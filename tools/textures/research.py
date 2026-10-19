#!/usr/bin/env python3
"""Reviews the maintainer's reference list of HD texture projects (candidates only).

Run on a CI runner (the work container cannot reach these hosts). For each
reference of tools/textures/research/references-386.json, and each provenance
link of the same entry, it reads the page once and reports what a reviewer
needs to decide whether a pack can enter the catalogue:

  - HTTP status, final URL, title; a page that refuses an automated read
    (401/403/429/503, a bot challenge or a CAPTCHA page) is reported
    "protected" and never worked around;
  - the links of the page, classified by host (GitHub release or archive,
    GameBanana file, MEGA, Google Drive, MediaFire, Dropbox, OneDrive,
    archive.org, Patreon, Ko-fi, ...), with their anchor text;
  - GameBanana mods: the public API (apiv11) for the name, submitter,
    credits, game, files (size, MD5, date) and, for each file, the archive
    file tree GameBanana publishes, summarized as the engines read it
    (Dolphin tex1_ names and Game ID folders, Azahar title ID folders and
    pack.json, PPSSPP textures.ini, Beetle PSX <hash>-<palette> names,
    PCSX2 replacements, RomFS/ExeFS mods);
  - GitHub repositories: releases (assets, sizes) and the default branch
    tree, summarized the same way;
  - the Texture Packs Archive spreadsheet: every row of every sheet that
    names a link;
  - listing pages (forum boards, directory pages): the thread or project
    links of the following pages too (--pages).

Nothing is downloaded beyond the pages and the API answers, and nothing is
written to tools/textures/sources: a candidate becomes a catalogue entry only
after review and verify_packs.py.

  python3 tools/textures/research.py refs --console gc --out build/hdtex/research-gc.jsonl
  python3 tools/textures/research.py refs --ids S001,S005 --pages 6 --out ...
"""
import argparse
import html
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from xml.etree import ElementTree

HERE = Path(__file__).resolve().parent
REFERENCES = HERE / 'research' / 'references-386.json'
USER_AGENT = 'NeoStation-HD-catalogue-review/1.0 (+https://github.com/TarbleFR/neostation-ios)'
MAX_PAGE = 4 << 20
PACE = 1.5  # seconds between two requests to one host
_last = {}

HOSTS = [
    ('github-release', r'github\.com/[^/]+/[^/]+/releases'),
    ('github-archive', r'(codeload\.github\.com|github\.com/[^/]+/[^/]+/archive/)'),
    ('github', r'(//|\.)github\.com/'),
    ('github-raw', r'(raw\.githubusercontent\.com|objects\.githubusercontent\.com)'),
    ('gitlab', r'gitlab\.com/'),
    ('codeberg', r'codeberg\.org/'),
    ('gamebanana-file', r'gamebanana\.com/(dl|mmdl)/'),
    ('gamebanana', r'gamebanana\.com/'),
    ('mega', r'mega\.(nz|co\.nz|io)/'),
    ('gdrive', r'(drive|docs)\.google\.com/'),
    ('gsites', r'sites\.google\.com/'),
    ('mediafire', r'mediafire\.com/'),
    ('dropbox', r'dropbox\.com/'),
    ('onedrive', r'(1drv\.ms|onedrive\.live\.com|sharepoint\.com)'),
    ('archive-org', r'archive\.org/(download|details)/'),
    ('wayback', r'web\.archive\.org/'),
    ('pixeldrain', r'pixeldrain\.com/'),
    ('patreon', r'patreon\.com/'),
    ('kofi', r'ko-fi\.com/'),
    ('moddb', r'moddb\.com/'),
    ('nexus', r'nexusmods\.com/'),
    ('itch', r'itch\.io/'),
    ('reddit', r'reddit\.com/'),
    ('youtube', r'(youtube\.com|youtu\.be)/'),
    ('discord', r'discord\.(gg|com)/'),
    ('dolphin-forum', r'forums\.dolphin-emu\.org/'),
    ('ppsspp-forum', r'forums\.ppsspp\.org/'),
    ('gbatemp', r'gbatemp\.net/'),
    ('terabox', r'(terabox|1024tera)\.com/'),
    ('workupload', r'workupload\.com/'),
    ('catbox', r'(catbox|litterbox)\.moe/'),
]
FILE_EXT = re.compile(r'\.(zip|7z|rar|tar|gz|xz|zst)(\?|$)', re.I)
SKIP_LINK = re.compile(r'(\.(css|js|svg|ico|woff2?|ttf|jpe?g|gif|webp|png)(\?|$))|^(javascript|mailto):|^#', re.I)
CHALLENGE = re.compile(r'(cf-chl|challenge-platform|Just a moment\.\.\.|Attention Required|captcha|hcaptcha|recaptcha|'
                       r'Checking your browser|DDoS protection|Enable JavaScript and cookies)', re.I)


