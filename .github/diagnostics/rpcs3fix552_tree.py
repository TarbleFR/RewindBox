"""Private552 delivery tree: the validated 551 product tree with the crash fix of 6b527ca.

551 shipped the 550 product tree with the RPCS3 551 files of 4e5bf59 (Core,
timeline logger, game profiles). Every 551 launch the maintainer tried
crashed within 0.4 s of boot return. 552 keeps all of 551 and replaces only
the files of the fix commit (6b527ca): the game profiles (Dragon Ball Z
without a title profile, God of War III with synchronous MoltenVK submits
and without asynchronous texture streaming), the timeline logger (core_log
lines written before returning, so a fatal line precedes the abort), their
tests and the analysis. The two shipped files are the two shipped 551 files;
the Core is the 551 one. Runner checkout only: Git history is not changed.
"""
import argparse, fnmatch, json, os, shutil, subprocess, tempfile
from pathlib import Path
import rpcs3cell551_tree as previous

ROOT = Path(__file__).resolve().parents[2]
HOST_TREE = previous.HOST_TREE
SOURCE_UI = previous.SOURCE_UI
SOURCE551 = previous.SOURCE551
SOURCE552 = '6b527cae4d07b8e43d1bb6b4d2fca618eb3ecdb5'
FIX552 = ['docs/rpcs3-crash552.md', 'lib/services/rpcs3_game_profile_service.dart',
          'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3Diagnostics.mm', 'test/native/rpcs3_cell551.inc',
          'test/native/rpcs3_core_log_durable552_test.mm', 'test/rpcs3_core_log_durable552_test.py',
          'test/rpcs3_game_profile_service_test.dart']
# The shipped 552 files (lib, native, packages, assets, pubspec): the 551 ones.
SHIPPED552 = sorted(p for p in FIX552 if p.startswith(('lib/', 'native/', 'packages/', 'assets/', 'pubspec.')))
assert SHIPPED552 == previous.SHIPPED551, SHIPPED552
RECIPE = ['.github/diagnostics/rpcs3fix552_tree.py', '.github/diagnostics/rpcs3fix552_delivery.py',
          '.github/workflows/rpcs3-fix552-delivery.yml', 'build-utils/validate_rpcs3_552_ipa.py',
          'build-utils/validate_liquid_glass_fix552_ipa.py', 'build-utils/validate_melonx_threading552_ipa.py',
          'build-utils/delivery-552-rpcs3-recipient.pem', 'docs/evidence/rpcs3-fix552-local.json']
OWNED = previous.OWNED + FIX552 + RECIPE
TREES = previous.TREES


def git(*args, env=None):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True, env=env).strip()


def matches(path, patterns):
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def owned(path):
    return path in FIX552 or matches(path, RECIPE) or previous.owned(path)


def source_of(path):
    """Commit whose version of a file this build carries; None for this
    build's own recipe and for documentation, which follow HEAD."""
    if path in FIX552:
        return None if path.startswith('docs/') else SOURCE552
    if matches(path, RECIPE):
        return None
    return previous.source_of(path)


def exists(commit, path):
    return bool(git('ls-tree', commit, '--', path))


def verify():
    """The index is the 551 product tree plus the 552 files, each from its source.

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
    for p in previous.previous.UI:
        assert git('rev-parse', ':' + p) == git('rev-parse', SOURCE_UI + ':' + p), p
    for p in previous.CELL551:
        source = source_of(p)
        if source:
            assert git('rev-parse', ':' + p) == git('rev-parse', source + ':' + p), p
    for p in FIX552:
        if source_of(p):
            assert git('rev-parse', ':' + p) == git('rev-parse', SOURCE552 + ':' + p), p
    return sorted(staged)


def pin(report):
    head = git('rev-parse', 'HEAD')
    committed = {p for p in git('diff', '--name-only', HOST_TREE, head).splitlines() if p}
    plan = {}
    for p in sorted(committed | set(previous.previous.UI) | set(previous.CELL551) | set(FIX552)):
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
    receipt = dict(schemaVersion=1, head=head, hostTree=HOST_TREE, source547=previous.previous.SOURCE547,
                   source548=previous.previous.SOURCE548, source549=previous.previous.SOURCE549, sourceInterface=SOURCE_UI,
                   source551=SOURCE551, source552=SOURCE552, restored=restored, removed=sorted(removed), keptFiles=kept,
                   productTrees=product_trees(), productTrees551=product_trees_551(), productTrees550=product_trees_550(),
                   reason='The 551 product tree with the crash-fix files of 6b527ca; each file from the commit that validated it; Git history unchanged.')
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


def _trees_with(versions):
    """The pinned trees with some shipped files put back to other commits,
    computed in a scratch copy of the index."""
    with tempfile.TemporaryDirectory() as scratch:
        index = os.path.join(scratch, 'index')
        shutil.copy2(git('rev-parse', '--path-format=absolute', '--git-path', 'index'), index)
        env = dict(os.environ, GIT_INDEX_FILE=index)
        for p, source in versions.items():
            mode, kind, blob = git('ls-tree', source, '--', p).split('\t')[0].split()
            git('update-index', '--cacheinfo', f'{mode},{blob},{p}', env=env)
        tree = git('write-tree', env=env)
    return {p: git('rev-parse', tree + ':' + p) for p in TREES}


def product_trees_551():
    """The trees with the shipped 552 files put back to their 551 versions:
    equal to the trees build 551 shipped (its delivery receipt)."""
    return _trees_with({p: SOURCE551 for p in SHIPPED552})


def product_trees_550():
    """The trees with the shipped files put back to their 550 versions: equal
    to the trees the 550 interface and MeloNX receipts were bound to."""
    return _trees_with({p: previous.previous.source_of(p) for p in SHIPPED552})


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--pin', action='store_true')
    p.add_argument('--report', default='build/delivery/host-tree552.json')
    a = p.parse_args()
    if a.pin:
        pin(a.report)
    else:
        print(json.dumps(verify(), indent=2))
