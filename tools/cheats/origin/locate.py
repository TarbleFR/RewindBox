#!/usr/bin/env python3
"""Finds every origin-only program of the unified catalogue in its source's
own file, and proves that recipe.rebuild gives back its exact code fields.

  python3 tools/cheats/origin/locate.py --origins <dir> [--sources a,b] [--out recipes.json.gz]

<dir>/<source id>/ holds each source's files at the pinned revision (the
layout of the source's repository). A program is "origin-only" when every
provenance of it is a source the catalogue does not host (decision register:
no licence, tooling licence or conditional permission). Nothing is written
outside --out; the report lists, per source, located and unlocated programs.
"""
import argparse
import base64
import html
import collections
import gzip
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import zipfile  # noqa: E402
from recipe import derive, fbneo, raw_text, rebuild_mister  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
DIRECTORY = ROOT / 'native/cheats/catalogue'
REGISTER = ROOT / 'docs/evidence/cheat-source-decision-register-2026-10-28.json'
ORIGIN_VERDICTS = {'no-licence-evidence', 'tooling-licence-only', 'conditional-permission'}
CODE_FIELDS = ('code', 'lines', 'source_code', 'choices', 'native_document')


def identities(game, scheme):
    return [i['value'] for i in game.get('identities', []) if i.get('scheme') == scheme]


class Source:
    """The pinned files of one source and the members a game may come from."""

    def __init__(self, root):
        self.root = root
        self._data = {}
        self.files = sorted(p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file())

    def member(self, path):
        if path not in self._data:
            data = (self.root / path).read_bytes()
            try:
                data.decode('utf-8')
                encoding = 'utf-8'
            except UnicodeDecodeError:
                encoding = 'cp1252'
            self._data[path] = (data, encoding)
        return self._data[path]

    def candidates(self, game, program):
        """Members named by the program (source_member) or by the source's rule."""
        member = program.get('source_member')
        if member:
            parts = member.split('/')
            return [m for m in ('/'.join(parts[i:]) for i in range(len(parts))) if m in self.names] or \
                [f for f in self.files if f.rsplit('/', 1)[-1] == parts[-1]]
        return self.rule(game, program)

    def rule(self, game, program):
        return self.files if len(self.files) <= 4 else []

    def recipe(self, game, program, raw, expected):
        """A recipe whose rebuild equals `expected`, from the rule's members
        first, then (small sources) from any member holding the first line."""
        tried = set()
        for paths in (lambda: self.candidates(game, program), lambda: self.search(raw, program)):
            for path in paths():
                if path in tried or not (self.root / path).is_file():
                    continue
                tried.add(path)
                for text in self.variants(raw, program):
                    found = self.check(path, locate(text, *self.member(path)), program, expected)
                    if found:
                        return found
        return None

    @staticmethod
    def variants(raw, program):
        """The text as published, then as importers that normalised it read it."""
        yield raw
        tokens = [t for t in re.split(r'[+;,\s]+', raw) if t]
        for text in (' '.join(tokens).lower(), ' '.join(tokens), '\n'.join(tokens).lower(), raw.lower(), '\n'.join(tokens)):
            if text != raw:
                yield text

    def search(self, raw, program):
        if len(self.files) > 6000:
            return []
        firsts = {next((p for p in text.split('\n') if p.strip()), '').split(' ')[0]
                  for text in self.variants(raw, program)} - {''}
        return [f for f in self.files
                if any(first.lower().encode(self.member(f)[1]) in self.member(f)[0].lower() for first in firsts)]

    def check(self, path, items, program, expected):
        if items is None:
            return None
        member = [self.member(path)]
        for plus in (False, True):
            for drop in (False, True):
                recipe = {'m': 0, 'r': items, **({'n': 'plus'} if plus else {}), **({'d': 1} if drop else {})}
                if derive(raw_text(recipe, member), program['dialect'], plus, drop=drop) == expected:
                    return {'p': path, **{k: v for k, v in recipe.items() if k != 'm'}}
        return None

    @property
    def names(self):
        if not hasattr(self, '_names'):
            self._names = set(self.files)
        return self._names


