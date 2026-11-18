using System.Buffers.Binary;
using System.Diagnostics;
using System.Linq.Expressions;
using System.Reflection;
using System.Security.Cryptography;
using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.Shader;
using Ryujinx.Graphics.Shader.Translation;

class CacheStages
{
    private const BindingFlags Static = BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic;
    private static readonly Type Serializer = Type.GetType("Ryujinx.Graphics.Gpu.Shader.DiskCache.ShaderBinarySerializer, Ryujinx.Graphics.Gpu", true)!;
    private static readonly Type Collection = Type.GetType("Ryujinx.Graphics.Vulkan.ShaderCollection, Ryujinx.Graphics.Vulkan", true)!;
    private static readonly Func<ShaderSource[], byte[]> Pack = Serializer.GetMethod("Pack", Static)!.CreateDelegate<Func<ShaderSource[], byte[]>>();
    public record struct Identity(ulong Stable, ulong First, ulong Second, int Stages, long Length);
#if CANDIDATE
    private delegate bool ReadStages(byte[] code, out ShaderSource[] stages);
    private static readonly ReadStages Read = Serializer.GetMethod("TryUnpack", Static)!.CreateDelegate<ReadStages>();
    private static ShaderSource[] Unpack(byte[] code) => Read(code, out var stages) ? stages : throw new InvalidDataException();
#else
    private static readonly Func<byte[], ShaderSource[]> Unpack = OldUnpack();
    private static Func<byte[], ShaderSource[]> OldUnpack()
    {
        var method = Serializer.GetMethod("Unpack", Static)!;
        var code = Expression.Parameter(typeof(byte[]));
        return Expression.Lambda<Func<byte[], ShaderSource[]>>(Expression.Call(method,
            Expression.Constant(null, method.GetParameters()[0].ParameterType), code), code).Compile();
    }
#endif

    // Call the actual private key methods of each compiled library, without a reflection allocation in the timed loop.
    private static Func<ShaderSource[], Identity> ProgramKeys()
    {
        var method = Collection.GetMethod("ComputeCodeIdentity", Static)!;
        var sources = Expression.Parameter(typeof(ShaderSource[]));
        var identity = Expression.Variable(method.ReturnType);
        var first = Expression.Property(identity, "First");
#if CANDIDATE
        Expression stable = first;
#else
        Expression stable = Expression.Call(Collection.GetMethod("ComputeStableHash", Static)!, sources);
#endif
        var make = Expression.New(typeof(Identity).GetConstructors().Single(), stable, first, Expression.Property(identity, "Second"),
            Expression.Property(identity, "Stages"), Expression.Property(identity, "Length"));
        return Expression.Lambda<Func<ShaderSource[], Identity>>(Expression.Block(new[] { identity },
            Expression.Assign(identity, Expression.Call(method, sources)), make), sources).Compile();
    }

    private static void Check(bool ok) { if (!ok) throw new Exception("Shader cache result differs"); }

    public static void Main(string[] args)
    {
        var keys = ProgramKeys();
        var vertex = File.ReadAllBytes(args[0]);
        var fragment = File.ReadAllBytes(args[1]);
        ShaderSource[] shaders = [new(vertex, ShaderStage.Vertex, TargetLanguage.Spirv),
                                  new(fragment, ShaderStage.Fragment, TargetLanguage.Spirv)];
        var packed = Pack(shaders);
        var original = keys(shaders);
        var loaded = Unpack(packed);
        Check(original.Stable == original.First && keys(loaded) == original && Pack(loaded).SequenceEqual(packed));
        var text = new ShaderSource("éclair", ShaderStage.Fragment, TargetLanguage.Glsl);
        var textIdentity = keys([text]);
        Check(text.BinaryCode == null && textIdentity.Stable == textIdentity.First);
        Check(keys([shaders[1], shaders[0]]) != original);
        var compute = new ShaderSource(File.ReadAllBytes(args[2]), ShaderStage.Compute, TargetLanguage.Spirv);
        var computeIdentity = keys([compute]);
        Check(keys(Unpack(Pack([compute]))) == computeIdentity && computeIdentity.First == computeIdentity.Stable);
#if CANDIDATE
        Check(shaders[0].BinaryCode == vertex && loaded.All(s => ReferenceEquals(s.BinarySegment.Array, packed)));
        Check(loaded.All(s => s.BinarySegment.Offset % sizeof(uint) == 0));
        byte[] badLength = (byte[])packed.Clone();
        BinaryPrimitives.WriteInt32LittleEndian(badLength.AsSpan(8), int.MaxValue);
        byte[] badStage = (byte[])packed.Clone();
        BinaryPrimitives.WriteInt32LittleEndian(badStage.AsSpan(4), -1);
        foreach (var bad in new byte[][] { [], [255,255,255,127], packed[..^1], badLength, badStage })
            Check(!Read(bad, out var stages) && stages == null);
        Check(Read(packed, out _));
#endif
        var digest = Convert.ToHexString(SHA256.HashData(packed));
        packed = null;
        GC.Collect(); GC.WaitForPendingFinalizers();
        Check(Task.Run(() => keys(loaded) == original && loaded[0].BinaryCode.SequenceEqual(vertex) &&
                             loaded[1].BinaryCode.SequenceEqual(fragment)).Result);

        // A 2-stage, 208 KiB record. These are reader/hash workloads with arbitrary bytes, never submitted as shader modules.
        var one = new byte[104 * 1024];
        var two = new byte[104 * 1024];
        new Random(777).NextBytes(one); new Random(779).NextBytes(two);
        ShaderSource[] translated = [new(one, ShaderStage.Vertex, TargetLanguage.Spirv), new(two, ShaderStage.Fragment, TargetLanguage.Spirv)];
        var record = Pack(translated);
        for (int i = 0; i < 32; i++) _ = keys(Unpack(record));
        var runs = new List<object>();
        for (int pass = 0; pass < 5; pass++)
        {
            long start = Stopwatch.GetTimestamp(), before = GC.GetAllocatedBytesForCurrentThread();
            ulong checksum = 0;
            for (int i = 0; i < 1024; i++) checksum += keys(Unpack(record)).Second;
            long allocated = GC.GetAllocatedBytesForCurrentThread() - before;
            double ms = Stopwatch.GetElapsedTime(start).TotalMilliseconds;
            long saveStart = Stopwatch.GetTimestamp(), saveBefore = GC.GetAllocatedBytesForCurrentThread();
            for (int i = 0; i < 128; i++) Check(Pack(translated).AsSpan().SequenceEqual(record));
            runs.Add(new { allocated, ms, checksum, saveAllocated = GC.GetAllocatedBytesForCurrentThread() - saveBefore,
                           saveMs = Stopwatch.GetElapsedTime(saveStart).TotalMilliseconds });
        }
        Console.WriteLine(System.Text.Json.JsonSerializer.Serialize(new { digest, original, textIdentity, computeIdentity, records = 1024, runs }));
    }
}
