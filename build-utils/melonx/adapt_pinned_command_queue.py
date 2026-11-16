"""The threaded renderer's command queue is allocated on the pinned object heap, so a compacting collection cannot move it
while the GPU thread writes a command through the raw pointer New<T> handed out (every title).

Evidence (IPA 748-751 / Core 030cc14f, private journals; counts only): ThreadedRenderer's constructor allocates the
command queue as a plain byte array of _elementSize * 10 000 bytes (large object heap, not pinned). New<T> returns a
pointer into it (Unsafe.AsPointer of the slot's span) and the caller then writes the command through that pointer with
Set(...): ThreadedPipeline.cs makes 59 such New calls, 12 of them with a Ref(...) argument and 8 with a CopySpan(...)
argument, evaluated between New and the end of Set (an allocation, so a GC safe point). RewindBox compacts the heap in
play: one compaction in a presentation gap per session in 12550, 12613 and 14991, started off the GPU thread. If the
array moved inside that window, the command would be written to the old address and the render thread would read a
stale slot. No exception, no crash and no corrupted command were seen: a latent hazard, not an observed failure.

Change (ThreadedRenderer.cs, constructor): _commandQueue = GC.AllocateArray<byte>(_elementSize * QueueCount, pinned:
true). Same length, zeroed as `new byte[]` is (plan 748 rank 17 named AllocateUninitializedArray; the zeroed form keeps
the queue's first-lap content identical to today's, for every command whose Set leaves a byte unwritten). The array never
moves, so the pointer New<T> returns stays valid; nothing else changes: the slots, New<T> (still the only place a raw
pointer into the queue is made), the render loop and the reference table (_refQueue holds objects and stays movable).

Host proof (gate sync-wait-attribution, final preparation, production GAL with a backend double): the fixture's queue
(800 000 bytes) is on the pinned object heap after a compacting full collection (808 208 bytes there, 8 184 in the
control), zeroed before any command and not moved; the render work lines and the synchronous-wait attribution are the
candidate's. Fixture figures, not a device measure.

Scope: every title (the threaded backend). Bound (plan 748 rank 17): no effect observed and none claimed; it removes a
hazard of one compaction per session in play. Memory: the same bytes, on the pinned object heap instead of the large
object heap, for the renderer's life. Expected on the device: nothing in the logs. Not measured on an iPhone.
First of the ThreadedRenderer.cs edits after Core 030cc14f (adapt_render_command_clock takes its post-image; the staged,
unwired adapt_render_command_longest anchors on Core 030cc14f's text and would need its BASELINE rebased onto the last of
these). Rollback: drop this adapter from prepare_embedded.py and ORDER, and rebase adapt_render_command_clock's BASELINE
on Core 030cc14f's ThreadedRenderer.cs (50505d0b...). Fail closed on drift.
"""
import hashlib
from adapt_session import once

RENDERER = 'src/Ryujinx.Graphics.GAL/Multithreading/ThreadedRenderer.cs'
BASELINE = {RENDERER: '50505d0b7a72a65ae1320df30b5e3e7e3378bbf34012d16677ac31d97d62d760'}  # Core 030cc14f

QUEUE_OLD = '''            _commandQueue = new byte[_elementSize * QueueCount];
'''
QUEUE_NEW = '''            // RewindBox (adapt_pinned_command_queue): on the pinned object heap, zeroed as before. New<T> hands out a raw
            // pointer into this array that the GPU thread writes through after GC safe points (Ref, CopySpan arguments): a
            // compacting collection must not move it in between.
            _commandQueue = GC.AllocateArray<byte>(_elementSize * QueueCount, pinned: true);
'''

PAIRS = ((QUEUE_OLD, QUEUE_NEW),)


def apply(source):
    path = source / RENDERER
    digests = list(BASELINE.items())  # empty when the adapter control reverses this adapter
    for _, expected in digests:
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, RENDERER
    # New<T> is the only place a raw pointer into the queue is made, and the queue is assigned once (the constructor).
    text = path.read_text(encoding='utf-8-sig')
    assert not digests or (text.count('Unsafe.AsPointer(') == 1 and text.count('_commandQueue = ') == 1 and
                           text.count('Span<byte> memory = new(_commandQueue, taken * _elementSize, _elementSize);') == 1), RENDERER
    for old, new in PAIRS:
        once(path, old, new)
    return [path]
