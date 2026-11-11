#!/usr/bin/env python3
"""adapt_pause_checkpoint_growth on the final preparation, against the Core 725 preparation as control.

Usage: melonx_pause_checkpoint_growth_test.py <final preparation> (or --candidate-source <final preparation>)

Static: the control is the Core 725 file; the candidate differs by the adapter's one replacement; the pause and play
callers and SaveCache are the control's text; the play rule is unchanged. Executed on the production
Ryujinx.Graphics.Vulkan of each side: PipelineCacheManager.MainGrowthWorthWriting (its real code, called by reflection
on an instance with only the written size and time set) for the IPA 724 pause (+1.06 MiB, 191 s), a pause with nothing
new, with 8 MiB new, with 1 MiB new after 11 min, and three play cases. Expected: control writes on every growth at a
pause, candidate only from 8 MiB; play identical. No device. Writes dist/melonx/pause-checkpoint-growth-checks.json.
"""
from pathlib import Path
import hashlib, json, os, platform, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, files_edited_later  # noqa: E402
_HOLD = []
CONTROL, FINAL_PREPARATION = control_source(SOURCE, 'adapt_pause_checkpoint_growth', _HOLD)
import adapt_pause_checkpoint_growth as adapter  # noqa: E402

DOTNET = os.environ.get('DOTNET', 'dotnet')
VULKAN = 'src/Ryujinx.Graphics.Vulkan/'
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
check(not files_edited_later('adapt_pause_checkpoint_growth'), 'no later adapter edits the file')
control_text = (CONTROL / adapter.MANAGER).read_text(encoding='utf-8-sig')
candidate_text = (SOURCE / adapter.MANAGER).read_text(encoding='utf-8-sig')
check(sha(CONTROL / adapter.MANAGER) == adapter.BASELINE[adapter.MANAGER], 'control is the Core 725 preparation')
check(control_text.replace(adapter.RULE_OLD, adapter.RULE_NEW) == candidate_text and control_text.count(adapter.RULE_OLD) == 1,
      'the candidate is the control plus the one replacement')
for signature in ('public void CheckpointMainOnPause()', 'private void CheckpointMainIfDue()', 'private unsafe void SaveCache(CacheState state, long size, bool final)'):
    check(member(control_text, signature) == member(candidate_text, signature), 'unchanged: ' + signature)
check('MainCheckpointMinimumGrowthBytes = 8L * 1024 * 1024' in candidate_text and 'MainCheckpointStaleMs = 600_000' in candidate_text,
      'the play bounds are unchanged (8 MiB, 10 min)')

PROGRAM = r'''using System;
using System.Collections.Generic;
using System.Reflection;
using System.Runtime.CompilerServices;

// The manager is internal to the production assembly: found by name, its private decision invoked by reflection.
var type = typeof(Ryujinx.Graphics.Vulkan.VulkanRenderer).Assembly.GetType("Ryujinx.Graphics.Vulkan.PipelineCacheManager", throwOnError: true);
var decide = type.GetMethod("MainGrowthWorthWriting", BindingFlags.NonPublic | BindingFlags.Instance);
var bytes = type.GetField("_mainWrittenBytes", BindingFlags.NonPublic | BindingFlags.Instance);
var stamp = type.GetField("_mainWrittenTimestamp", BindingFlags.NonPublic | BindingFlags.Instance);
const long MiB = 1024 * 1024;
long file = 793 * MiB + 104 * 1024;
var cases = new (string Name, long Grown, long SinceMs, bool Pause)[]
{
    ("pauseIpa724", (long)(1.06 * MiB), 191_000, true), ("pauseNothing", 0, 20_000, true), ("pause8MiB", 8 * MiB, 60_000, true),
    ("pause1MiBAfter11Min", 1 * MiB, 660_000, true), ("play1MiB", 1 * MiB, 60_000, false), ("play8MiB", 8 * MiB, 60_000, false),
    ("play1MiBAfter11Min", 1 * MiB, 660_000, false),
};
var report = new List<string>();
foreach (var c in cases)
{
    object manager = RuntimeHelpers.GetUninitializedObject(type);
    long now = 10_000_000;
    bytes.SetValue(manager, file);
    stamp.SetValue(manager, now - c.SinceMs);
    bool write = (bool)decide.Invoke(manager, new object[] { file + c.Grown, now, c.Pause });
    report.Add("\"" + c.Name + "\": " + (write ? "true" : "false"));
}
Console.WriteLine("{" + string.Join(", ", report) + "}");
'''
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1')
temporary = tempfile.TemporaryDirectory(prefix='melonx-pause-checkpoint-')
WORK = Path(temporary.name).resolve()


