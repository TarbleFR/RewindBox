using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Text.Json;
using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.GAL.Multithreading;
using Ryujinx.Graphics.GAL.Multithreading.Commands;
using Ryujinx.Graphics.GAL.Multithreading.Model;
using Ryujinx.Graphics.GAL.Multithreading.Resources;

static class Program
{
#if ADAPTED
    const bool Adapted = true;
#else
    const bool Adapted = false;
#endif
    static void Check(bool value, string reason)
    {
        if (!value) throw new Exception(reason);
    }

    static SetRenderTargetsCommand Command(ThreadedRenderer transport, ITexture[] colors, int count, ITexture depth)
    {
        SetRenderTargetsCommand command = default;
        command.Set(count, new TableRef<ITexture[]>(transport, colors), new TableRef<ITexture>(transport, depth));
        return command;
    }

    static (bool Returned, bool Cleared) RentalState(ITexture[] original)
    {
        ITexture[] next = SetRenderTargetsCommand.ArrayPool.Rent(original.Length);
        bool same = ReferenceEquals(next, original), cleared = true;
        foreach (ITexture item in next) cleared &= item == null;
        SetRenderTargetsCommand.ArrayPool.Return(next, clearArray: true);
        return (same, same && cleared);
    }

    static bool Success(List<string> semantics)
    {
        ThreadedRenderer transport = new();
        Backend backend = new() { Capture = true };
        HostTexture first = new("first"), depth = new("depth");
        ITexture[] colors = SetRenderTargetsCommand.ArrayPool.Rent(3);
        // A nonlogical tail must never reach the backend, and must be cleared too.
        Array.Fill(colors, new HostTexture("tail"));
        colors[0] = new ThreadedTexture { Base = first };
        colors[1] = null;
        colors[2] = new ThreadedTexture { Base = first };
        SetRenderTargetsCommand command = Command(transport, colors, 3, new ThreadedTexture { Base = depth });
        SetRenderTargetsCommand.Run(ref command, transport, backend);
        Check(backend.Calls == 1 && backend.Count == 3, "logical color count/call count");
        Check(ReferenceEquals(backend.First, first) && ReferenceEquals(backend.Last, first), "color identity/alias");
        Check(backend.Middle == null && ReferenceEquals(backend.Depth, depth), "null holes/depth identity");
        Check(transport.Consumed == 2 && transport.Live == 0, "success FIFO reference consumption");
        semantics.Add("colors:3:first,null,first;depth:depth;refs:0,1;calls:1");
        (bool returned, bool cleared) = RentalState(colors);
        Check(returned, "success must return its rental");
        Check(cleared == Adapted, "success pool root clearing");

        transport = new(); backend = new() { Capture = true };
        colors = SetRenderTargetsCommand.ArrayPool.Rent(0);
        command = Command(transport, colors, 0, null);
        SetRenderTargetsCommand.Run(ref command, transport, backend);
        Check(backend.Count == 0 && backend.Depth == null && transport.Consumed == 2, "empty render targets");
        semantics.Add("colors:0;depth:null;refs:0,1;calls:1");
        RentalState(colors);
        return cleared;
    }

    static bool ConversionFailure(List<string> exceptions)
    {
        ThreadedRenderer transport = new(); Backend backend = new();
        ITexture[] colors = SetRenderTargetsCommand.ArrayPool.Rent(3);
        colors[0] = new ThreadedTexture { Base = new HostTexture("first") };
        colors[1] = new HostTexture("invalid threaded texture");
        colors[2] = new ThreadedTexture { Base = new HostTexture("last") };
        SetRenderTargetsCommand command = Command(transport, colors, 3, new ThreadedTexture());
        try { SetRenderTargetsCommand.Run(ref command, transport, backend); throw new Exception("conversion should throw"); }
        catch (InvalidCastException) { }
        Check(transport.Consumed == 1 && transport.Live == 1 && backend.Calls == 0, "conversion order changed");
        exceptions.Add("InvalidCastException;refs:0;calls:0;depth-remains-for-queue-teardown");
        transport.Clear();
        (bool returned, bool cleared) = RentalState(colors);
        Check(returned == Adapted && cleared == Adapted, "conversion return/clear");
        if (!returned) Array.Clear(colors);
        return returned;
    }

