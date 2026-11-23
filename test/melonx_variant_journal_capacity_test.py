#!/usr/bin/env python3
"""The pipeline variant journal holds 4096 states in 8 MiB and loads no more than that (adapt_variant_journal_capacity),
before and after, real engine code.

Usage: melonx_variant_journal_capacity_test.py <final preparation containing the adapter>
       melonx_variant_journal_capacity_test.py <control> --candidate-source <final preparation containing the adapter>

Control is the preparation with the adapter reversed (melonx_adapter_control); candidate is the adapter applied to it.
For each, the production PipelineVariantJournal (cut out of PipelineCacheManager.cs) runs with doubles for the logger,
the engine journal and the replaying program (test/melonx_variant_journal_capacity/Program.cs):
- a session shaped like Hogwarts Legacy's session 40 in the IPA 821 log (counts only): the title's file read as the log
  reads it (2028 states of 426 programs, 33 older than 8 sessions, 3330 lines), 1168 of the loaded states met (853
  created late by a draw, 315 built for skipped draws) and 398 states new to the journal (211 and 187), mixed. The
  control ends as the log does ("2048 of 2048 states, given up for newer states 378"); the candidate holds the 2426
  states and gives up none. At the next launch every program offers its states and the player draws everything the two
  sessions drew: the control replays 2048 and creates 378 late, the candidate replays the 2426 and creates none. Run
  with and without the policy Hogwarts Legacy runs under;
- across builds: the candidate reads the file the control's session left (the 378 given-up states are still in it) and
  the control reads the candidate's (a rollback: 2048 loaded, 378 given up at the load);
- the bounds: a journal filled with the largest variants, every state replayed (one schedule each, two in flight at
  most) and refreshed (the file passes its bound and is compacted, no line lost), 500 states over the bound given up in
  the eviction order, the file never over MaxFileBytes; the arithmetic of the largest compaction;
- the load's cost on this host for a full journal of usual states (time, bytes allocated, heap held per state, the 426
  offers);
- files of another version, schema or magic, empty, cut, damaged, noise, and 40 MiB long: none throws, the same states
  are loaded by both variants except from the over-long file, of which the candidate reads its bound only.
The candidate's production Vulkan assembly is built. No device: host times, no Vulkan creation.
Writes dist/melonx/variant-journal-capacity-checks.json.
"""
from pathlib import Path
import hashlib, json, os, re, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
FINAL_SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, files_edited_later  # noqa: E402
_HOLD = []
SOURCE, FINAL_PREPARATION = control_source(FINAL_SOURCE, 'adapt_variant_journal_capacity', _HOLD)
from adapt_variant_journal_capacity import apply, BASELINE, MANAGER, PAIRS  # noqa: E402

VULKAN = 'src/Ryujinx.Graphics.Vulkan/'
DOTNET = os.environ.get('DOTNET', 'dotnet')
FIXTURE = ROOT / 'test/melonx_variant_journal_capacity'
MIB = 1024 * 1024
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


def journal_class(text):
    """PipelineVariantJournal as the file holds it: from its declaration to the namespace's closing brace."""
    return text[text.index('    sealed class PipelineVariantJournal'):text.rindex('}')]


check(FINAL_PREPARATION, 'the source is a final preparation containing the adapter')
for name, expected in BASELINE.items():
    check(hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected, 'not the adapter\'s preparation: ' + name)

environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
reports, texts, cross = {}, {}, {}
with tempfile.TemporaryDirectory(prefix='melonx-variant-journal-capacity-') as temporary:
    temporary = Path(temporary).resolve()
    work = temporary / 'candidate'
    shutil.copytree(SOURCE, work, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
    changed = apply(work)
    check(sorted(str(p.relative_to(work)) for p in changed) == sorted(BASELINE), 'adapter changed other files')
    later = files_edited_later('adapt_variant_journal_capacity')
    for name in BASELINE:
        if name not in later:
            check((work / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)
    try:
        apply(work)
        refused = False
    except AssertionError:
        refused = True
    check(refused, 'fail closed: an adapted tree is refused')
    texts['control'] = (SOURCE / MANAGER).read_text(encoding='utf-8-sig')
    texts['candidate'] = (work / MANAGER).read_text(encoding='utf-8-sig')
    for old, new in PAIRS:
        check(texts['control'].count(old) == 1 and texts['candidate'].count(new) == 1, 'each replacement is exact and reversible: ' + new[:60])
    result = subprocess.run([DOTNET, 'build', str(work / (VULKAN + 'Ryujinx.Graphics.Vulkan.csproj')), '-c', 'Release', '-nologo',
                             '-m:1', '-p:NuGetAudit=false'], capture_output=True, text=True, timeout=2400, env=environment, cwd=work)
    if result.returncode:
        print(result.stdout[-5000:], result.stderr[-2000:], flush=True)
    check(result.returncode == 0, 'candidate production Vulkan assembly builds')
    warned = [line for line in result.stdout.splitlines() if 'PipelineCacheManager.cs' in line and 'warning' in line]
    check(not warned, 'no warning in the edited file: ' + str(warned[:2]))
    shutil.rmtree(work)

    programs = {}
    for variant in ('control', 'candidate'):
        fixture = temporary / ('fixture-' + variant)
        fixture.mkdir()
        template = (FIXTURE / 'Program.cs').read_text()
        check(template.count('//__JOURNAL__') == 1, 'fixture mark')
        (fixture / 'Program.cs').write_text(template.replace('//__JOURNAL__', journal_class(texts[variant])))
        (fixture / 'Fixture.csproj').write_text(
            '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
            '<Nullable>disable</Nullable><NuGetAudit>false</NuGetAudit><NoWarn>CS0649;CS0414;CS0169;CS8321;CS1998</NoWarn>'
            '<ServerGarbageCollector>false</ServerGarbageCollector></PropertyGroup></Project>\n')
        result = subprocess.run([DOTNET, 'build', str(fixture / 'Fixture.csproj'), '-c', 'Release', '-nologo', '-p:NuGetAudit=false'],
                                capture_output=True, text=True, timeout=900, env=environment, cwd=fixture)
        if result.returncode:
            print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
            result.check_returncode()
        programs[variant] = fixture / 'bin/Release/net10.0/Fixture.dll'

    def run(variant, *arguments):
        result = subprocess.run([DOTNET, str(programs[variant]), variant, *arguments], capture_output=True, text=True, timeout=1800,
                                env=environment, cwd=temporary)
        if result.returncode:
            print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
            result.check_returncode()
        return json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))

    for variant in ('control', 'candidate'):
        reports[variant] = run(variant, str(temporary / ('files-' + variant)), 'main')
    # Across builds: each variant loads the file the other's session left.
    cross['candidate'] = run('candidate', str(temporary / 'cross-candidate'), 'cross', reports['control']['left']['path'])['cross']
    cross['control'] = run('control', str(temporary / 'cross-control'), 'cross', reports['candidate']['left']['path'])['cross']
    for variant in ('control', 'candidate'):
        del reports[variant]['left']['path']
        print(json.dumps(reports[variant]), flush=True)
    print(json.dumps(cross), flush=True)

c, k = reports['control'], reports['candidate']

# --- The on-disk format is the one the devices hold ---
control, candidate = texts['control'], texts['candidate']
for signature in ('private byte[] Header()', 'private static byte[] Encode(Record record, byte kind)',
                  'private static byte[] EncodeFailure(', 'private static bool TryParse(', 'internal static ulong Checksum64(',
                  'private static uint Checksum(', 'internal static ulong Schema'):
    check(member(candidate, signature) == member(control, signature), 'the format is unchanged: ' + signature)
for constant in ('internal const uint Magic = 0x56504252;', 'internal const uint Version = 1;', 'internal const int RecentSessions = 8;',
                 'internal const int MaxReplaysPerSession = MaxRecords;', 'internal const long ReplayWorkBudgetMs = 120_000;',
                 'internal const int MaxInFlight = 2;', 'internal const int LowDevicePercent = 8;', 'private const int HeaderBytes = 16;'):
    check(control.count(constant) == candidate.count(constant) == 1, 'unchanged: ' + constant)
check(re.search(r'internal const string StateFields =\n.*?;\n\n', control, re.S).group(0) ==
      re.search(r'internal const string StateFields =\n.*?;\n\n', candidate, re.S).group(0), 'the schema is unchanged')
check('internal const int MaxRecords = 2048;' in control and 'internal const int MaxRecords = 4096;' in candidate, 'the bound in states')
check('MaxFileBytes = 4L * 1024 * 1024;' in control and 'MaxFileBytes = 8L * 1024 * 1024;' in candidate, 'the bound in bytes')
load = member(candidate, 'internal void Load()')
check('File.ReadAllBytes(_path)' in member(control, 'internal void Load()') and 'File.ReadAllBytes' not in journal_class(candidate) and
      load.count('ReadBounded(_path, out cut)') == 1, 'the load reads through ReadBounded only')
