#!/usr/bin/env python3
"""The S2Arm conditional of packages/dolphin_internal_bridge/ci/verify_ipa.py, on synthetic IPAs.

    python3 -B test/s2arm_dolphin_verify_ipa_test.py

verify_ipa.validate is the closed extension set of the Dolphin packager (build_support.py package) and of the seal
(delivery_benchmark.py). Without S2Arm-native-identity.json it behaves byte for byte as the common line's: same report
bytes, same refusal messages, on a matrix of common IPAs (the Dolphin packaging fixture, a stray S2Arm helper, stray
engine frameworks, an identity file elsewhere, MeloNX's own conditional, a missing helper, an empty file). Two
references are used: the common line's file itself (git blob below, when this clone has it) and the current file with
its S2Arm statements removed from the syntax tree (the three names it imports and the one conditional), which must be
the same program as that blob: the diff only adds statements, and they run only behind the identity file.
With the identity file: S2ArmJITHelper.appex joins the closed set with the contract of the distribution validator
(bundle suffix, share-services point, principal class, marker), its executable is checked like the other helpers'
(arm64 iOS image, executable mode, the host's StikJIT resolved), and both engine frameworks are required, by the
distribution validator that validate() calls first and by validate()'s own conditional (shown with the first one
stubbed out). Synthetic Mach-O only: no signature trust, no device.
"""
from __future__ import annotations

import ast
import json
import plistlib
import subprocess
import sys
import tempfile
import types
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
# verify_ipa.py of the common line before the S2Arm statements (origin/Claude at 41c76404; same blob on this branch's
# base ba04c914).
PRE_CHANGE_BLOB = '6032458096236bcf75fc007d208d4ba177dd3216'
APP = fixtures.APP
HELPER = APP + 'PlugIns/S2ArmJITHelper.appex/'
DOLPHIN_HELPER = APP + 'PlugIns/DolphinJITHelper.appex/'
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
    """The current validator's syntax tree without its S2Arm statements: the imported names and the conditional."""
    tree = ast.parse((ROOT / PATH).read_text())
    names = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == 'validate_single_ipa_distribution':
            kept = [alias for alias in node.names if not alias.name.startswith('S2ARM_')]
            names += len(node.names) - len(kept)
            node.names = kept
    conditionals = 0
    for holder in ast.walk(tree):
        body = getattr(holder, 'body', None)
        if isinstance(body, list):
            kept = [node for node in body if not (isinstance(node, ast.If) and is_s2arm(node.test))]
            conditionals += len(body) - len(kept)
            holder.body = kept
    leftover = [node.id for node in ast.walk(tree) if isinstance(node, ast.Name) and node.id.startswith('S2ARM_')]
    if names != 3 or conditionals != 1 or leftover:
        raise AssertionError(f'unexpected S2Arm statements: {names} names, {conditionals} conditionals, {leftover}')
    return tree


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


def with_frameworks(members, names=distribution.S2ARM_FRAMEWORKS):
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
                   'stray engine frameworks without identity': 'report', 'helper and frameworks without identity': 'refused',
                   'identity file outside the application root': 'refused', 'MeloNX conditional': 'report',
                   'MeloNX conditional and a stray S2Arm helper': 'refused', 'missing ARMSX2 helper': 'refused',
                   'empty file': 'refused'}


class WithoutTheIdentityFile(unittest.TestCase):
    def test_the_diff_only_adds_statements_behind_the_identity_file(self):
        source = pre_change_source()
        if source is None:
            self.skipTest('the common line blob is not in this clone')
        self.assertEqual(ast.dump(stripped_tree()), ast.dump(ast.parse(source)))

    def test_same_bytes_as_the_common_line_validator(self):
        references = {'stripped': module_from(stripped_tree(), 'verify_ipa_stripped')}
        source = pre_change_source()
        if source is not None:
            references['common line blob'] = module_from(source, 'verify_ipa_common')
        for name, members in common_cases().items():
            actual = outcome(validator, members)
            self.assertEqual(actual[0], EXPECTED_COMMON[name], name + ': ' + actual[1][:300])
            for label, reference in references.items():
                with self.subTest(case=name, reference=label):
                    self.assertEqual(actual, outcome(reference, members))
        self.assertIn('S2ArmJITHelper.appex', outcome(validator, common_cases()['stray S2Arm helper without identity'])[1])
        self.assertEqual(len(references), 1 + (source is not None))

    def test_the_common_constants_are_unchanged(self):
        self.assertEqual(validator.EXPECTED_HELPERS, distribution.EXPECTED_EXTENSIONS)
        self.assertNotIn('S2ArmJITHelper.appex', validator.EXPECTED_HELPERS)
        self.assertIs(validator.S2ARM_EXTENSIONS, distribution.S2ARM_EXTENSIONS)
        self.assertEqual((validator.S2ARM_IDENTITY, validator.S2ARM_FRAMEWORKS),
                         ('S2Arm-native-identity.json', ('S2ArmEngine', 'NS2Pro')))


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
        source = pre_change_source()
        if source is not None:
            refused = outcome(module_from(source, 'verify_ipa_common'), s2arm_ipa())
            self.assertEqual(refused[0], 'refused')
            self.assertIn('Unexpected app-extension set', refused[1])

    def test_the_engine_frameworks_and_the_helper_are_required(self):
        for name in distribution.S2ARM_FRAMEWORKS:
            with self.subTest(framework=name):
                members = s2arm_ipa()
                del members[APP + f'Frameworks/{name}.framework/{name}']
                self.assertEqual(outcome(validator, members),
                                 ('refused', 'DistributionError: S2Arm identity requires the engine frameworks: ' + name))
        members = {path: data for path, data in s2arm_ipa().items() if not path.startswith(HELPER)}
        kind, text = outcome(validator, members)
        self.assertEqual(kind, 'refused')
        self.assertIn('Unexpected app-extension set', text)

    def test_its_own_conditional_with_the_distribution_validator_stubbed(self):
        """validate()'s own checks, not only the distribution validator's: the identity admits the helper, requires
        both frameworks, and the helper meets the contract and is a real executable of the application."""
        stripped = module_from(stripped_tree(), 'verify_ipa_stripped')

        def own(module, members, plain=()):
            with mock.patch.object(module, 'validate_distribution', lambda ipa: None):
                return outcome(module, members, plain)
        self.assertEqual(own(validator, s2arm_ipa())[0], 'report')
        refused = own(stripped, s2arm_ipa())
        self.assertEqual(refused[0], 'refused')
        self.assertIn('Unexpected app-extension set', refused[1], 'without the conditional the helper is refused')
        for name in distribution.S2ARM_FRAMEWORKS:
            with self.subTest(framework=name):
                members = s2arm_ipa()
                del members[APP + f'Frameworks/{name}.framework/{name}']
                self.assertEqual(own(validator, members),
                                 ('refused', 'ValueError: S2Arm identity requires the engine frameworks: ' + name))
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
