#!/usr/bin/env python3
"""Offline native Store provider integration: real HTTP delegates, AES and engines.

Only the resolver endpoint and HTTP server are controlled fixtures. Production
NSURLSession streaming, ciphertext resume, CommonCrypto decryption, hash gates,
archive readers, engine adapters and transactional installation run unchanged.
"""
from __future__ import annotations
import hashlib
import io
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import zipfile
import zlib

from texture_direct_network_test import ROOT, build_native


def png() -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    pixels = hashlib.shake_256(b'NeoStation Store integration fixture').digest(64 * 64 * 4)
    scanlines = b''.join(b'\0' + pixels[y * 256:(y + 1) * 256] for y in range(64))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 64, 64, 8, 6, 0, 0, 0)) +
            chunk(b'IDAT', zlib.compress(scanlines)) + chunk(b'IEND', b''))


def fixtures(folder: Path) -> Path:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from texture_rar_test import rar4
    folder.mkdir(parents=True)
    image = png()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_STORED) as archive:
        archive.writestr('GALE01/tex1_fixture.png', image)
    plain = buffer.getvalue()
    key, iv = bytes(range(16)), bytes(range(16, 24)) + bytes(8)
    encryptor = Cipher(algorithms.AES(key), modes.CTR(iv)).encryptor()
    cipher = encryptor.update(plain) + encryptor.finalize()
    (folder / 'plain.zip').write_bytes(plain)
    (folder / 'cipher.bin').write_bytes(cipher)
    (folder / 'texture.png').write_bytes(image)
    (folder / 'dolphin.rar').write_bytes(rar4([
        ('GALE01/tex1_fixture.png', image, 0o100644, 0),
        ('GALE01/installer.exe', b'never installed', 0o100644, 0),
    ]))
    (folder / 'ps2.rar').write_bytes(rar4([
        ('SLUS-21137/replacements/ui/0123456789abcdef-00004a2d.png', image, 0o100644, 0),
        ('SLUS-21137/replacements/installer.exe', b'never installed', 0o100644, 0),
    ]))
    (folder / 'wrong-region.rar').write_bytes(rar4([
        ('SLES-50000/replacements/0123456789abcdef-00004a2d.png', image, 0o100644, 0),
    ]))
    (folder / 'damaged.rar').write_bytes((folder / 'ps2.rar').read_bytes()[:-30])
    metadata = {'size': len(plain), 'sha256': hashlib.sha256(plain).hexdigest(),
                'key': key.hex(), 'iv': iv.hex()}
    path = folder / 'fixtures.json'
    path.write_text(json.dumps(metadata))
    return path


def main() -> int:
    if sys.platform != 'darwin':
        print('NOT RUN: Store provider integration requires macOS Foundation/CommonCrypto', file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory(prefix='neotex-provider-') as temporary:
        folder = Path(temporary)
        metadata = fixtures(folder / 'fixtures')
        binary = build_native(folder / 'build', ROOT / 'test/texture_store_provider_test.mm', armsx2=True)
        subprocess.run([str(binary), str(metadata), str(folder / 'work')], check=True, timeout=300)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