def host_kind(url):
    for kind, pattern in HOSTS:
        if re.search(pattern, url, re.I):
            return kind
    return 'other'


def pace(url):
    host = urllib.parse.urlsplit(url).hostname or ''
    wait = _last.get(host, 0) + PACE - time.time()
    if wait > 0:
        time.sleep(wait)
    _last[host] = time.time()


def fetch(url, accept='text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8', headers=None, limit=MAX_PAGE):
    """One GET; returns {status, url, type, body (bytes), error}. Never retried on a refusal."""
    pace(url)
    request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, 'Accept': accept, **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=40) as response:
            body = response.read(limit + 1)
            return {'status': response.status, 'url': response.geturl(), 'type': response.headers.get('Content-Type', ''),
                    'length': response.headers.get('Content-Length'), 'body': body[:limit], 'truncated': len(body) > limit}
    except urllib.error.HTTPError as error:
        body = b''
        try:
            body = error.read(200000)
        except Exception:
            pass
        return {'status': error.code, 'url': url, 'type': error.headers.get('Content-Type', '') if error.headers else '',
                'body': body, 'error': f'HTTP {error.code}'}
    except Exception as error:  # DNS, TLS, timeout
        return {'status': 0, 'url': url, 'type': '', 'body': b'', 'error': repr(error)[:200]}


def head(url):
    """Size and type of a candidate file without downloading it (HEAD, then a 1-byte range)."""
    pace(url)
    for method, extra in (('HEAD', {}), ('GET', {'Range': 'bytes=0-0'})):
        request = urllib.request.Request(url, method=method, headers={'User-Agent': USER_AGENT, **extra})
        try:
            with urllib.request.urlopen(request, timeout=40) as response:
                size = response.headers.get('Content-Length')
                if method == 'GET' and response.headers.get('Content-Range'):
                    size = response.headers['Content-Range'].rsplit('/', 1)[-1]
                return {'status': response.status, 'final': response.geturl(), 'type': response.headers.get('Content-Type', ''),
                        'size': int(size) if size and size.isdigit() else None,
                        'disposition': response.headers.get('Content-Disposition', '')}
        except urllib.error.HTTPError as error:
            if method == 'GET':
                return {'status': error.code, 'final': url}
        except Exception as error:
            if method == 'GET':
                return {'status': 0, 'final': url, 'error': repr(error)[:120]}
    return {'status': 0, 'final': url}


def text_of(body):
    return body.decode('utf-8', 'replace') if isinstance(body, (bytes, bytearray)) else body


def page_title(page):
    match = re.search(r'<title[^>]*>(.*?)</title>', page, re.I | re.S)
    return html.unescape(re.sub(r'\s+', ' ', match.group(1))).strip()[:200] if match else ''


def page_links(page, base):
    links = []
    seen = set()
    for match in re.finditer(r'<a\b[^>]*?href\s*=\s*["\']([^"\']+)["\'][^>]*>(.*?)</a>', page, re.I | re.S):
        href = html.unescape(match.group(1)).strip()
        if SKIP_LINK.search(href) and not FILE_EXT.search(href):
            continue
        url = urllib.parse.urljoin(base, href)
        if not url.startswith('http') or url in seen:
            continue
        seen.add(url)
        anchor = html.unescape(re.sub(r'<[^>]+>', ' ', match.group(2)))
        links.append({'url': url, 'text': re.sub(r'\s+', ' ', anchor).strip()[:90], 'kind': host_kind(url)})
    # Bare URLs written in posts (forums often print them as text).
    for match in re.finditer(r'https?://[^\s"\'<>\]\)]+', re.sub(r'<a\b[^>]*>.*?</a>', ' ', page, flags=re.I | re.S)):
        url = html.unescape(match.group(0)).rstrip('.,;')
        if url not in seen and not SKIP_LINK.search(url):
            seen.add(url)
            links.append({'url': url, 'text': '(text)', 'kind': host_kind(url)})
    return links


