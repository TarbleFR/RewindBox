#!/usr/bin/env python3
"""Launcher of the standard delivery recipe for the Switch 2 (S2Arm) test line (IPA B, builds from 801).

The recipe (.github/diagnostics/standard_delivery.py) is imported unchanged; this file never writes it.
Only what ties the recipe to the common line is redirected, in memory, before its entry point runs:

  delivery side (the run that builds this IPA: our branch, our workflow, our request tag)
    BRANCH, WORKFLOW, TRIGGER, TRIGGER_MARKER   module constants
    subject_build                               its request tag is a literal in the recipe
    jobs_that_run                               its default branch was bound when the recipe was imported
    trigger_paths                               its default commit message carries the common tag
  producer side (the delivered base this IPA starts from: produced on the common line, or by this line)
    verify_base, authenticate_base              run with BRANCH = the branch of the base's own line

Nothing else changes: manifests stay under build-utils/delivery/, every check keeps its condition.
The redirection is refused when the recipe's uses of those constants are not exactly the reviewed
inventory below (RECIPE_INVENTORY), so a change of the recipe cannot be silently mis-redirected.

Operations: every operation of the recipe (same arguments), plus
  request-guard     preflight: the run is on the line's branch and requests a build of this line
  recipient-guard   the recipient public key of this build is committed, is the manifest's and is the
                    one DELIVERY_RECIPIENT names (build-utils/delivery_cipher.py would otherwise fall
                    back to an old key when the variable is unset)
  inventory         print the recipe inventory this launcher was reviewed against, and the current one
"""
from __future__ import annotations

import ast
import functools
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[3]
RECIPE = '.github/diagnostics/standard_delivery.py'
VERIFIER = 'build-utils/verify_downloaded_delivery.py'

# --- The line ------------------------------------------------------------------------------------------
DELIVERY_BRANCH = 'work/s2arm-switch2-prototype-20261110'
WORKFLOW = '.github/workflows/s2arm-delivery.yml'
TRIGGER_MARKER = '[s2arm-delivery:'
TRIGGER = re.compile(r'\[s2arm-delivery:(\d{3,4})\]')
FIRST_BUILD = 801
RECIPIENT = 'build-utils/delivery-{build}-recipient.pem'
# The common line, as the recipe names it. A base is authenticated on the branch of the line that delivered it.
COMMON_BRANCH = 'Claude'
COMMON_WORKFLOW = '.github/workflows/standard-delivery.yml'
COMMON_TRIGGER_MARKER = '[ipa-delivery:'
BASE_LINES = {COMMON_WORKFLOW: COMMON_BRANCH, WORKFLOW: DELIVERY_BRANCH}

