using System;
using System.Collections;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using System.Threading;

static class Program
{
    const BindingFlags PrivateStatic = BindingFlags.Static | BindingFlags.NonPublic;
    static int _checks;
    static bool _fixed;
    static void Check(bool value, string message)
    {
        _checks++;
        if (!value) throw new Exception(message);
    }

    static Type Pool<T>() => typeof(Ryujinx.Common.Memory.MemoryOwner<T>)
        .GetNestedType("ArrayPooling", BindingFlags.NonPublic)!.MakeGenericType(typeof(T));

    static void StopTimers(Type pool)
    {
        foreach (string name in new[] { "_arrayTimer", "_spareTimer" })
            ((Timer?)pool.GetField(name, PrivateStatic)?.GetValue(null))?.Change(Timeout.Infinite, Timeout.Infinite);
    }

    static long PoolBytes(Type pool)
    {
        long bytes = 0;
        foreach (object holder in (IEnumerable)pool.GetField("_pool", PrivateStatic)!.GetValue(null)!)
            bytes += ((Array)holder.GetType().GetField("Array")!.GetValue(holder)!).LongLength;
        return bytes;
    }

    static void Age(Type pool)
    {
        foreach (object holder in (IEnumerable)pool.GetField("_pool", PrivateStatic)!.GetValue(null)!)
            holder.GetType().GetField("Returned")!.SetValue(holder, Environment.TickCount64 - 4000);
    }

    static void Expire(Type pool)
    {
        if (_fixed) pool.GetMethod("ReleaseIdleArrays", PrivateStatic)!.Invoke(null, new object?[] { null });
        StopTimers(pool);
    }

    static (long before, long after) Retention()
    {
        var owners = new Ryujinx.Common.Memory.MemoryOwner<byte>[32];
        Type pool = Pool<byte>();
        for (int i = 0; i < owners.Length; i++) owners[i] = Ryujinx.Common.Memory.MemoryOwner<byte>.Rent(1024 * 1024 + 4096 * i);
        foreach (var owner in owners) owner.Dispose();
        StopTimers(pool);
        long before = PoolBytes(pool);
        Check(before >= 32 * 1024 * 1024, "distinct large uploads cached");
        Age(pool);
        Expire(pool);
        long after = PoolBytes(pool);
        Check(after == (_fixed ? 0 : before), "only idle primary arrays released");

        if (_fixed)
        {
            using var live = Ryujinx.Common.Memory.MemoryOwner<byte>.Rent(2 * 1024 * 1024);
            live.Span.Fill(91);
            using (var idle = Ryujinx.Common.Memory.MemoryOwner<byte>.Rent(1024 * 1024)) { }
            StopTimers(pool);
            Age(pool);
            Expire(pool);
            Check(live.Span[0] == 91 && live.Span[^1] == 91, "idle cleanup preserves leased arrays");

            // A fresh spare must survive when its older primary expires.
            var first = Ryujinx.Common.Memory.MemoryOwner<int>.Rent(262144);
            var second = Ryujinx.Common.Memory.MemoryOwner<int>.Rent(262144);
            Type ints = Pool<int>();
            first.Dispose();
            Age(ints);
            second.Dispose();
            StopTimers(ints);
            Expire(ints);
            Check(PoolBytes(ints) == 262144, "fresh spare promoted after primary expires");
            Check((long)ints.GetField("_spareBytes", PrivateStatic)!.GetValue(null)! == 0, "promoted spare not counted twice");
            Age(ints);
            Expire(ints);
            Check(PoolBytes(ints) == 0, "promoted array also expires when cold");

            // Hot reuse keeps the same lease storage and restarts the idle window.
            var a = Ryujinx.Common.Memory.MemoryOwner<short>.Rent(524288);
            a.Span[0] = 123;
            a.Dispose();
            Type shorts = Pool<short>();
            Age(shorts);
            var b = Ryujinx.Common.Memory.MemoryOwner<short>.Rent(524288);
            Check(b.Span[0] == 123, "hot array reused before timer runs");
            b.Dispose();
            StopTimers(shorts);
            Expire(shorts);
            Check(PoolBytes(shorts) == 524288, "recent return refreshes idle expiry");

            // A large mixed pool must retain every fresh entry in sorted order while removing
            // interleaved cold entries. All lengths are rented before any return, so they are distinct.
            var mixed = new Ryujinx.Common.Memory.MemoryOwner<uint>[1000];
            Type uints = Pool<uint>();
            for (int i = 0; i < mixed.Length; i++)
            {
                mixed[i] = Ryujinx.Common.Memory.MemoryOwner<uint>.Rent(256 + i * 8);
                mixed[i].Span[0] = (uint)i;
            }
            foreach (var item in mixed)
            {
                item.Dispose();
                StopTimers(uints);
            }
            var entries = (IList)uints.GetField("_pool", PrivateStatic)!.GetValue(null)!;
            Check(entries.Count == 1000, "1000 distinct primary lengths cached");
            long now = Environment.TickCount64;
            for (int i = 0; i < entries.Count; i++)
            {
                object holder = entries[i]!;
                holder.GetType().GetField("Returned")!.SetValue(holder, (i & 1) == 0 ? now - 4000 : now);
            }
            Expire(uints);
            Check(entries.Count == 500, "interleaved cold entries removed");
            for (int i = 0; i < entries.Count; i++)
            {
                object holder = entries[i]!;
                var array = (uint[])holder.GetType().GetField("Array")!.GetValue(holder)!;
                int original = i * 2 + 1;
                if (array.Length != 256 + original * 8 || array[0] != (uint)original)
                    throw new Exception("compaction changed order or live contents");
            }
            Check(true, "compaction preserves all fresh lengths and contents in sorted order");
            Age(uints);
            Expire(uints);
            Check(entries.Count == 0, "remaining interleaved arrays expire on the next pass");
        }
        return (before, after);
    }

