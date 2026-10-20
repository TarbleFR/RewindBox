#!/usr/bin/env python3
"""Execute the Build 499 SPU fixes and their exact pre-499 negative controls.

The production SHUFB mask table, branch-target function and diagnostic block
are compiled with the real opcode decoder. The scalar shuffle is independent
of the insert fast path. No commercial game or iPhone measurement is implied.
"""
import argparse
import hashlib
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
OLD_MASK = '{ 0x1011121303151617, 0x0001020304050607, &cpu_translator::get_type<u64[2]>, 1, 0 }'
NEW_MASK = OLD_MASK.replace('1011121303151617', '1011121314151617')
OLD_LOG = '\t\tspu_log.notice("Building function 0x%x... (size %u, %s)", func.entry_point, func.data.size(), m_hash);'
NEW_LOG = '''\t\t// NEOSTATION_BUILD499_SPU_AUDIT_V1: aggregate JITPROF/SPUPROF remain the default diagnostics.
\t\t// Per-block messages are opt-in trace; avoid formatting and file writes on every compile.
\t\tspu_log.trace("SPUCORE499 Building function 0x%x... (size %u, %s)", func.entry_point, func.data.size(), m_hash);'''
DUMP_COMMENT = '''\t\t// NEOSTATION_BUILD499_SPU_AUDIT_V1: a decrementer read is ordinary guest code,
\t\t// not a compilation error. Preserve its full dump only in explicit SPU debug mode.
'''
BRANCH_ADDITION = '''\t\telse if (index == 1)
\t\t{
\t\t\t// RPCS3 9c8e4349 / ARMSX3 ddd902e7: branch target precedes fallthrough.
\t\t\tstd::swap(res[0], res[1]);
\t\t}
'''
REFERENCE_LLVM_SHA256 = '0fbd4c477a3e83f8254c0ae4efc77cf17348dba3f2159c4d6686aff9e4317b17'
REFERENCE_THREAD_SHA256 = 'b61d719ba055884c9bb9689ad7411fc57cd44eedd717d08b822562b5231f7c9a'


def reference_translator(text):
    """Undo only this cycle's three exact translator edits, then prove the old hash."""
    assert text.count(NEW_LOG) == text.count(NEW_MASK) == text.count(DUMP_COMMENT) == 1
    text = text.replace(NEW_LOG, OLD_LOG).replace(NEW_MASK, OLD_MASK)
    start = text.index(DUMP_COMMENT)
    end = text.index('\n\n\t\tif (to_log_func)', start)
    block = text[start:end]
    prefix = DUMP_COMMENT + '\t\tif (g_cfg.core.spu_debug)\n\t\t{\n'
    assert block.startswith(prefix) and block.endswith('\n\t\t}')
    inner = block[len(prefix):-len('\n\t\t}')]
    assert all(line.startswith('\t') for line in inner.splitlines() if line)
    text = text[:start] + '\n'.join(line[1:] if line else line for line in inner.split('\n')) + text[end:]
    assert hashlib.sha256(text.encode()).hexdigest() == REFERENCE_LLVM_SHA256
    return text


def reference_thread(text):
    assert text.count(BRANCH_ADDITION) == 1
    text = text.replace(BRANCH_ADDITION, '')
    assert hashlib.sha256(text.encode()).hexdigest() == REFERENCE_THREAD_SHA256
    return text


def snippets(llvm, thread):
    masks = llvm.split('} s_masks[30]\n', 1)[1].split('\n\t\t\t\t};', 1)[0].strip() + '\n}'
    branch = thread.split('std::array<u32, 2> op_branch_targets(', 1)[1].split('\nstd::tuple<u32, std::array<u32, 3>, u32> op_register_targets', 1)[0]
    branch = 'std::array<u32, 2> op_branch_targets(' + branch
    diag = llvm.split('\t\tstd::string function_log;', 1)[1].split('\n\t\tusing namespace llvm;', 1)[0]
    diag = '\t\tstd::string function_log;' + diag
    return masks, branch, diag


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    args = parser.parse_args()
    core = args.source.resolve()
    llvm = (core / 'rpcs3/Emu/Cell/SPULLVMRecompiler.cpp').read_text()
    thread = (core / 'rpcs3/Emu/Cell/SPUThread.cpp').read_text()
    old_llvm, old_thread = reference_translator(llvm), reference_thread(thread)
    cmake = (core / 'rpcs3/Emu/CMakeLists.txt').read_text()
    digest = cmake.split('foreach(NEOSTATION_SPU_CODEGEN_SOURCE IN ITEMS', 1)[1].split(')', 1)[0]
    assert all(name in digest for name in ('Cell/SPULLVMRecompiler.cpp', 'Cell/SPUThread.cpp', 'Cell/SPUOpcodes.h'))
    ppu = cmake.split('foreach(NEOSTATION_PPU_CODEGEN_SOURCE IN ITEMS', 1)[1].split(')', 1)[0]
    assert 'Cell/SPUThread.cpp' not in ppu
    assert '#define RPCS3_IOS_ABI_VERSION 30u' in (core / 'rpcs3/ios/RPCS3IOS.h').read_text()
    compiler = shlex.split(os.environ.get('CXX') or shutil.which('clang++') or shutil.which('g++') or 'clang++')
    if sdk := os.environ.get('HOST_MACOS_SDK'):
        compiler += ['-isysroot', sdk]
    with tempfile.TemporaryDirectory(prefix='rpcs3-499-') as temporary:
        work = Path(temporary)
        for name, l, t in [('fixed', llvm, thread), ('reference', old_llvm, old_thread)]:
            for file, body in zip(('Masks.inc', 'Branch.inc', 'Diagnostics.inc'), snippets(l, t)):
                (work / file).write_text(body)
            exe = work / name
            command = [*compiler, '-std=gnu++20', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                '-I' + str(core), '-I' + str(core / 'rpcs3'), '-I' + str(work),
                str(ROOT / 'test/native/rpcs3_build499_spu_audit_test.cpp'), '-o', str(exe)]
            subprocess.run(command, check=True, timeout=120)
            subprocess.run([str(exe), name], check=True, timeout=30)
    print('PASS: Build 499 SHUFB masks, taken-first branches, debug-only dumps, exact pre-499 controls, SPU cache identity and ABI 30')


if __name__ == '__main__':
    main()
