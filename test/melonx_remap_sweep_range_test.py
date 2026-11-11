#!/usr/bin/env python3
"""adapt_remap_sweep_range on the final preparation, against the Core 733 preparation as control, on the real engine.

Usage: melonx_remap_sweep_range_test.py <Core 733 prepared tree>
       melonx_remap_sweep_range_test.py <control> --candidate-source <final preparation containing the adapter>

IPA 725, Hogwarts Legacy (pid 51986; private journals, aggregates only): the bindless delta pass runs 390 to 570 times
per `performance` sample of 5.1 s, visits 53 to 160 pool ids per call of which 88 % are changed, takes 0.43 to 0.68 s
and allocates 18 to 34 KiB per call, in steady scenes too. Upstream re-queues every member of the texture cache's
partially mapped set at every guest Map and Unmap, wherever the event is; the adapter re-queues only the members the
event can concern.

Static: the control is the Core 733 set of three files; the candidate differs by the adapter's three replacements;
UpdatePoolMappings is unchanged; the new check is declared once and called once (from the remap action); no counter is
added and the performance collector is not edited; a drifted file is refused.
Executed: the production Ryujinx.Graphics.Gpu builds from the control and from the candidate; then (test-only
InternalsVisibleTo) test/melonx_remap_sweep_range/Program.cs runs the same seeded script on each engine's real
TextureManager, TextureBindingsManager, TextureBindingsArrayCache, TexturePool, TextureCache, Texture and GPU
MemoryManager, with a backend double that keeps the bytes of every upload: two address spaces sharing one texture
cache, a pool of 256 ids bound through two pool arrays and eight ordinary bindings (textures created partially mapped,
fully mapped, ids sharing one texture, textures referenced at two addresses) and a pool of 32 ids in the other address
space at the same numeric addresses; 440 steps (Map and Unmap of unrelated ranges, events of the other address space,
hole fills, partial unmaps, remaps to other pages, descriptor rewrites, two scripted sequences), each followed by a
commit of both channels. Required:
 0. the scene is the intended one and each engine is deterministic (two control runs give the same digests);
 1. control and candidate have the same digests at every step: what every array element and every ordinary binding
    shows (the bytes of the bound host texture), every pool item's presence and physical range, and its membership of
    the partially mapped set. Backend calls are not part of the digests: sending fewer is the purpose; they are counted
    per kind of step. The same holds in the "dependencies" scene, where textures linked by a copy dependency (which
    cannot be restored in place) stay in the pool: the control destroys and recreates them at every unrelated event,
    the candidate keeps them, and what is bound shows the same bytes;
 2. at every step whose event is unrelated to every texture (another range, or the other address space) the control
    queues every pool reference of every member of the set and the candidate none, except the single first sweep of a
    texture created partially mapped (ChangedMapping still false);
 3. at every other step with an event the candidate queues exactly the control's references restricted to the textures
    the event can concern (computed by the fixture from the state before the event);
 4. sensitivity: wrong variants of the check, built from the adapter's own text, are caught: by the digests (the
    intersection test ignored; the check without its "never swept" and "no pool owner" rules; each rule removed alone;
    the address space comparison inverted) or by requirements 2 and 3 (the address space comparison dropped, which only
    sweeps too much).
Nothing here depends on time or on thread scheduling: the fixture does everything on one thread, waits for nothing and
reads no clock; no duration is measured or compared.
Not an iPhone: whether the device's Map and Unmap events are what re-queues its textures is read in the next session's
arrDeltaElems, arrDeltaChanged and gpuWork.arrayDelta. Writes dist/melonx/remap-sweep-range-checks.json.
"""
from pathlib import Path
import hashlib, json, os, platform, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
FINAL_SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, use_authenticated_libhac_feed  # noqa: E402
_HOLD = []
CONTROL_SOURCE, FINAL_PREPARATION = control_source(FINAL_SOURCE, 'adapt_remap_sweep_range', _HOLD)
import adapt_remap_sweep_range as adapter  # noqa: E402

