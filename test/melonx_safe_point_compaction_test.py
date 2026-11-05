#!/usr/bin/env python3
"""Large object heap compaction at the first frame and in a held host pause (adapt_safe_point_compaction).

Usage: melonx_safe_point_compaction_test.py <Core 658 prepared MeloNX tree>
       melonx_safe_point_compaction_test.py <control> --candidate-source <final preparation containing the adapter>

Applies the adapter to a copy of the Core 658 preparation and builds the production Ryujinx.Library assembly (with every
Core project it references). Static checks bind that each file equals the preparation once the adapter's replacements are
undone, that the first-frame call sits in the render loop's first-frame block, that the pause call follows the pause
control's TogglePauseEmulation and SetEmbeddedPaused, and that no other collection is added. In the preparation they bind
why nothing compacts the LOH today: the GC settings (ConserveMemory 5, HighMemoryPercent 99), and the CPU engine with
HostMappedUnsafe on ARM64 being LightningJit, whose disk cache state is a dummy (PTC, the only CompactOnce requester,
never runs). The executed fixture compiles the production EmbeddedHeapCompaction class unchanged with doubles of
HostMemoryBudget and the launch journal and runs it with the host's segments GC library (libclrgc.so on Linux,
libclrgc.dylib on macOS; iOS NativeAOT has no regions) and the Core's GC settings: control (no call) against candidate (first frame), and the pause flow (device gate,
resume before the delay, close begun, held pause, 60 s interval). No device. Writes
dist/melonx/safe-point-compaction-checks.json.
"""
from pathlib import Path
import hashlib, json, os, platform, re, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, files_edited_later, use_authenticated_libhac_feed  # noqa: E402
_HOLD = []
FINAL_SOURCE = SOURCE
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_safe_point_compaction', _HOLD)
import adapt_safe_point_compaction  # noqa: E402
from adapt_safe_point_compaction import apply, BASELINE, COMPACTION_CLASS  # noqa: E402

MEMORY = 'src/Ryujinx.Library/EmbeddedMemory.cs'
LIBRARY = 'src/Ryujinx.Library/Library.cs'
WINDOW = 'src/Ryujinx.Library/Window/WindowBase.cs'
DOTNET = os.environ.get('DOTNET', 'dotnet')
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


for name, expected in BASELINE.items():
    check(hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected, 'not the Core 658 preparation: ' + name)

# Why, in the preparation.
csproj = (SOURCE / 'src/Ryujinx.Library/Ryujinx.Library.csproj').read_text(encoding='utf-8-sig')
check(re.search(r'ConserveMemory[^\n]*5', csproj) is not None and re.search(r'HighMemoryPercent[^\n]*99', csproj) is not None,
      'GC settings: ConserveMemory 5, HighMemoryPercent 99')
factory = (SOURCE / 'src/Ryujinx.HLE/HOS/ArmProcessContextFactory.cs').read_text(encoding='utf-8-sig')
check(re.search(r'isArm64Host && \(mode == MemoryManagerMode\.HostMapped \|\| mode == MemoryManagerMode\.HostMappedUnsafe\) && '
                r'!context\.Device\.Configuration\.EnableGdbStub\s*\?\s*new LightningJitEngine', factory) is not None,
      'HostMappedUnsafe on an ARM64 host runs LightningJit')
lightning = (SOURCE / 'src/Ryujinx.Cpu/LightningJit/LightningJitCpuContext.cs').read_text(encoding='utf-8-sig')
check(re.search(r'LoadDiskCache\([^)]*\)\s*\{\s*return new DummyDiskCacheLoadState\(\);', lightning) is not None,
      'LightningJit: no PTC (dummy disk cache state)')
compact_once = []
for path in (SOURCE / 'src').rglob('*.cs'):
    text = path.read_text(encoding='utf-8-sig', errors='replace')
    if 'GCLargeObjectHeapCompactionMode.CompactOnce' in text:
        compact_once.append(path.relative_to(SOURCE).as_posix())
check(compact_once == ['src/ARMeilleure/Translation/PTC/Ptc.cs'], 'the only CompactOnce requester is PTC: ' + str(compact_once))
memory_budget = (SOURCE / 'src/Ryujinx.Memory/HostMemoryBudget.cs').read_text(encoding='utf-8-sig')
check('public static bool IsConstrained => OperatingSystem.IsIOS();' in memory_budget, 'IsConstrained is iOS only')

