#!/usr/bin/env python3
"""adapt_worker_library_share on the final preparation, against the Core 715 files as control.

Usage: melonx_worker_library_share_test.py <Core 715 prepared tree>
       melonx_worker_library_share_test.py <control> --candidate-source <final preparation containing the adapter>

Executed for control and candidate on the variant's real PipelineCacheManager.cs with the content double of
test/melonx_pipeline_snapshot_retire (an entry stands for a Metal library: MoltenVK v1.4.2 keeps them per VkPipelineCache
and vkMergePipelineCaches copies the missing ones). A worker request is modelled as MeloNX makes it: the main cache is
looked up first (all the libraries the pipeline needs), else the pipeline is created in the worker's own cache, where every
library that cache lacks is compiled (counted). Scenarios (test/melonx_worker_library_share/Program.cs): variants of 12 new
programs alternating between two workers, then the close and a second launch; two workers compiling the same new program
at the same moment; the main lock held when a worker would publish; a main snapshot refused once (main Frozen); a worker
cache recycled past its budget; render-thread creations (main or side cache) while both workers publish; another holder
announced while a worker fails to take the lock (the render thread must go to the side cache at once; a variant clearing
every announcement must fail); main's estimate near its budget (refused, then credited). Isolated
directories, never a player's cache. Static: the publication runs on the worker thread after its own compilation, under the
main lock with the checkpoint protocol, and keeps the merge bookkeeping of PreserveBeforeRecycle. Writes
dist/melonx/worker-library-share-checks.json.
"""
from pathlib import Path
import hashlib, json, os, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
FINAL_SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, files_edited_later, use_authenticated_libhac_feed  # noqa: E402
_HOLD = []
CONTROL_SOURCE, FINAL_PREPARATION = control_source(FINAL_SOURCE, 'adapt_worker_library_share', _HOLD)
import adapt_worker_library_share as adapter  # noqa: E402

DOTNET = os.environ.get('DOTNET', 'dotnet')
VULKAN = 'src/Ryujinx.Graphics.Vulkan/'
MANAGER, STATE = adapter.MANAGER, adapter.STATE
HARNESS = ROOT / 'test/melonx_worker_library_share'
TAG = 'RewindBox (adapt_worker_library_share)'
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def text(tree, name):
    return (tree / name).read_text(encoding='utf-8-sig')


for name, expected in adapter.BASELINE.items():
    check(sha(CONTROL_SOURCE / name) == expected, 'control is the Core 715 preparation: ' + name)

