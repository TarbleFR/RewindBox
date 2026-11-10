#!/usr/bin/env python3
"""Setting the program already set keeps its bound descriptor sets (adapt_same_program_descriptors), before and after.

Usage: melonx_same_program_descriptors_test.py <Core 703 prepared MeloNX tree>
       melonx_same_program_descriptors_test.py <control> --candidate-source <final preparation containing the adapter>

Control is the preparation without the adapter, candidate adds it. Static checks bind the mechanism: ComputeClass sets
the program before every dispatch; the helper shaders restore the main pipeline through SignalCommandBufferChange; the
texture and image arrays signal ForceTextureDirty/ForceImageDirty when their elements change while bound; Auto keeps a
resource referenced by a command buffer until it completes. Candidate: only the adapter's replacements, fail closed;
the production Ryujinx.Graphics.Vulkan assembly builds. Executed: the production DescriptorSetUpdater members (setters,
SetProgram, UpdateAndBindDescriptorSets, the template update and its production writer, extra sets, Rebind, SwapBuffer,
command buffer changes) with Vulkan boundaries that keep the bytes each set was written with and the set bound per
(bind point, set index) in the current command buffer (test/melonx_same_program_descriptors). After every draw or
dispatch the descriptors it reads are decoded and checked against the resources the script bound: compute/graphics
alternation, texture, sampler, format and image changes, a slot reused with another texture, uniform and storage offset
and range changes, an unbound texture, a texture array element change, overlapping and disjoint buffer invalidations,
a buffer replacement, a new command buffer, another program of the same layout, and buffer texture and buffer image
views changed without a setter call. Control and candidate read the same descriptors at every step; the candidate
writes fewer sets. A third variant without the buffer view guard must fail on the silent view change (the fixture
detects a stale descriptor). Counts per step and for 2 000 dispatches of one program. No device, no MoltenVK.
Writes dist/melonx/same-program-descriptors-checks.json.
"""
from pathlib import Path
import hashlib, json, os, re, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, files_edited_later, use_authenticated_libhac_feed  # noqa: E402
_HOLD = []
FINAL_SOURCE = SOURCE
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_same_program_descriptors', _HOLD)
import adapt_same_program_descriptors  # noqa: E402
from adapt_same_program_descriptors import apply, BASELINE, UPDATER, PIPELINE  # noqa: E402
from adapt_descriptor_updates import method  # noqa: E402

FIXTURE = ROOT / 'test/melonx_same_program_descriptors'
DOTNET = os.environ.get('DOTNET', 'dotnet')
TAG = 'RewindBox (adapt_same_program_descriptors)'
FILES = ['src/Ryujinx.Graphics.Vulkan/DescriptorSetTemplateUpdater.cs', 'src/Ryujinx.Graphics.Vulkan/NativeArray.cs',
         'src/Ryujinx.Graphics.Vulkan/BitMapStruct.cs', 'src/Ryujinx.Graphics.Vulkan/ResourceBindingSegment.cs',
         'src/Ryujinx.Graphics.Vulkan/Constants.cs', 'src/Ryujinx.Common/Memory/IArray.cs',
         'src/Ryujinx.Common/Memory/StructArrayHelpers.cs', 'src/Ryujinx.Common/Utilities/BitUtils.cs',
         'src/Ryujinx.Graphics.GAL/BufferAssignment.cs', 'src/Ryujinx.Graphics.GAL/BufferRange.cs',
         'src/Ryujinx.Graphics.GAL/BufferHandle.cs', 'src/Ryujinx.Graphics.GAL/ResourceLayout.cs',
         'src/Ryujinx.Graphics.Shader/ShaderStage.cs']
SIGNATURES = [
    '        private record struct BufferRef', '        private record struct TextureRef', '        private record struct ImageRef',
    '        private enum DirtyFlags', '        private static bool BindingOverlaps(', '        internal void Rebind(',
    '        public void AdvancePdSequence(', '        public void SetProgram(',
    '        public void SetImage(CommandBufferScoped cbs, ShaderStage stage, int binding, ITexture image)',
    '        public void SetStorageBuffers(CommandBuffer commandBuffer, ReadOnlySpan<BufferAssignment> buffers)',
    '        public void SetTextureAndSampler(\n', '        public void SetTextureArraySeparate(',
    '        private static ref ArrayRef<T> GetArrayRef<T>(', '        public void SetUniformBuffers(',
    '        private static Span<T> TemplateScratch<T>(', '        private void SignalDirty(',
    '        public void UpdateAndBindDescriptorSets(', '        private static bool UpdateBuffer(',
    '        private void UpdateAndBind(CommandBufferScoped cbs, ShaderCollection program, int setIndex, PipelineBindPoint pbp)',
    '        private void UpdateAndBindUniformBufferPd(', '        private void Initialize(CommandBufferScoped cbs, int setIndex, DescriptorSetCollection dsc)',
    '        private void BindExtraSets(', '        public void SignalCommandBufferChange(', '        public void ForceTextureDirty(',
    '        public void ForceImageDirty(', '        private static void SwapBuffer(', '        public void SwapBuffer(',
]
GUARD = '                _dirty |= BufferViewSets(program);\n'
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


