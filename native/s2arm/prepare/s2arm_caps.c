// See s2arm_caps.h. Port of S2Arm pack/gen_caps.sh, tools/caps_policy.py (decide, sources,
// engine_l1) and graphics/nvn/games/profile_guess.py (nso, facts_of, guess, engine) with
// graphics/nvn/tools/nso_syms.py (dynsyms) and the graphics/nvn/tools/romfs_list.py walk.
// engine_l1 is True only when the facts are read without any Python exception and the engine
// rule matches; every place the original can raise (struct.error, AssertionError, KeyError,
// ValueError from bytes.index, LZ4BlockError, OSError) is a check here that makes it False.
// Deliberate differences: a module image above 1 GiB counts as an exception (Python would try to
// allocate it); RomFS files are not opened (the original reads their first 32 bytes and treats an
// unreadable one as an exception; the resource pack reads every file anyway and fails on it);
// cpatch.tsv with double quotes and file names with non-ASCII white space are refused / not folded.
#define _POSIX_C_SOURCE 200809L
#include "s2arm_caps.h"
#include "lz4.h"

#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#define IMAGE_CAP ((uint64_t)1 << 30)
#define MAX_DEPTH 256

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

static uint32_t le32(const uint8_t *p) { return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24; }
static uint64_t le64(const uint8_t *p) { return (uint64_t)le32(p) | (uint64_t)le32(p + 4) << 32; }

static char *pjoin(const char *a, const char *b) {
    size_t la = strlen(a), lb = strlen(b);
    char *p = malloc(la + lb + 2);
    if (!p) return NULL;
    memcpy(p, a, la);
    size_t k = la;
    if (la && a[la - 1] != '/') p[k++] = '/';
    memcpy(p + k, b, lb + 1);
    return p;
}
static int exists(const char *p) {
    struct stat st;
    return stat(p, &st) == 0;
}
static int is_dir(const char *p) {
    struct stat st;
    return stat(p, &st) == 0 && S_ISDIR(st.st_mode);
}

typedef struct {
    char **v;
    size_t n, cap;
} list_t;
static void list_free(list_t *l) {
    for (size_t i = 0; i < l->n; i++) free(l->v[i]);
    free(l->v);
    memset(l, 0, sizeof *l);
}
static int cmp_str(const void *a, const void *b) { return strcmp(*(char *const *)a, *(char *const *)b); }
static int listdir(const char *path, list_t *out) {   // sorted names; -1 unreadable, -2 out of memory
    DIR *d = opendir(path);
    if (!d) return -1;
    struct dirent *e;
    int ok = 1;
    while (ok && (e = readdir(d))) {
        if (!strcmp(e->d_name, ".") || !strcmp(e->d_name, "..")) continue;
        if (out->n == out->cap) {
            size_t cap = out->cap ? out->cap * 2 : 32;
            char **nv = realloc(out->v, cap * sizeof *nv);
            if (!nv) {
                ok = 0;
                break;
            }
            out->v = nv;
            out->cap = cap;
        }
        size_t l = strlen(e->d_name) + 1;
        char *s = malloc(l);
        if (!s) ok = 0;
        else {
            memcpy(s, e->d_name, l);
            out->v[out->n++] = s;
        }
    }
    closedir(d);
    if (!ok) return -2;
    if (out->n) qsort(out->v, out->n, sizeof *out->v, cmp_str);
    return 0;
}

// Reads a whole regular file of at most cap bytes. 0, -1 cannot open / not a regular file / read error, -2 above cap.
static int read_file(const char *path, uint64_t cap, uint8_t **data, size_t *len) {
    int fd = open(path, O_RDONLY | O_NONBLOCK);
    if (fd < 0) return -1;
    struct stat st;
    if (fstat(fd, &st) || !S_ISREG(st.st_mode)) {
        close(fd);
        return -1;
    }
    if ((uint64_t)st.st_size > cap) {
        close(fd);
        return -2;
    }
    size_t want = (size_t)st.st_size, n = 0;
    uint8_t *b = malloc(want + 1);
    if (!b) {
        close(fd);
        return -1;
    }
    for (;;) {
        ssize_t k = read(fd, b + n, want + 1 - n);
        if (k < 0 && errno == EINTR) continue;
        if (k < 0) {
            free(b);
            close(fd);
            return -1;
        }
        if (k == 0) break;
        n += (size_t)k;
        if (n > want) {
            free(b);
            close(fd);
            return -2;
        }
    }
    close(fd);
    *data = b;
    *len = n;
    return 0;
}