bounded = member(candidate, 'private static byte[] ReadBounded(')
check('new byte[(int)Math.Min(length, MaxFileBytes)]' in bounded and 'cut = length > MaxFileBytes;' in bounded, 'ReadBounded allocates its bound at most')
for name in ('Append', 'Compact', 'MakeRoom', 'Rewrite', 'Pump', 'NoteLate', 'NoteReplayUsed', 'Completed', 'EvictionOrder'):
    signature = next(s for s in ('private void %s(' % name, 'internal void %s(' % name, 'public void %s(' % name, 'private bool %s(' % name,
                                 'internal static int %s(' % name) if s in control)
    check(member(candidate, signature) == member(control, signature), 'unchanged: ' + name)

# --- A session like the log's ---
LOG_LOADED = ('2028 variants of 426 programs planned for session 40 (dropped: 0 failed, 33 older than 8 sessions, 0 unreadable, '
              '0 given up for newer states; 3330 lines read')
LOG_JOURNAL = 'Journal: 2048 of 2048 states, given up for newer states 378 (at the load 0), not recorded 0, compactions 0, lines not written 0 '
for name in ('session', 'sessionPolicy'):
    cs, ks = c[name], k[name]
    for report in (cs, ks):
        check(report['loadedLine'].startswith(LOG_LOADED), name + ': the load reads the title\'s file as the log does: ' + report['loadedLine'])
        check((report['loaded'], report['session']) == (2028, 40), name + ': 2028 states for session 40')
        check((report['lateNew'], report['latePlanned'], report['builtForSkipped']) == (211, 853, 502), name + ': the session\'s counts')
        check('late creations left 1064 (' in report['summary'] and 'new 211, planned not built yet 853,' in report['summary'] and
              'built for skipped draws 502 (' in report['summary'], name + ': the summary reads as the log\'s')
        check((report['notRecorded'], report['compactions'], report['linesNotWritten']) == (0, 0, 0), name + ': nothing unrecorded or unwritten')
        check(report['nextStatesDrawn'] == 2426 and report['nextScheduledTwice'] == 0 and report['nextMostInFlight'] <= 2,
              name + ': the next launch schedules each state once, two at a time')
    check(cs['journal'].startswith(LOG_JOURNAL) and cs['evicted'] == 378, name + ': control gives up 378 states, as the log: ' + cs['journal'])
    check(ks['journal'].startswith('Journal: 2426 of 4096 states, given up for newer states 0 (at the load 0), not recorded 0, compactions 0, '
                                   'lines not written 0 ') and ks['evicted'] == 0, name + ': candidate holds the 2426 states: ' + ks['journal'])
    check((cs['nextLoaded'], cs['nextGivenUpAtLoad'], cs['nextReplayed']) == (2048, 378, 2048), name + ': control\'s next launch replays 2048')
    check((ks['nextLoaded'], ks['nextGivenUpAtLoad'], ks['nextReplayed']) == (2426, 0, 2426), name + ': candidate\'s next launch replays the 2426')
    check((cs['nextReadyBeforeFirstDraw'], cs['nextLateNew'], cs['nextLateCreations'], cs['nextNotRecorded']) == (2048, 378, 378, 378),
          name + ': control creates the 378 given-up states late again and cannot record them')
    check((ks['nextReadyBeforeFirstDraw'], ks['nextLateNew'], ks['nextLateCreations'], ks['nextNotRecorded']) == (2426, 0, 0, 0),
          name + ': candidate has every state ready before its first draw')
    check(ks['nextJournal'].startswith('Journal: 2426 of 4096 states, given up for newer states 0 (at the load 0), not recorded 0, '),
          name + ': candidate\'s next journal: ' + ks['nextJournal'])
    reuse = re.search(r'; 3594 lines read; (\d+) met in one session only; last met 1 to 8 sessions ago: ([\d/]+)\) ', ks['nextLoadedLine'])
    check(reuse is not None and ks['nextLoadedLine'].startswith('2426 variants of 426 programs planned for session 41 (dropped: 0 failed, '
          '0 older than 8 sessions, 0 unreadable, 0 given up for newer states; '), name + ': candidate\'s loaded line: ' + ks['nextLoadedLine'])
    ages = [int(n) for n in reuse.group(2).split('/')]
    check(len(ages) == 8 and sum(ages) == 2426 and ages[0] == 1566 and ages[1] == 0 and ages[7] > 0 and 398 <= int(reuse.group(1)) <= 2426 - 1168,
          name + ': the reuse counts: ' + reuse.group(0))
    check(cs['fileBytes'] <= 4 * MIB and ks['fileBytes'] <= 8 * MIB and ks['fileBytes'] == cs['fileBytes'], name + ': the session\'s file is the same, under its bound')
