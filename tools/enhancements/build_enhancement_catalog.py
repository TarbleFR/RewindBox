#!/usr/bin/env python3
"""Build the RewindBox Cheats & Enhancements catalogue.

The catalogue only references formats each embedded engine already reads,
and only content whose licence allows redistribution or that the engine
already ships:

* RPCS3: patch.yml 1.2 entries (CC BY-SA 4.0), keyed by PPU hash, serial
  and APP_VER.
* ARMSX2 (PCSX2): the engine's own patches.zip by name, plus MIT-licensed
  cheat groups in one cheats/ pnach per serial and boot ELF CRC.
* Dolphin: OnFrame/Gecko/AR codes of GPL GameSettings INIs: the engine's own
  by name, others with their bodies.
* MeloNX: none. The Switch cheat and patch collections carry no licence.

Inputs are pinned (git revisions or a content SHA-256). No game, BIOS,
firmware or key is read or written. Usage:

  python3 tools/enhancements/build_enhancement_catalog.py --cache /tmp/enh-cache

`--offline` requires every input in the cache. `--reuse-engines rpcs3`
keeps the published records of the named engines, read back from the
catalogue and checked against its SHA-256: an engine whose pins did not move
needs no download and is not rebuilt.

Publication never rewrites a file an app may still ask for. Each revision
has its own folder, `r/<revision>/`, named by the index's `base_url`: its
shards stay as they are, so an app holding that index keeps downloading the
bytes it lists. An app asks the folder of the index it holds for a newer
one, so the newest index is written to `r/*/index.json.gz` of every earlier
revision of the same record format (`format` in the index), and bundled in
the app (assets/data). A shard that did not change keeps its SHA-256: an
app that adopts the new index downloads only the shards that changed. A run
that changes no shard publishes nothing.

The first publication (`index.json.gz` and `shards/` at the root, record
format 1) is frozen: the apps that bundle it do not read PS2 records by
reference, and keep exactly what they have.

A publication never drops an entry ID of the previous one unless
ID_REMOVAL_ALLOWLIST names it with its reason; VALIDATION.json reports the
IDs and keys each engine removed, added or moved (`drift`).
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
import zipfile
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from classify import classify  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / 'native/enhancements/catalogue'
BUNDLED_INDEX = ROOT / 'assets/data/enhancements_index.json.gz'
BASE_URL = 'https://raw.githubusercontent.com/TarbleFR/RewindBox/Claude/native/enhancements/catalogue/'
SHARDS_PER_ENGINE = 32
# Record format of the published index. An app reads the formats it was built for; a new format
# is published to new folders only, and the folders of earlier formats keep their last index.
#   1  first publication (root index.json.gz and shards/, frozen)
#   2  PS2 records may point into their sources' files (`origin`, files with `parts`)
#   3  Switch exefs patches may point to a source's .pchtxt file (`exefs: [{bid, o, size, sha256}]`)
#   4  Switch pointers may select a named, bounded member of a pinned ZIP.
# Optional fields an older app ignores keep the format: entry `flags` (every engine), Switch `author`, `notes`
# and the record's `latest` update (23 November 2026). Switch `alt/` groups are ordinary `group` values: every
# format-4 app applies them as exclusive groups.
FORMAT = 4
ENGINES = ('melonx', 'rpcs3', 'armsx2', 'dolphin', 'azahar')

# Only sources whose licence allows redistribution, or content the embedded
# engine already ships (referenced by name, never redistributed). Sources
# without a licence were reviewed and removed (docs/ENHANCEMENTS.md, Rights).
SOURCES = {
    # ------------------------------------------------------------ MeloNX
    # No licence: the catalogue holds names and pointers only, and the app
    # downloads each title's file from the original repository (origin).
    'switch-cheats-db': {
        'name': 'HamletDuFromage/switch-cheats-db (GBAtemp main cheat file, ChanseyIsTheBest 60 FPS/graphics)',
        'url': 'https://github.com/HamletDuFromage/switch-cheats-db',
        'git': 'https://github.com/HamletDuFromage/switch-cheats-db.git',
        'revision': '4e19981a5c57aee3545ced66e158aa9e7fefa045',
        'origin': 'https://raw.githubusercontent.com/HamletDuFromage/switch-cheats-db/'
                  '4e19981a5c57aee3545ced66e158aa9e7fefa045/',
        'license': 'No licence; the codes belong to the authors credited in each title. Not hosted by '
                   'RewindBox: the app downloads the original file of each title from this repository and '
                   'revision. Titles whose authors restrict distribution are left out.',
        'engines': ['melonx'],
    },
    # No licence either: exefs patches (IPSwitch .pchtxt), read by reference like the cheats above.
    'fl4sh-zip': {
        'name': 'Fl4sh9174/Switch-Emulator-Ultrawide-FPS-Mods',
        'url': 'https://github.com/Fl4sh9174/Switch-Emulator-Ultrawide-FPS-Mods',
        'git': 'https://github.com/Fl4sh9174/Switch-Emulator-Ultrawide-FPS-Mods.git',
        'revision': '5eed21701e8091389e2e746f073f694ea2ad4ec6',
        'origin': 'https://raw.githubusercontent.com/Fl4sh9174/Switch-Emulator-Ultrawide-FPS-Mods/'
                  '5eed21701e8091389e2e746f073f694ea2ad4ec6/',
        'license': "Original authors retain their rights. The app reads selected patches from the publisher's ZIP.",
        'engines': ['melonx'],
        'author': 'Fl4sh9174',
    },
    'keatonthebot-pchtxt': {
        'name': 'KeatonTheBot/switch-pchtxt-mods (exefs patches: resolution, frame rate, effects)',
        'url': 'https://github.com/KeatonTheBot/switch-pchtxt-mods',
        'git': 'https://github.com/KeatonTheBot/switch-pchtxt-mods.git',
        'revision': '13f0e6559136ead857e7c66d53f1ef1775d339f4',
        'origin': 'https://raw.githubusercontent.com/KeatonTheBot/switch-pchtxt-mods/'
                  '13f0e6559136ead857e7c66d53f1ef1775d339f4/',
        'license': 'No licence; the patches belong to KeatonTheBot. Not hosted by RewindBox: the app downloads each '
                   'patch file from this repository and revision.',
        'engines': ['melonx'],
        'author': 'KeatonTheBot',
    },
    # Same kind of patches, laid out <game>/[<Title ID>]/<mod>/<version>.pchtxt (no exefs folder).
    'stevensnd-port-mods': {
        'name': 'StevensND/switch-port-mods (exefs patches: frame rate, resolution, aspect ratio)',
        'url': 'https://github.com/StevensND/switch-port-mods',
        'git': 'https://github.com/StevensND/switch-port-mods.git',
        'revision': '774e7f7c85561ddd865c1cab555f2a335054d522',
        'origin': 'https://raw.githubusercontent.com/StevensND/switch-port-mods/'
                  '774e7f7c85561ddd865c1cab555f2a335054d522/',
        'license': 'No licence; the patches belong to StevensND and to the authors each readme credits. Not hosted by '
                   'RewindBox: the app downloads each patch file from this repository and revision.',
        'engines': ['melonx'],
        'author': 'StevensND',
        'layout': 'bracket',
    },
    'stevensnd-ue4-mods': {
        'name': 'StevensND/ue4-emuswitch-60fps (exefs patches of Unreal Engine games: frame rate, resolution, effects)',
        'url': 'https://github.com/StevensND/ue4-emuswitch-60fps',
        'git': 'https://github.com/StevensND/ue4-emuswitch-60fps.git',
        'revision': '53c69bf93c2f79a6a0e6e7a46f26ea0f0010f06c',
        'origin': 'https://raw.githubusercontent.com/StevensND/ue4-emuswitch-60fps/'
                  '53c69bf93c2f79a6a0e6e7a46f26ea0f0010f06c/',
        'license': 'No licence; the patches belong to StevensND and to the authors each readme credits. The author '
                   'does not allow his mods to be re-uploaded to other sites: RewindBox hosts none of them, the app '
                   'downloads each patch file from this repository and revision.',
        'engines': ['melonx'],
        'author': 'StevensND',
        'layout': 'bracket',
    },
    # ------------------------------------------------------------ RPCS3
    'rpcs3-patches': {
        'name': 'RPCS3 game patches (RPCS3 Wiki contributors, official patch API)',
        'url': 'https://wiki.rpcs3.net/index.php?title=Help:Game_Patches',
        'download': 'https://rpcs3.net/compatibility?patch&api=v1&v=1.2',
        'sha256': 'f1f3cab0c8fee21c30ef69789d79468e2c69a4f52583e53e4392a1cf97791486',
        'license': 'CC BY-SA 4.0 (RPCS3 Wiki; General disclaimer and patch-help footer browser-verified 2026-10-28; except where otherwise noted). '
                   'Adapted: converted to RewindBox JSON and filtered; the adapted RPCS3 entries are '
                   'distributed under CC BY-SA 4.0. Per-patch Author and Notes kept.',
        'engines': ['rpcs3'],
    },
    # MIT (copyright chidreams): Aldo's PS3 cheat database converted to RPCS3 patches, one file per game
    # and version. Hosted with its notice; merged into the RPCS3 records even when those are reused.
    'artemis-rpcs3': {
        'name': 'ChiDreams/Artemis-Patch-Collection-RPCS3 (Aldo\'s PS3 cheat database as RPCS3 patches)',
        'url': 'https://github.com/chidreams/Artemis-Patch-Collection-RPCS3',
        'git': 'https://github.com/chidreams/Artemis-Patch-Collection-RPCS3.git',
        'revision': 'fd267a65759a2f1dcae31e362d318de7a6e16594',
        'license': 'MIT (Copyright (c) 2023 chidreams); cheats from Aldo\'s PS3 cheat database, ported by ChiDreams, '
                   'with each patch\'s Author kept. Converted to RewindBox JSON.',
        'engines': ['rpcs3'],
        'merge': True,
    },
    'artemis-rpcs3-pkg': {
        'name': 'PaauloSilva/Artemis-Patch-Collection-RPCS3_PKG (the same collection for PSN releases)',
        'url': 'https://github.com/PaauloSilva/Artemis-Patch-Collection-RPCS3_PKG',
        'git': 'https://github.com/PaauloSilva/Artemis-Patch-Collection-RPCS3_PKG.git',
        'revision': '471bde6f857fe1ed9a717f7468e9dc91bc53a500',
        'license': 'MIT (Copyright (c) 2023 chidreams, as its LICENSE states); cheats from Aldo\'s PS3 cheat database, '
                   'with each patch\'s Author kept. Converted to RewindBox JSON.',
        'engines': ['rpcs3'],
        'merge': True,
    },
    # ------------------------------------------------------------ ARMSX2
    'armsx2-patches-zip': {
        'name': 'ARMSX2 engine patches.zip (the PCSX2 patch set inside the embedded engine)',
        'url': 'https://github.com/ARMSX2/ARMSX2/blob/9d989ca933a85bb2f1d111fd3b9e5742ac7d2fbe/'
               'platforms/ios/app/src/main/assets/resources/patches.zip',
        'git': 'https://github.com/ARMSX2/ARMSX2.git',
        'revision': '9d989ca933a85bb2f1d111fd3b9e5742ac7d2fbe',
        'sparse': 'platforms/ios/app/src/main/assets/resources/patches.zip',
        'license': 'Shipped inside the embedded ARMSX2 engine (build-utils/armsx2/source.json). RewindBox '
                   'lists patch names and author credits only and enables them in the per-game settings; '
                   'no patch body is redistributed.',
        'engines': ['armsx2'],
    },
    'cookieplmonster-ccc': {
        'name': 'CookiePLMonster Console-Cheat-Codes (PS2)',
        'url': 'https://github.com/CookiePLMonster/Console-Cheat-Codes',
        'git': 'https://github.com/CookiePLMonster/Console-Cheat-Codes',
        'revision': 'f63492f8ce9bbbf8eba57b2616fed3bc17c0740f',
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
    # No licence: by reference only. The catalogue holds each group's name, author and the byte
    # range of its lines in the source's file; the app downloads that file from the source at the
    # pinned revision, checks it, and writes the selected groups (origin, see docs/ENHANCEMENTS.md).
    'pcsx2-patches': {
        'name': 'PCSX2/pcsx2_patches (official PCSX2 patch repository, newer than the engine\'s patches.zip)',
        'url': 'https://github.com/PCSX2/pcsx2_patches',
        'git': 'https://github.com/PCSX2/pcsx2_patches.git',
        'revision': 'b919d7fb5849feeb30b2da07d02f6dc662f28ba5',
        'origin': 'https://raw.githubusercontent.com/PCSX2/pcsx2_patches/b919d7fb5849feeb30b2da07d02f6dc662f28ba5/',
        'license': 'No licence; each patch belongs to the author its file names. Not hosted by RewindBox: the '
                   'app downloads the game\'s original file from this repository and revision. Only the groups '
                   'the embedded engine does not already ship are listed.',
        'engines': ['armsx2'],
    },
    'peterdelta-pcsx2': {
        'name': 'PeterDelta/PCSX2 (50/60 FPS, widescreen and quality-of-life patches)',
        'url': 'https://github.com/PeterDelta/PCSX2',
        'git': 'https://github.com/PeterDelta/PCSX2.git',
        'revision': '8ee633941cfdfb233a772e2d28b1a6006624d392',
        'origin': 'https://raw.githubusercontent.com/PeterDelta/PCSX2/8ee633941cfdfb233a772e2d28b1a6006624d392/',
        'license': 'No licence; the patches belong to PeterDelta and the authors each group names. Not hosted '
                   'by RewindBox: the app downloads the game\'s original file from this repository and revision.',
        'engines': ['armsx2'],
    },
    'gabominated-pcsx2': {
        'name': 'Gabominated/PCSX2 (FPS, widescreen and visual patches)',
        'url': 'https://github.com/Gabominated/PCSX2',
        'git': 'https://github.com/Gabominated/PCSX2.git',
        'revision': '24eaa108d39a63aec5d53e19b4962bb239f145ef',
        'origin': 'https://raw.githubusercontent.com/Gabominated/PCSX2/24eaa108d39a63aec5d53e19b4962bb239f145ef/',
        'license': 'No licence; the patches belong to Gabominated and the authors each group names. Not hosted '
                   'by RewindBox: the app downloads the game\'s original file from this repository and revision.',
        'engines': ['armsx2'],
    },
    'nethersx2-cheats': {
        'name': 'Saramagrean/NetherSX2-cheats (FPS, alternative widescreen ratios, no-interlacing; based on pcsx2_patches)',
        'url': 'https://github.com/Saramagrean/NetherSX2-cheats',
        'git': 'https://github.com/Saramagrean/NetherSX2-cheats.git',
        'revision': '52187122e0adf73a50869b52ce9143e878ab4129',
        'origin': 'https://raw.githubusercontent.com/Saramagrean/NetherSX2-cheats/52187122e0adf73a50869b52ce9143e878ab4129/',
        'license': 'No licence; based on pcsx2_patches, each patch belongs to the author its file names. Not hosted '
                   'by RewindBox: the app downloads the game\'s original file from this repository and revision. '
                   'Only the groups no earlier source has are listed.',
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
        'url': 'https://github.com/dolphin-emu/dolphin/tree/c5069249b473da2427c89a698f1338aeb4011034/Data/Sys/GameSettings',
        'git': 'https://github.com/dolphin-emu/dolphin.git',
        'revision': 'c5069249b473da2427c89a698f1338aeb4011034',
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
        'url': 'https://github.com/project-slippi/Ishiiruka/tree/07b2d287a1f074942811d13b3c990fa29401ba7c/Data/Sys/GameSettings',
        'git': 'https://github.com/project-slippi/Ishiiruka.git',
        'revision': '07b2d287a1f074942811d13b3c990fa29401ba7c',
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
    # ------------------------------------------------------------ Azahar (3DS)
    # GPL-3.0 (LICENSE at the repository root): the Gateway codes are hosted with that notice and the
    # source's credit, like the Dolphin codes. Azahar reads <user>/cheats/<Title ID>.txt when a game loads.
    'sharkive-3ds': {
        'name': 'FlagBrew/Sharkive (3DS Gateway codes)',
        'url': 'https://github.com/FlagBrew/Sharkive',
        'git': 'https://github.com/FlagBrew/Sharkive.git',
        'revision': 'aeab5fd3b001ed22c013efd1a02b092575d825ed',
        'sparse': '/3ds/\n/LICENSE',
        'license': 'GPL-3.0 (LICENSE of FlagBrew/Sharkive); codes submitted by the community, credited to the '
                   'Sharkive contributors.',
        'engines': ['azahar'],
    },
}

SWITCH_BUILD = re.compile(r'^[0-9A-F]{16}$')
SWITCH_TITLE = re.compile(r'^0100[0-9A-F]{12}$')
SWITCH_LINE = re.compile(r'^[0-9A-Fa-f]{8}( [0-9A-Fa-f]{8}){0,3}$')
# Read only to find titles whose authors restrict distribution; nothing of it
# is published.
RESTRICTION_INPUTS = {
    'gbatemp-matias3ds': {
        'git': 'https://github.com/exefer/gbatemp-matias3ds-cheats.git',
        'revision': 'ca85a7c9a30983a9084ba49866369a67f3d152a5',
    },
}
RPCS3_HASH = re.compile(r'^PPU-[0-9a-fA-F]{40}$')
RPCS3_SERIAL = re.compile(r'^[A-Z]{4}[0-9]{5}$')
RPCS3_VERSION = re.compile(r'^[0-9]{2}\.[0-9]{2}$')
RPCS3_OFFSET = re.compile(r'^0x[0-9A-Fa-f]{1,8}$')
# Exactly the opcodes RPCS3UnifiedCheats accepts before the Core parser runs.
RPCS3_TYPES = {
    'byte', 'le16', 'le32', 'le64', 'lef32', 'lef64', 'be16', 'be32', 'be64', 'bd32', 'bd64',
    'bef32', 'bef64', 'alloc', 'calloc', 'code_alloc', 'jump', 'jump_link', 'jump_func',
    'utf8', 'cutf8', 'bpex'}
PS2_FILE = re.compile(r'^(?:([A-Z]{4}-[0-9]{5})_)?([0-9A-F]{8})\.pnach$')
PS2_SERIAL = re.compile(r'\b([A-Z]{4})[-_ ]?([0-9]{3})\.?([0-9]{2})\b')
DOLPHIN_STEM = re.compile(r'^([A-Z0-9]{1}|[A-Z0-9]{3}|[A-Z0-9]{6})(r[0-9]+)?$')


def stable_id(*parts):
    return hashlib.sha1('\x1f'.join(parts).encode()).hexdigest()[:16]


def shard_of(engine, key):
    return '%s-%02d' % (engine, int(hashlib.sha1(key.encode()).hexdigest()[:4], 16) % SHARDS_PER_ENGINE)


def clean_label(text, limit=160):
    text = re.sub(r'\s+', ' ', str(text or '')).strip()
    return text[:limit]


RATIO = re.compile(r'\b(4|5|15|16|18|20|21|32|43) ?[:.] ?(3|4|9|10|18)\b|ultra ?wide|\b\d{3,4} ?x ?\d{3,4}\b', re.I)


def display_group(scope, name, category):
    """Aspect-ratio choices of one game patch the same values: one at a time."""
    if category == 'ultrawide' and RATIO.search(name):
        return f'display/{scope}'
    return ''


# ---------------------------------------------------------------- flags

# One vocabulary for every engine (`flags`, sorted, only when not empty), read from the author's own words:
# a flag repeats what a name, label, note or description says, never a measured effect.
#   default       restores the game's own value (`Default 30 FPS`, `AA High (Default TAA)`, `Restore Code`), in
#                 every console mode: never one mode's default (`(Docked's Default)`), which changes the other mode
#   noRefresh     a frame-rate entry that does not raise the frame cap (`Dynamic Resolution Target 45 FPS`)
#   experimental  experimental, WIP, beta or test code
#   crashRisk     the author says it can crash or freeze the game (`Crash If TAAU ON`)
#   heavy         renders 2160 lines or more (4K, 8K, 2160p, 3840x2160, 6880x2880)
#   dram8gb       needs the expanded (8 GB) DRAM memory layout
FLAGS = ('crashRisk', 'default', 'dram8gb', 'experimental', 'heavy', 'noRefresh')
FLAG_DEFAULT = re.compile(
    # `Default X`, `01. Default X`, `(v1.2.0) Default X`, an RPCS3 choice `— Default FOV(70)`; not a menu
    r"(?:^(?:\(v[\d.]+\)\s*|[\d#№]+\s*[-.):]?\s*)?(?:new\s+)?|—\s*)defaults?\b"
    r"(?!\s+(?:settings?|options?|menus?|screens?)\b)"
    r"|\(\s*default\s*(?:[),]|$)|,\s*default\s*\)|\(\s*default\s+[a-z]\s*\)"  # (Default) (Default, alt) (alt, default)
    r"|\bhandheld(?:'s)? (?:&|and|/) docked(?:'s)? default\b|\bdefault range\b"  # (Handheld's & Docked's Default)
    r"|[\s-]default\s*(?:@\S+\s*)?$|\bdefault \(\d[^)]*\)\s*$|\breturns? (?:to )?default\b"
    # `Restore Code`, `(Restore Code)`, `1(Restore Code)`, `MASTER OFF/RESTORE CODE`; not a note on another code
    # (`60 FPS (Disable + Restore Code for 30FPS)`)
    r"|^\W*(?:[\d#№]+\W*|\S+\s+)?(?:\w+/)?restore code\b", re.I)
# `(Default TAA)` names the standard TAA method of a UE4 anti-aliasing choice (against `(Faster TAA)`), not the
# game's setting. `2x default` is a multiplier, `Default HUD` a variant of an ultrawide mod, `(Default Resolution)` what a mod keeps.
# A name that gives one console mode's default (`Default Handheld RRS 75% (540p)`, `(Docked's Default)`,
# `Handheld/Default Docked`, `(720p Docked's Default)` beside handheld words) changes the game in the other mode;
# MeloNX runs handheld unless the player docks it. Both modes (`Default Handheld/Docked RRS 100% (720p)`,
# `(Handheld's & Docked's Default)`, `Default RSS 100% (720p HH, 1080p D)`) are the game's default.
MODE_HANDHELD = re.compile(r"\bhand-?held\b|\bportable\b|\bundocked\b|(?-i:\bHH\b|\bH\.)", re.I)
MODE_DOCKED = re.compile(r"\bdock(?:ed)?\b|\bTV\b|(?-i:\bD\.|(?<=\dp )D\b)", re.I)
ONE_MODE_DEFAULT = re.compile(r"\w\W*\bdefault (?:for )?(?:hand-?held|dock(?:ed)?)\b"
                              r"|(?<![&/] )(?<!and )\b(?:hand-?held|dock(?:ed)?)'s default\b", re.I)
FLAG_NO_REFRESH = re.compile(r'\b(?:dynamic resolution|DR[ST])(?: target)? \d{2,3} ?fps\b|\bresolution target\b'
                             r'|\bDR[ST] target\b|\bfps (?:counter|display|meter)\b|\b(?:show|display)\w* fps\b'
                             r'|\bspeed fix for\b', re.I)
# `Split screen untested` and `Always Gold License Test` say nothing of the code itself.
FLAG_EXPERIMENTAL = re.compile(
    r'\bexperimental\b|\bwip\b|\bwork in progress\b|\(\s*beta\s*\)|\bbeta\s*$|\bbeta (?:version|build)\b'
    r'|\(\s*test\b[^)]*\)|\(\s*untested\s*\)|(?:^|[.!?]\s+)untested\b|\bnot (?:yet )?tested\b(?! with)'
    r'|\bneeds? (?:further |more )?testing\b', re.I)
# Read per sentence. `Crash Mode` (Burnout), `Infinite Crash Guard`, `Version 3.0 Fixes Crash in ...` and
# `No Crashes` are no risk; `Turn on 1st or the game will crash` is about the codes that need this one.
FLAG_CRASH = re.compile(
    r'\bcrash(?:es)? if\b|\bcrash(?:es)? (?:in|on|when|while|during|after)\b|\(softlock\)'
    r'|\b(?:may|might|can|could|will|would)\s+(?:also\s+|possibly\s+)?(?:cause\s+(?:a\s+|the\s+)?(?:game\s+)?)?'
    r'(?:crash|softlock)|\b(?:may|might|will|would) freeze\b(?! (?:enem|foe|time|the time))', re.I)
FLAG_CRASH_NOT = re.compile(r'\b(?:fix(?:es|ed)?|prevents?|avoids?)\b[^.;]*\b(?:crash|freez|hang|softlock)'
                            r'|\b(?:crash|freeze|hang|softlock)\s*fix|\bturn(?:ed)? on (?:1st|first)\b'
                            r'|\b(?:needs? to|must|has to) be (?:turned )?(?:on|enabled|activated)\b[^.]*\bbefore\b', re.I)
FLAG_DRAM = re.compile(r'\b[68] ?gb (?:of )?(?:dram|ram|memory)\b|\bdram\b[^.]*\blayout\b'
                       r'|\b(?:extended|expanded|alternative) memory layout\b|\bmemory layout\b[^.]*\b[68] ?gb\b', re.I)
# A render size: `4K`, `2160p`, `3840x2160`. A shadow map size (`4K Shadow Resolution`) is not one.
FLAG_HEAVY = re.compile(r'(?<![\w.])(\d{1,2}) ?k(?!\w)(?! ?shadow)|(?<![\w.])(\d{4}) ?p\b'
                        r'|(?<![\w.])\d{3,5} ?[x×] ?(\d{3,4})(?![\w.])', re.I)
HEAVY_LINES = 2160


def heavy(text):
    """Whether a label names a render of 2160 lines or more."""
    for match in FLAG_HEAVY.finditer(text):
        if re.search(r'shadows?\W*(?:res\w*|quality|map)?\W*$', text[:match.start()], re.I):
            continue
        kilo, lines, height = match.groups()
        if (kilo and int(kilo) >= 4) or (lines and int(lines) >= HEAVY_LINES) or (height and int(height) >= HEAVY_LINES):
            return True
    return False


def one_mode(name):
    """Whether a name gives the game's default of one console mode only."""
    handheld, docked = bool(MODE_HANDHELD.search(name)), bool(MODE_DOCKED.search(name))
    return handheld != docked or (handheld and bool(ONE_MODE_DEFAULT.search(name)))