def own_navigation(link, site):
    """A link of the page's own site that is neither a file nor a thread or project page."""
    host = urllib.parse.urlsplit(link['url']).hostname or ''
    if host != site or FILE_EXT.search(link['url']):
        return False
    return not re.search(r'(showthread\.php\?tid=|/threads/|Thread-|/mods/\d+|/dl/\d+|/downloads/[a-z0-9-]+|/addons/[a-z0-9-]+|'
                         r'/releases|/texturepacks/|/download)', link['url'], re.I)


def page_text(page):
    page = re.sub(r'<(script|style)\b.*?</\1>', ' ', page, flags=re.I | re.S)
    page = re.sub(r'<br\s*/?>|</p>|</div>|</li>', '\n', page, flags=re.I)
    return html.unescape(re.sub(r'[ \t]+', ' ', re.sub(r'<[^>]+>', ' ', page)))


KEYWORDS = re.compile(r'(download|mega|drive|mediafire|version|update|v\d+\.\d+|release|credit|permission|reupload|re-upload|'
                      r'do not|don\'t|patreon|early access|free|licen[cs]e|game ?id|serial|title ?id|NTSC|PAL|USA|EUR|JPN|'
                      r'4k|2k|1080|resolution|dolphin|citra|azahar|lime|ppsspp|duckstation|beetle|pcsx2|aethersx2|nethersx2)', re.I)


def snippets(page, limit=12):
    """Lines of the page text that talk about downloads, versions, terms or identifiers."""
    out = []
    for line in page_text(page).splitlines():
        line = line.strip()
        if 12 <= len(line) <= 400 and KEYWORDS.search(line) and line not in out:
            out.append(line[:240])
            if len(out) >= limit:
                break
    return out


# ---------------------------------------------------------------- archive trees

def summarize_tree(paths):
    """What the engines would read in a list of archive paths."""
    paths = [p.replace('\\', '/') for p in paths]
    summary = Counter()
    game_ids, title_ids, discs, tops = Counter(), Counter(), Counter(), Counter()
    for path in paths:
        parts = [p for p in path.split('/') if p]
        if not parts:
            continue
        tops[parts[0]] += 1
        name = parts[-1]
        low = name.lower()
        if re.match(r'^tex1_\d+x\d+_', low) and low.endswith(('.png', '.dds')):
            summary['tex1'] += 1
            for part in parts[:-1]:
                if re.fullmatch(r'[A-Z0-9]{6}', part) or re.fullmatch(r'[A-Z0-9]{3}', part):
                    game_ids[part] += 1
                    break
        elif re.fullmatch(r'[0-9a-f]{1,8}-[0-9a-f]{1,8}\.(png|dds|webp|jpe?g|bmp|tga)', low):
            summary['beetle'] += 1
        elif low == 'textures.ini':
            summary['textures.ini'] += 1
            for part in parts[:-1]:
                if re.fullmatch(r'[A-Z]{4}[0-9]{5}', part):
                    discs[part] += 1
        elif low == 'pack.json':
            summary['pack.json'] += 1
        elif low.endswith(('.png', '.dds', '.ktx', '.ktx2', '.zim', '.astc')):
            summary[low.rsplit('.', 1)[-1]] += 1
        elif low in ('exheader.bin', 'code.bin') or 'romfs' in [p.lower() for p in parts] or 'exefs' in [p.lower() for p in parts]:
            summary['romfs/exefs'] += 1
        elif low.endswith(('.zip', '.7z', '.rar')):
            summary['nested-archive'] += 1
        elif low.endswith('.txt') and re.fullmatch(r'[A-Z0-9]{3,6}\.txt', name):
            summary['dolphin-marker'] += 1
        for part in parts[:-1]:
            if re.fullmatch(r'[0-9A-Fa-f]{16}', part):
                title_ids[part.upper()] += 1
                break
        if 'replacements' in [p.lower() for p in parts]:
            summary['pcsx2-replacements'] += 1
    return {'entries': len(paths), 'counts': dict(summary), 'game_ids': dict(game_ids.most_common(8)),
            'title_ids': dict(title_ids.most_common(8)), 'disc_ids': dict(discs.most_common(8)),
            'top': dict(tops.most_common(8))}


