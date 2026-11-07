"""A texture flush never records a copy from a destroyed image (Core 691; every title).

IPA 688 (Hogwarts Legacy, PID 31473) and IPA 690 (PID 32980, Core 689) ended with the same native crash: signal 11 at
address 0x111 in MoltenVK's MVKCmdBufferImageCopy<1>::setContent, called by vkCmdCopyImageToBuffer, on a guest thread
("RenderThread 1", "Thread_0x...AC939A0"), under the memory tracking signal handler (MeloNXCore frames of the fault
handler, then a texture flush, then the Vulkan copy). setContent dereferences one object, the image:
validate() reads MVKImage::_hasExpectedTexelSize (MoltenVK v1.4.2, MVKCmdTransfer.mm), at offset 0x111 of a null
MVKImage. The image handle the Core passed was VK_NULL_HANDLE.

Cause in the Core: a guest CPU access to GPU-modified memory runs TextureGroup.FlushAction on that guest thread
(BackgroundContextAction runs it there, not on the render thread). It reads Storage.GetFlushTexture() and calls
ThreadedTexture.GetData(), which calls the Vulkan TextureView directly, concurrently with the render thread. The GPU
thread may meanwhile have replaced or disposed that host texture (Texture.ReplaceStorage / DisposeTextures queue its
Release); the render thread then disposes the view and storage, and Auto<DisposableImage>.DecrementReferenceCount sets
the value to default once the last reference goes. PersistentFlushBuffer.GetTextureData then reads
view.GetImage().Get(cbs).Value: Get returns that default value for a destroyed Auto, an image handle of 0, which
vkCmdCopyImageToBuffer receives.

Change:
- Ryujinx.Graphics.GAL: TextureReleasedException.
- PersistentFlushBuffer.GetTextureData (both overloads): the image's Auto is referenced (TryIncrementReferenceCount)
  before the copy is recorded and released after its submission, so the render thread cannot destroy it in between;
  if it is already destroyed, no command is recorded and TextureReleasedException is thrown.
- TextureView.CopyTo(BufferRange) (render thread, GPU read-backs): a destroyed image records no copy (counted).
- Texture.GetTextureDataFromGpu / GetTextureDataSliceFromGpu: a TextureReleasedException leaves the output (guest
  memory for a flush) unchanged and is counted; the first and every 64th are logged. The released texture's data is
  gone either way; the change replaces a process crash with no write.
Nothing else changes for a live texture. Not measured on an iPhone. Fail closed on drift: the four files must be the
Core 689 preparation's.
"""
import hashlib
from adapt_session import once

GAL = 'src/Ryujinx.Graphics.GAL/ITexture.cs'
FLUSH = 'src/Ryujinx.Graphics.Vulkan/PersistentFlushBuffer.cs'
VIEW = 'src/Ryujinx.Graphics.Vulkan/TextureView.cs'
TEXTURE = 'src/Ryujinx.Graphics.Gpu/Image/Texture.cs'
BASELINE = {
    GAL: 'bebb69971eaf9f1f3947e94e30115a0e6c477e4fed95a188b18aa325fa38369b',
    FLUSH: '1906acde917876bdbd0ec4f929834b57567a98352b5920fd8cf532b4e66b6f65',
    VIEW: 'c7ecc07151a14de6dbbb2650c4d4007f99f170b95009f900081d305d665dcf9c',
    TEXTURE: '1b8b8696f3ab803249f127ed83c86b3aa468578bce9718a03c138ff29588fb77',
}

GAL_OLD = '''        void Release();
    }
}
'''
GAL_NEW = '''        void Release();
    }

    /// <summary>
    /// RewindBox (adapt_released_texture_flush): the host texture was destroyed before its data could be read back.
    /// </summary>
    public sealed class TextureReleasedException : System.InvalidOperationException
    {
        public TextureReleasedException() : base("The host texture was released before its data was read back.")
        {
        }
    }
}
'''

