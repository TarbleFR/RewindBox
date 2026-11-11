#!/usr/bin/env python3
"""adapt_cold_buffer_trim on the final preparation, against the Core 729 preparation as control.

Usage: melonx_cold_buffer_trim_test.py <Core 729 prepared tree>
       melonx_cold_buffer_trim_test.py <control> --candidate-source <final preparation containing the adapter>

Static: the control is the Core 729 pair of files; the candidate differs by the adapter's four replacements (the stamp
in AddBuffer and in Touch, the choice at the end of Trim with the added members, one field in Buffer.cs); Trim keeps its
setting check, targets and floor; the headroom threshold is GpuContext.TrimCaches' comfortable one; the capacity
eviction is untouched.
Executed for control, candidate and three sensitivity variants on the variant's real BufferCache.cs members (AddBuffer,
RemoveBufferTracking, Touch, Trim, both EnforceCapacity, and the candidate's added block), with the doubles and the
world of test/melonx_cold_buffer_trim/Program.cs (a lookup of an evicted buffer creates it again, counted; the host's
uptime the cache reads once every 256 lookups is driven by the scenarios):
- the IPA 724 shape (100 MiB all used every second, 25 trims in 150 s, 1.3 GiB of headroom): the control evicts and the
  game recreates 672 buffers, the candidate none; under this process's own pressure or an unknown headroom the candidate
  is the control, buffer for buffer;
- cold buffers leave first and only they leave; a host pause ages nothing; a second without a frame, or in which the
  cache is not used at all, is not a second of play; with few lookups ages only lag; everything cold leaves as upstream
  evicts it; unevictable buffers are passed over; tracking off trims nothing; the capacity eviction is upstream's; a
  suppressed eviction does nothing; the journal is bounded.
Sensitivity: without the stamp in Touch, with the host's clock instead of seconds of play, and without the age test,
the candidate must each fail a scenario.
The buffer is a double: the cost of a creation on the device (Metal allocation, guest memory copy, tracking handles) is
the IPA 724 journal's, not this test's. Writes dist/melonx/cold-buffer-trim-checks.json.
"""
from pathlib import Path
import hashlib, json, os, platform, re, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
FINAL_SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, files_edited_later  # noqa: E402
_HOLD = []
CONTROL_SOURCE, FINAL_PREPARATION = control_source(FINAL_SOURCE, 'adapt_cold_buffer_trim', _HOLD)
import adapt_cold_buffer_trim as adapter  # noqa: E402

DOTNET = os.environ.get('DOTNET', 'dotnet')
CACHE, BUFFER = adapter.CACHE, adapter.BUFFER
CONTEXT = 'src/Ryujinx.Graphics.Gpu/GpuContext.cs'
HARNESS = ROOT / 'test/melonx_cold_buffer_trim'
MEMBERS = [
    'private void AddBuffer(Buffer buffer)',
    'private void RemoveBufferTracking(Buffer buffer)',
    'private void Touch(Buffer buffer)',
    'public ulong Trim(MemoryPressureLevel level)',
    'private void EnforceCapacity(Buffer protectedBuffer)',
    'private void EnforceCapacity(Buffer protectedBuffer, ulong target)',
]
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
check(not files_edited_later('adapt_cold_buffer_trim'), 'no later adapter edits these files')
for name, expected in adapter.BASELINE.items():
    check(sha(CONTROL_SOURCE / name) == expected, 'control is the Core 729 preparation: ' + name)
control_cache, final_cache = text(CONTROL_SOURCE, CACHE), text(FINAL_SOURCE, CACHE)
control_buffer, final_buffer = text(CONTROL_SOURCE, BUFFER), text(FINAL_SOURCE, BUFFER)
rebuilt = control_cache
for name, old, new in adapter.PAIRS:
    if name == CACHE:
        check(rebuilt.count(old) == 1, 'one site in the control: ' + old.strip().splitlines()[0])
        rebuilt = rebuilt.replace(old, new)
check(rebuilt == final_cache, 'BufferCache.cs is the control plus the three replacements')
check(control_buffer.count(adapter.FIELD_OLD) == 1 and control_buffer.replace(adapter.FIELD_OLD, adapter.FIELD_NEW) == final_buffer,
      'Buffer.cs is the control plus one field')
check(final_buffer.count('LastUseEpoch') == 1, 'Buffer.cs only declares the field')
drift = Path(tempfile.mkdtemp(prefix='melonx-cold-buffer-trim-drift-'))
for name in adapter.BASELINE:
    (drift / name).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(CONTROL_SOURCE / name, drift / name)
