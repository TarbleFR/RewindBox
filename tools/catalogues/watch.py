#!/usr/bin/env python3
"""Which pinned sources of the catalogues moved upstream, without downloading them.

RewindBox's catalogues (cheats, enhancements, HD textures, shaders) are built
from sources pinned to a revision. This tool lists every pin and asks each
upstream, cheaply, whether it moved:

  - a git source: one `git ls-remote <url> HEAD` (the advertised head only;
    nothing is cloned);
  - an HTTP source: one conditional request (If-None-Match / If-Modified-Since
    with the validators kept from the last answer); "304 Not Modified" costs
    no body.

Answers are kept in a cache file. A source asked less than --max-age hours
ago is not asked again, and two requests to one host are at least --pace
seconds apart, so a scheduled or repeated run stays far below the providers'
limits. A host that refuses (401, 403, 429, 5xx) is reported "refused" and is
not asked again in this run.

  python3 tools/catalogues/watch.py                     every pin and its state
  python3 tools/catalogues/watch.py --only shaders      one catalogue
  python3 tools/catalogues/watch.py --delta             also what changed between the pin and the
                                                         head of each moved git source: file names
                                                         only (a blobless fetch of the two commits)
  python3 tools/catalogues/watch.py --offline           the cached answers, no request

States: current, moved (the head is another revision: a refresh may be worth
it), engine (pinned to the embedded engine: it moves only with the engine),
refused, unreachable, unchecked (offline and never asked).

This tool changes no catalogue. A moved source is refreshed by its own
builder, which reviews and pins the new input:

  cheats        tools/cheats/unified_catalogue.py (see native/cheats/catalogue/README.md)
  enhancements  tools/enhancements/build_enhancement_catalog.py (--reuse-engines keeps the
                engines whose pins did not move)
  textures      tools/textures/import_ps2ktxpak.py (three-way merge), tools/textures/discover.py links
  shaders       tools/shaders/build_slang_catalog.py
"""
import argparse
import ast
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CACHE = ROOT / 'build/catalogue-watch/cache.json'
USER_AGENT = 'RewindBox-catalogue-watch/1.0'
COMMIT = re.compile(r'^[0-9a-f]{40}$')
GITHUB = re.compile(r'^https://github\.com/([^/]+/[^/#?]+?)(?:\.git)?(?:[/#?].*)?$')


def assignments(path, names):
    """Literal top-level assignments of a Python file, read without running it."""
    found = {}
    tree = ast.parse(path.read_text(encoding='utf-8'))
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) \
                and node.targets[0].id in names:
            try:
                found[node.targets[0].id] = ast.literal_eval(node.value)
            except ValueError:
                pass  # built from other names (an f-string): not a pin by itself
    return found


def github_url(url):
    match = GITHUB.match(url or '')
    return f'https://github.com/{match.group(1)}' if match else None


