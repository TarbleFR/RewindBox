// See s2arm_zbic.h. Port of S2Arm pack/nx_unpack/ZbicDecoder.cs and NsoZbic.cs (Apache-2.0,
// pinned commit in tools/s2arm_prototype/pin.json). The structure, the order of the checks
// and the arithmetic follow the C# line by line, so that every input the original accepts
// gives the same bytes and every input it rejects is rejected here. Where the C# would end
// in a runtime exception other than InvalidDataException (index out of range, allocation
// failure) this port fails cleanly with an error as well; nx_unpack exits 1 in both cases.
#define _POSIX_C_SOURCE 200809L
#include "s2arm_zbic.h"

#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>

#define ZBIC_MAGIC 0x4349425Au   // "ZBIC"
#define ZSTD_MAGIC 0xFD2FB528u   // standard zstd: reported as "not ZBIC"
#define BLOCK_MAX (128 << 10)    // RFC 8878 Block_Maximum_Size

typedef struct {
    char *error;
    size_t error_size;
    const char *prefix;                    // "<name>: NSO segment <i> ZBIC data cannot be decoded (" ... ")" when set
    const rb_s2arm_zbic_options *options;  // cancellation (may be NULL)
    int *stopped;                          // set to 1 when the cancel callback stopped the work (may be NULL)
} ctx_t;

#if defined(__GNUC__)
__attribute__((format(printf, 2, 3)))
#endif
static int bad(ctx_t *x, const char *fmt, ...) {
    if (x->error && x->error_size) {
        char message[512];
        va_list ap;
        va_start(ap, fmt);
        vsnprintf(message, sizeof message, fmt, ap);
        va_end(ap);
        if (x->prefix) snprintf(x->error, x->error_size, "%s%s)", x->prefix, message);
        else snprintf(x->error, x->error_size, "%s", message);
    }
    return -1;
}

// Polls the cancel callback; when it asks to stop, records it and fails like an error.
static int stop_requested(ctx_t *x) {
    if (!x->options || !x->options->cancelled || !x->options->cancelled(x->options->context)) return 0;
    if (x->stopped) *x->stopped = 1;
    if (x->error && x->error_size) snprintf(x->error, x->error_size, "cancelled");
    return 1;
}

static uint32_t le32(const uint8_t *p) { return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24; }
static uint64_t le64(const uint8_t *p) { return (uint64_t)le32(p) | (uint64_t)le32(p + 4) << 32; }
static void put32(uint8_t *p, uint32_t v) {
    p[0] = (uint8_t)v;
    p[1] = (uint8_t)(v >> 8);
    p[2] = (uint8_t)(v >> 16);
    p[3] = (uint8_t)(v >> 24);
}
static int highbit32(uint32_t v) { // 31 - LeadingZeroCount(v); -1 for 0
    int n = -1;
    while (v) {
        n++;
        v >>= 1;
    }
    return n;
}

// ---------------- backward bit stream (RFC 8878 4.1) ----------------
typedef struct {
    const uint8_t *b;
    size_t len;
    int64_t pos;   // bits not read yet; negative once read past the start (zeros are read)
} bits_t;

static int bits_init(ctx_t *x, bits_t *s, const uint8_t *b, size_t len) {
    if (len == 0 || b[len - 1] == 0) return bad(x, "bit stream empty or its last byte is 0 (no end mark)");
    s->b = b;
    s->len = len;
    s->pos = 8 * (int64_t)(len - 1) + highbit32(b[len - 1]);
    return 0;
}
static uint64_t bits_at(const bits_t *s, int64_t from, int n) {   // bits [from, from+n), from >= 0, n <= 56
    size_t i = (size_t)(from >> 3);
    int sh = (int)(from & 7);
    uint64_t v = 0;
    if (i + 8 <= s->len) v = le64(s->b + i);
    else
        for (size_t k = 0; k < 8 && i + k < s->len; k++) v |= (uint64_t)s->b[i + k] << (8 * k);
    return (v >> sh) & ((1ull << n) - 1);
}
static uint64_t bits_peek(const bits_t *s, int n) {
    if (n == 0) return 0;
    int64_t from = s->pos - n;
    if (from >= 0) return bits_at(s, from, n);
    if (s->pos <= 0) return 0;
    return bits_at(s, 0, (int)s->pos) << (n - s->pos);
}
static uint64_t bits_read(bits_t *s, int n) {
    uint64_t v = bits_peek(s, n);
    s->pos -= n;
    return v;
}

// ---------------- FSE decoding tables ----------------
typedef struct {
    int log;
    uint8_t sym[512];
    uint8_t nbits[512];
    uint16_t base[512];
} fse_t;

static int fse_build(ctx_t *x, fse_t *t, const int16_t *norm, int max_sym, int log) {
    if (log < 0 || log > 9 || max_sym < 0 || max_sym > 255) return bad(x, "FSE table parameters out of range");
    int size = 1 << log, high = size - 1, next[256], positive = 0;
    t->log = log;
    memset(t->sym, 0, (size_t)size);
    for (int s = 0; s <= max_sym; s++) {
        if (norm[s] == -1) {   // "less than 1" probability: one cell each at the end of the table
            if (high < 0) return bad(x, "FSE table cannot be filled (normalised counts inconsistent)");
            t->sym[high--] = (uint8_t)s;
            next[s] = 1;
        } else {
            next[s] = norm[s];
            if (norm[s] > 0) positive += norm[s];
        }
    }
    if (positive > high + 1) return bad(x, "FSE table cannot be filled (normalised counts inconsistent)");
    int pos = 0, step = (size >> 1) + (size >> 3) + 3, mask = size - 1;
    for (int s = 0; s <= max_sym; s++)
        for (int k = 0; k < norm[s]; k++) {
            t->sym[pos] = (uint8_t)s;
            do pos = (pos + step) & mask;
            while (pos > high);
        }
    if (pos != 0) return bad(x, "FSE table cannot be filled (normalised counts inconsistent)");
    for (int u = 0; u < size; u++) {
        int s = t->sym[u];
        if (s > max_sym) return bad(x, "FSE table cannot be filled (normalised counts inconsistent)");
        int v = next[s]++;
        if (v <= 0) return bad(x, "FSE table cannot be filled (normalised counts inconsistent)");
        int nb = log - highbit32((uint32_t)v);
        if (nb < 0) return bad(x, "FSE table cannot be filled (normalised counts inconsistent)");
        t->nbits[u] = (uint8_t)nb;
        t->base[u] = (uint16_t)((v << nb) - size);
    }
    return 0;
}
static void fse_rle(fse_t *t, uint8_t s) {
    t->log = 0;
    t->sym[0] = s;
    t->nbits[0] = 0;
    t->base[0] = 0;
}

