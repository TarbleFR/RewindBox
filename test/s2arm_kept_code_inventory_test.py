#!/usr/bin/env python3
"""The blocking check of the kept-code inventory (build-utils/s2arm/engine/kept_code_inventory.py --check).

    python3 -B test/s2arm_kept_code_inventory_test.py
    S2ARM_INVENTORY_PROOF=<folder with kept-code-inventory.json and S2ArmEngine.map.gz of an engine run> \
        python3 -B test/s2arm_kept_code_inventory_test.py

On small synthetic inventories and link maps: a package with kept code needs a licence entry, a linked archive (or the
obj_app group) needs a rule; both failures are printed and exit 1; packages without kept code are listed and never fail;
every text the tables name is one the collector writes. With S2ARM_INVENTORY_PROOF (the proof of a producer run, never
committed): the check passes on the real data.
"""
from __future__ import annotations

import contextlib
import gzip
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
for part in ('build-utils', 'build-utils/s2arm/engine', 'test'):
    if str(ROOT / part) not in sys.path:
        sys.path.insert(0, str(ROOT / part))

import collect_licenses as collector  # noqa: E402
import kept_code_inventory as inventory  # noqa: E402

SDK = '/Applications/Xcode.app/Contents/Developer/Platforms/iPhoneOS.platform/Developer/SDKs/iPhoneOS.sdk'
NATIVE = '/Users/runner/work/_temp/nuget/microsoft.netcore.app.runtime.nativeaot.ios-arm64/10.0.15/runtimes/ios-arm64/native'
LINKED = (   # the shapes of the groups of the real link (run 43122083170), one of each
    'linker synthesized',
    'build/ios/obj_app/runtime_src_os.c.o', 'build/ios/obj_app/graphics_track_track.c.o',
    'build/gal/ios/libnxgal.a(gal_aa.o)', 'build/nvn/ios/libnvn.a(nvn_tex.c.o)', 'build/nvn/ios/libglx.a(a.o)',
    'build/dsx/ios/libdsx.a(dsx_xc.o)',
    '/Users/runner/work/_temp/s2arm-run/s2arm/cache/nxaot/ios-arm64-3052043189b23ab8/libs2a_cs.a(all.o)',
    f'{NATIVE}/libRuntime.WorkstationGC.a(allocheap.cpp.o)', f'{NATIVE}/libSystem.Native.a(pal_io.c.o)',
    f'{NATIVE}/libbrotlienc.a(encode.c.o)',
    '/x/cache/vpx/ios-arm64-1.17.0-a-b/s2a-1/libs2a_vpx.a(vp9.c.o)', '/x/cache/opus/b/s2a-2/libs2a_opus.a(celt.c.o)',
    '/x/cache/dav1d/c/s2a-3/libs2a_dav1d.a(decode.c.o)',
    '/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/lib/clang/21/lib/darwin/libclang_rt.ios.a(x.o)',
    f'{SDK}/System/Library/Frameworks/Metal.framework/Metal.tbd', f'{SDK}/usr/lib/libz.tbd',
    '/System/Library/PrivateFrameworks/UIKitCore.framework/UIKitCore', '/usr/lib/system/libdyld.dylib',
)


def map_text(groups=LINKED):
    lines = ['# Path: /x/S2ArmEngine', '# Object files:']
    lines += [f'[{index:3}] {path}' for index, path in enumerate(groups)]
    return '\n'.join(lines + ['# Sections:', '# Address\tSize\tSegment\tSection', '# Symbols:']) + '\n'


def report(kept=(), absent=()):
    managed = {name: dict(version='1.0', kept=True, assemblies={name: dict(symbols=3)}) for name in kept}
    managed.update({name: dict(version='1.0', kept=False, assemblies={name: dict(symbols=0)}) for name in absent})
    return dict(managed=managed)


