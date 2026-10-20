#!/usr/bin/env python3
"""Builds the unified HD texture catalogue from its reviewed sources and the
results of verify_packs.py.

  tools/textures/sources/<console>.json   reviewed entries (author, page, licence,
                                          download, install layout), one list per console
  tools/textures/verified.jsonl           one verification record per pack (real
                                          download, size, SHA-256, installed files)

Output, byte-identical in both places (gzip without a timestamp):
  native/textures/catalogue/manifest.json.gz                       hosted copy, refreshed
                                                                    by the app without a new IPA
  packages/neo_texture_catalog/ios/Resources/manifest.json.gz       copy bundled in the app

A pack is "available" (one-tap download) only when its verification record
says ok: the author's file was downloaded, is a ZIP or 7z (never a web
page), and the app's own installer put real textures into the engine's
layout. Its size and SHA-256 are the ones measured; nothing is re-hosted.
A pack whose author does not publish a file the app can fetch is "manual"
(page link). A pack whose verification failed is listed as manual with the
reason, or left out when its file is gone.

A pack published on a file host (download.verify in its source) normally
stays a page link. When CI fetched the author's file and installed it with
the app's code, download.verified also lets the app import that exact file.
Explicitly reviewed download.in_app sources may instead use the existing
HTTPS downloader: only stable original file URLs are emitted, including
GameBanana's download endpoint and Dropbox's documented dl=1 shared link.
Other providers and RAR use an additional native capability descriptor;
older clients retain the manual fallback. Raw CI records and their original
source URLs are never rewritten for promotion.

  python3 tools/textures/build_catalogue.py            writes both copies
  python3 tools/textures/build_catalogue.py --check    fails when they are stale
  python3 tools/textures/build_catalogue.py --inventory docs/...md   also writes the inventory table
"""
import argparse
import base64
import gzip
import hashlib
import io
import json
import re
import sys
import urllib.parse
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SOURCES = HERE / 'sources'
VERIFIED = HERE / 'verified.jsonl'
HOSTED = ROOT / 'native/textures/catalogue/manifest.json.gz'
BUNDLED = ROOT / 'packages/neo_texture_catalog/ios/Resources/manifest.json.gz'
CONSOLES = ['ps2', 'gc', 'wii', 'psp', '3ds', 'n64', 'ps1', 'nes']
ENGINE = {'ps2': 'armsx2', 'gc': 'dolphin', 'wii': 'dolphin', 'psp': 'ppsspp', '3ds': 'azahar', 'n64': 'mupen64plus',
          'ps1': 'beetle', 'nes': 'mesen'}
KEEP = ('id', 'system', 'systems', 'engine', 'title', 'version', 'games', 'authors', 'page_url', 'source_id',
        'licence', 'credits', 'requirements', 'notes')
# Verification problems that leave a usable page for the user (the file exists but
# the installers cannot take it as published): listed as manual with the reason.
MANUAL_REASONS = {
    'method:14': 'Its ZIP entries are compressed with LZMA (method 14), which the installers do not read: '
                 'extract it on a computer and import the folder.',
    'rar': 'This historical verification did not install its RAR archive. It stays unavailable until '
           'a new verification with the current archive reader succeeds; external extraction and folder import remain possible.',
}


def fail(message):
    print('FAIL', message)
    raise SystemExit(1)


def folder_id(engine, identity):
    if engine == 'beetle':
        return 'Game-texture-replacements'  # named after the loaded file in the app (verify_packs.folder_for)
    if engine == 'mupen64plus':
        return bytes.fromhex(identity['value']).decode('ascii')  # the ROM header name, in hexadecimal
    if engine == 'mesen':
        return 'Game'  # named after the loaded ROM file in the app (verify_packs.folder_for)
    value = identity['value'].upper()
    if engine == 'ppsspp':
        return value.replace('-', '')
    return value


