#!/usr/bin/env python3
"""Compares rb_s2arm_nup_expand with S2Arm's pack/ns2_nup.py on synthetic NUP containers (CI only).

Usage: run_nup_test.py <s2arm_checkout> <s2arm_prepare_cli> <work_dir>
       run_nup_test.py --mine-only <s2arm_prepare_cli> <work_dir>   (local: our side and the hand checks only)

Every container is written here from the public NUP specification v1 (https://github.com/a55uka/nup
SPEC.md; no game content): a superblock, a table of contents with its SHA-256, packages, directories,
files (stored or one zstd frame each, with their SHA-256), child slots and a name pool, then the data and
the packages' metadata blocks (TLV: NACP 0x0002, icon 0x0003, localized icons 0x000A). For each case
both sides expand the same container: a success needs the same tree (names, directories, bytes; the
content of .ns2_nup_key is excluded, see s2arm_nup.h), a failure of the original needs a failure of ours
that leaves neither the output folder nor <output>.tmp. The original needs a zstd module (the CI step
installs zstandard); ours uses zstd 1.5.7's decoder (s2arm_zstd.c).
"""
import hashlib
import os
import shutil
import struct
import subprocess
import sys
from pathlib import Path

try:
    import zstandard
except ImportError:   # the reference cannot run either; --mine-only cases still need a compressor
    zstandard = None

APP = 0x0400C3F0000A0000
NO_DIR = 0xFFFFFFFF
BASE, UPDATE, ADDON = 0, 1, 2
state = {'ran': 0, 'failed': 0}


def report(ok, name, detail):
    state['ran'] += 1
    state['failed'] += not ok
    print(f"{'ok  ' if ok else 'FAIL'} {name} ({detail})", flush=True)


def npdm(tid):
    b = bytearray(0x200)
    b[:4] = b'META'
    struct.pack_into('<II', b, 0x70, 0x100, 0x40)
    b[0x100:0x104] = b'ACI0'
    struct.pack_into('<Q', b, 0x110, tid)
    return bytes(b)


def nacp(title):
    b = bytearray(0x4000)
    b[:len(title)] = title
    struct.pack_into('<Q', b, 0x3078, APP)
    return bytes(b)


def tlv(entries):
    return b''.join(struct.pack('<HHI', t, 0, len(v)) + v for t, v in entries)


def licons(entries):   # [tag length][tag][u32 size][data] ...
    return b''.join(bytes([len(t)]) + t + struct.pack('<I', len(d)) + d for t, d in entries)


def zstd_frame(data):
    if zstandard is None:
        raise SystemExit('a zstd compressor is needed to write the containers: pip install zstandard')
    return zstandard.ZstdCompressor(level=3, write_content_size=True).compress(data)


