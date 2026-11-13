#!/usr/bin/env python3
"""Patch 0014: the RomFS index of a game prepared on the phone is written at its first start and reused (plain python3).

Mario Kart World on IPA 733 (engine log of iPhone17,2, 13 Nov): `服务：RomFS 目录表建 +69684.1 ms（本段 69232.8 ms）`, and
65201.9 ms in the session of 12 Nov: at every launch the services enumerate the RomFS directory (205,058 files in the
preparation journal) and open each file for its length, because the game has no romfs.s2aidx. S2Arm writes that index
when it packs a game on a computer (pack/stages/romfsidx.sh); RewindBox's on-device preparation does not
(docs/s2arm-study-2026-11-11.md, "Not ported").

Patch 0014: when there is no index the services write it with S2Arm's own writer (RomFsIndex.Write, the image its own
test compares byte for byte with the directory build: services/S2A.Services.Tests/Program.cs) and read the image
through it; the next starts read the index. An index written this way carries a stamp of the directory tree it was
written for and is dropped when the tree changed; an index without a stamp (S2Arm's pack-time one) is trusted as before.
The index sits in the game's pack folder, which RewindBox's preparation deletes whenever it prepares the game again.

The C# is compiled by s2arm-engine.yml (no .NET SDK here); the time of the second start is only known from a device log
(start marks `RewindBox: RomFS index written for the next starts` then `RewindBox: RomFS index read`).

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
check(ordered(application, 'if (File.Exists(index) && RomFsIndex.RbStale(romfs, index))', 'RomFsIndex.RbForget(index);',
              ' if (File.Exists(index))', 'image = RomFsIndex.Open(romfs, index, overlay);', 'image = RomFsIndex.RbWriteAndOpen(romfs, index, overlay);',
              'if (image != null)', 'image = RomFsFromDirectory(romfs, overlay);', 'device.Configuration.VirtualFileSystem.SetRomFs(pid, image);'),
      'stale index dropped, then: index read, else written and read, else the directory build as before')
check(removed.strip() == 'image = RomFsFromDirectory(romfs, overlay);', f'the only line replaced is the unconditional directory build: {removed.strip()!r}')
check('RewindBox: RomFS index read\\0"u8' in application and 'RewindBox: RomFS index written for the next starts\\0"u8' in application
      and 'RomFS 目录表建' not in removed and 'SetRomFs' not in removed,
      "reading and writing the index have their own start mark; S2Arm's own mark of the step is not touched, so its duration is still read on the same line")
check('S2A RomFS：游戏数据里没有预建索引' in application and '-' + ' ' * 20 + 'Console.Error.WriteLine' not in patch, "S2Arm's message about the missing index is kept")

# The writer: S2Arm's own, stamp first, tree unchanged across the write, any failure drops the files and reports.
writer = index[index.find('internal static IStorage RbWriteAndOpen('):]
check(ordered(writer, 'if (OverlayFiles(overlayDir) != null)', 'return null;', 'string before = RbTreeStamp(romfsDir);',
              'File.WriteAllText(indexPath + RbStampSuffix, before, Encoding.UTF8);', 'Write(romfsDir, indexPath);',
              'if (RbTreeStamp(romfsDir) != before)', 'throw new IOException(', 'return Open(romfsDir, indexPath, null);'),
      "written with RomFsIndex.Write; the stamp goes first (an interrupted write never leaves an index without a stamp); no index with an overlay")
check(ordered(writer, 'catch (Exception e) when (e is IOException || e is UnauthorizedAccessException || e is InvalidDataException)', 'RbForget(indexPath);',
              'Red.Note("RewindBox: RomFS index not written', 'return null;'),
      'a write that fails removes its files, says so in the log and leaves the directory build to the caller')
stale = index[index.find('internal static bool RbStale('):index.find('internal static void RbForget(')]
check(ordered(stale, 'if (!File.Exists(stamp))', 'return false;', 'return File.ReadAllText(stamp, Encoding.UTF8) != RbTreeStamp(romfsDir);', 'return true;'),
      "an index without a stamp is S2Arm's pack-time one (never stale here); an unreadable stamp or tree counts as stale")
stamp = index[index.find('internal static string RbTreeStamp('):index.find('internal static bool RbStale(')]
check(ordered(stamp, 'Directory.ResolveLinkTarget(root, true)', 'Directory.EnumerateDirectories(root, "*", SearchOption.AllDirectories)', 'dirs.Sort(StringComparer.Ordinal);',
              'Directory.GetLastWriteTimeUtc(root).Ticks', 'Directory.GetLastWriteTimeUtc(dir).Ticks'),
      "the stamp is every directory of the tree (the link's target when romfs/ is a link) with its modification time, in a fixed order")
forget = index[index.find('internal static void RbForget('):index.find('internal static IStorage RbWriteAndOpen(')]
check(all(name in forget for name in ('File.Delete(indexPath + RbStampSuffix);', 'File.Delete(indexPath);', 'File.Delete(indexPath + ".tmp");')),
      "dropping an index removes the stamp, the index and the writer's temporary file")
check('public const string RbStampSuffix = ".rbtree";' in index, 'the stamp is romfs.s2aidx.rbtree, next to the index (inside the pack folder)')
check('System.Security.Cryptography' not in added, 'no new library enters the NativeAOT link (the stamp is compared as text)')
check('public static void Write(' not in added and 'IndexedStorage' not in added, "S2Arm's index writer and reader are used as they are")

# The pack folder the index is written in is removed by every new preparation of the game.
preparation = (ROOT / 'packages/s2arm_engine_bridge/ios/Classes/S2ArmGamePreparation.m').read_text(encoding='utf-8')
check(re.search(r'for \(NSString \*path in @\[ moduleDir, imagesDir, packDir \]\) \[files removeItemAtPath:path error:nil\];', preparation) is not None,
      'a new preparation deletes the pack folder, and with it an index written at an earlier start')

check(added.count('RewindBox (patch 0014)') == 2, 'both changes are marked RewindBox (patch 0014)')
series = sorted(p.name for p in PATCHES.glob('*.patch'))
check(len(series) >= 14 and series[13] == PATCH.name, f'0014 is the 14th engine patch: {series[12:15]}')
notices = (ROOT / 'docs/s2arm-legal-notices.md').read_text(encoding='utf-8')
check(PATCH.name in notices and 'RewindBox patches 0001–0014' in notices, 'the legal notices list patch 0014 and the series 0001–0014')
readme = (ROOT / 'build-utils/s2arm/engine/README.md').read_text(encoding='utf-8')
check(PATCH.name in readme, 'the engine README explains patch 0014')
bridge_yml = (ROOT / '.github/workflows/s2arm-bridge-ios.yml').read_text(encoding='utf-8')
check('python3 -B test/s2arm_romfs_index_test.py' in bridge_yml and 'test/s2arm_romfs_index_test.py' in bridge_yml.split('jobs:')[0],
      's2arm-bridge-ios.yml runs this test and is triggered by it')

for failure in failures:
    print('FAIL ' + failure)
print(json.dumps({'result': 'failed' if failures else 'passed', 'checks': checks}))
sys.exit(1 if failures else 0)
