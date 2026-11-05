// Probe of the Core 667 fixes, built against the production Ryujinx.Graphics.Vulkan and Ryujinx.Graphics.Gpu of one
// variant (control: the Core 663 preparation; candidate: the final preparation; test-only InternalsVisibleTo).
// - barriers: the REAL TextureArray and ImageArray, buffer and view arrays made without a device, queue their
//   write-to-read barriers (no command buffer is reached: a buffer array returns or throws first, an empty view array
//   holds no storage).
// - mathMode: the REAL MVKInitialization.Initialize() against a test double of MoltenVK's configuration entry points
//   (StubMoltenVK.c, loaded for "libMoltenVK.dylib"); the configuration bytes it writes back are returned.
// - shaderSaves: the REAL ShaderCache.ProcessShaderCacheQueue and Dispose on an uninitialized ShaderCache whose save
//   queue, hash tables and disk-cache writer are real objects; the writer's work queue counts the shaders it receives
//   instead of writing files; the programs are test doubles whose link status the probe sets.
// - candidate only: the native Core 667 members (EmbeddedJitArenaRequest, EmbeddedNoteLaunchTitle), as delivered in
//   native/melonx/EmbeddedRuntime.cs, compiled here unchanged and run on a decision table.
using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;
using System.Threading;
using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.Gpu.Shader;
using Ryujinx.Graphics.Gpu.Shader.DiskCache;
using Ryujinx.Graphics.Vulkan;
using Ryujinx.Graphics.Vulkan.MoltenVK;
using Silk.NET.Vulkan;

#if CANDIDATE
static partial class Library
{
//__CORE667_RUNTIME__
    public static bool ArenaRequest(ulong hint, ulong mapped, ulong process, out ulong request) => EmbeddedJitArenaRequest(hint, mapped, process, out request);
    public static void NoteTitle(ulong title) => EmbeddedNoteLaunchTitle(title);
}
#endif

static unsafe class Probe
{
    static nint _stub;
    static int _queued;

    static string Throws(Action action)
    {
        try { action(); return "none"; }
        catch (Exception e) { return e.GetType().FullName; }
    }

    public static void Count<T>(T task) => Interlocked.Increment(ref _queued);

    sealed class FakeProgram : IProgram
    {
        public volatile ProgramLinkStatus Status;
        public FakeProgram(ProgramLinkStatus status) { Status = status; }
        public bool CanBindWhileIncomplete => false;
        public ProgramLinkStatus CheckProgramLink(bool blocking) => Status;
        public byte[] GetBinary() => null;
        public void Dispose() { }
    }

    static Dictionary<string, string> Barriers() => new()
    {
        ["bufferTexture"] = Throws(() => new TextureArray(null, 8, true).QueueWriteToReadBarriers(default, PipelineStageFlags.AllCommandsBit)),
        ["bufferImage"] = Throws(() => new ImageArray(null, 8, true).QueueWriteToReadBarriers(default, PipelineStageFlags.AllCommandsBit)),
        ["emptyTexture"] = Throws(() => new TextureArray(null, 8, false).QueueWriteToReadBarriers(default, PipelineStageFlags.AllCommandsBit)),
        ["emptyImage"] = Throws(() => new ImageArray(null, 8, false).QueueWriteToReadBarriers(default, PipelineStageFlags.AllCommandsBit)),
        ["bufferTextureTwice"] = Throws(() =>
        {
            var array = new TextureArray(null, 4, true);
            array.QueueWriteToReadBarriers(default, PipelineStageFlags.FragmentShaderBit);
            array.QueueWriteToReadBarriers(default, PipelineStageFlags.ComputeShaderBit);
        }),
    };

    static string Configuration(bool? precise)
    {
        ((delegate* unmanaged<void>)NativeLibrary.GetExport(_stub, "stub_reset"))();
#if CANDIDATE
        if (precise.HasValue) MVKInitialization.PreciseMath = precise.Value;
#endif
        MVKInitialization.Initialize();
        int size = Marshal.SizeOf<MVKConfiguration>();
        byte[] bytes = new byte[size];
        fixed (byte* output = bytes)
            ((delegate* unmanaged<byte*, nuint, void>)NativeLibrary.GetExport(_stub, "stub_read"))(output, (nuint)size);
        return Convert.ToHexString(bytes);
    }

    static object Field(object target, string name) =>
        target.GetType().GetField(name, BindingFlags.Instance | BindingFlags.NonPublic)?.GetValue(target);

