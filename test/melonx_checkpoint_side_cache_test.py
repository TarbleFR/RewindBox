#!/usr/bin/env python3
"""adapt_checkpoint_side_cache on the final preparation, against the Core 673 postimage as control.

While a play-time checkpoint holds the main pipeline cache lock, a main-cache creation goes to a side cache with its own
lock (no wait, no failure); the side cache is merged into main at the end of the checkpoint, under the main lock.
Control: the final preparation with the adapter reversed (melonx_adapter_control), which must be the Core 673 bytes.
Executed (test/melonx_checkpoint_side_cache with test/melonx_main_cache_checkpoint/Double.cs) for control and candidate
on the variant's real PipelineCacheManager.cs. Writes dist/melonx/checkpoint-side-cache-checks.json.
"""
from pathlib import Path
import hashlib, json, os, platform, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
FINAL_SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
import melonx_adapter_control as control_tools  # noqa: E402
import adapt_checkpoint_side_cache as adapter  # noqa: E402

DOTNET = os.environ.get('DOTNET', 'dotnet')
VULKAN = 'src/Ryujinx.Graphics.Vulkan/'
MANAGER, STATE = VULKAN + 'PipelineCacheManager.cs', VULKAN + 'PipelineState.cs'
HARNESS = ROOT / 'test/melonx_checkpoint_side_cache'
DOUBLE = ROOT / 'test/melonx_main_cache_checkpoint/Double.cs'
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(tree, name):
    return (tree / name).read_text(encoding='utf-8-sig')


def member(text, signature):
    start = text.rindex('\n', 0, text.index(signature)) + 1
    depth, index = 0, text.index('{', start)
    for index in range(index, len(text)):
        depth += (text[index] == '{') - (text[index] == '}')
        if depth == 0:
            return text[start:index + 1]
    raise AssertionError(signature)


temporary = tempfile.TemporaryDirectory(prefix='melonx-checkpoint-side-cache-')
WORK = Path(temporary.name).resolve()  # resolved: on macOS /var is a link to /private/var
CONTROL = WORK / 'control'
for name in adapter.BASELINE:
    (CONTROL / name).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(FINAL_SOURCE / name, CONTROL / name)
shutil.copyfile(FINAL_SOURCE / (VULKAN + 'VulkanException.cs'), WORK / 'VulkanException.cs')

# --- Control: the adapter reversed must be the Core 671 bytes; forward reproduces the final preparation ---
control_tools._reverse('adapt_checkpoint_side_cache', CONTROL)
for name, expected in adapter.BASELINE.items():
    check(sha(CONTROL / name) == expected, 'control is the Core 673 postimage: ' + name)
forward = WORK / 'forward'
for name in adapter.BASELINE:
    (forward / name).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(CONTROL / name, forward / name)