def entry_flags(entry, said=()):
    """Flags of one entry from its name, and from what its author says of it ([said]: notes, label,
    description). The name alone decides what it restores, refreshes and renders."""
    name = entry.get('name') or ''
    text = ' '.join([name, *(str(part) for part in said if part)])
    flags = set()
    if FLAG_DEFAULT.search(name) and not one_mode(name):
        flags.add('default')
    if entry.get('cat') == 'fps' and ('default' in flags or FLAG_NO_REFRESH.search(name)):
        flags.add('noRefresh')
    if FLAG_EXPERIMENTAL.search(text):
        flags.add('experimental')
    if any(FLAG_CRASH.search(sentence) and not FLAG_CRASH_NOT.search(sentence)
           for sentence in re.split(r'(?<=[.!?])\s+', text)):
        flags.add('crashRisk')
    if entry.get('cat') != 'cheat' and heavy(name):
        flags.add('heavy')
    if FLAG_DRAM.search(text):
        flags.add('dram8gb')
    return sorted(flags)


# A Switch title's notes name the code they warn about: `[Use TAAU] only for use with [AA Mode = TAA] &
# [AA Medium], else will crash the game` (ChanseyIsTheBest, Hazerou).
CREDIT_CRASH = re.compile(r'\[([^\[\]]{2,80})\] only for use with [^.]*?\b(?:else|otherwise)\b[^.]*?'
                          r'\b(?:will|may|can|might) crash', re.I)


