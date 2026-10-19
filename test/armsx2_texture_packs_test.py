#!/usr/bin/env python3
"""Build 485: HD texture packs of the embedded ARMSX2 engine, host side.

Writes real fixtures (ZIP with Store/Deflate/ZIP64/CP437 names and refused
variants, GNU and pax tar, folders, ISO 9660 images with 2048 and raw 2352
sectors), compiles test/armsx2_texture_pack_core_test.cpp against the
production header packages/armsx2_internal_bridge/ios/Classes/
ARMSX2TexturePackCore.h and runs it. Also checks that the vendored upstream
headers are byte-identical to the pinned ARMSX2 files.

Portable (Linux or macOS, clang++ and zlib). It proves file handling only:
texture replacement in a game is reported by the engine (ABI 8), not here.
"""
from pathlib import Path
import hashlib, io, json, os, shutil, struct, subprocess, sys, tarfile, tempfile, zlib

ROOT = Path(__file__).resolve().parents[1]
CLASSES = ROOT / 'packages/armsx2_internal_bridge/ios/Classes'

PINNED = json.loads((ROOT / 'build-utils/armsx2/upstream-files.json').read_text())
for name in ('TexturePackPaths.h', 'TexturePackTar.h'):
    digest = hashlib.sha256((CLASSES / 'upstream' / name).read_bytes()).hexdigest()
    assert digest == PINNED['platforms/ios/app/src/main/cpp/IOS/' + name], name
print('PASS vendored upstream TexturePackPaths.h and TexturePackTar.h match the pinned ARMSX2 files')

PNG = bytes([137, 80, 78, 71, 13, 10, 26, 10]) + b'\x00' * 40


def dds(fourcc: bytes) -> bytes:
    header = bytearray(128)
    header[0:4] = b'DDS '
    struct.pack_into('<IIII', header, 4, 124, 0x1007, 64, 64)
    struct.pack_into('<II4s', header, 76, 32, 4, fourcc)
    return bytes(header) + b'\x11' * 2048


def astc() -> bytes:
    header = bytes([0x13, 0xAB, 0xA1, 0x5C, 4, 4, 1, 16, 0, 0, 16, 0, 0, 1, 0, 0])
    return header + b'\x22' * (16 * 16)


PAYLOAD = {
    'ui/0123456789abcdef-00004a2d.png': PNG + b'base',
    'ui/0123456789abcdef-00004a2d-mip1.png': PNG + b'mip',
    'fedcba9876543210-0000a1b2.dds': dds(b'DXT1'),
    '1111222233334444-r64x32-0000c3d4.astc': astc(),
    'bad-0000beef.dds': dds(b'ATI2'),  # BC5: no loader on iOS
    'readme.txt': b'credits',
}
PREFIX = 'pack-' + 'a' * 40 + '/textures/SLUS-21137/replacements/'


def make_zip(path, files, *, zip64=False, split=False, crc_override=None, method_override=None,
             encrypt=None, symlink=None, raw_names=None, extra_entries=0, forged_cd=False):
    """Hand-written ZIP so every field the reader trusts is under test control."""
    out = bytearray()
    central = bytearray()
    entries = list(files.items()) + [(f'extra/{i}.txt', b'x') for i in range(extra_entries)]
    for name, data in entries:
        raw = (raw_names or {}).get(name, name.encode())
        method = 0 if name.endswith('.txt') or name in (method_override or {}) else 8
        compressed = data if method == 0 else zlib.compress(data, 9)[2:-4]
        if method_override and name in method_override:
            method = method_override[name]
        crc = (crc_override or {}).get(name, zlib.crc32(data))
        flags = 0x1 if encrypt == name else 0
        offset = len(out)
        out += struct.pack('<IHHHHHIIIHH', 0x04034b50, 20, flags, method, 0, 0, crc,
                           len(compressed), len(data), len(raw), 0) + raw + compressed
        external = (0o120777 << 16) if symlink == name else 0
        made = (3 << 8) | 20
        if zip64:
            extra = struct.pack('<HHQQQ', 1, 24, len(data), len(compressed), offset)
            sizes = (0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF)
        else:
            extra = b''
            sizes = (len(compressed), len(data), offset)
        central += struct.pack('<IHHHHHHIIIHHHHHII', 0x02014b50, made, 45 if zip64 else 20, flags, method, 0, 0,
                               crc, sizes[0], sizes[1], len(raw), len(extra), 0, 0, 0, external, sizes[2]) + raw + extra
    cd_offset = len(out)
    out += central
    count = len(entries)
    if zip64 or count > 0xFFFF:
        z64 = len(out)
        out += struct.pack('<IQHHIIQQQQ', 0x06064b50, 44, 45, 45, 0, 0, count, count, len(central), cd_offset)
        out += struct.pack('<IIQI', 0x07064b50, 0, z64, 1)
        out += struct.pack('<IHHHHIIH', 0x06054b50, 0, 0, 0xFFFF, 0xFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 0)
    else:
        disk = 1 if split else 0
        size = 0xFFFFFFF0 if forged_cd else len(central)
        out += struct.pack('<IHHHHIIH', 0x06054b50, disk, disk, count, count, size, 0 if forged_cd else cd_offset, 0)
    path.write_bytes(bytes(out))


