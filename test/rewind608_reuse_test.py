"""Behavioral failures of explicit608 reuse; no emulator/simulator is run."""
import ast
import copy
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import types
import unittest
from unittest import mock

SUBJECT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(SUBJECT / '.github/diagnostics'), str(SUBJECT / 'build-utils')]
import rewind608_reuse as reuse
import rewind608_producers as producers


def entry(marker='a', mode='100644', kind='blob'):
    return dict(mode=mode, type=kind, object=marker * 40)


class ExactInputs(unittest.TestCase):
    def test_eager_import_default_is_portable_but_lazy_values_are_preserved(self):
        for source in ('import os', 'from os import path'):
            parsed = ast.parse(source).body[0]
            # Model the older node schema, rather than deleting a 3.15
            # instance field whose class-level default is still None.
            older_type = type(type(parsed).__name__, (ast.AST,),
                              {'_fields': tuple(f for f in parsed._fields if f != 'is_lazy')})
            node = older_type()
            for field, value in ast.iter_fields(parsed):
                if field != 'is_lazy':
                    setattr(node, field, value)
            self.assertFalse(hasattr(node, 'is_lazy'))
            absent = reuse.canonical_ast(node)
            self.assertEqual(absent['fields']['is_lazy'], 0)
            self.assertEqual(reuse.canonical_ast(parsed), absent)
            node.is_lazy = 0
            self.assertEqual(reuse.canonical_ast(node), absent)
            for lazy in (1, None, '', []):
                node.is_lazy = lazy
                actual = reuse.canonical_ast(node)
                self.assertIs(type(actual['fields']['is_lazy']), type(lazy))
                self.assertEqual(actual['fields']['is_lazy'], lazy)
                self.assertNotEqual(actual, absent)

    def test_actual_lazy_import_syntax_cannot_change_a_protected_import(self):
        for eager, lazy in (('import os', 'lazy import os'),
                            ('from os import path', 'lazy from os import path')):
            before = eager + '\ndef consumer():\n return 1\n'
            after = lazy + '\ndef consumer():\n return 2\n'
            if sys.version_info < (3, 15):
                with self.assertRaises(SyntaxError):
                    ast.parse(after)
            else:
                self.assertEqual(ast.parse(after).body[0].is_lazy, 1)
                with self.assertRaisesRegex(ValueError, 'outside the reviewed consumer bodies'):
                    reuse.verify_python(before, after, {'consumer'})

    def test_projection_does_not_depend_on_ast_dump_format(self):
        raw = b"def producer(a=None, b='', c=False, d=b'abc'):\n return (a, b, c, d, ...)\n"
        expected = reuse.python_projection(raw, set())
        for formatter in ('old formatting with empty fields', 'new formatting omitting empty fields'):
            with mock.patch.object(ast, 'dump', return_value=formatter) as dump:
                self.assertEqual(reuse.python_projection(raw, set()), expected)
                dump.assert_not_called()
        structured = json.loads(expected)
        defaults = structured['fields']['body'][0]['fields']['args']['fields']['defaults']
        self.assertIsNone(defaults[0]['fields']['value'])
        self.assertEqual(defaults[1]['fields']['value'], '')
        self.assertIs(defaults[2]['fields']['value'], False)
        self.assertEqual(defaults[3]['fields']['value'], {'constantBytes': '616263'})

    def test_only_known_optional_ast_fields_are_normalized(self):
        node = ast.parse("def producer(arg):\n return None\n").body[0]
        expected = reuse.canonical_ast(node)
        self.assertEqual(expected['fields']['type_params'], [])
        self.assertIsNone(expected['fields']['type_comment'])
        for field in ('type_params', 'type_comment'):
            if hasattr(node, field):
                delattr(node, field)
        self.assertEqual(reuse.canonical_ast(node), expected)
        for field in ('type_params', 'type_comment'):
            setattr(node, field, None)
        self.assertEqual(reuse.canonical_ast(node), expected)
        literal = node.body[0].value
        for value in (None, '', False, 0, 0.0):
            literal.value = value
            result = reuse.canonical_ast(node)
            actual = result['fields']['body'][0]['fields']['value']['fields']['value']
            self.assertIs(type(actual), type(value))
            self.assertEqual(actual, value)
        node.decorator_list = [ast.Name(id='new_policy', ctx=ast.Load())]
        self.assertNotEqual(reuse.canonical_ast(node), expected)

    def test_selection_is_explicit_and_unknown_values_fail(self):
        for value, expected in (('', False), (reuse.SOURCE, True)):
            with mock.patch.dict(os.environ, {'REWIND608_REUSE': value}):
                self.assertEqual(reuse.enabled(), expected)
        for value in ('true', 'false', 'latest', '0' * 40):
            with mock.patch.dict(os.environ, {'REWIND608_REUSE': value}):
                with self.assertRaises(ValueError):
                    reuse.enabled()

    def test_only_exact_recipe_files_may_change(self):
        before = {'lib/main.dart': entry(), reuse.PRODUCERS: entry()}
        after = {**before, reuse.PRODUCERS: entry('b'), reuse.MODULE: entry('c'), reuse.REUSE_TEST: entry('d')}
        self.assertEqual(reuse.validate_tree_delta(before, after),
                         sorted((reuse.PRODUCERS, reuse.MODULE, reuse.REUSE_TEST)))
        for path in ('lib/main.dart', 'pubspec.lock', 'test/touch_layout_support.py',
                     'packages/dolphin_internal_bridge/ci/device_info_sdk_compat.py',
                     '.github/diagnostics/rewind608_baseline.py', '.github/diagnostics/rewind608_checks.py'):
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    reuse.validate_tree_delta(before, {**after, path: entry('e')})

    def test_deletion_mode_symlink_gitlink_and_unknown_additions_fail(self):
        before = {reuse.PRODUCERS: entry()}
        for after in ({}, {reuse.PRODUCERS: entry('a', '100755')},
                      {reuse.PRODUCERS: entry('a', '120000')},
                      {reuse.PRODUCERS: entry('a', '160000', 'commit')},
                      {reuse.PRODUCERS: entry('b'), 'test/new_helper.py': entry('c')}):
            with self.subTest(after=after), self.assertRaises(ValueError):
                reuse.validate_tree_delta(before, after)

    def test_only_consumer_body_is_exempted(self):
        before = b"import os\nPOLICY=1\ndef consumer(kind):\n return 1\ndef producer():\n return POLICY\n"
        self.assertTrue(reuse.verify_python(before, before.replace(b'return 1', b'return 2'), {'consumer'}))
        for replacement in (
            before.replace(b'POLICY=1', b'POLICY=2'),
            before.replace(b'import os', b'import sys'),
            before.replace(b'return POLICY', b'return 4'),
            before.replace(b'consumer(kind)', b'consumer(kind=side_effect())'),
            before.replace(b'def consumer', b'@side_effect()\ndef consumer'),
            before.replace(b'consumer(kind)', b'consumer(kind: side_effect())'),
            before + b'\nconsumer(1)\n',
            before + b'\ndef consumer(kind):\n return 3\n',
        ):
            with self.subTest(replacement=replacement), self.assertRaises(ValueError):
                reuse.verify_python(before, replacement, {'consumer'})

    def test_new_helper_must_have_no_definition_time_execution(self):
        before = b"def consumer(kind):\n return 1\n"
        simple = b"\ndef helper(identity, shaders):\n return identity\n"
        self.assertTrue(reuse.verify_python(before, before + simple, {'consumer'}, {'helper'}))
        for helper in (
            simple.replace(b'shaders)', b'shaders=side_effect())'),
            simple.replace(b'def helper', b'@side_effect()\ndef helper'),
            simple.replace(b'identity,', b'identity: side_effect(),'),
            simple.replace(b'def helper', b'async def helper'),
            simple + simple,
        ):
            with self.subTest(helper=helper), self.assertRaises(ValueError):
                reuse.verify_python(before, before + helper, {'consumer'}, {'helper'})

    def test_actual_producer_projection_keeps_shared_executed_code(self):
        before = reuse.source_bytes(reuse.SOURCE, reuse.PRODUCERS)
        after = (SUBJECT / reuse.PRODUCERS).read_bytes()
        self.assertEqual(reuse.verify_python(before, after, {'origin', 'tests', 'native'},
                                            {'validate_armsx2_shaders'}),
                         '8311059a4f823683c1ba649999bc0b6897b64d95dba4a70ee970048e6d286971')
        self.assertEqual(reuse.verify_python(
            reuse.source_bytes(reuse.SOURCE, reuse.DELIVERY), (SUBJECT / reuse.DELIVERY).read_bytes(),
            {'contract', 'expected'}),
            'b1c2da2bab325e18d5002ef737ad9a935b83b4cc8fd9ffd50e3e64b6646d0502')
        for name in ('native_manifest', 'execution', 'input_paths', 'input_hashes', 'fetch', 'save'):
            changed = after.replace(('def ' + name + '(').encode(),
                                    ('def replaced_' + name + '(').encode(), 1)
            with self.subTest(name=name), self.assertRaises(ValueError):
                reuse.verify_python(before, changed, {'origin', 'tests', 'native'},
                                    {'validate_armsx2_shaders'})

    def test_rendered_workflow_preserves_producer_jobs_and_valid_expressions(self):
        original = reuse.source_bytes(reuse.SOURCE, reuse.WORKFLOW).decode()
        rendered = reuse.expected_reuse_workflow(original)
        self.assertEqual((SUBJECT / reuse.WORKFLOW).read_text(), rendered)
        self.assertNotRegex(rendered, r'\$\{(?!\{)\s*(steps|github|inputs|needs)\.')
        self.assertIn('ref: $' + '{{ github.sha }}', rendered)
        self.assertIn(reuse.PUSH_MARKER, reuse.SELECTION)
        self.assertIn("github.event_name == 'push'", reuse.SELECTION)
        self.assertIn('type: boolean', rendered)
        for name in reuse.PINS:
            pattern = r'^  ' + name + r':\n(.*?)(?=^  [a-z0-9_-]+:\n|\Z)'
            old = re.search(pattern, original, re.M | re.S).group()
            new = re.search(pattern, rendered, re.M | re.S).group()
            normalized = new.replace('    if: ' + reuse.SKIP + '\n', '', 1)
            normalized = normalized.replace('uses: ' + reuse.IPA_UPLOAD_GUARD, 'uses: actions/upload-artifact@v4')
            self.assertEqual(normalized, old)
            self.assertIn(f"needs.{name}.result == 'skipped'", reuse.APP_GATE)
            self.assertIn(f"needs.{name}.result == 'success'", reuse.APP_GATE)
        self.assertIn("needs.preflight.result == 'success'", reuse.APP_GATE)
        self.assertIn("needs.reuse.result == 'success'", reuse.APP_GATE)
        self.assertIn("needs.reuse.result == 'skipped'", reuse.APP_GATE)


