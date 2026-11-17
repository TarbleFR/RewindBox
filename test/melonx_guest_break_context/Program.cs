using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using Ryujinx.Common;
using Ryujinx.Cpu;
using Ryujinx.HLE.HOS.Kernel;
using Ryujinx.HLE.HOS.Kernel.Process;
using Ryujinx.HLE.HOS.Kernel.SupervisorCall;
using Ryujinx.HLE.HOS.Kernel.Threading;
using Ryujinx.HLE.Loaders.Elf;
using Ryujinx.Memory;

// Built as "Ryujinx.Tests" (Ryujinx.HLE's InternalsVisibleTo) against the candidate's production Ryujinx.HLE. It runs
// the production GuestBreakContext with the real journal, the real KThread, KProcess and HleProcessDebugger code and a
// real software address space (AddressSpaceManager) holding a guest frame chain, TLS, a thread name and the break's info
// bytes (taken from test/melonx_guest_fault_context/Program.cs). Only the objects' construction is replaced
// (uninitialized objects whose fields are set).
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
    public const ulong Info = Base + 0x5000;

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

    // A guest thread "MainThread" (uid 72) of process "Fixture" (pid 81) at svcBreak(reason, Info, size): the main image
    // covers the code, the stack and every register value, so the debugger resolves each one as main:offset.
    static KThread FakeGuest(bool withOwner, ulong reason, ulong info, ulong size)
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
        memory.Write(Base + 0x4000, "MainThread\0"u8);
        memory.Write<uint>(Info, 0x00000202);                        // result 2002-0001
        for (uint i = 1; i < 64; i++) memory.Write<uint>(Info + i * 4, 0xA0000000 + i);

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
        for (int i = 3; i <= 28; i++) registers.X[i] = Base + 0x500 + (ulong)i * 8;
        registers.X[0] = reason;
        registers.X[1] = info;
        registers.X[2] = size;
        registers.X[29] = Base + 0x1000;
        registers.X[30] = Base + 0x404;
        registers.X[31] = Base + 0x1800;
        registers.Pc = Base + 0x400;

        KThread thread = (KThread)RuntimeHelpers.GetUninitializedObject(typeof(KThread));
        if (withOwner) Set(thread, "<Owner>k__BackingField", process);
        Set(thread, "<Context>k__BackingField", context);
        Set(thread, "<ThreadUid>k__BackingField", 72UL);
        Set(thread, "_tlsAddress", Base + 0x2000);
        return thread;
    }

    static string Journal(string path, int skip)
    {
        string[] lines = File.Exists(path) ? File.ReadAllLines(path) : Array.Empty<string>();
        var rows = new List<string>();
        for (int i = skip; i < lines.Length; i++)
        {
            using JsonDocument row = JsonDocument.Parse(lines[i][lines[i].IndexOf('{')..]);
            rows.Add(row.RootElement.GetProperty("stage").GetString() + "/" + row.RootElement.GetProperty("status").GetString() +
                     "/" + row.RootElement.GetProperty("diagnostic").GetString());
        }
        return string.Join("\u0001", rows);
    }

    static int Main(string[] args)
    {
        string journal = args[0];
        EmbeddedLaunchDiagnostics.ConfigureJournal(journal);
        var result = new Dictionary<string, object>();

        // Every register a guest address: the debugger's printout resolves each one from the images (a value outside
        // them is looked up in the process's page table, which this fixture does not build). The size is then past 256.
        result["registers"] = GuestBreakContext.Describe(FakeGuest(true, Base + 0x500, Info, Base + 0x510), 0, 250);
        // The call Break makes, then the same text through the real journal.
        string result4 = GuestBreakContext.Describe(FakeGuest(true, 0, Info, 4), 0, 250);
        result["result4"] = result4;
        EmbeddedLaunchDiagnostics.Record("guestBreak", "context", detail: result4);
        result["journal"] = Journal(journal, 0);
        result["safeUnchanged"] = EmbeddedLaunchDiagnostics.Safe(result4) == result4;
        result["bytes64"] = GuestBreakContext.Describe(FakeGuest(true, 1, Info, 0x40), 1, 250);
        result["bytes256"] = GuestBreakContext.InfoBytes(FakeGuest(true, 2, Info, 0x100), Info, 0x100).Length;
        result["tooLarge"] = GuestBreakContext.InfoBytes(FakeGuest(true, 0, Info, 0x101), Info, 0x101);
        result["zeroSize"] = GuestBreakContext.InfoBytes(FakeGuest(true, 0, Info, 0), Info, 0);
        result["unmapped"] = GuestBreakContext.InfoBytes(FakeGuest(true, 0, 0x20000000, 4), 0x20000000, 4);
        result["straddling"] = GuestBreakContext.InfoBytes(FakeGuest(true, 0, Base + (1 << 20) - 8, 16), Base + (1 << 20) - 8, 16);
        result["notification"] = GuestBreakContext.Kind(0x80000002);
        result["kinds"] = string.Join(",", new ulong[] { 0, 1, 2, 3, 4, 5, 6, 7, 8 }.Select(GuestBreakContext.Kind));
        result["noThread"] = GuestBreakContext.Describe(null, 7, 250);
        result["broken"] = GuestBreakContext.Describe(FakeGuest(false, 0, Info, 4), 0, 250);
        var frames = new System.Text.StringBuilder("Process: Fixture, PID: 81\nThread ID: 72 (MainThread)\n");
        for (int i = 0; i < 100; i++) frames.Append($"   0x{Base + (ulong)i * 4:x16}\tmain:0x{i * 4:x4}\t\n");
        string bounded = GuestBreakContext.Format(0, Info, 4, "02020000", 72, "MainThread", "\tX[00]:\t0x1\n\tPC:\t0x2\n", frames.ToString());
        result["boundedLength"] = bounded.Length;
        result["boundedFrameLines"] = bounded.Split('\n').Length;
        result["boundedEndsWithMore"] = bounded.EndsWith("(more frames not kept)");
        result["boundedKeepsX0"] = bounded.Contains("X[00]");
        result["hugeLength"] = GuestBreakContext.Format(0, 0, 0, "", 72, new string('n', 5000), "", "").Length;
        Console.WriteLine(JsonSerializer.Serialize(result));
        return 0;
    }
}