DOTNET = os.environ.get('DOTNET', 'dotnet')
HARNESS = ROOT / 'test/melonx_remap_sweep_range'
FAKES = ROOT / 'test/melonx_gpu_teardown/Fakes.cs'
GPU = 'src/Ryujinx.Graphics.Gpu/Ryujinx.Graphics.Gpu.csproj'
PROBE = 'MeloNXRemapSweepProbe'
STEPS, SEED = 440, 20261111
MARKER = 'RewindBox (adapt_remap_sweep_range)'
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
control = {name: text(CONTROL_SOURCE, name) for name in adapter.BASELINE}
candidate_text = {}
for name, expected in adapter.BASELINE.items():
    check(sha(CONTROL_SOURCE / name) == expected, 'control is the Core 733 preparation: ' + name)
    rebuilt = control[name]
    for file, old, new in adapter.PAIRS:
        if file == name:
            # Every old text is the control's own: no replacement needs another's result.
            check(control[name].count(old) == 1 and rebuilt.count(old) == 1, 'one site in the control: ' + name)
            check(MARKER in new, 'the replacement carries the adapter\'s marker: ' + name)
            rebuilt = rebuilt.replace(old, new)
    candidate_text[name] = rebuilt
check(len(adapter.PAIRS) == 3 and [pair[0] for pair in adapter.PAIRS] == [adapter.CACHE, adapter.TEXTURE, adapter.POOL] and
      sorted(adapter.BASELINE) == sorted([adapter.CACHE, adapter.TEXTURE, adapter.POOL]),
      'three replacements: one in TextureCache.cs, one in Texture.cs, one in TexturePool.cs, and no other file')
if FINAL_PREPARATION:
    from melonx_adapter_control import files_edited_later  # noqa: E402
    check(not files_edited_later('adapt_remap_sweep_range'), 'no later adapter edits these files')
    for name in adapter.BASELINE:
        check(candidate_text[name] == text(FINAL_SOURCE, name), name + ': the final preparation is the control plus the adapter\'s replacements')
check(all(adapter.TOUCH_NEW.count(part) == 1 for part in (adapter.NEVER_SWEPT_RULE, adapter.NO_OWNER_RULE, adapter.OWNER_TEST)),
      'the check holds its three tests once each')
check(member(control[adapter.TEXTURE], '        public void UpdatePoolMappings()') ==
      member(candidate_text[adapter.TEXTURE], '        public void UpdatePoolMappings()'), 'UpdatePoolMappings is unchanged')
cache = candidate_text[adapter.CACHE]
check(control[adapter.CACHE].count('texture.UpdatePoolMappings();') == cache.count('texture.UpdatePoolMappings();') == 1 and
      cache.count('if (texture.PoolMappingsTouch(memoryManager, e.Address, e.Size))') == 1 and
      cache.index('if (texture.PoolMappingsTouch(') < cache.index('texture.UpdatePoolMappings();'),
      'the remap action sweeps a member only after the check')
check(cache.count('overlaps[i].RemapSweepOverlapped = true;') == 1 and cache.count('overlaps[i].Unmapped(unmapped);') == 1 and
      candidate_text[adapter.TEXTURE].count('RemapSweepOverlapped = false;') == 1,
      'the overlapped textures are marked in the remap action and the mark is consumed by the check')
check(all('PD.' not in new and 'EmbeddedPerformanceDiagnostics' not in new for _, _, new in adapter.PAIRS),
      'the adapter adds no counter and does not use the performance collector')
drift = Path(tempfile.mkdtemp(prefix='melonx-remap-sweep-range-drift-'))
for name in adapter.BASELINE:
    (drift / name).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(CONTROL_SOURCE / name, drift / name)
(drift / adapter.POOL).write_bytes((drift / adapter.POOL).read_bytes() + b'\n// unreviewed drift\n')
try:
    adapter.apply(drift)
    refused = False
except AssertionError:
    refused = True
shutil.rmtree(drift)
check(refused, 'a drifted TexturePool.cs is refused')

# --- Executed: the real engine of both sides ---
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1')
WORK = Path(tempfile.mkdtemp(prefix='melonx-remap-sweep-range-')).resolve()


