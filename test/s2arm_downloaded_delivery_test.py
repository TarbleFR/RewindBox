#!/usr/bin/env python3
"""The S2Arm conditional of build-utils/verify_downloaded_delivery.py, run through verify() on synthetic deliveries.

    python3 -B test/s2arm_downloaded_delivery_test.py

The offline verifier of a downloaded delivery counts the application and its extensions (a closed count: eight
bundles) before it checks their versions. verify() runs here end to end on a synthetic decrypted delivery, with only
what needs the network, the private key, openssl, a git history or a macOS runner replaced (the saved API binding,
the transport parts, the key match, the decryption, the base and image checks of the recipe, the effective checkout,
the six offline validators): every check of the IPA itself runs.
Without S2Arm-native-identity.json: the same report bytes, or the same refusal, as the common line's verifier (git blob
below, when this clone has it) and as the current file with its S2Arm statements removed from the syntax tree (the
import and the branch, replaced by its else statement, which must be that blob's program), on common deliveries (eight
bundles, seven, nine, a stray S2Arm helper, an identity file elsewhere, wrong versions, a changed packaged identity).
With it: nine bundles with S2ArmJITHelper.appex pass (reported with their versions); eight, or nine without the helper,
and a helper of another build are refused.
"""
from __future__ import annotations

import argparse
import ast
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

PATH = 'build-utils/verify_downloaded_delivery.py'
# The verifier of the common line before the S2Arm statements (origin/Claude at 41c76404; same blob on this branch's
# base ba04c914).
PRE_CHANGE_BLOB = '292a92ad329c5b5e206f91c8b42c603741afd794'
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
# One date for every IPA entry: the report holds the IPA's SHA-256, so two builds of the same members must give the
# same bytes (ZipFile.writestr would date each entry with the clock, two seconds per step).
ENTRY_TIME = (2026, 11, 11, 0, 0, 0)


def sha(data):
    return hashlib.sha256(data).hexdigest()


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
    """The verifier's syntax tree without its S2Arm import, and with its S2Arm branch replaced by the else statement."""
    tree = ast.parse((ROOT / PATH).read_text())
    imports = [node for node in tree.body if isinstance(node, ast.ImportFrom) and
               all(alias.name.startswith('S2ARM_') for alias in node.names)]
    tree.body = [node for node in tree.body if node not in imports]
    replaced = 0
    for holder in ast.walk(tree):
        body = getattr(holder, 'body', None)
        if not isinstance(body, list):
            continue
        new = []
        for node in body:
            if isinstance(node, ast.If) and is_s2arm(node.test):
                new += node.orelse
                replaced += 1
            else:
                new.append(node)
        holder.body = new
    if len(imports) != 1 or replaced != 1 or is_s2arm(tree):
        raise AssertionError(f'unexpected S2Arm statements: {len(imports)} imports, {replaced} branches')
    return tree


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


def with_identity(members, path=APP + distribution.S2ARM_IDENTITY):
    return changed(members, **{path: json.dumps({'schema': 1, 'engine': 'S2Arm'}).encode()})


def s2arm_delivery():
    return with_identity(with_helper(common_delivery()))


class FakeRepo:
    def __init__(self, manifest):
        self.files = {recipe.manifest_path(BUILD): json.dumps(manifest).encode(), manifest['recipient']['path']: RECIPIENT,
                      'pubspec.yaml': f'name: rewindbox\nversion: {VERSION}+{BUILD}\n'.encode(),
                      'build-utils/melonx/core-pin.json': json.dumps(MELONX_PIN).encode(),
                      'build-utils/rpcs3/core-pin.json': json.dumps(RPCS3_PIN).encode()}

    def show(self, ref, path):
        assert ref == SOURCE, ref
        return self.files[path]

    def tree_of(self, ref):
        return 'e' * 40


