// Port of S2Arm tools/addr_need.py (Apache-2.0, pinned commit in tools/s2arm_prototype/pin.json).
// Function names in comments refer to the original. The original relies on Python exceptions
// (struct.error, IndexError, ValueError) for every out-of-range read; each such place is an explicit
// check here and ends in RB_S2ARM_ADDR_INVALID. Sets and dicts of the original are replaced by
// sorted arrays so that no iteration order can influence the result.
#include "s2arm_addr_need.h"
#include "lz4.h"

#include <errno.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>

#define GIB ((uint64_t)1 << 30)
#define ALIAS_MAX_GB 63
#define APP_POOL_MB 3284
#define SDK_META ((uint64_t)0x3FE00000)
#define IMAGE_CAP ((uint64_t)1 << 30)   // refuse images above 1 GiB (the original would need that much RAM too)
#define TRACE_BUDGET 4000

enum { N_ADDRESS_REGION = 0, N_NLIB_VIRTUAL = 1, N_CLAIMS = 8, N_COMMIT = 8, N_ALL = 9 };
static const char *const k_names[N_ALL] = {
    "_ZN2nn2os21AllocateAddressRegionEPmm",
    "nnmem_nlib_virtual_alloc",
    "_ZN2nn3mem17StandardAllocator10InitializeEPvm",
    "_ZN2nn3mem17StandardAllocator10InitializeEPvmb",
    "_ZN2nn3mem17StandardAllocatorC1EPvm",
    "_ZN2nn3mem17StandardAllocatorC1EPvmb",
    "_ZN2nn3mem17StandardAllocatorC2EPvm",
    "_ZN2nn3mem17StandardAllocatorC2EPvmb",
    "_ZN2nn2os19AllocateMemoryPagesEmm",
};

typedef struct {
    char *error;
    size_t error_size;
} ctx_t;

#if defined(__GNUC__)
__attribute__((format(printf, 3, 4)))
#endif
static int fail(ctx_t *x, int code, const char *fmt, ...) {
    if (x->error && x->error_size) {
        va_list ap;
        va_start(ap, fmt);
        vsnprintf(x->error, x->error_size, fmt, ap);
        va_end(ap);
    }
    return code;
}

// ---------- growable vectors ----------

static int vec_reserve(void **p, size_t *cap, size_t need, size_t esz) {
    if (need <= *cap) return 1;
    size_t ncap = *cap ? *cap : 16;
    while (ncap < need) {
        if (ncap > ((size_t)1 << 40)) return 0;
        ncap *= 2;
    }
    void *np = realloc(*p, ncap * esz);
    if (!np) return 0;
    *p = np;
    *cap = ncap;
    return 1;
}

typedef struct {
    char *p;
    size_t n, cap;
    int oom;
} sbuf_t;

static void sb_add(sbuf_t *s, const char *t, size_t len) {
    if (s->oom) return;
    if (!vec_reserve((void **)&s->p, &s->cap, s->n + len + 1, 1)) {
        s->oom = 1;
        return;
    }
    memcpy(s->p + s->n, t, len);
    s->n += len;
    s->p[s->n] = 0;
}
static void sb_str(sbuf_t *s, const char *t) { sb_add(s, t, strlen(t)); }

// ---------- bounds-checked reads (struct.unpack_from semantics, negative offsets count from the end) ----------

static int rd_pos(size_t len, int64_t off, size_t size, size_t *pos) {
    int64_t l = (int64_t)len;
    if (off < 0) {
        if (off + (int64_t)size > 0) return 0;
        off += l;
        if (off < 0) return 0;
    } else if (off > l || (int64_t)size > l - off) {
        return 0;
    }
    *pos = (size_t)off;
    return 1;
}
static uint32_t le32(const uint8_t *p) { return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24; }
static uint64_t le64(const uint8_t *p) { return (uint64_t)le32(p) | (uint64_t)le32(p + 4) << 32; }
static int rd32(const uint8_t *b, size_t len, int64_t off, uint32_t *v) {
    size_t pos;
    if (!rd_pos(len, off, 4, &pos)) return 0;
    *v = le32(b + pos);
    return 1;
}
// Clamp an unsigned 64-bit value from the file to an offset that can never be valid but does not overflow.
static int64_t off_u64(uint64_t v) { return v > ((uint64_t)1 << 60) ? ((int64_t)1 << 60) : (int64_t)v; }

static int read_file(ctx_t *x, const char *path, uint8_t **data, size_t *len) {
    FILE *f = fopen(path, "rb");
    if (!f) return fail(x, RB_S2ARM_ADDR_IO, "cannot open %s: %s", path, strerror(errno));
    uint8_t *buf = NULL;
    size_t n = 0, cap = 0;
    for (;;) {
        if (!vec_reserve((void **)&buf, &cap, n + 65536 + 1, 1)) {
            free(buf);
            fclose(f);
            return fail(x, RB_S2ARM_ADDR_IO, "out of memory reading %s", path);
        }
        size_t got = fread(buf + n, 1, 65536, f);
        n += got;
        if (n > IMAGE_CAP) {
            free(buf);
            fclose(f);
            return fail(x, RB_S2ARM_ADDR_INVALID, "%s is larger than 1 GiB", path);
        }
        if (got < 65536) break;
    }
    int bad = ferror(f);
    fclose(f);
    if (bad) {
        free(buf);
        return fail(x, RB_S2ARM_ADDR_IO, "cannot read %s", path);
    }
    *data = buf;
    *len = n;
    return 0;
}

// ---------- npdm_program / npdm_system_resource ----------

static int npdm_info(ctx_t *x, const uint8_t *d, size_t len, char program[17], int *vamm) {
    if (len < 0x78 || memcmp(d, "META", 4)) return fail(x, RB_S2ARM_ADDR_INVALID, "not an NPDM (no META header)");
    uint64_t offset = le32(d + 0x70);
    if (offset + 0x18 > len || memcmp(d + offset, "ACI0", 4)) return fail(x, RB_S2ARM_ADDR_INVALID, "ACI0 the META header points at is missing (offset %#llx)", (unsigned long long)offset);
    snprintf(program, 17, "%016llx", (unsigned long long)le64(d + offset + 0x10));
    *vamm = le32(d + 0x14) > 0;
    return 0;
}

