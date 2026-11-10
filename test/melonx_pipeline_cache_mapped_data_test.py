#!/usr/bin/env python3
"""adapt_pipeline_cache_mapped_data on the final preparation, against the Core 719 files as control.

Usage: melonx_pipeline_cache_mapped_data_test.py <Core 719 prepared tree>
       melonx_pipeline_cache_mapped_data_test.py <control> --candidate-source <final preparation containing the adapter>

Executed for control, candidate and three sensitivity variants on the variant's real PipelineCacheManager.cs with the
content double of test/melonx_pipeline_cache_mapped_data/Double.cs in reference mode: a cache created with the 'RBX1'
pNext structure keeps pointers into the caller's data, as MoltenVK with the RewindBox patch keeps each library's
compressed MSL (build-utils/melonx/moltenvk/rewindbox-moltenvk.patch); vkMergePipelineCaches carries them to the
destination (MoltenVK v1.4.2 MVKShaderLibraryCache::merge copies each library with MVKShaderLibrary's copy constructor,
which copies the compressor and so its external pointer); each later merge, write and destroy checks the region is still
mapped (msync) and still holds the data it read. Scenarios (Program.cs): a session (main 200 libraries + worker 20, load,
play, pause checkpoint replacing the main file, play, close, next launch); a snapshot refused once; a file of another
driver identity; the close overtaking the background load; the merge into main reporting an error after merging. Sensitivity: releasing the snapshot at the end of the
creation (before the merge), never releasing it, or keeping it after the close destroyed main must each fail.
The RAM measured on the real MoltenVK is the melonx-mapped-cache run (macOS, not an iPhone). Static: main is never a
merge source or recycled and its file is only replaced (written beside it, then moved) or deleted. Isolated
directories, never a player's cache. Writes dist/melonx/pipeline-cache-mapped-data-checks.json.
"""
from pathlib import Path
import hashlib, json, os, re, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
FINAL_SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, files_edited_later, use_authenticated_libhac_feed  # noqa: E402
_HOLD = []
CONTROL_SOURCE, FINAL_PREPARATION = control_source(FINAL_SOURCE, 'adapt_pipeline_cache_mapped_data', _HOLD)
import adapt_pipeline_cache_mapped_data as adapter  # noqa: E402

DOTNET = os.environ.get('DOTNET', 'dotnet')
VULKAN = 'src/Ryujinx.Graphics.Vulkan/'
MANAGER = adapter.MANAGER
HARNESS = ROOT / 'test/melonx_pipeline_cache_mapped_data'
TAG = 'RewindBox (adapt_pipeline_cache_mapped_data)'
PATCH = ROOT / 'build-utils/melonx/moltenvk/rewindbox-moltenvk.patch'
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
    check(sha(CONTROL_SOURCE / name) == expected, 'control is the Core 719 preparation: ' + name)

