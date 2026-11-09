#!/usr/bin/env python3
"""A texture array changed again in the same command buffer references only what it did not hold
(adapt_array_reference_deltas), before and after.

Usage: melonx_array_reference_deltas_test.py <Core 713 prepared MeloNX tree>
       melonx_array_reference_deltas_test.py <control> --candidate-source <final preparation containing the adapter>

Control is the preparation without the adapter, candidate adds it. Static checks bind the mechanism: the production
Auto adds a command buffer reference once per command buffer (ownership bit) and resets a value only when its last
reference, command buffers included, is released; the delivered AddReferences walks the counted views and samplers once
per command buffer, submission and change. Candidate: only the adapter's replacements, fail closed; the production
Ryujinx.Graphics.Vulkan assembly builds. Executed: the whole Vulkan TextureArray.cs and ResourceArray.cs of control and
candidate, with the doubles of test/melonx_array_descriptor_ranges/Boundaries.cs (Auto ownership per command buffer, the
manual descriptor set cache, command buffers completed two submissions behind), through test/melonx_array_reference_deltas
(rounds of a small change then a bind in each command buffer, new views and samplers, a view entering and leaving between
two binds, a destroyed view entering, more than 1 024 new views between two binds, a large update). Every bind checks the
set's elements, its holder and that the command buffer owns every view and sampler the set references. Policy on: the
same descriptors written (trace), sets, binds, barriers and invalidations in both, fewer Gets and references added in
the candidate. Policy off: identical. A variant that does not reference the new views must fail (ownership). No device,
no MoltenVK. Writes dist/melonx/array-reference-deltas-checks.json.
"""
from pathlib import Path
import hashlib, json, os, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, files_edited_later, use_authenticated_libhac_feed  # noqa: E402
_HOLD = []
FINAL_SOURCE = SOURCE
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_array_reference_deltas', _HOLD)
import adapt_array_reference_deltas  # noqa: E402
from adapt_array_reference_deltas import apply, BASELINE, ARRAY  # noqa: E402

RESOURCE = 'src/Ryujinx.Graphics.Vulkan/ResourceArray.cs'
FIXTURE = ['test/melonx_array_reference_deltas/Program.cs', 'test/melonx_array_descriptor_ranges/Boundaries.cs']
DOTNET = os.environ.get('DOTNET', 'dotnet')
TAG = 'RewindBox (adapt_array_reference_deltas)'
PROJECT = '''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><AllowUnsafeBlocks>true</AllowUnsafeBlocks>
<Nullable>disable</Nullable><ImplicitUsings>disable</ImplicitUsings><EnableNETAnalyzers>false</EnableNETAnalyzers>
<NuGetAudit>false</NuGetAudit><NoWarn>0649;0169;0414</NoWarn></PropertyGroup></Project>'''
NEW_VIEW_GET = '''                    if (view.Get(cbs).Value.Handle == 0)'''
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


def read(tree, name):
    return (tree / name).read_text(encoding='utf-8-sig')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


for name, expected in BASELINE.items():
    check(sha(SOURCE / name) == expected, 'not the pinned preparation: ' + name)

vulkan = 'src/Ryujinx.Graphics.Vulkan/'
auto = read(SOURCE, vulkan + 'Auto.cs')
check('if (_cbOwnership.Set(cbs.CommandBufferIndex))' in member(auto, 'public void AddCommandBufferDependencies(CommandBufferScoped cbs)') and
      'if (!_destroyed)' in member(auto, 'public T Get(CommandBufferScoped cbs)') and
      '_value = default;' in member(auto, 'public void DecrementReferenceCount()') and
      'cbs.AddDependant(this);' in auto,
      'Auto: one command buffer reference per command buffer; a value reset only when its last reference is released')
delivered = member(read(SOURCE, ARRAY), 'private void AddReferences(CommandBufferScoped cbs, TextureView dummyTexture, SamplerHolder dummySampler)')
check('foreach (Auto<DisposableImageView> view in _viewReferences.Keys)' in delivered and
      'cbs.CommandBufferIndex == _referencesCommandBuffer && submission == _referencesSubmission' in delivered,
      'delivered: the counted views and samplers walked once per command buffer, submission and change')