(drift / BUFFER).write_bytes((drift / BUFFER).read_bytes() + b'\n// unreviewed drift\n')
try:
    adapter.apply(drift)
    refused = False
except AssertionError:
    refused = True
shutil.rmtree(drift)
check(refused, 'a drifted Buffer.cs is refused')

block = final_cache[final_cache.index(adapter.MEMBERS_BEGIN):final_cache.index(adapter.MEMBERS_END) + len(adapter.MEMBERS_END)]
check(final_cache.count(adapter.MEMBERS_BEGIN) == 1 and final_cache.count(adapter.MEMBERS_END) == 1 and adapter.MEMBERS_BEGIN not in control_cache,
      'the added members stand once, between their markers')
trim_control, trim_final = member(control_cache, MEMBERS[3]), member(final_cache, MEMBERS[3])
head = trim_control[:trim_control.index('            ulong before = _cachedBufferBytes;')]
check(trim_final.startswith(head) and 'GraphicsConfig.EnableHostMemoryBudgetTracking' in head and
      'MemoryPressureLevel.Critical => _cachedBufferBytes / 2' in head and
      'MemoryPressureLevel.Warning => _cachedBufferBytes - (_cachedBufferBytes / 4)' in head and
      'Math.Max(target, _maxCachedBufferBytes / TrimFloorDivisor)' in head,
      'Trim keeps its setting check, targets and floor')
check('private const ulong TrimFloorDivisor = 8;' in final_cache and 'private const ulong MiB = 1024 * 1024;' in final_cache,
      'the floor divisor and the unit the fixture declares are the real ones')
check(trim_final.count('EnforceCapacity(null, target);') == 1 and trim_final.count('EvictCold(target);') == 1 and
      re.search(r'if \(HostMemoryBudget\.AvailableBytes >= DeviceShortOnlyHeadroomBytes\)\s*\{\s*EvictCold\(target\);\s*\}\s*else\s*\{\s*EnforceCapacity\(null, target\);\s*\}', trim_final) is not None,
      'cold eviction with the comfortable headroom, upstream eviction otherwise')
context = text(FINAL_SOURCE, CONTEXT)
check('private const ulong ComfortableHeadroomBytes = 768 * TrimMiB;' in context and 'private const ulong TrimMiB = 1024 * 1024;' in context and
      'private const ulong DeviceShortOnlyHeadroomBytes = 768 * MiB;' in block,
      'the threshold is the one at or above which TrimCaches runs only because the device is short')
check('bool freeOnly = deviceShort && available >= ComfortableHeadroomBytes;' in context and
      'evicted += physicalMemory.BufferCache.Trim(level);' in context,
      'TrimCaches still calls the buffer trim, and decides its texture trim on the same headroom')
helper = '        private static long HostMilliseconds() => Environment.TickCount64;\n'
check(final_cache.count(helper) == 1 and helper not in block and final_cache.count('HostMilliseconds()') == 2 and
      block.count('(int)(HostMilliseconds() / 1000)') == 1,
      'the clock is the host\'s uptime, read through the one helper the fixture replaces')
check('_context' not in block and 'TextureUseEpoch' not in final_cache and 'private const int UseClockLookups = 256;' in block and
      block.count('(++_useClockLookups & (UseClockLookups - 1)) == 0') == 1,
      'the clock is the cache\'s own (nothing of GpuContext is read), once every 256 lookups')
check('internal const int ColdBufferAgeSeconds = 60;' in block and 'private int _coldTextureAgeSeconds = ColdTextureInitialAgeSeconds;' in context and
      re.search(r'ColdTextureInitialAgeSeconds = 60;', context) is not None, 'the age is the cold texture release\'s initial 60 s')
for signature in (MEMBERS[1], MEMBERS[4], MEMBERS[5]):
    check(member(control_cache, signature) == member(final_cache, signature), 'unchanged: ' + signature)
stamp = '            buffer.LastUseEpoch = UseEpoch(); // RewindBox (adapt_cold_buffer_trim)\n'
check(member(final_cache, MEMBERS[0]).replace(stamp, '') == member(control_cache, MEMBERS[0]) and
      member(final_cache, MEMBERS[2]).replace(stamp, '') == member(control_cache, MEMBERS[2]) and final_cache.count(stamp) == 2,
      'AddBuffer and Touch differ by the stamp alone')
check(final_cache.count('Touch(') == control_cache.count('Touch(') and final_cache.count('EvictCold(') == 2 and final_cache.count('UseEpoch()') == 3 and
      final_cache.count('PlaySeconds()') == 3,
      'no lookup changes; one caller of the cold eviction; the two stamps count lookups, the eviction only reads the seconds of play')