def flatten_tree(node, prefix=''):
    """GameBanana's _aArchiveFileTree: nested dicts/lists of names."""
    out = []
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(value, (dict, list)):
                out += flatten_tree(value, f'{prefix}{key}/')
            else:
                out.append(f'{prefix}{value if isinstance(value, str) else key}')
    elif isinstance(node, list):
        for value in node:
            if isinstance(value, (dict, list)):
                out += flatten_tree(value, prefix)
            else:
                out.append(f'{prefix}{value}')
    return out


# ---------------------------------------------------------------- GameBanana

def gamebanana(url):
    match = re.search(r'gamebanana\.com/(mods|wips)/(\d+)', url)
    if not match:
        return None
    kind = 'Mod' if match.group(1) == 'mods' else 'Wip'
    api = f'https://gamebanana.com/apiv11/{kind}/{match.group(2)}/ProfilePage'
    response = fetch(api, accept='application/json')
    out = {'api': api, 'status': response['status']}
    if response['status'] != 200:
        out['error'] = response.get('error') or text_of(response['body'])[:200]
        return out
    try:
        data = json.loads(response['body'])
    except ValueError:
        out['error'] = 'not json'
        return out
    out['name'] = data.get('_sName')
    out['version'] = data.get('_sVersion')
    out['game'] = (data.get('_aGame') or {}).get('_sName')
    out['submitter'] = (data.get('_aSubmitter') or {}).get('_sName')
    out['date_added'] = data.get('_tsDateAdded')
    out['date_updated'] = data.get('_tsDateUpdated') or data.get('_tsDateModified')
    out['category'] = (data.get('_aCategory') or {}).get('_sName')
    out['private'] = data.get('_bIsPrivate')
    out['trashed'] = data.get('_bIsTrashed')
    out['withheld'] = data.get('_bIsWithheld')
    out['initial_visibility'] = data.get('_sInitialVisibility')
    credits = []
    for group in data.get('_aCredits') or []:
        for author in group.get('_aAuthors') or []:
            credits.append(f"{group.get('_sGroupName', '')}: {author.get('_sName', '')} ({author.get('_sRole', '')})".strip())
    out['credits'] = credits[:20]
    licence = {}
    for key in ('_sLicense', '_aLicenseChecklist', '_sLicenseText'):
        if data.get(key):
            licence[key] = data[key]
    out['licence'] = licence
    description = re.sub(r'<[^>]+>', ' ', data.get('_sText') or '')
    out['text'] = [line for line in snippets(description)][:10]
    files = []
    for item in data.get('_aFiles') or []:
        entry = {'id': item.get('_idRow'), 'file': item.get('_sFile'), 'size': item.get('_nFilesize'),
                 'md5': item.get('_sMd5Checksum'), 'date': item.get('_tsDateAdded'), 'url': item.get('_sDownloadUrl'),
                 'description': (item.get('_sDescription') or '')[:160], 'analysis': item.get('_sAnalysisResult')}
        for endpoint in (f"https://gamebanana.com/apiv11/File/{item.get('_idRow')}/RawFileTree",
                         f"https://gamebanana.com/apiv11/File/{item.get('_idRow')}"):
            detail = fetch(endpoint, accept='application/json')
            if detail['status'] != 200:
                entry.setdefault('tree_status', []).append(detail['status'])
                continue
            try:
                document = json.loads(detail['body'])
            except ValueError:
                continue
            tree = document if isinstance(document, list) else (
                (document.get('_aMetadata') or {}).get('_aArchiveFileTree') or document.get('_aArchiveFileTree')
                or document.get('_aFileTree'))
            if tree:
                entry['tree'] = summarize_tree(flatten_tree(tree))
                entry['tree_source'] = endpoint.rsplit('/', 1)[-1]
                break
            entry.setdefault('tree_keys', sorted(document)[:20] if isinstance(document, dict) else type(document).__name__)
        files.append(entry)
    out['files'] = files
    out['alternate_sources'] = [{'url': s.get('url') or s.get('_sUrl'), 'text': s.get('description') or s.get('_sDescription')}
                                for s in (data.get('_aAlternateFileSources') or [])][:10]
    return out


