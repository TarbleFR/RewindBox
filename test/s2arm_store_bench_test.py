#!/usr/bin/env python3
"""Patch 0011: the engine's store emulation self-test is skipped while a debugger is attached (plain python3).

Mario Kart World on IPA 731 (12 Nov): after "start passed" the engine asked for no code page for 10 minutes, then for
main's 42 MB 49 ms after RewindBox's JIT helper detached. crash.c s2a_emul_store_bench, run once at the first thread's
fault set-up, writes 2000 times to a read-only page: each fault stops the process for an attached debugger. The test
is a measurement (one log line), so under a debugger it is skipped. The patch is compiled by s2arm-engine.yml.

    python3 -B test/s2arm_store_bench_test.py
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / 'build-utils/s2arm/engine/patches/0011-guest-skip-the-store-emulation-self-test-under-a-debugger.patch'
failures, checks = [], 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        failures.append(message)


patch = PATCH.read_text(encoding='utf-8') if PATCH.is_file() else ''
check(bool(patch), 'patch 0011 exists')
check(re.findall(r'^diff --git a/(\S+) b/', patch, re.M) == ['runtime/src/crash.c'], 'patch 0011 touches crash.c only')
added = [line[1:] for line in patch.splitlines() if line.startswith('+') and not line.startswith('+++')]
removed = [line for line in patch.splitlines() if line.startswith('-') and not line.startswith('---')]
check(not removed, 'patch 0011 removes nothing from the engine')
body = '\n'.join(added)
check('#include <sys/sysctl.h>' in body, 'P_TRACED comes from sysctl kern.proc.pid, as boot.c reads it')
check('KERN_PROC_PID, getpid()' in body and '(kp.kp_proc.p_flag & P_TRACED)' in body and 'return; }' in body,
      'the self-test returns before its faults when the process is traced')
check('RewindBox (patch 0011)' in body, 'the change is marked RewindBox (patch 0011)')
# The early return sits right after the S2A_TRACK_EMUL_STORE check, before the test page is mapped.
bench = patch[patch.index(' void s2a_emul_store_bench(void) {\n'):] if ' void s2a_emul_store_bench(void) {\n' in patch else ''
at = [bench.find(part) for part in ('getenv("S2A_TRACK_EMUL_STORE")', '(kp.kp_proc.p_flag & P_TRACED)', 'mmap(NULL, 0x4000')]
check(min(at) >= 0 and at == sorted(at), 'the debugger check comes before the test page and its 2000 faults')
series = sorted(p.name for p in (ROOT / 'build-utils/s2arm/engine/patches').glob('*.patch'))
check(len(series) >= 11 and series[10] == PATCH.name, f'0011 is the 11th engine patch: {series[9:12]}')
notices = (ROOT / 'docs/s2arm-legal-notices.md').read_text(encoding='utf-8')
check(PATCH.name in notices, 'the legal notices list patch 0011')

for failure in failures:
    print('FAIL ' + failure)
print(json.dumps({'result': 'failed' if failures else 'passed', 'checks': checks}))
sys.exit(1 if failures else 0)