// ---------- _nso_image ----------

typedef struct {
    uint8_t *image;
    size_t ilen, icap;
    uint32_t seg_mem[3], seg_size[3];
} nso_t;

static int nso_image(ctx_t *x, const uint8_t *raw, size_t rawlen, nso_t *out) {
    uint32_t flags;
    if (rawlen < 4 || memcmp(raw, "NSO0", 4)) return fail(x, RB_S2ARM_ADDR_INVALID, "not an NSO");
    if (rawlen >= 0x10 && (le32(raw + 0xC) & 0x80))
        return fail(x, RB_S2ARM_ADDR_UNSUPPORTED, "ZBIC-compressed NSO (flag 0x80): normalise it first (rb_s2arm_nso_normalize; rb_s2arm_prepare_code does)");
    if (!rd32(raw, rawlen, 0xC, &flags)) return fail(x, RB_S2ARM_ADDR_INVALID, "NSO header too short");
    static const int headers[3] = {0x10, 0x20, 0x30}, csizes[3] = {0x60, 0x64, 0x68};
    for (int k = 0; k < 3; k++) {
        uint32_t offset, memory, size, csize;
        if (!rd32(raw, rawlen, headers[k], &offset) || !rd32(raw, rawlen, headers[k] + 4, &memory) || !rd32(raw, rawlen, headers[k] + 8, &size) ||
            !rd32(raw, rawlen, csizes[k], &csize))
            return fail(x, RB_S2ARM_ADDR_INVALID, "NSO segment header out of range");
        const uint8_t *data = raw;
        size_t dlen = 0;
        if (offset < rawlen) {   // Python slice raw[offset:offset+csize] clamps to the file
            data = raw + offset;
            dlen = rawlen - offset < csize ? rawlen - offset : csize;
        }
        uint8_t *plain = NULL;
        if (flags & (1u << k)) {
            if (size > IMAGE_CAP) return fail(x, RB_S2ARM_ADDR_INVALID, "NSO segment %d too large", k);
            plain = malloc(size ? size : 1);
            if (!plain) return fail(x, RB_S2ARM_ADDR_IO, "out of memory");
            int got = LZ4_decompress_safe((const char *)data, (char *)plain, (int)dlen, (int)size);
            if (got < 0) {
                free(plain);
                return fail(x, RB_S2ARM_ADDR_INVALID, "NSO segment %d: LZ4 data is corrupt", k);
            }
            data = plain;
            dlen = (size_t)got;
        }
        // image[memory:memory+size] = data, after extending the image to memory+size.
        uint64_t end = (uint64_t)memory + size;
        uint64_t need = end > out->ilen ? end : out->ilen;
        uint64_t newlen = need - size + dlen;
        uint64_t cap_need = need > newlen ? need : newlen;
        if (cap_need > IMAGE_CAP) {
            free(plain);
            return fail(x, RB_S2ARM_ADDR_INVALID, "NSO image larger than 1 GiB");
        }
        if (!vec_reserve((void **)&out->image, &out->icap, (size_t)cap_need + 1, 1)) {
            free(plain);
            return fail(x, RB_S2ARM_ADDR_IO, "out of memory");
        }
        if (need > out->ilen) memset(out->image + out->ilen, 0, (size_t)need - out->ilen);
        out->ilen = (size_t)need;
        if (dlen != size) memmove(out->image + memory + dlen, out->image + end, out->ilen - (size_t)end);
        if (dlen) memcpy(out->image + memory, data, dlen);
        out->ilen = (size_t)newlen;
        free(plain);
        out->seg_mem[k] = memory;
        out->seg_size[k] = size;
    }
    return 0;
}

// ---------- _Code ----------

typedef struct {
    const uint8_t *image;
    size_t ilen;
    int64_t lo;
    uint32_t text_size;
    uint32_t *words;
    size_t nwords;
    uint32_t *cstart;   // CSR over word index of the branch target: callers of lo+4*t are csites[cstart[t]..cstart[t+1])
    uint32_t *csites;   // word indexes of the B / BL instructions, ascending per target
} code_t;

static void code_free(code_t *c) {
    free(c->words);
    free(c->cstart);
    free(c->csites);
    memset(c, 0, sizeof *c);
}

static int code_init(ctx_t *x, code_t *c, const nso_t *nso) {
    memset(c, 0, sizeof *c);
    c->image = nso->image;
    c->ilen = nso->ilen;
    c->lo = nso->seg_mem[0];
    c->text_size = nso->seg_size[0];
    size_t n = c->text_size / 4;
    // struct.unpack_from("<%dI", image, lo)
    if ((uint64_t)c->lo + 4 * (uint64_t)n > c->ilen) return fail(x, RB_S2ARM_ADDR_INVALID, "text segment does not fit the NSO image");
    c->nwords = n;
    c->words = malloc((n ? n : 1) * sizeof(uint32_t));
    c->cstart = calloc(n + 2, sizeof(uint32_t));
    if (!c->words || !c->cstart) {
        code_free(c);
        return fail(x, RB_S2ARM_ADDR_IO, "out of memory");
    }
    for (size_t i = 0; i < n; i++) c->words[i] = le32(c->image + c->lo + 4 * i);
    size_t total = 0;
    for (size_t i = 0; i < n; i++) {
        uint32_t w = c->words[i];
        if ((w & 0x7C000000) == 0x14000000) {
            int64_t off = w & 0x3FFFFFF;
            if (off & (1 << 25)) off -= (int64_t)1 << 26;
            int64_t t = (int64_t)i + off;
            if (t >= 0 && t < (int64_t)n) {   // targets outside the text are never looked up
                c->cstart[t + 1]++;
                total++;
            }
        }
    }
    for (size_t t = 0; t < n; t++) c->cstart[t + 1] += c->cstart[t];
    c->csites = malloc((total ? total : 1) * sizeof(uint32_t));
    uint32_t *cursor = malloc((n ? n : 1) * sizeof(uint32_t));
    if (!c->csites || !cursor) {
        free(cursor);
        code_free(c);
        return fail(x, RB_S2ARM_ADDR_IO, "out of memory");
    }
    if (n) memcpy(cursor, c->cstart, n * sizeof(uint32_t));
    for (size_t i = 0; i < n; i++) {
        uint32_t w = c->words[i];
        if ((w & 0x7C000000) == 0x14000000) {
            int64_t off = w & 0x3FFFFFF;
            if (off & (1 << 25)) off -= (int64_t)1 << 26;
            int64_t t = (int64_t)i + off;
            if (t >= 0 && t < (int64_t)n) c->csites[cursor[t]++] = (uint32_t)i;
        }
    }
    free(cursor);
    return 0;
}

