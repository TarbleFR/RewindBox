using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using System.Threading;
using Ryujinx.Graphics.Gpu;
using Ryujinx.Graphics.Gpu.Shader;
using Ryujinx.Graphics.Gpu.Shader.DiskCache;

// The production ParallelDiskCacheLoader (control: the IPA 771 preparation; candidate: with
// adapt_shader_load_binary_release) against the controlled boundaries of test/melonx_shader_loader_lifetime (copied,
// with a host cache that makes a program's host code again from its index). Two scenarios:
// - memory: 120 programs created from the host cache, each with 1 MiB of host code; at the end of the load (inside the
//   storage's LoadShaders, after every program was processed) the managed memory still reachable is measured, and the
//   loader's list is read;
// - rebuild: 8 programs from the host cache, then a corrupted-file error makes the loader rebuild the cache files; the
//   code written for each program is compared with the code the host cache holds (sha256), and the read back is checked
//   to come before the files are cleared.
static class Program
{
    private static int _checks;
    private static readonly Dictionary<string, object> Report = new();
#if CANDIDATE
    private const bool Candidate = true;
#else
    private const bool Candidate = false;
#endif

    private static void Check(bool condition, string message)
    {
        Interlocked.Increment(ref _checks);
        if (!condition) throw new Exception(message);
    }

    private static ParallelDiskCacheLoader Create(BoundaryState state, out DiskCacheHostStorage storage)
    {
        storage = new DiskCacheHostStorage(state);
        return new ParallelDiskCacheLoader(new GpuContext(state), new ShaderCacheHashTable(), new ComputeShaderCacheHashTable(), storage,
            (kind, compiled, total) => state.States.Enqueue(kind), CancellationToken.None);
    }

    private static CachedShaderProgram HostProgram(BoundaryState state, int index, bool compute)
    {
        CachedShaderStage[] shaders = new CachedShaderStage[compute ? 1 : 6];
        shaders[compute ? 0 : 1] = new CachedShaderStage(null, [(byte)index], []);
        return new CachedShaderProgram(new NativeProgram(state), new ShaderSpecializationState(), shaders);
    }

    private static byte[] Code(int index, int size)
    {
        byte[] code = new byte[size];
        for (int i = 0; i < code.Length; i++) code[i] = (byte)(index * 31 + i * 7);
        return code;
    }

    private static int ListedCodes(ParallelDiskCacheLoader loader)
    {
        object list = typeof(ParallelDiskCacheLoader).GetField("_programList", BindingFlags.Instance | BindingFlags.NonPublic).GetValue(loader);
        var values = (System.Collections.IEnumerable)list.GetType().GetProperty("Values").GetValue(list);
        int codes = 0;
        foreach (object value in values)
        {
            object code = value.GetType().GetField("Item2").GetValue(value);
            if (code != null) codes++;
        }
        return codes;
    }

    private static void Memory()
    {
        const int Programs = 120, Size = 1 << 20;
        BoundaryState state = new();
        ParallelDiskCacheLoader loader = Create(state, out DiskCacheHostStorage storage);
        storage.ProgramCount = Programs;
        long baseline = 0, retained = 0;
        int listed = -1;
        storage.OnLoad = (_, loading) =>
        {
            GC.Collect(); GC.WaitForPendingFinalizers(); GC.Collect();
            baseline = GC.GetTotalMemory(true);
            for (int index = 0; index < Programs; index++)
            {
                loading.QueueHostProgram(HostProgram(state, index, index % 2 == 0), Code(index, Size), index, index % 2 == 0);
                loading.CheckCompilation();
            }
            GC.Collect(); GC.WaitForPendingFinalizers(); GC.Collect();
            retained = GC.GetTotalMemory(true) - baseline;
            listed = ListedCodes(loading);
        };
        loader.LoadShaders();
        Check(state.ProgramChecks == Programs && storage.Additions == 0 && storage.ReadBackCalls == 0, "memory: every program loaded, no rebuild");
        Check(state.States.Last() == ShaderCacheState.Loaded, "memory: the load completes");
        Report["memoryRetainedMiB"] = Math.Round(retained / 1048576.0, 1);
        Report["memoryListedCodes"] = listed;
    }

    private static void Rebuild()
    {
        const int Programs = 8, Size = 200_000;
        BoundaryState state = new();
        ParallelDiskCacheLoader loader = Create(state, out DiskCacheHostStorage storage);
        storage.ProgramCount = Programs;
        storage.HostCode = index => Code(index, Size);
        storage.OnLoad = (_, loading) =>
        {
            for (int index = 0; index < Programs; index++)
            {
                loading.QueueHostProgram(HostProgram(state, index, index % 2 == 0), Code(index, Size), index, index % 2 == 0);
                loading.CheckCompilation();
            }
            throw new DiskCacheLoadException(DiskCacheLoadResult.FileCorruptedGeneric);
        };
        loader.LoadShaders();
        Check(storage.SharedClears == 1 && storage.HostClears == 1 && storage.Additions == Programs, "rebuild: the cache files are written again");
        var expected = Enumerable.Range(0, Programs).ToDictionary(i => i,
            i => Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(Code(i, Size))));
        Check(storage.Written.Count == Programs && expected.All(pair => storage.Written[pair.Key] == pair.Value),
            "rebuild: every program written with the host code its cache holds");
        Report["rebuildReadBackCalls"] = storage.ReadBackCalls;
        Report["rebuildReadBackPrograms"] = storage.ReadBackPrograms;
        Report["rebuildClearsBeforeReadBack"] = storage.ClearsBeforeReadBack;

        // A program whose code cannot be read back is written without host code (a rebuild of the guest entry).
        BoundaryState missingState = new();
        ParallelDiskCacheLoader missing = Create(missingState, out DiskCacheHostStorage missingStorage);
        missingStorage.HostCode = index => index == 3 ? null : Code(index, Size);
        missingStorage.OnLoad = (_, loading) =>
        {
            for (int index = 0; index < Programs; index++)
            {
                loading.QueueHostProgram(HostProgram(missingState, index, index % 2 == 0), Code(index, Size), index, index % 2 == 0);
                loading.CheckCompilation();
            }
            throw new DiskCacheLoadException(DiskCacheLoadResult.FileCorruptedGeneric);
        };
        missing.LoadShaders();
        Check(missingStorage.Additions == Programs, "rebuild with a missing code: every program written");
        Report["missingWritten"] = string.Join(",", Enumerable.Range(0, Programs).Select(i => missingStorage.Written[i] == "none" ? "none" : "code"));
    }

    public static void Main()
    {
        try
        {
            Memory();
            Rebuild();
            Console.WriteLine(JsonSerializer.Serialize(new { candidate = Candidate, checks = _checks, report = Report }));
        }
        catch (Exception error)
        {
            Console.Error.WriteLine(error);
            Environment.Exit(1);
        }
    }
}
