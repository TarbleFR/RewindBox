#!/usr/bin/env python3
"""Warm-up and draw keys agree on topology and primitive restart (adapt_warmup_key_parity), on the real prepared engine.

Usage: melonx_warmup_key_parity_test.py <Core 658 prepared MeloNX tree>
       melonx_warmup_key_parity_test.py <control> --candidate-source <final preparation containing the adapter>
When the MoltenVK v1.4.2 sources are present (/home/user/work/mvk or $MOLTENVK_SOURCE pointing at its MoltenVK folder),
the MoltenVK mechanism is bound in them too (the gate is then MoltenVK-only and closed elsewhere).

Control is the Core 658 preparation, candidate adds the adapter. Static checks: each file is the preparation once the
adapter's replacements are undone; the host program's ShaderInfo is the only consumer of the new state (specialization
state, `pipeline` and the disk cache untouched, geometry-as-compute programs never saved); RunFragment's calls; every
Vulkan key write of topology and restart goes through the normalisation. For each variant the production GPU and Vulkan
assemblies are built, then built again as executables with a fixture:
- GPU (test/melonx_warmup_key_parity/gpu): ShaderCache.HostPipelineState and VtgAsComputeState.GetGeometryOutputTopology
  for guest topologies, restart values and 1-3 output vertices per primitive;
- Vulkan (test/melonx_warmup_key_parity/vulkan): warm-up keys from PipelineConverter, draw keys from the real
  PipelineBase setters, the created restart from PipelineState.CreateGraphicsPipeline's own lines (extracted here), on
  five capability sets (MoltenVK with and without its private API, Vulkan with and without list/patch list restart).
Required: the four logged misses reproduced in the control (text equal to the log's), hits in the candidate; created
pipelines identical except strips with restart off on MoltenVK without the private API; every other key field identical.
No device. Writes dist/melonx/warmup-key-parity-checks.json.
"""
from pathlib import Path
import hashlib, json, os, re, shutil, subprocess, sys, tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, files_edited_later, use_authenticated_libhac_feed  # noqa: E402
_HOLD = []
FINAL_SOURCE = SOURCE
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_warmup_key_parity', _HOLD)
import adapt_warmup_key_parity  # noqa: E402
from adapt_warmup_key_parity import apply, BASELINE  # noqa: E402

CACHE = 'src/Ryujinx.Graphics.Gpu/Shader/ShaderCache.cs'
VTG = 'src/Ryujinx.Graphics.Gpu/Engine/Threed/ComputeDraw/VtgAsComputeState.cs'
BASE = 'src/Ryujinx.Graphics.Vulkan/PipelineBase.cs'
CONVERTER = 'src/Ryujinx.Graphics.Vulkan/PipelineConverter.cs'
STATE = 'src/Ryujinx.Graphics.Vulkan/PipelineState.cs'
PROJECTS = {'gpu': 'src/Ryujinx.Graphics.Gpu/Ryujinx.Graphics.Gpu.csproj',
            'vulkan': 'src/Ryujinx.Graphics.Vulkan/Ryujinx.Graphics.Vulkan.csproj'}
DOTNET = os.environ.get('DOTNET', 'dotnet')
MOLTENVK = Path(os.environ.get('MOLTENVK_SOURCE', '/home/user/work/mvk/MoltenVK'))
STRIPS = ('LineStrip', 'TriangleStrip')
# The logged warning texts (the Hogwarts session core log; counts only in the adapter docstring).
LOGGED_TOPOLOGY = ' Differs from warm-up: Topology warm-up=TriangleList draw=TriangleStrip; PrimitiveRestartEnable warm-up=False draw=True'
LOGGED_RESTART = ' Differs from warm-up: PrimitiveRestartEnable warm-up=False draw=True'
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


def run(command, cwd, environment):
    result = subprocess.run(command, capture_output=True, text=True, timeout=2400, env=environment, cwd=cwd)
    if result.returncode:
        print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
    result.check_returncode()
    return result.stdout


def creation_snippet(state_text):
    """PipelineState.CreateGraphicsPipeline's restart lines, verbatim."""
    start = state_text.index('                bool primitiveRestartEnable = PrimitiveRestartEnable;')
    end = state_text.index('primitiveRestartEnable &= topologySupportsRestart;', start) + len('primitiveRestartEnable &= topologySupportsRestart;')
    check(state_text.count('bool primitiveRestartEnable = PrimitiveRestartEnable;') == 1, 'one creation restart block')
    return state_text[start:end]