for name, expected in BASELINE.items():
    check(hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected, 'not the pinned preparation: ' + name)

# The mechanism, in the preparation.
gpu = 'src/Ryujinx.Graphics.Gpu/Engine/'
dispatch = read(SOURCE, gpu + 'Compute/ComputeClass.cs')
check(dispatch.count('_context.Renderer.Pipeline.SetProgram(cs.HostProgram);') == 2 and
      dispatch.index('_context.Renderer.Pipeline.SetProgram(cs.HostProgram);') < dispatch.index('_context.Renderer.Pipeline.DispatchCompute('),
      'ComputeClass sets the program before every dispatch')
check('_context.Renderer.Pipeline.SetProgram(gs.HostProgram);' in read(SOURCE, gpu + 'Threed/StateUpdater.cs'),
      'StateUpdater sets the program on each shader state update')
vulkan = 'src/Ryujinx.Graphics.Vulkan/'
helper = read(SOURCE, vulkan + 'PipelineHelperShader.cs')
full = read(SOURCE, vulkan + 'PipelineFull.cs')
base = read(SOURCE, PIPELINE)
check('SignalCommandBufferChange();' in member(helper, 'public void SetCommandBuffer(CommandBufferScoped cbs)') and
      'gd.PipelineInternal.Restore();' in helper and 'SignalCommandBufferChange();' in member(full, 'public void Restore()'),
      'helper shaders: their own updater, the main pipeline restored through SignalCommandBufferChange')
check('_descriptorSetUpdater.SignalCommandBufferChange();' in member(base, 'protected void SignalCommandBufferChange()') and
      'SignalCommandBufferChange();' in member(base, 'public void SwapBuffer(Auto<DisposableBuffer> from, Auto<DisposableBuffer> to)'),
      'command buffer changes and buffer replacements mark every set dirty')
array = read(SOURCE, vulkan + 'ResourceArray.cs')
check('gd.PipelineInternal.ForceImageDirty();' in array and 'gd.PipelineInternal.ForceTextureDirty();' in array,
      'texture and image arrays mark their set dirty when their elements change while bound')
auto = read(SOURCE, vulkan + 'Auto.cs')
check('if (!_destroyed)' in member(auto, 'public T Get(CommandBufferScoped cbs)') and
      '_value = default;' in member(auto, 'public void DecrementReferenceCount()'),
      'Auto: a value is reset only when the last reference (command buffers included) is released')
textureBuffer = read(SOURCE, vulkan + 'TextureBuffer.cs')
check('ReleaseImpl();' in member(textureBuffer, 'public void SetStorage(BufferRange buffer)') and
      '_bufferView ??= ' in member(textureBuffer, 'public BufferView GetBufferView(CommandBufferScoped cbs, bool write)'),
      'TextureBuffer: its view changes without a setter call (the reason for the buffer view guard)')

