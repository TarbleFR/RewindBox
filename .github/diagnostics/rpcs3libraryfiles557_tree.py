"""Private557 delivery tree: the delivered 554 product tree with the files of the 557 fix (d645f05).

554 shipped the 553 product tree (550 interface, RPCS3 551 Core, 552 launch-
crash fix, 553 MeloNX parity) with the RPCS3 library-file import of 410678b.
557 keeps all of it and replaces only the files of the fix commit (d645f05):
the ROM folder saves are queued (UNIQUE constraint failed:
user_rom_folders.path), the search screen shows no error for a declined
installation, a disc RPCS3 installed keeps its row and launches by title
ID once its own file is deleted, the installation can free the original's
space, and deleting a library-folder disc removes its file, its key and
RPCS3's copy; their tests and the analysis. Every file's parent version
(b58c7b1) equals the 554 pinned one, so the change is exactly that commit.

Unlike 554, 557 changes files earlier builds shipped or hashed: one
interface file of 550 (search_screen.dart), eight files of 554 (five shipped
Dart files, three tests) and sqlite_service.dart, an input of the 550 and
MeloNX receipts. Those receipts stay bound to the delivered 554 tree, which
this index gives back with the 557 files at their 554 versions and this
recipe removed (at_554; documentation follows HEAD in both). Runner checkout
only: Git history is not changed.
"""
import argparse, fnmatch, json, os, shutil, subprocess, tempfile
from pathlib import Path
import rpcs3import554_tree as previous

ROOT = Path(__file__).resolve().parents[2]
HOST_TREE = previous.HOST_TREE
SOURCE_UI = previous.SOURCE_UI
SOURCE551 = previous.SOURCE551
SOURCE552 = previous.SOURCE552
SOURCE_PARITY = previous.SOURCE_PARITY
SOURCE_HOST = previous.SOURCE_HOST
SOURCE_DART = previous.SOURCE_DART
SOURCE554 = previous.SOURCE554
SOURCE557 = 'd645f05cf0af4e2052038fee361148b54f8eac6a'
FIX557 = ['docs/rpcs3-library-files557.md',
          'lib/data/datasources/sqlite_database_service.dart',
          'lib/data/datasources/sqlite_service.dart',
          'lib/l10n/rpcs3_library_file_locale.dart',
          'lib/repositories/game_repository.dart',
          'lib/screens/search_screen/search_screen.dart',
          'lib/services/game/game_launch_service.dart',
          'lib/services/rpcs3_library_file_deletion.dart',
          'lib/services/rpcs3_library_file_service.dart',
          'lib/services/rpcs3_library_service.dart',
          'lib/widgets/rpcs3_library_file_install_dialog.dart',
          'lib/widgets/rpcs3_multi_delete_dialog.dart',
          'test/retroarch_baseline_scope_test.py',
          'test/rom_folders_concurrent_save_test.dart',
          'test/rpcs3_library_file_dialog_test.dart',
          'test/rpcs3_library_file_route_contract_test.py',
          'test/rpcs3_library_file_rows_test.dart',
          'test/rpcs3_library_file_service_test.dart']
# The shipped 557 files (lib, native, packages, assets, pubspec).
SHIPPED557 = sorted(p for p in FIX557 if p.startswith(('lib/', 'native/', 'packages/', 'assets/', 'pubspec.')))
LOCAL = 'docs/evidence/rpcs3-library-files557-local.json'
RECIPE = ['.github/diagnostics/rpcs3libraryfiles557_tree.py', '.github/diagnostics/rpcs3libraryfiles557_delivery.py',
          '.github/workflows/rpcs3-library-files557-delivery.yml', 'build-utils/validate_rpcs3_library_files557_ipa.py',
          'build-utils/validate_liquid_glass557_ipa.py',
          'build-utils/validate_melonx_parity557_ipa.py', 'build-utils/delivery-557-rpcs3-recipient.pem', LOCAL]
OWNED = previous.OWNED + FIX557 + RECIPE
# Files an earlier private build shipped or pinned that 557 replaces: the 550
# search screen and eight 554 files. Nothing of 551, 552 or 553 changes.
REPLACED = sorted(set(FIX557) & set(previous.OWNED))
UI550 = previous.previous.previous.previous.previous.UI
assert set(REPLACED) == ({'lib/screens/search_screen/search_screen.dart'} | (set(FIX557) & set(previous.FIX554))), REPLACED
assert not set(FIX557) & (set(previous.previous.PARITY) | set(previous.previous.previous.FIX552)
                          | set(previous.previous.previous.previous.CELL551))
TREES = previous.TREES


def git(*args, env=None):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True, env=env).strip()


def matches(path, patterns):
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def owned(path):
    return path in FIX557 or matches(path, RECIPE) or previous.owned(path)


def source_of(path):
    """Commit whose version of a file this build carries; None for this
    build's own recipe and for documentation, which follow HEAD."""
    if path in FIX557:
        return None if path.startswith('docs/') else SOURCE557
    if matches(path, RECIPE):
        return None
    return previous.source_of(path)


