#!/usr/bin/env python3
"""Private 586 from the 585 baseline (maintainer rule of 28 October 2026, AGENTS.md "Delivery baseline").

The delivered 585 index is recorded once in rewind586_baseline.json.gz: every
path with its mode and blob, and the tree they make. It was derived by the 586
recipe of rewind586_tree.py (tree_585(): the pinned 586 index with every 586
file at its delivered 585 version, proved against the recipe chain 558-585);
the 585 delivery itself is docs/evidence/rpcs3-cell585-delivery.json (run
40703700988, IPA 626a2f8b...5abe). A delivery does not prove those builds again.

The record also holds the 586 delta: every file the 586 work changes or
removes, with the commit that validated it (the MeloNX engine of 75a13f7, the
Cheats & Enhancements work of b451b10 to d0f27cc, the RPCS3 Core 587 of
a8a7ce1 and its profile 147af30, the unified cheats validator, the MeloNX
journal and the package audit of this session). The recipe files follow HEAD.

pin(): the index and working tree become baseline + delta + the recipe files
of HEAD, in one read-tree. verify(): the index is that tree, each delta file is
the blob of its commit, each delta commit is in the history of HEAD and names
the session that made it.
"""
import argparse
import gzip
import json
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RECORD = ROOT / '.github/diagnostics/rewind586_baseline.json.gz'
BUILD = '586'
# Shipped source trees, as the earlier recipes name them.
TREES = ['lib', 'native', 'packages', 'assets', 'pubspec.yaml', 'pubspec.lock']
SESSIONS = {
    'Claude-Session: https://claude.ai/code/session_01K9YJtzFdPCSuLb7YJr2eeo',  # MeloNX engine, recipe
    'Claude-Session: https://claude.ai/code/session_01JA5QgPNMf2RK6ptCEMpk2z',  # Cheats & Enhancements
    'Claude-Session: https://claude.ai/code/session_01BcZDeV9dViZteLEWQGkbHE',  # RPCS3 Core 587
}
# This recipe's own files; the earlier recipe files of the record follow HEAD as well.
RECIPE = ['.github/diagnostics/rewind586_baseline.py', '.github/diagnostics/rewind586_baseline.json.gz',
          '.github/diagnostics/rewind586_baseline_delivery.py', '.github/workflows/rewind586-baseline-delivery.yml',
          'build-utils/validate_melonx_engine586_ipa.py', 'build-utils/validate_rpcs3_core587_ipa.py',
          '.github/diagnostics/rewind586_fast.py']
ZERO = '0' * 40


def git(*args, env=None, input=None):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True, env=env, input=input).strip()


def record():
    with gzip.open(RECORD, 'rt', encoding='utf-8') as handle:
        return json.load(handle)


def follow_head(data):
    return sorted(set(data['followHead']) | set(RECIPE))


def head_entries(paths):
    """{path: (mode, blob)} of the paths HEAD carries."""
    found = {}
    for start in range(0, len(paths), 200):
        for line in git('ls-tree', '-z', '--full-tree', 'HEAD', '--', *paths[start:start + 200]).split('\0'):
            if line:
                meta, path = line.split('\t', 1)
                mode, kind, blob = meta.split()
                assert kind == 'blob', line
                found[path] = (mode, blob)
    return found


def build_tree(data):
    """The 586 tree in a scratch index: baseline, then delta, then the recipe files of HEAD."""
    with tempfile.TemporaryDirectory() as scratch:
        env = dict(os.environ, GIT_INDEX_FILE=os.path.join(scratch, 'index'))
        git('read-tree', '--empty', env=env)
        git('update-index', '-z', '--index-info', env=env,
            input=''.join(f'{mode} {blob}\t{path}\0' for mode, blob, path in data['entries']))
        baseline = git('write-tree', env=env)
        assert baseline == data['baseline']['tree'], (baseline, data['baseline']['tree'])
        lines = []
        for path, entry in sorted(data['delta'].items()):
            lines.append(f'0 {ZERO}\t{path}\0' if entry.get('deleted') else f"{entry['mode']} {entry['blob']}\t{path}\0")
        follow = follow_head(data)
        present = head_entries(follow)
        for path in follow:
            lines.append(f'{present[path][0]} {present[path][1]}\t{path}\0' if path in present else f'0 {ZERO}\t{path}\0')
        git('update-index', '-z', '--index-info', env=env, input=''.join(lines))
        return git('write-tree', env=env), baseline