def formats_of(engine, installed, checks):
    """The texture formats the pack installs, as the page shows them."""
    out = set()
    for folder in installed:
        for name, count in (folder.get('formats') or {}).items():
            if not int(count):
                continue
            name = name.lower()
            if name.startswith('dds'):
                out.add('dds-uncompressed' if name in ('ddsrgba', 'ddsuncompressed') else 'dds')
            elif name in ('png', 'ktx2', 'zim', 'astc', 'ktx', 'bmp'):
                out.add(name)
            elif name == 'dds':
                out.add('dds')
    # Dolphin, PPSSPP: the checker read each DDS header; only block formats need GPU support.
    for report in (checks or {}).values():
        kinds = report.get('dds') if isinstance(report.get('dds'), dict) else None
        if kinds is not None and 'dds' in out:
            if kinds and all(kind == 'rgba' for kind in kinds):
                out.discard('dds')
                out.add('dds-uncompressed')
    return sorted(out)


def source_name(entry):
    source = entry['source_id']
    if source.startswith('github:'):
        return source[len('github:'):], 'https://github.com/' + source[len('github:'):]
    # A creator's own page (forum profile) names the source better than one of its packs.
    return source.split(':', 1)[-1], entry.get('source_url') or entry['page_url']


def hosted_in_app_download(entry, record):
    """A reviewed stable original URL, with a provider only when a resolver is needed.

    Keep the stable creator URL in the source/CI observation, not a temporary
    CDN redirect. The size/SHA-256 still come only from the successful native
    archive verification. Dropbox's dl=1 switch is its documented download
    action; this does not remove access restrictions or bypass a quota.
    """
    download = entry.get('download') or {}
    if not download.get('in_app'):
        return None
    url = (download.get('verify') or {}).get('url') or ''
    try:
        parts = urllib.parse.urlsplit(url)
        valid_port = parts.port in (None, 443)
    except ValueError:
        fail(f'{entry["id"]}: malformed in-app host URL')
    host, provider = (parts.hostname or '').lower(), record.get('host')
    allowed = len(url) <= 2048 and parts.scheme == 'https' and not parts.username and not parts.password and valid_port
    if provider != 'mega':
        allowed = allowed and not parts.fragment
    if provider == 'gamebanana':
        allowed = allowed and host in ('gamebanana.com', 'www.gamebanana.com') and bool(re.fullmatch(r'/dl/[0-9]+/?', parts.path))
    elif provider == 'dropbox':
        allowed = allowed and host in ('www.dropbox.com', 'dropbox.com', 'dl.dropbox.com', 'dl.dropboxusercontent.com') and \
            bool(re.match(r'^/(?:s/[^/]+/|scl/fi/[^/]+/)', parts.path))
        if allowed:
            query = [(key, value) for key, value in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
                     if key not in ('dl', 'raw')]
            query.append(('dl', '1'))
            url = urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query)))
    elif provider == 'direct':
        allowed = allowed and (
            (host == 'archive.org' and bool(re.match(r'^/download/[^/]+/.+', parts.path))) or
            (host == 'pixeldrain.com' and bool(re.fullmatch(r'/api/file/[A-Za-z0-9]+', parts.path))) or
            (host == 'forums.ppsspp.org' and parts.path == '/attachment.php' and
             bool(re.fullmatch(r'[0-9]+', dict(urllib.parse.parse_qsl(parts.query)).get('aid', '')))) or
            (host == 'github.com' and bool(re.match(r'^/[^/]+/[^/]+/releases/download/[^/]+/.+', parts.path)))
        )
    elif provider == 'gdrive':
        # A creator may copy Drive's account-context alias. The same public
        # file is requested anonymously at /uc; keep its query and CI URL.
        if host == 'drive.google.com' and re.fullmatch(r'/u/[0-9]+/uc', parts.path):
            parts = parts._replace(path='/uc')
            url = urllib.parse.urlunsplit(parts)
        file_path = bool(re.fullmatch(r'/file/d/[A-Za-z0-9_-]{10,200}/?(?:view|edit)?/?', parts.path))
        query = dict(urllib.parse.parse_qsl(parts.query))
        query_id = query.get('id', '')
        key_ok = not query.get('resourcekey') or bool(re.fullmatch(r'[A-Za-z0-9_-]{1,256}', query['resourcekey']))
        id_path = parts.path in ('/uc', '/open', '/download') and bool(re.fullmatch(r'[A-Za-z0-9_-]{10,200}', query_id))
        allowed = allowed and host in ('drive.google.com', 'docs.google.com', 'drive.usercontent.google.com') and key_ok and (file_path or id_path)
    elif provider == 'mega':
        file_link = bool(re.fullmatch(r'/file/[A-Za-z0-9_-]{8}', parts.path) and
                         re.fullmatch(r'[A-Za-z0-9_-]{43}', parts.fragment))
        folder_file = bool(re.fullmatch(r'/folder/[A-Za-z0-9_-]{8}', parts.path) and
                           re.fullmatch(r'[A-Za-z0-9_-]{22}/file/[A-Za-z0-9_-]{8}', parts.fragment))
        old_file = parts.path in ('', '/') and bool(re.fullmatch(r'![A-Za-z0-9_-]{8}![A-Za-z0-9_-]{43}', parts.fragment))
        old_folder_file = parts.path in ('', '/') and bool(re.fullmatch(r'F![A-Za-z0-9_-]{8}![A-Za-z0-9_-]{22}![A-Za-z0-9_-]{8}', parts.fragment))
        key = (parts.fragment.split('/')[0] if file_link or folder_file else
               parts.fragment.split('!')[2] if old_file or old_folder_file else '')
        try:
            raw_key = base64.urlsafe_b64decode(key + '=' * (-len(key) % 4))
            canonical_key = base64.urlsafe_b64encode(raw_key).decode().rstrip('=')
            key_ok = len(raw_key) == (16 if folder_file or old_folder_file else 32) and canonical_key == key
        except ValueError:
            key_ok = False
        allowed = allowed and host in ('mega.nz', 'www.mega.nz', 'mega.co.nz', 'www.mega.co.nz') and \
            len(url) <= 512 and not parts.query and key_ok and (file_link or folder_file or old_file or old_folder_file)
    elif provider == 'yandex':
        allowed = allowed and host in ('disk.yandex.ru', 'disk.yandex.com', 'yadi.sk') and \
            not parts.query and bool(re.fullmatch(r'/d/[A-Za-z0-9_-]+/?', parts.path))
    else:
        allowed = False
    if not allowed:
        fail(f'{entry["id"]}: in-app host URL is not a reviewed stable original download')
    return {'url': url, **({'provider': provider} if provider in ('gdrive', 'mega', 'yandex') else {})}