// ---------------- profile_guess.nso: the image, with Python bytearray slice-assignment semantics ----------------
typedef struct {
    uint8_t *p;
    size_t n, cap;
} img_t;

static int img_assign(img_t *im, uint64_t mo, uint64_t sz, const uint8_t *data, size_t dn) {   // img[mo:mo+sz] = data
    size_t start = mo < im->n ? (size_t)mo : im->n, stop = mo + sz < im->n ? (size_t)(mo + sz) : im->n;
    if (stop < start) stop = start;
    uint64_t nn = (uint64_t)im->n - (stop - start) + dn;
    if (nn > IMAGE_CAP) return -1;
    if (nn > im->cap) {
        uint8_t *np = realloc(im->p, (size_t)nn + 1);
        if (!np) return -1;
        im->p = np;
        im->cap = (size_t)nn;
    }
    memmove(im->p + start + dn, im->p + stop, im->n - stop);
    if (dn) memcpy(im->p + start, data, dn);
    im->n = (size_t)nn;
    return 0;
}

// 0 = the image, -1 = the original raises (or the image is above the cap).
static int nso_image(const uint8_t *d, size_t len, img_t *im) {
    if (len < 0x6C) return -1;   // struct.unpack_from at 0x0C, 0x10..0x3B, 0x60..0x6B
    uint32_t flags = le32(d + 0x0C);
    uint32_t fo[3], mo[3], sz[3], csz[3];
    for (int i = 0; i < 3; i++) {
        fo[i] = le32(d + 0x10 + 0x10 * i);
        mo[i] = le32(d + 0x14 + 0x10 * i);
        sz[i] = le32(d + 0x18 + 0x10 * i);
        csz[i] = le32(d + 0x60 + 4 * i);
    }
    uint64_t initial = (uint64_t)mo[2] + sz[2];
    if (initial > IMAGE_CAP) return -1;
    im->p = calloc(1, (size_t)initial + 1);
    if (!im->p) return -1;
    im->n = im->cap = (size_t)initial;
    for (int i = 0; i < 3; i++) {
        size_t start = fo[i] < len ? fo[i] : len, end = (uint64_t)fo[i] + csz[i] < len ? (size_t)(fo[i] + csz[i]) : len;
        size_t rl = end > start ? end - start : 0;
        const uint8_t *raw = d + start;
        if ((flags >> i) & 1) {   // python-lz4 block decompress with uncompressed_size = sz
            if (sz[i] > 0x7FFFFFFFu || rl > 0x7FFFFFFFu || sz[i] > IMAGE_CAP) return -1;
            uint8_t *out = malloc(sz[i] ? sz[i] : 1);
            if (!out) return -1;
            int got = LZ4_decompress_safe((const char *)raw, (char *)out, (int)rl, (int)sz[i]);
            int r = got < 0 ? -1 : img_assign(im, mo[i], sz[i], out, (size_t)got);
            free(out);
            if (r) return -1;
        } else if (img_assign(im, mo[i], sz[i], raw, rl))
            return -1;
    }
    return 0;
}

// struct.unpack_from bounds with Python's negative offsets (counted from the end).
static int at(const img_t *im, int64_t off, size_t size, size_t *out) {
    int64_t n = (int64_t)im->n;
    if (off < 0) {
        if (off + n < 0) return 0;
        off += n;
    }
    if ((uint64_t)off + size > (uint64_t)n) return 0;
    *out = (size_t)off;
    return 1;
}

