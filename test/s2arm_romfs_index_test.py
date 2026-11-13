#!/usr/bin/env python3
"""Patch 0014: the RomFS index of a game prepared on the phone is written at its first start, from one walk (plain python3).

Mario Kart World, engine logs of an iPhone17,2:
- IPA 733 (12 and 13 Nov): `服务：RomFS 目录表建 +69684.1 ms（本段 69232.8 ms）` at every launch. The services enumerate the
  RomFS directory (205,058 files) and open each file for its length, because the game has no romfs.s2aidx. S2Arm writes
  that index when it packs a game on a computer; RewindBox's on-device preparation does not.
- IPA 734 (13 Nov 16:15), the first version of this patch: `RewindBox: RomFS index written for the next starts
  +127361.9 ms（本段 126897.5 ms）`. It took a stamp of the tree before and after S2Arm's writer: three walks of the
  tree and every file opened. The preparation journal of the same phone gives the price of one cold walk: 29.4 s
  (`nro walk`, 12 Nov), 0.3 s when the directories are cached.

This version walks the tree once. The walk gives each file with its length (the entry's own lstat; a link is opened
for its target's length, as S2Arm's writer does for every file) and each directory with its modification time. The
lengths go to S2Arm's own list mode (RomFsIndex.Write with a list file: the same LibHac build, no file opened); the
directory times are the stamp. A start that finds an index reads the directories' times again, one stat each and no
walk, and drops the index when any differs: adding, removing, renaming or replacing an entry changes the time of its
directory. An index without a stamp is S2Arm's pack-time one and is trusted as before.

The C# is compiled by s2arm-engine.yml only (no .NET SDK here, and no run of it there): this test reads the patch.
How long the start that writes takes with this version, and a start that reads, is only known from a device log (start
marks `RewindBox: RomFS tree walked (N files, M directories)`, `RewindBox: RomFS index written for the next starts`,
then `RewindBox: RomFS index read (M directories checked)`).

    python3 -B test/s2arm_romfs_index_test.py
"""
import json
import re
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

# The start: a stale index of ours is dropped, an index is read, a missing one is written, the directory build stays the fallback.
check(ordered(application, 'if (File.Exists(index) && RomFsIndex.RbStale(romfs, index, out rbDirectories))', 'RomFsIndex.RbForget(index);',
              ' if (File.Exists(index))', 'image = RomFsIndex.Open(romfs, index, overlay);', 'image = RomFsIndex.RbWriteAndOpen(romfs, index, overlay, text => Native.Mark(',
              'if (image != null)', 'image = RomFsFromDirectory(romfs, overlay);', 'device.Configuration.VirtualFileSystem.SetRomFs(pid, image);'),
      'stale index dropped, then: index read, else written and read, else the directory build as before')
check(removed.strip() == 'image = RomFsFromDirectory(romfs, overlay);', f'the only line replaced is the unconditional directory build: {removed.strip()!r}')
check('$"RewindBox: RomFS index read ({rbDirectories} directories checked)\\0"' in application and 'RewindBox: RomFS index written for the next starts\\0"u8' in application
      and 'RomFS 目录表建' not in removed and 'SetRomFs' not in removed,
      "reading and writing the index have their own start mark; S2Arm's own mark of the step is not touched, so its duration is still read on the same line")
check('S2A RomFS：游戏数据里没有预建索引' in application and '-' + ' ' * 20 + 'Console.Error.WriteLine' not in patch, "S2Arm's message about the missing index is kept")
check('using System.Text;' not in application and application.count('System.Text.Encoding.UTF8.GetBytes(') == 2,
      'Application.cs has no using for System.Text: the two marks name the encoding in full')

