"""Private562 delivery tree: the delivered 561 product tree with the MeloNX keyboard and L3/R3 files of 9b40129.

561 shipped the 560 product (550 interface, 552 launch-crash fix, 553 MeloNX
parity, 554 RPCS3 import, 557 library files, 558 MeloNX measurement) with the
RPCS3 Core 561. 562 keeps all of it and replaces only the files of the MeloNX
user-request commit (9b40129, this session): the host answers the Switch
keyboard (new MeloNXTextInput.swift; MeloNXRuntimeAPI binds the engine's
callback registry; the session view attaches and answers it before every
stop) and the in-game menu toggles Melo-Controller's L3/R3 buttons; two
strings in twelve languages; their test. The engine and the RPCS3 Core 561
are unchanged. Every file's version before that commit equals the 561 pinned
one, so the change is exactly it.

562 replaces three files the 558 recipe pinned (MeloNXRuntimeAPI.swift,
MeloNXMetalSessionViewController.swift, ui-strings.json), which earlier
receipts hash. Those receipts stay bound to the delivered 561 tree, which
at_561() gives back: the 562 files at their 561 versions and this recipe
removed (documentation follows HEAD in both). Runner checkout only: Git
history is not changed.
"""
import argparse, fnmatch, json, os, subprocess, tempfile
from pathlib import Path
import rpcs3cell561_tree as previous

ROOT = Path(__file__).resolve().parents[2]
HOST_TREE = previous.HOST_TREE
SOURCE551 = previous.SOURCE551
SOURCE558 = previous.SOURCE558
SOURCE559 = previous.SOURCE559
SOURCE560 = previous.SOURCE560
SOURCE561 = previous.SOURCE561
# The MeloNX user-request commit, built and tested by its own host run.
SOURCE562 = '9b40129fa188f8e2aa6a35c94abea005406062d3'
FIRST562 = SOURCE562
SESSION = 'Claude-Session: https://claude.ai/code/session_01K9YJtzFdPCSuLb7YJr2eeo'
CLASSES = 'packages/melonx_internal_bridge/ios/Classes/'
FIX562 = ['build-utils/melonx/ui-strings.json',
          CLASSES + 'MeloNXMetalSessionViewController.swift',
          CLASSES + 'MeloNXRuntimeAPI.swift',
          CLASSES + 'MeloNXTextInput.swift',
          'docs/melonx-keyboard562.md',
          'test/melonx_text_input/App.swift',
          'test/melonx_text_input/Doubles.swift',
          'test/melonx_text_input_test.py']
# The shipped 562 files (lib, native, packages, assets, pubspec).
SHIPPED562 = sorted(p for p in FIX562 if p.startswith(('lib/', 'native/', 'packages/', 'assets/', 'pubspec.')))
RECIPE = ['.github/diagnostics/melonxinput562_tree.py', '.github/diagnostics/melonxinput562_delivery.py',
          '.github/workflows/melonx-input562-delivery.yml', 'build-utils/validate_rpcs3_562_ipa.py',
          'build-utils/validate_liquid_glass562_ipa.py', 'build-utils/validate_melonx_perf562_ipa.py',
          'build-utils/validate_rpcs3_library_files562_ipa.py', 'build-utils/validate_melonx_input562_ipa.py',
          'build-utils/delivery-562-recipient.pem']
OWNED = previous.OWNED + FIX562 + RECIPE
TREES = previous.TREES
# Files the 558 recipe pinned that 562 replaces; nothing else of an earlier build.
REPLACED = sorted(set(FIX562) & {p for p in FIX562 if previous.owned(p)})
assert REPLACED == sorted(['build-utils/melonx/ui-strings.json', CLASSES + 'MeloNXMetalSessionViewController.swift',
                           CLASSES + 'MeloNXRuntimeAPI.swift']), REPLACED
assert all(previous.source_of(p) == SOURCE558 for p in REPLACED)
assert SHIPPED562 == sorted(p for p in FIX562 if p.startswith(CLASSES))


def git(*args, env=None):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True, env=env).strip()


def matches(path, patterns):
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def owned(path):
    return path in FIX562 or matches(path, RECIPE) or previous.owned(path)


