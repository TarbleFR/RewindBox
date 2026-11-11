#!/usr/bin/env python3
"""The exported symbol list of S2ArmEngine.framework (build-utils/s2arm/engine/export_list.py), on synthetic inputs.

    python3 -B test/s2arm_engine_exports_test.py
"""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('export_list', ROOT / 'build-utils/s2arm/engine/export_list.py')
tool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tool)

ENTRY = [f'0000000000001000 T _{name}' for name in tool.GUEST_ENTRY_POINTS]


def nm(*names):
    return '\n'.join(ENTRY + [f'00000000000020{i:02x} T {name}' for i, name in enumerate(names)]) + '\n'


def utf16(text):
    # A NativeAOT frozen string literal: length, then UTF-16LE characters, then a NUL character.
    return len(text).to_bytes(4, 'little') + text.encode('utf-16-le') + b'\0\0'


class ExportList(unittest.TestCase):
    def test_kept_are_entry_points_and_names_looked_up_by_string(self):
        data = (b'\x8b\x00S2A_InitSession\x00nxgal_out_size\x00log: s2a_hidden_fn failed\x00' +
                utf16('s2a_pad_rumble_session') + b'\xff\xfe')
        result = tool.compute(data, nm('_S2A_InitSession', '_nxgal_out_size', '_s2a_pad_rumble_session',
                                       '_s2a_hidden_fn', '__ZN7glslang8TProgramD1Ev', '_vpx_codec_decode',
                                       '_OBJC_CLASS_$_S2AViewController'))
        self.assertEqual(result['keep'], sorted(['_S2A_InitSession', '_nxgal_out_size', '_s2a_pad_rumble_session'] +
                                                ['_' + name for name in tool.GUEST_ENTRY_POINTS]))
        # Only exact strings count: a name inside a log message is not a lookup.
        self.assertNotIn('_s2a_hidden_fn', result['keep'])
        self.assertEqual((result['exportsBefore'], result['dropped'], result['droppedGlslang'], result['droppedCxx'],
                          result['droppedObjcClasses']), (12, 4, 1, 1, 1))
        self.assertEqual((result['missingGuestEntryPoints'], result['refusedKept']), ([], []))

    def test_an_unexported_looked_up_name_is_not_added(self):
        # The engine may look up a function another image defines (or none does): it is not exported from here.
        result = tool.compute(b'\x00s2a_shell_library_vc\x00', nm())
        self.assertNotIn('_s2a_shell_library_vc', result['keep'])

    def test_refusals(self):
        with tempfile.TemporaryDirectory(prefix='s2arm-exports-') as directory:
            folder = Path(directory)
            binary, listing = folder / 'S2ArmEngine', folder / 'nm.txt'
            out, report = folder / 'S2ArmEngine.exports', folder / 'S2ArmEngine.exports.json'
            arguments = [str(path) for path in (binary, listing, out, report)]
            binary.write_bytes(b'\x00S2A_InitSession\x00')
            listing.write_text(nm('_S2A_InitSession'))
            self.assertEqual(tool.main(arguments), 0)
            self.assertEqual(out.read_text().split(), sorted(['_S2A_InitSession'] +
                                                             ['_' + n for n in tool.GUEST_ENTRY_POINTS]))
            self.assertEqual(json.loads(report.read_text())['kept'], 6)
            # A guest entry point missing from the unrestricted link.
            out.unlink()
            listing.write_text('\n'.join(ENTRY[1:]) + '\n')
            self.assertEqual(tool.main(arguments), 1)
            self.assertFalse(out.exists(), 'no list is written for a refused link')
            self.assertEqual(json.loads(report.read_text())['missingGuestEntryPoints'], [tool.GUEST_ENTRY_POINTS[0]])
            # A kept name that names glslang (looked up by string).
            binary.write_bytes(b'\x00glslang_initialize_process\x00')
            listing.write_text(nm('_glslang_initialize_process'))
            self.assertEqual(tool.main(arguments), 1)
            self.assertFalse(out.exists())
            self.assertEqual(json.loads(report.read_text())['refusedKept'], ['_glslang_initialize_process'])
            self.assertEqual(tool.main(arguments[:3]), 2)

    def test_the_guest_link_uses_the_list(self):
        make = (ROOT / 'build-utils/s2arm/engine/guest.mk').read_text()
        self.assertIn('$(S2ARM_GUEST_LINK) -o $(S2ARM_GUEST_OPEN)\n', make)
        self.assertIn('export_list.py $(S2ARM_GUEST_OPEN) $(S2ARM_GUEST_OPEN).nm $(S2ARM_GUEST_EXPORTS) $(S2ARM_GUEST_EXPORTS).json', make)
        self.assertIn('$(S2ARM_GUEST_LINK) -Wl,-exported_symbols_list,$(S2ARM_GUEST_EXPORTS) -o $(S2ARM_GUEST_FW)/S2ArmEngine', make)
        bridge = (ROOT / 'packages/s2arm_engine_bridge/ios/Classes/S2ArmGuestABI.h').read_text()
        for name in tool.GUEST_ENTRY_POINTS[:4]:
            self.assertIn(f'"{name}"', bridge, 'the host bridge looks it up by this name')


if __name__ == '__main__':
    unittest.main()
