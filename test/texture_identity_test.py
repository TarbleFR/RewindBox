"""Game identity readers of the HD texture catalogue
(packages/neo_texture_catalog/ios/Classes/NeoTextureIdentity.h), exercised on
synthetic images built here: no commercial game is used. Each case checks the
identifier the engine names its texture folder after.
"""
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLASSES = ROOT / 'packages/neo_texture_catalog/ios/Classes'


def iso9660(files):
    """files: {path: bytes} with '/'-separated upper-case paths. Returns a
    2048-byte-sector ISO9660 image (PVD at 16, root directory at 18)."""
    tree = {}
    for path, data in files.items():
        parts = path.split('/')
        node = tree
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = data
    sectors = {}
    next_sector = [18]

    def allocate(count):
        start = next_sector[0]
        next_sector[0] += max(count, 1)
        return start

    def record(name, extent, size, directory):
        name_bytes = name if isinstance(name, bytes) else (name.encode() + (b'' if directory else b';1'))
        length = 33 + len(name_bytes)
        length += length % 2
        out = bytes([length, 0]) + struct.pack('<I', extent) + struct.pack('>I', extent)
        out += struct.pack('<I', size) + struct.pack('>I', size) + bytes(7) + bytes([2 if directory else 0, 0, 0])
        out += struct.pack('<H', 1) + struct.pack('>H', 1) + bytes([len(name_bytes)]) + name_bytes
        return out + bytes(length - len(out))

    def write_dir(node, extent, parent_extent):
        entries = []
        children = []
        for name in sorted(node):
            value = node[name]
            if isinstance(value, dict):
                child_extent = allocate(1)
                children.append((value, child_extent))
                entries.append(record(name, child_extent, 2048, True))
            else:
                file_extent = allocate((len(value) + 2047) // 2048)
                sectors[file_extent] = value
                entries.append(record(name, file_extent, len(value), False))
        body = record(b'\x00', extent, 2048, True) + record(b'\x01', parent_extent, 2048, True) + b''.join(entries)
        assert len(body) <= 2048
        sectors[extent] = body
        for child, child_extent in children:
            write_dir(child, child_extent, extent)

    root_extent = allocate(1)
    write_dir(tree, root_extent, root_extent)
    pvd = bytearray(2048)
    pvd[0] = 1
    pvd[1:6] = b'CD001'
    pvd[6] = 1
    pvd[156:156 + 34] = record(b'\x00', root_extent, 2048, True)
    sectors[16] = bytes(pvd)
    sectors[17] = bytes([255]) + b'CD001' + bytes([1])
    total = next_sector[0]
    image = bytearray(total * 2048)
    for index, data in sectors.items():
        image[index * 2048:index * 2048 + len(data)] = data
    return bytes(image)


def raw2352(image, mode2=True):
    out = bytearray()
    for i in range(len(image) // 2048):
        header = b'\x00' + b'\xff' * 10 + b'\x00' + bytes(4) + (bytes(8) if mode2 else b'')
        out += header + image[i * 2048:(i + 1) * 2048]
        out += bytes(2352 - len(header) - 2048)
    return bytes(out)


def lz4_compress(data):
    """Greedy LZ4 block compressor (test input only)."""
    out, i, anchor, table = bytearray(), 0, 0, {}

    def emit(literal, match_length, offset):
        token_lit = min(len(literal), 15)
        token_match = 0 if match_length is None else min(match_length - 4, 15)
        out.append((token_lit << 4) | token_match)
        if len(literal) >= 15:
            rest = len(literal) - 15
            while rest >= 255:
                out.append(255)
                rest -= 255
            out.append(rest)
        out.extend(literal)
        if match_length is not None:
            out.extend(struct.pack('<H', offset))
            if match_length - 4 >= 15:
                rest = match_length - 4 - 15
                while rest >= 255:
                    out.append(255)
                    rest -= 255
                out.append(rest)
    limit = len(data) - 12
    while i < limit:
        key = data[i:i + 4]
        candidate = table.get(key)
        table[key] = i
        if candidate is not None and i - candidate < 65535:
            length = 4
            while i + length < len(data) - 5 and data[candidate + length] == data[i + length]:
                length += 1
            emit(data[anchor:i], length, i - candidate)
            i += length
            anchor = i
        else:
            i += 1
    emit(data[anchor:], None, 0)
    return bytes(out)


def ciso(image, lz4=False, block=2048):
    blocks = (len(image) + block - 1) // block
    header = (b'ZISO' if lz4 else b'CISO') + struct.pack('<IQIBB2x', 0x18, len(image), block, 1, 0)
    index_size = (blocks + 1) * 4
    data, offsets = bytearray(), []
    position = 0x18 + index_size
    for b in range(blocks):
        chunk = image[b * block:(b + 1) * block].ljust(block, b'\x00')
        if lz4:
            packed = lz4_compress(chunk)
        else:
            engine = zlib.compressobj(9, zlib.DEFLATED, -15)
            packed = engine.compress(chunk) + engine.flush()
        plain = len(packed) >= block
        offsets.append(position | (0x80000000 if plain else 0))
        payload = chunk if plain else packed
        data += payload
        position += len(payload)
    offsets.append(position)
    return header + b''.join(struct.pack('<I', o) for o in offsets) + bytes(data)


def sfo(values):
    keys = b''
    data = b''
    entries = b''
    for name, value in values.items():
        raw = value.encode() + b'\x00'
        padded = raw.ljust((len(raw) + 3) & ~3, b'\x00')
        entries += struct.pack('<HHIII', len(keys), 0x0204, len(raw), len(padded), len(data))
        keys += name.encode() + b'\x00'
        data += padded
    keys = keys.ljust((len(keys) + 3) & ~3, b'\x00')
    key_start = 20 + len(entries)
    data_start = key_start + len(keys)
    return b'\x00PSF' + struct.pack('<IIII', 0x101, key_start, data_start, len(values)) + entries + keys + data


def disc_header(game_id, revision, wii):
    h = bytearray(0x440)
    h[0:6] = game_id.encode()
    h[7] = revision
    if wii:
        h[0x18:0x1C] = struct.pack('>I', 0x5D1C9EA3)
    else:
        h[0x1C:0x20] = struct.pack('>I', 0xC2339F3D)
    h[0x20:0x30] = b'Synthetic game'
    return bytes(h)


def build_driver(folder):
    errors = []
    for cxx in (os.environ.get('CXX'), 'clang++', 'g++'):
        if not cxx or not shutil.which(cxx):
            continue
        output = folder / 'identity'
        result = subprocess.run([cxx, '-std=c++20', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined',
                                 f'-I{CLASSES}', str(ROOT / 'test/native/texture_identity_driver.cpp'), '-lz', '-o',
                                 str(output)], capture_output=True, text=True)
        if result.returncode == 0:
            return output
        errors.append(result.stderr[-500:])
    raise SystemExit('cannot build identity driver:\n' + '\n'.join(errors))


def main():
    with tempfile.TemporaryDirectory() as temp:
        temp = Path(temp)
        driver = build_driver(temp)
        count = [0]

        def check(kind, data, expect, ok=True):
            count[0] += 1
            path = temp / f'g{count[0]}'
            path.write_bytes(data)
            result = subprocess.run([str(driver), kind, str(path)], capture_output=True, text=True)
            assert 'runtime error' not in result.stderr and 'Sanitizer' not in result.stderr, result.stderr
            fields = dict(item.split('=', 1) for item in result.stdout.split())
            assert (result.returncode == 0) == ok, (kind, result.stdout)
            for key, value in expect.items():
                assert fields.get(key) == value, (kind, key, fields)
            return fields

        # PS2: serial from SYSTEM.CNF and the ELF CRC (XOR of 32-bit words).
        elf = os.urandom(300000 - 2)
        crc = 0
        for (word,) in struct.iter_unpack('<I', elf[:len(elf) // 4 * 4]):
            crc ^= word
        cnf = b'BOOT2 = cdrom0:\\SLUS_210.50;1\r\nVER = 1.00\r\nVMODE = NTSC\r\n'
        image = iso9660({'SYSTEM.CNF': cnf, 'SLUS_210.50': elf})
        expect = {'value': 'SLUS21050', 'folder': 'SLUS-21050', 'crc': f'{crc:08X}', 'region': 'USA'}
        check('ps2', image, {**expect, 'format': 'iso'})
        check('ps2', raw2352(image, True), {**expect, 'format': 'bin'})
        check('ps2', raw2352(image, False), {**expect, 'format': 'bin'})
        check('ps2', ciso(image), {**expect, 'format': 'cso'})
        check('ps2', ciso(image, lz4=True), {**expect, 'format': 'zso'})
        nested = iso9660({'SYSTEM.CNF': b'BOOT2 = cdrom0:\\DATA\\SCES_123.45;1\n', 'DATA/SCES_123.45': b'\x7fELF' + bytes(60)})
        check('ps2', nested, {'value': 'SCES12345', 'folder': 'SCES-12345', 'region': 'Europe', 'crc': '464C457F'})
        check('ps2', iso9660({'README.TXT': b'x'}), {'problem': 'noSystemCnf'}, ok=False)
        check('ps2', b'not an image' * 3000, {'problem': 'unsupportedFormat'}, ok=False)

        # GameCube / Wii: ID and revision across containers.
        gc = disc_header('GZ2E01', 2, False)
        check('gc', gc + bytes(0x10000), {'value': 'GZ2E01', 'revision': '2', 'region': 'USA', 'format': 'iso'})
        wii = disc_header('RMGP01', 1, True)
        check('wii', wii + bytes(0x10000), {'value': 'RMGP01', 'revision': '1', 'region': 'Europe', 'format': 'iso'})
        wbfs = b'WBFS' + struct.pack('>I', 1000) + bytes([9, 21, 0, 0]) + bytes(0x200 - 12) + wii
        check('wii', wbfs, {'value': 'RMGP01', 'revision': '1', 'format': 'wbfs'})
        cis = b'CISO' + struct.pack('<I', 0x200000) + bytes([1]) + bytes(0x8000 - 9) + gc
        check('gc', cis, {'value': 'GZ2E01', 'format': 'ciso'})
        for magic, name in ((b'WIA\x01', 'wia'), (b'RVZ\x01', 'rvz')):
            wia = magic + bytes(0x58 - 4) + gc[:0x80] + bytes(0x400)
            check('gc', wia, {'value': 'GZ2E01', 'revision': '2', 'format': name})
        block = gc.ljust(0x4000, b'\x00')
        packed = zlib.compress(block, 9)
        gcz = struct.pack('<IIQQII', 0xB10BC001, 0, len(packed), len(block), len(block), 1)
        gcz += struct.pack('<Q', 0) + struct.pack('<I', zlib.adler32(packed)) + packed
        check('gc', gcz, {'value': 'GZ2E01', 'revision': '2', 'format': 'gcz'})
        check('gc', bytes(0x500), {'problem': 'unsupportedFormat'}, ok=False)
        # Wii WAD (Virtual Console): title ID low bytes + group ID, title version
        # as revision (Dolphin's TMDReader::GetGameID / GetTitleVersion).
        def wad(title_low, group, version, cert=0xA00, ticket=0x2A4):
            tmd = bytearray(0x208)
            tmd[0x18C:0x194] = b'\x00\x01\x00\x01' + title_low
            tmd[0x198:0x19A] = group
            tmd[0x1DC:0x1DE] = struct.pack('>H', version)
            align = lambda n: (n + 0x3F) & ~0x3F
            head = struct.pack('>I2sHIIIIII', 0x20, b'Is', 0, cert, 0, ticket, len(tmd), 0x40, 0)
            return head.ljust(0x40, b'\x00') + bytes(align(cert)) + bytes(align(ticket)) + bytes(tmd).ljust(align(len(tmd)), b'\x00') + bytes(0x40)
        check('wii', wad(b'NAAE', b'01', 2), {'value': 'NAAE01', 'revision': '2', 'region': 'USA', 'format': 'wad'})
        check('wii', wad(b'NACP', b'01', 0, cert=0xA10), {'value': 'NACP01', 'revision': '0', 'region': 'Europe', 'format': 'wad'})
        check('wii', wad(b'\x00\x00\x00\x02', b'\x00\x00', 513), {'problem': 'unsupportedFormat'}, ok=False)

        # PSP: PARAM.SFO DISC_ID / DISC_VERSION, PBP, UMD_DATA.BIN fallback.
        param = sfo({'DISC_ID': 'ULUS10041', 'DISC_VERSION': '1.01', 'TITLE': 'Synthetic'})
        image = iso9660({'PSP_GAME/PARAM.SFO': param, 'UMD_DATA.BIN': b'ULUS-10041|0000000000000000|0001|G'})
        expect = {'value': 'ULUS10041', 'folder': 'ULUS10041', 'revision': '1.01', 'region': 'USA'}
        check('psp', image, {**expect, 'format': 'iso'})
        check('psp', ciso(image), {**expect, 'format': 'cso'})
        check('psp', ciso(image, lz4=True), {**expect, 'format': 'zso'})
        pbp = b'\x00PBP' + struct.pack('<I', 0x10000) + struct.pack('<8I', *([40, 40 + len(param)] + [40 + len(param)] * 6)) + param
        check('psp', pbp, {'value': 'ULUS10041', 'revision': '1.01', 'format': 'pbp'})
        umd_only = iso9660({'UMD_DATA.BIN': b'ULES-01234|0000000000000000|0001|G'})
        check('psp', umd_only, {'value': 'ULES01234', 'region': 'Europe'})
        check('psp', iso9660({'X.BIN': b'1'}), {'problem': 'noDiscID'}, ok=False)

        # 3DS: program ID from NCSD/NCCH, title ID from the CIA TMD; updates refused.
        program = 0x0004000000033500
        ncch = bytearray(0x200)
        ncch[0x100:0x104] = b'NCCH'
        ncch[0x118:0x120] = struct.pack('<Q', program)
        ncsd = bytearray(0x4000)
        ncsd[0x100:0x104] = b'NCSD'
        ncsd[0x120:0x128] = struct.pack('<II', 0x4000 // 0x200, 0x10)
        check('3ds', bytes(ncsd) + bytes(ncch) + bytes(0x1000), {'value': '0004000000033500', 'format': 'cci'})
        check('3ds', bytes(ncch) + bytes(0x1000), {'value': '0004000000033500', 'format': 'cxi'})
        cert, ticket = 0xA00, 0x350
        cia = bytearray(struct.pack('<IHHIIIIQ', 0x2020, 0, 0, cert, ticket, 0x208, 0, 0)) + bytes(0x2020 - 32)
        cia = cia.ljust(0x2040, b'\x00') + bytes(cert).ljust((cert + 63) & ~63, b'\x00') + bytes(ticket).ljust((ticket + 63) & ~63, b'\x00')
        tmd = bytearray(0x208)
        tmd[0:4] = struct.pack('>I', 0x10004)
        tmd[0x140 + 0x4C:0x140 + 0x54] = struct.pack('>Q', program)
        check('3ds', bytes(cia) + bytes(tmd), {'value': '0004000000033500', 'format': 'cia'})
        update = bytearray(ncch)
        update[0x118:0x120] = struct.pack('<Q', 0x0004000E00033500)
        check('3ds', bytes(update) + bytes(0x100), {'problem': 'notGame'}, ok=False)
        check('3ds', bytes(0x400), {'problem': 'unsupportedFormat'}, ok=False)
        print(f'PASS texture identity: {count[0]} synthetic images (PS2 ISO/raw MODE1/MODE2/CSO/ZSO serial + ELF CRC; '
              'GC/Wii ISO/WBFS/CISO/WIA/RVZ/GCZ/WAD ID + revision; PSP ISO/CSO/ZSO/PBP/UMD_DATA disc ID; '
              '3DS NCSD/NCCH/CIA program ID, update refused; unreadable inputs reported)')


if __name__ == '__main__':
    main()
