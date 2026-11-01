#!/usr/bin/env python3
"""RetroAchievements disc identification through .chd and .cso images.

Builds the pinned rcheevos copy, the vendored libchdr and RBDiscHashReader.c
into a small host program (with AddressSanitizer/UBSan), creates synthetic
discs (PlayStation, PlayStation 2, PSP, Saturn, PC Engine CD, Dreamcast) and
checks that a game compressed to .chd (chdman) or .cso gives exactly the hash
rcheevos computes for the original .cue/.bin, .gdi or .iso. Before this
reader, rcheevos read a .chd/.cso as a raw image and never recognized it.

Requires gcc, zlib headers, chdman (mame-tools) and genisoimage; skipped
otherwise. Synthetic data only: no game, BIOS or account data is involved.
"""

import os
import pathlib
import random
import shutil
import struct
import subprocess
import tempfile
import unittest
import zlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
BRIDGE = ROOT / 'packages/libretro_internal_bridge/ios'
RCHEEVOS = BRIDGE / 'ThirdParty/rcheevos'
LIBCHDR = BRIDGE / 'ThirdParty/libchdr'
READER = BRIDGE / 'Classes/RBDiscHashReader.c'

PSX, PS2, PSP, SATURN, SEGA_CD, PCE_CD, DREAMCAST = 12, 21, 41, 39, 9, 76, 40

SYNC = b'\x00' + b'\xff' * 10 + b'\x00'

CLI_SOURCE = r'''
#include <stdio.h>
#include <stdlib.h>
#include "RBDiscHashReader.h"
int main(int argc, char **argv) {
  char hash[33];
  int ok;
  if (argc < 3) return 2;
  if (argc > 3) {
    rc_hash_iterator_t it;
    rc_hash_initialize_iterator(&it, argv[2], NULL, 0);
    ok = rc_hash_generate(hash, (uint32_t)atoi(argv[1]), &it);
    rc_hash_destroy_iterator(&it);
  } else {
    ok = rb_hash_generate_for_file(hash, (uint32_t)atoi(argv[1]), argv[2]);
  }
  printf("%s\n", ok ? hash : "FAIL");
  return 0;
}
'''


