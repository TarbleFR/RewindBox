#!/usr/bin/env python3
"""Compares the ZBIC decoder and NSO normalisation of s2arm_zbic.c with S2Arm's C# originals (CI only).

Usage: run_zbic_test.py <s2arm_checkout> <s2arm_prepare_cli> <ZbicBatch command> <nx_unpack command> <ZbicTest command> <work_dir>
       run_zbic_test.py --mine-only <s2arm_checkout> <s2arm_prepare_cli> <work_dir>    (local: our side and known answers)

Commands are executables: ZbicBatch (tools/s2arm_prototype/zbic_batch, compiling S2Arm's
pack/nx_unpack/ZbicDecoder.cs and NsoZbic.cs), S2Arm's nx_unpack and its tests/nx_unpack_zbic
(ZbicTest). Inputs, all synthetic:
  - the test frames of S2Arm's tests/nx_unpack_zbic/Program.cs (read from the checkout as data),
    every one-byte change and every truncation of them, wrong expected lengths, a standard zstd frame;
  - frames from make_synth_zbic.py (every block, literal and table form), their random bit
    flips and truncations, hand-made header edge cases;
  - NSOs: S2Arm's own test layout around its frames, ZBIC versions of make_synth_nso.py modules,
    bad flags / offsets / sizes / hashes, header byte flips, non-NSO and short files.
Frame and NSO inputs go through both batch drivers (ZbicBatch and `s2arm_prepare_cli zbic-batch`):
every input must succeed in both with the same bytes or fail in both. A subset then goes through
the real `nx_unpack --nso-normalize` and our `nso-normalize` (exit status, output presence, bytes),
with the samples `ZbicTest --emit` writes and the expected files it derives from them.
"""
import base64
import hashlib
import random
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import make_synth_nso as synth  # noqa: E402
import make_synth_zbic as zbic  # noqa: E402

state = {'ran': 0, 'failed': 0}


def report(ok, name, detail):
    state['ran'] += 1
    state['failed'] += not ok
    print(f"{'ok  ' if ok else 'FAIL'} {name} ({detail})", flush=True)


# ---- S2Arm's test data (tests/nx_unpack_zbic/Program.cs), read as data ----
WORDS = ['the', 'of', 'and', 'to', 'in', 'is', 'was', 'for', 'on', 'that', 'with', 'as', 'by', 'at', 'from', 'this', 'be',
         'or', 'are', 'an', 'which', 'it', 'not', 'have', 'had']


def gen(seed, n):
    """Gen() of S2Arm's ZBIC test: the plain text its frames decode to."""
    x, parts, length = seed, [], 0
    while length < n:
        x = (x * 1103515245 + 12345) & 0x7fffffff
        r = x >> 16
        s = WORDS[r % len(WORDS)] + (str(r % 1000) if r % 7 == 0 else '') + ('\n' if r % 13 == 0 else ' ')
        parts.append(s)
        length += len(s)
    return ''.join(parts).encode()[:n]


def s2arm_frames(checkout):
    src = (checkout / 'tests/nx_unpack_zbic/Program.cs').read_text(encoding='utf-8')

    def const(name):
        m = re.search(r'string ' + name + r' =\s*((?:"[^"]*"\s*\+?\s*)+);', src)
        if not m:
            raise SystemExit(f'cannot find {name} in tests/nx_unpack_zbic/Program.cs')
        return ''.join(re.findall(r'"([^"]*)"', m.group(1)))
    frames = [bytes.fromhex(const(n)) for n in ('F1', 'F2', 'F3')]
    plain = [gen(1, 3000), gen(2, 1500), gen(3, 600)]
    flp = base64.b64decode(const('FLP'))
    fck_std = bytes.fromhex(const('FCK'))
    fck = b'ZBIC' + fck_std[4:]
    ck_text = b'S2Arm ZBIC checksum test: abcabcabcabcabcabcabcabc 0123456789 0123456789.\n'
    return frames, plain, flp, gen(36, 14500), fck, fck_std, ck_text


