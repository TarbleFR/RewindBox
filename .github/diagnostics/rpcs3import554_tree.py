"""Private554 delivery tree: the delivered 553 product tree with the RPCS3 library-file import of 410678b.

553 shipped the 552 product tree (550 interface, RPCS3 551 Core, 552 launch-
crash fix) with the MeloNX standalone parity. A user's app.log then showed a
PS3 ISO of the library folder (roms/ps3) listed by the scan but launched
through the RetroArch route on every try, while RPCS3's library stayed
empty. 554 keeps all of 553 and adds only the files of the fix commit
(410678b): every iOS PS3 row takes the RPCS3 branch, a library-folder disc
is linked to the title RPCS3 holds or installed by RPCS3's own import after
the user agrees, `.dkey` disc keys are accepted, import results reach
app.log; their tests and the analysis. No shipped file of 553 changes, and
the Core is the 551 one. Runner checkout only: Git history is not changed.
"""
import argparse, fnmatch, json, os, shutil, subprocess, tempfile
from pathlib import Path
import melonxparity553_tree as previous

ROOT = Path(__file__).resolve().parents[2]
HOST_TREE = previous.HOST_TREE
SOURCE_UI = previous.SOURCE_UI
SOURCE551 = previous.SOURCE551
SOURCE552 = previous.SOURCE552
SOURCE_PARITY = previous.SOURCE_PARITY
SOURCE_HOST = previous.SOURCE_HOST
SOURCE_DART = previous.SOURCE_DART
SOURCE554 = '410678b7b2d383c83fd60886333c48c4d977a361'
FIX554 = ['docs/rpcs3-import554.md',
          'lib/l10n/rpcs3_library_file_locale.dart',
          'lib/screens/game_screen/my_games_list/launch_flow.dart',
          'lib/services/game/game_launch_service.dart',
          'lib/services/rpcs3_content_import_service.dart',
          'lib/services/rpcs3_disc_image.dart',
          'lib/services/rpcs3_library_file_service.dart',
          'lib/services/rpcs3_library_service.dart',
          'lib/widgets/rpcs3_library_file_install_dialog.dart',
          'test/localization_12_locale_coverage_test.py',
          'test/ps3_disc_image_builder.dart',
          'test/rpcs3_disc_image_test.dart',
          'test/rpcs3_library_file_dialog_test.dart',
          'test/rpcs3_library_file_route_contract_test.py',
          'test/rpcs3_library_file_service_test.dart',
          'test/storage_contract_test.py']
# The shipped 554 files (lib, native, packages, assets, pubspec).
SHIPPED554 = sorted(p for p in FIX554 if p.startswith(('lib/', 'native/', 'packages/', 'assets/', 'pubspec.')))
LOCAL = 'docs/evidence/rpcs3-import554-local.json'
RECIPE = ['.github/diagnostics/rpcs3import554_tree.py', '.github/diagnostics/rpcs3import554_delivery.py',
          '.github/workflows/rpcs3-import554-delivery.yml', 'build-utils/validate_rpcs3_import554_ipa.py',
          'build-utils/validate_liquid_glass554_ipa.py', 'build-utils/validate_melonx_parity554_ipa.py',
          'build-utils/delivery-554-rpcs3-recipient.pem', LOCAL]
OWNED = previous.OWNED + FIX554 + RECIPE
# 554 changes no file an earlier private build shipped or pinned.
assert not set(FIX554) & set(previous.OWNED), sorted(set(FIX554) & set(previous.OWNED))
TREES = previous.TREES


def git(*args, env=None):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True, env=env).strip()


def matches(path, patterns):
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def owned(path):
    return path in FIX554 or matches(path, RECIPE) or previous.owned(path)


def source_of(path):
    """Commit whose version of a file this build carries; None for this
    build's own recipe and for documentation, which follow HEAD."""
    if path in FIX554:
        return None if path.startswith('docs/') else SOURCE554
    if matches(path, RECIPE):
        return None
    return previous.source_of(path)


def exists(commit, path):
    return bool(git('ls-tree', commit, '--', path))


def verify():
    """The index is the 553 product tree plus the 554 files, each from its source.

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
    for p in previous.previous.previous.previous.UI:
        assert git('rev-parse', ':' + p) == git('rev-parse', SOURCE_UI + ':' + p), p
    for p in previous.previous.SHIPPED552:
        assert git('rev-parse', ':' + p) == git('rev-parse', SOURCE552 + ':' + p), p
    for p in previous.PARITY:
        if previous.source_of(p):
            assert git('rev-parse', ':' + p) == git('rev-parse', previous.source_of(p) + ':' + p), p
    for p in FIX554:
        if source_of(p):
            assert git('rev-parse', ':' + p) == git('rev-parse', SOURCE554 + ':' + p), p
    return sorted(staged)


def pin(report):
    head = git('rev-parse', 'HEAD')
    committed = {p for p in git('diff', '--name-only', HOST_TREE, head).splitlines() if p}
    plan = {}
    cell551 = previous.previous.previous.CELL551
    for p in sorted(committed | set(previous.previous.previous.previous.UI) | set(cell551)
                    | set(previous.previous.FIX552) | set(previous.PARITY) | set(FIX554)):
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
    ui = previous.previous.previous.previous
    receipt = dict(schemaVersion=1, head=head, hostTree=HOST_TREE, source547=ui.SOURCE547,
                   source548=ui.SOURCE548, source549=ui.SOURCE549, sourceInterface=SOURCE_UI, source551=SOURCE551,
                   source552=SOURCE552, sourceParity=SOURCE_PARITY, sourceHost=SOURCE_HOST, sourceDart=SOURCE_DART,
                   source554=SOURCE554, restored=restored, removed=sorted(removed), keptFiles=kept,
                   productTrees=product_trees(), productTrees553=product_trees_553(), productTrees552=product_trees_552(),
                   productTrees551=product_trees_551(), productTrees550=product_trees_550(),
                   reason='The 553 product tree with the RPCS3 library-file import files of 410678b; each file from the commit that validated it; Git history unchanged.')
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


def import_at_553():
    """The shipped 554 files at their 553 versions (the new ones absent)."""
    return {p: previous.source_of(p) or HOST_TREE for p in SHIPPED554}


def product_trees_553():
    """The 554 files at their 553 versions: the 553 product tree."""
    return trees_with(import_at_553())


def product_trees_552():
    """The 553 product tree with the MeloNX parity files at their 552 versions."""
    versions = import_at_553()
    versions.update(previous.melonx_at(previous.previous.source_of))
    return trees_with(versions)


def product_trees_551():
    """The RPCS3 files at 551 and the MeloNX files at their 551 versions: the 551 product tree."""
    versions = import_at_553()
    versions.update(previous.melonx_at(previous.previous.previous.source_of))
    versions.update({p: SOURCE551 for p in previous.previous.SHIPPED552})
    return trees_with(versions)


def product_trees_550():
    """Every shipped 551/552/553/554 file at its 550 version: the trees the
    550 interface and MeloNX receipts were bound to."""
    at550 = previous.previous.previous.previous.source_of
    versions = import_at_553()
    versions.update(previous.melonx_at(at550))
    versions.update({p: at550(p) for p in previous.previous.SHIPPED552})
    return trees_with(versions)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--pin', action='store_true')
    p.add_argument('--report', default='build/delivery/host-tree554.json')
    a = p.parse_args()
    if a.pin:
        pin(a.report)
    else:
        print(json.dumps(verify(), indent=2))
