#!/usr/bin/env python3
"""Counts the installable packs of an HD texture index the way the Build 489 request does.

Installable = one tap (availability "available") or a manual pack whose exact file
was verified on CI (download.verified). Resolutions, formats, updates, region dumps,
mirrors and button/style variants of one pack count once: packs are grouped into
families (the "family" of the source entry; for older entries the id without its
resolution/format words, plus the explicit groups below). Each family has a scope:
complete, partial (a part of the game) or ui (interface, fonts, buttons, icons).

  python3 tools/textures/count_packs.py [--index <manifest.json.gz>] [--git <rev>] [--json]
"""
import argparse
import collections
import gzip
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCES = ROOT / 'tools/textures/sources'
INDEX = 'native/textures/catalogue/manifest.json.gz'
CONSOLES = ['gc', 'wii', '3ds', 'psp', 'ps2', 'n64', 'ps1', 'nes']
VARIANT_WORDS = {'4k', '1080', '1080p', '720p', '1440p', '2160p', 'dds', 'png', 'bc7', 'bc3', 'bc1', '2x', '3x', '4x', '8x', '16x',
                 'hd', 'uhd', 'ktx', 'ktx2', 'astc', 'light', 'pack', 'fullres', 'eu', 'us', 'jp'}
# Older entries whose variants differ by more than a resolution word (style, region dump, aspect).
GROUPS = [
    (r'^gc-ttyd-button-labels-', 'gc-ttyd-button-labels-pictocat'),
    (r'^psp-gta-lcs-weapon-icons-', 'psp-gta-lcs-weapon-icons'),
    (r'^psp-gta-vcs-weapon-icons-', 'psp-gta-vcs-weapon-icons'),
    (r'^psp-peggle-hd-', 'psp-peggle-hd'),
    (r'^psp-patapon2-remastered-', 'psp-patapon2-remastered'),
    (r'^ps2-burnout3-buttons-', 'ps2-burnout3-buttons-feralai'),
    (r'^ps2-burnout-revenge-buttons-', 'ps2-burnout-revenge-buttons-feralai'),
    (r'^ps2-mh2dos-hdui-paulbury-', 'ps2-mh2dos-hdui-paulbury'),
    (r'^ps2-gta-vcs-asi-factory-', 'ps2-gta-vcs-asi-factory'),
    (r'^n64-f-zero-x-hq-pilot-portraits', 'n64-f-zero-x-hq-pilot-portraits'),
]
# Scope of the older entries that are not complete packs (new entries carry their own).
SCOPE = {
    'ui': ['gc-ttyd-button-labels-pictocat', 'gc-star-fox-adventures-hd-font-calinou', 'gc-sms-hd-texture-extras-chasem',
           'psp-burnout-legends-hd-ui-testietendie', 'psp-fate-extra-jp-hd-font-sieben5106', 'psp-gta-chinatown-wars-sonofugly',
           'psp-gta-lcs-weapon-icons', 'psp-gta-vcs-weapon-icons', 'psp-ridge-racer-2-rrv-hud-amame-a', 'psp-wipeout-pure-retokyo',
           'ps2-burnout3-buttons-feralai', 'ps2-burnout-revenge-buttons-feralai', 'ps2-burnout3-hd-vehicle-icons-goatsevens',
           'ps2-burnout-revenge-enhanced-interface-goatsevens', 'ps2-mgs2-hd-ui-nathanhigley', 'ps2-mh2dos-hdui-paulbury',
           'ps2-dynamite-deka-english-seonggino', '3ds-mh4u-hd-ui-xl3lackout', '3ds-oot3d-chinese-hd-font-map-linkfish1',
           '3ds-oot3d-chinese-hd-font-map-remake-wee2002', '3ds-pokemon-y-hd-text-only'],
    'partial': ['n64-f-zero-x-hq-pilot-portraits', 'n64-sm64-hires-fonts-paintings-fanfreluche', 'ps2-gta-vcs-asi-factory',
                'psp-gta-vcs-asi-factory'],
}
SCOPE_OF = {family: scope for scope, families in SCOPE.items() for family in families}


def installable(pack):
    return pack['availability'] == 'available' or (pack['availability'] == 'manual' and (pack.get('download') or {}).get('verified'))


