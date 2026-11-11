#!/usr/bin/env python3
"""Durable gen2 collection lines (stage "gcEvent") of the performance collector, on the real Core 649 preparation.

Usage: melonx_gc_events_test.py <Core 649 prepared MeloNX tree>
       melonx_gc_events_test.py <Core 649 prepared tree> --candidate-source <final preparation containing the change>

Finding (IPA 650, private maintainer logs, two Hogwarts sessions in one process): a 756 ms blocking compacting gen2
collection during the second session's gameplay, and each closed session's heap surviving the forced teardown
collection. The performance samples only carry the latest collection of any kind, so neither the blocking collection's
trigger inputs nor the survivors of each gen2 are recorded.

Change (native/melonx/EmbeddedPerformanceDiagnostics.cs, copied into the Core as
src/Ryujinx.Common/EmbeddedPerformanceDiagnostics.cs, then edited by adapt_bindless_array_deltas): each sample whose
latest blocking (GCKind.FullBlocking) or background gen2 index changed writes one Core journal line per new index,
in index order. Each kind has its own budget of 16 lines per session, so background lines cannot starve blocking
ones; lines over budget are counted in suppressedLines. The final sample (after Library.cs's teardown collections)
is never bounded and also reports the latest collection whose line was suppressed: at most 2 * 16 + 2 lines per
session. Instrumentation only.

The control is the Core 649 preparation's collector; the candidate is this checkout's collector with the array-delta
edits applied as prepare_embedded.py applies them (and, with --candidate-source, it must equal the final preparation).
Static checks: the candidate is the control plus inserted lines only, at the four expected places (no hot-path,
lock or policy change), no inserted "begin" status, no collection triggered. Both Ryujinx.Common projects build. The
real collector and journal (control and candidate) run the same probe with forced blocking compacting collections
(GC.Collect(2, Forced, true, true)) and background gen2s (required; the test fails if this host's runtime runs
none): the control writes no gcEvent line, the candidate writes exactly one per new collection with plausible fields,
none before Start, a per-window gen2 count, a background and a blocking line of one window in index order, 16 per kind
and session with the suppressed count, a background line after the blocking budget is spent, and a final line after
the budget is spent (both for a collection after the last sample and for a suppressed one); the performance sample
keys are unchanged. The existing performance fixture (test/melonx_performance_diagnostics/Program.cs) runs on both too.
Writes dist/melonx/gc-events-checks.json. No device.
"""
from pathlib import Path
import argparse, difflib, hashlib, json, os, re, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
parser.add_argument('source', type=Path, help='Core 649 prepared tree (control)')
parser.add_argument('--candidate-source', type=Path, help='Final preparation containing the change')
args = parser.parse_args()
SOURCE = args.source.resolve()
FINAL = args.candidate_source.resolve() if args.candidate_source else None
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
from adapt_session import once  # noqa: E402
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import journal_of_earlier_cores  # noqa: E402
from adapt_bindless_array_deltas import DIAGNOSTIC_EDITS  # noqa: E402

COLLECTOR = 'src/Ryujinx.Common/EmbeddedPerformanceDiagnostics.cs'
JOURNAL = 'src/Ryujinx.Common/EmbeddedLaunchDiagnostics.cs'
NATIVE = 'native/melonx/EmbeddedPerformanceDiagnostics.cs'
# Core 649 preparation (dma-core-contract.json preparedMembers) and the collector it was prepared from.
BASELINE = {COLLECTOR: '7de6a7a29cc02ebf7878bebf5bb557886f2efb517fece493214de72ca4434a81',
            JOURNAL: 'eb143b14be90261baf92788713a8bb73b11d9d921f420bf2b9b7ad65f5068658'}
NATIVE_BASELINE = '95732befcbfe919f6f5a16c40621dfd7ee9b94c47d510806aebf020ef761ca39'
EXISTING_FIXTURE_CHECKS = 122  # resultDetails.checks pinned for performance-diagnostics in dma-core-contract.json
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


for name, expected in BASELINE.items():
    check(sha((SOURCE / name).read_bytes()) == expected, 'not the Core 649 preparation: ' + name)

