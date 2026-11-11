#!/usr/bin/env python3
"""Host test of REWINDBOX_GATE_BEFORE_LINE_924 on a materialized Core source.

IPA 724 logs (10 November 2026), Call of Duty: Black Ops II (BLES01717, pid 50194, session 8): no frame from window 41
on. FREEZE_DUMP: the main thread waits for a semaphore (3.2 s), the PPU thread Secondary (0.97 core) holds a reservation
on 0x2e208d8 at time 0x83d1ee800 while the word of that line reads 0x83d1ee840 (locked by another thread) on two reads
27 us apart, and the six SPURS kernels are on GETLLAR/PUTLLC of the lines 0x2e20880 and 0x2e20c00. SPUWAIT551 of the
frozen windows: putllc_ok 7.5 and 8.5 million per 5 s (2.0 million in play), putllc_heavy 6.0 and 6.7 million,
getllar_sleep and event_wait 0; PPUGRACE664: 6010 and 6155 windows opened, 8671 and 8768 writer locks deferred for
994 and 1012 ms in total (115 us each). The reservation word does not go backwards: the FREEZE_DUMP line records are
read before the thread records (their ts= are earlier), which is what the build 723 dump showed.

Cause in the source: do_putllc locks its line (rsrv_unique_lock) and then takes vm::writer_lock, whose deferral to a
starving PPU and to the window that PPU opens (CELL571, REWINDBOX_PPU_GRACE_664) ran with the line locked. A PPU
conditional store fails on a locked line (ppu_store_reservation), so a PPU whose next step is on the line the SPUs poll
spent its windows failing it.

Correction: the deferral is made before the line is locked (passive_gate::ahead_scope in do_putllc), and
vm::writer_lock does not defer a second time (defer_writer_once). Same waits, same bound; the reservation time and the
line are validated after the deferral by the same fetch_op and the same comparison under the writer lock. The PPU's
full-line conditional store and do_cell_atomic_128_store keep their order: neither is on the observed path, and
PPUThread.cpp is an input of the PPU cache identity. SPUThread.cpp changes inside do_putllc only (plus one include),
with an exact alias to the delivered effective hash (test/rpcs3_core924_codegen_test.py).

This test checks the source and compiles test/native/rpcs3_gate_line924_model.cpp against the source's gate header:
the line's word while a writer defers (locked before, free after) and a storm on the line the PPU needs, in both
orders. No iPhone, FPS or freeze result is inferred from the model.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / 'test/native/rpcs3_gate_line924_model.cpp'
GATE = 'rpcs3/ios/IOSPassiveLockGate.h'
VM = 'rpcs3/Emu/Memory/vm.cpp'
SPU = 'rpcs3/Emu/Cell/SPUThread.cpp'
PPU = 'rpcs3/Emu/Cell/PPUThread.cpp'


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def read(source: Path, rel: str) -> str:
    return (source / rel).read_bytes().decode('utf-8').replace('\r\n', '\n')


def source_checks(source: Path) -> dict:
    gate = read(source, GATE)
    require('inline thread_local bool deferred_ahead = false;' in gate, 'thread mark')
    scope = gate[gate.index('class ahead_scope'):gate.index('// vm::writer_lock: defers unless')]
    require('explicit ahead_scope(bool active = true) noexcept\n\t\t: m_active(active)\n\t{\n\t\tif (active)\n\t\t{\n'
            '\t\t\tdefer_writer();\n\t\t\tdeferred_ahead = true;\n\t\t}\n\t}' in scope and
            '~ahead_scope()\n\t{\n\t\tif (m_active)\n\t\t{\n\t\t\tdeferred_ahead = false;\n\t\t}\n\t}' in scope and
            'ahead_scope(const ahead_scope&) = delete;' in scope, 'ahead_scope defers once and marks the thread until it ends')
    require('inline void defer_writer_once() noexcept\n{\n\tif (!deferred_ahead)\n\t{\n\t\tdefer_writer();\n\t}\n}' in gate,
            'the writer lock defers unless the caller did')
    # The 571/579/664 gate itself is unchanged.
    require('constexpr std::chrono::microseconds writer_deferral{500};' in gate and
            'constexpr std::chrono::microseconds grace_window{100};' in gate and
            'constexpr std::uint64_t starving_after = 2;' in gate, 'bounds unchanged')

    vm = read(source, VM)
    require(vm.count('rpcs3::ios::passive_gate::defer_writer_once();') == 1 and
            'rpcs3::ios::passive_gate::defer_writer();' not in vm, 'vm::writer_lock uses the once form')
    lock = vm[vm.index('rpcs3::ios::passive_gate::defer_writer_once();') - 200:vm.index('rpcs3::ios::passive_gate::defer_writer_once();')]
    require('if (range_lock)' in lock, 'only writer locks with a range lock defer, as before')

    spu = read(source, SPU)
    require('#include "ios/IOSPassiveLockGate.h"' in spu, 'SPU include')
    putllc = spu[spu.index('bool spu_thread::do_putllc(const spu_mfc_cmd& args)'):spu.index('void do_cell_atomic_128_store(u32 addr, const void* to_write)\n{')]
    ahead = putllc.index('const rpcs3::ios::passive_gate::ahead_scope ios_gate_ahead(accurate);')
    lock_line = putllc.index('r += vm::rsrv_unique_lock;')
    writer = putllc.index('vm::writer_lock lock(addr, range_lock);')
    require(putllc.count('ios_gate_ahead') == 1 and ahead < lock_line < writer, 'PUTLLC defers before locking its line')
    require(putllc.index('if (rtime != res)') < ahead, 'a PUTLLC whose time already changed fails without deferring')
    # The validation after the deferral is the unchanged one.
    require('if ((r & -128) != rtime || (r & 127))\n\t\t\t{\n\t\t\t\treturn false;\n\t\t\t}\n\n\t\t\tr += vm::rsrv_unique_lock;' in putllc[ahead:],
            'the line lock still validates the reservation time')
    require('if (cmp_rdata(rdata, super_data))' in putllc[writer:], 'the store still compares the line under the writer lock')
    # The no-op write-back takes no lock and does not defer.
    require(putllc.index('if (accurate && cmp_rdata(to_write, rdata))') < ahead, 'no-op PUTLLC returns before the deferral')

    # The 128-byte store and the PPU keep their order (and PPUThread.cpp its bytes: it is a PPU cache identity input).
    require(spu.count('ahead_scope') == 1 and 'ahead_scope' not in read(source, PPU) and
            'IOSPassiveLockGate' not in read(source, PPU), 'one site')
    return {'sites': 1}


def run_model(source: Path, cxx: str, sanitize: bool) -> dict:
    with tempfile.TemporaryDirectory(prefix='gate-line924-') as tmp:
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
        require(report['passed'] is True, 'model report')
        require(report['lineWhileDeferring'] == {'before': 64, 'after': 0}, 'the line is locked during the deferral before, free after')
        require(report['storm']['after']['ppuStores'] > report['storm']['before']['ppuStores'], 'the PPU stores more on the polled line')
        return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--cxx', default='g++')
    parser.add_argument('--sanitize', action='store_true')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    report = {'test': 'rpcs3_gate_line924', 'source_checks': source_checks(args.source.resolve()),
              'model': run_model(args.source.resolve(), args.cxx, args.sanitize), 'sanitizers': args.sanitize,
              'iphone_tested': False, 'fps_claimed': False, 'freeze_fix_observed_on_device': False}
    report['result'] = 'passed'
    text = json.dumps(report, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text + '\n')
    print(text)
    print('PASS: REWINDBOX_GATE_BEFORE_LINE_924 source order and host model')


if __name__ == '__main__':
    main()
