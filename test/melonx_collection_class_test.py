#!/usr/bin/env python3
"""adapt_collection_class on the final preparation, against its predecessor as control.

Usage: melonx_collection_class_test.py <predecessor preparation> [--candidate-source <final preparation containing the adapter>]
       melonx_collection_class_test.py --emit-fixture <directory>   (the fixture's sources, for the macOS workflow)

IPA 729 Hogwarts Legacy: ephemeral collections that promote almost nothing stop the engine for hundreds of
milliseconds (gen0 363.9 ms for 2.2 MiB, 447.6 ms for 0.1 MiB, 720.6 ms for 1.1 MiB). A blocking collection runs on
the thread whose allocation triggered it; the guest's threads are user-interactive and run translated code a collection
does not stop; the other engine threads are in a lower class.

Static: only EmbeddedSession.cs changes, each replacement once and reversing to the control; the keep-alive still
requests one collection and the class requests none; the registration, the session mark and the journal line are each
inside their own catch; the poll's release is the first statement after the poll's sleep; every function the callouts
can reach is declared without a collector transition and is called once by Register before the callouts are
registered; the callouts contain no allocation, lock, string or exception.
Built: the production Ryujinx.Library of the candidate.
Executed (test/melonx_collection_class/Program.cs with the adapter's class text, unchanged):
- compiled ahead of time for the host (the Core's runtime kind), with the fixture's platform functions and the
  runtime's real collection callouts: a utility thread's 25 collections each raise that thread and none is left raised;
  user-interactive threads and threads outside the classes are never raised; three forced collections allocate 0 bytes
  on their thread; raising off: accounted, never raised; four threads of four classes for two seconds: every override
  started is ended, never two at once, and overrides left by collections that go on in the background are ended by
  the next collection or the background thread - or, with a poll as the keep-alive's, by the poll; a session mark
  restarts the totals;
- compiled ahead of time without the fixture's platform (not an Apple platform): nothing registered, collections run;
- on the just-in-time runtime, which has no such registration: refused, reported, collections run.
The Apple scheduler and the production QoS calls are exercised by the workflow melonx-collection-class.yml on macOS
arm64 (the same fixture, mode "apple"); this gate does not run them.
"""
from pathlib import Path
import hashlib, json, os, re, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
import adapt_collection_class as adapter  # noqa: E402

FIXTURE_PROJECT = (
    '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
    '<Nullable>disable</Nullable><AllowUnsafeBlocks>true</AllowUnsafeBlocks><PublishAot>true</PublishAot>'
    '<InvariantGlobalization>true</InvariantGlobalization><ServerGarbageCollection>false</ServerGarbageCollection>'
    '<ConcurrentGarbageCollection>true</ConcurrentGarbageCollection><NuGetAudit>false</NuGetAudit>'
    '<NoWarn>CA1416;CS8981</NoWarn></PropertyGroup></Project>\n')


def emit_fixture(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'CollectionClass.cs').write_text(adapter.CLASS, encoding='utf-8')
    shutil.copyfile(ROOT / 'test/melonx_collection_class/Program.cs', directory / 'Program.cs')
    (directory / 'Fixture.csproj').write_text(FIXTURE_PROJECT)


if '--emit-fixture' in sys.argv:
    emit_fixture(Path(sys.argv[sys.argv.index('--emit-fixture') + 1]).resolve())
    raise SystemExit(0)

SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
from melonx_adapter_control import control_source, files_edited_later  # noqa: E402
_HOLD = []
FINAL_SOURCE = SOURCE
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_collection_class', _HOLD)

DOTNET = os.environ.get('DOTNET', 'dotnet')
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(command, cwd, timeout=2400):
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, cwd=cwd,
                            env=dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1'))
    if result.returncode:
        print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
        raise SystemExit('FAILED: ' + ' '.join(str(part) for part in command[:4]))
    return result.stdout


def body(text, signature):
    """The braces block that follows a signature."""
    start = text.index('{', text.index(signature))
    depth, at = 1, start + 1
    while depth:
        depth += {'{': 1, '}': -1}.get(text[at], 0)
        at += 1
    return text[start:at]


