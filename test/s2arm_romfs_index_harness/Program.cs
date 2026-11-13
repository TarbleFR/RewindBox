// Runs engine patch 0014 (the RomFS index written on the device) on .NET: RomFsIndex.cs as patched, and the pieces of
// Application.cs that use it, taken verbatim from a patched S2Arm tree by test/s2arm_romfs_index_dotnet.py (nothing of
// S2Arm is kept in this repository). This file: the index written by the one walk against S2Arm's own writer and the
// directory build, staleness, layouts with links, damaged files. Written for the review of 13 Nov 2026; Extra.cs holds
// what the third version of the patch added, Perf.cs the timings on a tree of the phone's size.
//   harness.dll <empty folder>          this file
//   harness.dll extra <empty folder>    Extra.cs
//   harness.dll perf <pack folder> old|write|read|ref [reference index]
using IStorage = LibHac.Fs.IStorage;
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using S2A.Services;

static partial class T
{
    static int fails = 0, checks = 0;
    static void Check(bool ok, string what) { checks++; if (!ok) { fails++; Console.WriteLine("FAIL " + what); } else Console.WriteLine("ok   " + what); }
    static string Hash(IStorage s)
    {
        s.GetSize(out long size).ThrowIfFailure();
        using var sha = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        byte[] buf = new byte[1 << 20];
        for (long o = 0; o < size; o += buf.Length)
        {
            int n = (int)Math.Min(buf.Length, size - o);
            s.Read(o, buf.AsSpan(0, n)).ThrowIfFailure();
            sha.AppendData(buf, 0, n);
        }
        return size + ":" + Convert.ToHexString(sha.GetHashAndReset());
    }
    static void W(string path, int size, byte fill = 0x41)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(path));
        byte[] b = new byte[size]; Array.Fill(b, fill); for (int i = 0; i < size; i += 97) b[i] = (byte)(i * 31 + size);
        File.WriteAllBytes(path, b);
    }
    static string Fresh(string root, string name) { string d = Path.Combine(root, name); if (Directory.Exists(d)) Directory.Delete(d, true); Directory.CreateDirectory(d); return d; }
    static void Tree(string romfs)
    {
        W(Path.Combine(romfs, "a.bin"), 1000);
        W(Path.Combine(romfs, "zero.bin"), 0);
        W(Path.Combine(romfs, "dir1/b.bin"), 12345);
        W(Path.Combine(romfs, "dir1/sub/c with space.bin"), 77);
        W(Path.Combine(romfs, "dir1/sub/tab\there.bin"), 5);
        W(Path.Combine(romfs, "dir\twith tab/inner/x.bin"), 300);
        W(Path.Combine(romfs, "日本語/データ.bin"), 4097);
        W(Path.Combine(romfs, "dir2/.DS_Store"), 10);
        W(Path.Combine(romfs, "dir2/._junk"), 10);
        W(Path.Combine(romfs, "dir2/keep.dat"), 65536);
        W(Path.Combine(romfs, "Upper/Case.TXT"), 3);
        W(Path.Combine(romfs, "upper2/case.txt"), 3);
        Directory.CreateDirectory(Path.Combine(romfs, "empty/dir/deep"));
        W(Path.Combine(romfs, "back\\slash-name-skipped-on-purpose".Replace("\\", "_")), 9);
    }
    static void Pause() => Thread.Sleep(30);   // coarse timestamps on this kernel: let the next change get a later time

    static int Main(string[] args)
    {
        if (args[0] == "perf") return Perf.Run(args);
        if (args[0] == "extra") return Extra(args);
        string root = args[0];
        Console.WriteLine(".NET " + Environment.Version + " on " + System.Runtime.InteropServices.RuntimeInformation.OSDescription);

        // ---- A: plain tree: index written by the walk == upstream writer's enumeration index; image == directory image
        {
            string prog = Fresh(root, "A"), romfs = Path.Combine(prog, "romfs");
            Tree(romfs);
            Pause();
            string refIdx = Path.Combine(root, "A.ref.s2aidx");
            RomFsIndex.Write(romfs, refIdx);   // upstream: enumerate + open each
            string dirHash = Hash(Application.RomFsFromDirectory(romfs));
            Native.Marks.Clear(); Red.Lines.Clear();
            IStorage img = Application.HarnessRegisterRomFs(prog);
            string idx = Path.Combine(prog, "romfs.s2aidx");
            Check(File.Exists(idx) && File.ReadAllBytes(idx).AsSpan().SequenceEqual(File.ReadAllBytes(refIdx)), "A: index from the one walk is byte-identical to upstream Write(dir, out)");
            Check(Hash(img) == dirHash, "A: image through the written index == RomFsFromDirectory image (" + dirHash.Substring(0, 24) + ")");
            Check(File.Exists(idx + ".rbtree") && !File.Exists(idx + ".rblist") && !File.Exists(idx + ".tmp"), "A: stamp kept, list and tmp gone");
            Check(Native.Marks.Count == 2 && Native.Marks[0].StartsWith("RewindBox: RomFS tree walked (") && Native.Marks[1] == "RewindBox: RomFS index written for the next starts", "A: marks " + string.Join(" | ", Native.Marks));
            Console.WriteLine("--- stamp:\n" + File.ReadAllText(idx + ".rbtree").Replace("\t", "<TAB>"));
            Native.Marks.Clear();
            IStorage img2 = Application.HarnessRegisterRomFs(prog);
            Check(Native.Marks.Count == 1 && Native.Marks[0].StartsWith("RewindBox: RomFS index read ("), "A: second start reads: " + string.Join(" | ", Native.Marks));
            Check(Hash(img2) == dirHash, "A: second start image identical");
            Application.Reset2();

            // ---- B: staleness
            (string name, Action act, bool expectStale)[] mods = {
                ("add file in nested dir", () => W(Path.Combine(romfs, "dir1/sub/new.bin"), 10), true),
                ("remove file", () => File.Delete(Path.Combine(romfs, "dir1/b.bin")), true),
                ("rename file", () => File.Move(Path.Combine(romfs, "a.bin"), Path.Combine(romfs, "a2.bin")), true),
                ("replace file via temp+rename (other length)", () => { W(Path.Combine(romfs, "dir2/keep.dat.tmp"), 99); File.Move(Path.Combine(romfs, "dir2/keep.dat.tmp"), Path.Combine(romfs, "dir2/keep.dat"), true); }, true),
                ("add directory", () => Directory.CreateDirectory(Path.Combine(romfs, "empty/dir/deep/er")), true),
                ("remove empty directory", () => Directory.Delete(Path.Combine(romfs, "empty/dir/deep/er")), true),
                ("add junk .DS_Store", () => W(Path.Combine(romfs, "dir1/.DS_Store"), 4), true),
                ("rewrite in place, same length", () => { using var f = new FileStream(Path.Combine(romfs, "日本語/データ.bin"), FileMode.Open, FileAccess.Write); f.Write(new byte[10]); }, false),
                ("rewrite in place, other length (truncate+write, as cp does)", () => { using var f = new FileStream(Path.Combine(romfs, "日本語/データ.bin"), FileMode.Truncate, FileAccess.Write); f.Write(new byte[10]); }, false),
            };
            foreach (var (name, act, expectStale) in mods)
            {
                Pause(); act(); Pause();
                bool stale = RomFsIndex.RbStale(romfs, idx, out int n);
                Check(stale == expectStale, $"B: {name}: stale={stale} (expected {expectStale}), {n} directories looked at");
                Native.Marks.Clear();
                IStorage im = Application.HarnessRegisterRomFs(prog);
                if (expectStale)
                {
                    Check(Native.Marks.Count == 2 && Native.Marks[1] == "RewindBox: RomFS index written for the next starts", $"B: {name}: rewritten: " + string.Join(" | ", Native.Marks));
                    Check(Hash(im) == Hash(Application.RomFsFromDirectory(romfs)), $"B: {name}: image after rewrite == directory image");
                    Check(!RomFsIndex.RbStale(romfs, idx, out _), $"B: {name}: not stale after rewrite");
                }
                else
                {
                    string h1 = null, h2 = null; Exception ex = null;
                    try { h1 = Hash(im); } catch (Exception e) { ex = e; }
                    try { h2 = Hash(Application.RomFsFromDirectory(romfs)); } catch (Exception e) { h2 = "EXC " + e.GetType().Name; }
                    Console.WriteLine($"     {name}: index image {(ex != null ? "read FAILS: " + ex.GetType().Name + " " + ex.Message.Split('\n')[0] : (h1 == h2 ? "== directory image" : "!= directory image"))}");
                }
                Application.Reset2();
            }
        }

        // ---- C1: romfs is a relative link (chain of two) to a clean tree
        {
            string c = Fresh(root, "C1"), export = Path.Combine(c, "Exports/Game/base/romfs"), rootDir = Path.Combine(c, "game/root"), prog = Path.Combine(c, "game/pack");
            Tree(export);
            Directory.CreateDirectory(rootDir); Directory.CreateDirectory(prog);
            File.CreateSymbolicLink(Path.Combine(rootDir, "romfs"), "../../Exports/Game/base/romfs");
            File.CreateSymbolicLink(Path.Combine(prog, "romfs"), "../root/romfs");
            Pause();
            string romfs = Path.Combine(prog, "romfs"), idx = Path.Combine(prog, "romfs.s2aidx"), refIdx = Path.Combine(c, "ref.s2aidx");
            RomFsIndex.Write(romfs, refIdx);
            Native.Marks.Clear(); Red.Lines.Clear();
            IStorage img = Application.HarnessRegisterRomFs(prog);
            Check(File.Exists(idx) && File.ReadAllBytes(idx).AsSpan().SequenceEqual(File.ReadAllBytes(refIdx)), "C1: linked root (2-link relative chain): index identical to upstream writer's");
            Check(Hash(img) == Hash(Application.RomFsFromDirectory(romfs)), "C1: image identical");
            Console.WriteLine("     marks: " + string.Join(" | ", Native.Marks) + "   notes: " + string.Join(" | ", Red.Lines));
            Pause(); W(Path.Combine(export, "dir1/added.bin"), 3); Pause();
            Check(RomFsIndex.RbStale(romfs, idx, out _), "C1: change inside the link's target is seen");
            Application.Reset2();
        }

        // ---- C2: delta layout: pack/romfs -> ../root/romfs (real dirs, one relative link per file into the export)
        {
            string c = Fresh(root, "C2"), export = Path.Combine(c, "Exports/Game/base/romfs"), view = Path.Combine(c, "game/root/romfs"), prog = Path.Combine(c, "game/pack");
            Tree(export);
            Directory.CreateDirectory(prog);
            foreach (string f in Directory.EnumerateFiles(export, "*", SearchOption.AllDirectories))
            {
                string rel = Path.GetRelativePath(export, f), at = Path.Combine(view, rel);
                Directory.CreateDirectory(Path.GetDirectoryName(at));
                File.CreateSymbolicLink(at, Path.GetRelativePath(Path.GetDirectoryName(at), f));
            }
            File.CreateSymbolicLink(Path.Combine(prog, "romfs"), "../root/romfs");
            Pause();
            string romfs = Path.Combine(prog, "romfs"), idx = Path.Combine(prog, "romfs.s2aidx"), refIdx = Path.Combine(c, "ref.s2aidx");
            RomFsIndex.Write(romfs, refIdx);
            Native.Marks.Clear(); Red.Lines.Clear();
            IStorage img = Application.HarnessRegisterRomFs(prog);
            Check(File.Exists(idx) && File.ReadAllBytes(idx).AsSpan().SequenceEqual(File.ReadAllBytes(refIdx)), "C2: one link per file: index identical to upstream writer's (target lengths, not link lengths)");
            Check(Hash(img) == Hash(Application.RomFsFromDirectory(romfs)), "C2: image identical");
            Console.WriteLine("     marks: " + string.Join(" | ", Native.Marks) + "   notes: " + string.Join(" | ", Red.Lines));
            Application.Reset2();
            // a file of the export replaced (delete + create, other length): the view's directories do not move
            Pause(); File.Delete(Path.Combine(export, "dir1/b.bin")); W(Path.Combine(export, "dir1/b.bin"), 500); Pause();
            bool stale = RomFsIndex.RbStale(romfs, idx, out int n);
            Console.WriteLine($"     C2: export file replaced with another length: stale={stale} ({n} directories)");
            Native.Marks.Clear(); Red.Lines.Clear();
            IStorage im = Application.HarnessRegisterRomFs(prog);
            string r; try { r = Hash(im) == Hash(Application.RomFsFromDirectory(romfs)) ? "== directory image" : "!= directory image"; } catch (Exception e) { r = "read FAILS: " + e.GetType().Name + " " + e.Message.Split('\n')[0]; }
            Console.WriteLine("     C2: after that, start: " + string.Join(" | ", Native.Marks) + " ; reading the image: " + r + " ; red: " + string.Join(" | ", Red.Lines));
            Application.Reset2();
        }

        // ---- D: a linked directory inside the tree
        {
            string prog = Fresh(root, "D"), romfs = Path.Combine(prog, "romfs");
            Tree(romfs);
            Directory.CreateDirectory(Path.Combine(prog, "elsewhere")); W(Path.Combine(prog, "elsewhere/e.bin"), 8);
            Directory.CreateSymbolicLink(Path.Combine(romfs, "dir1/linked"), "../../elsewhere");
            Native.Marks.Clear(); Red.Lines.Clear();
            IStorage img = Application.HarnessRegisterRomFs(prog);
            string idx = Path.Combine(prog, "romfs.s2aidx");
            Check(!File.Exists(idx) && !File.Exists(idx + ".rbtree") && !File.Exists(idx + ".rblist") && !File.Exists(idx + ".tmp"), "D: linked directory: nothing left behind");
            Check(Hash(img) == Hash(Application.RomFsFromDirectory(romfs)), "D: directory image used");
            Console.WriteLine("     notes: " + string.Join(" | ", Red.Lines));
            Application.Reset2();
        }

        // ---- E: a name with a line break
        {
            string prog = Fresh(root, "E"), romfs = Path.Combine(prog, "romfs");
            Tree(romfs); W(Path.Combine(romfs, "dir1/line\nbreak.bin"), 8);
            Native.Marks.Clear(); Red.Lines.Clear();
            IStorage img = Application.HarnessRegisterRomFs(prog);
            string idx = Path.Combine(prog, "romfs.s2aidx");
            Check(!File.Exists(idx) && !File.Exists(idx + ".rbtree"), "E: line break in a name: no index");
            Console.WriteLine("     notes: " + string.Join(" | ", Red.Lines));
            Application.Reset2();
        }

        // ---- F: empty tree, and files in the root only
        foreach (string kind in new[] { "empty", "rootonly" })
        {
            string prog = Fresh(root, "F_" + kind), romfs = Path.Combine(prog, "romfs");
            Directory.CreateDirectory(romfs);
            if (kind == "rootonly") { W(Path.Combine(romfs, "one.bin"), 10); W(Path.Combine(romfs, "two.bin"), 20); }
            Pause();
            string idx = Path.Combine(prog, "romfs.s2aidx"), refIdx = Path.Combine(root, "F.ref");
            Native.Marks.Clear(); Red.Lines.Clear();
            string how;
            try
            {
                RomFsIndex.Write(romfs, refIdx);
                IStorage img = Application.HarnessRegisterRomFs(prog);
                how = (File.Exists(idx) ? (File.ReadAllBytes(idx).AsSpan().SequenceEqual(File.ReadAllBytes(refIdx)) ? "index identical to upstream" : "index DIFFERS") : "no index") + "; stamp lines " + (File.Exists(idx + ".rbtree") ? File.ReadAllLines(idx + ".rbtree").Length.ToString() : "-");
                Native.Marks.Clear();
                Application.HarnessRegisterRomFs(prog);
                how += "; second start: " + string.Join(" | ", Native.Marks);
                Pause(); W(Path.Combine(romfs, "added.bin"), 1); Pause();
                how += "; after adding a root file stale=" + RomFsIndex.RbStale(romfs, idx, out _);
            }
            catch (Exception e) { how = "EXC " + e.GetType().FullName + ": " + e.Message; }
            Console.WriteLine($"     F {kind}: {how}   notes: " + string.Join(" | ", Red.Lines));
            Application.Reset2();
        }

        // ---- G: dangling file link (before the patch: FileNotFoundException out of RomFsFromDirectory)
        {
            string prog = Fresh(root, "G"), romfs = Path.Combine(prog, "romfs");
            Tree(romfs); File.CreateSymbolicLink(Path.Combine(romfs, "dir1/dangling.bin"), "nowhere");
            Red.Lines.Clear();
            string how; try { Application.HarnessRegisterRomFs(prog); how = "no exception"; } catch (Exception e) { how = e.GetType().Name; }
            Console.WriteLine("     G dangling link: start -> " + how + " ; notes: " + string.Join(" | ", Red.Lines));
            string before; try { Application.RomFsFromDirectory(romfs); before = "no exception"; } catch (Exception e) { before = e.GetType().Name; }
            Console.WriteLine("     G dangling link: RomFsFromDirectory alone (previous flow) -> " + before);
            Application.Reset2();
        }

        // ---- I: damaged files at a later start
        {
            string prog = Fresh(root, "I"), romfs = Path.Combine(prog, "romfs"), idx = Path.Combine(prog, "romfs.s2aidx");
            Tree(romfs); Pause();
            Application.HarnessRegisterRomFs(prog); Application.Reset2();
            byte[] good = File.ReadAllBytes(idx); string stamp = File.ReadAllText(idx + ".rbtree");
            (string name, Action damage)[] cases = {
                ("stamp truncated to 10 bytes", () => File.WriteAllText(idx + ".rbtree", stamp.Substring(0, 10))),
                ("stamp zero-filled", () => File.WriteAllBytes(idx + ".rbtree", new byte[stamp.Length])),
                ("stamp empty", () => File.WriteAllBytes(idx + ".rbtree", Array.Empty<byte>())),
                ("stamp: a path line holding NUL then TAB digits", () => File.WriteAllText(idx + ".rbtree", stamp + "x\0y\t123\n")),
                ("index empty (0 bytes), stamp intact", () => File.WriteAllBytes(idx, Array.Empty<byte>())),
                ("index truncated to 100 bytes, stamp intact", () => File.WriteAllBytes(idx, good.AsSpan(0, 100).ToArray())),
                ("index truncated to half, stamp intact", () => File.WriteAllBytes(idx, good.AsSpan(0, good.Length / 2).ToArray())),
                ("index zero-filled (same length), stamp intact", () => File.WriteAllBytes(idx, new byte[good.Length])),
            };
            foreach (var (name, damage) in cases)
            {
                File.WriteAllBytes(idx, good); File.WriteAllText(idx + ".rbtree", stamp, new UTF8Encoding(false));
                damage();
                Native.Marks.Clear(); Red.Lines.Clear();
                string how;
                try { IStorage im = Application.HarnessRegisterRomFs(prog); how = "start ok: " + string.Join(" | ", Native.Marks) + (Hash(im) == Hash(Application.RomFsFromDirectory(romfs)) ? " ; image right" : " ; image WRONG"); }
                catch (Exception e) { how = "start THROWS " + e.GetType().FullName + ": " + e.Message.Split('\n')[0]; }
                string again;
                try { Native.Marks.Clear(); Application.HarnessRegisterRomFs(prog); again = "ok (" + string.Join(" | ", Native.Marks) + ")"; } catch (Exception e) { again = "THROWS again " + e.GetType().Name; }
                Console.WriteLine($"     I {name}: {how} ; next start: {again}");
                Application.Reset2();
            }
        }

        // ---- K: the tree changes while the index is written (the mark callback runs after the walk, before Write)
        {
            string prog = Fresh(root, "K"), romfs = Path.Combine(prog, "romfs"), idx = Path.Combine(prog, "romfs.s2aidx");
            Tree(romfs); Pause();
            Red.Lines.Clear();
            IStorage r = RomFsIndex.RbWriteAndOpen(romfs, idx, null, text => { Pause(); W(Path.Combine(romfs, "dir1/sub/late.bin"), 4); });
            Check(r == null && !File.Exists(idx) && !File.Exists(idx + ".rbtree") && !File.Exists(idx + ".rblist"), "K: change during the write: no index kept; notes: " + string.Join(" | ", Red.Lines));
        }

        // ---- missing-path time
        Console.WriteLine("     Directory.GetLastWriteTimeUtc(missing) = " + Directory.GetLastWriteTimeUtc(Path.Combine(root, "no/such/dir")).ToString("o") + " ticks " + Directory.GetLastWriteTimeUtc(Path.Combine(root, "no/such/dir")).Ticks);

        Console.WriteLine($"RESULT checks={checks} fails={fails}");
        return fails == 0 ? 0 : 1;
    }
}
