// GPU-side fixture of adapt_bindless_retention. Compiled with the production TextureBindingsArrayCache, the GAL threaded
// array producers, commands and ThreadedArrayPool and GAL ITextureArray.cs of the variant (control or candidate), and with
// the boundary doubles of test/melonx_array_rebuild_allocations/Program.cs (pools, textures, renderer transport, backend
// sinks; its Main is not the entry point here).
//
// What it runs:
// - scenarios: random pool writes, removals, scaling, alias destruction, forced whole rebuilds and quiet passes on
//   texture, sampler and image pool arrays (threaded and direct, 70 to 65536 elements); after every update the backend
//   element contents (textures and samplers of every sink), the synchronised and store-signalled textures and the
//   cache's recorded state are digested. The backend call stream is NOT part of the digest: the candidate drops the
//   all-null companion call by design; the calls of each kind are counted instead.
// - measure: three pool-sized (524288) threaded texture entries and one sampler entry created through
//   UpdateTextureArray, then whole rebuilds of each: the live large-object heap (GC.GetGCMemoryInfo after compacting
//   collections) before and after, the GPU-thread bytes allocated per whole rebuild, the arrays the cache and the
//   threaded pool keep, and (candidate) TextureArrayInventory against the arrays read by reflection.
// - release: RemoveAllWithPool on the pool: the entries' delta state leaves the large-object heap and the inventory.
using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Runtime;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.GAL.Multithreading.Model;
using Ryujinx.Graphics.Gpu.Engine.Types;
using Ryujinx.Graphics.Gpu.Image;
using Ryujinx.Graphics.Shader;
using PD = Ryujinx.Common.EmbeddedPerformanceDiagnostics;

static class BindlessRetentionGpu
{
#if ADAPTED
    const bool Adapted = true;
#else
    const bool Adapted = false;
#endif
    const BindingFlags Any = BindingFlags.Instance | BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic;
    const double MiB = 1024 * 1024;

