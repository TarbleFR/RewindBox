#!/usr/bin/env python3
"""A stage's resource layout declares each used binding with the type it is used as (adapt_layout_used_types), before and after.

Usage: melonx_layout_used_types_test.py <Core 701 prepared MeloNX tree> [--spirv-cross <SPIRV-Cross 6c09849f checkout,
           built> --moltenvk <MoltenVK v1.4.2 db660224 checkout>]
       melonx_layout_used_types_test.py <control> --candidate-source <final preparation containing the adapter> [...]

Control is the preparation without the adapter, candidate adds it. Static checks bind the mechanism in the preparation:
GpuAccessorBase gives textures and buffer textures (images and buffer images) one static counter, a buffer one a block
further, limit two blocks; ShaderInfoBuilder declares each stage's set as fixed blocks (TextureAndSampler then
BufferTexture, Image then BufferImage) and the usages with the type each resource is used as; the Vulkan backend
creates the descriptor set layouts from the declared descriptors and writes the bindings from the usages. Candidate:
only the adapter's replacements, fail closed, the production Ryujinx.Graphics.Gpu assembly builds with it. Executed: for
each variant a fixture compiles the tree's own ShaderInfoBuilder.cs (and GpuAccessorBase.GetStageIndex) with the
Vulkan backend's capabilities and runs BuildForCache, as a program created or loaded from the host cache, on synthetic
programs whose bindings this test derives with the counter rule (test/melonx_layout_used_types): 36 fragment textures
with buffer textures between them (the shape of Hogwarts Legacy program 890A188FB55B5D5D), a stage at its limit, 17
images, a vertex stage over its limit, a binding used with both types, a small program. Control declares texel
buffers at the overflowing combined-sampler bindings; candidate declares every used single binding with its used type
and changes nothing else (bindings, counts, stages, arrays, other programs). With --spirv-cross and --moltenvk, the
fragment conversion of MoltenVK v1.4.2 runs with SPIRV-Cross 6c09849f (test/melonx_layout_used_types/MslConversion.cpp)
on synthetic SPIR-V (no game data): 36 textures fail with "nullptr" under the control layout and convert under the
candidate's; 32 convert identically; 33 with a 3D texture convert under both, the control one with the sampler in the
next binding's slot. No device, no Metal compilation.
Writes dist/melonx/layout-used-types-checks.json.
"""
from pathlib import Path
import hashlib, json, os, re, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]


def option(name):
    return Path(sys.argv[sys.argv.index(name) + 1]).resolve() if name in sys.argv else None


SOURCE = (option('--candidate-source') or Path(sys.argv[1])).resolve()
SPIRV_CROSS, MOLTENVK = option('--spirv-cross'), option('--moltenvk')
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, files_edited_later, use_authenticated_libhac_feed  # noqa: E402
_HOLD = []
FINAL_SOURCE = SOURCE
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_layout_used_types', _HOLD)
import adapt_layout_used_types  # noqa: E402
from adapt_layout_used_types import apply, BASELINE, BUILDER  # noqa: E402

ACCESSOR = 'src/Ryujinx.Graphics.Gpu/Shader/GpuAccessorBase.cs'
FACTORY = 'src/Ryujinx.Graphics.Vulkan/PipelineLayoutFactory.cs'
COLLECTION = 'src/Ryujinx.Graphics.Vulkan/ShaderCollection.cs'
FIXTURE = ROOT / 'test/melonx_layout_used_types'
DOTNET = os.environ.get('DOTNET', 'dotnet')
TAG = 'RewindBox (adapt_layout_used_types)'
SPIRV_CROSS_REVISION = '6c09849fe88c48eaed08413aa022aaa136a3a057'
MOLTENVK_REVISION = 'db66022459ffb663aa2b50f6b018bc2e124f5edf'
TEXTURES, IMAGES = 32, 16  # VulkanRenderer.GetCapabilities: Constants.MaxTexturesPerStage, MaxImagesPerStage
# Vulkan descriptor types of the fixture's output (EnumConversion.Convert).
SAMPLER, COMBINED, SAMPLED, STORAGE_IMAGE, TEXEL, STORAGE_TEXEL, UBO, SSBO = range(8)
STAGE_FLAG = {'Vertex': 1, 'Fragment': 16}
STAGE_INDEX = {'Vertex': 0, 'Fragment': 1}  # GpuAccessorBase.GetStageIndex
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


