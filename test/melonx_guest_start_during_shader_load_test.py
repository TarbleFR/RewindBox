#!/usr/bin/env python3
"""The guest starts while the disk shader cache loads (adapt_guest_start_during_shader_load), before and after, real engine code.

Usage: melonx_guest_start_during_shader_load_test.py <final preparation containing the adapter>
       melonx_guest_start_during_shader_load_test.py <control> --candidate-source <final preparation containing the adapter>

Control is the preparation with the adapter reversed (melonx_adapter_control), candidate is the adapter applied to it,
which must be the final preparation byte for byte. The real GpuContext members of the GPU initialization (its fields and
states, RegisterProcess, UnregisterProcess, InitializeShaderCache, CancelShaderCacheInitialization, WaitUntilGpuReady,
RunDeferredActions, Dispose and, in the candidate, WaitUntilGuestMayStart, ReleaseGuestForShaderLoad,
WaitForShaderCacheLoader and GetShaderLoadPhase), the real PhysicalMemory.Dispose and Destroy and the whole real
ArmProcessContext.cs, SynchronizationManager.cs, Syncpoint.cs, SyncpointWaiterHandle.cs and ISynchronizationManager.cs run with
doubles (test/melonx_guest_start_during_shader_load): a shader cache whose load lasts a set time and fills a table, a
guest whose threads submit GPU commands as soon as they execute, the GPU thread of WindowBase.Render (the loop after
InitializeShaderCache) and the session owner's stop and release.

For control and candidate: (1) a launch with a 600 ms load: the control's guest starts after the load, the candidate's
while it runs, and the time to "guest started" drops by the load; (2) a stop before the loader starts, a stop during
the load (two ways the loader leaves) and a loader failure: the guest does not execute, or was already executing and
its unregistration returns only after the loader ended, a thread created afterwards never executes, no thread stays
blocked; a guest process that ends during the load; a release after a failed render worker; (3) the first GPU command
is processed only after the load, with the whole table, in every case; (4) 200 launches with randomized small delays.
Fences (the wait NvHostEvent forces on the CPU side after two cancellations), on a 2 s load: an infinite WaitOnSyncpoint
issued during the load answers "timed out" after its 1 s clamp in the control, with nothing processed, and in the
candidate only once the load has ended and the syncpoint was incremented, signalled; one that is never incremented ends
1 s after the end of the load; a finite timeout ends when asked in both; WaitOnSyncpointWhileProgressing (Hogwarts
policy) gives up as idle or without progress in the control and reaches the fence in the candidate; the same waits
issued after the load behave identically in both; a stop wakes the parked waits within a 50 ms slice while the loader
still unwinds, a failed loader as soon as it has ended, and a wait issued after a cancelled load is the 1 s one.
A third build, the candidate without its two waits for the loader, must show the unregistration and the release
overtaking the loader: the checks see the fault they guard against. Static checks bind the adapter's hunks, the
order inside InitializeShaderCache, the callers and the unchanged render loop, stop order and deferred destruction.
The candidate's Ryujinx.Graphics.Gpu and Ryujinx.HLE are built. No device: the launch time on an iPhone, and what a
guest does while the GPU thread still loads, are known only from a device run.
Writes dist/melonx/guest-start-during-shader-load-checks.json.
"""
from pathlib import Path
import difflib, filecmp, hashlib, json, os, re, shutil, subprocess, sys, tempfile, time

ROOT = Path(__file__).resolve().parents[1]
FINAL_SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, files_edited_later, use_authenticated_libhac_feed  # noqa: E402
_HOLD = []
SOURCE, FINAL_PREPARATION = control_source(FINAL_SOURCE, 'adapt_guest_start_during_shader_load', _HOLD)
from adapt_guest_start_during_shader_load import apply, BASELINE, FILE_PAIRS  # noqa: E402

GPU = 'src/Ryujinx.Graphics.Gpu/GpuContext.cs'
PROCESS = 'src/Ryujinx.HLE/HOS/ArmProcessContext.cs'
MEMORY = 'src/Ryujinx.Graphics.Gpu/Memory/PhysicalMemory.cs'
SYNC = 'src/Ryujinx.Graphics.Gpu/Synchronization/SynchronizationManager.cs'
# Compiled whole, with SynchronizationManager.cs and ArmProcessContext.cs.
WHOLE = ('src/Ryujinx.Graphics.Gpu/Synchronization/Syncpoint.cs', 'src/Ryujinx.Graphics.Gpu/Synchronization/SyncpointWaiterHandle.cs',
         'src/Ryujinx.Graphics.Device/ISynchronizationManager.cs')
WINDOW = 'src/Ryujinx.Library/Window/WindowBase.cs'
LIFETIME = 'src/Ryujinx.Library/EmbeddedWindowLifetime.cs'
PROJECTS = ('src/Ryujinx.Graphics.Gpu/Ryujinx.Graphics.Gpu.csproj', 'src/Ryujinx.HLE/Ryujinx.HLE.csproj')
DOTNET = os.environ.get('DOTNET', 'dotnet')
FIXTURE = ROOT / 'test/melonx_guest_start_during_shader_load'
SEED = int(os.environ.get('MELONX_GUEST_START_SEED') or time.time_ns() % 1_000_000_007)
WAIT_CALL = '            WaitForShaderCacheLoader();\n'
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def member(text, signature):
    start = text.rindex('\n', 0, text.index(signature)) + 1
    depth, index = 0, text.index('{', start)
    for index in range(index, len(text)):
        depth += (text[index] == '{') - (text[index] == '}')
        if depth == 0:
            return text[start:index + 1]
    raise AssertionError(signature)


def read(tree, name):
    return (tree / name).read_text(encoding='utf-8-sig')


def sources(tree):
    return sorted(p.relative_to(tree).as_posix() for p in tree.rglob('*')
                  if p.is_file() and not {'.git', 'bin', 'obj'} & set(p.relative_to(tree).parts))