    static string Hash(string value) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value)))[..16];

    static long Total(PD.Counter counter) => PD.Totals[(int)counter];

    // Backend calls of each kind made by one update (the doubles' probe marks).
    static (int Textures, int Samplers, int Images) Calls(Action update)
    {
        Probe.Begin();
        update();
        Probe.End();
        int textures = 0, samplers = 0, images = 0;
        for (int i = 0; i < Probe.Count; i++)
        {
            textures += Probe.Names[i] == "backend SetTextures" ? 1 : 0;
            samplers += Probe.Names[i] == "backend SetSamplers" ? 1 : 0;
            images += Probe.Names[i] == "backend SetImages" ? 1 : 0;
        }
        return (textures, samplers, images);
    }

    static object Scenario(bool threaded, Kind kind, bool store, bool resScale, int length, int format, int seed, int steps)
    {
        World w = new(length, threaded, seed);
        TextureUsageFlags flags = (store ? TextureUsageFlags.ImageStore : 0) | (resScale ? TextureUsageFlags.ResScaleUnsupported : 0);
        TextureBindingInfo binding = World.Binding(length, kind, flags, format);
        List<string> digests = new();
        long full0 = Total(PD.Counter.ArrayFullElements);
        int textureCalls = 0, samplerCalls = 0, imageCalls = 0, fullRebuilds = 0;
        for (int step = 0; step < steps; step++)
        {
            if (step != 0) w.Mutate(1 + w.Random.Next(step % 4 == 0 ? 0 : 6));
            if (step % 7 == 3) w.ForceRebuild(binding, kind, w.Random.Next(length));
            foreach (Texture t in w.All) t.ResetStep();
            long before = Total(PD.Counter.ArrayFullElements);
            (int Textures, int Samplers, int Images) calls = Calls(() => w.Update(binding, kind));
            bool full = Total(PD.Counter.ArrayFullElements) != before;
            fullRebuilds += full ? 1 : 0;
            // Only whole rebuilds send the companion array; delta runs send the array's own kind in both variants.
            if (full)
            {
                textureCalls += calls.Textures; samplerCalls += calls.Samplers; imageCalls += calls.Images;
            }
            Check.That(w.Violations == 0, "a call reached a disposed texture");
            string synced = string.Join(",", w.All.Where(t => t.StepSynced).Select(t => t.SignalName).OrderBy(n => n, StringComparer.Ordinal));
            string signaled = string.Join(",", w.All.Where(t => t.StepSignaled).Select(t => t.SignalName).OrderBy(n => n, StringComparer.Ordinal));
            digests.Add(Hash(w.Contents() + "#" + synced + "#" + signaled + "#" + w.CacheState()));
        }
        w.Threaded?.Dispose();
        return new
        {
            threaded, kind = kind.ToString(), store, resScale, length, format, seed, steps, fullRebuilds,
            fullElements = Total(PD.Counter.ArrayFullElements) - full0,
            wholeRebuildCalls = new { textures = textureCalls, samplers = samplerCalls, images = imageCalls },
            digest = Hash(string.Join(";", digests)),
        };
    }

    static long LiveLoh()
    {
        for (int i = 0; i < 2; i++)
        {
            GCSettings.LargeObjectHeapCompactionMode = GCLargeObjectHeapCompactionMode.CompactOnce;
            GC.Collect(2, GCCollectionMode.Forced, blocking: true, compacting: true);
            GC.WaitForPendingFinalizers();
        }
        GCGenerationInfo loh = GC.GetGCMemoryInfo(GCKind.FullBlocking).GenerationInfo[3];
        return loh.SizeAfterBytes - loh.FragmentationAfterBytes;
    }

    // Arrays of 85000 bytes or more the cache and the threaded pool keep between updates, by element type.
    static Dictionary<string, long> Kept(TextureBindingsArrayCache cache)
    {
        Dictionary<string, long> kept = new() { ["ITexture"] = 0, ["ISampler"] = 0 };
        void Inspect(object value)
        {
            if (value is not Array[] arrays) return;
            foreach (Array array in arrays)
            {
                if (array == null || (long)array.Length * IntPtr.Size < 85000) continue;
                kept[array.GetType().GetElementType().Name] += (long)array.Length * IntPtr.Size;
            }
        }
        foreach (FieldInfo field in typeof(TextureBindingsArrayCache).GetFields(Any))
            if (field.FieldType.IsArray && field.FieldType.GetElementType().IsArray) Inspect(field.GetValue(cache));
        foreach (Type type in new[] { typeof(ThreadedArrayPool<ITexture>), typeof(ThreadedArrayPool<ISampler>) })
            foreach (FieldInfo field in type.GetFields(Any))
                if (field.FieldType.IsArray && field.FieldType.GetElementType().IsArray) Inspect(field.GetValue(null));
        return kept;
    }

    // The per-element delta arrays of every pool entry, read by reflection.
    static long DeltaBytes(TextureBindingsArrayCache cache, out int entries)
    {
        long bytes = 0;
        entries = 0;
        foreach (object pair in (IEnumerable)typeof(TextureBindingsArrayCache).GetField("_cacheFromPool", Any).GetValue(cache))
        {
            object entry = pair.GetType().GetProperty("Value").GetValue(pair);
            entries++;
            foreach (string name in new[] { "DeltaItems", "DeltaTextures", "DeltaHosts", "DeltaSamplers", "DeltaHostSamplers", "DeltaSequences" })
                if (entry.GetType().GetField(name, Any).GetValue(entry) is Array values)
                    bytes += (long)values.Length * (values is int[] ? sizeof(int) : IntPtr.Size);
        }
        return bytes;
    }

    static long Inventory(string name) =>
        Type.GetType("Ryujinx.Graphics.GAL.TextureArrayInventory") is Type type ? (long)type.GetField(name, Any).GetValue(null) : -1;

    // The first entry (Texture2D) last updated the given time ago, and the next update publishes the idle entries. In its
    // own frame: no reference to the entry outlives the call.
    [System.Runtime.CompilerServices.MethodImpl(System.Runtime.CompilerServices.MethodImplOptions.NoInlining)]
    static void AgeFirstEntry(TextureBindingsArrayCache cache, long milliseconds)
    {
        object pool = typeof(TextureBindingsArrayCache).GetField("_cacheFromPool", Any).GetValue(cache);
        object first = null;
        foreach (object pair in (IEnumerable)pool) { first = pair.GetType().GetProperty("Value").GetValue(pair); break; }
        FieldInfo lastUse = first.GetType().GetField("LastUse", Any);
        lastUse.SetValue(first, (long)lastUse.GetValue(first) - milliseconds);
        typeof(TextureBindingsArrayCache).GetField("_inventoryPublished", Any).SetValue(cache, 0L);
    }

    static readonly Target[] Targets = { Target.Texture2D, Target.Texture2DArray, Target.Cubemap };

    static object Measure()
    {
        const int Length = 524288;
        // The inventory is process-wide: the scenarios' caches above still hold their entries; deltas are compared.
        long entries0 = Inventory("PoolEntries"), bytes0 = Inventory("PoolEntryBytes"), idle0 = Inventory("PoolEntriesIdle");
        long loh0 = LiveLoh();
        World w = new(Length, true, 3, librarySize: 4096);
        long lohWorld = LiveLoh();
        TextureBindingInfo[] bindings = Targets.Select(t => World.Binding(Length, Kind.Texture, 0, 0, t)).ToArray();
        TextureBindingInfo samplerBinding = World.Binding(4096, Kind.Sampler);
        long full0 = Total(PD.Counter.ArrayFullElements);
        long allocated0 = GC.GetAllocatedBytesForCurrentThread();
        foreach (TextureBindingInfo binding in bindings) w.Update(binding, Kind.Texture);
        w.Update(samplerBinding, Kind.Sampler);
        long createdBytes = GC.GetAllocatedBytesForCurrentThread() - allocated0;
        Check.That(Total(PD.Counter.ArrayFullElements) - full0 == 3L * Length + 4096, "three pool-sized texture entries and one sampler entry, as on the device");
        long lohCreated = LiveLoh();
        Dictionary<string, long> keptCreated = Kept(w.Cache);

        // Whole rebuilds of the existing entries (as the device's 58 per session): the steady retention and allocation.
        const int Rounds = 4;
        long rebuildBytes = 0;
        for (int round = 0; round < Rounds; round++)
        {
            for (int a = 0; a < bindings.Length; a++)
            {
                w.ForceRebuild(bindings[a], Kind.Texture, (round * 7919 + a * 104729) % Length);
                long before = GC.GetAllocatedBytesForCurrentThread();
                long fullBefore = Total(PD.Counter.ArrayFullElements);
                w.Update(bindings[a], Kind.Texture);
                Check.That(Total(PD.Counter.ArrayFullElements) - fullBefore == Length, "a forced whole rebuild");
                if (round > 0) rebuildBytes += GC.GetAllocatedBytesForCurrentThread() - before;
            }
        }
        long lohRebuilt = LiveLoh();
        Dictionary<string, long> keptRebuilt = Kept(w.Cache);
        long delta = DeltaBytes(w.Cache, out int entries);
        long sinks = 0;
        foreach (TextureSink sink in w.Threaded.TextureSinks) sinks += ((long)sink.Textures.Length + sink.Samplers.Length) * IntPtr.Size;

        // Inventory (candidate): what the GPU caches report against the arrays themselves; an idle entry; then the release.
        object inventory = null;
        if (Adapted)
        {
            Check.That(Inventory("PoolEntries") - entries0 == entries && entries == 4, "inventory counts the pool entries");
            Check.That(Inventory("PoolEntryBytes") - bytes0 == delta, "inventory bytes are the entries' delta arrays");
            Check.That(Inventory("PoolEntriesIdle") - idle0 == 0, "no entry idle yet");
            AgeFirstEntry(w.Cache, 31000);
            w.Update(samplerBinding, Kind.Sampler);
            long idle = Inventory("PoolEntriesIdle") - idle0;
            Check.That(idle == 1, "an entry not updated for 30 s is reported idle");
            inventory = new { entries = Inventory("PoolEntries") - entries0, idle, bytes = Inventory("PoolEntryBytes") - bytes0 };
        }

        w.Cache.RemoveAllWithPool(w.Textures);
        w.Cache.RemoveAllWithPool(w.Samplers);
        w.Threaded.Drain();
        DeltaBytes(w.Cache, out int left);
        Check.That(left == 0, "the pool entries are removed with their pools");
        long lohReleased = LiveLoh();
        if (Adapted)
        {
            Check.That(Inventory("PoolEntries") == entries0 && Inventory("PoolEntryBytes") == bytes0 && Inventory("PoolEntriesIdle") == idle0,
                       "removed entries leave the inventory");
        }
        object result = new
        {
            length = Length, textureEntries = bindings.Length, samplerEntryLength = 4096,
            lohBaselineBytes = loh0, lohWorldBytes = lohWorld - loh0,
            lohEntriesCreatedBytes = lohCreated - lohWorld, lohAfterRebuildsBytes = lohRebuilt - lohWorld,
            lohAfterReleaseBytes = lohReleased - lohWorld,
            deltaStateBytes = delta, backendSinkDoubleBytes = sinks,
            keptAfterCreation = keptCreated, keptAfterRebuilds = keptRebuilt,
            creationAllocatedBytes = createdBytes, wholeRebuildAllocatedBytes = rebuildBytes / ((Rounds - 1) * bindings.Length),
            inventory,
        };
        GC.KeepAlive(w);
        return result;
    }

    static void Main()
    {
        // First, in a fresh process: the threaded pool's kept arrays are process-wide.
        object measure = Measure();
        List<object> scenarios = new();
        foreach (bool threaded in new[] { true, false })
            foreach (Kind kind in new[] { Kind.Texture, Kind.Sampler, Kind.Image })
                foreach (int length in new[] { 70, 5000, 65536 })
                    for (int seed = 1; seed <= 2; seed++)
                    {
                        bool store = kind == Kind.Image && seed == 1;
                        bool resScale = kind != Kind.Sampler && seed == 2;
                        int format = kind != Kind.Sampler && seed == 2 ? 2 : 0;
                        scenarios.Add(Scenario(threaded, kind, store, resScale, length, format, seed * 37 + length, length > 5000 ? 10 : 24));
                    }
        Console.WriteLine(JsonSerializer.Serialize(new
        {
            adapted = Adapted, checks = Check.Count, scenarios, measure,
            gcSettings = new { conserveMemory = AppContext.GetData("System.GC.ConserveMemory")?.ToString(), server = GCSettings.IsServerGC },
        }));
    }
}
