#!/usr/bin/env python3
"""Static contract of the Core 610 producer route (gate, runner, recipe patch, workflow).

Run before requesting the Apple build: every pin must agree with the committed
canonical delta and the delivered a4ae86d0 reference, the recipe may differ from
the delivered recipe only by the gate it calls, and the workflow must build only
the Core (no IPA, no release). With --source, the gate's host-side source
closure also runs on a materialized Core 610 tree.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
DIAG = ROOT / '.github/diagnostics'
sys.path.insert(0, str(DIAG))


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def check(source: Path | None) -> dict:
    gate = load('rpcs3_core610', DIAG / 'rpcs3_core610.py')
    runner = load('build_rpcs3_core610', ROOT / 'build-utils/rpcs3/build_rpcs3_core610.py')
    delivered_runner = load('build_rpcs3_mvk_cache_core', ROOT / 'build-utils/rpcs3/build_rpcs3_mvk_cache_core.py')
    recovered = load('rpcs3runtime607_core', DIAG / 'rpcs3runtime607_core.py')
    manifest = json.loads((ROOT / 'build-utils/rpcs3/canonical-source.json').read_bytes())
    assert gate.PATCH_SHA == manifest['patch_sha256'] == sha((ROOT / 'build-utils/rpcs3/embedded-core.patch').read_bytes())
    assert gate.POSTIMAGES == len(manifest['files_sha256']) and gate.RECORD in manifest
    assert gate.UPSTREAM == manifest['upstream_commit']
    assert gate.DELIVERED_SOURCE == recovered.CORE_SOURCE
    assert gate.DELIVERED_IDENTITY_SHA == recovered.IDENTITY_SHA256 and gate.DELIVERED_PROOF_SHA == recovered.PROOF_SHA256
    identity, proof = gate.delivered()
    assert identity['sha256'] == recovered.CORE_SHA256
    assert gate.NEW_CANONICAL_UPSTREAM <= set(manifest['files_sha256'])
    assert gate.NEW_CANONICAL_UPSTREAM <= set(proof['source_closure']['upstream_dependencies']['files_sha256'])
    # Recipe: the delivered patch with only the gate path replaced.
    old = (ROOT / 'build-utils/rpcs3/patches/mvk-cache-core-recipe.patch').read_text()
    new = (ROOT / 'build-utils/rpcs3/patches/core610-recipe.patch').read_text()
    assert new == old.replace('.github/diagnostics/rpcs3_mvk_cache_core.py', '.github/diagnostics/rpcs3_core610.py')
    assert old.count('rpcs3_mvk_cache_core.py') == 2 and 'rpcs3_mvk_cache_core' not in new
    assert runner.BEFORE == delivered_runner.BEFORE and runner.PATCH_SHA == sha(new.encode())
    assert sha(runner.recipe_bytes()) == runner.AFTER != delivered_runner.AFTER
    runner_text = (ROOT / 'build-utils/rpcs3/build_rpcs3_core610.py').read_text()
    assert '.github/diagnostics/rpcs3_core610.py' in runner_text and 'rpcs3_mvk_cache_core.py' in runner_text.split('"""')[1]
    # Every gate input exists; the workflow, runner and recipe are bound.
    for name in gate.INPUTS:
        assert (ROOT / name).is_file(), name
    for name in (gate.WORKFLOW, 'build-utils/rpcs3/build_rpcs3_core610.py', 'build-utils/rpcs3/patches/core610-recipe.patch'):
        assert name in gate.INPUTS, name
    # Workflow: Core-only, gated by marker, exact gate/runner calls and artifacts.
    text = (ROOT / gate.WORKFLOW).read_text()
    workflow = yaml.safe_load(text)
    trigger = workflow.get('on', workflow.get(True))
    assert trigger['push']['branches'] == ['Claude'] and trigger['push']['paths'] == [gate.WORKFLOW]
    assert set(workflow['jobs']) == {'core', 'apple-host-tests'}
    for job in workflow['jobs'].values():
        assert "contains(github.event.head_commit.message, '[rpcs3-core610]')" in job['if']
    assert workflow['env']['RPCS3_MVK_DEPENDENCY_RUN'] == '41239096061'
    assert workflow['env']['RPCS3_DELIVERED_CORE_SOURCE'] == gate.DELIVERED_SOURCE
    for needle in ('rpcs3_core610.py \\\n              --prepare', 'build_rpcs3_core610.py', '--write-core-identity',
                   'name: RPCS3Core-610-${{ github.sha }}', 'core610-proof.json'):
        assert needle in text, needle
    for forbidden in ('flutter build', 'xcodebuild -exportArchive', 'gh release', 'softprops/action-gh-release',
                      'delivery_cipher', '.ipa'):
        assert forbidden not in text, forbidden
    tests = [step for step in workflow['jobs']['apple-host-tests']['steps'] if 'run' in step][-1]['run']
    for name in ('rpcs3_spu_mfc_lr_test.py', 'rpcs3_exitspawn_worker610_test.py', 'rpcs3_feedback_census_test.py',
                 'rpcs3_transition_phases_test.py', 'rpcs3_core610_codegen_test.py', 'rpcs3_core610_reuse_audit_test.py',
                 'rpcs3_position_invariance_test.py'):
        assert name in tests and (ROOT / 'test' / name).is_file(), name
    result = {'patch_sha256': gate.PATCH_SHA, 'postimages': gate.POSTIMAGES, 'recipe_sha256': runner.AFTER,
              'recipe_patch_sha256': runner.PATCH_SHA, 'delivered_reference': gate.DELIVERED_SOURCE,
              'gate_inputs': len(gate.INPUTS), 'workflow_sha256': sha(text.encode())}
    if source:
        closure = gate.source_closure(source.resolve())
        result['source_closure'] = {'reviewed_core_input_drift': sorted(closure['reviewed_core_input_drift']),
                                    'upstream_files': len(closure['upstream_dependencies']['files_sha256']),
                                    'exports': len(closure['exported_symbols'])}
        result['reused_native_modes'] = sorted(gate.reused_modes(identity))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, help='materialized Core 610 tree (optional)')
    args = parser.parse_args()
    print(json.dumps(check(args.source), indent=2))
    print('PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
