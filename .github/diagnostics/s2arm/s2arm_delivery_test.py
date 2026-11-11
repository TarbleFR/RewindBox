#!/usr/bin/env python3
"""Offline tests of the Switch 2 (S2Arm) test IPA delivery line (plain python3; no network, no build).

    python3 -B .github/diagnostics/s2arm/s2arm_delivery_test.py

What they cover: the launcher redirects exactly the reviewed line constants of the unchanged standard
recipe and refuses a recipe it was not reviewed for; the base stays authenticated on the line that
delivered it; the generated workflow is the committed one, triggers only on this branch and tag, keeps
every common step and uploads only through the protected action; the Info.plist key is set once, in
order, and the built application is checked; the draft manifests are accepted by the recipe's own checker.
Not covered here (needs the reshaped history, the network or a macOS build): freeze, the API-backed
contract checks, the run itself.
"""
from __future__ import annotations

import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import plistlib
import re
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
for _part in (HERE, ROOT / 'build-utils/s2arm', ROOT / '.github/ipa-protection'):
    if str(_part) not in sys.path:
        sys.path.insert(0, str(_part))

import standard_delivery_s2arm as line  # noqa: E402
import make_manifest  # noqa: E402
import make_workflow  # noqa: E402
import set_probe_key as probe  # noqa: E402
import check_workflows  # noqa: E402

RECIPE = ROOT / line.RECIPE
# The recipe file the launcher inventory was reviewed against (commit 687ea833). A different file is not an
# error of the recipe: it asks for a review of RECIPE_INVENTORY and HANDLING, then for this value.
REVIEWED_RECIPE_SHA256 = '6508c07d769b8253d026492aef9e6eef3e9b1adc66c4bdf50221646bc14a1799'
MODEL = 724   # stand-in model of the common line until 725 is delivered
REDIRECTED = {'BRANCH', 'WORKFLOW', 'TRIGGER', 'TRIGGER_MARKER', 'subject_build', 'trigger_paths', 'verify_base',
              'authenticate_base'}
