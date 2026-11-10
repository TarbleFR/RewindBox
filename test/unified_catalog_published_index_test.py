#!/usr/bin/env python3
"""Validate only the final published gzip index through the real Apple reader.

This separate data-commit gate compiles the manager and existing native fixture,
then invokes ONLY its --manifest probe. The already accepted synthetic/runtime
suite is deliberately not executed again. No game, core, or IPA is built.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'native/cheats/catalogue/manifest.json.gz'
# The app bundles the origin publication (v2); older apps keep reading v1.
BUNDLED = ROOT / 'packages/neo_cheat_catalog/ios/Resources/manifest.json.gz'
PACKAGE = ROOT / 'packages/neo_cheat_catalog/ios'
NATIVE_FIXTURE = ROOT / 'test/unified_catalog_runtime_native.m'
COMPRESSED_LIMIT = 12 * 1024 * 1024
EXPANDED_LIMIT = 64 * 1024 * 1024


def publication_counts(path: Path) -> tuple[int, int, str]:
    """Read the published file with the same gzip expansion bounds as iOS."""
    compressed = path.read_bytes()
    if not 18 <= len(compressed) <= COMPRESSED_LIMIT or compressed[:2] != b'\x1f\x8b':
        raise ValueError('Published index must be a bounded gzip file')
    expected_size = int.from_bytes(compressed[-4:], 'little')
    if not 0 < expected_size <= EXPANDED_LIMIT:
        raise ValueError('Published index exceeds its expansion limit')
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    expanded = decoder.decompress(compressed, EXPANDED_LIMIT + 1)
    if (len(expanded) != expected_size or len(expanded) > EXPANDED_LIMIT or
            not decoder.eof or decoder.unused_data or decoder.unconsumed_tail):
        raise ValueError('Published gzip is truncated, concatenated, or has an invalid size')
    document = json.loads(expanded)
    if document.get('schema_version') != 1:
        raise ValueError('Unsupported published index schema')
    if not isinstance(document.get('games'), list) or not document['games']:
        raise ValueError('Published index has no game records')
    if not isinstance(document.get('packs'), list) or not document['packs']:
        raise ValueError('Published index has no packs')
    games, packs = len(document['games']), len(document['packs'])
    if isinstance(document.get('totals'), dict) and document['totals'].get('games', games) != games:
        raise ValueError('Published game count differs from declared totals')
    return games, packs, hashlib.sha256(compressed).hexdigest()


def run_published_gate(manifest: Path, result_path: Path | None = None) -> dict:
    if platform.system() != 'Darwin':
        raise RuntimeError('Published-index Apple reader gate requires macOS/Xcode; no Apple execution was performed')
    games, packs, digest = publication_counts(manifest)
    manager = PACKAGE / 'Classes/NeoUnifiedCheatCatalog.m'
    with tempfile.TemporaryDirectory(prefix='neo-cheat-published-index-') as folder:
        executable = Path(folder) / 'PublishedIndexReader'
        # The production reader prefers a local raw index when one exists.
        # Isolate exactly this published gzip so a stale untracked manifest.json
        # beside it cannot accidentally become the object under test.
        probe_manifest = Path(folder) / 'manifest.json.gz'
        shutil.copyfile(manifest, probe_manifest)
        if hashlib.sha256(probe_manifest.read_bytes()).hexdigest() != digest:
            raise ValueError('Published index changed during gate preparation')
        subprocess.run([
            'xcrun', '--sdk', 'macosx', 'clang', '-fobjc-arc', '-fblocks',
            '-Wno-deprecated-declarations', '-framework', 'Foundation', '-lz',
            '-I', str(PACKAGE / 'Classes/Public'),
            str(NATIVE_FIXTURE), str(manager), '-o', str(executable),
        ], check=True, timeout=120)
        # No invocation without --manifest: synthetic checks already passed on
        # the code commit and do not belong to this data-only verification.
        process = subprocess.run([
            str(executable), '--manifest', str(probe_manifest),
            '--expected-games', str(games), '--expected-packs', str(packs),
        ], capture_output=True, text=True, timeout=120)
        if process.stdout:
            print(process.stdout, end='' if process.stdout.endswith('\n') else '\n', flush=True)
        if process.stderr:
            print(process.stderr, end='' if process.stderr.endswith('\n') else '\n', flush=True)
        process.check_returncode()
    evidence = {
        'schema_version': 1,
        'manifest': str(manifest),
        'manifest_sha256': digest,
        'runtime_source_sha256': hashlib.sha256(manager.read_bytes()).hexdigest(),
        'native_fixture_sha256': hashlib.sha256(NATIVE_FIXTURE.read_bytes()).hexdigest(),
        'games': games,
        'packs': packs,
        # The actual Foundation probe asserts this, all publication counts and
        # shared snapshots across ten menus before returning a successful exit.
        'rejected_entries': 0,
        'apple_execution': True,
        'synthetic_suite_repeated': False,
        'foundation_output': process.stdout,
    }
    if result_path:
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(json.dumps(evidence, indent=2) + '\n')
    print(f'Published index accepted by Foundation: games={games}, packs={packs}, rejected_entries=0', flush=True)
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--result', type=Path)
    args = parser.parse_args()
    if args.manifest:
        run_published_gate(args.manifest, args.result)
        return
    run_published_gate(MANIFEST, args.result)
    if BUNDLED.read_bytes() != MANIFEST.read_bytes():
        run_published_gate(BUNDLED)


if __name__ == '__main__':
    main()
