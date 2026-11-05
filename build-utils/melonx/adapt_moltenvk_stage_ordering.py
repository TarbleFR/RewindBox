"""Order every later reader stage of a written texture, and render/compute switches, under MoltenVK 1.4.2's fences.

IPA 658 (MeloNX Core 658), Hogwarts Legacy, iPhone A18 Pro, iOS 27 beta 1, session pid 12312, 5 November 2026
06:41:39-06:50:08 UTC (private screenshots and logs, not in the repository): in an outdoor scene, frames with a white sky
and scene and black blobs following the cloud shapes, sharp-edged black rectangles and a horizontal black band across
the left 40 % of the screen, a cyan block near the top; other frames correct; the HUD always intact. Rectangles, a band
that stops part-way along a row and stale-coloured blocks are the shape of a read that overlaps its writer (tiles or
thread groups already written and the rest still holding older contents), not of a shader's arithmetic.

What orders such reads with MoltenVK v1.4.2 (Khronos db660224, rebuilt for IPA 640 and later) on iOS 18+: MVKDevice
gives Apple GPUs an MTLResidencySet, and MVKPipelineLayout then emits no UseResource operation for any argument-buffer
descriptor (MVKPipeline.mm, `} else if (!_device->hasResidencySet()) {`), so Metal no longer tracks hazards for
textures read through descriptor sets (only push descriptors and attachments are still bound directly). Ordering comes
only from vkCmdPipelineBarrier recorded outside a Metal render encoder (MVKCmdPipeline.mm: endCurrentMetalEncoding and
setBarrier), which MoltenVK turns into MTLFence slots per barrier stage (vertex, fragment, compute, copy;
MVKCommandBuffer.mm setBarrier: wait[dst][src] = update[src]); a later encoder waits only on the slots that a barrier
naming its own stage as destination recorded. The MoltenVK 1.4.0 fork used up to IPA 639 had no residency set on iOS
and called useResource for every descriptor, so Metal ordered each such read after the earlier writer by itself.

Gap 1 (TextureStorage.QueueWriteToReadBarrier, delivered Ryujinx): after an attachment write (AddStoreOpUsage or
QueueLoadOpBarrier), the first bind of the texture queues one barrier from the writer's stage to that reader's stage
only, then clears the pending modification. A later reader in another stage gets no barrier. Under MoltenVK 1.4.2 a
later compute or vertex-stage reader (a compute shader after a fragment read, a vertex shader read) then waits on no
fence the writer updated, and may run while the writer's render pass is still storing its tiles; a later fragment
reader stays ordered only because setBarrier also chains a source stage to itself (wait[i][i]). Texture and image arrays
(TextureArray/ImageArray.QueueWriteToReadBarriers) call the same method per storage. This is a Vulkan-level gap that
desktop drivers and Metal's own tracking hid. Change (every title, wherever Metal does not track argument-buffer hazards:
MoltenVK 1.4.1 and later, any other driver): the storage keeps the last modification's access and stage after its first
reader, and the stages covered since; a reader in a stage not covered yet gets its own barrier from the writer's stage
(only the new stages), once per modification and stage. No allocation, a few flag operations per bind; nothing for a
stage already covered. Counted by reader stage in the 5 s pass and GPU detail line.

Render/compute switches (Hogwarts policy, MoltenVkPolicy.OrderEncoderTransitions, set by the Library like
DeferInPassReadBarriers): on MoltenVK without argument-buffer hazard tracking, a switch from a render pass to a
compute dispatch, or from a dispatch to a render pass, within one command buffer, that no recorded barrier orders
(source stages of the earlier encoder kind, destination stages of the later one) gets a full memory barrier
(AllCommands to AllCommands) outside the pass, as Metal's tracking ordered such switches with 1.4.0 whenever a resource
was shared. It covers writes Ryujinx does not track per texture (storage images and buffers left without a guest
barrier). Every title counts its switches (covered, ordered, left unordered) in the same line; only the policy records
the barriers. MoltenVK command buffers are already totally ordered by syncFences.

Not changed: what is drawn and dispatched, attachment feedback loops (MoltenVK restarts the Metal pass), the 1.4.0
path, fast math. Not measured on an iPhone. Fail closed on drift: each file must be the Core 658 preparation's.
"""
import hashlib
from adapt_session import once