def pins():
    """Every pinned upstream: {catalogue, id, name, kind, url, pinned, note}."""
    out = []

    def add(catalogue, identifier, name, url, pinned, kind='git', note=''):
        out.append({'catalogue': catalogue, 'id': identifier, 'name': name, 'kind': kind, 'url': url,
                    'pinned': pinned, 'note': note})

    # Enhancements: the builder's own table.
    enhancements = assignments(ROOT / 'tools/enhancements/build_enhancement_catalog.py', {'SOURCES', 'RESTRICTION_INPUTS'})
    engine_pinned = {'armsx2-patches-zip': 'ARMSX2 engine', 'dolphin-gamesettings': 'Dolphin engine'}
    for identifier, source in {**enhancements.get('SOURCES', {}), **enhancements.get('RESTRICTION_INPUTS', {})}.items():
        if 'git' in source:
            add('enhancements', identifier, source.get('name', identifier), source['git'].removesuffix('.git'),
                source['revision'], 'engine' if identifier in engine_pinned else 'git', engine_pinned.get(identifier, ''))
        elif 'download' in source:
            add('enhancements', identifier, source['name'], source['download'], 'sha256:' + source['sha256'], 'http')

    # Shaders: the pinned repositories of the two catalogue builders.
    slang = assignments(ROOT / 'tools/shaders/build_slang_catalog.py',
                        {'SLANG_REPOSITORY', 'SLANG_COMMIT', 'PREVIEWS_REPOSITORY', 'PREVIEWS_COMMIT'})
    if slang.get('SLANG_COMMIT'):
        add('shaders', 'slang-shaders', 'libretro/slang-shaders', slang['SLANG_REPOSITORY'], slang['SLANG_COMMIT'])
        add('shaders', 'shader-previews', 'libretro/shader-previews', slang['PREVIEWS_REPOSITORY'], slang['PREVIEWS_COMMIT'])
    for name in ('slang-catalog.json', 'dolphin-catalog.json'):
        path = ROOT / 'packages/neo_shader_kit/ios/Resources' / name
        if not path.exists():
            continue
        catalog = json.loads(path.read_text(encoding='utf-8'))
        for source in [catalog.get('source') or {}] + [layer.get('source') or {} for layer in catalog.get('additions') or []]:
            repository, commit = source.get('repository'), source.get('commit')
            if not repository or not commit or any(pin['url'] == repository and pin['pinned'] == commit for pin in out):
                continue
            engine = catalog.get('engine') == 'dolphin'
            add('shaders', f'{name}:{commit[:8]}', source.get('name', repository), repository, commit,
                'engine' if engine else 'git', 'Dolphin engine (Sys/Shaders ship with it)' if engine else '')

    # HD textures: the imported PS2 catalogue and the game database its serials are checked against.
    report = ROOT / 'tools/textures/ps2ktxpak-report.json'
    if report.exists():
        data = json.loads(report.read_text(encoding='utf-8'))
        add('textures', 'ps2ktxpak', 'ps2ktxpak/catalog (PS2 texture pack records, MIT)', data['catalog'], data['commit'])
        add('textures', 'pcsx2-gameindex', 'PCSX2 GameIndex.yaml (serials and titles)', 'https://github.com/PCSX2/pcsx2',
            data['gameindex_commit'], note='only bin/resources/GameIndex.yaml is read')

    # Unified cheats: the builder's lock, then the origin table (what the app downloads).
    seen = set()
    lock = json.loads((ROOT / 'tools/cheats/unified-sources.json').read_text(encoding='utf-8'))
    for source in lock['sources']:
        url, revision = github_url(source.get('url')), source.get('revision') or ''
        status = source.get('status', '')
        note = '' if status == 'available' else f'not published ({status})' if status else ''
        if url and COMMIT.match(revision) and (url, revision) not in seen:
            seen.add((url, revision))
            add('cheats', source['id'], source.get('name', source['id']), url, revision, note=note)
        elif re.match(r'^[0-9a-f]{64}$', revision) and str(source.get('download_url', '')).startswith('https://'):
            # One file pinned by its SHA-256 (cheat.db, cheats.bml...): asked with its validators.
            add('cheats', source['id'], source.get('name', source['id']), source['download_url'], 'sha256:' + revision,
                'http', note)
    for identifier, repository, commit in origin_pins(ROOT / 'tools/cheats/origin/sources.py'):
        if (f'https://github.com/{repository}', commit) not in seen:
            seen.add((f'https://github.com/{repository}', commit))
            add('cheats', identifier + ':origin', identifier + ' (origin download)', f'https://github.com/{repository}', commit)
    return out


def origin_pins(path):
    """(source, repository, commit) of the github(...) entries of the origin table, read without running it."""
    tree = ast.parse(path.read_text(encoding='utf-8'))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'ORIGINS' for target in node.targets) \
                and isinstance(node.value, ast.Dict):
            for key, value in zip(node.value.keys, node.value.values):
                if isinstance(key, ast.Constant) and isinstance(value, ast.Call) and getattr(value.func, 'id', '') == 'github' \
                        and len(value.args) >= 2 and all(isinstance(argument, ast.Constant) for argument in value.args[:2]):
                    yield key.value, value.args[0].value, value.args[1].value