// nso_syms.dynsyms: 1 = parses, 0 = raises.
static int dynsyms_ok(const img_t *im) {
    size_t o;
    if (!at(im, 4, 4, &o)) return 0;
    uint64_t mod0 = le32(im->p + o);
    if (mod0 + 4 > im->n || memcmp(im->p + mod0, "MOD0", 4)) return 0;   // the slice is shorter or differs: AssertionError
    if (!at(im, (int64_t)mod0 + 4, 4, &o)) return 0;
    int64_t dyn = (int64_t)mod0 + (int32_t)le32(im->p + o);
    int have[3] = {0, 0, 0};   // tags 4, 5, 6
    uint64_t val[3] = {0, 0, 0};
    int b32 = 0;
    for (int pass = 0; pass < 2; pass++) {
        int step = pass ? 8 : 16;
        memset(have, 0, sizeof have);
        for (int i = 0; i < 4096; i++) {
            if (!at(im, dyn + (int64_t)i * step, (size_t)step, &o)) return 0;
            int64_t t = pass ? (int64_t)(int32_t)le32(im->p + o) : (int64_t)le64(im->p + o);
            uint64_t v = pass ? le32(im->p + o + 4) : le64(im->p + o + 8);
            if (t == 0) break;
            if (t >= 4 && t <= 6 && !have[t - 4]) have[t - 4] = 1, val[t - 4] = v;   // setdefault: the first one counts
        }
        if (pass == 0) {
            b32 = !have[2] || !have[1];
            if (!b32) break;
        }
    }
    if (!have[2] || !have[1]) return 0;   // tags[6], tags[5]: KeyError
    uint64_t symtab = val[2], strtab = val[1];
    int64_t ent = b32 ? 16 : 24, n;
    if (have[0]) {
        if (val[0] > (uint64_t)INT64_MAX - 4 || !at(im, (int64_t)val[0] + 4, 4, &o)) return 0;
        n = le32(im->p + o);
    } else {
        if (symtab > (uint64_t)INT64_MAX || strtab > (uint64_t)INT64_MAX) return 0;
        int64_t diff = (int64_t)strtab - (int64_t)symtab;
        n = diff >= 0 ? diff / ent : -((-diff + ent - 1) / ent);   // floor division
    }
    for (int64_t i = 1; i < n; i++) {
        if (symtab > (uint64_t)INT64_MAX / 2 || !at(im, (int64_t)symtab + i * ent, (size_t)ent, &o)) return 0;
        uint64_t name = le32(im->p + o);
        uint64_t s = strtab + name;   // img.index(b'\0', strtab + name)
        if (strtab > (uint64_t)INT64_MAX / 2 || s >= im->n || !memchr(im->p + s, 0, im->n - s)) return 0;
    }
    return 1;
}