GPU_MEMBERS = ('public void RegisterProcess(', 'public void UnregisterProcess(', 'private void ShaderCacheStateUpdate(',
               'public bool InitializeShaderCache(', 'public void CancelShaderCacheInitialization()', 'public bool WaitUntilGpuReady()',
               'internal void RunDeferredActions()', 'public void Dispose()')
NEW_MEMBERS = ('public bool WaitUntilGuestMayStart()', 'private void ReleaseGuestForShaderLoad(', 'private void WaitForShaderCacheLoader()',
               'internal SynchronizationManager.ShaderLoadPhase GetShaderLoadPhase()')


def fixture_source(gpu, memory):
    """Double.cs with the real members of this variant's GpuContext.cs and PhysicalMemory.cs."""
    fields = gpu[gpu.index('        private readonly ManualResetEvent _gpuReadyEvent;'):
                 gpu.index('        /// <summary>\n        /// Creates a new instance of the GPU emulation context.')]
    check('private enum GpuInitializationState' in fields and '_gpuInitializationCancellationRequested' in fields,
          'the initialization\'s fields and states are the real ones')
    constructor = member(gpu, 'public GpuContext(IRenderer renderer, DirtyHacks hacks)')
    events = ''.join(line + '\n' for line in constructor.splitlines()
                     if re.fullmatch(r'\s+(_\w+Event = new ManualResetEvent\(false\)|Synchronization = new SynchronizationManager\(\w*\));', line))
    check(events.count('new SynchronizationManager(') == 1, 'the syncpoint manager is constructed by the real line')
    signatures = GPU_MEMBERS + tuple(s for s in NEW_MEMBERS if s in gpu)
    methods = '\n\n'.join(member(gpu, s) for s in signatures)
    memory_methods = member(memory, 'public void Dispose()') + '\n\n' + member(memory, 'private void Destroy()')
    template = (FIXTURE / 'Double.cs').read_text()
    for mark, code in (('/* GPU_FIELDS */', fields), ('/* GPU_CONSTRUCTOR */', events), ('/* GPU_METHODS */', methods),
                       ('/* MEMORY_METHODS */', memory_methods)):
        check(template.count(mark) == 1, 'fixture mark ' + mark)
        template = template.replace(mark, code)
    return template


check(FINAL_PREPARATION, 'the source is a final preparation containing the adapter')
for name, expected in BASELINE.items():
    check(hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected, 'not the adapter\'s preparation: ' + name)