// ---------------- BIC normalised-count header ----------------
// Rules (facts from Atmosphere zstd.c FSE_readNCount_bic, as written in the C# comments):
//  first byte: low 7 bits = payload byte count n, high bit = "low probability" flag lp; the
//  header takes 1+n bytes and must be strictly shorter than the available data. The payload
//  is a mixed-radix number read from its last byte backwards (refill while the accumulator is
//  below 2^40). Digits: max symbol - 1 (radix 52), table log - 5 (radix 8), the low part L of
//  the last cumulative value (radix 2^log); last cumulative = lp ? maxSym + L + 2 : L + 1.
//  cum[0..P] (P = smallest power of two above max symbol, <= 128): interval halving, preorder,
//  right half first; equal ends fill the interval without reading; then, if cum[1] != 0, one
//  digit of radix cum[1]+1 is read and dropped. Count of s = cum[s+1] - cum[s] - lp.
typedef struct {
    const uint8_t *p;
    size_t left;
    uint64_t acc;
} digits_t;

static void digits_fill(digits_t *d) {
    while (d->left > 0 && d->acc < (1ull << 40)) d->acc = (d->acc << 8) | d->p[--d->left];
}
static uint64_t digits_take(digits_t *d, uint64_t m) {
    uint64_t r = d->acc % m;
    d->acc /= m;
    digits_fill(d);
    return r;
}

static int bic_split(ctx_t *x, int lo, int hi, int *cum, digits_t *d) {   // depth <= log2(128) = 7
    if (hi - lo < 2) return 0;
    if (cum[lo] == cum[hi]) {
        for (int k = lo + 1; k < hi; k++) cum[k] = cum[lo];
        return 0;
    }
    if (cum[hi] < cum[lo]) return bad(x, "BIC header: cumulative count goes backwards");
    int mid = (lo + hi) >> 1;
    cum[mid] = cum[lo] + (int)digits_take(d, (uint64_t)(cum[hi] - cum[lo] + 1));
    if (bic_split(x, mid, hi, cum, d)) return -1;
    return bic_split(x, lo, mid, cum, d);
}

// Returns the header size, or -1.
static int read_counts(ctx_t *x, const uint8_t *src, size_t len, int sym_limit, int log_limit, int16_t *norm, int *max_sym_out,
                       int *log_out) {
    if (len == 0) return bad(x, "BIC header: no data");
    int n = src[0] & 0x7F, lp = src[0] >> 7;
    if ((size_t)n + 1 >= len) return bad(x, "BIC header runs past the data");
    digits_t d = {src + 1, (size_t)n, 0};
    digits_fill(&d);
    int max_sym = (int)digits_take(&d, 52) + 1;
    if (max_sym > sym_limit) return bad(x, "BIC header: max symbol %d above the limit %d", max_sym, sym_limit);
    int log = (int)digits_take(&d, 8) + 5;
    if (log > log_limit) return bad(x, "BIC header: table log %d above the limit %d", log, log_limit);
    int total = 1 << log, last = (int)digits_take(&d, (uint64_t)total);
    int top = lp ? max_sym + last + 2 : last + 1;
    int P = 1;
    while (P <= max_sym) P <<= 1;
    if (P > 128) return bad(x, "BIC header: too many symbols");
    int cum[129];
    memset(cum, 0, sizeof cum);
    cum[P] = top;
    if (bic_split(x, 0, P, cum, &d)) return -1;
    if (cum[1] != 0) digits_take(&d, (uint64_t)cum[1] + 1);
    int sum = 0;
    for (int s = 0; s <= max_sym; s++) {
        int c = cum[s + 1] - cum[s] - lp;
        if (c < -1) return bad(x, "BIC header: negative count");
        norm[s] = (int16_t)c;
        sum += c < 0 ? 1 : c;
    }
    if (sum != total) return bad(x, "BIC header: counts sum to %d, not 2^%d", sum, log);
    if (d.left != 0) return bad(x, "BIC header: payload not fully read");
    *max_sym_out = max_sym;
    *log_out = log;
    return n + 1;
}

// ---------------- sequence code tables (RFC 8878 3.1.1.3.2.1) ----------------
static const int LL_BASE[36] = {0,  1,  2,  3,  4,  5,  6,   7,   8,   9,   10,   11,   12,   13,   14,   15,    16,    18,
                                20, 22, 24, 28, 32, 40, 48, 64, 128, 256, 512, 1024, 2048, 4096, 8192, 16384, 32768, 65536};
static const uint8_t LL_BITS[36] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 3, 3, 4, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16};
static const int ML_BASE[53] = {3,  4,  5,  6,  7,  8,  9,  10, 11, 12,  13,  14,  15,  16,   17,   18,   19,   20,
                                21, 22, 23, 24, 25, 26, 27, 28, 29, 30,  31,  32,  33,  34,   35,   37,   39,   41,
                                43, 47, 51, 59, 67, 83, 99, 131, 259, 515, 1027, 2051, 4099, 8195, 16387, 32771, 65539};
static const uint8_t ML_BITS[53] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                                    0, 0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 3, 3, 4, 4, 5, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16};
// Predefined distributions (RFC 8878 3.1.1.3.2.2)
static const int16_t LL_DEF[36] = {4, 3, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 1, 1, 1, 2, 2, 2, 2, 2, 2, 2, 2, 2, 3, 2, 1, 1, 1, 1, 1, -1, -1, -1, -1};
static const int16_t ML_DEF[53] = {1, 4, 3, 2, 2, 2, 2, 2, 2, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1,
                                   1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, -1, -1, -1, -1, -1, -1, -1};
static const int16_t OF_DEF[29] = {1, 1, 1, 1, 1, 1, 2, 2, 2, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, -1, -1, -1, -1, -1};

// ---------------- frame ----------------
enum { T_LL, T_OF, T_ML };
typedef struct {
    uint8_t lit[BLOCK_MAX];
    uint8_t hsym[4096], hlen[4096];   // last Huffman table (treeless literals reuse it)
    int hbits, have_huffman;
    fse_t def[3], own[3], weights;
    const fse_t *slot[3];             // last sequence tables (repeat mode reuses them)
    int32_t r1, r2, r3;               // repeat offsets
    int16_t norm[256];
    uint8_t w[256];
} frame_t;

typedef struct {
    ctx_t *x;
    frame_t *f;
    uint8_t *dst;
    size_t dst_len;
} dec_t;