def source_of(path):
    """Commit whose version of a file this build carries; None for this
    build's own recipe and for documentation, which follow HEAD."""
    if path in FIX562:
        return None if path.startswith('docs/') else SOURCE562
    if matches(path, RECIPE):
        return None
    return previous.source_of(path)


exists = previous.exists
blob = previous.blob
index_with = previous.index_with


def at_561():
    """{path: commit, or None when absent}: every 562 file at its version in
    the delivered 561 tree, and this recipe removed. Applied to this index it
    gives back the 561 index exactly (docs an earlier recipe owns follow HEAD
    in both; this build's own documentation is absent from the 561 tree)."""
    versions = {p: None for p in RECIPE}
    for p in FIX562:
        source = previous.source_of(p)
        if p.startswith('docs/') and previous.owned(p):
            # Documentation an earlier recipe owns follows HEAD in both trees.
            versions[p] = git('rev-parse', 'HEAD') if exists('HEAD', p) else None
        else:
            versions[p] = source if exists(source, p) else None
    return versions


def parent_contract():
    """The 562 change is exactly this session's commit: each file's version
    before it is the one the 561 tree pins (absent for the new files), every
    commit that touched a 562 file since is this session's, and each shipped
    or test file did change."""
    parent = git('rev-parse', FIRST562 + '^')
    for p in FIX562:
        if p.startswith('docs/'):
            continue
        before = previous.source_of(p)
        assert blob(parent, p) == (blob(before, p) if before else None), (p, before)
        assert blob(SOURCE562, p) != blob(parent, p), (p, 'unchanged')
    commits = git('log', '--format=%H', parent + '..' + SOURCE562, '--',
                  *[p for p in FIX562 if not p.startswith('docs/')]).split()
    assert commits == [SOURCE562], commits
    assert SESSION in git('log', '-1', '--format=%B', SOURCE562)


def verify():
    """The index is the 561 product tree with the 562 files, each from its source.

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
    for p in FIX562:
        if source_of(p):
            assert git('rev-parse', ':' + p) == git('rev-parse', SOURCE562 + ':' + p), p
    return sorted(staged)


def pin(report):
    head = git('rev-parse', 'HEAD')
    parent_contract()
    previous.parent_contract()
    previous.previous.parent_contract()
    previous.previous.previous.parent_contract()
    previous.previous.previous.previous.parent_contract()
    p558 = previous.previous.previous.previous
    committed = {p for p in git('diff', '--name-only', HOST_TREE, head).splitlines() if p}
    plan = {}
    for p in sorted(committed | set(p558.UI550) | set(p558.CELL551) | set(p558.FIX552)
                    | set(p558.PARITY) | set(p558.FIX554) | set(p558.FIX557)
                    | set(p558.FIX558) | set(previous.previous.previous.CELL559) | set(previous.previous.CELL560)
                    | set(previous.CELL561) | set(FIX562)):
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
    trees561 = product_trees_561()
    # Only the packages tree changes, and only by the shipped 562 files.
    assert {p for p in TREES if trees[p] != trees561[p]} == {'packages'}, (trees, trees561)
    receipt = dict(schemaVersion=1, head=head, hostTree=HOST_TREE, source551=SOURCE551, source558=SOURCE558,
                   source559=SOURCE559, source560=SOURCE560, source561=SOURCE561, source562=SOURCE562, replaced=REPLACED,
                   restored=restored, removed=sorted(removed), keptFiles=kept, productTrees=trees,
                   productTrees561=trees561,
                   reason='The 561 product tree with the MeloNX keyboard and L3/R3 files of 9b40129; each file from the commit that validated it; Git history unchanged.')
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


def tree_561():
    """The delivered 561 tree: the 562 files at their 561 versions, computed in
    a scratch copy of the index, so the pinned index is untouched."""
    with tempfile.TemporaryDirectory() as scratch:
        env = index_with(at_561(), os.path.join(scratch, 'index'))
        return git('write-tree', env=env)


def product_trees_561():
    tree = tree_561()
    return {p: git('rev-parse', tree + ':' + p) for p in TREES}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--pin', action='store_true')
    p.add_argument('--report', default='build/delivery/host-tree562.json')
    a = p.parse_args()
    if a.pin:
        pin(a.report)
    else:
        print(json.dumps(verify(), indent=2))
