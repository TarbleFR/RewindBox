#!/usr/bin/env python3
"""packages/dolphin_internal_bridge/ci/verify_ipa.py with the S2Arm entry of IDENTITY_ENGINES, on synthetic IPAs.

    python3 -B test/s2arm_dolphin_verify_ipa_test.py

verify_ipa.validate is the closed extension set of the Dolphin packager (build_support.py package) and of the seal
(delivery_benchmark.py). The file is the common line's (session 03's design, Claude c0aae729: git blob below): S2Arm
enters only through its entry of validate_single_ipa_distribution.IDENTITY_ENGINES, which verify_ipa reads through
identity_engine_helpers. The reference is the same validator with that entry removed from the table. Without
S2Arm-native-identity.json at the app root it gives the same report bytes and refusal messages as the reference on a
matrix of common IPAs (the Dolphin packaging fixture, a stray S2Arm helper, an identity file elsewhere, MeloNX's own
conditional, a missing helper, an empty file), except that an S2Arm engine image packaged without the identity is
refused, with that reason.
With the identity file: S2ArmJITHelper.appex joins the closed set with the contract of the distribution validator
(bundle suffix, share-services point, principal class, marker), its executable is checked like the other helpers'
(arm64 iOS image, executable mode, the host's StikJIT resolved), and both engine images are required, by the
distribution validator that validate() calls first and by validate()'s own check (shown with the first one
stubbed out). Synthetic Mach-O only: no signature trust, no device.
"""
from __future__ import annotations

import json
import plistlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for part in ('build-utils', 'test', 'packages/dolphin_internal_bridge/ci'):
    if str(ROOT / part) not in sys.path:
        sys.path.insert(0, str(ROOT / part))

import validate_single_ipa_distribution as distribution  # noqa: E402
import single_ipa_distribution_test as fixtures  # noqa: E402
import verify_ipa as validator  # noqa: E402

PATH = 'packages/dolphin_internal_bridge/ci/verify_ipa.py'
# verify_ipa.py of the common line with the identity table (origin/Claude at b4ef45fc): this branch keeps its bytes.
COMMON_BLOB = '613eed254edce2cbaf54460a020be34a6a82136c'
FRAMEWORKS = ('S2ArmEngine', 'NS2Pro')
APP = fixtures.APP
HELPER = APP + 'PlugIns/S2ArmJITHelper.appex/'
DOLPHIN_HELPER = APP + 'PlugIns/DolphinJITHelper.appex/'
MELONX_FRAMEWORKS = ('MeloNXCore', 'MeloNXMoltenVK', 'MeloNXSDL3', 'MeloNXAvCodec', 'MeloNXAvUtil', 'MeloNXJitSupport')


def file_blob():
    return subprocess.run(['git', 'hash-object', str(ROOT / PATH)], capture_output=True, text=True, check=True).stdout.strip()


def without_s2arm_entry():
    """The closed-set table without the S2Arm entry, for every validator that reads it (one shared dict)."""
    patch = mock.patch.dict(distribution.IDENTITY_ENGINES)
    patch.start()
    del distribution.IDENTITY_ENGINES[distribution.S2ARM_IDENTITY]
    return patch


def reference(members, plain=()):
    patch = without_s2arm_entry()
    try:
        return outcome(validator, members, plain)
    finally:
        patch.stop()


def images_without_identity():
    return 'DistributionError: ' + '; '.join(f'{image} is packaged without {distribution.S2ARM_IDENTITY}'
                                             for image in distribution.S2ARM_IMAGES)


def info(members, prefix):
    return plistlib.loads(members[prefix + 'Info.plist'])


def with_helper(members, change=None):
    """The Dolphin helper fixture (linking the host's StikJIT) under the S2Arm helper contract."""
    members = dict(members)
    value = info(members, DOLPHIN_HELPER)
    contract = distribution.S2ARM_EXTENSIONS['S2ArmJITHelper.appex']
    value.pop('NeoStationDolphinJITHelper')
    value.update(CFBundleExecutable='S2ArmJITHelper',
                 CFBundleIdentifier='com.neogamelab.neostation' + contract['bundleSuffix'], **{contract['marker']: '1'})
    value['NSExtension']['NSExtensionPrincipalClass'] = contract['principalClass']
    if change:
        change(value)
    members[HELPER + 'Info.plist'] = plistlib.dumps(value)
    members[HELPER + 'S2ArmJITHelper'] = members[DOLPHIN_HELPER + 'DolphinJITHelper']
    return members