def exists(commit, path):
    return bool(git('ls-tree', commit, '--', path))


def blob(commit, path):
    return git('rev-parse', commit + ':' + path) if exists(commit, path) else None


def at_554():
    """{path: commit, or None when absent}: every 557 file at its version in
    the delivered 554 tree, and this recipe removed. Applied to this index it
    gives back the 554 index exactly (docs follow HEAD in both)."""
    versions = {p: None for p in RECIPE}
    for p in FIX557:
        source = previous.source_of(p)
        if source is None:
            # Documentation the 554 recipe owned follows HEAD there too.
            versions[p] = git('rev-parse', 'HEAD') if exists('HEAD', p) else None
        else:
            versions[p] = source if exists(source, p) else None
    return versions


def parent_contract():
    """The 557 change is exactly the fix commit: each file's version before it
    (b58c7b1) is the one the 554 tree pins."""
    parent = git('rev-parse', SOURCE557 + '^')
    for p in FIX557:
        if p.startswith('docs/'):
            continue
        before = previous.source_of(p)
        assert blob(parent, p) == (blob(before, p) if before else None), (p, before)
    changed = {p for p in git('diff-tree', '--no-commit-id', '--name-only', '-r', SOURCE557).split()}
    assert changed == set(FIX557), changed ^ set(FIX557)


def verify():
    """The index is the 554 product tree with the 557 files, each from its source.

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
    # Every file of the earlier builds keeps its pinned version unless 557 replaces it.
    for p in UI550:
        assert git('rev-parse', ':' + p) == git('rev-parse', (SOURCE557 if p in FIX557 else SOURCE_UI) + ':' + p), p
    for p in previous.previous.previous.SHIPPED552:
        assert git('rev-parse', ':' + p) == git('rev-parse', SOURCE552 + ':' + p), p
    for p in previous.previous.PARITY:
        if previous.previous.source_of(p):
            assert git('rev-parse', ':' + p) == git('rev-parse', previous.previous.source_of(p) + ':' + p), p
    for p in previous.FIX554:
        source = source_of(p)
        if source:
            assert source == (SOURCE557 if p in FIX557 else SOURCE554), p
            assert git('rev-parse', ':' + p) == git('rev-parse', source + ':' + p), p
    for p in FIX557:
        if source_of(p):
            assert git('rev-parse', ':' + p) == git('rev-parse', SOURCE557 + ':' + p), p
    return sorted(staged)


def pin(report):
    head = git('rev-parse', 'HEAD')
    parent_contract()
    committed = {p for p in git('diff', '--name-only', HOST_TREE, head).splitlines() if p}
    plan = {}
    cell551 = previous.previous.previous.previous.CELL551
    for p in sorted(committed | set(UI550) | set(cell551) | set(previous.previous.previous.FIX552)
                    | set(previous.previous.PARITY) | set(previous.FIX554) | set(FIX557)):
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
    ui = previous.previous.previous.previous.previous
    receipt = dict(schemaVersion=1, head=head, hostTree=HOST_TREE, source547=ui.SOURCE547,
                   source548=ui.SOURCE548, source549=ui.SOURCE549, sourceInterface=SOURCE_UI, source551=SOURCE551,
                   source552=SOURCE552, sourceParity=SOURCE_PARITY, sourceHost=SOURCE_HOST, sourceDart=SOURCE_DART,
                   source554=SOURCE554, source557=SOURCE557, replaced=REPLACED, restored=restored,
                   removed=sorted(removed), keptFiles=kept, productTrees=product_trees(),
                   productTrees554=product_trees_554(),
                   reason='The 554 product tree with the 557 fix files of d645f05; each file from the commit that validated it; Git history unchanged.')
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


def index_with(versions, index):
    """Writes into the scratch index [index] (a copy of the current one) the
    files of {path: commit or None (absent)}."""
    shutil.copy2(git('rev-parse', '--path-format=absolute', '--git-path', 'index'), index)
    env = dict(os.environ, GIT_INDEX_FILE=index)
    for p, source in sorted(versions.items()):
        if source is None or not exists(source, p):
            git('update-index', '--force-remove', '--', p, env=env)
            continue
        mode, kind, sha = git('ls-tree', source, '--', p).split('\t')[0].split()
        git('update-index', '--add', '--cacheinfo', f'{mode},{sha},{p}', env=env)
    return env


def product_trees_554():
    """The 557 files at their 554 versions: the delivered 554 product tree.

    Computed in a scratch copy of the index, so the pinned index is untouched.
    """
    with tempfile.TemporaryDirectory() as scratch:
        env = index_with(at_554(), os.path.join(scratch, 'index'))
        tree = git('write-tree', env=env)
    return {p: git('rev-parse', tree + ':' + p) for p in TREES}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--pin', action='store_true')
    p.add_argument('--report', default='build/delivery/host-tree557.json')
    a = p.parse_args()
    if a.pin:
        pin(a.report)
    else:
        print(json.dumps(verify(), indent=2))
