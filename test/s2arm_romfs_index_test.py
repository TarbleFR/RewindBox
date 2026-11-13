#!/usr/bin/env python3
"""Patch 0014: the RomFS index of a game prepared on the phone is written at its first start, from one walk (plain python3).

Mario Kart World, engine logs of an iPhone17,2:
- IPA 733 (12 and 13 Nov): `服务：RomFS 目录表建 +69684.1 ms（本段 69232.8 ms）` at every launch. The services enumerate the
  RomFS directory (205,058 files) and open each file for its length, because the game has no romfs.s2aidx. S2Arm writes
  that index when it packs a game on a computer; RewindBox's on-device preparation does not.
- IPA 734 (13 Nov 16:15), the first version of this patch: `RewindBox: RomFS index written for the next starts
  +127361.9 ms（本段 126897.5 ms）`. It took a stamp of the tree before and after S2Arm's writer: three walks of the
  tree and every file opened.

This version walks the tree once. The walk gives each file with its length (the entry's own lstat; a link is opened
for its target's length, as S2Arm's writer does for every file) and each directory with its modification time. The
lengths go to S2Arm's own list mode (RomFsIndex.Write with a list file: the same LibHac build, no file opened again);
the directory times are the stamp. A start that finds an index reads the directories' times again, one stat each and
no walk, and drops the index when any differs: adding, removing, renaming or replacing an entry changes the time of its
directory. An index without a stamp is S2Arm's pack-time one and is trusted as before.

After the review of 13 Nov (the code was compiled and run on .NET 10 for it):
- the view of a game with an update holds one link per file, this game's case: the start that writes still opens every
  file once, as a start did before it (expected: about the 69 s of IPA 733 for that one start); the gain is at the
  starts after it;
- the stamp sees neither a file rewritten in place nor one replaced behind a link. The reader already fails such a read
  in red; an index written on the device is then dropped, so the next start writes it again from the tree as it is;
- the stamp holds the index's length and is completed only once the index is on the disk (flushed), so an index cut
  short by a stop of the device is not read; an index of ours that does not read is dropped instead of stopping every
  start; dropping removes the index first and its stamp last;
- a tree that cannot have an index here (a linked directory, a name with a line break or a backslash) is remembered,
  so later starts do not walk it to find that out again; a folder that cannot be written fails before the walk;
- a start whose managed heap limit does not hold the writer builds from the directory, as before the patch, and the
  next start tries again (the .NET GC limit is picked start by start, gclimit.c). Measured on 205,058 files with .NET
  10.0.15 on Linux: the writer runs under the smallest limit S2Arm sets (SOH 384 / LOH 256 / POH 64 MB) and down to
  SOH 96 / LOH 128 MB; the directory build runs down to LOH 64 MB, so without this fallback the patch would have
  turned a start that works into one that fails there. After the start the index keeps 29 MB of managed memory where
  the directory build keeps 112 MB.

This test reads the patch. The C# itself is compiled by s2arm-engine.yml (NativeAOT, for iOS).
With S2ARM_DOTNET_TOOLS (a folder made by build-utils/s2arm/engine/dotnet_tools.py: Roslyn and a .NET runtime taken
from NuGet, Linux x64) and S2ARM_UPSTREAM (an S2Arm checkout holding the pinned commit), it also compiles the patched
sources and runs them (test/s2arm_romfs_index_dotnet.py, the harness of test/s2arm_romfs_index_harness): 83 checks on
.NET 10.0.15 when this version was written, the index byte for byte S2Arm's writer's on small trees and on 205,058
files in both layouts, and every case above. Measured then on a tree of the phone's size, warm cache, this machine:
4.2 s for the start that writes (4.0 s for the directory build it replaces), then 27 ms to check 6,435 directories and
27 ms to open the index. Without those two variables that part is not executed, and the result says so.
What the phone takes is only known from its log (start marks `RewindBox: RomFS tree walked (N files, M directories)`,
`RewindBox: RomFS index written for the next starts`, then `RewindBox: RomFS index read (M directories checked)`).

    python3 -B test/s2arm_romfs_index_test.py
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATCHES = ROOT / 'build-utils/s2arm/engine/patches'
PATCH = PATCHES / '0014-guest-romfs-index-written-at-the-first-start.patch'
failures, checks = [], 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        failures.append(message)


def ordered(text, *parts):
    at = -1
    for part in parts:
        at = text.find(part, at + 1)
        if at < 0:
            return False
    return True


patch = PATCH.read_text(encoding='utf-8') if PATCH.is_file() else ''
check(bool(patch), 'patch 0014 exists')
check(re.findall(r'^diff --git a/(\S+) b/', patch, re.M) == ['services/S2A.Services/Application.cs', 'services/S2A.Services/RomFsIndex.cs'],
      'patch 0014 touches Application.cs and RomFsIndex.cs only')
application, index = patch.split('diff --git a/services/S2A.Services/RomFsIndex.cs')[0], patch.split('diff --git a/services/S2A.Services/RomFsIndex.cs')[-1]
added = '\n'.join(line[1:] for line in patch.splitlines() if line.startswith('+') and not line.startswith('+++'))
removed = '\n'.join(line[1:] for line in patch.splitlines() if line.startswith('-') and not line.startswith('---'))


def function(head, end):
    return index[index.find(head):index.find(end)]


# The start: an index that is to be read is read, a missing or dropped one is written, the directory build stays the fallback.
check(ordered(application, 'IStorage image = RomFsIndex.RbOpen(romfs, index, overlay, out int rbDirectories);', ' if (image != null)',
              'image = RomFsIndex.RbWriteAndOpen(romfs, index, overlay, text => Native.Mark(', 'if (image != null)', 'image = RomFsFromDirectory(romfs, overlay);',
              'device.Configuration.VirtualFileSystem.SetRomFs(pid, image);'),
      'an index is read when it is to be read, else one is written and read, else the directory build as before')
check(sorted(line.strip() for line in removed.splitlines() if line.strip()) == ['IStorage image;', 'if (File.Exists(index))', 'image = RomFsFromDirectory(romfs, overlay);', 'image = RomFsIndex.Open(romfs, index, overlay);'],
      f"of S2Arm's start only the choice between its index and its directory build is replaced: {sorted(set(line.strip() for line in removed.splitlines() if line.strip()))}")
check('$"RewindBox: RomFS index read ({rbDirectories} directories checked)\\0"' in application and 'RewindBox: RomFS index written for the next starts\\0"u8' in application
      and 'RomFS 目录表建' not in removed and 'SetRomFs' not in removed,
      "reading and writing the index have their own start mark; S2Arm's own mark of the step is not touched, so its duration is still read on the same line")
check('S2A RomFS：游戏数据里没有预建索引' in application and '-' + ' ' * 20 + 'Console.Error.WriteLine' not in patch, "S2Arm's message about the missing index is kept")
check('using System.Text;' not in application and application.count('System.Text.Encoding.UTF8.GetBytes(') == 2,
      'Application.cs has no using for System.Text: the two marks name the encoding in full')
check(ordered(application, ' Red.Report("RomFS 文件长度与索引不符（romfs.s2aidx 过期？），本次读回失败"', '+                    RomFsIndex.RbMismatch(_path);', ' opened.Dispose();',
              ' return ResultFs.HostFileDataCorrupted.Value;'),
      "a file whose length is not the index's still fails its read in red, as S2Arm has it; an index written on the device is then dropped")

# Which index is read.
opener = function('internal static IStorage RbOpen(', 'internal static void RbMismatch(')
check(ordered(opener, 'RbInUse(romfsDir, indexPath, false);', 'if (!File.Exists(indexPath))', 'return null;', 'if (!File.Exists(indexPath + RbStampSuffix))', 'return Open(romfsDir, indexPath, overlayDir);',
              'if (RbStale(romfsDir, indexPath, out directories))', 'IStorage image = Open(romfsDir, indexPath, overlayDir);', 'RbInUse(romfsDir, indexPath, true);', 'return image;',
              'catch (Exception e) when (e is InvalidDataException || e is ArgumentException || e is IOException || e is UnauthorizedAccessException)',
              'Red.Note(why, indexPath);', 'RbForget(indexPath);', 'return null;'),
      "S2Arm's pack-time index (no stamp) is opened as before, its failures its own; one written here is opened only while current, and one that does not read is dropped, "
      'said, and written again instead of stopping every start')
check(opener.count('Open(romfsDir, indexPath, overlayDir)') == 2 and opener.find('RbStale(') < opener.find('IStorage image = Open('), 'an index found stale is never opened')
mismatch = function('internal static void RbMismatch(', '        // Writes the index of romfsDir')
check(ordered(mismatch, 'internal static void RbMismatch(string path)', 'lock (_rbOpened)', 'path.StartsWith(entry.Root, StringComparison.Ordinal)', '_rbOpened.RemoveAt(at);',
              'if (index != null)', 'RbForget(index);', 'Red.Note('),
      "a length mismatch drops, once, the index of the folder the file is in, and only when that index is one written here (S2Arm's own is left as it is; so is a folder read without an index)")

# The writer: stamp pending first, one walk, lengths to S2Arm's list mode, the index flushed, then the stamp with its length.
writer = index[index.find('internal static IStorage RbWriteAndOpen('):]
walk = writer[:writer.find('dirs.Sort(StringComparer.Ordinal);')]
check(writer.count('EnumerateFileSystemInfos("*", SearchOption.AllDirectories)') == 1 and 'EnumerateFiles(' not in writer and 'EnumerateDirectories(' not in writer,
      'the tree is walked once, with the options of Directory.EnumerateFiles(all directories), which S2Arm\'s writer and the directory build use')
check(ordered(walk, 'if (OverlayFiles(overlayDir) != null || File.Exists(indexPath + RbRefusedSuffix))', 'return null;',
              'File.WriteAllText(stampPath, RbStampHead + "\\n" + RbStampPending + "\\n", utf8);', 'long rootTicks = Directory.GetLastWriteTimeUtc(root).Ticks;', 'EnumerateFileSystemInfos('),
      "no index with an overlay or for a tree already refused; the pending stamp is written before the walk (a folder that cannot be written fails there, and an index always "
      "has a stamp); the root's time is read before the walk (a change during it shows at the check)")
check(ordered(walk, 'bool link = (entry.Attributes & System.IO.FileAttributes.ReparsePoint) != 0;', 'string rel = Path.GetRelativePath(root, entry.FullName);',
              "if (Path.DirectorySeparatorChar == '\\\\')", "rel = rel.Replace('\\\\', '/');", "else if (rel.Contains('\\\\'))", 'throw new InvalidDataException(',
              'if (link && entry is System.IO.DirectoryInfo)', 'throw new InvalidDataException(',
              'if (rel.IndexOfAny(RbLineBreaks) >= 0)', 'throw new InvalidDataException(', 'if (entry is System.IO.DirectoryInfo)', 'dirs.Add(rel + "\\t" + entry.LastWriteTimeUtc.Ticks);',
              'else if (!IsHostJunk(entry.FullName))', 'if (link)', 'using FileStream content = File.OpenRead(entry.FullName);', 'size = content.Length;',
              'size = ((System.IO.FileInfo)entry).Length;', 'files.Add((rel, size));'),
      "a directory gives its time, a file its own length, a link its target's (opened, as S2Arm's writer measures every file); junk names are left out as S2Arm leaves them; "
      'a linked directory, or a name with a line break or (where it is not the separator) a backslash, means no index')
check(walk.count('File.OpenRead(') == 1 and ordered(walk, 'if (link)', 'File.OpenRead('), 'only a link is opened: a plain file costs the lstat the walk already makes')
check(ordered(writer, 'dirs.Sort(StringComparer.Ordinal);', 'new(indexPath + RbListSuffix, false, utf8)', "list.Write(size);", "list.Write('\\t');", 'list.Write(rel);', "list.Write('\\n');",
              'mark?.Invoke($"RewindBox: RomFS tree walked ({files.Count} files, {dirs.Count} directories)");', 'Write(romfsDir, indexPath, indexPath + RbListSuffix);',
              'File.Delete(indexPath + RbListSuffix);', 'using (FileStream written = new(indexPath, FileMode.Open, FileAccess.ReadWrite, FileShare.Read))', 'written.Flush(true);',
              'indexLength = written.Length;', 'stamp.Append(RbStampHead).Append("\\nindex ").Append(indexLength).Append(\'\\n\').Append(rootTicks).Append(\'\\n\');',
              'stamp.Append(dir).Append(\'\\n\');', 'using (FileStream final = new(stampPath + ".tmp", FileMode.Create, FileAccess.Write, FileShare.None))', 'final.Flush(true);',
              'File.Move(stampPath + ".tmp", stampPath, overwrite: true);', 'if (RbStale(romfsDir, indexPath, out _))', 'throw new IOException(',
              'IStorage image = Open(romfsDir, indexPath, null);', 'RbInUse(romfsDir, indexPath, true);', 'return image;'),
      "the lengths go to S2Arm's list mode as `bytes<TAB>path` lines; the index is flushed to the disk, then the stamp is completed with the index's length, flushed and renamed "
      'over the pending one; the tree must still be the stamped one after the write')
check(ordered(writer, 'catch (Exception e) when (e is IOException || e is UnauthorizedAccessException || e is InvalidDataException || e is OutOfMemoryException)', 'RbForget(indexPath);',
              'if (e is InvalidDataException)', 'File.WriteAllText(indexPath + RbRefusedSuffix, e.Message + "\\n", utf8);', 'Red.Note("RewindBox: RomFS index not written', 'return null;'),
      "a write that fails, a managed heap limit that does not hold the writer included, removes its files, says so and leaves the directory build to the caller; "
      "a refusal that is the tree's own is kept, so later starts do not walk to find it again")

# The check at a start: the stamp's index length and directories, one stat each, no walk.
stale = function('internal static bool RbStale(', 'internal static void RbForget(')
check(ordered(stale, 'directories = 0;', 'if (!File.Exists(stamp))', 'return false;', 'string root = RbRoot(romfsDir);', 'File.ReadAllLines(stamp, Encoding.UTF8)',
              'lines[0] != RbStampHead', '!lines[1].StartsWith("index ", StringComparison.Ordinal)', '!long.TryParse(lines[1].AsSpan(6), out long indexLength)',
              'new System.IO.FileInfo(indexPath).Length != indexLength', 'Directory.GetLastWriteTimeUtc(root).Ticks != rootTicks', 'return true;',
              "int tab = lines[i].LastIndexOf('\\t');", 'directories++;',
              'Directory.GetLastWriteTimeUtc(Path.Combine(root, lines[i].Substring(0, tab))).Ticks != ticks', 'return true;', 'return false;',
              'catch (Exception e) when (e is IOException || e is UnauthorizedAccessException || e is ArgumentException)', 'return true;'),
      "an index without a stamp is S2Arm's pack-time one (never stale here); otherwise the index must have the stamped length, and the root and every stamped directory the "
      'stamped time; a pending, unreadable or malformed stamp counts as stale')
check('Enumerate' not in stale and 'File.OpenRead' not in stale, 'the check walks nothing and opens no game file: one stat per stamped directory')
root = function('private static string RbRoot(', 'internal static bool RbStale(')
check(ordered(root, 'Path.GetFullPath(romfsDir)', 'Directory.ResolveLinkTarget(root, true)', 'target != null ? target.FullName : root'),
      "the tree's root is what romfs/ links to when it is a link (a link's own time does not move when its target's entries do)")
check('private const string RbStampHead = "rb-romfs-tree 2";' in index and 'private const string RbStampPending = "index -";' in index,
      'the stamp is a head line, the index\'s length (`index -` while it is written), the root\'s time, then `path<TAB>time` per directory; the head is not the first version\'s, '
      'whose stamps are therefore stale')
forget = function('internal static void RbForget(', 'internal static IStorage RbOpen(')
check(ordered(forget, 'File.Delete(indexPath);', 'File.Delete(indexPath + ".tmp");', 'File.Delete(indexPath + RbListSuffix);', 'File.Delete(indexPath + RbStampSuffix + ".tmp");',
              'File.Delete(indexPath + RbStampSuffix);') and 'RbRefusedSuffix' not in forget,
      "dropping an index removes the index first and its stamp last (an interruption never leaves an index without a stamp, which would be read as S2Arm's own); a kept refusal stays")
check(all(text in index for text in ('public const string RbStampSuffix = ".rbtree";', 'public const string RbListSuffix = ".rblist";', 'public const string RbRefusedSuffix = ".rbno";')),
      'the stamp, the list and a kept refusal sit next to the index (inside the pack folder)')
check('System.Security.Cryptography' not in added, 'no new library enters the NativeAOT link (the stamp is compared as text)')
check('public static void Write(' not in added + removed and 'class IndexedStorage' not in added + removed and 'public static IStorage Open(' not in added + removed,
      "S2Arm's index writer and reader are used as they are")
check('Native.' not in index, 'RomFsIndex.cs calls nothing of the native layer (it is also built into S2Arm\'s own index tool and tests): the mark comes in as a delegate')

# The pack folder the index is written in is removed by every new preparation of the game.
preparation = (ROOT / 'packages/s2arm_engine_bridge/ios/Classes/S2ArmGamePreparation.m').read_text(encoding='utf-8')
check(re.search(r'for \(NSString \*path in @\[ moduleDir, imagesDir, packDir \]\) \[files removeItemAtPath:path error:nil\];', preparation) is not None,
      'a new preparation deletes the pack folder, and with it an index written at an earlier start')

check(added.count('RewindBox (patch 0014)') == 3, 'the three changes are marked RewindBox (patch 0014)')
series = sorted(p.name for p in PATCHES.glob('*.patch'))
check(len(series) >= 14 and series[13] == PATCH.name, f'0014 is the 14th engine patch: {series[12:15]}')
notices = (ROOT / 'docs/s2arm-legal-notices.md').read_text(encoding='utf-8')
check(PATCH.name in notices, 'the legal notices list patch 0014')
readme = (ROOT / 'build-utils/s2arm/engine/README.md').read_text(encoding='utf-8')
check(PATCH.name in readme and '126.9 s' in readme, 'the engine README explains patch 0014 and what its first version cost')
bridge_yml = (ROOT / '.github/workflows/s2arm-bridge-ios.yml').read_text(encoding='utf-8')
check('python3 -B test/s2arm_romfs_index_test.py' in bridge_yml and 'test/s2arm_romfs_index_test.py' in bridge_yml.split('jobs:')[0],
      's2arm-bridge-ios.yml runs this test and is triggered by it')

# The patched C#, compiled and run, when a compiler and a runtime are given.
harness = ROOT / 'test/s2arm_romfs_index_harness'
check(all((harness / name).is_file() for name in ('Program.cs', 'Extra.cs', 'Perf.cs', 'Stubs.cs')) and (ROOT / 'test/s2arm_romfs_index_dotnet.py').is_file()
      and (ROOT / 'build-utils/s2arm/engine/dotnet_tools.py').is_file(), 'the harness, its runner and the tool that fetches a compiler and a runtime are in the repository')
check(not any(name in (path.name for path in harness.iterdir()) for name in ('RomFsIndex.cs', 'Application.cs', 'AppBlock.cs')),
      "nothing of S2Arm's sources is kept in the harness folder: the runner takes them from the pinned commit and the patch")
tools, upstream, dotnet = os.environ.get('S2ARM_DOTNET_TOOLS'), os.environ.get('S2ARM_UPSTREAM'), 'not executed (S2ARM_DOTNET_TOOLS and S2ARM_UPSTREAM not both set)'
if tools and upstream:
    run = subprocess.run([sys.executable, '-B', str(ROOT / 'test/s2arm_romfs_index_dotnet.py'), tools, upstream], capture_output=True, text=True, timeout=3600)
    line = run.stdout.strip().splitlines()[-1] if run.stdout.strip() else ''
    try:
        outcome = json.loads(line)
    except ValueError:
        outcome = {'result': 'failed', 'why': (run.stdout + run.stderr)[-400:]}
    check(run.returncode == 0 and outcome.get('result') == 'passed' and outcome.get('checks', 0) >= 79,
          'the patched C# compiles without a warning and its harness passes on .NET: ' + json.dumps(outcome, ensure_ascii=False)[:700])
    dotnet = outcome.get('checks', 0) if outcome.get('result') == 'passed' else 'failed'

for failure in failures:
    print('FAIL ' + failure)
print(json.dumps({'result': 'failed' if failures else 'passed', 'checks': checks, 'dotnet': dotnet}))
sys.exit(1 if failures else 0)
