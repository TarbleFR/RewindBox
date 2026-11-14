#!/usr/bin/env python3
"""adapt_host_thread_class on the final preparation, against the Core 731 preparation as control.

Usage: melonx_host_thread_class_test.py <Core 731 prepared tree>
       melonx_host_thread_class_test.py <control> --candidate-source <final preparation containing the adapter>

IPA 725, Hogwarts Legacy (pid 51986; private journals, aggregates only): the guest's threads run at base priority 31
and spend 20 to 35 % of their CPU time on performance cores in the stretches at 20 FPS; the engine's render and GPU
threads, raised to the user-interactive class since Core 609, run at 47 and spend 80 to 97 % there.

Static: the control is the Core 731 set of eight files; the candidate differs by the adapter's nine replacements (the
helper in NanosleepPool.cs, and the call as the first statement of eight thread bodies); the bodies are the entry points
of the threads named; nothing else in the tree calls the helper; HostThreadQos is unchanged.
Executed: the production Ryujinx.HLE project (with Ryujinx.Audio and Ryujinx.Common) is built from the control and from
the candidate. test/melonx_host_thread_class/Program.cs loads the side's assemblies and runs each real thread body on
its own thread (on an uninitialized object: the first statements run, then the body ends as the control's does):
- candidate: every one of the eight bodies asks the user-interactive class (0x21, relative priority 0) once, on its own
  thread; the control asks nothing and ends the same way;
- the helper: nothing asked when the platform is not Apple's; a refusal leaves the thread as it is and is recorded once
  in the engine journal for any number of refusals; a missing library or entry point is not an error;
- on macOS (the Core gates' host) the engine's own call is made and the thread's class read back from the system:
  the answer must agree with the class. The fixture's host runtime (CoreCLR) keeps its own threads outside the
  system's classes (class 0) and the system then refuses them (EPERM; Core CI run 42999377576, run 43008139574), so
  the acceptance is established where the Core's threads are: test/melonx_host_thread_class_system_test.py is run
  here, and must pass (the adapter's helper on a system thread, and on the threads of the same fixture compiled with
  NativeAOT, the kind of runtime the Core is delivered with: all in class 0x21 after the call, nothing recorded).
Sensitivity: with another class in the helper, without the platform test, and with the control's Ryujinx.HLE beside the
candidate's other assemblies, the fixture must report it.
Not an iPhone: which cores then serve the threads, and what the frame gains, are read in the next session's cpu=, pc=
and hw= fields. Writes dist/melonx/host-thread-class-checks.json.
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
CONTROL_SOURCE, FINAL_PREPARATION = control_source(FINAL_SOURCE, 'adapt_host_thread_class', _HOLD)
import adapt_host_thread_class as adapter  # noqa: E402

DOTNET = os.environ.get('DOTNET', 'dotnet')
HARNESS = ROOT / 'test/melonx_host_thread_class'
RENDERER = 'src/Ryujinx.Graphics.GAL/Multithreading/ThreadedRenderer.cs'
# (file, the body's signature, how the file starts the thread on it, the thread's name in the fixture's report)
SITES = (
    (adapter.SLEEP, '            private void Loop()', '_thread = new Thread(Loop)', 'Common.Nanosleep.N'),
    (adapter.THREAD, '        private void ThreadStart()', 'HostThread = new Thread(ThreadStart) { Name = "HLE.KThread" };', 'guest and HLE service threads'),
    (adapter.TIMER, '        private void WaitAndCheckScheduledObjects()', 'Thread work = new(WaitAndCheckScheduledObjects)', 'HLE.TimeManager'),
    (adapter.KERNEL, '            void PreemptionThreadStart()', 'new Thread(PreemptionThreadStart) { Name = "HLE.PreemptionThread" }.Start();', 'HLE.PreemptionThread'),
    (adapter.FLINGER, '        private void HandleComposition()', '_composerThread = new Thread(HandleComposition)', 'SurfaceFlinger.Composer'),
    (adapter.PROCESSOR, '        private void Work()', '_workerThread = new Thread(Work)', 'AudioProcessor.Worker'),
    (adapter.RENDERER, '        private void SendCommands()', '_workerThread = new Thread(SendCommands)', 'AudioRendererManager.Worker'),
    (adapter.MANAGER, '        private void Update()', '_workerThread = new Thread(Update)', 'AudioManager.Worker'),
)
INTERACTIVE = [[0x21, 0]]
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
    assert source.count(signature) == 1, signature
    start = source.rindex('\n', 0, source.index(signature)) + 1
    depth, index = 0, source.index('{', start)
    for index in range(index, len(source)):
        depth += (source[index] == '{') - (source[index] == '}')
        if depth == 0:
            return source[start:index + 1]
    raise AssertionError(signature)


# --- Static: the exact scope ---
check(FINAL_PREPARATION, 'the source given is a final preparation containing the adapter')
# Core 747: adapt_wait_spin_bound changes the scheduler event's type in KThread.cs (and the renderer's two events) after
# this adapter; its gate (wait-spin-bound) binds those replacements, which are undone here before the comparisons.
import adapt_wait_spin_bound as _spin  # noqa: E402
# IPA 736 lot: adapt_timer_earliest_wake edits KTimeManager.cs after this adapter (when the timer thread is signalled);
# its replacements are undone here too.
import adapt_timer_earliest_wake as _timer  # noqa: E402
check(files_edited_later('adapt_host_thread_class') == {_spin.THREAD, _timer.MANAGER},
      'the only later edits of these files are adapt_wait_spin_bound\'s, in KThread.cs, and adapt_timer_earliest_wake\'s, in KTimeManager.cs')


def without_later(name, source):
    for old, new in reversed(tuple(_spin.FILE_PAIRS.get(name, ())) + (tuple(_timer.PAIRS) if name == _timer.MANAGER else ())):
        check(source.count(new) == 1, 'the later adapter\'s replacement, once: ' + new.strip().splitlines()[0][:60])
        source = source.replace(new, old)
    return source


control = {name: text(CONTROL_SOURCE, name) for name in adapter.BASELINE}
final = {name: without_later(name, text(FINAL_SOURCE, name)) for name in adapter.BASELINE}
for name, expected in adapter.BASELINE.items():
    check(sha(CONTROL_SOURCE / name) == expected, 'control is the Core 731 preparation: ' + name)
    rebuilt = control[name]
    for file, old, new in adapter.PAIRS:
        if file == name:
            check(rebuilt.count(old) == 1, 'one site in the control: ' + name)
            rebuilt = rebuilt.replace(old, new)
    check(rebuilt == final[name], name + ' is the control plus the adapter\'s replacements')
check(len(adapter.PAIRS) == 9 and len(adapter.SITES) == len(SITES) == 8 and [site[0] for site in adapter.SITES] == [site[0] for site in SITES],
      'nine replacements: the helper and one call in each of the eight files')
for name, signature, start, thread in SITES:
    before, after = member(control[name], signature), member(final[name], signature)
    brace = before.index('{\n') + 2
    indent = before[brace:len(before) - len(before[brace:].lstrip(' '))]
    check(after == before[:brace] + indent + adapter.CALL + before[brace:], thread + ': the call is the body\'s first statement and its only change')
    check(final[name].count(start) == 1 and control[name].count(start) == 1, thread + ': the body is the entry point of the thread the file starts')
sources = list((FINAL_SOURCE / 'src').rglob('*.cs'))
calls = sum(path.read_text(encoding='utf-8-sig', errors='replace').count('HostThreadClass.RaiseCurrentThread()') for path in sources)
declared = sum(path.read_text(encoding='utf-8-sig', errors='replace').count('class HostThreadClass') for path in sources)
check(calls == 8 and declared == 1, 'the tree calls the helper from these eight bodies only and declares it once')
block = final[adapter.SLEEP][final[adapter.SLEEP].index(adapter.HELPER_BEGIN):final[adapter.SLEEP].index(adapter.HELPER_END)]
renderer = without_later(RENDERER, text(FINAL_SOURCE, RENDERER))
check('public const uint UserInteractive = 0x21;' in block and 'private const uint UserInteractive = 0x21;' in renderer and
      'EntryPoint = "pthread_set_qos_class_self_np"' in block and 'EntryPoint = "pthread_set_qos_class_self_np"' in renderer and
      'result = SetClass(UserInteractive, 0);' in block,
      'the class and the call are those of the render and GPU threads (HostThreadQos)')
check(renderer == text(CONTROL_SOURCE, RENDERER) and renderer.count('HostThreadQos.RaiseCurrentThread();') >= 1, 'HostThreadQos and its callers are unchanged')
check(block.count('ApplePlatform = ') == 1 and block.count('SetClass = ') == 1 and
      sum(path.read_text(encoding='utf-8-sig', errors='replace').count('HostThreadClass.SetClass') +
          path.read_text(encoding='utf-8-sig', errors='replace').count('HostThreadClass.ApplePlatform') for path in sources) == 0,
      'the two seams are assigned where they are declared and nowhere in the engine')
drift = Path(tempfile.mkdtemp(prefix='melonx-host-thread-class-drift-'))
for name in adapter.BASELINE:
    (drift / name).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(CONTROL_SOURCE / name, drift / name)
(drift / adapter.MANAGER).write_bytes((drift / adapter.MANAGER).read_bytes() + b'\n// unreviewed drift\n')
try:
    adapter.apply(drift)
    refused = False
except AssertionError:
    refused = True
shutil.rmtree(drift)
check(refused, 'a drifted AudioManager.cs is refused')

# --- Executed: the real assemblies of both sides ---
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1')
WORK = Path(tempfile.mkdtemp(prefix='melonx-host-thread-class-')).resolve()


def build(tree, project, what):
    # The package assemblies (LibHac and others) are copied beside the project's: the fixture loads the closure from there.
    result = subprocess.run([DOTNET, 'build', str(tree / project), '-c', 'Release', '-nologo', '-m:1', '-p:NuGetAudit=false',
                             '-p:CopyLocalLockFileAssemblies=true'],
                            capture_output=True, text=True, timeout=2400, env=environment, cwd=tree)
    if result.returncode:
        print('\n'.join(line for line in result.stdout.splitlines() if ': error ' in line)[:6000], result.stderr[-2000:], flush=True)
    check(result.returncode == 0, what + ' builds')


outputs = {}
for side, source in (('control', CONTROL_SOURCE), ('candidate', FINAL_SOURCE)):
    tree = WORK / side
    shutil.copytree(source, tree, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
    use_authenticated_libhac_feed(tree, ROOT)
    build(tree, 'src/Ryujinx.HLE/Ryujinx.HLE.csproj', side + ': production Ryujinx.HLE (with Ryujinx.Audio and Ryujinx.Common)')
    outputs[side] = tree / 'src/Ryujinx.HLE/bin/Release/net10.0'
    check(all((outputs[side] / (name + '.dll')).is_file() for name in ('Ryujinx.HLE', 'Ryujinx.Audio', 'Ryujinx.Common')), side + ': the three assemblies are built')
    print(side + ': production Ryujinx.HLE built', flush=True)

# Sensitivity: the candidate's helper altered (Ryujinx.Common rebuilt alone), and the control's HLE beside the candidate's others.
tree = WORK / 'candidate'
helper_path = tree / adapter.SLEEP
helper = helper_path.read_text(encoding='utf-8')
for variant, old, new in (('wrongClass', 'public const uint UserInteractive = 0x21;', 'public const uint UserInteractive = 0x19;'),
                          ('noPlatformTest', '            if (!ApplePlatform())\n', '            if (false)\n')):
    check(helper.count(old) == 1, variant + ': one site to alter')
    helper_path.write_text(helper.replace(old, new), encoding='utf-8')
    build(tree, 'src/Ryujinx.Common/Ryujinx.Common.csproj', variant + ': Ryujinx.Common')
    outputs[variant] = WORK / variant
    shutil.copytree(outputs['candidate'], outputs[variant])
    shutil.copyfile(tree / 'src/Ryujinx.Common/bin/Release/net10.0/Ryujinx.Common.dll', outputs[variant] / 'Ryujinx.Common.dll')
helper_path.write_text(helper, encoding='utf-8')
outputs['hleWithoutCalls'] = WORK / 'hleWithoutCalls'
shutil.copytree(outputs['candidate'], outputs['hleWithoutCalls'])
shutil.copyfile(outputs['control'] / 'Ryujinx.HLE.dll', outputs['hleWithoutCalls'] / 'Ryujinx.HLE.dll')

fixture = WORK / 'fixture'
fixture.mkdir()
shutil.copyfile(HARNESS / 'Program.cs', fixture / 'Program.cs')
(fixture / 'Fixture.csproj').write_text(
    '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
    '<Nullable>disable</Nullable><NuGetAudit>false</NuGetAudit><NoWarn>CS0649;CS0414;CS0169;CS8632</NoWarn></PropertyGroup></Project>\n')
result = subprocess.run([DOTNET, 'build', str(fixture / 'Fixture.csproj'), '-c', 'Release', '-nologo', '-p:NuGetAudit=false'],
                        capture_output=True, text=True, timeout=900, env=environment, cwd=fixture)
if result.returncode:
    print('\n'.join(line for line in result.stdout.splitlines() if ': error ' in line)[:6000], flush=True)
check(result.returncode == 0, 'the fixture builds')
reports = {}
for variant, directory in outputs.items():
    run = subprocess.run([DOTNET, str(fixture / 'bin/Release/net10.0/Fixture.dll'), str(directory), variant],
                         capture_output=True, text=True, timeout=900, env=environment, cwd=fixture)
    if run.returncode:
        print(run.stdout[-4000:], run.stderr[-4000:], flush=True)
    check(run.returncode == 0, variant + ' fixture runs')
    reports[variant] = json.loads(run.stdout.strip().splitlines()[-1])
shutil.rmtree(WORK)
if os.environ.get('MELONX_TEST_REPORTS'):
    Path(os.environ['MELONX_TEST_REPORTS']).write_text(json.dumps(reports, indent=1))
c, k = reports['control'], reports['candidate']
threads = [site[3] for site in SITES]

# Every thread body: the candidate asks the class once, on its own thread; the control asks nothing; both end alike.
check(sorted(k['sites']) == sorted(c['sites']) == sorted(threads) and k['helper'] and not c['helper'], 'the eight bodies ran on both sides; only the candidate has the helper')
for thread in threads:
    site_k, site_c = k['sites'][thread], c['sites'][thread]
    check(site_k['requests'] == INTERACTIVE and site_k['onItsOwnThread'], 'candidate: ' + thread + ' asks the user-interactive class once, for itself: ' + json.dumps(site_k))
    check(site_c['requests'] == [], 'control: ' + thread + ' asks nothing: ' + json.dumps(site_c))
    check(site_k['end'] == site_c['end'] and site_k['end'] not in ('timeout', 'method not found') and not site_k['end'].startswith('fixture') and
          site_k['method'] == site_c['method'], thread + ': the body ends as the control\'s does: ' + json.dumps([site_c, site_k]))
ends = {thread: k['sites'][thread]['end'] for thread in threads}
check(k['recordsAfterGrants'] == 0 and c['recordsAfterGrants'] == 0, 'a granted class writes no journal record')

# The helper.
check(k['granted']['value'] is True and k['granted']['requests'] == INTERACTIVE and k['granted']['end'] == 'returned', 'granted: true')
check(k['notApple']['value'] is False and k['notApple']['requests'] == [] and k['notApple']['end'] == 'returned',
      'another platform: nothing is asked, nothing changes')
check(len(k['refused']) == 3 and all(r['value'] is False and r['requests'] == INTERACTIVE and r['end'] == 'returned' for r in k['refused']) and
      k['recordsAfterRefusals'] == 1 and
      k['refusalRecords'] == ['refused 1: pthread_set_qos_class_self_np returned 1 on refused 0 (adapt_host_thread_class)'],
      'three refusals: false each time, one journal record naming the first thread: ' + json.dumps(k['refusalRecords']))
for name in ('libraryMissing', 'entryMissing'):
    check(k[name]['value'] is False and k[name]['end'] == 'returned' and k[name]['requests'] == INTERACTIVE, name + ': not an error')
own = k['ownSeams']
check(own['end'] == 'returned' and own['requests'] == [], 'the engine\'s own seams make the system call themselves')
system = None
if own['applePlatform']:
    check((own['value'] is True and own['classAfter'] == 0x21 and own['classBefore'] != 0x21) or
          (own['value'] is False and own['classAfter'] == own['classBefore'] == 0),
          'macOS: granted with the class read back, or refused to a thread the host runtime keeps outside the classes: ' + json.dumps(own))
    run = subprocess.run([sys.executable, str(ROOT / 'test/melonx_host_thread_class_system_test.py')], capture_output=True, text=True,
                         timeout=3600, env=dict(os.environ, DOTNET=DOTNET))
    print(run.stdout[-4000:], run.stderr[-2000:], flush=True)
    check(run.returncode == 0, 'macOS: the helper against the system (melonx_host_thread_class_system_test.py) passes')
    system = json.loads((ROOT / 'dist/melonx/host-thread-class-system-checks.json').read_text())
    ahead = system['aheadOfTime']
    check(system['result'] == 'passed' and ahead['aheadOfTime'] is True and
          all(ahead[kind]['answer'] is True and ahead[kind]['classAfter'] == 0x21 for kind in ('systemThreadHelper', 'runtimeThreadHelper')) and
          ahead['records'] == [] and system['report']['systemThreadHelper']['classAfter'] == 0x21,
          'macOS: system threads and the ahead-of-time runtime\'s threads are in the user-interactive class after the helper: ' + json.dumps(ahead))
else:
    check(own['value'] is False and own['classAfter'] == 0, 'this host is not an Apple platform: nothing asked: ' + json.dumps(own))

# Sensitivity.
wrong, open_, mixed = reports['wrongClass'], reports['noPlatformTest'], reports['hleWithoutCalls']
check(all(wrong['sites'][thread]['requests'] == [[0x19, 0]] for thread in threads), 'sensitivity: another class in the helper is seen at every site')
check(open_['notApple']['requests'] == INTERACTIVE and open_['notApple']['value'] is True, 'sensitivity: without the platform test another platform is asked')
kernel = [site[3] for site in SITES if site[0].startswith('src/Ryujinx.HLE/')]
check(len(kernel) == 4 and all(mixed['sites'][thread]['requests'] == ([] if thread in kernel else INTERACTIVE) for thread in threads),
      'sensitivity: the control\'s Ryujinx.HLE beside the candidate\'s other assemblies: its four bodies ask nothing')

inputs = ['build-utils/melonx/adapt_host_thread_class.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_host_thread_class_test.py', 'test/melonx_host_thread_class/Program.cs', 'test/melonx_adapter_control.py',
          'test/melonx_host_thread_class_system_test.py', 'test/melonx_host_thread_class_system/Program.cs']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core731Preparation',
               postimages={p: sha(FINAL_SOURCE / p) for p in adapter.BASELINE} if FINAL_PREPARATION else {},
               productionHleBuilt=True,
               comparison=dict(threadBodies=len(threads), raisedControl=sum(1 for t in threads if c['sites'][t]['requests']),
                               raisedCandidate=sum(1 for t in threads if k['sites'][t]['requests'] == INTERACTIVE),
                               journalRecordsForThreeRefusals=k['recordsAfterRefusals'], sensitivityVariantsFailed=3),
               bodyEnds=ends, systemClassReadBack=bool(own['applePlatform']), system=system,
               reports=reports, sdk=sdk, host=platform.system(), physicalDeviceTested=False,
               deviceEvidence='IPA 725, Hogwarts Legacy, pid 51986 (private journals): <MainThread> at priority 31, 20 to 35 % of its CPU time on '
                              'performance cores in the stretches at 20 FPS and 61 % in the 20 s at 30 FPS; render and GPU threads at 47, 80 to '
                              '97 %; the process\'s threads wait for a core 1.4 to 1.8 times as long as they run',
               inputs={name: sha(ROOT / name) for name in inputs},
               limitation='The request is observed (and, on macOS, the class read back from the system); which cores then serve the threads, '
                          'the frame time and the heat are an iPhone\'s to show: cpu= priorities, pc=, hw=, dsp= and th= of the next session.')
out = ROOT / 'dist/melonx/host-thread-class-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
