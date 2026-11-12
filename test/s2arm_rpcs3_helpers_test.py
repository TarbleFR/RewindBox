#!/usr/bin/env python3
"""build-utils/validate_rpcs3_ipa.py validate_helper_bundles with the S2Arm entry of IDENTITY_ENGINES.

    python3 -B test/s2arm_rpcs3_helpers_test.py

validate_helper_bundles is the closed extension set of the recipe's `structure` step (validate_rpcs3_ipa.validate_ipa,
on the extracted IPA). The file is the common line's (session 03's design, Claude c0aae729: git blob below): S2Arm
enters only through its entry of validate_single_ipa_distribution.IDENTITY_ENGINES, read through
identity_engine_helpers. The reference is the same validator with that entry removed from the table. Without
S2Arm-native-identity.json at the app root it gives the same helper identifiers and refusal messages as the reference
on a matrix of common applications (the five extensions, a stray S2Arm helper, an identity file elsewhere, MeloNX's own
conditional, a missing helper, an extension outside PlugIns), except that an S2Arm engine image packaged without the
identity is refused, with that reason.
With the identity file: S2ArmJITHelper.appex joins the closed set and every per-extension check of the common
validator applies to it (share-services point, principal class, package type, marker, bundle identifier, host
versions, executable name, arm64 executable, no VPN entitlement), and both engine images are required.
validate_ipa itself (RPCS3 Core, nm, otool, file) needs a macOS runner and the Core: not run here.
"""
from __future__ import annotations

import json
import plistlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for part in ('build-utils', 'test'):
    if str(ROOT / part) not in sys.path:
        sys.path.insert(0, str(ROOT / part))

import validate_single_ipa_distribution as distribution  # noqa: E402
import single_ipa_distribution_test as fixtures  # noqa: E402
import validate_rpcs3_ipa as validator  # noqa: E402

PATH = 'build-utils/validate_rpcs3_ipa.py'
# validate_rpcs3_ipa.py of the common line with the identity table (origin/Claude at b4ef45fc): this branch keeps its
# bytes.
COMMON_BLOB = '02df21a4e371081389cb151bc11070574ab7b41e'
FRAMEWORKS = ('S2ArmEngine', 'NS2Pro')
APP = fixtures.APP
HELPER = APP + 'PlugIns/S2ArmJITHelper.appex/'
RPCS3_HELPER = APP + 'PlugIns/RPCS3JITHelper.appex/'
MELONX_FRAMEWORKS = ('MeloNXCore', 'MeloNXMoltenVK', 'MeloNXSDL3', 'MeloNXAvCodec', 'MeloNXAvUtil', 'MeloNXJitSupport')


def file_blob():
    return subprocess.run(['git', 'hash-object', str(ROOT / PATH)], capture_output=True, text=True, check=True).stdout.strip()


def without_s2arm_entry():
    """The closed-set table without the S2Arm entry, for every validator that reads it (one shared dict)."""
    patch = mock.patch.dict(distribution.IDENTITY_ENGINES)
    patch.start()
    del distribution.IDENTITY_ENGINES[distribution.S2ARM_IDENTITY]
    return patch


def reference(members):
    patch = without_s2arm_entry()
    try:
        return outcome(validator, members)
    finally:
        patch.stop()


def images_without_identity():
    return 'ValidationError: ' + '; '.join(f'{image} is packaged without {distribution.S2ARM_IDENTITY}'
                                           for image in distribution.S2ARM_IMAGES)


def info(members, prefix):
    return plistlib.loads(members[prefix + 'Info.plist'])


def with_helper(members, change=None, executable=None):
    """A copy of the RPCS3 helper fixture under the S2Arm helper contract."""
    members = dict(members)
    value = info(members, RPCS3_HELPER)
    contract = distribution.S2ARM_EXTENSIONS['S2ArmJITHelper.appex']
    value.pop('NeoStationRPCS3JITHelper')
    value.update(CFBundleExecutable='S2ArmJITHelper',
                 CFBundleIdentifier='com.neogamelab.neostation' + contract['bundleSuffix'], **{contract['marker']: '1'})
    value['NSExtension']['NSExtensionPrincipalClass'] = contract['principalClass']
    if change:
        change(value)
    members[HELPER + 'Info.plist'] = plistlib.dumps(value)
    members[HELPER + 'S2ArmJITHelper'] = members[RPCS3_HELPER + 'RPCS3JITHelper'] if executable is None else executable
    return members


def with_frameworks(members, names=FRAMEWORKS):
    members = dict(members)
    for name in names:
        members[APP + f'Frameworks/{name}.framework/{name}'] = fixtures.macho(None, filetype=6)
        members[APP + f'Frameworks/{name}.framework/Info.plist'] = plistlib.dumps({'CFBundleExecutable': name})
    return members