static int huff_stream(dec_t *z, const uint8_t *s, size_t len, uint8_t *out, size_t n) {
    frame_t *f = z->f;
    bits_t br = {NULL, 0, 0};
    if (bits_init(z->x, &br, s, len)) return -1;
    int mb = f->hbits;
    for (size_t i = 0; i < n; i++) {
        int v = (int)bits_peek(&br, mb);
        out[i] = f->hsym[v];
        br.pos -= f->hlen[v];
    }
    if (br.pos != 0) return bad(z->x, "Huffman stream not read exactly");
    return 0;
}

// Huffman tree description (RFC 8878 4.2.1); returns its size or -1.
static int huff_tree(dec_t *z, const uint8_t *c, size_t clen) {
    ctx_t *x = z->x;
    frame_t *f = z->f;
    if (clen < 1) return bad(x, "Huffman tree description truncated");
    int hb = c[0], nw;
    uint8_t *w = f->w;
    memset(w, 0, 256);
    if (hb < 128) {   // FSE-compressed weights: BIC header
        if (clen - 1 < (size_t)hb) return bad(x, "Huffman weights truncated");
        const uint8_t *zz = c + 1;
        size_t zl = (size_t)hb;
        int max_sym, log;
        int hn = read_counts(x, zz, zl, 255, 6, f->norm, &max_sym, &log);
        if (hn < 0) return -1;
        fse_t *t = &f->weights;
        if (fse_build(x, t, f->norm, max_sym, log)) return -1;
        bits_t br = {NULL, 0, 0};
        if (bits_init(x, &br, zz + hn, zl - (size_t)hn)) return -1;
        int a = (int)bits_read(&br, log), bb = (int)bits_read(&br, log);
        nw = 0;
        for (;;) {   // two states take turns; when the bits run out the other state emits the last one
            if (nw >= 255) return bad(x, "too many Huffman weights");
            w[nw++] = t->sym[a];
            a = t->base[a] + (int)bits_read(&br, t->nbits[a]);
            if (br.pos < 0) {
                if (nw >= 255) return bad(x, "too many Huffman weights");
                w[nw++] = t->sym[bb];
                break;
            }
            if (nw >= 255) return bad(x, "too many Huffman weights");
            w[nw++] = t->sym[bb];
            bb = t->base[bb] + (int)bits_read(&br, t->nbits[bb]);
            if (br.pos < 0) {
                if (nw >= 255) return bad(x, "too many Huffman weights");
                w[nw++] = t->sym[a];
                break;
            }
        }
        hb += 1;
    } else {
        nw = hb - 127;
        int bytes = (nw + 1) / 2;
        if (clen - 1 < (size_t)bytes) return bad(x, "Huffman weights truncated");
        for (int i = 0; i < nw; i++) w[i] = (uint8_t)(i % 2 == 0 ? c[1 + i / 2] >> 4 : c[1 + i / 2] & 15);
        hb = 1 + bytes;
    }
    int64_t sum = 0;
    int rank[13] = {0};
    for (int i = 0; i < nw; i++) {
        if (w[i] > 12) return bad(x, "Huffman weight above 12");
        rank[w[i]]++;
        if (w[i] > 0) sum += (int64_t)1 << (w[i] - 1);
    }
    if (sum == 0) return bad(x, "all Huffman weights are 0");
    int max_bits = 0;
    for (uint64_t v = (uint64_t)sum; v; v >>= 1) max_bits++;   // highbit(sum) + 1
    if (max_bits > 12) return bad(x, "longest Huffman code above 12 bits");
    int64_t rest = ((int64_t)1 << max_bits) - sum;
    if ((rest & (rest - 1)) != 0) return bad(x, "Huffman weights do not leave a power of two");
    int last_w = 0;
    for (uint64_t v = (uint64_t)rest; v; v >>= 1) last_w++;
    if (nw > 255 || last_w > 12) return bad(x, "Huffman weights inconsistent");
    w[nw] = (uint8_t)last_w;
    rank[last_w]++;
    int ns = nw + 1;
    if (rank[1] < 2 || (rank[1] & 1) != 0) return bad(x, "the number of weight-1 Huffman symbols must be even and at least 2");
    int size = 1 << max_bits, pos = 0;
    for (int wt = 1; wt <= max_bits; wt++)
        for (int s = 0; s < ns; s++)
            if (w[s] == wt) {
                int span = 1 << (wt - 1);
                if (pos + span > size) return bad(x, "Huffman table overflow");
                memset(f->hsym + pos, s, (size_t)span);
                memset(f->hlen + pos, max_bits + 1 - wt, (size_t)span);
                pos += span;
            }
    if (pos != size) return bad(x, "Huffman table not full");
    f->hbits = max_bits;
    f->have_huffman = 1;
    return hb;
}