# The writer: one walk, lengths to S2Arm's list mode, stamp first, tree unchanged across the write, any failure drops the files and reports.
writer = index[index.find('internal static IStorage RbWriteAndOpen('):]
walk = writer[:writer.find('dirs.Sort(StringComparer.Ordinal);')]
check(writer.count('EnumerateFileSystemInfos("*", SearchOption.AllDirectories)') == 1 and 'EnumerateFiles(' not in writer and 'EnumerateDirectories(' not in writer,
      'the tree is walked once, with the options of Directory.EnumerateFiles(all directories), which S2Arm\'s writer and the directory build use')
check(ordered(walk, 'Directory.GetLastWriteTimeUtc(root).Ticks', 'EnumerateFileSystemInfos('), "the root's time is read before the walk (a change during it shows at the check)")
check(ordered(walk, 'bool link = (entry.Attributes & System.IO.FileAttributes.ReparsePoint) != 0;', 'if (link && entry is System.IO.DirectoryInfo)', 'throw new InvalidDataException(',
              'if (rel.IndexOfAny(RbLineBreaks) >= 0)', 'throw new InvalidDataException(', 'if (entry is System.IO.DirectoryInfo)', 'dirs.Add(rel + "\\t" + entry.LastWriteTimeUtc.Ticks);',
              'else if (!IsHostJunk(entry.FullName))', 'if (link)', 'using FileStream content = File.OpenRead(entry.FullName);', 'size = content.Length;',
              'size = ((System.IO.FileInfo)entry).Length;', 'files.Add((rel, size));'),
      "a directory gives its time, a file its own length, a link its target's (opened, as S2Arm's writer measures every file); junk names are left out as S2Arm leaves them; "
      'a linked directory or a name with a line break means no index')
check(walk.count('File.OpenRead(') == 1 and ordered(walk, 'if (link)', 'File.OpenRead('), 'only a link is opened: a plain file costs the lstat the walk already makes')
check(ordered(writer, 'if (OverlayFiles(overlayDir) != null)', 'return null;', 'dirs.Sort(StringComparer.Ordinal);', 'File.WriteAllText(indexPath + RbStampSuffix, stamp.ToString(),',
              'new(indexPath + RbListSuffix, false, new UTF8Encoding(false))', "list.Write(size);", "list.Write('\\t');", 'list.Write(rel);', "list.Write('\\n');",
              'mark?.Invoke($"RewindBox: RomFS tree walked ({files.Count} files, {dirs.Count} directories)");', 'Write(romfsDir, indexPath, indexPath + RbListSuffix);',
              'File.Delete(indexPath + RbListSuffix);', 'if (RbStale(romfsDir, indexPath, out _))', 'throw new IOException(', 'return Open(romfsDir, indexPath, null);'),
      "the stamp goes first (an interrupted write never leaves an index without a stamp); the lengths go to S2Arm's list mode as `bytes<TAB>path` lines; "
      'the tree must still be the stamped one after the write; no index with an overlay')
check(ordered(writer, 'catch (Exception e) when (e is IOException || e is UnauthorizedAccessException || e is InvalidDataException)', 'RbForget(indexPath);',
              'Red.Note("RewindBox: RomFS index not written', 'return null;'),
      'a write that fails removes its files, says so and leaves the directory build to the caller')

# The check at a start: the stamp's directories, one stat each, no walk.
stale = index[index.find('internal static bool RbStale('):index.find('internal static void RbForget(')]
check(ordered(stale, 'directories = 0;', 'if (!File.Exists(stamp))', 'return false;', 'string root = RbRoot(romfsDir);', 'File.ReadAllLines(stamp, Encoding.UTF8)',
              'lines[0] != RbStampHead', 'Directory.GetLastWriteTimeUtc(root).Ticks != rootTicks', 'return true;', "int tab = lines[i].LastIndexOf('\\t');", 'directories++;',
              'Directory.GetLastWriteTimeUtc(Path.Combine(root, lines[i].Substring(0, tab))).Ticks != ticks', 'return true;', 'return false;',
              'catch (Exception e) when (e is IOException || e is UnauthorizedAccessException)', 'return true;'),
      "an index without a stamp is S2Arm's pack-time one (never stale here); otherwise the root and every stamped directory must have the stamped time; "
      'an unreadable or malformed stamp counts as stale')
