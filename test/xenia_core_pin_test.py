#!/usr/bin/env python3
"""build-utils/xenia/core_pin.py on a synthetic XeniaCore artifact (no XeniOS bytes).

The artifact is a zip as xenia-core.yml uploads it (XeniaCore.framework with
its resources, and XeniaCore.json); the binary is a tiny arm64 Mach-O written
by the shader-converter validator test's generator.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


core_pin = load('core_pin', ROOT / 'build-utils' / 'xenia' / 'core_pin.py')
generator = load('xenia_shader_converter_validator_test', ROOT / 'test' / 'xenia_shader_converter_validator_test.py')
REVISION = json.loads((ROOT / 'build-utils' / 'xenia' / 'source.json').read_text())['revision']


def core_binary(**overrides) -> bytes:
    options = dict(minos=(26, 0, 0), install='@rpath/XeniaCore.framework/XeniaCore',
                   exports=['_NeoXenia_GetAPI'],
                   dependencies=('/usr/lib/libSystem.B.dylib', '@rpath/libmetalirconverter.dylib'))
    options.update(overrides)
    return generator.dylib(**options)


def artifact(directory: Path, binary: bytes, *, source: str = REVISION, extra: dict | None = None) -> Path:
    report = {'framework': 'XeniaCore.framework', 'bytes': len(binary),
              'sha256': hashlib.sha256(binary).hexdigest(), 'minos': '26.0.0', 'sdk': '27.2.0',
              'dependencies': ['/usr/lib/libSystem.B.dylib', '@rpath/libmetalirconverter.dylib'],
              'exports': ['_NeoXenia_GetAPI'], 'objc_classes': 0, 'source': source}
    path = directory / 'XeniaCore-test.zip'
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('XeniaCore.framework/XeniaCore', binary)
        for name in ('Info.plist', 'LICENSE.txt', 'Acknowledgements.json'):
            archive.writestr('XeniaCore.framework/' + name, 'synthetic')
        archive.writestr('XeniaCore.json', json.dumps(report))
        for name, data in (extra or {}).items():
            archive.writestr(name, data)
    return path


class CorePin(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = Path(tempfile.mkdtemp())
        self.pin = self.directory / 'core-pin.json'
        core_pin.PIN = self.pin

    def tearDown(self) -> None:
        shutil.rmtree(self.directory)

    def make_pin(self, zip_path: Path) -> dict:
        code = core_pin.main(['pin', str(zip_path), '--run', '1', '--job', '2', '--attempt', '1',
                              '--artifact', '3', '--name', 'XeniaCore-test', '--expires', '2026-11-25T00:00:00Z'])
        self.assertEqual(code, 0)
        return json.loads(self.pin.read_text())

    def verify(self, location: Path) -> int:
        return core_pin.main(['verify', str(location), '--pin', str(self.pin)])

    def test_a_pinned_artifact_verifies_as_zip_and_as_extracted_folder(self) -> None:
        zip_path = artifact(self.directory, core_binary())
        record = self.make_pin(zip_path)
        self.assertEqual(record['sha256'], hashlib.sha256(zip_path.read_bytes()).hexdigest())
        self.assertEqual(record['image'], 'Frameworks/XeniaCore.framework/XeniaCore')
        self.assertEqual(len(record['packagedFingerprint']), 64)
        self.assertEqual(record['source'], REVISION)
        self.assertEqual(self.verify(zip_path), 0)
        extracted = self.directory / 'extracted'
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(extracted)
        self.assertEqual(self.verify(extracted), 0)

    def test_another_binary_or_artifact_is_refused(self) -> None:
        self.make_pin(artifact(self.directory, core_binary()))
        other = self.directory / 'other'
        other.mkdir()
        changed = artifact(other, core_binary(exports=['_NeoXenia_GetAPI'], minos=(26, 0, 0),
                                              install='@rpath/XeniaCore.framework/XeniaCore',
                                              dependencies=('/usr/lib/libSystem.B.dylib',
                                                            '@rpath/libmetalirconverter.dylib',
                                                            '/usr/lib/libc++.1.dylib')))
        self.assertEqual(self.verify(changed), 1)

    def test_an_artifact_that_is_not_the_expected_core_is_refused(self) -> None:
        cases = {
            'converter inside': dict(extra={'libmetalirconverter.dylib': b'x'}),
            'another revision': dict(source='0' * 40),
        }
        for label, options in cases.items():
            with self.subTest(label):
                folder = self.directory / label.replace(' ', '-')
                folder.mkdir()
                with self.assertRaises(SystemExit):
                    core_pin.facts(core_pin.read_artifact(artifact(folder, core_binary(), **options))[0])
        for label, binary in {
            'iOS 18 image': core_binary(minos=(18, 0, 0)),
            'extra export': core_binary(exports=['_NeoXenia_GetAPI', '_main']),
            'no converter dependency': core_binary(dependencies=('/usr/lib/libSystem.B.dylib',)),
        }.items():
            with self.subTest(label):
                folder = self.directory / label.replace(' ', '-')
                folder.mkdir()
                with self.assertRaises(SystemExit):
                    core_pin.facts(core_pin.read_artifact(artifact(folder, binary))[0])


if __name__ == '__main__':
    unittest.main()
