"""Private577 delivery tree: the delivered 576 product tree with the interface and controller files of 48b9865.

576 shipped the 575 product (the 573 product with the RPCS3 Core 575; God of
War III without the 30 fps limiter, MeloNX keyboard and L3/R3) with the
MeloNX engine of 301e0f8. 577 keeps all of it and replaces only the files of
the maintainer-request commit 48b9865 (this session): the "Show system
bubbles" option of Settings › Themes › User interface (twelve languages), the
controller handed back to the menu once a game session ends (the gamepads
bridge reinstalls its handler; the RPCS3 input bridge restores the one it
replaced) and the latched `⋯` menu of the playlists, with their tests. The
RPCS3 Core 575 and the MeloNX engine of 301e0f8 are unchanged: no file of 577
is an input of either.

577 replaces five files the 550 recipe pinned at e12f1d4 (the interface
settings model, screen and strings, the games list, the settings test); every
other 577 file is the host tree's version or new. Every file's version before
48b9865 equals the 576 pinned one, so the change is exactly that commit.
Earlier receipts stay bound to the delivered 576 tree, which at_576() gives
back: the 577 files at their 576 versions (or absent) and this recipe
removed. Documentation follows HEAD. Runner checkout only: Git history is
not changed.
"""
import argparse, fnmatch, json, os, subprocess, tempfile
from pathlib import Path
import melonxwarm576_tree as previous
from liquidglass550_tree import SOURCE_UI

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
SOURCE576 = previous.SOURCE576
# The interface and controller commit (maintainer request, 27 October 2026).
SOURCE577 = '48b9865a3a305b4ed9e9cc2f6e45a15ce8d8a728'
SESSION = 'Claude-Session: https://claude.ai/code/session_01JA5QgN7driG9Po99SgE6cK'
FIX577 = ['lib/l10n/interface_style_locale.dart',
          'lib/screens/game_screen/game_details_card/tabs/game_details_achievements_tab.dart',
          'lib/screens/game_screen/my_games_carousel.dart',
          'lib/screens/game_screen/my_games_grid.dart',
          'lib/screens/game_screen/my_games_list.dart',
          'lib/screens/game_screen/my_games_list/gamepad_nav.dart',
          'lib/screens/settings_screen/interface_style/interface_style_screen.dart',
          'lib/screens/systems_screen/my_systems_section/my_systems_grid.dart',
          'lib/screens/systems_screen/my_systems_section/system_card.dart',
          'lib/services/game_launch_manager.dart',
          'lib/themes/interface_style.dart',
          'lib/utils/gamepad_nav.dart',
          'lib/widgets/console_bubble_transition.dart',
          'lib/widgets/game_action_buttons.dart',
          'lib/widgets/game_view_footer.dart',
          'packages/gamepads/lib/src/gamepads.dart',
          'packages/gamepads_darwin/ios/Classes/GamepadsIosPlugin.swift',
          'packages/gamepads_darwin/ios/Classes/GamepadsListener.swift',
          'packages/gamepads_platform_interface/lib/gamepads_platform_interface.dart',
          'packages/gamepads_platform_interface/lib/method_channel_gamepads_platform_interface.dart',
          'packages/rpcs3_internal_bridge/ios/Classes/RPCS3GameInputController.mm',
          'test/game_audio_handoff_test.py',
          'test/interface_style_settings_test.dart',
          'test/ios_gamepad_navigation_test.dart',
          'test/select_layer_latch_test.dart',
          'test/system_bubbles_option_test.dart']
# The shipped 577 files (compiled into the application).
SHIPPED577 = sorted(p for p in FIX577 if p.startswith(('lib/', 'native/', 'packages/', 'assets/', 'pubspec.')))
RECIPE = ['.github/diagnostics/interface577_tree.py', '.github/diagnostics/interface577_delivery.py',
          '.github/workflows/interface577-delivery.yml', 'build-utils/validate_rpcs3_577_ipa.py',
          'build-utils/validate_liquid_glass577_ipa.py', 'build-utils/validate_melonx_perf577_ipa.py',
          'build-utils/validate_rpcs3_library_files577_ipa.py', 'build-utils/validate_melonx_input577_ipa.py',
          'build-utils/validate_melonx_texture577_ipa.py', 'build-utils/validate_melonx_jit577_ipa.py',
          'build-utils/validate_melonx_switch577_ipa.py', 'build-utils/validate_melonx_warm577_ipa.py',
          'build-utils/validate_interface577_ipa.py', 'build-utils/delivery-577-recipient.pem']
OWNED = previous.OWNED + FIX577 + RECIPE
TREES = previous.TREES
# The 577 files an earlier recipe pins (the 550 interface); the others follow the host tree.
REPLACED = sorted(p for p in FIX577 if previous.owned(p))
assert REPLACED == ['lib/l10n/interface_style_locale.dart', 'lib/screens/game_screen/my_games_list.dart',
                    'lib/screens/settings_screen/interface_style/interface_style_screen.dart',
                    'lib/themes/interface_style.dart', 'test/interface_style_settings_test.dart'], REPLACED
assert all(previous.source_of(p) == SOURCE_UI for p in REPLACED)
# No 577 file is an input of the RPCS3 Core 575, the MeloNX engine or an earlier recipe's own fix.
assert not set(FIX577) & (set(previous.FIX576) | set(previous.previous.CELL575))