// Literals section (RFC 8878 3.1.1.3.1) into f->lit; returns its size or -1.
static int literals(dec_t *z, const uint8_t *b, size_t blen, int *n_out) {
    ctx_t *x = z->x;
    frame_t *f = z->f;
    if (blen < 1) return bad(x, "literals section truncated");
    int b0 = b[0], type = b0 & 3, sf = (b0 >> 2) & 3;
    if (type < 2) {
        int hs = sf == 1 ? 2 : sf == 3 ? 3 : 1;
        if (blen < (size_t)hs) return bad(x, "literals header truncated");
        int n = hs == 1 ? b0 >> 3 : hs == 2 ? (b0 >> 4) + (b[1] << 4) : (b0 >> 4) + (b[1] << 4) + (b[2] << 12);
        if (n > BLOCK_MAX) return bad(x, "literals above the block limit");
        *n_out = n;
        if (type == 0) {
            if (blen - (size_t)hs < (size_t)n) return bad(x, "raw literals truncated");
            memcpy(f->lit, b + hs, (size_t)n);
            return hs + n;
        }
        if (blen - (size_t)hs < 1) return bad(x, "RLE literals truncated");
        memset(f->lit, b[hs], (size_t)n);
        return hs + 1;
    }
    int hsz = sf < 2 ? 3 : sf + 2, streams = sf == 0 ? 1 : 4;
    if (blen < (size_t)hsz) return bad(x, "literals header truncated");
    int regen, csize;
    if (hsz == 3) {
        uint32_t v = (uint32_t)b0 | (uint32_t)b[1] << 8 | (uint32_t)b[2] << 16;
        regen = (int)((v >> 4) & 0x3FF);
        csize = (int)((v >> 14) & 0x3FF);
    } else if (hsz == 4) {
        uint32_t v = le32(b);
        regen = (int)((v >> 4) & 0x3FFF);
        csize = (int)(v >> 18);
    } else {
        uint64_t v = le32(b) | (uint64_t)b[4] << 32;
        regen = (int)((v >> 4) & 0x3FFFF);
        csize = (int)((v >> 22) & 0x3FFFF);
    }
    if (regen > BLOCK_MAX) return bad(x, "literals above the block limit");
    if (blen - (size_t)hsz < (size_t)csize) return bad(x, "compressed literals truncated");
    const uint8_t *c = b + hsz;
    size_t cl = (size_t)csize;
    int t = 0;
    if (type == 2) {
        if ((t = huff_tree(z, c, cl)) < 0) return -1;
    } else if (!f->have_huffman)
        return bad(x, "literals reuse the previous Huffman table, but this frame has none");
    c += t;
    cl -= (size_t)t;
    if (streams == 1) {
        if (huff_stream(z, c, cl, f->lit, (size_t)regen)) return -1;
    } else {
        if (cl < 6) return bad(x, "Huffman jump table truncated");
        int s1 = c[0] | c[1] << 8, s2 = c[2] | c[3] << 8, s3 = c[4] | c[5] << 8;
        int64_t s4 = (int64_t)cl - 6 - s1 - s2 - s3;
        if (s4 < 1) return bad(x, "Huffman four-stream sizes inconsistent");
        int seg = (regen + 3) / 4, last = regen - 3 * seg;
        if (last < 0) return bad(x, "Huffman four streams: too few literals");
        const uint8_t *d = c + 6;
        if (huff_stream(z, d, (size_t)s1, f->lit, (size_t)seg)) return -1;
        d += s1;
        if (huff_stream(z, d, (size_t)s2, f->lit + seg, (size_t)seg)) return -1;
        d += s2;
        if (huff_stream(z, d, (size_t)s3, f->lit + 2 * seg, (size_t)seg)) return -1;
        d += s3;
        if (huff_stream(z, d, (size_t)s4, f->lit + 3 * seg, (size_t)last)) return -1;
    }
    *n_out = regen;
    return hsz + csize;
}

static int seq_table(dec_t *z, const uint8_t *b, size_t blen, int mode, int which, int sym_limit, int log_limit, const char *name) {
    frame_t *f = z->f;
    switch (mode) {
    case 0:
        f->slot[which] = &f->def[which];
        return 0;
    case 1:
        if (blen < 1) return bad(z->x, "%s RLE symbol truncated", name);
        if (b[0] > sym_limit) return bad(z->x, "%s RLE symbol out of range", name);
        fse_rle(&f->own[which], b[0]);
        f->slot[which] = &f->own[which];
        return 1;
    case 2: {
        int max_sym, log;
        int n = read_counts(z->x, b, blen, sym_limit, log_limit, f->norm, &max_sym, &log);
        if (n < 0) return -1;
        if (fse_build(z->x, &f->own[which], f->norm, max_sym, log)) return -1;
        f->slot[which] = &f->own[which];
        return n;
    }
    default:
        if (!f->slot[which]) return bad(z->x, "%s table repeats the previous one, but this frame has none", name);
        return 0;
    }
}

// Compressed block: literals + sequences, decoded into dst[op..]; returns the byte count or -1.
static int64_t block(dec_t *z, const uint8_t *b, size_t blen, size_t op, size_t frame_start) {
    ctx_t *x = z->x;
    frame_t *f = z->f;
    int n_lit = 0;
    int used = literals(z, b, blen, &n_lit);
    if (used < 0) return -1;
    size_t p = (size_t)used;
    if (p >= blen) return bad(x, "compressed block has no sequences section");
    int n_seq = b[p++];
    if (n_seq >= 128) {
        if (n_seq < 255) {
            if (p >= blen) return bad(x, "sequence count truncated");
            n_seq = ((n_seq - 128) << 8) + b[p++];
        } else {
            if (blen - p < 2) return bad(x, "sequence count truncated");
            n_seq = b[p] + (b[p + 1] << 8) + 0x7F00;
            p += 2;
        }
    }
    size_t o = op;
    if (n_seq == 0) {
        if (p != blen) return bad(x, "block without sequences has trailing bytes");
        if (z->dst_len - o < (size_t)n_lit) return bad(x, "output exceeds the expected length");
        memcpy(z->dst + o, f->lit, (size_t)n_lit);
        return n_lit;
    }
    if (p >= blen) return bad(x, "sequence modes byte truncated");
    int modes = b[p++];
    if ((modes & 3) != 0) return bad(x, "sequence modes reserved bits not 0");
    int k;
    if ((k = seq_table(z, b + p, blen - p, (modes >> 6) & 3, T_LL, 35, 9, "literal length")) < 0) return -1;
    p += (size_t)k;
    if ((k = seq_table(z, b + p, blen - p, (modes >> 4) & 3, T_OF, 31, 8, "offset")) < 0) return -1;
    p += (size_t)k;
    if ((k = seq_table(z, b + p, blen - p, (modes >> 2) & 3, T_ML, 52, 9, "match length")) < 0) return -1;
    p += (size_t)k;
    const fse_t *ll = f->slot[T_LL], *of = f->slot[T_OF], *ml = f->slot[T_ML];
    bits_t br = {NULL, 0, 0};
    if (bits_init(x, &br, b + p, blen - p)) return -1;
    int sl = (int)bits_read(&br, ll->log), so = (int)bits_read(&br, of->log), sm = (int)bits_read(&br, ml->log);
    int li = 0;
    for (int i = 0; i < n_seq; i++) {
        int lc = ll->sym[sl], mc = ml->sym[sm], oc = of->sym[so];
        if (lc > 35 || mc > 52 || oc > 31) return bad(x, "sequence code out of range");
        int64_t ov = ((int64_t)1 << oc) + (int64_t)bits_read(&br, oc);
        int mlen = ML_BASE[mc] + (int)bits_read(&br, ML_BITS[mc]);
        int llen = LL_BASE[lc] + (int)bits_read(&br, LL_BITS[lc]);
        int64_t off;
        if (ov > 3) {
            off = ov - 3;
            f->r3 = f->r2;
            f->r2 = f->r1;
            f->r1 = (int32_t)(off < INT32_MAX ? off : INT32_MAX);
        } else {
            int idx = (int)ov - 1 + (llen == 0 ? 1 : 0);   // 0 = r1, 1 = r2, 2 = r3, 3 = r1 - 1
            if (idx == 0) off = f->r1;
            else {
                off = idx == 1 ? f->r2 : idx == 2 ? f->r3 : (int64_t)f->r1 - 1;
                if (idx != 1) f->r3 = f->r2;
                f->r2 = f->r1;
                f->r1 = (int32_t)off;
            }
        }
        if (i + 1 < n_seq) {   // state update order: literal length, match length, offset
            int nl = ll->base[sl] + (int)bits_read(&br, ll->nbits[sl]);
            int nm = ml->base[sm] + (int)bits_read(&br, ml->nbits[sm]);
            int no = of->base[so] + (int)bits_read(&br, of->nbits[so]);
            if (nl >= 1 << ll->log || nm >= 1 << ml->log || no >= 1 << of->log) return bad(x, "FSE state out of range");
            sl = nl;
            sm = nm;
            so = no;
        }
        if (llen > n_lit - li) return bad(x, "sequence needs more literals than the literals section holds");
        if ((int64_t)llen + mlen > (int64_t)(z->dst_len - o)) return bad(x, "output exceeds the expected length");
        memcpy(z->dst + o, f->lit + li, (size_t)llen);
        li += llen;
        o += (size_t)llen;
        if (off <= 0 || off > (int64_t)(o - frame_start)) return bad(x, "match offset %lld reaches before the frame start", (long long)off);
        size_t from = o - (size_t)off;
        for (int q = 0; q < mlen; q++) z->dst[o + (size_t)q] = z->dst[from + (size_t)q];   // forward copy (overlap repeats)
        o += (size_t)mlen;
    }
    if (br.pos != 0) return bad(x, "sequence bit stream not read exactly");
    int rest = n_lit - li;
    if (z->dst_len - o < (size_t)rest) return bad(x, "output exceeds the expected length");
    memcpy(z->dst + o, f->lit + li, (size_t)rest);
    o += (size_t)rest;
    return (int64_t)(o - op);
}

