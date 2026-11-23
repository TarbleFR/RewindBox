#!/usr/bin/env python3
"""The GPU thread's sync query no longer waits behind a reader's GPU wait (adapt_unblocked_sync_queries), before and
after, real engine code.

Usage: melonx_unblocked_sync_queries_test.py <final preparation containing the adapter>
       melonx_unblocked_sync_queries_test.py <control> --candidate-source <final preparation containing the adapter>

Control is the preparation with the adapter reversed (melonx_adapter_control); candidate is the adapter applied to it,
which must give the final preparation's files. For each, the production SyncManager, MultiFenceHolder, FenceHolder,
FenceHelper, CommandBufferPool, CommandBufferScoped, BufferUsageBitmap, BitMap, VulkanException, ObjectPool, SpanOwner
and the GAL SyncMap are compiled with the doubles of test/melonx_unblocked_sync_queries (Double.cs): Vulkan and MoltenVK
are a GPU model whose fences signal when a GPU thread has executed the submitted command buffers in order, each for the
GPU time recorded into it, and whose vkQueueSubmit spends CPU time per recorded draw on the submitting thread. The probe
(Program.cs) runs:
 1. a scripted single-thread sequence (6 000 steps: draws, syncs strict or not, flushes, GPU completions, queries, waits,
    cleanups): the trace of every query value, wait and pool count must be the control's byte for byte;
 2. the convoy: a reader waits for a command buffer with 60 ms of GPU work; the GPU thread's query, a render-thread sync
    creation and a lookup of a long-signalled sync are timed (control: each waits for that GPU work; candidate: none);
 3. the candidate's journal line over one 5 s window, with known waits from three kinds of thread;
 4. a stream shaped like the IPA 822 Hogwarts Legacy window (draws, framebuffers, 4 strict and 14 other syncs per frame,
    present, a guest read-back per frame, a guest memory reader, GPU/render/GPU-thread costs), with and without the
    GPU-thread queries, and a light stream: frame time, GPU busy, submissions, syncs, fences and holders created, render
    passes and passes begun again on the same framebuffer, blocked time on the GPU thread and the render thread, guest
    waits, and two guest-visible invariants (a wait never returns before the work recorded before its sync completed; a
    query never reports a sync whose predecessor's work is not complete);
 5. the cost of an uncontended query and of a signalled wait.
The candidate's production Vulkan assembly (with GAL) is built. No device. Writes dist/melonx/unblocked-sync-queries-checks.json.
"""
from pathlib import Path
import hashlib, json, os, re, shutil, statistics, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
FINAL_SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, files_edited_later  # noqa: E402
_HOLD = []
SOURCE, FINAL_PREPARATION = control_source(FINAL_SOURCE, 'adapt_unblocked_sync_queries', _HOLD)
import adapt_unblocked_sync_queries as adapter  # noqa: E402

VULKAN = 'src/Ryujinx.Graphics.Vulkan/'
DOTNET = os.environ.get('DOTNET', 'dotnet')
FIXTURE = ROOT / 'test/melonx_unblocked_sync_queries'
COMPILED = [VULKAN + name for name in ('SyncManager.cs', 'MultiFenceHolder.cs', 'FenceHolder.cs', 'FenceHelper.cs', 'CommandBufferPool.cs',
                                       'CommandBufferScoped.cs', 'BufferUsageBitmap.cs', 'BitMap.cs', 'VulkanException.cs')] + \
           ['src/Ryujinx.Common/Pools/ObjectPool.cs', 'src/Ryujinx.Common/Memory/SpanOwner.cs', adapter.MAP]
REPEATS = 3
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


def project_closure(tree, project):
    """The project and every project it references, transitively (relative paths of their directories)."""
    found, pending = [], [Path(project)]
    while pending:
        current = pending.pop()
        directory = current.parent.as_posix()
        if directory in found:
            continue
        found.append(directory)
        text = (tree / current).read_text(encoding='utf-8-sig')
        for reference in re.findall(r'<ProjectReference Include="([^"]+)"', text):
            pending.append(Path(os.path.normpath((current.parent / reference.replace('\\', '/')).as_posix())))
    return found


# 0. The control and the candidate texts.
check(FINAL_PREPARATION, 'the source is a final preparation containing the adapter')
for name, expected in adapter.BASELINE.items():
    check(sha(SOURCE / name) == expected, "not the adapter's preparation: " + name)
control = {name: (SOURCE / name).read_text(encoding='utf-8-sig') for name in adapter.BASELINE}
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
reports, compiled_inputs = {}, {}

