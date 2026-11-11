#!/usr/bin/env python3
"""The S2Arm conditional of build-utils/validate_single_ipa_distribution.py, on synthetic IPAs.

    python3 -B test/s2arm_validator_test.py

Without S2Arm-native-identity.json the validator behaves byte for byte as the common line's validator: same
report bytes, same refusal messages, on a matrix of common IPAs (valid, a stray S2Arm helper, stray engine
frameworks, an identity file elsewhere, MeloNX's own conditional, a missing helper). Two references are used:
the common line's file itself (git blob below, when this clone has it) and the current file with its S2Arm
statements removed from the syntax tree, which must be the same program as that blob: the diff only adds
statements, and they run only behind the identity file.
With the identity file: S2ArmJITHelper.appex joins the closed set with its bundle suffix, principal class and
marker, and both engine frameworks are required. Synthetic Mach-O only: no signature trust, no device.
"""
from __future__ import annotations

import ast
import copy
import json
import plistlib
import subprocess
import sys
import tempfile
import types
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for part in ('build-utils', 'test'):
    if str(ROOT / part) not in sys.path:
        sys.path.insert(0, str(ROOT / part))

import validate_single_ipa_distribution as validator  # noqa: E402
import single_ipa_distribution_test as fixtures  # noqa: E402

PATH = 'build-utils/validate_single_ipa_distribution.py'
# The validator of the common line before the S2Arm statements (origin/Claude at 4142792, unchanged since f040406).
PRE_CHANGE_BLOB = 'c7d46cbb4f6203516afd42cdbbd2c06d42a8b585'
APP = fixtures.APP
HELPER = APP + 'PlugIns/S2ArmJITHelper.appex/'
MELONX_FRAMEWORKS = ('MeloNXCore', 'MeloNXMoltenVK', 'MeloNXSDL3', 'MeloNXAvCodec', 'MeloNXAvUtil', 'MeloNXJitSupport')


def module_from(source, name):
    """A module made from validator source text or syntax tree, under its own name (the shared one is untouched)."""
    module = types.ModuleType(name)
    module.__file__ = str(ROOT / PATH)
    exec(compile(source, str(ROOT / PATH), 'exec'), module.__dict__)
    return module


def pre_change_source():
    result = subprocess.run(['git', 'cat-file', 'blob', PRE_CHANGE_BLOB], cwd=ROOT, capture_output=True)
    return result.stdout.decode() if result.returncode == 0 else None


def is_s2arm(node):
    return any(isinstance(child, ast.Name) and child.id.startswith('S2ARM_') for child in ast.walk(node))


def stripped_tree():
    """The current validator's syntax tree without the S2Arm statements (module constants and the conditional)."""
    tree = ast.parse((ROOT / PATH).read_text())
    removed = [node for node in tree.body if isinstance(node, ast.Assign) and is_s2arm(node)]
    tree.body = [node for node in tree.body if node not in removed]
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'validate')
    holders = [node for node in ast.walk(function) if isinstance(node, (ast.With, ast.FunctionDef))]
    conditionals = 0
    for holder in holders:
        kept = [node for node in holder.body if not (isinstance(node, ast.If) and is_s2arm(node.test))]
        conditionals += len(holder.body) - len(kept)
        holder.body = kept
    if len(removed) != 3 or conditionals != 1 or is_s2arm(tree):
        raise AssertionError(f'unexpected S2Arm statements: {len(removed)} constants, {conditionals} conditionals')
    return tree


def info(members, prefix):
    return plistlib.loads(members[prefix + 'Info.plist'])


def with_helper(members):
    """A copy of the RPCS3 helper fixture under the S2Arm helper contract."""
    members = dict(members)
    source = APP + 'PlugIns/RPCS3JITHelper.appex/'
    value = info(members, source)
    contract = validator.S2ARM_EXTENSIONS['S2ArmJITHelper.appex']
    value.pop('NeoStationRPCS3JITHelper')
    value.update(CFBundleExecutable='S2ArmJITHelper',
                 CFBundleIdentifier='com.neogamelab.neostation' + contract['bundleSuffix'], **{contract['marker']: '1'})
    value['NSExtension']['NSExtensionPrincipalClass'] = contract['principalClass']
    members[HELPER + 'Info.plist'] = plistlib.dumps(value)
    members[HELPER + 'S2ArmJITHelper'] = members[source + 'RPCS3JITHelper']
    return members


