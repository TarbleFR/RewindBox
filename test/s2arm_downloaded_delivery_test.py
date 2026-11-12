#!/usr/bin/env python3
"""build-utils/verify_downloaded_delivery.py with the S2Arm entry of IDENTITY_ENGINES, run through verify().

    python3 -B test/s2arm_downloaded_delivery_test.py

The offline verifier of a downloaded delivery counts the application and its extensions (eight bundles, plus the
helper of each engine whose identity file is packaged: session 03's design, Claude c0aae729) before it checks their
versions, and requires the packaged identity files to be exactly those of the manifest's pinned-engine components,
each naming its pin and carrying its pinned payload. verify() runs here end to end on a synthetic decrypted delivery,
with only what needs the network, the private key, openssl, a git history or a macOS runner replaced (the saved API
binding, the transport parts, the key match, the decryption, the base and image checks of the recipe, the effective
checkout, the six offline validators): every check of the IPA itself runs.
The file is the common line's (git blob below): S2Arm enters only through its entry of IDENTITY_ENGINES. Without
S2Arm-native-identity.json: the same report bytes, or the same refusal, as the same verifier without that entry, on
common deliveries (eight bundles, seven, nine, a stray S2Arm helper, an identity file elsewhere, wrong versions, a
changed packaged identity).
With it and the manifest's s2arm pinned engine: nine bundles with S2ArmJITHelper.appex pass (reported with their
versions); eight, or nine without the helper, and a helper of another build are refused, as are an identity without
the component, the component without the identity and an engine image that is not the pinned payload.
"""
from __future__ import annotations

import argparse
import hashlib
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
for part in ('.github/diagnostics', 'build-utils', 'packages/dolphin_internal_bridge/ci', 'test'):
    if str(ROOT / part) not in sys.path:
        sys.path.insert(0, str(ROOT / part))

import standard_delivery as recipe  # noqa: E402
import validate_single_ipa_distribution as distribution  # noqa: E402
import single_ipa_distribution_test as fixtures  # noqa: E402
import verify_downloaded_delivery as verifier  # noqa: E402
from rewind607_delivery import zip_payloads  # noqa: E402
from delivery_benchmark import payload_fingerprint  # noqa: E402

PATH = 'build-utils/verify_downloaded_delivery.py'
# The verifier of the common line with the identity table (origin/Claude at b4ef45fc): this branch keeps its bytes.
COMMON_BLOB = 'fd2f06a574e346e41b91b6d97e3e48e83cb4a491'
APP = recipe.APP_ROOT
BUILD, VERSION, SOURCE = 803, '0.0.8', 'a' * 40
HELPER = 'PlugIns/S2ArmJITHelper.appex/Info.plist'
COMMON_EXTENSIONS = sorted(distribution.EXPECTED_EXTENSIONS) + ['MeloNXJITHelper.appex', 'MeloNXRamDonor.appex']
COMPONENTS = dict(dolphin='Frameworks/DolphinCore.framework/DolphinCore', armsx2='Frameworks/ARMSX2Core.framework/ARMSX2Core',
                  rpcs3='Frameworks/libRPCS3Core.dylib')
MELONX_PIN = dict(source='b' * 40, binaries={'ios-arm64': dict(sha256='c' * 64)}, packagedFingerprint='d' * 64)
RPCS3_PIN = dict(exports=dict(added=['rpcs3_ios_fixture_export']))
SCRIPT = b'// melonx-universal.js fixture\n'
RECIPIENT = b'-----BEGIN PUBLIC KEY-----\nfixture\n-----END PUBLIC KEY-----\n'
S2ARM_PIN_PATH = 'build-utils/s2arm/engine-pin.json'
S2ARM_ENGINE = 'Frameworks/S2ArmEngine.framework/S2ArmEngine'
S2ARM_IMAGE = fixtures.packaging_image({}, filetype=6, symbols={'_s2a_rb_guest_start'})
S2ARM_PIN = dict(status='verified', packagedFingerprint=payload_fingerprint(S2ARM_IMAGE))
S2ARM_COMPONENT = dict(mode='pinned-engine', pin=S2ARM_PIN_PATH, identityFile=distribution.S2ARM_IDENTITY,
                       image=S2ARM_ENGINE)
# One date for every IPA entry: the report holds the IPA's SHA-256, so two builds of the same members must give the
# same bytes (ZipFile.writestr would date each entry with the clock, two seconds per step).
ENTRY_TIME = (2026, 11, 11, 0, 0, 0)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def file_blob():
    return subprocess.run(['git', 'hash-object', str(ROOT / PATH)], capture_output=True, text=True, check=True).stdout.strip()


