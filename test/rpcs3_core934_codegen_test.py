#!/usr/bin/env python3
"""Authenticate the PPU/SPU codegen identities of Core 934 (Core 933 plus the settings API rule and the Metal stretch: the iOS settings
API and the Metal present, none of them a codegen input). Core 933 = Core 932 plus the local profile: new iOS headers, the boot read, the title
policy and the report, none of them a codegen input). Core 932 = Core 931 plus the ARMSX3 lot and the first audit fixes: the patch engine,
the boot layering, the report, the JIT fallback step, the texture prehash budget, MoltenVK settings and new iOS headers, none of them a
codegen input). Core 931 = Core 930 plus the thermal chantier (vm.cpp, RSXFIFO.cpp, the report, the
platform observers, the settings and new iOS headers, none of them a codegen input). Core 930 = Core 929 plus the SPU wait sites of the
SPU region profile (a new iOS header and the profile sampler, neither of them a codegen input). Core 929 = Core 928 without the MLAA pair written into restored savestate memory:
the PPU loader and the MLAA report header, neither of them a codegen input). Core 928 = Core 927 plus the GPU gate closed at the deactivation: the gate header,
the application observers, the renderer's settle function and the report, none of them a codegen input). Core 927 = Core 926 plus asynchronous MoltenVK submits made definitive: the
encoding-queue headers, the background gate, the Vulkan renderer, the settings text, the policy and the report, none of them a
codegen input). Core 926 = Core 925 plus two Black Ops II levers: the title levers, the canary
record name and the settings text, none of them a codegen input). Core 925 = Core 924 plus GPU memory packing: the Vulkan memory allocator, a new
header, the settings, the policy and the report, none of them a codegen input). Core 924 = Core 923 plus the deferral before the line lock: SPUThread.cpp changes in
the host body of do_putllc() only, plus one include, with one exact alias; vm.cpp and the gate header are not codegen inputs).
Core 923 = Core 922 plus the SPU region profile and the memory ledger line: the
capture header, the freeze dump and the report, none of them a codegen input). Core 922 = Core 921 plus the God of War III MLAA bypass on resumed savestates
and the freeze dump reservation words: PPUModule.cpp, the MLAA report header and the freeze dump, none of them a codegen input).
Core 921 = Core 920 plus the release of stale idle textures: the texture cache,
its sections and header, the Vulkan renderer, the settings, the policy and the report, none of them a codegen input). Core 920 =
Core 919 plus the lever comparison on request and the ZCULL cost line:
the settings, the policy, the comparison and ZCULL headers, RSXZCULL.cpp, the Vulkan renderer and the report, none of them a
codegen input). Core 919 = Core 918 plus the ZCULL watched flush of Black Ops II and its own
budget: the title list, the watched header, the Vulkan renderer and the policy, none of them a codegen input). Core 918 = Core
917 plus the busy wait reference duration, the scheduler
counts and the two-lever comparison: util/asm.hpp, the lever helpers, the settings, the policy and the report, none of them a
codegen input). Core 917 = Core 916 plus the writer park spin, the park counters and the automatic storm captures (vm.cpp, the
settings, the policy, the report and the capture files, none of them a codegen input)
with the Core 916 audit: Core 916 (Core 914 plus one more host-body change of do_putllc(), the
store of a SPURS header line with relaxed reservations, and its include; Core 915 was a witness of 914, not an increment).
Core 914 = Core 912 plus one more host-body change of do_putllc(), the capture generation; Core 913 was a witness of 912. As for Core 912: no codegen input changes (Core 908: vm.cpp, the memo, the profiler
and the freeze dump; Core 909: the NV47 method handlers, RSXThread, the Vulkan renderer, PPUModule.cpp and sys_spu.cpp; Core 910: RSXFIFO,
the texture cache, the prehash and memo headers, the pass census and the policy/settings files; are not inputs. Core 911 and Core 912 each change one input,
SPUThread.cpp, in the host body of do_putllc() only (912 adds one include), each with one exact alias in
JITCacheCompatibility.cmake (as Core 627 did).

Core 903 = Core 668 + build-utils/rpcs3/core901-from-668.patch (the native Metal 4 renderer, stage M1) +
build-utils/rpcs3/core902-from-901.patch (stage M2: shaders to MSL through SPIRV-Cross, the draw path) +
build-utils/rpcs3/core903-from-902.patch (stages M3 and M4: textures, queries, MSAA, conversion kernels, overlays) +
build-utils/rpcs3/core904-from-903.patch (Utilities/JITIOS.cpp high window, Metal M5 part 1, M3 gaps, rsx_cache.h). The
increments add the Metal sources to rpcs3/Emu/CMakeLists.txt, the file that carries the codegen identity recipe, so this audit
recomputes the ordered identity recipe of the source and requires the delivered identities: every cached PPU module
and SPU object stays valid. It reads the materialized Core 911 tree (source) and the delivered a4ae86d0 tree
(baseline); no compiler, CMake or LLVM is executed. It requires:
- no file of either increment is a codegen input, and the compatibility table is untouched;
- the identities computed from the source are the delivered PPU/SPU identities;
- with every increment reversed, the Core 668 audit passes (which runs the 665, 664 and earlier audits in turn) and every
  codegen input is byte-identical between the reversed tree and the source.
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
PATCHES = (ROOT / 'build-utils/rpcs3/core934-from-933.patch', ROOT / 'build-utils/rpcs3/core933-from-932.patch', ROOT / 'build-utils/rpcs3/core932-from-931.patch', ROOT / 'build-utils/rpcs3/core931-from-930.patch', ROOT / 'build-utils/rpcs3/core930-from-929.patch', ROOT / 'build-utils/rpcs3/core929-from-928.patch', ROOT / 'build-utils/rpcs3/core928-from-927.patch', ROOT / 'build-utils/rpcs3/core927-from-926.patch', ROOT / 'build-utils/rpcs3/core926-from-925.patch', ROOT / 'build-utils/rpcs3/core925-from-924.patch', ROOT / 'build-utils/rpcs3/core924-from-923.patch', ROOT / 'build-utils/rpcs3/core923-from-922.patch', ROOT / 'build-utils/rpcs3/core922-from-921.patch', ROOT / 'build-utils/rpcs3/core921-from-920.patch', ROOT / 'build-utils/rpcs3/core920-from-919.patch', ROOT / 'build-utils/rpcs3/core919-from-918.patch', ROOT / 'build-utils/rpcs3/core918-from-917.patch', ROOT / 'build-utils/rpcs3/core917-from-916.patch', ROOT / 'build-utils/rpcs3/core916-from-914.patch', ROOT / 'build-utils/rpcs3/core914-from-912.patch', ROOT / 'build-utils/rpcs3/core912-from-911.patch', ROOT / 'build-utils/rpcs3/core911-from-910.patch', ROOT / 'build-utils/rpcs3/core910-from-909.patch', ROOT / 'build-utils/rpcs3/core909-from-908.patch', ROOT / 'build-utils/rpcs3/core908-from-907.patch', ROOT / 'build-utils/rpcs3/core907-from-906.patch', ROOT / 'build-utils/rpcs3/core906-from-905.patch', ROOT / 'build-utils/rpcs3/core905-from-904.patch', ROOT / 'build-utils/rpcs3/core904-from-903.patch', ROOT / 'build-utils/rpcs3/core903-from-902.patch', ROOT / 'build-utils/rpcs3/core902-from-901.patch',
           ROOT / 'build-utils/rpcs3/core901-from-668.patch')


def module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


c668 = module('core668_codegen', ROOT / 'test/rpcs3_core668_codegen_test.py')
c665 = c668.c665
c619, c616, c610 = c665.c619, c665.c616, c665.c610


def increment_files() -> set:
    files = set()
    for patch in PATCHES:
        files |= set(re.findall(r'^diff --git a/(\S+) b/\S+$', patch.read_text('utf-8', 'surrogateescape'), re.M))
    return files


def identities(source: Path) -> dict:
    compat = (source / c610.COMPAT).read_text()
    cmake_text = (source / c610.CMAKE).read_text()
    current = c610.aliases(compat)
    return {kind: c616.identity(source, cmake_text, current, kind)[0] for kind in ('PPU', 'SPU')}


SPU = 'rpcs3/Emu/Cell/SPUThread.cpp'
SIGNATURES = {'do_putllc': 'bool spu_thread::do_putllc(const spu_mfc_cmd& args)', 'process_mfc_cmd': 'bool spu_thread::process_mfc_cmd()',
              'get_ch_value': 's64 spu_thread::get_ch_value(u32 ch)', 'set_ch_value': 'bool spu_thread::set_ch_value(u32 ch, u32 value)'}


def patch_files(patch: Path) -> set:
    return set(re.findall(r'^diff --git a/(\S+) b/\S+$', patch.read_text('utf-8', 'surrogateescape'), re.M))


def spu_aliases(text: str) -> dict:
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


INCLUDE912 = '#include "ios/IOSCapture912.h"\n'
INCLUDE916 = '#include "ios/IOSSpursRelaxedStore.h" // REWINDBOX_SPURS_RELAXED_STORE_916\n'
INCLUDE924 = '#include "ios/IOSPassiveLockGate.h" // REWINDBOX_GATE_BEFORE_LINE_924\n'


def host_only_step(tree: Path, patch: Path, label: str, allowed_include: str = '') -> dict:
    """Reverse `patch` on `tree` and require: SPUThread.cpp is its only codegen input, it differs only inside
    do_putllc() (plus `allowed_include`), and the patch adds exactly one alias, for the exact new file, to the effective
    hash of the file before it."""
    inputs = c619.codegen_inputs(tree)
    files = patch_files(patch)
    assert files & set(inputs) == {SPU}, f'{label} codegen inputs: ' + repr(sorted(files & set(inputs)))
    assert c610.COMPAT in files and c610.CMAKE not in files and 'rpcs3/Emu/Cell/SPUThread.h' not in files, label + ': the identity recipe or the SPU layout changed'
    new_raw, compat_new = (tree / SPU).read_bytes(), (tree / c610.COMPAT).read_text()
    subprocess.run(['git', 'apply', '-R', '--whitespace=nowarn', str(patch)], cwd=tree, check=True, timeout=300)
    old_raw, compat_old = (tree / SPU).read_bytes(), (tree / c610.COMPAT).read_text()
    new_sha, old_sha = hashlib.sha256(new_raw).hexdigest(), hashlib.sha256(old_raw).hexdigest()
    new_table, old_table = spu_aliases(compat_new), spu_aliases(compat_old)
    assert set(new_table) - set(old_table) == {new_sha} and all(new_table[key] == old_table[key] for key in old_table), label + ': alias table'
    assert new_table[new_sha] == old_table[old_sha], label + ': the new file does not keep the effective hash of the file before'
    assert len(c610.aliases(compat_new)) == len(c610.aliases(compat_old)) + 1, label + ': exactly one alias added'
    new, old = new_raw.decode('utf-8', 'surrogateescape'), old_raw.decode('utf-8', 'surrogateescape')
    if allowed_include:
        assert new.count(allowed_include) == 1 and old.count(allowed_include) == 0, label + ': the include'
        new = new.replace(allowed_include, '', 1)
    assert new.replace(method(new, SIGNATURES['do_putllc']), method(old, SIGNATURES['do_putllc']), 1) == old, label + ': SPUThread.cpp changes outside do_putllc()'
    for name in ('process_mfc_cmd', 'get_ch_value', 'set_ch_value'):
        assert method(new, SIGNATURES[name]) == method(old, SIGNATURES[name]), f'{label}: {name} changed'
    return {'spu_thread_sha256': new_sha, 'effective_sha256': new_table[new_sha]}


def audit(source: Path, baseline: Path) -> dict:
    # Core 924 changes SPUThread.cpp the same way (do_putllc() only, one include, one exact alias).
    # Core 901 to 910 touch no codegen input. Core 911 and Core 912 each change one, SPUThread.cpp, in the host body of
    # do_putllc() only (912 adds one include), each with one exact alias to the effective hash the delivered Core
    # already used (the Core 627 procedure).
    inputs = c619.codegen_inputs(source)
    older = set()
    for patch in PATCHES[:10] + PATCHES[11:18] + PATCHES[22:]:
        older |= patch_files(patch)
    assert not older & set(inputs) and c610.COMPAT not in older, 'an older increment changed a codegen input'
    result = identities(source)
    for kind, candidate in result.items():
        assert candidate == c610.DELIVERED[kind], kind + ' identity changed: ' + candidate

    with tempfile.TemporaryDirectory(prefix='core934-codegen-') as temporary:
        tree = Path(temporary) / 'core668'
        shutil.copytree(source, tree, ignore=shutil.ignore_patterns('.git'), symlinks=True)
        subprocess.run(['git', 'init', '-q'], cwd=tree, check=True, timeout=60)
        for index, name in ((0, 'Core 934'), (1, 'Core 933'), (2, 'Core 932'), (3, 'Core 931'), (4, 'Core 930'), (5, 'Core 929'), (6, 'Core 928'), (7, 'Core 927'), (8, 'Core 926'), (9, 'Core 925')):
            assert not patch_files(PATCHES[index]) & set(inputs) and c610.COMPAT not in patch_files(PATCHES[index]), name + ' changes a codegen input'
            subprocess.run(['git', 'apply', '-R', '--whitespace=nowarn', str(PATCHES[index])], cwd=tree, check=True, timeout=300)
            assert identities(tree) == result, 'the tree before ' + name + ' computes other identities'
        step924 = host_only_step(tree, PATCHES[10], 'Core 924', INCLUDE924)
        assert identities(tree) == result, 'the Core 923 tree computes other identities'
        for index, name in ((11, 'Core 923'), (12, 'Core 922'), (13, 'Core 921'), (14, 'Core 920'), (15, 'Core 919'), (16, 'Core 918'), (17, 'Core 917')):
            assert not patch_files(PATCHES[index]) & set(inputs) and c610.COMPAT not in patch_files(PATCHES[index]), name + ' changes a codegen input'
            subprocess.run(['git', 'apply', '-R', '--whitespace=nowarn', str(PATCHES[index])], cwd=tree, check=True, timeout=300)
            assert identities(tree) == result, 'the tree before ' + name + ' computes other identities'
        step916 = host_only_step(tree, PATCHES[18], 'Core 916', INCLUDE916)
        assert identities(tree) == result, 'the Core 914 tree computes other identities'
        step914 = host_only_step(tree, PATCHES[19], 'Core 914')
        assert identities(tree) == result, 'the Core 912 tree computes other identities'
        step912 = host_only_step(tree, PATCHES[20], 'Core 912', INCLUDE912)
        assert identities(tree) == result, 'the Core 911 tree computes other identities'
        step911 = host_only_step(tree, PATCHES[21], 'Core 911')
        for patch in PATCHES[22:]:
            subprocess.run(['git', 'apply', '-R', '--whitespace=nowarn', str(patch)], cwd=tree, check=True, timeout=300)
        for name in inputs:
            if name != SPU and (source / name).exists():
                assert (tree / name).read_bytes() == (source / name).read_bytes(), name + ' differs from its Core 668 bytes'
        reversed_identities = identities(tree)
        assert reversed_identities == result, 'the reversed Core 668 tree computes other identities'
        report668 = c668.audit(tree, baseline)

    return dict(passed=True, codegen=result, new_exact_aliases=5, changed_codegen_input=SPU, core924=step924, core916=step916, core914=step914, core912=step912, core911=step911,
                identity_recipe_file_changed=False, core668_audit=report668, compiler_executed=False, cmake_executed=False,
                emitted_objects_compared=False,
                scope='Core 911, 912, 914, 916 and 924 each change one codegen input in the host body of do_putllc() only, each with one exact '
                      'alias; the ordered CMake identity recipe and exact host-code snapshots; no gameplay claim')


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
    print(text)


if __name__ == '__main__':
    main()