# ---------------------------------------------------------------- GitHub

def github_api(path):
    headers = {'Accept': 'application/vnd.github+json'}
    token = os.environ.get('GH_TOKEN')
    if token:
        headers['Authorization'] = f'Bearer {token}'
    response = fetch('https://api.github.com/' + path, accept='application/vnd.github+json', headers=headers, limit=32 << 20)
    if response['status'] != 200:
        return None, response.get('error') or response['status']
    try:
        return json.loads(response['body']), None
    except ValueError:
        return None, 'not json'


def github(url):
    match = re.match(r'https?://github\.com/([^/]+)/([^/#?]+)', url)
    if not match:
        return None
    owner, repo = match.group(1), match.group(2).removesuffix('.git')
    out = {'repo': f'{owner}/{repo}'}
    info, error = github_api(f'repos/{owner}/{repo}')
    if not info:
        out['error'] = error
        return out
    out.update(default_branch=info.get('default_branch'), licence=(info.get('license') or {}).get('spdx_id'),
               size_kb=info.get('size'), pushed=info.get('pushed_at'), archived=info.get('archived'),
               description=(info.get('description') or '')[:200])
    releases, _ = github_api(f'repos/{owner}/{repo}/releases?per_page=10')
    out['releases'] = [{'tag': r.get('tag_name'), 'date': r.get('published_at'),
                        'assets': [{'name': a['name'], 'size': a['size'], 'url': a['browser_download_url']}
                                   for a in r.get('assets') or []][:12]} for r in releases or []]
    tree, error = github_api(f"repos/{owner}/{repo}/git/trees/{info.get('default_branch')}?recursive=1")
    if tree:
        paths = [item['path'] for item in tree.get('tree') or [] if item.get('type') == 'blob']
        out['tree'] = summarize_tree(paths)
        out['tree']['truncated'] = tree.get('truncated')
        lfs = [p for p in paths if p == '.gitattributes']
        out['lfs_attributes'] = bool(lfs)
    return out


# ---------------------------------------------------------------- spreadsheet

def spreadsheet(url):
    match = re.search(r'/d/([A-Za-z0-9_-]{20,})', url)
    if not match:
        return None
    file_id = match.group(1)
    out = {'id': file_id, 'sheets': []}
    data = None
    for candidate in (f'https://docs.google.com/spreadsheets/d/{file_id}/export?format=xlsx',
                      f'https://drive.google.com/uc?export=download&id={file_id}'):
        response = fetch(candidate, accept='*/*', limit=64 << 20)
        out.setdefault('tried', []).append({'url': candidate, 'status': response['status'], 'type': response['type'][:60]})
        if response['status'] == 200 and response['body'][:2] == b'PK':
            data = response['body']
            break
    if data is None:
        return out
    book = zipfile.ZipFile(io.BytesIO(data))
    ns = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
          'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
    shared = []
    if 'xl/sharedStrings.xml' in book.namelist():
        root = ElementTree.fromstring(book.read('xl/sharedStrings.xml'))
        for item in root.findall('m:si', ns):
            shared.append(''.join(t.text or '' for t in item.iter('{%s}t' % ns['m'])))
    workbook = ElementTree.fromstring(book.read('xl/workbook.xml'))
    rels = ElementTree.fromstring(book.read('xl/_rels/workbook.xml.rels'))
    targets = {rel.get('Id'): rel.get('Target') for rel in rels}
    for sheet in workbook.find('m:sheets', ns):
        name = sheet.get('name')
        target = targets.get(sheet.get('{%s}id' % ns['r']), '')
        path = 'xl/' + target.lstrip('/').removeprefix('xl/')
        if path not in book.namelist():
            continue
        root = ElementTree.fromstring(book.read(path))
        links = {}
        rels_path = path.replace('worksheets/', 'worksheets/_rels/') + '.rels'
        if rels_path in book.namelist():
            sheet_rels = {r.get('Id'): r.get('Target') for r in ElementTree.fromstring(book.read(rels_path))}
            for link in root.iter('{%s}hyperlink' % ns['m']):
                target_url = sheet_rels.get(link.get('{%s}id' % ns['r']))
                if target_url:
                    links[link.get('ref')] = target_url
        rows = []
        for row in root.iter('{%s}row' % ns['m']):
            cells = []
            for cell in row.findall('m:c', ns):
                value = cell.find('m:v', ns)
                inline = cell.find('m:is', ns)
                text = ''
                if cell.get('t') == 's' and value is not None:
                    text = shared[int(value.text)]
                elif inline is not None:
                    text = ''.join(t.text or '' for t in inline.iter('{%s}t' % ns['m']))
                elif value is not None:
                    text = value.text or ''
                if cell.get('r') in links:
                    text = f'{text} <{links[cell.get("r")]}>'.strip()
                cells.append(text.strip())
            if any(cells):
                rows.append(cells)
        out['sheets'].append({'name': name, 'rows': len(rows), 'header': rows[0] if rows else [], 'data': rows[1:]})
    return out


