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

The .NET GC reserves its limit from the host's hole below the window: 870 MB at most when that hole is under 3712 MB,
2688 MB from there on (gclimit.c). The hole is the 3 GiB and the 0-1023 MB that the window's 1 GiB alignment leaves in
front of them, so the limit changes from start to start: 2688 MB of 4094 MB in that run, the smaller one on five of
the phone's seven logged starts (holes of 3140-3304 MB). That run was left 1187 MB of addresses for Metal, malloc and
the runtime; at the first 3D frames 166 MB were left, under the engine's own reserve of 256 MB. It stopped on
something else (patch 0016) before anything was refused, so this is a margin restored, not a failure seen.

Patch 0019: when the window gives up the two ranges of patch 0013, the host also gets, below them, what the low
region lacks of the 1843 MB the layout counts on, in whole GiB, at most 2 GiB (S2A_HOST_MORE_MB), and only as much as
leaves both ranges their size. The room comes from the part of the alias region that fits in the window (the game had
touched 0.7 of 29.7 GiB); the window still holds the regions in front of the alias region and one application pool
of it. On the device's numbers: 2 GiB more for the host, the window 39936 MB instead of 41984 MB.

The GC limit is picked by the hole without that room (vawin.c s2a_rb_low_holes_less, used by gclimit.c): it is the one
S2Arm picks for the start, and every GiB given is the host's. Counted (the first version of this patch), the room put
every start over 3712 MB: with 2 GiB a start that had the smaller limit gained 230 MB, and with one GiB it lost 794 MB.

