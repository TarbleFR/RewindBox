#!/usr/bin/env python3
"""A small ZBIC encoder for synthetic test input (written for RewindBox; no S2Arm code).

ZBIC is zstd (RFC 8878) with the frame magic "ZBIC" and the FSE normalised-count
headers written with binary interpolative coding (BIC). This encoder produces valid
frames that exercise every part a ZBIC decoder has: raw / RLE / compressed blocks;
raw, RLE, Huffman (1 and 4 streams, FSE-compressed or direct weights) and treeless
literals; predefined, RLE, FSE-compressed (BIC header, with and without the
low-probability flag) and repeated sequence tables; repeat offsets; single-segment
frames with 1/2/4/8-byte content sizes, window descriptors, zero dictionary ids,
checksums, several frames and skippable frames. Choices are drawn from a seeded
random.Random, so a seed names a frame. It is a test tool: speed and ratio do not matter.

    zbic_frames(data, rng)  -> ZBIC bytes (one or more frames) decoding to data
    zbic_nso(nso, rng, ...) -> the NSO with its segments ZBIC-compressed (flag 0x80)
"""
import hashlib
import heapq
import random
import struct
import sys

MAGIC = b'ZBIC'
BLOCK_MAX = 128 << 10
LL_BASE = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 18, 20, 22, 24, 28, 32, 40, 48, 64, 128, 256, 512,
           1024, 2048, 4096, 8192, 16384, 32768, 65536]
LL_BITS = [0] * 16 + [1, 1, 1, 1, 2, 2, 3, 3, 4, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16]
ML_BASE = list(range(3, 35)) + [35, 37, 39, 41, 43, 47, 51, 59, 67, 83, 99, 131, 259, 515, 1027, 2051, 4099, 8195,
                                16387, 32771, 65539]
ML_BITS = [0] * 32 + [1, 1, 1, 1, 2, 2, 3, 3, 4, 4, 5, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16]
LL_DEF = ([4, 3, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 1, 1, 1, 2, 2, 2, 2, 2, 2, 2, 2, 2, 3, 2, 1, 1, 1, 1, 1, -1, -1, -1, -1], 6)
ML_DEF = ([1, 4, 3, 2, 2, 2, 2, 2, 2] + [1] * 37 + [-1] * 7, 6)
OF_DEF = ([1, 1, 1, 1, 1, 1, 2, 2, 2] + [1] * 15 + [-1] * 5, 5)
LIMITS = {'ll': (35, 9), 'of': (31, 8), 'ml': (52, 9)}   # symbol limit, table log limit (the decoder's)