changed = sorted(str(p.relative_to(forward)) for p in adapter.apply(forward))
check(changed == sorted(adapter.BASELINE), 'the adapter changes only its files')
for name in adapter.BASELINE:
    check((forward / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)

# --- Static: the exact scope ---
manager = read(FINAL_SOURCE, MANAGER)
enter = member(manager, 'public bool EnterMainCreation(Lock mainLock, bool tryOnly, out PipelineCache target)')
check('mainLock.TryEnter(tryOnly ? 0 : 2)' in enter and '_mainCheckpointInProgress' in enter and '_sideCacheLock.Enter();' in enter and
      'mainLock.Enter()' not in enter, 'a main-cache creation only tries the main lock and uses the side cache during a checkpoint')
checkpoint = member(manager, 'private void CheckpointMainIfDue()')
fin = checkpoint[checkpoint.rindex('finally'):]
check(fin.index('MergeSideCache();') < fin.index('_mainCacheLock.Exit();') < fin.index('_mainCheckpointInProgress = false;'),
      'the side cache joins main under the main lock, before the flag is lowered')
check(manager.count('MergeSideCache()') == 2, 'only the checkpoint end merges the side cache')
state = read(FINAL_SOURCE, STATE)
check(state.count('EnterMainCreation(') == 2 and state.count('ExitMainCreation(') == 2 and 'PipelineCreationLock.Enter()' not in state and
      'PipelineCreationLock.TryEnter()' not in state and 'lock (gd.PipelineCreationLock)' not in state,
      'graphics and compute main-cache creations both go through EnterMainCreation; no direct main lock remains')
check(state.replace(adapter.COMPUTE_NEW, adapter.COMPUTE_OLD).replace(adapter.GRAPHICS_NEW, adapter.GRAPHICS_OLD) == read(CONTROL, STATE),
      'PipelineState differs only by the two creation paths')

# --- Executed: control and candidate fixtures ---
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1')
reports = {}
for variant in ('control', 'candidate'):
    tree = CONTROL if variant == 'control' else FINAL_SOURCE
    fixture = WORK / ('fixture-' + variant)
    fixture.mkdir()
    shutil.copyfile(tree / MANAGER, fixture / 'PipelineCacheManager.cs')
    shutil.copyfile(WORK / 'VulkanException.cs', fixture / 'VulkanException.cs')
    shutil.copyfile(DOUBLE, fixture / 'Double.cs')
    shutil.copyfile(HARNESS / 'Program.cs', fixture / 'Program.cs')
    constants = '<DefineConstants>$(DefineConstants);CANDIDATE</DefineConstants>' if variant == 'candidate' else ''
    (fixture / 'Fixture.csproj').write_text(
        '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
        '<Nullable>disable</Nullable><AllowUnsafeBlocks>true</AllowUnsafeBlocks><NuGetAudit>false</NuGetAudit>' + constants +
        '<NoWarn>CS0649;CS0414;CS0169;CS8321;CS0162;CS1998;CS8632</NoWarn></PropertyGroup></Project>\n')
    build = subprocess.run([DOTNET, 'build', str(fixture / 'Fixture.csproj'), '-c', 'Release', '-nologo', '-p:NuGetAudit=false'],
                           capture_output=True, text=True, timeout=900, env=environment, cwd=fixture)
    if build.returncode:
        print('\n'.join(line for line in build.stdout.splitlines() if ': error ' in line)[:6000], flush=True)
    check(build.returncode == 0, variant + ' fixture builds with the real PipelineCacheManager.cs')
    run = subprocess.run([DOTNET, str(fixture / 'bin/Release/net10.0/Fixture.dll'), variant],
                         capture_output=True, text=True, timeout=600, env=environment, cwd=fixture)
    if run.returncode:
        print(run.stdout[-4000:], run.stderr[-4000:], flush=True)
    check(run.returncode == 0, variant + ' fixture runs')
    reports[variant] = json.loads(run.stdout.strip().splitlines()[-1])
    print(variant + ': ' + json.dumps(reports[variant]), flush=True)

c, k = reports['control'], reports['candidate']
cd, kd = c['duringCheckpoint'], k['duringCheckpoint']
check(cd['blockingWaitMs'] >= 250 and cd['blockingIntoMain'], 'control (Core 673): the render thread waits for the checkpoint: %s ms' % cd['blockingWaitMs'])
check(kd['blockingWaitMs'] < 100 and kd['blockingCreated'] and not kd['blockingIntoMain'],
      'candidate: a blocking creation during the checkpoint goes to the side cache at once: %s ms' % kd['blockingWaitMs'])
check(kd['tryOnlyCreated'] and not kd['tryOnlyIntoMain'] and kd['tryOnlyWaitMs'] < 100, 'candidate: a try-only creation succeeds into the side cache (no skipped draw)')
check(kd['mergeAfterSave'] and kd['mergeLine'] == 'merge into main 1 lockHeld=True' and kd['mainGrowthBytes'] >= 2 * 64 * 1024,
      'the side cache joins main under the main lock after the save; its pipelines are in main')
check(kd['checkpointInProgressAfter'] is False, 'the flag is lowered after the checkpoint')
cn, kn = c['noCheckpoint'], k['noCheckpoint']
check(not cn['tryOnlyCreated'] and not kn['tryOnlyCreated'], 'outside a checkpoint a try-only creation still fails when another creation holds the lock')
check(kn['blockingIntoMain'] and kn['blockingWaitMs'] >= 100 and cn['blockingWaitMs'] >= 100, 'outside a checkpoint a blocking creation waits for main as before')
check(c['warnings'] == 0 and k['warnings'] == 0, 'no warning or error line')

inputs = ['build-utils/melonx/adapt_checkpoint_side_cache.py', 'build-utils/melonx/adapt_session.py', 'test/melonx_checkpoint_side_cache_test.py',
          'test/melonx_main_cache_checkpoint/Double.cs', 'test/melonx_checkpoint_side_cache/Program.cs', 'test/melonx_adapter_control.py']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=True, sourceKind='finalPreparationWithReversedControl',
               postimages={n: sha(FINAL_SOURCE / n) for n in adapter.BASELINE}, reports=reports, sdk=sdk, host=platform.system(),
               physicalDeviceTested=False, gameTested=False, inputs={n: sha(ROOT / n) for n in inputs},
               limitation='Host fixture of the real cache manager with a Vulkan double. The stutter at checkpoints on an iPhone is '
                          'known only from a device run.')
out = ROOT / 'dist/melonx/checkpoint-side-cache-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