def with_frameworks(members, names=FRAMEWORKS):
    """The engine frameworks as arm64 iOS dylibs; the engine links the other one through the host's rpath."""
    members = dict(members)
    for name in names:
        dependencies = ('@rpath/NS2Pro.framework/NS2Pro',) if name == 'S2ArmEngine' else ()
        members[APP + f'Frameworks/{name}.framework/{name}'] = fixtures.packaging_image(
            {}, filetype=6, dependencies=dependencies + ('/usr/lib/libSystem.B.dylib',))
        members[APP + f'Frameworks/{name}.framework/Info.plist'] = plistlib.dumps(
            {'CFBundleExecutable': name, 'CFBundlePackageType': 'FMWK'})
    return members


def with_identity(members, path=APP + distribution.S2ARM_IDENTITY):
    members = dict(members)
    members[path] = json.dumps({'schema': 1, 'engine': 'S2Arm'}).encode()
    return members


def with_melonx(members):
    members = dict(members)
    members[APP + 'MeloNX-native-identity.json'] = b'{}'
    target = APP + 'PlugIns/MeloNXJITHelper.appex/'
    value = info(members, DOLPHIN_HELPER)
    value.update(CFBundleExecutable='MeloNXJITHelper', CFBundleIdentifier='com.neogamelab.neostation.melonxjithelper')
    value.pop('NeoStationDolphinJITHelper')
    value['NeoStationMeloNXJITHelper'] = '1'
    value['NSExtension']['NSExtensionPrincipalClass'] = 'MeloNXJITRequestHandler'
    members[target + 'Info.plist'] = plistlib.dumps(value)
    members[target + 'MeloNXJITHelper'] = members[DOLPHIN_HELPER + 'DolphinJITHelper']
    for name in MELONX_FRAMEWORKS:
        members[APP + f'Frameworks/{name}.framework/{name}'] = fixtures.packaging_image({}, filetype=6)
    return members


def s2arm_ipa():
    return with_identity(with_frameworks(with_helper(fixtures.complete_dolphin_packaging_members())))


def outcome(check, members, plain=()):
    """The exact result of one validator on one IPA: the report bytes, or the refusal type and message. Members are
    written with an executable mode, except those in `plain`."""
    with tempfile.TemporaryDirectory(prefix='s2arm-dolphin-verify-') as temporary:
        ipa = Path(temporary) / 'NeoStation.ipa'
        if members is not None:
            with zipfile.ZipFile(ipa, 'w') as archive:
                for path, data in members.items():
                    entry = zipfile.ZipInfo(path)
                    entry.external_attr = (0o100644 if path in plain else 0o100755) << 16
                    archive.writestr(entry, data)
        else:
            ipa.write_bytes(b'')
        try:
            return 'report', json.dumps(check.validate(ipa), indent=2, sort_keys=True)
        except Exception as error:   # noqa: BLE001 - the exact refusal is the result being compared
            return 'refused', type(error).__name__ + ': ' + str(error)


def common_cases():
    common = fixtures.complete_dolphin_packaging_members()
    missing = {path: data for path, data in common.items() if not path.startswith(APP + 'PlugIns/ARMSX2JITHelper.appex/')}
    return {
        'Dolphin packaging IPA': common,
        'stray S2Arm helper without identity': with_helper(common),
        'stray engine frameworks without identity': with_frameworks(common),
        'helper and frameworks without identity': with_frameworks(with_helper(common)),
        'identity file outside the application root': with_identity(with_frameworks(with_helper(common)),
                                                                    APP + 'Frameworks/' + distribution.S2ARM_IDENTITY),
        'MeloNX conditional': with_melonx(common),
        'MeloNX conditional and a stray S2Arm helper': with_helper(with_melonx(common)),
        'missing ARMSX2 helper': missing,
        'empty file': None,
    }