replacements, reports = [], {}
original_once = adapt_same_program_descriptors.once
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_TieredCompilation='0')
pin = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())
built = []
with tempfile.TemporaryDirectory(prefix='melonx-same-program-descriptors-') as temporary:
    temporary = Path(temporary).resolve()
    candidate_tree = temporary / 'candidate-tree'
    shutil.copytree(SOURCE, candidate_tree, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
    use_authenticated_libhac_feed(candidate_tree, ROOT)

    def recording_once(path, old, new):
        replacements.append((path.relative_to(candidate_tree).as_posix(), old, new))
        original_once(path, old, new)

    adapt_same_program_descriptors.once = recording_once
    try:
        changed = apply(candidate_tree)
    finally:
        adapt_same_program_descriptors.once = original_once
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
        check(read(candidate_tree, name).count(TAG) >= 2, 'commented: ' + name)
    if FINAL_PREPARATION:
        later = files_edited_later('adapt_same_program_descriptors')
        for name in BASELINE:
            if name not in later:
                check((candidate_tree / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)
    texts = {p.relative_to(candidate_tree).as_posix(): p.read_text(errors='ignore') for p in (candidate_tree / 'src').rglob('*.cs')}
    check(sorted(n for n, t in texts.items() if 'BufferViewSets(' in t) == [UPDATER] and
          sorted(n for n, t in texts.items() if 'SameProgramSets' in t) == sorted([UPDATER, PIPELINE]), 'the change stays in its two files')
    set_program = member(read(candidate_tree, UPDATER), 'public void SetProgram(CommandBufferScoped cbs, ShaderCollection program, bool isBound)')
    check(set_program.index('if (ReferenceEquals(program, _program))') < set_program.index('_dirty = DirtyFlags.All;') and
          GUARD in set_program and '_dirty = ' not in set_program[:set_program.index('_dirty = DirtyFlags.All;')].replace(GUARD, ''),
          'candidate: the program already set never clears a dirty flag; any other program marks all four')
    result = subprocess.run([DOTNET, 'build', str(candidate_tree / 'src/Ryujinx.Graphics.Vulkan/Ryujinx.Graphics.Vulkan.csproj'), '-c', 'Release',
                             '-nologo', '-m:1', '-p:NuGetAudit=false'], capture_output=True, text=True, timeout=2400,
                            env=dict(environment, DOTNET_TieredCompilation='1'), cwd=candidate_tree)
    if result.returncode:
        print(result.stdout[-6000:], result.stderr[-2000:], flush=True)
    check(result.returncode == 0, 'production Ryujinx.Graphics.Vulkan builds with the adapter')
    built.append('Ryujinx.Graphics.Vulkan')

    control_text = read(SOURCE, UPDATER)
    candidate_text = read(candidate_tree, UPDATER)
    variants = {'control': control_text, 'candidate': candidate_text, 'unguarded': candidate_text.replace(GUARD, '')}
    check(variants['unguarded'] != candidate_text, 'the guard is removable for the sensitivity variant')
    member_hashes = {}
    for variant, text in variants.items():
        listed = SIGNATURES + (['        private static DirtyFlags BufferViewSets('] if variant != 'control' else [])
        members = [method(text, signature) for signature in listed]
        member_hashes[variant] = {s.strip(): hashlib.sha256(m.encode()).hexdigest() for s, m in zip(listed, members)}
        work = temporary / variant
        work.mkdir()
        (work / 'Production.cs').write_text('''using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using Ryujinx.Common.Memory;
using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.Shader;
using Silk.NET.Vulkan;
using Buffer = Silk.NET.Vulkan.Buffer;
namespace Ryujinx.Graphics.Vulkan { partial class DescriptorSetUpdater {
''' + '\n\n'.join(members) + '\n} }\n')
        tree = SOURCE if variant == 'control' else candidate_tree
        for relative in FILES:
            shutil.copyfile(tree / relative, work / Path(relative).name)
        for name in ('Program.cs', 'Boundaries.cs'):
            shutil.copyfile(FIXTURE / name, work / name)
        (work / 'Probe.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><AllowUnsafeBlocks>true</AllowUnsafeBlocks>
<Nullable>disable</Nullable><EnableNETAnalyzers>false</EnableNETAnalyzers><NoWarn>0649;0162;0169;0414;8500</NoWarn>
<NuGetAudit>false</NuGetAudit></PropertyGroup>
<ItemGroup><PackageReference Include="Silk.NET.Vulkan" Version="2.22.0" /></ItemGroup></Project>''')
        (work / 'NuGet.Config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
        (work / 'global.json').write_text(json.dumps({'sdk': {'version': pin['dotnet'], 'rollForward': 'disable'}}))
        result = subprocess.run([DOTNET, 'run', '--project', str(work / 'Probe.csproj'), '-c', 'Release'],
                                cwd=work, capture_output=True, text=True, timeout=600, env=environment)
        if variant == 'unguarded':
            failure = (result.stdout + result.stderr)
            check(result.returncode != 0 and 'same buffer texture program, views changed without a setter: set 2 binding 32 buffer view 40, expected 41' in failure,
                  'sensitivity: without the buffer view guard the fixture reads a stale buffer view: ' + failure[-800:])
            reports[variant] = dict(failedAsExpected=True)
            continue
        if result.returncode:
            print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
        check(result.returncode == 0, variant + ': fixture ran')
        lines = result.stdout.splitlines()
        reports[variant] = json.loads(next(line for line in lines if line.startswith('{')))
        reports[variant]['trace'] = lines[lines.index('TRACE') + 1:]
        print(variant, json.dumps({k: v for k, v in reports[variant].items() if k not in ('trace', 'steps')}), flush=True)

c, k = reports['control'], reports['candidate']
check(c['trace'] == k['trace'] and c['traceSha256'] == k['traceSha256'] and c['observations'] == k['observations'] >= 40,
      'every draw and dispatch reads the same descriptors in both variants')
steps = {s['label']: (cs, s) for cs, s in zip(c['steps'], k['steps'])}
check([s['label'] for s in c['steps']] == [s['label'] for s in k['steps']], 'same steps')
for label, (cs, ks) in steps.items():
    check(ks['writes'] <= cs['writes'] and ks['allocations'] <= cs['allocations'] and ks['descriptors'] <= cs['descriptors'],
          label + ': the candidate never writes more')
    if not label.startswith('same compute program') and not label.startswith('same graphics program') and \
       label not in ('first compute program again',):
        pass
same = steps['same compute program, nothing changed']
check(same[0]['writes'] == 4 and same[0]['arraySetLookups'] == 1 and same[1]['writes'] == same[1]['binds'] == same[1]['allocations'] == 0 and
      same[1]['arraySetLookups'] == 0, 'nothing changed: control writes the four sets and looks up the array set again; candidate nothing: ' + str(same))
for label, sets in (('same compute program, uniform offset', 1), ('same compute program, texture changed', 1),
                    ('same compute program, storage range', 1), ('same compute program, image changed', 1),
                    ('same compute program, texture array element changed', 1),
                    ('same compute program after an overlapping buffer invalidation', 1),
                    ('same compute program, identical assignment', 0), ('same compute program after a disjoint buffer write', 0),
                    ('same graphics program, nothing changed', 0), ('new command buffer, same program again', 0)):
    check(steps[label][1]['writes'] == sets and steps[label][0]['writes'] > sets, f'{label}: candidate writes {sets} set(s): {steps[label]}')
for label in ('other compute program, same layout', 'first compute program again', 'graphics again after compute',
              'other graphics program, same layout', 'new command buffer, same program', 'same program after a buffer replacement',
              'buffer texture program'):
    check(steps[label][0] == steps[label][1], label + ': unchanged (another program, a new command buffer or a replacement): ' + str(steps[label]))
silent = steps['same buffer texture program, views changed without a setter']
check(silent[1]['writes'] == 2 and silent[0]['writes'] == 2, 'buffer texture and buffer image sets written again: ' + str(silent))
loops = {v: reports[v]['loops'] for v in ('control', 'candidate')}
check(loops['control']['uniformEachDispatch']['writes'] == 8000 and loops['candidate']['uniformEachDispatch']['writes'] == 2000 and
      loops['control']['unchanged']['writes'] == 8000 and loops['candidate']['unchanged']['writes'] == 0,
      '2 000 dispatches of one program: control writes 4 sets each, candidate the uniform set when it changes, none otherwise: ' + str(loops))
check(k['renderDetail']['SameProgramSets'] > 0 and k['renderDetail']['ProgramSets'] > k['renderDetail']['SameProgramSets'] and
      sum(k['renderDetail']['DescriptorSetWrites']) == sum(k['writesBySet']) and k['renderDetail']['DescriptorsWritten'] > 0,
      'the window counters count the program sets and every template write: ' + str(k['renderDetail']))

inputs = ['build-utils/melonx/adapt_same_program_descriptors.py', 'build-utils/melonx/adapt_session.py',
          'build-utils/melonx/adapt_descriptor_updates.py', 'test/melonx_same_program_descriptors_test.py',
          'test/melonx_adapter_control.py', 'test/melonx_same_program_descriptors/Program.cs',
          'test/melonx_same_program_descriptors/Boundaries.cs']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core703Preparation',
               postimages={p: hashlib.sha256((FINAL_SOURCE / p).read_bytes()).hexdigest() for p in BASELINE} if FINAL_PREPARATION else {},
               comparison=dict(sameDescriptorsRead=True, observations=c['observations'], traceSha256=c['traceSha256'],
                               unchangedDispatchWritesControl=same[0]['writes'], unchangedDispatchWritesCandidate=same[1]['writes'],
                               loops=loops, sensitivityVariantFailed=True),
               steps={v: reports[v]['steps'] for v in ('control', 'candidate')}, productionMemberHashes=member_hashes,
               sdk=sdk, physicalDeviceTested=False, productionAssembliesBuilt=built, productionUpdaterMembersExecuted=True,
               vulkanBoundariesDoubled=True, sourceBaseline=BASELINE,
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               upstreamInputs={p: hashlib.sha256((SOURCE / p).read_bytes()).hexdigest() for p in FILES},
               limitation='Production updater members with Vulkan boundaries doubled; MoltenVK, the render thread time saved '
                          'and the share of program sets that repeat the current program in Hogwarts Legacy are known only '
                          'from a device run (the pass detail line counts them).')
out = ROOT / 'dist/melonx/same-program-descriptors-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk, loops=loops)))