def manifest():
    return dict(status='frozen', build=BUILD, recipient=dict(path=f'build-utils/delivery-{BUILD}-recipient.pem',
                                                             sha256=sha(RECIPIENT)),
                tests={group: dict(mode='fresh') for group in recipe.TEST_GROUPS},
                components=dict(dolphin=dict(image=COMPONENTS['dolphin']), armsx2=dict(image=COMPONENTS['armsx2']),
                                rpcs3=dict(image=COMPONENTS['rpcs3'], pin='build-utils/rpcs3/core-pin.json'),
                                melonx=dict(pin='build-utils/melonx/core-pin.json')),
                images=dict(replacedFingerprints={}), product=dict(restore={}))


def outcome(module, members, receipt=None):
    """verify() of `module` on one decrypted delivery holding these IPA members: the report bytes, or the refusal."""
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
        value = manifest()
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
            APP_ROOT=recipe.APP_ROOT, IDENTITY=recipe.IDENTITY)
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
    def test_the_change_is_one_import_and_one_branch_whose_else_is_the_common_statement(self):
        source = pre_change_source()
        if source is None:
            self.skipTest('the common line blob is not in this clone')
        self.assertEqual(ast.dump(stripped_tree()), ast.dump(ast.parse(source)))

    def test_same_report_or_refusal_as_the_common_line_verifier(self):
        references = {'stripped': module_from(stripped_tree(), 'verify_downloaded_delivery_stripped')}
        source = pre_change_source()
        if source is not None:
            references['common line blob'] = module_from(source, 'verify_downloaded_delivery_common')
        for name, (members, kind) in common_cases().items():
            actual = outcome(verifier, members)
            self.assertEqual(actual[0], kind, name + ': ' + actual[1][:300])
            for label, reference in references.items():
                with self.subTest(case=name, reference=label):
                    self.assertEqual(actual, outcome(reference, members))
        self.assertEqual(outcome(verifier, common_cases()['one extension missing'][0]),
                         ('refused', 'VERIFICATION FAILED: Wrong bundle versions'))
        report = json.loads(outcome(verifier, common_delivery())[1])
        self.assertEqual((report['result'], report['binaryValidation']['bundleCount']), ('passed-offline-checks', 8))
        self.assertEqual(len(references), 1 + (source is not None))


class WithTheIdentityFile(unittest.TestCase):
    def test_the_s2arm_delivery_passes_with_its_eighth_extension(self):
        kind, text = outcome(verifier, s2arm_delivery())
        self.assertEqual(kind, 'report', text)
        validation = json.loads(text)['binaryValidation']
        self.assertEqual(validation['bundleCount'], 9)
        self.assertEqual(validation['versions'][HELPER], dict(CFBundleIdentifier='com.neogamelab.neostation',
                                                              CFBundleVersion=str(BUILD), CFBundleShortVersionString=VERSION,
                                                              MinimumOSVersion=None))
        refused = ('refused', 'VERIFICATION FAILED: Wrong bundle versions')
        self.assertEqual(outcome(module_from(stripped_tree(), 'verify_downloaded_delivery_stripped'), s2arm_delivery()),
                         refused)
        source = pre_change_source()
        if source is not None:
            self.assertEqual(outcome(module_from(source, 'verify_downloaded_delivery_common'), s2arm_delivery()), refused)

    def test_the_count_the_helper_and_its_versions_are_required(self):
        refused = ('refused', 'VERIFICATION FAILED: Wrong bundle versions (S2Arm identity: the application and its eight '
                              'extensions, S2ArmJITHelper.appex included)')
        common = with_identity(common_delivery())
        cases = {
            'eight bundles, no S2Arm helper': common,
            'nine bundles, another extension instead of the helper': changed(
                common, **{APP + 'PlugIns/Other.appex/Info.plist': bundle()}),
            'ten bundles': changed(s2arm_delivery(), **{APP + 'PlugIns/Other.appex/Info.plist': bundle()}),
            'the helper of another build': with_identity(with_helper(common_delivery(), version='802')),
            'the helper of another version': with_identity(with_helper(common_delivery(), marketing='0.0.7')),
        }
        for name, members in cases.items():
            with self.subTest(case=name):
                self.assertEqual(outcome(verifier, members), refused)


if __name__ == '__main__':
    unittest.main(verbosity=2)
