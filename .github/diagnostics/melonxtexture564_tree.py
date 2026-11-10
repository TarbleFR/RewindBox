"""Private564 delivery tree: the delivered 563 product tree with the MeloNX engine files of 876a087.

563 shipped the 562 product (the 561 product with the MeloNX keyboard and
L3/R3 host) with the RPCS3 Core 563. 564 keeps all of it and replaces only the
files of the MeloNX engine commit (876a087, this session): the texture pool
adaptation (descriptors outside the GPU address space are rejected before
being sized or logged), the bounded engine journal and its crash record, the
adaptation registration, their tests, the engine workflow wiring, the
effective-graphics journal receipt that hashes the changed journal, and the
analysis. The engine they describe is built and tested by its own engine run
from 876a087. Every file's version before that commit equals the 563 pinned
one, so the change is exactly it.

Earlier receipts stay bound to the delivered 563 tree, which at_563() gives
back: the 564 files at their 563 versions and this recipe removed (this
build's analysis is absent there). Runner checkout only: Git history is not
changed.
"""
import argparse, fnmatch, json, os, subprocess, tempfile
from pathlib import Path
import rpcs3cell563_tree as previous

ROOT = Path(__file__).resolve().parents[2]
HOST_TREE = previous.HOST_TREE
SOURCE551 = previous.SOURCE551
SOURCE558 = previous.SOURCE558
SOURCE559 = previous.SOURCE559
SOURCE560 = previous.SOURCE560
SOURCE561 = previous.SOURCE561
SOURCE562 = previous.SOURCE562
SOURCE563 = previous.SOURCE563
# The MeloNX engine commit, built and tested by its own engine run.
SOURCE564 = '876a087b536469017f2e71b41c8d4df4643c3976'
FIRST564 = SOURCE564
SESSION = 'Claude-Session: https://claude.ai/code/session_01K9YJtzFdPCSuLb7YJr2eeo'
# This build's analysis follows HEAD; every other file is taken from 876a087.
DOCS564 = ['docs/melonx-texture-journal.md']
FIX564 = ['.github/workflows/melonx-core.yml',
          'build-utils/melonx/adapt_texture_pool.py',
          'build-utils/melonx/prepare_embedded.py',
          'docs/evidence/melonx-effective-graphics-journal.json',
          'docs/melonx-texture-journal.md',
          'native/melonx/EmbeddedLaunchDiagnostics.cs',
          'native/melonx/EmbeddedRuntime.cs',
          'test/melonx_engine_journal_test.py',
          'test/melonx_texture_pool/Program.cs',
          'test/melonx_texture_pool_test.py']
# The engine's own inputs (hashed by the engine identity as adaptations).
ENGINE564 = ['build-utils/melonx/adapt_texture_pool.py', 'build-utils/melonx/prepare_embedded.py',
             'native/melonx/EmbeddedLaunchDiagnostics.cs', 'native/melonx/EmbeddedRuntime.cs']
# The shipped 564 files (lib, native, packages, assets, pubspec): native sources
# compiled into the engine, never into the application itself.
SHIPPED564 = sorted(p for p in FIX564 if p.startswith(('lib/', 'native/', 'packages/', 'assets/', 'pubspec.')))
RECIPE = ['.github/diagnostics/melonxtexture564_tree.py', '.github/diagnostics/melonxtexture564_delivery.py',
          '.github/workflows/melonx-texture564-delivery.yml', 'build-utils/validate_rpcs3_564_ipa.py',
          'build-utils/validate_liquid_glass564_ipa.py', 'build-utils/validate_melonx_perf564_ipa.py',
          'build-utils/validate_rpcs3_library_files564_ipa.py', 'build-utils/validate_melonx_input564_ipa.py',
          'build-utils/validate_melonx_texture564_ipa.py', 'build-utils/delivery-564-recipient.pem']
OWNED = previous.OWNED + FIX564 + RECIPE
TREES = previous.TREES
# Files an earlier recipe pinned that 564 replaces.
REPLACED = sorted(p for p in FIX564 if previous.owned(p))
assert REPLACED == sorted(['build-utils/melonx/prepare_embedded.py', 'docs/evidence/melonx-effective-graphics-journal.json',
                           'native/melonx/EmbeddedRuntime.cs']), REPLACED
assert SHIPPED564 == ['native/melonx/EmbeddedLaunchDiagnostics.cs', 'native/melonx/EmbeddedRuntime.cs']


