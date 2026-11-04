#!/usr/bin/env python3
"""Gen0 budget ceiling for scene transitions (adapt_gc_latency), and the evaluation of SustainedLowLatency.

Usage: melonx_gc_latency_test.py <prepared MeloNX tree (adapt_gc_latency BASELINE)>
       melonx_gc_latency_test.py <control> --candidate-source <final preparation containing the adapter>

Applies the adapter to a copy of the preparation, builds the production Ryujinx.Library for the control and the
candidate, and evaluates (MSBuild, RuntimeIdentifier ios-arm64) the RuntimeHostConfigurationOption items ILC embeds as
runtime knobs in the iOS publish. Static checks: only Ryujinx.Library.csproj changes, by one System.GC.Gen0MaxBudget
item; the other GC knobs (ConserveMemory 5, HighMemoryPercent 99) and the absence of System.GC.Concurrent (background GC
on) are unchanged; Library.cs (Load's teardown collections) is untouched and nothing sets a GC latency mode.

Measurement (test/melonx_gc_latency/Program.cs): a NativeAOT linux-x64 host is published twice, with the control's and
the candidate's evaluated System.GC.* knobs, and run on a transition workload (scene unload of 40 % of a long-lived
heap, then ~720 MiB of short-lived arrays per transition, 5 cycles) and on a fragmenting unload (85 %). The iPhone's
cache-derived gen0 minimum (8 MiB: 16 MiB L2 * 4/5 * 5/8) is given to both through DOTNET_GCgen0size, since this host's
L3 would otherwise make it 136 MiB. Median of 3 seeds, runs interleaved. Evaluation-only variants: the control under
SustainedLowLatency (set for the session, restored before the teardown collections), and both modes with ConserveMemory 0.
Writes dist/melonx/gc-latency-checks.json. No device.
"""
from pathlib import Path
import hashlib, json, os, shutil, statistics, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source  # noqa: E402
_HOLD = []
FINAL_SOURCE = SOURCE
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_gc_latency', _HOLD)
from adapt_gc_latency import apply, BASELINE, ADDED, GEN0_MAX_BUDGET  # noqa: E402

PROJECT = 'src/Ryujinx.Library/Ryujinx.Library.csproj'
LIBRARY = 'src/Ryujinx.Library/Library.cs'
DOTNET = os.environ.get('DOTNET', 'dotnet')
DEVICE_GEN0_MIN = 8 * 1024 * 1024
REPETITIONS = 3
checks = 0
measurements = {}


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def use_authenticated_libhac_feed(tree):
    """As in melonx_binder_teardown_test.py: a tree still declaring the unreachable upstream LibHac feed uses the
    authenticated local package (dist/melonx/libhac-feed, build_libhac identity receipt). Otherwise unchanged."""
    lock = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())['libHac']
    feed = ROOT / 'dist/melonx/libhac-feed'
    package = feed / (lock['package'] + '.' + lock['version'] + '.nupkg')
    receipt = ROOT / 'dist/melonx/libhac-identity.json'
    config = (tree / 'nuget.config').read_text(encoding='utf-8-sig')
    if 'https://starforgejo.dev/api/packages/Ryulynx/nuget/index.json' not in config or not package.is_file() or not receipt.is_file():
        return
    identity = json.loads(receipt.read_text())
    check(identity['source'] == lock and hashlib.sha256(package.read_bytes()).hexdigest() == identity['packageSha256'],
          'the local LibHac package is the authenticated one')
    from build_libhac import configure_feed
    configure_feed(tree, feed, lock['package'])


def run(command, cwd, env, timeout=2400):
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, env=env, cwd=cwd)
    if result.returncode:
        print(result.stdout[-5000:], result.stderr[-2000:], flush=True)
    return result


for name, expected in BASELINE.items():
    check(hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected, 'not the pinned preparation: ' + name)

environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
for key in [k for k in environment if k.startswith(('DOTNET_GC', 'DOTNET_gc', 'COMPlus_'))]:
    del environment[key]