def stage(kind, resources, cbuffers=1):
    """A stage whose single textures and images get their bindings as GpuAccessorBase.CreateTextureBinding and
    CreateImageBinding give them: one counter per kind, + the per-stage count for a buffer one, stage block base."""
    counters = {'texture': 0, 'image': 0}
    textures, images = [], []
    for resource in resources:
        if resource[0] == 'array':  # [array, set, binding, dim, length, separate]: its own descriptor, outside the blocks
            textures.append(list(resource[1:]))
            continue
        family, dim = resource
        per_stage = TEXTURES if family == 'texture' else IMAGES
        index = counters[family]
        counters[family] += 1
        if dim == 5:
            index += per_stage
        check(index < 2 * per_stage, 'synthetic program within the counter limit')
        binding = STAGE_INDEX[kind] * 2 * per_stage + index
        (textures if family == 'texture' else images).append([2 if family == 'texture' else 3, binding, dim, 1, 0])
    return dict(stage=kind, cbuffers=[[0, 1 + STAGE_INDEX[kind] * 18 + i] for i in range(cbuffers)], sbuffers=[],
                textures=textures, images=images)


def tex(count, dim=1):
    return [('texture', dim)] * count


# Hogwarts Legacy 890A188FB55B5D5D's fragment shape: 36 static textures, buffer textures at counter values 22, 24 and 25,
# the 33rd-36th combined textures a cube, two 2D and a 3D one (bindings 96-99), and a separately sampled texture array.
HOGWARTS = tex(22) + [('texture', 5), ('texture', 1), ('texture', 5), ('texture', 5)] + tex(6) + \
    [('texture', 3), ('texture', 1), ('texture', 1), ('texture', 2)] + [('array', 4, 0, 1, 8, 1)]
PROGRAMS = [
    dict(name='hogwarts-shape', stages=[stage('Vertex', tex(3)), stage('Fragment', HOGWARTS, cbuffers=2)]),
    dict(name='at-limit', stages=[stage('Vertex', tex(2)),
                                  stage('Fragment', tex(5) + [('texture', 5)] + tex(3) + [('texture', 5)] + tex(22))]),
    dict(name='images-overflow', stages=[stage('Vertex', []),
                                         stage('Fragment', tex(4) + [('image', 1)] * 3 + [('image', 5)] + [('image', 1)] * 14)]),
    dict(name='vertex-overflow', stages=[stage('Vertex', tex(34)), stage('Fragment', tex(2))]),
    dict(name='both-types', stages=[stage('Vertex', []), stage('Fragment', [('texture', 5)] + tex(32))]),
    dict(name='small', stages=[stage('Vertex', tex(2)), stage('Fragment', tex(4) + [('texture', 5)])]),
    # The SPIR-V of the conversion step: combined samplers at fragment bindings 64.. (counter values 0..).
    dict(name='msl-36', stages=[stage('Vertex', [], 0), stage('Fragment', tex(32) + tex(1, 3) + tex(2) + tex(1, 2), 0)]),
    dict(name='msl-32', stages=[stage('Vertex', [], 0), stage('Fragment', tex(32), 0)]),
    dict(name='msl-33-3d', stages=[stage('Vertex', [], 0), stage('Fragment', tex(32) + tex(1, 2), 0)]),
]
MSL = {'msl-36': ['2D'] * 32 + ['Cube', '2D', '2D', '3D'], 'msl-32': ['2D'] * 32, 'msl-33-3d': ['2D'] * 32 + ['3D']}