with tempfile.TemporaryDirectory(prefix='melonx-gc-events-') as temporary:
    work = Path(temporary).resolve()
    # The control collector is the pinned native collector plus exactly the array-delta edits.
    reverse = work / 'reverse.cs'
    shutil.copyfile(SOURCE / COLLECTOR, reverse)
    for old, new in reversed(DIAGNOSTIC_EDITS):
        once(reverse, new, old)
    check(sha(reverse.read_bytes()) == NATIVE_BASELINE, 'Core 649 collector is the pinned native one plus the array-delta edits')
    candidate_file = work / 'candidate.cs'
    shutil.copyfile(ROOT / NATIVE, candidate_file)
    for old, new in DIAGNOSTIC_EDITS:
        once(candidate_file, old, new)
    if FINAL:
        check((FINAL / COLLECTOR).read_bytes() == candidate_file.read_bytes(), 'final preparation holds this collector')
        # Core 725 gives the journal room at the start of a process (ConfigureJournal, MeloNX-core.log only) and Core 733
        # keeps the snapshot's bytes (core733_native); nothing else differs from the journal of the control, and the
        # candidate probe compiles the final one.
        check(journal_of_earlier_cores((FINAL / JOURNAL).read_text(encoding='utf-8-sig')) ==
              (SOURCE / JOURNAL).read_text(encoding='utf-8-sig'), 'final preparation keeps the journal, but for its room at the start of a process and its kept snapshot')
    control_text = (SOURCE / COLLECTOR).read_text(encoding='utf-8-sig')
    candidate_text = candidate_file.read_text(encoding='utf-8-sig')

    # Static: inserted lines only, at the expected places.
    a, b = control_text.split('\n'), candidate_text.split('\n')
    opcodes = [op for op in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes() if op[0] != 'equal']
    check(all(op[0] == 'insert' for op in opcodes), 'candidate is the control plus inserted lines: ' + str(opcodes[:3]))
    anchors = [a[op[1] - 1].strip() for op in opcodes]
    check(anchors == ['public readonly int[] PreviousCollections = new int[3];',
                      'for (int i = 0; i < 3; i++) PreviousCollections[i] = GC.CollectionCount(i);',
                      'string report = Capture(epoch, now, finalReport);',
                      '}'], 'insertions at the epoch fields, the epoch start, the sample emission and before Capture: ' + str(anchors))
    # difflib may align the block's closing brace with Emit's: either way it ends right before Capture.
    check('private static string Capture(Epoch epoch, long now, bool final)' in [line.strip() for line in a[opcodes[3][1]:opcodes[3][1] + 2]] and
          ''.join(a[opcodes[3][1] - 1:opcodes[3][1] + 1]).strip() in ('}', '}    }'),
          'the new methods sit just before Capture')
    inserted = '\n'.join('\n'.join(b[op[3]:op[4]]) for op in opcodes)
    check(b[opcodes[2][3]:opcodes[2][4]] == ['            RecordGcEvents(epoch, finalReport);'], 'one call in the sample emission')
    check(inserted.count('EmbeddedLaunchDiagnostics.Record(') == 1 and
          'EmbeddedLaunchDiagnostics.Record("gcEvent", kind, detail:' in inserted, 'one gcEvent journal call')
    check('string kind = fullBlocking ? "fullBlocking" : "background";' in inserted and '"begin"' not in inserted and
          'EmbeddedLaunchDiagnostics.Record("gcEvent", kind,' in inserted, 'statuses fullBlocking/background, never begin')
    check(not re.search(r'GC\.Collect\(|GC\.AddMemoryPressure|GCSettings|Interlocked|lock \(|Monitor\.|Thread\.|Volatile\.Write|_current',
                        inserted), 'no collection, GC setting, lock, thread or collector-state change')
    check('catch { } // Observability must never change the emulator\'s result.' in inserted, 'GC event failures are contained')
    check('MaxGcEventLinesPerKind = 16;' in inserted and inserted.count('MaxGcEventLinesPerKind') == 3 and
          inserted.count('if (!final && kindLines >= MaxGcEventLinesPerKind) { epoch.SuppressedGcEventLines++; return; }') == 1 and
          'int kindLines = fullBlocking ? epoch.FullBlockingGcEventLines : epoch.BackgroundGcEventLines;' in inserted,
          'bounded at 16 per kind and session, except the final sample; suppressed lines counted')

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

    def probe(side, collector, program):
        project = work / (side + '-' + Path(program).stem)
        shutil.rmtree(project, ignore_errors=True)  # a probe run again after a host-runtime fallback starts clean
        project.mkdir()
        shutil.copyfile(collector, project / 'EmbeddedPerformanceDiagnostics.cs')
        shutil.copyfile((FINAL if FINAL and side != 'control' else SOURCE) / JOURNAL, project / 'EmbeddedLaunchDiagnostics.cs')
        shutil.copyfile(ROOT / program, project / Path(program).name)
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
        check(run.returncode == 0, 'probe runs: ' + side + ' ' + program)
        return json.loads(next(line for line in run.stdout.splitlines() if line.startswith('{')))

    # The probe needs this host runtime's real background gen2s. .NET 10.0.0 sometimes runs a requested one blocking
    # (dotnet/runtime#119383, docs/melonx-bgc-fallback-2026-11-05.md); the probe counts those host fallbacks. Only then
    # is the probe run again (at most three runs, all recorded); a run without a host fallback is never repeated.
    probe_runs = []
    for attempt in range(3):
        observed = {side: probe(side, path, 'test/melonx_performance_diagnostics/GcEventsProgram.cs')
                    for side, path in (('control', SOURCE / COLLECTOR), ('candidate', candidate_file))}
        probe_runs.append({side: value.get('hostFallbacks', 0) for side, value in observed.items()})
        if not any(probe_runs[-1].values()):
            break
    check(not any(probe_runs[-1].values()), 'a probe run without a host-runtime background fallback: ' + str(probe_runs))
    existing = {side: probe(side, path, 'test/melonx_performance_diagnostics/Program.cs')
                for side, path in (('control', SOURCE / COLLECTOR), ('candidate', candidate_file))}