# --- Reviewed inventory of the recipe --------------------------------------------------------------------
# For every top-level function of the recipe: which line constants it reads and which line literals it
# quotes. Reviewed at .github/diagnostics/standard_delivery.py of commit 687ea833 (blob sha256 in the test).
LINE_NAMES = ('BRANCH', 'WORKFLOW', 'TRIGGER', 'TRIGGER_MARKER', 'MANIFESTS')
LINE_LITERALS = ('ipa-delivery', 'Claude', 'standard-delivery')
RECIPE_INVENTORY = {
    '<module>': ['BRANCH', 'MANIFESTS', 'TRIGGER', 'TRIGGER_MARKER', 'WORKFLOW', 'literal:Claude',
                 'literal:ipa-delivery', 'literal:standard-delivery'],
    'manifest_path': ['MANIFESTS'],
    'subject_build': ['TRIGGER', 'literal:ipa-delivery'],
    'verify_base': ['BRANCH'],
    'authenticate_base': ['BRANCH'],
    'reuse_guard': ['BRANCH', 'WORKFLOW'],
    'source_contract': ['BRANCH'],
    'materialize': ['literal:ipa-delivery'],
    'republish': ['WORKFLOW'],
    'freeze': ['BRANCH'],
    'jobs_that_run': ['BRANCH'],
    'trigger_paths': ['BRANCH', 'WORKFLOW', 'literal:Claude', 'literal:ipa-delivery'],
    'contract': ['MANIFESTS'],
    'record': ['BRANCH', 'WORKFLOW'],
}
# How each entry is handled (printed by `inventory`, asserted complete by the test).
HANDLING = {
    '<module>': 'constants: BRANCH, WORKFLOW, TRIGGER, TRIGGER_MARKER are assigned; MANIFESTS is kept',
    'manifest_path': 'kept: manifests of this line live in build-utils/delivery/ on this branch only',
    'subject_build': 'delivery side, replaced: the recipe quotes the common tag as a literal',
    'verify_base': 'producer side, wrapped: BRANCH is the base line branch while it runs',
    'authenticate_base': 'producer side, wrapped: BRANCH is the base line branch while it runs',
    'reuse_guard': 'delivery side, constants: the reused test run is an earlier run of this same build',
    'source_contract': 'delivery side, constant: GITHUB_REF_NAME is the line branch',
    'materialize': 'delivery side: calls the replaced subject_build; its literal is only a printed sentence',
    'republish': 'delivery side, constant: the republication record names this workflow',
    'freeze': 'delivery side, constant: checkout branch and origin/<branch> of the freeze',
    'jobs_that_run': 'delivery side, default argument rebound to the line branch',
    'trigger_paths': 'delivery side, constants; wrapped to give the default message the line tag',
    'contract': 'kept: the local default is the latest manifest of build-utils/delivery/',
    'record': 'delivery side, constants: the recorded run is this line\'s run and the receipt names its branch',
}
# What the downloaded-delivery verifier reads from the recipe module (attribute uses of `sd`).
VERIFIER_INVENTORY = {
    'api_binding': ['BRANCH', 'WORKFLOW', 'subject_build'],   # delivery side: the saved run of this build
    'verify': ['verify_base'],                                # producer side: wrapped
}


class LineError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise LineError(message)


def sha_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inventory(source, prefix=None):
    """{function: sorted line constants read and line literals quoted}; with `prefix`, attribute uses of it."""
    attributes = set(LINE_NAMES) | {'subject_build', 'verify_base', 'authenticate_base'}

    def uses(node):
        found = set()
        for child in ast.walk(node):
            if prefix is None and isinstance(child, ast.Name) and child.id in LINE_NAMES:
                found.add(child.id)
            elif prefix and isinstance(child, ast.Attribute) and isinstance(child.value, ast.Name) and \
                    child.value.id == prefix and child.attr in attributes:
                found.add(child.attr)
            elif prefix is None and isinstance(child, ast.Constant) and isinstance(child.value, str):
                found.update('literal:' + literal for literal in LINE_LITERALS if literal in child.value)
        return found
    result, module = {}, set()
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found = uses(node)
            if found:
                result[node.name] = sorted(found)
        else:
            module |= uses(node)
    if module:
        result['<module>'] = sorted(module)
    return result


def inventory_drift(actual, expected):
    """Readable differences between the current and the reviewed inventory (empty = identical)."""
    return [f'{name}: reviewed {expected.get(name)}, now {actual.get(name)}'
            for name in sorted(set(actual) | set(expected)) if actual.get(name) != expected.get(name)]


def check_recipe_inventory(root=ROOT):
    drift = inventory_drift(inventory((Path(root) / RECIPE).read_text()), RECIPE_INVENTORY)
    require(not drift, 'The standard recipe no longer uses its line constants as this launcher was reviewed for; '
            'review the launcher before any delivery of this line:\n- ' + '\n- '.join(drift))


def check_verifier_inventory(root=ROOT):
    drift = inventory_drift(inventory((Path(root) / VERIFIER).read_text(), prefix='sd'), VERIFIER_INVENTORY)
    require(not drift, 'The downloaded-delivery verifier no longer reads the recipe as this launcher was reviewed '
            'for:\n- ' + '\n- '.join(drift))


