#!/usr/bin/env python3
"""Offline tests of the Switch 2 (S2Arm) test IPA delivery line (plain python3; no network, no build).

    python3 -B .github/diagnostics/s2arm/s2arm_delivery_test.py

What they cover: the launcher redirects exactly the reviewed line constants of the unchanged standard
recipe and refuses a recipe it was not reviewed for; the base stays authenticated on the line that
delivered it; the generated workflow is the committed one, triggers only on this branch and tag, keeps
every common step and uploads only through the protected action; the Info.plist key is set once, in
order, and the built application is checked; the draft manifests are accepted by the recipe's own checker.
The S2Arm engine: its producer run and artifact authenticated (mocked API, synthetic producer archives),
frameworks and identity embedded and checked in a synthetic built application and signed IPA, the common
validators accepting the S2Arm application through their own conditionals (same outcome as the common line's files
without the identity; nothing extended in memory), the engine steps with no edit of a common step, a draft carrying
the engine, the common downloaded-delivery verifier run unchanged. The engine's licence and notice texts: listed
by the producer (synthetic), checked at download against their record, the legal gate's rule, the pin and the producer
commit's RewindBox notice, placed in Legal/S2Arm and checked there in the application (also by the gate's own S2Arm
conditional), in the signed IPA and offline, with the legal gate run again on the built application by the workflow.
The engine bridge (packages/s2arm_engine_bridge): its preparation library and system data producers authenticated
(mocked API, synthetic xcframework and system data tree), the library installed where the podspec vendors it, the
tree placed as S2ArmSystemData, both recorded in the engine identity and checked in the built application, the
signed IPA and offline (system data against SHA256SUMS, licences, direct chain, registrant, a synthetic Runner's
symbols and export trie), the four steps and their order, a draft carrying the bridge.
Not covered here (needs the reshaped history, the network or a macOS build): freeze, the API-backed
contract checks, the run itself, a real engine framework, a real xcframework, system data tree or Runner.
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
import shutil
import struct
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
for _part in (HERE, ROOT / 'build-utils/s2arm', ROOT / '.github/ipa-protection', ROOT / 'build-utils', ROOT / 'test',
              ROOT / '.github/diagnostics'):
    if str(_part) not in sys.path:
        sys.path.insert(0, str(_part))

import standard_delivery_s2arm as line  # noqa: E402
import make_manifest  # noqa: E402
import make_workflow  # noqa: E402
import set_probe_key as probe  # noqa: E402
import check_workflows  # noqa: E402
import single_ipa_distribution_test as fixtures  # noqa: E402

RECIPE = ROOT / line.RECIPE
# The recipe file the launcher inventory was reviewed against (commit 687ea833). A different file is not an
# error of the recipe: it asks for a review of RECIPE_INVENTORY and HANDLING, then for this value.
REVIEWED_RECIPE_SHA256 = '503fe296c8764bcb3a16cac01ac0f7e202737d6e94058a2b2d806219f9271a41'
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
                            'Download and authenticate the S2Arm engine frameworks of the pinned producer run',
                            'Download and authenticate the S2Arm preparation library of the pinned producer run',
                            'Download and authenticate the S2Arm system data of the pinned producer run',
                            'Install the S2Arm preparation library in the engine bridge package before CocoaPods',
                            'Turn the S2Arm device probe on in the generated host',
                            'Add the S2Arm JIT helper extension to the generated host',
                            'Check the S2Arm probe key and code in the compiled application',
                            'Place the S2Arm system data and its licences in the built application',
                            'Embed the S2Arm engine frameworks and their identity in the built application',
                            'Check the S2Arm engine frameworks, identity and JIT helper in the built application',
                            'Check the legal gate with the S2Arm engine notices of the built application',
                            'Check the S2Arm probe key and code in the signed IPA',
                            'Check the S2Arm engine frameworks, identity and JIT helper in the signed IPA']})
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
        # The common calls, the three guards, the four engine steps, and the four steps of the engine bridge
        # (preparation library download and install, system data download and placement). The Dolphin packager is
        # the common call: its validator has its own S2Arm conditional.
        self.assertEqual(len(recipe_calls), self.common_text.count('.github/diagnostics/standard_delivery.py') + 3 + 4 + 4)
        self.assertNotIn('diagnostics/standard_delivery.py', self.text)
        operations = {operation for script, operation in calls if 'standard_delivery' in script}
        self.assertLessEqual(operations, set(self.sd.OPERATIONS) | set(line.LINE_OPERATIONS))
        self.assertLessEqual({'request-guard', 'recipient-guard', 'engine-download', 'engine-embed', 'engine-check-app',
                              'engine-check-ipa', 'prepare-download', 'prepare-install',
                              'sysdata-download', 'sysdata-embed'}, operations)
        self.assertEqual(set(line.LINE_OPERATIONS) - {'inventory'},
                         set(line.PATH_OPERATIONS) | set(line.PLAIN_OPERATIONS))
        # The recipe steps that run a closed-set validator on the application go through the launcher, unchanged.
        self.assertLessEqual({'structure', 'seal', 'validate'}, operations)
        self.assertNotIn('dolphin-package', operations)

    def test_validators_encryption_and_split_are_the_common_ones(self):
        def lines(text, *needles):
            return [item.strip() for item in text.splitlines() if any(needle in item for needle in needles)]
        needles = ('delivery_cipher.py', 'split_encrypted_delivery.py', 'build-utils/validate_', 'retention-days',
                   'compression-level', 'if-no-files-found', 'shasum', 'DELIVERY_RECIPIENT', 'embed_legal_bundle.py')
        generated, common = lines(self.text, *needles), lines(self.common_text, *needles)
        # Two lines more than the common workflow: the environment of the preflight recipient guard, and the legal gate
        # run again on the built application once it carries the engine's notices.
        extra = 'DELIVERY_RECIPIENT: ${{ steps.manifest.outputs.recipient }}'
        self.assertEqual((generated.count(extra), common.count(extra)), (2, 1))
        generated.remove(extra)
        gate = ('run: python3 build-utils/embed_legal_bundle.py --validate-only --app '
                'build/ios/DolphinDerivedData/Build/Products/Release-iphoneos/Runner.app --dolphin-sha "$DOLPHIN_SHA"')
        self.assertEqual((generated.count(gate), common.count(gate)), (1, 0))
        generated.remove(gate)
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
        self.assertEqual(names[key + 1], 'Add the S2Arm JIT helper extension to the generated host')
        self.assertEqual(names[key + 2], 'Align application and extension versions to the pubspec version')
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


ENGINE_ZIP_SHA = 'f' * 64
ARTIFACT_ID = 777001
ENGINE_RUN = 43100000001
PRODUCER = '9' * 40
CHAIN = b'0be3f28548fd'


def dylib(install_name, dependencies=(), signed=False, filetype=6, rpaths=()):
    """A minimal arm64 iOS image: LC_BUILD_VERSION (iOS 18.0), LC_ID_DYLIB, LC_LOAD_DYLIB, LC_RPATH, optionally
    an empty code-signature superblob (what signing adds; the payload fingerprint ignores it)."""
    def text(kind, value):
        raw = value.encode() + b'\0'
        size = (24 + len(raw) + 7) // 8 * 8
        return struct.pack('<6I', kind, size, 24, 0, 0, 0) + raw + bytes(size - 24 - len(raw))
    commands = [struct.pack('<6I', 0x32, 24, 2, 18 << 16, 0, 0)]
    if install_name:
        commands.append(text(0xD, install_name))
    commands += [text(0xC, item) for item in dependencies]
    commands += [text(0x8000001C, item) for item in rpaths]
    size = sum(map(len, commands)) + (16 if signed else 0)
    body = b'image payload'
    signature = struct.pack('>III', 0xFADE0CC0, 12, 0)
    if signed:
        commands.append(struct.pack('<4I', 0x1D, 16, 32 + size + len(body), len(signature)))
    header = struct.pack('<8I', 0xFEEDFACF, 0x0100000C, 0, filetype, len(commands), size, 0, 0)
    return header + b''.join(commands) + body + (signature if signed else b'')


def framework_files(name, signed=False):
    files = {f'{name}.framework/{name}': dylib(
        f'@rpath/{name}.framework/{name}', ('/usr/lib/libSystem.B.dylib', '/System/Library/Frameworks/Metal.framework/Metal')
        + (('@rpath/NS2Pro.framework/NS2Pro',) if name == 'S2ArmEngine' else ()), signed=signed),
        f'{name}.framework/Info.plist': plistlib.dumps({'CFBundleExecutable': name, 'CFBundlePackageType': 'FMWK',
                                                         'CFBundleIdentifier': 'org.s2arm.' + name}),
        f'{name}.framework/{name.lower()}.metallib': b'MTLB fixture data'}
    if name == 'S2ArmEngine':   # written beside the engine by its producer (guest.mk): DMSH_CHAIN of the pin
        files[f'{name}.framework/{line.DIRECT_CHAIN}'] = CHAIN + b'\n'
    if signed:
        files[f'{name}.framework/_CodeSignature/CodeResources'] = b'<plist>signed</plist>'
    return files


def zipped(files, symlink=None):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        for path, data in files.items():
            archive.writestr(path, data)
        if symlink:
            entry = zipfile.ZipInfo(symlink)
            entry.external_attr = (0o120777 << 16)
            archive.writestr(entry, b'target')
    return buffer.getvalue()


PATCHES = {'build-utils/s2arm/engine/patches/0001-a.patch': b'patch one\n',
           'build-utils/s2arm/engine/patches/0002-b.patch': b'patch two\n'}
PIN = json.dumps({'s2arm': {'commit': '6b6a571553f7a687af46e03e2cdbf8ef4d77f335'},
                  'dependencies': json.loads((ROOT / line.ENGINE_PIN).read_bytes())['dependencies']}).encode()


NOTICE = (ROOT / line.ENGINE_NOTICE).read_bytes()


class FakeRepo:
    """The git queries the engine checks make, on a producer commit with the pin, two patches and the notice."""
    def __init__(self, ancestor=True, files=None):
        self.ancestor = ancestor
        self.files = dict(PATCHES, **{'tools/s2arm_prototype/pin.json': PIN, line.ENGINE_NOTICE: NOTICE}) \
            if files is None else files

    def is_ancestor(self, ancestor, descendant):
        return self.ancestor

    def entries(self, ref):
        assert ref == PRODUCER
        return {path: ('100644', 'blob') for path in self.files}

    def show(self, ref, path):
        assert ref == PRODUCER
        return self.files[path]


def licence_texts(commit='6b6a571553f7a687af46e03e2cdbf8ef4d77f335', notice=NOTICE, drop=(), change=None):
    """The engine's licence and notice texts as its producer collects them (collect_licenses.py): every text the legal
    gate requires, RewindBox's notice and the manifest that lists them with their origin and SHA-256."""
    gate = line.legal()
    texts = {path: f'licence text fixture: {path}\n'.encode() for path in gate.S2ARM_REQUIRED_NOTICES if path not in drop}
    texts['MacNativeGames/LICENSE'] = b'an optional licence text fixture\n'
    if gate.S2ARM_REWINDBOX_NOTICE in texts:
        texts[gate.S2ARM_REWINDBOX_NOTICE] = notice
    if change:
        change(texts)
    manifest = dict(schema=1, engine='S2Arm', s2arm=dict(repository='https://github.com/jhaizhou-ops/S2Arm', commit=commit),
                    collector='build-utils/s2arm/engine/collect_licenses.py', components=[
                        dict(component=path.split('/')[0], license='fixture', files=[dict(
                            path=path, sha256=sha(data), bytes=len(data),
                            source=dict(kind='rewindbox' if path == gate.S2ARM_REWINDBOX_NOTICE else 's2arm', path=path))])
                        for path, data in texts.items()])
    return dict(texts, **{gate.S2ARM_NOTICE_MANIFEST: (json.dumps(manifest, indent=1) + '\n').encode()})


def producer_artifact(zips=None, identity=None, extra=None, licences=None):
    zips = zips or {name: zipped(framework_files(name)) for name in line.ENGINE_FRAMEWORKS}
    archives = {f'{name}.framework.zip': data for name, data in zips.items()}
    licences = licence_texts() if licences is None else licences
    value = dict(run=ENGINE_RUN, attempt=1, head_sha=PRODUCER, s2arm_commit='6b6a571553f7a687af46e03e2cdbf8ef4d77f335',
                 patches=[dict(name=path.rsplit('/', 1)[1], sha256=sha(data)) for path, data in sorted(PATCHES.items())],
                 files={name: sha(data) for name, data in archives.items()},
                 licenses=dict(manifest=line.ENGINE_LICENSE_MANIFEST, files=len(licences),
                               sha256=sha(licences.get(line.legal().S2ARM_NOTICE_MANIFEST, b''))))
    value.update(identity or {})
    members = dict(archives, **{line.ENGINE_LICENSES + path: data for path, data in licences.items()},
                   **{line.ENGINE_IDENTITY: json.dumps(value).encode()}, **(extra or {}))
    return zipped(members), {name: sha(data) for name, data in archives.items()}


def api_for(artifact, run=None, artifacts=None):
    def get(endpoint):
        if endpoint == f'actions/runs/{ENGINE_RUN}':
            return dict(dict(id=ENGINE_RUN, path=line.ENGINE_WORKFLOW, head_branch=line.DELIVERY_BRANCH,
                             status='completed', conclusion='success', run_attempt=1, head_sha=PRODUCER), **(run or {}))
        if endpoint.startswith(f'actions/runs/{ENGINE_RUN}/artifacts?name='):
            name = line.ENGINE_ARTIFACT.format(source=PRODUCER)
            assert endpoint == f'actions/runs/{ENGINE_RUN}/artifacts?name={name}&per_page=100', endpoint
            default = [dict(id=ARTIFACT_ID, name=name, size_in_bytes=len(artifact), digest='sha256:' + sha(artifact),
                            expired=False, expires_at='2026-12-01T00:00:00Z',
                            workflow_run=dict(id=ENGINE_RUN, head_sha=PRODUCER))]
            return dict(artifacts=default if artifacts is None else artifacts(default))
        raise AssertionError('unexpected endpoint ' + endpoint)
    return get


# --- The engine bridge: synthetic producers of the preparation library and of the system data ------------------
PREPARE_RUN = 43100000002
SYSDATA_RUN = 43100000003
PREPARE_ARTIFACT_ID = 777002
SYSDATA_ARTIFACT_ID = 777003
LIBRARY = b'!<arch>\nS2ArmPrepare.o/ 0 0 0 644 16 `\nrelocatable obj\n'
REGISTRANT = ('#import "GeneratedPluginRegistrant.h"\n@implementation GeneratedPluginRegistrant\n'
              '+ (void)registerWithRegistry:(NSObject<FlutterPluginRegistry>*)registry {\n'
              '  [S2ArmProbePlugin registerWithRegistrar:[registry registrarForPlugin:@"S2ArmProbePlugin"]];\n'
              f'  {line.BRIDGE_REGISTRATION}\n}}\n@end\n')


def xcframework(library=LIBRARY, entry=None, extra=None, info=None):
    """S2ArmPrepare.xcframework as xcodebuild -create-xcframework makes it from one iOS arm64 static library."""
    library_entry = dict(BinaryPath=line.PREPARE_LIBRARY, HeadersPath='Headers', LibraryIdentifier='ios-arm64',
                         LibraryPath=line.PREPARE_LIBRARY, SupportedArchitectures=['arm64'], SupportedPlatform='ios')
    library_entry.update(entry or {})
    plist = dict(AvailableLibraries=[library_entry], CFBundlePackageType='XFWK', XCFrameworkFormatVersion='1.0')
    plist.update(info or {})
    root = line.PREPARE_XCFRAMEWORK + '/'
    files = {root + 'Info.plist': plistlib.dumps(plist), root + 'ios-arm64/' + line.PREPARE_LIBRARY: library,
             root + 'ios-arm64/Headers/s2arm_prepare.h': b'/* fixture */\n',
             root + 'ios-arm64/Headers/s2arm_pack.h': b'/* fixture */\n'}
    files.update(extra or {})
    return files


