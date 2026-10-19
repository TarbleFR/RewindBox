#!/usr/bin/env python3
"""Fetches one file an author published on a file host, for verification on CI.

The catalogue never downloads from these hosts in the app (Build 486 rule: a
pack published on MEGA, Google Drive, MediaFire, Dropbox or GameBanana is a
manual link). CI downloads the author's file once, from the link the author
posted, to measure its size and SHA-256 and to install it with the app's own
installer; the app then accepts that exact file when the user imports it.

Supported, all public links without an account:
  direct        GitHub release assets, archive.org files (an item's /details/ page is
                listed through its public metadata API), any https URL of a file
  gamebanana    https://gamebanana.com/dl/<file id> (the site's own download link)
  mediafire     file pages (/file/<key>/..., /?<key>, /download/<key>/...) and
                folders (the public folder API lists their files)
  gdrive        file links (/file/d/<id>, open?id=, uc?id=) through Google's own
                "download anyway" form; folders through the public embedded view
  dropbox       shared links with dl=1
  mega          public file links with megatools (megatools dl); a folder link is
                reported "folder" and its files are reviewed by hand

Never worked around: a page asking to sign in, a CAPTCHA or bot challenge, a
payment, a transfer quota or rate limit ("Too many users have viewed or
downloaded this file", MEGA's transfer quota, HTTP 429/509). Those end the
attempt with status "protected" or "quota" and the reason.

  python3 tools/textures/hosts.py <url> <destination>     one file, prints a JSON line
"""
import hashlib
import html
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

USER_AGENT = 'Mozilla/5.0 (X11; Linux x86_64) NeoStation-HD-catalogue-verifier/1.0 (+https://github.com/TarbleFR/neostation-ios)'
CHUNK = 4 << 20
CHALLENGE = re.compile(r'(cf-chl|challenge-platform|captcha|hcaptcha|recaptcha|Checking your browser|Enable JavaScript and cookies)', re.I)
QUOTA = re.compile(r'(Too many users have viewed or downloaded|download quota|quota exceeded|Bandwidth limit exceeded|'
                   r'transfer quota|over quota|EOVERQUOTA|rate limit)', re.I)
SIGN_IN = re.compile(r'(accounts\.google\.com/ServiceLogin|Sign in to continue|You need permission|Request access)', re.I)


class HostError(Exception):
    def __init__(self, status, reason):
        super().__init__(f'{status}: {reason}')
        self.status, self.reason = status, reason


def kind(url):
    host = (urllib.parse.urlsplit(url).hostname or '').lower()
    if host.endswith('gamebanana.com'):
        return 'gamebanana'
    if host.endswith('mediafire.com'):
        return 'mediafire'
    if host in ('drive.google.com', 'docs.google.com', 'drive.usercontent.google.com'):
        return 'gdrive'
    if host.endswith('dropbox.com') or host.endswith('dropboxusercontent.com'):
        return 'dropbox'
    if host.endswith('mega.nz') or host.endswith('mega.co.nz') or host.endswith('mega.io'):
        return 'mega'
    if host in ('terabox.com', 'www.terabox.com', '1024terabox.com', 'www.1024terabox.com') or host.endswith('patreon.com'):
        return 'refused'
    return 'direct'


def _open(url, data=None, headers=None):
    request = urllib.request.Request(url, data=data, headers={'User-Agent': USER_AGENT, **(headers or {})})
    try:
        return urllib.request.urlopen(request, timeout=120)
    except urllib.error.HTTPError as error:
        if error.code in (429, 509):
            raise HostError('quota', f'HTTP {error.code}')
        if error.code in (401, 403):
            raise HostError('protected', f'HTTP {error.code}')
        if error.code in (404, 410):
            raise HostError('gone', f'HTTP {error.code}')
        raise


def _page(url):
    with _open(url) as response:
        body = response.read(4 << 20).decode('utf-8', 'replace')
        return body, response.geturl()


def _stream(response, destination, max_bytes):
    digest = hashlib.sha256()
    size = 0
    with open(destination, 'wb') as out:
        while True:
            block = response.read(CHUNK)
            if not block:
                break
            size += len(block)
            if size > max_bytes:
                raise HostError('tooLarge', f'larger than {max_bytes} bytes')
            digest.update(block)
            out.write(block)
    return size, digest.hexdigest()


def _html_reason(path):
    with open(path, 'rb') as handle:
        text = handle.read(1 << 20).decode('utf-8', 'replace')
    if QUOTA.search(text):
        return HostError('quota', QUOTA.search(text).group(0))
    if CHALLENGE.search(text):
        return HostError('protected', 'bot challenge')
    if SIGN_IN.search(text):
        return HostError('protected', 'sign-in or permission page')
    return HostError('html', 'web page instead of a file')


def _looks_html(path):
    with open(path, 'rb') as handle:
        head = handle.read(512).lstrip().lower()
    return head.startswith(b'<!doctype html') or head.startswith(b'<html') or b'<head' in head