    static (long bytes, int uploads) Snapshot()
    {
        var texture = new Texture();
        texture.Data = new byte[1024 * 1024];
        texture.SynchronizeFull();
        Check(texture.Conversions == 1, "initial conversion");
        texture.SynchronizeFull();
        Check(texture.Conversions == 1, "identical bytes skip conversion");
        long before = GC.GetAllocatedBytesForCurrentThread();
        for (int i = 1; i <= 128; i++)
        {
            texture.Data[0] = (byte)i;
            texture.SynchronizeFull();
            if (texture.LastUpload != i) throw new Exception("snapshot does not preserve changed guest bytes");
        }
        long bytes = GC.GetAllocatedBytesForCurrentThread() - before;
        Check(texture.Conversions == 129, "every changed texture converted");
        Check(_fixed ? bytes < 16384 : bytes >= 128L * 1024 * 1024, "changed snapshot allocation budget");
        texture.Data = new byte[17];
        texture.Data[0] = 201;
        texture.SynchronizeFull();
        Check(texture.LastUpload == 201, "snapshot resized with exact bytes");
        texture.Slow = false;
        texture.SynchronizeFull();
        texture.SynchronizeFull();
        Check(texture.Conversions == 132, "native texture path unchanged");
        texture.InvalidateSnapshot();
        texture.Slow = true;
        texture.Data[0] = 202;
        texture.SynchronizeFull();
        Check(texture.LastUpload == 202, "invalidated snapshot starts fresh");
        return (bytes, texture.Conversions);
    }

    static void Main(string[] args)
    {
        _fixed = args[0] == "fixed";
        var retention = Retention();
        var snapshot = Snapshot();
        Console.WriteLine(JsonSerializer.Serialize(new { mode = args[0], passed = true, checks = _checks,
            primaryRetainedBytesBefore = retention.before, primaryRetainedBytesAfterIdle = retention.after,
            changedSnapshotUploads = 128, changedSnapshotAllocatedBytes = snapshot.bytes,
            interleavedPoolLengths = _fixed ? 1000 : 0,
            physicalDeviceTested = false }));
    }
}
