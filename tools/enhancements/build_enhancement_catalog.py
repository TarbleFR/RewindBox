#!/usr/bin/env python3
"""Build the RewindBox Cheats & Enhancements catalogue.

The catalogue only references formats each embedded engine already reads:

* MeloNX (Ryujinx): Atmosphere cheat files keyed by Title ID and Build ID,
  and exefs IPSwitch patches (.pchtxt) keyed by their @nsobid header.
* RPCS3: patch.yml 1.2 entries, keyed by PPU hash, serial and APP_VER.
* ARMSX2 (PCSX2): one .pnach per serial and boot ELF CRC, merging the
  labelled groups of several sources.
* Dolphin: OnFrame/Gecko/AR codes of GameSettings INIs: the engine's own by
  name, others with their bodies.

Titles whose authors restrict distribution are excluded (RESTRICTED).

Inputs are pinned (git revisions or a content SHA-256). No game, BIOS,
firmware or key is read or written. Usage:

  python3 tools/enhancements/build_enhancement_catalog.py --cache /tmp/enh-cache

`--offline` requires every input in the cache.
"""
import argparse
import collections
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

TAKEDOWN = 'https://github.com/TarbleFR/RewindBox/issues'
NO_LICENCE = ('No licence file: all rights stay with the authors credited in each entry. RewindBox '
              'republishes the entries for on-demand download only, does not relicense them and '
              'removes any author\'s entries on request (' + TAKEDOWN + ').')