class Asker:
    def __init__(self, cache_path, max_age, pace, offline):
        self.path, self.max_age, self.pace, self.offline = cache_path, max_age * 3600, pace, offline
        self.cache = json.loads(cache_path.read_text(encoding='utf-8')) if cache_path.exists() else {}
        self.last, self.refused, self.requests = {}, set(), 0

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.cache, indent=1, sort_keys=True) + '\n', encoding='utf-8')
        os.replace(temporary, self.path)

    def wait(self, host):
        delay = self.last.get(host, 0) + self.pace - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        self.last[host] = time.monotonic()
        self.requests += 1

    def fresh(self, key):
        entry = self.cache.get(key)
        return entry if entry and time.time() - entry.get('checked', 0) < self.max_age else None

    def git_head(self, url):
        """The commit `url` advertises as HEAD: {'head'} or {'error', 'state'}."""
        key = 'git ' + url
        entry = self.fresh(key)
        if entry or self.offline:
            return dict(self.cache.get(key) or {'state': 'unchecked'}, cached=True)
        host = urllib.parse.urlsplit(url).hostname or ''
        if host in self.refused:
            return {'state': 'refused', 'error': 'host refused an earlier request of this run'}
        self.wait(host)
        try:
            result = subprocess.run(['git', 'ls-remote', url, 'HEAD'], capture_output=True, text=True, timeout=60,
                                    env={**os.environ, 'GIT_TERMINAL_PROMPT': '0'})
        except subprocess.TimeoutExpired:
            return {'state': 'unreachable', 'error': 'timeout'}
        match = re.match(r'^([0-9a-f]{40})\s+HEAD', result.stdout)
        if result.returncode != 0 or not match:
            error = (result.stderr.strip().splitlines() or ['no HEAD advertised'])[-1][:200]
            refused = bool(re.search(r'\b(401|403|429)\b|rate limit|denied', error, re.I))
            if refused:
                self.refused.add(host)
            return {'state': 'refused' if refused else 'unreachable', 'error': error}
        self.cache[key] = {'head': match.group(1), 'checked': int(time.time())}
        return dict(self.cache[key])

    def http_state(self, url):
        """Whether an HTTP source changed since the validators kept from its last answer."""
        key = 'http ' + url
        entry = self.fresh(key)
        if entry or self.offline:
            return dict(self.cache.get(key) or {'state': 'unchecked'}, cached=True)
        host = urllib.parse.urlsplit(url).hostname or ''
        if host in self.refused:
            return {'state': 'refused', 'error': 'host refused an earlier request of this run'}
        previous = self.cache.get(key) or {}
        headers = {'User-Agent': USER_AGENT}
        if previous.get('etag'):
            headers['If-None-Match'] = previous['etag']
        if previous.get('last_modified'):
            headers['If-Modified-Since'] = previous['last_modified']
        self.wait(host)
        request = urllib.request.Request(url, headers=headers, method='HEAD')
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                validators = {'etag': response.headers.get('ETag') or '', 'last_modified': response.headers.get('Last-Modified') or '',
                              'length': response.headers.get('Content-Length') or ''}
        except urllib.error.HTTPError as error:
            if error.code == 304:
                self.cache[key] = dict(previous, checked=int(time.time()), changed=False)
                return dict(self.cache[key])
            if error.code in (401, 403, 429) or error.code >= 500:
                self.refused.add(host)
                return {'state': 'refused', 'error': f'HTTP {error.code}'}
            return {'state': 'unreachable', 'error': f'HTTP {error.code}'}
        except (urllib.error.URLError, OSError, ValueError) as error:
            return {'state': 'unreachable', 'error': str(getattr(error, 'reason', error))[:200]}
        known = {field: previous.get(field) for field in ('etag', 'last_modified', 'length')}
        comparable = any(validators.values()) and any(known.values())
        self.cache[key] = dict(validators, checked=int(time.time()),
                               changed=comparable and validators != known if comparable else None)
        return dict(self.cache[key])


