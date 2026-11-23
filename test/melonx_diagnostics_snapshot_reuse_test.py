#!/usr/bin/env python3
"""The engine's diagnostics snapshot keeps its bytes: native/melonx/EmbeddedLaunchDiagnostics.cs and the export in
native/melonx/EmbeddedRuntime.cs, against the delivered baseline as control.

Usage: melonx_diagnostics_snapshot_reuse_test.py <baseline prepared tree> [--candidate-source <final preparation>]

IPA 725, Hogwarts Legacy (pid 51986; private journals, aggregates only): the host's diagnostics queue (utility class,
priority 20) calls neostation_melonx_diagnostics every 300 ms for the whole session. Each call wrote the snapshot anew:
a stream grown to the size of the 64 events, a JSON writer and a copy. A collection that thread's allocation triggered
ran at its priority: gen0 2 673.6 ms, a 3 034 ms frame gap, the stall watch showing the thread in
gc_heap::mark_through_cards_for_segments with 15.6 ms of CPU in 961 ms while 148 threads waited.

Change: the snapshot's bytes are kept in one buffer and written again only when something they hold has changed (every
event and performance record takes a new Sequence; the stage, error code, error detail and journal error are
and the number of events are compared); the export copies them to the host's memory (SnapshotTo) instead of asking for
a managed copy. Snapshot() keeps its contract (a new array) for its other callers. The change is stated as exact pairs
in build-utils/melonx/core733_native.py, which the earlier gates reverse to recover the files they compare with.

Static: the final preparation holds this checkout's two files; each is the Core 731 file plus this one replacement.
Executed for control, candidate and three sensitivity variants: the side's real EmbeddedLaunchDiagnostics.cs and its
real export, called through the unmanaged entry point (test/melonx_diagnostics_snapshot_reuse/Program.cs):
- 192 steps (launch stages, a failure and Begin, performance records of the current and of other generations, repeated
  engine warnings, redaction, a text the JSON writer refuses, 150 long records through the 64-event ring, a crash
  record): after each one the export's bytes, asked twice, and Snapshot()'s are the same, and the chain of all answers
  (timestamps and process id aside) is the control's;
- the export's answers at the capacity's edges are the control's;
- with the ring full of long records, 1 000 polls without a change allocate nothing on the polling thread (the control:
  several times the snapshot each), and 200 polls each after a new record allocate nothing either;
- the performance observer is still asked at every poll and cannot break one;
- four threads recording while another polls: every answer is a whole snapshot, in order, of at most 64 events.
Sensitivity: without the comparison of the four strings, without the buffer reset, and without the comparison of the
sequence, the chain differs from the control's.
The production Ryujinx.Common project of the final preparation builds. Host runtime, not an iPhone: what the change
gives on the device is the absence of collections run by the host's diagnostics thread, to read in the next session's
stall records and gcPause summary. Writes dist/melonx/diagnostics-snapshot-reuse-checks.json.
"""
from pathlib import Path
import hashlib, json, os, platform, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
BASELINE_SOURCE = Path(sys.argv[1]).resolve()
FINAL_PREPARATION = '--candidate-source' in sys.argv
FINAL_SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1]).resolve() if FINAL_PREPARATION else None
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
import core733_native as native_edits  # noqa: E402

DOTNET = os.environ.get('DOTNET', 'dotnet')
HARNESS = ROOT / 'test/melonx_diagnostics_snapshot_reuse'
JOURNAL, RUNTIME = 'src/Ryujinx.Common/EmbeddedLaunchDiagnostics.cs', 'src/Ryujinx.Library/EmbeddedRuntime.cs'
NATIVE = {JOURNAL: ROOT / 'native/melonx/EmbeddedLaunchDiagnostics.cs', RUNTIME: ROOT / 'native/melonx/EmbeddedRuntime.cs'}
# The exact pairs of the change (the Core 731 files' text and this checkout's), shared with the earlier gates that
# reverse them.
MARKER = '    // The snapshot is written manually: NativeAOT cannot assume reflection\n'
OLD_SNAPSHOT, OLD_EXPORT, NEW_EXPORT = native_edits.SNAPSHOT_OLD, native_edits.EXPORT_OLD, native_edits.EXPORT_NEW
EXPORT = '    public static unsafe int EmbeddedDiagnostics(byte* output, int capacity)'
ATTRIBUTE = '    [UnmanagedCallersOnly(EntryPoint = "neostation_melonx_diagnostics")]\n'
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def sha(data):
    return hashlib.sha256(data if isinstance(data, bytes) else Path(data).read_bytes()).hexdigest()


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
candidate = {name: path.read_text(encoding='utf-8-sig') for name, path in NATIVE.items()}
control = {name: (BASELINE_SOURCE / name).read_text(encoding='utf-8-sig') for name in NATIVE}
if FINAL_PREPARATION:
    for name, path in NATIVE.items():
        check((FINAL_SOURCE / name).read_bytes() == path.read_bytes(), 'the final preparation holds this checkout\'s ' + name)
