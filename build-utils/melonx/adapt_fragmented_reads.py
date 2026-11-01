"""Read fragmented guest ranges for the GPU without allocating a new array each time.

Build 609 Hogwarts journals (1 November 2026): in 3D scenes the GPU thread allocates
1.3-1.8 GB per 5 s, about 250-350 MB per second of DispatchCalls work (r = 0.95 with
its busy time, unrelated to draw counts), and 70-80 % of all collections are gen 2,
so the bytes are mostly arrays of 85,000 bytes or more. On iOS the 16 KiB host page
forces MemoryManagerHostTracked (ArmProcessContextFactory: no host-mapped address
space above 4 KiB pages). Its GetSpan borrows a range only when it lies in one host
block; any range that crosses non-adjacent guest physical pages, or is only partly
covered by a private allocation, is returned as a new byte[] copy. The GPU reads guest
memory that way for every buffer upload, texture reload, command prefetch and copy.

The bytes read, the tracking calls and their order are unchanged:
- IVirtualMemoryManager.TryGetContiguousSpan borrows like GetSpan; its default IS
  GetSpan, so every manager other than HostTracked behaves exactly as before.
  HostTracked answers false for fragmented ranges instead of allocating.
- PhysicalMemory.GetReadOnlyRegion(address, size) borrows, or reads with the same
  Read call into a cleared pooled array that the caller disposes after use;
  PhysicalMemory.ReadInto copies into the caller's own span. Bytes a handled invalid
  access leaves unread stay zero, as in the array GetSpan used to return.
- Buffer uploads, single- and multi-range texture snapshots, the GPU memory
  manager's page-by-page reads, command prefetch, the copy engine's source and
  destination reads and the CPU mirror of buffer-to-buffer copies use them. Every consumer copies synchronously: SetBufferData copies spans
  into the renderer's queue or staging memory, and spans cannot outlive the call.
- Remaining fresh copies and the reads now served from the pool are counted.
"""
from pathlib import Path

NAMES = [
    'src/Ryujinx.Memory/IVirtualMemoryManager.cs',
    'src/Ryujinx.Cpu/Jit/MemoryManagerHostTracked.cs',
    'src/Ryujinx.Graphics.Gpu/Memory/PhysicalMemory.cs',
    'src/Ryujinx.Graphics.Gpu/Memory/MemoryManager.cs',
    'src/Ryujinx.Graphics.Gpu/Memory/Buffer.cs',
    'src/Ryujinx.Graphics.Gpu/Engine/GPFifo/GPFifoDevice.cs',
    'src/Ryujinx.Graphics.Gpu/Engine/Dma/DmaClass.cs',
    'src/Ryujinx.Graphics.Gpu/Memory/BufferCache.cs',
]
ALIAS = 'using PD = Ryujinx.Common.EmbeddedPerformanceDiagnostics;\n'
COUNT_COPY = '''{indent}PD.Count(PD.Counter.ReadCopies);
{indent}PD.Count(PD.Counter.ReadCopyBytes, {size});
'''
# Whole-buffer and region uploads. Fixtures that own Buffer.cs reverse exactly these edits.
BUFFER_UPLOADS = (
    ('''                        _context.Renderer.SetBufferData(Handle, 0, _physicalMemory.GetSpan(Address, (int)Size));''',
     '''                        using (ReadOnlyRegion region = _physicalMemory.GetReadOnlyRegion(Address, (int)Size))
                        {
                            _context.Renderer.SetBufferData(Handle, 0, region.Span);
                        }'''),
    ('''            _context.Renderer.SetBufferData(Handle, offset, _physicalMemory.GetSpan(mAddress, (int)mSize));''',
     '''            using (ReadOnlyRegion region = _physicalMemory.GetReadOnlyRegion(mAddress, (int)mSize))
            {
                _context.Renderer.SetBufferData(Handle, offset, region.Span);
            }'''),
)


