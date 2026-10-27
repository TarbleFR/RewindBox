"""Private566 delivery tree: the delivered 564 product tree with the MeloNX engine files of 86c2b4d.

564 shipped the 563 product with the MeloNX engine of 876a087. 566 keeps all
of it and replaces only the files of the MeloNX engine commits b4e81d5 and
86c2b4d (this session; the second only corrects the decoder test's comparison
of host code sizes): the LightningJit decoder adaptation (translation units end after a
trap and where the next function starts), the GC adaptation (ConserveMemory
9 -> 5), their registration, the decoder test and its probe, the simulator
smoke homebrew that executes the new unit ends, the engine workflow wiring,
and the analysis. The engine they describe is built and tested by its own
engine run from 86c2b4d. Every file's version before b4e81d5 equals the 564
pinned one, so the change is exactly those two commits. No file of lib, native, packages,
assets or pubspec changes: the product trees are the delivered 564 ones.

Earlier receipts stay bound to the delivered 564 tree, which at_564() gives
back: the 566 files at their 564 versions and this recipe removed (this
build's analysis is absent there). Runner checkout only: Git history is not
changed.
"""
import argparse, fnmatch, json, os, subprocess, tempfile
from pathlib import Path
import melonxtexture564_tree as previous

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
# The MeloNX engine commits; the last is built and tested by its own engine run.
FIRST566 = 'b4e81d5ff1114c5ad2eae52924848d0ade45d88d'
SOURCE566 = '86c2b4dc4c2239bdae427e1725ca557a2b400f99'
ENGINE_COMMITS = [SOURCE566, FIRST566]
SESSION = previous.SESSION
# This build's analysis follows HEAD; every other file is taken from 86c2b4d.
DOCS566 = ['docs/melonx-jit-gc-566.md']
FIX566 = ['.github/workflows/melonx-core.yml',
          'build-utils/melonx/adapt_gc.py',
          'build-utils/melonx/adapt_jit_decoder.py',
          'build-utils/melonx/prepare_embedded.py',
          'docs/melonx-jit-gc-566.md',
          'test/melonx_jit_decoder/Program.cs',
          'test/melonx_jit_decoder_test.py',
          'test/melonx_runtime_smoke.py']
# The engine's own inputs (hashed by the engine identity as adaptations).
ENGINE566 = ['build-utils/melonx/adapt_gc.py', 'build-utils/melonx/adapt_jit_decoder.py',
             'build-utils/melonx/prepare_embedded.py']
RECIPE = ['.github/diagnostics/melonxjit566_tree.py', '.github/diagnostics/melonxjit566_delivery.py',
          '.github/workflows/melonx-jit566-delivery.yml', 'build-utils/validate_rpcs3_566_ipa.py',
          'build-utils/validate_liquid_glass566_ipa.py', 'build-utils/validate_melonx_perf566_ipa.py',
          'build-utils/validate_rpcs3_library_files566_ipa.py', 'build-utils/validate_melonx_input566_ipa.py',
          'build-utils/validate_melonx_texture566_ipa.py', 'build-utils/validate_melonx_jit566_ipa.py',
          'build-utils/delivery-566-recipient.pem']
OWNED = previous.OWNED + FIX566 + RECIPE
TREES = previous.TREES
# Files an earlier recipe pinned that 566 replaces.
REPLACED = sorted(p for p in FIX566 if previous.owned(p))
assert REPLACED == sorted(['.github/workflows/melonx-core.yml', 'build-utils/melonx/prepare_embedded.py',
                           'test/melonx_runtime_smoke.py']), REPLACED
# 566 ships no application file: the engine is its only product change.
assert not [p for p in FIX566 if p.startswith(('lib/', 'native/', 'packages/', 'assets/', 'pubspec.'))]


def git(*args, env=None):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True, env=env).strip()


def matches(path, patterns):
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def owned(path):
    return path in FIX566 or matches(path, RECIPE) or previous.owned(path)


def source_of(path):
    """Commit whose version of a file this build carries; None for this
    build's own recipe and analysis, which follow HEAD."""
    if path in FIX566:
        return None if path in DOCS566 else SOURCE566
    if matches(path, RECIPE):
        return None
    return previous.source_of(path)


