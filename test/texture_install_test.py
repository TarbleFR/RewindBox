"""File-system core of the HD texture installer
(packages/neo_texture_catalog/ios/Classes/NeoTextureInstall.h): per-engine
file filters, import layout detection, staged extraction into the engines'
real folder layouts, the journaled swap with rollback and crash recovery,
and removal limited to the pack's own folder.
"""
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'test'))
import texture_7z_writer as sz  # noqa: E402

CLASSES = ROOT / 'packages/neo_texture_catalog/ios/Classes'
LZMA = ROOT / 'packages/neo_texture_catalog/ios/ThirdParty/lzma'
PNG = b'\x89PNG\r\n\x1a\n' + bytes(range(256)) * 64


def real_png(width, height):
    """A decodable RGBA PNG (Mesen reads each image's IHDR size)."""
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    raw = b''.join(b'\x00' + bytes(4 * width) for _ in range(height))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)) +
            chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))
DDS = b'DDS ' + bytes(124) + bytes(range(256)) * 8


def build(folder):
    errors = []
    for cxx in (os.environ.get('CXX'), 'clang++', 'g++'):
        if not cxx or not shutil.which(cxx):
            continue
        lzma = folder / 'lzma.o'
        driver = folder / 'install'
        steps = [[cxx, '-x', 'c', '-c', '-O1', '-fsanitize=address,undefined', '-fno-sanitize=alignment', f'-I{LZMA}',
                  str(CLASSES / 'NeoTextureLZMA.c'), '-o', str(lzma)],
                 [cxx, '-std=c++20', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined', f'-I{CLASSES}', f'-I{LZMA}',
                  str(ROOT / 'test/native/texture_install_driver.cpp'), str(lzma), '-lz', '-o', str(driver)]]
        result = None
        for step in steps:
            result = subprocess.run(step, capture_output=True, text=True)
            if result.returncode:
                break
        if result.returncode == 0:
            return driver
        errors.append(result.stderr[-800:])
    raise SystemExit('cannot build install driver:\n' + '\n'.join(errors))


