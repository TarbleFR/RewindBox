"""Private585 delivery tree: the delivered 583 product tree with the RPCS3 Core 585 recipe of 2b01363.

583 shipped the 582 product (the 581 product with the MeloNX engine of
e55ca25 and the Switch discovery fix) with the RPCS3 Core 583. 585 keeps
every shipped file of it and replaces only the RPCS3 Core recipe: the
canonical delta, its manifest, the Core build script, the Core pin test and
workflow, and the driver, test and fixture of the Core 585. The Core they
describe (583 with early command buffer submission Automatic for God of War
III) is built and tested by its own Core run from 2b01363. The 583 tree pins
five of these files at 8ebca28 (the 583 Core); the only commit that changed a
585 file since is the 585 Core commit. No file of lib, native, packages,
assets or pubspec changes: the product trees are the delivered 583 ones.

Earlier receipts stay bound to the delivered 583 tree, which at_583() gives
back: the 585 files at their 583 versions and this recipe removed
(documentation follows HEAD in both). Runner checkout only: Git history is
not changed.
"""
import argparse, fnmatch, json, os, subprocess, tempfile
from pathlib import Path
import rpcs3cell583_tree as previous

ROOT = Path(__file__).resolve().parents[2]
HOST_TREE = previous.HOST_TREE
SOURCE551 = previous.SOURCE551
SOURCE558 = previous.SOURCE558
SOURCE559 = previous.SOURCE559
SOURCE560 = previous.SOURCE560
SOURCE561 = previous.SOURCE561
SOURCE562 = previous.SOURCE562
SOURCE563 = previous.SOURCE563
SOURCE564 = previous.SOURCE564
SOURCE565 = previous.SOURCE565
SOURCE565APP = previous.SOURCE565APP
SOURCE566 = previous.SOURCE566
SOURCE567 = previous.SOURCE567
SOURCE569 = previous.SOURCE569
SOURCE571 = previous.SOURCE571
SOURCE572 = previous.SOURCE572
SOURCE573 = previous.SOURCE573
SOURCE575 = previous.SOURCE575
SOURCE576 = previous.SOURCE576
SOURCE577 = previous.SOURCE577
SOURCE_APP577 = previous.SOURCE_APP577
SOURCE579 = previous.SOURCE579
SOURCE581 = previous.SOURCE581
SOURCE582 = previous.SOURCE582
SOURCE_APP582 = previous.SOURCE_APP582
SOURCE583 = previous.SOURCE583
# The Core commit built and tested by the 585 Core run.
SOURCE585 = '2b013636f53a432bf67752d30d84a2bb33facbf2'
CORE_COMMITS = {SOURCE585[:8]: '[rpcs3-cell585-core]'}
CELL585 = ['.github/diagnostics/rpcs3cell585_core.py',
           '.github/workflows/rpcs3-cell585-core.yml',
           '.github/workflows/rpcs3-core.yml',
           'build-utils/build_rpcs3_embedded_core.sh',
           'build-utils/rpcs3/canonical-source.json',
           'build-utils/rpcs3/embedded-core.patch',
           'docs/evidence/rpcs3-cell585-host-linux.json',
           'docs/evidence/rpcs3-cell585-macos.json',
           'docs/rpcs3-cell585.md',
           'test/fixtures/rpcs3_cell585.diff',
           'test/neo_swap_core_pin_test.py',
           'test/rpcs3_cell585_test.py']
# The files the 583 tree pins at the 583 Core commit that 585 replaces.
REPLACED = sorted(p for p in CELL585 if previous.source_of(p) == SOURCE583)
# delivery_contract_memo.py, which the 565 recipe owns, follows HEAD here too.
RECIPE = ['.github/diagnostics/rpcs3cell585_tree.py', '.github/diagnostics/rpcs3cell585_delivery.py',
          '.github/workflows/rpcs3-cell585-delivery.yml', 'build-utils/validate_rpcs3_585_ipa.py',
          'build-utils/validate_liquid_glass585_ipa.py', 'build-utils/validate_melonx_perf585_ipa.py',
          'build-utils/validate_rpcs3_library_files585_ipa.py', 'build-utils/validate_melonx_input585_ipa.py',
          'build-utils/validate_melonx_texture585_ipa.py', 'build-utils/validate_melonx_jit585_ipa.py',
          'build-utils/validate_melonx_switch585_ipa.py', 'build-utils/validate_melonx_warm585_ipa.py',
          'build-utils/validate_melonx_sync585_ipa.py', 'build-utils/validate_melonx_entry585_ipa.py',
          'build-utils/delivery-585-recipient.pem']
