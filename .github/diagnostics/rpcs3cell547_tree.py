"""Private547 delivery tree: the validated 546 host plus the RPCS3 547 Core files only.

The 547 Core and its timeline family landed on Claude next to concurrent work by
other agents (the Liquid Glass interface, which reserves build 548, and MeloNX
notes). This delivery packages the 546 delivery tree with nothing but the 547
Core files: every other path committed since that tree is restored to its state
there in the runner checkout (files added since then are removed). Git history
is not changed.
"""
import argparse, fnmatch, json, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOST_TREE = '6c6c624179540b860de16eab9c08323efaf12683'
OWNED = ['packages/rpcs3_internal_bridge/ios/Classes/Rpcs3Diagnostics.mm',
         'test/native/rpcs3_diagnostics546_test.mm',
         'build-utils/rpcs3/canonical-source.json', 'build-utils/rpcs3/embedded-core.patch',
         'build-utils/build_rpcs3_embedded_core.sh', '.github/workflows/rpcs3-core.yml',
         'test/neo_swap_core_pin_test.py', 'test/rpcs3_cell547_test.py', 'test/native/rpcs3_cell547.inc',
         'test/fixtures/rpcs3_cell547.diff', '.github/diagnostics/rpcs3cell547_*.py',
         '.github/workflows/rpcs3-cell547-*.yml', 'build-utils/validate_rpcs3_547_ipa.py',
         'build-utils/delivery-547-recipient.pem', 'docs/rpcs3-cell546.md', 'docs/rpcs3-cell547.md',
         'docs/evidence/rpcs3-cell546-*.json', 'docs/evidence/rpcs3-cell547-*.json', 'AGENTS.md']


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def owned(path):
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in OWNED)


def verify():
    """The index differs from the 546 delivery tree only in 547 files.

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
    receipt = dict(schemaVersion=1, head=head, hostTree=HOST_TREE, restoredToHostTree=restored, rpcs3Cell547Files=kept,
                   reason='Concurrent work after the 546 delivery tree is excluded from this private IPA; Git history unchanged.')
    if report:
        out = ROOT / report
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))
    return receipt


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--pin', action='store_true')
    p.add_argument('--report', default='build/delivery/host-tree547.json')
    a = p.parse_args()
    if a.pin:
        pin(a.report)
    else:
        print(json.dumps(verify(), indent=2))