class Bits:
    """Fields in the order the decoder reads them; serialised as a backward bit stream."""

    def __init__(self):
        self.fields = []

    def put(self, value, n):
        assert 0 <= value < (1 << n) or (n == 0 and value == 0)
        self.fields.append((value, n))

    def total(self):
        return sum(n for _, n in self.fields)

    def bytes(self):
        t = self.total()
        acc, pos = 1 << t, t
        for v, n in self.fields:
            pos -= n
            acc |= v << pos
        return acc.to_bytes(t // 8 + 1, 'little')


def highbit(v):
    return v.bit_length() - 1


class Fse:
    """The decoder's FSE table (same spreading), with the tANS ranges used to encode."""

    def __init__(self, norm, log):
        size = 1 << log
        self.log, self.norm = log, list(norm)
        self.sym, self.nb, self.base = [0] * size, [0] * size, [0] * size
        nxt, high = [0] * len(norm), size - 1
        for s, c in enumerate(norm):
            if c == -1:
                self.sym[high] = s
                high -= 1
                nxt[s] = 1
            else:
                nxt[s] = c
        pos, step, mask = 0, (size >> 1) + (size >> 3) + 3, size - 1
        for s, c in enumerate(norm):
            for _ in range(max(c, 0)):
                self.sym[pos] = s
                pos = (pos + step) & mask
                while pos > high:
                    pos = (pos + step) & mask
        assert pos == 0
        for u in range(size):
            s = self.sym[u]
            x = nxt[s]
            nxt[s] += 1
            nb = log - highbit(x)
            self.nb[u], self.base[u] = nb, (x << nb) - size
        self.states = {}
        for u in range(size):
            self.states.setdefault(self.sym[u], []).append(u)

    def has(self, s):
        return s in self.states

    def encode(self, syms, rng, last_needs_bits=False):
        """States for syms (decoder order) and the update bits between them.
        Returns (initial state, [(bits, nb) for the update after symbol i, i < len-1])."""
        cand = self.states[syms[-1]]
        if last_needs_bits:
            cand = [u for u in cand if self.nb[u] > 0]
            if not cand:
                return None
        state = rng.choice(cand)
        ups = []
        for s in reversed(syms[:-1]):
            prev = next(u for u in self.states[s] if self.base[u] <= state < self.base[u] + (1 << self.nb[u]))
            ups.append((state - self.base[prev], self.nb[prev]))
            state = prev
        ups.reverse()
        return state, ups


def rle_table(s):
    t = Fse.__new__(Fse)
    t.log, t.sym, t.nb, t.base, t.states, t.norm = 0, [s], [0], [0], {s: [0]}, None
    return t


DEF = {'ll': Fse(*LL_DEF), 'ml': Fse(*ML_DEF), 'of': Fse(*OF_DEF)}


def bic_digits(norm, log, lp, rng):
    max_sym = len(norm) - 1
    P = 1
    while P <= max_sym:
        P <<= 1
    cum = [0] * (P + 1)
    for s in range(max_sym + 1):
        cum[s + 1] = cum[s] + norm[s] + lp
    for s in range(max_sym + 2, P + 1):
        cum[s] = cum[max_sym + 1]
    top, total = cum[P], 1 << log
    last = top - max_sym - 2 if lp else top - 1
    assert 0 <= last < total
    digits = [(max_sym - 1, 52), (log - 5, 8), (last, total)]

    def split(lo, hi):
        if hi - lo < 2 or cum[lo] == cum[hi]:
            return
        mid = (lo + hi) >> 1
        digits.append((cum[mid] - cum[lo], cum[hi] - cum[lo] + 1))
        split(mid, hi)
        split(lo, mid)
    split(0, P)
    if cum[1] != 0:
        digits.append((rng.randrange(cum[1] + 1), cum[1] + 1))
    return digits


def bic_payload(digits, rng):
    """Bytes the decoder's refill-at-2^40 mixed-radix reader turns into digits (built backwards)."""
    L, U = 1 << 40, 1 << 48
    for _ in range(100):
        x, out, ok = rng.randrange(L, U), [], True
        for r, m in reversed(digits):
            for k in (0, 1, 2) if rng.random() < 0.5 else (1, 0, 2):
                y = (x >> (8 * k)) * m + r
                if L <= y < U:
                    for _ in range(k):
                        out.append(x & 255)
                        x >>= 8
                    x = y
                    break
            else:
                ok = False
                break
        if ok:
            out += list(x.to_bytes(6, 'little'))
            return bytes(out)
    raise RuntimeError('no BIC payload found')


def bic_header(norm, log, lp, rng):
    payload = bic_payload(bic_digits(norm, log, lp, rng), rng)
    assert len(payload) <= 127
    return bytes([len(payload) | (lp << 7)]) + payload


def normalise(freq, log, rng, allow_low):
    """Normalised counts (sum of |count| = 2^log); rare symbols may get -1 when allow_low."""
    total = 1 << log
    used = [s for s, f in enumerate(freq) if f]
    assert 0 < len(used) <= total
    norm = [0] * len(freq)
    low = set()
    if allow_low and len(used) > 1:
        low = {s for s in used if rng.random() < 0.3}
        if len(low) == len(used):
            low.discard(used[0])
    for s in low:
        norm[s] = -1
    rest = [s for s in used if s not in low]
    left = total - len(low)
    for s in rest:
        norm[s] = 1
    left -= len(rest)
    weight = sum(freq[s] for s in rest)
    for s in rest:
        add = left * freq[s] // weight
        norm[s] += add
    left = total - sum(abs(c) for c in norm)
    i = 0
    while left > 0:
        norm[rest[i % len(rest)]] += 1
        left -= 1
        i += 1
    return norm


def huffman_lengths(freq):
    freq = list(freq)
    while True:
        heap = [(f, i, (i,)) for i, f in enumerate(freq) if f]
        if len(heap) < 2:
            return None
        heapq.heapify(heap)
        length = [0] * len(freq)
        n = len(freq)
        while len(heap) > 1:
            f1, _, a = heapq.heappop(heap)
            f2, _, b = heapq.heappop(heap)
            for s in a + b:
                length[s] += 1
            heapq.heappush(heap, (f1 + f2, n, a + b))
            n += 1
        if max(length) <= 11:
            return length
        freq = [(f >> 1) + 1 if f else 0 for f in freq]


class FrameState:
    def __init__(self):
        self.huff = None       # (weights by symbol, max_bits) of the last Huffman table
        self.tables = {}       # 'll'/'of'/'ml' -> last table
        self.rep = [1, 4, 8]


def huffman_codes(weights, max_bits):
    codes, pos = {}, 0
    for wt in range(1, max_bits + 1):
        for s, w in enumerate(weights):
            if w == wt:
                span = 1 << (wt - 1)
                codes[s] = (pos >> (wt - 1), max_bits + 1 - wt)
                pos += span
    assert pos == 1 << max_bits
    return codes


def huff_stream(lits, codes):
    b = Bits()
    for c in lits:
        b.put(*codes[c])
    return b.bytes() if b.fields else b'\x01'


def tree_description(weights, rng):
    """weights for symbols 0..last (the last one implied). Direct or FSE-compressed."""
    last = max(s for s, w in enumerate(weights) if w)
    explicit = weights[:last]
    n = len(explicit)
    if n >= 2 and rng.random() < 0.7:
        freq = [0] * (max(explicit) + 1)
        for w in explicit:
            freq[w] += 1
        if len(freq) < 2:
            freq.append(0)
        for _ in range(8):
            log = rng.choice([5, 6])
            low_ok = rng.random() < 0.5
            norm = normalise(freq, log, rng, low_ok)
            t = Fse(norm, log)
            chains = [explicit[0::2], explicit[1::2]]
            last_chain = (n - 2) % 2
            enc = [t.encode(chains[k], rng, last_needs_bits=(k == last_chain)) for k in (0, 1)]
            if None in enc:
                continue
            lp = 1 if (low_ok or rng.random() < 0.3) and -1 in norm or rng.random() < 0.2 else 0
            if -1 in norm:
                lp = 1
            head = bic_header(norm, log, lp, rng)
            b = Bits()
            b.put(enc[0][0], log)
            b.put(enc[1][0], log)
            ups = [enc[0][1], enc[1][1]]
            idx = [0, 0]
            for j in range(n - 2):   # update after W[j], chain j % 2
                k = j % 2
                b.put(*ups[k][idx[k]])
                idx[k] += 1
            z = head + b.bytes()
            if len(z) < 128:
                return bytes([len(z)]) + z
    if n > 128 or n < 1:
        return None
    packed = bytearray()
    for i in range(0, n, 2):
        packed.append(explicit[i] << 4 | (explicit[i + 1] if i + 1 < n else 0))
    return bytes([127 + n]) + bytes(packed)


def literals_section(lits, fs, rng):
    n = len(lits)
    options = ['raw']
    if n and len(set(lits)) == 1:
        options.append('rle')
    if n >= 2 and len(set(lits)) > 1:
        options += ['huff', 'huff']
        if fs.huff and all(fs.huff[0][c] if c < len(fs.huff[0]) else 0 for c in set(lits)):
            options.append('treeless')
    kind = rng.choice(options)
    if kind in ('raw', 'rle'):
        t = 0 if kind == 'raw' else 1
        if n < 32 and rng.random() < 0.8:
            head = bytes([t | n << 3])
        elif n < 4096 and rng.random() < 0.8:
            head = bytes([t | 1 << 2 | (n & 15) << 4, n >> 4])
        else:
            head = bytes([t | 3 << 2 | (n & 15) << 4, (n >> 4) & 255, n >> 12])
        return head + (bytes(lits) if kind == 'raw' else bytes(lits[:1]))
    if kind == 'treeless':
        weights, max_bits = fs.huff
        tree, t = b'', 3
    else:
        freq = [0] * 256
        for c in lits:
            freq[c] += 1
        length = huffman_lengths(freq)
        if length is None:
            return literals_section_raw(lits)
        max_bits = max(length)
        weights = [max_bits + 1 - l if l else 0 for l in length]
        while weights and weights[-1] == 0:
            weights.pop()
        tree = tree_description(weights, rng)
        if tree is None:
            return literals_section_raw(lits)
        t = 2
    codes = huffman_codes(weights, max_bits)
    seg = (n + 3) // 4
    four = n - 3 * seg >= 0 and (n > 1023 or rng.random() < 0.5)
    if four:
        parts = [lits[0:seg], lits[seg:2 * seg], lits[2 * seg:3 * seg], lits[3 * seg:]]
        streams = [huff_stream(p, codes) for p in parts]
        if any(len(s) > 0xFFFF for s in streams[:3]):
            return literals_section_raw(lits)
        body = struct.pack('<HHH', *(len(s) for s in streams[:3])) + b''.join(streams)
    else:
        if n > 1023:
            return literals_section_raw(lits)
        body = huff_stream(lits, codes)
    csize = len(tree) + len(body)
    if not four:
        if csize > 1023:
            return literals_section_raw(lits)
        v = t | 0 << 2 | n << 4 | csize << 14
        head = v.to_bytes(3, 'little')
    elif n < 1024 and csize < 1024 and rng.random() < 0.5:
        head = (t | 1 << 2 | n << 4 | csize << 14).to_bytes(3, 'little')
    elif n < 16384 and csize < 16384 and rng.random() < 0.6:
        head = (t | 2 << 2 | n << 4 | csize << 18).to_bytes(4, 'little')
    elif csize < (1 << 18):
        head = (t | 3 << 2 | n << 4 | csize << 22).to_bytes(5, 'little')
    else:
        return literals_section_raw(lits)
    fs.huff = (weights, max_bits)
    return head + tree + body


def literals_section_raw(lits):
    n = len(lits)
    return bytes([3 << 2 | (n & 15) << 4, (n >> 4) & 255, n >> 12]) + bytes(lits)


def code_of(value, base, bits):
    for c in range(len(base) - 1, -1, -1):
        if base[c] <= value:
            assert value < base[c] + (1 << bits[c])
            return c
    raise ValueError(value)


def choose_table(name, codes, fs, rng):
    """(mode, table, header bytes) for one of the three sequence streams."""
    limit, log_limit = LIMITS[name]
    opts = []
    if len(set(codes)) == 1:
        opts.append('rle')
    if all(DEF[name].has(c) for c in codes):
        opts.append('def')
    prev = fs.tables.get(name)
    if prev is not None and all(prev.has(c) for c in codes):
        opts.append('repeat')
    opts += ['fse', 'fse']
    while True:
        kind = rng.choice(opts)
        if kind == 'rle':
            return 1, rle_table(codes[0]), bytes([codes[0]])
        if kind == 'def':
            return 0, DEF[name], b''
        if kind == 'repeat':
            return 3, prev, b''
        max_sym = max(max(codes), 1)
        freq = [0] * (max_sym + 1)
        for c in codes:
            freq[c] += 1
        if rng.random() < 0.3 and max_sym < limit:   # a few unused symbols above
            freq += [0] * rng.randrange(1, min(4, limit - max_sym) + 1)
        used = sum(1 for f in freq if f)
        logs = [g for g in range(5, log_limit + 1) if (1 << g) >= used]
        if not logs:
            opts = [o for o in opts if o != 'fse'] or ['def']
            continue
        log = rng.choice(logs)
        low_ok = rng.random() < 0.4
        norm = normalise(freq, log, rng, low_ok)
        lp = 1 if -1 in norm or rng.random() < 0.3 else 0
        return 2, Fse(norm, log), bic_header(norm, log, lp, rng)


def find_sequences(out, start, end, frame_start, rng):
    """Greedy LZ77 over out[frame_start:end] for the block out[start:end]: [(llen, offset, mlen)], literal tail."""
    table, seqs, lit_start, i = {}, [], start, start
    for j in range(max(frame_start, start - 4096), start):
        table[bytes(out[j:j + 4])] = j
    min_match = rng.choice([3, 4, 6])
    while i + 4 <= end:
        key = bytes(out[i:i + 4])
        j = table.get(key)
        table[key] = i
        if j is not None and rng.random() < 0.9:
            m = 0
            while i + m < end and out[j + m] == out[i + m] and m < 0x1FFFF:
                m += 1
            if m >= min_match:
                seqs.append((i - lit_start, i - j, m))
                i += m
                lit_start = i
                continue
        i += 1
    return seqs, lit_start


def sequences_section(seqs, fs, rng):
    """seqs: [(llen, offset, mlen)]. Picks offset representations (repeat codes when possible)."""
    rows = []
    rep = fs.rep
    for llen, off, mlen in seqs:
        choices = [off + 3]
        if llen > 0:
            choices += [k + 1 for k, r in enumerate(rep) if r == off]
        else:
            if rep[1] == off:
                choices.append(1)
            if rep[2] == off:
                choices.append(2)
            if rep[0] - 1 == off:
                choices.append(3)
        ov = rng.choice(choices)
        # The decoder's repeat-offset update.
        if ov > 3:
            rep[:] = [min(ov - 3, 0x7FFFFFFF), rep[0], rep[1]]
        else:
            idx = ov - 1 + (1 if llen == 0 else 0)
            if idx != 0:
                o = rep[1] if idx == 1 else rep[2] if idx == 2 else rep[0] - 1
                if idx != 1:
                    rep[2] = rep[1]
                rep[1] = rep[0]
                rep[0] = o
        rows.append((code_of(llen, LL_BASE, LL_BITS), llen, highbit(ov), ov, code_of(mlen, ML_BASE, ML_BITS), mlen))
    n = len(rows)
    head = bytes([n]) if n < 128 else bytes([(n >> 8) + 128, n & 255]) if n < 0x7F00 else bytes([255]) + struct.pack('<H', n - 0x7F00)
    lm, lt, lh = choose_table('ll', [r[0] for r in rows], fs, rng)
    om, ot, oh = choose_table('of', [r[2] for r in rows], fs, rng)
    mm, mt, mh = choose_table('ml', [r[4] for r in rows], fs, rng)
    fs.tables.update(ll=lt, of=ot, ml=mt)
    head += bytes([lm << 6 | om << 4 | mm << 2]) + lh + oh + mh
    enc = {}
    for name, t, col in (('ll', lt, 0), ('of', ot, 2), ('ml', mt, 4)):
        enc[name] = t.encode([r[col] for r in rows], rng)
    b = Bits()
    b.put(enc['ll'][0], lt.log)
    b.put(enc['of'][0], ot.log)
    b.put(enc['ml'][0], mt.log)
    for i, (lc, llen, oc, ov, mc, mlen) in enumerate(rows):
        b.put(ov - (1 << oc), oc)
        b.put(mlen - ML_BASE[mc], ML_BITS[mc])
        b.put(llen - LL_BASE[lc], LL_BITS[lc])
        if i + 1 < n:
            b.put(*enc['ll'][1][i])
            b.put(*enc['ml'][1][i])
            b.put(*enc['of'][1][i])
    return head + b.bytes()


def compressed_block(out, start, end, frame_start, fs, rng):
    saved = (fs.huff, dict(fs.tables), list(fs.rep))
    if rng.random() < 0.15:
        seqs, tail = [], start
    else:
        seqs, tail = find_sequences(out, start, end, frame_start, rng)
    lits = []
    pos = start
    for llen, off, mlen in seqs:
        lits += out[pos:pos + llen]
        pos += llen + mlen
    lits += out[tail:end]
    body = literals_section(lits, fs, rng)
    body += sequences_section(seqs, fs, rng) if seqs else b'\0'
    return body, saved


def frame(data, rng, single=None, checksum=None):
    data = bytes(data)
    n = len(data)
    fs = FrameState()
    single = rng.random() < 0.4 if single is None else single
    checksum = rng.random() < 0.5 if checksum is None else checksum
    did_flag = rng.choice([0, 0, 0, 1, 2, 3])
    if single:
        sizes = [s for s in (0, 1, 2, 3) if (s != 0 or n < 256) and (s != 1 or 256 <= n < 65792) and (s != 2 or n < 1 << 32)]
        fcs_flag = rng.choice(sizes)
        window = n
        block_max = min(n, BLOCK_MAX)
    else:
        fcs_flag = rng.choice([0, 0, 1, 2, 3]) if n >= 256 else rng.choice([0, 2, 3])
        if fcs_flag == 1 and not 256 <= n < 65792:
            fcs_flag = 2
        e = rng.choice([0, 3, 7, 7, 8, 12])
        m = rng.randrange(8)
        window = (1 << (10 + e)) + ((1 << (10 + e)) >> 3) * m
        block_max = min(window, BLOCK_MAX)
    fhd = fcs_flag << 6 | (1 if single else 0) << 5 | (1 if checksum else 0) << 2 | did_flag
    out = bytearray(MAGIC) + bytes([fhd])
    if not single:
        out.append(e << 3 | m)
    out += bytes([0, 1, 2, 4][did_flag])   # dictionary id 0 in the chosen width
    fcs_size = (1 if single else 0) if fcs_flag == 0 else 1 << fcs_flag
    if fcs_size == 2:
        out += struct.pack('<H', n - 256)
    elif fcs_size:
        out += n.to_bytes(fcs_size, 'little')
    pos = 0
    while True:
        chunk = min(n - pos, block_max, rng.choice([block_max, 1 << rng.randrange(4, 18)]))
        end = pos + chunk
        last = end == n
        part = data[pos:end]
        kinds = ['raw', 'comp', 'comp', 'comp']
        if chunk and len(set(part)) == 1:
            kinds += ['rle', 'rle']
        kind = rng.choice(kinds) if chunk else rng.choice(['raw', 'rle'])
        if kind == 'comp':
            body, saved = compressed_block(data, pos, end, 0, fs, rng)
            if len(body) > block_max:
                fs.huff, fs.tables, fs.rep = saved[0], saved[1], saved[2]
                kind = 'raw'
        if kind == 'raw':
            out += (int(last) | 0 << 1 | chunk << 3).to_bytes(3, 'little') + part
        elif kind == 'rle':
            out += (int(last) | 1 << 1 | chunk << 3).to_bytes(3, 'little') + (part[:1] or bytes([rng.randrange(256)]))
        else:
            out += (int(last) | 2 << 1 | len(body) << 3).to_bytes(3, 'little') + body
        pos = end
        if last:
            break
    if checksum:
        out += struct.pack('<I', xxh64(data) & 0xFFFFFFFF)
    return bytes(out)


def zbic_frames(data, rng, frames=None):
    data = bytes(data)
    count = frames or (1 if len(data) < 64 or rng.random() < 0.6 else rng.randrange(2, 4))
    cuts = sorted(rng.randrange(len(data) + 1) for _ in range(count - 1))
    out = bytearray()
    prev = 0
    for k, cut in enumerate(cuts + [len(data)]):
        if rng.random() < 0.15:
            skip = bytes(rng.randrange(256) for _ in range(rng.randrange(0, 12)))
            out += struct.pack('<II', 0x184D2A50 | rng.randrange(16), len(skip)) + skip
        out += frame(data[prev:cut], rng)
        prev = cut
    return bytes(out)


P1, P2, P3, P4, P5 = 0x9E3779B185EBCA87, 0xC2B2AE3D27D4EB4F, 0x165667B19E3779F9, 0x85EBCA77C2B2AE63, 0x27D4EB2F165667C5
M64 = (1 << 64) - 1


def _rot(x, r):
    return ((x << r) | (x >> (64 - r))) & M64


def _round(acc, lane):
    return _rot((acc + lane * P2) & M64, 31) * P1 & M64


def xxh64(d):
    n, i = len(d), 0
    if n >= 32:
        v = [(P1 + P2) & M64, P2, 0, (-P1) & M64]
        while i + 32 <= n:
            for k in range(4):
                v[k] = _round(v[k], int.from_bytes(d[i + 8 * k:i + 8 * k + 8], 'little'))
            i += 32
        h = (_rot(v[0], 1) + _rot(v[1], 7) + _rot(v[2], 12) + _rot(v[3], 18)) & M64
        for x in v:
            h = ((h ^ _round(0, x)) * P1 + P4) & M64
    else:
        h = P5
    h = (h + n) & M64
    while i + 8 <= n:
        h = (_rot(h ^ _round(0, int.from_bytes(d[i:i + 8], 'little')), 27) * P1 + P4) & M64
        i += 8
    if i + 4 <= n:
        h = (_rot(h ^ (int.from_bytes(d[i:i + 4], 'little') * P1 & M64), 23) * P2 + P3) & M64
        i += 4
    while i < n:
        h = (_rot(h ^ (d[i] * P5 & M64), 11) * P1) & M64
        i += 1
    h ^= h >> 33
    h = h * P2 & M64
    h ^= h >> 29
    h = h * P3 & M64
    h ^= h >> 32
    return h


def zbic_nso(nso, rng, extra_flags=0, hashes=True, compress=(True, True, True)):
    """An uncompressed NSO (flags bits 0-2 clear) with its segments ZBIC-compressed."""
    nso = bytes(nso)
    assert nso[:4] == b'NSO0' and struct.unpack_from('<I', nso, 0xC)[0] & 7 == 0
    segs = []
    for i in range(3):
        off, _, size = struct.unpack_from('<III', nso, 0x10 + 0x10 * i)
        segs.append(nso[off:off + size])
    first = min(struct.unpack_from('<I', nso, 0x10 + 0x10 * i)[0] for i in range(3))
    head = bytearray(nso[:first])
    flags = 0x80 | extra_flags
    body = bytearray()
    at = first
    for i, plain in enumerate(segs):
        stored = zbic_frames(plain, rng) if compress[i] else plain
        if compress[i]:
            flags |= 1 << i
        if hashes:
            flags |= 8 << i
            head[0xA0 + 0x20 * i:0xC0 + 0x20 * i] = hashlib.sha256(plain).digest()
        struct.pack_into('<I', head, 0x10 + 0x10 * i, at)
        struct.pack_into('<I', head, 0x60 + 4 * i, len(stored))
        body += stored
        at += len(stored)
    struct.pack_into('<I', head, 0xC, flags)
    return bytes(head + body)


def rle_frame(size, value=0x41):
    """One ZBIC frame of `size` bytes made only of 128 KiB RLE blocks (4 bytes each): ~32 KiB per GiB."""
    out = bytearray(MAGIC) + bytes([0x00, 0x38])   # no content size, no checksum; window 2^17 = 128 KiB
    left = size
    while True:
        n = min(left, BLOCK_MAX)
        left -= n
        out += (int(left == 0) | 1 << 1 | n << 3).to_bytes(3, 'little') + bytes([value])
        if left == 0:
            return bytes(out)


def rle_bomb_nso(sizes, flags=0x87):
    """A tiny NSO whose ZBIC segments declare and decode to `sizes` bytes (decompression-bomb tests)."""
    head = bytearray(0x100)
    head[:4] = b'NSO0'
    struct.pack_into('<I', head, 0xC, flags)
    body, at, mem = bytearray(), 0x100, 0
    for i, size in enumerate(sizes):
        stored = rle_frame(size, 0x41 + i)
        struct.pack_into('<III', head, 0x10 + 0x10 * i, at, mem, size)
        struct.pack_into('<I', head, 0x60 + 4 * i, len(stored))
        body += stored
        at += len(stored)
        mem += size
    return bytes(head + body)


def lz4_bomb_nso(sizes):
    """An NSO whose LZ4 segments (flags 0-2) declare `sizes` bytes but hold a few bytes of LZ4 data."""
    head = bytearray(0x100)
    head[:4] = b'NSO0'
    struct.pack_into('<I', head, 0xC, 0x07)
    lz4 = bytes([0x10, 0x41])   # one literal "A"
    at = 0x100
    for i, size in enumerate(sizes):
        struct.pack_into('<III', head, 0x10 + 0x10 * i, at, 0, size)
        struct.pack_into('<I', head, 0x60 + 4 * i, len(lz4))
        at += len(lz4)
    return bytes(head) + lz4 * len(sizes)


if __name__ == '__main__':
    # make_synth_zbic.py <plain in> <zbic out> [seed]   or   --nso <nso in> <nso out> [seed]
    a = sys.argv[1:]
    if a and a[0] == '--nso':
        out = zbic_nso(open(a[1], 'rb').read(), random.Random(int(a[3]) if len(a) > 3 else 1))
        open(a[2], 'wb').write(out)
    else:
        open(a[1], 'wb').write(zbic_frames(open(a[0], 'rb').read(), random.Random(int(a[2]) if len(a) > 2 else 1)))