class Gecko(Source):
    def rule(self, game, program):
        return [f'codes/{g}.txt' for g in identities(game, 'dolphin-disc-game-id')]


class DuckStation(Source):
    def __init__(self, root):
        super().__init__(root)
        self.by_serial = collections.defaultdict(list)
        for path in self.files:
            match = re.match(r'cheats/([A-Z]{4}-\d{5})', path)
            if match and path.endswith('.cht'):
                self.by_serial[match[1]].append(path)

    def rule(self, game, program):
        return [p for s in identities(game, 'ps1-disc-serial') for p in self.by_serial.get(s, [])]


class MightyMo(Source):
    """Nestopia XML: <cheat> with <genie>, or <address>[<compare>]<value>;
    "(n of m)" parts join with "+" (unified_formats.parse_mighty_mo)."""

    TAG = re.compile(rb'<(genie|address|value|compare|description)>(.*?)</\1>', re.S)

    def rule(self, game, program):
        title = game['title']
        return [f for f in self.files if f.rsplit('/', 1)[-1] == title + '.xml']

    def recipe(self, game, program, raw, expected):
        for path in self.rule(game, program):
            data, encoding = self.member(path)
            parts = {}
            for block in re.finditer(rb'<cheat\b.*?</cheat>', data, re.S):
                fields = {m[1].decode(): (block.start() + m.start(2), block.start() + m.end(2))
                          for m in self.TAG.finditer(block[0])}
                description = html.unescape(data[slice(*fields['description'])].decode(encoding)).strip() \
                    if 'description' in fields else ''
                items = self.items(data, encoding, fields)
                if items is None:
                    continue
                part = re.fullmatch(r"(.+?)\s*\((\d+) of (\d+)\)", description)
                if part:
                    parts.setdefault((part[1], int(part[3])), {})[int(part[2])] = items
                    continue
                found = self.check(path, items, program, expected)
                if found and description == program['name']:
                    return found
            for (name, total), numbered in parts.items():
                if name != program['name']:
                    continue
                items = []
                for number in sorted(numbered):
                    items += (['+'] if items else []) + numbered[number]
                found = self.check(path, items, program, expected)
                if found:
                    return found
        return None

    @staticmethod
    def items(data, encoding, fields):
        def text(tag):
            return data[slice(*fields[tag])].decode(encoding).strip() if tag in fields else ''
        if text('genie'):
            return [list(fields['genie'])]
        if text('address') and text('value'):
            items = [[*fields['address'], 'x']]
            if text('compare'):
                items += ['?', [*fields['compare'], 'x']]
            return items + [':', [*fields['value'], 'x']]
        return None


class MiSTer(Source):
    """Cheats_MiSTer: one zip per game, one binary .gg program per member;
    the program's provenance names both (unified_adapt.parse_mister_adapted_zip)."""

    SYSTEMS = {"NES": "nes", "PSX": "psx", "GBA": "gba"}

    def archive(self, path):
        """Members of one game's zip, kept while that game's programs are read."""
        if getattr(self, '_archive', (None,))[0] != path:
            with zipfile.ZipFile(self.root / path) as bundle:
                self._archive = (path, {i.filename: bundle.read(i) for i in bundle.infolist() if not i.is_dir()})
        return self._archive[1]

    def recipe(self, game, program, raw, expected):
        for provenance in program.get('provenance', []):
            archive, member = provenance.get('archive_member'), provenance.get('program_member')
            if not archive or not member:
                continue
            path = archive.split('/', 1)[1]
            if not (self.root / path).is_file():
                continue
            system = next((v for k, v in self.SYSTEMS.items() if k in path.split('/')), None)
            data = self.archive(path).get(member)
            if data is None:
                continue
            for plus in (False, True):
                recipe = {'k': 'mister', 's': system, **({'n': 'plus'} if plus else {})}
                try:
                    if rebuild_mister(recipe, data, program['dialect']) == expected:
                        return {'p': path, 'z': member, **recipe}
                except ValueError:
                    break
        return None