EXPECTED_COMMON = {'Dolphin packaging IPA': 'report', 'stray S2Arm helper without identity': 'refused',
                   'stray engine frameworks without identity': 'refused', 'helper and frameworks without identity': 'refused',
                   'identity file outside the application root': 'refused', 'MeloNX conditional': 'report',
                   'MeloNX conditional and a stray S2Arm helper': 'refused', 'missing ARMSX2 helper': 'refused',
                   'empty file': 'refused'}


IMAGES_WITHOUT_IDENTITY = {'stray engine frameworks without identity', 'helper and frameworks without identity',
                           'identity file outside the application root'}


class WithoutTheIdentityFile(unittest.TestCase):
    def test_the_file_is_the_common_line_file(self):
        self.assertEqual(file_blob(), COMMON_BLOB)
        self.assertNotIn('S2ARM', (ROOT / PATH).read_text())
        self.assertIs(validator.identity_engine_helpers, distribution.identity_engine_helpers)

    def test_same_bytes_as_without_the_s2arm_entry(self):
        for name, members in common_cases().items():
            actual = outcome(validator, members)
            self.assertEqual(actual[0], EXPECTED_COMMON[name], name + ': ' + actual[1][:300])
            if name in IMAGES_WITHOUT_IDENTITY:
                self.assertEqual(actual[1], images_without_identity(), name)
                continue
            with self.subTest(case=name):
                self.assertEqual(actual, reference(members))
        self.assertIn('S2ArmJITHelper.appex', outcome(validator, common_cases()['stray S2Arm helper without identity'])[1])
        self.assertEqual(reference(common_cases()['stray engine frameworks without identity'])[0], 'report',
                         'without the entry stray frameworks were accepted')

    def test_the_common_constants_are_unchanged(self):
        self.assertEqual(validator.EXPECTED_HELPERS, distribution.EXPECTED_EXTENSIONS)
        self.assertNotIn('S2ArmJITHelper.appex', validator.EXPECTED_HELPERS)
        self.assertEqual(distribution.IDENTITY_ENGINES[distribution.S2ARM_IDENTITY],
                         (distribution.S2ARM_EXTENSIONS, tuple(f'Frameworks/{name}.framework/{name}' for name in FRAMEWORKS)))
        self.assertEqual(distribution.S2ARM_IDENTITY, 'S2Arm-native-identity.json')