class Writer:
    """Packages: (kind, title_id, version, flags, root tree, exefs tree or None, romfs tree or None, meta bytes).
    A tree is {name: bytes | ('z', bytes) | ('raw-size', bytes, size) | dict}; dicts are directories."""

    def __init__(self):
        self.dirs, self.files, self.slots, self.pool, self.data = [], [], [], bytearray(), []

    def name(self, raw):
        off = len(self.pool)
        self.pool += raw
        return off, len(raw)

    def tree(self, t, name=b''):
        idx = len(self.dirs)
        self.dirs.append(None)
        children = []
        for k, v in t.items():
            k = k if isinstance(k, bytes) else k.encode()
            if isinstance(v, dict):
                children.append(('d', self.tree(v, k)))
            else:
                children.append(('f', self.file(k, v)))
        children.reverse()   # slots out of name order: the reader sorts them
        first = len(self.slots)
        self.slots.extend(children)
        o, n = self.name(name)
        self.dirs[idx] = (o, n, first, len(children))
        return idx

    def file(self, name, v):
        o, n = self.name(name)
        codec, body, sha = 0, v, None
        if isinstance(v, tuple) and v[0] == 'z':
            codec, body = 1, zstd_frame(v[1])
            size, sha = len(v[1]), hashlib.sha256(v[1]).digest()
        elif isinstance(v, tuple) and v[0] == 'zraw':   # a hand-made encoded body: (zraw, encoded, size, sha of the plain bytes)
            codec, body, size, sha = 1, v[1], v[2], v[3]
        elif isinstance(v, tuple) and v[0] == 'badsha':
            body = v[1]
            size, sha = len(body), hashlib.sha256(body + b'x').digest()
        elif isinstance(v, tuple) and v[0] == 'codec2':
            codec, body = 2, v[1]
            size, sha = len(body), hashlib.sha256(body).digest()
        else:
            size, sha = len(v), hashlib.sha256(v).digest()
        idx = len(self.files)
        self.files.append([o, n, size, 0, len(body) if size else 0, sha, codec])
        self.data.append((idx, body if size else b''))
        return idx

    def build(self, packages, corrupt=None):
        recs = []
        for kind, tid, version, flags, root, exefs, romfs, meta in packages:
            r = self.tree(root)
            e = self.tree(exefs, b'exefs') if exefs is not None else NO_DIR
            m = self.tree(romfs, b'romfs') if romfs is not None else NO_DIR
            recs.append([tid, r, e, m, version, kind, flags, meta])
        ndirs, nfiles = len(self.dirs), len(self.files)
        need = 0x30 + len(recs) * 0x40 + ndirs * 0x18 + nfiles * 0x50
        slots = b''.join(struct.pack('<I', i if t == 'd' else ndirs + i) for t, i in self.slots)
        pool_off = need + len(slots)
        toc_size = pool_off + len(self.pool)
        blob = (0x80 + toc_size + 15) // 16 * 16
        p = blob
        body = bytearray()
        for idx, b in self.data:
            if not b:
                continue
            self.files[idx][3] = p
            body += b + b'\0' * ((-len(b)) % 16)
            p += len(b) + (-len(b)) % 16
        metas = []
        for r in recs:
            mb = r[7] or b''
            metas.append((p, len(mb)) if mb else (0, 0))
            body += mb + b'\0' * ((-len(mb)) % 16)
            p += len(mb) + (-len(mb)) % 16
        toc = bytearray(struct.pack('<4sIQQQQQ', b'TOC\x01', len(recs), ndirs, nfiles, pool_off, len(self.pool), 0))
        for r, (mo, ms) in zip(recs, metas):
            toc += struct.pack('<QIIIIBBHIQI20x', r[0], r[1], r[2], r[3], r[4], r[5], r[6], 0, 0, mo, ms)
        for o, n, first, count in self.dirs:
            toc += struct.pack('<IIIIQ', o, n, first, count, 0)
        for o, n, size, eoff, esz, sha, codec in self.files:
            toc += struct.pack('<IIQQQ32sBBH12x', o, n, size, eoff, esz, sha, codec, 0, 0)
        toc += slots + self.pool
        assert len(toc) == toc_size
        fsize = blob + len(body)
        sha = hashlib.sha256(toc).digest()
        if corrupt == 'toc-sha':
            sha = hashlib.sha256(toc + b'!').digest()
        sup = struct.pack('<4sHHQQ32sQQII16s32s', b'NUP\x01', 0x80, 0, 0x80, toc_size, sha, blob, fsize, len(recs), 0, b'\x11' * 16, b'\0' * 32)
        out = sup + bytes(toc) + b'\0' * (blob - 0x80 - toc_size) + bytes(body)
        if corrupt == 'truncated':
            out = out[:-16]
        return out


def exefs(tid=APP, extra=None):
    t = {'main': b'MAINNSO' * 50, 'main.npdm': npdm(tid), 'sdk': ('z', b'SDK' * 4000)}
    t.update(extra or {})
    return t


