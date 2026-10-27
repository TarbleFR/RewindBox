"""Private561 delivery tree: the delivered 560 product tree with the RPCS3 Core 561 recipe of 5b03388.

560 shipped the 559 product tree (itself the 558 one: 550 interface, 552
launch-crash fix, 553 MeloNX parity, 554 RPCS3 import, 557 library files, 558
MeloNX measurement files) with the RPCS3 Core 560 recipe of cba3fa9. 561 keeps
every shipped file of it and replaces only the Core recipe again: the
canonical delta, its manifest, the Core build script, the Core pin test and
workflow, and the 561 driver, test, harness and fixture. The Core they
describe (560 + the early command buffer submission) is built and tested by
its own Core run from 5b03388. The 560 recipe pins five of these files at
cba3fa9; the only commit that changed them since is 5b03388. No file of lib,
native, packages, assets or pubspec changes, so the product trees are the
delivered 560 (and 559, 558) ones. The recipe carries core_swap_base.py: the
macOS job takes the published 559 application (release 0.0.10) in place of
the Xcode compile.

Earlier receipts stay bound to the delivered 560 tree, which at_560() gives
back: the 561 files at their 560 versions and this recipe removed
(documentation follows HEAD in both). Runner checkout only: Git history is
not changed.
"""
import argparse, fnmatch, json, os, subprocess, tempfile
from pathlib import Path
import rpcs3cell560_tree as previous

ROOT = Path(__file__).resolve().parents[2]
HOST_TREE = previous.HOST_TREE
SOURCE551 = previous.SOURCE551
SOURCE558 = previous.SOURCE558
SOURCE559 = previous.SOURCE559
SOURCE560 = previous.SOURCE560
# The Core commit built and tested by the 561 Core run.
SOURCE561 = '5b033881a032be1c2ac71080e229b86dc675ed6d'
CORE_COMMITS = {'5b033881': '[rpcs3-cell561-core]'}
CELL561 = ['.github/diagnostics/rpcs3cell561_core.py',
           '.github/workflows/rpcs3-cell561-core.yml',
           '.github/workflows/rpcs3-core.yml',
           'build-utils/build_rpcs3_embedded_core.sh',
           'build-utils/rpcs3/canonical-source.json',
           'build-utils/rpcs3/embedded-core.patch',
           'docs/evidence/rpcs3-cell561-host-linux.json',
           'docs/evidence/rpcs3-cell561-macos.json',
           'docs/rpcs3-cell561.md',
           'test/fixtures/rpcs3_cell561.diff',
           'test/native/rpcs3_early561.inc',
           'test/neo_swap_core_pin_test.py',
           'test/rpcs3_cell561_test.py']
# The files the 560 recipe pinned at the 560 Core commit that 561 replaces.
REPLACED = sorted(p for p in CELL561 if previous.source_of(p) == SOURCE560)
RECIPE = ['.github/diagnostics/rpcs3cell561_tree.py', '.github/diagnostics/rpcs3cell561_delivery.py',
          '.github/workflows/rpcs3-cell561-delivery.yml', 'build-utils/validate_rpcs3_561_ipa.py',
          'build-utils/validate_liquid_glass561_ipa.py', 'build-utils/validate_melonx_perf561_ipa.py',
          'build-utils/validate_rpcs3_library_files561_ipa.py', 'build-utils/delivery-561-recipient.pem',
          'build-utils/core_swap_base.py']
OWNED = previous.OWNED + CELL561 + RECIPE
TREES = previous.TREES
assert REPLACED == sorted(['.github/workflows/rpcs3-core.yml', 'build-utils/build_rpcs3_embedded_core.sh',
                           'build-utils/rpcs3/canonical-source.json', 'build-utils/rpcs3/embedded-core.patch',
                           'test/neo_swap_core_pin_test.py']), REPLACED
# 561 ships nothing: no file of the product trees is a 561 file.
assert not [p for p in CELL561 if p.split('/')[0] in TREES or p in TREES]


def git(*args, env=None):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True, env=env).strip()


def matches(path, patterns):
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def owned(path):
    return path in CELL561 or matches(path, RECIPE) or previous.owned(path)


def source_of(path):
    """Commit whose version of a file this build carries; None for this
    build's own recipe and for documentation, which follow HEAD."""
    if path in CELL561:
        return None if path.startswith('docs/') else SOURCE561
    if matches(path, RECIPE):
        return None
    return previous.source_of(path)


exists = previous.exists
blob = previous.blob


def at_560():
    """{path: commit, or None when absent}: every 561 file at its version in
    the delivered 560 tree, and this recipe removed. Applied to this index it
    gives back the 560 index exactly (docs follow HEAD in both)."""
    versions = {p: None for p in RECIPE}
    for p in CELL561:
        source = previous.source_of(p)
        if source is None:
            versions[p] = git('rev-parse', 'HEAD') if exists('HEAD', p) else None
        else:
            versions[p] = source if exists(source, p) else None
    return versions