static void frame_reset(frame_t *f) {
    f->have_huffman = 0;
    f->hbits = 0;
    f->slot[0] = f->slot[1] = f->slot[2] = NULL;
    f->r1 = 1;
    f->r2 = 4;
    f->r3 = 8;
}

// One frame starting at src[*ip] (magic already checked), output from dst[start]; returns its size or -1.
static int64_t frame_run(dec_t *z, const uint8_t *src, size_t src_len, size_t *ip, size_t start) {
    ctx_t *x = z->x;
    frame_reset(z->f);
    size_t p = *ip + 4;
    if (p >= src_len) return bad(x, "frame header truncated");
    int fhd = src[p++];
    int fcs_flag = fhd >> 6, single = (fhd >> 5) & 1, check = (fhd >> 2) & 1, did_flag = fhd & 3;
    if ((fhd & 8) != 0) return bad(x, "frame header reserved bit not 0");
    int64_t window = 0;
    if (single == 0) {
        if (p >= src_len) return bad(x, "frame header truncated");
        int wd = src[p++], wlog = 10 + (wd >> 3);
        int64_t bsz = (int64_t)1 << wlog;
        window = bsz + (bsz >> 3) * (wd & 7);
    }
    static const int did_sizes[4] = {0, 1, 2, 4};
    size_t did_size = (size_t)did_sizes[did_flag];
    if (src_len - p < did_size) return bad(x, "frame header truncated");
    uint32_t did = 0;
    for (size_t k = 0; k < did_size; k++) did |= (uint32_t)src[p + k] << (8 * k);
    p += did_size;
    if (did != 0) return bad(x, "frame needs dictionary %u (ZBIC NSO segments carry none)", did);
    size_t fcs_size = fcs_flag == 0 ? (size_t)single : (size_t)1 << fcs_flag;
    if (src_len - p < fcs_size) return bad(x, "frame header truncated");
    int64_t fcs = -1;
    if (fcs_size > 0) {
        uint64_t v = 0;
        for (size_t k = 0; k < fcs_size; k++) v |= (uint64_t)src[p + k] << (8 * k);
        fcs = fcs_size == 2 ? (int64_t)v + 256 : (int64_t)v;   // 8 bytes above 2^63 wrap negative, as the C# cast does
        p += fcs_size;
    }
    if (single != 0) window = fcs;
    int64_t block_max = window < BLOCK_MAX ? window : BLOCK_MAX;
    size_t op = start;
    for (;;) {
        if (stop_requested(x)) return -1;   // between blocks: at most 128 KiB of output each
        if (src_len - p < 3) return bad(x, "block header truncated");
        int h = src[p] | src[p + 1] << 8 | src[p + 2] << 16;
        p += 3;
        int last = h & 1, type = (h >> 1) & 3, size = h >> 3;
        if (type == 3) return bad(x, "reserved block type 3");
        if (size > block_max) return bad(x, "block size %d above the limit %lld", size, (long long)block_max);
        if (type == 0) {
            if (src_len - p < (size_t)size) return bad(x, "raw block truncated");
            if (z->dst_len - op < (size_t)size) return bad(x, "output exceeds the expected length");
            memcpy(z->dst + op, src + p, (size_t)size);
            p += (size_t)size;
            op += (size_t)size;
        } else if (type == 1) {
            if (p >= src_len) return bad(x, "RLE block truncated");
            if (z->dst_len - op < (size_t)size) return bad(x, "output exceeds the expected length");
            memset(z->dst + op, src[p], (size_t)size);
            p += 1;
            op += (size_t)size;
        } else {
            if (src_len - p < (size_t)size) return bad(x, "compressed block truncated");
            int64_t got = block(z, src + p, (size_t)size, op, start);
            if (got < 0) return -1;
            if (got > block_max) return bad(x, "block decodes to more than the block limit");
            p += (size_t)size;
            op += (size_t)got;
        }
        if (last != 0) break;
    }
    if (fcs >= 0 && (int64_t)(op - start) != fcs)
        return bad(x, "frame decodes to %lld bytes, its header says %lld", (long long)(op - start), (long long)fcs);
    if (check != 0) {
        if (src_len - p < 4) return bad(x, "checksum truncated");
        uint32_t want = le32(src + p);
        p += 4;
        uint32_t got = (uint32_t)rb_s2arm_xxh64(z->dst + start, op - start);
        if (got != want) return bad(x, "frame checksum mismatch (XXH64 low 32 bits 0x%08x, frame 0x%08x)", got, want);
    }
    *ip = p;
    return (int64_t)(op - start);
}

