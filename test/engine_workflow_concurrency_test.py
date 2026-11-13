#!/usr/bin/env python3
"""Exercise producer/check/pin event collisions in the actual workflow concurrency expressions.

Standard library only. This evaluates the small expression subset used by these three
workflows, not the Actions scheduler; actual runner execution remains a CI check.
"""
from pathlib import Path
import fnmatch
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
EXPRESSION = re.compile(r'\$\{\{(.*?)\}\}')
TOKEN = re.compile(r"\s+|'(?:[^']|'')*'|&&|\|\||==|!=|[!(),]|[A-Za-z_][A-Za-z_0-9.]*")


def evaluate(expression, event):
    """Fail closed on unsupported syntax rather than approximating a new Actions expression."""
    parts, end = [], 0
    for match in TOKEN.finditer(expression):
        if expression[end:match.start()]:
            raise ValueError('Unsupported expression syntax: ' + expression[end:match.start()])
        end = match.end()
        token = match.group()
        if token.isspace():
            continue
        if token in event:
            parts.append(repr(event[token]))
        elif token.startswith("'"):
            parts.append(repr(token[1:-1].replace("''", "'")))
        elif token in ('true', 'false'):
            parts.append(str(token == 'true'))
        elif token in ('&&', '||', '!'):
            parts.append({'&&': 'and', '||': 'or', '!': 'not'}[token])
        elif token in ('contains', '==', '!=', '(', ')', ','):
            parts.append(token)
        else:
            raise ValueError('Unsupported expression token: ' + token)
    if expression[end:]:
        raise ValueError('Unsupported expression tail: ' + expression[end:])
    return eval(' '.join(parts), {'__builtins__': {},
                                'contains': lambda value, needle: needle.lower() in (value or '').lower()})


def event(sha='a' * 40, *, dispatch=False, build=False, message='', branch='component'):
    return {'github.sha': sha, 'github.ref': 'refs/heads/' + branch,
            'github.event_name': 'workflow_dispatch' if dispatch else 'push',
            'github.event.head_commit.message': None if dispatch else message,
            'inputs.build_core': build if dispatch else None}


def policy(workflow, context):
    text = (ROOT / '.github/workflows' / workflow).read_text()
    block = re.search(r'^concurrency:\n((?:[ \t].*\n|\n)+)', text, re.M).group(1)
    values = dict(re.findall(r'^  (group|cancel-in-progress): (.+)$', block, re.M))
    if set(values) != {'group', 'cancel-in-progress'}:
        raise ValueError('Missing concurrency fields: ' + workflow)
    group = EXPRESSION.sub(lambda match: str(evaluate(match[1], context)), values['group'])
    cancellation = values['cancel-in-progress']
    match = EXPRESSION.fullmatch(cancellation)
    cancel = evaluate(match[1], context) if match else evaluate(cancellation, context)
    if not isinstance(cancel, bool):
        raise ValueError('Cancellation must be boolean')
    return group, cancel


class EngineConcurrency(unittest.TestCase):
    def test_xenia_dispatch_and_tagged_producers_are_isolated_from_checks(self):
        checks = policy('xenia-core.yml', event(sha='b' * 40, message='[xenia-checks]'))
        self.assertTrue(checks[1])
        for trigger in (event(dispatch=True, build=True), event(message='[xenia-core] build'),
                        event(message='[xenia-pin run=123] bind')):
            with self.subTest(trigger=trigger):
                group, cancel = policy('xenia-core.yml', trigger)
                self.assertIn(trigger['github.sha'], group)
                self.assertFalse(cancel)
                self.assertNotEqual(group, checks[0])

    def test_xenia_checks_replace_only_checks_on_the_same_branch(self):
        first = policy('xenia-core.yml', event(message='[xenia-checks]'))
        for trigger in (event(sha='b' * 40, message='[xenia-checks]'), event(sha='b' * 40, dispatch=True, build=False)):
            self.assertEqual(policy('xenia-core.yml', trigger), first)
        self.assertTrue(first[1])
        self.assertNotEqual(policy('xenia-core.yml', event(branch='other', message='[xenia-checks]'))[0], first[0])
        ordinary = policy('xenia-core.yml', event(sha='b' * 40))
        self.assertNotEqual(ordinary[0], first[0])
        self.assertFalse(ordinary[1])

    def test_successive_producers_and_repeated_dispatches_never_cancel_running_builds(self):
        for workflow in ('xenia-core.yml', 's2arm-core.yml', 's2arm-engine.yml', 's2arm-prepare.yml'):
            with self.subTest(workflow=workflow):
                first = policy(workflow, event(dispatch=True, build=True))
                same_source = policy(workflow, event(dispatch=True, build=True))
                next_source = policy(workflow, event(sha='b' * 40, dispatch=True, build=True))
                self.assertEqual(same_source, first)
                self.assertFalse(first[1])
                self.assertFalse(next_source[1])
                self.assertNotEqual(first[0], next_source[0])

    def test_s2arm_push_builds_pins_and_dispatches_keep_source_groups(self):
        for workflow in ('s2arm-core.yml', 's2arm-engine.yml', 's2arm-prepare.yml'):
            for trigger in (event(), event(sha='b' * 40), event(message='[s2arm-pin run=123] bind'),
                            event(dispatch=True)):
                with self.subTest(workflow=workflow, trigger=trigger):
                    group, cancel = policy(workflow, trigger)
                    self.assertIn(trigger['github.sha'], group)
                    self.assertFalse(cancel)