check('Enumerate' not in stale and 'File.OpenRead' not in stale, 'the check walks nothing and opens no game file: one stat per stamped directory')
root = index[index.find('private static string RbRoot('):index.find('internal static bool RbStale(')]
check(ordered(root, 'Path.GetFullPath(romfsDir)', 'Directory.ResolveLinkTarget(root, true)', 'target != null ? target.FullName : root'),
      "the tree's root is what romfs/ links to when it is a link (a link's own time does not move when its target's entries do)")
check('private const string RbStampHead = "rb-romfs-tree 1";' in index and ordered(writer, 'stamp.Append(RbStampHead).Append(\'\\n\').Append(Directory.GetLastWriteTimeUtc(root).Ticks).Append(\'\\n\');', 'stamp.Append(dir).Append(\'\\n\');'),
      'the stamp is a head line, the root\'s time, then `path<TAB>time` per directory: the format the first version wrote')
forget = index[index.find('internal static void RbForget('):index.find('internal static IStorage RbWriteAndOpen(')]
check(all(name in forget for name in ('File.Delete(indexPath + RbStampSuffix);', 'File.Delete(indexPath);', 'File.Delete(indexPath + ".tmp");', 'File.Delete(indexPath + RbListSuffix);')),
      "dropping an index removes the stamp, the index, the writer's temporary file and the list")
check('public const string RbStampSuffix = ".rbtree";' in index and 'public const string RbListSuffix = ".rblist";' in index, 'the stamp and the list sit next to the index (inside the pack folder)')
check('System.Security.Cryptography' not in added, 'no new library enters the NativeAOT link (the stamp is compared as text)')
check('public static void Write(' not in added + removed and 'class IndexedStorage' not in added + removed and 'public static IStorage Open(' not in added + removed,
      "S2Arm's index writer and reader are used as they are")
check('Native.' not in index, 'RomFsIndex.cs calls nothing of the native layer (it is also built into S2Arm\'s own index tool and tests): the mark comes in as a delegate')

# The pack folder the index is written in is removed by every new preparation of the game.
preparation = (ROOT / 'packages/s2arm_engine_bridge/ios/Classes/S2ArmGamePreparation.m').read_text(encoding='utf-8')
check(re.search(r'for \(NSString \*path in @\[ moduleDir, imagesDir, packDir \]\) \[files removeItemAtPath:path error:nil\];', preparation) is not None,
      'a new preparation deletes the pack folder, and with it an index written at an earlier start')

check(added.count('RewindBox (patch 0014)') == 2, 'both changes are marked RewindBox (patch 0014)')
series = sorted(p.name for p in PATCHES.glob('*.patch'))
check(len(series) >= 14 and series[13] == PATCH.name, f'0014 is the 14th engine patch: {series[12:15]}')
notices = (ROOT / 'docs/s2arm-legal-notices.md').read_text(encoding='utf-8')
check(PATCH.name in notices, 'the legal notices list patch 0014')
readme = (ROOT / 'build-utils/s2arm/engine/README.md').read_text(encoding='utf-8')
check(PATCH.name in readme and '126.9 s' in readme, 'the engine README explains patch 0014 and what its first version cost')
bridge_yml = (ROOT / '.github/workflows/s2arm-bridge-ios.yml').read_text(encoding='utf-8')
check('python3 -B test/s2arm_romfs_index_test.py' in bridge_yml and 'test/s2arm_romfs_index_test.py' in bridge_yml.split('jobs:')[0],
      's2arm-bridge-ios.yml runs this test and is triggered by it')

for failure in failures:
    print('FAIL ' + failure)
print(json.dumps({'result': 'failed' if failures else 'passed', 'checks': checks}))
sys.exit(1 if failures else 0)
