#!/usr/bin/env python3
"""Static contract of the RPCS3 Core producer route (spec, gate, runner, recipe patch, workflow).

The route builds the Core declared in build-utils/rpcs3/core-build.json (Core
611: the delivered Core 610 plus only the folded RetroAchievements record). Run
before requesting the Apple build: every declared value must agree with the
committed canonical delta, with the delivered reference Core's committed
evidence and its independent records (run receipt, delivery scope, delivery
consumer, the a4ae86d0 recovery pins), the recipe may differ from the delivered
recipe only by the gate it calls and must equal the recipe the reference
executed, and the workflow must build only the Core (no IPA, no release) on the
declared markers. With --source, the gate's host-side source closure also runs
on a materialized tree; with --baseline and --reused-reference as well, the
Apple reuse authentication runs offline on a downloaded reference artifact.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile

import yaml

ROOT = Path(__file__).resolve().parents[1]
DIAG = ROOT / '.github/diagnostics'
sys.path.insert(0, str(DIAG))
STEP_VALUE = re.compile(r'\$\{\{\s*steps\.core-build\.outputs\.([a-z_]+)\s*\}\}')


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def rendered(name: str, values: dict) -> str:
    return STEP_VALUE.sub(lambda match: str(values[match.group(1)]), name)


def check(source: Path | None, baseline: Path | None = None, reused_reference: Path | None = None) -> dict:
    gate = load('rpcs3_core610', DIAG / 'rpcs3_core610.py')
    spec = gate.SPEC
    reference = spec['reference']
    runner = load('build_rpcs3_core610', ROOT / spec['route']['driver'])
    delivered_runner = load('build_rpcs3_mvk_cache_core', ROOT / 'build-utils/rpcs3/build_rpcs3_mvk_cache_core.py')
    recovered = load('rpcs3runtime607_core', DIAG / 'rpcs3runtime607_core.py')
    consumer = load('rpcs3core610_delivery', DIAG / 'rpcs3core610_delivery.py')
    base = load('rpcs3_mvk_cache_core', DIAG / 'rpcs3_mvk_cache_core.py')
    dependency = load('rpcs3_mvk_dependency_artifact', DIAG / 'rpcs3_mvk_dependency_artifact.py')
    manifest = json.loads((ROOT / 'build-utils/rpcs3/canonical-source.json').read_bytes())
    staged = json.loads((ROOT / spec['delta']['manifest']).read_bytes())
    # The spec drives the gate and the Apple harness module: no per-build value is one of their literals.
    for path in (DIAG / 'rpcs3_core610.py', DIAG / 'rpcs3_core_apple_host.py'):
        code = path.read_text().split('"""', 2)[2]
        for route_name in ('rpcs3_core610', 'rpcs3-core610', 'core610-recipe', 'core610-proof'):
            code = code.replace(route_name, '')
        for value in (gate.BUILD, gate.REFERENCE_BUILD):
            assert not re.search(rf'(?<![0-9A-Za-z]){value}(?![0-9A-Za-z])', code), (path.name, value)
        for value in (gate.PATCH_SHA, gate.DELIVERED_SOURCE, gate.DELIVERED_IDENTITY_SHA, gate.HOST_SHA, gate.CORE_TYPE,
                      *gate.CODEGEN.values(), *gate.RUNTIME_MARKERS, reference['apple_host_tests_artifact']['sha256'],
                      str(reference['run']), str(spec['moltenvk_dependency']['run']), spec['apple_host_tests']['baseline']['source']):
            assert value not in code, (path.name, value)
    assert gate.load_spec() == spec and spec['route']['gate'] == '.github/diagnostics/rpcs3_core610.py'
    # The spec is validated: malformed or inconsistent declarations are refused.
    with tempfile.TemporaryDirectory(prefix='rpcs3-core-spec-') as temp:
        mutations = {
            'identity type without the build': lambda s: s.update(identity_type='rpcs3-ios-core' + str(s['reference']['build'])),
            'a retired marker reactivated': lambda s: s['route']['markers'].update(core_and_apple=s['route']['retired_markers'][0]),
            'another route gate': lambda s: s['route'].update(gate='.github/diagnostics/rpcs3_core611.py'),
            'a reference Apple result neither reused nor rerun': lambda s: s['apple_host_tests'].update(
                rerun=[i for i in s['apple_host_tests']['rerun'] if i['name'] != 'transition-phases']),
            'a rerun command also declared reused': lambda s: s['apple_host_tests']['reused']['reused_commands'][
                'reuse-audit'].pop('rerun_by_this_build'),
            'a reused mode count not two per harness': lambda s: s['native_modes'].update(reused_count=7),
            'an unsorted reviewed drift': lambda s: s['core_inputs']['reviewed_drift'].reverse(),
            'a reference later than the build': lambda s: s['reference'].update(build=s['build'] + 1),
            'a malformed canonical digest': lambda s: s['canonical'].update(patch_sha256='a63b9643'),
        }
        for label, mutate in mutations.items():
            broken = json.loads(json.dumps(spec))
            mutate(broken)
            path = Path(temp) / 'core-build.json'
            path.write_text(json.dumps(broken))
            try:
                gate.load_spec(path)
            except (ValueError, KeyError):
                continue
            raise AssertionError('malformed core build spec accepted: ' + label)
    # Canonical delta: the declared build, exactly the reference plus the folded record.
    assert gate.PATCH_SHA == manifest['patch_sha256'] == sha((ROOT / 'build-utils/rpcs3/embedded-core.patch').read_bytes())
    assert gate.POSTIMAGES == len(manifest['files_sha256']) and all(record in manifest for record in gate.RECORDS)
    assert gate.UPSTREAM == manifest['upstream_commit'] == base.UPSTREAM
    assert manifest[spec['delta']['record']] == staged and staged['folded_into_canonical_delta'] is True
    assert staged['patch_sha256'] == spec['delta']['patch_sha256'] == sha((ROOT / staged['patch']).read_bytes())
    assert spec['exports'] == reference['exports'] + len(staged['exports_added'])
    assert gate.POSTIMAGES == reference['postimages'] + len(staged['new_files'])
    # The Core-input pin (written by the fold) and the Core-input scope agree with the spec.
    pin = load('neo_swap_core_pin_test', ROOT / 'test/neo_swap_core_pin_test.py')
    assert pin.PATCH_SHA256 == gate.PATCH_SHA and pin.UPSTREAM == gate.UPSTREAM
    assert len(set(pin.CORE_INPUTS)) == spec['core_inputs']['count'] and gate.REVIEWED_CORE_INPUT_DRIFT <= set(pin.CORE_INPUTS)
    # Reference: the delivered Core, bound by digest and checked against independent records.
    identity, proof = gate.delivered()
    receipt = json.loads((gate.DELIVERED / reference['run_receipt']).read_bytes())
    assert identity['sha256'] == receipt['core']['sha256'] == reference['core']['sha256']
    assert receipt['run'] == reference['run'] and receipt['artifact'] == reference['artifact']
    scope = json.loads((ROOT / reference['delivery_scope']).read_bytes())['sourceDelta']
    for name, digest in ((reference['identity'], gate.DELIVERED_IDENTITY_SHA), (reference['proof'], gate.DELIVERED_PROOF_SHA),
                         (reference['run_receipt'], reference['run_receipt_sha256'])):
        assert scope[f"{reference['evidence']}/{name}"]['after'] == digest, name
    assert identity['delivered_reference']['source'] == recovered.CORE_SOURCE == spec['apple_host_tests']['baseline']['source']
    assert (identity['delivered_reference']['identity_sha256'], identity['delivered_reference']['proof_sha256']) == (
        recovered.IDENTITY_SHA256, recovered.PROOF_SHA256)
    assert spec['apple_host_tests']['baseline']['canonical_patch_sha256'] == base.PATCH_SHA
    assert {name for name, item in identity['reused_native_modes'].items()
            if item['reused_from_delivered'] == recovered.CORE_SOURCE} == set(identity['reused_native_modes'])
    assert gate.NEW_CANONICAL_UPSTREAM <= set(manifest['files_sha256'])
    assert gate.NEW_CANONICAL_UPSTREAM <= set(proof['source_closure']['upstream_dependencies']['files_sha256'])
    # Host bridge: the Core-input drift starts from the reference's bridge, and the declared host is the current one.
    assert identity['core_input_sha256'][gate.HOST] == dependency.HOST_BEFORE
    assert sha((ROOT / gate.HOST).read_bytes()) == gate.HOST_SHA
    declared = spec['moltenvk_dependency']
    linked = identity['moltenvk_dependency']
    if 'replaces' in declared:
        # A replaced dependency: its own run recorded the current bridge (no reviewed pair), and it replaces exactly the
        # dependency the reference Core linked.
        assert declared['reviewed_host_delta'] is False and declared['run'] != linked['run']
        assert {k: declared['replaces'][k] for k in ('run', 'source', 'library_sha256')} == {
            k: linked[k] for k in ('run', 'source', 'library_sha256')}
    else:
        # The reference's dependency: the Core-input drift and the MoltenVK reviewed delta are the same pair.
        assert gate.HOST_SHA == dependency.HOST_AFTER and declared['reviewed_host_delta'] is True
        assert declared['run'] == linked['run'] and declared['source'] == linked['source']
        assert declared['library_sha256'] == linked['library_sha256']
    # The delivery consumer pins either this build's reference (until it is built) or this build.
    consumer_build = int(consumer.CORE_TYPE.removeprefix('rpcs3-ios-core'))
    assert consumer_build in (gate.REFERENCE_BUILD, gate.BUILD), consumer.CORE_TYPE
    if consumer_build == gate.REFERENCE_BUILD:
        assert consumer.PIN == dict(source=reference['source'], run=reference['run'], attempt=reference['attempt'],
                                    job=reference['core_job'], artifact=reference['artifact']['id'],
                                    name=reference['artifact']['name'], bytes=reference['artifact']['bytes'],
                                    sha256=reference['artifact']['sha256'], core_sha256=reference['core']['sha256'],
                                    core_bytes=reference['core']['bytes'], identity_sha256=gate.DELIVERED_IDENTITY_SHA)
        tests = reference['apple_host_tests_artifact']
        assert consumer.HOST_TESTS == dict(source=reference['source'], run=reference['run'], attempt=reference['attempt'],
                                           job=reference['apple_host_test_job'], artifact=tests['id'], name=tests['name'],
                                           bytes=tests['bytes'], sha256=tests['sha256'])
        assert consumer.PATCH_SHA == gate.DELIVERED_PATCH_SHA and consumer.CODEGEN == gate.CODEGEN
        assert consumer.HOST_SHA256 == identity['core_input_sha256'][gate.HOST]
        assert consumer.HOST_TEST_STEPS == set(spec['apple_host_tests']['reused']['steps'])
        assert list(consumer.HOST_TEST_NAMES) == spec['apple_host_tests']['reused']['commands']
    # Recipe: the delivered patch with only the gate path replaced, executed by the reference too.
    old = (ROOT / 'build-utils/rpcs3/patches/mvk-cache-core-recipe.patch').read_text()
    new = (ROOT / spec['route']['recipe_patch']).read_text()
    assert new == old.replace('.github/diagnostics/rpcs3_mvk_cache_core.py', spec['route']['gate'])
    assert old.count('rpcs3_mvk_cache_core.py') == 2 and 'rpcs3_mvk_cache_core' not in new
    assert runner.BEFORE == delivered_runner.BEFORE and runner.PATCH_SHA == sha(new.encode())
    assert sha(runner.recipe_bytes()) == runner.AFTER != delivered_runner.AFTER
    assert identity['build_recipe'] == {'original_recipe_sha256': runner.BEFORE, 'recipe_patch_sha256': runner.PATCH_SHA,
                                        'candidate_recipe_sha256': runner.AFTER, 'frozen_recipe_modified': False}
    runner_text = (ROOT / spec['route']['driver']).read_text()
    assert spec['route']['gate'] in runner_text and 'rpcs3_mvk_cache_core.py' in runner_text.split('"""')[1]
    # Every gate input exists; the spec, workflow, runner and recipe are bound.
    for name in gate.INPUTS:
        assert (ROOT / name).is_file(), name
    for name in (gate.WORKFLOW, spec['route']['driver'], spec['route']['recipe_patch'], 'build-utils/rpcs3/core-build.json',
                 '.github/diagnostics/rpcs3_core_apple_host.py', spec['delta']['manifest'], spec['delta']['patch']):
        assert name in gate.INPUTS, name
    # Workflow: Core-only, gated by the declared markers, exact gate/runner calls and artifacts.
    text = (ROOT / gate.WORKFLOW).read_text()
    workflow = yaml.safe_load(text)
    trigger = workflow.get('on', workflow.get(True))
    assert trigger['push']['branches'] == ['Claude'] and trigger['push']['paths'] == [gate.WORKFLOW]
    assert set(workflow['jobs']) == {'core'}
    markers = spec['route']['markers']
    core_marker = f"contains(github.event.head_commit.message, '{markers['core_and_apple']}')"
    apple_marker = f"contains(github.event.head_commit.message, '{markers['apple_only']}')"
    for job in workflow['jobs'].values():
        assert core_marker in job['if'], job['if']
    assert apple_marker not in workflow['jobs']['core']['if']
    for retired in spec['route']['retired_markers']:
        assert retired not in text, retired
    assert 'RPCS3_MVK_DEPENDENCY_RUN' not in workflow['env'] and 'RPCS3_DELIVERED_CORE_SOURCE' not in workflow['env']
    for job in workflow['jobs'].values():
        steps = [step.get('id') for step in job['steps']]
        assert 'core-build' in steps and job['steps'][steps.index('core-build')]['run'].count('--github-outputs') == 1
    # The route passes the declared dependency (the reference's, or its declared replacement) to the authenticating step.
    assert gate.github_outputs()['dependency_run'] == spec['moltenvk_dependency']['run']
    assert gate.github_outputs()['dependency_source'] == spec['moltenvk_dependency']['source']
    assert gate.github_outputs()['apple_baseline_source'] == recovered.CORE_SOURCE
    authenticate = next(step for step in workflow['jobs']['core']['steps'] if 'rpcs3_core610.py \\\n' in step.get('run', '')
                        and '--prepare' in step['run'])
    assert authenticate['env']['RPCS3_MVK_DEPENDENCY_RUN'] == '${{ steps.core-build.outputs.dependency_run }}'
    assert authenticate['env']['RPCS3_MVK_DEPENDENCY_SOURCE'] == '${{ steps.core-build.outputs.dependency_source }}'
    for needle in ('rpcs3_core610.py \\\n              --prepare', 'build_rpcs3_core610.py', '--write-core-identity',
                   'name: RPCS3Core-${{ steps.core-build.outputs.build }}-${{ github.sha }}', 'core610-proof.json'):
        assert needle in text, needle
    assert 'rpcs3_core_apple_host.py --run' not in text
    plan = gate.apple_host_test_plan()
    assert plan['validation_mode'] == 'build-only' and plan['full_regression_suite_executed'] is False
    assert plan['executed_in_core_job'] == 0 and set(plan['deferred']) == {i['name'] for i in spec['apple_host_tests']['rerun']}
    for forbidden in ('flutter build', 'xcodebuild -exportArchive', 'gh release', 'softprops/action-gh-release',
                      'delivery_cipher', '.ipa', 'RPCS3Core-610', 'RPCS3Core-611'):
        assert forbidden not in text, forbidden
    # Step names carry the declared build; the consumer's pinned names are their instance for its build.
    values = dict(gate.github_outputs(), build=consumer_build)
    core_steps = {rendered(step['name'], values) for step in workflow['jobs']['core']['steps']}
    assert consumer.CORE_STEPS <= core_steps, sorted(consumer.CORE_STEPS - core_steps)
    # Apple harnesses: the rerun commands and the reused harnesses exist; nothing of the reference is dropped.
    apple = spec['apple_host_tests']
    for item in apple['rerun']:
        assert (ROOT / item['argv'][1]).is_file(), item['name']
    for name, item in apple['reused']['reused_commands'].items():
        for path in item['repo_inputs']:
            assert (ROOT / path).is_file(), path
        assert (ROOT / apple['reused']['evidence'] / (name + '.json')).is_file(), name
    assert set(apple['reused']['commands']) <= set(apple['reused']['reused_commands']) | {i['name'] for i in apple['rerun']}
    result = {'build': gate.BUILD, 'reference_build': gate.REFERENCE_BUILD, 'patch_sha256': gate.PATCH_SHA,
              'postimages': gate.POSTIMAGES, 'exports': spec['exports'], 'recipe_sha256': runner.AFTER,
              'recipe_patch_sha256': runner.PATCH_SHA, 'delivered_reference': gate.DELIVERED_SOURCE,
              'consumer_pins_build': consumer_build, 'gate_inputs': len(gate.INPUTS),
              'spec_sha256': sha((ROOT / 'build-utils/rpcs3/core-build.json').read_bytes()),
              'workflow_sha256': sha(text.encode()),
              'validation_mode': 'build-only', 'apple_deferred': [item['name'] for item in apple['rerun']],
              'apple_reused': sorted(n for n, i in apple['reused']['reused_commands'].items() if not i.get('rerun_by_this_build'))}
    if source:
        closure = gate.source_closure(source.resolve())
        result['source_closure'] = {'reviewed_core_input_drift': sorted(closure['reviewed_core_input_drift']),
                                    'upstream_files': len(closure['upstream_dependencies']['files_sha256']),
                                    'exports': len(closure['exported_symbols']),
                                    'exports_added': closure['exports_added']}
        result['reused_native_modes'] = sorted(gate.reused_modes(identity, source.resolve()))
        if baseline and reused_reference:
            apple_host = load('rpcs3_core_apple_host', DIAG / 'rpcs3_core_apple_host.py')
            with tempfile.TemporaryDirectory(prefix='rpcs3-core-route-') as temp:
                out = Path(temp) / 'apple'
                shutil.copytree(reused_reference, out / 'reused-reference')
                summary = apple_host.authenticate_reused(source, baseline, out, download=False)
            result['apple_reused_authenticated'] = sorted(summary['commands'])
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, help='materialized tree of the declared Core build (optional)')
    parser.add_argument('--baseline', type=Path, help='materialized delivered a4ae86d0 tree (optional, with --source)')
    parser.add_argument('--reused-reference', type=Path,
                        help='directory with job.json, run.json, artifact.json and apple-host-tests.zip of the reference')
    args = parser.parse_args()
    print(json.dumps(check(args.source, args.baseline, args.reused_reference), indent=2))
    print('PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
