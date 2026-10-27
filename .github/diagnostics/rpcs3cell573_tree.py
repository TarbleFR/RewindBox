"""Private573 delivery tree: the delivered 572 product tree with the RPCS3 Core 573 recipe of 92074e5.

572 shipped the 567 product (the 566 product with the RPCS3 Core 567; God of
War III without the 30 fps limiter, MeloNX keyboard and L3/R3) with the
MeloNX engine of 8cc2348. 573 keeps every shipped file of it and replaces
only the RPCS3 Core recipe: the canonical delta, its manifest, the Core build
script, the Core pin test and workflow, and the drivers, tests, harnesses and
fixtures of the Cores 569, 571 and 573. The Core they describe (567 with the
iOS QoS kept, passive-lock fairness, the texture residency cap and scoped
texture revalidation) is built and tested by its own Core run from 92074e5;
the 569 and 571 Cores were each built and tested by theirs. The 567 recipe,
which the 572 tree keeps, pins five of these files at 67dd222; the only
commits that changed a 573 file since are the Core commits of 569, 571 and
573. No file of lib, native, packages, assets or pubspec changes: the product
trees are the delivered 572 ones.

Earlier receipts stay bound to the delivered 572 tree, which at_572() gives
back: the 573 files at their 572 versions and this recipe removed
(documentation follows HEAD in both). Runner checkout only: Git history is
not changed.
"""
import argparse, fnmatch, json, os, subprocess, tempfile
from pathlib import Path
import melonxjit572_tree as previous

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
SOURCE572 = previous.SOURCE572
# The Core commit built and tested by the 573 Core run; the 569 and 571 Core
# commits before it, each built and tested by its own Core run.
SOURCE573 = '92074e51b9e7216902c57fd5ae099d8aa3caea63'
SOURCE571 = '0522f593b7abd08f32414b3107a4dbf2e7f0f186'
SOURCE569 = 'e70fa381297f53808db3e136ae9df65718daca3a'
CORE_COMMITS = {'92074e51': '[rpcs3-cell573-core]', '0522f593': '[rpcs3-cell571-core]',
                'bca64ab0': '[rpcs3-cell571-core]', 'ab192e8b': '[rpcs3-cell571-core]',
                'e70fa381': '[rpcs3-cell569-core]'}
CELL573 = ['.github/diagnostics/rpcs3cell569_core.py',
           '.github/diagnostics/rpcs3cell571_core.py',
           '.github/diagnostics/rpcs3cell573_core.py',
           '.github/workflows/rpcs3-cell569-core.yml',
           '.github/workflows/rpcs3-cell571-core.yml',
           '.github/workflows/rpcs3-cell573-core.yml',
           '.github/workflows/rpcs3-core.yml',
           'build-utils/build_rpcs3_embedded_core.sh',
           'build-utils/rpcs3/canonical-source.json',
           'build-utils/rpcs3/embedded-core.patch',
           'docs/evidence/rpcs3-cell569-host-linux.json',
           'docs/evidence/rpcs3-cell569-macos.json',
           'docs/evidence/rpcs3-cell571-host-linux.json',
           'docs/evidence/rpcs3-cell571-macos.json',
           'docs/evidence/rpcs3-cell573-host-linux.json',
           'docs/evidence/rpcs3-cell573-macos.json',
           'docs/rpcs3-cell569.md',
           'docs/rpcs3-cell571.md',
           'docs/rpcs3-cell573.md',
           'test/fixtures/rpcs3_cell569.diff',
           'test/fixtures/rpcs3_cell571.diff',
           'test/fixtures/rpcs3_cell573.diff',
           'test/native/rpcs3_passive_gate571.inc',
           'test/native/rpcs3_qos_keep569.inc',
           'test/native/rpcs3_scoped_revalidation573.inc',
           'test/native/rpcs3_texture_residency573.inc',
           'test/neo_swap_core_pin_test.py',
           'test/rpcs3_cell569_test.py',
           'test/rpcs3_cell571_test.py',
           'test/rpcs3_cell573_test.py']
# The files the 572 tree pins at the 567 Core commit that 573 replaces.
REPLACED = sorted(p for p in CELL573 if previous.source_of(p) == SOURCE567)
# delivery_contract_memo.py, which the 565 recipe owns, follows HEAD here too.
RECIPE = ['.github/diagnostics/rpcs3cell573_tree.py', '.github/diagnostics/rpcs3cell573_delivery.py',
          '.github/workflows/rpcs3-cell573-delivery.yml', 'build-utils/validate_rpcs3_573_ipa.py',
          'build-utils/validate_liquid_glass573_ipa.py', 'build-utils/validate_melonx_perf573_ipa.py',
          'build-utils/validate_rpcs3_library_files573_ipa.py', 'build-utils/validate_melonx_input573_ipa.py',
          'build-utils/validate_melonx_texture573_ipa.py', 'build-utils/validate_melonx_jit573_ipa.py',
          'build-utils/validate_melonx_switch573_ipa.py', 'build-utils/delivery-573-recipient.pem']
