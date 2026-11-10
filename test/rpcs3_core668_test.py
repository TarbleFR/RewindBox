#!/usr/bin/env python3
"""Host tests of RPCS3 Core 668 = Core 665 + build-utils/rpcs3/core668-from-665.patch.

Core 668 (iOS): the maintainer abandoned the thread orchestrator v1 on 5 November 2026 (complexity, no gain measured on
iPhone). The increment is the reverse of core665-from-664.patch on every file but ios/IOSThreadOrchestrator.h, which stays
as a comment that no source includes (the canonical delta never drops a file). Every other file is the pinned Core 664 file.
This driver:
- authenticates the increment against its record, requires it to start from the pinned Core 665 files and to end on the
  pinned Core 664 files (the Core 664 record, then the delivered Core 610 reference), reverts it, requires the reverted files
  to be the Core 665 files, then applies it again byte for byte;
- requires the orchestrator gone: the header holds no code, no Core source names it, levers627= has 17 digits again, and the
  host test page has no row, value list or translation for it;
- absence control: test/rpcs3_thread_orchestrator665_test.py passes on the reverted Core 665 tree and fails on the source;
- runs the Core 664 suite on the source itself (Core 668 is Core 664), which runs the 660 to 627 suites in turn.
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
DELTA = ROOT / 'build-utils/rpcs3/core668-from-665.patch'
FORWARD = 'build-utils/rpcs3/core665-from-664.patch'
RECORD = ROOT / 'build-utils/rpcs3/core668-delta.json'
RECORD665 = ROOT / 'build-utils/rpcs3/core665-delta.json'
RECORD664 = ROOT / 'build-utils/rpcs3/core664-delta.json'
REFERENCE = ROOT / 'docs/evidence/rpcs3-core610-20261101/apple-core/identity.json'
FILES = ('rpcs3/Emu/CPU/CPUThread.cpp', 'rpcs3/Emu/Memory/vm.cpp', 'rpcs3/Emu/RSX/RSXThread.cpp', 'rpcs3/Emu/System.cpp',
         'rpcs3/Emu/system_config.h', 'rpcs3/ios/IOSThreadOrchestrator.h', 'rpcs3/ios/RPCS3IOSBootDiagnostics.h',
         'rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp', 'rpcs3/ios/RPCS3IOSExperimentalPolicy.h', 'rpcs3/ios/RPCS3IOSPerformance.cpp',
         'rpcs3/ios/RPCS3IOSSettings.cpp')
TOMB = 'rpcs3/ios/IOSThreadOrchestrator.h'
NAMES = ('IOSThreadOrchestrator', 'thread_orchestrator', 'orchestrator::', 'ORCH665', 'PLACEMENT665', 'Resolved title policy 665')
SUFFIXES = {'.cpp', '.h', '.hpp', '.mm', '.inl', '.txt', '.cmake'}

sys.path.insert(0, str(ROOT / 'test'))
import rpcs3_core636_test as core636  # noqa: E402  (require, lf_sha)

require = core636.require


def patch_files(text: str) -> list:
    return re.findall(r'^diff --git a/(\S+) b/\S+$', text, re.M)


def code_lines(text: str) -> list:
    return [line for line in text.replace('\r\n', '\n').splitlines()
            if line.strip() and not line.strip().startswith('//') and line.strip() != '#pragma once']


def check_increment(source: Path) -> dict:
    increment = json.loads(RECORD.read_text())['increment_from_core665']
    raw = DELTA.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == increment['patch_sha256'], 'core668-from-665.patch differs from its record')
    text = raw.decode('utf-8', 'surrogateescape').replace('\r\n', '\n')
    files = patch_files(text)
    require(sorted(files) == sorted(FILES) == sorted(increment['files_before_sha256']) == sorted(increment['files_after_sha256']) and
            increment['files'] == len(FILES) and increment['removed_files'] == [] and increment['reverse_of'] == FORWARD and
            increment['insertions_only'] is False, 'core668 files')
    # It starts from the pinned Core 665 files.
    after665 = json.loads(RECORD665.read_text())['increment_from_core664']['files_after_sha256']
    for name in FILES:
        require(increment['files_before_sha256'][name] == after665[name], name + ': the increment does not start from the pinned Core 665 file')
    # It ends on the pinned Core 664 files; the header is a comment.
    after664 = json.loads(RECORD664.read_text())['files_after_sha256']
    reference = json.loads(REFERENCE.read_text())['native_source_sha256']
    for name in FILES:
        require(core636.lf_sha(source / name) == increment['files_after_sha256'][name], name + ' is not the reviewed Core 668 file')
        if name == TOMB:
            require(name not in after664 and name not in reference, name + ' is not a Core 664 file')
            require(not code_lines((source / name).read_text('utf-8')), name + ' still holds code')
        else:
            pinned = after664.get(name, reference.get(name))
            require(pinned is not None and increment['files_after_sha256'][name] == pinned, name + ' is not the pinned Core 664 file')
    removed = [line for line in text.splitlines() if line.startswith('-') and not line.startswith('---')]
    require(len(removed) == increment['removed_lines'], 'removed line count')
    return {'files': len(files), 'patch_sha256': increment['patch_sha256'], 'removed_lines': len(removed), 'equals_core664_except': TOMB}


def check_absent(source: Path) -> dict:
    scanned = 0
    for root in ('rpcs3', 'Utilities'):
        for path in sorted((source / root).rglob('*')):
            if not path.is_file() or path.suffix not in SUFFIXES or path.relative_to(source).as_posix() == TOMB:
                continue
            text = path.read_text('utf-8', 'surrogateescape')
            scanned += 1
            for name in NAMES:
                require(name not in text, f'{path.relative_to(source)} still names {name}')
    diagnostics = (source / 'rpcs3/ios/RPCS3IOSBootDiagnostics.h').read_text('utf-8')
    require(diagnostics.count('append_text(line, "levers627", rsx.levers627, 17);') == 1 and
            'rsx.levers627, 18);' not in diagnostics, 'levers627= has 17 digits')
    classes = ROOT / 'packages/rpcs3_internal_bridge/ios/Classes'
    for name in ('Rpcs3SessionMenu.mm', 'Rpcs3InternalBridgePlugin.mm', 'RPCS3InGameLocalization.mm'):
        text = (classes / name).read_text('utf-8', 'surrogateescape')
        for token in ('thread_orchestrator', 'testThreadOrchestrator', 'Build665Translations'):
            require(token not in text, f'{name} still carries {token}')
    require('thread_orchestrator' not in (ROOT / 'test/rpcs3_graphics_tests612_test.py').read_text('utf-8'),
            'the test page contract still lists the orchestrator')
    return {'core_files_scanned': scanned, 'levers627_digits': 17, 'host_files': 3}


def revert(source: Path, work: Path) -> Path:
    increment = json.loads(RECORD.read_text())['increment_from_core665']
    tree = work / 'core665'
    shutil.copytree(source, tree, ignore=shutil.ignore_patterns('.git'), symlinks=True)
    subprocess.run(['git', 'init', '-q'], cwd=tree, check=True)
    result = subprocess.run(['git', 'apply', '-R', '--whitespace=nowarn', str(DELTA)], cwd=tree, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
    require(result.returncode == 0, 'core668-from-665.patch does not revert: ' + result.stdout[-2000:])
    for name, digest in increment['files_before_sha256'].items():
        require(core636.lf_sha(tree / name) == digest, name + ' reverted does not match its pinned Core 665 SHA-256')
    again = work / 'core665-again'
    again.mkdir()
    for name in FILES:
        (again / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(tree / name, again / name)
    subprocess.run(['git', 'init', '-q'], cwd=again, check=True)
    result = subprocess.run(['git', 'apply', '--whitespace=nowarn', str(DELTA)], cwd=again, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
    require(result.returncode == 0, 'core668-from-665.patch does not apply to the reverted files: ' + result.stdout[-2000:])
    for name in FILES:
        require((again / name).read_bytes() == (source / name).read_bytes(), name + ': the increment does not rebuild the source')
    return tree


def run(name: str, command: list, work: Path, expect_pass: bool = True, timeout: int = 3600) -> dict:
    print(name)
    report = work / (re.sub(r'\W+', '-', name) + '.json')
    result = subprocess.run([sys.executable, '-B', *command, '--report', str(report)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, timeout=timeout)
    print('  ' + '\n  '.join(result.stdout.strip().splitlines()[-1:]))
    if expect_pass:
        require(result.returncode == 0, f'{name} fails:\n' + result.stdout[-3000:])
        return json.loads(report.read_text())
    require(result.returncode != 0, f'{name} passes on a source without the orchestrator')
    return {'failed_as_required': True, 'last_line': result.stdout.strip().splitlines()[-1:]}


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
    with tempfile.TemporaryDirectory(prefix='core668-') as temporary:
        work = Path(temporary)
        print('increment')
        report['increment'] = check_increment(source)
        print('orchestrator absent')
        report['absence'] = check_absent(source)
        tree665 = revert(source, work)
        test = str(ROOT / 'test/rpcs3_thread_orchestrator665_test.py')
        report['controlCore665'] = run('absence control: the orchestrator test on the reverted Core 665 tree',
                                       [test, '--source', str(tree665), '--cxx', args.cxx], work)
        report['controlCore668'] = run('absence control: the orchestrator test on the Core 668 source',
                                       [test, '--source', str(source), '--cxx', args.cxx], work, expect_pass=False)
        print('core 664 suite on the source')
        command = [sys.executable, str(ROOT / 'test/rpcs3_core664_test.py'), '--source', str(source), '--cxx', args.cxx,
                   '--report', str(work / 'core664.json')] + (['--no-sanitizers'] if not sanitize else [])
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=10800)
        print('  ' + '\n  '.join(result.stdout.strip().splitlines()[-2:]))
        require(result.returncode == 0 and 'PASS: Core 664' in result.stdout, 'the Core 664 suite fails on the source:\n' + result.stdout[-3000:])
        report['core664'] = json.loads((work / 'core664.json').read_text())
    print('PASS: Core 668 increment starts from the pinned Core 665 files, ends on the pinned Core 664 files and rebuilds the source; '
          'orchestrator absent (Core and host), absence control; the Core 664 suite on the source')
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