def parent_contract():
    """The 561 change is exactly the Core commit since 560: each replaced
    file's 560 version is the 560 Core one, the only commit that touched a 561
    file since cba3fa9 is the Core commit validated by its own Core run, and
    each non-documentation file did change."""
    for p in CELL561:
        if p.startswith('docs/'):
            continue
        before = previous.source_of(p)
        assert before == SOURCE560 if p in REPLACED else not exists(before, p), (p, before)
        assert blob(SOURCE561, p) != (blob(before, p) if before else None), (p, 'unchanged')
    commits = git('log', '--format=%H', SOURCE560 + '..' + SOURCE561, '--',
                  *[p for p in CELL561 if not p.startswith('docs/')]).split()
    assert commits == [SOURCE561], commits
    tags = {c[:8]: git('log', '-1', '--format=%s', c) for c in commits}
    assert set(tags) == set(CORE_COMMITS), tags
    for short, tag in CORE_COMMITS.items():
        assert tags[short].endswith(tag), (short, tags[short])


def verify():
    """The index is the 560 product tree with the 561 files, each from its source.

    The index, not the working tree, is compared: later build steps generate and
    patch files in place but never stage them, so the check stays valid.
    """
    staged = [p for p in git('diff', '--cached', '--name-only', HOST_TREE).splitlines() if p]
    foreign = sorted(p for p in staged if not owned(p))
    assert not foreign, foreign
    for p in staged:
        source = source_of(p)
        if source is None:
            continue
        assert exists(source, p), (p, 'absent from', source)
        assert git('rev-parse', ':' + p) == git('rev-parse', source + ':' + p), (p, source)
    for p in CELL561:
        if source_of(p):
            assert git('rev-parse', ':' + p) == git('rev-parse', SOURCE561 + ':' + p), p
    return sorted(staged)


def pin(report):
    head = git('rev-parse', 'HEAD')
    parent_contract()
    previous.parent_contract()
    previous.previous.parent_contract()
    previous.previous.previous.parent_contract()
    p558 = previous.previous.previous
    committed = {p for p in git('diff', '--name-only', HOST_TREE, head).splitlines() if p}
    plan = {}
    for p in sorted(committed | set(p558.UI550) | set(p558.CELL551) | set(p558.FIX552)
                    | set(p558.PARITY) | set(p558.FIX554) | set(p558.FIX557)
                    | set(p558.FIX558) | set(previous.previous.CELL559) | set(previous.CELL560)
                    | set(CELL561)):
        source = source_of(p)
        if source is not None:
            plan.setdefault(source, []).append(p)
    restored, removed = {}, []
    for source, paths in plan.items():
        present = [p for p in paths if exists(source, p)]
        absent = [p for p in paths if not exists(source, p)]
        changed = [p for p in present if not exists(head, p) or git('rev-parse', head + ':' + p) != git('rev-parse', source + ':' + p)]
        if changed:
            subprocess.run(['git', 'restore', '--source=' + source, '--staged', '--worktree', '--', *changed], cwd=ROOT, check=True)
            restored[source] = changed
        for p in absent:
            if exists(head, p):
                subprocess.run(['git', 'rm', '-q', '--cached', '--', p], cwd=ROOT, check=True)
                (ROOT / p).unlink(missing_ok=True)
                removed.append(p)
    kept = verify()
    # Fresh checkout: the working tree must equal the pinned index exactly.
    assert not git('diff', '--name-only'), git('diff', '--name-only')
    assert not git('ls-files', '--others', '--exclude-standard', '--', 'lib', 'native', 'packages', 'assets', 'build-utils/rpcs3')
    trees = product_trees()
    assert trees == product_trees_560(), '561 changes no shipped file'
    receipt = dict(schemaVersion=1, head=head, hostTree=HOST_TREE, source551=SOURCE551, source558=SOURCE558,
                   source559=SOURCE559, source560=SOURCE560, source561=SOURCE561, replaced=REPLACED,
                   restored=restored, removed=sorted(removed), keptFiles=kept, productTrees=trees,
                   productTrees560=product_trees_560(),
                   reason='The 560 product tree with the RPCS3 Core 561 recipe of 5b03388; each file from the commit that validated it; Git history unchanged.')
    if report:
        out = ROOT / report
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))
    return receipt


def product_trees():
    """Git object IDs of every shipped source tree in the pinned index."""
    tree = git('write-tree')
    return {p: git('rev-parse', tree + ':' + p) for p in TREES}


index_with = previous.index_with


def tree_560():
    """The delivered 560 tree: the 561 files at their 560 versions, computed in
    a scratch copy of the index, so the pinned index is untouched."""
    with tempfile.TemporaryDirectory() as scratch:
        env = index_with(at_560(), os.path.join(scratch, 'index'))
        return git('write-tree', env=env)


def product_trees_560():
    tree = tree_560()
    return {p: git('rev-parse', tree + ':' + p) for p in TREES}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--pin', action='store_true')
    p.add_argument('--report', default='build/delivery/host-tree561.json')
    a = p.parse_args()
    if a.pin:
        pin(a.report)
    else:
        print(json.dumps(verify(), indent=2))
