using IStorage = LibHac.Fs.IStorage;
using System;
using System.Diagnostics;
using System.IO;
using S2A.Services;

static class Perf
{
    static string Mem() { var i = GC.GetGCMemoryInfo(); return $"heap now {GC.GetTotalMemory(false) >> 20} MB, committed {i.TotalCommittedBytes >> 20} MB, gen2 count {GC.CollectionCount(2)}"; }
    public static int Run(string[] a)
    {
        string prog = a[1], mode = a[2];
        string romfs = Path.Combine(prog, "romfs"), idx = Path.Combine(prog, "romfs.s2aidx");
        Stopwatch sw = Stopwatch.StartNew();
        if (mode == "old")
        {
            IStorage s = Application.RomFsFromDirectory(romfs);
            Console.WriteLine($"old RomFsFromDirectory: {sw.ElapsedMilliseconds} ms; {Mem()}");
            GC.Collect(); Console.WriteLine($"   retained after full GC: {GC.GetTotalMemory(true) >> 20} MB");
            s.GetSize(out long size); Console.WriteLine("   image size " + size);
            GC.KeepAlive(s);
        }
        else if (mode == "write")
        {
            long tWalk = 0;
            IStorage s = RomFsIndex.RbWriteAndOpen(romfs, idx, null, t => { tWalk = sw.ElapsedMilliseconds; Console.WriteLine($"   {t} at {tWalk} ms; {Mem()}"); });
            Console.WriteLine($"new RbWriteAndOpen: {sw.ElapsedMilliseconds} ms (walk {tWalk} ms, write+check+open {sw.ElapsedMilliseconds - tWalk} ms), result {(s == null ? "null" : "storage")}; {Mem()}");
            GC.Collect(); Console.WriteLine($"   retained after full GC: {GC.GetTotalMemory(true) >> 20} MB; index {new FileInfo(idx).Length >> 10} KB, stamp {new FileInfo(idx + ".rbtree").Length >> 10} KB");
            s.GetSize(out long size); Console.WriteLine("   image size " + size);
            GC.KeepAlive(s);
        }
        else if (mode == "read")
        {
            bool stale = RomFsIndex.RbStale(romfs, idx, out int n);
            long t1 = sw.ElapsedMilliseconds;
            IStorage s = RomFsIndex.Open(romfs, idx, null);
            Console.WriteLine($"new later start: RbStale={stale} ({n} directories) {t1} ms, Open {sw.ElapsedMilliseconds - t1} ms; {Mem()}");
            GC.Collect(); Console.WriteLine($"   retained after full GC: {GC.GetTotalMemory(true) >> 20} MB");
            GC.KeepAlive(s);
        }
        else if (mode == "ref")
        {
            RomFsIndex.Write(romfs, a[3]);
            Console.WriteLine($"upstream Write(dir, out): {sw.ElapsedMilliseconds} ms; {Mem()}");
            byte[] x = File.ReadAllBytes(a[3]), y = File.Exists(idx) ? File.ReadAllBytes(idx) : null;
            Console.WriteLine("   index written by the walk " + (y == null ? "absent" : x.AsSpan().SequenceEqual(y) ? "IDENTICAL to upstream's" : "DIFFERS from upstream's"));
        }
        return 0;
    }
}
