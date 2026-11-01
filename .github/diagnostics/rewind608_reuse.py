"""Explicit recovery of the successful 0279198 prerequisites, not a fresh run.

The original whole workflow failed in its application consumer. Its four
successful prerequisite jobs, archives, receipts and source identities remain
unaltered. Only the changed recipe contracts run again; product tests and cores
may be reused only after an exact repository-wide input comparison.
"""
from __future__ import annotations

import argparse
import ast
import copy
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import zipfile

import rewind608_baseline as tree
import rewind608_producers as producers

ROOT = tree.ROOT
SOURCE = '0279198b1c33d869550cae3cf35f155b9d3a4f79'
ORIGINAL = dict(source=SOURCE, tree='67f9f0c891d86b09d04c4f273931eeb0d33f602e',
                run=41293321826, attempt=1)
ORIGINAL_SCOPE = 'e1a10e7ac140b1c018989c59efd59cb0c301f0e460b355663a9700b78e182b1a'
PINS = {
    'flutter': dict(job=124808995458, artifact=13077931904, archiveBytes=12621,
                    archiveSHA256='39e91ced6ab771c9a09087db9336cda93d6528ad5a356f0a810f53983f0693ff'),
    'native': dict(job=124808995448, artifact=13078266751, archiveBytes=69659,
                   archiveSHA256='8aaf4a7c1f36c68352d143f7962998f30ad6a574c56ee0c8f71cbc5c39e044e9'),
    'dolphin': dict(job=124810929735, artifact=13078193437, archiveBytes=11191038,
                    archiveSHA256='9d32c236c79c43cd57053b000dfaba94c4e0d6f627bd04a657f74b36dd58c064'),
    'armsx2': dict(job=124810929747, artifact=13078023872, archiveBytes=14042625,
                   archiveSHA256='e4354b47eee93d5dc8d53be070a88cc83ceb8b31ff4f7ccdca2eb2c2067b8763'),
}
MODULE = '.github/diagnostics/rewind608_reuse.py'
PRODUCERS = '.github/diagnostics/rewind608_producers.py'
DELIVERY = '.github/diagnostics/rewind608_delivery.py'
WORKFLOW = producers.WORKFLOW
CONTRACT_TEST = 'test/rewind608_delivery_contract_test.py'
REUSE_TEST = 'test/rewind608_reuse_test.py'
ALLOWED_RECIPE_PATHS = frozenset((MODULE, PRODUCERS, DELIVERY, WORKFLOW, CONTRACT_TEST,
                                REUSE_TEST, tree.CONFIG))
CURRENT_JOB_NAME = 'Build608 reuse verified0279198 prerequisites'
PREFLIGHT_JOB_NAME = 'Build608 authenticate delivered607 and immutable retained engines'
PREFLIGHT_STEP = 'Require reviewed607 delta and authenticated retained producer archives'
CURRENT_STEP = 'Authenticate identical inputs and run only affected recipe contracts'
CURRENT_UPLOAD = 'Preserve explicit reused-origin proof and current contract logs'
COMMANDS = (
    ('delivery-contract-tests', ('python3', '-B', CONTRACT_TEST)),
    ('reuse-contract-tests', ('python3', '-B', REUSE_TEST)),
)
PUSH_MARKER = '[rewind608-reuse0279198]'
SELECTION = "(inputs.reuse_0279198 || (github.event_name == 'push' && contains(github.event.head_commit.message, '[rewind608-reuse0279198]')))"
SKIP = '${{ !' + SELECTION + ' }}'
SELECT = '${{ ' + SELECTION + ' }}'
APP_GATE = ("${{ always() && !cancelled() && needs.preflight.result == 'success' && "
    "((" + SELECTION + " && needs.reuse.result == 'success' && "
    "needs.flutter.result == 'skipped' && needs.native.result == 'skipped' && "
    "needs.dolphin.result == 'skipped' && needs.armsx2.result == 'skipped') || "
    "(!" + SELECTION + " && needs.reuse.result == 'skipped' && "
    "needs.flutter.result == 'success' && needs.native.result == 'success' && "
    "needs.dolphin.result == 'success' && needs.armsx2.result == 'success')) }}")
require, sha = tree.require, tree.sha


def enabled():
    value = os.environ.get('REWIND608_REUSE', '')
    require(value in ('', SOURCE), 'Unknown explicit608 reuse selection; no automatic fallback')
    return value == SOURCE