def credited_crashes(credits):
    """Code names a title's notes say crash the game outside their conditions."""
    return {match.group(1).strip().casefold() for credit in credits for match in CREDIT_CRASH.finditer(str(credit))}


def finish_flags(engine, records):
    """Flags of every entry of an engine, built or reused (idempotent); returns the count of each flag."""
    counts = collections.Counter()
    for record in records.values():
        crashes = credited_crashes(record.get('credits', ())) if engine == 'melonx' else set()
        for entry in record['entries']:
            said = [entry.get(field) for field in ('notes', 'label', 'description')]
            flags = set(entry_flags(entry, said))
            if crashes:
                base = re.sub(r'^default\s+', '', entry['name'].casefold())
                if any(base == name or base.startswith((name + ' ', name + '(')) for name in crashes):
                    flags.add('crashRisk')
            if flags:
                entry['flags'] = sorted(flags)
            else:
                entry.pop('flags', None)
            counts.update(flags)
    return dict(sorted(counts.items()))


# ---------------------------------------------------------------- inputs

def fetch_git(cache, source_id, offline):
    source = SOURCES.get(source_id) or RESTRICTION_INPUTS[source_id]
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

# Authors who restrict where their codes may appear. A title carrying such a
# notice in any source is left out.
RESTRICTED = re.compile(
    r"exclusive to gbatemp|outside (of )?gbatemp|do not (steal|distribute|re-?post|re-?upload|share)|"
    r"don'?t (steal|distribute|re-?post|re-?upload|share)|(re)?distribution (is )?(prohibited|forbidden|not allowed)|"
    r"spreading codes .* prohibited", re.I)
# cp1252 sequences produced when UTF-8 text was decoded as Latin-1.
MOJIBAKE = re.compile('[ÂÃâîï][\u0080-¿ŒœŠšŸŽžƒˆ˜–—‘-„†-•…‰‹›€™]')


def switch_lines(body):
    """Opcode words of one Atmosphere section, or None when any line is not one.
    lib/services/enhancements/enhancement_origin.dart applies the same rule."""
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


# What an Atmosphere code stores to, read the way Ryujinx compiles it (Ryujinx.HLE/HOS/Tamper): each cheat is its
# own program, one instruction per line, its sixteen registers start at 0 and keep their values between frames.
# A value is (terms, offset): a sum of symbolic terms (a memory region's base, a value loaded from an address,
# another operation) plus a 64-bit constant. Two codes that store to the same terms, offsets, widths and
# conditions write the same memory: they are alternatives of one setting. A register a code never sets reads 0,
# but Atmosphere runs a title's master code and enabled cheats as one program, where it holds what they left: a
# store must start from a memory region, and one through such a register alone (`640F0000 …` after a master code
# that loads R13 to R15) is never compared. Added to a region (type 0's `R`: `04010000 …` beside `04000000 …`), it
# is the 0 the author relies on. Only the opcodes below are modelled; any other (loops, register conditions,
# saves, key holds of type C4, pauses) leaves a code out of grouping.
ATMOSPHERE_WIDTHS = {1, 2, 4, 8}
ATMOSPHERE_ARITHMETIC = ('add', 'sub', 'mul', 'lsh', 'rsh', 'and', 'or', 'not', 'xor', 'mov')
U64 = (1 << 64) - 1


def atmosphere_instruction(line):
    """One Atmosphere instruction as a tuple, or None when it is not one of the modelled encodings."""
    words = line.split()
    nib = ''.join(words)
    if not words or any(len(word) != 8 for word in words):
        return None
    kind, width = nib[0], int(nib[1], 16)
    if kind == '0':  # 0TMR00AA AAAAAAAA VVVVVVVV (VVVVVVVV): store a value to region M + register R + A
        region = int(nib[2], 16)
        if width in ATMOSPHERE_WIDTHS and region <= 3 and nib[4:6] == '00' and len(words) == (4 if width == 8 else 3):
            return ('store', width, region, int(nib[3], 16), int(nib[6:16], 16))
    elif kind == '1':  # 1TMC00AA AAAAAAAA VVVVVVVV (VVVVVVVV): begin a block run when memory compares to a value
        region, condition = int(nib[2], 16), int(nib[3], 16)
        if width in ATMOSPHERE_WIDTHS and region <= 3 and 1 <= condition <= 6 and nib[4:6] == '00' and \
                len(words) == (4 if width == 8 else 3):
            return ('if', 'memory', width, region, condition, int(nib[6:16], 16), int(nib[16:], 16))
    elif kind == '2':  # 20000000 ends a block, 21000000 starts its else part
        if line in ('20000000', '21000000'):
            return ('end',) if line == '20000000' else ('else',)
    elif kind == '4':  # 400R0000 VVVVVVVV VVVVVVVV: register R = V
        if nib[1:3] == '00' and nib[4:8] == '0000' and len(words) == 3:
            return ('set', int(nib[3], 16), int(nib[8:24], 16))
    elif kind == '5':  # 5TMRI0AA AAAAAAAA: R = [region M + A] (I=0) or [R + A] (I=1)
        region, mode = int(nib[2], 16), nib[4]
        if width in ATMOSPHERE_WIDTHS and region <= 3 and mode in '01' and nib[5] == '0' and len(words) == 2:
            return ('load', width, region, int(nib[3], 16), mode == '1', int(nib[6:16], 16))
    elif kind == '6':  # 6T0RIor0 VVVVVVVV VVVVVVVV: store V to [R (+ r)], then R += T when I
        if width in ATMOSPHERE_WIDTHS and nib[2] == '0' and nib[4] in '01' and nib[5] in '01' and nib[7] == '0' and \
                len(words) == 3:
            return ('store_at', width, int(nib[3], 16), nib[4] == '1', nib[5] == '1', int(nib[6], 16))
    elif kind == '7':  # 7T0RC000 VVVVVVVV: R = R op V
        operation = int(nib[4], 16)
        if width in ATMOSPHERE_WIDTHS and nib[2] == '0' and operation <= 4 and nib[5:8] == '000' and len(words) == 2:
            register = int(nib[3], 16)
            return ('math', width, ATMOSPHERE_ARITHMETIC[operation], register, register, None, int(nib[8:16], 16))
    elif kind == '8':  # 8kkkkkkk: begin a block run while these keys are held
        if len(words) == 1:
            return ('if', 'keys', int(nib[1:8], 16))
    elif kind == '9':  # 9TCRS0s0: R = S op s; 9TCRS100 VVVVVVVV (VVVVVVVV): R = S op V
        operation = int(nib[2], 16)
        if width in ATMOSPHERE_WIDTHS and operation <= 9:
            target, left = int(nib[3], 16), int(nib[4], 16)
            if nib[5] == '0' and nib[7] == '0' and len(words) == 1:
                return ('math', width, ATMOSPHERE_ARITHMETIC[operation], target, left, int(nib[6], 16), None)
            if nib[5] == '1' and nib[6:8] == '00' and len(words) == (3 if width == 8 else 2):
                return ('math', width, ATMOSPHERE_ARITHMETIC[operation], target, left, None, int(nib[8:], 16))
    elif kind == 'A':  # ATSRIOxa (aaaaaaaa): store register S to the address offset type O gives, R += T when I
        offset, extra = int(nib[5], 16), int(nib[6], 16)
        immediate = offset in (2, 4, 5)
        if width in ATMOSPHERE_WIDTHS and nib[4] in '01' and offset <= 5 and len(words) == (2 if immediate else 1) \
                and (offset < 3 or extra <= 3) and (immediate or nib[7] == '0'):
            return ('store_reg', width, int(nib[2], 16), int(nib[3], 16), nib[4] == '1', offset, extra,
                    int(nib[7:], 16) if immediate else 0)
    return None


def _value_add(a, b):
    return tuple(sorted(a[0] + b[0])), (a[1] + b[1]) & U64


def _value_math(name, width, a, b):
    """A register after an arithmetic opcode: exact on constants and 64-bit offsets, symbolic otherwise."""
    if name == 'mov':
        return a
    if name == 'add' and width == 8:
        return _value_add(a, b)
    if name == 'sub' and width == 8 and not b[0]:
        return a[0], (a[1] - b[1]) & U64
    if not a[0] and not b[0] and name != 'not':
        x, y = a[1], b[1]
        result = {'add': x + y, 'sub': x - y, 'mul': x * y, 'lsh': x << (y & 63), 'rsh': x >> (y & 63),
                  'and': x & y, 'or': x | y, 'xor': x ^ y}[name]
        return (), result & ((1 << (8 * width)) - 1)
    return (('op', name, width, a, b),), 0


def anchored(value):
    """Whether an address starts from a memory region, directly or through a pointer loaded from one."""
    return any(term[0] == 'region' or (term[0] == 'load' and anchored(term[2]))
               or (term[0] == 'op' and (anchored(term[3]) or anchored(term[4]))) for term in value[0])


def atmosphere_writes(lines):
    """The memory an Atmosphere code stores to: a frozenset of (conditions, width, address), whatever the
    values. None when the code uses an encoding not modelled here, reads a register its previous run left
    (or one set in a block that has ended), stores to an address no memory region anchors, leaves a block
    open, or stores nothing."""
    program = [atmosphere_instruction(line) for line in lines]
    if not program or None in program:
        return None
    assigned = set()
    for op in program:
        if op[0] in ('set', 'math'):
            assigned.add(op[1] if op[0] == 'set' else op[3])
        elif op[0] == 'load':
            assigned.add(op[3])
        elif op[0] == 'store_at' and op[3]:
            assigned.add(op[2])
        elif op[0] == 'store_reg' and op[4]:
            assigned.add(op[3])
    registers, blocks, stores = {}, [], set()

    def read(register):
        if register not in registers:
            if register in assigned:
                raise LookupError
            return (), 0  # an address built on it alone is never compared (anchored)
        value, where = registers[register]
        if tuple(blocks[:len(where)]) != where:
            raise LookupError
        return value

    def write(register, value):
        registers[register] = (value, tuple(blocks))

    def region(number):
        return (('region', number),), 0

    try:
        for op in program:
            kind = op[0]
            if kind == 'store':
                _, width, number, register, offset = op
                stores.add((tuple(blocks), width, _value_add(_value_add(region(number), read(register)), ((), offset))))
            elif kind == 'if':
                blocks.append(op)
            elif kind == 'end':
                blocks.pop()
            elif kind == 'else':
                if blocks[-1][0] == 'else':
                    return None
                blocks[-1] = ('else', blocks[-1])
            elif kind == 'set':
                write(op[1], ((), op[2]))
            elif kind == 'load':
                _, width, number, register, relative, offset = op
                base = read(register) if relative else region(number)
                write(register, ((('load', width, _value_add(base, ((), offset))),), 0))
            elif kind == 'store_at':
                _, width, register, increment, offset, offset_register = op
                address = read(register)
                if offset:
                    address = _value_add(address, read(offset_register))
                stores.add((tuple(blocks), width, address))
                if increment:
                    write(register, _value_add(read(register), ((), width)))
            elif kind == 'math':
                _, width, name, target, left, right, immediate = op
                write(target, _value_math(name, width, read(left), read(right) if right is not None else ((), immediate)))
            else:  # store_reg
                _, width, source, register, increment, offset, extra, immediate = op
                read(source)
                if offset in (0, 1, 2):
                    address = read(register)
                    if offset == 1:
                        address = _value_add(address, read(extra))
                else:
                    address = region(extra) if offset == 4 else _value_add(region(extra), read(register))
                if offset in (2, 4, 5):
                    address = _value_add(address, ((), immediate))
                stores.add((tuple(blocks), width, address))
                if increment:
                    write(register, _value_add(read(register), ((), width)))
    except (LookupError, IndexError):
        return None
    if blocks or not stores or not all(anchored(address) for _, _, address in stores):
        return None
    return frozenset(stores)


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


