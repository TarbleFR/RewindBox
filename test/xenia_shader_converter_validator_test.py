#!/usr/bin/env python3
"""build-utils/xenia/validate_shader_converter.py on synthetic Mach-O files.

No Apple bytes are involved: each case writes a tiny arm64 dylib header with
the load commands the validator reads. The real library was checked out of
band against the pin (docs/xenios-playlist.md § Shader converter).
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import struct
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'validate_shader_converter', ROOT / 'build-utils' / 'xenia' / 'validate_shader_converter.py')
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)
PIN = json.loads((ROOT / 'build-utils' / 'xenia' / 'source.json').read_text())
REQUIRED = PIN['shader_converter']['required_exports']


def _pad(blob: bytes) -> bytes:
    return blob + b'\0' * (-len(blob) % 8)


def dylib(*, platform=2, minos=(13, 0, 0), install='@rpath/libmetalirconverter.dylib',
          exports=REQUIRED, cryptid=0, dependencies=('/usr/lib/libSystem.B.dylib',)) -> bytes:
    def version(parts):
        return (parts[0] << 16) | (parts[1] << 8) | parts[2]

    commands = []
    name = _pad(install.encode() + b'\0')
    commands.append(struct.pack('<IIIIII', validator.LC_ID_DYLIB, 24 + len(name), 24, 0, 0, 0) + name)
    for dependency in dependencies:
        encoded = _pad(dependency.encode() + b'\0')
        commands.append(struct.pack('<IIIIII', validator.LC_LOAD_DYLIB, 24 + len(encoded), 24, 0,
                                    0x10000, 0x10000) + encoded)
    commands.append(struct.pack('<IIIIII', validator.LC_BUILD_VERSION, 24, platform,
                                version(minos), version((26, 4, 0)), 0))
    commands.append(struct.pack('<IIIIII', validator.LC_ENCRYPTION_INFO_64, 24, 16384, 0, cryptid, 0))
    symtab_index = len(commands)
    commands.append(b'')  # placeholder, sized below
    sizeofcmds = sum(len(command) for command in commands) + 24
    header_size = 32
    strings = b'\0' + b''.join(symbol.encode() + b'\0' for symbol in exports)
    symoff = header_size + sizeofcmds
    symbols = b''
    strx = 1
    for symbol in exports:
        symbols += struct.pack('<IBBHQ', strx, validator.N_EXT | validator.N_SECT, 1, 0, 0x1000)
        strx += len(symbol) + 1
    stroff = symoff + len(symbols)
    commands[symtab_index] = struct.pack('<IIIIII', validator.LC_SYMTAB, 24, symoff, len(exports),
                                         stroff, len(strings))
    header = struct.pack('<IiiIIIII', validator.MH_MAGIC_64, validator.CPU_TYPE_ARM64, 0,
                         validator.MH_DYLIB, len(commands), sizeofcmds, 0x100085, 0)
    return header + b''.join(commands) + symbols + strings


class ShaderConverterValidator(unittest.TestCase):
    def run_on(self, data: bytes, *flags: str) -> tuple[int, dict]:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'libmetalirconverter.dylib'
            path.write_bytes(data)
            import io
            import contextlib
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = validator.main([str(path), *flags])
            return code, json.loads(out.getvalue())

    def test_an_iphoneos_library_with_the_pinned_interface_passes(self) -> None:
        code, report = self.run_on(dylib())
        self.assertEqual(code, 0, report)
        self.assertEqual(report['platform'], 'IOS')
        self.assertEqual(report['install_name'], '@rpath/libmetalirconverter.dylib')
        self.assertFalse(report['matches_pinned_reference'])

    def test_the_wrong_platform_is_refused(self) -> None:
        for platform, name in ((1, 'MACOS'), (7, 'IOSSIMULATOR')):
            code, report = self.run_on(dylib(platform=platform))
            self.assertEqual(code, 1, name)
            self.assertTrue(any('iPhoneOS' in failure for failure in report['failures']), report)

    def test_a_missing_export_names_the_symbol(self) -> None:
        code, report = self.run_on(dylib(exports=[s for s in REQUIRED if s != '_IRCompilerCreate']))
        self.assertEqual(code, 1)
        self.assertIn('_IRCompilerCreate', ' '.join(report['failures']))

    def test_install_name_encryption_minos_and_dependencies_are_checked(self) -> None:
        cases = {
            'install name': dylib(install='/usr/local/lib/libmetalirconverter.dylib'),
            'encrypted': dylib(cryptid=1),
            'minos': dylib(minos=(26, 0, 0)),
            'non-system': dylib(dependencies=('@rpath/libLLVM.dylib',)),
        }
        for label, data in cases.items():
            code, report = self.run_on(data)
            self.assertEqual(code, 1, label)
            self.assertTrue(any(label in failure for failure in report['failures']), (label, report))

    def test_a_universal_or_foreign_file_is_refused(self) -> None:
        code, report = self.run_on(struct.pack('>II', validator.FAT_MAGIC, 2) + b'\0' * 64)
        self.assertEqual(code, 1)
        self.assertIn('universal', report['failures'][0])
        code, _ = self.run_on(b'not a mach-o file at all, really' * 4)
        self.assertEqual(code, 1)

    def test_the_pinned_digest_can_be_required(self) -> None:
        data = dylib()
        code, report = self.run_on(data, '--require-pinned-digest')
        self.assertEqual(code, 1)
        self.assertEqual(report['sha256'], hashlib.sha256(data).hexdigest())
        self.assertTrue(any('pinned upstream mirror' in failure for failure in report['failures']))
        self.assertFalse(report['matches_pinned_mirror'])

    @staticmethod
    def signed_image(payload: bytes = b'code' * 64, signature: bytes = b'S' * 32, *, linkedit_size: int = 0x4000) -> bytes:
        """A minimal thin arm64 image: __LINKEDIT, then LC_CODE_SIGNATURE pointing at the trailing blob."""
        header_size, commands_size = 32, 72 + 16
        body_offset = header_size + commands_size
        sig_offset = body_offset + len(payload)
        segment = struct.pack('<II16sQQQQIIII', 0x19, 72, b'__LINKEDIT', 0x8000, linkedit_size,
                              body_offset, linkedit_size, 1, 1, 0, 0)
        code_signature = struct.pack('<IIII', validator.LC_CODE_SIGNATURE, 16, sig_offset, len(signature))
        header = struct.pack('<IiiIIIII', validator.MH_MAGIC_64, validator.CPU_TYPE_ARM64, 0,
                             validator.MH_DYLIB, 2, commands_size, 0, 0)
        return header + segment + code_signature + payload + signature

    def test_the_signature_free_digest_ignores_only_the_signature(self) -> None:
        original = self.signed_image()
        resigned = self.signed_image(signature=b'R' * 4096, linkedit_size=0x5000)
        self.assertEqual(validator.signature_free_digest(original), validator.signature_free_digest(resigned),
                         'a new signature (and the __LINKEDIT size it needs) is not a modification')
        patched = self.signed_image(payload=b'code' * 63 + b'cod3')
        self.assertNotEqual(validator.signature_free_digest(original), validator.signature_free_digest(patched),
                            'any other changed byte (install_name_tool, strip, a patch) is')
        with self.assertRaises(ValueError):
            validator.signature_free_digest(dylib())  # no signature: nothing to compare against
        self.assertRegex(PIN['shader_converter']['upstream_mirror']['signature_free_sha256'], '^[0-9a-f]{64}$')

    def test_the_pin_matches_the_native_bridge(self) -> None:
        # The bridge's availability check and the packaging path agree.
        plugin = (ROOT / 'packages' / 'xenia_internal_bridge' / 'ios' / 'Classes' /
                  'XeniaInternalBridgePlugin.mm').read_text()
        self.assertIn('libmetalirconverter.dylib', plugin)
        self.assertEqual(PIN['shader_converter']['package_path'], 'Frameworks/libmetalirconverter.dylib')
        self.assertEqual(PIN['revision'], 'cf7c7ee452314913124d205e41e325b33891aacb')
        self.assertEqual(PIN['abi_version'], 2)
        header = (ROOT / 'packages' / 'xenia_internal_bridge' / 'ios' / 'Classes' / 'XeniaCoreABI.h').read_text()
        self.assertIn('#define NEO_XENIA_ABI_VERSION 2u', header)


if __name__ == '__main__':
    unittest.main()