BASELINE = {
    'src/Ryujinx.Graphics.Vulkan/TextureStorage.cs': '3020f6c8dd938de055638a0349ee5127e1024f24673eb24c4f5d73f0628763ab',
    'src/Ryujinx.Graphics.Vulkan/BarrierBatch.cs': 'c34ef138840334a14adc2f8380bc15a18e2dad73889254a980bea5aefa581883',
    'src/Ryujinx.Graphics.Vulkan/PipelineBase.cs': '8d5db09a9b260535e50b3be7de47a8a9dd088f5692f59dd3b207dd37f7e5f9c5',
    'src/Ryujinx.Library/Library.cs': '1a8617c9a43876d72dbfb7954333bbda221f34db5a868a6b5f3f6fc3b1a42ec0',
}

STORAGE_FIELDS_OLD = '''        private AccessFlags _lastReadAccess;
        private PipelineStageFlags _lastReadStage;
'''
STORAGE_FIELDS_NEW = '''        private AccessFlags _lastReadAccess;
        private PipelineStageFlags _lastReadStage;

        // RewindBox (adapt_moltenvk_stage_ordering): the last modification's access and stage, kept after its first
        // reader's barrier, and the reader stages a write-to-read barrier has covered since that modification.
        private AccessFlags _readCoverageAccess;
        private PipelineStageFlags _readCoverageStage;
        private PipelineStageFlags _readCoveredStages;
'''

READ_BARRIER_OLD = '''                if (_gd.PipelineInternal != null && _gd.PipelineInternal.TryDeferInPassReadBarrier(this, dstStageFlags))
                {
                    _lastModificationAccess = AccessFlags.None;
                    return;
                }

                ImageAspectFlags aspectFlags = Info.Format.ConvertAspectFlags();
                ImageMemoryBarrier barrier = TextureView.GetImageBarrier(
                    _imageAuto.Get(cbs).Value,
                    _lastModificationAccess,
                    dstAccessFlags,
                    aspectFlags,
                    0,
                    0,
                    _info.GetLayers(),
                    _info.Levels);

                _gd.Barriers.QueueBarrier(barrier, this, _lastModificationStage, dstStageFlags);

                _lastModificationAccess = AccessFlags.None;
            }
        }
'''
READ_BARRIER_NEW = '''                if (_gd.PipelineInternal != null && _gd.PipelineInternal.TryDeferInPassReadBarrier(this, dstStageFlags))
                {
                    _lastModificationAccess = AccessFlags.None;
                    // RewindBox (adapt_moltenvk_stage_ordering): a deferred barrier covers no stage yet; later readers
                    // keep the delivered path.
                    _readCoverageAccess = AccessFlags.None;
                    return;
                }

                ImageAspectFlags aspectFlags = Info.Format.ConvertAspectFlags();
                ImageMemoryBarrier barrier = TextureView.GetImageBarrier(
                    _imageAuto.Get(cbs).Value,
                    _lastModificationAccess,
                    dstAccessFlags,
                    aspectFlags,
                    0,
                    0,
                    _info.GetLayers(),
                    _info.Levels);

                _gd.Barriers.QueueBarrier(barrier, this, _lastModificationStage, dstStageFlags);

                // RewindBox (adapt_moltenvk_stage_ordering): this modification is now ordered before the first reader's
                // stages only; kept for the readers of other stages.
                _readCoverageAccess = _lastModificationAccess;
                _readCoverageStage = _lastModificationStage;
                _readCoveredStages = dstStageFlags;
                RenderDetail.NoteWriteToRead(dstStageFlags, later: false);

                _lastModificationAccess = AccessFlags.None;
            }
            else if (_readCoverageAccess != AccessFlags.None && (dstStageFlags & ~_readCoveredStages) != 0 &&
                !_gd.MoltenVkTracksArgumentBufferHazards)
            {
                // RewindBox (adapt_moltenvk_stage_ordering): a reader in a stage no barrier has covered since the last
                // modification. Under MoltenVK 1.4.2 (residency sets, no useResource) its Metal encoder waits only on the
                // fences a barrier names its stage for, so it gets its own barrier from the writer's stage (new stages only).
                PipelineStageFlags newStages = dstStageFlags & ~_readCoveredStages;
                ImageMemoryBarrier barrier = TextureView.GetImageBarrier(
                    _imageAuto.Get(cbs).Value,
                    _readCoverageAccess,
                    dstAccessFlags,
                    Info.Format.ConvertAspectFlags(),
                    0,
                    0,
                    _info.GetLayers(),
                    _info.Levels);

                _gd.Barriers.QueueBarrier(barrier, this, _readCoverageStage, newStages);

                _readCoveredStages |= newStages;
                RenderDetail.NoteWriteToRead(newStages, later: true);
            }
        }
'''

