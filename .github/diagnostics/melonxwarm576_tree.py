"""Private576 delivery tree: the delivered 575 product tree with the MeloNX engine files of 301e0f8 and the StikDebug fallback removal of 504f9c0.

575 shipped the 573 product (the 572 product with the RPCS3 Core 573; MeloNX
engine 8cc2348, God of War III without the 30 fps limiter, MeloNX keyboard
and L3/R3) with the RPCS3 Core 575. 576 keeps all of it and replaces only the
files of the MeloNX engine commit 301e0f8 (this session): three engine
adaptations (shader-cache warm-ups detached from the game's start, attachment-
less framebuffers sized to the viewports, a temporary boot trace of FINAL
FANTASY TACTICS - The Ivalice Chronicles), the adaptation list and the engine
workflow's push paths. The engine they describe is built and tested by its own
engine run from 301e0f8. The two existing files are pinned by the 575 tree at
the 566 engine commit 86c2b4d; the three adaptations are new. The only commit
that touched a 576 file since 86c2b4d is 301e0f8. No file of lib, native,
packages, assets or pubspec changes for the engine.

576 also carries the only application change committed since 575: the
StikDebug fallback removal of 504f9c0 (another session; MeloNX always uses
the integrated JIT helper, whose iOS 26 handshake the external backend
skipped, running the RX/RW probe iOS 26 kills). Its three changed product
files (lib, packages) and its tests come from 504f9c0, the two files it
deletes are removed, and the storage contract test from bfbb806, the later
commit that also lists the MeloNX imports. The product trees differ from the
delivered 575 ones in lib and packages only.

Earlier receipts stay bound to the delivered 575 tree, which at_575() gives
back: the 576 files at their 575 versions (or absent, or restored for the two
deleted ones) and this recipe removed.
Runner checkout only: Git history is not changed.
"""
import argparse, fnmatch, json, os, subprocess, tempfile
from pathlib import Path
import rpcs3cell575_tree as previous

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
SOURCE569 = previous.SOURCE569
SOURCE571 = previous.SOURCE571
SOURCE572 = previous.SOURCE572
SOURCE573 = previous.SOURCE573
SOURCE575 = previous.SOURCE575
# The MeloNX engine commit, built and tested by its own engine run.
SOURCE576 = '301e0f86020696a9e26e626d28b9078ae678f1d5'
ENGINE_COMMITS = [SOURCE576]
SESSION = 'Claude-Session: https://claude.ai/code/session_01K9YJtzFdPCSuLb7YJr2eeo'
FIX576 = ['.github/workflows/melonx-core.yml',
          'build-utils/melonx/adapt_attachmentless_framebuffer.py',
          'build-utils/melonx/adapt_fft_boot_trace.py',
          'build-utils/melonx/adapt_shader_warmup.py',
          'build-utils/melonx/prepare_embedded.py']
# The engine's own inputs (hashed by the engine identity as adaptations).
ENGINE576 = ['build-utils/melonx/adapt_attachmentless_framebuffer.py',
             'build-utils/melonx/adapt_fft_boot_trace.py',
             'build-utils/melonx/adapt_shader_warmup.py',
             'build-utils/melonx/prepare_embedded.py']
# The StikDebug fallback removal (504f9c0) and its tests; the storage contract
# test from bfbb806, which keeps 504f9c0's change and lists the MeloNX imports.
SOURCE_APP576 = '504f9c087999a0dbcc9b2aa62c2bfd49c7bee7bf'
SOURCE_TEST576 = 'bfbb806705efbc3398bef9e1cb85ea4cfbd9f01a'
APP576 = {'lib/l10n/jit_fallback_locale.dart': SOURCE_APP576,
          'lib/screens/settings_screen/new_settings_options/tools_settings_content.dart': SOURCE_APP576,
          'lib/services/jit_backend_preference_service.dart': SOURCE_APP576,
          'lib/services/melonx_internal_service.dart': SOURCE_APP576,
          'packages/melonx_internal_bridge/ios/Classes/MeloNXInternalBridgePlugin.swift': SOURCE_APP576,
          'test/jit_backend_preference_service_test.dart': SOURCE_APP576,
          'test/libretro_bios_checker_screen_test.dart': SOURCE_APP576,
          'test/melonx_launch_flow_test.py': SOURCE_APP576,
          'test/neoplay_build397_integration_test.py': SOURCE_APP576,
          'test/storage_tools_row_test.dart': SOURCE_APP576,
          'test/storage_contract_test.py': SOURCE_TEST576}
