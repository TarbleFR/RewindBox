#!/usr/bin/env python3
"""Build the RewindBox Cheats & Enhancements catalogue.

The catalogue only references formats each embedded engine already reads:

* MeloNX (Ryujinx): Atmosphere cheat files, keyed by Title ID and Build ID.
* RPCS3: patch.yml 1.2 entries, keyed by PPU hash, serial and APP_VER.
* ARMSX2 (PCSX2): .pnach files, keyed by serial and boot ELF CRC.
* Dolphin: [OnFrame] patches of the engine's own Sys/GameSettings, by name.

Inputs are pinned (git revisions or a content SHA-256). No game, BIOS,
firmware or key is read or written. Usage:

  python3 tools/enhancements/build_enhancement_catalog.py --cache /tmp/enh-cache

`--offline` requires every input in the cache.
"""
import argparse
import datetime
import gzip
import hashlib
import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from classify import classify  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / 'native/enhancements/catalogue'
BUNDLED_INDEX = ROOT / 'assets/data/enhancements_index.json.gz'
BASE_URL = 'https://raw.githubusercontent.com/TarbleFR/RewindBox/Claude/native/enhancements/catalogue/'
SHARDS_PER_ENGINE = 32

SOURCES = {
    'switch-cheats-db': {
        'name': 'HamletDuFromage switch-cheats-db',
        'url': 'https://github.com/HamletDuFromage/switch-cheats-db',
        'git': 'https://github.com/HamletDuFromage/switch-cheats-db',
        'revision': '109766ab21c784150287c83ff85c02ab9512dccb',
        'license': 'No licence file. Community codes mirrored from GBAtemp and '
                   'ChanseyIsTheBest/NX-60FPS-RES-GFX-Cheats; every author credit kept.',
        'engines': ['melonx'],
    },
    'rpcs3-patches': {
        'name': 'RPCS3 game patches (wiki.rpcs3.net, official patch API)',
        'url': 'https://wiki.rpcs3.net/index.php?title=Help:Game_Patches',
        'download': 'https://rpcs3.net/compatibility?patch&api=v1&v=1.2',
        'sha256': 'f1f3cab0c8fee21c30ef69789d79468e2c69a4f52583e53e4392a1cf97791486',
        'license': 'Distributed by the RPCS3 project through the same API as its '
                   'own patch manager; per-patch Author fields kept.',
        'engines': ['rpcs3'],
    },
    'pcsx2-patches': {
        'name': 'PCSX2 pcsx2_patches',
        'url': 'https://github.com/PCSX2/pcsx2_patches',
        'git': 'https://github.com/PCSX2/pcsx2_patches',
        'revision': 'ba8ef4f42c353d8ee44d572f8111b10db54a3f0b',
        'license': 'No licence file. The patch set PCSX2 (GPL-3.0) and ARMSX2 '
                   'distribute with their builds; author= fields kept.',
        'engines': ['armsx2'],
    },
    'dolphin-gamesettings': {
        'name': 'Dolphin Sys/GameSettings (dolphin-ios engine revision)',
        'url': 'https://github.com/OatmealDome/dolphin-ios/tree/7cac54161659421ed95c2cd1c0b0746539a4cd38/Data/Sys/GameSettings',
        'git': 'https://github.com/OatmealDome/dolphin-ios.git',
        'revision': '7cac54161659421ed95c2cd1c0b0746539a4cd38',
        'sparse': 'Data/Sys/GameSettings/',
        'license': 'GPL-2.0-or-later (Dolphin). Only patch names are referenced; '
                   'the bodies stay in the engine bundle.',
        'engines': ['dolphin'],
    },
}