journal, runtime = candidate[JOURNAL], candidate[RUNTIME]
check(JOURNAL == native_edits.JOURNAL and RUNTIME == native_edits.RUNTIME and {name: str(path.relative_to(ROOT)) for name, path in NATIVE.items()} == native_edits.NATIVE and
      OLD_SNAPSHOT.startswith(MARKER) and native_edits.SNAPSHOT_NEW.startswith(MARKER), 'the pairs are those of these two files')
for name in NATIVE:
    restored = native_edits.reverse(candidate[name], name)
    check(sha(restored.encode()) == native_edits.CORE731[name] and native_edits.apply(restored, name) == candidate[name],
          name + ' is the Core 731 file with the one replacement of core733_native')
check(journal.count(MARKER) == 1 and journal.endswith(native_edits.SNAPSHOT_NEW) and runtime.count(NEW_EXPORT) == 1,
      'the journal\'s snapshot members and the export\'s body are the replaced parts')
check(control[JOURNAL].count(OLD_SNAPSHOT) == 1 and control[JOURNAL].endswith(OLD_SNAPSHOT) and control[RUNTIME].count(OLD_EXPORT) == 1,
      'the control (delivered baseline) writes the snapshot anew at every call and copies it')
for name in (JOURNAL, RUNTIME):
    check(ATTRIBUTE + EXPORT in candidate[RUNTIME] and ATTRIBUTE + EXPORT in control[RUNTIME], 'the export keeps its entry point')
added = journal[journal.index(MARKER):]
snapshot = member(journal, '    public static byte[] Snapshot()')
check('WriteSnapshot();' in snapshot and 'return SnapshotBuffer.WrittenSpan.ToArray();' in snapshot and 'MemoryStream' not in added,
      'Snapshot() still returns a new array, from the kept bytes')
writer = member(journal, '    private static void WriteSnapshot()')
check(writer.index('SnapshotSequence = -1;') < writer.index('SnapshotBuffer.ResetWrittenCount();') < writer.index('json.WriteStartObject();') <
      writer.index('json.Flush();') < writer.index('SnapshotSequence = sequence;') and
      'SnapshotSequence == sequence && SnapshotEvents == Events.Count && SnapshotStage == stage &&' in writer and
      'SnapshotErrorCode == errorCode && SnapshotErrorDetail == errorDetail && SnapshotJournalFailure == journalFailure)' in writer and
      writer.count('SnapshotEvents = Events.Count;') == 1,
      'kept only when the sequence, the number of events and the four strings are the ones written; not kept until written whole')
copy = member(journal, '    public static unsafe int SnapshotTo(byte* output, int capacity)')
check('if (output == null || capacity <= data.Length) return -data.Length;' in copy and
      'data.CopyTo(new Span<byte>(output, capacity)); output[data.Length] = 0;' in copy and copy.count('lock (Gate)') == 1 and
      'Volatile.Read(ref PerformanceObserver)?.Invoke();' in copy and 'ToArray' not in copy,
      'SnapshotTo answers as the export did, under the journal\'s gate, without a managed copy')
# Every writer of what the snapshot holds either takes a new Sequence or assigns one of the four compared strings.
head = journal[:journal.index(MARKER)]
check(head.count('++Sequence') == 2 and head.count('Events.Enqueue((++Sequence,') == 1 and head.count('Performance = (++Sequence,') == 1 and
      head.count('Events.Dequeue()') == 1 and head.count('PrecedingPerformance = ') == 1 and
      head.index('PrecedingPerformance = ') < head.index('Performance = (++Sequence,'),
      'events and performance records change only with a new Sequence')

# --- Executed: control, candidate and sensitivity variants ---
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1')
WORK = Path(tempfile.mkdtemp(prefix='melonx-diagnostics-snapshot-')).resolve()
strings = (' && SnapshotStage == stage &&\n'
           '            SnapshotErrorCode == errorCode && SnapshotErrorDetail == errorDetail && SnapshotJournalFailure == journalFailure)')
