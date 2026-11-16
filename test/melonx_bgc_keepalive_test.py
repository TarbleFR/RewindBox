#!/usr/bin/env python3
"""adapt_bgc_keepalive on the final preparation, against the Core 691 file as control.

Usage: melonx_bgc_keepalive_test.py <control> --candidate-source <final preparation containing the adapter>

IPA 690/691: every in-play blocking gen2 fell back from a background one (148/557 ms, 151/439/718 ms), each more than
20 s after the previous background gen2: the .NET 10.0.0 workstation BGC thread had left after its 20 s idle wait and
its re-creation raced the start check. For control and candidate the production Ryujinx.Library assembly (which compiles the session file) is built. The
candidate's real BackgroundGcKeepAlive class, taken from the final preparation, runs in
test/melonx_bgc_keepalive/Program.cs: (1) its policy table (nothing before the session's first background gen2,
nothing before 12 s, a request from 12 to 16 s, nothing after 16 s, nothing under a 384 MiB heap); (2) its real loop on
fake seams (virtual clock, background record, heap): one request per window, none after a missed window, none after
Stop, the journal lines; (3) its real loop on the host .NET 10.0.0 runtime with a 448 MiB live heap for 45 s: its
requests are background collections (the background record advances, no blocking gen2 is added). Source: the session
start (after the diagnostics epoch, before the game loads) and stop (in the finally, after the epoch) wiring, the official GC call (blocking false, compacting false), no other collection, no lock or wait on
an emulator thread. Writes dist/melonx/bgc-keepalive-checks.json. No device; the device race itself is not reproduced.

Plan 748 rank 2, managed alternative (adapt_keepalive_after_ephemeral), on the final preparation: the final
EmbeddedSession.cs's keep-alive classes, and as control the same text with that adapter's replacements undone (its
pinned baseline), run their real loops in test/melonx_bgc_keepalive/Final.cs (stubs for the classes of other files).
Simulated (virtual clock, scripted records, the same script for both): the control requests at the first poll 12 s after
the record changed; the candidate makes no request at 12 s or 15.25 s without an ephemeral collection, requests at the
poll that sees one end (not one that ended before the window, nor while the heap is too fragmented), requests at 15.5 s
without one, and misses a window when held over its last polls; its summary counts both kinds. Static: Decide, the
window's constants and the request itself are the control's. Real (candidate, production reads and request, host .NET
10 runtime, 448 MiB live heap): with an ephemeral collection forced every 1.7 s every request comes within a poll of one's
end, 12 s or more after the background record changed; with none, at 15.5 to 16 s; no blocking gen2 added.
"""
from pathlib import Path
import hashlib, json, os, re, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import ORDER, control_source, files_edited_later  # noqa: E402
_HOLD = []
FINAL_SOURCE = SOURCE
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_bgc_keepalive', _HOLD)
import adapt_bgc_keepalive as adapter  # noqa: E402

DOTNET = os.environ.get('DOTNET', 'dotnet')
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


for name, expected in adapter.BASELINE.items():
    check(hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected, 'not the Core 691 preparation: ' + name)

