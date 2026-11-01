"""Offline failures of the608 recipe guards; no iOS build is claimed here."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / '.github/diagnostics'), str(ROOT / 'build-utils')]
import rewind608_baseline as baseline
import rewind608_delivery as delivery
import rewind608_producers as producers
import rewind608_checks as checks
import collect_build_source_evidence as collector


class Inventory608(unittest.TestCase):
    def test_exact_named_89_plus_one_inventory(self):
        names = sorted(delivery.inventory())
        self.assertEqual(delivery.validate_inventory(names), 90)
        self.assertIn('Frameworks/retro_achievements_session.framework/retro_achievements_session', names)
        with self.assertRaises(ValueError):
            delivery.validate_inventory(names[:-1])
        with self.assertRaises(ValueError):
            delivery.validate_inventory(names[:-1] + ['Frameworks/unreviewed.framework/unreviewed'])
        with self.assertRaises(ValueError):
            delivery.validate_inventory(names + [names[0]])

    def test_retained_rpc_identity_is_exact607(self):
        self.assertEqual(delivery.rpc.CORE_SOURCE, 'a4ae86d085c231e3c5c93f7f72d2eced0f38ec24')
        self.assertEqual(delivery.rpc.CORE_SHA256, 'f512e6c4a6a2bf3b2ff6f41a2f2e2f6b966240ec2295a35e31f406a36229001f')
        self.assertEqual(delivery.rpc.CORE_RUN, 41243687649)
        self.assertEqual(baseline.BASE, '68552e27770b114ecc9a347600816132794b4fae')
        self.assertEqual(baseline.BASELINE['run'], 41246903346)
        self.assertIn('.github/diagnostics/rpcs3runtime607_core.py', baseline.PRESERVED)

    def test_additive_dolphin_exports_include_old_and_new_contract(self):
        self.assertTrue({'_neostation_dolphin_configure_achievements',
                         '_neostation_dolphin_configure_achievements_session',
                         '_neostation_dolphin_achievements_snapshot',
                         '_neostation_dolphin_set_achievement_presenter'} <= producers.DOLPHIN_EXPORTS)

    def test_scope_cannot_be_regenerated_in_ci(self):
        with mock.patch.dict(os.environ, {'CI': 'true'}):
            with self.assertRaisesRegex(ValueError, 'may not be generated in CI'):
                baseline.freeze()

    def test_artifact_member_inventory_rejects_links(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'real').write_text('source')
            self.assertEqual(producers.member_hashes(root), {'real': baseline.sha(b'source')})
            (root / 'link').symlink_to('real')
            with self.assertRaises(ValueError):
                producers.member_hashes(root)

    def test_patched_common_sources_are_retained_with_core_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'upstream'
            path = 'common/Darwin/DarwinMisc.cpp'
            (source / path).parent.mkdir(parents=True)
            (source / path).write_text('actual patched source\n')
            with mock.patch.object(producers.subprocess, 'check_output', side_effect=[path + '\n', '']):
                changed = producers.retain_patched_sources(source, root / 'retained')
            self.assertEqual(changed, {path: baseline.sha(b'actual patched source\n')})
            self.assertEqual((root / 'retained' / path).read_bytes(), (source / path).read_bytes())


class SameRun608(unittest.TestCase):
    def setUp(self):
        self.execution = dict(source='a' * 40, tree='b' * 40, run=123, attempt=2)
        self.run = dict(head_sha='a' * 40, head_branch='Claude', path=producers.WORKFLOW,
                        run_attempt=2, event='push', status='in_progress', conclusion=None)
        self.job = dict(id=456, name=producers.JOBS['dolphin'], head_sha='a' * 40, run_id=123,
                       run_attempt=2, status='completed', conclusion='success',
                       steps=[dict(name=name, conclusion='success') for name in producers.REQUIRED_STEPS['dolphin']])
        self.artifact = dict(id=789, name='RewindBox608-dolphin-' + 'a' * 40 + '-attempt2',
                             digest='sha256:' + 'c' * 64, expired=False, size_in_bytes=100,
                             workflow_run=dict(id=123, head_sha='a' * 40))

    def call(self):
        responses = [self.run, dict(total_count=1, jobs=[self.job]), self.artifact]
        with mock.patch.object(producers, 'execution', return_value=self.execution), \
             mock.patch.object(producers, 'api', side_effect=responses), \
             mock.patch.dict(os.environ, {'DOLPHIN_ARTIFACT_ID': '789', 'DOLPHIN_ARTIFACT_DIGEST': 'c' * 64}):
            return producers.origin('dolphin')

    def test_completed_prerequisite_accepted_while_ipa_run_is_active(self):
        self.assertEqual(self.call()['artifact'], 789)

    def test_wrong_source_rejected(self):
        self.run['head_sha'] = 'd' * 40
        with self.assertRaises(ValueError):
            self.call()

    def test_old_attempt_rejected(self):
        self.job['run_attempt'] = 1
        with self.assertRaises(ValueError):
            self.call()

    def test_pending_or_failed_job_rejected(self):
        for state in ('in_progress', 'queued'):
            with self.subTest(state=state):
                self.job.update(status=state, conclusion=None)
                with self.assertRaises(ValueError):
                    self.call()
        self.job.update(status='completed', conclusion='failure')
        with self.assertRaises(ValueError):
            self.call()

    def test_missing_successful_compilation_step_rejected(self):
        self.job['steps'][0]['conclusion'] = 'skipped'
        with self.assertRaises(ValueError):
            self.call()

    def test_old_named_or_expired_or_changed_archive_rejected(self):
        original = copy.deepcopy(self.artifact)
        for update in ({'expired': True}, {'digest': 'sha256:' + 'd' * 64},
                       {'name': 'DolphinCore-AchievementTranslation-' + 'a' * 40},
                       {'workflow_run': dict(id=122, head_sha='a' * 40)}):
            with self.subTest(update=update):
                self.artifact = {**original, **update}
                with self.assertRaises(ValueError):
                    self.call()


class DeclarationChain608(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.audit_name = 'docs/evidence/package-sources-license-audit-2026-10-21.json'
        self.prior_name = 'docs/evidence/achievement-translation-declarations-2026-10-31.json'
        self.session_name = 'docs/evidence/retro-achievements-session-declarations-2026-11-01.json'
        self.old_paths = ('pubspec.yaml', *baseline.DECLARATION_PATHS[1:4],
            'packages/achievement_translation/pubspec.yaml',
            'packages/achievement_translation/ios/achievement_translation.podspec')
        self.extra = 'packages/unchanged/pubspec.yaml'
        self.write('pubspec.lock', b'unchanged hosted packages\n')
        lock = baseline.sha((self.root / 'pubspec.lock').read_bytes())
        for path in collector.SOURCE_DOCUMENTS:
            self.write('docs/' + path, b'Original unresolved source notice\n')
        for path in collector.SOURCE_EVIDENCE:
            self.write('docs/evidence/' + path, b'{}\n')
        old = {p: baseline.sha(('original ' + p).encode()) for p in self.old_paths[:4]}
        old[self.extra] = baseline.sha(b'unchanged declaration')
        self.write(self.extra, b'unchanged declaration')
        self.write(self.audit_name, dict(pubspec_lock_sha256=lock, source_declaration_sha256=old))
        updated = {p: dict(before=old.get(p), after=baseline.sha(('translation ' + p).encode())) for p in self.old_paths}
        self.write(self.prior_name, dict(schema=1, baseline_inventory=self.audit_name,
            baseline_inventory_sha256=self.digest(self.audit_name), pubspec_lock_sha256=lock,
            complete_corresponding_source_attested=False, declarations=updated))
        followup = {}
        for path in baseline.DECLARATION_PATHS:
            raw = ('session ' + path).encode()
            followup[path] = dict(before=updated[path]['after'] if path in updated else None,
                                 after=baseline.sha(raw))
            self.write(path, raw)
        for path in self.old_paths[4:]:
            self.write(path, ('translation ' + path).encode())
        self.write(self.session_name, dict(schema=1, baseline_inventory=self.prior_name,
            baseline_inventory_sha256=self.digest(self.prior_name), pubspec_lock_sha256=lock,
            complete_corresponding_source_attested=False, declarations=followup,
            dependency_changes=dict(external_packages_added=[])))

    def write(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value if isinstance(value, bytes) else (json.dumps(value) + '\n').encode())

    def digest(self, name):
        return baseline.sha((self.root / name).read_bytes())

    def test_two_authentic_scoped_reviews_preserve_historical_chain(self):
        result = collector.repository_inputs(self.root)
        self.assertIn(self.session_name, result)
        self.assertIn(self.audit_name, result)
        self.assertIn(self.prior_name, result)

    def test_changed_current_declaration_rejected(self):
        self.write('pubspec.yaml', b'undeclared dependency')
        with self.assertRaises(SystemExit):
            collector.repository_inputs(self.root)

    def test_changed_untouched_declaration_rejected(self):
        self.write(self.extra, b'undeclared dependency')
        with self.assertRaises(SystemExit):
            collector.repository_inputs(self.root)

    def test_rewriting_the_historical_review_rejected(self):
        value = json.loads((self.root / self.prior_name).read_bytes())
        value['declarations']['pubspec.yaml']['after'] = '0' * 64
        self.write(self.prior_name, value)
        with self.assertRaises(SystemExit):
            collector.repository_inputs(self.root)

    def test_new_hosted_dependency_or_new_scope_rejected(self):
        self.write('pubspec.lock', b'changed hosted packages')
        with self.assertRaises(SystemExit):
            collector.repository_inputs(self.root)


class RetainedArchives608(unittest.TestCase):
    def origin(self, change=None):
        pin = delivery.RETAINED_ARCHIVES['libretro']
        artifact = dict(id=pin['artifact'], name=pin['name'], size_in_bytes=pin['bytes'],
            digest='sha256:' + pin['sha256'], expired=False, expires_at='2026-11-03T16:19:42Z',
            workflow_run=dict(id=pin['run'], head_sha=pin['source']))
        artifact.update(change or {})
        with mock.patch.object(delivery.engine, 'api', return_value=artifact):
            return delivery.retained_archive_origin('libretro')

    def test_exact_archive_identity_accepted(self):
        self.assertEqual(self.origin()['artifact'], 12280822192)

    def test_expired_archive_rejected_before_native_builds(self):
        with self.assertRaises(ValueError):
            self.origin({'expired': True})

    def test_same_name_new_archive_rejected(self):
        with self.assertRaises(ValueError):
            self.origin({'id': 12280822193})

    def test_changed_archive_bytes_rejected(self):
        for update in ({'digest': 'sha256:' + '0' * 64}, {'size_in_bytes': 1}):
            with self.subTest(update=update):
                with self.assertRaises(ValueError):
                    self.origin(update)


class CentralReceipt608(unittest.TestCase):
    def receipt(self):
        return dict(status='passed', contract=dict(test_methods=['testCase' + str(i) for i in range(35)]),
                    xctest_summary=dict(totalTestCount=35, failedTests=0, skippedTests=0))

    def test_actual_harness_status_schema_accepted(self):
        value = self.receipt()
        self.assertEqual(checks.validate_central_receipt(value), value)

    def test_source_check_or_incomplete_execution_rejected(self):
        for value in ({'result': 'passed'}, dict(self.receipt(), status='running'),
                      dict(self.receipt(), contract=dict(test_methods=['testOne']))):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    checks.validate_central_receipt(value)

    def test_skipped_failed_or_omitted_tests_rejected(self):
        for update in ({'failedTests': 1}, {'skippedTests': 1}, {'totalTestCount': 34}):
            value = self.receipt()
            value['xctest_summary'].update(update)
            with self.subTest(update=update):
                with self.assertRaises(ValueError):
                    checks.validate_central_receipt(value)


if __name__ == '__main__':
    unittest.main(verbosity=2)
