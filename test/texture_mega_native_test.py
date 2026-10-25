#!/usr/bin/env python3
"""MEGA public API fixtures + production CommonCrypto implementation (macOS).

The encrypted fixture is generated independently with python-cryptography,
including counter rollover, a non-block-aligned tail and encrypted folder keys.
No account, creator payload, network transfer or quota retry is used here.
"""
from pathlib import Path
import base64
import hashlib
import json
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CLASSES = ROOT / 'packages/neo_texture_catalog/ios/Classes'


def fixtures(folder):
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    def b64(data):
        return base64.urlsafe_b64encode(data).rstrip(b'=').decode()
    raw = bytes(range(32))
    key = bytes(a ^ b for a, b in zip(raw[:16], raw[16:]))
    iv = raw[16:24] + bytes(8)
    folder_key = bytes(range(32, 48))
    plain = b'PK\x03\x04' + bytes((i * 23 + i // 251) & 255 for i in range((3 << 20) + 33))
    encrypted = Cipher(algorithms.AES(key), modes.CTR(iv)).encryptor().update(plain)
    attributes = b'MEGA' + json.dumps({'n': 'Synthetic HD fixture.zip'}, separators=(',', ':')).encode()
    attributes += bytes(-len(attributes) % 16)
    attributes = Cipher(algorithms.AES(key), modes.CBC(bytes(16))).encryptor().update(attributes)
    wrapped = Cipher(algorithms.AES(folder_key), modes.ECB()).encryptor().update(raw)
    (folder / 'cipher.bin').write_bytes(encrypted)
    (folder / 'plain.bin').write_bytes(plain)
    output = {
        'part': {'provider': 'mega', 'url': f'https://mega.nz/file/ABCDEFGH#{b64(raw)}',
                 'size': len(plain), 'sha256': hashlib.sha256(plain).hexdigest()},
        'legacy': f'https://mega.co.nz/#!ABCDEFGH!{b64(raw)}',
        'folderPart': {'provider': 'mega', 'url': f'https://mega.nz/folder/FOLDERAB#{b64(folder_key)}/file/FILEABCD',
                       'size': len(plain), 'sha256': hashlib.sha256(plain).hexdigest()},
        'crypto': {'key': b64(key), 'iv': b64(iv), 'size': len(plain)},
        'fileResponse': [{'g': 'https://gfs000.userstorage.mega.co.nz/temporary-fixture',
                          's': len(plain), 'at': b64(attributes)}],
        'folderResponse': [{'f': [{'h': 'FILEABCD', 't': 0, 's': len(plain),
                                  'k': 'FOLDERAB:' + b64(wrapped), 'a': b64(attributes)}]}],
    }
    (folder / 'fixture.json').write_text(json.dumps(output))


def main():
    if sys.platform != 'darwin':
        print('NOT RUN: MEGA CommonCrypto native test requires macOS', file=sys.stderr)
        return 2
    sdk = subprocess.check_output(['xcrun', '--show-sdk-path'], text=True).strip()
    with tempfile.TemporaryDirectory(prefix='neotex-mega-') as temporary:
        folder = Path(temporary)
        fixtures(folder)
        binary = folder / 'test-mega'
        subprocess.run(['xcrun', 'clang++', '-std=c++20', '-fobjc-arc', '-Wall', '-Wextra', '-Werror',
                        '-Wno-deprecated-declarations', '-isysroot', sdk, '-I', str(CLASSES),
                        '-I', str(CLASSES / 'Public'), str(CLASSES / 'NeoTextureMega.mm'),
                        str(ROOT / 'test/texture_mega_test.mm'), '-framework', 'Foundation', '-o', str(binary)], check=True)
        subprocess.run([str(binary), str(folder)], check=True, timeout=120)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
