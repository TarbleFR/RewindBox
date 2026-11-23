"""The Vulkan memory journal line also says what 16 KiB pages add to the dedicated blocks and what device-memory allocation
costs the threads that create buffers and images (diagnostic only, every title).

Evidence (IPA 822, Hogwarts Legacy, pid 12224, private core and performance logs; counts and durations only):
- the last "vulkanMemory sample" line, 77 s into the session: 14 807 blocks, 633 MiB, all of them dedicated (8 736
  image blocks of 438 MiB, 6 063 mapped buffer blocks of 194 MiB, 8 device-local buffer blocks), 51 and 32 KiB a block on
  average; the footprint 4.5 to 4.75 GB with the device at 7 to 10 % available; the iOS "graphics" share 1 146 to 1 384 MB;
- why every block is dedicated: MoltenVK v1.4.2 reports maxMemoryAllocationCount 2^30, so MemoryAllocator's pool block
  is 16 GiB / 2^30 = 16 bytes (MeloNX's EnableSuballocationPooling is false) and MemoryAllocatorBlockList dedicates any
  allocation of 8 bytes or more. MoltenVK gives each such VkDeviceMemory a placement MTLHeap of its size, and
  MemoryRequirements comes from Metal's heapBufferSizeAndAlign / heapTextureSizeAndAlign;
- whether those heaps waste memory to 16 KiB pages is not in any log: the journal sums the requirement sizes only. A
  host model of the production block list (sizes shaped like the line above) gives 24 to 27 MiB that sub-allocating the
  small buffers would save if requirements are not whole pages (H1), and 7 to 11 MiB that it would cost if they are (H2),
  while the Warning and Critical trims would return 35 and 70 MiB less to iOS in both cases; the allocation policy is
  therefore not changed, and this line is what decides;
- the render windows put CreateBufferAccess at 795 calls in 73.9 ms per 5 s late in the session (93 us a call; 32 us in
  an earlier window, 484 us in the last one); how much of that is vkAllocateMemory is not in the logs.

Change (MemoryAllocatorBlockList.cs, MemoryAllocator.cs):
- each block list keeps, for its dedicated blocks, the sum of (size rounded up to 16 KiB - size) and how many are not a
  whole number of 16 KiB pages, updated where _dedicatedBytes already is (publication and removal, under the list's write
  lock): O(1), no allocation; AddRounding reads them, and the dedicated block count, under the list's read lock;
- MemoryAllocator.AllocateDeviceMemory (the path of every buffer created by BufferManager.CreateBacking and every image of
  TextureStorage; it reaches vkAllocateMemory and vkMapMemory through the block list) is a wrapper: two
  Stopwatch.GetTimestamp reads and two Interlocked additions around the unchanged body, counted for buffers and for images
  apart (by its isBuffer argument);
- UsageText appends to each listed block list ", 16 KiB rounding R KiB over N of D dedicated blocks", and before its
  closing "(adapt_vulkan_memory_journal)" the allocations since the previous line: "; device memory allocations since
  the previous line (adapt_vulkan_memory_rounding_journal): buffers C in T ms, images C in T ms" (the counters are taken
  and reset when the line is written; the first line counts from the renderer's start).
No size, alignment, memory type, dedicated choice, order, map, free or trim changes: the allocator's Allocate and Free
paths are the same statements with the counters beside them. No detail starts with "name=" (the journal's redaction).
Reading it on the device: N about 0 (R about 0) in the buffer and image lists means Metal already rounds the
requirements (H2: no bytes to win by sub-allocation); N in the thousands means R is what per-allocation heaps lose to
pages at most (H1). The allocation times against the CreateBufferAccess and CreateTexture times of the same 30 s say
what share sub-allocation could save on the render thread.
Not measured on an iPhone. Fail closed on drift: the files must be the Core 827 preparation's.
"""
import hashlib

from adapt_session import once

BLOCKS = 'src/Ryujinx.Graphics.Vulkan/MemoryAllocatorBlockList.cs'
ALLOCATOR = 'src/Ryujinx.Graphics.Vulkan/MemoryAllocator.cs'
BASELINE = {
    BLOCKS: 'c0b2d68a19b360ce9cfe142fce51dee72a918c0544cc7086c92535dd612ac65b',
    ALLOCATOR: 'f5d64ab81684f357d9b28dfccd638e682793dc24a4ff46364683f248d4338ab2',
}

