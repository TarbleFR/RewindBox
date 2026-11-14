using System;
using System.Collections.Generic;

namespace Silk.NET.Vulkan
{
    readonly struct CommandBuffer { }
}

namespace Ryujinx.Graphics.Vulkan
{
    // Command transport and native completion are controlled at this boundary. The Python runner inserts verbatim, from
    // the variant's production CommandBufferPool.cs: AddDependant, the dependant release loop of WaitAndDecrementRef and,
    // for the final variant (FINAL), the DependantEntry struct the dependants are stored as.
    sealed class CommandBufferPool
    {
        public const int MaxCommandBuffers = 16;
#if FINAL
        /* PRODUCTION_DEPENDANT_ENTRY */
        struct Entry
        {
            public List<DependantEntry> Dependants;
            public List<MultiFenceHolder> Waitables;
        }
#else
        struct Entry
        {
            public List<IAuto> Dependants;
            public List<MultiFenceHolder> Waitables;
        }
#endif
        readonly Entry[] _commandBuffers = new Entry[MaxCommandBuffers];
        public CommandBufferPool()
        {
            for (int i = 0; i < MaxCommandBuffers; i++)
            {
                _commandBuffers[i].Dependants = new();
                _commandBuffers[i].Waitables = new();
            }
        }
        /* PRODUCTION_ADD_DEPENDANT */
        public void AddWaitable(int index, MultiFenceHolder holder)
        {
            if (!_commandBuffers[index].Waitables.Contains(holder))
                _commandBuffers[index].Waitables.Add(holder);
        }
        public int DependencyCount(int index) => _commandBuffers[index].Dependants.Count;
        public int WaitableCount(int index) => _commandBuffers[index].Waitables.Count;
        public FenceHolder GetFence(int index) => new();
        public void Return(CommandBufferScoped scoped) { }
        // The command buffer's fence is signalled: what production WaitAndDecrementRef does with its dependants.
        public void Complete(int cbIndex)
        {
            ref Entry entry = ref _commandBuffers[cbIndex];
/* PRODUCTION_RELEASE_LOOP */
            entry.Dependants.Clear();
            entry.Waitables.Clear();
        }
    }
    sealed class FenceHolder { }
    sealed class MultiFenceHolder
    {
        public readonly List<(int Slot, int Offset, int Size, bool Write)> Uses = new();
        public void AddBufferUse(int slot, int offset, int size, bool write)
            => Uses.Add((slot, offset, size, write));
    }
}
