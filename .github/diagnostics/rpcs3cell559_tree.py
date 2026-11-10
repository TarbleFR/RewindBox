"""Private559 delivery tree: the delivered 558 product tree with the RPCS3 Core 559 recipe of 07c76ec.

558 shipped the 557 product tree (550 interface, RPCS3 551 Core, 552
launch-crash fix, 553 MeloNX parity, 554 RPCS3 import, 557 library files)
with the MeloNX measurement files of cfce9f6. 559 keeps every shipped file of
it and replaces only the Core recipe: the canonical delta, its manifest, the
Core build script, the Core pin test and workflow, and the 559 driver, tests
and fixture. The Core they describe (551 + 555 + 559) was built and tested by
run 40403710130 from 07c76ec. Earlier recipes pin five of these files at the
551 Core commit (4e5bf59); every commit that changed them since is a Core
commit validated by its own Core run (554 benchmark, 555, 559). No file of
lib, native, packages, assets or pubspec changes, so the product trees are
the delivered 558 ones.

Earlier receipts stay bound to the delivered 558 tree, which at_558() gives
back: the 559 files at their 558 versions and this recipe removed
(documentation follows HEAD in both). Runner checkout only: Git history is
not changed.
"""
import argparse, fnmatch, json, os, subprocess, tempfile
from pathlib import Path
import melonxperf558_tree as previous

ROOT = Path(__file__).resolve().parents[2]
HOST_TREE = previous.HOST_TREE
SOURCE551 = previous.SOURCE551
SOURCE558 = previous.SOURCE558
# The Core commit built and tested by run 40403710130.
SOURCE559 = '07c76ec11f4000247f908b792f53b304c91c8bcd'
CORE_COMMITS = {'f1a30bf8': '[rpcs3-cell554-bench]', 'f508f1bf': '[rpcs3-cell555-core]', '07c76ec1': '[rpcs3-cell559-core]'}
CELL559 = ['.github/diagnostics/rpcs3cell559_core.py',
           '.github/workflows/rpcs3-cell559-core.yml',
           '.github/workflows/rpcs3-core.yml',
           'build-utils/build_rpcs3_embedded_core.sh',
           'build-utils/rpcs3/canonical-source.json',
           'build-utils/rpcs3/embedded-core.patch',
           'docs/evidence/rpcs3-cell559-host-linux.json',
           'docs/evidence/rpcs3-cell559-macos.json',
           'docs/rpcs3-cell559.md',
           'test/fixtures/rpcs3_cell559.diff',
           'test/native/rpcs3_dirty559.inc',
           'test/native/rpcs3_epoch559.inc',
           'test/native/rpcs3_inline559.inc',
           'test/native/rpcs3_inline559_main.inc',
           'test/native/rpcs3_overwrite559.inc',
           'test/native/rpcs3_spupasses559.inc',
           'test/native/rpcs3_vpcompare559.inc',
           'test/neo_swap_core_pin_test.py',
           'test/rpcs3_cell559_test.py']
# The files earlier recipes pinned at the 551 Core commit that 559 replaces.
REPLACED = sorted(p for p in CELL559 if previous.source_of(p) == SOURCE551)
RECIPE = ['.github/diagnostics/rpcs3cell559_tree.py', '.github/diagnostics/rpcs3cell559_delivery.py',
          '.github/workflows/rpcs3-cell559-delivery.yml', 'build-utils/validate_rpcs3_559_ipa.py',
          'build-utils/validate_liquid_glass559_ipa.py', 'build-utils/validate_melonx_perf559_ipa.py',
          'build-utils/validate_rpcs3_library_files559_ipa.py', 'build-utils/delivery-559-recipient.pem']
OWNED = previous.OWNED + CELL559 + RECIPE
TREES = previous.TREES
assert REPLACED == sorted(['.github/workflows/rpcs3-core.yml', 'build-utils/build_rpcs3_embedded_core.sh',
                           'build-utils/rpcs3/canonical-source.json', 'build-utils/rpcs3/embedded-core.patch',
                           'test/neo_swap_core_pin_test.py']), REPLACED
# 559 ships nothing: no file of the product trees is a 559 file.
assert not [p for p in CELL559 if p.split('/')[0] in TREES or p in TREES]


