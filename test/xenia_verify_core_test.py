#!/usr/bin/env python3
"""The build-path check of build-utils/xenia/verify_core.py (plain python3, standard library only).

    python3 -B test/xenia_verify_core_test.py

Run 43121527685 linked XeniaCore and verify_core.py refused it: an absolute runner path was in the binary, and the
check named only the prefix. It now lists every leaked string with its place (load command, section, or the symbol
string table that holds the N_SO/N_OSO debug map) and still refuses. A synthetic thin arm64 Mach-O carries one path
in an LC_RPATH, one in a __TEXT,__cstring section and one in the string table.
"""
import importlib.util
from pathlib import Path
import struct
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('verify_core', ROOT / 'build-utils/xenia/verify_core.py')
verify_core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify_core)


def synthetic(rpath=b'/Users/runner/work/_temp/msc-ios', cstring=b'/Users/runner/work/RewindBox/a.cc',
              strtab=b'/Users/runner/work/RewindBox/build/x.o'):
    """Header, LC_SEGMENT_64 with one section, LC_RPATH, LC_SYMTAB; then the section and string table bytes."""
    rpath_cmd = struct.pack('<III', 0x8000001C, 0, 12) + rpath + b'\0'
    rpath_cmd += b'\0' * (-len(rpath_cmd) % 8)
    rpath_cmd = rpath_cmd[:4] + struct.pack('<I', len(rpath_cmd)) + rpath_cmd[8:]
    segment_size, symtab_size = 72 + 80, 24
    commands_size = segment_size + len(rpath_cmd) + symtab_size
    section_offset = 32 + commands_size
    section_bytes = b'\0' + cstring + b'\0'
    strtab_offset = section_offset + len(section_bytes)
    strtab_bytes = b'\0' + strtab + b'\0'
    header = struct.pack('<IiiIIIII', 0xFEEDFACF, 0x0100000C, 0, 6, 3, commands_size, 0, 0)
    segment = struct.pack('<II16sQQQQiiII', 0x19, segment_size, b'__TEXT', 0, 0, 0, 0, 5, 5, 1, 0)
    section = struct.pack('<16s16sQQIIIIIIII', b'__cstring', b'__TEXT', 0, len(section_bytes), section_offset,
                          0, 0, 0, 2, 0, 0, 0)
    symtab = struct.pack('<IIIIII', 0x2, symtab_size, 0, 0, strtab_offset, len(strtab_bytes))
    return header + segment + section + rpath_cmd + symtab + section_bytes + strtab_bytes


class BuildPathCheck(unittest.TestCase):
    def test_each_leak_is_listed_with_its_place(self):
        leaks = verify_core.leaked_paths(synthetic())
        self.assertEqual(len(leaks), 3, leaks)
        self.assertTrue(leaks[0].startswith('load command LC_RPATH @0x'), leaks)
        self.assertTrue(leaks[0].endswith(': /Users/runner/work/_temp/msc-ios'), leaks)
        self.assertTrue(any(leak.startswith('section __TEXT,__cstring') and
                            leak.endswith('/Users/runner/work/RewindBox/a.cc') for leak in leaks), leaks)
        self.assertTrue(any(leak.startswith('symbol string table') and leak.endswith('build/x.o') for leak in leaks),
                        leaks)

    def test_a_clean_image_has_no_leak(self):
        clean = synthetic(rpath=b'@loader_path/..', cstring=b'/xenios/src/a.cc', strtab=b'_NeoXenia_GetAPI')
        self.assertEqual(verify_core.leaked_paths(clean), [])

    def test_every_forbidden_prefix_is_found_and_the_list_is_bounded(self):
        for prefix in verify_core.FORBIDDEN_PATHS:
            with self.subTest(prefix=prefix):
                self.assertEqual(len(verify_core.leaked_paths(synthetic(cstring=prefix + b'x'))), 3)
        many = b'\0'.join(b'/home/runner/%d' % index for index in range(60))
        leaks = verify_core.leaked_paths(synthetic(strtab=many), limit=10)
        self.assertEqual(len(leaks), 11)
        self.assertEqual(leaks[-1], '... 52 more')

    def test_a_non_macho_input_is_still_searched(self):
        self.assertEqual(verify_core.leaked_paths(b'xx/Users/runner/y\0'), ['outside any section @0x0: xx/Users/runner/y'])

    def test_the_link_drops_the_build_rpath_and_the_debug_map(self):
        target = (ROOT / 'packages/xenia_internal_bridge/core/target.cmake').read_text()
        self.assertIn('SKIP_BUILD_RPATH TRUE', target)
        self.assertIn('"-Wl,-S"', target)


if __name__ == '__main__':
    unittest.main()
