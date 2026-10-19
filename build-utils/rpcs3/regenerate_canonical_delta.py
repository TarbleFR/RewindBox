#!/usr/bin/env python3
"""Regenerate the single canonical RPCS3 Core delta from a reviewed work tree.

The work tree is the upstream revision of ``canonical-source.json`` (``upstream_commit``)
with the reviewed changes applied in place (tracked edits and new files). This tool
writes ``embedded-core.patch`` as one ``git diff`` from that upstream revision, refreshes
``files_sha256`` (LF-normalized SHA-256 of every added or modified file, the key that
``materialize_rpcs3_core.py`` verifies) and ``patch_sha256`` in the manifest, pins the same
digest in ``test/neo_swap_core_pin_test.py`` and, optionally, appends a policy sentence and
merges a JSON record (for example ``diagnostics_487``) into the manifest.

It never rebuilds a Core, never touches the work tree's HEAD or index (a temporary index
is used) and refuses a work tree whose upstream revision is not the manifest's.

    python3 build-utils/rpcs3/regenerate_canonical_delta.py <work-tree> \
        [--policy-note "Build 487 …"] [--record diagnostics_487=record.json] \
        [--verify-with <pristine upstream clone>] [--dry-run]
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / 'build-utils/rpcs3/canonical-source.json'
PATCH = ROOT / 'build-utils/rpcs3/embedded-core.patch'
PIN_TEST = ROOT / 'test/neo_swap_core_pin_test.py'


def run(command, cwd=None, env=None, check=True):
    return subprocess.run(command, cwd=cwd, env=env, check=check, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def lf_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def generate(work: Path, upstream: str):
    """Return (patch_text, {relative: sha256}) for upstream..work-tree incl. new files."""
    with tempfile.TemporaryDirectory(prefix='canonical-index-') as tmp:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(tmp) / 'index'))
        run(['git', 'read-tree', upstream], cwd=work, env=env)
        run(['git', 'add', '-A', '--', '.'], cwd=work, env=env)
        # Index lines carry the default abbreviation; the historical patch mixes 7- and
        # 9-character blob ids, so the regenerated text differs from it only there.
        # Bytes, never text mode: upstream files with CRLF endings must keep
        # their exact '\r' in removed and context lines.
        patch = subprocess.run(['git', '-c', 'diff.renames=false', 'diff', '--cached', '--no-color',
                                '--no-ext-diff', upstream], cwd=work, env=env, check=True,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout
        status = run(['git', 'diff', '--cached', '--name-status', '--no-renames', upstream],
                     cwd=work, env=env).stdout
    files = {}
    for line in status.splitlines():
        kind, _, relative = line.partition('\t')
        if kind in ('A', 'M'):
            files[relative] = lf_sha256(work / relative)
        elif kind == 'D':
            raise SystemExit('A canonical delta never deletes an upstream file: ' + relative)
        else:
            raise SystemExit('Unexpected status ' + line)
    if not patch.endswith(b'\n'):
        patch += b'\n'
    return patch, files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('work', type=Path, help='work tree: upstream revision + reviewed changes in place')
    parser.add_argument('--policy-note', default=None, help='sentence appended to manifest["policy"]')
    parser.add_argument('--record', action='append', default=[], metavar='NAME=FILE.json',
                        help='top-level manifest record to merge (replaces an existing record of that name)')
    parser.add_argument('--verify-with', type=Path, default=None,
                        help='pristine upstream clone: re-materialize there to prove the new delta applies')
    parser.add_argument('--dry-run', action='store_true', help='compute and report, write nothing')
    args = parser.parse_args()

    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    upstream = manifest['upstream_commit']
    work = args.work.resolve()
    head = run(['git', 'rev-parse', upstream], cwd=work, check=False)
    if head.returncode != 0:
        raise SystemExit(f'{work} does not contain the upstream revision {upstream}')
    patch, files = generate(work, upstream)
    digest = hashlib.sha256(patch).hexdigest()
    old_files = manifest['files_sha256']
    added = sorted(set(files) - set(old_files))
    changed = sorted(f for f in files if f in old_files and old_files[f] != files[f])
    removed = sorted(set(old_files) - set(files))
    print(f'patch: {len(patch)} bytes, sha256 {digest}; files {len(files)} '
          f'(+{len(added)} new, {len(changed)} changed, {len(removed)} no longer in the delta)')
    for f in added:
        print('  new:    ', f)
    for f in changed:
        print('  changed:', f)
    for f in removed:
        print('  removed:', f)
    if removed:
        raise SystemExit('Refusing to drop files from the canonical delta; review the work tree')
    if args.dry_run:
        print('dry run: nothing written; identical to the current patch: ' + str(digest == manifest['patch_sha256']))
        return 0

    # Keep the historical key order; append new files at the end.
    ordered = {k: files[k] for k in old_files if k in files}
    ordered.update({k: files[k] for k in added})
    manifest['files_sha256'] = ordered
    manifest['patch_sha256'] = digest
    if args.policy_note:
        manifest['policy'] = manifest['policy'].rstrip() + ' ' + args.policy_note.strip()
    for item in args.record:
        name, _, path = item.partition('=')
        if not name or not path:
            raise SystemExit('--record expects NAME=FILE.json')
        manifest[name] = json.loads(Path(path).read_text(encoding='utf-8'))
    PATCH.write_bytes(patch)
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    pin = PIN_TEST.read_text(encoding='utf-8')
    new_pin, count = re.subn(r"^PATCH_SHA256 = '[0-9a-f]{64}'$", f"PATCH_SHA256 = '{digest}'", pin, flags=re.M)
    if count != 1:
        raise SystemExit('PATCH_SHA256 pin not found exactly once in ' + str(PIN_TEST))
    PIN_TEST.write_text(new_pin, encoding='utf-8')
    print('wrote', PATCH.relative_to(ROOT), MANIFEST.relative_to(ROOT), PIN_TEST.relative_to(ROOT))

    if args.verify_with:
        with tempfile.TemporaryDirectory(prefix='canonical-verify-') as tmp:
            clone = Path(tmp) / 'rpcs3'
            run(['git', 'clone', '-q', '--no-checkout', str(args.verify_with.resolve()), str(clone)])
            run(['git', 'checkout', '-q', '--detach', upstream], cwd=clone)
            result = run([sys.executable, str(ROOT / 'build-utils/materialize_rpcs3_core.py'), str(clone)], check=False)
            print(result.stdout.strip())
            if result.returncode != 0:
                print(result.stderr.strip(), file=sys.stderr)
                raise SystemExit('materialize_rpcs3_core.py rejected the regenerated delta')
            # Every file of the work tree equals the materialized file (whole-tree proof, not only the delta).
            for relative in files:
                if lf_sha256(clone / relative) != files[relative]:
                    raise SystemExit('Materialized file differs from the work tree: ' + relative)
            shutil.rmtree(clone, ignore_errors=True)
        print('PASS: regenerated delta applies on a pristine upstream clone and reproduces the work tree')
    return 0


if __name__ == '__main__':
    sys.exit(main())
