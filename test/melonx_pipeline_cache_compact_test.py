#!/usr/bin/env python3
"""adapt_pipeline_cache_compact on the final preparation, against the Core 727 preparation as control.

Usage: melonx_pipeline_cache_compact_test.py <Core 727 prepared tree>
       melonx_pipeline_cache_compact_test.py <control> --candidate-source <final preparation containing the adapter>

Static: the control is the Core 727 file; the candidate differs by the adapter's two replacements; the call stands in
LoadMainSnapshot under the main lock, after the staging caches are destroyed and before the lock is released, only for an
accepted, merged snapshot of a manager not disposed; the write is the existing SaveCache (beside the file, then moved).
Executed for control, candidate and two sensitivity variants on the variant's real PipelineCacheManager.cs with the
content double of test/melonx_pipeline_cache_compact/Double.cs in key mode (a cache created from data keeps each whole
entry at a sixteenth of its length, as MoltenVK with the fifth part of build-utils/melonx/moltenvk/rewindbox-moltenvk.patch
keeps a library under its cache key). Scenarios (Program.cs): the decision by itself; a whole file whose session is
killed after the load; the same through play, a pause and the close, with a worker snapshot; a file already holding
keys; a small whole file and the growth rule after it; a write that fails at the load; the close overtaking the load.
Sensitivity: the candidate without the call, and with a decision that always writes, must each fail.
The sizes and the memory on the real MoltenVK are the melonx-cache-keys run (macOS, not an iPhone). Isolated
directories, never a player's cache. Writes dist/melonx/pipeline-cache-compact-checks.json.
"""
from pathlib import Path
import hashlib, json, os, platform, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
FINAL_SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, files_edited_later, use_authenticated_libhac_feed  # noqa: E402
_HOLD = []
CONTROL_SOURCE, FINAL_PREPARATION = control_source(FINAL_SOURCE, 'adapt_pipeline_cache_compact', _HOLD)
import adapt_pipeline_cache_compact as adapter  # noqa: E402

DOTNET = os.environ.get('DOTNET', 'dotnet')
VULKAN = 'src/Ryujinx.Graphics.Vulkan/'
MANAGER = adapter.MANAGER
HARNESS = ROOT / 'test/melonx_pipeline_cache_compact'
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


def member(source, signature):
    start = source.rindex('\n', 0, source.index(signature)) + 1
    depth, index = 0, source.index('{', start)
    for index in range(index, len(source)):
        depth += (source[index] == '{') - (source[index] == '}')
        if depth == 0:
            return source[start:index + 1]
    raise AssertionError(signature)


for name, expected in adapter.BASELINE.items():
    check(sha(CONTROL_SOURCE / name) == expected, 'control is the Core 727 preparation: ' + name)