def s2arm_make(flags, bodies, plain):
    """Make() of S2Arm's test: header + module name + three segments, SHA-256 of the plain segments."""
    modname = b'main\0\0\0\0'
    h = bytearray(0x100)
    h[:4] = b'NSO0'
    struct.pack_into('<I', h, 0x0C, flags)
    struct.pack_into('<I', h, 0x1C, 0x100)
    struct.pack_into('<I', h, 0x2C, len(modname))
    at, mem = 0x100 + len(modname), 0
    for i in range(3):
        struct.pack_into('<III', h, 0x10 + 0x10 * i, at, mem, len(plain[i]))
        struct.pack_into('<I', h, 0x60 + 4 * i, len(bodies[i]))
        h[0xA0 + 0x20 * i:0xC0 + 0x20 * i] = hashlib.sha256(plain[i]).digest()
        at += len(bodies[i])
        mem += len(plain[i])
    return bytes(h) + modname + b''.join(bodies)


# ---- corpus ----
class Corpus:
    def __init__(self, work):
        self.work, self.jobs = work, []

    def add(self, kind, data, expected, tag):
        i = len(self.jobs)
        path = self.work / 'in' / f'{i}.bin'
        path.write_bytes(data)
        self.jobs.append((kind, path, expected, tag))

    def manifest(self, side):
        out = self.work / side
        out.mkdir()
        lines = [f'{k}\t{p}\t{e}\t{out / f"{i}.out"}\n' for i, (k, p, e, _) in enumerate(self.jobs)]
        m = self.work / f'{side}.manifest'
        m.write_text(''.join(lines))
        return m, out


def header_edge_cases(add):
    """Frame headers and blocks the encoder does not write on its own."""
    def fr(fhd, rest):
        return b'ZBIC' + bytes([fhd]) + rest
    raw = lambda data, last=1: (last | len(data) << 3).to_bytes(3, 'little') + data
    add(fr(0x20, b'\x03' + raw(b'abc')), 3, 'single segment, 1-byte size')
    add(fr(0x20, b'\x04' + raw(b'abc')), 3, 'content size larger than the data')
    add(fr(0x20, b'\x02' + raw(b'abc')), 3, 'block larger than the single-segment window')
    add(fr(0xE0, b'\xff' * 8 + raw(b'abc')), 3, '8-byte content size above 2^63')
    add(fr(0xC0, b'\x00' + b'\xff' * 8 + raw(b'abc')), 3, 'window + 8-byte content size above 2^63')
    add(fr(0x00, b'\xf8' + raw(b'abc')), 3, 'largest window descriptor')
    add(fr(0x00, b'\x00' + raw(bytes(1025))), 1025, 'block larger than a 1 KiB window')
    add(fr(0x08, b'\x00' + raw(b'abc')), 3, 'reserved header bit')
    add(fr(0x01, b'\x00\x07' + raw(b'abc')), 3, 'dictionary id 7')
    add(fr(0x03, b'\x00\x00\x00\x00\x00' + raw(b'abc')), 3, 'dictionary id 0 in 4 bytes')
    add(fr(0x00, b'\x00' + (1 | 3 << 1 | 3 << 3).to_bytes(3, 'little') + b'abc'), 3, 'reserved block type')
    add(fr(0x00, b'\x00' + (1 | 1 << 1).to_bytes(3, 'little') + b'q'), 0, 'empty RLE block')
    add(fr(0x00, b'\x00' + raw(b'ab', 0)), 2, 'no last block')
    add(fr(0x04, b'\x00' + raw(b'abc')), 3, 'checksum missing')
    add(fr(0x04, b'\x00' + raw(b'abc') + struct.pack('<I', zbic.xxh64(b'abc') & 0xFFFFFFFF)), 3, 'checksum good')
    add(struct.pack('<II', 0x184D2A5F, 3) + b'xyz', 0, 'skippable frame only')
    add(struct.pack('<II', 0x184D2A50, 9) + b'xyz', 0, 'skippable frame truncated')
    add(struct.pack('<II', 0x184D2A50, 0) + fr(0x00, b'\x00' + raw(b'abc')), 3, 'skippable then frame')
    add(fr(0x00, b'\x00' + raw(b'abc')) + b'ZB', 3, 'trailing bytes shorter than a magic')
    add(fr(0x00, b'\x00' + raw(b'abc')) + bytes.fromhex('28b52ffd') + bytes(8), 3, 'trailing standard zstd frame')
    add(fr(0x00, b'\x00' + (1 | 2 << 1 | 1 << 3).to_bytes(3, 'little') + b'\x00'), 0, 'compressed block: literals only, no sequences byte')
    add(fr(0x00, b'\x00' + (1 | 2 << 1 | 2 << 3).to_bytes(3, 'little') + b'\x00\x00'), 0, 'compressed block: empty literals, zero sequences')
    add(fr(0x00, b'\x00' + (1 | 2 << 1 | 3 << 3).to_bytes(3, 'little') + b'\x00\x00\x00'), 0, 'zero sequences then a stray byte')
    add(b'', 0, 'empty input')
    add(b'ZBIC', 0, 'magic only')


