#!/usr/bin/env python3
"""Writes the origin publication (v2) of the unified cheat catalogue.

  python3 tools/cheats/origin/skeleton.py --origins <dir> --bundles <dir> --recipes recipes.json.gz

The v2 manifest lists the same games, with the same chunk SHA-256 and size,
as the hosted (v1) one: an installed chunk stays installed. Its packs carry
every chunk whole, except that a program of a source RewindBox does not host
keeps no code. In its place, `origin` says where the code is in that
source's own file (recipe.py), and the manifest's `origin.files` lists each
such file with its size and SHA-256 at the pinned revision. The app
downloads those files, rebuilds the chunk and checks its SHA-256.

Every rebuilt chunk is compared here with the published one: a program
whose chunk cannot be rebuilt byte for byte stays whole (and is reported).
"""
import argparse
import base64
import collections
import gzip
import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
from recipe import fbneo, raw_text, rebuild, rebuild_mister  # noqa: E402
from sources import ORIGINS  # noqa: E402
from unified_catalogue import canonical, gzip_bytes, sha  # noqa: E402

ROOT = HERE.parents[2]
V1 = ROOT / 'native/cheats/catalogue'
CODE_FIELDS = ('code', 'lines', 'source_code', 'choices', 'native_document')


class Origins:
    """Origin files (bytes, encoding) by (source, path). `table` is the file
    table of the pack being written: each pack carries its own, so the app
    resolves a pack without the manifest."""

    def __init__(self, roots, bundles):
        self.roots, self.bundles = roots, bundles
        self.table, self.index, self._bytes, self._zips, self._digests = [], {}, {}, {}, {}
        self.all_files = {}

    def start_pack(self):
        self.table, self.index = [], {}

    def file_index(self, source, path):
        key = (source, path)
        if key not in self.index:
            if key not in self._digests:
                data = self.raw(source, path)
                self._digests[key] = {'source': source, 'path': path, 'size': len(data),
                                      'sha256': hashlib.sha256(data).hexdigest()}
                self.all_files[key] = self._digests[key]
            self.index[key] = len(self.table)
            self.table.append(self._digests[key])
        return self.index[key]

    def raw(self, source, path):
        key = (source, path)
        if key not in self._bytes:
            if 'bundle' in ORIGINS[source]:
                self._bytes[key] = (self.bundles / f'{source}.bin').read_bytes()
            else:
                self._bytes[key] = (self.roots / source / path).read_bytes()
        return self._bytes[key]

    def member(self, source, path, inner=None):
        data = self.raw(source, path)
        if inner is not None:
            if (source, path) not in self._zips:
                with zipfile.ZipFile(io.BytesIO(data)) as bundle:
                    self._zips[(source, path)] = {i.filename: bundle.read(i) for i in bundle.infolist()}
            data = self._zips[(source, path)][inner]
        try:
            data.decode('utf-8')
            return data, 'utf-8'
        except UnicodeDecodeError:
            return data, 'cp1252'


def fields_of(program, origins, source):
    """The code fields a recipe gives back, with the file it reads."""
    recipe = dict(program['origin'])
    entry = origins.table[recipe.pop('f')]
    data, encoding = origins.member(source, entry['path'], recipe.get('z'))
    if recipe.get('k') == 'mister':
        return rebuild_mister(recipe, data, program['dialect'])
    if recipe.get('k') == 'fbneo':
        return fbneo(raw_text({'m': 0, 'r': recipe['r']}, [(data, encoding)]))
    return rebuild({**recipe, 'm': 0}, [(data, encoding)], program['dialect'])


