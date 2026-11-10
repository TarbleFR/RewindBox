"""Private567 delivery tree: the delivered 566 product tree with the RPCS3 Core 567 recipe of 67dd222.

566 shipped the 565 product (the 564 product with the RPCS3 Core 565 and the
God of War III profile without the 30 fps limiter) with the MeloNX engine of
86c2b4d. 567 keeps every shipped file of it and replaces only the Core recipe:
the canonical delta, its manifest, the Core build script, the Core pin test
and workflow, and the 567 driver, test, harness and fixture. The Core they
describe (565 with the RSX thread priority and the pooled-worker QoS reset)
is built and tested by its own Core run from 67dd222. The 565 recipe, which
the 566 tree keeps, pins five of these files at 07e416c; the only commit that
changed a 567 file since is 67dd222 (the Core). No file of lib, native,
packages, assets or pubspec changes: the product trees are the delivered 566
ones.

Earlier receipts stay bound to the delivered 566 tree, which at_566() gives
back: the 567 files at their 566 versions and this recipe removed
(documentation follows HEAD in both). Runner checkout only: Git history is
not changed.
"""
import argparse, fnmatch, json, os, subprocess, tempfile
from pathlib import Path
import melonxjit566_tree as previous

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
# The Core commit built and tested by the 567 Core run.
SOURCE567 = '67dd222bdbc8dbfefa6a666560e56672346f1521'
CORE_COMMITS = {'67dd222b': '[rpcs3-cell567-core]'}
CELL567 = ['.github/diagnostics/rpcs3cell567_core.py',
           '.github/workflows/rpcs3-cell567-core.yml',
           '.github/workflows/rpcs3-core.yml',
           'build-utils/build_rpcs3_embedded_core.sh',
           'build-utils/rpcs3/canonical-source.json',
           'build-utils/rpcs3/embedded-core.patch',
           'docs/evidence/rpcs3-cell567-host-linux.json',
           'docs/evidence/rpcs3-cell567-macos.json',
           'docs/rpcs3-cell567.md',
           'test/fixtures/rpcs3_cell567.diff',
           'test/native/rpcs3_thread_qos567.inc',
           'test/neo_swap_core_pin_test.py',
           'test/rpcs3_cell567_test.py']
# The files the 566 tree pins at the 565 Core commit that 567 replaces.
REPLACED = sorted(p for p in CELL567 if previous.source_of(p) == SOURCE565)
# delivery_contract_memo.py, which the 565 recipe owns, follows HEAD here too.
RECIPE = ['.github/diagnostics/rpcs3cell567_tree.py', '.github/diagnostics/rpcs3cell567_delivery.py',
          '.github/workflows/rpcs3-cell567-delivery.yml', 'build-utils/validate_rpcs3_567_ipa.py',
          'build-utils/validate_liquid_glass567_ipa.py', 'build-utils/validate_melonx_perf567_ipa.py',
          'build-utils/validate_rpcs3_library_files567_ipa.py', 'build-utils/validate_melonx_input567_ipa.py',
          'build-utils/validate_melonx_texture567_ipa.py', 'build-utils/validate_melonx_jit567_ipa.py',
          'build-utils/delivery-567-recipient.pem']
OWNED = previous.OWNED + CELL567 + RECIPE
TREES = previous.TREES
assert REPLACED == sorted(['.github/workflows/rpcs3-core.yml', 'build-utils/build_rpcs3_embedded_core.sh',
                           'build-utils/rpcs3/canonical-source.json', 'build-utils/rpcs3/embedded-core.patch',
                           'test/neo_swap_core_pin_test.py']), REPLACED
# The Core recipe ships nothing.
assert not [p for p in CELL567 if p.split('/')[0] in TREES or p in TREES]
assert not set(CELL567) & set(previous.FIX566)
assert previous.owned('build-utils/delivery_contract_memo.py')


def git(*args, env=None):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True, env=env).strip()


def matches(path, patterns):
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def owned(path):
    return path in CELL567 or matches(path, RECIPE) or previous.owned(path)