def with_identity(members, path=APP + distribution.S2ARM_IDENTITY):
    members = dict(members)
    members[path] = json.dumps({'schema': 1, 'engine': 'S2Arm'}).encode()
    return members


def with_melonx(members):
    members = dict(members)
    members[APP + 'MeloNX-native-identity.json'] = b'{}'
    source, target = APP + 'PlugIns/DolphinJITHelper.appex/', APP + 'PlugIns/MeloNXJITHelper.appex/'
    value = info(members, source)
    value.update(CFBundleExecutable='MeloNXJITHelper', CFBundleIdentifier='com.neogamelab.neostation.melonxjithelper')
    value.pop('NeoStationDolphinJITHelper')
    value['NeoStationMeloNXJITHelper'] = '1'
    value['NSExtension']['NSExtensionPrincipalClass'] = 'MeloNXJITRequestHandler'
    members[target + 'Info.plist'] = plistlib.dumps(value)
    members[target + 'MeloNXJITHelper'] = members[source + 'DolphinJITHelper']
    for name in MELONX_FRAMEWORKS:
        members[APP + f'Frameworks/{name}.framework/{name}'] = fixtures.macho(None, filetype=6)
    return members


def s2arm_app():
    return with_identity(with_frameworks(with_helper(fixtures.complete_ipa_members())))


def outcome(check, members):
    """The exact result of validate_helper_bundles on the extracted members: the identifiers, or the refusal."""
    directory = tempfile.mkdtemp(prefix='s2arm-rpcs3-helpers-')
    try:
        root = Path(directory)
        for name, data in members.items():
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        app = root / APP
        host = plistlib.loads((app / 'Info.plist').read_bytes())
        try:
            return 'report', json.dumps(check.validate_helper_bundles(app, host, root), indent=2, sort_keys=True)
        except Exception as error:   # noqa: BLE001 - the exact refusal is the result being compared
            return 'refused', type(error).__name__ + ': ' + str(error)
    finally:
        shutil.rmtree(directory)


def common_cases():
    common = fixtures.complete_ipa_members()
    missing = {path: data for path, data in common.items() if not path.startswith(APP + 'PlugIns/ARMSX2JITHelper.appex/')}
    outside = dict(common)
    outside['Payload/Other.appex/Info.plist'] = plistlib.dumps({})
    return {
        'common application': common,
        'stray S2Arm helper without identity': with_helper(common),
        'stray engine frameworks without identity': with_frameworks(common),
        'helper and frameworks without identity': with_frameworks(with_helper(common)),
        'identity file outside the application root': with_identity(with_frameworks(with_helper(common)),
                                                                    APP + 'Frameworks/' + distribution.S2ARM_IDENTITY),
        'MeloNX conditional': with_melonx(common),
        'MeloNX conditional and a stray S2Arm helper': with_helper(with_melonx(common)),
        'missing ARMSX2 helper': missing,
        'extension outside PlugIns': outside,
    }


EXPECTED_COMMON = {'common application': 'report', 'stray S2Arm helper without identity': 'refused',
                   'stray engine frameworks without identity': 'refused', 'helper and frameworks without identity': 'refused',
                   'identity file outside the application root': 'refused', 'MeloNX conditional': 'report',
                   'MeloNX conditional and a stray S2Arm helper': 'refused', 'missing ARMSX2 helper': 'refused',
                   'extension outside PlugIns': 'refused'}


IMAGES_WITHOUT_IDENTITY = {'stray engine frameworks without identity', 'helper and frameworks without identity',
                           'identity file outside the application root'}


class WithoutTheIdentityFile(unittest.TestCase):
    def test_the_file_is_the_common_line_file(self):
        self.assertEqual(file_blob(), COMMON_BLOB)
        self.assertNotIn('S2ARM', (ROOT / PATH).read_text())
        self.assertIs(validator.identity_engine_helpers, distribution.identity_engine_helpers)

    def test_same_result_as_without_the_s2arm_entry(self):
        for name, members in common_cases().items():
            actual = outcome(validator, members)
            self.assertEqual(actual[0], EXPECTED_COMMON[name], name + ': ' + actual[1][:300])
            if name in IMAGES_WITHOUT_IDENTITY:
                self.assertEqual(actual[1], images_without_identity(), name)
                continue
            with self.subTest(case=name):
                self.assertEqual(actual, reference(members))
        self.assertEqual(len(json.loads(outcome(validator, fixtures.complete_ipa_members())[1])), 5)
        self.assertIn('S2ArmJITHelper.appex', outcome(validator, common_cases()['stray S2Arm helper without identity'])[1])
        self.assertEqual(reference(common_cases()['stray engine frameworks without identity'])[0], 'report',
                         'without the entry stray frameworks were accepted')

    def test_the_common_constants_are_unchanged(self):
        self.assertEqual(validator.EXPECTED_HELPERS, distribution.EXPECTED_EXTENSIONS)
        self.assertNotIn('S2ArmJITHelper.appex', validator.EXPECTED_HELPERS)
        self.assertEqual(distribution.IDENTITY_ENGINES[distribution.S2ARM_IDENTITY],
                         (distribution.S2ARM_EXTENSIONS, tuple(f'Frameworks/{name}.framework/{name}' for name in FRAMEWORKS)))