def sources():
    found = {}
    for path in SOURCES.glob('*.json'):
        if path.name.startswith('excluded'):
            continue
        for entry in json.loads(path.read_text(encoding='utf-8')):
            found[entry['id']] = entry
    return found


def family(pack, entries):
    entry = entries.get(pack['id']) or {}
    if entry.get('family'):
        return entry['family']
    for pattern, name in GROUPS:
        if re.search(pattern, pack['id']):
            return name
    return '-'.join(word for word in pack['id'].split('-') if word not in VARIANT_WORDS)


def scope(pack, name, entries):
    entry = entries.get(pack['id']) or {}
    return entry.get('scope') or SCOPE_OF.get(pack['id']) or SCOPE_OF.get(name) or 'complete'


def count(index, entries):
    per = {console: {'entries': 0, 'families': {}, 'games': set()} for console in CONSOLES}
    for pack in index['packs']:
        if not installable(pack):
            continue
        name = family(pack, entries)
        for console in [pack['system']] + [s for s in pack.get('systems') or [] if s != pack['system']]:
            if console not in per:
                continue
            item = per[console]
            item['entries'] += 1
            item['families'].setdefault(name, {'scope': scope(pack, name, entries), 'variants': 0, 'manual': True})
            item['families'][name]['variants'] += 1
            if pack['availability'] == 'available':
                item['families'][name]['manual'] = False
            for game in pack['games']:
                item['games'].add(game['identities'][0]['value'].upper()[:3 if console in ('gc', 'wii') else None])
    result = {}
    for console, item in per.items():
        scopes = collections.Counter(f['scope'] for f in item['families'].values())
        result[console] = {'distinct': len(item['families']), 'entries': item['entries'],
                           'variants': item['entries'] - len(item['families']),
                           'complete': scopes['complete'], 'partial': scopes['partial'], 'ui': scopes['ui'],
                           'oneTapFamilies': sum(1 for f in item['families'].values() if not f['manual']),
                           'manualVerifiedFamilies': sum(1 for f in item['families'].values() if f['manual']),
                           'games': len(item['games']), 'families': sorted(item['families'])}
    # A pack listed for two consoles (Wii Virtual Console packs that also serve the GameCube discs)
    # appears in both rows; the total counts each family and each entry once.
    families = {}
    for item in per.values():
        families.update(item['families'])
    scopes = collections.Counter(f['scope'] for f in families.values())
    entries_total = sum(1 for pack in index['packs'] if installable(pack))
    result['total'] = {'distinct': len(families), 'entries': entries_total, 'variants': entries_total - len(families),
                       'complete': scopes['complete'], 'partial': scopes['partial'], 'ui': scopes['ui'],
                       'oneTapFamilies': sum(1 for f in families.values() if not f['manual']),
                       'manualVerifiedFamilies': sum(1 for f in families.values() if f['manual']),
                       'games': len({g for item in per.values() for g in item['games']}), 'families': sorted(families)}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--index', default=str(ROOT / INDEX))
    parser.add_argument('--git', help='read the index of this revision instead')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    data = (subprocess.run(['git', '-C', str(ROOT), 'show', f'{args.git}:{INDEX}'], check=True, capture_output=True).stdout
            if args.git else Path(args.index).read_bytes())
    index = json.loads(gzip.decompress(data))
    result = count(index, sources())
    if args.json:
        print(json.dumps(result, indent=1))
        return
    print(f'index {index["revision"]}: installable packs counted once per family')
    print(f'{"console":8} {"distinct":>8} {"entries":>8} {"variants":>8} {"complete":>8} {"partial":>8} {"ui":>4} {"oneTap":>7} {"manual✓":>8} {"games":>6}')
    for console in CONSOLES + ['total']:
        r = result[console]
        print(f'{console:8} {r["distinct"]:8} {r["entries"]:8} {r["variants"]:8} {r["complete"]:8} {r["partial"]:8} {r["ui"]:4} '
              f'{r["oneTapFamilies"]:7} {r["manualVerifiedFamilies"]:8} {r["games"]:6}')


if __name__ == '__main__':
    sys.exit(main())
