#!/usr/bin/env python3
"""gcEvent lines flag a background gen2 that fell back to a blocking one, and give the LOH occupied bytes (Core 658).

Usage: melonx_gc_fallback_test.py <Core 658 prepared MeloNX tree>
       melonx_gc_fallback_test.py <Core 658 prepared tree> --candidate-source <final preparation containing the change>

Finding (IPA 658, Hogwarts Legacy, pid 11152, private Core journal, not in the repository): both in-play full blocking
gen2 collections (102 ms and 332 ms) are each followed by a "background" gcEvent line with the same index whose payload
is byte for byte an earlier background collection's (two and four collections back). .NET 10.0.0's do_pre_gc stamps
the background record with the index of a gen2 it chose as background; when the background GC cannot start
(do_concurrent_p false), the same collection runs blocking and the record keeps the earlier payload. The journal so
shows a background collection that did not happen and hides that the blocking one began as a concurrent one.

Change (native/melonx/EmbeddedPerformanceDiagnostics.cs, copied into the Core as
src/Ryujinx.Common/EmbeddedPerformanceDiagnostics.cs, then edited by adapt_bindless_array_deltas): when the latest
background and blocking indices are equal, the sample writes one fullBlocking line with fellBackFromBackground 1 and no
background line; every line carries fellBackFromBackground, the session's fallback count (counted even when the line
is over budget) and lohOccupiedAfterBytes (LOH size minus free space after that collection). Journal only.

Control: the Core 658 collector. Candidate: this checkout's native collector with the array-delta edits applied as
prepare_embedded.py applies them (with --candidate-source it must equal the final preparation's). Static: the change
stays in the epoch fields and the two gcEvent methods, adds no GC read, journal call, collection, lock or thread, and
the GC reads are the control's. Both production Ryujinx.Common projects build. Behaviour: the real collector and journal
of each side run test/melonx_gc_fallback/Program.cs, where only the collector's GC.GetGCMemoryInfo / CollectionCount
calls go through a test seam (same rewrite on both sides) that, for the fallback, returns the runtime's own blocking
information of a real forced collection and the runtime's own latest background information with its index set to the
blocking one's (the device signature). The control must write the stale background line (the defect), the candidate a
single flagged blocking line, nothing for real collections (no false positive), the flag at the final sample when the
blocking budget is spent, and lohOccupiedAfterBytes = LOH size - LOH free on every line. Writes
dist/melonx/gc-fallback-checks.json. No device; the runtime fallback itself is not reproduced on this host.
"""
from pathlib import Path
import argparse, difflib, hashlib, json, os, re, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
parser.add_argument('source', type=Path, help='Core 658 prepared tree (control)')
parser.add_argument('--candidate-source', type=Path, help='Final preparation containing the change')
args = parser.parse_args()
SOURCE = args.source.resolve()
FINAL = args.candidate_source.resolve() if args.candidate_source else None
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
from adapt_session import once  # noqa: E402
from adapt_bindless_array_deltas import DIAGNOSTIC_EDITS  # noqa: E402

COLLECTOR = 'src/Ryujinx.Common/EmbeddedPerformanceDiagnostics.cs'
JOURNAL = 'src/Ryujinx.Common/EmbeddedLaunchDiagnostics.cs'
NATIVE = 'native/melonx/EmbeddedPerformanceDiagnostics.cs'
# Core 658 preparation and the native collector it was prepared from.
BASELINE = {COLLECTOR: '2af3a086c9271b6bcc40bd3b1087eb71e92aa6c3204325d44521b63f1816c835',
            JOURNAL: 'eb143b14be90261baf92788713a8bb73b11d9d921f420bf2b9b7ad65f5068658'}
NATIVE_BASELINE = 'a899834ff0e46ce265e00c438e073b8aaa8e4299e8aa182b6c0a6435503810e0'
PROGRAM = 'test/melonx_gc_fallback/Program.cs'
DOTNET = os.environ.get('DOTNET', 'dotnet')
ENVIRONMENT = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_TieredCompilation='0')
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def region(lines, start, end):
    """Line indices [first, last) from the line starting with `start` to the line before the one starting with `end`."""
    first = next(i for i, line in enumerate(lines) if line.startswith(start))
    last = next(i for i in range(first + 1, len(lines)) if lines[i].startswith(end))
    return first, last


