#!/usr/bin/env python3
"""build-utils/xenia/check_app_shader_converter.py on synthetic app bundles.

Each case builds a tiny Runner.app: synthetic Mach-O images (no Apple or
XeniOS bytes), the Legal/MetalShaderConverter notices copied from
assets/legal/metal-shader-converter/. Plus a static check that no script or
workflow rewrites the runtime (EA1844 2.E).
"""
from __future__ import annotations

import importlib.util
import re
import shutil
import struct
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tool = load('check_app_shader_converter', ROOT / 'build-utils' / 'xenia' / 'check_app_shader_converter.py')
gen = load('xenia_shader_converter_validator_test', ROOT / 'test' / 'xenia_shader_converter_validator_test.py')
validator = gen.validator


def runtime_image(payload: bytes = b'runtime' * 32, signature: bytes = b'A' * 64) -> bytes:
    return gen.ShaderConverterValidator.signed_image(payload=payload, signature=signature)


def image(*dependencies: str) -> bytes:
    return gen.dylib(dependencies=('/usr/lib/libSystem.B.dylib', *dependencies))


class AppShaderConverter(unittest.TestCase):
    def setUp(self) -> None:
        self.app = Path(tempfile.mkdtemp()) / 'Runner.app'
        (self.app / 'Frameworks').mkdir(parents=True)
        self.digest = validator.signature_free_digest(runtime_image())

    def tearDown(self) -> None:
        shutil.rmtree(self.app.parent)

    def write(self, relative: str, data: bytes) -> None:
        path = self.app / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def engine(self, *, runtime: bytes | None = None, notices: bool = True) -> None:
        self.write(tool.RUNTIME, runtime or runtime_image(signature=b'R' * 4096))  # re-signed for the IPA
        self.write(tool.CORE, image(tool.DEPENDENCY))
        self.write('Runner', image())
        if notices:
            for path in (ROOT / 'assets' / 'legal' / 'metal-shader-converter').iterdir():
                if path.name != 'license-sources.json':
                    self.write(f'{tool.LEGAL}/{path.name}', path.read_bytes())

    def test_an_app_without_the_xenios_engine_is_unchanged(self) -> None:
        self.write('Runner', image())
        self.assertEqual(tool.check(self.app, self.digest), [])

    def test_the_engine_with_a_resigned_runtime_and_its_notices_passes(self) -> None:
        self.engine()
        self.assertEqual(tool.check(self.app, self.digest), [])

    def test_a_modified_runtime_is_refused(self) -> None:
        self.engine(runtime=runtime_image(payload=b'runtime' * 31 + b'runtim3'))
        self.assertTrue(any('2.E' in failure for failure in tool.check(self.app, self.digest)))

    def test_another_image_loading_the_runtime_is_refused(self) -> None:
        self.engine()
        self.write('PlugIns/Other.appex/Other', image(tool.DEPENDENCY))
        self.assertTrue(any('only XeniaCore' in failure for failure in tool.check(self.app, self.digest)))

    def test_missing_notices_or_a_lone_half_is_refused(self) -> None:
        self.engine(notices=False)
        self.assertTrue(any('2.D' in failure for failure in tool.check(self.app, self.digest)))
        (self.app / tool.CORE).unlink()
        self.assertEqual(tool.check(self.app, self.digest), [f'{tool.RUNTIME} and {tool.CORE} ship together or not at all'])

    def test_no_script_or_workflow_rewrites_the_runtime(self) -> None:
        rewriting = re.compile(r'(install_name_tool|\bstrip\b|\blipo\b|vtool|bitcode_strip)[^\n]*libmetalirconverter'
                               r'|libmetalirconverter[^\n]*(install_name_tool|\bstrip\b|\blipo\b|vtool|bitcode_strip)')
        offenders = []
        for folder in ('build-utils', '.github', 'packages', 'tools'):
            for path in (ROOT / folder).rglob('*'):
                if path.suffix in ('.py', '.sh', '.yml', '.yaml', '.rb', '.cmake', '.podspec') and path.is_file():
                    if rewriting.search(path.read_text(encoding='utf-8', errors='replace')):
                        offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual(offenders, [])


if __name__ == '__main__':
    unittest.main()