# ---------------------------------------------------------------- pages

def review_url(url, follow_pages=0):
    record = {'url': url, 'kind': host_kind(url)}
    if record['kind'] in ('mega', 'patreon', 'discord', 'terabox'):
        record['status'] = 'not-read'
        record['reason'] = 'host the review does not read (encrypted, account or app only)'
        return record
    if record['kind'] == 'gamebanana' and re.search(r'gamebanana\.com/(mods|wips)/\d+', url):
        record['gamebanana'] = gamebanana(url)
        record['status'] = record['gamebanana'].get('status')
        return record
    if record['kind'] == 'github' and re.match(r'https?://github\.com/[^/]+/[^/#?]+/?(blob/[^/]+/[^#?]+)?$', url):
        if '/blob/' not in url:
            record['github'] = github(url)
            record['status'] = 200 if record['github'] and not record['github'].get('error') else 0
            return record
    if record['kind'] == 'gdrive' and '/spreadsheets/' in url:
        record['spreadsheet'] = spreadsheet(url)
        record['status'] = 200 if record['spreadsheet'] and record['spreadsheet']['sheets'] else 0
        return record
    reddit = re.match(r'https?://(www\.)?reddit\.com/(r/[^/]+/comments/[A-Za-z0-9]+)', url)
    target = f'https://www.reddit.com/{reddit.group(2)}/.json?limit=100' if reddit else url
    response = fetch(target)
    record['status'] = response['status']
    record['final'] = response['url']
    record['type'] = response['type'][:60]
    body = text_of(response['body'])
    protected = response['status'] in (401, 403, 429, 503) or (response['status'] in (200, 202) and CHALLENGE.search(body[:20000] or '') and
                                                                 'html' in response['type'] and len(page_links(body, url)) < 15)
    if protected:
        record['protected'] = True
        record['status_text'] = response.get('error') or 'bot challenge'
        return record
    if response['status'] != 200:
        record['error'] = response.get('error')
        return record
    if reddit:
        try:
            listing = json.loads(body)
            post = listing[0]['data']['children'][0]['data']
            texts = [post.get('title', ''), post.get('selftext', ''), post.get('url', '')]
            for child in listing[1]['data']['children'][:60]:
                texts.append(child.get('data', {}).get('body', ''))
            joined = '\n'.join(t for t in texts if t)
            record['title'] = post.get('title')
            record['author'] = post.get('author')
            record['links'] = [{'url': u, 'text': '(reddit)', 'kind': host_kind(u)} for u in
                               dict.fromkeys(re.findall(r'https?://[^\s\)\]]+', joined))]
            record['snippets'] = snippets(joined)
        except (ValueError, KeyError, IndexError):
            record['error'] = 'reddit json'
        return record
    if 'html' not in response['type'] and not body.lstrip().startswith('<'):
        record['body_text'] = body[:600]
        return record
    record['title'] = page_title(body)
    site = urllib.parse.urlsplit(response['url']).hostname or ''
    record['links'] = [link for link in page_links(body, response['url'])
                       if (link['kind'] != 'other' or FILE_EXT.search(link['url'])) and not own_navigation(link, site)]
    record['snippets'] = snippets(body)
    if follow_pages:
        record['listing'] = listing_pages(url, body, follow_pages)
    return record


