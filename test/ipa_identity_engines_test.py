#!/usr/bin/env python3
"""Closed IPA sets for engines packaged with an identity file (plain python3, standard library only).

    python3 -B test/ipa_identity_engines_test.py

validate_single_ipa_distribution.IDENTITY_ENGINES maps an identity file at the app root (written by the delivery step
that embeds the engine) to the JIT helper it adds and the images it requires: XeniaCore, with XeniaJITHelper.appex,
Frameworks/XeniaCore.framework/XeniaCore and Frameworks/libmetalirconverter.dylib. Without the file the expected sets
are today's and the images are refused. These tests run the four places that hold the closed sets on synthetic IPAs
(the fixtures of single_ipa_distribution_test.py): validate_single_ipa_distribution.validate, the Dolphin
verify_ipa.validate, validate_rpcs3_ipa.validate_helper_bundles, the standard delivery's version step (the real
heredoc of standard-delivery.yml, base 8 bundles plus one helper per packaged identity) and
verify_downloaded_delivery.packaged_engine_helpers. Synthetic Mach-O images: no device, no signing, no XeniOS bytes.
"""
from __future__ import annotations

import importlib.util
import json
import hashlib
import os
import plistlib
import re
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for part in ('build-utils', 'packages/dolphin_internal_bridge/ci', '.github/diagnostics'):
    sys.path.insert(0, str(ROOT / part))
spec = importlib.util.spec_from_file_location('single_ipa_distribution_test', ROOT / 'test/single_ipa_distribution_test.py')
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)
validator, rpcs3_validator, dolphin_validator = fixtures.validator, fixtures.rpcs3_validator, fixtures.dolphin_validator
import verify_downloaded_delivery as downloaded  # noqa: E402
from delivery_benchmark import payload_fingerprint  # noqa: E402

APP = fixtures.APP
HELPER = APP + 'PlugIns/XeniaJITHelper.appex/'
CORE = APP + 'Frameworks/XeniaCore.framework/XeniaCore'
CONVERTER = APP + 'Frameworks/libmetalirconverter.dylib'
IDENTITY = APP + 'Xenia-native-identity.json'


def with_xenia(members):
    """The members plus the Xenia identity, its helper (a renamed copy of the Dolphin helper) and its two images."""
    members = dict(members)
    original = APP + 'PlugIns/DolphinJITHelper.appex/'
    info = plistlib.loads(members[original + 'Info.plist'])
    info.update(CFBundleExecutable='XeniaJITHelper', CFBundleIdentifier='com.neogamelab.neostation.xeniajithelper')
    info.pop('NeoStationDolphinJITHelper')
    info['NeoStationXeniaJITHelper'] = '1'
    info['NSExtension']['NSExtensionPrincipalClass'] = 'XeniaJITRequestHandler'
    members[HELPER + 'Info.plist'] = plistlib.dumps(info)
    members[HELPER + 'XeniaJITHelper'] = members[original + 'DolphinJITHelper']
    members[CORE] = fixtures.packaging_image({}, filetype=6, dependencies=('@rpath/libmetalirconverter.dylib',),
                                             rpaths=('@executable_path/Frameworks', '@loader_path/..'))
    members[CONVERTER] = fixtures.packaging_image({}, filetype=6)
    members[IDENTITY] = b'{}'
    return members


def without(members, *paths):
    return {name: data for name, data in members.items() if not any(name.startswith(path) for path in paths)}