def _download_direct(url, destination, max_bytes, referer=None):
    with _open(url, headers={'Referer': referer} if referer else None) as response:
        final = response.geturl()
        disposition = response.headers.get('Content-Disposition', '')
        size, digest = _stream(response, destination, max_bytes)
    if _looks_html(destination):
        raise _html_reason(destination)
    name = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)', disposition)
    return {'size': size, 'sha256': digest, 'final': final,
            'name': urllib.parse.unquote(name.group(1)) if name else urllib.parse.unquote(final.rsplit('/', 1)[-1].split('?')[0])}


# ------------------------------------------------------------------ MediaFire

def mediafire_key(url):
    path = urllib.parse.urlsplit(url)
    for pattern in (r'/(?:file|download|view)/([a-z0-9]+)', r'/file_premium/([a-z0-9]+)'):
        match = re.search(pattern, path.path, re.I)
        if match:
            return match.group(1)
    if path.query and re.fullmatch(r'[a-z0-9]{8,20}', path.query.split('&')[0], re.I):
        return path.query.split('&')[0]
    return None


def mediafire_folder(url):
    match = re.search(r'/folder/([a-z0-9]+)', url, re.I)
    if not match:
        return None
    files = []
    for chunk in range(1, 6):
        api = ('https://www.mediafire.com/api/1.5/folder/get_content.php?response_format=json&content_type=files'
               f'&chunk={chunk}&folder_key={match.group(1)}')
        body, _ = _page(api)
        content = json.loads(body).get('response', {}).get('folder_content', {})
        for item in content.get('files') or []:
            files.append({'name': item.get('filename'), 'size': int(item.get('size') or 0),
                          'url': f"https://www.mediafire.com/file/{item.get('quickkey')}/{urllib.parse.quote(item.get('filename') or '')}/file"})
        if content.get('more_chunks') != 'yes':
            break
    return files


def mediafire(url, destination, max_bytes):
    key = mediafire_key(url)
    if not key:
        raise HostError('unsupported', 'MediaFire link without a file key')
    body, final = _page(f'https://www.mediafire.com/file/{key}/file')
    if CHALLENGE.search(body):
        raise HostError('protected', 'bot challenge')
    match = re.search(r'href="(https://download\d*\.mediafire\.com/[^"]+)"', body)
    if not match:
        if re.search(r'(File Removed|Invalid or Deleted File|has been removed)', body, re.I):
            raise HostError('gone', 'removed from MediaFire')
        raise HostError('html', 'no download link on the MediaFire page')
    return _download_direct(html.unescape(match.group(1)), destination, max_bytes, referer=final)


# --------------------------------------------------------------- Google Drive

def gdrive_id(url):
    for pattern in (r'/file/d/([A-Za-z0-9_-]{10,})', r'[?&]id=([A-Za-z0-9_-]{10,})', r'/uc\?.*id=([A-Za-z0-9_-]{10,})'):
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def gdrive_folder(url):
    match = re.search(r'/folders/([A-Za-z0-9_-]{10,})', url) or (re.search(r'[?&]id=([A-Za-z0-9_-]{10,})', url) if 'folderview' in url else None)
    if not match:
        return None
    body, _ = _page(f'https://drive.google.com/embeddedfolderview?id={match.group(1)}')
    if SIGN_IN.search(body):
        raise HostError('protected', 'private folder')
    files = []
    for entry in re.finditer(r'<a href="(https://drive\.google\.com/file/d/([A-Za-z0-9_-]+)/[^"]*)"[^>]*>.*?'
                             r'class="flip-entry-title">([^<]+)<', body, re.S):
        files.append({'name': html.unescape(entry.group(3)), 'url': f'https://drive.google.com/file/d/{entry.group(2)}/view'})
    for entry in re.finditer(r'<a href="https://drive\.google\.com/drive/folders/([A-Za-z0-9_-]+)"[^>]*>.*?class="flip-entry-title">([^<]+)<', body, re.S):
        files.append({'name': html.unescape(entry.group(2)) + '/', 'url': f'https://drive.google.com/drive/folders/{entry.group(1)}', 'folder': True})
    return files


def gdrive(url, destination, max_bytes):
    file_id = gdrive_id(url)
    if not file_id:
        raise HostError('unsupported', 'Google Drive link without a file id')
    first = f'https://drive.usercontent.google.com/download?id={file_id}&export=download'
    with _open(first) as response:
        size, digest = _stream(response, destination, max_bytes)
        final = response.geturl()
        disposition = response.headers.get('Content-Disposition', '')
    if _looks_html(destination):
        text = Path(destination).read_text('utf-8', 'replace')
        if QUOTA.search(text):
            raise HostError('quota', 'Google Drive download quota')
        if SIGN_IN.search(text) or 'ServiceLogin' in text:
            raise HostError('protected', 'private file')
        # Large files: Google's "can't scan for viruses, download anyway" form (no account, no CAPTCHA).
        form = re.search(r'<form[^>]+id="download-form"[^>]+action="([^"]+)"(.*?)</form>', text, re.S)
        if not form:
            raise HostError('html', 'no Google Drive download form')
        fields = dict(re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)"', form.group(2)))
        action = html.unescape(form.group(1)) + '?' + urllib.parse.urlencode(fields)
        return _download_direct(action, destination, max_bytes)
    name = re.search(r'filename="([^"]+)"', disposition)
    return {'size': size, 'sha256': digest, 'final': final, 'name': name.group(1) if name else file_id}


