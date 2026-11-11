#!/usr/bin/env python3
"""Compares rb_s2arm_ns2_dump with S2Arm's pack/ns2_dump.py on synthetic export folders (CI only).

Usage: run_ns2_dump_test.py <s2arm_checkout> <s2arm_prepare_cli> <nx_unpack command> <work_dir> [<ZbicTest command>]
       run_ns2_dump_test.py --mine-only <s2arm_prepare_cli> <work_dir>   (local: our side and the hand checks only)

<nx_unpack command> is an executable running S2Arm's nx_unpack (ns2_dump.py hands ZBIC NSOs to
it through S2A_NX_UNPACK); <ZbicTest command> runs S2Arm's tests/nx_unpack_zbic (its --emit
samples are added as cases). Every export folder is built here (no game content): fake NSO
headers, the synthetic modules of make_synth_nso.py, ZBIC modules from make_synth_zbic.py,
an NPDM with only the fields read. For each case both sides convert the same folder; a
success needs the same tree (names, directories, bytes; the content of .ns2_dump_key is
excluded, see s2arm_ns2_dump.h), a failure of the original needs a failure of ours.
"""
import os
import random
import shutil
import struct
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import make_synth_nso as synth  # noqa: E402
import make_synth_zbic as zbic  # noqa: E402

TID = 0x040074A01BF12000
state = {'ran': 0, 'failed': 0}


def report(ok, name, detail):
    state['ran'] += 1
    state['failed'] += not ok
    print(f"{'ok  ' if ok else 'FAIL'} {name} ({detail})", flush=True)


