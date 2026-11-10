"""Keep texel-buffer views when unrelated buffers are created.

TextureBuffer uses BufferManager.BufferCount as a conservative generation:
every buffer creation changes it, including unrelated upload/staging buffers.
The pinned SetStorage consequently disposes its VkBufferView even when its
buffer and range are unchanged. Keep the existing generation fast path, then
compare the actual holder on a generation change. A recycled handle has a new
holder and still invalidates the view. BufferHolder's native buffer is assigned
only by its constructors. No range, format, access barrier or lifetime changes.
"""
from adapt_session import once


def apply(source):
    vulkan = source / 'src/Ryujinx.Graphics.Vulkan'
    texture = vulkan / 'TextureBuffer.cs'
    manager = vulkan / 'BufferManager.cs'
    once(manager, '''        private bool TryGetBuffer(BufferHandle handle, out BufferHolder holder)
''', '''        // Identity only: callers do not acquire a new resource reference.
        internal BufferHolder GetBufferIdentity(BufferHandle handle)
        {
            return TryGetBuffer(handle, out BufferHolder holder) ? holder : null;
        }

        private bool TryGetBuffer(BufferHandle handle, out BufferHolder holder)
''')
    once(texture, '''        private int _bufferCount;
''', '''        private int _bufferCount;
        private BufferHolder _bufferIdentity;
''')
    once(texture, '''        public void SetStorage(BufferRange buffer)
        {
            if (_bufferHandle == buffer.Handle &&
                _offset == buffer.Offset &&
                _size == buffer.Size &&
                _bufferCount == _gd.BufferManager.BufferCount)
            {
                return;
            }

            _bufferHandle = buffer.Handle;
            _offset = buffer.Offset;
            _size = buffer.Size;
            _bufferCount = _gd.BufferManager.BufferCount;

            ReleaseImpl();
        }
''', '''        public void SetStorage(BufferRange buffer)
        {
            bool sameRange = _bufferHandle == buffer.Handle &&
                _offset == buffer.Offset &&
                _size == buffer.Size;
            int bufferCount = _gd.BufferManager.BufferCount;

            if (sameRange && _bufferCount == bufferCount)
            {
                return;
            }

            BufferHolder identity = _gd.BufferManager.GetBufferIdentity(buffer.Handle);
            _bufferCount = bufferCount;

            if (sameRange && ReferenceEquals(_bufferIdentity, identity))
            {
                // Other buffers were created; this view still names the same
                // native buffer. A reused handle instead has a new holder.
                return;
            }

            _bufferHandle = buffer.Handle;
            _offset = buffer.Offset;
            _size = buffer.Size;
            _bufferIdentity = identity;

            ReleaseImpl();
        }
''')
    return [texture, manager]