def push_matches(workflow, branch, path):
    text = (ROOT / '.github/workflows' / workflow).read_text()
    block = re.search(r'^  push:\n((?:[ \t].*\n|\n)+)', text, re.M).group(1)
    branches = [value.strip() for value in re.search(r'branches: \[([^]]+)\]', block)[1].split(',')]
    patterns = re.findall(r'^      - (.+)$', block, re.M)
    if not patterns:
        raise ValueError('Producer push needs path filters: ' + workflow)
    return branch in branches and any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def selected_jobs(workflow, context):
    text = (ROOT / '.github/workflows' / workflow).read_text().split('\njobs:\n', 1)[1]
    jobs = re.findall(r'^  ([\w-]+):\n((?:(?!^  [\w-]+:).|\n)*)', text, re.M)
    result = set()
    for name, block in jobs:
        conditions = re.findall(r'^    if: (.+)$', block, re.M)
        if not conditions:
            raise ValueError('Every producer/check job needs an explicit route: ' + name)
        match = EXPRESSION.fullmatch(conditions[0])
        if not match:
            raise ValueError('Unsupported job condition')
        if evaluate(match[1], context):
            result.add(name)
    return result


class EngineRoutes(unittest.TestCase):
    def test_only_relevant_claude_paths_trigger_push_routes(self):
        for workflow, source in (
                ('xenia-core.yml', 'packages/xenia_internal_bridge/core/XeniaCore.mm'),
                ('s2arm-core.yml', 'native/s2arm/prepare/s2arm_prepare.cpp'),
                ('s2arm-engine.yml', 'build-utils/s2arm/engine/patches/fix.patch'),
                ('s2arm-prepare.yml', 'tools/s2arm_prototype/pin.json')):
            with self.subTest(workflow=workflow):
                self.assertTrue(push_matches(workflow, 'Claude', source))
                self.assertTrue(push_matches(workflow, 'Claude', '.github/workflows/' + workflow))
                self.assertFalse(push_matches(workflow, 'Claude', 'docs/AI_TASK_BOARD.md'))
                for branch in ('main', 'Backup', 'work/playlists-xenios-20261110', 'work/s2arm-switch2-prototype-20261110'):
                    self.assertFalse(push_matches(workflow, branch, source))

    def test_unmarked_pushes_start_no_jobs(self):
        for workflow in ('xenia-core.yml', 's2arm-core.yml', 's2arm-engine.yml', 's2arm-prepare.yml'):
            for message in ('ordinary source change', '[ipa-delivery:999] freeze'):
                with self.subTest(workflow=workflow, message=message):
                    self.assertEqual(selected_jobs(workflow, event(branch='Claude', message=message)), set())

    def test_xenia_checks_core_pin_and_dispatch_have_the_required_jobs(self):
        checks = {'checks', 'plugin_app'}
        cases = ((event(message='[xenia-checks]'), checks),
                 (event(message='[xenia-core]'), checks | {'core'}),
                 (event(message='[xenia-pin run=123]'), checks | {'pin'}),
                 (event(dispatch=True), checks), (event(dispatch=True, build=True), checks | {'core'}))
        for trigger, expected in cases:
            with self.subTest(trigger=trigger):
                self.assertEqual(selected_jobs('xenia-core.yml', trigger), expected)
        text = (ROOT / '.github/workflows/xenia-core.yml').read_text()
        self.assertRegex(text, r'(?m)^  core:\n(?:    .*\n)*    needs: checks$')
        review = text.split('name: The delivery review gate binds the pinned Core and its recipe\n', 1)[1]
        guard = EXPRESSION.fullmatch(re.search(r'^        if: (.+)$', review, re.M)[1])[1]
        for trigger, required in ((event(dispatch=True, build=True), False),
                                  (event(message='[xenia-core]'), False),
                                  (event(message='[xenia-pin run=123]'), True), (event(dispatch=True), True)):
            self.assertEqual(evaluate(guard, trigger), required)

    def test_s2arm_producers_require_their_own_marker_or_dispatch(self):
        for workflow, marker, job in (('s2arm-core.yml', '[s2arm-core]', 'prepare-core'),
                                     ('s2arm-engine.yml', '[s2arm-engine]', 'engine'),
                                     ('s2arm-prepare.yml', '[s2arm-prepare]', 'prepare')):
            for trigger in (event(message=marker), event(dispatch=True)):
                with self.subTest(workflow=workflow, trigger=trigger):
                    self.assertEqual(selected_jobs(workflow, trigger), {job})
        pin = '[s2arm-pin engine=101 prepare=102 sysdata=103]'
        self.assertEqual(selected_jobs('s2arm-engine.yml', event(message=pin)), {'pin'})
        self.assertEqual(selected_jobs('s2arm-engine.yml', event(message='[s2arm-engine] ' + pin)), {'pin'})
        self.assertEqual(selected_jobs('s2arm-core.yml', event(message=pin)), set())
        self.assertEqual(selected_jobs('s2arm-prepare.yml', event(message=pin)), set())


if __name__ == '__main__':
    unittest.main(verbosity=2)
