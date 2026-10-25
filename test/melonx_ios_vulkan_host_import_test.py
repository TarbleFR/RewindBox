#!/usr/bin/env python3
"""Build 529 regression: MoltenVK host-pointer import must be opt-out on iOS."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
from adapt_runtime import disable_ios_host_import


class HostImportFallbackTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.src = Path(self.temp.name)
        self.initialization = self.src / 'src/Ryujinx.Graphics.Vulkan/VulkanInitialization.cs'
        self.renderer = self.src / 'src/Ryujinx.Graphics.Vulkan/VulkanRenderer.cs'
        self.texture = self.src / 'src/Ryujinx.Graphics.Gpu/Image/TextureGroup.cs'
        for file in (self.initialization, self.renderer, self.texture):
            file.parent.mkdir(parents=True, exist_ok=True)
        self.initialization.write_text(
            'using System;\nusing System.Linq;\n'
            'var enabledExtensions = _requiredExtensions.Union(_desirableExtensions.Intersect(physicalDevice.DeviceExtensions)).ToArray();\n'
            .replace('var enabledExtensions', '            var enabledExtensions')
        )
        self.renderer.write_text(
            '            new HardwareCapabilities(\n'
            '                _physicalDevice.IsDeviceExtensionPresent(ExtExternalMemoryHost.ExtensionName),\n'
            '            );\n'
        )
        self.texture.write_text(
            'if (hostPointer != 0 && _context.Renderer.PrepareHostMapping(hostPointer, Storage.Size))\n'
            '{\n'
            '    _flushBuffer = _context.Renderer.CreateBuffer(hostPointer, (int)Storage.Size);\n'
            '    _flushBufferImported = true;\n'
            '}\n'
            'else\n'
            '{\n'
            '    _flushBuffer = _context.Renderer.CreateBuffer((int)Storage.Size, BufferAccess.HostMemory);\n'
            '    _flushBufferImported = false;\n'
            '}\n'
        )

    def test_ios_disables_import_and_keeps_copy_fallback(self):
        original_fallback = self.texture.read_bytes()
        changed = disable_ios_host_import(self.src)
        self.assertEqual(set(changed), {self.initialization, self.renderer})
        self.assertIn(
            '.Where(extension => !OperatingSystem.IsIOS() || extension != ExtExternalMemoryHost.ExtensionName)',
            self.initialization.read_text())
        self.assertIn(
            '!OperatingSystem.IsIOS() && _physicalDevice.IsDeviceExtensionPresent(ExtExternalMemoryHost.ExtensionName)',
            self.renderer.read_text())
        self.assertEqual(original_fallback, self.texture.read_bytes())
        self.assertIn('BufferAccess.HostMemory', self.texture.read_text())
        with self.assertRaises(AssertionError):
            disable_ios_host_import(self.src)  # never silently rewrite on drift

    def test_missing_fallback_refuses_to_patch(self):
        self.texture.write_text('no safe host buffer readback path\n')
        before_init, before_renderer = self.initialization.read_bytes(), self.renderer.read_bytes()
        with self.assertRaises(AssertionError):
            disable_ios_host_import(self.src)
        self.assertEqual(before_init, self.initialization.read_bytes())
        self.assertEqual(before_renderer, self.renderer.read_bytes())

    def test_missing_capability_anchor_fails_closed(self):
        self.renderer.write_text('unexpected upstream renderer revision\n')
        with self.assertRaises(AssertionError):
            disable_ios_host_import(self.src)


if __name__ == '__main__':
    unittest.main()
