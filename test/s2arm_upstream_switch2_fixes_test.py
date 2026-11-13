#!/usr/bin/env python3
"""Patch 0015: four fixes S2Arm made after the pin for Switch 2 games, taken as they are (plain python3).

The pin is S2Arm 6b6a5715 (10 Nov). Between it and S2Arm's main of 13 Nov (6bd0f402) four fixes concern a Switch 2 game
that runs in direct mode on Metal 4, which is how Mario Kart World runs on iPhone17,2 (engine log of 13 Nov: `Switch 2
进程：NVN2 设备`, `direct backend: Metal 4`):

  240603b6  a Switch 2 pool's buffer address is the CPU address of its storage. The pin gives every pool an address in
            a window from 0xC000000000; a Switch 2 game reads GetBufferAddress + offset with the CPU (S2Arm #351: crash
            before the first frame at 0xc086d00000, right after a virtual pool was mapped).
  09e80022  nn::oe::SetGraphicsTargetFrameRate is answered by the host. The SDK's own goes to the gs session, which
            direct mode never starts (S2Arm #679: abort after the first frame of 04003F40232DE000).
  81f8e8bd  the GPU time of a frame is the sum of each submission's own time on its queue, not of spans that include the
            wait behind earlier submissions (S2Arm #647: 23 runs on Metal 4 ended by the 1 s gate while frames took 16-24 ms).
  26465c45  one frame over the 1 s gate is a yellow line; the run only stops when 3 frames are over it within 10 s
            (an iPad run was frozen by one frame of 1020 ms).

Not taken: 85da99de (a pause page instead of the stop: new UI in ios/app.m and string tables) and 3fbde57c (command
recordings shared by content, S2Arm #783: host addresses over 10-40 minutes of play), both larger than a start needs.

Patch 0017 is one more S2Arm commit taken the same way, after the first run that drew (13 Nov 16:15) ended on a SIGBUS
whose log had the address only:

  0532b481  a SIGBUS / SIGSEGV report adds one line: read or write (from the ESR), the mapping that holds the address or
            the next one, its bounds, current and maximum protection, tag and share mode (runtime/src/crash.c).

Each patch must be exactly its commits' changes to engine sources. This test compares it with them when an S2Arm
checkout that has the commits is given (S2ARM_UPSTREAM=<path>, as on the machine that wrote the patch) and always checks
the patch's own content. Compiled by s2arm-engine.yml; whether the game needs any of them is only known from a device log.

    python3 -B test/s2arm_upstream_switch2_fixes_test.py
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATCHES = ROOT / 'build-utils/s2arm/engine/patches'
PATCH = PATCHES / '0015-upstream-switch2-pool-addresses-frame-rate-and-gpu-time-gate.patch'
COMMITS = {   # upstream commit -> the engine source it changes (its tests and notes are not taken)
    '240603b6': 'graphics/nvn/gfx/nvn/hle_nvn.c',
    '09e80022': 'graphics/nvn/gfx/nvn/nvn2_codec.c',
    '81f8e8bd': 'graphics/nvn/gfx/nvn/nvn_mtl.m',
    '26465c45': 'graphics/nvn/gfx/nvn/nvn_mtl.m',
}
failures, checks = [], 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        failures.append(message)


def changed(diff):
    """The added and removed lines of a diff, in order, without file headers."""
    return [line for line in diff.splitlines() if line[:1] in '+-' and not line.startswith(('+++', '---'))]


patch = PATCH.read_text(encoding='utf-8') if PATCH.is_file() else ''
check(bool(patch), 'patch 0015 exists')
touched = re.findall(r'^diff --git a/(\S+) b/', patch, re.M)
check(touched == sorted(set(COMMITS.values())), f'patch 0015 touches the three engine sources of the four commits only: {touched}')
added = '\n'.join(line[1:] for line in patch.splitlines() if line.startswith('+') and not line.startswith('+++'))
removed = '\n'.join(line[1:] for line in patch.splitlines() if line.startswith('-') and not line.startswith('---'))

# 240603b6: no window address for a Switch 2 pool.
check('o->gva = o->mem || (o->flags & 0x200) ? gva_alloc((uint64_t)(uintptr_t)o->mem, o->size) : 0;' in removed
      and 'o->gva = !nvn2_on() && (o->mem || (o->flags & 0x200)) ? gva_alloc((uint64_t)(uintptr_t)o->mem, o->size) : 0;' in added,
      'a Switch 2 pool gets no window address (its buffer address is its storage); Switch 1 pools keep theirs')
# 09e80022: the host answers the target frame rate, by name prefix, in the Switch 2 import hook.
check('#define OE_TARGET_RATE "_ZN2nn2oe26SetGraphicsTargetFrameRateE"' in added
      and 'if (!strncmp(name, OE_TARGET_RATE, sizeof OE_TARGET_RATE - 1)) return (void *)oe_target_rate;' in added and 'return RES_OK; }' in added,
      'nn::oe::SetGraphicsTargetFrameRate is taken by the host and answers success')
# 81f8e8bd: exclusive time per queue.
check('static void gpu_tag_done(uint64_t f, int qi, double sub, double g0, double g1) {' in added
      and 'uint64_t from = s0 > prev ? s0 : prev, excl = s1 > from ? s1 - from : 0;' in added
      and 'uint64_t busy = atomic_fetch_add(&g_gpu[k].ns, excl) + excl;' in added,
      "a frame's GPU time adds each submission's own time on its queue")
# 26465c45: one frame over the gate does not stop the run.
check('#define S2A_GPU_OVER_N 3' in added and '#define S2A_GPU_OVER_WINDOW_S 10.0' in added
      and 'int stop = n >= S2A_GPU_OVER_N && at - first <= S2A_GPU_OVER_WINDOW_S;' in added
      and 'if (stop) {' in added and 'mtl_gpu_halt(w); }' in added,
      'the run stops when 3 frames are over the gate within 10 s; a single one is logged')
check('#define S2A_GPU_FRAME_MAX_MS 1000' not in added and '#define S2A_GPU_FRAME_MAX_MS' not in removed, 'the 1 s gate itself is not changed')
check('RewindBox' not in added, 'the patch adds no RewindBox code: the four commits as S2Arm wrote them')

upstream = os.environ.get('S2ARM_UPSTREAM', '')
compared = False
if upstream and Path(upstream, '.git').exists():
    want = []
    for commit, source in COMMITS.items():
        shown = subprocess.run(['git', '-C', upstream, 'show', '--format=', commit[:8], '--', source], capture_output=True, text=True)
        check(shown.returncode == 0 and shown.stdout.strip(), f'S2Arm commit {commit[:8]} is in the checkout given by S2ARM_UPSTREAM')
        want += changed(shown.stdout)
    # 26465c45 rewrites one line 81f8e8bd added: in the combined patch that line appears once, in its final form.
    superseded = [line for line in want if line.startswith('+') and ('-' + line[1:]) in want]
    for line in superseded:
        want.remove(line)
        want.remove('-' + line[1:])
    check(sorted(changed(patch)) == sorted(want),
          f'patch 0015 is exactly the four commits (changed lines differ: {len(set(changed(patch)) ^ set(want))})')
    compared = True

# ---- patch 0017: 0532b481, the crash report names the faulting memory ----
CRASH_PATCH = PATCHES / '0017-upstream-crash-names-the-faulting-memory.patch'
CRASH_COMMIT, CRASH_SOURCE = '0532b481', 'runtime/src/crash.c'
crash = CRASH_PATCH.read_text(encoding='utf-8') if CRASH_PATCH.is_file() else ''
check(bool(crash), 'patch 0017 exists')
check(re.findall(r'^diff --git a/(\S+) b/', crash, re.M) == [CRASH_SOURCE], 'patch 0017 touches runtime/src/crash.c only (the commit\'s own test is not taken)')
crash_added = '\n'.join(line[1:] for line in crash.splitlines() if line.startswith('+') and not line.startswith('+++'))
check('static void fault_region_note(int sig, siginfo_t *si, ucontext_t *uc) {' in crash_added and 'if (sig != SIGBUS && sig != SIGSEGV) return;' in crash_added
      and 'vm_region_recurse_64(mach_task_self(), &r, &sz, &depth, (vm_region_recurse_info_t)&info, &cnt)' in crash_added
      and 'fault_region_note(sig, si, uc);' in crash_added,
      'a SIGBUS / SIGSEGV report asks Mach for the mapping at the faulting address and logs it')
check(not [line for line in crash.splitlines() if line.startswith('-') and not line.startswith('---')], 'patch 0017 removes nothing from the crash report')
check('RewindBox' not in crash_added, 'patch 0017 adds no RewindBox code: the commit as S2Arm wrote it')
if upstream and Path(upstream, '.git').exists():
    shown = subprocess.run(['git', '-C', upstream, 'show', '--format=', CRASH_COMMIT, '--', CRASH_SOURCE], capture_output=True, text=True)
    check(shown.returncode == 0 and shown.stdout.strip(), f'S2Arm commit {CRASH_COMMIT} is in the checkout given by S2ARM_UPSTREAM')
    check(changed(crash) == changed(shown.stdout), 'patch 0017 is exactly the commit\'s change to runtime/src/crash.c')

series = sorted(p.name for p in PATCHES.glob('*.patch'))
check(len(series) >= 17 and series[14] == PATCH.name and series[16] == CRASH_PATCH.name, f'0015 and 0017 are the 15th and 17th engine patches: {series[13:17]}')
notices = (ROOT / 'docs/s2arm-legal-notices.md').read_text(encoding='utf-8')
check(PATCH.name in notices and 'RewindBox patches 0001–0019' in notices and all(c[:8] in notices for c in COMMITS),
      'the legal notices list patch 0015, its four S2Arm commits and the series 0001–0019')
check(CRASH_PATCH.name in notices and CRASH_COMMIT in notices, 'the legal notices list patch 0017 and its S2Arm commit')
readme = (ROOT / 'build-utils/s2arm/engine/README.md').read_text(encoding='utf-8')
check(PATCH.name in readme and all(c[:8] in readme for c in COMMITS), 'the engine README explains patch 0015 with its four commits')
check(CRASH_PATCH.name in readme and CRASH_COMMIT in readme, 'the engine README explains patch 0017 with its commit')
bridge_yml = (ROOT / '.github/workflows/s2arm-bridge-ios.yml').read_text(encoding='utf-8')
check('python3 -B test/s2arm_upstream_switch2_fixes_test.py' in bridge_yml and 'test/s2arm_upstream_switch2_fixes_test.py' in bridge_yml.split('jobs:')[0],
      's2arm-bridge-ios.yml runs this test and is triggered by it')

for failure in failures:
    print('FAIL ' + failure)
print(json.dumps({'result': 'failed' if failures else 'passed', 'checks': checks, 'comparedWithUpstream': compared}))
sys.exit(1 if failures else 0)
