"""Private 594: delivered 593 plus the reviewed RPCS3/MeloNX component delta.

No historical delivery recipe or contract is imported. Run --pin only in an
isolated delivery checkout. The delivered tree and modes are retained; only the reviewed component delta is applied.
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
RECORD = ROOT / '.github/diagnostics/rewind594_baseline.json.gz'
BUILD = '594'
BASE_TREE = 'bb3c99e15e52ac109d5eaf827c80cb8e5c7759c6'
BASE_SOURCE = 'b13dc1155e5f4971ba9e32ea4a267f6e447ea1bf'
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
    assert baseline['build'] == 593 and baseline['tree'] == BASE_TREE
    assert baseline['source'] == BASE_SOURCE and baseline['run'] == 40818195216
    assert baseline['ipaSHA256'] == '6d8fe2635ef793ac24a34d760771d726174313b22f2485b1b154698c79881806'
    assert len(data['entries']) == len({path for _, _, path in data['entries']}) == 7133
    assert len(data['followHead']) == len(set(data['followHead']))
    assert sorted({entry['commit'] for entry in data['delta'].values()}) == data['deltaCommits']
    assert not set(data['delta']) & set(data['followHead'])
    assert {path for path in data['delta'] if product_path(path)} == {'native/melonx/EmbeddedLaunchPreflight.cs'}, 'Unexpected product delta'
    assert not any(product_path(path) for path in data['followHead']), 'A product input cannot follow HEAD'
    assert data['delta']['native/melonx/EmbeddedLaunchPreflight.cs']['blob'] == data['inputPins']['melonx']['files']['native/melonx/EmbeddedLaunchPreflight.cs']['blob'], 'Preflight must match compiled engine 82'
    for commit in data['deltaCommits']:
        subprocess.run(['git', 'merge-base', '--is-ancestor', commit, 'HEAD'], cwd=ROOT, check=True)
        paths = sorted(path for path, entry in data['delta'].items() if entry['commit'] == commit)
        expected = {path: (entry['mode'], entry['blob']) for path, entry in data['delta'].items()
                    if entry['commit'] == commit and not entry.get('deleted')}
        assert listed(commit, paths) == expected, commit
    assert set(data['inputPins']) == {'rpcs3', 'melonx', 'melonxRecipe', 'melonxRuntime'}
    assert {name: len(pin['files']) for name, pin in data['inputPins'].items()} == {
        'rpcs3': 190, 'melonx': 74, 'melonxRecipe': 4, 'melonxRuntime': 3}
    for name, pin in data['inputPins'].items():
        expected = {path: (entry['mode'], entry['blob']) for path, entry in pin['files'].items()}
        assert listed(pin['source'], sorted(expected)) == expected, name + ' provenance changed'
    return data


def build_tree(data):
    with tempfile.TemporaryDirectory(prefix='rewind594-index-') as tmp:
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
    assert git('write-tree').decode().strip() == tree, 'Checkout is not pinned 594'
    assert not git('diff', '--name-only').strip(), 'Pinned source changed'
    baseline = {path: git('rev-parse', BASE_TREE + ':' + path).decode().strip() for path in PRODUCTS}
    current = {path: git('rev-parse', tree + ':' + path).decode().strip() for path in PRODUCTS}
    unchanged = [path for path in PRODUCTS if path != 'native']
    assert all(current[path] == baseline[path] for path in unchanged), 'An unchanged application product differs from delivered 593'
    native_delta = git('diff-tree', '--no-commit-id', '--name-only', '-r', BASE_TREE, tree, '--', 'native').decode().splitlines()
    assert native_delta == ['native/melonx/EmbeddedLaunchPreflight.cs'], 'Unexpected native product delta'
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
    return dict(build=594, head=git('rev-parse', 'HEAD').decode().strip(), tree=tree,
                baseline=data['baseline'], deltaFiles=len(data['delta']), deltaCommits=data['deltaCommits'],
                productTrees=current, unchangedProductTrees=unchanged, reviewedNativeProductDelta=native_delta, inputPins=inputs,
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
    target = ROOT / 'build/delivery/host-tree594.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pin', action='store_true')
    args = parser.parse_args()
    print(json.dumps(pin() if args.pin else verify(), indent=2))
