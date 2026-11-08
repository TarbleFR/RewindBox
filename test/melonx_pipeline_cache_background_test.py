#!/usr/bin/env python3
"""adapt_pipeline_cache_background on the final preparation, against the Core 693 files as control.

Usage: melonx_pipeline_cache_background_test.py <control> --candidate-source <final preparation containing the adapter>

IPA 693: gpuStartup mainPipelineCache took 536 s (cold system Metal cache: MoltenVK compiles every Metal library of
the 780 MiB snapshot while it creates the cache). Executed for control and candidate on the variant's real
PipelineCacheManager.cs with a Vulkan double whose snapshot creation takes 1.5-2 s
(test/melonx_pipeline_cache_background): the candidate's constructor no longer waits for it; the snapshot is created
on RewindBox.PipelineCacheLoad and merged into main there under the main lock; while it loads, a pause checkpoint and
the teardown save leave the file unchanged; a worker waits for the load; once loaded, the session's content is written
with the snapshot's; a session ending during the load does not wait and leaves the device release to the loader
thread, which destroys its cache and merges nothing; no snapshot means nothing pending; a rejected snapshot is
written over as before. Source: PipelineState's two worker lookups wait first, VulkanRenderer releases the device
through DeferDeviceRelease, nothing else changes. Writes dist/melonx/pipeline-cache-background-checks.json.
"""
from pathlib import Path
import hashlib, json, os, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
FINAL_SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source  # noqa: E402
_HOLD = []
CONTROL_SOURCE, FINAL_PREPARATION = control_source(FINAL_SOURCE, 'adapt_pipeline_cache_background', _HOLD)
import adapt_pipeline_cache_background as adapter  # noqa: E402

DOTNET = os.environ.get('DOTNET', 'dotnet')
VULKAN = 'src/Ryujinx.Graphics.Vulkan/'
HARNESS = ROOT / 'test/melonx_pipeline_cache_background'
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


for name, expected in adapter.BASELINE.items():
    check(sha(CONTROL_SOURCE / name) == expected, 'control is the Core 693 preparation: ' + name)

temporary = tempfile.TemporaryDirectory(prefix='melonx-pipeline-cache-background-')
WORK = Path(temporary.name).resolve()
CANDIDATE = WORK / 'candidate'
for name in adapter.BASELINE:
    (CANDIDATE / name).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(CONTROL_SOURCE / name, CANDIDATE / name)