FLUSH_FULL_OLD = '''            BufferHolder flushStorage = ResizeIfNeeded(size);

            using (CommandBufferScoped cbs = cbp.Rent())
            {
                Buffer buffer = flushStorage.GetBuffer(cbs.CommandBuffer).Get(cbs).Value;
                Image image = view.GetImage().Get(cbs).Value;

                view.CopyFromOrToBuffer(cbs.CommandBuffer, buffer, image, size, true, 0, 0, info.GetLayers(), info.Levels, singleSlice: false);
            }
'''
FLUSH_FULL_NEW = '''            BufferHolder flushStorage = ResizeIfNeeded(size);
            Auto<DisposableImage> imageAuto = AcquireImage(view);

            try
            {
                using (CommandBufferScoped cbs = cbp.Rent())
                {
                    Buffer buffer = flushStorage.GetBuffer(cbs.CommandBuffer).Get(cbs).Value;
                    Image image = imageAuto.Get(cbs).Value;

                    view.CopyFromOrToBuffer(cbs.CommandBuffer, buffer, image, size, true, 0, 0, info.GetLayers(), info.Levels, singleSlice: false);
                }
            }
            finally
            {
                imageAuto.DecrementReferenceCount();
            }
'''
FLUSH_SLICE_OLD = '''            BufferHolder flushStorage = ResizeIfNeeded(size);

            using (CommandBufferScoped cbs = cbp.Rent())
            {
                Buffer buffer = flushStorage.GetBuffer(cbs.CommandBuffer).Get(cbs).Value;
                Image image = view.GetImage().Get(cbs).Value;

                view.CopyFromOrToBuffer(cbs.CommandBuffer, buffer, image, size, true, layer, level, 1, 1, singleSlice: true);
            }
'''
FLUSH_SLICE_NEW = '''            BufferHolder flushStorage = ResizeIfNeeded(size);
            Auto<DisposableImage> imageAuto = AcquireImage(view);

            try
            {
                using (CommandBufferScoped cbs = cbp.Rent())
                {
                    Buffer buffer = flushStorage.GetBuffer(cbs.CommandBuffer).Get(cbs).Value;
                    Image image = imageAuto.Get(cbs).Value;

                    view.CopyFromOrToBuffer(cbs.CommandBuffer, buffer, image, size, true, layer, level, 1, 1, singleSlice: true);
                }
            }
            finally
            {
                imageAuto.DecrementReferenceCount();
            }
'''
FLUSH_DISPOSE_OLD = '''        public void Dispose()
        {
            _flushStorage.Dispose();
        }
'''
FLUSH_DISPOSE_NEW = '''        /// <summary>
        /// RewindBox (adapt_released_texture_flush): a guest thread flushes concurrently with the render thread, which may
        /// have destroyed the view's image (its Auto then returns a null handle). The image is referenced for the copy, so
        /// it cannot be destroyed while the copy is recorded; a destroyed one records nothing.
        /// </summary>
        private static Auto<DisposableImage> AcquireImage(TextureView view)
        {
            Auto<DisposableImage> imageAuto = view.GetImage();

            if (!imageAuto.TryIncrementReferenceCount())
            {
                throw new Ryujinx.Graphics.GAL.TextureReleasedException();
            }

            return imageAuto;
        }

        public void Dispose()
        {
            _flushStorage.Dispose();
        }
'''

VIEW_OLD = '''            int outSize = Info.GetMipSize(level);
            int hostSize = GetBufferDataLength(outSize);

            Image image = GetImage().Get(cbs).Value;
            int offset = range.Offset;
'''
VIEW_NEW = '''            int outSize = Info.GetMipSize(level);
            int hostSize = GetBufferDataLength(outSize);

            Image image = GetImage().Get(cbs).Value;
            int offset = range.Offset;

            // RewindBox (adapt_released_texture_flush): a destroyed image (null handle) records no copy.
            if (image.Handle == 0)
            {
                System.Threading.Interlocked.Increment(ref ReleasedImageCopiesSkipped);
                return;
            }
'''
VIEW_FIELD_OLD = '''        public PinnedSpan<byte> GetData()
        {
'''
VIEW_FIELD_NEW = '''        // RewindBox (adapt_released_texture_flush): copies to a buffer skipped because the image was already destroyed.
        public static long ReleasedImageCopiesSkipped;

        public PinnedSpan<byte> GetData()
        {
'''

TEX_FULL_OLD = '''        private void GetTextureDataFromGpu(Span<byte> output, bool blacklist, ITexture texture = null)
        {
'''
TEX_FULL_NEW = '''        private void GetTextureDataFromGpu(Span<byte> output, bool blacklist, ITexture texture = null)
        {
            // RewindBox (adapt_released_texture_flush): a host texture destroyed before the read-back leaves the output.
            try
            {
                GetTextureDataFromGpuUnguarded(output, blacklist, texture);
            }
            catch (TextureReleasedException)
            {
                NoteReleasedFlush();
            }
        }

        // RewindBox (adapt_released_texture_flush): flushes of a host texture destroyed before its read-back.
        private static long _releasedFlushes;

        private static void NoteReleasedFlush()
        {
            long count = System.Threading.Interlocked.Increment(ref _releasedFlushes);

            if (count == 1 || count % 64 == 0)
            {
                Logger.Warning?.Print(LogClass.Gpu, $"Texture flush skipped: its host texture was released before the read-back ({count}).");
            }
        }

        private void GetTextureDataFromGpuUnguarded(Span<byte> output, bool blacklist, ITexture texture = null)
        {
'''
TEX_SLICE_OLD = '''        public void GetTextureDataSliceFromGpu(Span<byte> output, int layer, int level, bool blacklist, ITexture texture = null)
        {
'''
TEX_SLICE_NEW = '''        public void GetTextureDataSliceFromGpu(Span<byte> output, int layer, int level, bool blacklist, ITexture texture = null)
        {
            // RewindBox (adapt_released_texture_flush): a host texture destroyed before the read-back leaves the output.
            try
            {
                GetTextureDataSliceFromGpuUnguarded(output, layer, level, blacklist, texture);
            }
            catch (TextureReleasedException)
            {
                NoteReleasedFlush();
            }
        }

        private void GetTextureDataSliceFromGpuUnguarded(Span<byte> output, int layer, int level, bool blacklist, ITexture texture = null)
        {
'''


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    once(paths[GAL], GAL_OLD, GAL_NEW)
    once(paths[FLUSH], FLUSH_FULL_OLD, FLUSH_FULL_NEW)
    once(paths[FLUSH], FLUSH_SLICE_OLD, FLUSH_SLICE_NEW)
    once(paths[FLUSH], FLUSH_DISPOSE_OLD, FLUSH_DISPOSE_NEW)
    once(paths[VIEW], VIEW_FIELD_OLD, VIEW_FIELD_NEW)
    once(paths[VIEW], VIEW_OLD, VIEW_NEW)
    once(paths[TEXTURE], TEX_FULL_OLD, TEX_FULL_NEW)
    once(paths[TEXTURE], TEX_SLICE_OLD, TEX_SLICE_NEW)
    return list(paths.values())
