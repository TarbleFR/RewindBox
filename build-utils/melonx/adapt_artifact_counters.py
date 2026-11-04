"""Count, every window, the three Vulkan paths suspected of the remaining black artifacts (instrumentation only).

IPA 650 (MeloNX Core 649), Hogwarts Legacy, two sessions in one process (private player logs, maintainer's iPhone, not in
the repository): black artifacts remain on screen and their mechanism is undecided. The delivered logs do not say which
of three code paths runs while they appear:
- texture arrays: an element whose image view has been destroyed while the array still holds it is bound to the dummy
  texture, which samples black (TextureArray.GetImageInfos for the delivered walk of each command buffer; ResolveValues
  for the incremental refresh of EncodingPolicy.IncrementalArrayDescriptors, whose RebuildReferences records such an
  element as changed);
- MoltenVK in-pass image barriers: when every image barrier queued inside a render pass is for an attachment of that pass,
  BarrierBatch keeps it inside the pass on MoltenVK (EndsPassForInPassImageBarriers is false, adapt_moltenvk_barrier_ordering
  only ends the pass for a non-attachment). With MoltenVK 1.4.2 and residency sets (!MoltenVkTracksArgumentBufferHazards)
  vkCmdPipelineBarrier inside an active Metal render encoder sets no MTLFence, so such a barrier orders nothing;
- the tile-based write-mask filter (PipelineBase.CreateFramebuffer, filterWriteMasked): a color attachment bound twice is
  removed from the framebuffer from the binding whose write mask is 0; draws then no longer write it through that slot.

Change, counters only: RenderDetail gains four counters appended to the existing "Vulkan pass and GPU detail" line (one
"artifact paths" segment before the GPU figure) and reset there every window:
- texture-array elements given the dummy view because their view was destroyed, by the delivered walk and by the
  incremental refresh (counted per element resolved, the elements copied from the previous equal element included);
- in-pass image barriers of attachments only kept inside the pass on MoltenVK without argument-buffer hazard tracking.
  The image-barrier decision (an else-if branch after the delivered ones) only marks a local; the counter moves after
  the delivered memory-barrier check of the same loop turn, and only if the pass is still active then: a queued memory
  barrier for DrawIndirect, or for a stage SupportsRenderPassBarrier rejects (compute), still ends the pass there and
  the image barriers are then recorded outside it, which is not counted. The unit is one turn of the BarrierBatch.Flush
  while loop with such barriers pending and kept, not a barrier or a Flush call: barriers of two flag pairs, more than
  16 barriers, or a memory barrier of other flags queued first each add a turn for the same queue;
- color attachments removed by the write-mask filter; a slot already emptied is compared again by the delivered loop
  (null == null) and is not counted twice.
Each increment sits at its decision (the barrier one where the loop turn has settled whether the pass stays) and changes
no decision, barrier, binding or framebuffer: the files are the preparation plus inserted lines only. Render thread, as
the other RenderDetail counters. Not measured on an iPhone; a non-zero count while artifacts appear points to a path, it
does not prove it is their cause.
Order: the BASELINE is the complete Core 649 preparation, adapt_moltenvk_barrier_ordering and every other adapter of
these files included, so this one runs after all of them (it shares PipelineBase.cs and BarrierBatch.cs with
adapt_moltenvk_barrier_ordering).
Fail closed on drift: each file must be the Core 649 preparation's.
"""
import hashlib
from adapt_session import once

BASELINE = {
    'src/Ryujinx.Graphics.Vulkan/PipelineBase.cs': 'ce7f301ce41101b0d45f40c90c53983551a993e2c907cbb22857038556bc8752',
    'src/Ryujinx.Graphics.Vulkan/BarrierBatch.cs': '5aa919aea10db6ed5f3ca952d661581b07c3edc46cc05979c62162098941549f',
    'src/Ryujinx.Graphics.Vulkan/TextureArray.cs': '4e85b01cb67039c821977f7ac45d9aed1c8f6274a07a88a6ad367cebbbaa629b',
}

