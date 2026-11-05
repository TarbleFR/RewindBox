#!/usr/bin/env python3
"""Host test of REWINDBOX_THREAD_ORCHESTRATOR_665 on a materialized Core source.

Scheduling and measurement only: the PPU threads start one relative step above the default USER_INTERACTIVE priority (-1 against -2 with the RSX thread priority lever, at most 0), below the RSX and audio threads, rate-limited
samples (one per ms per thread) record the CPU and QoS class of PPU, SPU and RSX threads, and vm::writer_lock times its wait
for every PPU thread to park. Setting experimental.thread_orchestrator (levers627 digit 18, COREPROF PLACEMENT665).
Disabled is Core 664. Checks the wiring in the source and builds/runs test/native/rpcs3_thread_orchestrator665_unit.cpp
against the source's header. No iPhone, FPS or stall result is inferred.
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
UNIT = ROOT / 'test/native/rpcs3_thread_orchestrator665_unit.cpp'
HDR = 'rpcs3/ios/IOSThreadOrchestrator.h'
MARKER = 'REWINDBOX_THREAD_ORCHESTRATOR_665'


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def read(source: Path, rel: str) -> str:
    return (source / rel).read_bytes().decode('utf-8').replace('\r\n', '\n')


def source_checks(source: Path) -> dict:
    require((source / HDR).is_file(), 'missing ' + HDR)
    hdr = read(source, HDR)
    require(MARKER in hdr, 'header marker')
    require('constexpr assignment qos_for(cls c, const policy& p) noexcept' in hdr, 'qos_for')
    require('if (!p.enabled || c != cls::ppu)\n\t{\n\t\treturn {};\n\t}' in hdr and
            'const int above_default = p.default_relative_priority + 1;\n\treturn {qos_user_interactive, above_default < 0 ? above_default : 0};' in hdr,
            'only the PPU, one relative step above the default, at most 0')
    require('inline thread_local std::uint64_t next_due = 0;' in hdr and 'if (now < next_due)' in hdr, 'thread_local rate limiter')
    require('pthread_cpu_number_np' in hdr and 'sched_getcpu' in hdr and 'qos_class_self()' in hdr, 'cpu and qos reads')
    require('if (!enabled.load(std::memory_order_relaxed))\n\t{\n\t\treturn;\n\t}' in hdr, 'sample is off while disabled')

    config = read(source, 'rpcs3/Emu/system_config.h')
    require('cfg::_enum<ios_experimental_mode> thread_orchestrator{ this, "Thread Orchestrator", ios_experimental_mode::automatic };' in config,
            'setting')
    require('bool thread_orchestrator = false;' in read(source, 'rpcs3/ios/RPCS3IOSExperimentalPolicy.h'), 'policy field')
    policy = read(source, 'rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp')
    require('resolved.thread_orchestrator = resolve_mode(g_cfg.ios_experimental.thread_orchestrator, true);' in policy, 'resolve')
    require('orchestrator::enabled.store(resolved.thread_orchestrator, std::memory_order_relaxed);' in policy, 'enabled follows the policy')
    require('"Resolved title policy 665: thread_orchestrator=%d ppu_qos=%d ppu_rel=%d perflevel0_cpus=%u perflevel1_cpus=%u"' in policy and
            'hw.perflevel0.logicalcpu' in policy and 'hw.perflevel1.logicalcpu' in policy, 'boot line')
    settings = read(source, 'rpcs3/ios/RPCS3IOSSettings.cpp')
    require(settings.count('GAME_SETTING("experimental.thread_orchestrator", "Experimental"') == 1 and
            'g_cfg.ios_experimental.thread_orchestrator, 0, 0, 0)' in settings, 'catalogue entry')
    require(re.search(r'ios_add_lever\(ios_levers\.ppu_grace, ios_lever_settings\.ppu_grace\);\n\t+// Core 665: digit 18 of levers627=\.\n'
                      r'\t+ios_add_lever\(ios_levers\.thread_orchestrator, ios_lever_settings\.thread_orchestrator\);\n\t+ios_rsx\.levers627 = ios_levers627;',
                      read(source, 'rpcs3/Emu/System.cpp')), 'levers627 digit 18')
    require('append_text(line, "levers627", rsx.levers627, 18);' in read(source, 'rpcs3/ios/RPCS3IOSBootDiagnostics.h'), 'CONFIG_LAYERS carries 18 digits')

    cpu = read(source, 'rpcs3/Emu/CPU/CPUThread.cpp')
    require('#include "ios/IOSThreadOrchestrator.h"' in cpu, 'CPUThread include')
    require('if (rpcs3::ios::get_experimental_policy().thread_orchestrator)' in cpu and
            'rpcs3::ios::orchestrator::apply_to_current_thread(rpcs3::ios::orchestrator::qos_for(cls,\n\t\t\t{true, rpcs3::ios::thread_qos::default_relative_priority.load(std::memory_order_relaxed)}));' in cpu, 'start-up assignment only when enabled')
    require(cpu.index('spu_native_priority);') < cpu.index('orchestrator::apply_to_current_thread'), 'after the 627 SPU code')
    chk = cpu[cpu.index('bool cpu_thread::check_state() noexcept'):]
    require('rpcs3::ios::orchestrator::sample(' in chk[:600], 'check_state sample')
    vm = read(source, 'rpcs3/Emu/Memory/vm.cpp')
    require(vm.count('rpcs3::ios::orchestrator::sample(') == 2, 'passive_lock and writer_lock samples')
    require('record_writer_suspend(' in vm and 'const u64 suspend_begin = rpcs3::ios::orchestrator::enabled.load' in vm and
            'const u64 ppu_wait_begin = suspend_begin ? utils::get_tsc() : 0;' in vm, 'writer-lock suspend timing')
    require(vm.index('const u64 suspend_begin') < vm.index('reservation_lock_wait(wait_iteration);') <
            vm.index('const u64 ppu_wait_begin') <
            vm.index('for (u64 wait_iteration = 0; !(ptr->state & cpu_flag::wait); wait_iteration++)') < vm.index('record_writer_suspend('),
            'park timing spans the wait for every PPU thread')
    rsx = read(source, 'rpcs3/Emu/RSX/RSXThread.cpp')
    require('orchestrator::sample(rpcs3::ios::orchestrator::cls::rsx);' in rsx and '#include "ios/IOSThreadOrchestrator.h"' in rsx, 'RSX FIFO loop sample')
    require(rsx.index('orchestrator::sample(rpcs3::ios::orchestrator::cls::rsx);') < rsx.index('\t\t\trun_FIFO();\n\t\t}\n\t}\n\n\tvoid thread::on_exit()'), 'sample before run_FIFO')
    perf = read(source, 'rpcs3/ios/RPCS3IOSPerformance.cpp')
    require('COREPROF PPUGRACE664' in perf and perf.index('COREPROF PPUGRACE664') < perf.index('COREPROF PLACEMENT665'), 'report follows PPUGRACE664')
    require('"COREPROF PLACEMENT665 session=%llu window=%llu enabled=%d class=%s samples=%llu cpu=%s qos=%s "' in perf and
            '"wl_suspends=%llu wl_suspend_ms=%.3f wl_ppu_wait_ms=%.3f wl_slow_ppu_waits=%llu wl_slow_ppu_wait_ms=%.3f "' in perf and 'orch::take_writer()' in perf, 'report line')
    return {'levers627_digits': 18, 'sample_interval_ms': 1, 'slow_park_us': 50}


def run_unit(source: Path, cxx: str, sanitize: bool) -> str:
    with tempfile.TemporaryDirectory(prefix='orchestrator665-') as tmp:
        binary = Path(tmp) / 'unit'
        flags = ['-std=c++20', '-Wall', '-Wextra', '-Werror', '-pthread', '-I', str(source / 'rpcs3')]
        flags += ['-O1', '-g', '-fsanitize=address,undefined', '-fno-sanitize-recover=all'] if sanitize else ['-O2']
        build = subprocess.run([cxx, *flags, str(UNIT), '-o', str(binary)], capture_output=True, text=True)
        require(build.returncode == 0, 'unit build failed:\n' + build.stderr[-4000:])
        env = {'UBSAN_OPTIONS': 'halt_on_error=1:print_stacktrace=1', 'ASAN_OPTIONS': 'abort_on_error=1'}
        result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=300, env=env)
        require(result.returncode == 0, f'unit failed ({result.returncode}):\n' + result.stderr[-4000:])
        return result.stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--cxx', default='g++')
    parser.add_argument('--sanitize', action='store_true')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    report = {'test': 'rpcs3_thread_orchestrator665', 'source_checks': source_checks(source),
              'unit': run_unit(source, args.cxx, args.sanitize), 'sanitizers': args.sanitize,
              'iphone_tested': False, 'fps_claimed': False, 'result': 'passed'}
    text = json.dumps(report, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text + '\n')
    print(text)
    print('PASS: REWINDBOX_THREAD_ORCHESTRATOR_665 wiring and host unit')


if __name__ == '__main__':
    main()
