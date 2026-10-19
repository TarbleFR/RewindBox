#!/usr/bin/env python3
"""The CI checks of tools/textures (verify_packs.py, hosts.py) on synthetic inputs.

- PPSSPP: textures.ini at the game folder's root, or inside a textures.zip there
  (TextureReplacer reads the archive as the folder); missing ini; [hashes]
  targets missing or differing only in letter case (iOS storage is case-sensitive).
- MEGA public folders: node keys decrypted with the folder key, file keys
  derived from their two halves, attributes AES-CBC, files AES-CTR, exactly as
  MEGA's web client encrypts them (a node encrypted here is read back).
"""
from pathlib import Path
import base64
import json
import os
import struct
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/textures'))
import hosts  # noqa: E402
import verify_packs  # noqa: E402

checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit(f'FAIL {message}')


INI = '[options]\nhash = quick\n[hashes]\n0000000012345678 = new/a.png\n0000000012345679 = New/B.png\n0000000012345670 = gone.png\n'
with tempfile.TemporaryDirectory() as folder:
    game = Path(folder)
    (game / 'new').mkdir()
    (game / 'new/a.png').write_bytes(b'\x89PNG')
    (game / 'new/b.png').write_bytes(b'\x89PNG')
    (game / 'textures.ini').write_text(INI)
    report, problems = verify_packs.check_ppsspp(game)
    check(not problems and report['hash'] == 'quick' and report['hashTargets'] == 3, f'loose ini {report} {problems}')
    check(report['missingTargets'] == 1 and report['caseMismatches'] == 1 and 'zipped' not in report, f'loose targets {report}')
    (game / 'textures.ini').unlink()
    for name in ('new/a.png', 'new/b.png'):
        (game / name).unlink()
    report, problems = verify_packs.check_ppsspp(game)
    check(problems == ['missingIni'], f'no ini {problems}')
    with zipfile.ZipFile(game / 'textures.zip', 'w') as archive:
        archive.writestr('textures.ini', INI)
        archive.writestr('new/a.png', b'\x89PNG')
        archive.writestr('new/b.png', b'\x89PNG')
    report, problems = verify_packs.check_ppsspp(game)
    check(not problems and report.get('zipped') and report['hashTargets'] == 3, f'zipped ini {report} {problems}')
    check(report['missingTargets'] == 1 and report['caseMismatches'] == 1, f'zipped targets {report}')
    with zipfile.ZipFile(game / 'textures.zip', 'w') as archive:
        archive.writestr('readme.txt', 'no ini')
    check(verify_packs.check_ppsspp(game)[1] == ['missingIni'], 'a textures.zip without textures.ini')
    (game / 'textures.zip').write_bytes(b'not a zip')
    check(verify_packs.check_ppsspp(game)[1] == ['missingIni'], 'a damaged textures.zip')
    (game / 'textures.ini').write_text('[options]\nhash = md5\n')
    check(verify_packs.check_ppsspp(game)[1] == ['iniHash'], 'a loose ini wins over textures.zip and its hash is checked')

# MEGA public folder: encrypt a folder node and a file node as the web client does.
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes  # noqa: E402


def encrypt(key, mode, data):
    return Cipher(algorithms.AES(key), mode).encryptor().update(data)


def b64(data):
    return base64.urlsafe_b64encode(data).decode().rstrip('=')


def attributes(key, name):
    plain = b'MEGA' + json.dumps({'n': name}).encode()
    return b64(encrypt(key, modes.CBC(bytes(16)), plain + b'\0' * (-len(plain) % 16)))


folder_key, inner_key = os.urandom(16), os.urandom(16)
file_key, nonce, mac = os.urandom(16), os.urandom(8), os.urandom(8)
words = struct.unpack('>4I', file_key)
tail = struct.unpack('>2I', nonce) + struct.unpack('>2I', mac)
node_key = struct.pack('>8I', *(words[i] ^ tail[i] for i in range(4)), *tail)
content = b'PK\x03\x04' + os.urandom(3000)
nodes = [
    {'h': 'ROOT', 'p': 'OWNER', 't': 1, 'k': 'ROOT:' + b64(encrypt(folder_key, modes.ECB(), os.urandom(16))), 'a': attributes(os.urandom(16), 'x')},
    {'h': 'SUB', 'p': 'ROOT', 't': 1, 'k': 'ROOT:' + b64(encrypt(folder_key, modes.ECB(), inner_key)), 'a': attributes(inner_key, 'GALE01')},
    {'h': 'FILE', 'p': 'SUB', 't': 0, 's': len(content), 'k': 'ROOT:' + b64(encrypt(folder_key, modes.ECB(), node_key)),
     'a': attributes(file_key, 'pack.zip')},
    {'h': 'BAD', 'p': 'SUB', 't': 0, 's': 1, 'k': 'ROOT:' + b64(os.urandom(32)), 'a': attributes(os.urandom(16), 'other.zip')},
]
hosts._mega_api = lambda payload, folder: {'f': nodes}
link = 'https://mega.nz/folder/ABCDEFGH#' + b64(folder_key)
_, _, decrypted = hosts._mega_folder_nodes(link)
check(decrypted['FILE']['name'] == 'pack.zip' and decrypted['FILE']['path'] == 'GALE01/pack.zip', f'file path {decrypted.get("FILE")}')
check('BAD' not in decrypted, 'a node that does not decrypt with the folder key is left out')
listed = hosts.mega_folder(link)
check(listed == [{'name': 'GALE01/pack.zip', 'size': len(content), 'url': link + '/file/FILE'}], f'listing {listed}')
check(hosts._aes(decrypted['FILE']['key'], 'ctr', decrypted['FILE']['iv'])(encrypt(file_key, modes.CTR(nonce + bytes(8)), content)) == content,
      'AES-CTR with the derived file key and nonce gives the file back')
check(hosts.mega_link('https://mega.nz/#F!ABCDEFGH!' + b64(folder_key)) == link, 'old #F! folder links')

# A MEGA transfer that stalls (per-address quota, throttling) ends at the bound as "quota", its partial download removed.
calls = []


def stalled(command, **options):
    calls.append(options.get('timeout'))
    Path(command[command.index('--path') + 1], 'partial.zip').write_bytes(b'PK')
    raise hosts.subprocess.TimeoutExpired(command, options.get('timeout'))


real_run, real_tool = hosts.subprocess.run, hosts._megatools
hosts.subprocess.run, hosts._megatools = stalled, lambda: '/usr/bin/megatools'
try:
    with tempfile.TemporaryDirectory() as folder:
        destination = Path(folder) / 'part-0'
        try:
            hosts.mega('https://mega.nz/file/ABCDEFGH#' + b64(file_key), str(destination), 1 << 30)
            check(False, 'a stalled MEGA transfer raises')
        except hosts.HostError as error:
            check(error.status == 'quota', f'stalled MEGA transfer status {error.status}')
        check(calls == [hosts.MEGA_SECONDS] and hosts.MEGA_SECONDS <= 3600, f'MEGA transfer bound {calls}')
        check(sorted(p.name for p in Path(folder).iterdir()) == [], 'the partial MEGA download is removed')
finally:
    hosts.subprocess.run, hosts._megatools = real_run, real_tool
print(f'PASS texture verification checks: {checks} checks (PPSSPP loose and zipped textures.ini, missing and '
      'case-mismatched targets; MEGA folder listing, key derivation, attributes and file decryption; stalled MEGA transfer)')
