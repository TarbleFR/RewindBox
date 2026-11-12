#!/usr/bin/env python3
"""Exercise producer/check/pin event collisions in the actual workflow concurrency expressions.

Standard library only. This evaluates the small expression subset used by these three
workflows, not the Actions scheduler; actual runner execution remains a CI check.
"""
from pathlib import Path
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
        checks = policy('xenia-core.yml', event(sha='b' * 40))
        self.assertTrue(checks[1])
        for trigger in (event(dispatch=True, build=True), event(message='[xenia-core] build'),
                        event(message='[xenia-pin run=123] bind')):
            with self.subTest(trigger=trigger):
                group, cancel = policy('xenia-core.yml', trigger)
                self.assertIn(trigger['github.sha'], group)
                self.assertFalse(cancel)
                self.assertNotEqual(group, checks[0])

    def test_xenia_checks_replace_only_checks_on_the_same_branch(self):
        first = policy('xenia-core.yml', event())
        for trigger in (event(sha='b' * 40), event(sha='b' * 40, dispatch=True, build=False)):
            self.assertEqual(policy('xenia-core.yml', trigger), first)
        self.assertTrue(first[1])
        self.assertNotEqual(policy('xenia-core.yml', event(branch='other'))[0], first[0])

    def test_successive_producers_and_repeated_dispatches_never_cancel_running_builds(self):
        for workflow in ('xenia-core.yml', 's2arm-core.yml', 's2arm-engine.yml'):
            with self.subTest(workflow=workflow):
                first = policy(workflow, event(dispatch=True, build=True))
                same_source = policy(workflow, event(dispatch=True, build=True))
                next_source = policy(workflow, event(sha='b' * 40, dispatch=True, build=True))
                self.assertEqual(same_source, first)
                self.assertFalse(first[1])
                self.assertFalse(next_source[1])
                self.assertNotEqual(first[0], next_source[0])

    def test_s2arm_push_builds_pins_and_dispatches_keep_source_groups(self):
        for workflow in ('s2arm-core.yml', 's2arm-engine.yml'):
            for trigger in (event(), event(sha='b' * 40), event(message='[s2arm-pin run=123] bind'),
                            event(dispatch=True)):
                with self.subTest(workflow=workflow, trigger=trigger):
                    group, cancel = policy(workflow, trigger)
                    self.assertIn(trigger['github.sha'], group)
                    self.assertFalse(cancel)


if __name__ == '__main__':
    unittest.main(verbosity=2)