// callers.get(address, ()): word indexes of the B / BL instructions that target the address, ascending.
static size_t callers_of(const code_t *c, int64_t address, const uint32_t **sites) {
    int64_t d = address - c->lo;
    if (d < 0 || d % 4 || d / 4 >= (int64_t)c->nwords) return 0;
    size_t t = (size_t)(d / 4);
    *sites = c->csites + c->cstart[t];
    return c->cstart[t + 1] - c->cstart[t];
}

// word_at: Python floor division and negative list indexes; IndexError becomes INVALID.
static int word_at(ctx_t *x, const code_t *c, int64_t address, uint32_t *w) {
    int64_t d = address - c->lo;
    int64_t idx = d >= 0 ? d / 4 : -((-d + 3) / 4);
    if (idx < 0) idx += (int64_t)c->nwords;
    if (idx < 0 || idx >= (int64_t)c->nwords) return fail(x, RB_S2ARM_ADDR_INVALID, "code address %#llx is outside the text segment", (unsigned long long)address);
    *w = c->words[idx];
    return 0;
}

static int boundary_word(uint32_t w) { return w == 0xD65F03C0 || w == 0xD503201F || w == 0 || (w & 0xFC000000) == 0x14000000; }
static int branch_word(uint32_t w) {
    return (w & 0x7C000000) == 0x14000000 || (w & 0x7E000000) == 0x34000000 || (w & 0x7E000000) == 0x36000000 || (w & 0xFF000010) == 0x54000000 ||
           (w & 0xFE1FFC1F) == 0xD61F0000;
}

// function_start: *found = 0 is Python None.
static int function_start(ctx_t *x, const code_t *c, int64_t address, int64_t *out, int *found) {
    uint32_t w, before;
    *found = 1;
    int st = word_at(x, c, address, &w);
    if (st) return st;
    if ((w & 0xFC000000) == 0x14000000) {
        for (int k = 0; k < 4; k++) {
            int64_t at = address - 4 * k;
            if (at <= c->lo) break;
            if ((st = word_at(x, c, at - 4, &before))) return st;
            if (boundary_word(before)) {
                *out = at;
                return 0;
            }
            if (branch_word(before)) break;
        }
    }
    for (int k = 1; k < 4096; k++) {
        int64_t at = address - 4 * (int64_t)k;
        if (at <= c->lo) {
            *out = c->lo;
            return 0;
        }
        if ((st = word_at(x, c, at, &w)) || (st = word_at(x, c, at - 4, &before))) return st;
        int prologue = ((w & 0xFFC003E0) == 0xA98003E0 && (w & (1u << 21))) || ((w & 0xFFE00FE0) == 0xF8000FE0 && (w & (1u << 20))) ||
                       (w & 0xFF0003FF) == 0xD10003FF;
        if (prologue && boundary_word(before)) {
            *out = at;
            return 0;
        }
    }
    *found = 0;
    return 0;
}

// ---------- _import_stub_names ----------

typedef struct {
    int64_t addr;
    int name;
} stub_t;
typedef struct {
    uint64_t offset;
    size_t seq;
    int name;
} slot_t;

static int slot_cmp(const void *a, const void *b) {
    const slot_t *p = a, *q = b;
    if (p->offset != q->offset) return p->offset < q->offset ? -1 : 1;
    return p->seq < q->seq ? -1 : p->seq > q->seq;
}