def bundle(version=str(BUILD), marketing=VERSION):
    return plistlib.dumps({'CFBundleIdentifier': 'com.neogamelab.neostation', 'CFBundleVersion': version,
                           'CFBundleShortVersionString': marketing})


def identity():
    return {'schema': 1, 'build': BUILD, 'application': {'source': SOURCE}, 'physicalDeviceTested': False}


def common_delivery():
    """The members of a delivered IPA as far as the offline verifier reads them."""
    members = {APP + 'Info.plist': bundle(), APP + 'Runner': fixtures.packaging_image({}),
               APP + recipe.IDENTITY: json.dumps(identity()).encode(),
               APP + 'MeloNX-native-identity.json': json.dumps(dict(
                   sourceCoreIdentity=dict(host=MELONX_PIN['source'], sha256=MELONX_PIN['binaries']['ios-arm64']['sha256']),
                   compiledPayloadFingerprints=dict(MeloNXCore=MELONX_PIN['packagedFingerprint']))).encode(),
               APP + 'PlugIns/MeloNXJITHelper.appex/melonx-universal.js': SCRIPT,
               APP + COMPONENTS['dolphin']: fixtures.packaging_image({}, filetype=6, symbols={'_dolphin_fixture'}),
               APP + COMPONENTS['armsx2']: fixtures.packaging_image({}, filetype=6, symbols={'_armsx2_fixture'}),
               APP + COMPONENTS['rpcs3']: fixtures.packaging_image(
                   {}, filetype=6, symbols={'_' + name for name in RPCS3_PIN['exports']['added']})}
    for name in COMMON_EXTENSIONS:
        members[APP + f'PlugIns/{name}/Info.plist'] = bundle()
    return members


def changed(members, **updates):
    members = dict(members)
    for path, data in updates.items():
        if data is None:
            members.pop(path, None)
        else:
            members[path] = data
    return members


def with_helper(members, **versions):
    return changed(members, **{APP + HELPER: bundle(**versions)})


def with_identity(members, path=APP + distribution.S2ARM_IDENTITY, image=S2ARM_IMAGE):
    """The identity the pinned-engine embed step writes, and the engine images it packages."""
    record = {'component': 's2arm', 'pinSha256': sha(json.dumps(S2ARM_PIN).encode()),
              'packagedFingerprint': S2ARM_PIN['packagedFingerprint']}
    return changed(members, **{path: json.dumps(record).encode(), APP + S2ARM_ENGINE: image,
                               APP + 'Frameworks/NS2Pro.framework/NS2Pro': fixtures.packaging_image({}, filetype=6)})


def s2arm_delivery():
    return with_identity(with_helper(common_delivery()))


class FakeRepo:
    def __init__(self, manifest):
        self.files = {recipe.manifest_path(BUILD): json.dumps(manifest).encode(), manifest['recipient']['path']: RECIPIENT,
                      'pubspec.yaml': f'name: rewindbox\nversion: {VERSION}+{BUILD}\n'.encode(),
                      'build-utils/melonx/core-pin.json': json.dumps(MELONX_PIN).encode(),
                      'build-utils/rpcs3/core-pin.json': json.dumps(RPCS3_PIN).encode(),
                      S2ARM_PIN_PATH: json.dumps(S2ARM_PIN).encode()}

    def show(self, ref, path):
        assert ref == SOURCE, ref
        return self.files[path]

    def tree_of(self, ref):
        return 'e' * 40


def manifest(s2arm=False):
    value = dict(status='frozen', build=BUILD, recipient=dict(path=f'build-utils/delivery-{BUILD}-recipient.pem',
                                                             sha256=sha(RECIPIENT)),
                tests={group: dict(mode='fresh') for group in recipe.TEST_GROUPS},
                components=dict(dolphin=dict(image=COMPONENTS['dolphin']), armsx2=dict(image=COMPONENTS['armsx2']),
                                rpcs3=dict(image=COMPONENTS['rpcs3'], pin='build-utils/rpcs3/core-pin.json'),
                                melonx=dict(pin='build-utils/melonx/core-pin.json')),
                images=dict(replacedFingerprints={}), product=dict(restore={}))
    if s2arm:
        value['components']['s2arm'] = dict(S2ARM_COMPONENT)
    return value


