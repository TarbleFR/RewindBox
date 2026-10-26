"""Private551 delivery tree: the validated 550 product tree with the RPCS3 551 files of 4e5bf59.

550 shipped the 549 product tree (546 delivery tree, RPCS3 547 Core, MeloNX
threading and FPS counter) with the e12f1d4 interface. 551 keeps all of that
and replaces only the files of the RPCS3 551 commit (4e5bf59): the Core
recipe, its tests and the two shipped host files (the timeline logger and the
game profiles). Every 551 file's parent version equals the 550 pinned one, so
the change is exactly that commit. Runner checkout only: Git history is not
changed.
"""
import argparse, fnmatch, json, os, shutil, subprocess, tempfile
from pathlib import Path
import liquidglass550_tree as previous

ROOT = Path(__file__).resolve().parents[2]
HOST_TREE = previous.HOST_TREE
SOURCE_UI = previous.SOURCE_UI
SOURCE551 = '4e5bf59b29c3aed8c3680b8b987aa586a52069c0'
CELL551 = ['.github/diagnostics/rpcs3cell551_core.py', '.github/workflows/rpcs3-cell551-core.yml',
           '.github/workflows/rpcs3-core.yml', 'AGENTS.md', 'build-utils/build_rpcs3_embedded_core.sh',
           'build-utils/rpcs3/canonical-source.json', 'build-utils/rpcs3/embedded-core.patch',
           'build-utils/rpcs3/patch_moltenvk_compile_qos.py', 'docs/evidence/rpcs3-cell551-local.json',
           'docs/rpcs3-cell551.md', 'lib/services/rpcs3_game_profile_service.dart',
           'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3Diagnostics.mm', 'test/fixtures/rpcs3_cell551.diff',
           'test/native/rpcs3_build487_boot_diagnostics_test.cpp', 'test/native/rpcs3_cell551.inc',
           'test/native/rpcs3_diagnostics546_test.mm', 'test/neo_swap_core_pin_test.py',
           'test/rpcs3_cell551_test.py', 'test/rpcs3_game_profile_service_test.dart']
# The shipped 551 files (lib, native, packages, assets, pubspec).
SHIPPED551 = sorted(p for p in CELL551 if p.startswith(('lib/', 'native/', 'packages/', 'assets/', 'pubspec.')))
RECIPE = ['.github/diagnostics/rpcs3cell551_tree.py', '.github/diagnostics/rpcs3cell551_delivery.py',
          '.github/workflows/rpcs3-cell551-delivery.yml', 'build-utils/validate_rpcs3_551_ipa.py',
          'build-utils/validate_liquid_glass551_ipa.py', 'build-utils/validate_melonx_threading551_ipa.py',
          'build-utils/delivery-551-recipient.pem']
OWNED = previous.OWNED + CELL551 + RECIPE
TREES = ['lib', 'native', 'packages', 'assets', 'pubspec.yaml', 'pubspec.lock']


def git(*args, env=None):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True, env=env).strip()


def matches(path, patterns):
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def owned(path):
    return path in CELL551 or matches(path, RECIPE) or previous.owned(path)


def source_of(path):
    """Commit whose version of a file this build carries; None for this
    build's own recipe and for documentation, which follow HEAD."""
    if path in CELL551:
        return None if path in ('AGENTS.md', 'docs/rpcs3-cell551.md') else SOURCE551
    if matches(path, RECIPE):
        return None
    return previous.source_of(path)


def exists(commit, path):
    return bool(git('ls-tree', commit, '--', path))


def verify():
    """The index is the 550 product tree plus the 551 files, each from its source.

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
    for p in previous.UI:
        assert git('rev-parse', ':' + p) == git('rev-parse', SOURCE_UI + ':' + p), p
    for p in CELL551:
        if source_of(p):
            assert git('rev-parse', ':' + p) == git('rev-parse', SOURCE551 + ':' + p), p
    return sorted(staged)


def pin(report):
    head = git('rev-parse', 'HEAD')
    committed = {p for p in git('diff', '--name-only', HOST_TREE, head).splitlines() if p}
    plan = {}
    for p in sorted(committed | set(previous.UI) | set(CELL551)):
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
    receipt = dict(schemaVersion=1, head=head, hostTree=HOST_TREE, source547=previous.SOURCE547, source548=previous.SOURCE548,
                   source549=previous.SOURCE549, sourceInterface=SOURCE_UI, source551=SOURCE551, restored=restored,
                   removed=sorted(removed), keptFiles=kept, productTrees=product_trees(), productTrees550=product_trees_550(),
                   reason='The 550 product tree with the RPCS3 551 files of 4e5bf59; each file from the commit that validated it; Git history unchanged.')
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


def product_trees_550():
    """The same trees with the shipped 551 files put back to their 550 versions.

    Computed in a scratch copy of the index: equal to the trees the 550
    interface and MeloNX receipts were bound to, it shows the 551 tree differs
    from the tested 550 one by the shipped 551 files only.
    """
    with tempfile.TemporaryDirectory() as scratch:
        index = os.path.join(scratch, 'index')
        shutil.copy2(git('rev-parse', '--path-format=absolute', '--git-path', 'index'), index)
        env = dict(os.environ, GIT_INDEX_FILE=index)
        for p in SHIPPED551:
            source = previous.source_of(p)
            mode, kind, blob = git('ls-tree', source, '--', p).split('\t')[0].split()
            git('update-index', '--cacheinfo', f'{mode},{blob},{p}', env=env)
        tree = git('write-tree', env=env)
    return {p: git('rev-parse', tree + ':' + p) for p in TREES}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--pin', action='store_true')
    p.add_argument('--report', default='build/delivery/host-tree551.json')
    a = p.parse_args()
    if a.pin:
        pin(a.report)
    else:
        print(json.dumps(verify(), indent=2))
