#!/usr/bin/env python3
"""Patch 0013: NVN virtual pools and the host stacks of the game's threads get address ranges of their own (plain python3 + cc).

Mario Kart World on IPA 733 (engine log of iPhone17,2, 13 Nov, engine 9ddb304e with patch 0012): 0 frames. The window
cannot hold the game's standard layout (75958 MB asked, largest hole below 2^39 64512 MB), so the engine left 3 GiB to
the host below the window and gave the window the rest. Every NVN virtual pool was then reserved by mmap(NULL) in those
3 GiB, next to Metal, malloc, the .NET GC and the host stacks of the game's threads (the tail allocator, which serves
those stacks, has no range in that layout). The first 8 pools took 1016 MB, later ones asked 1 GiB each: the host hole
went 1717 MB -> 813 -> 693 -> 5 MB, reservations were halved (512 MB, 32 MB, 16 MB) then refused (errno 12), MapVirtual
was refused 219 times, and pthread_create failed with EAGAIN for the game's thread 162 (session ended, code 134).

Patch 0013: in that layout the window gives up two ranges right below its base, reserved in one piece with it: one for
the tail allocator (host stacks first), one for the virtual pools (runtime/src/rb_vparena.c, a new file). The host's
3 GiB stay as they were. A pool's range is cut at the full length asked and given back when the pool is finalized; the
halving fallback only remains for the kernel's own placement, and is now a red line with the pool's size.

The arena file is compiled from the patch and run here (first fit, merging, guard page, inaccessible again after
release, 20000 random steps), with the sizing rule on the numbers of the device log. The engine itself is compiled by
s2arm-engine.yml; what the game does with it is only known from a device log.

    python3 -B test/s2arm_vp_arena_test.py
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
PATCH = PATCHES / '0013-guest-virtual-pool-arena-and-host-stacks-below-the-window.patch'
HARNESS = ROOT / 'test/s2arm_vp_arena_harness.c'
ARENA = 'runtime/src/rb_vparena.c'
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
    """file -> its part of the patch."""
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
check(bool(patch), 'patch 0013 exists')
files = sections(patch)
check(sorted(files) == ['graphics/nvn/gfx/nvn/hle_nvn.c', ARENA, 'runtime/src/vawin.c'],
      f'patch 0013 touches hle_nvn.c, vawin.c and adds rb_vparena.c: {sorted(files)}')
arena_part, vawin, nvn = files.get(ARENA, ''), files.get('runtime/src/vawin.c', ''), files.get('graphics/nvn/gfx/nvn/hle_nvn.c', '')
check('new file mode' in arena_part and not minus(arena_part), 'rb_vparena.c is a new file')
arena = plus(arena_part) + '\n'

# ---- the window side (vawin.c) ----
added, removed = plus(vawin), minus(vawin)
check(ordered(added, 'rb_extra = rb_arenas(g_fit, &rb_tl, &rb_vp);', 'at = fat + HOST_BELOW + rb_extra;', 'want = g_fit - HOST_BELOW - rb_extra;', 'g_keep_lo = fat;'),
      'only the layout that cannot hold the standard span gives the ranges up; the host keeps HOST_BELOW below them')
check('#define HOST_BELOW' not in added and '#define HOST_BELOW' not in removed and '#define TL_TAKE' not in added,
      "the host's 3 GiB and the tail allocator's own size are not changed")
check('mmap((void *)(at - rb_extra), want + rb_extra, PROT_NONE, MAP_PRIVATE | MAP_ANON, -1, 0);' in added and '| MAP_FIXED' not in added and 'MAP_FIXED |' not in added,
      'the ranges and the window are one reservation, still without MAP_FIXED (the landing is checked, nothing is overwritten)')
check(ordered(vawin, 'if (p != (void *)(at - rb_extra)) { if (p != MAP_FAILED) munmap(p, want + rb_extra);', 'g_ok = 1; g_base = at; g_size = g_res = want;',
              'if (rb_tl) s2a_tail_init(at - rb_extra, rb_tl);', 'init(at - rb_vp, rb_vp);'),
      'a reservation that lands elsewhere is given back whole (red line kept); otherwise tail range first, virtual pool arena right below the window')
check('【红】地址窗口：空洞 %#llx +%llu MB 占不到' in added and '【红】地址窗口：空洞 %#llx +%llu MB 占不到' in removed,
      'the failure of the reservation is still reported in red')
check(ordered(added, 'static int rb_alias_first(void) {', 'if (g_ctr || !g_npdm[0]) return 1;', '"addr_need.tsv"', '别名区GB'),
      "a game whose alias region the layout sizes from the window (addr_need.tsv hint), or an unknown game, keeps the window it had")
check(ordered(added, 'dlsym(RTLD_DEFAULT, "s2a_rb_host_arenas")', 'dlsym(RTLD_DEFAULT, "s2a_app_pool")', 'getenv("S2A_VP_ARENA_MB")', 'tail_on() ? TL_TAKE : 0'),
      'sizes come from rb_vparena.c by name (S2Arm tests that link vawin.c alone give nothing up); S2A_VP_ARENA_MB and S2A_TAIL are honoured')
check('dlsym(RTLD_DEFAULT, "s2a_rb_vp_note")' in added, "the arena's line is logged with the tail allocator's in the address listing")
check('s2a_guest' not in added and 'guest_file' not in added, 'the guest memory file is still mapped over the window only')

# ---- the pools (hle_nvn.c) ----
added, removed = plus(nvn), minus(nvn)
check(ordered(nvn, '+    int rb = 0;', 'a = s2a_rb_vp_map(len); rb = a != NULL;', '\n     if (!a) a = vpool_mmap(len);') and '-    if (!a) a = vpool_mmap(len);' not in nvn,
      'a pool takes its range from the arena at the length asked, the kernel chooses only when the arena has none')
check(ordered(nvn, 'void *a = s2a_vp_arena_map ? s2a_vp_arena_map(len) : NULL;', 's2a_rb_vp_map(len)'),
      "S2Arm's own frame-recording arena keeps priority")
check('uint64_t cap = 1ull << 30;' not in added and 'uint64_t cap' not in removed and 'len = o->size < cap ? o->size : cap' not in removed,
      "the engine's reservation per pool (its size, at most 1 GiB) is not changed")
check('has no free range of %#llx bytes' in added and added.count('【红】') >= 3, 'an arena that cannot hold a pool is a red line')
check('【红】 [nvn] virtual pool %p (%#llx bytes): %#llx bytes of address space not available (errno %d), reserving %#llx instead' in added
      and '[nvn] virtual pool %p: %#llx bytes of address space not available (errno %d), reserving %#llx instead' in removed,
      'a reservation smaller than asked is now a red line, with the size of the pool')
check('【红】 virtual pool %p (%#llx bytes): cannot reserve %#llx bytes of address space (errno %d)' in added and 'return NULL; }' in added,
      'a refused reservation still fails the pool, in red, with its size')
check(ordered(nvn, ' static void vpool_unmap_range(uint8_t *base, uint64_t len) {', '+    if (s2a_rb_vp_unmap && s2a_rb_vp_unmap(base, len)) return;', '\n     if (s2a_vp_arena_has'),
      "a finalized pool's range goes back to the arena before any munmap")
check(all(f'弱链接[nvntest]：{name}' in added for name in ('s2a_rb_vp_map', 's2a_rb_vp_unmap', 's2a_rb_vp_size')),
      "the three arena functions are declared for S2Arm's NVN unit-test link, as its own arena functions are")
check('is %#llx bytes; %#llx are reserved' in added, 'a pool larger than its reservation is logged with its real size (first 8)')
check(not re.search(r'^-.*(LOG\("【红】 MapVirtual|return 0;)', nvn, re.M), 'no failure of MapVirtual is removed or softened')

# ---- the arena, compiled from the patch and run ----
check(HARNESS.is_file(), 'test/s2arm_vp_arena_harness.c exists')
check('#include "native.h"' not in arena and 'mach/' not in arena, 'rb_vparena.c needs no engine or Mach header (it is compiled alone here)')
check(ordered(arena, 'int s2a_rb_vp_unmap(void *p, uint64_t len) {', 'mmap(p, n, PROT_NONE, MAP_PRIVATE | MAP_ANON | MAP_FIXED, -1, 0) == p'),
      'a released range is covered with a fresh inaccessible mapping (no alias of the old pool survives)')
check('+ RBVP_PAGE; }' in arena and '#define RBVP_PAGE 16384ull' in arena, 'ranges start on a 16 KiB host page and are followed by one guard page')
compiler = shutil.which('cc') or shutil.which('clang') or shutil.which('gcc')
check(bool(compiler), 'a C compiler is available (cc, clang or gcc)')
ran = ''
if compiler and arena.strip() and HARNESS.is_file():
    with tempfile.TemporaryDirectory() as work:
        source, binary = Path(work) / 'rb_vparena.c', Path(work) / 'vp_arena'
        source.write_text(arena, encoding='utf-8')
        build = subprocess.run([compiler, '-std=c11', '-D_GNU_SOURCE', '-D_DARWIN_C_SOURCE', '-Wall', '-Wextra', '-Werror', '-O1', '-o', str(binary),
                                str(HARNESS), str(source), '-lpthread'], capture_output=True, text=True)
        check(build.returncode == 0, 'rb_vparena.c and the harness compile without a warning: ' + build.stderr[-600:])
        if build.returncode == 0:
            run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=120)
            ran = run.stdout.strip().splitlines()[-1] if run.stdout.strip() else ''
            check(run.returncode == 0 and ran.startswith('PASSED'), 'the arena harness passes: ' + run.stdout[-900:])

series = sorted(p.name for p in PATCHES.glob('*.patch'))
check(len(series) >= 13 and series[12] == PATCH.name, f'0013 is the 13th engine patch: {series[11:14]}')
check(plus(patch).count('RewindBox (patch 0013)') >= 8, 'every change is marked RewindBox (patch 0013)')
notices = (ROOT / 'docs/s2arm-legal-notices.md').read_text(encoding='utf-8')
check(PATCH.name in notices and ARENA in notices, 'the legal notices list patch 0013 and its new file')
readme = (ROOT / 'build-utils/s2arm/engine/README.md').read_text(encoding='utf-8')
check(PATCH.name in readme, 'the engine README explains patch 0013')
bridge_yml = (ROOT / '.github/workflows/s2arm-bridge-ios.yml').read_text(encoding='utf-8')
check('python3 -B test/s2arm_vp_arena_test.py' in bridge_yml and 'test/s2arm_vp_arena_test.py' in bridge_yml.split('jobs:')[0]
      and 'test/s2arm_vp_arena_harness.c' in bridge_yml.split('jobs:')[0], 's2arm-bridge-ios.yml runs this test and is triggered by it')

for failure in failures:
    print('FAIL ' + failure)
print(json.dumps({'result': 'failed' if failures else 'passed', 'checks': checks, 'harness': ran}))
sys.exit(1 if failures else 0)