ignore = shutil.ignore_patterns('.git', 'bin', 'obj', 'MeloNX')
name = adapter.SESSION
with tempfile.TemporaryDirectory(prefix='melonx-collection-class-') as temporary:
    temporary = Path(temporary).resolve()
    candidate = temporary / 'candidate'
    shutil.copytree(SOURCE, candidate, ignore=ignore, symlinks=True)
    check(sha(candidate / name) == adapter.BASELINE[name], 'control is the predecessor\'s output')
    before = (candidate / name).read_text(encoding='utf-8-sig')
    others = {str(path.relative_to(candidate)): sha(path) for path in (candidate / 'src/Ryujinx.Library').glob('*.cs')
              if str(path.relative_to(candidate)) != name}
    changed = adapter.apply(candidate)
    check(sorted(str(path.relative_to(candidate)) for path in changed) == sorted(adapter.BASELINE), 'adapter changed other files')
    try:
        adapter.apply(candidate)
        refused = False
    except AssertionError:
        refused = True
    check(refused, 'fail closed: an adapted tree is refused')
    after = (candidate / name).read_text(encoding='utf-8-sig')
    restored = after
    for old, new in reversed(adapter.PAIRS):
        check(restored.count(new) == 1, 'replacement present once: ' + new.strip().splitlines()[0][:70])
        restored = restored.replace(new, old)
    check(restored == before, 'nothing else changes in ' + name)
    for path, digest in others.items():
        check(sha(candidate / path) == digest, 'not touched: ' + path)

    postimages = {}
    if FINAL_PREPARATION:
        final_text = (FINAL_SOURCE / name).read_text(encoding='utf-8-sig')
        for _, new in adapter.PAIRS:
            check(final_text.count(new) == 1, 'replacement in the final preparation: ' + new.strip().splitlines()[0][:70])
        if name not in files_edited_later('adapt_collection_class'):
            check((candidate / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)
        shutil.rmtree(candidate)
        shutil.copytree(FINAL_SOURCE, candidate, ignore=ignore, symlinks=True)
        after = final_text
        postimages = {name: sha(candidate / name)}

    # --- static: the keep-alive and the class ---
    klass = adapter.CLASS
    check(after.count(klass) == 1 and after.rstrip().endswith(klass.rstrip()), 'the class is the end of the file, once')
    keepalive = after[after.index('public static class BackgroundGcKeepAlive'):after.index(klass)]
    check(keepalive.count('GC.Collect(') == 1 and 'GC.Collect' not in klass and 'GCSettings' not in klass and
          'TryStartNoGCRegion' not in klass and 'Thread.Sleep' not in klass and 'ThreadPriority' not in klass and
          '.Priority' not in klass and 'pthread_set' not in klass,
          'no collection requested, delayed or configured by the class; the keep-alive still requests one')
    start = body(keepalive, 'public static void Start(long generation)')
    check('try { CollectionClass.Register(); CollectionClass.MarkSession(); } catch { }' in start,
          'registration and session mark inside their own catch, in the keep-alive\'s start')
    stop = body(keepalive, 'public static void Stop(long generation)')
    check('try { EmbeddedLaunchDiagnostics.Record("gcPause", "class", detail: CollectionClass.Describe()); } catch { }' in stop and
          stop.index('"gcPause", "summary"') < stop.index('"gcPause", "class"'), 'one journal line at the session\'s close, in its own catch')
    loop = body(keepalive, 'private static void Loop(Run run)')
    check(re.search(r'System\.Threading\.Thread\.Sleep\(PollMs\);\s*(//[^\n]*\n\s*)*CollectionClass\.ReleaseAfterRestart\(\);', loop) and
          keepalive.count('CollectionClass.ReleaseAfterRestart();') == 1, 'the poll ends a left override first thing after its sleep')
    check(after.count('CollectionClass.') - klass.count('CollectionClass.') == 4, 'four uses of the class outside it')

    imports = re.findall(r'\[System\.Runtime\.InteropServices\.DllImport\(([^)]*)\)([^\]]*)\]\s*private static extern [^;]*? (\w+)\(', klass)
    check(len(imports) == 6 and all('SuppressGCTransition' in attributes for _, attributes, _ in imports),
          'six imports, each without a collector transition: %s' % [function for _, _, function in imports])
    check([function for _, _, function in imports] == ['RhRegisterGcCallout', 'pthread_self', 'qos_class_self',
          'pthread_override_qos_class_start_np', 'pthread_override_qos_class_end_np', 'clock_gettime_nsec_np'], 'the imports')
    check('DllImport("*", EntryPoint = "RhRegisterGcCallout")' in klass, 'the registration is the runtime\'s own, linked statically')
    on_start, on_end = body(klass, 'private static void OnStart(uint condemnedGeneration)'), body(klass, 'private static void OnEnd(uint condemnedGeneration)')
    for label, text in (('start', on_start), ('end', on_end)):
        check(not re.search(r'\bnew\b|\block\b|\bthrow\b|\btry\b|"|\$|\bstring\b|Monitor|\.ToString|\bawait\b|\byield\b', text),
              'the %s callout allocates nothing, takes no lock, raises nothing' % label)
        called = set(re.findall(r'\b([A-Z]\w+)\(', text))
        check(called <= {'Exchange', 'Lower', 'Self', 'ClassOfSelf', 'CpuNs', 'WallNs', 'Raise', 'Bucket'},
              'the %s callout calls only the platform functions and interlocked exchange: %s' % (label, sorted(called)))
    check(klass.count('[System.Runtime.InteropServices.UnmanagedCallersOnly]') == 2, 'two callouts')
    register = body(klass, 'public static int Register()')
    bound = register[:register.index('RhRegisterGcCallout(')]
    check(all(call in bound for call in ('Self()', 'ClassOfSelf()', 'CpuNs()', 'WallNs()', 'Raise(self)', 'Lower(token)')),
          'every function a callout calls is called once before the callouts are registered')
    check('if (!Applies) return' in register and register.index('if (!Applies) return') < register.index('try'),
          'another platform: nothing is bound or registered')
    check('catch (System.Exception)' in register and 'status = 3;' in register, 'a runtime without the registration is reported, not fatal')
    check('qosClass != UserInteractive && qosClass != Unspecified' in on_start and 'RaiseCollectingThread &&' in on_start,
          'a user-interactive thread and a thread outside the classes are left as they are; the raising has a switch')
    check(on_start.index('Interlocked.Exchange(ref _token, 0)') < on_start.index('Raise(self)') and
          on_end.count('Interlocked.Exchange(ref _token, 0)') == 1 and klass.count('Lower(token)') + klass.count('Lower(pending)') == 4,
          'an override is taken out of its slot before it is ended, by whichever of the four places ends it')
    check('pthread_override_qos_class_start_np(thread, UserInteractive, 0)' in klass and 'UserInteractive = 0x21' in klass and
          'clock_gettime_nsec_np(8)' in klass and 'clock_gettime_nsec_np(16)' in klass,
          'the override is user-interactive; the clocks are the uptime and the thread\'s CPU time')

    # --- built: the production assembly ---
    out = run([DOTNET, 'build', str(candidate / 'src/Ryujinx.Library/Ryujinx.Library.csproj'), '-c', 'Release', '-nologo', '-m:1',
               '-p:NuGetAudit=false'], candidate)
    warnings = sorted(set(line.split(': warning ')[1].split(':')[0] for line in out.splitlines()
                          if 'EmbeddedSession.cs' in line and ': warning ' in line))
    check(not warnings, 'no warning in EmbeddedSession.cs: %s' % warnings)
    check(' error ' not in out, 'production Ryujinx.Library assembly builds')

    # --- executed ---
    fixture = temporary / 'fixture'
    emit_fixture(fixture)
    check((fixture / 'CollectionClass.cs').read_text(encoding='utf-8') == klass and klass in after, 'the fixture compiles the adapter\'s class text')
    run([DOTNET, 'build', str(fixture / 'Fixture.csproj'), '-c', 'Release', '-nologo', '-o', str(fixture / 'jit')], fixture)
    refused_run = json.loads(run([DOTNET, str(fixture / 'jit/Fixture.dll'), 'refused'], fixture).strip().splitlines()[-1])
    shutil.rmtree(fixture / 'obj')
    rid = 'linux-arm64' if os.uname().machine in ('aarch64', 'arm64') else 'linux-x64'
    run([DOTNET, 'publish', str(fixture / 'Fixture.csproj'), '-r', rid, '-c', 'Release', '-nologo', '-o', str(fixture / 'aot')], fixture)
    plain = json.loads(run([str(fixture / 'aot/Fixture'), 'plain'], fixture).strip().splitlines()[-1])
    r = json.loads(run([str(fixture / 'aot/Fixture'), 'host'], fixture).strip().splitlines()[-1])

print(json.dumps({k: v for k, v in r.items() if k not in ('describe', 'marked')})[:2400], flush=True)

for unregistered, status, said in ((refused_run, 3, 'refused by the runtime'), (plain, 2, 'not this platform')):
    check(unregistered['registered'] == unregistered['registeredAgain'] == unregistered['status'] == status and said in unregistered['describe'],
          '%s: reported as status %d' % (unregistered['mode'], status))
    check(unregistered['collections'] >= 10 and unregistered['starts'] == unregistered['ends'] == unregistered['raised'] == 0 and
          not unregistered['inForce'] and unregistered['platformRaises'] == unregistered['platformLowers'],
          '%s: collections run, no callout, no override' % unregistered['mode'])

check(r['registered'] == 1 and r['registeredAgain'] == 1, 'ahead of time: the runtime accepts both callouts; a second registration is the first')
u = r['utility']
check(u['collections'] == 25 and u['raised'] == 25 and u['raisedThisThread'] == 25 and not u['inForceAfter'] and u['cpuWithinWall'],
      'a utility thread\'s collections each raise that thread, none is left raised: %s' % u)
for label in ('interactive', 'unspecified'):
    check(r[label] == {'collections': 10, 'raised': 0, 'raisedThisThread': 0}, 'a %s thread is never raised: %s' % (label, r[label]))
check(r['allocation'] == {'bytesAllocatedByThreeCollections': 0, 'raised': 3, 'inForceAfter': False},
      'three forced collections: raised three times, 0 bytes allocated on the thread: %s' % r['allocation'])
check(r['off'] == {'collections': 10, 'raised': 0}, 'raising off: accounted, never raised: %s' % r['off'])
s, p = r['stress'], r['polled']
for label, phase in (('as it is', s), ('with the poll', p)):
    check(phase['raises'] == phase['lowers'] and phase['alive'] == 0 and not phase['inForceAfter'] and phase['raises'] >= 10,
          'four classes, %s: every override started is ended: %s' % (label, phase))
    check(phase['ends'] >= phase['starts'] >= 20 and phase['generation2'] >= 3, 'four classes, %s: collections of every kind ran: %s' % (label, phase))
check(s['endedByPoll'] == 0 and s['endedByNextStart'] + s['endedByAnotherThread'] >= 1,
      'a collection that goes on in the background leaves its override until the next collection or its end: %s' % s)
check(p['endedByPoll'] >= 1 and p['endedByPoll'] >= p['endedByNextStart'] + p['endedByAnotherThread'],
      'with the keep-alive\'s poll that override is ended while the engine runs: %s' % p)
check(r['platform']['mostAlive'] == 1 and r['platform']['raises'] == r['platform']['lowers'] == r['raised'] and r['platform']['alive'] == 0,
      'never two overrides at once; as many ended as started: %s' % r['platform'])
for request in r['background']['requests']:
    check(request['inForceAtReturn'] == (request['endsAtReturn'] == 0) and request['endedByPoll'] == int(request['inForceAtReturn']) and
          not request['inForceAfterPoll'] and request['aliveAfterPoll'] == 0 and not request['inForceAfter'] and request['raised'] == 1,
          'a requested background collection: raised once; an override is left only if no end was reported, and the poll ends it: %s' % request)
check(all(word in r['describe'] for word in ('utility ', 'default ', 'background ', 'user-interactive ', 'wall ', 'CPU ', '(adapt_collection_class).')),
      'the journal line names each class with its wall and CPU time')
m = r['marked']
check(m['starts'] == m['raised'] == m['utility'] == 0 and 'raised 0 times' in m['describe'], 'a session mark restarts the totals: %s' % m)

inputs = ['build-utils/melonx/adapt_collection_class.py', 'build-utils/melonx/adapt_session.py', 'test/melonx_collection_class_test.py',
          'test/melonx_collection_class/Program.cs', 'test/melonx_adapter_control.py']
report = {
    'result': 'passed', 'checks': checks, 'finalPreparationBound': FINAL_PREPARATION,
    'sourceKind': 'finalPreparationWithReversedControl' if FINAL_PREPARATION else 'pinnedPreparationPlusAdapter',
    'postimages': postimages, 'physicalDeviceTested': False, 'productionLibraryAssemblyBuilt': True,
    'sourceBaseline': adapter.BASELINE, 'aheadOfTimeRuntime': rid,
    'utilityCollectionsRaised': u['raised'], 'bytesAllocatedInsideCollections': r['allocation']['bytesAllocatedByThreeCollections'],
    'overridesStartedAndEnded': [r['platform']['raises'], r['platform']['lowers']], 'mostOverridesAtOnce': r['platform']['mostAlive'],
    'leftByBackgroundCollections': {'endedByNextStartOrBackgroundThread': s['endedByNextStart'] + s['endedByAnotherThread'],
                                    'endedByPollWhenPolled': p['endedByPoll']},
    'probe': r, 'plain': plain, 'refused': refused_run,
    'deviceEvidence': 'IPA 729 Hogwarts Legacy (private journal, pid 58475): gcPause gen0 363.9 ms promoting 2.2 MiB, 447.6 ms '
                      'promoting 0.1 MiB, 720.6 ms promoting 1.1 MiB; 33 pauses over 33.3 ms. IPA 725: a collection on a thread of '
                      'priority 20 received 15.6 ms of CPU in 961 ms',
    'appleEvidence': 'workflow melonx-collection-class.yml (macOS arm64): scheduling probe run 43315146893; the fixture\'s "apple" '
                     'mode is run by that workflow, not by this gate',
    'inputs': {path: sha(ROOT / path) for path in inputs},
    'limitation': 'Host: the runtime\'s callouts, their order and the override protocol with the fixture\'s platform functions. '
                  'The QoS calls and the scheduler\'s response are exercised on macOS arm64 by the workflow; the effect on the '
                  'iPhone\'s pauses is read from the gcPause lines of the next IPA.',
}
out = ROOT / 'dist/melonx/collection-class-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(report, indent=2) + '\n')
print(f'PASS {checks} collection class checks')