SOURCES = {
    # ------------------------------------------------------------ MeloNX
    'switch-cheats-db': {
        'name': 'HamletDuFromage switch-cheats-db (GBAtemp and ChanseyIsTheBest mirror)',
        'url': 'https://github.com/HamletDuFromage/switch-cheats-db',
        'git': 'https://github.com/HamletDuFromage/switch-cheats-db',
        'revision': '109766ab21c784150287c83ff85c02ab9512dccb',
        'license': NO_LICENCE + ' Titles whose authors restrict distribution to GBAtemp are excluded.',
        'engines': ['melonx'],
    },
    'gbatemp-matias3ds': {
        'name': 'exefer gbatemp-matias3ds-cheats (GBAtemp cheat request thread)',
        'url': 'https://github.com/exefer/gbatemp-matias3ds-cheats',
        'git': 'https://github.com/exefer/gbatemp-matias3ds-cheats',
        'revision': 'ca85a7c9a30983a9084ba49866369a67f3d152a5',
        'license': 'Repository compilation MIT (c) 2026 exefer; "All rights belong to the original cheat '
                   'authors". ' + NO_LICENCE,
        'engines': ['melonx'],
    },
    'titledb-cheats': {
        'name': 'blawar titledb cheats.json',
        'url': 'https://github.com/blawar/titledb/blob/d424690446eec6f4484209b9a1c067c7f7511398/cheats.json',
        'git': 'https://github.com/blawar/titledb',
        'revision': 'd424690446eec6f4484209b9a1c067c7f7511398',
        'sparse': 'cheats.json',
        'license': 'Repository MIT (c) 2019 Blake Warner; community codes without per-code credit. ' + NO_LICENCE,
        'engines': ['melonx'],
    },
    'keatonthebot-pchtxt': {
        'name': 'KeatonTheBot switch-pchtxt-mods (exefs patches)',
        'url': 'https://github.com/KeatonTheBot/switch-pchtxt-mods',
        'git': 'https://github.com/KeatonTheBot/switch-pchtxt-mods',
        'revision': '81e79b55505648ff20fd9c0ed4540d5634c60f0e',
        'license': 'Mods by KeatonTheBot (https://linktr.ee/keatonthebot). ' + NO_LICENCE,
        'engines': ['melonx'],
    },
    'fl4sh-ultrawide': {
        'name': 'Fl4sh9174 Switch Emulator Ultrawide, FPS and Graphics Mods (exefs patches)',
        'url': 'https://github.com/Fl4sh9174/Switch-Ultrawide-Mods',
        'git': 'https://github.com/Fl4sh9174/Switch-Ultrawide-Mods',
        'revision': '76fc6ac3e5776ed41d8b6724c7141f46b74a6617',
        'license': 'Mods by Fl4sh9174 (https://ko-fi.com/fl4sh9174); exefs-only mods, romfs assets excluded. '
                   + NO_LICENCE,
        'engines': ['melonx'],
    },
    # ------------------------------------------------------------ RPCS3
    'rpcs3-patches': {
        'name': 'RPCS3 game patches (RPCS3 Wiki contributors, official patch API)',
        'url': 'https://wiki.rpcs3.net/index.php?title=Help:Game_Patches',
        'download': 'https://rpcs3.net/compatibility?patch&api=v1&v=1.2',
        'sha256': 'f1f3cab0c8fee21c30ef69789d79468e2c69a4f52583e53e4392a1cf97791486',
        'license': 'CC BY-SA 4.0 (RPCS3 Wiki, per its General disclaimer; to be confirmed in a browser). '
                   'Adapted: converted to RewindBox JSON and filtered; the adapted RPCS3 entries are '
                   'distributed under CC BY-SA 4.0. Per-patch Author and Notes kept.',
        'engines': ['rpcs3'],
    },
    # ------------------------------------------------------------ ARMSX2
    'pcsx2-patches': {
        'name': 'PCSX2 pcsx2_patches',
        'url': 'https://github.com/PCSX2/pcsx2_patches',
        'git': 'https://github.com/PCSX2/pcsx2_patches',
        'revision': 'ba8ef4f42c353d8ee44d572f8111b10db54a3f0b',
        'license': 'Patches by the authors named in author= and comments (Arapapa, PeterDelta, ElHecht, '
                   'nemesis2000, Gabominated, El_Patas, asasega, Silent and others). The set PCSX2 and ARMSX2 '
                   'distribute as patches.zip. ' + NO_LICENCE,
        'engines': ['armsx2'],
    },
    'gabominated-pcsx2': {
        'name': 'Gabominated PCSX2 patches (50/60 FPS, widescreen, visual enhance)',
        'url': 'https://github.com/Gabominated/PCSX2',
        'git': 'https://github.com/Gabominated/PCSX2',
        'revision': '24eaa108d39a63aec5d53e19b4962bb239f145ef',
        'license': 'Patches by Gabominated and the authors named in each file. ' + NO_LICENCE,
        'engines': ['armsx2'],
    },
    'peterdelta-pcsx2': {
        'name': 'PeterDelta PCSX2 patches (50/60 FPS, widescreen)',
        'url': 'https://github.com/PeterDelta/PCSX2',
        'git': 'https://github.com/PeterDelta/PCSX2',
        'revision': '1ad26ca29667ea29cd96989f77ed323c233f939a',
        'license': 'Patches by PeterDelta and the authors named in each file. ' + NO_LICENCE,
        'engines': ['armsx2'],
    },
    'cookieplmonster-ccc': {
        'name': 'CookiePLMonster Console-Cheat-Codes (PS2)',
        'url': 'https://github.com/CookiePLMonster/Console-Cheat-Codes',
        'git': 'https://github.com/CookiePLMonster/Console-Cheat-Codes',
        'revision': '26e407a754e0a2b2c73f55ad4f9261b32cfb42cd',
        'license': 'MIT, Copyright (c) 2020-2023 Adrian Zdanowicz (Silent).',
        'engines': ['armsx2'],
    },
    'aerowidescreen-pcsx2': {
        'name': 'AeroWidescreen PCSX2-Cheats',
        'url': 'https://github.com/AeroWidescreen/PCSX2-Cheats',
        'git': 'https://github.com/AeroWidescreen/PCSX2-Cheats',
        'revision': 'ab043ba5adb9e65837fd451d207e6c7c2731c3b1',
        'license': 'MIT, Copyright (c) 2023 Aero_.',
        'engines': ['armsx2'],
    },
    # ------------------------------------------------------------ Dolphin
    'dolphin-gamesettings': {
        'name': 'Dolphin Sys/GameSettings (dolphin-ios engine revision)',
        'url': 'https://github.com/OatmealDome/dolphin-ios/tree/7cac54161659421ed95c2cd1c0b0746539a4cd38/Data/Sys/GameSettings',
        'git': 'https://github.com/OatmealDome/dolphin-ios.git',
        'revision': '7cac54161659421ed95c2cd1c0b0746539a4cd38',
        'sparse': 'Data/Sys/GameSettings/',
        'license': 'GPL-2.0-or-later (Dolphin). Only code names are referenced; '
                   'the bodies ship with the engine.',
        'engines': ['dolphin'],
    },
    'dolphin-upstream': {
        'name': 'Dolphin Sys/GameSettings (dolphin-emu master)',
        'url': 'https://github.com/dolphin-emu/dolphin/tree/3eb30c7620b4475b2e0404228ba0d2b238a132f1/Data/Sys/GameSettings',
        'git': 'https://github.com/dolphin-emu/dolphin.git',
        'revision': '3eb30c7620b4475b2e0404228ba0d2b238a132f1',
        'sparse': 'Data/Sys/GameSettings/',
        'license': 'GPL-2.0-or-later (Dolphin); code credits kept in each name.',
        'engines': ['dolphin'],
    },
    'ishiiruka-gamesettings': {
        'name': 'Ishiiruka (Dolphin fork) Sys/GameSettings',
        'url': 'https://github.com/Tinob/Ishiiruka/tree/cba6d7279b44894297d8c1dde1effdbba3605c32/Data/Sys/GameSettings',
        'git': 'https://github.com/Tinob/Ishiiruka.git',
        'revision': 'cba6d7279b44894297d8c1dde1effdbba3605c32',
        'sparse': 'Data/Sys/GameSettings/',
        'license': 'GPL-2.0-or-later (Dolphin/Ishiiruka).',
        'engines': ['dolphin'],
    },
    'slippi-gamesettings': {
        'name': 'Slippi Ishiiruka Sys/GameSettings',
        'url': 'https://github.com/project-slippi/Ishiiruka/tree/d6779e03dcfd8dab4bb9b6634eb8f9b393c9d195/Data/Sys/GameSettings',
        'git': 'https://github.com/project-slippi/Ishiiruka.git',
        'revision': 'd6779e03dcfd8dab4bb9b6634eb8f9b393c9d195',
        'sparse': 'Data/Sys/GameSettings/',
        'license': 'GPL-2.0-or-later (Dolphin/Ishiiruka).',
        'engines': ['dolphin'],
    },
    'mpn-gamesettings': {
        'name': 'Dolphin-MPN (Mario Party Netplay) Sys/GameSettings',
        'url': 'https://github.com/MarioPartyNetplay/Dolphin-MPN/tree/cb414b1d65213869928ccb2b6fd0d2406d04bfe0/Data/Sys/GameSettings',
        'git': 'https://github.com/MarioPartyNetplay/Dolphin-MPN.git',
        'revision': 'cb414b1d65213869928ccb2b6fd0d2406d04bfe0',
        'sparse': 'Data/Sys/GameSettings/',
        'license': 'GPL-2.0-or-later (Dolphin).',
        'engines': ['dolphin'],
    },
    'admentus-enhancement-codes': {
        'name': 'Admentus64 Enhancement-Codes (GameCube discs)',
        'url': 'https://github.com/Admentus64/Enhancement-Codes',
        'git': 'https://github.com/Admentus64/Enhancement-Codes.git',
        'revision': 'f8e9ad12d90460e316b552fdf73052eb308e9ab9',
        'license': 'GPL-3.0 (Admentus64).',
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


RATIO = re.compile(r'\b(4|5|15|16|18|20|21|32|43) ?[:.] ?(3|4|9|10|18)\b|ultra ?wide|\b\d{3,4} ?x ?\d{3,4}\b', re.I)
RESOLUTION = re.compile(r'\b\d{3,4}p\b|\b[2-8] ?k\b|\b\d{3,4} ?x ?\d{3,4}\b|resolution', re.I)


def display_group(scope, name, category):
    """Aspect-ratio choices of one game patch the same values: one at a time."""
    if category == 'ultrawide' and RATIO.search(name):
        return f'display/{scope}'
    return ''


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

# Authors who restrict where their codes may appear. Any title carrying such
# a notice in any source is excluded from every Switch cheat source.
RESTRICTED = re.compile(
    r"exclusive to gbatemp|outside (of )?gbatemp|do not (steal|distribute|re-?post|re-?upload|share)|"
    r"don'?t (steal|distribute|re-?post|re-?upload|share)|(re)?distribution (is )?(prohibited|forbidden|not allowed)|"
    r"spreading codes .* prohibited", re.I)
NSOBID = re.compile(r'^@nsobid-([0-9A-Fa-f]{32,64})\s*$')
# cp1252 sequences produced when UTF-8 text was decoded as Latin-1.
MOJIBAKE = re.compile('[ÂÃâîï][\u0080-¿ŒœŠšŸŽžƒˆ˜–—‘-„†-•…‰‹›€™]')


def switch_lines(body):
    """Opcode words of one Atmosphere section, or None when any line is not one."""
    lines = []
    for raw in body:
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


def repair_mojibake(name):
    """Undo UTF-8 read as cp1252; None when the name stays garbled."""
    if not MOJIBAKE.search(name):
        return name
    try:
        fixed = name.encode('cp1252').decode('utf-8')
    except (UnicodeEncodeError, UnicodeDecodeError):
        return None
    return None if MOJIBAKE.search(fixed) else fixed


def atmosphere_sections(text):
    """(kind, label, lines) of an Atmosphere file; kind is '[' or '{'."""
    sections, current = [], None
    for raw in text.replace('\r', '').split('\n'):
        line = raw.strip().lstrip('﻿')
        if line.startswith('[') and line.endswith(']') or line.startswith('{') and line.endswith('}'):
            current = (line[0], line[1:-1].strip(), [])
            sections.append(current)
        elif line and current is not None:
            current[2].append(line)
    return sections


class SwitchCatalogue:
    """Merges Atmosphere cheats of several sources per title.

    The first source to name a program on a build keeps it; a later source
    adds only builds that program lacks, and a body already present on a
    build under another name is not added twice."""

    def __init__(self, stats):
        self.titles = {}
        self.bodies = {}
        self.stats = stats

    def record(self, tid):
        return self.titles.setdefault(tid, {'title': '', 'credits': [], 'master': {}, 'entries': {}})

    def credit(self, tid, text, source_id):
        text = re.sub(r'\s+', ' ', text).strip()
        if not text or SWITCH_LINE.match(text):
            return
        if len(text) > 2000:
            self.stats['melonx_long_credits'] += 1
            text = text[:2000]
        credits = self.record(tid)['credits']
        line = text if source_id == 'switch-cheats-db' else f'{text} ({source_id})'
        if line not in credits and len(credits) < 64:
            credits.append(line)

    def add(self, tid, build, raw_name, body, source_id, default):
        lines = switch_lines(body)
        if lines is None:
            self.stats['melonx_rejected_cheats'] += 1
            return
        record = self.record(tid)
        if raw_name.strip().startswith('{'):
            record['master'].setdefault(build, lines)  # always on with any cheat of its build
            return
        name = repair_mojibake(switch_name(raw_name))
        if not name:
            self.stats['melonx_rejected_cheats'] += 1
            return
        seen = self.bodies.setdefault((tid, build), set())
        key = tuple(lines)
        category = classify(name, default)
        entry = record['entries'].get(name.casefold())
        if entry is None:
            if key in seen:
                self.stats['melonx_duplicate_cheats'] += 1
                return
            entry = record['entries'][name.casefold()] = {
                'id': stable_id('melonx', tid, name.casefold()), 'cat': category, 'name': name,
                'source': source_id, 'builds': {}}
        if category != 'cheat' and entry['cat'] == 'cheat':
            entry['cat'] = category
        if build in entry['builds'] or key in seen:
            self.stats['melonx_duplicate_cheats'] += 1
            return
        entry['builds'][build] = lines
        seen.add(key)
        if entry['source'] != source_id:
            entry.setdefault('also', [])
            if source_id not in entry['also']:
                entry['also'].append(source_id)


def switch_restricted_titles(scdb, matias):
    """Title IDs whose authors limit distribution, from every Switch source."""
    restricted = set()
    for folder in ('cheats', 'cheats_gfx', 'cheats_gbatemp'):
        for path in sorted((scdb / folder).glob('*.json')):
            data = json.loads(path.read_text(encoding='utf-8'))
            for file_name, credit in (data.get('attribution') or {}).items():
                if RESTRICTED.search(file_name) or RESTRICTED.search(str(credit)):
                    restricted.add(path.stem.upper())
    for path in sorted((matias / 'titles').glob('*/cheats/*.txt')):
        if RESTRICTED.search(path.read_text(encoding='utf-8', errors='replace')):
            restricted.add(path.parts[-3].upper())
    return restricted


def build_melonx(scdb, matias, titledb, keaton, fl4sh, stats):
    restricted = switch_restricted_titles(scdb, matias)
    stats['melonx_restricted_titles'] = sorted(restricted)
    catalogue = SwitchCatalogue(stats)

    def allowed(tid):
        if not SWITCH_TITLE.match(tid):
            stats['melonx_rejected_titles'] += 1
            return False
        if tid in restricted:
            stats['melonx_restricted_skipped'] += 1
            return False
        return True

    # 1. switch-cheats-db: gameplay codes, then the graphics/FPS mirror.
    for folder, default in (('cheats', 'cheat'), ('cheats_gfx', 'graphics')):
        for path in sorted((scdb / folder).glob('*.json')):
            tid = path.stem.upper()
            if not allowed(tid):
                continue
            data = json.loads(path.read_text(encoding='utf-8'))
            record = catalogue.record(tid)
            for file_name, credit in sorted((data.get('attribution') or {}).items()):
                if not record['title']:
                    record['title'] = clean_label(re.sub(r'\.txt$', '', file_name, flags=re.I), 120)
                # Attribution files sometimes repeat the codes: keep every other line.
                prose = [l.strip() for l in str(credit).splitlines()
                         if l.strip() and not SWITCH_LINE.match(l.strip())
                         and not (l.strip().startswith('[') and l.strip().endswith(']'))]
                catalogue.credit(tid, ' '.join(prose), 'switch-cheats-db')
            for build, cheats in data.items():
                if build == 'attribution':
                    continue
                if not SWITCH_BUILD.match(build) or not isinstance(cheats, dict):
                    stats['melonx_rejected_builds'] += 1
                    continue
                for raw_name, code in cheats.items():
                    catalogue.add(tid, build, raw_name, str(code).split('\n')[1:], 'switch-cheats-db', default)

    # 2. gbatemp-matias3ds: one Atmosphere file per Build ID.
    for path in sorted((matias / 'titles').glob('*/cheats/*.txt')):
        tid, build = path.parts[-3].upper(), path.stem.upper()
        if not allowed(tid):
            continue
        if not SWITCH_BUILD.match(build):
            stats['melonx_rejected_builds'] += 1
            continue
        for kind, label, body in atmosphere_sections(path.read_text(encoding='utf-8', errors='replace')):
            if not body:
                catalogue.credit(tid, label, 'gbatemp-matias3ds')  # e.g. [From MAX-CHEATS.com by ...]
                continue
            catalogue.add(tid, build, f'{kind}{label}{"]" if kind == "[" else "}"}', body,
                          'gbatemp-matias3ds', 'cheat')

    # 3. titledb cheats.json: title -> build -> hash -> {title, source}.
    data = json.loads((titledb / 'cheats.json').read_text(encoding='utf-8'))
    for tid, builds in sorted(data.items()):
        tid = tid.upper()
        if not allowed(tid) or not isinstance(builds, dict):
            continue
        for build, cheats in sorted(builds.items()):
            build = build.upper()[:16]
            if not SWITCH_BUILD.match(build) or not isinstance(cheats, dict):
                stats['melonx_rejected_builds'] += 1
                continue
            for _, cheat in sorted(cheats.items()):
                if not isinstance(cheat, dict):
                    continue
                label = str(cheat.get('title') or '').strip()
                if not label:
                    continue
                if label[0] not in '[{':
                    label = f'[{label}]'
                catalogue.add(tid, build, label, str(cheat.get('source') or '').split('\n'),
                              'titledb-cheats', 'cheat')

    # 4. exefs patches (.pchtxt), one entry per mod folder.
    exefs = build_melonx_exefs(keaton, fl4sh, stats)

    out = {}
    for tid in sorted(set(catalogue.titles) | set(exefs)):
        record = catalogue.titles.get(tid) or {'title': '', 'credits': [], 'master': {}, 'entries': {}}
        mods = exefs.get(tid, {'title': '', 'entries': []})
        entries = sorted(record['entries'].values(), key=lambda e: (e['cat'], e['name'].casefold()))
        for entry in entries:
            group = display_group(tid, entry['name'], entry['cat'])
            if group:
                entry['group'] = group
        entries += mods['entries']
        if not entries:
            continue
        out[tid] = {'title': record['title'] or mods['title'] or tid, 'credits': record['credits'],
                    'master': record['master'], 'entries': entries}
    return out


def normalise_pchtxt(text):
    """The text Ryujinx's IPSwitchPatcher matches: the @nsobid line first, upper-case.

    The engine compares that header to the executable's hex Build ID exactly
    (Convert.ToHexString is upper-case), so a lower-case or late header would
    never load. Returns (build id, text) or None."""
    lines = text.replace('\r', '').lstrip('﻿').split('\n')
    while lines and not lines[0].strip():
        lines.pop(0)
    if not lines:
        return None
    match = NSOBID.match(lines[0].strip())
    if not match:
        return None
    bid = match.group(1).upper()
    if len(bid.rstrip('0')) < 32:
        return None  # truncated ids never match a loaded executable
    body = '\n'.join(lines[1:]).strip('\n')
    if len(body) > 64 * 1024 or not re.search(r'^\s*[0-9A-Fa-f]{6,8}\s+\S', body, re.M):
        return None
    return bid, f'@nsobid-{bid}\n{body}\n'


def build_melonx_exefs(keaton, fl4sh, stats):
    import zipfile

    mods = {}

    def add(tid, title, mod, files, source_id):
        tid = tid.upper()
        if not SWITCH_TITLE.match(tid):
            stats['melonx_exefs_rejected'] += 1
            return
        patches, bids = [], set()
        for name, text in sorted(files):
            normalised = normalise_pchtxt(text)
            if normalised is None:
                stats['melonx_exefs_rejected'] += 1
                continue
            bid, body = normalised
            if bid in bids:
                continue
            bids.add(bid)
            patches.append({'bid': bid, 'text': body})
        if not patches:
            return
        label = clean_label(re.sub(r'[\[\]]', '', mod), 120)
        category = classify(label, 'graphics')
        record = mods.setdefault(tid, {'title': title, 'entries': [], 'keys': set()})
        key = tuple(sorted(p['text'] for p in patches))
        if key in record['keys']:
            stats['melonx_exefs_duplicates'] += 1
            return
        record['keys'].add(key)
        record['entries'].append({
            'id': stable_id('melonx-exefs', tid, source_id, label.casefold()), 'cat': category,
            'name': label, 'source': source_id, 'exefs': patches,
            # Resolution and aspect mods rewrite the same render targets, and
            # frame-rate mods the same timing: one of each at a time.
            'group': (f'display/{tid}' if category == 'ultrawide' or RESOLUTION.search(label)
                      else f'exefs-fps/{tid}' if category == 'fps' else '')})

    # KeatonTheBot: <Game>/<TITLEID>/<Mod>/exefs/<version>.pchtxt
    grouped = {}
    for path in sorted(keaton.glob('*/*/*/exefs/*.pchtxt')):
        game, tid, mod = path.parts[-5], path.parts[-4], path.parts[-3]
        grouped.setdefault((tid, game, mod), []).append((path.name, path.read_text(encoding='utf-8', errors='replace')))
    for (tid, game, mod), files in sorted(grouped.items()):
        add(tid, game, mod, files, 'keatonthebot-pchtxt')

    # Fl4sh9174: <Game> [TITLEID]...zip with [Mod]/exefs/*.pchtxt; mods carrying
    # anything else (romfs assets, scripts) are skipped whole.
    for path in sorted(fl4sh.glob('*.zip')):
        match = re.search(r'\[(0100[0-9A-Fa-f]{12})\]', path.name)
        if not match:
            stats['melonx_exefs_rejected'] += 1
            continue
        game = clean_label(path.name.split('[')[0], 120)
        with zipfile.ZipFile(path) as archive:
            members = {}
            for info in archive.infolist():
                parts = info.filename.split('/')
                if info.is_dir() or len(parts) < 2 or '..' in parts:
                    continue
                members.setdefault(parts[0], []).append((info, parts))
            for mod, items in sorted(members.items()):
                if any(len(parts) != 3 or parts[1].lower() != 'exefs' or not parts[2].lower().endswith('.pchtxt')
                       for _, parts in items):
                    stats['melonx_exefs_mods_with_other_content'] += 1
                    continue
                files = [(parts[2], archive.read(info).decode('utf-8', errors='replace'))
                         for info, parts in items if info.file_size <= 64 * 1024]
                add(match.group(1), game, mod, files, 'fl4sh-ultrawide')

    for record in mods.values():
        record.pop('keys')
        record['entries'].sort(key=lambda e: (e['cat'], e['name'].casefold()))
    return mods


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


def load_patch_yml(text):
    """patch.yml as RPCS3 reads it: yaml-cpp iterates every top-level pair,
    so a PPU hash listed twice contributes the patches of both blocks."""
    loader = _RedefiningLoader(text)
    try:
        root = loader.get_single_node()
        document = {}
        for key_node, value_node in root.value:
            key = loader.construct_object(key_node, deep=True)
            value = loader.construct_object(value_node, deep=True)
            if isinstance(value, dict) and isinstance(document.get(key), dict):
                document[key] = {**document[key], **value}
            else:
                document[key] = value
        return document
    finally:
        loader.dispose()


def build_rpcs3(text, stats):
    document = load_patch_yml(text)
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

PS2_ANY_FILE = re.compile(r'^([A-Z]{4}-[0-9]{5})_([0-9A-Fa-f]{8})(?:_[^/]*)?\.pnach$')
# Extra pnach sources after pcsx2_patches, in priority order: (source id, glob, label).
PS2_EXTRA = (
    ('gabominated-pcsx2', 'PCSX2 Patches/*.pnach', 'Gabominated'),
    ('peterdelta-pcsx2', 'patches/*.pnach', 'PeterDelta'),
    ('cookieplmonster-ccc', 'PS2/**/*.pnach', 'Silent'),
    ('aerowidescreen-pcsx2', '**/*.pnach', 'Aero'),
)


def parse_pnach(text):
    """(gametitle, global comment lines, groups) of a pnach file. A group keeps
    its raw lines; lines before the first group are never treated as one."""
    title, comments, groups, current = '', [], [], None
    for raw in text.replace('\r', '').split('\n'):
        line = raw.strip()
        if line.startswith('[') and line.endswith(']') and len(line) > 2:
            current = {'name': line[1:-1].strip(), 'description': '', 'author': '', 'patches': 0,
                       'lines': [], 'code': []}
            groups.append(current)
            continue
        if current is None:
            if line.startswith('//'):
                comments.append(line)
            elif line.lower().startswith('gametitle'):
                title = line.partition('=')[2].strip()
            continue
        current['lines'].append(raw.rstrip())
        if not line or line.startswith('//'):
            continue
        key, _, value = line.partition('=')
        key = key.strip().lower()
        if key == 'description':
            current['description'] = value.strip()
        elif key == 'author':
            current['author'] = value.strip()
        elif key in ('patch', 'dpatch'):
            current['patches'] += 1
            current['code'].append(re.sub(r'\s+', '', line).lower())
    for group in groups:
        while group['lines'] and not group['lines'][-1].strip():
            group['lines'].pop()
    return title, comments, groups


def build_armsx2(roots, stats):
    """One SERIAL_CRC.pnach per game: pcsx2_patches verbatim, then the labelled
    groups other sources add. An identical group is not repeated; a different
    group under a taken name is renamed with its author."""
    games = {}

    def key_of(name):
        match = PS2_ANY_FILE.match(name)
        return (match.group(1), match.group(2).upper()) if match else None

    for path in sorted((roots['pcsx2-patches'] / 'patches').glob('*.pnach')):
        match = PS2_FILE.match(path.name)
        if not match:
            stats['armsx2_skipped_files'] += 1
            continue
        data = path.read_bytes()
        if len(data) > 512 * 1024:
            stats['armsx2_skipped_files'] += 1
            continue
        text = data.decode('utf-8', errors='replace')
        title, _, groups = parse_pnach(text)
        game = games.setdefault(match.groups(), {'title': title, 'base': text, 'groups': [], 'extra': []})
        for group in groups:
            if group['name'] and group['patches']:
                game['groups'].append((group, 'pcsx2-patches'))

    for source_id, pattern, label in PS2_EXTRA:
        root = roots[source_id]
        for path in sorted(root.glob(pattern)):
            key = key_of(path.name)
            if key is None or path.stat().st_size > 512 * 1024:
                stats['armsx2_skipped_files'] += 1
                continue
            title, comments, groups = parse_pnach(path.read_bytes().decode('utf-8', errors='replace'))
            game = games.setdefault(key, {'title': title, 'base': '', 'groups': [], 'extra': []})
            game['title'] = game['title'] or title
            taken = {g['name'].casefold(): g for g, _ in game['groups']}
            codes = {tuple(g['code']) for g, _ in game['groups']}
            added = []
            for group in groups:
                if not group['name'] or not group['patches']:
                    continue
                if tuple(group['code']) in codes:
                    stats['armsx2_duplicate_groups'] += 1
                    continue
                name = group['name']
                if name.casefold() in taken:
                    name = f'{name} ({label})'
                    if name.casefold() in taken:
                        stats['armsx2_duplicate_groups'] += 1
                        continue
                renamed = dict(group, name=name)
                if name != group['name']:
                    renamed['variant_of'] = group['name']
                taken[name.casefold()] = renamed
                codes.add(tuple(group['code']))
                game['groups'].append((renamed, source_id))
                added.append(renamed)
            if added:
                game['extra'].append((source_id, path.relative_to(root).as_posix(), comments, added))

    serials = {}
    for (serial, crc), game in sorted(games.items()):
        if not game['groups']:
            continue
        text = game['base'] or f'gametitle={game["title"]}\n'
        for source_id, relative, comments, groups in game['extra']:
            source = SOURCES[source_id]
            text = text.rstrip('\n') + (
                f'\n\n// --- RewindBox: from {source["name"]}, {source["url"]} @ {source["revision"][:12]}, '
                f'{relative} ---\n')
            for comment in comments[:20]:
                text += comment + '\n'
            for group in groups:
                text += f'\n[{group["name"]}]\n' + '\n'.join(group['lines']) + '\n'
        encoded = text.encode('utf-8')
        if len(encoded) > 512 * 1024:
            stats['armsx2_skipped_files'] += 1
            continue
        record = serials.setdefault(serial, {'title': '', 'files': {}, 'entries': []})
        # gametitle often carries the serial, CRC and version: keep the name.
        name = re.split(r'\s*[(\[]?\b[A-Z]{4}[-_ ]?[0-9]{3}\.?[0-9]{2}', game['title'])[0]
        record['title'] = record['title'] or clean_label(name.strip(' -/'), 120)
        # The installed bytes are the UTF-8 text RewindBox writes.
        record['files'][crc] = {'name': f'{serial}_{crc}.pnach', 'sha256': hashlib.sha256(encoded).hexdigest(),
                                'size': len(encoded), 'text': text}
        for group, source_id in game['groups']:
            if len(group['name']) > 160:
                stats['armsx2_skipped_groups'] += 1
                continue
            # PCSX2 matches `Enable = <name>` to the group name exactly.
            record['entries'].append({
                'id': stable_id('armsx2', serial, crc, group['name'].casefold()),
                'cat': classify(group['name'] + ' ' + group['description']),
                'name': group['name'], 'crc': crc,
                'description': clean_label(group['description'], 300),
                'author': clean_label(group['author'], 200), 'source': source_id,
                # A renamed variant replaces its namesake; ratio choices exclude each other.
                'group': display_group(crc, group['name'], classify(group['name'] + ' ' + group['description']))
                or (f'variant/{crc}/{group["variant_of"].casefold()}' if group.get('variant_of') else '')})
        variants = {e['group'] for e in record['entries'] if e['group'].startswith('variant/')}
        for entry in record['entries']:
            key = f'variant/{crc}/{entry["name"].casefold()}'
            if not entry['group'] and key in variants:
                entry['group'] = key
    for record in serials.values():
        record['entries'].sort(key=lambda e: (e['cat'], e['name'].casefold(), e['crc']))
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


DOLPHIN_EXTRA = (
    ('dolphin-upstream', 'Data/Sys/GameSettings/*.ini'),
    ('ishiiruka-gamesettings', 'Data/Sys/GameSettings/*.ini'),
    ('slippi-gamesettings', 'Data/Sys/GameSettings/*.ini'),
    ('mpn-gamesettings', 'Data/Sys/GameSettings/*.ini'),
    # GameCube discs only: the VC files target WADs modified by Patcher64+.
    ('admentus-enhancement-codes', "Paper Mario, TTYD (GC)/G8ME01.ini"),
    ('admentus-enhancement-codes', "Zelda, Collector's Edition (GC)/PZLE01.ini"),
    ('admentus-enhancement-codes', "Zelda, Collector's Edition (GC)/PZLP01.ini"),
    ('admentus-enhancement-codes', 'Zelda, Master Quest (GC)/D43E01.ini'),
    ('admentus-enhancement-codes', 'Zelda, Master Quest (GC)/D43P01.ini'),
)
DOLPHIN_BODY = {
    'gecko': re.compile(r'^[0-9A-Fa-f]{8} [0-9A-Fa-f]{8}$'),
    'ar': re.compile(r'^[0-9A-Fa-f]{8} [0-9A-Fa-f]{8}$'),
    'onframe': re.compile(r'^0x[0-9A-Fa-f]{8}:(byte|word|dword):0x[0-9A-Fa-f]{1,8}$'),
}


def dolphin_file(text):
    """Title, per-kind default names and codes of one GameSettings INI."""
    sections = ini_sections(text)
    heading = text.splitlines()[0] if text else ''
    title = clean_label(re.sub(r'^#\s*[A-Z0-9]+\s*-\s*', '', heading), 120) if heading.startswith('#') else ''
    kinds = {}
    for section, kind in DOLPHIN_KINDS:
        defaults = {dolphin_code_name(kind, l.strip()[1:]) for l in sections.get(section + '_Enabled', [])
                    if l.strip().startswith('$')}
        codes, current = [], None
        for line in sections.get(section, []):
            stripped = line.strip()
            if stripped.startswith('$'):
                current = {'label': stripped[1:].strip(), 'body': [], 'notes': []}
                current['name'] = dolphin_code_name(kind, current['label'])
                codes.append(current)
            elif current is not None and stripped.startswith('*'):
                current['notes'].append(stripped[1:].strip())
            elif current is not None and stripped and not stripped.startswith('#'):
                current['body'].append(stripped)
        kinds[kind] = {'defaults': defaults, 'codes': codes}
    return title, kinds


def dolphin_category(label, stats):
    """The enhancement category of a code label, or None for gameplay codes
    (unified cheat catalogue) and compatibility fixes (the engine's call)."""
    category = classify(label)
    if category == 'cheat':
        stats['dolphin_cheats_left_to_catalogue'] += 1
        return None
    if re.search(r'\b(fix|fixes|hang|crash|freeze|workaround)\b', label, re.I) and \
            category == 'graphics' and not re.search(r'aspect|widescreen', label, re.I):
        stats['dolphin_fixes_skipped'] += 1
        return None
    return category


def build_dolphin(roots, stats):
    stems, engine_names, bodies = {}, {}, {}

    def stem_record(stem, title):
        record = stems.setdefault(stem, {'title': title, 'defaults': {}, 'entries': []})
        record['title'] = record['title'] or title
        return record

    # 1. The engine's own Sys/GameSettings: bodies ship with it, names suffice.
    for path in sorted((roots['dolphin-gamesettings'] / 'Data/Sys/GameSettings').glob('*.ini')):
        match = DOLPHIN_STEM.match(path.stem)
        if not match:
            stats['dolphin_skipped_files'] += 1
            continue
        title, kinds = dolphin_file(path.read_text(encoding='utf-8', errors='replace'))
        listed, defaults = [], {}
        for kind, data in kinds.items():
            names = engine_names.setdefault(path.stem, {}).setdefault(kind, set())
            if data['defaults']:
                defaults[kind] = sorted(data['defaults'])
            for code in data['codes']:
                names.add(code['name'])
                bodies.setdefault(path.stem, set()).add(tuple(code['body']))
                if not code['name'] or not code['body'] or code['name'] in data['defaults']:
                    continue
                category = dolphin_category(code['label'], stats)
                if category is None:
                    continue
                listed.append({'id': stable_id('dolphin', path.stem, kind, code['name']), 'cat': category,
                               'kind': kind, 'name': code['name'], 'label': clean_label(code['label'], 200),
                               'group': display_group(path.stem[:6], code['name'], category),
                               'lines': len(code['body']),
                               'revision': int(match.group(2)[1:]) if match.group(2) else None,
                               'source': 'dolphin-gamesettings'})
        if listed or defaults:
            record = stem_record(path.stem, title)
            record['defaults'] = defaults
            record['entries'].extend(listed)

    # 2. Other sources: full code bodies RewindBox writes into the user INI.
    for source_id, pattern in DOLPHIN_EXTRA:
        for path in sorted(roots[source_id].glob(pattern)):
            stem = path.stem
            match = DOLPHIN_STEM.match(stem)
            if not match or stem.endswith('XX'):  # e.g. Slippi's GALEXX is no retail disc
                stats['dolphin_skipped_files'] += 1
                continue
            title, kinds = dolphin_file(path.read_text(encoding='utf-8', errors='replace'))
            for kind, data in kinds.items():
                known = engine_names.get(stem, {}).get(kind, set())
                for code in data['codes']:
                    name, body = code['name'], code['body']
                    if not name or name in data['defaults'] or name in known or name.startswith('=') or \
                            re.search(r'\btest\b|\bpart ?\d', name, re.I):
                        continue
                    if not body or len(body) > 512 or not all(DOLPHIN_BODY[kind].match(l) for l in body):
                        stats['dolphin_rejected_bodies'] += 1
                        continue
                    category = dolphin_category(code['label'], stats)
                    if category is None:
                        continue
                    seen = bodies.setdefault(stem, set())
                    record = stem_record(stem, title)
                    if tuple(body) in seen or any(e['kind'] == kind and e['name'] == name for e in record['entries']):
                        stats['dolphin_duplicate_codes'] += 1
                        continue
                    seen.add(tuple(body))
                    record['entries'].append({
                        'id': stable_id('dolphin', stem, kind, name), 'cat': category, 'kind': kind,
                        'name': name, 'label': clean_label(code['label'], 200), 'lines': len(body),
                        'body': [l.upper() if kind != 'onframe' else l for l in body],
                        'notes': clean_label(' '.join(code['notes']), 600),
                        'group': display_group(stem[:6], name, category),
                        'revision': int(match.group(2)[1:]) if match.group(2) else None,
                        'source': source_id})
    for record in stems.values():
        record['entries'].sort(key=lambda e: (e['cat'], e['name'].casefold(), e['kind']))
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
    stats = collections.defaultdict(int)
    git = {source_id: fetch_git(args.cache, source_id, args.offline)
           for source_id, source in SOURCES.items() if 'git' in source}
    engines = {
        'melonx': build_melonx(git['switch-cheats-db'], git['gbatemp-matias3ds'], git['titledb-cheats'],
                               git['keatonthebot-pchtxt'], git['fl4sh-ultrawide'], stats),
        'rpcs3': build_rpcs3(fetch_rpcs3(args.cache, args.offline), stats),
        'armsx2': build_armsx2(git, stats),
        'dolphin': build_dolphin(git, stats),
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
