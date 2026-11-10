"""Async shaders: a draw is skipped for a background compile only into targets the frame regenerates (Core 689).

IPA 688 on the device (Hogwarts Legacy, PID 29464, 7 November 2026, Core 687, per-game "Async shaders" on; private
journals and a screenshot): fewer stutters than without async shaders (game FPS mean 25.2 against 20.7, frame time p95
67 ms against 83 ms), but texture corruption (magenta and yellow areas over the castle staircase). With async shaders a
draw whose program is still compiling is skipped (PipelineBase.PrepareGraphicsDraw, "not ready": 5 934 in this
session). The only guard was VulkanRenderer.IsCriticalOffscreenTarget: an offscreen target waits for the complete
pipeline only until its first render pass without a skipped draw (TextureStorage.HasCompleteRenderPass). A target the
game draws into once and keeps (a cache, a capture, an atlas filled tile by tile) then keeps the hole of a skipped draw
in every later frame that samples it; Unreal Engine also reuses pooled render targets, so such a hole shows other
passes' data.

Change (every title, only when a draw may be skipped, which needs async shaders on): a draw may be skipped only when
its framebuffer is regenerated each frame: every attachment had a render pass in the previous frame, and one of them
(colour or depth) was cleared whole in the current frame (a clear whose rectangle covers the framebuffer and all its
layers, depth aspect for a depth target). Into any other offscreen target the draw waits for its program and pipeline
(the existing complete-pipeline path, with its promoted compilation), as an incomplete target already did. Targets
shown by the swapchain stay skippable, as before. Frames are counted at each Window.Present on the render thread,
where passes, clears and draws are recorded too, so no lock is added. The "Vulkan render stages" line ends with
"; async draws held for their program N (ms)". No skip is added anywhere; without async shaders nothing changes. Not
measured on an iPhone. Fail closed on drift: the five files must be the Core 687 preparation's.
"""
import hashlib
from adapt_session import once

VULKAN = 'src/Ryujinx.Graphics.Vulkan/'
RENDERER = VULKAN + 'VulkanRenderer.cs'
WINDOW = VULKAN + 'Window.cs'
STORAGE = VULKAN + 'TextureStorage.cs'
FRAMEBUFFER = VULKAN + 'FramebufferParams.cs'
PIPELINE = VULKAN + 'PipelineBase.cs'
BASELINE = {
    RENDERER: 'ba9f2ab96d95fff0a26d166123dd050f4ba928f556a305d66d2baf7818b36f03',
    WINDOW: '97b45de736ab2db2f8177fd40df988246e65cd5bb14e8a956b4480a31fc4eddf',
    STORAGE: '0ca96c7ee75598e65f8cc755feef9872b09671b2c89c64d3428b61f772d1d242',
    FRAMEBUFFER: 'a159f3430982d96ff0b33395b7953c9b7cb21c592ef10ace062928da6c879834',
    PIPELINE: 'ab0365d59f9838ef9970f09241f31d4bd58fa0a014096ad493aedc0ba352660e',
}

CRITICAL_ANCHOR = '''        internal bool IsCriticalOffscreenTarget(FramebufferParams framebuffer)
'''
CRITICAL_FIELD = '''        // RewindBox (adapt_async_regenerated_targets): frames presented, counted on the render thread (Window.Present), from 1.
        internal ulong AsyncFrame = 1;

        internal bool IsCriticalOffscreenTarget(FramebufferParams framebuffer)
'''
CRITICAL_OLD = '''            return framebuffer.HasIncompleteAttachments();
'''
CRITICAL_NEW = '''            // RewindBox (adapt_async_regenerated_targets): a skipped draw is redrawn by the next frames only in a target the
            // frame regenerates; any other offscreen target would keep the hole, so its draws wait for their pipeline.
            return framebuffer.HasIncompleteAttachments() || !framebuffer.IsRegeneratedEachFrame(AsyncFrame);
'''

PRESENT_OLD = '''            _gd.RegisterPresentationTexture(view);
'''
PRESENT_NEW = '''            _gd.RegisterPresentationTexture(view);
            _gd.AsyncFrame++; // RewindBox (adapt_async_regenerated_targets)
'''