def build_corpus(corpus, checkout):
    frames, plain, flp, flp_plain, fck, fck_std, ck_text = s2arm_frames(checkout)
    add = lambda data, expected, tag: corpus.add('frame', data, expected, tag)
    for k in range(3):
        add(frames[k], len(plain[k]), f'S2Arm frame A{k + 1}')
        add(frames[k], len(plain[k]) + 1, f'A{k + 1} expected length + 1')
        add(frames[k], len(plain[k]) - 1, f'A{k + 1} expected length - 1')
    add(flp, len(flp_plain), 'S2Arm low-probability frame')
    add(b''.join(frames), sum(map(len, plain)), 'S2Arm frames back to back')
    add(fck, len(ck_text), 'S2Arm checksum frame')
    add(fck_std, len(ck_text), 'standard zstd frame')
    for name, data, n in (('A1', frames[0], 3000), ('A2', frames[1], 1500), ('A3', frames[2], 600), ('CK', fck, len(ck_text))):
        for i in range(len(data)):
            for bit in (0x01, 0x80):
                b = bytearray(data)
                b[i] ^= bit
                add(bytes(b), n, f'{name} byte {i} ^ {bit:#x}')
        for c in range(len(data)):
            add(data[:c], n, f'{name} cut to {c}')
    for i in range(0, len(flp), 3):
        b = bytearray(flp)
        b[i] ^= 1 << (i % 8)
        add(bytes(b), len(flp_plain), f'LP byte {i}')
    for c in range(0, len(flp), 41):
        add(flp[:c], len(flp_plain), f'LP cut to {c}')
    header_edge_cases(add)

    rng = random.Random(20261111)
    made = []
    for s in range(300):
        r = random.Random(s)
        n = r.choice([0, 1, 7, 31, 32, 255, 256, 257, 1000, 4096, 5000, 65791, 70000, 131072, 140000])
        kind = s % 5
        if kind == 0:
            d = bytes(r.randrange(256) for _ in range(n))
        elif kind == 1:
            d = gen(s, n)
        elif kind == 2:
            d = bytes([r.randrange(3)]) * n
        elif kind == 3:
            d = bytes(r.choice(b'abcab\0\0\0\xff') for _ in range(n))
        else:
            d = (synth.build(dynamic=True) * (n // 0x3100 + 1))[:n]
        f = zbic.zbic_frames(d, r)
        made.append((f, d))
        add(f, len(d), f'encoder seed {s} ({n} bytes)')
    for s, (f, d) in enumerate(made[:200]):
        for _ in range(12):
            b = bytearray(f)
            if b:
                b[rng.randrange(len(b))] ^= 1 << rng.randrange(8)
            add(bytes(b), len(d), f'encoder seed {s} bit flip')
        add(f[:rng.randrange(len(f) + 1)], len(d), f'encoder seed {s} cut')

    # NSOs
    addn = lambda data, tag: corpus.add('nso', data, 0, tag)
    z = s2arm_make(0xBF, frames, plain)
    addn(z, 'S2Arm layout 0xBF')
    addn(s2arm_make(0xFF, frames, plain), 'S2Arm layout 0xFF')
    addn(s2arm_make(0x3F, plain, plain), 'not ZBIC: unchanged')
    addn(s2arm_make(0x1BF, frames, plain), 'unknown flag bit 0x100')
    bad = bytearray(z)
    bad[0xC0] ^= 1
    addn(bytes(bad), 'segment hash mismatch')
    sz = bytearray(s2arm_make(0x87, frames, plain))
    struct.pack_into('<I', sz, 0x18, len(plain[0]) + 1)
    addn(bytes(sz), 'segment size differs from the decoded size')
    addn(s2arm_make(0xBF, [frames[0], frames[1], fck_std], [plain[0], plain[1], ck_text]), 'segment holds a standard zstd frame')
    t0 = struct.unpack_from('<I', z, 0x10)[0]
    for k in range(len(frames[0])):
        b = bytearray(z)
        b[t0 + k] ^= 1
        addn(bytes(b), f'S2Arm layout text byte {k}')
    for k in range(0x100):
        for bit in (0x01, 0x10, 0x80):
            b = bytearray(z)
            b[k] ^= bit
            addn(bytes(b), f'S2Arm layout header byte {k:#x} ^ {bit:#x}')
    for field, value in ((0x10, 0xFF), (0x10, 0x80000000), (0x60, 0x80000000), (0x18, 0x80000000), (0x18, 0x7FFFFFFF),
                         (0x60, 0x7FFFFFFF), (0x20, len(z)), (0x64, 0), (0x28, 0)):
        b = bytearray(z)
        struct.pack_into('<I', b, field, value)
        addn(bytes(b), f'field {field:#x} = {value:#x}')
    module = synth.build(dynamic=True)
    for s in range(60):
        r = random.Random(500 + s)
        zn = zbic.zbic_nso(module, r, extra_flags=r.choice([0, 0x40]), hashes=r.random() < 0.7,
                           compress=tuple(r.random() < 0.8 for _ in range(3)))
        addn(zn, f'synthetic module seed {s}')
        if s < 20:
            for _ in range(10):
                b = bytearray(zn)
                b[r.randrange(len(b))] ^= 1 << r.randrange(8)
                addn(bytes(b), f'synthetic module seed {s} bit flip')
    addn(module, 'uncompressed synthetic module')
    addn(b'this is not an NSO file at all', 'not an NSO')
    addn(z[:0xFF], 'ZBIC NSO shorter than its header')
    addn(z[:0x100], 'ZBIC NSO header only')
    addn(z[:len(z) - 1], 'ZBIC NSO one byte short')
    addn(b'', 'empty file')


def batch(command, manifest):
    """Runs a batch driver (a command list) over the manifest: {input index: (ok|err|crash, message)}."""
    r = subprocess.run(command + [str(manifest)], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f'{command} failed: {r.stderr[-2000:]}')
    out = {}
    for line in r.stdout.splitlines():
        number, status, *rest = line.split(' ', 2)
        out[int(number) - 1] = (status, rest[0] if rest else '')
    return out


def main():
    a = sys.argv[1:]
    mine_only = a[:1] == ['--mine-only']
    if mine_only:
        checkout, cli, work = Path(a[1]).resolve(), Path(a[2]).resolve(), Path(a[3]).resolve()
        zbatch = nx_unpack = zbictest = None
    else:
        checkout, cli, zbatch, nx_unpack, zbictest, work = (Path(p).resolve() for p in a[:6])
    shutil.rmtree(work, ignore_errors=True)
    (work / 'in').mkdir(parents=True)
    corpus = Corpus(work)
    build_corpus(corpus, checkout)
    print(f'{len(corpus.jobs)} inputs ({sum(k == "nso" for k, *_ in corpus.jobs)} NSOs)', flush=True)

    m_mine, out_mine = corpus.manifest('mine')
    mine = batch([str(cli), 'zbic-batch'], m_mine)
    if mine_only:
        frames, plain, flp, flp_plain, fck, fck_std, ck_text = s2arm_frames(checkout)
        byname = {tag: i for i, (_, _, _, tag) in enumerate(corpus.jobs)}

        def got(tag):
            p = out_mine / f'{byname[tag]}.out'
            return p.read_bytes() if p.exists() else None
        report(all(got(f'S2Arm frame A{k + 1}') == plain[k] for k in range(3)), 'S2Arm frames decode to Gen()', '')
        report(got('S2Arm low-probability frame') == flp_plain, 'S2Arm low-probability frame', '')
        report(got('S2Arm checksum frame') == ck_text, 'S2Arm checksum frame', '')
        same = [i for i in range(len(frames[0])) if got(f'A1 byte {i} ^ 0x1') == plain[0]]
        report(same == [15, 20, 459], 'one-byte changes of A1 that still decode to the text = S2Arm D1 (15, 20, 459)', str(same))
        enc = [i for i, (_, _, _, tag) in enumerate(corpus.jobs) if tag.startswith('encoder seed') and tag.endswith('bytes)')]
        report(all(mine[i][0] == 'ok' for i in enc), 'encoder frames decode', f'{len(enc)} frames')
        print(f"{state['ran']} checks, {state['failed']} failed; {sum(v[0] == 'ok' for v in mine.values())} of {len(mine)} inputs decode")
        sys.exit(1 if state['failed'] else 0)

    m_ref, out_ref = corpus.manifest('ref')
    ref = batch([str(zbatch)], m_ref)
    crashes = [i for i, v in ref.items() if v[0] == 'crash']
    mismatched = {}
    for i, (kind, _, _, tag) in enumerate(corpus.jobs):
        r_ok, m_ok = ref.get(i, ('missing', ''))[0] == 'ok', mine.get(i, ('missing', ''))[0] == 'ok'
        same = r_ok == m_ok and (not r_ok or (out_ref / f'{i}.out').read_bytes() == (out_mine / f'{i}.out').read_bytes())
        if not same:
            mismatched[i] = f'{tag}: reference {ref.get(i)}, mine {mine.get(i)}'
    frames_n = sum(k == 'frame' for k, *_ in corpus.jobs)
    for kind, label in (('frame', 'ZbicDecoder.Decompress'), ('nso', 'NsoZbic.Normalize')):
        idx = [i for i, j in enumerate(corpus.jobs) if j[0] == kind]
        bad = [mismatched[i] for i in idx if i in mismatched]
        ok_count = sum(ref.get(i, ('', ''))[0] == 'ok' for i in idx)
        report(not bad, f'{label} vs s2arm_zbic.c', f'{len(idx)} inputs, {ok_count} decode, {len(idx) - ok_count} fail in both'
               if not bad else f'{len(bad)} differ: {bad[:5]}')
    if crashes:
        print(f'note: {len(crashes)} inputs end the C# original in a non-InvalidDataException exception (nx_unpack exits 1); '
              f'first: {[corpus.jobs[i][3] + " " + ref[i][1] for i in crashes[:5]]}')
    print(f'{frames_n} frame inputs, {len(corpus.jobs) - frames_n} NSO inputs compared', flush=True)

    # The real command lines: nx_unpack --nso-normalize and ours, on a subset and on ZbicTest's samples.
    cmp_dir = work / 'cli'
    cmp_dir.mkdir()
    samples = []
    for flags in ('BF', 'FF'):
        sample, expected = cmp_dir / f'emit-{flags}.nso', cmp_dir / f'emit-{flags}.exp'
        r = subprocess.run([str(zbictest), '--emit', str(sample), str(expected), flags], capture_output=True, text=True)
        report(r.returncode == 0 and sample.is_file(), f'ZbicTest --emit {flags}', r.stderr.strip()[-200:])
        samples.append((f'ZbicTest sample {flags}', sample, expected))
    pick = [i for i, j in enumerate(corpus.jobs) if j[0] == 'nso']
    pick = pick[:12] + pick[-8:] + pick[12:len(pick) - 8:97]
    inputs = samples + [(corpus.jobs[i][3], corpus.jobs[i][1], None) for i in pick]
    inputs.append(('missing input', cmp_dir / 'no-such.nso', None))
    differ = []
    for n, (tag, path, expected) in enumerate(inputs):
        ro, mo = cmp_dir / f'{n}.ref', cmp_dir / f'{n}.mine'
        rr = subprocess.run([str(nx_unpack), '--nso-normalize', str(path), str(ro)], capture_output=True, text=True)
        mr = subprocess.run([str(cli), 'nso-normalize', str(path), str(mo)], capture_output=True, text=True)
        same = (rr.returncode == 0) == (mr.returncode == 0) and ro.exists() == mo.exists() and \
            (not ro.exists() or ro.read_bytes() == mo.read_bytes()) and (rr.returncode == 0 or not mo.exists())
        if expected is not None:
            same = same and mo.exists() and mo.read_bytes() == expected.read_bytes()
        if not same:
            differ.append(f'{tag}: nx_unpack rc={rr.returncode} {rr.stderr.strip()[-120:]!r}; mine rc={mr.returncode} {mr.stderr.strip()[-120:]!r}')
    report(not differ, 'nx_unpack --nso-normalize vs s2arm_prepare_cli nso-normalize', f'{len(inputs)} files' if not differ else str(differ[:5]))
    r = subprocess.run([str(zbictest)], capture_output=True, text=True)
    print(f'note: S2Arm ZbicTest itself exits {r.returncode}: {(r.stdout.strip().splitlines() or [""])[-1]}')

    print(f"{state['ran']} checks, {state['failed']} failed")
    sys.exit(1 if state['failed'] or state['ran'] < 5 else 0)


if __name__ == '__main__':
    main()