FIELDS_OLD = '''        private ulong _dedicatedBytes;
        private ulong _dedicatedMappedBytes;
'''
FIELDS_NEW = '''        private ulong _dedicatedBytes;
        private ulong _dedicatedMappedBytes;
        // RewindBox (adapt_vulkan_memory_rounding_journal): what 16 KiB pages add to the dedicated blocks (each is its own
        // Metal heap) and how many of them are not a whole number of pages. Same lock as _dedicatedBytes.
        internal const ulong RoundingPageBytes = 16 * 1024;
        private ulong _dedicatedRoundingBytes;
        private ulong _dedicatedUnalignedBlocks;
'''

ROUNDING_OLD = '''        public unsafe MemoryAllocation Allocate(ulong size, ulong alignment, bool map)
        {
'''
ROUNDING_NEW = '''        // RewindBox (adapt_vulkan_memory_rounding_journal): this list's dedicated blocks and their 16 KiB rounding, under its
        // read lock.
        internal void AddRounding(ref ulong dedicatedBlocks, ref ulong roundingBytes, ref ulong unalignedBlocks)
        {
            _lock.EnterReadLock();

            try
            {
                dedicatedBlocks += (ulong)(_dedicatedBlocks?.Count ?? 0);
                roundingBytes += _dedicatedRoundingBytes;
                unalignedBlocks += _dedicatedUnalignedBlocks;
            }
            finally
            {
                _lock.ExitReadLock();
            }
        }

        // RewindBox (adapt_vulkan_memory_rounding_journal): called with the list's write lock held, beside _dedicatedBytes.
        private void NoteDedicatedRounding(ulong size, bool published)
        {
            ulong slack = (RoundingPageBytes - size % RoundingPageBytes) % RoundingPageBytes;
            if (slack == 0)
            {
                return;
            }

            if (published)
            {
                _dedicatedRoundingBytes += slack;
                _dedicatedUnalignedBlocks++;
            }
            else
            {
                _dedicatedRoundingBytes -= slack;
                _dedicatedUnalignedBlocks--;
            }
        }

        public unsafe MemoryAllocation Allocate(ulong size, ulong alignment, bool map)
        {
'''

INSERT_OLD = '''                _dedicatedBytes += block.Size;
                _dedicatedMappedBytes += block.Mapped ? block.Size : 0;
                return;
'''
INSERT_NEW = '''                _dedicatedBytes += block.Size;
                _dedicatedMappedBytes += block.Mapped ? block.Size : 0;
                NoteDedicatedRounding(block.Size, published: true);
                return;
'''

REMOVE_OLD = '''                            _dedicatedBytes -= block.Size;
                            _dedicatedMappedBytes -= block.Mapped ? block.Size : 0;
'''
REMOVE_NEW = '''                            _dedicatedBytes -= block.Size;
                            _dedicatedMappedBytes -= block.Mapped ? block.Size : 0;
                            NoteDedicatedRounding(block.Size, published: false);
'''

TIMER_FIELDS_OLD = '''        private readonly ReaderWriterLockSlim _lock;

        public MemoryAllocator('''
TIMER_FIELDS_NEW = '''        private readonly ReaderWriterLockSlim _lock;
        // RewindBox (adapt_vulkan_memory_rounding_journal): AllocateDeviceMemory calls and their Stopwatch ticks since the
        // previous journal line, for buffers and for images.
        private long _bufferAllocationCalls;
        private long _bufferAllocationTicks;
        private long _imageAllocationCalls;
        private long _imageAllocationTicks;

        public MemoryAllocator('''

TUPLE_OLD = '''            var lists = new List<(int Type, bool Buffers, ulong Blocks, ulong Bytes, ulong Dedicated, ulong Mapped, ulong Free)>();'''
TUPLE_NEW = '''            var lists = new List<(int Type, bool Buffers, ulong Blocks, ulong Bytes, ulong Dedicated, ulong Mapped, ulong Free,
                ulong DedicatedBlocks, ulong Rounding, ulong Unaligned)>();'''

COLLECT_OLD = '''                    list.AddUsage(ref blocks, ref bytes, ref dedicated, ref mapped, ref free);
                    lists.Add((list.MemoryTypeIndex, list.ForBuffer, blocks, bytes, dedicated, mapped, free));'''
