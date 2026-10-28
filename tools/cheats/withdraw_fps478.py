#!/usr/bin/env python3
"""Withdraw the 60 FPS supplement programs that no licence or permission covers.

Rights review of 28 October 2026 (docs/SOURCE_RIGHTS_FOLLOWUP_2026-10-28.md):

* pcsx2_fps478, gabominated_fps478, nethersx2_fps478 (a pcsx2_patches
  derivative) and nds_fps478 (a Reddit post) grant no licence: their
  programs are withdrawn and the profiles move to excluded_sources with
  their credits.
* illusion_fps478 mirrors RPCS3 Wiki content (CC BY-SA 4.0, browser-verified,
  docs/licenses/rpcs3-wiki-2026-10-28.md). Programs whose native document is
  identical to the official patch.yml (content SHA-256 f1f3cab0...) are kept
  and relabelled with that licence; the 3 that differ are withdrawn.

Only the packs holding these programs are rewritten; every other pack and
chunk keeps its bytes. Like withdraw_pokemonfrance.py, this runs once against
the reviewed index and is not meant to be re-run.
"""
import base64
import copy
import gzip
import json
from pathlib import Path

from unified_catalogue import canonical, gzip_bytes, sha, validate

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = ROOT / 'native/cheats/catalogue'
BUNDLE = ROOT / 'packages/neo_cheat_catalog/ios/Resources/manifest.json.gz'
BASE_INDEX = '095cf728487a7b10d0516b88895d64f1eac43ad5df65eb4aabe5f1796e79270c'
WITHHELD = {
    'pcsx2_fps478': 125,
    'gabominated_fps478': 291,
    'nethersx2_fps478': 486,
    'nds_fps478': 5,
}
ILLUSION = 'illusion_fps478'
# Native documents that differ from the official patch.yml (lineage check).
ILLUSION_DIFFERS = {
    '27f742c00526dffcd10f3d2b5593ee1a',
    '8652b210de7d0220d9f877e7600bfb8a',
    'dbe94750f58a5e0aebc9010c67f55540',
}
ILLUSION_LICENSE = ('CC BY-SA 4.0 (RPCS3 Wiki contributors and the named patch authors; '
                    'https://creativecommons.org/licenses/by-sa/4.0/). Identical to the official RPCS3 '
                    'patch.yml, content SHA-256 f1f3cab0c8fee21c30ef69789d79468e2c69a4f52583e53e4392a1cf97791486; '
                    'transported from the pinned illusion0001 mirror.')
REASON = ('Withheld: the source grants no licence to redistribute its codes and no written permission '
          'is recorded (rights review of 28 October 2026). Credits retained in historical records.')


def sources_of(program):
    return {p.get('source_id') for p in program.get('provenance', [])} | \
           {p.get('import_source_id') for p in program.get('provenance', [])}


def withdrawn(program):
    ids = sources_of(program)
    return bool(ids & WITHHELD.keys()) or (ILLUSION in ids and program['id'] in ILLUSION_DIFFERS)


def relabel(program):
    if ILLUSION not in sources_of(program):
        return program
    program = copy.deepcopy(program)
    for p in program['provenance']:
        if p.get('source_id') == ILLUSION:
            p['license'] = ILLUSION_LICENSE
    return program


