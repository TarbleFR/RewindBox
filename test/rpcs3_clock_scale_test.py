#!/usr/bin/env python3
"""Run exact production clock helpers against preimages and a uint128 oracle.

The counter, clock scale and offset are runtime inputs. No instruction-level
JIT or Core is compiled and the benchmark does not measure iPhone gameplay.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'rpcs3/Emu/Cell/lv2/sys_time.cpp'
UPSTREAM = '22f1152783cef1f7e04af7b1c895173e28fd5b03'


def sha(data):
    return hashlib.sha256(data.replace(b'\r\n', b'\n')).hexdigest()


def braced(text, name):
    assert text.count(name) == 1, name
    start = text.index(name)
    end = text.index('{', start) + 1
    depth = 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]


def without_ios(text):
    out = []
    skip = False
    for line in text.splitlines(keepends=True):
        if line.strip() == '#ifdef RPCS3_IOS':
            assert not skip
            skip = True
        elif skip and line.strip() == '#endif':
            skip = False
        elif not skip:
            out.append(line)
    assert not skip
    return ''.join(out)


def functions(text, prefix='CLOCK_NOINLINE '):
    return '\n'.join(prefix + braced(text, 'u64 ' + name + '()')
                     for name in ['get_timebased_time', 'get_system_time'])


def code(before, after):
    adapter = (ROOT / 'test/native/rpcs3_clock_scale.inc').read_text()
    return adapter.replace('// BEFORE_FUNCTIONS', functions(before)).replace('// AFTER_FUNCTIONS', functions(after))


def arm_code(before, after):
    # Freestanding code generation: real function bodies, external inputs,
    # and the production ARM counter-read instruction. No Apple SDK is used.
    preamble = '''using u64=unsigned long long;
struct timespec { long tv_sec; long tv_nsec; };
extern "C" int clock_gettime(int,timespec*);
#define CLOCK_MONOTONIC 1
#define ensure(v) do { if (!(v)) __builtin_trap(); } while(false)
extern u64 g_timebase_offs;
struct Config {struct {u64 clocks_scale;} core;};
extern Config g_cfg;
static constexpr u64 g_timebase_freq=80000000ull;
namespace utils {
extern u64 s_tsc_freq;
inline u64 get_tsc_freq() {return s_tsc_freq;}
inline u64 get_tsc() {u64 r;__asm__ volatile("mrs %0, cntvct_el0":"=r"(r));return r;}
}
'''
    return preamble + '\nnamespace before {\n' + functions(before, '') + '\n}\nnamespace after {\n' + functions(after, '') + '\n}\n'



def assembly_paths(assembly):
    """Check actual dynamic paths; counting UDIV in the whole function is wrong.

    This deliberately checks the pinned LLVM 22 A18 assembly form. Fail closed
    if control flow changes rather than accidentally accepting if-conversion.
    """
    result = {}
    for helper in ['get_timebased_time', 'get_system_time']:
        paths = {}
        for namespace in ['before', 'after']:
            symbol = f'__ZN{len(namespace)}{namespace}{len(helper)}{helper}Ev'
            start = assembly.index(symbol + ':')
            body = assembly[start:assembly.index('\t.cfi_endproc', start)]
            instructions, labels = [], {}
            for line in body.splitlines():
                line = line.split(';', 1)[0].strip()
                if line.endswith(':'):
                    labels[line[:-1]] = len(instructions)
                elif line and not line.startswith('.'):
                    instructions.append(line)
            zero = next(i for i, line in enumerate(instructions) if line.startswith('cbz\t'))
            frequency_register = instructions[zero].split()[1].rstrip(',')
            compare, branch = None, None
            if namespace == 'after':
                compare = next(i for i, line in enumerate(instructions)
                               if line.startswith('cmp\t' + frequency_register + ','))
                branch = compare + 1
                assert instructions[branch].startswith('b.ne\t'), 'frequency test must retain a branch'
                constant_register = instructions[compare].split(',')[1].strip()
                constants = {}
                for line in instructions[:compare]:
                    match = re.fullmatch(r'(mov|movk)\s+([xw]\d+), #(\d+)(?:, lsl #(\d+))?', line)
                    if not match:
                        continue
                    op, register, value, shift = match.groups()
                    key, value, shift = 'x' + register[1:], int(value), int(shift or 0)
                    constants[key] = value if op == 'mov' else ((constants[key] & ~(65535 << shift)) | (value << shift))
                assert constants[constant_register] == 1_000_000_000
                blocks = re.findall(r'; InlineAsm Start\n(.*?); InlineAsm End', body, re.S)
                assert len(blocks) == 2 and not blocks[1].strip(), 'branch-retention asm must emit nothing'
            for frequency in [1_000_000_000, 24_000_000]:
                pc, visited = 0, []
                for _ in range(len(instructions) * 2):
                    assert pc not in visited, 'unexpected loop on nonzero counter path'
                    visited.append(pc)
                    instruction = instructions[pc]
                    op = instruction.split()[0]
                    if op == 'ret':
                        break
                    if pc == zero:
                        pc += 1  # Both tested frequencies are nonzero.
                    elif pc == branch:
                        pc = pc + 1 if frequency == 1_000_000_000 else labels[instruction.split()[1]]
                    elif op == 'b':
                        pc = labels[instruction.split()[1]]
                    else:
                        assert op not in ['cbz', 'cbnz', 'tbz', 'tbnz'] and not op.startswith('b.'), instruction
                        assert op not in ['bl', 'blr', 'br', 'brk', 'dmb', 'dsb', 'isb'], instruction
                        pc += 1
                else:
                    raise AssertionError('nonzero counter path did not return')
                count = sum(instructions[i].startswith('udiv\t') for i in visited)
                expected = 0 if namespace == 'after' and frequency == 1_000_000_000 else 2
                assert count == expected, (namespace, helper, frequency, count)
                paths[f'{namespace}_{frequency}Hz'] = {'dynamicUDIV': count, 'instructionsToReturn': len(visited)}
        result[helper] = paths
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path)
    p.add_argument('--before', type=Path)
    p.add_argument('--sanitize', action='store_true')
    p.add_argument('--benchmark', action='store_true')
    p.add_argument('--zig', type=Path)
    p.add_argument('--report', type=Path)
    a = p.parse_args()
    source = a.source.resolve()
    after_bytes = (source / SOURCE).read_bytes()
    if a.before:
        before_bytes = (a.before / SOURCE).read_bytes()
    else:
        before_bytes = subprocess.check_output(['git', 'show', UPSTREAM + ':' + SOURCE], cwd=source)
    before = before_bytes.decode().replace('\r\n', '\n')
    after = after_bytes.decode().replace('\r\n', '\n')
    assert without_ios(after) == before, 'off-iOS source must be byte-identical'
    cxx = shlex.split(os.environ.get('CXX', 'c++'))
    if sdk := os.environ.get('HOST_MACOS_SDK'):
        cxx += ['-isysroot', sdk]
    with tempfile.TemporaryDirectory(prefix='rpcs3-clock-scale-') as tmp:
        work = Path(tmp)
        cpp = work / 'clock.cpp'
        cpp.write_text(code(before, after))
        exe = work / 'clock'
        flags = ['-std=c++20', '-Wall', '-Wextra', '-Werror', '-g', '-UNDEBUG', '-DRPCS3_IOS']
        flags += ['-O1', '-fsanitize=address,undefined', '-fno-omit-frame-pointer'] if a.sanitize else ['-O3']
        subprocess.run(cxx + flags + [str(cpp), '-o', str(exe)], check=True)
        result = subprocess.run([str(exe)] + (['benchmark'] if a.benchmark else []), capture_output=True,
                                text=True, timeout=90, env=dict(os.environ, ASAN_OPTIONS='detect_leaks=0', UBSAN_OPTIONS='halt_on_error=1'))
        if result.returncode:
            print(result.stderr)
            result.check_returncode()
        report = {'passed': True, 'host': platform.machine(), 'compiler': subprocess.check_output(cxx + ['--version'], text=True).splitlines()[0],
                  'sourceBeforeSHA256': sha(before_bytes), 'sourceAfterSHA256': sha(after_bytes),
                  'harnessSHA256': sha(cpp.read_bytes()), 'sanitized': a.sanitize, 'leakSanitizer': False, 'hostFlags': flags,
                  'offIOSUnchanged': True, 'results': json.loads(result.stdout),
                  'physicalDeviceTested': False, 'coreCompiled': False, 'gameplayMeasured': False,
                  'scope': 'Actual native sys_time.cpp helper bodies; runtime counter/config adapters; uint128 arithmetic oracle. Synthetic helper CPU timing only.'}
        if a.zig:
            arm_cpp = work / 'clock-arm.cpp'
            arm_cpp.write_text(arm_code(before, after))
            assembly = work / 'clock-arm.s'
            subprocess.run([str(a.zig), 'c++', '-std=c++20', '-target', 'aarch64-macos', '-mcpu=apple_a18', '-O3', '-g0',
                            '-DRPCS3_IOS', '-S', str(arm_cpp), '-o', str(assembly)], check=True, timeout=90)
            assert assembly.is_file()
            report['aarch64Assembly'] = {'compiler': subprocess.check_output([str(a.zig), 'c++', '--version'], text=True).splitlines()[0],
                                         'target': 'aarch64-macos', 'cpu': 'apple_a18', 'SDKUsed': False, 'flags': '-std=c++20 -target aarch64-macos -mcpu=apple_a18 -O3 -g0 -DRPCS3_IOS -S',
                                         'paths': assembly_paths(assembly.read_text()),
                                         'inputSHA256': sha(arm_cpp.read_bytes()), 'assemblySHA256': sha(assembly.read_bytes())}
            if a.report:
                a.report.parent.mkdir(parents=True, exist_ok=True)
                a.report.with_suffix('.aarch64.s').write_bytes(assembly.read_bytes())
        report['inputs'] = {str(path.relative_to(ROOT)): sha(path.read_bytes()) for path in
                            [ROOT / 'test/rpcs3_clock_scale_test.py', ROOT / 'test/native/rpcs3_clock_scale.inc']}
    if a.report:
        a.report.parent.mkdir(parents=True, exist_ok=True)
        a.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
