// Doubles around the real engine code of the JIT arena preparation (test/melonx_jit_arena_usage_journal_test.py):
// DualMappedJitAllocator.cs, MemoryManagerUnixHelper.cs, DualMappedNoWxCache.cs, CacheMemoryAllocator.cs,
// TranslatedFunction.cs and EmbeddedStartupTrace.cs are compiled whole beside this file; the class DualMappedMemory
// (Translator.cs) and the arena members and neostation_melonx_prepare_jit of EmbeddedRuntime.cs replace the marks below.
// The helper and the Mach calls are the native double helper_double.c.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Numerics;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Threading;
using Ryujinx.Common;
using Ryujinx.Common.Logging;
using Ryujinx.Cpu.LightningJit.Cache;
using Ryujinx.Cpu.Signal;
using Ryujinx.Memory;

namespace Fixture
{
    public static class Helper
    {
        public static nint Handle;
        public static bool DualMappingEnabled = true;

        [DllImport("helper_double")] public static extern void helper_double_configure(long nanosecondsPerPage, int stop, int fail);
        [DllImport("helper_double")] public static extern ulong helper_double_counter(int index);

        public static ulong Traps => helper_double_counter(0);
        public static ulong Pages => helper_double_counter(1);
        public static ulong Detaches => helper_double_counter(2);
        public static double HeldMs => helper_double_counter(3) / 1000.0;
        public static ulong SizedRequests => helper_double_counter(4);
        public static ulong Aliases => helper_double_counter(5);
        public static ulong TrapsAfterDetach => helper_double_counter(6);
        public static ulong Regions => helper_double_counter(7);
    }

    public sealed record JournalEvent(double Ms, string Stage, string Status, int Code, string Detail);
}

namespace Ryujinx.Common.Logging
{
    public enum LogClass { Cpu }

    public readonly struct Log
    {
        public void Print(LogClass logClass, string message) { }
    }

    public static class Logger
    {
        public static Log? Info => null;
    }
}

namespace Ryujinx.Common
{
    public static class EmbeddedNativeLibraries
    {
        public static bool UniversalJit => true;

        // The real allocator installs this resolver for its assembly: the helper's trampolines and the Mach calls
        // ("libc") come from the native double, which also serves libc's own mmap and munmap.
        public static nint Resolve(string name, Assembly assembly, DllImportSearchPath? searchPath) =>
            name is "MeloNXJitSupport" or "libc" or "helper_double" ? Fixture.Helper.Handle : 0;
    }

    public static partial class EmbeddedLaunchDiagnostics
    {
        private static readonly object Gate = new();
        private static readonly long Origin = Stopwatch.GetTimestamp();
        public static readonly List<Fixture.JournalEvent> Events = new();
        public static string Stage { get; private set; } = "nativeAot";

        public static void Record(string stage, string status, int code = 0, string detail = "", long performanceGeneration = 0)
        {
            lock (Gate)
            {
                if (status == "begin") Stage = stage;
                Events.Add(new(Stopwatch.GetElapsedTime(Origin).TotalMilliseconds, stage, status, code, detail));
            }
        }

        public static void Fail(string stage, string code, Exception error, int status = 1)
        {
            lock (Gate)
            {
                Stage = stage;
                Events.Add(new(Stopwatch.GetElapsedTime(Origin).TotalMilliseconds, stage, "failed", status, code + ": " + error.GetType().Name + ": " + error.Message));
            }
        }

        public static Fixture.JournalEvent[] Snapshot()
        {
            lock (Gate) return Events.ToArray();
        }
    }

    public static class BitUtils
    {
        public static T AlignUp<T>(T value, T size) where T : IBinaryInteger<T> => (value + (size - T.One)) & -size;
    }
}

namespace Ryujinx.Common.Configuration
{
    public static class AppDataManager
    {
        public static string GamesDirPath { get; set; }
    }
}

namespace Ryujinx.Memory
{
    public class MemoryBlock
    {
        public static bool DualMappedEnabled() => Fixture.Helper.DualMappingEnabled;
        public static ulong GetPageSize() => 16384;
    }

    public static class HostMemoryBudget
    {
        public static ulong TotalBytes { get; set; }
    }
}

namespace Ryujinx.Cpu.Signal
{
    // What NativeSignalHandler.InitializeSignalHandler does with the helper: its code block is one dual-mapped page
    // (MapCode: new MemoryBlock(..., DualMapping)), then MemoryBlock.Detach tells the helper to detach. Once.
    static class NativeSignalHandler
    {
        private static bool _initialized;
        public static DualMappedJitAllocator CodeBlock;

        public static void InitializeSignalHandler(Func<nint, nint, nint> customSignalHandlerFactory = null)
        {
            if (_initialized) return;
            CodeBlock = new DualMappedJitAllocator(16384);
            DualMappedJitAllocator.BreakJITDetach();
            _initialized = true;
        }
    }
}

namespace Ryujinx.Cpu.LightningJit
{
    class TranslatorCache<T>
    {
        private readonly Dictionary<ulong, T> _values = new();

        public bool TryGetValue(ulong address, out T value)
        {
            lock (_values) return _values.TryGetValue(address, out value);
        }

        public T GetOrAdd(ulong address, ulong size, T value)
        {
            lock (_values)
            {
                if (_values.TryGetValue(address, out T existing)) return existing;
                _values[address] = value;
                return value;
            }
        }
    }

    class Translator
    {
        internal TranslatorCache<TranslatedFunction> Functions { get; } = new();
        internal int Registered;

        internal void RegisterFunction(ulong guestAddress, TranslatedFunction func) => Registered++;
    }

/* DUAL_MAPPED_MEMORY */
}

namespace Ryujinx.Cpu.LightningJit.Cache
{
    // The real cache invalidates the instruction cache on Apple systems only and throws elsewhere: for the files of
    // this namespace the host stands for the device (the invalidation itself is the counter below).
    static class OperatingSystem
    {
        public static bool IsMacOS() => true;
        public static bool IsIOS() => false;
    }

    static class JitSupportDarwin
    {
        public static int Invalidations;

        public static void SysIcacheInvalidate(nint start, nint len) => Interlocked.Increment(ref Invalidations);
    }
}

namespace Ryujinx.Library
{
    static class EmbeddedBootstrap
    {
        public static bool Ready = true;
    }

    static class EmbeddedSessions
    {
        public static int State;
    }

    partial class Library
    {
        internal static readonly object EmbeddedHostGate = new();
        private static bool EmbeddedJitQuarantined;
        private static ulong EmbeddedJitArenaHint;

        // The launch preflight's part in the arena: the title's hint (EmbeddedJitArenaFor).
        internal static void Preflight(ulong hint) => EmbeddedJitArenaHint = hint;
        internal static bool Quarantined => EmbeddedJitQuarantined;

/* RUNTIME_ARENA */

/* RUNTIME_PREPARE */
    }
}