// Returns stubs ascending by address (the original sorts them or only builds a set from them).
static int import_stub_names(ctx_t *x, const code_t *c, int nnames, stub_t **out, size_t *count) {
    const uint8_t *img = c->image;
    size_t len = c->ilen;
    *out = NULL;
    *count = 0;
    uint32_t mod0, dynoff;
    if (!rd32(img, len, 4, &mod0)) return fail(x, RB_S2ARM_ADDR_INVALID, "NSO image too short for MOD0 offset");
    if (!rd32(img, len, (int64_t)mod0 + 4, &dynoff)) return fail(x, RB_S2ARM_ADDR_INVALID, "MOD0 header out of range");
    int64_t dynamic = (int64_t)mod0 + (int32_t)dynoff;
    uint64_t tag_value[24] = {0};
    int has[24] = {0};
    for (;;) {
        size_t pos;
        if (!rd_pos(len, dynamic, 16, &pos)) return fail(x, RB_S2ARM_ADDR_INVALID, "dynamic section out of range");
        int64_t tag = (int64_t)le64(img + pos);
        uint64_t value = le64(img + pos + 8);
        dynamic += 16;
        if (tag == 0) break;
        if ((tag == 2 || tag == 5 || tag == 6 || tag == 7 || tag == 8 || tag == 23) && !has[tag]) {   // setdefault: first one wins
            has[tag] = 1;
            tag_value[tag] = value;
        }
    }
    if (!has[5] || !has[6]) return 0;
    slot_t *slots = NULL;
    size_t nslots = 0, cslots = 0;
    uint64_t bases[2] = {has[23] ? tag_value[23] : 0, has[7] ? tag_value[7] : 0};
    uint64_t sizes[2] = {has[2] ? tag_value[2] : 0, has[8] ? tag_value[8] : 0};
    int st = 0;
    for (int g = 0; g < 2 && !st; g++) {
        uint64_t count_r = bases[g] ? sizes[g] / 24 : 0;
        for (uint64_t k = 0; k < count_r; k++) {
            size_t pos, spos;
            if (!rd_pos(len, off_u64(bases[g]) + (int64_t)(k * 24 > ((uint64_t)1 << 60) ? ((uint64_t)1 << 60) : k * 24), 24, &pos)) {
                st = fail(x, RB_S2ARM_ADDR_INVALID, "relocation table out of range");
                break;
            }
            uint64_t offset = le64(img + pos), info = le64(img + pos + 8);
            if (!(info >> 32)) continue;
            if (!rd_pos(len, off_u64(tag_value[6]) + (int64_t)((info >> 32) * 24), 4, &spos)) {
                st = fail(x, RB_S2ARM_ADDR_INVALID, "symbol table out of range");
                break;
            }
            uint64_t at = tag_value[5] + le32(img + spos);
            if (tag_value[5] > len || at >= len) {
                st = fail(x, RB_S2ARM_ADDR_INVALID, "symbol name out of range");
                break;
            }
            const uint8_t *nul = memchr(img + at, 0, len - (size_t)at);
            if (!nul) {
                st = fail(x, RB_S2ARM_ADDR_INVALID, "symbol name not terminated");
                break;
            }
            size_t slen = (size_t)(nul - (img + at));
            for (int n = 0; n < nnames; n++) {
                if (strlen(k_names[n]) == slen && !memcmp(k_names[n], img + at, slen)) {
                    if (!vec_reserve((void **)&slots, &cslots, nslots + 1, sizeof *slots)) {
                        st = fail(x, RB_S2ARM_ADDR_IO, "out of memory");
                        break;
                    }
                    slots[nslots].offset = offset;
                    slots[nslots].seq = nslots;
                    slots[nslots].name = n;
                    nslots++;
                    break;
                }
            }
            if (st) break;
        }
    }
    if (st) {
        free(slots);
        return st;
    }
    if (nslots > 1) qsort(slots, nslots, sizeof *slots, slot_cmp);
    // dict semantics: the last entry per offset wins (it sorts last among equal offsets)
    size_t uniq = 0;
    for (size_t i = 0; i < nslots; i++) {
        if (i + 1 < nslots && slots[i + 1].offset == slots[i].offset) continue;
        slots[uniq++] = slots[i];
    }
    stub_t *stubs = NULL;
    size_t nstubs = 0, cstubs = 0;
    int64_t lo = c->lo;
    int64_t limit = lo + (int64_t)c->text_size - 8;
    for (int64_t a = lo; a < limit; a += 4) {
        size_t pos;
        if (!rd_pos(len, a, 8, &pos)) {
            st = fail(x, RB_S2ARM_ADDR_INVALID, "code scan out of range");
            break;
        }
        uint32_t w0 = le32(img + pos), w1 = le32(img + pos + 4);
        if ((w0 & 0x9F00001F) == 0x90000010 && (w1 & 0xFFC003FF) == 0xF9400211) {
            int64_t imm = (int64_t)((((w0 >> 5) & 0x7FFFF) << 2) | ((w0 >> 29) & 3));
            if (imm & (1 << 20)) imm -= (int64_t)1 << 21;
            int64_t slot = (a & ~(int64_t)0xFFF) + imm * 4096 + (int64_t)((w1 >> 10) & 0xFFF) * 8;
            if (slot < 0) continue;
            size_t lo_i = 0, hi_i = uniq;
            while (lo_i < hi_i) {
                size_t mid = (lo_i + hi_i) / 2;
                if (slots[mid].offset < (uint64_t)slot) lo_i = mid + 1; else hi_i = mid;
            }
            if (lo_i < uniq && slots[lo_i].offset == (uint64_t)slot) {
                if (!vec_reserve((void **)&stubs, &cstubs, nstubs + 1, sizeof *stubs)) {
                    st = fail(x, RB_S2ARM_ADDR_IO, "out of memory");
                    break;
                }
                stubs[nstubs].addr = a;
                stubs[nstubs].name = slots[lo_i].name;
                nstubs++;
            }
        }
    }
    free(slots);
    if (st) {
        free(stubs);
        return st;
    }
    *out = stubs;
    *count = nstubs;
    return 0;
}

// ---------- _bitmask / _move_immediate / _register_constants ----------

static int bit_length(uint32_t v) {
    int n = 0;
    while (v) {
        n++;
        v >>= 1;
    }
    return n;
}

static int bitmask(unsigned n, unsigned immr, unsigned imms, uint64_t *out) {
    int length = bit_length((n << 6) | (~imms & 0x3F)) - 1;
    if (length < 1) return 0;
    unsigned size = 1u << length;
    unsigned s = imms & (size - 1), r = immr & (size - 1);
    if (s == size - 1) return 0;
    uint64_t element = ((uint64_t)1 << (s + 1)) - 1;
    uint64_t mask = size == 64 ? ~(uint64_t)0 : (((uint64_t)1 << size) - 1);
    if (r) element = ((element >> r) | (element << (size - r))) & mask;
    uint64_t result = 0;
    for (unsigned i = 0; i < 64 / size; i++) result |= element << (i * size);
    *out = result;
    return 1;
}

static int move_immediate(uint32_t w, uint64_t *out) {
    if ((w & 0xFF800000) == 0xD2800000) {
        *out = (uint64_t)((w >> 5) & 0xFFFF) << (16 * ((w >> 21) & 3));
        return 1;
    }
    if ((w & 0xFF8003E0) == 0xB20003E0) return bitmask((w >> 22) & 1, (w >> 16) & 0x3F, (w >> 10) & 0x3F, out);
    return 0;
}

// ---------- static_alias_gb ----------

static int u64_cmp(const void *a, const void *b) {
    int64_t p = *(const int64_t *)a, q = *(const int64_t *)b;
    return p < q ? -1 : p > q;
}

