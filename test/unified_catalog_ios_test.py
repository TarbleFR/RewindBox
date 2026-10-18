#!/usr/bin/env python3
"""Actual iPhone SDK compile/link gate plus host Foundation behavior.

Run only on macOS with Xcode. Does not rebuild emulator cores or make an IPA.
"""
from pathlib import Path
import platform
import subprocess
import tempfile
import unittest

from unified_catalog_ios_build import compile_catalog
from unified_catalog_runtime_test import PackContractTests


@unittest.skipUnless(platform.system() == 'Darwin', 'iPhone SDK gate requires macOS/Xcode')
class IPhoneCatalogTests(unittest.TestCase):
    def test_iphone_sdk_compile_and_link(self):
        sdk = subprocess.check_output(['xcrun', '--sdk', 'iphoneos', '--show-sdk-path'], text=True).strip()
        target = 'arm64-apple-ios17.4'
        with tempfile.TemporaryDirectory(prefix='neo-cheat-iphone-') as folder:
            work = Path(folder)
            objects = compile_catalog('iphoneos', target, sdk, work, plugin=True)
            library = work / 'libneo_cheat_catalog.dylib'
            subprocess.run(['xcrun', '--sdk', 'iphoneos', 'clang', '-target', target,
                            '-isysroot', sdk, '-dynamiclib', '-fobjc-arc',
                            *(str(obj) for obj in objects), '-framework', 'Foundation',
                            '-framework', 'UIKit', '-lz', '-Wl,-undefined,dynamic_lookup',
                            '-o', str(library)], check=True)
            undefined = subprocess.check_output(['xcrun', 'nm', '-u', str(library)], text=True)
            missing = [line for line in undefined.splitlines() if '_OBJC_CLASS_$_NeoUnified' in line]
            self.assertEqual(missing, [], 'catalogue declares an unresolved internal class')


if __name__ == '__main__':
    unittest.main(verbosity=2)
