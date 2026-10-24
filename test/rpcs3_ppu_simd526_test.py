#!/usr/bin/env python3
"""Four actual PPU VMSUM methods and their native LLVM builders on ARM64.

Adapters replace the register file and the generic CPUTranslator expression
DSL with minimal LLVM IRBuilder operations for loaded, nonconstant operands.
The 525 reference and current production method bodies are compiled directly,
and the new production native builders are included unchanged. The generated code
is executed on the ARM64 host, including the DOTPROD-disabled fallback; the
hardware DOTPROD instructions themselves are not emulated by a test shim.
The assembly target is the Core's AArch64 JIT triple / apple-m4 target. Runtime
execution uses the actual host CPU. No guest game or iPhone is exercised.
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
OPERATIONS = ('VMSUMUBM', 'VMSUMMBM', 'VMSUMUHM', 'VMSUMSHM')
BEFORE = ROOT / 'test/fixtures/rpcs3_ppu_dot526_before.inc'


def methods(text):
    result = []
    for name in OPERATIONS:
        start = text.index('void PPUTranslator::' + name + '(ppu_opcode_t op)\n{')
        position, depth = text.index('{', start) + 1, 1
        while depth:
            if text[position] == '{':
                depth += 1
            if text[position] == '}':
                depth -= 1
            position += 1
        result.append(text[start:position])
    return '\n\n'.join(result) + '\n'


def llvm_config(explicit):
    candidates = [explicit, os.environ.get('LLVM_CONFIG')]
    if os.environ.get('HOST_LLVM_ROOT'):
        candidates.append(str(Path(os.environ['HOST_LLVM_ROOT']) / 'bin/llvm-config'))
    if shutil.which('brew'):
        prefix = subprocess.run(['brew', '--prefix', 'llvm@22'], capture_output=True, text=True, timeout=60)
        if prefix.returncode == 0:
            candidates.append(str(Path(prefix.stdout.strip()) / 'bin/llvm-config'))
    candidates.append(shutil.which('llvm-config'))
    return next((Path(p) for p in candidates if p and Path(p).is_file()), None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--llvm-config')
    parser.add_argument('--require-llvm', action='store_true')
    parser.add_argument('--report', type=Path)
    parser.add_argument('--artifacts', type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    translator = source / 'rpcs3/Emu/Cell/PPUTranslator.cpp'
    helper = source / 'rpcs3/Emu/CPU/Backends/AArch64/CellVectorLowering.h'
    production = methods(translator.read_text())
    reference = BEFORE.read_text()
    assert 'RPCS3 525' in reference
    for operation, entry in [('VMSUMUBM', 'unsigned_byte_dot'), ('VMSUMMBM', 'signed_unsigned_byte_dot'),
                              ('VMSUMUHM', 'halfword_pair_dot'), ('VMSUMSHM', 'halfword_pair_dot')]:
        body = methods_for(production, operation)
        assert 'rpcs3::cell::arm64::' + entry in body
        if operation.endswith('BM'):
            assert 'if (utils::has_dotprod())' in body
            assert methods_for(reference, operation).split('{', 1)[1].rsplit('}', 1)[0].strip() in body
        else:
            assert '#else' in body
    config = llvm_config(args.llvm_config)
    if config is None:
        if args.require_llvm:
            raise SystemExit('FAIL LLVM22 with ARM64 execution is required')
        print('SKIP LLVM22 unavailable; no generated-code validation claimed')
        return
    def flags(*options):
        return shlex.split(subprocess.check_output([str(config), *options], text=True))
    version = subprocess.check_output([str(config), '--version'], text=True).strip()
    assert version.startswith('22.'), version
    assert 'AArch64' in flags('--targets-built')
    compiler = Path(flags('--bindir')[0]) / 'clang++'
    command = [str(compiler) if compiler.is_file() else os.environ.get('CXX', 'clang++')]
    if sdk := os.environ.get('HOST_MACOS_SDK'):
        command += ['-isysroot', sdk]
    command += ['-std=c++20', '-O2', '-g', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter', '-Wno-deprecated-declarations']
    command += [flag for flag in flags('--cxxflags') if not flag.startswith(('-std=', '-O', '-g', '-W', '-fno-exceptions', '-fno-rtti'))]
    with tempfile.TemporaryDirectory(prefix='rpcs3-ppu-dot526-') as temporary:
        work = Path(temporary)
        (work / 'rpcs3_ppu_dot526_before.inc').write_text(reference)
        (work / 'rpcs3_ppu_dot526_after.inc').write_text(production)
        binary = work / 'ppu-dot526'
        command += ['-I', str(source), '-I', str(work), str(ROOT / 'test/native/rpcs3_ppu_dot526.cpp'), '-o', str(binary)]
        command += flags('--ldflags') + flags('--libs', 'core', 'mcjit', 'native', 'aarch64', 'support', 'executionengine', 'runtimedyld', 'transformutils') + flags('--system-libs')
        command += ['-Wl,-rpath,' + flags('--libdir')[0]]
        env = dict(os.environ)
        env.pop('SDKROOT', None)
        subprocess.run(command, check=True, env=env, timeout=600)
        result = work / 'result.json'
        subprocess.run([str(binary), str(result), str(work)], check=True, env=env, timeout=240)
        report = json.loads(result.read_text())
        hardware = {}
        if shutil.which('sysctl'):
            for name in ('hw.model', 'machdep.cpu.brand_string'):
                queried = subprocess.run(['sysctl', '-n', name], capture_output=True, text=True, timeout=15)
                hardware[name] = queried.stdout.strip() if queried.returncode == 0 else None
        report.update(hardware=hardware, benchmark_cache='warm generated code and hot corpus; no guest/file cache eviction', llvm_version=version, production_translator_sha256=hashlib.sha256(translator.read_bytes()).hexdigest(),
                      production_helper_sha256=hashlib.sha256(helper.read_bytes()).hexdigest(),
                      before_fixture_sha256=hashlib.sha256(BEFORE.read_bytes()).hexdigest(),
                      limitations='Generated integer kernels on ARM64 host; register-file and generic expression DSL adapters, production method bodies and native builders unchanged; no full PPU translator pipeline, game, guest CPU instruction stream, phone FPS, cold/warm title cache or peak memory measurement')
        assert len(report['operations']) == 4
        assert all(row['bit_exact'] and row['big_endian_exact'] for row in report['operations'])
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, indent=2) + '\n')
        if args.artifacts:
            args.artifacts.mkdir(parents=True, exist_ok=True)
            for assembly in work.glob('*.s'):
                shutil.copy2(assembly, args.artifacts / assembly.name)
        print(json.dumps(report, indent=2))


def methods_for(text, operation):
    start = text.index('void PPUTranslator::' + operation + '(ppu_opcode_t op)\n{')
    end = text.find('\n\nvoid ', start)
    return text[start:end if end != -1 else len(text)]


if __name__ == '__main__':
    main()
