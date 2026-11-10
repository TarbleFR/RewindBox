#!/usr/bin/env python3
"""adapt_extra_array_dirty on the final preparation, against the Core 721 preparation as control.

Usage: melonx_extra_array_dirty_test.py <control> --candidate-source <final preparation containing the adapter>

IPA 718 Hogwarts in play: SetTextureArraySeparate 17 000-93 500 times per 5 s and 63 517 texture sets written (about 74
descriptors each) on the render thread; a separate array change marked DirtyFlags.Texture, so set 2 was written again
although it does not hold that array. Static: only the adapter's three replacements; SetTextureArraySeparate is the only
setter signalling the new bit; set 2's content is read from _textureRefs, _bufferTextureRefs and _textureArrayRefs only
(never _textureArrayExtraRefs); BindExtraSets rebinds the extra sets when the bit is set; All contains it (program and
command buffer changes mark every set); the production Ryujinx.Graphics.Vulkan assembly builds. Executed: the
production DescriptorSetUpdater members with the Vulkan boundaries of test/melonx_same_program_descriptors (sets keep
the bytes they were written with, the set bound per bind point and index is recorded), all of its scenarios plus
separate arrays switched with set 2 unchanged, with a texture change, with an element change, across a new command
buffer and another program, and 400 dispatches switching the array each time (test/melonx_extra_array_dirty). After
every draw or dispatch the descriptors it reads are decoded and checked against the resources bound, including which
array's set is bound at index 4 and its version: control and candidate read the same descriptors; the candidate writes
set 2 only when its content changes. A variant whose extra sets are not rebound on the new bit must fail (stale array
set). No device, no MoltenVK. Writes dist/melonx/extra-array-dirty-checks.json.
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
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_extra_array_dirty', _HOLD)
import adapt_extra_array_dirty as adapter  # noqa: E402
from adapt_descriptor_updates import method  # noqa: E402

UPDATER = adapter.UPDATER
FIXTURE = ROOT / 'test/melonx_extra_array_dirty'
DOTNET = os.environ.get('DOTNET', 'dotnet')
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
    '        private static DirtyFlags BufferViewSets(',
]
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def read(tree, name):
    return (tree / name).read_text(encoding='utf-8-sig')


for name, expected in adapter.BASELINE.items():
    check(hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected, 'not the Core 721 preparation: ' + name)

reports = {}
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_TieredCompilation='0')
pin = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())
with tempfile.TemporaryDirectory(prefix='melonx-extra-array-dirty-') as temporary:
    temporary = Path(temporary).resolve()
    candidate_tree = temporary / 'candidate-tree'
    shutil.copytree(SOURCE, candidate_tree, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
    use_authenticated_libhac_feed(candidate_tree, ROOT)
    changed = adapter.apply(candidate_tree)
    check(sorted(p.relative_to(candidate_tree).as_posix() for p in changed) == [UPDATER], 'the adapter changes DescriptorSetUpdater.cs only')
    duplicate = temporary / 'duplicate'
    (duplicate / UPDATER).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(candidate_tree / UPDATER, duplicate / UPDATER)
    try:
        adapter.apply(duplicate)
        refused = False
    except AssertionError:
        refused = True
    check(refused, 'fail closed: an adapted tree is refused')
    control_text, candidate_text = read(SOURCE, UPDATER), read(candidate_tree, UPDATER)
    undone = candidate_text
    for old, new in reversed(adapter.PAIRS):
        check(undone.count(new) == 1, 'each replacement once: ' + new.strip().splitlines()[0][:60])
        undone = undone.replace(new, old)
    check(undone == control_text, 'DescriptorSetUpdater.cs is the preparation but the adapter\'s replacements')
    check(candidate_text.count(adapter.TAG) == 3, 'commented')
    if FINAL_PREPARATION and UPDATER not in files_edited_later('adapt_extra_array_dirty'):
        check((candidate_tree / UPDATER).read_bytes() == (FINAL_SOURCE / UPDATER).read_bytes(), 'final preparation is the adapter')
    # Static: the bit's writers and readers.
    check(candidate_text.count('DirtyFlags.TextureArrayExtra') == 2 and candidate_text.count('TextureArrayExtra = 1 << 4,') == 1 and
          'SignalDirty(DirtyFlags.TextureArrayExtra);' in method(candidate_text, '        public void SetTextureArraySeparate('),
          'SetTextureArraySeparate is the only writer of the bit; BindExtraSets\' condition and All read it')
    separate_image = method(candidate_text, '        public void SetImageArraySeparate(')
    check('SignalDirty(DirtyFlags.Image);' in separate_image, 'image arrays in their own set keep DirtyFlags.Image')
    update = method(candidate_text, '        private void UpdateAndBind(CommandBufferScoped cbs, ShaderCollection program, int setIndex, PipelineBindPoint pbp)')
    check('_textureArrayExtraRefs' not in update and '_textureArrayRefs[binding]' in update and '_textureRefs[index]' in update,
          'set 2 is written from the main texture bindings only, never from the separate arrays')
    extra = method(candidate_text, '        private void BindExtraSets(')
    check('_textureArrayExtraRefs[setIndex - PipelineBase.DescriptorSetLayouts].Array.GetDescriptorSets(' in extra,
          'the separate arrays are bound by BindExtraSets')
    check('All = Uniform | Storage | Texture | Image | TextureArrayExtra,' in candidate_text and
          candidate_text.count('_dirty = DirtyFlags.All;') == control_text.count('_dirty = DirtyFlags.All;') >= 2,
          'program and command buffer changes still mark every set, the new bit included')
    result = subprocess.run([DOTNET, 'build', str(candidate_tree / 'src/Ryujinx.Graphics.Vulkan/Ryujinx.Graphics.Vulkan.csproj'), '-c', 'Release',
                             '-nologo', '-m:1', '-p:NuGetAudit=false'], capture_output=True, text=True, timeout=2400,
                            env=dict(environment, DOTNET_TieredCompilation='1'), cwd=candidate_tree)
    if result.returncode:
        print(result.stdout[-6000:], result.stderr[-2000:], flush=True)
    check(result.returncode == 0, 'production Ryujinx.Graphics.Vulkan builds with the adapter')

    variants = {'control': control_text, 'candidate': candidate_text,
                'unbound': candidate_text.replace(adapter.EXTRA_NEW, adapter.EXTRA_OLD)}
    check(variants['unbound'] != candidate_text, 'the rebind condition is removable for the sensitivity variant')
    member_hashes = {}
    for variant, text in variants.items():
        members = [method(text, signature) for signature in SIGNATURES]
        member_hashes[variant] = {s.strip(): hashlib.sha256(m.encode()).hexdigest() for s, m in zip(SIGNATURES, members)}
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
        if variant == 'unbound':
            failure = result.stdout + result.stderr
            check(result.returncode != 0 and 'separate array B, set 2 unchanged: the texture array set bound is another array\'s set' in failure,
                  'sensitivity: without the rebind the draw reads the previous array\'s set: ' + failure[-800:])
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
check(c['trace'] == k['trace'] and c['traceSha256'] == k['traceSha256'] and c['observations'] == k['observations'] >= 100,
      'every draw and dispatch reads the same descriptors in both variants, the separate array set included')
check([s['label'] for s in c['steps']] == [s['label'] for s in k['steps']], 'same steps')
steps = {cs['label']: (cs, ks) for cs, ks in zip(c['steps'], k['steps'])}
for label, (cs, ks) in steps.items():
    check(ks['writes'] <= cs['writes'] and ks['descriptors'] <= cs['descriptors'] and ks['arraySetLookups'] == cs['arraySetLookups'],
          label + ': the candidate never writes more, and binds the separate array set exactly as often: ' + str((cs, ks)))
for label in ('separate array B, set 2 unchanged', 'separate array A again, set 2 unchanged'):
    cs, ks = steps[label]
    check(cs['writes'] == 1 and ks['writes'] == 0 and cs['arraySetLookups'] == ks['arraySetLookups'] == 1,
          label + ': control writes set 2 again, the candidate only binds the array set: ' + str((cs, ks)))
for label in ('separate array B and a texture change', 'separate array B element changed while bound'):
    cs, ks = steps[label]
    check(cs['writes'] == ks['writes'] == 1, label + ': set 2 written in both: ' + str((cs, ks)))
cs, ks = steps['separate array A and a uniform change']
check(cs['writes'] == 2 and ks['writes'] == 1, 'a uniform change with the switch: the candidate writes the uniform set only: ' + str((cs, ks)))
for label in ('new command buffer, separate array B', 'other compute program after the switches', 'array program after another program'):
    check(steps[label][0]['writes'] == steps[label][1]['writes'], label + ': unchanged (a new command buffer or another program): ' + str(steps[label]))
loops = {v: reports[v]['loops'] for v in ('control', 'candidate')}
sc, sk = loops['control']['separateEachDispatch'], loops['candidate']['separateEachDispatch']
check(sc['writes'] == 400 and sk['writes'] == 0 and sc['arraySetLookups'] == sk['arraySetLookups'] == 400,
      '400 dispatches switching the separate array: control writes set 2 each time, the candidate never: ' + str(loops))
for name in ('uniformEachDispatch', 'unchanged'):
    check(loops['control'][name] == {**loops['candidate'][name], 'ms': loops['control'][name]['ms']},
          name + ' loop: unchanged by this adapter: ' + str(loops))

inputs = ['build-utils/melonx/adapt_extra_array_dirty.py', 'build-utils/melonx/adapt_session.py',
          'build-utils/melonx/adapt_descriptor_updates.py', 'test/melonx_extra_array_dirty_test.py', 'test/melonx_adapter_control.py',
          'test/melonx_extra_array_dirty/Program.cs', 'test/melonx_extra_array_dirty/Boundaries.cs']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core721Preparation',
               postimages={p: hashlib.sha256((FINAL_SOURCE / p).read_bytes()).hexdigest() for p in adapter.BASELINE} if FINAL_PREPARATION else {},
               comparison=dict(sameDescriptorsRead=True, observations=c['observations'], traceSha256=c['traceSha256'],
                               separateSwitchWritesControl=sc['writes'], separateSwitchWritesCandidate=sk['writes'],
                               arraySetBindsUnchanged=True, sensitivityVariantFailed=True),
               steps={v: reports[v]['steps'] for v in ('control', 'candidate')}, loops=loops, productionMemberHashes=member_hashes,
               sdk=sdk, physicalDeviceTested=False, productionAssembliesBuilt=['Ryujinx.Graphics.Vulkan'], productionUpdaterMembersExecuted=True,
               vulkanBoundariesDoubled=True, sourceBaseline=adapter.BASELINE,
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               upstreamInputs={p: hashlib.sha256((SOURCE / p).read_bytes()).hexdigest() for p in FILES},
               limitation='Production updater members with Vulkan boundaries doubled; the share of texture-set writes caused by '
                          'separate array switches in Hogwarts Legacy and the render-thread time saved are known only from a '
                          'device run (the pass detail line counts the sets written).')
out = ROOT / 'dist/melonx/extra-array-dirty-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk, loops=loops)))
