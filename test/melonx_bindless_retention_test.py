#!/usr/bin/env python3
"""Less managed memory per bindless pool array, and its journal (adapt_bindless_retention), on the real prepared engine.

Usage: melonx_bindless_retention_test.py <Core 658 prepared MeloNX tree> [--work <dir>]
       melonx_bindless_retention_test.py <control> --candidate-source <final preparation containing the adapter> [--work <dir>]
--work: where the control and candidate trees are copied and built (default: a temporary directory, removed at the end);
their bin/obj are removed at the end either way. The Xcode project (src/MeloNX) is not copied: nothing built here uses it.

Applies the adapter to a copy of the Core 658 preparation (the control is a second copy). Static checks bind that each
edited file equals the preparation once the adapter's replacements are undone, that the delta paths, the descriptor-set
writes and the buffer-array paths are unchanged, and, in the preparation, the facts the change relies on: a pool texture
array's rebuild gives its elements no sampler and a pool sampler array's none texture, the delta runs send the array's
own kind only, TextureView.Storage and its image view are read-only and owned by each view, and ResourceArray.Dispose is
the only caller of ReleaseOwnDescriptorSets.
Builds the production Ryujinx.Graphics.Gpu and Ryujinx.Graphics.Vulkan of the candidate (with GAL), then:
- the GPU fixture (test/melonx_bindless_retention/GpuFixture.cs with the boundary doubles of
  test/melonx_array_rebuild_allocations/Program.cs) on the REAL TextureBindingsArrayCache, threaded producers, commands
  and ThreadedArrayPool of each variant: 36 pool scenarios with identical backend contents, synchronisation sets and
  recorded state; three 524288-element texture entries and a 4096-element sampler entry created and rebuilt with the
  live large-object heap read before and after, the arrays kept, the inventory, and their release with the pool;
- the Vulkan probe (test/melonx_bindless_retention/VulkanProbe.cs, test-only InternalsVisibleTo) on the REAL
  TextureArray of each variant: 48 scenarios with identical element state, descriptor values, reference counts and
  change log, identical exception types, the large-object heap of three 524288-element arrays, their release, the
  inventory and the journal text; then a deliberately wrong candidate (samplers ignored in the element comparison) must
  change digests, which shows the digests see the element state.
No eviction is implemented (every measured device entry is in use), so there is no deferred release to test.
Writes dist/melonx/bindless-retention-checks.json. No device, no Metal memory measurement, no FPS claim.
"""
from pathlib import Path
import hashlib, json, os, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
ARGS = sys.argv[1:]
WORK_ARG = None
if '--work' in ARGS:
    WORK_ARG = Path(ARGS[ARGS.index('--work') + 1]).resolve()