FAKE_PEM = b'-----BEGIN PUBLIC KEY-----\nnot a key: bytes of a test\n-----END PUBLIC KEY-----\n'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def private_recipe():
    """A second, unconfigured import of the recipe file (the shared module stays as other tests left it)."""
    spec = importlib.util.spec_from_file_location('standard_delivery_private_copy', RECIPE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def manifest(build=MODEL):
    return json.loads((ROOT / f'build-utils/delivery/{build}.json').read_bytes())


class Launcher(unittest.TestCase):
    def test_the_recipe_file_is_untouched_and_is_the_reviewed_one(self):
        before = sha(RECIPE.read_bytes())
        sd = private_recipe()
        line.configure(sd)
        line.configure()
        make_manifest.draft(line.configure(), 'successor', MODEL, 801)
        self.assertEqual(sha(RECIPE.read_bytes()), before)
        tracked = subprocess.run(['git', 'status', '--porcelain', '--', line.RECIPE, line.COMMON_WORKFLOW, line.VERIFIER,
                                  'test/standard_delivery_contract_test.py', 'build-utils/delivery', 'pubspec.lock'],
                                 cwd=ROOT, capture_output=True, text=True, check=True).stdout
        self.assertEqual(tracked, '', 'a file of the common recipe is modified in this checkout')
        self.assertEqual(before, REVIEWED_RECIPE_SHA256, 'the standard recipe changed: review the launcher inventory '
                         '(standard_delivery_s2arm.py inventory), then record the new file here')

    def test_exactly_the_listed_names_are_redirected(self):
        sd = private_recipe()
        before = dict(vars(sd))
        defaults = sd.jobs_that_run.__defaults__
        self.assertEqual((sd.BRANCH, sd.WORKFLOW, sd.MANIFESTS, sd.TRIGGER_MARKER, defaults),
                         ('Claude', '.github/workflows/standard-delivery.yml', 'build-utils/delivery', '[ipa-delivery:',
                          ('Claude',)))
        self.assertIs(line.configure(sd), sd)
        after = dict(vars(sd))
        changed = {name for name in before if after[name] is not before[name]}
        self.assertEqual(changed, REDIRECTED)
        self.assertEqual(set(after) - set(before), {'S2ARM_LINE'})
        self.assertEqual((sd.BRANCH, sd.WORKFLOW, sd.TRIGGER_MARKER, sd.TRIGGER.pattern),
                         (line.DELIVERY_BRANCH, line.WORKFLOW, '[s2arm-delivery:', r'\[s2arm-delivery:(\d{3,4})\]'))
        self.assertEqual(sd.jobs_that_run.__defaults__, (line.DELIVERY_BRANCH,))
        # Kept: the manifest directory, the recipe/product partition and its digest, jobs and required steps.
        for name in ('MANIFESTS', 'RECIPE_PREFIXES', 'RECIPE_FILES', 'RECIPE_GLOBS', 'RECIPE_DEFINITION', 'JOB_NAMES',
                     'REQUIRED_STEPS', 'CONTRACT_TEST', 'REPOSITORY', 'EMBEDDED_RECIPE_FILES', 'TEST_GROUPS'):
            self.assertIs(after[name], before[name], name)
        self.assertEqual(sd.recipe_definition_sha(), manifest()['product']['recipeDefinitionSHA256'])
        self.assertEqual(sd.manifest_path(801), 'build-utils/delivery/801.json')
        line.configure(sd)   # idempotent
        self.assertEqual({name for name in before if vars(sd)[name] is not before[name]}, REDIRECTED)

    def test_every_recipe_use_of_a_line_constant_is_reviewed_and_handled(self):
        actual = line.inventory(RECIPE.read_text())
        self.assertEqual(actual, line.RECIPE_INVENTORY)
        self.assertEqual(set(line.HANDLING), set(line.RECIPE_INVENTORY))
        self.assertEqual(line.inventory((ROOT / line.VERIFIER).read_text(), prefix='sd'), line.VERIFIER_INVENTORY)
        # Every function that reads BRANCH is either redirected as a whole or declared delivery side.
        for name, uses in line.RECIPE_INVENTORY.items():
            if 'BRANCH' in uses and name != '<module>':
                self.assertRegex(line.HANDLING[name], r'^(delivery|producer) side', name)

    def test_a_recipe_that_drifted_is_refused(self):
        source = RECIPE.read_text()
        drifted = source + "\n\ndef new_check(run):\n    return run['head_branch'] == BRANCH\n"
        self.assertEqual(line.inventory_drift(line.inventory(drifted), line.RECIPE_INVENTORY),
                         ["new_check: reviewed None, now ['BRANCH']"])
        moved = source.replace("run['path'] == WORKFLOW and run['run_attempt'] == pin['attempt']",
                               "run['path'] == COMMON and run['run_attempt'] == pin['attempt']")
        self.assertNotEqual(moved, source)
        self.assertTrue(line.inventory_drift(line.inventory(moved), line.RECIPE_INVENTORY))
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / line.RECIPE
            target.parent.mkdir(parents=True)
            target.write_text(drifted)
            with self.assertRaisesRegex(line.LineError, 'review the launcher'):
                line.check_recipe_inventory(temporary)
        with mock.patch.dict(line.RECIPE_INVENTORY, {'freeze': ['WORKFLOW']}):
            with self.assertRaises(line.LineError):
                line.configure(private_recipe())

    def test_request_tag(self):
        self.assertEqual(line.subject_build('[s2arm-delivery:801] build(s2arm): request'), 801)
        self.assertEqual(line.subject_build('[s2arm-delivery:1024] x'), 1024)
        self.assertIsNone(line.subject_build('[ipa-delivery:801] build(delivery): request'))
        self.assertIsNone(line.subject_build('docs: nothing requested'))
        for subject in ('build: request [s2arm-delivery:801]', '[s2arm-delivery:801] [s2arm-delivery:802]',
                        '[s2arm-delivery:725] a build of the shared sequence', '[s2arm-delivery:800] x'):
            with self.assertRaises(line.LineError, msg=subject):
                line.subject_build(subject)
        sd = line.configure(private_recipe())
        self.assertIs(sd.subject_build, line.subject_build)
        common = private_recipe()
        self.assertEqual(common.subject_build('[ipa-delivery:724] x'), 724)
        self.assertIsNone(common.subject_build('[s2arm-delivery:801] x'))

    def test_the_base_is_authenticated_on_the_line_that_delivered_it(self):
        sd = line.configure(private_recipe())
        value = manifest()
        self.assertEqual(value['base']['workflow'], line.COMMON_WORKFLOW)
        self.assertEqual(line.base_branch(value), 'Claude')
        images = sd.verify_base(value)
        self.assertEqual(len(images), value['base']['identity']['images'])
        self.assertEqual(sd.BRANCH, line.DELIVERY_BRANCH, 'the delivery branch is restored after the base check')
        # The recipe's own condition still decides: without the redirection a common base is refused on this line.
        with self.assertRaisesRegex(ValueError, 'base receipt differs'):
            sd.verify_base.__wrapped__(value)
        broken = copy.deepcopy(value)
        broken['base']['receipt']['sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            sd.verify_base(broken)
        self.assertEqual(sd.BRANCH, line.DELIVERY_BRANCH)
        unknown = copy.deepcopy(value)
        unknown['base']['workflow'] = '.github/workflows/other.yml'
        with self.assertRaisesRegex(line.LineError, 'unknown workflow'):
            sd.verify_base(unknown)
        own = copy.deepcopy(value)
        own['base']['workflow'] = line.WORKFLOW
        self.assertEqual(line.base_branch(own), line.DELIVERY_BRANCH)
        with self.assertRaisesRegex(ValueError, 'base receipt differs'):
            sd.verify_base(own)   # the committed receipt says Claude: a base of this line must say this branch

    def test_the_base_run_is_authenticated_through_the_api_on_its_own_branch(self):
        sd = line.configure(private_recipe())
        value = manifest()
        base = value['base']

        def api(branch):
            def get(endpoint):
                if endpoint.startswith('actions/runs/'):
                    return dict(id=base['run'], head_sha=base['source'], conclusion='success', run_attempt=base['attempt'],
                                head_branch=branch, path=base['workflow'])
                job = next(job for job in base['jobs'].values() if endpoint == 'actions/jobs/' + str(job['id']))
                return dict(id=job['id'], name=job['name'], run_id=base['run'], head_sha=base['source'],
                            run_attempt=base['attempt'], conclusion='success')
            return get
        self.assertEqual(sd.authenticate_base(value, api('Claude'))['result'], 'authenticated')
        with self.assertRaisesRegex(ValueError, 'Wrong delivered base run'):
            sd.authenticate_base(value, api(line.DELIVERY_BRANCH))
        self.assertEqual(sd.BRANCH, line.DELIVERY_BRANCH)

    def test_request_guard(self):
        sd = line.configure(private_recipe())

        class Repo:
            def __init__(self, subject):
                self.value = subject

            def commit(self, ref):
                return 'a' * 40

            def subject(self, ref):
                return self.value
        environment = dict(GITHUB_REF_NAME=line.DELIVERY_BRANCH, GITHUB_REF='refs/heads/' + line.DELIVERY_BRANCH,
                           GITHUB_EVENT_NAME='push', GITHUB_SHA='a' * 40)
        tagged = Repo('[s2arm-delivery:801] build(s2arm): request')
        self.assertEqual(line.request_guard(sd, environment, tagged)['build'], 801)
        manual = dict(environment, GITHUB_EVENT_NAME='workflow_dispatch', REQUESTED_BUILD='801')
        self.assertEqual(line.request_guard(sd, manual, tagged)['event'], 'workflow_dispatch')
        refused = (
            (dict(environment, GITHUB_REF_NAME='Claude', GITHUB_REF='refs/heads/Claude'), tagged),
            (dict(environment, GITHUB_SHA='b' * 40), tagged),
            (dict(environment, GITHUB_EVENT_NAME='pull_request'), tagged),
            (environment, Repo('[ipa-delivery:801] build(delivery): request')),
            (environment, Repo('[s2arm-delivery:724] x')),
            (dict(manual, REQUESTED_BUILD='802'), tagged),
            (dict(manual, REQUESTED_BUILD=''), tagged),
        )
        for case, repo in refused:
            with self.assertRaises(line.LineError, msg=case):
                line.request_guard(sd, case, repo)

    def test_recipient_guard(self):
        sd = line.configure(private_recipe())
        expected = 'build-utils/delivery-801-recipient.pem'
        self.assertEqual(line.recipient_path(801), expected)
        self.assertTrue(sd.is_recipe(expected), 'the recipient key is a recipe path (never a product file)')
        value = dict(build=801, recipient=dict(path=expected, sha256=sha(FAKE_PEM)))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'build-utils').mkdir()
            with mock.patch.object(sd, 'ROOT', root):
                environment = {'DELIVERY_RECIPIENT': expected}
                with self.assertRaisesRegex(line.LineError, 'not committed'):
                    line.recipient_guard(sd, environment, value)
                (root / expected).write_bytes(FAKE_PEM)
                self.assertEqual(line.recipient_guard(sd, environment, value)['sha256'], sha(FAKE_PEM))
                for case in ({}, {'DELIVERY_RECIPIENT': ''}, {'DELIVERY_RECIPIENT': 'build-utils/delivery-422-recipient.pem'}):
                    with self.assertRaises(line.LineError, msg=case):
                        line.recipient_guard(sd, case, value)
                other = dict(value, recipient=dict(path='build-utils/delivery-724-recipient.pem', sha256=sha(FAKE_PEM)))
                with self.assertRaises(line.LineError):
                    line.recipient_guard(sd, {'DELIVERY_RECIPIENT': other['recipient']['path']}, other)
                with self.assertRaises(ValueError):   # the recipe's own check: the key is not the manifest's
                    line.recipient_guard(sd, environment, dict(value, recipient=dict(path=expected, sha256='0' * 64)))
                (root / 'build-utils/delivery-724-recipient.pem').write_bytes(FAKE_PEM)
                with self.assertRaisesRegex(line.LineError, 'key of an earlier delivery'):
                    line.recipient_guard(sd, environment, value)

    def test_the_verifier_runs_on_the_configured_recipe(self):
        import verify_downloaded_delivery_s2arm as launcher
        verifier = launcher.load_verifier()
        self.assertIs(verifier.sd, line.configure())
        self.assertEqual((verifier.sd.BRANCH, verifier.sd.WORKFLOW), (line.DELIVERY_BRANCH, line.WORKFLOW))
        self.assertIs(verifier.sd.subject_build, line.subject_build)
        self.assertTrue(hasattr(verifier.sd.verify_base, '__wrapped__'))


class Workflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sd = line.configure()
        cls.common_text = (ROOT / line.COMMON_WORKFLOW).read_text()
        cls.text = (ROOT / line.WORKFLOW).read_text()
        cls.spec = cls.sd.load_yaml_subset(cls.text)
        cls.common = cls.sd.load_yaml_subset(cls.common_text)

    def test_the_committed_workflow_is_the_generated_one(self):
        self.assertEqual(make_workflow.generate(self.common_text), self.text)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(make_workflow.main(['--check']), 0)

    def test_the_parser_of_the_recipe_agrees_with_pyyaml(self):
        try:
            import yaml
        except ImportError:
            self.skipTest('PyYAML is not installed')
        self.assertEqual(yaml.safe_load(self.text), self.spec)

    def test_trigger_only_on_this_branch_and_tag(self):
        trigger = self.spec['on']
        self.assertEqual(set(trigger), {'push', 'workflow_dispatch'})
        self.assertEqual(trigger['push'], {'branches': [line.DELIVERY_BRANCH]})
        self.assertEqual(trigger['workflow_dispatch'], {'inputs': {'build': {
            'description': trigger['workflow_dispatch']['inputs']['build']['description'], 'required': True,
            'type': 'string'}}})
        push = self.sd.push_filter(self.spec)
        self.assertTrue(self.sd.push_triggers(push, line.DELIVERY_BRANCH, ['build-utils/delivery/801.json']))
        for branch in ('Claude', 'main', 'work/s2arm-switch2-prototype-20261110-x', 'work/other'):
            self.assertFalse(self.sd.push_triggers(push, branch, ['build-utils/delivery/801.json']), branch)
        gate = self.sd.strip_expression(self.spec['jobs']['preflight']['if'])
        status = dict(success=True, failure=False, cancelled=False, always=True)

        def runs(ref, event, message):
            head = dict(head_commit=dict(message=message)) if message is not None else {}
            context = dict(github=dict(ref=ref, event_name=event, event=head), inputs={}, needs={})
            return self.sd.truthy(self.sd.evaluate(gate, context, status))
        ours = 'refs/heads/' + line.DELIVERY_BRANCH
        self.assertTrue(runs(ours, 'push', '[s2arm-delivery:801] build(s2arm): request'))
        self.assertTrue(runs(ours, 'workflow_dispatch', None))
        self.assertFalse(runs(ours, 'push', '[ipa-delivery:801] build(delivery): request'))
        self.assertFalse(runs(ours, 'push', 'build(s2arm): request [s2arm-delivery:801]'))
        self.assertFalse(runs(ours, 'push', 'docs: nothing'))
        self.assertFalse(runs('refs/heads/Claude', 'push', '[s2arm-delivery:801] x'))
        self.assertFalse(runs('refs/heads/Claude', 'workflow_dispatch', None))
        for name, job in self.spec['jobs'].items():
            if name != 'preflight':
                self.assertEqual(job['needs'], 'preflight', name)
                self.assertIn("needs.preflight.outputs.build != ''", job['if'], name)
        running, unevaluated = self.sd.jobs_that_run(self.spec, 'docs: no tag')
        self.assertEqual((running, unevaluated), ([], []))
        running, _ = self.sd.jobs_that_run(self.spec, '[ipa-delivery:801] x')
        self.assertEqual(running, [])
        running, _ = self.sd.jobs_that_run(self.spec, '[s2arm-delivery:801] x')
        self.assertIn('preflight', running)
        # The common workflow is not started by this line's tag or branch, and conversely.
        common_push = self.sd.push_filter(self.common)
        self.assertFalse(self.sd.push_triggers(common_push, line.DELIVERY_BRANCH, ['build-utils/delivery/801.json']))

    def test_same_jobs_and_steps_with_only_the_declared_differences(self):
        report = make_workflow.explain(self.common_text, self.text, self.sd.load_yaml_subset)
        self.assertEqual(report['jobs'], ['preflight', 'flutter', 'native', 'republish', 'application'])
        self.assertEqual(report['insertedSteps'], {
            'preflight': ['Check that this run requests a build of the Switch 2 test line',
                          'Check the committed recipient public key of this build'],
            'flutter': [], 'native': [], 'republish': [],
            'application': ['Check the committed recipient public key of this build',
                            'Turn the S2Arm device probe on in the generated host',
                            'Check the S2Arm probe key and code in the compiled application',
                            'Check the S2Arm probe key and code in the signed IPA']})
        for job, steps in self.sd.REQUIRED_STEPS.items():
            self.assertLessEqual(steps, {step['name'] for step in self.spec['jobs'][job]['steps']}, job)
        self.assertEqual(tuple(self.spec['jobs']), self.sd.JOB_NAMES[:1] + ('flutter', 'native', 'republish', 'application'))
        for job in self.spec['jobs'].values():
            names = [step['name'] for step in job['steps']]
            self.assertEqual(names[:2], ['Checkout the exact candidate and its history', self.sd.MATERIALIZE_STEP])
            self.assertEqual(sum(step.get('uses', '').startswith('actions/checkout@') for step in job['steps']), 1)

    def test_every_recipe_call_goes_through_the_launcher(self):
        calls = re.findall(r'python3 -B (\S+) (\S+)', self.text)
        recipe_calls = [script for script, _ in calls if 'standard_delivery' in script]
        self.assertEqual(set(recipe_calls), {'.github/diagnostics/s2arm/standard_delivery_s2arm.py'})
        self.assertEqual(len(recipe_calls), self.common_text.count('.github/diagnostics/standard_delivery.py') + 3)
        self.assertNotIn('diagnostics/standard_delivery.py', self.text)
        operations = {operation for script, operation in calls if 'standard_delivery' in script}
        self.assertLessEqual(operations, set(self.sd.OPERATIONS) | set(line.LINE_OPERATIONS))
        self.assertLessEqual({'request-guard', 'recipient-guard'}, operations)

    def test_validators_encryption_and_split_are_the_common_ones(self):
        def lines(text, *needles):
            return [item.strip() for item in text.splitlines() if any(needle in item for needle in needles)]
        needles = ('delivery_cipher.py', 'split_encrypted_delivery.py', 'build-utils/validate_', 'retention-days',
                   'compression-level', 'if-no-files-found', 'shasum', 'DELIVERY_RECIPIENT', 'embed_legal_bundle.py')
        generated, common = lines(self.text, *needles), lines(self.common_text, *needles)
        # One line more than the common workflow: the environment of the preflight recipient guard.
        extra = 'DELIVERY_RECIPIENT: ${{ steps.manifest.outputs.recipient }}'
        self.assertEqual((generated.count(extra), common.count(extra)), (2, 1))
        generated.remove(extra)
        self.assertEqual(generated, common)
        application = {step['name']: step for step in self.spec['jobs']['application']['steps']}
        self.assertEqual(self.spec['jobs']['application']['env']['DELIVERY_RECIPIENT'],
                         '${{ needs.preflight.outputs.recipient }}')
        names = list(application)
        guard = names.index('Check the committed recipient public key of this build')
        for name, step in application.items():
            if 'delivery_cipher.py' in step.get('run', ''):
                self.assertLess(guard, names.index(name), name)

    def test_uploads_only_through_the_protected_action_at_its_pin(self):
        uses = re.findall(r'\buses:\s*(\S+)', self.text)
        uploads = [action for action in uses if 'upload' in action]
        self.assertEqual(len(uploads), 21)
        self.assertEqual(set(uploads), {'TarbleFR/RewindBox/.github/actions/upload-protected-artifact@'
                                        '3bd75a37a4056eb9324987c76f32b002a89d58cb'})
        self.assertEqual(check_workflows.GUARD, uploads[0])
        self.assertNotIn('actions/upload-artifact', self.text)
        self.assertEqual(check_workflows.errors(ROOT), [])
        self.assertEqual(sorted(uses), sorted(re.findall(r'\buses:\s*(\S+)', self.common_text)))

    def test_probe_key_is_set_after_the_host_and_before_the_stamp_and_the_build(self):
        steps = self.spec['jobs']['application']['steps']
        names = [step['name'] for step in steps]
        key = names.index('Turn the S2Arm device probe on in the generated host')
        self.assertEqual(steps[key]['run'], 'python3 build-utils/s2arm/set_probe_key.py set\n'
                                            'python3 build-utils/s2arm/set_probe_key.py check-host\n')
        for earlier in ('Generate iOS host', 'Configure release host',
                        'Verify central session pod is in the actual generated host'):
            self.assertLess(names.index(earlier), key, earlier)
        self.assertEqual(names[key + 1], 'Align application and extension versions to the pubspec version')
        build = names.index('Compile Release device binary with measured AOT and Xcode phases')
        self.assertLess(key, build)
        self.assertEqual(names[build + 1], 'Check the S2Arm probe key and code in the compiled application')
        self.assertIn('check-app build/ios/DolphinDerivedData/Build/Products/Release-iphoneos/Runner.app',
                      steps[build + 1]['run'])
        signed = names.index('Check the S2Arm probe key and code in the signed IPA')
        self.assertEqual(names[signed - 1], 'Verify every signed image, the replaced Core payloads and the retained payloads')
        self.assertIn('check-ipa "dist/$IPA_NAME.ipa"', steps[signed]['run'])
        self.assertLess(signed, names.index('Prepare encrypted delivery and evidence'))
        self.assertLess(signed, names.index('Upload encrypted IPA and verification reports'))
        self.assertEqual(self.text.count('set_probe_key.py set\n'), 1)
        for step in steps:   # no step of the workflow rewrites the key afterwards or ignores a failure
            self.assertNotIn('continue-on-error', step)
        self.assertNotIn(probe.FORBIDDEN_KEY, self.text)

    def test_a_trigger_commit_of_this_line_starts_this_workflow_only(self):
        try:
            import yaml  # noqa: F401
        except ImportError:
            self.skipTest('trigger-paths parses every workflow with PyYAML')
        report = self.sd.trigger_paths(801, ['build-utils/delivery/801.json'])
        self.assertEqual(report['otherWorkflowsStarted'], {})
        self.assertIn('preflight', report['standardDeliveryJobs'])
        self.assertTrue(report['subject'].startswith('[s2arm-delivery:801] '))
        for paths, message in ((['build-utils/s2arm/set_probe_key.py'], None), (['pubspec.yaml'], None),
                               (['build-utils/delivery/801.json'], '[ipa-delivery:801] request'),
                               (['build-utils/delivery/801.json'], '[s2arm-delivery:801] request [skip ci]')):
            with self.assertRaises(ValueError, msg=paths):
                self.sd.trigger_paths(801, paths, message)


def macho(symbols, magic=0xFEEDFACF, cpu=0x0100000C):
    """A minimal 64-bit Mach-O with only a symbol table: [(name, n_type)]."""
    strings, entries = b'\0', b''
    for name, kind in symbols:
        entries += struct.pack('<IBBHQ', len(strings), kind, 1, 0, 0x100000000)
        strings += name.encode() + b'\0'
    symbol_offset = 32 + 24
    header = struct.pack('<IiiIIIII', magic, cpu, 0, 2, 1, 24, 0, 0)
    command = struct.pack('<IIIIII', 2, 24, symbol_offset, len(symbols), symbol_offset + len(entries), len(strings))
    return header + command + entries + strings


LINKED = macho([('_main', 0x0F), ('_OBJC_CLASS_$_S2ArmProbePlugin', 0x0F), ('_rb_s2arm_probe_attached', 0x0E),
                ('_rb_s2arm_probe_detached', 0x0F), ('_objc_msgSend', 0x01)])


class ProbeKey(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.plist = self.root / 'Info.plist'

    def write(self, value):
        self.plist.write_bytes(plistlib.dumps(value, fmt=plistlib.FMT_XML, sort_keys=False))

    def test_set_once_then_refused(self):
        self.write({'CFBundleName': 'Runner', 'RewindBoxMeloNXRamDonor': True, 'CFBundleVersion': '1'})
        self.assertEqual(probe.main(['set', '--plist', str(self.plist)]), 0)
        info = plistlib.loads(self.plist.read_bytes())
        self.assertIs(info['RewindBoxS2ArmProbe'], True)
        self.assertEqual(list(info), ['CFBundleName', 'RewindBoxMeloNXRamDonor', 'CFBundleVersion', 'RewindBoxS2ArmProbe'])
        self.assertNotIn('RewindBoxS2ArmProbeMapped', info)
        before = self.plist.read_bytes()
        self.assertEqual(probe.main(['set', '--plist', str(self.plist)]), 1, 'a second set must be refused')
        with self.assertRaisesRegex(probe.ProbeError, 'already'):
            probe.set_key(self.plist)
        self.assertEqual(self.plist.read_bytes(), before)

    def test_refusals(self):
        with self.assertRaisesRegex(probe.ProbeError, 'Missing host Info.plist'):
            probe.set_key(self.root / 'absent/Info.plist')
        self.assertEqual(probe.main(['set', '--plist', str(self.root / 'absent/Info.plist')]), 1)
        self.write({'RewindBoxS2ArmProbeMapped': False})
        with self.assertRaisesRegex(probe.ProbeError, 'must never be set'):
            probe.set_key(self.plist)
        self.write({'RewindBoxS2ArmProbe': False})
        with self.assertRaisesRegex(probe.ProbeError, 'already'):
            probe.set_key(self.plist)
        self.plist.write_bytes(b'not a property list')
        with self.assertRaises(probe.ProbeError):
            probe.set_key(self.plist)
        for value in ({}, {'RewindBoxS2ArmProbe': False}, {'RewindBoxS2ArmProbe': 'true'}, {'RewindBoxS2ArmProbe': 1},
                      {'RewindBoxS2ArmProbe': True, 'RewindBoxS2ArmProbeMapped': True},
                      {'RewindBoxS2ArmProbe': True, 'RewindBoxS2ArmProbeMapped': False}):
            with self.assertRaises(probe.ProbeError, msg=value):
                probe.check_info(plistlib.dumps(value), 'Info.plist')

    def test_the_stamp_keeps_the_key(self):
        """build-utils/stamp_host_version.py rewrites the host Info.plist right after: same reader and writer."""
        self.write({'CFBundleVersion': '1'})
        probe.set_key(self.plist)
        data = plistlib.loads(self.plist.read_bytes())
        data['CFBundleVersion'] = '801'
        self.plist.write_bytes(plistlib.dumps(data, fmt=plistlib.FMT_XML, sort_keys=False))
        self.assertEqual(probe.check_info(self.plist.read_bytes(), 'Info.plist')['value'], True)
        stamp = (ROOT / 'build-utils/stamp_host_version.py').read_text()
        self.assertIn("plistlib.loads(path.read_bytes())", stamp)
        self.assertNotIn('RewindBoxS2ArmProbe', stamp)

    def test_host_check(self):
        registrant = self.root / 'GeneratedPluginRegistrant.m'
        self.write({'RewindBoxS2ArmProbe': True})
        registrant.write_text('[S2ArmProbePlugin registerWithRegistrar:[registry registrarForPlugin:@"S2ArmProbePlugin"]];')
        self.assertEqual(probe.check_host(registrant, self.plist)['pluginClass'], 'S2ArmProbePlugin')
        registrant.write_text('[OtherPlugin registerWithRegistrar:nil];')
        with self.assertRaisesRegex(probe.ProbeError, 'does not register'):
            probe.check_host(registrant, self.plist)

    def test_executable(self):
        self.assertEqual(probe.check_executable(LINKED, 'Runner')['definedSymbols'], list(probe.REQUIRED_SYMBOLS))
        self.assertEqual(probe.check_executable(LINKED, 'Runner')['evidence'], 'symbols')
        # A stripped release executable: no probe symbol left, the Objective-C metadata of the plugin remains.
        metadata = b''.join(b'\0' + name.encode() for name in probe.OBJC_METADATA) + b'\0'
        stripped = probe.check_executable(macho([]) + metadata, 'Runner')
        self.assertEqual((stripped['evidence'], stripped['strippedSymbols']), ('objc-metadata', list(probe.REQUIRED_SYMBOLS)))
        for absent in probe.OBJC_METADATA:
            partial = b''.join(b'\0' + name.encode() for name in probe.OBJC_METADATA if name != absent) + b'\0'
            with self.assertRaisesRegex(probe.ProbeError, absent):
                probe.check_executable(macho([]) + partial, 'Runner')
        fat = struct.pack('>IIIIIII', 0xCAFEBABE, 1, 0x0100000C, 0, 28, len(LINKED), 14) + LINKED
        self.assertEqual(probe.check_executable(fat, 'Runner')['pluginClass'], 'S2ArmProbePlugin')
        for missing in probe.REQUIRED_SYMBOLS:
            image = macho([(name, 0x0F) for name in probe.REQUIRED_SYMBOLS if name != missing])
            with self.assertRaisesRegex(probe.ProbeError, re.escape(missing)):
                probe.check_executable(image, 'Runner')
        # An imported (undefined) or debugging entry is not a definition.
        for kind in (0x01, 0x24):
            image = macho([(name, 0x0F) for name in probe.REQUIRED_SYMBOLS[:2]] + [(probe.REQUIRED_SYMBOLS[2], kind)])
            with self.assertRaises(probe.ProbeError):
                probe.check_executable(image, 'Runner')
        for raw in (b'', b'\0' * 64, macho([], cpu=0x01000007), struct.pack('<IiiIIIII', 0xFEEDFACF, 0x0100000C, 0, 2, 0, 0, 0, 0)):
            with self.assertRaises(probe.ProbeError):
                probe.check_executable(raw, 'Runner')

    def ipa(self, info, runner=LINKED, extra=()):
        path = self.root / 'test.ipa'
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('Payload/NeoStation.app/Info.plist', plistlib.dumps(info))
            archive.writestr('Payload/NeoStation.app/Runner', runner)
            for name in extra:
                archive.writestr(name, b'x')
        return path

    def test_ipa_and_application(self):
        good = {'CFBundleVersion': '801', 'RewindBoxS2ArmProbe': True}
        result = probe.check_ipa(self.ipa(good))
        self.assertEqual((result['result'], result['application'], result['value']), ('passed', 'NeoStation.app', True))
        self.assertEqual(probe.main(['check-ipa', str(self.ipa(good)), '--report', str(self.root / 'report.json')]), 0)
        self.assertEqual(json.loads((self.root / 'report.json').read_bytes())['result'], 'passed')
        with self.assertRaises(probe.ProbeError):
            probe.check_ipa(self.ipa({'CFBundleVersion': '801'}))
        with self.assertRaises(probe.ProbeError):
            probe.check_ipa(self.ipa(dict(good, RewindBoxS2ArmProbeMapped=True)))
        with self.assertRaises(probe.ProbeError):
            probe.check_ipa(self.ipa(good, runner=macho([('_main', 0x0F)])))
        with self.assertRaisesRegex(probe.ProbeError, 'separate probe framework'):
            probe.check_ipa(self.ipa(good, extra=['Payload/NeoStation.app/Frameworks/s2arm_probe.framework/s2arm_probe']))
        self.assertEqual(probe.main(['check-ipa', str(self.root / 'absent.ipa')]), 1)
        app = self.root / 'Runner.app'
        app.mkdir()
        (app / 'Info.plist').write_bytes(plistlib.dumps(good))
        (app / 'Runner').write_bytes(LINKED)
        self.assertEqual(probe.check_app(app)['result'], 'passed')
        (app / 'Runner').write_bytes(macho([('_main', 0x0F)]))
        self.assertEqual(probe.main(['check-app', str(app)]), 1)


class Manifest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sd = line.configure()
        cls.model = manifest()

    def draft(self, mode, **keywords):
        return make_manifest.draft(self.sd, mode, MODEL, 801, **keywords)

    def test_successor_of_the_delivered_model(self):
        value = self.draft('successor')
        self.assertEqual(self.sd.manifest_errors(value), [], 'the recipe refuses the draft')
        self.assertEqual((value['build'], value['status'], value['base']['build']), (801, 'draft', MODEL))
        self.assertNotIn('frozen', value)
        folder = f'docs/evidence/rewind{MODEL}'
        receipt = json.loads((ROOT / folder / 'delivery.json').read_bytes())
        base = value['base']
        self.assertEqual((base['source'], base['tree'], base['run'], base['attempt']),
                         tuple(receipt['execution'][key] for key in ('source', 'tree', 'run', 'attempt')))
        self.assertEqual(base['workflow'], line.COMMON_WORKFLOW)
        self.assertEqual(base['receipt'], dict(path=folder + '/delivery.json',
                                               sha256=sha((ROOT / folder / 'delivery.json').read_bytes()),
                                               proofFiles=len(receipt['proofFiles'])))
        self.assertEqual(base['ipa']['sha256'], receipt['ipa']['sha256'])
        self.assertEqual(len(self.sd.verify_base(value)), base['identity']['images'])
        for key in ('rpcs3', 'melonx'):
            spec = value['components'][key]
            self.assertIs(spec['unchangedFromBase'], True)
            self.assertNotIn(key, value['images']['replaced'])
            self.assertEqual(value['images']['retained'][key], [spec['image']])
            self.assertEqual(spec['pinSha256'], self.model['components'][key]['pinSha256'])
        self.assertEqual(value['images']['mustChange'], ['Frameworks/App.framework/App', 'Runner'])
        self.assertEqual((value['images']['added'], value['images']['removed']), ([], []))
        self.assertEqual(value['product'], dict(reviewedCommits=[], sourceOnly=[], promotedCommits=[]))
        self.assertEqual(value['republish'], self.model['republish'])

    def test_sibling_of_the_model(self):
        value = self.draft('sibling', reviewed=[('1' * 40, 'probe')], source_only=[('2' * 40, 'work branch')])
        self.assertEqual(self.sd.manifest_errors(value), [])
        self.assertEqual(value['base'], self.model['base'])
        self.assertEqual(value['components'], self.model['components'])
        self.assertEqual(value['product']['reviewedCommits'][:-1], self.model['product']['reviewedCommits'])
        self.assertEqual(value['product']['reviewedCommits'][-1], dict(commit='1' * 40, note='probe'))
        self.assertEqual(value['product']['sourceOnly'][-1], dict(commit='2' * 40, targetBuild=802, note='work branch'))
        self.assertEqual(value['images']['replaced'], self.model['images']['replaced'])
        self.assertLessEqual(set(self.model['images']['mustChange']) | {'Runner'}, set(value['images']['mustChange']))
        self.assertEqual(value['s2arm']['pending'][-1:], [] if (ROOT / line.recipient_path(801)).is_file() else
                         value['s2arm']['pending'][-1:])

    def test_a_draft_carries_nothing_the_freeze_writes(self):
        for mode in ('successor', 'sibling'):
            value = self.draft(mode)
            self.assertEqual(set(value['product']), set(make_manifest.DRAFT_PRODUCT_KEYS), mode)
            self.assertEqual(set(value['images']), set(make_manifest.DRAFT_IMAGE_KEYS), mode)
            for group in self.sd.TEST_GROUPS:
                self.assertEqual(value['tests'][group]['mode'], 'fresh', (mode, group))
                self.assertNotIn('commands', value['tests'][group])
                self.assertNotIn('reuse', value['tests'][group])
                self.assertEqual(value['tests'][group].get('additions'), self.model['tests'][group].get('additions'))
            self.assertEqual(value['recipient']['path'], 'build-utils/delivery-801-recipient.pem')
            frozen = dict(value, status='frozen')
            self.assertTrue(self.sd.manifest_errors(frozen), 'a draft relabelled frozen must be refused')

    def test_the_declared_delta(self):
        value = self.draft('successor')
        delta = value['s2arm']['delta']
        self.assertEqual(delta['hostInfoPlist'], dict(set={'RewindBoxS2ArmProbe': True},
                                                      never=['RewindBoxS2ArmProbeMapped'],
                                                      by='build-utils/s2arm/set_probe_key.py'))
        self.assertEqual(delta['runnerMustDefine'], list(probe.REQUIRED_SYMBOLS))
        paths = value['s2arm']['deltaPaths']
        self.assertIn('pubspec.yaml', paths)
        self.assertIn('packages/s2arm_probe/ios/s2arm_probe.podspec', paths)
        self.assertTrue(all(self.sd.is_product(path) for path in paths), 'the delta is product: it must be reviewed')
        self.assertEqual(value['s2arm']['derivedMustChange'], ['Frameworks/App.framework/App'])
        pubspec = (ROOT / 'pubspec.yaml').read_text()
        self.assertEqual(pubspec.count('  - packages/s2arm_probe\n'), 1)
        self.assertEqual(pubspec.count('  s2arm_probe:\n    path: packages/s2arm_probe\n'), 1)
        self.assertNotIn('s2arm', (ROOT / 'pubspec.lock').read_text())
        with self.assertRaises(SystemExit):
            make_manifest.draft(self.sd, 'successor', MODEL, 725)

    def test_the_committed_drafts_are_the_generated_ones(self):
        for mode in ('successor', 'sibling'):
            committed = json.loads((HERE / f'drafts/801.{mode}-of-{MODEL}.draft.json').read_bytes())
            value = self.draft(mode)
            for item in (committed, value):   # the recipient key is committed later, by its owner
                item['recipient']['sha256'] = None
                item['s2arm']['pending'] = [text for text in item['s2arm']['pending'] if not text.startswith('recipient')]
            self.assertEqual(committed, value, mode)
            self.assertEqual(committed['status'], 'draft')

    def test_no_manifest_of_this_line_is_in_the_common_directory_unfrozen(self):
        for path in (ROOT / 'build-utils/delivery').glob('*.json'):
            if path.stem.isdecimal() and int(path.stem) >= line.FIRST_BUILD:
                self.assertEqual(self.sd.manifest_errors(json.loads(path.read_bytes())), [], path.name)


class NewFiles(unittest.TestCase):
    def test_placement_and_content_rules(self):
        sd = line.configure()
        recipe = ['.github/workflows/s2arm-delivery.yml'] + [
            path.relative_to(ROOT).as_posix() for path in sorted(HERE.rglob('*')) if path.is_file() and
            '__pycache__' not in path.parts]
        for path in recipe:
            self.assertTrue(sd.is_recipe(path), path + ' must be a recipe path (no classification, never compiled)')
        self.assertTrue(sd.is_product('build-utils/s2arm/set_probe_key.py'),
                        'the key setter changes the application: it is product, reviewed with the probe')
        banned = re.compile('|'.join(('cl' + 'aude-', 'gp' + 't-', 'son' + 'net', 'op' + 'us', 'hai' + 'ku')), re.I)
        for path in recipe + ['build-utils/s2arm/set_probe_key.py']:
            text = (ROOT / path).read_text()
            self.assertIsNone(banned.search(text), path + ' names a model')
            self.assertNotIn('PRIVATE' + ' KEY', text, path)


if __name__ == '__main__':
    os.environ.pop('BUILD_NUMBER', None)
    unittest.main(verbosity=2)