def dotnet(*arguments, cwd):
    result = subprocess.run([DOTNET, *arguments], capture_output=True, text=True, timeout=2400, env=environment, cwd=cwd)
    if result.returncode:
        errors = [line for line in result.stdout.splitlines() if ': error ' in line]
        print('\n'.join(dict.fromkeys(errors[:40])), result.stdout[-4000:], result.stderr[-2000:], sep='\n', flush=True)
    return result


def build_probe(side):
    directory = WORK / ('probe-' + side)
    build = dotnet('build', str(directory / (PROBE + '.csproj')), '-c', 'Release', '-nologo', '-m:1', '-p:NuGetAudit=false', cwd=directory)
    check(build.returncode == 0, 'the fixture builds against the ' + side + ' engine')


def run_probe(side, scene, what):
    directory = WORK / ('probe-' + side)
    run = subprocess.run([DOTNET, str(directory / ('bin/Release/net10.0/' + PROBE + '.dll')), str(STEPS), str(SEED), '-', scene],
                         capture_output=True, text=True, timeout=1800, env=environment, cwd=directory)
    if run.returncode:
        print(run.stdout[-4000:], run.stderr[-4000:], flush=True)
    check(run.returncode == 0, what + ': the fixture runs')
    return json.loads(next(line for line in run.stdout.splitlines() if line.startswith('{"scene"')))


