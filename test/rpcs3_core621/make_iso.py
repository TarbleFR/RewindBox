#!/usr/bin/env python3
"""Small PS3-layout ISO 9660 images for the REWINDBOX_ISO_IMAGE_LIFETIME_621 test.

Layout (2048-byte sectors), as test/ps3_disc_image_builder.dart: system area
(sector 0: one unencrypted PS3 region),
primary descriptor (16), terminator (17), root (18), PS3_GAME (19), USRDIR (20),
then the files. Each file's byte i is (i * 131 + seed * 7 + (i >> 11)) & 0xff,
the formula iso_lifetime_test.cpp checks.
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

SECTOR = 2048


def file_bytes(seed: int, size: int) -> bytes:
    return bytes(((i * 131 + seed * 7 + (i >> 11)) & 0xFF) for i in range(size))


def record(lba: int, size: int, directory: bool, name: bytes) -> bytes:
    length = 33 + len(name) + (1 if len(name) % 2 == 0 else 0)
    out = bytearray(length)
    out[0] = length
    out[2:6] = struct.pack('<I', lba)
    out[6:10] = struct.pack('>I', lba)
    out[10:14] = struct.pack('<I', size)
    out[14:18] = struct.pack('>I', size)
    out[18:25] = bytes([126, 11, 2, 12, 0, 0, 0])  # 2026-11-02 12:00:00
    out[25] = 0x02 if directory else 0x00
    out[28:32] = struct.pack('<HH', 1, 1)[:2] + struct.pack('>H', 1)
    out[32] = len(name)
    out[33:33 + len(name)] = name
    return bytes(out)


def image(icon_seed: int, data_seed: int) -> bytes:
    root, game, usrdir = 18, 19, 20
    files = {
        'PS3_DISC.SFB': (0x11, 16),
        'PARAM.SFO': (0x13, 300),
        'ICON0.PNG': (icon_seed, 4096),
        'DATA.BIN': (data_seed, 3 * SECTOR * 37 + 1234),
    }
    placement = {}
    lba = 21
    for name, (_, size) in files.items():
        placement[name] = lba
        lba += (size + SECTOR - 1) // SECTOR
    out = bytearray(lba * SECTOR)
    # PS3 disc sector 0: one unencrypted region covering the whole image
    # (iso_file_decryption::init reads the region count and its last sector).
    out[0:4] = struct.pack('>I', 1)
    out[12:16] = struct.pack('>I', lba - 1)
    for index in range(2 * SECTOR, 16 * SECTOR):
        out[index] = (index * 31) & 0xFF

    def descriptor(index: int, kind: int) -> None:
        at = index * SECTOR
        out[at] = kind
        out[at + 1:at + 6] = b'CD001'
        out[at + 6] = 1

    descriptor(16, 1)
    descriptor(17, 255)
    root_record = record(root, SECTOR, True, b'\x00')
    out[16 * SECTOR + 156:16 * SECTOR + 156 + len(root_record)] = root_record

    def directory(at_lba: int, parent: int, entries: list[bytes]) -> None:
        at = at_lba * SECTOR
        for entry in [record(at_lba, SECTOR, True, b'\x00'), record(parent, SECTOR, True, b'\x01'), *entries]:
            out[at:at + len(entry)] = entry
            at += len(entry)

    directory(root, root, [
        record(placement['PS3_DISC.SFB'], files['PS3_DISC.SFB'][1], False, b'PS3_DISC.SFB;1'),
        record(game, SECTOR, True, b'PS3_GAME'),
    ])
    directory(game, root, [
        record(placement['ICON0.PNG'], files['ICON0.PNG'][1], False, b'ICON0.PNG;1'),
        record(placement['PARAM.SFO'], files['PARAM.SFO'][1], False, b'PARAM.SFO;1'),
        record(usrdir, SECTOR, True, b'USRDIR'),
    ])
    directory(usrdir, game, [
        record(placement['DATA.BIN'], files['DATA.BIN'][1], False, b'DATA.BIN;1'),
    ])
    for name, (seed, size) in files.items():
        at = placement[name] * SECTOR
        out[at:at + size] = file_bytes(seed, size)
    return bytes(out)


def main() -> int:
    target = Path(sys.argv[1])
    target.mkdir(parents=True, exist_ok=True)
    (target / 'disc-a.iso').write_bytes(image(0x21, 0x5A))
    (target / 'disc-b.iso').write_bytes(image(0x33, 0x77))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