static int decompress(ctx_t *x, const uint8_t *src, size_t src_len, uint8_t *dst, size_t expected) {
    if (src_len > RB_S2ARM_ZBIC_FILE_CAP || expected > RB_S2ARM_ZBIC_FILE_CAP) return bad(x, "data too large");
    frame_t *f = malloc(sizeof *f);
    if (!f) return bad(x, "out of memory");
    ctx_t quiet = *x;
    int ok = fse_build(&quiet, &f->def[T_LL], LL_DEF, 35, 6) == 0 && fse_build(&quiet, &f->def[T_ML], ML_DEF, 52, 6) == 0 &&
             fse_build(&quiet, &f->def[T_OF], OF_DEF, 28, 5) == 0;
    if (!ok) {
        free(f);
        return bad(x, "internal error: predefined tables");
    }
    dec_t z = {x, f, dst, expected};
    size_t ip = 0, op = 0;
    int frames = 0, result = 0;
    while (ip < src_len) {
        if (src_len - ip < 4) {
            result = bad(x, "%zu bytes left at offset 0x%zx, not enough for a frame magic", src_len - ip, ip);
            break;
        }
        uint32_t m = le32(src + ip);
        if (m == ZBIC_MAGIC) {
            int64_t got = frame_run(&z, src, src_len, &ip, op);
            if (got < 0) {
                result = -1;
                break;
            }
            op += (size_t)got;
            frames++;
        } else if ((m & 0xFFFFFFF0u) == 0x184D2A50u) {   // skippable frame (RFC 8878 3.1.2)
            if (src_len - ip < 8) {
                result = bad(x, "skippable frame header truncated");
                break;
            }
            uint64_t len = le32(src + ip + 4);
            if (len > src_len - ip - 8) {
                result = bad(x, "skippable frame runs past the data");
                break;
            }
            ip += 8 + (size_t)len;
        } else if (m == ZSTD_MAGIC) {
            result = bad(x, "offset 0x%zx is a standard zstd frame (magic 28 B5 2F FD), not ZBIC", ip);
            break;
        } else {
            result = bad(x, "offset 0x%zx: unknown frame magic 0x%08x (ZBIC is 5A 42 49 43)", ip, m);
            break;
        }
    }
    free(f);
    if (result) return -1;
    if (frames == 0) return bad(x, "no ZBIC frame");
    if (op != expected) return bad(x, "decoded 0x%zx bytes, expected 0x%zx", op, expected);
    return 0;
}

int rb_s2arm_zbic_decompress(const uint8_t *src, size_t src_len, uint8_t *dst, size_t expected, char *error, size_t error_size) {
    ctx_t x = {error, error_size, NULL, NULL, NULL};
    if ((!src && src_len) || (!dst && expected)) return bad(&x, "invalid arguments"), RB_S2ARM_ZBIC_INVALID;
    return decompress(&x, src, src_len, dst, expected) ? RB_S2ARM_ZBIC_INVALID : RB_S2ARM_ZBIC_OK;
}

// ---------------- XXH64 (seed 0) ----------------
#define P1 0x9E3779B185EBCA87ull
#define P2 0xC2B2AE3D27D4EB4Full
#define P3 0x165667B19E3779F9ull
#define P4 0x85EBCA77C2B2AE63ull
#define P5 0x27D4EB2F165667C5ull
static uint64_t rot64(uint64_t v, int r) { return (v << r) | (v >> (64 - r)); }
static uint64_t xround(uint64_t acc, uint64_t lane) { return rot64(acc + lane * P2, 31) * P1; }
static uint64_t xmerge(uint64_t h, uint64_t v) { return (h ^ xround(0, v)) * P1 + P4; }

uint64_t rb_s2arm_xxh64(const uint8_t *d, size_t n) {
    size_t i = 0;
    uint64_t h;
    if (n >= 32) {
        uint64_t v1 = P1 + P2, v2 = P2, v3 = 0, v4 = 0 - P1;
        for (; i + 32 <= n; i += 32) {
            v1 = xround(v1, le64(d + i));
            v2 = xround(v2, le64(d + i + 8));
            v3 = xround(v3, le64(d + i + 16));
            v4 = xround(v4, le64(d + i + 24));
        }
        h = rot64(v1, 1) + rot64(v2, 7) + rot64(v3, 12) + rot64(v4, 18);
        h = xmerge(h, v1);
        h = xmerge(h, v2);
        h = xmerge(h, v3);
        h = xmerge(h, v4);
    } else
        h = P5;
    h += (uint64_t)n;
    for (; i + 8 <= n; i += 8) h = rot64(h ^ xround(0, le64(d + i)), 27) * P1 + P4;
    if (i + 4 <= n) {
        h = rot64(h ^ ((uint64_t)le32(d + i) * P1), 23) * P2 + P3;
        i += 4;
    }
    for (; i < n; i++) h = rot64(h ^ (d[i] * P5), 11) * P1;
    h ^= h >> 33;
    h *= P2;
    h ^= h >> 29;
    h *= P3;
    h ^= h >> 32;
    return h;
}

// ---------------- SHA-256 (segment hashes) ----------------
typedef struct {
    uint32_t h[8];
    uint8_t buf[64];
    uint64_t total;
    size_t fill;
} sha_t;

static const uint32_t K256[64] = {
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be,
    0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa,
    0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967, 0x27b70a85,
    0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3,
    0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070, 0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f,
    0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2};

static uint32_t ror32(uint32_t v, int n) { return v >> n | v << (32 - n); }

static void sha_block(sha_t *s, const uint8_t *p) {
    uint32_t w[64];
    for (int i = 0; i < 16; i++) w[i] = (uint32_t)p[4 * i] << 24 | (uint32_t)p[4 * i + 1] << 16 | (uint32_t)p[4 * i + 2] << 8 | p[4 * i + 3];
    for (int i = 16; i < 64; i++) {
        uint32_t s0 = ror32(w[i - 15], 7) ^ ror32(w[i - 15], 18) ^ (w[i - 15] >> 3);
        uint32_t s1 = ror32(w[i - 2], 17) ^ ror32(w[i - 2], 19) ^ (w[i - 2] >> 10);
        w[i] = w[i - 16] + s0 + w[i - 7] + s1;
    }
    uint32_t a = s->h[0], b = s->h[1], c = s->h[2], d = s->h[3], e = s->h[4], f = s->h[5], g = s->h[6], h = s->h[7];
    for (int i = 0; i < 64; i++) {
        uint32_t t1 = h + (ror32(e, 6) ^ ror32(e, 11) ^ ror32(e, 25)) + ((e & f) ^ (~e & g)) + K256[i] + w[i];
        uint32_t t2 = (ror32(a, 2) ^ ror32(a, 13) ^ ror32(a, 22)) + ((a & b) ^ (a & c) ^ (b & c));
        h = g;
        g = f;
        f = e;
        e = d + t1;
        d = c;
        c = b;
        b = a;
        a = t1 + t2;
    }
    s->h[0] += a;
    s->h[1] += b;
    s->h[2] += c;
    s->h[3] += d;
    s->h[4] += e;
    s->h[5] += f;
    s->h[6] += g;
    s->h[7] += h;
}