def switch_restricted_titles(scdb, matias):
    """Title IDs whose authors limit distribution, in either collection."""
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


PCHTXT_HEADER = re.compile(r'^@nsobid-([0-9A-Fa-f]{32,64})$')
# Choices that patch the same values of a game (render resolution, aspect ratio): one at a time.
SWITCH_DISPLAY = re.compile(r'\b\d{3,4}p\b|\b\d{3,4} ?x ?\d{3,4}\b|\b[24581]K\b|ultra ?wide|wide ?screen|\baspect\b|'
                            r'\b(?:4|5|15|16|17|18|19|20|21|24|32|40|43) ?[:.] ?(?:3|4|9|10)\b|\bSSAA\b', re.I)
# A game version in a label (`v1.3.2`, `1.0.19975`, `V4.04b`) is not an aspect ratio. Until the catalogue of
# 18 November 2026 one put frame-rate and effect mods (`120FPS v1.3.2`, `Disable Dof v4.0.1`) among the display
# choices of their title, so turning a resolution or ultrawide mod on turned them off.
SWITCH_VERSION = re.compile(r'(?<![\w.])v?\d+(?:\.\d+){2,}[a-z]?(?![\w.])|(?<![\w.])v\d+(?:\.\d+)+[a-z]?(?![\w.])', re.I)
# The display version a Switch patch file is named after (`1.3.2.pchtxt`).
SWITCH_PATCH_VERSION = re.compile(r'^v?(\d+(?:\.\d+)+)\.pchtxt$', re.I)
BRACKET_TITLE = re.compile(r'^(?:.* )?\[(0100[0-9A-Fa-f]{12})\]$')
VERSION_NAME = re.compile(r'^v?\d+(?:\.\d+)+$', re.I)


def pchtxt_text(raw):
    """(Build ID, text) of an IPSwitch patch file as the app writes it, or None.

    Strict UTF-8, carriage returns removed, the Build ID of the first line
    in upper case (Ryujinx compares it case-sensitively), one final newline.
    EnhancementOrigin applies the same rules and checks the SHA-256."""
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError:
        return None
    if text.startswith('\ufeff'):
        return None
    lines = text.replace('\r', '').split('\n')
    header = PCHTXT_HEADER.match(lines[0])
    if not header:
        return None
    bid = header.group(1).upper()
    body = '\n'.join(['@nsobid-' + bid] + lines[1:])
    if not body.endswith('\n'):
        body += '\n'
    return (bid, body) if len(body) <= 64 * 1024 else None


def readme_credits(folder):
    """Credits a title's readme states (after "Credits:" or under a "Credits" heading), as one line.

    Links keep their text only; support and donation lines are not credits."""
    for name in ('readme.md', 'README.md', 'Readme.md'):
        if (folder / name).is_file():
            lines = (folder / name).read_text(encoding='utf-8', errors='replace').replace('\r', '').split('\n')
            break
    else:
        return ''
    found = []
    for index, line in enumerate(lines):
        inline = re.match(r'^\s*\**Credits\**\s*:\**\s*(.*)$', line, re.I)
        heading = re.match(r'^#+\s*Credits\s*$', line, re.I)
        if inline and inline.group(1).strip():
            found.append(inline.group(1))
        elif inline or heading:
            for following in lines[index + 1:index + 14]:
                if following.startswith('#'):
                    break
                found.append(following)
        original = re.search(r'orig\w* made by \[?([\w .-]{2,40})', line, re.I)
        if original:
            found.append(f'{original.group(1).strip()} (original author)')
    names = []
    for line in found:
        line = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', line).strip().lstrip('-*').strip().strip('*').strip()
        if not line or re.search(r'https?://|ko-?fi|donate|support', line, re.I):
            continue
        if line.casefold() not in {name.casefold() for name in names}:
            names.append(line)
    return clean_label(', '.join(names), 200).rstrip('. ')


def build_melonx_exefs(root, source_id, titles, restricted, stats):
    """Exefs patches of a repository laid out <game>/<Title ID>/<mod>/exefs/<version>.pchtxt,
    by reference: per mod, one pointer per patch file (Build ID, origin file, size and SHA-256
    of the text the app writes). Nothing of the patch itself is published."""
    mods = {}
    bracket = SOURCES[source_id].get('layout') == 'bracket'
    for path in sorted(root.glob('*/*/**/*.pchtxt' if bracket else '*/*/**/exefs/*.pchtxt')):
        parts = path.relative_to(root).parts
        if bracket:
            # <game>/[<Title ID>]/<mod>/<version>.pchtxt; a folder that only repeats the version is not part of the name.
            named = BRACKET_TITLE.match(parts[1])
            tid = named.group(1).upper() if named else ''
            folders = [part for part in parts[2:-1] if part.casefold() != 'exefs']
            if len(folders) > 1 and folders[-1] == path.stem and VERSION_NAME.match(folders[-1]):
                folders = folders[:-1]
            name = clean_label(' - '.join(folders), 120)
        else:
            tid = parts[1].upper()
            name = clean_label(' - '.join(parts[2:-2]), 120)
        if not SWITCH_TITLE.match(tid) or not name:
            stats['melonx_exefs_rejected'] += 1
            continue
        if tid in restricted:
            stats['melonx_restricted_skipped'] += 1
            continue
        raw = path.read_bytes()
        read = pchtxt_text(raw)
        if read is None:
            stats['melonx_exefs_rejected'] += 1
            continue
        bid, text = read
        mod = mods.setdefault((tid, name.casefold()), {'tid': tid, 'name': name, 'game': parts[0], 'files': {},
                                                       'folders': [root.joinpath(*parts[:depth])
                                                                   for depth in range(len(parts) - 1, 1, -1)]})
        if bid in mod['files']:
            stats['melonx_exefs_rejected'] += 1  # two files of one mod for the same executable
            continue
        encoded = text.encode('utf-8')
        mod['files'][bid] = {'path': path.relative_to(root).as_posix(), 'raw_size': len(raw),
                             'raw_sha256': hashlib.sha256(raw).hexdigest(), 'size': len(encoded),
                             'sha256': hashlib.sha256(encoded).hexdigest()}
    for (tid, _), mod in sorted(mods.items()):
        record = titles.setdefault(tid, {'title': '', 'credits': [], 'origin': [], 'master': {}, 'entries': {}, 'seen': {}})
        record['title'] = record['title'] or clean_label(mod['game'], 120)
        author = SOURCES[source_id]['author']
        credit = f'Exefs patches by {author} ({SOURCES[source_id]["url"]}).'
        # The readme nearest to the patch file speaks for it: the mod's own, else the title's.
        stated = next(filter(None, map(readme_credits, mod['folders'])), '') if bracket else ''
        if stated and stated.casefold() != author.casefold():
            # The title's readme credits other people than the repository's owner: its words are kept.
            credit = f'Exefs patches published by {author} ({SOURCES[source_id]["url"]}); credits of its readme: {stated}.'
        if credit not in record['credits']:
            record['credits'].append(credit)
        key = 'exefs/' + mod['name'].casefold()
        if key in record['entries']:
            if record['entries'][key]['source'] == source_id:
                stats['melonx_exefs_rejected'] += 1
                continue
            # The same mod name from another author: both stay, the later one carries its author's name.
            mod['name'] = clean_label(f"{mod['name']} ({author})", 120)
            key = 'exefs/' + mod['name'].casefold()
            if key in record['entries']:
                stats['melonx_exefs_rejected'] += 1
                continue
            stats['melonx_exefs_same_name'] += 1
        patches = []
        for bid, item in sorted(mod['files'].items()):
            record['origin'].append({'source': source_id, 'path': item['path'], 'size': item['raw_size'],
                                     'sha256': item['raw_sha256']})
            patches.append({'bid': bid, 'o': len(record['origin']) - 1, 'size': item['size'], 'sha256': item['sha256']})
        category = classify(mod['name'], 'graphics')
        # The first source's IDs are published: they keep their shape; a later source's ID carries its source.
        identity = ('melonx', tid, 'exefs', mod['name'].casefold()) if not bracket else \
            ('melonx', tid, 'exefs', source_id, mod['name'].casefold())
        # The mod's author: the people its readme credits, else the repository's owner.
        entry = {'id': stable_id(*identity), 'cat': category, 'name': mod['name'],
                 'source': source_id, 'exefs': patches, 'author': clean_label(stated or author, 200)}
        record['entries'][key] = entry
        stats['melonx_exefs_entries'] += 1


def has_enabled_ipswitch_write(text):
    """Some releases include an empty template for one executable version."""
    enabled = False
    for raw in text.splitlines()[1:]:
        if not raw.strip():
            enabled = False
        line = raw.split('//', 1)[0].strip()
        if line.startswith('@stop'):
            break
        if line.startswith('@enabled'):
            enabled = True
        elif line.startswith('@disabled'):
            enabled = False
        elif enabled and re.match(r'^[0-9a-fA-F]{1,8} +(?:[0-9a-fA-F]{2}|")', line):
            return True
    return False


def build_melonx_zip(root, titles, restricted, stats):
    """Only publish pointers for complete mods the two existing Switch installers can apply."""
    source = 'fl4sh-zip'
    for package in sorted(root.glob('*.zip')):
        match = re.search(r'\[(0100[0-9a-fA-F]{12})\]', package.stem)
        if not match or match[1].upper() in restricted:
            stats['fl4sh_archives_unmatched_or_restricted'] += 1
            continue
        tid = match[1].upper()
        groups = collections.defaultdict(list)
        with zipfile.ZipFile(package) as archive:
            for item in archive.infolist():
                if item.is_dir():
                    continue
                parts = item.filename.split('/')
                if any(part in ('', '.', '..') or '\\' in part for part in parts):
                    raise ValueError(f'Unsafe ZIP member in {package.name}')
                for i, part in enumerate(parts):
                    if part.lower() in ('exefs', 'romfs', 'cheats'):
                        groups[tuple(parts[:i])].append((part.lower(), parts[i + 1:], item))
                        break
            record = titles.setdefault(tid, {'title': '', 'credits': [], 'origin': [], 'master': {}, 'entries': {}, 'seen': {}})
            origin = len(record['origin'])
            pending = {}
            for folder, items in sorted(groups.items()):
                label = clean_label(' - '.join(part.strip('[]') for part in folder), 120)
                if not label or package.stat().st_size > 16 << 20 or any(
                        len(parts) != 1 or item.file_size > 65536 or item.flag_bits & 1
                        for _, parts, item in items):
                    stats['fl4sh_groups_not_installable'] += 1
                    continue
                patches = {}
                cheats = {}
                bodies = {}
                has_empty_patch = False
                for layout, parts, item in items:
                    raw = archive.read(item)
                    member = {'o': origin, 'member': item.filename, 'rawSize': len(raw)}
                    if layout == 'exefs' and parts[0].lower().endswith('.pchtxt'):
                        read = pchtxt_text(raw)
                        if not read or read[0] in patches:
                            break
                        bid, body = read
                        if not has_enabled_ipswitch_write(body):
                            has_empty_patch = True
                            stats['fl4sh_empty_patch_versions'] += 1
                            continue
                        encoded = body.encode()
                        patches[bid] = {**member, 'bid': bid, 'size': len(encoded), 'sha256': hashlib.sha256(encoded).hexdigest()}
                    elif layout == 'cheats' and re.fullmatch(r'[0-9A-Fa-f]{16}\.txt', parts[0], re.I):
                        # Keep only complete, independent Atmosphère sections. A master or an
                        # unrecognised line makes this whole mod unsuitable for the cheat installer.
                        bid = parts[0][:-4].upper()
                        try:
                            lines = raw.decode('utf-8-sig').replace('\r', '').splitlines()
                        except UnicodeError:
                            break
                        active = None
                        sections = {}
                        valid = True
                        for line in (s.strip() for s in lines if s.strip()):
                            if line.startswith('[') and line.endswith(']') and line not in sections:
                                active = line
                                sections[active] = []
                            elif active and switch_lines([line]):
                                sections[active].append(line)
                            else:
                                valid = False
                                break
                        sections = {key: body for key, body in sections.items() if body}
                        if not valid or not sections or not all(switch_lines(body) for body in sections.values()):
                            break
                        for section in sections:
                            builds = cheats.setdefault(section, {})
                            if bid in builds:
                                valid = False
                                break
                            builds[bid] = {**member, 'k': section}
                            bodies[(section, bid)] = sections[section]
                        if not valid:
                            break
                    else:
                        break
                else:
                    # The patch and cheat of a combined release must target the same executable.
                    if has_empty_patch and cheats:
                        stats['fl4sh_groups_not_installable'] += 1
                        continue
                    if patches and not cheats:
                        pending[('exefs', folder)] = (label, {'exefs': [patches[k] for k in sorted(patches)]})
                        continue
                    if patches and len(cheats) == 1:
                        builds = next(iter(cheats.values()))
                        if set(builds) == {bid[:16] for bid in patches}:
                            pending[('combined', folder)] = (label, {'exefs': [patches[k] for k in sorted(patches)], 'builds': builds})
                            continue
                    if cheats and not patches:
                        for section, builds in sorted(cheats.items()):
                            name = clean_label(section[1:-1], 120)
                            if not name or not switch_name(section):
                                continue
                            writes = {bid: atmosphere_writes([line.upper() for line in bodies[(section, bid)]])
                                      for bid in builds}
                            stats['melonx_alt_codes_not_compared'] += sum(value is None for value in writes.values())
                            writes = {bid: value for bid, value in writes.items() if value is not None}
                            pending[('cheat', folder, section)] = (name, {'builds': builds,
                                                                          **({'_writes': writes} if writes else {})})
                        continue
                stats['fl4sh_groups_not_installable'] += 1
            if not pending:
                continue
            record['title'] = record['title'] or clean_label(package.stem[:match.start()], 120)
            record['credits'].append('Mods published by Fl4sh9174 and the authors credited in the original archives.')
            with package.open('rb') as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            record['origin'].append({'source': source, 'path': package.name, 'size': package.stat().st_size, 'sha256': digest})
            for key, (label, payload) in pending.items():
                identity = stable_id('melonx', tid, source, key[0], *key[1], *key[2:])
                display_key = ('exefs/' if key[0] == 'exefs' else '') + label.casefold()
                if display_key in record['entries'] or any(e['name'].casefold() == label.casefold() for e in record['entries'].values()):
                    label = clean_label(f'{label} (Fl4sh9174 · {" / ".join(key[1])})', 180)
                category = classify(label, 'cheat' if key[0] == 'cheat' else 'graphics')
                entry = {'id': identity, 'name': label, 'source': source, 'cat': category, **payload}
                record['entries'][identity] = entry
                stats['fl4sh_' + key[0] + '_entries'] += 1