SWITCH_BUILD = re.compile(r'^[0-9A-F]{16}$')
SWITCH_TITLE = re.compile(r'^0100[0-9A-F]{12}$')
SWITCH_LINE = re.compile(r'^[0-9A-Fa-f]{8}( [0-9A-Fa-f]{8}){0,3}$')
RPCS3_HASH = re.compile(r'^PPU-[0-9a-fA-F]{40}$')
RPCS3_SERIAL = re.compile(r'^[A-Z]{4}[0-9]{5}$')
RPCS3_VERSION = re.compile(r'^[0-9]{2}\.[0-9]{2}$')
RPCS3_OFFSET = re.compile(r'^0x[0-9A-Fa-f]{1,8}$')
# Exactly the opcodes RPCS3UnifiedCheats accepts before the Core parser runs.
RPCS3_TYPES = {
    'byte', 'le16', 'le32', 'le64', 'lef32', 'lef64', 'be16', 'be32', 'be64', 'bd32', 'bd64',
    'bef32', 'bef64', 'alloc', 'calloc', 'code_alloc', 'jump', 'jump_link', 'jump_func',
    'utf8', 'cutf8', 'bpex'}
PS2_FILE = re.compile(r'^([A-Z]{4}-[0-9]{5})_([0-9A-F]{8})\.pnach$')
DOLPHIN_STEM = re.compile(r'^([A-Z0-9]{1}|[A-Z0-9]{3}|[A-Z0-9]{6})(r[0-9]+)?$')


def stable_id(*parts):
    return hashlib.sha1('\x1f'.join(parts).encode()).hexdigest()[:16]


def shard_of(engine, key):
    return '%s-%02d' % (engine, int(hashlib.sha1(key.encode()).hexdigest()[:4], 16) % SHARDS_PER_ENGINE)


def clean_label(text, limit=160):
    text = re.sub(r'\s+', ' ', str(text or '')).strip()
    return text[:limit]


# ---------------------------------------------------------------- inputs

def fetch_git(cache, source_id, offline):
    source = SOURCES[source_id]
    target = cache / source_id
    if (target / '.git').exists():
        head = subprocess.check_output(['git', '-C', str(target), 'rev-parse', 'HEAD'], text=True).strip()
        if head == source['revision']:
            return target
        if offline:
            raise SystemExit(f'{source_id}: cached revision {head} is not the pinned one')
    if offline:
        raise SystemExit(f'{source_id}: missing from the cache')
    subprocess.run(['rm', '-rf', str(target)], check=True)
    subprocess.run(['git', 'init', '-q', str(target)], check=True)
    subprocess.run(['git', '-C', str(target), 'remote', 'add', 'origin', source['git']], check=True)
    fetch = ['git', '-C', str(target), 'fetch', '-q', '--depth', '1']
    if 'sparse' in source:
        subprocess.run(['git', '-C', str(target), 'config', 'core.sparseCheckout', 'true'], check=True)
        (target / '.git/info/sparse-checkout').write_text(source['sparse'] + '\n')
        fetch.append('--filter=blob:none')
    subprocess.run(fetch + ['origin', source['revision']], check=True)
    subprocess.run(['git', '-C', str(target), 'checkout', '-q', 'FETCH_HEAD'], check=True)
    return target


def fetch_rpcs3(cache, offline):
    source = SOURCES['rpcs3-patches']
    target = cache / 'rpcs3-patch.yml'
    if not target.exists():
        if offline:
            raise SystemExit('rpcs3-patches: missing from the cache')
        with urllib.request.urlopen(source['download'], timeout=120) as response:
            payload = json.loads(response.read())
        target.write_text(payload['patch'], encoding='utf-8')
    text = target.read_text(encoding='utf-8')
    digest = hashlib.sha256(text.encode()).hexdigest()
    if digest != source['sha256']:
        raise SystemExit(f'rpcs3-patches: content {digest} is not the pinned {source["sha256"]}; '
                         'review the new patch.yml and update the pin')
    return text


# ---------------------------------------------------------------- MeloNX

def switch_cheat(name, code):
    """One Atmosphere section, or None when any body line is not an opcode word."""
    lines = []
    for raw in code.split('\n')[1:]:
        line = raw.strip()
        if not line:
            continue
        if not SWITCH_LINE.match(line):
            return None
        lines.append(line.upper())
    if not lines or len(lines) > 512:
        return None
    return lines


def switch_name(raw):
    """A section label Ryujinx parses unchanged: it strips //, # and ; first."""
    name = raw.strip()
    if len(name) >= 2 and name[0] in '[{' and name[-1] in ']}':
        name = name[1:-1]
    name = re.sub(r'//|[#;\[\]{}]', ' ', name)
    return clean_label(name, 120)