class IdentityEngines(unittest.TestCase):
    def check_rpcs3(self, members):
        with tempfile.TemporaryDirectory(prefix='xenia-rpcs3-helpers-') as temporary:
            root = Path(temporary)
            for name, data in members.items():
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            return rpcs3_validator.validate_helper_bundles(root / APP, plistlib.loads(members[APP + 'Info.plist']))

    def refused(self, members, reason):
        """Every validator that holds the closed set refuses the members with that reason."""
        fixtures_case = fixtures.SingleIPADistributionTests()
        fixtures_case.reject(members, reason)
        with self.assertRaisesRegex(rpcs3_validator.ValidationError, reason):
            self.check_rpcs3(members)

    def test_the_table_is_the_xenia_helper_contract(self):
        self.assertEqual(validator.IDENTITY_ENGINES, {'Xenia-native-identity.json': (
            {'XeniaJITHelper.appex': {'bundleSuffix': '.xeniajithelper', 'principalClass': 'XeniaJITRequestHandler',
                                      'marker': 'NeoStationXeniaJITHelper'}},
            ('Frameworks/XeniaCore.framework/XeniaCore', 'Frameworks/libmetalirconverter.dylib')),
            # Switch 2 (S2Arm), its contract checked by test/s2arm_validator_test.py.
            'S2Arm-native-identity.json': (
            {'S2ArmJITHelper.appex': {'bundleSuffix': '.s2armjithelper', 'principalClass': 'S2ArmJITRequestHandler',
                                      'marker': 'NeoStationS2ArmJITHelper'}},
            ('Frameworks/S2ArmEngine.framework/S2ArmEngine', 'Frameworks/NS2Pro.framework/NS2Pro'))})
        helper = plistlib.loads((ROOT / 'native/xenia_internal_helper/Info.plist').read_bytes())
        contract = validator.XENIA_EXTENSIONS['XeniaJITHelper.appex']
        self.assertEqual(helper['NSExtension']['NSExtensionPrincipalClass'], contract['principalClass'])
        self.assertEqual(helper['NSExtension']['NSExtensionPointIdentifier'], validator.SHARE_EXTENSION_POINT)
        self.assertEqual(helper[contract['marker']], '1')
        self.assertIn("'com.neogamelab.neostation" + contract['bundleSuffix'] + "'",
                      (ROOT / 'build-utils/configure_xenia_ios.py').read_text())
        self.assertEqual(validator.identity_engine_helpers(lambda relative: False), ({}, []))

    def test_without_the_identity_the_sets_are_todays(self):
        self.assertEqual(len(self.check_rpcs3(fixtures.complete_ipa_members())), 5)
        fixtures.SingleIPADistributionTests().validate_members(fixtures.complete_dolphin_packaging_members(),
                                                               dolphin_validator.validate)
        validator_report = fixtures.SingleIPADistributionTests().validate_members(fixtures.complete_ipa_members())
        self.assertNotIn('XeniaJITHelper.appex', {entry['bundle'] for entry in validator_report['embeddedExtensions']})

    def test_the_identity_adds_the_helper_and_requires_both_images(self):
        members = with_xenia(fixtures.complete_dolphin_packaging_members())
        self.assertEqual(len(self.check_rpcs3(members)), 6)
        case = fixtures.SingleIPADistributionTests()
        report = case.validate_members(members)
        self.assertIn('XeniaJITHelper.appex', {entry['bundle'] for entry in report['embeddedExtensions']})
        report = case.validate_members(members, dolphin_validator.validate)
        self.assertIn('XeniaJITHelper.appex', report['embeddedExtensions'])
        self.assertIn({'image': CORE, 'dependency': '@rpath/libmetalirconverter.dylib', 'resolved': CONVERTER},
                      report['resolvedDependencies'])

    def test_each_missing_part_is_refused(self):
        members = with_xenia(fixtures.complete_dolphin_packaging_members())
        self.refused(without(members, CORE), 'requires Frameworks/XeniaCore.framework/XeniaCore')
        self.refused(without(members, CONVERTER), 'requires Frameworks/libmetalirconverter.dylib')
        self.refused(without(members, HELPER), 'Unexpected app-extension set')
        broken = dict(members)
        info = plistlib.loads(broken[HELPER + 'Info.plist'])
        info['NSExtension']['NSExtensionPrincipalClass'] = 'Wrong'
        broken[HELPER + 'Info.plist'] = plistlib.dumps(info)
        self.refused(broken, 'principal class')

    def test_engine_parts_without_the_identity_are_refused(self):
        members = with_xenia(fixtures.complete_dolphin_packaging_members())
        self.refused(without(members, IDENTITY), 'is packaged without Xenia-native-identity.json')
        alone = without(members, IDENTITY, HELPER, CONVERTER)
        self.refused(alone, 'Frameworks/XeniaCore.framework/XeniaCore is packaged without')
        helper_only = without(members, IDENTITY, CORE, CONVERTER)
        self.refused(helper_only, 'Unexpected app-extension set')


VERSION_STEP = 'Verify final signed legal bundle and application and extension versions'


def version_heredoc():
    text = (ROOT / '.github/workflows/standard-delivery.yml').read_text()
    step = text[text.index('- name: ' + VERSION_STEP):]
    body = step[step.index("<<'PYVERSION'\n") + len("<<'PYVERSION'\n"):step.index('\n        PYVERSION\n')]
    return '\n'.join(line[8:] for line in body.splitlines()) + '\n'