reports, builds = {}, {}
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
with tempfile.TemporaryDirectory(prefix='melonx-guest-start-shader-load-') as temporary:
    work = Path(temporary).resolve() / 'candidate'
    shutil.copytree(SOURCE, work, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
    changed = apply(work)
    check(sorted(str(p.relative_to(work)) for p in changed) == sorted(BASELINE), 'adapter changed other files')
    later = files_edited_later('adapt_guest_start_during_shader_load')
    for name in BASELINE:
        if name not in later:
            check((work / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)
    # The adapter touches its declared files only: every other file of the tree is the control's, byte for byte.
    names = sources(SOURCE)
    check(names == sources(work), 'the adapter adds or removes no file')
    different = [name for name in names if not filecmp.cmp(SOURCE / name, work / name, shallow=False)]
    check(sorted(different) == sorted(BASELINE), 'only the declared files differ: ' + str(different))

    texts = {variant: {name: read(tree, name) for name in (GPU, PROCESS, MEMORY, SYNC) + WHOLE} for variant, tree in (('control', SOURCE), ('candidate', work))}
    # The candidate without its two waits for the loader: what the gate must be able to see.
    check(texts['candidate'][GPU].count(WAIT_CALL) == 2, 'two waits for the loader (UnregisterProcess, Dispose)')
    texts['withoutWaits'] = dict(texts['candidate'], **{GPU: texts['candidate'][GPU].replace(WAIT_CALL, '')})

    for variant in ('control', 'candidate', 'withoutWaits'):
        fixture = Path(temporary).resolve() / ('fixture-' + variant)
        fixture.mkdir()
        (fixture / 'Double.cs').write_text(fixture_source(texts[variant][GPU], texts[variant][MEMORY]))
        for name in (PROCESS, SYNC) + WHOLE:
            (fixture / Path(name).name).write_text(texts[variant][name])
        shutil.copyfile(FIXTURE / 'Program.cs', fixture / 'Program.cs')
        (fixture / 'Fixture.csproj').write_text(
            '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
            '<Nullable>disable</Nullable><NuGetAudit>false</NuGetAudit><NoWarn>CS0649;CS0414;CS0169;CS0067;CS8321;CS1998</NoWarn>'
            '</PropertyGroup></Project>\n')
        for command in ([DOTNET, 'build', str(fixture / 'Fixture.csproj'), '-c', 'Release', '-nologo', '-p:NuGetAudit=false'],
                        [DOTNET, str(fixture / 'bin/Release/net10.0/Fixture.dll'), variant, str(SEED), '0' if variant == 'withoutWaits' else '200']):
            result = subprocess.run(command, capture_output=True, text=True, timeout=1800, env=environment, cwd=fixture)
            if result.returncode:
                print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
                result.check_returncode()
        reports[variant] = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
        print(json.dumps(reports[variant]), flush=True)

    use_authenticated_libhac_feed(work, ROOT)
    for project in PROJECTS:
        result = subprocess.run([DOTNET, 'build', str(work / project), '-c', 'Release', '-nologo', '-m:1', '-p:NuGetAudit=false'],
                                capture_output=True, text=True, timeout=2400, env=environment, cwd=work)
        if result.returncode:
            print(result.stdout[-5000:], result.stderr[-2000:], flush=True)
        check(result.returncode == 0, 'candidate production assembly builds: ' + project)
        # The assembly just built is the candidate's: it carries the new wait, and the HLE no longer calls the old one.
        built = sorted((work / project).parent.glob('bin/Release/*/' + Path(project).stem + '.dll'))
        check(len(built) == 1, 'one production assembly: ' + project)
        image = built[0].read_bytes()
        check(b'WaitUntilGuestMayStart' in image and (b'WaitUntilGpuReady' in image) == (project == PROJECTS[0]) and
              ('guestStartedDuringShaderLoad'.encode('utf-16-le') in image) == (project == PROJECTS[0]),
              'the built assembly holds the change: ' + project)
        builds[project] = hashlib.sha256(image).hexdigest()

    callers = {variant: {method: sorted(name for name in names if name.endswith('.cs') and (method + '(').encode() in (tree / name).read_bytes())
                         for method in ('WaitUntilGpuReady', 'WaitUntilGuestMayStart', 'WaitForShaderCacheLoader', 'RunDeferredActions',
                                        'GetShaderLoadPhase', 'WaitOnSyncpoint', 'WaitOnSyncpointWhileProgressing')}
               for variant, tree in (('control', SOURCE), ('candidate', work))}

c, k, m = reports['control'], reports['candidate'], reports['withoutWaits']
NO_OVERTAKING = ('handlersRemovedDuringLoad', 'destroysQueuedDuringLoad', 'cachesDisposedDuringLoad', 'eventsDisposedDuringLoad')


def clean(report, name, failure=''):
    check(all(report[key] == 0 for key in NO_OVERTAKING) and report['unregisterReturnedDuringLoad'] is False,
          name + ': nothing is unregistered, queued for destruction or disposed while the loader runs: ' + str({key: report[key] for key in NO_OVERTAKING}))
    check(report['commandsDuringLoad'] == 0 and report['commandsWithPartialTable'] == 0, name + ': no GPU command before the load ended')
    check(report['blockedThreads'] == 0, name + ': no thread is left blocked')
    check(report['renderFailure'] == failure and report['disposeFailure'] == '', name + ': no failure but the loader\'s own: ' +
          str((report['renderFailure'], report['disposeFailure'])))
    check(report['forbiddenGuestRuns'] == 0 and report['guestStartsBeforeSnapshot'] == 0 and report['guestStartsBeforeHostInitialized'] == 0,
          name + ': no guest thread executes before the loader\'s snapshot or after a cancellation or failure')


# 1. A launch.
cl, kl = c['launch'], k['launch']
for name, report in (('control launch', cl), ('candidate launch', kl)):
    clean(report, name)
    check(report['programs'] == report['table'] == 60 and report['loadMs'] >= 550 and report['loadsBegun'] == 1, name + ': a 600 ms load of 60 programs: ' + str(report['loadMs']))
    check(report['initializeResult'] is True and report['state'] == 'Ready' and report['waitUntilGpuReady'] is True and report['loadedEventSeen'], name + ': the GPU is ready')
    check(report['guestThreadsRan'] == 3 and report['kernelExits'] == 0 and report['threadsEndedWithoutRunning'] == 0, name + ': the three guest threads execute')
    check(report['commands'] == 9 and report['firstCommandMs'] >= report['loadEndMs'], name + ': the first GPU command follows the load: ' +
          str((report['firstCommandMs'], report['loadEndMs'])))
    check(report['cachesDisposed'] == 1 and report['destroysQueued'] == 1, name + ': the caches are destroyed once, at the close')
check(cl['guestStartMs'] >= cl['loadEndMs'] and cl['guestStartsBeforeLoadEnded'] == 0, 'control: the guest starts after the load: ' + str((cl['guestStartMs'], cl['loadEndMs'])))
check(kl['guestStartMs'] < 150 and kl['guestStartMs'] < kl['loadEndMs'] - 0.8 * kl['loadMs'] and kl['guestStartsBeforeLoadEnded'] == 2,
      'candidate: the guest starts while the load runs: ' + str((kl['guestStartMs'], kl['loadBeginMs'], kl['loadEndMs'], kl['guestStartsBeforeLoadEnded'])))
check(cl['guestStartMs'] - kl['guestStartMs'] >= 0.8 * cl['loadMs'], 'the time to "guest started" drops by the load: ' +
      str((cl['guestStartMs'], kl['guestStartMs'], cl['loadMs'])))
check(cl['journal'] == [] and len(kl['journal']) == 1 and kl['journal'][0].startswith('launch guestStartedDuringShaderLoad ') and
      'registered memories in the loader\'s snapshot 1;' in kl['journal'][0], 'candidate: one journal line for the launch, none in the control: ' + str(kl['journal']))

# 2. Stopped before the loader starts.
for name, case in (('control', c['cancelBeforeLoader']), ('candidate', k['cancelBeforeLoader'])):
    report = case['report']
    clean(report, name + ' stop before the loader')
    check(case['released'] is True and report['guestThreadsRan'] == 0 and report['threadsEndedWithoutRunning'] == 2 and report['kernelExits'] == 2,
          name + ': stopped before the loader, no guest thread executes and each exits through the kernel')
    check(report['loadsBegun'] == 0 and report['initializeResult'] is False and report['state'] == 'Cancelled' and report['waitUntilGpuReady'] is False and
          report['commands'] == 0 and report['journal'] == [], name + ': nothing is loaded or drawn after a stop before the loader')

# Stopped during the load, whichever way the loader leaves.
for case in ('cancelDuringLoad', 'cancelDuringLoadThrowing'):
    for name, report in (('control ' + case, c[case]), ('candidate ' + case, k[case])):
        clean(report, name)
        check(report['initializeResult'] is False and report['state'] == 'Cancelled' and report['waitUntilGpuReady'] is False and report['commands'] == 0 and
              0 < report['table'] < report['programs'], name + ': the load is cancelled and no GPU command is processed')
        check(report['loadEndMs'] - report['stopMs'] >= 140 and report['stopReturnedMs'] >= report['loadEndMs'] and report['unregisterReturnMs'] >= report['loadEndMs'],
              name + ': the guest\'s termination and unregistration return only after the loader ended: ' +
              str((report['stopMs'], report['loadEndMs'], report['unregisterReturnMs'], report['stopReturnedMs'])))
        check(report['cachesDisposed'] == 1 and report['releaseEnterMs'] >= report['loadEndMs'], name + ': the caches are destroyed once, after the loader')
    check(c[case]['guestThreadsRan'] == 0 and c[case]['threadsEndedWithoutRunning'] == 2 and c[case]['journal'] == [], 'control ' + case + ': no guest thread executed')
    check(k[case]['guestThreadsRan'] == 1 and k[case]['threadsEndedWithoutRunning'] == 1 and k[case]['kernelExits'] == 1 and len(k[case]['journal']) == 1,
          'candidate ' + case + ': the thread started before the stop executed, the one created after it did not')
    check(k[case]['unregisterEnterMs'] < k[case]['loadEndMs'] - 100, 'candidate ' + case + ': the unregistration waited for the loader: ' +
          str((k[case]['unregisterEnterMs'], k[case]['loadEndMs'])))

# The loader fails.
cf, kf = c['loaderFailure'], k['loaderFailure']
for name, report in (('control loader failure', cf), ('candidate loader failure', kf)):
    clean(report, name, failure='InvalidOperationException')
    check(report['initializeResult'] is None and report['state'] == 'Failed' and report['waitUntilGpuReady'] is False and report['commands'] == 0 and
          report['table'] == 30, name + ': the failure reaches the render worker and no GPU command is processed')
    check(report['unregisterReturnMs'] >= report['loadEndMs'] and report['cachesDisposed'] == 1, name + ': unregistered and destroyed after the loader')
check(cf['guestThreadsRan'] == 0 and cf['threadsEndedWithoutRunning'] == 2 and cf['kernelExits'] == 2, 'control: a failed loader, no guest thread executes')
check(kf['guestThreadsRan'] == 1 and kf['guestStartsBeforeLoadEnded'] == 1 and kf['threadsEndedWithoutRunning'] == 1 and kf['kernelExits'] == 1,
      'candidate: the guest was executing when the loader failed; a thread created after the failure does not execute')

# The guest process ends during the load.
ce, ke, me = c['guestExit'], k['guestExit'], m['guestExit']
for name, report in (('control guest exit', ce), ('candidate guest exit', ke)):
    clean(report, name)
    check(report['unregisterReturnMs'] >= report['loadEndMs'] and report['loadedEventSeen'] and report['state'] == 'Ready' and report['commands'] == 3 and
          report['firstCommandMs'] >= report['loadEndMs'] and report['cachesDisposed'] == 1,
          name + ': the process is unregistered after the loader, which reports its end; its commands follow the load')
check(ce['unregisterEnterMs'] >= ce['loadEndMs'], 'control: the guest process ends after the load')
check(ke['unregisterEnterMs'] < ke['loadEndMs'] - 300, 'candidate: the guest process ended during the load and its unregistration waited: ' +
      str((ke['unregisterEnterMs'], ke['unregisterReturnMs'], ke['loadEndMs'])))
check(me['unregisterReturnedDuringLoad'] is True and me['handlersRemovedDuringLoad'] == 1 and me['destroysQueuedDuringLoad'] == 1 and me['loadedEventSeen'] is False,
      'without the wait, the unregistration overtakes the loader and the gate sees it: ' + str({key: me[key] for key in NO_OVERTAKING}))

# The render worker failed during the load and something still holds the process.
cw, kw, mw = c['renderWorkerFailed'], k['renderWorkerFailed'], m['renderWorkerFailed']
for name, report in (('control failed render worker', cw), ('candidate failed render worker', kw)):
    clean(report, name)
    check(report['releaseReturnMs'] >= report['loadEndMs'] and report['cachesDisposed'] == 1 and report['destroysQueued'] == 1,
          name + ': the GPU is released after the loader ended: ' + str((report['releaseEnterMs'], report['releaseReturnMs'], report['loadEndMs'])))
check(cw['releaseEnterMs'] >= cw['loadEndMs'] and cw['guestThreadsRan'] == 0, 'control: the waiting guest thread ordered the release after the loader')
check(kw['releaseEnterMs'] < kw['loadEndMs'] - 100 and kw['guestThreadsRan'] == 1, 'candidate: the release itself waited for the loader: ' +
      str((kw['releaseEnterMs'], kw['loadEndMs'])))
check(mw['eventsDisposedDuringLoad'] >= 1 and mw['destroysQueuedDuringLoad'] == 1, 'without the wait, the release overtakes the loader and the gate sees it: ' +
      str({key: mw[key] for key in NO_OVERTAKING}))

# Fences: the CPU-side wait forced after two cancellations, on a 2 s load.
cq, kq = c['fenceDuringLoad'], k['fenceDuringLoad']
for name, case in (('control fences', cq), ('candidate fences', kq)):
    clean(case['report'], name)
    check(case['report']['loadMs'] >= 1900 and case['report']['state'] == 'Ready' and case['report']['commands'] == 3 and case['forced']['issuedMs'] < 400,
          name + ': the waits are issued early in a 2 s load: ' + str((case['report']['loadMs'], case['forced']['issuedMs'])))
    check(case['finite']['outcome'] == 'timedOut' and 280 <= case['finite']['elapsedMs'] <= 900 and case['finite']['loadRunningAtReturn'] is True,
          name + ': a finite guest timeout ends when the guest asked, during the load: ' + str(case['finite']['elapsedMs']))
    # Issued after the load: today's behaviour in both.
    check(case['later']['outcome'] == 'signalled' and 150 <= case['later']['elapsedMs'] <= 900 and case['later']['value'] == 1,
          name + ': after the load, an infinite wait is signalled when the syncpoint is incremented: ' + str(case['later']['elapsedMs']))
    check(case['laterNever']['outcome'] == 'timedOut' and 950 <= case['laterNever']['elapsedMs'] <= 1700 and case['laterNever']['value'] == 0,
          name + ': after the load, an infinite wait gives up after its 1 s clamp: ' + str(case['laterNever']['elapsedMs']))
    check(case['laterFinite']['outcome'] == 'timedOut' and 280 <= case['laterFinite']['elapsedMs'] <= 900, name + ': after the load, a finite timeout')
    check(case['laterIdle']['outcome'] == 'Idle' and 90 <= case['laterIdle']['elapsedMs'] <= 700 and
          case['laterBusy']['outcome'] == 'NoProgress' and 290 <= case['laterBusy']['elapsedMs'] <= 1100,
          name + ': after the load, the progress-aware wait gives up idle after a slice and without progress after its limit: ' +
          str((case['laterIdle'], case['laterBusy'])))
for wait in ('later', 'laterNever', 'laterFinite', 'laterIdle', 'laterBusy', 'finite'):
    check(cq[wait]['outcome'] == kq[wait]['outcome'] and abs(cq[wait]['elapsedMs'] - kq[wait]['elapsedMs']) <= 300,
          wait + ': the same in control and candidate: ' + str((cq[wait]['elapsedMs'], kq[wait]['elapsedMs'])))
end = kq['report']['loadEndMs']
check(cq['forced']['outcome'] == 'timedOut' and 950 <= cq['forced']['elapsedMs'] <= 1700 and cq['forced']['loadRunningAtReturn'] is True and
      cq['forced']['commandsAtReturn'] == 0 and cq['forced']['value'] == 0,
      'control: the forced wait gives up after its clamp during the load, with nothing processed: ' + str(cq['forced']))
check(kq['forced']['outcome'] == 'signalled' and end <= kq['forced']['returnedMs'] <= end + 500 and kq['forced']['loadRunningAtReturn'] is False and
      kq['forced']['commandsAtReturn'] >= 1 and kq['forced']['value'] >= 1,
      'candidate: the forced wait returns once the load has ended and the syncpoint was incremented, signalled: ' + str((kq['forced'], end)))
check(cq['never']['outcome'] == 'timedOut' and 950 <= cq['never']['elapsedMs'] <= 1700 and cq['never']['loadRunningAtReturn'] is True,
      'control: a wait never signalled gives up 1 s after it was issued, during the load')
check(kq['never']['outcome'] == 'timedOut' and end + 950 <= kq['never']['returnedMs'] <= end + 1800 and kq['never']['value'] == 0,
      'candidate: a wait never signalled gives up 1 s after the load ended: ' + str((kq['never']['returnedMs'], end)))
check(cq['idle']['outcome'] == 'Idle' and cq['idle']['elapsedMs'] <= 700 and cq['busy']['outcome'] == 'NoProgress' and cq['busy']['elapsedMs'] <= 1100 and
      cq['idle']['loadRunningAtReturn'] is True and cq['busy']['loadRunningAtReturn'] is True and cq['idle']['value'] == 0,
      'control: the progress-aware wait gives up during the load, as idle or without progress: ' + str((cq['idle'], cq['busy'])))
check(all(kq[wait]['outcome'] == 'Reached' and end <= kq[wait]['returnedMs'] <= end + 500 and kq[wait]['value'] >= 1 and
          kq[wait]['loadRunningAtReturn'] is False for wait in ('idle', 'busy')),
      'candidate: the progress-aware wait treats the load as progress pending and reaches the fence after it: ' + str((kq['idle'], kq['busy'], end)))
check(cq['errorsDuringLoad'] == 3 and kq['errorsDuringLoad'] == 2 and cq['report']['errorLines'] == 5 and kq['report']['errorLines'] == 4,
      'one "took more than" line per wait that gave up: ' + str((cq['errorsDuringLoad'], kq['errorsDuringLoad'], cq['report']['errorLines'], kq['report']['errorLines'])))
held = [line for line in kq['report']['journal'] if line.startswith('launch syncpointWaitHeldForShaderLoad ')]
check(cq['report']['journal'] == [] and len(kq['report']['journal']) == 2 and len(held) == 1 and ' for threshold 1 held ' in held[0] and
      'while the disk shader cache loaded' in held[0],
      'candidate: one journal line for the first wait held beyond the former clamp: ' + str(kq['report']['journal']))

# A stop while waits are parked; the loader takes 500 ms to unwind.
cx, kx = c['fenceCancel'], k['fenceCancel']
for name, case in (('control fence stop', cx), ('candidate fence stop', kx)):
    clean(case['report'], name)
    check(case['report']['state'] == 'Cancelled' and case['report']['loadEndMs'] - case['cancelMs'] >= 480,
          name + ': the loader ends 500 ms after the stop: ' + str((case['cancelMs'], case['report']['loadEndMs'])))
    check(case['afterCancel']['outcome'] == 'timedOut' and 950 <= case['afterCancel']['elapsedMs'] <= 1700 and
          case['afterCancel']['issuedMs'] >= case['report']['loadEndMs'], name + ': a wait issued after a cancelled load is the 1 s one: ' +
          str(case['afterCancel']['elapsedMs']))
check(cx['parked']['outcome'] == 'timedOut' and 950 <= cx['parked']['elapsedMs'] <= 1700 and cx['parkedProgressing']['outcome'] == 'NoProgress',
      'control: the parked waits end by their clamp and their no-progress limit')
check(kx['parked']['outcome'] == 'timedOut' and 0 <= kx['parked']['returnedMs'] - kx['cancelMs'] <= 250 and kx['parked']['loadRunningAtReturn'] is True and
      kx['parked']['value'] == 0, 'candidate: the stop wakes the parked wait within a slice, unsignalled, while the loader still unwinds: ' +
      str((kx['parked']['returnedMs'], kx['cancelMs'], kx['report']['loadEndMs'])))
check(kx['parkedProgressing']['outcome'] == 'Cancelled' and 0 <= kx['parkedProgressing']['returnedMs'] - kx['cancelMs'] <= 250,
      'candidate: the stop ends the parked progress-aware wait within its poll: ' + str((kx['parkedProgressing']['returnedMs'], kx['cancelMs'])))

# The loader fails while a wait is parked.
cy, ky = c['fenceFailure'], k['fenceFailure']
for name, case in (('control fence failure', cy), ('candidate fence failure', ky)):
    clean(case['report'], name, failure='InvalidOperationException')
    check(case['report']['state'] == 'Failed' and case['parked']['outcome'] == 'timedOut' and case['parked']['value'] == 0, name + ': the wait ends unsignalled')
check(950 <= cy['parked']['elapsedMs'] <= 1700, 'control: after its clamp')
check(0 <= ky['parked']['returnedMs'] - ky['report']['loadEndMs'] <= 250 and ky['parked']['elapsedMs'] < 900,
      'candidate: a failed loader ends the parked wait as soon as it has ended: ' + str((ky['parked']['returnedMs'], ky['report']['loadEndMs'])))

# 4. 200 launches with randomized delays.
ZERO = ('commandsDuringLoad', 'commandsWithPartialTable', 'commandsWithoutReady', 'forbiddenGuestRuns', 'guestRanAfterCancelBeforeLoader',
        'guestStartsBeforeSnapshot', 'guestStartsBeforeHostInitialized', 'unregisterReturnedDuringLoad', 'blockedThreads', 'unexpectedFailures',
        'readyMismatch') + NO_OVERTAKING
for name, race in (('control', c['race']), ('candidate', k['race'])):
    check(race['iterations'] == 200 and race['seed'] == SEED and all(count > 0 for count in race['perMode'].values()) and len(race['perMode']) == 5,
          name + ': 200 randomized launches over the five cases: ' + str(race['perMode']))
    check(all(race[key] == 0 for key in ZERO), name + ': no ordering fault in 200 randomized launches: ' + str({key: race[key] for key in ZERO if race[key]}))
    check(race['launchesWithCommands'] >= 20, name + ': GPU commands were processed in the launches that became ready: ' + str(race['launchesWithCommands']))
check(c['race']['guestStartsBeforeLoadEnded'] == 0 and c['race']['launchesWithGuestBeforeLoadEnd'] == 0 and c['race']['journalLines'] == 0,
      'control: the guest never starts before the load ended')
check(k['race']['launchesWithGuestBeforeLoadEnd'] >= 40 and k['race']['journalLines'] >= k['race']['launchesWithGuestBeforeLoadEnd'],
      'candidate: the guest started before the load ended in many of the launches, one journal line each: ' +
      str((k['race']['launchesWithGuestBeforeLoadEnd'], k['race']['journalLines'])))

# Static: the hunks, and what the change relies on.
ck, kk = texts['control'], texts['candidate']
removed = {GPU: ['            Synchronization = new SynchronizationManager();',
                 '                    foreach (PhysicalMemory physicalMemory in PhysicalMemoryRegistry.Values)'],
           SYNC: ['                    if (System.Diagnostics.Stopwatch.GetElapsedTime(start) >= totalCap)'],
           PROCESS: ['            // We must wait until shader cache is loaded, among other things, before executing CPU code.',
                     '            if (!_gpuContext.WaitUntilGpuReady())']}
for name, pairs in FILE_PAIRS.items():
    before, after = ck[name].splitlines(), kk[name].splitlines()
    gone, added = [], 0
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, before, after, autojunk=False).get_opcodes():
        if tag in ('delete', 'replace'):
            gone += before[i1:i2]
        if tag in ('insert', 'replace'):
            added += j2 - j1
    check(gone == removed[name], name + ': the only lines removed are the replaced ones: ' + str(gone))
    check(added == sum(len(new.splitlines()) - len(old.splitlines()) for old, new in pairs) + len(gone), name + ': the lines added are the hunks\'')
    rebuilt = kk[name]
    for old, new in pairs:
        check(rebuilt.count(new) == 1, name + ': each hunk is present once')
        rebuilt = rebuilt.replace(new, old)
    check(rebuilt == ck[name], name + ': unchanged except for the hunks')
    check(not re.search(r'TitleId|ProgramId|PaceStrictHostSyncs|0100[0-9A-Fa-f]{12}', ''.join(new for _, new in pairs)), name + ': no per-title condition')
check(ck[MEMORY] == kk[MEMORY], 'PhysicalMemory unchanged')

gpu = kk[GPU]
initialize = member(gpu, 'public bool InitializeShaderCache(')
i = initialize.index
check(i('WaitHandle.WaitAny(new[] { HostInitalized, token.WaitHandle });') < i('ICollection<PhysicalMemory> physicalMemories = PhysicalMemoryRegistry.Values;') <
      i('ReleaseGuestForShaderLoad(physicalMemories.Count);') < i('foreach (PhysicalMemory physicalMemory in physicalMemories)') <
      i('physicalMemory.ShaderCache.Initialize(token);') < i('finally') < i('_gpuInitializationState = outcome;'),
      'the guest is released after the host is initialized and the snapshot taken, before the first cache loads')
check(initialize.count('PhysicalMemoryRegistry') == 1, 'the loader reads the registry once')
cancel = member(gpu, 'public void CancelShaderCacheInitialization()')
check(gpu.count('_gpuReadyEvent.Set();') == 2 and gpu.count('_guestStartEvent.Set();') == 3 and
      i('_gpuInitializationState = outcome;') < i('_guestStartEvent.Set();') < i('_gpuReadyEvent.Set();') and
      cancel.index('GpuInitializationState.Cancelled;') < cancel.index('_guestStartEvent.Set();') < cancel.index('_gpuReadyEvent.Set();') and
      gpu.count('_gpuReadyEvent.Dispose();\n            _guestStartEvent.Dispose();') == 1,
      'the guest event is set on every terminal path, before the ready event, and disposed with it')
check(re.search(r'_gpuReadyEvent\.Set\(\);\s*\}\s*\}\s*return outcome == GpuInitializationState\.Ready;\s*\}\Z', initialize) is not None,
      'the ready event is the loader\'s last use of the context: a release that waited for it disposes nothing the loader still touches')
release = member(gpu, 'private void ReleaseGuestForShaderLoad(')
check(release.index('if (_gpuInitializationCancellationRequested)') < release.index('_guestStartEvent.Set();') and 'lock (_gpuInitializationLock)' in release,
      'a requested cancellation keeps the guest waiting for the terminal state')
start = member(gpu, 'public bool WaitUntilGuestMayStart()')
lock = member(start, 'lock (_gpuInitializationLock)')
check(start.index('_guestStartEvent.WaitOne();') < start.index('lock (_gpuInitializationLock)') and
      'GpuInitializationState.Ready' in lock and 'GpuInitializationState.Initializing || _gpuInitializationCancellationRequested' in lock,
      'the guest may start when ready, or while a loader runs with no cancellation requested')
check('Record(' not in lock and gpu.count('"guestStartedDuringShaderLoad"') == 1 and
      start.index('Interlocked.Exchange(ref _guestStartJournaled, 1) == 0') < start.index('EmbeddedLaunchDiagnostics.Record("launch", "guestStartedDuringShaderLoad"'),
      'one journal line per context, outside the state lock')
wait = member(gpu, 'private void WaitForShaderCacheLoader()')
check('WaitOne' not in member(wait, 'lock (_gpuInitializationLock)') and wait.index('lock (_gpuInitializationLock)') < wait.index('if (loading)') <
      wait.index('_gpuReadyEvent.WaitOne();'), 'the wait for the loader is outside the state lock')
unregister, dispose = member(gpu, 'public void UnregisterProcess('), member(gpu, 'public void Dispose()')
check(unregister.index('WaitForShaderCacheLoader();') < unregister.index('PhysicalMemoryRegistry.TryRemove(') and
      dispose.index('WaitForShaderCacheLoader();') < dispose.index('foreach (var cache in _counterReportCaches)') < dispose.index('_gpuReadyEvent.Dispose();'),
      'UnregisterProcess and Dispose wait for the loader before anything else')
for signature in ('public bool WaitUntilGpuReady()', 'public void RegisterProcess(', 'internal void RunDeferredActions()'):
    check(member(ck[GPU], signature) == member(gpu, signature), signature + ' unchanged')
check(callers['control']['WaitUntilGpuReady'] == sorted((GPU, PROCESS)) and callers['candidate']['WaitUntilGpuReady'] == [GPU],
      'WaitUntilGpuReady had one caller, ArmProcessContext.Execute, and has none left: ' + str(callers['candidate']['WaitUntilGpuReady']))
check(callers['candidate']['WaitUntilGuestMayStart'] == sorted((GPU, PROCESS)) and kk[PROCESS].count('WaitUntilGuestMayStart(') == 1 and
      'WaitUntilGuestMayStart' in member(kk[PROCESS], 'public void Execute(') and callers['candidate']['WaitForShaderCacheLoader'] == [GPU],
      'the new wait is called by ArmProcessContext.Execute only, once per guest thread start')
check(callers['candidate']['RunDeferredActions'] == sorted((GPU, 'src/Ryujinx.Graphics.Gpu/Engine/GPFifo/GPFifoDevice.cs')),
      'queued destructions run on the GPU thread\'s dispatch only')
memory_dispose = member(kk[MEMORY], 'public void Dispose()')
check('_context.DeferredActions.Enqueue(Destroy);' in memory_dispose and 'ShaderCache' not in memory_dispose and
      'ShaderCache.Dispose();' in member(kk[MEMORY], 'private void Destroy()'), 'PhysicalMemory.Dispose queues the caches\' destruction for the GPU thread')
check('_gpuContext.UnregisterProcess(_pid);' in member(kk[PROCESS], 'public void Dispose()'), 'a destroyed process unregisters its memory')
# The fences.
sync = kk[SYNC]
phase = member(gpu, 'internal SynchronizationManager.ShaderLoadPhase GetShaderLoadPhase()')
check('lock (_gpuInitializationLock)' in phase and
      '_gpuInitializationState == GpuInitializationState.Initializing && !_gpuInitializationCancellationRequested' in phase and
      phase.count('ShaderLoadPhase.Running') == 1 and phase.count('ShaderLoadPhase.Ready') == 1 and phase.count('ShaderLoadPhase.None') == 1,
      'Running only while a loader runs with no cancellation requested, Ready once ready, None otherwise')
check(gpu.count('new SynchronizationManager(') == 1 and 'Synchronization = new SynchronizationManager(GetShaderLoadPhase);' in gpu and
      'internal SynchronizationManager(Func<ShaderLoadPhase> shaderLoadPhase) : this()' in sync, 'the manager is given the phase at construction, a delegate')
loading = member(sync, 'private bool ShaderCacheLoading()')
check(loading.index('_shaderLoadPhase == null || Volatile.Read(ref _shaderLoadOver)') < loading.index('_shaderLoadPhase();') <
      loading.index('Volatile.Write(ref _shaderLoadOver, true);') and 'return phase == ShaderLoadPhase.Running;' in loading,
      'once the load has ended ready, the question is one volatile read for the rest of the session')
wait_on = member(sync, 'public bool WaitOnSyncpoint(')
infinite = member(wait_on, 'if (timeout == Timeout.InfiniteTimeSpan)')
check(wait_on.count('ShaderCacheLoading()') == 1 and 'duringShaderLoad = ShaderCacheLoading();' in infinite and 'timeout = TimeSpan.FromSeconds(1);' in infinite and
      wait_on.index('if (duringShaderLoad && !WaitWhileShaderCacheLoads(id, threshold, waitEvent))') < wait_on.index('bool signaled = waitEvent.WaitOne(timeout);'),
      'only an infinite wait asks, and the usual clamped wait follows the load')
stripped = wait_on.replace(FILE_PAIRS[SYNC][1][1], FILE_PAIRS[SYNC][1][0])
check(stripped == member(ck[SYNC], 'public bool WaitOnSyncpoint('), 'WaitOnSyncpoint is the control\'s but for the wait during the load')
parked = member(sync, 'private bool WaitWhileShaderCacheLoads(')
check('private const int ShaderLoadWaitSliceMs = 50;' in sync and
      'while (phase == ShaderLoadPhase.Running && !waitEvent.WaitOne(ShaderLoadWaitSliceMs))' in parked and 'return phase != ShaderLoadPhase.None;' in parked and
      sync.count('"syncpointWaitHeldForShaderLoad"') == 1 and 'Interlocked.Exchange(ref _shaderLoadWaitJournaled, 1) == 0' in parked,
      'the parked wait asks every 50 ms and journals once')
progressing = sync[sync.index('        public ProgressWaitOutcome WaitOnSyncpointWhileProgressing(uint id, uint threshold, TimeSpan slice, TimeSpan noProgressLimit,\n            TimeSpan totalCap,'):]
progressing = member('\n' + progressing, 'public ProgressWaitOutcome WaitOnSyncpointWhileProgressing(')
j = progressing.index
check(j('bool shaderLoad = ShaderCacheLoading();') < j('if (cancelled())') < j('if (phase == ShaderLoadPhase.None)') < j('if (phase == ShaderLoadPhase.Ready)') <
      j('sliceStart = lastProgress = capStart = System.Diagnostics.Stopwatch.GetTimestamp();') < j('if (nowValue >= threshold)') <
      j('continue; // RewindBox (adapt_guest_start_during_shader_load): loading is progress pending') <
      j('if (System.Diagnostics.Stopwatch.GetElapsedTime(capStart) >= totalCap)') < j('else if (gpuIdle())') < j('ProgressWaitOutcome.NoProgress'),
      'the progress-aware wait: no cap, idle or no-progress fallback while the load runs; its clocks restart when it ended ready')
check(callers['candidate']['GetShaderLoadPhase'] == [GPU] and callers['candidate']['WaitOnSyncpoint'] == callers['control']['WaitOnSyncpoint'] == sorted((
          SYNC, 'src/Ryujinx.Graphics.Device/ISynchronizationManager.cs', 'src/Ryujinx.Graphics.Gpu/Engine/GPFifo/GPFifoClass.cs',
          'src/Ryujinx.Graphics.Host1x/Host1xClass.cs', 'src/Ryujinx.HLE/HOS/Services/Nv/Types/NvFence.cs')) and
      callers['candidate']['WaitOnSyncpointWhileProgressing'] == sorted((SYNC, 'src/Ryujinx.HLE/HOS/Services/Nv/NvDrvServices/NvHostCtrl/Types/NvHostEvent.cs')),
      'the waiters are the known ones: ' + str((callers['candidate']['WaitOnSyncpoint'], callers['candidate']['WaitOnSyncpointWhileProgressing'])))

window = read(FINAL_SOURCE, WINDOW)
w = window.index
check(w('Device.Gpu.SetGpuThread();') < w('bool gpuReady = Device.Gpu.InitializeShaderCache(_gpuCancellationTokenSource.Token);') <
      w('while (gpuReady && _embeddedLifetime.RenderAllowed)') < w('Device.ProcessFrame();') < w('Device.PresentLoop(SwapBuffers)') <
      w('_embeddedLifetime.NotifyRenderDrained();'), 'the GPU thread processes its first command only after InitializeShaderCache returned true')
check(w('Device.Gpu.CancelShaderCacheInitialization();') < w('_gpuCancellationTokenSource.Cancel();') < w('Device.System.Dispose();') <
      w('Device.DisposeGpu();'), 'the stop requests the cancellation before it terminates the guest, and releases the GPU last')
lifetime = read(FINAL_SOURCE, LIFETIME)
check(lifetime.index('try { stopGuest(); }') < lifetime.index('_renderDrained.Wait();') < lifetime.index('try { releaseGpu(); }'),
      'the GPU is released after the render loop reported its drain')

inputs = ['build-utils/melonx/adapt_guest_start_during_shader_load.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_guest_start_during_shader_load_test.py', 'test/melonx_guest_start_during_shader_load/Double.cs',
          'test/melonx_guest_start_during_shader_load/Program.cs']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION, physicalDeviceTested=False,
               sourceKind='finalPreparationWithReversedControl',
               postimages={p: hashlib.sha256((FINAL_SOURCE / p).read_bytes()).hexdigest() for p in BASELINE},
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               reports=reports, sdk=sdk, seed=SEED, sourceBaseline=BASELINE, productionAssembliesBuilt=builds,
               callers=callers['candidate'], shaderCacheLoaderDouble=True,
               limitation='Host threads with a loader double of 600 ms (2 s for the fences, 2 ms per program in the randomized launches) and a guest double; '
                          'the launch time on an iPhone, the load\'s length while the guest boots, and what a title does while its GPU '
                          'commands wait for the end of the load are known only from a device run.')
out = ROOT / 'dist/melonx/guest-start-during-shader-load-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk, seed=SEED)))