COLLECT_NEW = '''                    list.AddUsage(ref blocks, ref bytes, ref dedicated, ref mapped, ref free);
                    // RewindBox (adapt_vulkan_memory_rounding_journal): the dedicated blocks' 16 KiB rounding.
                    ulong dedicatedBlocks = 0, rounding = 0, unaligned = 0;
                    list.AddRounding(ref dedicatedBlocks, ref rounding, ref unaligned);
                    lists.Add((list.MemoryTypeIndex, list.ForBuffer, blocks, bytes, dedicated, mapped, free, dedicatedBlocks, rounding, unaligned));'''

LIST_OLD = '''                            $"(dedicated {list.Dedicated / MiB} MiB, mapped {list.Mapped / MiB} MiB, pooled free {list.Free / MiB} MiB)");
            }
'''
LIST_NEW = '''                            $"(dedicated {list.Dedicated / MiB} MiB, mapped {list.Mapped / MiB} MiB, pooled free {list.Free / MiB} MiB)");
                text.Append($", 16 KiB rounding {list.Rounding / 1024} KiB over {list.Unaligned} of {list.DedicatedBlocks} dedicated blocks");
            }

            // RewindBox (adapt_vulkan_memory_rounding_journal): device memory allocations since the previous line.
            long bufferCalls = Interlocked.Exchange(ref _bufferAllocationCalls, 0);
            long bufferTicks = Interlocked.Exchange(ref _bufferAllocationTicks, 0);
            long imageCalls = Interlocked.Exchange(ref _imageAllocationCalls, 0);
            long imageTicks = Interlocked.Exchange(ref _imageAllocationTicks, 0);
            static string Milliseconds(long ticks) =>
                (ticks * 1000.0 / System.Diagnostics.Stopwatch.Frequency).ToString("0.0", System.Globalization.CultureInfo.InvariantCulture);
            text.Append($"; device memory allocations since the previous line (adapt_vulkan_memory_rounding_journal): buffers {bufferCalls} " +
                        $"in {Milliseconds(bufferTicks)} ms, images {imageCalls} in {Milliseconds(imageTicks)} ms");
'''

WRAP_OLD = '''        public MemoryAllocation AllocateDeviceMemory(
            MemoryRequirements requirements,
            MemoryPropertyFlags flags = 0,
            bool isBuffer = false,
            bool poolSmallBuffer = false)
        {
'''
WRAP_NEW = '''        public MemoryAllocation AllocateDeviceMemory(
            MemoryRequirements requirements,
            MemoryPropertyFlags flags = 0,
            bool isBuffer = false,
            bool poolSmallBuffer = false)
        {
            // RewindBox (adapt_vulkan_memory_rounding_journal): the unchanged allocation, timed for the journal line.
            long start = System.Diagnostics.Stopwatch.GetTimestamp();

            try
            {
                return AllocateDeviceMemoryUntimed(requirements, flags, isBuffer, poolSmallBuffer);
            }
            finally
            {
                long ticks = System.Diagnostics.Stopwatch.GetTimestamp() - start;
                if (isBuffer)
                {
                    Interlocked.Increment(ref _bufferAllocationCalls);
                    Interlocked.Add(ref _bufferAllocationTicks, ticks);
                }
                else
                {
                    Interlocked.Increment(ref _imageAllocationCalls);
                    Interlocked.Add(ref _imageAllocationTicks, ticks);
                }
            }
        }

        private MemoryAllocation AllocateDeviceMemoryUntimed(
            MemoryRequirements requirements,
            MemoryPropertyFlags flags,
            bool isBuffer,
            bool poolSmallBuffer)
        {
'''

EDITS = {
    BLOCKS: ((FIELDS_OLD, FIELDS_NEW), (ROUNDING_OLD, ROUNDING_NEW), (INSERT_OLD, INSERT_NEW), (REMOVE_OLD, REMOVE_NEW)),
    ALLOCATOR: ((TIMER_FIELDS_OLD, TIMER_FIELDS_NEW), (TUPLE_OLD, TUPLE_NEW), (COLLECT_OLD, COLLECT_NEW), (LIST_OLD, LIST_NEW),
                (WRAP_OLD, WRAP_NEW)),
}


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    for name, pairs in EDITS.items():
        for old, new in pairs:
            once(paths[name], old, new)
    return list(paths.values())