static void sha_update(sha_t *s, const uint8_t *p, size_t n) {
    s->total += n;
    while (n) {
        size_t take = 64 - s->fill < n ? 64 - s->fill : n;
        memcpy(s->buf + s->fill, p, take);
        s->fill += take;
        p += take;
        n -= take;
        if (s->fill == 64) {
            sha_block(s, s->buf);
            s->fill = 0;
        }
    }
}

static void sha256(const uint8_t *data, size_t len, uint8_t out[32]) {
    sha_t s = {{0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19}, {0}, 0, 0};
    sha_update(&s, data, len);
    uint64_t bits = s.total * 8;
    uint8_t pad = 0x80;
    sha_update(&s, &pad, 1);
    pad = 0;
    while (s.fill != 56) sha_update(&s, &pad, 1);
    uint8_t lenbytes[8];
    for (int i = 0; i < 8; i++) lenbytes[i] = (uint8_t)(bits >> (56 - 8 * i));
    sha_update(&s, lenbytes, 8);
    for (int i = 0; i < 8; i++) {
        out[4 * i] = (uint8_t)(s.h[i] >> 24);
        out[4 * i + 1] = (uint8_t)(s.h[i] >> 16);
        out[4 * i + 2] = (uint8_t)(s.h[i] >> 8);
        out[4 * i + 3] = (uint8_t)s.h[i];
    }
}

// ---------------- NSO normalisation (NsoZbic.cs) ----------------
#define NSO_ZBIC 0x80u
#define NSO_BIT6 0x40u   // new on Switch 2, unrelated to segment decoding: kept
#define NSO_KNOWN (0x3Fu | NSO_BIT6 | NSO_ZBIC)
static const size_t SEG_HDR[3] = {0x10, 0x20, 0x30};

static size_t output_cap(const rb_s2arm_zbic_options *options) {
    size_t cap = options && options->max_output ? options->max_output : RB_S2ARM_ZBIC_DEFAULT_MAX_OUTPUT;
    return cap < RB_S2ARM_ZBIC_FILE_CAP ? cap : RB_S2ARM_ZBIC_FILE_CAP;
}

static int unknown_flags(ctx_t *x, const char *name, uint32_t flags) {
    return bad(x,
               "%s: NSO flags 0x%x have unknown bits 0x%x (known: LZ4 bits 0-2, hash bits 3-5, 0x40, ZBIC 0x80); compression "
               "unknown, not decoded",
               name, flags, flags & ~NSO_KNOWN);
}

int rb_s2arm_nso_normalize_ex(const uint8_t *v, size_t len, const char *name, const rb_s2arm_zbic_options *options, uint8_t **out,
                              size_t *out_len, char *error, size_t error_size) {
    int stopped = 0;
    ctx_t x = {error, error_size, NULL, options, &stopped};
    if (!out || !out_len || (!v && len)) return bad(&x, "invalid arguments"), RB_S2ARM_ZBIC_INVALID;
    *out = NULL;
    *out_len = 0;
    if (!name) name = "nso";
    if (len < 0x100 || memcmp(v, "NSO0", 4)) return RB_S2ARM_ZBIC_OK;
    if (len > RB_S2ARM_ZBIC_FILE_CAP) return bad(&x, "%s: file too large", name), RB_S2ARM_ZBIC_INVALID;
    uint32_t flags = le32(v + 0x0C);
    if (flags & ~NSO_KNOWN) return unknown_flags(&x, name, flags), RB_S2ARM_ZBIC_INVALID;
    if (!(flags & NSO_ZBIC)) return RB_S2ARM_ZBIC_OK;

    // Pass 1, nothing decoded or allocated yet: the checks the C# makes per segment that need no
    // decoding (bounds, negative or mismatched sizes), and the size of the result, which every
    // accepted input has exactly (a decoded segment must equal its declared size, an uncompressed
    // one its file size): header and module name up to the first segment, then the three segments.
    int32_t off[3], size[3], fsz[3];
    size_t first = len;
    uint64_t total = 0;
    for (int i = 0; i < 3; i++) {
        off[i] = (int32_t)le32(v + SEG_HDR[i]);
        size[i] = (int32_t)le32(v + SEG_HDR[i] + 8);
        fsz[i] = (int32_t)le32(v + 0x60 + 4 * i);
        if (off[i] < 0x100 || fsz[i] < 0 || (int64_t)off[i] + fsz[i] > (int64_t)len)
            return bad(&x, "%s: NSO segment %d runs past the file (offset 0x%x, size 0x%x, file 0x%zx)", name, i, (unsigned)off[i],
                       (unsigned)fsz[i], len),
                   RB_S2ARM_ZBIC_INVALID;
        if ((size_t)off[i] < first) first = (size_t)off[i];
        if ((flags >> i) & 1) {
            if (size[i] < 0)
                return bad(&x, "%s: NSO segment %d ZBIC data cannot be decoded (expected length is negative)", name, i), RB_S2ARM_ZBIC_INVALID;
            if ((size_t)size[i] > RB_S2ARM_ZBIC_SEGMENT_CAP)
                return bad(&x, "%s: NSO segment %d decompressed size 0x%x above the limit", name, i, (unsigned)size[i]), RB_S2ARM_ZBIC_INVALID;
            total += (uint64_t)size[i];
        } else {
            if (fsz[i] != size[i])
                return bad(&x, "%s: NSO segment %d is not compressed but its file size 0x%x differs from its size 0x%x", name, i,
                           (unsigned)fsz[i], (unsigned)size[i]),
                       RB_S2ARM_ZBIC_INVALID;
            total += (uint64_t)fsz[i];
        }
    }
    total += first;
    size_t cap = output_cap(options);
    if (total > cap)
        return bad(&x, "%s: the normalised NSO would be 0x%llx bytes, above the limit 0x%zx", name, (unsigned long long)total, cap),
               RB_S2ARM_ZBIC_INVALID;

    // Pass 2: one buffer of that size; each segment decoded (or copied) straight into its place.
    uint8_t *n = malloc(total ? (size_t)total : 1);
    if (!n) return bad(&x, "out of memory"), RB_S2ARM_ZBIC_IO;
    memcpy(n, v, first);
    size_t at = first;
    for (int i = 0; i < 3; i++) {
        size_t length = (flags >> i) & 1 ? (size_t)size[i] : (size_t)fsz[i];
        const uint8_t *raw = v + off[i];
        if (stop_requested(&x)) {
            free(n);
            return RB_S2ARM_ZBIC_CANCELLED;
        }
        if ((flags >> i) & 1) {
            char prefix[300];
            snprintf(prefix, sizeof prefix, "%s: NSO segment %d ZBIC data cannot be decoded (", name, i);
            ctx_t inner = {error, error_size, prefix, options, &stopped};
            if (decompress(&inner, raw, (size_t)fsz[i], n + at, length)) {
                free(n);
                if (stopped && error && error_size) snprintf(error, error_size, "cancelled");
                return stopped ? RB_S2ARM_ZBIC_CANCELLED : RB_S2ARM_ZBIC_INVALID;
            }
        } else
            memcpy(n + at, raw, length);
        if ((flags >> (3 + i)) & 1) {
            uint8_t digest[32];
            sha256(n + at, length, digest);
            if (memcmp(digest, v + 0xA0 + 0x20 * i, 32)) {
                free(n);
                return bad(&x, "%s: NSO segment %d SHA-256 after decoding differs from the header (file corrupt or modified)", name, i),
                       RB_S2ARM_ZBIC_INVALID;
            }
        }
        at += length;
    }
    // New layout: header + what lies between it and the first segment (module name) + the three segments back to back.
    at = first;
    for (int i = 0; i < 3; i++) {
        size_t length = (flags >> i) & 1 ? (size_t)size[i] : (size_t)fsz[i];
        put32(n + SEG_HDR[i], (uint32_t)at);
        put32(n + 0x60 + 4 * i, (uint32_t)length);
        at += length;
    }
    put32(n + 0x0C, flags & ~(NSO_ZBIC | 0x7u));
    *out = n;
    *out_len = (size_t)total;
    return RB_S2ARM_ZBIC_OK;
}