class FBNeo(Source):
    """FBNeo-cheats: cheats/<driver>.ini, one `cheat` block per program."""

    def rule(self, game, program):
        return [f'cheats/{d}.ini' for d in identities(game, 'fbneo-driver-name')]

    def check(self, path, items, program, expected):
        if items is None:
            return None
        recipe = {'m': 0, 'r': items}
        try:
            if fbneo(raw_text(recipe, [self.member(path)])) == expected:
                return {'p': path, 'r': items, 'k': 'fbneo'}
        except ValueError:
            return None
        return None


class ByTitle(Source):
    """One file per game named after the title (Mighty Mo, weed-sheet)."""

    def rule(self, game, program):
        title = game['title']
        return [f for f in self.files if f.rsplit('/', 1)[-1] in (title, title + '.xml')]


SOURCES = {'geckoarchive': Gecko, 'duckstation': DuckStation, 'cwcheat': Source, 'lunamoo': Source,
           'psxdatacenter_v2_478': Source, 'shadow_pnach478': Source, 'pal_pnach478': Source,
           'yuki_pnach478': Source, 'weed_sheet': ByTitle, 'mighty_mo': MightyMo, 'dillonhafer_xml': Source,
           'delta_workbook': Source, 'mister': MiSTer, 'fbneo': FBNeo}


def locate(raw, data, encoding):
    """Recipe items for `raw` read line by line: each line is a byte range,
    found anywhere in the member, with "\n" between them; or None."""
    items, at = [], 0
    for index, piece in enumerate(raw.split('\n')):
        if index:
            items.append('\n')
        needle = piece.encode(encoding)
        start = data.find(needle, at)
        if start < 0:
            start = data.find(needle)
        if start < 0 and needle:
            # Hex written in mixed case by hand: the recipe keeps the bytes.
            match = re.search(re.escape(needle), data, re.I)
            start = match.start() if match else -1
        if start < 0:
            return None
        items.append([start, start + len(needle)])
        at = start + len(needle)
    return items


def programs(migrate):
    """(source, game, program) of every origin-only program."""
    manifest = json.loads(gzip.decompress((DIRECTORY / 'manifest.json.gz').read_bytes()))
    for pack in manifest['packs']:
        retired = {r['game_id'] for r in pack.get('retired', [])}
        body = json.loads(gzip.decompress((DIRECTORY / pack['path']).read_bytes()))
        for member in body['files']:
            if member['game_id'] in retired:
                continue
            chunk = json.loads(base64.b64decode(member['data']))
            for program in chunk['cheats']:
                ids = {p['source_id'] for p in program.get('provenance', [])}
                if ids and ids <= migrate:
                    yield min(ids), chunk['game'], program


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--origins', type=Path, required=True)
    parser.add_argument('--sources', default=','.join(SOURCES))
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    register = json.loads(REGISTER.read_text())
    migrate = {s['id'] for s in register['sources'] if s['verdict'] in ORIGIN_VERDICTS}
    wanted = set(args.sources.split(','))
    loaded = {sid: SOURCES[sid](args.origins / sid) for sid in wanted}
    report = collections.defaultdict(collections.Counter)
    recipes, failures = {}, collections.defaultdict(list)
    for source_id, game, program in programs(migrate):
        if source_id not in wanted:
            continue
        source = loaded[source_id]
        raw = program.get('source_code', program['code'])
        expected = {k: program[k] for k in CODE_FIELDS if k in program}
        found = source.recipe(game, program, raw, expected)
        if found:
            report[source_id]['located'] += 1
            recipes[f"{game['id']}/{program['id']}"] = found
        else:
            report[source_id]['unlocated'] += 1
            if len(failures[source_id]) < 5:
                failures[source_id].append({'game': game['title'], 'name': program['name'], 'raw': raw[:200],
                                            'candidates': source.candidates(game, program)[:3]})
    print(json.dumps({'report': report, 'failures': failures}, indent=1, ensure_ascii=False))
    if args.out:
        args.out.write_bytes(gzip.compress(json.dumps(recipes, sort_keys=True).encode(), mtime=0))


if __name__ == '__main__':
    main()