def delta_contract(data):
    """Each delta file is the blob of its commit (or absent from it); each delta commit is in the history
    of HEAD and names the session that made it."""
    commits = sorted({entry['commit'] for entry in data['delta'].values()})
    assert commits == sorted(data['deltaCommits']), commits
    for commit in commits:
        subprocess.run(['git', 'merge-base', '--is-ancestor', commit, 'HEAD'], cwd=ROOT, check=True)
        message = git('log', '-1', '--format=%B', commit)
        assert any(session in message for session in SESSIONS), commit
    by_commit = {}
    for path, entry in data['delta'].items():
        by_commit.setdefault(entry['commit'], []).append(path)
    for commit, paths in by_commit.items():
        found = {}
        for start in range(0, len(paths), 200):
            for line in git('ls-tree', '-z', '--full-tree', commit, '--', *paths[start:start + 200]).split('\0'):
                if line:
                    meta, path = line.split('\t', 1)
                    mode, _, blob = meta.split()
                    found[path] = (mode, blob)
        for path in paths:
            entry = data['delta'][path]
            if entry.get('deleted'):
                assert path not in found, (path, commit)
            else:
                assert found.get(path) == (entry['mode'], entry['blob']), (path, commit)
    assert not set(data['delta']) & set(follow_head(data))
    return commits


def product_trees(tree):
    return {p: git('rev-parse', f'{tree}:{p}') for p in TREES}


def pin(report):
    data = record()
    assert os.environ.get('BUILD_NUMBER', BUILD) == BUILD
    commits = delta_contract(data)
    tree, baseline = build_tree(data)
    # One read-tree: the index and the working tree become the 586 tree (files absent from it are removed).
    subprocess.run(['git', 'read-tree', '--reset', '-u', tree], cwd=ROOT, check=True)
    assert git('write-tree') == tree
    assert not git('diff', '--name-only'), git('diff', '--name-only')
    assert not git('ls-files', '--others', '--exclude-standard', '--', *TREES[:4], 'build-utils/rpcs3')
    trees, trees585 = product_trees(tree), product_trees(baseline)
    receipt = dict(schemaVersion=1, build=int(BUILD), head=git('rev-parse', 'HEAD'), tree=tree,
                   baseline=data['baseline'] | dict(entries=None), deltaFiles=len(data['delta']),
                   deltaDeleted=sorted(p for p, e in data['delta'].items() if e.get('deleted')),
                   deltaCommits=commits, followHead=follow_head(data), productTrees=trees,
                   productTrees585=trees585, changedProductTrees=sorted(p for p in TREES if trees[p] != trees585[p]),
                   reason='The delivered 585 index with the files of the 586 commits, each from the commit that '
                          'validated it, and the recipe files of HEAD; earlier builds are not proved again '
                          '(maintainer rule of 28 October 2026).')
    receipt['baseline'].pop('entries')
    if report:
        out = ROOT / report
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({k: v for k, v in receipt.items() if k not in ('followHead', 'deltaDeleted')}, indent=2))
    return receipt


def verify():
    """The checkout is the pinned 586 tree, and the delta still holds."""
    data = record()
    commits = delta_contract(data)
    tree, baseline = build_tree(data)
    assert git('write-tree') == tree, 'the index is not the pinned 586 tree'
    assert not git('diff', '--name-only'), git('diff', '--name-only')
    return dict(build=int(BUILD), tree=tree, baselineTree=baseline, deltaFiles=len(data['delta']),
                deltaCommits=commits, productTrees=product_trees(tree))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--pin', action='store_true')
    parser.add_argument('--report', default='build/delivery/host-tree586.json')
    args = parser.parse_args()
    if args.pin:
        pin(args.report)
    else:
        print(json.dumps(verify(), indent=2))
