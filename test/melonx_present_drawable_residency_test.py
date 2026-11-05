#!/usr/bin/env python3
"""The drawable written through a render pass, not a compute descriptor (adapt_present_drawable_residency).

Usage: melonx_present_drawable_residency_test.py <Core 656 prepared MeloNX tree>
       melonx_present_drawable_residency_test.py <control> --candidate-source <final preparation containing the adapter>
Optional: MOLTENVK_SOURCE=<MoltenVK v1.4.2 checkout's MoltenVK/MoltenVK directory> to bind the mechanism in its sources.

Applies the adapter to a copy of the Core 656 preparation and builds the production Ryujinx.Graphics.Vulkan assembly.
Static checks bind that Window.cs equals the preparation once the adapter's replacements are undone (nothing else
changes), that no swapchain image view is handed to a compute writer any more (PresentCopy, a scaling filter), that
the default path draws into the swapchain view with BlitColor with PresentCopy's regions and filter, that a scaling
filter writes a texture Ryujinx creates and BlitColor copies it into the drawable, that MetalFX and the clear are
unchanged, and that the one journal line names the path. In the preparation it binds why: PresentCopy writes its
destination as a storage image through a minimal-layout program (no push descriptors). With MOLTENVK_SOURCE, in
MoltenVK v1.4.2: no UseResource for argument buffer descriptors once a residency set exists, a residency set on iOS 18,
the presentable image's texture is the drawable's, and only MoltenVK's own allocations are made resident. No device.
Writes dist/melonx/present-drawable-residency-checks.json.
"""
from pathlib import Path
import hashlib, json, os, re, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, use_authenticated_libhac_feed  # noqa: E402
_HOLD = []
FINAL_SOURCE = SOURCE
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_present_drawable_residency', _HOLD)
import adapt_present_drawable_residency  # noqa: E402
from adapt_present_drawable_residency import apply, BASELINE  # noqa: E402

VULKAN = 'src/Ryujinx.Graphics.Vulkan/'
WINDOW = VULKAN + 'Window.cs'
DOTNET = os.environ.get('DOTNET', 'dotnet')
MOLTENVK = os.environ.get('MOLTENVK_SOURCE')
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


for name, expected in BASELINE.items():
    check(hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected, 'not the Core 656 preparation: ' + name)

