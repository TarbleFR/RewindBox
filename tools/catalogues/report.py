#!/usr/bin/env python3
"""Counts of RewindBox's catalogues, read from the generated files only.

  python3 tools/catalogues/report.py                 the working tree
  python3 tools/catalogues/report.py --git <rev>     the files of a commit
  python3 tools/catalogues/report.py --compare <rev> the commit, the working tree and the difference
  python3 tools/catalogues/report.py --json          the figures as JSON

Every figure comes from a published file: the cheat index
(native/cheats/catalogue/v2/manifest.json.gz), the enhancements index bundled
in the app and the shards it lists, the HD texture manifest, and the two
shader catalogues. Nothing is estimated and nothing is fetched.

What the words mean here:
  installable   the app installs it itself: a cheat program of the unified
                catalogue, an enhancement entry, a one-tap HD pack (verified
                download), a shader preset;
  by reference  installable, but the bytes are downloaded from the source at
                a pinned revision and checked; RewindBox hosts names and
                pointers only (origin);
  page link     an HD pack listed with its author's page: the app opens the
                page, it downloads nothing.
Counts of different catalogues, and of overlapping sources, do not add up.
"""
import argparse
import gzip
import hashlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENHANCEMENTS_BASE = 'https://raw.githubusercontent.com/TarbleFR/RewindBox/Claude/native/enhancements/catalogue/'


class Tree:
    """Files of the working tree, or of a commit."""

    def __init__(self, revision=None):
        self.revision = revision

    def read(self, path):
        if self.revision is None:
            target = ROOT / path
            return target.read_bytes() if target.exists() else None
        result = subprocess.run(['git', 'show', f'{self.revision}:{path}'], cwd=ROOT, capture_output=True)
        return result.stdout if result.returncode == 0 else None

    def json(self, path):
        data = self.read(path)
        if data is None:
            return None
        return json.loads(gzip.decompress(data) if data[:2] == b'\x1f\x8b' else data)


def cheats(tree):
    manifest = tree.json('native/cheats/catalogue/v2/manifest.json.gz')
    if manifest is None:
        return None
    hosted_only = sum(1 for pack in manifest['packs'] if not pack.get('origin'))
    return {'revision': manifest['revision'][:12], 'sources': len(manifest['sources']),
            'programs': manifest['totals']['programs'], 'identity_groups': manifest['totals']['identity_groups'],
            'transport_records': len(manifest['games']), 'packs': len(manifest['packs']),
            'packs_with_origin_recipes': len(manifest['packs']) - hosted_only,
            'systems': len({game['system'] for game in manifest['games']})}


def enhancements(tree):
    index = tree.json('assets/data/enhancements_index.json.gz')
    if index is None:
        return None
    folder = 'native/enhancements/catalogue/' + index['base_url'][len(ENHANCEMENTS_BASE):]
    unhosted = {source['id'] for source in index['sources'] if source.get('origin')}
    by_engine, by_source, referenced, hosted = {}, Counter(), 0, 0
    for name, meta in sorted(index['shards'].items()):
        data = tree.read(folder + meta['path'])
        if data is None or hashlib.sha256(data).hexdigest() != meta['sha256']:
            raise SystemExit(f'enhancements: shard {name} is missing or does not match the index')
        for record in json.loads(gzip.decompress(data))['keys'].values():
            for entry in record['entries']:
                by_source[entry['source']] += 1
                if entry['source'] in unhosted:
                    referenced += 1
                else:
                    hosted += 1
    for engine, totals in index['totals'].items():
        by_engine[engine] = {'games': totals['keys'], 'entries': sum(totals['entries'].values()), **totals['entries']}
    return {'revision': index['revision'], 'sources': len(index['sources']),
            'games': sum(engine['games'] for engine in by_engine.values()),
            'entries': sum(engine['entries'] for engine in by_engine.values()),
            'entries_hosted_or_shipped_by_the_engine': hosted, 'entries_by_reference': referenced,
            'by_engine': by_engine, 'by_source': dict(sorted(by_source.items()))}


def textures(tree):
    manifest = tree.json('native/textures/catalogue/manifest.json.gz')
    if manifest is None:
        return None
    one_tap, page, by_system = 0, 0, {}
    for pack in manifest['packs']:
        installable = pack.get('availability') == 'available' or bool((pack.get('download') or {}).get('in_app'))
        one_tap += installable
        page += not installable
        counts = by_system.setdefault(pack['system'], {'one_tap': 0, 'page_link': 0})
        counts['one_tap' if installable else 'page_link'] += 1
    arguments = [sys.executable, str(ROOT / 'tools/textures/count_packs.py'), '--json']
    if tree.revision:
        arguments += ['--git', tree.revision]
    families = None
    counted = subprocess.run(arguments, cwd=ROOT, capture_output=True, text=True)
    if counted.returncode == 0:
        try:
            families = json.loads(counted.stdout[counted.stdout.index('{'):]).get('total', {}).get('distinct')
        except (ValueError, AttributeError):
            families = None
    return {'revision': manifest['revision'], 'references': len(manifest['packs']), 'sources': len(manifest['sources']),
            'one_tap_profiles': one_tap, 'one_tap_distinct_families': families, 'page_links': page,
            'by_system': dict(sorted(by_system.items()))}


def shaders(tree):
    out = {}
    for engine, name in (('libretro_slang', 'slang-catalog.json'), ('dolphin', 'dolphin-catalog.json')):
        catalog = tree.json('packages/neo_shader_kit/ios/Resources/' + name)
        if catalog is None:
            continue
        layers = [catalog] + list(catalog.get('additions') or [])
        entries = [entry for layer in layers for entry in layer.get('entries') or []]
        out[engine] = {'sources': [(layer.get('source') or {}).get('commit', '')[:12] for layer in layers],
                       'presets': len(entries),
                       'files': sum(len(layer.get('files') or []) for layer in layers),
                       'validation': dict(Counter(entry.get('validation', '') for entry in entries)),
                       'bundled_with_the_engine': sum(1 for entry in entries if entry.get('bundled'))}
    return out or None


def collect(tree):
    return {'cheats': cheats(tree), 'enhancements': enhancements(tree), 'textures': textures(tree), 'shaders': shaders(tree)}


def flat(value, prefix=''):
    """{dotted key: number} of the countable figures."""
    out = {}
    if isinstance(value, dict):
        for key, item in value.items():
            out.update(flat(item, f'{prefix}{key}.'))
    elif isinstance(value, bool):
        pass
    elif isinstance(value, (int, float)):
        out[prefix[:-1]] = value
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--git', help='a commit instead of the working tree')
    parser.add_argument('--compare', help='a commit to compare the working tree with')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    if args.compare:
        before, after = collect(Tree(args.compare)), collect(Tree())
        if args.json:
            print(json.dumps({'before': before, 'after': after}, indent=1))
            return
        a, b = flat(before), flat(after)
        print(f'{"figure":<58} {"before":>10} {"after":>10} {"change":>9}')
        for key in sorted(set(a) | set(b), key=lambda k: (k.split('.')[0], k)):
            x, y = a.get(key, 0), b.get(key, 0)
            change = y - x
            print(f'{key:<58} {x:>10,} {y:>10,} {("+" if change > 0 else "") + format(change, ",") if change else "":>9}')
        return
    figures = collect(Tree(args.git))
    if args.json:
        print(json.dumps(figures, indent=1))
        return
    for key, value in sorted(flat(figures).items(), key=lambda item: (item[0].split('.')[0], item[0])):
        print(f'{key:<58} {value:>10,}')


if __name__ == '__main__':
    main()
