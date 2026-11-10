#!/usr/bin/env python3
"""Durable 30 s memory inventory line in the Core journal (adapt_memory_inventory), before and after.

Usage: melonx_memory_inventory_test.py <Core 658 prepared MeloNX tree>
       melonx_memory_inventory_test.py <control> --candidate-source <final preparation containing the adapter>

Control is the Core 658 preparation, candidate adds the adapter. Static: GpuContext.cs is the control plus one call
after the Info report and the inventory members only; the added code triggers no collection, takes no lock and changes
no cache, budget or trim. The production Ryujinx.Graphics.Gpu assembly builds on both sides. Behaviour: the side's real
GpuContext members from DeviceShortPercent to the end of CheckHostMemory (and the candidate's inventory members) run in
a fixture (test/melonx_memory_inventory/Program.cs) with doubles for the host budget, the GPU caches, the graphics
configuration and the logger, and the tree's real EmbeddedLaunchDiagnostics journal: both sides give the same Info
reports, gates and trims; the control writes no Core journal line, the candidate one line per report with the doubles'
values and the runtime's last-collection values (LOH occupied = LOH size - free), 120 reports at 30 s then one in 4,
at most 240 lines. Writes dist/melonx/memory-inventory-checks.json. No device.
"""
from pathlib import Path
import hashlib, json, os, re, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, files_edited_later  # noqa: E402
_HOLD = []
FINAL_SOURCE = SOURCE
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_memory_inventory', _HOLD)
from adapt_memory_inventory import apply, BASELINE, INVENTORY  # noqa: E402

CONTEXT = 'src/Ryujinx.Graphics.Gpu/GpuContext.cs'
JOURNAL = 'src/Ryujinx.Common/EmbeddedLaunchDiagnostics.cs'
FIXTURE = 'test/melonx_memory_inventory/Program.cs'
CALL = '\n            RecordMemoryInventory(device, textures, textureLimit, buffers, bufferLimit);\n'
DOTNET = os.environ.get('DOTNET', 'dotnet')
ENVIRONMENT = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
MIB = 1024 * 1024
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


for name, expected in BASELINE.items():
    check(sha(SOURCE / name) == expected, 'not the Core 658 preparation: ' + name)

texts, reports = {}, {}
with tempfile.TemporaryDirectory(prefix='melonx-memory-inventory-') as temporary:
    for variant in ('control', 'candidate'):
        work = Path(temporary).resolve() / variant
        shutil.copytree(SOURCE, work, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
        if variant == 'candidate':
            changed = apply(work)
            check(sorted(str(p.relative_to(work)) for p in changed) == sorted(BASELINE), 'adapter changed other files')
            if FINAL_PREPARATION:
                later = files_edited_later('adapt_memory_inventory')
                for name in BASELINE:
                    if name not in later:
                        check((work / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)
        text = (work / CONTEXT).read_text(encoding='utf-8-sig')
        texts[variant] = text
        result = subprocess.run([DOTNET, 'build', str(work / 'src/Ryujinx.Graphics.Gpu/Ryujinx.Graphics.Gpu.csproj'), '-c', 'Release',
                                 '-nologo', '-m:1', '-p:NuGetAudit=false'], capture_output=True, text=True, timeout=1800,
                                env=ENVIRONMENT, cwd=work)
        if result.returncode:
            print(result.stdout[-5000:], result.stderr[-2000:], flush=True)
        check(result.returncode == 0, variant + ' production Ryujinx.Graphics.Gpu builds')

        start = text.index('        private const int DeviceShortPercent = 7;')
        end = text.index('        /// <summary>\n        /// Advances internal sequence number.')
        members = text[start:end]
        check('public void CheckHostMemory()' in members and ('private void RecordMemoryInventory(' in members) == (variant == 'candidate'),
              variant + ': fixture runs the real CheckHostMemory' + (' and RecordMemoryInventory' if variant == 'candidate' else ''))
        fixture = Path(temporary).resolve() / ('fixture-' + variant)
        fixture.mkdir()
        (fixture / 'Program.cs').write_text((ROOT / FIXTURE).read_text().replace('        //__GPU_CONTEXT_MEMBERS__\n', members))
        shutil.copyfile(work / JOURNAL, fixture / 'EmbeddedLaunchDiagnostics.cs')
        (fixture / 'Fixture.csproj').write_text(
            '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
            '<Nullable>disable</Nullable><NuGetAudit>false</NuGetAudit><AllowUnsafeBlocks>true</AllowUnsafeBlocks>'
            '<NoWarn>CS0067;CS0414;CS0649;CS8321</NoWarn></PropertyGroup></Project>\n')
        for command in ([DOTNET, 'build', str(fixture / 'Fixture.csproj'), '-c', 'Release', '-nologo', '-p:NuGetAudit=false'],
                        [DOTNET, str(fixture / 'bin/Release/net10.0/Fixture.dll')]):
            result = subprocess.run(command, capture_output=True, text=True, timeout=900, env=ENVIRONMENT, cwd=fixture)
            if result.returncode:
                print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
                result.check_returncode()
        reports[variant] = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))

