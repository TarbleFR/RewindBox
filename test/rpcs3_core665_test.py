#!/usr/bin/env python3
"""Host tests of RPCS3 Core 665 = Core 664 + build-utils/rpcs3/core665-from-664.patch.

Core 665 (iOS), the thread orchestrator v1 (REWINDBOX_THREAD_ORCHESTRATOR_665, ios/IOSThreadOrchestrator.h): with the setting
experimental.thread_orchestrator (Automatic: every title), rate-limited self-samples (at most one per millisecond per
thread) of the CPU and QoS class each thread class runs on, the time each vm::writer_lock suspend phase waits and how often
it exceeds 50 us, reported by COREPROF PLACEMENT665; the PPU threads start one relative step above the default
USER_INTERACTIVE priority (below the RSX and audio threads). Boot line "Resolved title policy 665", CONFIG_LAYERS levers627
digit 18 and its row on the accuracy test page (12 locales). Disabled is Core 664. Scheduling and measurement only.
This driver:
- authenticates the increment against its record, reverts it and requires the reverted files to be the pinned Core 664
  files (the Core 664 record, then the delivered Core 610 reference) and the new header gone, then applies it again;
- runs test/rpcs3_thread_orchestrator665_test.py on the source (wiring and the host unit, plain and under ASan and UBSan),
  then the test page wiring checks;
- runs the Core 664 suite on the reverted tree (which runs the 660 to 627 suites in turn).
No placement, gameplay, iPhone or FPS claim.
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
DELTA = ROOT / 'build-utils/rpcs3/core665-from-664.patch'
RECORD = ROOT / 'build-utils/rpcs3/core665-delta.json'
RECORD664 = ROOT / 'build-utils/rpcs3/core664-delta.json'
REFERENCE = ROOT / 'docs/evidence/rpcs3-core610-20261101/apple-core/identity.json'
FILES = ('rpcs3/Emu/CPU/CPUThread.cpp', 'rpcs3/Emu/Memory/vm.cpp', 'rpcs3/Emu/RSX/RSXThread.cpp', 'rpcs3/Emu/System.cpp',
         'rpcs3/Emu/system_config.h', 'rpcs3/ios/IOSThreadOrchestrator.h', 'rpcs3/ios/RPCS3IOSBootDiagnostics.h',
         'rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp', 'rpcs3/ios/RPCS3IOSExperimentalPolicy.h', 'rpcs3/ios/RPCS3IOSPerformance.cpp',
         'rpcs3/ios/RPCS3IOSSettings.cpp')
NEW = ('rpcs3/ios/IOSThreadOrchestrator.h',)
MARKS = ('REWINDBOX_THREAD_ORCHESTRATOR_665', 'Core 665: digit 18 of levers627=.')
# The only line Core 665 removes: the CONFIG_LAYERS digit count (17 -> 18).
REMOVED = {
    'append_text(line, "levers627", rsx.levers627, 17);',
}
LOCALES = 12

sys.path.insert(0, str(ROOT / 'test'))
import rpcs3_core636_test as core636  # noqa: E402  (require, lf_sha)

require = core636.require


def patch_files(text: str) -> list:
    return re.findall(r'^diff --git a/(\S+) b/\S+$', text, re.M)


def check_increment(source: Path) -> dict:
    increment = json.loads(RECORD.read_text())['increment_from_core664']
    raw = DELTA.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == increment['patch_sha256'], 'core665-from-664.patch differs from its record')
    text = raw.decode('utf-8', 'surrogateescape').replace('\r\n', '\n')
    files = patch_files(text)
    require(sorted(files) == sorted(FILES) == sorted(increment['files_after_sha256']) and
            sorted(increment['files_before_sha256']) == sorted(set(FILES) - set(NEW)) and
            increment['files'] == len(FILES) and increment['new_files'] == list(NEW) and increment['insertions_only'] is False,
            'core665 files')
    removed = [line[1:].strip() for line in text.splitlines() if line.startswith('-') and not line.startswith('---')]
    added = [line[1:].strip() for line in text.splitlines() if line.startswith('+') and not line.startswith('+++')]
    require(set(removed) <= REMOVED and len(removed) == len(REMOVED) == increment['removed_lines'],
            'Core 665 removes only the listed line: ' + repr(sorted(set(removed) - REMOVED)[:3]))
    for mark in MARKS:
        require(any(mark in line for line in added), mark + ' is not marked')
    # The increment starts from the pinned Core 664 files: the Core 664 record's own digests, and for a file that record
    # does not carry, the delivered Core 610 reference (the gate's rule: canonical = reference + folded delta).
    after664 = json.loads(RECORD664.read_text())['files_after_sha256']
    reference = json.loads(REFERENCE.read_text())['native_source_sha256']
    for name in files:
        if name not in NEW:
            pinned = after664.get(name, reference.get(name))
            require(pinned is not None and increment['files_before_sha256'][name] == pinned,
                    name + ': the increment does not start from the pinned Core 664 file')
        else:
            require(name not in after664 and name not in reference, name + ' is new in Core 665')
        require(core636.lf_sha(source / name) == increment['files_after_sha256'][name], name + ' is not the reviewed Core 665 file')
    code = [line for line in added if line and not line.startswith('//')]
    return {'files': len(files), 'patch_sha256': increment['patch_sha256'], 'added_code_lines': len(code), 'removed_lines': len(removed)}


def revert(source: Path, work: Path) -> Path:
    increment = json.loads(RECORD.read_text())['increment_from_core664']
    tree = work / 'core664'
    shutil.copytree(source, tree, ignore=shutil.ignore_patterns('.git'), symlinks=True)
    subprocess.run(['git', 'init', '-q'], cwd=tree, check=True)
    result = subprocess.run(['git', 'apply', '-R', '--whitespace=nowarn', str(DELTA)], cwd=tree, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
    require(result.returncode == 0, 'core665-from-664.patch does not revert: ' + result.stdout[-2000:])
    for name, digest in increment['files_before_sha256'].items():
        require(core636.lf_sha(tree / name) == digest, name + ' reverted does not match its pinned Core 664 SHA-256')
    for name in NEW:
        require(not (tree / name).exists(), name + ' survives the reversal')
    # Reapplied, the increment rebuilds the source byte for byte.
    again = work / 'core664-again'
    again.mkdir()
    for name in FILES:
        if name not in NEW:
            (again / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(tree / name, again / name)
    subprocess.run(['git', 'init', '-q'], cwd=again, check=True)
    result = subprocess.run(['git', 'apply', '--whitespace=nowarn', str(DELTA)], cwd=again, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
    require(result.returncode == 0, 'core665-from-664.patch does not apply to the reverted files: ' + result.stdout[-2000:])
    for name in FILES:
        require((again / name).read_bytes() == (source / name).read_bytes(), name + ': the increment does not rebuild the source')
    return tree


def run(name: str, command: list, work: Path, timeout: int = 3600) -> dict:
    print(name)
    report = work / (re.sub(r'\W+', '-', name) + '.json')
    result = subprocess.run([sys.executable, '-B', *command, '--report', str(report)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, timeout=timeout)
    print('  ' + '\n  '.join(result.stdout.strip().splitlines()[-1:]))
    require(result.returncode == 0, f'{name} fails:\n' + result.stdout[-3000:])
    return json.loads(report.read_text())


def check_test_page(source: Path) -> dict:
    read = lambda path: path.read_text('utf-8', 'surrogateescape').replace('\r\n', '\n')
    system = read(source / 'rpcs3/Emu/System.cpp')
    classes = ROOT / 'packages/rpcs3_internal_bridge/ios/Classes'
    menu, plugin, l10n = read(classes / 'Rpcs3SessionMenu.mm'), read(classes / 'Rpcs3InternalBridgePlugin.mm'), read(classes / 'RPCS3InGameLocalization.mm')
    require(read(source / 'rpcs3/ios/RPCS3IOSBootDiagnostics.h').count('append_text(line, "levers627", rsx.levers627, 18);') == 1,
            'every digit of levers627= reaches CONFIG_LAYERS')
    require(re.search(r'ios_add_lever\(ios_levers\.ppu_grace, ios_lever_settings\.ppu_grace\);\n(?:\t+//[^\n]*\n)*'
                      r'\t+ios_add_lever\(ios_levers\.thread_orchestrator, ios_lever_settings\.thread_orchestrator\);\n', system), 'digit 18 follows digit 17')
    require('      // Core 665: digit 18 of levers627=.\n'
            '      @{@"key": @"experimental.thread_orchestrator", @"title": @"testThreadOrchestrator", @"field": @"levers627", @"bit": @17,\n'
            '        @"values": @[@"Enabled", @"Disabled"], @"labels": @[@"enabled", @"disabled"]},\n' in menu, 'test page row')
    require(menu.index('@"key": @"experimental.ppu_grace"') < menu.index('@"key": @"experimental.thread_orchestrator"'), 'row after digit 17')
    require(plugin.count('@"experimental.thread_orchestrator": @[@"Enabled", @"Disabled"]') == 1, 'test page whitelist')
    start = l10n.index('NSDictionary<NSString*, NSDictionary<NSString*, NSString*>*>* Build665Translations() {')
    table = l10n[start:l10n.index('  return values;\n}', start)]
    values = re.findall(r'@"testThreadOrchestrator": @"([^"]+)"', table)
    require(len(values) == LOCALES and len(set(values)) == LOCALES and values[0] == 'Thread orchestrator', 'the row in every locale')
    require(l10n.count('@"testThreadOrchestrator"') == LOCALES, 'the label lives in the 665 table only')
    lookup = l10n[l10n.index('NSString* RPCS3LocalizedString('):]
    require(lookup.index('build665[locale][key]') < lookup.index('build664[locale][key]'), 'the 665 table is read first')
    return {'levers627_digits': 18, 'row': 'thread_orchestrator', 'bit': 17, 'locales': LOCALES}


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
    with tempfile.TemporaryDirectory(prefix='core665-') as temporary:
        work = Path(temporary)
        print('increment')
        report['increment'] = check_increment(source)
        tree664 = revert(source, work)
        orchestrator = [str(ROOT / 'test/rpcs3_thread_orchestrator665_test.py'), '--source', str(source), '--cxx', args.cxx]
        report['orchestrator'] = run('thread orchestrator: wiring and host unit', orchestrator, work)
        if sanitize:
            report['orchestratorSanitized'] = run('thread orchestrator: host unit under ASan and UBSan', orchestrator + ['--sanitize'], work)
        print('test page')
        report['testPage'] = check_test_page(source)
        print('core 664 suite on the reverted tree')
        command = [sys.executable, str(ROOT / 'test/rpcs3_core664_test.py'), '--source', str(tree664), '--cxx', args.cxx,
                   '--report', str(work / 'core664.json')] + (['--no-sanitizers'] if not sanitize else [])
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=10800)
        print('  ' + '\n  '.join(result.stdout.strip().splitlines()[-2:]))
        require(result.returncode == 0 and 'PASS: Core 664' in result.stdout, 'the Core 664 suite fails on the reverted tree:\n' + result.stdout[-3000:])
        report['core664'] = json.loads((work / 'core664.json').read_text())
    print('PASS: Core 665 increment reverts to the pinned Core 664 files and rebuilds the source; thread orchestrator '
          '(wiring, host unit); test page row; the Core 664 suite on the reverted tree')
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
