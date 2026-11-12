#!/usr/bin/env python3
"""The S2Arm entry of ENGINE_HELPERS in the version check of .github/workflows/standard-delivery.yml, executed.

    python3 -B test/s2arm_version_check_test.py

The step "Verify final signed legal bundle and application and extension versions" counts the application and its
extensions in the signed IPA (the application, its seven extensions and the helper of each engine whose identity file
is packaged: session 03's design, Claude c0aae729) and checks their versions. Its Python (the PYVERSION here-document)
is taken from the workflow as the recipe's YAML parser reads it and run on synthetic IPAs the way the step runs it:
python3 reading it on stdin, in a directory holding pubspec.yaml, dist/<IPA_NAME>.ipa and build/delivery, with
BUILD_NUMBER and IPA_NAME set.
S2Arm adds one entry to the step's literal table. Without S2Arm-native-identity.json: same exit status, same assertion
and the same version-validation.json bytes as the common line's step (the workflow blob below, when this clone has it)
and as the current step without that entry (which must be that blob's program), on common IPAs (the eight bundles,
seven, nine, a stray S2Arm helper, an identity file elsewhere, wrong versions, two applications).
With it: the application and eight extensions, S2ArmJITHelper.appex among them, pass; eight bundles, or nine without that
helper, or ten, are refused; every bundle's versions are still checked.
"""
from __future__ import annotations

import ast
import json
import os
import plistlib
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for part in ('build-utils', '.github/diagnostics'):
    if str(ROOT / part) not in sys.path:
        sys.path.insert(0, str(ROOT / part))

import validate_single_ipa_distribution as distribution  # noqa: E402
import standard_delivery as recipe  # noqa: E402

WORKFLOW = '.github/workflows/standard-delivery.yml'
# The common workflow with the identity table, before the S2Arm entry (origin/Claude at b4ef45fc).
PRE_CHANGE_BLOB = '83a6da3d9915995eff1e8f78088e4f94da8f9525'
ENTRY = ", 'S2Arm-native-identity.json': ['S2ArmJITHelper.appex']"
STEP = 'Verify final signed legal bundle and application and extension versions'
OPEN, CLOSE = "python3 - <<'PYVERSION'\n", '\nPYVERSION\n'
APP = 'Payload/NeoStation.app/'
HELPER = 'PlugIns/S2ArmJITHelper.appex/Info.plist'
# The seven extensions of the common IPA: the closed set of the distribution validator and MeloNX's two.
COMMON_EXTENSIONS = sorted(distribution.EXPECTED_EXTENSIONS) + ['MeloNXJITHelper.appex', 'MeloNXRamDonor.appex']
BUILD, VERSION = '803', '0.0.8'
SEVEN = 'AssertionError: Expected the application, its seven extensions and []'
EIGHT = "AssertionError: Expected the application, its seven extensions and ['S2ArmJITHelper.appex']"
MISSING = 'AssertionError: Missing engine helper S2ArmJITHelper.appex'


def step_script(text):
    """The Python of the version check, as the step hands it to python3."""
    steps = recipe.load_yaml_subset(text)['jobs']['application']['steps']
    run = next(step for step in steps if step['name'] == STEP)['run']
    start = run.index(OPEN) + len(OPEN)
    return run[start:run.index(CLOSE, start)] + '\n'


def pre_change_text():
    result = subprocess.run(['git', 'cat-file', 'blob', PRE_CHANGE_BLOB], cwd=ROOT, capture_output=True)
    return result.stdout.decode() if result.returncode == 0 else None


def stripped_script(script):
    """The step without the S2Arm entry of its ENGINE_HELPERS table."""
    if script.count(ENTRY) != 1:
        raise AssertionError('the step does not carry the S2Arm entry exactly once')
    return script.replace(ENTRY, '')


def bundle(version=BUILD, marketing=VERSION, identifier='com.neogamelab.neostation'):
    return plistlib.dumps({'CFBundleIdentifier': identifier, 'CFBundleVersion': version,
                           'CFBundleShortVersionString': marketing})


def common_ipa():
    members = {APP + 'Info.plist': bundle(), APP + 'Runner': b'\xcf\xfa\xed\xfe fixture'}
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


def s2arm_ipa():
    return with_identity(with_helper(common_ipa()))


def run_step(script, members):
    """(exit status, the exception line, version-validation.json bytes or None) of the step's Python on one IPA."""
    with tempfile.TemporaryDirectory(prefix='s2arm-version-check-') as directory:
        root = Path(directory)
        (root / 'pubspec.yaml').write_text(f'name: rewindbox\nversion: {VERSION}+{BUILD}\n')
        (root / 'dist').mkdir()
        (root / 'build/delivery').mkdir(parents=True)
        with zipfile.ZipFile(root / 'dist/NeoStation.ipa', 'w') as archive:
            for path, data in members.items():
                archive.writestr(path, data)
        environment = dict(PATH=os.environ.get('PATH', '/usr/bin:/bin'), BUILD_NUMBER=BUILD, IPA_NAME='NeoStation')
        process = subprocess.run([sys.executable, '-I', '-'], input=script.encode(), cwd=root, env=environment,
                                 capture_output=True, timeout=120)
        lines = process.stderr.decode().strip().splitlines()
        report = root / 'build/delivery/version-validation.json'
        return process.returncode, lines[-1] if lines else '', report.read_bytes() if report.is_file() else None