temporary = tempfile.TemporaryDirectory(prefix='melonx-pipeline-cache-mapped-data-')
WORK = Path(temporary.name).resolve()
CANDIDATE = WORK / 'candidate'
shutil.copytree(CONTROL_SOURCE, CANDIDATE, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
use_authenticated_libhac_feed(CANDIDATE, ROOT)
changed = sorted(str(p.relative_to(CANDIDATE)) for p in adapter.apply(CANDIDATE))
check(changed == sorted(adapter.BASELINE), 'the adapter changes only PipelineCacheManager.cs')
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
    later = files_edited_later('adapt_pipeline_cache_mapped_data')
    for name in adapter.BASELINE:
        if name not in later:
            check((CANDIDATE / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)

# --- Static: the exact scope ---
manager_k, manager_c = text(CANDIDATE, MANAGER), text(CONTROL_SOURCE, MANAGER)
PAIRS = [(adapter.FIELD_OLD, adapter.FIELD_NEW), (adapter.CREATE_OLD, adapter.CREATE_NEW), (adapter.RETRY_OLD, adapter.RETRY_NEW),
         (adapter.DECLARE_OLD, adapter.DECLARE_NEW), (adapter.STAGING_OLD, adapter.STAGING_NEW), (adapter.IGNORED_OLD, adapter.IGNORED_NEW),
         (adapter.INNER_DISPOSE_OLD, adapter.INNER_DISPOSE_NEW), (adapter.OUTER_OLD, adapter.OUTER_NEW), (adapter.DESTROY_OLD, adapter.DESTROY_NEW)]
reverted = manager_k
for old, new in reversed(PAIRS):
    check(reverted.count(new) == 1, 'one replacement: ' + old.strip()[:60])
    reverted = reverted.replace(new, old)
check(reverted == manager_c, MANAGER + ' differs only by the adapter')
check(manager_k.count('adapt_pipeline_cache_mapped_data') >= 8, 'commented')
check(manager_k.count('referenceData: true') == 1 and 'CreateCache(snapshot, "main", out accepted, referenceData: true)' in manager_k and
      'CreateCache(workerSnapshot, $"worker {index}", out bool workerAccepted)' in manager_k,
      'only the main snapshot is referenced; worker snapshots are copied as before (their mappings close at once)')
check(adapter.STYPE == 0x52425831 and 'internal const uint MappedCacheDataSType = 0x52425831;' in manager_k,
      'the structure type is the one the MoltenVK patch reads')
patch = PATCH.read_text()
check('kRewindBoxMappedCacheDataSType = 0x52425831' in patch and
      'RewindBox mapped cache data: compressed MSL referenced in the mapped file, not copied' in patch,
      'the pinned MoltenVK patch reads that structure (otherwise ignored: MoltenVK walks only the pNext types it knows)')
load = manager_k[manager_k.index('        private unsafe void LoadMainSnapshot(MappedSnapshot snapshot)'):]
load = load[:load.index('\n        public PipelineCache MainCache')]
check(load.index('referenced = accepted;') < load.index('referenced = false; // RewindBox') < load.index('if (!referenced)') <
      load.index('MergeInto(_mainState.Cache, source)') < load.index('_mainDataSnapshot = snapshot;'),
      'kept from the creation (an ignored header keeps nothing), never released before the merge, stored at the end')
final = load[load.rindex('            finally\n'):]
check(final.index('lock (_mainCacheLock)') < final.index('if (_disposed)') < final.index('snapshot.Dispose();') < final.index('_mainDataSnapshot = snapshot;')
      and final.index('_mainDataSnapshot = snapshot;') < final.index('_mainLoaded.Set();'),
      'stored or released under the main lock, before the load is reported finished; released if the close destroyed main')
dispose = manager_k[manager_k.index('        private unsafe void DisposeLocked()'):]
dispose = dispose[:dispose.index('\n        }\n') + 10]
check(dispose.index('_api.DestroyPipelineCache(_device, _mainState.Cache, null);') < dispose.index('_mainDataSnapshot?.Dispose();'),
      'released only after main is destroyed')
check(manager_k.count('_mainDataSnapshot') == 4, 'the field is only declared, stored, released and cleared')
# Main's data must stay what MoltenVK read: main is never a merge source nor recycled; its file only replaced or deleted.
merges = [call for call in re.findall(r'\bMergeInto\([^,]*', manager_k) if not call.startswith('MergeInto(PipelineCache ')]
check(manager_k.count('MergePipelineCaches(') == 1 and merges and set(merges) <= {'MergeInto(_mainState.Cache', 'MergeInto(main.Cache'},
      'main is only ever a merge destination (one driver merge call, in MergeInto): ' + str(sorted(set(merges))))
notify = manager_k[manager_k.index('        public void NotifyWorkerPipelineCreated(int workerIndex)'):]
notify = notify[:notify.index('\n        }\n') + 10]
check(re.findall(r'\bRecycle\((\w+)', manager_k) == ['worker', 'state', 'CacheState'] and manager_k.count('Maintain(') == 4 and
      'Maintain(state, force: false);' in notify and 'Maintain(_mainState, force: true, allowRecycle: false);' in manager_k and
      manager_k.count('allowRecycle: false') == 2,
      'main is never recycled: the only recycling Maintain runs on a worker\'s own thread for its cache')
save = manager_k[manager_k.index('        private unsafe void SaveCache(CacheState state, long size, bool final)'):]
save = save[:save.index('\n        }\n') + 10]
check('string temporaryPath = state.Path + ".tmp";' in save and 'File.Move(temporaryPath, state.Path, overwrite: true);' in save and
      'new(temporaryPath, FileMode.Create' in save and 'new(temporaryPath, FileMode.Open' in save and
      not re.search(r'new\(state\.Path|FileStream\(state\.Path|OpenWrite\(state\.Path', manager_k),
      'a cache file is written beside it and moved over it, never rewritten in place (the mapped inode keeps its bytes)')

# --- Production assembly builds ---
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1')
result = subprocess.run([DOTNET, 'build', str(CANDIDATE / 'src/Ryujinx.Graphics.Vulkan/Ryujinx.Graphics.Vulkan.csproj'), '-c', 'Release',
                         '-nologo', '-m:1', '-p:NuGetAudit=false'], capture_output=True, text=True, timeout=2400, env=environment, cwd=CANDIDATE)
if result.returncode:
    print(result.stdout[-6000:], result.stderr[-2000:], flush=True)
check(result.returncode == 0, 'production Ryujinx.Graphics.Vulkan builds with the adapter')

# --- Executed: control, candidate and sensitivity fixtures ---
KEEP_AFTER_CLOSE = '''                        if (_disposed)
                        {
                            snapshot.Dispose();
                        }'''
check(manager_k.count(adapter.INNER_DISPOSE_NEW) == 1 and manager_k.count(adapter.DESTROY_NEW) == 1 and manager_k.count(KEEP_AFTER_CLOSE) == 1,
      'the three parts the sensitivity variants revert are present once')
SENSITIVITY = {
    # Released at the end of the creation, as before (and not again at the end of the load).
    'releasedEarly': manager_k.replace(adapter.INNER_DISPOSE_NEW, adapter.INNER_DISPOSE_OLD.replace(
        'snapshot.Dispose();', 'snapshot.Dispose();\n                    referenced = false;')),
    'neverReleased': manager_k.replace(adapter.DESTROY_NEW, adapter.DESTROY_OLD + '            _ = _mainDataSnapshot;\n'),
    'keptAfterClose': manager_k.replace(KEEP_AFTER_CLOSE, KEEP_AFTER_CLOSE.replace('if (_disposed)', 'if (false)')),
}
reports = {}
for variant in ('control', 'candidate', *SENSITIVITY):
    tree = CONTROL_SOURCE if variant == 'control' else CANDIDATE
    fixture = WORK / ('fixture-' + variant)
    fixture.mkdir()
    shutil.copyfile(tree / MANAGER, fixture / 'PipelineCacheManager.cs')
    if variant in SENSITIVITY:
        (fixture / 'PipelineCacheManager.cs').write_text(SENSITIVITY[variant])
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
    run = subprocess.run([DOTNET, str(fixture / 'bin/Release/net10.0/Fixture.dll'), variant],
                         capture_output=True, text=True, timeout=900, env=environment, cwd=fixture)
    if run.returncode:
        print(run.stdout[-4000:], run.stderr[-4000:], flush=True)
    check(run.returncode == 0, variant + ' fixture runs')
    reports[variant] = json.loads(run.stdout.strip().splitlines()[-1])
    print(variant, json.dumps({k: v for k, v in reports[variant].items() if k != 'warnings'}), flush=True)

c, k = reports['control'], reports['candidate']
cs, ks = c['session'], k['session']
check([a['referenced'] for a in cs['attempts']] == [False, False] and cs['referenceCreations'] == 0 and cs['journalLines'] == 0 and
      not cs['mappedAfterLoad'], 'control: no structure passed, the snapshot copied and released at once: ' + str(cs['attempts']))
check([(a['role'], a['referenced']) for a in ks['attempts']] == [('main', True), ('worker', False)] and ks['referenceCreations'] == 1 and
      ks['mainRegions'] == 1 and ks['journalLines'] == 1,
      'candidate: the main snapshot referenced (carried into main by the merge), the worker snapshot copied; one journal line')
check(ks['mappedAfterLoad'] and ks['mappedAfterCheckpoint'] and ks['mappedBeforeDispose'] and not ks['mappedAfterDispose'] and
      ks['mainDestroyedWithValidRegions'] == 1 and ks['invalidReads'] == 0 and ks['validReads'] >= 4,
      'candidate: mapped through play, the pause checkpoint (file replaced) and the close, released after main is destroyed, '
      'every read valid: ' + json.dumps(ks))
for name, s in (('control', cs), ('candidate', ks)):
    check(s['entriesAfterLoad'] == 220 and s['checkpointWrote'] and s['onDisk'] == 260 and s['allOnDisk'] and s['entriesNextLaunch'] == 260 and
          s['invalidReadsNextLaunch'] == 0 and not s['mappedAfterNextDispose'], name + ': same content loaded, written and read at the next launch')
for name, r in (('control', c), ('candidate', k)):
    check(r['refused']['referenceCreations'] == 0 and not r['refused']['mappedAfterLoad'] and r['refused']['journalLines'] == 0 and
          r['refused']['fileKept'] and r['refused']['invalidReads'] == 0, name + ': a refused snapshot is released at once, its file kept')
    check(not r['foreign']['mappedAfterLoad'] and r['foreign']['journalLines'] == 0 and r['foreign']['rewritten'] and r['foreign']['invalidReads'] == 0,
          name + ': a file of another driver identity is released at once and written again')
    check(r['overtaken']['pendingAtClose'] and not r['overtaken']['mappedAfterLoad'] and r['overtaken']['journalLines'] == 0 and
          r['overtaken']['invalidReads'] == 0 and r['overtaken']['fileKept'], name + ': a close overtaking the load: released when it returns')
m = k['mergeFailed']
check(m['referencedAttempt'] and m['mappedAfterLoad'] and m['mappedBeforeDispose'] and not m['mappedAfterDispose'] and
      m['mainDestroyedWithValidRegions'] == 1 and m['invalidReads'] == 0 and m['validReads'] >= 2 and m['fileKept'] and m['journalLines'] == 1,
      'candidate: a merge reporting an error after it may have referenced the data keeps the mapping until main is destroyed: ' + str(m))
check(c['mergeFailed']['fileKept'] and not c['mergeFailed']['mappedAfterLoad'] and c['mergeFailed']['invalidReads'] == 0,
      'control: the failed merge leaves main Frozen, its file kept, as before')
check(reports['releasedEarly']['mergeFailed']['invalidReads'] > 0, 'sensitivity: released before the merge, the failed merge path reads it too')
check(k['refused']['referencedAttempt'] and k['foreign']['referencedAttempt'] and k['overtaken']['referenceCreations'] == 1,
      'candidate: those creations asked for the reference too')
check(reports['releasedEarly']['session']['invalidReads'] > 0, 'sensitivity: a snapshot released before the merge is read after its release')
check(reports['neverReleased']['session']['mappedAfterDispose'], 'sensitivity: a snapshot never released stays mapped after the close')
check(reports['keptAfterClose']['overtaken']['mappedAfterLoad'], 'sensitivity: a snapshot kept after the close overtook the load stays mapped')

inputs = ['build-utils/melonx/adapt_pipeline_cache_mapped_data.py', 'build-utils/melonx/adapt_session.py',
          'build-utils/melonx/moltenvk/rewindbox-moltenvk.patch',
          'test/melonx_pipeline_cache_mapped_data_test.py', 'test/melonx_pipeline_cache_mapped_data/Program.cs',
          'test/melonx_pipeline_cache_mapped_data/Double.cs', 'test/melonx_adapter_control.py']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core719Preparation',
               postimages={p: sha(FINAL_SOURCE / p) for p in adapter.BASELINE} if FINAL_PREPARATION else {},
               comparison=dict(mainReferenced=True, workerCopied=True, mappedUntilMainDestroyed=True, invalidReadsCandidate=ks['invalidReads'],
                               validReadsCandidate=ks['validReads'], sameContentOnDisk=True, refusedReleasedAtOnce=True,
                               foreignReleasedAtOnce=True, overtakenReleased=True, mergeFailedKeptUntilMainDestroyed=True,
                               sensitivityVariantsFailed=3),
               reports=reports, sdk=sdk, physicalDeviceTested=False, productionVulkanSourceExecuted=True,
               driverModel='MoltenVK with the RewindBox patch referencing the cache data (pointers kept, carried by merges, '
                           'checked with msync and the content); the RAM measure on the real MoltenVK is the melonx-mapped-cache '
                           'run (macOS); no device',
               sourceBaseline=adapter.BASELINE, inputs={p: sha(ROOT / p) for p in inputs})
out = ROOT / 'dist/melonx/pipeline-cache-mapped-data-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, comparison=receipt['comparison'])))
