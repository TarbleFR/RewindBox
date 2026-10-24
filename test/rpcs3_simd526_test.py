#!/usr/bin/env python3
"""Differentially exercise production SPU SIMD bodies before/after the native migration.

The only doubles are a register file, decoded opcode fields, host feature queries
and scale-table storage. v128, gv implementations, instruction bodies, LUTs and
legacy ARM SSE adapter are read from the materialized, hash-locked source.
"""
import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'test/fixtures/rpcs3_simd526_spu.diff'
NATIVE = ROOT / 'test/native/rpcs3_simd526.cpp'
BASELINE_SPU_SHA = 'cb333853b65df6cb4a1f1254539eb193b685fc3e91c752ab4eb7b014e3c17e8f'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def balanced(text, start):
    depth, i = 1, start
    while depth:
        if text[i] == '{': depth += 1
        elif text[i] == '}': depth -= 1
        i += 1
    return i


def instructions(text):
    text = text.split('\n#if 0\n', 1)[0]
    result = {}
    for match in re.finditer(r'(?m)^bool (\w+)\(spu_thread& spu, spu_opcode_t op\)\n\{', text):
        end = balanced(text, match.end())
        result[match.group(1)] = text[match.start():end]
    return result


def runtime_functions(text):
    result = {}
    # Exclude asmjit builder overloads: the test executes host runtime bodies.
    pattern = r'(?m)^(?:inline|FORCE_INLINE) (?:v128|u32|bool|void) (gv_\w+)\([^;{]*\)\s*\n\{'
    for match in re.finditer(pattern, text):
        if 'auto mptr' in match.group(0):
            continue # Offset-aware member broadcasts are not used by these bodies.
        end = balanced(text, match.end())
        start = match.start()
        previous = text[:start].rsplit('\n', 2)
        if len(previous) > 1 and previous[-2].startswith('template <'):
            start -= len(previous[-2]) + 1
        result.setdefault(match.group(1), []).append(text[start:end])
    return result