def replace_once(text, before, after):
    require(text.count(before) == 1, 'The reviewed workflow anchor changed: ' + before[:100])
    return text.replace(before, after, 1)


def expected_reuse_workflow(original):
    """Exact text transform: preserves all original producer steps and context.

    This is intentionally stricter than a YAML semantic comparison and needs no
    extra YAML dependency. It is a verifier, never a CI source-writing command.
    """
    value = replace_once(original, '  workflow_dispatch: {}',
        "  workflow_dispatch:\n    inputs:\n      reuse_0279198:\n"
        "        description: Reuse only verified0279198 tests and cores; fail on any changed input\n"
        "        type: boolean\n        required: false\n        default: false")
    for kind in PINS:
        value = replace_once(value, f'  {kind}:\n', f'  {kind}:\n    if: {SKIP}\n')
    outputs = '\n'.join(
        f"      {kind}-{field}: " + '${{ steps.check.outputs.' + f'{kind}-{field}' + ' }}'
        for kind in PINS for field in ('artifact-id', 'artifact-digest'))
    reuse_job = f"""  reuse:
    name: {CURRENT_JOB_NAME}
    needs: preflight
    if: {SELECT}
    runs-on: ubuntu-latest
    timeout-minutes: 15
    env:
      REWIND608_REUSE: {SOURCE}
    outputs:
      artifact-id: ${{{{ steps.proof.outputs.artifact-id }}}}
      artifact-digest: ${{{{ steps.proof.outputs.artifact-digest }}}}
{outputs}
    steps:
    - name: Checkout exact candidate and original history
      uses: actions/checkout@v4
      with:
        ref: ${{{{ github.sha }}}}
        fetch-depth: 0
        persist-credentials: false
    - name: {CURRENT_STEP}
      id: check
      run: python3 -B {MODULE} prepare
    - name: {CURRENT_UPLOAD}
      id: proof
      if: always()
      uses: actions/upload-artifact@v4
      with:
        name: RewindBox608-reuse-${{{{ github.sha }}}}-attempt${{{{ github.run_attempt }}}}
        path: build/validation608/reuse/
        if-no-files-found: error
        retention-days: 14
"""
    value = replace_once(value, '  application:\n', reuse_job + '  application:\n')
    value = replace_once(value, '    name: Build608 full Flutter IPA with exact607 retained engines\n',
        '    name: Build608 full Flutter IPA with exact607 retained engines\n' +
        f'    if: {APP_GATE}\n')
    value = replace_once(value, '    - armsx2\n    runs-on: macos-15\n',
        '    - armsx2\n    - reuse\n    runs-on: macos-15\n')
    for kind in ('DOLPHIN', 'ARMSX2'):
        value = replace_once(value, f'      {kind}_CORE_HOST_SHA: ' + '${{ github.sha }}',
            f'      {kind}_CORE_HOST_SHA: ' +
            "${{ " + SELECTION + " && '" + SOURCE + "' || github.sha }}")
        value = replace_once(value, f'      {kind}_CORE_RUN_ID: ' + '${{ github.run_id }}',
            f'      {kind}_CORE_RUN_ID: ' +
            "${{ " + SELECTION + " && '41293321826' || github.run_id }}")
    for kind in PINS:
        for suffix, output in (('ID', 'id'), ('DIGEST', 'digest')):
            old = f'      {kind.upper()}_ARTIFACT_{suffix}: ' + \
                '${{ needs.' + kind + '.outputs.artifact-' + output + ' }}'
            new = f'      {kind.upper()}_ARTIFACT_{suffix}: ' + \
                '${{ ' + SELECTION + ' && needs.reuse.outputs.' + kind + \
                '-artifact-' + output + ' || needs.' + kind + '.outputs.artifact-' + output + ' }}'
            value = replace_once(value, old, new)
    anchor = '      DELIVERY_MODE: cold\n'
    value = replace_once(value, anchor, anchor +
        "      REWIND608_REUSE: ${{ " + SELECTION + " && '" + SOURCE + "' || '' }}\n" +
        "      REUSE_ARTIFACT_ID: ${{ needs.reuse.outputs.artifact-id }}\n" +
        "      REUSE_ARTIFACT_DIGEST: ${{ needs.reuse.outputs.artifact-digest }}\n")
    for before, after in (
        ('Authenticate and install same-run608 Dolphin session Core', 'Authenticate and install explicitly selected608 Dolphin session Core'),
        ('Authenticate and install same-run608 ARMSX2 ABI9 Core', 'Authenticate and install explicitly selected608 ARMSX2 ABI9 Core'),
        ('Authenticate actual same-run608 test jobs, receipts and command logs', 'Authenticate original608 test jobs, current recovery guards and command logs'),
    ):
        value = replace_once(value, before, after)
    return value