int rb_s2arm_nso_normalize(const uint8_t *v, size_t len, const char *name, uint8_t **out, size_t *out_len, char *error,
                           size_t error_size) {
    return rb_s2arm_nso_normalize_ex(v, len, name, NULL, out, out_len, error, error_size);
}

// Reads a whole open file of at most `cap` bytes into one exact allocation: 0, -1 read error /
// out of memory, -2 larger than cap (checked from its size before anything is allocated).
static int read_capped(FILE *f, size_t cap, uint8_t **data, size_t *len) {
    struct stat st;
    if (fstat(fileno(f), &st) || st.st_size < 0) return -1;
    if ((uint64_t)st.st_size > cap) return -2;
    size_t want = (size_t)st.st_size;
    uint8_t *buf = malloc(want + 1);
    if (!buf) return -1;
    if (fseek(f, 0, SEEK_SET)) {
        free(buf);
        return -1;
    }
    size_t n = 0, got;
    while (n <= want && (got = fread(buf + n, 1, want + 1 - n, f)) > 0) n += got;
    if (ferror(f) || n > want) {   // read error, or the file grew while being read
        int code = ferror(f) ? -1 : -2;
        free(buf);
        return code;
    }
    *data = buf;
    *len = n;
    return 0;
}

static int write_out(const char *path, const uint8_t *head, size_t head_len, FILE *rest, const uint8_t *bytes, size_t n) {
    FILE *f = fopen(path, "wb");
    if (!f) return -1;
    int bad_write = (head_len && fwrite(head, 1, head_len, f) != head_len) || (n && fwrite(bytes, 1, n, f) != n);
    if (rest && !bad_write) {   // stream the remainder of the input (copy without loading it)
        char block[1 << 16];
        size_t got;
        while ((got = fread(block, 1, sizeof block, rest)) > 0)
            if (fwrite(block, 1, got, f) != got) {
                bad_write = 1;
                break;
            }
        bad_write |= ferror(rest) != 0;
    }
    bad_write |= fclose(f) != 0;
    if (bad_write) remove(path);
    return bad_write ? -1 : 0;
}

int rb_s2arm_nso_normalize_file_ex(const char *in, const char *out, const rb_s2arm_zbic_options *options, char *error, size_t error_size) {
    ctx_t x = {error, error_size, NULL, options, NULL};
    if (!in || !out) return bad(&x, "invalid arguments"), RB_S2ARM_ZBIC_INVALID;
    const char *base = strrchr(in, '/');
    base = base ? base + 1 : in;
    FILE *f = fopen(in, "rb");
    if (!f) return bad(&x, "cannot read %s", in), RB_S2ARM_ZBIC_IO;
    uint8_t head[0x100];
    size_t got = fread(head, 1, sizeof head, f);
    if (ferror(f)) {
        fclose(f);
        return bad(&x, "cannot read %s", in), RB_S2ARM_ZBIC_IO;
    }
    int nso = got == sizeof head && !memcmp(head, "NSO0", 4);
    uint32_t flags = nso ? le32(head + 0x0C) : 0;
    if (nso && (flags & ~NSO_KNOWN)) {
        fclose(f);
        return unknown_flags(&x, base, flags), RB_S2ARM_ZBIC_INVALID;
    }
    if (!nso || !(flags & NSO_ZBIC)) {   // nothing to normalise: the same bytes, streamed
        int r = write_out(out, head, got, f, NULL, 0);
        fclose(f);
        return r ? (bad(&x, "cannot write %s", out), RB_S2ARM_ZBIC_IO) : RB_S2ARM_ZBIC_OK;
    }
    // A ZBIC NSO is read whole, as the original does, but never above the output cap.
    size_t cap = output_cap(options);
    uint8_t *data = NULL;
    size_t len = 0;
    int r = read_capped(f, cap, &data, &len);
    fclose(f);
    if (r == -2) return bad(&x, "%s: the ZBIC NSO file is above the limit 0x%zx", base, cap), RB_S2ARM_ZBIC_INVALID;
    if (r) return bad(&x, "cannot read %s", in), RB_S2ARM_ZBIC_IO;
    uint8_t *result = NULL;
    size_t rlen = 0;
    int code = rb_s2arm_nso_normalize_ex(data, len, base, options, &result, &rlen, error, error_size);
    free(data);
    if (code == RB_S2ARM_ZBIC_OK && write_out(out, NULL, 0, NULL, result, rlen)) {
        bad(&x, "cannot write %s", out);
        code = RB_S2ARM_ZBIC_IO;
    }
    free(result);
    return code;
}

int rb_s2arm_nso_normalize_file(const char *in, const char *out, char *error, size_t error_size) {
    return rb_s2arm_nso_normalize_file_ex(in, out, NULL, error, error_size);
}
