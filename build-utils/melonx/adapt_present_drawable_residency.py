"""Write the game image into the iOS drawable through a render pass, so it reaches the screen with MoltenVK 1.4.2.

IPA 657, 5 November 2026, maintainer's iPhone on iOS 27 beta 1, Hogwarts Legacy (private logs and a video filmed with
another device, not in the repository): the screen stays black at launch or freezes on one image while the game keeps
running. The performance journal shows 30 presents a second, each one shown on glass (CAMetalDrawable presentedTime at
33 ms intervals), the guest presenting 30 frames a second from its three GPU-rendered buffers (Present sources: GPU
modified, from guest memory 0) and drawing about 555 draws a frame; the game audio goes on. A host pause, or an iOS
screen recording, brings the image back; with a recording running from launch there is no fault. The maintainer
dates the fault to the change from the MeloNX standalone MoltenVK (a fork reporting 1.4.0, no residency set on iOS) to
Khronos MoltenVK v1.4.2 (pinned in build-utils/melonx/moltenvk-rebuild-pin.json), and keeps v1.4.2.

Mechanism (read in the Core 656 preparation and in MoltenVK v1.4.2, commit db660224):
- Window.Present (Vulkan) writes the final image into the swapchain image with HelperShader.PresentCopy, a compute
  shader that binds the swapchain image view as a storage image (SetImage). The program is created with a minimal
  layout (CreateProgramWithMinimalLayout: isMinimal, so no push descriptors): the image goes through an ordinary
  descriptor set, which MoltenVK encodes in a Metal argument buffer (Apple GPUs are argument buffer tier 2). The
  scaling filters (FSR, Area) write the swapchain image the same way.
- MoltenVK v1.4.2 creates an MTLResidencySet on iOS 18 and later (MVKDevice: residencySets on Apple6+, iOS 18.0) and
  adds it to its command queues; MVKPipeline then emits no UseResource operation for any descriptor of an argument
  buffer layout when the device has a residency set (`else if (!_device->hasResidencySet())`): residency is left to
  the set. Only textures and buffers MoltenVK allocates are added to it (makeResident). A swapchain image's texture is
  the CAMetalDrawable's texture (MVKPresentableSwapchainImage::getMTLTexture returns getCAMetalDrawable().texture):
  never added. Metal requires a resource reached through an argument buffer to be resident (useResource or a residency
  set); otherwise the access is undefined. So the compute write of each frame into the drawable is not guaranteed to
  land: the drawable keeps what it held, and Core Animation shows it on time. A fresh drawable is black (the launch),
  a reused one holds an older frame (the freeze, the older frames and black frames seen since IPA 643). The MeloNX
  fork has no residency set on iOS: every descriptor resource gets useResource, the write lands.
- A render pass attachment is resident by Metal's own rule (resources bound to an encoder directly, attachments
  included, need no useResource): HelperShader.BlitColor draws into the swapchain view as a color attachment. It is
  the path upstream Ryujinx presents through, and the one this Window already takes for a multisampled image.

Change (Window.cs only):
- the default path (no MetalFX, no scaling filter) draws the image into the drawable with BlitColor, same source and
  destination regions, same filter, alpha forced to 1 (the layer is opaque), instead of PresentCopy;
- a scaling filter (FSR, Area) writes a 2D RGBA8 texture of the swapchain size that Ryujinx creates (allocated by
  MoltenVK, so in its residency set), then BlitColor copies that texture into the drawable as an attachment (whole
  image, nearest); the texture is re-created when the size changes and disposed with the window;
- MetalFX (native Metal, which binds its output directly) and the clear are unchanged;
- one journal line per window on iOS at the first present names the path taken.
Not measured on an iPhone. Fail closed on drift: Window.cs must be the Core 656 preparation's (after
adapt_present_pacing).
"""
import hashlib
from adapt_session import once