def canonical_ast(value):
    """Portable structural AST; optional schema fields never hide literal values."""
    if isinstance(value, ast.AST):
        name = type(value).__name__
        fields = dict(ast.iter_fields(value))
        optional = {}
        if name in ('FunctionDef', 'AsyncFunctionDef', 'ClassDef'):
            optional['type_params'] = []
        if name in ('FunctionDef', 'AsyncFunctionDef', 'Assign', 'For', 'AsyncFor',
                    'With', 'AsyncWith', 'arg'):
            optional['type_comment'] = None
        if name == 'Constant':
            optional['kind'] = None
        if name in ('TypeVar', 'ParamSpec', 'TypeVarTuple'):
            optional['default_value'] = None
        for field, default in optional.items():
            if field not in fields or fields[field] is None or fields[field] == [] or fields[field] == '':
                fields[field] = default
        return dict(node=name, fields={key: canonical_ast(item) for key, item in fields.items()})
    if isinstance(value, list):
        return [canonical_ast(item) for item in value]
    if isinstance(value, tuple):
        return dict(constantTuple=[canonical_ast(item) for item in value])
    if isinstance(value, bytes):
        return dict(constantBytes=value.hex())
    if isinstance(value, complex):
        return dict(constantComplex=[value.real.hex(), value.imag.hex()])
    if value is Ellipsis:
        return dict(constantEllipsis=True)
    require(value is None or type(value) in (str, int, float, bool), 'Unsupported semantic AST value')
    return value


def python_projection(raw, bodies, new_helpers=()):
    parsed = ast.parse(raw)
    seen = set()
    kept = []
    for index, node in enumerate(parsed.body):
        if index == 0 and isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            continue  # A module docstring is descriptive, not an executed expression.
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in bodies | set(new_helpers):
            require(node.name not in seen, 'Duplicated consumer/helper definition: ' + node.name)
            seen.add(node.name)
            if node.name in new_helpers:
                require(isinstance(node, ast.FunctionDef) and not node.decorator_list and
                    not node.args.defaults and not node.args.kw_defaults and not node.returns and
                    not node.args.vararg and not node.args.kwarg and not getattr(node, 'type_params', []) and
                    all(a.annotation is None for a in node.args.posonlyargs + node.args.args + node.args.kwonlyargs),
                    'New consumer helper has executable definition-time behavior')
                continue
            node = copy.deepcopy(node)
            node.body = [ast.Pass()]  # Preserve signatures, annotations, defaults and decorators.
        kept.append(node)
    require(bodies <= seen, 'An existing consumer definition was removed')
    parsed.body = kept
    return json.dumps(canonical_ast(parsed), ensure_ascii=True, sort_keys=True, separators=(',', ':'))


def verify_python(before, after, bodies, new_helpers=()):
    old = python_projection(before, set(bodies))
    new = python_projection(after, set(bodies), new_helpers)
    require(old == new, 'Producer/import/helper code changed outside the reviewed consumer bodies')
    return sha(old.encode())


def git_bytes(*arguments):
    return subprocess.check_output(['git', *arguments], cwd=ROOT, timeout=120)


def source_bytes(source, path):
    require(re.fullmatch('[0-9a-f]{40}', source), 'Source must be a complete immutable commit')
    tree.safe_path(path)
    return git_bytes('show', source + ':' + path)


def tracked_tree(source):
    result = {}
    for entry in git_bytes('ls-tree', '-r', '-z', '--full-tree', source).split(b'\0'):
        if entry:
            header, path = entry.split(b'\t', 1)
            mode, kind, object_id = header.decode().split()
            name = path.decode()
            require(name not in result, 'Duplicated tracked source path')
            result[name] = dict(mode=mode, type=kind, object=object_id)
    return result


