"""Size replacement Vulkan pools for repeated small, single-set descriptor budgets."""
import hashlib

from adapt_session import once

MANAGER = 'src/Ryujinx.Graphics.Vulkan/DescriptorSetManager.cs'
MEMORY = 'src/Ryujinx.Graphics.Vulkan/MemoryAllocator.cs'
BASELINE = {
    MANAGER: '001d25b5fbab35f104004bc28384cbb70bfa767029a8a1eae935670300709758',
    MEMORY: 'f5d64ab81684f357d9b28dfccd638e682793dc24a4ff46364683f248d4338ab2',
}

FIELDS = '''        private static long _poolsCreated;
        private static long _expandedPools;

        internal static string PoolCreationTotals() =>
            $"descriptor pools since process start: created {Interlocked.Read(ref _poolsCreated)}, expanded {Interlocked.Read(ref _expandedPools)}";

'''

CREATE = '''                // GetDescriptorPoolSizes can supply exactly one set of descriptors for
                // a layout with separate types. Grow only when this layout requests another pool.
                currentPool = CreateReplacementOrDefault(api, poolSizes, setsCount, descriptorsCount,
                    updateAfterBind, replacing: currentPool != null);
                Interlocked.Increment(ref _poolsCreated);'''

HELPER = '''        private DescriptorPoolHolder CreateReplacementOrDefault(Vk api, ReadOnlySpan<DescriptorPoolSize> sizes,
            int setsCount, int descriptorsCount, bool updateAfterBind, bool replacing)
        {
            if (replacing && !updateAfterBind && setsCount == 1 && descriptorsCount is > 0 and <= 16 &&
                sizes.Length is > 0 and <= 8)
            {
                ulong budget = 0;
                foreach (var size in sizes)
                {
                    budget += size.DescriptorCount;
                }

                if (budget == (uint)descriptorsCount)
                {
                    Span<DescriptorPoolSize> expanded = stackalloc DescriptorPoolSize[sizes.Length];
                    sizes.CopyTo(expanded);
                    for (int i = 0; i < expanded.Length; i++)
                    {
                        expanded[i].DescriptorCount *= MaxSets;
                    }

                    try
                    {
                        var pool = new DescriptorPoolHolder(api, _device, expanded, updateAfterBind);
                        Interlocked.Increment(ref _expandedPools);
                        return pool;
                    }
                    catch (VulkanException e) when (e.ResultCode is Result.ErrorOutOfHostMemory or Result.ErrorOutOfDeviceMemory)
                    {
                        // The original small allocation may still succeed.
                    }
                }
            }

            return new DescriptorPoolHolder(api, _device, sizes, updateAfterBind);
        }

'''


def apply(source):
    for name, expected in BASELINE.items():
        assert hashlib.sha256((source / name).read_bytes()).hexdigest() == expected, name
    manager = source / MANAGER
    memory = source / MEMORY
    anchor = '        private readonly Device _device;'
    once(manager, anchor, FIELDS + anchor)
    once(manager, '                currentPool = new DescriptorPoolHolder(api, _device, poolSizes, updateAfterBind);', CREATE)
    anchor = '        private DescriptorPoolHolder GetPool('
    once(manager, anchor, HELPER + anchor)
    anchor = '            return text.Append(" (adapt_vulkan_memory_journal)").ToString();'
    once(memory, anchor, '            text.Append("; ").Append(DescriptorSetManager.PoolCreationTotals());\n' + anchor)
    return [manager, memory]