STORAGE_OLD = '''        public void MarkRenderPassComplete()
        {
            _hasCompleteRenderPass = true;
        }
'''
STORAGE_NEW = '''        public void MarkRenderPassComplete()
        {
            _hasCompleteRenderPass = true;
        }

        // RewindBox (adapt_async_regenerated_targets): the last frame with a render pass on this storage, whether the frame
        // before it had one too, and the last frame that cleared it whole. Render thread only. Frame 0 is "never".
        private ulong _asyncPassFrame;
        private bool _asyncPassPrevious;
        private ulong _asyncClearFrame;

        public void NoteAsyncPass(ulong frame)
        {
            if (_asyncPassFrame != frame)
            {
                _asyncPassPrevious = _asyncPassFrame != 0 && _asyncPassFrame + 1 == frame;
                _asyncPassFrame = frame;
            }
        }

        public void NoteAsyncFullClear(ulong frame)
        {
            _asyncClearFrame = frame;
        }

        public bool AsyncPassInPreviousFrame(ulong frame)
        {
            return _asyncPassFrame == frame ? _asyncPassPrevious : _asyncPassFrame != 0 && _asyncPassFrame + 1 == frame;
        }

        public bool AsyncClearedWholeIn(ulong frame)
        {
            return _asyncClearFrame == frame;
        }
'''

FRAMEBUFFER_OLD = '''        public void MarkAttachmentsComplete()
        {
'''
FRAMEBUFFER_NEW = '''        // RewindBox (adapt_async_regenerated_targets): every attachment had a render pass in the previous frame, and one of
        // them was cleared whole in this one.
        public bool IsRegeneratedEachFrame(ulong frame)
        {
            bool cleared = false;

            if (_colors != null)
            {
                int count = ColorAttachmentsCount;

                for (int i = 0; i < count; i++)
                {
                    TextureStorage storage = _colors[i].Storage;

                    if (storage != null)
                    {
                        if (!storage.AsyncPassInPreviousFrame(frame))
                        {
                            return false;
                        }

                        cleared |= storage.AsyncClearedWholeIn(frame);
                    }
                }
            }

            if (_depthStencil?.Storage is TextureStorage depthStorage)
            {
                if (!depthStorage.AsyncPassInPreviousFrame(frame))
                {
                    return false;
                }

                cleared |= depthStorage.AsyncClearedWholeIn(frame);
            }

            return cleared;
        }

        public void NoteAsyncPass(ulong frame)
        {
            if (_colors != null)
            {
                int count = ColorAttachmentsCount;

                for (int i = 0; i < count; i++)
                {
                    _colors[i].Storage?.NoteAsyncPass(frame);
                }
            }

            _depthStencil?.Storage?.NoteAsyncPass(frame);
        }

        public bool ClearsWhole(in ClearRect clearRect)
        {
            return clearRect.Rect.Offset.X <= 0 && clearRect.Rect.Offset.Y <= 0 &&
                clearRect.Rect.Extent.Width >= Width && clearRect.Rect.Extent.Height >= Height &&
                clearRect.BaseArrayLayer == 0 && clearRect.LayerCount >= Layers;
        }

        public void MarkAttachmentsComplete()
        {
'''

TIMER_OLD = '''        public static long PrepareTicks, Prepares, NotReady;
'''
TIMER_NEW = '''        public static long PrepareTicks, Prepares, NotReady;
        public static long AsyncHeld, AsyncHeldTicks; // RewindBox (adapt_async_regenerated_targets)
'''
LOG_OLD = '''                " ms (acquire " + Ms(_acquireTicks) + " ms, queue present " + Ms(_queuePresentTicks) + " ms)";
'''
LOG_NEW = '''                " ms (acquire " + Ms(_acquireTicks) + " ms, queue present " + Ms(_queuePresentTicks) + " ms)" +
                "; async draws held for their program " + AsyncHeld + " (" + Ms(AsyncHeldTicks) + " ms)";
            AsyncHeld = AsyncHeldTicks = 0;
'''