def with_frameworks(members, names=validator.S2ARM_FRAMEWORKS):
    members = dict(members)
    for name in names:
        members[APP + f'Frameworks/{name}.framework/{name}'] = fixtures.macho(None, filetype=6)
        members[APP + f'Frameworks/{name}.framework/Info.plist'] = plistlib.dumps({'CFBundleExecutable': name})
    return members


def with_identity(members, path=APP + validator.S2ARM_IDENTITY):
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


def s2arm_ipa():
    return with_identity(with_frameworks(with_helper(fixtures.complete_ipa_members())))


def outcome(check, members):
    """The exact result of one validator on one IPA: the report bytes, or the refusal type and message."""
    with tempfile.TemporaryDirectory(prefix='s2arm-validator-') as temporary:
        ipa = Path(temporary) / 'NeoStation.ipa'
        with zipfile.ZipFile(ipa, 'w') as archive:
            for path, data in members.items():
                entry = zipfile.ZipInfo(path)
                entry.external_attr = 0o100755 << 16
                archive.writestr(entry, data)
        try:
            return 'report', json.dumps(check.validate(ipa), indent=2, sort_keys=True)
        except Exception as error:   # noqa: BLE001 - the exact refusal is the result being compared
            return 'refused', type(error).__name__ + ': ' + str(error)


def common_cases():
    common = fixtures.complete_ipa_members()
    missing = {path: data for path, data in common.items() if not path.startswith(APP + 'PlugIns/ARMSX2JITHelper.appex/')}
    return {
        'common IPA': common,
        'stray S2Arm helper without identity': with_helper(common),
        'stray engine frameworks without identity': with_frameworks(common),
        'helper and frameworks without identity': with_frameworks(with_helper(common)),
        'identity file outside the application root': with_identity(with_frameworks(with_helper(common)),
                                                                    APP + 'Frameworks/' + validator.S2ARM_IDENTITY),
        'MeloNX conditional': with_melonx(common),
        'MeloNX conditional and a stray S2Arm helper': with_helper(with_melonx(common)),
        'missing ARMSX2 helper': missing,
        'Dolphin packaging fixture': fixtures.complete_dolphin_packaging_members(),
    }


class WithoutTheIdentityFile(unittest.TestCase):
    def test_the_diff_only_adds_statements_behind_the_identity_file(self):
        source = pre_change_source()
        if source is None:
            self.skipTest('the common line blob is not in this clone')
        self.assertEqual(ast.dump(stripped_tree()), ast.dump(ast.parse(source)))

    def test_same_bytes_as_the_common_line_validator(self):
        references = {'stripped': module_from(stripped_tree(), 'validate_single_ipa_distribution_stripped')}
        source = pre_change_source()
        if source is not None:
            references['common line blob'] = module_from(source, 'validate_single_ipa_distribution_common')
        expected = {'common IPA': 'report', 'stray S2Arm helper without identity': 'refused',
                    'stray engine frameworks without identity': 'report',
                    'helper and frameworks without identity': 'refused',
                    'identity file outside the application root': 'refused', 'MeloNX conditional': 'report',
                    'MeloNX conditional and a stray S2Arm helper': 'refused', 'missing ARMSX2 helper': 'refused',
                    'Dolphin packaging fixture': 'report'}
        for name, members in common_cases().items():
            actual = outcome(validator, members)
            self.assertEqual(actual[0], expected[name], name + ': ' + actual[1][:300])
            for label, reference in references.items():
                with self.subTest(case=name, reference=label):
                    self.assertEqual(actual, outcome(reference, members))
        self.assertIn('S2ArmJITHelper.appex', outcome(validator, common_cases()['stray S2Arm helper without identity'])[1])
        self.assertEqual(len(references), 1 + (source is not None))

    def test_the_common_constants_are_unchanged(self):
        self.assertNotIn('S2ArmJITHelper.appex', validator.EXPECTED_EXTENSIONS)
        self.assertEqual(validator.EXPECTED_EXTENSIONS, fixtures.JIT_CONTRACTS | fixtures.DONOR_CONTRACTS |
                         fixtures.RELAY_CONTRACTS)


