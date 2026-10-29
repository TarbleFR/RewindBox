using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;
using Ryujinx.HLE.HOS.Kernel.Ipc;
using Ryujinx.HLE.HOS.Kernel.Memory;
using Ryujinx.HLE.HOS.Kernel.Process;
using Ryujinx.HLE.HOS.Kernel.Threading;
using Ryujinx.Horizon.Common;

namespace Ryujinx.HLE.HOS.Kernel.Process { class KProcess { } }
namespace Ryujinx.HLE.HOS.Kernel.Threading { class KThread { } class KWritableEvent { } }
namespace Ryujinx.HLE.HOS.Kernel.Memory
{
    class KPageTableBase
    {
        public const int PageSize = 4096;
        public readonly List<string> Calls = new();
        public Result CopyDataFromCurrentProcess(ulong address, ulong size, MemoryState stateMask, MemoryState state, KMemoryPermission permission, MemoryAttribute attributeMask, MemoryAttribute attribute, ulong source)
        { Calls.Add($"copy:{address}:{size}:{source}:{state}:{permission}"); return Result.Success; }
        public Result UnmapNoAttributeIfStateEquals(ulong address, ulong size, MemoryState state)
        { Calls.Add($"unmap:{address}:{size}:{state}"); return Result.Success; }
        public Result UnmapIpcRestorePermission(ulong address, ulong size, MemoryState state)
        { Calls.Add($"restore:{address}:{size}:{state}"); return Result.Success; }
    }
}

static class Program
{
    static int _checks, _cases;
    static bool _candidate;
    static readonly StringBuilder DescriptorTrace = new();
    static void Check(bool condition, string message) { _checks++; if (!condition) throw new Exception(message); }
    [MethodImpl(MethodImplOptions.NoInlining)]
    static (WeakReference[] weak, ReturnBoundary owner) Participants()
    {
        ReturnBoundary owner = new();
        KThread client = new(); KProcess server = new(); KWritableEvent signal = new();
        KSessionRequest request = owner.RequestPool.Allocate().Set(client, 4097, 5000, signal);
        request.ServerProcess = server;
        request.BufferDescriptorTable.AddSendBuffer(4097, 8193, 31, MemoryState.IpcBuffer0);
        owner.Return(request);
        return (new[] { new WeakReference(client), new WeakReference(server), new WeakReference(signal) }, owner);
    }
    static void Reuse()
    {
        ReturnBoundary owner = new();
        KSessionRequest previous = null;
        KBufferDescriptorTable table = null;
        for (int iteration = 0; iteration < 128; iteration++)
        {
            KThread client = new(); KProcess server = new(); KWritableEvent signal = iteration % 2 == 0 ? new() : null;
            KSessionRequest request = owner.RequestPool.Allocate().Set(client, (ulong)(4097 + iteration), 5000, signal);
            if (previous != null) Check(ReferenceEquals(previous, request), "Request not reused");
            if (table != null) Check(ReferenceEquals(table, request.BufferDescriptorTable), "Descriptor allocation introduced");
            table = request.BufferDescriptorTable;
            request.ServerProcess = server;
            Check(request.ClientThread == client && request.AsyncEvent == signal && request.ServerProcess == server, "Request setup changed");
            Check(request.CustomCmdBuffAddr == (ulong)(4097 + iteration) && request.CustomCmdBuffSize == 5000, "Message range changed");
            for (int i = 0; i < 8; i++)
            {
                Check(table.AddSendBuffer((ulong)(4097 + i), (ulong)(8193 + i), (ulong)(31 + i), MemoryState.IpcBuffer0) == Result.Success, "Send descriptor");
                Check(table.AddReceiveBuffer((ulong)(16385 + i), (ulong)(24577 + i), (ulong)(32 + i), MemoryState.IpcBuffer1) == Result.Success, "Receive descriptor");
                Check(table.AddExchangeBuffer((ulong)(32769 + i), (ulong)(40961 + i), (ulong)(33 + i), MemoryState.IpcBuffer3) == Result.Success, "Exchange descriptor");
            }
            Check(table.AddSendBuffer(0, 0, 0, MemoryState.IpcBuffer0) == KernelResult.OutOfMemory, "Descriptor limit changed");
            KPageTableBase memory = new();
            Check(table.CopyBuffersToClient(memory) == Result.Success, "Copy descriptors");
            Check(table.UnmapServerBuffers(memory) == Result.Success, "Unmap descriptors");
            Check(table.RestoreClientBuffers(memory) == Result.Success, "Restore descriptors");
            DescriptorTrace.AppendJoin(';', memory.Calls).Append('|');
            int calls = memory.Calls.Count;
            owner.Return(request);
            Check(memory.Calls.Count == calls, "Return changed native ownership or memory");
            if (_candidate) Check(request.ClientThread == null && request.ServerProcess == null && request.AsyncEvent == null, "Pooled request holds participants");
            Check(ReferenceEquals(table, request.BufferDescriptorTable), "Return discarded reusable descriptors");
            previous = request;
            _cases++;
        }
    }
    static void ConcurrentReuse()
    {
        ReturnBoundary owner = new();
        Parallel.For(0, 8, _ =>
        {
            for (int i = 0; i < 500; i++)
            {
                KThread thread = new();
                KSessionRequest request = owner.RequestPool.Allocate().Set(thread, (ulong)i, 64);
                if (request.ClientThread != thread) throw new Exception("Concurrent request ownership");
                owner.Return(request);
            }
        });
        _cases += 8;
    }
    public static void Main(string[] args)
    {
        _candidate = args[0] == "candidate";
        Reuse(); ConcurrentReuse();
        var retention = Participants();
        GC.Collect(); GC.WaitForPendingFinalizers(); GC.Collect();
        int retained = retention.weak.Count(reference => reference.IsAlive);
        Check(retained == (_candidate ? 0 : 3), "Completed IPC participants retained");
        GC.KeepAlive(retention.owner);
        Console.WriteLine(JsonSerializer.Serialize(new {
            variant = args[0], checks = _checks, scenarios = _cases,
            retainedParticipants = retained,
            descriptorDigest = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(DescriptorTrace.ToString()))),
            concurrentPoolCycles = 4000,
        }));
    }
}
