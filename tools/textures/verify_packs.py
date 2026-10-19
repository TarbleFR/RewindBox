#!/usr/bin/env python3
"""Verifies the HD texture catalogue sources against the authors' real files.

For every automatable pack of a sources file (tools/textures/sources/*.json):
download each part from the author's own URL (streamed, never kept), check it
is an archive and not a web page, record its size and SHA-256 (multi-part:
byte-joined, as the app does), then install it with the app's own code:

  ARMSX2   the Build 485 store pipeline (texture_verify armsx2), after the
           catalogue's own expansion when the pack needs one (7z, a subtree);
  Dolphin, PPSSPP, Azahar
           NeoTextureInstall (texture_verify detect + install), then what each
           engine requires: Dolphin tex1_ names and DDS block formats; PPSSPP
           textures.ini (hash type, [hashes] targets, exact case as iOS
           reads folders); Azahar pack.json (the booleans the engine reads
           without a fallback) and that every PNG decompresses.

One JSON line per pack goes to --out and to stdout (between VERIFY_BEGIN and
VERIFY_END markers, so a CI log is enough to read the results). Nothing is
re-hosted: the files are deleted after each pack.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
import zlib
from pathlib import Path

CHUNK = 4 << 20
sys.path.insert(0, str(Path(__file__).resolve().parent))  # hosts.py


def log(message):
    print(message, flush=True)


def download(url, destination, max_bytes):
    """Streams url to destination; returns (size, sha256, content type)."""
    request = urllib.request.Request(url, headers={'User-Agent': 'NeoStation-catalogue-verifier'})
    digest = hashlib.sha256()
    size = 0
    with urllib.request.urlopen(request, timeout=120) as response, open(destination, 'wb') as out:
        content_type = response.headers.get('Content-Type', '')
        final = response.geturl()
        while True:
            block = response.read(CHUNK)
            if not block:
                break
            size += len(block)
            if size > max_bytes:
                raise RuntimeError(f'larger than {max_bytes} bytes')
            digest.update(block)
            out.write(block)
    return size, digest.hexdigest(), content_type, final


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        while True:
            block = handle.read(CHUNK)
            if not block:
                return digest.hexdigest()
            digest.update(block)


def sniff(path):
    with open(path, 'rb') as handle:
        head = handle.read(512)
    if head.startswith(b'7z\xbc\xaf\x27\x1c'):
        return '7z'
    if head.startswith(b'PK'):
        return 'zip'
    if head.startswith(b'Rar!'):
        return 'rar'
    text = head.lstrip().lower()
    if text.startswith(b'<!doctype html') or text.startswith(b'<html') or b'<head' in text:
        return 'html'
    return 'unknown'


def run(driver, *args):
    result = subprocess.run([driver, *args], capture_output=True, text=True, errors='replace')
    return result.returncode, result.stdout


def key_values(line):
    return dict(part.split('=', 1) for part in line.split() if '=' in part)


def folder_stats(folder):
    files = size = 0
    formats = {}
    for path in Path(folder).rglob('*'):
        if path.is_file() and path.name != 'NeoStation-pack.json':
            files += 1
            size += path.stat().st_size
            extension = path.suffix.lower().lstrip('.')
            formats[extension] = formats.get(extension, 0) + 1
    return files, size, formats


def dds_kind(path):
    with open(path, 'rb') as handle:
        head = handle.read(148)
    if len(head) < 128 or head[:4] != b'DDS ':
        return 'invalid'
    flags, fourcc = struct.unpack_from('<I4s', head, 80)
    if not flags & 4:
        return 'rgba'
    if fourcc == b'DX10' and len(head) >= 132:
        dxgi = struct.unpack_from('<I', head, 128)[0]
        return {71: 'bc1', 74: 'bc2', 77: 'bc3', 80: 'bc4', 83: 'bc5', 95: 'bc6h', 98: 'bc7'}.get(dxgi, f'dxgi{dxgi}')
    return {b'DXT1': 'bc1', b'DXT3': 'bc2', b'DXT5': 'bc3', b'ATI1': 'bc4', b'ATI2': 'bc5'}.get(fourcc, fourcc.decode('latin-1'))


def png_ok(path):
    """The whole PNG decompresses (Azahar does not survive a damaged image)."""
    try:
        with open(path, 'rb') as handle:
            data = handle.read()
        if data[:8] != b'\x89PNG\r\n\x1a\n':
            return False
        offset, idat = 8, bytearray()
        while offset + 8 <= len(data):
            length, kind = struct.unpack_from('>I4s', data, offset)
            chunk = data[offset + 8: offset + 8 + length]
            crc = struct.unpack_from('>I', data, offset + 8 + length)[0]
            if zlib.crc32(kind + chunk) & 0xffffffff != crc:
                return False
            if kind == b'IDAT':
                idat += chunk
            if kind == b'IEND':
                break
            offset += 12 + length
        zlib.decompress(bytes(idat))
        return True
    except Exception:
        return False


def strip_comments(text):
    """pack.json may hold // and /* */ comments (the engine's parser accepts them)."""
    out, i, quoted = [], 0, False
    while i < len(text):
        c = text[i]
        if quoted:
            out.append(c)
            if c == '\\' and i + 1 < len(text):
                out.append(text[i + 1])
                i += 1
            elif c == '"':
                quoted = False
        elif c == '"':
            quoted = True
            out.append(c)
        elif text.startswith('//', i):
            while i < len(text) and text[i] != '\n':
                i += 1
            continue
        elif text.startswith('/*', i):
            end = text.find('*/', i + 2)
            i = len(text) if end < 0 else end + 2
            continue
        else:
            out.append(c)
        i += 1
    return ''.join(out)