VARIANTS = {
    'control': None,
    'candidate': None,
    # Sensitivity: each removes one part of the candidate.
    'stringsNotCompared': (strings, ')'),
    'bufferNotReset': ('        SnapshotBuffer.ResetWrittenCount();\n', ''),
    # (The number of events changes with almost every new sequence, so it is left out with it.)
    'sequenceNotCompared': ('SnapshotSequence == sequence && SnapshotEvents == Events.Count', 'SnapshotSequence != -1'),
}
reports = {}
for variant, change in VARIANTS.items():
    side = control if variant == 'control' else candidate
    text = side[JOURNAL]
    if change:
        check(text.count(change[0]) == 1, variant + ': one site to alter')
        text = text.replace(change[0], change[1])
    fixture = WORK / variant
    fixture.mkdir()
    (fixture / 'EmbeddedLaunchDiagnostics.cs').write_text(text)
    (fixture / 'Export.cs').write_text(
        'using System;\nusing System.Runtime.InteropServices;\nusing Ryujinx.Common;\n\nnamespace Ryujinx.Library\n{\n'
        'public static unsafe class Export\n{\n' + ATTRIBUTE + member(side[RUNTIME], EXPORT) + '\n}\n}\n')
    shutil.copyfile(HARNESS / 'Program.cs', fixture / 'Program.cs')
    (fixture / 'Fixture.csproj').write_text(
        '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
        '<Nullable>disable</Nullable><AllowUnsafeBlocks>true</AllowUnsafeBlocks><NuGetAudit>false</NuGetAudit>'
        '<ServerGarbageCollector>false</ServerGarbageCollector><TieredPGO>false</TieredPGO>'
        '<NoWarn>CS0649;CS0414;CS0169;CS0067;CS8321;CS0162;CS8632;SYSLIB1054</NoWarn></PropertyGroup></Project>\n')
    build = subprocess.run([DOTNET, 'build', str(fixture / 'Fixture.csproj'), '-c', 'Release', '-nologo', '-p:NuGetAudit=false'],
                           capture_output=True, text=True, timeout=900, env=environment, cwd=fixture)
    if build.returncode:
        print('\n'.join(line for line in build.stdout.splitlines() if ': error ' in line)[:6000], flush=True)
    check(build.returncode == 0, variant + ' fixture builds with the side\'s real journal and export')
    run = subprocess.run([DOTNET, str(fixture / 'bin/Release/net10.0/Fixture.dll'), variant],
                         capture_output=True, text=True, timeout=900, env=environment, cwd=fixture)
    if run.returncode:
        print(run.stdout[-4000:], run.stderr[-4000:], flush=True)
    check(run.returncode == 0, variant + ' fixture runs')
    reports[variant] = json.loads(run.stdout.strip().splitlines()[-1])
if os.environ.get('MELONX_TEST_REPORTS'):
    Path(os.environ['MELONX_TEST_REPORTS']).write_text(json.dumps(reports, indent=1))
c, k = reports['control'], reports['candidate']

# Functional: the same answers, step by step.
fc, fk = c['functional'], k['functional']
check(fc['steps'] == fk['steps'] == 192 and fc['exportTwiceAndSnapshotEqual'] == fk['exportTwiceAndSnapshotEqual'] == 192 and
      fc['firstDifferences'] == fk['firstDifferences'] == [], 'after each step the export, asked twice, and Snapshot() agree: ' + json.dumps([fc, fk]))
check(fk['digest'] == fc['digest'], 'the chain of the 192 answers is the control\'s: ' + json.dumps([fc, fk]))
check(fk['parsed'] == fc['parsed'] and fk['unparsed'] == fc['unparsed'] == 0 and fk['statusNotZero'] == fc['statusNotZero'] and
      fk['parsed'] + fk['statusNotZero'] == 192 and fk['maxEvents'] == fc['maxEvents'] == 64 and fk['maxBytes'] == fc['maxBytes'] > 100_000 and
      fk['journalLines'] == fc['journalLines'] > 150,
      'every answer is whole JSON or the same refusal; the ring fills to 64 long records; the file journal is written alike')

# The export's answers at the capacity's edges.
size = k['capacity']['size']
check(k['capacity'] == dict(size=size, nullOutput=-size, zeroCapacity=-size, capacityOfTheSize=-size, untouchedWhenRefused=True,
                            capacityOfTheSizePlusOne=0, terminated=True, sameBytes=True) and c['capacity'] == k['capacity'],
      'capacity edges answered as before: ' + json.dumps([c['capacity'], k['capacity']]))

# Allocations of the polling thread.
ac, ak = c['allocations'], k['allocations']
check(ak['snapshotBytes'] == ac['snapshotBytes'] > 100_000 and ac['quietBytesPerPoll'] >= 2 * ac['snapshotBytes'] and
      ac['changingBytesPerPoll'] >= 2 * ac['snapshotBytes'], 'control: every poll allocates several times the snapshot: ' + json.dumps(ac))
check(ak['quietBytesPerPoll'] == 0 and ak['quietWritten'] == 0 and ak['quietKept'] == 1000,
      'candidate: 1 000 polls without a change write nothing and allocate nothing: ' + json.dumps(ak))
check(ak['changingBytesPerPoll'] == 0 and ak['changingWritten'] == 200 and ak['changingKept'] == 0,
      'candidate: a poll after a new record writes into the kept buffer and allocates nothing: ' + json.dumps(ak))