def validate_tree_delta(before, after):
    changed = {path for path in before.keys() | after.keys() if before.get(path) != after.get(path)}
    require(changed and changed <= ALLOWED_RECIPE_PATHS,
            'Reuse changes a product, tool, dependency or test input: ' + repr(sorted(changed - ALLOWED_RECIPE_PATHS)))
    for path in changed:
        old, new = before.get(path), after.get(path)
        require(new is not None and new['type'] == 'blob' and new['mode'] == '100644',
                'Reuse recipe was removed or has a nonregular/executable mode: ' + path)
        require(old is None or (old['mode'] == new['mode'] and old['type'] == new['type']),
                'Tracked source mode/type changed: ' + path)
        require(old is not None or path in (MODULE, REUSE_TEST), 'Unexpected new recipe file: ' + path)
    return sorted(changed)


def input_equivalence(origin_source=SOURCE, candidate_source=None):
    """Pure/read-only source proof; explicit commits, no network or GITHUB env."""
    candidate_source = candidate_source or tree.git('rev-parse', 'HEAD')
    require(origin_source == SOURCE and re.fullmatch('[0-9a-f]{40}', candidate_source or ''),
            'Reuse supports only the reviewed0279198 origin and a complete candidate SHA')
    require(candidate_source != SOURCE, 'Recovery needs its own candidate source')
    subprocess.run(['git', 'merge-base', '--is-ancestor', SOURCE, candidate_source], cwd=ROOT, check=True)
    old_tree, new_tree = tracked_tree(SOURCE), tracked_tree(candidate_source)
    changed = validate_tree_delta(old_tree, new_tree)
    before_workflow = source_bytes(SOURCE, WORKFLOW).decode()
    after_workflow = source_bytes(candidate_source, WORKFLOW).decode()
    require(after_workflow == expected_reuse_workflow(before_workflow),
            'Workflow producer recipe, tools, inherited context or explicit reuse gate changed')
    projections = {
        PRODUCERS: verify_python(source_bytes(SOURCE, PRODUCERS), source_bytes(candidate_source, PRODUCERS),
                                 {'origin', 'tests', 'native'}, {'validate_armsx2_shaders'}),
        DELIVERY: verify_python(source_bytes(SOURCE, DELIVERY), source_bytes(candidate_source, DELIVERY),
                                {'contract', 'expected'}),
    }
    old_scope_raw = source_bytes(SOURCE, tree.CONFIG)
    current_scope_raw = source_bytes(candidate_source, tree.CONFIG)
    require(sha(old_scope_raw) == ORIGINAL_SCOPE, 'Original test scope differs')
    old_scope, current_scope = json.loads(old_scope_raw), json.loads(current_scope_raw)
    for key in ('schema', 'build', 'baseline', 'productDelta', 'declarationsSHA256',
                'nativeInventorySHA256', 'publicKeySHA256', 'scopeGeneratedInCI', 'physicalDeviceTested'):
        require(old_scope[key] == current_scope[key], 'Reviewed product/dependency scope changed: ' + key)
    return dict(schema=1, originSource=SOURCE, candidateSource=candidate_source,
        originTree=tree.git('rev-parse', SOURCE + '^{tree}'),
        candidateTree=tree.git('rev-parse', candidate_source + '^{tree}'),
        originalSourceScopeSHA256=ORIGINAL_SCOPE, candidateSourceScopeSHA256=sha(current_scope_raw),
        unchangedTrackedEntries=len(old_tree.keys() & new_tree.keys()) - len([p for p in changed if p in old_tree]),
        changedRecipePaths={p: dict(before=old_tree.get(p), after=new_tree.get(p)) for p in changed},
        producerCodeProjectionSHA256=projections,
        originalWorkflowSHA256=sha(before_workflow.encode()), candidateWorkflowSHA256=sha(after_workflow.encode()),
        producerStepsAndInheritedContextIdentical=True,
        originalWholeInputHashesMayDifferForReviewedRecipeFiles=True,
        affectedChecks=[name for name, _ in COMMANDS])