def build_melonx(root, stats):
    titles = {}
    for folder, source_id, default in (('cheats', 'switch-cheats-db', 'cheat'),
                                       ('cheats_gfx', 'switch-cheats-db', 'graphics')):
        for path in sorted((root / folder).glob('*.json')):
            tid = path.stem.upper()
            if not SWITCH_TITLE.match(tid):
                stats['melonx_rejected_titles'] += 1
                continue
            data = json.loads(path.read_text(encoding='utf-8'))
            record = titles.setdefault(tid, {'title': '', 'credits': [], 'master': {}, 'entries': {}})
            for file_name, credit in sorted((data.get('attribution') or {}).items()):
                if not record['title']:
                    record['title'] = clean_label(re.sub(r'\.txt$', '', file_name, flags=re.I), 120)
                # Attribution files sometimes repeat the codes: keep prose only.
                prose = [l.strip() for l in str(credit).splitlines()
                         if l.strip() and not l.strip().startswith(('[', '{')) and not SWITCH_LINE.match(l.strip())]
                text = clean_label(' '.join(prose), 300)
                if text and text not in record['credits'] and len(record['credits']) < 12:
                    record['credits'].append(text)
            for build, cheats in data.items():
                if build == 'attribution':
                    continue
                if not SWITCH_BUILD.match(build) or not isinstance(cheats, dict):
                    stats['melonx_rejected_builds'] += 1
                    continue
                for raw_name, code in cheats.items():
                    lines = switch_cheat(raw_name, str(code))
                    if lines is None:
                        stats['melonx_rejected_cheats'] += 1
                        continue
                    name = switch_name(raw_name)
                    if raw_name.strip().startswith('{'):
                        # Atmosphere master code: always on with any cheat of its build.
                        record['master'][build] = lines
                        continue
                    if not name:
                        stats['melonx_rejected_cheats'] += 1
                        continue
                    category = classify(name, default)
                    entry = record['entries'].setdefault(name.casefold(), {
                        'id': stable_id('melonx', tid, name.casefold()),
                        'cat': category, 'name': name, 'source': source_id, 'builds': {}})
                    if category != 'cheat' and entry['cat'] == 'cheat':
                        entry['cat'] = category
                    if build in entry['builds']:
                        stats['melonx_duplicate_cheats'] += 1
                        continue
                    entry['builds'][build] = lines
    out = {}
    for tid, record in titles.items():
        entries = sorted(record['entries'].values(), key=lambda e: (e['cat'], e['name'].casefold()))
        if not entries:
            continue
        out[tid] = {'title': record['title'] or tid, 'credits': record['credits'],
                    'master': record['master'], 'entries': entries}
    return out


# ---------------------------------------------------------------- RPCS3

def flatten_rpcs3(lines, depth=0):
    if depth > 8 or not isinstance(lines, list):
        return None
    flat = []
    for line in lines:
        if not isinstance(line, list) or not line:
            return None
        if line[0] == 'load':
            nested = flatten_rpcs3(line[1] if len(line) == 2 else None, depth + 1)
            if nested is None:
                return None
            flat.extend(nested)
            continue
        if len(line) != 3 or line[0] not in RPCS3_TYPES or not isinstance(line[1], str) or \
                not RPCS3_OFFSET.match(line[1]) or not isinstance(line[2], str):
            return None
        flat.append([line[0], line[1], line[2]])
    return flat


def rpcs3_variants(name, patch):
    """(label, lines, group) variants; configurable values become fixed choices."""
    lines = flatten_rpcs3(patch.get('Patch'))
    if not lines or len(lines) > 8192:
        return []
    group = clean_label(patch.get('Group') or '', 120)
    config = patch.get('Configurable Values')
    if not config:
        return [(name, lines, group, '')]
    if not isinstance(config, dict):
        return []

    def substitute(values):
        return [[t, o, values.get(v, v)] for t, o, v in lines]

    if len(config) == 1:
        key, spec = next(iter(config.items()))
        allowed = spec.get('Allowed Values') if isinstance(spec, dict) else None
        if isinstance(allowed, dict) and 1 < len(allowed) <= 16 and \
                str(spec.get('Type', '')).endswith('_enum'):
            choice_group = group or ('rewindbox/' + stable_id(name))
            return [('%s — %s' % (name, clean_label(label, 40)), substitute({key: str(value)}), choice_group, label)
                    for label, value in allowed.items() if isinstance(value, str)]
    defaults = {}
    for key, spec in config.items():
        if not isinstance(spec, dict) or not isinstance(spec.get('Value'), str):
            return []
        defaults[key] = spec['Value']
    return [(name, substitute(defaults), group, 'default')]