check("'='" not in block and '=\\"' not in block and re.search(r'\$"[^"]*\w=\{', block) is None, 'the journal detail has no name=value text')

# --- Executed: control, candidate and sensitivity variants on the real members ---
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1')
WORK = Path(tempfile.mkdtemp(prefix='melonx-cold-buffer-trim-')).resolve()
age_test = '                if (epoch - buffer.LastUseEpoch < ColdBufferAgeSeconds)\n'
VARIANTS = {
    'control': None,
    'candidate': None,
    # Sensitivity: each removes one part of the candidate.
    # Touch reads the clock but no longer stamps the buffer it returns.
    'noStamp': (member(final_cache, MEMBERS[2]), member(final_cache, MEMBERS[2]).replace('buffer.LastUseEpoch = UseEpoch();', 'UseEpoch();')),
    'hostClock': ('            return _hostSecondSeen - _skippedSeconds;\n', '            return _hostSecondSeen;\n'),
    'anyAge': (age_test, '                if (false)\n'),
}
reports = {}
for variant, change in VARIANTS.items():
    source = control_cache if variant == 'control' else final_cache
    members = '\n\n'.join(member(source, signature) for signature in MEMBERS)
    if variant != 'control':
        members += '\n\n' + block
    if change:
        check(members.count(change[0]) == 1, variant + ': one site to alter')
        members = members.replace(change[0], change[1])
    fixture = WORK / variant
    fixture.mkdir()
    (fixture / 'Members.cs').write_text(
        'using Ryujinx.Memory;\nusing System;\nusing System.Collections.Generic;\n\n'
        'namespace Ryujinx.Graphics.Gpu.Memory\n{\n    public partial class BufferCache\n    {\n' + members + '\n    }\n}\n')
    shutil.copyfile(HARNESS / 'Program.cs', fixture / 'Program.cs')
    (fixture / 'Fixture.csproj').write_text(
        '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
        '<Nullable>disable</Nullable><NuGetAudit>false</NuGetAudit>'
        '<NoWarn>CS0649;CS0414;CS0169;CS0067;CS8321;CS0162;CS8632</NoWarn></PropertyGroup></Project>\n')
    build = subprocess.run([DOTNET, 'build', str(fixture / 'Fixture.csproj'), '-c', 'Release', '-nologo', '-p:NuGetAudit=false'],
                           capture_output=True, text=True, timeout=900, env=environment, cwd=fixture)
    if build.returncode:
        print('\n'.join(line for line in build.stdout.splitlines() if ': error ' in line)[:6000], flush=True)
    check(build.returncode == 0, variant + ' fixture builds with the real BufferCache.cs members')
    run = subprocess.run([DOTNET, str(fixture / 'bin/Release/net10.0/Fixture.dll'), variant],
                         capture_output=True, text=True, timeout=900, env=environment, cwd=fixture)
    if run.returncode:
        print(run.stdout[-4000:], run.stderr[-4000:], flush=True)
    check(run.returncode == 0, variant + ' fixture runs')
    reports[variant] = json.loads(run.stdout.strip().splitlines()[-1])
shutil.rmtree(WORK)
if os.environ.get('MELONX_TEST_REPORTS'):
    Path(os.environ['MELONX_TEST_REPORTS']).write_text(json.dumps(reports, indent=1))
c, k = reports['control'], reports['candidate']

# The IPA 724 shape.
hot_c, hot_k = c['hotSetDeviceShort'], k['hotSetDeviceShort']
check(hot_c['trims'] == 25 and hot_c['evicted'] == 13 * 25 + 12 * 31 and hot_c['recreated'] == 672 and hot_c['releasedMiB'] == 697 and
      hot_c['lowestCachedMiB'] == 69 and hot_c['notifications'] == 25 and not hot_c['allResidentAtTheEnd'] and
      hot_c['evictionOrder'] == list(range(25)) + list(range(15)),
      'control: every trim evicts a quarter or down to the floor of the buffers in use, all recreated: ' + json.dumps(hot_c))
check(hot_k['trims'] == 25 and hot_k['evicted'] == 0 and hot_k['recreated'] == 0 and hot_k['created'] == 100 and hot_k['releasedMiB'] == 0 and
      hot_k['cachedMiB'] == 100 and hot_k['lowestCachedMiB'] == 100 and hot_k['notifications'] == 0 and hot_k['allResidentAtTheEnd'] and
      hot_k['records'] == 3, 'candidate: nothing in use leaves, nothing is recreated; three records in 150 s: ' + json.dumps(hot_k))