def hydrate(chunk, origins):
    """The published chunk from a skeleton chunk (the app does the same)."""
    out = dict(chunk)
    out['cheats'] = []
    for program in chunk['cheats']:
        if 'origin' not in program:
            out['cheats'].append(program)
            continue
        source = origins.table[program['origin']['f']]['source']
        restored = {k: v for k, v in program.items() if k != 'origin'}
        restored.update(fields_of(program, origins, source))
        out['cheats'].append(restored)
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--origins', type=Path, required=True)
    parser.add_argument('--bundles', type=Path, required=True, help='<source>.bin of bundle sources')
    parser.add_argument('--recipes', type=Path, required=True)
    parser.add_argument('--out', type=Path, default=V1 / 'v2')
    args = parser.parse_args()
    recipes = json.loads(gzip.decompress(args.recipes.read_bytes()))
    manifest = json.loads(gzip.decompress((V1 / 'manifest.json.gz').read_bytes()))
    games = {g['id']: g for g in manifest['games']}
    origins = Origins(args.origins, args.bundles)
    stats = collections.Counter()
    out_packs = []
    (args.out / 'packs').mkdir(parents=True, exist_ok=True)
    for pack in manifest['packs']:
        origins.start_pack()
        retired = {r['game_id'] for r in pack.get('retired', [])}
        body = json.loads(gzip.decompress((V1 / pack['path']).read_bytes()))
        files = []
        for member in body['files']:
            if member['game_id'] in retired:
                continue
            published = base64.b64decode(member['data'])
            chunk = json.loads(published)
            skeleton, changed = dict(chunk), False
            skeleton['cheats'] = []
            for program in chunk['cheats']:
                recipe = recipes.get(f"{chunk['game']['id']}/{program['id']}")
                if recipe is None:
                    skeleton['cheats'].append(program)
                    continue
                source = min(p['source_id'] for p in program['provenance'])
                path = recipe['p'] if 'bundle' not in ORIGINS[source] else ORIGINS[source]['bundle']
                stripped = {k: v for k, v in program.items() if k not in CODE_FIELDS}
                stripped['origin'] = {'f': origins.file_index(source, path),
                                      **{k: v for k, v in recipe.items() if k != 'p'}}
                if 'bundle' in ORIGINS[source]:
                    stripped['origin']['z'] = recipe['p']
                skeleton['cheats'].append(stripped)
                changed = True
            if changed and canonical(hydrate(skeleton, origins)) == published:
                files.append({'game_id': member['game_id'], 'skeleton': base64.b64encode(canonical(skeleton)).decode()})
                stats['skeleton_chunks'] += 1
                stats['origin_programs'] += sum('origin' in p for p in skeleton['cheats'])
            else:
                if changed:
                    stats['chunks_kept_whole_after_failed_rebuild'] += 1
                files.append({'game_id': member['game_id'], 'data': member['data']})
                stats['hosted_chunks'] += 1
        body = {'schema_version': 1, 'files': files}
        if origins.table:
            used = sorted({f['source'] for f in origins.table})
            body['origin'] = {'version': 1, 'sources': {u: ORIGINS[u] for u in used}, 'files': origins.table}
        raw = canonical(body)
        packed = gzip_bytes(raw)
        digest = sha(packed)
        entry = {'id': 'pack-' + digest[:24], 'path': 'packs/pack-' + digest[:24] + '.json.gz', 'sha256': digest,
                 'size': len(packed), 'uncompressed_size': len(raw),
                 'game_ids': [g for g in pack['game_ids'] if g not in retired],
                 'origin': any('skeleton' in f for f in files)}
        (args.out / entry['path']).write_bytes(packed)
        for gid in entry['game_ids']:
            games[gid]['pack_id'] = entry['id']
        out_packs.append(entry)
    for old in (args.out / 'packs').glob('*.json.gz'):
        if old.name not in {Path(p['path']).name for p in out_packs}:
            old.unlink()
    v2 = dict(manifest)
    v2['packs'] = out_packs
    v2['games'] = [games[g['id']] for g in manifest['games']]
    files = list(origins.all_files.values())
    used = sorted({f['source'] for f in files})
    # Summary only: each pack carries the files it needs.
    v2['origin'] = {'version': 1, 'sources': {u: ORIGINS[u] for u in used}, 'file_count': len(files)}
    v2['totals'] = {**manifest['totals'], 'download_bytes': sum(p['size'] for p in out_packs),
                    'origin_bytes': sum(f['size'] for f in files)}
    v2.pop('revision', None)
    v2['revision'] = sha(canonical(v2))
    packed = gzip_bytes(canonical(v2))
    (args.out / 'manifest.json.gz').write_bytes(packed)
    report = {'manifest_sha256': sha(packed), 'manifest_bytes': len(packed), **stats,
              'origin_files': len(files), 'origin_bytes': v2['totals']['origin_bytes'],
              'pack_bytes': v2['totals']['download_bytes']}
    (args.out / 'VALIDATION.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
