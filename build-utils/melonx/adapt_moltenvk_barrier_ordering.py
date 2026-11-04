"""Keep the in-pass read barrier when MoltenVK no longer orders argument-buffer reads by itself.

IPA 640 (MeloNX Core 639, Hogwarts Legacy, 4 November 2026; private player logs and a screen recording, not in the
repository): a real FPS gain, and at camera cuts the presented image alternates between the new shot and the previous
one for a few frames (A A B A B A B B B); single older frames also appear inside continuous shots. An older frame
presented between newer ones is a texture read before the pass that writes it has finished, i.e. a missing ordering.

What changed for MeloNX between 629 and 640 on this path: IPA 640 replaces MoltenVK 1.4.0 with the rebuilt Khronos
v1.4.2. On iOS 18 with an Apple6 or later GPU and argument buffers, v1.4.2 makes resources resident through a
MTLResidencySet and stops calling useResource for argument-buffer resources (MVKDevice.mm, residencySets; MVKCommand-
Buffer.mm barrierWait/barrierUpdate): Metal then no longer tracks hazards for those reads, and ordering comes only from
the Vulkan barriers, which v1.4.2 turns into MTLFence waits and updates.

adapt_hogwarts_dma_copies (build 628, MoltenVkPolicy.DeferInPassReadBarriers, Hogwarts Legacy only) defers the
write-to-read barrier of a texture bound inside a render pass it is not an attachment of to the next begin of that pass
(PipelineBase.TryDeferInPassReadBarrier clears the pending modification and records nothing now). Its stated premise is
that "Metal's hazard tracking already orders this read". That holds for MoltenVK 1.4.0 and earlier on iOS, not for
v1.4.2: the draws of the current pass then read the texture with no barrier at all. 640 deferred such barriers in the
same minutes as the stale frames (6-14 per 5 s window).

Change: VulkanRenderer records whether the MoltenVK in use orders argument-buffer reads by Metal's hazard tracking,
MoltenVK 1.4.0 or earlier (VkPhysicalDeviceProperties.driverVersion is MVK_VERSION, major * 10000 + minor * 100 +
patch: 10400 or less), and logs that once. TryDeferInPassReadBarrier defers only then; otherwise the barrier is queued
as the delivered Ryujinx path does (BarrierBatch records it inside the pass and MoltenVK orders it). Nothing else
changes: the policy flag, feedback-loop barriers, forced fences, other titles and 1.4.0 behaviour are as before.
Expected cost: the few barriers 640 deferred (about 0.1 per frame) are recorded again.

Every title, same MoltenVK (Super Smash Bros. Ultimate on IPA 640 showed a similar flicker; its logs show the policy above
off and 0 deferrals, so that path is not its cause): Ryujinx's BarrierBatch records an image barrier queued inside a render
pass inside that pass on MoltenVK ("Metal already has hazard tracking"), while other tile-based GPUs end the pass first. In
MoltenVK 1.4.2 with residency sets, vkCmdPipelineBarrier links encoders through MTLFences only when no Metal render encoder
is active (MVKCmdPipeline.mm: setBarrier under !_mtlRenderEncoder && hasResidencySet()); inside a pass it restarts the Metal
pass for a GENERAL-layout image barrier but sets no fence, and applyImageMemoryBarrier only syncs host memory and layouts.
So a texture written by an earlier pass and sampled in the active one is ordered by nothing. When such a barrier is for a
texture that is not an attachment of the pass (BarrierBatch's anyIsNonAttachment) and MoltenVK no longer tracks
argument-buffer hazards, the pass now ends before the barrier is recorded, as the delivered path already does on other
tile-based GPUs; the draw begins the pass again after the flush (PipelineBase). Feedback loops (attachments of the active
pass only), MoltenVK 1.4.0 and other drivers keep the delivered path. The pass and GPU detail line counts these endings
for every title ("in-pass image barriers ending the pass"). MoltenVK already restarted the Metal pass for each such
GENERAL-layout barrier, so the expected cost is the Vulkan pass re-begin. Not measured on an iPhone, for either title.
Fail closed on drift: each file must be the Core 639 preparation's.
"""
import hashlib
from adapt_session import once

BASELINE = {
    'src/Ryujinx.Graphics.Vulkan/VulkanRenderer.cs': '52d86f7c12b4e779ff038b5788a28dc66bd268261c667a79eab567ad7ffadd4e',
    'src/Ryujinx.Graphics.Vulkan/PipelineBase.cs': '04ce0581b9b04cd04510d6d253f710a1f944303411849cf22ede1305534214c0',
    'src/Ryujinx.Graphics.Vulkan/BarrierBatch.cs': 'b6d5db87a7a69e5ea034e7a61a341ef9198801a8dde957eadc9babbd410944eb',
}