# --- Delivery side -------------------------------------------------------------------------------------

def subject_build(subject):
    """The build requested by `[s2arm-delivery:NNN]` at the start of the commit subject (None when absent).

    Same rules as the recipe's subject_build for its own tag: one tag at most, and it opens the subject.
    A build below 801 belongs to the shared sequence and is refused."""
    found = TRIGGER.findall(subject)
    require(len(found) <= 1, 'The commit subject requests several builds: ' + subject)
    if not found:
        return None
    require(subject.startswith(TRIGGER_MARKER + found[0] + ']'),
            'The delivery tag must start the commit subject: ' + subject)
    require(int(found[0]) >= FIRST_BUILD, f'Builds of the Switch 2 test line start at {FIRST_BUILD}: ' + subject)
    return int(found[0])


def recipient_path(build):
    return RECIPIENT.format(build=int(build))


# --- Producer side -------------------------------------------------------------------------------------

def base_branch(manifest):
    """The branch of the line that delivered the manifest's base, named by the base's workflow."""
    workflow = manifest['base'].get('workflow')
    require(workflow in BASE_LINES, 'The base was delivered by an unknown workflow: ' + repr(workflow))
    return BASE_LINES[workflow]


def on_base_line(sd, function):
    """Run a base check of the recipe with BRANCH = the branch of the base's own line, then restore it."""
    @functools.wraps(function)
    def wrapper(manifest, *arguments, **keywords):
        previous = sd.BRANCH
        sd.BRANCH = base_branch(manifest)
        try:
            return function(manifest, *arguments, **keywords)
        finally:
            sd.BRANCH = previous
    return wrapper


def with_line_message(function):
    @functools.wraps(function)
    def wrapper(build, paths, message=None, root=None, loader=None):
        message = message or f'{TRIGGER_MARKER}{build}] build(s2arm): request the private test IPA {build}'
        return function(build, paths, message, root, loader)
    return wrapper


# --- Configuration -------------------------------------------------------------------------------------

def load_recipe():
    """The recipe module under its own name, so every module that imports it gets the configured one."""
    for part in ('.github/diagnostics',):
        if str(ROOT / part) not in sys.path:
            sys.path.insert(0, str(ROOT / part))
    return importlib.import_module('standard_delivery')


def configure(sd=None):
    """Redirect the imported recipe to this line. Idempotent; refuses a recipe it was not reviewed for."""
    sd = sd or load_recipe()
    if getattr(sd, 'S2ARM_LINE', None) is not None:
        return sd
    check_recipe_inventory()
    require((sd.BRANCH, sd.WORKFLOW, sd.TRIGGER_MARKER, sd.MANIFESTS) ==
            (COMMON_BRANCH, COMMON_WORKFLOW, COMMON_TRIGGER_MARKER, 'build-utils/delivery') and
            sd.jobs_that_run.__defaults__ == (COMMON_BRANCH,) and
            sd.is_recipe(recipient_path(FIRST_BUILD)) and sd.is_recipe(WORKFLOW),
            'The standard recipe is not the common-line recipe this launcher redirects')
    sd.BRANCH = DELIVERY_BRANCH
    sd.WORKFLOW = WORKFLOW
    sd.TRIGGER = TRIGGER
    sd.TRIGGER_MARKER = TRIGGER_MARKER
    sd.subject_build = subject_build
    sd.jobs_that_run.__defaults__ = (DELIVERY_BRANCH,)
    sd.trigger_paths = with_line_message(sd.trigger_paths)
    sd.verify_base = on_base_line(sd, sd.verify_base)
    sd.authenticate_base = on_base_line(sd, sd.authenticate_base)
    sd.S2ARM_LINE = dict(branch=DELIVERY_BRANCH, workflow=WORKFLOW, tag=TRIGGER_MARKER, firstBuild=FIRST_BUILD,
                         baseLines=dict(BASE_LINES))
    return sd


