#!/usr/bin/env python3
"""adapt_pipeline_snapshot_retire on the final preparation, against the Core 711 file as control.

Usage: melonx_pipeline_snapshot_retire_test.py <control> --candidate-source <final preparation containing the adapter>

Executed for control and candidate on the variant's real PipelineCacheManager.cs with a Vulkan double that holds cache
CONTENT (test/melonx_pipeline_snapshot_retire/Double.cs: entries keyed by id, the VkPipelineCacheHeaderVersionOne header,
MoltenVK v1.4.2's readData rules: a foreign header is ignored with success, a record cut short refuses the whole data).
Every launch is a new manager over the same isolated directory (never a player's cache); content is checked entry by
entry, in memory after the background load and in the files after the close. Scenarios: four launches in a row (the
steady state: what is mapped, hydrated, merged and written); a kill after worker checkpoints; main not written at the
close (write failure, over budget); a close during the background load; a worker file cut short; the main file cut
short; two driver versions alternating; another cache UUID under the same file name (iOS or MoltenVK revision) with a
pause and a kill; a launch after an incident between main's write and the workers' removal; a kill while main was being
written (a partial .tmp); main's snapshot leaving no room for the worker snapshots. Writes
dist/melonx/pipeline-snapshot-retire-checks.json.
"""
from pathlib import Path
import hashlib, json, os, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
FINAL_SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, files_edited_later  # noqa: E402
_HOLD = []
CONTROL_SOURCE, FINAL_PREPARATION = control_source(FINAL_SOURCE, 'adapt_pipeline_snapshot_retire', _HOLD)
import adapt_pipeline_snapshot_retire as adapter  # noqa: E402

DOTNET = os.environ.get('DOTNET', 'dotnet')
VULKAN = 'src/Ryujinx.Graphics.Vulkan/'
MANAGER = VULKAN + 'PipelineCacheManager.cs'
HARNESS = ROOT / 'test/melonx_pipeline_snapshot_retire'
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


for name, expected in adapter.BASELINE.items():
    check(sha(CONTROL_SOURCE / name) == expected, 'control is the Core 711 preparation: ' + name)

temporary = tempfile.TemporaryDirectory(prefix='melonx-pipeline-snapshot-retire-')
WORK = Path(temporary.name).resolve()
CANDIDATE = WORK / 'candidate'
for name in adapter.BASELINE:
    (CANDIDATE / name).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(CONTROL_SOURCE / name, CANDIDATE / name)