OWNED = previous.OWNED + CELL585 + RECIPE
TREES = previous.TREES
assert REPLACED == sorted(['.github/workflows/rpcs3-core.yml', 'build-utils/build_rpcs3_embedded_core.sh',
                           'build-utils/rpcs3/canonical-source.json', 'build-utils/rpcs3/embedded-core.patch',
                           'test/neo_swap_core_pin_test.py']), REPLACED
# The Core recipe ships nothing.
assert not [p for p in CELL585 if p.split('/')[0] in TREES or p in TREES]
assert not set(CELL585) & set(previous.RECIPE)
assert not set(CELL585) & set(previous.previous.CHANGED)
assert previous.owned('build-utils/delivery_contract_memo.py')


def git(*args, env=None):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True, env=env).strip()


def matches(path, patterns):
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def owned(path):
    return path in CELL585 or matches(path, RECIPE) or previous.owned(path)


def source_of(path):
    """Commit whose version of a file this build carries; None for this
    build's own recipe and for documentation, which follow HEAD."""
    if path in CELL585:
        return None if path.startswith('docs/') else SOURCE585
    if matches(path, RECIPE):
        return None
    return previous.source_of(path)


exists = previous.exists
blob = previous.blob
index_with = previous.index_with


def at_583():
    """{path: commit, or None when absent}: every 585 file at its version in
    the delivered 583 tree, and this recipe removed. Applied to this index it
    gives back the 583 index exactly (docs follow HEAD in both)."""
    versions = {p: None for p in RECIPE}
    for p in CELL585:
        source = previous.source_of(p)
        if source is None:
            versions[p] = git('rev-parse', 'HEAD') if exists('HEAD', p) else None
        else:
            versions[p] = source if exists(source, p) else None
    return versions


def parent_contract():
    """The 585 change is exactly the 585 Core commit: each replaced file's
    583 version is the 583 Core one, every other 585 file is absent from the
    583 tree, the only commit that touched a 585 file since 8ebca28 is the
    585 Core commit (validated by its own Core run), and each
    non-documentation file did change."""
    for p in CELL585:
        if p.startswith('docs/'):
            continue
        before = previous.source_of(p)
        assert before == SOURCE583 if p in REPLACED else not exists(before, p), (p, before)
        assert blob(SOURCE585, p) != (blob(before, p) if before and exists(before, p) else None), (p, 'unchanged')
    commits = git('log', '--format=%H', SOURCE583 + '..' + SOURCE585, '--',
                  *[p for p in CELL585 if not p.startswith('docs/')]).split()
    assert commits[0] == SOURCE585 and len(commits) == len(CORE_COMMITS), commits
    tags = {c[:8]: git('log', '-1', '--format=%s', c) for c in commits}
    assert set(tags) == set(CORE_COMMITS), tags
    for short, tag in CORE_COMMITS.items():
        assert tags[short].endswith(tag), (short, tags[short])


def verify():
    """The index is the 583 product tree with the 585 files, each from its source.

    The index, not the working tree, is compared: later build steps generate and
    patch files in place but never stage them, so the check stays valid.
    """
    staged = [p for p in git('diff', '--cached', '--name-only', HOST_TREE).splitlines() if p]
    foreign = sorted(p for p in staged if not owned(p))
    assert not foreign, foreign
    p577 = previous.previous.previous.previous.previous
    for p in staged:
        source = source_of(p)
        if source is None:
            continue
        if not exists(source, p):
            # Deleted at its source (the 576 trace, the 504f9c0 Dart files): absent from the index.
            assert p in p577.DELETED577 + p577.previous.DELETED576 and not git('ls-files', '--', p), p
            continue
        assert git('rev-parse', ':' + p) == git('rev-parse', source + ':' + p), (p, source)
    for p in CELL585:
        if source_of(p):
            assert git('rev-parse', ':' + p) == git('rev-parse', SOURCE585 + ':' + p), p
    return sorted(staged)