class DeliveryVersionStep(unittest.TestCase):
    """The real heredoc of the standard delivery's version step, run on synthetic IPAs."""

    def run_step(self, members):
        version = next(line.partition(':')[2].strip().strip('"\'').split('+')[0]
                       for line in (ROOT / 'pubspec.yaml').read_text().splitlines() if line.startswith('version:'))
        with tempfile.TemporaryDirectory(prefix='delivery-version-step-') as temporary:
            work = Path(temporary)
            (work / 'build-utils').symlink_to(ROOT / 'build-utils')
            (work / 'pubspec.yaml').write_bytes((ROOT / 'pubspec.yaml').read_bytes())
            (work / 'dist').mkdir()
            (work / 'build/delivery').mkdir(parents=True)
            with zipfile.ZipFile(work / 'dist/NeoStation.ipa', 'w') as archive:
                for name, data in members.items():
                    if name.endswith('Info.plist'):
                        info = plistlib.loads(data)
                        info.update(CFBundleVersion='931', CFBundleShortVersionString=version)
                        data = plistlib.dumps(info)
                    archive.writestr(name, data)
            return subprocess.run([sys.executable, '-c', version_heredoc()], cwd=work, capture_output=True, text=True,
                                  env=dict(os.environ, IPA_NAME='NeoStation', BUILD_NUMBER='931'))

    def common(self):
        """The application and its seven extensions, as the common IPA packages them today."""
        members = fixtures.complete_ipa_members()
        for name in ('MeloNXJITHelper.appex', 'MeloNXRamDonor.appex'):
            members[APP + 'PlugIns/' + name + '/Info.plist'] = plistlib.dumps({'CFBundleIdentifier': name})
        return members

    def test_the_step_table_is_the_validators_table(self):
        heredoc = version_heredoc()
        table = re.search(r'^ENGINE_HELPERS = (\{.*\})$', heredoc, re.M)
        self.assertIsNotNone(table, 'the version step names its engine helpers')
        self.assertEqual(eval(table.group(1), {}), {identity: list(extensions) for identity, (extensions, _)
                                                     in validator.IDENTITY_ENGINES.items()})
        self.assertNotIn('sys.path', heredoc, 'the delivery workflow imports no repository module')

    def test_the_common_ipa_keeps_its_eight_bundles(self):
        self.assertIn('assert len(bundles) == 8 + len(helpers)', version_heredoc())
        result = self.run_step(self.common())
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_an_identity_adds_exactly_its_helper(self):
        members = self.common()
        members[IDENTITY] = b'{}'
        members[HELPER + 'Info.plist'] = plistlib.dumps({'CFBundleIdentifier': 'x'})
        self.assertEqual(self.run_step(members).returncode, 0)
        self.assertIn('Missing engine helper XeniaJITHelper.appex',
                      self.run_step(without(members, HELPER)).stderr)
        self.assertNotEqual(self.run_step(without(members, IDENTITY)).returncode, 0, 'nine bundles without identity')


class DownloadedDeliveryEngines(unittest.TestCase):
    """verify_downloaded_delivery.packaged_engine_helpers: identities equal the manifest's pinned engines."""

    def check(self, members, manifest, pin):
        with tempfile.TemporaryDirectory(prefix='downloaded-engines-') as temporary:
            ipa = Path(temporary) / 'x.ipa'
            with zipfile.ZipFile(ipa, 'w') as archive:
                for name, data in members.items():
                    archive.writestr(name, data)
            pin_raw = json.dumps(pin).encode()
            with zipfile.ZipFile(ipa) as archive:
                bundles = {name[len(APP):]: {} for name in archive.namelist() if name.endswith('.appex/Info.plist')}
                return downloaded.packaged_engine_helpers(archive, APP, bundles, manifest,
                                                         lambda path: pin_raw if path == 'pin.json' else None)

    def setUp(self):
        self.image = fixtures.packaging_image({}, filetype=6)
        self.other = fixtures.packaging_image({}, filetype=6, symbols={'_Other'})
        self.pin = {'packagedFingerprint': payload_fingerprint(self.image)}
        self.manifest = {'components': {'xenia': {'mode': 'pinned-engine', 'pin': 'pin.json',
                                                  'identityFile': 'Xenia-native-identity.json',
                                                  'image': 'Frameworks/XeniaCore.framework/XeniaCore'}}}
        identity = {'component': 'xenia', 'pinSha256': hashlib.sha256(json.dumps(self.pin).encode()).hexdigest(),
                    'packagedFingerprint': self.pin['packagedFingerprint']}
        self.members = {IDENTITY: json.dumps(identity).encode(), HELPER + 'Info.plist': b'', CORE: self.image}

    def test_a_pinned_engine_with_its_identity(self):
        self.assertEqual(self.check(self.members, self.manifest, self.pin), ['XeniaJITHelper.appex'])

    def test_without_engines_nothing_changes(self):
        self.assertEqual(self.check({}, {'components': {}}, self.pin), [])

    def test_identity_and_manifest_must_agree(self):
        with self.assertRaisesRegex(SystemExit, 'differ from the pinned engines'):
            self.check(self.members, {'components': {}}, self.pin)
        with self.assertRaisesRegex(SystemExit, 'differ from the pinned engines'):
            self.check(without(self.members, IDENTITY), self.manifest, self.pin)

    def test_identity_pin_and_image_must_agree(self):
        with self.assertRaisesRegex(SystemExit, 'Missing engine helper'):
            self.check(without(self.members, HELPER), self.manifest, self.pin)
        with self.assertRaisesRegex(SystemExit, 'not its pinned payload'):
            self.check(dict(self.members, **{CORE: self.other}), self.manifest, self.pin)
        with self.assertRaisesRegex(SystemExit, 'not its pinned payload'):
            self.check(self.members, self.manifest, dict(self.pin, other=1))


if __name__ == '__main__':
    unittest.main()
