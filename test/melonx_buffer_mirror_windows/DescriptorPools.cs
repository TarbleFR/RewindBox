// Native API boundary for exercising the complete production DescriptorSetManager.
using Silk.NET.Vulkan;

namespace Silk.NET.Vulkan
{
    struct Device {}
    struct DescriptorPool { public ulong Handle; }
    struct DescriptorSet { public ulong Handle; }
    struct DescriptorSetLayout { public ulong Handle; }
    struct DescriptorPoolSize { public uint DescriptorCount; }
    enum DescriptorPoolCreateFlags { None, UpdateAfterBindBit }
    enum StructureType { DescriptorPoolCreateInfo, DescriptorSetAllocateInfo }
    enum Result { Success, ErrorOutOfPoolMemory, ErrorUnknown, ErrorOutOfHostMemory, ErrorOutOfDeviceMemory }
    sealed class VulkanException(Result result) : Exception(result.ToString())
    {
        public Result ResultCode { get; } = result;
    }
    static class Results
    {
        public static void ThrowOnError(this Result result)
        {
            if (result != Result.Success) throw new VulkanException(result);
        }
    }
    unsafe struct DescriptorPoolCreateInfo {
        public StructureType SType; public DescriptorPoolCreateFlags Flags;
        public uint MaxSets, PoolSizeCount; public DescriptorPoolSize* PPoolSizes;
    }
    unsafe struct DescriptorSetAllocateInfo {
        public StructureType SType; public DescriptorPool DescriptorPool;
        public uint DescriptorSetCount; public DescriptorSetLayout* PSetLayouts;
    }
    unsafe class Vk
    {
        public int Failures, Allocations;
        public readonly List<ulong> Destructions = new();
        public ulong Created;
        public readonly List<uint[]> RequestedSizes = new();
        public Result NextCreateResult;

        public Result CreateDescriptorPool(Device device, in DescriptorPoolCreateInfo info, void* allocator, out DescriptorPool pool)
        {
            var counts = new uint[info.PoolSizeCount];
            for (int i = 0; i < counts.Length; i++) counts[i] = info.PPoolSizes[i].DescriptorCount;
            RequestedSizes.Add(counts);
            if (NextCreateResult != Result.Success)
            {
                Result result = NextCreateResult;
                NextCreateResult = Result.Success;
                pool = default;
                return result;
            }
            pool = new DescriptorPool { Handle = ++Created };
            return Result.Success;
        }
        public Result AllocateDescriptorSets(Device device, DescriptorSetAllocateInfo* info, DescriptorSet* sets)
        {
            Allocations++;
            if (Failures > 0) { Failures--; return Result.ErrorOutOfPoolMemory; }
            for (int i = 0; i < info->DescriptorSetCount; i++) sets[i].Handle = 1;
            return Result.Success;
        }
        public void DestroyDescriptorPool(Device device, DescriptorPool pool, void* allocator)
        {
            lock (Destructions) Destructions.Add(pool.Handle);
        }
    }
}

// The Python fixture also builds this boundary with BeforePool instead of AfterPool.
namespace AfterPool
{
    class Auto<T>(T value) { public T Value = value; }
    struct DescriptorSetCollection
    {
        private DescriptorSetManager.DescriptorPoolHolder holder;
        private readonly DescriptorSet[] sets;
        public int SetsCount => sets.Length;
        public DescriptorSetCollection(DescriptorSetManager.DescriptorPoolHolder holder, DescriptorSet[] sets)
        { this.holder = holder; this.sets = sets; }
        public void Dispose() { holder?.FreeDescriptorSets(this); holder = null; }
    }
    static class Lifetime
    {
        public static (int FailedPoolDestroys, int EarlyDestroys, bool LastSetReleased) Exercise()
        {
            var vk = new Vk { Failures = 1 };
            var manager = new DescriptorSetManager(default, 1);
            var sizes = new[] { new DescriptorPoolSize { DescriptorCount = 8 } };
            var set = manager.AllocateDescriptorSet(vk, default, sizes, 0, 1, false);
            int duplicate = vk.Destructions.Count(h => h == 1);
            manager.Dispose();
            int early = vk.Destructions.Count(h => h == 2);
            set.Value.Dispose();
            manager.Dispose();
            return (duplicate, early, vk.Destructions.Count(h => h == 2) == 1);
        }

        public static void CheckConcurrentRelease()
        {
            var vk = new Vk();
            var manager = new DescriptorSetManager(default, 1);
            var sizes = new[] { new DescriptorPoolSize { DescriptorCount = 8 } };
            var sets = Enumerable.Range(0, 40).Select(_ => manager.AllocateDescriptorSet(vk, default, sizes, 0, 1, true)).ToArray();
            Parallel.Invoke(manager.Dispose, () => Parallel.ForEach(sets, set => set.Value.Dispose()));
            if (vk.Destructions.Count != 5 || vk.Destructions.Distinct().Count() != 5) throw new Exception("Incorrect pool lifetime");
            try { manager.AllocateDescriptorSet(vk, default, sizes, 0, 1, true); }
            catch (ObjectDisposedException) { return; }
            throw new Exception("Allocated after shutdown");
        }
    }
}