static int static_alias_gb(ctx_t *x, const code_t *c, int *alias) {
    const int depth = 6, window = 16, wrapper_max = 96;
    stub_t *stubs = NULL;
    size_t nstubs = 0;
    int st = import_stub_names(x, c, N_CLAIMS, &stubs, &nstubs);
    if (st) return st;
    int64_t *members = malloc((nstubs ? nstubs : 1) * sizeof(int64_t));
    uint8_t *seen = calloc(c->nwords / 8 + 1, 1);
    int64_t *wrappers = NULL;
    size_t nwrappers = 0, cwrappers = 0, nmembers = nstubs;
    uint64_t largest = 0;
    if (!members || !seen) {
        st = fail(x, RB_S2ARM_ADDR_IO, "out of memory");
        goto done;
    }
    for (size_t i = 0; i < nstubs; i++) members[i] = stubs[i].addr;
    for (int level = 0; level < depth && !st; level++) {
        nwrappers = 0;
        for (size_t m = 0; m < nmembers && !st; m++) {
            const uint32_t *sites;
            size_t ns = callers_of(c, members[m], &sites);
            for (size_t s = 0; s < ns && !st; s++) {
                uint32_t idx = sites[s];
                if (seen[idx >> 3] & (1u << (idx & 7))) continue;
                seen[idx >> 3] |= (uint8_t)(1u << (idx & 7));
                int64_t site = c->lo + 4 * (int64_t)idx;
                uint32_t rev[16];   // rev[j] = word at site - 4*(j+1)
                int cnt = 0;
                for (int k = 1; k <= window; k++) {
                    uint32_t w;
                    if ((st = word_at(x, c, site - 4 * (int64_t)k, &w))) break;
                    if ((w & 0x7C000000) == 0x14000000 || w == 0xD65F03C0) break;
                    rev[cnt++] = w;
                }
                if (st) break;
                // _register_constants over the block in address order; max of the claim-sized values
                uint64_t known[32], found = 0;
                uint32_t known_mask = 0;
                for (int j = cnt - 1; j >= 0; j--) {
                    uint32_t w = rev[j];
                    unsigned reg = w & 0x1F;
                    uint64_t value = 0;
                    int has_value = move_immediate(w, &value);
                    if (!has_value && (w & 0xFF800000) == 0xF2800000 && (known_mask >> reg & 1)) {
                        unsigned shift = 16 * ((w >> 21) & 3);
                        value = (known[reg] & ~((uint64_t)0xFFFF << shift)) | (uint64_t)((w >> 5) & 0xFFFF) << shift;
                        has_value = 1;
                    }
                    if (!has_value) {
                        known_mask &= ~(1u << reg);
                    } else {
                        known[reg] = value;
                        known_mask |= 1u << reg;
                        if (value >= 4 * GIB && value % GIB == 0 && value < ((uint64_t)1 << 39) && value > found) found = value;
                    }
                }
                if (found) {
                    if (found > largest) largest = found;
                    continue;
                }
                int64_t start;
                int has_start;
                if ((st = function_start(x, c, site, &start, &has_start))) break;
                if (has_start && (site - start) / 4 <= wrapper_max) {
                    if (!vec_reserve((void **)&wrappers, &cwrappers, nwrappers + 1, sizeof(int64_t))) {
                        st = fail(x, RB_S2ARM_ADDR_IO, "out of memory");
                        break;
                    }
                    wrappers[nwrappers++] = start;
                }
            }
        }
        if (st) break;
        // members = set(wrappers)
        if (nwrappers) qsort(wrappers, nwrappers, sizeof(int64_t), u64_cmp);
        size_t uniq = 0;
        for (size_t i = 0; i < nwrappers; i++)
            if (!i || wrappers[i] != wrappers[i - 1]) wrappers[uniq++] = wrappers[i];
        if (uniq > nstubs) {
            int64_t *nm = realloc(members, uniq * sizeof(int64_t));
            if (!nm) {
                st = fail(x, RB_S2ARM_ADDR_IO, "out of memory");
                break;
            }
            members = nm;
        }
        if (uniq) memcpy(members, wrappers, uniq * sizeof(int64_t));
        nmembers = uniq;
        if (!nmembers) break;
    }
    if (!st) {
        uint64_t gb = (largest + SDK_META + GIB - 1) / GIB;
        *alias = largest ? (int)(gb < ALIAS_MAX_GB ? gb : ALIAS_MAX_GB) : 0;
    }
done:
    free(stubs);
    free(members);
    free(seen);
    free(wrappers);
    return st;
}

// ---------- _gpr_writes / _source_kind / _trace ----------

static uint32_t only1(unsigned r) { return r != 31 ? 1u << r : 0; }

// Returns 0 for None (unrecognised), else 1 with the register set in *writes.
static int gpr_writes(uint32_t w, uint32_t *writes) {
    unsigned rd = w & 31, rn = (w >> 5) & 31, rt2 = (w >> 10) & 31;
    if ((w & 0x1C000000) == 0x14000000) {
        if ((w & 0xFC000000) == 0x94000000 || (w & 0xFFFFFC1F) == 0xD63F0000) *writes = 1u << 30;
        else if ((w & 0xFFF00000) == 0xD5300000) *writes = only1(rd);
        else *writes = 0;
        return 1;
    }
    if ((w & 0x1C000000) == 0x10000000) { *writes = only1(rd); return 1; }
    if ((w & 0x0E000000) == 0x0A000000) { *writes = only1(rd); return 1; }
    if ((w & 0x0A000000) == 0x08000000) {
        int vector = (w & (1u << 26)) != 0;
        if ((w & 0x3B000000) == 0x18000000) { *writes = vector ? 0 : only1(rd); return 1; }
        if ((w & 0x3A000000) == 0x28000000) {
            uint32_t r = ((w >> 23) & 1) ? only1(rn) : 0;
            if (((w >> 22) & 1) && !vector) r |= only1(rd) | only1(rt2);
            *writes = r;
            return 1;
        }
        if ((w & 0x3B000000) == 0x39000000 || (w & 0x3B200000) == 0x38000000 || (w & 0x3B200C00) == 0x38200800) {
            uint32_t r = ((w & 0x3B200000) == 0x38000000 && ((w >> 10) & 1)) ? only1(rn) : 0;
            unsigned opc = (w >> 22) & 3, sz = w >> 30;
            if (opc && !vector && !(sz == 3 && opc == 2)) r |= only1(rd);
            *writes = r;
            return 1;
        }
        if ((w & 0x3F000000) == 0x08000000) { *writes = ((w >> 22) & 1) ? only1(rd) : only1((w >> 16) & 31); return 1; }
        if ((w & 0x3B200C00) == 0x38200000) { *writes = only1(rd); return 1; }
        return 0;
    }
    if ((w & 0x7F3FFC00) == 0x1E260000 ||   /* the original's second value 0x9E660000 can never match under that mask */ (w & 0xBFE0FC00) == 0x0E003C00) { *writes = only1(rd); return 1; }
    if ((w & 0x0E000000) == 0x0E000000 || (w & 0x0E000000) == 0x0C000000) { *writes = 0; return 1; }
    return 0;
}