def used_type(family, dim, separate):
    if family == 'images':
        return STORAGE_TEXEL if dim == 5 else STORAGE_IMAGE
    return TEXEL if dim == 5 else SAMPLER if dim == -1 else SAMPLED if separate else COMBINED


def expected_changes(program):
    """(set, binding, stages) -> used type, for each single binding a stage uses with one type that its block declares
    as the other block type; a binding used with both types is left."""
    changes = {}
    for entry in program['stages']:
        flag = STAGE_FLAG[entry['stage']]
        for family, per_stage, single, buffer in (('textures', TEXTURES, COMBINED, TEXEL), ('images', IMAGES, STORAGE_IMAGE, STORAGE_TEXEL)):
            used = {}
            for set_, binding, dim, length, separate in entry[family]:
                if length > 1:
                    continue
                used.setdefault((set_, binding), set()).add(used_type(family, dim, separate))
            base = STAGE_INDEX[entry['stage']] * 2 * per_stage
            for (set_, binding), types in used.items():
                block = single if binding - base < per_stage else buffer
                if len(types) == 1 and types != {block}:
                    changes[(set_, binding, flag)] = types.pop()
    return changes


def layouts(directory):
    result = {}
    for program in PROGRAMS:
        lines = (directory / (program['name'] + '.l')).read_text().split('\n')
        result[program['name']] = [tuple(int(x) for x in line.split()) for line in lines if line]
    return result


for name, expected in BASELINE.items():
    check(hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected, 'not the pinned preparation: ' + name)

# The mechanism, in the preparation.
accessor = read(SOURCE, ACCESSOR)
for kind, family in (('Texture', 'Textures'), ('Image', 'Images')):
    create = member(accessor, f'public SetBindingPair Create{kind}Binding(int count, bool isBuffer)')
    check(f'int index = _static{family}Count++;' in create and
          f'index += (int)_context.Capabilities.Maximum{family}PerStage;' in create and
          f'binding = GetBindingFromIndex(index, _context.Capabilities.Maximum{family}PerStage * 2, "{kind}");' in create,
          f'{kind.lower()}s and buffer {kind.lower()}s share one counter, a buffer one a block further, limit two blocks')
check('return GetStageIndex(_stageIndex) * (int)maxPerStage + index;' in member(accessor, 'private int GetBindingFromIndex('),
      'binding: stage block base + index')
builder = read(SOURCE, BUILDER)
stage_info = member(builder, 'public void AddStageInfo(ShaderProgramInfo info, bool vertexAsCompute = false)')
check('int textureBinding = _reservedTextures + stageIndex * texturesPerStage * 2;' in stage_info and
      'AddDualDescriptor(stages, ResourceType.TextureAndSampler, ResourceType.BufferTexture, textureSetIndex, textureBinding, texturesPerStage);' in stage_info and
      'AddDualDescriptor(stages, ResourceType.Image, ResourceType.BufferImage, imageSetIndex, imageBinding, imagesPerStage);' in stage_info and
      'AddUsage(info.Textures, stages, isImage: false);' in stage_info, 'ShaderInfoBuilder: fixed blocks per stage, usages per resource')
check('ResourceType type = GetTextureResourceType(texture, isImage);' in member(builder, 'private void AddUsage(IEnumerable<TextureDescriptor> textures'),
      'usages carry the type each texture is used as')
factory = read(SOURCE, FACTORY)
check('DescriptorType = descriptor.Type.Convert(),' in factory and 'rdc.Descriptors[descIndex]' in factory,
      'Vulkan: the descriptor set layouts are the declared descriptors')
collection = read(SOURCE, COLLECTION)
check('BindingSegments = BuildBindingSegments(resourceLayout.SetUsages, out bool usesBufferTextures);' in collection,
      'Vulkan: the bindings written are the usages')