texts = {}
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
with tempfile.TemporaryDirectory(prefix='melonx-bgc-keepalive-') as temporary:
    for variant in ('control', 'candidate'):
        work = Path(temporary).resolve() / variant
        shutil.copytree(SOURCE, work, ignore=shutil.ignore_patterns('.git', 'bin', 'obj', 'MeloNX'), symlinks=True)
        if variant == 'candidate':
            changed = adapter.apply(work)
            check(sorted(str(p.relative_to(work)) for p in changed) == sorted(adapter.BASELINE), 'adapter changed other files')
            if FINAL_PREPARATION:
                # Core 719: adapt_bgc_fragmentation_guard edits the same class later; control_source() proved that control
                # plus this adapter plus the later ones is the final preparation, so only untouched files compare here.
                later = files_edited_later('adapt_bgc_keepalive')
                for name in adapter.BASELINE:
                    if name not in later:
                        check((work / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)
        texts[variant] = (work / adapter.SESSION).read_text(encoding='utf-8-sig')
        result = subprocess.run([DOTNET, 'build', str(work / 'src/Ryujinx.Library/Ryujinx.Library.csproj'), '-c', 'Release',
                                 '-nologo', '-m:1', '-p:NuGetAudit=false'], capture_output=True, text=True, timeout=1800, env=environment, cwd=work)
        if result.returncode:
            print(result.stdout[-5000:], result.stderr[-2000:], flush=True)
        check(result.returncode == 0, variant + ' production Ryujinx.Library assembly builds')

    control, candidate = texts['control'], texts['candidate']
    marker = '// RewindBox (adapt_bgc_keepalive): keeps the workstation background GC thread'
    check(marker not in control and candidate.count(marker) == 1, 'the class is the candidate\'s only addition')
    klass = candidate[candidate.index(marker):]
    check(klass.rstrip().endswith('}') and klass.count('public static class BackgroundGcKeepAlive') == 1, 'one class at the end')
    check(candidate.replace(adapter.START_NEW, adapter.START_OLD).replace(adapter.STOP_NEW, adapter.STOP_OLD)
          .replace(adapter.TAIL_NEW, adapter.TAIL_OLD) == control, 'nothing else in the file changes')
    check(klass.count('GC.Collect(') == 1 and 'GC.Collect(2, GCCollectionMode.Forced, blocking: false, compacting: false)' in klass,
          'the only collection is a non-blocking, non-compacting gen2 request')
    check('lock (' not in klass and '.Wait(' not in klass and 'Monitor.' not in klass, 'no lock or wait in the keep-alive')
    check('Priority = System.Threading.ThreadPriority.BelowNormal' in klass and 'IsBackground = true' in klass, 'its own background thread')
    start = candidate.index('EmbeddedPerformanceDiagnostics.Start(generation);')
    check(candidate.index('BackgroundGcKeepAlive.Start(generation);') == start + len('EmbeddedPerformanceDiagnostics.Start(generation);\n                ')
          and candidate.index('BackgroundGcKeepAlive.Start(generation);') < candidate.index('try { Load(options);'), 'started with the session, before the game loads')
    stop = candidate.index('EmbeddedPerformanceDiagnostics.Stop(generation);')
    check(candidate.index('BackgroundGcKeepAlive.Stop(generation);') == stop + len('EmbeddedPerformanceDiagnostics.Stop(generation);\n                    ')
          and candidate.count('BackgroundGcKeepAlive.Stop(generation);') == 1, 'stopped in the finally, right after the epoch')

    fixture = Path(temporary).resolve() / 'fixture'
    fixture.mkdir()
    program = (ROOT / 'test/melonx_bgc_keepalive/Program.cs').read_text()
    (fixture / 'Program.cs').write_text(program.replace('//__CLASS__\n', klass + '\n'))
    (fixture / 'Fixture.csproj').write_text(
        '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
        '<Nullable>disable</Nullable><NuGetAudit>false</NuGetAudit><ServerGarbageCollection>false</ServerGarbageCollection>'
        '<ConcurrentGarbageCollection>true</ConcurrentGarbageCollection></PropertyGroup></Project>\n')
    for command in ([DOTNET, 'build', str(fixture / 'Fixture.csproj'), '-c', 'Release', '-nologo', '-p:NuGetAudit=false'],
                    [DOTNET, str(fixture / 'bin/Release/net10.0/Fixture.dll')]):
        result = subprocess.run(command, capture_output=True, text=True, timeout=900, env=environment, cwd=fixture)
        if result.returncode:
            print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
            result.check_returncode()
    report = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
print(json.dumps(report), flush=True)

policy = report['policy']
check(policy == {'none': 'NotSeen', '0': 'Wait', '11999': 'Wait', '12000': 'Induce', '16000': 'Induce', '16001': 'Missed',
                 '30000': 'Missed', '14000small': 'SmallHeap', '14000at384': 'Induce'}, 'policy table')
sim = report['simulated']
check(sim['beforeFirst'] == 0, 'nothing before the session\'s first background gen2')
check(sim['at11'] == 0, 'nothing 11 s after it')
check(sim['at14'] == 1 and 20_000 + 12_000 <= sim['firstAtMs'] <= 20_000 + 12_500, 'one request 12 s after it')
check(sim['second'] == 2 and 34_000 + 12_000 <= sim['secondAtMs'] <= 34_000 + 12_500, 'one more 12 s after the next')
check(sim['smallHeap'] == 2, 'none for a small heap')
check(sim['missed'] == 2, 'none after a missed window')
check(sim['afterStop'] == 2, 'none after Stop')
check(any('gcKeepAlive/started' in line for line in sim['lines']) and
      any(line.startswith('gcKeepAlive/summary: background gen2 requests 2, windows missed 1, small-heap skips 1') for line in sim['lines']),
      'journal: first request and session summary')
real = report['real']
check(real['requested'] >= 2, 'requests on the host runtime')
check(real['backgroundAdvanced'] >= real['requested'], 'each request is a background gen2 on the host runtime')
check(real['blockingAdvanced'] == 0, 'no blocking gen2 added on the host runtime')
check(real['heapMiB'] >= 384, 'the live heap is large enough')

# Plan 748 rank 2, managed alternative: the final preparation's keep-alive, executed (see the docstring).
final = dict(executed=False)
if FINAL_PREPARATION and 'adapt_keepalive_after_ephemeral' in ORDER:
    import adapt_keepalive_after_ephemeral as after  # noqa: E402
    check(files_edited_later('adapt_keepalive_after_ephemeral') == set(), 'no later adapter edits the session file')
    final_text = (FINAL_SOURCE / after.SESSION).read_text(encoding='utf-8-sig')
    control_text = final_text
    for old, new in reversed(after.PAIRS):
        check(control_text.count(new) == 1, 'adapt_keepalive_after_ephemeral replacement once: ' + new.strip().splitlines()[0][:60])
        control_text = control_text.replace(new, old)
    check(hashlib.sha256(control_text.encode('utf-8')).hexdigest() == after.BASELINE[after.SESSION],
          'the final session file is adapt_keepalive_after_ephemeral on its pinned baseline')
    end = '// RewindBox (adapt_collection_class): a collection that stops every engine thread'
    classes = {name: text[text.index(marker):text.index(end)] for name, text in (('candidate', final_text), ('control', control_text))}

    def member(text, signature):
        start = text.index(signature)
        return text[start:text.index('\n    }\n', start) + 7]

    def induce_case(text):
        loop = text[text.index('    private static void Loop(Run run)'):]
        return loop[loop.rindex('\n', 0, loop.index('case Decision.Induce:')) + 1:loop.index('case Decision.Missed:')]

    candidate_class, control_class = classes['candidate'], classes['control']
    check(candidate_class.count('GC.Collect(') == 1 and 'GC.Collect(2, GCCollectionMode.Forced, blocking: false, compacting: false)' in candidate_class and
          'lock (' not in candidate_class and '.Wait(' not in candidate_class and 'GCSettings' not in candidate_class,
          'final: the only collection is still the non-blocking request; no lock, wait or setting')
    check(all(member(candidate_class, signature) == member(control_class, signature) for signature in
              ('    public static Decision Decide(long msSinceBackground, long heapBytes, double fragmentation)',
               '    public static Decision Decide(long msSinceBackground, long heapBytes)')) and
          all(line in candidate_class for line in ('    public const long WindowStartMs = 12_000;\n', '    public const long WindowEndMs = 16_000;\n',
                                                   '    public const int PollMs = 250;\n')),
          'final: the window (Decide and its constants) is the control\'s')
    induce = induce_case(candidate_class)
    statements = [line.strip() for line in induce.splitlines() if line.strip() and not line.strip().startswith('//')]
    check(induce.replace(after.INDUCE_NEW, after.INDUCE_OLD).replace(after.COUNT_NEW, after.COUNT_OLD) == induce_case(control_class) and
          statements[1] == 'if (!RequestNow(now - lastChange, ephemeralEnded)) break;',
          'final: the request waits first thing in its case; the request itself and its accounting are the control\'s')

    project = ('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
               '<Nullable>disable</Nullable><NuGetAudit>false</NuGetAudit><ServerGarbageCollection>false</ServerGarbageCollection>'
               '<ConcurrentGarbageCollection>true</ConcurrentGarbageCollection></PropertyGroup></Project>\n')
    fixture_text = (ROOT / 'test/melonx_bgc_keepalive/Final.cs').read_text()
    runs = {}
    with tempfile.TemporaryDirectory(prefix='melonx-bgc-keepalive-final-') as temporary:
        for variant, modes in (('control', ('simulated',)), ('candidate', ('simulated', 'real'))):
            fixture = Path(temporary).resolve() / variant
            fixture.mkdir()
            (fixture / 'Program.cs').write_text(fixture_text.replace('//__KEEPALIVE__\n', classes[variant] + '\n'))
            (fixture / 'Fixture.csproj').write_text(project)
            result = subprocess.run([DOTNET, 'build', str(fixture / 'Fixture.csproj'), '-c', 'Release', '-nologo', '-p:NuGetAudit=false'],
                                    capture_output=True, text=True, timeout=900, env=environment, cwd=fixture)
            if result.returncode:
                print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
                result.check_returncode()
            for mode in modes:
                result = subprocess.run([DOTNET, str(fixture / 'bin/Release/net10.0/Fixture.dll'), mode], capture_output=True, text=True,
                                        timeout=900, env=environment, cwd=fixture)
                if result.returncode:
                    print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
                    result.check_returncode()
                runs[variant + '.' + mode] = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
    print(json.dumps(runs)[:4000], flush=True)

    def keepalive_summary(journal):
        lines = [line for line in journal if line.startswith('gcKeepAlive/summary: ')]
        check(len(lines) == 1, 'one keep-alive summary: ' + str(journal))
        return lines[0]

    c, k = runs['control.simulated'], runs['candidate.simulated']
    check(c['latestRequestMs'] is None and 'requestNow' not in c, 'the control has no alignment')
    check(c['requests'] == [13_000, 27_250, 44_500, 61_250] and c['marks'] == {'at12sWithoutEphemeral': 1, 'afterEphemeralAt13250': 1,
          'at15250WithoutEphemeral': 2, 'fragmentedThenLow': 3},
          'control: a request at the first poll 12 s after each record change (or request), wherever the ephemeral collections are: ' + str(c))
    check(keepalive_summary(c['journal']).startswith('gcKeepAlive/summary: background gen2 requests 4, windows missed 0, ') and
          keepalive_summary(c['journal']).endswith(', dormant after a fragmented skip 0 (adapt_bgc_keepalive, adapt_bgc_fragmentation_guard, '
                                                   'adapt_gc_keepalive_dormant)'), 'control summary: ' + keepalive_summary(c['journal']))
    check(k['latestRequestMs'] == 15_500 and k['requestNow'] == {'12000none': False, '12000ended': True, '15499none': False, '15499ended': True,
                                                                '15500none': True, '15500ended': True, '16000none': True, '16000ended': True},
          'candidate rule: right after an ephemeral collection ended, or from 16 s less two polls (15.5 s) on: ' + str(k.get('requestNow')))
    check(k['marks'] == {'at12sWithoutEphemeral': 0, 'afterEphemeralAt13250': 1, 'at15250WithoutEphemeral': 1, 'fragmentedThenLow': 2},
          'candidate: nothing at 12 s or 13 s without an ephemeral collection (one ended before the window does not count), nothing at '
          '15.25 s, nothing when the fragmentation falls without one: ' + str(k['marks']))
    check(k['requests'] == [14_250, 30_750, 44_750],
          'candidate: at the poll that saw an ephemeral collection end 13.25 s after the record changed; at 15.5 s without one; at the '
          'ephemeral end after a fragmented refusal (the one seen while refused does not count later): ' + str(k['requests']))
    check(keepalive_summary(k['journal']) == 'gcKeepAlive/summary: background gen2 requests 3, windows missed 1, small-heap skips 0, '
          'background records seen 4, fragmented skips 1, requests run blocking 0, dormant after a fragmented skip 0, requests right after an '
          'ephemeral collection 2, at 15500 ms without one 1 (adapt_bgc_keepalive, adapt_bgc_fragmentation_guard, adapt_gc_keepalive_dormant, '
          'adapt_keepalive_after_ephemeral)',
          'candidate summary: the two kinds of request counted; a keep-alive held over its window\'s last polls misses it (the control '
          'requested at 15.25 s): ' + keepalive_summary(k['journal']))
    for name, run in (('control', c), ('candidate', k)):
        check(sum(line.startswith('gcKeepAlive/started: ') for line in run['journal']) == 1 and
              not any(line.startswith(('gcKeepAlive/dormant', 'gcKeepAlive/elevated', 'gcPause/ephemeral')) for line in run['journal']),
              name + ': one started line, no other keep-alive line kind: ' + str(run['journal']))

    r = runs['candidate.real']
    forced, quiet = r['forced'], r['quiet']
    check(len(forced['requests']) >= 2 and all(0 <= q['sinceEphemeralEnd'] <= 250 + 250 and q['sinceBackgroundChange'] >= 12_000 - 100
                                                 for q in forced['requests']),
          'real, an ephemeral collection every 1.7 s: every request within a poll of one\'s end, 12 s or more after the record changed: ' +
          str(forced['requests']))
    check(', requests right after an ephemeral collection %d, at 15500 ms without one 0 (' % len(forced['requests']) in
          keepalive_summary(forced['journal']) and ', windows missed 0, ' in keepalive_summary(forced['journal']),
          'real, forced: counted as right after an ephemeral collection: ' + keepalive_summary(forced['journal']))
    # Quiet: the fixture forces nothing; an ephemeral collection the runtime runs on its own may still end in a window.
    aligned = [q for q in quiet['requests'] if 0 <= q['sinceEphemeralEnd'] <= 250 + 250]
    latest = [q for q in quiet['requests'] if 15_500 - 100 <= q['sinceBackgroundChange'] <= 16_000 + 500]
    counts = re.search(r', requests right after an ephemeral collection (\d+), at 15500 ms without one (\d+) \(', keepalive_summary(quiet['journal']))
    check(len(quiet['requests']) >= 1 and all(q in aligned or q in latest for q in quiet['requests']) and counts and
          int(counts.group(1)) + int(counts.group(2)) == len(quiet['requests']) and
          int(counts.group(2)) >= len([q for q in latest if q not in aligned]) and
          int(counts.group(1)) >= len([q for q in aligned if q not in latest]) and
          ', windows missed 0, ' in keepalive_summary(quiet['journal']),
          'real, nothing forced: each request within a poll of an ephemeral collection\'s end or at 15.5 to 16 s after the record '
          'changed, and counted so: ' + str(quiet))
    unaligned = [q for q in latest if q not in aligned]
    check(r['blockingAdvanced'] == 0 and r['backgroundAdvanced'] >= len(forced['requests']) + len(quiet['requests']) and r['heapMiB'] >= 384,
          'real: the requests are background collections, no blocking gen2 added: ' +
          str({key: r[key] for key in ('blockingAdvanced', 'backgroundAdvanced', 'heapMiB')}))
    final = dict(executed=True, controlRequestsAtFirstPollOf12s=True, noRequestWithoutEphemeralBefore15500=True, requestAfterEphemeral=True,
                 requestAtLatest=True, windowUnchanged=True, missedWhenHeldOverLastPolls=True, summaryCountsBothKinds=True,
                 realAlignedRequests=len(forced['requests']), realLatestRequests=len(unaligned), realBlockingAdded=r['blockingAdvanced'],
                 runs=runs)

inputs = ['build-utils/melonx/adapt_bgc_keepalive.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_bgc_keepalive_test.py', 'test/melonx_bgc_keepalive/Program.cs', 'test/melonx_adapter_control.py']
if final['executed']:
    inputs += ['build-utils/melonx/adapt_keepalive_after_ephemeral.py', 'test/melonx_bgc_keepalive/Final.cs']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core691Preparation',
               postimages={p: hashlib.sha256((FINAL_SOURCE / p).read_bytes()).hexdigest() for p in adapter.BASELINE} if FINAL_PREPARATION else {},
               report=report, sdk=sdk, physicalDeviceTested=False, productionLibraryAssemblyBuilt=True, sourceBaseline=adapter.BASELINE,
               finalKeepAlive=final,
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs})
out = ROOT / 'dist/melonx/bgc-keepalive-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