changed = sorted(str(p.relative_to(CANDIDATE)) for p in adapter.apply(CANDIDATE))
check(changed == sorted(adapter.BASELINE), 'the adapter changes only its file')
if FINAL_PREPARATION:
    later = files_edited_later('adapt_pipeline_snapshot_retire')
    for name in adapter.BASELINE:
        if name not in later:
            check((CANDIDATE / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)


# --- Static: the exact scope ---
def text(tree, name):
    return (tree / name).read_text(encoding='utf-8-sig')


manager_k, manager_c = text(CANDIDATE, MANAGER), text(CONTROL_SOURCE, MANAGER)
pairs = [(getattr(adapter, n + '_NEW'), getattr(adapter, n + '_OLD')) for n in
         ('FIELDS', 'CTOR', 'RECREATED', 'PENDING', 'ARRAYS', 'REFUSED', 'JOINED', 'PRESERVE', 'SAVED', 'CLOSE',
          'HEADER_FIELD', 'HEADER_SET', 'IGNORED', 'LOADED_LINE')] + [(adapter.RETIRE_NEW, adapter.RETIRE_ANCHOR)]
reverted = manager_k
for new, old in pairs:
    check(reverted.count(new) == 1, 'one replacement: ' + old[:60])
    reverted = reverted.replace(new, old)
check(reverted == manager_c, 'PipelineCacheManager differs only by the adapter')
close = manager_k[manager_k.index('        public void MergeAndSave()'):]
close = close[:close.index('\n        }\n') + 10]
check(close.index('MergeInto(_mainState.Cache, workerCaches') < close.index('state.FileOutsideMain = false;')
      < close.index('Maintain(_mainState, force: true, allowRecycle: false);') < close.index('mainFileHoldsWorkers = !_mainState.Frozen')
      < close.index('RetireWorkerFile(state);'),
      'the close: merge, then main written, then the workers decided from main\'s saved generation')
check('Interlocked.Read(ref _mainState.Generation) == Interlocked.Read(ref _mainState.SavedGeneration)' in close and
      '!_mainState.Frozen' in close and 'Maintain(state, force: true, allowRecycle: false);' in close,
      'a worker is removed only once main\'s file holds main\'s content; every other case writes the workers as before')
check(manager_k.count('RetireWorkerFile(') == 2 and manager_k.count('File.Delete(') == manager_c.count('File.Delete(') + 1,
      'one new removal, called only from the close')
check(manager_k.count('_workerSnapshotsHeldUntil') == manager_c.count('_workerSnapshotsHeldUntil') and
      'Interlocked.Read(ref _mainState.SavedGeneration) < Interlocked.Read(ref _workerSnapshotsHeldUntil)' in manager_k,
      'the workers\' hold (no worker file replaced before main holds it) is unchanged')
load = manager_k[manager_k.index('private unsafe void LoadMainSnapshot('):]
load = load[:load.index('\n        }\n') + 10]
check(load.index('bool foreign = !IsDeviceCacheHeader(snapshot);') < load.index('staging = CreateCache(snapshot, "main", out accepted);')
      < load.index('if (accepted && foreign && staging.Handle != 0 && IsEmptyCache(staging))'),
      'the size query runs only for a foreign header, after the driver created the cache')
check(manager_k.count('IsEmptyCache(') == 2 and manager_k.count('IsDeviceCacheHeader(') == 2, 'the header check is used only by the load')

# --- Executed: control and candidate fixtures ---
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1')
reports = {}
for variant in ('control', 'candidate'):
    tree = CONTROL_SOURCE if variant == 'control' else CANDIDATE
    fixture = WORK / ('fixture-' + variant)
    fixture.mkdir()
    shutil.copyfile(tree / MANAGER, fixture / 'PipelineCacheManager.cs')
    shutil.copyfile(FINAL_SOURCE / (VULKAN + 'VulkanException.cs'), fixture / 'VulkanException.cs')
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
    run = subprocess.run([DOTNET, str(fixture / 'bin/Release/net10.0/Fixture.dll'), variant],
                         capture_output=True, text=True, timeout=900, env=environment, cwd=fixture)
    if run.returncode:
        print(run.stdout[-4000:], run.stderr[-4000:], flush=True)
    check(run.returncode == 0, variant + ' fixture runs')
    reports[variant] = json.loads(run.stdout.strip().splitlines()[-1])

c, k = reports['control'], reports['candidate']

# S1: the steady state.
measures = []
for index, (cl, kl) in enumerate(zip(c['steady']['launches'], k['steady']['launches'])):
    for name, launch in (('control', cl), ('candidate', kl)):
        check(launch['loaded'] and launch['missingAfterLoad'] == 0 and launch['missingOnDisk'] == 0,
              '%s launch %d: every pipeline compiled so far is in memory after the load and on disk after the close' % (name, index + 1))
        check(launch['pauseKeptWorkerFiles'], '%s launch %d: a pause checkpoint leaves the worker files as they are' % (name, index + 1))
    cd, kd = cl['load'], kl['load']
    check(kl['close']['writtenWorkers'] == 0 and kl['close']['workerFilesPresent'] == 0,
          'candidate launch %d: the close writes no worker file and leaves none (main\'s file holds them)' % (index + 1))
    check(cl['close']['writtenWorkers'] > 0 and cl['close']['workerFilesPresent'] == 2,
          'control launch %d: the close writes the worker files again' % (index + 1))
    check(kl['close']['writtenMain'] == cl['close']['writtenMain'], 'launch %d: main written with the same content' % (index + 1))
    if index:
        duplicates = cd['mergedEntries'] - cd['mergeAddedEntries']
        check(cd['workerFileBytes'] > 0 and duplicates > 0 and duplicates == cd['hydratedEntries'] - kd['hydratedEntries'],
              'control launch %d: its worker snapshots are mapped, hydrated and merged for nothing (%d entries main held)' % (index + 1, duplicates))
        check(kd['workerFileBytes'] == 0 and kd['mergedEntries'] == kd['mergeAddedEntries'] and kd['mainEntries'] == cd['mainEntries'],
              'candidate launch %d: only main\'s snapshot is read; main holds the same entries' % (index + 1))
    measures.append(dict(launch=index + 1,
                         control=dict(mappedMain=cd['mainFileBytes'], mappedWorkers=cd['workerFileBytes'], hydrated=cd['hydratedBytes'],
                                      duplicateEntries=cd['mergedEntries'] - cd['mergeAddedEntries'], loadMs=cd['loadMs'],
                                      closeWrittenMain=cl['close']['writtenMain'], closeWrittenWorkers=cl['close']['writtenWorkers'],
                                      closeMs=cl['close']['closeMs']),
                         candidate=dict(mappedMain=kd['mainFileBytes'], mappedWorkers=kd['workerFileBytes'], hydrated=kd['hydratedBytes'],
                                        duplicateEntries=kd['mergedEntries'] - kd['mergeAddedEntries'], loadMs=kd['loadMs'],
                                        closeWrittenMain=kl['close']['writtenMain'], closeWrittenWorkers=kl['close']['writtenWorkers'],
                                        closeMs=kl['close']['closeMs'])))
check(c['steady']['final']['missingAfterLoad'] == 0 and k['steady']['final']['missingAfterLoad'] == 0, 'a fifth launch has everything in both')

# S2: a kill after worker checkpoints.
for name, r in (('control', c['crash']), ('candidate', k['crash'])):
    check(r['checkpointed'] == 128 and r['onDiskAfterKill'] == 128 and r['missingAfterRelaunch'] == 0 and r['missingThirdLaunch'] == 0,
          name + ': the worker checkpoints survive a kill and are loaded at the next two launches')
check(k['crash']['close']['workerFilesPresent'] == 0 and k['crash']['thirdLoad']['workerFileBytes'] == 0,
      'candidate: once main\'s file holds them, the worker files are removed and the next launch reads main only')

# S3/S4: main not written at the close.
for mode in ('writeFailure', 'overBudget'):
    for name, r in (('control', c[mode]), ('candidate', k[mode])):
        check(r['mainUnchanged'] and r['missingEarlier'] == 0 and r['missingEarlierThirdLaunch'] == 0 and r['sessionMainKept'] == 0,
              '%s %s: main\'s previous file stands; nothing written before is lost; the session\'s main pipelines are not on disk' % (name, mode))
    check(k[mode]['close']['workerFilesPresent'] == 2 and k[mode]['sessionWorkerKept'] == k[mode]['sessionWorkerEntries'] == 80 and
          k[mode]['sessionWorkerThirdLaunch'] == 80,
          'candidate %s: nothing removed; the session\'s worker pipelines are written to the worker files and loaded next' % mode)

# S5: a close during the background load.
for name, r in (('control', c['closeDuringLoad']), ('candidate', k['closeDuringLoad'])):
    check(r['pendingAtClose'] and r['filesUnchanged'] and r['filesUnchangedAfterLoad'] and r['close']['writtenMain'] == 0 and
          r['close']['writtenWorkers'] == 0 and r['missingNextLaunch'] == 0 and r['missingLaunchAfter'] == 0,
          name + ': a close during the load changes no file; the next launches have everything')
check(k['closeDuringLoad']['nextClose']['workerFilesPresent'] == 0, 'candidate: the worker files go at the next complete close')

# S6: a worker file cut short.
check(k['cutWorker']['refusedPerLaunch'] == [1, 0, 0] and k['cutWorker']['workerFilesAfterEachClose'] == [0, 0, 0],
      'candidate: the refused file is removed at the first close; it is not read again')
check(c['cutWorker']['refusedPerLaunch'] == [1, 1, 1], 'control: the refused file is read and refused at every launch')
for name, r in (('control', c['cutWorker']), ('candidate', k['cutWorker'])):
    check(r['missingLastLoop'] == 0 and r['missingAfter'] == 0, name + ': everything outside the cut file is kept')

# S7: the main file cut short (what the worker copies gave back).
for name, r in (('control', c['cutMain']), ('candidate', k['cutMain'])):
    check(r['refused'] == 1 and r['mainEntriesBack'] == 0 and r['sessionAfterKept'] == r['sessionAfter'],
          name + ': main refused; the next session is kept')
check(c['cutMain']['workerEntriesBack'] == c['cutMain']['workerEntries'] and k['cutMain']['workerEntriesBack'] == 0,
      'cut main file: the control gets the last session\'s worker pipelines back from their copies, the candidate does not')

# S8: two driver versions alternating.
for name, r in (('control', c['alternating']), ('candidate', k['alternating'])):
    check(r['missingAOnReturn'] == 0 and r['missingBOnReturn'] == 0 and r['bHydratedFromA'] == 0 and r['filesA'][0] > 0 and r['filesB'][0] > 0,
          name + ': each version keeps its own files; each comes back whole')
check(k['alternating']['filesA'][1:] == [0, 0] and k['alternating']['filesB'][1:] == [0, 0], 'candidate: no worker copy for either version')

# S9: another cache UUID under the same file name.
ki, ci = k['identity'], c['identity']
check(ki['load']['ignored'] == 1 and ki['load']['mainEntries'] == 0 and ci['load']['ignored'] >= 1 and ci['load']['mainEntries'] == 0,
      'the driver ignores a snapshot of another cache UUID in both')
check(ki['pauseWrote'] and ki['keptAfterKill'] == ki['session'] == 100 and ki['thirdLoad']['ignored'] == 0,
      'candidate: the pause writes the session over the ignored file; after a kill the next launch has it')
check(not ci['pauseWrote'] and ci['keptAfterKill'] == 0 and ci['thirdLoad']['ignored'] >= 1,
      'control: no pause checkpoint after an ignored snapshot; a kill loses the session and the file is ignored again')
check(ki['keptAfterClose'] == ki['sessionsTotal'], 'candidate: every pipeline of both sessions is kept')

# S10: a launch after an incident between main's write and the workers' removal.
for name, r in (('control', c['incident']), ('candidate', k['incident'])):
    check(r['missing'] == 0 and r['missingOnDisk'] == 0 and r['load']['mergedEntries'] > r['load']['mergeAddedEntries'],
          name + ': worker copies back on disk are merged as duplicates; nothing lost')
check(k['incident']['close']['workerFilesPresent'] == 0, 'candidate: removed again at that close')

# S11: a kill while main was being written.
for name, r in (('control', c['killDuringWrite']), ('candidate', k['killDuringWrite'])):
    check(r['missingAfterRelaunch'] == 0 and not r['tmpAfterSave'] and r['missingOnDisk'] == 0,
          name + ': the previous main file loads; the partial .tmp is replaced at the next write')

# S12: no room in main for the worker snapshots.
for name, r in (('control', c['room']), ('candidate', k['room'])):
    check(r['workersUntouched'] and r['missingNextLaunch'] == 0 and r['missingLaunchAfter'] == 0 and r['load']['mergedEntries'] < r['load']['hydratedEntries'],
          name + ': worker snapshots that do not fit stay as they are and join at the next launch')
check(any('workerKept' in line for line in k['journal']) and any('workerRetired' in line for line in k['journal']) and
      any('mainIgnored' in line for line in k['journal']), 'candidate: removals, kept files and ignored snapshots are in the engine journal')
check(not any('Could not remove' in line for line in k['warnings']), 'candidate: every removal succeeded')

inputs = ['build-utils/melonx/adapt_pipeline_snapshot_retire.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_pipeline_snapshot_retire_test.py', 'test/melonx_pipeline_snapshot_retire/Program.cs',
          'test/melonx_pipeline_snapshot_retire/Double.cs', 'test/melonx_adapter_control.py']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core711Preparation',
               postimages={p: sha(FINAL_SOURCE / p) for p in adapter.BASELINE} if FINAL_PREPARATION else {},
               measures=measures, reports=reports, sdk=sdk, physicalDeviceTested=False, productionVulkanSourceExecuted=True,
               driverModel='MoltenVK v1.4.2 readData rules on a content double; no Metal compilation, no device',
               sourceBaseline=adapter.BASELINE, inputs={p: sha(ROOT / p) for p in inputs})
out = ROOT / 'dist/melonx/pipeline-snapshot-retire-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk, measures=measures)))
