"""Apply the Vulkan buffer and descriptor fixes to the exact build 777 sources."""
import hashlib

from adapt_session import once

GPU = 'src/Ryujinx.Graphics.Vulkan/'
BASELINE = {
    GPU + 'BufferHolder.cs': '995109150bf1b68f5c03d895833b17fd6f7fdd3cd3b3d2da361d7949a190e834',
    GPU + 'PipelineFull.cs': '42998032a55d518b8f49a1a11ff78ad2a4f22eaa4898a877760e05afcc323b9b',
    GPU + 'BitMapStruct.cs': '7abb5cef85fc75a8e196f94c2c2e3234a2ff66f2fe8d32afc16e24489dd14ee8',
    GPU + 'DescriptorSetUpdater.cs': '655003ffedb12032b15da14ff19027239861d1febd962973897969f6def048dc',
    GPU + 'ShaderCollection.cs': 'ee23e7d16f6aab6578ccf46310d0854ed149ab60171fca660bba744de7273ca8',
}


def apply(source):
    for name, expected in BASELINE.items():
        assert hashlib.sha256((source / name).read_bytes()).hexdigest() == expected, name

    once(source / (GPU + 'BufferHolder.cs'), '''        private FenceHolder _flushFence;
        private int _flushWaiting;

        private byte[] _pendingData;
        private bool _mirrorCopyCountedOut; // RewindBox (adapt_mirror_copy_journal)
        private BufferMirrorRangeList _pendingDataRanges;
        private Dictionary<ulong, StagingBufferReserved> _mirrors;
''', '''        private FenceHolder _flushFence;
        private int _flushWaiting;

        // Small edits to a large, in-flight buffer initially keep just one movable window.
        // Promote once if simultaneously pending writes cannot fit. Uploads still use contiguous spans.
        private const int MirrorWindowBytes = 16 * 1024;
        private byte[] _pendingData;
        private int _pendingDataOffset;
        private bool _mirrorCopyCountedOut; // RewindBox (adapt_mirror_copy_journal)
        private BufferMirrorRangeList _pendingDataRanges;
        private Dictionary<ulong, StagingBufferReserved> _mirrors;
''')

    once(source / (GPU + 'BufferHolder.cs'), '''            return ((int)(key >> 32), (int)key);
        }

        private unsafe bool TryGetMirror(CommandBufferScoped cbs, ref int offset, int size, out Auto<DisposableBuffer> buffer)
        {
            size = Math.Min(size, Size - offset);
''', '''            return ((int)(key >> 32), (int)key);
        }

        private Span<byte> PendingWriteSpan(int offset, int length)
        {
            if (_pendingData == null)
            {
                int capacity = Size >= 85000 && length <= MirrorWindowBytes ? MirrorWindowBytes : Size;
                _pendingData = new byte[capacity];
                _pendingDataOffset = capacity == Size ? 0 : Math.Min(offset, Size - capacity);
                _mirrors = new Dictionary<ulong, StagingBufferReserved>();
                MirrorCopyJournal.Added(capacity);
            }
            else if (offset < _pendingDataOffset || offset - _pendingDataOffset > _pendingData.Length - length)
            {
                if (length <= _pendingData.Length && _pendingDataRanges.Count() == 0)
                {
                    _pendingDataOffset = Math.Min(offset, Size - _pendingData.Length);
                }
                else
                {
                    byte[] previous = _pendingData;
                    byte[] full = new byte[Size];
                    previous.AsSpan().CopyTo(full.AsSpan(_pendingDataOffset));
                    _pendingData = full;
                    _pendingDataOffset = 0;
                    MirrorCopyJournal.Added(full.Length, previous.Length);
                }
            }

            return _pendingData.AsSpan(offset - _pendingDataOffset, length);
        }

        // TryGetMirror has already checked both a dirty overlap and the GPU write fence.
        // Every dirty byte is inside the window. Read only clean bytes from the mapped buffer.
        private void FillMirror(Span<byte> mapped, int offset, Span<byte> target)
        {
            int start = Math.Max(offset, _pendingDataOffset);
            int end = Math.Min(offset + target.Length, _pendingDataOffset + _pendingData.Length);
            int prefix = start - offset;
            int length = end - start;
            mapped[..prefix].CopyTo(target);
            _pendingDataRanges.FillData(mapped.Slice(prefix, length),
                _pendingData.AsSpan(start - _pendingDataOffset, length), start, target.Slice(prefix, length));
            mapped[(end - offset)..].CopyTo(target[(end - offset)..]);
        }

        private unsafe bool TryGetMirror(CommandBufferScoped cbs, ref int offset, int size, out Auto<DisposableBuffer> buffer)
        {
            size = Math.Min(size, Size - offset);
''')

    once(source / (GPU + 'BufferHolder.cs'), '''            // Build data for the new mirror.

            Span<byte> baseData = new((void*)(_map + offset), size);
            Span<byte> modData = _pendingData.AsSpan(offset, size);

            StagingBufferReserved? newMirror = _gd.BufferManager.StagingBuffer.TryReserveData(cbs, size);

            if (newMirror != null)
            {
                StagingBufferReserved mirror = newMirror.Value;
                _pendingDataRanges.FillData(baseData, modData, offset, new Span<byte>((void*)(mirror.Buffer._map + mirror.Offset), size));

                if (_mirrors.Count == 0)
                {
''', '''            // Build data for the new mirror.

            Span<byte> baseData = new((void*)(_map + offset), size);

            StagingBufferReserved? newMirror = _gd.BufferManager.StagingBuffer.TryReserveData(cbs, size);

            if (newMirror != null)
            {
                StagingBufferReserved mirror = newMirror.Value;
                FillMirror(baseData, offset, new Span<byte>((void*)(mirror.Buffer._map + mirror.Offset), size));

                if (_mirrors.Count == 0)
                {
''')

    once(source / (GPU + 'BufferHolder.cs'), '''
                    if (_gd.PipelineInternal.CurrentCommandBuffer.CommandBuffer.Handle == cbs.CommandBuffer.Handle)
                    {
                        SetData(rangeOffset, _pendingData.AsSpan(rangeOffset, rangeSize), cbs, _gd.PipelineInternal.EndRenderPassDelegate, false);
                    }
                    else
                    {
                        SetData(rangeOffset, _pendingData.AsSpan(rangeOffset, rangeSize), cbs, null, false);
                    }
                }
            }
''', '''
                    if (_gd.PipelineInternal.CurrentCommandBuffer.CommandBuffer.Handle == cbs.CommandBuffer.Handle)
                    {
                        SetData(rangeOffset, _pendingData.AsSpan(rangeOffset - _pendingDataOffset, rangeSize), cbs, _gd.PipelineInternal.EndRenderPassDelegate, false);
                    }
                    else
                    {
                        SetData(rangeOffset, _pendingData.AsSpan(rangeOffset - _pendingDataOffset, rangeSize), cbs, null, false);
                    }
                }
            }
''')

    once(source / (GPU + 'BufferHolder.cs'), '''
        public bool RemoveOverlappingMirrors(int offset, int size)
        {
            List<ulong> toRemove = null;
            foreach (ulong key in _mirrors.Keys)
            {
                (int keyOffset, int keySize) = FromMirrorKey(key);
                if (!(offset + size <= keyOffset || offset >= keyOffset + keySize))
                {
                    toRemove ??= [];

                    toRemove.Add(key);
                }
            }

            if (toRemove != null)
            {
                foreach (ulong key in toRemove)
                {
                    _mirrors.Remove(key);
                }

                return true;
            }

            return false;
        }

        public unsafe void SetData(int offset, ReadOnlySpan<byte> data, CommandBufferScoped? cbs = null, Action endRenderPass = null, bool allowCbsWait = true)
''', '''
        public bool RemoveOverlappingMirrors(int offset, int size)
        {
            bool removed = false;
            foreach (ulong key in _mirrors.Keys)
            {
                (int keyOffset, int keySize) = FromMirrorKey(key);
                if (offset < (long)keyOffset + keySize && keyOffset < (long)offset + size)
                {
                    // Dictionary.Remove preserves the active enumerator on .NET 10.
                    removed |= _mirrors.Remove(key);
                }
            }

            return removed;
        }

        public unsafe void SetData(int offset, ReadOnlySpan<byte> data, CommandBufferScoped? cbs = null, Action endRenderPass = null, bool allowCbsWait = true)
''')

    once(source / (GPU + 'BufferHolder.cs'), '''            // If the buffer does not have an in-flight write (including an inline update), then upload data to a pendingCopy.
            if (allowMirror && !_waitable.IsBufferRangeInUse(offset, dataSize, true))
            {
                if (_pendingData == null)
                {
                    _pendingData = new byte[Size];
                    _mirrors = new Dictionary<ulong, StagingBufferReserved>();
                    MirrorCopyJournal.Added(Size); // RewindBox (adapt_mirror_copy_journal)
                }

                data[..dataSize].CopyTo(_pendingData.AsSpan(offset, dataSize));
                _pendingDataRanges.Add(offset, dataSize);

                // Remove any overlapping mirrors.
''', '''            // If the buffer does not have an in-flight write (including an inline update), then upload data to a pendingCopy.
            if (allowMirror && !_waitable.IsBufferRangeInUse(offset, dataSize, true))
            {
                data[..dataSize].CopyTo(PendingWriteSpan(offset, dataSize));
                _pendingDataRanges.Add(offset, dataSize);

                // Remove any overlapping mirrors.
''')

    once(source / (GPU + 'BufferHolder.cs'), '''            if (_pendingData != null)
            {
                _pendingDataRanges.Remove(offset, dataSize);
            }

            if (cbs != null &&
''', '''            if (_pendingData != null)
            {
                _pendingDataRanges.Remove(offset, dataSize);
                if (RemoveOverlappingMirrors(offset, dataSize))
                {
                    _gd.PipelineInternal.Rebind(_buffer, offset, dataSize);
                }
            }

            if (cbs != null &&
''')

    once(source / (GPU + 'BufferHolder.cs'), '''            if (_pendingData != null && !_mirrorCopyCountedOut)
            {
                _mirrorCopyCountedOut = true;
                MirrorCopyJournal.Removed(Size);
            }

            _gd.PipelineInternal?.FlushCommandsIfWeightExceeding(_buffer, (ulong)Size);
''', '''            if (_pendingData != null && !_mirrorCopyCountedOut)
            {
                _mirrorCopyCountedOut = true;
                MirrorCopyJournal.Removed(_pendingData.Length);
            }

            _gd.PipelineInternal?.FlushCommandsIfWeightExceeding(_buffer, (ulong)Size);
''')

    once(source / (GPU + 'BufferHolder.cs'), '''    }

    /// <summary>
    /// RewindBox (adapt_mirror_copy_journal): the managed copies of whole buffers that hold mirror data (BufferHolder's
    /// _pendingData), counted for the journal only. IPA 759, Hogwarts Legacy: 275 to 277 MiB of live large object heap
    /// beside 246 MiB of mapped Vulkan buffers; what part of it these copies are was not known. A record each time the
    /// bytes held reach a new 16 MiB step, at most 32 per process.
''', '''    }

    /// <summary>
    /// RewindBox (adapt_mirror_copy_journal): the managed arrays that hold mirror data (BufferHolder's
    /// _pendingData), counted for the journal only. IPA 759, Hogwarts Legacy: 275 to 277 MiB of live large object heap
    /// beside 246 MiB of mapped Vulkan buffers; what part of it these copies are was not known. A record each time the
    /// bytes held reach a new 16 MiB step, at most 32 per process.
''')

    once(source / (GPU + 'BufferHolder.cs'), '''        private static long _nextReport = ReportStep;
        private static int _reports;

        public static void Added(int size)
        {
            Interlocked.Increment(ref _buffers);

            if (size >= LargeObjectBytes)
            {
''', '''        private static long _nextReport = ReportStep;
        private static int _reports;

        public static void Added(int size, int previousSmallWindow = 0)
        {
            if (previousSmallWindow == 0)
            {
                Interlocked.Increment(ref _buffers);
            }

            if (size >= LargeObjectBytes)
            {
''')

    once(source / (GPU + 'BufferHolder.cs'), '''                Interlocked.Add(ref _largeBytes, size);
            }

            long bytes = Interlocked.Add(ref _bytes, size);

            if (bytes < Volatile.Read(ref _nextReport))
            {
''', '''                Interlocked.Add(ref _largeBytes, size);
            }

            long bytes = Interlocked.Add(ref _bytes, size - previousSmallWindow);

            if (bytes < Volatile.Read(ref _nextReport))
            {
''')

    once(source / (GPU + 'BufferHolder.cs'), '''        {
            System.Globalization.CultureInfo invariant = System.Globalization.CultureInfo.InvariantCulture;

            return Volatile.Read(ref _buffers).ToString(invariant) + " buffers hold a managed copy of their whole size for mirror data: " +
                (bytes / (1024.0 * 1024.0)).ToString("F1", invariant) + " MiB, of which " +
                (Volatile.Read(ref _largeBytes) / (1024.0 * 1024.0)).ToString("F1", invariant) + " MiB in " +
                Volatile.Read(ref _largeBuffers).ToString(invariant) +
''', '''        {
            System.Globalization.CultureInfo invariant = System.Globalization.CultureInfo.InvariantCulture;

            return Volatile.Read(ref _buffers).ToString(invariant) + " buffers hold managed backing for mirror data: " +
                (bytes / (1024.0 * 1024.0)).ToString("F1", invariant) + " MiB, of which " +
                (Volatile.Read(ref _largeBytes) / (1024.0 * 1024.0)).ToString("F1", invariant) + " MiB in " +
                Volatile.Read(ref _largeBuffers).ToString(invariant) +
''')

    once(source / (GPU + 'PipelineFull.cs'), '''        private CounterQueueEvent _activeConditionalRender;

        private readonly List<BufferedQuery> _pendingQueryCopies;
        private readonly List<BufferHolder> _activeBufferMirrors;

        private ulong _byteWeight;

''', '''        private CounterQueueEvent _activeConditionalRender;

        private readonly List<BufferedQuery> _pendingQueryCopies;
        private readonly HashSet<BufferHolder> _activeBufferMirrors;

        private ulong _byteWeight;

''')

    once(source / (GPU + 'BitMapStruct.cs'), '''
        public void SignalSet(Action<int, int> action)
        {
            // Iterate the set bits in the result, and signal them.

            int offset = 0;
''', '''
        public void SignalSet(Action<int, int> action)
        {
            SignalSet(action, static (binding, callback) => callback(binding, 1));
        }

        public void SignalSet<TState>(TState state, Action<int, TState> action)
        {
            // Iterate the set bits in the result, and signal them.

            int offset = 0;
''')

    once(source / (GPU + 'BitMapStruct.cs'), '''                {
                    int bit = BitOperations.TrailingZeroCount((ulong)value);

                    action(offset + bit, 1);

                    value &= ~(1L << bit);
                }
''', '''                {
                    int bit = BitOperations.TrailingZeroCount((ulong)value);

                    action(offset + bit, state);

                    value &= ~(1L << bit);
                }
''')

    once(source / (GPU + 'DescriptorSetUpdater.cs'), '''        private bool _updateDescriptorCacheCbIndex;

        [Flags]
        private enum DirtyFlags
        {
            None = 0,
            Uniform = 1 << 0,
''', '''        private bool _updateDescriptorCacheCbIndex;

        [Flags]
        internal enum DirtyFlags
        {
            None = 0,
            Uniform = 1 << 0,
''')

    once(source / (GPU + 'DescriptorSetUpdater.cs'), '''
            // Check stage bindings

            _uniformMirrored.Union(_uniformSet).SignalSet((int binding, int count) =>
            {
                for (int i = 0; i < count; i++)
                {
                    ref BufferRef bufferRef = ref _uniformBufferRefs[binding];
                    if (bufferRef.Buffer == buffer)
                    {
                        ref DescriptorBufferInfo info = ref _uniformBuffers[binding];
                        int bindingOffset = bufferRef.Offset;

                        if (BindingOverlaps(ref info, bindingOffset, offset, size))
                        {
                            _uniformSet.Clear(binding);
                            _uniformSetPd[binding] = 0;
                            SignalDirty(DirtyFlags.Uniform);
                        }
                    }

                    binding++;
                }
            });

            _storageMirrored.Union(_storageSet).SignalSet((int binding, int count) =>
            {
                for (int i = 0; i < count; i++)
                {
                    ref BufferRef bufferRef = ref _storageBufferRefs[binding];
                    if (bufferRef.Buffer == buffer)
                    {
                        ref DescriptorBufferInfo info = ref _storageBuffers[binding];
                        int bindingOffset = bufferRef.Offset;

                        if (BindingOverlaps(ref info, bindingOffset, offset, size))
                        {
                            _storageSet.Clear(binding);
                            SignalDirty(DirtyFlags.Storage);
                        }
                    }

                    binding++;
                }
            });
        }
''', '''
            // Check stage bindings

            var state = (Updater: this, Buffer: buffer, Offset: offset, Size: size);
            _uniformMirrored.Union(_uniformSet).SignalSet(state, static (binding, s) =>
            {
                ref BufferRef bufferRef = ref s.Updater._uniformBufferRefs[binding];
                if (bufferRef.Buffer == s.Buffer)
                {
                    ref DescriptorBufferInfo info = ref s.Updater._uniformBuffers[binding];
                    int bindingOffset = bufferRef.Offset;

                    if (BindingOverlaps(ref info, bindingOffset, s.Offset, s.Size))
                    {
                        s.Updater._uniformSet.Clear(binding);
                        s.Updater._uniformSetPd[binding] = 0;
                        s.Updater.SignalDirty(DirtyFlags.Uniform);
                    }
                }
            });

            _storageMirrored.Union(_storageSet).SignalSet(state, static (binding, s) =>
            {
                ref BufferRef bufferRef = ref s.Updater._storageBufferRefs[binding];
                if (bufferRef.Buffer == s.Buffer)
                {
                    ref DescriptorBufferInfo info = ref s.Updater._storageBuffers[binding];
                    int bindingOffset = bufferRef.Offset;

                    if (BindingOverlaps(ref info, bindingOffset, s.Offset, s.Size))
                    {
                        s.Updater._storageSet.Clear(binding);
                        s.Updater.SignalDirty(DirtyFlags.Storage);
                    }
                }
            });
        }
''')

    once(source / (GPU + 'DescriptorSetUpdater.cs'), '''            {
                RenderDetail.SameProgramSets++;
                _updateDescriptorCacheCbIndex = true;
                _dirty |= BufferViewSets(program);
                return;
            }

''', '''            {
                RenderDetail.SameProgramSets++;
                _updateDescriptorCacheCbIndex = true;
                _dirty |= program.BufferViewDirtyFlags;
                return;
            }

''')

    once(source / (GPU + 'DescriptorSetUpdater.cs'), '''            _dirty = DirtyFlags.All;
        }

        private static DirtyFlags BufferViewSets(ShaderCollection program)
        {
            DirtyFlags flags = DirtyFlags.None;

            foreach (ResourceBindingSegment segment in program.BindingSegments[PipelineBase.TextureSetIndex])
            {
                if (segment.Type == ResourceType.BufferTexture)
                {
                    flags |= DirtyFlags.Texture;
                }
            }

            foreach (ResourceBindingSegment segment in program.BindingSegments[PipelineBase.ImageSetIndex])
            {
                if (segment.Type == ResourceType.BufferImage)
                {
                    flags |= DirtyFlags.Image;
                }
            }

''', '''            _dirty = DirtyFlags.All;
        }

        internal static DirtyFlags BufferViewSets(ResourceBindingSegment[][] segments)
        {
            DirtyFlags flags = DirtyFlags.None;

            foreach (ResourceBindingSegment segment in segments.Length > PipelineBase.TextureSetIndex ? segments[PipelineBase.TextureSetIndex] : Array.Empty<ResourceBindingSegment>())
            {
                if (segment.Type == ResourceType.BufferTexture)
                {
                    flags |= DirtyFlags.Texture;
                    break;
                }
            }

            foreach (ResourceBindingSegment segment in segments.Length > PipelineBase.ImageSetIndex ? segments[PipelineBase.ImageSetIndex] : Array.Empty<ResourceBindingSegment>())
            {
                if (segment.Type == ResourceType.BufferImage)
                {
                    flags |= DirtyFlags.Image;
                    break;
                }
            }

''')

    once(source / (GPU + 'ShaderCollection.cs'), '''
        public ResourceBindingSegment[][] ClearSegments { get; }
        public ResourceBindingSegment[][] BindingSegments { get; }
        public DescriptorSetTemplate[] Templates { get; }

        public ProgramLinkStatus LinkStatus { get; private set; }
''', '''
        public ResourceBindingSegment[][] ClearSegments { get; }
        public ResourceBindingSegment[][] BindingSegments { get; }
        internal DescriptorSetUpdater.DirtyFlags BufferViewDirtyFlags { get; }
        public DescriptorSetTemplate[] Templates { get; }

        public ProgramLinkStatus LinkStatus { get; private set; }
''')

    once(source / (GPU + 'ShaderCollection.cs'), '''
            ClearSegments = BuildClearSegments(sets);
            BindingSegments = BuildBindingSegments(resourceLayout.SetUsages, out bool usesBufferTextures);
            Templates = BuildTemplates(usePushDescriptors);
            (IncoherentBufferWriteStages, IncoherentTextureWriteStages) = BuildIncoherentStages(resourceLayout.SetUsages);

''', '''
            ClearSegments = BuildClearSegments(sets);
            BindingSegments = BuildBindingSegments(resourceLayout.SetUsages, out bool usesBufferTextures);
            BufferViewDirtyFlags = DescriptorSetUpdater.BufferViewSets(BindingSegments);
            Templates = BuildTemplates(usePushDescriptors);
            (IncoherentBufferWriteStages, IncoherentTextureWriteStages) = BuildIncoherentStages(resourceLayout.SetUsages);

''')

    return [source / name for name in BASELINE]