POLICY_OLD = '''        public static bool MeasureGpu { get; set; }
    }
'''
POLICY_NEW = '''        public static bool MeasureGpu { get; set; }

        /// <summary>
        /// RewindBox (adapt_moltenvk_stage_ordering): on MoltenVK without Metal tracking of argument-buffer hazards (1.4.1
        /// and later, residency sets), a full memory barrier at each switch between a render pass and a compute dispatch
        /// of one command buffer that no recorded barrier orders (EncoderOrdering). Off: counted only.
        /// </summary>
        public static bool OrderEncoderTransitions { get; set; }
    }

    /// <summary>
    /// RewindBox (adapt_moltenvk_stage_ordering): switches between render passes and compute dispatches in a command buffer,
    /// and whether a recorded barrier orders each one under MoltenVK 1.4.2's fences: a barrier recorded outside a render pass
    /// makes the encoders of its destination stages wait for those of its source stages (MVKCommandEncoder::setBarrier); the
    /// stage classes are MoltenVK's (mvkBarrierStagesFromPipelineStageFlags). State per recording thread, reset when its
    /// command buffer changes (MoltenVK orders command buffers whole). The counters are read by RenderDetail every window.
    /// </summary>
    static class EncoderOrdering
    {
        private const PipelineStageFlags AnyStage = PipelineStageFlags.TopOfPipeBit | PipelineStageFlags.BottomOfPipeBit |
            PipelineStageFlags.AllCommandsBit;

        internal const PipelineStageFlags VertexStages = AnyStage | PipelineStageFlags.AllGraphicsBit | PipelineStageFlags.DrawIndirectBit |
            PipelineStageFlags.VertexInputBit | PipelineStageFlags.VertexShaderBit | PipelineStageFlags.TessellationControlShaderBit |
            PipelineStageFlags.TessellationEvaluationShaderBit | PipelineStageFlags.GeometryShaderBit | PipelineStageFlags.TransformFeedbackBitExt;

        internal const PipelineStageFlags FragmentStages = AnyStage | PipelineStageFlags.AllGraphicsBit | PipelineStageFlags.FragmentShaderBit |
            PipelineStageFlags.EarlyFragmentTestsBit | PipelineStageFlags.LateFragmentTestsBit | PipelineStageFlags.ColorAttachmentOutputBit;

        internal const PipelineStageFlags ComputeStages = AnyStage | PipelineStageFlags.ComputeShaderBit;

        [ThreadStatic] private static nint _commandBuffer;
        [ThreadStatic] private static bool _renderSinceDispatch;
        [ThreadStatic] private static bool _dispatchSinceRender;
        // Destination stages ordered after the last render pass, and after the last dispatch, by barriers recorded since.
        [ThreadStatic] private static PipelineStageFlags _orderedAfterRender;
        [ThreadStatic] private static PipelineStageFlags _orderedAfterDispatch;

        public static long RenderToCompute, RenderToComputeCovered, RenderToComputeOrdered;
        public static long ComputeToRender, ComputeToRenderCovered, ComputeToRenderOrdered;

        private static void Bind(nint commandBuffer)
        {
            if (_commandBuffer != commandBuffer)
            {
                _commandBuffer = commandBuffer;
                _renderSinceDispatch = false;
                _dispatchSinceRender = false;
                _orderedAfterRender = PipelineStageFlags.None;
                _orderedAfterDispatch = PipelineStageFlags.None;
            }
        }

        /// <summary>A pipeline barrier recorded outside any render pass.</summary>
        internal static void NoteBarrier(nint commandBuffer, PipelineStageFlags source, PipelineStageFlags destination)
        {
            Bind(commandBuffer);

            if ((source & FragmentStages) != 0)
            {
                _orderedAfterRender |= destination;
            }

            if ((source & ComputeStages) != 0)
            {
                _orderedAfterDispatch |= destination;
            }
        }

        /// <summary>Before a render pass begins: true if the caller must record the full barrier first.</summary>
        internal static bool BeforeRenderPass(nint commandBuffer, bool order)
        {
            Bind(commandBuffer);

            if (!_dispatchSinceRender)
            {
                return false;
            }

            Interlocked.Increment(ref ComputeToRender);

            if ((_orderedAfterDispatch & VertexStages) != 0 && (_orderedAfterDispatch & FragmentStages) != 0)
            {
                Interlocked.Increment(ref ComputeToRenderCovered);
                return false;
            }

            if (order)
            {
                Interlocked.Increment(ref ComputeToRenderOrdered);
            }

            return order;
        }

        internal static void RenderPassBegun(nint commandBuffer)
        {
            Bind(commandBuffer);
            _renderSinceDispatch = true;
            _dispatchSinceRender = false;
            _orderedAfterRender = PipelineStageFlags.None;
        }

        /// <summary>Before a dispatch is recorded: true if the caller must record the full barrier first.</summary>
        internal static bool BeforeDispatch(nint commandBuffer, bool order)
        {
            Bind(commandBuffer);

            if (!_renderSinceDispatch)
            {
                return false;
            }

            Interlocked.Increment(ref RenderToCompute);

            if ((_orderedAfterRender & ComputeStages) != 0)
            {
                Interlocked.Increment(ref RenderToComputeCovered);
                return false;
            }

            if (order)
            {
                Interlocked.Increment(ref RenderToComputeOrdered);
            }

            return order;
        }

        internal static void DispatchRecorded(nint commandBuffer)
        {
            Bind(commandBuffer);
            _dispatchSinceRender = true;
            _renderSinceDispatch = false;
            _orderedAfterDispatch = PipelineStageFlags.None;
        }
    }
'''