SOURCE = Path(ARGS[ARGS.index('--candidate-source') + 1] if '--candidate-source' in ARGS else ARGS[0]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, files_edited_later, use_authenticated_libhac_feed  # noqa: E402
_HOLD = []
FINAL_SOURCE = SOURCE
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_bindless_retention', _HOLD)
import adapt_bindless_retention  # noqa: E402
from adapt_bindless_retention import apply, BASELINE, CACHE, INVENTORY, ARRAY, DETAIL  # noqa: E402

DOTNET = os.environ.get('DOTNET', 'dotnet')
HARNESS = ROOT / 'test/melonx_bindless_retention'
GAL = 'src/Ryujinx.Graphics.GAL'
MULTI = GAL + '/Multithreading'
VK = 'src/Ryujinx.Graphics.Vulkan/'
GPU_FIXTURE_FILES = [
    CACHE, 'src/Ryujinx.Graphics.Gpu/Image/TextureBindingInfo.cs', 'src/Ryujinx.Graphics.Gpu/Engine/Types/SamplerIndex.cs',
    'src/Ryujinx.Graphics.Shader/TextureHandle.cs', 'src/Ryujinx.Graphics.Shader/TextureUsageFlags.cs',
    'src/Ryujinx.Graphics.Shader/ShaderStage.cs', GAL + '/Target.cs', INVENTORY, GAL + '/IImageArray.cs',
    MULTI + '/Model/TableRef.cs', MULTI + '/Model/ThreadedArrayPool.cs', MULTI + '/Commands/IGALCommand.cs',
    MULTI + '/Resources/ThreadedTextureArray.cs', MULTI + '/Resources/ThreadedImageArray.cs',
    MULTI + '/Commands/TextureArray/TextureArraySetTexturesCommand.cs', MULTI + '/Commands/TextureArray/TextureArraySetSamplersCommand.cs',
    MULTI + '/Commands/TextureArray/TextureArrayDisposeCommand.cs', MULTI + '/Commands/ImageArray/ImageArraySetImagesCommand.cs',
    MULTI + '/Commands/ImageArray/ImageArrayDisposeCommand.cs',
]
MiB = 1 << 20
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(tree, name):
    return (tree / name).read_text(encoding='utf-8-sig')


def member(text, signature):
    """One complete member, its exact body."""
    assert text.count(signature) == 1, signature
    start = text.rindex('\n', 0, text.index(signature)) + 1
    depth, index = 0, text.index('{', text.index(signature))
    for index in range(index, len(text)):
        depth += (text[index] == '{') - (text[index] == '}')
        if depth == 0:
            return text[start:index + 1]
    raise AssertionError(signature)


for name, expected in BASELINE.items():
    check(sha(SOURCE / name) == expected, 'not the Core 658 preparation: ' + name)

# Preparation facts the change relies on.
cache_source, array_source = read(SOURCE, CACHE), read(SOURCE, ARRAY)
rebuild = member(cache_source, 'private void UpdateFromPool(')
check(rebuild.count('sampler = samplerPool?.Get(index);') == 1 and
      rebuild.index('if (isSampler)\n                    {\n                        sampler = samplerPool?.Get(index);') <
      rebuild.index('ref readonly TextureDescriptor descriptor = ref texturePool.GetForBinding(index, bindingInfo.FormatInfo, out texture);'),
      'pool rebuild: a sampler is looked up only for a sampler array, a texture only for the others')
check('ISampler hostSampler = sampler?.GetHostSampler(texture);' in rebuild and
      'ITexture hostTexture = texture?.GetTargetTexture(bindingInfo.Target);' in rebuild,
      'pool rebuild: the host values come from those lookups (null otherwise)')
flush = member(cache_source, 'private void FlushDeltaRun(')
samplers_sent = flush.index('entry.TextureArray.SetSamplers(runStart, samplers);')
check(flush.index('if (isSampler)') < samplers_sent < flush.index('return;', samplers_sent) <
      flush.index('entry.TextureArray.SetTextures(runStart, textures);'), 'delta runs send the array\'s own kind only')
view_source = read(SOURCE, VK + 'TextureView.cs')
check('private readonly Auto<DisposableImageView> _imageView;' in view_source and 'public TextureStorage Storage { get; }' in view_source and
      member(view_source, 'public Auto<DisposableImageView> GetImageView()').count('return _imageView;') == 1,
      'TextureView: storage and image view are read-only members, GetImageView returns the field')
check(view_source.count('_imageView = ') == 2 and '_imageView = CreateImageView(componentMapping, subresourceRange, type, shaderUsage);' in view_source and
      '_imageView = new Auto<DisposableImageView>(view);' in view_source and
      'return new Auto<DisposableImageView>(new DisposableImageView(gd.Api, device, imageView), null, storage.GetImage());' in view_source,
      'each view owns a new image view (the element comparison by image view is a comparison by view)')
sampler_source = read(SOURCE, VK + 'SamplerHolder.cs')
check('private readonly Auto<DisposableSampler> _sampler;' in sampler_source, 'a sampler holder\'s sampler is read-only')
callers = [p.relative_to(SOURCE).as_posix() for p in (SOURCE / 'src/Ryujinx.Graphics.Vulkan').rglob('*.cs')
           if 'ReleaseOwnDescriptorSets()' in p.read_text(encoding='utf-8-sig')]
check(sorted(callers) == [VK + 'ResourceArray.cs', ARRAY] and
      member(read(SOURCE, VK + 'ResourceArray.cs'), 'public void Dispose()').count('ReleaseOwnDescriptorSets();') == 1,
      'ReleaseOwnDescriptorSets runs from Dispose only')
check('private readonly TextureRef[] _textureRefs;' in array_source and array_source.count('_textureRefs = new TextureRef[size];') == 1,
      'the delivered element array')

replacements = {}
original_once = adapt_bindless_retention.once
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1')


def ignore_for(base):
    def ignore(directory, names):
        skipped = {'.git', 'bin', 'obj'} & set(names)
        if Path(directory).resolve() == (base / 'src').resolve() and 'MeloNX' in names:
            skipped.add('MeloNX')
        return skipped
    return ignore


def dotnet(*arguments, cwd, timeout=2400):
    result = subprocess.run([DOTNET, *arguments], capture_output=True, text=True, timeout=timeout, env=environment, cwd=cwd)
    if result.returncode:
        errors = [line for line in result.stdout.splitlines() if ': error ' in line]
        print('\n'.join(dict.fromkeys(errors[:40])), result.stdout[-4000:], result.stderr[-2000:], sep='\n', flush=True)
    return result


def run(dll, cwd):
    result = subprocess.run([DOTNET, str(dll)], capture_output=True, text=True, timeout=1800, env=environment, cwd=cwd)
    if result.returncode:
        print(result.stdout[-4000:], result.stderr[-4000:], flush=True)
    check(result.returncode == 0, 'runs: ' + str(dll))
    return json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))


