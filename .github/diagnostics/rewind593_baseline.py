"""Private 593: delivered 588 plus the reviewed RPCS3/MeloNX component delta.

No historical delivery recipe or contract is imported. Run --pin only in an
isolated delivery checkout. Every product tree and file mode stays at 588.
"""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
RECORD = ROOT / '.github/diagnostics/rewind593_baseline.json.gz'
BUILD = '593'
BASE_TREE = '81db3172b5ffb79e724c5ff6f944a61898fb7252'
BASE_SOURCE = '4a20e8e9a036314134df2605a6d33cd168c50098'
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
            assert kind == 'blob', path
            entries[path] = (mode, blob)
    return entries


def product_path(path):
    return path.split('/')[0] in PRODUCTS


def contract(data):
    baseline = data['baseline']
    assert baseline['build'] == 588 and baseline['tree'] == BASE_TREE
    assert baseline['source'] == BASE_SOURCE and baseline['run'] == 40803513166
    assert baseline['ipaSHA256'] == 'dfa8aa7a1d60e29226dbaa260cd12bf44a9a91510d4e25805ec6aaa0a1af9b70'
    assert len(data['entries']) == len({path for _, _, path in data['entries']}) == 7036
    assert len(data['followHead']) == len(set(data['followHead']))
    assert sorted({entry['commit'] for entry in data['delta'].values()}) == data['deltaCommits']
    assert not set(data['delta']) & set(data['followHead'])
    assert not any(product_path(path) for path in [*data['delta'], *data['followHead']]), 'Product delta is forbidden'
    for commit in data['deltaCommits']:
        subprocess.run(['git', 'merge-base', '--is-ancestor', commit, 'HEAD'], cwd=ROOT, check=True)
        paths = sorted(path for path, entry in data['delta'].items() if entry['commit'] == commit)
        expected = {path: (entry['mode'], entry['blob']) for path, entry in data['delta'].items()
                    if entry['commit'] == commit and not entry.get('deleted')}
        assert listed(commit, paths) == expected, commit
    assert set(data['inputPins']) == {'rpcs3', 'melonx', 'melonxReceipts'}
    assert {name: len(pin['files']) for name, pin in data['inputPins'].items()} == {
        'rpcs3': 161, 'melonx': 62, 'melonxReceipts': 51}
    for name, pin in data['inputPins'].items():
        expected = {path: (entry['mode'], entry['blob']) for path, entry in pin['files'].items()}
        assert listed(pin['source'], sorted(expected)) == expected, name + ' provenance changed'
    return data


def build_tree(data):
    with tempfile.TemporaryDirectory(prefix='rewind593-index-') as tmp:
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
    assert git('write-tree').decode().strip() == tree, 'Checkout is not pinned 593'
    assert not git('diff', '--name-only').strip(), 'Pinned source changed'
    baseline = {path: git('rev-parse', BASE_TREE + ':' + path).decode().strip() for path in PRODUCTS}
    current = {path: git('rev-parse', tree + ':' + path).decode().strip() for path in PRODUCTS}
    assert current == baseline, 'An application product tree differs from delivered 588'
    checked = {}
    inputs = {}
    for name, pin in data['inputPins'].items():
        expected = {path: (entry['mode'], entry['blob']) for path, entry in pin['files'].items()}
        assert listed(tree, sorted(expected)) == expected, name + ' planned input blobs changed'
        for path, entry in pin['files'].items():
            if path not in checked:
                checked[path] = hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
            assert checked[path] == entry['sha256'], 'Compiled/test input differs: ' + path
        inputs[name] = dict(source=pin['source'], count=len(expected), blobsAndSHA256Matched=True)
    for path, entry in data['hostCompatibility'].items():
        assert listed(tree, [path])[path] == listed(BASE_TREE, [path])[path] == (entry['mode'], entry['blob']), path
    return dict(build=593, head=git('rev-parse', 'HEAD').decode().strip(), tree=tree,
                baseline=data['baseline'], deltaFiles=len(data['delta']), deltaCommits=data['deltaCommits'],
                productTrees=current, unchangedProductTrees=PRODUCTS, inputPins=inputs,
                uniqueInputFilesChecked=len(checked), hostCompatibilityPaths=len(data['hostCompatibility']),
                historicalContractsReplayed=False)


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
    target = ROOT / 'build/delivery/host-tree593.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pin', action='store_true')
    args = parser.parse_args()
    print(json.dumps(pin() if args.pin else verify(), indent=2))
