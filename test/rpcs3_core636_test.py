#!/usr/bin/env python3
"""Host tests of RPCS3 Core 636 = Core 634 + build-utils/rpcs3/core636-from-634.patch.

Core 636 carries the three corrections of the independent Core 634 audit and one shorter guest wait:
- REWINDBOX_GUEST_ACCESS_FP_LR_636 (Utilities/Thread.cpp, ios/IOSGuestAccessEmulation.h): the ZCULL fault handler
  (Core 630) no longer reads or writes X29/X30 through Darwin's __x[29]; such an access keeps the retry
  (test/rpcs3_core636/guest_access_fp_lr_test.cpp, Darwin register layout, bounds-checked);
- REWINDBOX_SPIRV_CAP_636 (ios/IOSSpirvCache.h): the 256 MiB bound counts the batch flush() is writing and the
  header (test/rpcs3_core636/spirv_cache_cap_test.cpp, the audit's 840 + 840 bytes sequence, an empty file, six
  adders near the bound);
- REWINDBOX_PPU_CHECK_STOP_636 (rpcs3/Emu/Cell/PPUThread.cpp): the parallel check pass assigns no check after a
  missing object or a stop (test/rpcs3_core636/jit_check_test.cpp, extracted from PPUThread.cpp);
- REWINDBOX_ZCULL_SLOT_WAKE_636 (rpcs3/Emu/RSX/RSXZCULL.cpp, ios/IOSZcullOnDemand.h): a guest's pause before asking
  for its ZCULL report slot again ends at a slot release (test/rpcs3_core636/slot_wake_test.cpp).
This driver:
- authenticates the increment against its record and reverts it to the pinned Core 634 files;
- runs the four fixtures on this tree, and the three correction fixtures on the reverted Core 634 tree, where each
  must fail (the defect is reproduced, so the fixture tests it);
- runs the Core 634 suite on the reverted tree (which runs the Core 630 and 627 suites in turn).
No gameplay, iPhone or FPS claim.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / 'test/rpcs3_core636'
DELTA = ROOT / 'build-utils/rpcs3/core636-from-634.patch'
RECORD = ROOT / 'build-utils/rpcs3/core636-delta.json'

sys.path.insert(0, str(ROOT / 'test'))
import rpcs3_core621_test as core621  # noqa: E402  (shared helpers: require, run)
import rpcs3_core630_test as core630  # noqa: E402  (a64_block)
import rpcs3_core634_test as core634  # noqa: E402  (extract)

require = core621.require


def lf_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def build(cxx: str, sources: list, output: Path, includes: list, flags: list) -> subprocess.CompletedProcess:
    command = [cxx, '-std=gnu++20', *flags, *[f'-I{path}' for path in includes], *map(str, sources), '-o', str(output), '-pthread', '-lz']
    result, _ = core621.run(command, timeout=1200)
    require(result.returncode == 0, f'compile {output.name} failed:\n' + result.stdout[-4000:])
    return result


def execute(command: list, timeout: int = 1800) -> tuple[int, str]:
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout)
    return result.returncode, result.stdout


def last_json(output: str) -> dict:
    lines = [line for line in output.splitlines() if line.startswith('{')]
    return json.loads(lines[-1]) if lines else {}


def check_increment(source: Path) -> dict:
    increment = json.loads(RECORD.read_text())['increment_from_core634']
    raw = DELTA.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == increment['patch_sha256'], 'core636-from-634.patch differs from its record')
    files = re.findall(r'^diff --git a/(\S+) b/\S+$', raw.decode('utf-8', 'surrogateescape'), re.M)
    require(files and increment['files'] == len(files) == len(increment['files_after_sha256']), 'core636-from-634.patch files')
    for name in files:
        require(lf_sha(source / name) == increment['files_after_sha256'][name], name + ' is not the reviewed Core 636 file')
    return {'files': len(files), 'patch_sha256': increment['patch_sha256']}


def core634_tree(source: Path, work: Path) -> Path:
    increment = json.loads(RECORD.read_text())['increment_from_core634']
    tree = work / 'core634'
    shutil.copytree(source, tree, ignore=shutil.ignore_patterns('.git', '3rdparty'), symlinks=True)
    subprocess.run(['git', 'init', '-q'], cwd=tree, check=True)
    result = subprocess.run(['git', 'apply', '-R', '--whitespace=nowarn', str(DELTA)], cwd=tree,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    require(result.returncode == 0, 'the Core 634 tree cannot be rebuilt: ' + result.stdout[-2000:])
    for name, digest in increment['files_before_sha256'].items():
        require(lf_sha(tree / name) == digest, name + ' reverted does not match its pinned Core 634 SHA-256')
    return tree


def fp_lr(tree: Path, cxx: str, folder: Path, label: str) -> tuple[int, str]:
    folder.mkdir(parents=True)
    (folder / 'a64_block.inc').write_text(core630.a64_block(tree), 'utf-8', 'surrogateescape')
    output = folder / 'fp_lr'
    build(cxx, [HERE / 'guest_access_fp_lr_test.cpp'], output, [tree / 'rpcs3', folder],
          ['-O1', '-g', '-DRPCS3_IOS=1', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function',
           '-fsanitize=bounds,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer'])
    return execute([str(output)])


def spirv_cap(tree: Path, cxx: str, folder: Path, label: str) -> tuple[int, str]:
    folder.mkdir(parents=True)
    output = folder / 'spirv_cap'
    build(cxx, [HERE / 'spirv_cache_cap_test.cpp', tree / 'rpcs3/Crypto/sha256.cpp'], output, [tree / 'rpcs3', tree],
          ['-O1', '-g', '-DRPCS3_IOS=1'])
    data = folder / 'files'
    data.mkdir()
    return execute([str(output), str(data)])


def jit_check(tree: Path, cxx: str, folder: Path, label: str, sanitize: bool) -> tuple[int, str]:
    folder.mkdir(parents=True)
    ppu = (tree / 'rpcs3/Emu/Cell/PPUThread.cpp').read_text('utf-8', 'surrogateescape')
    begin = 'template <typename Job, typename Stop>\nvoid ios_run_link_jobs(' if 'typename Stop>\nvoid ios_run_link_jobs(' in ppu \
        else 'template <typename Job>\nvoid ios_run_link_jobs('
    (folder / 'ppu_link_jobs.inc').write_text(core634.extract(ppu, begin, '\n}\n}\n') + '\n}\n', 'utf-8', 'surrogateescape')
    (folder / 'ppu_check_block.inc').write_text(core634.extract(ppu, 'atomic_t<u32> ios_missing = 0;', '#else\n\t\treturn false;'),
                                                'utf-8', 'surrogateescape')
    flags = ['-O1', '-g', '-Wall', '-Wextra', '-Wno-unused-function']
    if sanitize:
        flags += ['-fsanitize=address,undefined', '-fno-sanitize-recover=undefined', '-fno-omit-frame-pointer']
    output = folder / 'jit_check'
    build(cxx, [HERE / 'jit_check_test.cpp'], output, [tree / 'rpcs3', folder], flags)
    return execute([str(output)])


def slot_wake(tree: Path, cxx: str, folder: Path, sanitize: bool) -> dict:
    folder.mkdir(parents=True)
    report = {}
    sets = {'plain': ['-O1', '-g']}
    if sanitize:
        sets['tsan'] = ['-O1', '-g', '-fsanitize=thread'] + ([] if 'clang' in Path(cxx).name else ['-Wno-tsan'])
    for name, flags in sets.items():
        output = folder / ('slot_wake-' + name)
        build(cxx, [HERE / 'slot_wake_test.cpp'], output, [tree / 'rpcs3'], flags + ['-DRPCS3_IOS=1', '-Wall', '-Wextra'])
        code, text = execute([str(output)])
        require(code == 0 and last_json(text).get('failures') == 0, f'slot wake ({name}) failed:\n' + text[-3000:])
        report[name] = [json.loads(line) for line in text.splitlines() if line.startswith('{')]
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--cxx', default='g++')
    parser.add_argument('--report', type=Path)
    parser.add_argument('--no-sanitizers', action='store_true')
    args = parser.parse_args()
    source = args.source.resolve()
    sanitize = not args.no_sanitizers
    report: dict = {'cxx': args.cxx}
    with tempfile.TemporaryDirectory(prefix='core636-') as temporary:
        work = Path(temporary)
        print('increment')
        report['increment'] = check_increment(source)
        tree634 = core634_tree(source, work)

        print('X29/X30 in the ZCULL fault handler')
        code, text = fp_lr(source, args.cxx, work / 'fp_lr-636', 'core636')
        result = last_json(text)
        require(code == 0 and result.get('failures') == 0 and result.get('refused') == 14 and result.get('completed') == 2,
                'X29/X30 fixture fails on Core 636:\n' + text[-3000:])
        code634, text634 = fp_lr(tree634, args.cxx, work / 'fp_lr-634', 'core634')
        require(code634 != 0, 'the X29/X30 fixture does not reproduce the Core 634 defect')
        report['fp_lr'] = {'core636': result, 'core634_reproduced': 'out of bounds' in text634 or 'accepted:' in text634}

        print('SPIR-V pack bound')
        code, text = spirv_cap(source, args.cxx, work / 'spirv-636', 'core636')
        require(code == 0 and last_json(text).get('failures') == 0, 'SPIR-V bound fixture fails on Core 636:\n' + text[-3000:])
        code634, text634 = spirv_cap(tree634, args.cxx, work / 'spirv-634', 'core634')
        require(code634 != 0, 'the SPIR-V bound fixture does not reproduce the Core 634 defect')
        report['spirv_cap'] = {'core636': [json.loads(line) for line in text.splitlines() if line.startswith('{')],
                               'core634': [json.loads(line) for line in text634.splitlines() if line.startswith('{')]}

        print('PPU check pass')
        code, text = jit_check(source, args.cxx, work / 'jit-636', 'core636', sanitize)
        require(code == 0 and last_json(text).get('failures') == 0, 'PPU check fixture fails on Core 636:\n' + text[-3000:])
        code634, text634 = jit_check(tree634, args.cxx, work / 'jit-634', 'core634', sanitize)
        require(code634 != 0, 'the PPU check fixture does not reproduce the Core 634 defect')
        report['jit_check'] = {'core636': last_json(text), 'core634': last_json(text634)}

        print('ZCULL slot wake')
        report['slot_wake'] = slot_wake(source, args.cxx, work / 'slot_wake', sanitize)

        print('core 634 suite on the reverted tree')
        command = [sys.executable, str(ROOT / 'test/rpcs3_core634_test.py'), '--source', str(tree634), '--cxx', args.cxx,
                   '--report', str(work / 'core634.json')] + (['--no-sanitizers'] if not sanitize else [])
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=7200)
        print('  ' + '\n  '.join(result.stdout.strip().splitlines()[-3:]))
        require(result.returncode == 0 and 'PASS: Core 634' in result.stdout, 'the Core 634 suite fails on the reverted tree:\n' + result.stdout[-3000:])
        report['core634'] = json.loads((work / 'core634.json').read_text())
    print('PASS: Core 636 increment reverts to Core 634; X29/X30, SPIR-V bound and PPU check fixed (each reproduced on '
          'Core 634); slot wake; the Core 634 suite on that tree')
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
