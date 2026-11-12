// Port of the `--gpu-drivers` mode of S2Arm graphics/nvn/games/profile_guess.py (Apache-2.0, pinned commit in
// tools/s2arm_prototype/pin.json): gpu_driver_modules (line ~180), nso (~35) and kind (~47), plus
// nso_syms.dynsyms from graphics/nvn/tools/nso_syms.py, whose only observable effect here is that it raises on
// a malformed module. The original relies on Python exceptions for every out-of-range read; each such place is
// an explicit check here (struct.unpack_from semantics, negative offsets count from the end) and ends in
// RB_S2ARM_MODULES_INVALID.
#define _POSIX_C_SOURCE 200809L
#include "s2arm_modules.h"
#include "lz4.h"

#include <dirent.h>
#include <errno.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>

#define IMAGE_CAP ((uint64_t)1 << 30)   // refuse files and images above 1 GiB (the original would need that much RAM too)

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

static uint32_t le32(const uint8_t *p) { return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24; }
static uint64_t le64(const uint8_t *p) { return (uint64_t)le32(p) | (uint64_t)le32(p + 4) << 32; }

// struct.unpack_from position check for `size` bytes at `off` of a buffer of `len` bytes.
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

// Reads a whole file (bounded by IMAGE_CAP). A directory is an I/O error, as open() of one is in Python.
static int read_file(ctx_t *x, const char *path, uint8_t **data, size_t *len) {
    struct stat sb;
    if (stat(path, &sb) == 0 && S_ISDIR(sb.st_mode)) return fail(x, RB_S2ARM_MODULES_IO, "%s is a directory", path);
    FILE *f = fopen(path, "rb");
    if (!f) return fail(x, RB_S2ARM_MODULES_IO, "cannot open %s: %s", path, strerror(errno));
    uint8_t *buf = NULL;
    size_t n = 0, cap = 0;
    for (;;) {
        if (!vec_reserve((void **)&buf, &cap, n + 65536 + 1, 1)) {
            free(buf);
            fclose(f);
            return fail(x, RB_S2ARM_MODULES_IO, "out of memory reading %s", path);
        }
        size_t got = fread(buf + n, 1, 65536, f);
        n += got;
        if (n > IMAGE_CAP) {
            free(buf);
            fclose(f);
            return fail(x, RB_S2ARM_MODULES_INVALID, "%s is larger than 1 GiB", path);
        }
        if (got < 65536) break;
    }
    int bad = ferror(f);
    fclose(f);
    if (bad) {
        free(buf);
        return fail(x, RB_S2ARM_MODULES_IO, "cannot read %s", path);
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

// ---------- nso(): the module image ----------

typedef struct {
    uint8_t *p;
    size_t n, cap;
} img_t;

// bytearray slice assignment img[mo:mo+sz] = data (the slice is clamped to the image; the image is resized).
static int splice(ctx_t *x, img_t *img, uint32_t mo, uint32_t sz, const uint8_t *data, size_t dlen) {
    uint64_t start = mo < img->n ? mo : img->n;
    uint64_t stop = (uint64_t)mo + sz;
    if (stop > img->n) stop = img->n;
    uint64_t newlen = img->n - (stop - start) + dlen;
    if (newlen > IMAGE_CAP) return fail(x, RB_S2ARM_MODULES_INVALID, "NSO image larger than 1 GiB");
    if (!vec_reserve((void **)&img->p, &img->cap, (size_t)newlen + 1, 1)) return fail(x, RB_S2ARM_MODULES_IO, "out of memory");
    memmove(img->p + start + dlen, img->p + stop, img->n - (size_t)stop);
    if (dlen) memcpy(img->p + start, data, dlen);
    img->n = (size_t)newlen;
    return 0;
}

static int nso_image(ctx_t *x, const char *name, const uint8_t *d, size_t len, img_t *img) {
    if (len < 0x6C) return fail(x, RB_S2ARM_MODULES_INVALID, "%s: NSO header too short", name);
    uint32_t flags = le32(d + 0xC), seg[3][3], csz[3];
    for (int k = 0; k < 3; k++) {
        for (int j = 0; j < 3; j++) seg[k][j] = le32(d + 0x10 + k * 0x10 + j * 4);
        csz[k] = le32(d + 0x60 + k * 4);
    }
    uint64_t initial = (uint64_t)seg[2][1] + seg[2][2];   // bytearray(segs[2][1] + segs[2][2]): the image without bss
    if (initial > IMAGE_CAP) return fail(x, RB_S2ARM_MODULES_INVALID, "%s: NSO image larger than 1 GiB", name);
    img->p = calloc((size_t)initial + 1, 1);
    if (!img->p) return fail(x, RB_S2ARM_MODULES_IO, "out of memory");
    img->n = (size_t)initial;
    img->cap = (size_t)initial + 1;
    for (int k = 0; k < 3; k++) {
        uint32_t fo = seg[k][0], mo = seg[k][1], sz = seg[k][2];
        const uint8_t *data = d;
        size_t dlen = 0;
        if (fo < len) {   // raw = d[fo:fo+csz[i]] clamps to the file
            data = d + fo;
            dlen = len - fo < csz[k] ? len - fo : csz[k];
        }
        uint8_t *plain = NULL;
        if (flags >> k & 1) {   // lz4.block.decompress(raw, uncompressed_size=sz); a shorter result is accepted
            if (sz > IMAGE_CAP || dlen > (size_t)INT32_MAX) return fail(x, RB_S2ARM_MODULES_INVALID, "%s: NSO segment %d too large", name, k);
            plain = malloc(sz ? sz : 1);
            if (!plain) return fail(x, RB_S2ARM_MODULES_IO, "out of memory");
            int got = LZ4_decompress_safe((const char *)data, (char *)plain, (int)dlen, (int)sz);
            if (got < 0) {
                free(plain);
                return fail(x, RB_S2ARM_MODULES_INVALID, "%s: NSO segment %d: LZ4 data is corrupt", name, k);
            }
            data = plain;
            dlen = (size_t)got;
        }
        int st = splice(x, img, mo, sz, data, dlen);
        free(plain);
        if (st) return st;
    }
    return 0;
}

// ---------- nso_syms.dynsyms(): only whether it raises ----------

// Reads the dynamic segment (up to 4096 entries, first entry per tag wins, 0 ends it); only tags 4, 5, 6 matter.
static int dyn_read(const uint8_t *img, size_t len, int64_t dyn, int wide, uint64_t val[7], int have[7]) {
    size_t step = wide ? 16 : 8;
    for (int i = 0; i < 7; i++) have[i] = 0;
    for (int64_t i = 0; i < 4096; i++) {
        size_t pos;
        if (!rd_pos(len, dyn + i * (int64_t)step, step, &pos)) return 0;
        int64_t tag = wide ? (int64_t)le64(img + pos) : (int64_t)(int32_t)le32(img + pos);
        uint64_t value = wide ? le64(img + pos + 8) : le32(img + pos + 4);
        if (tag == 0) break;
        if (tag >= 4 && tag <= 6 && !have[tag]) {
            have[tag] = 1;
            val[tag] = value;
        }
    }
    return 1;
}

static int dynsyms_ok(const uint8_t *img, size_t len) {
    size_t pos;
    if (!rd_pos(len, 4, 4, &pos)) return 0;
    uint64_t mod0 = le32(img + pos);
    if (mod0 + 4 > len || memcmp(img + mod0, "MOD0", 4)) return 0;   // assert img[mod0:mod0+4] == b'MOD0'
    if (!rd_pos(len, (int64_t)mod0 + 4, 4, &pos)) return 0;
    int64_t dyn = (int64_t)mod0 + (int32_t)le32(img + pos);
    uint64_t val[7] = {0};
    int have[7];
    if (!dyn_read(img, len, dyn, 1, val, have)) return 0;
    int wide = have[5] && have[6];
    if (!wide && !dyn_read(img, len, dyn, 0, val, have)) return 0;   // 32-bit module: Elf32_Dyn / Elf32_Sym
    if (!have[5] || !have[6]) return 0;                               // KeyError
    uint64_t symtab = val[6], strtab = val[5];
    uint64_t ent = wide ? 24 : 16, n;
    if (have[4]) {
        if (val[4] > len || val[4] + 4 > len || len - (val[4] + 4) < 4) return 0;
        n = le32(img + val[4] + 4);
    } else {
        n = strtab >= symtab ? (strtab - symtab) / ent : 0;
    }
    for (uint64_t i = 1; i < n; i++) {
        if (symtab > len || i * ent > len - symtab) return 0;
        uint64_t off = symtab + i * ent;
        if (len - off < ent) return 0;
        uint32_t name = le32(img + off);
        if (strtab > UINT64_MAX - name) return 0;
        uint64_t start = strtab + name;
        if (start >= len || !memchr(img + start, 0, len - (size_t)start)) return 0;   // img.index(b'\0', start)
    }
    return 1;
}

// ---------- kind(): the smallest NintendoSDK component name ----------

static int is_word(uint8_t c) { return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || c == '_'; }

// re.findall(rb'NintendoSDK_(?!nnSdk)\w+-[0-9_]+', img), each match cut at its last '-'; sorted(comps)[0] is the
// smallest. \w+ cannot contain '-', so no backtracking into it can help and the match is decided by the run.
static int is_gpu_driver(const uint8_t *img, size_t len) {
    static const char prefix[] = "NintendoSDK_";
    const size_t plen = sizeof prefix - 1;
    size_t best = 0, best_len = 0;
    int have = 0;
    size_t p = 0;
    while (p + plen <= len) {
        const uint8_t *hit = memchr(img + p, 'N', len - plen + 1 - p);
        if (!hit) break;
        p = (size_t)(hit - img);
        if (memcmp(img + p, prefix, plen)) {
            p++;
            continue;
        }
        size_t q = p + plen;
        if (q + 5 <= len && !memcmp(img + q, "nnSdk", 5)) {
            p++;
            continue;
        }
        size_t r = q;
        while (r < len && is_word(img[r])) r++;
        if (r == q || r >= len || img[r] != '-') {
            p++;
            continue;
        }
        size_t s = r + 1, t = s;
        while (t < len && (img[t] == '_' || (img[t] >= '0' && img[t] <= '9'))) t++;
        if (t == s) {
            p++;
            continue;
        }
        size_t clen = r - p;
        if (!have) {
            have = 1;
            best = p;
            best_len = clen;
        } else {
            size_t m = clen < best_len ? clen : best_len;
            int c = memcmp(img + p, img + best, m);
            if (c < 0 || (c == 0 && clen < best_len)) {
                best = p;
                best_len = clen;
            }
        }
        p = t;
    }
    if (!have) return 0;   // no component: kind() is GLSLC, an nn:: area or '?', never a driver
    return best_len == 18 && (!memcmp(img + best, "NintendoSDK_OpenGL", 18) || !memcmp(img + best, "NintendoSDK_Vulkan", 18));
}

// ---------- gpu_driver_modules ----------

static int cmp_names(const void *a, const void *b) { return strcmp(*(char *const *)a, *(char *const *)b); }

int rb_s2arm_gpu_drivers(const char *exefs_dir, const char *output_path, char *error, size_t error_size) {
    ctx_t x = {error, error_size};
    if (error && error_size) error[0] = 0;
    if (!exefs_dir || !output_path) return fail(&x, RB_S2ARM_MODULES_INVALID, "missing path");
    char **names = NULL;
    size_t nnames = 0, ncap = 0;
    char *out = NULL;
    size_t outn = 0, outcap = 0;
    int st = 0;
    DIR *dir = opendir(exefs_dir);
    if (!dir) return fail(&x, RB_S2ARM_MODULES_IO, "cannot read directory %s: %s", exefs_dir, strerror(errno));
    for (struct dirent *e; (e = readdir(dir));) {
        if (!strcmp(e->d_name, ".") || !strcmp(e->d_name, "..")) continue;
        if (!vec_reserve((void **)&names, &ncap, nnames + 1, sizeof *names) || !(names[nnames] = strdup(e->d_name))) {
            st = fail(&x, RB_S2ARM_MODULES_IO, "out of memory");
            break;
        }
        nnames++;
    }
    closedir(dir);
    if (st) goto done;
    qsort(names, nnames, sizeof *names, cmp_names);   // sorted(Path(exefs).iterdir()): same directory, so by name
    for (size_t i = 0; i < nnames; i++) {
        const char *name = names[i];
        if (!strcmp(name, "main") || !strcmp(name, "sdk") || !strcmp(name, "rtld")) continue;
        size_t plen = strlen(exefs_dir) + 1 + strlen(name) + 1;
        char *path = malloc(plen);
        if (!path) {
            st = fail(&x, RB_S2ARM_MODULES_IO, "out of memory");
            goto done;
        }
        snprintf(path, plen, "%s/%s", exefs_dir, name);
        uint8_t *data = NULL;
        size_t len = 0;
        st = read_file(&x, path, &data, &len);   // the original reads 4 bytes first; a whole read fails the same way
        free(path);
        if (st) goto done;
        if (len < 4 || memcmp(data, "NSO0", 4)) {
            free(data);
            continue;
        }
        img_t img = {0};
        st = nso_image(&x, name, data, len, &img);
        free(data);
        int driver = 0;
        if (!st) {
            if (!dynsyms_ok(img.p, img.n)) st = fail(&x, RB_S2ARM_MODULES_INVALID, "%s: malformed dynamic symbol table", name);
            else driver = is_gpu_driver(img.p, img.n);
        }
        free(img.p);
        if (st) goto done;
        if (driver) {
            size_t nl = strlen(name);
            if (!vec_reserve((void **)&out, &outcap, outn + nl + 2, 1)) {
                st = fail(&x, RB_S2ARM_MODULES_IO, "out of memory");
                goto done;
            }
            memcpy(out + outn, name, nl);
            out[outn + nl] = '\n';
            outn += nl + 1;
        }
    }
    if (!outn) {   // print('\n'.join([])) writes one LF
        if (!vec_reserve((void **)&out, &outcap, 2, 1)) {
            st = fail(&x, RB_S2ARM_MODULES_IO, "out of memory");
            goto done;
        }
        out[outn++] = '\n';
    }
    if (!mkdir_parents(output_path)) {
        st = fail(&x, RB_S2ARM_MODULES_IO, "cannot create the directory of %s", output_path);
        goto done;
    }
    {
        FILE *f = fopen(output_path, "wb");
        if (!f) {
            st = fail(&x, RB_S2ARM_MODULES_IO, "cannot write %s: %s", output_path, strerror(errno));
            goto done;
        }
        size_t wrote = fwrite(out, 1, outn, f);
        int closed = fclose(f);
        if (wrote != outn || closed != 0) st = fail(&x, RB_S2ARM_MODULES_IO, "cannot write %s", output_path);
    }
done:
    for (size_t i = 0; i < nnames; i++) free(names[i]);
    free(names);
    free(out);
    return st;
}
