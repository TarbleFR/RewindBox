using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using Ryujinx.Cpu.LightningJit;
using ExecutionContext = Ryujinx.Cpu.LightningJit.State.ExecutionContext;

// These adapters represent unrelated engine services. The complete production
// NativeInterface and the exact production VirtualMemoryEvent body are compiled.
namespace ARMeilleure.Memory { public interface IMemoryManager {} }
namespace Ryujinx.Cpu.LightningJit.State
{
    class ExecutionContext
    {
        public ulong ThreadUid;
        public ulong Dispatch;
        public bool FailRead;
        public ulong Pc => FailRead ? throw new InvalidOperationException("context adapter read failed") : Dispatch;
        public int ExecutionMode;
        public ulong CntfrqEl0, CntpctEl0;
        public bool Running;
        public void OnBreak(ulong address, int imm) {}
        public void OnSupervisorCall(ulong address, int imm) {}
        public void OnUndefined(ulong address, int opcode) {}
        public void CheckInterrupt() {}
    }
}
namespace Ryujinx.Cpu.LightningJit
{
    class Translator
    {
        public nint GetOrTranslatePointer(nint frame, ulong address, int mode) => 0;
        public void InvalidateJitCacheRegion(ulong address, int size) {}
    }
}
namespace Ryujinx.Memory
{
    class InvalidMemoryRegionException : Exception
    {
        public InvalidMemoryRegionException(string text) : base(text) {}
    }
}
class Program
{
    private static int _checks;
    private static void Check(bool value, string message)
    {
        Interlocked.Increment(ref _checks);
        if (!value) throw new Exception(message);
    }
    private static void Guard(GuardProbe probe, ulong address, string context)
    {
        try { probe.Run(address, 1, true); throw new Exception("Invalid guard was allowed"); }
        catch (Ryujinx.Memory.InvalidMemoryRegionException error)
        {
            Check(error.Message.StartsWith($"Native page-table guard: relativeOffset=0x{address:X}; size=1; write=True; tableBytes=0x40000000; "), "Original guard fields");
            Check(error.Message.Contains(context), "Expected guest context");
            Check(error.Message.Contains("sizeIsSignalHint=True") && error.Message.Contains("faultPcKnown=False"), "Diagnostic limits explicit");
            Check(error.Message.Length < 300, "Bounded diagnostic");
        }
    }
    static void Main()
    {
        NativeInterface.UnregisterThread();
        var probe = new GuardProbe();
        Guard(probe, 0x40000003, "guestContext=unavailable");
        Guard(probe, 0x40000000, "guestContext=unavailable");
        Check(probe.Commitments.Count == 0, "Guard never committed");
        Check(probe.Run(0x3ffffff8, 1, false) == 0x13ffffff8, "Original lazy commitment result");
        Check(probe.Commitments.Count == 1 && probe.Commitments[0] == 0x7ffffff000, "Original guest page calculation");

        var execution = new ExecutionContext { ThreadUid = 12, Dispatch = 0x800123450 };
        NativeInterface.RegisterThread(execution, null, null);
        Guard(probe, 0x40000003, "guestThread=12; lastGuestDispatch=0x800123450");
        execution.Dispatch = 0x801001000;
        Guard(probe, 0x40000003, "lastGuestDispatch=0x801001000");
        execution.FailRead = true;
        Guard(probe, 0x40000003, "guestContext=unavailable");
        NativeInterface.UnregisterThread();
        Guard(probe, 0x40000003, "guestContext=unavailable");

        var failures = new List<Exception>();
        using var barrier = new Barrier(4);
        var threads = new Thread[4];
        for (int index = 0; index < threads.Length; index++)
        {
            int own = index;
            threads[index] = new Thread(() => {
                try
                {
                    var local = new ExecutionContext { ThreadUid = (ulong)(own + 100), Dispatch = (ulong)(0x2000 + own * 4) };
                    var localProbe = new GuardProbe();
                    NativeInterface.RegisterThread(local, null, null);
                    barrier.SignalAndWait();
                    for (int iteration = 0; iteration < 32; iteration++)
                        Guard(localProbe, 0x40000003, $"guestThread={local.ThreadUid}; lastGuestDispatch=0x{local.Dispatch:X}");
                    NativeInterface.UnregisterThread();
                    Guard(localProbe, 0x40000003, "guestContext=unavailable");
                }
                catch (Exception error) { lock(failures) failures.Add(error); }
            });
            threads[index].Start();
        }
        foreach (var thread in threads) thread.Join();
        Check(failures.Count == 0, "Thread contexts isolated");
        Check(NativeInterface.DescribeLastGuestDispatch().Contains("unavailable"), "Other threads do not register main thread");
        Console.WriteLine(JsonSerializer.Serialize(new { result = "passed", checks = _checks, threads = 4,
            productionNativeInterface = true, productionGuardBody = true, actualSignalHandlerExecuted = false,
            actualNativeContextExecuted = false, physicalDeviceTested = false }));
    }
}
