#!/usr/bin/env python3
"""adapt_loh_compaction_request on the final preparation, against its predecessor as control.

Usage: melonx_loh_compaction_request_test.py <predecessor preparation> --candidate-source <final preparation>

IPA 767, Super Smash Bros. Ultimate: the large object heap kept about 490 MiB free for eight minutes; the collector's own
blocking gen2 compacted the small object heap and not the LOH (docs/melonx-ipa767-journals-2026-11-17.md).

Static: only Switch.cs changes, its two replacements applied once to the control give the final file and reverse to it;
ProcessFrame asks the request only in the pressure branch, after Gpu.TrimCaches; the request class (between its markers)
starts no collection (no GC.Collect), sets the mode in one place, reads the collector's last collection and the mode.
Built: the production Ryujinx.HLE of the candidate.
Executed (test/melonx_loh_compaction_request/Program.cs with the candidate's class, unchanged; the host's segments
collector, as iOS NativeAOT, with the Core's ConserveMemory 5 and HighMemoryPercent 99):
- the rule at each of its limits (256 MiB, device 15 %, unknown device, the same collection, no collection, pending);
- a large object heap with 319 MiB free after a sweep (640 arrays of 1 MiB written, every other one kept): without the
  request (control) a blocking gen2 the caller does not ask to compact leaves it, committed and resident; with it
  (candidate) the same collection compacts the LOH, gives the free space back (committed and resident bytes fall) and
  clears the mode; the live arrays are intact; no request when not constrained, when the device is not short, while one
  is pending, nor after that collection (little free space).
No device. Writes dist/melonx/loh-compaction-request-checks.json.
"""
from pathlib import Path
import hashlib, json, os, platform, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, use_authenticated_libhac_feed  # noqa: E402
import adapt_loh_compaction_request as adapter  # noqa: E402

FINAL_SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
_HOLD = []
SOURCE, FINAL_PREPARATION = control_source(FINAL_SOURCE, 'adapt_loh_compaction_request', _HOLD)
DOTNET = os.environ.get('DOTNET', 'dotnet')
SWITCH = adapter.SWITCH
BEGIN, END = '    // RewindBox (adapt_loh_compaction_request) begin\n', '    // RewindBox (adapt_loh_compaction_request) end\n'
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


check(FINAL_PREPARATION, 'the candidate is the final preparation containing the adapter')
for name, expected in adapter.BASELINE.items():
    check(hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected, 'control is the predecessor preparation: ' + name)

environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
reports = {}
with tempfile.TemporaryDirectory(prefix='melonx-loh-request-') as temporary:
    work = Path(temporary).resolve() / 'candidate'
    shutil.copytree(SOURCE, work, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
    use_authenticated_libhac_feed(work, ROOT)
    adapter.apply(work)
    final = (FINAL_SOURCE / SWITCH).read_text(encoding='utf-8-sig')
    check((work / SWITCH).read_text(encoding='utf-8-sig') == final, 'the control plus the adapter is the final Switch.cs')
    control_text = (SOURCE / SWITCH).read_text(encoding='utf-8-sig')
    reverted = final
    for _, old, new in reversed(adapter.PAIRS):
        check(reverted.count(new) == 1 and control_text.count(old) == 1, 'each replacement once')
        reverted = reverted.replace(new, old)
    check(reverted == control_text, 'the replacements reverse to the control')

    frame = member(final, 'public void ProcessFrame()')
    branch = member(frame, 'if (pressure != MemoryPressureLevel.Normal)')
    check(frame.count('LargeObjectHeapRequest.') == 5 and branch.count('LargeObjectHeapRequest.OnHostPressure(') == 1 and
          branch.index('Gpu.TrimCaches(pressure);') < branch.index('LargeObjectHeapRequest.OnHostPressure(') and
          frame.index('Gpu.CheckHostMemory();') > frame.index(branch),
          'ProcessFrame asks the request in the pressure branch only, after the cache trim; the rest of the frame is unchanged')
    cls = final[final.index(BEGIN):final.index(END) + len(END)]
    check('GC.Collect' not in cls and cls.count('GCSettings.LargeObjectHeapCompactionMode = ') == 1 and
          'System.GC.GetGCMemoryInfo()' in cls and 'generations[3].FragmentationAfterBytes' in cls and
          'MinimumFreeBytes = 256L * 1024 * 1024' in cls and 'DeviceShortPercent = 15' in cls,
          'the request starts no collection, sets the mode in one place and reads the last collection')
    check(final.count('GC.Collect') == control_text.count('GC.Collect'), 'no collection added to Switch.cs')

    result = subprocess.run([DOTNET, 'build', str(work / 'src/Ryujinx.HLE/Ryujinx.HLE.csproj'), '-c', 'Release', '-nologo',
                             '-m:1', '-p:NuGetAudit=false'], capture_output=True, text=True, timeout=3600, env=environment, cwd=work)
    if result.returncode:
        print(result.stdout[-6000:], result.stderr[-2000:], flush=True)
    check(result.returncode == 0, 'production Ryujinx.HLE builds with the adapter')
    shutil.rmtree(work)

    fixture = Path(temporary).resolve() / 'fixture'
    fixture.mkdir()
    shutil.copyfile(ROOT / 'test/melonx_loh_compaction_request/Program.cs', fixture / 'Program.cs')
    (fixture / 'Request.cs').write_text('namespace Ryujinx.HLE\n{\n' + cls + '}\n')
    (fixture / 'Probe.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><Nullable>disable</Nullable>
<ServerGarbageCollection>false</ServerGarbageCollection><ConcurrentGarbageCollection>true</ConcurrentGarbageCollection>
</PropertyGroup></Project>
''')
    build = subprocess.run([DOTNET, 'build', 'Probe.csproj', '-c', 'Release', '-nologo', '-v', 'q'], cwd=fixture,
                           capture_output=True, text=True, timeout=600, env=environment)
    if build.returncode:
        print(build.stdout[-4000:], build.stderr[-2000:], flush=True)
    check(build.returncode == 0, 'fixture builds with the production class')
    GC_LIBRARY = 'libclrgc.dylib' if platform.system() == 'Darwin' else 'libclrgc.so'
    gc_environment = dict(environment, DOTNET_GCName=GC_LIBRARY, DOTNET_GCConserveMemory='5', DOTNET_GCHighMemPercent='63')
    for mode in ('control', 'candidate'):
        run = subprocess.run([DOTNET, 'bin/Release/net10.0/Probe.dll', mode], cwd=fixture, capture_output=True, text=True,
                             timeout=300, env=gc_environment)
        if run.returncode:
            print(run.stdout[-3000:], run.stderr[-3000:], flush=True)
        check(run.returncode == 0, 'fixture runs: ' + mode)
        reports[mode] = json.loads(run.stdout.strip().splitlines()[-1])

for report in reports.values():
    config = report['gcConfig']
    check(config.get('GCRegionRange') == '0' and config.get('GCConserveMem') == '5' and config.get('GCName') == GC_LIBRARY and
          config.get('GCHighMemPercent') == '99', 'segments GC with the Core\'s settings: ' + str(config))
    check(report['policy'] == {'free256MiBDevice15': True, 'freeUnder256MiB': False, 'device16': False, 'deviceUnknown': False,
                               'sameCollection': False, 'noCollectionYet': False, 'pending': False}, 'policy: ' + str(report['policy']))
    check(report['liveIntact'], 'live arrays intact: ' + report['mode'])
    before = report['before']
    check(before['lohFreeMiB'] >= 300 and before['mode'] == 'Default', 'a large object heap with its free space after a sweep: ' + str(before))
control, candidate = reports['control'], reports['candidate']
b, a = control['before'], control['after']
check(a['lohFreeMiB'] >= b['lohFreeMiB'] - 8 and a['committedMiB'] >= b['committedMiB'] - 8 and a['rssMiB'] >= b['rssMiB'] - 32,
      'control: the blocking collection leaves the free space committed and resident: ' + str((b, a)))
b, a = candidate['before'], candidate['after']
r = candidate['results']
check(r == {'notConstrained': False, 'deviceNotShort': False, 'modeAfterRefusals': 'Default', 'request': True,
            'modeAfterRequest': 'CompactOnce', 'secondWhilePending': False, 'requests': 1, 'lastFreeMiB': b['lohFreeMiB'],
            'afterConsumed': False, 'requestsAtEnd': 1}, 'candidate requests: ' + str(r))
check(a['lohFreeMiB'] <= 8 and b['committedMiB'] - a['committedMiB'] >= 250 and b['rssMiB'] - a['rssMiB'] >= 250 and
      a['mode'] == 'Default', 'candidate: the same collection compacts the LOH and gives the free space back: ' + str((b, a)))

inputs = ['build-utils/melonx/adapt_loh_compaction_request.py', 'build-utils/melonx/adapt_session.py', 'test/melonx_adapter_control.py',
          'test/melonx_loh_compaction_request_test.py', 'test/melonx_loh_compaction_request/Program.cs']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl',
               postimages={p: hashlib.sha256((FINAL_SOURCE / p).read_bytes()).hexdigest() for p in adapter.BASELINE},
               sdk=sdk, gc=GC_LIBRARY + ' (segments), ConserveMemory 5, HighMemoryPercent 99, workstation concurrent, ' + platform.system() + ' CoreCLR',
               reports={k: {key: v for key, v in rep.items() if key != 'gcConfig'} for k, rep in reports.items()},
               lohCompactionRequest=dict(executed=True, controlKeptFreeMiB=control['after']['lohFreeMiB'],
                                         candidateGaveBackMiB=candidate['before']['committedMiB'] - candidate['after']['committedMiB']),
               physicalDeviceTested=False, productionHleAssemblyBuilt=True, sourceBaseline=adapter.BASELINE,
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               limitation='The fixture runs host CoreCLR with the segments GC (' + platform.system() + ' resident bytes, not iOS phys_footprint); '
                          'whether and when the collector runs a blocking gen2 on the device is the collector\'s own decision')
out = ROOT / 'dist/melonx/loh-compaction-request-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
