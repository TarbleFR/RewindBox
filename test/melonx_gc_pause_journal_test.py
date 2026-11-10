#!/usr/bin/env python3
"""adapt_gc_pause_journal on the final preparation, against its predecessor (adapt_gc_keepalive_dormant on Core 721) as
control.

Usage: melonx_gc_pause_journal_test.py <Core 721 preparation> [--candidate-source <final preparation containing the adapter>]

IPA 718 Hogwarts in play: 130-190 ms of GC pause per 5 s for 2-3 ephemeral collections (about 29 ms per gen0 and 135 ms
per gen1 by fitting the windows), with a 64 MiB gen0 budget; no record gives each collection. The candidate's keep-alive
loop also reads the ephemeral record on each 250 ms poll, adds each new collection to its generation's totals and
journals the long ones (bounded); the run's collections are counted by generation from the runtime's collection counts.
The production Ryujinx.Library assembly builds. The candidate's real class runs in test/melonx_gc_pause_journal/Program.cs
on the host .NET 10 runtime:
- scripted (fake record and counts): gen0 25.4 ms, gen1 140.2 ms, gen0 5 ms, then a gen1 and a background gen2 ending
  between two reads, gen0 30 ms, gen1 19.9 ms and 20 more: a line per collection paused 20 ms or more, in order; the
  summary gives per generation the collections seen of those that ran (the missed gen1 counts, the gen2 does not),
  pause, longest, promoted, and the counts over a frame and paused 20 ms or more;
- bound (the candidate's own methods, by reflection): 500 collections of 25 ms give the first 24 lines then every
  16th, 48 in all; a run whose start counts were not read says so;
- real (production reads): the fixture forces gen0 and gen1 collections (each one's generation read back from the
  runtime, which may run a requested gen1 as a gen2), a background gen2 and a blocking gen2; the summary's totals are
  the runtime's own counts by generation, without the gen2s, and every forced ephemeral collection is seen.
No request is made in any scenario. Static: only the keep-alive class changes; no collection, lock, setting or wait
added; each read and line is inside its own catch. Host runtime, not an iPhone. Writes
dist/melonx/gc-pause-journal-checks.json.
"""
from pathlib import Path
import hashlib, json, os, re, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, files_edited_later  # noqa: E402
import adapt_gc_keepalive_dormant as dormant  # noqa: E402
import adapt_gc_pause_journal as adapter  # noqa: E402
_HOLD = []
FINAL_SOURCE = SOURCE
if hashlib.sha256((SOURCE / dormant.SESSION).read_bytes()).hexdigest() == dormant.BASELINE[dormant.SESSION]:
    # The Core 721 preparation itself: the predecessor (adapt_gc_keepalive_dormant) is applied to a copy first.
    _HOLD.append(tempfile.TemporaryDirectory(prefix='melonx-gc-pause-predecessor-'))
    predecessor = Path(_HOLD[-1].name) / 'predecessor'
    shutil.copytree(SOURCE, predecessor, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
    dormant.apply(predecessor)
    SOURCE = FINAL_SOURCE = predecessor
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_gc_pause_journal', _HOLD)

DOTNET = os.environ.get('DOTNET', 'dotnet')
MARKER = '// RewindBox (adapt_bgc_keepalive): keeps the workstation background GC thread'
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
with tempfile.TemporaryDirectory(prefix='melonx-gc-pause-journal-') as temporary:
    work = Path(temporary).resolve() / 'candidate'
    shutil.copytree(SOURCE, work, ignore=shutil.ignore_patterns('.git', 'bin', 'obj', 'MeloNX'), symlinks=True)
    session = work / adapter.SESSION
    check(hashlib.sha256(session.read_bytes()).hexdigest() == adapter.BASELINE[adapter.SESSION], 'control is the predecessor\'s output')
    control = session.read_text(encoding='utf-8-sig')
    changed = adapter.apply(work)
    check(sorted(str(p.relative_to(work)) for p in changed) == sorted(adapter.BASELINE), 'adapter changed other files')
    try:
        adapter.apply(work)
        refused = False
    except AssertionError:
        refused = True
    check(refused, 'fail closed: an adapted tree is refused')
    if FINAL_PREPARATION and adapter.SESSION not in files_edited_later('adapt_gc_pause_journal'):
        check(session.read_bytes() == (FINAL_SOURCE / adapter.SESSION).read_bytes(), 'final preparation is the adapter')
    candidate = session.read_text(encoding='utf-8-sig')
    restored = candidate
    for old, new in reversed(adapter.PAIRS):
        check(restored.count(new) == 1, 'replacement present once: ' + new.strip().splitlines()[0][:60])
        restored = restored.replace(new, old)
    check(restored == control, 'nothing else in the file changes')
    klass = candidate[candidate.index(MARKER):]
    check(klass.count('GC.Collect(') == 1 and 'lock (' not in klass and '.Wait(' not in klass and 'GCSettings' not in klass and
          klass.count('GC.GetGCMemoryInfo(GCKind.Ephemeral)') == 1 and klass.count('GC.CollectionCount(') == 3,
          'no collection, lock, wait or setting added: one more record read and the three collection counts')
    loop = klass[klass.index('    private static void Loop(Run run)'):]
    poll = loop[loop.index('long now = ReadMilliseconds();'):loop.index('long index = ReadBackgroundIndex();')]
    check(re.search(r'try\s*\{\s*EphemeralRecord ephemeral = ReadEphemeral\(\);[^}]*\{[^}]*NoteEphemeral\(run, ephemeral\);\s*\}\s*\}\s*catch \{ \}', poll)
          and 'try { lastEphemeral = ReadEphemeral().Index; } catch { }' in loop and
          'try { run.CountsAtStart = ReadCollectionCounts(); } catch { }' in klass and
          'try { EmbeddedLaunchDiagnostics.Record("gcPause", "summary", detail: PauseSummary(run)); } catch { }' in klass,
          'read on every poll before the background record; every read and line inside its own catch: the keep-alive goes on')
    result = subprocess.run([DOTNET, 'build', str(work / 'src/Ryujinx.Library/Ryujinx.Library.csproj'), '-c', 'Release',
                             '-nologo', '-m:1', '-p:NuGetAudit=false'], capture_output=True, text=True, timeout=1800,
                            env=environment, cwd=work)
    if result.returncode:
        print(result.stdout[-5000:], result.stderr[-2000:], flush=True)
    check(result.returncode == 0, 'production Ryujinx.Library assembly builds')
    fixture = Path(temporary).resolve() / 'fixture'
    fixture.mkdir()
    program = (ROOT / 'test/melonx_gc_pause_journal/Program.cs').read_text()
    (fixture / 'Program.cs').write_text(program.replace('//__CANDIDATE__\n', klass + '\n'))
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
print(json.dumps({k: v for k, v in report.items() if k != 'scripted'})[:3000], flush=True)


def summary(journal, stage='gcKeepAlive'):
    lines = [line for line in journal if line.startswith(stage + '/summary: ')]
    check(len(lines) == 1, 'one ' + stage + ' summary: ' + str(journal[-3:]))
    return lines[0]


KEEPALIVE_TAIL = ', dormant after a fragmented skip 0 (adapt_bgc_keepalive, adapt_bgc_fragmentation_guard, adapt_gc_keepalive_dormant)'
PAUSE = re.compile(r'^gcPause/summary: ephemeral collections gen0 seen (\d+) of (\d+|\?), pause (\d+) ms, longest ([\d.]+) ms, '
                   r'promoted ([\d.]+) MiB; gen1 seen (\d+) of (\d+|\?), pause (\d+) ms, longest ([\d.]+) ms, promoted ([\d.]+) MiB; '
                   r'over 33\.3 ms (\d+), paused 20 ms or more (\d+), lines (\d+) \(adapt_gc_pause_journal\)$')
check(report['lineThresholdMs'] == 20 and report['maxPauseLines'] == 48 and report['denseLines'] == 24 and
      report['lineStride'] == 16, 'bounds: 20 ms, the first 24 lines then every 16th, at most 48')

s = report['scripted']
pauses = [line for line in s['journal'] if line.startswith('gcPause/ephemeral: ')]
check(len(pauses) == 23, 'one line per collection paused 20 ms or more (23 of the 25 seen): ' + str(len(pauses)))
check(pauses[0] == 'gcPause/ephemeral: gen0 25.4 ms, promoted 3.0 MiB, gen0 64.0->1.0 MiB, gen1 30.0->30.0 MiB, compacted 1, '
      'index 10, long collection 1 (adapt_gc_pause_journal)' and
      pauses[1] == 'gcPause/ephemeral: gen1 140.2 ms, promoted 3.0 MiB, gen0 64.0->1.0 MiB, gen1 40.0->30.0 MiB, compacted 1, '
      'index 11, long collection 2 (adapt_gc_pause_journal)' and
      pauses[2].startswith('gcPause/ephemeral: gen0 30.0 ms, ') and pauses[2].endswith(', index 15, long collection 3 (adapt_gc_pause_journal)') and
      pauses[-1].startswith('gcPause/ephemeral: gen1 79.0 ms, ') and pauses[-1].endswith(', index 36, long collection 23 (adapt_gc_pause_journal)'),
      'the lines in order, without the 5 ms and 19.9 ms collections: ' + str(pauses[:3] + pauses[-1:]))
check(summary(s['journal']).endswith(KEEPALIVE_TAIL), 'the keep-alive summary is unchanged: ' + summary(s['journal']))
text = summary(s['journal'], 'gcPause')
check(text == 'gcPause/summary: ephemeral collections gen0 seen 13 of 13, pause 750 ms, longest 78.0 ms, promoted 39.0 MiB; '
      'gen1 seen 12 of 13, pause 860 ms, longest 140.2 ms, promoted 36.0 MiB; over 33.3 ms 21, paused 20 ms or more 23, '
      'lines 23 (adapt_gc_pause_journal)',
      'per generation, the collections seen of those that ran (the gen1 ended between two reads counts, the background gen2 '
      'does not), pause, longest, promoted; over a frame, long ones, lines: ' + text)
check(s['requests'] == 0, 'no keep-alive request in the scripted run')

b = report['bound']
ranks = [int(re.search(r', long collection (\d+) \(adapt_gc_pause_journal\)$', line).group(1)) for line in b['journal']
         if line.startswith('gcPause/ephemeral: ')]
check(ranks == list(range(1, 25)) + list(range(40, 409, 16)), 'the first 24 long collections then every 16th, 48 lines: ' + str(ranks))
check(b['summary'] == 'ephemeral collections gen0 seen 250 of ?, pause 6250 ms, longest 25.0 ms, promoted 750.0 MiB; gen1 seen 250 '
      'of ?, pause 6250 ms, longest 25.0 ms, promoted 750.0 MiB; over 33.3 ms 0, paused 20 ms or more 500, lines 48 '
      '(adapt_gc_pause_journal)', 'every collection is still counted past the line bound; unread start counts say so: ' + b['summary'])

r = report['real']
check(summary(r['journal']).endswith(KEEPALIVE_TAIL) and r['requests'] == 0, 'no keep-alive request in the real run')
text = summary(r['journal'], 'gcPause')
seen = PAUSE.match(text)
before, after = r['countsBefore'], r['countsAfter']
ran0 = (after[0] - before[0]) - (after[1] - before[1])
ran1 = (after[1] - before[1]) - (after[2] - before[2])
check(seen and seen.group(2) == str(ran0) and seen.group(7) == str(ran1),
      'the totals are the runtime\'s own counts by generation over the run (gen0 %d, gen1 %d): %s' % (ran0, ran1, text))
check(r['requestedBackground'] in ('background', 'blocking') and after[2] - before[2] >= 2,
      'the gen2 requested in the background (ran %s) and the blocking one ran in the run; the totals above leave them out: %s'
      % (r['requestedBackground'], [before, after]))
check(r['ranGen0'] >= 2 and r['ranGen1'] >= 2 and r['ranGen0'] + r['ranGen1'] + r['ranGen2'] == r['forced'],
      'forced collections, each one\'s generation read back from the runtime: ' + str({k: r[k] for k in ('ranGen0', 'ranGen1', 'ranGen2', 'forced')}))
check(r['ranGen0'] <= int(seen.group(1)) <= ran0 and r['ranGen1'] <= int(seen.group(6)) <= ran1,
      'the production read sees every forced ephemeral collection with its generation, and none beyond those that ran: ' + text)

inputs = ['build-utils/melonx/adapt_gc_pause_journal.py', 'build-utils/melonx/adapt_gc_keepalive_dormant.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_gc_pause_journal_test.py', 'test/melonx_gc_pause_journal/Program.cs', 'test/melonx_adapter_control.py']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core721PreparationWithPredecessor',
               postimages={p: hashlib.sha256((FINAL_SOURCE / p).read_bytes()).hexdigest() for p in adapter.BASELINE} if FINAL_PREPARATION else {},
               report=report, sdk=sdk, physicalDeviceTested=False, productionLibraryAssemblyBuilt=True, sourceBaseline=adapter.BASELINE,
               comparison=dict(linesBounded=48, linesSampledAfter=24, perGenerationTotalsFromRuntimeCounts=True, gen2NotCountedAsEphemeral=True,
                               productionReadSeesForcedCollections=True, requestsUnchanged=True, keepAliveSummaryUnchanged=True),
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs})
out = ROOT / 'dist/melonx/gc-pause-journal-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