DETAIL_FIELDS_OLD = '''        public static long InPassAttachmentBarriersKept;
'''
DETAIL_FIELDS_NEW = '''        public static long InPassAttachmentBarriersKept;
        // RewindBox (adapt_moltenvk_stage_ordering): write-to-read barriers after an attachment write, by reader stage class
        // (vertex, fragment, compute): the first reader's (delivered) and those of a later reader in a stage not yet covered.
        public static readonly long[] WriteToReadFirst = new long[3];
        public static readonly long[] WriteToReadLater = new long[3];

        public static void NoteWriteToRead(PipelineStageFlags stages, bool later)
        {
            long[] counts = later ? WriteToReadLater : WriteToReadFirst;

            if ((stages & ~(PipelineStageFlags.FragmentShaderBit | PipelineStageFlags.ComputeShaderBit)) != 0)
            {
                System.Threading.Interlocked.Increment(ref counts[0]);
            }

            if ((stages & PipelineStageFlags.FragmentShaderBit) != 0)
            {
                System.Threading.Interlocked.Increment(ref counts[1]);
            }

            if ((stages & PipelineStageFlags.ComputeShaderBit) != 0)
            {
                System.Threading.Interlocked.Increment(ref counts[2]);
            }
        }
'''

LOG_OLD = '''            text.Append("; GPU ").Append(MetalGpuTimer.TakeWindow(frames));
'''
LOG_NEW = '''            // RewindBox (adapt_moltenvk_stage_ordering): counted and reset every window.
            text.Append("; write-to-read barriers (vertex/fragment/compute): first reader ")
                .Append(System.Threading.Interlocked.Exchange(ref WriteToReadFirst[0], 0)).Append('/')
                .Append(System.Threading.Interlocked.Exchange(ref WriteToReadFirst[1], 0)).Append('/')
                .Append(System.Threading.Interlocked.Exchange(ref WriteToReadFirst[2], 0)).Append(", later reader in a new stage ")
                .Append(System.Threading.Interlocked.Exchange(ref WriteToReadLater[0], 0)).Append('/')
                .Append(System.Threading.Interlocked.Exchange(ref WriteToReadLater[1], 0)).Append('/')
                .Append(System.Threading.Interlocked.Exchange(ref WriteToReadLater[2], 0))
                .Append("; encoder switches: render to compute ").Append(System.Threading.Interlocked.Exchange(ref EncoderOrdering.RenderToCompute, 0))
                .Append(" (barrier recorded ").Append(System.Threading.Interlocked.Exchange(ref EncoderOrdering.RenderToComputeCovered, 0))
                .Append(", ordered by the policy ").Append(System.Threading.Interlocked.Exchange(ref EncoderOrdering.RenderToComputeOrdered, 0))
                .Append("), compute to render ").Append(System.Threading.Interlocked.Exchange(ref EncoderOrdering.ComputeToRender, 0))
                .Append(" (barrier recorded ").Append(System.Threading.Interlocked.Exchange(ref EncoderOrdering.ComputeToRenderCovered, 0))
                .Append(", ordered by the policy ").Append(System.Threading.Interlocked.Exchange(ref EncoderOrdering.ComputeToRenderOrdered, 0))
                .Append(')');

            text.Append("; GPU ").Append(MetalGpuTimer.TakeWindow(frames));
'''