def next_pages(url, page, count):
    """URLs of the following pages of a listing, by the site's own pagination."""
    out = []
    if 'forums.ppsspp.org/forumdisplay.php' in url:
        out = [f'{url}&page={n}' for n in range(2, count + 1)]
    elif 'gbatemp.net/forums/' in url:
        out = [f"{url.rstrip('/')}/page-{n}" for n in range(2, count + 1)]
    elif 'forums.dolphin-emu.org/Forum-' in url:
        out = [f'{url}?page={n}' for n in range(2, count + 1)]
    elif 'emulationking.com' in url:
        out = [f"{url.rstrip('/')}/page/{n}/" for n in range(2, count + 1)]
    elif 'forums.dolphin-emu.org/archive/index.php?forum-' in url:
        base = re.sub(r'forum-(\d+)(-\d+)?\.html.*$', r'forum-\1', url)
        out = [f'{base}-{n}.html' for n in range(1, count + 1)]
    return out


def thread_links(page, base):
    keep = []
    for link in page_links(page, base):
        u = link['url']
        if re.search(r'(showthread\.php\?tid=\d+|/threads/[^/]+\.\d+/?$|Thread-[^/?#]+$|archive/index\.php\?thread-\d+|'
                     r'/texturepacks/[^/]+/?$|henrikomagnifico\.com/[a-z0-9-]+$)', u) and link['text'] and link['text'] != '(text)':
            keep.append({'url': u, 'text': link['text']})
    return keep


def listing_pages(url, first, count):
    pages = [{'url': url, 'threads': thread_links(first, url)}]
    for page_url in next_pages(url, first, count):
        response = fetch(page_url)
        body = text_of(response['body'])
        if response['status'] != 200 or CHALLENGE.search(body[:20000] or ''):
            pages.append({'url': page_url, 'status': response['status'], 'protected': response['status'] in (401, 403, 429, 503)})
            break
        threads = thread_links(body, page_url)
        pages.append({'url': page_url, 'threads': threads})
        if not threads:
            break
    return pages