for name in ('hotSetOwnPressure', 'hotSetUnknownHeadroom'):
    check(k[name] == c[name] == dict(hot_c), name + ': under its own pressure or an unknown headroom the candidate is upstream, buffer for buffer')

# Cold first, cold only.
cold_c, cold_k = c['coldGoFirst'], k['coldGoFirst']
check([(s['second'], s['releasedMiB'], s['evicted'], s['cachedMiB']) for s in cold_k['steps']] ==
      [(30, 0, [], 100), (70, 25, list(range(25)), 75), (80, 15, list(range(25, 40)), 60), (90, 0, [], 60)],
      'candidate: nothing at 30 s, the cold buffers oldest first once unused for 60 s, then nothing: ' + json.dumps(cold_k['steps']))
check(cold_k['recreated'] == 0 and cold_k['hotResident'] and cold_k['coldResident'] == 0 and cold_k['releasedMiB'] == 40 and cold_k['notifications'] == 2 and
      cold_k['records'] == 3, 'candidate: the 40 MiB nothing used are given back, no buffer in use is touched: ' + json.dumps(cold_k))
check(cold_k['recordDetails'] == [
    'bufferCache coldTrim: pass 1: released 0 buffers (0 MiB) unused for 60 s of play, left 25 MiB above the target in use; '
    'cache 100 of 160 MiB; so far 0 buffers (0 MiB) in 1 passes (adapt_cold_buffer_trim)',
    'bufferCache coldTrim: pass 2: released 25 buffers (25 MiB) unused for 60 s of play, left 0 MiB above the target in use; '
    'cache 75 of 160 MiB; so far 25 buffers (25 MiB) in 2 passes (adapt_cold_buffer_trim)',
    'bufferCache coldTrim: pass 3: released 15 buffers (15 MiB) unused for 60 s of play, left 3 MiB above the target in use; '
    'cache 60 of 160 MiB; so far 40 buffers (40 MiB) in 3 passes (adapt_cold_buffer_trim)'], 'candidate: the three records: ' + json.dumps(cold_k['recordDetails']))
check([(s['second'], s['releasedMiB'], s['evicted']) for s in cold_c['steps']] ==
      [(30, 25, list(range(25))), (70, 19, list(range(25, 44))), (80, 15, list(range(40, 55))), (90, 15, list(range(40, 55)))] and
      cold_c['recreated'] == 34, 'control: once the cold buffers are gone the trims take buffers in use, recreated: ' + json.dumps(cold_c['steps']))

# A pause ages nothing; a second without a frame is not play.
for name in ('pauseTrimFirst', 'pauseUseFirst'):
    check(c[name]['evicted'] == 31 and c[name]['recreated'] == 31, 'control: the trim after a pause evicts 31 buffers in use: ' + name)
    check(k[name]['evicted'] == 0 and k[name]['recreated'] == 0 and k[name]['cachedMiB'] == 100 and k[name]['records'] == 1,
          'candidate: a 300 s pause ages no buffer: ' + name + ' ' + json.dumps(k[name]))
stall_c, stall_k = c['stallSeconds'], k['stallSeconds']
check(stall_k['evictedAt'] == {'hostSecond120': [], 'hostSecond210': [99]} and stall_k['recreated'] == 0 and stall_k['records'] == 2,
      'candidate: unused for 40 s of play (117 host seconds) stays; unused for 69 s of play leaves: ' + json.dumps(stall_k))
check(stall_c['evictedAt']['hostSecond120'] == [99] + list(range(10)) and stall_c['recreated'] == 20, 'control: half of what is in use each time')

# Everything cold: upstream's eviction, buffer for buffer.
check(k['allCold']['evictionOrder'] == c['allCold']['evictionOrder'] == list(range(32)) and k['allCold']['returnedMiB'] == c['allCold']['returnedMiB'] == 32 and
      k['allCold']['notifications'] == c['allCold']['notifications'] == 1 and k['allCold']['cachedMiB'] == 69,
      'everything else cold: the same buffers leave in the same order, down to the same target')
check(k['unevictable']['evictionOrder'] == c['unevictable']['evictionOrder'] == list(range(10, 36)) and k['unevictable']['pinnedResident'],
      'unevictable buffers are passed over; the cold ones after them leave')
check(c['noLookup']['evicted'] == 31 and k['noLookup']['evicted'] == 0 and k['noLookup']['cachedMiB'] == 100,
      'candidate: seconds in which the cache is not used at all age nothing (the control evicts 31 buffers)')
few = k['fewLookups']
check(few['evictedAt'] == {'second100': [], 'second200': [200], 'second300': [200]} and few['recreated'] == 0 and few['cachedMiB'] == 100,
      'candidate: with a clock read every 2.56 s ages only lag: nothing in use leaves, the cold buffer leaves later: ' + json.dumps(few['evictedAt']))