def main():
    with tempfile.TemporaryDirectory() as temp:
        temp = Path(temp)
        driver = build(temp)
        checks = [0]

        def run(*args):
            result = subprocess.run([str(driver), *map(str, args)], capture_output=True, text=True)
            assert 'runtime error' not in result.stderr and 'Sanitizer' not in result.stderr, result.stderr
            checks[0] += 1
            return result.returncode, result.stdout.strip()

        def detect(engine, current, names):
            listing = temp / 'names.txt'
            listing.write_text('\n'.join(names) + '\n')
            return run('detect', engine, current, listing)[1]

        def zip_of(name, entries):
            path = temp / name
            with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
                for entry, data in entries:
                    z.writestr(entry, data)
            return path

        # Per-engine filters mirror what each engine reads.
        for engine, path, ok in (('dolphin', 'GZ2E01/tex1_64x64_abc_14.png', True), ('dolphin', 'GZ2E01/readme.png', False),
                                 ('dolphin', 'Pack/gameids/GZ2E01.txt', True), ('dolphin', 'Pack/notes.txt', False),
                                 ('dolphin', 'Pack/gameids/readme.txt', False), ('dolphin', 'Pack/all.txt', True),
                                 ('dolphin', 'Pack/GZ2.txt', True), ('dolphin', 'Pack/gz2e01.txt', False),
                                 ('armsx2', 'x/abc-def-00005494.png', True), ('armsx2', 'x/a.astc', True), ('armsx2', 'x/a.jpg', False),
                                 ('ppsspp', 'textures.ini', True), ('ppsspp', 'sub/textures.ini', False), ('ppsspp', 'a/b.zim', True),
                                 ('azahar', 'pack.json', True), ('azahar', 'sub/pack.json', False), ('azahar', 'tex1_1x1.png', True),
                                 # Azahar: extension compared exactly, at most three dot parts, pack.json exactly.
                                 ('azahar', 'a/tex1_1x1.PNG', False), ('azahar', 'tex1_1x1.norm.png', True),
                                 ('azahar', 'a.b.c.png', False), ('azahar', 'Pack.json', False), ('azahar', 'a/b.KTX', False),
                                 # GLideNHQ: Rice names (<ROM>#crc#fmt#siz...), ".png"/".bmp" exactly, hidden and "~!~" skipped.
                                 ('mupen64plus', 'SUPER MARIO 64/SUPER MARIO 64#2D3A1B6C#0#2_all.png', True),
                                 ('mupen64plus', 'SM64/SUPER MARIO 64#2D3A1B6C#0#2_rgb.bmp', True),
                                 ('mupen64plus', 'SM64/SUPER MARIO 64#2D3A1B6C#0#2_all.PNG', False),
                                 ('mupen64plus', 'SM64/preview.png', False), ('mupen64plus', 'SM64/#2D3A1B6C#0#2_all.png', False),
                                 ('mupen64plus', 'SM64/.hidden/SUPER MARIO 64#1#0#2_all.png', False),
                                 ('mupen64plus', 'SM64/~!~off/SUPER MARIO 64#1#0#2_all.png', False),
                                 # Beetle PSX HW: <hash>-<palette>.<ext> in hex, any of its decoders without
                                 # case, the folder's own entries only, and its prefetch journal.
                                 ('beetle', '1a2b3c4d-0.png', True), ('beetle', 'ABCD-1234.DDS', True),
                                 ('beetle', 'ff-ff.webp', True), ('beetle', '0-0.tga', True), ('beetle', 'prefetch.journal', True),
                                 ('beetle', 'sub/1a2b-0.png', False), ('beetle', '1a2b-0.gif', False),
                                 ('beetle', '123456789-0.png', False), ('beetle', 'readme.txt', False), ('beetle', 'g12-0.png', False),
                                 # Mesen: hires.txt and palette.dat at the pack root (exact names), the PNG,
                                 # OGG and IPS/UPS/BPS files hires.txt names, anywhere below.
                                 ('mesen', 'hires.txt', True), ('mesen', 'palette.dat', True), ('mesen', 'sub/hires.txt', False),
                                 ('mesen', 'Hires.txt', False), ('mesen', 'tiles/a.PNG', True), ('mesen', 'BGM/title.ogg', True),
                                 ('mesen', 'Megaman - Super.ips', True), ('mesen', 'fix.bps', True), ('mesen', 'readme.txt', False),
                                 ('mesen', 'preview.jpg', False)):
            assert (run('accepts', engine, path)[0] == 0) == ok, (engine, path)

        # Import layout detection.
        out = detect('dolphin', 'GZ2E01', ['Pack v2/GZ2E01/sub/tex1_a.png', 'README.txt'])
        assert 'rule=Pack v2/GZ2E01/>GZ2E01' in out and 'other=0' in out and 'problem= ' in out + ' ', out
        # A Game ID marker alone is no texture.
        assert 'problem=noTextures' in detect('dolphin', 'GZ2E01', ['Pack/gameids/GZ2E01.txt']), 'marker only'
        out = detect('dolphin', 'GZ2P01', ['GZ2/tex1_a.png'])
        assert 'rule=GZ2/>GZ2 ' in out + ' ' and 'other=0' in out, out
        out = detect('dolphin', 'GZ2P01', ['GZ2E01/tex1_a.png'])
        assert 'rule=GZ2E01/>GZ2P01' in out and 'other=1' in out and 'found=GZ2E01' in out, out
        out = detect('dolphin', 'GZ2P01', ['RMGE01/tex1_a.png'])
        assert 'problem=otherGame' in out, out
        out = detect('dolphin', 'GZ2E01', ['textures/tex1_a.png'])
        assert 'rule=>GZ2E01' in out and 'other=0' in out, out
        out = detect('armsx2', 'SLUS-21050', ['Pack/SLUS-21050/replacements/a.png', 'Pack/SLUS-21050/dumps/b.png'])
        assert 'rule=Pack/SLUS-21050/replacements/>SLUS-21050/replacements' in out and 'other=0' in out, out
        out = detect('armsx2', 'SLUS-21050', ['SLUS_210.50/a.png'])
        assert 'rule=SLUS_210.50/>SLUS-21050/replacements' in out, out
        out = detect('armsx2', 'SLUS-21050', ['SLES-53000/replacements/a.png'])
        assert 'other=1' in out and 'found=SLES-53000' in out, out
        out = detect('armsx2', 'SLUS-21050', ['textures/replacements/a.png'])
        assert 'rule=textures/replacements/>SLUS-21050/replacements' in out, out
        out = detect('ppsspp', 'ULUS10041', ['Pack/ULUS10041/textures.ini', 'Pack/ULUS10041/new/a.png'])
        assert 'rule=Pack/ULUS10041/>ULUS10041' in out and 'other=0' in out, out
        out = detect('ppsspp', 'ULUS10041', ['ULES00151/textures.ini', 'ULES00151/a.png'])
        assert 'other=1' in out and 'found=ULES00151' in out, out
        assert 'problem=missingIni' in detect('ppsspp', 'ULUS10041', ['a.png'])
        out = detect('azahar', '0004000000033500', ['load/textures/0004000000033500/pack.json', 'load/textures/0004000000033500/a.png'])
        assert 'rule=load/textures/0004000000033500/>0004000000033500' in out and 'other=0' in out, out
        out = detect('azahar', '0004000000033500', ['0004000000033600/a.png'])
        assert 'other=1' in out, out
        out = detect('azahar', '0004000000033500', ['MyPack/pack.json', 'MyPack/a.png'])
        assert 'rule=MyPack/>0004000000033500' in out, out

        # N64: the folder named after the ROM, else the folders holding the textures.
        rice = 'SUPER MARIO 64#2D3A1B6C#0#2_all.png'
        out = detect('mupen64plus', 'SUPER MARIO 64', [f'SM64 Reloaded/SUPER MARIO 64/a/{rice}', f'SM64 Reloaded/SUPER MARIO 64/{rice}',
                                                        'SM64 Reloaded/README.md'])
        assert 'rule=SM64 Reloaded/SUPER MARIO 64/>SUPER MARIO 64' in out and 'other=0' in out, out
        out = detect('mupen64plus', 'SUPER MARIO 64', [f'pack/hd/{rice}', f'pack/ui/{rice}'])
        assert 'rule=pack/>SUPER MARIO 64' in out and 'other=0' in out, out
        out = detect('mupen64plus', 'SUPER MARIO 64', ['THE LEGEND OF ZELDA/THE LEGEND OF ZELDA#1#0#2_all.png'])
        assert 'problem=otherGame' in out and 'found=THE LEGEND OF ZELDA' in out, out
        out = detect('mupen64plus', 'SUPER MARIO 64', [f'p/{rice}', 'p/SUPER MARIO 64 (J)#1#0#2_all.png'])
        assert 'other=1' in out, out
        assert 'problem=noTextures' in detect('mupen64plus', 'SUPER MARIO 64', ['p/readme.png'])
        # Beetle: the folder holding the texture names is installed as the
        # game's <content name>-texture-replacements; dumps and page-aligned
        # folders are never taken.
        current = 'Game (USA)-texture-replacements'
        out = detect('beetle', current, ['Castlevania (USA)-texture-replacements/1a2b-0.png',
                                         'Castlevania (USA)-texture-replacements/3c4d-ff.png',
                                         'Castlevania (USA)-texture-dump/9-9.png', 'Castlevania (USA)-texture-dump/8-8.png',
                                         'Castlevania (USA)-texture-dump/7-7.png', 'readme.txt'])
        assert f'rule=Castlevania (USA)-texture-replacements/>{current}' in out and 'problem= ' in out + ' ', out
        out = detect('beetle', current, ['1a2b-0.png', 'credits.txt'])
        assert f'rule=>{current}' in out, out
        assert 'problem=noTextures' in detect('beetle', current, ['Pack-texture-replacements-pages/1-2.png', 'x/readme.txt'])

        # Install into each engine's real layout from ZIP, 7z and a folder.
        dolphin = temp / 'Dolphin/User/Load/Textures'
        dolphin.mkdir(parents=True)
        pack = zip_of('d.zip', [('Pack/GZ2E01/sub/tex1_a.png', PNG), ('Pack/GZ2E01/tex1_b.dds', DDS), ('Pack/readme.txt', b'x'),
                                ('Pack/GZ2E01/preview.jpg', b'jpg')])
        code, out = run('install', 'dolphin', dolphin, pack, 'Pack/GZ2E01/=GZ2E01')
        assert code == 0 and 'files=2' in out, out
        assert (dolphin / 'GZ2E01/sub/tex1_a.png').read_bytes() == PNG and not (dolphin / 'GZ2E01/preview.jpg').exists()
        assert not list(dolphin.glob('.neostation-*')), list(dolphin.iterdir())
        # Marker layout (Dolphin's gameids/<ID>.txt): the pack keeps its own
        # top folder with the marker; excluded subfolders (sources, original
        # dumps) are never installed.
        marked = zip_of('m.zip', [('repo-1a2b/gameids/RMCE01.txt', b''), ('repo-1a2b/gameids/RMCP01.txt', b''),
                                  ('repo-1a2b/textures/tex1_a.png', PNG), ('repo-1a2b/originals/tex1_a.png', PNG),
                                  ('repo-1a2b/README.md', b'x')])
        code, out = run('install', 'dolphin', dolphin, marked, 'repo-1a2b/=MKWii-HD|originals/')
        assert code == 0 and 'files=3' in out, out
        assert (dolphin / 'MKWii-HD/gameids/RMCE01.txt').exists() and (dolphin / 'MKWii-HD/textures/tex1_a.png').exists()
        assert not (dolphin / 'MKWii-HD/originals').exists() and not (dolphin / 'MKWii-HD/README.md').exists()
        markers = zip_of('mo.zip', [('repo/gameids/GZ2E01.txt', b''), ('repo/README.md', b'x')])
        code, out = run('install', 'dolphin', dolphin, markers, 'repo/=Markers')
        assert code == 5 and 'noTextures' in out and not (dolphin / 'Markers').exists(), out
        # Update replaces the previous version atomically; the old files go.
        (dolphin / 'GZ2E01/old.png').write_bytes(PNG)
        pack2 = zip_of('d2.zip', [('GZ2E01/tex1_c.png', PNG)])
        code, out = run('install', 'dolphin', dolphin, pack2, 'GZ2E01/=GZ2E01')
        assert code == 0 and (dolphin / 'GZ2E01/tex1_c.png').exists() and not (dolphin / 'GZ2E01/sub').exists(), out
        assert not list(dolphin.glob('.neostation-*'))

        ps2 = temp / 'ARMSX2/textures'
        ps2.mkdir(parents=True)
        (ps2 / 'SLUS-21050/dumps').mkdir(parents=True)
        (ps2 / 'SLUS-21050/dumps/user-dump.png').write_bytes(PNG)
        archive = temp / 'p.7z'
        archive.write_bytes(sz.build([('SLUS-21050/replacements/1a2b-00005494.png', PNG),
                                      ('SLUS-21050/replacements/sub/3c4d-00005494.dds', DDS)], sz.LZMA2))
        code, out = run('install', 'armsx2', ps2, archive, 'SLUS-21050/replacements/=SLUS-21050/replacements')
        assert code == 0 and 'files=2' in out, out
        assert (ps2 / 'SLUS-21050/replacements/sub/3c4d-00005494.dds').read_bytes() == DDS
        assert (ps2 / 'SLUS-21050/dumps/user-dump.png').exists(), 'dumps must never be touched'
        # Removing the pack removes only replacements/; the folder stays for dumps.
        assert run('remove', ps2, 'SLUS-21050/replacements')[0] == 0
        assert not (ps2 / 'SLUS-21050/replacements').exists() and (ps2 / 'SLUS-21050/dumps/user-dump.png').exists()
        (ps2 / 'SLES-50000/replacements').mkdir(parents=True)
        (ps2 / 'SLES-50000/replacements/a.png').write_bytes(PNG)
        assert run('remove', ps2, 'SLES-50000/replacements')[0] == 0 and not (ps2 / 'SLES-50000').exists()

        psp = temp / 'Libretro/Saves/PPSSPP/PSP/TEXTURES'
        psp.mkdir(parents=True)
        source = temp / 'picked/ULUS10041'
        (source / 'new').mkdir(parents=True)
        (source / 'textures.ini').write_text('[options]\nversion = 1\nhash = quick\n')
        (source / 'new/a.png').write_bytes(PNG)
        (source / 'thumbs.db').write_bytes(b'x')
        code, out = run('install', 'ppsspp', psp, source.parent, 'ULUS10041/=ULUS10041')
        assert code == 0 and (psp / 'ULUS10041/textures.ini').exists() and not (psp / 'ULUS10041/thumbs.db').exists(), out

        n3ds = temp / 'Libretro/Saves/Azahar/Azahar/load/textures'
        n3ds.mkdir(parents=True)
        pack = zip_of('a.zip', [('0004000000033500/pack.json', b'{"options":{}}'), ('0004000000033500/tex1_a.png', PNG)])
        code, out = run('install', 'azahar', n3ds, pack, '0004000000033500/=0004000000033500')
        assert code == 0 and (n3ds / '0004000000033500/pack.json').exists(), out

        n64 = temp / 'Libretro/System/Mupen64plus/hires_texture'
        n64.mkdir(parents=True)
        pack = zip_of('n.zip', [(f'SM64/SUPER MARIO 64/{rice}', PNG), ('SM64/SUPER MARIO 64/notes.txt', b'x'),
                                ('SM64/SUPER MARIO 64/~!~disabled/SUPER MARIO 64#1#0#2_all.png', PNG)])
        code, out = run('install', 'mupen64plus', n64, pack, 'SM64/SUPER MARIO 64/=SUPER MARIO 64')
        assert code == 0 and 'files=1' in out and (n64 / 'SUPER MARIO 64' / rice).read_bytes() == PNG, out
        assert not (n64 / 'SUPER MARIO 64/notes.txt').exists() and not (n64 / 'SUPER MARIO 64/~!~disabled').exists()
        # Beetle: the core's save directory also holds the game's memory
        # cards; only <content>-texture-replacements is written or removed,
        # its files flat (a subfolder is not read by the core).
        beetle = temp / 'Libretro/Saves/Beetle PSX HW'
        beetle.mkdir(parents=True)
        (beetle / 'Game (USA).mcr').write_bytes(b'MC' + bytes(126))
        (beetle / 'Game (USA).1.mcr').write_bytes(b'MC' + bytes(126))
        pack = zip_of('b.zip', [('Game-texture-replacements/1a2b-0.png', PNG), ('Game-texture-replacements/3C4D-FF.dds', DDS),
                                ('Game-texture-replacements/prefetch.journal', b'TTPJ' + bytes(12)),
                                ('Game-texture-replacements/variants/5e6f-0.png', PNG), ('Game-texture-replacements/readme.txt', b'x')])
        code, out = run('install', 'beetle', beetle, pack, f'Game-texture-replacements/={current}')
        assert code == 0 and 'files=3' in out, out
        assert sorted(p.name for p in (beetle / current).iterdir()) == ['1a2b-0.png', '3C4D-FF.dds', 'prefetch.journal']
        assert (beetle / 'Game (USA).mcr').read_bytes() == b'MC' + bytes(126) and (beetle / 'Game (USA).1.mcr').exists()
        assert not list(beetle.glob('.neostation-*'))
        journal_only = zip_of('bj.zip', [('x-texture-replacements/prefetch.journal', b'TTPJ')])
        code, out = run('install', 'beetle', beetle, journal_only, f'x-texture-replacements/={current}')
        assert code == 5 and 'noTextures' in out and (beetle / current / '1a2b-0.png').exists(), out
        assert run('remove', beetle, current)[0] == 0 and not (beetle / current).exists()
        assert (beetle / 'Game (USA).mcr').exists() and (beetle / 'Game (USA).1.mcr').exists(), 'memory cards must stay'

        # Mesen: HdPacks/<content name>/, the folder of the shallowest
        # hires.txt (a variant's hires.txt below it is the author's option,
        # never read by the core); a pack without hires.txt is refused.
        out = detect('mesen', 'Contra (U)', ['Contra80s-v1.4.2/Contra (U) [!]/hires.txt', 'Contra80s-v1.4.2/Contra (U) [!]/a.png',
                                             'Contra80s-v1.4.2/Contra (U) [!]/alt/hires.txt', 'Contra80s-v1.4.2/README.md'])
        assert 'rule=Contra80s-v1.4.2/Contra (U) [!]/>Contra (U)' in out and 'problem= ' in out + ' ', out
        assert 'problem=missingHires' in detect('mesen', 'Contra (U)', ['pack/a.png', 'pack/readme.txt'])
        nes = temp / 'Libretro/System/HdPacks'
        nes.mkdir(parents=True)
        hires = ('<ver>106\n<scale>2\n<supportedRom>c9ea66bb7cb30ad5343f1721b1d4d3219859319b\n<img>tiles/a.png\n'
                 '[hud]<background>Stage1.png,1.0\n<patch>fix.ips,2F88381557339A14C20428455F6991C1EB902C99\n'
                 '<bgm>0,1,BGM\\title.ogg\n<tile>0,0,0F161616,0,0,1,N\n')
        tile = real_png(16, 16)
        pack = zip_of('m.zip', [('Pack/Contra (U) [!]/hires.txt', hires), ('Pack/Contra (U) [!]/tiles/a.png', tile),
                                ('Pack/Contra (U) [!]/fix.ips', b'PATCH' + b'EOF'), ('Pack/Contra (U) [!]/BGM/title.ogg', b'OggS' + bytes(60)),
                                ('Pack/Contra (U) [!]/notes.txt', b'x'), ('Pack/screenshot.png', PNG)])
        code, out = run('install', 'mesen', nes, pack, 'Pack/Contra (U) [!]/=Contra (U)')
        assert code == 0 and 'files=4' in out, out
        assert sorted(str(p.relative_to(nes / 'Contra (U)')) for p in (nes / 'Contra (U)').rglob('*') if p.is_file()) == \
            ['BGM/title.ogg', 'fix.ips', 'hires.txt', 'tiles/a.png'], out
        # What the core would refuse or could not hold, read from the folder.
        code, out = run('mesencheck', nes / 'Contra (U)')
        assert code == 0 and 'ver=106 scale=2' in out and f'decoded={16 * 16 * 4}' in out, out
        assert 'skipped=1' in out and 'missing=0' in out, out          # Stage1.png: the core skips a missing background
        assert 'rom=2F88381557339A14C20428455F6991C1EB902C99' in out and 'rom=C9EA66BB7CB30AD5343F1721B1D4D3219859319B' in out, out
        mesen2 = temp / 'mesen2'
        mesen2.mkdir()
        (mesen2 / 'hires.txt').write_text('<ver>108\n<img>a.png\n')
        (mesen2 / 'a.png').write_bytes(tile)
        assert 'problem=formatTooNew' in run('mesencheck', mesen2)[1]
        (mesen2 / 'hires.txt').write_text('<ver>106\n<img>a.png\n<img>sub\\missing.png\n')
        assert 'problem=missingFiles' in run('mesencheck', mesen2)[1]
        (mesen2 / 'hires.txt').write_text('<ver>106\n<img>../outside.png\n')
        assert 'problem=missingFiles' in run('mesencheck', mesen2)[1]
        (mesen2 / 'hires.txt').write_text('<ver>106\n<img>a.png\n')
        (mesen2 / 'a.png').write_bytes(b'not a png at all, but long enough')
        assert 'problem=archiveDamaged' in run('mesencheck', mesen2)[1]
        assert 'problem=missingHires' in run('mesencheck', temp / 'Libretro/System')[1]
        assert run('remove', nes, 'Contra (U)')[0] == 0 and not (nes / 'Contra (U)').exists()

        # Refusals leave the installed pack untouched and no staging behind.
        before = sorted(p.name for p in (dolphin / 'GZ2E01').iterdir())
        bad = zip_of('bad.zip', [('GZ2E01/tex1_bad.png', b'not a png at all')])
        code, out = run('install', 'dolphin', dolphin, bad, 'GZ2E01/=GZ2E01')
        assert code == 4 and 'signature' in out, out
        empty = zip_of('empty.zip', [('GZ2E01/readme.txt', b'x')])
        code, out = run('install', 'dolphin', dolphin, empty, 'GZ2E01/=GZ2E01')
        assert code == 5 and 'noTextures' in out, out
        rar = temp / 'x.rar'
        rar.write_bytes(b'Rar!\x1a\x07\x00' + bytes(64))
        code, out = run('install', 'dolphin', dolphin, rar, 'GZ2E01/=GZ2E01')
        assert code == 3 and 'rar' in out, out
        dup = temp / 'dup.zip'
        with zipfile.ZipFile(dup, 'w') as z:
            z.writestr('GZ2E01/tex1_a.png', PNG)
            z.writestr('GZ2E01/TEX1_A.PNG'.replace('TEX1', 'tex1'), PNG)
        code, out = run('install', 'dolphin', dolphin, dup, 'GZ2E01/=GZ2E01')
        assert code == 3 and 'duplicate' in out, out
        assert sorted(p.name for p in (dolphin / 'GZ2E01').iterdir()) == before
        assert not list(dolphin.glob('.neostation-*'))
        # A link anywhere on the target path is refused.
        outside = temp / 'outside'
        outside.mkdir()
        (dolphin / 'LINKED').symlink_to(outside, target_is_directory=True)
        pack = zip_of('l.zip', [('X/tex1_a.png', PNG)])
        code, out = run('install', 'dolphin', dolphin, pack, 'X/=LINKED/inner')
        assert code == 5 and 'unsafeTarget' in out and not list(outside.iterdir()), out
        assert run('remove', dolphin, 'LINKED/inner')[0] == 1
        (dolphin / 'LINKED').unlink()

        # Crash recovery: a swap interrupted after moving the old folder aside
        # puts it back; leftover staging is cleared.
        (dolphin / 'GZ2E01').rename(dolphin / '.neostation-previous-deadbeef')
        (dolphin / '.neostation-staging-cafe').mkdir()
        (dolphin / '.neostation-swap.journal').write_text(f'{dolphin}/GZ2E01\t{dolphin}/.neostation-previous-deadbeef\n')
        assert run('recover', dolphin)[0] == 0
        assert (dolphin / 'GZ2E01/tex1_c.png').exists() and not list(dolphin.glob('.neostation-*'))
        print(f'PASS texture install: {checks[0]} checks (engine file filters, import layout detection for Dolphin/ARMSX2/'
              'PPSSPP/Azahar/Mupen64Plus-Next/Beetle PSX HW/Mesen incl. region-free, other region and other game, ZIP/7z/folder installs into the real '
              'layouts incl. Dolphin Game ID markers and excluded subfolders, update, removal limited to the pack folder with PS2 dumps '
              'and PS1 memory cards kept, Mesen hires.txt version/missing image/damaged image/decoded size/ROM SHA-1, '
              'signature/empty/RAR/duplicate/'
              'link refusals without side effects, crash recovery)')


if __name__ == '__main__':
    main()
