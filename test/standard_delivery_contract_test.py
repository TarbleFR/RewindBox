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
PIL_IMPORT = re.compile(r'^\s*(?:from PIL\b|import PIL\b)', re.M)


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
    return sd.manifest_effective_tree(REPO, manifest, head)


def product_reader():
    """Read a path as CI materializes it, and as the freeze reads it.

    Product paths come from the current manifest's effective tree, where source-only work is restored; recipe paths
    come from the checkout.
    """
    effective = sd.EffectiveReader(REPO, effective_of_head()['effective'])
    return lambda path: effective.read(path) if sd.is_product(path) else (
        (ROOT / path).read_bytes() if (ROOT / path).is_file() else None)


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
    # Build 0 has no standard manifest: the replay starts from the base source tree.
    return tree, dict(base=dict(build=0, source=base), product=dict(
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

    def test_standard_base_receipt_lists_its_other_jobs(self):
        """A standard-recipe base receipt also lists republish and the test jobs (skipped when reused)."""
        _, manifest = current_manifest()
        receipt_raw = (ROOT / manifest['base']['receipt']['path']).read_bytes()
        receipt = json.loads(receipt_raw)
        names = set(receipt['execution']['jobs'])
        self.assertTrue({'preflight', 'application'} <= names)
        failed = copy.deepcopy(receipt)
        extra = sorted(names - {'preflight', 'application'})
        if not extra:
            self.skipTest('the base receipt lists only its preflight and application jobs')
        failed['execution']['jobs'][extra[0]]['conclusion'] = 'failure'
        raw = json.dumps(failed).encode()
        broken = copy.deepcopy(manifest)
        broken['base']['receipt']['sha256'] = sha(raw)
        read = lambda path: raw if path == manifest['base']['receipt']['path'] else (ROOT / path).read_bytes()
        with self.assertRaises(ValueError):
            sd.verify_base(broken, read)

    def test_record_replays_the_latest_receipt_and_needs_its_signed_inventory(self):
        """718, 10 November 2026: a receipt written without signed-payload-identity.json cannot be the base of a later
        build. 719: a verification report already in the evidence folder stopped the record on a copy onto itself."""
        from unittest import mock
        builds = sorted((int(p.stem) for p in (ROOT / sd.MANIFESTS).glob('*.json') if p.stem.isdigit()), reverse=True)
        chosen = None
        for build in builds:
            folder = ROOT / f'docs/evidence/rewind{build}'
            if all((folder / name).is_file() for name in ('delivery.json', 'signed-payload-identity.json',
                                                           f'download{build}-verification.json', 'api/jobs.json')):
                report = json.loads((folder / f'download{build}-verification.json').read_bytes())
                jobs = json.loads((folder / 'api/jobs.json').read_bytes())
                jobs = jobs.get('jobs', []) if isinstance(jobs, dict) else jobs
                if set(job['name'] for job in jobs) == set(sd.JOB_NAMES) and \
                        report.get('result') == 'passed-offline-checks':
                    chosen = build
                    break
        if chosen is None:
            self.skipTest('no standard receipt with its signed image inventory in this tree')
        committed = json.loads((ROOT / f'docs/evidence/rewind{chosen}/delivery.json').read_bytes())
        run = committed['execution']['run']

        def replay(prepare=None, verification_outside=False):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                (root / sd.MANIFESTS).mkdir(parents=True)
                shutil.copy2(ROOT / sd.manifest_path(chosen), root / sd.manifest_path(chosen))
                folder = root / f'docs/evidence/rewind{chosen}'
                shutil.copytree(ROOT / f'docs/evidence/rewind{chosen}', folder)
                (folder / 'delivery.json').unlink()
                verification = folder / f'download{chosen}-verification.json'
                api = folder / 'api'
                if verification_outside:
                    outside = root / 'outside'
                    outside.mkdir()
                    shutil.move(str(verification), outside / 'report.json')
                    shutil.move(str(api), outside / 'api')
                    verification, api = outside / 'report.json', outside / 'api'
                if prepare:
                    prepare(folder)
                with mock.patch.object(sd, 'in_ci', lambda: False):
                    result = sd.record(chosen, run, verification, api, key_deleted=True, root=root)
                return result, json.loads((folder / 'delivery.json').read_bytes())

        for outside in (False, True):
            result, written = replay(verification_outside=outside)
            self.assertEqual(result['result'], 'written')
            for key in ('build', 'result', 'ipa', 'baseline', 'proofFiles'):
                self.assertEqual(written[key], committed[key], (key, outside))
            self.assertEqual(written['execution']['run'], run)
            self.assertIn('signed-payload-identity.json', written['proofFiles'])

        with self.assertRaisesRegex(ValueError, 'signed image inventory'):
            replay(lambda folder: (folder / 'signed-payload-identity.json').unlink())

        def another_ipa(folder):
            path = folder / 'signed-payload-identity.json'
            identity = json.loads(path.read_bytes())
            identity['ipaSha256'] = '0' * 64
            path.write_text(json.dumps(identity))
        with self.assertRaisesRegex(ValueError, 'not the one of the verified IPA'):
            replay(another_ipa)

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
        build, manifest = current_manifest()
        base = sd.verify_base(manifest)
        images = manifest['images']
        expected = {
            611: ('Frameworks/libRPCS3Core.dylib', 'Frameworks/MeloNXCore.framework/MeloNXCore',
                  'Frameworks/rpcs3_internal_bridge.framework/rpcs3_internal_bridge',
                  'Frameworks/retro_achievements_session.framework/retro_achievements_session',
                  'Frameworks/App.framework/App', 'Runner'),
            # 612 changes the RPCS3 Core and its bridge only; the MeloNX Core of 611 is kept.
            612: ('Frameworks/libRPCS3Core.dylib', 'Frameworks/rpcs3_internal_bridge.framework/rpcs3_internal_bridge',
                  'Runner'),
        }
        for name in expected.get(build, ('Runner',)):
            self.assertIn(name, images['mustChange'])
        retained_names = []
        for patterns in images['retained'].values():
            retained_names += sd.expand_image_patterns(patterns, sorted(base))
        for key, spec in manifest['components'].items():
            if spec.get('unchangedFromBase') is True:
                self.assertNotIn(spec['image'], images['mustChange'], key)
                self.assertNotIn(key, images['replaced'], key)
                self.assertIn(spec['image'], sd.expand_image_patterns(images['retained'][key], sorted(base)), key)
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
    def test_melonx_verifier_comes_from_the_manifest(self):
        _, manifest = current_manifest()
        spec = manifest['components']['melonx']
        self.assertEqual(sd.melonx_component(manifest).__name__, sd.MELONX_VERIFIERS[spec['verifier']])
        for verifier, pin in ((spec['verifier'], 'build-utils/melonx/other-pin.json'),
                              ('.github/diagnostics/unknown_component.py', spec['pin'])):
            with self.assertRaises(ValueError):
                sd.melonx_component(dict(manifest, components=dict(manifest['components'],
                                                                     melonx=dict(spec, verifier=verifier, pin=pin))))

    def test_melonx_pin_is_verified_and_bound_to_its_contract(self):
        _, manifest = current_manifest()
        melonx = sd.melonx_component(manifest)
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
        # Checked against the product tree CI materializes, as the freeze checks it: source-only work that touches the
        # pin's inputs (another session's next RPCS3 Core) is restored there.
        read = product_reader()
        report = rpcs3.pin_errors(pin, read)
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
            rpcs3.pinned(pin, read)
        if manifest['status'] == 'frozen':
            self.assertEqual(manifest['components']['rpcs3']['pinSha256'],
                             sha((ROOT / manifest['components']['rpcs3']['pin']).read_bytes()))

    def synthetic_pin(self):
        pin = rpcs3.load_pin()
        canonical = json.loads(product_reader()(rpcs3.CANONICAL))
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
        pin, read = self.synthetic_pin(), product_reader()
        self.assertEqual(rpcs3.pin_errors(pin, read), dict(status='verified', missing=[], errors=[]))
        rpcs3.pinned(pin, read)
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
                rpcs3.pinned(broken, read)

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
        # Number literals, not substrings: a build number can occur inside a hash (624 in the MeloNX
        # upstream tree 82a29e6f593f6244869481e9...).
        for build, manifest in manifests().items():
            self.assertNotIn(int(build), numbers)
            self.assertNotIn(int(manifest['base']['build']), numbers)

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

    def test_the_flutter_job_provides_the_pillow_its_python_tests_import(self):
        """650 run 41861290919: test/pocket_skin_input_chain_test.py failed on "No module named 'PIL'" (the
        ubuntu runner's python3 has no Pillow). A frozen flutter command whose Python source imports PIL runs
        with the pinned Pillow of the skin checks, from a venv put first on PATH before the group step."""
        importing = sorted({argument for manifest in manifests().values()
                            if manifest['tests'].get('flutter', {}).get('mode') == 'fresh'
                            for _, arguments in manifest['tests']['flutter'].get('commands', [])
                            for argument in arguments
                            if argument.endswith('.py') and (ROOT / argument).is_file() and
                            PIL_IMPORT.search((ROOT / argument).read_text(encoding='utf-8'))})
        self.assertIn('test/pocket_skin_input_chain_test.py', importing)
        pins = set(re.findall(r'pillow==([0-9.]+)', (ROOT / '.github/workflows/skin-orientation-checks.yml').read_text()))
        self.assertEqual(len(pins), 1, pins)
        name = 'Provide the pinned Pillow of the skin verifiers'
        names = [s['name'] for s in steps('flutter')]
        self.assertIn(name, names, 'flutter commands import PIL: ' + repr(importing))
        self.assertLess(names.index('Resolve exact workspace lock'), names.index(name))
        self.assertLess(names.index(name), names.index(RUN_STEPS['flutter']))
        provide = step('flutter', name)['run']
        self.assertIn('python3 -m venv --system-site-packages "$RUNNER_TEMP/delivery-python"', provide)
        self.assertIn('pip install --quiet --disable-pip-version-check pillow==' + next(iter(pins)), provide)
        self.assertTrue(provide.rstrip().endswith('echo "$RUNNER_TEMP/delivery-python/bin" >> "$GITHUB_PATH"'))

    def test_no_fresh_native_command_imports_pil_without_its_pillow(self):
        """718 run 42741950414 attempt 1: the native job failed only on test/pocket_skin_input_chain_test.py,
        "No module named 'PIL'". The recipe had added to the native group the command its flutter group
        already ran, with the pinned Pillow, on the same tree. The native job provides no Pillow, so no fresh
        native command may import PIL (negative control: the 718 recipe of that run)."""
        def importers(manifest):
            return sorted({argument for _, arguments in manifest['tests'].get('native', {}).get('commands', [])
                           for argument in arguments
                           if argument.endswith('.py') and (ROOT / argument).is_file() and
                           PIL_IMPORT.search((ROOT / argument).read_text(encoding='utf-8'))})
        failed = json.loads(REPO.show('b9a451fbf93ab0d4d4848770456e9aaebe8ce859', sd.manifest_path(718)))
        self.assertEqual(importers(failed), ['test/pocket_skin_input_chain_test.py'])
        self.assertNotIn('Provide the pinned Pillow of the skin verifiers', [s['name'] for s in steps('native')])
        for build, manifest in manifests().items():
            if manifest['tests'].get('native', {}).get('mode') == 'fresh':
                self.assertEqual(importers(manifest), [], build)

    def test_the_native_job_boots_its_simulator_once_before_the_group(self):
        """694 run 42506743712 and 718 run 42741950414: the translation XCTest let xcodebuild boot the
        simulator and shut it down afterwards (the central session receipt records it Shutdown), so the
        central session XCTest booted it again and waited 278 s and 400 s in its test phase for 4-5 s of tests;
        the Dolphin and ARMSX2 XCTests that followed on the booted device waited 7-15 s. The native job boots
        the device every XCTest selects once, before Flutter is set up, and waits for it right before the
        group; no test command or device check changes."""
        names = [s['name'] for s in steps('native')]
        boot = 'Boot the targeted iOS simulator once for every XCTest'
        wait = 'Wait for the targeted iOS simulator to finish booting'
        self.assertLess(names.index('Select targeted Xcode16.4 and Swift6'), names.index(boot))
        self.assertLess(names.index(boot), names.index('Set up Flutter3.47.2'))
        self.assertEqual(names.index(wait) + 1, names.index(RUN_STEPS['native']))
        self.assertLess(names.index('Prepare real Flutter iOS headers and simulator project tool'), names.index(wait))
        text, waiting = step('native', boot)['run'], step('native', wait)['run']
        runtime = "'com.apple.CoreSimulator.SimRuntime.iOS-' + sdk.replace('.', '-')"
        for source in ('test/retro_achievements_session_native_test.py', '.github/diagnostics/rewind608_checks.py',
                       'test/dolphin_account_267_test.py', 'test/armsx2_graphics_ui_test.py'):
            body = (ROOT / source).read_text(encoding='utf-8')
            self.assertIn(runtime, body, source)
            self.assertIn("['name'].startswith('iPhone')", body, source)
            self.assertIn("'simctl', 'list', 'devices', 'available', '-j'", body, source)
        self.assertIn(runtime, text)
        self.assertIn("'simctl', 'list', 'devices', 'available', '-j'", text)
        self.assertIn("d['name'].startswith('iPhone') and d.get('isAvailable')", text)
        self.assertIn("matches[0]['udid']", text)
        self.assertIn('nohup xcrun simctl bootstatus "$UDID" -b', text)
        self.assertIn('xcrun simctl bootstatus "$TARGET_SIMULATOR" -b', waiting)
        for value in (text, waiting):
            self.assertNotIn('shutdown', value.lower())
            self.assertNotIn('erase', value.lower())

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

    def test_promoted_deferred_work_before_the_base(self):
        g = self.git
        start = self.base()
        g.write('lib/a.dart', 'a-deferred')
        g.write('lib/l10n.dart', 'strings')
        feature = g.commit('deferred feature with its strings')
        g.write('lib/l10n.dart', 'strings + fix')
        g.write('lib/fix.dart', 'f')
        fix = g.commit('fix written on the deferred strings')
        g.write('lib/b.dart', 'b-delivered')
        delivered = g.commit('delivered base')
        g.write('docs/n.md', 'n')
        head = g.commit('recipe-only')
        # The base delivery deferred both commits: its effective tree restored their paths.
        restored = ['lib/a.dart', 'lib/fix.dart', 'lib/l10n.dart']
        initial = self.repo.entries(start)
        base_entries = {p: e for p, e in self.repo.entries(delivered).items() if sd.is_product(p)}
        for path in restored:
            if path in initial:
                base_entries[path] = initial[path]
            else:
                base_entries.pop(path)
        tree = sd.replay(self.repo, delivered, head, [], [], base_entries, [dict(commit=fix)], restored)
        self.assertEqual([c['path'] for c in tree['conflicts']], ['lib/l10n.dart'],
                         'A promoted change must start from the effective bytes')
        promoted = [dict(commit=feature, paths=['lib/l10n.dart']), dict(commit=fix)]
        tree = sd.effective_tree(self.repo, delivered, head, [], [], base_entries, promoted, restored)
        heads = self.repo.entries(head)
        self.assertEqual(tree['conflicts'] + tree['unclassified'], [])
        self.assertEqual([c['role'] for c in tree['commits']], ['promoted', 'promoted', 'recipe'])
        self.assertEqual([c['partial'] for c in tree['commits'][:2]], [True, False])
        self.assertEqual(tree['effective']['lib/l10n.dart'], heads['lib/l10n.dart'])
        self.assertEqual(tree['effective']['lib/fix.dart'], heads['lib/fix.dart'])
        self.assertEqual(tree['effective']['lib/a.dart'], initial['lib/a.dart'], 'Paths left out stay deferred')
        self.assertEqual(sorted(tree['restoreRecords']), ['lib/a.dart'])
        for bad, deferred_paths in (([dict(commit=fix), dict(commit=feature, paths=['lib/l10n.dart'])], restored),
                                    ([dict(commit=feature, paths=['lib/keep.dart'])], restored),
                                    ([dict(commit=feature)], ['lib/fix.dart', 'lib/l10n.dart']),
                                    ([dict(commit=head)], restored),
                                    ([dict(commit=delivered)], restored)):
            with self.assertRaises(ValueError):
                sd.replay(self.repo, delivered, head, [], [], base_entries, bad, deferred_paths)
        manifest = dict(status='draft', product=dict(reviewedCommits=[], sourceOnly=[], promotedCommits=[dict(commit='x')]))
        self.assertTrue([e for e in sd.manifest_errors(dict(self.valid_manifest(), product=manifest['product']))
                         if 'promotedCommits' in e])

    def valid_manifest(self):
        _, manifest = current_manifest()
        return json.loads(json.dumps(manifest))

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
        side = self.git.commit('side')
        self.git.run('checkout', '-q', 'Claude')
        self.git.run('merge', '-q', '--no-edit', '--no-ff', 'side')
        merge = self.git.run('rev-parse', 'HEAD')
        # Maintainer decision, 4 November 2026: a merge on the first-parent line is one change to classify.
        tree = sd.replay(self.repo, base, merge, [unclassified, late], [])
        self.assertEqual([c['commit'] for c in tree['unclassified']], [merge], 'an unreviewed merge stays unclassified')
        self.assertTrue([c for c in tree['commits'] if c['commit'] == merge][0].get('merge'))
        self.assertNotIn(side, [c['commit'] for c in tree['commits']], 'side-branch commits are not replayed one by one')
        tree = sd.replay(self.repo, base, merge, [unclassified, late, merge], [])
        self.assertFalse(tree['unclassified'] or tree['conflicts'] or tree['missing'])
        self.assertIn('lib/side.dart', tree['effective'], 'a reviewed merge brings its side branch')
        tree = sd.replay(self.repo, base, merge, [unclassified, late, side], [])
        self.assertEqual(tree['missing'], [side], 'a side-branch commit cannot be classified separately')
        # Still refused: merges after the freeze, and a base off the first-parent line.
        tree, manifest = frozen_product(self.repo, base, late, [unclassified, late], [])
        with self.assertRaises(ValueError):
            sd.materialize_tree(self.repo, manifest, merge)
        with self.assertRaises(ValueError):
            sd.replay(self.repo, side, merge, [], [])

    def test_recipe_patterns(self):
        for path in ('.github/workflows/x.yml', 'docs/a/b.md', 'AGENTS.md', '.claude/settings.json',
                     'build-utils/delivery/611.json', 'build-utils/delivery-611-recipient.pem',
                     'build-utils/rpcs3/core-pin.json', 'build-utils/melonx/reads-core-pin.json',
                     'build-utils/melonx/arrays-core-pin.json', 'build-utils/melonx/dma-core-pin.json',
                     'test/standard_delivery_contract_test.py', 'build-utils/verify_downloaded_delivery.py'):
            self.assertTrue(sd.is_recipe(path), path)
        for path in ('lib/a.dart', 'test/x_test.py', 'build-utils/rpcs3/canonical-source.json', 'packages/a/README.md',
                     'build-utils/x/delivery-1-recipient.pem', 'build-utils/melonx/reads-core-contract.json', 'pubspec.yaml'):
            self.assertFalse(sd.is_recipe(path), path)
        self.assertEqual(sd.recipe_definition_sha(), sd.sha(sd.canonical(sd.RECIPE_DEFINITION)))


class BaseEffectiveTree(unittest.TestCase):
    """A build replays from the tree its base delivery compiled, not from the raw base source tree."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='standard-base-')
        self.git = Git(self.directory.name)
        self.repo = sd.Repo(self.directory.name)

    def tearDown(self):
        self.directory.cleanup()

    def delivered_base(self):
        """Build 900 freezes over a deferred commit; its source then carries the frozen manifest."""
        g = self.git
        g.write('lib/a.dart', 'a0')
        g.write('lib/b.dart', 'b0')
        first = g.commit('build 899 delivered')
        g.write('lib/a.dart', 'a-deferred')
        g.write('lib/new_deferred.dart', 'n')
        deferred = g.commit('deferred work for a later build')
        g.write('lib/b.dart', 'b1')
        reviewed = g.commit('reviewed for 900')
        tree, frozen = frozen_product(self.repo, first, reviewed, [reviewed], [deferred])
        manifest = dict(build=900, status='frozen', base=dict(build=899, source=first),
                        product=dict(frozen['product'], reviewedCommits=[dict(commit=reviewed)],
                                     sourceOnly=[dict(commit=deferred, targetBuild=901, note='later')]))
        g.write(sd.manifest_path(900), json.dumps(manifest))
        source = g.commit('[ipa-delivery:900] trigger')
        return dict(first=first, deferred=deferred, reviewed=reviewed, source=source, manifest=manifest, tree=tree)

    def next_manifest(self, delivered, reviewed=(), source_only=()):
        return dict(build=901, base=dict(build=900, source=delivered['source']),
                    product=dict(reviewedCommits=[dict(commit=c) for c in reviewed],
                                 sourceOnly=[dict(commit=c, targetBuild=902, note='x') for c in source_only]))

    def test_deferred_work_of_the_base_stays_out(self):
        delivered = self.delivered_base()
        self.git.write('lib/c.dart', 'c1')
        head = self.git.commit('reviewed for 901')
        manifest = self.next_manifest(delivered, [head])
        tree = sd.manifest_effective_tree(self.repo, manifest, head)
        self.assertEqual(tree['conflicts'] + tree['unclassified'], [])
        self.assertEqual(tree['baseEffectiveDigest'], delivered['manifest']['product']['effectiveDigest'])
        entries = self.repo.entries(delivered['first'])
        self.assertEqual(tree['effective']['lib/a.dart'], entries['lib/a.dart'], 'The base deferral is inherited')
        self.assertNotIn('lib/new_deferred.dart', tree['effective'])
        self.assertEqual(tree['effective']['lib/b.dart'], self.repo.entries(delivered['reviewed'])['lib/b.dart'])
        self.assertEqual(sorted(tree['restoreRecords']), ['lib/a.dart', 'lib/new_deferred.dart'])
        self.assertEqual(sorted(tree['effectiveRecords']), ['lib/c.dart'])
        # The raw source tree would have absorbed the deferred work without review.
        raw = sd.effective_tree(self.repo, delivered['source'], head, [head], [])
        self.assertEqual(raw['effective']['lib/a.dart'], self.repo.entries(delivered['deferred'])['lib/a.dart'])
        frozen = dict(manifest, product=dict(manifest['product'], freezeCommit=head, effective=tree['effectiveRecords'],
                                             restore=tree['restoreRecords'], effectiveDigest=tree['effectiveDigest'],
                                             baseEffectiveDigest=tree['baseEffectiveDigest']))
        result = sd.materialize_tree(self.repo, frozen, head)
        self.assertEqual(result['effectiveDigest'], tree['effectiveDigest'])
        self.assertEqual((self.git.root / 'lib/a.dart').read_text(), 'a0')
        self.assertFalse(os.path.lexists(self.git.root / 'lib/new_deferred.dart'))
        with self.assertRaises(ValueError):
            sd.expected_product_paths(self.repo, dict(frozen, product=dict(frozen['product'], baseEffectiveDigest=None)), head)

    def test_a_tampered_base_manifest_is_refused(self):
        delivered = self.delivered_base()
        manifest = dict(delivered['manifest'])
        manifest['product'] = dict(manifest['product'], effectiveDigest='0' * 64)
        self.git.write(sd.manifest_path(900), json.dumps(manifest))
        head = self.git.commit('rewrite the base manifest after its delivery')
        with self.assertRaises(ValueError):
            sd.manifest_effective_tree(self.repo, self.next_manifest(dict(delivered, source=head)), head)

    def test_a_base_without_a_standard_manifest_compiled_its_source_tree(self):
        g = self.git
        g.write('lib/a.dart', 'a0')
        source = g.commit('delivered by an earlier recipe')
        g.write('lib/a.dart', 'a1')
        head = g.commit('reviewed')
        manifest = dict(build=611, base=dict(build=610, source=source),
                        product=dict(reviewedCommits=[dict(commit=head)], sourceOnly=[]))
        tree = sd.manifest_effective_tree(self.repo, manifest, head)
        self.assertIsNone(tree['baseEffectiveDigest'])
        self.assertEqual(tree['baseEntries'], {p: e for p, e in self.repo.entries(source).items() if sd.is_product(p)})


class UnchangedPinnedComponent(unittest.TestCase):
    """A build that keeps the base's pinned Core installs it again and keeps its base image."""

    def manifest(self, replaced=None, retained=None, unchanged=True):
        _, current = current_manifest()
        value = json.loads(json.dumps(current))
        # The MeloNX rules alone: RPCS3 is a replaced Core here, whatever the current build does with it.
        value['components']['rpcs3'].pop('unchangedFromBase', None)
        value['components']['melonx']['unchangedFromBase'] = unchanged
        value['images']['replaced'] = replaced if replaced is not None else {'rpcs3': 'Frameworks/libRPCS3Core.dylib'}
        value['images']['retained'] = dict({k: v for k, v in value['images']['retained'].items() if k not in ('rpcs3', 'melonx')},
                                           **({'melonx': retained} if retained is not None else {}))
        return value

    def test_schema(self):
        image = 'Frameworks/MeloNXCore.framework/MeloNXCore'
        errors = sd.manifest_errors(self.manifest(retained=[image]))
        self.assertFalse([e for e in errors if 'unchangedFromBase' in e], errors)
        both = self.manifest(replaced={'rpcs3': 'Frameworks/libRPCS3Core.dylib', 'melonx': image}, retained=[image])
        self.assertTrue([e for e in sd.manifest_errors(both) if 'unchangedFromBase' in e])
        self.assertTrue([e for e in sd.manifest_errors(self.manifest(retained=[])) if 'unchangedFromBase' in e])
        self.assertTrue([e for e in sd.manifest_errors(self.manifest(retained=[image], unchanged='yes'))
                         if 'unchangedFromBase' in e])

    def test_payload_rule(self):
        replaced, unchanged = self.manifest(unchanged=False), self.manifest(retained=[])
        self.assertTrue(sd.pinned_payload_rule(replaced, 'melonx', 'a', 'b'))
        self.assertFalse(sd.pinned_payload_rule(replaced, 'melonx', 'a', 'a'))
        self.assertTrue(sd.pinned_payload_rule(unchanged, 'melonx', 'a', 'a'))
        self.assertFalse(sd.pinned_payload_rule(unchanged, 'melonx', 'a', 'b'))


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

    def test_inherited_deferral_for_612(self):
        build, manifest = current_manifest()
        if build != 612:
            self.skipTest('612-specific expectations')
        tree = effective_of_head()
        base = json.loads(REPO.show(manifest['base']['source'], sd.manifest_path(611)))
        self.assertEqual(tree['baseEffectiveDigest'], base['product']['effectiveDigest'])
        deferred = set(base['product']['deferred'][B06888A9])
        restore = tree['restoreRecords']
        pending = {path for item in tree['unclassified'] for path in item['paths']}
        self.assertEqual(set(restore) - pending, deferred, '612 restores exactly the deferral inherited from 611')
        self.assertEqual({p: restore[p] for p in deferred}, {p: base['product']['restore'][p] for p in deferred})
        self.assertFalse(set(tree['effectiveRecords']) & deferred)
        self.assertEqual([c['commit'] for c in tree['commits'] if c['commit'] == B06888A9], [])

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


class PocketSkinRevisionReview(unittest.TestCase):
    """720, 10 November 2026: PR 166 and PR 167 rebuilt six Pocket packs in place and the declaration chain of the
    application refused the effective tree ("Pocket board Originals added packs differ from the review"). The revision
    review binds every rebuilt pack to the identity an earlier review gave it. 722: PR 169 rebuilt the same six packs
    again; a second revision review binds each to the identity of the first, and only the last revision is checked
    against the catalog."""

    REVIEWS = ('docs/evidence/pocket-skins-framing-press-declarations-2026-11-10.json',
               'docs/evidence/pocket-skins-native-ratio-declarations-2026-11-10.json')
    CATALOG = 'assets/skins/pocket/catalog.json'

    def setUp(self):
        self.present = [name for name in self.REVIEWS if (ROOT / name).is_file()]
        if not self.present:
            self.skipTest('no Pocket skin revision review in this tree')
        # The last revision is the one the catalog must match.
        self.REVIEW = self.present[-1]
        import importlib.util
        spec = importlib.util.spec_from_file_location('source_evidence_revision',
                                                      ROOT / 'build-utils/collect_build_source_evidence.py')
        self.evidence = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.evidence)
        tree = effective_of_head()
        self.reader = sd.EffectiveReader(REPO, tree['effective'])
        _, manifest = current_manifest()
        head = manifest['product'].get('freezeCommit') or REPO.commit('HEAD')
        self.paths = set(tree['effective']) | {path for path in REPO.entries(head) if sd.is_recipe(path)}
        self.paths |= set(self.present)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        for path in self.paths:
            (self.root / path).parent.mkdir(parents=True, exist_ok=True)
            (self.root / path).touch()
        self.cache, self.overrides = {}, {}

    def read(self, root, path):
        """The collector's read_input on the effective tree: product paths as the freeze restores them, recipe paths
        from the checkout; an override stands for a changed file."""
        relative = Path(path).resolve().relative_to(Path(root).resolve()).as_posix()
        if not Path(path).is_file():
            raise SystemExit('Source evidence is not a repository file: ' + relative)
        if relative in self.overrides:
            return self.overrides[relative]
        if relative not in self.cache:
            data = self.reader.read(relative) if sd.is_product(relative) else None
            self.cache[relative] = data if data is not None else (ROOT / relative).read_bytes()
        return self.cache[relative]

    def collect(self, overrides=None, absent=()):
        from unittest import mock
        self.overrides = dict(overrides or {})
        for path in absent:
            (self.root / path).unlink()
        try:
            with mock.patch.object(self.evidence, 'read_input', self.read):
                return self.evidence.repository_inputs(self.root)
        finally:
            for path in absent:
                (self.root / path).touch()

    def test_the_rebuilt_packs_pass_only_through_their_revision_review(self):
        review = json.loads(self.read(self.root, self.root / self.REVIEW))
        bundle = review['bundled_assets']
        catalog_raw = self.read(self.root, self.root / self.CATALOG)
        self.assertEqual(bundle['catalog_sha256'], sha(catalog_raw))
        self.assertEqual(len(bundle['revised_skins']) + len(bundle['unchanged_skins']), bundle['catalog_skins'])
        self.assertTrue('pubspec.lock' in self.collect(), 'the effective tree does not pass its declaration chain')

        # Before the revision review existed: the same tree is refused by the first earlier review of a rebuilt pack.
        with self.assertRaisesRegex(SystemExit, 'differ from the review|catalog changed since review'):
            self.collect(absent=[self.REVIEW])

        def changed_review(edit):
            value = json.loads(json.dumps(review))
            edit(value['bundled_assets'])
            return {self.REVIEW: json.dumps(value).encode()}

        # A revision that does not name the identity the earlier review gave the pack binds nothing.
        bound = sorted(set(bundle['revised_skins']) & {'switch-pocket', 'ps2-pocket-original', 'wii-pocket-original',
                                                       'gamecube-pocket-original'})
        self.assertTrue(bound, 'no rebuilt pack carries an earlier identity review')
        with self.assertRaisesRegex(SystemExit, 'does not bind the reviewed pack: ' + bound[0]):
            self.collect(changed_review(lambda b: b['revised_skins'][bound[0]]['previous'].update(sha256='0' * 64)))
        # A pack the catalog holds at another identity than the revision reviewed.
        with self.assertRaisesRegex(SystemExit, 'differ'):
            self.collect(changed_review(lambda b: b['revised_skins'][bound[0]].update(size=1)))
        # A revision that leaves a pack of the catalog out.
        with self.assertRaisesRegex(SystemExit, 'differ'):
            self.collect(changed_review(lambda b: b['unchanged_skins'].clear() if b['unchanged_skins']
                                        else b['revised_skins'].pop(bound[0])))
        # The catalog moved after the review.
        with self.assertRaisesRegex(SystemExit, 'catalog changed since review'):
            self.collect({self.CATALOG: catalog_raw + b'\n'})
        # An archive that is not the one the catalog and the review name.
        archive = bundle['revised_skins'][bound[0]]['archiveAsset']
        with self.assertRaisesRegex(SystemExit, 'archive differs from the catalog'):
            self.collect({archive: self.read(self.root, self.root / archive) + b'x'})
        # And the unchanged tree still passes after the controls.
        self.assertTrue('pubspec.lock' in self.collect())

    def test_a_later_revision_is_bound_to_the_one_before(self):
        if len(self.present) < 2:
            self.skipTest('a single Pocket skin revision review in this tree')
        first, last = self.present[-2], self.present[-1]
        later = json.loads(self.read(self.root, self.root / last))
        self.assertEqual(later['baseline_inventory'], first)
        self.assertTrue('pubspec.lock' in self.collect())
        # A later revision without the one before it binds nothing.
        with self.assertRaisesRegex(SystemExit, 'lacks the revision before it'):
            self.collect(absent=[first])
        # The earlier revision edited after the later one bound it (its digest is the later one's baseline).
        earlier = json.loads(self.read(self.root, self.root / first))
        earlier['scope'] += ' '
        with self.assertRaisesRegex(SystemExit, 'different baseline or dependency scope'):
            self.collect({first: json.dumps(earlier).encode()})

        def changed_later(edit):
            value = json.loads(json.dumps(later))
            edit(value['bundled_assets'])
            return {last: json.dumps(value).encode()}

        # A pack the later revision rebuilds from an identity the earlier revision did not give it.
        rebuilt = sorted(later['bundled_assets']['revised_skins'])[0]
        with self.assertRaisesRegex(SystemExit, 'differ from the review|does not bind the reviewed pack'):
            self.collect(changed_later(lambda b: b['revised_skins'][rebuilt]['previous'].update(sha256='0' * 64)))
        # A later revision that does not start from the earlier revision's catalog.
        with self.assertRaisesRegex(SystemExit, 'catalog changed since review'):
            self.collect(changed_later(lambda b: b.update(previous_catalog_sha256='0' * 64)))
        self.assertTrue('pubspec.lock' in self.collect())


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

    def test_612_additions(self):
        build, manifest = current_manifest()
        if build != 612:
            self.skipTest('612-specific expectations')
        tree = effective_of_head()
        reader = sd.EffectiveReader(REPO, tree['effective'])
        for group, name in (('flutter', 'rpcs3-graphics-tests-612'), ('native', 'rpcs3-graphics-tests-612-apple')):
            commands = dict(sd.expand_commands(group, manifest['tests'][group], reader.listing))
            self.assertEqual(commands[name], ['python3', '-B', 'test/rpcs3_graphics_tests612_test.py'])
            self.assertEqual(manifest['tests'][group]['mode'], 'fresh', '612 changes product inputs of both groups')

    def test_a_group_runs_an_identical_command_once(self):
        """616..718: test/rpcs3_diagnostics546_native_test.py ran twice in the native job, as
        rpcs3-timeline-613-foundation and rpcs3-timeline-616-foundation, with the same log bytes in 694 and
        718 (cbed30fc...). An addition repeating an argv of its own group (base or added) is refused; the
        same script in the other group stays allowed (another runner and toolchain)."""
        listing = lambda prefix: []
        for frozen in (sd.manifest_path(694), sd.manifest_path(718)):
            old = json.loads(REPO.show('b9a451fbf93ab0d4d4848770456e9aaebe8ce859', frozen))
            with self.assertRaisesRegex(ValueError, 'rpcs3-timeline-616-foundation repeats the identical command '
                                                    'rpcs3-timeline-613-foundation'):
                sd.expand_commands('native', old['tests']['native'], listing)
        base = sd.base_groups()['native'][0]
        with self.assertRaisesRegex(ValueError, 'repeats the identical command ' + base[0]):
            sd.expand_commands('native', {'additions': {'commands': [['again', list(base[1])]]}}, listing)
        spec = {'additions': {'commands': [['one', ['python3', '-B', 'test/x_test.py']],
                                           ['two', ['python3', '-B', 'test/x_test.py', '--other']]]}}
        self.assertEqual([n for n, _ in sd.expand_commands('native', spec, listing)][-2:], ['one', 'two'])
        flutter = sd.base_groups()['flutter']
        script = next(argv for _, argv in flutter if argv[:2] == ['python3', '-B'])
        sd.expand_commands('native', {'additions': {'commands': [['cross', list(script)]]}}, listing)

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

    def test_purged_original_archive_needs_its_republication(self):
        """GitHub purges an expired artifact (Not Found); a pinned republication then stands for it."""
        origin = dict(workflow='.github/workflows/producer.yml', branch='Claude', source='1' * 40, run=11, attempt=1,
                      runConclusion='success', artifact=13, name='LibretroCores-' + '1' * 40, bytes=10, sha256='a' * 64,
                      expiresAt='2026-11-03T16:19:42Z')

        def api(endpoint):
            if endpoint == 'actions/runs/11':
                return dict(id=11, head_sha='1' * 40, path=origin['workflow'], head_branch='Claude', status='completed',
                            conclusion='success')
            raise subprocess.CalledProcessError(1, ['gh', 'api', endpoint])

        spec = dict(mode='retain-archive', destination='build/libretro', inputs=[], origin=origin)
        with self.assertRaises(ValueError):
            retained.archive_origin('libretro', spec, api)
        value = retained.archive_origin('libretro', dict(spec, republished=dict(run=21)), api)
        self.assertTrue(value['originPurged'])
        self.assertEqual((value['sha256'], value['bytes']), (origin['sha256'], origin['bytes']))


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

    def test_pieces_hold_a_payload_over_the_former_256_mib(self):
        """722, 10 November 2026: the encrypted IPA passed 4 x 64 MiB (run 42848698413, split_encrypted_delivery.py
        refused it after the application was built and sealed). Four pieces of at most 96 MiB carry it."""
        with tempfile.TemporaryDirectory(prefix='standard-split-') as directory:
            work = Path(directory)
            encrypted = work / 'encrypted'
            encrypted.mkdir()
            payload_bytes = 4 * 64 * 1024 * 1024 + 4096
            with (encrypted / 'artifact.tar.enc').open('wb') as output:
                output.truncate(payload_bytes)
            (encrypted / 'format.json').write_text(json.dumps({'cipher': 'AES-256-CBC PBKDF2 200000', 'keyEnvelope': 'RSA OAEP SHA256',
                                                               'content': 'tar', 'publication': 'encrypted delivery only'}))
            (encrypted / 'password.rsa').write_bytes(b'envelope')
            environment = dict(os.environ, GITHUB_SHA='d' * 40, GITHUB_RUN_ID='77', BUILD_NUMBER='901')
            result = subprocess.run([sys.executable, 'build-utils/split_encrypted_delivery.py', str(encrypted), str(work / 'parts')],
                                    cwd=ROOT, env=environment, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr[-2000:])
            manifest = json.loads(result.stdout)
            self.assertEqual([part['index'] for part in manifest['parts']], [0, 1, 2, 3])
            self.assertEqual(sum(part['bytes'] for part in manifest['parts']), payload_bytes)
            self.assertTrue(all(64 * 1024 * 1024 < part['bytes'] <= 96 * 1024 * 1024 for part in manifest['parts']))


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
