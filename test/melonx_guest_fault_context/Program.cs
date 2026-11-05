using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using Ryujinx.Common;
using Ryujinx.Cpu;
using Ryujinx.HLE.HOS.Kernel;
using Ryujinx.HLE.HOS.Kernel.Process;
using Ryujinx.HLE.HOS.Kernel.Threading;
using Ryujinx.HLE.Loaders.Elf;
using Ryujinx.Memory;

// Built as "Ryujinx.Tests" (Ryujinx.HLE's InternalsVisibleTo) against the production Ryujinx.HLE of one side. The crash
// modes run that side's real UnhandledException subscriptions (copied from its EmbeddedRuntime.cs by the driver), with
// the real journal, the real KThread, KProcess and HleProcessDebugger code and a real software address space
// (AddressSpaceManager) holding a guest frame chain, TLS and thread name; then they let an exception go unhandled on a
// thread and the process ends. Only the objects' construction is replaced (uninitialized objects whose fields are set).
public class ContextProxy : DispatchProxy
{
    public readonly Dictionary<int, ulong> X = new();
    public ulong Pc;

    protected override object Invoke(MethodInfo method, object[] args)
    {
        switch (method.Name)
        {
            case "GetX": return X.TryGetValue((int)args[0], out ulong value) ? value : 0UL;
            case "get_Pc": return Pc;
            case "get_IsAarch32": return false;
            default:
                return method.ReturnType != typeof(void) && method.ReturnType.IsValueType ? Activator.CreateInstance(method.ReturnType) : null;
        }
    }
}

sealed class FakeProcessContext : IProcessContext
{
    public FakeProcessContext(IVirtualMemoryManager memory) => AddressSpace = memory;
    public IVirtualMemoryManager AddressSpace { get; }
    public ulong AddressSpaceSize => 1UL << 30;
    public IExecutionContext CreateExecutionContext(ExceptionCallbacks exceptionCallbacks) => throw new NotSupportedException();
    public void Execute(IExecutionContext context, ulong codeAddress) => throw new NotSupportedException();
    public void InvalidateCacheRegion(ulong address, ulong size) { }
    public void Dispose() { }
}

static class Program
{
    public const ulong Base = 0x10000000;
    const string Guard = "Native page-table guard: relativeOffset=0x40000018; size=1; write=False; tableBytes=0x40000000; " +
                         "sizeIsSignalHint=True; guestContext=present; guestThread=80; lastGuestDispatch=0x10000400; faultPcKnown=False.";

    static void Set(object target, string name, object value)
    {
        for (Type type = target.GetType(); type != null; type = type.BaseType)
        {
            FieldInfo field = type.GetField(name, BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);
            if (field != null) { field.SetValue(target, value); return; }
        }
        throw new MissingFieldException(target.GetType().Name, name);
    }

    static object Get(object target, string name) =>
        target.GetType().GetField(name, BindingFlags.Instance | BindingFlags.NonPublic).GetValue(target);

    // A guest thread "FHeartBeatThread" (uid 80) of process "Fixture" (pid 81): the main image covers the code, the
    // stack and every register value, so the debugger resolves each one as main:offset.
    static KThread FakeGuest(bool withOwner)
    {
        MemoryBlock block = new(1 << 20);
        AddressSpaceManager memory = new(block, 1UL << 30);
        memory.Map(Base, 0, 1 << 20, MemoryMapFlags.None);
        memory.Write<ulong>(Base + 0x1000, Base + 0x1100);
        memory.Write<ulong>(Base + 0x1008, Base + 0x444);
        memory.Write<ulong>(Base + 0x1100, 0);
        memory.Write<ulong>(Base + 0x1108, Base + 0x888);
        memory.Write<ulong>(Base + 0x2000 + 0x1F8, Base + 0x3000);   // TLS -> ThreadType
        memory.Write<ushort>(Base + 0x3000 + 0x46, 1);               // ThreadType version 1
        memory.Write<ulong>(Base + 0x3000 + 0x1A0, Base + 0x4000);   // -> name
        memory.Write(Base + 0x4000, "FHeartBeatThread\0"u8);

        KProcess process = (KProcess)RuntimeHelpers.GetUninitializedObject(typeof(KProcess));
        Set(process, "<Name>k__BackingField", "Fixture");
        Set(process, "<Pid>k__BackingField", 81UL);
        Set(process, "<Context>k__BackingField", new FakeProcessContext(memory));
        HleProcessDebugger debugger = new(process);
        Set(debugger, "_loaded", 1);
        ((List<HleProcessDebugger.Image>)Get(debugger, "_images")).Add(new HleProcessDebugger.Image(Base, 1 << 20, Array.Empty<ElfSymbol>()) { Name = "main" });
        Set(process, "<Debugger>k__BackingField", debugger);

        IExecutionContext context = DispatchProxy.Create<IExecutionContext, ContextProxy>();
        ContextProxy registers = (ContextProxy)(object)context;
        for (int i = 0; i <= 28; i++) registers.X[i] = Base + 0x500 + (ulong)i * 8;
        registers.X[29] = Base + 0x1000;
        registers.X[30] = Base + 0x404;
        registers.X[31] = Base + 0x1800;
        registers.Pc = Base + 0x400;

        KThread thread = (KThread)RuntimeHelpers.GetUninitializedObject(typeof(KThread));
        if (withOwner) Set(thread, "<Owner>k__BackingField", process);
        Set(thread, "<Context>k__BackingField", context);
        Set(thread, "<ThreadUid>k__BackingField", 80UL);
        Set(thread, "_tlsAddress", Base + 0x2000);
        return thread;
    }

