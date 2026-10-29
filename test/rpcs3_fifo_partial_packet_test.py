#!/usr/bin/env python3
"""Execute the real FIFO cache/read/GET methods on partially published packets.

Guest RAM, I/O translation, reservations and CPU wait/recovery callbacks are
explicit host adapters. Both the delivered594 baseline and candidate bodies
are compiled. Baseline failures use a defined sentinel, never undefined C++.
No GPU, game, complete savestate serialization or concurrent memory ordering
is tested, and the results do not imply an iPhone frame-rate improvement.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import subprocess
import tempfile

from rpcs3_texture_address_index_test import braced

ROOT = Path(__file__).resolve().parents[1]
CPP = 'rpcs3/Emu/RSX/RSXFIFO.cpp'
HEADER = 'rpcs3/Emu/RSX/RSXFIFO.h'
COMMANDS = 'rpcs3/Emu/RSX/gcm_enums.h'
MODES = 'rpcs3/Emu/system_config_types.h'
SOURCE = (CPP,)
SUPPORT = (HEADER, COMMANDS, MODES)
ADAPTERS = (ROOT / 'test/native/rpcs3_fifo_pending_wait.inc',
            ROOT / 'test/native/rpcs3_fifo_partial_packet.inc')
METHODS = (
    'FIFO_control::FIFO_control(::rsx::thread* pctrl)',
    'u32 FIFO_control::translate_address(u32 address) const',
    'void FIFO_control::sync_get() const',
    'void FIFO_control::sync_get_force() const',
    'void FIFO_control::restore_state(u32 cmd, u32 count)',
    'void FIFO_control::inc_get(bool wait)',
    'inline u32 FIFO_control::read_put() const',
    'std::pair<bool, u32> FIFO_control::fetch_u32_refill(u32 addr)',
    'void FIFO_control::set_get(u32 get, u32 spin_cmd)',
    'bool FIFO_control::read_unsafe(register_pair& data)',
    'void FIFO_control::abort()',
    'void FIFO_control::read(register_pair& data)',
)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def program(tree, namespace):
    tree = Path(tree)
    cpp, header = (tree / CPP).read_text(), (tree / HEADER).read_text()
    declaration = braced(header, 'class FIFO_control\n')
    assert declaration.count('private:') == 1
    # Visibility only; every field, default value and inline production method
    # remains intact. Tests inspect retry/published GET and remaining counts.
    declaration = declaration.replace('private:', 'public:')
    bodies = []
    for signature in METHODS:
        body = braced(cpp, signature)
        if 'read_put()' in signature:
            body = 'template <bool Full>\n' + body
        bodies.append(body)
    return ('namespace ' + namespace + ' {\nusing namespace rsx;\n'
            'using namespace rsx::FIFO;\n' + declaration + ';\n' +
            '\n'.join(bodies) + '\n}\n')


def harness(source, baseline):
    source, baseline = Path(source), Path(baseline)
    for path in SUPPORT:
        assert (source / path).read_bytes() == (baseline / path).read_bytes(), path
    before, after = (tree / CPP for tree in (baseline, source))
    before, after = before.read_text(), after.read_text()
    signature = 'void FIFO_control::read(register_pair& data)'
    assert after.replace(braced(after, signature), '@READ@', 1) == before.replace(
        braced(before, signature), '@READ@', 1), 'Unrelated FIFO code changed'
    header = (source / HEADER).read_text()
    constants = braced((source / MODES).read_text(), 'enum class rsx_fifo_mode : unsigned') + ';\n'
    constants += 'namespace rsx {\n' + braced((source / COMMANDS).read_text(), 'enum Method : u32') + ';\n'
    constants += 'namespace FIFO {\n' + braced(header, 'enum internal_commands : u32') + ';\n'
    constants += braced(header, 'struct register_pair\n') + ';\n}}\n'
    code = ADAPTERS[0].read_text()
    for token, replacement in (
            ('@CONSTANTS@', constants), ('@BEFORE@', program(baseline, 'before')),
            ('@AFTER@', program(source, 'after')),
            ('@PACKET_TESTS@', ADAPTERS[1].read_text())):
        assert code.count(token) == 1, token
        code = code.replace(token, replacement)
    assert '@' not in code
    return code


def expected(source, baseline):
    source, baseline = Path(source), Path(baseline)
    code = harness(source, baseline)
    return dict(
        sourceSHA256={p: sha((source / p).read_bytes()) for p in SOURCE + SUPPORT},
        baselineSHA256={p: sha((baseline / p).read_bytes()) for p in SOURCE + SUPPORT},
        harnessSHA256=sha(code.encode()),
        adapterSHA256={str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in ADAPTERS},
        productionMethods=list(METHODS))


def verify_counts(result):
    assert result['passed'] is True and result['assertionsActive'] is True
    # Counts come from the deterministic cross-product in the checked-in C++
    # adapters. These expectations reject partial or fabricated success reports.
    counts = dict(pendingCases=960, pendingWaits=188928,
                  baselinePendingUnchanged=188928, candidatePendingUnchanged=0,
                  resumedPendingCommands=47232, partialPackets=1728,
                  baselineFirstArgumentMissed=1728, candidateFirstArgumentMissed=0,
                  resumedPartialWords=586368, headerWaits=6912,
                  getReentries=576, faultCancellationRecoveryCases=9,
                  fastBlockingCases=6, restoredPendingCases=48)
    for key, value in counts.items():
        assert result[key] == value, (key, result[key], value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--compiler', default=os.environ.get('CXX', 'c++'))
    parser.add_argument('--sanitizer', choices=('address,undefined',))
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    identities = expected(args.source, args.baseline)
    code = harness(args.source, args.baseline)
    compiler = shlex.split(args.compiler)
    flags = ['-std=c++20', '-DRPCS3_IOS', '-g', '-Wall', '-Wextra', '-Werror',
             '-pthread', '-UNDEBUG', '-O1' if args.sanitizer else '-O3']
    if args.sanitizer:
        flags += ['-fsanitize=' + args.sanitizer, '-fno-omit-frame-pointer']
        if platform.system() == 'Linux':
            flags += ['-fno-pie', '-no-pie']
    if sdk := os.environ.get('HOST_MACOS_SDK'):
        flags += ['-isysroot', sdk]
    env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1',
               UBSAN_OPTIONS='halt_on_error=1')
    with tempfile.TemporaryDirectory(prefix='rpcs3-fifo-partial-') as temporary:
        cpp, exe = Path(temporary) / 'test.cpp', Path(temporary) / 'test'
        cpp.write_text(code)
        subprocess.run(compiler + flags + [str(cpp), '-o', str(exe)], check=True)
        run = subprocess.run([str(exe)], text=True, capture_output=True,
                             timeout=180, env=env)
        assert run.returncode == 0 and not run.stderr, (run.returncode, run.stdout, run.stderr)
        result = json.loads(run.stdout)
    verify_counts(result)
    assert identities == expected(args.source, args.baseline)
    report = dict(passed=True, assertionsActive=True, results=result,
                  compiler=subprocess.check_output(compiler + ['--version'], text=True).splitlines()[0],
                  compilerFlags=flags, sanitizer=args.sanitizer, **identities,
                  host=dict(system=platform.system(), machine=platform.machine()),
                  leakSanitizer=False, physicalDeviceTested=False, gameplayMeasured=False,
                  fullSavestateSerializationTested=False, concurrentMemoryOrderingTested=False,
                  scope=__doc__)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