trees = {}
for side in ('control', 'candidate'):
    tree = trees[side] = WORK / side
    shutil.copytree(CONTROL_SOURCE, tree, ignore=shutil.ignore_patterns('.git', 'bin', 'obj', 'MeloNX'), symlinks=True)
    if side == 'candidate':
        changed = adapter.apply(tree)
        check(sorted(str(p.relative_to(tree)) for p in changed) == sorted(adapter.BASELINE), 'the adapter changed its three files')
        for name in adapter.BASELINE:
            check(text(tree, name) == candidate_text[name], 'candidate is the control plus the adapter\'s replacements: ' + name)
            if FINAL_PREPARATION:
                check((tree / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)
        sources = [path.read_text(encoding='utf-8-sig', errors='replace') for path in (tree / 'src').rglob('*.cs')]
        check(sum(s.count('PoolMappingsTouch(') for s in sources) == 2 and sum(s.count('.ChannelMemoryManager') for s in sources) == 1 and
              sum(s.count('ChannelMemoryManager =>') for s in sources) == 1 and sum(s.count('RemapSweepOverlapped') for s in sources) == 4,
              'the tree declares the check, the pool\'s address space and the mark once, and uses them from the remap action only')
    use_authenticated_libhac_feed(tree, ROOT)
    build = dotnet('build', str(tree / GPU), '-c', 'Release', '-nologo', '-m:1', '-p:NuGetAudit=false', cwd=tree)
    check(build.returncode == 0, side + ': production Ryujinx.Graphics.Gpu builds')
    if side == 'candidate':
        warnings = sorted({line for line in build.stdout.splitlines() if 'warning' in line and
                           any(Path(name).name + '(' in line for name in adapter.BASELINE)})
        check(not warnings, 'no compiler warning in the edited files: ' + '\n'.join(warnings[:5]))
    print(side + ': production Ryujinx.Graphics.Gpu built', flush=True)
    project = tree / GPU
    project_text = project.read_text(encoding='utf-8-sig')
    project.write_text(project_text.replace('</Project>', '  <ItemGroup><InternalsVisibleTo Include="' + PROBE + '" /></ItemGroup>\n</Project>'))
    probe = WORK / ('probe-' + side)
    probe.mkdir()
    shutil.copyfile(HARNESS / 'Program.cs', probe / 'Program.cs')
    shutil.copyfile(FAKES, probe / 'Fakes.cs')
    (probe / (PROBE + '.csproj')).write_text(f'''<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><Nullable>disable</Nullable>
    <AllowUnsafeBlocks>true</AllowUnsafeBlocks><NoWarn>CA1416;CS8632</NoWarn><NuGetAudit>false</NuGetAudit>
    <ManagePackageVersionsCentrally>false</ManagePackageVersionsCentrally>
  </PropertyGroup>
  <ItemGroup>
    <ProjectReference Include="{tree}/src/Ryujinx.Graphics.Gpu/Ryujinx.Graphics.Gpu.csproj" />
    <ProjectReference Include="{tree}/src/Ryujinx.Cpu/Ryujinx.Cpu.csproj" />
  </ItemGroup>
</Project>
''')
    for extra in ('global.json', 'nuget.config'):
        if (tree / extra).exists():
            shutil.copyfile(tree / extra, probe / extra)
    build_probe(side)

reports = dict(control=run_probe('control', 'gated', 'control'), controlAgain=run_probe('control', 'gated', 'control, second run'),
               candidate=run_probe('candidate', 'gated', 'candidate'),
               dependenciesControl=run_probe('control', 'dependencies', 'control, dependencies scene'),
               dependenciesControlAgain=run_probe('control', 'dependencies', 'control, dependencies scene, second run'),
               dependenciesCandidate=run_probe('candidate', 'dependencies', 'candidate, dependencies scene'))

# Sensitivity: the candidate's check altered (Texture.cs only), the fixture rebuilt against it.
WRONG_NO_OWNER = adapter.NO_OWNER_RULE.replace('return true;', 'return false;')
VARIANTS = {
    'intersectionIgnored': [(adapter.OWNER_TEST, 'if (owner.GpuAddress == ulong.MaxValue)')],
    'withoutBothRules': [(adapter.NEVER_SWEPT_RULE, ''), (adapter.NO_OWNER_RULE, WRONG_NO_OWNER)],
    'withoutNeverSweptRule': [(adapter.NEVER_SWEPT_RULE, '')],
    'withoutNoOwnerRule': [(adapter.NO_OWNER_RULE, WRONG_NO_OWNER)],
    'addressSpaceInverted': [(adapter.OWNER_TEST, adapter.OWNER_TEST.replace('== memoryManager', '!= memoryManager'))],
    'addressSpaceIgnored': [(adapter.OWNER_TEST, adapter.OWNER_TEST.replace('owner.Pool.ChannelMemoryManager == memoryManager && ', ''))],
}
texture_path = trees['candidate'] / adapter.TEXTURE
for variant, replacements in VARIANTS.items():
    wrong = adapter.TOUCH_NEW
    for old, new in replacements:
        check(wrong.count(old) == 1 and old != new, variant + ': one site to alter in the adapter\'s text')
        wrong = wrong.replace(old, new)
    check(control[adapter.TEXTURE].count(adapter.TOUCH_OLD) == 1, variant + ': one site in the control')
    texture_path.write_text(control[adapter.TEXTURE].replace(adapter.TOUCH_OLD, wrong), encoding='utf-8')
    build_probe('candidate')
    reports[variant] = run_probe('candidate', 'gated', 'wrong variant ' + variant)
shutil.rmtree(WORK)
if os.environ.get('MELONX_TEST_REPORTS'):
    Path(os.environ['MELONX_TEST_REPORTS']).write_text(json.dumps(reports, indent=1))

UNRELATED = ('unrelatedMap', 'unrelatedUnmap', 'otherMmMap', 'otherMmUnmap', 'alUnrelated')
PARTS = ('arrayElements', 'ordinaryBindings', 'poolRanges', 'partialSet')


def first_difference(a, b):
    for x, y in zip(a['steps'], b['steps'], strict=True):
        if x['d'] != y['d']:
            return dict(step=x['i'], kind=x['k'], differs=[name for name, p, q in zip(PARTS, x['d'], y['d']) if p != q])
    return None


def queue_violations(reference, other):
    """The steps at which `other` does not queue exactly what the reference's state says the event concerns."""
    return [(x['i'], x['k'], len(y['queued']), len(x['expected'])) for x, y in zip(reference['steps'], other['steps'], strict=True)
            if 'ev' in x and y['queued'] != x['expected']]


def by_kind(report, field):
    totals = {}
    for step in report['steps']:
        value = step.get(field)
        value = len(value) if isinstance(value, list) else value
        if value is not None and value >= 0:
            totals[step['k']] = totals.get(step['k'], 0) + value
    return totals


def total(report, field):
    return sum(by_kind(report, field).values())


c, k = reports['control'], reports['candidate']

# --- 0. the scene, and determinism ---
scene = c['scene']
kinds = {}
for step in c['steps']:
    kinds[step['k']] = kinds.get(step['k'], 0) + 1
check(scene == k['scene'] == reports['controlAgain']['scene'], 'same scene on both engines')
check(scene['pool1Items'] == 254 and scene['pool2Items'] == 32 and scene['partiallyMappedSetAtStart'] >= 40 and
      scene['idsSharingOneAddress'] == 10 and scene['texturesWithTwoAddresses'] == 9 and scene['addressSpaces'] == 2 and
      scene['arrays'] == [256, 255, 32] and scene['ordinaryBindings'] == 8 and scene['dependencyScene'] is False,
      'the intended scene: ' + json.dumps(scene))
check(len(c['steps']) == len(k['steps']) == STEPS and c['seed'] == k['seed'] == SEED, 'the same %d steps of seed %d on both engines' % (STEPS, SEED))
check([step['k'] for step in c['steps']] == [step['k'] for step in k['steps']] and
      [step.get('ev') for step in c['steps']] == [step.get('ev') for step in k['steps']], 'the same events in the same order')
check(all(kinds.get(kind, 0) >= 4 for kind in ('unrelatedMap', 'unrelatedUnmap', 'otherMmMap', 'otherMmUnmap', 'holeFill', 'partialUnmap', 'remap',
                                               'rewrite', 'mm2HoleFill', 'mm2PartialUnmap', 'scAway', 'scFillBack', 'alAway', 'alUnrelated',
                                               'alFill', 'alBack', 'alClean')), 'every kind of step occurs: ' + json.dumps(kinds))
check(first_difference(c, reports['controlAgain']) is None and
      [step.get('queued') for step in c['steps']] == [step.get('queued') for step in reports['controlAgain']['steps']],
      'the control is deterministic: ' + json.dumps(first_difference(c, reports['controlAgain'])))
check(all(step.get('pending', 0) == 0 and step['leftInQueues'] == 0 for report in (c, k) for step in report['steps']),
      'every queued reference is resolved by the commit that follows its event')

# --- 1. the same observable state at every step ---
difference = first_difference(c, k)
check(difference is None, 'control and candidate digests differ: ' + json.dumps(difference))
digests_equal = sum(x['d'] == y['d'] for x, y in zip(c['steps'], k['steps'], strict=True))
check(digests_equal == STEPS, 'the digests are equal at every step')
check(total(c, 'uploads') == total(k, 'uploads') and total(c, 'fullRebuildElements') == total(k, 'fullRebuildElements'),
      'the same uploads and whole array rebuilds on both sides')
dc, dk = reports['dependenciesControl'], reports['dependenciesCandidate']
check(dc['scene']['dependencyScene'] is True and dc['scene'] == dk['scene'] and len(dc['steps']) == len(dk['steps']) == STEPS,
      'dependencies scene: the same scene on both engines')
check(first_difference(dc, reports['dependenciesControlAgain']) is None,
      'dependencies scene: the control is deterministic: ' + json.dumps(first_difference(dc, reports['dependenciesControlAgain'])))
difference = first_difference(dc, dk)
check(difference is None, 'dependencies scene: control and candidate digests differ: ' + json.dumps(difference))
check(total(dc, 'hostTexturesCreated') > 0, 'dependencies scene: textures are created during the script (the control recreates them)')

# --- 2. unrelated events: the control queues every reference of every member, the candidate none ---
unrelated = dict(steps=0, controlQueued=0, candidateQueued=0, stepsWhereCandidateQueuesNothing=0, firstSweeps=0)
for x, y in zip(c['steps'], k['steps'], strict=True):
    if x['k'] in UNRELATED:
        check(x['overlapped'] == 0, f"step {x['i']} ({x['k']}) physically overlaps no texture")
        check(len(x['queued']) == x['sweepOwners'] and x['sweepOwners'] >= x['membersWithOwners'] > 0,
              f"step {x['i']} ({x['k']}): the control queues every pool reference of every member: {len(x['queued'])} of {x['sweepOwners']}")
        # The one exception is the first sweep of a texture created partially mapped (never swept: ChangedMapping false).
        check(y['queued'] == x['expected'] and (y['queued'] == [] or x['neverSwept'] > 0),
              f"step {x['i']} ({x['k']}): the candidate queues nothing but never swept textures: {len(y['queued'])}, never swept {x['neverSwept']}")
        unrelated['steps'] += 1
        unrelated['controlQueued'] += len(x['queued'])
        unrelated['candidateQueued'] += len(y['queued'])
        unrelated['stepsWhereCandidateQueuesNothing'] += y['queued'] == []
        unrelated['firstSweeps'] += x['neverSwept']
check(unrelated['steps'] >= 100 and unrelated['controlQueued'] > 1000 and unrelated['stepsWhereCandidateQueuesNothing'] >= unrelated['steps'] - 10,
      'unrelated events exercised: ' + json.dumps(unrelated))

# --- 3. concerning events: the candidate queues the control's references of the concerned textures only ---
concerning = dict(steps=0, controlQueued=0, candidateQueued=0)
for x, y in zip(c['steps'], k['steps'], strict=True):
    if 'ev' in x and x['k'] not in UNRELATED:
        check(set(x['expected']) <= set(x['queued']), f"step {x['i']} ({x['k']}): what the event concerns is part of what the control queues")
        check(y['queued'] == x['expected'] == y['expected'],
              f"step {x['i']} ({x['k']}): candidate queued {len(y['queued'])}, the event concerns {len(x['expected'])} of the control's {len(x['queued'])}")
        concerning['steps'] += 1
        concerning['controlQueued'] += len(x['queued'])
        concerning['candidateQueued'] += len(y['queued'])
check(queue_violations(c, k) == [], 'requirements 2 and 3 hold for the candidate at every event')
check(concerning['steps'] >= 80 and 0 < concerning['candidateQueued'] < concerning['controlQueued'], 'concerning events exercised: ' + json.dumps(concerning))
for kind in ('holeFill', 'partialUnmap', 'remap', 'mm2HoleFill', 'mm2PartialUnmap'):
    check(by_kind(k, 'queued').get(kind, 0) > 0, 'the candidate queues at ' + kind + ' steps')
check(total(k, 'deltaChanged') < total(c, 'deltaChanged') and total(k, 'setTexturesElements') < total(c, 'setTexturesElements') and
      total(k, 'queued') < total(c, 'queued'), 'the candidate resolves and sends fewer array elements')

# --- 4. sensitivity ---
sensitivity = {}
for variant in VARIANTS:
    wrong = reports[variant]
    difference = first_difference(c, wrong)
    violations = queue_violations(c, wrong)
    sensitivity[variant] = dict(digestDifference=difference, stepsWithOtherDigest=sum(x['d'] != y['d'] for x, y in zip(c['steps'], wrong['steps'], strict=True)),
                                queueViolations=len(violations), queueViolationKinds=sorted({v[1] for v in violations}))
    if variant == 'addressSpaceIgnored':
        # Sweeping too much is not unsound: the state stays the same; the queue requirements see it, at events whose
        # numeric range holds a texture of the other address space.
        check(difference is None and any(v[1] in ('otherMmMap', 'otherMmUnmap') for v in violations),
              variant + ': caught by the queue requirements at events of the other address space: ' + json.dumps(sensitivity[variant]))
    else:
        check(difference is not None, variant + ': caught by the digests')
check(sensitivity['intersectionIgnored']['digestDifference']['kind'] in ('holeFill', 'mm2HoleFill', 'remap', 'partialUnmap', 'scFillBack') and
      sensitivity['addressSpaceInverted']['digestDifference']['kind'] in ('holeFill', 'mm2HoleFill', 'remap', 'partialUnmap', 'scFillBack'),
      'a check that ignores the range, or the right address space, shows at a step that changes a mapping: ' + json.dumps(sensitivity))
check(sensitivity['withoutNoOwnerRule']['digestDifference']['kind'] == 'scFillBack' and sensitivity['withoutBothRules']['digestDifference']['kind'] == 'scFillBack',
      'without the "no pool owner" rule a hole filled while only the short cache holds the texture is missed: ' + json.dumps(sensitivity))
check(sensitivity['withoutNeverSweptRule']['digestDifference']['kind'] == 'alBack',
      'without the "never swept" rule a hole filled at an address no pool owner uses is missed: ' + json.dumps(sensitivity))

FIELDS = ('queued', 'restored', 'deltaVisited', 'deltaChanged', 'setTexturesCalls', 'setTexturesElements', 'slotCalls', 'uploads', 'hostTexturesCreated')
inputs = ['build-utils/melonx/adapt_remap_sweep_range.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_remap_sweep_range_test.py', 'test/melonx_remap_sweep_range/Program.cs', 'test/melonx_gpu_teardown/Fakes.cs',
          'test/melonx_adapter_control.py']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core733Preparation',
               postimages={p: sha(FINAL_SOURCE / p) for p in adapter.BASELINE} if FINAL_PREPARATION else {},
               productionGpuAssemblyBuilt=True,
               comparison=dict(steps=STEPS, seed=SEED, digestsEqual=digests_equal,
                               unrelatedEvents=unrelated['steps'], concerningEvents=concerning['steps'],
                               controlQueued=total(c, 'queued'), candidateQueued=total(k, 'queued'),
                               controlDeltaChanged=total(c, 'deltaChanged'), candidateDeltaChanged=total(k, 'deltaChanged'),
                               controlSetTexturesElements=total(c, 'setTexturesElements'), candidateSetTexturesElements=total(k, 'setTexturesElements'),
                               sensitivityVariantsFailed=len(VARIANTS)),
               scene=scene, stepKinds=kinds, unrelated=unrelated, concerning=concerning,
               dependenciesScene=dict(steps=STEPS, digestsEqual=sum(x['d'] == y['d'] for x, y in zip(dc['steps'], dk['steps'], strict=True)),
                                      hostTexturesCreated=dict(control=total(dc, 'hostTexturesCreated'), candidate=total(dk, 'hostTexturesCreated')),
                                      uploads=dict(control=total(dc, 'uploads'), candidate=total(dk, 'uploads')),
                                      queued=dict(control=total(dc, 'queued'), candidate=total(dk, 'queued'))),
               informational=dict(stepsWithOtherHostTextureIdentities=sum(x['identities'] != y['identities'] for x, y in zip(c['steps'], k['steps'])),
                                  stepsWithOtherChangedMappingFlags=sum(x['changedMappingFlags'] != y['changedMappingFlags'] for x, y in zip(c['steps'], k['steps']))),
               perKind={field: dict(control=by_kind(c, field), candidate=by_kind(k, field)) for field in FIELDS},
               sensitivity=sensitivity, sdk=sdk, host=platform.system(), physicalDeviceTested=False,
               deviceEvidence='IPA 725, Hogwarts Legacy, pid 51986 (private journals): UpdateFromPoolDelta 390 to 570 calls per performance '
                              'sample of 5.1 s, 53 to 160 ids visited per call of which 88 % changed, 0.43 to 0.68 s, 18 to 34 KiB per call',
               inputs={name: sha(ROOT / name) for name in inputs},
               limitation='One thread, a backend double and a scripted guest: whether the device\'s Map and Unmap events are what re-queues '
                          'its textures is not shown here; arrDeltaElems, arrDeltaChanged and gpuWork.arrayDelta of the next session decide it. '
                          'Views and textures with views, descriptors with a base level, and events concurrent with the GPU thread are not in the script.')
out = ROOT / 'dist/melonx/remap-sweep-range-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
