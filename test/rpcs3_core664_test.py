#!/usr/bin/env python3
"""Host tests of RPCS3 Core 664 = Core 660 + build-utils/rpcs3/core664-from-660.patch.

Core 664 (iOS; IPA 662 logs, Call of Duty: Black Ops II, pids 13140 and 13941; the signature of 624 and 657):
- REWINDBOX_PPU_GRACE_664 (ios/IOSPassiveLockGate.h): when a passive-lock waiter marked starving by the CELL571 gate
  leaves vm::passive_lock, it opens a 100 us window before dropping its mark, and vm::writer_lock keeps deferring while
  that window lasts, within the same 500 us bound per writer lock. The PPU thread then runs before the next heavy PUTLLC
  parks it again. Every writer still takes the full writer lock and parks every PPU thread. Setting
  experimental.ppu_grace (Automatic: every title, with Passive Lock Fairness), boot line "Resolved title policy 664",
  COREPROF PPUGRACE664, CONFIG_LAYERS levers627 digit 17 and its row on the accuracy test page (12 locales).
This driver:
- authenticates the increment against its record, reverts it and requires the reverted files to be the pinned Core 660
  files (the Core 660 record's own SHA-256);
- runs test/rpcs3_ppu_grace664_test.py on the source (wiring checks and the host model built on the source's gate
  header, plain and under ASan and UBSan), then the test page wiring checks;
- runs the Core 660 suite on the reverted tree (which runs the 659, 655, 652, 651, 645, 641, 638, 636, 634, 630 and 627
  suites in turn).
No stall, gameplay, iPhone or FPS claim.
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
DELTA = ROOT / 'build-utils/rpcs3/core664-from-660.patch'
RECORD = ROOT / 'build-utils/rpcs3/core664-delta.json'
RECORD660 = ROOT / 'build-utils/rpcs3/core660-delta.json'
REFERENCE = ROOT / 'docs/evidence/rpcs3-core610-20261101/apple-core/identity.json'
FILES = ('rpcs3/Emu/System.cpp', 'rpcs3/Emu/system_config.h', 'rpcs3/ios/IOSPassiveLockGate.h', 'rpcs3/ios/RPCS3IOSBootDiagnostics.h',
         'rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp', 'rpcs3/ios/RPCS3IOSExperimentalPolicy.h', 'rpcs3/ios/RPCS3IOSPerformance.cpp',
         'rpcs3/ios/RPCS3IOSSettings.cpp')
NEW: tuple = ()
MARKS = ('REWINDBOX_PPU_GRACE_664', 'Core 664: digit 17 of levers627=.')
# The only lines Core 664 removes or rewrites (whitespace-stripped): the mark's release condition, the deferral's
# comment, entry test, loop condition and sleep bound, the wake-up passed on after each sleep (now when the writer
# leaves), and the CONFIG_LAYERS digit count.
REMOVED = {
    'if (m_marked && starving.fetch_sub(1, std::memory_order_seq_cst) == 1 && sleepers.load(std::memory_order_seq_cst))',
    '// Before a writer publishes its lock: wait while a waiter starves, bounded.',
    '// Returns true when it deferred at all.',
    'if (!seen)',
    'for (auto now = start; seen && now < stop; now = std::chrono::steady_clock::now())',
    'sleepers.fetch_add(1, std::memory_order_seq_cst);',
    'sleep_while(starving, seen, stop - now);',
    'sleepers.fetch_sub(1, std::memory_order_seq_cst);',
    '',
    'if (!starving.load(std::memory_order_seq_cst) && sleepers.load(std::memory_order_seq_cst))',
    '// Pass the wake-up on to the next sleeping writer.',
    'wake_one(starving);',
    'append_text(line, "levers627", rsx.levers627, 16);',
}
LOCALES = 12

sys.path.insert(0, str(ROOT / 'test'))
import rpcs3_core636_test as core636  # noqa: E402  (require, lf_sha)

require = core636.require


def patch_files(text: str) -> list:
    return re.findall(r'^diff --git a/(\S+) b/\S+$', text, re.M)


def check_increment(source: Path) -> dict:
    increment = json.loads(RECORD.read_text())['increment_from_core660']
    raw = DELTA.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == increment['patch_sha256'], 'core664-from-660.patch differs from its record')
    text = raw.decode('utf-8', 'surrogateescape').replace('\r\n', '\n')
    files = patch_files(text)
    require(sorted(files) == sorted(FILES) == sorted(increment['files_after_sha256']) == sorted(increment['files_before_sha256']) and
            increment['files'] == len(FILES) and increment['new_files'] == list(NEW) and increment['insertions_only'] is False,
            'core664 files')
    removed = [line[1:].strip() for line in text.splitlines() if line.startswith('-') and not line.startswith('---')]
    added = [line[1:].strip() for line in text.splitlines() if line.startswith('+') and not line.startswith('+++')]
    require(set(removed) <= REMOVED and len(removed) == len(REMOVED) == increment['removed_lines'],
            'Core 664 removes only the listed lines: ' + repr(sorted(set(removed) - REMOVED)[:3]))
    for mark in MARKS:
        require(any(mark in line for line in added), mark + ' is not marked')
    # The increment starts from the pinned Core 660 files: the Core 660 record's own digests, and for a file that record
    # does not carry, the delivered Core 610 reference (the gate's rule: canonical = reference + folded delta).
    after660 = json.loads(RECORD660.read_text())['files_after_sha256']
    reference = json.loads(REFERENCE.read_text())['native_source_sha256']
    for name in files:
        pinned = after660.get(name, reference.get(name))
        require(pinned is not None and increment['files_before_sha256'][name] == pinned,
                name + ': the increment does not start from the pinned Core 660 file')
        require(core636.lf_sha(source / name) == increment['files_after_sha256'][name], name + ' is not the reviewed Core 664 file')
    code = [line for line in added if line and not line.startswith('//')]
    return {'files': len(files), 'patch_sha256': increment['patch_sha256'], 'added_code_lines': len(code), 'removed_lines': len(removed)}


def revert(source: Path, work: Path) -> Path:
    increment = json.loads(RECORD.read_text())['increment_from_core660']
    tree = work / 'core660'
    shutil.copytree(source, tree, ignore=shutil.ignore_patterns('.git'), symlinks=True)
    subprocess.run(['git', 'init', '-q'], cwd=tree, check=True)
    result = subprocess.run(['git', 'apply', '-R', '--whitespace=nowarn', str(DELTA)], cwd=tree, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
    require(result.returncode == 0, 'core664-from-660.patch does not revert: ' + result.stdout[-2000:])
    for name, digest in increment['files_before_sha256'].items():
        require(core636.lf_sha(tree / name) == digest, name + ' reverted does not match its pinned Core 660 SHA-256')
    # Reapplied, the increment rebuilds the source byte for byte.
    again = work / 'core664-again'
    again.mkdir()
    for name in FILES:
        (again / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(tree / name, again / name)
    subprocess.run(['git', 'init', '-q'], cwd=again, check=True)
    result = subprocess.run(['git', 'apply', '--whitespace=nowarn', str(DELTA)], cwd=again, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
    require(result.returncode == 0, 'core664-from-660.patch does not apply to the reverted files: ' + result.stdout[-2000:])
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
    require(read(source / 'rpcs3/ios/RPCS3IOSBootDiagnostics.h').count('append_text(line, "levers627", rsx.levers627, 17);') == 1,
            'every digit of levers627= reaches CONFIG_LAYERS')
    require(re.search(r'ios_add_lever\(ios_levers\.zcull_depth_guard, ios_lever_settings\.zcull_depth_guard\);\n(?:\t+//[^\n]*\n)*'
                      r'\t+ios_add_lever\(ios_levers\.ppu_grace, ios_lever_settings\.ppu_grace\);\n', system), 'digit 17 follows digit 16')
    require('      // Core 664: digit 17 of levers627=.\n'
            '      @{@"key": @"experimental.ppu_grace", @"title": @"testPpuGrace", @"field": @"levers627", @"bit": @16,\n'
            '        @"values": @[@"Enabled", @"Disabled"], @"labels": @[@"enabled", @"disabled"]},\n' in menu, 'test page row')
    require(menu.index('@"key": @"experimental.zcull_depth_guard"') < menu.index('@"key": @"experimental.ppu_grace"'), 'row after digit 16')
    require(plugin.count('@"experimental.ppu_grace": @[@"Enabled", @"Disabled"]') == 1, 'test page whitelist')
    start = l10n.index('NSDictionary<NSString*, NSDictionary<NSString*, NSString*>*>* Build664Translations() {')
    table = l10n[start:l10n.index('  return values;\n}', start)]
    values = re.findall(r'@"testPpuGrace": @"([^"]+)"', table)
    require(len(values) == LOCALES and len(set(values)) == LOCALES and values[0] == 'PPU grace after starvation', 'the row in every locale')
    require(l10n.count('@"testPpuGrace"') == LOCALES, 'the label lives in the 664 table only')
    lookup = l10n[l10n.index('NSString* RPCS3LocalizedString('):]
    require(lookup.index('build664[locale][key]') < lookup.index('build660[locale][key]'), 'the 664 table is read first')
    return {'levers627_digits': 17, 'row': 'ppu_grace', 'bit': 16, 'locales': LOCALES}


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
    with tempfile.TemporaryDirectory(prefix='core664-') as temporary:
        work = Path(temporary)
        print('increment')
        report['increment'] = check_increment(source)
        tree660 = revert(source, work)
        grace = [str(ROOT / 'test/rpcs3_ppu_grace664_test.py'), '--source', str(source), '--cxx', args.cxx]
        report['ppuGrace'] = run('ppu grace after starvation: wiring and host model', grace, work)
        if sanitize:
            report['ppuGraceSanitized'] = run('ppu grace after starvation: host model under ASan and UBSan', grace + ['--sanitize'], work)
        print('test page')
        report['testPage'] = check_test_page(source)
        print('core 660 suite on the reverted tree')
        command = [sys.executable, str(ROOT / 'test/rpcs3_core660_test.py'), '--source', str(tree660), '--cxx', args.cxx,
                   '--report', str(work / 'core660.json')] + (['--no-sanitizers'] if not sanitize else [])
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=10800)
        print('  ' + '\n  '.join(result.stdout.strip().splitlines()[-2:]))
        require(result.returncode == 0 and 'PASS: Core 660' in result.stdout, 'the Core 660 suite fails on the reverted tree:\n' + result.stdout[-3000:])
        report['core660'] = json.loads((work / 'core660.json').read_text())
    print('PASS: Core 664 increment reverts to the pinned Core 660 files and rebuilds the source; PPU grace after starvation '
          '(wiring, host model); test page row; the Core 660 suite on the reverted tree')
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
