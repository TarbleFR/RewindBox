#!/usr/bin/env python3
"""Withdraw the eight Pokemon France programs without rewriting other chunks.

The old publication remains identifiable in Git history. No attribution is
removed from a program while keeping that program executable.
"""
import base64
import copy
import gzip
import json
from pathlib import Path

from unified_catalogue import canonical, gzip_bytes, sha

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = ROOT / 'native/cheats/catalogue'
BUNDLE = ROOT / 'packages/neo_cheat_catalog/ios/Resources/manifest.json.gz'
BASE_INDEX = 'a475a740a2e6251a5638077ffcce53c81afc125acd6fbcfaf97ff28d7602d1a1'
WITHDRAWN = {'533635c085f971e8a5e3e0f854348c69', '60d89cf805c614b7c3b08e4b53ee5b48'}
REASON = 'Withheld pending written reuse permission; source credits retained in historical records.'


def blocked(program):
    return any(p.get('source_id') == 'pokemonfrance' or p.get('import_source_id') == 'pokemonfrance'
               for p in program.get('provenance', []))


def withdraw(index, read_pack, write_pack):
    result = copy.deepcopy(index)
    metas = {g['id']: g for g in result['games']}
    assert WITHDRAWN <= metas.keys()
    packs, changed, removed = [], [], 0
    for pack in result['packs']:
        if not WITHDRAWN.intersection(pack['game_ids']):
            packs.append(pack)
            continue
        data = read_pack(pack['path'])
        assert len(data) == pack['size'] and sha(data) == pack['sha256']
        raw = gzip.decompress(data)
        assert len(raw) == pack['uncompressed_size']
        body = json.loads(raw)
        kept = []
        for member in body['files']:
            if member['game_id'] not in WITHDRAWN:
                kept.append(member)
                continue
            chunk_bytes = base64.b64decode(member['data'])
            meta = metas[member['game_id']]
            assert len(chunk_bytes) == meta['size'] and sha(chunk_bytes) == meta['sha256']
            chunk = json.loads(chunk_bytes)
            assert len(chunk['cheats']) == 4 and all(blocked(c) for c in chunk['cheats'])
            removed += len(chunk['cheats'])
        body['files'] = kept
        raw = canonical(body)
        packed = gzip_bytes(raw)
        digest = sha(packed)
        replacement = {**pack, 'id': 'pack-' + digest[:24], 'path': 'packs/pack-' + digest[:24] + '.json.gz',
                       'sha256': digest, 'size': len(packed), 'uncompressed_size': len(raw),
                       'game_ids': [g for g in pack['game_ids'] if g not in WITHDRAWN]}
        write_pack(replacement['path'], packed)
        for gid in replacement['game_ids']:
            metas[gid]['pack_id'] = replacement['id']
        packs.append(replacement)
        changed.append({'old': pack['path'], 'new': replacement['path'], 'sha256': digest})
    assert removed == 8 and len(changed) == 2
    source = next(s for s in result['sources'] if s['id'] == 'pokemonfrance')
    assert source['available_programs'] == removed
    result['sources'] = [s for s in result['sources'] if s['id'] != 'pokemonfrance']
    result['excluded_sources'] = [*result.get('excluded_sources', []),
                                  {**source, 'status': 'withheld', 'available_programs': 0, 'reason': REASON}]
    result['games'] = [g for g in result['games'] if g['id'] not in WITHDRAWN]
    result['packs'] = packs
    totals = result['totals']
    totals.update(sources=len(result['sources']), games=len(result['games']),
                  identity_groups=len({g.get('identity_group', g['id']) for g in result['games']}),
                  programs=totals['programs'] - removed,
                  cheats=sum(g['cheat_count'] for g in result['games']),
                  available=sum(g['available_count'] for g in result['games']),
                  download_bytes=sum(p['size'] for p in packs))
    result.pop('revision', None)
    result['revision'] = sha(canonical(result))
    return result, changed


def main():
    baseline = BUNDLE.read_bytes()
    assert sha(baseline) == BASE_INDEX, 'Run only against the reviewed Build 479 index'
    index, changed = withdraw(json.loads(gzip.decompress(baseline)),
        lambda p: (DIRECTORY / p).read_bytes(), lambda p, b: (DIRECTORY / p).write_bytes(b))
    packed = gzip_bytes(canonical(index))
    (DIRECTORY / 'manifest.json.gz').write_bytes(packed)
    BUNDLE.write_bytes(packed)
    for p in changed:
        (DIRECTORY / p['old']).unlink()
    receipt = {'baselineIndexSHA256': BASE_INDEX, 'manifestSHA256': sha(packed),
               'removedPrograms': 8, 'removedTransportRecords': sorted(WITHDRAWN),
               'preservedPacks': len(index['packs']) - 2, 'replacedPacks': changed,
               'totals': index['totals'], 'reason': REASON, 'existingIPAsChanged': False}
    (ROOT / 'docs/evidence/source-rights-withdrawal.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