def git(*args, env=None):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True, env=env).strip()


def matches(path, patterns):
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def owned(path):
    return path in FIX564 or matches(path, RECIPE) or previous.owned(path)


def source_of(path):
    """Commit whose version of a file this build carries; None for this
    build's own recipe and analysis, which follow HEAD."""
    if path in FIX564:
        return None if path in DOCS564 else SOURCE564
    if matches(path, RECIPE):
        return None
    return previous.source_of(path)


exists = previous.exists
blob = previous.blob
index_with = previous.index_with


def at_563():
    """{path: commit, or None when absent}: every 564 file at its version in
    the delivered 563 tree, and this recipe removed. Applied to this index it
    gives back the 563 index exactly (this build's analysis is absent there)."""
    versions = {p: None for p in RECIPE}
    for p in FIX564:
        source = previous.source_of(p)
        versions[p] = source if source and exists(source, p) else None
    return versions


def parent_contract():
    """The 564 change is exactly this session's engine commit: each file's
    version before it is the one the 563 tree pins (absent for the new files),
    no other commit touched a 564 file since, and each non-analysis file did
    change."""
    parent = git('rev-parse', FIRST564 + '^')
    for p in FIX564:
        if p in DOCS564:
            continue
        before = previous.source_of(p)
        assert blob(parent, p) == (blob(before, p) if before and exists(before, p) else None), (p, before)
        assert blob(SOURCE564, p) != blob(parent, p), (p, 'unchanged')
    commits = git('log', '--format=%H', parent + '..' + SOURCE564, '--',
                  *[p for p in FIX564 if p not in DOCS564]).split()
    assert commits == [SOURCE564], commits
    assert SESSION in git('log', '-1', '--format=%B', SOURCE564)


def verify():
    """The index is the 563 product tree with the 564 files, each from its source.

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
    for p in FIX564:
        if source_of(p):
            assert git('rev-parse', ':' + p) == git('rev-parse', SOURCE564 + ':' + p), p
    return sorted(staged)


def pin(report):
    head = git('rev-parse', 'HEAD')
    parent_contract()
    chain = previous
    for _ in range(6):
        # 563, 562, 561, 560, 559 and 558, each against its own parent.
        chain.parent_contract()
        p558 = chain
        chain = chain.previous
    p562 = previous.previous
    p561 = p562.previous
    committed = {p for p in git('diff', '--name-only', HOST_TREE, head).splitlines() if p}
    plan = {}
    for p in sorted(committed | set(p558.UI550) | set(p558.CELL551) | set(p558.FIX552)
                    | set(p558.PARITY) | set(p558.FIX554) | set(p558.FIX557)
                    | set(p558.FIX558) | set(p561.previous.previous.CELL559) | set(p561.previous.CELL560)
                    | set(p561.CELL561) | set(p562.FIX562) | set(previous.CELL563) | set(FIX564)):
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
    trees563 = product_trees_563()
    # Only the native tree changes, and only by the two engine journal sources.
    assert {p for p in TREES if trees[p] != trees563[p]} == {'native'}, (trees, trees563)
    receipt = dict(schemaVersion=1, head=head, hostTree=HOST_TREE, source551=SOURCE551, source558=SOURCE558,
                   source559=SOURCE559, source560=SOURCE560, source561=SOURCE561, source562=SOURCE562,
                   source563=SOURCE563, source564=SOURCE564, replaced=REPLACED, restored=restored,
                   removed=sorted(removed), keptFiles=kept, productTrees=trees, productTrees563=trees563,
                   reason='The 563 product tree with the MeloNX engine files of 876a087; each file from the commit that validated it; Git history unchanged.')
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


def tree_563():
    """The delivered 563 tree: the 564 files at their 563 versions, computed in
    a scratch copy of the index, so the pinned index is untouched."""
    with tempfile.TemporaryDirectory() as scratch:
        env = index_with(at_563(), os.path.join(scratch, 'index'))
        return git('write-tree', env=env)


def product_trees_563():
    tree = tree_563()
    return {p: git('rev-parse', tree + ':' + p) for p in TREES}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--pin', action='store_true')
    p.add_argument('--report', default='build/delivery/host-tree564.json')
    a = p.parse_args()
    if a.pin:
        pin(a.report)
    else:
        print(json.dumps(verify(), indent=2))