def iso_image(path, cnf: bytes | None, *, raw=False):
    sectors = {}
    pvd = bytearray(2048)
    pvd[0] = 1; pvd[1:6] = b'CD001'; pvd[6] = 1
    root = bytearray(34)
    root[0] = 34
    struct.pack_into('<I', root, 2, 18); struct.pack_into('>I', root, 6, 18)
    struct.pack_into('<I', root, 10, 2048); struct.pack_into('>I', root, 14, 2048)
    root[25] = 2; root[32] = 1
    pvd[156:190] = root
    sectors[16] = bytes(pvd)
    terminator = bytearray(2048); terminator[0] = 255; terminator[1:6] = b'CD001'; terminator[6] = 1
    sectors[17] = bytes(terminator)

    def record(name: bytes, lba: int, size: int, flags: int = 0) -> bytes:
        length = 33 + len(name) + (1 if len(name) % 2 == 0 else 0)
        rec = bytearray(length)
        rec[0] = length
        struct.pack_into('<I', rec, 2, lba); struct.pack_into('>I', rec, 6, lba)
        struct.pack_into('<I', rec, 10, size); struct.pack_into('>I', rec, 14, size)
        rec[25] = flags; rec[32] = len(name); rec[33:33 + len(name)] = name
        return bytes(rec)

    directory = record(b'\x00', 18, 2048, 2) + record(b'\x01', 18, 2048, 2)
    if cnf is None:
        directory += record(b'OTHER.TXT;1', 19, 5)
        sectors[19] = b'hello'.ljust(2048, b'\0')
    else:
        directory += record(b'SYSTEM.CNF;1', 19, len(cnf))
        sectors[19] = cnf.ljust(2048, b'\0')
    sectors[18] = directory.ljust(2048, b'\0')
    out = bytearray()
    for lba in range(24):
        data = sectors.get(lba, bytes(2048))
        if raw:
            out += b'\x00' + b'\xff' * 10 + b'\x00' + bytes([0, 2, lba, 2]) + bytes(8) + data + bytes(280)
        else:
            out += data
    path.write_bytes(bytes(out))