check(c['session']['journal'] == c['sessionPolicy']['journal'] and k['session']['journal'] == k['sessionPolicy']['journal'], 'the same under Hogwarts\' policy')

# --- Across builds ---
check(c['left']['journal'].startswith(LOG_JOURNAL) and k['left']['journal'].startswith('Journal: 2426 of 4096 states, given up for newer states 0 '),
      'the files left: ' + c['left']['journal'])
check(c['left']['fileBytes'] == k['left']['fileBytes'], 'both builds leave the same bytes (a given-up state\'s line stays in the file)')
check((cross['candidate']['loaded'], cross['candidate']['givenUpAtLoad'], cross['candidate']['replayed'], cross['candidate']['warnings']) == (2426, 0, 2426, 0),
      'the candidate reads the file an earlier build left, its given-up states included: ' + cross['candidate']['loadedLine'])
check((cross['control']['loaded'], cross['control']['givenUpAtLoad'], cross['control']['replayed'], cross['control']['warnings']) == (2048, 378, 2048, 0),
      'rollback: an earlier build reads the candidate\'s file and trims it: ' + cross['control']['loadedLine'])

# --- The bounds ---
cb, kb = c['bounds'], k['bounds']
check((kb['maxRecords'], kb['maxFileBytes'], kb['maxReplays'], kb['recentSessions']) == (4096, 8 * MIB, 4096, 8), 'candidate bounds')
check((cb['maxRecords'], cb['maxFileBytes'], cb['maxReplays'], cb['recentSessions']) == (2048, 4 * MIB, 2048, 8), 'control bounds')
check(kb['largestCompaction'] == 4096 * 1483 + 9 * 4096 * 28 + 16 == 7106576, 'the largest compaction: ' + str(kb['largestCompaction']))
for name, report in (('control', cb), ('candidate', kb)):
    most = report['maxRecords']
    check(report['largestCompaction'] <= report['maxFileBytes'] - report['maxFileBytes'] // 8, name + ': the largest compaction leaves an eighth of the file')
    check(report['filledBytes'] == 16 + most * 1483 <= report['maxFileBytes'] and report['filledNotRecorded'] == 0 and
          report['filledJournal'].startswith('Journal: %d of %d states, given up for newer states 0 ' % (most, most)), name + ': a journal of the largest variants fits')
    check(report['replayLoaded'] == report['replayed'] == report['replayScheduled'] == most and report['replayScheduledTwice'] == 0 and
          report['replaySummaryPlanned'], name + ': every recorded state is replayed, once: ' + str(report['replayed']))
    check(1 <= report['replayMostInFlight'] <= 2, name + ': two replays in flight at most')
    check(report['refreshCompactions'] >= 1 and report['refreshLinesNotWritten'] == 0 and report['refreshNotRecorded'] == 0 and
          report['afterRefreshLoaded'] == most and report['afterRefreshSession'] == 3, name + ': a full file is compacted, every refresh kept')
    check((report['overEvicted'], report['overNotRecorded'], report['overLinesNotWritten']) == (500, 0, 0) and
          report['overJournal'].startswith('Journal: %d of %d states, given up for newer states 500 ' % (most, most)), name + ': over the bound the journal gives up, in order')
    check((report['overNextLoaded'], report['overNextGivenUpAtLoad']) == (most, 500), name + ': and the next load keeps the bound')
    check(report['mostFileBytes'] <= report['maxFileBytes'] and report['warnings'] == 0, name + ': the file never passes its bound: ' + str(report['mostFileBytes']))
check('; 0 met in one session only; last met 1 to 8 sessions ago: 4096/0/0/0/0/0/0/0) ' in kb['afterRefreshLine'], 'every state refreshed: ' + kb['afterRefreshLine'])

# --- The load's cost (host) ---
cost = k['loadCost']
check(cost['states'] == 4096 and cost['fileBytes'] == 16 + 2 * 4096 * 459, 'a full journal of usual states after a session that refreshed each')
check(cost['loadMs'] < 2000 and cost['offersMs'] < 2000, 'the load and the offers are cheap on this host: %s ms, %s ms' % (cost['loadMs'], cost['offersMs']))
check(cost['heapBytesPerState'] < 1024 and cost['heapBytesHeld'] < 4 * MIB, 'the heap a full journal holds: ' + str(cost['heapBytesHeld']))
check(cost['loadAllocatedBytes'] < 3 * cost['fileBytes'] + 4 * MIB, 'the load allocates in proportion to its file: ' + str(cost['loadAllocatedBytes']))
check(cost['heldScheduled'] == 0 and cost['memoryHolds'] >= 1, 'no replay while the device is short of memory')

# --- Other formats, damage, over-long ---
cl, kl = c['loads'], k['loads']
EXPECTED = dict(good=(100, 101), otherVersion=(0, 1), olderVersion=(0, 1), otherSchema=(0, 1), otherMagic=(0, 1), empty=(0, 1),
                shortHeader=(0, 1), headerOnly=(0, 1), tornTail=(99, 100), flippedByte=(99, 100), lyingLength=(100, 101),
                garbageAfterHeader=(0, 1), garbage=(0, 1), zeroLengthLines=(0, 1))
for name, (loaded, afterwards) in EXPECTED.items():
    for variant, report in (('control', cl[name]), ('candidate', kl[name])):
        check(report['threw'] is False and report['warnings'] == 0, '%s: %s is read without an exception' % (variant, name))
        check((report['loaded'], report['nextLoaded']) == (loaded, afterwards), '%s: %s loads %d states and records again: %s' % (variant, name, loaded, report))
    check(cl[name]['line'].split(' lines read')[0] == kl[name]['line'].split(' lines read')[0] and cl[name]['dropped'] == kl[name]['dropped'] and
          cl[name]['fileBytesAfter'] == kl[name]['fileBytesAfter'], name + ': both variants read it alike')
check(' 1 unreadable,' in kl['flippedByte']['line'] and ' 0 unreadable,' in kl['tornTail']['line'], 'a damaged line is counted, a torn tail ignored')
check('file cut' not in ''.join(kl[name]['line'] for name in EXPECTED), 'a file under the bound is not cut')
co, ko = cl['overLong'], kl['overLong']
check(kl['overLongBytes'] == 40 * MIB and kl['typicalLine'] == 459 and kl['overLongLines'] == cl['overLongLines'] > 87000, 'the over-long file')
check(co['threw'] is False and ko['threw'] is False and co['warnings'] == ko['warnings'] == 0, 'an over-long file is read without an exception')
check((co['loaded'], ko['loaded'], co['nextLoaded'], ko['nextLoaded']) == (2048, 4096, 2048, 4096), 'an over-long file loads the bound in states')
lines_in_bound = (8 * MIB - 16) // 459
check('; %d lines read, file cut at its bound; ' % lines_in_bound in ko['line'] and ko['givenUpAtLoad'] == lines_in_bound - 4096,
      'the candidate reads its bound of the file: ' + ko['line'])
check('; %d lines read)' % cl['overLongLines'] in co['line'], 'the control reads the whole file: ' + co['line'])
check(co['allocatedBytes'] > kl['overLongBytes'] > ko['allocatedBytes'] and ko['allocatedBytes'] < 4 * 8 * MIB,
      'the load\'s memory is bounded by MaxFileBytes, not by the file: %d then %d' % (co['allocatedBytes'], ko['allocatedBytes']))
check(co['fileBytesAfter'] <= 4 * MIB and ko['fileBytesAfter'] <= 8 * MIB, 'and the file is compacted under its bound')

inputs = ['build-utils/melonx/adapt_variant_journal_capacity.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_variant_journal_capacity_test.py', 'test/melonx_variant_journal_capacity/Program.cs']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION, sourceKind='finalPreparationWithReversedControl',
               postimages={p: hashlib.sha256((FINAL_SOURCE / p).read_bytes()).hexdigest() for p in BASELINE},
               reports=reports, cross=cross, sdk=sdk, physicalDeviceTested=False, productionVulkanAssemblyBuilt=True,
               sourceBaseline=BASELINE, inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               limitation='Host run of the production journal class with doubles for the replaying program, the logger and the engine '
                          'journal: counts, bytes and host times. The memory of the replayed pipelines and the stutter on an iPhone are not '
                          'measured; they are read from the pipelineVariants and memory lines of a device run.')
out = ROOT / 'dist/melonx/variant-journal-capacity-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
