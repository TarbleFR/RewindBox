#!/usr/bin/env python3
"""New native RAR reader: real RAR4/RAR5/solid files and hostile-input bounds.

Builds the vendored production decoder with ASan+UBSan. Fixture provenance and
licences are retained in test/fixtures/texture_rar; no game textures are used.
"""
import binascii
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/textures'))
import build_rar_library

FIXTURES = ROOT / 'test/fixtures/texture_rar'
CLASSES = ROOT / 'packages/neo_texture_catalog/ios/Classes'
SANITIZE = ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
# This container denies LeakSanitizer /proc/ptrace enumeration. ASan/UBSan
# remain enabled; the driver's per-reader allocation accounting must reach zero.
RUN_ENV = {**os.environ, 'ASAN_OPTIONS': 'detect_leaks=0'}


def fixture(name):
    result = bytearray()
    active = False
    for line in (FIXTURES / (name + '.uu')).read_bytes().splitlines():
        if line.startswith(b'begin '):
            active = True
        elif line == b'end':
            break
        elif active and line:
            result.extend(binascii.a2b_uu(line))
    return bytes(result)


def rar4_block(kind, flags, body=b''):
    header = struct.pack('<BHH', kind, flags, 7 + len(body)) + body
    return struct.pack('<H', zlib.crc32(header) & 0xffff) + header


def rar4(entries, main_flags=0):
    result = b'Rar!\x1a\x07\0' + rar4_block(0x73, main_flags, bytes(6))
    for name, data, attrs, flags in entries:
        name = name.encode('utf-8')
        fields = struct.pack('<IIBIIBBHI', len(data), len(data), 3, zlib.crc32(data), 0,
                             20, 0x30, len(name), attrs)
        result += rar4_block(0x74, 0x8000 | flags, fields + name) + data
    return result + rar4_block(0x7b, 0)


def vint(value):
    out = bytearray()
    while value >= 128:
        out.append((value & 127) | 128)
        value >>= 7
    return bytes(out + bytes([value]))


def rar5_crc(data, directory=False, solid=False):
    def block(content):
        header = vint(len(content)) + content
        return struct.pack('<I', zlib.crc32(header)) + header
    name = b'directory/checksum.txt' if directory else b'checksum.txt'
    main = block(b'\1\0' + vint(4 if solid else 0))
    if directory:
        dirname = b'directory'
        fields = vint(1) + vint(0) + vint(0o40755) + vint(0) + vint(1) + vint(len(dirname)) + dirname
        main += block(vint(2) + vint(2) + vint(0) + fields)
    body = (vint(4) + vint(len(data)) + vint(0o100644) + struct.pack('<I', zlib.crc32(data))
            + vint(0) + vint(1) + vint(len(name)) + name)
    file = block(vint(2) + vint(2) + vint(len(data)) + body) + data
    return b'Rar!\x1a\x07\1\0' + main + file + block(b'\5\0\0')


def rar4_first(data):
    # Keep the original compressed first member of the upstream fixture;
    # later symlinks must be rejected by the separate unchanged-fixture test.
    offset = 7
    prefix = data[:7]
    while offset + 7 <= len(data):
        kind, flags, size = struct.unpack_from('<BHH', data, offset + 2)
        packed = struct.unpack_from('<I', data, offset + 7)[0] if flags & 0x8000 else 0
        block = data[offset:offset + size + packed]
        prefix += block
        offset += size + packed
        if kind == 0x74:
            return prefix + rar4_block(0x7b, 0)
    raise AssertionError('no compressed file in upstream fixture')