def git(*args, env=None):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True, env=env).strip()


def matches(path, patterns):
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def owned(path):
    return path in CELL559 or matches(path, RECIPE) or previous.owned(path)


def source_of(path):
    """Commit whose version of a file this build carries; None for this
    build's own recipe and for documentation, which follow HEAD."""
    if path in CELL559:
        return None if path.startswith('docs/') else SOURCE559
    if matches(path, RECIPE):
        return None
    return previous.source_of(path)


def exists(commit, path):
    return bool(git('ls-tree', commit, '--', path))


def blob(commit, path):
    return git('rev-parse', commit + ':' + path) if exists(commit, path) else None


def at_558():
    """{path: commit, or None when absent}: every 559 file at its version in
    the delivered 558 tree, and this recipe removed. Applied to this index it
    gives back the 558 index exactly (docs follow HEAD in both)."""
    versions = {p: None for p in RECIPE}
    for p in CELL559:
        source = previous.source_of(p)
        if source is None:
            versions[p] = git('rev-parse', 'HEAD') if exists('HEAD', p) else None
        else:
            versions[p] = source if exists(source, p) else None
    return versions


def parent_contract():
    """The 559 change is exactly the Core commits since 551: each replaced
    file's 558 version is the 551 Core one, every commit that touched a 559
    file since 4e5bf59 is one of the Core commits validated by its own Core
    run, and each non-documentation file did change."""
    for p in CELL559:
        if p.startswith('docs/'):
            continue
        before = previous.source_of(p)
        assert before == SOURCE551 if p in REPLACED else not exists(before, p), (p, before)
        assert blob(SOURCE559, p) != (blob(before, p) if before else None), (p, 'unchanged')
    commits = git('log', '--format=%H', SOURCE551 + '..' + SOURCE559, '--',
                  *[p for p in CELL559 if not p.startswith('docs/')]).split()
    assert commits and commits[0] == SOURCE559, commits
    tags = {c[:8]: git('log', '-1', '--format=%s', c) for c in commits}
    assert set(tags) == set(CORE_COMMITS), tags
    for short, tag in CORE_COMMITS.items():
        assert tags[short].endswith(tag), (short, tags[short])


def verify():
    """The index is the 558 product tree with the 559 files, each from its source.

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
    for p in CELL559:
        if source_of(p):
            assert git('rev-parse', ':' + p) == git('rev-parse', SOURCE559 + ':' + p), p
    return sorted(staged)


def pin(report):
    head = git('rev-parse', 'HEAD')
    parent_contract()
    previous.parent_contract()
    committed = {p for p in git('diff', '--name-only', HOST_TREE, head).splitlines() if p}
    plan = {}
    for p in sorted(committed | set(previous.UI550) | set(previous.CELL551) | set(previous.FIX552)
                    | set(previous.PARITY) | set(previous.FIX554) | set(previous.FIX557)
                    | set(previous.FIX558) | set(CELL559)):
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
    assert trees == product_trees_558(), '559 changes no shipped file'
    receipt = dict(schemaVersion=1, head=head, hostTree=HOST_TREE, source551=SOURCE551, source558=SOURCE558,
                   source559=SOURCE559, replaced=REPLACED, restored=restored, removed=sorted(removed),
                   keptFiles=kept, productTrees=trees, productTrees558=product_trees_558(),
                   reason='The 558 product tree with the RPCS3 Core 559 recipe of 07c76ec; each file from the commit that validated it; Git history unchanged.')
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


def tree_558():
    """The delivered 558 tree: the 559 files at their 558 versions, computed in
    a scratch copy of the index, so the pinned index is untouched."""
    with tempfile.TemporaryDirectory() as scratch:
        env = index_with(at_558(), os.path.join(scratch, 'index'))
        return git('write-tree', env=env)


def product_trees_558():
    tree = tree_558()
    return {p: git('rev-parse', tree + ':' + p) for p in TREES}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--pin', action='store_true')
    p.add_argument('--report', default='build/delivery/host-tree559.json')
    a = p.parse_args()
    if a.pin:
        pin(a.report)
    else:
        print(json.dumps(verify(), indent=2))