enum { K_UNKNOWN, K_COMPUTE, K_LOAD, K_CONST, K_REGISTER };
enum { M_NONE, M_BUDGET, M_NONARG, M_DEEP, M_INDIRECT, M_PASTTEXT, M_JOIN, M_UNKNOWN_INSN, M_CALLRET, M_VOLATILE, M_MOVK_REG, M_MOVK_NONCONST, M_BITMASK, M_LOAD, M_RUNTIME };
static const char *const k_kind_text[4] = {"不明", "计算", "读内存", "常量"};
static const char *const k_msg_text[] = {
    "",
    "追踪步数用完",
    "",   // M_NONARG is formatted with the register number
    "调用链过深",
    "间接调用（无直接调用者）",
    "越过代码段",
    "控制流汇合",
    "认不出的指令",
    "调用返回值",
    "调用后易失寄存器",
    "movk 拼在寄存器拷贝上",
    "movk 拼在非常量上",
    "位掩码立即数",
    "取数（配置 / 全局 / 结构体）",
    "运行时计算",
};

typedef struct {
    int kind, msg, reg;
    uint64_t value;   // constants only
    int64_t at;
} tres_t;
typedef struct {
    tres_t *v;
    size_t n, cap;
} tvec_t;

static int tpush(ctx_t *x, tvec_t *o, int kind, int msg, int reg, uint64_t value, int64_t at) {
    if (!vec_reserve((void **)&o->v, &o->cap, o->n + 1, sizeof *o->v)) return fail(x, RB_S2ARM_ADDR_IO, "out of memory");
    tres_t *t = &o->v[o->n++];
    t->kind = kind;
    t->msg = msg;
    t->reg = reg;
    t->value = value;
    t->at = at;
    return 0;
}

// _source_kind: kind K_REGISTER carries the source register in *value.
static void source_kind(uint32_t w, int *kind, int *msg, uint64_t *value) {
    *msg = M_NONE;
    *value = 0;
    uint64_t v;
    if ((w & 0x7F800000) == 0x52800000) {
        *kind = K_CONST;
        *value = (uint64_t)((w >> 5) & 0xFFFF) << (16 * ((w >> 21) & 3));
    } else if ((w & 0x7F800000) == 0x12800000) {
        uint64_t n = ~((uint64_t)((w >> 5) & 0xFFFF) << (16 * ((w >> 21) & 3)));
        *kind = K_CONST;
        *value = n & ((w >> 31) ? ~(uint64_t)0 : 0xFFFFFFFFu);
    } else if ((w & 0x7F8003E0) == 0x320003E0) {
        if (bitmask((w >> 22) & 1, (w >> 16) & 0x3F, (w >> 10) & 0x3F, &v)) {
            *kind = K_CONST;
            *value = v;
        } else {
            *kind = K_COMPUTE;
            *msg = M_BITMASK;
        }
    } else if ((w & 0x7FE0FFE0) == 0x2A0003E0) {
        unsigned rm = (w >> 16) & 31;
        if (rm == 31) {
            *kind = K_CONST;
        } else {
            *kind = K_REGISTER;
            *value = rm;
        }
    } else if ((w & 0x7FFFFC00) == 0x11000000) {
        *kind = K_REGISTER;
        *value = (w >> 5) & 31;
    } else if ((w & 0x0A000000) == 0x08000000) {
        *kind = K_LOAD;
        *msg = M_LOAD;
    } else {
        *kind = K_COMPUTE;
        *msg = M_RUNTIME;
    }
}

// _trace: appends the sources of `reg` at the call `site` to `out` in the original's list order.
static int trace(ctx_t *x, const code_t *c, int64_t site, int reg, int depth, int *budget, tvec_t *out) {
    int64_t cur = site - 4, start = 0;
    int has_start, st;
    uint32_t movk[TRACE_BUDGET];
    size_t nmovk = 0;
    if ((st = function_start(x, c, site, &start, &has_start))) return st;
    for (;;) {
        if (*budget <= 0) return tpush(x, out, K_UNKNOWN, M_BUDGET, 0, 0, site);
        (*budget)--;
        if (has_start && cur < start) {
            if (reg > 7) return tpush(x, out, K_UNKNOWN, M_NONARG, reg, 0, start);
            if (depth <= 0) return tpush(x, out, K_UNKNOWN, M_DEEP, 0, 0, start);
            const uint32_t *callers;
            size_t n = callers_of(c, start, &callers);
            if (!n) return tpush(x, out, K_UNKNOWN, M_INDIRECT, 0, 0, start);
            for (size_t i = 0; i < n; i++)
                if ((st = trace(x, c, c->lo + 4 * (int64_t)callers[i], reg, depth - 1, budget, out))) return st;
            return 0;
        }
        if (cur < c->lo) return tpush(x, out, K_UNKNOWN, M_PASTTEXT, 0, 0, cur);
        uint32_t w, writes;
        if ((st = word_at(x, c, cur, &w))) return st;
        if (branch_word(w) && (w & 0xFC000000) != 0x94000000) return tpush(x, out, K_UNKNOWN, M_JOIN, 0, 0, cur);
        if (!gpr_writes(w, &writes)) return tpush(x, out, K_COMPUTE, M_UNKNOWN_INSN, 0, 0, cur);
        if ((w & 0xFC000000) == 0x94000000 && reg >= 0 && reg < 19) {
            if (reg == 0) return tpush(x, out, K_COMPUTE, M_CALLRET, 0, 0, cur);
            return tpush(x, out, K_UNKNOWN, M_VOLATILE, 0, 0, cur);
        }
        if (reg >= 0 && reg < 32 && (writes >> reg & 1)) {
            if ((w & 0x7F800000) == 0x72800000) {   // movk: remember its 16 bits, look for the earlier movz
                if (nmovk >= TRACE_BUDGET) return fail(x, RB_S2ARM_ADDR_INVALID, "movk chain too long");
                movk[nmovk++] = w;
                cur -= 4;
                continue;
            }
            int kind, msg;
            uint64_t value;
            source_kind(w, &kind, &msg, &value);
            if (kind == K_REGISTER) {
                if (nmovk) return tpush(x, out, K_COMPUTE, M_MOVK_REG, 0, 0, cur);
                reg = (int)value;
                cur -= 4;
                continue;
            }
            if (kind == K_CONST && nmovk) {
                for (size_t i = nmovk; i-- > 0;) {
                    unsigned sh = 16 * ((movk[i] >> 21) & 3);
                    value = (value & ~((uint64_t)0xFFFF << sh)) | (uint64_t)((movk[i] >> 5) & 0xFFFF) << sh;
                }
            } else if (nmovk) {
                return tpush(x, out, K_COMPUTE, M_MOVK_NONCONST, 0, 0, cur);
            }
            return tpush(x, out, kind, msg, 0, value, cur);
        }
        cur -= 4;
    }
}

