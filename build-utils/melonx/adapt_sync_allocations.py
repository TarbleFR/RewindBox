"""Keep GPU sync semantics while avoiding repeated allocation and prefix copies.

Sync handles are enqueued and only retired from the head. A Queue keeps that
order without shifting every survivor for every completed handle. The flush
callback is allocated only when an interrupt is actually requested; previously
its captured local forced a display class even for absent/already-flushed IDs.
Buffer-usage queries compute their shared page interval once, preserving all
sixteen command-buffer bitmap checks and the original integer arithmetic.
"""
import hashlib
from adapt_session import once


def apply(source):
    directory = source / 'src/Ryujinx.Graphics.Vulkan'
    sync = directory / 'SyncManager.cs'
    bitmap = directory / 'BufferUsageBitmap.cs'
    for path, expected in ((sync, 'fcbee4e89cf44eba0b4a39fbd5b6331d29b25126a3dd9a0ed17ab9cd095bdfec'),
                           (bitmap, 'f205e7787ecd8699117bc32771218191c3617861888afda260c1bf28411ea663')):
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, str(path)
    once(sync, 'using System.Linq;\n', '')
    once(sync, 'private readonly List<SyncHandle> _handles;', 'private readonly Queue<SyncHandle> _handles;')
    once(sync, '            _handles = [];', '            _handles = new();')
    once(sync, '                _handles.Add(handle);', '                _handles.Enqueue(handle);')
    once(sync, '                    first = _handles.FirstOrDefault();', '                    _handles.TryPeek(out first);')
    once(sync, '                            _handles.RemoveAt(0);', '                            _handles.Dequeue();')
    once(sync, '''                    _gd.InterruptAction(() =>
                    {
                        if (result.NeedsFlush(_flushId))
                        {
                            _gd.FlushAllCommands();
                        }
                    });''', '''                    RequestFlush(result);''')
    once(sync, '        public void Cleanup()\n', '''        private void RequestFlush(SyncHandle handle)
        {
            // Keep the captured owner/handle private to an actual request.
            // A delayed callback must still recheck the latest flush ID.
            _gd.InterruptAction(() =>
            {
                if (handle.NeedsFlush(_flushId))
                {
                    _gd.FlushAllCommands();
                }
            });
        }

        public void Cleanup()
''')
    once(bitmap, '''        public bool OverlapsWith(int offset, int size, bool write)
        {
            for (int i = 0; i < CommandBufferPool.MaxCommandBuffers; i++)
            {
                if (OverlapsWith(i, offset, size, write))
                {
                    return true;
                }
            }

            return false;
        }''', '''        public bool OverlapsWith(int offset, int size, bool write)
        {
            if (size == 0)
            {
                return false;
            }

            int start = offset / _granularity;
            int end = (offset + size - 1) / _granularity;

            for (int i = 0; i < CommandBufferPool.MaxCommandBuffers; i++)
            {
                int cbBase = i * _bitsPerCb + (write ? _writeBitOffset : 0);

                if (_bitmap.IsSet(cbBase + start, cbBase + end))
                {
                    return true;
                }
            }

            return false;
        }''')
    return [sync, bitmap]