def load():
    entries = []
    for console in CONSOLES:
        if console == 'wii':
            continue  # dolphin.json holds both GameCube and Wii
        name = console if console != 'gc' else 'dolphin'
        # <console>.json, then the imported lists (<console>-<origin>.json, e.g. ps2-ps2ktxpak.json).
        for path in [path for path in [SOURCES / f'{name}.json'] if path.exists()] + sorted(SOURCES.glob(f'{name}-*.json')):
            for entry in json.loads(path.read_text(encoding='utf-8')):
                entries.append(entry)
    seen = set()
    for entry in entries:
        if entry['id'] in seen:
            fail(f'duplicate pack id {entry["id"]}')
        seen.add(entry['id'])
        if ENGINE.get(entry['system']) != entry['engine']:
            fail(f'{entry["id"]}: engine {entry["engine"]} does not run {entry["system"]}')
    records = {}
    if VERIFIED.exists():
        for line in VERIFIED.read_text(encoding='utf-8').splitlines():
            if line.strip():
                record = json.loads(line)
                records[record['id']] = record
    return entries, records


def build(entries, records):
    packs, excluded, pending = [], [], []
    digests = {}
    for entry in entries:
        download = entry.get('download') or {}
        pack = {key: entry[key] for key in KEEP if key in entry}
        hosted = bool((download.get('verify') or {}).get('url')) and not download.get('automatable')
        if not download.get('automatable') and not hosted:
            pack['availability'] = 'manual'
            pack['download'] = {'automatable': False}
            packs.append(pack)
            continue
        record = records.get(entry['id'])
        if hosted and (not record or record.get('status') != 'ok'):
            # Not (yet) verified, or its host refused CI (quota, sign-in): a page link like any manual pack.
            pack['availability'] = 'manual'
            pack['download'] = {'automatable': False}
            packs.append(pack)
            if record:
                excluded.append((entry, record))
            continue
        if not record:
            pending.append(entry['id'])
            continue
        status = record.get('status')
        if status != 'ok':
            reason = next((text for key, text in MANUAL_REASONS.items()
                           if key in json.dumps(record) and status in ('install', 'unsupportedArchive')), None)
            if reason:
                pack['availability'] = 'manual'
                pack['download'] = {'automatable': False}
                pack['notes'] = ((pack.get('notes') or '') + ' ' + reason).strip()
                packs.append(pack)
            excluded.append((entry, record))
            continue
        # A confirmed import of another disc proves extraction only. Explicit
        # serial evidence requires verification for the correct target first.
        plan = record.get('plan') or {}
        if entry['engine'] == 'armsx2' and plan.get('match') == 'otherSerial' and plan.get('serials'):
            fail(f'{entry["id"]}: archive identifies another disc ({plan["serials"]}); '
                 'review the game identities and verify the corrected target before publication')
        parts = record['parts']
        expected = [download['verify']] if hosted else download['parts']
        if len(parts) != len(expected) or any(a['url'] != b['url'] for a, b in zip(parts, expected)):
            fail(f'{entry["id"]}: verification record names other files')
        host_download = hosted_in_app_download(entry, record) if hosted else None
        if hosted and not host_download:
            name = download.get('file_name') or record.get('file_name') or f'{entry["id"]}.{record["format"]}'
            spec = {'automatable': False, 'verified': {'format': record['format'], 'file_name': name[:200],
                                                       'size': parts[0]['size'], 'sha256': parts[0]['sha256'], 'host': record.get('host', '')}}
        else:
            spec = {'automatable': True, 'format': record['format'],
                    'file_name': download.get('file_name') or (record.get('file_name') if host_download else None) or parts[0]['url'].rsplit('/', 1)[-1],
                    'parts': [{**(host_download or {'url': p['url']}), 'size': p['size'], 'sha256': p['sha256']} for p in parts]}
        if len(parts) > 1:
            spec['size'] = record['size']
            spec['sha256'] = record['sha256']
        if download.get('repository'):
            spec['repository'] = download['repository']
        # Older apps must keep a truthful manual action for a provider requiring
        # a native resolver or for RAR. New clients validate and expand in_app;
        # legacy clients retain the verified-file import/page fallback. The
        # existing ZIP/7z HTTPS path remains directly available to every build.
        if spec.get('automatable') and (record['format'] == 'rar' or (host_download or {}).get('provider')):
            name = spec['file_name'][:200]
            spec = {'automatable': False,
                    'verified': {'format': record['format'], 'file_name': name,
                                 'size': spec.get('size') or parts[0]['size'],
                                 'sha256': spec.get('sha256') or parts[0]['sha256'], 'host': record.get('host', 'direct')},
                    'in_app': {**spec, 'file_name': name}}
        # Identical packs (same file, same folders installed) are merged; variants
        # installing other folders of one archive (button styles...) are kept.
        digest = ((spec.get('in_app') or spec).get('sha256') or parts[0]['sha256'],
                  json.dumps([[f['from'], sorted(f.get('exclude') or [])] for f in record['installed']]))
        if digest in digests:
            fail(f'{entry["id"]} and {digests[digest]} install the same files of the same download: merge them')
        digests[digest] = entry['id']
        first = folder_id(entry['engine'], entry['games'][0]['identities'][0])
        folders = []
        for installed in record['installed']:
            target = installed['to']
            declared = next((f for f in (entry.get('install') or {}).get('folders', []) if f['from'] == installed['from']), None)
            if declared:
                target = declared['to']
            elif entry['engine'] == 'beetle':
                target = '{id}'  # Beetle: <content name>-texture-replacements of the game it is installed for
            elif target == first and len({folder_id(entry['engine'], g['identities'][0]) for g in entry['games']}) > 1:
                target = '{id}'  # detected for the first game; the pack serves each listed game
            folder = {'from': installed['from'], 'to': target}
            if installed.get('exclude'):
                folder['exclude'] = installed['exclude']
            folders.append(folder)
        files = sum(int(f['files']) for f in record['installed'])
        size = sum(int(f['bytes']) for f in record['installed'])
        if not files:
            fail(f'{entry["id"]}: verified without files')
        notes = [pack['notes']] if pack.get('notes') else []
        for report in (record.get('checks') or {}).values():
            # PPSSPP reads textures.ini paths as written; iOS storage is case-sensitive.
            if report.get('caseMismatches'):
                notes.append(f'{report["caseMismatches"]} of its textures.ini entries differ from their file only in letter case '
                             'and are not loaded on iOS.')
            if report.get('ddsIgnored'):
                notes.append('Its DDS files are ignored by Azahar without a pack.json.')
        if notes:
            pack['notes'] = ' '.join(notes)
        pack['availability'] = 'available' if spec.get('automatable') else 'manual'
        pack['download'] = spec
        pack['install'] = {'files': files, 'bytes': size, 'folders': folders,
                           'formats': formats_of(entry['engine'], record['installed'], record.get('checks'))}
        pack['verified_at'] = record['verified_at']
        packs.append(pack)
    packs.sort(key=lambda p: (CONSOLES.index(p['system']), p['games'][0]['title'].lower(), p['title'].lower(), p['id']))
    sources = {}
    source_urls = {entry['id']: entry.get('source_url') for entry in entries if entry.get('source_url')}
    for pack in packs:
        name, url = source_name({**pack, 'source_url': source_urls.get(pack['id'])})
        source = sources.setdefault(pack['source_id'], {'id': pack['source_id'], 'name': name, 'url': url,
                                                         'licence': pack['licence']['summary'], 'systems': set()})
        for system in pack.get('systems') or [pack['system']]:
            source['systems'].add(system)
    source_list = [{**s, 'systems': sorted(s['systems'], key=CONSOLES.index)} for s in sorted(sources.values(), key=lambda s: s['name'].lower())]
    body = {'packs': packs, 'sources': source_list}
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    dates = sorted({p['verified_at'] for p in packs if p.get('verified_at')})
    index = {'catalogue_id': 'neostation-hd-textures', 'schema_version': 1,
             'revision': f'{dates[-1] if dates else "unverified"}.{digest[:12]}',
             'generated_at': dates[-1] if dates else '', **body}
    return index, excluded, pending


