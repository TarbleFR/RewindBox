"""Fail-closed Build442 reuse for a cover-only IPA; no native tests are repeated."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('cover_reuse', ROOT / 'build-utils/verify_delivery_reuse.py')
reuse = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reuse)
WORKFLOW = '.github/workflows/retroarch-delivery.yml'


class LibraryCoverDelivery(unittest.TestCase):
    def fixture(self, folder):
        files = {
            'lib/widgets/library_book_cover.dart': b'original cover\n',
            'native/neoswap-relay/Backend.cpp': b'unchanged runtime\n',
            'pubspec.yaml': b'name: neostation\nversion: 0.0.2+442\n',
            'pubspec.lock': b'locked dependency graph\n',
            'analysis_options.yaml': b'analyzer: existing rules\n',
            WORKFLOW: (ROOT / WORKFLOW).read_bytes(),
        }
        for name, data in files.items():
            path = folder / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        subprocess.run(['git', 'init', '-q', str(folder)], check=True)
        subprocess.run(['git', '-C', str(folder), 'add', '.'], check=True)
        subprocess.run(['git', '-C', str(folder), '-c', 'user.name=Test',
                        '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'baseline'], check=True)
        return files

    def test_only_cover_and_reviewed_delivery_inputs_differ_in_candidate(self):
        changed, unchanged = reuse.verify_library_covers_tree()
        self.assertGreater(len(unchanged), 2000)
        self.assertIn('lib/widgets/library_book_cover.dart', changed)
        self.assertFalse(any(p.startswith(('native/', 'packages/')) for p in changed))
        self.assertTrue({'pubspec.yaml', 'pubspec.lock', 'analysis_options.yaml'} <= unchanged.keys())
        # The wider historical lane must also recognize the new cover inputs.
        broad_changed, _ = reuse.verify_tree()
        self.assertIn('lib/widgets/library_book_cover.dart', broad_changed)
        self.assertIn('test/library_book_cover_test.dart', broad_changed)

    def test_rejects_transitive_dependencies_and_untracked_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            files = self.fixture(folder)
            with patch.object(reuse, 'ROOT', folder):
                self.assertEqual(reuse.verify_library_covers_tree('HEAD')[0], [])
                cover = folder / 'lib/widgets/library_book_cover.dart'
                cover.write_bytes(b'new cover\n')
                self.assertEqual(reuse.verify_library_covers_tree('HEAD')[0], ['lib/widgets/library_book_cover.dart'])
                for name in ('native/neoswap-relay/Backend.cpp', 'pubspec.lock', 'pubspec.yaml', 'analysis_options.yaml'):
                    with self.subTest(path=name):
                        path = folder / name
                        path.write_bytes(files[name] + b'changed\n')
                        with self.assertRaisesRegex(ValueError, 'Unreviewed library covers input changed'):
                            reuse.verify_library_covers_tree('HEAD')
                        path.write_bytes(files[name])
                rogue = folder / 'new_unreviewed_input.txt'
                rogue.write_text('must not escape the tracked comparison')
                with self.assertRaisesRegex(ValueError, 'Unreviewed library covers input changed'):
                    reuse.verify_library_covers_tree('HEAD')

    def test_rejects_deleted_symlinked_and_executable_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            files = self.fixture(folder)
            cover = folder / 'lib/widgets/library_book_cover.dart'
            with patch.object(reuse, 'ROOT', folder):
                cover.chmod(0o755)
                with self.assertRaisesRegex(ValueError, 'input mode changed'):
                    reuse.verify_library_covers_tree('HEAD')
                cover.chmod(0o644)
                cover.unlink()
                with self.assertRaisesRegex(ValueError, 'missing or symlinked'):
                    reuse.verify_library_covers_tree('HEAD')
                cover.symlink_to(folder / 'pubspec.lock')
                with self.assertRaisesRegex(ValueError, 'missing or symlinked'):
                    reuse.verify_library_covers_tree('HEAD')

    def test_delivery_and_native_recipes_cannot_hide_in_allowed_workflow_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            files = self.fixture(folder)
            workflow = folder / WORKFLOW
            with patch.object(reuse, 'ROOT', folder):
                workflow.write_text(files[WORKFLOW].decode().replace('  cold:\n', '  cold:\n    # changed packaging\n', 1))
                with self.assertRaisesRegex(ValueError, 'pinned packaging recipe'):
                    reuse.verify_library_covers_tree('HEAD')
                workflow.write_text(files[WORKFLOW].decode().replace('delivery-443-recipient.pem', 'delivery-rogue-recipient.pem'))
                with self.assertRaisesRegex(ValueError, 'pinned packaging recipe'):
                    reuse.verify_library_covers_tree('HEAD')
                workflow.write_text(files[WORKFLOW].decode().replace('xcrun clang++ "${common[@]}"', 'xcrun clang++ -DNDEBUG "${common[@]}"', 1))
                with self.assertRaisesRegex(ValueError, 'pinned native test recipe'):
                    reuse.verify_library_covers_tree('HEAD')

    def evidence(self):
        run = {'head_sha': reuse.LIBRARY_COVERS_REFERENCE, 'status': 'completed',
               'conclusion': 'success', 'path': WORKFLOW}
        steps = {
            'checks': ['Verify closed validation input tree and previous CI success',
                       'Verify reused Dart evidence and changed pipeline guards'],
            'native': ['Select Xcode 26.3 for NeoPlay and Google Cast',
                       'Validate changed RPCS3 NeoSwap allocators and iPhone control plane',
                       'Verify prior Swift success for identical transport inputs',
                       'Run the embedded libretro host against a test core',
                       'Run the portable libretro frontend modules (geometry, controls, settings, skins)',
                       'Compile and render every libretro shader preset with Metal',
                       'Compile and link every libretro bridge source for iPhone'],
            'Release device build • cold': ['Compile Release device binary with measured AOT and Xcode phases',
                                           'Package and validate NeoStation IPA',
                                           'Seal every executable, framework and extension for SideStore'],
        }
        jobs = {'jobs': [{'name': name, 'head_sha': reuse.LIBRARY_COVERS_REFERENCE,
                         'run_id': reuse.LIBRARY_COVERS_RUN, 'conclusion': 'success',
                         'steps': [{'name': step, 'conclusion': 'success'} for step in names]}
                        for name, names in steps.items()]}
        return run, jobs

    def test_reuse_requires_exact_completed_successful_build(self):
        run, jobs = self.evidence()
        for key, bad in (('head_sha', '0' * 40), ('status', 'in_progress'),
                         ('conclusion', 'failure'), ('path', 'other.yml')):
            with self.subTest(key=key):
                wrong = dict(run, **{key: bad})
                with patch.object(reuse.subprocess, 'check_output', return_value=json.dumps(wrong).encode()):
                    with self.assertRaisesRegex(ValueError, 'not successful at its exact reference'):
                        reuse.verify_library_covers_evidence()
        with patch.object(reuse.subprocess, 'check_output', side_effect=[json.dumps(run).encode(), json.dumps(jobs).encode()]):
            record = reuse.verify_library_covers_evidence()
        self.assertEqual(record['run'], 38170927050)
        self.assertTrue(record['validationWasReused'])
        self.assertFalse(record['deviceGameplayValidated'])

    def test_reuse_rejects_missing_failed_wrong_sha_or_skipped_job_evidence(self):
        run, jobs = self.evidence()
        bad_jobs = []
        missing = copy.deepcopy(jobs); missing['jobs'].pop(); bad_jobs.append(missing)
        failed = copy.deepcopy(jobs); failed['jobs'][1]['conclusion'] = 'failure'; bad_jobs.append(failed)
        wrong = copy.deepcopy(jobs); wrong['jobs'][1]['head_sha'] = '0' * 40; bad_jobs.append(wrong)
        other_run = copy.deepcopy(jobs); other_run['jobs'][1]['run_id'] = 1; bad_jobs.append(other_run)
        skipped = copy.deepcopy(jobs); skipped['jobs'][0]['steps'][1]['conclusion'] = 'skipped'; bad_jobs.append(skipped)
        for payload in bad_jobs:
            with self.subTest(payload=payload), patch.object(reuse.subprocess, 'check_output', side_effect=[json.dumps(run).encode(), json.dumps(payload).encode()]):
                with self.assertRaises(ValueError):
                    reuse.verify_library_covers_evidence()

    def test_workflow_limits_cover_lane_to_changed_tests_and_verified_native_reuse(self):
        workflow = (ROOT / WORKFLOW).read_text()
        checks, rest = workflow.split('  checks:\n', 1)[1].split('  native:\n', 1)
        native = rest.split('  cold:\n', 1)[0]
        self.assertIn('options: [full, rpcs3_neoswap, library_covers]', workflow)
        for body, names in ((checks, (
            'Reuse successful unchanged Dart validation',
            'Analyze the changed integration and its restored dependencies',
            'Reproduce the seven-root registration defect on the unchanged 422 code',
            'Validate changed library, callback, launch and restart behavior',
            'Verify reused Dart evidence and changed pipeline guards')),
            (native, ('Validate changed RPCS3 NeoSwap allocators and iPhone control plane',
                      'Preserve exact NeoSwap native validation',
                      'Verify prior Swift success for identical transport inputs',
                      'Validate changed Swift transport and compile the actual iPhone plugin',
                      'Run the embedded libretro host against a test core',
                      'Run the portable libretro frontend modules (geometry, controls, settings, skins)',
                      'Compile and render every libretro shader preset with Metal',
                      'Compile and link every libretro bridge source for iPhone'))):
            for name in names:
                step = body.split('    - name: ' + name + '\n', 1)[1].split('\n    - ', 1)[0]
                self.assertIn("inputs.validation_scope != 'library_covers'", step, name)
        self.assertIn('flutter test test/library_book_cover_test.dart test/library_ui_hub_test.dart test/library_ui_hub_open_test.dart', checks)
        self.assertIn('python3 test/library_cover_delivery_test.py', checks)
        self.assertIn('--scope library_covers', native)
        self.assertIn('NeoStation-442-neoswap-native-' + reuse.LIBRARY_COVERS_REFERENCE, native)
        self.assertIn("record['xcode']==subprocess.check_output", native)
        self.assertIn("record['iphoneSDK']==subprocess.check_output", native)
        self.assertIn('hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest', native)
        self.assertIn("if: ${{ inputs.benchmark == true || contains(github.event.head_commit.message, '[benchmark-build]') }}", workflow)


if __name__ == '__main__':
    unittest.main()