// ---------- alias_unbounded ----------

typedef struct {
    int64_t site;
    int kind;
    char *detail;
} reason_t;
typedef struct {
    reason_t *v;
    size_t n, cap;
} reasons_t;

static void reasons_free(reasons_t *r) {
    for (size_t i = 0; i < r->n; i++) free(r->v[i].detail);
    free(r->v);
    memset(r, 0, sizeof *r);
}

static int is_commit(const stub_t *stubs, size_t n, int64_t addr) {
    size_t lo = 0, hi = n;
    while (lo < hi) {
        size_t mid = (lo + hi) / 2;
        if (stubs[mid].addr < addr) lo = mid + 1; else hi = mid;
    }
    return lo < n && stubs[lo].addr == addr && stubs[lo].name == N_COMMIT;
}

static const char *const k_conditional_suffix = "；预留后提交是条件性的，地址可只预留";

static int alias_unbounded(ctx_t *x, const code_t *c, reasons_t *rs) {
    const int depth = 6;
    stub_t *stubs = NULL;
    size_t nstubs = 0;
    int st = import_stub_names(x, c, N_ALL, &stubs, &nstubs);
    if (st) return st;
    tvec_t tv = {0};
    for (size_t si = 0; si < nstubs && !st; si++) {
        int name = stubs[si].name;
        if (name == N_COMMIT) continue;
        const uint32_t *sites;
        size_t ns = callers_of(c, stubs[si].addr, &sites);
        for (size_t s = 0; s < ns && !st; s++) {
            int64_t site = c->lo + 4 * (int64_t)sites[s];
            int conditional_commit = 0, size_reg;
            if (name == N_ADDRESS_REGION || name == N_NLIB_VIRTUAL) {
                int committed = 0, saw_condition = 0;
                for (int k = 1; k < 25; k++) {
                    uint32_t w;
                    if ((st = word_at(x, c, site + 4 * (int64_t)k, &w))) break;
                    if (w == 0xD65F03C0) break;
                    if ((w & 0x7E000000) == 0x34000000 || (w & 0x7E000000) == 0x36000000 || (w & 0xFF000010) == 0x54000000) {
                        saw_condition = 1;
                    } else if (branch_word(w) && (w & 0xFC000000) != 0x94000000) {
                        break;
                    }
                    if ((w & 0xFC000000) == 0x94000000) {
                        int64_t off = w & 0x3FFFFFF;
                        if (off & (1 << 25)) off -= (int64_t)1 << 26;
                        if (is_commit(stubs, nstubs, site + 4 * (k + off))) {
                            committed = !saw_condition;
                            conditional_commit = saw_condition;
                            break;
                        }
                    }
                }
                if (st) break;
                if (committed) continue;
                size_reg = 1;
            } else {
                int budget = TRACE_BUDGET, any_zero = 0;
                tv.n = 0;
                if ((st = trace(x, c, site, 1, depth, &budget, &tv))) break;
                for (size_t i = 0; i < tv.n; i++)
                    if (tv.v[i].kind == K_CONST && tv.v[i].value == 0) any_zero = 1;
                if (!any_zero) continue;
                size_reg = 2;
            }
            int budget = TRACE_BUDGET;
            tv.n = 0;
            if ((st = trace(x, c, site, size_reg, depth, &budget, &tv))) break;
            for (size_t i = 0; i < tv.n && !st; i++) {
                const tres_t *t = &tv.v[i];
                if (t->kind == K_CONST) continue;
                char text[96];
                if (t->msg == M_NONARG) snprintf(text, sizeof text, "x%d 进函数前就有（非参数寄存器）", t->reg);
                else snprintf(text, sizeof text, "%s", k_msg_text[t->msg]);
                size_t cap = strlen(text) + strlen(k_conditional_suffix) + 40;
                char *detail = malloc(cap);
                if (!detail) {
                    st = fail(x, RB_S2ARM_ADDR_IO, "out of memory");
                    break;
                }
                int n = snprintf(detail, cap, "%s@%s0x%llx", text, t->at < 0 ? "-" : "", (unsigned long long)(t->at < 0 ? -t->at : t->at));
                if ((name == N_ADDRESS_REGION || name == N_NLIB_VIRTUAL) && conditional_commit) snprintf(detail + n, cap - (size_t)n, "%s", k_conditional_suffix);
                if (!vec_reserve((void **)&rs->v, &rs->cap, rs->n + 1, sizeof *rs->v)) {
                    free(detail);
                    st = fail(x, RB_S2ARM_ADDR_IO, "out of memory");
                    break;
                }
                rs->v[rs->n].site = site;
                rs->v[rs->n].kind = t->kind;
                rs->v[rs->n].detail = detail;
                rs->n++;
            }
        }
    }
    free(tv.v);
    free(stubs);
    return st;
}