for name, expected in BASELINE.items():
    check(hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected, 'not the Core 658 preparation: ' + name)

reports, texts = {}, {}
replacements = []
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
with tempfile.TemporaryDirectory(prefix='melonx-warmup-key-parity-') as temporary:
    for variant in ('control', 'candidate'):
        work = Path(temporary).resolve() / variant
        shutil.copytree(SOURCE, work, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
        use_authenticated_libhac_feed(work, ROOT)
        if variant == 'candidate':
            original_once = adapt_warmup_key_parity.once

            def recording_once(path, old, new):
                replacements.append((str(path.relative_to(work)), old, new))
                original_once(path, old, new)

            adapt_warmup_key_parity.once = recording_once
            try:
                changed = apply(work)
            finally:
                adapt_warmup_key_parity.once = original_once
            check(sorted(str(p.relative_to(work)) for p in changed) == sorted(BASELINE), 'adapter changed other files')
            for name in BASELINE:
                undone = (work / name).read_text(encoding='utf-8-sig')
                for path, old, new in reversed([r for r in replacements if r[0] == name]):
                    check(undone.count(new) == 1, 'each replacement once: ' + new[:60])
                    undone = undone.replace(new, old)
                check(undone == (SOURCE / name).read_text(encoding='utf-8-sig'), 'only the adapter\'s replacements: ' + name)
            if FINAL_PREPARATION:
                later = files_edited_later('adapt_warmup_key_parity')
                for name in BASELINE:
                    if name not in later:
                        check((work / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)
        texts[variant] = {name: (work / name).read_text(encoding='utf-8-sig') for name in (*BASELINE, STATE)}
        # The production assemblies as they ship (libraries), then as fixture executables.
        for project in PROJECTS.values():
            run([DOTNET, 'build', str(work / project), '-c', 'Release', '-nologo', '-m:1', '-p:NuGetAudit=false'], work, environment)
            check(True, variant + ' production assembly builds: ' + project)
        (work / 'src/Ryujinx.Graphics.Vulkan/Creation.cs').write_text(
            'using PrimitiveTopology = Silk.NET.Vulkan.PrimitiveTopology;\n'
            'using Ryujinx.Graphics.Vulkan;\n\n'
            '// PipelineState.CreateGraphicsPipeline\'s restart lines, copied verbatim by melonx_warmup_key_parity_test.py.\n'
            'static class Creation\n{\n'
            '    public static bool CreatedRestart(VulkanRenderer gd, PrimitiveTopology Topology, bool PrimitiveRestartEnable)\n    {\n'
            + creation_snippet(texts[variant][STATE]) + '\n\n                return primitiveRestartEnable;\n    }\n}\n')
        cases = Path(temporary).resolve() / (variant + '-vtg-cases.json')
        for fixture in ('gpu', 'vulkan'):
            project = work / PROJECTS[fixture]
            tree = ET.parse(project)
            group = ET.SubElement(tree.getroot(), 'PropertyGroup')
            for key, value in [('OutputType', 'Exe'), ('StartupObject', 'Program'), ('NuGetAudit', 'false'),
                               ('EnableNETAnalyzers', 'false'), ('TreatWarningsAsErrors', 'false')]:
                ET.SubElement(group, key).text = value
            tree.write(project)
            shutil.copyfile(ROOT / 'test/melonx_warmup_key_parity' / fixture / 'Program.cs', project.parent / 'Program.cs')
            run([DOTNET, 'build', str(project), '-c', 'Release', '-nologo', '-m:1', '-p:NuGetAudit=false'], work, environment)
            output = run([DOTNET, str(project.parent / 'bin/Release/net10.0' / (project.stem + '.dll')), variant, str(cases)],
                         work, environment)
            report = json.loads(next(line for line in output.splitlines() if line.startswith('{')))
            if fixture == 'gpu':
                report['vtgCases'] = json.loads(cases.read_text())
            reports[variant + '-' + fixture] = report
            print(json.dumps({k: v for k, v in report.items() if k not in ('matrix', 'pairs', 'logged', 'vtgCases')}), flush=True)

# --- Static: the source the fixtures cannot reach. ---
control, candidate = texts['control'], texts['candidate']
check(control[CACHE].count('infoBuilder.Build(') == 1 and 'ShaderInfo info = infoBuilder.Build(pipeline);' in control[CACHE],
      'control: the host program\'s warm-up is the guest state itself (the GPU fixture\'s control host state)')
graphics = member(candidate[CACHE], 'public CachedShaderProgram GetGraphicsShader(')
check(candidate[CACHE].count('infoBuilder.Build(') == 1 and
      graphics.count('ShaderInfo info = infoBuilder.Build(HostPipelineState(pipeline, geometryAsCompute));') == 1,
      'candidate: only the live host program takes the passthrough state')
check(graphics.index('geometryAsCompute = CreateHostVertexAsComputeProgram(') < graphics.index('infoBuilder.Build(HostPipelineState(') <
      graphics.index('_context.Renderer.CreateProgram(shaderSourcesArray, info);'), 'state built once geometryAsCompute is known')
check('ShaderSpecializationState specState = new(ref graphicsState, ref pipeline, transformFeedbackDescriptors);' in graphics and
      'UpdatePipelineInfo(ref state, ref pipeline, graphicsState, channel);' in graphics,
      'specialization state and StateUpdater\'s pipeline keep the guest values')
check(re.search(r'if \(vertexAsCompute == null\)\s*\{\s*EnqueueProgramToSave\(', graphics) is not None and
      'return hasGeometryShader && ShouldConvertGeometryToCompute(context, geometryHasStore);' in candidate[CACHE],
      'geometry-as-compute programs (vertex converted too) are never written to the disk cache')
fragment = member(candidate[VTG], 'public readonly void RunFragment()')
branch = fragment[fragment.index('if (_geometryAsCompute != null)'):fragment.index('else')]
check(branch.index('SetProgram(_vertexPassthroughProgram);') < branch.index('SetPrimitiveRestart(true, -1);') <
      branch.index('SetPrimitiveTopology(GetGeometryOutputTopology(_geometryAsCompute.Info.GeometryVerticesPerPrimitive));') <
      branch.index('DrawIndexed('), 'RunFragment draws the passthrough with restart on and the output strip topology')
check(member(candidate[VTG], 'static PrimitiveTopology GetGeometryOutputTopology(').split('\n', 1)[1] ==
      member(control[VTG], 'static PrimitiveTopology GetGeometryOutputTopology(').split('\n', 1)[1] and
      fragment == member(control[VTG], 'public readonly void RunFragment()'), 'RunFragment and its topology mapping unchanged')
for variant, text in (('control', control), ('candidate', candidate)):
    writes = re.findall(r'_newState\.(PrimitiveRestartEnable|Topology) = ([^;]+);', text[BASE])
    if variant == 'control':
        check(writes == [('PrimitiveRestartEnable', 'enable'), ('Topology', 'vkTopology')], 'control key writes: ' + str(writes))
    else:
        check(writes == [('PrimitiveRestartEnable', 'PipelineConverter.PipelinePrimitiveRestart(Gd, enable, _newState.Topology)'),
                         ('Topology', 'vkTopology'),
                         ('PrimitiveRestartEnable', 'PipelineConverter.PipelinePrimitiveRestart(Gd, _primitiveRestartRequested, vkTopology)')],
              'candidate: every PipelineBase key write of restart is normalised, after each topology write: ' + str(writes))
    converter_writes = re.findall(r'pipeline\.(PrimitiveRestartEnable|Topology) = ([^;]+);', text[CONVERTER])
    expected = [('PrimitiveRestartEnable', 'state.PrimitiveRestartEnable'), ('Topology', 'gd.TopologyRemap(state.Topology).Convert()')] \
        if variant == 'control' else [('Topology', 'gd.TopologyRemap(state.Topology).Convert()'),
                                      ('PrimitiveRestartEnable', 'PipelinePrimitiveRestart(gd, state.PrimitiveRestartEnable, pipeline.Topology)')]
    check(converter_writes == expected, variant + ' converter writes: ' + str(converter_writes))
helper = member(candidate[CONVERTER], 'internal static bool PipelinePrimitiveRestart(')
creation = creation_snippet(candidate[STATE])
names = lambda text: sorted(set(re.findall(r'PrimitiveTopology\.(\w+)', text)))
check(names(creation[creation.index('else'):]) == names(helper[helper.index(': topology is'):]),
      'the normalisation lists the topologies creation restarts')
check('gd.IsMoltenVk && !gd.Capabilities.SupportsPrimitiveTopologyListRestart &&' in helper and
      names(helper[:helper.index('return true;')]) == sorted(STRIPS), 'MoltenVK constant: line and triangle strips only')
# Nothing else in the Vulkan backend writes a key's topology or restart (HelperShader goes through the setters).
writers = sorted(p.relative_to(SOURCE).as_posix() for p in (SOURCE / 'src/Ryujinx.Graphics.Vulkan').rglob('*.cs')
                 if re.search(r'\.(PrimitiveRestartEnable|Topology) = ', p.read_text(encoding='utf-8-sig')))
check(writers == sorted([BASE, CONVERTER]), 'key topology and restart written only by PipelineBase and PipelineConverter: ' + str(writers))

# --- Behaviour. ---
for variant in ('control', 'candidate'):
    check(reports[variant + '-gpu']['outputTopology'] == {'0': 'Points', '1': 'Points', '2': 'LineStrip', '3': 'TriangleStrip',
                                                           '4': 'Points', '6': 'Points'}, variant + ' RunFragment topology mapping')
for c in reports['control-gpu']['vtgCases']:
    check(c['hostTopology'] == c['guestTopology'] and c['hostRestart'] == c['guestRestart'], 'control host state is the guest\'s')
for c in reports['candidate-gpu']['vtgCases']:
    check(c['hostTopology'] == c['passthroughTopology'] and c['hostRestart'] is True, 'candidate host state is the draw\'s: ' + str(c))

matrix = {variant: {(m['config'], m['topology'], m['restart']): m for m in reports[variant + '-vulkan']['matrix']}
          for variant in ('control', 'candidate')}
check(set(matrix['control']) == set(matrix['candidate']) and len(matrix['control']) == 5 * 14 * 2, 'matrix complete')
changed_created = []
for key, c in matrix['control'].items():
    k = matrix['candidate'][key]
    config = key[0]
    check(c['warmUpEqualsDraw'] and k['warmUpEqualsDraw'], 'warm-up and draw agree for the same request: ' + str(key))
    check(c['setterOrderIndependent'] and k['setterOrderIndependent'], 'setter order does not matter: ' + str(key))
    check(c['otherFields'] == k['otherFields'], 'every other key field unchanged: ' + str(key))
    check(c['keyRestart'] == key[2], 'control keys the request: ' + str(key))
    check(k['keyRestart'] == k['createdRestart'], 'candidate keys what is created: ' + str(key))
    shipped_strip = config == 'moltenVkShipped' and k['vkTopology'] in STRIPS
    if shipped_strip:
        check(k['createdRestart'] is True, 'MoltenVK without private API: strips created with restart on (what Metal does)')
        if c['createdRestart'] != k['createdRestart']:
            changed_created.append(list(key))
    else:
        check(c['createdRestart'] == k['createdRestart'], 'created pipeline unchanged: ' + str(key))
check(sorted(changed_created) == sorted([['moltenVkShipped', t, False] for t in ('LineStrip', 'TriangleStrip', 'QuadStrip')]),
      'the only created change: strips with restart off on MoltenVK without private API: ' + str(changed_created))
pairs = {variant: {(p['config'], p['topology']): p['restartOffEqualsOn'] for p in reports[variant + '-vulkan']['pairs']}
         for variant in ('control', 'candidate')}
merged = []
for key, equal in pairs['candidate'].items():
    check(pairs['control'][key] is False, 'control keys restart off and on apart: ' + str(key))
    off, on = matrix['control'][key + (False,)], matrix['control'][key + (True,)]
    identical = off['createdRestart'] == on['createdRestart'] or (key[0] == 'moltenVkShipped' and off['vkTopology'] in STRIPS)
    check(equal == identical, 'candidate merges exactly the requests that create the same pipeline: ' + str(key))
    merged += [list(key)] if equal else []
logged = {variant: reports[variant + '-vulkan']['logged'] for variant in ('control', 'candidate')}
for variant in ('control', 'candidate'):
    check(len(logged[variant]) == 5 * (7 * 2 * 3 + 4), variant + ' logged cases complete')
shipped = lambda variant, **match: [x for x in logged[variant] if x['config'] == 'moltenVkShipped' and
                                    all(x.get(k) == v for k, v in match.items())]
log1 = shipped('control', guestTopology='Triangles', guestRestart=False, verticesPerPrimitive=3)
log2 = shipped('control', guestTopology='TriangleStrip', guestRestart=False, verticesPerPrimitive=3)
check(len(log1) == 1 and not log1[0]['hit'] and log1[0]['describe'] == LOGGED_TOPOLOGY, 'control reproduces the topology miss: ' + str(log1))
check(len(log2) == 1 and not log2[0]['hit'] and log2[0]['describe'] == LOGGED_RESTART, 'control reproduces the restart-only miss: ' + str(log2))
for x in logged['candidate']:
    if 'restartOnlyDraw' not in x:
        check(x['hit'] and x['describe'] == '', 'candidate: every geometry-as-compute first draw finds its warm-up: ' + str(x))
control_vtg_misses = sum(1 for x in logged['control'] if 'restartOnlyDraw' not in x and not x['hit'])
for x in logged['candidate']:
    if 'restartOnlyDraw' in x:
        c = next(y for y in logged['control'] if y['config'] == x['config'] and y.get('restartOnlyDraw') and y['guestTopology'] == x['guestTopology'])
        check(not c['hit'], 'control: a restart-only first draw misses: ' + str(c))
        merges = x['config'] == 'moltenVkShipped' and x['guestTopology'] in STRIPS or \
            (x['guestTopology'] in ('Triangles',) and x['config'] in ('moltenVkShipped', 'vulkanNoListRestart'))
        check(x['hit'] == merges, 'candidate: a restart-only first draw hits exactly where the pipelines are identical: ' + str(x))

# --- MoltenVK v1.4.2: without MVK_USE_METAL_PRIVATE_API the restart flag is stored, never used. ---
def private_only(text, needle):
    """Every line containing needle is inside an `#if MVK_USE_METAL_PRIVATE_API` branch."""
    stack, found = [], 0
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(('#if', '#ifdef', '#ifndef')):
            stack.append(stripped)
        elif stripped.startswith(('#else', '#elif')):
            stack[-1] = 'else ' + stack[-1]
        elif stripped.startswith('#endif'):
            stack.pop()
        elif needle in line:
            found += 1
            if '#if MVK_USE_METAL_PRIVATE_API' not in stack:
                return False
    return found > 0


moltenvk = None
if (MOLTENVK / 'MoltenVK/GPUObjects/MVKPipeline.mm').is_file():
    mvk = MOLTENVK / 'MoltenVK'
    environment_h = (MOLTENVK.parent / 'Common/MVKCommonEnvironment.h').read_text()
    check(re.search(r'#ifndef MVK_USE_METAL_PRIVATE_API\s*#\s*define MVK_USE_METAL_PRIVATE_API\s+0', environment_h) is not None,
          'MoltenVK: the private API is off unless defined')
    pipeline = (mvk / 'GPUObjects/MVKPipeline.mm').read_text()
    check('bool primitiveRestart = true; // Always enabled in Metal' in pipeline and
          pipeline.count('_staticStateData.enable.set(MVKRenderStateEnableFlag::PrimitiveRestart, primitiveRestart);') == 1 and
          'Metal does not support disabling primitive restart.' in pipeline, 'MoltenVK: the pipeline only stores the flag')
    sources = {p.relative_to(mvk).as_posix(): p.read_text(errors='replace') for p in sorted(mvk.rglob('*')) if p.suffix in ('.mm', '.h', '.m')}
    readers = {path: text for path, text in sources.items() if 'isPrimitiveRestartEnabled()' in text or 'setPrimitiveRestartEnabled' in text
               or 'isPrimRestart =' in text}
    check(sorted(readers) == ['Commands/MVKCmdDraw.mm', 'Commands/MVKCommandEncoderState.h', 'Commands/MVKCommandEncoderState.mm',
                              'GPUObjects/MVKRenderPass.mm'], 'MoltenVK: restart readers: ' + str(sorted(readers)))
    # MVKRenderPass.mm only names the selector in a comment on the OpenGL mode it unlocks, itself private API.
    check(private_only(readers['GPUObjects/MVKRenderPass.mm'], 'setPrimitiveRestartEnabled'), 'MoltenVK: render pass mention private')
    check(private_only(readers['Commands/MVKCmdDraw.mm'], 'isPrimitiveRestartEnabled()') and
          'bool isPrimRestart = true;' in readers['Commands/MVKCmdDraw.mm'] and
          private_only(readers['Commands/MVKCommandEncoderState.mm'], 'setPrimitiveRestartEnabled') and
          private_only(readers['Commands/MVKCommandEncoderState.mm'], 'enable.has(MVKRenderStateEnableFlag::PrimitiveRestart)'),
          'MoltenVK: the flag is read only with the private API compiled in')
    reads = [path for path, text in sources.items() if '.has(MVKRenderStateEnableFlag::PrimitiveRestart)' in text]
    check(sorted(reads) == ['Commands/MVKCommandEncoderState.h', 'Commands/MVKCommandEncoderState.mm'] and
          sources['Commands/MVKCommandEncoderState.h'].count('isPrimitiveRestartEnabled') == 1, 'MoltenVK: no other reader')
    device = (mvk / 'GPUObjects/MVKDevice.mm').read_text()
    check(re.search(r'#if MVK_USE_METAL_PRIVATE_API\s*if \(!getMVKConfig\(\)\.useMetalPrivateAPI\) \{\s*#endif[^#]*'
                    r'vk_EXT_primitive_topology_list_restart\.enabled = false;', device) is not None and
          'listRestartFeatures->primitiveTopologyListRestart = getMVKConfig().useMetalPrivateAPI;' in device,
          'MoltenVK: list restart exposed only while the private API is in use (the runtime gate)')
    moltenvk = {path: hashlib.sha256((mvk / path).read_bytes()).hexdigest() for path in
                ('GPUObjects/MVKPipeline.mm', 'GPUObjects/MVKDevice.mm', 'Commands/MVKCmdDraw.mm',
                 'Commands/MVKCommandEncoderState.mm', 'Commands/MVKCommandEncoderState.h')}
def shipped_patch_keeps_private_api_off(pin):
    """Unmodified, or a pinned patch (lot 9: drawable ownership) that leaves the private API and its switch alone."""
    if pin['patch'] is None:
        return True
    text = (ROOT / pin['patch']).read_text()
    files = re.findall(r'^diff --git a/(\S+)', text, re.M)
    return (hashlib.sha256((ROOT / pin['patch']).read_bytes()).hexdigest() == pin['patchSha256'] and
            'MVK_USE_METAL_PRIVATE_API' not in text and 'useMetalPrivateAPI' not in text and
            files == ['MoltenVK/MoltenVK/GPUObjects/MVKImage.h', 'MoltenVK/MoltenVK/GPUObjects/MVKImage.mm'])


build_script = (ROOT / 'build-utils/melonx/build_moltenvk_rebuild.py').read_text()
pin = json.loads((ROOT / 'build-utils/melonx/moltenvk-rebuild.json').read_text())
check("run(['make', 'ios'], cwd=target)" in build_script and 'MVK_USE_METAL_PRIVATE_API' not in build_script and
      pin['tag'] == 'v1.4.2' and shipped_patch_keeps_private_api_off(pin), 'the shipped MoltenVK is v1.4.2 built without the private API')

inputs = ['build-utils/melonx/adapt_warmup_key_parity.py', 'build-utils/melonx/adapt_session.py', 'test/melonx_adapter_control.py',
          'test/melonx_warmup_key_parity_test.py', 'test/melonx_warmup_key_parity/gpu/Program.cs',
          'test/melonx_warmup_key_parity/vulkan/Program.cs', 'build-utils/melonx/build_moltenvk_rebuild.py',
          'build-utils/melonx/moltenvk-rebuild.json', 'build-utils/melonx/moltenvk/rewindbox-drawable-ownership.patch']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
summary = dict(controlGeometryAsComputeMisses=control_vtg_misses, mergedRestartPairs=merged, createdChanges=changed_created,
               loggedTopologyMiss=LOGGED_TOPOLOGY, loggedRestartMiss=LOGGED_RESTART)
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core658Preparation',
               postimages={p: hashlib.sha256((FINAL_SOURCE / p).read_bytes()).hexdigest() for p in BASELINE} if FINAL_PREPARATION else {},
               summary=summary, gpuReports={v: {k: x for k, x in reports[v + '-gpu'].items() if k != 'vtgCases'} for v in ('control', 'candidate')},
               moltenVkSourceChecked=moltenvk is not None, moltenVkSources=moltenvk or {}, sdk=sdk, physicalDeviceTested=False,
               productionAssembliesBuilt=sorted(PROJECTS.values()), nativeCallsUsed=False, sourceBaseline=BASELINE,
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               limitation='Host fixture of the keys, the created restart value and the warm-up state; the number of '
                          'render-thread pipeline builds and stalls in Hogwarts Legacy is known only from a device run.')
out = ROOT / 'dist/melonx/warmup-key-parity-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk, summary=summary)))