def gpu_fixture(tree, out, adapted):
    for relative in GPU_FIXTURE_FILES:
        (out / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(tree / relative, out / relative)
    shutil.copyfile(ROOT / 'test/melonx_array_rebuild_allocations/Program.cs', out / 'Doubles.cs')
    shutil.copyfile(HARNESS / 'GpuFixture.cs', out / 'GpuFixture.cs')
    define = '<DefineConstants>ADAPTED</DefineConstants>' if adapted else ''
    (out / 'test.csproj').write_text(f'''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><StartupObject>BindlessRetentionGpu</StartupObject>
<AllowUnsafeBlocks>true</AllowUnsafeBlocks><Nullable>disable</Nullable><ServerGarbageCollection>false</ServerGarbageCollection>
<EnableNETAnalyzers>false</EnableNETAnalyzers><NuGetAudit>false</NuGetAudit><NoWarn>0649;0162;0168;0219;8981;CS7022</NoWarn>{define}
</PropertyGroup><ItemGroup>
<RuntimeHostConfigurationOption Include="System.GC.ConserveMemory" Value="5" />
<RuntimeHostConfigurationOption Include="System.GC.HighMemoryPercent" Value="99" />
</ItemGroup></Project>''')
    (out / 'NuGet.Config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
    check(dotnet('build', str(out / 'test.csproj'), '-c', 'Release', '-nologo', '-p:NuGetAudit=false', cwd=out).returncode == 0,
          'GPU fixture builds: ' + out.name)
    return run(out / 'bin/Release/net10.0/test.dll', out), {p: sha(out / p) for p in GPU_FIXTURE_FILES}


def vulkan_probe(tree, out):
    project = tree / (VK + 'Ryujinx.Graphics.Vulkan.csproj')
    text = project.read_text(encoding='utf-8-sig')
    if 'MeloNXBindlessProbe' not in text:
        check(text.count('</Project>') == 1, 'Vulkan project')
        # Test-only access to the internal production types; the production build is made before, without it.
        project.write_text(text.replace('</Project>', '  <ItemGroup><InternalsVisibleTo Include="MeloNXBindlessProbe" /></ItemGroup>\n</Project>'))
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    shutil.copyfile(HARNESS / 'VulkanProbe.cs', out / 'Program.cs')
    (out / 'MeloNXBindlessProbe.csproj').write_text(f'''<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><Nullable>disable</Nullable>
    <AllowUnsafeBlocks>true</AllowUnsafeBlocks><NoWarn>CA1416;CS8632</NoWarn><NuGetAudit>false</NuGetAudit>
    <ManagePackageVersionsCentrally>false</ManagePackageVersionsCentrally><ServerGarbageCollection>false</ServerGarbageCollection>
  </PropertyGroup>
  <ItemGroup>
    <RuntimeHostConfigurationOption Include="System.GC.ConserveMemory" Value="5" />
    <ProjectReference Include="{tree}/src/Ryujinx.Graphics.Vulkan/Ryujinx.Graphics.Vulkan.csproj" />
  </ItemGroup>
</Project>
''')
    shutil.copyfile(tree / 'global.json', out / 'global.json')
    shutil.copyfile(tree / 'nuget.config', out / 'nuget.config')
    check(dotnet('build', str(out / 'MeloNXBindlessProbe.csproj'), '-c', 'Release', '-nologo', '-m:1', cwd=out).returncode == 0,
          'Vulkan probe builds: ' + out.name)
    return run(out / 'bin/Release/net10.0/MeloNXBindlessProbe.dll', out)


temporary = None
if WORK_ARG is None:
    temporary = tempfile.TemporaryDirectory(prefix='melonx-bindless-retention-')
    WORK = Path(temporary.name).resolve()
else:
    WORK = WORK_ARG
    WORK.mkdir(parents=True, exist_ok=True)
control_tree, work = WORK / 'control', WORK / 'candidate'
outputs = [WORK / name for name in ('gpu-control', 'gpu-candidate', 'vk-control', 'vk-candidate', 'vk-wrong')]
for stale in [control_tree, work, *outputs]:
    if stale.exists():
        shutil.rmtree(stale)
reports, compiled = {}, {}
try:
    shutil.copytree(SOURCE, control_tree, ignore=ignore_for(SOURCE), symlinks=True)
    shutil.copytree(SOURCE, work, ignore=ignore_for(SOURCE), symlinks=True)
    use_authenticated_libhac_feed(control_tree, ROOT)
    use_authenticated_libhac_feed(work, ROOT)

    def recording_once(path, old, new):
        replacements.setdefault(path.relative_to(work).as_posix(), []).append((old, new))
        original_once(path, old, new)

    adapt_bindless_retention.once = recording_once
    try:
        changed = apply(work)
    finally:
        adapt_bindless_retention.once = original_once
    check(sorted(p.relative_to(work).as_posix() for p in changed) == sorted(BASELINE), 'adapter changed other files')
    if FINAL_PREPARATION:
        # Files a later Core 661 adapter also edits are proven by control_source's forward check; the others must
        # be the final preparation's bytes here.
        later = files_edited_later('adapt_bindless_retention')
        for name in BASELINE:
            if name not in later:
                check((work / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)
    for name in BASELINE:
        undone = read(work, name)
        for old, new in reversed(replacements[name]):
            check(undone.count(new) == 1, 'each replacement once: ' + new[:60])
            undone = undone.replace(new, old, 1)
        check(undone == read(SOURCE, name), name + ' is the preparation but the adapter\'s replacements')
    check([len(replacements[n]) for n in (INVENTORY, CACHE, ARRAY, DETAIL)] == [1, 9, 9, 1], 'replacement counts')

    cache, array, detail = read(work, CACHE), read(work, ARRAY), read(work, DETAIL)
    for signature in ('private bool UpdateFromPoolDelta(', 'private void FlushDeltaRun(', 'private bool CollectLoggedChanges(',
                      'public void RecordDelta(', 'public bool DeltaUnchanged(', 'private void UpdateFromBuffer(',
                      'private void RemoveLeastUsedEntries()', 'private static T[] RentRebuildScratch<T>(',
                      'private static void ReturnRebuildScratch<T>(', 'private void SetTextureArray(', 'public void SynchronizeMemory('):
        check(member(cache, signature) == member(cache_source, signature), 'unchanged: ' + signature)
    pool_rebuild = member(cache, 'private void UpdateFromPool(')
    check('samplers = isImage || !isSampler ? null : RentRebuildScratch(' in pool_rebuild and
          'textures = isSampler ? null : RentRebuildScratch(' in pool_rebuild and
          pool_rebuild.count('entry.TextureArray.SetSamplers(0, samplers);') == 1 and
          pool_rebuild.index('if (isSampler)\n                    {\n                        entry.TextureArray.SetSamplers(0, samplers);') <
          pool_rebuild.index('entry.TextureArray.SetTextures(0, textures);'), 'pool rebuild sends the array\'s own kind only')
    check(pool_rebuild.count('ReturnRebuildScratch(') == 2, 'both scratch arrays still returned (null is ignored)')
    for signature in ('private DescriptorSet[] GetOwnDescriptorSets(', 'private unsafe void WriteRuns(', 'private int GatherChanges(',
                      'private void RecordChange(', 'private void AddReferences(', 'private void RefreshValues(',
                      'private static void SwapReference<T>(', 'public ReadOnlySpan<BufferView> GetBufferViews(',
                      'public DescriptorSet[] GetDescriptorSets(', 'private void SetDirty('):
        check(member(array, signature) == member(array_source, signature), 'unchanged: ' + signature)
    check('_textureRefs' not in array and 'struct TextureRef' not in array and 'ref TextureRef' not in array and 'TextureRef[]' not in array,
      'no TextureRef left')
    log = member(detail, 'public static void Log(string window, long frames)')
    check(log.replace('''            // RewindBox (adapt_bindless_retention): the managed storage of the bindless pool arrays still held.
            text.Append(TextureArray.InventoryText());

''', '', 1) == member(read(SOURCE, DETAIL), 'public static void Log(string window, long frames)'), 'the detail line gains one part only')
    check(log.index('TextureArray.InventoryText()') < log.index('text.Append("; GPU ")'), 'before the GPU part')

    # Production assemblies of the candidate (GAL comes with both), then the control's Vulkan for the probe.
    for project in ('src/Ryujinx.Graphics.Gpu/Ryujinx.Graphics.Gpu.csproj', VK + 'Ryujinx.Graphics.Vulkan.csproj'):
        build = dotnet('build', str(work / project), '-c', 'Release', '-nologo', '-m:1', '-p:NuGetAudit=false', cwd=work)
        check(build.returncode == 0, 'production build with the adapter: ' + project)
        warnings = sorted({line for line in build.stdout.splitlines() if 'warning' in line and
                           any(f in line for f in ('TextureBindingsArrayCache.cs', 'ITextureArray.cs', 'TextureArray.cs(', 'PipelineBase.cs'))})
        check(not warnings, 'no compiler warning in the edited files: ' + '\n'.join(warnings[:5]))
        print('candidate: production ' + project + ' built', flush=True)

    reports['gpuControl'], compiled['gpuControl'] = gpu_fixture(control_tree, WORK / 'gpu-control', False)
    reports['gpuCandidate'], compiled['gpuCandidate'] = gpu_fixture(work, WORK / 'gpu-candidate', True)
    print('GPU fixture ran: ' + str(reports['gpuControl']['checks']) + ' / ' + str(reports['gpuCandidate']['checks']) + ' program checks', flush=True)
    reports['vkControl'] = vulkan_probe(control_tree, WORK / 'vk-control')
    reports['vkCandidate'] = vulkan_probe(work, WORK / 'vk-candidate')
    # A wrong candidate: the element comparison ignores the samplers. The digests must see it.
    wrong_text = read(work, ARRAY)
    right = 'return ReferenceEquals(ViewAt(left), ViewAt(right)) && ReferenceEquals(SamplerAt(left), SamplerAt(right));'
    check(wrong_text.count(right) == 1, 'element comparison')
    (work / ARRAY).write_text(wrong_text.replace(right, 'return ReferenceEquals(ViewAt(left), ViewAt(right));'), encoding='utf-8')
    try:
        reports['vkWrong'] = vulkan_probe(work, WORK / 'vk-wrong')
    finally:
        (work / ARRAY).write_text(wrong_text, encoding='utf-8')
    print('Vulkan probe ran', flush=True)
finally:
    for path in [control_tree, work, *outputs]:
        for sub in path.rglob('*') if path.exists() else []:
            if sub.is_dir() and sub.name in ('bin', 'obj'):
                shutil.rmtree(sub, ignore_errors=True)
    if temporary is not None:
        temporary.cleanup()

# GPU: identical results; the companion calls are gone.
gc_, gn = reports['gpuControl'], reports['gpuCandidate']
check(not gc_['adapted'] and gn['adapted'], 'variants swapped')
check(gc_['gcSettings']['conserveMemory'] == gn['gcSettings']['conserveMemory'] == '5', 'published GC setting')
check(len(gc_['scenarios']) == len(gn['scenarios']) == 36, 'GPU scenario inventory')
companion = dict(control=0, candidate=0)
for old, new in zip(gc_['scenarios'], gn['scenarios'], strict=True):
    check({k: v for k, v in old.items() if k not in ('digest', 'wholeRebuildCalls')} ==
          {k: v for k, v in new.items() if k not in ('digest', 'wholeRebuildCalls')}, 'GPU scenario pairing')
    check(old['digest'] == new['digest'], 'backend contents, synchronisation or recorded state differ: ' + json.dumps(new))
    if old['kind'] == 'Texture':
        check(old['wholeRebuildCalls']['samplers'] == old['fullRebuilds'] > 0 and new['wholeRebuildCalls']['samplers'] == 0 and
              new['wholeRebuildCalls']['textures'] == old['wholeRebuildCalls']['textures'] == old['fullRebuilds'],
              'texture arrays: no sampler call per whole rebuild: ' + json.dumps(new))
        companion['control'] += old['wholeRebuildCalls']['samplers']
    if old['kind'] == 'Sampler':
        check(old['wholeRebuildCalls']['textures'] == old['fullRebuilds'] > 0 and new['wholeRebuildCalls']['textures'] == 0 and
              new['wholeRebuildCalls']['samplers'] == old['fullRebuilds'], 'sampler arrays: no texture call per whole rebuild')
        companion['control'] += old['wholeRebuildCalls']['textures']
    if old['kind'] == 'Image':
        check(old['wholeRebuildCalls'] == new['wholeRebuildCalls'], 'image arrays unchanged')
mc, mn = gc_['measure'], gn['measure']
for key in ('length', 'textureEntries', 'deltaStateBytes', 'backendSinkDoubleBytes', 'lohWorldBytes'):
    check(mc[key] == mn[key], 'GPU measure pairing: ' + key)
check(mc['deltaStateBytes'] == 3 * 524288 * 28 + 4096 * 16, 'delta state: 28 bytes per texture element, 16 per sampler element')
check(mc['keptAfterRebuilds']['ISampler'] >= 524288 * 8 and mn['keptAfterRebuilds']['ISampler'] == 0 and
      mn['keptAfterCreation']['ISampler'] == 0, 'no pool-sized sampler array kept by the cache or the threaded pool')
check(mc['keptAfterRebuilds']['ITexture'] == mn['keptAfterRebuilds']['ITexture'], 'texture scratch unchanged')
gpu_saved = mc['lohAfterRebuildsBytes'] - mn['lohAfterRebuildsBytes']
check(abs(gpu_saved - mc['keptAfterRebuilds']['ISampler']) <= 1024,
      'the live large-object heap falls by the sampler arrays no longer kept (their headers aside)')
check(mn['creationAllocatedBytes'] < mc['creationAllocatedBytes'], 'creating the entries allocates less')
check(mn['lohAfterReleaseBytes'] <= mc['lohAfterReleaseBytes'] and
      mc['lohAfterRebuildsBytes'] - mc['lohAfterReleaseBytes'] >= mc['deltaStateBytes'] and
      mn['lohAfterRebuildsBytes'] - mn['lohAfterReleaseBytes'] >= mn['deltaStateBytes'],
      'removing the pool releases the entries\' delta state from the large-object heap')
inventory = mn['inventory']
check(inventory == dict(entries=4, idle=1, bytes=mn['deltaStateBytes']) and mc['inventory'] is None,
      'GPU inventory: entries, the idle one and the delta bytes, back to zero after the release (checked in the program)')

# Vulkan: identical element state, values, references, change log and exceptions; less heap per array.
vc, vn, vw = reports['vkControl'], reports['vkCandidate'], reports['vkWrong']
check(vc['variant'] == 'control' and vn['variant'] == vw['variant'] == 'candidate', 'probe variants')
check(len(vc['scenarios']) == len(vn['scenarios']) == 48, 'Vulkan scenario inventory')
for old, new in zip(vc['scenarios'], vn['scenarios'], strict=True):
    check({k: v for k, v in old.items() if k != 'digest'} == {k: v for k, v in new.items() if k != 'digest'}, 'Vulkan scenario pairing')
    check(old['digest'] == new['digest'], 'element state, descriptor values, references or change log differ: ' + json.dumps(new))
check(len({s['digest'] for s in vc['scenarios']}) == 48, 'scenario digests are distinct')
wrong = sum(old['digest'] != bad['digest'] for old, bad in zip(vc['scenarios'], vw['scenarios'], strict=True))
check(wrong > 0, 'a wrong candidate changes the digests')
check(vc['exceptions'] == vn['exceptions'] and vc['exceptions']['bufferSampler'] == 'NullReferenceException' and
      vc['exceptions']['textureViewBeyond'] == 'IndexOutOfRangeException', 'same exceptions as delivered: ' + json.dumps(vn['exceptions']))
ac, an = vc['measure'], vn['measure']
check(ac['arrays'] == an['arrays'] == 3 and ac['length'] == an['length'] == 524288, 'Vulkan measure shape')
check(ac['lohPerArrayBytes'] >= 24 * MiB and an['lohPerArrayBytes'] >= 16 * MiB, 'element arrays measured in the heap')
vulkan_saved = ac['lohFilledBytes'] - an['lohFilledBytes']
check(vulkan_saved >= 3 * 8 * MiB, 'the live large-object heap falls by 8 MiB per 524288-element texture array: ' + str(vulkan_saved))
check(ac['lohAfterReleaseBytes'] <= 0 and an['lohAfterReleaseBytes'] <= 0, 'disposed and dropped arrays leave the heap')
check(an['inventoryArrays'] == 3 and an['inventoryBytes'] == 3 * 524288 * (8 + 24) and an['disposedArrays'] == 0 and
      an['disposedBytes'] == 0, 'backend inventory: the arrays over 4096 elements and their bytes, zero after Dispose')
check(an['line'] == '; bindless pool arrays held: entries 0 (not updated for 30 s or more 0), per-element delta state 0.0 MiB; '
                    'backend texture arrays over 4096 elements 3, element arrays 48.0 MiB', 'journal text: ' + str(an['line']))

per_entry_control = mc['deltaStateBytes'] // 3 + ac['lohPerArrayBytes']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
inputs = ['build-utils/melonx/adapt_bindless_retention.py', 'build-utils/melonx/adapt_session.py', 'test/melonx_bindless_retention_test.py',
          'test/melonx_bindless_retention/GpuFixture.cs', 'test/melonx_bindless_retention/VulkanProbe.cs',
          'test/melonx_array_rebuild_allocations/Program.cs', 'test/melonx_adapter_control.py']
measurements = dict(
    perEntry524288=dict(gpuDeltaStateBytes=524288 * 28, vulkanControlHeapBytes=ac['lohPerArrayBytes'],
                        vulkanCandidateHeapBytes=an['lohPerArrayBytes'], controlBytes=per_entry_control),
    gpu=dict(control={k: mc[k] for k in mc if k != 'inventory'}, candidate=mn, liveHeapSavedBytes=gpu_saved),
    vulkan=dict(control=ac, candidate=an, liveHeapSavedBytes=vulkan_saved),
    companionCallsRemoved=companion['control'],
    expectedDevice='Three 524288-element pool texture entries per Hogwarts session (core-performance: one creation burst of '
                   '3 x 524288 + 4096 full elements with 80-92 MiB on the render thread): about 114 MiB of element arrays '
                   '(14 MiB GPU + 24 MiB Vulkan each) plus kept rebuild scratch; this change removes 3 x 8 MiB of Vulkan '
                   'arrays and the kept pool-sized sampler arrays (8 MiB measured without render-thread lag, up to 16 MiB '
                   'with it), about 32-40 MiB of the 250-282 MiB live LOH.')
receipt = dict(result='passed', checks=checks, programChecks=dict(gpuControl=gc_['checks'], gpuCandidate=gn['checks'],
                                                                   vulkanControl=vc['checks'], vulkanCandidate=vn['checks']),
               measurements=measurements, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'basePreparation',
               postimages={p: sha(FINAL_SOURCE / p) for p in BASELINE} if FINAL_PREPARATION else {},
               sdk=sdk, physicalDeviceTested=False, productionGpuAssemblyBuilt=True, productionVulkanAssemblyBuilt=True,
               evictionImplemented=False, sourceBaseline=BASELINE, compiledGpuFixtureSources=compiled,
               inputs={p: sha(ROOT / p) for p in inputs},
               limitation='Host measurement with doubles for pools, textures and the GPU-side backend, and device-less Vulkan '
                          'views and samplers; the delivered walk (GetImageInfos) and barrier queueing need a command buffer '
                          'and are bound statically. Native MoltenVK descriptor memory, MaxSlots and the 250 MiB of live LOH '
                          'present before any array (other owners) are not changed. No eviction: every device entry measured '
                          'is in use. Not measured on an iPhone.')
out = ROOT / 'dist/melonx/bindless-retention-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(f"GPU: kept sampler arrays {mc['keptAfterRebuilds']['ISampler']} -> {mn['keptAfterRebuilds']['ISampler']} bytes; "
      f"live LOH after creation and rebuilds {mc['lohAfterRebuildsBytes']} -> {mn['lohAfterRebuildsBytes']}; "
      f"creation allocates {mc['creationAllocatedBytes']} -> {mn['creationAllocatedBytes']}")
print(f"Vulkan: live LOH per 524288-element array {ac['lohPerArrayBytes']} -> {an['lohPerArrayBytes']} bytes; "
      f"wrong candidate changed {wrong} of 48 digests")
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