@lru_cache(maxsize=1)
def authenticate_original():
    run = producers.api('actions/runs/' + str(ORIGINAL['run']))
    require(run['id'] == ORIGINAL['run'] and run['head_sha'] == SOURCE and run['head_branch'] == 'Claude' and
        run['path'] == WORKFLOW and run['run_attempt'] == 1 and run['status'] == 'completed' and
        run['conclusion'] == 'failure' and run['event'] in ('push', 'workflow_dispatch'),
        'Original whole run must retain its actual completed failure')
    jobs = producers.api(f"actions/runs/{ORIGINAL['run']}/attempts/1/jobs?per_page=100")
    require(jobs['total_count'] == len(jobs['jobs']) and jobs['total_count'] <= 100, 'Unexpected origin job pagination')
    by_id = {job['id']: job for job in jobs['jobs']}
    require(len(by_id) == len(jobs['jobs']), 'Duplicated original job')
    for job_id, conclusion in ((124808921278, 'success'), (124814980616, 'failure')):
        job = by_id[job_id]
        require(job['head_sha'] == SOURCE and job['run_id'] == ORIGINAL['run'] and
                job['run_attempt'] == 1 and job['status'] == 'completed' and job['conclusion'] == conclusion,
                'Original preflight/application status changed')
    app_steps = by_id[124814980616]['steps']
    require(any(step['name'] == 'Compile Release device binary with measured AOT and Xcode phases' and
                step['conclusion'] == 'skipped' for step in app_steps),
            'The pinned application failure was not the reviewed prebuild consumer failure')
    result = {}
    for kind, pin in PINS.items():
        matching = [job for job in jobs['jobs'] if job['name'] == producers.JOBS[kind]]
        require(len(matching) == 1 and matching[0]['id'] == pin['job'], 'Wrong original prerequisite job')
        job = matching[0]
        require(job['head_sha'] == SOURCE and job['run_id'] == ORIGINAL['run'] and job['run_attempt'] == 1 and
                job['status'] == 'completed' and job['conclusion'] == 'success', 'Original prerequisite did not pass')
        successful = {step['name'] for step in job['steps'] if step['conclusion'] == 'success'}
        require(producers.REQUIRED_STEPS[kind] <= successful, 'Original prerequisite omitted required execution')
        artifact = producers.api('actions/artifacts/' + str(pin['artifact']))
        name = f'RewindBox608-{kind}-{SOURCE}-attempt1'
        require(artifact['id'] == pin['artifact'] and artifact['name'] == name and not artifact['expired'] and
                artifact['size_in_bytes'] == pin['archiveBytes'] and artifact['digest'] == 'sha256:' + pin['archiveSHA256'] and
                artifact['workflow_run']['id'] == ORIGINAL['run'] and artifact['workflow_run']['head_sha'] == SOURCE,
                'Original prerequisite archive ID/digest/size/source changed or expired')
        result[kind] = dict(result='authenticated', evidenceMode='reused', kind=kind, execution=ORIGINAL.copy(),
            **pin, artifactName=name, originalRunConclusion='failure', originalJobConclusion='success')
    return result


def guard_input_hashes():
    return {p: sha((ROOT / p).read_bytes()) for p in sorted(ALLOWED_RECIPE_PATHS)}


def prepare():
    require(enabled(), 'Explicit reuse selection is required')
    tree.verify()
    current = producers.execution()
    proof = dict(schema=1, build=608, result='running', evidenceMode='reused',
        candidateExecution=current, originalExecution=ORIGINAL.copy(), originalRunConclusion='failure',
        inputEquivalence=input_equivalence(SOURCE, current['source']), originalOrigins=authenticate_original(),
        currentGuardInputs=guard_input_hashes(), affectedChecks=[], unchangedSuitesReexecuted=False,
        coresRebuilt=False, physicalDeviceTested=False)
    directory = ROOT / 'build/validation608/reuse'
    require(not directory.exists(), 'Refusing to overwrite reuse evidence')
    directory.mkdir(parents=True)
    first_failure = 0
    for name, argv in COMMANDS:
        environment = dict(os.environ, REWIND608_REUSE='')
        start = time.monotonic()
        log = directory / (name + '.log')
        with log.open('wb') as output:
            try:
                completed = subprocess.run(argv, cwd=ROOT, env=environment, stdout=output,
                    stderr=subprocess.STDOUT, timeout=300)
                code = completed.returncode
            except subprocess.TimeoutExpired:
                code = 124
        raw = log.read_bytes()
        print(raw.decode(errors='replace'), flush=True)
        proof['affectedChecks'].append(dict(name=name, argv=list(argv), exitCode=code,
            seconds=round(time.monotonic() - start, 3), log=log.name, logSHA256=sha(raw)))
        first_failure = first_failure or code
    require(not tree.git('diff', '--name-only') and tree.git('write-tree') == current['tree'],
            'Recovery checks changed a tracked input')
    proof['result'] = 'failed' if first_failure else 'passed'
    producers.save(directory / 'validation.json', proof)
    if first_failure:
        raise SystemExit(first_failure)
    with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
        for kind, pin in PINS.items():
            print(f"{kind}-artifact-id={pin['artifact']}", file=output)
            print(f"{kind}-artifact-digest={pin['archiveSHA256']}", file=output)
    return proof