def check_dolphin(folder):
    report = {'dds': {}}
    for path in Path(folder).rglob('*.dds'):
        kind = dds_kind(path)
        report['dds'][kind] = report['dds'].get(kind, 0) + 1
    report['tex1'] = sum(1 for path in Path(folder).rglob('tex1_*') if path.is_file())
    return report, [] if report['tex1'] else ['noTextures']


def check_ppsspp(folder):
    problems, report = [], {}
    ini = Path(folder) / 'textures.ini'
    packed = Path(folder) / 'textures.zip'
    archive = None
    if not ini.exists() and packed.exists():
        # TextureReplacer::LoadIni: a textures.zip in the game folder is opened as the
        # folder itself (its textures.ini and textures are read from the archive).
        try:
            archive = zipfile.ZipFile(packed)
            data = archive.read('textures.ini')
        except (zipfile.BadZipFile, KeyError, OSError):
            return report, ['missingIni']
        report['zipped'] = True
    elif ini.exists():
        data = ini.read_bytes()
    else:
        return report, ['missingIni']
    text = data.decode('utf-8', 'replace')
    section, options, hashes = '', {}, []
    for raw in text.splitlines():
        # IniFile::Load: a UTF-8 byte order mark is removed from each line, then CR.
        raw = raw[1:] if raw.startswith('\ufeff') else raw
        raw = raw.rstrip('\r')
        line = raw.split('#', 1)[0].strip() if not raw.startswith('[') else raw.strip()
        if raw.startswith('['):
            section = raw.strip().strip('[]').lower()
            continue
        if '=' not in line:
            continue
        key, value = (part.strip() for part in line.split('=', 1))
        if section == 'options':
            options[key.lower()] = value
        elif section == 'hashes' and value:
            hashes.append(value.replace('\\', '/'))
    report['hash'] = options.get('hash', '')
    if report['hash'].lower() not in ('quick', 'xxh32', 'xxh64'):
        problems.append('iniHash')
    if archive is not None:
        files = {name for name in archive.namelist() if not name.endswith('/')}
    else:
        files = {str(path.relative_to(folder)).replace('\\', '/') for path in Path(folder).rglob('*') if path.is_file()}
    lower = {name.lower() for name in files}
    targets = {name.lstrip('/') for name in hashes if '..' not in name}
    report['hashTargets'] = len(targets)
    report['missingTargets'] = sum(1 for name in targets if name.lower() not in lower)
    # Folders on iOS are case-sensitive: a different case is a texture that never loads.
    report['caseMismatches'] = sum(1 for name in targets if name not in files and name.lower() in lower)
    report['leadingSlash'] = sum(1 for name in hashes if name.startswith('/'))
    report['dds'] = {}
    for path in Path(folder).rglob('*.dds'):
        kind = dds_kind(path)
        report['dds'][kind] = report['dds'].get(kind, 0) + 1
    return report, problems


