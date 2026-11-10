#!/usr/bin/env python3
"""Host tests of RPCS3 Core 906 = Core 668 + the core901 to core906 increments.

Core 906: retired game-setting overrides skipped and pruned (RPCS3IOSSettings.cpp, executed by
test/rpcs3_retired_overrides906_test.py) and the timed COREPROF METAL report with the drain state line.

Core 904 (iOS): the JIT arena high window (Utilities/JITIOS.cpp, iOS 27) and the native Metal 4 renderer of the Metal branch, stages M1 (build-utils/rpcs3/core901-delta.json), M2
(core902-delta.json), M3+M4 (core903-delta.json) and M5 part 1 + M3 gaps (core904-delta.json; the texture cache, uploads, samplers, render-to-texture and readback;
exact occlusion queries, MSAA resolve, conversion kernels and native overlays), opt-in per title
(experimental.metal_renderer; Automatic keeps Vulkan). Metal 4 runs only on an iPhone: the GitHub macOS GPU is paravirtual
and has no Metal 4. This driver:
- authenticates the three increments against their records, requires each to start from the previous Core's files and the
  last one to end on the source, reverts them (903, 902, 901), requires the reverted files to be the recorded Core 668 files,
  then applies them again byte for byte;
- builds and runs the presentation unit (MTLPresent.h) and every host test the renderer carries
  (rpcs3/Emu/RSX/Metal/tests/*.cpp: texture formats, samplers, D24 round trip, query rules, kernel and MSAA math), plain and
  ASan/UBSan;
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
    ('core903', ROOT / 'build-utils/rpcs3/core903-from-902.patch', ROOT / 'build-utils/rpcs3/core903-delta.json', 'increment_from_core902'),
    ('core904', ROOT / 'build-utils/rpcs3/core904-from-903.patch', ROOT / 'build-utils/rpcs3/core904-delta.json', 'increment_from_core903'),
    ('core905', ROOT / 'build-utils/rpcs3/core905-from-904.patch', ROOT / 'build-utils/rpcs3/core905-delta.json', 'increment_from_core904'),
    ('core906', ROOT / 'build-utils/rpcs3/core906-from-905.patch', ROOT / 'build-utils/rpcs3/core906-delta.json', 'increment_from_core905'),
)
PRESENT_UNIT = ROOT / 'test/native/rpcs3_metal_present_unit.cpp'
METAL_FILES = ('rpcs3/Emu/RSX/Metal/MTLAPI.h', 'rpcs3/Emu/RSX/Metal/MTLAPIApple.mm', 'rpcs3/Emu/RSX/Metal/MTLGSRender.cpp',
               'rpcs3/Emu/RSX/Metal/MTLDraw.cpp', 'rpcs3/Emu/RSX/Metal/MTLShaderTranslator.cpp',
               '3rdparty/rewindbox-spirv-cross/spirv_msl.cpp', '3rdparty/rewindbox-spirv-cross/LICENSE',
               'rpcs3/Emu/RSX/Metal/MTLTextureCache.cpp', 'rpcs3/Emu/RSX/Metal/MTLTexture.cpp',
               'rpcs3/Emu/RSX/Metal/MTLQueries.cpp', 'rpcs3/Emu/RSX/Metal/MTLResolve.cpp',
               'rpcs3/Emu/RSX/Metal/MTLComputeTasks.cpp', 'rpcs3/Emu/RSX/Metal/MTLOverlays.cpp',
               'rpcs3/Emu/RSX/Metal/MTLPipelineArchive.cpp', 'rpcs3/Emu/RSX/Metal/MTLM5Renderer.cpp')

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
    # The last increment ends on the source; each increment starts from the files the previous one ends on.
    records = [json.loads(record_path.read_text())[key] for name, patch, record_path, key in STEPS]
    for name, digest in records[-1]['files_after_sha256'].items():
        require(core636.lf_sha(source / name) == digest, name + ' is not the reviewed Core 906 file')
    for (previous_name, *_), previous, (name, *_), current in zip(STEPS, records, STEPS[1:], records[1:]):
        for file_name, digest in current['files_before_sha256'].items():
            expected = previous['files_after_sha256'].get(file_name)
            if expected is not None:
                require(digest == expected, f'{file_name}: the {name} increment does not start from the {previous_name} file')
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
    again = work / 'core906-again'
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


def metal_host_tests(source: Path, cxx: str, work: Path, sanitize: bool) -> dict:
    """Every host test the renderer sources carry, plain and ASan/UBSan; each may write MSL libraries to its argument."""
    results = {}
    tests = sorted((source / 'rpcs3/Emu/RSX/Metal/tests').glob('*.cpp'))
    require(len(tests) >= 2, 'the Metal renderer host tests are missing: ' + repr([t.name for t in tests]))
    includes = ['-I', str(source / 'rpcs3'), '-I', str(source), '-I', str(source / 'rpcs3/Emu'), '-I', str(source / '3rdparty')]
    variants = [('plain', [])] + ([('asan-ubsan', ['-fsanitize=address,undefined', '-fno-sanitize-recover=undefined'])] if sanitize else [])
    for test in tests:
        for label, flags in variants:
            binary = work / f'{test.stem}-{label}'
            msl = work / f'{test.stem}-{label}-msl'
            msl.mkdir(exist_ok=True)
            built = subprocess.run([cxx, '-std=gnu++20', '-O1', '-Wall', *includes, *flags, '-o', str(binary), str(test)],
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=900)
            require(built.returncode == 0, f'{test.name} does not build ({label}):\n' + built.stdout[-3000:])
            ran = subprocess.run([str(binary), str(msl)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=1800)
            require(ran.returncode == 0 and 'PASS' in ran.stdout, f'{test.name} fails ({label}):\n' + ran.stdout[-3000:])
            results[f'{test.stem}-{label}'] = ran.stdout.strip().splitlines()[-1]
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
    with tempfile.TemporaryDirectory(prefix='core906-') as temporary:
        work = Path(temporary)
        print('increments')
        report['increments'] = check_increments(source)
        print('revert to Core 668 and apply again')
        tree668 = revert(source, work)
        print('presentation unit')
        report['presentUnit'] = present_unit(source, args.cxx, work, sanitize)
        print('renderer host tests')
        report['metalHostTests'] = metal_host_tests(source, args.cxx, work, sanitize)
        print('retired game-setting overrides (906)')
        retired = subprocess.run([sys.executable, '-B', str(ROOT / 'test/rpcs3_retired_overrides906_test.py'), '--source', str(source),
                                  '--cxx', args.cxx], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=600)
        require(retired.returncode == 0 and 'PASS' in retired.stdout, 'retired override test fails:\n' + retired.stdout[-3000:])
        report['retiredOverrides906'] = retired.stdout.strip().splitlines()[-1]
        print('core 668 driver on the reverted tree')
        command = [sys.executable, '-B', str(ROOT / 'test/rpcs3_core668_test.py'), '--source', str(tree668), '--cxx', args.cxx,
                   '--report', str(work / 'core668.json')] + (['--no-sanitizers'] if not sanitize else [])
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=14400)
        print('  ' + '\n  '.join(result.stdout.strip().splitlines()[-2:]))
        require(result.returncode == 0 and 'PASS: Core 668' in result.stdout, 'the Core 668 driver fails on the reverted tree:\n' +
                result.stdout[-3000:])
        report['core668'] = json.loads((work / 'core668.json').read_text())
    print('PASS: Core 906 increments (Metal M1, M2, M3+M4, M5 part 1 with the M3 gaps and the JIT high window, the parity items, then the '
          'retired overrides and the timed Metal report) start from the recorded Core 668 and 901 to 905 files, revert and rebuild the source; presentation unit; renderer host tests; the '
          'Core 668 driver on the reverted tree')
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
