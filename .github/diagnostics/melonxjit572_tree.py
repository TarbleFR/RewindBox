"""Private572 delivery tree: the delivered 567 product tree with the MeloNX engine files of 8cc2348.

567 shipped the 566 product (the 565 product with the MeloNX engine of
86c2b4d; God of War III without the 30 fps limiter, MeloNX keyboard and
L3/R3) with the RPCS3 Core 567. 572 keeps all of it and replaces only the
files of the MeloNX engine commit 8cc2348 (this session): the LightningJit
decoder adaptation (a unit also ends at a jump past the other cases of a
switch), the decoder test and its probe, and the simulator smoke homebrew
that executes the new unit end. The engine they describe is built and tested
by its own engine run from 8cc2348. Every file's version before 8cc2348 equals
the 567 pinned one (the 566 engine commit), so the change is exactly that
commit. No file of lib, native, packages, assets or pubspec changes: the
product trees are the delivered 567 ones. The RPCS3 Cores committed after 567
(569, 571) are not part of this build.

Earlier receipts stay bound to the delivered 567 tree, which at_567() gives
back: the 572 files at their 567 versions and this recipe removed. Runner
checkout only: Git history is not changed.
"""
import argparse, fnmatch, json, os, subprocess, tempfile
from pathlib import Path
import rpcs3cell567_tree as previous

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
# The MeloNX engine commit, built and tested by its own engine run.
SOURCE572 = '8cc2348037890adb7b8eef8adde3cd5e4a57c8d2'
ENGINE_COMMITS = [SOURCE572]
SESSION = 'Claude-Session: https://claude.ai/code/session_01K9YJtzFdPCSuLb7YJr2eeo'
FIX572 = ['build-utils/melonx/adapt_jit_decoder.py',
          'test/melonx_jit_decoder/Program.cs',
          'test/melonx_jit_decoder_test.py',
          'test/melonx_runtime_smoke.py']
# The engine's own inputs (hashed by the engine identity as adaptations).
ENGINE572 = ['build-utils/melonx/adapt_jit_decoder.py']
# delivery_contract_memo.py, which the 565 recipe owns, follows HEAD here too.
RECIPE = ['.github/diagnostics/melonxjit572_tree.py', '.github/diagnostics/melonxjit572_delivery.py',
          '.github/workflows/melonx-jit572-delivery.yml', 'build-utils/validate_rpcs3_572_ipa.py',
          'build-utils/validate_liquid_glass572_ipa.py', 'build-utils/validate_melonx_perf572_ipa.py',
          'build-utils/validate_rpcs3_library_files572_ipa.py', 'build-utils/validate_melonx_input572_ipa.py',
          'build-utils/validate_melonx_texture572_ipa.py', 'build-utils/validate_melonx_jit572_ipa.py',
          'build-utils/validate_melonx_switch572_ipa.py', 'build-utils/delivery-572-recipient.pem']
OWNED = previous.OWNED + FIX572 + RECIPE
TREES = previous.TREES
# Every 572 file is one the 566 engine commit validated, which 567 pins.
REPLACED = sorted(p for p in FIX572 if previous.source_of(p) == SOURCE566)
assert REPLACED == sorted(FIX572), REPLACED
# 572 ships no application file: the engine is its only product change.
assert not [p for p in FIX572 if p.startswith(('lib/', 'native/', 'packages/', 'assets/', 'pubspec.'))]
assert not set(FIX572) & set(previous.CELL567)
assert previous.owned('build-utils/delivery_contract_memo.py')


def git(*args, env=None):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True, env=env).strip()


def matches(path, patterns):
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def owned(path):
    return path in FIX572 or matches(path, RECIPE) or previous.owned(path)


def source_of(path):
    """Commit whose version of a file this build carries; None for this
    build's own recipe, which follows HEAD."""
    if path in FIX572:
        return SOURCE572
    if matches(path, RECIPE):
        return None
    return previous.source_of(path)


exists = previous.exists
blob = previous.blob
index_with = previous.index_with


def at_567():
    """{path: commit, or None when absent}: every 572 file at its version in
    the delivered 567 tree, and this recipe removed. Applied to this index it
    gives back the 567 index exactly."""
    versions = {p: None for p in RECIPE}
    for p in FIX572:
        source = previous.source_of(p)
        versions[p] = source if source and exists(source, p) else None
    return versions


def parent_contract():
    """The 572 change is exactly this session's engine commit: each file's
    version before it is the one the 567 tree pins (the 566 engine commit's),
    no other commit touched a 572 file since 86c2b4d, and each file did change."""
    parent = git('rev-parse', SOURCE572 + '^')
    for p in FIX572:
        before = previous.source_of(p)
        assert before == SOURCE566, (p, before)
        assert blob(parent, p) == blob(before, p), (p, before)
        assert blob(SOURCE572, p) != blob(parent, p), (p, 'unchanged')
    commits = git('log', '--format=%H', SOURCE566 + '..' + SOURCE572, '--', *FIX572).split()
    assert commits == ENGINE_COMMITS, commits
    for commit in ENGINE_COMMITS:
        assert SESSION in git('log', '-1', '--format=%B', commit)


def verify():
    """The index is the 567 product tree with the 572 files, each from its source.

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
    for p in FIX572:
        assert git('rev-parse', ':' + p) == git('rev-parse', SOURCE572 + ':' + p), p
    return sorted(staged)


def pin(report):
    head = git('rev-parse', 'HEAD')
    parent_contract()
    chain = previous
    for _ in range(10):
        # 567, 566, 565, 564, 563, 562, 561, 560, 559 and 558, each against its own parent.
        chain.parent_contract()
        p558 = chain
        chain = chain.previous
    p566 = previous.previous
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
                    | set(p565.CELL565) | set(p565.FIX565) | set(p566.FIX566) | set(previous.CELL567)
                    | set(FIX572)):
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
    trees567 = product_trees_567()
    # No product tree changes: the engine is built from its own run.
    assert trees == trees567, (trees, trees567)
    receipt = dict(schemaVersion=1, head=head, hostTree=HOST_TREE, source551=SOURCE551, source558=SOURCE558,
                   source559=SOURCE559, source560=SOURCE560, source561=SOURCE561, source562=SOURCE562,
                   source563=SOURCE563, source564=SOURCE564, source565=SOURCE565, source565App=SOURCE565APP,
                   source566=SOURCE566, source567=SOURCE567, source572=SOURCE572, replaced=REPLACED,
                   restored=restored, removed=sorted(removed), keptFiles=kept, productTrees=trees,
                   productTrees567=trees567,
                   reason='The 567 product tree with the MeloNX engine files of 8cc2348; each file from the commit that validated it; Git history unchanged.')
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


def tree_567():
    """The delivered 567 tree: the 572 files at their 567 versions, computed in
    a scratch copy of the index, so the pinned index is untouched."""
    with tempfile.TemporaryDirectory() as scratch:
        env = index_with(at_567(), os.path.join(scratch, 'index'))
        return git('write-tree', env=env)


def product_trees_567():
    tree = tree_567()
    return {p: git('rev-parse', tree + ':' + p) for p in TREES}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--pin', action='store_true')
    p.add_argument('--report', default='build/delivery/host-tree572.json')
    a = p.parse_args()
    if a.pin:
        pin(a.report)
    else:
        print(json.dumps(verify(), indent=2))
