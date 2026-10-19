#!/usr/bin/env python3
"""Finds HD texture pack candidates and checks the links of the catalogue.

This tool never writes tools/textures/sources: it produces candidates for a
human review. A candidate becomes a catalogue entry only after its page,
author, terms and game identities are reviewed and, for a one-tap pack, after
tools/textures/verify_packs.py installed the author's real file.

  discover.py github --out build/hdtex/candidates.jsonl
      Searches GitHub (repository search and topics, then code search for
      the files each engine reads: textures.ini, pack.json), and for every
      repository reads its file tree, its releases and its README. It reports
      the engine signals it found (tex1_ names, textures.ini, pack.json,
      PCSX2 replacements folders), the game identifiers written in folder
      names or in the README (PS2 serials, Dolphin Game IDs, PSP DISC_IDs,
      3DS Title IDs), the release files, Git LFS pointers and the licence
      GitHub detected, and whether the repository is already catalogued or
      was reviewed and left out.

  discover.py links --out build/hdtex/links.jsonl
      For every catalogued pack: whether its page and each download part are
      still reachable with the recorded size, and, for a GitHub source,
      whether a newer release than the catalogued version exists. Verdicts:
      ok, update, refused (the host refuses an automated check: 401, 403,
      429, 503; not a dead link) and broken. Each URL is asked once, a host
      at most once a second; LINKS_SUMMARY counts the verdicts.

  discover.py summarize --candidates build/hdtex/candidates.jsonl --out build/hdtex/summary.jsonl
      One short line per candidate whose files an engine reads (tex1_ names,
      textures.ini, pack.json, PCSX2 replacements) or that names a game
      identifier: the review list without unrelated texture packs.

Every mode prints one line per result between DISCOVER_BEGIN and
DISCOVER_END markers, so a CI log is enough to read them. The GitHub API is
read with GH_TOKEN or GITHUB_TOKEN when set (repository search is limited to
30 requests a minute, code search to 10).
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCES = HERE / 'sources'
API = 'https://api.github.com'

# Repository searches: an engine word with a texture word, the topics used
# by pack authors, and the words of the pack names seen in the catalogue.
REPOSITORY_QUERIES = [
    'texture pack pcsx2', 'texture pack ps2', 'hd textures pcsx2', 'pcsx2 textures', 'ps2 hd textures',
    'texture pack dolphin', 'dolphin hd textures', 'dolphin texture', 'gamecube texture pack', 'wii texture pack',
    'gamecube hd textures', 'wii hd textures', 'texture pack ppsspp', 'ppsspp textures', 'psp texture pack',
    'psp hd textures', 'ppsspp hd', 'texture pack citra', 'citra textures', '3ds texture pack', '3ds hd textures',
    'azahar textures', 'lime3ds textures', 'upscaled textures emulator', 'ai upscaled textures', 'hd texture pack',
    'texture replacement pack', 'remastered textures', 'hd remaster textures', 'retexture', 'texturepack',
    'ppsspp texture', 'pcsx2 texture', 'dolphin-emu texture', 'citra texture', 'ui hd texture', 'hd ui pack',
    'hd font texture', 'esrgan texture pack', 'texture upscale pack',
]
TOPICS = ['texture-pack', 'hd-texture-pack', 'custom-textures', 'texture-packs', 'hd-textures', 'texturepack',
          'texture-replacement', 'ppsspp', 'pcsx2', 'dolphin-emu', 'dolphin-emulator', 'citra', 'citra-emu',
          'azahar', 'gamecube', 'nintendo-3ds', 'psp', 'ps2', 'upscaling', 'esrgan']
# Code searches for the files an engine reads at the root of a pack.
CODE_QUERIES = ['filename:textures.ini hash', 'filename:textures.ini "[hashes]"', 'filename:pack.json skip_mipmap',
                'filename:pack.json use_new_hash', 'filename:textures.ini ppsspp']

PS2_SERIAL = re.compile(r'\b(S[CL][AEKPU][ACDMSX]|PAPX|PBPX|SCAJ|SCKA|SCPS|SLKA|SRPM|SCED|TCES|TCPS|TLES)[-_ ]?(\d{3})\.?(\d{2})\b')
PSP_ID = re.compile(r'\b((?:UL|UC|NP)[EJUAKHS][SMHBGJZ]|NPEZ|NPUZ|NPJJ|NPHG|NPEG|NPUG|NPJG)[-_ ]?(\d{5})\b')
DOLPHIN_ID = re.compile(r'\b([GRSDW][A-Z0-9]{2}[EPJKDFISUXYZWLM][A-Z0-9]{2})\b')
DOLPHIN_ID3 = re.compile(r'^([GRSDWNHJXCEFLM][A-Z0-9]{2})$')
TITLE_ID = re.compile(r'\b(0004000[0-9A-Fa-f]{9})\b')
TEX1 = re.compile(r'(^|/)tex1_[0-9]+x[0-9]+_', re.I)
# GLideN64 (Mupen64Plus-Next) hi-res names: <ROM name>#<crc>#<fmt>#<siz>[#<palette crc>]_<kind>.png
RICE = re.compile(r'#[0-9a-f]{8}#[0-4]#[0-3](#[0-9a-f]{8})?_(all|ciByRGBA|allciByRGBA|rgb|a)\.(png|bmp)$', re.I)
PCSX2_HASH = re.compile(r'(^|/)[0-9a-f]{16}-[0-9a-f]{8}(-[0-9a-f]{8})?\.(png|dds)$', re.I)
ARCHIVE = re.compile(r'\.(zip|7z|rar|tar|tar\.gz|tgz|tar\.zst|zst)(\.\d{3})?$', re.I)
# A search result is described only when its name, description or topics speak
# of textures (topic searches such as "ppsspp" also return emulators and tools).
TEXTURE_WORDS = re.compile(r'textur|retex|upscal|remaster|\bhd\b|[^a-z]hd[^a-z]|^hd|hd$|4k|2k|8k|\bui\b|font|esrgan|'
                           r'gigapixel|材质|纹理|高清|テクスチャ|hires|hi-res|high.?res|pack', re.I)


def log(line):
    print(line, flush=True)


class GitHub:
    def __init__(self, token):
        self.token = token
        self.calls = 0

    def get(self, path, accept='application/vnd.github+json', raw=False):
        url = path if path.startswith('https://') else API + path
        for attempt in range(6):
            request = urllib.request.Request(url, headers={'Accept': accept, 'User-Agent': 'NeoStation-catalogue-discovery',
                                                           'X-GitHub-Api-Version': '2022-11-28'})
            if self.token and url.startswith(API):
                request.add_header('Authorization', f'Bearer {self.token}')
            try:
                self.calls += 1
                with urllib.request.urlopen(request, timeout=60) as response:
                    data = response.read()
                    return data if raw else json.loads(data)
            except urllib.error.HTTPError as error:
                body = error.read()[:2000].decode('utf-8', 'replace').lower() if error.code in (403, 429) else ''
                limited = error.code == 429 or 'rate limit' in body or error.headers.get('X-RateLimit-Remaining') == '0'
                if limited and url.startswith(API):
                    reset = error.headers.get('X-RateLimit-Reset') or ''
                    retry = error.headers.get('Retry-After') or ''
                    remaining = error.headers.get('X-RateLimit-Remaining')
                    wait = 60
                    if retry.isdigit():
                        wait = int(retry) + 1
                    elif remaining == '0' and reset.isdigit():
                        wait = max(5, int(reset) - int(time.time()) + 2)
                    if wait > 3700 or attempt == 5:
                        raise
                    log(f'# rate limited on {url}, waiting {wait} s')
                    time.sleep(wait)
                    continue
                if error.code in (403, 404, 409, 451):
                    return None
                if error.code >= 500 and attempt < 5:
                    time.sleep(5 * (attempt + 1))
                    continue
                raise
            except (urllib.error.URLError, TimeoutError):
                if attempt < 5:
                    time.sleep(5 * (attempt + 1))
                    continue
                raise
        return None


def is_exclusions(path):
    """excluded.json and excluded-<origin>.json: reviewed and left out, not entries."""
    return path.name == 'excluded.json' or path.name.startswith('excluded-')


def catalogued():
    """Repositories already in a sources file, and those reviewed and left out."""
    known, excluded = {}, []
    for path in sorted(SOURCES.glob('*.json')):
        if is_exclusions(path):
            excluded += json.loads(path.read_text(encoding='utf-8'))
            continue
        for entry in json.loads(path.read_text(encoding='utf-8')):
            source = entry.get('source_id', '')
            if source.startswith('github:'):
                known.setdefault(source[7:].lower(), []).append(entry['id'])
    left_out = ' '.join(item['source'] for item in excluded).lower()
    return known, left_out


def ids_in(text):
    found = {'ps2': set(), 'psp': set(), 'dolphin': set(), '3ds': set()}
    for match in PS2_SERIAL.finditer(text.upper()):
        found['ps2'].add(f'{match.group(1)}-{match.group(2)}{match.group(3)}')
    for match in PSP_ID.finditer(text.upper()):
        found['psp'].add(f'{match.group(1)}{match.group(2)}')
    for match in TITLE_ID.finditer(text):
        found['3ds'].add(match.group(1).upper())
    return found


def tree_signals(paths):
    """What the file tree says: which engine reads it, and for which games."""
    signals = {'tex1': 0, 'textures_ini': [], 'pack_json': [], 'replacements': set(), 'pcsx2_hash': 0, 'rice': 0,
               'png': 0, 'dds': 0, 'ktx': 0, 'lfs': False, 'archives': []}
    ids = {'ps2': set(), 'psp': set(), 'dolphin': set(), '3ds': set()}
    folders = set()
    for path in paths:
        lower = path.lower()
        name = path.rsplit('/', 1)[-1]
        if TEX1.search(path):
            signals['tex1'] += 1
        if name.lower() == 'textures.ini':
            signals['textures_ini'].append(path)
        if name.lower() == 'pack.json':
            signals['pack_json'].append(path)
        if PCSX2_HASH.search(path):
            signals['pcsx2_hash'] += 1
        if RICE.search(name):
            signals['rice'] += 1
        if '/replacements/' in lower or lower.startswith('replacements/'):
            signals['replacements'].add(path[:lower.index('replacements/') + len('replacements/')])
        if lower.endswith('.png'):
            signals['png'] += 1
        elif lower.endswith('.dds'):
            signals['dds'] += 1
        elif lower.endswith('.ktx') or lower.endswith('.ktx2'):
            signals['ktx'] += 1
        if ARCHIVE.search(lower):
            signals['archives'].append(path)
        if name == '.gitattributes':
            signals['gitattributes'] = path
        for part in path.split('/')[:-1]:
            folders.add(part)
        if name.lower().endswith('.txt') and DOLPHIN_ID3.match(name[:-4]) or re.match(r'^[A-Z0-9]{6}\.txt$', name):
            ids['dolphin'].add(name[:-4])
    for folder in folders:
        upper = folder.upper()
        for kind, found in ids_in(upper).items():
            ids[kind] |= found
        if re.fullmatch(r'[GRSDW][A-Z0-9]{2}[A-Z][A-Z0-9]{2}', folder):
            ids['dolphin'].add(folder)
    signals['replacements'] = sorted(signals['replacements'])[:10]
    signals['textures_ini'] = signals['textures_ini'][:20]
    signals['pack_json'] = signals['pack_json'][:20]
    signals['archives'] = signals['archives'][:20]
    return signals, {kind: sorted(values)[:40] for kind, values in ids.items() if values}


def engine_guess(signals, text):
    text = text.lower()
    guesses = []
    if signals['textures_ini'] or 'ppsspp' in text:
        guesses.append('ppsspp')
    if signals['pack_json'] or any(word in text for word in ('citra', 'azahar', 'lime3ds', '3ds')):
        guesses.append('azahar')
    if signals['replacements'] or signals['pcsx2_hash'] or any(word in text for word in ('pcsx2', 'aethersx2', 'nethersx2', 'ps2')):
        guesses.append('armsx2')
    if (signals['tex1'] and not signals['pack_json']) or any(word in text for word in ('dolphin', 'gamecube', ' wii')):
        guesses.append('dolphin')
    if signals.get('rice') or any(word in text for word in ('gliden64', 'mupen64', 'hires_texture', 'nintendo 64', ' n64')):
        guesses.append('mupen64plus')
    return guesses


def search_repositories(gh, queries, topics, limit):
    found = {}
    for query in queries + [f'topic:{topic}' for topic in topics]:
        for page in range(1, 11):
            data = gh.get(f'/search/repositories?q={urllib.parse.quote(query)}&per_page=100&page={page}')
            if not data:
                break
            for item in data.get('items', []):
                found.setdefault(item['full_name'].lower(), item)
            if len(data.get('items', [])) < 100 or len(found) >= limit:
                break
            time.sleep(2.2)
        time.sleep(2.2)
        log(f'# search "{query}": {len(found)} repositories so far')
        if len(found) >= limit:
            break
    return found


def search_code(gh, queries):
    repositories = {}
    for query in queries:
        for page in range(1, 11):
            data = gh.get(f'/search/code?q={urllib.parse.quote(query)}&per_page=100&page={page}')
            if not data:
                break
            for item in data.get('items', []):
                repository = item['repository']['full_name']
                repositories.setdefault(repository.lower(), {'full_name': repository, 'paths': []})['paths'].append(item['path'])
            if len(data.get('items', [])) < 100:
                break
            time.sleep(6.5)
        time.sleep(6.5)
        log(f'# code "{query}": {len(repositories)} repositories so far')
    return repositories


def describe(gh, full_name, item, known, left_out, code_paths):
    record = {'repo': full_name}
    if item is None:
        item = gh.get(f'/repos/{full_name}') or {}
    for key in ('description', 'stargazers_count', 'pushed_at', 'fork', 'archived', 'size', 'default_branch', 'html_url'):
        record[key] = item.get(key)
    record['topics'] = item.get('topics') or []
    record['licence'] = ((item.get('license') or {}).get('spdx_id')) or None
    lower = full_name.lower()
    record['status'] = 'catalogued' if lower in known else ('reviewed' if lower in left_out else 'new')
    if lower in known:
        record['packs'] = known[lower]
    branch = item.get('default_branch') or 'main'
    tree = gh.get(f'/repos/{full_name}/git/trees/{urllib.parse.quote(branch)}?recursive=1') or {}
    paths = [entry['path'] for entry in tree.get('tree', []) if entry.get('type') == 'blob']
    record['files'] = len(paths)
    record['truncated'] = bool(tree.get('truncated'))
    record['top'] = sorted({path.split('/', 1)[0] for path in paths})[:25]
    signals, ids = tree_signals(paths + (code_paths or []))
    if signals.get('gitattributes'):
        attributes = gh.get(f'https://raw.githubusercontent.com/{full_name}/{urllib.parse.quote(branch)}/{signals["gitattributes"]}', raw=True) or b''
        signals['lfs'] = b'filter=lfs' in attributes
        signals.pop('gitattributes')
    record['signals'] = signals
    text = ''
    readme = next((path for path in sorted(paths, key=len) if '/' not in path and path.lower().startswith('readme')), None)
    if readme:
        data = gh.get(f'https://raw.githubusercontent.com/{full_name}/{urllib.parse.quote(branch)}/{urllib.parse.quote(readme)}', raw=True) or b''
        text = data.decode('utf-8', 'replace')
    readme_ids = ids_in(text)
    for kind, values in readme_ids.items():
        if values:
            ids.setdefault(kind, [])
            ids[kind] = sorted(set(ids[kind]) | values)[:40]
    record['ids'] = ids
    record['readme'] = re.sub(r'\s+', ' ', text)[:700]
    releases = gh.get(f'/repos/{full_name}/releases?per_page=10') or []
    record['releases'] = [{'tag': release.get('tag_name'), 'published': (release.get('published_at') or '')[:10],
                           'pre': release.get('prerelease'),
                           'assets': [[asset['name'], asset['size']] for asset in release.get('assets', [])][:12]}
                          for release in releases[:6]]
    record['engines'] = engine_guess(signals, ' '.join([full_name, item.get('description') or '', ' '.join(record['topics']), text[:4000]]))
    return record


def promising(record):
    """Texture files in the tree, an engine file, a game identifier or a release archive."""
    signals = record.get('signals') or {}
    textures = signals.get('tex1') or signals.get('textures_ini') or signals.get('pack_json') or signals.get('replacements') \
        or signals.get('pcsx2_hash') or signals.get('rice') or (signals.get('png', 0) + signals.get('dds', 0) + signals.get('ktx', 0)) >= 20
    archives = any(ARCHIVE.search(asset[0]) for release in record.get('releases') or [] for asset in release['assets'])
    return bool(textures or archives or record.get('ids') or signals.get('archives'))


def mode_github(args, gh, emit):
    known, left_out = catalogued()
    found = search_repositories(gh, REPOSITORY_QUERIES if not args.query else args.query,
                                TOPICS if not args.query else args.topic or [], args.limit)
    found = {lower: item for lower, item in found.items()
             if TEXTURE_WORDS.search(' '.join([item['full_name'], item.get('description') or '', ' '.join(item.get('topics') or [])]))}
    log(f'# {len(found)} repositories speak of textures')
    code = {}
    if not args.skip_code:
        try:
            code = search_code(gh, CODE_QUERIES)
        except urllib.error.HTTPError as error:
            log(f'# code search unavailable: HTTP {error.code}')
    for lower, entry in code.items():
        found.setdefault(lower, None)
    for name in args.repo or []:
        found.setdefault(name.lower(), None)
    log(f'# {len(found)} repositories to describe')
    names = sorted(found)
    if args.shard:
        index, count = (int(x) for x in args.shard.split('/'))
        names = names[index::count]
    for lower in names:
        item = found[lower]
        full_name = item['full_name'] if item else (code.get(lower) or {}).get('full_name') or next((n for n in args.repo or [] if n.lower() == lower), lower)
        try:
            record = describe(gh, full_name, item, known, left_out, (code.get(lower) or {}).get('paths'))
        except Exception as error:  # one repository never stops the others
            record = {'repo': full_name, 'error': repr(error)[:200]}
        if record.get('error') or (args.all or record.get('status') == 'new') and (args.all or promising(record)):
            emit(record)
    log(f'# {gh.calls} GitHub requests')


HEAD_CACHE = {}
HOST_LAST = {}
HOST_INTERVAL = 1.0  # seconds between two requests to the same host


def head(url):
    """Reachability and size of a URL without downloading it (one byte asked).

    Each URL is asked once per run, and a host at most once a second. The
    request names itself; a host that refuses automated requests is reported
    as such, never worked around."""
    if url in HEAD_CACHE:
        return HEAD_CACHE[url]
    host = urllib.parse.urlsplit(url).hostname or ''
    wait = HOST_LAST.get(host, 0) + HOST_INTERVAL - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    request = urllib.request.Request(url, headers={'User-Agent': 'NeoStation-catalogue-links', 'Range': 'bytes=0-0'})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            total = response.headers.get('Content-Range', '').rsplit('/', 1)[-1]
            size = int(total) if total.isdigit() else int(response.headers.get('Content-Length') or -1)
            result = {'status': response.status, 'size': size, 'type': response.headers.get('Content-Type', '')}
    except urllib.error.HTTPError as error:
        result = {'status': error.code}
    except Exception as error:
        result = {'status': 0, 'error': repr(error)[:120]}
    HOST_LAST[host] = time.monotonic()
    HEAD_CACHE[url] = result
    return result


# 401/403/429/503: the host refuses an automated check (login, rate limit,
# anti-bot page). That does not show the page is gone: reported apart.
REFUSED = (401, 403, 429, 503)


def link_state(status):
    return 'ok' if status in (200, 206) else 'refused' if status in REFUSED else 'broken'


def mode_links(args, gh, emit):
    latest_cache, head_cache = {}, {}
    totals = {}
    for path in sorted(SOURCES.glob('*.json')):
        if is_exclusions(path):
            continue
        for entry in json.loads(path.read_text(encoding='utf-8')):
            if args.only and entry['id'] not in args.only.split(','):
                continue
            page = head(entry['page_url'])
            result = {'id': entry['id'], 'page': page['status'], 'page_host': urllib.parse.urlsplit(entry['page_url']).hostname,
                      'automatable': bool((entry.get('download') or {}).get('automatable'))}
            parts = (entry.get('download') or {}).get('parts') or []
            result['parts'] = []
            for part in parts:
                checked = head(part['url'])
                # A repository archive is generated on request: no length is announced before it is sent.
                same = checked.get('size') == part.get('size') if part.get('size') and (checked.get('size') or -1) >= 0 else None
                result['parts'].append({'url': part['url'], 'status': checked.get('status'), 'size': checked.get('size'), 'same_size': same})
            source = entry.get('source_id', '')
            repository = (entry.get('download') or {}).get('repository')
            if source.startswith('github:') and repository:
                # A repository archive is pinned to a commit: newer when the default branch moved.
                if source not in head_cache:
                    info = gh.get(f'/repos/{source[7:]}') or {}
                    branch = info.get('default_branch')
                    head_cache[source] = ((gh.get(f'/repos/{source[7:]}/commits/{branch}') or {}).get('sha') if branch else None)
                head = head_cache[source]
                if head:
                    result['head'] = head[:12]
                    result['newer'] = head != repository.get('commit')
            elif source.startswith('github:'):
                if source not in latest_cache:
                    latest_cache[source] = gh.get(f'/repos/{source[7:]}/releases/latest')
                latest = latest_cache[source]
                if latest:
                    result['latest_release'] = latest.get('tag_name')
                    # The catalogued release is the tag of its download (or page) URL, not the version text.
                    urls = [part['url'] for part in parts] + [entry.get('page_url', '')]
                    tags = {re.search(r'/releases/(?:download|tag)/([^/]+)', url).group(1) for url in urls
                            if re.search(r'/releases/(?:download|tag)/([^/]+)', url)}
                    catalogued = {urllib.parse.unquote(tag) for tag in tags}
                    result['newer'] = bool(latest.get('tag_name')) and bool(catalogued) and latest.get('tag_name') not in catalogued
                    # A repository publishing several packs: its latest release may be another pack's.
                    result['review'] = 'latest release of the repository; check that it is this pack' if result['newer'] else None
            states = [link_state(result['page'])] + [link_state(p['status']) for p in result['parts']]
            if 'broken' in states or any(p['same_size'] is False for p in result['parts']):
                result['verdict'] = 'broken'
            elif 'refused' in states:
                result['verdict'] = 'refused'
            else:
                result['verdict'] = 'update' if result.get('newer') else 'ok'
            key = ('one-tap' if result['automatable'] else 'manual', result['verdict'])
            totals[key] = totals.get(key, 0) + 1
            emit(result)
    summary = {f'{kind} {verdict}': count for (kind, verdict), count in sorted(totals.items())}
    summary['urls'] = len(HEAD_CACHE)
    log('LINKS_SUMMARY ' + json.dumps(summary, sort_keys=True))


def engine_relevant(record):
    """A repository whose files an engine reads, or that names a game identifier."""
    signals = record.get('signals') or {}
    return bool(signals.get('tex1') or signals.get('textures_ini') or signals.get('pack_json') or signals.get('replacements') or signals.get('rice')
                or signals.get('pcsx2_hash') or record.get('ids'))


def mode_summarize(args, gh, emit):
    """One short line per engine-relevant candidate of a github run (its JSONL output)."""
    kept = 0
    for line in Path(args.candidates).read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get('error') or not engine_relevant(record):
            continue
        signals = record.get('signals') or {}
        assets = [f'{release["tag"]}:{name}:{size}' for release in record.get('releases') or [] for name, size in release['assets']
                  if ARCHIVE.search(name)][:6]
        emit({'repo': record['repo'], 'engines': record.get('engines'), 'ids': {k: v[:5] for k, v in (record.get('ids') or {}).items()},
              'tex1': signals.get('tex1'), 'ini': (signals.get('textures_ini') or [])[:3], 'packjson': (signals.get('pack_json') or [])[:2],
              'repl': (signals.get('replacements') or [])[:2], 'pcsx2': signals.get('pcsx2_hash'), 'rice': signals.get('rice'), 'png': signals.get('png'),
              'dds': signals.get('dds'), 'lfs': signals.get('lfs'), 'fork': record.get('fork'), 'files': record.get('files'),
              'stars': record.get('stargazers_count'), 'licence': record.get('licence'), 'pushed': (record.get('pushed_at') or '')[:10],
              'assets': assets, 'top': (record.get('top') or [])[:8], 'desc': (record.get('description') or '')[:90]})
        kept += 1
    log(f'# {kept} engine-relevant candidates')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('mode', choices=['github', 'links', 'summarize'])
    parser.add_argument('--candidates', default='', help='summarize: the JSONL written by the github mode')
    parser.add_argument('--out', required=True)
    parser.add_argument('--query', action='append', help='replace the built-in repository searches')
    parser.add_argument('--topic', action='append', help='with --query: the topics to search (none otherwise)')
    parser.add_argument('--repo', action='append', help='also describe this owner/name')
    parser.add_argument('--limit', type=int, default=3000, help='stop searching after this many repositories')
    parser.add_argument('--skip-code', action='store_true')
    parser.add_argument('--all', action='store_true', help='also report catalogued and reviewed repositories')
    parser.add_argument('--only', default='', help='links: only these pack ids')
    parser.add_argument('--shard', default='', help='github: describe only the repositories i, i+n... (i/n)')
    args = parser.parse_args()
    gh = GitHub(os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN'))
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as out:
        def emit(record):
            line = json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
            out.write(line + '\n')
            out.flush()
            log('DISCOVER ' + line)
        log('DISCOVER_BEGIN')
        {'github': mode_github, 'links': mode_links, 'summarize': mode_summarize}[args.mode](args, gh, emit)
        log('DISCOVER_END')


if __name__ == '__main__':
    sys.exit(main())
