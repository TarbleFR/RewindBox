#!/usr/bin/env python3
"""Offline contract of the standard delivery recipe (no network, no build; runs on Linux).

Checks the build manifests (schema, base receipts and proof files, component pins, recipient,
images, tests), the static workflow (only standard_delivery.py operations, no build-number literal,
constant job names, checkout then materialize in every job, tests awaited before the identity is
embedded and before anything is encrypted, the delivered 610 application steps kept unchanged),
the effective-tree replay and restoration (synthetic repositories and the real 611 history), the
reuse guard, the republication of retained archives and the trigger-commit evaluation.

In CI (BUILD_NUMBER set) the manifest of that build must be frozen; locally a draft manifest is
checked for everything a draft carries and the pending RPCS3 Core pin is reported as pending.
"""
from __future__ import annotations

import ast
import copy
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.github/diagnostics'))

import standard_delivery as sd  # noqa: E402
import retained_components as retained  # noqa: E402
import rpcs3_core_component as rpcs3  # noqa: E402

try:
    import yaml
except ImportError:  # PyYAML is optional: the recipe parses its own workflow without it.
    yaml = None

WORKFLOW = ROOT / sd.WORKFLOW
WORKFLOW610 = ROOT / '.github/workflows/rewind610-delivery.yml'
CI_BUILD = os.environ.get('BUILD_NUMBER')
REPO = sd.Repo(ROOT)
B06888A9 = 'b06888a98dad1e8cb96cb4eaa929250da471cc14'
REVIEWED_RA = '6f4244a006cb1a445feb199f77980e178b3171b7'
GAME_BOX = 'cdba032126fff1b583b4a7cd2e75847f0ff851a4'
# Application steps of the delivered 610 workflow that the standard workflow keeps byte-identical.
UNCHANGED_610_STEPS = (
    'Select Xcode 26.3 for NeoPlay and Google Cast', 'Set up Flutter 3.47.2', 'Resolve locked Dart dependencies',
    'Prepare lightweight build tools', 'Generate iOS host', 'Restore unchanged canonical StikJIT compilation interfaces',
    'Build canonical StikJIT from pinned sources for iOS 18 26 and 27', 'Install verified cached StikJIT interfaces',
    'Prepare the retained libretro artifact destination',
    "Package the standalone MeloNX app's own MoltenVK (maintainer exception, pinned upstream bytes)",
    'Prepare emulator build definitions', 'Configure release host',
    'Align application and extension versions to the pubspec version',
    'Compile Release device binary with measured AOT and Xcode phases',
    'Embed NeoPlay source identity and dependency acknowledgements', 'Embed verified RPCS3 Core and signing metadata',
    'Embed lazy-loaded ARMSX2 Core framework', 'Embed lazy-loaded libretro cores, MoltenVK and system assets',
    'Embed legal, license and source notices', 'Embed verified MeloNX runtime and actual build-source notices',
    'Embed the standalone MeloNX MoltenVK with its provenance and Apache-2.0 notice',
    'Preserve sealed IPA and source receipts before final compatibility validators',
    'Preserve sealed recovery piece 1 of 4', 'Preserve sealed recovery piece 2 of 4',
    'Preserve sealed recovery piece 3 of 4', 'Preserve sealed recovery piece 4 of 4',
    'Verify actual packaged MeloNX exports, helper identity and native notices',
    'Finalize observed timings and artifact identity', 'Prepare encrypted delivery and evidence',
    'Upload encrypted IPA and verification reports', 'Prepare bounded encrypted transport pieces',
    'Upload encrypted transport piece 1 of 4', 'Upload encrypted transport piece 2 of 4',
    'Upload encrypted transport piece 3 of 4', 'Upload encrypted transport piece 4 of 4',
    'Collect diagnostic evidence', 'Upload diagnostics', 'Remove temporary secrets',
)
# Test-job steps of the fresh 610 jobs (git object 6d17e6d) kept identical.
UNCHANGED_TEST_STEPS = ('Set up Flutter3.47.2', 'Resolve exact workspace lock', 'Select targeted Xcode16.4 and Swift6',
                        'Prepare real Flutter iOS headers and simulator project tool')
RUN_STEPS = {'flutter': 'Run source contracts and Flutter behavior',
             'native': 'Run actual Xcode16.4 tests and host compilation'}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def manifests():
    result = {}
    for path in sorted((ROOT / sd.MANIFESTS).glob('*.json')):
        if path.stem.isdecimal():
            result[int(path.stem)] = json.loads(path.read_bytes())
    return result


def workflow():
    return sd.load_yaml_subset(WORKFLOW.read_text())


def steps(job):
    return workflow()['jobs'][job]['steps']


def step(job, name):
    found = [s for s in steps(job) if s.get('name') == name]
    assert len(found) == 1, name
    return found[0]


def run_text(job):
    return '\n'.join(s.get('run', '') for s in steps(job))


def current_manifest():
    values = manifests()
    build = int(CI_BUILD) if CI_BUILD else max(values)
    return build, values[build]


@lru_cache(maxsize=None)
def effective_of_head():
    """The effective tree of the current manifest at its freeze commit (frozen) or at HEAD (draft)."""
    build, manifest = current_manifest()
    head = manifest['product'].get('freezeCommit') or REPO.commit('HEAD')
    reviewed = [c['commit'] for c in manifest['product']['reviewedCommits']]
    source_only = [c['commit'] for c in manifest['product']['sourceOnly']]
    return sd.effective_tree(REPO, manifest['base']['source'], head, reviewed, source_only)


class Git:
    """A synthetic repository for the replay, restoration and reuse tests."""

    def __init__(self, root):
        self.root = Path(root)
        self.run('init', '-q')
        self.run('checkout', '-q', '-b', 'Claude')

    def run(self, *args):
        return subprocess.run(['git', '-c', 'user.name=contract', '-c', 'user.email=contract@example.invalid',
                               '-c', 'commit.gpgsign=false', '-c', 'core.hooksPath=/dev/null', *args],
                              cwd=self.root, check=True, capture_output=True).stdout.decode().strip()

    def write(self, path, data, mode=0o644):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_symlink():
            target.unlink()
        target.write_bytes(data if isinstance(data, bytes) else data.encode())
        target.chmod(mode)

    def symlink(self, path, destination):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        if os.path.lexists(target):
            target.unlink()
        os.symlink(destination, target)

    def remove(self, path):
        (self.root / path).unlink()

    def commit(self, message):
        self.run('add', '-A')
        self.run('commit', '-q', '--allow-empty', '-m', message)
        return self.run('rev-parse', 'HEAD')


def frozen_product(repo, base, head, reviewed, source_only):
    tree = sd.effective_tree(repo, base, head, reviewed, source_only)
    return tree, dict(base=dict(source=base), product=dict(
        freezeCommit=head, effective=tree['effectiveRecords'], restore=tree['restoreRecords'],
        effectiveDigest=tree['effectiveDigest'], productFiles=tree['productFiles']))


