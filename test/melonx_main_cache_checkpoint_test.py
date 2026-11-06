#!/usr/bin/env python3
"""adapt_main_cache_checkpoint on the final preparation, against the Core 671 preparation as control.

The main Vulkan pipeline cache is written during play from a worker thread (at most every 180 s, after 64 main pipelines
or a merge, only when the lock is free), and a render-thread creation that would only try the lock waits for it while a
checkpoint holds it (no skipped draw).

Control: the final preparation with the adapter reversed (melonx_adapter_control), which must be the Core 671 bytes.
Executed (test/melonx_main_cache_checkpoint) for control and candidate: the variant's real PipelineCacheManager.cs and
VulkanException.cs with a host Vulkan double (each cache a byte count; every read recorded with its thread and whether
the main cache lock is held). No device. Writes dist/melonx/main-cache-checkpoint-checks.json.
"""
from pathlib import Path
import hashlib, json, os, platform, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
FINAL_SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
import melonx_adapter_control as control_tools  # noqa: E402
import adapt_main_cache_checkpoint as adapter  # noqa: E402

DOTNET = os.environ.get('DOTNET', 'dotnet')
VULKAN = 'src/Ryujinx.Graphics.Vulkan/'
MANAGER, STATE = VULKAN + 'PipelineCacheManager.cs', VULKAN + 'PipelineState.cs'
HARNESS = ROOT / 'test/melonx_main_cache_checkpoint'
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


temporary = tempfile.TemporaryDirectory(prefix='melonx-main-cache-checkpoint-')
WORK = Path(temporary.name).resolve()  # resolved: on macOS /var is a link to /private/var
# The adapter's postimage: later adapters that edit its files (adapt_checkpoint_side_cache, Core 675) reversed first.
POST = WORK / 'post'
for name in adapter.BASELINE:
    (POST / name).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(FINAL_SOURCE / name, POST / name)
for later in reversed(control_tools.later_sharing('adapt_main_cache_checkpoint')):
    control_tools._reverse(later, POST)
shutil.copyfile(FINAL_SOURCE / (VULKAN + 'VulkanException.cs'), POST / (VULKAN + 'VulkanException.cs'))
FINAL_SOURCE = POST
CONTROL = WORK / 'control'
for name in adapter.BASELINE:
    (CONTROL / name).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(FINAL_SOURCE / name, CONTROL / name)
shutil.copyfile(FINAL_SOURCE / (VULKAN + 'VulkanException.cs'), WORK / 'VulkanException.cs')

# --- Control: the adapter reversed must be the Core 671 bytes; forward reproduces the final preparation ---
control_tools._reverse('adapt_main_cache_checkpoint', CONTROL)
for name, expected in adapter.BASELINE.items():
    check(sha(CONTROL / name) == expected, 'control is the Core 671 preparation: ' + name)
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
notify = member(manager, 'public void NotifyWorkerPipelineCreated(int workerIndex)')
check(notify.index('Maintain(state, force: false);') < notify.index('CheckpointMainIfDue();'), 'the checkpoint runs after the worker upkeep')
checkpoint = member(manager, 'private void CheckpointMainIfDue()')
check(checkpoint.count('_mainCacheLock.TryEnter()') == 1 and 'lock (_mainCacheLock)' not in checkpoint and '.Enter()' not in checkpoint,
      'the worker only tries the main cache lock; it never waits for it')
check(checkpoint.index('_mainCheckpointInProgress = true;') < checkpoint.index('_mainCacheLock.TryEnter()') and
      checkpoint.rindex('_mainCacheLock.Exit();') < checkpoint.rindex('_mainCheckpointInProgress = false;'),
      'the flag is raised before the lock is tried and lowered after it is released')
check('SaveCache(main, size, final: false);' in checkpoint and 'size > main.Budget' in checkpoint, 'the same save and budget rule as at close')
check(manager.count('CheckpointMainIfDue()') == 2, 'only the worker completion calls the checkpoint')
for name in ('public void NotifyMainPipelineCreated()', 'public void MergeAndSave()', 'private void Maintain(CacheState state, bool force, bool allowRecycle = true)'):
    check(member(manager, name) == member(read(CONTROL, MANAGER), name), 'unchanged: ' + name)
state = read(FINAL_SOURCE, STATE)
check(state.replace(adapter.LOCK_NEW, adapter.LOCK_OLD) == read(CONTROL, STATE) and state.count('MainCheckpointInProgress') == 1,
      'PipelineState differs only by the wait while a checkpoint holds the lock')

# --- Executed: control and candidate fixtures ---
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1')
reports = {}
for variant in ('control', 'candidate'):
    tree = CONTROL if variant == 'control' else FINAL_SOURCE
    fixture = WORK / ('fixture-' + variant)
    fixture.mkdir()
    shutil.copyfile(tree / MANAGER, fixture / 'PipelineCacheManager.cs')
    shutil.copyfile(WORK / 'VulkanException.cs', fixture / 'VulkanException.cs')
    for name in ('Double.cs', 'Program.cs'):
        shutil.copyfile(HARNESS / name, fixture / name)
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
check(c['played']['mainFile'] is False and c['played']['mainReads'] == [], 'control: nothing writes the main cache during play')
p = k['played']
check(p['mainFile'] and p['mainFileBytes'] == p['mainBytes'] and p['infoLines'] == 1, 'candidate: the main cache is written whole during play')
check(len(p['mainReads']) == 1 and p['mainReads'][0].startswith('worker0 ') and p['mainReads'][0].endswith('lockHeld=True'),
      'read once, on the worker thread, under the main cache lock')
check(k['withinInterval']['mainReads'] == [], 'not again within 180 s')
r = k['renderHoldsLock']
check(r['mainReads'] == [] and not r['mainFile'] and r['workerMs'] < 200 and r['flagLeftRaised'] is False,
      'a lock held by the render thread is not waited for and nothing is written: %s' % r)
check(len(k['afterRenderReleased']['mainReads']) == 1 and k['afterRenderReleased']['mainFile'], 'the next worker completion writes it')
check(k['fewPipelines']['mainReads'] == [] and not k['fewPipelines']['mainFile'], 'fewer than 64 main pipelines and no merge: no write')
s = k['slowCheckpoint']
check(s['flagSeen'] and s['renderTryEnterFailedWhileRaised'] and s['flagAfter'] is False and s['mainFile'],
      'during a checkpoint the flag is raised whenever the lock is held by it (the render path waits), and clears after')
check(c['warnings'] == 0 and k['warnings'] == 0, 'no warning or error line')

inputs = ['build-utils/melonx/adapt_main_cache_checkpoint.py', 'build-utils/melonx/adapt_checkpoint_side_cache.py', 'build-utils/melonx/adapt_session.py', 'test/melonx_main_cache_checkpoint_test.py',
          'test/melonx_main_cache_checkpoint/Double.cs', 'test/melonx_main_cache_checkpoint/Program.cs', 'test/melonx_adapter_control.py']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=True, sourceKind='finalPreparationWithReversedControl',
               postimages={n: sha(FINAL_SOURCE / n) for n in adapter.BASELINE}, reports=reports, sdk=sdk, host=platform.system(),
               physicalDeviceTested=False, gameTested=False, inputs={n: sha(ROOT / n) for n in inputs},
               limitation='Host fixture of the real cache manager with a Vulkan double. The checkpoint duration on an iPhone, '
                          'the pipelines kept across crashed sessions and the stutter reduction are known only from a device run.')
out = ROOT / 'dist/melonx/main-cache-checkpoint-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