DEFER_OLD = '''            _rpHolder.AddForcedFence(storage, dstStageFlags);
            RenderDetail.DeferredPassBarriers++;

            return true;
        }
'''
DEFER_NEW = '''            _rpHolder.AddForcedFence(storage, dstStageFlags);
            RenderDetail.DeferredPassBarriers++;

            return true;
        }

        /// <summary>
        /// RewindBox (adapt_moltenvk_stage_ordering): whether switches between render passes and dispatches that no barrier
        /// orders get one (Hogwarts policy, MoltenVK without argument-buffer hazard tracking).
        /// </summary>
        private bool OrdersEncoderTransitions => MoltenVkPolicy.OrderEncoderTransitions && Gd.IsMoltenVk && !Gd.MoltenVkTracksArgumentBufferHazards;

        /// <summary>
        /// RewindBox (adapt_moltenvk_stage_ordering): a full memory barrier outside any render pass. MoltenVK 1.4.2 links
        /// every Metal encoder stage recorded after it to every one recorded before it (MTLFence waits and updates).
        /// </summary>
        private void RecordEncoderTransitionBarrier()
        {
            MemoryBarrier memoryBarrier = new()
            {
                SType = StructureType.MemoryBarrier,
                SrcAccessMask = AccessFlags.MemoryWriteBit,
                DstAccessMask = AccessFlags.MemoryReadBit | AccessFlags.MemoryWriteBit,
            };

            Gd.Api.CmdPipelineBarrier(
                CommandBuffer,
                PipelineStageFlags.AllCommandsBit,
                PipelineStageFlags.AllCommandsBit,
                0,
                1,
                new ReadOnlySpan<MemoryBarrier>(in memoryBarrier),
                0,
                ReadOnlySpan<BufferMemoryBarrier>.Empty,
                0,
                ReadOnlySpan<ImageMemoryBarrier>.Empty);

            EncoderOrdering.NoteBarrier(CommandBuffer.Handle, PipelineStageFlags.AllCommandsBit, PipelineStageFlags.AllCommandsBit);
        }
'''

BEGIN_OLD = '''                FramebufferParams.InsertLoadOpBarriers(Gd, Cbs);
'''
BEGIN_NEW = '''                FramebufferParams.InsertLoadOpBarriers(Gd, Cbs);

                // RewindBox (adapt_moltenvk_stage_ordering): a switch from compute dispatches that no barrier orders.
                if (EncoderOrdering.BeforeRenderPass(CommandBuffer.Handle, OrdersEncoderTransitions))
                {
                    RecordEncoderTransitionBarrier();
                }

                EncoderOrdering.RenderPassBegun(CommandBuffer.Handle);
'''