def serialize(index):
    data = json.dumps(index, ensure_ascii=False, indent=None, separators=(',', ':'), sort_keys=False).encode('utf-8')
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode='wb', compresslevel=9, mtime=0, filename='') as out:
        out.write(data)
    return data, buffer.getvalue()


def validate(index):
    """The same rules as NeoTextureCatalog +validatedIndex: a pack the app would reject fails here."""
    https = re.compile(r'^https://[^\s]+$')
    sha = re.compile(r'^[0-9a-f]{64}$')
    token = re.compile(r'^[A-Za-z0-9._-]{1,120}$')
    for pack in index['packs']:
        where = pack['id']
        if not token.match(pack['id']) or pack['id'] in ('.', '..'):
            fail(f'{where}: id')
        if not pack.get('version') or len(pack['version']) > 64 or not pack.get('title') or len(pack['title']) > 200:
            fail(f'{where}: version/title')
        if not https.match(pack['page_url']) or not pack['authors'] or not pack['games'] or len(pack['games']) > 64:
            fail(f'{where}: page, authors or games')
        if any(not a or len(a) > 120 for a in pack['authors']):
            fail(f'{where}: author')
        if pack.get('systems') and (pack['system'] not in pack['systems'] or any(ENGINE[s] != pack['engine'] for s in pack['systems'])):
            fail(f'{where}: systems')
        for game in pack['games']:
            if not game.get('title') or not game.get('identities') or len(game['identities']) > 16:
                fail(f'{where}: game')
            for identity in game['identities']:
                if not re.match(r'^[A-Za-z0-9._-]{1,40}$', identity['type']) or not re.match(r'^[A-Za-z0-9._-]{1,60}$', identity['scheme']):
                    fail(f'{where}: identity type/scheme')
                if not re.match(r'^[A-Za-z0-9-]{1,40}$', identity['value']):
                    fail(f'{where}: identity value {identity["value"]}')
        download = pack['download']
        verified = download.get('verified')
        if verified is not None:
            if pack['availability'] != 'manual' or download.get('automatable') or verified.get('format') not in ('zip', '7z', 'rar') or \
                    not sha.match(verified.get('sha256', '')) or not 0 < verified.get('size', 0) <= 64 << 30 or \
                    not 0 < len(verified.get('file_name') or '') <= 200:
                fail(f'{where}: verified file')
        native = download.get('in_app')
        if native is not None:
            if not isinstance(native, dict) or native.get('automatable') is not True or verified is None or \
                    pack['availability'] != 'manual' or native.get('format') != verified['format'] or \
                    native.get('file_name') != verified['file_name']:
                fail(f'{where}: native download capability')
        effective = native if native is not None else download
        if pack['availability'] == 'available' or native is not None:
            if effective['format'] not in ('zip', '7z', 'rar') or not 1 <= len(effective['parts']) <= 16 or \
                    (pack['availability'] == 'available' and effective['format'] == 'rar'):
                fail(f'{where}: download format/parts')
            for part in effective['parts']:
                if not https.match(part['url']) or not sha.match(part['sha256']) or not 0 < part['size'] <= 64 << 30:
                    fail(f'{where}: part')
                provider = part.get('provider')
                if provider is not None:
                    expected = hosted_in_app_download({'id': where, 'download': {'in_app': True, 'verify': {'url': part['url']}}},
                                                      {'host': provider})
                    if expected != {'url': part['url'], 'provider': provider}:
                        fail(f'{where}: native provider')
                    if provider == 'mega' and part['size'] > 16 << 30:
                        fail(f'{where}: native MEGA size')
            if len(effective['parts']) > 1 and (not sha.match(effective['sha256']) or effective['size'] != sum(p['size'] for p in effective['parts'])):
                fail(f'{where}: joined parts')
            if len(effective['parts']) == 1 and (('size' in effective and effective['size'] != effective['parts'][0]['size']) or
                                               ('sha256' in effective and effective['sha256'] != effective['parts'][0]['sha256'])):
                fail(f'{where}: conflicting single-part totals')
            if native is not None:
                effective_size = effective.get('size') or effective['parts'][0]['size']
                effective_sha = effective.get('sha256') or effective['parts'][0]['sha256']
                if effective_size != verified['size'] or effective_sha != verified['sha256']:
                    fail(f'{where}: native download differs from verified file')
        if pack['availability'] == 'available' or verified is not None:
            install = pack['install']
            if not 0 < install['files'] <= 2000000 or not 0 < install['bytes'] <= 256 << 30 or not 1 <= len(install['folders']) <= 16:
                fail(f'{where}: install totals')
            targets = set()
            for folder in install['folders']:
                if folder['from'] and not folder['from'].endswith('/'):
                    fail(f'{where}: from {folder["from"]}')
                parts = folder['to'].split('/')
                if not 1 <= len(parts) <= 2 or any(p in ('', '.', '..') for p in parts) or folder['to'].lower() in targets:
                    fail(f'{where}: to {folder["to"]}')
                targets.add(folder['to'].lower())
                for prefix in folder.get('exclude', []):
                    if not prefix.endswith('/'):
                        fail(f'{where}: exclude {prefix}')
    if len(index['packs']) > 5000:
        fail('too many packs')