# The adapter's replacements, recorded, to undo them on the candidate.
replacements = []
original_once = adapt_present_drawable_residency.once
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
with tempfile.TemporaryDirectory(prefix='melonx-present-residency-') as temporary:
    work = Path(temporary).resolve() / 'candidate'
    shutil.copytree(SOURCE, work, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
    use_authenticated_libhac_feed(work, ROOT)

    def recording_once(path, old, new):
        replacements.append((old, new))
        original_once(path, old, new)

    adapt_present_drawable_residency.once = recording_once
    try:
        changed = apply(work)
    finally:
        adapt_present_drawable_residency.once = original_once
    check(sorted(str(p.relative_to(work)) for p in changed) == sorted(BASELINE), 'adapter changed other files')
    if FINAL_PREPARATION:
        for name in BASELINE:
            check((work / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)
    control = (SOURCE / WINDOW).read_text(encoding='utf-8-sig')
    window = (work / WINDOW).read_text(encoding='utf-8-sig')
    undone = window
    for old, new in reversed(replacements):
        check(undone.count(new) == 1, 'each replacement once: ' + new[:60])
        undone = undone.replace(new, old)
    check(undone == control, 'Window.cs is the preparation but the adapter\'s four replacements')

    present = member(window, 'public unsafe override void Present(') if 'public unsafe override void Present(' in window \
        else member(window, 'override void Present(')
    present_control = member(control, 'public unsafe override void Present(') if 'public unsafe override void Present(' in control \
        else member(control, 'override void Present(')
    attachment = '_swapchainImageViews[nextImage].GetImageViewForAttachment()'
    check(present_control.count(attachment) == 2 and 'HelperShader.PresentCopy(' in present_control,
          'control: PresentCopy and the scaling filter write the swapchain view through a descriptor')
    check(present.count(attachment) == 0 and 'PresentCopy(' not in window,
          'candidate: no swapchain image view handed to a compute writer')
    blits = re.findall(r'_gd\.HelperShader\.BlitColor\(\s*_gd,\s*cbs,\s*(\w+),\s*_swapchainImageViews\[nextImage\],\s*(\w+),\s*(\w+),\s*'
                       r'(\w+),\s*true\);', present)
    check(blits == [('scalingTarget', 'wholeImage', 'wholeImage', 'false'),
                    ('view', 'sourceRegion', 'destinationRegion', '_isLinear'),
                    ('view', 'sourceRegion', 'destinationRegion', '_isLinear')],
          'BlitColor into the swapchain view: scaling target, default path, multisampled path: ' + str(blits))
    check(re.search(r'_scalingFilter\.Run\(\s*view,\s*cbs,\s*scalingTarget\.GetImageViewForAttachment\(\),\s*VkFormat\.R8G8B8A8Unorm,\s*'
                    r'_width,\s*_height,\s*sourceRegion,\s*new Extents2D\(dstX0, dstY0, dstX1, dstY1\)\s*\);', present) is not None,
          'the scaling filter writes the texture of ours with the same regions')
    check(present.index('_scalingFilter.Run(') < present.index('scalingTarget,\n'), 'filter before its copy into the drawable')
    check('ClearSwapchain(cbs.CommandBuffer, swapchainImage);' in present and present.count('_metalFxScalingFilter?.Prepare(') == 1 and
          present_control.count('_metalFxScalingFilter?.Prepare(') == 1, 'MetalFX and the clear unchanged')
    getter = member(window, 'private TextureView GetPresentScalingTarget()')
    check('_gd.CreateTexture(new TextureCreateInfo(' in getter and 'Ryujinx.Graphics.GAL.Format.R8G8B8A8Unorm' in getter and
          'Target.Texture2D' in getter and '_presentScalingTarget?.Dispose();' in getter and
          '_presentScalingTarget.Width != _width || _presentScalingTarget.Height != _height' in getter,
          'a 2D RGBA8 texture of the swapchain size, re-created when the size changes')
    dispose = member(window, 'protected virtual void Dispose(bool disposing)')
    check('_presentScalingTarget?.Dispose();' in dispose, 'disposed with the window')
    check(present.count('(adapt_present_drawable_residency)");') == 1 and '_presentPathLogged = true;' in present and
          'OperatingSystem.IsIOS()' in present, 'one journal line per window on iOS')

    # Why, in the preparation: PresentCopy is a compute write of a storage image, its program has a minimal layout.
    helper = (SOURCE / VULKAN / 'HelperShader.cs').read_text(encoding='utf-8-sig')
    copy = member(helper, 'public void PresentCopy(')
    check('_pipeline.SetImage(0, dst);' in copy and '_pipeline.DispatchCompute(' in copy, 'PresentCopy: storage image, compute')
    check(re.search(r'_programPresentCopy = gd\.CreateProgramWithMinimalLayout\(', helper) is not None and
          '.Add(ResourceStages.Compute, ResourceType.Image, 0, true).Build();' in helper, 'PresentCopy: minimal layout, image')
    renderer = (SOURCE / VULKAN / 'VulkanRenderer.cs').read_text(encoding='utf-8-sig')
    check('isMinimal: true' in member(renderer, 'internal ShaderCollection CreateProgramWithMinimalLayout('), 'minimal programs')
    collection = (SOURCE / VULKAN / 'ShaderCollection.cs').read_text(encoding='utf-8-sig')
    check(re.search(r'bool usePushDescriptors = !isMinimal &&', collection) is not None, 'minimal programs use no push descriptors')
    blit = member(helper, 'public void BlitColor(')
    check('SetRenderTarget' in blit or 'SetRenderTargets' in blit, 'BlitColor renders into its destination as an attachment')

    result = subprocess.run([DOTNET, 'build', str(work / (VULKAN + 'Ryujinx.Graphics.Vulkan.csproj')), '-c', 'Release', '-nologo',
                             '-m:1', '-p:NuGetAudit=false'], capture_output=True, text=True, timeout=2400, env=environment, cwd=work)
    if result.returncode:
        print(result.stdout[-6000:], result.stderr[-2000:], flush=True)
    check(result.returncode == 0, 'production Ryujinx.Graphics.Vulkan builds with the adapter')

moltenvk = None
if MOLTENVK:
    mvk = Path(MOLTENVK)
    pipeline = (mvk / 'GPUObjects/MVKPipeline.mm').read_text()
    check(re.search(r'\} else if \(!_device->hasResidencySet\(\)\) \{\s*MVKDescriptorBindOperationCode useTex', pipeline) is not None,
          'MoltenVK: no UseResource for argument buffer descriptors once a residency set exists')
    device = (mvk / 'GPUObjects/MVKDevice.mm').read_text()
    check('_metalFeatures.residencySets = mvkOSVersionIsAtLeast(15.0, 18.0, 2.0);' in device and
          'addResidencySet' in (mvk / 'GPUObjects/MVKQueue.mm').read_text(), 'MoltenVK: a residency set on iOS 18, on the queue')
    image = (mvk / 'GPUObjects/MVKImage.mm').read_text()
    check(re.search(r'id<MTLTexture> MVKPresentableSwapchainImage::getMTLTexture\(uint8_t planeIndex\) \{\s*'
                    r'return _mtlTextureHeadless \? _mtlTextureHeadless : getCAMetalDrawable\(\)\.texture;', image) is not None,
          'MoltenVK: a presentable image\'s texture is the drawable\'s')
    drawable = member(image, 'id<CAMetalDrawable> MVKPresentableSwapchainImage::getCAMetalDrawable()')
    check('makeResident' not in drawable, 'MoltenVK: the drawable is not made resident')
    moltenvk = {'checked': True, 'path': str(mvk)}

inputs = ['build-utils/melonx/adapt_present_drawable_residency.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_present_drawable_residency_test.py']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core656Preparation',
               postimages={p: hashlib.sha256((FINAL_SOURCE / p).read_bytes()).hexdigest() for p in BASELINE} if FINAL_PREPARATION else {},
               moltenvkSource=moltenvk, sdk=sdk, physicalDeviceTested=False, productionVulkanAssemblyBuilt=True,
               sourceBaseline=BASELINE, inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               limitation='Whether the image comes back on iOS 18 and later is known only from a device run.')
out = ROOT / 'dist/melonx/present-drawable-residency-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
