"""What the Vulkan memory allocator holds, by memory type, in the engine journal (Core 727 candidate, RAM diagnosis).

IPA 724, Hogwarts Legacy (pid 49375): MoltenVK reports "GPU memory allocated" 1 269 MB in play and the kernel's
graphics ledger 1 053 + 159 MiB, while the texture and buffer caches account for 157 and 133 MiB
(memoryInventory). About 1 GB of device memory is not attributed, at 4-8 % of the device available, where each
thread's CPU time per frame is 2 to 5 times what it was at 30 FPS. Nothing says whether it is pooled blocks, their free
space, dedicated allocations, or host-visible (mapped) memory.

Change (diagnostic only, every title; no allocation, block or free path changes):
- MemoryAllocatorBlockList.Block.FreeBytes(): the free bytes of a pooled block, under its range lock;
- MemoryAllocatorBlockList.AddUsage(): its pooled and dedicated blocks (count, bytes, mapped bytes, pooled free bytes),
  under the list's read lock (allocation takes it too; a free takes the write lock);
- MemoryAllocator.UsageText(): every block list under the allocator's read lock, as
  "type T buffers|images: B blocks X MiB (dedicated D MiB, mapped M MiB, pooled free F MiB)", the four largest, then
  the totals;
- one "vulkanMemory sample" line from the render stage window (PipelineBase.Log, every 5 s): the first at the first
  window, then every sixth (about 30 s), at most 60.
Not measured on an iPhone. Fail closed on drift: the files must be the Core 725 preparation's.
"""
import hashlib
from adapt_session import once

BLOCKS = 'src/Ryujinx.Graphics.Vulkan/MemoryAllocatorBlockList.cs'
ALLOCATOR = 'src/Ryujinx.Graphics.Vulkan/MemoryAllocator.cs'
STAGES = 'src/Ryujinx.Graphics.Vulkan/PipelineBase.cs'
RENDERER = 'src/Ryujinx.Graphics.Vulkan/VulkanRenderer.cs'
BASELINE = {
    BLOCKS: '6c0f8f932fe46ee689d17ccc79ab6f63a5677a7901ed374d1fa2b72cc84fc719',
    ALLOCATOR: '15833c21c16b3698de4f872d547f0d2b050cde28843695d972c366777512f9b3',
    STAGES: 'c2bf7240ce6e4bbb17ad9ec18a47d0edfdc4cc57df398b5600e8fa824c64b304',
    RENDERER: 'fb84d717296319a20c398329a0a9b1259c9cc31103928ff40f41ae78a65d7054',
}

FREE_OLD = '''            public Block(DeviceMemory memory, nint hostPointer, ulong size, bool dedicated, bool importedHostPointer = false)
            {
'''
FREE_NEW = '''            // RewindBox (adapt_vulkan_memory_journal): the free bytes of this block, read under its range lock.
            internal ulong FreeBytes()
            {
                lock (_rangeLock)
                {
                    ulong free = 0;
                    foreach (Range range in _freeRanges)
                    {
                        free += range.Size;
                    }

                    return free;
                }
            }

            public Block(DeviceMemory memory, nint hostPointer, ulong size, bool dedicated, bool importedHostPointer = false)
            {
'''

USAGE_OLD = '''        public unsafe MemoryAllocation Allocate(ulong size, ulong alignment, bool map)
        {
'''
USAGE_NEW = '''        // RewindBox (adapt_vulkan_memory_journal): this list's pooled and dedicated blocks, under its read lock.
        internal void AddUsage(ref ulong blocks, ref ulong bytes, ref ulong dedicated, ref ulong mapped, ref ulong free)
        {
            _lock.EnterReadLock();

            try
            {
                foreach (Block block in _blocks)
                {
                    blocks++;
                    bytes += block.Size;
                    mapped += block.Mapped ? block.Size : 0;
                    free += block.FreeBytes();
                }

                if (_dedicatedBlocks != null)
                {
                    foreach (Block block in _dedicatedBlocks)
                    {
                        blocks++;
                        bytes += block.Size;
                        dedicated += block.Size;
                        mapped += block.Mapped ? block.Size : 0;
                    }
                }
            }
            finally
            {
                _lock.ExitReadLock();
            }
        }

        public unsafe MemoryAllocation Allocate(ulong size, ulong alignment, bool map)
        {
'''