replacements, built = [], []
original_once = adapt_layout_used_types.once
results, conversions = {}, {}
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
with tempfile.TemporaryDirectory(prefix='melonx-layout-used-types-') as temporary:
    temporary = Path(temporary).resolve()
    programs_json = temporary / 'programs.json'
    programs_json.write_text(json.dumps(PROGRAMS))
    for variant in ('control', 'candidate'):
        work = temporary / variant
        shutil.copytree(SOURCE, work, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
        use_authenticated_libhac_feed(work, ROOT)
        if variant == 'candidate':
            def recording_once(path, old, new):
                replacements.append((path.relative_to(work).as_posix(), old, new))
                original_once(path, old, new)

            adapt_layout_used_types.once = recording_once
            try:
                changed = apply(work)
            finally:
                adapt_layout_used_types.once = original_once
            check(sorted(p.relative_to(work).as_posix() for p in changed) == sorted(BASELINE), 'adapter changed other files')
            duplicate = temporary / 'duplicate'
            for name in BASELINE:
                (duplicate / name).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(work / name, duplicate / name)
            try:
                apply(duplicate)
                refused = False
            except AssertionError:
                refused = True
            check(refused, 'fail closed: an adapted tree is refused')
            for name in BASELINE:
                undone = read(work, name)
                for path, old, new in reversed(replacements):
                    if path == name:
                        check(undone.count(new) == 1, 'each replacement once: ' + new[:60])
                        undone = undone.replace(new, old)
                check(undone == read(SOURCE, name), name + ' is the preparation but the adapter\'s replacements')
                check(read(work, name).count(TAG) >= 2, 'commented: ' + name)
            if FINAL_PREPARATION:
                later = files_edited_later('adapt_layout_used_types')
                for name in BASELINE:
                    if name not in later:
                        check((work / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)
            new_builder = read(work, BUILDER)
            new_stage_info = member(new_builder, 'public void AddStageInfo(ShaderProgramInfo info, bool vertexAsCompute = false)')
            check(new_stage_info.index('AddDualDescriptor(stages, ResourceType.Image, ResourceType.BufferImage') <
                  new_stage_info.index('DeclareUsedTypes(info.Textures, stages, isImage: false);') <
                  new_stage_info.index('DeclareUsedTypes(info.Images, stages, isImage: true);') <
                  new_stage_info.index('AddArrayDescriptors(info.Textures, stages, isImage: false);'),
                  'candidate: used types declared after the blocks, before the arrays')
            declare = member(new_builder, 'private void DeclareUsedTypes(IEnumerable<TextureDescriptor> textures, ResourceStages stages, bool isImage)')
            check('descriptors.Add(' not in declare and 'Remove' not in declare and 'Usage' not in declare and
                  'new ResourceDescriptor(descriptor.Binding, 1, binding.Value, stages)' in declare,
                  'candidate: only the type of existing single descriptors changes')
            texts = {p.relative_to(work).as_posix(): p.read_text(errors='ignore') for p in (work / 'src').rglob('*.cs')}
            check(sorted(name for name, text in texts.items() if 'DeclareUsedTypes(' in text) == [BUILDER], 'DeclareUsedTypes in ShaderInfoBuilder only')
            result = subprocess.run([DOTNET, 'build', str(work / 'src/Ryujinx.Graphics.Gpu/Ryujinx.Graphics.Gpu.csproj'), '-c', 'Release',
                                     '-nologo', '-m:1', '-p:NuGetAudit=false'], capture_output=True, text=True, timeout=2400,
                                    env=environment, cwd=work)
            if result.returncode:
                print(result.stdout[-6000:], result.stderr[-2000:], flush=True)
            check(result.returncode == 0, 'production Ryujinx.Graphics.Gpu builds with the adapter')
            built.append('Ryujinx.Graphics.Gpu')

        fixture = temporary / ('fixture-' + variant)
        fixture.mkdir()
        shutil.copyfile(work / BUILDER, fixture / 'ShaderInfoBuilder.cs')
        shutil.copyfile(FIXTURE / 'Program.cs', fixture / 'Program.cs')
        stage_index = member(read(work, ACCESSOR), 'public static int GetStageIndex(int stageIndex)')
        stubs = (FIXTURE / 'Stubs.cs').read_text()
        check(stubs.count('    static partial class GpuAccessorBase\n    {\n    }\n') == 1, 'stubs: the accessor slot')
        (fixture / 'Stubs.cs').write_text(stubs.replace('    static partial class GpuAccessorBase\n    {\n    }\n',
                                                         '    static partial class GpuAccessorBase\n    {\n' + stage_index + '\n    }\n'))
        (fixture / 'Fixture.csproj').write_text(
            '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
            '<Nullable>disable</Nullable><NuGetAudit>false</NuGetAudit><NoWarn>CS0649;CS0414;CS0169</NoWarn></PropertyGroup><ItemGroup>'
            f'<ProjectReference Include="{work / "src/Ryujinx.Graphics.GAL/Ryujinx.Graphics.GAL.csproj"}" />'
            f'<ProjectReference Include="{work / "src/Ryujinx.Graphics.Shader/Ryujinx.Graphics.Shader.csproj"}" />'
            '</ItemGroup></Project>\n')
        out = temporary / ('layouts-' + variant)
        for command in ([DOTNET, 'build', str(fixture / 'Fixture.csproj'), '-c', 'Release', '-nologo', '-m:1', '-p:NuGetAudit=false'],
                        [DOTNET, str(fixture / 'bin/Release/net10.0/Fixture.dll'), str(programs_json), str(out)]):
            result = subprocess.run(command, capture_output=True, text=True, timeout=900, env=environment, cwd=fixture)
            if result.returncode:
                print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
            check(result.returncode == 0, variant + ': ' + ' '.join(command[1:3]))
        check(json.loads(result.stdout.strip().splitlines()[-1]) == {'programs': len(PROGRAMS)}, variant + ': every program built')
        results[variant] = layouts(out)
        if variant == 'candidate':
            shutil.copytree(out, temporary / 'kept-candidate')
        else:
            shutil.copytree(out, temporary / 'kept-control')

    control, candidate = results['control'], results['candidate']
    summary = {}
    for program in PROGRAMS:
        name = program['name']
        c, k = control[name], candidate[name]
        check([row[:2] + row[3:] for row in c] == [row[:2] + row[3:] for row in k],
              name + ': same descriptors (sets, bindings, counts, stages) in both variants')
        expected = expected_changes(program)
        differing = {(row[0], row[1], row[4]): krow[2] for row, krow in zip(c, k) if row[2] != krow[2]}
        check(differing == expected, name + ': candidate changes exactly the used bindings outside their block type: ' +
              str((sorted(differing.items()), sorted(expected.items()))))
        for entry in program['stages']:
            flag = STAGE_FLAG[entry['stage']]
            declared = {(row[0], row[1], row[4]): row[2] for row in k if row[3] == 1}
            for family in ('textures', 'images'):
                for set_, binding, dim, length, separate in entry[family]:
                    if length > 1:
                        continue
                    types = {used_type(family, d, s) for st, b, d, n, s in entry[family] if (st, b) == (set_, binding) and n == 1}
                    if len(types) == 1:
                        check(declared[(set_, binding, flag)] == types.pop(), f'{name}: candidate declares {set_}/{binding} as used')
        summary[name] = dict(changed=len(expected), descriptors=len(k))
    check(summary['hogwarts-shape']['changed'] == 4 and summary['images-overflow']['changed'] == 2 and
          summary['vertex-overflow']['changed'] == 2 and summary['msl-36']['changed'] == 4 and summary['msl-33-3d']['changed'] == 1 and
          all(summary[n]['changed'] == 0 for n in ('at-limit', 'both-types', 'small', 'msl-32')), 'changed bindings: ' + str(summary))
    hogwarts = {(row[0], row[1], row[4]): row[2] for row in control['hogwarts-shape']}
    check(all(hogwarts[(2, b, 16)] == TEXEL for b in range(96, 100)) and
          all(dict(((r[0], r[1], r[4]), r[2]) for r in candidate['hogwarts-shape'])[(2, b, 16)] == COMBINED for b in range(96, 100)),
          'control declares texel buffers at the combined samplers 96-99, candidate combined samplers')
    check(any(row[0] == 4 and row[3] == 8 for row in candidate['hogwarts-shape']) and
          [r for r in control['hogwarts-shape'] if r[0] == 4] == [r for r in candidate['hogwarts-shape'] if r[0] == 4],
          'the texture array keeps its own descriptor')

    if SPIRV_CROSS and MOLTENVK:
        for path, revision in ((SPIRV_CROSS, SPIRV_CROSS_REVISION), (MOLTENVK, MOLTENVK_REVISION)):
            head = subprocess.run(['git', '-C', str(path), 'rev-parse', 'HEAD'], capture_output=True, text=True, check=True).stdout.strip()
            dirty = subprocess.run(['git', '-C', str(path), 'status', '--porcelain', '--untracked-files=no'],
                                   capture_output=True, text=True, check=True).stdout.strip()
            check(head == revision and not dirty, f'{path.name} is the pinned unmodified revision {revision}')
        check((MOLTENVK / 'ExternalRevisions/SPIRV-Cross_repo_revision').read_text().strip() == SPIRV_CROSS_REVISION,
              'the SPIRV-Cross revision MoltenVK v1.4.2 pins')
        converter = temporary / 'MslConversion'
        libraries = [str(SPIRV_CROSS / 'build' / f'libspirv-cross-{part}.a') for part in ('msl', 'reflect', 'glsl', 'core')]
        result = subprocess.run(['g++', '-O1', '-std=c++17', '-I' + str(SPIRV_CROSS), '-I' + str(SPIRV_CROSS / 'include/spirv/unified1'),
                                 '-I' + str(MOLTENVK / 'MoltenVKShaderConverter/MoltenVKShaderConverter'),
                                 str(FIXTURE / 'MslConversion.cpp'), *libraries, '-o', str(converter)], capture_output=True, text=True)
        if result.returncode:
            print(result.stderr[-4000:])
        check(result.returncode == 0, 'conversion driver builds')
        sys.path.insert(0, str(FIXTURE))
        sys.dont_write_bytecode = True  # nothing written into the fixture directory
        import synthetic_spirv  # noqa: E402
        for name, dims in MSL.items():
            vertex, fragment = temporary / (name + '.vert.spv'), temporary / (name + '.frag.spv')
            vertex.write_bytes(synthetic_spirv.vertex())
            fragment.write_bytes(synthetic_spirv.fragment(len(dims), 64, dims))
            for variant in ('control', 'candidate'):
                layout = temporary / ('kept-' + variant) / (name + '.l')
                metal = temporary / f'{name}-{variant}.metal'
                run = subprocess.run([str(converter), str(vertex), str(fragment), str(layout), '1', '0', '30200', str(metal)],
                                     capture_output=True, text=True, timeout=120)
                line = run.stdout.strip().splitlines()[-1] if run.stdout.strip() else run.stderr.strip()
                conversions.setdefault(name, {})[variant] = dict(returncode=run.returncode, result=line.split(' ')[0],
                                                                 message=line, msl=metal.read_text() if metal.exists() else None)
        m36, m32, m33 = conversions['msl-36'], conversions['msl-32'], conversions['msl-33-3d']
        check(m36['control']['returncode'] == 1 and m36['control']['message'] == 'FAIL nullptr',
              'reproducer: 36 textures fail with "nullptr" under the control layout: ' + m36['control']['message'])
        check(m36['candidate']['returncode'] == 0 and m36['candidate']['result'] == 'OK', 'reproducer: 36 textures convert under the candidate layout')
        msl36 = m36['candidate']['msl']
        for kind, count in (('texturecube<float>', 1), ('texture3d<float>', 1), ('texture2d<float>', 34)):
            members = re.findall(r'^\s*' + re.escape(kind) + r' (m_\d+) \[\[id\((\d+)\)\]\];$', msl36, flags=re.M)
            check(len(members) == count and all(f'sampler {n}Smplr [[id({int(i) + 1})]];' in msl36 for n, i in members),
                  f'candidate: {count} {kind} with their samplers in the fragment argument buffer')
        check(m32['control']['returncode'] == m32['candidate']['returncode'] == 0 and m32['control']['msl'] == m32['candidate']['msl'],
              '32 textures (within the block): same layout, same MSL')
        check(m33['control']['returncode'] == m33['candidate']['returncode'] == 0, '33 textures with a 3D one convert under both')

        def host_slot(rows, binding):
            """MoltenVK's argument buffer index of a set-2 binding: one per texture or buffer, two per combined sampler."""
            slot = 0
            for set_, b, kind, count, _ in sorted(rows, key=lambda r: (r[1], r[4])):
                if set_ != 2:
                    continue
                if b == binding:
                    return slot
                slot += count * (2 if kind == COMBINED else 1)
            raise AssertionError(binding)

        texture3d = re.search(r'texture3d<float> (m_\d+) \[\[id\((\d+)\)\]\];', m33['control']['msl'])
        check(texture3d is not None, 'control MSL: the 3D texture')
        slot, sampler = int(texture3d.group(2)), f'sampler {texture3d.group(1)}Smplr [[id({int(texture3d.group(2)) + 1})]];'
        kept_control, kept_candidate = layouts(temporary / 'kept-control')['msl-33-3d'], layouts(temporary / 'kept-candidate')['msl-33-3d']
        check(sampler in m33['control']['msl'] and host_slot(kept_control, 96) == slot and host_slot(kept_control, 97) == slot + 1,
              'control: the 3D texture\'s sampler is at the slot the host layout gives binding 97 (aliasing)')
        check(sampler in m33['candidate']['msl'] and host_slot(kept_candidate, 96) == slot and host_slot(kept_candidate, 97) == slot + 2,
              'candidate: the sampler has its own slot')
        for name in conversions:
            for variant in conversions[name]:
                text = conversions[name][variant].pop('msl')
                conversions[name][variant]['mslSha256'] = hashlib.sha256(text.encode()).hexdigest() if text else None

inputs = ['build-utils/melonx/adapt_layout_used_types.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_layout_used_types_test.py', 'test/melonx_adapter_control.py',
          'test/melonx_layout_used_types/Program.cs', 'test/melonx_layout_used_types/Stubs.cs',
          'test/melonx_layout_used_types/MslConversion.cpp', 'test/melonx_layout_used_types/synthetic_spirv.py']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core701Preparation',
               postimages={p: hashlib.sha256((FINAL_SOURCE / p).read_bytes()).hexdigest() for p in BASELINE} if FINAL_PREPARATION else {},
               comparison=dict(changedBindings={n: v['changed'] for n, v in summary.items()},
                               hogwartsShapeControlTypes96to99=[hogwarts[(2, b, 16)] for b in range(96, 100)],
                               mslConversion={n: {v: r['message'] for v, r in d.items()} for n, d in conversions.items()} or None),
               conversions=conversions or None, mslConversionExecuted=bool(conversions),
               spirvCrossRevision=SPIRV_CROSS_REVISION if conversions else None, moltenVkRevision=MOLTENVK_REVISION if conversions else None,
               sdk=sdk, physicalDeviceTested=False, metalCompiled=False, productionAssembliesBuilt=built,
               productionShaderInfoBuilderExecuted=True, gameDataUsed=False, sourceBaseline=BASELINE,
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               limitation='Synthetic programs and SPIR-V; the conversion is MoltenVK v1.4.2\'s configuration replayed with its '
                          'SPIRV-Cross revision, not MoltenVK itself, and no Metal compilation or draw runs. Whether program '
                          '890A188FB55B5D5D\'s pipeline is created, its draws executed and the image correct is known only from a '
                          'device run.')
out = ROOT / 'dist/melonx/layout-used-types-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk, mslConversion=receipt['comparison']['mslConversion'])))