class OriginalAuthority(unittest.TestCase):
    def setUp(self):
        reuse.authenticate_original.cache_clear()
        self.addCleanup(reuse.authenticate_original.cache_clear)
        self.run = dict(id=reuse.ORIGINAL['run'], head_sha=reuse.SOURCE, head_branch='Claude',
                        path=producers.WORKFLOW, run_attempt=1, status='completed',
                        conclusion='failure', event='push')
        base = dict(head_sha=reuse.SOURCE, run_id=reuse.ORIGINAL['run'],
                    run_attempt=1, status='completed', conclusion='success')
        self.jobs = [
            dict(base, id=124808921278, name='preflight', steps=[]),
            dict(base, id=124814980616, name='application', conclusion='failure', steps=[
                dict(name='Compile Release device binary with measured AOT and Xcode phases',
                     conclusion='skipped')]),
        ]
        self.artifacts = {}
        for kind, pin in reuse.PINS.items():
            self.jobs.append(dict(base, id=pin['job'], name=producers.JOBS[kind], steps=[
                dict(name=name, conclusion='success') for name in producers.REQUIRED_STEPS[kind]]))
            self.artifacts[pin['artifact']] = dict(
                id=pin['artifact'], name=f'RewindBox608-{kind}-{reuse.SOURCE}-attempt1',
                expired=False, size_in_bytes=pin['archiveBytes'], digest='sha256:' + pin['archiveSHA256'],
                workflow_run=dict(id=reuse.ORIGINAL['run'], head_sha=reuse.SOURCE))

    def api(self, endpoint):
        if endpoint == 'actions/runs/' + str(reuse.ORIGINAL['run']):
            return self.run
        if '/jobs?' in endpoint:
            return dict(total_count=len(self.jobs), jobs=self.jobs)
        return self.artifacts[int(endpoint.rsplit('/', 1)[1])]

    def call(self):
        reuse.authenticate_original.cache_clear()
        with mock.patch.object(producers, 'api', side_effect=self.api):
            return reuse.authenticate_original()

    def test_failed_whole_run_and_successful_individual_jobs_are_preserved(self):
        values = self.call()
        self.assertEqual(set(values), set(reuse.PINS))
        for kind, value in values.items():
            self.assertEqual(value['execution'], reuse.ORIGINAL)
            self.assertEqual(value['originalRunConclusion'], 'failure')
            self.assertEqual(value['originalJobConclusion'], 'success')
            self.assertEqual(value['evidenceMode'], 'reused')
            self.assertEqual(value['artifact'], reuse.PINS[kind]['artifact'])

    def test_wrong_whole_run_source_attempt_branch_or_relabelled_success_fails(self):
        baseline = copy.deepcopy(self.run)
        for change in ({'head_sha': 'd' * 40}, {'run_attempt': 2}, {'head_branch': 'main'},
                       {'id': 12}, {'status': 'in_progress'}, {'conclusion': 'success'}):
            self.run = {**baseline, **change}
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.call()

    def test_failed_skipped_or_wrong_original_job_fails(self):
        baseline = copy.deepcopy(self.jobs[2])
        for change in ({'conclusion': 'failure'}, {'conclusion': 'skipped'}, {'id': 12},
                       {'run_id': 12}, {'run_attempt': 2}, {'head_sha': 'e' * 40}):
            self.jobs[2] = {**baseline, **change}
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.call()

    def test_omitted_required_step_or_duplicate_job_fails(self):
        self.jobs[2]['steps'][0]['conclusion'] = 'skipped'
        with self.assertRaises(ValueError):
            self.call()
        self.jobs[2]['steps'][0]['conclusion'] = 'success'
        self.jobs.append(copy.deepcopy(self.jobs[2]))
        with self.assertRaises(ValueError):
            self.call()

    def test_changed_expired_wrong_named_or_wrong_source_archive_fails(self):
        identifier = reuse.PINS['native']['artifact']
        original = copy.deepcopy(self.artifacts[identifier])
        for change in ({'id': 123}, {'expired': True}, {'size_in_bytes': 1},
                       {'digest': 'sha256:' + 'f' * 64}, {'name': 'relabelled'},
                       {'workflow_run': dict(id=12, head_sha=reuse.SOURCE)},
                       {'workflow_run': dict(id=reuse.ORIGINAL['run'], head_sha='d' * 40)}):
            self.artifacts[identifier] = {**original, **change}
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.call()