def container(path, packages, corrupt=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(Writer().build(packages, corrupt))
    return path


def tree(root):
    """{relative path: bytes or 'dir'}; .ns2_nup_key compared by presence only."""
    out = {}
    root = Path(root)
    if not root.is_dir():
        return None
    for p in sorted(root.rglob('*')):
        rel = str(p.relative_to(root))
        if p.is_dir() and not p.is_symlink():
            out[rel + '/'] = 'dir'
        elif p.name == '.ns2_nup_key':
            out[rel] = 'key'
        else:
            out[rel] = p.read_bytes()
    return out


class Runner:
    def __init__(self, checkout, cli, work, mine_only):
        self.checkout, self.cli, self.work, self.mine_only = checkout, cli, work, mine_only

    def reference(self, src, out):
        r = subprocess.run([sys.executable, str(self.checkout / 'pack/ns2_nup.py'), str(src), str(out)], capture_output=True, text=True)
        return r.returncode, (r.stdout + r.stderr).strip()

    def mine(self, src, out):
        r = subprocess.run([str(self.cli), 'nup', str(src), str(out)], capture_output=True, text=True)
        return r.returncode, (r.stdout + r.stderr).strip()

    def case(self, name, src, expect='ok', check=None, keep=None):
        ref, mine = self.work / (keep or name) / 'ref', self.work / (keep or name) / 'out'
        if not keep:
            for d in (ref, mine, Path(str(ref) + '.tmp'), Path(str(mine) + '.tmp')):
                shutil.rmtree(d, ignore_errors=True)
        rc_m, log_m = self.mine(src, mine)
        last = (log_m.splitlines() or [''])[-1][-200:]
        clean = not Path(str(mine) + '.tmp').exists()
        if self.mine_only:
            ok = (rc_m == 0) == (expect in ('ok', 'reused')) and clean
            if ok and rc_m != 0:
                ok = not mine.exists() or keep is not None
            if ok and expect == 'reused':
                ok = 'reused' in log_m
            if ok and check and rc_m == 0:
                problem = check(mine)
                ok = not problem
                last = problem or last
            report(ok, name, f'mine rc={rc_m}: {last}')
            return
        rc_r, log_r = self.reference(src, ref)
        ref_last = (log_r.splitlines() or [''])[-1][-200:]
        if (rc_r == 0) != (expect in ('ok', 'reused')):
            report(False, name, f'the reference exits {rc_r}, the test expected {expect}: {ref_last}')
            return
        if rc_r != 0:
            report(rc_m != 0 and not mine.exists() and clean, name, f'reference fails ({ref_last}); mine rc={rc_m}: {last}')
            return
        a, b = tree(ref), tree(mine)
        different = sorted(k for k in set(a) | set(b or {}) if a.get(k) != (b or {}).get(k))
        ok = rc_m == 0 and not different and clean and (expect != 'reused' or 'reused' in log_m)
        if ok and check:
            problem = check(mine)
            ok = not problem
            last = problem or last
        report(ok, name, f'{len(a)} entries identical' if ok else f'mine rc={rc_m}: {last}; differing: {different[:8]}')


def main():
    a = sys.argv[1:]
    mine_only = a[:1] == ['--mine-only']
    if mine_only:
        checkout, cli, work = None, Path(a[1]).resolve(), Path(a[2]).resolve()
    else:
        checkout, cli, work = Path(a[0]).resolve(), Path(a[1]).resolve(), Path(a[2]).resolve()
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    inputs = work / 'inputs'
    run = Runner(checkout, cli, work, mine_only)
    dlc1, dlc2 = APP + 0x1001, APP + 0x1002
    icon_en, icon_fr = b'\xff\xd8JPEG-en' * 30, b'\xff\xd8JPEG-fr' * 30
    base_romfs = {'Common': {'a.bin': b'A' * 3000, 'big.bin': ('z', bytes(range(256)) * 20000), 'empty.bin': b'',
                             '.listing': b'exporter listing\n'},
                  'Empty': {}, 'Nested': {'L1': {'L2': {'deep.txt': b'deep'}}},
                  'Jeu é 游戏.bin': b'unicode name', 'z_last.dat': ('z', b'Z' * 70000)}

    # 1. base + two updates (the newest written, with its control data) + two DLC; stored and zstd files, an
    #    exporter's .listing left out, an empty file and folder, nested folders, a non-ASCII name, slots unsorted
    full = container(inputs / 'Full Game [0400C3F0000A0000][v131072].nup', [
        (BASE, APP, 0, 0, {'exefs': exefs(extra={'subsdk0': b'SUB0' * 100}), 'romfs': base_romfs}, exefs(extra={'subsdk0': b'SUB0' * 100}), base_romfs,
         tlv([(2, nacp(b'Base title')), (10, licons([(b'fr-FR', icon_fr), (b'en-US', icon_en)]))])),
        (UPDATE, APP + 0x800, 65536, 0, {'e': exefs()}, exefs(), {'Common': {'a.bin': b'old update'}}, tlv([(2, nacp(b'Old update'))])),
        (UPDATE, APP + 0x800, 131072, 0, {'e': exefs()}, exefs(extra={'main': ('z', b'NEWMAIN' * 9000)}),
         {'Common': {'a.bin': b'new update a', 'u.bin': ('z', b'U' * 12345)}, 'Patch': {'p.txt': b'patch'}},
         tlv([(2, nacp(b'Update title')), (3, b'\xff\xd8direct-icon'), (2, nacp(b'second NACP ignored'))])),
        (ADDON, dlc2, 0, 0, {'r': {}}, None, {'dlc2': {'x.bin': ('z', b'X' * 5000)}}, None),
        (ADDON, dlc1, 0, 0, {'r': {}}, None, {'dlc1.bin': b'dlc one'}, None),
    ])

    def check_full(o):
        o = Path(o)
        want = ['base/exefs/main', 'base/exefs/subsdk0', 'base/romfs/Common/big.bin', 'base/romfs/Empty', 'updates/131072/exefs/main',
                'updates/131072/control.nacp', 'updates/131072/icon_AmericanEnglish.dat', f'dlc/{dlc1:016X}/0/romfs/dlc1.bin',
                f'dlc/{dlc2:016X}/0/romfs/dlc2/x.bin', 'base/control.nacp', 'base/icon_AmericanEnglish.dat', '.ns2_nup_key']
        missing = [w for w in want if not (o / w).exists()]
        if missing:
            return f'missing {missing}'
        if (o / 'updates/65536').exists() or (o / 'base/romfs/Common/.listing').exists():
            return 'older update or .listing written'
        if (o / 'updates/131072/exefs/main').read_bytes() != b'NEWMAIN' * 9000 or (o / 'base/icon_AmericanEnglish.dat').read_bytes() != icon_en:
            return 'content'
        if (o / 'updates/131072/icon_AmericanEnglish.dat').read_bytes() != b'\xff\xd8direct-icon' or (o / 'updates/131072/control.nacp').read_bytes()[:12] != b'Update title':
            return 'update control'
        return None
    run.case('full', full, check=check_full)
    run.case('full-reused', full, expect='reused', keep='full', check=check_full)
    # 2. the folder that holds the container (find_nup)
    run.case('folder-with-one-nup', full.parent)

    # 3. no base package: an update marked standalone_update is the whole game, written as base/ too
    upd = {'Data': {'d.bin': ('z', b'D' * 40000)}, 'e.txt': b'e'}
    standalone = container(inputs / 'standalone' / 'Standalone.nup', [
        (UPDATE, APP + 0x800, 196608, 1, {'e': exefs()}, exefs(), upd, tlv([(2, nacp(b'Standalone')), (10, licons([(b'ja', b'ja-icon'), (b'EN', b'en-icon')]))])),
        (ADDON, dlc1, 0, 0, {'r': {}}, None, {'only.bin': b'only'}, None),
    ])
    run.case('standalone-update', standalone,
             check=lambda o: None if (Path(o) / 'base/romfs/Data/d.bin').read_bytes() == b'D' * 40000 and
             (Path(o) / 'updates/196608/icon_AmericanEnglish.dat').read_bytes() == b'en-icon' and not (Path(o) / 'base/control.nacp').exists() else 'layout')

    # 4. a base record with no file: the update as the whole game, the base record's metadata merged under the update's
    holder = container(inputs / 'holder' / 'Holder.nup', [
        (BASE, APP, 0, 0, {'empty': {'z.bin': b''}}, None, None, tlv([(2, nacp(b'From the base record')), (3, b'base-icon')])),
        (UPDATE, APP + 0x800, 65536, 0, {'e': exefs()}, exefs(), {'r.bin': b'r'}, tlv([(3, b'update-icon')])),
    ])
    run.case('empty-base-record', holder,
             check=lambda o: None if (Path(o) / 'updates/65536/control.nacp').read_bytes()[:20] == b'From the base record' and
             (Path(o) / 'updates/65536/icon_AmericanEnglish.dat').read_bytes() == b'update-icon' and (Path(o) / 'base/exefs/main').is_file() else 'merge')

    # 5. base only, no control data, no romfs
    run.case('base-only', container(inputs / 'base-only' / 'B.nup', [(BASE, APP, 0, 0, {'e': exefs()}, exefs(), None, None)]),
             check=lambda o: None if not (Path(o) / 'base/control.nacp').exists() and not (Path(o) / 'base/romfs').exists() else 'layout')
    # 6. a NACP of the wrong size is not written; an empty localized icon list gives no icon
    run.case('short-nacp', container(inputs / 'short' / 'S.nup', [(BASE, APP, 0, 0, {'e': exefs()}, exefs(), {'a': b'a'}, tlv([(2, b'short'), (10, b'')]))]),
             check=lambda o: None if not (Path(o) / 'base/control.nacp').exists() else 'short NACP written')

    # failures: every place the original stops
    ok_pkgs = [(BASE, APP, 0, 0, {'e': exefs()}, exefs(), {'a': b'a'}, None)]
    run.case('toc-sha', container(inputs / 'bad1' / 'x.nup', ok_pkgs, 'toc-sha'), 'fail')
    run.case('truncated', container(inputs / 'bad2' / 'x.nup', ok_pkgs, 'truncated'), 'fail')
    run.case('file-sha', container(inputs / 'bad3' / 'x.nup', [(BASE, APP, 0, 0, {'e': exefs()}, exefs(), {'a': ('badsha', b'abc')}, None)]), 'fail')
    run.case('codec-2', container(inputs / 'bad4' / 'x.nup', [(BASE, APP, 0, 0, {'e': exefs()}, exefs(), {'a': ('codec2', b'abc')}, None)]), 'fail')
    garbage = b'\x28\xb5\x2f\xfd' + b'\x00garbage' * 8
    run.case('zstd-garbage', container(inputs / 'bad5' / 'x.nup', [(BASE, APP, 0, 0, {'e': exefs()}, exefs(), {'a': ('zraw', garbage, 100, b'\0' * 32)}, None)]), 'fail')
    run.case('two-bases', container(inputs / 'bad6' / 'x.nup', ok_pkgs + ok_pkgs), 'fail')
    run.case('not-a-dlc', container(inputs / 'bad7' / 'x.nup', ok_pkgs + [(ADDON, APP + 0x1000 + 2001, 0, 0, {'r': {}}, None, {'a': b'a'}, None)]), 'fail')
    run.case('dlc-twice', container(inputs / 'bad8' / 'x.nup', ok_pkgs + [(ADDON, dlc1, 0, 0, {'r': {}}, None, {'a': b'a'}, None)] * 2), 'fail')
    run.case('dlc-no-romfs', container(inputs / 'bad9' / 'x.nup', ok_pkgs + [(ADDON, dlc1, 0, 0, {'r': {}}, None, None, None)]), 'fail')
    run.case('bad-name', container(inputs / 'bad10' / 'x.nup', [(BASE, APP, 0, 0, {'e': exefs()}, exefs(), {'..': b'escape'}, None)]), 'fail')
    run.case('pid-mismatch', container(inputs / 'bad11' / 'x.nup', ok_pkgs + [(UPDATE, APP, 65536, 0, {'e': exefs(APP + 0x2000)}, exefs(APP + 0x2000), None, None)]), 'fail')
    run.case('update-version-0', container(inputs / 'bad12' / 'x.nup', ok_pkgs + [(UPDATE, APP, 0, 0, {'e': exefs()}, exefs(), None, None)]), 'fail')
    run.case('same-update-twice', container(inputs / 'bad13' / 'x.nup', ok_pkgs + [(UPDATE, APP, 65536, 0, {'e': exefs()}, exefs(), None, None)] * 2), 'fail')
    run.case('no-main', container(inputs / 'bad14' / 'x.nup', [(BASE, APP, 0, 0, {'e': {'main.npdm': npdm(APP)}}, {'main.npdm': npdm(APP)}, None, None)]), 'fail')
    run.case('update-not-standalone', container(inputs / 'bad15' / 'x.nup', [(UPDATE, APP, 65536, 0, {'e': exefs()}, exefs(), None, None)]), 'fail')
    run.case('not-base-title', container(inputs / 'bad16' / 'x.nup', [(BASE, APP + 1, 0, 0, {'e': exefs(APP + 1)}, exefs(APP + 1), None, None)]), 'fail')
    two = inputs / 'two'
    container(two / 'a.nup', ok_pkgs)
    container(two / 'b.nup', ok_pkgs)
    run.case('folder-with-two-nups', two, 'fail')
    notnup = inputs / 'notnup' / 'x.nup'
    notnup.parent.mkdir(parents=True, exist_ok=True)
    notnup.write_bytes(b'PK\x03\x04 not a container')
    run.case('not-a-nup', notnup, 'fail')

    print(f"{state['ran']} cases, {state['failed']} failed")
    return 1 if state['failed'] else 0


if __name__ == '__main__':
    sys.exit(main())
