using Ryujinx.Common.Collections;
using Ryujinx.Memory.Range;
using System;
using System.Collections.Generic;

namespace Ryujinx.Graphics.Gpu.Memory
{
    enum BufferStage : byte { Vertex = 1, Copy = 9, None = 12 }
    static class MemoryManager { public const ulong PteUnmapped = ulong.MaxValue; }
    static class Trace
    {
        public static bool Enabled = true;
        public static readonly List<string> Events = new();
        public static Action OnSynchronize;
        public static void Record(string value) { if (Enabled) Events.Add(value); }
    }
    sealed class Buffer
    {
        public ulong Address;
        public void SynchronizeMemory(ulong address, ulong size)
        {
            if (Trace.Enabled) Trace.Record($"sync:{address}:{size}");
            Trace.OnSynchronize?.Invoke();
        }
        public void SignalModified(ulong address, ulong size, BufferStage stage)
        { if (Trace.Enabled) Trace.Record($"dirty:{address}:{size}:{stage}"); }
    }
    sealed class MultiRangeBuffer : IMultiRangeItem
    {
        readonly MultiRange _range;
        public readonly int Id;
        public static long RangeReads;
        public static long EqualCalls;
        public MultiRange Range { get { RangeReads++; return _range; } }
        public MultiRangeBuffer(int id, MultiRange range) { Id = id; _range = range; }
        public void AddModifiedRegion(MultiRange range, int sequence)
        { if (Trace.Enabled) Trace.Record($"virtual:{Id}:{sequence}"); }
        // Instrument only the comparison count; preserve the production
        // MultiRangeBuffer's object-identity equality behavior.
        public override bool Equals(object other) { EqualCalls++; return ReferenceEquals(this, other); }
        public override int GetHashCode() => System.Runtime.CompilerServices.RuntimeHelpers.GetHashCode(this);
    }
    sealed class CapabilityBoundary { public bool SupportsSparseBuffer; }
    sealed class ContextBoundary { public readonly CapabilityBoundary Capabilities = new(); }
    sealed class BufferCache
    {
        readonly MultiRangeList<MultiRangeBuffer> _multiRangeBuffers;
        readonly ContextBoundary _context = new();
        readonly Buffer _physical = new();
        int _virtualModifiedSequenceNumber;
        public int Sequence { get => _virtualModifiedSequenceNumber; set => _virtualModifiedSequenceNumber = value; }
        public bool Sparse { set => _context.Capabilities.SupportsSparseBuffer = value; }
        public BufferCache(MultiRangeList<MultiRangeBuffer> ranges) { _multiRangeBuffers = ranges; }
        Buffer GetOrCreateBuffer(ulong address, ulong size, BufferStage stage)
        {
            if (Trace.Enabled) Trace.Record($"get:{address}:{size}:{stage}");
            _physical.Address = address;
            return _physical;
        }
        void Touch(Buffer buffer) { if (Trace.Enabled) Trace.Record($"touch:{buffer.Address}"); }
        public MultiRangeBuffer Lookup(MultiRange range, BufferStage stage = BufferStage.Copy, bool write = false)
            => GetBuffer(range, stage, write);

        /* PRODUCTION_GET_BUFFER */

        /* PRODUCTION_BUFFER_PREDICATE */
    }
}
