#!/usr/bin/env python3
"""REWINDBOX_SPU_NOOP_SPIN_ACCURATE_911, executed: the bounded wait of a polling SPU thread on the accurate path.

Black Ops II (BLES01717) runs with Accurate SPU Reservations (database configuration; CONFIG_LAYERS accurate_res=true
on builds 676 and 694). There the write-back of unchanged data completes in the CELL565 block of
spu_thread::do_putllc and never reached the wait of REWINDBOX_SPU_NOOP_SPIN_WAIT_627, which sits in the relaxed-only
branch at the top of the function: build 676, PID 25658, session 3, windows 4-8 (60 FPS menus): 53-102 million
completed PUTLLC per 5 s window, 35,692-371,177 of them changing data, SPU threads on 4.0-5.0 cores, getllar_sleep=0.

The driver runs the real block (extracted from SPUThread.cpp) in the harness of the Core 627 test
(test/rpcs3_core627/spin_wait_test.cpp: mocks of the reservation word, the notifier, the wait journal and the clock;
13 scenarios: streak threshold, bounds doubling to the cap, rearm spacing, a line that already changed, a wait that
ends early, the notifier that cannot start, several lines, policy off...). Negative controls: the block without the
reservation-time condition, and with the completion flag false, must fail scenarios.
Static: the flag is set only where the CELL565 comparison succeeded; the wait starts after the comparison scope (the
RSX reservation lock is released); a PUTLLC that changes data still restarts the streak; the relaxed block of 627 is
unchanged; process_mfc_cmd is untouched (the tracker stays a thread_local of SPUThread.cpp).
Host behaviour only: no iPhone CPU, FPS or thermal result is inferred.

    python3 test/rpcs3_spu_noop_spin_accurate911_test.py --source CORE [--cxx g++] [--no-sanitizers] [--report OUT.json]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / 'test/rpcs3_core627/spin_wait_test.cpp'
SPU = 'rpcs3/Emu/Cell/SPUThread.cpp'
BEGIN = '\t\tif (ios_accurate_noop && rpcs3::ios::get_experimental_policy().spu_noop_spin_wait)\n'
END = '\t\t// REWINDBOX_SPU_NOOP_SPIN_ACCURATE_911 end\n'
INCLUDE = '#include "spin_block.inc"\n'


def require(condition, message):
    if not condition:
        raise SystemExit('FAIL: ' + message)


def block(text: str) -> str:
    require(text.count(BEGIN) == 1 and text.count(END) == 1, 'the 911 block markers')
    return text[text.index(BEGIN):text.index(END)]


def static_checks(text: str) -> None:
    start = text.index('bool spu_thread::do_putllc(const spu_mfc_cmd& args)')
    body = text[start:text.index('bool spu_thread::do_putlluc', start) if 'bool spu_thread::do_putlluc' in text[start:] else start + 20000]
    flag = '\t\t\t\t\tios_accurate_noop = true; // REWINDBOX_SPU_NOOP_SPIN_ACCURATE_911\n\t\t\t\t\traddr = 0; // Disable notification\n\t\t\t\t\treturn true;'
    compare = ('if (cmp_rdata(rdata, vm::_ref<spu_rdata_t>(addr)) && rdata_fence() && res == rtime && '
               'cmp_rdata(rdata, vm::_ref<spu_rdata_t>(addr)) && rdata_fence() && res == rtime)\n\t\t\t\t{\n')
    require(body.count('ios_accurate_noop = true;') == 1 and compare + flag in body, 'the flag is set only where the CELL565 comparison succeeded')
    require(body.index('bool ios_accurate_noop = false;') < body.index('if ([&]()\n') < body.index('rsx::reservation_lock rsx_lock(addr, 128);') <
            body.index(flag) < body.index('\t}())\n\t{\n') < body.index(BEGIN), 'the wait starts after the comparison scope')
    require('\t\tif (!(accurate && cmp_rdata(to_write, rdata)))\n\t\t{\n\t\t\tt_ios_noop_spin.on_progress();\n\t\t}\n' in body,
            'a PUTLLC that changes data restarts the streak; a no-op write-back does not')
    relaxed = body[body.index('const bool unchanged = !accurate && cmp_rdata(to_write, rdata);'):body.index('#endif\n\t\t\traddr = 0;\n\t\t\treturn true;')]
    require(relaxed.count('t_ios_noop_spin.on_noop(') == 1 and 'if (rpcs3::ios::get_experimental_policy().spu_noop_spin_wait)' in relaxed,
            'the relaxed block of 627')
    new = block(text)
    old = relaxed[relaxed.index('static const u64 s_ios_noop_gap_ticks'):]
    squash = lambda value: ''.join(value.split())
    require(squash(old[:old.rindex('}')]) in squash(new), 'the accurate block uses the same tracker calls and the same wait as the 627 block')
    require(text.count('REWINDBOX_SPU_NOOP_SPIN_ACCURATE_911') >= 5, 'markers')


def build(cxx: str, source: Path, folder: Path, name: str, flags: list) -> Path:
    binary = folder / name
    command = [cxx, '-std=c++20', *flags, '-I', str(source / 'rpcs3'), '-I', str(folder), str(folder / 'harness.cpp'), '-o', str(binary), '-pthread']
    result = subprocess.run(command, capture_output=True, text=True)
    require(result.returncode == 0, name + ' does not build:\n' + result.stderr[-3000:])
    return binary


def run(binary: Path) -> dict:
    result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=600)
    lines = result.stdout.strip().splitlines()
    report = json.loads(lines[-1]) if lines and lines[-1].startswith('{') else {'failures': -1}
    report['returncode'] = result.returncode
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--cxx', default='g++')
    parser.add_argument('--no-sanitizers', action='store_true')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    text = (source / SPU).read_text('utf-8', 'surrogateescape').replace('\r\n', '\n')
    static_checks(text)
    harness = HARNESS.read_text()
    require(harness.count(INCLUDE) == 1, 'the harness include')
    plain = ['-O2', '-Wall', '-Wextra', '-Werror', '-Wno-missing-field-initializers']
    report: dict = {'cxx': args.cxx}
    with tempfile.TemporaryDirectory(prefix='noop911-') as temporary:
        def variant(name: str, code: str, flag: str = 'true') -> Path:
            folder = Path(temporary) / name
            folder.mkdir()
            (folder / 'spin_block911.inc').write_text(code, 'utf-8', 'surrogateescape')
            (folder / 'harness.cpp').write_text(harness.replace(INCLUDE, f'\t\tconst bool ios_accurate_noop = {flag};\n#include "spin_block911.inc"\n'))
            return folder
        real = variant('real', block(text))
        result = run(build(args.cxx, source, real, 'plain', plain))
        require(result['returncode'] == 0 and result['failures'] == 0 and result['scenarios'] == 13, 'the accurate polling block: ' + repr(result))
        report['plain'] = result
        if not args.no_sanitizers and sys.platform.startswith('linux'):
            for name, flags in (('tsan', ['-O1', '-g', '-fsanitize=thread']),
                                ('asan', ['-O1', '-g', '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-fno-sanitize-recover=undefined'])):
                result = run(build(args.cxx, source, real, name, flags))
                require(result['returncode'] == 0 and result['failures'] == 0, name + ': ' + repr(result))
                report[name] = result
        controls = {}
        condition = ' && vm::reservation_acquire(addr) == rtime'
        require(block(text).count(condition) == 1, 'the reservation-time condition')
        for name, code, flag in (('no_reservation_time_condition', block(text).replace(condition, ''), 'true'),
                                 ('completion_flag_false', block(text), 'false')):
            result = run(build(args.cxx, source, variant(name, code, flag), 'plain', [f for f in plain if f != '-Werror']))
            require(result['failures'] > 0, f'negative control {name}: no scenario fails')
            controls[name] = result['failures']
            print(f'negative control {name}: {result["failures"]} failed checks')
        report['negative_controls'] = controls
    report['result'] = 'passed'
    print('PASS: on the accurate path a polling SPU thread waits as in 627 (13 scenarios on the real block; the wait starts after '
          'the CELL565 comparison completed and its scope ended; data changes restart the streak); negative controls fail')
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