def build_melonx(scdb, matias, stats, exefs=(), archives=None):
    """switch-cheats-db by reference: per title, the origin files (path, size,
    SHA-256 at the pinned revision) and, per program and Build ID, the key of
    the code in that file. The app downloads the file and reads the lines.
    `exefs` adds the patch files of (checkout, source id) repositories the same way."""
    restricted = switch_restricted_titles(scdb, matias)
    stats['melonx_restricted_titles'] = sorted(restricted)
    titles = {}
    for folder, default in (('cheats', 'cheat'), ('cheats_gfx', 'graphics')):
        for path in sorted((scdb / folder).glob('*.json')):
            tid = path.stem.upper()
            if not SWITCH_TITLE.match(tid):
                stats['melonx_rejected_titles'] += 1
                continue
            if tid in restricted:
                stats['melonx_restricted_skipped'] += 1
                continue
            raw = path.read_bytes()
            data = json.loads(raw)
            record = titles.setdefault(tid, {'title': '', 'credits': [], 'origin': [], 'master': {},
                                             'entries': {}, 'seen': {}})
            origin = len(record['origin'])
            used = False
            for file_name, credit in sorted((data.get('attribution') or {}).items()):
                if not record['title']:
                    record['title'] = clean_label(re.sub(r'\.txt$', '', file_name, flags=re.I), 120)
                # Attribution files sometimes repeat the codes: keep every other line.
                prose = ' '.join(l.strip() for l in str(credit).splitlines()
                                 if l.strip() and not SWITCH_LINE.match(l.strip())
                                 and not (l.strip().startswith('[') and l.strip().endswith(']')))
                prose = re.sub(r'\s+', ' ', prose).strip()[:2000]
                if prose and prose not in record['credits'] and len(record['credits']) < 64:
                    record['credits'].append(prose)
            for build, cheats in data.items():
                if build == 'attribution':
                    continue
                if not SWITCH_BUILD.match(build) or not isinstance(cheats, dict):
                    stats['melonx_rejected_builds'] += 1
                    continue
                for raw_name, code in cheats.items():
                    lines = switch_lines(str(code).split('\n')[1:])
                    if lines is None:
                        stats['melonx_rejected_cheats'] += 1
                        continue
                    pointer = {'o': origin, 'k': raw_name}
                    if raw_name.strip().startswith('{'):
                        record['master'].setdefault(build, pointer)  # on with any cheat of its build
                        used = True
                        continue
                    name = repair_mojibake(switch_name(raw_name))
                    if not name:
                        stats['melonx_rejected_cheats'] += 1
                        continue
                    seen = record['seen'].setdefault(build, set())
                    body = tuple(lines)
                    entry = record['entries'].get(name.casefold())
                    category = classify(name, default)
                    if entry is None:
                        if body in seen:
                            stats['melonx_duplicate_cheats'] += 1
                            continue
                        entry = record['entries'][name.casefold()] = {
                            'id': stable_id('melonx', tid, name.casefold()), 'cat': category, 'name': name,
                            'source': 'switch-cheats-db', 'builds': {}}
                    if category != 'cheat' and entry['cat'] == 'cheat':
                        entry['cat'] = category
                    if build in entry['builds'] or body in seen:
                        stats['melonx_duplicate_cheats'] += 1
                        continue
                    entry['builds'][build] = pointer
                    # What the code stores to, for the alternatives' groups; never published.
                    writes = atmosphere_writes(lines)
                    if writes is not None:
                        entry.setdefault('_writes', {})[build] = writes
                    else:
                        stats['melonx_alt_codes_not_compared'] += 1
                    seen.add(body)
                    used = True
            if used:
                record['origin'].append({'source': 'switch-cheats-db', 'path': f'{folder}/{path.name}',
                                         'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
            else:
                # Pointers into an unused file are never written; keep indexes dense.
                assert not any(p['o'] == origin for e in record['entries'].values() for p in e['builds'].values())
    for root, source_id in exefs:
        build_melonx_exefs(root, source_id, titles, restricted, stats)
    if archives is not None:
        build_melonx_zip(archives, titles, restricted, stats)
    versions = switch_versions(scdb)
    out = {}
    for tid, record in sorted(titles.items()):
        entries = sorted(record['entries'].values(), key=lambda e: (e['cat'], e['name'].casefold()))
        if not entries:
            continue
        out[tid] = {'title': switch_title(versions, tid) or record['title'] or tid, 'credits': record['credits'],
                    'origin': record['origin'], 'master': record['master'], 'entries': entries}
    finish_melonx(out, versions, stats)
    return out


def switch_versions(scdb):
    """switch-cheats-db's versions.json at the pinned revision: per Title ID, the main Build ID of each
    update number (`0` the game itself) and the title's name."""
    path = scdb / 'versions.json'
    if not path.exists():
        return {}
    data = json.loads(path.read_bytes())
    return data if isinstance(data, dict) else {}


def switch_title(versions, tid):
    """The game's own name in versions.json (marks removed), or ''. The cheat files' headers name an author's
    file (`Mario Kart 8 Deluxe 1.7.1 by Xtatu speed mod`, `1`), not the game."""
    known = versions.get(tid) or versions.get(tid.lower())
    title = known.get('title') if isinstance(known, dict) else None
    return clean_label(re.sub('[\u2122\u00ae\u00a9]', '', title), 120) if isinstance(title, str) else ''


def switch_group(tid, entry):
    """Exclusive group of a Switch entry. The resolution and aspect-ratio mods of a title are one choice
    (`display/`); its exefs frame-rate mods patch the same frame limit and are another (`fps/`). A frame-rate
    mod is never a display choice, and a game version in a name is not an aspect ratio."""
    label = SWITCH_VERSION.sub(' ', entry['name'])
    exefs = 'exefs' in entry
    if entry['cat'] == 'fps':
        return f'fps/{tid}' if exefs else ''
    if (exefs or entry.get('source') == 'fl4sh-zip') and SWITCH_DISPLAY.search(label):
        return f'display/{tid}'
    return display_group(tid, label, entry['cat'])


def version_key(text):
    return tuple(int(part) for part in text.split('.'))


def switch_releases(tid, record, versions):
    """Game versions the catalogue knows for the Build IDs of a title's entries: the display version each
    patch file is named after (`1.3.2.pchtxt`) and switch-cheats-db's update numbers. Without versions.json
    (a reused record), the update numbers already published are kept."""
    builds, display, updates = set(), collections.defaultdict(set), collections.defaultdict(set)
    for entry in record['entries']:
        builds.update(entry.get('builds', {}))
        for patch in entry.get('exefs', ()):
            build = patch['bid'][:16].upper()
            builds.add(build)
            name = (patch.get('member') or record['origin'][patch['o']]['path']).rsplit('/', 1)[-1]
            match = SWITCH_PATCH_VERSION.match(name)
            if match:
                display[build].add(match.group(1))
    if versions is None:
        for build, value in (record.get('releases') or {}).items():
            updates[build].update(value.get('update', ()))
    else:
        known = versions.get(tid) or versions.get(tid.lower())
        for number, build in (known.items() if isinstance(known, dict) else ()):
            if str(number).isdigit() and isinstance(build, str) and SWITCH_BUILD.match(build.upper()):
                updates[build.upper()].add(int(number))
    releases = {}
    for build in sorted(builds):
        value = {}
        if display[build]:
            value['display'] = sorted(display[build], key=version_key)
        if updates[build]:
            value['update'] = sorted(updates[build])
        if value:
            releases[build] = value
    return releases


def switch_latest(tid, record, versions):
    """The newest update versions.json knows for a title: its number (`update`, `v393216`; update 6 is
    393216 >> 16), the Build ID of its main executable (`build`) when listed, and the display version a patch
    file of that build is named after (`display`). Kept as published without versions.json (a reused record)."""
    if versions is None:
        return record.get('latest')
    known = versions.get(tid) or versions.get(tid.lower())
    number = known.get('latest') if isinstance(known, dict) else None
    if not isinstance(number, int) or isinstance(number, bool) or number < 0:
        return None
    latest = {'update': number}
    build = known.get(str(number))
    if isinstance(build, str) and SWITCH_BUILD.match(build.upper()):
        latest['build'] = build.upper()
        display = (record.get('releases') or {}).get(latest['build'], {}).get('display')
        if display:
            latest['display'] = display[-1]
    return latest


def fold_switch_updates(records, versions, stats):
    """A record keyed by an update's Title ID (low 13 bits 0x800) joins its application's record: the app looks
    only the application's Title ID up (these entries were never offered until 23 November 2026), and Ryujinx
    reads an update's cheats and patches from the application's folder. Entries keep their IDs. A name the
    application already uses gets ` (update)`; a build its namesake already has under that name stays with the
    namesake (the builder's rule for one name), unless the entry would be left without a build. Idempotent."""
    for key in sorted(records):
        number = int(key, 16)
        if number & 0x1FFF != 0x800:
            continue
        application = '%016X' % (number & ~0x1FFF)
        source = records.pop(key)
        record = records.get(application)
        if record is None:
            title = switch_title(versions or {}, application) or (source['title'] if source['title'] != key else '')
            record = records[application] = {'title': title or application, 'credits': [], 'origin': [],
                                             'master': {}, 'entries': []}
        base = len(record['origin'])
        record['origin'].extend(source['origin'])

        def rebased(pointer):
            return {**pointer, 'o': pointer['o'] + base}
        for build, pointer in sorted(source['master'].items()):
            record['master'].setdefault(build, rebased(pointer))  # one master per build: the first, as built
        namesakes = {entry['name'].casefold(): entry for entry in record['entries']}
        labels = set(namesakes)
        for entry in source['entries']:
            entry = dict(entry)
            if 'builds' in entry:
                entry['builds'] = {build: rebased(pointer) for build, pointer in entry['builds'].items()}
            if 'exefs' in entry:
                entry['exefs'] = [rebased(patch) for patch in entry['exefs']]
            namesake = namesakes.get(entry['name'].casefold())
            if namesake is not None:
                if 'builds' in entry and 'builds' in namesake and 'exefs' not in entry and 'exefs' not in namesake:
                    own = {build: pointer for build, pointer in entry['builds'].items() if build not in namesake['builds']}
                    if own and len(own) < len(entry['builds']):
                        stats['melonx_update_builds_left_to_namesake'] += len(entry['builds']) - len(own)
                        entry['builds'] = own
                        if '_writes' in entry:
                            entry['_writes'] = {build: value for build, value in entry['_writes'].items() if build in own}
                entry['name'] = azahar_label(entry['name'], '(update)', labels)
                stats['melonx_update_entries_renamed'] += 1
            else:
                labels.add(entry['name'].casefold())
            namesakes[entry['name'].casefold()] = entry
            record['entries'].append(entry)
        record['credits'].extend(credit for credit in source['credits'] if credit not in record['credits'])
        record['entries'].sort(key=lambda e: (e['cat'], e['name'].casefold()))
        stats.setdefault('melonx_keys_moved', {})[key] = application
        stats['melonx_entries_moved'] += len(source['entries'])


def balanced_label(text):
    """A label whose square brackets were half removed (`Unlock FPS v1.3.2] Ryujinx`, from the folder
    `[Unlock FPS v1.3.2] Ryujinx`), read as the folder meant it: the first bracketed part is the name, the
    rest a qualifier (`Unlock FPS v1.3.2 (Ryujinx)`). Each ` - ` part of a label is read on its own."""
    parts = []
    for part in text.split(' - '):
        chunks = [chunk.strip() for chunk in re.split(r'[\[\]]', part) if chunk.strip()]
        rest = ' '.join(chunks[1:])
        if rest.startswith('(') and rest.endswith(')') and rest.count('(') == 1:
            rest = rest[1:-1].strip()
        parts.append(f'{chunks[0]} ({rest})' if rest else chunks[0] if chunks else part)
    return clean_label(' - '.join(parts), 120)


def brackets_balanced(text):
    depth = 0
    for char in text:
        depth += {'[': 1, ']': -1}.get(char, 0)
        if depth < 0:
            return False
    return depth == 0


def fl4sh_folder(entry):
    """The folder names a Fl4sh9174 mod has in its archive (`[Unlock FPS v1.3.2] Ryujinx`), from a member."""
    for pointer in [*entry.get('exefs', ()), *entry.get('builds', {}).values()]:
        parts = str(pointer.get('member', '')).split('/')
        for index, part in enumerate(parts):
            if index and part.lower() in ('exefs', 'romfs', 'cheats'):
                return parts[:index]
    return None


def balance_switch_name(entry, labels, stats):
    """A name with broken square brackets, mended; the author's whole folder name goes to the notes."""
    if brackets_balanced(entry['name']):
        return
    fixed = balanced_label(entry['name'])
    if not fixed or fixed.casefold() in labels or not brackets_balanced(fixed):
        stats['melonx_names_left_unbalanced'] += 1
        return
    folder = fl4sh_folder(entry)
    original = ' - '.join(folder) if folder else entry['name']
    labels.discard(entry['name'].casefold())
    labels.add(fixed.casefold())
    entry['name'] = fixed
    entry['notes'] = clean_label(' '.join(filter(None, [original, entry.get('notes')])), 400)
    stats['melonx_names_balanced'] += 1


def switch_alternatives(tid, record, stats):
    """Exclusive groups of Atmosphere alternatives: cheat-file entries of one category whose codes store to the
    same memory, with the same widths and conditions, on a build they share (30/45/60 FPS, resolution or AA
    choices); the values differ. Entries linked through other builds join the same group, but a group never holds
    two codes that store to different memory on a build both have: one collision, often an error of the source
    file (Monster Hunter Rise `dog speed 2x` and `1p hitrange 1.5x` on one update), never joins codes that another
    shared build tells apart. Only the group's name is published (`alt/<Title ID>/<digest>`, the digest of the
    smallest write set its members share); an entry keeps a group it already has, and a group needs two entries
    without one."""
    entries = [entry for entry in record['entries'] if 'exefs' not in entry and entry.get('_writes')]
    parent = list(range(len(entries)))
    # What the members of each group store to, per build: two groups join only when they agree on every build.
    writes_of = [dict(entry['_writes']) for entry in entries]

    def find(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index
    holders, refused = collections.defaultdict(list), set()
    for index, entry in enumerate(entries):
        for build, writes in sorted(entry['_writes'].items()):
            key = (entry['cat'], build, writes)
            for other in holders[key]:
                one, two = find(other), find(index)
                if one == two:
                    continue
                small, large = sorted((writes_of[one], writes_of[two]), key=len)
                if any(large.get(shared, value) != value for shared, value in small.items()):
                    refused.add((other, index))
                    continue
                parent[two] = one
                writes_of[one].update(writes_of[two])
            holders[key].append(index)
    stats['melonx_alt_joins_refused'] += len(refused)
    members = collections.defaultdict(list)
    for index in range(len(entries)):
        members[find(index)].append(index)
    grouped, names = 0, set()
    for group in sorted(members.values()):
        free = [entries[index] for index in group if not entries[index].get('group')]
        if len(free) < 2:
            continue
        held = collections.Counter((entries[index]['cat'], build, writes)
                                   for index in group for build, writes in entries[index]['_writes'].items())
        text = min('\x1f'.join([cat, build, *sorted(repr(store) for store in writes)])
                   for (cat, build, writes), count in held.items() if count > 1)
        name = f'alt/{tid}/' + hashlib.sha1(text.encode()).hexdigest()[:10]
        if name in names:  # another group stores there too, but a shared build tells the two apart
            name = f'alt/{tid}/' + hashlib.sha1(f'{text}\x1f{free[0]["id"]}'.encode()).hexdigest()[:10]
        assert name not in names, name
        names.add(name)
        for entry in free:
            entry['group'] = name
        grouped += len(free)
        stats['melonx_alt_groups'] += 1
    if grouped:
        stats['melonx_alt_entries'] += grouped
        stats['melonx_alt_titles'] += 1


def finish_melonx(records, versions, stats):
    """Update records folded into their application, names, authors, groups and game versions of every
    Switch record, built or reused (idempotent). A reused record has no code: it keeps its `alt/` groups."""
    fold_switch_updates(records, versions, stats)
    for tid, record in records.items():
        labels = {entry['name'].casefold() for entry in record['entries']}
        for entry in record['entries']:
            balance_switch_name(entry, labels, stats)
            author = SOURCES.get(entry.get('source'), {}).get('author')
            if author:
                entry.setdefault('author', author)
        built = any('_writes' in entry for entry in record['entries'])
        for entry in record['entries']:
            group = switch_group(tid, entry)
            if group:
                entry['group'] = group
            elif built or not entry.get('group', '').startswith('alt/'):
                entry.pop('group', None)
        if built:
            switch_alternatives(tid, record, stats)
        for entry in record['entries']:
            entry.pop('_writes', None)
            group = entry.get('group', '')
            stats['melonx_group_' + (group.split('/')[0] if group else 'none')] += 1
        record['entries'].sort(key=lambda e: (e['cat'], e['name'].casefold()))
        releases = switch_releases(tid, record, versions)
        if releases:
            record['releases'] = releases
            stats['melonx_titles_with_versions'] += 1
        else:
            record.pop('releases', None)
        latest = switch_latest(tid, record, versions)
        if latest:
            record['latest'] = latest
            stats['melonx_titles_with_latest'] += 1
            stats['melonx_titles_with_latest_build'] += 'build' in latest
            stats['melonx_titles_with_latest_display'] += 'display' in latest
            if 'build' in latest:
                # Entries made for older updates only: none of their builds is the newest one.
                stats['melonx_entries_without_latest_build'] += sum(
                    1 for entry in record['entries']
                    if latest['build'] not in {*entry.get('builds', {}), *(p['bid'][:16] for p in entry.get('exefs', ()))})
        else:
            record.pop('latest', None)


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


ARTEMIS_SOURCES = ('artemis-rpcs3', 'artemis-rpcs3-pkg')


def merge_rpcs3_artemis(records, roots, stats):
    """Adds the Artemis collections to the RPCS3 records (built or reused). Idempotent: earlier
    Artemis entries are dropped first. A patch the official database already has for the same
    executable (same lines) is not listed twice; a name already taken gets the suffix "(Artemis)"."""
    for record in records.values():
        record['entries'] = [e for e in record['entries'] if e.get('source') not in ARTEMIS_SOURCES]
    for root, source_id in roots:
        for path in sorted(p for p in root.iterdir() if p.is_file() and not p.name.startswith('.')
                           and p.name not in ('LICENSE', 'README.md')):
            try:
                document = load_patch_yml(path.read_bytes().decode('utf-8'))
            except Exception:
                stats['rpcs3_artemis_unreadable'] += 1
                continue
            for hash_key, patches in document.items():
                if not RPCS3_HASH.match(str(hash_key)) or not isinstance(patches, dict):
                    continue
                for name, patch in patches.items():
                    if not isinstance(patch, dict) or not isinstance(patch.get('Games'), dict):
                        stats['rpcs3_artemis_rejected'] += 1
                        continue
                    variants = rpcs3_variants(clean_label(name, 160), patch)
                    if not variants:
                        stats['rpcs3_artemis_rejected'] += 1
                        continue
                    for title, by_serial in patch['Games'].items():
                        if not isinstance(by_serial, dict):
                            continue
                        title = re.sub(r'\s*\(Artemis\)\s*$', '', str(title))
                        for serial, versions in by_serial.items():
                            if not RPCS3_SERIAL.match(str(serial)) or not isinstance(versions, list):
                                continue
                            versions = sorted({v for v in versions if isinstance(v, str) and RPCS3_VERSION.match(v)})
                            if not versions:
                                continue
                            record = records.setdefault(serial, {'title': clean_label(title, 120), 'entries': []})
                            for label, lines, group, variant in variants:
                                target = {'hash': hash_key, 'title': clean_label(title, 200), 'versions': versions,
                                          'patch': lines}
                                same = [e for e in record['entries'] if e['name'].casefold() == label.casefold()]
                                if any(t['hash'] == hash_key and t['patch'] == lines
                                       for e in record['entries'] for t in e['targets']):
                                    stats['rpcs3_artemis_duplicate'] += 1
                                    continue
                                mine = [e for e in same if e['source'] in ARTEMIS_SOURCES]
                                if mine:
                                    mine[0]['targets'].append(target)
                                    continue
                                shown = label if not same else f'{label} (Artemis)'
                                if any(e['name'].casefold() == shown.casefold() for e in record['entries']):
                                    stats['rpcs3_artemis_duplicate'] += 1
                                    continue
                                record['entries'].append({
                                    'id': stable_id('rpcs3', serial, 'artemis', shown.casefold()), 'cat': classify(shown),
                                    'name': shown, 'author': clean_label(patch.get('Author'), 200),
                                    'notes': clean_label(patch.get('Notes'), 600),
                                    'patch_version': clean_label(patch.get('Patch Version'), 20),
                                    'group': group, 'variant': clean_label(variant, 40),
                                    'source': source_id, 'targets': [target]})
                                stats['rpcs3_artemis_entries'] += 1
    for record in records.values():
        record['entries'].sort(key=lambda e: (e['cat'], e['name'].casefold()))
        for entry in record['entries']:
            entry['targets'].sort(key=lambda t: (t['hash'], t['versions']))


# ---------------------------------------------------------------- ARMSX2

PS2_ANY_FILE = re.compile(r'^([A-Z]{4}-[0-9]{5})_([0-9A-Fa-f]{8})(?:_[^/]*)?\.pnach$')
# Licensed cheat sources, in priority order: (source id, glob, label).
PS2_EXTRA = (
    ('cookieplmonster-ccc', 'PS2/**/*.pnach', 'Silent'),
    ('aerowidescreen-pcsx2', '**/*.pnach', 'Aero'),
)
# Sources without a licence, read by reference (origin), in order of precedence.
PS2_ORIGIN = (
    ('pcsx2-patches', 'patches/*.pnach', 'PCSX2'),
    ('peterdelta-pcsx2', 'patches/*.pnach', 'PeterDelta'),
    ('gabominated-pcsx2', 'PCSX2 Patches/*.pnach', 'Gabominated'),
    ('nethersx2-cheats', 'cheats_*/*.pnach', 'NetherSX2'),
)
PS2_CRC_FILE = re.compile(r'^([0-9A-Fa-f]{8})\.pnach$')
ORIGIN_NOTICE = ('// No licence is stated by this source. RewindBox does not host these lines: the app read them '
                 'from the file above, at that revision.')


def pnach_blocks(raw):
    """The labelled groups of a pnach file as byte ranges: [(name, start, end)],
    where raw[start:end] holds the lines after the "[name]" header up to the end
    of the group's last non-blank line. Lines before the first group belong to none."""
    blocks, offset, current = [], 0, None
    for line in raw.split(b'\n'):
        end = offset + len(line)
        stripped = line.strip()
        if stripped.startswith(b'[') and stripped.endswith(b']') and len(stripped) > 2:
            current = [stripped[1:-1].strip(), min(end + 1, len(raw)), min(end + 1, len(raw))]
            blocks.append(current)
        elif current is not None and stripped:
            current[2] = end
        offset = end + 1
    return [tuple(block) for block in blocks]


def origin_body(raw, start, end):
    """The text the app writes for raw[start:end]: strict UTF-8 with carriage returns removed
    (EnhancementOrigin does the same), or None when the bytes are not UTF-8."""
    try:
        text = raw[start:end].decode('utf-8')
    except UnicodeDecodeError:
        return None
    # Dart's decoder drops a leading byte order mark: such a range is never published.
    return None if text.startswith('\ufeff') else text.replace('\r', '')


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


def licence_comment(root):
    """The MIT notice a copy of the source's code must carry, as pnach comments."""
    text = (root / 'LICENSE').read_text(encoding='utf-8').strip()
    return [('// ' + line).rstrip() for line in text.split('\n')]


def build_armsx2(roots, stats):
    """Per game: the patches ARMSX2 ships in its patches.zip, referenced by
    name only (enabled under [Patches]); then the labelled groups of licensed
    sources the zip lacks, in one cheat file the adapter writes to cheats/
    (enabled under [Cheats]). PCSX2 reads patches.zip only while patches/
    holds no file for the game, so nothing is written there. Groups of the
    sources without a licence follow, by reference: their names and authors,
    and the byte range of their lines in the source's own file."""
    import zipfile
    source = SOURCES['armsx2-patches-zip']
    games = {}
    with zipfile.ZipFile(roots['armsx2-patches-zip'] / source['sparse']) as archive:
        names = set(archive.namelist())
        for name in sorted(names):
            match = PS2_FILE.match(name)
            if not match:
                stats['armsx2_skipped_files'] += 1
                continue
            serial, crc = match.groups()
            text = archive.read(name).decode('utf-8', errors='replace')
            title, _, groups = parse_pnach(text)
            if serial is None:
                # PCSX2 falls back to CRC.pnach only without SERIAL_CRC.pnach.
                found = PS2_SERIAL.search(title)
                serial = found and f'{found.group(1)}-{found.group(2)}{found.group(3)}'
                if not serial or f'{serial}_{crc}.pnach' in names:
                    stats['armsx2_skipped_files'] += 1
                    continue
            game = games.setdefault((serial, crc), {'title': title, 'groups': [], 'extra': []})
            for group in groups:
                if group['name'] and group['patches']:
                    game['groups'].append((group, 'armsx2-patches-zip'))

    for source_id, pattern, label in PS2_EXTRA:
        root = roots[source_id]
        for path in sorted(root.glob(pattern)):
            match = PS2_ANY_FILE.match(path.name)
            if match is None or path.stat().st_size > 512 * 1024:
                stats['armsx2_skipped_files'] += 1
                continue
            key = (match.group(1), match.group(2).upper())
            title, _, groups = parse_pnach(path.read_bytes().decode('utf-8', errors='replace'))
            game = games.setdefault(key, {'title': title, 'groups': [], 'extra': []})
            game['title'] = game['title'] or title
            taken = {g['name'].casefold() for g, _ in game['groups']}
            codes = {tuple(g['code']) for g, _ in game['groups']}
            added = []
            for group in groups:
                if not group['name'] or not group['patches']:
                    continue
                if tuple(group['code']) in codes:
                    stats['armsx2_duplicate_groups'] += 1  # the engine already ships it
                    continue
                name = group['name']
                if name.casefold() in taken:
                    name = f'{name} ({label})'
                    if name.casefold() in taken:
                        stats['armsx2_duplicate_groups'] += 1
                        continue
                renamed = dict(group, name=name, kind='cheat')
                if name != group['name']:
                    renamed['variant_of'] = group['name']
                taken.add(name.casefold())
                codes.add(tuple(group['code']))
                game['groups'].append((renamed, source_id))
                added.append(renamed)
            if added:
                game['extra'].append((source_id, path.relative_to(root).as_posix(), added))

    for source_id, pattern, label in PS2_ORIGIN:
        root = roots[source_id]
        for path in sorted(root.glob(pattern)):
            match = PS2_ANY_FILE.match(path.name)
            crc_only = PS2_CRC_FILE.match(path.name)
            if (match is None and crc_only is None) or path.stat().st_size > 512 * 1024:
                stats['armsx2_skipped_files'] += 1
                continue
            raw = path.read_bytes()
            try:
                title = parse_pnach(raw.decode('utf-8'))[0]
            except UnicodeDecodeError:
                stats['armsx2_origin_not_utf8'] += 1
                continue
            if match is not None:
                key = (match.group(1), match.group(2).upper())
            else:
                # A file named by its CRC alone: the serial is the one its gametitle line gives.
                found = PS2_SERIAL.search(title)
                if not found:
                    stats['armsx2_skipped_files'] += 1
                    continue
                key = (f'{found.group(1)}-{found.group(2)}{found.group(3)}', crc_only.group(1).upper())
            game = games.setdefault(key, {'title': title, 'groups': [], 'extra': []})
            game['title'] = game['title'] or title
            taken = {g['name'].casefold() for g, _ in game['groups']}
            codes = {tuple(g['code']) for g, _ in game['groups']}
            added = []
            for header, start, end in pnach_blocks(raw):
                body = origin_body(raw, start, end)
                try:
                    name = header.decode('utf-8')
                except UnicodeDecodeError:
                    body = None
                parsed = parse_pnach(f'[{name}]\n{body}\n')[2] if body else []
                # One group exactly, read the same way from the range as from the whole file.
                if len(parsed) != 1 or parsed[0]['name'] != name or not parsed[0]['patches'] or \
                        '\n' in name or len(name) > 120:
                    stats['armsx2_origin_rejected_groups'] += 1
                    continue
                group = parsed[0]
                if tuple(group['code']) in codes:
                    stats['armsx2_duplicate_groups'] += 1  # the engine or an earlier source has it
                    continue
                shown = name
                if shown.casefold() in taken:
                    shown = f'{name} ({label})'
                    if shown.casefold() in taken:
                        stats['armsx2_duplicate_groups'] += 1
                        continue
                # The description routes the entry to its tab; like the lines, it is not published.
                renamed = dict(group, name=shown, kind='cheat', unhosted=True, range=(start, end), body=body)
                if shown != name:
                    renamed['variant_of'] = name
                taken.add(shown.casefold())
                codes.add(tuple(group['code']))
                game['groups'].append((renamed, source_id))
                added.append(renamed)
            if added:
                game.setdefault('origin', []).append(
                    (source_id, path.relative_to(root).as_posix(), len(raw), hashlib.sha256(raw).hexdigest(), added))

    serials = {}
    for (serial, crc), game in sorted(games.items()):
        if not game['groups']:
            continue
        record = serials.setdefault(serial, {'title': '', 'files': {}, 'entries': []})
        # gametitle often carries the serial, CRC and version: keep the name.
        name = re.split(r'\s*[(\[]?\b[A-Z]{4}[-_ ]?[0-9]{3}\.?[0-9]{2}', game['title'])[0]
        record['title'] = record['title'] or clean_label(name.strip(' -/'), 120)
        if game['extra'] or game.get('origin'):
            # `parts` alternates RewindBox's own text (and the licensed groups it may host) with
            # pointers [origin file, start, end] to the lines of a source it does not host.
            text = f'gametitle={game["title"]}\n'
            parts, literal = [], text
            for source_id, relative, groups in game['extra']:
                extra = SOURCES[source_id]
                piece = (f'\n// --- {extra["name"]}, {extra["url"]} @ {extra["revision"][:12]}, {relative}\n'
                         + '\n'.join(licence_comment(roots[source_id])) + '\n')
                for group in groups:
                    piece += f'\n[{group["name"]}]\n' + '\n'.join(group['lines']) + '\n'
                text += piece
                literal += piece
            for source_id, relative, size, digest, groups in game.get('origin', []):
                extra = SOURCES[source_id]
                origins = record.setdefault('origin', [])
                origins.append({'source': source_id, 'path': relative, 'size': size, 'sha256': digest})
                piece = (f'\n// --- {extra["name"]}, {extra["url"]} @ {extra["revision"][:12]}, {relative}\n'
                         f'{ORIGIN_NOTICE}\n')
                text += piece
                literal += piece
                for group in groups:
                    header = f'\n[{group["name"]}]\n'
                    text += header + group['body'] + '\n'
                    parts += [literal + header, [len(origins) - 1, group['range'][0], group['range'][1]]]
                    literal = '\n'
            encoded = text.encode('utf-8')
            # The installed bytes are the UTF-8 text RewindBox writes.
            payload = {'name': f'{serial}_{crc}_rewindbox.pnach', 'size': len(encoded),
                       'sha256': hashlib.sha256(encoded).hexdigest()}
            if parts:
                payload['parts'] = parts + [literal]
            else:
                payload['text'] = text
            record['files'][crc] = payload
        for group, source_id in game['groups']:
            if len(group['name']) > 160:
                stats['armsx2_skipped_groups'] += 1
                continue
            cat = classify(group['name'] + ' ' + group['description'])
            cheat = group.get('kind') == 'cheat'
            # PCSX2 matches `Enable = <name>` to the group name exactly.
            record['entries'].append({
                'id': stable_id('armsx2', serial, crc, group['name'].casefold()),
                'cat': cat, 'name': group['name'], 'crc': crc,
                'kind': 'cheat' if cheat else 'patch',
                # Bodies and descriptions of the engine's patches stay in the engine.
                'description': clean_label(group['description'], 300) if cheat and not group.get('unhosted') else '',
                'author': clean_label(group['author'], 200), 'source': source_id,
                # A renamed variant replaces its namesake; ratio choices exclude each other.
                'group': display_group(crc, group['name'], cat)
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


# ---------------------------------------------------------------- Azahar (3DS)

# Azahar's Gateway interpreter (src/core/cheats/gateway_cheat.cpp at 2127.0-rc5, 6f293a24): a line is
# exactly "XXXXXXXX YYYYYYYY"; its type is the first hex digit, or the first two for D codes. Types the
# interpreter does not know (F, DE, DF) do nothing; a line of another length is skipped with an error.
# Applications (00040000) and demos (00040002) run under their own Title ID. A file named after an update
# (0004000E) holds codes for the updated game; Azahar loads them under the game's own Title ID.
AZAHAR_TITLE = re.compile(r'^0004000[02E][0-9A-F]{8}$')
AZAHAR_LINE = re.compile(r'^[0-9A-F]{8} [0-9A-F]{8}$')
AZAHAR_TYPES = set(range(0x0, 0x0D)) | set(range(0xD0, 0xDE)) | {0xE}
# Pad bits the Joker code (DD) can see: hid:USER's PadState (A..GPIO14, circle pad). ZL, ZR, the C-stick
# and touch never reach it, so a combo that needs them never fires.
AZAHAR_PAD = {0: 'A', 1: 'B', 2: 'Select', 3: 'Start', 4: 'Right', 5: 'Left', 6: 'Up', 7: 'Down', 8: 'R',
              9: 'L', 10: 'X', 11: 'Y', 28: 'Circle Right', 29: 'Circle Left', 30: 'Circle Up', 31: 'Circle Down'}
AZAHAR_PAD_MASK = 0x00003FFF | 0xF0000000
# A game version in a cheat's name (`v1.5`, `Game v1.0`, `ver. 1.1`): cheats are version-specific.
AZAHAR_VERSION = re.compile(r'(?i)(?<![\w.])v(?:er(?:sion)?\.?\s*)?(\d+\.\d+(?:\.\d+)?)(?![\w.])')
AZAHAR_BASE_VERSIONS = {'1.0', '1.00', '1.0.0'}


def azahar_lines(lines):
    """The code lines as Azahar runs them, or None when the interpreter would skip a line, not know its
    type, or read past the end of the code (an E patch whose data lines are missing: an out-of-range
    read in PatchOp)."""
    out = [line.upper() for line in lines]
    index = 0
    while index < len(out):
        line = out[index]
        if not AZAHAR_LINE.match(line):
            return None
        kind = int(line[:2], 16) if line[0] == 'D' else int(line[0], 16)
        if kind not in AZAHAR_TYPES:
            return None
        if kind == 0xE:
            # PatchOp copies its data from the next ceil(Y / 8) lines, which are data, not codes.
            count = -(-int(line[9:], 16) // 8)
            if index + count >= len(out) or not all(AZAHAR_LINE.match(data) for data in out[index + 1:index + 1 + count]):
                return None
            index += count
        index += 1
    return out


def azahar_combo(lines):
    """Buttons of the Joker codes (DD000000 XXXXXXXX) a cheat waits for, in pad order; None when one needs a
    button Azahar never reports to the cheat engine."""
    combos = []
    for line in lines:
        if not line.startswith('DD000000 '):
            continue
        mask = int(line[9:], 16)
        if mask & ~AZAHAR_PAD_MASK:
            return None
        keys = [name for bit, name in sorted(AZAHAR_PAD.items()) if mask >> bit & 1]
        if keys and keys not in combos:
            combos.append(keys)
    return combos


def azahar_sections(text):
    """Sections of a Gateway cheat file, parsed like GatewayCheat::LoadFile: `[name]`, `*` comments,
    code lines; lines before the first section are ignored."""
    sections, current = [], None
    for raw in text.replace('\r', '').split('\n'):
        line = raw.replace('\0', '').strip()
        if len(line) >= 2 and line[0] == '[':
            current = {'name': line[1:-1] if line.endswith(']') else '', 'header': line, 'lines': [], 'notes': []}
            sections.append(current)
        elif current is None or not line:
            continue
        elif line[0] == '*':
            current['notes'].append(line[1:].strip())
        else:
            current['lines'].append(line)
    return sections


def azahar_label(name, suffix, labels):
    """A label no other code of the title has (case-insensitive), at most 120 characters; added to labels."""
    base = f'{name[:120 - len(suffix) - 1].rstrip()} {suffix}' if suffix else name
    label, number = base, 1
    while label.casefold() in labels:
        number += 1
        tail = f' ({number})'
        label = f'{base[:120 - len(tail)].rstrip()}{tail}'
    labels.add(label.casefold())
    return label


def build_azahar(root, stats):
    """Sharkive's 3DS files (3ds/<Title ID>.txt), hosted: per title, each cheat's name, category, the game
    versions its name states, the button combo it waits for, and its code lines checked against Azahar's
    interpreter. The adapter writes the chosen ones, each marked `*citra_enabled`, to cheats/<Title ID>.txt."""
    records = {}
    for path in sorted((root / '3ds').glob('*.txt')):
        tid = path.stem.upper()
        if not AZAHAR_TITLE.match(tid):
            stats['azahar_rejected_titles'] += 1
            continue
        update = tid.startswith('0004000E')
        if update:
            tid = '00040000' + tid[8:]
            stats['azahar_update_files'] += 1
        raw = path.read_bytes()
        try:
            text = raw.decode('utf-8')
        except UnicodeDecodeError:
            text = raw.decode('latin-1')
            stats['azahar_latin1_files'] += 1
        record = records.setdefault(tid, {'title': '', 'credits': ['FlagBrew Sharkive contributors (GPL-3.0)'],
                                          'entries': []})
        entries = record['entries']
        labels = {e['name'].casefold() for e in entries}
        names = collections.Counter()
        for section in azahar_sections(text):
            full = clean_label(section['name'], 400)
            name = full[:120].rstrip()
            if not name or not section['header'].endswith(']'):
                stats['azahar_rejected_unnamed'] += 1
                continue
            if not section['lines']:
                stats['azahar_rejected_empty'] += 1
                continue
            lines = azahar_lines(section['lines'])
            if lines is None:
                stats['azahar_rejected_lines'] += 1
                continue
            combo = azahar_combo(lines)
            if combo is None:
                stats['azahar_rejected_unreported_buttons'] += 1
                continue
            names[name.casefold()] += 1
            occurrence = names[name.casefold()]
            # Every code of a title keeps a name of its own: a code of the update's file whose name the game's
            # file already uses says so, and a repeated name is numbered.
            label = azahar_label(name, '(update)' if update and name.casefold() in labels else '', labels)
            identity = ('azahar', tid, name.casefold(), str(occurrence)) if not update else \
                ('azahar', tid, 'update', name.casefold(), str(occurrence))
            entry = {'id': stable_id(*identity), 'cat': classify(name, 'cheat'),
                     'name': label, 'source': 'sharkive-3ds', 'lines': lines}
            if update:
                entry['update'] = True
            versions = sorted({v for v in AZAHAR_VERSION.findall(name)}, key=lambda v: [int(x) for x in v.split('.')])
            if versions:
                entry['versions'] = versions
            if combo:
                entry['combo'] = combo
            # A name cut to fit the list keeps its whole text as the code's description.
            notes = clean_label(' '.join([full] * (full != name) + [note for note in section['notes'] if note]), 400)
            if notes:
                entry['notes'] = notes
            group = display_group(tid, name, entry['cat'])
            if group:
                entry['group'] = group
            entries.append(entry)
            stats['azahar_entries'] += 1
    for tid in list(records):
        if not records[tid]['entries']:
            stats['azahar_titles_without_entries'] += 1
            del records[tid]
            continue
        records[tid]['entries'].sort(key=lambda e: (e['cat'], e['name'].casefold()))
    return records


# ---------------------------------------------------------------- output

def pack_json(payload):
    """(gzip bytes, expanded size) of one catalogue file; the same input gives the same bytes."""
    data = json.dumps(payload, ensure_ascii=False, separators=(',', ':'), sort_keys=True).encode()
    return gzip.compress(data, compresslevel=9, mtime=0), len(data)


def counts(entries):
    result = {}
    for entry in entries:
        result[entry['cat']] = result.get(entry['cat'], 0) + 1
    return result


def published():
    """The newest published index (the one bundled in the app) and the local folder its
    `base_url` names."""
    path = BUNDLED_INDEX
    if not path.exists():
        return None, None
    index = json.loads(gzip.decompress(path.read_bytes()))
    base = index.get('base_url', '')
    if not base.startswith(BASE_URL):
        raise SystemExit(f'published index: base_url {base} is not below {BASE_URL}')
    return index, OUTPUT / base[len(BASE_URL):]


def published_shards(index, folder):
    """{shard: packed bytes} of the published index, each checked against it."""
    shards = {}
    for name, meta in index['shards'].items():
        data = (folder / meta['path']).read_bytes()
        if len(data) != meta['size'] or hashlib.sha256(data).hexdigest() != meta['sha256']:
            raise SystemExit(f'published shard {name} does not match its index')
        shards[name] = data
    return shards


# Entry IDs a new revision may drop, per engine: {engine: {id: reason}}. A player's state names entries by ID:
# an ID that disappears leaves an active code on the player's files that the page no longer shows. Empty:
# no publication has dropped one (test/enhancement_catalog_data_test.py checks the previous revision).
ID_REMOVAL_ALLOWLIST = {}


def catalogue_drift(previous_shards, engines, moved):
    """Per engine, what this revision changes against the published one: entry IDs removed and added, keys
    removed and added, and keys moved into another (an update's Title ID folded into its application's)."""
    previous = collections.defaultdict(dict)
    for data in previous_shards.values():
        shard = json.loads(gzip.decompress(data))
        previous[shard['engine']].update(shard['keys'])
    report = {}
    for engine, records in engines.items():
        old = previous.get(engine, {})
        old_ids = {entry['id'] for record in old.values() for entry in record['entries']}
        new_ids = {entry['id'] for record in records.values() for entry in record['entries']}
        added = sorted(new_ids - old_ids)
        report[engine] = {
            'ids_removed': sorted(old_ids - new_ids), 'ids_added': len(added), 'ids_added_first': added[:200],
            'keys_removed': sorted(set(old) - set(records)), 'keys_added': sorted(set(records) - set(old)),
            'keys_moved': {key: target for key, target in sorted(moved.items()) if engine == 'melonx'},
        }
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--revision', default='')
    parser.add_argument('--reuse-engines', default='',
                        help='engines (comma separated) whose published records are kept as they are')
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    reuse = {engine for engine in args.reuse_engines.split(',') if engine}
    unknown = reuse - set(ENGINES)
    if unknown:
        raise SystemExit(f'--reuse-engines: unknown engine {sorted(unknown)}')
    previous, previous_folder = published()
    previous_shards = published_shards(previous, previous_folder) if previous else {}
    if reuse and not previous:
        raise SystemExit('--reuse-engines needs a published catalogue')
    stats = collections.defaultdict(int)
    # A reused engine's sources are not fetched: its records come from the published shards.
    needed = {source_id for source_id, source in SOURCES.items()
              if 'git' in source and (set(source['engines']) - reuse or source.get('merge'))}
    git = {source_id: fetch_git(args.cache, source_id, args.offline) for source_id in sorted(needed)}
    engines = {}
    for engine in ENGINES:
        if engine in reuse:
            records = {}
            for name, data in previous_shards.items():
                if name.startswith(engine + '-'):
                    records.update(json.loads(gzip.decompress(data))['keys'])
            if engine == 'melonx':
                finish_melonx(records, None, stats)
            engines[engine] = records
        elif engine == 'melonx':
            engines[engine] = build_melonx(git['switch-cheats-db'],
                                           fetch_git(args.cache, 'gbatemp-matias3ds', args.offline), stats,
                                           exefs=[(git[source_id], source_id) for source_id in
                                                  ('keatonthebot-pchtxt', 'stevensnd-port-mods', 'stevensnd-ue4-mods')], archives=git['fl4sh-zip'])
        elif engine == 'rpcs3':
            engines[engine] = build_rpcs3(fetch_rpcs3(args.cache, args.offline), stats)
        elif engine == 'armsx2':
            engines[engine] = build_armsx2(git, stats)
        elif engine == 'azahar':
            engines[engine] = build_azahar(git['sharkive-3ds'], stats)
        else:
            engines[engine] = build_dolphin(git, stats)
        if engine == 'rpcs3':
            merge_rpcs3_artemis(engines[engine], [(git[s], s) for s in ARTEMIS_SOURCES], stats)
    flags = {engine: finish_flags(engine, records) for engine, records in engines.items()}
    for record in engines['melonx'].values():
        assert not any(key.startswith('_') for entry in record['entries'] for key in entry), 'a code leaked'
    # An entry ID a player may have turned on is never dropped silently (docs/ENHANCEMENTS.md, Publication).
    drift = catalogue_drift(previous_shards, engines, stats.pop('melonx_keys_moved', {}))
    lost = {engine: [i for i in report['ids_removed'] if i not in ID_REMOVAL_ALLOWLIST.get(engine, {})]
            for engine, report in drift.items()}
    if any(lost.values()):
        raise SystemExit('entry IDs of the published revision would disappear: '
                         + json.dumps({engine: ids for engine, ids in lost.items() if ids}) +
                         '; keep them, or list each in ID_REMOVAL_ALLOWLIST with its reason')
    index_engines, shard_meta, shard_bytes, totals = {}, {}, {}, {}
    for engine, records in engines.items():
        grouped = {}
        keys = {}
        for key in sorted(records):
            shard = shard_of(engine, key)
            grouped.setdefault(shard, {})[key] = records[key]
            keys[key] = [records[key]['title'], counts(records[key]['entries']), shard]
        for shard, members in sorted(grouped.items()):
            packed, expanded = pack_json({'schema': 1, 'engine': engine, 'shard': shard, 'keys': members})
            # gzip headers can vary between Python versions. Preserve verified bytes and device caches.
            old = previous_shards.get(shard)
            if old and old != packed and gzip.decompress(old) == gzip.decompress(packed):
                packed = old
            shard_bytes[shard] = packed
            shard_meta[shard] = {'path': f'shards/{shard}.json.gz', 'size': len(packed), 'expanded': expanded,
                                 'sha256': hashlib.sha256(packed).hexdigest()}
        index_engines[engine] = {'keys': keys}
        engine_totals = {}
        for record in records.values():
            for cat, n in counts(record['entries']).items():
                engine_totals[cat] = engine_totals.get(cat, 0) + n
        totals[engine] = {'keys': len(records), 'entries': engine_totals}
    changed = sorted(shard for shard, data in shard_bytes.items() if previous_shards.get(shard) != data)
    removed = sorted(set(previous_shards) - set(shard_bytes))
    sources = [{'id': k, **{f: v[f] for f in ('name', 'url', 'license', 'engines')},
                **({'origin': v['origin']} if 'origin' in v else {}),
                'revision': v.get('revision') or v.get('sha256')} for k, v in SOURCES.items()]
    if previous and not changed and not removed and previous.get('sources') == sources:
        print(f'no shard or source changed: revision {previous["revision"]} stays published')
        return
    digest = hashlib.sha256(json.dumps([shard_meta, sources], sort_keys=True).encode()).hexdigest()
    # Apps keep the later string: the UTC date and time order two publications of one day.
    revision = args.revision or datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H%MZ') + '.' + digest[:12]
    if previous and revision <= previous['revision']:
        raise SystemExit(f'revision {revision} is not later than the published {previous["revision"]}: '
                         'apps keep the later string')
    folder = OUTPUT / 'r' / revision
    for shard, data in shard_bytes.items():
        target = folder / shard_meta[shard]['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    index = {
        'schema': 1, 'format': FORMAT, 'catalogue': 'rewindbox-enhancements', 'revision': revision,
        'base_url': f'{BASE_URL}r/{revision}/', 'sources': sources,
        'engines': index_engines, 'shards': shard_meta, 'totals': totals,
    }
    packed, _ = pack_json(index)
    # An app asks the folder of the index it holds: every earlier revision of this record format
    # gets the newest index. The frozen first publication and other formats are left alone.
    same_format = [path for path in sorted(OUTPUT.glob('r/*/index.json.gz'))
                   if json.loads(gzip.decompress(path.read_bytes())).get('format') == FORMAT]
    for target in [BUNDLED_INDEX, *same_format, folder / 'index.json.gz']:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(packed)
    rejections = dict(stats)
    validation = OUTPUT / 'VALIDATION.json'
    if reuse and validation.exists():
        # Counters of a reused engine are those of the run that built it.
        for key, value in json.loads(validation.read_text())['rejections'].items():
            if key.split('_')[0] in reuse:
                rejections[key] = value
    report = {'revision': revision, 'index_sha256': hashlib.sha256(packed).hexdigest(),
              'index_size': len(packed), 'totals': totals, 'rejections': rejections, 'flags': flags,
              'shard_bytes': sum(m['size'] for m in shard_meta.values()),
              'published': {'previous': previous['revision'] if previous else None, 'reused_engines': sorted(reuse),
                            'changed_shards': changed, 'removed_shards': removed,
                            'changed_bytes': sum(len(shard_bytes[shard]) for shard in changed)},
              # Against the previous revision: IDs and keys removed, added or moved, per engine.
              'drift': {'against': previous['revision'] if previous else None, 'engines': drift}}
    validation.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'rejections'}, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
