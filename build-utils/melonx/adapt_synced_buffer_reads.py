"""A buffer flush whose GPU writes a completed WaitSync covers reads the buffer without a render-thread round trip (Core 701).

IPA 694 (Hogwarts Legacy, pid 40200, session 902CF1BC, Core 699 sync-wait attribution): BufferGetData was the second
synchronous wait of GPU.MainThread, 3 349.7 ms over 35 windows (up to 706 calls and 460.7 ms in one 5 s window) for
7.5 ms of the command itself: the wait was the render thread draining the commands queued ahead of it.

Every GetBufferData of Buffer.FlushImpl comes after a completed WaitSync of the modification it flushes:
Buffer.Flush is only the modified-range list's flush action, run by RemoveRangesAndFlush after
BufferModifiedRangeList.WaitForAndFlushRanges waited for the latest sync of the flushed ranges (directly or through a
migration span, whose source is held alive by its reference count, and BufferPreFlush, whose copies were queued
before that sync). ThreadedRenderer.WaitSync returns once the render thread has run the CreateSync command (SyncMap)
and its fence has signalled: every command queued before it, the write included, has run. The commands queued since
are not needed for this data, yet the GPU thread's InvokeCommand waited for all of them; guest threads already read
such a flush directly (the non-GPU-thread branch of ThreadedRenderer.GetBufferData).

Change: IRenderer.GetBufferDataAfterSync (default member: GetBufferData, so other renderers and doubles are
unchanged); ThreadedRenderer reads on the calling thread exactly as its non-GPU-thread branch does
(Buffers.MapBufferBlocking, which waits for a buffer still being created and fails with the renderer); Buffer.FlushImpl
uses it. The waits that make the data valid (WaitSync, the backend's own fence waits) are kept; no command, barrier or
order changes. Fail closed on drift: the files must be the Core 699 preparation's.
"""
import hashlib
from adapt_session import once

INTERFACE = 'src/Ryujinx.Graphics.GAL/IRenderer.cs'
RENDERER = 'src/Ryujinx.Graphics.GAL/Multithreading/ThreadedRenderer.cs'
BUFFER = 'src/Ryujinx.Graphics.Gpu/Memory/Buffer.cs'
BASELINE = {
    INTERFACE: '7435fb2578c74f645a5d44c269b55afa70ba267dd6c50ce40eb9ad4fe613898a',
    RENDERER: '04e29d2d861ef4da902f0b10d9176dbd3c6f9b1d814ee4f73486a7e83d142b39',
    BUFFER: '388f3a7ca9e412ea5bd55d2551911ce316078b5d63adf6adb7d2984ca16dc50f',
}

INTERFACE_OLD = '''        PinnedSpan<byte> GetBufferData(BufferHandle buffer, int offset, int size);
'''
INTERFACE_NEW = '''        PinnedSpan<byte> GetBufferData(BufferHandle buffer, int offset, int size);

        /// <summary>
        /// RewindBox (adapt_synced_buffer_reads): reads a buffer range whose GPU writes a completed WaitSync already
        /// covers (a flush of modified ranges). The same as GetBufferData unless the renderer can read it without
        /// running the commands queued since that sync.
        /// </summary>
        PinnedSpan<byte> GetBufferDataAfterSync(BufferHandle buffer, int offset, int size) => GetBufferData(buffer, offset, size);
'''

RENDERER_OLD = '''        public unsafe Capabilities GetCapabilities()
'''
RENDERER_NEW = '''        /// <summary>
        /// RewindBox (adapt_synced_buffer_reads): the caller waited for the sync of the writes it reads (WaitSync: the
        /// render thread ran every command queued before it), so the data does not depend on the commands queued since.
        /// Read on the calling thread as the non-GPU-thread branch of GetBufferData does, instead of an InvokeCommand
        /// that waits for the render thread to run them all.
        /// </summary>
        public PinnedSpan<byte> GetBufferDataAfterSync(BufferHandle buffer, int offset, int size)
        {
            return _baseRenderer.GetBufferData(Buffers.MapBufferBlocking(buffer), offset, size);
        }

        public unsafe Capabilities GetCapabilities()
'''

BUFFER_OLD = '''            using PinnedSpan<byte> data = _context.Renderer.GetBufferData(handle, offset, (int)size);

            // TODO: When write tracking shaders, they will need to be aware of changes in overlapping buffers.
'''
BUFFER_NEW = '''            // RewindBox (adapt_synced_buffer_reads): every caller runs after WaitForAndFlushRanges waited for the sync of
            // the flushed writes, so the threaded renderer reads without draining its queue.
            using PinnedSpan<byte> data = _context.Renderer.GetBufferDataAfterSync(handle, offset, (int)size);

            // TODO: When write tracking shaders, they will need to be aware of changes in overlapping buffers.
'''


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    once(paths[INTERFACE], INTERFACE_OLD, INTERFACE_NEW)
    once(paths[RENDERER], RENDERER_OLD, RENDERER_NEW)
    once(paths[BUFFER], BUFFER_OLD, BUFFER_NEW)
    return list(paths.values())