# --- Operations of this line ---------------------------------------------------------------------------

def request_guard(sd, environment=None, repo=None):
    """Preflight, right after the effective tree is restored: the run is on the line branch and its head commit
    requests one build of this line; a manual run must name that same build."""
    environment = os.environ if environment is None else environment
    require(environment.get('GITHUB_REF_NAME') == DELIVERY_BRANCH and
            environment.get('GITHUB_REF', 'refs/heads/' + DELIVERY_BRANCH) == 'refs/heads/' + DELIVERY_BRANCH,
            'A delivery of this line runs on ' + DELIVERY_BRANCH + ' only')
    event = environment.get('GITHUB_EVENT_NAME', '')
    require(event in ('push', 'workflow_dispatch'), 'Unexpected event: ' + repr(event))
    repo = repo or sd.Repo()
    head = repo.commit('HEAD')
    require(head == environment.get('GITHUB_SHA', head), 'Checkout differs from the triggering source')
    requested = subject_build(repo.subject(head))
    require(requested is not None, 'The head commit subject does not start with ' + TRIGGER_MARKER + 'N]')
    if event == 'workflow_dispatch':
        asked = environment.get('REQUESTED_BUILD', '')
        require(asked.isdecimal() and int(asked) == requested,
                f'The manual run asks for build {asked!r} but the head commit requests {requested}')
    return dict(result='accepted', event=event, branch=DELIVERY_BRANCH, build=requested, source=head)


def recipient_guard(sd, environment=None, manifest=None):
    """The recipient public key of this build, and no other, receives the delivery."""
    environment = os.environ if environment is None else environment
    manifest = manifest or sd.ci_manifest()
    root = sd.ROOT
    expected = recipient_path(manifest['build'])
    value = environment.get('DELIVERY_RECIPIENT', '')
    require(value, 'DELIVERY_RECIPIENT is not set: delivery_cipher.py would encrypt to an old key')
    require(value == expected == manifest['recipient']['path'],
            f'The recipient of build {manifest["build"]} must be {expected} (variable {value!r}, manifest '
            f'{manifest["recipient"]["path"]!r})')
    require((Path(root) / expected).is_file(), 'The recipient public key is not committed: ' + expected)
    result = sd.recipient_check(manifest, environment)
    reused = sorted(path.name for path in (Path(root) / 'build-utils').glob('delivery-*-recipient.pem')
                    if path.name != Path(expected).name and sha_file(path) == result['sha256'])
    require(not reused, 'The recipient key of this build is the key of an earlier delivery: ' + ', '.join(reused))
    return dict(result='accepted', build=manifest['build'], **result)


def describe():
    actual = inventory((ROOT / RECIPE).read_text())
    return dict(recipe=RECIPE, recipeSHA256=sha_file(ROOT / RECIPE), line=dict(
        branch=DELIVERY_BRANCH, workflow=WORKFLOW, tag=TRIGGER_MARKER + 'N]', firstBuild=FIRST_BUILD,
        recipient=RECIPIENT, baseLines=BASE_LINES), reviewed=RECIPE_INVENTORY, current=actual,
        drift=inventory_drift(actual, RECIPE_INVENTORY), handling=HANDLING,
        verifier=dict(path=VERIFIER, reviewed=VERIFIER_INVENTORY,
                      current=inventory((ROOT / VERIFIER).read_text(), prefix='sd')))


LINE_OPERATIONS = ('request-guard', 'recipient-guard', 'inventory')


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == 'inventory':
        value = describe()
        print(json.dumps(value, indent=2))
        return 1 if value['drift'] else 0
    sd = configure()
    if argv and argv[0] in LINE_OPERATIONS:
        result = request_guard(sd) if argv[0] == 'request-guard' else recipient_guard(sd)
        print(json.dumps(result, indent=2))
        return 0
    return sd.main(argv)


if __name__ == '__main__':
    raise SystemExit(main())