texts, knobs, library_texts = {}, {}, {}
with tempfile.TemporaryDirectory(prefix='melonx-gc-latency-') as temporary:
    temporary = Path(temporary).resolve()
    for variant in ('control', 'candidate'):
        work = temporary / variant
        shutil.copytree(SOURCE, work, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
        use_authenticated_libhac_feed(work)
        if variant == 'candidate':
            changed = apply(work)
            check(sorted(str(p.relative_to(work)) for p in changed) == sorted(BASELINE), 'adapter changed other files')
            if FINAL_PREPARATION:
                for name in BASELINE:
                    check((work / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)
        texts[variant] = (work / PROJECT).read_text(encoding='utf-8-sig')
        library_texts[variant] = (work / LIBRARY).read_bytes()
        # The knobs ILC embeds in the iOS publish (Microsoft.NETCore.Native.targets: --runtimeknob per item).
        evaluated = run([DOTNET, 'msbuild', str(work / PROJECT), '-getItem:RuntimeHostConfigurationOption',
                         '-p:RuntimeIdentifier=ios-arm64', '-p:Configuration=Release', '-nologo'], work, environment, 600)
        check(evaluated.returncode == 0, variant + ': project evaluates for ios-arm64')
        items = json.loads(evaluated.stdout)['Items']['RuntimeHostConfigurationOption']
        knobs[variant] = {item['Identity']: item.get('Value', '') for item in items}
        built = run([DOTNET, 'build', str(work / PROJECT), '-c', 'Release', '-nologo', '-m:1', '-p:NuGetAudit=false'], work, environment)
        check(built.returncode == 0, variant + ' production Ryujinx.Library builds')
        print(variant + ': production Ryujinx.Library built; GC knobs ' +
              json.dumps({k: v for k, v in knobs[variant].items() if k.startswith('System.GC.')}), flush=True)

    # Static: one knob added to the project, nothing else.
    control_text, candidate_text = texts['control'], texts['candidate']
    check(candidate_text.count(ADDED) == 1 and candidate_text.replace(ADDED, '', 1) == control_text,
          'project unchanged but the Gen0MaxBudget item')
    check(library_texts['control'] == library_texts['candidate'], 'Library.cs untouched (Load and its teardown collections)')
    library = library_texts['candidate'].decode('utf-8-sig')
    check('GC.Collect(2, GCCollectionMode.Aggressive, blocking: true, compacting: true);' in library and
          'GCSettings.LatencyMode' not in library and 'GCLatencyMode' not in library,
          'teardown collections as prepared; no latency mode set by the session')
    gc_control = {k: v for k, v in knobs['control'].items() if k.startswith('System.GC.')}
    gc_candidate = {k: v for k, v in knobs['candidate'].items() if k.startswith('System.GC.')}
    check(gc_control == {'System.GC.ConserveMemory': '5', 'System.GC.HighMemoryPercent': '99'}, 'control GC knobs: ' + str(gc_control))
    check(gc_candidate == dict(gc_control, **{'System.GC.Gen0MaxBudget': str(GEN0_MAX_BUDGET)}), 'candidate GC knobs: ' + str(gc_candidate))
    check({k: v for k, v in knobs['control'].items() if not k.startswith('System.GC.')} ==
          {k: v for k, v in knobs['candidate'].items() if not k.startswith('System.GC.')}, 'other runtime knobs unchanged')
    check('System.GC.Concurrent' not in knobs['candidate'] and 'System.GC.Server' not in knobs['candidate'],
          'workstation GC with background GC (System.GC.Concurrent default true) in the iOS publish')

    # NativeAOT hosts with each variant's GC knobs.
    program = ROOT / 'test/melonx_gc_latency/Program.cs'
    hosts = {}
    for variant in ('control', 'candidate'):
        fixture = temporary / ('host-' + variant)
        fixture.mkdir()
        shutil.copyfile(program, fixture / 'Program.cs')
        items = ''.join('<RuntimeHostConfigurationOption Include="%s" Value="%s" />' % (k, v)
                        for k, v in sorted({'control': gc_control, 'candidate': gc_candidate}[variant].items()))
        (fixture / 'Host.csproj').write_text(
            '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
            '<PublishAot>true</PublishAot><InvariantGlobalization>true</InvariantGlobalization><Nullable>disable</Nullable>'
            '<NuGetAudit>false</NuGetAudit><OptimizationPreference>Speed</OptimizationPreference></PropertyGroup>'
            '<ItemGroup>' + items + '</ItemGroup></Project>\n')
        published = run([DOTNET, 'publish', str(fixture / 'Host.csproj'), '-c', 'Release', '-r', 'linux-x64', '-nologo',
                         '-p:NuGetAudit=false', '-o', str(fixture / 'out')], fixture, environment, 900)
        check(published.returncode == 0, variant + ' NativeAOT host publishes')
        hosts[variant] = fixture / 'out/Host'

    device = dict(environment, DOTNET_GCgen0size='%x' % DEVICE_GEN0_MIN)
    scenarios = {'transition': [], 'fragmented': ['--unload', '0.85', '--no-large-objects']}
    variants = {
        'control': ('control', [], {}),
        'candidate': ('candidate', [], {}),
        'controlSustained': ('control', ['--sustained'], {}),
        'conserve0': ('control', [], {'DOTNET_GCConserveMemory': '0'}),
        'conserve0Sustained': ('control', ['--sustained'], {'DOTNET_GCConserveMemory': '0'}),
    }
    plan = {'transition': ('control', 'candidate', 'controlSustained'),
            'fragmented': ('control', 'candidate', 'controlSustained', 'conserve0', 'conserve0Sustained')}
    reports = {}
    for repetition in range(REPETITIONS):
        for scenario, arguments in scenarios.items():
            for name in plan[scenario]:
                host, extra, env = variants[name]
                result = run([str(hosts[host])] + arguments + extra + ['--seed', str(650 + repetition)], ROOT, dict(device, **env), 600)
                check(result.returncode == 0, scenario + ' ' + name + ' runs')
                report = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
                reports.setdefault(scenario, {}).setdefault(name, []).append(report)
                print('%s %s seed %d: pause %.0f ms, max %.0f ms, gen0/1/2 %s, blocking gen2 %d, frame p99 %.1f ms, peak committed %d MiB'
                      % (scenario, name, 650 + repetition, report['totalPauseMs'], report['maxPauseMs'], report['gcCounts'],
                         report['blockingGen2'], report['frameP99Ms'], report['peakCommittedMiB']), flush=True)

    keys = ('totalPauseMs', 'transitionPauseMs', 'steadyPauseMs', 'maxPauseMs', 'maxEphemeralPauseMs', 'blockingGen2',
            'blockingGen2PauseMs', 'backgroundGen2', 'frameP99Ms', 'frameMaxMs', 'framesOver33Ms', 'transitionFrameP50Ms',
            'peakHeapMiB', 'peakCommittedMiB', 'allocatedMiB')
    medians = {scenario: {name: dict({k: statistics.median(r[k] for r in runs) for k in keys},
                                     gen0=statistics.median(r['gcCounts'][0] for r in runs),
                                     gen1=statistics.median(r['gcCounts'][1] for r in runs),
                                     gen2=statistics.median(r['gcCounts'][2] for r in runs))
                          for name, runs in by_name.items()} for scenario, by_name in reports.items()}

    # Every run: the knobs reached the GC; same work; teardown collections blocking and compacting in the normal mode.
    for scenario, by_name in reports.items():
        for name, runs in by_name.items():
            host, extra, env = variants[name]
            for report in runs:
                config = report['gcConfig']
                check(config['ConcurrentGC'] == 'True' and config['ServerGC'] == 'False', name + ': workstation background GC')
                check(config['GCHighMemPercent'] == '99' and config['GCConserveMem'] == ('0' if env else '5'), name + ': knobs ' + str(config))
                check(config['GCGen0MaxBudget'] == str(GEN0_MAX_BUDGET if host == 'candidate' else DEVICE_GEN0_MIN),
                      name + ': gen0 ceiling ' + config['GCGen0MaxBudget'])
                check(report['modeDuringSession'] == ('SustainedLowLatency' if extra else 'Interactive') and
                      report['modeAtTeardown'] == 'Interactive', name + ': latency mode')
                check(report['teardownFullBlocking'] and report['teardownCompacted'], name + ': teardown collection blocking and compacting')
                check(report['observedCollections'] >= 0.95 * report['gcCounts'][0], name + ': collections observed')
        allocated = {name: [r['allocatedMiB'] for r in runs] for name, runs in by_name.items()}
        check(len({tuple(v) for v in allocated.values()}) == 1, scenario + ': identical work in every variant ' + str(allocated))

    control, candidate = medians['transition']['control'], medians['transition']['candidate']
    check(candidate['gen0'] <= control['gen0'] / 3, 'transition: gen0 collections cut (%s -> %s)' % (control['gen0'], candidate['gen0']))
    check(candidate['totalPauseMs'] <= 0.8 * control['totalPauseMs'],
          'transition: total pause at least 20 %% shorter (%s -> %s ms)' % (control['totalPauseMs'], candidate['totalPauseMs']))
    check(candidate['frameP99Ms'] < control['frameP99Ms'], 'transition: frame p99 shorter')
    check(candidate['blockingGen2'] <= control['blockingGen2'], 'transition: no added blocking gen2')
    check(candidate['peakCommittedMiB'] - control['peakCommittedMiB'] <= 128, 'transition: peak committed within 128 MiB')
    fragmented_control, fragmented_candidate = medians['fragmented']['control'], medians['fragmented']['candidate']
    check(fragmented_candidate['totalPauseMs'] < fragmented_control['totalPauseMs'], 'fragmented: total pause shorter')
    check(fragmented_candidate['gen0'] <= fragmented_control['gen0'] / 3, 'fragmented: gen0 collections cut')
    check(fragmented_candidate['peakCommittedMiB'] - fragmented_control['peakCommittedMiB'] <= 128, 'fragmented: peak committed within 128 MiB')
    # Evaluation (not adopted): under ConserveMemory 5 SustainedLowLatency keeps the blocking compacting gen2 of a
    # fragmenting unload (ConserveMemory's rule ignores the latency mode).
    check(fragmented_control['blockingGen2'] >= 1 and medians['fragmented']['controlSustained']['blockingGen2'] >= 1,
          'fragmented: the blocking gen2 happens under ConserveMemory 5 with or without SustainedLowLatency')
    check(medians['transition']['controlSustained']['blockingGen2'] == control['blockingGen2'],
          'transition: SustainedLowLatency changes no blocking gen2 count')
    measurements = medians

    inputs = ['build-utils/melonx/adapt_gc_latency.py', 'build-utils/melonx/adapt_session.py', 'test/melonx_gc_latency_test.py',
              'test/melonx_gc_latency/Program.cs', 'test/melonx_adapter_control.py']
    sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
    receipt = dict(
        result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
        sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'pinnedPreparation',
        postimages={p: hashlib.sha256((FINAL_SOURCE / p).read_bytes()).hexdigest() for p in BASELINE} if FINAL_PREPARATION else {},
        sourceBaseline=BASELINE, evaluatedGcKnobs={'control': gc_control, 'candidate': gc_candidate},
        hostRuntime='NativeAOT linux-x64 (same gc.cpp and RhConfig knob path as ios-arm64)',
        emulatedDeviceGen0MinimumBytes=DEVICE_GEN0_MIN, repetitions=REPETITIONS, measurements=measurements,
        evaluation={'sustainedLowLatency': 'not adopted: under ConserveMemory 5 the blocking compacting gen2 after a fragmenting '
                                           'unload stays (joined_generation_to_condemn ConserveMemory rule ignores the latency '
                                           'mode); no change on the transition workload',
                    'conserveMemory0': 'evaluation only: see measurements.fragmented.conserve0*'},
        sdk=sdk, physicalDeviceTested=False, productionLibraryBuilt=True,
        inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
        limitation='Measured on a NativeAOT linux-x64 host with a synthetic workload and the iPhone gen0 minimum emulated '
                   '(DOTNET_GCgen0size 8 MiB), 4 cores, a cgroup-derived heap hard limit the device does not have; the '
                   'emulator\'s thread count (suspension cost) and real allocation mix are not reproduced. The blocking '
                   'compacting gen2 of ConserveMemory\'s fragmentation rule is not removed. Device check: MiB allocated per '
                   'gen0 collection in transition windows of the performance journal.')
    out = ROOT / 'dist/melonx/gc-latency-checks.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipt, indent=2) + '\n')
    for scenario, by_name in medians.items():
        for name, values in by_name.items():
            print('median %s %s: %s' % (scenario, name, json.dumps(values)), flush=True)
    print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