control, candidate = observed['control'], observed['candidate']
# Control: the delivered collector writes no gcEvent line at all.
check(control['totalLines'] == 0 and control['linesAfterForcedGc'] == 0 and control['ringGcEvents'] == 0, 'control writes no gcEvent line')
check(control['performanceKeys'] == candidate['performanceKeys'], 'performance sample keys unchanged')
check(control['journalError'] == candidate['journalError'] == '', 'journal writes succeed')
# Candidate: nothing for collections before Start or in idle windows, one line per new forced collection.
check(candidate['linesAfterStart'] == 0 and candidate['linesAfterIdleSample'] == 0, 'no line for a collection before Start')
check(candidate['linesAfterForcedGc'] == 1 and candidate['ringGcEvents'] == 1, 'one line (Core file and ordinary ring) for one forced GC')
check(candidate['linesAfterTwoIdleSamples'] == 1, 'the same collection is not reported twice')
check(candidate['firstStatus'] == 'fullBlocking' and candidate['firstNativeStatus'] == 0, 'status fullBlocking, code 0')
detail = candidate['firstDetail']
check(detail['kind'] == 'fullBlocking' and detail['index'] == candidate['expectedIndex'] and detail['generation'] == 2 and
      detail['concurrent'] == 0 and detail['compacted'] == 1, 'index, generation 2, blocking, compacting')
check(detail['line'] == 1 and detail['kindLine'] == 1 and detail['maxLinesPerKind'] == 16 and detail['suppressedLines'] == 0 and
      detail['sessionGeneration'] == 1 and detail['finalSample'] is False and detail['newInWindow'] is True and detail['schema'] == 1,
      'line ordinals, bound and session')
check(len(detail['pauseMs']) == 2 and detail['pauseMs'][0] > 0 and detail['pauseMs'][1] >= 0 and
      abs(detail['pauseMs'][0] - candidate['expectedPauseMs']) < 0.002, 'pause durations in ms')
check(len(detail['gen2']) == 4 and len(detail['loh']) == 4 and detail['gen2'][0] >= 0 and detail['gen2'][2] > 0 and
      all(v >= 0 for v in detail['gen2'] + detail['loh']) and
      detail['generationColumns'] == 'sizeBeforeBytes,fragmentationBeforeBytes,sizeAfterBytes,fragmentationAfterBytes',
      'gen2 and LOH before/after sizes and fragmentation')
check(detail['promotedBytes'] > 0 and detail['heapSizeBytes'] > 0 and detail['totalCommittedBytes'] > 0, 'promotions, heap and committed bytes')
check(detail['highMemoryLoadThresholdBytes'] > 0 and detail['memoryLoadBytes'] >= 0 and detail['gen2CollectionsInWindow'] == 1,
      'memory load inputs and window count')
check(candidate['linesAfterFortyMore'] == 16 and candidate['lineOrdinals'] == list(range(1, 17)) and candidate['indicesStrictlyIncreasing'],
      'at most 16 blocking lines per session before the final sample, ordered')
check(candidate['windowCounts'] == [1] * 16, 'gen2CollectionsInWindow counts the gen2s since the previous sample, not the session')
check(candidate['linesAfterStop1'] == 17 and candidate['stop1Final'] is True and candidate['stop1IndexIsTeardown'] and
      candidate['stop1NewInWindow'] is True and candidate['stop1Window'] == 1 and candidate['stop1Suppressed'] == 25 and
      candidate['stop1KindLine'] == 17, 'after the budget is spent, the final sample writes the teardown collection with the suppressed count')