class WithTheIdentityFile(unittest.TestCase):
    def test_the_s2arm_ipa_is_accepted_with_its_helper(self):
        kind, text = outcome(validator, s2arm_ipa())
        self.assertEqual(kind, 'report', text)
        report = json.loads(text)
        bundles = {entry['bundle']: entry for entry in report['embeddedExtensions']}
        self.assertEqual(set(bundles), set(fixtures.JIT_CONTRACTS) | set(fixtures.DONOR_CONTRACTS) |
                         set(fixtures.RELAY_CONTRACTS) | {'S2ArmJITHelper.appex'})
        self.assertEqual(bundles['S2ArmJITHelper.appex'], {
            'bundle': 'S2ArmJITHelper.appex', 'bundleIdentifier': 'com.neogamelab.neostation.s2armjithelper',
            'extensionPoint': 'com.apple.share-services'})
        self.assertIn('NeoStation.app/PlugIns/S2ArmJITHelper.appex', report['nestedSigningOrder'])
        self.assertEqual(len(report['nestedSigningOrder']), 7)
        self.assertEqual(outcome(validator, with_melonx(s2arm_ipa()))[0], 'report', 'both conditionals at once')
        source = pre_change_source()
        if source is not None:
            refused = outcome(module_from(source, 'validate_single_ipa_distribution_common'), s2arm_ipa())
            self.assertEqual(refused[0], 'refused')
            self.assertIn('Unexpected app-extension set', refused[1])

    def test_the_engine_frameworks_are_required(self):
        for name in validator.S2ARM_FRAMEWORKS:
            with self.subTest(framework=name):
                members = s2arm_ipa()
                del members[APP + f'Frameworks/{name}.framework/{name}']
                self.assertEqual(outcome(validator, members),
                                 ('refused', 'DistributionError: S2Arm identity requires the engine frameworks: ' + name))
        self.assertEqual(validator.S2ARM_FRAMEWORKS, ('S2ArmEngine', 'NS2Pro'))

    def test_the_helper_is_required_and_its_contract_checked(self):
        members = {path: data for path, data in s2arm_ipa().items() if not path.startswith(HELPER)}
        kind, text = outcome(validator, members)
        self.assertEqual(kind, 'refused')
        self.assertIn('Unexpected app-extension set', text)
        changes = (
            (lambda value: value.update(CFBundleIdentifier='com.neogamelab.neostation.rpcs3jithelper'), 'bundle identifier'),
            (lambda value: value['NSExtension'].update(NSExtensionPrincipalClass='Rpcs3JITRequestHandler'), 'principal class'),
            (lambda value: value.update(NeoStationS2ArmJITHelper='0'), 'identity marker'),
            (lambda value: value['NSExtension'].update(NSExtensionPointIdentifier='com.apple.ar.viewer'), 'extension point'),
            (lambda value: value.update(CFBundleVersion='1'), 'build numbers'),
            (lambda value: value.update(CFBundlePackageType='APPL'), 'package type'),
        )
        for change, reason in changes:
            with self.subTest(reason=reason):
                members = s2arm_ipa()
                value = info(members, HELPER)
                change(value)
                members[HELPER + 'Info.plist'] = plistlib.dumps(value)
                kind, text = outcome(validator, members)
                self.assertEqual(kind, 'refused')
                self.assertIn(reason, text)
        members = s2arm_ipa()
        members[HELPER + 'S2ArmJITHelper'] = fixtures.macho({'com.apple.developer.networking.vpn.api': ['allow-vpn']})
        self.assertIn('retired VPN entitlements', outcome(validator, members)[1])
        members = s2arm_ipa()
        members[APP + 'PlugIns/Other.appex/Info.plist'] = plistlib.dumps({})
        self.assertIn('Unexpected app-extension set', outcome(validator, members)[1])

    def test_the_contract_is_the_package_one(self):
        package = plistlib.loads((ROOT / 'packages/s2arm_jit_helper/extension/Info.plist').read_bytes())
        contract = validator.S2ARM_EXTENSIONS['S2ArmJITHelper.appex']
        self.assertEqual(set(validator.S2ARM_EXTENSIONS), {'S2ArmJITHelper.appex'})
        self.assertEqual(package[contract['marker']], '1')
        self.assertEqual(package['NSExtension']['NSExtensionPrincipalClass'], contract['principalClass'])
        self.assertEqual(package['NSExtension']['NSExtensionPointIdentifier'], validator.SHARE_EXTENSION_POINT)
        self.assertEqual(validator.S2ARM_IDENTITY, 'S2Arm-native-identity.json')
        broken = copy.deepcopy(s2arm_ipa())
        self.assertEqual(outcome(validator, broken)[0], 'report')


if __name__ == '__main__':
    unittest.main(verbosity=2)
