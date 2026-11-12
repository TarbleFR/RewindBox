// See s2arm_pack.h. Ports of S2Arm ios/embed.py, ios/macho_dylib.py, pack/ship_ext.py (container
// per-game files), pack/save_identity.py, pack/pkg_srcs.py (srcs), pack/pack.py,
// graphics/tools/direct/runtime_only_lib.sh and the bookkeeping of runtime/src/pack_apply.c
// (Apache-2.0, pinned commit in tools/s2arm_prototype/pin.json). Every assertion, red line and
// Python exception of the originals is an explicit check failing the call.
#if defined(__APPLE__)
#define _DARWIN_C_SOURCE
#else
#define _XOPEN_SOURCE 700   // realpath, symlink, pwrite
#endif
#include "s2arm_pack.h"
#include "s2arm_dirent.h"
#include "s2arm_sha256.h"

#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <time.h>
#include <unistd.h>

#define PG 0x4000            // 16 KiB: blocks, segments
#define CS_PAGE 4096         // code signature page
#define MAX_DEPTH 256
#define MAX_MODULES 512

typedef struct {
    char *error;
    size_t error_size;
    int (*cancelled)(void *context);
    void *context;
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
static int stop(ctx_t *x) { return x->cancelled && x->cancelled(x->context); }

static uint32_t le32(const uint8_t *p) { return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24; }
static uint64_t le64(const uint8_t *p) { return (uint64_t)le32(p) | (uint64_t)le32(p + 4) << 32; }

// ---------------- byte buffers, strings, paths ----------------
typedef struct {
    uint8_t *p;
    size_t n, cap;
} buf_t;

static int buf_add(buf_t *b, const void *data, size_t n) {
    if (b->n + n + 1 > b->cap) {
        size_t cap = b->cap ? b->cap : 256;
        while (cap < b->n + n + 1) cap *= 2;
        uint8_t *np = realloc(b->p, cap);
        if (!np) return 0;
        b->p = np;
        b->cap = cap;
    }
    if (n) memcpy(b->p + b->n, data, n);
    b->n += n;
    b->p[b->n] = 0;
    return 1;
}
static int buf_str(buf_t *b, const char *s) { return buf_add(b, s, strlen(s)); }
#if defined(__GNUC__)
__attribute__((format(printf, 2, 3)))
#endif
static int buf_fmt(buf_t *b, const char *fmt, ...) {
    char tmp[1024];
    va_list ap;
    va_start(ap, fmt);
    int n = vsnprintf(tmp, sizeof tmp, fmt, ap);
    va_end(ap);
    return n >= 0 && (size_t)n < sizeof tmp && buf_add(b, tmp, (size_t)n);
}
static int buf_u32(buf_t *b, uint32_t v) {
    uint8_t t[4] = {(uint8_t)v, (uint8_t)(v >> 8), (uint8_t)(v >> 16), (uint8_t)(v >> 24)};
    return buf_add(b, t, 4);
}
static int buf_u64(buf_t *b, uint64_t v) { return buf_u32(b, (uint32_t)v) && buf_u32(b, (uint32_t)(v >> 32)); }
static int buf_be32(buf_t *b, uint32_t v) {
    uint8_t t[4] = {(uint8_t)(v >> 24), (uint8_t)(v >> 16), (uint8_t)(v >> 8), (uint8_t)v};
    return buf_add(b, t, 4);
}
static int buf_be64(buf_t *b, uint64_t v) { return buf_be32(b, (uint32_t)(v >> 32)) && buf_be32(b, (uint32_t)v); }
static int buf_name16(buf_t *b, const char *s) {
    uint8_t t[16] = {0};
    size_t n = strlen(s);
    if (n > 16) return 0;
    memcpy(t, s, n);
    return buf_add(b, t, 16);
}

static char *sdup(const char *s) {
    size_t n = strlen(s) + 1;
    char *p = malloc(n);
    if (p) memcpy(p, s, n);
    return p;
}
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
static char *pcat(const char *a, const char *b) {   // a + b, no separator
    size_t la = strlen(a), lb = strlen(b);
    char *p = malloc(la + lb + 1);
    if (!p) return NULL;
    memcpy(p, a, la);
    memcpy(p + la, b, lb + 1);
    return p;
}

static int is_file(const char *p) {
    struct stat st;
    return stat(p, &st) == 0 && S_ISREG(st.st_mode);
}
static int is_dir(const char *p) {
    struct stat st;
    return stat(p, &st) == 0 && S_ISDIR(st.st_mode);
}
static int is_link(const char *p) {
    struct stat st;
    return lstat(p, &st) == 0 && S_ISLNK(st.st_mode);
}
static int exists(const char *p) {
    struct stat st;
    return stat(p, &st) == 0;
}
static int nonempty_file(const char *p) {   // [ -s p ] on a regular file
    struct stat st;
    return stat(p, &st) == 0 && S_ISREG(st.st_mode) && st.st_size > 0;
}

static int makedirs(const char *path) {   // os.makedirs(exist_ok=True)
    size_t n = strlen(path);
    char *p = malloc(n + 1);
    if (!p) return -1;
    memcpy(p, path, n + 1);
    for (size_t i = 1; i <= n; i++)
        if (p[i] == '/' || p[i] == 0) {
            char saved = p[i];
            p[i] = 0;
            if (mkdir(p, 0777) && errno != EEXIST) {
                free(p);
                return -1;
            }
            p[i] = saved;
        }
    int ok = is_dir(path);
    free(p);
    return ok ? 0 : -1;
}

static int rmtree(const char *path, int depth) {   // shutil.rmtree(ignore_errors=True); symlinks removed, never followed
    if (depth > MAX_DEPTH) return -1;
    struct stat st;
    if (lstat(path, &st)) return 0;
    if (!S_ISDIR(st.st_mode)) return unlink(path);
    DIR *d = opendir(path);
    if (d) {
        struct dirent *e;
        while ((e = readdir(d))) {
            if (!strcmp(e->d_name, ".") || !strcmp(e->d_name, "..")) continue;
            char *p = pjoin(path, e->d_name);
            if (p) rmtree(p, depth + 1);
            free(p);
        }
        closedir(d);
    }
    return rmdir(path);
}

static int read_all(const char *path, size_t cap, uint8_t **data, size_t *len) {   // 0, -1 unreadable / no memory, -2 too large
    FILE *f = fopen(path, "rb");
    if (!f) return -1;
    struct stat st;
    if (fstat(fileno(f), &st) || st.st_size < 0) {
        fclose(f);
        return -1;
    }
    if ((uint64_t)st.st_size > cap) {
        fclose(f);
        return -2;
    }
    size_t want = (size_t)st.st_size, n = 0, got;
    uint8_t *b = malloc(want + 1);
    if (!b) {
        fclose(f);
        return -1;
    }
    while (n <= want && (got = fread(b + n, 1, want + 1 - n, f)) > 0) n += got;
    int bad = ferror(f);
    fclose(f);
    if (bad || n > want) {
        free(b);
        return bad ? -1 : -2;
    }
    b[n] = 0;
    *data = b;
    *len = n;
    return 0;
}

static int write_all(const char *path, const void *data, size_t n) {
    FILE *f = fopen(path, "wb");
    if (!f) return -1;
    int bad = n && fwrite(data, 1, n, f) != n;
    bad |= fclose(f) != 0;
    if (bad) unlink(path);
    return bad ? -1 : 0;
}

// shutil.copyfile: contents only, symlinks followed, destination replaced. With hash: SHA-256 of the copy.
static int copy_file(ctx_t *x, const char *src, const char *dst, uint8_t hash[32]) {
    int in = open(src, O_RDONLY);
    if (in < 0) return -1;
    struct stat st;
    if (fstat(in, &st) || !S_ISREG(st.st_mode)) {
        close(in);
        return -1;
    }
    unlink(dst);
    int out = open(dst, O_WRONLY | O_CREAT | O_TRUNC, 0666);
    if (out < 0) {
        close(in);
        return -1;
    }
    static const size_t CHUNK = 1 << 20;
    char *block = malloc(CHUNK);
    s2arm_sha256_ctx h;
    s2arm_sha256_init(&h);
    int bad = !block;
    while (!bad) {
        ssize_t n = read(in, block, CHUNK);
        if (n < 0 && errno == EINTR) continue;
        if (n < 0) bad = 1;
        if (n <= 0) break;
        if (hash) s2arm_sha256_update(&h, block, (size_t)n);
        for (ssize_t done = 0; !bad && done < n;) {
            ssize_t w = write(out, block + done, (size_t)(n - done));
            if (w < 0 && errno == EINTR) continue;
            if (w < 0) bad = 1;
            else done += w;
        }
        if (stop(x)) bad = 2;
    }
    free(block);
    close(in);
    if (close(out)) bad = bad ? bad : 1;
    if (bad) {
        unlink(dst);
        return bad == 2 ? -5 : -1;
    }
    if (hash) s2arm_sha256_final(&h, hash);
    return 0;
}

// Relative path from directory `from` to `to` (both absolute and resolved), as os.path.relpath.
static char *relpath(const char *to, const char *from) {
    size_t i = 0, common = 0;
    while (to[i] && from[i] && to[i] == from[i]) {
        if (to[i] == '/') common = i;
        i++;
    }
    if ((!to[i] || to[i] == '/') && (!from[i] || from[i] == '/')) common = i;
    buf_t b = {0};
    const char *rest = from + common;
    while (*rest == '/') rest++;
    int ok = 1;
    while (*rest && ok) {   // one ".." per remaining component of `from`
        ok = buf_str(&b, b.n ? "/.." : "..");
        const char *slash = strchr(rest, '/');
        rest = slash ? slash + 1 : rest + strlen(rest);
        while (*rest == '/') rest++;
    }
    const char *tail = to + common;
    while (*tail == '/') tail++;
    if (ok && *tail) ok = (!b.n || buf_str(&b, "/")) && buf_str(&b, tail);
    if (ok && !b.n) ok = buf_str(&b, ".");
    if (!ok) {
        free(b.p);
        return NULL;
    }
    return (char *)b.p;
}

// A relative symlink at `link` (its parent exists) to the resolved `target`; `final_parent` is the
// resolved directory the link will live in once its tree is renamed into place.
static int relative_symlink(const char *target, const char *final_parent, const char *link) {
    char *real = realpath(target, NULL);
    if (!real) return -1;
    char *rel = relpath(real, final_parent);
    free(real);
    if (!rel) return -1;
    unlink(link);
    int r = symlink(rel, link);
    free(rel);
    return r;
}

// ---------------- Python int(text, 16) to a 64-bit value ----------------
// Returns 1 and the value, 0 when Python raises ValueError, -1 when it parses but leaves int64.
static int py_int16(const char *s, int64_t *value) {
    const char *p = s, *end = s + strlen(s);
    while (p < end && (*p == ' ' || (*p >= '\t' && *p <= '\r'))) p++;
    while (end > p && (end[-1] == ' ' || (end[-1] >= '\t' && end[-1] <= '\r'))) end--;
    int negative = 0;
    if (p < end && (*p == '+' || *p == '-')) negative = *p++ == '-';
    int prefix = 0;
    if (end - p >= 2 && p[0] == '0' && (p[1] == 'x' || p[1] == 'X')) {
        p += 2;
        prefix = 1;
    }
    if (p == end) return 0;
    uint64_t v = 0;
    int digits = 0, big = 0, under = prefix;
    for (; p < end; p++) {
        int d;
        if (*p == '_') {
            if (!under) return 0;
            under = 0;
            continue;
        }
        if (*p >= '0' && *p <= '9') d = *p - '0';
        else if (*p >= 'a' && *p <= 'f') d = *p - 'a' + 10;
        else if (*p >= 'A' && *p <= 'F') d = *p - 'A' + 10;
        else return 0;
        if (v >> 59) big = 1;
        v = v << 4 | (uint64_t)d;
        digits++;
        under = 1;
    }
    if (!digits || p[-1] == '_') return 0;
    if (big || v > (uint64_t)INT64_MAX + (negative ? 1u : 0u)) return -1;
    *value = negative ? (int64_t)(0 - v) : (int64_t)v;
    return 1;
}

// ---------------- the <m>.fixups.tsv header ----------------
// dict(l[2:].split(None, 1) for l in open(path) if l.startswith('# ')), values stripped; last key wins.
typedef struct {
    char *key, *value;
} kv_t;
typedef struct {
    kv_t *v;
    size_t n, cap;
} header_t;

static void header_free(header_t *h) {
    for (size_t i = 0; i < h->n; i++) {
        free(h->v[i].key);
        free(h->v[i].value);
    }
    free(h->v);
    memset(h, 0, sizeof *h);
}
static const char *header_get(const header_t *h, const char *key) {
    for (size_t i = h->n; i-- > 0;)
        if (!strcmp(h->v[i].key, key)) return h->v[i].value;
    return NULL;
}
static int is_space(unsigned char c) { return c == ' ' || (c >= '\t' && c <= '\r') || (c >= 0x1c && c <= 0x1f); }

static int utf8_valid(const uint8_t *s, size_t n) {   // Python's strict UTF-8 decoder
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

static int read_header(ctx_t *x, const char *path, header_t *h) {
    uint8_t *d = NULL;
    size_t n = 0;
    int r = read_all(path, (size_t)1 << 30, &d, &n);
    if (r) return fail(x, r == -2 ? RB_S2ARM_PACK_INVALID : RB_S2ARM_PACK_IO, "cannot read %s", path);
    if (!utf8_valid(d, n)) {
        free(d);
        return fail(x, RB_S2ARM_PACK_INVALID, "%s is not UTF-8 text", path);
    }
    int code = 0;
    size_t i = 0;
    while (i < n && !code) {   // universal newlines: \n, \r\n, \r
        size_t j = i;
        while (j < n && d[j] != '\n' && d[j] != '\r') j++;
        size_t next = j < n ? (d[j] == '\r' && j + 1 < n && d[j + 1] == '\n' ? j + 2 : j + 1) : j;
        if (j - i >= 2 && d[i] == '#' && d[i + 1] == ' ') {
            size_t a = i + 2;
            while (a < j && is_space(d[a])) a++;
            size_t b = a;
            while (b < j && !is_space(d[b])) b++;
            size_t c = b;
            while (c < j && is_space(d[c])) c++;
            if (a == j || c == j) {
                code = fail(x, RB_S2ARM_PACK_INVALID, "%s: header line without a value", path);
                break;
            }
            size_t e = j;
            while (e > c && is_space(d[e - 1])) e--;
            if (h->n == h->cap) {
                size_t cap = h->cap ? h->cap * 2 : 32;
                kv_t *nv = realloc(h->v, cap * sizeof *nv);
                if (!nv) {
                    code = fail(x, RB_S2ARM_PACK_IO, "out of memory");
                    break;
                }
                h->v = nv;
                h->cap = cap;
            }
            char *key = malloc(b - a + 1), *value = malloc(e - c + 1);
            if (!key || !value) {
                free(key);
                free(value);
                code = fail(x, RB_S2ARM_PACK_IO, "out of memory");
                break;
            }
            memcpy(key, d + a, b - a);
            key[b - a] = 0;
            memcpy(value, d + c, e - c);
            value[e - c] = 0;
            h->v[h->n].key = key;
            h->v[h->n].value = value;
            h->n++;
        }
        i = next;
    }
    free(d);
    return code;
}

static int header_hex(ctx_t *x, const header_t *h, const char *key, const char *fallback, const char *module, int64_t *out) {
    const char *v = header_get(h, key);
    if (!v) v = fallback;
    if (!v) return fail(x, RB_S2ARM_PACK_INVALID, "%s.fixups.tsv has no %s", module, key);
    int r = py_int16(v, out);
    if (r == 0) return fail(x, RB_S2ARM_PACK_INVALID, "%s.fixups.tsv: %s is not hexadecimal (%s)", module, key, v);
    // Beyond 2^40 the original's arithmetic (unbounded Python integers) can only end in a failed assertion
    // or an image of terabytes; refusing such values here keeps every later sum inside int64.
    if (r < 0 || *out > ((int64_t)1 << 40) || *out < -((int64_t)1 << 40))
        return fail(x, RB_S2ARM_PACK_INVALID, "%s.fixups.tsv: %s out of range (%s)", module, key, v);
    return 0;
}

// ---------------- module load order (tools/module_order.py) ----------------
static int subsdk_number(const char *name, uint64_t *n) {   // subsdk[0-9]+ (whole name)
    if (strncmp(name, "subsdk", 6) || !name[6]) return 0;
    uint64_t v = 0;
    for (const char *p = name + 6; *p; p++) {
        if (*p < '0' || *p > '9') return 0;
        v = v > UINT64_MAX / 10 ? UINT64_MAX : v * 10 + (uint64_t)(*p - '0');
    }
    *n = v;
    return 1;
}
static int order_cmp(const void *pa, const void *pb) {
    const char *a = *(char *const *)pa, *b = *(char *const *)pb;
    uint64_t na = 0, nb = 0;
    int ka = !strcmp(a, "main") ? 0 : subsdk_number(a, &na) ? 1 : !strcmp(a, "sdk") ? 3 : 2;
    int kb = !strcmp(b, "main") ? 0 : subsdk_number(b, &nb) ? 1 : !strcmp(b, "sdk") ? 3 : 2;
    if (ka != kb) return ka < kb ? -1 : 1;
    if (ka == 1 && na != nb) return na < nb ? -1 : 1;
    return strcmp(a, b);   // others by name; equal subsdk numbers (subsdk7 / subsdk07) by name
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
static int list_add(list_t *l, char *s) {
    if (!s) return 0;
    if (l->n == l->cap) {
        size_t cap = l->cap ? l->cap * 2 : 16;
        char **nv = realloc(l->v, cap * sizeof *nv);
        if (!nv) {
            free(s);
            return 0;
        }
        l->v = nv;
        l->cap = cap;
    }
    l->v[l->n++] = s;
    return 1;
}
static int cmp_str(const void *a, const void *b) { return strcmp(*(char *const *)a, *(char *const *)b); }

// Names of a directory (no "." / ".."), sorted; -1 unreadable, -2 out of memory. Each name keeps its readdir type
// (s2arm_dirent.h) in the byte after its terminating NUL, for walk_source.
static int listdir(const char *path, list_t *out) {
    DIR *d = opendir(path);
    if (!d) return -1;
    struct dirent *e;
    int ok = 1;
    while (ok && (e = readdir(d)))
        if (strcmp(e->d_name, ".") && strcmp(e->d_name, "..")) {
            size_t n = strlen(e->d_name);
            char *s = malloc(n + 2);
            if (s) {
                memcpy(s, e->d_name, n + 1);
                s[n + 1] = (char)s2arm_dirent_type(e);
            }
            ok = list_add(out, s);
        }
    closedir(d);
    if (!ok) return -2;
    if (out->n) qsort(out->v, out->n, sizeof *out->v, cmp_str);
    return 0;
}

// ship_ext.py modules(): every <m>.fixups.tsv of root (Path.glob matches hidden names too), in load order.
static int root_modules(ctx_t *x, const char *root, list_t *mods) {
    list_t names = {0};
    if (listdir(root, &names)) return fail(x, RB_S2ARM_PACK_IO, "cannot list %s", root);
    static const char suffix[] = ".fixups.tsv";
    size_t sl = sizeof suffix - 1;
    for (size_t i = 0; i < names.n; i++) {
        size_t l = strlen(names.v[i]);
        if (l < sl || strcmp(names.v[i] + l - sl, suffix)) continue;
        char *m = malloc(l - sl + 1);
        if (!m) {
            list_free(&names);
            return fail(x, RB_S2ARM_PACK_IO, "out of memory");
        }
        memcpy(m, names.v[i], l - sl);
        m[l - sl] = 0;
        if (!list_add(mods, m)) {
            list_free(&names);
            return fail(x, RB_S2ARM_PACK_IO, "out of memory");
        }
    }
    list_free(&names);
    if (mods->n) qsort(mods->v, mods->n, sizeof *mods->v, order_cmp);
    return 0;
}

// ---------------- image pack: layout (ios/embed.py) ----------------
typedef struct {   // a piece of a section: zeros (path NULL) or a file range
    const char *path;
    uint64_t off, n;
} piece_t;
typedef struct {
    piece_t *v;
    size_t n, cap;
} pieces_t;
static int piece_add(pieces_t *p, const char *path, uint64_t off, uint64_t n) {
    if (p->n == p->cap) {
        size_t cap = p->cap ? p->cap * 2 : 32;
        piece_t *nv = realloc(p->v, cap * sizeof *nv);
        if (!nv) return 0;
        p->v = nv;
        p->cap = cap;
    }
    p->v[p->n].path = path;
    p->v[p->n].off = off;
    p->v[p->n].n = n;
    p->n++;
    return 1;
}
static uint64_t pieces_len(const pieces_t *p) {
    uint64_t z = 0;
    for (size_t i = 0; i < p->n; i++) z += p->v[i].n;
    return z;
}

static int64_t r16(int64_t v) { return (v + PG - 1) & ~(int64_t)(PG - 1); }
static int64_t pymod(int64_t a, int64_t m) {
    int64_t r = a % m;
    return r < 0 ? r + m : r;
}

typedef struct {
    char name[24];
    uint64_t off[4], len[4];   // x0, W, x1, x2
} entry_t;

typedef struct {
    pieces_t code, data;
    entry_t *entries;
    size_t count;
    char **paths;   // owned patched.bin paths
} layout_t;

static void layout_free(layout_t *l) {
    free(l->code.v);
    free(l->data.v);
    free(l->entries);
    for (size_t i = 0; i < l->count; i++) free(l->paths[i]);
    free(l->paths);
    memset(l, 0, sizeof *l);
}

static int layout(ctx_t *x, const char *root, char *const *names, size_t count, layout_t *L) {
    L->entries = calloc(count ? count : 1, sizeof *L->entries);
    L->paths = calloc(count ? count : 1, sizeof *L->paths);
    if (!L->entries || !L->paths) return fail(x, RB_S2ARM_PACK_IO, "out of memory");
    uint64_t coff = 0, doff = 0;
    for (size_t k = 0; k < count; k++) {
        const char *spec = names[k], *eq = strchr(spec, '=');
        char name[64], stem[1024];
        size_t nl = eq ? (size_t)(eq - spec) : strlen(spec);
        const char *st = eq ? eq + 1 : spec;
        if (nl >= sizeof name || strlen(st) >= sizeof stem) return fail(x, RB_S2ARM_PACK_INVALID, "module name too long: %s", spec);
        memcpy(name, spec, nl);
        name[nl] = 0;
        strcpy(stem, st);
        char *fx = pjoin(root, stem), *fixups = fx ? pcat(fx, ".fixups.tsv") : NULL, *bin = fx ? pcat(fx, ".patched.bin") : NULL;
        free(fx);
        if (!fixups || !bin) {
            free(fixups);
            free(bin);
            return fail(x, RB_S2ARM_PACK_IO, "out of memory");
        }
        L->paths[k] = bin;
        L->count = k + 1;   // layout_free releases the paths stored so far
        header_t h = {0};
        int code = read_header(x, fixups, &h);
        free(fixups);
        int64_t te = 0, po = 0, ko = 0, ks = 0, lb = 0, l2 = 0, fl = 0;
        if (!code) code = header_hex(x, &h, "TEXT_END", NULL, stem, &te);
        if (!code) code = header_hex(x, &h, "PATCH_OFF", NULL, stem, &po);
        if (!code) code = header_hex(x, &h, "KEY_PAGE_OFF", NULL, stem, &ko);
        if (!code) code = header_hex(x, &h, "KEY_PAGE_SIZE", NULL, stem, &ks);
        if (!code) code = header_hex(x, &h, "LOAD_BIAS", "0", stem, &lb);
        // A negative bias becomes a negative zero run in front of x0, which macho_dylib.py cannot pack (struct.error).
        if (!code && lb < 0) code = fail(x, RB_S2ARM_PACK_INVALID, "%s.fixups.tsv: LOAD_BIAS is negative", stem);
        int dual = header_get(&h, "PATCH2_OFF") != NULL;   // only its presence counts; PATCH2_LEN defaults to 0
        if (!code && dual) code = header_hex(x, &h, "PATCH2_LEN", "0", stem, &l2);
        struct stat sb;
        if (!code && stat(bin, &sb)) code = fail(x, RB_S2ARM_PACK_INVALID, "%s.patched.bin is missing", stem);
        int64_t sz_all = code ? 0 : (int64_t)sb.st_size;
        int64_t a = r16(te + lb) - lb, sz = sz_all - l2;
        int64_t end = po >= 0 ? po + r16(sz - po) : r16(sz);
        if (!code && strlen(name) > 23) code = fail(x, RB_S2ARM_PACK_INVALID, "module name %s too long (at most 23 bytes in the index)", name);
        struct {
            int kind;
            int64_t lo, hi;
        } cuts[4];
        int ncuts = 0;
        if (!code && po < 0) {   // FAR: patched.bin = image [0, FILE_IMAGE_LEN) + patch area
            code = header_hex(x, &h, "FILE_IMAGE_LEN", NULL, stem, &fl);
            if (!code && !(pymod(fl, PG) == 0 && a <= fl && fl < sz && ks == PG && !lb))
                code = fail(x, RB_S2ARM_PACK_INVALID, "%s: far layout does not hold (FILE_IMAGE_LEN 0x%llx, size 0x%llx, bias 0x%llx)", name,
                            (unsigned long long)fl, (unsigned long long)sz, (unsigned long long)lb);
            cuts[0].kind = 0, cuts[0].lo = 0, cuts[0].hi = a;
            cuts[1].kind = 1, cuts[1].lo = a, cuts[1].hi = fl;
            cuts[2].kind = 2, cuts[2].lo = fl, cuts[2].hi = end;
            ncuts = 3;
        } else if (!code) {
            if (!(pymod(po + lb, PG) == 0 && a <= ko && ko + ks <= po && pymod(ko + lb, PG) == 0 && ks == PG))
                code = fail(x, RB_S2ARM_PACK_INVALID, "%s: patch area / key page layout does not hold (PATCH_OFF 0x%llx, KEY_PAGE_OFF 0x%llx)", name,
                            (unsigned long long)po, (unsigned long long)ko);
            cuts[0].kind = 0, cuts[0].lo = 0, cuts[0].hi = a;
            cuts[1].kind = 1, cuts[1].lo = a, cuts[1].hi = po;
            cuts[2].kind = 2, cuts[2].lo = po, cuts[2].hi = end;
            ncuts = 3;
        }
        if (!code && !(0 <= l2 && l2 <= sz_all && pymod(l2, 4) == 0))
            code = fail(x, RB_S2ARM_PACK_INVALID, "%s: PATCH2_LEN 0x%llx does not fit", name, (unsigned long long)l2);
        if (!code && l2) {
            cuts[3].kind = 3, cuts[3].lo = sz, cuts[3].hi = sz + r16(l2);
            ncuts = 4;
        }
        header_free(&h);
        if (code) return code;
        entry_t *e = &L->entries[k];
        memset(e, 0, sizeof *e);
        memcpy(e->name, name, strlen(name));
        for (int c = 0; c < ncuts; c++) {
            int64_t lo = cuts[c].lo, hi = cuts[c].hi;
            int64_t lim = cuts[c].kind == 3 ? sz_all : sz;
            int64_t fill = (hi < lim ? hi : lim) - lo;
            int64_t pre = lb && lo == 0 ? lb : 0;
            int64_t ln = pre + hi - lo;
            if (!(pymod(ln, PG) == 0 && 0 <= fill && fill <= hi - lo))   // blocks are whole 16 KiB pages (vm_remap); the file holds the block
                return fail(x, RB_S2ARM_PACK_INVALID, "%s: block %d does not hold (length %s0x%llx, from the file %s0x%llx)", name, cuts[c].kind,
                            ln < 0 ? "-" : "", (unsigned long long)(ln < 0 ? -ln : ln), fill < 0 ? "-" : "",
                            (unsigned long long)(fill < 0 ? -fill : fill));
            pieces_t *target = cuts[c].kind == 1 ? &L->data : &L->code;
            uint64_t *at = cuts[c].kind == 1 ? &doff : &coff;
            int ok = (!pre || piece_add(target, NULL, 0, (uint64_t)pre)) && (!fill || piece_add(target, bin, (uint64_t)lo, (uint64_t)fill)) &&
                     (!(ln - pre - fill) || piece_add(target, NULL, 0, (uint64_t)(ln - pre - fill)));
            if (!ok) return fail(x, RB_S2ARM_PACK_IO, "out of memory");
            e->off[cuts[c].kind] = *at;
            e->len[cuts[c].kind] = (uint64_t)ln;
            *at += (uint64_t)ln;
        }
    }
    L->count = count;
    return 0;
}

// ---------------- image pack: the Mach-O (ios/macho_dylib.py) ----------------
#define LC_SEGMENT_64 0x19
#define LC_SYMTAB 0x2
#define LC_DYSYMTAB 0xB
#define LC_ID_DYLIB 0xD
#define LC_UUID 0x1B
#define LC_BUILD_VERSION 0x32
#define LC_CODE_SIGNATURE 0x1D
#define PURE_INSTRUCTIONS 0x80000400u
#define MH_FLAGS (0x1u | 0x4u | 0x80u | 0x100000u)

typedef struct {
    const char *name;
    int align;
    uint32_t flags;
    const pieces_t *pieces;     // or bytes
    const uint8_t *bytes;
    size_t bytes_len;
    uint64_t at, size;
} section_t;

static uint64_t up(uint64_t n, uint64_t a) { return (n + a - 1) / a * a; }

static int seg_cmd(buf_t *b, const char *name, uint64_t vm, uint64_t size, uint64_t fo, uint64_t fsize, int32_t prot, const section_t *s,
                   int ns) {
    int ok = buf_u32(b, LC_SEGMENT_64) && buf_u32(b, (uint32_t)(72 + 80 * ns)) && buf_name16(b, name) && buf_u64(b, vm) && buf_u64(b, size) &&
             buf_u64(b, fo) && buf_u64(b, fsize) && buf_u32(b, (uint32_t)prot) && buf_u32(b, (uint32_t)prot) && buf_u32(b, (uint32_t)ns) &&
             buf_u32(b, 0);
    for (int i = 0; ok && i < ns; i++)
        ok = buf_name16(b, s[i].name) && buf_name16(b, name) && buf_u64(b, s[i].at) && buf_u64(b, s[i].size) && buf_u32(b, (uint32_t)s[i].at) &&
             buf_u32(b, (uint32_t)s[i].align) && buf_u32(b, 0) && buf_u32(b, 0) && buf_u32(b, s[i].flags) && buf_u32(b, 0) && buf_u32(b, 0) &&
             buf_u32(b, 0);
    return ok;
}

typedef struct {   // SHA-256 of every 4 KiB page of what is written, page 0 kept aside (patched at the end)
    s2arm_sha256_ctx cur;
    size_t in_page;
    uint64_t page;
    uint8_t *hashes;
    size_t cap;
    uint8_t zero_page[32];
} pager_t;

static int pager_push(pager_t *p, const uint8_t digest[32]) {
    if ((p->page + 1) * 32 > p->cap) {
        size_t cap = p->cap ? p->cap * 2 : 4096;
        while (cap < (p->page + 1) * 32) cap *= 2;
        uint8_t *nh = realloc(p->hashes, cap);
        if (!nh) return 0;
        p->hashes = nh;
        p->cap = cap;
    }
    memcpy(p->hashes + p->page * 32, digest, 32);
    p->page++;
    return 1;
}
static int pager_feed(pager_t *p, const uint8_t *d, size_t n) {
    while (n) {
        size_t take = CS_PAGE - p->in_page < n ? CS_PAGE - p->in_page : n;
        s2arm_sha256_update(&p->cur, d, take);
        p->in_page += take;
        d += take;
        n -= take;
        if (p->in_page == CS_PAGE) {
            uint8_t dg[32];
            s2arm_sha256_final(&p->cur, dg);
            if (!pager_push(p, dg)) return 0;
            s2arm_sha256_init(&p->cur);
            p->in_page = 0;
        }
    }
    return 1;
}
static int pager_zeros(pager_t *p, uint64_t n) {
    static const uint8_t zeros[CS_PAGE];
    if (p->in_page) {
        size_t take = CS_PAGE - p->in_page < n ? CS_PAGE - p->in_page : (size_t)n;
        if (!pager_feed(p, zeros, take)) return 0;
        n -= take;
    }
    for (; n >= CS_PAGE; n -= CS_PAGE)
        if (!pager_push(p, p->zero_page)) return 0;
    return pager_feed(p, zeros, (size_t)n);
}
static int pager_finish(pager_t *p) {   // the last, partial page
    if (!p->in_page) return 1;
    uint8_t dg[32];
    s2arm_sha256_final(&p->cur, dg);
    p->in_page = 0;
    return pager_push(p, dg);
}

typedef struct {
    ctx_t *x;
    int fd;
    uint64_t pos;
    pager_t pager;
    s2arm_sha256_ctx body;   // the UUID: section placements and contents (zero runs by length)
    uint8_t *page0;          // the first 4 KiB, hashed at the end once the UUID is in
} writer_t;

static int w_bytes(writer_t *w, const uint8_t *d, size_t n) {
    for (size_t done = 0; done < n;) {
        ssize_t k = write(w->fd, d + done, n - done);
        if (k < 0 && errno == EINTR) continue;
        if (k <= 0) return fail(w->x, RB_S2ARM_PACK_IO, "cannot write the image pack");
        done += (size_t)k;
    }
    size_t skip = 0;   // page 0 goes aside
    if (w->pos < CS_PAGE) {
        skip = CS_PAGE - (size_t)w->pos < n ? CS_PAGE - (size_t)w->pos : n;
        memcpy(w->page0 + w->pos, d, skip);
        if (w->pos + skip == CS_PAGE) w->pager.page = 1;   // its hash is pushed at the end, in slot 0
    }
    if (w->pos + skip >= CS_PAGE && !pager_feed(&w->pager, d + skip, n - skip)) return fail(w->x, RB_S2ARM_PACK_IO, "out of memory");
    w->pos += n;
    return 0;
}
static int w_zeros(writer_t *w, uint64_t n) {
    static const uint8_t zeros[1 << 16];
    if (w->pos < CS_PAGE || n < (1 << 20)) {
        while (n) {
            size_t k = n < sizeof zeros ? (size_t)n : sizeof zeros;
            int r = w_bytes(w, zeros, k);
            if (r) return r;
            n -= k;
        }
        return 0;
    }
    if (ftruncate(w->fd, (off_t)(w->pos + n)) || lseek(w->fd, (off_t)(w->pos + n), SEEK_SET) < 0)   // sparse, as macho_dylib.py does
        return fail(w->x, RB_S2ARM_PACK_IO, "cannot extend the image pack");
    if (!pager_zeros(&w->pager, n)) return fail(w->x, RB_S2ARM_PACK_IO, "out of memory");
    w->pos += n;
    return 0;
}

static int w_piece(writer_t *w, const piece_t *p) {
    if (!p->path) {
        uint8_t len[8];
        for (int i = 0; i < 8; i++) len[i] = (uint8_t)(p->n >> (8 * i));
        s2arm_sha256_update(&w->body, len, 8);   // a zero block is hashed as its length
        return w_zeros(w, p->n);
    }
    int in = open(p->path, O_RDONLY);
    if (in < 0) return fail(w->x, RB_S2ARM_PACK_IO, "cannot read %s", p->path);
    if (lseek(in, (off_t)p->off, SEEK_SET) < 0) {
        close(in);
        return fail(w->x, RB_S2ARM_PACK_IO, "cannot read %s", p->path);
    }
    static const size_t CHUNK = 1 << 20;
    uint8_t *b = malloc(CHUNK);
    if (!b) {
        close(in);
        return fail(w->x, RB_S2ARM_PACK_IO, "out of memory");
    }
    int code = 0;
    for (uint64_t left = p->n; left && !code;) {
        if (stop(w->x)) {
            code = fail(w->x, RB_S2ARM_PACK_CANCELLED, "cancelled");
            break;
        }
        ssize_t k = read(in, b, left < CHUNK ? (size_t)left : CHUNK);
        if (k < 0 && errno == EINTR) continue;
        if (k <= 0) {
            code = fail(w->x, RB_S2ARM_PACK_INVALID, "%s at 0x%llx is shorter than 0x%llx bytes", p->path, (unsigned long long)p->off,
                        (unsigned long long)p->n);
            break;
        }
        s2arm_sha256_update(&w->body, b, (size_t)k);
        code = w_bytes(w, b, (size_t)k);
        left -= (uint64_t)k;
    }
    free(b);
    close(in);
    return code;
}

static int place(section_t *s, int n, uint64_t start, uint64_t *end) {
    uint64_t at = start;
    for (int i = 0; i < n; i++) {
        at = up(at, (uint64_t)1 << s[i].align);
        s[i].size = s[i].pieces ? pieces_len(s[i].pieces) : s[i].bytes_len;
        s[i].at = at;
        at += s[i].size;
    }
    *end = at;
    return 0;
}

static int write_dylib(ctx_t *x, const char *dst, const layout_t *L) {
    // the index: "S2AEMB01", count, 88, then name[24] + 4 x (offset, length)
    buf_t idx = {0};
    int ok = buf_add(&idx, "S2AEMB01", 8) && buf_u32(&idx, (uint32_t)L->count) && buf_u32(&idx, 88);
    for (size_t i = 0; ok && i < L->count; i++) {
        ok = buf_add(&idx, L->entries[i].name, 24);
        for (int k = 0; ok && k < 4; k++) ok = buf_u64(&idx, L->entries[i].off[k]) && buf_u64(&idx, L->entries[i].len[k]);
    }
    pieces_t one_page = {0};
    if (!ok || (!L->data.n && !piece_add(&one_page, NULL, 0, PG))) {
        free(idx.p);
        return fail(x, RB_S2ARM_PACK_IO, "out of memory");
    }
    section_t text[2] = {{"__swcode", 14, PURE_INSTRUCTIONS, &L->code, NULL, 0, 0, 0}, {"__swidx", 3, 0, NULL, idx.p, idx.n, 0, 0}};
    section_t data[1] = {{"__img", 14, 0, L->data.n ? &L->data : &one_page, NULL, 0, 0, 0}};
    uint64_t tend, dend;
    place(text, 2, PG, &tend);
    uint64_t tsize = up(tend, PG);
    place(data, 1, tsize, &dend);
    uint64_t dsize = up(dend, PG) - tsize, le = tsize + dsize;
    static const uint8_t strtab[8] = {' ', 0, 0, 0, 0, 0, 0, 0};
    uint64_t cs_off = up(le + sizeof strtab, 16);
    uint64_t cs_size = up((cs_off / CS_PAGE + 1) * 52, CS_PAGE) + 0x40000;
    int code = 0;
    if (cs_off + cs_size > UINT32_MAX || le > UINT32_MAX) code = fail(x, RB_S2ARM_PACK_INVALID, "image pack above 4 GiB (32-bit Mach-O offsets)");
    static const char install[] = "@rpath/S2AImages.dylib";
    size_t name_len = sizeof install, idz = (size_t)up(24 + name_len, 8);
    uint32_t v = (18u << 16) | (0u << 8);
    buf_t lc = {0};
    size_t uuid_at = 0;
    int ncmds = 0;
    if (!code) {
        ok = seg_cmd(&lc, "__TEXT", 0, tsize, 0, tsize, 5, text, 2) && ++ncmds &&
             seg_cmd(&lc, "__SWDATA", tsize, dsize, tsize, dsize, 3, data, 1) && ++ncmds &&
             seg_cmd(&lc, "__LINKEDIT", le, up(cs_off + cs_size - le, PG), le, cs_off + cs_size - le, 1, NULL, 0) && ++ncmds;
        size_t id_at = lc.n;
        ok = ok && buf_u32(&lc, LC_ID_DYLIB) && buf_u32(&lc, (uint32_t)idz) && buf_u32(&lc, 24) && buf_u32(&lc, 2) && buf_u32(&lc, 0x10000) &&
             buf_u32(&lc, 0x10000) && buf_add(&lc, install, name_len) && ++ncmds;
        while (ok && lc.n < id_at + idz) ok = buf_add(&lc, "", 1);
        uuid_at = 32 + lc.n + 8;
        static const uint8_t zero16[16];
        ok = ok && buf_u32(&lc, LC_UUID) && buf_u32(&lc, 24) && buf_add(&lc, zero16, 16) && ++ncmds &&                                 // filled from the contents
             buf_u32(&lc, LC_BUILD_VERSION) && buf_u32(&lc, 24) && buf_u32(&lc, 2) && buf_u32(&lc, v) && buf_u32(&lc, v) && buf_u32(&lc, 0) &&   // platform 2 = iOS
             ++ncmds && buf_u32(&lc, LC_SYMTAB) && buf_u32(&lc, 24) && buf_u32(&lc, 0) && buf_u32(&lc, 0) && buf_u32(&lc, (uint32_t)le) &&
             buf_u32(&lc, sizeof strtab) && ++ncmds && buf_u32(&lc, LC_DYSYMTAB) && buf_u32(&lc, 80);
        for (int i = 0; ok && i < 18; i++) ok = buf_u32(&lc, 0);
        ok = ok && ++ncmds && buf_u32(&lc, LC_CODE_SIGNATURE) && buf_u32(&lc, 16) && buf_u32(&lc, (uint32_t)cs_off) && buf_u32(&lc, (uint32_t)cs_size) &&
             ++ncmds;
        if (!ok) code = fail(x, RB_S2ARM_PACK_IO, "out of memory");
        else if (32 + lc.n > PG) code = fail(x, RB_S2ARM_PACK_INVALID, "load commands do not fit the header page");
    }
    writer_t w;
    memset(&w, 0, sizeof w);
    w.x = x;
    w.fd = -1;
    if (!code) {
        w.page0 = calloc(1, CS_PAGE);
        static const uint8_t zpage[CS_PAGE];
        s2arm_sha256(zpage, CS_PAGE, w.pager.zero_page);
        s2arm_sha256_init(&w.pager.cur);
        s2arm_sha256_init(&w.body);
        unlink(dst);
        w.fd = open(dst, O_RDWR | O_CREAT | O_TRUNC, 0644);
        if (!w.page0) code = fail(x, RB_S2ARM_PACK_IO, "out of memory");
        else if (w.fd < 0) code = fail(x, RB_S2ARM_PACK_IO, "cannot create %s", dst);
    }
    if (!code) {
        buf_t hdr = {0};
        ok = buf_u32(&hdr, 0xFEEDFACF) && buf_u32(&hdr, 0x0100000C) && buf_u32(&hdr, 0) && buf_u32(&hdr, 6) && buf_u32(&hdr, (uint32_t)ncmds) &&
             buf_u32(&hdr, (uint32_t)lc.n) && buf_u32(&hdr, MH_FLAGS) && buf_u32(&hdr, 0) && buf_add(&hdr, lc.p, lc.n);
        code = ok ? w_bytes(&w, hdr.p, hdr.n) : fail(x, RB_S2ARM_PACK_IO, "out of memory");
        free(hdr.p);
    }
    section_t *all[3] = {&text[0], &text[1], &data[0]};
    for (int i = 0; i < 3 && !code; i++) {
        section_t *s = all[i];
        code = w_zeros(&w, s->at - w.pos);
        uint8_t place_desc[16];
        for (int k = 0; k < 8; k++) place_desc[k] = (uint8_t)(s->at >> (8 * k)), place_desc[8 + k] = (uint8_t)(s->size >> (8 * k));
        s2arm_sha256_update(&w.body, place_desc, 16);
        if (s->pieces)
            for (size_t k = 0; k < s->pieces->n && !code; k++) code = w_piece(&w, &s->pieces->v[k]);
        else if (!code) {
            s2arm_sha256_update(&w.body, s->bytes, s->bytes_len);
            code = w_bytes(&w, s->bytes, s->bytes_len);
        }
    }
    if (!code) code = w_zeros(&w, le - w.pos);
    if (!code) code = w_bytes(&w, strtab, sizeof strtab);
    if (!code) code = w_zeros(&w, cs_off - w.pos);
    if (!code && !pager_finish(&w.pager)) code = fail(x, RB_S2ARM_PACK_IO, "out of memory");
    if (!code) {   // the UUID, then page 0's hash
        uint8_t digest[32];
        s2arm_sha256_final(&w.body, digest);
        memcpy(w.page0 + uuid_at, digest, 16);
        if (pwrite(w.fd, digest, 16, (off_t)uuid_at) != 16) code = fail(x, RB_S2ARM_PACK_IO, "cannot write the image pack");
        s2arm_sha256(w.page0, CS_PAGE, digest);
        if (w.pager.cap < 32) code = fail(x, RB_S2ARM_PACK_INVALID, "image pack too small");
        else memcpy(w.pager.hashes, digest, 32);
    }
    uint64_t npages = w.pager.page;
    if (!code && npages != (cs_off + CS_PAGE - 1) / CS_PAGE) code = fail(x, RB_S2ARM_PACK_INVALID, "internal error: page count");
    if (!code) {   // SuperBlob + CodeDirectory 0x20400, linker-signed ad-hoc (CS_ADHOC | CS_LINKER_SIGNED)
        static const char ident[] = "S2AImages";
        size_t hdrlen = 88, il = sizeof ident;
        buf_t sig = {0};
        uint32_t cdlen = (uint32_t)(hdrlen + il + 32 * npages);
        ok = buf_be32(&sig, 0xFADE0CC0) && buf_be32(&sig, 20 + cdlen) && buf_be32(&sig, 1) && buf_be32(&sig, 0) && buf_be32(&sig, 20) &&
             buf_be32(&sig, 0xFADE0C02) && buf_be32(&sig, cdlen) && buf_be32(&sig, 0x20400) && buf_be32(&sig, 0x20002) &&
             buf_be32(&sig, (uint32_t)(hdrlen + il)) && buf_be32(&sig, (uint32_t)hdrlen) && buf_be32(&sig, 0) && buf_be32(&sig, (uint32_t)npages) &&
             buf_be32(&sig, (uint32_t)cs_off) && buf_add(&sig, "\x20\x02\x00\x0c", 4) && buf_be32(&sig, 0) && buf_be32(&sig, 0) &&
             buf_be32(&sig, 0) && buf_be32(&sig, 0) && buf_be64(&sig, 0) && buf_be64(&sig, 0) && buf_be64(&sig, tsize) && buf_be64(&sig, 0) &&
             buf_add(&sig, ident, il) && buf_add(&sig, w.pager.hashes, 32 * npages);
        if (!ok) code = fail(x, RB_S2ARM_PACK_IO, "out of memory");
        else if (sig.n > cs_size) code = fail(x, RB_S2ARM_PACK_INVALID, "signature area too small");
        else {
            code = w_bytes(&w, sig.p, sig.n);
            if (!code) code = w_zeros(&w, cs_size - sig.n);
        }
        free(sig.p);
    }
    if (w.fd >= 0 && close(w.fd) && !code) code = fail(x, RB_S2ARM_PACK_IO, "cannot finish %s", dst);
    if (code && w.fd >= 0) unlink(dst);
    free(w.page0);
    free(w.pager.hashes);
    free(lc.p);
    free(idx.p);
    free(one_page.v);
    return code;
}

int rb_s2arm_image_pack(const char *root, const char *const *modules, size_t count, const char *output, char *error, size_t error_size) {
    ctx_t x = {error, error_size, NULL, NULL};
    if (!root || !output) return fail(&x, RB_S2ARM_PACK_INVALID, "incomplete request");
    list_t mods = {0};
    int code = 0;
    if (!modules || !count) {
        if ((code = root_modules(&x, root, &mods))) return code;
    } else
        for (size_t i = 0; i < count && !code; i++)
            if (!modules[i] || !list_add(&mods, sdup(modules[i]))) code = fail(&x, RB_S2ARM_PACK_IO, "out of memory");
    if (!code && !mods.n) code = fail(&x, RB_S2ARM_PACK_INVALID, "%s has no rewritten module (*.fixups.tsv)", root);
    if (!code && mods.n > MAX_MODULES) code = fail(&x, RB_S2ARM_PACK_INVALID, "too many modules");
    for (size_t i = 0; i < mods.n && !code; i++)   // module names (before "=") must be unique
        for (size_t j = 0; j < i && !code; j++) {
            size_t a = strcspn(mods.v[i], "="), b = strcspn(mods.v[j], "=");
            if (a == b && !strncmp(mods.v[i], mods.v[j], a)) code = fail(&x, RB_S2ARM_PACK_INVALID, "module name given twice: %.*s", (int)a, mods.v[i]);
        }
    layout_t L = {0};
    char *tmp = pcat(output, ".tmp");   // written aside, then renamed over the output: a failure leaves the previous pack
    if (!code && !tmp) code = fail(&x, RB_S2ARM_PACK_IO, "out of memory");
    if (!code) code = layout(&x, root, mods.v, mods.n, &L);
    if (!code) code = write_dylib(&x, tmp, &L);
    if (!code && rename(tmp, output)) {
        unlink(tmp);
        code = fail(&x, RB_S2ARM_PACK_IO, "cannot rename %s to %s", tmp, output);
    }
    free(tmp);
    layout_free(&L);
    list_free(&mods);
    return code;
}

// ---------------- module directory (pack/ship_ext.py container) ----------------
// The shell's table list (pack/pkg_srcs.py app_tables() at the pinned commit; CI checks it).
static const char *const APP_TABLES[] = {"addr_need.tsv", "cpatch.tsv",     "fps.tsv",           "gpu_drivers.tsv",  "nro_exports.tsv",
                                         "nro_modules.tsv", "s2a_caps.tsv", "widen_enable.*.tsv", "widen_full.*.tsv", "widen_verified.tsv"};

static int table_match(const char *pattern, const char *name) {   // "<prefix>*<suffix>" or a literal name
    const char *star = strchr(pattern, '*');
    if (!star) return !strcmp(pattern, name);
    size_t pl = (size_t)(star - pattern), sl = strlen(star + 1), nl = strlen(name);
    return nl >= pl + sl && !strncmp(name, pattern, pl) && !strcmp(name + nl - sl, star + 1);
}

static int npdm_gid(ctx_t *x, const char *npdm, char gid[17]) {   // ship_ext.py npdm_ident
    uint8_t *b = NULL;
    size_t n = 0;
    int r = read_all(npdm, 1u << 26, &b, &n);
    if (r) return fail(x, RB_S2ARM_PACK_INVALID, "cannot read %s", npdm);
    int code = 0;
    if (n < 0x80 || memcmp(b, "META", 4)) code = fail(x, RB_S2ARM_PACK_INVALID, "%s is not an NPDM (no META header)", npdm);
    else {
        uint64_t aci = le32(b + 0x70);
        if (aci + 0x18 > n || memcmp(b + aci, "ACI0", 4)) code = fail(x, RB_S2ARM_PACK_INVALID, "%s has no ACI0 (no program id)", npdm);
        else snprintf(gid, 17, "%016llX", (unsigned long long)le64(b + aci + 0x10));
    }
    free(b);
    return code;
}

static int hexdigits(const char *s, size_t n, int lower_only) {
    if (strlen(s) != n) return 0;
    for (; *s; s++)
        if (!((*s >= '0' && *s <= '9') || (*s >= 'a' && *s <= 'f') || (!lower_only && *s >= 'A' && *s <= 'F'))) return 0;
    return 1;
}

static int json_string(buf_t *b, const char *s) {   // json.dumps(ensure_ascii=False)
    int ok = buf_str(b, "\"");
    for (const unsigned char *p = (const unsigned char *)s; ok && *p; p++) {
        if (*p == '"') ok = buf_str(b, "\\\"");
        else if (*p == '\\') ok = buf_str(b, "\\\\");
        else if (*p == '\n') ok = buf_str(b, "\\n");
        else if (*p == '\r') ok = buf_str(b, "\\r");
        else if (*p == '\t') ok = buf_str(b, "\\t");
        else if (*p == '\b') ok = buf_str(b, "\\b");
        else if (*p == '\f') ok = buf_str(b, "\\f");
        else if (*p < 0x20) ok = buf_fmt(b, "\\u%04x", *p);
        else ok = buf_add(b, p, 1);
    }
    return ok && buf_str(b, "\"");
}

// pack/save_identity.py validate + json.dumps(separators=(",", ":")) + "\n", keys in identity()'s order.
static int save_identity_text(ctx_t *x, const rb_s2arm_save_identity *si, buf_t *out) {
    if (!si->id || !hexdigits(si->id, 16, 0)) return fail(x, RB_S2ARM_PACK_INVALID, "save identity: invalid game id");
    if (!si->name || si->version < 0 || !utf8_valid((const uint8_t *)si->name, strlen(si->name)))
        return fail(x, RB_S2ARM_PACK_INVALID, "save identity: invalid game version or name");
    if (!si->content_identity || !hexdigits(si->content_identity, 64, 1)) return fail(x, RB_S2ARM_PACK_INVALID, "save identity: invalid content identity");
    int ok = buf_str(out, "{\"id\":") && json_string(out, si->id) && buf_str(out, ",\"name\":") && json_string(out, si->name) &&
             buf_fmt(out, ",\"version\":%lld,\"contentIdentity\":", si->version) && json_string(out, si->content_identity) && buf_str(out, "}\n");
    return ok ? 0 : fail(x, RB_S2ARM_PACK_IO, "out of memory");
}

static int ctx_value_ok(const char *v) { return v[0] == '/' || (!strncmp(v, "@bundle/", 8) && v[8]) || (!strncmp(v, "@home/", 6) && v[6]); }

int rb_s2arm_module_dir(const rb_s2arm_module_request *r, char *error, size_t error_size) {
    ctx_t x = {error, error_size, NULL, NULL};
    if (!r || !r->root || !r->module_dir || !*r->module_dir) return fail(&x, RB_S2ARM_PACK_INVALID, "incomplete request");
    const char *root = r->root;
    list_t mods = {0};
    buf_t si = {0}, c = {0};
    char *npdm = pjoin(root, "main.npdm"), *dest = sdup(r->module_dir), *tmp = NULL;
    char gid[17] = "";
    int code = !npdm || !dest ? fail(&x, RB_S2ARM_PACK_IO, "out of memory") : root_modules(&x, root, &mods);   // check_root
    while (dest && strlen(dest) > 1 && dest[strlen(dest) - 1] == '/') dest[strlen(dest) - 1] = 0;
    if (!code && !mods.n) code = fail(&x, RB_S2ARM_PACK_INVALID, "%s has no rewritten module (*.fixups.tsv)", root);
    if (!code && !is_file(npdm)) code = fail(&x, RB_S2ARM_PACK_INVALID, "%s has no main.npdm", root);
    if (!code) code = npdm_gid(&x, npdm, gid);
    if (!code) {   // ship_ext.py program_dirs: programs/1 with a main.npdm and rewritten modules starts a multi-program collection
        char *p1 = pjoin(root, "programs/1"), *pn = p1 ? pjoin(p1, "main.npdm") : NULL;
        list_t pm = {0};
        if (!p1 || !pn) code = fail(&x, RB_S2ARM_PACK_IO, "out of memory");
        else if (is_file(pn) && !root_modules(&x, p1, &pm) && pm.n)
            code = fail(&x, RB_S2ARM_PACK_INVALID, "multi-program collections (programs/<n>/) are not supported");
        list_free(&pm);
        free(p1);
        free(pn);
    }
    // The texts are checked before anything is written.
    if (!code && r->save_identity) code = save_identity_text(&x, r->save_identity, &si);
    if (!code && r->write_launch_ctx) {   // ship_ext.py ctx_text, host values where given
        char d_images[96], d_module[64], d_data[96], d_docs[64];
        snprintf(d_images, sizeof d_images, "@bundle/Frameworks/S2AImages-%s.dylib", gid);
        snprintf(d_module, sizeof d_module, "@bundle/Games/%s", gid);
        snprintf(d_docs, sizeof d_docs, "@home/Documents/games/%s", gid);
        snprintf(d_data, sizeof d_data, "%s/\xe8\xb5\x84\xe6\xba\x90\xe5\x8c\x85", d_docs);   // ".../资源包"
        const char *vi = r->ctx_images ? r->ctx_images : d_images, *vm = r->ctx_module_dir ? r->ctx_module_dir : d_module,
                   *vg = r->ctx_game_data ? r->ctx_game_data : d_data, *vd = r->ctx_docs ? r->ctx_docs : d_docs;
        if (!ctx_value_ok(vi) || !ctx_value_ok(vm) || !ctx_value_ok(vg) || !ctx_value_ok(vd) || strpbrk(vi, "\t\n\r") || strpbrk(vm, "\t\n\r") ||
            strpbrk(vg, "\t\n\r") || strpbrk(vd, "\t\n\r"))
            code = fail(&x, RB_S2ARM_PACK_INVALID, "launch.ctx values must be absolute or start with @bundle/ or @home/");
        else if (!buf_fmt(&c, "version\t1\ngame_id\t%s\n", gid) || !buf_str(&c, "images\t") || !buf_str(&c, vi) || !buf_str(&c, "\nmodule_dir\t") ||
                 !buf_str(&c, vm) || !buf_str(&c, "\ngame_data\t") || !buf_str(&c, vg) || !buf_str(&c, "\ndocs\t") || !buf_str(&c, vd) ||
                 !buf_str(&c, "\n"))
            code = fail(&x, RB_S2ARM_PACK_IO, "out of memory");
    }
    // The directory is built in <module_dir>.tmp and replaces the previous one at the end, as ship_ext.py
    // assembles a fresh container: no file of an earlier version is left behind.
    if (!code) {
        tmp = pcat(dest, ".tmp");
        if (!tmp) code = fail(&x, RB_S2ARM_PACK_IO, "out of memory");
        else {
            rmtree(tmp, 0);
            if (makedirs(tmp)) code = fail(&x, RB_S2ARM_PACK_IO, "cannot create %s", tmp);
        }
    }
    static const char *const suffixes[3] = {".fixups.tsv", ".gates.tsv", ".widen.tsv"};
    for (size_t i = 0; i < mods.n && !code; i++)
        for (int k = 0; k < 3 && !code; k++) {
            char *name = pcat(mods.v[i], suffixes[k]), *src = name ? pjoin(root, name) : NULL, *dst = name ? pjoin(tmp, name) : NULL;
            if (!name || !src || !dst) code = fail(&x, RB_S2ARM_PACK_IO, "out of memory");
            else if (is_file(src) || k != 2) {   // fixups and gates are required, widen only when present
                if (copy_file(&x, src, dst, NULL)) code = fail(&x, RB_S2ARM_PACK_INVALID, "cannot copy %s", name);
            }
            free(name);
            free(src);
            free(dst);
        }
    if (!code) {
        char *dst = pjoin(tmp, "main.npdm");
        if (!dst || copy_file(&x, npdm, dst, NULL)) code = fail(&x, RB_S2ARM_PACK_IO, "cannot copy main.npdm");
        free(dst);
    }
    if (!code) {   // the shell's tables (pathlib glob, sorted, regular files only)
        list_t names = {0};
        if (listdir(root, &names)) code = fail(&x, RB_S2ARM_PACK_IO, "cannot list %s", root);
        for (size_t t = 0; t < sizeof APP_TABLES / sizeof *APP_TABLES && !code; t++)
            for (size_t i = 0; i < names.n && !code; i++) {
                if (!table_match(APP_TABLES[t], names.v[i])) continue;
                char *src = pjoin(root, names.v[i]), *dst = pjoin(tmp, names.v[i]);
                if (!src || !dst) code = fail(&x, RB_S2ARM_PACK_IO, "out of memory");
                else if (is_file(src) && copy_file(&x, src, dst, NULL)) code = fail(&x, RB_S2ARM_PACK_IO, "cannot copy %s", names.v[i]);
                free(src);
                free(dst);
            }
        list_free(&names);
    }
    static const char *const art[2] = {"icon.jpg", "banner.jpg"};   // icon, and the banner when the root has one (_place_banner)
    for (int k = 0; k < 2 && !code; k++) {
        char *src = pjoin(root, art[k]), *dst = pjoin(tmp, art[k]);
        if (!src || !dst) code = fail(&x, RB_S2ARM_PACK_IO, "out of memory");
        else if (is_file(src) && copy_file(&x, src, dst, NULL)) code = fail(&x, RB_S2ARM_PACK_IO, "cannot copy %s", art[k]);
        free(src);
        free(dst);
    }
    struct {
        const char *name;
        const buf_t *text;
        int when;
    } texts[2] = {{"save-identity.json", &si, r->save_identity != NULL}, {"launch.ctx", &c, r->write_launch_ctx}};
    for (int k = 0; k < 2 && !code; k++) {
        if (!texts[k].when) continue;
        char *dst = pjoin(tmp, texts[k].name);
        if (!dst || write_all(dst, texts[k].text->p, texts[k].text->n)) code = fail(&x, RB_S2ARM_PACK_IO, "cannot write %s", texts[k].name);
        free(dst);
    }
    if (!code && r->images_path) {
        char *dir = sdup(r->images_path), *slash = dir ? strrchr(dir, '/') : NULL;
        if (!dir) code = fail(&x, RB_S2ARM_PACK_IO, "out of memory");
        else if (slash && slash != dir) {
            *slash = 0;
            if (makedirs(dir)) code = fail(&x, RB_S2ARM_PACK_IO, "cannot create %s", dir);
        }
        free(dir);
        if (!code) code = rb_s2arm_image_pack(root, (const char *const *)mods.v, mods.n, r->images_path, error, error_size);
    }
    if (!code) {
        rmtree(dest, 0);
        if (rename(tmp, dest)) code = fail(&x, RB_S2ARM_PACK_IO, "cannot rename %s to %s", tmp, dest);
    }
    if (code && tmp) rmtree(tmp, 0);
    free(si.p);
    free(c.p);
    free(tmp);
    free(dest);
    free(npdm);
    list_free(&mods);
    return code;
}

// ---------------- the empty direct library (graphics/tools/direct/runtime_only_lib.sh) ----------------
int rb_s2arm_direct_skeleton(const char *root, const char *chain, const char *tag, const char *reason, char *error, size_t error_size) {
    ctx_t x = {error, error_size, NULL, NULL};
    if (!root || !chain || !tag || !reason) return fail(&x, RB_S2ARM_PACK_INVALID, "incomplete request");
    size_t cl = strlen(chain);
    if (!cl || cl > 12 || strchr(chain, '/') || !strcmp(chain, ".") || !strcmp(chain, ".."))
        return fail(&x, RB_S2ARM_PACK_INVALID, "direct library chain must be 1 to 12 characters");
    // the program id: title_id of unpack.tsv, upper case (stage_direct.sh awk)
    char *up = pjoin(root, "unpack.tsv");
    uint8_t *u = NULL;
    size_t un = 0;
    int r = up ? read_all(up, 1u << 20, &u, &un) : -1;
    free(up);
    if (r) return fail(&x, RB_S2ARM_PACK_INVALID, "cannot read unpack.tsv");
    char tid[64] = "";
    for (size_t i = 0; i < un;) {
        size_t j = i;
        while (j < un && u[j] != '\n') j++;
        if (j - i > 9 && !memcmp(u + i, "title_id\t", 9)) {
            size_t k = i + 9, e = k;
            while (e < j && u[e] != '\t') e++;
            if (e - k < sizeof tid) {
                for (size_t q = 0; q < e - k; q++) tid[q] = (char)(u[k + q] >= 'a' && u[k + q] <= 'z' ? u[k + q] - 32 : u[k + q]);
                tid[e - k] = 0;
            }
            break;
        }
        i = j + 1;
    }
    free(u);
    if (!tid[0]) return fail(&x, RB_S2ARM_PACK_INVALID, "unpack.tsv has no title_id");
    char *shaders = pjoin(root, "shaders"), *d = shaders ? pjoin(shaders, "direct") : NULL, *tmp = d ? pcat(d, ".tmp") : NULL;
    char *bdir = NULL;
    int code = 0;
    if (!shaders || !d || !tmp) code = fail(&x, RB_S2ARM_PACK_IO, "out of memory");
    if (!code) {
        rmtree(tmp, 0);
        char bname[32];
        snprintf(bname, sizeof bname, "b-%s", chain);
        bdir = pjoin(tmp, bname);
        if (!bdir || makedirs(bdir)) code = fail(&x, RB_S2ARM_PACK_IO, "cannot create the direct library");
    }
    if (!code) {
        uint8_t lib[48] = {'S', '2', 'A', 'L', 'I', 'B', 0, 0, 1};   // magic, version 1, 0 entries, 0 shards, the chain (12 bytes), 12 zero bytes
        memcpy(lib + 24, chain, cl);
        buf_t in = {0}, ro = {0};
        int ok = buf_fmt(&in, "game\t%s\ninputs\truntime-only-", tid) && buf_str(&in, tag) && buf_str(&in, "\n") &&
                 buf_str(&ro, "\xe6\x9c\xac\xe6\xac\xbe\xe7\xa6\xbb\xe7\xba\xbf\xe7\x9b\xb4\xe8\xbf\x9e\xe5\xba\x93\xe4\xb8\xba\xe7\xa9\xba\xef\xbc\x88"
                                   "\xe7\xa6\xbb\xe7\xba\xbf 0 \xe6\x94\xaf\xef\xbc\x89\xef\xbc\x8c\xe8\xbf\x90\xe8\xa1\x8c\xe6\x97\xb6\xe9\xa6\x96\xe9"
                                   "\x81\x87\xe7\x8e\xb0\xe7\xbc\x96\n") &&
                 buf_str(&ro, reason);
        // The texts runtime_only_lib.sh writes (Chinese, byte for byte): runtime_only.txt "this game's offline direct
        // library is empty (0 offline shaders), compiled at first use" + the reason; the two empty tables' comments.
        static const char facts[] = "# \xe8\xbf\x90\xe8\xa1\x8c\xe6\x97\xb6\xe7\x8e\xb0\xe7\xbc\x96\xe7\xa9\xba\xe5\xba\x93\xef\xbc\x9a\xe7\xa9\xba\xe7\xad\x94"
                                    "\xe6\xa1\x88\xe8\xa1\xa8 = \xe5\x85\xa8\xe9\x83\xa8\xe6\x8c\x89\xe7\xbc\xba\xe7\x9c\x81\xe7\xad\x94\xef\xbc\x88graphics/"
                                    "tools/direct/dsh/Tables.cs\xef\xbc\x89\n";
        static const char pairs[] = "# \xe8\xbf\x90\xe8\xa1\x8c\xe6\x97\xb6\xe7\x8e\xb0\xe7\xbc\x96\xe7\xa9\xba\xe5\xba\x93\xef\xbc\x9a\xe7\xa9\xba\xe9\x85\x8d"
                                    "\xe5\xaf\xb9\xe8\xa1\xa8\n";
        struct {
            const char *name;
            const void *data;
            size_t n;
        } files[] = {{"shader_map.tsv", "", 0},       {"keys.tsv", "", 0},           {"shader_facts.tsv", facts, sizeof facts - 1},
                     {"shader_pairs.tsv", pairs, sizeof pairs - 1}, {"runtime_only.txt", ro.p, ro.n}};
        char *libp = pjoin(bdir, "lib.idx"), *inp = pjoin(bdir, "inputs.tsv");
        ok = ok && libp && inp && !write_all(libp, lib, sizeof lib) && !write_all(inp, in.p, in.n);
        for (size_t i = 0; ok && i < sizeof files / sizeof *files; i++) {
            char *p = pjoin(tmp, files[i].name);
            ok = p && !write_all(p, files[i].data, files[i].n);
            free(p);
        }
        free(libp);
        free(inp);
        free(in.p);
        free(ro.p);
        if (!ok) code = fail(&x, RB_S2ARM_PACK_IO, "cannot write the direct library");
    }
    if (!code) {
        rmtree(d, 0);
        if (makedirs(shaders) || rename(tmp, d)) code = fail(&x, RB_S2ARM_PACK_IO, "cannot place shaders/direct");
    }
    if (code && tmp) rmtree(tmp, 0);
    free(shaders);
    free(d);
    free(tmp);
    free(bdir);
    return code;
}

// ---------------- resource pack (pack/pkg_srcs.py srcs + pack/pack.py) ----------------
typedef struct {
    char *rel, *src;   // path in the pack, source file
    uint64_t size;
    uint8_t sha[32];
} pfile_t;
typedef struct {
    pfile_t *v;
    size_t n, cap;
} pfiles_t;

static void pfiles_free(pfiles_t *f) {
    for (size_t i = 0; i < f->n; i++) {
        free(f->v[i].rel);
        free(f->v[i].src);
    }
    free(f->v);
    memset(f, 0, sizeof *f);
}
static int pfiles_add(pfiles_t *f, char *rel, char *src, uint64_t size) {
    if (!rel || !src) {
        free(rel);
        free(src);
        return 0;
    }
    if (f->n == f->cap) {
        size_t cap = f->cap ? f->cap * 2 : 256;
        pfile_t *nv = realloc(f->v, cap * sizeof *nv);
        if (!nv) {
            free(rel);
            free(src);
            return 0;
        }
        f->v = nv;
        f->cap = cap;
    }
    f->v[f->n].rel = rel;
    f->v[f->n].src = src;
    f->v[f->n].size = size;
    f->n++;
    return 1;
}

// One source of pack.py: a single file under its name, or os.walk(top) with sorted directories and
// files, symlinked directories listed but not entered, .DS_Store and ._* skipped.
static int walk_source(ctx_t *x, pfiles_t *out, const char *name, const char *dir, const char *rel, int depth) {
    if (depth > MAX_DEPTH) return fail(x, RB_S2ARM_PACK_INVALID, "directory tree too deep: %s", dir);
    list_t names = {0};
    int r = listdir(dir, &names);
    if (r == -1) return 0;   // os.walk skips what it cannot list
    if (r) return fail(x, RB_S2ARM_PACK_IO, "out of memory");
    list_t dirs = {0};
    int code = 0;
    // The stats are relative to the directory (fstatat), as stat(p) but without resolving its path again for each file.
    int dfd = open(dir, O_RDONLY | O_DIRECTORY);
    for (size_t i = 0; i < names.n && !code; i++) {   // files of this directory first (sorted), then the subdirectories
        char *p = pjoin(dir, names.v[i]);
        if (!p) {
            code = fail(x, RB_S2ARM_PACK_IO, "out of memory");
            break;
        }
        unsigned char type = (unsigned char)names.v[i][strlen(names.v[i]) + 1];
        if (type == DT_DIR) {   // a real directory (the listing says so: neither a stat nor an lstat is needed)
            if (!list_add(&dirs, sdup(names.v[i]))) code = fail(x, RB_S2ARM_PACK_IO, "out of memory");
            free(p);
            continue;
        }
        struct stat st;
        int st_ok = (dfd >= 0 ? fstatat(dfd, names.v[i], &st, 0) : stat(p, &st)) == 0;
        if (st_ok && S_ISDIR(st.st_mode)) {   // a link to a directory is listed, not entered
            if (type == DT_UNKNOWN && !is_link(p) && !list_add(&dirs, sdup(names.v[i]))) code = fail(x, RB_S2ARM_PACK_IO, "out of memory");
            free(p);
            continue;
        }
        const char *n = names.v[i];
        if (!strcmp(n, ".DS_Store") || !strncmp(n, "._", 2)) {
            free(p);
            continue;
        }
        char *sub = *rel ? pjoin(rel, n) : sdup(n), *full = sub ? pjoin(name, sub) : NULL;
        if (!sub || !full) code = fail(x, RB_S2ARM_PACK_IO, "out of memory");
        else if (strpbrk(full, "\t\n")) code = fail(x, RB_S2ARM_PACK_INVALID, "path with a tab or a newline, index.tsv cannot hold it: %s", full);
        else if (!st_ok) code = fail(x, RB_S2ARM_PACK_IO, "cannot stat %s", p);
        else if (!S_ISREG(st.st_mode)) code = fail(x, RB_S2ARM_PACK_INVALID, "%s is not a regular file", p);
        else if (!pfiles_add(out, full, p, (uint64_t)st.st_size)) code = fail(x, RB_S2ARM_PACK_IO, "out of memory");
        else {
            full = NULL;
            p = NULL;
        }
        free(sub);
        free(full);
        free(p);
    }
    if (dfd >= 0) close(dfd);
    for (size_t i = 0; i < dirs.n && !code; i++) {
        char *p = pjoin(dir, dirs.v[i]), *sub = *rel ? pjoin(rel, dirs.v[i]) : sdup(dirs.v[i]);
        code = p && sub ? walk_source(x, out, name, p, sub, depth + 1) : fail(x, RB_S2ARM_PACK_IO, "out of memory");
        free(p);
        free(sub);
    }
    list_free(&dirs);
    list_free(&names);
    return code;
}

static int add_source(ctx_t *x, pfiles_t *out, const char *name, const char *src) {
    if (!exists(src)) return fail(x, RB_S2ARM_PACK_INVALID, "source missing: %s", src);
    if (is_file(src)) {
        struct stat st;
        if (stat(src, &st)) return fail(x, RB_S2ARM_PACK_IO, "cannot stat %s", src);
        return pfiles_add(out, sdup(name), sdup(src), (uint64_t)st.st_size) ? 0 : fail(x, RB_S2ARM_PACK_IO, "out of memory");
    }
    return walk_source(x, out, name, src, "", 0);
}

static int ls_cmp(const void *pa, const void *pb) {   // pkg_srcs.ls: hidden names last, then byte order
    const char *a = *(char *const *)pa, *b = *(char *const *)pb;
    if ((a[0] == '.') != (b[0] == '.')) return a[0] == '.' ? 1 : -1;
    return strcmp(a, b);
}

// The files under the RomFS and DLC links, read in place and hashed by up to HASH_THREADS threads: the whole RomFS
// (22 GB for Mario Kart World) went through one thread before, at about 110 MB/s on the phone (pack step 204 s of a
// 427 s preparation, IPA 731). Each file's digest goes to its own slot, so index.tsv is the same in any order; the
// first failure wins and stops the others. Progress and the request's callbacks other than `cancelled` stay on the
// calling thread (the bridge's progress throttle is not thread-safe); `cancelled` is polled by every thread, between
// 4 MiB chunks, as before.
#define HASH_THREADS 4
#define HASH_CHUNK ((size_t)4 << 20)

typedef struct {
    ctx_t *x;                         // x->error is written once, under lock, by the first failure
    const rb_s2arm_resource_request *r;
    pfile_t *files;
    const size_t *todo;               // indexes into files, in index order
    size_t count;
    uint64_t total;
    int inline_progress;              // 1: the work runs on the calling thread (no thread could start)
    atomic_size_t next;
    atomic_uint_least64_t done;       // bytes hashed so far, including what came before (copies)
    atomic_int failed;
    pthread_mutex_t lock;
    pthread_cond_t idle;              // signalled when the last thread ends
    int active;                       // threads still working, under lock
    int code;                         // the first failure, under lock
} hash_pool_t;

#if defined(__GNUC__)
__attribute__((format(printf, 3, 4)))
#endif
static int pool_fail(hash_pool_t *p, int code, const char *fmt, ...) {
    pthread_mutex_lock(&p->lock);
    if (!p->code) {
        p->code = code;
        if (p->x->error && p->x->error_size) {
            va_list ap;
            va_start(ap, fmt);
            vsnprintf(p->x->error, p->x->error_size, fmt, ap);
            va_end(ap);
        }
        atomic_store(&p->failed, 1);
    }
    pthread_mutex_unlock(&p->lock);
    return code;
}

static int hash_one(hash_pool_t *p, pfile_t *f, uint8_t *b) {
    int fd = open(f->src, O_RDONLY);
    if (fd < 0) return pool_fail(p, RB_S2ARM_PACK_IO, "cannot read %s", f->src);
    s2arm_sha256_ctx h;
    s2arm_sha256_init(&h);
    uint64_t got = 0;
    int code = 0;
    for (;;) {
        if (atomic_load(&p->failed)) {   // another file failed: stop without a message of our own
            code = -1;
            break;
        }
        if (p->r->cancelled && p->r->cancelled(p->r->context)) {
            code = pool_fail(p, RB_S2ARM_PACK_CANCELLED, "cancelled");
            break;
        }
        ssize_t k = read(fd, b, HASH_CHUNK);
        if (k < 0 && errno == EINTR) continue;
        if (k < 0) {
            code = pool_fail(p, RB_S2ARM_PACK_IO, "cannot read %s", f->src);
            break;
        }
        if (k == 0) break;
        s2arm_sha256_update(&h, b, (size_t)k);
        got += (uint64_t)k;
        uint64_t done = atomic_fetch_add(&p->done, (uint64_t)k) + (uint64_t)k;
        if (p->inline_progress && p->r->progress) p->r->progress(p->r->context, done, p->total);
    }
    close(fd);
    if (!code && got != f->size) code = pool_fail(p, RB_S2ARM_PACK_IO, "%s changed while being read", f->src);
    if (!code) s2arm_sha256_final(&h, f->sha);
    return code;
}

static void *hash_worker(void *arg) {
    hash_pool_t *p = arg;
    uint8_t *b = malloc(HASH_CHUNK);   // one buffer per thread, not one per file
    if (!b) pool_fail(p, RB_S2ARM_PACK_IO, "out of memory");
    while (b && !atomic_load(&p->failed)) {
        size_t k = atomic_fetch_add(&p->next, 1);
        if (k >= p->count || hash_one(p, &p->files[p->todo[k]], b)) break;
    }
    free(b);
    pthread_mutex_lock(&p->lock);
    if (--p->active == 0) pthread_cond_signal(&p->idle);
    pthread_mutex_unlock(&p->lock);
    return NULL;
}

static int hash_linked(ctx_t *x, const rb_s2arm_resource_request *r, pfile_t *files, const size_t *todo, size_t count,
                       uint64_t *done, uint64_t total) {
    hash_pool_t p;
    memset(&p, 0, sizeof p);
    p.x = x, p.r = r, p.files = files, p.todo = todo, p.count = count, p.total = total;
    atomic_init(&p.next, 0);
    atomic_init(&p.done, *done);
    atomic_init(&p.failed, 0);
    if (pthread_mutex_init(&p.lock, NULL)) return fail(x, RB_S2ARM_PACK_IO, "cannot create a lock");
    if (pthread_cond_init(&p.idle, NULL)) {
        pthread_mutex_destroy(&p.lock);
        return fail(x, RB_S2ARM_PACK_IO, "cannot create a condition");
    }
    long cpus = sysconf(_SC_NPROCESSORS_ONLN);
    size_t want = cpus < 1 ? 1 : cpus > HASH_THREADS ? HASH_THREADS : (size_t)cpus;
    if (want > count) want = count;
    pthread_t threads[HASH_THREADS];
    size_t started = 0;
    pthread_mutex_lock(&p.lock);
    for (size_t i = 0; i < want; i++) {
        if (pthread_create(&threads[started], NULL, hash_worker, &p)) break;
        started++;
        p.active++;   // under lock: a thread that ends at once waits for it before counting itself out
    }
    if (!started) {   // no thread: the same work here, with progress after each chunk as before
        pthread_mutex_unlock(&p.lock);
        p.inline_progress = 1;
        p.active = 1;
        hash_worker(&p);
    } else {
        while (p.active > 0) {   // progress every 100 ms from this thread, until the last thread signals its end
            struct timespec deadline;
            clock_gettime(CLOCK_REALTIME, &deadline);
            deadline.tv_nsec += 100 * 1000000L;
            if (deadline.tv_nsec >= 1000000000L) deadline.tv_sec++, deadline.tv_nsec -= 1000000000L;
            pthread_cond_timedwait(&p.idle, &p.lock, &deadline);
            if (p.active > 0 && r->progress) {
                pthread_mutex_unlock(&p.lock);
                r->progress(r->context, atomic_load(&p.done), total);
                pthread_mutex_lock(&p.lock);
            }
        }
        pthread_mutex_unlock(&p.lock);
        for (size_t i = 0; i < started; i++) pthread_join(threads[i], NULL);
    }
    *done = atomic_load(&p.done);
    int code = p.code;
    pthread_cond_destroy(&p.idle);
    pthread_mutex_destroy(&p.lock);
    if (!code && r->progress) r->progress(r->context, *done, total);
    return code;
}

int rb_s2arm_resource_pack(const rb_s2arm_resource_request *r, char *error, size_t error_size) {
    ctx_t x = {error, error_size, r ? r->cancelled : NULL, r ? r->context : NULL};
    if (!r || !r->root || !r->pack_dir || !*r->pack_dir) return fail(&x, RB_S2ARM_PACK_INVALID, "incomplete request");
    const char *root = r->root;
    int code = 0;
    char *pack = NULL, *tmp = NULL, *parent = NULL, *final_parent = NULL;
    pfiles_t files = {0};
    buf_t index = {0}, manifest = {0};
    struct {
        const char *name;
        char *src;
        int link;   // 1: a relative symlink to the source; 0: copies
    } srcs[256];
    int ns = 0;
    {   // pkg_srcs.srcs(w), in its order
        char *p;
        if ((p = pjoin(root, "ui_overlay/romfs")) && is_dir(p)) code = fail(&x, RB_S2ARM_PACK_INVALID, "a RomFS layout overlay (ui_overlay/romfs) is not supported");
        free(p);
        srcs[ns].name = "exefs/main.npdm", srcs[ns].src = pjoin(root, "exefs/main.npdm"), srcs[ns++].link = 0;
        srcs[ns].name = "romfs", srcs[ns].src = pjoin(root, "romfs"), srcs[ns++].link = 1;
        if ((p = pjoin(root, "romfs.s2aidx")) && nonempty_file(p)) srcs[ns].name = "romfs.s2aidx", srcs[ns].src = p, srcs[ns++].link = 0;
        else free(p);
        if ((p = pjoin(root, "ctl/control.nacp")) && is_file(p)) srcs[ns].name = "ctl/control.nacp", srcs[ns].src = p, srcs[ns++].link = 0;
        else free(p);
        p = r->systemdata_dir ? sdup(r->systemdata_dir) : pjoin(root, "systemdata");
        if (p && is_dir(p)) srcs[ns].name = "systemdata", srcs[ns].src = p, srcs[ns++].link = r->systemdata_link;
        else free(p);
        if ((p = pjoin(root, "patch.tsv")) && nonempty_file(p)) srcs[ns].name = "patch.tsv", srcs[ns].src = p, srcs[ns++].link = 0;
        else free(p);
        if ((p = pjoin(root, "aoc.tsv")) && nonempty_file(p)) {
            srcs[ns].name = "aoc.tsv", srcs[ns].src = p, srcs[ns++].link = 0;
            if ((p = pjoin(root, "aoc")) && is_dir(p)) srcs[ns].name = "aoc", srcs[ns].src = p, srcs[ns++].link = 1;
            else free(p);
        } else
            free(p);
        char *sd = pjoin(root, "shaders/direct");
        list_t names = {0};
        if (sd && listdir(sd, &names) == 0 && names.n) qsort(names.v, names.n, sizeof *names.v, ls_cmp);
        for (size_t i = 0; i < names.n && !code; i++) {
            if (!strcmp(names.v[i], "link")) continue;
            if (ns >= 250) {
                code = fail(&x, RB_S2ARM_PACK_INVALID, "too many entries in shaders/direct");
                break;
            }
            char *rel = pjoin("shaders/direct", names.v[i]);
            srcs[ns].name = rel, srcs[ns].src = pjoin(sd, names.v[i]), srcs[ns++].link = 2;   // 2: copies, name owned
        }
        list_free(&names);
        free(sd);
        if ((p = pjoin(root, "programs/1/exefs/main.npdm")) && is_file(p)) code = fail(&x, RB_S2ARM_PACK_INVALID, "multi-program collections are not supported");
        free(p);
        for (int i = 0; i < ns && !code; i++)
            if (!srcs[i].src || !srcs[i].name) code = fail(&x, RB_S2ARM_PACK_IO, "out of memory");
    }
    // No path can come twice (pack.py's merge only serves the refused ui_overlay): every source has its own
    // top-level name, and a walk lists each path once.
    for (int i = 0; i < ns && !code; i++) code = add_source(&x, &files, srcs[i].name, srcs[i].src);
    // the pack in <pack_dir>.tmp: copies and relative symlinks
    if (!code) {
        pack = sdup(r->pack_dir);
        while (pack && strlen(pack) > 1 && pack[strlen(pack) - 1] == '/') pack[strlen(pack) - 1] = 0;
        tmp = pack ? pcat(pack, ".tmp") : NULL;
        parent = pack ? sdup(pack) : NULL;
        char *slash = parent ? strrchr(parent, '/') : NULL;
        if (!tmp || !parent) code = fail(&x, RB_S2ARM_PACK_IO, "out of memory");
        else {
            if (slash == parent) slash[1] = 0;
            else if (slash) *slash = 0;
            else strcpy(parent, ".");
            if (makedirs(parent)) code = fail(&x, RB_S2ARM_PACK_IO, "cannot create %s", parent);
        }
        if (!code) {
            char *rp = realpath(parent, NULL);
            const char *base = strrchr(pack, '/') ? strrchr(pack, '/') + 1 : pack;
            final_parent = rp ? pjoin(rp, base) : NULL;
            free(rp);
            if (!final_parent) code = fail(&x, RB_S2ARM_PACK_IO, "cannot resolve %s", parent);
        }
        if (!code) {
            rmtree(tmp, 0);
            if (makedirs(tmp)) code = fail(&x, RB_S2ARM_PACK_IO, "cannot create %s", tmp);
        }
    }
    uint64_t total = 0, done = 0;
    for (size_t i = 0; i < files.n; i++) total += files.v[i].size;
    for (int i = 0; i < ns && !code; i++) {   // links first: the files under them are hashed in place
        if (srcs[i].link != 1) continue;
        char *at = pjoin(tmp, srcs[i].name), *fp = pjoin(final_parent, srcs[i].name);
        char *lp = fp ? sdup(fp) : NULL, *ls = lp ? strrchr(lp, '/') : NULL;
        if (ls) *ls = 0;   // the resolved directory the link will live in
        char *atp = at ? sdup(at) : NULL, *as = atp ? strrchr(atp, '/') : NULL;
        if (as) *as = 0;
        if (!at || !fp || !lp || !atp) code = fail(&x, RB_S2ARM_PACK_IO, "out of memory");
        else if (makedirs(atp) || relative_symlink(srcs[i].src, lp, at)) code = fail(&x, RB_S2ARM_PACK_IO, "cannot link %s", srcs[i].name);
        free(at);
        free(fp);
        free(lp);
        free(atp);
    }
    size_t *linked_files = files.n ? malloc(files.n * sizeof *linked_files) : NULL, nlinked = 0;
    if (files.n && !linked_files && !code) code = fail(&x, RB_S2ARM_PACK_IO, "out of memory");
    for (size_t i = 0; i < files.n && !code; i++) {   // the copies here, in order; the linked files are hashed below
        pfile_t *f = &files.v[i];
        int linked = 0;
        for (int k = 0; k < ns; k++)
            if (srcs[k].link == 1 && !strncmp(f->rel, srcs[k].name, strlen(srcs[k].name)) && f->rel[strlen(srcs[k].name)] == '/') linked = 1;
        if (linked) {
            linked_files[nlinked++] = i;
            continue;
        }
        char *dst = pjoin(tmp, f->rel), *dir = dst ? sdup(dst) : NULL, *slash = dir ? strrchr(dir, '/') : NULL;
        if (slash) *slash = 0;
        if (!dst || !dir) code = fail(&x, RB_S2ARM_PACK_IO, "out of memory");
        else if (makedirs(dir)) code = fail(&x, RB_S2ARM_PACK_IO, "cannot create %s", dir);
        else {
            int c = copy_file(&x, f->src, dst, f->sha);
            if (c == -5) code = fail(&x, RB_S2ARM_PACK_CANCELLED, "cancelled");
            else if (c) code = fail(&x, RB_S2ARM_PACK_IO, "cannot copy %s", f->src);
            done += f->size;
            if (!code && r->progress) r->progress(r->context, done, total);
        }
        free(dst);
        free(dir);
    }
    if (!code && nlinked) code = hash_linked(&x, r, files.v, linked_files, nlinked, &done, total);
    free(linked_files);
    if (!code) {   // index.tsv, manifest.json (version 2), then the device's bookkeeping
        char hex[65];
        for (size_t i = 0; i < files.n && !code; i++) {
            s2arm_sha256_hex(files.v[i].sha, hex);
            if (!buf_str(&index, files.v[i].rel) || !buf_fmt(&index, "\t%llu\t%s\n", (unsigned long long)files.v[i].size, hex))
                code = fail(&x, RB_S2ARM_PACK_IO, "out of memory");
        }
        uint8_t digest[32];
        s2arm_sha256(index.p ? index.p : (const uint8_t *)"", index.n, digest);
        s2arm_sha256_hex(digest, hex);
        if (!code && !buf_fmt(&manifest, "{\n \"version\": 2,\n \"files\": %zu,\n \"total\": %llu,\n \"index_sha256\": \"%s\"\n}", files.n,
                              (unsigned long long)total, hex))
            code = fail(&x, RB_S2ARM_PACK_IO, "out of memory");
        struct {
            const char *name;
            const void *data;
            size_t n;
            int when;
        } out[] = {{"index.tsv", index.p, index.n, 1},
                   {"manifest.json", manifest.p, manifest.n, 1},
                   {"index.applied.tsv", index.p, index.n, r->write_applied},
                   {".applied", hex, 64, r->write_applied}};
        for (size_t i = 0; i < sizeof out / sizeof *out && !code; i++) {
            if (!out[i].when) continue;
            char *p = pjoin(tmp, out[i].name);
            if (!p || write_all(p, out[i].data ? out[i].data : "", out[i].n)) code = fail(&x, RB_S2ARM_PACK_IO, "cannot write %s", out[i].name);
            free(p);
        }
    }
    if (!code) {
        rmtree(pack, 0);
        if (rename(tmp, pack)) code = fail(&x, RB_S2ARM_PACK_IO, "cannot rename %s to %s", tmp, pack);
    }
    if (code && tmp) rmtree(tmp, 0);
    for (int i = 0; i < ns; i++) {
        free(srcs[i].src);
        if (srcs[i].link == 2) free((char *)srcs[i].name);
    }
    pfiles_free(&files);
    free(index.p);
    free(manifest.p);
    free(pack);
    free(tmp);
    free(parent);
    free(final_parent);
    return code;
}