class _RedefiningLoader(yaml.BaseLoader):
    """Scalars stay text (hex stays hex); a redefined anchor replaces the
    earlier one for later aliases, as YAML 1.2 and yaml-cpp (RPCS3) do."""

    def compose_node(self, parent, index):
        if self.check_event(yaml.events.AliasEvent):
            return super().compose_node(parent, index)
        event = self.peek_event()
        anchor = getattr(event, 'anchor', None)
        if anchor is not None:
            self.anchors.pop(anchor, None)
        return super().compose_node(parent, index)


def build_rpcs3(text, stats):
    document = yaml.load(text, Loader=_RedefiningLoader)
    if str(document.get('Version')) != '1.2':
        raise SystemExit('rpcs3-patches: unexpected patch.yml version')
    serials = {}
    for hash_key, patches in document.items():
        if not RPCS3_HASH.match(hash_key) or not isinstance(patches, dict):
            continue
        for name, patch in patches.items():
            if not isinstance(patch, dict) or not isinstance(patch.get('Games'), dict):
                stats['rpcs3_rejected'] += 1
                continue
            variants = rpcs3_variants(clean_label(name, 160), patch)
            if not variants:
                stats['rpcs3_rejected'] += 1
                continue
            for title, by_serial in patch['Games'].items():
                if not isinstance(by_serial, dict):
                    continue
                for serial, versions in by_serial.items():
                    if not RPCS3_SERIAL.match(serial) or not isinstance(versions, list):
                        continue
                    versions = sorted({v for v in versions if isinstance(v, str) and RPCS3_VERSION.match(v)})
                    if not versions:
                        continue
                    record = serials.setdefault(serial, {'title': clean_label(title, 120), 'entries': {}})
                    for label, lines, group, variant in variants:
                        key = label.casefold()
                        entry = record['entries'].setdefault(key, {
                            'id': stable_id('rpcs3', serial, key), 'cat': classify(label), 'name': label,
                            'author': clean_label(patch.get('Author'), 200),
                            'notes': clean_label(patch.get('Notes'), 600),
                            'patch_version': clean_label(patch.get('Patch Version'), 20),
                            'group': group, 'variant': clean_label(variant, 40),
                            'source': 'rpcs3-patches', 'targets': []})
                        entry['targets'].append({'hash': hash_key, 'title': clean_label(title, 200),
                                                 'versions': versions, 'patch': lines})
    out = {}
    for serial, record in serials.items():
        entries = sorted(record['entries'].values(), key=lambda e: (e['cat'], e['name'].casefold()))
        for entry in entries:
            entry['targets'].sort(key=lambda t: (t['hash'], t['versions']))
        out[serial] = {'title': record['title'], 'entries': entries}
    return out


# ---------------------------------------------------------------- ARMSX2

def parse_pnach(text):
    title, groups, current = '', [], None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('//'):
            continue
        if line.startswith('[') and line.endswith(']') and len(line) > 2:
            current = {'name': line[1:-1].strip(), 'description': '', 'author': '', 'patches': 0}
            groups.append(current)
            continue
        key, _, value = line.partition('=')
        key = key.strip().lower()
        if current is None:
            if key == 'gametitle':
                title = value.strip()
            continue
        if key == 'description':
            current['description'] = value.strip()
        elif key == 'author':
            current['author'] = value.strip()
        elif key in ('patch', 'dpatch'):
            current['patches'] += 1
    return title, groups