# This lot's edits of the native collector (old, new), in file order: reversing them on this checkout's collector must
# give back the Core 658 native collector byte for byte (NATIVE_BASELINE).
COLLECTOR_EDITS = [
    ('        public int SeenGen2Collections, GcEventLines, FullBlockingGcEventLines, BackgroundGcEventLines, SuppressedGcEventLines;\n        public Epoch(long generation)',
     '        public int SeenGen2Collections, GcEventLines, FullBlockingGcEventLines, BackgroundGcEventLines, SuppressedGcEventLines;\n        // Blocking gen2s that began as background collections (see RecordGcEvents), counted even when their line is suppressed.\n        public int FallbackGcCollections;\n        public Epoch(long generation)'),
    ('    // on a hot path.\n    private const int MaxGcEventLinesPerKind = 16;',
     "    // on a hot path.\n    // A gen2 the runtime chose as a background collection that could not start\n    // runs in-line and blocking, but .NET 10.0.0 (gc.cpp do_pre_gc and\n    // get_completed_bgc_info) has already stamped the background record with\n    // that collection's index and never refreshes its data: both kinds then\n    // report the same index, the background one with an earlier collection's\n    // payload. That pair is one blocking line flagged fellBackFromBackground,\n    // and the stale background payload is not written. Visible only while no\n    // later background gen2 has replaced the record (same 5 s window).\n    private const int MaxGcEventLinesPerKind = 16;"),
    ('            epoch.SeenGen2Collections = gen2;\n            bool reportBlocking = newBlocking || (final && blocking.Index != epoch.WrittenFullBlockingGcIndex);',
     '            epoch.SeenGen2Collections = gen2;\n            bool fellBack = blocking.Index > 0 && background.Index == blocking.Index;\n            if (fellBack && newBackground) epoch.FallbackGcCollections++;\n            // The stale background record is accounted for: no later sample, final included, writes it.\n            if (fellBack) epoch.WrittenBackgroundGcIndex = background.Index;\n            bool reportBlocking = newBlocking || (final && blocking.Index != epoch.WrittenFullBlockingGcIndex);'),
    ('            bool reportBlocking = newBlocking || (final && blocking.Index != epoch.WrittenFullBlockingGcIndex);\n            bool reportBackground = newBackground || (final && background.Index != epoch.WrittenBackgroundGcIndex);\n            bool backgroundFirst = reportBackground && background.Index < blocking.Index;',
     '            bool reportBlocking = newBlocking || (final && blocking.Index != epoch.WrittenFullBlockingGcIndex);\n            bool reportBackground = !fellBack && (newBackground || (final && background.Index != epoch.WrittenBackgroundGcIndex));\n            bool backgroundFirst = reportBackground && background.Index < blocking.Index;'),
    ('            bool backgroundFirst = reportBackground && background.Index < blocking.Index;\n            if (backgroundFirst) RecordGcEvent(epoch, false, background, newBackground, window, final);\n            if (reportBlocking) RecordGcEvent(epoch, true, blocking, newBlocking, window, final);\n            if (reportBackground && !backgroundFirst) RecordGcEvent(epoch, false, background, newBackground, window, final);\n        }',
     '            bool backgroundFirst = reportBackground && background.Index < blocking.Index;\n            if (backgroundFirst) RecordGcEvent(epoch, false, background, newBackground, window, final, false);\n            if (reportBlocking) RecordGcEvent(epoch, true, blocking, newBlocking, window, final, fellBack);\n            if (reportBackground && !backgroundFirst) RecordGcEvent(epoch, false, background, newBackground, window, final, false);\n        }'),
    ('    }\n    private static void RecordGcEvent(Epoch epoch, bool fullBlocking, GCMemoryInfo memory, bool newInWindow, int window, bool final)\n    {',
     '    }\n    private static void RecordGcEvent(Epoch epoch, bool fullBlocking, GCMemoryInfo memory, bool newInWindow, int window, bool final, bool fellBack)\n    {'),
    ('            json.WriteString("kind", kind); json.WriteBoolean("newInWindow", newInWindow);\n            json.WriteNumber("index", memory.Index); json.WriteNumber("generation", memory.Generation);',
     '            json.WriteString("kind", kind); json.WriteBoolean("newInWindow", newInWindow);\n            json.WriteNumber("fellBackFromBackground", fellBack ? 1 : 0); json.WriteNumber("fallbacksInSession", epoch.FallbackGcCollections);\n            json.WriteNumber("index", memory.Index); json.WriteNumber("generation", memory.Generation);'),
    ('            json.WriteString("generationColumns", "sizeBeforeBytes,fragmentationBeforeBytes,sizeAfterBytes,fragmentationAfterBytes");\n            json.WriteNumber("memoryLoadBytes", memory.MemoryLoadBytes);',
     '            json.WriteString("generationColumns", "sizeBeforeBytes,fragmentationBeforeBytes,sizeAfterBytes,fragmentationAfterBytes");\n            // Live large objects after this collection: LOH size minus its free space (LOH churn between gen2s).\n            json.WriteNumber("lohOccupiedAfterBytes", generations.Length > 3 ? Math.Max(0, generations[3].SizeAfterBytes - generations[3].FragmentationAfterBytes) : 0);\n            json.WriteNumber("memoryLoadBytes", memory.MemoryLoadBytes);'),
]