// ---------- collect ----------

static int mkdir_parents(const char *path) {
    size_t plen = strlen(path);
    char *copy = malloc(plen + 1);
    if (!copy) return 0;
    memcpy(copy, path, plen + 1);
    char *slash = strrchr(copy, '/');
    int ok = 1;
    if (slash && slash != copy) {
        *slash = 0;
        for (char *p = copy + 1; ok; p++) {
            if (*p == '/' || *p == 0) {
                char save = *p;
                *p = 0;
                struct stat sb;
                if (mkdir(copy, 0777) != 0 && !(stat(copy, &sb) == 0 && S_ISDIR(sb.st_mode))) ok = 0;
                *p = save;
                if (!save) break;
            }
        }
    }
    free(copy);
    return ok;
}

static int build_table(ctx_t *x, const char *program, const char *build, const code_t *code, sbuf_t *table) {
    int alias = 0, st = 0;
    reasons_t rs = {0};
    char tmp[256];
    if (code) {
        if ((st = static_alias_gb(x, code, &alias))) return st;
        if (alias && (st = alias_unbounded(x, code, &rs))) {
            reasons_free(&rs);
            return st;
        }
    }
    snprintf(tmp, sizeof tmp, "# 地址需求采集算法 2\n版本\t2\n程序号\t%s\n构建号\t%s\n别名区GB\t%d\n普通堆MB\t%d\n", program, build, alias, APP_POOL_MB);
    sb_str(table, tmp);
    if (rs.n) {
        size_t N = rs.n;
        char **items = calloc(N, sizeof *items);
        size_t *ilen = malloc(N * sizeof *ilen), *pre = malloc((N + 1) * sizeof *pre);
        if (!items || !ilen || !pre) {
            st = fail(x, RB_S2ARM_ADDR_IO, "out of memory");
        } else {
            pre[0] = 0;
            for (size_t i = 0; i < N && !st; i++) {
                size_t cap = strlen(rs.v[i].detail) + 128;
                items[i] = malloc(cap);
                if (!items[i]) {
                    st = fail(x, RB_S2ARM_ADDR_IO, "out of memory");
                    break;
                }
                int n = snprintf(items[i], cap, "main+0x%llx %s（%s）", (unsigned long long)rs.v[i].site, k_kind_text[rs.v[i].kind], rs.v[i].detail);
                ilen[i] = (size_t)n;
                pre[i + 1] = pre[i] + ilen[i];
            }
        }
        if (!st) {
            char header[128], more[64];
            int hlen = snprintf(header, sizeof header, "只占地址、尺寸非常量的申请 %zu 处：", N);
            size_t n;
            for (n = N; n >= 1; n--) {
                size_t mlen = 0;
                if (n < N) mlen = (size_t)snprintf(more, sizeof more, "；另 %zu 处", N - n);
                size_t total = (size_t)hlen + pre[n] + 3 * (n - 1) + mlen;
                if (total <= 400) break;
            }
            if (n == 0) n = 1;   // the original keeps the one-item line when nothing fits
            sb_str(table, "别名区上限\t不定\n上限不定原因\t");
            sb_str(table, header);
            for (size_t i = 0; i < n; i++) {
                if (i) sb_str(table, "；");
                sb_str(table, items[i]);
            }
            if (n < N) {
                snprintf(more, sizeof more, "；另 %zu 处", N - n);
                sb_str(table, more);
            }
            sb_str(table, "\n");
        }
        if (items)
            for (size_t i = 0; i < N; i++) free(items[i]);
        free(items);
        free(ilen);
        free(pre);
    }
    reasons_free(&rs);
    if (!st && table->oom) st = fail(x, RB_S2ARM_ADDR_IO, "out of memory");
    return st;
}

int rb_s2arm_addr_need(const char *main_nso, const char *npdm, const char *output_path, char *error, size_t error_size) {
    ctx_t x = {error, error_size};
    if (error && error_size) error[0] = 0;
    if (!main_nso || !npdm || !output_path) return fail(&x, RB_S2ARM_ADDR_INVALID, "missing argument");
    uint8_t *npdm_data = NULL, *main_data = NULL;
    size_t npdm_len = 0, main_len = 0;
    nso_t nso = {0};
    code_t code;
    int have_code = 0, st;
    char program[17] = "", build[33];
    int vamm = 0;
    sbuf_t table = {0};
    if ((st = read_file(&x, npdm, &npdm_data, &npdm_len))) goto done;
    if ((st = npdm_info(&x, npdm_data, npdm_len, program, &vamm))) goto done;
    if ((st = read_file(&x, main_nso, &main_data, &main_len))) goto done;
    if (main_len < 0x50) {
        st = fail(&x, RB_S2ARM_ADDR_INVALID, "main is too short to hold the build id at 0x40");
        goto done;
    }
    for (int i = 0; i < 16; i++) snprintf(build + 2 * i, 3, "%02x", main_data[0x40 + i]);
    if (vamm) {
        if ((st = nso_image(&x, main_data, main_len, &nso))) goto done;
        if ((st = code_init(&x, &code, &nso))) goto done;
        have_code = 1;
    }
    if ((st = build_table(&x, program, build, have_code ? &code : NULL, &table))) goto done;
    if (!mkdir_parents(output_path)) {
        st = fail(&x, RB_S2ARM_ADDR_IO, "cannot create the directory of %s", output_path);
        goto done;
    }
    {
        FILE *f = fopen(output_path, "wb");
        if (!f) {
            st = fail(&x, RB_S2ARM_ADDR_IO, "cannot write %s: %s", output_path, strerror(errno));
            goto done;
        }
        size_t wrote = fwrite(table.p, 1, table.n, f);
        int closed = fclose(f);
        if (wrote != table.n || closed != 0) st = fail(&x, RB_S2ARM_ADDR_IO, "cannot write %s", output_path);
    }
done:
    if (have_code) code_free(&code);
    free(nso.image);
    free(npdm_data);
    free(main_data);
    free(table.p);
    return st;
}
