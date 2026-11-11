// Port of S2Arm tools/nro_exports.py and runtime/rewriter/nro_to_nso.py (Apache-2.0, pinned commit in
// tools/s2arm_prototype/pin.json), with the RomFS walk of graphics/nvn/tools/romfs_list.py they use.
// The originals rely on Python exceptions (struct.error, ValueError) for every out-of-range read; each such
// place is an explicit check here and ends in RB_S2ARM_NRO_INVALID. Directory order never matters: both
// originals sort the relative paths (plain string order, which is byte order for UTF-8) before using them.
// romfs_list.walk semantics kept: unreadable directories are skipped silently, symlinks to directories are not
// entered and are not files, and entries that are not real directories and are named .DS_Store or start with
// "._" are skipped.
#define _POSIX_C_SOURCE 200809L
#include "s2arm_nro.h"

#include <dirent.h>
#include <errno.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>

#define FILE_CAP ((uint64_t)1 << 30)   // refuse files above 1 GiB (the original's own NMAX for a single NRO)
#define MAX_DEPTH 256
#define PAGE 0x1000u

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

static uint16_t le16(const uint8_t *p) { return (uint16_t)(p[0] | p[1] << 8); }
static uint32_t le32(const uint8_t *p) { return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24; }
static uint64_t le64(const uint8_t *p) { return (uint64_t)le32(p) | (uint64_t)le32(p + 4) << 32; }
static void put32(uint8_t *p, uint32_t v) {
    p[0] = (uint8_t)v;
    p[1] = (uint8_t)(v >> 8);
    p[2] = (uint8_t)(v >> 16);
    p[3] = (uint8_t)(v >> 24);
}

// struct.unpack_from position check for `size` bytes at `off` of a buffer of `len` bytes (negative offsets
// count from the end).
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

static int read_file(ctx_t *x, const char *path, uint8_t **data, size_t *len) {
    struct stat sb;
    if (stat(path, &sb) == 0 && S_ISDIR(sb.st_mode)) return fail(x, RB_S2ARM_NRO_IO, "%s is a directory", path);
    FILE *f = fopen(path, "rb");
    if (!f) return fail(x, RB_S2ARM_NRO_IO, "cannot open %s: %s", path, strerror(errno));
    uint8_t *buf = NULL;
    size_t n = 0, cap = 0;
    for (;;) {
        if (!vec_reserve((void **)&buf, &cap, n + 65536 + 1, 1)) {
            free(buf);
            fclose(f);
            return fail(x, RB_S2ARM_NRO_IO, "out of memory reading %s", path);
        }
        size_t got = fread(buf + n, 1, 65536, f);
        n += got;
        if (n > FILE_CAP) {
            free(buf);
            fclose(f);
            return fail(x, RB_S2ARM_NRO_INVALID, "%s is larger than 1 GiB", path);
        }
        if (got < 65536) break;
    }
    int bad = ferror(f);
    fclose(f);
    if (bad) {
        free(buf);
        return fail(x, RB_S2ARM_NRO_IO, "cannot read %s", path);
    }
    *data = buf;
    *len = n;
    return 0;
}

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

static int write_file(ctx_t *x, const char *path, const void *data, size_t len) {
    if (!mkdir_parents(path)) return fail(x, RB_S2ARM_NRO_IO, "cannot create the directory of %s", path);
    FILE *f = fopen(path, "wb");
    if (!f) return fail(x, RB_S2ARM_NRO_IO, "cannot write %s: %s", path, strerror(errno));
    size_t wrote = len ? fwrite(data, 1, len, f) : 0;
    int closed = fclose(f);
    if (wrote != len || closed != 0) return fail(x, RB_S2ARM_NRO_IO, "cannot write %s", path);
    return 0;
}

static char *join_path(const char *a, const char *b) {
    size_t la = strlen(a), lb = strlen(b);
    char *r = malloc(la + 1 + lb + 1);
    if (!r) return NULL;
    memcpy(r, a, la);
    r[la] = '/';
    memcpy(r + la + 1, b, lb + 1);
    return r;
}

