#!/usr/bin/env python3
"""Imports ARMSX2's PS2 texture pack catalogue (ps2ktxpak) as manual entries.

ps2ktxpak (https://github.com/ps2ktxpak/catalog, MIT, data included) records
for each PS2 pack its creators, the pages where it is announced, what it
costs and whether a copy may be hosted. NeoStation keeps only what it needs
to send the user to the creator's own page:

  - free packs only (cost "free" or "free_with_ads"); a paid pack, or a pack
    whose cost is not recorded, is left out;
  - packs whose creators are named (an empty credit list is left out);
  - the creator's page: the primary source when it is an announcement page
    (forum thread, creator or repository page), never a file host or an
    archive mirror (archive.org, MediaFire, Mega, Drive...) and never
    ps2ktxpak's own stored copy, which is not the creator's distribution;
  - packs that ps2ktxpak marks withdrawn, disputed or revoked are left out;
  - game serials checked against PCSX2's GameIndex.yaml. A pack recorded
    without a serial gets the serials whose GameIndex title is its game's
    title (in its recorded region), marked "confirm": they come from a game
    database, not from the creator;
  - packs already in tools/textures/sources (same page or repository) are
    not imported twice.

Every entry is "manual": NeoStation opens the creator's page and never
downloads, hosts or redistributes the files. Nothing is verified beyond the
records: the page was not opened from the verification environment (its
reachability is checked by discover.py links).

  python3 tools/textures/import_ps2ktxpak.py --catalog <clone> --gameindex <GameIndex.yaml> \
      --commit <ps2ktxpak commit> --gameindex-commit <pcsx2 commit>

writes tools/textures/sources/ps2-ps2ktxpak.json and prints what was left out
and why (also written to tools/textures/ps2ktxpak-report.json).
"""
import argparse
import glob
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
SOURCES = HERE / 'sources'
OUT = SOURCES / 'ps2-ps2ktxpak.json'
REPORT = HERE / 'ps2ktxpak-report.json'
# Announcement pages a manual entry may open. File hosts and archive mirrors are not pages of the creator.
PAGE_HOSTS = {'gbatemp.net', 'github.com', 'www.moddb.com', 'moddb.com', 'ostrichmods.com', 'ko-fi.com', 'www.gtplanet.net',
              'www.reddit.com', 'raymanpc.com', 'www.onihdrp.com', 'libertycity.net', 'www.patreon.com', 'patreon.com'}
REGION_NAMES = {'NTSC-U': 'USA', 'NTSC-J': 'Japan', 'NTSC-K': 'Korea', 'NTSC-C': 'China', 'NTSC-Unk': None}
TYPE_NAMES = {'ai_upscale': 'AI upscale', 'handcrafted': 'Handcrafted', 'mixed': 'AI upscale and handcrafted',
              'port': 'Port of another version\'s textures', 'button_replacement': 'Button prompt replacement'}
COMPLETENESS = {'complete': 'complete', 'in_progress': 'work in progress', 'incomplete': 'incomplete', 'partial': 'partial'}
NOT_RETAIL = re.compile(r'\b(demo|beta|trial|prototype|kiosk|taikenban|preview|sample|promo|debug)\b', re.I)
ROMAN = {'ii': '2', 'iii': '3', 'iv': '4', 'v': '5', 'vi': '6', 'vii': '7', 'viii': '8', 'ix': '9', 'x': '10', 'xi': '11', 'xii': '12'}


def normalize(title):
    text = unicodedata.normalize('NFKD', title).encode('ascii', 'ignore').decode().lower()
    text = text.replace('&', ' and ')
    text = re.sub(r"[’'`]", '', text)
    text = re.sub(r'[^a-z0-9]+', ' ', text)
    words = [ROMAN.get(word, word) for word in text.split()]
    if words and words[0] == 'the':
        words = words[1:]
    return ' '.join(words)


def region_of(gameindex_region):
    if gameindex_region.startswith('PAL'):
        return 'Europe'
    return REGION_NAMES.get(gameindex_region)


def wanted(gameindex_region, recorded):
    if not recorded or 'multi' in recorded:
        return True
    for region in recorded:
        if region == 'PAL' and gameindex_region.startswith('PAL'):
            return True
        if region == gameindex_region:
            return True
    return False