check(candidate['session2LinesAfterStart'] == 17 and candidate['session2NewLines'] == 2 and candidate['session2Windows'] == [1, 2] and
      candidate['session2Finals'] == [False, True] and candidate['session2KindLines'] == [1, 2] and
      candidate['session2Generation'] == 2 and candidate['session2IndexIsLatest'],
      'next session: fresh budget, previous collections not repeated, per-window counts 1 then 2, final sample reports the latest')
check(candidate['backgroundObserved'] and candidate['backgroundObserved2'],
      'this host ran the background gen2s the background half of the probe needs')
check(candidate['mixedStatuses'] == ['background', 'fullBlocking'] and candidate['mixedIndicesStrictlyIncreasing'] and
      candidate['mixedIndicesMatch'] and all(w >= 2 for w in candidate['mixedWindows']),
      'one window with a background then a blocking gen2: two lines, background first, indices increasing')
check(candidate['backgroundConcurrent'] == 1 and candidate['backgroundGeneration'] == 2, 'background gen2 line')
check(candidate['session3BlockingSpent'] == 14 and candidate['lateStatuses'] == ['background'] and candidate['lateSuppressed'] == [2],
      'blocking budget spent (2 suppressed, counted): a background line is still written, carrying the count')
check(candidate['session3FinalLines'] == 1 and candidate['session3FinalKind'] == 'fullBlocking' and candidate['session3FinalSample'] is True and
      candidate['session3FinalIndexIsSuppressed'] and candidate['session3FinalNewInWindow'] is False and
      candidate['session3FinalWindow'] == 0 and candidate['session3FinalSuppressed'] == 2 and candidate['session3FinalKindLine'] == 17,
      'no collection after the last sample: the final sample writes the latest, suppressed, blocking collection')
check(candidate['session3Lines'] <= 2 * 16 + 2, 'per-session hard bound')
check(set(candidate['statuses']) <= {'fullBlocking', 'background'} and candidate['maxDetailLength'] < 4000, 'statuses and bounded detail')
for side in ('control', 'candidate'):
    check(existing[side]['result'] == 'passed' and existing[side]['checks'] == EXISTING_FIXTURE_CHECKS and
          existing[side]['actualProductionCollector'] and existing[side]['hotCounterAllocatedBytes'] == 0 and
          existing[side]['hotScopeAllocatedBytes'] == 0, 'existing performance fixture passes: ' + side)

inputs = [NATIVE, 'build-utils/melonx/adapt_bindless_array_deltas.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_gc_events_test.py', 'test/melonx_performance_diagnostics/GcEventsProgram.cs',
          'test/melonx_performance_diagnostics/Program.cs']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True, env=ENVIRONMENT).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL is not None,
               sourceKind='finalPreparation' if FINAL else 'core649PreparationPlusCheckoutCollector',
               sourceBaseline=BASELINE, nativeBaseline={NATIVE: NATIVE_BASELINE},
               postimages={COLLECTOR: sha(candidate_text.encode()), JOURNAL: sha(((FINAL or SOURCE) / JOURNAL).read_bytes())},
               productionCommonBuilt=builds, sdk=sdk, physicalDeviceTested=False,
               backgroundGcObserved=candidate['backgroundObserved'], serverGc=candidate['serverGc'], hostFallbackProbeRuns=probe_runs,
               candidateLines=dict(total=candidate['totalLines'], statuses=candidate['statuses'], maxDetailLength=candidate['maxDetailLength']),
               existingFixtureChecks={side: existing[side]['checks'] for side in existing},
               hostSampleDetail=candidate['firstDetail'],
               inputs={p: sha((ROOT / p).read_bytes()) for p in inputs},
               limitation='Journal only, host runtime (workstation concurrent GC, not Apple NativeAOT); the test fails on a host '
                          'that runs no background gen2. A sample sees only the latest blocking and the latest background gen2; '
                          'earlier ones in the same 5 s window are counted, not described. Lines over the 16-per-kind budget '
                          'are counted (suppressedLines), not described, except the latest of each kind in the final sample. '
                          'What triggered the device collection is known only from a device run with these lines.')
out = ROOT / 'dist/melonx/gc-events-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk, backgroundGcObserved=candidate['backgroundObserved'],
                      candidateLines=receipt['candidateLines'], existingFixtureChecks=receipt['existingFixtureChecks'])))