def fixtures(base: Path):
    payload = base / 'payload'
    for name, data in PAYLOAD.items():
        (payload / name).parent.mkdir(parents=True, exist_ok=True)
        (payload / name).write_bytes(data)
    prefixed = {PREFIX + name: data for name, data in PAYLOAD.items()}
    make_zip(base / 'pack-deflate.zip', prefixed)
    stored = {name: data for name, data in prefixed.items()}
    make_zip(base / 'pack-stored.zip', stored, method_override={n: 0 for n in stored})
    make_zip(base / 'pack-zip64.zip', prefixed, zip64=True, extra_entries=65536)
    make_zip(base / 'pack-cp437.zip', {'Caf\x82/SLUS-21137/a1-00000001.png': PNG},
             raw_names={'Caf\x82/SLUS-21137/a1-00000001.png': b'Caf\x82/SLUS-21137/a1-00000001.png'})
    make_zip(base / 'pack-symlink.zip', {'link-00000001.png': b'/etc/passwd'}, symlink='link-00000001.png')
    make_zip(base / 'pack-traversal.zip', {'../evil-00000001.png': PNG})
    make_zip(base / 'pack-encrypted.zip', {'a-00000001.png': PNG}, encrypt='a-00000001.png')
    make_zip(base / 'pack-split.zip', {'a-00000001.png': PNG}, split=True)
    make_zip(base / 'pack-deflate64.zip', {'SLUS-21137/a-00000001.png': PNG}, method_override={'SLUS-21137/a-00000001.png': 9})
    make_zip(base / 'pack-badcrc.zip', {'SLUS-21137/a-00000001.png': PNG}, crc_override={'SLUS-21137/a-00000001.png': 1234})
    make_zip(base / 'pack-unnamed.zip', {'SLUS-21137/texture.png': PNG, 'SLUS-21137/cover.dds': dds(b'DXT1')})
    make_zip(base / 'pack-forged-cd.zip', {'a-00000001.png': PNG}, forged_cd=True)
    # Another game of another region (store test: explained, then installed only with consent).
    make_zip(base / 'pack-other-region.zip',
             {'God of War II (Europe)/SLES-54164/replacements/a1b2c3d4e5f60708-00000001.png': PNG})
    # Only the name matters to the host: .tar.zst is decoded by the engine (ABI 8) in a game.
    (base / 'pack.tar.zst').write_bytes(bytes([0x28, 0xB5, 0x2F, 0xFD]) + bytes(60))
    (base / 'not-a-zip.zip').write_bytes(b'not a zip archive at all' * 4)

    with tarfile.open(base / 'pack.tar', 'w', format=tarfile.GNU_FORMAT) as tar:
        tar.add(payload, arcname=PREFIX.rstrip('/'))
    with tarfile.open(base / 'pack-pax.tar', 'w', format=tarfile.PAX_FORMAT) as tar:
        tar.add(payload, arcname=PREFIX.rstrip('/'))
    with tarfile.open(base / 'pack-traversal.tar', 'w', format=tarfile.GNU_FORMAT) as tar:
        member = tarfile.TarInfo('../evil-00000001.png')
        member.size = len(PNG)
        tar.addfile(member, io.BytesIO(PNG))
    whole = (base / 'pack.tar').read_bytes()
    (base / 'truncated.tar').write_bytes(whole[:len(whole) // 2])

    folder = base / 'folder/SLUS-21137/replacements'
    shutil.copytree(payload, folder)
    linked = base / 'folder-link'
    shutil.copytree(payload, linked)
    os.symlink('/etc', linked / 'escape')

    iso_image(base / 'game.iso', b'BOOT2 = cdrom0:\\SLUS_211.37;1\r\nVER = 1.01\r\nVMODE = NTSC\r\n')
    iso_image(base / 'game-raw.bin', b'BOOT2 = cdrom0:\\SCES_500.51;1\nVER = 1.00\nVMODE = PAL\n', raw=True)
    iso_image(base / 'volume-without-cnf.iso', None)
    (base / 'not-a-disc.chd').write_bytes(b'MComprHD' + bytes(70000))


def main() -> int:
    compiler = os.environ.get('CXX') or shutil.which('clang++') or 'c++'
    with tempfile.TemporaryDirectory(prefix='armsx2-textures-') as directory:
        base = Path(directory)
        data, work, binary = base / 'fixtures', base / 'work', base / 'test'
        data.mkdir(); work.mkdir()
        fixtures(data)
        command = [compiler, '-std=c++20', '-O1', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter',
                   '-I', str(CLASSES), str(ROOT / 'test/armsx2_texture_pack_core_test.cpp'), '-lz', '-o', str(binary)]
        if os.environ.get('ARMSX2_TEXTURE_SANITIZE') == '1':
            # Memory/UB run; warnings stay errors in the normal build (GCC flags libstdc++'s regex here).
            command = [c for c in command if c != '-Werror']
            command[1:1] = ['-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer', '-g']
        if sys.platform == 'darwin':
            command[1:1] = ['-isysroot', subprocess.check_output(['xcrun', '--show-sdk-path'], text=True).strip()]
        subprocess.run(command, check=True)
        subprocess.run([str(binary), str(data), str(work)], check=True, timeout=300)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