OWNED = previous.OWNED + CELL573 + RECIPE
TREES = previous.TREES
assert REPLACED == sorted(['.github/workflows/rpcs3-core.yml', 'build-utils/build_rpcs3_embedded_core.sh',
                           'build-utils/rpcs3/canonical-source.json', 'build-utils/rpcs3/embedded-core.patch',
                           'test/neo_swap_core_pin_test.py']), REPLACED
# The Core recipe ships nothing.
assert not [p for p in CELL573 if p.split('/')[0] in TREES or p in TREES]
assert not set(CELL573) & set(previous.FIX572)
assert previous.owned('build-utils/delivery_contract_memo.py')


def git(*args, env=None):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True, env=env).strip()


def matches(path, patterns):
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def owned(path):
    return path in CELL573 or matches(path, RECIPE) or previous.owned(path)


def source_of(path):
    """Commit whose version of a file this build carries; None for this
    build's own recipe and for documentation, which follow HEAD."""
    if path in CELL573:
        return None if path.startswith('docs/') else SOURCE573
    if matches(path, RECIPE):
        return None
    return previous.source_of(path)


exists = previous.exists
blob = previous.blob
index_with = previous.index_with


def at_572():
    """{path: commit, or None when absent}: every 573 file at its version in
    the delivered 572 tree, and this recipe removed. Applied to this index it
    gives back the 572 index exactly (docs follow HEAD in both)."""
    versions = {p: None for p in RECIPE}
    for p in CELL573:
        source = previous.source_of(p)
        if source is None:
            versions[p] = git('rev-parse', 'HEAD') if exists('HEAD', p) else None
        else:
            versions[p] = source if exists(source, p) else None
    return versions


def parent_contract():
    """The 573 change is exactly the Core commits since 567: each replaced
    file's 572 version is the 567 Core one, every other 573 file is absent
    from the 572 tree, the only commits that touched a 573 file since 67dd222
    are the 569, 571 and 573 Core commits (each validated by its own Core
    run), and each non-documentation file did change."""
    for p in CELL573:
        if p.startswith('docs/'):
            continue
        before = previous.source_of(p)
        assert before == SOURCE567 if p in REPLACED else not exists(before, p), (p, before)
        assert blob(SOURCE573, p) != (blob(before, p) if before and exists(before, p) else None), (p, 'unchanged')
    commits = git('log', '--format=%H', SOURCE567 + '..' + SOURCE573, '--',
                  *[p for p in CELL573 if not p.startswith('docs/')]).split()
    assert commits[0] == SOURCE573 and len(commits) == len(CORE_COMMITS), commits
    tags = {c[:8]: git('log', '-1', '--format=%s', c) for c in commits}
    assert set(tags) == set(CORE_COMMITS), tags
    for short, tag in CORE_COMMITS.items():
        assert tags[short].endswith(tag), (short, tags[short])
    assert SOURCE571 in commits and SOURCE569 in commits


def verify():
    """The index is the 572 product tree with the 573 files, each from its source.

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
    for p in CELL573:
        if source_of(p):
            assert git('rev-parse', ':' + p) == git('rev-parse', SOURCE573 + ':' + p), p
    return sorted(staged)


def pin(report):
    head = git('rev-parse', 'HEAD')
    parent_contract()
    chain = previous
    for _ in range(11):
        # 572, 567, 566, 565, 564, 563, 562, 561, 560, 559 and 558, each against its own parent.
        chain.parent_contract()
        p558 = chain
        chain = chain.previous
    p567 = previous.previous
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
                    | set(previous.FIX572) | set(CELL573)):
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
    trees572 = product_trees_572()
    # No product tree changes: the Core is built by its own run.
    assert trees == trees572, (trees, trees572)
    receipt = dict(schemaVersion=1, head=head, hostTree=HOST_TREE, source551=SOURCE551, source558=SOURCE558,
                   source559=SOURCE559, source560=SOURCE560, source561=SOURCE561, source562=SOURCE562,
                   source563=SOURCE563, source564=SOURCE564, source565=SOURCE565, source565App=SOURCE565APP,
                   source566=SOURCE566, source567=SOURCE567, source569=SOURCE569, source571=SOURCE571,
                   source572=SOURCE572, source573=SOURCE573, replaced=REPLACED, restored=restored,
                   removed=sorted(removed), keptFiles=kept, productTrees=trees, productTrees572=trees572,
                   reason='The 572 product tree with the RPCS3 Core 573 recipe of 92074e5; each file from the commit that validated it; Git history unchanged.')
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


def tree_572():
    """The delivered 572 tree: the 573 files at their 572 versions, computed in
    a scratch copy of the index, so the pinned index is untouched."""
    with tempfile.TemporaryDirectory() as scratch:
        env = index_with(at_572(), os.path.join(scratch, 'index'))
        return git('write-tree', env=env)


def product_trees_572():
    tree = tree_572()
    return {p: git('rev-parse', tree + ':' + p) for p in TREES}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--pin', action='store_true')
    p.add_argument('--report', default='build/delivery/host-tree573.json')
    a = p.parse_args()
    if a.pin:
        pin(a.report)
    else:
        print(json.dumps(verify(), indent=2))