def outcome(module, members, receipt=None, s2arm=False, entry=True):
    """verify() of `module` on one decrypted delivery holding these IPA members: the report bytes, or the refusal.
    `s2arm`: the manifest declares the s2arm pinned engine; `entry`: IDENTITY_ENGINES keeps the S2Arm entry."""
    if not entry:
        with mock.patch.dict(distribution.IDENTITY_ENGINES):
            del distribution.IDENTITY_ENGINES[distribution.S2ARM_IDENTITY]
            return outcome(module, members, receipt, s2arm)
    with tempfile.TemporaryDirectory(prefix='s2arm-downloaded-delivery-') as directory:
        root = Path(directory)
        ipa_name = f'RewindBox-Build{BUILD}-{SOURCE}-cold.ipa'
        staging = root / 'staging'
        staging.mkdir()
        with zipfile.ZipFile(staging / ipa_name, 'w') as archive:
            for path, data in members.items():
                entry = zipfile.ZipInfo(path, date_time=ENTRY_TIME)
                entry.external_attr = 0o600 << 16   # as writestr gives a file entry named by a string
                archive.writestr(entry, data)
        raw = (staging / ipa_name).read_bytes()
        images = {name: record['fingerprint'] for name, record in zip_payloads(staging / ipa_name).items()}
        signed = dict(ipaSha256=sha(raw), ipaBytes=len(raw), build=BUILD, images=images)
        validation = dict(result='passed', ipaSHA256=sha(raw), ipaBytes=len(raw), identity=receipt or identity())
        work, report = root / 'work', root / 'report.json'
        work.mkdir()
        value = manifest(s2arm)
        jobs = {name: dict(id=index + 1, conclusion='success') for index, name in enumerate(recipe.JOB_NAMES)}

        def decrypt(payload, envelope, key, target):
            delivery = target / 'delivery'
            delivery.mkdir()
            (delivery / ipa_name).write_bytes(raw)
            (delivery / 'SHA256SUMS').write_text(f'{sha(raw)}  {ipa_name}\n')
            (delivery / 'signed-payload-identity.json').write_text(json.dumps(signed))
            (delivery / 'standard-ipa-validation.json').write_text(json.dumps(validation))
            return delivery, sorted(path.name for path in delivery.iterdir()), True

        def effective_checkout(repo, manifest, source, target):
            script = target / 'packages/melonx_jit_helper/ios/Resources/melonx-universal.js'
            script.parent.mkdir(parents=True)
            script.write_bytes(SCRIPT)
            return target

        proxy = types.SimpleNamespace(
            Repo=lambda *arguments: FakeRepo(value), manifest_path=recipe.manifest_path, manifest_errors=lambda item: [],
            TEST_GROUPS=recipe.TEST_GROUPS, artifact_name=recipe.artifact_name, sha_file=recipe.sha_file,
            verify_base=lambda item, read: dict(images),
            check_images=lambda actual, base, item: dict(changedFromBase=[], undeclaredChanges=[], retainedVerified=len(actual)),
            APP_ROOT=recipe.APP_ROOT, IDENTITY=recipe.IDENTITY, engine_components=recipe.engine_components)
        replaced = dict(
            sd=proxy,
            api_binding=lambda api, build, repo: (dict(head_sha=SOURCE, id=4310, run_attempt=1, conclusion='success'), jobs,
                                                  {}, {'run-attempt.json': '0' * 64}),
            transport=lambda *arguments: (dict(schemaVersion=1), [dict(index=0)], b'payload', b'envelope'),
            recipient_matches=lambda public, private: 'f' * 64, decrypt=decrypt, effective_checkout=effective_checkout,
            run_validator=lambda name, arguments, cwd, logs: dict(name=name, exitCode=0, logSHA256='0' * 64))
        args = argparse.Namespace(build=BUILD, parts=root / 'parts', api=root / 'api', key=root / 'private.key', work=work,
                                  report=report)
        with mock.patch.multiple(module, **replaced):
            try:
                return 'report', json.dumps(module.verify(args), indent=1, sort_keys=True)
            except SystemExit as error:
                return 'refused', str(error)