COUNTERS = ('ArrayDestroyedViewWalkElements', 'ArrayDestroyedViewRefreshElements', 'InPassAttachmentBarriersKept',
            'MaskedAttachmentsRemoved')


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name

    pipeline = paths['src/Ryujinx.Graphics.Vulkan/PipelineBase.cs']
    once(pipeline, '''        // RewindBox (adapt_moltenvk_barrier_ordering): image barriers of non-attachments that ended the active pass, every title.
        public static long EndedPassImageBarriers;
''', '''        // RewindBox (adapt_moltenvk_barrier_ordering): image barriers of non-attachments that ended the active pass, every title.
        public static long EndedPassImageBarriers;
        // RewindBox (adapt_artifact_counters): the paths suspected of black artifacts, each counted at its decision.
        // Texture-array elements whose view was destroyed, given the dummy (black) view: by the delivered walk of each
        // command buffer (TextureArray.GetImageInfos) and by the incremental refresh of changed elements (ResolveValues).
        public static long ArrayDestroyedViewWalkElements, ArrayDestroyedViewRefreshElements;
        // MoltenVK without Metal tracking of argument-buffer hazards: image barriers queued inside a render pass, all for
        // attachments of that pass, kept inside it (BarrierBatch.Flush). Once per loop turn of Flush with them pending and
        // the pass still active after its memory-barrier check: a count of decisions, not of barriers or Flush calls.
        public static long InPassAttachmentBarriersKept;
        // Color attachments removed by the tile-based write-mask filter (PipelineBase.CreateFramebuffer).
        public static long MaskedAttachmentsRemoved;
''')
    once(pipeline, '''            text.Append("; GPU ").Append(MetalGpuTimer.TakeWindow(frames));
''', '''            // RewindBox (adapt_artifact_counters): counted and reset every window.
            text.Append("; artifact paths: texture-array elements on the dummy for a destroyed view ")
                .Append(System.Threading.Interlocked.Exchange(ref ArrayDestroyedViewWalkElements, 0)).Append(" walked, ")
                .Append(System.Threading.Interlocked.Exchange(ref ArrayDestroyedViewRefreshElements, 0))
                .Append(" refreshed; attachment-only in-pass image barriers kept in the pass ")
                .Append(System.Threading.Interlocked.Exchange(ref InPassAttachmentBarriersKept, 0))
                .Append("; write-masked attachments removed ").Append(System.Threading.Interlocked.Exchange(ref MaskedAttachmentsRemoved, 0));

            text.Append("; GPU ").Append(MetalGpuTimer.TakeWindow(frames));
''')
    once(pipeline, '''                            if (vkBlend.ColorWriteMask == 0)
                            {
                                colors[i] = null;
                                MaskOut(colors);
                            }
                            else if (vkBlend2.ColorWriteMask == 0)
                            {
                                colors[j] = null;
                                MaskOut(colors);
                            }''', '''                            if (vkBlend.ColorWriteMask == 0)
                            {
                                // RewindBox (adapt_artifact_counters): a slot already emptied is compared again (null == null)
                                // and is not counted twice.
                                RenderDetail.MaskedAttachmentsRemoved += colors[i] != null ? 1 : 0;
                                colors[i] = null;
                                MaskOut(colors);
                            }
                            else if (vkBlend2.ColorWriteMask == 0)
                            {
                                RenderDetail.MaskedAttachmentsRemoved += colors[j] != null ? 1 : 0;
                                colors[j] = null;
                                MaskOut(colors);
                            }''')

    batch = paths['src/Ryujinx.Graphics.Vulkan/BarrierBatch.cs']
    once(batch, '''                if (inRenderPass && _imageBarriers.Count > 0)
                {
                    // Image barriers queued in the batch are meant to be globally scoped,
''', '''                // RewindBox (adapt_artifact_counters): attachment-only image barriers this turn leaves in the pass.
                bool attachmentBarriersKeptInPass = false;

                if (inRenderPass && _imageBarriers.Count > 0)
                {
                    // Image barriers queued in the batch are meant to be globally scoped,
''')
    once(batch, '''                                // Metal already has hazard tracking so MVK doesn't need this.
                                endRenderPass();
                                inRenderPass = false;
                            }
                        }
                    }
''', '''                                // Metal already has hazard tracking so MVK doesn't need this.
                                endRenderPass();
                                inRenderPass = false;
                            }
                        }
                        else if (!_gd.MoltenVkTracksArgumentBufferHazards)
                        {
                            // RewindBox (adapt_artifact_counters): MoltenVK with residency-set ordering and every image barrier
                            // for an attachment of the active pass: left inside the Metal render encoder, where MoltenVK 1.4.2
                            // sets no fence. Marked only; counted below if the memory-barrier check keeps the pass.
                            attachmentBarriersKeptInPass = true;
                        }
                    }
''')

    once(batch, '''                    if (allFlags.HasFlag(PipelineStageFlags.DrawIndirectBit) || !_gd.SupportsRenderPassBarrier(allFlags))
                    {
                        endRenderPass();
                        inRenderPass = false;
                    }
                }

                AddBarriers(_memoryBarrierBatch.AsSpan(),''', '''                    if (allFlags.HasFlag(PipelineStageFlags.DrawIndirectBit) || !_gd.SupportsRenderPassBarrier(allFlags))
                    {
                        endRenderPass();
                        inRenderPass = false;
                    }
                }

                // RewindBox (adapt_artifact_counters): counted only if the memory-barrier check above kept the pass, so
                // the image barriers of this turn are recorded inside it.
                RenderDetail.InPassAttachmentBarriersKept += attachmentBarriersKeptInPass && inRenderPass ? 1 : 0;

                AddBarriers(_memoryBarrierBatch.AsSpan(),''')

    array = paths['src/Ryujinx.Graphics.Vulkan/TextureArray.cs']
    once(array, '''            _cachedSubmissionCount = submissionCount;

            for (int i = 0; i < textures.Length; i++)
            {
                ref DescriptorImageInfo texture = ref textures[i];
                ref TextureRef refs = ref _textureRefs[i];

                if (i > 0 && _textureRefs[i - 1].View == refs.View && _textureRefs[i - 1].Sampler == refs.Sampler)
                {
                    texture = textures[i - 1];

                    continue;
                }

                texture.ImageLayout = ImageLayout.General;
                texture.ImageView = refs.View?.Get(cbs).Value ?? default;
                texture.Sampler = refs.Sampler?.Get(cbs).Value ?? default;

                if (texture.ImageView.Handle == 0)''', '''            _cachedSubmissionCount = submissionCount;
            // RewindBox (adapt_artifact_counters): whether the element resolved last had a destroyed view (copies count too).
            bool destroyedView = false;

            for (int i = 0; i < textures.Length; i++)
            {
                ref DescriptorImageInfo texture = ref textures[i];
                ref TextureRef refs = ref _textureRefs[i];

                if (i > 0 && _textureRefs[i - 1].View == refs.View && _textureRefs[i - 1].Sampler == refs.Sampler)
                {
                    texture = textures[i - 1];
                    RenderDetail.ArrayDestroyedViewWalkElements += destroyedView ? 1 : 0;

                    continue;
                }

                texture.ImageLayout = ImageLayout.General;
                texture.ImageView = refs.View?.Get(cbs).Value ?? default;
                texture.Sampler = refs.Sampler?.Get(cbs).Value ?? default;
                // RewindBox (adapt_artifact_counters): a view held but destroyed; the element takes the dummy (black) view below.
                destroyedView = refs.View != null && texture.ImageView.Handle == 0;
                RenderDetail.ArrayDestroyedViewWalkElements += destroyedView ? 1 : 0;

                if (texture.ImageView.Handle == 0)''')
    once(array, '''            Span<DescriptorImageInfo> textures = _textures;

            for (int i = start; i < end; i++)
            {
                ref TextureRef refs = ref _textureRefs[i];

                if (i > start && _textureRefs[i - 1].View == refs.View && _textureRefs[i - 1].Sampler == refs.Sampler)
                {
                    textures[i] = textures[i - 1];

                    continue;
                }

                ImageView view = refs.View?.GetUnsafe().Value ?? default;
                Silk.NET.Vulkan.Sampler sampler = refs.Sampler?.GetUnsafe().Value ?? default;
''', '''            Span<DescriptorImageInfo> textures = _textures;
            // RewindBox (adapt_artifact_counters): whether the element resolved last had a destroyed view (copies count too).
            bool destroyedView = false;

            for (int i = start; i < end; i++)
            {
                ref TextureRef refs = ref _textureRefs[i];

                if (i > start && _textureRefs[i - 1].View == refs.View && _textureRefs[i - 1].Sampler == refs.Sampler)
                {
                    textures[i] = textures[i - 1];
                    RenderDetail.ArrayDestroyedViewRefreshElements += destroyedView ? 1 : 0;

                    continue;
                }

                ImageView view = refs.View?.GetUnsafe().Value ?? default;
                Silk.NET.Vulkan.Sampler sampler = refs.Sampler?.GetUnsafe().Value ?? default;
                // RewindBox (adapt_artifact_counters): a view held but destroyed; the element takes the dummy (black) view below.
                destroyedView = refs.View != null && view.Handle == 0;
                RenderDetail.ArrayDestroyedViewRefreshElements += destroyedView ? 1 : 0;
''')
    return list(paths.values())