def prepare_producer(files=None, sums=None, identity=None, undefined=None, extra=None, drop=(), library=LIBRARY,
                     archive=None):
    """The s2arm-core.yml artifact: the xcframework archive (built from `files`, or given), sha256.txt, undefined.txt
    and the identity."""
    if archive is None:
        archive = zipped(xcframework(library=library) if files is None else files)
    listing = (f'{sha(archive)}  {line.PREPARE_ZIP}\n{sha(LIBRARY)}  {line.PREPARE_LIBRARY}\n'.encode()
               if sums is None else sums)
    pin = json.loads(PIN)
    value = dict(component=line.PREPARE_XCFRAMEWORK, source=PRODUCER, s2arm=pin['s2arm']['commit'],
                 dependencies={name: entry['sha256'] for name, entry in pin['dependencies'].items()},
                 sha256={line.PREPARE_ZIP: sha(archive), line.PREPARE_LIBRARY: sha(LIBRARY)}, xcode='Xcode 16.4')
    value.update(identity or {})
    members = {line.PREPARE_ZIP: archive, line.PREPARE_SUMS: listing,
               line.PREPARE_UNDEFINED: b'\nlibS2ArmPrepare.a(S2ArmPrepare.o):\n_free\n_malloc\n' if undefined is None
               else undefined, line.PREPARE_IDENTITY: json.dumps(value).encode(), **(extra or {})}
    return zipped({name: data for name, data in members.items() if name not in drop}), sha(archive)


def sysdata_tree():
    """The system data tree build_sysdata_bundle.sh makes (open fonts, tz data, synthesised data), without SHA256SUMS."""
    return {
        'systemdata/fonts/nintendo_udsg-r_std_003.bfttf': b'open replacement font fixture',
        'systemdata/fonts/nintendo_ext_003.bfttf': b'pad icon font fixture',
        'systemdata/010000000000080E/zoneinfo/UTC': b'TZif2 fixture',
        'systemdata/010000000000080E/binaryList.txt': b'UTC\n',
        'systemdata/0100000000000802/data.bin': b'empty but well-formed fixture',
        'systemdata/0100000000000802.synth': '合成：pack/sysdata_synth.py 0100000000000802\n'.encode(),
        'licenses/fonts/OFL-NotoSans.txt': b'SIL Open Font License 1.1 fixture',
        'licenses/fonts/OFL-NotoSansCJK.txt': b'SIL Open Font License 1.1 fixture',
        'licenses/fonts/MANIFEST.tsv': b'font\tsource\n',
        'licenses/fonts/LICENSES.md': b'# fonts\n',
        'licenses/tzdata/LICENSE': b'Unless specified below, all files in the tz code and data are in the public domain.\n',
        'SOURCES.tsv': ('part\tsource\ns2arm\t' + json.loads(PIN)['s2arm']['commit'] + '\nfonts\tfixture\n'
                        'tzdata\tservices/systemdata/make_tzdata.sh, IANA 2026f\nsynthesised\t0100000000000802\n').encode(),
    }


def sums_of(files):
    return ''.join(f'{sha(data)}  {path}\n' for path, data in files.items()).encode()


def sysdata_producer(tree=None, sums=None, extra=None, drop=(), symlink=None):
    """The macOS system data artifact of s2arm-prepare.yml: the tree and its SHA256SUMS."""
    tree = sysdata_tree() if tree is None else tree
    members = dict(tree, SHA256SUMS=sums_of(tree) if sums is None else sums)
    members.update(extra or {})
    return zipped({name: data for name, data in members.items() if name not in drop}, symlink), sha(members['SHA256SUMS'])


def producer_api(run_id, workflow, pattern, artifact, artifact_id, run=None, artifacts=None):
    """The API of one producer run (successful, this branch, PRODUCER) and of its one artifact."""
    name = pattern.format(source=PRODUCER)

    def get(endpoint):
        if endpoint == f'actions/runs/{run_id}':
            return dict(dict(id=run_id, path=workflow, head_branch=line.DELIVERY_BRANCH, status='completed',
                             conclusion='success', run_attempt=1, head_sha=PRODUCER), **(run or {}))
        if endpoint == f'actions/runs/{run_id}/artifacts?name={name}&per_page=100':
            default = [dict(id=artifact_id, name=name, size_in_bytes=len(artifact), digest='sha256:' + sha(artifact),
                            expired=False, expires_at='2026-12-01T00:00:00Z',
                            workflow_run=dict(id=run_id, head_sha=PRODUCER))]
            return dict(artifacts=default if artifacts is None else artifacts(default))
        raise AssertionError('unexpected endpoint ' + endpoint)
    return get


def prepare_api(artifact, **keywords):
    return producer_api(PREPARE_RUN, line.PREPARE_WORKFLOW, line.PREPARE_ARTIFACT, artifact, PREPARE_ARTIFACT_ID, **keywords)


def sysdata_api(artifact, **keywords):
    return producer_api(SYSDATA_RUN, line.SYSDATA_WORKFLOW, line.SYSDATA_ARTIFACT, artifact, SYSDATA_ARTIFACT_ID, **keywords)


def uleb(value):
    out = bytearray()
    while True:
        byte, value = value & 0x7F, value >> 7
        out.append(byte | (0x80 if value else 0))
        if not value:
            return bytes(out)


def export_trie(names):
    """A dyld export trie: the root's edges are the whole names, each leading to a terminal node (flags 0)."""
    names = sorted(names)
    leaf = uleb(3) + b'\x00' + uleb(0x1000) + b'\x00'   # terminal of 3 bytes: flags, address; no child
    size = 0
    while True:
        root = b'\x00' + bytes([len(names)]) + b''.join(
            name.encode() + b'\0' + uleb(size + index * len(leaf)) for index, name in enumerate(names))
        if len(root) == size:
            return root + leaf * len(names)
        size = len(root)


def runner_image(defined=None, undefined=(), exports=None, entitlements=None, dependencies=(), rpaths=()):
    """A synthetic arm64 iOS Runner: build version, dylibs and rpaths, a symbol table (external definitions and
    imports), a dyld export trie (LC_DYLD_EXPORTS_TRIE) and a code signature with the given entitlements."""
    defined = ['_main', *line.RUNNER_DEFINES] if defined is None else list(defined)
    exports = ['__mh_execute_header', '_main', line.ENGINE_LOADED] if exports is None else list(exports)

    def text(kind, value):
        raw = value.encode() + b'\0'
        size = (24 + len(raw) + 7) // 8 * 8
        return struct.pack('<6I', kind, size, 24, 0, 0, 0) + raw + bytes(size - 24 - len(raw))
    commands = [struct.pack('<6I', 0x32, 24, 2, 18 << 16, 0, 0)]
    commands += [text(0xC, item) for item in dependencies] + [text(0x8000001C, item) for item in rpaths]
    strings, entries = bytearray(b'\0'), bytearray()
    for name, kind in [(name, 0x0F) for name in defined] + [(name, 0x01) for name in undefined]:
        entries += struct.pack('<IBBHQ', len(strings), kind, 1 if kind == 0x0F else 0, 0, 0x1000 if kind == 0x0F else 0)
        strings += name.encode() + b'\0'
    trie = export_trie(exports)
    signature = fixtures.macho({} if entitlements is None else entitlements)[48:]
    size = sum(map(len, commands)) + 24 + 16 + 16
    symbols = 32 + size
    trie_offset = symbols + len(entries) + len(strings)
    commands += [struct.pack('<6I', 2, 24, symbols, len(defined) + len(undefined), symbols + len(entries), len(strings)),
                 struct.pack('<4I', 0x80000033, 16, trie_offset, len(trie)),
                 struct.pack('<4I', 0x1D, 16, trie_offset + len(trie), len(signature))]
    header = struct.pack('<8I', 0xFEEDFACF, 0x0100000C, 0, 2, len(commands), size, 0, 0)
    return header + b''.join(commands) + bytes(entries) + bytes(strings) + trie + signature