def build_armsx2(root, stats):
    serials = {}
    for path in sorted((root / 'patches').glob('*.pnach')):
        match = PS2_FILE.match(path.name)
        if not match:
            stats['armsx2_skipped_files'] += 1
            continue
        serial, crc = match.groups()
        data = path.read_bytes()
        if len(data) > 512 * 1024:
            stats['armsx2_skipped_files'] += 1
            continue
        text = data.decode('utf-8', errors='replace')
        title, groups = parse_pnach(text)
        groups = [g for g in groups if g['name'] and g['patches']]
        if not groups:
            continue
        record = serials.setdefault(serial, {'title': '', 'files': {}, 'entries': []})
        # gametitle often carries the serial, CRC and version: keep the name.
        name = re.split(r'\s*[(\[]?\b[A-Z]{4}[-_ ]?[0-9]{3}\.?[0-9]{2}', title)[0]
        record['title'] = record['title'] or clean_label(name.strip(' -/'), 120)
        # The installed bytes are the UTF-8 text RewindBox writes.
        encoded = text.encode('utf-8')
        record['files'][crc] = {'name': path.name, 'sha256': hashlib.sha256(encoded).hexdigest(),
                                'size': len(encoded), 'text': text}
        for group in groups:
            record['entries'].append({
                'id': stable_id('armsx2', serial, crc, group['name'].casefold()),
                'cat': classify(group['name'] + ' ' + group['description']),
                'name': clean_label(group['name'], 160), 'crc': crc,
                'description': clean_label(group['description'], 300),
                'author': clean_label(group['author'], 200), 'source': 'pcsx2-patches'})
    for record in serials.values():
        record['entries'].sort(key=lambda e: (e['cat'], e['name'].casefold(), e['crc']))
        record['title'] = record['title'] or ''
    return serials


# ---------------------------------------------------------------- Dolphin

def ini_sections(text):
    sections, current = {}, None
    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if stripped.startswith('[') and stripped.endswith(']'):
            current = sections.setdefault(stripped[1:-1], [])
        elif current is not None:
            current.append(line)
    return sections


DOLPHIN_KINDS = (('OnFrame', 'onframe'), ('Gecko', 'gecko'), ('ActionReplay', 'ar'))


def dolphin_code_name(kind, label):
    """The name Dolphin matches in *_Enabled lists: Gecko drops its [creator]."""
    if kind == 'gecko':
        return label.split('[', 1)[0].strip()
    return label.strip()


def build_dolphin(root, stats):
    stems = {}
    for path in sorted((root / 'Data/Sys/GameSettings').glob('*.ini')):
        stem = path.stem
        match = DOLPHIN_STEM.match(stem)
        if not match:
            stats['dolphin_skipped_files'] += 1
            continue
        text = path.read_text(encoding='utf-8', errors='replace')
        sections = ini_sections(text)
        heading = text.splitlines()[0] if text else ''
        title = clean_label(re.sub(r'^#\s*[A-Z0-9]+\s*-\s*', '', heading), 120) if heading.startswith('#') else ''
        defaults, listed = {}, []
        for section, kind in DOLPHIN_KINDS:
            enabled = sorted({dolphin_code_name(kind, l.strip()[1:]) for l in sections.get(section + '_Enabled', [])
                              if l.strip().startswith('$')})
            if enabled:
                defaults[kind] = enabled
            codes, current = [], None
            for line in sections.get(section, []):
                stripped = line.strip()
                if stripped.startswith('$'):
                    current = {'label': stripped[1:].strip(), 'lines': 0}
                    codes.append(current)
                elif current is not None and stripped and not stripped.startswith(('#', '*')):
                    current['lines'] += 1
            for code in codes:
                name = dolphin_code_name(kind, code['label'])
                if not name or not code['lines'] or name in enabled:
                    continue
                category = classify(code['label'])
                # Gameplay codes already reach Dolphin through the unified cheat
                # catalogue and its in-game menu; compatibility fixes stay the
                # engine's decision. Only enhancements are listed here.
                if category == 'cheat':
                    stats['dolphin_cheats_left_to_catalogue'] += 1
                    continue
                if re.search(r'\b(fix|fixes|hang|crash|freeze|workaround)\b', code['label'], re.I) and \
                        category == 'graphics' and not re.search(r'aspect|widescreen', code['label'], re.I):
                    stats['dolphin_fixes_skipped'] += 1
                    continue
                listed.append({'id': stable_id('dolphin', stem, kind, name), 'cat': category, 'kind': kind,
                               'name': clean_label(name, 160), 'label': clean_label(code['label'], 200),
                               'lines': code['lines'],
                               'revision': int(match.group(2)[1:]) if match.group(2) else None,
                               'source': 'dolphin-gamesettings'})
        if listed or defaults:
            stems[stem] = {'title': title, 'defaults': defaults,
                           'entries': sorted(listed, key=lambda e: (e['cat'], e['name'].casefold(), e['kind']))}
    return stems