replacements = {}
original_once = adapt_safe_point_compaction.once
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
reports = {}
with tempfile.TemporaryDirectory(prefix='melonx-safe-point-compaction-') as temporary:
    work = Path(temporary).resolve() / 'candidate'
    shutil.copytree(SOURCE, work, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
    use_authenticated_libhac_feed(work, ROOT)

    def recording_once(path, old, new):
        replacements.setdefault(Path(path).relative_to(work).as_posix(), []).append((old, new))
        original_once(path, old, new)

    adapt_safe_point_compaction.once = recording_once
    try:
        changed = apply(work)
    finally:
        adapt_safe_point_compaction.once = original_once
    check(sorted(str(p.relative_to(work)) for p in changed) == sorted(BASELINE), 'adapter changed other files')
    if FINAL_PREPARATION:
        # Files a later Core 661 adapter also edits are proven by control_source's forward check; the others must
        # be the final preparation's bytes here.
        later = files_edited_later('adapt_safe_point_compaction')
        for name in BASELINE:
            if name not in later:
                check((work / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)
    for name in BASELINE:
        undone = (work / name).read_text(encoding='utf-8-sig')
        for old, new in reversed(replacements[name]):
            check(undone.count(new) == 1, 'each replacement once: ' + new[:60])
            undone = undone.replace(new, old)
        check(undone == (SOURCE / name).read_text(encoding='utf-8-sig'), name + ' is the preparation but the adapter\'s replacements')
    check(sum(len(v) for v in replacements.values()) == 3, 'three replacements')

    memory = (work / MEMORY).read_text(encoding='utf-8-sig')
    check(memory.count(COMPACTION_CLASS) == 1 and memory.endswith(COMPACTION_CLASS), 'the class is appended to EmbeddedMemory.cs')
    check(COMPACTION_CLASS.count('System.GC.Collect(') == 1 and
          'System.GC.Collect(2, System.GCCollectionMode.Forced, blocking: true, compacting: true);' in COMPACTION_CLASS and
          'GCLargeObjectHeapCompactionMode.CompactOnce;\n            System.GC.Collect(' in COMPACTION_CLASS,
          'one blocking compacting gen2, LOH compaction requested right before it')
    check('Monitor.TryEnter(_gate)' in COMPACTION_CLASS and 'IsBackground = true' in COMPACTION_CLASS and
          'Volatile.Read(ref _pauseGeneration) != generation || stopping()' in COMPACTION_CLASS,
          'never two at once; the pause thread is a background thread that gives up when the pause ended or a close began')
    check(COMPACTION_CLASS.count('Ryujinx.Memory.HostMemoryBudget.IsConstrained') == 2, 'both entry points iOS only')
    window = (work / WINDOW).read_text(encoding='utf-8-sig')
    first = re.search(r'if \(Device\.PresentLoop\(SwapBuffers\)\)\s*\{\s*if \(!_ranFirstFrame\)\s*\{\s*_ranFirstFrame = true;\s*'
                      r'SendStatistics\(false\);\s*(//[^\n]*\s*)+EmbeddedHeapCompaction\.AfterFirstFrame\(\);\s*\}', window)
    check(first is not None and window.count('EmbeddedHeapCompaction.') == 1, 'first-frame call in the render loop\'s first-frame block only')
    library = (work / LIBRARY).read_text(encoding='utf-8-sig')
    check(re.search(r'EmbeddedSessions\.PublishControls\(\(\) =>\s*\{\s*//[^\n]*\s*EmbeddedHeapCompaction\.OnSessionEnd\(\);\s*_window\.Exit\(\);\s*\}, paused =>\s*\{'
                    r'\s*//[^\n]*\s*if \(!paused\) EmbeddedHeapCompaction\.BeforeResume\(\);\s*'
                    r'_emulationContext\.System\.TogglePauseEmulation\(paused\);'
                    r'\s*_window\.SetEmbeddedPaused\(paused\);\s*//[^\n]*\s*EmbeddedHeapCompaction\.OnHostPause\(paused, '
                    r'\(\) => EmbeddedSessions\.IsStopping\);\s*\}\);', library) is not None and library.count('EmbeddedHeapCompaction.') == 4 and
          re.search(r'finally\s*\{\s*EmbeddedHeapCompaction\.OnSessionEnd\(\);\s*EmbeddedSessions\.WithdrawControls\(\);\s*DisplaySleep\.Restore\(\);', library) is not None,
          'pause call after the pause control\'s own work; resume waits first; stop and withdraw end the generation')
    check(re.search(r'Volatile\.Read\(ref _pauseGeneration\) != generation\)\s*\{\s*return;\s*\}[^;]*GetGCMemoryInfo', COMPACTION_CLASS, re.S) is not None and
          COMPACTION_CLASS.index('Monitor.TryEnter(_gate)') < COMPACTION_CLASS.index('System.GC.Collect(') and
          re.search(r'BeforeResume\(\)\s*\{\s*System\.Threading\.Interlocked\.Increment\(ref _pauseGeneration\);\s*System\.Threading\.Monitor\.Enter\(_gate\);\s*'
                    r'System\.Threading\.Monitor\.Exit\(_gate\);', COMPACTION_CLASS) is not None,
          'the generation is re-checked inside the gate before collecting; a resume ends the generation then passes the gate')
    check(COMPACTION_CLASS.count('stopping()') == 1 and 'Monitor.Enter(_gate)' in COMPACTION_CLASS and
          COMPACTION_CLASS.index('stopping()') < COMPACTION_CLASS.index('Compact("hostPause"'), 'stopping() is called outside the gate')
    for name in BASELINE:
        added = (work / name).read_text(encoding='utf-8-sig').count('GC.Collect(') - (SOURCE / name).read_text(encoding='utf-8-sig').count('GC.Collect(')
        check(added == (1 if name == MEMORY else 0), 'collections added in ' + name)

    result = subprocess.run([DOTNET, 'build', str(work / 'src/Ryujinx.Library/Ryujinx.Library.csproj'), '-c', 'Release', '-nologo',
                             '-m:1', '-p:NuGetAudit=false'], capture_output=True, text=True, timeout=3600, env=environment, cwd=work)
    if result.returncode:
        print(result.stdout[-6000:], result.stderr[-2000:], flush=True)
    check(result.returncode == 0, 'production Ryujinx.Library builds with the adapter')
    shutil.rmtree(work)

    # Executed fixture: the production class, unchanged, with the segments GC and the Core's GC settings.
    fixture = Path(temporary).resolve() / 'fixture'
    fixture.mkdir()
    shutil.copyfile(ROOT / 'test/melonx_safe_point_compaction/Program.cs', fixture / 'Program.cs')
    (fixture / 'Compaction.cs').write_text('namespace Ryujinx.Library\n{\n' + COMPACTION_CLASS + '}\n')
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
    # The segments GC library of the host runtime: libclrgc.so on Linux, libclrgc.dylib on macOS (the Core CI runner).
    GC_LIBRARY = 'libclrgc.dylib' if platform.system() == 'Darwin' else 'libclrgc.so'
    gc_environment = dict(environment, DOTNET_GCName=GC_LIBRARY, DOTNET_GCConserveMemory='5', DOTNET_GCHighMemPercent='63')
    for mode in ('control', 'candidate', 'pause', 'race'):
        run = subprocess.run([DOTNET, 'bin/Release/net10.0/Probe.dll', mode], cwd=fixture, capture_output=True, text=True,
                             timeout=300, env=gc_environment)
        if run.returncode:
            print(run.stdout[-3000:], run.stderr[-3000:], flush=True)
        check(run.returncode == 0, 'fixture runs: ' + mode)
        reports[mode] = json.loads(run.stdout.strip().splitlines()[-1])

control, candidate, pause, race = reports['control'], reports['candidate'], reports['pause'], reports['race']
for report in reports.values():
    config = report['gcConfig']
    check(config.get('GCRegionRange') == '0' and config.get('GCConserveMem') == '5' and config.get('GCName') == GC_LIBRARY and config.get('GCHighMemPercent') == '99',
          'segments GC with the Core\'s settings: ' + str({k: config.get(k) for k in ('GCRegionRange', 'GCConserveMem', 'GCHighMemPercent', 'GCName')}))
    check(report['policy'] == {'firstFrame63MiB': False, 'firstFrame64MiB': True, 'pauseDevice15': True, 'pauseDevice16': False,
                               'pauseDeviceUnknown': False, 'pauseSmall': False, 'pause59s': False, 'pause60s': True},
          'policy: ' + str(report['policy']))
    check(report['liveIntact'], 'live arrays intact: ' + report['mode'])
    before = report['beforeFirstFrame']
    check(before['lastGcGeneration'] == 0 and before['lohFreeMiB'] >= 150 and before['reclaimableMiB'] >= before['lohFreeMiB'],
          'a boot-like LOH with free space, still reported after a gen0 collection: ' + str(before))
b, a = control['beforeFirstFrame'], control['afterFirstFrame']
check(control['compactionsAfterFirstFrame'] == 0 and a['lohFreeMiB'] == b['lohFreeMiB'] and abs(a['rssMiB'] - b['rssMiB']) <= 16,
      'control: the swept free space stays committed and resident: ' + str((b, a)))
b, a = candidate['beforeFirstFrame'], candidate['afterFirstFrame']
check(candidate['compactionsAfterFirstFrame'] == 1 and a['lohFreeMiB'] <= 8 and b['rssMiB'] - a['rssMiB'] >= 150 and
      b['committedMiB'] - a['committedMiB'] >= 150 and a['lohMiB'] <= b['lohMiB'] - b['lohFreeMiB'] + 8,
      'candidate: the first-frame compaction gives the LOH free space back: ' + str((b, a)))
check(candidate['compactionsAfterSecondFirstFrame'] == 1, 'nothing to reclaim: no second collection')
check(candidate['pauseWithin60s'] == 1, 'a held pause within 60 s of the last compaction does not compact')
check(len([l for l in candidate['journal'] if 'heapCompacted: firstFrame:' in l]) == 1 and len(candidate['journal']) == 1,
      'one journal line: ' + str(candidate['journal']))
check(pause['pauseDevice40'] == 0 and pause['pauseResumedAfter1s'] == 0 and pause['pauseWhileStopping'] == 0 and
      pause['heldPause'] == 1 and pause['secondHeldPauseWithin60s'] == 1,
      'pause: device 40 % no, resumed after 1 s no, close begun no, held at 11 % yes, again within 60 s no: ' + str(pause))
b, a = pause['beforeHeldPause'], pause['afterHeldPause']
check(b['rssMiB'] - a['rssMiB'] >= 150 and a['lohFreeMiB'] <= 8, 'held pause gives the free space back: ' + str((b, a)))
check(len(pause['journal']) == 1 and 'heapCompacted: hostPause:' in pause['journal'][0], 'one pause journal line')
check(race['resumeDuringDelay'] == 0 and race['resumeBetweenCheckAndCollect'] == 0 and race['closeThenNewSession'] == 0,
      'no collection during play: resume in the delay, resume between the check and the collection, close then a new session: ' + str(race))
check(race['inFlightSeen'] and race['resumeReturnedAfterRelease'] and race['resumeWaitedForInFlight'] == 1 and race['resumeWaitMs'] >= 0 and len(race['journal']) == 1 and
      'heapCompacted: hostPause:' in race['journal'][0],
      'a resume arriving during a collection waits for it (worker held at the gate until the resume thread started; the resume returned only after the release): ' + str(race))

inputs = ['build-utils/melonx/adapt_safe_point_compaction.py', 'build-utils/melonx/adapt_session.py', 'test/melonx_adapter_control.py',
          'test/melonx_safe_point_compaction_test.py', 'test/melonx_safe_point_compaction/Program.cs']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core658Preparation',
               postimages={p: hashlib.sha256((FINAL_SOURCE / p).read_bytes()).hexdigest() for p in BASELINE} if FINAL_PREPARATION else {},
               sdk=sdk, gc=GC_LIBRARY + ' (segments), ConserveMemory 5, HighMemoryPercent 99, workstation concurrent, ' + platform.system() + ' CoreCLR',
               reports={k: {key: v for key, v in r.items() if key != 'gcConfig'} for k, r in reports.items()},
               physicalDeviceTested=False, productionLibraryAssemblyBuilt=True, sourceBaseline=BASELINE,
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               limitation='The fixture runs host CoreCLR with the segments GC (' + platform.system() + ' resident bytes, not iOS phys_footprint)'
                          + (', in a container whose cgroup sets a GC heap hard limit' if platform.system() == 'Linux' else '')
                          + '; the footprint change and pause length on an iPhone are known only from a device run.')
out = ROOT / 'dist/melonx/safe-point-compaction-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
