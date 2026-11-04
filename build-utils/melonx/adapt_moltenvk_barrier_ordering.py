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
Expected cost: the few barriers 640 deferred (about 0.1 per frame) are recorded again. Not measured on an iPhone.
Fail closed on drift: each file must be the Core 639 preparation's.
"""
import hashlib
from adapt_session import once

BASELINE = {
    'src/Ryujinx.Graphics.Vulkan/VulkanRenderer.cs': '52d86f7c12b4e779ff038b5788a28dc66bd268261c667a79eab567ad7ffadd4e',
    'src/Ryujinx.Graphics.Vulkan/PipelineBase.cs': '04ce0581b9b04cd04510d6d253f710a1f944303411849cf22ede1305534214c0',
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
    return list(paths.values())