# Static: one call after the Info report and the inventory members, nothing else.
control, candidate = texts['control'], texts['candidate']
check(candidate.count(CALL) == 1 and candidate.count(INVENTORY) == 1 and
      candidate.replace(INVENTORY, '', 1).replace(CALL, '', 1) == control, 'GpuContext unchanged but the call and the inventory members')
report_end = candidate.index('$"managed heap {GC.GetGCMemoryInfo().HeapSizeBytes / (long)TrimMiB} MiB");')
check(report_end < candidate.index(CALL) < candidate.index('private void RecordMemoryInventory('), 'the line follows the Info report')
check(not re.search(r'GC\.Collect\(|GCSettings|AddMemoryPressure|\.Trim\(|TrimCaches|CacheLimit\s*=|lock \(|Interlocked|Thread\.', INVENTORY),
      'no collection, GC setting, trim, cache limit, lock or thread')
check(INVENTORY.count('EmbeddedLaunchDiagnostics.Record(') == 1 and 'EmbeddedLaunchDiagnostics.Record("memoryInventory", "sample",' in INVENTORY and
      '"begin"' not in INVENTORY, 'one memoryInventory journal call, never begin')

# Behaviour.
c, k = reports['control'], reports['candidate']
for key in ('infoWhenOff', 'infoAfterFirst', 'infoWithinGate', 'trims', 'reports', 'firstInfo'):
    check(c[key] == k[key], 'same Info reports, gates and trims: ' + key)
check(c['infoWhenOff'] == 0 and c['infoAfterFirst'] == 1 and c['infoWithinGate'] == 1 and c['trims'] == 1 and c['reports'] == 800,
      'control path observed: gated reports, one device-short trim')
check(c['inventoryWhenOff'] == c['inventoryAfterFirst'] == c['inventoryLines'] == 0, 'control writes no memoryInventory line')
check(k['inventoryWhenOff'] == 0 and k['inventoryAfterFirst'] == 1 and k['inventoryWithinGate'] == 1, 'one line per report, the report\'s gates kept')
d = k['firstDetail']
check(d['schema'] == 1 and d['line'] == 1 and d['report'] == 1 and d['maxLines'] == 240 and d['reportIntervalMs'] == 30000, 'ordinals and bound')
check(d['footprintBytes'] == 4566 * MIB and d['availableBytes'] == 2089 * MIB and d['deviceAvailablePercent'] == 11, 'footprint, headroom, device %')
check(d['textureCacheBytes'] == 155 * MIB and d['textureCacheLimitBytes'] == 768 * MIB and d['bufferCacheBytes'] == 30 * MIB and
      d['bufferCacheLimitBytes'] == 554 * MIB, 'texture and buffer cache sizes summed over the physical memories')
check(d['lastGcIndex'] == k['expectedGcIndex'] and d['lohAfterBytes'] == k['expectedLohAfter'] and d['lohFreeAfterBytes'] == k['expectedLohFree'] and
      d['lohOccupiedAfterBytes'] == max(0, k['expectedLohAfter'] - k['expectedLohFree']) and d['lohOccupiedAfterBytes'] >= 2 * MIB and
      d['lastGcHeapBytes'] == k['expectedHeap'], 'last collection: index, heap, LOH size, free and occupied (2 MiB of large objects kept)')
check(d['gen2AfterBytes'] == k['expectedGen2After'] and d['gen2FreeAfterBytes'] == k['expectedGen2Free'] and d['lastGcCommittedBytes'] > 0 and d['managedInUseBytes'] > 0 and
      len(d['collections']) == 3 and d['collections'][2] >= 1, 'gen2, committed, in-use bytes and collection counts')
expected_reports = list(range(1, 121)) + list(range(124, 601, 4))
check(k['inventoryLines'] == 240 and k['lineOrdinals'] == list(range(1, 241)) and k['reportNumbers'] == expected_reports,
      '120 reports at 30 s, then one in 4, at most 240 lines over 800 reports')
check(k['intervals'] == [30000, 120000] and k['maxLength'] < 4096, 'interval per line, bounded lines')

inputs = ['build-utils/melonx/adapt_memory_inventory.py', 'build-utils/melonx/adapt_session.py', 'test/melonx_memory_inventory_test.py',
          FIXTURE, 'test/melonx_adapter_control.py']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core658Preparation',
               postimages={p: sha(FINAL_SOURCE / p) for p in BASELINE} if FINAL_PREPARATION else {},
               sourceBaseline=BASELINE, sdk=sdk, physicalDeviceTested=False, productionGpuAssemblyBuilt=True,
               firstLine=k['firstDetail'], inventoryLines=k['inventoryLines'],
               inputs={p: sha(ROOT / p) for p in inputs},
               limitation='Host fixture with doubles for the iOS budget values (footprint, headroom, device %) and the GPU '
                          'caches; the device values, and the Metal and native memory outside these counters, are known only '
                          'from a device run. Journal only.')
out = ROOT / 'dist/melonx/memory-inventory-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
