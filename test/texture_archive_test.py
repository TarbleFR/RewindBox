"""Exercise the production streaming ZIP/ZIP64/7z readers of the HD texture
catalogue (packages/neo_texture_catalog/ios/Classes/NeoTextureArchive.h and
NeoTextureSevenZip.h) through test/native/texture_archive_driver.cpp.

Nothing is loaded whole: entries are decompressed through fixed buffers into
new files whose size and CRC-32 must match the archive. The driver extracts
every supported entry except names containing "skip-".
"""
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import warnings
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'test'))
import texture_7z_writer as sz  # noqa: E402

CLASSES = ROOT / 'packages/neo_texture_catalog/ios/Classes'
LZMA = ROOT / 'packages/neo_texture_catalog/ios/ThirdParty/lzma'
PNG = b'\x89PNG\r\n\x1a\n' + bytes(range(256)) * 3000


def compiler():
    for candidate in (os.environ.get('CXX'), 'clang++', 'g++'):
        if candidate and shutil.which(candidate):
            yield candidate


def build(folder):
    """Compiles the driver with ASan/UBSan. The SDK's own deliberate unaligned
    loads (allowed on ARM64 and x86) are excluded from the alignment check."""
    errors = []
    for cxx in compiler():
        sanitize = ['-fsanitize=address,undefined']
        lzma_object = folder / 'lzma.o'
        driver = folder / 'texture-archive'
        steps = [
            [cxx, '-x', 'c', '-c', '-O1', *sanitize, '-fno-sanitize=alignment', f'-I{LZMA}',
             str(CLASSES / 'NeoTextureLZMA.c'), '-o', str(lzma_object)],
            [cxx, '-std=c++20', '-Wall', '-Wextra', '-Werror', *sanitize, f'-I{CLASSES}', f'-I{LZMA}',
             str(ROOT / 'test/native/texture_archive_driver.cpp'), str(lzma_object), '-lz', '-o', str(driver)],
        ]
        result = None
        for step in steps:
            result = subprocess.run(step, capture_output=True, text=True)
            if result.returncode:
                break
        if result.returncode == 0:
            return driver
        errors.append(f'{cxx}: {result.stderr[-600:]}')
    raise SystemExit('cannot build the archive driver:\n' + '\n'.join(errors))


