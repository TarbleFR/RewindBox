"""Private558 delivery tree: the delivered 557 product tree with the MeloNX measurement files (cfce9f6).

557 shipped the 554 product tree (550 interface, RPCS3 551 Core, 552 launch-
crash fix, 553 MeloNX standalone parity, 554 RPCS3 import) with the
library-file fix of d645f05. 558 keeps all of it and replaces only the files
of the MeloNX measurement commits (4464ed6..cfce9f6, the Claude MeloNX session
only): the engine's audio pacing counters and their export, the per-second
[MeloNX:perf] journal, the emulation-priority choice, repeated NSLog stubs
counted once, Dart log lines appended with O_APPEND, the live log following a
user-data migration; their tests. Every file's version before those commits
(8bbe655) equals the 557 pinned one, so the change is exactly them. (The same
change was first prepared as 556 on the 554 tree; at the maintainer's request
it is built on 557 instead, and 556 was never delivered.)

558 changes files earlier builds shipped or hashed: nine files of the 553
parity (five Swift and header files, build_core.sh, ui-strings.json, the
parity test, the analysis) and prepare_embedded.py, an input of the MeloNX
engine receipts. Those receipts stay bound to the delivered 557 tree, which
this index gives back with the 558 files at their 557 versions and this
recipe removed (at_557; documentation follows HEAD in both); the 557 recipe
puts the 554 tree back for its own inherited checks. Runner checkout only:
Git history is not changed.
"""
import argparse, fnmatch, json, os, shutil, subprocess, tempfile
from pathlib import Path
import rpcs3libraryfiles557_tree as previous

ROOT = Path(__file__).resolve().parents[2]
HOST_TREE = previous.HOST_TREE
SOURCE_UI = previous.SOURCE_UI
SOURCE551 = previous.SOURCE551
SOURCE552 = previous.SOURCE552
SOURCE_PARITY = previous.SOURCE_PARITY
SOURCE_HOST = previous.SOURCE_HOST
SOURCE_DART = previous.SOURCE_DART
SOURCE554 = previous.SOURCE554
SOURCE557 = previous.SOURCE557
# The last commit of the measurement change; its engine files are those of the
# engine run (8f83748) and its Swift files those of the host run (e2c9437).
SOURCE558 = 'cfce9f6e82c23a2420f002ca155f829226f4f122'
FIRST558 = '4464ed6'
SESSION = 'Claude-Session: https://claude.ai/code/session_01KYeboDCuXQVCYqDw7Psc6T'
CLASSES = 'packages/melonx_internal_bridge/ios/Classes/'
FIX558 = ['build-utils/melonx/adapt_audio_pacing.py',
          'build-utils/melonx/build_core.sh',
          'build-utils/melonx/prepare_embedded.py',
          'build-utils/melonx/ui-strings.json',
          'docs/evidence/melonx-audio-pacing-local.json',
          'docs/melonx-persona-performance-2026-10-25.md',
          'lib/services/logger_service.dart',
          'lib/services/user_data_location_service.dart',
          'native/melonx/EmbeddedAudioPacing.cs',
          'native/melonx/EmbeddedAudioPacingExport.cs',
          CLASSES + 'MeloNXInternalBridgePlugin.swift',
          CLASSES + 'MeloNXMetalSessionViewController.swift',
          CLASSES + 'MeloNXPerfJournal.swift',
          CLASSES + 'MeloNXRuntimeAPI.swift',
          CLASSES + 'MeloNXSessionABI.h',
          CLASSES + 'MeloNXStandaloneParity.swift',
          'test/logger_append_test.dart',
          'test/melonx_audio_pacing/Program.cs',
          'test/melonx_audio_pacing_test.py',
          'test/melonx_perf_journal_test.py',
          'test/melonx_standalone_parity_test.py',
          'test/user_data_migration_log_test.dart']
# The shipped 558 files (lib, native, packages, assets, pubspec).
SHIPPED558 = sorted(p for p in FIX558 if p.startswith(('lib/', 'native/', 'packages/', 'assets/', 'pubspec.')))
SHIPPED_DART558 = sorted(p for p in SHIPPED558 if p.startswith('lib/'))
SHIPPED_MELONX558 = sorted(set(SHIPPED558) - set(SHIPPED_DART558))
LOCAL = 'docs/evidence/melonx-perf558-local.json'
RECIPE = ['.github/diagnostics/melonxperf558_tree.py', '.github/diagnostics/melonxperf558_delivery.py',
          '.github/workflows/melonx-perf558-delivery.yml', 'build-utils/validate_melonx_perf558_ipa.py',
          'build-utils/validate_liquid_glass558_ipa.py', 'build-utils/validate_rpcs3_library_files558_ipa.py',
          'build-utils/delivery-558-recipient.pem', LOCAL]
