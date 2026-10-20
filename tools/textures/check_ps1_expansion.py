#!/usr/bin/env python3
"""Verify the PS1 publication using real CI records and the previous catalogue.

This is a metadata gate: it never downloads a texture archive or counts a
protected/manual author reference as an installed pack. Foundation validates
the same bundled index and disc matching in the separate native job.
"""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_catalogue as catalogue
import count_packs

BASE = '64e73bcfdcaa66067b7a8edfea0e8852faa0d43a'
PREVIOUS = '15f5317a83ec14ba66e66285065a99cee9e302f7'
PREVIOUS_EXPANDED = '388f5c5194c5ace2e26ee2753ce1ab221756c512'
INDEX = 'native/textures/catalogue/manifest.json.gz'
BUNDLED = 'packages/neo_texture_catalog/ios/Resources/manifest.json.gz'
NEW_SOURCES = ['tools/textures/sources/ps1-expansion.json',
               'tools/textures/sources/ps1-ironhulk33.json',
               'tools/textures/sources/ps1-author-pages.json']
SUCCESSES = {'ps1-linnaealyn-xenogears-perfect-art-works': 399,
             'ps1-faospark-suikoden-ii-project-kyaro': 437,
             'ps1-nr74w-wipeout': 100,
             'ps1-nr74w-wipeout-2097-xl': 89,
             'ps1-somber-twilight-tenchu-stealth-assassins': 1757,
             'ps1-cac-gamer-gran-turismo-2-tahiti-x8': 233}
OBSERVATIONS = [(39475381324, '0ed658654bd6edbb44257762421d7867d79d26b7', 2),
                (39475695835, '070557e734dec9c1aa064fea11967afc525b9148', 10),
                (39479736059, '0a2fdbabeaf3802b9abe7aa8e05d74f2c00f4d1b', 4),
                (39482826008, '0cd67e5830f271a7dc6010b55a893c74af2c01be', 2),
                (39483666586, 'fba188684d75867808eaa2de9c122fc19fcfdad3', 1)]


def input_paths():
    return sorted(NEW_SOURCES + [INDEX, BUNDLED,
        'tools/textures/sources/ps1.json', 'tools/textures/build_catalogue.py',
        'tools/textures/count_packs.py', 'tools/textures/check_ps1_expansion.py',
        'tools/textures/verified.jsonl', 'tools/textures/ci-records.json',
        '.github/workflows/hd-textures.yml', 'test/texture_direct_host_publication_test.py',
        'test/texture_catalog_native_test.py',
        *[f'docs/evidence/ps1-hd-ci/{run}.jsonl' for run, _, _ in OBSERVATIONS]])


def git_bytes(path):
    return subprocess.check_output(['git', 'show', f'{BASE}:{path}'], cwd=ROOT)