def withdraw(index, read_pack, write_pack):
    result = copy.deepcopy(index)
    metas = {g['id']: g for g in result['games']}
    packs, changed, dropped_games = [], [], set()
    removed = {source: 0 for source in [*WITHHELD, ILLUSION]}
    kept_illusion = 0
    for pack in result['packs']:
        data = read_pack(pack['path'])
        assert len(data) == pack['size'] and sha(data) == pack['sha256']
        raw = gzip.decompress(data)
        assert len(raw) == pack['uncompressed_size']
        body = json.loads(raw)
        retired = {row['game_id'] for row in pack.get('retired', [])}
        touched, files = False, []
        for member in body['files']:
            chunk_bytes = base64.b64decode(member['data'])
            chunk = json.loads(chunk_bytes)
            hits = [c for c in chunk['cheats'] if sources_of(c) & {*WITHHELD, ILLUSION}]
            if not hits:
                files.append(member)
                continue
            # Superseded copies are never served: none may carry these programs.
            assert member['game_id'] not in retired, member['game_id']
            meta = metas[member['game_id']]
            assert len(chunk_bytes) == meta['size'] and sha(chunk_bytes) == meta['sha256']
            touched = True
            kept = []
            for program in chunk['cheats']:
                if withdrawn(program):
                    source = next(s for s in [*WITHHELD, ILLUSION] if s in sources_of(program))
                    removed[source] += 1
                    continue
                if ILLUSION in sources_of(program):
                    kept_illusion += 1
                kept.append(relabel(program))
            ids = {c['id'] for c in kept}
            assert all(d in ids for c in kept for d in c.get('dependencies', [])), 'a kept program loses a dependency'
            if not kept:
                dropped_games.add(member['game_id'])
                continue
            chunk['cheats'] = kept
            encoded = canonical(chunk)
            meta.update(size=len(encoded), sha256=sha(encoded), cheat_count=len(kept),
                        available_count=sum(c['status'] == 'available' for c in kept))
            files.append({**member, 'data': base64.b64encode(encoded).decode('ascii')})
        if not touched:
            packs.append(pack)
            continue
        body['files'] = files
        raw = canonical(body)
        packed = gzip_bytes(raw)
        digest = sha(packed)
        replacement = {**pack, 'id': 'pack-' + digest[:24], 'path': 'packs/pack-' + digest[:24] + '.json.gz',
                       'sha256': digest, 'size': len(packed), 'uncompressed_size': len(raw),
                       'game_ids': [g for g in pack['game_ids'] if g not in dropped_games]}
        write_pack(replacement['path'], packed)
        for gid in replacement['game_ids']:
            metas[gid]['pack_id'] = replacement['id']
        packs.append(replacement)
        changed.append({'old': pack['path'], 'new': replacement['path'], 'sha256': digest})
    assert {s: removed[s] for s in WITHHELD} == WITHHELD, removed
    assert removed[ILLUSION] == len(ILLUSION_DIFFERS) and kept_illusion == 280, (removed, kept_illusion)

    by_id = {s['id']: s for s in result['sources']}
    for source_id in WITHHELD:
        assert by_id[source_id]['available_programs'] == WITHHELD[source_id]
    result['sources'] = [s for s in result['sources'] if s['id'] not in WITHHELD]
    result['excluded_sources'] = [*result.get('excluded_sources', []), *[
        {**by_id[s], 'status': 'withheld', 'available_programs': 0, 'reason': REASON} for s in WITHHELD]]
    illusion = next(s for s in result['sources'] if s['id'] == ILLUSION)
    illusion.update(available_programs=kept_illusion, license=ILLUSION_LICENSE,
                    reason='3 programs that differ from the official patch.yml withheld (rights review of '
                           '28 October 2026).')
    result['games'] = [g for g in result['games'] if g['id'] not in dropped_games]
    result['packs'] = packs
    total_removed = sum(removed.values())
    totals = result['totals']
    totals.update(sources=len(result['sources']), games=len(result['games']),
                  identity_groups=len({g.get('identity_group', g['id']) for g in result['games']}),
                  programs=totals['programs'] - total_removed,
                  cheats=sum(g['cheat_count'] for g in result['games']),
                  available=sum(g['available_count'] for g in result['games']),
                  download_bytes=sum(p['size'] for p in packs))
    result.pop('revision', None)
    result['revision'] = sha(canonical(result))
    return result, changed, removed, sorted(dropped_games)


def withdraw_rejections(path=DIRECTORY / 'supplement478-native-rejections.json.gz'):
    """Rejected-program records of the 478 import carry full code bodies:
    drop those of the withheld sources (and the 3 illusion programs)."""
    rows = json.loads(gzip.decompress(path.read_bytes()))
    kept = [r for r in rows if not withdrawn(r['program'])]
    path.write_bytes(gzip_bytes(canonical(kept)))
    return len(rows) - len(kept)


def main():
    baseline = BUNDLE.read_bytes()
    assert sha(baseline) == BASE_INDEX, 'Run only against the reviewed index of 28 October 2026'
    assert (DIRECTORY / 'manifest.json.gz').read_bytes() == baseline
    index, changed, removed, dropped = withdraw(
        json.loads(gzip.decompress(baseline)),
        lambda p: (DIRECTORY / p).read_bytes(), lambda p, b: (DIRECTORY / p).write_bytes(b))
    packed = gzip_bytes(canonical(index))
    (DIRECTORY / 'manifest.json.gz').write_bytes(packed)
    BUNDLE.write_bytes(packed)
    for p in changed:
        (DIRECTORY / p['old']).unlink()
    validate(DIRECTORY)
    rejections = withdraw_rejections()
    receipt = {'baselineIndexSHA256': BASE_INDEX, 'manifestSHA256': sha(packed),
               'removedPrograms': removed, 'removedTransportRecords': dropped,
               'removedRejectionRecords': rejections,
               'withheldIllusionPrograms': sorted(ILLUSION_DIFFERS), 'relicensedIllusionPrograms': 280,
               'preservedPacks': len(index['packs']) - len(changed), 'replacedPacks': changed,
               'totals': index['totals'], 'reason': REASON, 'existingIPAsChanged': False}
    (ROOT / 'docs/evidence/source-rights-withdrawal-fps478.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({k: v for k, v in receipt.items() if k != 'replacedPacks'}, indent=2))


if __name__ == '__main__':
    main()