def check_azahar(folder):
    problems, report = [], {}
    pack = Path(folder) / 'pack.json'
    if pack.exists():
        try:
            options = json.loads(strip_comments(pack.read_text(encoding='utf-8', errors='replace'))).get('options', {})
            report['pack_json'] = {key: options.get(key) for key in ('skip_mipmap', 'flip_png_files', 'use_new_hash')}
            if not all(isinstance(options.get(key), bool) for key in ('skip_mipmap', 'flip_png_files', 'use_new_hash')):
                problems.append('packJsonOptions')
        except Exception as error:
            report['pack_json_error'] = str(error)[:120]
            problems.append('packJsonInvalid')
    else:
        report['pack_json'] = None  # legacy hash; the engine refuses DDS without pack.json
    pngs = list(Path(folder).rglob('*.png'))
    bad = [str(path.relative_to(folder)) for path in pngs if not png_ok(path)]
    report['png'] = len(pngs)
    report['badPng'] = bad[:5]
    if bad:
        problems.append('badPng')
    report['dds'] = sum(1 for _ in Path(folder).rglob('*.dds'))
    if report['dds'] and not pack.exists():
        report['ddsIgnored'] = True
    return report, problems


def check_mupen64plus(folder):
    """GLideNHQ: Rice textures <ROM name>#<crc>#<fmt>#<siz>..., read from hires_texture/<ROM name>."""
    report, problems = {}, []
    name = Path(folder).name
    rice = [path for path in Path(folder).rglob('*') if path.is_file() and path.name[-4:] in ('.png', '.bmp') and '#' in path.name]
    report['rice'] = len(rice)
    report['otherName'] = sum(1 for path in rice if name not in path.name)
    pngs = [path for path in rice if path.name.endswith('.png')]
    bad = [str(path.relative_to(folder)) for path in pngs[:4000] if not png_ok(path)]
    report['pngChecked'] = min(len(pngs), 4000)
    report['badPng'] = bad[:5]
    if not rice:
        problems.append('noTextures')
    if rice and report['otherName'] == len(rice):
        problems.append('otherRomName')
    return report, problems


def check_beetle(folder):
    """Beetle PSX HW (rhi_tt.c): <hash>-<palette>.<png|dds|webp|jpg|bmp|tga> directly in
    <content name>-texture-replacements (no subfolder), the Lazy modes' prefetch.journal."""
    report, problems = {}, []
    pattern = re.compile(r'^[0-9a-f]{1,8}-[0-9a-f]{1,8}\.(png|dds|webp|jpe?g|bmp|tga)$', re.I)
    names = [path for path in Path(folder).iterdir() if path.is_file()]
    textures = [path for path in names if pattern.match(path.name)]
    report['textures'] = len(textures)
    report['subfolders'] = sum(1 for path in Path(folder).iterdir() if path.is_dir())
    pngs = [path for path in textures if path.suffix.lower() == '.png']
    bad = [path.name for path in pngs[:4000] if not png_ok(path)]
    report['pngChecked'] = min(len(pngs), 4000)
    report['badPng'] = bad[:5]
    if not textures:
        problems.append('noTextures')
    if bad:
        problems.append('badPng')
    return report, problems


