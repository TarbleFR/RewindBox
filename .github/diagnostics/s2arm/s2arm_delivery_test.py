#!/usr/bin/env python3
"""Offline tests of the Switch 2 (S2Arm) test IPA delivery line (plain python3; no network, no build).

    python3 -B .github/diagnostics/s2arm/s2arm_delivery_test.py

What they cover: the launcher redirects exactly the reviewed line constants of the unchanged standard
recipe and refuses a recipe it was not reviewed for; the base stays authenticated on the line that
delivered it; the generated workflow is the committed one, triggers only on this branch and tag, keeps
every common step and uploads only through the protected action; the Info.plist key is set once, in
order, and the built application is checked; the draft manifests are accepted by the recipe's own checker.
The S2Arm engine: its producer run and artifact authenticated (mocked API, synthetic producer archives),
frameworks and identity embedded and checked in a synthetic built application and signed IPA, the in-memory
S2Arm-aware extension sets of the two common validators (same outcome as the originals without the identity),
the engine steps and the two declared edits of common steps, a draft carrying the engine, the verifier edit.
Not covered here (needs the reshaped history, the network or a macOS build): freeze, the API-backed
contract checks, the run itself, a real engine framework.
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
                            'Download and authenticate the S2Arm engine frameworks of the pinned producer run',
                            'Turn the S2Arm device probe on in the generated host',
                            'Add the S2Arm JIT helper extension to the generated host',
                            'Check the S2Arm probe key and code in the compiled application',
                            'Embed the S2Arm engine frameworks and their identity in the built application',
                            'Check the S2Arm engine frameworks, identity and JIT helper in the built application',
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
        # The common calls, the three guards, the four engine steps and the routed Dolphin packager.
        self.assertEqual(len(recipe_calls), self.common_text.count('.github/diagnostics/standard_delivery.py') + 3 + 5)
        self.assertNotIn('diagnostics/standard_delivery.py', self.text)
        operations = {operation for script, operation in calls if 'standard_delivery' in script}
        self.assertLessEqual(operations, set(self.sd.OPERATIONS) | set(line.LINE_OPERATIONS))
        self.assertLessEqual({'request-guard', 'recipient-guard', 'engine-download', 'engine-embed', 'engine-check-app',
                              'engine-check-ipa', 'dolphin-package'}, operations)
        self.assertEqual(set(line.LINE_OPERATIONS) - {'inventory'},
                         set(line.PATH_OPERATIONS) | set(line.PLAIN_OPERATIONS))
        self.assertLessEqual(set(line.EXTENDED_OPERATIONS), operations)

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
PIN = json.dumps({'s2arm': {'commit': '6b6a571553f7a687af46e03e2cdbf8ef4d77f335'}}).encode()


class FakeRepo:
    """The git queries the engine checks make, on a producer commit with the pin and two patches."""
    def __init__(self, ancestor=True, files=None):
        self.ancestor = ancestor
        self.files = dict(PATCHES, **{'tools/s2arm_prototype/pin.json': PIN}) if files is None else files

    def is_ancestor(self, ancestor, descendant):
        return self.ancestor

    def entries(self, ref):
        assert ref == PRODUCER
        return {path: ('100644', 'blob') for path in self.files}

    def show(self, ref, path):
        assert ref == PRODUCER
        return self.files[path]


def producer_artifact(zips=None, identity=None, extra=None):
    zips = zips or {name: zipped(framework_files(name)) for name in line.ENGINE_FRAMEWORKS}
    archives = {f'{name}.framework.zip': data for name, data in zips.items()}
    value = dict(run=ENGINE_RUN, attempt=1, head_sha=PRODUCER, s2arm_commit='6b6a571553f7a687af46e03e2cdbf8ef4d77f335',
                 patches=[dict(name=path.rsplit('/', 1)[1], sha256=sha(data)) for path, data in sorted(PATCHES.items())],
                 files={name: sha(data) for name, data in archives.items()})
    value.update(identity or {})
    members = dict(archives, **{line.ENGINE_IDENTITY: json.dumps(value).encode()}, **(extra or {}))
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


class EngineLine(unittest.TestCase):
    """engine-download, engine-embed, engine-check-app and engine-check-ipa on synthetic producer data."""
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
        self.manifest = dict(build=803, images=dict(added=list(line.ENGINE_IMAGES)),
                             s2arm=dict(engine=dict(workflow=line.ENGINE_WORKFLOW, run=ENGINE_RUN, zips=self.zips)))
        for name, value in (('OUT', self.out), ('ROOT', self.root)):
            patcher = mock.patch.object(self.sd, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(self.sd, 'ci_manifest', lambda: self.manifest)
        patcher.start()
        self.addCleanup(patcher.stop)

    def download(self, artifact=None, get=None, repo=None):
        artifact = self.artifact if artifact is None else artifact
        return line.engine_download(self.sd, get or api_for(artifact), lambda identifier, path: path.write_bytes(artifact),
                                    repo or FakeRepo(), self.root)

    def application(self, versions=('803', '0.0.8')):
        app = self.root / 'Runner.app'
        if app.exists():
            shutil.rmtree(app)
        helper = app / 'PlugIns' / line.HELPER
        helper.mkdir(parents=True)
        (app / 'Frameworks').mkdir()
        host = {'CFBundleIdentifier': 'com.neogamelab.neostation', 'CFBundleVersion': versions[0],
                'CFBundleShortVersionString': versions[1], 'CFBundleExecutable': 'Runner'}
        (app / 'Info.plist').write_bytes(plistlib.dumps(host))
        (helper / 'Info.plist').write_bytes(plistlib.dumps(helper_info(*versions)))
        (helper / line.HELPER_EXECUTABLE).write_bytes(helper_image(signed=False))
        (helper / 's2arm-universal.js').write_bytes(self.script)
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


class ExtensionSets(unittest.TestCase):
    """The S2Arm-aware closed extension sets of verify_ipa.validate and validate_rpcs3_ipa.validate_helper_bundles."""
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

    def wrapped(self):
        modules = {'verify_ipa': private_module('verify_ipa', 'packages/dolphin_internal_bridge/ci/verify_ipa.py'),
                   'validate_rpcs3_ipa': private_module('validate_rpcs3_ipa', 'build-utils/validate_rpcs3_ipa.py')}
        originals = {name: private_module(name, path) for name, path in
                     (('verify_ipa', 'packages/dolphin_internal_bridge/ci/verify_ipa.py'),
                      ('validate_rpcs3_ipa', 'build-utils/validate_rpcs3_ipa.py'))}
        self.assertEqual(line.extend_validators(modules), {path: 'extend' for path in line.EXTENSION_SETS})
        self.assertTrue(modules['verify_ipa'].validate.s2armExtended)
        self.assertIs(line.extend_validators(modules)['build-utils/validate_rpcs3_ipa.py'], 'extend')
        return modules, originals

    def test_the_s2arm_ipa_passes_only_the_extended_sets(self):
        modules, originals = self.wrapped()
        ipa = self.ipa(self.members())
        kind, text = self.outcome(modules['verify_ipa'].validate, ipa)
        self.assertEqual(kind, 'report', text)
        self.assertIn(line.HELPER, json.loads(text)['embeddedExtensions'])
        self.assertIn('Unexpected app-extension set', self.outcome(originals['verify_ipa'].validate, ipa)[1])
        root, app = self.extracted(self.members())
        info = plistlib.loads((app / 'Info.plist').read_bytes())
        kind, text = self.outcome(modules['validate_rpcs3_ipa'].validate_helper_bundles, app, info, root)
        self.assertEqual(kind, 'report', text)
        self.assertEqual(json.loads(text)[line.HELPER], 'com.neogamelab.neostation.s2armjithelper')
        self.assertIn('Unexpected app-extension set',
                      self.outcome(originals['validate_rpcs3_ipa'].validate_helper_bundles, app, info, root)[1])
        self.assertNotIn(line.HELPER, modules['verify_ipa'].EXPECTED_HELPERS, 'the set is extended only while it runs')
        self.assertNotIn(line.HELPER, modules['validate_rpcs3_ipa'].EXPECTED_HELPERS)

    def test_without_the_identity_the_validators_are_unchanged(self):
        modules, originals = self.wrapped()
        for members in (fixtures.complete_dolphin_packaging_members(), self.members(identity=False),
                        self.members(identity=False, helper=False)):
            ipa = self.ipa(members)
            self.assertEqual(self.outcome(modules['verify_ipa'].validate, ipa),
                             self.outcome(originals['verify_ipa'].validate, ipa))
            root, app = self.extracted(members)
            info = plistlib.loads((app / 'Info.plist').read_bytes())
            self.assertEqual(self.outcome(modules['validate_rpcs3_ipa'].validate_helper_bundles, app, info, root),
                             self.outcome(originals['validate_rpcs3_ipa'].validate_helper_bundles, app, info, root))
        bad = Path(tempfile.mkdtemp(prefix='s2arm-sets-')) / 'not.ipa'
        self.addCleanup(shutil.rmtree, bad.parent)
        bad.write_bytes(b'not a zip')
        self.assertEqual(self.outcome(modules['verify_ipa'].validate, bad), self.outcome(originals['verify_ipa'].validate, bad))

    def test_the_identity_requires_the_frameworks_and_the_helper(self):
        modules, _ = self.wrapped()
        for frameworks in (('S2ArmEngine',), ('NS2Pro',)):
            members = self.members(frameworks=frameworks)
            self.assertIn('engine frameworks', self.outcome(modules['verify_ipa'].validate, self.ipa(members))[1])
            root, app = self.extracted(members)
            self.assertIn('engine frameworks', self.outcome(modules['validate_rpcs3_ipa'].validate_helper_bundles, app,
                                                            plistlib.loads((app / 'Info.plist').read_bytes()), root)[1])
        members = self.members(helper=False)
        self.assertIn('Unexpected app-extension set', self.outcome(modules['verify_ipa'].validate, self.ipa(members))[1])

    def test_the_reviewed_shape_is_required(self):
        with tempfile.TemporaryDirectory(prefix='s2arm-review-') as directory:
            root = Path(directory)
            for path in line.EXTENSION_SETS:
                (root / path).parent.mkdir(parents=True, exist_ok=True)
                (root / path).write_text((ROOT / path).read_text())
                self.assertEqual(line.extension_set_review(path, root), 'extend')
            path = 'build-utils/validate_rpcs3_ipa.py'
            source = (ROOT / path).read_text()
            for changed in (source.replace('expected_helpers = dict(EXPECTED_HELPERS)', 'expected_helpers = EXPECTED_HELPERS'),
                            source + '\n\ndef other():\n    return EXPECTED_HELPERS\n',
                            source.replace('helper_identifiers = validate_helper_bundles(app, info, root)',
                                           'helper_identifiers = globals()["validate_helper_bundles"](app, info, root)')):
                self.assertNotEqual(changed, source)
                (root / path).write_text(changed)
                with self.assertRaisesRegex(line.LineError, 'review'):
                    line.extension_set_review(path, root)
            (root / path).write_text(source + '\n# S2Arm handled here\n')
            self.assertEqual(line.extension_set_review(path, root), 'native')

    def test_the_dolphin_packager_binds_the_extended_validator(self):
        verify_ipa = importlib.import_module('verify_ipa')
        rpcs3 = importlib.import_module('validate_rpcs3_ipa')
        saved = verify_ipa.validate, rpcs3.validate_helper_bundles, sys.modules.get('build_support')
        calls = []
        fake = types.ModuleType('build_support')
        try:
            line.extend_validators()
            fake.validate = verify_ipa.validate
            fake.main = lambda: calls.append(list(sys.argv))
            sys.modules['build_support'] = fake
            result = line.dolphin_package(None)
            self.assertEqual(result['result'], 'packaged')
            self.assertEqual(calls, [[str(ROOT / 'packages/dolphin_internal_bridge/ci/build_support.py'), 'package']])
            fake.validate = saved[0]
            with self.assertRaisesRegex(line.LineError, 'did not bind'):
                line.dolphin_package(None)
        finally:
            verify_ipa.validate, rpcs3.validate_helper_bundles = saved[0], saved[1]
            if saved[2] is None:
                sys.modules.pop('build_support', None)
            else:
                sys.modules['build_support'] = saved[2]


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

    def test_the_two_declared_edits_of_common_steps(self):
        report = make_workflow.explain(self.common_text, self.text, self.sd.load_yaml_subset)
        self.assertEqual([(item['step'], item['new']) for item in report['editedSteps']], [
            ('Package the rebuilt application and retain current component identities',
             make_workflow.LINE_CALL + 'dolphin-package'),
            ('Verify final signed legal bundle and application and extension versions',
             'assert len(bundles) == 9, "Expected the application and its eight extensions (S2ArmJITHelper included)"')])
        package = self.step('Package the rebuilt application and retain current component identities')['run']
        self.assertNotIn('build_support.py package', package)
        self.assertLess(package.index('dolphin-package'), package.index('structure "dist/$IPA_NAME.ipa"'))
        self.assertNotIn('== 8', self.step('Verify final signed legal bundle and application and extension versions')['run'])
        self.assertEqual(self.text.count('build_support.py package'), 0)
        self.assertEqual(self.common_text.count('build_support.py package'), 1)
        # A common step that no longer holds the edited text stops the generation.
        for job, name, old, new, count in make_workflow.STEP_EDITS:
            for changed in (self.common_text.replace(old, old[:-1] + '#'), self.common_text.replace(old, old + '\n' + old)):
                with self.subTest(step=name):
                    with self.assertRaisesRegex(make_workflow.GenerationError, 'occurrence'):
                        make_workflow.generate(changed)
        # The count: the application, the common closed set, MeloNX's helper and RAM donor, the S2Arm helper.
        validator = distribution_module()
        self.assertEqual(1 + len(validator.EXPECTED_EXTENSIONS) + 2 + len(validator.S2ARM_EXTENSIONS), 9)


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
                     'build-utils/validate_single_ipa_distribution.py', 'packages/s2arm_probe/ios/s2arm_probe.podspec'):
            self.assertIn(path, paths)
        self.assertTrue(all(self.sd.is_product(path) for path in paths))
        names = [name for name, _ in value['tests']['flutter']['additions']['commands']]
        self.assertLessEqual({'s2arm-jit-helper', 's2arm-validator', 's2arm-configure'}, set(names))
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


class Verifier(unittest.TestCase):
    def test_the_in_memory_edit_is_the_declared_one(self):
        original = (ROOT / line.VERIFIER).read_text().splitlines()
        edited = line.edited_verifier_source().splitlines()
        changed = [(a, b) for a, b in zip(original, edited) if a != b]
        self.assertEqual(len(original), len(edited))
        self.assertEqual(len(changed), len(line.VERIFIER_EDITS))
        for (before, after), (old, new, _) in zip(changed, line.VERIFIER_EDITS):
            self.assertTrue(before.startswith(old) and after == new + before[len(old):], (before, after))
        self.assertIn("8 + (root + 'S2Arm-native-identity.json' in names)", line.edited_verifier_source())
        import verify_downloaded_delivery_s2arm as launcher
        verifier = launcher.load_verifier()
        self.assertTrue(verifier.S2ARM_EDITED)
        self.assertIs(launcher.load_verifier(), verifier)
        with tempfile.TemporaryDirectory(prefix='s2arm-verifier-') as directory:
            target = Path(directory) / line.VERIFIER
            target.parent.mkdir(parents=True)
            target.write_text((ROOT / line.VERIFIER).read_text().replace('len(bundles) == 8', 'len(bundles) == 7'))
            with self.assertRaisesRegex(line.LineError, 'review'):
                line.edited_verifier_source(directory)


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
                   'test/s2arm_validator_test.py', 'test/s2arm_configure_test.py'] + [
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


if __name__ == '__main__':
    os.environ.pop('BUILD_NUMBER', None)
    unittest.main(verbosity=2)