check(c['observer'] == k['observer'] == dict(calls=30, status=0), 'the observer is asked at every poll and cannot break one')
expected = dict(polls=True, invalid=0, unordered=0, overfull=0, backwards=0, finalEqualsSnapshot=True, finalEvents=64)
check(c['concurrent'] == expected and k['concurrent'] == expected, 'recording threads and a poller: whole, ordered snapshots: ' + json.dumps(k['concurrent']))

# Sensitivity: each altered candidate answers differently from the control.
for variant in ('stringsNotCompared', 'bufferNotReset', 'sequenceNotCompared'):
    check(reports[variant]['functional']['digest'] != fc['digest'], 'sensitivity: ' + variant + ' must not give the control\'s answers')
check(fk['watched'] == fc['watched'] and len(fc['watched']) == 5, 'the watched answers are the control\'s')
strings_only = reports['stringsNotCompared']['functional']['watched']
check(strings_only['file begin'] == fc['watched']['file begin'] and strings_only['begin again'] != fc['watched']['begin again'] and
      strings_only['performance refused'] != fc['watched']['performance refused'] and strings_only['long 149'] == fc['watched']['long 149'],
      'sensitivity: without the strings, the answers after Begin and after a refused performance "begin" are stale, the others right')
check(reports['bufferNotReset']['functional']['unparsed'] > 0 and reports['bufferNotReset']['concurrent']['invalid'] > 0,
      'sensitivity: without the reset, a rewritten snapshot is not whole JSON')
check(reports['sequenceNotCompared']['functional']['watched']['performance sample'] != fc['watched']['performance sample'] and
      reports['sequenceNotCompared']['functional']['watched']['long 149'] != fc['watched']['long 149'] and
      reports['sequenceNotCompared']['concurrent']['finalEvents'] != 64 and reports['sequenceNotCompared']['allocations']['changingWritten'] == 0,
      'sensitivity: without the sequence, new records never reach the snapshot')

# The production project of the final preparation builds with the file.
built = False
if FINAL_PREPARATION:
    tree = WORK / 'production'
    shutil.copytree(FINAL_SOURCE, tree, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
    build = subprocess.run([DOTNET, 'build', str(tree / 'src/Ryujinx.Common/Ryujinx.Common.csproj'), '-c', 'Release', '-nologo', '-m:1', '-p:NuGetAudit=false'],
                           capture_output=True, text=True, timeout=1800, env=environment, cwd=tree)
    if build.returncode:
        print('\n'.join(line for line in build.stdout.splitlines() if ': error ' in line)[:6000], flush=True)
    check(build.returncode == 0, 'the production Ryujinx.Common project of the final preparation builds')
    built = True
shutil.rmtree(WORK)

inputs = ['native/melonx/EmbeddedLaunchDiagnostics.cs', 'native/melonx/EmbeddedRuntime.cs', 'build-utils/melonx/core733_native.py',
          'test/melonx_diagnostics_snapshot_reuse_test.py', 'test/melonx_diagnostics_snapshot_reuse/Program.cs']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparation' if FINAL_PREPARATION else 'checkoutAgainstBaseline',
               postimages={name: sha(FINAL_SOURCE / name) for name in NATIVE} if FINAL_PREPARATION else {},
               preimages={name: sha(BASELINE_SOURCE / name) for name in NATIVE},
               productionCommonBuilt=built,
               comparison=dict(steps=fk['steps'], sameAnswersAsControl=fk['digest'] == fc['digest'],
                               snapshotBytes=ak['snapshotBytes'], controlBytesPerQuietPoll=ac['quietBytesPerPoll'],
                               candidateBytesPerQuietPoll=ak['quietBytesPerPoll'], controlBytesPerChangingPoll=ac['changingBytesPerPoll'],
                               candidateBytesPerChangingPoll=ak['changingBytesPerPoll'], sensitivityVariantsFailed=3),
               reports=reports, sdk=sdk, host=platform.system(), physicalDeviceTested=False,
               deviceEvidence='IPA 725, Hogwarts Legacy, pid 51986 (private journals): gen0 collection of 2 673.6 ms run by the host\'s '
                              'diagnostics thread (priority 20; 15.6 ms of CPU in 961 ms; 148 threads waiting), frame gap 3 034 ms; the '
                              'thread polls this snapshot every 300 ms',
               inputs={name: sha(ROOT / name) for name in inputs},
               limitation='Host runtime (the allocation counts are this runtime\'s; the ring of the fixture holds 64 records of about '
                          '2.6 KiB). What the device gains is read in the next session: no collection run by the diagnostics thread in '
                          'the stall records, the gcPause summary, the background collections per minute.')
out = ROOT / 'dist/melonx/diagnostics-snapshot-reuse-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