class CurrentGuard(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.current = dict(source='1' * 40, tree='2' * 40, run=123, attempt=2)
        self.equivalence = dict(originSource=reuse.SOURCE, candidateSource=self.current['source'])
        self.origins = {'native': {'execution': copy.deepcopy(reuse.ORIGINAL)}}
        self.inputs = {'recipe': '3' * 64}
        self.proof = dict(schema=1, build=608, result='passed', evidenceMode='reused',
            candidateExecution=self.current.copy(), originalExecution=copy.deepcopy(reuse.ORIGINAL),
            originalRunConclusion='failure', inputEquivalence=self.equivalence,
            originalOrigins=self.origins, currentGuardInputs=self.inputs,
            unchangedSuitesReexecuted=False, coresRebuilt=False, physicalDeviceTested=False, affectedChecks=[])
        for name, argv in reuse.COMMANDS:
            raw = ('test output ' + name).encode()
            (self.folder / (name + '.log')).write_bytes(raw)
            self.proof['affectedChecks'].append(dict(name=name, argv=list(argv), exitCode=0,
                log=name + '.log', logSHA256=reuse.sha(raw), seconds=0.1))

    def call(self):
        with mock.patch.object(reuse, 'guard_input_hashes', return_value=self.inputs):
            return reuse.validate_guard(self.proof, self.current, self.equivalence, self.origins, self.folder)

    def test_current_guard_and_original_execution_remain_distinct(self):
        self.assertEqual(self.call()['candidateExecution'], self.current)
        self.assertEqual(self.call()['originalExecution'], reuse.ORIGINAL)
        self.assertNotEqual(self.current['source'], reuse.SOURCE)

    def test_nested_receipt_difference_identifies_the_exact_field(self):
        self.equivalence['producerCodeProjectionSHA256'] = {'producer.py': 'a' * 64}
        self.proof['inputEquivalence'] = copy.deepcopy(self.equivalence)
        self.proof['inputEquivalence']['producerCodeProjectionSHA256']['producer.py'] = 'b' * 64
        with self.assertRaisesRegex(ValueError, r'inputEquivalence\.producerCodeProjectionSHA256\.producer\.py'):
            self.call()

    def test_wrong_candidate_origin_inputs_or_asserted_rebuild_fails(self):
        baseline = copy.deepcopy(self.proof)
        for change in ({'candidateExecution': reuse.ORIGINAL}, {'originalExecution': self.current},
                       {'originalRunConclusion': 'success'}, {'currentGuardInputs': {}},
                       {'result': 'failed'}, {'coresRebuilt': True},
                       {'unchangedSuitesReexecuted': True}, {'inputEquivalence': {}},
                       {'physicalDeviceTested': True}, {'physicalDeviceTested': 0}):
            self.proof = {**baseline, **change}
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.call()

    def test_failed_omitted_changed_command_or_modified_log_fails(self):
        baseline = copy.deepcopy(self.proof)
        for change in ({'exitCode': 1}, {'argv': ['true']}, {'name': 'other'}, {'logSHA256': '0' * 64}):
            self.proof = copy.deepcopy(baseline)
            self.proof['affectedChecks'][0].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.call()
        self.proof = copy.deepcopy(baseline)
        self.proof['affectedChecks'].pop()
        with self.assertRaises(ValueError):
            self.call()
        self.proof = copy.deepcopy(baseline)
        (self.folder / self.proof['affectedChecks'][0]['log']).write_bytes(b'altered')
        with self.assertRaises(ValueError):
            self.call()


class CurrentAuthority(unittest.TestCase):
    def setUp(self):
        CurrentGuard.setUp(self)
        reuse.verified_guard.cache_clear()
        self.addCleanup(reuse.verified_guard.cache_clear)
        (self.folder / 'validation.json').write_text(json.dumps(self.proof))
        self.run = dict(id=self.current['run'], head_sha=self.current['source'], head_branch='Claude',
            path=reuse.WORKFLOW, run_attempt=self.current['attempt'], event='push', status='in_progress')
        self.message = '[rewind608-delivery] ' + reuse.PUSH_MARKER + ' scoped consumer fix'
        base = dict(head_sha=self.current['source'], run_id=self.current['run'],
                    run_attempt=self.current['attempt'], status='completed', conclusion='success')
        self.jobs = [
            dict(base, id=1, name=reuse.PREFLIGHT_JOB_NAME,
                 steps=[dict(name=reuse.PREFLIGHT_STEP, conclusion='success')]),
            dict(base, id=2, name=reuse.CURRENT_JOB_NAME, steps=[
                 dict(name=name, conclusion='success') for name in (reuse.CURRENT_STEP, reuse.CURRENT_UPLOAD)]),
        ]
        self.jobs.extend(dict(base, id=index + 3, name=producers.JOBS[kind],
                             conclusion='skipped', steps=[]) for index, kind in enumerate(reuse.PINS))
        self.artifact = dict(id=789, name=f"RewindBox608-reuse-{self.current['source']}-attempt{self.current['attempt']}",
            expired=False, digest='sha256:' + 'c' * 64, size_in_bytes=100,
            workflow_run=dict(id=self.current['run'], head_sha=self.current['source']))
        self.environment = dict(REWIND608_REUSE=reuse.SOURCE, REUSE_ARTIFACT_ID='789',
                                REUSE_ARTIFACT_DIGEST='c' * 64)

    def api(self, endpoint):
        if endpoint == 'actions/runs/' + str(self.current['run']):
            return self.run
        if '/jobs?' in endpoint:
            return dict(total_count=len(self.jobs), jobs=self.jobs)
        if endpoint == 'actions/artifacts/789':
            return self.artifact
        raise AssertionError('Unexpected API request: ' + endpoint)

    def call(self):
        reuse.verified_guard.cache_clear()
        with mock.patch.dict(os.environ, self.environment), \
             mock.patch.object(producers, 'execution', return_value=self.current), \
             mock.patch.object(producers, 'api', side_effect=self.api), \
             mock.patch.object(reuse, 'git_bytes', return_value=self.message.encode()), \
             mock.patch.object(reuse, 'guard_input_hashes', return_value=self.inputs), \
             mock.patch.object(reuse, 'input_equivalence', return_value=self.equivalence), \
             mock.patch.object(reuse, 'authenticate_original', return_value=self.origins), \
             mock.patch.object(reuse, '_guard_archive', return_value=self.folder):
            return reuse.verified_guard()

    def test_current_guard_completed_while_current_application_is_running(self):
        value = self.call()
        self.assertEqual(value['execution'], self.current)
        self.assertEqual(value['artifact'], self.artifact['id'])
        self.assertEqual(value['receipt'], self.proof)
        self.assertEqual(value['receipt']['originalExecution'], reuse.ORIGINAL)

    def test_missing_explicit_push_marker_rejects_reuse(self):
        for message in ('fix', '[rewind608-delivery]', reuse.PUSH_MARKER):
            self.message = message
            with self.subTest(message=message), self.assertRaises(ValueError):
                self.call()

    def test_wrong_current_run_source_branch_attempt_or_event_fails(self):
        baseline = self.run.copy()
        for change in ({'id': 15}, {'head_sha': reuse.SOURCE}, {'head_branch': 'main'},
                       {'run_attempt': 1}, {'event': 'workflow_run'}, {'path': 'other.yml'}):
            self.run = {**baseline, **change}
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.call()

    def test_preflight_must_have_actually_passed_in_candidate_attempt(self):
        baseline = copy.deepcopy(self.jobs[0])
        for change in ({'conclusion': 'skipped'}, {'head_sha': reuse.SOURCE}, {'run_id': 15},
                       {'run_attempt': 1}, {'status': 'in_progress'}, {'steps': []}):
            self.jobs[0] = {**baseline, **change}
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.call()
        self.jobs[0] = baseline
        self.jobs.append(copy.deepcopy(baseline))
        with self.assertRaises(ValueError):
            self.call()

    def test_mixed_fresh_reused_or_wrong_context_skipped_jobs_fail(self):
        baseline = copy.deepcopy(self.jobs[2])
        for change in ({'conclusion': 'success'}, {'conclusion': 'failure'}, {'head_sha': reuse.SOURCE},
                       {'run_id': 15}, {'run_attempt': 1}, {'status': 'in_progress'}):
            self.jobs[2] = {**baseline, **change}
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.call()
        self.jobs.pop(2)
        with self.assertRaises(ValueError):
            self.call()

    def test_incomplete_wrong_context_or_duplicated_current_guard_job_fails(self):
        baseline = copy.deepcopy(self.jobs[1])
        for change in ({'conclusion': 'failure'}, {'head_sha': reuse.SOURCE}, {'run_attempt': 1},
                       {'run_id': 15}, {'status': 'in_progress'}, {'steps': baseline['steps'][:1]}):
            self.jobs[1] = {**baseline, **change}
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.call()
        self.jobs[1] = baseline
        self.jobs.append(dict(baseline, id=90))
        with self.assertRaises(ValueError):
            self.call()

    def test_wrong_current_artifact_or_origin_relabelled_as_current_fails(self):
        baseline = copy.deepcopy(self.artifact)
        for change in ({'id': 15}, {'name': 'old-origin'}, {'expired': True},
                       {'digest': 'sha256:' + 'f' * 64},
                       {'workflow_run': dict(id=reuse.ORIGINAL['run'], head_sha=reuse.SOURCE)},
                       {'workflow_run': dict(id=self.current['run'], head_sha=reuse.SOURCE)}):
            self.artifact = {**baseline, **change}
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.call()


class ReusedTestMetadata(unittest.TestCase):
    def setUp(self):
        from rewind608_checks import command_names
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.old_scope = b'original reviewed scope'
        self.current = dict(source='1' * 40, tree='2' * 40, run=123, attempt=2)
        self.directories = {}
        self.original_receipts = {}
        for kind in ('flutter', 'native'):
            directory = self.root / kind
            directory.mkdir()
            commands = []
            for name in command_names(kind):
                raw = (kind + ' original ' + name).encode()
                (directory / (name + '.log')).write_bytes(raw)
                commands.append(dict(name=name, argv=['original', name], exitCode=0,
                    log=name + '.log', logSHA256=reuse.sha(raw)))
            receipt = dict(result='passed', group=kind, execution=copy.deepcopy(reuse.ORIGINAL),
                sourceScopeSHA256=reuse.sha(self.old_scope), commands=commands,
                xcodeVersion='Xcode 16.4\nBuild version fixture', swiftVersion='Apple Swift version 6.1.2')
            (directory / 'validation.json').write_text(json.dumps(receipt))
            self.directories[kind] = directory
            self.original_receipts[kind] = receipt
        self.recovery = dict(execution=self.current, receipt=dict(affectedChecks=[
            dict(name=name, argv=list(argv), exitCode=0, logSHA256='c' * 64) for name, argv in reuse.COMMANDS]))

    def call(self):
        def fetch(kind):
            return (dict(kind=kind, evidenceMode='reused', execution=copy.deepcopy(reuse.ORIGINAL)),
                    self.directories[kind])
        with mock.patch.object(producers, 'OUT', self.root / 'out'), \
             mock.patch.object(producers, 'fetch', side_effect=fetch), \
             mock.patch.object(reuse, 'source_bytes', return_value=self.old_scope), \
             mock.patch.object(reuse, 'verified_guard', return_value=self.recovery):
            return producers.tests()

    def test_only_affected_recipe_is_fresh_and_original_receipts_are_unchanged(self):
        value = self.call()
        for kind in ('flutter', 'native'):
            self.assertEqual(value[kind]['receipt'], self.original_receipts[kind])
            self.assertEqual(value[kind]['execution'], reuse.ORIGINAL)
            self.assertEqual(value[kind]['evidenceMode'], 'reused')
            for item, original in zip(value[kind]['commandEvidence'], self.original_receipts[kind]['commands']):
                if kind == 'flutter' and item['name'] == 'delivery-contract-tests':
                    self.assertEqual(item['evidenceMode'], 'fresh')
                    self.assertEqual(item['execution'], self.current)
                    self.assertEqual(item['argv'], list(reuse.COMMANDS[0][1]))
                    self.assertEqual(item['logSHA256'], 'c' * 64)
                else:
                    self.assertEqual(item['evidenceMode'], 'reused')
                    self.assertEqual(item['execution'], reuse.ORIGINAL)
                    self.assertEqual(item['argv'], original['argv'])
                    self.assertEqual(item['logSHA256'], original['logSHA256'])

    def test_relabelled_execution_scope_or_failed_original_command_fails(self):
        baseline = copy.deepcopy(self.original_receipts['native'])
        path = self.directories['native'] / 'validation.json'
        for change in ({'execution': self.current}, {'sourceScopeSHA256': '0' * 64},
                       {'result': 'failed'}, {'xcodeVersion': 'Xcode 26.3\n'}):
            path.write_text(json.dumps({**baseline, **change}))
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.call()
        modified = copy.deepcopy(baseline)
        modified['commands'][0]['exitCode'] = 1
        path.write_text(json.dumps(modified))
        with self.assertRaises(ValueError):
            self.call()

    def test_omitted_original_command_or_modified_original_log_fails(self):
        path = self.directories['flutter'] / 'validation.json'
        modified = copy.deepcopy(self.original_receipts['flutter'])
        modified['commands'].pop()
        path.write_text(json.dumps(modified))
        with self.assertRaises(ValueError):
            self.call()
        path.write_text(json.dumps(self.original_receipts['flutter']))
        command = self.original_receipts['flutter']['commands'][0]
        (self.directories['flutter'] / command['log']).write_bytes(b'changed')
        with self.assertRaises(ValueError):
            self.call()


class ReusedNativeMetadata(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.artifact = self.root / 'archive'
        self.core = self.artifact / 'ARMSX2Core.framework/ARMSX2Core'
        self.core.parent.mkdir(parents=True)
        self.core.write_bytes(b'unit fixture Mach-O boundary')
        (self.artifact / 'patched-source608').mkdir()
        (self.artifact / 'patched-source608/actual.cpp').write_text('actual source')
        revision = '9' * 40
        self.identity = dict(host_commit=reuse.SOURCE, architectures=['arm64'],
            sha256=reuse.sha(self.core.read_bytes()), revision=revision, abi_version=9,
            release='iOSv2.6.0', shader_chains=True, performance_overlays=True)
        (self.artifact / 'identity.json').write_text(json.dumps(self.identity))
        self.old_inputs = {'recipe': 'a' * 64}
        self.current_inputs = {'recipe': 'b' * 64}
        self.record = dict(schema=1, build=608, kind='armsx2', execution=reuse.ORIGINAL.copy(),
            inputs=self.old_inputs, upstreamRevision=revision,
            files=producers.member_hashes(self.artifact),
            compiledSourcePostimages=producers.member_hashes(self.artifact / 'patched-source608'))
        (self.artifact / 'producer608.json').write_text(json.dumps(self.record))
        pin = self.root / 'build-utils/armsx2/source.json'
        pin.parent.mkdir(parents=True)
        pin.write_text(json.dumps(dict(revision=revision, abi_version=9, release='iOSv2.6.0')))
        fast = self.root / 'build/fast-native/identity.json'
        fast.parent.mkdir(parents=True)
        fast.write_text('{}')
        self.value = dict(evidenceMode='reused', execution=reuse.ORIGINAL.copy(), artifact=1)

    def call(self):
        verify = types.ModuleType('verify_ipa')
        verify.macho = lambda raw: dict(architecture='arm64', platform=2, fileType=6,
            id='@rpath/ARMSX2Core.framework/ARMSX2Core', definedSymbols=['_NeoARMSX2_GetAPI'])
        benchmark = types.ModuleType('delivery_benchmark')
        benchmark.payload_fingerprint = lambda raw: 'fixture fingerprint'
        with mock.patch.object(producers, 'ROOT', self.root), \
             mock.patch.object(producers, 'OUT', self.root / 'build/delivery'), \
             mock.patch.object(producers, 'fetch', return_value=(self.value, self.artifact)), \
             mock.patch.object(producers, 'input_hashes', return_value=self.current_inputs), \
             mock.patch.object(reuse, 'original_input_hashes', return_value=self.old_inputs), \
             mock.patch.object(producers, 'validate_armsx2_shaders'), \
             mock.patch.dict(sys.modules, {'verify_ipa': verify, 'delivery_benchmark': benchmark}):
            return producers.native('armsx2')

    def test_install_retains_actual_compiler_origin_and_separate_current_input_hashes(self):
        result = self.call()
        fast = json.loads((self.root / 'build/fast-native/identity.json').read_bytes())
        self.assertEqual(result['execution'], reuse.ORIGINAL)
        self.assertEqual(result['identity']['host_commit'], reuse.SOURCE)
        self.assertEqual(result['sourceInputs'], self.old_inputs)
        self.assertEqual(result['candidateSourceInputs'], self.current_inputs)
        self.assertNotEqual(result['sourceInputs'], result['candidateSourceInputs'])
        self.assertEqual(fast['armsx2CoreHostCommit'], reuse.SOURCE)
        self.assertEqual(fast['armsx2CoreRunId'], reuse.ORIGINAL['run'])
        self.assertEqual(json.loads((self.root / 'dist/armsx2/identity.json').read_bytes()), self.identity)

    def test_relabelled_compiler_execution_is_rejected(self):
        self.record['execution'] = dict(reuse.ORIGINAL, source='7' * 40)
        (self.artifact / 'producer608.json').write_text(json.dumps(self.record))
        with self.assertRaisesRegex(ValueError, 'compiled inputs differ'):
            self.call()


if __name__ == '__main__':
    unittest.main()
