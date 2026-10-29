#!/usr/bin/env python3
"""Exercise production JIT cache read bodies against the delivered 593 baseline.

Only this I/O delta is tested. LLVM's unchanged object validator is an explicit
adapter; gzip decoding and filesystem operations execute their real code.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def body(text, signature):
    start = text.index(signature)
    brace = text.index('{', start)
    level = 1
    i = brace + 1
    while level:
        if text[i] == '{':
            level += 1
        elif text[i] == '}':
            level -= 1
        i += 1
    return text[start:i]


def production(text, namespace):
    load = body(text, 'static std::unique_ptr<llvm::MemoryBuffer> load(')
    probe = body(text, 'jit_cached_object jit_compiler::load_cached_object(')
    probe = probe.replace('jit_compiler::load_cached_object', 'load_cached_object', 1)
    validator = '''static bool validate(const llvm::MemoryBuffer& b, std::string_view) {
        return b.getBufferSize() && static_cast<unsigned char>(b.getBufferStart()[0]) == 0x7f;
    }'''
    return f'namespace {namespace} {{\nstruct ObjectCache {{\n{load}\n{validator}\n}};\n{probe}\n}}\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--baseline', required=True, type=Path)
    parser.add_argument('--compiler', default=os.environ.get('CXX', 'g++'))
    parser.add_argument('--sanitize', action='store_true')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    baseline = args.baseline.resolve()
    path = 'Utilities/JITLLVM.cpp'
    before = (baseline / path).read_text()
    after = (source / path).read_text()
    assert hashlib.sha256((baseline / path).read_bytes()).hexdigest() == '6dc91ec7e52f504b7af42302d90c286a922575f3d81070ef29732d9671fa828d'
    # All object emission, relocation and symbol validation code stays exact.
    remaining = after
    signatures = [
        'static std::unique_ptr<llvm::MemoryBuffer> load(',
        'std::unique_ptr<llvm::MemoryBuffer> getObject(',
        'jit_cached_object jit_compiler::load_cached_object(',
    ]
    for signature in signatures:
        remaining = remaining.replace(body(after, signature), body(before, signature), 1)
    assert remaining == before, 'unreviewed change outside three I/O/cache-hit methods'
    assert (source / 'Utilities/JITObjectBuffer.h').read_bytes() == (baseline / 'Utilities/JITObjectBuffer.h').read_bytes()
    harness = (ROOT / 'test/native/rpcs3_jit_cache_io.inc').read_text()
    generated = harness.replace('// @PRODUCTION_BODIES@', production(before, 'before') + production(after, 'after'))
    compiler = shlex.split(args.compiler)
    with tempfile.TemporaryDirectory(prefix='rpcs3-jit-io-') as temp:
        work = Path(temp)
        cpp = work / 'test.cpp'
        cpp.write_text(generated)
        flags = ['-std=c++20', '-O2', '-g', '-UNDEBUG', '-DRPCS3_IOS']
        cmd = compiler + flags + ['-I', str(source), str(cpp), '-lz', '-o', str(work / 'test')]
        if args.sanitize:
            cmd += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
        subprocess.run(cmd, check=True)
        env = dict(os.environ)
        if args.sanitize:
            env['ASAN_OPTIONS'] = 'detect_leaks=0'
        completed = subprocess.run([str(work / 'test'), str(work / 'files')], text=True, capture_output=True, env=env)
        if completed.returncode:
            if args.report:
                args.report.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(cpp, args.report.with_suffix('.failed.cpp'))
                shutil.copyfile(work / 'test', args.report.with_suffix('.failed.bin'))
                args.report.write_text(json.dumps({'passed': False, 'returncode': completed.returncode,
                    'stdout': completed.stdout, 'stderr': completed.stderr, 'command': cmd}, indent=2) + '\n')
            print(completed.stdout, completed.stderr, sep='\n')
            completed.check_returncode()
        result = json.loads(completed.stdout)
        # Non-iOS preprocessing must preserve the exact old production text.
        old_cpp = work / 'old.cpp'; new_cpp = work / 'new.cpp'
        old_cpp.write_text(production(before, 'same') + body(before, 'std::unique_ptr<llvm::MemoryBuffer> getObject('))
        new_cpp.write_text(production(after, 'same') + body(after, 'std::unique_ptr<llvm::MemoryBuffer> getObject('))
        clean = lambda p: subprocess.check_output(compiler + ['-E', '-P', '-x', 'c++', str(p)], text=True)
        assert ''.join(clean(old_cpp).split()) == ''.join(clean(new_cpp).split())
    result.update({
        'compiler': subprocess.check_output(compiler + ['--version'], text=True).splitlines()[0],
        'sanitizers': ['address', 'undefined'] if args.sanitize else [],
        'compilerFlags': flags + (['-fsanitize=address,undefined', '-fno-omit-frame-pointer'] if args.sanitize else []),
        'source_sha256': hashlib.sha256((source / path).read_bytes()).hexdigest(),
        'baseline_sha256': hashlib.sha256((baseline / path).read_bytes()).hexdigest(),
        'generated_cpp_sha256': hashlib.sha256(generated.encode()).hexdigest(),
        'non_ios_read_bodies_unchanged': True,
        'emission_and_relocation_code_unchanged': True,
        'physical_device_tested': False,
    })
    text = json.dumps(result, indent=2) + '\n'
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text)
    print(text, end='')


if __name__ == '__main__':
    main()
