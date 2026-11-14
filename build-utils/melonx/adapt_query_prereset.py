"""Occlusion queries reset ahead stay reset across a submission, so the next query does not end the render pass again.

Scope: every title with occlusion (SamplesPassed) queries; no policy flag.

IPA 740 / Core da2525a1, Hogwarts Legacy (private journal, pid 5954, "Vulkan pass and GPU detail" and "Vulkan render
stages" windows): in the 25 play windows of 5 s from 04:32:02 to 04:34:22 UTC (the 3 pause windows left out) a render
pass began again on the same framebuffer after a ReportCounter 105 to 266 times per window (1.17 to 2.71 per frame of
the window; 457, or 3.39 per frame, in the window before them, 04:31:57), out of 599 to 921 submissions per window, 0 to
36 of them with the query cause; 3 730 to 8 431 ReportCounter calls per 5 s in the five windows that log them. On the
ReportCounter path only two things end the pass: the query submission, and a query that needs its reset
(BufferedQuery.Begin -> PipelineFull.BeginQuery: EndRenderPass, vkCmdResetQueryPool, then ResetFutureCounters resets
the next free queries ahead). SubmitCommands called Gd.ResetCounterPool() at every submission:
CounterQueue.ResetSequence++ made every query reset ahead look stale, so the first occlusion query after each submission
reset again, ending the render pass when a draw had begun one, and the resets done ahead in the previous command buffer
were lost. Under MoltenVK a cut costs a render encoder, the occlusion accumulation compute encoder, a blit and a tile
store/load.

Why it is exact (prep765 sources). (1) Vulkan: query commands for one query submitted to one queue execute in submission
order, so a vkCmdResetQueryPool recorded in an earlier main command buffer precedes the vkCmdBeginQuery of a later one.
Only the render thread records into PipelineFull's command buffer; CommandBufferPool.Return submits it at once, under
the queue lock, on the one VkQueue of Gd.CommandBufferPool; the reset is recorded outside a render pass (BeginQuery ends
the pass first). Upstream before e7cf4e6e relied on the same rule: a query was reset at the start of a command buffer
and its _isReset flag, cleared only by Begin, survived later submissions. (2) A query reset ahead is a free entry of
CounterQueue._queryPool (each BufferedQuery owns a one-query VkQueryPool): nothing is recorded for it until
GetQueryObject dequeues it and BufferedQuery.Begin begins it, which clears its mark. Its previous End and copy were
recorded and executed before it came back: ReturnQueryObject runs when its event's last reference goes, after
TryConsume read the copied value (the 5 s timeout path, Invalid, is upstream's and does not change). (3) The marked
entries (_resetSequence == ResetSequence) are a prefix of the pool: ResetFutureCounters marks the first entries,
GetQueryObject dequeues the head, ReturnQueryObject enqueues unmarked entries at the tail; ResetFutureCounters runs only
from the CounterQueueEvent constructor of an occlusion query, inside QueueReport's lock (_lock, reentrant) or before the
consumer thread exists (VulkanRenderer._counters still null), so no return interleaves with its walk. Validity does not
depend on it: it means a reset ahead is never repeated, and a used-up prefix (unmarked head) takes the reset and a new
batch. With ResetCounterPool no longer called, ResetSequence stays 0 and a mark means "reset since its last use".
(4) Unchanged: the other counter types (never reset ahead, so ResetSequence never mattered to them), Reset()
(Begin(null)) and the active queries re-begun after a submission still reset in the command buffer that begins them.
Embedded MoltenVK (v1.4.2, db660224; MVKQueryPool.mm, MVKCommandEncoderState.mm): the reset fills the query's slot of
the pool's result buffer with a blit (status Initial at encode), and the result is added into that slot by a compute
atomic add at the end of the Metal render pass, or at once for an End outside a pass. That buffer is created with
newBufferWithLength and default options, so Metal tracks its hazards (only the device's temporary visibility buffer is
untracked and fenced): the fill of an earlier MTLCommandBuffer is ordered before the accumulation of a later one on the
same queue, the tracking that already orders the two encoders within one command buffer and, upstream, a copy recorded
after a submission. The reset also lists the query in the earlier command buffer, whose completion can mark it Available
early on the host; only vkGetQueryPoolResults and the compute copy path read that, and Ryujinx's copy (64-bit, stride 8,
wait, no availability bit) is the direct blit. This reverses, for the queries reset ahead only, upstream e7cf4e6e
(#4329, "Reset queries on same command buffer"), whose stated reason is validation-layer complaints, not a rule of the
specification.

Change (PipelineFull.cs, SubmitCommands): the Gd.ResetCounterPool() call, the only caller of VulkanRenderer,
Counters and CounterQueue.ResetCounterPool, is removed; those stay, uncalled. Applied after every adapter of Core
bacdcacd (PipelineFull.cs as prepared there).

Expected on the device: "same framebuffer again after ReportCounter" lower per window, down to the cuts of used-up
batches (at most 32 minus the queries since the last attachment change, else the frame prediction): between 0 and all
of the 105 to 266 per window, the journals cannot split the two; fewer vkCmdResetQueryPool; no change in the "query"
submissions. Occlusion-culled objects to be checked by eye. Not measured on an iPhone. Rollback: drop this adapter from
prepare_embedded.py and ORDER. Fail closed on drift.
"""
import hashlib
from adapt_session import once

FULL = 'src/Ryujinx.Graphics.Vulkan/PipelineFull.cs'
BASELINE = {FULL: '0a9361a026e77f6e03599590168b84eb9b642f74a88bc58fbd3fdcb15765e8ba'}

SUBMIT_OLD = '''            Gd.ResetCounterPool();

            Restore();
        }
'''
SUBMIT_NEW = '''            // RewindBox (adapt_query_prereset): the queries ResetFutureCounters reset ahead stay reset across
            // this submission (query commands of one queue execute in submission order), so the first query
            // after it does not end the render pass to reset again.
            Restore();
        }
'''

PAIRS = ((SUBMIT_OLD, SUBMIT_NEW),)


def apply(source):
    path = source / FULL
    digests = list(BASELINE.items())  # empty when the adapter control reverses this adapter
    for _, expected in digests:
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, FULL
    for old, new in PAIRS:
        once(path, old, new)
    return [path]