def delta(pin, head, work):
    """File names that differ between the pinned commit and the head (no file content is fetched)."""
    repository = work / re.sub(r'[^A-Za-z0-9_.-]+', '_', pin['url'].split('github.com/')[-1])
    if not (repository / 'HEAD').exists():
        repository.mkdir(parents=True, exist_ok=True)
        subprocess.run(['git', 'init', '-q', '--bare', str(repository)], check=True)
        subprocess.run(['git', '-C', str(repository), 'remote', 'add', 'origin', pin['url']], check=True)
    fetch = subprocess.run(['git', '-C', str(repository), 'fetch', '-q', '--filter=blob:none', '--depth', '1', 'origin',
                            pin['pinned'], head], capture_output=True, text=True, timeout=900)
    if fetch.returncode != 0:
        return {'error': (fetch.stderr.strip().splitlines() or ['fetch failed'])[-1][:200]}
    names = subprocess.run(['git', '-C', str(repository), 'diff', '--name-status', '--no-renames', pin['pinned'], head],
                           capture_output=True, text=True, timeout=900)
    if names.returncode != 0:
        return {'error': (names.stderr.strip().splitlines() or ['diff failed'])[-1][:200]}
    status, folders = Counter(), Counter()
    for line in names.stdout.splitlines():
        kind, _, path = line.partition('\t')
        status[{'A': 'added', 'D': 'deleted', 'M': 'modified'}.get(kind[:1], 'other')] += 1
        folders[path.split('/')[0] if '/' in path else '.'] += 1
    return {'files': dict(status), 'folders': dict(folders.most_common(8))}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--only', default='', help='catalogues to list, comma separated: cheats,enhancements,textures,shaders')
    parser.add_argument('--cache', type=Path, default=DEFAULT_CACHE)
    parser.add_argument('--max-age', type=float, default=20, help='hours an answer is kept before the source is asked again')
    parser.add_argument('--pace', type=float, default=1.0, help='seconds between two requests to one host')
    parser.add_argument('--offline', action='store_true', help='no request: the cached answers only')
    parser.add_argument('--delta', action='store_true', help='for each moved git source, the file names that changed')
    parser.add_argument('--out', type=Path, help='also write the report as JSON')
    args = parser.parse_args()
    wanted = {name for name in args.only.split(',') if name}
    asker = Asker(args.cache, args.max_age, args.pace, args.offline)
    rows = []
    for pin in pins():
        if wanted and pin['catalogue'] not in wanted:
            continue
        row = dict(pin)
        if pin['kind'] == 'http':
            answer = asker.http_state(pin['url'])
            row['state'] = answer.get('state') or ('moved' if answer.get('changed') else 'current' if answer.get('changed') is False
                                                   else 'unchecked')
            if answer.get('changed') is None and not answer.get('state'):
                row['note'] = 'first answer kept: a change shows from the next run'
        else:
            answer = asker.git_head(pin['url'])
            row['head'] = answer.get('head')
            if answer.get('head'):
                row['state'] = 'current' if answer['head'] == pin['pinned'] else 'engine' if pin['kind'] == 'engine' else 'moved'
            else:
                row['state'] = answer.get('state', 'unreachable')
            if args.delta and row['state'] == 'moved' and not args.offline:
                row['delta'] = delta(pin, answer['head'], args.cache.parent / 'git')
        if answer.get('error'):
            row['error'] = answer['error']
        row['cached'] = bool(answer.get('cached'))
        rows.append(row)
    if not args.offline:
        asker.save()
    width = max((len(row['id']) for row in rows), default=10)
    for row in rows:
        head = (row.get('head') or '')[:12]
        line = f"{row['catalogue']:<12} {row['id']:<{width}} {row['state']:<11} {str(row['pinned'])[:12]:<12} {head:<12} {row['url']}"
        extra = row.get('note') or row.get('error') or ''
        if row.get('delta'):
            extra = json.dumps(row['delta'], sort_keys=True)
        print(line + (f'  [{extra}]' if extra else ''))
    states = Counter(row['state'] for row in rows)
    print(f'WATCH_SUMMARY {len(rows)} pins: ' + ', '.join(f'{count} {state}' for state, count in sorted(states.items()))
          + f'; {asker.requests} requests')
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps({'checked_at': int(time.time()), 'summary': dict(states), 'pins': rows}, indent=1) + '\n',
                            encoding='utf-8')


if __name__ == '__main__':
    sys.exit(main())