def pin(report):
    head = git('rev-parse', 'HEAD')
    parent_contract()
    chain = previous
    for _ in range(19):
        # 583, 582, 581, 579, 577, 576, 575, 573, 572, 567, 566, 565, 564, 563, 562, 561, 560, 559 and 558, each against its own parent.
        chain.parent_contract()
        p558 = chain
        chain = chain.previous
    p583 = previous
    p582 = p583.previous
    p581 = p582.previous
    p579 = p581.previous
    p577 = p579.previous
    p576 = p577.previous
    p575 = p576.previous
    p573 = p575.previous
    p572 = p573.previous
    p567 = p572.previous
    p566 = p567.previous
    p565 = p566.previous
    p564 = p565.previous
    p563 = p564.previous
    p562 = p563.previous
    p561 = p562.previous
    committed = {p for p in git('diff', '--name-only', HOST_TREE, head).splitlines() if p}
    plan = {}
    for p in sorted(committed | set(p558.UI550) | set(p558.CELL551) | set(p558.FIX552)
                    | set(p558.PARITY) | set(p558.FIX554) | set(p558.FIX557)
                    | set(p558.FIX558) | set(p561.previous.previous.CELL559) | set(p561.previous.CELL560)
                    | set(p561.CELL561) | set(p562.FIX562) | set(p563.CELL563) | set(p564.FIX564)
                    | set(p565.CELL565) | set(p565.FIX565) | set(p566.FIX566) | set(p567.CELL567)
                    | set(p572.FIX572) | set(p573.CELL573) | set(p575.CELL575) | set(p576.FIX576)
                    | set(p576.APP576) | set(p577.FIX577) | set(p577.APP577) | set(p579.CELL579)
                    | set(p581.CELL581) | set(p582.FIX582) | set(p582.APP582) | set(p583.CELL583) | set(CELL585)):
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
    trees583 = product_trees_583()
    # No product tree changes: the Core is built by its own run.
    assert trees == trees583, (trees, trees583)
    receipt = dict(schemaVersion=1, head=head, hostTree=HOST_TREE, source551=SOURCE551, source558=SOURCE558,
                   source559=SOURCE559, source560=SOURCE560, source561=SOURCE561, source562=SOURCE562,
                   source563=SOURCE563, source564=SOURCE564, source565=SOURCE565, source565App=SOURCE565APP,
                   source566=SOURCE566, source567=SOURCE567, source569=SOURCE569, source571=SOURCE571,
                   source572=SOURCE572, source573=SOURCE573, source575=SOURCE575, source576=SOURCE576,
                   source577=SOURCE577, sourceApp577=SOURCE_APP577, source579=SOURCE579, source581=SOURCE581,
                   source582=SOURCE582, sourceApp582=SOURCE_APP582, source583=SOURCE583, source585=SOURCE585,
                   replaced=REPLACED, restored=restored, removed=sorted(removed), keptFiles=kept, productTrees=trees,
                   productTrees583=trees583,
                   reason='The 583 product tree with the RPCS3 Core 585 recipe of 2b01363; each file from the commit that validated it; Git history unchanged.')
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


def tree_583():
    """The delivered 583 tree: the 585 files at their 583 versions, computed in
    a scratch copy of the index, so the pinned index is untouched."""
    with tempfile.TemporaryDirectory() as scratch:
        env = index_with(at_583(), os.path.join(scratch, 'index'))
        return git('write-tree', env=env)


def product_trees_583():
    tree = tree_583()
    return {p: git('rev-parse', tree + ':' + p) for p in TREES}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--pin', action='store_true')
    p.add_argument('--report', default='build/delivery/host-tree585.json')
    a = p.parse_args()
    if a.pin:
        pin(a.report)
    else:
        print(json.dumps(verify(), indent=2))
