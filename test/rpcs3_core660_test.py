#!/usr/bin/env python3
"""Host tests of RPCS3 Core 660 = Core 659 + build-utils/rpcs3/core660-from-659.patch.

Core 660 (iOS; IPA 657 logs, Core 655, PID 10471, and the Core 659 analysis) folds five reviewed steps, each kept as its
own patch under build-utils/rpcs3/core660-lots/ and applied in this order:
0. REWINDBOX_SPU_TIMEBASE_MAPPING_660: SPU blocks that read the decrementer link spu_timebase_offs to g_timebase_offs
   again (compile() clears every mapping before each module, so since Build 481 the name resolved to a null-function
   stub and the JIT decrementer carried a per-boot constant bias against the C++ read).
1. REWINDBOX_SPU_DIRECT_OBJECT_HIT_660: an SPU object-cache hit whose undefined symbols are all known SPU helpers or
   patchpoints of its own module is linked without building its LLVM IR again; any other object takes the IR path.
2. REWINDBOX_TEXTURE_LOOKUP_MEMO_660: a sampler slot reuses the result of an identical texture lookup while nothing in
   the texture cache changed (exact invalidation by generations), with a sampled self-verification that turns the memo
   off for the boot at the first difference; Assassin's Creed served, Black Ops II verified at every reuse.
3. REWINDBOX_ZCULL_WATCHED_FLUSH_660 and REWINDBOX_ZCULL_DEPTH_GUARD_660: a report into a ZCULL slot the game waited for
   arms the 659 boundary submission of its command buffer; at the queue-depth limit the open command buffer is submitted
   only while it holds the oldest pending query (upstream behaviour from 8,192 pending reports).
4. The accuracy test page gains the three new settings (CONFIG_LAYERS levers627 digits 14 to 16).
This driver:
- authenticates the folded increment and the five steps against the record, rebuilds every intermediate tree from the
  reverted Core 659 tree, and requires the last one to be the source byte for byte;
- runs each step's own test on its pair of trees (timebase: Core 660 against Core 659; the others: the tree after the
  step against the tree before it), then the test page wiring checks;
- runs the Core 659 suite on the reverted tree (which runs the 655, 652, 651, 645, 641, 638, 636, 634, 630 and 627
  suites in turn).
No rendering, gameplay, iPhone or FPS claim.
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
DELTA = ROOT / 'build-utils/rpcs3/core660-from-659.patch'
RECORD = ROOT / 'build-utils/rpcs3/core660-delta.json'
LOTS = (('timebase', 'build-utils/rpcs3/core660-lots/0-timebase.patch', ('REWINDBOX_SPU_TIMEBASE_MAPPING_660',)),
        ('spu-direct', 'build-utils/rpcs3/core660-lots/1-spu-direct.patch', ('REWINDBOX_SPU_DIRECT_OBJECT_HIT_660',)),
        ('texture-memo', 'build-utils/rpcs3/core660-lots/2-texture-memo.patch', ('REWINDBOX_TEXTURE_LOOKUP_MEMO_660',)),
        ('zcull', 'build-utils/rpcs3/core660-lots/3-zcull.patch', ('REWINDBOX_ZCULL_WATCHED_FLUSH_660', 'REWINDBOX_ZCULL_DEPTH_GUARD_660')),
        ('test-page', 'build-utils/rpcs3/core660-lots/4-test-page.patch', ('Core 660: digits 14 to 16 of levers627=',)))
NEW = ('rpcs3/ios/IOSSpuObjectBindings.h', 'rpcs3/ios/IOSTextureLookupMemo.h', 'rpcs3/ios/IOSZcullWatched.h')
CODEGEN_CHANGED = ('Utilities/JITLLVM.cpp', 'rpcs3/Emu/Cell/SPULLVMRecompiler.cpp')
# The three settings of the test page (levers627 digits 14 to 16), in the order of their rows.
TEST_PAGE = (('spu_direct_object_hits', 'SPU Direct Object Hits', 'testSpuDirectObjectHits', 13),
             ('texture_lookup_memo', 'Texture Lookup Memo', 'testTextureLookupMemo', 14),
             ('zcull_depth_guard', 'ZCULL Queue-Depth Guard', 'testZcullDepthGuard', 15))
LOCALES = 12

sys.path.insert(0, str(ROOT / 'test'))
import rpcs3_core636_test as core636  # noqa: E402  (require, lf_sha)

require = core636.require


def patch_files(raw: bytes) -> list:
    return re.findall(r'^diff --git a/(\S+) b/\S+$', raw.decode('utf-8', 'surrogateescape'), re.M)


def apply(tree: Path, patch: Path, reverse: bool = False) -> None:
    result = subprocess.run(['git', 'apply', *(['-R'] if reverse else []), '--whitespace=nowarn', str(patch)], cwd=tree,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    require(result.returncode == 0, f'{patch.name} does not apply{" in reverse" if reverse else ""}: ' + result.stdout[-2000:])


def check_increment(source: Path) -> dict:
    increment = json.loads(RECORD.read_text())['increment_from_core659']
    raw = DELTA.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == increment['patch_sha256'], 'core660-from-659.patch differs from its record')
    files = patch_files(raw)
    require(sorted(files) == sorted(increment['files_after_sha256']) and increment['files'] == len(files) and
            sorted(increment['new_files']) == sorted(NEW) and increment['insertions_only'] is False, 'core660 files')
    require(set(NEW) <= set(files) and not set(NEW) & set(increment['files_before_sha256']), 'the three new headers')
    text = raw.decode('utf-8', 'surrogateescape').replace('\r\n', '\n')
    removed = [line for line in text.splitlines() if line.startswith('-') and not line.startswith('---')]
    require(len(removed) == increment['removed_lines'], 'removed line count')
    for name in files:
        require(core636.lf_sha(source / name) == increment['files_after_sha256'][name], name + ' is not the reviewed Core 660 file')
    lots = increment['lots']
    require([lot['name'] for lot in lots] == [name for name, _, _ in LOTS], 'the five steps, in order')
    for (name, path, marks), lot in zip(LOTS, lots):
        lot_raw = (ROOT / path).read_bytes()
        require(lot['patch'] == path and hashlib.sha256(lot_raw).hexdigest() == lot['patch_sha256'], path + ' differs from its record')
        added = [line[1:] for line in lot_raw.decode('utf-8', 'surrogateescape').splitlines()
                 if line.startswith('+') and not line.startswith('+++')]
        for mark in marks:
            require(any(mark in line for line in added), f'{name}: {mark} is not marked')
        require(sorted(patch_files(lot_raw)) == sorted(lot['files']) and set(lot['files']) <= set(files), name + ' files')
    return {'files': len(files), 'patch_sha256': increment['patch_sha256'], 'removed_lines': len(removed),
            'steps': {lot['name']: len(lot['files']) for lot in lots}}


def copy(tree: Path, target: Path) -> Path:
    shutil.copytree(tree, target, ignore=shutil.ignore_patterns('.git', '3rdparty'), symlinks=True)
    subprocess.run(['git', 'init', '-q'], cwd=target, check=True)
    return target


def chain(source: Path, work: Path) -> list:
    """Core 659 (the folded patch reversed), then the tree after each step; the last is the source."""
    increment = json.loads(RECORD.read_text())['increment_from_core659']
    tree659 = copy(source, work / 'core659')
    apply(tree659, DELTA, reverse=True)
    for name, digest in increment['files_before_sha256'].items():
        require(core636.lf_sha(tree659 / name) == digest, name + ' reverted does not match its pinned Core 659 SHA-256')
    for name in NEW:
        require(not (tree659 / name).exists(), name + ' survives the reversal')
    trees = [tree659]
    for index, (name, path, _) in enumerate(LOTS):
        tree = copy(trees[-1], work / f'step{index}-{name}')
        apply(tree, ROOT / path)
        trees.append(tree)
    for name in increment['files_after_sha256']:
        require((trees[-1] / name).read_bytes() == (source / name).read_bytes(), name + ': the five steps do not rebuild the source')
    return trees


def run(name: str, command: list, work: Path, timeout: int = 3600) -> dict:
    print(name)
    report = work / (name + '.json')
    result = subprocess.run([sys.executable, '-B', *command, '--report', str(report)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, timeout=timeout)
    print('  ' + '\n  '.join(result.stdout.strip().splitlines()[-2:]))
    require(result.returncode == 0, f'{name} fails:\n' + result.stdout[-3000:])
    return json.loads(report.read_text())


def check_test_page(source: Path) -> dict:
    read = lambda path: path.read_text('utf-8', 'surrogateescape').replace('\r\n', '\n')
    system = read(source / 'rpcs3/Emu/System.cpp')
    digits = read(source / 'rpcs3/ios/RPCS3IOSBootDiagnostics.h')
    config = read(source / 'rpcs3/Emu/system_config.h')
    settings = read(source / 'rpcs3/ios/RPCS3IOSSettings.cpp')
    policy_h = read(source / 'rpcs3/ios/RPCS3IOSExperimentalPolicy.h')
    classes = ROOT / 'packages/rpcs3_internal_bridge/ios/Classes'
    menu, plugin, l10n = read(classes / 'Rpcs3SessionMenu.mm'), read(classes / 'Rpcs3InternalBridgePlugin.mm'), read(classes / 'RPCS3InGameLocalization.mm')
    require(digits.count('append_text(line, "levers627", rsx.levers627, 16);') == 1, 'every digit of levers627= reaches CONFIG_LAYERS')
    previous = 'spu_object_prefetch'
    start = l10n.index('NSDictionary<NSString*, NSDictionary<NSString*, NSString*>*>* Build660Translations() {')
    table = l10n[start:l10n.index('  return values;\n}', start)]
    for setting, name, label, bit in TEST_PAGE:
        require(f'cfg::_enum<ios_experimental_mode> {setting}{{ this, "{name}", ios_experimental_mode::automatic }};' in config, 'setting ' + setting)
        require(settings.count(f'GAME_SETTING("experimental.{setting}", "Experimental"') == 1 and
                f'kind::RPCS3_IOS_SETTING_CHOICE, g_cfg.ios_experimental.{setting}, 0, 0, 0)' in settings, 'catalogue ' + setting)
        require(f'bool {setting} = false;' in policy_h, 'policy field ' + setting)
        require(re.search(rf'ios_add_lever\(ios_levers\.{previous}, ios_lever_settings\.{previous}\);\n(?:\t+//[^\n]*\n)*'
                          rf'\t+ios_add_lever\(ios_levers\.{setting}, ios_lever_settings\.{setting}\);\n', system), 'digit of the state field: ' + setting)
        previous = setting
        require(f'@{{@"key": @"experimental.{setting}", @"title": @"{label}", @"field": @"levers627", @"bit": @{bit},\n' in menu, 'test page row ' + setting)
        require(f'@"experimental.{setting}": @[@"Enabled", @"Disabled"]' in plugin, 'test page whitelist ' + setting)
        values = re.findall(rf'@"{label}": @"([^"]+)"', table)
        require(len(values) == LOCALES and len(set(values[1:]) & {values[0]}) == 0, 'test page row in every locale: ' + setting)
    lookup = l10n[l10n.index('NSString* RPCS3LocalizedString('):]
    require(lookup.index('build660[locale][key]') < lookup.index('build634[locale][key]'), 'the 660 table is read first')
    return {'levers627_digits': 16, 'rows': [setting for setting, *_ in TEST_PAGE], 'locales': LOCALES}


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
    with tempfile.TemporaryDirectory(prefix='core660-') as temporary:
        work = Path(temporary)
        print('increment')
        report['increment'] = check_increment(source)
        trees = chain(source, work)
        tree659, tb, spu, memo, zcull, _ = trees
        report['timebase'] = run('spu timebase mapping: Core 660 against Core 659',
                                 [str(ROOT / 'test/rpcs3_spu_timebase_mapping660_test.py'), '--candidate', str(source), '--control', str(tree659)], work)
        report['spuDirect'] = run('spu direct object hits: step 1 against step 0',
                                  [str(ROOT / 'test/rpcs3_spu_direct_hit660_test.py'), '--candidate', str(spu), '--control', str(tb), '--cxx', args.cxx], work)
        report['textureMemo'] = run('texture lookup memo: step 2 against step 1',
                                    [str(ROOT / 'test/rpcs3_texture_lookup_memo660_test.py'), '--candidate', str(memo), '--control', str(spu), '--cxx', args.cxx], work)
        report['zcull'] = run('zcull watched flush and depth guard: step 3 against step 2',
                              [str(ROOT / 'test/rpcs3_zcull_levers660_test.py'), '--candidate', str(zcull), '--control', str(memo), '--cxx', args.cxx]
                              + ([] if sanitize else ['--no-sanitizers']), work)
        print('test page')
        report['testPage'] = check_test_page(source)
        print('core 659 suite on the reverted tree')
        command = [sys.executable, str(ROOT / 'test/rpcs3_core659_test.py'), '--source', str(tree659), '--cxx', args.cxx,
                   '--report', str(work / 'core659.json')] + (['--no-sanitizers'] if not sanitize else [])
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=7200)
        print('  ' + '\n  '.join(result.stdout.strip().splitlines()[-3:]))
        require(result.returncode == 0 and 'PASS: Core 659' in result.stdout, 'the Core 659 suite fails on the reverted tree:\n' + result.stdout[-3000:])
        report['core659'] = json.loads((work / 'core659.json').read_text())
    print('PASS: Core 660 increment and its five steps rebuild the source from Core 659; SPU timebase mapping, SPU direct object '
          'hits, texture lookup memo, ZCULL watched flush and depth guard on their own trees; test page rows; the Core 659 suite on that tree')
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