temporary = tempfile.TemporaryDirectory(prefix='melonx-worker-library-share-')
WORK = Path(temporary.name).resolve()
CANDIDATE = WORK / 'candidate'
shutil.copytree(CONTROL_SOURCE, CANDIDATE, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
use_authenticated_libhac_feed(CANDIDATE, ROOT)
changed = sorted(str(p.relative_to(CANDIDATE)) for p in adapter.apply(CANDIDATE))
check(changed == sorted(adapter.BASELINE), 'the adapter changes only its two files')
duplicate = WORK / 'duplicate'
for name in adapter.BASELINE:
    (duplicate / name).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(CANDIDATE / name, duplicate / name)
try:
    adapter.apply(duplicate)
    refused = False
except AssertionError:
    refused = True
check(refused, 'fail closed: an adapted tree is refused')
if FINAL_PREPARATION:
    later = files_edited_later('adapt_worker_library_share')
    for name in adapter.BASELINE:
        if name not in later:
            check((CANDIDATE / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)

# --- Static: the exact scope ---
manager_k, manager_c = text(CANDIDATE, MANAGER), text(CONTROL_SOURCE, MANAGER)
state_k, state_c = text(CANDIDATE, STATE), text(CONTROL_SOURCE, STATE)
for tree_text, control_text, pairs, name in (
        (manager_k, manager_c, [(adapter.NOTIFY_NEW, adapter.NOTIFY_OLD), (adapter.CLOSE_NEW, adapter.CLOSE_OLD)] +
         [(new, old) for old, new in reversed(adapter.PROTOCOL)], MANAGER),
        (state_k, state_c, [(adapter.COMPUTE_NEW, adapter.COMPUTE_OLD), (adapter.GRAPHICS_NEW, adapter.GRAPHICS_OLD)], STATE)):
    reverted = tree_text
    for new, old in pairs:
        check(reverted.count(new) == 1, 'one replacement: ' + old[:60])
        reverted = reverted.replace(new, old)
    check(reverted == control_text, name + ' differs only by the adapter')
    check(tree_text.count(TAG) >= 2, 'commented: ' + name)
share = manager_k[manager_k.index('        private void ShareWithMain(CacheState state)'):]
share = share[:share.index('\n        }\n') + 10]
check(share.index('WorkerCompiledOwn = false;') < share.index('if (!compiled ||') < share.index('Interlocked.Increment(ref _mainCheckpointHolders);') <
      share.index('if (!_mainCacheLock.TryEnter())') < share.index('Interlocked.Decrement(ref _mainCheckpointHolders);') <
      share.index('MergeInto(main.Cache, source)') < share.index('MergeSideCache();') < share.index('_mainCacheLock.Exit();') <
      share.rindex('Interlocked.Decrement(ref _mainCheckpointHolders);'),
      'published after an own compilation only, never waiting for the main lock, announced as a holder (render thread to the side cache)')
check('_mainCheckpointInProgress' not in manager_k and manager_k.count('Interlocked.Increment(ref _mainCheckpointHolders);') == 4 and
      manager_k.count('Interlocked.Decrement(ref _mainCheckpointHolders);') == 6 and
      'public bool MainCheckpointInProgress => Volatile.Read(ref _mainCheckpointHolders) != 0;' in manager_k,
      'every holder counts: four announcements (load, play-time and pause checkpoints, share), six withdrawals (one per path)')
check('main.Frozen' in share and 'PipelineVariantJournal.LowDevicePercent' in share and
      share.count('main.EstimatedBytes + ') == 2 and share.index('main.EstimatedBytes + growth > main.Budget') > share.index('if (!_mainCacheLock.TryEnter())') and
      'main.OnMerged(growth);' in share and 'state.SharedPipelineCount = state.PipelineCount;' in share and
      'state.MergedGeneration = Interlocked.Read(ref state.Generation);' in share and 'state.FileOutsideMain = false;' in share,
      'budget checked before and again under the lock, main\'s estimate credited; not into a Frozen main or under low memory; the merge bookkeeping of PreserveBeforeRecycle')
check('SharedPipelineCount = 0;' in manager_k[manager_k.index('public void OnRecreated(PipelineCache cache)'):][:400] and
      'if (added > 0 && bytes > _measuredBytes && _mergedCredit == 0)' in manager_k and '_mergedCredit = 0;' in manager_k,
      'a recycled worker cache starts its share accounting again')
notify = manager_k[manager_k.index('        public void NotifyWorkerPipelineCreated(int workerIndex)'):]
notify = notify[:notify.index('\n        }\n') + 10]
check(notify.index('Maintain(state, force: false);') < notify.index('ShareWithMain(state);') < notify.index('CheckpointMainIfDue();'),
      'on the worker thread that owns the cache, after its upkeep (a recycle first preserves into main), before the checkpoint')
for body in (state_k[state_k.index(adapter.COMPUTE_NEW):][:len(adapter.COMPUTE_NEW)], state_k[state_k.index(adapter.GRAPHICS_NEW):][:len(adapter.GRAPHICS_NEW)]):
    check('PipelineCacheManager.WorkerCompiledOwn = result == Result.Success;' in body, 'the flag marks a worker creation compiled in its own cache')
scheduler = text(CONTROL_SOURCE, VULKAN + 'BackgroundCompilationScheduler.cs')
check('workerIndex => _pipelineCacheManager.NotifyWorkerPipelineCreated(workerIndex)' in scheduler,
      'NotifyWorkerPipelineCreated runs after the work item, on the worker thread that made it')

# --- Production assembly builds ---
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1')
result = subprocess.run([DOTNET, 'build', str(CANDIDATE / 'src/Ryujinx.Graphics.Vulkan/Ryujinx.Graphics.Vulkan.csproj'), '-c', 'Release',
                         '-nologo', '-m:1', '-p:NuGetAudit=false'], capture_output=True, text=True, timeout=2400, env=environment, cwd=CANDIDATE)
if result.returncode:
    print(result.stdout[-6000:], result.stderr[-2000:], flush=True)
check(result.returncode == 0, 'production Ryujinx.Graphics.Vulkan builds with the adapter')

# --- Executed: control and candidate fixtures ---
reports = {}
BUSY_WITHDRAW = '''                Interlocked.Decrement(ref _mainCheckpointHolders);
                Interlocked.Increment(ref _sharesBusy);'''
check(manager_k.count(BUSY_WITHDRAW) == 1, 'the busy path withdraws its own announcement (replaceable for the sensitivity variant)')
for variant in ('control', 'candidate', 'clearsOthers'):
    tree = CONTROL_SOURCE if variant == 'control' else CANDIDATE
    fixture = WORK / ('fixture-' + variant)
    fixture.mkdir()
    shutil.copyfile(tree / MANAGER, fixture / 'PipelineCacheManager.cs')
    if variant == 'clearsOthers':
        (fixture / 'PipelineCacheManager.cs').write_text(manager_k.replace(BUSY_WITHDRAW, BUSY_WITHDRAW.replace(
            'Interlocked.Decrement(ref _mainCheckpointHolders);', 'Volatile.Write(ref _mainCheckpointHolders, 0);')))
    shutil.copyfile(tree / (VULKAN + 'VulkanException.cs'), fixture / 'VulkanException.cs')
    shutil.copyfile(HARNESS / 'Double.cs', fixture / 'Double.cs')
    shutil.copyfile(HARNESS / 'Program.cs', fixture / 'Program.cs')
    (fixture / 'Fixture.csproj').write_text(
        '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
        '<Nullable>disable</Nullable><AllowUnsafeBlocks>true</AllowUnsafeBlocks><NuGetAudit>false</NuGetAudit>'
        '<NoWarn>CS0649;CS0414;CS0169;CS8321;CS0162;CS1998;CS8632;CS0219</NoWarn></PropertyGroup></Project>\n')
    build = subprocess.run([DOTNET, 'build', str(fixture / 'Fixture.csproj'), '-c', 'Release', '-nologo', '-p:NuGetAudit=false'],
                           capture_output=True, text=True, timeout=900, env=environment, cwd=fixture)
    if build.returncode:
        print('\n'.join(line for line in build.stdout.splitlines() if ': error ' in line)[:6000], flush=True)
    check(build.returncode == 0, variant + ' fixture builds with the real PipelineCacheManager.cs')
    run = subprocess.run([DOTNET, str(fixture / 'bin/Release/net10.0/Fixture.dll'), 'candidate' if variant == 'clearsOthers' else variant],
                         capture_output=True, text=True, timeout=900, env=environment, cwd=fixture)
    if run.returncode:
        print(run.stdout[-4000:], run.stderr[-4000:], flush=True)
    check(run.returncode == 0, variant + ' fixture runs')
    reports[variant] = json.loads(run.stdout.strip().splitlines()[-1])
    print(variant, json.dumps({k: v for k, v in reports[variant].items() if k not in ('warnings', 'shareLines')}), flush=True)

c, k, s = reports['control'], reports['candidate'], reports['clearsOthers']
for name, r in (('control', c), ('candidate', k)):
    o = r['overlap']
    check(o['announcementKept'] and o['renderReturnedWhileHeld'] and o['renderToSideCache'] and o['renderRouteMs'] < 250 and
          o['announcementWithdrawnAfter'], name + ': with another holder announced, a render-thread creation goes to the side cache at once: ' + str(o))
check(not s['overlap']['announcementKept'] and not s['overlap']['renderReturnedWhileHeld'],
      'sensitivity: a share that clears every announcement leaves the render thread waiting for the lock: ' + str(s['overlap']))
e = k['estimate']
check(e['perPipelineAfter'] == e['perPipelineBefore'] and e['creditedEstimate'] >= (74 << 20) and e['laterEstimate'] >= e['actual'] + 16 * e['perPipelineAfter'],
      'a merge\'s credit does not lower the bytes per pipeline; after the measure the estimate never falls below the measured size: ' + str(e))
b = k['budget']
check(b['refusedKeptOut'] and b['overBudget'] == 1 and b['sharedAfterRoom'] and b['credited'] > 0,
      'over main\'s estimated budget: refused and counted; with room: shared and main\'s estimate credited: ' + str(b))
ca, ka = c['alternating'], k['alternating']
check(ca['librariesCompiled'] > ka['librariesCompiled'] >= ka['distinctLibraries'] == 14 and ca['mainHits'] == 0 and ka['mainHits'] > 0,
      'alternating variants: the candidate compiles fewer libraries (each published one is found by the other worker)')
check(ka['librariesCompiled'] - ka['distinctLibraries'] <= 1,
      'what is left is a pipeline needing a new library: created in the worker cache, its other libraries compiled there too')
check(ka['shares'] > 0 and ka['shareMs'] >= 0 and ka['entriesIteratedByMerges'] > 0 and ka['mainEntriesBeforeClose'] == 14 and ca['mainEntriesBeforeClose'] == 0,
      'the candidate publishes during play; the control only at the close')
check(ca['onDiskAll'] and ka['onDiskAll'] and ca['onDisk'] == ka['onDisk'] == 14 and ca['nextLaunchCompiled'] == ka['nextLaunchCompiled'] == 0,
      'the close writes the same content; the next launch compiles nothing in both')
for name, r in (('control', c), ('candidate', k)):
    check(r['concurrent']['simultaneousCompiled'] == 4, name + ': two workers compiling the same new program at the same moment both compile it')
check(c['concurrent']['laterMainHits'] == 0 and k['concurrent']['laterMainHits'] == 2 and k['concurrent']['laterCompiled'] == 0,
      'only later requests find what was published')
check(not k['busy']['inMainWhileBusy'] and k['busy']['busyCount'] == 1 and k['busy']['bothInMainAfter'] and k['busy']['compiled'] == 2,
      'main lock held: not published then (counted), published with the next own compilation; nothing waited')
for name, r in (('control', c), ('candidate', k)):
    check(r['frozen']['addedToMainDuringPlay'] == 0 and r['frozen']['mainFileKept'], name + ': a Frozen main receives nothing during play; its file is kept')
    check(r['recycle']['compiled'] == 4300 and r['recycle']['allOnDisk'], name + ': a recycled worker cache loses nothing')
    # The scenario builds the overlap itself (the render thread starts after both workers' first publication; the workers
    # publish until it is done), so the counts hold whatever the threads' speeds.
    check(r['threads']['renderCreations'] == 2000 and r['threads']['renderFinished'] and r['threads']['allRenderOnDisk'] and
          r['threads']['allWorkerOnDisk'] and min(r['threads']['workerRequests']) >= 300,
          name + ': render-thread creations during publications are all kept')
check(k['recycle']['allInMainBeforeClose'] and not c['recycle']['allInMainBeforeClose'], 'candidate: published before and after the recycle')
check(any('Worker libraries shared with the main cache (session, at close): 13 merges' in line for line in k['shareLines']),
      'the close logs the session\'s publications')

inputs = ['build-utils/melonx/adapt_worker_library_share.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_worker_library_share_test.py', 'test/melonx_worker_library_share/Program.cs',
          'test/melonx_worker_library_share/Double.cs', 'test/melonx_adapter_control.py']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core715Preparation',
               postimages={p: sha(FINAL_SOURCE / p) for p in adapter.BASELINE} if FINAL_PREPARATION else {},
               comparison=dict(librariesCompiledControl=ca['librariesCompiled'], librariesCompiledCandidate=ka['librariesCompiled'],
                               distinctLibraries=14, mainHitsCandidate=ka['mainHits'], shares=ka['shares'],
                               entriesIteratedByMerges=ka['entriesIteratedByMerges'], simultaneousStillDuplicated=True,
                               sameContentOnDisk=True, renderRoutedToSideCacheDuringOverlap=True, sensitivityVariantFailed=True,
                               budgetRecheckedUnderLock=True, budgetIsEstimate=True),
               reports=reports, sdk=sdk, physicalDeviceTested=False, productionVulkanSourceExecuted=True,
               driverModel='MoltenVK v1.4.2 per-cache library and merge rules on a content double; the real-backend counts are in '
                           'the melonx-library-share run; no device',
               sourceBaseline=adapter.BASELINE, inputs={p: sha(ROOT / p) for p in inputs})
out = ROOT / 'dist/melonx/worker-library-share-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, comparison=receipt['comparison'])))