def main():
    with tempfile.TemporaryDirectory() as temp:
        temp = Path(temp)
        driver = build(temp)
        counter = [0]

        def run(kind, data, *extra):
            counter[0] += 1
            archive = temp / f'a{counter[0]}.{kind}'
            archive.write_bytes(data)
            out = temp / f'o{counter[0]}'
            out.mkdir()
            result = subprocess.run([str(driver), kind, str(archive), str(out), *map(str, extra)],
                                    capture_output=True, text=True)
            assert 'runtime error' not in result.stderr and 'AddressSanitizer' not in result.stderr, result.stderr
            return result.returncode, out, result.stdout

        def zip_bytes(entries, method=zipfile.ZIP_DEFLATED, force64=False, mutate=None):
            path = temp / 'build.zip'
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                with zipfile.ZipFile(path, 'w', compression=method, allowZip64=True) as z:
                    for name, data in entries:
                        if isinstance(name, zipfile.ZipInfo):
                            z.writestr(name, data)
                        else:
                            with z.open(name, 'w', force_zip64=force64) as handle:
                                handle.write(data)
            data = path.read_bytes()
            return mutate(data) if mutate else data

        checks = 0
        # ZIP: stored/deflated, with and without ZIP64 local records.
        for method in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            for force64 in (False, True):
                code, out, log = run('zip', zip_bytes([('SLUS-21050/replacements/a.png', PNG), ('dir/', b''),
                                                        ('README.txt', b'hi')], method, force64))
                assert code == 0, log
                assert (out / 'SLUS-21050/replacements/a.png').read_bytes() == PNG
                checks += 1
        # ZIP64 end records: more than 65535 entries.
        many = [(f'GZ2E01/tex1_{i:05d}.png', b'\x89PNG\r\n\x1a\n%d' % i) for i in range(70000)]
        data = zip_bytes(many, zipfile.ZIP_STORED)
        assert b'PK\x06\x06' in data[-200:], 'expected a ZIP64 end of central directory'
        code, out, log = run('zip', data)
        assert code == 0, log[-400:]
        assert len(list((out / 'GZ2E01').iterdir())) == 70000
        assert (out / 'GZ2E01/tex1_69999.png').read_bytes() == b'\x89PNG\r\n\x1a\n69999'
        checks += 1
        # Windows separators are folded; CP437 and UTF-8 names decode.
        code, out, log = run('zip', zip_bytes([('Pack\\0004000000033500\\a.png', PNG)]))
        assert code == 0 and (out / 'Pack/0004000000033500/a.png').read_bytes() == PNG, log
        info = zipfile.ZipInfo('Pok\x82mon/tex.png')  # CP437 0x82 = é, no UTF-8 flag
        info.flag_bits &= ~0x800

        def keep_cp437(data):
            return data.replace('Pok\u00e9mon'.encode('utf-8'), b'Pok\x82mon') if False else data
        code, out, log = run('zip', zip_bytes([('Pokémon/tex.png', PNG)]))
        assert code == 0 and (out / 'Pokémon/tex.png').read_bytes() == PNG, log
        raw = zip_bytes([('PokXmon/tex.png', PNG)], zipfile.ZIP_STORED)
        raw = raw.replace(b'PokXmon', b'Pok\x82mon')  # same length; flag bit 11 stays clear
        code, out, log = run('zip', raw)
        assert code == 0 and (out / 'Pokémon/tex.png').read_bytes() == PNG, log
        checks += 3
        # Unsafe names make the whole archive unreadable.
        for name in ('../escape.png', '/abs.png', 'C:/drive.png', 'a/../b.png', 'a//b.png', 'a/./b.png'):
            code, out, log = run('zip', zip_bytes([(name, PNG)], zipfile.ZIP_STORED))
            assert code == 2 and 'open invalid' in log, (name, log)
            checks += 1
        # Links and encrypted entries are never materialized.
        link = zipfile.ZipInfo('GZ2E01/skip-link.png')
        link.create_system = 3
        link.external_attr = 0o120777 << 16
        code, out, log = run('zip', zip_bytes([(link, b'/etc/passwd'), ('GZ2E01/tex1_a.png', PNG)]))
        assert code == 0 and not (out / 'GZ2E01/skip-link.png').exists() and 'link=1' in log, log
        link2 = zipfile.ZipInfo('GZ2E01/link.png')
        link2.create_system = 3
        link2.external_attr = 0o120777 << 16
        code, out, log = run('zip', zip_bytes([(link2, b'/etc/passwd')]))
        assert code == 3 and 'extract unsupported' in log, log

        def encrypt(data):
            b = bytearray(data)
            for signature, offset in ((b'PK\x03\x04', 6), (b'PK\x01\x02', 8)):
                at = b.index(signature)
                b[at + offset] |= 1
            return bytes(b)
        code, out, log = run('zip', zip_bytes([('GZ2E01/tex1_a.png', PNG)], mutate=encrypt))
        assert code == 3 and 'enc=1' in log, log
        checks += 3
        # Damaged data: CRC, truncation, an entry pointing into another entry.

        def bad_crc(data):
            b = bytearray(data)
            at = b.index(b'PK\x01\x02')
            b[at + 16] ^= 1
            return bytes(b)
        code, out, log = run('zip', zip_bytes([('GZ2E01/tex1_a.png', PNG)], mutate=bad_crc))
        assert code == 3 and 'extract crc' in log and not (out / 'GZ2E01/tex1_a.png').exists(), log
        code, out, log = run('zip', zip_bytes([('GZ2E01/tex1_a.png', PNG)])[:-5])
        assert code == 2, log

        def overlap(data):
            # Second central entry reuses the first local header (overlapping bomb).
            b = bytearray(data)
            first = b.index(b'PK\x01\x02')
            second = b.index(b'PK\x01\x02', first + 4)
            b[second + 42:second + 46] = b[first + 42:first + 46]
            return bytes(b)
        code, out, log = run('zip', zip_bytes([('A/tex1_a.png', PNG), ('A/tex1_b.png', PNG)], zipfile.ZIP_STORED,
                                              mutate=overlap))
        assert code == 3, log
        # Per-file limit: the entry is refused, not truncated.
        code, out, log = run('zip', zip_bytes([('A/tex1_a.png', PNG)]), 0, 1 << 28, 1000)
        assert code == 3 and 'extract limits' in log, log
        # Cancellation removes the unfinished file.
        big = os.urandom(3 << 20)
        code, out, log = run('zip', zip_bytes([('A/tex1_big.png', big)], zipfile.ZIP_STORED), 1 << 20)
        assert code == 4 and not (out / 'A/tex1_big.png').exists(), log
        checks += 5

        # 7z: every supported coder, solid or not, plain or encoded header.
        entries = [('pack', None), ('pack/0004000000033500', None), ('pack/0004000000033500/a.png', PNG),
                   ('pack/empty.txt', b''), ('pack/0004000000033500/b.png', PNG[::-1])]
        for method in (sz.COPY, sz.LZMA, sz.LZMA2, sz.DEFLATE):
            for solid in (True, False):
                for encoded in (True, False):
                    code, out, log = run('7z', sz.build(entries, method, solid, encoded, folder_crc=True))
                    assert code == 0, log
                    assert (out / 'pack/0004000000033500/a.png').read_bytes() == PNG
                    assert (out / 'pack/0004000000033500/b.png').read_bytes() == PNG[::-1]
                    assert (out / 'pack/empty.txt').read_bytes() == b''
                    checks += 1
        # The LZMA window never exceeds the block: a 16 MiB dictionary over a
        # ~1.5 MB block needs ~1.5 MB, refused under a 1 MiB cap, fine at 4 MiB.
        archive = sz.build(entries, sz.LZMA2, True, True, dictionary=1 << 24)
        code, out, log = run('7z', archive, 0, 1 << 20)
        assert code == 3 and 'extract limits' in log, log
        code, out, log = run('7z', archive, 0, 4 << 20)
        assert code == 0, log
        archive = sz.build(entries, sz.LZMA, True, True, dictionary=1 << 24)
        code, out, log = run('7z', archive, 0, 1 << 20)
        assert code == 3 and 'extract limits' in log, log
        checks += 3
        # Only wanted files are written; unwanted ones in the same block are skipped.
        code, out, log = run('7z', sz.build([('p/skip-a.png', PNG), ('p/b.png', PNG[::-1]), ('p/skip-c.png', PNG)],
                                            sz.LZMA2))
        assert code == 0, log
        assert (out / 'p/b.png').read_bytes() == PNG[::-1] and not (out / 'p/skip-a.png').exists(), log
        checks += 1
        # A symlink (Unix mode in the attributes) is never written.
        code, out, log = run('7z', sz.build([('p/link.png', b'/etc/passwd')], sz.COPY,
                                            attributes=[0x8000 | (0o120777 << 16)]))
        assert code == 3 and 'link=1' in log and not (out / 'p/link.png').exists(), log
        # Damaged packed data or CRC.
        archive = bytearray(sz.build([('p/a.png', PNG)], sz.COPY, encode_header=False))
        archive[32 + 100] ^= 0xff
        code, out, log = run('7z', bytes(archive))
        assert code == 3 and 'extract crc' in log and not (out / 'p/a.png').exists(), log
        code, out, log = run('7z', sz.build([('p/a.png', PNG)], sz.LZMA2)[:-10])
        assert code == 2, log
        code, out, log = run('7z', b'7z\xbc\xaf\x27\x1c' + b'\x00' * 40)
        assert code == 2, log
        checks += 4
        # Cancellation inside a solid block.
        code, out, log = run('7z', sz.build([('p/a.png', os.urandom(2 << 20))], sz.COPY), 1 << 20)
        assert code == 4 and not (out / 'p/a.png').exists(), log
        checks += 1
        print(f'PASS texture archives: {checks} ZIP/ZIP64/7z scenarios (stored/deflate, ZIP64 end records with 70000 '
              'entries, separators and name encodings, traversal/absolute/drive names, links, encryption, CRC, '
              'truncation, overlapping entries, per-file limit, cancellation; 7z Copy/LZMA/LZMA2/Deflate solid and '
              'not, plain and encoded headers, bounded LZMA window, partial extraction, damaged data)')


if __name__ == '__main__':
    main()
