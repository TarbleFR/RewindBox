"""Private549 delivery tree: the 546 delivery tree with the files of three validated deliveries.

Build 547 added the RPCS3 547 Core files to the 546 delivery tree; build 548
added the Liquid Glass interface to the same tree (with the RPCS3 546 Core).
549 combines both and adds the MeloNX backend-threading default and the
in-game FPS counter (05c2e03, f812267, 9bf068b). The three file sets do not
overlap. Every other path committed since the 546 tree is restored to its state
there in the runner checkout (files added since then are removed), exactly as
for 547. Git history is not changed.
"""
import argparse, fnmatch, json, subprocess
from pathlib import Path
import rpcs3cell547_tree as previous
import liquidglass_ui_delivery as glass

ROOT = Path(__file__).resolve().parents[2]
HOST_TREE = previous.HOST_TREE
MELONX549 = ['build-utils/melonx/adapt_session.py', 'build-utils/melonx/build_core.sh',
             'build-utils/melonx/managed_checks.py',
             'native/melonx/EmbeddedGraphicsSettings.cs', 'native/melonx/EmbeddedPerformance.cs',
             'native/melonx/EmbeddedSession.cs', 'native/melonx/EmbeddedWindowLifetime.cs',
             'lib/l10n/melonx_library_locale.dart', 'lib/services/melonx_internal_service.dart',
             'lib/widgets/melonx_internal_playlist_actions.dart',
             'packages/melonx_internal_bridge/ios/Classes/MeloNXMemoryGraph.swift',
             'packages/melonx_internal_bridge/ios/Classes/MeloNXMetalSessionViewController.swift',
             'packages/melonx_internal_bridge/ios/Classes/MeloNXRuntimeAPI.swift',
             'packages/melonx_internal_bridge/ios/Classes/MeloNXSessionABI.h',
             'test/melonx_display_native_test.py', 'test/melonx_effective_graphics_journal_test.py',
             'test/melonx_memory_graph_test.py', 'test/melonx_runtime_smoke.py', 'test/melonx_session_test.py',
             'docs/evidence/melonx-effective-graphics-journal.json', 'docs/melonx-persona-performance-2026-10-25.md']
# The interface owns the sources its 548 receipt hashes plus its recipe files.
GLASS = sorted(glass.owned())
OWNED = previous.OWNED + GLASS + MELONX549 + [
    '.github/diagnostics/melonxthreading549_*.py', '.github/workflows/melonx-threading549-*.yml',
    'build-utils/validate_melonx_threading549_ipa.py', 'build-utils/validate_liquid_glass549_ipa.py',
    'build-utils/delivery-549-recipient.pem',
    'test/melonx_threading549_test.dart', 'docs/evidence/melonx-threading549-*.json']
# Files kept from the 547 and 548 delivery commits; only their documentation changed since.
SOURCE547 = '08f2f7fa8c9081ff8f049eb96d31f054d549f278'
SOURCE548 = '5a9f1502973f3b9c37ddbc5f32abb5457b86ee80'


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def owned(path):
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in OWNED)


def verify():
    """The index differs from the 546 delivery tree only in 547, 548 and 549 MeloNX files.

    The index, not the working tree, is compared: later build steps generate and
    patch files in place but never stage them, so the check stays valid.
    """
    staged = [p for p in git('diff', '--cached', '--name-only', HOST_TREE).splitlines() if p]
    foreign = sorted(p for p in staged if not owned(p))
    assert not foreign, foreign
    # Every 547 and 548 file is the one delivered in 547 or 548.
    for p in staged:
        if p.startswith(('AGENTS.md', 'docs/')):
            continue
        if previous.owned(p):
            assert git('rev-parse', ':' + p) == git('rev-parse', SOURCE547 + ':' + p), p
        elif p in GLASS:
            assert git('rev-parse', ':' + p) == git('rev-parse', SOURCE548 + ':' + p), p
    return sorted(staged)


def pin(report):
    head = git('rev-parse', 'HEAD')
    committed = [p for p in git('diff', '--name-only', HOST_TREE, head).splitlines() if p]
    restored = sorted(p for p in committed if not owned(p))
    if restored:
        subprocess.run(['git', 'restore', '--source=' + HOST_TREE, '--staged', '--worktree', '--', *restored], cwd=ROOT, check=True)
    kept = verify()
    # Fresh checkout: the working tree must equal the pinned index exactly.
    assert not git('diff', '--name-only'), git('diff', '--name-only')
    assert not git('ls-files', '--others', '--exclude-standard', '--', 'lib', 'native', 'packages', 'assets', 'build-utils/rpcs3')
    receipt = dict(schemaVersion=1, head=head, hostTree=HOST_TREE, source547=SOURCE547, source548=SOURCE548, restoredToHostTree=restored,
                   keptFiles=kept, productTrees=product_trees(),
                   reason='Only the 547 Core, 548 interface and 549 MeloNX files are kept on the 546 delivery tree; Git history unchanged.')
    if report:
        out = ROOT / report
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))
    return receipt


def product_trees():
    """Git object IDs of every shipped source tree in the pinned index."""
    tree = git('write-tree')
    return {p: git('rev-parse', tree + ':' + p) for p in ['lib', 'native', 'packages', 'assets', 'pubspec.yaml', 'pubspec.lock']}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--pin', action='store_true')
    p.add_argument('--report', default='build/delivery/host-tree549.json')
    a = p.parse_args()
    if a.pin:
        pin(a.report)
    else:
        print(json.dumps(verify(), indent=2))