def common_cases():
    common = common_delivery()
    first = APP + f'PlugIns/{COMMON_EXTENSIONS[0]}/Info.plist'
    return {
        'the application and its seven extensions': (common, 'report'),
        'one extension missing': (changed(common, **{first: None}), 'refused'),
        'one extension more': (changed(common, **{APP + 'PlugIns/Other.appex/Info.plist': bundle()}), 'refused'),
        'stray S2Arm helper without identity': (with_helper(common), 'refused'),
        'identity file outside the application root': (
            with_identity(with_helper(common), APP + 'Frameworks/' + distribution.S2ARM_IDENTITY), 'refused'),
        'wrong extension build': (changed(common, **{first: bundle(version='802')}), 'refused'),
        'wrong marketing version': (changed(common, **{first: bundle(marketing='0.0.7')}), 'refused'),
        'nested extension not counted': (changed(common, **{APP + 'PlugIns/Other.appex/PlugIns/Inner.appex/Info.plist':
                                                            bundle()}), 'report'),
        'packaged identity differs from the receipt': (changed(common, **{APP + recipe.IDENTITY: json.dumps(
            dict(identity(), schema=2)).encode()}), 'refused'),
    }


class WithoutTheIdentityFile(unittest.TestCase):
    def test_the_file_is_the_common_line_file(self):
        self.assertEqual(file_blob(), COMMON_BLOB)
        self.assertNotIn('S2ARM', (ROOT / PATH).read_text())
        self.assertIs(verifier.IDENTITY_ENGINES, distribution.IDENTITY_ENGINES)

    def test_same_report_or_refusal_as_without_the_s2arm_entry(self):
        for name, (members, kind) in common_cases().items():
            actual = outcome(verifier, members)
            self.assertEqual(actual[0], kind, name + ': ' + actual[1][:300])
            with self.subTest(case=name):
                self.assertEqual(actual, outcome(verifier, members, entry=False))
        self.assertEqual(outcome(verifier, common_cases()['one extension missing'][0]),
                         ('refused', 'VERIFICATION FAILED: Wrong bundle versions'))
        report = json.loads(outcome(verifier, common_delivery())[1])
        self.assertEqual((report['result'], report['binaryValidation']['bundleCount']), ('passed-offline-checks', 8))


class WithTheIdentityFile(unittest.TestCase):
    def test_the_s2arm_delivery_passes_with_its_eighth_extension(self):
        kind, text = outcome(verifier, s2arm_delivery(), s2arm=True)
        self.assertEqual(kind, 'report', text)
        validation = json.loads(text)['binaryValidation']
        self.assertEqual(validation['bundleCount'], 9)
        self.assertEqual(validation['versions'][HELPER], dict(CFBundleIdentifier='com.neogamelab.neostation',
                                                              CFBundleVersion=str(BUILD), CFBundleShortVersionString=VERSION,
                                                              MinimumOSVersion=None))
        self.assertEqual(outcome(verifier, s2arm_delivery(), s2arm=True, entry=False), (
            'refused', 'VERIFICATION FAILED: The packaged engine identities differ from the pinned engines of the manifest'))

    def test_the_count_the_helper_and_its_versions_are_required(self):
        missing = ('refused', 'VERIFICATION FAILED: Missing engine helper')
        wrong = ('refused', 'VERIFICATION FAILED: Wrong bundle versions')
        common = with_identity(common_delivery())
        cases = {
            'eight bundles, no S2Arm helper': (common, missing),
            'nine bundles, another extension instead of the helper': (changed(
                common, **{APP + 'PlugIns/Other.appex/Info.plist': bundle()}), missing),
            'ten bundles': (changed(s2arm_delivery(), **{APP + 'PlugIns/Other.appex/Info.plist': bundle()}), wrong),
            'the helper of another build': (with_identity(with_helper(common_delivery(), version='802')), wrong),
            'the helper of another version': (with_identity(with_helper(common_delivery(), marketing='0.0.7')), wrong),
        }
        for name, (members, refused) in cases.items():
            with self.subTest(case=name):
                self.assertEqual(outcome(verifier, members, s2arm=True), refused)

    def test_the_identity_is_the_pinned_engine_of_the_manifest(self):
        differ = ('refused', 'VERIFICATION FAILED: The packaged engine identities differ from the pinned engines of the '
                             'manifest')
        self.assertEqual(outcome(verifier, s2arm_delivery()), differ, 'an identity without the component')
        self.assertEqual(outcome(verifier, with_helper(common_delivery()), s2arm=True), differ,
                         'the component without the identity')
        other = fixtures.packaging_image({}, filetype=6, symbols={'_other'})
        self.assertEqual(outcome(verifier, with_identity(with_helper(common_delivery()), image=other), s2arm=True),
                         ('refused', 'VERIFICATION FAILED: The packaged s2arm engine is not its pinned payload'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