PREPARE_OLD = '''            if (canSkipForBackgroundCompile && !UpdateProgramStagesIfReady(blocking: false))
            {
                if (!requiresCompletePipeline ||
                    !_program.WaitForShaderModules(Timeout.Infinite) ||
                    !UpdateProgramStagesIfReady(blocking: false))
                {
'''
PREPARE_NEW = '''            if (canSkipForBackgroundCompile && !UpdateProgramStagesIfReady(blocking: false))
            {
                // RewindBox (adapt_async_regenerated_targets): a held draw's wait for its program is counted and timed.
                long heldStart = requiresCompletePipeline ? RenderStageTimer.Now() : 0;
                bool held = requiresCompletePipeline &&
                    _program.WaitForShaderModules(Timeout.Infinite) &&
                    UpdateProgramStagesIfReady(blocking: false);

                if (requiresCompletePipeline)
                {
                    RenderStageTimer.AsyncHeld++;
                    RenderStageTimer.AsyncHeldTicks += RenderStageTimer.Now() - heldStart;
                }

                if (!held)
                {
'''

PASS_OLD = '''                Gd.Api.CmdBeginRenderPass(CommandBuffer, in renderPassBeginInfo, SubpassContents.Inline);
                RenderPassActive = true;
'''
PASS_NEW = '''                Gd.Api.CmdBeginRenderPass(CommandBuffer, in renderPassBeginInfo, SubpassContents.Inline);
                RenderPassActive = true;
                FramebufferParams.NoteAsyncPass(Gd.AsyncFrame); // RewindBox (adapt_async_regenerated_targets)
'''

COLOR_CLEAR_OLD = '''            ClearAttachment attachment = new(ImageAspectFlags.ColorBit, (uint)index, clearValue);
            ClearRect clearRect = FramebufferParams.GetClearRect(ClearScissor, layer, layerCount);

            Gd.Api.CmdClearAttachments(CommandBuffer, 1, &attachment, 1, &clearRect);
'''
COLOR_CLEAR_NEW = '''            ClearAttachment attachment = new(ImageAspectFlags.ColorBit, (uint)index, clearValue);
            ClearRect clearRect = FramebufferParams.GetClearRect(ClearScissor, layer, layerCount);

            Gd.Api.CmdClearAttachments(CommandBuffer, 1, &attachment, 1, &clearRect);

            // RewindBox (adapt_async_regenerated_targets): a whole clear regenerates the target in this frame.
            if (FramebufferParams.ClearsWhole(in clearRect))
            {
                FramebufferParams.GetColorView(index)?.Storage?.NoteAsyncFullClear(Gd.AsyncFrame);
            }
'''
DEPTH_CLEAR_OLD = '''            ClearAttachment attachment = new(flags, 0, clearValue);
            ClearRect clearRect = FramebufferParams.GetClearRect(ClearScissor, layer, layerCount);

            Gd.Api.CmdClearAttachments(CommandBuffer, 1, &attachment, 1, &clearRect);
'''
DEPTH_CLEAR_NEW = '''            ClearAttachment attachment = new(flags, 0, clearValue);
            ClearRect clearRect = FramebufferParams.GetClearRect(ClearScissor, layer, layerCount);

            Gd.Api.CmdClearAttachments(CommandBuffer, 1, &attachment, 1, &clearRect);

            // RewindBox (adapt_async_regenerated_targets): a whole depth clear regenerates the depth target in this frame.
            if ((flags & ImageAspectFlags.DepthBit) != 0 && FramebufferParams.ClearsWhole(in clearRect))
            {
                FramebufferParams.GetDepthStencilView()?.Storage?.NoteAsyncFullClear(Gd.AsyncFrame);
            }
'''


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    once(paths[RENDERER], CRITICAL_ANCHOR, CRITICAL_FIELD)
    once(paths[RENDERER], CRITICAL_OLD, CRITICAL_NEW)
    once(paths[WINDOW], PRESENT_OLD, PRESENT_NEW)
    once(paths[STORAGE], STORAGE_OLD, STORAGE_NEW)
    once(paths[FRAMEBUFFER], FRAMEBUFFER_OLD, FRAMEBUFFER_NEW)
    pipeline = paths[PIPELINE]
    once(pipeline, TIMER_OLD, TIMER_NEW)
    once(pipeline, LOG_OLD, LOG_NEW)
    once(pipeline, PREPARE_OLD, PREPARE_NEW)
    once(pipeline, PASS_OLD, PASS_NEW)
    once(pipeline, COLOR_CLEAR_OLD, COLOR_CLEAR_NEW)
    once(pipeline, DEPTH_CLEAR_OLD, DEPTH_CLEAR_NEW)
    return list(paths.values())