TEXT_OLD = '''        public MemoryAllocation AllocateDeviceMemory(
'''
TEXT_NEW = '''        // RewindBox (adapt_vulkan_memory_journal): what every block list holds, the four largest and the totals, in MiB.
        internal string UsageText()
        {
            var lists = new List<(int Type, bool Buffers, ulong Blocks, ulong Bytes, ulong Dedicated, ulong Mapped, ulong Free)>();
            _lock.EnterReadLock();

            try
            {
                foreach (MemoryAllocatorBlockList list in _blockLists)
                {
                    ulong blocks = 0, bytes = 0, dedicated = 0, mapped = 0, free = 0;
                    list.AddUsage(ref blocks, ref bytes, ref dedicated, ref mapped, ref free);
                    lists.Add((list.MemoryTypeIndex, list.ForBuffer, blocks, bytes, dedicated, mapped, free));
                }
            }
            finally
            {
                _lock.ExitReadLock();
            }

            const ulong MiB = 1024 * 1024;
            ulong totalBlocks = 0, total = 0, totalDedicated = 0, totalMapped = 0, totalFree = 0;

            foreach (var list in lists)
            {
                totalBlocks += list.Blocks;
                total += list.Bytes;
                totalDedicated += list.Dedicated;
                totalMapped += list.Mapped;
                totalFree += list.Free;
            }

            lists.Sort((a, b) => b.Bytes.CompareTo(a.Bytes));
            var text = new System.Text.StringBuilder();
            text.Append($"Vulkan device memory: {totalBlocks} blocks {total / MiB} MiB (dedicated {totalDedicated / MiB} MiB, mapped " +
                        $"{totalMapped / MiB} MiB, pooled free {totalFree / MiB} MiB) in {lists.Count} lists");

            for (int i = 0; i < lists.Count && i < 4; i++)
            {
                var list = lists[i];
                text.Append($"; type {list.Type} {(list.Buffers ? "buffers" : "images")}: {list.Blocks} blocks {list.Bytes / MiB} MiB " +
                            $"(dedicated {list.Dedicated / MiB} MiB, mapped {list.Mapped / MiB} MiB, pooled free {list.Free / MiB} MiB)");
            }

            return text.Append(" (adapt_vulkan_memory_journal)").ToString();
        }

        public MemoryAllocation AllocateDeviceMemory(
'''

LOG_OLD = '''            Ryujinx.Common.Logging.Logger.Warning?.Print(Ryujinx.Common.Logging.LogClass.Gpu, text);
            RenderDetail.Log(window, frames);
'''
LOG_NEW = '''            Ryujinx.Common.Logging.Logger.Warning?.Print(Ryujinx.Common.Logging.LogClass.Gpu, text);
            RenderDetail.Log(window, frames);

            // RewindBox (adapt_vulkan_memory_journal): the allocator's blocks at the first window, then every sixth (about
            // 30 s), at most 60 lines. Observability only: a failure is ignored.
            if (MemoryUsage != null && _memoryWindows++ % 6 == 0 && _memoryLines < 60)
            {
                try
                {
                    _memoryLines++;
                    Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("vulkanMemory", "sample", detail: MemoryUsage());
                }
                catch
                {
                }
            }
'''

FIELD_OLD = '''        public static void NotePresent(long start, long acquireStart, long acquired, long queuePresentStart)
'''
FIELD_NEW = '''        // RewindBox (adapt_vulkan_memory_journal): set by the renderer once its allocator exists.
        internal static Func<string> MemoryUsage;
        private static int _memoryWindows;
        private static int _memoryLines;

        public static void NotePresent(long start, long acquireStart, long acquired, long queuePresentStart)
'''

RENDERER_OLD = '''            MemoryAllocator = new MemoryAllocator(Api, _physicalDevice, _device);
'''
RENDERER_NEW = '''            MemoryAllocator = new MemoryAllocator(Api, _physicalDevice, _device);
            // RewindBox (adapt_vulkan_memory_journal): the render stage window journals what the allocator holds.
            MemoryAllocator allocator = MemoryAllocator;
            RenderStageTimer.MemoryUsage = allocator.UsageText;
'''

EDITS = {BLOCKS: ((FREE_OLD, FREE_NEW), (USAGE_OLD, USAGE_NEW)), ALLOCATOR: ((TEXT_OLD, TEXT_NEW),),
         STAGES: ((FIELD_OLD, FIELD_NEW), (LOG_OLD, LOG_NEW)), RENDERER: ((RENDERER_OLD, RENDERER_NEW),)}


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    for name, pairs in EDITS.items():
        for old, new in pairs:
            once(paths[name], old, new)
    return list(paths.values())