static int isdir(const char *path) {
    struct stat sb;
    return stat(path, &sb) == 0 && S_ISDIR(sb.st_mode);
}

static int ends_nro_ci(const char *name, const char *ext) {   // name.lower().endswith(ext), ext lowercase ASCII
    size_t n = strlen(name), e = strlen(ext);
    if (n < e) return 0;
    for (size_t i = 0; i < e; i++) {
        char c = name[n - e + i];
        if (c >= 'A' && c <= 'Z') c = (char)(c + 32);
        if (c != ext[i]) return 0;
    }
    return 1;
}

// ---------- SHA-256 ----------

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

static uint32_t ror(uint32_t v, int n) { return v >> n | v << (32 - n); }

static void sha_block(sha_t *s, const uint8_t *p) {
    uint32_t w[64];
    for (int i = 0; i < 16; i++) w[i] = (uint32_t)p[4 * i] << 24 | (uint32_t)p[4 * i + 1] << 16 | (uint32_t)p[4 * i + 2] << 8 | p[4 * i + 3];
    for (int i = 16; i < 64; i++) {
        uint32_t s0 = ror(w[i - 15], 7) ^ ror(w[i - 15], 18) ^ (w[i - 15] >> 3);
        uint32_t s1 = ror(w[i - 2], 17) ^ ror(w[i - 2], 19) ^ (w[i - 2] >> 10);
        w[i] = w[i - 16] + s0 + w[i - 7] + s1;
    }
    uint32_t a = s->h[0], b = s->h[1], c = s->h[2], d = s->h[3], e = s->h[4], f = s->h[5], g = s->h[6], h = s->h[7];
    for (int i = 0; i < 64; i++) {
        uint32_t t1 = h + (ror(e, 6) ^ ror(e, 11) ^ ror(e, 25)) + ((e & f) ^ (~e & g)) + K256[i] + w[i];
        uint32_t t2 = (ror(a, 2) ^ ror(a, 13) ^ ror(a, 22)) + ((a & b) ^ (a & c) ^ (b & c));
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

static void to_hex(const uint8_t h[32], char out[65]) {
    for (int i = 0; i < 32; i++) snprintf(out + 2 * i, 3, "%02x", h[i]);
}

// ---------- set of 32-byte hashes, in insertion order ----------

typedef struct {
    uint8_t *keys;   // n * 32 bytes, insertion order
    size_t n, cap;
    uint32_t *slots;   // index + 1, 0 = empty
    size_t nslots;
} hset_t;

static void hset_free(hset_t *s) {
    free(s->keys);
    free(s->slots);
}

static size_t hset_slot(const hset_t *s, const uint8_t *key) {
    size_t i = (size_t)le64(key) & (s->nslots - 1);
    while (s->slots[i] && memcmp(s->keys + (size_t)(s->slots[i] - 1) * 32, key, 32)) i = (i + 1) & (s->nslots - 1);
    return i;
}

static int hset_find(const hset_t *s, const uint8_t *key) { return s->nslots && s->slots[hset_slot(s, key)] != 0; }

// Adds `key` (not present). Returns 0 on success, -1 when out of memory.
static int hset_add(hset_t *s, const uint8_t *key) {
    if (s->n >= UINT32_MAX / 2) return -1;
    if (s->n * 2 >= s->nslots) {
        size_t ns = s->nslots ? s->nslots * 2 : 64;
        uint32_t *slots = calloc(ns, sizeof *slots);
        if (!slots) return -1;
        free(s->slots);
        s->slots = slots;
        s->nslots = ns;
        for (size_t k = 0; k < s->n; k++) s->slots[hset_slot(s, s->keys + k * 32)] = (uint32_t)(k + 1);
    }
    if (!vec_reserve((void **)&s->keys, &s->cap, (s->n + 1) * 32, 1)) return -1;
    memcpy(s->keys + s->n * 32, key, 32);
    s->n++;
    s->slots[hset_slot(s, key)] = (uint32_t)s->n;
    return 0;
}

// ---------- romfs_list.walk: the files of a RomFS ----------

typedef struct {
    char **v;
    size_t n, cap;
} strvec_t;

static void strvec_free(strvec_t *s) {
    for (size_t i = 0; i < s->n; i++) free(s->v[i]);
    free(s->v);
}

static int strvec_push(strvec_t *s, char *str) {   // takes ownership on success
    if (!vec_reserve((void **)&s->v, &s->cap, s->n + 1, sizeof *s->v)) return 0;
    s->v[s->n++] = str;
    return 1;
}

static int cmp_str(const void *a, const void *b) { return strcmp(*(char *const *)a, *(char *const *)b); }

// Lists the names of one directory (without . and ..); 0 when it cannot be opened, -1 out of memory.
static int list_names(const char *path, strvec_t *names) {
    DIR *d = opendir(path);
    if (!d) return 0;
    int st = 1;
    for (struct dirent *e; (e = readdir(d));) {
        if (!strcmp(e->d_name, ".") || !strcmp(e->d_name, "..")) continue;
        char *copy = strdup(e->d_name);
        if (!copy || !strvec_push(names, copy)) {
            free(copy);
            st = -1;
            break;
        }
    }
    closedir(d);
    return st;
}

// Collects the RomFS-relative paths of the files whose name ends in .nro (any case).
static int walk_nro(ctx_t *x, const char *root, const char *rel, int depth, strvec_t *found) {
    if (depth > MAX_DEPTH) return fail(x, RB_S2ARM_NRO_INVALID, "directory tree deeper than %d levels", MAX_DEPTH);
    char *dir = rel[0] ? join_path(root, rel) : strdup(root);
    if (!dir) return fail(x, RB_S2ARM_NRO_IO, "out of memory");
    strvec_t names = {0};
    int listed = list_names(dir, &names);   // an unreadable directory is skipped, as os.walk does
    int st = 0;
    if (listed < 0) st = fail(x, RB_S2ARM_NRO_IO, "out of memory");
    for (size_t i = 0; !st && i < names.n; i++) {
        const char *name = names.v[i];
        char *full = join_path(dir, name);
        char *relname = rel[0] ? join_path(rel, name) : strdup(name);
        if (!full || !relname) {
            free(full);
            free(relname);
            st = fail(x, RB_S2ARM_NRO_IO, "out of memory");
            break;
        }
        struct stat ls, fs;
        int real_dir = 0, is_link = 0, follows_dir = 0;
        if (lstat(full, &ls) == 0) {
            is_link = S_ISLNK(ls.st_mode);
            real_dir = S_ISDIR(ls.st_mode);
        }
        if (stat(full, &fs) == 0) follows_dir = S_ISDIR(fs.st_mode);
        int keep = 1;
        if (!real_dir && (!strcmp(name, ".DS_Store") || !strncmp(name, "._", 2))) keep = 0;   // macOS litter
        if (keep && follows_dir) {
            if (real_dir && !is_link) st = walk_nro(x, root, relname, depth + 1, found);
            free(relname);
        } else if (keep && ends_nro_ci(name, ".nro")) {
            if (!strvec_push(found, relname)) {
                free(relname);
                st = fail(x, RB_S2ARM_NRO_IO, "out of memory");
            }
        } else {
            free(relname);
        }
        free(full);
    }
    strvec_free(&names);
    free(dir);
    return st;
}

static int collect_nro(ctx_t *x, const char *romfs, strvec_t *found) {
    int st = walk_nro(x, romfs, "", 0, found);
    if (!st && found->n > 1) qsort(found->v, found->n, sizeof *found->v, cmp_str);   // found.sort()
    return st;
}

// ---------- nro_exports.py ----------

// bytes.decode('utf-8', 'replace'): every maximal ill-formed subpart becomes one U+FFFD.
static void append_utf8_replace(sbuf_t *out, const uint8_t *b, size_t n) {
    static const char fffd[] = "\xEF\xBF\xBD";
    size_t i = 0;
    while (i < n) {
        uint8_t c = b[i];
        size_t need = 0;
        uint8_t lo = 0x80, hi = 0xBF;
        if (c < 0x80) {
            sb_add(out, (const char *)b + i, 1);
            i++;
            continue;
        } else if (c >= 0xC2 && c <= 0xDF) {
            need = 1;
        } else if (c >= 0xE0 && c <= 0xEF) {
            need = 2;
            if (c == 0xE0) lo = 0xA0;
            if (c == 0xED) hi = 0x9F;
        } else if (c >= 0xF0 && c <= 0xF4) {
            need = 3;
            if (c == 0xF0) lo = 0x90;
            if (c == 0xF4) hi = 0x8F;
        } else {
            sb_add(out, fffd, 3);
            i++;
            continue;
        }
        size_t k = 1;   // bytes of the sequence that are valid so far
        while (k <= need && i + k < n) {
            uint8_t cc = b[i + k];
            if (cc < lo || cc > hi) break;
            lo = 0x80;
            hi = 0xBF;
            k++;
        }
        if (k == need + 1) {
            sb_add(out, (const char *)b + i, k);
        } else {
            sb_add(out, fffd, 3);
        }
        i += k;
    }
}

// exports(path): appends "<symbol>\t<rel>\n" per exported symbol; INVALID where the original raises.
static int nro_exports_of(ctx_t *x, const char *rel, const uint8_t *d, size_t len, sbuf_t *rows) {
    size_t pos;
    if (len < 0x14 || memcmp(d + 0x10, "NRO0", 4)) return fail(x, RB_S2ARM_NRO_INVALID, "%s: not an NRO (no NRO0 marker)", rel);
    uint64_t m0 = le32(d + 4);
    if (m0 + 4 > len || memcmp(d + m0, "MOD0", 4)) return fail(x, RB_S2ARM_NRO_INVALID, "%s: no MOD0 at offset %#llx", rel, (unsigned long long)m0);
    if (!rd_pos(len, (int64_t)m0 + 4, 4, &pos)) return fail(x, RB_S2ARM_NRO_INVALID, "%s: MOD0 truncated", rel);
    int64_t dyn = (int64_t)m0 + (int32_t)le32(d + pos);
    uint64_t symtab = 0, strtab = 0;
    int have5 = 0, have6 = 0;
    for (int64_t o = dyn; o < (int64_t)len - 16; o += 16) {   // range(dyn, len(d) - 16, 16)
        if (!rd_pos(len, o, 16, &pos)) return fail(x, RB_S2ARM_NRO_INVALID, "%s: dynamic segment out of range", rel);
        uint64_t tag = le64(d + pos), value = le64(d + pos + 8);
        if (tag == 0) break;
        if (tag == 5 && !have5) {
            have5 = 1;
            strtab = value;
        } else if (tag == 6 && !have6) {
            have6 = 1;
            symtab = value;
        }
    }
    if (!have5 || !have6 || !(symtab < strtab)) return fail(x, RB_S2ARM_NRO_INVALID, "%s: no usable DT_SYMTAB / DT_STRTAB in the dynamic segment", rel);
    for (uint64_t o = symtab; o < strtab; o += 24) {
        if (o > len || len - o < 24) return fail(x, RB_S2ARM_NRO_INVALID, "%s: symbol table out of range", rel);
        uint32_t nm = le32(d + o);
        uint8_t info = d[o + 4];
        uint16_t shndx = le16(d + o + 6);
        if (!shndx || ((info >> 4) != 1 && (info >> 4) != 2)) continue;
        if (strtab > UINT64_MAX - nm) return fail(x, RB_S2ARM_NRO_INVALID, "%s: symbol name out of range", rel);
        uint64_t start = strtab + nm;
        const uint8_t *end = start < len ? memchr(d + start, 0, len - (size_t)start) : NULL;   // d.index(b'\0', st + nm)
        if (!end) return fail(x, RB_S2ARM_NRO_INVALID, "%s: symbol name without terminator", rel);
        size_t nlen = (size_t)(end - (d + start));
        if (!nlen) continue;
        append_utf8_replace(rows, d + start, nlen);
        sb_str(rows, "\t");
        sb_str(rows, rel);
        sb_str(rows, "\n");
        if (rows->oom) return fail(x, RB_S2ARM_NRO_IO, "out of memory");
    }
    return 0;
}

int rb_s2arm_nro_exports(const char *romfs_dir, const char *output_path, char *error, size_t error_size) {
    ctx_t x = {error, error_size};
    if (error && error_size) error[0] = 0;
    if (!romfs_dir || !output_path) return fail(&x, RB_S2ARM_NRO_INVALID, "missing path");
    if (!isdir(romfs_dir)) return RB_S2ARM_NRO_OK;   // os.path.isdir(nd) else []: nothing to write
    strvec_t found = {0};
    sbuf_t rows = {0};
    int st = collect_nro(&x, romfs_dir, &found);
    if (st || !found.n) goto done;
    sb_str(&rows, "# nro_exports.tsv：tools/nro_exports.py 出；romfs/nro 下各 NRO 的导出符号（符号<TAB>NRO 文件名），装载器把命中的未解析导入记成「延迟到 nn::ro 装载」\n");
    for (size_t i = 0; i < found.n; i++) {
        char *path = join_path(romfs_dir, found.v[i]);
        if (!path) {
            st = fail(&x, RB_S2ARM_NRO_IO, "out of memory");
            goto done;
        }
        uint8_t *data = NULL;
        size_t len = 0;
        st = read_file(&x, path, &data, &len);
        free(path);
        if (st) goto done;
        st = nro_exports_of(&x, found.v[i], data, len, &rows);
        free(data);
        if (st) goto done;
    }
    if (rows.oom) {
        st = fail(&x, RB_S2ARM_NRO_IO, "out of memory");
        goto done;
    }
    st = write_file(&x, output_path, rows.p, rows.n);
done:
    strvec_free(&found);
    free(rows.p);
    return st;
}

// ---------- nro_to_nso.py ----------

// parse(d, what): validates the NRO and returns its three segments and the bss size.
static int nro_parse(ctx_t *x, const char *what, const uint8_t *d, size_t len, uint32_t segs[3][2], uint32_t *bss) {
    if (len < 0x80 || memcmp(d + 0x10, "NRO0", 4)) return fail(x, RB_S2ARM_NRO_INVALID, "%s: not an NRO (no NRO0 marker)", what);
    uint64_t size = le32(d + 0x18);
    for (int i = 0; i < 3; i++) {
        segs[i][0] = le32(d + 0x20 + i * 8);
        segs[i][1] = le32(d + 0x24 + i * 8);
    }
    *bss = le32(d + 0x38);
    if (size != len) return fail(x, RB_S2ARM_NRO_INVALID, "%s: size %#llx in the header differs from the file %#zx", what, (unsigned long long)size, len);
    uint64_t to = segs[0][0], ts = segs[0][1], ro = segs[1][0], rs = segs[1][1], dt = segs[2][0], ds = segs[2][1];
    if (to != 0 || ro != ts || dt != ro + rs || dt + ds != size) return fail(x, RB_S2ARM_NRO_INVALID, "%s: segments are not contiguous", what);
    if ((ts | rs | ds | *bss) & (PAGE - 1)) return fail(x, RB_S2ARM_NRO_INVALID, "%s: segment or bss not 4 KiB aligned", what);
    uint64_t m0 = le32(d + 4);
    if (m0 + 4 > len || memcmp(d + m0, "MOD0", 4)) return fail(x, RB_S2ARM_NRO_INVALID, "%s: no MOD0 at offset %#llx", what, (unsigned long long)m0);
    return 0;
}

// to_nso(d, segs, bss): 0x100-byte NSO header (version 0, flags 0) followed by the NRO. Returns NULL when out of memory.
static uint8_t *nro_to_nso_bytes(const uint8_t *d, size_t len, uint32_t segs[3][2], uint32_t bss, size_t *outlen) {
    uint8_t *r = calloc(0x100 + len, 1);
    if (!r) return NULL;
    memcpy(r, "NSO0", 4);
    uint32_t fo = 0x100;
    for (int i = 0; i < 3; i++) {
        put32(r + 0x10 + i * 0x10, fo);
        put32(r + 0x14 + i * 0x10, segs[i][0]);
        put32(r + 0x18 + i * 0x10, segs[i][1]);
        put32(r + 0x60 + i * 4, segs[i][1]);
        fo += segs[i][1];
    }
    put32(r + 0x3C, bss);
    memcpy(r + 0x40, d + 0x40, 0x20);    // build id
    memcpy(r + 0x88, d + 0x68, 0x18);    // api info / dynamic string table / dynamic symbol table
    memcpy(r + 0x100, d, len);
    *outlen = 0x100 + len;
    return r;
}

// nrr_hashes(romfs): hashes registered by romfs/.nrr/*.nrr, by NRR file name then table order, deduplicated.
static int nrr_hashes(ctx_t *x, const char *romfs, hset_t *reg) {
    char *nd = join_path(romfs, ".nrr");
    if (!nd) return fail(x, RB_S2ARM_NRO_IO, "out of memory");
    int st = 0;
    strvec_t names = {0};
    if (!isdir(nd)) goto done;
    {
        DIR *probe = opendir(nd);
        if (!probe) {
            st = fail(x, RB_S2ARM_NRO_IO, "cannot read directory %s: %s", nd, strerror(errno));
            goto done;
        }
        closedir(probe);
    }
    if (list_names(nd, &names) < 0) {
        st = fail(x, RB_S2ARM_NRO_IO, "out of memory");
        goto done;
    }
    qsort(names.v, names.n, sizeof *names.v, cmp_str);   // sorted(romfs_list.listdir(nd))
    for (size_t i = 0; i < names.n; i++) {
        const char *f = names.v[i];
        if (!ends_nro_ci(f, ".nrr")) continue;
        char *path = join_path(nd, f);
        if (!path) {
            st = fail(x, RB_S2ARM_NRO_IO, "out of memory");
            goto done;
        }
        struct stat sb;
        if (stat(path, &sb) != 0 || !S_ISREG(sb.st_mode)) {   // os.path.isfile
            free(path);
            continue;
        }
        uint8_t *d = NULL;
        size_t len = 0;
        st = read_file(x, path, &d, &len);
        free(path);
        if (st) goto done;
        if (len < 0x350 || memcmp(d, "NRR0", 4)) {
            free(d);
            st = fail(x, RB_S2ARM_NRO_INVALID, ".nrr/%s: not an NRR (no NRR0 marker or shorter than 0x350 bytes)", f);
            goto done;
        }
        uint64_t off = le32(d + 0x340), cnt = le32(d + 0x344);
        if (off + cnt * 32 > len) {
            free(d);
            st = fail(x, RB_S2ARM_NRO_INVALID, ".nrr/%s: hash table %#llx + %llu x 32 exceeds the file %#zx", f, (unsigned long long)off, (unsigned long long)cnt, len);
            goto done;
        }
        for (uint64_t k = 0; k < cnt; k++) {
            const uint8_t *h = d + off + k * 32;
            if (!hset_find(reg, h) && hset_add(reg, h)) {
                free(d);
                st = fail(x, RB_S2ARM_NRO_IO, "out of memory");
                goto done;
            }
        }
        free(d);
    }
done:
    strvec_free(&names);
    free(nd);
    return st;
}

typedef struct {
    char name[24];
    uint64_t size;
    uint32_t bss;
    sbuf_t rels;   // RomFS-relative paths joined by '|'
    uint8_t hash[32];
} mod_t;

int rb_s2arm_nro_to_nso(const char *romfs_dir, const char *output_dir, char *error, size_t error_size) {
    ctx_t x = {error, error_size};
    if (error && error_size) error[0] = 0;
    if (!romfs_dir || !output_dir) return fail(&x, RB_S2ARM_NRO_INVALID, "missing path");
    strvec_t found = {0};
    hset_t reg = {0}, seen = {0};
    mod_t *mods = NULL;
    size_t nmods = 0, mcap = 0;
    sbuf_t table = {0};
    int st = collect_nro(&x, romfs_dir, &found);
    if (st) goto done;
    if ((st = nrr_hashes(&x, romfs_dir, &reg))) goto done;
    for (size_t i = 0; i < found.n; i++) {
        const char *rel = found.v[i];
        char *path = join_path(romfs_dir, rel);
        if (!path) {
            st = fail(&x, RB_S2ARM_NRO_IO, "out of memory");
            goto done;
        }
        uint8_t *d = NULL;
        size_t len = 0;
        st = read_file(&x, path, &d, &len);
        free(path);
        if (st) goto done;
        uint32_t segs[3][2], bss = 0;
        if ((st = nro_parse(&x, rel, d, len, segs, &bss))) {
            free(d);
            goto done;
        }
        uint8_t key[32];
        sha256(d, len, key);
        if (hset_find(&seen, key)) {   // same content: another source path of the module that has it
            size_t idx = (size_t)seen.slots[hset_slot(&seen, key)] - 1;   // module numbers follow insertion order
            sb_str(&mods[idx].rels, "|");
            sb_str(&mods[idx].rels, rel);
            free(d);
            if (mods[idx].rels.oom) {
                st = fail(&x, RB_S2ARM_NRO_IO, "out of memory");
                goto done;
            }
            continue;
        }
        size_t nsolen = 0;
        uint8_t *nso = nro_to_nso_bytes(d, len, segs, bss, &nsolen);
        if (!nso || hset_add(&seen, key) || !vec_reserve((void **)&mods, &mcap, nmods + 1, sizeof *mods)) {
            free(nso);
            free(d);
            st = fail(&x, RB_S2ARM_NRO_IO, "out of memory");
            goto done;
        }
        mod_t *m = &mods[nmods++];
        memset(m, 0, sizeof *m);
        snprintf(m->name, sizeof m->name, "nro%zu", nmods - 1);
        m->size = len;
        m->bss = bss;
        memcpy(m->hash, key, 32);
        sb_str(&m->rels, rel);
        free(d);
        char *outpath = join_path(output_dir, m->name);
        st = outpath ? write_file(&x, outpath, nso, nsolen) : fail(&x, RB_S2ARM_NRO_IO, "out of memory");
        free(outpath);
        free(nso);
        if (st || m->rels.oom) {
            if (!st) st = fail(&x, RB_S2ARM_NRO_IO, "out of memory");
            goto done;
        }
    }
    // want = registered hashes that no *.nro file has
    size_t want = 0;
    for (size_t k = 0; k < reg.n; k++) want += !hset_find(&seen, reg.keys + k * 32);
    if (want) {
        st = fail(&x, RB_S2ARM_NRO_UNSUPPORTED,
                  "%zu NRO hash(es) registered by the NRR files are not in any *.nro file: finding them inside other RomFS files needs zstd, which is not implemented",
                  want);
        goto done;
    }
    if (!nmods) goto done;   // no *.nro and nothing registered: no table
    sb_str(&table, "# 模块名\tSHA-256\tNRO 大小\tbss 大小\tromfs 相对路径\n");
    for (size_t i = 0; i < nmods; i++) {
        char hex[65], line[160];
        to_hex(mods[i].hash, hex);
        snprintf(line, sizeof line, "%s\t%s\t0x%llx\t0x%llx\t", mods[i].name, hex, (unsigned long long)mods[i].size, (unsigned long long)mods[i].bss);
        sb_str(&table, line);
        sb_add(&table, mods[i].rels.p, mods[i].rels.n);
        sb_str(&table, "\n");
    }
    if (table.oom) {
        st = fail(&x, RB_S2ARM_NRO_IO, "out of memory");
        goto done;
    }
    {
        char *tpath = join_path(output_dir, "nro_modules.tsv");
        st = tpath ? write_file(&x, tpath, table.p, table.n) : fail(&x, RB_S2ARM_NRO_IO, "out of memory");
        free(tpath);
    }
done:
    for (size_t i = 0; i < nmods; i++) free(mods[i].rels.p);
    free(mods);
    free(table.p);
    hset_free(&reg);
    hset_free(&seen);
    strvec_free(&found);
    return st;
}
