#!/usr/bin/env python3
"""An update of the main sets alone keeps the bindless array sets bound (adapt_extra_set_binds), before and after.

Usage: melonx_extra_set_binds_test.py <Core 713 prepared MeloNX tree>
       melonx_extra_set_binds_test.py <control> --candidate-source <final preparation containing the adapter>

Control is the preparation without the adapter, candidate adds it. Static checks bind the mechanism: every event that
can change or disturb an extra set raises the texture or image flag (SetProgram with another program, CopyFrom and
SignalCommandBufferChange set all four; the helper shaders restore the main pipeline through SignalCommandBufferChange;
SetTextureArraySeparate/SetImageArraySeparate signal their set; bound texture and image arrays signal
ForceTextureDirty/ForceImageDirty on an element change); the extra sets are bound with the program's own layout; Auto
keeps a resource referenced by a command buffer until it completes. Candidate: only the adapter's replacements, fail
closed; the production Ryujinx.Graphics.Vulkan assembly builds. Executed: the production DescriptorSetUpdater members
(test/melonx_extra_set_binds, adapted from the Core 705 fixture) with Vulkan boundaries that keep the bytes each set was
written with and the set bound per (bind point, set index), disturbing sets as Vulkan does for another layout. After
every draw or dispatch the descriptors read, and the array set bound at index 4 (which array, which version, bound with
which layout), are checked against what the script bound: texture, buffer texture and image arrays in the extra set,
their element changes, uniform-only and storage-only updates, programs of the same and of another layout, new command
buffers, a plain texture flag on an image array program. Control and candidate read the same descriptors at every step;
the candidate looks up and binds fewer array sets. A variant that ignores the texture flag must fail (stale array
version after an element change). No device, no MoltenVK. Writes dist/melonx/extra-set-binds-checks.json.
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
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_extra_set_binds', _HOLD)
import adapt_extra_set_binds  # noqa: E402
from adapt_extra_set_binds import apply, BASELINE, UPDATER  # noqa: E402
from adapt_descriptor_updates import method  # noqa: E402

FIXTURE = ROOT / 'test/melonx_extra_set_binds'
DOTNET = os.environ.get('DOTNET', 'dotnet')
TAG = 'RewindBox (adapt_extra_set_binds)'
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
    '        public void AdvancePdSequence(', '        public void SetProgram(', '        private static DirtyFlags BufferViewSets(',
    '        public void SetImage(CommandBufferScoped cbs, ShaderStage stage, int binding, ITexture image)',
    '        public void SetStorageBuffers(CommandBuffer commandBuffer, ReadOnlySpan<BufferAssignment> buffers)',
    '        public void SetTextureAndSampler(\n', '        public void SetTextureArraySeparate(', '        public void SetImageArraySeparate(',
    '        private static ref ArrayRef<T> GetArrayRef<T>(', '        public void SetUniformBuffers(',
    '        private static Span<T> TemplateScratch<T>(', '        private void SignalDirty(',
    '        public void UpdateAndBindDescriptorSets(', '        private static bool UpdateBuffer(',
    '        private void UpdateAndBind(CommandBufferScoped cbs, ShaderCollection program, int setIndex, PipelineBindPoint pbp)',
    '        private void UpdateAndBindUniformBufferPd(', '        private void Initialize(CommandBufferScoped cbs, int setIndex, DescriptorSetCollection dsc)',
    '        private void BindExtraSets(', '        public void SignalCommandBufferChange(', '        public void ForceTextureDirty(',
    '        public void ForceImageDirty(', '        private static void SwapBuffer(', '        public void SwapBuffer(',
]
CONDITION = 'arraysKept: (_dirty & (DirtyFlags.Texture | DirtyFlags.Image)) == 0'
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
vulkan = 'src/Ryujinx.Graphics.Vulkan/'
updater = read(SOURCE, UPDATER)
helper = read(SOURCE, vulkan + 'PipelineHelperShader.cs')
full = read(SOURCE, vulkan + 'PipelineFull.cs')
base = read(SOURCE, vulkan + 'PipelineBase.cs')
check('SignalCommandBufferChange();' in member(helper, 'public void SetCommandBuffer(CommandBufferScoped cbs)') and
      'gd.PipelineInternal.Restore();' in helper and 'SignalCommandBufferChange();' in member(full, 'public void Restore()'),
      'helper shaders: their own updater, the main pipeline restored through SignalCommandBufferChange')
check('_descriptorSetUpdater.SignalCommandBufferChange();' in member(base, 'protected void SignalCommandBufferChange()'),
      'command buffer changes reach the updater')
check('_dirty = DirtyFlags.All;' in member(updater, 'public void SignalCommandBufferChange()') and
      '_dirty = DirtyFlags.All;' in member(updater, 'public void CopyFrom(DescriptorSetUpdater other)') and
      member(updater, 'public void SetProgram(').count('_dirty = DirtyFlags.All;') == 1,
      'a command buffer change, CopyFrom and another program mark all four sets dirty')
check('SignalDirty(DirtyFlags.Texture);' in member(updater, 'public void SetTextureArraySeparate(') and
      'SignalDirty(DirtyFlags.Image);' in member(updater, 'public void SetImageArraySeparate('),
      'another array or stage at an extra set marks the texture or image set dirty')
array = read(SOURCE, vulkan + 'ResourceArray.cs')
check('gd.PipelineInternal.ForceImageDirty();' in array and 'gd.PipelineInternal.ForceTextureDirty();' in array and
      'if (_bindCount != 0)' in member(array, 'protected void SetDirty(VulkanRenderer gd, bool isImage)'),
      'bound texture and image arrays mark their set dirty when their elements change')
for name in ('TextureArray.cs', 'ImageArray.cs'):
    text = read(SOURCE, vulkan + name)
    check(text.count('SetDirty(_gd, isImage: ') == 1 and 'private void SetDirty(bool storageChanged)' in text,
          name + ': every element change goes through SetDirty')
bind_extra = member(updater, 'private void BindExtraSets(')
check(bind_extra.count('CmdBindDescriptorSets(') == 1 and '_program.PipelineLayout, (uint)setIndex, 1, sets' in bind_extra,
      'the extra sets are bound one by one with the program\'s own layout')
auto = read(SOURCE, vulkan + 'Auto.cs')
check('if (!_destroyed)' in member(auto, 'public T Get(CommandBufferScoped cbs)') and
      '_value = default;' in member(auto, 'public void DecrementReferenceCount()') and
      'if (_cbOwnership.Set(cbs.CommandBufferIndex))' in member(auto, 'public void AddCommandBufferDependencies(CommandBufferScoped cbs)'),
      'Auto: once per command buffer, a value reset only when the last reference (command buffers included) is released')

replacements, reports = [], {}
original_once = adapt_extra_set_binds.once
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_TieredCompilation='0')
pin = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())
built = []
with tempfile.TemporaryDirectory(prefix='melonx-extra-set-binds-') as temporary:
    temporary = Path(temporary).resolve()
    candidate_tree = temporary / 'candidate-tree'
    shutil.copytree(SOURCE, candidate_tree, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
    use_authenticated_libhac_feed(candidate_tree, ROOT)

    def recording_once(path, old, new):
        replacements.append((path.relative_to(candidate_tree).as_posix(), old, new))
        original_once(path, old, new)

    adapt_extra_set_binds.once = recording_once
    try:
        changed = apply(candidate_tree)
    finally:
        adapt_extra_set_binds.once = original_once
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
        later = files_edited_later('adapt_extra_set_binds')
        for name in BASELINE:
            if name not in later:
                check((candidate_tree / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)
    candidate_text = read(candidate_tree, UPDATER)
    extra = member(candidate_text, 'private void BindExtraSets(')
    check(CONDITION in member(candidate_text, 'public void UpdateAndBindDescriptorSets(') and
          'if (arraysKept && segment.IsArray && segment.Type is not (ResourceType.BufferTexture or ResourceType.BufferImage))' in extra and
          extra.index('if (arraysKept') < extra.index('if (segment.IsArray)'),
          'candidate: only texture, sampler and image arrays are kept, only without a texture or image change')
    result = subprocess.run([DOTNET, 'build', str(candidate_tree / 'src/Ryujinx.Graphics.Vulkan/Ryujinx.Graphics.Vulkan.csproj'), '-c', 'Release',
                             '-nologo', '-m:1', '-p:NuGetAudit=false'], capture_output=True, text=True, timeout=2400,
                            env=dict(environment, DOTNET_TieredCompilation='1'), cwd=candidate_tree)
    if result.returncode:
        print(result.stdout[-6000:], result.stderr[-2000:], flush=True)
    check(result.returncode == 0, 'production Ryujinx.Graphics.Vulkan builds with the adapter')
    built.append('Ryujinx.Graphics.Vulkan')

    variants = {'control': read(SOURCE, UPDATER), 'candidate': candidate_text,
                'textureFlagIgnored': candidate_text.replace(CONDITION, 'arraysKept: (_dirty & DirtyFlags.Image) == 0')}
    check(variants['textureFlagIgnored'] != candidate_text, 'the condition is replaceable for the sensitivity variant')
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
        if variant == 'textureFlagIgnored':
            failure = result.stdout + result.stderr
            check(result.returncode != 0 and 'same compute program, texture array element changed: the array set bound holds version 0, current 1' in failure,
                  'sensitivity: keeping the array sets after a texture array change reads a stale array: ' + failure[-800:])
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
check(c['trace'] == k['trace'] and c['traceSha256'] == k['traceSha256'] and c['observations'] == k['observations'] >= 60,
      'every draw and dispatch reads the same descriptors and the same array set version in both variants')
check([s['label'] for s in c['steps']] == [s['label'] for s in k['steps']], 'same steps')
steps = {s['label']: (cs, s) for cs, s in zip(c['steps'], k['steps'])}
for label, (cs, ks) in steps.items():
    check(ks['writes'] == cs['writes'] and ks['allocations'] == cs['allocations'] and ks['descriptors'] == cs['descriptors'],
          label + ': the same sets written')
    check(ks['arraySetLookups'] <= cs['arraySetLookups'] and ks['binds'] <= cs['binds'] and
          cs['binds'] - ks['binds'] == cs['arraySetLookups'] - ks['arraySetLookups'],
          label + ': only array set lookups and their binds removed: ' + str((cs, ks)))
kept = ('same compute program, uniform offset', 'same compute program, storage range', 'same compute program, storage offset',
        'same compute program, uniform only after the array change', 'same compute program, storage only',
        'array program, uniform only', 'another layout, uniform only',
        'array program after another layout, uniform only', 'image array program, uniform only',
        'image array program, uniform only after the change', 'image array program, new command buffer, uniform only',
        'texture array program, uniform only')
for label in kept:
    cs, ks = steps[label]
    check(cs['arraySetLookups'] == 1 and ks['arraySetLookups'] == 0 and ks['binds'] == cs['binds'] - 1,
          f'{label}: the array set kept bound (control looks it up and binds it again): {steps[label]}')
looked_up = ('compute first dispatch', 'same compute program, texture changed', 'same compute program, image changed',
             'same compute program, texture array element changed', 'first compute program again', 'back to the array program',
             'program of another layout with an array set', 'array program after another layout', 'buffer texture array program',
             'buffer texture array program, uniform only', 'buffer texture array element changed', 'image array program',
             'image array element changed', 'image array program, a plain texture flag', 'image array program, new command buffer',
             'back to the texture array program')
for label in looked_up:
    check(steps[label][0] == steps[label][1] and steps[label][1]['arraySetLookups'] == 1,
          f'{label}: unchanged, the array set looked up and bound (change, program, layout, command buffer or buffer views): {steps[label]}')
loops = {v: reports[v]['loops'] for v in ('control', 'candidate')}
lc, lk = loops['control'], loops['candidate']
check(lc['uniformEachDispatch']['arraySetLookups'] == 2000 and lk['uniformEachDispatch']['arraySetLookups'] == 0 and
      lc['uniformEachDispatch']['binds'] == 4000 and lk['uniformEachDispatch']['binds'] == 2000 and
      lc['storageEachDispatch']['arraySetLookups'] == 2000 and lk['storageEachDispatch']['arraySetLookups'] == 0 and
      lk['storageEachDispatch']['binds'] == 2000 and lk['arrayChangeEvery8']['arraySetLookups'] == 250 and
      lc['arrayChangeEvery8']['arraySetLookups'] == 2000 and lc['unchanged'] ['arraySetLookups'] == lk['unchanged']['arraySetLookups'] == 0 and
      all(lc[name]['writes'] == lk[name]['writes'] for name in lc),
      '2 000 dispatches of one array program: control looks the array set up and binds it each time, candidate only after '
      'an array change; the same sets written: ' + str(loops))
check(c['disturbed'] == k['disturbed'] > 0, 'programs of other layouts disturbed higher sets in both variants (the model is exercised)')

inputs = ['build-utils/melonx/adapt_extra_set_binds.py', 'build-utils/melonx/adapt_session.py',
          'build-utils/melonx/adapt_descriptor_updates.py', 'test/melonx_extra_set_binds_test.py',
          'test/melonx_adapter_control.py', 'test/melonx_extra_set_binds/Program.cs', 'test/melonx_extra_set_binds/Boundaries.cs']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core713Preparation',
               postimages={p: hashlib.sha256((FINAL_SOURCE / p).read_bytes()).hexdigest() for p in BASELINE} if FINAL_PREPARATION else {},
               comparison=dict(sameDescriptorsRead=True, observations=c['observations'], traceSha256=c['traceSha256'],
                               uniformOnlyLookupsControl=lc['uniformEachDispatch']['arraySetLookups'],
                               uniformOnlyLookupsCandidate=lk['uniformEachDispatch']['arraySetLookups'],
                               loops=loops, sensitivityVariantFailed=True),
               steps={v: reports[v]['steps'] for v in ('control', 'candidate')}, productionMemberHashes=member_hashes,
               sdk=sdk, physicalDeviceTested=False, productionAssembliesBuilt=built, productionUpdaterMembersExecuted=True,
               vulkanBoundariesDoubled=True, sourceBaseline=BASELINE,
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               upstreamInputs={p: hashlib.sha256((SOURCE / p).read_bytes()).hexdigest() for p in FILES},
               limitation='Production updater members with Vulkan boundaries and the arrays doubled; MoltenVK, the render thread '
                          'time saved and the share of uniform/storage-only updates of array programs in Hogwarts Legacy are '
                          'known only from a device run (the pass detail line counts array current binds and reference passes).')
out = ROOT / 'dist/melonx/extra-set-binds-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk, loops=loops)))