DELETED576 = ['lib/l10n/jit_fallback_locale.dart', 'lib/services/jit_backend_preference_service.dart']
# delivery_contract_memo.py, which the 565 recipe owns, follows HEAD here too.
RECIPE = ['.github/diagnostics/melonxwarm576_tree.py', '.github/diagnostics/melonxwarm576_delivery.py',
          '.github/workflows/melonx-warm576-delivery.yml', 'build-utils/validate_rpcs3_576_ipa.py',
          'build-utils/validate_liquid_glass576_ipa.py', 'build-utils/validate_melonx_perf576_ipa.py',
          'build-utils/validate_rpcs3_library_files576_ipa.py', 'build-utils/validate_melonx_input576_ipa.py',
          'build-utils/validate_melonx_texture576_ipa.py', 'build-utils/validate_melonx_jit576_ipa.py',
          'build-utils/validate_melonx_switch576_ipa.py', 'build-utils/validate_melonx_warm576_ipa.py',
          'build-utils/delivery-576-recipient.pem']
OWNED = previous.OWNED + FIX576 + sorted(APP576) + RECIPE
TREES = previous.TREES
# The 576 files the 575 tree pins at the 566 engine commit; the others are new.
REPLACED = sorted(p for p in FIX576 if previous.owned(p) and previous.source_of(p) == SOURCE566)
ADDED = sorted(p for p in FIX576 if not previous.owned(p))
assert REPLACED == ['.github/workflows/melonx-core.yml', 'build-utils/melonx/prepare_embedded.py'], REPLACED
assert sorted(REPLACED + ADDED) == sorted(FIX576), (REPLACED, ADDED)
# 576 ships no application file: the engine is its only product change.
assert not [p for p in FIX576 if p.startswith(('lib/', 'native/', 'packages/', 'assets/', 'pubspec.'))]
assert not set(FIX576) & (set(previous.CELL575) | set(previous.previous.CELL573) | set(previous.previous.previous.FIX572))
assert not set(APP576) & (set(FIX576) | set(previous.CELL575) | set(previous.previous.CELL573))
assert {p.split('/')[0] for p in APP576 if p.split('/')[0] in TREES} == {'lib', 'packages'}
assert previous.owned('build-utils/delivery_contract_memo.py')


def git(*args, env=None):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True, env=env).strip()


def matches(path, patterns):
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def owned(path):
    return path in FIX576 or path in APP576 or matches(path, RECIPE) or previous.owned(path)


def source_of(path):
    """Commit whose version of a file this build carries; None for this
    build's own recipe, which follows HEAD."""
    if path in FIX576:
        return SOURCE576
    if path in APP576:
        return APP576[path]
    if matches(path, RECIPE):
        return None
    return previous.source_of(path)


exists = previous.exists
blob = previous.blob
index_with = previous.index_with


def at_575():
    """{path: commit, or None when absent}: every 576 file at its version in
    the delivered 575 tree, and this recipe removed. Applied to this index it
    gives back the 575 index exactly."""
    versions = {p: None for p in RECIPE}
    for p in FIX576:
        source = previous.source_of(p) if p in REPLACED else None
        versions[p] = source if source and exists(source, p) else None
    for p in APP576:
        source = previous.source_of(p)
        versions[p] = source if source and exists(source, p) else None
    return versions