replacements, reports = [], {}
original_once = adapt_array_reference_deltas.once
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_TieredCompilation='0')
pin = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())
built = []
with tempfile.TemporaryDirectory(prefix='melonx-array-reference-deltas-') as temporary:
    temporary = Path(temporary).resolve()
    candidate_tree = temporary / 'candidate-tree'
    shutil.copytree(SOURCE, candidate_tree, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
    use_authenticated_libhac_feed(candidate_tree, ROOT)

    def recording_once(path, old, new):
        replacements.append((path.relative_to(candidate_tree).as_posix(), old, new))
        original_once(path, old, new)

    adapt_array_reference_deltas.once = recording_once
    try:
        changed = apply(candidate_tree)
    finally:
        adapt_array_reference_deltas.once = original_once
    check(sorted(p.relative_to(candidate_tree).as_posix() for p in changed) == sorted(BASELINE), 'adapter changed other files')
    duplicate = temporary / 'duplicate'
    for name in BASELINE:
        (duplicate / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(candidate_tree / name, duplicate / name)
    try:
        apply(duplicate)
        refused = False
    except AssertionError:
        refused = True
    check(refused, 'fail closed: an adapted tree is refused')
    for name in BASELINE:
        undone = read(candidate_tree, name)
        for path, old, new in reversed(replacements):
            if path == name:
                check(undone.count(new) == 1, 'each replacement once: ' + new[:60])
                undone = undone.replace(new, old)
        check(undone == read(SOURCE, name), name + ' is the preparation but the adapter\'s replacements')
        check(read(candidate_tree, name).count(TAG) >= 3, 'commented: ' + name)
    if FINAL_PREPARATION:
        later = files_edited_later('adapt_array_reference_deltas')
        for name in BASELINE:
            if name not in later:
                check((candidate_tree / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)
    candidate_text = read(candidate_tree, ARRAY)
    early = member(candidate_text, 'private void AddReferences(CommandBufferScoped cbs, TextureView dummyTexture, SamplerHolder dummySampler)')
    check('(_referencesSequence == _changeSequence || AddNewReferences(cbs)))' in early and
          early.index('!_referencesInvalid && cbs.CommandBufferIndex == _referencesCommandBuffer && submission == _referencesSubmission') <
          early.index('AddNewReferences(cbs)') and early.count('_newViewReferences?.Clear();') == 1,
          'candidate: the delta pass only with valid counts in the command buffer and submission of the last pass')
    result = subprocess.run([DOTNET, 'build', str(candidate_tree / 'src/Ryujinx.Graphics.Vulkan/Ryujinx.Graphics.Vulkan.csproj'), '-c', 'Release',
                             '-nologo', '-m:1', '-p:NuGetAudit=false'], capture_output=True, text=True, timeout=2400,
                            env=dict(environment, DOTNET_TieredCompilation='1'), cwd=candidate_tree)
    if result.returncode:
        print(result.stdout[-6000:], result.stderr[-2000:], flush=True)
    check(result.returncode == 0, 'production Ryujinx.Graphics.Vulkan builds with the adapter')
    built.append('Ryujinx.Graphics.Vulkan')

    check(candidate_text.count(NEW_VIEW_GET) == 1, 'the new views\' reference is replaceable for the sensitivity variant')
    variants = {'control': read(SOURCE, ARRAY), 'candidate': candidate_text,
                'newViewsNotReferenced': candidate_text.replace(NEW_VIEW_GET, NEW_VIEW_GET.replace('view.Get(cbs)', 'view.GetUnsafe()'))}
    compiled = {}
    for variant, text in variants.items():
        work = temporary / variant
        work.mkdir()
        (work / 'TextureArray.cs').write_text(text)
        tree = SOURCE if variant == 'control' else candidate_tree
        shutil.copyfile(tree / RESOURCE, work / 'ResourceArray.cs')
        for relative in FIXTURE:
            shutil.copyfile(ROOT / relative, work / Path(relative).name)
        gal = read(tree, 'src/Ryujinx.Graphics.GAL/ITextureArray.cs')
        start = gal.index('    public static class TextureArrayInventory')
        depth, end = 0, None
        for index in range(gal.index('{', start), len(gal)):
            depth += {'{': 1, '}': -1}.get(gal[index], 0)
            if depth == 0:
                end = index + 1
                break
        (work / 'TextureArrayInventory.cs').write_text('namespace Ryujinx.Graphics.GAL\n{\n' + gal[start:end] + '\n}\n')
        (work / 'Arrays.csproj').write_text(PROJECT)
        (work / 'nuget.config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
        (work / 'global.json').write_text(json.dumps({'sdk': {'version': pin['dotnet'], 'rollForward': 'disable'}}))
        compiled[variant] = {'TextureArray.cs': sha(work / 'TextureArray.cs'), 'ResourceArray.cs': sha(work / 'ResourceArray.cs')}
        for mode in (('on',) if variant == 'newViewsNotReferenced' else ('on', 'off')):
            run = subprocess.run([DOTNET, 'run', '--project', str(work / 'Arrays.csproj'), '-c', 'Release',
                                  *([] if mode == 'on' else ['--no-build']), '--', mode],
                                 cwd=work, capture_output=True, text=True, timeout=900, env=environment)
            if variant == 'newViewsNotReferenced':
                failure = run.stdout + run.stderr
                check(run.returncode != 0 and 'every view and sampler the set references is owned by the command buffer' in failure,
                      'sensitivity: a delta pass that does not reference the new views leaves them unowned: ' + failure[-800:])
                reports[variant] = dict(failedAsExpected=True, message=failure[failure.find('InvalidOperationException'):][:200])
                continue
            if run.returncode:
                print(run.stdout[-6000:], run.stderr[-3000:], flush=True)
            check(run.returncode == 0, f'{variant} {mode}: fixture ran')
            reports[f'{variant}-{mode}'] = json.loads(next(line for line in run.stdout.splitlines() if line.startswith('{')))
            print(variant, mode, json.dumps(reports[f'{variant}-{mode}']), flush=True)

c, k = reports['control-on'], reports['candidate-on']
same = ('violations', 'trace', 'descriptors', 'writeCalls', 'templateCommits', 'setsAllocated', 'binds', 'freshViews',
        'freshSamplers', 'passingReferenced', 'barriers', 'textureDirty')
for key in same:
    check(c[key] == k[key], f'policy on: {key} identical ({c[key]} / {k[key]})')
check(c['violations'] == 0 and c['passingReferenced'] is False and c['binds'] >= 1500 and c['checks'] == k['checks'],
      'no violation; a view that left before the bind is not referenced; every bind checked')
for key in ('ArrayWholeWrites', 'ArrayRangeWrites', 'ArrayRangeElements', 'ArrayCurrentBinds', 'ArraySlotsAdded', 'ArrayFallbacks', 'ArrayReferencePasses'):
    check(c['detail'][key] == k['detail'][key], f'policy on: {key} identical')
check(k['detail']['ArrayReferencesAdded'] * 5 < c['detail']['ArrayReferencesAdded'] and k['gets'] * 5 < c['gets'],
      'the candidate adds far fewer references and makes far fewer Gets: ' + str((c['detail'], k['detail'], c['gets'], k['gets'])))
off_c, off_k = reports['control-off'], reports['candidate-off']
check({x: y for x, y in off_c.items() if x != 'checks'} == {x: y for x, y in off_k.items() if x != 'checks'},
      'policy off: the candidate is the delivered array')

inputs = ['build-utils/melonx/adapt_array_reference_deltas.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_array_reference_deltas_test.py', 'test/melonx_adapter_control.py', *FIXTURE]
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core713Preparation',
               postimages={p: sha(FINAL_SOURCE / p) for p in BASELINE} if FINAL_PREPARATION else {},
               comparison=dict(sameDescriptorsWritten=True, trace=c['trace'], binds=c['binds'], violations=0,
                               referencePasses=c['detail']['ArrayReferencePasses'],
                               referencesAddedControl=c['detail']['ArrayReferencesAdded'],
                               referencesAddedCandidate=k['detail']['ArrayReferencesAdded'],
                               getsControl=c['gets'], getsCandidate=k['gets'], policyOffIdentical=True,
                               sensitivityVariantFailed=True),
               reports=reports, compiledSources=compiled, sdk=sdk, physicalDeviceTested=False, productionAssembliesBuilt=built,
               productionTextureArrayExecuted=True, vulkanBoundariesDoubled=True, sourceBaseline=BASELINE,
               inputs={p: sha(ROOT / p) for p in inputs},
               limitation='The whole production TextureArray with doubled Vulkan, ownership and descriptor set cache; MoltenVK, '
                          'the render thread time saved and the passes per command buffer of Hogwarts Legacy are known only from '
                          'a device run (the pass detail line counts reference passes and references added).')
out = ROOT / 'dist/melonx/array-reference-deltas-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk, comparison=receipt['comparison'])))
