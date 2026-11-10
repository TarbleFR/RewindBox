"""Private552 delivery tree: the validated 551 product tree with the MeloNX standalone-parity files of 62626c0.

551 shipped the 550 product tree (546 delivery tree, RPCS3 547 Core, MeloNX
threading and FPS counter, e12f1d4 interface) with the RPCS3 551 files of
4e5bf59. 552 keeps all of that and adds only the files of the MeloNX parity
commit (62626c0): selectable MoltenVK (the standalone app's own binary by
default), the stderr journal, Game Mode, the present target, the engine
options journal and the threading import fix. Every 62626c0 file's parent
version equals the 551 pinned one, so the change is exactly that commit.
Runner checkout only: Git history is not changed.
"""
import argparse, fnmatch, json, os, shutil, subprocess, tempfile
from pathlib import Path
import rpcs3cell551_tree as previous

ROOT = Path(__file__).resolve().parents[2]
HOST_TREE = previous.HOST_TREE
SOURCE_UI = previous.SOURCE_UI
SOURCE551 = previous.SOURCE551
SOURCE552 = '62626c0fa0263c8ce29671bf060c9bc7d746c1a0'
PARITY552 = ['build-utils/configure_melonx_ios.py', 'build-utils/melonx/build_core.sh',
             'build-utils/melonx/package_standalone_moltenvk.py', 'build-utils/melonx/ui-strings.json',
             'docs/evidence/melonx-effective-graphics-journal.json', 'docs/melonx-persona-performance-2026-10-25.md',
             'lib/services/melonx_internal_service.dart', 'native/melonx/EmbeddedGraphicsSettings.cs',
             'native/melonx/EmbeddedNativeLibraries.cs', 'native/melonx/EmbeddedPerformance.cs',
             'native/melonx/EmbeddedRuntime.cs', 'native/melonx/EmbeddedSession.cs',
             'packages/melonx_internal_bridge/ios/Classes/MeloNXInternalBridgePlugin.swift',
             'packages/melonx_internal_bridge/ios/Classes/MeloNXMetalSessionViewController.swift',
             'packages/melonx_internal_bridge/ios/Classes/MeloNXRuntimeAPI.swift',
             'packages/melonx_internal_bridge/ios/Classes/MeloNXSessionABI.h',
             'packages/melonx_internal_bridge/ios/Classes/MeloNXStandaloneParity.swift',
             'test/melonx_display_native_test.py', 'test/melonx_effective_graphics_journal_test.py',
             'test/melonx_standalone_parity_test.py', 'test/melonx_threading549_test.dart']
# The shipped 552 files (lib, native, packages, assets, pubspec).
SHIPPED552 = sorted(p for p in PARITY552 if p.startswith(('lib/', 'native/', 'packages/', 'assets/', 'pubspec.')))
LOCAL = 'docs/evidence/melonx-parity552-local.json'
RECIPE = ['.github/diagnostics/melonxparity552_tree.py', '.github/diagnostics/melonxparity552_delivery.py',
          '.github/workflows/melonx-parity552-delivery.yml', 'build-utils/validate_melonx_parity552_ipa.py',
          'build-utils/validate_liquid_glass552_ipa.py', 'build-utils/delivery-552-recipient.pem', LOCAL]
OWNED = previous.OWNED + PARITY552 + RECIPE
TREES = previous.TREES


def git(*args, env=None):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True, env=env).strip()


def matches(path, patterns):
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def owned(path):
    return path in PARITY552 or matches(path, RECIPE) or previous.owned(path)


def source_of(path):
    """Commit whose version of a file this build carries; None for this
    build's own recipe and for documentation, which follow HEAD."""
    if path in PARITY552:
        return None if path == 'docs/melonx-persona-performance-2026-10-25.md' else SOURCE552
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
    for p in previous.SHIPPED551:
        assert git('rev-parse', ':' + p) == git('rev-parse', SOURCE551 + ':' + p), p
    for p in PARITY552:
        if source_of(p):
            assert git('rev-parse', ':' + p) == git('rev-parse', SOURCE552 + ':' + p), p
    return sorted(staged)


def pin(report):
    head = git('rev-parse', 'HEAD')
    committed = {p for p in git('diff', '--name-only', HOST_TREE, head).splitlines() if p}
    plan = {}
    for p in sorted(committed | set(previous.previous.UI) | set(previous.CELL551) | set(PARITY552)):
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
                   reason='The 551 product tree with the MeloNX parity files of 62626c0; each file from the commit that validated it; Git history unchanged.')
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


def trees_with(versions):
    """The shipped trees with some files put back to {path: commit or None (absent)}.

    Computed in a scratch copy of the index, so the pinned index is untouched.
    """
    with tempfile.TemporaryDirectory() as scratch:
        index = os.path.join(scratch, 'index')
        shutil.copy2(git('rev-parse', '--path-format=absolute', '--git-path', 'index'), index)
        env = dict(os.environ, GIT_INDEX_FILE=index)
        for p, source in sorted(versions.items()):
            if source is None or not exists(source, p):
                git('update-index', '--force-remove', '--', p, env=env)
                continue
            mode, kind, blob = git('ls-tree', source, '--', p).split('\t')[0].split()
            git('update-index', '--add', '--cacheinfo', f'{mode},{blob},{p}', env=env)
        tree = git('write-tree', env=env)
    return {p: git('rev-parse', tree + ':' + p) for p in TREES}


def product_trees_551():
    """The trees with the shipped 552 files at their 551 versions: the 551 product tree."""
    return trees_with({p: previous.source_of(p) or HOST_TREE for p in SHIPPED552})


def product_trees_550():
    """The trees with the shipped 551 and 552 files at their 550 versions.

    Equal to the trees the 550 interface and MeloNX receipts were bound to; the
    551 files go back as 551 put them back, and 551 did not touch the 552 files.
    """
    versions = {p: previous.previous.source_of(p) or HOST_TREE for p in SHIPPED552}
    versions.update({p: previous.previous.source_of(p) for p in previous.SHIPPED551})
    return trees_with(versions)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--pin', action='store_true')
    p.add_argument('--report', default='build/delivery/host-tree552.json')
    a = p.parse_args()
    if a.pin:
        pin(a.report)
    else:
        print(json.dumps(verify(), indent=2))
