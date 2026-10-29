#!/usr/bin/env python3
"""Execute the production LLVM enqueue emissions and MFC completion protocol.

The enqueue IR builder is an explicit bounded-memory evaluation adapter, not
LLVM or an AArch64 execution engine. The emitted source block, MFC executor,
tag completion and tag-update branch are extracted verbatim. No game fix or
device performance is inferred from this protocol regression.
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
import rpcs3_spu_mfc_runtime_test as runtime

ROOT = Path(__file__).resolve().parents[1]
LLVM = 'rpcs3/Emu/Cell/SPULLVMRecompiler.cpp'
ADAPTER = ROOT / 'test/native/rpcs3_spu_mfc_llvm_tag.inc'
STORE = '\t\t\t\t\tm_ir->CreateStore(tag.value, _ptr(pmfc, &spu_mfc_cmd::tag));\n'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def enqueue(tree):
    text = (tree / LLVM).read_text()
    start = text.index('// Fallback: enqueue the command')
    end = text.index('\n\t\t\t}\n\n\t\t\t// Fallback to unoptimized WRCH', start)
    return text[start:end]


def bodies(tree):
    cpp = (tree / runtime.CPP).read_text()
    result = {signature: braced(cpp, signature) for signature in runtime.METHODS}
    channel = cpp[cpp.index('bool spu_thread::set_ch_value('):]
    result['tagUpdate'] = braced(channel, 'case MFC_WrTagUpdate:')
    process = cpp[cpp.index('bool spu_thread::process_mfc_cmd()'):]
    result['referenceBarrierEnqueue'] = braced(process, 'case MFC_BARRIER_CMD:')
    return result


def harness(source, baseline):
    old, new = (tree.joinpath(LLVM).read_text() for tree in (baseline, source))
    old_enqueue, new_enqueue = enqueue(baseline), enqueue(source)
    # Exactly one tag store in the barrier-class enqueue branch; all other
    # generated instructions, queue publication and helper bodies stay exact.
    assert ''.join(new_enqueue.rsplit(STORE, 1)) == old_enqueue
    assert old.replace(old_enqueue, '@ENQUEUE@') == new.replace(new_enqueue, '@ENQUEUE@')
    before, after = bodies(baseline), bodies(source)
    assert before == after
    mfc = source.joinpath(runtime.MFC).read_text()
    assert mfc == baseline.joinpath(runtime.MFC).read_text()
    declarations = '\n'.join(braced(mfc, signature) + ';' for signature in (
        'enum MFC : u8', 'enum mfc_tag_update : u32', 'struct alignas(16) spu_mfc_cmd'))
    boundary = runtime.ADAPTER.read_text().split('@BEFORE@', 1)[0]
    boundary = boundary.replace('@MFC@', declarations)
    production = runtime.program(source, 'production')
    production = production.replace('bool check_mfc_interrupts(u32 next_pc);',
        'bool check_mfc_interrupts(u32 next_pc);\nspu_mfc_cmd ch_mfc_cmd{};\n'
        'bool reference_enqueue() { switch(ch_mfc_cmd.cmd) { '
        + after['referenceBarrierEnqueue']
        + ' default: throw Escaped{}; } }\n'
        'bool request_tag_update(u32 value) { switch (0) { case 0: '
        + after['tagUpdate'][after['tagUpdate'].index('{'):]
        + '} return false; }')
    code = ADAPTER.read_text()
    return boundary + production + code.replace('@BEFORE_ENQUEUE@', old_enqueue).replace('@AFTER_ENQUEUE@', new_enqueue)


def identities(source, baseline):
    return dict(sourceSHA256={p: sha((source/p).read_bytes()) for p in (LLVM, runtime.MFC)},
        baselineSHA256={p: sha((baseline/p).read_bytes()) for p in (LLVM, runtime.MFC)},
        runtimeBodySHA256={k: sha(v.encode()) for k,v in bodies(source).items()},
        harnessSHA256=sha(harness(source, baseline).encode()),
        adapterSHA256={str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in (ADAPTER, runtime.ADAPTER)})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--sanitizer', choices=['address,undefined'])
    parser.add_argument('--compiler', default=os.environ.get('CXX', 'c++'))
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    source, baseline = args.source.resolve(), args.baseline.resolve()
    identity = identities(source, baseline)
    compiler = shlex.split(args.compiler)
    flags = ['-std=c++20', '-g', '-Wall', '-Wextra', '-Werror', '-UNDEBUG', '-O1' if args.sanitizer else '-O3']
    if args.sanitizer:
        flags += ['-fsanitize='+args.sanitizer, '-fno-omit-frame-pointer']
        if platform.system() == 'Linux':
            flags += ['-fno-pie', '-no-pie']
    if sdk := os.environ.get('HOST_MACOS_SDK'):
        flags += ['-isysroot', sdk]
    with tempfile.TemporaryDirectory(prefix='rpcs3-mfc-llvm-tag-') as temp:
        cpp, exe = Path(temp)/'test.cpp', Path(temp)/'test'
        cpp.write_text(harness(source, baseline))
        subprocess.run([*compiler, *flags, str(cpp), '-o', str(exe)], check=True)
        run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=120,
            env=dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1', UBSAN_OPTIONS='halt_on_error=1'))
        assert run.returncode == 0 and not run.stderr, (run.returncode, run.stdout, run.stderr)
        result = json.loads(run.stdout)
    assert identity == identities(source, baseline)
    report = dict(passed=True, assertionsActive=True, **identity, results=result,
        compiler=subprocess.check_output([*compiler, '--version'], text=True).splitlines()[0], compilerFlags=flags,
        sanitizer=args.sanitizer, host=platform.machine(), llvmCompiled=False, aarch64Executed=False,
        physicalDeviceTested=False, gameplayMeasured=False, realDMATransfersTested=False,
        concurrentMemoryOrderingTested=False, leakSanitizer=False, scope=__doc__)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