def verify(baseline_file=None, previous_file=None, previous_expanded_file=None):
    old_raw = baseline_file.read_bytes() if baseline_file else git_bytes(INDEX)
    before = json.loads(gzip.decompress(old_raw))
    raw = (ROOT / INDEX).read_bytes()
    assert raw == (ROOT / BUNDLED).read_bytes(), 'Hosted and bundled catalogues differ'
    after = json.loads(gzip.decompress(raw))
    entries, records = catalogue.load()
    rebuilt, excluded, pending = catalogue.build(entries, records)
    catalogue.validate(after)
    assert not pending and catalogue.serialize(rebuilt)[1] == raw, 'Catalogue is stale or pending'
    old = {p['id']: p for p in before['packs']}
    new = {p['id']: p for p in after['packs']}
    assert len(old) == 1088 and len(new) == len(after['packs']) == 1123
    assert all(new.get(key) == value for key, value in old.items()), 'A pre-existing pack changed'
    previous_raw = previous_file.read_bytes() if previous_file else subprocess.check_output(
        ['git', 'show', f'{PREVIOUS}:{INDEX}'], cwd=ROOT)
    previous = json.loads(gzip.decompress(previous_raw))
    assert len(previous['packs']) == 1112
    assert all(new.get(p['id']) == p for p in previous['packs']), 'A previous 26-reference catalogue object changed'
    previous_expanded_raw = previous_expanded_file.read_bytes() if previous_expanded_file else subprocess.check_output(
        ['git', 'show', f'{PREVIOUS_EXPANDED}:{INDEX}'], cwd=ROOT)
    previous_expanded = json.loads(gzip.decompress(previous_expanded_raw))
    assert len(previous_expanded['packs']) == 1120
    assert all(new.get(p['id']) == p for p in previous_expanded['packs']), 'A previous 32-reference catalogue object changed'
    staged = [p for path in NEW_SOURCES for p in json.loads((ROOT / path).read_text())]
    assert len(staged) == len({p['id'] for p in staged}) == 35
    assert set(new) - set(old) == {p['id'] for p in staged}, 'Unexpected addition outside PS1'
    assert all(p['system'] == 'ps1' and p['engine'] == 'beetle' for p in staged)
    assert sum(p['system'] == 'ps1' for p in after['packs']) == 37
    direct = [p for p in staged if p['id'] in SUCCESSES]
    assert len(direct) == 6
    for entry in direct:
        identifier = entry['id']
        record, published = records[identifier], new[identifier]
        assert record['status'] == 'ok'
        spec = published['download'].get('in_app') or published['download']
        assert spec['automatable'] is True
        assert [{k: part[k] for k in ('url', 'size', 'sha256')} for part in spec['parts']] == record['parts']
        if record.get('host') in ('mega', 'gdrive'):
            assert published['availability'] == 'manual' and published['download']['automatable'] is False
            assert all(part['provider'] == record['host'] for part in spec['parts'])
            assert all(game.get('confirm') is True for game in published['games'])
        else:
            assert published['availability'] == 'available'
        assert published['install']['files'] == SUCCESSES[identifier]
        assert published['install']['folders'][0]['to'] == '{id}'
        for checks in record['checks'].values():
            assert checks['textures'] == checks['pngChecked'] == SUCCESSES[identifier]
            assert checks['subfolders'] == 0 and not checks['badPng']
    manual = [p for p in staged if p['id'] not in SUCCESSES]
    assert len(manual) == 29
    for entry in manual:
        published = new[entry['id']]
        assert published['availability'] == 'manual'
        assert published['download'] == {'automatable': False}
        assert 'install' not in published and 'verified_at' not in published
        assert all(g.get('confirm') is True for g in published['games'])
    registered = json.loads((ROOT / 'tools/textures/ci-records.json').read_text())['runs']
    observed = set()
    for run, source, count in OBSERVATIONS:
        matches = [r for r in registered if r['run'] == run]
        assert len(matches) == 1 and matches[0]['source'] == source
        assert matches[0]['consoles'] == ['ps1'] and matches[0]['records'] == count
        rows = (ROOT / f'docs/evidence/ps1-hd-ci/{run}.jsonl').read_text().splitlines()
        assert len(rows) == count
        for line in rows:
            record = json.loads(line)
            assert records[record['id']] == record, 'Canonical record differs from CI artifact'
            assert record['id'] not in observed
            observed.add(record['id'])
            assert record['status'] == ('ok' if record['id'] in SUCCESSES else 'protected')
    assert len(observed) == 19
    if not baseline_file:
        current = (ROOT / 'tools/textures/verified.jsonl').read_bytes()
        assert current.startswith(git_bytes('tools/textures/verified.jsonl')), 'Original canonical records changed'
        old_runs = json.loads(git_bytes('tools/textures/ci-records.json'))['runs']
        assert registered[:len(old_runs)] == old_runs and len(registered) == len(old_runs) + 5
    counts = count_packs.count(after, count_packs.sources())
    assert counts['ps1']['oneTapFamilies'] == counts['ps1']['distinct'] == 8
    assert counts['total']['distinct'] == counts['total']['oneTapFamilies'] == 424
    assert counts['total']['entries'] == 509
    return {
        'passed': True, 'baseline': BASE, 'revision': after['revision'],
        'catalogue_sha256': hashlib.sha256(raw).hexdigest(),
        'existing_pack_objects_unchanged': len(old), 'previous_catalogue_objects_unchanged': 1112,
        'previous_expanded_catalogue_objects_unchanged': 1120,
        'new_ps1_references': 35,
        'new_verified_one_tap': 6, 'new_manual_author_references': 29,
        'ps1_total': 37, 'ps1_verified_one_tap_total': 8,
        'new_pngs_verified': sum(SUCCESSES.values()),
        'archive_observations': {'ok': 6, 'protected': 13},
        'total_one_tap_families': 424, 'total_installable_profiles': 509,
        'physical_device_validated': False,
        'source': os.environ.get('GITHUB_SHA'),
        'run': int(os.environ['GITHUB_RUN_ID']) if os.environ.get('GITHUB_RUN_ID') else None,
        'inputs_sha256': {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in input_paths()},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-file', type=Path, help='Local read-only snapshot check, never used by CI/delivery')
    parser.add_argument('--previous-file', type=Path, help='Local previous 26-reference snapshot, never used by CI/delivery')
    parser.add_argument('--previous-expanded-file', type=Path, help='Local previous 32-reference snapshot, never used by CI/delivery')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report = verify(args.baseline_file, args.previous_file, args.previous_expanded_file)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    main()
