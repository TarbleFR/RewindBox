#!/usr/bin/env python3
"""Every Xbox 360 JIT attach goes through RewindBox's full-width StikJIT.

XeniaCore lifts XeniOS's 8 GB code-region limit (NeoXeniaExecuteRegionLimit):
that limit exists because StikDebug 3.1.x writes 36-bit addresses. The lifted
limit is only safe while the debugger that prepares the region is the StikJIT
RewindBox builds from source with build-utils/patch_stikjit_rpcs3.py (16 hex
digits, marker NEOSTATION_STIKJIT_RPCS3_V1). This contract ties each link:
patch -> install -> helper linkage -> IPA validator -> runtime refusal before
attach (Dart) and before the Core's prepare (bridge).
"""
from pathlib import Path
import importlib.util
import json
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / 'packages/xenia_internal_bridge/ios/Classes/XeniaInternalBridgePlugin.mm'
CORE = ROOT / 'packages/xenia_internal_bridge/core/XeniaCore.mm'
SERVICE = ROOT / 'lib/services/xenia_jit_service.dart'


def load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class XeniaJitTransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pin = json.loads((ROOT / 'build-utils/stikjit/source.json').read_text())
        cls.patch = load(ROOT / 'build-utils/patch_stikjit_rpcs3.py')
        cls.patch_text = (ROOT / 'build-utils/patch_stikjit_rpcs3.py').read_text()
        cls.install = (ROOT / 'build-utils/install_patched_stikjit.py').read_text()
        cls.validator = (ROOT / 'build-utils/validate_stikjit_ipa.py').read_text()
        cls.configure = (ROOT / 'build-utils/configure_xenia_ios.py').read_text()
        cls.podspec = (ROOT / 'packages/xenia_jit_helper/ios/xenia_jit_helper.podspec').read_text()
        cls.bridge = BRIDGE.read_text()
        cls.core = CORE.read_text()
        cls.service = SERVICE.read_text()
        cls.marker = cls.pin['transport_marker']

    def test_one_marker_names_the_full_width_transport(self):
        self.assertEqual(self.marker, 'NEOSTATION_STIKJIT_RPCS3_V1')
        self.assertEqual(self.patch.SWIFT_MARKER, self.marker)
        self.assertIn(f"SWIFT_MARKER = b'{self.marker}'", self.install)
        self.assertIn(
            f'static NSString* const kXeniaFullWidthTransportMarker = @"{self.marker}";',
            self.bridge,
        )

    def test_the_patch_writes_sixteen_hex_digits(self):
        self.assertIn("'    private static let jitAddressHexDigits = 16\\n'", self.patch_text)
        self.assertIn("'    private static let jitPageCommandLength = 26\\n'", self.patch_text)
        self.assertIn('for nibble in 0..<Self.jitAddressHexDigits {', self.patch_text)
        self.assertIn('let shift = UInt64((Self.jitAddressHexDigits - 1 - nibble) * 4)', self.patch_text)
        # The marker is in the same patched source as the serializer: a binary
        # carrying it was built with the 16-digit writer.
        self.assertIn('neoStationPatchID = "{SWIFT_MARKER}"', self.patch_text)

    def test_only_a_marked_stikjit_enters_the_app(self):
        self.assertIn('if SWIFT_MARKER not in binary_data:', self.install)
        self.assertIn("prefix=app+'Frameworks/StikJIT.framework/'", self.validator)
        self.assertIn("for marker in (pin['classic_attach_marker'],pin['transport_marker']):", self.validator)
        self.assertIn('assert marker.encode() in binary,marker', self.validator)

    def test_the_helper_loads_the_app_stikjit_and_embeds_none(self):
        stik = "'../packages/stikjit_bridge/ios/Frameworks/StikJIT.xcframework/ios-arm64/StikJIT.framework'"
        self.assertIn(f'stik_path = {stik}', self.configure)
        self.assertIn('framework_phase.add_file_reference(stik_ref, true)', self.configure)
        self.assertIn(
            "settings['LD_RUNPATH_SEARCH_PATHS'] = '$(inherited) @executable_path/Frameworks @executable_path/../../Frameworks'",
            self.configure,
        )
        # The only copy phase this script writes embeds the helper in Runner;
        # nothing copies StikJIT into the appex.
        self.assertEqual(self.configure.count('new_copy_files_build_phase('), 1)
        self.assertIn("runner.new_copy_files_build_phase('Embed App Extensions')", self.configure)
        self.assertNotIn('vendored_frameworks', self.podspec)
        self.assertIn('stikjit_bridge/ios/Frameworks/StikJIT.xcframework/ios-arm64', self.podspec)

    def test_the_bridge_checks_every_stikjit_the_helper_can_load(self):
        problem = self.bridge[self.bridge.index('static NSString* XeniaJitTransportProblem(void) {'):]
        problem = problem[:problem.index('\n}\n')]
        self.assertIn('main.privateFrameworksPath stringByAppendingPathComponent:@"StikJIT.framework/StikJIT"', problem)
        self.assertIn('@"XeniaJITHelper.appex/Frameworks/StikJIT.framework/StikJIT"', problem)
        self.assertEqual(problem.count('XeniaFileContains('), 2)
        self.assertIn('@"transportFullWidth" : @(XeniaJitTransportProblem() == nil),', self.bridge)

    def test_the_bridge_refuses_before_the_core_prepares(self):
        guard = self.bridge.index(
            'if ((api->jit_state() & NEO_XENIA_JIT_NEEDS_TOOL) && (!handshake || XeniaJitTransportProblem())) {'
        )
        self.assertLess(guard, self.bridge.index('stage = @"jitToolUnverified";', guard) + 1)
        self.assertLess(guard, self.bridge.index('api->prepare(&configuration', guard))
        self.assertLess(guard, self.bridge.index('XeniaJitConfirmCoreLoadHandoff()', guard))

    def test_dart_refuses_before_any_attach(self):
        plan = self.service[self.service.index('static XeniaJitPlan planFor('):]
        unsupported = plan.index(
            "if (state['transportFullWidth'] != true) {\n        return XeniaJitPlan.toolUnsupported;"
        )
        self.assertLess(unsupported, plan.index('XeniaJitPlan.attachForCoreHandshake'))
        self.assertLess(unsupported, plan.index('XeniaJitPlan.reuseAttachedTool'))
        ensure = self.service[self.service.index('static Future<XeniaJitOutcome> ensure('):]
        refusal = ensure.index('if (plan == XeniaJitPlan.toolUnsupported) {')
        self.assertLess(refusal, ensure.index('pairingFile('))
        self.assertLess(refusal, ensure.index('prepareJit('))
        self.assertIn("'jitToolUnsupported',", ensure[refusal:refusal + 200])

    def test_the_core_lifts_the_limit_only_for_this_transport(self):
        self.assertRegex(
            self.core,
            re.compile(
                r'extern "C" uintptr_t NeoXeniaExecuteRegionLimit\(void\) \{\s*return uintptr_t\(1\) << 47;\s*\}'
            ),
        )
        limit = self.core[:self.core.index('extern "C" uintptr_t NeoXeniaExecuteRegionLimit(void)')]
        limit = limit[limit.rindex('\n\n'):]
        self.assertIn('build-utils/patch_stikjit_rpcs3.py', limit)
        self.assertIn('validate_stikjit_ipa.py', limit)


if __name__ == '__main__':
    unittest.main()
