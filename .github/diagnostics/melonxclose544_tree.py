"""Private544 delivery tree: the validated 542 host plus the MeloNX close-teardown files only.

The MeloNX close fix (eabc057, d9f35c2) landed on Claude next to concurrent
RPCS3 543 Core work. This delivery packages the validated 542 tree, including
its RPCS3 542 Core pins, with nothing but the MeloNX close files: every other
path committed since 3494edc is restored to its 3494edc state in the runner
checkout (files added since then are removed). Git history is not changed.
"""
import argparse, fnmatch, json, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOST_TREE = '3494edc9e09fb60fecc35dd6cc301bcb93bc9434'
OWNED = ['build-utils/melonx/adapt_gpu_lifetime.py', 'build-utils/melonx/prepare_embedded.py',
         'build-utils/melonx/analyze_session_logs.py', '.github/workflows/melonx-core.yml',
         'lib/services/melonx_internal_service.dart', 'lib/services/game_launch_manager.dart',
         'lib/widgets/game_launch_dialog.dart',
         'packages/melonx_internal_bridge/ios/Classes/MeloNXInternalBridgePlugin.swift',
         'test/game_audio_handoff_test.py', 'test/game_close_status_test.py', 'test/melonx_gpu_teardown_test.py',
         'test/melonx_gpu_teardown/*', 'docs/melonx-fermeture-persona-2026-10-25.md',
         'docs/evidence/melonx-close-teardown-2026-10-25.json', 'docs/evidence/melonx-close544-*.json',
         '.github/workflows/melonx-close544-*.yml', '.github/diagnostics/melonxclose544_*.py',
         'build-utils/validate_melonx_close544_ipa.py', 'build-utils/delivery-544-recipient.pem']


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def owned(path):
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in OWNED)


def verify():
    """The index differs from 3494edc only in MeloNX close files.

    The index, not the working tree, is compared: later build steps generate and
    patch files in place but never stage them, so the check stays valid.
    """
    staged = [p for p in git('diff', '--cached', '--name-only', HOST_TREE).splitlines() if p]
    foreign = sorted(p for p in staged if not owned(p))
    assert not foreign, foreign
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
    receipt = dict(schemaVersion=1, head=head, hostTree=HOST_TREE, restoredToHostTree=restored, meloNXCloseFiles=kept,
                   reason='Concurrent RPCS3 543 work after 3494edc is excluded from this private IPA; Git history unchanged.')
    if report:
        out = ROOT / report
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))
    return receipt


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--pin', action='store_true')
    p.add_argument('--report', default='build/delivery/host-tree544.json')
    a = p.parse_args()
    if a.pin:
        pin(a.report)
    else:
        print(json.dumps(verify(), indent=2))