def common_cases():
    common = common_ipa()
    first = APP + f'PlugIns/{COMMON_EXTENSIONS[0]}/Info.plist'
    second_app = changed(common, **{'Payload/Other.app/Info.plist': bundle()})
    return {
        'the application and its seven extensions': (common, 0, ''),
        'one extension missing': (changed(common, **{first: None}), 1, SEVEN),
        'one extension more': (changed(common, **{APP + 'PlugIns/Other.appex/Info.plist': bundle()}), 1, SEVEN),
        'stray S2Arm helper without identity': (with_helper(common), 1, SEVEN),
        'identity file outside the application root': (
            with_identity(with_helper(common), APP + 'Frameworks/' + distribution.S2ARM_IDENTITY), 1, SEVEN),
        'wrong extension build': (changed(common, **{first: bundle(version='802')}), 1, 'AssertionError: ' + first),
        'wrong marketing version': (changed(common, **{first: bundle(marketing='0.0.7')}), 1, 'AssertionError: ' + first),
        'two applications': (second_app, 1, 'AssertionError'),
    }


class WithoutTheIdentityFile(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = step_script((ROOT / WORKFLOW).read_text())
        text = pre_change_text()
        cls.common_script = step_script(text) if text is not None else None

    def test_the_change_is_one_table_entry(self):
        if self.common_script is None:
            self.skipTest('the common line blob is not in this clone')
        self.assertEqual(ast.dump(ast.parse(stripped_script(self.script))), ast.dump(ast.parse(self.common_script)))
        self.assertIn('assert len(bundles) == 8 + len(helpers)', self.script)

    def test_same_outcome_as_the_common_line_step(self):
        references = {'stripped': stripped_script(self.script)}
        if self.common_script is not None:
            references['common line blob'] = self.common_script
        for name, (members, status, line) in common_cases().items():
            actual = run_step(self.script, members)
            self.assertEqual(actual[:2], (status, line), name)
            self.assertEqual(actual[2] is not None, status == 0, name)
            for label, reference in references.items():
                with self.subTest(case=name, reference=label):
                    self.assertEqual(actual, run_step(reference, members))
        report = json.loads(run_step(self.script, common_ipa())[2])
        self.assertEqual((report['result'], report['build'], report['version'], len(report['bundles'])),
                         ('passed', int(BUILD), VERSION, 8))
        self.assertEqual(len(references), 1 + (self.common_script is not None))

    def test_the_seven_extensions_are_the_common_set(self):
        self.assertEqual(len(COMMON_EXTENSIONS), 7)
        self.assertNotIn('S2ArmJITHelper.appex', COMMON_EXTENSIONS)
        self.assertEqual(set(distribution.S2ARM_EXTENSIONS), {'S2ArmJITHelper.appex'})
        self.assertEqual(HELPER, 'PlugIns/' + next(iter(distribution.S2ARM_EXTENSIONS)) + '/Info.plist')


class WithTheIdentityFile(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = step_script((ROOT / WORKFLOW).read_text())
        text = pre_change_text()
        cls.common_script = step_script(text) if text is not None else None

    def test_the_s2arm_ipa_passes_with_its_eighth_extension(self):
        status, line, raw = run_step(self.script, s2arm_ipa())
        self.assertEqual((status, line), (0, ''))
        report = json.loads(raw)
        self.assertEqual(len(report['bundles']), 9)
        self.assertIn(APP + HELPER, report['bundles'])
        self.assertEqual(run_step(stripped_script(self.script), s2arm_ipa())[:2], (1, SEVEN))
        if self.common_script is not None:
            self.assertEqual(run_step(self.common_script, s2arm_ipa())[:2], (1, SEVEN))

    def test_the_count_and_the_helper_are_required(self):
        common = with_identity(common_ipa())
        cases = {
            'eight bundles, no S2Arm helper': (common, MISSING),
            'nine bundles, another extension instead of the helper': (changed(
                common, **{APP + 'PlugIns/Other.appex/Info.plist': bundle()}), MISSING),
            'ten bundles, the helper and another extension': (changed(
                s2arm_ipa(), **{APP + 'PlugIns/Other.appex/Info.plist': bundle()}), EIGHT),
            'the helper without one common extension': (changed(
                s2arm_ipa(), **{APP + f'PlugIns/{COMMON_EXTENSIONS[-1]}/Info.plist': None}), EIGHT),
        }
        for name, (members, line) in cases.items():
            with self.subTest(case=name):
                self.assertEqual(run_step(self.script, members), (1, line, None))

    def test_the_versions_of_the_helper_are_checked(self):
        for versions in (dict(version='802'), dict(marketing='0.0.7')):
            with self.subTest(versions=versions):
                members = with_identity(with_helper(common_ipa(), **versions))
                self.assertEqual(run_step(self.script, members), (1, 'AssertionError: ' + APP + HELPER, None))


if __name__ == '__main__':
    unittest.main(verbosity=2)