    static void Subscribe()
    {
        //__SUBSCRIPTION__
    }

    static int Crash(string mode)
    {
        Subscribe();
        Thread thread = new(() =>
        {
            if (mode != "host") KernelStatic.SetKernelContext(null, FakeGuest(mode != "broken"));
            Exception error = mode switch
            {
                "other" => new InvalidOperationException("synthetic engine crash"),
                "nested" => new AggregateException("wrapped", new InvalidMemoryRegionException(Guard)),
                _ => new InvalidMemoryRegionException(Guard),
            };
            throw error;
        });
        thread.Start();
        thread.Join();
        return 0; // not reached: the unhandled exception ends the process
    }

#if CANDIDATE
    static int Unit()
    {
        var result = new Dictionary<string, object>();
        result["nullForObject"] = GuestFaultContext.Describe(new object(), 250) == null;
        result["nullForOther"] = GuestFaultContext.Describe(new InvalidOperationException(), 250) == null;
        result["nullOnHostThread"] = GuestFaultContext.Describe(new InvalidMemoryRegionException(Guard), 250) == null;
        result["nestedDetected"] = GuestFaultContext.IsGuestMemoryFault(new AggregateException(new Exception("x", new InvalidMemoryRegionException(Guard))));
        Stopwatch watch = Stopwatch.StartNew();
        string late = GuestFaultContext.Capture(() => { Thread.Sleep(5000); return "late"; }, 250);
        result["timeoutText"] = late;
        result["timeoutMs"] = watch.ElapsedMilliseconds;
        result["throwText"] = GuestFaultContext.Capture(() => throw new InvalidMemoryRegionException(), 250);
        // Direct call on a guest thread, then the same text through the journal's real redactor.
        string direct = null;
        Thread guest = new(() =>
        {
            KernelStatic.SetKernelContext(null, FakeGuest(true));
            direct = GuestFaultContext.Describe(new InvalidMemoryRegionException(Guard), 250);
        });
        guest.Start();
        guest.Join();
        result["direct"] = direct;
        result["directSafeUnchanged"] = EmbeddedLaunchDiagnostics.Safe(direct) == direct;
        var frames = new System.Text.StringBuilder("Process: Fixture, PID: 81\nThread ID: 80 (FHeartBeatThread)\n");
        for (int i = 0; i < 100; i++) frames.Append($"   0x{Base + (ulong)i * 4:x16}\tmain:0x{i * 4:x4}\t\n");
        string bounded = GuestFaultContext.Format(80, "FHeartBeatThread", "\tX[00]:\t0x1\n\tPC:\t0x2\n", frames.ToString());
        result["boundedLength"] = bounded.Length;
        result["boundedFrameLines"] = bounded.Split('\n').Length;
        result["boundedEndsWithMore"] = bounded.EndsWith("(more frames not kept)");
        result["boundedKeepsX0"] = bounded.Contains("X[00]");
        string huge = GuestFaultContext.Format(80, new string('n', 5000), "", "");
        result["hugeLength"] = huge.Length;
        Console.WriteLine(JsonSerializer.Serialize(result));
        return 0;
    }
#endif

    static int Main(string[] args)
    {
        EmbeddedLaunchDiagnostics.ConfigureJournal(args[1]);
#if CANDIDATE
        if (args[0] == "unit") return Unit();
#endif
        return Crash(args[0]);
    }
}