The rule (runtime/src/rb_hostroom.c) is compiled from the patch and run here together with patch 0013's own sizing
(rb_vparena.c from that patch). With S2ARM_UPSTREAM (an S2Arm checkout holding the pinned commit) gclimit.c of that
commit with the patch applied is compiled too, with a stand-in for native.h, and s2a_gc_limit_apply is run: the limit
picked with and without a room, and without the function (the room counted, as S2Arm's own test links the file).
Without the variable that part is not executed and the result says so. s2a_rb_low_holes_less itself reads the
process's regions through Mach and is not run here. The engine is compiled by s2arm-engine.yml; what the host's
addresses do on a device is only known from its log (`RewindBox: the low region [4 GB, 6 GB) has N MB free ...`,
`RewindBox: the GC limit is picked without the N MB ...`, the `GC 上限` line, then the ledger lines).

    python3 -B test/s2arm_host_room_test.py
"""
import json
import os
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


def after(part):
    """The lines of the file's changed places as the patch leaves them: context and added lines."""
    return '\n'.join(line[1:] for line in part.splitlines() if line[:1] in (' ', '+') and not line.startswith('+++'))


patch = PATCH.read_text(encoding='utf-8') if PATCH.is_file() else ''
check(bool(patch), 'patch 0019 exists')
files = sections(patch)
ROOM = 'runtime/src/rb_hostroom.c'
GCLIMIT = 'runtime/src/gclimit.c'
check(sorted(files) == [GCLIMIT, ROOM, 'runtime/src/vawin.c'], f'patch 0019 touches gclimit.c and vawin.c and adds rb_hostroom.c: {sorted(files)}')
room_part, vawin, gclimit = files.get(ROOM, ''), files.get('runtime/src/vawin.c', ''), files.get(GCLIMIT, '')
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

# ---- the GC limit is picked without the room ----
check(ordered(after(vawin), 'g_ok = 1; g_base = at; g_size = g_res = want;', 'if (rb_host) { g_rb_more = rb_host; g_rb_more_lo = at - rb_extra - rb_host; }')
      and 'static uint64_t g_rb_more_lo, g_rb_more;' in added,
      "the room given is recorded once the reservation is where it was asked: the top of the host's range, ending where patch 0013's ranges start")
check(ordered(after(vawin), 'if (g_ok) holes_in(g_base + g_size, 1ull << 39, total, largest);', 'void s2a_rb_low_holes_less(uint64_t *total, uint64_t *largest, uint64_t *more) {',
              '*more = g_ok ? g_rb_more : 0;', 'if (!*more) { s2a_low_holes(total, largest); return; }', '*total = *largest = 0;',
              'holes_in(0x100000000ull, g_rb_more_lo, total, largest);', 'holes_in(g_rb_more_lo + g_rb_more, g_base, total, largest);',
              'holes_in(g_base + g_size, 1ull << 39, total, largest);'),
      "s2a_rb_low_holes_less reads s2a_low_holes' own ranges with the room left out; with no room it is s2a_low_holes")
check(not minus(gclimit).strip(), 'no line of gclimit.c is removed: its tiers, thresholds and limits are S2Arm\'s')
check(ordered(after(gclimit), 'if (getenv(vars[i])) {', 'uint64_t total = 0, largest = 0; s2a_low_holes(&total, &largest);', 'dlsym(RTLD_DEFAULT, "s2a_rb_low_holes_less")',
              'uint64_t lt = 0, ll = 0, more = 0; if (less) less(&lt, &ll, &more);', 'if (more) { LOG("RewindBox: the GC limit is picked without the %llu MB',
              'total = lt; largest = ll; } }', 'switch (s2a_gc_limit_pick(largest)) {'),
      'gclimit.c takes the holes without the room, by name, after the check of a limit set from outside and before the pick; it says so in the log')

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
NATIVE_H = '''// Stand-in for S2Arm's runtime/src/native.h: what gclimit.c uses of it
#include <dlfcn.h>
#include <stdint.h>
void rb_test_log(const char *format, ...);
#define LOG(...) rb_test_log(__VA_ARGS__)
int s2a_gc_limit_pick(uint64_t largest);
void s2a_gc_limit_apply(void);
void s2a_low_holes(uint64_t *total, uint64_t *largest);
'''
upstream = os.environ.get('S2ARM_UPSTREAM')
ran, ran_limit = '', 'not executed (S2ARM_UPSTREAM not set)'
if compiler and room.strip() and arena_source.strip() and HARNESS.is_file():
    with tempfile.TemporaryDirectory() as work:
        work = Path(work)
        (work / 'rb_hostroom.c').write_text(room, encoding='utf-8')
        (work / 'rb_vparena.c').write_text(arena_source, encoding='utf-8')
        binary = work / 'room'
        flags = ['-std=c11', '-D_GNU_SOURCE', '-D_DARWIN_C_SOURCE', '-Wall', '-Wextra', '-Werror', '-O1']
        build = subprocess.run([compiler, *flags, '-o', str(binary), str(HARNESS), str(work / 'rb_hostroom.c'), str(work / 'rb_vparena.c'), '-lpthread'],
                               capture_output=True, text=True)
        check(build.returncode == 0, 'the rule, the sizing and the harness compile without a warning: ' + build.stderr[-700:])
        if build.returncode == 0:
            run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=60)
            ran = run.stdout.strip().splitlines()[-1] if run.stdout.strip() else ''
            check(run.returncode == 0 and ran.startswith('PASSED'), 'the harness passes: ' + run.stdout[-900:])
        if upstream:   # S2Arm's gclimit.c of the pinned commit with the patch applied, run with a stand-in for native.h
            pin = json.loads((ROOT / 'tools/s2arm_prototype/pin.json').read_text(encoding='utf-8'))['s2arm']['commit']
            shown = subprocess.run(['git', '-C', upstream, 'show', f'{pin}:{GCLIMIT}'], capture_output=True)
            check(shown.returncode == 0, f'{upstream} holds {GCLIMIT} of the pinned S2Arm commit {pin}: ' + shown.stderr.decode(errors='replace')[-200:])
            if shown.returncode == 0:
                tree = work / 'tree'
                (tree / 'runtime/src').mkdir(parents=True)
                (tree / GCLIMIT).write_bytes(shown.stdout)
                applied = subprocess.run(['git', 'apply', '--include=' + GCLIMIT, str(PATCH)], cwd=tree, capture_output=True, text=True)
                check(applied.returncode == 0 and b's2a_rb_low_holes_less' in (tree / GCLIMIT).read_bytes(), "the patch's gclimit.c part applies on the pinned file: " + applied.stderr[-300:])
                (tree / 'runtime/src/native.h').write_text(NATIVE_H, encoding='utf-8')
                sources = [str(HARNESS), str(tree / GCLIMIT), str(work / 'rb_hostroom.c'), str(work / 'rb_vparena.c')]
                results = []
                for name, extra, argument in (('limit', ['-rdynamic'], []), ('limit-absent', [], ['absent'])):
                    if name == 'limit-absent' and not sys.platform.startswith('linux'):
                        results.append('without the function: not executed (only a Linux executable keeps its own functions from dlsym)')
                        continue
                    built = subprocess.run([compiler, *flags, '-DRB_GCLIMIT', *extra, '-o', str(work / name), *sources, '-lpthread', '-ldl'], capture_output=True, text=True)
                    check(built.returncode == 0, f'gclimit.c as patched compiles without a warning ({name}): ' + built.stderr[-700:])
                    if built.returncode == 0:
                        run = subprocess.run([str(work / name), *argument], capture_output=True, text=True, timeout=60)
                        last = run.stdout.strip().splitlines()[-1] if run.stdout.strip() else ''
                        check(run.returncode == 0 and last.startswith('PASSED'), f'the harness with gclimit.c passes ({name}): ' + run.stdout[-1200:])
                        results.append(f'{name}: {last}')
                ran_limit = '; '.join(results)

check(plus(patch).count('RewindBox (patch 0019)') >= 4, 'the changes are marked RewindBox (patch 0019)')
series = sorted(p.name for p in PATCHES.glob('*.patch'))
check(len(series) >= 19 and series[18] == PATCH.name, f'0019 is the 19th engine patch: {series[17:20]}')
notices = (ROOT / 'docs/s2arm-legal-notices.md').read_text(encoding='utf-8')
check(PATCH.name in notices and ROOM in notices and GCLIMIT in notices, 'the legal notices list patch 0019, its new file and the files it modifies')
readme = (ROOT / 'build-utils/s2arm/engine/README.md').read_text(encoding='utf-8')
check(PATCH.name in readme, 'the engine README explains patch 0019')

for failure in failures:
    print('FAIL ' + failure)
print(json.dumps({'result': 'failed' if failures else 'passed', 'checks': checks, 'harness': ran, 'gclimit': ran_limit}))
sys.exit(1 if failures else 0)
