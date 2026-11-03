#!/usr/bin/env python3
"""Authenticate the PPU/SPU codegen identities of Core 627 (unchanged from Core 624).

Core 627 = Core 624 + build-utils/rpcs3/core627-from-624.patch. One codegen input changes:
rpcs3/Emu/Cell/SPUThread.cpp (REWINDBOX_SPU_NOOP_SPIN_WAIT_627), in host code only: the no-op
path of do_putllc(), one include and one static thread_local. rpcs3/Emu/CPU/JITCacheCompatibility.cmake
maps the exact new hash to the effective hash the delivered Core already used, so the identities
PPU a987639e9f838d1c / SPU 477a3fa442d27917 and every cached PPU module and SPU object stay valid.

This audit reads the materialized Core 627 tree (source) and the delivered a4ae86d0 tree
(baseline). It requires that SPUThread.cpp is the only codegen input of the patch, that the
patch adds exactly one alias, for the exact hash of this file, to the effective hash of the Core
624 file, that the file differs from Core 624 only in do_putllc() and those two declarations,
and that SPUThread.h is untouched. It then reverses the patch on a copy of the tree, requires
every other codegen input byte-identical, and runs the Core 624 audit on that tree.
No compiler, CMake or LLVM is executed.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / 'build-utils/rpcs3/core627-from-624.patch'
COMPAT = 'rpcs3/Emu/CPU/JITCacheCompatibility.cmake'
SPU = 'rpcs3/Emu/Cell/SPUThread.cpp'
INCLUDE = '#include "ios/IOSSpuNoopSpin.h"\n'
THREAD_LOCAL = '''
#ifdef RPCS3_IOS
// REWINDBOX_SPU_NOOP_SPIN_WAIT_627 (ios/IOSSpuNoopSpin.h): per host thread, not a member of
// spu_thread, whose layout is a codegen input.
static thread_local rpcs3::ios::spu_noop_spin::tracker t_ios_noop_spin;
#endif
'''


def module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


c624 = module('core624_codegen', ROOT / 'test/rpcs3_core624_codegen_test.py')
c619 = c624.c619


def aliases(text: str) -> dict:
    return {actual: effective for source, actual, effective in re.findall(
        r'source STREQUAL "([^"]+)" AND\s+actual STREQUAL "([0-9a-f]{64})"\)\s+set\(\$\{output\} "([0-9a-f]{64})"', text)
        if source == 'Cell/SPUThread.cpp'}


def method(text: str, signature: str) -> str:
    begin = text.index(signature)
    depth, at = 0, text.index('{', begin)
    for at in range(at, len(text)):
        depth += (text[at] == '{') - (text[at] == '}')
        if not depth:
            return text[begin:at + 1]
    raise AssertionError('unbalanced ' + signature)


def audit(source: Path, baseline: Path) -> dict:
    files = re.findall(r'^diff --git a/(\S+) b/\S+$', PATCH.read_text('utf-8', 'surrogateescape'), re.M)
    inputs = c619.codegen_inputs(source)
    assert set(files) & set(inputs) == {SPU}, 'another codegen input changed: ' + repr(sorted(set(files) & set(inputs)))
    assert COMPAT in files and 'rpcs3/Emu/CMakeLists.txt' not in files, 'the identity recipe changed'
    with tempfile.TemporaryDirectory(prefix='core627-codegen-') as temporary:
        tree = Path(temporary) / 'core624'
        shutil.copytree(source, tree, ignore=shutil.ignore_patterns('.git', '3rdparty'), symlinks=True)
        subprocess.run(['git', 'init', '-q'], cwd=tree, check=True, timeout=60)
        subprocess.run(['git', 'apply', '-R', '--whitespace=nowarn', str(PATCH)], cwd=tree, check=True, timeout=120)
        for name in [*inputs, 'rpcs3/Emu/CMakeLists.txt']:
            if name != SPU and (source / name).exists():
                assert (tree / name).read_bytes() == (source / name).read_bytes(), name + ' differs from its Core 624 bytes'

        # The alias: the exact bytes of this file take the effective hash of the Core 624 file.
        new_raw, old_raw = (source / SPU).read_bytes(), (tree / SPU).read_bytes()
        new_sha, old_sha = hashlib.sha256(new_raw).hexdigest(), hashlib.sha256(old_raw).hexdigest()
        new_table, old_table = aliases((source / COMPAT).read_text()), aliases((tree / COMPAT).read_text())
        assert set(new_table) - set(old_table) == {new_sha} and all(new_table[key] == old_table[key] for key in old_table), 'alias table'
        assert new_table[new_sha] == old_table[old_sha], 'the new file does not keep the effective hash of Core 624'

        # Host code only: do_putllc(), the include, the thread_local.
        new, old = new_raw.decode('utf-8', 'surrogateescape'), old_raw.decode('utf-8', 'surrogateescape')
        signature = 'bool spu_thread::do_putllc(const spu_mfc_cmd& args)'
        assert new.count(INCLUDE) == 1 and new.count(THREAD_LOCAL) == 1, 'the two declarations'
        stripped = new.replace(INCLUDE, '', 1).replace(THREAD_LOCAL, '', 1)
        assert stripped.replace(method(stripped, signature), method(old, signature), 1) == old, 'SPUThread.cpp changes outside do_putllc()'
        for name in ('process_mfc_cmd', 'get_ch_value', 'set_ch_value'):
            head = {'process_mfc_cmd': 'bool spu_thread::process_mfc_cmd()', 'get_ch_value': 's64 spu_thread::get_ch_value(u32 ch)',
                    'set_ch_value': 'bool spu_thread::set_ch_value(u32 ch, u32 value)'}[name]
            assert method(new, head) == method(old, head), name + ' changed'
        report624 = c624.audit(tree, baseline)
    report619 = report624['core621_audit']['core619_audit']
    assert report619['core616_audit']['codegen']['PPU']['candidate'] == 'a987639e9f838d1c'
    assert report619['core616_audit']['codegen']['SPU']['candidate'] == '477a3fa442d27917'
    return dict(passed=True, core627_files=sorted(files), codegen_inputs_checked=len(inputs), changed_codegen_input=SPU,
                spu_thread_sha256=new_sha, effective_sha256=new_table[new_sha], core624_audit=report624,
                compiler_executed=False, cmake_executed=False,
                scope='Core 627 changes one codegen input in host code only, with an exact alias; the Core 624 audit holds on the reversed tree; no gameplay claim')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('source', type=Path)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    report = audit(args.source.resolve(), args.baseline.resolve())
    text = json.dumps(report, indent=2) + '\n'
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text)
    print(text, end='')


if __name__ == '__main__':
    main()