with tempfile.TemporaryDirectory(prefix='melonx-unblocked-sync-queries-') as temporary:
    temporary = Path(temporary).resolve()
    tree = temporary / 'candidate-tree'
    project = VULKAN + 'Ryujinx.Graphics.Vulkan.csproj'
    for name in ('Directory.Build.props', 'Directory.Packages.props', 'global.json', 'nuget.config'):
        if (SOURCE / name).exists():
            (tree / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / name, tree / name)
    for directory in project_closure(SOURCE, project):
        shutil.copytree(SOURCE / directory, tree / directory, ignore=shutil.ignore_patterns('bin', 'obj'), symlinks=True)
    for name in COMPILED:
        if not (tree / name).exists():
            (tree / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / name, tree / name)
    changed = adapter.apply(tree)
    check(sorted(p.relative_to(tree).as_posix() for p in changed) == sorted(adapter.BASELINE), 'the adapter changed its two files')
    later = files_edited_later('adapt_unblocked_sync_queries')
    for name in adapter.BASELINE:
        if name not in later:
            check((tree / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)
    candidate = {name: (tree / name).read_text(encoding='utf-8-sig') for name in adapter.BASELINE}
    drift = temporary / 'drift'
    for name in adapter.BASELINE:
        (drift / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SOURCE / name, drift / name)
    (drift / adapter.SYNC).write_bytes((drift / adapter.SYNC).read_bytes() + b'\n// unreviewed drift\n')
    try:
        adapter.apply(drift)
        refused = False
    except AssertionError:
        refused = True
    check(refused, 'a drifted SyncManager.cs is refused')

    result = subprocess.run([DOTNET, 'build', str(tree / project), '-c', 'Release', '-nologo', '-m:1', '-p:NuGetAudit=false'],
                            capture_output=True, text=True, timeout=2400, env=environment, cwd=tree)
    if result.returncode:
        print(result.stdout[-6000:], result.stderr[-2000:], flush=True)
    check(result.returncode == 0, 'candidate production Vulkan assembly (and GAL) builds')
    warnings = sorted({line for line in result.stdout.splitlines() if 'warning' in line and
                       any(Path(name).name + '(' in line for name in adapter.BASELINE)})
    check(not warnings, 'no compiler warning in the edited files: ' + '\n'.join(warnings[:5]))

    for variant, source in (('control', SOURCE), ('candidate', tree)):
        fixture = temporary / ('fixture-' + variant)
        for name in COMPILED:
            (fixture / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / name, fixture / name)
        for name in ('Double.cs', 'Program.cs'):
            shutil.copyfile(FIXTURE / name, fixture / name)
        define = 'CANDIDATE' if variant == 'candidate' else 'CONTROL'
        (fixture / 'Fixture.csproj').write_text(
            '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
            '<LangVersion>preview</LangVersion><Nullable>disable</Nullable><AllowUnsafeBlocks>true</AllowUnsafeBlocks>'
            '<NuGetAudit>false</NuGetAudit><EnableNETAnalyzers>false</EnableNETAnalyzers><NoWarn>CS0649;CS0414;CS0169;CS8321;CS1998</NoWarn>'
            f'<DefineConstants>$(DefineConstants);{define}</DefineConstants></PropertyGroup></Project>\n')
        compiled_inputs[variant] = {p.relative_to(fixture).as_posix(): sha(p) for p in sorted(fixture.rglob('*.cs'))}
        for command in ([DOTNET, 'build', str(fixture / 'Fixture.csproj'), '-c', 'Release', '-nologo', '-p:NuGetAudit=false'],
                        [DOTNET, str(fixture / 'bin/Release/net10.0/Fixture.dll'), str(REPEATS)]):
            result = subprocess.run(command, capture_output=True, text=True, timeout=1200, env=environment, cwd=fixture)
            if result.returncode:
                print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
                result.check_returncode()
        reports[variant] = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
        print(variant, json.dumps({k: v for k, v in reports[variant].items() if k != 'streams'}), flush=True)

# 1. Static: what changed in the production text.
query_c = member(control[adapter.SYNC], 'public ulong GetCurrent()')
query_k = member(candidate[adapter.SYNC], 'public ulong GetCurrent()')
check('lock (handle)' in query_c and 'lock (handle)' not in query_k and query_k.count('Monitor.TryEnter(handle)') == 1 and
      query_k.count('Monitor.Exit(handle)') == 1, 'the query takes each handle without waiting for it, and releases it')
check(query_k.count('handle.Waitable.WaitForFences(_gd.Api, _device, 0)') == query_c.count('handle.Waitable.WaitForFences(_gd.Api, _device, 0)') == 1,
      'the query polls a free handle as before')
for signature in ('public void Create(ulong id, bool strict)', 'private void RequestFlush(SyncHandle handle)', 'public void RegisterFlush()'):
    check(member(control[adapter.SYNC], signature) == member(candidate[adapter.SYNC], signature), 'unchanged: ' + signature)
wait_c, wait_k = member(control[adapter.SYNC], 'public void Wait(ulong id)'), member(candidate[adapter.SYNC], 'public void Wait(ulong id)')
check(wait_k.count('lock (') == wait_c.count('lock (') == 2 and wait_k.count('WaitForFences(') == wait_c.count('WaitForFences(') == 1 and
      wait_k.count('RequestFlush(result);') == wait_c.count('RequestFlush(result);') == 1, 'the wait keeps its locks, fence wait and flush request')
for name in adapter.BASELINE:
    for text in (candidate[name],):
        code = re.sub(r'//[^\n]*', '', text)
        check(code.count('FlushAllCommands') == re.sub(r'//[^\n]*', '', control[name]).count('FlushAllCommands') and
              code.count('AddWaitable') == re.sub(r'//[^\n]*', '', control[name]).count('AddWaitable') and
              code.count('AddInUseWaitable') == re.sub(r'//[^\n]*', '', control[name]).count('AddInUseWaitable'),
              'no submission or waitable added or removed: ' + name)
map_c, map_k = control[adapter.MAP], candidate[adapter.MAP]
check(member(map_c, 'internal void AssignSync(ulong id)') == member(map_k, 'internal void AssignSync(ulong id)') and
      member(map_c, 'internal void CreateSyncHandle(ulong id)') == member(map_k, 'internal void CreateSyncHandle(ulong id)'),
      'the sync map assigns and creates as before')
added = [line for line in member(map_k, 'internal void WaitSyncAvailability(ulong id)').splitlines()
         if line not in member(map_c, 'internal void WaitSyncAvailability(ulong id)').splitlines()]
check(all(adapter.TAG in line or line.strip() == 'if (waitStart != 0)' for line in added) and len(added) == 4,
      'the availability wait only gains its timing: ' + json.dumps(added))

c, k = reports['control'], reports['candidate']
# 2. Scripted: the same trace without contention.
check(c['scripted'] == k['scripted'] and c['scripted']['violations'] == 0 and c['scripted']['syncs'] > 900,
      'scripted: every query value, wait and pool count is the control\'s: ' + json.dumps([c['scripted'], k['scripted']]))
# 3. The convoy.
cc, kc = c['convoy'], k['convoy']
for report in (cc, kc):
    check(report['gpuWorkLeftAtQueryMs'] > 30 and 55 <= report['readerWaitMs'] < 200, 'the reader waited for its 60 ms command buffer: ' + json.dumps(report))
    check(report['currentAfter'] == 1, 'after the wait, the query reports the waited sync')
check(cc['queryMs'] > 30 and cc['createMs'] > 25 and cc['signalledLookupMs'] > 25 and cc['currentDuring'] == 1,
      'control: the query, a sync creation and a lookup of a signalled sync each wait for the GPU work: ' + json.dumps(cc))
check(kc['queryMs'] < 5 and kc['createMs'] < 5 and kc['signalledLookupMs'] < 5 and kc['readerStillWaitingAfterQuery'],
      'candidate: none of them waits for the reader\'s GPU work: ' + json.dumps(kc))
check(kc['currentDuring'] <= cc['currentDuring'], 'candidate: the query during the wait reports no later sync than the control')
# 4. The journal line.
line = k['journal']['line']
pattern = (r'^LogJournalIfDue: Vulkan host sync waits over (5\d{3}\.\d) ms: 6 waits [\d.]+ ms \(longest [\d.]+ ms; GPU thread 2 [\d.]+ ms, '
           r'render thread 3 [\d.]+ ms, other threads 1 [\d.]+ ms; submitted for the waiter 1 [\d.]+ ms\); waits for the render thread to '
           r'create the sync 1 (\d+\.\d) ms \(longest (\d+\.\d) ms\); sync queries 4 [\d.]+ ms \(longest [\d.]+ ms, fence holders polled 0, '
           r'passed a sync being waited for 0\) \(adapt_unblocked_sync_queries\)$')
match = re.match(pattern, line)
check(match is not None and 29 <= float(match.group(2)) < 200 and match.group(2) == match.group(3), 'the journal line: ' + line)
check(c['journal'] is None, 'the control has no journal line')


# 5. The streams: medians over the repeats.
def streams(report, label):
    return [s for s in report['streams'] if s['label'] == label]


def median(report, label, key):
    return statistics.median(s[key] for s in streams(report, label))


summary = {}
for label in ('hogwarts-queries', 'hogwarts-no-queries', 'light-queries'):
    check(len(streams(c, label)) == len(streams(k, label)) == REPEATS, label + ': every repeat ran')
    for report in (c, k):
        for s in streams(report, label):
            check(s['violations'] == 0 and s['signalTimeouts'] == 0, label + ': no wait or query ahead of the GPU work, no timeout')
            check(s['syncsPerFrame'] == s['holdersPerFrame'], label + ': one managed holder per sync, no other primitive per sync')
    keys = ('frameMs', 'gpuBusyPercent', 'submitsPerFrame', 'syncsPerFrame', 'fencesCreatedPerFrame', 'holdersPerFrame', 'passesPerFrame',
            'passResumesPerFrame', 'gpuThreadQueryMs', 'gpuThreadQueryMaxMs', 'renderNonStrictCreateMs', 'renderNonStrictCreateMaxMs',
            'readbackWaitPerFrameMs', 'readerWaitMeanMs', 'readerWaitMaxMs')
    summary[label] = {variant: {key: round(median(report, label, key), 3) for key in keys} for variant, report in (('control', c), ('candidate', k))}
    sc, sk = summary[label]['control'], summary[label]['candidate']
    check(sc['syncsPerFrame'] == sk['syncsPerFrame'] and sc['holdersPerFrame'] == sk['holdersPerFrame'], label + ': the same syncs and holders')
    check(abs(sc['submitsPerFrame'] - sk['submitsPerFrame']) <= 0.35 and abs(sc['fencesCreatedPerFrame'] - sk['fencesCreatedPerFrame']) <= 0.35 and
          abs(sc['passResumesPerFrame'] - sk['passResumesPerFrame']) <= 0.35,
          label + ': the same submissions, fences and passes begun again (timing-dependent flushes aside): ' + json.dumps(summary[label]))
hq = summary['hogwarts-queries']
check(hq['control']['gpuThreadQueryMs'] > 20 * max(hq['candidate']['gpuThreadQueryMs'], 1) and
      hq['control']['renderNonStrictCreateMs'] > 10 * max(hq['candidate']['renderNonStrictCreateMs'], 1),
      'hogwarts with queries: the GPU thread and the render thread no longer wait behind the readers: ' + json.dumps(hq))
check(hq['candidate']['gpuThreadQueryMaxMs'] < 2, 'hogwarts with queries: no query waits for GPU work in the candidate')
check(hq['candidate']['frameMs'] <= hq['control']['frameMs'] * 1.02, 'hogwarts with queries: no longer frame: ' + json.dumps(hq))
for label in ('hogwarts-no-queries', 'light-queries'):
    s = summary[label]
    check(s['candidate']['frameMs'] <= s['control']['frameMs'] * 1.05, label + ': no regression without contention: ' + json.dumps(s))
check(k['costs']['current'] == c['costs']['current'] and k['costs']['queryNanoseconds'] < c['costs']['queryNanoseconds'] + 1000 and
      k['costs']['signalledWaitNanoseconds'] < c['costs']['signalledWaitNanoseconds'] + 300,
      'the journal counters cost under a microsecond per query and 300 ns per wait: ' + json.dumps([c['costs'], k['costs']]))

inputs = ['build-utils/melonx/adapt_unblocked_sync_queries.py', 'build-utils/melonx/adapt_session.py', 'test/melonx_unblocked_sync_queries_test.py',
          'test/melonx_unblocked_sync_queries/Double.cs', 'test/melonx_unblocked_sync_queries/Program.cs', 'test/melonx_adapter_control.py']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, probeChecks={'control': c['checks'], 'candidate': k['checks']},
               finalPreparationBound=FINAL_PREPARATION, sourceKind='finalPreparationWithReversedControl',
               postimages={p: sha(FINAL_SOURCE / p) for p in adapter.BASELINE}, sourceBaseline=adapter.BASELINE,
               physicalDeviceTested=False, productionVulkanAssemblyBuilt=True, vulkanAndMoltenVkDoubled=True,
               scripted=k['scripted'], convoy={'control': cc, 'candidate': kc}, journalLine=line, streams=summary,
               costs={'control': c['costs'], 'candidate': k['costs']}, repeats=REPEATS, sdk=sdk, compiledSourceInputs=compiled_inputs,
               inputs={p: sha(ROOT / p) for p in inputs},
               limitation='Host threads with a GPU model (in-order command buffers, recorded GPU time, encoding CPU time at '
                          'submission); the stream is shaped by the IPA 822 per-frame counts, not replayed. How often a buffer '
                          'migration makes the GPU thread query while a reader waits on the device is read from the journal line '
                          '("passed a sync being waited for") of the next device session.')
out = ROOT / 'dist/melonx/unblocked-sync-queries-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk, streams=summary)))
