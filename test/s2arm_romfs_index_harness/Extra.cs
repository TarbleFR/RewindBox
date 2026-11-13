using IStorage = LibHac.Fs.IStorage;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using S2A.Services;

// What the third version of patch 0014 adds, after the review of 13 Nov (run: harness.dll extra <folder>)
static partial class T
{
    static string Marks() => string.Join(" | ", Native.Marks);
    static string Notes() => string.Join(" | ", Red.Lines);
    static IStorage Start(string prog) { Native.Marks.Clear(); Red.Lines.Clear(); return Application.HarnessRegisterRomFs(prog); }
    static string Try(Func<string> f) { try { return f(); } catch (Exception e) { return "EXC " + e.GetType().Name; } }
    static void DeltaView(string export, string view)
    {
        foreach (string f in Directory.EnumerateFiles(export, "*", SearchOption.AllDirectories))
        {
            string rel = Path.GetRelativePath(export, f), at = Path.Combine(view, rel);
            Directory.CreateDirectory(Path.GetDirectoryName(at));
            File.CreateSymbolicLink(at, Path.GetRelativePath(Path.GetDirectoryName(at), f));
        }
    }

    static int Extra(string[] args)
    {
        string root = args[1];

        // ---- M1: a file replaced behind a link (the view of a game with an update): this start's read fails, the index is dropped, the next start is right
        {
            string c = Fresh(root, "M1"), export = Path.Combine(c, "Exports/Game/base/romfs"), view = Path.Combine(c, "game/root/romfs"), prog = Path.Combine(c, "game/pack");
            Tree(export); Directory.CreateDirectory(prog); DeltaView(export, view);
            File.CreateSymbolicLink(Path.Combine(prog, "romfs"), "../root/romfs");
            string romfs = Path.Combine(prog, "romfs"), idx = Path.Combine(prog, "romfs.s2aidx");
            Pause(); Start(prog); Application.Reset2();
            Check(File.Exists(idx) && File.Exists(idx + ".rbtree"), "M1: index and stamp written");
            Pause(); File.Delete(Path.Combine(export, "dir1/b.bin")); W(Path.Combine(export, "dir1/b.bin"), 500); Pause();
            Check(!RomFsIndex.RbStale(romfs, idx, out _), "M1: the stamp does not see a file replaced in the export (its directories are the view's)");
            IStorage im = Start(prog);
            Check(Marks().StartsWith("RewindBox: RomFS index read ("), "M1: that start reads the index: " + Marks());
            string read = Try(() => Hash(im));
            Check(read == "EXC HorizonResultException", "M1: the read of the image fails at the replaced file, as for any index: " + read);
            Check(Red.Lines.Any(l => l.StartsWith("RED RomFS 文件长度与索引不符")) && Red.Lines.Count(l => l.Contains("the index written on this device is dropped")) == 1, "M1: S2Arm's red line, then the note that the index is dropped, once: " + Red.Lines.Count + " lines");
            Check(!File.Exists(idx) && !File.Exists(idx + ".rbtree"), "M1: index and stamp are gone");
            string again = Try(() => Hash(im));   // a second failing read in the same session: nothing more to drop, no second note
            Check(again == "EXC HorizonResultException" && Red.Lines.Count(l => l.Contains("is dropped")) == 1, "M1: later failing reads of that session note nothing more");
            Application.Reset2();
            IStorage next = Start(prog);
            Check(Marks().EndsWith("RewindBox: RomFS index written for the next starts") && Hash(next) == Hash(Application.RomFsFromDirectory(romfs)), "M1: the next start writes the index again and the image is the directory's: " + Marks());
            Application.Reset2();
        }

        // ---- M2: a file rewritten in place with another length (plain tree): the same
        {
            string prog = Fresh(root, "M2"), romfs = Path.Combine(prog, "romfs"), idx = Path.Combine(prog, "romfs.s2aidx");
            Tree(romfs); Pause(); Start(prog); Application.Reset2();
            Pause(); using (var f = new FileStream(Path.Combine(romfs, "dir2/keep.dat"), FileMode.Truncate, FileAccess.Write)) f.Write(new byte[10]); Pause();
            IStorage im = Start(prog);
            Check(Try(() => Hash(im)) == "EXC HorizonResultException" && !File.Exists(idx) && !File.Exists(idx + ".rbtree"), "M2: rewritten in place: the read fails and the index is dropped");
            Application.Reset2();
            IStorage next = Start(prog);
            Check(Hash(next) == Hash(Application.RomFsFromDirectory(romfs)) && File.Exists(idx), "M2: the next start is right again: " + Marks());
            Application.Reset2();
        }

        // ---- M3: S2Arm's own index (no stamp) is opened as before and never dropped
        {
            string prog = Fresh(root, "M3"), romfs = Path.Combine(prog, "romfs"), idx = Path.Combine(prog, "romfs.s2aidx");
            Tree(romfs); Pause(); RomFsIndex.Write(romfs, idx);
            IStorage im = Start(prog);
            Check(Marks() == "RewindBox: RomFS index read (0 directories checked)" && !File.Exists(idx + ".rbtree") && Hash(im) == Hash(Application.RomFsFromDirectory(romfs)), "M3: pack-time index read, no stamp made: " + Marks());
            Application.Reset2();
            using (var f = new FileStream(Path.Combine(romfs, "dir2/keep.dat"), FileMode.Truncate, FileAccess.Write)) f.Write(new byte[10]);
            IStorage im2 = Start(prog);
            Check(Try(() => Hash(im2)) == "EXC HorizonResultException" && File.Exists(idx) && !Red.Lines.Any(l => l.Contains("is dropped")), "M3: a mismatch fails the read as before and leaves S2Arm's index in place");
            Application.Reset2();
            File.WriteAllBytes(idx, new byte[40]);   // a damaged pack-time index: S2Arm's own failure, not caught here
            Check(Try(() => { Start(prog); return "no exception"; }) == "EXC InvalidDataException" && File.Exists(idx), "M3: a damaged pack-time index still throws, as before, and stays");
        }

        // ---- M4: a refusal that is the tree's own is kept: the next start does not walk
        foreach ((string kind, Action<string, string> make) in new (string, Action<string, string>)[] {
            ("linked directory", (prog, romfs) => { Directory.CreateDirectory(Path.Combine(prog, "elsewhere")); W(Path.Combine(prog, "elsewhere/e.bin"), 8); Directory.CreateSymbolicLink(Path.Combine(romfs, "dir1/linked"), "../../elsewhere"); }),
            ("line break in a name", (prog, romfs) => W(Path.Combine(romfs, "dir1/line\nbreak.bin"), 8)),
            ("backslash in a file name", (prog, romfs) => W(Path.Combine(romfs, "dir1/we\\ird.bin"), 8)),
            ("backslash in a directory name", (prog, romfs) => W(Path.Combine(romfs, "we\\ird/x.bin"), 8)),
        })
        {
            string prog = Fresh(root, "M4"), romfs = Path.Combine(prog, "romfs"), idx = Path.Combine(prog, "romfs.s2aidx");
            Tree(romfs); make(prog, romfs); Pause();
            IStorage im = Start(prog);
            string dir = Hash(Application.RomFsFromDirectory(romfs));
            Check(Hash(im) == dir && !File.Exists(idx) && !File.Exists(idx + ".rbtree") && !File.Exists(idx + ".rblist") && File.Exists(idx + ".rbno") && Marks() == "", $"M4 {kind}: directory image, no index, the refusal kept: " + Notes());
            Application.Reset2();
            IStorage im2 = Start(prog);
            Check(Hash(im2) == dir && Marks() == "" && Red.Lines.Count == 0 && !File.Exists(idx + ".rbtree"), $"M4 {kind}: the next start builds from the directory at once (no walk, no note)");
            Application.Reset2();
        }

        // ---- M5: a folder that cannot be written fails before the walk
        {
            string prog = Fresh(root, "M5"), romfs = Path.Combine(prog, "romfs"), idx = Path.Combine(prog, "romfs.s2aidx");
            Tree(romfs); Directory.CreateDirectory(idx + ".rbtree");   // the stamp cannot be created (this harness runs as root: a mode would not stop it)
            bool walked = false; Red.Lines.Clear();
            IStorage r = RomFsIndex.RbWriteAndOpen(romfs, idx, null, _ => walked = true);
            Check(r == null && !walked && !File.Exists(idx) && !File.Exists(idx + ".rbno"), "M5: no stamp can be written: null before any walk, nothing kept: " + Notes());
            Directory.Delete(idx + ".rbtree");
        }

        // ---- M6: the device stops while the index is written: a pending stamp never passes
        {
            string prog = Fresh(root, "M6"), romfs = Path.Combine(prog, "romfs"), idx = Path.Combine(prog, "romfs.s2aidx");
            Tree(romfs); Pause(); Start(prog); Application.Reset2();
            byte[] good = File.ReadAllBytes(idx); string final = File.ReadAllText(idx + ".rbtree");
            string[] lines = final.Split('\n');
            Check(lines[0] == "rb-romfs-tree 2" && lines[1] == "index " + good.Length, "M6: the stamp holds the index's length: " + lines[1]);
            File.WriteAllText(idx + ".rbtree", "rb-romfs-tree 2\nindex -\n");   // as left by a stop after the index was renamed in, before the final stamp
            Check(RomFsIndex.RbStale(romfs, idx, out _), "M6: index present with a pending stamp: not current");
            IStorage im = Start(prog);
            Check(Marks().EndsWith("RewindBox: RomFS index written for the next starts") && Hash(im) == Hash(Application.RomFsFromDirectory(romfs)), "M6: written again: " + Marks());
            Application.Reset2();
            File.WriteAllText(idx + ".rbtree", final.Replace("index " + good.Length, "index " + (good.Length + 1)));
            Check(RomFsIndex.RbStale(romfs, idx, out _), "M6: an index one byte shorter than its stamp says: not current");
            File.WriteAllText(idx + ".rbtree", final.Replace("rb-romfs-tree 2", "rb-romfs-tree 1"));
            Check(RomFsIndex.RbStale(romfs, idx, out _), "M6: the stamp of the first version of this patch: not current");
            File.WriteAllText(idx + ".rbtree", final);
            Check(!RomFsIndex.RbStale(romfs, idx, out int n) && n == 11, "M6: the final stamp again: current");
            File.Delete(idx);
            Check(RomFsIndex.RbStale(romfs, idx, out _), "M6: a stamp without its index: not current (no exception)");
            Start(prog); Application.Reset2();
        }

        // ---- M7: dropping an index: the index goes first, its stamp last
        {
            string prog = Fresh(root, "M7"), romfs = Path.Combine(prog, "romfs"), idx = Path.Combine(prog, "romfs.s2aidx");
            Tree(romfs); Pause(); Start(prog); Application.Reset2();
            File.Delete(idx); Directory.CreateDirectory(idx);   // an index that cannot be deleted (File.Delete of a directory fails)
            RomFsIndex.RbForget(idx);
            Check(File.Exists(idx + ".rbtree"), "M7: the index could not be deleted: its stamp stays, so the next start finds it stale again");
            Directory.Delete(idx);
            RomFsIndex.RbForget(idx);
            Check(!File.Exists(idx + ".rbtree"), "M7: with the index gone the stamp goes");
        }

        // ---- M8: two folders with an index each (a title with several programs): a mismatch drops the index of the folder the file is in
        {
            string a = Fresh(root, "M8a"), b = Fresh(root, "M8b"), romfsA = Path.Combine(a, "romfs"), romfsB = Path.Combine(b, "romfs");
            string idxA = Path.Combine(a, "romfs.s2aidx"), idxB = Path.Combine(b, "romfs.s2aidx");
            Tree(romfsA); Tree(romfsB); Pause();
            Start(a); Start(b); Application.Reset2();
            using (var f = new FileStream(Path.Combine(romfsA, "dir2/keep.dat"), FileMode.Truncate, FileAccess.Write)) f.Write(new byte[10]);
            IStorage imA = Start(a); IStorage imB = Start(b);   // B is opened last
            Check(Try(() => Hash(imA)) == "EXC HorizonResultException" && !File.Exists(idxA) && File.Exists(idxB) && File.Exists(idxB + ".rbtree"),
                "M8: the mismatch is in the first folder: its index is dropped, the other folder's stays");
            Check(Hash(imB) == Hash(Application.RomFsFromDirectory(romfsB)), "M8: the other folder still reads through its index");
            Application.Reset2();
            IStorage plain = Application.RomFsFromDirectory(romfsA);   // no index in use for this folder now
            using (var f = new FileStream(Path.Combine(romfsA, "a.bin"), FileMode.Truncate, FileAccess.Write)) f.Write(new byte[3]);
            Red.Lines.Clear();
            Check(Try(() => Hash(plain)) == "EXC HorizonResultException" && !Red.Lines.Any(l => l.Contains("is dropped")) && File.Exists(idxB), "M8: a folder read without an index: the read fails as before, nothing is dropped");
            Application.Reset2();
        }

        // ---- M9: the managed heap's limit does not hold the writer (thrown here from the walk's mark, which runs inside the writer): nothing is left,
        //      no refusal is kept, the start builds from the directory and the next start writes the index
        {
            string prog = Fresh(root, "M9"), romfs = Path.Combine(prog, "romfs"), idx = Path.Combine(prog, "romfs.s2aidx");
            Tree(romfs); Pause(); Red.Lines.Clear();
            IStorage none = RomFsIndex.RbWriteAndOpen(romfs, idx, null, _ => throw new OutOfMemoryException("limit"));
            Check(none == null && Directory.GetFiles(prog).Length == 0, "M9: out of managed memory in the writer: null, and no file of its own is left: " + string.Join(" ", Directory.GetFiles(prog).Select(Path.GetFileName)));
            Check(Red.Lines.Count(l => l.Contains("RomFS index not written, the image is built from the directory at this start") && l.Contains("OutOfMemoryException")) == 1, "M9: it says so in red, once: " + Notes());
            IStorage im = Start(prog);
            Check(Marks().EndsWith("RewindBox: RomFS index written for the next starts") && File.Exists(idx) && Hash(im) == Hash(Application.RomFsFromDirectory(romfs)), "M9: the next start writes the index: " + Marks());
            Application.Reset2();
            string other = Try(() => { RomFsIndex.RbWriteAndOpen(romfs, idx, null, _ => throw new InvalidOperationException("not the writer's")); return "no exception"; });
            Check(other == "EXC InvalidOperationException", "M9: an error the writer does not know is not taken for one of its own: " + other);
            Application.Reset2();
        }

        Console.WriteLine($"RESULT checks={checks} fails={fails}");
        return fails == 0 ? 0 : 1;
    }
}