class EngineLine(unittest.TestCase):
    """engine-download, engine-embed, engine-check-app and engine-check-ipa on synthetic producer data; the engine
    bridge: prepare-download, prepare-install, sysdata-download, sysdata-embed and its checks in the application."""
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='s2arm-engine-')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.sd = line.configure(private_recipe())
        self.out = self.root / 'build/delivery'
        (self.root / 'packages/s2arm_jit_helper/ios/Resources').mkdir(parents=True)
        self.script = (ROOT / line.HELPER_SCRIPT).read_bytes()
        (self.root / line.HELPER_SCRIPT).write_bytes(self.script)
        self.artifact, self.zips = producer_artifact()
        # The engine bridge of the build: the committed podspec, the generated registrant, the two producers.
        (self.root / line.BRIDGE_PODSPEC).parent.mkdir(parents=True)
        shutil.copyfile(ROOT / line.BRIDGE_PODSPEC, self.root / line.BRIDGE_PODSPEC)
        (self.root / line.BRIDGE_REGISTRANT).parent.mkdir(parents=True)
        (self.root / line.BRIDGE_REGISTRANT).write_text(REGISTRANT)
        self.prepare_artifact, self.prepare_zip = prepare_producer()
        self.sysdata_artifact, self.tree = sysdata_producer()
        self.manifest = dict(build=803, images=dict(added=list(line.ENGINE_IMAGES)),
                             s2arm=dict(engine=dict(workflow=line.ENGINE_WORKFLOW, run=ENGINE_RUN, zips=self.zips),
                                        prepare=dict(workflow=line.PREPARE_WORKFLOW, run=PREPARE_RUN, zip=self.prepare_zip),
                                        sysdata=dict(workflow=line.SYSDATA_WORKFLOW, run=SYSDATA_RUN, tree=self.tree)))
        for name, value in (('OUT', self.out), ('ROOT', self.root)):
            patcher = mock.patch.object(self.sd, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(self.sd, 'ci_manifest', lambda: self.manifest)
        patcher.start()
        self.addCleanup(patcher.stop)
        # As the workflow runs them before CocoaPods: the preparation library installed, the system data downloaded.
        self.prepare()
        line.prepare_install(self.sd, self.root)
        self.sysdata()

    def download(self, artifact=None, get=None, repo=None):
        artifact = self.artifact if artifact is None else artifact
        return line.engine_download(self.sd, get or api_for(artifact), lambda identifier, path: path.write_bytes(artifact),
                                    repo or FakeRepo(), self.root)

    def prepare(self, artifact=None, get=None, repo=None):
        artifact = self.prepare_artifact if artifact is None else artifact
        return line.prepare_download(self.sd, get or prepare_api(artifact),
                                     lambda identifier, path: path.write_bytes(artifact), repo or FakeRepo(), self.root)

    def sysdata(self, artifact=None, get=None, repo=None):
        artifact = self.sysdata_artifact if artifact is None else artifact
        return line.sysdata_download(self.sd, get or sysdata_api(artifact),
                                     lambda identifier, path: path.write_bytes(artifact), repo or FakeRepo(), self.root)

    def application(self, versions=('803', '0.0.8'), system_data=True, runner=None):
        """The built application as the compilation leaves it (Runner linked with the bridge, the JIT helper), and
        with the system data placed by sysdata-embed, as the workflow does right before engine-embed."""
        app = self.root / 'Runner.app'
        if app.exists():
            shutil.rmtree(app)
        helper = app / 'PlugIns' / line.HELPER
        helper.mkdir(parents=True)
        (app / 'Frameworks').mkdir()
        host = {'CFBundleIdentifier': 'com.neogamelab.neostation', 'CFBundleVersion': versions[0],
                'CFBundleShortVersionString': versions[1], 'CFBundleExecutable': 'Runner'}
        (app / 'Info.plist').write_bytes(plistlib.dumps(host))
        (app / 'Runner').write_bytes(runner_image() if runner is None else runner)
        (app / 'Legal').mkdir()   # the legal bundle, as embed_legal_bundle.py writes it before the engine is embedded
        (app / 'Legal/NeoStation-NOTICE.md').write_text('UPSTREAM NEOSTATION ATTRIBUTION fixture\n')
        (helper / 'Info.plist').write_bytes(plistlib.dumps(helper_info(*versions)))
        (helper / line.HELPER_EXECUTABLE).write_bytes(helper_image(signed=False))
        (helper / 's2arm-universal.js').write_bytes(self.script)
        if system_data:
            line.sysdata_embed(self.sd, app, self.root)
        return app

    def test_download_authenticates_the_producer_run_and_its_files(self):
        result = self.download()
        self.assertEqual(result['producer']['artifact']['id'], ARTIFACT_ID)
        self.assertEqual(result['producer']['source'], PRODUCER)
        self.assertEqual(result['zips'], self.zips)
        for name in line.ENGINE_ZIPS + (line.ENGINE_IDENTITY,):
            self.assertTrue((self.root / line.ENGINE_DOWNLOAD / name).is_file(), name)
        self.assertEqual(json.loads((self.out / 's2arm-engine-download.json').read_bytes())['result'], 'authenticated')

    def test_download_refusals(self):
        wrong_zip, _ = producer_artifact()
        cases = {
            'failed run': dict(get=api_for(self.artifact, run=dict(conclusion='failure'))),
            'other branch': dict(get=api_for(self.artifact, run=dict(head_branch='Claude'))),
            'other workflow': dict(get=api_for(self.artifact, run=dict(path='.github/workflows/s2arm-core.yml'))),
            'unfinished run': dict(get=api_for(self.artifact, run=dict(status='in_progress'))),
            'no artifact': dict(get=api_for(self.artifact, artifacts=lambda items: [])),
            'two artifacts': dict(get=api_for(self.artifact, artifacts=lambda items: items * 2)),
            'expired': dict(get=api_for(self.artifact, artifacts=lambda items: [dict(items[0], expired=True)])),
            'other run artifact': dict(get=api_for(self.artifact, artifacts=lambda items: [
                dict(items[0], workflow_run=dict(id=1, head_sha=PRODUCER))])),
            'digest differs': dict(get=api_for(self.artifact, artifacts=lambda items: [
                dict(items[0], digest='sha256:' + '0' * 64)])),
            'commit not delivered': dict(repo=FakeRepo(ancestor=False)),
            'patch series differs': dict(repo=FakeRepo(files=dict(PATCHES, **{
                'tools/s2arm_prototype/pin.json': PIN, 'build-utils/s2arm/engine/patches/0003-c.patch': b'three'}))),
            'pin differs': dict(repo=FakeRepo(files=dict(PATCHES, **{
                'tools/s2arm_prototype/pin.json': json.dumps({'s2arm': {'commit': '1' * 40}}).encode()}))),
        }
        for name, case in cases.items():
            with self.subTest(case=name):
                with self.assertRaises((line.LineError, KeyError)):
                    self.download(**case)
        artifacts = {
            'identity names another run': producer_artifact(identity=dict(run=1))[0],
            'identity names another commit': producer_artifact(identity=dict(head_sha='8' * 40))[0],
            'identity attempt beyond the run': producer_artifact(identity=dict(attempt=2))[0],
            'identity files differ': producer_artifact(identity=dict(files={}))[0],
            'extra member': producer_artifact(extra={'notes.txt': b'x'})[0],
        }
        for name, artifact in artifacts.items():
            with self.subTest(case=name):
                with self.assertRaises(line.LineError):
                    self.download(artifact)
        other = {name: zipped(dict(framework_files(name), **{f'{name}.framework/extra': b'1'}))
                 for name in line.ENGINE_FRAMEWORKS}
        artifact, _ = producer_artifact(zips=other)
        with self.assertRaisesRegex(line.LineError, 'differ from the manifest'):
            self.download(artifact)
        for spec in (None, dict(workflow=line.ENGINE_WORKFLOW, run=0, zips=self.zips),
                     dict(workflow=line.ENGINE_WORKFLOW, run=ENGINE_RUN, zips={'S2ArmEngine.framework.zip': 'f' * 64}),
                     dict(workflow='x', run=ENGINE_RUN, zips=self.zips)):
            with self.subTest(spec=spec):
                self.manifest['s2arm'] = {} if spec is None else dict(engine=spec)
                with self.assertRaises(line.LineError):
                    self.download()

    def test_framework_archives_are_checked(self):
        def archive(name, change):
            files = framework_files(name)
            change(files)
            return zipped(files)
        executable = 'S2ArmEngine.framework/S2ArmEngine'
        cases = {
            'member outside': lambda files: files.update({'Other/file': b'x'}),
            'nested dylib': lambda files: files.update({'S2ArmEngine.framework/libextra.dylib': b'x'}),
            'nested framework': lambda files: files.update({'S2ArmEngine.framework/Frameworks/X.framework/X': b'x'}),
            'second image': lambda files: files.update({'S2ArmEngine.framework/helper': dylib(None)}),
            'not a dylib': lambda files: files.update({executable: dylib('@rpath/S2ArmEngine.framework/S2ArmEngine',
                                                                          filetype=2)}),
            'wrong install name': lambda files: files.update({executable: dylib('@rpath/Other.framework/Other')}),
            'foreign dependency': lambda files: files.update({executable: dylib(
                '@rpath/S2ArmEngine.framework/S2ArmEngine', ('@rpath/MoltenVK.framework/MoltenVK',))}),
            'wrong executable name': lambda files: files.update({'S2ArmEngine.framework/Info.plist': plistlib.dumps(
                {'CFBundleExecutable': 'Other', 'CFBundlePackageType': 'FMWK'})}),
            'missing Info.plist': lambda files: files.pop('S2ArmEngine.framework/Info.plist'),
        }
        self.assertEqual(line.framework_inventory('S2ArmEngine', zipped(framework_files('S2ArmEngine')))['installName'],
                         '@rpath/S2ArmEngine.framework/S2ArmEngine')
        for name, change in cases.items():
            with self.subTest(case=name):
                with self.assertRaises((line.LineError, ValueError)):
                    line.framework_inventory('S2ArmEngine', archive('S2ArmEngine', change))
        with self.assertRaisesRegex(line.LineError, 'symbolic link'):
            line.framework_inventory('NS2Pro', zipped(framework_files('NS2Pro'), symlink='NS2Pro.framework/link'))

    def test_embed_then_check_the_built_application(self):
        self.download()
        app = self.application()
        result = line.engine_embed(self.sd, app, self.root)
        self.assertEqual(result['images'], list(line.ENGINE_IMAGES))
        identity = json.loads((app / line.PACKAGED_IDENTITY).read_bytes())
        self.assertEqual((identity['zips'], identity['producer']['run'], identity['build']), (self.zips, ENGINE_RUN, 803))
        self.assertEqual(identity['jitHelper']['marker'], 'NeoStationS2ArmJITHelper')
        self.assertIs(identity['physicalDeviceTested'], False)
        for name in line.ENGINE_FRAMEWORKS:
            for path, data in framework_files(name).items():
                self.assertEqual((app / 'Frameworks' / path).read_bytes(), data)
            self.assertTrue(os.access(app / 'Frameworks' / f'{name}.framework/{name}', os.X_OK))
        self.assertEqual(line.engine_check_app(self.sd, app, self.root)['result'], 'passed')
        with self.assertRaisesRegex(line.LineError, 'already'):
            line.engine_embed(self.sd, app, self.root)
        tampering = (
            lambda app: (app / 'Frameworks/NS2Pro.framework/ns2pro.metallib').write_bytes(b'changed'),
            lambda app: (app / 'Frameworks/NS2Pro.framework/extra.txt').write_bytes(b'extra'),
            lambda app: (app / 'PlugIns' / line.HELPER / 's2arm-universal.js').write_bytes(b'// other'),
            lambda app: (app / 'PlugIns' / line.HELPER / 'Info.plist').write_bytes(
                plistlib.dumps(dict(helper_info('803', '0.0.8'), NeoStationS2ArmJITHelper='0'))),
            lambda app: (app / 'PlugIns' / line.HELPER / 'Info.plist').write_bytes(plistlib.dumps(helper_info('802', '0.0.8'))),
            lambda app: (app / 'PlugIns' / line.HELPER / line.HELPER_EXECUTABLE).write_bytes(
                fixtures.packaging_image({}, filetype=2)),
            lambda app: nested(app / 'PlugIns' / line.HELPER / 'Frameworks/StikJIT.framework/StikJIT',
                               dylib('@rpath/StikJIT.framework/StikJIT')),
            lambda app: (app / line.PACKAGED_IDENTITY).write_text('{}'),
        )
        for index, tamper in enumerate(tampering):
            with self.subTest(case=index):
                app = self.application()
                line.engine_embed(self.sd, app, self.root)
                tamper(app)
                with self.assertRaises((line.LineError, ValueError, RuntimeError)):
                    line.engine_check_app(self.sd, app, self.root)

    def test_embed_refuses_archives_changed_after_the_download(self):
        self.download()
        (self.root / line.ENGINE_DOWNLOAD / 'NS2Pro.framework.zip').write_bytes(b'changed')
        with self.assertRaisesRegex(line.LineError, 'changed after its download'):
            line.engine_embed(self.sd, self.application(), self.root)

    def signed_ipa(self, change=None):
        """The common Dolphin packaging fixture at build 803 plus the signed S2Arm helper, frameworks and identity."""
        self.download()
        app = self.application()
        line.engine_embed(self.sd, app, self.root)
        members = fixtures.complete_dolphin_packaging_members()
        for path in [name for name in members if name.endswith('Info.plist') and
                     (name == fixtures.APP + 'Info.plist' or '.appex/' in name)]:
            value = plistlib.loads(members[path])
            value.update(CFBundleVersion='803', CFBundleShortVersionString='0.0.8')
            members[path] = plistlib.dumps(value)
        prefix = fixtures.APP + 'PlugIns/' + line.HELPER + '/'
        members[prefix + 'Info.plist'] = plistlib.dumps(helper_info('803', '0.0.8'))
        members[prefix + line.HELPER_EXECUTABLE] = helper_image(signed=True)
        members[prefix + 's2arm-universal.js'] = self.script
        for name in line.ENGINE_FRAMEWORKS:
            for path, data in framework_files(name, signed=True).items():
                members[fixtures.APP + 'Frameworks/' + path] = data
        members[fixtures.APP + line.PACKAGED_IDENTITY] = (app / line.PACKAGED_IDENTITY).read_bytes()
        # The engine bridge: the system data as placed, and the signed Runner that links the bridge and S2ArmPrepare;
        # the legal bundle with the engine's notices.
        for folder in (line.SYSTEM_DATA, 'Legal'):
            for path in sorted((app / folder).rglob('*')):
                if path.is_file():
                    members[fixtures.APP + path.relative_to(app).as_posix()] = path.read_bytes()
        members[fixtures.APP + 'Runner'] = signed_runner(members[fixtures.APP + 'Runner'])
        if change:
            change(members)
        ipa = self.root / 'dist/NeoStation.ipa'
        ipa.parent.mkdir(exist_ok=True)
        with zipfile.ZipFile(ipa, 'w') as archive:
            for path, data in members.items():
                entry = zipfile.ZipInfo(path)
                entry.external_attr = 0o100755 << 16
                archive.writestr(entry, data)
        from rewind607_delivery import zip_payloads
        images = {name: record['fingerprint'] for name, record in zip_payloads(ipa).items()}
        (self.out / 'signed-payload-identity.json').write_text(json.dumps(dict(ipaSha256=sha(ipa.read_bytes()),
                                                                                images=images)))
        return ipa

    def test_check_the_signed_ipa(self):
        ipa = self.signed_ipa()
        result = line.engine_check_ipa(self.sd, ipa, self.root)
        self.assertEqual(result['result'], 'passed')
        self.assertIn(line.HELPER, result['distributionBundles'])
        self.assertEqual(set(result['images']), set(line.ENGINE_IMAGES))
        self.assertTrue(all(item['signed'] for item in result['frameworks'].values()))
        self.assertTrue(result['helper']['signed'])
        app = fixtures.APP
        changes = {
            'framework resource changed': lambda m: m.update({app + 'Frameworks/NS2Pro.framework/ns2pro.metallib': b'x'}),
            'framework payload changed': lambda m: m.update({app + 'Frameworks/NS2Pro.framework/NS2Pro': dylib(
                '@rpath/NS2Pro.framework/NS2Pro', ('/usr/lib/libc++.1.dylib',), signed=True)}),
            'framework unsigned': lambda m: m.update({app + 'Frameworks/NS2Pro.framework/NS2Pro': dylib(
                '@rpath/NS2Pro.framework/NS2Pro', ('/usr/lib/libSystem.B.dylib',
                                                   '/System/Library/Frameworks/Metal.framework/Metal'))}),
            'helper missing': lambda m: [m.pop(name) for name in list(m) if '/S2ArmJITHelper.appex/' in name],
            'identity missing': lambda m: m.pop(app + line.PACKAGED_IDENTITY),
            'engine framework missing': lambda m: m.pop(app + 'Frameworks/S2ArmEngine.framework/S2ArmEngine'),
            'helper script changed': lambda m: m.update({app + 'PlugIns/S2ArmJITHelper.appex/s2arm-universal.js': b'//'}),
        }
        for name, change in changes.items():
            with self.subTest(case=name):
                with self.assertRaises((line.LineError, ValueError, RuntimeError, KeyError)):
                    line.engine_check_ipa(self.sd, self.signed_ipa(change), self.root)
        ipa = self.signed_ipa()
        receipt = json.loads((self.out / 'signed-payload-identity.json').read_bytes())
        receipt['images']['Frameworks/NS2Pro.framework/NS2Pro'] = '0' * 64
        (self.out / 'signed-payload-identity.json').write_text(json.dumps(receipt))
        with self.assertRaisesRegex(line.LineError, 'signer receipt'):
            line.engine_check_ipa(self.sd, ipa, self.root)
        self.manifest['images']['added'] = []
        with self.assertRaisesRegex(line.LineError, 'does not declare the engine images'):
            line.engine_check_ipa(self.sd, ipa, self.root)

    def test_offline_verification_of_a_downloaded_ipa(self):
        import verify_downloaded_delivery_s2arm as launcher
        ipa = self.signed_ipa()
        work = self.root / 'work'
        (work / 'effective-tree' / line.HELPER_SCRIPT).parent.mkdir(parents=True)
        (work / 'effective-tree' / line.HELPER_SCRIPT).write_bytes(self.script)
        report = dict(execution=dict(source='a' * 40), manifest=dict(path='build-utils/delivery/803.json'))

        class Repo:
            def __init__(self, value):
                self.value = value

            def show(self, ref, path):
                return json.dumps(self.value).encode()
        self.assertEqual(launcher.engine_check(ipa, report, work, Repo(self.manifest))['result'], 'passed')
        with self.assertRaisesRegex(line.LineError, 'does not declare'):
            launcher.engine_check(ipa, report, work, Repo(dict(self.manifest, s2arm={})))
        common = self.root / 'common.ipa'
        with zipfile.ZipFile(common, 'w') as archive:
            archive.writestr(fixtures.APP + 'Info.plist', b'x')
        self.assertIsNone(launcher.engine_check(common, report, work, Repo(dict(self.manifest, s2arm={}))))
        with self.assertRaisesRegex(line.LineError, 'lacks'):
            launcher.engine_check(common, report, work, Repo(self.manifest))

    # --- The engine's licence and notice texts ---------------------------------------------------------------------

    def test_the_engine_notices_are_downloaded_with_the_engine(self):
        result = self.download()
        texts = licence_texts()
        self.assertEqual(result['licenses'], dict(manifest=line.ENGINE_LICENSE_MANIFEST, files=len(texts),
                                                  sha256=sha(texts[line.legal().S2ARM_NOTICE_MANIFEST])))
        self.assertEqual(line.tree_files(self.root / line.ENGINE_DOWNLOAD / line.ENGINE_LICENSES), texts)

    def test_the_engine_notices_of_the_producer_are_checked(self):
        gate = line.legal()
        texts = licence_texts()
        manifest_sha = sha(texts[gate.S2ARM_NOTICE_MANIFEST])
        changed = dict(texts, **{'Ryujinx/LICENSE.txt': b'another text\n'})
        cases = {
            'no notices': (dict(licences={}), 'license-sources.json with its texts'),
            'a text changed after its listing': (dict(licences=changed, identity=dict(licenses=dict(
                manifest=line.ENGINE_LICENSE_MANIFEST, sha256=manifest_sha, files=len(texts)))), 'differs from'),
            'a required text missing': (dict(licences=licence_texts(drop=('dav1d/COPYING',))), 'required texts missing'),
            'a text the manifest does not list': (dict(extra={line.ENGINE_LICENSES + 'Other/LICENSE': b'x\n'}),
                                                  'not in license-sources.json'),
            'the identity records another manifest': (dict(identity=dict(licenses=dict(
                manifest=line.ENGINE_LICENSE_MANIFEST, sha256='0' * 64, files=len(texts)))), 'not the recorded one'),
            'the identity records another count': (dict(identity=dict(licenses=dict(
                manifest=line.ENGINE_LICENSE_MANIFEST, sha256=manifest_sha, files=1))), 'not the recorded one'),
            'the identity records no notices': (dict(identity=dict(licenses=None)), 'does not record'),
            'texts of another S2Arm commit': (dict(licences=licence_texts(commit='1' * 40)), 'the engine of'),
            'a notice that is not the producer commit\'s': (dict(licences=licence_texts(
                notice=NOTICE.replace(b'RewindBox changed S2Arm', b'RewindBox kept S2Arm'))), 'of the producer commit'),
            'a notice without the statement': (dict(licences=licence_texts(notice=b'RewindBox notice.\n')),
                                               'does not state that no Nintendo data ships'),
        }
        for name, (keywords, message) in cases.items():
            with self.subTest(case=name):
                artifact, _ = producer_artifact(**keywords)
                with self.assertRaisesRegex(line.LineError, re.escape(message)):
                    self.download(artifact)
        identity = dict(licenses=dict(manifest='licenses/other.json', sha256=manifest_sha, files=len(texts)))
        with self.assertRaisesRegex(line.LineError, 'does not record'):
            self.download(producer_artifact(identity=identity)[0])
        self.download()   # and the artifact of the fixture itself is accepted

    def test_the_engine_notices_go_into_the_legal_bundle(self):
        self.download()
        app = self.application()
        line.engine_embed(self.sd, app, self.root)
        texts = licence_texts()
        self.assertEqual(line.tree_files(app / line.LEGAL_NOTICES), texts)
        self.assertEqual((app / 'Legal/NeoStation-NOTICE.md').read_text(), 'UPSTREAM NEOSTATION ATTRIBUTION fixture\n')
        identity = json.loads((app / line.PACKAGED_IDENTITY).read_bytes())
        self.assertEqual(identity['licenses'], dict(path=line.LEGAL_NOTICES, manifest='license-sources.json',
                                                    sha256=sha(texts['license-sources.json']), files=len(texts)))
        result = line.engine_check_app(self.sd, app, self.root)
        self.assertEqual(result['licenses'], dict(path=line.LEGAL_NOTICES, sha256=identity['licenses']['sha256'],
                                                  files=len(texts)))
        # The legal gate's own S2Arm conditional accepts the application the launcher made.
        self.assertEqual(line.legal().validate_s2arm_notices(app)['s2arm']['commit'], identity['sourceIdentity']['s2arm_commit'])
        tampering = {
            'a text changed': lambda app: (app / line.LEGAL_NOTICES / 'bcdec/LICENSE').write_bytes(b'changed\n'),
            'a text added': lambda app: (app / line.LEGAL_NOTICES / 'Other.txt').write_bytes(b'extra\n'),
            'a text removed': lambda app: (app / line.LEGAL_NOTICES / 'glslang/LICENSE.txt').unlink(),
            'the notices removed': lambda app: shutil.rmtree(app / line.LEGAL_NOTICES),
            'the record removed': lambda app: (app / line.PACKAGED_IDENTITY).write_text(json.dumps(dict(
                json.loads((app / line.PACKAGED_IDENTITY).read_bytes()), licenses=None))),
        }
        for name, tamper in tampering.items():
            with self.subTest(case=name):
                app = self.application()
                line.engine_embed(self.sd, app, self.root)
                tamper(app)
                with self.assertRaises(line.LineError):
                    line.engine_check_app(self.sd, app, self.root)

    def test_embed_refuses_without_the_legal_bundle_or_with_changed_notices(self):
        self.download()
        app = self.application()
        shutil.rmtree(app / 'Legal')
        with self.assertRaisesRegex(line.LineError, 'Legal/ is not in the application'):
            line.engine_embed(self.sd, app, self.root)
        self.assertFalse((app / line.PACKAGED_IDENTITY).exists())
        app = self.application()
        (app / line.LEGAL_NOTICES).mkdir()
        with self.assertRaisesRegex(line.LineError, 'Legal/S2Arm is already in the application'):
            line.engine_embed(self.sd, app, self.root)
        (self.root / line.ENGINE_DOWNLOAD / line.ENGINE_LICENSES / 'SPIRV-Cross/LICENSE').write_bytes(b'changed\n')
        with self.assertRaisesRegex(line.LineError, 'changed after their download'):
            line.engine_embed(self.sd, self.application(), self.root)

    def test_the_engine_notices_of_the_signed_ipa(self):
        result = line.engine_check_ipa(self.sd, self.signed_ipa(), self.root)
        self.assertEqual(result['licenses']['files'], len(licence_texts()))
        app = fixtures.APP + line.LEGAL_NOTICES + '/'
        changes = {
            'a text changed': lambda m: m.update({app + 'Ryujinx/LICENSE.txt': b'changed\n'}),
            'a text added': lambda m: m.update({app + 'Other/LICENSE': b'extra\n'}),
            'the notices removed': lambda m: [m.pop(name) for name in list(m) if name.startswith(app)],
        }
        for name, change in changes.items():
            with self.subTest(case=name):
                with self.assertRaisesRegex(line.LineError, line.LEGAL_NOTICES):
                    line.engine_check_ipa(self.sd, self.signed_ipa(change), self.root)

    def test_offline_an_ipa_without_the_engine_carries_no_engine_notices(self):
        import verify_downloaded_delivery_s2arm as launcher
        work = self.root / 'work'
        report = dict(execution=dict(source='a' * 40), manifest=dict(path='build-utils/delivery/803.json'))

        class Repo:
            def show(self, ref, path):
                return json.dumps(dict(build=803, s2arm={})).encode()
        common = self.root / 'common.ipa'
        with zipfile.ZipFile(common, 'w') as archive:
            archive.writestr(fixtures.APP + 'Info.plist', b'x')
            archive.writestr(fixtures.APP + 'Legal/S2Arm/S2Arm/LICENSE', b'x')
        with self.assertRaisesRegex(line.LineError, 'carries its notices'):
            launcher.engine_check(common, report, work, Repo())

    # --- The engine bridge: its preparation library and system data ---------------------------------------------

    def run_refusals(self, function, cases, errors=(line.LineError,)):
        for name, case in cases.items():
            with self.subTest(case=name):
                with self.assertRaises(errors):
                    function(**case)

    def producer_run_cases(self, api, artifact):
        """The refusals of a producer's run and artifact through the API (the engine's, for another producer)."""
        other_workflow = line.SYSDATA_WORKFLOW if api is prepare_api else line.PREPARE_WORKFLOW
        return {
            'failed run': dict(get=api(artifact, run=dict(conclusion='failure'))),
            'cancelled run': dict(get=api(artifact, run=dict(conclusion='cancelled'))),
            'other branch': dict(get=api(artifact, run=dict(head_branch='Claude'))),
            'other workflow': dict(get=api(artifact, run=dict(path=other_workflow))),
            'engine workflow': dict(get=api(artifact, run=dict(path=line.ENGINE_WORKFLOW))),
            'unfinished run': dict(get=api(artifact, run=dict(status='in_progress'))),
            'no artifact': dict(get=api(artifact, artifacts=lambda items: [])),
            'two artifacts': dict(get=api(artifact, artifacts=lambda items: items * 2)),
            'expired': dict(get=api(artifact, artifacts=lambda items: [dict(items[0], expired=True)])),
            'other run artifact': dict(get=api(artifact, artifacts=lambda items: [
                dict(items[0], workflow_run=dict(id=1, head_sha=PRODUCER))])),
            'other commit artifact': dict(get=api(artifact, artifacts=lambda items: [
                dict(items[0], workflow_run=dict(items[0]['workflow_run'], head_sha='8' * 40))])),
            'digest differs': dict(get=api(artifact, artifacts=lambda items: [dict(items[0], digest='sha256:' + '0' * 64)])),
            'size differs': dict(get=api(artifact, artifacts=lambda items: [dict(items[0], size_in_bytes=1)])),
            'commit not delivered': dict(repo=FakeRepo(ancestor=False)),
        }

    def test_prepare_download_authenticates_the_producer_run_and_its_library(self):
        result = self.prepare()
        producer = result['producer']
        self.assertEqual((producer['workflow'], producer['run'], producer['source'], producer['branch']),
                         (line.PREPARE_WORKFLOW, PREPARE_RUN, PRODUCER, line.DELIVERY_BRANCH))
        self.assertEqual((producer['artifact']['id'], producer['artifact']['name']), (PREPARE_ARTIFACT_ID,
                                                                                     'S2ArmPrepare-' + PRODUCER))
        self.assertEqual(result['zip'], self.prepare_zip)
        self.assertEqual(result['xcframework']['library'], dict(path='ios-arm64/' + line.PREPARE_LIBRARY,
                                                                sha256=sha(LIBRARY), bytes=len(LIBRARY)))
        self.assertEqual(result['xcframework']['headers'], ['s2arm_pack.h', 's2arm_prepare.h'])
        self.assertEqual(result['identity']['s2arm'], json.loads(PIN)['s2arm']['commit'])
        for name in line.PREPARE_MEMBERS:
            self.assertTrue((self.root / line.PREPARE_DOWNLOAD / name).is_file(), name)
        self.assertEqual(json.loads((self.out / 's2arm-prepare-download.json').read_bytes())['result'], 'authenticated')

    def test_prepare_download_refusals(self):
        self.run_refusals(self.prepare, self.producer_run_cases(prepare_api, self.prepare_artifact),
                          (line.LineError, KeyError))
        pin = json.loads(PIN)
        self.run_refusals(self.prepare, {
            'pin differs': dict(repo=FakeRepo(files=dict(PATCHES, **{'tools/s2arm_prototype/pin.json': json.dumps(
                dict(pin, s2arm={'commit': '1' * 40})).encode()}))),
            'pinned dependencies differ': dict(repo=FakeRepo(files=dict(PATCHES, **{'tools/s2arm_prototype/pin.json': json.dumps(
                dict(pin, dependencies=dict(pin['dependencies'], lz4=dict(pin['dependencies']['lz4'], sha256='0' * 64)))
            ).encode()}))),
        })
        lz = line.PREPARE_LIBRARY
        library_entry = dict(BinaryPath=lz, HeadersPath='Headers', LibraryIdentifier='ios-arm64', LibraryPath=lz,
                             SupportedArchitectures=['arm64'], SupportedPlatform='ios')
        devices = 'for iOS arm64 devices'
        artifacts = {   # case: (artifact, the message of the check that must refuse it)
            'sha256.txt names another archive': (dict(sums=f'{"0" * 64}  {line.PREPARE_ZIP}\n{sha(LIBRARY)}  {lz}\n'.encode()),
                                                 'sha256.txt must give'),
            'sha256.txt lacks the library': (dict(sums=f'{{zip}}  {line.PREPARE_ZIP}\n'.encode()), 'sha256.txt must give'),
            'sha256.txt names another file': (dict(sums=f'{{zip}}  {line.PREPARE_ZIP}\n{sha(LIBRARY)}  {lz}\n'
                                                        f'{"1" * 64}  other.a\n'.encode()), 'sha256.txt must give'),
            'sha256.txt malformed': (dict(sums=b'not a listing\n'), 'malformed or repeated'),
            'identity of another commit': (dict(identity=dict(source='8' * 40)), 'another component or commit'),
            'identity of another S2Arm': (dict(identity=dict(s2arm='1' * 40)), 'the producer commit pins'),
            'identity of other dependencies': (dict(identity=dict(dependencies={})), 'the producer commit pins'),
            'identity digests differ from sha256.txt': (dict(identity=dict(sha256={})), 'digests differ from sha256.txt'),
            'identity of another component': (dict(identity=dict(component='Other.xcframework')),
                                              'another component or commit'),
            'identity without Xcode': (dict(identity=dict(xcode=' ')), 'names no Xcode'),
            'identity Xcode not a string': (dict(identity=dict(xcode=None)), 'names no Xcode'),
            'extra member': (dict(extra={'notes.txt': b'x'}), 'must hold exactly'),
            'missing member': (dict(drop=(line.PREPARE_UNDEFINED,)), 'must hold exactly'),
            'entry points left undefined': (dict(undefined=b'_free\n_rb_s2arm_prepare_code\n'), 'entry points undefined'),
            'library differs from sha256.txt': (dict(library=b'!<arch>\nanother library\n'), 'measured'),
            'not a static library': (dict(files=xcframework(library=dylib('@rpath/libS2ArmPrepare.dylib'))),
                                     'not a static library'),
            'simulator slice': (dict(files=xcframework(entry=dict(SupportedPlatformVariant='simulator'))), devices),
            'other architectures': (dict(files=xcframework(entry=dict(SupportedArchitectures=['arm64', 'x86_64']))),
                                    devices),
            'macOS library': (dict(files=xcframework(entry=dict(SupportedPlatform='macos'))), devices),
            'another library name': (dict(files=xcframework(entry=dict(LibraryPath='libOther.a'))), devices),
            'two libraries': (dict(files=xcframework(info=dict(AvailableLibraries=[library_entry, library_entry]))),
                              'exactly one library'),
            'not an xcframework': (dict(files=xcframework(info=dict(CFBundlePackageType='FMWK'))), 'exactly one library'),
            'extra library': (dict(files=xcframework(extra={'S2ArmPrepare.xcframework/ios-arm64/libOther.a': LIBRARY})),
                              'holds other files'),
            'nested header folder': (dict(files=xcframework(extra={
                'S2ArmPrepare.xcframework/ios-arm64/Headers/sub/x.h': b'/* */'})), 'holds other files'),
            'member outside the xcframework': (dict(files=dict(xcframework(), **{'Other/file': b'x'})), 'member outside'),
            'dynamic image beside it': (dict(files=xcframework(extra={
                'S2ArmPrepare.xcframework/ios-arm64/Headers/x.h': dylib('@rpath/X.framework/X')})), 'holds a Mach-O image'),
        }
        for name, (keywords, message) in artifacts.items():
            with self.subTest(case=name):
                # The manifest names each archive, so that the check of the case is the one that refuses it.
                files = keywords.get('files')
                archive = zipped(xcframework(library=keywords.get('library', LIBRARY)) if files is None else files)
                keywords = {key: value for key, value in keywords.items() if key not in ('files', 'library')}
                if isinstance(keywords.get('sums'), bytes):
                    keywords['sums'] = keywords['sums'].replace(b'{zip}', sha(archive).encode())
                artifact, digest = prepare_producer(archive=archive, **keywords)
                self.assertEqual(digest, sha(archive))
                self.manifest['s2arm']['prepare'] = dict(self.manifest['s2arm']['prepare'], zip=digest)
                with self.assertRaisesRegex(line.LineError, message):
                    self.prepare(artifact)
        linked = zipped(xcframework(), symlink='S2ArmPrepare.xcframework/ios-arm64/link')
        artifact, digest = prepare_producer(archive=linked)
        self.manifest['s2arm']['prepare'] = dict(self.manifest['s2arm']['prepare'], zip=digest)
        with self.assertRaisesRegex(line.LineError, 'symbolic link'):
            self.prepare(artifact)
        self.manifest['s2arm']['prepare'] = dict(self.manifest['s2arm']['prepare'], zip=self.prepare_zip)
        self.assertEqual(self.prepare()['result'], 'authenticated', 'the refusals above leave the good artifact accepted')
        other, _ = prepare_producer(files=xcframework(extra={'S2ArmPrepare.xcframework/ios-arm64/Headers/x.h': b'/**/'}))
        with self.assertRaisesRegex(line.LineError, 'differs from the manifest'):
            self.prepare(other)
        for spec in (None, dict(workflow=line.PREPARE_WORKFLOW, run=0, zip=self.prepare_zip),
                     dict(workflow=line.PREPARE_WORKFLOW, run=PREPARE_RUN, zip=self.prepare_zip.upper()),
                     dict(workflow=line.PREPARE_WORKFLOW, run=str(PREPARE_RUN), zip=self.prepare_zip),
                     dict(workflow=line.ENGINE_WORKFLOW, run=PREPARE_RUN, zip=self.prepare_zip),
                     dict(workflow=line.PREPARE_WORKFLOW, run=PREPARE_RUN, zip=self.prepare_zip, tree=self.tree)):
            with self.subTest(spec=spec):
                self.manifest['s2arm'] = dict(self.manifest['s2arm'], prepare=spec)
                if spec is None:
                    del self.manifest['s2arm']['prepare']
                with self.assertRaises(line.LineError):
                    self.prepare()

    def test_prepare_install_puts_the_library_where_the_podspec_vendors_it(self):
        for path, data in xcframework().items():
            self.assertEqual((self.root / line.BRIDGE_FRAMEWORKS / path).read_bytes(), data, path)
        record = json.loads((self.out / 's2arm-prepare-install.json').read_bytes())
        self.assertEqual((record['result'], record['path'], record['zip']),
                         ('installed', 'packages/s2arm_engine_bridge/ios/Frameworks/S2ArmPrepare.xcframework',
                          self.prepare_zip))
        self.assertEqual(record['library']['sha256'], sha(LIBRARY))
        self.assertEqual(record['files'], line.installed_xcframework(self.root))
        # The committed podspec vendors exactly that path; the package's .gitignore keeps what is installed out of Git.
        self.assertEqual(line.check_podspec(ROOT), sha((ROOT / line.BRIDGE_PODSPEC).read_bytes()))
        self.assertIn('/ios/Frameworks/', (ROOT / 'packages/s2arm_engine_bridge/.gitignore').read_text().splitlines())
        ignored = subprocess.run(['git', 'check-ignore', '-q', line.BRIDGE_FRAMEWORKS + '/S2ArmPrepare.xcframework/Info.plist'],
                                 cwd=ROOT)
        self.assertEqual(ignored.returncode, 0, 'the installed xcframework would show in git status')
        self.assertEqual(subprocess.run(['git', 'ls-files', line.BRIDGE_FRAMEWORKS], cwd=ROOT, capture_output=True,
                                        text=True, check=True).stdout, '')
        with self.assertRaisesRegex(line.LineError, 'not empty'):
            line.prepare_install(self.sd, self.root)
        shutil.rmtree(self.root / line.BRIDGE_FRAMEWORKS)
        downloaded = self.root / line.PREPARE_DOWNLOAD / line.PREPARE_ZIP
        original = downloaded.read_bytes()
        downloaded.write_bytes(b'changed')
        with self.assertRaisesRegex(line.LineError, 'changed after its download'):
            line.prepare_install(self.sd, self.root)
        downloaded.write_bytes(original)
        podspec = (self.root / line.BRIDGE_PODSPEC).read_text()
        for changed in (podspec.replace(line.BRIDGE_VENDORED, ''),
                        podspec.replace("'Frameworks/S2ArmPrepare.xcframework'", "'Frameworks/Other.xcframework'"),
                        podspec.replace(line.BRIDGE_VENDORED, line.BRIDGE_VENDORED + "\n  s.vendored_libraries = 'x.a'")):
            with self.subTest(podspec=changed[-80:]):
                (self.root / line.BRIDGE_PODSPEC).write_text(changed)
                with self.assertRaisesRegex(line.LineError, 'must vendor'):
                    line.prepare_install(self.sd, self.root)
        (self.root / line.BRIDGE_PODSPEC).write_text(podspec)
        self.manifest['build'] = 804
        with self.assertRaisesRegex(line.LineError, 'not this build'):
            line.prepare_install(self.sd, self.root)
        self.manifest['build'] = 803
        self.assertEqual(line.prepare_install(self.sd, self.root)['result'], 'installed')

    def test_sysdata_download_checks_every_file_against_its_listing(self):
        result = self.sysdata()
        producer = result['producer']
        self.assertEqual((producer['workflow'], producer['run'], producer['artifact']['name']),
                         (line.SYSDATA_WORKFLOW, SYSDATA_RUN, 's2arm-sysdata-macOS-' + PRODUCER))
        tree = sysdata_tree()
        self.assertEqual((result['tree'], result['files'], result['fonts']), (self.tree, len(tree), 2))
        self.assertEqual(result['bytes'], sum(map(len, tree.values())))
        self.assertEqual(result['licences'], sorted(path for path in tree if path.startswith('licenses/')))
        self.assertEqual(result['sources']['s2arm'], json.loads(PIN)['s2arm']['commit'])
        for path, data in dict(tree, SHA256SUMS=sums_of(tree)).items():
            self.assertEqual((self.root / line.SYSDATA_DOWNLOAD / 'tree' / path).read_bytes(), data, path)

    def test_sysdata_download_refusals(self):
        self.run_refusals(self.sysdata, self.producer_run_cases(sysdata_api, self.sysdata_artifact),
                          (line.LineError, KeyError))
        tree = sysdata_tree()

        def without(*names):
            return {path: data for path, data in tree.items() if path not in names}
        listing = 'differs from its SHA256SUMS'
        trees = {   # case: (artifact, the message of the check that must refuse it)
            'missing file': (dict(tree=tree, drop=('licenses/fonts/MANIFEST.tsv',)), listing),
            'extra file': (dict(tree=tree, extra={'systemdata/0100000000000802/extra.bin': b'x'}), listing),
            'changed file': (dict(tree=dict(tree, **{'systemdata/fonts/nintendo_ext_003.bfttf': b'other'}),
                                  sums=sums_of(tree)), 'differ from SHA256SUMS'),
            'listing malformed': (dict(tree=tree, sums=b'not a listing\n'), 'malformed or repeated'),
            'listing repeats a path': (dict(tree=tree, sums=sums_of(tree) + sums_of(dict(list(tree.items())[:1]))),
                                       'malformed or repeated'),
            'listing without newline': (dict(tree=tree, sums=sums_of(tree)[:-1]), 'not newline-terminated'),
            'SOURCES.tsv of another S2Arm': (dict(tree=dict(tree, **{'SOURCES.tsv': tree['SOURCES.tsv'].replace(
                json.loads(PIN)['s2arm']['commit'].encode(), b'1' * 40)})), 'the producer commit pins'),
            'SOURCES.tsv without header': (dict(tree=dict(tree, **{'SOURCES.tsv': tree['SOURCES.tsv'].split(b'\n', 1)[1]})),
                                           'no part/source header'),
            'no SOURCES.tsv': (dict(tree=without('SOURCES.tsv')), 'has no SOURCES.tsv'),
            'no time zone licence': (dict(tree=without('licenses/tzdata/LICENSE')), 'lacks the time zone licence'),
            'no open font licence': (dict(tree=without('licenses/fonts/OFL-NotoSans.txt',
                                                       'licenses/fonts/OFL-NotoSansCJK.txt')), 'open font licence'),
            'no shared font': (dict(tree=without('systemdata/fonts/nintendo_udsg-r_std_003.bfttf',
                                                 'systemdata/fonts/nintendo_ext_003.bfttf')), 'no shared font'),
            'Mach-O file': (dict(tree=dict(tree, **{'systemdata/0100000000000802/code': dylib('@rpath/X.framework/X')})),
                            'Mach-O image'),
            'hidden file': (dict(tree=dict(tree, **{'systemdata/.DS_Store': b'x'})), 'unexpected path'),
            'path outside the tree': (dict(tree=dict(tree, **{'other/file': b'x'})), 'unexpected path'),
            'bundle-like folder': (dict(tree=dict(tree, **{'systemdata/X.framework/X': b'x'})), 'unexpected path'),
            'paths that differ by case': (dict(tree=dict(tree, **{'systemdata/010000000000080E/zoneinfo/utc': b'x'})),
                                          'differ only by case'),
            'symbolic link': (dict(tree=tree, symlink='systemdata/link'), 'symbolic link'),
        }
        for name, (keywords, message) in trees.items():
            with self.subTest(case=name):
                artifact, digest = sysdata_producer(**keywords)
                self.manifest['s2arm']['sysdata'] = dict(self.manifest['s2arm']['sysdata'], tree=digest)
                with self.assertRaisesRegex(line.LineError, message):
                    self.sysdata(artifact)
        self.manifest['s2arm']['sysdata'] = dict(self.manifest['s2arm']['sysdata'], tree=self.tree)
        other, _ = sysdata_producer(tree=dict(tree, **{'licenses/fonts/MANIFEST.tsv': b'other'}))
        with self.assertRaisesRegex(line.LineError, 'not the one the manifest names'):
            self.sysdata(other)
        for spec in (None, dict(workflow=line.SYSDATA_WORKFLOW, run=0, tree=self.tree),
                     dict(workflow=line.SYSDATA_WORKFLOW, run=SYSDATA_RUN, tree=self.tree[:-1]),
                     dict(workflow=line.PREPARE_WORKFLOW, run=SYSDATA_RUN, tree=self.tree),
                     dict(workflow=line.SYSDATA_WORKFLOW, run=SYSDATA_RUN, zip=self.tree)):
            with self.subTest(spec=spec):
                self.manifest['s2arm'] = dict(self.manifest['s2arm'], sysdata=spec)
                if spec is None:
                    del self.manifest['s2arm']['sysdata']
                with self.assertRaises(line.LineError):
                    self.sysdata()

    def test_sysdata_embed_places_the_downloaded_tree_unchanged(self):
        app = self.application(system_data=False)
        result = line.sysdata_embed(self.sd, app, self.root)
        self.assertEqual((result['path'], result['tree'], result['files']), (line.SYSTEM_DATA, self.tree,
                                                                              len(sysdata_tree())))
        self.assertEqual(line.tree_files(app / line.SYSTEM_DATA), dict(sysdata_tree(), SHA256SUMS=sums_of(sysdata_tree())))
        self.assertEqual(sorted(path.name for path in (app / line.SYSTEM_DATA).iterdir()),
                         ['SHA256SUMS', 'SOURCES.tsv', 'licenses', 'systemdata'])
        with self.assertRaisesRegex(line.LineError, 'already'):
            line.sysdata_embed(self.sd, app, self.root)
        downloaded = self.root / line.SYSDATA_DOWNLOAD / 'tree'
        changes = {
            'file changed after the download': lambda: (downloaded / 'licenses/tzdata/LICENSE').write_bytes(b'x'),
            'file added after the download': lambda: (downloaded / 'systemdata/extra').write_bytes(b'x'),
            'file removed after the download': lambda: (downloaded / 'SOURCES.tsv').unlink(),
        }
        for name, change in changes.items():
            with self.subTest(case=name):
                self.sysdata()
                change()
                app = self.application(system_data=False)
                with self.assertRaises(line.LineError):
                    line.sysdata_embed(self.sd, app, self.root)
                self.assertFalse((app / line.SYSTEM_DATA).exists(), 'nothing is placed from a changed tree')
        self.sysdata()
        self.manifest['build'] = 804
        with self.assertRaisesRegex(line.LineError, 'not this build'):
            line.sysdata_embed(self.sd, self.application(system_data=False), self.root)

    def test_engine_embed_records_and_requires_the_bridge(self):
        self.download()
        app = self.application()
        line.engine_embed(self.sd, app, self.root)
        identity = json.loads((app / line.PACKAGED_IDENTITY).read_bytes())
        prepare, system, bridge = identity['prepare'], identity['systemData'], identity['bridge']
        self.assertEqual((prepare['workflow'], prepare['run'], prepare['zip'], prepare['linkedInto']),
                         (line.PREPARE_WORKFLOW, PREPARE_RUN, self.prepare_zip, 'Runner'))
        self.assertEqual((prepare['library']['sha256'], prepare['installedAt']),
                         (sha(LIBRARY), 'packages/s2arm_engine_bridge/ios/Frameworks/S2ArmPrepare.xcframework'))
        self.assertEqual(prepare['producer']['artifact']['name'], 'S2ArmPrepare-' + PRODUCER)
        self.assertEqual((system['workflow'], system['run'], system['tree'], system['path'], system['files']),
                         (line.SYSDATA_WORKFLOW, SYSDATA_RUN, self.tree, line.SYSTEM_DATA, len(sysdata_tree())))
        self.assertIn('licenses/tzdata/LICENSE', system['licences'])
        self.assertEqual((bridge['pluginClass'], bridge['directChain'], bridge['registrant']['sha256']),
                         ('S2ArmEngineBridgePlugin', CHAIN.decode(), sha(REGISTRANT.encode())))
        self.assertEqual((bridge['runnerDefines'], bridge['runnerExports']), (list(line.RUNNER_DEFINES),
                                                                              ['_rb_s2arm_engine_loaded']))
        self.assertIs(identity['physicalDeviceTested'], False)
        installed = self.root / line.BRIDGE_FRAMEWORKS / 'S2ArmPrepare.xcframework/ios-arm64/Headers/s2arm_pack.h'
        registrant = self.root / line.BRIDGE_REGISTRANT
        refusals = {
            'system data not placed': (dict(system_data=False), None, 'Missing'),
            'system data changed after its placement': (
                {}, lambda app: (app / line.SYSTEM_DATA / 'SOURCES.tsv').write_bytes(b'x'), 'differ from SHA256SUMS'),
            'library changed after its installation': ({}, lambda app: installed.write_bytes(b'/* other */'),
                                                       'after its installation'),
            'registrant without the bridge': ({}, lambda app: registrant.write_text(REGISTRANT.replace(
                line.BRIDGE_REGISTRATION, '')), 'does not register'),
        }
        for name, (keywords, change, message) in refusals.items():
            with self.subTest(case=name):
                saved = installed.read_bytes(), registrant.read_bytes()
                app = self.application(**keywords)
                if change:
                    change(app)
                with self.assertRaisesRegex(line.LineError, message):
                    line.engine_embed(self.sd, app, self.root)
                self.assertFalse((app / line.PACKAGED_IDENTITY).exists() or (app / 'Frameworks/NS2Pro.framework').exists(),
                                 'nothing is embedded when the bridge is refused')
                installed.write_bytes(saved[0])
                registrant.write_bytes(saved[1])
        for chain, message in ((None, 'has no S2ArmDirectChain.txt'), (b'not a chain', 'not a direct shader chain'),
                               (b'0be3f28548fd0', 'not a direct shader chain')):
            with self.subTest(chain=chain):
                files = {name: framework_files(name) for name in line.ENGINE_FRAMEWORKS}
                member = f'S2ArmEngine.framework/{line.DIRECT_CHAIN}'
                if chain is None:
                    files['S2ArmEngine'].pop(member)
                else:
                    files['S2ArmEngine'][member] = chain
                artifact, zips = producer_artifact(zips={name: zipped(value) for name, value in files.items()})
                self.manifest['s2arm']['engine'] = dict(self.manifest['s2arm']['engine'], zips=zips)
                self.download(artifact)
                with self.assertRaisesRegex(line.LineError, message):
                    line.engine_embed(self.sd, self.application(), self.root)
        self.manifest['s2arm']['engine'] = dict(self.manifest['s2arm']['engine'], zips=self.zips)
        self.download()
        del self.manifest['s2arm']['prepare']
        with self.assertRaisesRegex(line.LineError, 'declares no S2Arm preparation library'):
            line.engine_embed(self.sd, self.application(), self.root)

    def test_the_generated_registrant_registers_the_bridge_once(self):
        registrant = self.root / line.BRIDGE_REGISTRANT
        self.assertEqual(line.check_registrant(self.root), dict(path=line.BRIDGE_REGISTRANT, sha256=sha(REGISTRANT.encode()),
                                                                registers='S2ArmEngineBridgePlugin'))
        spaced = REGISTRANT.replace(line.BRIDGE_REGISTRATION, '[S2ArmEngineBridgePlugin  registerWithRegistrar: [registry '
                                                              'registrarForPlugin:@"S2ArmEngineBridgePlugin"] ];')
        registrant.write_text(spaced)
        self.assertEqual(line.check_registrant(self.root)['sha256'], sha(spaced.encode()))
        for text in (REGISTRANT.replace(line.BRIDGE_REGISTRATION, ''), REGISTRANT + line.BRIDGE_REGISTRATION + '\n',
                     REGISTRANT.replace('registrarForPlugin:@"S2ArmEngineBridgePlugin"', 'registrarForPlugin:@"Other"'),
                     REGISTRANT.replace('[S2ArmEngineBridgePlugin registerWithRegistrar', '[S2ArmEngineBridge registerWithRegistrar')):
            with self.subTest(registrant=text[-160:]):
                registrant.write_text(text)
                with self.assertRaisesRegex(line.LineError, 'does not register'):
                    line.check_registrant(self.root)
        registrant.unlink()
        with self.assertRaisesRegex(line.LineError, 'Missing generated plugin registrant'):
            line.check_registrant(self.root)

    def test_the_bridge_is_checked_in_the_built_application(self):
        self.download()
        app = self.application()
        line.engine_embed(self.sd, app, self.root)
        bridge = line.engine_check_app(self.sd, app, self.root)['bridge']
        self.assertEqual((bridge['systemData']['tree'], bridge['directChain'], bridge['runner']['exports']),
                         (self.tree, CHAIN.decode(), ['_rb_s2arm_engine_loaded']))
        self.assertEqual(bridge['registrant']['registers'], 'S2ArmEngineBridgePlugin')
        defines = [name for name in line.RUNNER_DEFINES if name != '_rb_s2arm_prepare_code']
        chain = 'Frameworks/S2ArmEngine.framework/' + line.DIRECT_CHAIN
        tampering = {
            'system data file changed': (lambda app: (app / line.SYSTEM_DATA / 'licenses/tzdata/LICENSE').write_bytes(b'x'),
                                         'differ from SHA256SUMS'),
            'system data file added': (lambda app: (app / line.SYSTEM_DATA / 'systemdata/extra').write_bytes(b'x'),
                                       'differs from its SHA256SUMS'),
            'system data file removed': (lambda app: (app / line.SYSTEM_DATA / 'licenses/fonts/OFL-NotoSans.txt').unlink(),
                                         'differs from its SHA256SUMS'),
            'system data listing changed': (lambda app: (app / line.SYSTEM_DATA / 'SHA256SUMS').write_bytes(b''),
                                            'not the one the manifest names'),
            'direct chain removed': (lambda app: (app / chain).unlink(), 'differ from the packaged identity|is missing'),
            'direct chain changed': (lambda app: (app / chain).write_bytes(b'0123\n'), 'differs from the producer archive|'
                                                                                         'not the one embedded'),
            'registrant changed after the embedding': (lambda app: (self.root / line.BRIDGE_REGISTRANT).write_text(
                REGISTRANT + '// regenerated\n'), 'changed after the embedding'),
            'registrant without the bridge': (lambda app: (self.root / line.BRIDGE_REGISTRANT).write_text(
                REGISTRANT.replace(line.BRIDGE_REGISTRATION, '')), 'does not register'),
            'preparation entry point not linked': (lambda app: (app / 'Runner').write_bytes(runner_image(
                defined=defines)), 'does not define'),
            'bridge plugin not linked': (lambda app: (app / 'Runner').write_bytes(runner_image(
                defined=line.RUNNER_DEFINES[1:])), 'does not define'),
            'rb_s2arm symbol left undefined': (lambda app: (app / 'Runner').write_bytes(runner_image(
                defined=defines, undefined=['_rb_s2arm_prepare_code'])), 'does not define|undefined'),
            'undefined import of the flag': (lambda app: (app / 'Runner').write_bytes(runner_image(
                undefined=['_rb_s2arm_engine_loaded'])), 'undefined'),
            'flag not exported': (lambda app: (app / 'Runner').write_bytes(runner_image(exports=['_main'])),
                                  'does not export'),
            'bridge packaged as a framework': (lambda app: nested(
                app / 'Frameworks/s2arm_engine_bridge.framework/s2arm_engine_bridge', b'x'), 'packaged on its own|differ'),
            'preparation library packaged': (lambda app: nested(app / 'Frameworks/libS2ArmPrepare.a', LIBRARY),
                                             'packaged on its own'),
        }
        for name, (tamper, message) in tampering.items():
            with self.subTest(case=name):
                (self.root / line.BRIDGE_REGISTRANT).write_text(REGISTRANT)
                app = self.application()
                line.engine_embed(self.sd, app, self.root)
                tamper(app)
                with self.assertRaisesRegex(line.LineError, message):
                    line.engine_check_app(self.sd, app, self.root)
        (self.root / line.BRIDGE_REGISTRANT).write_text(REGISTRANT)
        app = self.application()
        line.engine_embed(self.sd, app, self.root)
        self.manifest['s2arm']['sysdata'] = dict(self.manifest['s2arm']['sysdata'], tree='0' * 64)
        with self.assertRaisesRegex(line.LineError, 'is not the manifest\'s system data'):
            line.engine_check_app(self.sd, app, self.root)
        self.manifest['s2arm']['sysdata'] = dict(self.manifest['s2arm']['sysdata'], tree=self.tree)
        self.manifest['s2arm']['prepare'] = dict(self.manifest['s2arm']['prepare'], run=PREPARE_RUN + 1)
        with self.assertRaisesRegex(line.LineError, 'is not the manifest\'s preparation library'):
            line.engine_check_app(self.sd, app, self.root)

    def test_the_bridge_is_checked_in_the_signed_ipa(self):
        result = line.engine_check_ipa(self.sd, self.signed_ipa(), self.root)
        self.assertEqual((result['bridge']['systemData']['tree'], result['bridge']['directChain']),
                         (self.tree, CHAIN.decode()))
        self.assertEqual(result['bridge']['runner']['defines'], list(line.RUNNER_DEFINES))
        app = fixtures.APP
        data = app + line.SYSTEM_DATA + '/'

        def folders(members):   # what /usr/bin/zip -qry writes besides the files
            for name in [name for name in members if name.startswith(data)]:
                parts = name[len(app):].split('/')[:-1]
                for depth in range(1, len(parts) + 1):
                    members.setdefault(app + '/'.join(parts[:depth]) + '/', b'')
        listed = self.signed_ipa(folders)
        with zipfile.ZipFile(listed) as archive:
            self.assertIn(data + 'systemdata/fonts/', archive.namelist())
        self.assertEqual(line.engine_check_ipa(self.sd, listed, self.root)['bridge']['systemData']['tree'], self.tree)
        chain = app + 'Frameworks/S2ArmEngine.framework/' + line.DIRECT_CHAIN
        defines = [name for name in line.RUNNER_DEFINES if name != '_rb_s2arm_resource_pack']
        changes = {
            'system data file changed': (lambda m: m.update({data + 'SOURCES.tsv': b'x'}), 'differ from SHA256SUMS'),
            'system data file removed': (lambda m: m.pop(data + 'licenses/tzdata/LICENSE'), 'differs from its SHA256SUMS'),
            'system data file added': (lambda m: m.update({data + 'systemdata/extra': b'x'}), 'differs from its SHA256SUMS'),
            'system data absent': (lambda m: [m.pop(name) for name in list(m) if name.startswith(data)],
                                   f'has no {line.SYSDATA_SUMS}'),
            'direct chain removed': (lambda m: m.pop(chain), 'differ from the packaged identity|is missing'),
            'preparation entry point not linked': (lambda m: m.update({app + 'Runner': signed_runner(
                m[app + 'Runner'], defined=defines)}), 'does not define'),
            'rb_s2arm symbol left undefined': (lambda m: m.update({app + 'Runner': signed_runner(
                m[app + 'Runner'], undefined=['_rb_s2arm_caps'])}), 'undefined'),
            'flag not exported': (lambda m: m.update({app + 'Runner': signed_runner(m[app + 'Runner'], exports=['_main'])}),
                                  'does not export'),
            'bridge packaged as a framework': (lambda m: m.update({
                app + 'Frameworks/s2arm_engine_bridge.framework/Info.plist': b'x'}), 'packaged on its own'),
        }
        for name, (change, message) in changes.items():
            with self.subTest(case=name):
                with self.assertRaisesRegex(line.LineError, message):
                    line.engine_check_ipa(self.sd, self.signed_ipa(change), self.root)
        ipa = self.signed_ipa()
        self.manifest['s2arm']['prepare'] = dict(self.manifest['s2arm']['prepare'], zip='0' * 64)
        with self.assertRaisesRegex(line.LineError, 'is not the manifest\'s preparation library'):
            line.engine_check_ipa(self.sd, ipa, self.root)

    def test_offline_verification_of_the_engine_bridge(self):
        import verify_downloaded_delivery_s2arm as launcher
        ipa = self.signed_ipa()
        work = self.root / 'work'
        (work / 'effective-tree' / line.HELPER_SCRIPT).parent.mkdir(parents=True)
        (work / 'effective-tree' / line.HELPER_SCRIPT).write_bytes(self.script)
        report = dict(execution=dict(source='a' * 40), manifest=dict(path='build-utils/delivery/803.json'))

        class Repo:
            def __init__(self, value):
                self.value = value

            def show(self, ref, path):
                return json.dumps(self.value).encode()
        result = launcher.engine_check(ipa, report, work, Repo(self.manifest))
        self.assertEqual((result['bridge']['prepare'], result['bridge']['systemData']['tree']),
                         (dict(run=PREPARE_RUN, zip=self.prepare_zip), self.tree))
        s2arm = self.manifest['s2arm']
        refused = {
            'manifest without the preparation library': (dict(s2arm, prepare=None), 'declares no S2Arm preparation'),
            'manifest without the system data': (dict(s2arm, sysdata=None), 'declares no S2Arm system data'),
            'another preparation run': (dict(s2arm, prepare=dict(s2arm['prepare'], run=PREPARE_RUN + 1)),
                                        'preparation library'),
            'another system data tree': (dict(s2arm, sysdata=dict(s2arm['sysdata'], tree='0' * 64)), 'system data'),
        }
        for name, (value, message) in refused.items():
            with self.subTest(case=name):
                value = {key: item for key, item in value.items() if item is not None}
                with self.assertRaisesRegex(line.LineError, message):
                    launcher.engine_check(ipa, report, work, Repo(dict(self.manifest, s2arm=value)))
        # Offline there is no embedding record to bind the identity's digest: what it records is checked against the IPA.
        member = fixtures.APP + line.PACKAGED_IDENTITY

        def identity(edit):
            def change(members):
                value = json.loads(members[member])
                edit(value)
                members[member] = json.dumps(value).encode()
            return change
        edited = {
            'identity records another direct chain': (identity(lambda v: v['bridge'].update(directChain='0' * 12)),
                                                      'not the one embedded'),
            'identity records another system data tree': (identity(lambda v: v['systemData'].update(files=1)),
                                                          'not the tree embedded'),
            'identity without the bridge': (identity(lambda v: v.pop('bridge')), 'does not record the engine bridge'),
            'identity without a registration': (identity(lambda v: v['bridge'].update(registrant={})),
                                                'records no registration'),
        }
        for name, (change, message) in edited.items():
            with self.subTest(case=name):
                with self.assertRaisesRegex(line.LineError, message):
                    launcher.engine_check(self.signed_ipa(change), report, work, Repo(self.manifest))
        common = self.root / 'common.ipa'
        with zipfile.ZipFile(common, 'w') as archive:
            archive.writestr(fixtures.APP + 'Info.plist', b'x')
            archive.writestr(fixtures.APP + line.SYSTEM_DATA + '/SHA256SUMS', b'')
        with self.assertRaisesRegex(line.LineError, 'carries its bridge'):
            launcher.engine_check(common, report, work, Repo(dict(self.manifest, s2arm={})))
        plain = self.root / 'plain.ipa'
        with zipfile.ZipFile(plain, 'w') as archive:
            archive.writestr(fixtures.APP + 'Info.plist', b'x')
        for key in ('prepare', 'sysdata'):
            with self.subTest(declared=key):
                with self.assertRaisesRegex(line.LineError, 'carries its bridge'):
                    launcher.engine_check(plain, report, work, Repo(dict(self.manifest, s2arm={key: s2arm[key]})))


def signed_runner(common, **keywords):
    """The packaged Runner of the common fixture (its entitlements, dylibs and rpaths) linking the engine bridge."""
    return runner_image(entitlements=distribution_module().embedded_entitlements(common),
                        dependencies=('@rpath/DolphinCore.framework/DolphinCore',),
                        rpaths=('@executable_path/Frameworks',), **keywords)


def helper_info(version, marketing):
    contract = line.helper_contract()
    return {'CFBundleExecutable': line.HELPER_EXECUTABLE, 'CFBundlePackageType': 'XPC!',
            'CFBundleIdentifier': 'com.neogamelab.neostation' + contract['bundleSuffix'], 'CFBundleVersion': version,
            'CFBundleShortVersionString': marketing, 'MinimumOSVersion': '17.4', contract['marker']: '1',
            'NSExtension': {'NSExtensionPointIdentifier': 'com.apple.share-services',
                            'NSExtensionPrincipalClass': contract['principalClass'],
                            'NSExtensionAttributes': {'NSExtensionActivationRule': 'FALSEPREDICATE'}}}


def helper_image(signed=True):
    """The helper executable as the build links it: StikJIT of the host through @executable_path/../../Frameworks."""
    image = fixtures.packaging_image({}, dependencies=(line.STIKJIT, '/System/Library/Frameworks/Foundation.framework/Foundation'),
                                     rpaths=('@executable_path/Frameworks', '@executable_path/../../Frameworks'))
    return image   # packaging_image always carries a (synthetic) code signature


def nested(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def private_module(name, path):
    spec = importlib.util.spec_from_file_location(name + '_s2arm_private', ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# The two common validators of the Dolphin packager and seal and of the structure step, before their S2Arm conditionals
# (origin/Claude 41c76404): (module, path, blob).
COMMON_VALIDATORS = (('verify_ipa', 'packages/dolphin_internal_bridge/ci/verify_ipa.py',
                      '6032458096236bcf75fc007d208d4ba177dd3216'),
                     ('validate_rpcs3_ipa', 'build-utils/validate_rpcs3_ipa.py', '1a1028277da3309572e22f45c9c1ee3949dff085'))


def common_line_module(name, path, blob):
    """The common line's validator file before its S2Arm conditional (None when this clone lacks the blob)."""
    result = subprocess.run(['git', 'cat-file', 'blob', blob], cwd=ROOT, capture_output=True)
    if result.returncode:
        return None
    module = types.ModuleType(name + '_common_line')
    module.__file__ = str(ROOT / path)
    exec(compile(result.stdout.decode(), str(ROOT / path), 'exec'), module.__dict__)
    return module


class NativeConditionals(unittest.TestCase):
    """The closed extension sets of verify_ipa.validate (Dolphin packager, seal) and of
    validate_rpcs3_ipa.validate_helper_bundles (structure) accept the S2Arm application through their own conditionals;
    the launcher extends nothing in memory any more."""
    def members(self, identity=True, frameworks=line.ENGINE_FRAMEWORKS, helper=True):
        members = fixtures.complete_dolphin_packaging_members()
        app = fixtures.APP
        if helper:
            members[app + 'PlugIns/' + line.HELPER + '/Info.plist'] = plistlib.dumps(
                dict(helper_info('368', '0.0.2'), CFBundleIdentifier='com.neogamelab.neostation.s2armjithelper'))
            members[app + 'PlugIns/' + line.HELPER + '/' + line.HELPER_EXECUTABLE] = helper_image(signed=True)
        for name in frameworks:
            for path, data in framework_files(name, signed=True).items():
                members[app + 'Frameworks/' + path] = data
        if identity:
            members[app + line.PACKAGED_IDENTITY] = b'{}'
        return members

    def ipa(self, members):
        directory = tempfile.mkdtemp(prefix='s2arm-sets-')
        self.addCleanup(shutil.rmtree, directory)
        path = Path(directory) / 'NeoStation.ipa'
        with zipfile.ZipFile(path, 'w') as archive:
            for name, data in members.items():
                entry = zipfile.ZipInfo(name)
                entry.external_attr = 0o100755 << 16
                archive.writestr(entry, data)
        return path

    def extracted(self, members):
        directory = Path(tempfile.mkdtemp(prefix='s2arm-sets-'))
        self.addCleanup(shutil.rmtree, directory)
        for name, data in members.items():
            (directory / name).parent.mkdir(parents=True, exist_ok=True)
            (directory / name).write_bytes(data)
        return directory, directory / fixtures.APP

    @staticmethod
    def outcome(function, *arguments):
        try:
            return 'report', json.dumps(function(*arguments), sort_keys=True, default=str)
        except Exception as error:   # noqa: BLE001 - the exact refusal is compared
            return 'refused', type(error).__name__ + ': ' + str(error)

    def validators(self):
        """The validators the recipe runs (the shared modules) and the common line's files before their conditionals."""
        current = {name: importlib.import_module(name) for name, _, _ in COMMON_VALIDATORS}
        common = {name: module for name, path, blob in COMMON_VALIDATORS
                  if (module := common_line_module(name, path, blob)) is not None}
        return current, common

    def helpers(self, module, members):
        root, app = self.extracted(members)
        return self.outcome(module.validate_helper_bundles, app, plistlib.loads((app / 'Info.plist').read_bytes()), root)

    def test_the_s2arm_ipa_passes_the_common_validators_themselves(self):
        current, common = self.validators()
        ipa = self.ipa(self.members())
        kind, text = self.outcome(current['verify_ipa'].validate, ipa)
        self.assertEqual(kind, 'report', text)
        self.assertIn(line.HELPER, json.loads(text)['embeddedExtensions'])
        kind, text = self.helpers(current['validate_rpcs3_ipa'], self.members())
        self.assertEqual(kind, 'report', text)
        self.assertEqual(json.loads(text)[line.HELPER], 'com.neogamelab.neostation.s2armjithelper')
        if 'verify_ipa' in common:
            self.assertIn('Unexpected app-extension set', self.outcome(common['verify_ipa'].validate, ipa)[1])
        if 'validate_rpcs3_ipa' in common:
            self.assertIn('Unexpected app-extension set', self.helpers(common['validate_rpcs3_ipa'], self.members())[1])
        self.assertNotIn(line.HELPER, current['verify_ipa'].EXPECTED_HELPERS, 'the common sets stay closed')
        self.assertNotIn(line.HELPER, current['validate_rpcs3_ipa'].EXPECTED_HELPERS)

    def test_without_the_identity_the_validators_are_the_common_ones(self):
        current, common = self.validators()
        for members in (fixtures.complete_dolphin_packaging_members(), self.members(identity=False),
                        self.members(identity=False, helper=False)):
            ipa = self.ipa(members)
            result = self.outcome(current['verify_ipa'].validate, ipa)
            helpers = self.helpers(current['validate_rpcs3_ipa'], members)
            if 'verify_ipa' in common:
                self.assertEqual(result, self.outcome(common['verify_ipa'].validate, ipa))
            if 'validate_rpcs3_ipa' in common:
                self.assertEqual(helpers, self.helpers(common['validate_rpcs3_ipa'], members))
        self.assertIn('Unexpected app-extension set', self.outcome(current['verify_ipa'].validate,
                                                                   self.ipa(self.members(identity=False)))[1])
        self.assertIn('Unexpected app-extension set', self.helpers(current['validate_rpcs3_ipa'],
                                                                   self.members(identity=False))[1])
        bad = Path(tempfile.mkdtemp(prefix='s2arm-sets-')) / 'not.ipa'
        self.addCleanup(shutil.rmtree, bad.parent)
        bad.write_bytes(b'not a zip')
        if 'verify_ipa' in common:
            self.assertEqual(self.outcome(current['verify_ipa'].validate, bad), self.outcome(common['verify_ipa'].validate, bad))
        self.assertEqual(self.outcome(current['verify_ipa'].validate, bad)[0], 'refused')

    def test_the_identity_requires_the_frameworks_and_the_helper(self):
        current, _ = self.validators()
        for frameworks in (('S2ArmEngine',), ('NS2Pro',)):
            members = self.members(frameworks=frameworks)
            self.assertIn('engine frameworks', self.outcome(current['verify_ipa'].validate, self.ipa(members))[1])
            self.assertIn('engine frameworks', self.helpers(current['validate_rpcs3_ipa'], members)[1])
        members = self.members(helper=False)
        self.assertIn('Unexpected app-extension set', self.outcome(current['verify_ipa'].validate, self.ipa(members))[1])
        self.assertIn('Unexpected app-extension set', self.helpers(current['validate_rpcs3_ipa'], members)[1])

    def test_every_closed_set_carries_its_own_conditional(self):
        tests = {'build-utils/validate_single_ipa_distribution.py': 'test/s2arm_validator_test.py',
                 'packages/dolphin_internal_bridge/ci/verify_ipa.py': 'test/s2arm_dolphin_verify_ipa_test.py',
                 'build-utils/validate_rpcs3_ipa.py': 'test/s2arm_rpcs3_helpers_test.py',
                 '.github/workflows/standard-delivery.yml': 'test/s2arm_version_check_test.py',
                 'build-utils/verify_downloaded_delivery.py': 'test/s2arm_downloaded_delivery_test.py'}
        self.assertEqual([path for path, _ in line.NATIVE_CONDITIONALS], list(tests))
        for path, where in line.NATIVE_CONDITIONALS:
            text = (ROOT / path).read_text()
            self.assertTrue(line.PACKAGED_IDENTITY in text or 'S2ARM_IDENTITY' in text, path)
            self.assertIn(where, text, path)
            self.assertTrue((ROOT / tests[path]).is_file(), tests[path])
        self.assertEqual(distribution_module().S2ARM_IDENTITY, line.PACKAGED_IDENTITY)
        self.assertEqual([item['path'] for item in line.describe()['nativeConditionals']], list(tests))

    def test_nothing_is_extended_in_memory(self):
        for name in ('EXTENSION_SETS', 'VERIFIER_EDITS', 'EXTENDED_OPERATIONS', 'extend_validators', 's2arm_aware',
                     'extension_set_review', 'dolphin_package', 'edited_verifier_source'):
            self.assertFalse(hasattr(line, name), name)
        source = (HERE / 'standard_delivery_s2arm.py').read_text()
        for text in ('EXPECTED_HELPERS', 'exec(', 'setattr(', 'dolphin-package'):
            self.assertNotIn(text, source)
        self.assertNotIn('dolphin-package', line.LINE_OPERATIONS)
        line.configure()
        verify_ipa = importlib.import_module('verify_ipa')
        rpcs3 = importlib.import_module('validate_rpcs3_ipa')
        support = importlib.import_module('build_support')
        for function in (verify_ipa.validate, rpcs3.validate_helper_bundles):
            self.assertFalse(hasattr(function, '__wrapped__') or hasattr(function, 's2armExtended'), function)
            self.assertEqual(function.__code__.co_filename, str(Path(sys.modules[function.__module__].__file__)))
        self.assertIs(support.validate, verify_ipa.validate, 'the Dolphin packager runs the common validator itself')
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            line.main(['dolphin-package'])


class EngineWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sd = line.configure()
        cls.text = (ROOT / line.WORKFLOW).read_text()
        cls.common_text = (ROOT / line.COMMON_WORKFLOW).read_text()
        cls.steps = cls.sd.load_yaml_subset(cls.text)['jobs']['application']['steps']
        cls.names = [step['name'] for step in cls.steps]

    def step(self, name):
        return self.steps[self.names.index(name)]

    def test_the_engine_steps_and_their_order(self):
        names = self.names
        jit = names.index('Add the S2Arm JIT helper extension to the generated host')
        self.assertEqual(self.steps[jit]['run'], 'set -euo pipefail\npython3 build-utils/s2arm/configure_s2arm_ios.py\n'
                         'python3 build-utils/delivery_metrics.py s2arm_cocoa_pods env -u BUNDLE_GEMFILE -u BUNDLE_PATH '
                         'pod install --project-directory=ios\npython3 build-utils/s2arm/configure_s2arm_ios.py check-pods\n')
        self.assertEqual(names[jit - 1], 'Turn the S2Arm device probe on in the generated host')
        self.assertEqual(names[jit + 1], 'Align application and extension versions to the pubspec version')
        self.assertLess(names.index('Configure release host'), jit)
        download = names.index('Download and authenticate the S2Arm engine frameworks of the pinned producer run')
        self.assertEqual(names[download - 1], 'Authenticate the replaced engine producer runs')
        embed = names.index('Embed the S2Arm engine frameworks and their identity in the built application')
        app = names.index('Check the S2Arm engine frameworks, identity and JIT helper in the built application')
        package = names.index('Package the rebuilt application and retain current component identities')
        seal = names.index('Seal every executable, framework and extension for SideStore')
        signed = names.index('Check the S2Arm engine frameworks, identity and JIT helper in the signed IPA')
        self.assertLess(names.index('Compile Release device binary with measured AOT and Xcode phases'), embed)
        self.assertEqual(app, embed + 1)
        self.assertLess(download, embed)
        self.assertLess(app, package)
        self.assertLess(package, seal)
        self.assertEqual(names[signed - 1], 'Check the S2Arm probe key and code in the signed IPA')
        self.assertLess(names.index('Verify every signed image, the replaced Core payloads and the retained payloads'),
                        signed)
        self.assertLess(signed, names.index('Prepare encrypted delivery and evidence'))
        built = 'build/ios/DolphinDerivedData/Build/Products/Release-iphoneos/Runner.app'
        self.assertEqual(self.steps[embed]['run'], make_workflow.LINE_CALL + 'engine-embed ' + built)
        self.assertEqual(self.steps[app]['run'], make_workflow.LINE_CALL + 'engine-check-app ' + built)
        self.assertEqual(self.steps[signed]['run'], make_workflow.LINE_CALL + 'engine-check-ipa "dist/$IPA_NAME.ipa"')
        self.assertEqual(self.steps[download]['run'], make_workflow.LINE_CALL + 'engine-download')
        self.assertEqual(self.text.count('configure_s2arm_ios.py'), 2)

    def test_no_declared_edit_of_common_steps(self):
        """The Dolphin packager and the version check run as in the common workflow: their closed extension set and
        count carry their own S2Arm conditional, and the version check of this workflow, executed, counts the
        application and eight extensions only beside the S2Arm identity."""
        import s2arm_version_check_test as version_check
        report = make_workflow.explain(self.common_text, self.text, self.sd.load_yaml_subset)
        self.assertEqual(report['editedSteps'], [])
        self.assertEqual(make_workflow.STEP_EDITS, ())
        common = {step['name']: step for step in self.sd.load_yaml_subset(self.common_text)['jobs']['application']['steps']}
        for name in ('Package the rebuilt application and retain current component identities',
                     'Verify final signed legal bundle and application and extension versions'):
            expected = json.loads(json.dumps(common[name]).replace(make_workflow.COMMON_CALL, make_workflow.LINE_CALL))
            self.assertEqual(self.step(name), expected, name)
        package = self.step('Package the rebuilt application and retain current component identities')['run']
        self.assertLess(package.index('python3 packages/dolphin_internal_bridge/ci/build_support.py package'),
                        package.index('structure "dist/$IPA_NAME.ipa"'))
        self.assertEqual(self.text.count('build_support.py package'), 1)
        self.assertEqual(self.common_text.count('build_support.py package'), 1)
        self.assertNotIn('dolphin-package', self.text)
        script = version_check.step_script(self.text)
        self.assertEqual(script, version_check.step_script(self.common_text))
        self.assertEqual(version_check.run_step(script, version_check.s2arm_ipa())[:2], (0, ''))
        self.assertEqual(version_check.run_step(script, version_check.common_ipa())[:2], (0, ''))
        self.assertEqual(version_check.run_step(script, version_check.with_helper(version_check.common_ipa()))[:2],
                         (1, version_check.SEVEN))
        self.assertEqual(version_check.run_step(script, version_check.with_identity(version_check.common_ipa()))[:2],
                         (1, version_check.EIGHT))
        # A common workflow that no longer holds a step this one inserts after stops the generation.
        anchors = [after for _, after, _ in make_workflow.INSERTIONS if f'    - name: {after}\n' in self.common_text]
        self.assertGreaterEqual(len(anchors), 7)
        for after in anchors:
            with self.subTest(after=after):
                with self.assertRaisesRegex(make_workflow.GenerationError, 'not found exactly once'):
                    make_workflow.generate(self.common_text.replace(f'    - name: {after}\n', f'    - name: {after} (moved)\n'))
        # The count: the application, the common closed set, MeloNX's helper and RAM donor, the S2Arm helper.
        validator = distribution_module()
        self.assertEqual(1 + len(validator.EXPECTED_EXTENSIONS) + 2 + len(validator.S2ARM_EXTENSIONS), 9)

    def test_the_legal_gate_runs_on_the_application_with_the_engine_notices(self):
        names = self.names
        gate = names.index('Check the legal gate with the S2Arm engine notices of the built application')
        built = 'build/ios/DolphinDerivedData/Build/Products/Release-iphoneos/Runner.app'
        self.assertEqual(self.steps[gate]['run'], 'python3 build-utils/embed_legal_bundle.py --validate-only --app '
                                                  f'{built} --dolphin-sha "$DOLPHIN_SHA"')
        self.assertEqual(names[gate - 1], 'Check the S2Arm engine frameworks, identity and JIT helper in the built application')
        self.assertLess(names.index('Embed legal, license and source notices'),
                        names.index('Embed the S2Arm engine frameworks and their identity in the built application'))
        self.assertLess(gate, names.index('Package the rebuilt application and retain current component identities'))
        self.assertLess(gate, names.index('Seal every executable, framework and extension for SideStore'))
        common = {step['name']: step for step in self.sd.load_yaml_subset(self.common_text)['jobs']['application']['steps']}
        self.assertEqual(self.step('Embed legal, license and source notices'), common['Embed legal, license and source notices'])
        self.assertLess(names.index('Embed legal, license and source notices'), gate)
        self.assertEqual(self.text.count('embed_legal_bundle.py --validate-only'), 1)
        self.assertEqual(self.common_text.count('embed_legal_bundle.py --validate-only'), 0)

    def test_the_bridge_steps_and_their_order(self):
        names = self.names
        engine = names.index('Download and authenticate the S2Arm engine frameworks of the pinned producer run')
        prepare = 'Download and authenticate the S2Arm preparation library of the pinned producer run'
        sysdata = 'Download and authenticate the S2Arm system data of the pinned producer run'
        install = 'Install the S2Arm preparation library in the engine bridge package before CocoaPods'
        place = 'Place the S2Arm system data and its licences in the built application'
        self.assertEqual(names[engine + 1:engine + 4], [prepare, sysdata, install])
        built = 'build/ios/DolphinDerivedData/Build/Products/Release-iphoneos/Runner.app'
        self.assertEqual([self.step(name)['run'] for name in (prepare, sysdata, install, place)],
                         [make_workflow.LINE_CALL + operation for operation in
                          ('prepare-download', 'sysdata-download', 'prepare-install', 'sysdata-embed ' + built)])
        # The library is in the package before the first pod install (the config-only build, then Configure release
        # host's own), so CocoaPods links it into Runner; no step before it runs CocoaPods.
        first_pods = names.index('Configure release host')
        self.assertIn('pod install', self.step('Configure release host')['run'])
        self.assertIn('flutter build ios --release --no-codesign --config-only', self.step('Configure release host')['run'])
        self.assertLess(names.index(install), first_pods)
        self.assertEqual([name for name in names[:names.index(install)] if 'pod install' in self.step(name).get('run', '') or
                          'flutter build ios' in self.step(name).get('run', '')], [])
        # The system data goes into the compiled application right before the engine, which records it, and long
        # before the signature seals it.
        self.assertEqual(names[names.index(place) + 1], 'Embed the S2Arm engine frameworks and their identity in the built '
                                                         'application')
        self.assertLess(names.index('Compile Release device binary with measured AOT and Xcode phases'), names.index(place))
        self.assertLess(names.index(place), names.index('Seal every executable, framework and extension for SideStore'))
        self.assertEqual(self.text.count('sysdata-embed'), 1)
        self.assertEqual(self.text.count('prepare-install'), 1)
        for job, first, second in make_workflow.ORDER:
            if install in (first, second) or place in (first, second):
                self.assertLess(names.index(first), names.index(second), (first, second))


def distribution_module():
    import validate_single_ipa_distribution
    return validate_single_ipa_distribution


class EngineManifest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sd = line.configure()

    def test_a_draft_that_carries_the_engine(self):
        zips = {name: sha(name.encode()) for name in line.ENGINE_ZIPS}
        value = make_manifest.draft(self.sd, 'sibling', MODEL, 803, reviewed=[('1' * 40, 'engine')],
                                    engine=dict(run=ENGINE_RUN, zips=zips))
        self.assertEqual(self.sd.manifest_errors(value), [])
        self.assertEqual(value['s2arm']['engine'], dict(workflow=line.ENGINE_WORKFLOW, run=ENGINE_RUN, zips=zips))
        self.assertEqual(line.engine_spec(value), value['s2arm']['engine'])
        self.assertEqual(value['images']['added'], sorted(line.ENGINE_IMAGES))
        self.assertEqual(value['images']['removed'], [])
        paths = value['s2arm']['deltaPaths']
        for path in ('packages/s2arm_jit_helper/ios/Resources/s2arm-universal.js', 'build-utils/s2arm/configure_s2arm_ios.py',
                     'build-utils/validate_single_ipa_distribution.py', 'packages/s2arm_probe/ios/s2arm_probe.podspec',
                     'packages/dolphin_internal_bridge/ci/verify_ipa.py', 'build-utils/validate_rpcs3_ipa.py'):
            self.assertIn(path, paths)
        self.assertTrue(all(self.sd.is_product(path) for path in paths))
        self.assertEqual(value['s2arm']['engineDelta']['conditionals'], [path for path, _ in line.NATIVE_CONDITIONALS])
        self.assertIn('build-utils/embed_legal_bundle.py', paths)
        self.assertEqual(value['s2arm']['engineDelta']['notices'], make_manifest.ENGINE_DELTA['notices'])
        self.assertEqual(value['s2arm']['engineDelta']['producer']['members'],
                         list(line.ENGINE_ZIPS) + [line.ENGINE_IDENTITY, line.ENGINE_LICENSES])
        self.assertIn('licence and notice texts in Legal/S2Arm', value['note'])
        self.assertNotIn('Frameworks/dolphin_internal_bridge.framework/dolphin_internal_bridge', value['images']['mustChange'],
                         'the Dolphin verifier is CI code, not a source of the bridge image')
        names = [name for name, _ in value['tests']['flutter']['additions']['commands']]
        self.assertLessEqual({'s2arm-jit-helper', 's2arm-validator', 's2arm-configure', 's2arm-dolphin-verify-ipa',
                              's2arm-rpcs3-helpers', 's2arm-version-check', 's2arm-downloaded-delivery',
                              's2arm-legal-bundle', 's2arm-engine-licenses'}, set(names))
        commands = dict(value['tests']['flutter']['additions']['commands'])
        for name, argv in make_manifest.ENGINE_TESTS:
            self.assertEqual(commands[name], argv)
            self.assertTrue((ROOT / argv[-1]).is_file(), argv[-1])
        self.assertEqual(len(names), len(set(names)))
        self.assertIn('S2ArmEngine.framework and NS2Pro.framework of run', value['note'])
        self.assertEqual(value['s2arm']['engineDelta']['images']['added'], list(line.ENGINE_IMAGES))
        plain = make_manifest.draft(self.sd, 'sibling', MODEL, 803)
        self.assertNotIn('engine', plain['s2arm'])
        self.assertEqual(plain['images']['added'], [])
        with self.assertRaises(line.LineError):
            line.engine_spec(plain)
        for engine in (dict(run=0, zips=zips), dict(run=ENGINE_RUN, zips={line.ENGINE_ZIPS[0]: 'f' * 64}),
                       dict(run=ENGINE_RUN, zips=dict(zips, **{line.ENGINE_ZIPS[0]: 'F' * 64})),
                       dict(run='43100000001', zips=zips)):
            with self.subTest(engine=engine):
                with self.assertRaises(SystemExit):
                    make_manifest.draft(self.sd, 'sibling', MODEL, 803, engine=engine)

    def test_a_draft_that_carries_the_engine_bridge(self):
        zips = {name: sha(name.encode()) for name in line.ENGINE_ZIPS}
        engine = dict(run=ENGINE_RUN, zips=zips)
        prepare, sysdata = dict(run=PREPARE_RUN, zip=sha(b'prepare')), dict(run=SYSDATA_RUN, tree=sha(b'sysdata'))
        value = make_manifest.draft(self.sd, 'sibling', MODEL, 803, reviewed=[('1' * 40, 'bridge')], engine=engine,
                                    prepare=prepare, sysdata=sysdata)
        self.assertEqual(self.sd.manifest_errors(value), [])
        self.assertEqual(value['s2arm']['prepare'], dict(workflow=line.PREPARE_WORKFLOW, **prepare))
        self.assertEqual(value['s2arm']['sysdata'], dict(workflow=line.SYSDATA_WORKFLOW, **sysdata))
        self.assertEqual((line.prepare_spec(value), line.sysdata_spec(value)),
                         (value['s2arm']['prepare'], value['s2arm']['sysdata']))
        self.assertEqual(value['s2arm']['bridgeDelta'], make_manifest.BRIDGE_DELTA)
        paths = value['s2arm']['deltaPaths']
        for path in ('pubspec.yaml', 'packages/s2arm_engine_bridge/pubspec.yaml', 'packages/s2arm_engine_bridge/.gitignore',
                     'packages/s2arm_engine_bridge/ios/s2arm_engine_bridge.podspec',
                     'packages/s2arm_engine_bridge/ios/Classes/S2ArmGamePreparation.m',
                     'packages/s2arm_engine_bridge/lib/s2arm_engine_bridge.dart',
                     'build-utils/collect_build_source_evidence.py'):
            self.assertIn(path, paths)
        self.assertTrue(all(self.sd.is_product(path) for path in paths))
        self.assertFalse([path for path in paths if '/ios/Frameworks/' in path], 'the vendored library is not a product path')
        self.assertEqual(value['images']['added'], sorted(line.ENGINE_IMAGES), 'the bridge adds no image: it is in Runner')
        self.assertIn('Runner', value['images']['mustChange'])
        for group, expected in (('flutter', 's2arm-engine-bridge'), ('native', 's2arm-legal-review')):
            names = [name for name, _ in value['tests'][group]['additions']['commands']]
            self.assertEqual(names.count(expected), 1, group)
            self.assertEqual(len(names), len(set(names)), group)
        self.assertFalse([text for text in value['s2arm']['pending'] if 's2arm.prepare' in text])
        self.assertIn('Its host bridge packages/s2arm_engine_bridge', value['note'])
        self.assertIn(f'run {PREPARE_RUN} of .github/workflows/s2arm-core.yml', value['note'])
        # The engine alone: the draft says what is missing, and the launcher refuses such a build.
        alone = make_manifest.draft(self.sd, 'sibling', MODEL, 803, engine=engine)
        self.assertTrue([text for text in alone['s2arm']['pending'] if text.startswith('s2arm.prepare and s2arm.sysdata')])
        self.assertNotIn('prepare', alone['s2arm'])
        with self.assertRaises(line.LineError):
            line.prepare_spec(alone)
        refusals = {
            'preparation library without system data': dict(engine=engine, prepare=prepare),
            'system data without preparation library': dict(engine=engine, sysdata=sysdata),
            'bridge without the engine': dict(prepare=prepare, sysdata=sysdata),
            'archive digest in capitals': dict(engine=engine, prepare=dict(prepare, zip=prepare['zip'].upper()), sysdata=sysdata),
            'short tree digest': dict(engine=engine, prepare=prepare, sysdata=dict(sysdata, tree=sysdata['tree'][:-1])),
            'no run': dict(engine=engine, prepare=dict(prepare, run=0), sysdata=sysdata),
            'run as text': dict(engine=engine, prepare=prepare, sysdata=dict(sysdata, run=str(SYSDATA_RUN))),
            'no digest': dict(engine=engine, prepare=dict(run=PREPARE_RUN), sysdata=sysdata),
        }
        for name, keywords in refusals.items():
            with self.subTest(case=name):
                with self.assertRaises(SystemExit):
                    make_manifest.draft(self.sd, 'sibling', MODEL, 803, **keywords)
        with tempfile.TemporaryDirectory(prefix='s2arm-draft-') as directory:
            output = Path(directory) / '803.json'
            arguments = ['sibling', '--model', str(MODEL), '--build', '803', '--engine-run', str(ENGINE_RUN),
                         *[item for name, digest in zips.items() for item in ('--engine-zip', f'{name}={digest}')],
                         '--prepare-run', str(PREPARE_RUN), '--prepare-zip', prepare['zip'],
                         '--sysdata-run', str(SYSDATA_RUN), '--sysdata-tree', sysdata['tree'], '--output', str(output)]
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(make_manifest.main(arguments), 0)
            written = json.loads(output.read_bytes())
            self.assertEqual((written['s2arm']['prepare'], written['s2arm']['sysdata']),
                             (value['s2arm']['prepare'], value['s2arm']['sysdata']))
            for missing in ('--prepare-zip', '--sysdata-tree'):
                index = arguments.index(missing)
                with self.subTest(missing=missing), contextlib.redirect_stdout(io.StringIO()):
                    with self.assertRaises(SystemExit):
                        make_manifest.main(arguments[:index] + arguments[index + 2:])

    def model_with(self, added=(), removed=()):
        """make_manifest reading the MODEL manifest with these added and removed images, everything else unchanged."""
        model = manifest()
        model['images']['added'], model['images']['removed'] = list(added), list(removed)
        path = Path(self.sd.manifest_path(MODEL))
        real = make_manifest.read

        def read(root, name):
            return json.dumps(model).encode() if Path(name) == path else real(root, name)
        return mock.patch.object(make_manifest, 'read', read)

    def test_the_images_a_model_adds_or_removes(self):
        zips = {name: sha(name.encode()) for name in line.ENGINE_ZIPS}
        engine = dict(run=ENGINE_RUN, zips=zips)
        model = manifest()
        referenced = set(model['images']['mustChange']) | set(model['images']['replaced'].values()) | {
            image for images in model['images']['retained'].values() for image in images}
        base = sorted(self.sd.verify_base(model))
        gone = next(image for image in base if image not in referenced and '*' not in image)
        new = 'Frameworks/rb_new_bridge.framework/rb_new_bridge'
        with self.model_with(added=[new], removed=[gone]):
            # A sibling is the model rebuilt over the same base: it adds and removes what the model does.
            sibling = make_manifest.draft(self.sd, 'sibling', MODEL, 803, engine=engine)
            self.assertEqual(self.sd.manifest_errors(sibling), [])
            self.assertEqual(sibling['images']['added'], sorted({new} | set(line.ENGINE_IMAGES)))
            self.assertEqual(sibling['images']['removed'], [gone])
            plain = make_manifest.draft(self.sd, 'sibling', MODEL, 803)
            self.assertEqual((plain['images']['added'], plain['images']['removed']), ([new], [gone]))
            # A successor's base is the delivered model, whose signed inventory already holds its additions.
            successor = make_manifest.draft(self.sd, 'successor', MODEL, 803, engine=engine)
            self.assertEqual(successor['images']['added'], sorted(line.ENGINE_IMAGES))
            self.assertEqual(successor['images']['removed'], [])
        refusals = {
            'an added image already in the base': dict(added=[base[0]]),
            'a removed image not in the base': dict(removed=[new]),
            'an image both added and removed': dict(added=[new], removed=[new]),
            'an engine image added by the model': dict(added=[line.ENGINE_IMAGES[0]]),
        }
        for name, images in refusals.items():
            with self.subTest(case=name), self.model_with(**images):
                with self.assertRaises(SystemExit):
                    make_manifest.draft(self.sd, 'sibling', MODEL, 803, engine=engine)

    def test_a_sibling_of_726_keeps_the_xenios_bridge(self):
        # 726, the model of 803, adds the XeniOS bridge over 725; 803 is built from the same tree over the same base.
        model = manifest(726)
        self.assertEqual(model['images']['added'], ['Frameworks/xenia_internal_bridge.framework/xenia_internal_bridge'])
        zips = {name: sha(name.encode()) for name in line.ENGINE_ZIPS}
        value = make_manifest.draft(self.sd, 'sibling', 726, 803, reviewed=[('1' * 40, 'bridge')],
                                    engine=dict(run=ENGINE_RUN, zips=zips), prepare=dict(run=PREPARE_RUN, zip=sha(b'prepare')),
                                    sysdata=dict(run=SYSDATA_RUN, tree=sha(b'sysdata')))
        self.assertEqual(self.sd.manifest_errors(value), [])
        self.assertEqual(value['base'], model['base'])
        self.assertEqual(value['images']['added'], sorted(set(model['images']['added']) | set(line.ENGINE_IMAGES)))
        self.assertEqual(value['images']['removed'], [])
        self.assertLessEqual(set(model['images']['mustChange']) | {'Runner'}, set(value['images']['mustChange']))


class Verifier(unittest.TestCase):
    def test_the_common_verifier_runs_unchanged(self):
        """The common verifier is imported as it is (its count of the extensions carries its own S2Arm conditional),
        bound to the recipe configured for this line; a verifier that reads the recipe otherwise than reviewed is
        refused before it runs."""
        import verify_downloaded_delivery_s2arm as launcher
        verifier = launcher.load_verifier()
        self.assertIs(sys.modules['verify_downloaded_delivery'], verifier)
        self.assertEqual(Path(verifier.__file__).resolve(), (ROOT / line.VERIFIER).resolve())
        self.assertEqual(Path(verifier.verify.__code__.co_filename).resolve(), (ROOT / line.VERIFIER).resolve())
        self.assertFalse(hasattr(verifier, 'S2ARM_EDITED'))
        self.assertIs(launcher.load_verifier(), verifier)
        self.assertIs(verifier.sd, line.configure())
        source = (ROOT / line.VERIFIER).read_text()
        self.assertEqual(source.count('if root + S2ARM_IDENTITY in names:'), 1)
        self.assertEqual(verifier.S2ARM_EXTENSIONS, distribution_module().S2ARM_EXTENSIONS)
        wrapper = (HERE / 'verify_downloaded_delivery_s2arm.py').read_text()
        for text in ('S2ARM_EDITED', 'exec(', 'VERIFIER_EDITS', 'edited_verifier_source'):
            self.assertNotIn(text, wrapper)
        with tempfile.TemporaryDirectory(prefix='s2arm-verifier-') as directory:
            target = Path(directory) / line.VERIFIER
            target.parent.mkdir(parents=True)
            self.assertEqual(source.count('sd.subject_build('), 1)
            target.write_text(source.replace('sd.subject_build(', 'sd.authenticate_base('))
            with self.assertRaisesRegex(line.LineError, 'no longer reads the recipe'):
                line.check_verifier_inventory(directory)
            target.write_text(source)
            line.check_verifier_inventory(directory)


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
        product = ['build-utils/s2arm/set_probe_key.py', 'build-utils/s2arm/configure_s2arm_ios.py',
                   'build-utils/validate_single_ipa_distribution.py', 'test/s2arm_jit_helper_test.py',
                   'test/s2arm_validator_test.py', 'test/s2arm_configure_test.py',
                   'packages/dolphin_internal_bridge/ci/verify_ipa.py', 'build-utils/validate_rpcs3_ipa.py',
                   'test/s2arm_dolphin_verify_ipa_test.py', 'test/s2arm_rpcs3_helpers_test.py',
                   'test/s2arm_version_check_test.py', 'test/s2arm_downloaded_delivery_test.py',
                   'build-utils/s2arm/engine/RewindBox-S2Arm-NOTICE.txt', 'test/s2arm_legal_bundle_test.py'] + [
            path.relative_to(ROOT).as_posix() for path in sorted((ROOT / 'packages/s2arm_jit_helper').rglob('*'))
            if path.is_file()]
        for path in product:
            self.assertTrue(sd.is_product(path), path + ' reaches the application or its checks: it is product')
        self.assertTrue(sd.is_recipe('docs/s2arm-jit-helper.md'))
        banned = re.compile('|'.join(('cl' + 'aude-', 'gp' + 't-', 'son' + 'net', 'op' + 'us', 'hai' + 'ku')), re.I)
        for path in recipe + product + ['docs/s2arm-jit-helper.md']:
            text = (ROOT / path).read_text()
            self.assertIsNone(banned.search(text), path + ' names a model')
            self.assertNotIn('PRIVATE' + ' KEY', text, path)
        # The engine's licence collector, its test and the legal gate name the audio codec by its own name (its S2Arm
        # build script and licence folder): product paths, checked for keys only.
        for path in ('build-utils/s2arm/engine/collect_licenses.py', 'test/s2arm_engine_licenses_test.py',
                     'build-utils/embed_legal_bundle.py'):
            self.assertTrue(sd.is_product(path), path)
            self.assertNotIn('PRIVATE' + ' KEY', (ROOT / path).read_text(), path)

    def test_the_engine_bridge_files(self):
        sd = line.configure()
        tracked = subprocess.run(['git', 'ls-files', '-z', '--', line.BRIDGE_PACKAGE], cwd=ROOT, capture_output=True,
                                 check=True).stdout.decode().split('\0')
        package = sorted(path for path in tracked if path)
        self.assertIn(line.BRIDGE_PODSPEC, package)
        self.assertIn(line.BRIDGE_PACKAGE + '/.gitignore', package)
        self.assertFalse([path for path in package if path.startswith(line.BRIDGE_FRAMEWORKS + '/')],
                         'nothing of S2ArmPrepare.xcframework is committed')
        product = package + ['pubspec.yaml', 'build-utils/collect_build_source_evidence.py']
        for path in product:
            self.assertTrue(sd.is_product(path), path + ' reaches the application or its legal gate: it is product')
        for path in ('docs/s2arm-engine-bridge.md', 'docs/s2arm-legal-notices.md',
                     'docs/evidence/s2arm-engine-declarations-2026-11-11.json'):
            self.assertTrue(sd.is_recipe(path), path)
        banned = re.compile('|'.join(('cl' + 'aude-', 'gp' + 't-', 'son' + 'net', 'op' + 'us', 'hai' + 'ku')), re.I)
        # The notices name third-party libraries by their own names, among them a codec whose name contains a banned
        # word: they are checked for keys only.
        for path in package + ['docs/s2arm-engine-bridge.md', 'docs/evidence/s2arm-engine-declarations-2026-11-11.json']:
            text = (ROOT / path).read_text()
            self.assertIsNone(banned.search(text), path + ' names a model')
            self.assertNotIn('PRIVATE' + ' KEY', text, path)
        self.assertNotIn('PRIVATE' + ' KEY', (ROOT / 'docs/s2arm-legal-notices.md').read_text())
        # The functions the bridge calls in S2ArmPrepare are the entry points the Runner check requires.
        calls = set()
        for path in (ROOT / line.BRIDGE_PACKAGE / 'ios/Classes').glob('*.m'):
            calls |= set(re.findall(r'\b(rb_s2arm_\w+)\(', path.read_text()))
        declared = set(re.findall(r'\b(rb_s2arm_\w+)\(', (ROOT / line.BRIDGE_PACKAGE /
                                                          'ios/Classes/S2ArmPrepareABI.h').read_text()))
        self.assertEqual({'_' + name for name in declared}, set(line.PREPARE_ENTRY_POINTS))
        self.assertEqual({'_' + name for name in calls}, set(line.PREPARE_ENTRY_POINTS) |
                         {'_rb_s2arm_engine_loaded', '_rb_s2arm_engine_mark_loading'})
        self.assertIn('S2ARM_ENGINE_LOADED_EXPORT __attribute__((visibility("default"), used))',
                      (ROOT / line.BRIDGE_PACKAGE / 'ios/Classes/S2ArmEngineLoaded.c').read_text())
        # The delivery places the whole tree as S2ArmSystemData; the bridge links its systemdata/ folder into each
        # game's resource pack, where the engine reads systemdata/fonts and systemdata/<id> (S2Arm services Host.cs).
        preparation = (ROOT / line.BRIDGE_PACKAGE / 'ios/Classes/S2ArmGamePreparation.m').read_text()
        self.assertEqual(line.SYSTEM_DATA_READ, 'S2ArmSystemData/systemdata')
        self.assertEqual(preparation.count(f'stringByAppendingPathComponent:@"{line.SYSTEM_DATA_READ}"'), 1)
        self.assertNotIn(f'@"{line.SYSTEM_DATA}"', preparation)
        self.assertTrue(all(path.startswith(line.SYSDATA_TOPS) or path == line.SYSDATA_SOURCES for path in sysdata_tree()))


if __name__ == '__main__':
    os.environ.pop('BUILD_NUMBER', None)
    unittest.main(verbosity=2)