def git(*args, env=None):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True, env=env).strip()


def matches(path, patterns):
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def owned(path):
    return path in FIX577 or matches(path, RECIPE) or previous.owned(path)


def source_of(path):
    """Commit whose version of a file this build carries; None for this
    build's own recipe, which follows HEAD."""
    if path in FIX577:
        return SOURCE577
    if matches(path, RECIPE):
        return None
    return previous.source_of(path)


exists = previous.exists
blob = previous.blob
index_with = previous.index_with


def before(path):
    """The commit whose version of [path] the delivered 576 tree carries."""
    return previous.source_of(path) if previous.owned(path) else HOST_TREE


def at_576():
    """{path: commit, or None when absent}: every 577 file at its version in
    the delivered 576 tree, and this recipe removed. Applied to this index it
    gives back the 576 index exactly."""
    versions = {p: None for p in RECIPE}
    for p in FIX577:
        source = before(p)
        versions[p] = source if source and exists(source, p) else None
    return versions


def parent_contract():
    """The 577 change is exactly this session's commit: each file's version
    before it is the one the 576 tree carries (absent for the new tests), the
    only commit that touched a 577 file since the 576 engine commit is 48b9865,
    and each file did change."""
    parent = git('rev-parse', SOURCE577 + '^')
    for p in FIX577:
        assert blob(parent, p) == blob(before(p), p), (p, before(p))
        assert blob(SOURCE577, p) != blob(parent, p), (p, 'unchanged')
    commits = git('log', '--format=%H', SOURCE576 + '..' + SOURCE577, '--', *FIX577).split()
    assert commits == [SOURCE577], commits
    assert SESSION in git('log', '-1', '--format=%B', SOURCE577)


def verify():
    """The index is the 576 product tree with the 577 files, each from its source.

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
    for p in FIX577:
        assert git('rev-parse', ':' + p) == git('rev-parse', SOURCE577 + ':' + p), p
    return sorted(staged)


def fixes():
    """Every file an earlier recipe of the chain pins, and this build's."""
    t576 = previous
    t575 = t576.previous
    t573 = t575.previous
    t572 = t573.previous
    t567 = t572.previous
    t566 = t567.previous
    t565 = t566.previous
    t564 = t565.previous
    t563 = t564.previous
    t562 = t563.previous
    t561 = t562.previous
    t560 = t561.previous
    t559 = t560.previous
    t558 = t559.previous
    return (set(t558.UI550) | set(t558.CELL551) | set(t558.FIX552) | set(t558.PARITY) | set(t558.FIX554)
            | set(t558.FIX557) | set(t558.FIX558) | set(t559.CELL559) | set(t560.CELL560) | set(t561.CELL561)
            | set(t562.FIX562) | set(t563.CELL563) | set(t564.FIX564) | set(t565.CELL565) | set(t565.FIX565)
            | set(t566.FIX566) | set(t567.CELL567) | set(t572.FIX572) | set(t573.CELL573) | set(t575.CELL575)
            | set(t576.FIX576) | set(FIX577))


def pin(report):
    head = git('rev-parse', 'HEAD')
    parent_contract()
    chain = previous
    for _ in range(14):
        # 576, 575, 573, 572, 567, 566, 565, 564, 563, 562, 561, 560, 559 and 558, each against its own parent.
        chain.parent_contract()
        chain = chain.previous
    committed = {p for p in git('diff', '--name-only', HOST_TREE, head).splitlines() if p}
    plan = {}
    for p in sorted(committed | fixes()):
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
    trees576 = product_trees_576()
    # Only the lib and packages trees change, and only by the shipped 577 files.
    assert {p for p in TREES if trees[p] != trees576[p]} == {'lib', 'packages'}, (trees, trees576)
    receipt = dict(schemaVersion=1, head=head, hostTree=HOST_TREE, source551=SOURCE551, source558=SOURCE558,
                   source559=SOURCE559, source560=SOURCE560, source561=SOURCE561, source562=SOURCE562,
                   source563=SOURCE563, source564=SOURCE564, source565=SOURCE565, source565App=SOURCE565APP,
                   source566=SOURCE566, source567=SOURCE567, source569=SOURCE569, source571=SOURCE571,
                   source572=SOURCE572, source573=SOURCE573, source575=SOURCE575, source576=SOURCE576,
                   source577=SOURCE577, replaced=REPLACED, shipped=SHIPPED577, restored=restored,
                   removed=sorted(removed), keptFiles=kept, productTrees=trees, productTrees576=trees576,
                   reason='The 576 product tree with the interface and controller files of 48b9865; each file from the commit that validated it; Git history unchanged.')
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


def tree_576():
    """The delivered 576 tree: the 577 files at their 576 versions, computed in
    a scratch copy of the index, so the pinned index is untouched."""
    with tempfile.TemporaryDirectory() as scratch:
        env = index_with(at_576(), os.path.join(scratch, 'index'))
        return git('write-tree', env=env)


def product_trees_576():
    tree = tree_576()
    return {p: git('rev-parse', tree + ':' + p) for p in TREES}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--pin', action='store_true')
    p.add_argument('--report', default='build/delivery/host-tree577.json')
    a = p.parse_args()
    if a.pin:
        pin(a.report)
    else:
        print(json.dumps(verify(), indent=2))