static int contains(const uint8_t *h, size_t n, const char *needle) {
    size_t k = strlen(needle);
    for (size_t i = 0; k <= n && i + k <= n; i++)
        if (h[i] == (uint8_t)needle[0] && !memcmp(h + i, needle, k)) return 1;
    return 0;
}
static int ue4_marker(const uint8_t *h, size_t n) {   // re (?<![A-Za-z])UE4
    for (size_t i = 0; i + 3 <= n; i++)
        if (h[i] == 'U' && h[i + 1] == 'E' && h[i + 2] == '4') {
            if (!i) return 1;
            uint8_t c = h[i - 1];
            if (!((c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z'))) return 1;
        }
    return 0;
}

// profile_guess.npdm: 1 = no exception.
static int npdm_ok(const char *path) {
    if (!exists(path)) return 1;   // (0, None) without the file
    uint8_t *d = NULL;
    size_t n = 0;
    if (read_file(path, IMAGE_CAP, &d, &n)) return 0;
    int ok = 1;
    if (n >= 4 && !memcmp(d, "META", 4) && n < 0x18) ok = 0;   // unpack_from('<I', d, 0x14)
    for (size_t a = 0; ok && a + 4 <= n; a++)                    // d.find(b'ACI0'), then unpack_from('<Q', d, a + 0x10)
        if (!memcmp(d + a, "ACI0", 4)) {
            ok = a + 0x18 <= n;
            break;
        }
    free(d);
    return ok;
}

// os.path.splitext(path)[1].lower() is ".pak" or ".utoc" (leading dots of the name do not start an extension;
// KELVIN SIGN is the one non-ASCII character Python lowers to one of these letters).
static int engine_ext(const char *name) {
    const char *dot = strrchr(name, '.');
    if (!dot) return 0;
    const char *p = name;
    while (p < dot && *p == '.') p++;
    if (p == dot) return 0;
    char low[8];
    size_t k = 0;
    for (const unsigned char *c = (const unsigned char *)dot; *c; c++) {
        if (k >= 6) return 0;
        if (c[0] == 0xE2 && c[1] == 0x84 && c[2] == 0xAA) {
            low[k++] = 'k';
            c += 2;
            continue;
        }
        if (*c >= 0x80) return 0;
        low[k++] = (char)(*c >= 'A' && *c <= 'Z' ? *c + 32 : *c);
    }
    low[k] = 0;
    return !strcmp(low, ".pak") || !strcmp(low, ".utoc");
}

// romfs_files over a RomFS folder with the romfs_list rules: 1 = no exception; *pak set when a file has the extension.
static int romfs_scan(const char *dir, int depth, int *pak) {
    if (depth > MAX_DEPTH) return 0;
    list_t names = {0};
    int r = listdir(dir, &names);
    if (r == -1) return 1;   // an unreadable directory is skipped
    if (r) return 0;
    int ok = 1;
    for (size_t i = 0; i < names.n && ok; i++) {
        const char *nm = names.v[i];
        char *p = pjoin(dir, nm);
        if (!p) {
            ok = 0;
            break;
        }
        struct stat ls, st;
        int lok = lstat(p, &ls) == 0, sok = stat(p, &st) == 0;
        int realdir = lok && S_ISDIR(ls.st_mode), walkdir = sok && S_ISDIR(st.st_mode);
        if (!realdir && (!strcmp(nm, ".DS_Store") || !strncmp(nm, "._", 2))) {
            free(p);
            continue;   // macOS junk is left out of the walk
        }
        if (walkdir) {
            if (realdir) ok = romfs_scan(p, depth + 1, pak);   // symlinked directories are not entered
        } else if (!(sok && S_ISREG(st.st_mode)))
            ok = 0;   // not a regular file once followed: IsADirectoryError / FileNotFoundError
        else if (engine_ext(nm))
            *pak = 1;
        free(p);
    }
    list_free(&names);
    return ok;
}

// caps_policy.engine_l1: profile_guess facts_of + guess + engine, any exception = False.
static int engine_l1(const char *root) {
    char *ex = pjoin(root, "exefs"), *rf = pjoin(root, "romfs");
    int result = 0;
    if (!ex || !rf || !is_dir(ex) || !exists(rf)) goto done;
    list_t names = {0};
    if (listdir(ex, &names)) goto done;   // iterdir of an unreadable folder raises
    int ok = 1, have_main = 0, unity = 0, unreal = 0;
    for (size_t i = 0; i < names.n && ok; i++) {
        char *p = pjoin(ex, names.v[i]);
        uint8_t *d = NULL;
        size_t n = 0;
        int r = p ? read_file(p, IMAGE_CAP, &d, &n) : -1;
        free(p);
        if (r) {
            ok = 0;   // open() of a directory / unreadable entry raises (a module above 1 GiB counts the same)
            break;
        }
        if (n >= 4 && !memcmp(d, "NSO0", 4)) {
            img_t im = {0};
            if (nso_image(d, n, &im) || !dynsyms_ok(&im)) ok = 0;
            else if (!strcmp(names.v[i], "main")) {
                have_main = 1;
                unity = contains(im.p, im.n, "UnityEngine") || contains(im.p, im.n, "global-metadata.dat");
                unreal = contains(im.p, im.n, "Unreal") || ue4_marker(im.p, im.n);
            }
            free(im.p);
        }
        free(d);
    }
    list_free(&names);
    if (!ok || !have_main) goto done;   // guess(): mods['main'] KeyError without an NSO main
    char *npdm = pjoin(ex, "main.npdm");
    ok = npdm && npdm_ok(npdm);
    free(npdm);
    if (!ok) goto done;
    int pak = 0;
    if (is_dir(rf)) ok = romfs_scan(rf, 0, &pak);
    else ok = 0;   // a RomFS manifest file instead of a folder: not supported, counted as an exception
    if (!ok) goto done;
    result = unity || (unreal && pak);
done:
    free(ex);
    free(rf);
    return result;
}

// ---------------- caps_policy.sources ----------------
static int utf8_ok(const uint8_t *s, size_t n) {
    size_t i = 0;
    while (i < n) {
        uint8_t c = s[i], lo = 0x80, hi = 0xBF;
        size_t need;
        if (c < 0x80) {
            i++;
            continue;
        } else if (c >= 0xC2 && c <= 0xDF) need = 1;
        else if (c == 0xE0) need = 2, lo = 0xA0;
        else if (c == 0xED) need = 2, hi = 0x9F;
        else if (c >= 0xE1 && c <= 0xEF) need = 2;
        else if (c == 0xF0) need = 3, lo = 0x90;
        else if (c == 0xF4) need = 3, hi = 0x8F;
        else if (c >= 0xF1 && c <= 0xF3) need = 3;
        else return 0;
        if (n - i - 1 < need) return 0;
        for (size_t k = 1; k <= need; k++) {
            uint8_t d = s[i + k];
            if (d < (k == 1 ? lo : 0x80) || d > (k == 1 ? hi : 0xBF)) return 0;
        }
        i += need + 1;
    }
    return 1;
}

// cpatch.tsv rows (csv.DictReader, tab, lines starting with # left out): *ws / *fps when a 编号 starts with
// "widescreen:" / "fps:". 0, or an error code when the original raises.
static int cpatch(ctx_t *x, const char *path, int *ws, int *fps) {
    *ws = *fps = 0;
    if (!exists(path)) return 0;
    uint8_t *d = NULL;
    size_t n = 0;
    if (read_file(path, IMAGE_CAP, &d, &n)) return fail(x, RB_S2ARM_CAPS_INVALID, "cannot read cpatch.tsv");
    int code = 0;
    if (!utf8_ok(d, n)) code = fail(x, RB_S2ARM_CAPS_INVALID, "cpatch.tsv is not UTF-8");
    else if (memchr(d, '"', n)) code = fail(x, RB_S2ARM_CAPS_INVALID, "cpatch.tsv with double quotes is not supported");
    static const char key[] = "\xe7\xbc\x96\xe5\x8f\xb7";   // 编号
    int column = -2;   // -2: header not read yet; -1: the header has no such column; else its index (the last one, as a dict keeps)
    for (size_t i = 0; i < n && !code;) {
        size_t j = i;
        while (j < n && d[j] != '\n' && d[j] != '\r') j++;
        size_t next = j < n ? (d[j] == '\r' && j + 1 < n && d[j + 1] == '\n' ? j + 2 : j + 1) : j;
        if (j == i || d[i] == '#') {   // empty rows are skipped by DictReader, # lines are filtered out before it
            i = next;
            continue;
        }
        int field = 0, hit = -1;
        size_t a = i;
        for (size_t k = i; k <= j; k++)
            if (k == j || d[k] == '\t') {
                if (column == -2 && k - a == sizeof key - 1 && !memcmp(d + a, key, sizeof key - 1)) hit = field;
                if (column >= 0 && field == column) {
                    if (k - a >= 11 && !memcmp(d + a, "widescreen:", 11)) *ws = 1;
                    if (k - a >= 4 && !memcmp(d + a, "fps:", 4)) *fps = 1;
                }
                field++;
                a = k + 1;
            }
        if (column == -2) column = hit;
        else if (column >= 0 && field <= column)
            code = fail(x, RB_S2ARM_CAPS_INVALID, "cpatch.tsv row shorter than its header (the original raises)");
        i = next;
    }
    free(d);
    return code;
}

static int nonempty_table(ctx_t *x, const char *path, int *yes) {   // any line with text that does not start with #
    *yes = 0;
    uint8_t *d = NULL;
    size_t n = 0;
    if (read_file(path, IMAGE_CAP, &d, &n)) return fail(x, RB_S2ARM_CAPS_INVALID, "cannot read %s", path);
    for (size_t i = 0; i < n && !*yes;) {
        size_t j = i;
        while (j < n && d[j] != '\n' && d[j] != '\r') j++;
        int text = 0;
        for (size_t k = i; k < j && !text; k++) text = !(d[k] == ' ' || (d[k] >= '\t' && d[k] <= '\r') || (d[k] >= 0x1c && d[k] <= 0x1f));
        if (text && d[i] != '#') *yes = 1;
        i = j < n ? (d[j] == '\r' && j + 1 < n && d[j + 1] == '\n' ? j + 2 : j + 1) : j;
    }
    free(d);
    return 0;
}

typedef struct {
    char *p;
    size_t n, cap;
} sb_t;
static int sb_add(sb_t *s, const char *t) {
    size_t n = strlen(t);
    if (s->n + n + 1 > s->cap) {
        size_t cap = s->cap ? s->cap : 256;
        while (cap < s->n + n + 1) cap *= 2;
        char *np = realloc(s->p, cap);
        if (!np) return 0;
        s->p = np;
        s->cap = cap;
    }
    memcpy(s->p + s->n, t, n + 1);
    s->n += n;
    return 1;
}

#define ZH_SEP "\xe3\x80\x81"   // 、
#define S_THIRD "\xe7\xac\xac\xe4\xb8\x89\xe5\xb1\x82\xe9\x80\x9a\xe7\x94\xa8\xe6\xbb\xa1\xe5\xb1\x8f"
#define S_CP_WIDE "\xe7\xa4\xbe\xe5\x8c\xba\xe5\xae\xbd\xe5\xb1\x8f\xe8\xa1\xa5\xe4\xb8\x81"
#define S_GEN_WIDE "\xe9\x80\x9a\xe7\x94\xa8\xe5\xae\xbd\xe5\xb1\x8f\xe6\x94\xb9\xe5\x86\x99"
#define S_CP_FPS "\xe7\xa4\xbe\xe5\x8c\xba\xe5\xb8\xa7\xe7\x8e\x87\xe8\xa1\xa5\xe4\xb8\x81"
#define S_ENGINE_L1 "\xe5\xbc\x95\xe6\x93\x8e\xe9\x80\x9a\xe7\x94\xa8\xe7\xac\xac\xe4\xb8\x80\xe5\xb1\x82\xef\xbc\x88Unity / UE4 \xe6\x94\xbe\xe5\xbc\x80\xe4\xba\xa4\xe6\x8d\xa2\xe9\x97\xb4\xe9\x9a\x94\xef\xbc\x89"
#define S_ENGINE_ALL                                                                                                                          \
    "\xe5\xbc\x95\xe6\x93\x8e\xe9\x80\x9a\xe7\x94\xa8\xef\xbc\x9a\xe6\x94\xbe\xe5\xbc\x80\xe5\x87\xba\xe5\x9b\xbe\xe9\x97\xb4\xe9\x9a\x94\xef\xbc\x88" \
    "\xe5\x85\xa8\xe5\xbc\x95\xe6\x93\x8e\xef\xbc\x8c\xe5\x90\x8c\xe5\xb1\x80 A/B \xe5\x88\xa4\xe7\xba\xa2\xe6\x89\x8d\xe5\x85\xb3\xef\xbc\x89"
#define S_DEFAULT_ON "\xe9\xbb\x98\xe8\xae\xa4\xe5\xbc\x80\xef\xbc\x9a\xe6\x9d\xa5\xe6\xba\x90 "
#define S_WIDEN_OFF                                                                                                                         \
    "\xe5\x8f\x91\xe5\xb8\x83\xe7\xbc\xba\xe7\x9c\x81\xe5\x85\xb3\xef\xbc\x88\xe7\xbb\xb4\xe6\x8a\xa4\xe8\x80\x85 11-02\xef\xbc\x9a\xe6\xbb\xa1" \
    "\xe5\xb1\x8f\xe9\xbb\x98\xe8\xae\xa4\xe5\x85\xb3\xe3\x80\x81"                                                                         \
    "16:9 \xe4\xb8\xa4\xe4\xbe\xa7\xe9\xbb\x91\xe8\xbe\xb9\xef\xbc\x8c\xe6\x9c\x89\xe8\xa1\xa5\xe4\xb8\x81\xe6\x88\x96\xe7\x9c\x9f\xe6\x9c\xba" \
    "\xe9\xaa\x8c\xe8\xbf\x87\xe7\x9a\x84\xe6\xac\xbe\xe6\x89\x8d\xe5\xbc\x80\xef\xbc\x89"

static void collapse_spaces(char *s) {   // ' '.join(s.replace('\t', ' ').split())
    char *w = s;
    int pending = 0;
    for (char *r = s; *r; r++) {
        if (*r == ' ' || (*r >= '\t' && *r <= '\r') || (*r >= 0x1c && *r <= 0x1f)) {
            pending = w != s;
            continue;
        }
        if (pending) *w++ = ' ';
        pending = 0;
        *w++ = *r;
    }
    *w = 0;
}

static int write_caps(ctx_t *x, const char *path, int all_caps, int widen, const char *widen_why, int fps, const char *fps_why, int display) {
    sb_t s = {0};
    // gen_caps.sh printf format (the comment line holds a literal backslash-t)
    int ok = sb_add(&s, "plat\tapple\n# \xe5\x8c\x85\xe5\x86\x85\xe8\x83\xbd\xe5\x8a\x9b\xe6\xb8\x85\xe5\x8d\x95\xef\xbc\x88") &&
             sb_add(&s, all_caps ? "--all-caps \xe5\x87\xba\xe5\x8c\x85\xef\xbc\x9a\xe6\x9c\x89\xe6\x9d\xa5\xe6\xba\x90\xe5\x8d\xb3\xe5\xbc\x80\xe3\x80\x81"
                                   "\xe4\xb8\x8d\xe7\x9c\x8b\xe5\xbc\xba\xe4\xbf\xa1\xe5\x8f\xb7"
                                 : "\xe5\x8f\x91\xe5\xb8\x83\xe5\x8c\x85\xef\xbc\x9a"
                                   "60 \xe5\xb8\xa7\xe9\xbb\x98\xe8\xae\xa4\xe5\xbc\x80\xe3\x80\x81\xe5\xbc\xba\xe4\xbf\xa1\xe5\x8f\xb7\xe6\x89\x8d\xe5\x85\xb3"
                                   "\xef\xbc\x9b\xe6\xbb\xa1\xe5\xb1\x8f\xe9\xbb\x98\xe8\xae\xa4\xe5\x85\xb3\xe3\x80\x81\xe7\x9c\x9f\xe6\x9c\xba\xe9\xaa\x8c"
                                   "\xe8\xbf\x87\xe6\x88\x96\xe6\x9c\x89\xe8\xa1\xa5\xe4\xb8\x81\xe6\x89\x8d\xe5\xbc\x80\xef\xbc\x88tools/caps_policy.py\xef\xbc\x89") &&
             sb_add(&s, "\xef\xbc\x89\n# \xe6\xa0\xbc\xe5\xbc\x8f\xef\xbc\x9a<\xe8\x83\xbd\xe5\x8a\x9b>\\t<\xe5\x80\xbc>\\t# <\xe5\x8e\x9f\xe5\x9b\xa0>"
                        "\xef\xbc\x88"
                        "1 = \xe5\xbc\x80\xef\xbc\x8c"
                        "0 = \xe6\x98\xbe\xe5\xbc\x8f\xe5\x85\xb3\xef\xbc\x89\xef\xbc\x9b\xe4\xbc\x98\xe5\x85\x88\xe7\xba\xa7\xef\xbc\x9a\xe5\x90\xaf"
                        "\xe5\x8a\xa8\xe7\x8e\xaf\xe5\xa2\x83 > Settings.bundle\xef\xbc\x88\xe7\x94\xa8\xe6\x88\xb7\xe6\x94\xb9\xe8\xbf\x87\xe7\x9a\x84"
                        "\xe8\xae\xbe\xe7\xbd\xae\xef\xbc\x89> \xe6\x9c\xac\xe6\x96\x87\xe4\xbb\xb6\nwiden\t") &&
             sb_add(&s, widen ? "1" : "0") && sb_add(&s, "\t# ") && sb_add(&s, widen_why) && sb_add(&s, "\nfps60\t") && sb_add(&s, fps ? "1" : "0") &&
             sb_add(&s, "\t# ") && sb_add(&s, fps_why) &&
             sb_add(&s, "\ndirect\t1\t# \xe7\x9b\xb4\xe8\xbf\x9e\xe5\x8f\xaf\xe7\x94\xa8\ngyro\t1\t# \xe5\xae\xbf\xe4\xb8\xbb\xe9\x80\x9a\xe7\x94\xa8\xe8\x83\xbd"
                        "\xe5\x8a\x9b\nhaptics\t1\t# \xe5\xae\xbf\xe4\xb8\xbb\xe9\x80\x9a\xe7\x94\xa8\xe8\x83\xbd\xe5\x8a\x9b\n") &&
             (!display || sb_add(&s, "fps60_display\t1\t# " S_ENGINE_ALL "\n"));
    int code = 0;
    if (!ok) code = fail(x, RB_S2ARM_CAPS_IO, "out of memory");
    else {
        FILE *f = fopen(path, "wb");
        int bad = !f || fwrite(s.p, 1, s.n, f) != s.n;
        if (f) bad |= fclose(f) != 0;
        if (bad) {
            unlink(path);
            code = fail(x, RB_S2ARM_CAPS_IO, "cannot write %s", path);
        }
    }
    free(s.p);
    return code;
}

int rb_s2arm_caps(const char *root, const char *release_path, const char *all_caps_path, int *engine_out, char *error, size_t error_size) {
    ctx_t x = {error, error_size};
    if (!root || !release_path) return fail(&x, RB_S2ARM_CAPS_INVALID, "incomplete request");
    list_t fs = {0};
    if (is_dir(root) && listdir(root, &fs) == -2) return fail(&x, RB_S2ARM_CAPS_IO, "out of memory");
    sb_t widen = {0}, fps = {0};
    int code = 0, ok = sb_add(&widen, S_THIRD);
    for (size_t i = 0; ok && i < fs.n; i++) {   // widen_enable.*.tsv (sorted)
        size_t l = strlen(fs.v[i]);
        if (!strncmp(fs.v[i], "widen_enable.", 13) && l >= 4 && !strcmp(fs.v[i] + l - 4, ".tsv")) ok = sb_add(&widen, ZH_SEP) && sb_add(&widen, fs.v[i]);
    }
    char *p = pjoin(root, "widen_verified.tsv");
    int verified = p && exists(p);
    free(p);
    if (ok && verified) ok = sb_add(&widen, ZH_SEP "widen_verified.tsv");
    for (size_t i = 0; ok && i < fs.n; i++) {
        size_t l = strlen(fs.v[i]);
        if (!strncmp(fs.v[i], "widen_full.", 11) && l >= 4 && !strcmp(fs.v[i] + l - 4, ".tsv")) ok = sb_add(&widen, ZH_SEP) && sb_add(&widen, fs.v[i]);
    }
    int cp_ws = 0, cp_fps = 0;
    p = pjoin(root, "cpatch.tsv");
    if (!p) ok = 0;
    else code = cpatch(&x, p, &cp_ws, &cp_fps);
    free(p);
    if (ok && !code && cp_ws) ok = sb_add(&widen, ZH_SEP S_CP_WIDE);
    int general = 0;
    for (size_t i = 0; ok && !code && i < fs.n && !general; i++) {
        size_t l = strlen(fs.v[i]);
        if (l < 10 || strcmp(fs.v[i] + l - 10, ".widen.tsv")) continue;
        char *q = pjoin(root, fs.v[i]);
        code = q ? nonempty_table(&x, q, &general) : fail(&x, RB_S2ARM_CAPS_IO, "out of memory");
        free(q);
    }
    if (ok && !code && general) ok = sb_add(&widen, ZH_SEP S_GEN_WIDE);
    p = pjoin(root, "fps.tsv");
    int fps_table = p && exists(p);
    free(p);
    int engine = 0, display = 0;
    if (ok && !code) {
        if (fps_table) ok = sb_add(&fps, "fps.tsv");
        if (ok && cp_fps) ok = sb_add(&fps, fps.n ? ZH_SEP S_CP_FPS : S_CP_FPS);
        if (ok && !fps.n && (engine = engine_l1(root))) ok = sb_add(&fps, S_ENGINE_L1);
        if (ok && !fps.n) {   // decide(): no source at all, the general rule (no A/B result for this game)
            ok = sb_add(&fps, S_ENGINE_ALL);
            display = 1;
        }
    }
    if (engine_out) *engine_out = engine;
    if (!ok && !code) code = fail(&x, RB_S2ARM_CAPS_IO, "out of memory");
    if (!code) {
        sb_t fps_why = {0}, widen_on = {0};
        ok = sb_add(&fps_why, S_DEFAULT_ON) && sb_add(&fps_why, fps.p) && sb_add(&widen_on, S_DEFAULT_ON) && sb_add(&widen_on, widen.p);
        if (!ok) code = fail(&x, RB_S2ARM_CAPS_IO, "out of memory");
        else {
            collapse_spaces(fps_why.p);
            collapse_spaces(widen_on.p);
            // release: widen off by default unless widen_verified.tsv; --all-caps: on with any source
            code = write_caps(&x, release_path, 0, verified, verified ? widen_on.p : S_WIDEN_OFF, 1, fps_why.p, display);
            if (!code && all_caps_path) code = write_caps(&x, all_caps_path, 1, 1, widen_on.p, 1, fps_why.p, display);
        }
        free(fps_why.p);
        free(widen_on.p);
    }
    free(widen.p);
    free(fps.p);
    list_free(&fs);
    return code;
}
