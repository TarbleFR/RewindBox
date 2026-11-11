#!/usr/bin/env python3
"""adapt_vulkan_memory_journal on the final preparation, against the Core 725 preparation as control.

Usage: melonx_vulkan_memory_journal_test.py <final preparation> (or --candidate-source <final preparation>)

Static: the candidate is the control plus the adapter's replacements only; no allocation, free, block creation or
destruction code changes (Allocate, Free, InsertBlock and the allocator's Allocate are the control's text); the journal
call is inside a try/catch, bounded (60 lines) and every sixth window. Executed on the production
Ryujinx.Graphics.Vulkan of the candidate (test-only InternalsVisibleTo, no Vulkan device): real
MemoryAllocatorBlockList.Block objects (two pooled 4 MiB blocks with 1.5 MiB and 4 KiB allocated, one mapped, one
dedicated 8 MiB) in a real block list, and a real MemoryAllocator holding it and an image list; UsageText must give the
exact totals and per-list figures; RenderStageTimer.Log run 13 times must write 3 "vulkanMemory sample" lines to a
temporary engine journal, then nothing once the bound is reached. Writes dist/melonx/vulkan-memory-journal-checks.json.
"""
from pathlib import Path
import hashlib, json, os, platform, re, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, files_edited_later  # noqa: E402
_HOLD = []
CONTROL, FINAL_PREPARATION = control_source(SOURCE, 'adapt_vulkan_memory_journal', _HOLD)
import adapt_vulkan_memory_journal as adapter  # noqa: E402

DOTNET = os.environ.get('DOTNET', 'dotnet')
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def member(text, signature):
    start = text.rindex('\n', 0, text.index(signature)) + 1
    depth, index = 0, text.index('{', start)
    for index in range(index, len(text)):
        depth += (text[index] == '{') - (text[index] == '}')
        if depth == 0:
            return text[start:index + 1]
    raise AssertionError(signature)


check(FINAL_PREPARATION, 'the source given is a final preparation containing the adapter')
check(not files_edited_later('adapt_vulkan_memory_journal'), 'no later adapter edits its files')
for name, expected in adapter.BASELINE.items():
    check(sha(CONTROL / name) == expected, 'control is the Core 725 preparation: ' + name)
    control_text = (CONTROL / name).read_text(encoding='utf-8-sig')
    rebuilt = control_text
    for old, new in adapter.EDITS[name]:
        check(rebuilt.count(old) == 1, 'one site: ' + old.strip()[:50])
        rebuilt = rebuilt.replace(old, new)
    check(rebuilt == (SOURCE / name).read_text(encoding='utf-8-sig'), 'the candidate is the control plus the replacements: ' + name)
blocks_c = (CONTROL / adapter.BLOCKS).read_text(encoding='utf-8-sig')
blocks_k = (SOURCE / adapter.BLOCKS).read_text(encoding='utf-8-sig')
for signature in ('public unsafe MemoryAllocation Allocate(ulong size, ulong alignment, bool map)', 'private void InsertBlock(Block block)',
                  'public ulong Allocate(ulong size, ulong alignment)'):
    check(member(blocks_c, signature) == member(blocks_k, signature), 'allocation unchanged: ' + signature)
alloc_c = (CONTROL / adapter.ALLOCATOR).read_text(encoding='utf-8-sig')
alloc_k = (SOURCE / adapter.ALLOCATOR).read_text(encoding='utf-8-sig')
check(member(alloc_c, 'private MemoryAllocation Allocate(int memoryTypeIndex') == member(alloc_k, 'private MemoryAllocation Allocate(int memoryTypeIndex'),
      'allocator allocation unchanged')
log = member((SOURCE / adapter.STAGES).read_text(encoding='utf-8-sig'), 'private static void Log(long end)')
check(log.index('_memoryWindows++ % 6 == 0 && _memoryLines < 60') < log.index('try') < log.index('Record("vulkanMemory", "sample"') < log.index('catch'),
      'bounded, every sixth window, failures ignored')

