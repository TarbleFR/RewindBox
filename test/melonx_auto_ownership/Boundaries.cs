using System;
using System.Collections.Generic;

namespace Silk.NET.Vulkan
{
    readonly struct CommandBuffer { }
}

namespace Ryujinx.Graphics.Vulkan
{
    // Command transport and native completion are controlled at this boundary.
    // AddDependant is inserted verbatim from production by the Python runner.
    sealed class CommandBufferPool
    {
        public const int MaxCommandBuffers = 16;
        struct Entry
        {
            public List<IAuto> Dependants;
            public List<MultiFenceHolder> Waitables;
        }
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
        public void Complete(int index)
        {
            foreach (IAuto dependant in _commandBuffers[index].Dependants)
                dependant.DecrementReferenceCount(index);
            _commandBuffers[index].Dependants.Clear();
            _commandBuffers[index].Waitables.Clear();
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
