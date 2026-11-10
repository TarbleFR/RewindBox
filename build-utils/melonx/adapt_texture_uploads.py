"""Use a dedicated fence-backed staging ring for ordinary texture uploads.

TextureView.SetData previously created one native buffer, allocation and their
managed lifetime wrappers for every upload. The same render-thread operation
can reserve a slice of a lazily created texture StagingBuffer instead. Its
existing PendingCopy fence keeps the slice unavailable until the command buffer
completes. This is separate from the original vertex/buffer ring, so texture
traffic cannot displace a blocking buffer upload into a flush/wait. The new
ring costs at most 16 MiB of retained storage per renderer/session. Full rings,
large uploads and non-power-of-two texel blocks retain the original temporary
buffer path, without waiting or flushing to obtain ring space. If the optional
ring cannot allocate, disable it for this session and retain small temporaries;
device loss and errors other than allocation exhaustion still propagate.

Keep preload/current command-buffer selection and render-pass ordering. Buffer
offsets are aligned to at least 4 and the native texel-block size, including the
D24S8->D32FS8 expansion. Only power-of-two alignments use the ring's AlignUp.
Vulkan VUID-vkCmdCopyBufferToImage-dstImage-07975/07978 describes the offset
constraints (docs.vulkan.org/spec/latest/chapters/copies.html).
"""
from adapt_session import once


def apply(source):
    vulkan = source / 'src/Ryujinx.Graphics.Vulkan'
    texture = vulkan / 'TextureView.cs'
    manager = vulkan / 'BufferManager.cs'
    staging = vulkan / 'StagingBuffer.cs'
    once(staging, '        private const int BufferSize = 16 * 1024 * 1024;',
         '        internal const int BufferSize = 16 * 1024 * 1024;')
    once(staging, '''        public readonly BufferHandle Handle;
''', '''        public readonly BufferHandle Handle;

        internal bool IsValid => _buffer != null;
''')
    once(manager, '''        private readonly IdList<BufferHolder> _buffers;
''', '''        private readonly IdList<BufferHolder> _buffers;
        private StagingBuffer _textureStagingBuffer;
        private bool _textureStagingUnavailable;
''')
    once(manager, '''        public unsafe BufferHandle CreateHostImported(VulkanRenderer gd, nint pointer, int size)
''', '''        // Texture uploads have their own lazy ring: they must not consume the
        // space that PushData needs for blocking vertex/buffer uploads.
        internal StagingBuffer GetTextureStagingBuffer(VulkanRenderer gd)
        {
            if (_textureStagingUnavailable)
            {
                return null;
            }

            if (_textureStagingBuffer != null)
            {
                return _textureStagingBuffer;
            }

            try
            {
                StagingBuffer staging = new(gd, this);

                if (staging.IsValid)
                {
                    return _textureStagingBuffer = staging;
                }
            }
            catch (VulkanException exception) when (exception.ResultCode is
                Result.ErrorOutOfHostMemory or Result.ErrorOutOfDeviceMemory)
            {
                // Optional 16 MiB storage may fail while a small temporary still
                // fits. Never turn device loss into an allocation fallback.
            }

            _textureStagingUnavailable = true;
            return null;
        }

        public unsafe BufferHandle CreateHostImported(VulkanRenderer gd, nint pointer, int size)
''')
    once(manager, '''                StagingBuffer.Dispose();

                foreach (BufferHolder buffer in _buffers)
''', '''                _textureStagingBuffer?.Dispose();
                StagingBuffer.Dispose();

                foreach (BufferHolder buffer in _buffers)
''')
    once(texture, '''            int bufferDataLength = GetBufferDataLength(data.Length);

            using BufferHolder bufferHolder = _gd.BufferManager.Create(_gd, bufferDataLength);

            Auto<DisposableImage> imageAuto = GetImage();
''', '''            int bufferDataLength = GetBufferDataLength(data.Length);

            Auto<DisposableImage> imageAuto = GetImage();
''')
    once(texture, '''            CopyDataToBuffer(bufferHolder.GetDataStorage(0, bufferDataLength), data);

            VkBuffer buffer = bufferHolder.GetBuffer(cbs.CommandBuffer).Get(cbs).Value;
''', '''            int blockSize = GetBufferDataLength(Info.BytesPerPixel);
            int alignment = Math.Max((int)_gd.Capabilities.MinResourceAlignment, Math.Max(4, blockSize));
            StagingBufferReserved? reserved = bufferDataLength > 0 &&
                (uint)bufferDataLength <= StagingBuffer.BufferSize &&
                System.Numerics.BitOperations.IsPow2((uint)blockSize)
                ? _gd.BufferManager.GetTextureStagingBuffer(_gd)?.TryReserveData(cbs, bufferDataLength, alignment)
                : null;

            // Reserving does not wait: retain the previous path if the ring is
            // full, the upload is too large, or its block needs NPOT alignment.
            using BufferHolder temporary = reserved.HasValue ? null : _gd.BufferManager.Create(_gd, bufferDataLength);
            BufferHolder bufferHolder = reserved?.Buffer ?? temporary;
            int bufferOffset = reserved?.Offset ?? 0;

            CopyDataToBuffer(bufferHolder.GetDataStorage(bufferOffset, bufferDataLength), data);

            VkBuffer buffer = bufferHolder.GetBuffer(cbs.CommandBuffer).Get(cbs, bufferOffset, bufferDataLength).Value;
''')
    once(texture, '''                    region.Value.Width,
                    region.Value.Height);
''', '''                    region.Value.Width,
                    region.Value.Height,
                    bufferOffset);
''')
    once(texture, '''                CopyFromOrToBuffer(cbs.CommandBuffer, buffer, image, bufferDataLength, false, layer, level, layers, levels, singleSlice);
''', '''                CopyFromOrToBuffer(cbs.CommandBuffer, buffer, image, bufferDataLength, false, layer, level, layers, levels, singleSlice, bufferOffset);
''')
    once(texture, '''                int endOffset = offset + mipSize;

                if ((uint)endOffset > (uint)size)
''', '''                // size is the supplied byte count, independent of its offset
                // in the backing buffer (also true for CopyTo(BufferRange)).
                if ((uint)mipSize > (uint)size)
''')
    once(texture, '''                offset += mipSize;

                width = Math.Max(1, width >> 1);
''', '''                offset += mipSize;
                size -= mipSize;

                width = Math.Max(1, width >> 1);
''')
    once(texture, '''            int x,
            int y,
            int width,
            int height)
''', '''            int x,
            int y,
            int width,
            int height,
            int offset = 0)
''')
    once(texture, '''            BufferImageCopy region = new(
                0,
                (uint)AlignUpNpot(width, rowLengthAlignment),
''', '''            BufferImageCopy region = new(
                (ulong)offset,
                (uint)AlignUpNpot(width, rowLengthAlignment),
''')
    return [texture, manager, staging]