def prepare(source, directory):
    rel = 'rpcs3/Emu/Cell/SPUInterpreter.cpp'
    current = (source / rel).read_text()
    oldfile = directory / rel
    oldfile.parent.mkdir(parents=True)
    oldfile.write_text(current)
    subprocess.run(['git', 'apply', '--reverse', str(FIXTURE)], cwd=directory, check=True)
    before = oldfile.read_text()
    assert digest(before.encode()) == BASELINE_SPU_SHA, 'Baseline is not the verified build525 SPU interpreter'
    assert current.split('\n#if 0\n', 1)[1] == before.split('\n#if 0\n', 1)[1], 'Inactive precise code changed'
    # Removing only this include must not conceal remaining ARM SSE calls.
    assert 'sse2neon.h' not in current
    b, a = instructions(before), instructions(current)
    changed = [name for name in b if b[name] != a[name]]
    assert changed and set(b) == set(a)
    support = runtime_functions((source / 'rpcs3/util/simd.hpp').read_text())
    needed = {'gv_set_zeroing_denormals', 'gv_unset_zeroing_denormals'} | set(re.findall(r'\bgv_\w+', '\n'.join([a[x] + b[x] for x in changed])))
    while True:
        expanded = needed | set(re.findall(r'\bgv_\w+', '\n'.join(code for name in needed for code in support.get(name, []))))
        if expanded == needed: break
        needed = expanded
    assert needed <= support.keys(), sorted(needed - support.keys())
    functions = [code for name in support if name in needed for code in support[name]]
    # Forward declarations match original overload signatures and template args.
    declarations = [code[:code.index('{')].strip() + ';' for code in functions]
    simd = (source / 'rpcs3/util/simd.hpp').read_text()
    operators = simd[simd.index('inline v128 v128::operator|'):simd.index('inline v128 gv_exp2_approxfs')]
    common = '\n'.join(declarations + functions) + '\n' + operators
    # These production functions use only gpr and the decoded fields. No host
    # calls, guest memory, scheduler, JIT or GPU service are replaced here.
    for name in changed:
        assert not re.search(r'\bspu\.(?!gpr\b)\w+', a[name] + b[name]), name
    (directory / 'native-gv.hpp').write_text(common)
    (directory / 'instructions.hpp').write_text(
        'namespace baseline {\n' + '\n'.join('__attribute__((noinline' + (', no_sanitize(\"signed-integer-overflow\")' if x == 'ROTQMBI' else '') + ')) ' + b[x] for x in changed) + '\n}\n'
        'namespace candidate {\n' + '\n'.join('__attribute__((noinline)) ' + a[x] for x in changed) + '\n}\n'
        'namespace baseline_control {\n__attribute__((noinline)) ' + b['ROTQMBI'] + '\n}\n')
    # Import the real reciprocal estimate LUT definitions, not replacements.
    thread = (source / 'rpcs3/Emu/Cell/SPUThread.cpp').read_text()
    tables = []
    for match in re.finditer(r'(?m)^const u32 spu_f(?:rest|rsqest)_\w+_lut\[\d+\] =\n\{', thread):
        end = balanced(thread, match.end())
        tables.append(thread[match.start():end + 1])
    assert len(tables) == 4
    (directory / 'luts.hpp').write_text('\n'.join(tables))
    # A standalone preprocessing pass proves the entire migrated candidate
    # instruction set has no SSE call/type left under the ARM64 guards.
    candidate = 'namespace candidate {\n' + '\n'.join(a[x] for x in changed) + '\n}\n'
    cpp = subprocess.run(shlex.split(os.environ.get('CXX', 'c++')) + ['-E', '-P', '-x', 'c++', '-DARCH_ARM64=1', '-'], input=candidate, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    assert not re.search(r'\b(?:_mm_\w+|__m128\w*)\b', cpp.stdout), 'ARM64 still enters an SSE operation'
    (directory / 'cases.hpp').write_text('static const TestCase cases[] = {\n' + '\n'.join(
        '{"' + x + '", baseline::' + x + ', candidate::' + x + '},' for x in changed) + '\n};\n')
    (directory / 'wrappers.hpp').write_text('\n'.join(
        'extern "C" __attribute__((noinline)) bool simd526_' + variant + '_' + name + '(spu_thread* state, spu_opcode_t op) { return ' + variant + '::' + name + '(*state, op); }'
        for name in ('CNTB', 'SHUFB', 'ROTM', 'ROTHM', 'ROTQBY', 'ROTQMBY', 'SHLQBY', 'CFLTU')
        for variant in ('baseline', 'candidate')))
    return dict(instructions=changed, runtime_primitives=sorted(needed),
                before_spu_sha256=digest(before.encode()), after_spu_sha256=digest(current.encode()),
                simd_sha256=digest(simd.encode()), fixture_sha256=digest(FIXTURE.read_bytes()),
                v128_sha256=digest((source / 'rpcs3/util/v128.hpp').read_bytes()),
                types_sha256=digest((source / 'rpcs3/util/types.hpp').read_bytes()),
                sse_adapter_sha256=digest((source / 'rpcs3/Emu/CPU/sse2neon.h').read_bytes()),
                arm64_legacy_sse_operations=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', nargs='?', type=Path)
    parser.add_argument('--source', dest='source_option', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--sanitize', action='store_true')
    parser.add_argument('--benchmark', action='store_true')
    parser.add_argument('--keep-generated', type=Path)
    args = parser.parse_args()
    source = (args.source_option or args.source).resolve()
    compiler = shlex.split(os.environ.get('CXX', 'c++'))
    architecture = platform.machine().lower()
    with tempfile.TemporaryDirectory(prefix='rpcs3-simd526-') as temp:
        work = Path(temp)
        record = prepare(source, work)
        flags = ['-std=c++20', '-O3', '-fno-fast-math', '-fno-strict-aliasing', '-I' + str(source / 'rpcs3'), '-I' + str(work)]
        if architecture in ('arm64', 'aarch64'):
            flags += ['-DARCH_ARM64=1', '-march=armv8.4-a']
        else:
            flags += ['-DARCH_X64=1', '-msse4.1', '-mssse3', '-mfma']
        if os.environ.get('HOST_MACOS_SDK'):
            flags += ['-isysroot', os.environ['HOST_MACOS_SDK']]
        if args.sanitize:
            flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
        exe = work / 'simd-test'
        cmd = [*compiler, *flags, str(NATIVE), '-o', str(exe)]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if result.returncode:
            print(result.stdout.decode(), end='')
            raise SystemExit(result.returncode)
        execution_env = dict(os.environ, ASAN_OPTIONS=os.environ.get('ASAN_OPTIONS', 'detect_leaks=0'), UBSAN_OPTIONS='halt_on_error=1')
        if args.sanitize:
            control = subprocess.run([str(exe), '--baseline-undefined-negation'], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=execution_env)
            assert control.returncode != 0 and 'negation of -2147483648' in control.stderr, control.stderr
            record['baseline_undefined_negation_control'] = dict(rejected=True, stderr_sha256=digest(control.stderr.encode()), signed_overflow_suppressed_only_in_differential_baseline_ROTQMBI=True)
        output = subprocess.check_output([str(exe), '--benchmark' if args.benchmark else '--test'], text=True, env=execution_env)
        print(output, end='')
        record.update(json.loads(output))
        configurations = [dict(fp_contract='compiler-target-default', **json.loads(output))]
        if not args.benchmark:
            strict = work / 'simd-test-strict'
            result = subprocess.run([*compiler, *flags, '-ffp-contract=off', str(NATIVE), '-o', str(strict)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            if result.returncode:
                print(result.stdout.decode(), end='')
                raise SystemExit(result.returncode)
            strict_output = subprocess.check_output([str(strict), '--test'], text=True, env=execution_env)
            print(strict_output, end='')
            configurations.append(dict(fp_contract='off', **json.loads(strict_output)))
        record['floating_point_configurations'] = configurations
        record['compiler_flags'] = flags
        record.update(compiler=subprocess.check_output(compiler + ['--version'], text=True).splitlines()[0],
                      target=architecture, sanitized=args.sanitize, physical_device_tested=False,
                      host_system=platform.platform())
        if platform.system() == 'Darwin':
            record['host_hardware'] = subprocess.check_output(['sysctl', '-n', 'hw.model'], text=True).strip()
            record['host_cpu'] = subprocess.check_output(['sysctl', '-n', 'machdep.cpu.brand_string'], text=True).strip()
        # Save assembly for inspection; no whole binary disassembly data is
        # substituted for a production Core compile.
        assembly = work / 'simd.s'
        subprocess.run([*compiler, *flags, '-S', str(NATIVE), '-o', str(assembly)], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if architecture in ('arm64', 'aarch64'):
            text = assembly.read_text()
            checks = {'CNTB': r'\bcnt\b', 'SHUFB': r'\btbl\b', 'ROTM': r'\bushl\b', 'ROTHM': r'\bushl\b', 'ROTQBY': r'\btbl\b', 'CFLTU': r'\bfcvtzu\b'}
            found = {}
            for name, pattern in checks.items():
                label = re.search(r'(?m)^_*ZN9candidate' + str(len(name)) + name + r'E[^:]*:.*$', text)
                assert label, name
                end = re.search(r'(?m)^\s*(?:\.cfi_endproc|\.size|\.Lfunc_end)', text[label.end():])
                section = text[label.start():label.end() + end.start()] if end else text[label.start():]
                found[name] = bool(re.search(pattern, section))
                assert found[name], (name, section)
            record['native_instruction_checks'] = found
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(record, indent=2) + '\n')
        if args.keep_generated:
            shutil.copytree(work, args.keep_generated, dirs_exist_ok=True)


if __name__ == '__main__':
    main()