exists = previous.exists
blob = previous.blob
index_with = previous.index_with


def at_564():
    """{path: commit, or None when absent}: every 566 file at its version in
    the delivered 564 tree, and this recipe removed. Applied to this index it
    gives back the 564 index exactly (this build's analysis is absent there)."""
    versions = {p: None for p in RECIPE}
    for p in FIX566:
        source = previous.source_of(p)
        versions[p] = source if source and exists(source, p) else None
    return versions


def parent_contract():
    """The 566 change is exactly this session's two engine commits: each
    file's version before them is the one the 564 tree pins (absent for the new
    files), no other commit touched a 566 file since, and each non-analysis file
    did change."""
    parent = git('rev-parse', FIRST566 + '^')
    for p in FIX566:
        if p in DOCS566:
            continue
        before = previous.source_of(p)
        assert blob(parent, p) == (blob(before, p) if before and exists(before, p) else None), (p, before)
        assert blob(SOURCE566, p) != blob(parent, p), (p, 'unchanged')
    commits = git('log', '--format=%H', parent + '..' + SOURCE566, '--',
                  *[p for p in FIX566 if p not in DOCS566]).split()
    assert commits == ENGINE_COMMITS, commits
    for commit in ENGINE_COMMITS:
        assert SESSION in git('log', '-1', '--format=%B', commit)


def verify():
    """The index is the 564 product tree with the 566 files, each from its source.

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
    for p in FIX566:
        if source_of(p):
            assert git('rev-parse', ':' + p) == git('rev-parse', SOURCE566 + ':' + p), p
    return sorted(staged)


def pin(report):
    head = git('rev-parse', 'HEAD')
    parent_contract()
    chain = previous
    for _ in range(7):
        # 564, 563, 562, 561, 560, 559 and 558, each against its own parent.
        chain.parent_contract()
        p558 = chain
        chain = chain.previous
    p563 = previous.previous
    p562 = p563.previous
    p561 = p562.previous
    committed = {p for p in git('diff', '--name-only', HOST_TREE, head).splitlines() if p}
    plan = {}
    for p in sorted(committed | set(p558.UI550) | set(p558.CELL551) | set(p558.FIX552)
                    | set(p558.PARITY) | set(p558.FIX554) | set(p558.FIX557)
                    | set(p558.FIX558) | set(p561.previous.previous.CELL559) | set(p561.previous.CELL560)
                    | set(p561.CELL561) | set(p562.FIX562) | set(p563.CELL563) | set(previous.FIX564)
                    | set(FIX566)):
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
    trees564 = product_trees_564()
    # No product tree changes: the engine is built from its own run.
    assert trees == trees564, (trees, trees564)
    receipt = dict(schemaVersion=1, head=head, hostTree=HOST_TREE, source551=SOURCE551, source558=SOURCE558,
                   source559=SOURCE559, source560=SOURCE560, source561=SOURCE561, source562=SOURCE562,
                   source563=SOURCE563, source564=SOURCE564, source566=SOURCE566, replaced=REPLACED,
                   restored=restored, removed=sorted(removed), keptFiles=kept, productTrees=trees,
                   productTrees564=trees564,
                   reason='The 564 product tree with the MeloNX engine files of 86c2b4d; each file from the commit that validated it; Git history unchanged.')
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


def tree_564():
    """The delivered 564 tree: the 566 files at their 564 versions, computed in
    a scratch copy of the index, so the pinned index is untouched."""
    with tempfile.TemporaryDirectory() as scratch:
        env = index_with(at_564(), os.path.join(scratch, 'index'))
        return git('write-tree', env=env)


def product_trees_564():
    tree = tree_564()
    return {p: git('rev-parse', tree + ':' + p) for p in TREES}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--pin', action='store_true')
    p.add_argument('--report', default='build/delivery/host-tree566.json')
    a = p.parse_args()
    if a.pin:
        pin(a.report)
    else:
        print(json.dumps(verify(), indent=2))
