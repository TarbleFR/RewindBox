using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using Ryujinx.Graphics.Gpu.Engine.Threed;
using Ryujinx.Graphics.Gpu.Engine.Types;

namespace Ryujinx.Graphics.Gpu.Engine
{
    sealed class DeviceStateWithShadow<T> where T : struct
    {
        public T State;
    }
}
namespace Ryujinx.Graphics.Gpu.Engine.Threed
{
    // The updater uses only this field of the real, much larger register file.
    struct ThreedClassState { public UniformBufferState UniformBufferState; }
    enum ShaderType { Vertex, TessellationControl, TessellationEvaluation, Geometry, Fragment }
}
namespace Ryujinx.Graphics.Gpu
{
    sealed class GpuChannel
    {
        public Memory.MemoryManager MemoryManager;
        public Memory.BindingBoundary BufferManager;
    }
}
namespace Ryujinx.Graphics.Gpu.Memory
{
    sealed class BoundaryFailure : Exception { }
    sealed class Trace
    {
        public bool Record = true;
        public int Translates, Writes, Dirties, Binds;
        public int FailTranslate, FailWrite;
        public bool Changed = true;
        public Action<string> OnBoundary;
        public ulong Sink;
        public readonly List<string> Events = new();
        public void Add(string text) { if (Record) Events.Add(text); }
    }
    sealed class MemoryManager
    {
        public readonly PhysicalBoundary Physical;
        public readonly Trace Trace;
        public MemoryManager(Trace trace) { Trace = trace; Physical = new PhysicalBoundary(trace); }
        public ulong Translate(ulong address)
        {
            Trace.Translates++;
            if (Trace.Record) Trace.Add($"translate:{address:x16}");
            Trace.OnBoundary?.Invoke("translate");
            if (Trace.Translates == Trace.FailTranslate) throw new BoundaryFailure();
            return address ^ 0x1234000000000000;
        }
    }
    sealed class PhysicalBoundary
    {
        public readonly Trace Trace;
        public readonly CacheBoundary BufferCache;
        public PhysicalBoundary(Trace trace) { Trace = trace; BufferCache = new CacheBoundary(trace); }
        public bool WriteWithRedundancyCheck(ulong address, ReadOnlySpan<byte> bytes)
        {
            Trace.Writes++;
            if (Trace.Record) Trace.Add($"write:{address:x16}:{Convert.ToHexString(bytes)}");
            else Trace.Sink ^= address ^ (ulong)bytes.Length ^ (uint)MemoryMarshal.Cast<byte, int>(bytes)[0];
            Trace.OnBoundary?.Invoke("write");
            if (Trace.Writes == Trace.FailWrite) throw new BoundaryFailure();
            return Trace.Changed;
        }
    }
    sealed class CacheBoundary
    {
        readonly Trace trace;
        public CacheBoundary(Trace trace) { this.trace = trace; }
        public void ForceDirty(MemoryManager manager, ulong address, ulong size)
        {
            trace.Dirties++;
            if (trace.Record) trace.Add($"dirty:{address:x16}:{size}");
        }
    }
    sealed class BindingBoundary
    {
        readonly Trace trace;
        public BindingBoundary(Trace trace) { this.trace = trace; }
        public void SetGraphicsUniformBuffer(int stage, int index, ulong address, uint size)
        {
            trace.Binds++;
            if (trace.Record) trace.Add($"bind:{stage}:{index}:{address:x16}:{size}");
        }
    }
}