class WithTheIdentityFile(unittest.TestCase):
    def test_the_s2arm_application_is_accepted_with_its_helper(self):
        kind, text = outcome(validator, s2arm_app())
        self.assertEqual(kind, 'report', text)
        identifiers = json.loads(text)
        self.assertEqual(set(identifiers), set(distribution.EXPECTED_EXTENSIONS) | {'S2ArmJITHelper.appex'})
        self.assertEqual(identifiers['S2ArmJITHelper.appex'], 'com.neogamelab.neostation.s2armjithelper')
        kind, text = outcome(validator, with_melonx(s2arm_app()))
        self.assertEqual(kind, 'report', 'both conditionals at once: ' + text[:300])
        self.assertEqual(len(json.loads(text)), 7)
        refused = reference(s2arm_app())
        self.assertEqual(refused[0], 'refused')
        self.assertIn('Unexpected app-extension set', refused[1])

    def test_the_engine_frameworks_and_the_helper_are_required(self):
        for name in FRAMEWORKS:
            with self.subTest(framework=name):
                members = s2arm_app()
                del members[APP + f'Frameworks/{name}.framework/{name}']
                self.assertEqual(outcome(validator, members), ('refused', 'ValidationError: '
                                 f'S2Arm-native-identity.json requires Frameworks/{name}.framework/{name}'))
        members = {path: data for path, data in s2arm_app().items() if not path.startswith(HELPER)}
        kind, text = outcome(validator, members)
        self.assertEqual(kind, 'refused')
        self.assertIn('Unexpected app-extension set', text)

    def test_every_per_extension_check_applies_to_the_helper(self):
        contract = distribution.S2ARM_EXTENSIONS['S2ArmJITHelper.appex']
        changes = (
            (lambda value: value['NSExtension'].update(NSExtensionPointIdentifier='com.apple.ar.viewer'),
             "has an unexpected extension point: 'com.apple.ar.viewer'"),
            (lambda value: value['NSExtension'].update(NSExtensionPrincipalClass='Rpcs3JITRequestHandler'),
             'principal class is inconsistent'),
            (lambda value: value.update(CFBundlePackageType='APPL'), 'has an invalid package type'),
            (lambda value: value.update(**{contract['marker']: '0'}), 'identity marker is missing'),
            (lambda value: value.update(CFBundleIdentifier='com.neogamelab.neostation.rpcs3jithelper'),
             'bundle identifier is inconsistent'),
            (lambda value: value.update(CFBundleVersion='1'), 'and NeoStation have different CFBundleVersion'),
            (lambda value: value.update(CFBundleShortVersionString='9.9.9'),
             'and NeoStation have different CFBundleShortVersionString'),
            (lambda value: value.update(CFBundleExecutable='Other'), 'executable identity is inconsistent'),
        )
        for change, reason in changes:
            with self.subTest(reason=reason):
                members = with_identity(with_frameworks(with_helper(fixtures.complete_ipa_members(), change)))
                self.assertEqual(outcome(validator, members), ('refused', 'ValidationError: S2ArmJITHelper.appex ' + reason))
        members = s2arm_app()
        del members[HELPER + 'S2ArmJITHelper']
        self.assertEqual(outcome(validator, members), ('refused', 'ValidationError: S2ArmJITHelper.appex executable is missing'))
        members = with_identity(with_frameworks(with_helper(fixtures.complete_ipa_members(),
                                                            executable=fixtures.macho(None, filetype=6))))
        kind, text = outcome(validator, members)
        self.assertEqual(kind, 'refused')
        self.assertIn('S2ArmJITHelper.appex', text)
        members = with_identity(with_frameworks(with_helper(
            fixtures.complete_ipa_members(),
            executable=fixtures.macho({'com.apple.developer.networking.vpn.api': ['allow-vpn']}))))
        kind, text = outcome(validator, members)
        self.assertEqual(kind, 'refused')
        self.assertIn('S2ArmJITHelper.appex contains retired VPN entitlements', text)


if __name__ == '__main__':
    unittest.main(verbosity=2)