# MoltenVK 1.4.0: the last version whose iOS build tracks hazards of argument-buffer resources through useResource.
LAST_TRACKING_MOLTENVK = 10400


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name

    renderer = paths['src/Ryujinx.Graphics.Vulkan/VulkanRenderer.cs']
    once(renderer, '''        internal bool IsTBDR { get; private set; }
''', '''        internal bool IsTBDR { get; private set; }

        /// <summary>
        /// RewindBox (adapt_moltenvk_barrier_ordering): MoltenVK 1.4.0 or earlier, whose Metal encoders declare every
        /// argument-buffer resource they use (useResource), so Metal orders such a read after an earlier write. From
        /// 1.4.2 on iOS 18 resources are resident through a residency set and only the Vulkan barriers order them.
        /// </summary>
        internal bool MoltenVkTracksArgumentBufferHazards { get; private set; }
''')
    once(renderer, '''            GpuVersion = $"Vulkan v{ParseStandardVulkanVersion(properties.ApiVersion)}, Driver v{ParseDriverVersion(ref properties)}";
''', '''            GpuVersion = $"Vulkan v{ParseStandardVulkanVersion(properties.ApiVersion)}, Driver v{ParseDriverVersion(ref properties)}";

            // MoltenVK reports MVK_VERSION (major * 10000 + minor * 100 + patch) as its driver version.
            MoltenVkTracksArgumentBufferHazards = IsMoltenVk && properties.DriverVersion <= %d;

            if (IsMoltenVk)
            {
                Logger.Info?.Print(LogClass.Gpu, $"MoltenVK driver version {properties.DriverVersion}: " +
                    (MoltenVkTracksArgumentBufferHazards
                        ? "Metal tracks argument-buffer hazards; in-pass read barriers may be deferred"
                        : "only Vulkan barriers order argument-buffer reads; in-pass read barriers are recorded"));
            }
''' % LAST_TRACKING_MOLTENVK)

    pipeline = paths['src/Ryujinx.Graphics.Vulkan/PipelineBase.cs']
    once(pipeline, '''            if (!MoltenVkPolicy.DeferInPassReadBarriers || !RenderPassActive || !Gd.IsMoltenVk || !Gd.IsTBDR || _rpHolder == null)
''', '''            // RewindBox (adapt_moltenvk_barrier_ordering): the deferral relies on Metal's hazard tracking, which MoltenVK
            // 1.4.2 no longer applies to argument-buffer reads on iOS 18; there, the barrier is recorded as delivered.
            if (!MoltenVkPolicy.DeferInPassReadBarriers || !RenderPassActive || !Gd.IsMoltenVk || !Gd.IsTBDR || _rpHolder == null ||
                !Gd.MoltenVkTracksArgumentBufferHazards)
''')
    once(pipeline, """        public static long DeferredPassBarriers, FeedbackPassBarriers;
""", """        public static long DeferredPassBarriers, FeedbackPassBarriers;
        // RewindBox (adapt_moltenvk_barrier_ordering): image barriers of non-attachments that ended the active pass, every title.
        public static long EndedPassImageBarriers;
""")
    once(pipeline, """.Append(FeedbackPassBarriers).Append("; compute descriptors by program size: up to 32 ")""",
         """.Append(FeedbackPassBarriers).Append("; in-pass image barriers ending the pass ")
                .Append(System.Threading.Interlocked.Exchange(ref EndedPassImageBarriers, 0)).Append("; compute descriptors by program size: up to 32 ")""")

    batch = paths['src/Ryujinx.Graphics.Vulkan/BarrierBatch.cs']
    once(batch, """                    if (_gd.IsTBDR)
                    {
                        if (!_gd.IsMoltenVk)
                        {""", """                    if (_gd.IsTBDR)
                    {
                        if (EndsPassForInPassImageBarriers(anyIsNonAttachment))
                        {
                            // RewindBox (adapt_moltenvk_barrier_ordering): MoltenVK 1.4.2 on iOS 18 orders argument-buffer
                            // reads only through barriers recorded outside a Metal render encoder (MTLFence waits and updates
                            // set by vkCmdPipelineBarrier there); one recorded inside the pass orders nothing. End the pass, as
                            // other tile-based GPUs do below, so the barrier is recorded outside it.
                            RenderDetail.EndedPassImageBarriers++;
                            endRenderPass();
                            inRenderPass = false;
                        }
                        else if (!_gd.IsMoltenVk)
                        {""")
    once(batch, """        private void QueueIncoherentBarrier(IncoherentBarrierType type)""", """        /// <summary>
        /// RewindBox (adapt_moltenvk_barrier_ordering): whether image barriers queued inside a render pass must end it on
        /// MoltenVK. Only when one is for a texture that is not an attachment of the pass, and only when MoltenVK no longer
        /// declares argument-buffer resources to Metal (1.4.1 and later: residency sets, ordering by barriers alone).
        /// MoltenVK 1.4.0 and earlier keep the delivered path (the barrier inside the pass, Metal's hazard tracking).
        /// </summary>
        internal bool EndsPassForInPassImageBarriers(bool anyIsNonAttachment)
        {
            return anyIsNonAttachment && _gd.IsMoltenVk && !_gd.MoltenVkTracksArgumentBufferHazards;
        }

        private void QueueIncoherentBarrier(IncoherentBarrierType type)""")
    return list(paths.values())
