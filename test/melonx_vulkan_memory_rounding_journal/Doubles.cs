// Doubles for the production allocator files (MemoryAllocator.cs, MemoryAllocatorBlockList.cs, MemoryAllocation.cs,
// VulkanException.cs, BitUtils.cs) compiled outside the Vulkan project: the Silk.NET types they use and a driver that
// models MoltenVK v1.4.2 on an Apple GPU (memory types private, shared, memoryless; maxMemoryAllocationCount 2^30; one
// placement MTLHeap per VkDeviceMemory, counted with its 16 KiB rounding). Every native call is traced for the
// control/candidate comparison.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Text;
using Silk.NET.Vulkan;

namespace Silk.NET.Vulkan
{
    enum Result { ErrorMemoryMapFailed = -5, ErrorOutOfDeviceMemory = -2, Success = 0 }
    enum StructureType { MemoryAllocateInfo }
    readonly struct Device { }
    readonly struct DeviceMemory
    {
        public readonly ulong Handle;
        public DeviceMemory(ulong handle) { Handle = handle; }
    }
    struct MemoryAllocateInfo
    {
        public StructureType SType;
        public ulong AllocationSize;
        public uint MemoryTypeIndex;
    }
    [Flags]
    enum MemoryPropertyFlags : uint { None = 0, DeviceLocalBit = 1, HostVisibleBit = 2, HostCoherentBit = 4, HostCachedBit = 8, LazilyAllocatedBit = 16 }
    [Flags]
    enum MemoryHeapFlags : uint { None = 0, DeviceLocalBit = 1 }
    struct MemoryRequirements
    {
        public ulong Size;
        public ulong Alignment;
        public uint MemoryTypeBits;
    }
    struct MemoryType
    {
        public MemoryPropertyFlags PropertyFlags;
        public uint HeapIndex;
    }
    struct MemoryHeap
    {
        public ulong Size;
        public MemoryHeapFlags Flags;
    }
    struct PhysicalDeviceLimits { public uint MaxMemoryAllocationCount; }
    struct PhysicalDeviceProperties { public PhysicalDeviceLimits Limits; }
    sealed class Fixed<T>
    {
        private readonly T[] _items;
        public Fixed(params T[] items) { _items = items; }
        public T this[int index] => _items[index];
    }
    struct PhysicalDeviceMemoryProperties
    {
        public uint MemoryTypeCount;
        public Fixed<MemoryType> MemoryTypes;
        public uint MemoryHeapCount;
        public Fixed<MemoryHeap> MemoryHeaps;
    }

    unsafe sealed class Vk
    {
        public const ulong Page = 16384;
        sealed class MemoryState { public ulong Size; public uint Type; public bool Mapped; }
        readonly Dictionary<ulong, MemoryState> _memory = new();
        readonly object _gate = new();
        ulong _next;
        public bool Trace;
        public readonly StringBuilder Calls = new();
        public int Allocations, Frees, Maps, Unmaps, AllocationFailures;
        public ulong LiveBytes, LiveHeapBytes;
        public long SpinTicks;
        public int Live { get { lock (_gate) return _memory.Count; } }