def source_of(path):
    """Commit whose version of a file this build carries; None for this
    build's own recipe and for documentation, which follow HEAD."""
    if path in CELL567:
        return None if path.startswith('docs/') else SOURCE567
    if matches(path, RECIPE):
        return None
    return previous.source_of(path)


exists = previous.exists
blob = previous.blob
index_with = previous.index_with


def at_566():
    """{path: commit, or None when absent}: every 567 file at its version in
    the delivered 566 tree, and this recipe removed. Applied to this index it
    gives back the 566 index exactly (docs follow HEAD in both)."""
    versions = {p: None for p in RECIPE}
    for p in CELL567:
        source = previous.source_of(p)
        if source is None:
            versions[p] = git('rev-parse', 'HEAD') if exists('HEAD', p) else None
        else:
            versions[p] = source if exists(source, p) else None
    return versions


def parent_contract():
    """The 567 change is exactly the Core commit since 565: each replaced
    file's 566 version is the 565 Core one, the only commit that touched a 567
    file since 07e416c is the 567 Core commit (validated by its own Core run),
    and each non-documentation file did change."""
    for p in CELL567:
        if p.startswith('docs/'):
            continue
        before = previous.source_of(p)
        assert before == SOURCE565 if p in REPLACED else not exists(before, p), (p, before)
        assert blob(SOURCE567, p) != (blob(before, p) if before else None), (p, 'unchanged')
    commits = git('log', '--format=%H', SOURCE565 + '..' + SOURCE567, '--',
                  *[p for p in CELL567 if not p.startswith('docs/')]).split()
    assert commits[0] == SOURCE567 and len(commits) == len(CORE_COMMITS), commits
    tags = {c[:8]: git('log', '-1', '--format=%s', c) for c in commits}
    assert set(tags) == set(CORE_COMMITS), tags
    for short, tag in CORE_COMMITS.items():
        assert tags[short].endswith(tag), (short, tags[short])


def verify():
    """The index is the 566 product tree with the 567 files, each from its source.

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
    for p in CELL567:
        if source_of(p):
            assert git('rev-parse', ':' + p) == git('rev-parse', SOURCE567 + ':' + p), p
    return sorted(staged)


def pin(report):
    head = git('rev-parse', 'HEAD')
    parent_contract()
    chain = previous
    for _ in range(9):
        # 566, 565, 564, 563, 562, 561, 560, 559 and 558, each against its own parent.
        chain.parent_contract()
        p558 = chain
        chain = chain.previous
    p565 = previous.previous
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
                    | set(p565.CELL565) | set(p565.FIX565) | set(previous.FIX566) | set(CELL567)):
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
    trees566 = product_trees_566()
    # No product tree changes: the Core is built by its own run.
    assert trees == trees566, (trees, trees566)
    receipt = dict(schemaVersion=1, head=head, hostTree=HOST_TREE, source551=SOURCE551, source558=SOURCE558,
                   source559=SOURCE559, source560=SOURCE560, source561=SOURCE561, source562=SOURCE562,
                   source563=SOURCE563, source564=SOURCE564, source565=SOURCE565, source565App=SOURCE565APP,
                   source566=SOURCE566, source567=SOURCE567, replaced=REPLACED, restored=restored,
                   removed=sorted(removed), keptFiles=kept, productTrees=trees, productTrees566=trees566,
                   reason='The 566 product tree with the RPCS3 Core 567 recipe of 67dd222; each file from the commit that validated it; Git history unchanged.')
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


def tree_566():
    """The delivered 566 tree: the 567 files at their 566 versions, computed in
    a scratch copy of the index, so the pinned index is untouched."""
    with tempfile.TemporaryDirectory() as scratch:
        env = index_with(at_566(), os.path.join(scratch, 'index'))
        return git('write-tree', env=env)


def product_trees_566():
    tree = tree_566()
    return {p: git('rev-parse', tree + ':' + p) for p in TREES}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--pin', action='store_true')
    p.add_argument('--report', default='build/delivery/host-tree567.json')
    a = p.parse_args()
    if a.pin:
        pin(a.report)
    else:
        print(json.dumps(verify(), indent=2))