check(k['trackingOff'] == c['trackingOff'] and k['trackingOff']['evicted'] == 0 and k['trackingOff']['returnedMiB'] == 0, 'tracking off: no trim')
check(k['capacity'] == c['capacity'] and k['capacity']['evictionOrder'] == [0, 1, 2, 3, 4] and k['capacity']['cachedMiB'] == 5,
      'the capacity eviction is upstream\'s whatever the age')
check(c['suppressed']['returnedMiB'] == 0 and c['suppressed']['pending'] and k['suppressed']['returnedMiB'] == 0 and not k['suppressed']['pending'] and
      k['suppressed']['evicted'] == 0 and k['suppressed']['records'] == 0, 'a suppressed eviction: nothing leaves, nothing is left pending by the cold trim')
journal = k['journal']
check(journal['recordsAfterTenMinutes'] == 10 and journal['recordsWhileNothingCold'] == 160 and journal['records'] == 160 and journal['evicted'] == 81 and journal['cachedMiB'] == 20 and
      journal['stages'] == ['bufferCache coldTrim'] and journal['detailsWithEquals'] == 0 and journal['detailsNamingTheAdapter'] == 160 and
      journal['recreated'] == 0 and
      journal['firstDetail'] == 'pass 1: released 0 buffers (0 MiB) unused for 60 s of play, left 25 MiB above the target in use; cache 100 of 160 MiB; '
                                'so far 0 buffers (0 MiB) in 1 passes (adapt_cold_buffer_trim)',
      'the journal: one record a minute while nothing is cold, 160 at most: ' + json.dumps({key: value for key, value in journal.items() if key != 'firstDetail'}))
check(c['journal']['records'] == 0 and c['journal']['recreated'] == 5999 * 25, 'control: no record; 149 975 buffers recreated after 6 000 trims')
check(all(r['records'] == 0 for r in c.values() if isinstance(r, dict)), 'control: writes no journal record')

# Sensitivity: each altered candidate fails a scenario the candidate passes.
check(reports['noStamp']['hotSetDeviceShort']['recreated'] > 0, 'sensitivity: without the stamp in Touch, buffers in use look cold after a minute')
check(reports['hostClock']['pauseUseFirst']['evicted'] == 31 and reports['hostClock']['stallSeconds']['evictedAt']['hostSecond120'] == [99],
      'sensitivity: on the host\'s clock a pause and the seconds without a frame age the buffers')
check(reports['anyAge']['hotSetDeviceShort']['recreated'] == 672, 'sensitivity: without the age test the trim is upstream\'s')

inputs = ['build-utils/melonx/adapt_cold_buffer_trim.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_cold_buffer_trim_test.py', 'test/melonx_cold_buffer_trim/Program.cs', 'test/melonx_adapter_control.py']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core729Preparation',
               postimages={p: sha(FINAL_SOURCE / p) for p in adapter.BASELINE} if FINAL_PREPARATION else {},
               comparison=dict(trims=hot_k['trims'], recreatedControl=hot_c['recreated'], recreatedCandidate=hot_k['recreated'],
                               evictedInUseControl=hot_c['evicted'], evictedInUseCandidate=hot_k['evicted'],
                               coldReleasedMiBCandidate=cold_k['releasedMiB'], pauseEvictedControl=c['pauseTrimFirst']['evicted'],
                               pauseEvictedCandidate=k['pauseTrimFirst']['evicted'], journalRecordsAtMost=journal['records'],
                               sensitivityVariantsFailed=3),
               reports=reports, sdk=sdk, host=platform.system(), physicalDeviceTested=False, productionGpuSourceExecuted=True,
               deviceEvidence='IPA 724, Hogwarts Legacy, pid 49375 (private journals): 24 trims in 150 s; 5 s windows with a trim create 1 400 to '
                              '7 026 buffers on the render thread (64 to 460 ms) and dispose 3 637 to 7 317 after a Critical one; without a trim '
                              '0 to 870 created; the cache is back at 85-127 MiB at every 30 s report',
               inputs={name: sha(ROOT / name) for name in inputs},
               limitation='The real cache bookkeeping, eviction and trim on a buffer double: the cost of a creation on the device, the size '
                          'the cache settles at when nothing in use is evicted and the frame times are shown only by a device run '
                          '(LogRenderWork CreateBufferAccess and BufferDispose per window, bufferCache coldTrim records, bufferCacheBytes).')
out = ROOT / 'dist/melonx/cold-buffer-trim-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