# -------------------------------------------------------------------- Dropbox

def dropbox(url, destination, max_bytes):
    parts = urllib.parse.urlsplit(url)
    query = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query) if k not in ('dl', 'raw')] + [('dl', '1')]
    return _download_direct(urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query))), destination, max_bytes)


# ----------------------------------------------------------------------- MEGA

def mega_link(url):
    """megatools reads https://mega.nz/file/<id>#<key> and /folder/<id>#<key>, and the old #!id!key forms."""
    url = url.replace('mega.co.nz', 'mega.nz')
    match = re.search(r'#!([A-Za-z0-9_-]+)!([A-Za-z0-9_-]+)', url)
    if match:
        return f'https://mega.nz/file/{match.group(1)}#{match.group(2)}'
    match = re.search(r'#F!([A-Za-z0-9_-]+)!([A-Za-z0-9_-]+)', url)
    if match:
        return f'https://mega.nz/folder/{match.group(1)}#{match.group(2)}'
    return url


def _megatools():
    tool = shutil.which('megatools')
    if not tool:
        raise HostError('unsupported', 'megatools is not installed')
    return tool


def mega(url, destination, max_bytes):
    link = mega_link(url)
    if '/folder/' in link:
        # A shared folder holds several files of unknown size: its files are reviewed one by one, by hand.
        raise HostError('folder', 'MEGA folder link')
    work = Path(destination).parent / ('mega-' + Path(destination).name)
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    started = time.time()
    result = subprocess.run([_megatools(), 'dl', '--no-progress', '--path', str(work), link], capture_output=True, text=True,
                            errors='replace', timeout=4 * 3600)
    text = result.stderr + result.stdout
    files = [p for p in work.rglob('*') if p.is_file()]
    try:
        if result.returncode:
            if QUOTA.search(text) or 'bandwidth' in text.lower():
                raise HostError('quota', 'MEGA transfer quota')
            raise HostError('gone' if 'ENOENT' in text or 'EEXPIRED' in text or 'EBLOCKED' in text else 'error', text.strip()[-200:])
        if len(files) != 1:
            raise HostError('error', f'{len(files)} files downloaded from one MEGA link')
        if files[0].stat().st_size > max_bytes:
            raise HostError('tooLarge', f'larger than {max_bytes} bytes')
        shutil.move(str(files[0]), destination)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    digest = hashlib.sha256()
    with open(destination, 'rb') as handle:
        for block in iter(lambda: handle.read(CHUNK), b''):
            digest.update(block)
    return {'size': Path(destination).stat().st_size, 'sha256': digest.hexdigest(), 'final': link, 'name': files[0].name,
            'seconds': round(time.time() - started, 1)}


# ---------------------------------------------------------------------- entry

def archive_item(url):
    """The files of an archive.org item (its public metadata API), for a /details/<item> link."""
    match = re.search(r'archive\.org/details/([^/?#]+)', url)
    if not match:
        return None
    body, _ = _page(f'https://archive.org/metadata/{match.group(1)}')
    files = []
    for item in json.loads(body).get('files') or []:
        if item.get('source') == 'original' and re.search(r'\.(zip|7z|rar)$', item.get('name') or '', re.I):
            files.append({'name': item['name'], 'size': int(item.get('size') or 0),
                          'url': f"https://archive.org/download/{match.group(1)}/{urllib.parse.quote(item['name'])}"})
    return files


def folder_files(url):
    """The files of a shared MediaFire or Google Drive folder link or of an archive.org item, or None for a file link."""
    host = kind(url)
    if host == 'mediafire':
        return mediafire_folder(url)
    if host == 'gdrive':
        return gdrive_folder(url)
    if 'archive.org/details/' in url:
        return archive_item(url)
    return None


def fetch(url, destination, max_bytes):
    """Downloads the file of url to destination: {'host', 'size', 'sha256', 'final', 'name'}; raises HostError."""
    host = kind(url)
    if host == 'refused':
        raise HostError('protected', 'host requires an account or a payment')
    function = {'mediafire': mediafire, 'gdrive': gdrive, 'dropbox': dropbox}.get(host)
    if host == 'mega':
        result = mega(url, destination, max_bytes)
    elif function:
        result = function(url, destination, max_bytes)
    else:
        result = _download_direct(url, destination, max_bytes)
    result['host'] = host
    return result


if __name__ == '__main__':
    try:
        print(json.dumps(fetch(sys.argv[1], sys.argv[2], 16 << 30)))
    except HostError as error:
        print(json.dumps({'status': error.status, 'reason': error.reason}))
        raise SystemExit(1)