def apply(source):
    paths = [Path(source) / name for name in NAMES]
    texts = {path: path.read_text(encoding='utf-8-sig') for path in paths}
    if any('TryGetContiguousSpan' in text for text in texts.values()):
        raise RuntimeError('Fragmented read adaptation already present')
    interface, tracked, physical, gpu, buffer, fifo, dma, cache = paths
    for path in (tracked, physical, gpu):
        if not texts[path].startswith(ALIAS):
            texts[path] = ALIAS + texts[path]

    def once(path, old, new, count=1):
        text = texts[path]
        if text.count(old) != count:
            raise RuntimeError('Fragmented read source drift: ' + str(path) + ': ' + old[:100])
        texts[path] = text.replace(old, new)

    once(interface, '''        ReadOnlySpan<byte> GetSpan(ulong va, int size, bool tracked = false);
''', '''        ReadOnlySpan<byte> GetSpan(ulong va, int size, bool tracked = false);

        /// <summary>
        /// Borrows the range when the manager can do so without copying. A manager that cannot answers false
        /// without allocating, and the caller copies the range with Read. The default keeps GetSpan's behaviour.
        /// </summary>
        bool TryGetContiguousSpan(ulong va, int size, out ReadOnlySpan<byte> span)
        {
            span = GetSpan(va, size);
            return true;
        }
''')
    once(tracked, '''        public override bool TryReadUnsafe(ulong va, int length, out Span<byte> data)
        {
            throw new NotImplementedException();
        }
''', '''        public override bool TryReadUnsafe(ulong va, int length, out Span<byte> data)
        {
            throw new NotImplementedException();
        }

        // Borrows a range held in one host block exactly as GetSpan does; a fragmented or
        // partly private range answers false instead of allocating a copy.
        public bool TryGetContiguousSpan(ulong va, int size, out ReadOnlySpan<byte> span)
        {
            if (size == 0)
            {
                span = ReadOnlySpan<byte>.Empty;
                return true;
            }

            if (TryGetVirtualContiguous(va, size, out MemoryBlock memoryBlock, out ulong offset))
            {
                span = memoryBlock.GetSpan(offset, size);
                return true;
            }

            span = default;
            return false;
        }
''')
    once(tracked, '''                Span<byte> data = new byte[size];

                Read(va, data);

                return data;''', COUNT_COPY.format(indent=' ' * 16, size='size') + '''                Span<byte> data = new byte[size];

                Read(va, data);

                return data;''')
    once(physical, '''        public ReadOnlySpan<byte> GetSpan(ulong address, int size, bool tracked = false)
        {
            return _cpuMemory.GetSpan(address, size, tracked);
        }
''', '''        public ReadOnlySpan<byte> GetSpan(ulong address, int size, bool tracked = false)
        {
            return _cpuMemory.GetSpan(address, size, tracked);
        }

        /// <summary>
        /// Borrows contiguous guest data, or reads fragmented data into a cleared pooled snapshot that the
        /// region owns: the bytes GetSpan would have copied into a new array. Nothing may keep the span after
        /// the region is disposed.
        /// </summary>
        internal ReadOnlyRegion GetReadOnlyRegion(ulong address, int size, bool tracked = false)
        {
            if (size == 0)
            {
                return new ReadOnlyRegion(ReadOnlySpan<byte>.Empty);
            }

            if (tracked)
            {
                _cpuMemory.SignalMemoryTracking(address, (ulong)size, false);
            }

            if (_cpuMemory.TryGetContiguousSpan(address, size, out ReadOnlySpan<byte> borrowed))
            {
                return new ReadOnlyRegion(borrowed);
            }

            PD.Count(PD.Counter.PooledReads);
            PD.Count(PD.Counter.PooledReadBytes, size);
            MemoryOwner<byte> owner = MemoryOwner<byte>.RentCleared(size);

            try
            {
                _cpuMemory.Read(address, owner.Span);

                return new ReadOnlyRegion(owner.Span, owner);
            }
            catch
            {
                owner.Dispose();
                throw;
            }
        }

        /// <summary>
        /// Copies guest data into <paramref name="destination"/> without an intermediate array. Bytes that a
        /// handled invalid access leaves unread are zero, as in the array GetSpan would have returned.
        /// </summary>
        internal void ReadInto(ulong address, Span<byte> destination, bool tracked = false)
        {
            if (destination.Length == 0)
            {
                return;
            }

            if (tracked)
            {
                _cpuMemory.SignalMemoryTracking(address, (ulong)destination.Length, false);
            }

            if (_cpuMemory.TryGetContiguousSpan(address, destination.Length, out ReadOnlySpan<byte> borrowed))
            {
                borrowed.CopyTo(destination);
                destination[borrowed.Length..].Clear();
                return;
            }

            PD.Count(PD.Counter.PooledReads);
            PD.Count(PD.Counter.PooledReadBytes, destination.Length);
            destination.Clear();
            _cpuMemory.Read(address, destination);
        }
''')
    once(physical, '''                    return new ReadOnlyRegion(_cpuMemory.GetSpan(singleRange.Address, (int)singleRange.Size, tracked));''',
         '''                    return GetReadOnlyRegion(singleRange.Address, (int)singleRange.Size, tracked);''')
    once(physical, '''                        ReadOnlySpan<byte> source = _cpuMemory.GetSpan(currentRange.Address, size, tracked);
                        Span<byte> destination = data.Slice(offset, size);
                        source.CopyTo(destination);
                        // Preserve the zero-initialized snapshot contract even if a memory manager
                        // handles an invalid access by returning fewer bytes instead of throwing.
                        destination[source.Length..].Clear();''',
         '''                        // ReadInto zeroes bytes a handled invalid access leaves unread, keeping the
                        // zero-initialized snapshot contract without a temporary copy per range.
                        ReadInto(currentRange.Address, data.Slice(offset, size), tracked);''')
    once(physical, '''            Span<byte> data = new byte[range.GetSize()];''',
         COUNT_COPY.format(indent=' ' * 12, size='(long)range.GetSize()') + '''            Span<byte> data = new byte[range.GetSize()];''')
    once(gpu, '''                Span<byte> data = new byte[size];

                ReadImpl(va, data, tracked);

                return MemoryMarshal.Cast<byte, T>(data)[0];''',
         COUNT_COPY.format(indent=' ' * 16, size='size') + '''                Span<byte> data = new byte[size];

                ReadImpl(va, data, tracked);

                return MemoryMarshal.Cast<byte, T>(data)[0];''')
    once(gpu, '''                Span<byte> data = new byte[size];

                ReadImpl(va, data, tracked);

                return data;''',
         COUNT_COPY.format(indent=' ' * 16, size='size') + '''                Span<byte> data = new byte[size];

                ReadImpl(va, data, tracked);

                return data;''')
    once(gpu, '''                Span<byte> data = new byte[mappedSize];''',
         COUNT_COPY.format(indent=' ' * 16, size='mappedSize') + '''                Span<byte> data = new byte[mappedSize];''')
    once(gpu, '''        /// <summary>
        /// Reads data from a possibly non-contiguous region of GPU mapped memory.
''', '''        /// <summary>
        /// Borrows GPU mapped memory like GetSpan, or reads a fragmented range into a cleared pooled snapshot
        /// that the region owns until it is disposed.
        /// </summary>
        internal ReadOnlyRegion GetReadOnlyRegion(ulong va, int size, bool tracked = false)
        {
            if (IsContiguous(va, size))
            {
                (PhysicalMemory physicalMemory, ulong address) = TranslateWithPhysicalMemory(va);

                return physicalMemory.GetReadOnlyRegion(address, size, tracked);
            }

            PD.Count(PD.Counter.PooledReads);
            PD.Count(PD.Counter.PooledReadBytes, size);
            MemoryOwner<byte> owner = MemoryOwner<byte>.RentCleared(size);

            try
            {
                ReadImpl(va, owner.Span, tracked);

                return new ReadOnlyRegion(owner.Span, owner);
            }
            catch
            {
                owner.Dispose();
                throw;
            }
        }

        /// <summary>
        /// Copies GPU mapped memory into <paramref name="data"/> without an intermediate array: the same pages,
        /// tracking and bytes as GetSpan followed by a copy.
        /// </summary>
        internal void ReadInto(ulong va, Span<byte> data, bool tracked = false)
        {
            if (data.Length == 0)
            {
                return;
            }

            if (IsContiguous(va, data.Length))
            {
                (PhysicalMemory physicalMemory, ulong address) = TranslateWithPhysicalMemory(va);

                physicalMemory.ReadInto(address, data, tracked);
            }
            else
            {
                ReadImpl(va, data, tracked);
            }
        }

        /// <summary>
        /// Reads data from a possibly non-contiguous region of GPU mapped memory.
''')
    once(gpu, '''                physicalMemory.GetSpan(pa, size, tracked).CopyTo(data[..size]);''',
         '''                physicalMemory.ReadInto(pa, data[..size], tracked);''')
    once(gpu, '''                physicalMemory.GetSpan(pa, size, tracked).CopyTo(data.Slice(offset, size));''',
         '''                physicalMemory.ReadInto(pa, data.Slice(offset, size), tracked);''')
    for old, new in BUFFER_UPLOADS:
        once(buffer, old, new)
    once(fifo, '''            public void Prefetch(MemoryManager memoryManager)
            {
                ReadOnlySpan<int> words = GetWords(memoryManager, true);

                Words = _wordPool.Rent(words.Length);
                PooledWords = true;
                words.CopyTo(Words);
            }''', '''            public void Prefetch(MemoryManager memoryManager)
            {
                int count = (int)EntryCount;
                int[] words = _wordPool.Rent(count);

                try
                {
                    memoryManager.ReadInto(EntryAddress, MemoryMarshal.AsBytes(words.AsSpan(0, count)), true);
                }
                catch
                {
                    _wordPool.Return(words);
                    throw;
                }

                Words = words;
                PooledWords = true;
            }''')
    once(dma, '''                memoryManager.GetSpan(dstGpuVa + (ulong)dstBaseOffset, dstSize).CopyTo(dstSpan);''',
         '''                memoryManager.ReadInto(dstGpuVa + (ulong)dstBaseOffset, dstSpan);''')
    # The source stays owned until the copy's block ends; every consumer copies from it.
    once(dma, '''                ReadOnlySpan<byte> srcSpan = memoryManager.GetSpan(srcGpuVa + (ulong)srcBaseOffset, srcSize, true);''',
         '''                using ReadOnlyRegion srcRegion = memoryManager.GetReadOnlyRegion(srcGpuVa + (ulong)srcBaseOffset, srcSize, true);
                ReadOnlySpan<byte> srcSpan = srcRegion.Span;''')
    once(cache, '''                memoryManager.Physical.WriteTrackedResource(dstAddress, memoryManager.Physical.GetSpan(srcAddress, (int)size), ResourceKind.Buffer);''',
         '''                using (ReadOnlyRegion source = memoryManager.Physical.GetReadOnlyRegion(srcAddress, (int)size))
                {
                    memoryManager.Physical.WriteTrackedResource(dstAddress, source.Span, ResourceKind.Buffer);
                }''')
    for path, text in texts.items():
        path.write_text(text)
    return paths