class WithTheIdentityFile(unittest.TestCase):
    def test_the_s2arm_ipa_is_accepted_with_its_helper_and_frameworks(self):
        kind, text = outcome(validator, s2arm_ipa())
        self.assertEqual(kind, 'report', text)
        report = json.loads(text)
        self.assertEqual(report['embeddedExtensions'], sorted(set(distribution.EXPECTED_EXTENSIONS) | {'S2ArmJITHelper.appex'}))
        self.assertEqual(report['structuralValidation'], 'passed')
        images = report['machOImages']
        for name in ('S2ArmEngine', 'NS2Pro'):
            self.assertEqual(images[APP + f'Frameworks/{name}.framework/{name}']['fileType'], 6)
        self.assertIn(HELPER + 'S2ArmJITHelper', images)
        resolved = {(item['image'], item['dependency']): item['resolved'] for item in report['resolvedDependencies']}
        self.assertEqual(resolved[(HELPER + 'S2ArmJITHelper', '@rpath/StikJIT.framework/StikJIT')],
                         APP + 'Frameworks/StikJIT.framework/StikJIT')
        self.assertEqual(resolved[(APP + 'Frameworks/S2ArmEngine.framework/S2ArmEngine', '@rpath/NS2Pro.framework/NS2Pro')],
                         APP + 'Frameworks/NS2Pro.framework/NS2Pro')
        kind, text = outcome(validator, with_melonx(s2arm_ipa()))
        self.assertEqual(kind, 'report', 'both conditionals at once: ' + text[:300])
        self.assertLessEqual({'S2ArmJITHelper.appex', 'MeloNXJITHelper.appex'}, set(json.loads(text)['embeddedExtensions']))
        refused = reference(s2arm_ipa())
        self.assertEqual(refused[0], 'refused')
        self.assertIn('Unexpected app-extension set', refused[1])

    def test_the_engine_frameworks_and_the_helper_are_required(self):
        for name in FRAMEWORKS:
            with self.subTest(framework=name):
                members = s2arm_ipa()
                del members[APP + f'Frameworks/{name}.framework/{name}']
                self.assertEqual(outcome(validator, members), ('refused', 'DistributionError: '
                                 f'S2Arm-native-identity.json requires Frameworks/{name}.framework/{name}'))
        members = {path: data for path, data in s2arm_ipa().items() if not path.startswith(HELPER)}
        kind, text = outcome(validator, members)
        self.assertEqual(kind, 'refused')
        self.assertIn('Unexpected app-extension set', text)

    def test_its_own_conditional_with_the_distribution_validator_stubbed(self):
        """validate()'s own checks, not only the distribution validator's: the identity admits the helper, requires
        both frameworks, and the helper meets the contract and is a real executable of the application."""
        def own(module, members, plain=()):
            with mock.patch.object(module, 'validate_distribution', lambda ipa: None):
                return outcome(module, members, plain)
        self.assertEqual(own(validator, s2arm_ipa())[0], 'report')
        patch = without_s2arm_entry()
        try:
            refused = own(validator, s2arm_ipa())
        finally:
            patch.stop()
        self.assertEqual(refused[0], 'refused')
        self.assertIn('Unexpected app-extension set', refused[1], 'without the entry the helper is refused')
        for name in FRAMEWORKS:
            with self.subTest(framework=name):
                members = s2arm_ipa()
                del members[APP + f'Frameworks/{name}.framework/{name}']
                self.assertEqual(own(validator, members), ('refused', 'ValueError: '
                                 f'S2Arm-native-identity.json requires Frameworks/{name}.framework/{name}'))
        contract = distribution.S2ARM_EXTENSIONS['S2ArmJITHelper.appex']
        changes = (
            (lambda value: value.update(CFBundleIdentifier='com.neogamelab.neostation.rpcs3jithelper'), 'ID is inconsistent'),
            (lambda value: value['NSExtension'].update(NSExtensionPointIdentifier='com.apple.ar.viewer'),
             'has an unexpected extension point'),
            (lambda value: value['NSExtension'].update(NSExtensionPrincipalClass='Rpcs3JITRequestHandler'),
             'principal class is inconsistent'),
            (lambda value: value.update(**{contract['marker']: '0'}), 'identity marker is missing'),
        )
        for change, reason in changes:
            with self.subTest(reason=reason):
                members = with_identity(with_frameworks(with_helper(fixtures.complete_dolphin_packaging_members(), change)))
                kind, text = own(validator, members)
                self.assertEqual(kind, 'refused')
                self.assertEqual(text, 'ValueError: S2ArmJITHelper.appex ' + reason)
        self.assertEqual(own(validator, s2arm_ipa(), plain={HELPER + 'S2ArmJITHelper'}),
                         ('refused', 'ValueError: Executable mode missing: ' + HELPER + 'S2ArmJITHelper'))
        members = s2arm_ipa()
        members[HELPER + 'S2ArmJITHelper'] = b'not an image'
        self.assertEqual(own(validator, members),
                         ('refused', 'ValueError: Required arm64 executable is missing: ' + HELPER + 'S2ArmJITHelper'))
        members = s2arm_ipa()
        members[HELPER + 'S2ArmJITHelper'] = fixtures.packaging_image({}, dependencies=('@rpath/Missing.framework/Missing',),
                                                                       rpaths=('@executable_path/../../Frameworks',))
        kind, text = own(validator, members)
        self.assertEqual(kind, 'refused')
        self.assertIn('Unresolved dependency: ' + HELPER + 'S2ArmJITHelper -> @rpath/Missing.framework/Missing', text)


if __name__ == '__main__':
    unittest.main(verbosity=2)