class ManifestSchema(unittest.TestCase):
    def test_every_manifest_is_valid(self):
        values = manifests()
        self.assertTrue(values, 'No delivery manifest under build-utils/delivery')
        for build, value in values.items():
            self.assertEqual(sd.manifest_errors(value), [], build)
            self.assertEqual(value['build'], build)
        if CI_BUILD:
            self.assertEqual(values[int(CI_BUILD)]['status'], 'frozen', 'CI delivers only a frozen manifest')
            self.assertEqual(values[int(CI_BUILD)]['frozen']['inCI'], False)

    def test_base_receipts_and_proof_files(self):
        _, manifest = current_manifest()
        images = sd.verify_base(manifest)
        base = manifest['base']
        self.assertEqual(len(images), base['identity']['images'])
        self.assertEqual(REPO.tree_of(base['source']), base['tree'])
        self.assertTrue(REPO.is_ancestor(base['source'], 'HEAD'))
        receipt = json.loads((ROOT / base['receipt']['path']).read_bytes())
        self.assertEqual(len(receipt['proofFiles']), base['receipt']['proofFiles'])
        self.assertIn('jobs', receipt['execution'], 'The base receipt uses the 610 schema (execution.jobs)')
        broken = copy.deepcopy(manifest)
        broken['base']['jobs']['application']['id'] += 1
        with self.assertRaises(ValueError):
            sd.verify_base(broken)
        broken = copy.deepcopy(manifest)
        broken['base']['receipt']['sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            sd.verify_base(broken)

    def test_recipient(self):
        _, manifest = current_manifest()
        recipient = manifest['recipient']
        raw = (ROOT / recipient['path']).read_bytes()
        self.assertEqual(sha(raw), recipient['sha256'])
        self.assertTrue(raw.startswith(b'-----BEGIN PUBLIC KEY-----'))
        self.assertEqual(sd.recipient_check(manifest, {'DELIVERY_RECIPIENT': recipient['path']})['sha256'],
                         recipient['sha256'])
        for environment in ({}, {'DELIVERY_RECIPIENT': ''}, {'DELIVERY_RECIPIENT': 'build-utils/delivery-422-recipient.pem'}):
            with self.assertRaises(ValueError):
                sd.recipient_check(manifest, environment)
        if CI_BUILD:
            sd.recipient_check(manifest)

    def test_images(self):
        _, manifest = current_manifest()
        base = sd.verify_base(manifest)
        images = manifest['images']
        for name in ('Frameworks/libRPCS3Core.dylib', 'Frameworks/MeloNXCore.framework/MeloNXCore',
                     'Frameworks/rpcs3_internal_bridge.framework/rpcs3_internal_bridge',
                     'Frameworks/retro_achievements_session.framework/retro_achievements_session',
                     'Frameworks/App.framework/App', 'Runner'):
            self.assertIn(name, images['mustChange'])
        retained_names = []
        for patterns in images['retained'].values():
            retained_names += sd.expand_image_patterns(patterns, sorted(base))
        self.assertEqual(len(retained_names), len(set(retained_names)))
        self.assertEqual(sum(n.endswith('_libretro') for n in retained_names), 35)
        self.assertFalse(set(retained_names) & set(images['mustChange']))
        self.assertTrue(set(images['replaced'].values()) <= set(base) and set(images['mustChange']) <= set(base))
        tree = effective_of_head()
        derived, _ = sd.images_for_paths(sorted(tree['effectiveRecords']), set(base))
        self.assertLessEqual(set(derived), set(images['mustChange']) | set(images.get('derivedMustChange', [])))
        if manifest['status'] == 'frozen':
            self.assertEqual(images['baseImages'], sorted(base))
            self.assertEqual(images['retainedFingerprints'], {n: base[n] for n in sorted(retained_names)})

    def test_image_rules(self):
        base = {'A': '1', 'B': '2', 'C': '3', 'Runner': '4'}
        manifest = dict(images=dict(retainedFingerprints={'A': '1'}, replacedFingerprints={'B': '9'},
                                    mustChange=['B', 'Runner'], added=[], removed=[]))
        report = sd.check_images({'A': '1', 'B': '9', 'C': '7', 'Runner': '5'}, base, manifest)
        self.assertEqual(report['undeclaredChanges'], ['C'])
        for actual in ({'A': '0', 'B': '9', 'C': '3', 'Runner': '5'}, {'A': '1', 'B': '2', 'C': '3', 'Runner': '5'},
                       {'A': '1', 'B': '9', 'C': '3', 'Runner': '4'}, {'A': '1', 'B': '9', 'Runner': '5'},
                       {'A': '1', 'B': '9', 'C': '3', 'Runner': '5', 'D': '6'}):
            with self.assertRaises(ValueError):
                sd.check_images(actual, base, manifest)


class Components(unittest.TestCase):
    def test_melonx_pin_is_verified_and_bound_to_its_contract(self):
        import melonx_reads_core_component as melonx
        _, manifest = current_manifest()
        pin = melonx.pin()
        self.assertEqual(manifest['components']['melonx']['pin'], melonx.PIN)
        self.assertEqual(pin['contractSha256'], sha((ROOT / melonx.CONTRACT).read_bytes()))
        self.assertEqual(pin['name'], 'MeloNX-engine-' + pin['source'])
        self.assertTrue(REPO.is_ancestor(pin['source'], 'HEAD'))
        if manifest['status'] == 'frozen':
            self.assertEqual(manifest['components']['melonx']['pinSha256'], sha((ROOT / melonx.PIN).read_bytes()))

    def test_rpcs3_pin(self):
        _, manifest = current_manifest()
        pin = rpcs3.load_pin(ROOT / manifest['components']['rpcs3']['pin'])
        report = rpcs3.pin_errors(pin)
        self.assertEqual(report['errors'], [])
        self.assertEqual(len(rpcs3.expected_exports(pin)), pin['exports']['count'])
        self.assertEqual(rpcs3.added_symbols(pin), sorted('_rpcs3_ios_ra_' + n for n in
                                                         ('api_version', 'set_frame_callback', 'read_memory',
                                                          'get_session_info')))
        if pin['status'] == 'pending':
            print(f"\nRPCS3 Core pin pending: {len(report['missing'])} producer values unknown", flush=True)
            self.assertNotEqual(manifest['status'], 'frozen', 'A frozen manifest cannot carry a pending pin')
            with self.assertRaises(ValueError):
                rpcs3.pinned(pin)
            with self.assertRaises(ValueError):
                rpcs3.core_run(pin)
        else:
            rpcs3.pinned(pin)
        if manifest['status'] == 'frozen':
            self.assertEqual(manifest['components']['rpcs3']['pinSha256'],
                             sha((ROOT / manifest['components']['rpcs3']['pin']).read_bytes()))

    def synthetic_pin(self):
        pin = rpcs3.load_pin()
        canonical = json.loads((ROOT / rpcs3.CANONICAL).read_bytes())
        source = 'a' * 40
        pin['status'] = 'verified'
        pin['producer']['workflow'] = '.github/workflows/rpcs3-core611.yml'
        for part in ('core', 'hostTests'):
            pin['producer'][part].update(jobName=part, steps=['step'], source=source, run=1, attempt=1, job=2,
                                         artifact=3, name='RPCS3Core-611-' + source, bytes=10, sha256='b' * 64,
                                         expiresAt='2026-12-01T00:00:00Z')
        pin['producer']['hostTests']['names'] = ['lr-full-queue']
        pin['core'].update(type='rpcs3-ios-core611', dylibBytes=1, dylibSha256='c' * 64, identitySha256='d' * 64,
                           proofMember='core611-proof.json', proofSha256='e' * 64, payloadFingerprint='f' * 64)
        pin['canonical'].update(patchSha256=canonical['patch_sha256'], postimages=len(canonical['files_sha256']))
        return pin

    def test_synthetic_complete_pin(self):
        pin = self.synthetic_pin()
        self.assertEqual(rpcs3.pin_errors(pin), dict(status='verified', missing=[], errors=[]))
        rpcs3.pinned(pin)
        mutations = (
            lambda p: p['exports'].update(count=91),
            lambda p: p['exports']['added'].pop(),
            lambda p: p['host'].update(sha256='0' * 64),
            lambda p: p['hostStore'].update(sha256='0' * 64),
            lambda p: p.update(abi=31),
            lambda p: p['canonical'].update(patchSha256='0' * 64),
            lambda p: p['canonical'].update(postimages=1),
            lambda p: p['producer']['core'].update(name='RPCS3Core-611-other'),
            lambda p: p['core'].update(proofSha256=None),
            lambda p: p.update(status='pending'),
        )
        for mutate in mutations:
            broken = copy.deepcopy(pin)
            mutate(broken)
            with self.assertRaises(ValueError):
                rpcs3.pinned(broken)

    def test_retained_pins_equal_the_delivered_recipes(self):
        import rewind608_producers as producers608
        import rewind609_delivery as delivered609
        _, manifest = current_manifest()
        components = manifest['components']
        for kind in retained.NATIVES:
            spec, pin = components[kind], delivered609.REUSED_ARTIFACTS[kind]
            origin = spec['origin']
            self.assertEqual((origin['job'], origin['artifact'], origin['bytes'], origin['sha256']),
                             (pin['job'], pin['artifact'], pin['bytes'], pin['sha256']))
            self.assertEqual(origin['jobName'], producers608.JOBS[kind])
            self.assertEqual(set(origin['steps']), producers608.REQUIRED_STEPS[kind])
            self.assertEqual((origin['source'], origin['tree'], origin['run'], origin['attempt']),
                             tuple(delivered609.REUSED[k] for k in ('source', 'tree', 'run', 'attempt')))
            self.assertEqual(spec['payloadFingerprint'], delivered609.RETAINED_CORES[kind])
            self.assertEqual(sha((ROOT / spec['consumedBy']['receipt']).read_bytes()), spec['consumedBy']['sha256'])
            self.assertTrue(retained.same_definition_as_producers608(kind))
        self.assertEqual(components['dolphin']['upstreamRevision'], producers608.DOLPHIN_SOURCE)
        self.assertEqual(components['armsx2']['upstreamRevision'],
                         json.loads((ROOT / 'build-utils/armsx2/source.json').read_bytes())['revision'])
        for kind in retained.ARCHIVES:
            origin, pin = components[kind]['origin'], delivered609.RETAINED_ARCHIVES[kind]
            self.assertEqual({k: origin[k] for k in ('artifact', 'run', 'source', 'name', 'bytes', 'sha256')},
                             {k: pin[k] for k in ('artifact', 'run', 'source', 'name', 'bytes', 'sha256')})
            self.assertEqual(components[kind]['destination'], pin['destination'])

    def test_donor_pin_equals_the_preparer(self):
        _, manifest = current_manifest()
        donor = manifest['components']['donor']
        tree = ast.parse((ROOT / donor['preparer']).read_text())
        constants = {node.targets[0].id: node.value.value for node in tree.body if isinstance(node, ast.Assign) and
                     isinstance(node.targets[0], ast.Name) and isinstance(node.value, ast.Constant)}
        self.assertEqual(donor['sha256'], constants['BASELINE_IPA_SHA'])
        self.assertEqual(donor['release'], constants['BASELINE_RELEASE'])
        self.assertEqual(str(donor['build']), constants['BASELINE_BUILD'])
        self.assertEqual(donor['url'], f"https://github.com/{sd.REPOSITORY}/releases/download/{donor['release']}/{donor['asset']}")

    def test_retained_inputs_unchanged_since_the_base(self):
        _, manifest = current_manifest()
        tree = effective_of_head()
        reader = sd.EffectiveReader(REPO, tree['effective'])
        self.assertGreater(sd.retained_inputs_unchanged(manifest, REPO, reader.listing, reader.read), 0)
        if CI_BUILD:
            sd.retained_inputs_unchanged(manifest, REPO, sd.worktree_listing, sd.read_worktree)


class Workflow(unittest.TestCase):
    def test_subset_parser_agrees_with_pyyaml(self):
        if yaml is None:
            self.skipTest('PyYAML is not installed; the recipe does not need it')
        for path in (WORKFLOW, WORKFLOW610):
            expected = yaml.safe_load(path.read_text())
            expected['on'] = expected.pop(True, expected.get('on'))
            self.assertEqual(sd.load_yaml_subset(path.read_text()), expected, path.name)

    def test_trigger_concurrency_and_constant_job_names(self):
        value = workflow()
        self.assertEqual(value['on'], {'push': {'branches': ['Claude']}})
        self.assertEqual(value['concurrency'], {'group': 'rewindbox-ipa-delivery-${{ github.ref }}',
                                                'cancel-in-progress': False})
        self.assertEqual(tuple(value['jobs']), sd.JOB_NAMES)
        for name, job in value['jobs'].items():
            self.assertEqual(job['name'], name)
        self.assertEqual(value['permissions'], {'contents': 'read', 'actions': 'read'})
        gate = value['jobs']['preflight']['if']
        self.assertIn("startsWith(github.event.head_commit.message, '" + sd.TRIGGER_MARKER + "')", gate)
        self.assertIn("github.ref == 'refs/heads/Claude'", gate)
        self.assertNotIn('workflow_dispatch', WORKFLOW.read_text())

    def test_checkout_then_materialize_in_every_job(self):
        for job in sd.JOB_NAMES:
            first, second = steps(job)[:2]
            self.assertEqual(first['uses'], 'actions/checkout@v4', job)
            self.assertEqual(first['with'], {'ref': '${{ github.sha }}', 'fetch-depth': 0, 'persist-credentials': False})
            self.assertEqual(second['name'], sd.MATERIALIZE_STEP)
            self.assertEqual(second['run'], 'python3 -B .github/diagnostics/standard_delivery.py materialize')
            self.assertEqual(sum(s.get('uses', '').startswith('actions/checkout') for s in steps(job)), 1, job)
            for line in run_text(job).splitlines():
                if re.search(r'\bgit\s+(checkout|reset|stash|clean|switch|restore|read-tree)\b', line):
                    self.assertRegex(line.strip(), r"^(git -C \.native-sources/|subprocess\.run\(\['git','-C',path)", line)

    def test_only_standard_delivery_operations(self):
        text = WORKFLOW.read_text()
        calls = re.findall(r'\.github/diagnostics/([\w.]+)(?: (\S+))?', text)
        self.assertTrue(calls)
        for script, operation in calls:
            self.assertEqual(script, 'standard_delivery.py')
            self.assertIn(operation, sd.CI_OPERATIONS + ('contract',))
        for retired in (r'rewind\d', r'rpcs3core\d', r'rpcs3runtime\d', r'Build\d', r'build\d{3}', 'sys.path.insert',
                        'import rewind', 'from rewind', 'melonx-materialize', 'REUSED_TESTS'):
            self.assertIsNone(re.search(retired, text), retired)

    def test_no_build_number_literal(self):
        text = WORKFLOW.read_text()
        numbers = [int(n) for n in re.findall(r'(?<![\w.\-])(\d{3})(?![\w.\-])', text)]
        self.assertEqual([n for n in numbers if n >= 400], [], 'A build-number literal is in the workflow')
        for build, manifest in manifests().items():
            self.assertNotIn(str(build), text)
            self.assertNotIn(str(manifest['base']['build']), text)

    def test_numbers_come_from_preflight_outputs(self):
        value = workflow()
        for job in ('flutter', 'native', 'application'):
            environment = value['jobs'][job]['env']
            self.assertEqual(environment['BUILD_NUMBER'], '${{ needs.preflight.outputs.build }}')
            self.assertEqual(environment['DELIVERY_RECIPIENT'], '${{ needs.preflight.outputs.recipient }}')
        self.assertEqual(value['jobs']['application']['env']['ARTIFACT_NAME'],
                         '${{ needs.preflight.outputs.artifact-prefix }}-attempt${{ github.run_attempt }}-cold')
        self.assertNotIn('BUILD_NUMBER', value['env'])
        contract = step('preflight', 'Run the delivery contract')['env']
        self.assertEqual(contract, {'BUILD_NUMBER': '${{ steps.manifest.outputs.build }}',
                                    'DELIVERY_RECIPIENT': '${{ steps.manifest.outputs.recipient }}'})
        for name in ('ARMSX2_CORE_HOST_SHA', 'ARMSX2_CORE_RUN_ID', 'DOLPHIN_CORE_HOST_SHA', 'DOLPHIN_CORE_RUN_ID',
                     'LIBRETRO_CORES_VALIDATED_SHA', 'RPCS3_CORE_HOST_SHA', 'RPCS3_CORE_RUN_ID'):
            self.assertNotIn(name, WORKFLOW.read_text())

    def test_application_builds_in_parallel_and_awaits_the_tests(self):
        value = workflow()
        self.assertEqual(value['jobs']['application']['needs'], 'preflight')
        for group in sd.TEST_GROUPS:
            self.assertEqual(value['jobs'][group]['needs'], 'preflight')
            self.assertIn(f"needs.preflight.outputs.{group}-mode == 'fresh'", value['jobs'][group]['if'])
        names = [s['name'] for s in steps('application')]
        runs = [s.get('run', '') for s in steps('application')]
        awaited = names.index('Wait for and authenticate the test jobs and the fresh delivery contract')
        embed = next(i for i, r in enumerate(runs) if 'standard_delivery.py embed build/' in r)
        seal = next(i for i, r in enumerate(runs) if 'standard_delivery.py seal' in r)
        encrypted = [i for i, r in enumerate(runs) if 'delivery_cipher.py artifact' in r and 'build/delivery ' not in r]
        uploads = [i for i, s in enumerate(steps('application')) if s.get('uses', '').startswith('actions/upload-artifact')
                   and s['name'] != 'Upload diagnostics' and not s['name'].startswith('Republish ')]
        compile_step = names.index('Compile Release device binary with measured AOT and Xcode phases')
        self.assertLess(compile_step, awaited)
        self.assertEqual(embed, awaited + 1)
        self.assertLess(awaited, seal)
        self.assertTrue(encrypted and uploads and min(encrypted + uploads) > seal)
        self.assertNotIn('if', steps('application')[awaited])

    def test_test_jobs_come_from_the_fresh_610_jobs(self):
        old = sd.load_yaml_subset(REPO.show('6d17e6d', '.github/workflows/rewind610-delivery.yml').decode())
        for group in sd.TEST_GROUPS:
            before = {s['name']: s for s in old['jobs'][group]['steps']}
            after = {s['name']: s for s in steps(group)}
            for name in UNCHANGED_TEST_STEPS:
                if name in before:
                    self.assertEqual(after[name], before[name], name)
            self.assertEqual(workflow()['jobs'][group]['runs-on'], old['jobs'][group]['runs-on'])
            self.assertEqual(workflow()['jobs'][group]['timeout-minutes'], old['jobs'][group]['timeout-minutes'])
            self.assertEqual(step(group, RUN_STEPS[group])['run'],
                             f'python3 -B .github/diagnostics/standard_delivery.py tests {group}')
            self.assertIn(RUN_STEPS[group], before, 'The group step keeps its delivered 610 name')
        self.assertEqual(step('native', 'Select targeted Xcode16.4 and Swift6')['with'], {'xcode-version': '16.4'})

    def test_required_steps_exist(self):
        for job, names in sd.REQUIRED_STEPS.items():
            self.assertTrue(names <= {s['name'] for s in steps(job)}, job)
        upload = step('preflight', 'Preserve the delivery contract log')
        self.assertEqual(upload['id'], 'contract-log')
        self.assertEqual(upload['with']['path'], 'build/standard-delivery/contract/')
        outputs = workflow()['jobs']['preflight']['outputs']
        self.assertEqual(outputs['contract-artifact-digest'], '${{ steps.contract-log.outputs.artifact-digest }}')
        for group in sd.TEST_GROUPS:
            self.assertEqual(step(group, 'Preserve actual command results')['with']['name'],
                             '${{ needs.preflight.outputs.artifact-prefix }}-attempt${{ github.run_attempt }}-tests-' + group)

    def test_delivered_application_steps_are_unchanged(self):
        old = {s['name']: s for s in sd.load_yaml_subset(WORKFLOW610.read_text())['jobs']['application']['steps']}
        new = {s['name']: s for s in steps('application')}
        for name in UNCHANGED_610_STEPS:
            self.assertEqual(new[name], old[name], name)
        environment = workflow()['jobs']['application']['env']
        old_environment = sd.load_yaml_subset(WORKFLOW610.read_text())['jobs']['application']['env']
        for key in ('IPA_NAME', 'HOMEBREW_NO_AUTO_UPDATE', 'BUNDLE_GEMFILE', 'SCREENSCRAPER_DEV_ID',
                    'SCREENSCRAPER_DEV_PASSWORD', 'DELIVERY_METRICS', 'CACHE_NAMESPACE', 'GH_TOKEN', 'BUNDLE_PATH',
                    'DELIVERY_MODE'):
            self.assertEqual(environment[key], old_environment[key], key)
        self.assertEqual(workflow()['jobs']['application']['runs-on'], 'macos-15')

    def test_validators_pods_and_retention(self):
        text = run_text('application')
        for validator in ('validate_melonx_ipa.py', 'validate_legal_bundle_ipa.py', 'validate_no_kartpad_ipa.py',
                          'validate_no_dusklight_ipa.py', 'standard_delivery.py validate', 'standard_delivery.py structure'):
            self.assertIn(validator, text)
        pods = step('application', 'Verify central session pod is in the actual generated host')['run']
        self.assertIn("rpcs3_internal_bridge.podspec.json", pods)
        self.assertIn("{'retro_achievements_session', 'achievement_translation'}", pods)
        for item in steps('application'):
            if item.get('uses', '').startswith('actions/upload-artifact'):
                expected = 90 if item['name'].startswith('Republish ') else 14
                self.assertEqual(item['with']['retention-days'], expected, item['name'])

    def test_republication_steps(self):
        _, manifest = current_manifest()
        value = workflow()
        job = value['jobs']['republish']
        # An independent job right after preflight: a later application failure (or a retry after an
        # expiry) never loses the archives the next build retains. Component archives only; never the IPA.
        self.assertEqual(job['needs'], 'preflight')
        self.assertEqual(job['if'], "${{ needs.preflight.result == 'success' && needs.preflight.outputs.build != '' }}")
        self.assertEqual(job['name'], 'republish')
        self.assertIn('republish', retained.REPUBLISHING_JOBS)
        names = {s['name']: s for s in steps('republish')}
        order = [s['name'] for s in steps('republish')]
        self.assertEqual(order.index('Materialize the frozen effective product tree'), 1)
        self.assertTrue(set(manifest['republish']) <= set(sd.REPUBLISHED_KINDS))
        stage = order.index('Stage the authenticated component archives for republication')
        for operation in ('download-rpcs3', 'download-melonx', 'download-libretro', 'download-melonx-dependencies',
                          'authenticate-dolphin', 'authenticate-armsx2'):
            index = next(i for i, s in enumerate(steps('republish'))
                         if s.get('run', '').endswith('standard_delivery.py ' + operation))
            self.assertLess(index, stage)
        for kind in sd.REPUBLISHED_KINDS:
            item = names[retained.republish_step(kind)]
            self.assertEqual(item['with']['path'], f'build/republish/{kind}/')
            self.assertEqual(item['if'], "${{ hashFiles('build/republish/" + kind + "/republication.json') != '' }}")
            self.assertGreater(order.index(retained.republish_step(kind)), stage)
            self.assertNotIn('ipa', item['with']['path'].lower())
        self.assertFalse(any(s['name'].startswith('Republish ') for s in steps('application')))
        self.assertFalse(any('delivery_cipher' in s.get('run', '') or 'IPA' in s['name'] for s in steps('republish')))


class EffectiveTreeSynthetic(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='standard-delivery-')
        self.git = Git(self.directory.name)
        self.repo = sd.Repo(self.directory.name)

    def tearDown(self):
        self.directory.cleanup()

    def base(self):
        g = self.git
        g.write('lib/a.dart', 'a0')
        g.write('lib/b.dart', 'b0')
        g.write('lib/keep.dart', 'k0')
        g.write('tools/run.sh', '#!/bin/sh\n', 0o755)
        g.symlink('lib/link', 'a.dart')
        g.write('docs/x.md', 'x0')
        return g.commit('base')

    def test_reviewed_after_source_only_on_the_same_path_fails(self):
        base = self.base()
        self.git.write('lib/a.dart', 'a-source-only')
        source_only = self.git.commit('concurrent work')
        self.git.write('lib/a.dart', 'a-reviewed')
        reviewed = self.git.commit('reviewed change built on the concurrent work')
        tree = sd.replay(self.repo, base, reviewed, [reviewed], [source_only])
        self.assertEqual([c['path'] for c in tree['conflicts']], ['lib/a.dart'])
        self.assertEqual(tree['effective']['lib/a.dart'], self.repo.entries(base)['lib/a.dart'])

    def test_restoration_of_modes_symlinks_deletions_and_additions(self):
        base = self.base()
        g = self.git
        g.write('lib/new.dart', 'n1')
        g.write('lib/b.dart', 'b1')
        g.symlink('lib/link2', 'b.dart')
        r1 = g.commit('reviewed: add new, change b, add symlink')
        g.write('lib/a.dart', 'a-concurrent')
        g.remove('lib/keep.dart')
        g.write('lib/extra.dart', 'e')
        (g.root / 'tools/run.sh').chmod(0o644)
        g.symlink('lib/link', 'b.dart')
        g.write('docs/x.md', 'x1')
        s1 = g.commit('source-only for a later build')
        g.write('docs/y.md', 'y')
        head = g.commit('recipe-only docs')
        tree, manifest = frozen_product(self.repo, base, head, [r1], [s1])
        self.assertEqual(tree['conflicts'] + tree['unclassified'], [])
        self.assertEqual([c['role'] for c in tree['commits']], ['reviewed', 'sourceOnly', 'recipe'])
        restore = tree['restoreRecords']
        self.assertEqual(sorted(restore), ['lib/a.dart', 'lib/extra.dart', 'lib/keep.dart', 'lib/link', 'tools/run.sh'])
        self.assertIsNone(restore['lib/extra.dart'])
        self.assertEqual(restore['tools/run.sh']['mode'], '100755')
        self.assertEqual(restore['lib/link']['mode'], '120000')
        self.assertEqual(sorted(tree['effectiveRecords']), ['lib/b.dart', 'lib/link2', 'lib/new.dart'])
        result = sd.materialize_tree(self.repo, manifest, head)
        self.assertEqual(result['effectiveDigest'], tree['effectiveDigest'])
        root = g.root
        self.assertEqual((root / 'lib/a.dart').read_text(), 'a0')
        self.assertEqual((root / 'lib/keep.dart').read_text(), 'k0')
        self.assertFalse(os.path.lexists(root / 'lib/extra.dart'))
        self.assertTrue(os.stat(root / 'tools/run.sh').st_mode & 0o100)
        self.assertEqual(os.readlink(root / 'lib/link'), 'a.dart')
        self.assertEqual((root / 'lib/new.dart').read_text(), 'n1')
        self.assertEqual((root / 'docs/x.md').read_text(), 'x1', 'Recipe paths are never restored')
        sd.verify_materialized(self.repo, manifest, head)
        (root / 'lib/b.dart').write_text('tampered')
        with self.assertRaises(ValueError):
            sd.verify_materialized(self.repo, manifest, head)
        (root / 'lib/b.dart').write_text('b1')
        (root / 'lib/b.dart').chmod(0o755)
        with self.assertRaises(ValueError):
            sd.verify_materialized(self.repo, manifest, head)

    def test_unclassified_merges_and_late_product_commits(self):
        base = self.base()
        self.git.write('lib/a.dart', 'a1')
        unclassified = self.git.commit('unreviewed product change')
        tree = sd.replay(self.repo, base, unclassified, [], [])
        self.assertEqual([c['commit'] for c in tree['unclassified']], [unclassified])
        tree, manifest = frozen_product(self.repo, base, unclassified, [unclassified], [])
        self.git.write('docs/z.md', 'z')
        recipe = self.git.commit('recipe after the freeze')
        self.assertEqual(sd.materialize_tree(self.repo, manifest, recipe)['laterRecipeOnlyCommits'], [recipe])
        self.git.write('lib/b.dart', 'late')
        late = self.git.commit('product after the freeze')
        with self.assertRaises(ValueError):
            sd.materialize_tree(self.repo, manifest, late)
        self.git.run('checkout', '-q', '-b', 'side', base)
        self.git.write('lib/side.dart', 's')
        self.git.commit('side')
        self.git.run('checkout', '-q', 'Claude')
        self.git.run('merge', '-q', '--no-edit', '--no-ff', 'side')
        with self.assertRaises(ValueError):
            sd.replay(self.repo, base, self.git.run('rev-parse', 'HEAD'), [], [])

    def test_recipe_patterns(self):
        for path in ('.github/workflows/x.yml', 'docs/a/b.md', 'AGENTS.md', '.claude/settings.json',
                     'build-utils/delivery/611.json', 'build-utils/delivery-611-recipient.pem',
                     'build-utils/rpcs3/core-pin.json', 'build-utils/melonx/reads-core-pin.json',
                     'test/standard_delivery_contract_test.py', 'build-utils/verify_downloaded_delivery.py'):
            self.assertTrue(sd.is_recipe(path), path)
        for path in ('lib/a.dart', 'test/x_test.py', 'build-utils/rpcs3/canonical-source.json', 'packages/a/README.md',
                     'build-utils/x/delivery-1-recipient.pem', 'build-utils/melonx/reads-core-contract.json', 'pubspec.yaml'):
            self.assertFalse(sd.is_recipe(path), path)
        self.assertEqual(sd.recipe_definition_sha(), sd.sha(sd.canonical(sd.RECIPE_DEFINITION)))


class EffectiveTree611(unittest.TestCase):
    def test_replay_of_the_build_history(self):
        _, manifest = current_manifest()
        tree = effective_of_head()
        self.assertEqual(tree['conflicts'], [])
        self.assertEqual(tree['missing'], [])
        if manifest['status'] == 'draft':
            # The freeze refuses these; a draft only reports them.
            for item in tree['unclassified']:
                print(f"\nTo classify before the freeze: {item['commit'][:12]} {item['subject']} "
                      f"({item['productPaths']} product paths)", flush=True)
        else:
            self.assertEqual(tree['unclassified'], [], 'A frozen manifest classifies every product commit')
        if manifest['status'] == 'frozen':
            product = manifest['product']
            self.assertEqual(product['effective'], tree['effectiveRecords'])
            self.assertEqual(product['restore'], tree['restoreRecords'])
            self.assertEqual(product['effectiveDigest'], tree['effectiveDigest'])
            self.assertEqual(product['recipeDefinitionSHA256'], sd.recipe_definition_sha())

    def test_source_only_work_is_restored_for_611(self):
        build, manifest = current_manifest()
        if build != 611:
            self.skipTest('611-specific expectations')
        tree = effective_of_head()
        restore = tree['restoreRecords']
        deferred = tree['deferred'][B06888A9]
        pending = {path for item in tree['unclassified'] for path in item['paths']}
        self.assertEqual(sorted(restore), sorted(set(deferred) | pending),
                         'Exactly the deferred b06888a9 product paths (and paths of commits still to classify) differ')
        entries = REPO.entries(REVIEWED_RA)
        for path in [p for p in deferred if p.startswith('lib/l10n/app_locale')] + [
                'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3Achievements.mm']:
            self.assertEqual(restore[path]['gitBlob'], entries[path][1], path)
        added = [p for p, e in restore.items() if e is None]
        self.assertTrue(added and all(p not in entries for p in added))
        self.assertTrue(any(p.startswith('packages/libretro_internal_bridge/ios/ThirdParty/libchdr/') for p in added))
        self.assertNotIn('lib/l10n/game_box_locale.dart', restore)
        self.assertEqual(tree['effective']['lib/l10n/game_box_locale.dart'], REPO.entries(GAME_BOX)['lib/l10n/game_box_locale.dart'])

    def test_group_commands_exist_in_the_effective_tree(self):
        _, manifest = current_manifest()
        tree = effective_of_head()
        reader = sd.EffectiveReader(REPO, tree['effective'])
        for group in sd.TEST_GROUPS:
            commands = sd.expand_commands(group, manifest['tests'][group], reader.listing)
            if manifest['status'] == 'frozen':
                self.assertEqual(manifest['tests'][group]['commands'], commands, group)
            missing = [p for p in sd.command_inputs(commands) if not (reader.exists(p) or
                       (sd.is_recipe(p) and (ROOT / p).exists()))]
            self.assertEqual(missing, [], group)

    def test_embedded_recipe_inputs_cover_the_legal_bundle(self):
        tree = effective_of_head()
        reader = sd.EffectiveReader(REPO, tree['effective'])

        def constants(path, names):
            module = ast.parse(reader.read(path))
            found = {}
            for node in module.body:
                if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id in names:
                    found[node.targets[0].id] = ast.literal_eval(node.value)
            return found
        legal = constants('build-utils/embed_legal_bundle.py', {'CATALOG_CREDIT_DOCUMENTS'})
        evidence = constants('build-utils/collect_build_source_evidence.py', {'SOURCE_DOCUMENTS', 'SOURCE_EVIDENCE'})
        needed = {'LICENSE.md', 'NOTICE.md', 'docs/LEGAL_AND_CREDITS.md'}
        needed |= {'docs/' + n for n in legal['CATALOG_CREDIT_DOCUMENTS'] + evidence['SOURCE_DOCUMENTS']}
        needed |= {'docs/evidence/' + n for n in evidence['SOURCE_EVIDENCE']}
        needed |= set(re.findall(r'cp (docs/\S+) build/delivery-artifact/', WORKFLOW.read_text()))
        self.assertTrue(needed <= set(sd.EMBEDDED_RECIPE_FILES), sorted(needed - set(sd.EMBEDDED_RECIPE_FILES)))
        self.assertIn('docs/licenses/cheats', reader.read('build-utils/embed_legal_bundle.py').decode())
        self.assertTrue(all(sd.is_embedded_recipe_input('docs/licenses/cheats/' + n) for n in ('README.md', 'x.json')))
        for name in sd.EMBEDDED_RECIPE_FILES:
            self.assertTrue((ROOT / name).is_file(), name)


class Groups(unittest.TestCase):
    def test_base_commands_are_the_610_groups(self):
        import rewind610_checks as checks610
        groups = sd.base_groups()
        for group in sd.TEST_GROUPS:
            self.assertEqual([name for name, _ in groups[group]], checks610.command_names(group))
            for (name, argv), (_, old) in zip(groups[group], checks610.GROUPS[group]):
                self.assertEqual(argv, list(sd.CONTRACT_TEST) if name == 'delivery-contract-tests' else list(old))

    def test_611_additions(self):
        build, manifest = current_manifest()
        if build != 611:
            self.skipTest('611-specific expectations')
        tree = effective_of_head()
        reader = sd.EffectiveReader(REPO, tree['effective'])
        flutter = dict((n, a) for n, a in sd.expand_commands('flutter', manifest['tests']['flutter'], reader.listing))
        boxes = sorted(p for p in tree['effective'] if re.fullmatch(r'test/game_box[^/]*_test\.dart', p))
        self.assertGreaterEqual(len(boxes), 19)
        self.assertTrue(set(boxes) <= set(flutter['flutter-behavior']))
        for root in ('packages/rpcs3_internal_bridge/lib', 'lib/services/game_box', 'lib/screens/game_box',
                     'lib/widgets/game_box', 'lib/l10n/game_box_locale.dart', 'lib/repositories/game_repository.dart',
                     'lib/screens/game_screen/game_settings_dialog/game_settings_scrapping_tab.dart'):
            self.assertIn(root, flutter['flutter-analysis'])
        for name, script in (('storage-contract', 'test/storage_contract_test.py'),
                             ('localization-12-locales', 'test/localization_12_locale_coverage_test.py'),
                             ('rpcs3-retroachievements', 'test/rpcs3_retroachievements_test.py')):
            self.assertEqual(flutter[name], ['python3', '-B', script])
        native = dict(sd.expand_commands('native', manifest['tests']['native'], reader.listing))
        self.assertEqual(native['rpcs3-retroachievements-apple-clang'], ['python3', '-B', 'test/rpcs3_retroachievements_test.py'])
        # 611's inputs changed since 610, so both groups first ran fresh; a recipe-only retry may then reuse
        # those passed jobs (AGENTS.md), which requires a complete pin to a 611 run on this branch.
        for group in sd.TEST_GROUPS:
            mode = manifest['tests'][group]['mode']
            self.assertIn(mode, ('fresh', 'reuse'))
            if mode == 'reuse':
                pin = manifest['tests'][group]['reuse']
                self.assertEqual(set(pin), {'source', 'manifest', 'run', 'attempt', 'job', 'artifact', 'artifactName',
                                            'sha256', 'bytes'})
                self.assertEqual(pin['manifest'], 'build-utils/delivery/611.json')
                self.assertTrue(pin['artifactName'].startswith('RewindBox-Build611-' + pin['source']))
                self.assertTrue(pin['artifactName'].endswith('-tests-' + group))

    def test_recipe_reads_of_the_groups(self):
        """The reuse guard compares every recipe file a group may read (scripts it runs, diagnostics
        modules its tests import, recipe paths quoted there); the always-rerun contract is excluded."""
        _, manifest = current_manifest()
        tree = effective_of_head()
        reader = sd.EffectiveReader(REPO, tree['effective'])
        for group in sd.TEST_GROUPS:
            commands = sd.expand_commands(group, manifest['tests'][group], reader.listing)
            reads = sd.recipe_reads(REPO, 'HEAD', commands)
            self.assertEqual(reads, sorted(set(reads)))
            self.assertTrue(all(sd.is_recipe(path) for path in reads))
            for excluded in ('test/standard_delivery_contract_test.py', '.github/diagnostics/standard_delivery.py',
                             sd.WORKFLOW, sd.manifest_path(manifest['build'])):
                self.assertNotIn(excluded, reads, group)
            if group == 'native':
                self.assertIn('.github/diagnostics/rewind608_checks.py', reads)
                self.assertIn('.github/diagnostics/rewind610_checks.py', reads)
            print(f'\n{group}: the reuse guard compares {len(reads)} recipe files read by its commands', flush=True)


class ReuseGuard(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='standard-reuse-')
        self.git = Git(self.directory.name)
        self.repo = sd.Repo(self.directory.name)
        g = self.git
        g.write('lib/a.dart', 'a')
        g.write('.github/diagnostics/helper.py', 'import other\n')
        g.write('.github/diagnostics/other.py', 'VALUE = 1\n')
        self.commands = [['helper', ['python3', '-B', '.github/diagnostics/helper.py']],
                         ['unit', ['python3', '-B', 'test/unit_test.py']]]
        g.write('test/unit_test.py', 'print(1)\n')
        self.tested = dict(schema=1, build=900, product=dict(effectiveDigest='e' * 64),
                           tests=dict(flutter=dict(mode='fresh', commands=self.commands)))
        g.write('build-utils/delivery/900.json', json.dumps(self.tested))
        self.source = g.commit('tested run')
        self.current = copy.deepcopy(self.tested)
        self.current['tests']['flutter'].update(mode='reuse', reuse=dict(
            source=self.source, run=7, attempt=1, job=8, artifact=9, bytes=100, sha256='a' * 64,
            artifactName=sd.artifact_name(900, self.source, 1, 'tests-flutter'), manifest='build-utils/delivery/900.json'))
        g.write('build-utils/delivery/900.json', json.dumps(self.current))
        g.write('docs/retry.md', 'recipe-only retry')
        self.head = g.commit('retry')

    def tearDown(self):
        self.directory.cleanup()

    def api(self, **changes):
        responses = {
            'actions/runs/7/attempts/1': dict(id=7, head_sha=self.source, head_branch='Claude', path=sd.WORKFLOW,
                                              run_attempt=1, event='push'),
            'actions/jobs/8': dict(id=8, name='flutter', head_sha=self.source, run_id=7, run_attempt=1,
                                   status='completed', conclusion='success',
                                   steps=[dict(name=n, conclusion='success') for n in sd.REQUIRED_STEPS['flutter']]),
            'actions/artifacts/9': dict(id=9, name=sd.artifact_name(900, self.source, 1, 'tests-flutter'),
                                        digest='sha256:' + 'a' * 64, size_in_bytes=100, expired=False,
                                        workflow_run=dict(id=7, head_sha=self.source)),
        }
        for endpoint, update in changes.items():
            responses[endpoint] = dict(responses[endpoint], **update)
        return lambda endpoint: copy.deepcopy(responses[endpoint])

    def guard(self, manifest=None, get=None, head=None):
        return sd.reuse_guard('flutter', manifest or self.current, self.repo, get or self.api(), head or self.head)

    def test_identical_effective_tree_is_reused(self):
        value = self.guard()
        self.assertEqual(value['evidenceMode'], 'reused-identical-effective-tree')
        self.assertEqual(sorted(value['recipeReads']), ['.github/diagnostics/helper.py', '.github/diagnostics/other.py'])

    def test_refusals(self):
        steps_missing = [dict(name='Run source contracts and Flutter behavior', conclusion='success')]
        for get in (self.api(**{'actions/jobs/8': dict(conclusion='failure')}),
                    self.api(**{'actions/jobs/8': dict(name='native')}),
                    self.api(**{'actions/jobs/8': dict(steps=steps_missing)}),
                    self.api(**{'actions/artifacts/9': dict(expired=True)}),
                    self.api(**{'actions/artifacts/9': dict(digest='sha256:' + 'b' * 64)}),
                    self.api(**{'actions/runs/7/attempts/1': dict(path='.github/workflows/other.yml')})):
            with self.assertRaises(ValueError):
                self.guard(get=get)
        other = copy.deepcopy(self.current)
        other['product']['effectiveDigest'] = 'f' * 64
        with self.assertRaises(ValueError):
            self.guard(manifest=other)
        other = copy.deepcopy(self.current)
        other['tests']['flutter']['commands'] = self.commands[:1]
        with self.assertRaises(ValueError):
            self.guard(manifest=other)
        self.git.write('.github/diagnostics/other.py', 'VALUE = 2\n')
        changed = self.git.commit('a recipe module the group reads changed')
        with self.assertRaises(ValueError):
            self.guard(head=changed)

    def test_the_tested_source_must_be_an_ancestor(self):
        self.git.run('checkout', '-q', '--orphan', 'unrelated')
        self.git.write('build-utils/delivery/900.json', json.dumps(self.current))
        unrelated = self.git.commit('unrelated history')
        with self.assertRaises(ValueError):
            self.guard(head=unrelated)


class Republication(unittest.TestCase):
    def test_republished_bundle_is_accepted_only_for_the_original_bytes(self):
        with tempfile.TemporaryDirectory(prefix='standard-republish-') as directory:
            root = Path(directory)
            original = root / 'original-download.zip'
            with zipfile.ZipFile(original, 'w') as archive:
                archive.writestr('identity.json', '{}')
            origin = dict(workflow='.github/workflows/producer.yml', source='1' * 40, run=11, attempt=1, job=12,
                          artifact=13, name='Producer-archive', bytes=original.stat().st_size,
                          sha256=retained.sha_file(original))
            republisher = dict(build=900, source='2' * 40, run=21, attempt=1, workflow=sd.WORKFLOW, job='republish')
            record = retained.stage_republication('dolphin', origin, original, republisher, root)
            self.assertEqual(record['contentSHA256'], origin['sha256'])
            bundle = root / 'bundle.zip'
            folder = root / retained.REPUBLISH_ROOT / 'dolphin'

            def build(record_value=None, content=None):
                with zipfile.ZipFile(bundle, 'w') as archive:
                    archive.writestr('original.zip', content if content is not None else (folder / 'original.zip').read_bytes())
                    archive.writestr('republication.json', json.dumps(record_value or record))
                return dict(build=900, source='2' * 40, run=21, attempt=1, job=22, artifact=23, name='Republished',
                            bytes=bundle.stat().st_size, sha256=retained.sha_file(bundle))

            def api(republished, **changes):
                responses = {
                    'actions/runs/21': dict(id=21, head_sha='2' * 40, path=sd.WORKFLOW, head_branch='Claude', run_attempt=1),
                    'actions/jobs/22': dict(run_id=21, head_sha='2' * 40, run_attempt=1, name='republish',
                                            steps=[dict(name=retained.republish_step('dolphin'), conclusion='success')]),
                    'actions/artifacts/23': dict(id=23, name='Republished', size_in_bytes=republished['bytes'],
                                                 digest='sha256:' + republished['sha256'], expired=False,
                                                 workflow_run=dict(id=21, head_sha='2' * 40)),
                }
                for endpoint, update in changes.items():
                    responses[endpoint] = dict(responses[endpoint], **update)
                return lambda endpoint: copy.deepcopy(responses[endpoint])

            def download(artifact, path):
                shutil.copy2(bundle, path)

            target = root / 'restored/dolphin.zip'
            republished = build()
            value = retained.republished_archive('dolphin', origin, republished, target, api(republished), download)
            self.assertEqual(retained.sha_file(target), origin['sha256'])
            self.assertEqual(value['record']['original'], retained.original_binding(origin))
            cases = (
                (build(content=b'other bytes'), {}),
                (build(record_value=dict(record, original=dict(record['original'], run=99))), {}),
                (build(record_value=dict(record, republisher=dict(republisher, run=99))), {}),
            )
            for case, changes in cases:
                target.unlink(missing_ok=True)
                with self.assertRaises(ValueError):
                    retained.republished_archive('dolphin', origin, case, target, api(case, **changes), download)
            republished = build()
            with self.assertRaises(ValueError):
                retained.republished_archive('dolphin', origin, republished, target,
                                             api(republished, **{'actions/jobs/22': dict(steps=[])}), download)
            with self.assertRaises(ValueError):
                retained.republished_archive('dolphin', origin, republished, target,
                                             api(republished, **{'actions/jobs/22': dict(name='application')}), download)
            with self.assertRaises(ValueError):
                retained.stage_republication('dolphin', dict(origin, sha256='0' * 64), original, republisher, root)


class DownloadedDelivery(unittest.TestCase):
    """The offline verifier's transport, recipient and decryption checks on a synthetic delivery produced by
    the real build-utils/delivery_cipher.py and split_encrypted_delivery.py (throwaway key)."""

    def test_transport_recipient_and_decryption(self):
        sys.path.insert(0, str(ROOT / 'build-utils'))
        import verify_downloaded_delivery as verifier
        with tempfile.TemporaryDirectory(prefix='standard-download-') as directory:
            work = Path(directory)
            key, public, other = work / 'key.pem', work / 'public.pem', work / 'other.pem'
            for path in (key, other):
                subprocess.run(['openssl', 'genpkey', '-algorithm', 'RSA', '-pkeyopt', 'rsa_keygen_bits:2048',
                                '-out', str(path)], check=True, capture_output=True)
            subprocess.run(['openssl', 'pkey', '-in', str(key), '-pubout', '-out', str(public)], check=True,
                           capture_output=True)
            source, run, build = 'c' * 40, 55, 900
            delivery = work / 'delivery-artifact'
            delivery.mkdir()
            ipa_name = f'RewindBox-Build{build}-{source}-cold.ipa'
            (delivery / ipa_name).write_bytes(b'PK synthetic ipa')
            (delivery / 'SHA256SUMS').write_text(sha(b'PK synthetic ipa') + '  build/delivery-artifact/' + ipa_name + '\n')
            environment = dict(os.environ, DELIVERY_RECIPIENT=str(public), GITHUB_SHA=source, GITHUB_RUN_ID=str(run),
                               BUILD_NUMBER=str(build))
            subprocess.run([sys.executable, 'build-utils/delivery_cipher.py', 'artifact', str(delivery),
                            str(work / 'encrypted')], cwd=ROOT, env=environment, check=True, capture_output=True)
            subprocess.run([sys.executable, 'build-utils/split_encrypted_delivery.py', str(work / 'encrypted'),
                            str(work / 'parts')], cwd=ROOT, env=environment, check=True, capture_output=True)
            downloads = work / 'downloads'
            downloads.mkdir()
            name = sd.artifact_name(build, source, 1, 'cold')
            artifacts = {}
            for index in range(verifier.PARTS):
                archive = downloads / f'part{index:02d}.zip'
                with zipfile.ZipFile(archive, 'w') as output:
                    for member in sorted((work / 'parts' / f'part{index:02d}').iterdir()):
                        output.write(member, member.name)
                artifacts[f'{name}-part{index:02d}'] = dict(id=100 + index, size_in_bytes=archive.stat().st_size,
                                                            digest='sha256:' + sha(archive.read_bytes()))
            manifest, pieces, payload, envelope = verifier.transport(downloads, artifacts, name, source, run, build)
            self.assertEqual(len(pieces), verifier.PARTS)
            self.assertEqual(manifest['files']['artifact.tar.enc']['sha256'], sha(payload))
            verifier.recipient_matches(public, key)
            with self.assertRaises(SystemExit):
                verifier.recipient_matches(public, other)
            output = work / 'out'
            output.mkdir()
            folder, members, removed = verifier.decrypt(payload, envelope, key, output)
            self.assertEqual(members, sorted([ipa_name, 'SHA256SUMS']))
            self.assertTrue(removed)
            self.assertEqual((folder / ipa_name).read_bytes(), b'PK synthetic ipa')
            tampered = copy.deepcopy(artifacts)
            tampered[f'{name}-part02']['digest'] = 'sha256:' + '0' * 64
            with self.assertRaises(SystemExit):
                verifier.transport(downloads, tampered, name, source, run, build)
            with self.assertRaises(SystemExit):
                verifier.transport(downloads, artifacts, name, source, run + 1, build)


class TriggerCommit(unittest.TestCase):
    def test_subject_parsing(self):
        self.assertEqual(sd.subject_build('[ipa-delivery:611] build(delivery): request'), 611)
        with self.assertRaises(ValueError):
            sd.subject_build('build(delivery): request [ipa-delivery:611]')
        self.assertIsNone(sd.subject_build('docs: mention the tag in the body only'))
        with self.assertRaises(ValueError):
            sd.subject_build('[ipa-delivery:611] [ipa-delivery:612]')

    def test_expression_evaluator(self):
        status = dict(success=False, failure=False, cancelled=False, always=True)
        context = dict(github=dict(ref='refs/heads/Claude', event_name='push',
                                   event=dict(head_commit=dict(message='[ipa-delivery:611] x'))),
                       inputs={}, needs={'preflight': dict(result='skipped', outputs={})})
        cases = (("github.ref == 'refs/heads/Claude' && startsWith(github.event.head_commit.message, '[ipa-delivery:')", True),
                 ("startsWith(github.event.head_commit.message, '[x]')", False),
                 ("contains(github.event.head_commit.message, '[rewind610-delivery]')", False),
                 ("!(inputs.reuse_0279198 || (github.event_name == 'push' && contains(github.event.head_commit.message, '[x]')))", True),
                 ("always() && !cancelled() && needs.preflight.result == 'success'", False),
                 ("needs.preflight.outputs.build != ''", True))
        for expression, expected in cases:
            self.assertEqual(sd.truthy(sd.evaluate(expression, context, status)), expected, expression)
        with self.assertRaises(sd.Unevaluated):
            sd.evaluate("format('{0}', github.ref) == 'x'", context, status)

    def synthetic_root(self, other):
        directory = tempfile.TemporaryDirectory(prefix='standard-trigger-')
        root = Path(directory.name)
        (root / '.github/workflows').mkdir(parents=True)
        shutil.copy2(WORKFLOW, root / sd.WORKFLOW)
        (root / '.github/workflows/other.yml').write_text(other)
        return directory, root

    def test_trigger_paths_on_synthetic_workflows(self):
        quiet = ("'on':\n  push:\n    branches:\n    - Claude\njobs:\n  job:\n    if: ${{ contains(github.event.head_commit.message, '[other]') }}\n"
                 "    runs-on: ubuntu-latest\n    steps:\n    - run: 'true'\n")
        loud = ("'on':\n  push:\n    branches:\n    - Claude\n    paths:\n    - 'build-utils/delivery/**'\njobs:\n  job:\n"
                "    runs-on: ubuntu-latest\n    steps:\n    - run: 'true'\n")
        ignored = ("'on':\n  push:\n    paths-ignore:\n    - 'build-utils/**'\njobs:\n  job:\n    runs-on: ubuntu-latest\n"
                   "    steps:\n    - run: 'true'\n")
        for text, refused in ((quiet, False), (loud, True), (ignored, False)):
            directory, root = self.synthetic_root(text)
            with directory:
                if refused:
                    with self.assertRaises(ValueError):
                        sd.trigger_paths(611, ['build-utils/delivery/611.json'], root=root, loader=sd.load_yaml_subset)
                else:
                    report = sd.trigger_paths(611, ['build-utils/delivery/611.json'], root=root, loader=sd.load_yaml_subset)
                    self.assertEqual(report['otherWorkflowsStarted'], {})
                with self.assertRaises(ValueError):
                    sd.trigger_paths(611, ['lib/a.dart'], root=root, loader=sd.load_yaml_subset)
                with self.assertRaises(ValueError):
                    sd.trigger_paths(611, ['build-utils/delivery/611.json'], root=root, loader=sd.load_yaml_subset,
                                     message='[ipa-delivery:611] request [skip ci]')
                with self.assertRaises(ValueError):
                    sd.trigger_paths(611, ['build-utils/delivery/611.json'], root=root, loader=sd.load_yaml_subset,
                                     message='[ipa-delivery:612] request')

    def test_expected_trigger_commit_of_this_repository(self):
        if yaml is None:
            self.skipTest('trigger-paths is a local operation; it parses every workflow with PyYAML')
        build, _ = current_manifest()
        report = sd.trigger_paths(build, [sd.manifest_path(build)])
        self.assertEqual(report['otherWorkflowsStarted'], {})
        self.assertIn('preflight', report['standardDeliveryJobs'])
        with self.assertRaises(ValueError):
            sd.trigger_paths(build, ['test/rewind610_delivery_contract_test.py'])

    def test_globs(self):
        self.assertTrue(sd.filter_match(['build-utils/delivery/**'], 'build-utils/delivery/611.json'))
        self.assertFalse(sd.filter_match(['build-utils/*'], 'build-utils/delivery/611.json'))
        self.assertTrue(sd.filter_match(['test/rewind*test*'], 'test/rewind610_delivery_contract_test.py'))
        self.assertFalse(sd.filter_match(['test/rewind*test*'], 'test/standard_delivery_contract_test.py'))
        self.assertFalse(sd.filter_match(['docs/**', '!docs/keep.md'], 'docs/keep.md'))
        self.assertFalse(sd.push_triggers({'tags': ['v*']}, 'Claude', ['a']))
        self.assertTrue(sd.push_triggers({'branches-ignore': ['main']}, 'Claude', ['a']))


if __name__ == '__main__':
    unittest.main(verbosity=2)