    static bool BackendFailure(List<string> exceptions)
    {
        ThreadedRenderer transport = new(); Backend backend = new() { Failure = new BackendException() };
        ITexture[] colors = SetRenderTargetsCommand.ArrayPool.Rent(2);
        colors[0] = new ThreadedTexture { Base = new HostTexture("first") };
        colors[1] = null;
        SetRenderTargetsCommand command = Command(transport, colors, 2, null);
        try { SetRenderTargetsCommand.Run(ref command, transport, backend); throw new Exception("backend should throw"); }
        catch (BackendException error) { Check(ReferenceEquals(error, backend.Failure), "exception identity"); }
        Check(transport.Consumed == 2 && transport.Live == 0 && backend.Calls == 1, "backend call/reference order");
        exceptions.Add("BackendException:same-instance;refs:0,1;calls:1");
        (bool returned, bool cleared) = RentalState(colors);
        Check(returned == Adapted && cleared == Adapted, "backend return/clear");
        if (!returned) Array.Clear(colors);
        return returned;
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    static WeakReference ReleaseIntoPool()
    {
        ThreadedRenderer transport = new(); Backend backend = new();
        HostTexture resource = new("weak");
        ITexture[] colors = SetRenderTargetsCommand.ArrayPool.Rent(7);
        Array.Clear(colors);
        colors[0] = new ThreadedTexture { Base = resource };
        SetRenderTargetsCommand command = Command(transport, colors, 1, null);
        SetRenderTargetsCommand.Run(ref command, transport, backend);
        return new WeakReference(resource);
    }

    static long WarmAllocations()
    {
        ThreadedRenderer transport = new(); Backend backend = new();
        ThreadedTexture texture = new() { Base = new HostTexture("warm") };
        for (int i = 0; i < 10000; i++) Iteration(transport, backend, texture);
        long before = GC.GetAllocatedBytesForCurrentThread();
        for (int i = 0; i < 50000; i++) Iteration(transport, backend, texture);
        return GC.GetAllocatedBytesForCurrentThread() - before;
    }

    static void Iteration(ThreadedRenderer transport, Backend backend, ThreadedTexture texture)
    {
        transport.Clear();
        ITexture[] colors = SetRenderTargetsCommand.ArrayPool.Rent(3);
        colors[0] = texture; colors[1] = null; colors[2] = texture;
        SetRenderTargetsCommand command = Command(transport, colors, 3, texture);
        SetRenderTargetsCommand.Run(ref command, transport, backend);
    }

    static void Main()
    {
        List<string> semantics = new(), exceptions = new();
        bool successCleared = Success(semantics);
        bool conversionReturned = ConversionFailure(exceptions), backendReturned = BackendFailure(exceptions);
        WeakReference weak = ReleaseIntoPool();
        GC.Collect(); GC.WaitForPendingFinalizers(); GC.Collect();
        bool retains = weak.IsAlive;
        Check(retains != Adapted, "returned array must not root a texture graph");
        long allocated = WarmAllocations();
        Check(allocated == 0, "warm command allocated managed memory");
        Console.WriteLine(JsonSerializer.Serialize(new { semantics, exceptions, successCleared, conversionReturned,
            backendReturned, poolRetainsResource = retains, warmAllocatedBytes = allocated, warmCommands = 50000 }));
    }
}

namespace Ryujinx.Graphics.GAL
{
    interface ITexture { }
    interface IPipeline { void SetRenderTargets(Span<ITexture> colors, ITexture depthStencil); }
    interface IRenderer { IPipeline Pipeline { get; } }
    sealed class HostTexture(string name) : ITexture { public readonly string Name = name; }
    sealed class BackendException : Exception { }
    sealed class Backend : IRenderer, IPipeline
    {
        public IPipeline Pipeline => this;
        public bool Capture;
        public int Calls, Count;
        public ITexture First, Middle, Last, Depth;
        public BackendException Failure;
        public void SetRenderTargets(Span<ITexture> colors, ITexture depthStencil)
        {
            Calls++; Count = colors.Length;
            if (Capture)
            {
                First = colors.Length > 0 ? colors[0] : null;
                Middle = colors.Length > 1 ? colors[1] : null;
                Last = colors.Length > 2 ? colors[2] : null;
                Depth = depthStencil;
            }
            if (Failure != null) throw Failure;
        }
    }
}

namespace Ryujinx.Graphics.GAL.Multithreading.Resources
{
    sealed class ThreadedTexture : ITexture { public ITexture Base; }
}

namespace Ryujinx.Graphics.GAL.Multithreading.Commands
{
    enum CommandType { SetRenderTargets }
}

namespace Ryujinx.Graphics.GAL.Multithreading
{
    sealed class ThreadedRenderer
    {
        readonly object[] _slots = new object[2];
        int _producer;
        public int Consumed;
        public int Live => (_slots[0] == null ? 0 : 1) + (_slots[1] == null ? 0 : 1);
        public int AddTableRef(object value)
        {
            if (_producer >= 2) throw new Exception("too many producer references");
            _slots[_producer] = value;
            return _producer++;
        }
        public object RemoveTableRef(int index)
        {
            if (index != Consumed) throw new Exception("FIFO reference order changed");
            object value = _slots[index]; _slots[index] = null; Consumed++;
            return value;
        }
        public void Clear() { Array.Clear(_slots); _producer = 0; Consumed = 0; }
    }
}