def w(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def npdm(tid):
    b = bytearray(0x200)
    b[:4] = b'META'
    struct.pack_into('<II', b, 0x70, 0x100, 0x40)
    b[0x100:0x104] = b'ACI0'
    struct.pack_into('<Q', b, 0x110, tid)
    return bytes(b)


def nso(build, flags=0x3F, text=b''):
    """A fake NSO header (as S2Arm's own test builds); text goes uncompressed into the first segment."""
    b = bytearray(0x100)
    b[:4] = b'NSO0'
    struct.pack_into('<I', b, 0x0C, flags & ~7 if text else flags)
    b[0x40:0x50] = build
    if text:
        struct.pack_into('<III', b, 0x10, 0x100, 0, len(text))
        struct.pack_into('<I', b, 0x60, len(text))
    return bytes(b) + text


def nacp(title0=b'', title13=b'', title14=b'', version=b''):
    n = bytearray(0x4000)
    for lang, t in ((0, title0), (13, title13), (14, title14)):
        n[lang * 0x300:lang * 0x300 + len(t)] = t
    n[0x3060:0x3060 + len(version)] = version
    struct.pack_into('<Q', n, 0x3078, TID)
    return bytes(n)


def mk(root, full=True, updates=('65536', '458752')):
    """The layout of S2Arm's own tests/ns2_dump_test.sh: base, two updates, a DLC and another game's DLC."""
    root = Path(root)
    w(root / '.listing', b'x')
    w(root / 'base/exefs/main', nso(b'\x11' * 16))
    w(root / 'base/exefs/main.npdm', npdm(TID))
    w(root / 'base/exefs/.listing', b'x')
    w(root / 'base/romfs/A/a.bin', b'base-a')
    w(root / 'base/romfs/B/b.bin', b'base-b')
    w(root / 'base/romfs/S/old.Product.100.bin', b'stale')
    for v in updates:
        u = root / 'updates' / v
        w(u / 'exefs/main', nso(bytes([int(v) % 251]) * 16))
        w(u / 'exefs/main.npdm', npdm(TID))
        w(u / 'exefs/sdk', nso(b'\x22' * 16))
        w(u / 'romfs/A/a.bin', b'upd-a-' + v.encode())
        w(u / 'romfs/C/c.bin', b'upd-c')
        if full:
            w(u / 'romfs/B/b.bin', b'base-b')
    w(root / 'dlc/040074a01bf13001/0/romfs/d.bin', b'dlc1')
    w(root / 'dlc/040074a01bf13001/.listing', b'x')
    w(root / 'dlc/0100000000001001/0/romfs/x.bin', b'other')
    return root


SYM = b'\0_ZN2nn2fs21MountTemporaryStorageEPKc\0_ZN2nn2fs19MountDeviceSaveDataEPKc\0'


def lz4_subsdk():
    import lz4.block
    comp = lz4.block.compress(b'pad' * 64 + b'\0_ZN2nn2fs17MountCacheStorageEPKc\0', store_size=False)
    sd = bytearray(nso(b'\x56' * 16))
    struct.pack_into('<III', sd, 0x10, 0x100, 0, 3 * 64 + 35)
    struct.pack_into('<I', sd, 0x60, len(comp))
    struct.pack_into('<I', sd, 0x0C, 0x39)
    return bytes(sd) + comp


def zbic_module(seed, extra=0, code=None, hashes=True):
    return zbic.zbic_nso(synth.build(code, dynamic=True), random.Random(seed), extra_flags=extra, hashes=hashes)


def tree(root):
    """{relative path: bytes or 'dir'}; .ns2_dump_key compared by presence only."""
    out = {}
    root = Path(root)
    if not root.is_dir():
        return None
    for p in sorted(root.rglob('*')):
        rel = str(p.relative_to(root))
        if p.is_dir() and not p.is_symlink():
            out[rel + '/'] = 'dir'
        elif p.name == '.ns2_dump_key':
            out[rel] = 'key'
        else:
            out[rel] = p.read_bytes()
    return out


class Runner:
    def __init__(self, checkout, cli, nxu, work, mine_only):
        self.checkout, self.cli, self.nxu, self.work, self.mine_only = checkout, cli, nxu, work, mine_only

    def reference(self, export, out, args, env_nxu=True):
        env = {k: v for k, v in os.environ.items() if not k.startswith('S2A_')}
        if env_nxu and self.nxu:
            env['S2A_NX_UNPACK'] = str(self.nxu)
        r = subprocess.run([sys.executable, str(self.checkout / 'pack/ns2_dump.py'), str(export), str(out), *args],
                           capture_output=True, text=True, env=env)
        return r.returncode, (r.stdout + r.stderr).strip()

    def mine(self, export, out, args):
        r = subprocess.run([str(self.cli), 'ns2-dump', str(export), str(out), *args], capture_output=True, text=True)
        return r.returncode, (r.stdout + r.stderr).strip()

    def case(self, name, export, args=(), expect=None, check=None, keep=None):
        """keep: the name of an earlier case whose output directories are converted into again (reuse / redo)."""
        ref, mine = self.work / (keep or name) / 'ref', self.work / (keep or name) / 'out'
        if not keep:
            for d in (ref, mine, Path(str(ref) + '.tmp'), Path(str(mine) + '.tmp')):
                shutil.rmtree(d, ignore_errors=True)
        rc_m, log_m = self.mine(export, mine, args)
        last = (log_m.splitlines() or [''])[-1][-200:]
        if self.mine_only:
            ok = expect is None or (rc_m == 0) == (expect in ('ok', 'reused'))
            if ok and check and rc_m == 0:
                problem = check(mine)
                ok = not problem
                last = problem or last
            report(ok, name, f'mine rc={rc_m}: {last}')
            return
        rc_r, log_r = self.reference(export, ref, args)
        ref_last = (log_r.splitlines() or [''])[-1][-200:]
        if keep and expect == 'reused' and rc_r == 0 and '复用' not in log_r:   # the original prints "reusing" (复用)
            report(False, name, f'the reference did not reuse its output: {ref_last}')
            return
        if expect is not None and (rc_r == 0) != (expect in ('ok', 'reused')):
            report(False, name, f'the reference exits {rc_r}, the test expected {expect}: {ref_last}')
            return
        if rc_r != 0:
            report(rc_m != 0 and not mine.exists(), name, f'reference fails ({ref_last}); mine rc={rc_m}: {last}')
            return
        a, b = tree(ref), tree(mine)
        different = sorted(k for k in set(a) | set(b or {}) if a.get(k) != (b or {}).get(k))
        ok = rc_m == 0 and not different and (expect != 'reused' or 'reusing' in log_m)
        if ok and check:
            problem = check(mine)
            ok = not problem
            last = problem or last
        report(ok, name, f'{len(a)} entries identical' if ok else f'mine rc={rc_m}: {last}; differing: {different[:8]}')

    def ours_only(self, name, export, args, message):
        """Deliberate difference (module cap, default 1 GiB, checked before decoding): must fail at once with
        exit 1 and `message`, under a 512 MiB address-space limit on Linux (RB_TEST_NO_RLIMIT=1 lifts it)."""
        out = self.work / name / 'out'
        shutil.rmtree(out, ignore_errors=True)
        rlimit = sys.platform.startswith('linux') and os.environ.get('RB_TEST_NO_RLIMIT') != '1'

        def limited():
            import resource
            resource.setrlimit(resource.RLIMIT_AS, (512 << 20, 512 << 20))
        r = subprocess.run([str(self.cli), 'ns2-dump', str(export), str(out), *args], capture_output=True, text=True,
                           preexec_fn=limited if rlimit else None)
        ok = r.returncode == 1 and message in r.stderr and not out.exists() and not Path(str(out) + '.tmp').exists()
        report(ok, name, f'ours only, {"RLIMIT_AS 512 MiB" if rlimit else "no address-space limit"}: rc={r.returncode} {r.stderr.strip()[-160:]!r}')

    def detect(self, name, folder):
        r = subprocess.run([str(self.cli), 'ns2-detect', str(folder)], capture_output=True, text=True)
        if self.mine_only:
            report(True, name, f'mine rc={r.returncode} {r.stdout.strip()}')
            return
        e = subprocess.run([sys.executable, str(self.checkout / 'pack/ns2_dump.py'), '--detect', str(folder)], capture_output=True, text=True)
        ok = (e.returncode == 0) == (r.returncode == 0) and (e.returncode != 0 or e.stdout == r.stdout)
        report(ok, name, f'reference rc={e.returncode} {e.stdout.strip()!r}; mine rc={r.returncode} {r.stdout.strip()!r}')


def unpack(out):
    return dict(line.rstrip('\n').split('\t', 1) for line in open(Path(out) / 'unpack.tsv', encoding='utf-8'))


def main():
    a = sys.argv[1:]
    mine_only = a[:1] == ['--mine-only']
    if mine_only:
        checkout, cli, work, nxu, zbictest = None, Path(a[1]).resolve(), Path(a[2]).resolve(), None, None
    else:
        checkout, cli, nxu, work = Path(a[0]).resolve(), Path(a[1]).resolve(), Path(a[2]).resolve(), Path(a[3]).resolve()
        zbictest = Path(a[4]).resolve() if len(a) > 4 else None
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    inputs = work / 'inputs'
    run = Runner(checkout, cli, nxu, work, mine_only)

    # 1. full update: update romfs alone, newest update by number, synthesised NACP, DLC numbering
    def check_full(o):
        u = unpack(o)
        want = {'title_id': '040074a01bf12000', 'update': '458752', 'name': 'Game', 'aoc': '1',
                'builds': 'main:' + (bytes([458752 % 251]) * 16).hex() + ' sdk:' + '22' * 16}
        bad = [k for k, v in want.items() if u.get(k) != v]
        if bad or (Path(o) / 'romfs/S/old.Product.100.bin').exists():
            return f'unpack.tsv fields {bad} or stale base file kept'
        if (Path(o) / 'aoc.tsv').read_text() != 'idx\ttitle_id\tversion\tfiles\tbytes\n1\t040074a01bf13001\t0\t1\t4\n':
            return 'aoc.tsv'
        n = (Path(o) / 'ctl/control.nacp').read_bytes()
        if len(n) != 0x4000 or struct.unpack_from('<Q', n, 0x3078)[0] != TID or n[:4] != b'Game':
            return 'control.nacp'
        return None
    full = mk(inputs / 'Game')
    run.case('full-update', full, check=check_full)
    run.case('full-update-reused', full, keep='full-update', expect='reused', check=check_full)
    w(full / 'updates/458752/romfs/C/c2.bin', b'new')
    run.case('full-update-changed-source', full, keep='full-update',
             check=lambda o: None if (Path(o) / 'romfs/C/c2.bin').is_file() else 'not redone')

    # 2. delta update (no identical file): base overlaid by the update; --name
    run.case('delta-update-name', mk(inputs / 'Delta', full=False), ('--name', 'dk'),
             check=lambda o: None if (Path(o) / 'romfs/S/old.Product.100.bin').exists() and unpack(o)['name'] == 'dk' else 'overlay')
    run.case('delta-update-unicode-name', mk(inputs / 'Delta2', full=False), ('--name', 'Jeu é 游戏'))
    # 3. base only; folder given one level up (find_dump); a nested exefs file and hidden files
    b = inputs / 'BaseOnlyParent' / 'Inner'
    w(b / 'base/exefs/main', nso(b'\x01' * 16, 0x7F))
    w(b / 'base/exefs/main.npdm', npdm(TID))
    w(b / 'base/exefs/sub/nested', b'nested')
    w(b / 'base/exefs/.hidden', b'h')
    w(b / 'base/romfs/.hidden/x', b'x')
    w(b / 'base/romfs/data/z.bin', b'z' * 100)
    run.case('base-only-from-parent', b.parent, check=lambda o: None if unpack(o)['update'] == '' else 'update field')
    run.detect('detect-parent', b.parent)
    run.detect('detect-not-export', inputs / 'Delta' / 'base')
    # 4. update without exefs/main: exefs from the base, romfs from the update
    u4 = mk(inputs / 'UpdNoMain')
    for v in ('65536', '458752'):
        (u4 / 'updates' / v / 'exefs/main').unlink()
    run.case('update-without-main', u4)
    # 5. no base romfs; DLC directly in dlc/<id>/romfs; DLC with several versions, 0x prefix, licence only, file entry
    d5 = mk(inputs / 'NoBaseRom')
    shutil.rmtree(d5 / 'base/romfs')
    os.rename(d5 / 'dlc/040074a01bf13001/0/romfs', d5 / 'dlc/040074a01bf13001/romfs')
    os.rmdir(d5 / 'dlc/040074a01bf13001/0')
    w(d5 / 'dlc/040074A01BF13002/1/romfs/v1.bin', b'v1')
    w(d5 / 'dlc/040074A01BF13002/10/romfs/v10.bin', b'v10')
    w(d5 / 'dlc/040074A01BF13002/9/romfs/v9.bin', b'v9')
    w(d5 / 'dlc/040074A01BF13002/11/other.bin', b'no romfs in 11')
    w(d5 / 'dlc/0x040074a01bf13003/romfs/p.bin', b'prefixed')
    (d5 / 'dlc/040074a01bf13004/7').mkdir(parents=True)
    w(d5 / 'dlc/040074a01bf13005', b'a file named like a DLC')
    w(d5 / 'dlc/not-hex/romfs/q.bin', b'q')
    w(d5 / 'dlc/040074a01bf13001_0/romfs/u.bin', b'underscore')
    w(d5 / 'dlc/040074a01bf12fff/romfs/r.bin', b'index 0xfff')
    w(d5 / 'dlc/040074a01bf13000/romfs/r.bin', b'index 0x1000: out of range')
    run.case('no-base-romfs-dlc-layouts', d5)
    # 6. exported control.nacp (update folder) with an icon; titles and version with odd bytes
    c6 = mk(inputs / 'Control')
    w(c6 / 'updates/458752/control/control.nacp', nacp(b'Real Title', b'', b'\xe6\xb8\xb8\xe6\x88\x8f', b'1.2.3'))
    w(c6 / 'updates/458752/control/icon_AmericanEnglish.dat', b'\xff\xd8 icon')
    w(c6 / 'updates/458752/control/icon_Japanese.dat', b'\xff\xd8 other')
    run.case('control-exported-update', c6)
    c7 = mk(inputs / 'ControlBase')
    w(c7 / 'base/control.nacp', nacp(b'', b'\xe7\xb9\x81', b'', b'1.0\xff'))
    run.case('control-exported-base-zh13', c7)
    c8 = mk(inputs / 'ControlBad')
    w(c8 / 'base/control.nacp', nacp(b'Bad \xc3\x28 \xe2\x82 \xed\xa0\x80 \xf0\x9f\x98 end', b'', b'', b'v\x80'))
    run.case('control-invalid-utf8', c8)
    c9 = mk(inputs / 'ControlEmpty')
    w(c9 / 'base/control.nacp', nacp())
    run.case('control-empty-titles', c9, ('--name', 'Fallback'))
    c10 = mk(inputs / 'ControlWrongSize')
    w(c10 / 'base/control.nacp', b'\0' * 100)
    w(c10 / 'base/romfs/control.nacp', nacp(b'inside romfs: ignored'))
    run.case('control-wrong-size-synth', c10)
    # 7. save kinds from the game code (LZ4 segment too); sdk alone does not count
    s7 = mk(inputs / 'TmpSave')
    w(s7 / 'updates/458752/exefs/main', nso(b'\x55' * 16, 0x3F, SYM))
    try:
        w(s7 / 'updates/458752/exefs/subsdk0', lz4_subsdk())
    except ImportError:
        print('note: python lz4 missing, the LZ4 save-kind module is left out')
    run.case('save-kinds', s7, check=lambda o: None if struct.unpack_from('<q', (Path(o) / 'ctl/control.nacp').read_bytes(), 0x3168)[0] == 0x08000000 else 'temporary storage')
    s8 = mk(inputs / 'SdkOnly')
    w(s8 / 'updates/458752/exefs/sdk', nso(b'\x57' * 16, 0x3F, SYM))
    run.case('save-kinds-sdk-only', s8)
    # 8. ZBIC modules (synthetic module compressed by make_synth_zbic.py), 0x40 kept, several modules
    z1 = mk(inputs / 'Zbic')
    w(z1 / 'updates/458752/exefs/main', zbic_module(1, 0x40))
    w(z1 / 'updates/458752/exefs/subsdk0', zbic_module(2, 0, hashes=False))
    w(z1 / 'updates/458752/exefs/rtld', zbic_module(3))
    run.case('zbic-modules', z1, check=lambda o: None if (Path(o) / 'exefs/main').read_bytes()[0xC] == 0x78 else 'flags')
    z2 = mk(inputs / 'ZbicSaves')
    plain = bytearray(nso(b'\x66' * 16, 0, SYM + bytes(300)))
    for i in (1, 2):   # empty ro/data segments placed after text (a ZBIC NSO needs every segment past the header)
        struct.pack_into('<I', plain, 0x10 + 0x10 * i, len(plain))
    w(z2 / 'updates/458752/exefs/main', zbic.zbic_nso(bytes(plain), random.Random(5)))
    run.case('zbic-with-save-symbols', z2)
    if zbictest:
        for flags in ('BF', 'FF'):
            sample = inputs / f'emit-{flags}.nso'
            subprocess.run([str(zbictest), '--emit', str(sample), str(sample) + '.exp', flags], check=True, capture_output=True)
            ze = mk(inputs / f'ZbicEmit{flags}')
            w(ze / 'updates/458752/exefs/main', sample.read_bytes())
            run.case(f'zbic-s2arm-sample-{flags}', ze,
                     check=lambda o, s=sample: None if (Path(o) / 'exefs/main').read_bytes() == Path(str(s) + '.exp').read_bytes() else 'differs from Normalize')
    # 9. failures
    f1 = mk(inputs / 'Bit8')
    w(f1 / 'updates/458752/exefs/main', nso(b'\x45' * 16, 0x13F))
    run.case('unknown-flag-bit', f1, expect='fail')
    f2 = mk(inputs / 'ZbicBad')
    bad = bytearray(zbic_module(4))
    off, size = struct.unpack_from('<I', bad, 0x10)[0], struct.unpack_from('<I', bad, 0x60)[0]
    bad[off + size // 2:off + size // 2 + 16] = b'\xAA' * 16
    w(f2 / 'updates/458752/exefs/main', bytes(bad))
    run.case('zbic-corrupt', f2, expect='fail')
    f2b = mk(inputs / 'ZbicStd')
    bad = bytearray(zbic.zbic_nso(synth.build(dynamic=True), random.Random(9), hashes=False))
    off = struct.unpack_from('<I', bad, 0x10)[0]
    while bad[off:off + 4] != b'ZBIC':   # skip a leading skippable frame
        off += 8 + struct.unpack_from('<I', bad, off + 4)[0]
    bad[off:off + 4] = bytes.fromhex('28b52ffd')
    w(f2b / 'updates/458752/exefs/main', bytes(bad))
    run.case('zbic-standard-zstd-frame', f2b, expect='fail')
    f3 = mk(inputs / 'ZbicHash')
    bad = bytearray(zbic_module(6))
    bad[0xA0] ^= 1
    w(f3 / 'updates/458752/exefs/main', bytes(bad))
    run.case('zbic-hash-mismatch', f3, expect='fail')
    f4 = mk(inputs / 'Case')
    w(f4 / 'updates/458752/romfs/a/A.BIN', b'x')
    w(f4 / 'updates/458752/romfs/a/a.bin', b'y')
    if len(os.listdir(f4 / 'updates/458752/romfs/a')) == 2:
        run.case('case-collision', f4, expect='fail')
    f5 = inputs / 'NoRom'
    w(f5 / 'base/exefs/main', nso(b'\x01' * 16))
    w(f5 / 'base/exefs/main.npdm', npdm(TID))
    run.case('no-romfs', f5, expect='fail')
    f6 = mk(inputs / 'OtherTid')
    w(f6 / 'updates/458752/exefs/main.npdm', npdm(TID + 1))
    run.case('update-program-id-differs', f6, expect='fail')
    f7 = mk(inputs / 'ShortNso')
    w(f7 / 'updates/458752/exefs/subsdk1', b'NSO0\0\0')
    run.case('nso-header-truncated', f7, expect='fail')
    f8 = mk(inputs / 'BadNpdm')
    w(f8 / 'base/exefs/main.npdm', b'META' + bytes(0x40))
    run.case('npdm-too-short', f8, expect='fail')
    run.case('not-an-export', inputs / 'Delta' / 'romfs-nowhere', expect='fail')
    f9 = mk(inputs / 'NoMain')
    for p in (f9 / 'updates').glob('*/exefs/main'):
        p.unlink()
    (f9 / 'base/exefs/main').unlink()
    run.case('no-main', f9, expect='fail')
    # 10. decompression bombs and the host cap (ours only)
    b1 = mk(inputs / 'ZbicBomb')
    w(b1 / 'updates/458752/exefs/main', zbic.rle_bomb_nso([1 << 30] * 3))
    run.ours_only('bomb-zbic-main-3GiB', b1, (), 'above the limit')
    b2 = mk(inputs / 'Lz4Bomb')
    w(b2 / 'updates/458752/exefs/subsdk0', zbic.lz4_bomb_nso([1 << 30] * 3))
    run.ours_only('bomb-lz4-save-kind-scan-3GiB', b2, (), 'above the module limit')
    b3 = mk(inputs / 'ZbicCap')
    w(b3 / 'updates/458752/exefs/main', zbic_module(7))
    run.ours_only('host-module-cap-zbic', b3, ('--max-module-bytes', '4096'), 'above the limit')

    print(f"{state['ran']} cases, {state['failed']} failed")
    sys.exit(1 if state['failed'] or state['ran'] < 20 else 0)


if __name__ == '__main__':
    main()