def _guard_archive(value):
    directory = ROOT / 'build/components608/reuse'
    archive_path = directory.with_suffix('.zip')
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    if not archive_path.is_file() or archive_path.stat().st_size != value['archiveBytes'] or sha(archive_path.read_bytes()) != value['archiveSHA256']:
        temporary = archive_path.with_suffix('.part')
        with temporary.open('wb') as output:
            subprocess.run(['gh', 'api', f"repos/TarbleFR/RewindBox/actions/artifacts/{value['artifact']}/zip"],
                cwd=ROOT, stdout=output, check=True, timeout=120)
        require(temporary.stat().st_size == value['archiveBytes'] and sha(temporary.read_bytes()) == value['archiveSHA256'],
                'Current recovery proof archive bytes differ')
        temporary.replace(archive_path)
    from rewind606_engine import safe_members
    with zipfile.ZipFile(archive_path) as archive:
        safe_members(archive)
        expected = {'validation.json'} | {name + '.log' for name, _ in COMMANDS}
        require(set(archive.namelist()) == expected and len(archive.namelist()) == len(expected),
                'Unexpected recovery proof member inventory')
        directory.mkdir(parents=True, exist_ok=True)
        archive.extractall(directory)
    return directory


def require_same(actual, expected, path):
    """Fail on the exact field, without printing receipt contents."""
    require(type(actual) is type(expected), 'Recovery receipt type differs: ' + path)
    if isinstance(expected, dict):
        require(actual.keys() == expected.keys(), 'Recovery receipt fields differ: ' + path)
        for key in sorted(expected):
            require_same(actual[key], expected[key], path + '.' + str(key))
    elif isinstance(expected, list):
        require(len(actual) == len(expected), 'Recovery receipt length differs: ' + path)
        for index, (item, wanted) in enumerate(zip(actual, expected)):
            require_same(item, wanted, path + '[' + str(index) + ']')
    else:
        require(actual == expected, 'Recovery receipt value differs: ' + path)


def validate_guard(value, current, equivalence, originals, directory):
    expected = dict(schema=1, build=608, result='passed', evidenceMode='reused',
        candidateExecution=current, originalExecution=ORIGINAL, originalRunConclusion='failure',
        inputEquivalence=equivalence, originalOrigins=originals, currentGuardInputs=guard_input_hashes(),
        unchangedSuitesReexecuted=False, coresRebuilt=False, physicalDeviceTested=False)
    require(isinstance(value, dict), 'Current recovery receipt is not an object')
    for field, wanted in expected.items():
        require(field in value, 'Recovery receipt field missing: ' + field)
        require_same(value[field], wanted, field)
    require(len(value['affectedChecks']) == len(COMMANDS), 'An affected recipe test was omitted')
    for command, (name, argv) in zip(value['affectedChecks'], COMMANDS):
        require(command['name'] == name and command['argv'] == list(argv) and command['exitCode'] == 0 and
            command['log'] == name + '.log' and sha((directory / command['log']).read_bytes()) == command['logSHA256'],
            'Affected recipe contract did not pass with its original log')
    return value