CONSOLE_NAMES = {'ps2': 'PlayStation 2 (ARMSX2)', 'gc': 'GameCube (Dolphin)', 'wii': 'Wii (Dolphin)',
                 'psp': 'PSP (PPSSPP)', '3ds': 'Nintendo 3DS (Azahar)', 'n64': 'Nintendo 64 (Mupen64Plus-Next, GLideN64)',
                 'ps1': 'PlayStation (Beetle PSX HW, Vulkan)', 'nes': 'NES / Famicom (Mesen)'}


def cell(text):
    return str(text).replace('|', '\\|').replace('\n', ' ')


def inventory(index, excluded, pending, entries):
    """docs/HD_TEXTURE_CATALOG_SOURCES.md: every pack with its author, page,
    terms and verification, then what was reviewed and left out."""
    # excluded.json, then excluded-<origin>.json of other contributors.
    excluded_sources = [item for path in [SOURCES / 'excluded.json', *sorted(SOURCES.glob('excluded-*.json'))]
                        for item in json.loads(path.read_text(encoding='utf-8'))]
    lines = [
        '# HD texture catalogue — sources and credits',
        '',
        f'Generated by `tools/textures/build_catalogue.py` from `tools/textures/sources/` and the verification records '
        f'`tools/textures/verified.jsonl`. Catalogue revision `{index["revision"]}`.',
        '',
        'NeoStation hosts no texture. A pack marked *one tap* is downloaded from its author\'s own link when the user '
        'chooses it, checked against the size and SHA-256 measured here, and installed with the app\'s own installer '
        'into the engine\'s folder for the game. A *manual* pack is only a link to its author\'s page. Authors keep '
        'their rights; "no licence stated" grants nothing. Packs derived from commercial games are for use with the '
        'user\'s own copy.',
        '',
        'Verification (`tools/textures/verify_packs.py`, see `docs/build486-hd-textures-catalogue.md`): the author\'s file '
        'was downloaded, recognised as a ZIP or 7z (never a web page), installed with the production code, and the '
        'installed folder checked as the engine reads it (Dolphin tex1_ names and DDS formats, PPSSPP textures.ini, '
        'Azahar pack.json options and PNG integrity, the Build 485 store for PS2). It does not show that an engine '
        'displays the textures in a game.',
        '',
        'Manual PlayStation 2 entries noted "Listed in ps2ktxpak" are derived from the '
        '[ps2ktxpak catalogue](https://github.com/ps2ktxpak/catalog) (commit `807733e5`), ARMSX2\'s PlayStation 2 '
        'texture pack catalogue: game titles, serials, creators and the creators\' own pages, completed with the PCSX2 '
        'GameIndex (`tools/textures/import_ps2ktxpak.py`). ps2ktxpak is MIT-licensed, Copyright (c) 2026 ps2ktxpak '
        'contributors; its notice is shipped with the catalogue '
        '(`packages/neo_texture_catalog/ios/Resources/ps2ktxpak-LICENSE.txt`). The packs themselves belong to their '
        'creators, under the terms shown on their pages.',
        '',
        'A *manual, verified file* pack uses the author\'s file-host page or exact-file import in older app builds. '
        'The author\'s file was fetched once on CI '
        '(`tools/textures/hosts.py`) and installed with the production code, and the app installs that exact file '
        '(size and SHA-256) when the user imports it from the pack\'s page.',
        '',
        'Explicitly reviewed stable original HTTPS file links, GameBanana download links and Dropbox shared links '
        'using the documented `dl=1` option can use the existing one-tap downloader. These are the creator\'s '
        'original files, not copies hosted by NeoStation; signed temporary CDN links are never published. '
        'Access restrictions, challenges and provider quotas are not bypassed.',
        '',
        'An additional `download.in_app` descriptor is enabled only by app builds implementing its native provider '
        'or RAR reader. Those builds validate its original link, size, SHA-256 and install plan before offering '
        'one-tap installation. Older builds retain the manual fallback. Legacy counts below describe the base '
        'manifest; native-capability counts include these descriptors without counting the same family twice.',
        '',
        '| Console | HTTPS one tap (older builds) | One tap (new native client) | Remaining verified manual | Other manual | Games |',
        '|---|---:|---:|---:|---:|---:|',
    ]
    for console in CONSOLES:
        packs = [p for p in index['packs'] if console in (p.get('systems') or [p['system']])]
        if not packs:
            continue
        available = sum(1 for p in packs if p['availability'] == 'available')
        capable = sum(1 for p in packs if p['download'].get('in_app'))
        verified = sum(1 for p in packs if p['availability'] == 'manual' and p['download'].get('verified') and not p['download'].get('in_app'))
        manual = sum(1 for p in packs if p['availability'] == 'manual') - verified - capable
        games = {i['value'].upper() for p in packs for g in p['games'] for i in g['identities']}
        lines.append(f'| {CONSOLE_NAMES[console]} | {available} | {available + capable} | {verified} | {manual} | {len(games)} |')
    lines += ['', 'A pack serving GameCube discs and Wii Virtual Console titles is counted for both consoles.', '']
    for console in CONSOLES:
        packs = [p for p in index['packs'] if p['system'] == console]
        if not packs:
            continue
        lines += [f'## {CONSOLE_NAMES[console]}', '',
                  '| Pack | Game IDs | Version | Authors | Download | Installed | Formats | Terms | Verified |',
                  '|---|---|---|---|---:|---:|---|---|---|']
        for pack in packs:
            ids = ', '.join(sorted({i['value'] for g in pack['games'] for i in g['identities']}))
            confirm = ' (to confirm)' if any(g.get('confirm') for g in pack['games']) else ''
            title = f'[{cell(pack["title"])}]({pack["page_url"]})'
            if pack['availability'] == 'available':
                size = pack['download'].get('size') or sum(p['size'] for p in pack['download']['parts'])
                download = f'{size / 1e6:,.1f} MB'
                installed = f'{pack["install"]["files"]:,} files, {pack["install"]["bytes"] / 1e6:,.1f} MB'
                formats = ', '.join(pack['install']['formats'])
                verified = pack.get('verified_at', '')
            elif pack['download'].get('verified'):
                file = pack['download']['verified']
                mode = 'one tap with native support' if pack['download'].get('in_app') else 'manual, verified file'
                download = f'{mode} {file["size"] / 1e6:,.1f} MB ({file.get("host") or "file host"})'
                installed = f'{pack["install"]["files"]:,} files, {pack["install"]["bytes"] / 1e6:,.1f} MB'
                formats = ', '.join(pack['install']['formats'])
                verified = pack.get('verified_at', '')
            else:
                download, installed, formats, verified = 'manual', '—', '—', '—'
            lines.append(f'| {title} | {ids}{confirm} | {cell(pack["version"])} | {cell(", ".join(pack["authors"]))} | {download} | '
                         f'{installed} | {formats} | {cell(pack["licence"]["summary"])} | {verified} |')
        credited = [p for p in packs if p.get('credits')]
        if credited:
            lines += ['', 'Credits stated by the packs:', '']
            lines += [f'- {cell(p["title"])}: {cell(p["credits"])}' for p in credited]
        lines.append('')
    if excluded:
        lines += ['## Verification failures', '', '| Pack | Result |', '|---|---|']
        for entry, record in excluded:
            detail = record.get('problems') or record.get('problem') or record.get('error') or (record.get('output') or '').strip().splitlines()[-1:]
            lines.append(f'| {cell(entry["title"])} (`{entry["id"]}`) | {record.get("status")}: {cell(json.dumps(detail))[:200]} |')
        lines.append('')
    if pending:
        lines += ['## Not yet verified', '',
                  'Published as repository archives, verified by the `repositories` job of `.github/workflows/hd-textures.yml`; '
                  'left out of this revision until their record is in `tools/textures/verified.jsonl`:', '',
                  ', '.join(f'`{p}`' for p in pending), '']
    lines += ['## Reviewed and left out', '', '| Console | Source | Reason |', '|---|---|---|']
    for item in excluded_sources:
        lines.append(f'| {item["console"]} | {cell(item["source"])} | {cell(item["reason"])} |')
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--inventory', help='also write the source inventory (docs/HD_TEXTURE_CATALOG_SOURCES.md)')
    parser.add_argument('--allow-pending', action='store_true', help='leave unverified automatable packs out instead of failing')
    args = parser.parse_args()
    entries, records = load()
    index, excluded, pending = build(entries, records)
    if pending and not args.allow_pending:
        fail('unverified automatable packs: ' + ', '.join(pending))
    validate(index)
    data, compressed = serialize(index)
    if len(data) > 16 << 20 or len(compressed) > 4 << 20:
        fail('index too large for the app')
    counts = Counter(p['system'] for p in index['packs'])
    if args.check:
        stale = [str(p.relative_to(ROOT)) for p in (HOSTED, BUNDLED) if not p.exists() or p.read_bytes() != compressed]
        if stale:
            fail('stale catalogue (run tools/textures/build_catalogue.py): ' + ', '.join(stale))
        print(f'PASS HD texture catalogue {index["revision"]}: {len(index["packs"])} packs {dict(counts)}, '
              f'{len(index["sources"])} sources, {len(compressed)} bytes compressed')
        return
    for path in (HOSTED, BUNDLED):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(compressed)
    if args.inventory:
        Path(args.inventory).write_text(inventory(index, excluded, pending, entries), encoding='utf-8')
    print(f'Wrote {index["revision"]}: {len(index["packs"])} packs {dict(counts)}, {len(index["sources"])} sources, '
          f'{len(compressed)} bytes; excluded {len(excluded)}, pending {len(pending)}')


if __name__ == '__main__':
    main()
