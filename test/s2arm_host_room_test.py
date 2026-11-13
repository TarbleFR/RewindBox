#!/usr/bin/env python3
"""Patch 0019: what the host app's images take from the low region is left to the host below the window (python3 + cc).

Engine log of an iPhone17,2, 13 Nov 16:15 (IPA 734), Mario Kart World, the layout in which the window cannot hold the
standard span. S2Arm leaves the host 3 GiB below the window (HOST_BELOW) and its sizing counts on the low region too
(vawin.c: the host's addresses on iOS = about 1.8 GB of low region + that range; a Switch 2 game's host peak is
1.7-2.1 GB). In RewindBox the app's own binary and frameworks fill the low region:

    地址窗口前：低区 [4 GB, 6 GB) 空余合计 184 MB、最大一块 36 MB
    GC 上限：分堆 SOH 1536 / LOH 512 / POH 128 MB（…开局一次保留约 2688 MB）
    宿主地址 [崩溃]：起点空洞 T0 1187 MB、最低 Tmin 166 MB（第 90 秒）…
    【预警】低区账：余量低于保留量，可腾退的腾出 0 MB / 差 141 MB

The .NET GC's reservation takes 2688 MB of the 3 GiB, which left Metal, malloc and the runtime 1187 MB of addresses;
at the first 3D frames 166 MB were left, under the engine's own reserve of 256 MB. That run stopped on something else
(patch 0016) before anything was refused, so this is a margin restored, not a failure seen.

Patch 0019: when the window gives up the two ranges of patch 0013, the host also gets, below them, what the low
region lacks of the 1843 MB the layout counts on, in whole GiB, at most 2 GiB (S2A_HOST_MORE_MB), and only as much as
leaves both ranges their size. The room comes from the part of the alias region that fits in the window (the game had
touched 0.7 of 29.7 GiB); the window still holds the regions in front of the alias region and one application pool
of it. On the device's numbers: 2 GiB more for the host, the window 39936 MB instead of 41984 MB.

The rule (runtime/src/rb_hostroom.c) is compiled from the patch and run here together with patch 0013's own sizing
(rb_vparena.c from that patch). The engine is compiled by s2arm-engine.yml; what the host's addresses do on a device
is only known from its log (`RewindBox: the low region [4 GB, 6 GB) has N MB free ...`, then the ledger lines).

    python3 -B test/s2arm_host_room_test.py
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATCHES = ROOT / 'build-utils/s2arm/engine/patches'
PATCH = PATCHES / '0019-guest-host-room-for-what-the-app-takes-from-the-low-region.patch'
ARENAS = PATCHES / '0013-guest-virtual-pool-arena-and-host-stacks-below-the-window.patch'
HARNESS = ROOT / 'test/s2arm_host_room_harness.c'
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


def sections(patch):
    found = {}
    for part in re.split(r'^(?=diff --git )', patch, flags=re.M):
        match = re.match(r'diff --git a/(\S+) b/', part)
        if match:
            found[match.group(1)] = part
    return found


def plus(part):
    return '\n'.join(line[1:] for line in part.splitlines() if line.startswith('+') and not line.startswith('+++'))


def minus(part):
    return '\n'.join(line[1:] for line in part.splitlines() if line.startswith('-') and not line.startswith('---'))


patch = PATCH.read_text(encoding='utf-8') if PATCH.is_file() else ''
check(bool(patch), 'patch 0019 exists')
files = sections(patch)
ROOM = 'runtime/src/rb_hostroom.c'
check(sorted(files) == [ROOM, 'runtime/src/vawin.c'], f'patch 0019 touches vawin.c and adds rb_hostroom.c: {sorted(files)}')
room_part, vawin = files.get(ROOM, ''), files.get('runtime/src/vawin.c', '')
check('new file mode' in room_part and not minus(room_part), 'rb_hostroom.c is a new file')
room = plus(room_part) + '\n'
check('#include "native.h"' not in room and 'mach/' not in room, 'rb_hostroom.c needs no engine or Mach header (it is compiled alone here)')

# ---- the window side ----
added, removed = plus(vawin), minus(vawin)
check(ordered(added, 'rb_extra = rb_arenas(g_fit, &rb_tl, &rb_vp); rb_host = rb_extra ? rb_host_more(g_fit, &rb_low) : 0;',
              'at = fat + HOST_BELOW + rb_host + rb_extra; want = g_fit - HOST_BELOW - rb_host - rb_extra; g_keep_lo = fat;'),
      "the host's share is HOST_BELOW plus the extra room, only when the window gives up patch 0013's ranges; the host's range still starts at the hole")
check('#define HOST_BELOW' not in added and '#define HOST_BELOW' not in removed and '#define TL_TAKE' not in added and '#define RB_VP_ARENA' not in added + removed,
      "S2Arm's own 3 GiB, the tail allocator's size and the arena's size are not changed")
check('mmap(' not in added + removed, 'the reservation itself is patch 0013\'s, untouched: one piece, checked where it lands')
check(ordered(added, 'static uint64_t rb_arenas_at(uint64_t fit, uint64_t host_below, uint64_t *tail, uint64_t *vp) {', 'return sizes(fit, host_below, g_need, RB_VAMM_ALIAS,',
              'static uint64_t rb_arenas(uint64_t fit, uint64_t *tail, uint64_t *vp) { return rb_arenas_at(fit, HOST_BELOW, tail, vp); }'),
      "patch 0013's sizing is the same call with the host's share as an argument")
check(ordered(added, '#define RB_LOW_COUNTED (1843ull << 20)', '#define RB_HOST_MORE (2ull << 30)', 'dlsym(RTLD_DEFAULT, "s2a_rb_host_more")',
              'holes_in(0x100000000ull, 0x180000000ull, low_free, &largest);', 'getenv("S2A_HOST_MORE_MB")',
              'more(*low_free, RB_LOW_COUNTED, most, HOST_BELOW, rb_arenas_cb, &fit)'),
      "the low region is measured as S2Arm's own start-up line measures it ([4 GiB, 6 GiB)); the rule is taken by name; S2A_HOST_MORE_MB sets the most")
check('the low region [4 GB, 6 GB) has %llu MB free where the layout counts on about %llu MB: %llu MB more are left to the host below the window' in added
      and added.count('(unsigned long long)((HOST_BELOW + rb_host) >> 20)') == 2,
      'the engine log says what the low region had and what the host got; the two lines that gave the host\'s share give the real one')
check(not re.search(r'^-.*【红】', vawin, re.M), 'no red line of the reservation is removed')

# ---- the rule, compiled from the patch with patch 0013's sizing, and run ----
check(ordered(room, 'if (!arenas || low_free >= counted) return 0;', 'uint64_t given = arenas(host_below, ctx);', 'if (!given) return 0;',
              '(counted - low_free + RBH_GIB - 1) & ~(RBH_GIB - 1)', 'if (more > most) more = most & ~(RBH_GIB - 1);',
              'while (more && arenas(host_below + more, ctx) != given) more -= RBH_GIB;', 'return more;'),
      'what the low region lacks, in whole GiB, capped, and lowered until the arenas are what they were')
arena_source = plus(sections(ARENAS.read_text(encoding='utf-8')).get('runtime/src/rb_vparena.c', '')) + '\n' if ARENAS.is_file() else ''
check(bool(arena_source.strip()), "patch 0013's rb_vparena.c is there to size the arenas")
check(HARNESS.is_file(), 'test/s2arm_host_room_harness.c exists')
compiler = shutil.which('cc') or shutil.which('clang') or shutil.which('gcc')
check(bool(compiler), 'a C compiler is available (cc, clang or gcc)')
ran = ''
if compiler and room.strip() and arena_source.strip() and HARNESS.is_file():
    with tempfile.TemporaryDirectory() as work:
        work = Path(work)
        (work / 'rb_hostroom.c').write_text(room, encoding='utf-8')
        (work / 'rb_vparena.c').write_text(arena_source, encoding='utf-8')
        binary = work / 'room'
        build = subprocess.run([compiler, '-std=c11', '-D_GNU_SOURCE', '-D_DARWIN_C_SOURCE', '-Wall', '-Wextra', '-Werror', '-O1', '-o', str(binary), str(HARNESS),
                                str(work / 'rb_hostroom.c'), str(work / 'rb_vparena.c'), '-lpthread'], capture_output=True, text=True)
        check(build.returncode == 0, 'the rule, the sizing and the harness compile without a warning: ' + build.stderr[-700:])
        if build.returncode == 0:
            run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=60)
            ran = run.stdout.strip().splitlines()[-1] if run.stdout.strip() else ''
            check(run.returncode == 0 and ran.startswith('PASSED'), 'the harness passes: ' + run.stdout[-900:])

check(plus(patch).count('RewindBox (patch 0019)') >= 4, 'the changes are marked RewindBox (patch 0019)')
series = sorted(p.name for p in PATCHES.glob('*.patch'))
check(len(series) >= 19 and series[18] == PATCH.name, f'0019 is the 19th engine patch: {series[17:20]}')
notices = (ROOT / 'docs/s2arm-legal-notices.md').read_text(encoding='utf-8')
check(PATCH.name in notices and ROOM in notices, 'the legal notices list patch 0019 and its new file')
readme = (ROOT / 'build-utils/s2arm/engine/README.md').read_text(encoding='utf-8')
check(PATCH.name in readme, 'the engine README explains patch 0019')

for failure in failures:
    print('FAIL ' + failure)
print(json.dumps({'result': 'failed' if failures else 'passed', 'checks': checks, 'harness': ran}))
sys.exit(1 if failures else 0)