class Check(unittest.TestCase):
    def test_complete_inventory_passes(self):
        failures, lines = inventory.check(report(kept=inventory.PACKAGE_TEXTS, absent=('Humanizer.Core.af', 'System.CodeDom')),
                                          map_text())
        self.assertEqual(failures, [])
        self.assertIn('absent  System.CodeDom 1.0: no kept code', lines)
        self.assertTrue(any('compiler-rt' in line and 'no text' in line for line in lines))

    def test_a_kept_package_without_a_licence_entry_fails(self):
        failures, _ = inventory.check(report(kept=['Gommon', 'Some.New.Package', 'Another.One']), map_text())
        self.assertEqual(len(failures), 2)
        self.assertIn('Some.New.Package', failures[0] + failures[1])
        self.assertIn('Another.One', failures[0] + failures[1])

    def test_an_absent_package_is_never_a_failure(self):
        failures, lines = inventory.check(report(absent=('Some.New.Package',)), map_text())
        self.assertEqual(failures, [])
        self.assertIn('absent  Some.New.Package 1.0: no kept code', lines)

    def test_a_linked_group_without_a_rule_fails(self):
        for group in ('build/ios/libnewthing.a(x.o)', '/opt/third/libother.a(y.o)', 'build/ios/stray.o',
                      f'{NATIVE}/../other/libRuntime.a(z.o)'):
            with self.subTest(group=group):
                failures, _ = inventory.check(report(), map_text(LINKED + (group,)))
                self.assertEqual(len(failures), 1)
                self.assertIn('matches no licence rule', failures[0])
                self.assertIn(group.split('(')[0], failures[0])

    def test_the_groups_are_archives_not_members(self):
        self.assertEqual(inventory.link_groups(map_text(('a/libx.a(1.o)', 'a/libx.a(2.o)', 'b/y.o'))), ['a/libx.a', 'b/y.o'])

    def test_the_texts_the_tables_name_are_texts_the_collector_writes(self):
        sys.modules.pop('s2arm_engine_licenses_test', None)
        import s2arm_engine_licenses_test as fixtures
        with tempfile.TemporaryDirectory() as directory:
            fixture = fixtures.Fixture(directory)
            served = {url: fixtures.pinned_text(path) for _, _, path, url, _, _, _ in collector.PINNED_URLS}
            with mock.patch.object(collector, 'PINNED_URLS', fixtures.fixture_pinned_urls()), \
                    mock.patch.object(collector, 'fetch_url', served.__getitem__):
                manifest = fixture.collect()
        written = {entry['path'] for component in manifest['components'] for entry in component['files']}
        named = {path for texts in inventory.PACKAGE_TEXTS.values() for path in texts}
        named |= {path for _, texts, _ in inventory.NATIVE_RULES for path in texts}
        self.assertEqual(sorted(named - written), [])
        self.assertEqual(len(inventory.PACKAGE_TEXTS), 8)


class CommandLine(unittest.TestCase):
    def run_main(self, kept, groups=LINKED, compress=True):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        folder = Path(directory.name)
        (folder / 'inventory.json').write_text(json.dumps(report(kept=kept, absent=('System.CodeDom',))))
        raw = map_text(groups).encode()
        link_map = folder / ('map.gz' if compress else 'map')
        link_map.write_bytes(gzip.compress(raw) if compress else raw)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = inventory.main(['--check', '--from-json', str(folder / 'inventory.json'), '--link-map', str(link_map)])
        return status, output.getvalue()

    def test_exit_status_and_every_failure_printed(self):
        status, text = self.run_main(list(inventory.PACKAGE_TEXTS))
        self.assertEqual(status, 0)
        self.assertIn('0 failure(s)', text)
        self.assertIn('absent  System.CodeDom', text)
        status, text = self.run_main(list(inventory.PACKAGE_TEXTS) + ['New.Kept'], LINKED + ('a/libnew.a(x.o)',), compress=False)
        self.assertEqual(status, 1)
        self.assertIn('FAIL package New.Kept', text)
        self.assertIn('FAIL linked group a/libnew.a', text)
        self.assertIn('2 failure(s)', text)

    def test_from_json_needs_check(self):
        with self.assertRaises(SystemExit):
            with contextlib.redirect_stderr(io.StringIO()):
                inventory.main(['--from-json', 'x.json', '--link-map', 'x.map'])


@unittest.skipUnless(os.environ.get('S2ARM_INVENTORY_PROOF'), 'S2ARM_INVENTORY_PROOF names no folder')
class RealData(unittest.TestCase):
    def test_the_check_passes_on_the_real_run(self):
        folder = Path(os.environ['S2ARM_INVENTORY_PROOF'])
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = inventory.main(['--check', '--from-json', str(folder / 'kept-code-inventory.json'),
                                     '--link-map', str(folder / 'S2ArmEngine.map.gz')])
        self.assertEqual((status, output.getvalue().count('FAIL ')), (0, 0))
        kept = {name for name, entry in json.loads((folder / 'kept-code-inventory.json').read_text())['managed'].items()
                if entry['kept']}
        self.assertEqual(kept, set(inventory.PACKAGE_TEXTS))


if __name__ == '__main__':
    unittest.main(verbosity=2)