@lru_cache(maxsize=1)
def verified_guard():
    require(enabled(), 'Recovery proof requires explicit selected origin')
    current = producers.execution()
    run = producers.api('actions/runs/' + str(current['run']))
    require(run['id'] == current['run'] and run['head_sha'] == current['source'] and
            run['head_branch'] == 'Claude' and run['path'] == WORKFLOW and
            run['run_attempt'] == current['attempt'] and run['event'] in ('push', 'workflow_dispatch'),
            'Wrong explicitly selected recovery run')
    if run['event'] == 'push':
        message = git_bytes('show', '-s', '--format=%B', current['source']).decode()
        require(PUSH_MARKER in message and '[rewind608-delivery]' in message,
                'Push recovery requires both explicit delivery and0279198 reuse commit markers')
    jobs = producers.api(f"actions/runs/{current['run']}/attempts/{current['attempt']}/jobs?per_page=100")
    require(jobs['total_count'] == len(jobs['jobs']) and jobs['total_count'] <= 100, 'Unexpected current job pagination')
    require(len({item['id'] for item in jobs['jobs']}) == len(jobs['jobs']), 'Duplicated current job ID')
    preflights = [item for item in jobs['jobs'] if item['name'] == PREFLIGHT_JOB_NAME]
    require(len(preflights) == 1, 'Missing or duplicated current preflight')
    preflight = preflights[0]
    require(preflight['head_sha'] == current['source'] and preflight['run_id'] == current['run'] and
        preflight['run_attempt'] == current['attempt'] and preflight['status'] == 'completed' and
        preflight['conclusion'] == 'success' and
        PREFLIGHT_STEP in {s['name'] for s in preflight['steps'] if s['conclusion'] == 'success'},
        'Current preflight did not authenticate the retained inputs')
    matches = [job for job in jobs['jobs'] if job['name'] == CURRENT_JOB_NAME]
    require(len(matches) == 1, 'Missing or duplicated current recovery job')
    job = matches[0]
    require(job['head_sha'] == current['source'] and job['run_id'] == current['run'] and
        job['run_attempt'] == current['attempt'] and job['status'] == 'completed' and job['conclusion'] == 'success' and
        {CURRENT_STEP, CURRENT_UPLOAD} <= {s['name'] for s in job['steps'] if s['conclusion'] == 'success'},
        'Current recovery guard did not succeed')
    for kind in PINS:
        selected = [item for item in jobs['jobs'] if item['name'] == producers.JOBS[kind]]
        require(len(selected) == 1 and selected[0]['head_sha'] == current['source'] and
                selected[0]['run_id'] == current['run'] and selected[0]['run_attempt'] == current['attempt'] and
                selected[0]['status'] == 'completed' and selected[0]['conclusion'] == 'skipped',
                'Mixed fresh/reused prerequisite jobs are forbidden')
    artifact_id = int(os.environ['REUSE_ARTIFACT_ID'])
    digest = os.environ['REUSE_ARTIFACT_DIGEST'].removeprefix('sha256:')
    require(re.fullmatch('[0-9a-f]{64}', digest), 'Missing current recovery upload digest')
    artifact = producers.api('actions/artifacts/' + str(artifact_id))
    name = f"RewindBox608-reuse-{current['source']}-attempt{current['attempt']}"
    require(artifact['id'] == artifact_id and artifact['name'] == name and not artifact['expired'] and
        artifact['digest'] == 'sha256:' + digest and artifact['workflow_run']['id'] == current['run'] and
        artifact['workflow_run']['head_sha'] == current['source'], 'Wrong current recovery proof artifact')
    metadata = dict(artifact=artifact_id, artifactName=name, archiveSHA256=digest,
                    archiveBytes=artifact['size_in_bytes'], job=job['id'], execution=current)
    directory = _guard_archive(metadata)
    receipt = validate_guard(json.loads((directory / 'validation.json').read_bytes()), current,
        input_equivalence(SOURCE, current['source']), authenticate_original(), directory)
    return dict(metadata, receipt=receipt)


def origin(kind):
    require(kind in PINS, 'Unknown explicit reuse kind')
    guard = verified_guard()
    value = authenticate_original()[kind]
    require(int(os.environ[kind.upper() + '_ARTIFACT_ID']) == value['artifact'] and
            os.environ[kind.upper() + '_ARTIFACT_DIGEST'].removeprefix('sha256:') == value['archiveSHA256'],
            'Selected archive outputs differ from the explicit origin')
    return dict(value, reuseProof=dict(job=guard['job'], artifact=guard['artifact'],
                                      archiveSHA256=guard['archiveSHA256'], execution=guard['execution']))


def original_input_hashes(kind):
    return {name: sha(source_bytes(SOURCE, name)) for name in producers.input_paths(kind)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['prepare', 'verify'])
    args = parser.parse_args()
    print(json.dumps(prepare() if args.operation == 'prepare' else verified_guard(), indent=2))