changed = sorted(str(p.relative_to(CANDIDATE)) for p in adapter.apply(CANDIDATE))
check(changed == sorted(adapter.BASELINE), 'the adapter changes only its files')
if FINAL_PREPARATION:
    for name in adapter.BASELINE:
        check((CANDIDATE / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)

# --- Static: the exact scope ---
def text(tree, name):
    return (tree / name).read_text(encoding='utf-8-sig')


manager_k, manager_c = text(CANDIDATE, VULKAN + 'PipelineCacheManager.cs'), text(CONTROL_SOURCE, VULKAN + 'PipelineCacheManager.cs')
check(manager_k.replace(adapter.FIELDS_NEW, adapter.FIELDS_OLD).replace(adapter.LOAD_NEW, adapter.LOAD_OLD)
      .replace(adapter.END_NEW, adapter.END_OLD).replace(adapter.WORKERS_NEW, adapter.WORKERS_OLD)
      .replace(adapter.CONTENT_NEW, adapter.CONTENT_OLD) == manager_c,
      'PipelineCacheManager differs only by the background load')
check(manager_k.count('CreateCache(snapshot, "main", out accepted)') == 1 and 'CreateCache(mainSnapshot' not in manager_k,
      'the snapshot is created only by the loader')
load = manager_k[manager_k.index('private unsafe void LoadMainSnapshot('):]
load = load[:load.index('\n        }\n') + 10]
check(load.index('_mainCheckpointInProgress = true;') < load.index('_mainCacheLock.Enter();') < load.index('MergeInto(_mainState.Cache, source)')
      < load.index('_mainState.Frozen = failed;') < load.index('MergeSideCache();') < load.index('_mainCacheLock.Exit();')
      < load.index('_mainCheckpointInProgress = false;'), 'merged under the main lock with the checkpoint protocol')
check('if (!_disposed)' in load and load.index('if (!_disposed)') < load.index('MergeInto(') and
      load.index('MergeSideCache();') > load.index('if (!_disposed)'), 'nothing is merged into a disposed manager')
check(load.rindex('_mainLoaded.Set();') < load.rindex('release?.Invoke();'), 'the deferred release runs after the load is marked done')
state_k, state_c = text(CANDIDATE, VULKAN + 'PipelineState.cs'), text(CONTROL_SOURCE, VULKAN + 'PipelineState.cs')
check(state_k.replace(adapter.GRAPHICS_NEW, adapter.GRAPHICS_OLD).replace(adapter.COMPUTE_NEW, adapter.COMPUTE_OLD) == state_c and
      state_k.count('WaitForMainLoadOnWorker();') == 2, 'PipelineState: only the two worker lookups wait')
renderer_k, renderer_c = text(CANDIDATE, VULKAN + 'VulkanRenderer.cs'), text(CONTROL_SOURCE, VULKAN + 'VulkanRenderer.cs')
check(renderer_k.replace(adapter.RELEASE_NEW, adapter.RELEASE_OLD) == renderer_c and
      renderer_k.count('Api.DestroyDevice(_device, null);') == 1, 'VulkanRenderer: the device release goes through DeferDeviceRelease')

# --- Executed: control and candidate fixtures ---
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1')
reports = {}
for variant in ('control', 'candidate'):
    tree = CONTROL_SOURCE if variant == 'control' else CANDIDATE
    fixture = WORK / ('fixture-' + variant)
    fixture.mkdir()
    shutil.copyfile(tree / (VULKAN + 'PipelineCacheManager.cs'), fixture / 'PipelineCacheManager.cs')
    shutil.copyfile(FINAL_SOURCE / (VULKAN + 'VulkanException.cs'), fixture / 'VulkanException.cs')
    shutil.copyfile(HARNESS / 'Double.cs', fixture / 'Double.cs')
    shutil.copyfile(HARNESS / 'Program.cs', fixture / 'Program.cs')
    constants = '<DefineConstants>$(DefineConstants);CANDIDATE</DefineConstants>' if variant == 'candidate' else ''
    (fixture / 'Fixture.csproj').write_text(
        '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
        '<Nullable>disable</Nullable><AllowUnsafeBlocks>true</AllowUnsafeBlocks><NuGetAudit>false</NuGetAudit>' + constants +
        '<NoWarn>CS0649;CS0414;CS0169;CS8321;CS0162;CS1998;CS8632;CS0219</NoWarn></PropertyGroup></Project>\n')
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

SNAPSHOT = 10 * 1024 * 1024
c, k = reports['control'], reports['candidate']
cs, ks = c['startup'], k['startup']
check(cs['ctorMs'] >= 1400 and cs['mainAtStart'] >= SNAPSHOT, 'control (Core 693): the constructor waits for the snapshot: %.0f ms' % cs['ctorMs'])
check(ks['ctorMs'] < 500 and ks['pendingAtStart'] and ks['mainAtStart'] < 1024 * 1024,
      'candidate: the constructor returns at once with main empty: %.0f ms' % ks['ctorMs'])
check(ks['snapshotThread'] == 'RewindBox.PipelineCacheLoad' and ks['mergeThread'] == 'RewindBox.PipelineCacheLoad' and
      ks['mergeText'] == 'merge into main 1 lockHeld=True', 'candidate: created and merged on the loader thread, under the main lock')
WORKER = 1024 * 1024
check(cs['mainAtStart'] >= SNAPSHOT + 2 * WORKER - 64, 'control: the worker snapshots joined main at startup (adapt_pipeline_cache_room)')
check(ks['workersAtStart'] <= 64, 'candidate: the workers start empty')
check(ks['loaded'] and ks['mainAfterLoad'] >= SNAPSHOT + 2 * WORKER - 64 and ks['loaderMerges'] == 3,
      'candidate: main holds the snapshot and both worker snapshots once loaded, merged on the loader thread')
check(ks['workerFilesKeptBeforeMainWrite'] and ks['mainFileUnchangedBeforeSave'],
      'candidate: no worker overwrites its file before main is written with its content')
check(ks['mainFileAfterSave'] >= SNAPSHOT + 2 * WORKER, 'candidate: main is then written with the snapshot and both worker snapshots (%d)' % ks['mainFileAfterSave'])
check(ks['fileUnchangedDuringLoad'], 'candidate: no checkpoint or teardown save replaces the file while it loads')
check(ks['workerSawLoaded'] and ks['workerWaitMs'] >= 500, 'candidate: a worker waits for the load: %.0f ms' % ks['workerWaitMs'])
check(ks['fileAfter'] >= SNAPSHOT + 9 * 1024 * 1024 and cs['fileAfter'] >= SNAPSHOT + 9 * 1024 * 1024,
      'the next write holds the snapshot and the session content (control %d, candidate %d)' % (cs['fileAfter'], ks['fileAfter']))
check(any('loaded in the background' in line for line in ks['lines']), 'candidate: one line when the load ends')
ke = k['endDuringLoad']
check(ke['deferred'] and ke['releasedInTime'] and ke['releaseThread'] == 'RewindBox.PipelineCacheLoad' and ke['teardownMs'] < 500,
      'candidate: a session ending during the load does not wait; the loader thread releases the device: %s' % json.dumps(ke))
check(ke['mergesAfterDispose'] == 0 and ke['stagingDestroyed'] and ke['fileUnchanged'],
      'candidate: nothing merged into the disposed manager, the loader cache destroyed, the file kept')
check(not k['noSnapshot']['pending'] and not k['noSnapshot']['deferred'] and k['noSnapshot']['ctorMs'] < 500, 'candidate: no snapshot, nothing pending')
check(k['rejected']['loaded'] and not k['rejected']['mainMerged'] and k['rejected']['fileAfter'] == c['rejected']['fileAfter'] and
      k['rejected']['fileAfter'] < SNAPSHOT, 'a rejected snapshot is written over as before')

kt = k['loadEndsDuringTeardown']
check(kt['loaded'] and kt['moved'] and kt['fileAfter'] >= SNAPSHOT + 512 * 1024,
      'candidate: a load merged after a teardown save moves the content generation; the second save writes it all: %s' % json.dumps(kt))
kf = k['failedLoad']
check(kf['loaded'] and kf['fileKept'] and kf['workerFilesKept'] and kf['lines'] >= 1,
      'candidate: a failed load keeps main Frozen: the main and worker files are kept: %s' % json.dumps(kf))

inputs = ['build-utils/melonx/adapt_pipeline_cache_background.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_pipeline_cache_background_test.py', 'test/melonx_pipeline_cache_background/Program.cs',
          'test/melonx_pipeline_cache_background/Double.cs', 'test/melonx_adapter_control.py']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core693Preparation',
               postimages={p: sha(FINAL_SOURCE / p) for p in adapter.BASELINE} if FINAL_PREPARATION else {},
               reports=reports, sdk=sdk, physicalDeviceTested=False, productionVulkanSourceExecuted=True,
               sourceBaseline=adapter.BASELINE, inputs={p: sha(ROOT / p) for p in inputs})
out = ROOT / 'dist/melonx/pipeline-cache-background-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