def parent_contract():
    """The 576 change is exactly this session's engine commit: each replaced
    file's version before it is the one the 575 tree pins (the 566 engine
    commit's), each added file is absent from the 575 tree and before it, no
    other commit touched a 576 file since 86c2b4d, and each file did change."""
    parent = git('rev-parse', SOURCE576 + '^')
    for p in REPLACED:
        before = previous.source_of(p)
        assert before == SOURCE566, (p, before)
        assert blob(parent, p) == blob(before, p), (p, before)
        assert blob(SOURCE576, p) != blob(parent, p), (p, 'unchanged')
    for p in ADDED:
        assert not exists(HOST_TREE, p) and not exists(parent, p), p
        assert exists(SOURCE576, p), p
    commits = git('log', '--format=%H', SOURCE566 + '..' + SOURCE576, '--', *FIX576).split()
    assert commits == ENGINE_COMMITS, commits
    for commit in ENGINE_COMMITS:
        assert SESSION in git('log', '-1', '--format=%B', commit)
    # The application change is exactly 504f9c0 (and bfbb806 for the storage
    # contract test): each file's version before it is the one the 575 tree
    # carries, and each file changed or was deleted.
    app_parent = git('rev-parse', SOURCE_APP576 + '^')
    for p, source in APP576.items():
        before = previous.source_of(p)
        assert exists(before, p) and blob(app_parent, p) == blob(before, p), (p, before)
        if p in DELETED576:
            assert not exists(source, p), p
        else:
            assert exists(source, p) and blob(source, p) != blob(before, p), (p, 'unchanged')
        expected = [SOURCE_TEST576, SOURCE_APP576] if source == SOURCE_TEST576 else [SOURCE_APP576]
        assert git('log', '--format=%H', before + '..' + source, '--', p).split() == expected, p
    assert 'Claude-Session:' in git('log', '-1', '--format=%B', SOURCE_APP576)


def verify():
    """The index is the 575 product tree with the 576 files, each from its source.

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
        if p in DELETED576:
            # Deleted by 504f9c0: absent from its source and from the index.
            assert not exists(source, p) and not git('ls-files', '--', p), p
            continue
        assert exists(source, p), (p, 'absent from', source)
        assert git('rev-parse', ':' + p) == git('rev-parse', source + ':' + p), (p, source)
    for p in FIX576:
        assert git('rev-parse', ':' + p) == git('rev-parse', SOURCE576 + ':' + p), p
    for p, source in APP576.items():
        if p not in DELETED576:
            assert git('rev-parse', ':' + p) == git('rev-parse', source + ':' + p), p
    return sorted(staged)


def pin(report):
    head = git('rev-parse', 'HEAD')
    parent_contract()
    chain = previous
    for _ in range(13):
        # 575, 573, 572, 567, 566, 565, 564, 563, 562, 561, 560, 559 and 558, each against its own parent.
        chain.parent_contract()
        p558 = chain
        chain = chain.previous
    p573 = previous.previous
    p572 = p573.previous
    p567 = p572.previous
    p566 = p567.previous
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
                    | set(p565.CELL565) | set(p565.FIX565) | set(p566.FIX566) | set(p567.CELL567)
                    | set(p572.FIX572) | set(p573.CELL573) | set(previous.CELL575) | set(FIX576) | set(APP576)):
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
    trees575 = product_trees_575()
    # The engine is built from its own run; only the StikDebug removal changes product trees.
    assert {p for p in TREES if trees[p] != trees575[p]} == {'lib', 'packages'}, (trees, trees575)
    receipt = dict(schemaVersion=1, head=head, hostTree=HOST_TREE, source551=SOURCE551, source558=SOURCE558,
                   source559=SOURCE559, source560=SOURCE560, source561=SOURCE561, source562=SOURCE562,
                   source563=SOURCE563, source564=SOURCE564, source565=SOURCE565, source565App=SOURCE565APP,
                   source566=SOURCE566, source567=SOURCE567, source569=SOURCE569, source571=SOURCE571,
                   source572=SOURCE572, source573=SOURCE573, source575=SOURCE575, source576=SOURCE576,
                   replaced=REPLACED, added=ADDED, sourceApp576=SOURCE_APP576, sourceTest576=SOURCE_TEST576,
                   app576=APP576, deleted576=DELETED576, restored=restored, removed=sorted(removed), keptFiles=kept,
                   productTrees=trees, productTrees575=trees575,
                   reason='The 575 product tree with the MeloNX engine files of 301e0f8 and the StikDebug fallback removal of 504f9c0; each file from the commit that validated it; Git history unchanged.')
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


def tree_575():
    """The delivered 575 tree: the 576 files at their 575 versions, computed in
    a scratch copy of the index, so the pinned index is untouched."""
    with tempfile.TemporaryDirectory() as scratch:
        env = index_with(at_575(), os.path.join(scratch, 'index'))
        return git('write-tree', env=env)


def product_trees_575():
    tree = tree_575()
    return {p: git('rev-parse', tree + ':' + p) for p in TREES}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--pin', action='store_true')
    p.add_argument('--report', default='build/delivery/host-tree576.json')
    a = p.parse_args()
    if a.pin:
        pin(a.report)
    else:
        print(json.dumps(verify(), indent=2))
