#!/usr/bin/env python3
"""Fold the staged RetroAchievements Core patch into the single canonical delta.

Run this ONLY as the first step of an authorized RPCS3 Core build. Once folded,
canonical-source.json and embedded-core.patch no longer describe the prebuilt
Core, and every IPA workflow refuses that Core until one built from the new
delta is installed (RPCS3_CORE_HOST_SHA / RPCS3_CORE_RUN_ID).

    python3 -B build-utils/materialize_rpcs3_core.py <tree>
    python3 build-utils/rpcs3/fold_retroachievements_core_patch.py <tree> [--dry-run]

<tree> is a checkout of the manifest's upstream revision on which
materialize_rpcs3_core.py applied the current canonical delta. The staged patch
(build-utils/rpcs3/retroachievements-core.patch) is checked against the
recorded preimages, applied, verified against the recorded postimages, then
regenerate_canonical_delta.py rewrites embedded-core.patch, files_sha256,
patch_sha256 and the pin test, and records `retroachievements_core`. Nothing is
built, committed or pushed.
"""
import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STAGED = ROOT / 'build-utils/rpcs3/retroachievements-core.json'
CANONICAL = ROOT / 'build-utils/rpcs3/canonical-source.json'
REGENERATE = ROOT / 'build-utils/rpcs3/regenerate_canonical_delta.py'
POLICY_NOTE = ('NEOSTATION_RPCS3_RETROACHIEVEMENTS_V1: optional RetroAchievements hooks '
               '(VBlank frame callback, guarded guest reads, session info); ABI 30 unchanged.')


def lf_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('work', type=Path, help='materialized canonical Core tree')
    parser.add_argument('--dry-run', action='store_true', help='check only; change nothing')
    args = parser.parse_args()
    work = args.work.resolve()

    staged = json.loads(STAGED.read_text(encoding='utf-8'))
    canonical = json.loads(CANONICAL.read_text(encoding='utf-8'))
    if staged.get('folded_into_canonical_delta'):
        raise SystemExit('The RetroAchievements patch is already part of the canonical delta')
    patch = ROOT / staged['patch']
    if hashlib.sha256(patch.read_bytes()).hexdigest() != staged['patch_sha256']:
        raise SystemExit('Staged patch checksum mismatch')
    if staged['upstream_commit'] != canonical['upstream_commit']:
        raise SystemExit('The staged patch targets another upstream revision')
    head = subprocess.run(['git', '-C', str(work), 'rev-parse', 'HEAD'], check=True,
                          capture_output=True, text=True).stdout.strip()
    if head != canonical['upstream_commit']:
        raise SystemExit(f'{work} is not at the canonical upstream revision')
    for relative, before in staged['files_before_sha256'].items():
        if canonical['files_sha256'].get(relative) != before:
            raise SystemExit(f'{relative} changed in the canonical delta: rebase the staged patch first')
        if lf_sha256(work / relative) != before:
            raise SystemExit(f'{relative} is not the canonical postimage: run materialize_rpcs3_core.py first')
    for relative in staged['new_files']:
        if (work / relative).exists():
            raise SystemExit(f'{relative} already exists in the work tree')
    subprocess.run(['git', '-C', str(work), 'apply', '--check', str(patch)], check=True)
    if args.dry_run:
        print('PASS (dry run): the staged RetroAchievements patch applies to the canonical postimage')
        return 0

    subprocess.run(['git', '-C', str(work), 'apply', str(patch)], check=True)
    for relative, after in staged['files_after_sha256'].items():
        if lf_sha256(work / relative) != after:
            raise SystemExit(f'Unexpected postimage for {relative}')
    record = dict(staged, folded_into_canonical_delta=True,
                  base_canonical_patch_sha256=canonical['patch_sha256'])
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False, encoding='utf-8') as handle:
        json.dump(record, handle, indent=2)
        record_path = handle.name
    try:
        subprocess.run([sys.executable, str(REGENERATE), str(work), '--policy-note', POLICY_NOTE,
                        '--record', f'retroachievements_core={record_path}'], check=True)
    finally:
        Path(record_path).unlink(missing_ok=True)
    staged['folded_into_canonical_delta'] = True
    STAGED.write_text(json.dumps(staged, indent=2) + '\n', encoding='utf-8')
    print('Folded. Next, only with authorization: build the Core from this delta, then use its run in the IPA build.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