    static Dictionary<string, object> ShaderSaves()
    {
        const BindingFlags Private = BindingFlags.Instance | BindingFlags.NonPublic;
        Type cacheType = typeof(ShaderCache);
        var cache = (ShaderCache)RuntimeHelpers.GetUninitializedObject(cacheType);
        Type saveType = cacheType.GetNestedType("ProgramToSave", BindingFlags.NonPublic);
        Type queueType = typeof(Queue<>).MakeGenericType(saveType);
        object queue = Activator.CreateInstance(queueType);
        cacheType.GetField("_programsToSaveQueue", Private).SetValue(cache, queue);
        foreach (string name in new[] { "_graphicsShaderCache", "_computeShaderCache" })
        {
            FieldInfo field = cacheType.GetField(name, Private);
            field.SetValue(cache, Activator.CreateInstance(field.FieldType, true));
        }

        var writer = (BackgroundDiskCacheWriter)RuntimeHelpers.GetUninitializedObject(typeof(BackgroundDiskCacheWriter));
        Type taskType = typeof(BackgroundDiskCacheWriter).GetNestedType("CacheFileOperationTask", BindingFlags.NonPublic);
        Delegate counter = Delegate.CreateDelegate(typeof(Action<>).MakeGenericType(taskType),
            typeof(Probe).GetMethod(nameof(Count)).MakeGenericMethod(taskType));
        object work = Activator.CreateInstance(typeof(Ryujinx.Common.AsyncWorkQueue<>).MakeGenericType(taskType), counter, "Core667Probe");
        typeof(BackgroundDiskCacheWriter).GetField("_fileWriterWorkerQueue", Private).SetValue(writer, work);
        cacheType.GetField("_cacheWriter", Private).SetValue(cache, writer);

        ConstructorInfo make = saveType.GetConstructor(new[] { typeof(CachedShaderProgram), typeof(IProgram), typeof(byte[]) });
        void Enqueue(FakeProgram program) => queueType.GetMethod("Enqueue").Invoke(queue, new[] { make.Invoke(new object[] { null, program, Array.Empty<byte>() }) });
        int Pending() => (int)queueType.GetProperty("Count").GetValue(queue);

        var held = new FakeProgram(ProgramLinkStatus.Incomplete);
        Enqueue(new FakeProgram(ProgramLinkStatus.Success));
        Enqueue(new FakeProgram(ProgramLinkStatus.Success));
        Enqueue(new FakeProgram(ProgramLinkStatus.Failure));
        Enqueue(held);
        Enqueue(new FakeProgram(ProgramLinkStatus.Success));
        cache.ProcessShaderCacheQueue();
        int pendingFirst = Pending();
        Thread.Sleep(40);
        cache.ProcessShaderCacheQueue();
        int pendingWaiting = Pending();
        held.Status = ProgramLinkStatus.Success;
        cache.ProcessShaderCacheQueue();
        int pendingReleased = Pending();
        for (int i = 0; i < 60; i++)
        {
            Enqueue(new FakeProgram(ProgramLinkStatus.Success));
        }

        cache.ProcessShaderCacheQueue();
        int pendingEnd = Pending();
        for (int i = 0; i < 400 && Volatile.Read(ref _queued) < 64; i++)
        {
            Thread.Sleep(5);
        }

        int received = Volatile.Read(ref _queued);
        cache.Dispose();
        return new Dictionary<string, object>
        {
            ["pending"] = new[] { pendingFirst, pendingWaiting, pendingReleased, pendingEnd },
            ["writerReceived"] = received,
            ["written"] = Field(cache, "_savesWritten"),
            ["failed"] = Field(cache, "_savesFailed"),
            ["queuedCounter"] = Field(cache, "_savesQueued"),
            ["longestHeadWaitMs"] = Field(cache, "_longestHeadWaitTicks") is long ticks ? ticks * 1000 / System.Diagnostics.Stopwatch.Frequency : -1,
        };
    }

    static void Main(string[] arguments)
    {
        _stub = NativeLibrary.Load(arguments[0]);
        NativeLibrary.SetDllImportResolver(typeof(MVKInitialization).Assembly,
            (name, _, _) => name == "libMoltenVK.dylib" ? _stub : IntPtr.Zero);
        if (OperatingSystem.IsLinux())
        {
            NativeLibrary.SetDllImportResolver(typeof(Ryujinx.Common.Utilities.OsUtils).Assembly,
                (name, _, _) => name == "libc" ? NativeLibrary.Load("libc.so.6") : IntPtr.Zero);
        }

        Ryujinx.Common.EmbeddedLaunchDiagnostics.Begin();
        var report = new Dictionary<string, object>
        {
            ["barriers"] = Barriers(),
            ["configurationSize"] = Marshal.SizeOf<MVKConfiguration>(),
            ["fastMathOffset"] = (int)Marshal.OffsetOf<MVKConfiguration>(nameof(MVKConfiguration.FastMathEnabled)),
            ["configurationDefault"] = Configuration(null),
        };
#if CANDIDATE
        report["configurationPrecise"] = Configuration(true);
        report["configurationFast"] = Configuration(false);
        var notes = new Dictionary<string, bool>();
        foreach ((string name, ulong title) in new[] { ("hogwarts", 0x0100F7E00C70E000UL), ("smash", 0x01006A800016E000UL), ("reset", 0UL) })
        {
            Library.NoteTitle(title);
            notes[name] = MVKInitialization.PreciseMath;
        }

        report["notedPreciseMath"] = notes;
        const ulong MiB = 1UL << 20, GiB = 1UL << 30;
        var table = new List<string>();
        foreach ((ulong hint, ulong mapped, ulong process) in new[]
        {
            (0UL, 0UL, 6655 * MiB), (0UL, 0UL, 4 * GiB), (GiB, 0UL, 4 * GiB), (GiB, 0UL, 6655 * MiB), (0UL, 0UL, 6 * GiB),
            (0UL, 512 * MiB, 6655 * MiB), (GiB, 512 * MiB, 6655 * MiB), (GiB, GiB, 6655 * MiB), (0UL, GiB, 6655 * MiB),
            (GiB, 768 * MiB, 6655 * MiB), (512 * MiB, 0UL, 6655 * MiB),
        })
        {
            bool accepted = Library.ArenaRequest(hint, mapped, process, out ulong request);
            table.Add($"{hint / MiB},{mapped / MiB},{process / MiB} -> {(accepted ? "accept" : "refuse")} {request / MiB}");
        }

        report["arenaDecisions"] = table;
#endif
        report["shaderSaves"] = ShaderSaves();
        report["journal"] = Encoding.UTF8.GetString(Ryujinx.Common.EmbeddedLaunchDiagnostics.Snapshot());
        Console.WriteLine(JsonSerializer.Serialize(report));
    }
}
