"""Private 588: the recorded delivered 587 tree plus this delivery's delta.

No earlier delivery module is imported or replayed. Run --pin only in the
isolated CI checkout. Modes are retained in the snapshot and scratch index.
"""
import argparse
import gzip
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
RECORD = ROOT / '.github/diagnostics/rewind588_baseline.json.gz'
BUILD = '588'
BASE_TREE = 'fed8b77804738d471dc983853c2e1cd3f15ffb9c'
PRODUCTS = ['lib', 'native', 'packages', 'assets', 'pubspec.yaml', 'pubspec.lock']


def git(*args, env=None, data=None):
    return subprocess.check_output(['git', *args], cwd=ROOT, env=env, input=data)


def record():
    with gzip.open(RECORD, 'rt') as stream:
        return json.load(stream)


def listed(ref, paths=None):
    entries = {}
    args = ['ls-tree', '-rz', '--full-tree', ref]
    if paths:
        args += ['--', *paths]
    for row in git(*args).decode().split('\0'):
        if row:
            meta, path = row.split('\t')
            mode, kind, blob = meta.split()
            assert kind == 'blob'
            entries[path] = (mode, blob)
    return entries


def contract(data):
    assert data['baseline']['build'] == 587 and data['baseline']['tree'] == BASE_TREE
    assert data['baseline']['source'] == 'cd7ed1e2c127aa22a1466a06ed2961d9babf0f08'
    assert sorted({v['commit'] for v in data['delta'].values()}) == data['deltaCommits']
    assert not set(data['delta']) & set(data['followHead'])
    for commit in data['deltaCommits']:
        subprocess.run(['git', 'merge-base', '--is-ancestor', commit, 'HEAD'], cwd=ROOT, check=True)
        paths = sorted(p for p, v in data['delta'].items() if v['commit'] == commit)
        expected = {p: (v['mode'], v['blob']) for p, v in data['delta'].items()
                    if v['commit'] == commit and not v.get('deleted')}
        assert listed(commit, paths) == expected, commit
    return data


def build_tree(data):
    with tempfile.TemporaryDirectory(prefix='rewind588-index-') as tmp:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(tmp) / 'index'))
        git('read-tree', '--empty', env=env)
        rows = ''.join(f'{mode} {blob}\t{path}\0' for mode, blob, path in data['entries'])
        git('update-index', '-z', '--index-info', env=env, data=rows.encode())
        assert git('write-tree', '--missing-ok', env=env).decode().strip() == BASE_TREE
        changes = {}
        for path, entry in data['delta'].items():
            changes[path] = ('0', '0' * 40) if entry.get('deleted') else (entry['mode'], entry['blob'])
        current = listed('HEAD', data['followHead'])
        for path in data['followHead']:
            assert path in current, 'Missing reviewed recipe/input: ' + path
            changes[path] = current[path]
        rows = ''.join(f'{mode} {blob}\t{path}\0' for path, (mode, blob) in sorted(changes.items()))
        git('update-index', '-z', '--index-info', env=env, data=rows.encode())
        return git('write-tree', '--missing-ok', env=env).decode().strip()


def source_contract(data=None, expected_tree=None):
    data = contract(record()) if data is None else data
    tree = build_tree(data) if expected_tree is None else expected_tree
    assert git('write-tree').decode().strip() == tree, 'Checkout is not pinned 588'
    assert not git('diff', '--name-only').strip(), 'Pinned source changed'
    baseline = {p: git('rev-parse', BASE_TREE + ':' + p).decode().strip() for p in PRODUCTS}
    current = {p: git('rev-parse', tree + ':' + p).decode().strip() for p in PRODUCTS}
    assert {p for p in PRODUCTS if current[p] != baseline[p]} == {'native'}
    changed = git('diff', '--name-only', BASE_TREE, tree, '--', *PRODUCTS).decode().splitlines()
    assert changed == ['native/melonx/EmbeddedNativeGamepadLease.cs'], changed
    return dict(build=588, head=git('rev-parse', 'HEAD').decode().strip(), tree=tree,
                baseline=data['baseline'], deltaFiles=len(data['delta']),
                deltaCommits=data['deltaCommits'], productTrees=current,
                unchangedProductTrees=[p for p in PRODUCTS if current[p] == baseline[p]])


def verify():
    import sys
    sys.path.insert(0, str(ROOT / 'build-utils'))
    from delivery_contract_memo import reuse
    return reuse(BUILD, source_contract)


def pin():
    assert os.environ.get('BUILD_NUMBER', BUILD) == BUILD
    data = contract(record())
    tree = build_tree(data)
    subprocess.run(['git', 'read-tree', '--reset', '-u', tree], cwd=ROOT, check=True)
    import sys
    sys.path.insert(0, str(ROOT / 'build-utils'))
    from delivery_contract_memo import reuse
    result = reuse(BUILD, lambda: source_contract(data, tree))
    target = ROOT / 'build/delivery/host-tree588.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pin', action='store_true')
    args = parser.parse_args()
    print(json.dumps(pin() if args.pin else verify(), indent=2))