def main():
    with tempfile.TemporaryDirectory(prefix='neotex-rar-') as temporary:
        temp = Path(temporary)
        cxx = os.environ.get('CXX') or shutil.which('clang++') or 'g++'
        cc = os.environ.get('CC') or shutil.which('clang') or 'gcc'
        library = build_rar_library.build(temp / 'decoder', cc, SANITIZE)
        driver = temp / 'rar-reader'
        subprocess.run([cxx, '-std=c++20', '-Wall', '-Wextra', '-Werror', *SANITIZE,
                        '-I' + str(CLASSES), str(ROOT / 'test/native/texture_rar_driver.cpp'),
                        str(library), '-lz', *(['-liconv'] if sys.platform == 'darwin' else ['-no-pie']),
                        '-o', str(driver)], check=True)
        checks = []

        def run(name, data, expected='ok', *limits):
            archive = temp / (name + '.rar')
            archive.write_bytes(data)
            output = temp / (name + '-out')
            output.mkdir()
            result = subprocess.run([str(driver), str(archive), str(output), *map(str, limits)],
                                    capture_output=True, text=True, timeout=30, env=RUN_ENV)
            assert 'AddressSanitizer' not in result.stderr and 'runtime error:' not in result.stderr, result.stderr
            assert f'status={expected} ' in result.stdout, (name, result.returncode, result.stdout, result.stderr)
            assert (result.returncode == 0) == (expected == 'ok'), (name, result.stdout)
            checks.append({'name': name, 'result': result.stdout.strip()})
            return output, result.stdout

        def cancellation_cases():
            out, _ = run('solid-directory-control', rar5_crc(b'hello libarchive', directory=True, solid=True))
            assert (out / 'directory/checksum.txt').read_bytes() == b'hello libarchive'
            out, log = run('cancel-solid-output', fixture('test_read_format_rar5_multiple_files_solid.rar'),
                           'cancelled', 256 << 20, 1 << 30, 400000, 0, 48 << 30, 7)
            assert 'entries=1 ' in log and not list(out.rglob('*')), log
            out, log = run('cancel-extraction-output', rar4([('large.bin', b'x' * (1 << 20), 0o100644, 0)]),
                           'cancelled', 256 << 20, 1 << 30, 400000, 0, 48 << 30, 4)
            assert not list(out.rglob('*')), log

        if '--cancellation-only' in sys.argv:
            cancellation_cases()
            evidence = ROOT / 'build/hd-direct400/rar-reader-cancellation-tests.json'
            evidence.write_text(json.dumps({'checks': len(checks), 'sanitizers': SANITIZE, 'results': checks}, indent=2) + '\n')
            print('RAR P1 checks: solid directory and2 output-poll checks passed (ASan + UBSan).')
            return

        out, _ = run('rar4-stored', rar4([('GZLE01/tex1_fixture.png', b'PNG content', 0o100644, 0)]))
        assert (out / 'GZLE01/tex1_fixture.png').read_bytes() == b'PNG content'
        out, _ = run('rar4-compressed', rar4_first(fixture('test_read_format_rar_compress_normal.rar')))
        data = (out / 'LibarchiveAddingTest.html').read_bytes()
        assert len(data) == 20111 and data.endswith(b'</BODY>\n</HTML>')
        out, _ = run('rar5-crc-control', rar5_crc(b'hello libarchive'))
        assert (out / 'checksum.txt').read_bytes() == b'hello libarchive'
        out, _ = run('rar5-stored', fixture('test_read_format_rar5_stored.rar'))
        assert (out / 'helloworld.txt').read_bytes() == b'hello libarchive test suite!\n'
        out, _ = run('rar5-compressed', fixture('test_read_format_rar5_compressed.rar'))
        expected = b''.join(struct.pack('<I', max(0, k*k-3*k+1)) for k in range(1, 301))
        assert (out / 'test.bin').read_bytes() == expected
        out, _ = run('rar5-solid', fixture('test_read_format_rar5_multiple_files_solid.rar'))
        for magic in range(1, 5):
            expected = b''.join(struct.pack('<I', max(0, k*k-3*k+1+magic)) for k in range(1, 1025))
            assert (out / f'test{magic}.bin').read_bytes() == expected
        run('rar5-solid-seven', fixture('test_read_format_rar5_solid.rar'))
        run('rar5-blake2', fixture('test_read_format_rar5_blake2.rar'))
        for filename in ['test_read_format_rar4_encrypted.rar', 'test_read_format_rar5_encrypted.rar',
                         'test_read_format_rar5_solid_encrypted_filenames.rar',
                         'test_read_format_rar5_multiarchive_solid.part01.rar', 'test_read_format_rar.rar']:
            out, log = run(filename, fixture(filename), 'unsupported')
            assert not list(out.rglob('*')), (filename, log)
        run('rar4-volume', rar4([('a', b'x', 0o100644, 0)], 1), 'unsupported')
        run('rar4-solid-unsupported', rar4([('a', b'x', 0o100644, 0x10)], 8), 'unsupported')
        for i, name in enumerate(['../escape.png', '/absolute.png', 'C:\\escape.png', 'a//b.png', './a.png']):
            out, _ = run(f'unsafe-{i}', rar4([(name, b'x', 0o100644, 0)]), 'invalid')
            assert not list(out.rglob('*'))
        run('duplicate', rar4([('a.png', b'1', 0o100644, 0), ('a.png', b'2', 0o100644, 0)]), 'invalid')
        run('large-file', fixture('test_read_format_rar5_stored.rar'), 'limits', 256 << 20, 10)
        run('many-entries', fixture('test_read_format_rar5_multiple_files_solid.rar'), 'limits', 256 << 20, 1 << 30, 1)
        run('dictionary-budget', fixture('test_read_format_rar5_multiple_files_solid.rar'), 'limits', 1 << 20)
        run('tiny-budget', fixture('test_read_format_rar5_stored.rar'), 'limits', 1)
        out, log = run('total-before-solid-decode', fixture('test_read_format_rar5_multiple_files_solid.rar'),
                       'limits', 256 << 20, 1 << 30, 400000, 0, 8192)
        assert 'peak=0 ' in log and not list(out.rglob('*')), log
        run('cancelled', fixture('test_read_format_rar5_solid.rar'), 'cancelled', 256 << 20, 1 << 30, 400000, 1)
        out, _ = run('rar4-crc-control', rar4([('checksum.txt', b'hello libarchive', 0o100644, 0)]))
        data4 = rar4([('checksum.txt', b'hello libarchive', 0o100644, 0)]).replace(b'hello libarchive', b'jello libarchive')
        out, _ = run('bad-crc-rar4', data4, 'crc')
        assert not list(out.rglob('*'))
        zero_payload = bytes.fromhex('9d0ad96d')
        assert zlib.crc32(zero_payload) == 0
        out, _ = run('crc-zero-control', rar5_crc(zero_payload))
        assert (out / 'checksum.txt').read_bytes() == zero_payload
        zero_bad = rar5_crc(zero_payload).replace(zero_payload, b'bad!')
        out, _ = run('crc-zero-corrupt', zero_bad, 'crc')
        assert not list(out.rglob('*'))
        data = rar5_crc(b'hello libarchive').replace(b'hello libarchive', b'jello libarchive')
        out, _ = run('bad-crc', data, 'crc')
        assert not list(out.rglob('*')), 'partial failed file retained'
        run('truncated', fixture('test_read_format_rar5_compressed.rar')[:150], 'invalid')
        for name in ['test_read_format_rar5_bad_tables.rar', 'test_read_format_rar5_different_solid_window_size.rar']:
            archive = fixture(name)
            # Malformed decoder references must fail; exact decoder diagnostics differ.
            path = temp / name; path.write_bytes(archive); out = temp / (name + '-bad'); out.mkdir()
            result = subprocess.run([str(driver), str(path), str(out)], capture_output=True, text=True, timeout=30, env=RUN_ENV)
            assert result.returncode != 0 and 'status=ok ' not in result.stdout, result.stdout
            assert 'AddressSanitizer' not in result.stderr and 'runtime error:' not in result.stderr, result.stderr
            checks.append({'name': name, 'result': result.stdout.strip()})
        cancellation_cases()
        evidence = ROOT / 'build/hd-direct400/rar-reader-tests.json'
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text(json.dumps({'checks': len(checks), 'sanitizers': SANITIZE,
                                       'upstream': 'libarchive v3.8.10', 'results': checks}, indent=2) + '\n')
        print(f'RAR reader: {len(checks)} focused checks passed (ASan + UBSan).')


if __name__ == '__main__':
    main()
