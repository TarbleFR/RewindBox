"""Size a framebuffer without attachments to the viewports, not 1x1.

FINAL FANTASY TACTICS - The Ivalice Chronicles (010038b015560000) shows a
black screen with sound on Ryujinx 1.3.3 (Ryubing issue 103). A comment there
(August 2026) traced it to passes that bind no color, depth or stencil target,
whose fragment shader reads intermediate textures: the Vulkan backend gives
such a framebuffer a 1x1 extent (FramebufferParams), so only the fragment at
(0, 0) runs and the game's output stays empty. The pinned MeloNX source has
the same code. On hardware nothing bounds such a pass but the guest's screen
scissor and viewports.

- FramebufferParams.GrowWithoutAttachments: a framebuffer without attachments
  grows to a given extent (never shrinks while bound); one with attachments is
  untouched.
- PipelineBase: when such a framebuffer is bound, and whenever the viewports
  change while it is, it covers the viewports' extent, clamped to the device's
  maxFramebufferWidth/Height (VulkanRenderer). A larger extent recreates the
  null render pass's framebuffer, which RenderPassHolder already caches per
  size; the render pass and pipelines stay the same.

Passes with any attachment, the render pass, pipeline state and every other
size are unchanged. Fail closed on drift.
"""
from adapt_session import once


def apply(source):
    vulkan = source / 'src/Ryujinx.Graphics.Vulkan'
    framebuffer = vulkan / 'FramebufferParams.cs'
    once(framebuffer, '''        public int ColorAttachmentsCount => AttachmentsCount - (HasDepthStencil ? 1 : 0);
''', '''        public int ColorAttachmentsCount => AttachmentsCount - (HasDepthStencil ? 1 : 0);

        // Only a framebuffer without attachments: its extent bounds nothing but
        // rasterization (see PipelineBase.FitAttachmentlessFramebuffer).
        public bool GrowWithoutAttachments(uint width, uint height)
        {
            if (AttachmentsCount != 0 || (width <= Width && height <= Height))
            {
                return false;
            }

            Width = Math.Max(Width, width);
            Height = Math.Max(Height, height);

            return true;
        }
''')
    renderer = vulkan / 'VulkanRenderer.cs'
    once(renderer, '''        private VulkanPhysicalDevice _physicalDevice;
''', '''        private VulkanPhysicalDevice _physicalDevice;

        internal uint MaxFramebufferWidth => _physicalDevice.PhysicalDeviceProperties.Limits.MaxFramebufferWidth;
        internal uint MaxFramebufferHeight => _physicalDevice.PhysicalDeviceProperties.Limits.MaxFramebufferHeight;
''')
    pipeline = vulkan / 'PipelineBase.cs'
    once(pipeline, '''            FramebufferParams = FramebufferParams?.Update(colors, depthStencil) ?? new FramebufferParams(Device, colors, depthStencil);
''', '''            FramebufferParams = FramebufferParams?.Update(colors, depthStencil) ?? new FramebufferParams(Device, colors, depthStencil);
            FitAttachmentlessFramebuffer();
''')
    once(pipeline, '''            _newState.ViewportsCount = (uint)count;
            SignalStateChange();
        }
''', '''            _newState.ViewportsCount = (uint)count;
            SignalStateChange();

            if (FitAttachmentlessFramebuffer())
            {
                CreateRenderPass();
            }
        }
''')
    once(pipeline, '''        protected unsafe void CreateRenderPass()
''', '''        // A pass without attachments used a 1x1 framebuffer, so one fragment
        // ran. Cover the viewports, as only the guest's screen scissor and
        // viewports bound such a pass on hardware.
        private bool FitAttachmentlessFramebuffer()
        {
            if (FramebufferParams == null || FramebufferParams.AttachmentsCount != 0)
            {
                return false;
            }

            float right = 1f;
            float bottom = 1f;

            for (int i = 0; i < DynamicState.ViewportsCount; i++)
            {
                Silk.NET.Vulkan.Viewport viewport = DynamicState.Viewports[i];
                float x = viewport.X + viewport.Width;
                float y = viewport.Y + viewport.Height;

                if (float.IsFinite(x) && float.IsFinite(y))
                {
                    right = Math.Max(right, Math.Max(viewport.X, x));
                    bottom = Math.Max(bottom, Math.Max(viewport.Y, y));
                }
            }

            return FramebufferParams.GrowWithoutAttachments(
                (uint)Math.Min(MathF.Ceiling(right), Gd.MaxFramebufferWidth),
                (uint)Math.Min(MathF.Ceiling(bottom), Gd.MaxFramebufferHeight));
        }

        protected unsafe void CreateRenderPass()
''')
    return [framebuffer, renderer, pipeline]
