using System;
using System.Collections.Generic;
using System.Threading;

static class AllocationProbe
{
    public static long SizeReads, BlockVisits, Comparisons;
    public static Ryujinx.Graphics.Vulkan.MemoryAllocatorBlockList.Block Visit(
        Ryujinx.Graphics.Vulkan.MemoryAllocatorBlockList.Block block)
    {
        Interlocked.Increment(ref BlockVisits); return block;
    }
    public static bool FailBlock, FailPublication;
    public static void BeforeBlock()
    {
        if (FailBlock) { FailBlock = false; throw new OutOfMemoryException("injected block construction failure"); }
    }
    public static void BeforePublication()
    {
        if (FailPublication) { FailPublication = false; throw new OutOfMemoryException("injected list publication failure"); }
    }
}
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
    unsafe sealed class Vk
    {
        sealed class MemoryState { public ulong Size; public bool Mapped, Imported; public byte[] Bytes; }
        readonly Dictionary<ulong, MemoryState> _memory = new();
        readonly object _gate = new();
        ulong _next;
        public int Allocations, Frees, Maps, Unmaps, MapFailures, MapThrows, AllocationFailures;
        public bool StorePayloads;
        public ulong LiveBytes, PeakBytes;
        public void StorePattern(DeviceMemory memory, ulong offset, ulong size, int id)
        {
            lock (_gate)
            {
                byte[] bytes = _memory[memory.Handle].Bytes;
                for (ulong i = 0; i < size; i++) bytes[checked((int)(offset + i))] = (byte)((id * 37 + (int)i * 13) | 1);
            }
        }
        public bool CheckPattern(DeviceMemory memory, ulong offset, ulong size, int id)
        {
            lock (_gate)
            {
                byte[] bytes = _memory[memory.Handle].Bytes;
                for (ulong i = 0; i < size; i++)
                    if (bytes[checked((int)(offset + i))] != (byte)((id * 37 + (int)i * 13) | 1)) return false;
                return true;
            }
        }
        public int Live { get { lock (_gate) return _memory.Count; } }
        public int Mapped { get { lock (_gate) { int count = 0; foreach (var v in _memory.Values) if (v.Mapped) count++; return count; } } }
        public DeviceMemory Import(ulong size)
        {
            lock (_gate) { ulong h = ++_next; _memory.Add(h, new() { Size = size, Imported = true }); return new(h); }
        }
        public Result AllocateMemory(Device device, in MemoryAllocateInfo info, void* callbacks, out DeviceMemory memory)
        {
            lock (_gate)
            {
                if (AllocationFailures > 0) { AllocationFailures--; memory = default; return Result.ErrorOutOfDeviceMemory; }
                ulong h = ++_next;
                _memory.Add(h, new() { Size = info.AllocationSize, Bytes = StorePayloads ? new byte[checked((int)info.AllocationSize)] : null });
                LiveBytes += info.AllocationSize; PeakBytes = Math.Max(PeakBytes, LiveBytes);
                Allocations++; memory = new(h); return Result.Success;
            }
        }
        public Result MapMemory(Device device, DeviceMemory memory, ulong offset, ulong size, uint flags, ref void* pointer)
        {
            lock (_gate)
            {
                MemoryState state = _memory[memory.Handle];
                if (MapThrows > 0) { MapThrows--; throw new InvalidOperationException("injected driver binding exception"); }
                if (MapFailures > 0) { MapFailures--; return Result.ErrorMemoryMapFailed; }
                if (state.Mapped || offset + size > state.Size) throw new InvalidOperationException("invalid map");
                state.Mapped = true; Maps++;
                pointer = (void*)(0x10000000UL + memory.Handle * 0x100000UL + offset);
                return Result.Success;
            }
        }
        public void UnmapMemory(Device device, DeviceMemory memory)
        {
            lock (_gate)
            {
                MemoryState state = _memory[memory.Handle];
                if (!state.Mapped || state.Imported) throw new InvalidOperationException("invalid unmap");
                state.Mapped = false; Unmaps++;
            }
        }
        public void FreeMemory(Device device, DeviceMemory memory, void* callbacks)
        {
            lock (_gate)
            {
                if (!_memory.Remove(memory.Handle, out MemoryState state) || state.Mapped)
                    throw new InvalidOperationException("invalid native free");
                if (!state.Imported) LiveBytes -= state.Size;
                Frees++;
            }
        }
    }
}
namespace Ryujinx.Graphics.Vulkan
{
    // This independent host-import allocator is not exercised by these tests.
    sealed class HostMemoryAllocator
    {
        public void Free(Silk.NET.Vulkan.DeviceMemory memory, ulong offset, ulong size)
            => throw new NotSupportedException();
    }
}