def _bcd(value):
    return ((value // 10) << 4) | (value % 10)


def _msf(lba):
    absolute = lba + 150
    return bytes([_bcd(absolute // 4500), _bcd((absolute // 75) % 60), _bcd(absolute % 75)])


def mode1_raw(data, lba):
    assert len(data) == 2048
    return SYNC + _msf(lba) + b'\x01' + data + b'\x00' * 288


def mode2_form1_raw(data, lba):
    assert len(data) == 2048
    return SYNC + _msf(lba) + b'\x02' + b'\x00\x00\x08\x00' * 2 + data + b'\x00' * 280


def sectors(blob):
    blob += b'\x00' * (-len(blob) % 2048)
    return [blob[i:i + 2048] for i in range(0, len(blob), 2048)]


def msf_text(frames):
    return '%02d:%02d:%02d' % (frames // 4500, (frames // 75) % 60, frames % 75)


def write_cso(iso, target, version=1, align=0, block_size=2048):
    """CISO v0/v1: zlib raw deflate blocks, plain blocks flagged in bit 31."""
    data = pathlib.Path(iso).read_bytes()
    blocks = [data[i:i + block_size] for i in range(0, len(data), block_size)]
    header = b'CISO' + struct.pack('<IQIBBH', 24, len(data), block_size, version, align, 0)
    index_size = (len(blocks) + 1) * 4
    position = 24 + index_size
    index, payload = [], bytearray()
    for block in blocks:
        pad = (-position) % (1 << align)
        payload += b'\x00' * pad
        position += pad
        compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
        packed = compressor.compress(block) + compressor.flush()
        if len(packed) >= len(block):
            index.append((position >> align) | 0x80000000)
            payload += block
            position += len(block)
        else:
            index.append(position >> align)
            payload += packed
            position += len(packed)
    pad = (-position) % (1 << align)
    payload += b'\x00' * pad
    position += pad
    index.append(position >> align)
    pathlib.Path(target).write_bytes(header + b''.join(struct.pack('<I', e) for e in index) + payload)


@unittest.skipUnless(all(shutil.which(tool) for tool in ('gcc', 'chdman', 'genisoimage'))
                     and pathlib.Path('/usr/include/zlib.h').exists(),
                     'gcc, zlib, chdman and genisoimage are required')
class DiscHashReaderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = pathlib.Path(tempfile.mkdtemp(prefix='ra-disc-hash-'))
        cls.rng = random.Random(611)
        objects = []
        flags = ['-g', '-O1', '-std=c99', '-D_GNU_SOURCE', '-fsanitize=address,undefined',
                 '-fno-omit-frame-pointer']
        sources = [READER]
        sources += sorted((RCHEEVOS / 'src/rhash').glob('*.c'))
        sources += [p for p in sorted((RCHEEVOS / 'src').glob('*.c')) if p.name != 'rc_libretro.c']
        sources += sorted((RCHEEVOS / 'src/rcheevos').glob('*.c'))
        sources += sorted((RCHEEVOS / 'src/rapi').glob('*.c'))
        sources += sorted((LIBCHDR / 'src').glob('*.c'))
        sources += [LIBCHDR / 'deps/lzma-26.02/src/LzmaDec.c', LIBCHDR / 'deps/zstd-1.5.7/zstddeclib.c']
        includes = ['-I%s' % (RCHEEVOS / 'include'), '-I%s' % (RCHEEVOS / 'src'),
                    '-I%s' % (LIBCHDR / 'include'), '-I%s' % (BRIDGE / 'Classes')]
        defines = ['-DRC_CLIENT_SUPPORTS_HASH=1', '-DCHDR_SYSTEM_ZLIB', '-DZSTD_DISABLE_ASM']
        for index, source in enumerate(sources):
            obj = cls.tmp / ('%03d.o' % index)
            warnings = ['-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter'] if source == READER else ['-w']
            subprocess.run(['gcc', '-c', *flags, *warnings, *defines, *includes, str(source), '-o', str(obj)],
                           check=True)
            objects.append(str(obj))
        cli = cls.tmp / 'cli.c'
        cli.write_text(CLI_SOURCE)
        cls.cli = cls.tmp / 'hash_cli'
        subprocess.run(['gcc', *flags, *includes, str(cli), *objects, '-lz', '-lm', '-o', str(cls.cli)],
                       check=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def hash(self, console, path, default_reader=False):
        args = [str(self.cli), str(console), str(path)] + (['default'] if default_reader else [])
        env = dict(os.environ, ASAN_OPTIONS='detect_leaks=1:abort_on_error=1',
                   UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1')
        run = subprocess.run(args, capture_output=True, text=True, env=env, timeout=120)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertNotIn('runtime error', run.stderr)
        return run.stdout.strip()

    def iso(self, name, files, extra=()):
        folder = self.tmp / (name + '-files')
        for relative, content in files.items():
            target = folder / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        out = self.tmp / (name + '.iso')
        subprocess.run(['genisoimage', '-quiet', '-iso-level', '2', '-V', name.upper()[:16], *extra,
                        '-o', str(out), str(folder)], check=True)
        return out

    def chd(self, source, kind='createcd'):
        out = source.with_suffix('.chd')
        subprocess.run(['chdman', kind, '-f', '-i', str(source), '-o', str(out)], check=True,
                       capture_output=True)
        return out

    def random_bytes(self, size):
        return bytes(self.rng.getrandbits(8) for _ in range(size))

    def assert_same(self, console, reference, *others, reference_default=True):
        expected = self.hash(console, reference, default_reader=reference_default)
        self.assertRegex(expected, r'^[0-9a-f]{32}$')
        # The wrapper is transparent for formats rcheevos already reads.
        self.assertEqual(self.hash(console, reference), expected)
        for other in others:
            self.assertEqual(self.hash(console, other), expected, other.name)
            # Proof of the bug: without the reader the compressed image fails.
            self.assertNotEqual(self.hash(console, other, default_reader=True), expected, other.name)
        return expected

    # ------------------------------------------------------------ discs

    def psx_cue(self, name='psx'):
        exe = bytearray(b'PS-X EXE' + self.random_bytes(0x2000 + 2048 - 8))
        exe[28:32] = struct.pack('<I', 0x2000)
        iso = self.iso(name, {
            'SYSTEM.CNF': b'BOOT = cdrom:\\SLUS_123.45;1\r\nTCB = 4\r\nEVENT = 10\r\n',
            'SLUS_123.45': bytes(exe),
        })
        data = sectors(iso.read_bytes())
        track1 = b''.join(mode2_form1_raw(s, lba) for lba, s in enumerate(data))
        audio = self.random_bytes(2352 * 75)
        pregap = b'\x00' * (2352 * 150)
        (self.tmp / (name + '.bin')).write_bytes(track1 + pregap + audio)
        frames = len(data)
        cue = self.tmp / (name + '.cue')
        cue.write_text('FILE "%s.bin" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n'
                       '  TRACK 02 AUDIO\n    INDEX 00 %s\n    INDEX 01 %s\n'
                       % (name, msf_text(frames), msf_text(frames + 150)))
        return cue

    def test_playstation_chd_matches_cue(self):
        cue = self.psx_cue()
        chd = self.chd(cue)
        self.assert_same(PSX, cue, chd)

    def test_playstation_m3u_playlist_of_chd(self):
        cue = self.psx_cue('psxm3u')
        chd = self.chd(cue)
        playlist = self.tmp / 'psxm3u.m3u'
        playlist.write_text(chd.name + '\n')
        self.assertEqual(self.hash(PSX, playlist), self.hash(PSX, cue, default_reader=True))

    def test_saturn_and_sega_cd_chd_match_cue(self):
        for console, marker, name in ((SATURN, b'SEGA SEGASATURN ', 'saturn'),
                                      (SEGA_CD, b'SEGADISCSYSTEM  ', 'segacd')):
            first = marker + self.random_bytes(2048 - len(marker))
            data = [first] + [self.random_bytes(2048) for _ in range(40)]
            track1 = b''.join(mode1_raw(s, lba) for lba, s in enumerate(data))
            (self.tmp / (name + '.bin')).write_bytes(track1 + self.random_bytes(2352 * 30))
            cue = self.tmp / (name + '.cue')
            cue.write_text('FILE "%s.bin" BINARY\n  TRACK 01 MODE1/2352\n    INDEX 01 00:00:00\n'
                           '  TRACK 02 AUDIO\n    INDEX 01 %s\n' % (name, msf_text(len(data))))
            self.assert_same(console, cue, self.chd(cue))

    def pce_cue(self, name, stored_pregap):
        audio_frames = 300
        header = bytearray(2048)
        header[0:4] = bytes([0, 0, 2, 3])  # program at track sector 2, 3 sectors
        header[32:55] = b'PC Engine CD-ROM SYSTEM'
        header[106:128] = b'SYNTHETIC TEST DISC   '
        data = [self.random_bytes(2048), bytes(header)] + [self.random_bytes(2048) for _ in range(30)]
        start = audio_frames + 150  # index 01 of track 2
        track2 = b''.join(mode1_raw(s, start + i) for i, s in enumerate(data))
        audio = self.random_bytes(2352 * audio_frames)
        if stored_pregap:
            pregap = b''.join(mode1_raw(b'\x00' * 2048, audio_frames + i) for i in range(150))
            (self.tmp / (name + '.bin')).write_bytes(audio + pregap + track2)
            gap = '    INDEX 00 %s\n    INDEX 01 %s\n' % (msf_text(audio_frames), msf_text(audio_frames + 150))
        else:
            (self.tmp / (name + '.bin')).write_bytes(audio + track2)
            gap = '    PREGAP 00:02:00\n    INDEX 01 %s\n' % msf_text(audio_frames)
        cue = self.tmp / (name + '.cue')
        cue.write_text('FILE "%s.bin" BINARY\n  TRACK 01 AUDIO\n    INDEX 01 00:00:00\n'
                       '  TRACK 02 MODE1/2352\n%s' % (name, gap))
        return cue

    def test_pc_engine_cd_chd_with_stored_and_implicit_pregap(self):
        for stored in (True, False):
            cue = self.pce_cue('pce%d' % stored, stored)
            self.assert_same(PCE_CD, cue, self.chd(cue))

    def test_dreamcast_gdrom_chd_matches_gdi(self):
        ip = bytearray(b' ' * 32768)
        ip[0:16] = b'SEGA SEGAKATANA '
        ip[0x60:0x70] = b'1ST_READ.BIN    '
        ip[0x80:0x90] = b'SYNTHETIC GDROM '
        (self.tmp / 'ip.bin').write_bytes(bytes(ip))
        iso = self.iso('dc', {'1ST_READ.BIN': self.random_bytes(70000), 'DATA.BIN': self.random_bytes(5000)},
                       extra=('-C', '0,45000', '-G', str(self.tmp / 'ip.bin')))
        data = sectors(iso.read_bytes())
        folder = self.tmp / 'gdi'
        folder.mkdir(exist_ok=True)
        (folder / 'track01.bin').write_bytes(b''.join(mode1_raw(self.random_bytes(2048), i) for i in range(300)))
        (folder / 'track02.raw').write_bytes(self.random_bytes(2352 * 300))
        (folder / 'track03.bin').write_bytes(b''.join(mode1_raw(s, 45000 + i) for i, s in enumerate(data)))
        gdi = folder / 'disc.gdi'
        gdi.write_text('3\n1 0 4 2352 track01.bin 0\n2 450 0 2352 track02.raw 0\n'
                       '3 45000 4 2352 track03.bin 0\n')
        self.assert_same(DREAMCAST, gdi, self.chd(gdi))

    def test_playstation_2_dvd_chd_matches_iso(self):
        elf = b'\x7fELF' + self.random_bytes(150000)
        iso = self.iso('ps2', {'SYSTEM.CNF': b'BOOT2 = cdrom0:\\SLUS_200.01;1\r\nVER = 1.00\r\n',
                               'SLUS_200.01': elf})
        self.assert_same(PS2, iso, self.chd(iso, 'createdvd'))

    def test_psp_cso_and_dvd_chd_match_iso(self):
        compressible = b'PSP' * 20000
        iso = self.iso('psp', {'PSP_GAME/PARAM.SFO': b'\x00PSF' + self.random_bytes(700),
                               'PSP_GAME/SYSDIR/EBOOT.BIN': self.random_bytes(90000) + compressible,
                               'PSP_GAME/USRDIR/DATA.BIN': compressible})
        variants = []
        for version, align in ((1, 0), (0, 2), (1, 4)):
            target = self.tmp / ('psp-v%d-a%d.cso' % (version, align))
            write_cso(iso, target, version=version, align=align)
            variants.append(target)
        self.assert_same(PSP, iso, *variants, self.chd(iso, 'createdvd'))

    # -------------------------------------------------------- robustness

    def test_damaged_or_foreign_images_fail_cleanly(self):
        garbage = self.tmp / 'garbage.chd'
        garbage.write_bytes(self.random_bytes(100000))
        self.assertEqual(self.hash(PSX, garbage), 'FAIL')
        cue = self.psx_cue('psxcut')
        chd = self.chd(cue)
        truncated = self.tmp / 'truncated.chd'
        truncated.write_bytes(chd.read_bytes()[:len(chd.read_bytes()) // 2])
        self.assertNotEqual(self.hash(PSX, truncated), self.hash(PSX, cue, default_reader=True))
        iso = self.iso('pspcut', {'PSP_GAME/PARAM.SFO': b'\x00PSF' + self.random_bytes(500),
                                  'PSP_GAME/SYSDIR/EBOOT.BIN': self.random_bytes(30000)})
        cso = self.tmp / 'pspcut.cso'
        write_cso(iso, cso)
        cut = self.tmp / 'pspcut-truncated.cso'
        cut.write_bytes(cso.read_bytes()[:len(cso.read_bytes()) // 3])
        self.assertEqual(self.hash(PSP, cut), 'FAIL')
        v2 = self.tmp / 'pspcut-v2.cso'
        write_cso(iso, v2, version=2)
        self.assertEqual(self.hash(PSP, v2), 'FAIL')
        missing = self.tmp / 'missing.chd'
        self.assertEqual(self.hash(PSX, missing), 'FAIL')



class DiscReaderWiringContractTest(unittest.TestCase):
    """The pieces the device build relies on (checked without compiling)."""

    def read(self, relative):
        return (ROOT / relative).read_text(encoding='utf-8')

    def test_in_game_client_and_library_use_the_same_reader(self):
        client = self.read('packages/libretro_internal_bridge/ios/Classes/LibretroAchievements.m')
        self.assertIn('rb_hash_install_disc_reader(&hashCallbacks);', client)
        self.assertIn('rc_client_set_hash_callbacks(_client, &hashCallbacks);', client)
        self.assertNotIn('rc_hash_init_default_cdreader', client)
        plugin = self.read('packages/libretro_internal_bridge/ios/Classes/LibretroInternalBridgePlugin.m')
        self.assertIn('[call.method isEqualToString:@"retroAchievementsHash"]', plugin)
        self.assertIn('rb_hash_generate_for_file(hash, consoleId, file.fileSystemRepresentation)', plugin)
        dart = self.read('lib/services/retro_achievements_identity.dart')
        self.assertIn("MethodChannel('neostation/libretro_internal')", dart)
        self.assertIn("'retroAchievementsHash', {'path': path, 'consoleId': consoleId}", dart)
        self.assertIn('static NSString *const kLibretroChannel = @"neostation/libretro_internal";', plugin)

    def test_podspec_and_syntax_check_compile_the_reader_and_libchdr(self):
        podspec = self.read('packages/libretro_internal_bridge/ios/libretro_internal_bridge.podspec')
        for needle in ("'Classes/**/*.{h,m,c}'", "'ThirdParty/libchdr/src/*.c'",
                       "'ThirdParty/libchdr/deps/lzma-26.02/src/LzmaDec.c'",
                       "'ThirdParty/libchdr/deps/zstd-1.5.7/zstddeclib.c'",
                       'ThirdParty/libchdr/include', 'CHDR_SYSTEM_ZLIB=1', 'ZSTD_DISABLE_ASM=1',
                       'RC_CLIENT_SUPPORTS_HASH=1', "s.libraries = 'z'"):
            self.assertIn(needle, podspec)
        # Only the wrapper LzmaDec.c is compiled; the real one is included by it.
        self.assertNotIn('lzma-26.02/src/real', podspec)
        syntax = self.read('test/libretro_ios_syntax_test.py')
        self.assertIn('DISC_READER_SOURCES', syntax)
        self.assertIn("'CHDR_SYSTEM_ZLIB=1', 'ZSTD_DISABLE_ASM=1'", syntax)
        notice = self.read('packages/libretro_internal_bridge/ios/ThirdParty/libchdr/NEOSTATION_NOTICE.md')
        self.assertIn('47d794151b2b64f6aba60304e6480f4f5a2bc24b', notice)
        for license_file in ('LICENSE.txt', 'deps/lzma-26.02/LICENSE'):
            self.assertTrue((LIBCHDR / license_file).is_file(), license_file)

    def test_engines_publish_the_loaded_game_id(self):
        libretro = self.read('packages/libretro_internal_bridge/ios/Classes/LibretroAchievements.m')
        self.assertIn('atomic_store(&achievements->_gameId, game->id);', libretro)
        self.assertIn('@"gameId": @(atomic_load(&_gameReady) ? atomic_load(&_gameId) : 0u)', libretro)
        rpcs3 = self.read('packages/rpcs3_internal_bridge/ios/Classes/Rpcs3Achievements.mm')
        self.assertIn('achievements->_gameId.store(game->id);', rpcs3)
        self.assertIn('@"gameId": @(_gameReady.load() ? _gameId.load() : 0u)', rpcs3)
        hub = self.read('packages/retro_achievements_session/ios/Classes/RetroAchievementsSessionPlugin.m')
        self.assertIn('@"gameId"', hub)
        for service, needle in (('lib/services/libretro_internal_service.dart', 'contentPath: romPath'),
                                ('lib/services/stikjit_armsx2_service.dart', 'contentPath: bootBios ? null : gamePath'),
                                ('lib/services/rpcs3_internal_service.dart', 'contentPath: contentPath'),
                                ('lib/services/rpcs3_launch_service.dart', 'contentPath: sourcePath')):
            self.assertIn(needle, self.read(service), service)


if __name__ == '__main__':
    unittest.main()