OWNED = previous.OWNED + FIX558 + RECIPE
# Files an earlier private build shipped or pinned that 558 replaces: nine of
# the 553 parity. Nothing of 550, 551, 552, 554 or 557 changes.
REPLACED = sorted(set(FIX558) & set(previous.OWNED))
UI550 = previous.UI550
PARITY = previous.previous.previous.PARITY
FIX552 = previous.previous.previous.previous.FIX552
CELL551 = previous.previous.previous.previous.previous.CELL551
FIX554 = previous.previous.FIX554
FIX557 = previous.FIX557
assert set(REPLACED) <= set(PARITY), REPLACED
assert len(REPLACED) == 9, REPLACED
assert not set(FIX558) & (set(UI550) | set(FIX552) | set(CELL551) | set(FIX554) | set(FIX557))
TREES = previous.TREES


def git(*args, env=None):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True, env=env).strip()


def matches(path, patterns):
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def owned(path):
    return path in FIX558 or matches(path, RECIPE) or previous.owned(path)


def source_of(path):
    """Commit whose version of a file this build carries; None for this
    build's own recipe and for documentation, which follow HEAD."""
    if path in FIX558:
        return None if path.startswith('docs/') else SOURCE558
    if matches(path, RECIPE):
        return None
    return previous.source_of(path)


def exists(commit, path):
    return bool(git('ls-tree', commit, '--', path))


def blob(commit, path):
    return git('rev-parse', commit + ':' + path) if exists(commit, path) else None


def at_557():
    """{path: commit, or None when absent}: every 558 file at its version in
    the delivered 557 tree, and this recipe removed. Applied to this index it
    gives back the 557 index exactly (docs follow HEAD in both)."""
    versions = {p: None for p in RECIPE}
    for p in FIX558:
        source = previous.source_of(p)
        if source is None:
            # Documentation the earlier recipes owned follows HEAD there too.
            versions[p] = git('rev-parse', 'HEAD') if exists('HEAD', p) else None
        else:
            versions[p] = source if exists(source, p) else None
    return versions


def parent_contract():
    """The 558 change is exactly the measurement commits: each file's version
    before them (FIRST558^) is the one the 557 tree pins, every commit that
    touched a 558 file since is this session's, and each shipped or test
    file did change."""
    parent = git('rev-parse', FIRST558 + '^')
    for p in FIX558:
        if p.startswith('docs/'):
            continue
        before = previous.source_of(p)
        assert blob(parent, p) == (blob(before, p) if before else None), (p, before)
        assert blob(SOURCE558, p) != blob(parent, p), (p, 'unchanged')
    commits = git('log', '--format=%H', parent + '..' + SOURCE558, '--', *FIX558).split()
    assert commits and git('rev-parse', FIRST558) in commits
    for commit in commits:
        assert SESSION in git('log', '-1', '--format=%B', commit), commit


def verify():
    """The index is the 557 product tree with the 558 files, each from its source.

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
    # Every file of the earlier builds keeps its pinned version unless a later build replaces it.
    for p in sorted(set(UI550) | set(previous.previous.previous.previous.SHIPPED552) | set(PARITY)
                    | set(FIX554) | set(FIX557) | set(FIX558)):
        source = source_of(p)
        if source is None:
            continue
        expected = SOURCE558 if p in FIX558 else SOURCE557 if p in FIX557 else None
        if expected:
            assert source == expected, (p, source)
        if exists(source, p):
            assert git('rev-parse', ':' + p) == git('rev-parse', source + ':' + p), (p, source)
    return sorted(staged)


def pin(report):
    head = git('rev-parse', 'HEAD')
    parent_contract()
    previous.parent_contract()
    committed = {p for p in git('diff', '--name-only', HOST_TREE, head).splitlines() if p}
    plan = {}
    for p in sorted(committed | set(UI550) | set(CELL551) | set(FIX552) | set(PARITY)
                    | set(FIX554) | set(FIX557) | set(FIX558)):
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
    ui = previous.previous.previous.previous.previous.previous
    receipt = dict(schemaVersion=1, head=head, hostTree=HOST_TREE, source547=ui.SOURCE547,
                   source548=ui.SOURCE548, source549=ui.SOURCE549, sourceInterface=SOURCE_UI, source551=SOURCE551,
                   source552=SOURCE552, sourceParity=SOURCE_PARITY, sourceHost=SOURCE_HOST, sourceDart=SOURCE_DART,
                   source554=SOURCE554, source557=SOURCE557, source558=SOURCE558, replaced=REPLACED, restored=restored,
                   removed=sorted(removed), keptFiles=kept, productTrees=product_trees(),
                   productTrees557=product_trees_557(),
                   reason='The 557 product tree with the MeloNX measurement files of cfce9f6; each file from the commit that validated it; Git history unchanged.')
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


def product_trees_557():
    """The 558 files at their 557 versions: the delivered 557 product tree.

    Computed in a scratch copy of the index, so the pinned index is untouched.
    """
    with tempfile.TemporaryDirectory() as scratch:
        env = index_with(at_557(), os.path.join(scratch, 'index'))
        tree = git('write-tree', env=env)
    return {p: git('rev-parse', tree + ':' + p) for p in TREES}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--pin', action='store_true')
    p.add_argument('--report', default='build/delivery/host-tree558.json')
    a = p.parse_args()
    if a.pin:
        pin(a.report)
    else:
        print(json.dumps(verify(), indent=2))
