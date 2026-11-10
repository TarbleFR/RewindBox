"""Private543 delivery tree: the validated 542 host plus the RPCS3 543 Core files only.

Concurrent MeloNX work landed on Claude after 3494edc (eabc057, d9f35c2) and
needs its own rebuilt engine and validation. This delivery packages the
validated 542 tree with nothing but the 543 RPCS3 Core files: every other
path committed since 3494edc is restored to its 3494edc state in the runner
checkout (files added since then are removed). Git history is not changed.
"""
import argparse, fnmatch, json, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOST_TREE = '3494edc9e09fb60fecc35dd6cc301bcb93bc9434'
OWNED = ['build-utils/rpcs3/*', 'build-utils/build_rpcs3_embedded_core.sh', 'test/neo_swap_core_pin_test.py',
         '.github/workflows/rpcs3-core.yml', '.github/workflows/rpcs3-cell543-*.yml', '.github/diagnostics/rpcs3cell543_*.py',
         'build-utils/validate_rpcs3_543_ipa.py', 'build-utils/delivery-543-recipient.pem', 'test/rpcs3_cell543_test.py',
         'test/native/rpcs3_*543*.inc', 'test/fixtures/rpcs3_cell543.diff', 'docs/rpcs3-cell543.md', 'docs/evidence/rpcs3-cell543-*.json']


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def owned(path):
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in OWNED)


def verify():
    """The index differs from 3494edc only in 543 Core files.

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
    assert not git('ls-files', '--others', '--exclude-standard', '--', 'lib', 'native', 'packages', 'assets', 'build-utils/melonx')
    receipt = dict(schemaVersion=1, head=head, hostTree=HOST_TREE, restoredToHostTree=restored, rpcs3CoreFiles=kept,
                   reason='Concurrent unvalidated host work after 3494edc is excluded from this private IPA; Git history unchanged.')
    if report:
        out = ROOT / report
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))
    return receipt


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--pin', action='store_true')
    p.add_argument('--report', default='build/delivery/host-tree543.json')
    a = p.parse_args()
    if a.pin:
        pin(a.report)
    else:
        print(json.dumps(verify(), indent=2))