BASELINE = {
    'src/Ryujinx.Graphics.Vulkan/Window.cs': 'a6bb8b91e396028561ce74f76b29cfb34a1f995e86a99dec29afeea81f63174e',
}


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    window = paths['src/Ryujinx.Graphics.Vulkan/Window.cs']

    once(window, '''        private bool _colorSpacePassthroughEnabled;
''', '''        private bool _colorSpacePassthroughEnabled;

        // RewindBox (adapt_present_drawable_residency): what a scaling filter writes before the drawable copy, and the
        // once-per-window journal line of the present path.
        private TextureView _presentScalingTarget;
        private bool _presentPathLogged;
''')

    once(window, '''        private static SurfaceFormatKHR ChooseSwapSurfaceFormat(''', '''        // RewindBox (adapt_present_drawable_residency): a texture Ryujinx creates is allocated by MoltenVK, hence in its
        // residency set, and may be written by a compute shader through a descriptor; the drawable may not.
        private TextureView GetPresentScalingTarget()
        {
            if (_presentScalingTarget == null || _presentScalingTarget.Width != _width || _presentScalingTarget.Height != _height)
            {
                _presentScalingTarget?.Dispose();
                _presentScalingTarget = (TextureView)_gd.CreateTexture(new TextureCreateInfo(
                    _width,
                    _height,
                    1,
                    1,
                    1,
                    1,
                    1,
                    4,
                    Ryujinx.Graphics.GAL.Format.R8G8B8A8Unorm,
                    DepthStencilMode.Depth,
                    Target.Texture2D,
                    SwizzleComponent.Red,
                    SwizzleComponent.Green,
                    SwizzleComponent.Blue,
                    SwizzleComponent.Alpha));
            }

            return _presentScalingTarget;
        }

        private static SurfaceFormatKHR ChooseSwapSurfaceFormat(''')

    once(window, '''            if (metalFxPrepared)
            {
                ClearSwapchain(cbs.CommandBuffer, swapchainImage);
            }
            else if (_scalingFilter != null)
            {
                _scalingFilter.Run(
                    view,
                    cbs,
                    _swapchainImageViews[nextImage].GetImageViewForAttachment(),
                    _format,
                    _width,
                    _height,
                    sourceRegion,
                    new Extents2D(dstX0, dstY0, dstX1, dstY1)
                    );
            }
            else if (!view.Info.Target.IsMultisample)
            {
                _gd.HelperShader.PresentCopy(
                    _gd,
                    cbs,
                    view,
                    _swapchainImageViews[nextImage].GetImageViewForAttachment(),
                    sourceRegion,
                    destinationRegion,
                    _isLinear);
            }
''', '''            // RewindBox (adapt_present_drawable_residency): MoltenVK 1.4.2 on iOS 18 and later relies on its residency set
            // for every resource of an argument buffer and never adds the CAMetalLayer drawable to it, so a compute write
            // of the drawable through a storage image descriptor may not land (black launch, frozen or older frames).
            // The drawable is written as a render pass color attachment instead, which Metal always makes resident.
            if (!_presentPathLogged && OperatingSystem.IsIOS())
            {
                _presentPathLogged = true;
                Ryujinx.Common.Logging.Logger.Warning?.Print(Ryujinx.Common.Logging.LogClass.Gpu, "Present path: " +
                    (metalFxPrepared ? "MetalFX writes the drawable (native Metal)" : _scalingFilter != null
                        ? "scaling filter into a texture of ours, then a render pass into the drawable"
                        : "render pass into the drawable (color attachment), no compute write of the drawable") +
                    " (adapt_present_drawable_residency)");
            }

            if (metalFxPrepared)
            {
                ClearSwapchain(cbs.CommandBuffer, swapchainImage);
            }
            else if (_scalingFilter != null)
            {
                TextureView scalingTarget = GetPresentScalingTarget();
                Extents2D wholeImage = new(0, 0, _width, _height);

                _scalingFilter.Run(
                    view,
                    cbs,
                    scalingTarget.GetImageViewForAttachment(),
                    VkFormat.R8G8B8A8Unorm,
                    _width,
                    _height,
                    sourceRegion,
                    new Extents2D(dstX0, dstY0, dstX1, dstY1)
                    );

                _gd.HelperShader.BlitColor(
                    _gd,
                    cbs,
                    scalingTarget,
                    _swapchainImageViews[nextImage],
                    wholeImage,
                    wholeImage,
                    false,
                    true);
            }
            else if (!view.Info.Target.IsMultisample)
            {
                _gd.HelperShader.BlitColor(
                    _gd,
                    cbs,
                    view,
                    _swapchainImageViews[nextImage],
                    sourceRegion,
                    destinationRegion,
                    _isLinear,
                    true);
            }
''')

    once(window, '''                _effect?.Dispose();
                _scalingFilter?.Dispose();
                _metalFxScalingFilter?.Dispose();
            }
        }
''', '''                _effect?.Dispose();
                _scalingFilter?.Dispose();
                _metalFxScalingFilter?.Dispose();
                _presentScalingTarget?.Dispose();
            }
        }
''')
    return list(paths.values())