def run(side, source):
    tree = WORK / side / 'tree'
    shutil.copytree(source, tree, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
    probe = WORK / side / 'probe'
    probe.mkdir()
    (probe / 'Program.cs').write_text(PROGRAM)
    (probe / 'Probe.csproj').write_text(f'''<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><Nullable>disable</Nullable>
    <NuGetAudit>false</NuGetAudit><ManagePackageVersionsCentrally>false</ManagePackageVersionsCentrally></PropertyGroup>
  <ItemGroup><ProjectReference Include="{tree}/src/Ryujinx.Graphics.Vulkan/Ryujinx.Graphics.Vulkan.csproj" /></ItemGroup>
</Project>
''')
    for extra in ('global.json', 'nuget.config'):
        if (tree / extra).exists():
            shutil.copyfile(tree / extra, probe / extra)
    build = subprocess.run([DOTNET, 'build', str(probe / 'Probe.csproj'), '-c', 'Release', '-nologo', '-m:1', '-p:NuGetAudit=false'],
                           capture_output=True, text=True, timeout=2400, env=environment, cwd=probe)
    if build.returncode:
        print(build.stdout[-3000:], build.stderr[-2000:], flush=True)
    check(build.returncode == 0, side + ': the probe builds against the production Vulkan assembly')
    result = subprocess.run([DOTNET, str(probe / 'bin/Release/net10.0/Probe.dll')], capture_output=True, text=True, timeout=600,
                            env=environment, cwd=probe)
    if result.returncode:
        print(result.stdout[-2000:], result.stderr[-3000:], flush=True)
    check(result.returncode == 0, side + ': the probe ran')
    return json.loads(result.stdout.strip().splitlines()[-1])


control, candidate = run('control', CONTROL), run('candidate', SOURCE)
check(control == dict(pauseIpa724=True, pauseNothing=False, pause8MiB=True, pause1MiBAfter11Min=True, play1MiB=False, play8MiB=True,
                      play1MiBAfter11Min=True), 'control: a pause writes on any growth: %s' % control)
check(candidate == dict(pauseIpa724=False, pauseNothing=False, pause8MiB=True, pause1MiBAfter11Min=False, play1MiB=False, play8MiB=True,
                        play1MiBAfter11Min=True), 'candidate: a pause writes from 8 MiB, play unchanged: %s' % candidate)
check(all(control[k] == candidate[k] for k in control if k.startswith('play')), 'play decisions identical')

inputs = ['build-utils/melonx/adapt_pause_checkpoint_growth.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_pause_checkpoint_growth_test.py', 'test/melonx_adapter_control.py']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=True, sourceKind='finalPreparationWithReversedControl',
               productionVulkanAssemblyBuilt=True, postimages={adapter.MANAGER: sha(SOURCE / adapter.MANAGER)},
               control=control, candidate=candidate, sdk=sdk, host=platform.system(), physicalDeviceTested=False,
               inputs={name: sha(ROOT / name) for name in inputs},
               limitation='The decision only, on the production method; the write itself, the lock hold after a resume and the '
                          'freeze it caused are shown only by a device run (pipelineCache checkpoint / checkpointSkipped lines).')
out = ROOT / 'dist/melonx/pause-checkpoint-growth-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
