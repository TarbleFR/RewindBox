#!/usr/bin/env python3
"""The S2Arm conditional of build-utils/validate_rpcs3_ipa.py validate_helper_bundles, on synthetic applications.

    python3 -B test/s2arm_rpcs3_helpers_test.py

validate_helper_bundles is the closed extension set of the recipe's `structure` step (validate_rpcs3_ipa.validate_ipa,
on the extracted IPA). Without S2Arm-native-identity.json it behaves exactly as the common line's: same helper
identifiers, same refusal messages, on a matrix of common applications (the five extensions, a stray S2Arm helper,
stray engine frameworks, an identity file elsewhere, MeloNX's own conditional, a missing helper, an extension outside
PlugIns). Two references are used: the common line's file itself (git blob below, when this clone has it) and the
current file with its S2Arm statements removed from the syntax tree (the three names it imports and the one
conditional), which must be the same program as that blob.
With the identity file: S2ArmJITHelper.appex joins the closed set and every per-extension check of the common
validator applies to it (share-services point, principal class, package type, marker, bundle identifier, host
versions, executable name, arm64 executable, no VPN entitlement), and both engine frameworks are required.
validate_ipa itself (RPCS3 Core, nm, otool, file) needs a macOS runner and the Core: not run here.
"""
from __future__ import annotations

import ast
import json
import plistlib
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for part in ('build-utils', 'test'):
    if str(ROOT / part) not in sys.path:
        sys.path.insert(0, str(ROOT / part))

import validate_single_ipa_distribution as distribution  # noqa: E402
import single_ipa_distribution_test as fixtures  # noqa: E402
import validate_rpcs3_ipa as validator  # noqa: E402

PATH = 'build-utils/validate_rpcs3_ipa.py'
# validate_rpcs3_ipa.py of the common line before the S2Arm statements (origin/Claude at 41c76404; same blob on this
# branch's base ba04c914).
PRE_CHANGE_BLOB = '1a1028277da3309572e22f45c9c1ee3949dff085'
APP = fixtures.APP
HELPER = APP + 'PlugIns/S2ArmJITHelper.appex/'
RPCS3_HELPER = APP + 'PlugIns/RPCS3JITHelper.appex/'
MELONX_FRAMEWORKS = ('MeloNXCore', 'MeloNXMoltenVK', 'MeloNXSDL3', 'MeloNXAvCodec', 'MeloNXAvUtil', 'MeloNXJitSupport')


def module_from(source, name):
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
    """The current validator's syntax tree without its S2Arm statements: the imported names and the conditional."""
    tree = ast.parse((ROOT / PATH).read_text())
    names = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == 'validate_single_ipa_distribution':
            kept = [alias for alias in node.names if not alias.name.startswith('S2ARM_')]
            names += len(node.names) - len(kept)
            node.names = kept
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'validate_helper_bundles')
    conditionals = 0
    for holder in ast.walk(tree):
        body = getattr(holder, 'body', None)
        if isinstance(body, list):
            kept = [node for node in body if not (isinstance(node, ast.If) and is_s2arm(node.test))]
            if len(kept) != len(body) and holder is not function:
                raise AssertionError('an S2Arm conditional outside validate_helper_bundles')
            conditionals += len(body) - len(kept)
            holder.body = kept
    leftover = [node.id for node in ast.walk(tree) if isinstance(node, ast.Name) and node.id.startswith('S2ARM_')]
    if names != 3 or conditionals != 1 or leftover:
        raise AssertionError(f'unexpected S2Arm statements: {names} names, {conditionals} conditionals, {leftover}')
    return tree


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


def with_frameworks(members, names=distribution.S2ARM_FRAMEWORKS):
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
                   'stray engine frameworks without identity': 'report', 'helper and frameworks without identity': 'refused',
                   'identity file outside the application root': 'refused', 'MeloNX conditional': 'report',
                   'MeloNX conditional and a stray S2Arm helper': 'refused', 'missing ARMSX2 helper': 'refused',
                   'extension outside PlugIns': 'refused'}


class WithoutTheIdentityFile(unittest.TestCase):
    def test_the_diff_only_adds_statements_behind_the_identity_file(self):
        source = pre_change_source()
        if source is None:
            self.skipTest('the common line blob is not in this clone')
        self.assertEqual(ast.dump(stripped_tree()), ast.dump(ast.parse(source)))

    def test_same_result_as_the_common_line_validator(self):
        references = {'stripped': module_from(stripped_tree(), 'validate_rpcs3_ipa_stripped')}
        source = pre_change_source()
        if source is not None:
            references['common line blob'] = module_from(source, 'validate_rpcs3_ipa_common')
        for name, members in common_cases().items():
            actual = outcome(validator, members)
            self.assertEqual(actual[0], EXPECTED_COMMON[name], name + ': ' + actual[1][:300])
            for label, reference in references.items():
                with self.subTest(case=name, reference=label):
                    self.assertEqual(actual, outcome(reference, members))
        self.assertEqual(len(json.loads(outcome(validator, fixtures.complete_ipa_members())[1])), 5)
        self.assertIn('S2ArmJITHelper.appex', outcome(validator, common_cases()['stray S2Arm helper without identity'])[1])
        self.assertEqual(len(references), 1 + (source is not None))

    def test_the_common_constants_are_unchanged(self):
        self.assertEqual(validator.EXPECTED_HELPERS, distribution.EXPECTED_EXTENSIONS)
        self.assertNotIn('S2ArmJITHelper.appex', validator.EXPECTED_HELPERS)
        self.assertIs(validator.S2ARM_EXTENSIONS, distribution.S2ARM_EXTENSIONS)


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
        refused = outcome(module_from(stripped_tree(), 'validate_rpcs3_ipa_stripped'), s2arm_app())
        self.assertEqual(refused[0], 'refused')
        self.assertIn('Unexpected app-extension set', refused[1])
        source = pre_change_source()
        if source is not None:
            self.assertEqual(outcome(module_from(source, 'validate_rpcs3_ipa_common'), s2arm_app()), refused)

    def test_the_engine_frameworks_and_the_helper_are_required(self):
        for name in distribution.S2ARM_FRAMEWORKS:
            with self.subTest(framework=name):
                members = s2arm_app()
                del members[APP + f'Frameworks/{name}.framework/{name}']
                self.assertEqual(outcome(validator, members),
                                 ('refused', 'ValidationError: S2Arm identity requires the engine frameworks: ' + name))
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