temporary = tempfile.TemporaryDirectory(prefix='melonx-pipeline-cache-compact-')
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
    later = files_edited_later('adapt_pipeline_cache_compact')
    for name in adapter.BASELINE:
        if name not in later:
            check((CANDIDATE / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)

# --- Static: the exact scope ---
manager_k, manager_c = text(CANDIDATE, MANAGER), text(CONTROL_SOURCE, MANAGER)
reverted = manager_k
for old, new in reversed(adapter.PAIRS):
    check(reverted.count(new) == 1, 'one replacement: ' + old.strip()[:60])
    reverted = reverted.replace(new, old)
check(reverted == manager_c, MANAGER + ' differs only by the adapter')
load = member(manager_k, 'private unsafe void LoadMainSnapshot(MappedSnapshot snapshot)')
check(load.count('CompactMainAfterLoad(length);') == 1 and manager_k.count('CompactMainAfterLoad(') == 2,
      'one call, in the background load')
section = load[load.index('_mainCacheLock.Enter();'):]
section = section[:section.index('_mainCacheLock.Exit();')]
check(section.index('MergeInto(_mainState.Cache, source)') < section.index('_api.DestroyPipelineCache(_device, staging, null);') <
      section.index('_api.DestroyPipelineCache(_device, workerCache, null);') < section.index('if (accepted && !failed && !_disposed)') <
      section.index('CompactMainAfterLoad(length);'),
      'under the main lock, after the merge and after the staging caches are destroyed, for an accepted and merged snapshot only')
compact = member(manager_k, 'private void CompactMainAfterLoad(long fileBytes)')
check(compact.index('main.Frozen') < compact.index('GetCacheDataSize(main)') < compact.index('main.OnMeasured(data);') <
      compact.index('MainFileWorthCompacting(fileBytes, data)') < compact.index('SaveCache(main, data, final: false);') and
      compact.count('SaveCache(') == 1 and 'catch (Exception exception)' in compact and 'data <= main.Budget' in compact,
      'measured once; the estimate corrected; written by the existing SaveCache only when worth it and within the budget; a failure is contained')
for signature in ('private unsafe void SaveCache(CacheState state, long size, bool final)', 'private unsafe long GetCacheDataSize(CacheState state)',
                  'private bool MainGrowthWorthWriting(long size, long now, bool pause)', 'public void CheckpointMainOnPause()',
                  'private void CheckpointMainIfDue()'):
    check(member(manager_c, signature) == member(manager_k, signature), 'unchanged: ' + signature)
save = member(manager_k, 'private unsafe void SaveCache(CacheState state, long size, bool final)')
check('string temporaryPath = state.Path + ".tmp";' in save and 'File.Move(temporaryPath, state.Path, overwrite: true);' in save,
      'the file is written beside it and moved over it (the mapped snapshot main references keeps its bytes)')
check('RewindBox cache keys: a cached library keeps the resource bindings a lookup reads' in PATCH.read_text(),
      'the recipe patch holds the part that makes main smaller than a file written before')

# --- Production assembly builds ---
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1')
result = subprocess.run([DOTNET, 'build', str(CANDIDATE / 'src/Ryujinx.Graphics.Vulkan/Ryujinx.Graphics.Vulkan.csproj'), '-c', 'Release',
                         '-nologo', '-m:1', '-p:NuGetAudit=false'], capture_output=True, text=True, timeout=2400, env=environment, cwd=CANDIDATE)
if result.returncode:
    print(result.stdout[-6000:], result.stderr[-2000:], flush=True)
check(result.returncode == 0, 'production Ryujinx.Graphics.Vulkan builds with the adapter')

# --- Executed: control, candidate and sensitivity fixtures ---
ALWAYS_OLD = '''            return dataBytes > 0 && dataBytes <= fileBytes / MainCompactFileShare &&
                fileBytes - dataBytes >= MainCheckpointMinimumGrowthBytes;
'''
check(manager_k.count(ALWAYS_OLD) == 1 and manager_k.count(adapter.CALL_NEW) == 1, 'the parts the sensitivity variants change are present once')
SENSITIVITY = {
    'noCall': manager_k.replace(adapter.CALL_NEW, adapter.CALL_OLD + '                _ = (Action<long>)CompactMainAfterLoad;\n'),
    'alwaysCompact': manager_k.replace(ALWAYS_OLD, '            return dataBytes > 0;\n'),
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
check(c['decisions'] is None, 'control: no such decision')
check(k['decisions'] == dict(ipa724=True, moreThanHalf=False, exactlyHalf=True, under8MiBSaved=False, smallFile=False, sameSize=False,
                             grown=False, empty=False), 'candidate: written again when at most half the file and 8 MiB less: %s' % k['decisions'])
cm, km = c['migration'], k['migration']
for name, m in (('control', cm), ('candidate', km)):
    check(m['fileBefore'] == m['wholeSize'] and m['entriesInMain'] == 200 and m['invalidReads'] == 0 and m['mappedAfterLoad'] and
          not m['temporaryLeft'] and m['allOnDisk'], name + ': the whole file loaded, its mapping valid, every library on disk')
check(cm['fileAfterLoad'] == cm['wholeSize'] and cm['writtenAtLoad'] == 0 and cm['compactRecords'] == 0 and cm['entriesOnDiskAtKeyLength'] == 0 and
      cm['nextLaunchReadBytes'] == cm['wholeSize'] and cm['mainWrittenBytes'] == cm['wholeSize'],
      'control: the file stays whole after the load, and the next launch of a killed session reads it whole again: ' + json.dumps(cm))
check(km['fileAfterLoad'] == km['keySize'] and km['writtenAtLoad'] == km['keySize'] and km['compactRecords'] == 1 and km['writtenRecords'] == 1 and
      km['loadedSizeRecords'] == 0 and km['entriesOnDisk'] == 200 and km['entriesOnDiskAtKeyLength'] == 200 and km['mainWrittenBytes'] == km['keySize'] and
      km['validReads'] >= 2 and 'written again now (adapt_pipeline_cache_compact)' in km['record'],
      'candidate: written again at the load at the key size, every library in it, one journal record, the old mapping still read: ' + json.dumps(km))
check(km['nextLaunchReadBytes'] == km['keySize'] and km['nextLaunchEntries'] == 200 and km['nextLaunchCompactRecords'] == 0 and
      km['nextLaunchWritten'] == 0 and km['nextLaunchFile'] == km['keySize'] and km['nextLaunchInvalidReads'] == 0,
      'candidate: the next launch of the killed session reads the small file and writes nothing')
cs, ks = c['session'], k['session']
check(ks['fileAfterLoad'] == ks['keySizeWithWorker'] and ks['entriesOnDiskAfterLoad'] == 220, 'candidate: the worker snapshot joined at the load is in the file written then')
check(cs['entriesOnDiskAfterLoad'] == 200, 'control: the file is untouched by the load')
for name, s in (('control', cs), ('candidate', ks)):
    check(s['pauseSkipped'] == 1 and s['invalidReads'] == 0 and s['mainDestroyedWithValidRegions'] == 1 and s['entriesOnDiskAfterClose'] == 250 and
          s['allOnDisk'] and s['fileAfterClose'] == s['keySizeAfterClose'] and s['nextLaunchEntries'] == 250 and s['nextLaunchWritten'] == 0 and
          s['nextLaunchInvalidReads'] == 0, name + ': play, the pause, the close and the next launch as before: ' + json.dumps(s))
check(ks['fileAfterPause'] == ks['fileAfterLoad'], 'candidate: the pause under 8 MiB of new content writes nothing')
for name, r in (('control', c), ('candidate', k)):
    a = r['alreadyKeys']
    check(a['fileAfterLoad'] == a['fileBefore'] and a['sameFile'] and a['writtenAtLoad'] == 0 and a['compactRecords'] == 0 and a['entriesInMain'] == 2200 and
          a['mainWrittenBytes'] == a['fileBefore'], name + ': a file already holding keys is not written at the load: ' + json.dumps(a))
check(k['alreadyKeys']['loadedSizeRecords'] == 1 and c['alreadyKeys']['loadedSizeRecords'] == 0, 'candidate: one loadedSize record')
cf, kf = c['smallFile'], k['smallFile']
check(kf['writtenAtLoad'] == 0 and kf['compactRecords'] == 0 and kf['fileAfterLoad'] == kf['fileBefore'] and kf['mainWrittenBytesAfterLoad'] == kf['keySize'],
      'candidate: under 8 MiB to gain, the file is left; the growth rule counts from main\'s data: ' + json.dumps(kf))
check(kf['pauseWroteNewLibraries'] and kf['entriesOnDiskAfterPause'] == 2110, 'candidate: 8 MiB of new libraries are written at the pause')
check(cf['mainWrittenBytesAfterLoad'] == cf['fileBefore'] and not cf['pauseWroteNewLibraries'],
      'control: the same 8 MiB of new libraries are not written (counted against the file\'s larger size)')
kw = k['writeFails']
check(kw['fileAfterLoad'] == kw['fileBefore'] and not kw['temporaryLeft'] and kw['entriesOnDiskAfterLoad'] == 200 and kw['entriesOnDiskAfterClose'] == 210 and
      kw['fileAfterClose'] == kw['keySizeAfterClose'] and kw['invalidReads'] == 0,
      'candidate: a failed write at the load leaves the whole file valid; the session and its close go on: ' + json.dumps(kw))
for name, r in (('control', c), ('candidate', k)):
    o = r['overtaken']
    check(o['pendingAtClose'] and o['fileAfter'] == o['fileBefore'] and o['writtenAtLoad'] == 0 and o['compactRecords'] == 0 and o['loadedSizeRecords'] == 0 and
          o['invalidReads'] == 0 and not o['temporaryLeft'], name + ': a close overtaking the load: nothing measured or written: ' + json.dumps(o))
check(reports['noCall']['migration']['fileAfterLoad'] == reports['noCall']['migration']['wholeSize'] and reports['noCall']['migration']['compactRecords'] == 0,
      'sensitivity: without the call the file stays whole')
check(reports['alwaysCompact']['alreadyKeys']['writtenAtLoad'] > 0 and not reports['alwaysCompact']['alreadyKeys']['sameFile'],
      'sensitivity: a decision that always writes rewrites a file already holding keys')
unexpected = [w for w in k['warnings'] if 'Unable to read Vulkan pipeline cache for persistence' not in w]
check(not unexpected, 'candidate: no warning but the failed write of its scenario: ' + str(unexpected))

inputs = ['build-utils/melonx/adapt_pipeline_cache_compact.py', 'build-utils/melonx/adapt_session.py',
          'build-utils/melonx/moltenvk/rewindbox-moltenvk.patch',
          'test/melonx_pipeline_cache_compact_test.py', 'test/melonx_pipeline_cache_compact/Program.cs',
          'test/melonx_pipeline_cache_compact/Double.cs', 'test/melonx_adapter_control.py']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core727Preparation',
               postimages={p: sha(FINAL_SOURCE / p) for p in adapter.BASELINE} if FINAL_PREPARATION else {},
               comparison=dict(wholeFileBytes=km['wholeSize'], keyFileBytes=km['keySize'], writtenAtLoadCandidate=km['writtenAtLoad'],
                               writtenAtLoadControl=cm['writtenAtLoad'], nextLaunchReadsCandidate=km['nextLaunchReadBytes'],
                               nextLaunchReadsControl=cm['nextLaunchReadBytes'], sensitivityVariantsFailed=2),
               reports=reports, sdk=sdk, host=platform.system(), physicalDeviceTested=False, productionVulkanSourceExecuted=True,
               driverModel='a cache created from data keeps each whole entry at a sixteenth of its length (the cache key of the '
                           'recipe patch\'s fifth part); the real sizes and memory are the melonx-cache-keys run',
               inputs={name: sha(ROOT / name) for name in inputs},
               limitation='The manager on a content double: what MoltenVK keeps of a real file, the time of the write on the '
                          'device and the footprint are shown only by the macOS measure and a device run '
                          '(pipelineCache compact / loadedSize records, the load line of the driver).')
out = ROOT / 'dist/melonx/pipeline-cache-compact-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
