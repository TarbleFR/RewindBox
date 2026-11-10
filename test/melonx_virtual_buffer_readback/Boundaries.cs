using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using Ryujinx.Graphics.GAL;
using Ryujinx.Memory.Tracking;

namespace Ryujinx.Common { }
namespace Ryujinx.Graphics.Gpu
{
    sealed class GpuContext
    {
        public ulong SyncNumber;
        public int SequenceNumber;
        public readonly RendererBoundary Renderer = new();
        public void RegisterBufferMigration(Memory.BufferMigration migration) { }
        public void RegisterSyncAction(Synchronization.ISyncActionHandler handler) { }
    }
    sealed class RendererBoundary : IDisposable
    {
        internal sealed class Storage : IDisposable
        {
            public readonly byte[] Bytes;
            public readonly GCHandle Pin;
            public Storage(int length) { Bytes = new byte[length]; Pin = GCHandle.Alloc(Bytes, GCHandleType.Pinned); }
            public void Dispose() => Pin.Free();
        }
        readonly List<Storage> _storage = new() { null };
        readonly Storage _volatileScratch = new(65536);
        public readonly PipelineBoundary Pipeline;
        public int ActiveReads, ReadCalls, Disposals;
        public nint LastReadbackPointer;
        public bool FailNextRead;
        public bool VolatileReadback;
        public Action OnGetData;
        readonly Action _endRead;
        public RendererBoundary() { Pipeline = new(this); _endRead = EndRead; }
        void EndRead() { ActiveReads--; Disposals++; }
        public BufferHandle CreateBuffer(int length, BufferAccess access = default)
        {
            ulong id = (ulong)_storage.Count; _storage.Add(new Storage(length));
            return Unsafe.As<ulong, BufferHandle>(ref id);
        }
        public BufferHandle CreateBufferSparse(ReadOnlySpan<BufferRange> storages) => throw new NotSupportedException();
        public byte[] Bytes(BufferHandle handle) => _storage[(int)handle].Bytes;
        public unsafe PinnedSpan<byte> GetBufferData(BufferHandle handle, int offset, int size)
        {
            if (FailNextRead) { FailNextRead = false; throw new ProbeFailure(); }
            OnGetData?.Invoke();
            Storage storage = _storage[(int)handle];
            if (offset < 0 || size < 0 || offset + size > storage.Bytes.Length) throw new ArgumentOutOfRangeException();
            if (VolatileReadback)
            {
                InvalidateVolatileReadback();
                storage.Bytes.AsSpan(offset, size).CopyTo(_volatileScratch.Bytes);
                LastReadbackPointer = _volatileScratch.Pin.AddrOfPinnedObject();
                // Contract: this unowned scratch is valid only until the next
                // renderer operation, unlike a lease with an explicit disposer.
                return PinnedSpan<byte>.UnsafeFromSpan(_volatileScratch.Bytes.AsSpan(0, size));
            }
            ActiveReads++; ReadCalls++;
            LastReadbackPointer = storage.Pin.AddrOfPinnedObject() + offset;
            return new PinnedSpan<byte>((void*)LastReadbackPointer, size, _endRead);
        }
        public void SetBufferData(BufferHandle handle, int offset, ReadOnlySpan<byte> data) => data.CopyTo(Bytes(handle).AsSpan(offset));
        public void DeleteBuffer(BufferHandle handle) { }
        public void BackgroundContextAction(Action action, bool _) => action();
        public void WaitSync(ulong sync) { }
        public void InvalidateVolatileReadback() { if (VolatileReadback) Array.Fill(_volatileScratch.Bytes, (byte)238); }
        public void Dispose() { foreach (Storage item in _storage) item?.Dispose(); _volatileScratch.Dispose(); }
    }
    sealed class PipelineBoundary
    {
        readonly RendererBoundary _renderer;
        public readonly List<(BufferHandle source, BufferHandle destination, int sourceOffset, int destinationOffset, int size)> Copies = new();
        public bool RecordCopies = true, FailNextCopy;
        public Action BeforeCopy;
        public PipelineBoundary(RendererBoundary renderer) => _renderer = renderer;
        public void CopyBuffer(BufferHandle source, BufferHandle destination, int sourceOffset, int destinationOffset, int size)
        {
            _renderer.InvalidateVolatileReadback();
            BeforeCopy?.Invoke();
            if (FailNextCopy) { FailNextCopy = false; throw new ProbeFailure(); }
            if (RecordCopies) Copies.Add((source, destination, sourceOffset, destinationOffset, size));
            _renderer.Bytes(source).AsSpan(sourceOffset, size).CopyTo(_renderer.Bytes(destination).AsSpan(destinationOffset, size));
        }
    }
}
namespace Ryujinx.Graphics.Gpu.Memory
{
    enum BufferStage { None }
    struct BufferBackingState
    {
        public BufferBackingState(GpuContext context, Buffer buffer, BufferStage stage, Buffer[] bases) { }
        public BufferAccess SwitchAccess(Buffer buffer) => default;
        public bool ShouldChangeBacking(BufferStage stage = default) => false;
        public bool IsDeviceLocal => false;
        public void RecordSet() { }
        public void RecordFlush() { }
    }
    sealed class BufferPreFlush : IDisposable
    {
        public BufferPreFlush(GpuContext context, Buffer buffer, Action<BufferHandle, ulong, ulong> flush) { }
        public bool ShouldCopy => false;
        public void CopyModified(ulong address, ulong size) { }
        public void FlushWithAction(ulong address, ulong size, ulong sync) => throw new NotSupportedException();
        public void Dispose() { }
    }
    static class MemoryManager { public const ulong PageSize = 4096, PageMask = PageSize - 1; }
    sealed class BufferCache { public void BufferBackingChanged(Buffer buffer) { } }
    sealed class PhysicalMemory
    {
        public readonly byte[] Guest = new byte[65536];
        public readonly BufferCache BufferCache = new();
        public GpuContext Context;
        public int Writes;
        public bool FailNextWrite;
        public bool LastWriteAliasesReadback;
        public Action BeforeWrite;
        public RegionHandle BeginTracking(ulong a, ulong s, ResourceKind k, RegionFlags f) => new();
        public MultiRegionHandle BeginGranularTracking(ulong a, ulong s, ResourceKind k, RegionFlags f, List<IRegionHandle> b) => new();
        public ReadOnlySpan<byte> GetSpan(ulong address, int size) => Guest.AsSpan((int)address, size);
        public unsafe void WriteUntracked(ulong address, ReadOnlySpan<byte> data)
        {
            Check.That(Context.Renderer.ActiveReads > 0 || Context.Renderer.VolatileReadback, "backend pin survives through guest write");
            LastWriteAliasesReadback = (nint)Unsafe.AsPointer(ref MemoryMarshal.GetReference(data)) == Context.Renderer.LastReadbackPointer;
            BeforeWrite?.Invoke();
            if (FailNextWrite) { FailNextWrite = false; throw new ProbeFailure(); }
            data.CopyTo(Guest.AsSpan((int)address)); Writes++;
        }
    }
}
namespace Ryujinx.Memory.Tracking
{
    delegate void RegionSignal(ulong address, ulong size);
    enum ResourceKind { Buffer }
    enum RegionFlags { UnalignedAccess }
    interface IRegionHandle : IDisposable { bool Dirty { get; } }
    sealed class RegionHandle : IRegionHandle
    {
        public bool Dirty => false;
        public bool DirtyOrVolatile() => false;
        public void RegisterPreciseAction(Func<ulong, ulong, bool, bool> action) { }
        public void RegisterAction(RegionSignal action) { }
        public void Reprotect(bool value = false) { }
        public void ForceDirty() { }
        public void Dispose() { }
    }
    sealed class MultiRegionHandle : IRegionHandle
    {
        public bool Dirty => false;
        public IRegionHandle[] Handles => Array.Empty<IRegionHandle>();
        public void RegisterPreciseAction(ulong address, ulong size, Func<ulong, ulong, bool, bool> action) { }
        public void RegisterAction(ulong address, ulong size, RegionSignal action) { }
        public void QueryModified(ulong address, ulong size, Action<ulong, ulong> action, int sequence) { }
        public void ForceDirty(ulong address, ulong size) { }
        public void Dispose() { }
    }
}
sealed class ProbeFailure : Exception { }
