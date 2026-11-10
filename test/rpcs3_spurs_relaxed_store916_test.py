#!/usr/bin/env python3
"""REWINDBOX_SPURS_RELAXED_STORE_916, executed: a PUTLLC on a SPURS header never overwrites a plain guest store.

Build 718, Assassin's Creed (BLES00158, Accurate SPU Reservations off), PID 45272, session 3: after the request to
leave the game its main thread waited 6.125 s for the shutdown of a SPURS workload, until the stop limit ended the
game. In the stall dump the second header line holds the shutdown state and sysSrvMsgUpdateWorkload = 0xff, but the
plain byte store of sysSrvMessage = 0xff that the PPU makes next is not in the first header line (0xe0), and the five
SPURS kernels wait on that line with its current reservation time. With relaxed reservations the PUTLLC of a SPURS
header copied the SPU's whole 128-byte line into memory once the reservation time was unchanged: a plain store made
between GETLLAR and PUTLLC (it does not advance that time) was overwritten.

The driver compiles the real rpcs3/ios/IOSSpursRelaxedStore.h in test/native/rpcs3_spurs_relaxed_store916_test.cpp:
10 ordered scenarios on the dumped line (the store before the PUTLLC, into an untouched lane, into the first and
into a later changed lane while the line is stored, twice, onto the SPU's own byte, a two-byte store of which one
byte keeps its value, three changed lanes) and one concurrent run (two plain-store writers beside five
GETLLAR/PUTLLC threads on both lanes; every successful SPU increment and no other, and every guest store, must be
in memory). A PUTLLC that a guest store interrupts fails and gives back what it had stored: the line is what
GETLLAR read plus the guest's stores. Negative controls: the same harness with the previous store
(-DCONTROL_OLD_STORE) must lose the store, and with the first form of this correction (-DCONTROL_BYTE_MERGE, which
kept the store beside the SPU's bytes) must split the two-byte store. Static: do_putllc calls the store on the
relaxed SPURS path, releases the unique lock on every outcome, advances the reservation time whenever memory was
written and keeps no unconditional copy of the line on iOS.
Host behaviour only: nothing here measures an iPhone.

    python3 test/rpcs3_spurs_relaxed_store916_test.py --source CORE [--cxx g++] [--no-sanitizers] [--report OUT.json]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / 'test/native/rpcs3_spurs_relaxed_store916_test.cpp'
SPU = 'rpcs3/Emu/Cell/SPUThread.cpp'
HEADER = 'rpcs3/ios/IOSSpursRelaxedStore.h'


def require(condition, message):
    if not condition:
        raise SystemExit('FAIL: ' + message)


def static_checks(source: Path) -> None:
    text = (source / SPU).read_text('utf-8', 'surrogateescape').replace('\r\n', '\n')
    start = text.index('bool spu_thread::do_putllc(const spu_mfc_cmd& args)')
    body = text[start:text.index('void do_cell_atomic_128_store', start)]
    begin = body.index('\t\t\tif (relaxed_spurs)\n')
    branch = body[begin:body.index('\t\t\t}\n\t\t}\n', begin)]
    require(branch.count('#ifdef RPCS3_IOS') == 1 and branch.count('#else') == 1 and branch.count('#endif') == 1, 'one iOS branch on the relaxed SPURS path')
    ios, other = branch[branch.index('#ifdef RPCS3_IOS'):branch.index('#else')], branch[branch.index('#else'):branch.index('#endif')]
    require('rpcs3::ios::spurs_relaxed_store::store(vm::_ptr<unsigned char>(addr)' in ios and 'mov_rdata' not in ios,
            'iOS stores the line through the lane store, never by a copy of the whole line')
    require('atomic_storage<u128>::compare_exchange(*reinterpret_cast<u128*>(lane), comp, exch)' in ios, 'each lane is one atomic exchange')
    require("res += ios_spurs_result == rpcs3::ios::spurs_relaxed_store::result::refused_changed ? 0 - 64 : 64;" in ios,
            'the unique lock is released on every outcome; the time stays only when nothing was written')
    require("if (ios_spurs_result == rpcs3::ios::spurs_relaxed_store::result::refused_undone)\n\t\t\t\t{\n\t\t\t\t\tvm::reservation_notifier_notify(addr, rtime);" in ios and
            "return ios_spurs_result == rpcs3::ios::spurs_relaxed_store::result::stored;" in ios,
            'a store that was taken back tells the waiters and fails the PUTLLC')
    require('mov_rdata(*vm::_ptr<spu_rdata_t>(addr), to_write);\n\t\t\t\tres += 64;\n\t\t\t\treturn true;' in other, 'the upstream path is kept for other platforms')
    require(body.index('auto [_oldd, _ok] = res.fetch_op(') < body.index('if (relaxed_spurs)\n'), 'the store runs under the unique lock of the reservation word')
    require('const bool relaxed_spurs = !accurate && addr - spurs_addr <= 0x80;' in body, 'the scope is the two SPURS header lines with relaxed reservations')
    require(text.count('#include "ios/IOSSpursRelaxedStore.h"') == 1, 'the include')
    header = (source / HEADER).read_text()
    require('std::memcmp(memory, getllar, line_bytes) != 0' in header and 'if (!written)' in header, 'the header compares the line and refuses before any write')
    require('return result::refused_undone;' in header and 'stored_merged' not in header, 'an interrupted store is taken back, never merged')


def build(cxx: str, source: Path, folder: Path, name: str, flags: list) -> Path:
    binary = folder / name
    machine = ['-mcx16'] if platform.machine() in ('x86_64', 'AMD64') else []
    command = [cxx, '-std=c++20', *machine, *flags, '-I', str(source / 'rpcs3'), str(HARNESS), '-o', str(binary), '-pthread']
    result = subprocess.run(command, capture_output=True, text=True)
    require(result.returncode == 0, name + ' does not build:\n' + result.stderr[-3000:])
    return binary


def run(binary: Path, *arguments: str) -> dict:
    result = subprocess.run([str(binary), *arguments], capture_output=True, text=True, timeout=900)
    lines = result.stdout.strip().splitlines()
    report = json.loads(lines[-1]) if lines and lines[-1].startswith('{') else {'failures': -1}
    report.update(returncode=result.returncode, output=[line for line in lines[:-1]][-12:])
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--cxx', default='g++')
    parser.add_argument('--no-sanitizers', action='store_true')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    static_checks(source)
    plain = ['-O2', '-Wall', '-Wextra', '-Werror']
    report: dict = {'cxx': args.cxx}
    with tempfile.TemporaryDirectory(prefix='spurs916-') as temporary:
        folder = Path(temporary)
        result = run(build(args.cxx, source, folder, 'plain', plain))
        require(result['returncode'] == 0 and result['failures'] == 0 and result['checks'] == 19, 'the lane store: ' + repr(result))
        report['plain'] = result
        if not args.no_sanitizers and sys.platform.startswith('linux'):
            result = run(build(args.cxx, source, folder, 'asan', ['-O1', '-g', '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
                                                                  '-fno-sanitize-recover=undefined']))
            require(result['returncode'] == 0 and result['failures'] == 0, 'asan: ' + repr(result))
            report['asan'] = result
        binary = build(args.cxx, source, folder, 'control', plain + ['-DCONTROL_OLD_STORE'])
        control = run(binary, '--deterministic')
        lost = [line for line in control['output'] if "sysSrvMessage store made between GETLLAR and PUTLLC" in line]
        require(control['returncode'] != 0 and control['failures'] >= 6 and lost, 'the previous store must lose the guest store: ' + repr(control))
        report['control_previous_store'] = control
        concurrent = run(binary)
        counted = [line for line in concurrent['output'] if line.startswith('concurrent:') and 'lost_guest_stores=0 ' not in line]
        require(concurrent['returncode'] != 0 and counted, 'the previous store must lose guest stores in the concurrent run: ' + repr(concurrent))
        report['control_previous_store_concurrent'] = concurrent
        merge = run(build(args.cxx, source, folder, 'control_merge', plain + ['-DCONTROL_BYTE_MERGE']), '--deterministic')
        split = [line for line in merge['output'] if 'a two-byte guest store is never split' in line]
        require(merge['returncode'] != 0 and split, 'the byte merge must split the two-byte store: ' + repr(merge))
        report['control_byte_merge'] = merge
    print('PASS: a PUTLLC on a SPURS header keeps every plain guest store (%d checks; the previous store fails %d of the ordered checks, '
          'the byte merge %d)' % (report['plain']['checks'], report['control_previous_store']['failures'], report['control_byte_merge']['failures']))
    for name in ('plain', 'control_previous_store_concurrent'):
        for line in report[name]['output']:
            if line.startswith('concurrent:'):
                print('      %s: %s' % (name, line))
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