def verify(entry, driver, work, max_bytes):
    result = {'id': entry['id'], 'system': entry['system'], 'verified_at': time.strftime('%Y-%m-%d', time.gmtime())}
    spec = entry.get('download') or {}
    external = (spec.get('verify') or {}).get('url') if not spec.get('automatable') else None
    if not spec.get('automatable') and not external:
        result['status'] = 'manual'
        return result
    parts = []
    files = []
    started = time.time()
    if external:
        # A manual pack (file host): the author's file is fetched here once; the app
        # only accepts this exact file when the user imports it (hosts.py).
        import hosts
        path = work / 'part-0'
        try:
            fetched = hosts.fetch(external, str(path), max_bytes)
        except hosts.HostError as error:
            result.update(status=error.status, error=error.reason, manual=True)
            return result
        except Exception as error:
            result.update(status='network', error=str(error)[:200], manual=True)
            return result
        parts.append({'url': external, 'size': fetched['size'], 'sha256': fetched['sha256']})
        files.append(path)
        result.update(manual=True, host=fetched['host'], file_name=fetched.get('name') or '')
        if spec['verify'].get('sha256') and spec['verify']['sha256'] != fetched['sha256']:
            result.update(status='changed', parts=parts, expected=spec['verify']['sha256'])
            return result
    try:
        for index, part in enumerate([] if external else spec['parts']):
            path = work / f'part-{index}'
            size, digest, content_type, final = download_file(part['url'], path, max_bytes)
            parts.append({'url': part['url'], 'size': size, 'sha256': digest})
            files.append(path)
            if part.get('sha256') and part['sha256'] != digest:
                result.update(status='changed', parts=parts, expected=part['sha256'])
                return result
            if content_type.lower().startswith('text/html'):
                result.update(status='html', parts=parts)
                return result
    except Exception as error:
        result.update(status='network', error=str(error)[:200], parts=parts)
        return result
    archive = files[0]
    if len(files) > 1:
        archive = work / 'archive'
        with open(archive, 'wb') as out:
            for path in files:
                with open(path, 'rb') as handle:
                    shutil.copyfileobj(handle, out, CHUNK)
                path.unlink()
        result['size'] = archive.stat().st_size
        result['sha256'] = sha256_file(archive)
    result['parts'] = parts
    result['download_seconds'] = round(time.time() - started, 1)
    kind = sniff(archive)
    result['format'] = kind
    if kind not in ('zip', '7z'):
        result['status'] = 'unsupportedArchive'
        return result
    engine = entry['engine']
    first = entry['games'][0]['identities'][0]['value']
    if engine == 'armsx2':
        return verify_armsx2(entry, result, driver, work, archive, kind)
    current = folder_for(engine, first)
    folders = (entry.get('install') or {}).get('folders')
    if folders:
        rules = [(folder['from'], folder['to'].replace('{id}', current), folder.get('exclude', [])) for folder in folders]
        result['layout'] = 'declared'
    else:
        code, output = run(driver, 'detect', engine, current, str(archive))
        rules = [(*line[5:].split('\t', 1), []) for line in output.splitlines() if line.startswith('rule=')]
        problem = next((line[8:] for line in output.splitlines() if line.startswith('problem=')), '')
        other = any(line == 'other=1' for line in output.splitlines())
        if problem or not rules:
            result.update(status='layout', problem=problem or 'noRules', detect=output[-400:])
            return result
        result['layout'] = 'detected'
        result['other_region'] = other
    root = work / 'root'
    code, output = run(driver, 'install', engine, str(root), str(archive),
                       *[f'{a}={b}' + ('!' + '|'.join(excluded) if excluded else '') for a, b, excluded in rules])
    if code:
        result.update(status='install', output=output[-400:])
        return result
    installed = []
    problems = []
    report = {}
    for source, target, excluded in rules:
        folder = root / target
        count, size, formats = folder_stats(folder)
        installed.append({'from': source, 'to': target, 'exclude': excluded, 'files': count, 'bytes': size, 'formats': formats})
        checker = {'dolphin': check_dolphin, 'ppsspp': check_ppsspp, 'azahar': check_azahar, 'mupen64plus': check_mupen64plus,
                   'beetle': check_beetle}[engine]
        folder_report, folder_problems = checker(folder)
        report[target] = folder_report
        problems += folder_problems
    result['installed'] = installed
    result['checks'] = report
    result['status'] = 'failed' if problems else 'ok'
    if problems:
        result['problems'] = sorted(set(problems))
    return result


def download_file(url, path, max_bytes):
    last = None
    for attempt in range(3):
        try:
            return download(url, path, max_bytes)
        except Exception as error:  # transient network errors are retried
            last = error
            time.sleep(5 * (attempt + 1))
    raise last


def folder_for(engine, value):
    if engine == 'beetle':
        # Beetle names the folder after the loaded file; any game file name will do here.
        return 'Game-texture-replacements'
    if engine == 'mupen64plus':
        # The catalogue writes the N64 ROM header name in hexadecimal; GLideN64 names the folder after the name.
        return bytes.fromhex(value).decode('ascii')
    value = value.upper()
    if engine == 'ppsspp':
        return value.replace('-', '')
    return value