def describe(record, out):
    """Compact log lines for one reviewed URL."""
    status = record.get('status')
    flag = ' PROTECTED' if record.get('protected') else ''
    out.append(f"  {record['kind']} {status}{flag} {record['url']}" + (f" -> {record['final']}" if record.get('final') and record['final'] != record['url'] else ''))
    if record.get('reason'):
        out.append(f"    {record['reason']}")
    if record.get('title'):
        out.append(f"    title: {record['title'][:160]}")
    if record.get('error'):
        out.append(f"    error: {record['error']}")
    gb = record.get('gamebanana')
    if gb:
        out.append(f"    GB {gb.get('name')!r} v{gb.get('version')} game={gb.get('game')!r} by {gb.get('submitter')} cat={gb.get('category')} "
                   f"added={gb.get('date_added')} upd={gb.get('date_updated')} withheld={gb.get('withheld')} trashed={gb.get('trashed')}")
        if gb.get('credits'):
            out.append(f"    credits: {'; '.join(gb['credits'])[:300]}")
        if gb.get('licence'):
            out.append(f"    licence: {json.dumps(gb['licence'])[:300]}")
        for line in gb.get('text') or []:
            out.append(f"    | {line[:200]}")
        for f in gb.get('files') or []:
            out.append(f"    FILE {f.get('id')} {f.get('file')} {f.get('size')} md5={f.get('md5')} date={f.get('date')} {f.get('url')} {f.get('analysis') or ''}")
            if f.get('description'):
                out.append(f"      desc: {f['description']}")
            if f.get('tree'):
                out.append(f"      tree: {json.dumps(f['tree'], sort_keys=True)[:400]}")
            elif f.get('tree_keys') or f.get('tree_status'):
                out.append(f"      no tree: status={f.get('tree_status')} keys={f.get('tree_keys')}")
        for alt in gb.get('alternate_sources') or []:
            out.append(f"    ALT {alt.get('url')} {alt.get('text') or ''}")
    gh = record.get('github')
    if gh:
        out.append(f"    GH {gh.get('repo')} licence={gh.get('licence')} size={gh.get('size_kb')}KB pushed={gh.get('pushed')} "
                   f"archived={gh.get('archived')} lfs={gh.get('lfs_attributes')} err={gh.get('error')}")
        if gh.get('description'):
            out.append(f"    | {gh['description']}")
        for release in gh.get('releases') or []:
            out.append(f"    REL {release['tag']} {release['date']} " + ', '.join(f"{a['name']}({a['size']})" for a in release['assets']))
        if gh.get('tree'):
            out.append(f"    tree: {json.dumps(gh['tree'], sort_keys=True)[:500]}")
    sheet = record.get('spreadsheet')
    if sheet:
        out.append(f"    SHEET tried={sheet.get('tried')}")
        for item in sheet.get('sheets') or []:
            out.append(f"    SHEET {item['name']!r} rows={item['rows']} header={item['header'][:10]}")
    for line in record.get('snippets') or []:
        out.append(f"    | {line[:200]}")
    shown = 0
    for link in record.get('links') or []:
        if link['kind'] in ('youtube', 'discord', 'reddit') and shown > 20:
            continue
        out.append(f"    LINK [{link['kind']}] {link['url'][:180]} :: {link['text'][:60]}")
        shown += 1
        if shown >= 60:
            out.append('    LINK ...')
            break
    for page in record.get('listing') or []:
        out.append(f"    PAGE {page['url']} status={page.get('status', 200)} threads={len(page.get('threads') or [])}")
        for thread in page.get('threads') or []:
            out.append(f"      T {thread['url'][:160]} :: {thread['text'][:90]}")


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='mode', required=True)
    refs = sub.add_parser('refs')
    refs.add_argument('--console', default='')
    refs.add_argument('--ids', default='')
    refs.add_argument('--urls', default='', help='extra URLs separated by |, reviewed as references "X..."')
    refs.add_argument('--pages', type=int, default=0, help='listing pages to follow for directory references')
    refs.add_argument('--heads', action='store_true', help='size of direct file links found (HEAD, no download)')
    refs.add_argument('--out', required=True)
    args = parser.parse_args()
    references = json.loads(REFERENCES.read_text(encoding='utf-8'))['references']
    ids = {item for item in args.ids.split(',') if item}
    selected = [r for r in references if (not args.console or r['console'] in args.console.split(',')) and (not ids or r['id'] in ids)]
    for index, url in enumerate(u for u in args.urls.split('|') if u):
        selected.append({'id': f'X{index + 1:03d}', 'console': 'extra', 'title': url, 'url': url, 'provenance': []})
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    totals = Counter()
    print('RESEARCH_BEGIN', len(selected), flush=True)
    with open(args.out, 'w', encoding='utf-8') as out:
        for reference in selected:
            lines = [f"REF {reference['id']} [{reference['console']}] {reference['title']}"]
            records = []
            for url in [reference['url'], *reference.get('provenance', [])]:
                try:
                    record = review_url(url, args.pages if reference['console'] == 'directory' or reference['id'] in ids else 0)
                except Exception as error:  # one broken page never stops the review
                    record = {'url': url, 'kind': host_kind(url), 'status': 0, 'error': repr(error)[:200]}
                if args.heads:
                    for link in record.get('links') or []:
                        if FILE_EXT.search(link['url']) or link['kind'] in ('github-release', 'gamebanana-file', 'archive-org'):
                            link['head'] = head(link['url'])
                records.append(record)
                describe(record, lines)
                totals['protected' if record.get('protected') else str(record.get('status'))] += 1
            for link in (link for record in records for link in record.get('links') or [] if link.get('head')):
                h = link['head']
                lines.append(f"    HEAD {h.get('status')} {h.get('size')} {h.get('type', '')[:40]} {link['url'][:160]}")
            out.write(json.dumps({'reference': reference, 'records': records}, ensure_ascii=False) + '\n')
            print('\n'.join(lines), flush=True)
    print('RESEARCH_END', dict(totals), flush=True)


if __name__ == '__main__':
    main()