def load_gameindex(path):
    index, current = {}, None
    for line in open(path, encoding='utf-8'):
        match = re.match(r'^([A-Z]{4}-\d{5}):\s*$', line)
        if match:
            current = match.group(1)
            index[current] = {}
            continue
        if current:
            match = re.match(r'^  (name|region|name-en):\s*"?(.*?)"?\s*$', line)
            if match:
                index[current][match.group(1)] = match.group(2)
    return index


def host(url):
    match = re.match(r'^https://([^/]+)/', url or '')
    return match.group(1).lower() if match else ''


def canonical(url):
    url = (url or '').strip().rstrip('/')
    url = re.sub(r'^https?://(www\.)?', 'https://', url)
    url = re.sub(r'/(releases|tree)(/.*)?$', '', url) if 'github.com/' in url else url
    return url.lower()


def existing_pages():
    pages = set()
    for path in sorted(SOURCES.glob('*.json')):
        if path.name in ('excluded.json', OUT.name):
            continue
        for entry in json.loads(path.read_text(encoding='utf-8')):
            pages.add(canonical(entry['page_url']))
            source = entry.get('source_id', '')
            if source.startswith('github:'):
                pages.add(canonical('https://github.com/' + source[7:]))
            download = entry.get('download') or {}
            if download.get('page'):
                pages.add(canonical(download['page']))
    return pages


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--catalog', required=True)
    parser.add_argument('--gameindex', required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--gameindex-commit', required=True)
    args = parser.parse_args()
    gameindex = load_gameindex(args.gameindex)
    by_title = defaultdict(list)
    for serial, game in gameindex.items():
        name = game.get('name-en') or game.get('name') or ''
        if name and not NOT_RETAIL.search(name):
            by_title[normalize(re.sub(r'\s*\[[^\]]*\]', '', name))].append(serial)
    creators = {}
    for path in glob.glob(str(Path(args.catalog) / 'data/creators/*.yaml')):
        creator = yaml.safe_load(open(path, encoding='utf-8'))
        creators[creator['id']] = creator
    known = existing_pages()
    entries, skipped, seen = [], Counter(), {}
    details = defaultdict(list)
    for path in sorted(glob.glob(str(Path(args.catalog) / 'data/packs/*.yaml'))):
        pack = yaml.safe_load(open(path, encoding='utf-8'))
        key = pack['key']

        def skip(reason):
            skipped[reason] += 1
            details[reason].append(key)

        state = (pack.get('hosting') or {}).get('state')
        if state not in ('published', 'listed'):
            skip(f'hosting state {state}')
            continue
        if (pack.get('permission') or {}).get('kind') == 'revoked':
            skip('permission revoked')
            continue
        cost = (pack.get('access') or {}).get('cost')
        if cost not in ('free', 'free_with_ads'):
            skip('paid' if cost == 'paid' else 'cost not recorded')
            continue
        names = []
        for credit in pack.get('credits') or []:
            creator = creators.get(credit.get('creator'))
            if not creator or creator.get('status') != 'active':
                names = []
                break
            names.append(creator['name'][:120])
        if not names:
            skip('creator not named or withdrawn')
            continue
        sources = [s for s in pack.get('sources') or [] if s.get('url', '').startswith('https://')]
        sources.sort(key=lambda s: not s.get('primary'))
        page = next((s['url'] for s in sources if host(s['url']) in PAGE_HOSTS and s.get('kind') != 'mirror'
                     and not (host(s['url']).endswith('patreon.com') and cost != 'free')), None)
        if not page:
            skip('no announcement page of the creator (file host or archive mirror only)')
            continue
        if any(canonical(s['url']) in known for s in sources) or canonical(page) in known:
            skip('already in the catalogue')
            continue
        game = pack.get('game') or {}
        title = (game.get('title') or '').strip()
        serials = [s.upper() for s in game.get('serials') or []]
        confirm = False
        if serials:
            unknown = [s for s in serials if s not in gameindex]
            serials = [s for s in serials if s in gameindex]
            if unknown and not serials:
                skip('serial not in GameIndex')
                continue
        else:
            regions = game.get('regions') or []
            serials = sorted(s for s in by_title.get(normalize(title), []) if wanted(gameindex[s].get('region', ''), regions))
            confirm = True
            if not serials:
                skip('no serial recorded and no GameIndex title match')
                continue
            if len(serials) > 16:
                skip('title matches more than 16 serials')
                continue
        if not title or len(title) > 200:
            skip('game title')
            continue
        name = (pack.get('name') or title).strip()
        signature = (canonical(page), normalize(name), tuple(serials))
        if signature in seen:
            skip('duplicate of another ps2ktxpak record (same page, name and serials)')
            continue
        seen[signature] = key
        regions = sorted({r for r in (region_of(gameindex[s].get('region', '')) for s in serials) if r})
        notes = []
        kind = TYPE_NAMES.get(pack.get('type'))
        done = COMPLETENESS.get(pack.get('completeness'))
        if kind or done:
            sentence = ', '.join(x for x in (kind, done) if x)
            notes.append(sentence[0].upper() + sentence[1:] + '.')
        if pack.get('description'):
            description = re.sub(r'\s+', ' ', pack['description']).strip()
            notes.append(description[:300] + ('…' if len(description) > 300 else ''))
        review = pack.get('needs_review') or []
        if 'co_credit_unconfirmed' in review:
            notes.append('Co-credit not yet confirmed by the catalogue.')
        if 'credit_assigned_from_listing' in review:
            notes.append('Credit taken from a listing, not yet confirmed by the catalogue.')
        if confirm:
            notes.append('The creator\'s record names no serial: the serials are those of the game in PCSX2\'s database, '
                         'to confirm against your disc.')
        if cost == 'free_with_ads':
            notes.append('The creator\'s download link shows advertising.')
        notes.append(f'Listed in ps2ktxpak, ARMSX2\'s PS2 texture pack catalogue (MIT), commit {args.commit[:8]}.')
        # A "snapshot" version names the copy ps2ktxpak stored, not a release of the creator.
        version = str(pack.get('version') or '').strip()
        if not version or 'snapshot' in version.lower():
            version = 'See the creator\'s page'
        identities = [{'type': 'serial', 'scheme': 'ps2-disc-serial', 'value': s} for s in serials]
        game_entry = {'title': title, 'identities': identities}
        if regions:
            game_entry['regions'] = regions
        if confirm:
            game_entry['confirm'] = True
        page_host = host(page)
        if page_host == 'github.com':
            parts = page.split('/')
            source_id = 'github:' + '/'.join(parts[3:5])
        else:
            lead = (pack.get('credits') or [{}])[0].get('creator')
            source_id = f'creator:{creators[lead]["name"]}'
        entry = {
            'id': f'ps2-ktx-{key}'[:120],
            'title': name[:200],
            'version': version,
            'games': [game_entry],
            'authors': names,
            'page_url': page,
            'source_id': source_id,
            'licence': {
                'summary': 'Free on the creator\'s page; no licence recorded' if cost == 'free'
                           else 'Free on the creator\'s page (download link with advertising); no licence recorded',
                'redistribution': 'Link only: NeoStation opens the creator\'s page and does not download, host or redistribute this pack.',
            },
            'notes': ' '.join(notes),
            'download': {'automatable': False, 'page': page},
            'system': 'ps2',
            'engine': 'armsx2',
            'availability': 'manual',
        }
        creator_page = ((creators[(pack.get('credits') or [{}])[0].get('creator')].get('links') or {}).get('page') or '')
        if creator_page.startswith('https://') and page_host != 'github.com':
            entry['source_url'] = creator_page
        entries.append(entry)
    OUT.write_text(json.dumps(entries, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
    report = {'catalog': 'https://github.com/ps2ktxpak/catalog', 'commit': args.commit, 'licence': 'MIT (data included)',
              'gameindex': 'https://github.com/PCSX2/pcsx2/blob/master/bin/resources/GameIndex.yaml',
              'gameindex_commit': args.gameindex_commit, 'imported': len(entries),
              'left_out': dict(sorted(skipped.items(), key=lambda item: -item[1])),
              'left_out_keys': {reason: sorted(keys) for reason, keys in sorted(details.items())}}
    REPORT.write_text(json.dumps(report, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f'imported {len(entries)} manual PS2 entries; left out: {dict(skipped)}')


if __name__ == '__main__':
    sys.exit(main())