def verify_armsx2(entry, result, driver, work, archive, kind):
    folders = (entry.get('install') or {}).get('folders') or [{'from': '', 'to': ''}]
    source_from = folders[0]['from']
    excluded = folders[0].get('exclude') or []
    serial = entry['games'][0]['identities'][0]['value'].upper()
    if len(serial) == 9:
        serial = serial[:4] + '-' + serial[4:]
    name = (entry.get('download') or {}).get('file_name') or entry['id']
    data = work / 'armsx2'
    source, move = str(archive), []
    if kind != 'zip' or source_from or excluded:
        # The catalogue's own expansion on the engine's volume, then the store moves the files.
        code, output = run(driver, 'install', 'armsx2', str(data / 'textures'), str(archive), 'flat',
                           source_from + ('!' + '|'.join(excluded) if excluded else ''))
        line = next((line for line in output.splitlines() if line.startswith('result=')), '')
        values = key_values(line)
        if code or values.get('result') != 'expanded':
            result.update(status='install', output=output[-400:])
            return result
        source, move = values['folder'], ['move']
        result['expanded'] = {'files': int(values['files']), 'bytes': int(values['bytes'])}
    code, output = run(driver, 'armsx2', str(data), source, serial, name, *move)
    plan = key_values(next((line for line in output.splitlines() if line.startswith('plan ')), ''))
    installed = key_values(next((line for line in output.splitlines() if line.startswith('result=')), ''))
    result['plan'] = {key: plan.get(key, '') for key in ('files', 'bytes', 'error', 'match', 'pack', 'regionConflict', 'serials', 'excluded', 'skipped')}
    if code or installed.get('result') != 'installed':
        result.update(status='install', output=output[-600:])
        return result
    result['installed'] = [{'from': source_from, 'to': f'{serial}/replacements', 'files': int(installed['files']),
                            'bytes': int(installed['bytes']), 'unsupported': int(installed['unsupported']),
                            'formats': dict(item.split(':') for item in installed['formats'].strip(',').split(',') if item)}]
    result['status'] = 'ok'
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sources', required=True, nargs='+')
    parser.add_argument('--driver', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--only', default='')
    parser.add_argument('--max-gb', type=float, default=12)
    # repository: only packs downloaded as a GitHub repository archive (codeload);
    # release: every other automatable pack; host: manual packs whose file is on a
    # file host (download.verify, hosts.py).
    parser.add_argument('--kind', choices=['all', 'repository', 'release', 'host'], default='all')
    parser.add_argument('--resume', action='store_true', help='keep the results already in --out, verify the others')
    parser.add_argument('--work', default=None, help='folder for the temporary downloads')
    parser.add_argument('--skip-recorded', default=None,
                        help='skip the packs that already have a record in this file (tools/textures/verified.jsonl): a '
                             'record is kept as it was produced, success or failure; --only re-verifies a given pack')
    args = parser.parse_args()
    only = {item for item in args.only.split(',') if item}
    entries = []
    for path in args.sources:
        entries += json.loads(Path(path).read_text(encoding='utf-8'))
    done = {}
    if args.resume and Path(args.out).exists():
        for line in Path(args.out).read_text(encoding='utf-8').splitlines():
            if line.strip():
                record = json.loads(line)
                if record.get('status') in ('ok', 'failed', 'manual', 'layout', 'install', 'unsupportedArchive', 'html', 'changed'):
                    done[record['id']] = line
    recorded = set()
    if args.skip_recorded and Path(args.skip_recorded).exists():
        for line in Path(args.skip_recorded).read_text(encoding='utf-8').splitlines():
            if line.strip():
                recorded.add(json.loads(line)['id'])
    log('VERIFY_BEGIN')
    with open(args.out, 'w', encoding='utf-8') as out:
        for entry in entries:
            if only and entry['id'] not in only:
                continue
            repository = bool((entry.get('download') or {}).get('repository'))
            hosted = bool(((entry.get('download') or {}).get('verify') or {}).get('url'))
            if ((args.kind == 'repository' and not repository) or (args.kind == 'release' and (repository or hosted))
                    or (args.kind == 'host' and not hosted)):
                continue
            if entry['id'] in recorded and not only:
                continue
            if entry['id'] in done:
                out.write(done[entry['id']] + '\n')
                continue
            work = Path(tempfile.mkdtemp(prefix='hdtex-', dir=args.work))
            try:
                result = verify(entry, args.driver, work, int(args.max_gb * (1 << 30)))
            except Exception as error:
                result = {'id': entry['id'], 'system': entry['system'], 'status': 'error', 'error': repr(error)[:300]}
            finally:
                shutil.rmtree(work, ignore_errors=True)
            line = json.dumps(result, sort_keys=True, separators=(',', ':'))
            out.write(line + '\n')
            out.flush()
            log('VERIFY ' + line)
    log('VERIFY_END')


if __name__ == '__main__':
    main()