DISPATCH_OLD = '''            long barrierStart = RenderStageTimer.Now();
            Gd.Barriers.Flush(Cbs, _program, _feedbackLoop != 0, RenderPassActive, _rpHolder, EndRenderPassDelegate);
            long descriptorStart = RenderStageTimer.Now();

            _descriptorSetUpdater.UpdateAndBindDescriptorSets(Cbs, PipelineBindPoint.Compute);
'''
DISPATCH_NEW = '''            long barrierStart = RenderStageTimer.Now();
            Gd.Barriers.Flush(Cbs, _program, _feedbackLoop != 0, RenderPassActive, _rpHolder, EndRenderPassDelegate);

            // RewindBox (adapt_moltenvk_stage_ordering): a switch from a render pass that no barrier orders.
            if (EncoderOrdering.BeforeDispatch(CommandBuffer.Handle, OrdersEncoderTransitions))
            {
                RecordEncoderTransitionBarrier();
            }

            EncoderOrdering.DispatchRecorded(CommandBuffer.Handle);
            long descriptorStart = RenderStageTimer.Now();

            _descriptorSetUpdater.UpdateAndBindDescriptorSets(Cbs, PipelineBindPoint.Compute);
'''

BATCH_OLD = '''                if (hasBarrier)
                {
                    PipelineStageFlags srcStageFlags = flags.Source;

                    if (inRenderPass)
                    {
                        // Inside a render pass, barrier stages can only be from rasterization.
                        srcStageFlags &= ~PipelineStageFlags.ComputeShaderBit;
                    }

                    _gd.Api.CmdPipelineBarrier('''
BATCH_NEW = '''                if (hasBarrier)
                {
                    PipelineStageFlags srcStageFlags = flags.Source;

                    if (inRenderPass)
                    {
                        // Inside a render pass, barrier stages can only be from rasterization.
                        srcStageFlags &= ~PipelineStageFlags.ComputeShaderBit;
                    }
                    else
                    {
                        // RewindBox (adapt_moltenvk_stage_ordering): only a barrier outside a render pass sets MoltenVK
                        // 1.4.2's fences.
                        EncoderOrdering.NoteBarrier(cbs.CommandBuffer.Handle, srcStageFlags, flags.Dest);
                    }

                    _gd.Api.CmdPipelineBarrier('''

LIBRARY_OLD = '''            Ryujinx.Graphics.Vulkan.MoltenVkPolicy.MeasureGpu = hogwarts;
'''
LIBRARY_NEW = '''            Ryujinx.Graphics.Vulkan.MoltenVkPolicy.MeasureGpu = hogwarts;
            // RewindBox (adapt_moltenvk_stage_ordering): MoltenVK 1.4.2 (residency sets): a full barrier at each switch
            // between a render pass and a compute dispatch that no recorded barrier orders.
            Ryujinx.Graphics.Vulkan.MoltenVkPolicy.OrderEncoderTransitions = hogwarts;
'''


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name

    storage = paths['src/Ryujinx.Graphics.Vulkan/TextureStorage.cs']
    once(storage, STORAGE_FIELDS_OLD, STORAGE_FIELDS_NEW)
    once(storage, READ_BARRIER_OLD, READ_BARRIER_NEW)

    pipeline = paths['src/Ryujinx.Graphics.Vulkan/PipelineBase.cs']
    once(pipeline, POLICY_OLD, POLICY_NEW)
    once(pipeline, DETAIL_FIELDS_OLD, DETAIL_FIELDS_NEW)
    once(pipeline, LOG_OLD, LOG_NEW)
    once(pipeline, DEFER_OLD, DEFER_NEW)
    once(pipeline, BEGIN_OLD, BEGIN_NEW)
    once(pipeline, DISPATCH_OLD, DISPATCH_NEW)

    once(paths['src/Ryujinx.Graphics.Vulkan/BarrierBatch.cs'], BATCH_OLD, BATCH_NEW)
    once(paths['src/Ryujinx.Library/Library.cs'], LIBRARY_OLD, LIBRARY_NEW)
    return list(paths.values())
