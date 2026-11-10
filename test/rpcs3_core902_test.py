#!/usr/bin/env python3
"""Host tests of RPCS3 Core 902 = Core 668 + core901-from-668.patch + core902-from-901.patch (native Metal 4 renderer).

Core 902 (iOS): the native Metal 4 renderer of the Metal branch, stages M1 (device, MTL4 queue, allocators, residency,
compiler, presentation; build-utils/rpcs3/core901-delta.json) and M2 (RSX shaders to MSL through SPIRV-Cross and the draw
path; build-utils/rpcs3/core902-delta.json), opt-in per title (experimental.metal_renderer; Automatic keeps Vulkan). Metal 4
runs only on an iPhone: the GitHub macOS GPU is paravirtual and has no Metal 4. This driver:
- authenticates both increments against their records, requires each to start from the previous Core's files and to end on
  the source, reverts them (902 then 901), requires the reverted files to be the recorded Core 668 files, then applies them
  again byte for byte;
- builds and runs the presentation unit (display buffer conversion and aspect fit, MTLPresent.h), plain and ASan/UBSan;
- runs the Core 668 driver on the reverted tree (which runs the Core 664 suite and the earlier ones in turn).
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
STEPS = (
    ('core901', ROOT / 'build-utils/rpcs3/core901-from-668.patch', ROOT / 'build-utils/rpcs3/core901-delta.json', 'increment_from_core668'),
    ('core902', ROOT / 'build-utils/rpcs3/core902-from-901.patch', ROOT / 'build-utils/rpcs3/core902-delta.json', 'increment_from_core901'),
)
PRESENT_UNIT = ROOT / 'test/native/rpcs3_metal_present_unit.cpp'
METAL_FILES = ('rpcs3/Emu/RSX/Metal/MTLAPI.h', 'rpcs3/Emu/RSX/Metal/MTLAPIApple.mm', 'rpcs3/Emu/RSX/Metal/MTLGSRender.cpp',
               'rpcs3/Emu/RSX/Metal/MTLDraw.cpp', 'rpcs3/Emu/RSX/Metal/MTLShaderTranslator.cpp',
               '3rdparty/rewindbox-spirv-cross/spirv_msl.cpp', '3rdparty/rewindbox-spirv-cross/LICENSE')

sys.path.insert(0, str(ROOT / 'test'))
import rpcs3_core636_test as core636  # noqa: E402  (require, lf_sha)

require = core636.require


def patch_files(text: str) -> list:
    return re.findall(r'^diff --git a/(\S+) b/\S+$', text, re.M)


def check_increments(source: Path) -> dict:
    report = {}
    for name, patch, record_path, key in STEPS:
        increment = json.loads(record_path.read_text())[key]
        raw = patch.read_bytes()
        require(hashlib.sha256(raw).hexdigest() == increment['patch_sha256'], f'{patch.name} differs from its record')
        files = patch_files(raw.decode('utf-8', 'surrogateescape'))
        require(sorted(files) == sorted(increment['files_after_sha256']) and increment['files'] == len(files), name + ' files')
        require(sorted(increment['new_files']) == sorted(f for f in files if f not in increment['files_before_sha256']),
                name + ' new files')
        report[name] = {'files': len(files), 'new_files': len(increment['new_files']), 'patch_sha256': increment['patch_sha256']}
    # The 902 increment ends on the source; the 901 increment ends on the files the 902 increment starts from.
    last = json.loads(STEPS[1][2].read_text())[STEPS[1][3]]
    for name, digest in last['files_after_sha256'].items():
        require(core636.lf_sha(source / name) == digest, name + ' is not the reviewed Core 902 file')
    first = json.loads(STEPS[0][2].read_text())[STEPS[0][3]]
    for name, digest in last['files_before_sha256'].items():
        expected = first['files_after_sha256'].get(name)
        if expected is not None:
            require(digest == expected, name + ': the 902 increment does not start from the Core 901 file')
    for name in METAL_FILES:
        require((source / name).is_file(), name + ' is missing from the source')
    return report


def revert(source: Path, work: Path) -> Path:
    tree = work / 'core668'
    shutil.copytree(source, tree, ignore=shutil.ignore_patterns('.git'), symlinks=True)
    subprocess.run(['git', 'init', '-q'], cwd=tree, check=True)
    for name, patch, record_path, key in reversed(STEPS):
        increment = json.loads(record_path.read_text())[key]
        result = subprocess.run(['git', 'apply', '-R', '--whitespace=nowarn', str(patch)], cwd=tree, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True)
        require(result.returncode == 0, f'{patch.name} does not revert: ' + result.stdout[-2000:])
        for file_name, digest in increment['files_before_sha256'].items():
            require(core636.lf_sha(tree / file_name) == digest, f'{file_name} reverted ({name}) does not match its record')
        for file_name in increment['new_files']:
            require(not (tree / file_name).exists(), f'{file_name} survives the revert of {name}')
    # Forward again on a copy: both increments rebuild the source byte for byte.
    again = work / 'core902-again'
    shutil.copytree(tree, again, ignore=shutil.ignore_patterns('.git'), symlinks=True)
    subprocess.run(['git', 'init', '-q'], cwd=again, check=True)
    for name, patch, record_path, key in STEPS:
        result = subprocess.run(['git', 'apply', '--whitespace=nowarn', str(patch)], cwd=again, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True)
        require(result.returncode == 0, f'{patch.name} does not apply again: ' + result.stdout[-2000:])
    for name, patch, record_path, key in STEPS:
        for file_name in json.loads(record_path.read_text())[key]['files_after_sha256']:
            require((again / file_name).read_bytes() == (source / file_name).read_bytes(),
                    file_name + ': the increments do not rebuild the source')
    shutil.rmtree(again)
    return tree


def present_unit(source: Path, cxx: str, work: Path, sanitize: bool) -> dict:
    results = {}
    variants = [('plain', [])] + ([('asan-ubsan', ['-fsanitize=address,undefined', '-fno-sanitize-recover=undefined'])] if sanitize else [])
    for label, flags in variants:
        binary = work / f'metal-present-unit-{label}'
        command = [cxx, '-std=gnu++20', '-O1', '-Wall', '-I', str(source / 'rpcs3'), *flags, '-o', str(binary), str(PRESENT_UNIT)]
        built = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=600)
        require(built.returncode == 0, f'the presentation unit does not build ({label}):\n' + built.stdout[-3000:])
        ran = subprocess.run([str(binary)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=300)
        require(ran.returncode == 0, f'the presentation unit fails ({label}):\n' + ran.stdout[-3000:])
        results[label] = ran.stdout.strip().splitlines()[-1:] if ran.stdout.strip() else ['passed']
    return results


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
    with tempfile.TemporaryDirectory(prefix='core902-') as temporary:
        work = Path(temporary)
        print('increments')
        report['increments'] = check_increments(source)
        print('revert to Core 668 and apply again')
        tree668 = revert(source, work)
        print('presentation unit')
        report['presentUnit'] = present_unit(source, args.cxx, work, sanitize)
        print('core 668 driver on the reverted tree')
        command = [sys.executable, '-B', str(ROOT / 'test/rpcs3_core668_test.py'), '--source', str(tree668), '--cxx', args.cxx,
                   '--report', str(work / 'core668.json')] + (['--no-sanitizers'] if not sanitize else [])
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=14400)
        print('  ' + '\n  '.join(result.stdout.strip().splitlines()[-2:]))
        require(result.returncode == 0 and 'PASS: Core 668' in result.stdout, 'the Core 668 driver fails on the reverted tree:\n' +
                result.stdout[-3000:])
        report['core668'] = json.loads((work / 'core668.json').read_text())
    print('PASS: Core 902 increments (Metal M1 then M2) start from the recorded Core 668 and 901 files, revert and rebuild the '
          'source; presentation unit; the Core 668 driver on the reverted tree')
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