PROGRAM = r'''using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Threading;
using Ryujinx.Graphics.Vulkan;
using Silk.NET.Vulkan;

const ulong MiB = 1024 * 1024;
var flags = BindingFlags.NonPublic | BindingFlags.Instance;
var pooledA = new MemoryAllocatorBlockList.Block(default, (nint)0x1000, 4 * MiB, false);
var pooledB = new MemoryAllocatorBlockList.Block(default, nint.Zero, 4 * MiB, false);
var dedicated = new MemoryAllocatorBlockList.Block(default, nint.Zero, 8 * MiB, true);
pooledA.Allocate(MiB + MiB / 2, 256);
pooledB.Allocate(4096, 256);
var buffers = new MemoryAllocatorBlockList(null, default, 3, (int)(4 * MiB), true);
((List<MemoryAllocatorBlockList.Block>)typeof(MemoryAllocatorBlockList).GetField("_blocks", flags).GetValue(buffers)).AddRange(new[] { pooledA, pooledB });
typeof(MemoryAllocatorBlockList).GetField("_dedicatedBlocks", flags).SetValue(buffers, new List<MemoryAllocatorBlockList.Block> { dedicated });
var images = new MemoryAllocatorBlockList(null, default, 1, (int)(4 * MiB), false);
var imageBlock = new MemoryAllocatorBlockList.Block(default, nint.Zero, 4 * MiB, false);
imageBlock.Allocate(2 * MiB, 256);
((List<MemoryAllocatorBlockList.Block>)typeof(MemoryAllocatorBlockList).GetField("_blocks", flags).GetValue(images)).Add(imageBlock);
var allocator = (MemoryAllocator)System.Runtime.CompilerServices.RuntimeHelpers.GetUninitializedObject(typeof(MemoryAllocator));
typeof(MemoryAllocator).GetField("_blockLists", flags).SetValue(allocator, new List<MemoryAllocatorBlockList> { images, buffers });
typeof(MemoryAllocator).GetField("_lock", flags).SetValue(allocator, new ReaderWriterLockSlim(LockRecursionPolicy.NoRecursion));
string usage = allocator.UsageText();

string journal = Path.Combine(Path.GetTempPath(), "melonx-vulkan-memory-" + Environment.ProcessId, "MeloNX-core.log");
Directory.CreateDirectory(Path.GetDirectoryName(journal));
Ryujinx.Common.EmbeddedLaunchDiagnostics.ConfigureJournal(journal);
RenderStageTimer.MemoryUsage = allocator.UsageText;
var logMethod = typeof(RenderStageTimer).GetMethod("Log", BindingFlags.NonPublic | BindingFlags.Static);
int counted(int calls) { for (int i = 0; i < calls; i++) logMethod.Invoke(null, new object[] { (long)(i + 1) * 1000 }); return File.ReadAllLines(journal).Count(l => l.Contains("\"stage\":\"vulkanMemory\"")); }
int after13 = counted(13);
typeof(RenderStageTimer).GetField("_memoryLines", BindingFlags.NonPublic | BindingFlags.Static).SetValue(null, 60);
int afterBound = counted(12);
Console.WriteLine(System.Text.Json.JsonSerializer.Serialize(new Dictionary<string, object> { ["usage"] = usage, ["after13"] = after13, ["afterBound"] = afterBound }));
'''
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1')
temporary = tempfile.TemporaryDirectory(prefix='melonx-vulkan-memory-')
WORK = Path(temporary.name).resolve()
tree = WORK / 'tree'
shutil.copytree(SOURCE, tree, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
project = tree / 'src/Ryujinx.Graphics.Vulkan/Ryujinx.Graphics.Vulkan.csproj'
project.write_text(project.read_text(encoding='utf-8-sig').replace(
    '</Project>', '  <ItemGroup><InternalsVisibleTo Include="MeloNXMemoryProbe" /></ItemGroup>\n</Project>'))
probe = WORK / 'probe'
probe.mkdir()
(probe / 'Program.cs').write_text(PROGRAM)
(probe / 'MeloNXMemoryProbe.csproj').write_text(f'''<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><Nullable>disable</Nullable>
    <AllowUnsafeBlocks>true</AllowUnsafeBlocks><NuGetAudit>false</NuGetAudit><ManagePackageVersionsCentrally>false</ManagePackageVersionsCentrally></PropertyGroup>
  <ItemGroup><ProjectReference Include="{project}" /></ItemGroup>
</Project>
''')
for extra in ('global.json', 'nuget.config'):
    if (tree / extra).exists():
        shutil.copyfile(tree / extra, probe / extra)
build = subprocess.run([DOTNET, 'build', str(probe / 'MeloNXMemoryProbe.csproj'), '-c', 'Release', '-nologo', '-m:1', '-p:NuGetAudit=false'],
                       capture_output=True, text=True, timeout=2400, env=environment, cwd=probe)
if build.returncode:
    print('\n'.join(sorted({l for l in build.stdout.splitlines() if ' error ' in l}))[:4000], flush=True)
check(build.returncode == 0, 'the probe builds against the production Vulkan assembly')
run = subprocess.run([DOTNET, str(probe / 'bin/Release/net10.0/MeloNXMemoryProbe.dll')], capture_output=True, text=True, timeout=600, env=environment, cwd=probe)
if run.returncode:
    print(run.stdout[-2000:], run.stderr[-3000:], flush=True)
check(run.returncode == 0, 'the probe ran')
report = json.loads(run.stdout.strip().splitlines()[-1])
usage = report['usage']
check(usage.startswith('Vulkan device memory: 4 blocks 20 MiB (dedicated 8 MiB, mapped 4 MiB, pooled free 8 MiB) in 2 lists; '),
      'totals: 4 blocks, 20 MiB, dedicated 8, mapped 4, pooled free 2.5+3.99+2 = 8 MiB (floor): ' + usage)
check('; type 3 buffers: 3 blocks 16 MiB (dedicated 8 MiB, mapped 4 MiB, pooled free 6 MiB)' in usage and
      '; type 1 images: 1 blocks 4 MiB (dedicated 0 MiB, mapped 0 MiB, pooled free 2 MiB)' in usage and
      usage.index('type 3 buffers') < usage.index('type 1 images') and usage.endswith(' (adapt_vulkan_memory_journal)'),
      'per list, largest first: ' + usage)
check(report['after13'] == 3 and report['afterBound'] == 3, 'every sixth window (1, 7, 13), nothing past the bound: %s' % report)

inputs = ['build-utils/melonx/adapt_vulkan_memory_journal.py', 'build-utils/melonx/adapt_session.py', 'test/melonx_vulkan_memory_journal_test.py',
          'test/melonx_adapter_control.py']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=True, sourceKind='finalPreparationWithReversedControl',
               productionVulkanAssemblyBuilt=True, postimages={name: sha(SOURCE / name) for name in adapter.BASELINE},
               usage=usage, linesAfter13Windows=report['after13'], sdk=sdk, host=platform.system(), physicalDeviceTested=False,
               inputs={name: sha(ROOT / name) for name in inputs},
               limitation='Real block and allocator objects without a Vulkan device (no device memory is allocated); the figures '
                          'on an iPhone are what this line will show.')
out = ROOT / 'dist/melonx/vulkan-memory-journal-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