# ---------------------------------------------------------------- output

def write_gzip(path, payload):
    data = json.dumps(payload, ensure_ascii=False, separators=(',', ':'), sort_keys=True).encode()
    packed = gzip.compress(data, compresslevel=9, mtime=0)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(packed)
    return packed, len(data)


def counts(entries):
    result = {}
    for entry in entries:
        result[entry['cat']] = result.get(entry['cat'], 0) + 1
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--revision', default='')
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    stats = {k: 0 for k in ('melonx_rejected_titles', 'melonx_rejected_builds', 'melonx_rejected_cheats',
                            'melonx_duplicate_cheats', 'rpcs3_rejected', 'armsx2_skipped_files',
                            'dolphin_skipped_files', 'dolphin_fixes_skipped', 'dolphin_cheats_left_to_catalogue')}
    engines = {
        'melonx': build_melonx(fetch_git(args.cache, 'switch-cheats-db', args.offline), stats),
        'rpcs3': build_rpcs3(fetch_rpcs3(args.cache, args.offline), stats),
        'armsx2': build_armsx2(fetch_git(args.cache, 'pcsx2-patches', args.offline), stats),
        'dolphin': build_dolphin(fetch_git(args.cache, 'dolphin-gamesettings', args.offline), stats),
    }
    shards_dir = OUTPUT / 'shards'
    for old in shards_dir.glob('*.json.gz') if shards_dir.exists() else []:
        old.unlink()
    index_engines, shard_meta, totals = {}, {}, {}
    for engine, records in engines.items():
        grouped = {}
        keys = {}
        for key in sorted(records):
            shard = shard_of(engine, key)
            grouped.setdefault(shard, {})[key] = records[key]
            keys[key] = [records[key]['title'], counts(records[key]['entries']), shard]
        for shard, members in sorted(grouped.items()):
            packed, expanded = write_gzip(shards_dir / f'{shard}.json.gz',
                                          {'schema': 1, 'engine': engine, 'shard': shard, 'keys': members})
            shard_meta[shard] = {'path': f'shards/{shard}.json.gz', 'size': len(packed), 'expanded': expanded,
                                 'sha256': hashlib.sha256(packed).hexdigest()}
        index_engines[engine] = {'keys': keys}
        engine_totals = {}
        for record in records.values():
            for cat, n in counts(record['entries']).items():
                engine_totals[cat] = engine_totals.get(cat, 0) + n
        totals[engine] = {'keys': len(records), 'entries': engine_totals}
    digest = hashlib.sha256(json.dumps(shard_meta, sort_keys=True).encode()).hexdigest()
    revision = args.revision or datetime.date.today().isoformat() + '.' + digest[:12]
    index = {
        'schema': 1, 'catalogue': 'rewindbox-enhancements', 'revision': revision, 'base_url': BASE_URL,
        'sources': [{'id': k, **{f: v[f] for f in ('name', 'url', 'license', 'engines')},
                     'revision': v.get('revision') or v.get('sha256')} for k, v in SOURCES.items()],
        'engines': index_engines, 'shards': shard_meta, 'totals': totals,
    }
    packed, _ = write_gzip(OUTPUT / 'index.json.gz', index)
    BUNDLED_INDEX.parent.mkdir(parents=True, exist_ok=True)
    BUNDLED_INDEX.write_bytes(packed)
    report = {'revision': revision, 'index_sha256': hashlib.sha256(packed).hexdigest(),
              'index_size': len(packed), 'totals': totals, 'rejections': stats,
              'shard_bytes': sum(m['size'] for m in shard_meta.values())}
    (OUTPUT / 'VALIDATION.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