        public Result AllocateMemory(Device device, in MemoryAllocateInfo info, void* callbacks, out DeviceMemory memory)
        {
            if (SpinTicks > 0)
            {
                // The driver's own time (MoltenVK makes the MTLHeap and, for shared memory, its MTLBuffer).
                long until = Stopwatch.GetTimestamp() + SpinTicks;
                while (Stopwatch.GetTimestamp() < until) { }
            }
            lock (_gate)
            {
                if (AllocationFailures > 0)
                {
                    AllocationFailures--;
                    if (Trace) Calls.Append("AF").Append(info.AllocationSize).Append(';');
                    memory = default;
                    return Result.ErrorOutOfDeviceMemory;
                }
                ulong h = ++_next;
                _memory.Add(h, new() { Size = info.AllocationSize, Type = info.MemoryTypeIndex });
                LiveBytes += info.AllocationSize;
                LiveHeapBytes += (info.AllocationSize + Page - 1) / Page * Page;
                Allocations++;
                if (Trace) Calls.Append('A').Append(h).Append(':').Append(info.MemoryTypeIndex).Append(':').Append(info.AllocationSize).Append(';');
                memory = new(h);
                return Result.Success;
            }
        }
        public Result MapMemory(Device device, DeviceMemory memory, ulong offset, ulong size, uint flags, ref void* pointer)
        {
            lock (_gate)
            {
                MemoryState state = _memory[memory.Handle];
                if (state.Mapped || offset + size > state.Size) throw new InvalidOperationException("invalid map");
                state.Mapped = true;
                Maps++;
                if (Trace) Calls.Append('M').Append(memory.Handle).Append(':').Append(size).Append(';');
                pointer = (void*)(0x10000000UL + memory.Handle * 0x100000UL + offset);
                return Result.Success;
            }
        }
        public void UnmapMemory(Device device, DeviceMemory memory)
        {
            lock (_gate)
            {
                MemoryState state = _memory[memory.Handle];
                if (!state.Mapped) throw new InvalidOperationException("invalid unmap");
                state.Mapped = false;
                Unmaps++;
                if (Trace) Calls.Append('U').Append(memory.Handle).Append(';');
            }
        }
        public void FreeMemory(Device device, DeviceMemory memory, void* callbacks)
        {
            lock (_gate)
            {
                if (!_memory.Remove(memory.Handle, out MemoryState state) || state.Mapped)
                    throw new InvalidOperationException("invalid native free");
                LiveBytes -= state.Size;
                LiveHeapBytes -= (state.Size + Page - 1) / Page * Page;
                Frees++;
                if (Trace) Calls.Append('F').Append(memory.Handle).Append(';');
            }
        }
    }
}

namespace Ryujinx.Graphics.Vulkan
{
    readonly struct VulkanPhysicalDevice
    {
        public readonly PhysicalDeviceProperties PhysicalDeviceProperties;
        public readonly PhysicalDeviceMemoryProperties PhysicalDeviceMemoryProperties;

        public VulkanPhysicalDevice(PhysicalDeviceProperties properties, PhysicalDeviceMemoryProperties memoryProperties)
        {
            PhysicalDeviceProperties = properties;
            PhysicalDeviceMemoryProperties = memoryProperties;
        }

        // MoltenVK v1.4.2 on an Apple GPU with unified memory (MVKDevice.mm initMemoryProperties, maxMemoryAllocationCount).
        public static VulkanPhysicalDevice MoltenVk() => new(
            new PhysicalDeviceProperties { Limits = new PhysicalDeviceLimits { MaxMemoryAllocationCount = 1u << 30 } },
            new PhysicalDeviceMemoryProperties
            {
                MemoryTypeCount = 3,
                MemoryTypes = new Fixed<MemoryType>(
                    new MemoryType { PropertyFlags = MemoryPropertyFlags.DeviceLocalBit },
                    new MemoryType { PropertyFlags = MemoryPropertyFlags.HostVisibleBit | MemoryPropertyFlags.HostCoherentBit |
                                                     MemoryPropertyFlags.HostCachedBit | MemoryPropertyFlags.DeviceLocalBit },
                    new MemoryType { PropertyFlags = MemoryPropertyFlags.DeviceLocalBit | MemoryPropertyFlags.LazilyAllocatedBit }),
                MemoryHeapCount = 1,
                MemoryHeaps = new Fixed<MemoryHeap>(new MemoryHeap { Size = 8UL << 30, Flags = MemoryHeapFlags.DeviceLocalBit }),
            });
    }

    // MemoryAllocation's host-import branch; not exercised here.
    sealed class HostMemoryAllocator
    {
        public void Free(Silk.NET.Vulkan.DeviceMemory memory, ulong offset, ulong size) => throw new NotSupportedException();
    }
}