_CONTROL_HOLD = []
if FINAL is not None and sha((SOURCE / COLLECTOR).read_bytes()) != BASELINE[COLLECTOR]:
    # Core gate form (Core 661): {baseline} is a control tree of the delivered 614 Core, whose collector is older than
    # Core 658's. The control is then the final preparation with the Core 658 collector rebuilt from this checkout's
    # native collector: this lot's edits reversed (checked against NATIVE_BASELINE), then the array-delta edits, as
    # prepare_embedded.py applies them (checked against BASELINE below).
    _CONTROL_HOLD.append(tempfile.TemporaryDirectory(prefix='melonx-gc-fallback-control-'))
    control_tree = Path(_CONTROL_HOLD[0].name) / 'control'
    shutil.copytree(FINAL, control_tree, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
    native = (ROOT / NATIVE).read_bytes().decode('utf-8')
    for old, new in reversed(COLLECTOR_EDITS):
        check(native.count(new) == 1, 'this lot edit is in the native collector once')
        native = native.replace(new, old)
    check(sha(native.encode('utf-8')) == NATIVE_BASELINE, 'reversing this lot gives the Core 658 native collector')
    (control_tree / COLLECTOR).write_bytes(native.encode('utf-8'))
    for old, new in DIAGNOSTIC_EDITS:
        once(control_tree / COLLECTOR, old, new)
    SOURCE = control_tree.resolve()

for name, expected in BASELINE.items():
    check(sha((SOURCE / name).read_bytes()) == expected, 'not the Core 658 preparation: ' + name)

with tempfile.TemporaryDirectory(prefix='melonx-gc-fallback-') as temporary:
    work = Path(temporary).resolve()
    reverse = work / 'reverse.cs'
    shutil.copyfile(SOURCE / COLLECTOR, reverse)
    for old, new in reversed(DIAGNOSTIC_EDITS):
        once(reverse, new, old)
    check(sha(reverse.read_bytes()) == NATIVE_BASELINE, 'Core 658 collector is the pinned native one plus the array-delta edits')
    candidate_file = work / 'candidate.cs'
    shutil.copyfile(ROOT / NATIVE, candidate_file)
    for old, new in DIAGNOSTIC_EDITS:
        once(candidate_file, old, new)
    if FINAL:
        check((FINAL / COLLECTOR).read_bytes() == candidate_file.read_bytes(), 'final preparation holds this collector')
        check((FINAL / JOURNAL).read_bytes() == (SOURCE / JOURNAL).read_bytes(), 'final preparation keeps the journal')
    control_text = (SOURCE / COLLECTOR).read_text(encoding='utf-8-sig')
    candidate_text = candidate_file.read_text(encoding='utf-8-sig')

    # Static: changes only in the epoch fields and the gcEvent methods.
    a, b = control_text.split('\n'), candidate_text.split('\n')
    regions = {}
    for side, lines in (('control', a), ('candidate', b)):
        regions[side] = [region(lines, '    private sealed class Epoch', '    private static Epoch _current;'),
                         region(lines, '    // One durable Core journal line per newly completed gen2', '    private static string Capture(')]
    opcodes = [op for op in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes() if op[0] != 'equal']
    inside = lambda side, lo, hi: any(first <= lo and hi <= last for first, last in regions[side])
    check(opcodes and all(inside('control', op[1], op[2]) and inside('candidate', op[3], op[4]) for op in opcodes),
          'changes stay in the epoch fields and the gcEvent methods: ' + str(opcodes))
    added = '\n'.join('\n'.join(b[op[3]:op[4]]) for op in opcodes)
    check(not re.search(r'GC\.Collect\(|GCSettings|Interlocked|lock \(|Monitor\.|Thread\.|Volatile\.|_current|EmbeddedLaunchDiagnostics',
                        added), 'no collection, GC setting, lock, thread, collector state or new journal call')
    for call in ('GC.GetGCMemoryInfo(', 'GC.CollectionCount(', 'EmbeddedLaunchDiagnostics.Record(', 'MaxGcEventLinesPerKind'):
        check(candidate_text.count(call) == control_text.count(call), 'same number of ' + call)
    epoch_k = '\n'.join(b[slice(*regions['candidate'][0])])
    epoch_c = '\n'.join(a[slice(*regions['control'][0])])
    field = ('        // Blocking gen2s that began as background collections (see RecordGcEvents), counted even when their line is suppressed.\n'
             '        public int FallbackGcCollections;\n')
    check(epoch_k.count(field) == 1 and epoch_k.replace(field, '', 1) == epoch_c, 'epoch: one sampler-only counter added')
    check('bool fellBack = blocking.Index > 0 && background.Index == blocking.Index;' in candidate_text and
          'bool reportBackground = !fellBack && (newBackground || (final && background.Index != epoch.WrittenBackgroundGcIndex));' in candidate_text,
          'equal indices: one flagged blocking line, the stale background payload not written')

    # Both production Ryujinx.Common projects build.
    builds = {}
    for side, collector in (('control', SOURCE / COLLECTOR), ('candidate', candidate_file)):
        tree = work / ('tree-' + side)
        shutil.copytree(SOURCE, tree, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
        shutil.copyfile(collector, tree / COLLECTOR)
        result = subprocess.run([DOTNET, 'build', str(tree / 'src/Ryujinx.Common/Ryujinx.Common.csproj'), '-c', 'Release', '-nologo',
                                 '-m:1', '-p:NuGetAudit=false', '-p:GeneratePackageOnBuild=false'],
                                capture_output=True, text=True, timeout=1800, env=ENVIRONMENT, cwd=tree)
        if result.returncode:
            print(result.stdout[-5000:], result.stderr[-2000:], flush=True)
        check(result.returncode == 0, 'production Ryujinx.Common builds: ' + side)
        builds[side] = sha((tree / COLLECTOR).read_bytes())
        shutil.rmtree(tree)

    def probe(side, collector):
        project = work / ('probe-' + side)
        project.mkdir()
        text = collector.read_text(encoding='utf-8-sig')
        seamed = text.replace('GC.GetGCMemoryInfo(', 'GcFeed.GetGCMemoryInfo(').replace('GC.CollectionCount(', 'GcFeed.CollectionCount(')
        check(seamed.count('GcFeed.') == text.count('GC.GetGCMemoryInfo(') + text.count('GC.CollectionCount(') and
              'GC.GetGCMemoryInfo(' not in seamed, side + ': every collector GC read goes through the seam')
        (project / 'EmbeddedPerformanceDiagnostics.cs').write_text(seamed)
        shutil.copyfile(SOURCE / JOURNAL, project / 'EmbeddedLaunchDiagnostics.cs')
        shutil.copyfile(ROOT / PROGRAM, project / 'Program.cs')
        (project / 'Probe.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType>'
                                              '<TargetFramework>net10.0</TargetFramework><AllowUnsafeBlocks>true</AllowUnsafeBlocks>'
                                              '<EnableDefaultCompileItems>false</EnableDefaultCompileItems><EnableNETAnalyzers>false</EnableNETAnalyzers>'
                                              '<NuGetAudit>false</NuGetAudit></PropertyGroup><ItemGroup><Compile Include="*.cs" /></ItemGroup></Project>')
        (project / 'global.json').write_text('{"sdk":{"version":"10.0.100","rollForward":"disable"}}')
        (project / 'NuGet.Config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
        run = subprocess.run([DOTNET, 'run', '--project', str(project), '-c', 'Release', '-v', 'q'],
                             text=True, capture_output=True, timeout=600, env=ENVIRONMENT)
        if run.returncode:
            print(run.stdout[-5000:], run.stderr[-3000:], flush=True)
        check(run.returncode == 0, 'probe runs: ' + side)
        return json.loads(next(line for line in run.stdout.splitlines() if line.startswith('{')))

    observed = {side: probe(side, path) for side, path in (('control', SOURCE / COLLECTOR), ('candidate', candidate_file))}

c, k = observed['control'], observed['candidate']


def real_lines(side, lines, fell_back, index):
    """Lines of a real background gen2 request. This host's runtime may itself run the requested background gen2 blocking
    (the device signature, both records sharing the index): then the control writes the stale background line and the
    candidate one flagged blocking line; otherwise both write the background line, unflagged."""
    if fell_back:
        if side == 'control':
            return any(l['kind'] == 'background' and l['index'] == index for l in lines) and \
                any(l['kind'] == 'fullBlocking' and l['index'] == index for l in lines)
        return any(l['kind'] == 'fullBlocking' and l['index'] == index and l['fellBackFromBackground'] == 1 for l in lines) and \
            not any(l['kind'] == 'background' and l['index'] == index for l in lines)
    return any(l['kind'] == 'background' and l['index'] == index and l['concurrent'] == 1 for l in lines) and \
        all(l['concurrent'] == (l['kind'] == 'background') for l in lines) and \
        all(l['fellBackFromBackground'] in (-1, 0) for l in lines)


for side, o in observed.items():
    check(o['backgroundObserved'] and o['backgroundObserved2'], side + ': this host ran the background gen2s the probe needs')
    check(real_lines(side, o['realBackgroundLines'], o['hostFallback1'], o['stalePayloadIndex']),
          side + ': a real background gen2 request: ' + json.dumps(o['realBackgroundLines']))
    check(len(o['realBackgroundLines']) <= 3, side + ': no line for collections before Start')
    check(o['fallbackIndex'] > o['stalePayloadIndex'], side + ': the stamped payload is an earlier collection')
h1, h2 = int(k['hostFallback1']), int(k['hostFallback2'])
# Control: the device signature reaches the journal as a blocking line plus a stale background line.
fb = c['fallbackLines']
check([line['kind'] for line in fb] == ['fullBlocking', 'background'] and all(line['index'] == c['fallbackIndex'] for line in fb) and
      abs(fb[1]['pauseMs0'] - c['stalePauseMs0']) < 0.002,
      'control: a background line with the fallback index and an earlier collection\'s payload (the defect)')
check(all(line['fellBackFromBackground'] == -1 and line['lohOccupiedAfterBytes'] == -1 for line in c['session1Lines']), 'control has no new fields')
# Candidate: one flagged blocking line, nothing stale.
fb = k['fallbackLines']
check(len(fb) == 1 and fb[0]['kind'] == 'fullBlocking' and fb[0]['index'] == k['fallbackIndex'] and fb[0]['concurrent'] == 0 and
      fb[0]['fellBackFromBackground'] == 1 and fb[0]['fallbacksInSession'] == 1 + h1 and fb[0]['finalSample'] is False,
      'candidate: one fullBlocking line flagged fellBackFromBackground, no stale background line: ' + str(fb))
for side, o in observed.items():
    check(o['linesAfterRepeatedSample'] == 0, side + ': the same pair is not reported again')
    check(real_lines(side, o['laterBackgroundLines'], o['hostFallback2'], o['laterBackgroundIndex']),
          side + ': a later real background gen2 is reported: ' + json.dumps(o['laterBackgroundLines']))
    check(len(o['laterBlockingLines']) == 1 and o['laterBlockingLines'][0]['index'] == o['laterBlockingIndex'] and
          o['laterBlockingLines'][0]['kind'] == 'fullBlocking', side + ': a later real blocking gen2 is reported')
    check(o['session1FinalLines'] == [], side + ': the final sample repeats nothing')
    check(o['session2BudgetLines'] == 16, side + ': 16 blocking lines before the budget is spent')
    check(o['maxDetailLength'] < 4000, side + ': bounded lines')
check(all(line['fallbacksInSession'] == 1 + h1 + h2 for line in k['laterBackgroundLines']) and
      k['laterBlockingLines'][0]['fellBackFromBackground'] == 0 and k['laterBlockingLines'][0]['fallbacksInSession'] == 1 + h1 + h2,
      'candidate: a forced blocking collection is not flagged; the session count stays')
check([line['fellBackFromBackground'] for line in k['session1Lines']].count(1) == 1 + h1 + h2,
      'candidate: one flagged line per fallback in session 1, none for real collections')
# Budget spent: the control writes the stale background line; the candidate writes nothing, then the flagged final line.
check([(line['kind'], line['index']) for line in c['suppressedFallbackLines']] == [('background', c['suppressedFallbackIndex'])],
      'control: the stale background line still written after the blocking budget is spent')
check(k['suppressedFallbackLines'] == [], 'candidate: no stale line, the blocking line over budget is counted')
fc, fk = c['session2FinalLines'], k['session2FinalLines']
check(len(fc) == 1 and fc[0]['kind'] == 'fullBlocking' and fc[0]['finalSample'] and fc[0]['index'] == c['suppressedFallbackIndex'],
      'control: final blocking line')
check(len(fk) == 1 and fk[0]['kind'] == 'fullBlocking' and fk[0]['finalSample'] and fk[0]['index'] == k['suppressedFallbackIndex'] and
      fk[0]['fellBackFromBackground'] == 1 and fk[0]['fallbacksInSession'] == 1 and fk[0]['suppressedLines'] == 1 and fk[0]['kindLine'] == 17,
      'candidate: the final sample writes the suppressed fallback, flagged and counted: ' + str(fk))
# A later real blocking gen2 while the background record still holds the stale index: the final sample writes nothing stale.
s3c = [(line['kind'], line['index']) for line in c['session3Lines']]
check(s3c == [('fullBlocking', c['session3FallbackIndex']), ('background', c['session3FallbackIndex']),
              ('fullBlocking', c['session3LaterBlockingIndex'])], 'control: session 3 lines ' + str(s3c))
s3k = [(line['kind'], line['index'], line['fellBackFromBackground'], line['finalSample']) for line in k['session3Lines']]
check(s3k == [('fullBlocking', k['session3FallbackIndex'], 1, False), ('fullBlocking', k['session3LaterBlockingIndex'], 0, False)],
      'candidate: the flagged line, then the later blocking one unflagged; the final sample writes no stale background: ' + str(s3k))
lines_k = k['session1Lines'] + k['session2FinalLines'] + k['suppressedFallbackLines'] + k['session3Lines']
check(all(line['lohOccupiedAfterBytes'] == max(0, line['lohSizeAfterBytes'] - line['lohFreeAfterBytes']) for line in lines_k) and
      any(line['lohOccupiedAfterBytes'] > 0 for line in lines_k), 'candidate: lohOccupiedAfterBytes = LOH size - LOH free')

inputs = [NATIVE, 'build-utils/melonx/adapt_bindless_array_deltas.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_gc_fallback_test.py', PROGRAM]
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True, env=ENVIRONMENT).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL is not None,
               sourceKind='finalPreparation' if FINAL else 'core658PreparationPlusCheckoutCollector',
               sourceBaseline=BASELINE, nativeBaseline={NATIVE: NATIVE_BASELINE},
               postimages={COLLECTOR: sha(candidate_text.encode()), JOURNAL: BASELINE[JOURNAL]},
               productionCommonBuilt=builds, sdk=sdk, physicalDeviceTested=False,
               candidateFallbackLine=k['fallbackLines'][0], controlFallbackLines=c['fallbackLines'],
               hostRuntimeFallbacks={side: [o['hostFallback1'], o['hostFallback2']] for side, o in observed.items()},
               inputs={p: sha((ROOT / p).read_bytes()) for p in inputs},
               limitation='Journal only. The fallback is the device signature fed through a test seam (the runtime\'s own '
                          'blocking and background records, the background index set to the blocking one); this host\'s runtime '
                          'shows the same signature only now and then (hostRuntimeFallbacks), which the checks accept. The detection relies on .NET 10.0.0 do_pre_gc and '
                          'get_completed_bgc_info and must be rechecked on a runtime change; a later background gen2 in the '
                          'same 5 s window replaces the stamped record, so such a fallback is reported as an ordinary blocking '
                          'line.')
out = ROOT / 'dist/melonx/gc-fallback-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk, candidateFallbackLine=k['fallbackLines'][0])))
