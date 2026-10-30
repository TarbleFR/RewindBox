# Single-instruction color attachment feedback

## Retained change

`VKGSRender::snapshot_color_feedback()` already separated sampled color images
from the active attachment on MoltenVK, but only when the shader contained
multiple static sample instructions for that sampler. One instruction can read
an adjacent pixel, or several neighbors through linear filtering. The static
instruction count does not establish that reading and writing the attachment
within the same draw is safe.

On iOS, the helper now uses the same existing dynamic snapshot path for every
actual sampled attachment alias meeting its other guards. The image pointer
must equal an active color target, the view must have the color aspect, and
both image samples and surface samples-per-pixel must equal one. Non-MoltenVK,
depth, MSAA and distinct images (including a strict-mode copy already produced
by the cache) retain their existing path. Non-iOS source retains the old static
instruction filter. No new setting, diagnostic, barrier bypass or frame skip
is added.

Only `rpcs3/Emu/RSX/VK/VKDraw.cpp` changes in this renderer follow-up. The helper's
copy, layout transitions, dynamic-cache handling, sampler remapping and format
selection are otherwise unchanged. The existing descriptor remains associated
with the attachment so the next draw cannot mistake the snapshot for a static
source image.

## Reproduction and checks

`test/rpcs3_color_feedback_test.py` extracts the complete old/new production
helper and compiles it against explicit CPU image/cache adapters. The independent
oracle samples immutable pre-draw pixels, matching the semantics already chosen
by the existing multi-instruction snapshot path. A four-pixel draw is executed
in forward and reverse fragment order. One sample with an offset, and one linear
sample mixing two neighbors, each produce order-dependent pixels before the
change. The candidate matches the immutable oracle in both orders. The existing
multi-instruction cases remain correct.

The final normal and ASan/UBSan runs each exercise baseline iOS, candidate iOS
and candidate non-iOS. There are 70 candidate assertions and 68 in each other
variant; two order-dependent cases become zero only on the candidate iOS path.
Guards, format/remap changes, fresh pixels on repeated draws, layout restoration,
descriptor preservation and OOM returns are checked. An empty referenced mask
is covered by an explicit caller-contract adapter: the production callers
invoke this helper only while iterating referenced samplers. That adapter is
not presented as execution of the entire descriptor-binding method.

`non-ios-preprocessed.json` authenticates identical preprocessed extracted
programs without `RPCS3_IOS`. `rpcs3-color-feedback-final-plain` and
`rpcs3-color-feedback-final-asan` contain the final generated programs, exact
commands and results. `rpcs3-color-feedback-plain` is the intermediate
experiment before retaining the explicit non-iOS guard, with its narrower
historical scope preserved. Assertions remain active; leak detection is disabled,
so there is no LeakSanitizer claim.

## Cost and limits

The affected single-instruction alias now requests one image copy per draw,
where it previously requested none. Sixteen repeated calls request sixteen
copies and one reusable image allocation **in the cache adapter**. Actual VMA
allocations, GPU copy duration and total game copy counts are not measured by
this test. The production helper still uses the existing dynamic temporary
cache; it has not acquired a new allocation path. Multi-instruction draws have
unchanged copy counts, and nonaliases have no added copy.

This is a CPU reproduction of the ordering defect admitted by the old static
filter. It does not run Vulkan or Metal and does not identify the draw causing
Assassin's Creed's torch flicker. No physical visual correction, freeze recovery
or extra FPS is established. The additional copies may cost performance in
scenes that use this newly covered feedback path. Same-scene iPhone validation
must assess pixels and frame times together.

## Investigation not retained

Depth-write source masks were also checked against the primary
[Khronos synchronization examples](https://github.com/KhronosGroup/Vulkan-Guide/blob/main/chapters/synchronization_examples.adoc)
and [Vulkan synchronization specification](https://github.com/KhronosGroup/Vulkan-Docs/blob/main/chapters/synchronization.adoc).
The generic shadow-sampling example names both early and late fragment tests.
However, the guide separately permits a late-test source after attachment
stores, and the actual RPCS3 render passes use depth/stencil `STORE` operations
before ending the pass. This prevents identifying every late-only mask as an
actual source defect from the examined sequence. No speculative widening of
depth barriers is retained.
