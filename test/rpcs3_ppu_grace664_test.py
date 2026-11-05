#!/usr/bin/env python3
"""Host test of REWINDBOX_PPU_GRACE_664 on a materialized Core source.

IPA 662 logs (5 November 2026), Call of Duty: Black Ops II: three stalls of 9-40 s (pids 13140 twice and 13941) with the
signature of 624 and 657. During each, the six SPURS kernels take 1.2-1.6 million heavy PUTLLC writer locks per second
(4.4 s of writer-lock time per 5 s window), and the PPU thread that feeds their job queue (Secondary) is parked on
cpu_flag::memory. Two stalls recovered by themselves after 9-12 s: a starvation, not a lost update. The CELL571/579 gate
lets a starving waiter through once, but cpu_thread::check_state re-parks it at its escape check and the next writer's
cpu_flag::memory parks it again at its next check point.

REWINDBOX_PPU_GRACE_664 (ios/IOSPassiveLockGate.h): when a starving waiter leaves vm::passive_lock, writers keep deferring
for grace_window (100 us) more, within the same writer_deferral bound (500 us), so the PPU runs before the next writer
parks it. Every writer still takes the full writer lock and parks every PPU thread. Setting experimental.ppu_grace,
Automatic on for every title with Passive Lock Fairness (CONFIG_LAYERS levers627 digit 17, COREPROF PPUGRACE664).

This test checks the wiring in the source (gate, setting, policy, levers627, report line) and compiles
test/native/rpcs3_ppu_grace664_model.cpp against the source's gate header: deterministic window checks, then a storm
model (heavy PUTLLC back to back) and a moderate rate with the window off (the Core 660 order) and on. No iPhone, FPS or
stall result is inferred from the model.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / 'test/native/rpcs3_ppu_grace664_model.cpp'
GATE = 'rpcs3/ios/IOSPassiveLockGate.h'
CONFIG = 'rpcs3/Emu/system_config.h'
POLICY_H = 'rpcs3/ios/RPCS3IOSExperimentalPolicy.h'
POLICY = 'rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp'
SETTINGS = 'rpcs3/ios/RPCS3IOSSettings.cpp'
SYSTEM = 'rpcs3/Emu/System.cpp'
BOOT = 'rpcs3/ios/RPCS3IOSBootDiagnostics.h'
PERF = 'rpcs3/ios/RPCS3IOSPerformance.cpp'


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def read(source: Path, rel: str) -> str:
    return (source / rel).read_bytes().decode('utf-8').replace('\r\n', '\n')


def source_checks(source: Path) -> dict:
    gate = read(source, GATE)
    require(gate.count('REWINDBOX_PPU_GRACE_664') >= 3, 'gate markers')
    require('constexpr std::chrono::microseconds grace_window{100};' in gate, 'grace window is 100 us')
    require('constexpr std::chrono::microseconds writer_deferral{500};' in gate, 'the 571 deferral bound is unchanged')
    require('constexpr std::uint64_t starving_after = 2;' in gate, 'the 571 starving threshold is unchanged')
    require('inline std::atomic<bool> grace_enabled{false};' in gate and 'inline std::atomic<std::int64_t> grace_until{0};' in gate,
            'grace state defaults off')
    dtor = gate[gate.index('\t~waiter_mark()'):gate.index('};', gate.index('\t~waiter_mark()'))]
    require(dtor.index('grace_until.compare_exchange_weak') < dtor.index('starving.fetch_sub(1'), 'the window opens before the mark drops')
    require('if (grace_enabled.load(std::memory_order_relaxed))' in dtor, 'the window opens only when enabled')
    defer = gate[gate.index('inline bool defer_writer() noexcept'):]
    require('if (!seen && (!grace || grace <= steady_now_ns()))\n\t{\n\t\treturn false;\n\t}' in defer, 'no deferral without a window')
    require('for (auto now = start; now < stop; now = std::chrono::steady_clock::now())' in defer and
            'const auto stop = start + writer_deferral;' in defer, 'the deferral keeps its bound')
    require('if (!seen && !in_grace)\n\t\t{\n\t\t\tbreak;\n\t\t}' in defer, 'the deferral ends with the window')
    # Review of 5 November: a thread's own window does not hold its own writer locks (a PPU's stwcx right after its
    # starving wait), and the wake-up is passed on when a writer leaves, not after each sleep (no chain during a window).
    require('inline thread_local std::int64_t own_grace_until = 0;' in gate and dtor.index('own_grace_until = until;') <
            dtor.index('grace_until.compare_exchange_weak'), 'the opener records its own window')
    require('if (!seen && grace <= own)\n\t{\n\t\treturn false;\n\t}' in defer and
            'const bool in_grace = grace > now_ns && grace > own;' in defer, 'an own window holds nobody back')
    loop = defer[defer.index('\tfor (auto now = start; now < stop;'):defer.index('\t// CELL579_GATE_SLEEP: pass the last starving')]
    require('wake_one(' not in loop and 'wake_all(' not in loop, 'no wake-up from inside the deferral loop')
    tail = defer[defer.index('\t// CELL579_GATE_SLEEP: pass the last starving'):]
    require('if (slept && !starving.load(std::memory_order_seq_cst) && sleepers.load(std::memory_order_seq_cst))\n\t{\n'
            '\t\tif (windowed)\n\t\t{\n\t\t\twake_all(starving);\n\t\t}\n\t\telse\n\t\t{\n\t\t\twake_one(starving);\n\t\t}' in tail,
            'the exit pass-on: every sleeper after a window, one by one otherwise')
    require('os_sync_wake_by_address_all(&word, sizeof(std::uint32_t), OS_SYNC_WAKE_BY_ADDRESS_NONE);' in gate and
            'syscall(SYS_futex, &word, FUTEX_WAKE_PRIVATE, 0x7fffffff, nullptr, nullptr, 0);' in gate, 'wake_all on Apple and Linux')

    config = read(source, CONFIG)
    require('cfg::_enum<ios_experimental_mode> ppu_grace{ this, "PPU Grace After Starvation", ios_experimental_mode::automatic };' in config,
            'setting')
    require('bool ppu_grace = false;' in read(source, POLICY_H), 'policy field')
    policy = read(source, POLICY)
    require('resolved.ppu_grace = resolved.passive_lock_fairness && resolve_mode(g_cfg.ios_experimental.ppu_grace, true);' in policy,
            'Automatic is every title, with the gate')
    require(policy.index('rpcs3::ios::passive_gate::grace_until.store(0, std::memory_order_relaxed);') <
            policy.index('rpcs3::ios::passive_gate::grace_enabled.store(resolved.ppu_grace, std::memory_order_relaxed);'),
            'the window resets before it is enabled')
    require('Resolved title policy 664: ppu_grace=%d' in policy, 'resolved policy line')
    settings = read(source, SETTINGS)
    require(settings.count('GAME_SETTING("experimental.ppu_grace", "Experimental"') == 1 and
            'g_cfg.ios_experimental.ppu_grace, 0, 0, 0)' in settings, 'catalogue entry')
    system = read(source, SYSTEM)
    require(re.search(r'ios_add_lever\(ios_levers\.zcull_depth_guard, ios_lever_settings\.zcull_depth_guard\);\n'
                      r'\t+// Core 664: digit 17 of levers627=\.\n'
                      r'\t+ios_add_lever\(ios_levers\.ppu_grace, ios_lever_settings\.ppu_grace\);\n\t+ios_rsx\.levers627 = ios_levers627;',
                      system), 'levers627 digit 17')
    require('append_text(line, "levers627", rsx.levers627, 17);' in read(source, BOOT), 'CONFIG_LAYERS carries 17 digits')
    perf = read(source, PERF)
    require('#include "ios/IOSPassiveLockGate.h"' in perf and '"COREPROF PPUGRACE664 session=%llu window=%llu enabled=%d' in perf and
            'gate::grace_opened.exchange(0' in perf, 'COREPROF PPUGRACE664 report')
    return {'grace_window_us': 100, 'writer_deferral_us': 500, 'levers627_digits': 17}


def run_model(source: Path, cxx: str, sanitize: bool) -> dict:
    with tempfile.TemporaryDirectory(prefix='ppu-grace664-') as tmp:
        binary = Path(tmp) / 'model'
        flags = ['-std=c++20', '-Wall', '-Wextra', '-pthread', '-I', str(source / 'rpcs3')]
        flags += ['-O1', '-g', '-fsanitize=address,undefined', '-fno-sanitize-recover=undefined'] if sanitize else ['-O2']
        build = subprocess.run([cxx, *flags, str(MODEL), '-o', str(binary)], capture_output=True, text=True)
        require(build.returncode == 0, 'model build failed:\n' + build.stderr[-4000:])
        env = {'UBSAN_OPTIONS': 'halt_on_error=1:print_stacktrace=1'}
        if sanitize:
            env['ASAN_OPTIONS'] = ('detect_leaks=1:' if sys.platform.startswith('linux') else '') + 'abort_on_error=1'
        result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=600, env=env)
        require(result.returncode == 0, f'model failed ({result.returncode}):\n' + result.stderr[-4000:])
        report = json.loads(result.stdout)
        require(report['passed'] is True and report['windowUs'] == 100 and report['writerDeferralUs'] == 500, 'model report')
        require(report['storm']['on']['ppuShare'] >= report['storm']['off']['ppuShare'], 'the window costs the starving PPU progress')
        return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--cxx', default='g++')
    parser.add_argument('--sanitize', action='store_true')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    report = {'test': 'rpcs3_ppu_grace664', 'source_checks': source_checks(args.source.resolve()),
              'model': run_model(args.source.resolve(), args.cxx, args.sanitize), 'sanitizers': args.sanitize,
              'iphone_tested': False, 'fps_claimed': False}
    report['result'] = 'passed'
    text = json.dumps(report, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text + '\n')
    print(text)
    print('PASS: REWINDBOX_PPU_GRACE_664 wiring and host model')


if __name__ == '__main__':
    main()
