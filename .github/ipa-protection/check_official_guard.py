#!/usr/bin/env python3
"""Every guarded workflow that builds, packages or publishes an IPA runs only in the official repository.

Maintainer decision of 16 November 2026: test IPAs are built only by TarbleFR/RewindBox. Each job of such a
workflow carries the guard as its first conjunct, so a fork that enables Actions skips it:

    if: ${{ github.repository == 'TarbleFR/RewindBox' }}
    if: ${{ github.repository == 'TarbleFR/RewindBox' && (<previous condition>) }}

The standard recipe cannot change its workflow (a product test pins it): standard_delivery.fork_gate, called by
materialize (the first step of every job), refuses a fork's run unless it rebuilds a published release exactly.
The workflows listed in EXEMPT keep their text for the reason given. Standard library only (Linux, macOS and
Windows runners). Exit 1 with one message per problem.
"""
from __future__ import annotations

import ast
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
REPOSITORY = 'TarbleFR/RewindBox'
GUARD = "github.repository == '%s'" % REPOSITORY
CONDITION = re.compile(r'^    if: \$\{\{ (.*) \}\}\s*$')
# A workflow that encrypts, packages, archives, exports or publishes an app (or an IPA asset).
SIGNALS = re.compile(r'delivery_cipher\.py|\.ipa\b|Payload/|-exportArchive|flutter build (?:ios|ipa)|'
                     r'gh release (?:create|upload|edit)|releases/assets|xcodebuild[^\n]*\barchive\b')
RECIPE_GATE = ('standard-delivery.yml: its text is pinned by test/ipa_build_cache_test.py; '
               'standard_delivery.fork_gate (called by materialize) refuses fork runs')
PINNED = 'legacy per-build route pinned by %s; guard it in the change that updates that pin'
CHECKS = 'checks or inspects IPAs without building one'
MAIN_ONE_SHOT = ('one-shot 0.0.9 release fix triggered by a push to main touching its own file: any edit would '
                 're-run it at the next main update; keep it byte-identical')
EXEMPT = {
    'publish-fix-009.yml': MAIN_ONE_SHOT,
    'rename-fix-009-ipa.yml': MAIN_ONE_SHOT,
    'standard-delivery.yml': RECIPE_GATE,
    's2arm-delivery.yml': 'generated from standard-delivery.yml (s2arm/make_workflow.py); its operations run '
                          'standard_delivery.main, whose materialize applies the fork gate',
    'rewind608-retro-achievements-delivery.yml': PINNED % 'test/delivery609_contract_test.py (exact 608 transform)',
    'rewind609-hogwarts-liveness-delivery.yml': PINNED % 'test/delivery609_contract_test.py (exact 608 transform)',
    'rewind610-delivery.yml': PINNED % 'test/rewind610_delivery_contract_test.py (exact reviewed transform)',
    'legal-compliance-check.yml': CHECKS,
    'private-ipa-policy.yml': CHECKS + ' (its fixture is not an application)',
    'retroarch-relaunch-proof.yml': CHECKS,
    'retroarch-source-proof.yml': CHECKS,
    'rpcs3-cell528-host.yml': CHECKS,
    'xenia-core.yml': 'builds an engine; its IPA mentions are identity checks (test/ipa_identity_engines_test.py)',
}


def jobs(text):
    """[(job id, [lines of its block])] of a workflow's top-level jobs mapping (2-space job keys)."""
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if re.match(r'^jobs:\s*(#.*)?$', line)), None)
    if start is None:
        return []
    end = next((i for i in range(start + 1, len(lines)) if re.match(r'^\S', lines[i])), len(lines))
    keys = [i for i in range(start + 1, end) if re.match(r'^  [A-Za-z0-9_-]+:\s*(#.*)?$', lines[i])]
    return [(re.match(r'^  ([A-Za-z0-9_-]+):', lines[i]).group(1), lines[i + 1:(keys + [end])[n + 1]])
            for n, i in enumerate(keys)]


def guarded(line):
    """The condition is exactly ${{ GUARD }} or ${{ GUARD && (<rest>) }}: <rest> is one parenthesised group that
    closes at the very end (quoted strings ignored) and holds no other template, so no || can bypass the guard."""
    match = CONDITION.match(line)
    if not match:
        return False
    body = match.group(1)
    if body == GUARD:
        return True
    prefix = GUARD + ' && '
    rest = body[len(prefix):] if body.startswith(prefix) else ''
    if not rest.startswith('('):
        return False
    depth, quoted, index = 0, False, 0
    while index < len(rest):
        char = rest[index]
        if quoted:
            if char == "'" and rest[index + 1:index + 2] == "'":
                index += 1
            elif char == "'":
                quoted = False
        elif char == "'":
            quoted = True
        elif rest.startswith('${{', index) or rest.startswith('}}', index):
            return False
        elif char == '(':
            depth += 1
        elif char == ')':
            depth -= 1
            if depth == 0 and index != len(rest) - 1:
                return False
        index += 1
    return depth == 0 and not quoted


def unguarded_jobs(text):
    found = []
    for job, block in jobs(text):
        conditions = [line for line in block if re.match(r'^    if:', line)]
        if len(conditions) != 1 or not guarded(conditions[0]):
            found.append(job)
    return found


def recipe_gate_errors(root):
    """standard_delivery.materialize must call fork_gate before it loads or restores anything."""
    source = (root / '.github/diagnostics/standard_delivery.py').read_text(encoding='utf-8')
    tree = ast.parse(source)
    names = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
    if not {'fork_gate', 'run_repository', 'release_rebuild', 'materialize'} <= names:
        return ['standard_delivery.py lost its fork gate (fork_gate, run_repository, release_rebuild)']
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'materialize')
    text = ast.get_source_segment(source, function) or ''
    if 'fork_gate(' not in text or any(name in text and text.index('fork_gate(') > text.index(name)
                                       for name in ('load_manifest(', 'materialize_tree(')):
        return ['standard_delivery.materialize must call fork_gate before load_manifest and materialize_tree']
    return []


def errors(root=ROOT):
    problems = recipe_gate_errors(Path(root))
    workflows = sorted(Path(root, '.github/workflows').glob('*.y*ml'))
    present = {path.name for path in workflows}
    for name in sorted(set(EXEMPT) - present):
        problems.append(f'{name}: listed in EXEMPT but missing; remove the entry')
    for path in workflows:
        text = path.read_text(encoding='utf-8')
        if path.name in EXEMPT or not SIGNALS.search(text):
            continue
        missing = unguarded_jobs(text)
        if not jobs(text):
            problems.append(f'{path.name}: builds or ships an IPA but has no jobs mapping this check can read')
        elif missing:
            problems.append(f'{path.name}: builds or ships an IPA but job(s) {", ".join(missing)} lack the first '
                            f'conjunct "if: ${{{{ {GUARD} ... }}}}" (forks must skip them)')
    return problems


def main():
    problems = errors()
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        return 1
    print('Every IPA workflow outside EXEMPT (%d legacy or check routes) runs only in %s; the standard recipe '
          'keeps its fork gate.' % (len(EXEMPT), REPOSITORY))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
