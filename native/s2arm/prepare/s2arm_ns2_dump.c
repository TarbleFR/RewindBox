// See s2arm_ns2_dump.h. Port of S2Arm pack/ns2_dump.py (Apache-2.0, pinned commit in
// tools/s2arm_prototype/pin.json). Every red line and every Python exception of the
// original (struct.error, OSError, UnicodeEncodeError, LZ4 errors) is an explicit check
// here and fails the call; os.walk semantics are kept (unreadable directories skipped,
// symlinks to directories listed as directories and not entered, ".listing" skipped).
// Relative paths are sorted in byte order, which is Python's code-point order for UTF-8.
#if defined(__APPLE__)
#define _DARWIN_C_SOURCE
#else
#define _XOPEN_SOURCE 700   // realpath, symlink
#endif
#include "s2arm_ns2_dump.h"
#include "lz4.h"
#include "s2arm_dirent.h"
#include "s2arm_zbic.h"

#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>
#if defined(__APPLE__)
#include <sys/clonefile.h>
#endif

#define NACP_SIZE 0x4000
#define MAX_DEPTH 256
#define DEFAULT_MODULE_CAP ((size_t)1 << 30)   // default cap on one module's decoded image (see max_module_bytes)
#define KEY_TAG "rewindbox-ns2-dump-1"

typedef struct {
    char *error;
    size_t error_size;
    const rb_s2arm_ns2_dump_request *request;
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

#if defined(__GNUC__)
__attribute__((format(printf, 2, 3)))
#endif
static void note(ctx_t *x, const char *fmt, ...) {
    if (!x->request || !x->request->note) return;
    char line[1024];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(line, sizeof line, fmt, ap);
    va_end(ap);
    x->request->note(x->request->context, line);
}

static int cancelled(ctx_t *x) { return x->request && x->request->cancelled && x->request->cancelled(x->request->context); }

static size_t module_cap(const ctx_t *x) {
    size_t cap = x->request && x->request->max_module_bytes ? x->request->max_module_bytes : DEFAULT_MODULE_CAP;
    return cap < RB_S2ARM_ZBIC_FILE_CAP ? cap : RB_S2ARM_ZBIC_FILE_CAP;
}

static uint32_t le32(const uint8_t *p) { return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24; }
static uint64_t le64(const uint8_t *p) { return (uint64_t)le32(p) | (uint64_t)le32(p + 4) << 32; }
static void put32(uint8_t *p, uint32_t v) {
    for (int i = 0; i < 4; i++) p[i] = (uint8_t)(v >> (8 * i));
}
static void put64(uint8_t *p, uint64_t v) {
    for (int i = 0; i < 8; i++) p[i] = (uint8_t)(v >> (8 * i));
}

// ---------------- strings and paths ----------------
typedef struct {
    char *p;
    size_t n, cap;
} sb_t;

static int sb_add(sb_t *s, const char *data, size_t n) {
    if (s->n + n + 1 > s->cap) {
        size_t cap = s->cap ? s->cap : 256;
        while (cap < s->n + n + 1) cap *= 2;
        char *np = realloc(s->p, cap);
        if (!np) return 0;
        s->p = np;
        s->cap = cap;
    }
    memcpy(s->p + s->n, data, n);
    s->n += n;
    s->p[s->n] = 0;
    return 1;
}
static int sb_str(sb_t *s, const char *t) { return sb_add(s, t, strlen(t)); }
#if defined(__GNUC__)
__attribute__((format(printf, 2, 3)))
#endif
static int sb_fmt(sb_t *s, const char *fmt, ...) {
    char buf[1024];
    va_list ap;
    va_start(ap, fmt);
    int n = vsnprintf(buf, sizeof buf, fmt, ap);
    va_end(ap);
    return n >= 0 && (size_t)n < sizeof buf && sb_add(s, buf, (size_t)n);
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
static char *pjoin3(const char *a, const char *b, const char *c) {
    char *ab = pjoin(a, b);
    if (!ab) return NULL;
    char *r = pjoin(ab, c);
    free(ab);
    return r;
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

// posixpath.normpath
static char *normpath(const char *path) {
    size_t n = strlen(path);
    int slashes = path[0] == '/' ? (path[1] == '/' && path[2] != '/' ? 2 : 1) : 0;
    char *copy = malloc(n + 1), *out = malloc(n + 3);
    const char **comps = malloc((n + 1) * sizeof *comps);
    if (!copy || !out || !comps) {
        free(copy);
        free(out);
        free(comps);
        return NULL;
    }
    memcpy(copy, path, n + 1);
    size_t count = 0;
    for (char *tok = copy, *end; tok; tok = end) {
        end = strchr(tok, '/');
        if (end) *end++ = 0;
        if (!*tok || !strcmp(tok, ".")) continue;
        if (strcmp(tok, "..") || (!slashes && !count) || (count && !strcmp(comps[count - 1], ".."))) comps[count++] = tok;
        else if (count)
            count--;
    }
    size_t k = 0;
    for (int i = 0; i < slashes; i++) out[k++] = '/';
    for (size_t i = 0; i < count; i++) {
        size_t l = strlen(comps[i]);
        if (i) out[k++] = '/';
        memcpy(out + k, comps[i], l);
        k += l;
    }
    if (k == 0) out[k++] = '.';
    out[k] = 0;
    free(copy);
    free(comps);
    return out;
}

// Python's strict UTF-8 encoder accepts exactly the well-formed sequences (no surrogates).
static int utf8_valid(const uint8_t *s, size_t n) {
    size_t i = 0;
    while (i < n) {
        uint8_t c = s[i];
        size_t need;
        uint8_t lo = 0x80, hi = 0xBF;
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

// bytes.decode('utf-8', 'replace'): one U+FFFD per maximal invalid subpart, re-encoded as UTF-8.
static int utf8_replace(sb_t *out, const uint8_t *s, size_t n) {
    static const char fffd[] = "\xEF\xBF\xBD";
    size_t i = 0;
    while (i < n) {
        uint8_t c = s[i];
        size_t need;
        uint8_t lo = 0x80, hi = 0xBF;
        if (c < 0x80) {
            if (!sb_add(out, (const char *)s + i, 1)) return 0;
            i++;
            continue;
        } else if (c >= 0xC2 && c <= 0xDF) need = 1;
        else if (c == 0xE0) need = 2, lo = 0xA0;
        else if (c == 0xED) need = 2, hi = 0x9F;
        else if (c >= 0xE1 && c <= 0xEF) need = 2;
        else if (c == 0xF0) need = 3, lo = 0x90;
        else if (c == 0xF4) need = 3, hi = 0x8F;
        else if (c >= 0xF1 && c <= 0xF3) need = 3;
        else {
            if (!sb_add(out, fffd, 3)) return 0;
            i++;
            continue;
        }
        size_t k = 1;
        while (k <= need && i + k < n) {
            uint8_t d = s[i + k];
            if (d < (k == 1 ? lo : 0x80) || d > (k == 1 ? hi : 0xBF)) break;
            k++;
        }
        if (k == need + 1) {
            if (!sb_add(out, (const char *)s + i, k)) return 0;
        } else if (!sb_add(out, fffd, 3))
            return 0;
        i += k;
    }
    return 1;
}

// ---------------- files ----------------
// Reads a whole file of at most `cap` bytes into one exact allocation; the cap is checked from
// the file size before anything is allocated. 0, -1 unreadable / out of memory, -2 too large.
static int read_all(const char *path, size_t cap, uint8_t **data, size_t *len) {
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
    uint8_t *buf = malloc(want + 1);
    if (!buf) {
        fclose(f);
        return -1;
    }
    while (n <= want && (got = fread(buf + n, 1, want + 1 - n, f)) > 0) n += got;
    int bad = ferror(f);
    fclose(f);
    if (bad || n > want) {   // read error, or the file grew while being read
        free(buf);
        return bad ? -1 : -2;
    }
    *data = buf;
    *len = n;
    return 0;
}

static int read_head(const char *path, uint8_t *buf, size_t want, size_t *got) {
    FILE *f = fopen(path, "rb");
    if (!f) return -1;
    *got = fread(buf, 1, want, f);
    int bad = ferror(f);
    fclose(f);
    return bad ? -1 : 0;
}

static int write_all(const char *path, const void *data, size_t n) {
    FILE *f = fopen(path, "wb");
    if (!f) return -1;
    int bad = n && fwrite(data, 1, n, f) != n;
    bad |= fclose(f) != 0;
    return bad ? -1 : 0;
}

// os.makedirs(exist_ok=True). The path itself first, its parent only when it is missing: the
// in-place view of a delta update makes one link per RomFS file (about 205 000 for Mario Kart
// World), and a mkdir for every component from / before each of them (the previous loop, about
// 20 calls per link) made most of the 119 s unpack step seen on the phone (IPA 731).
static int makedirs(const char *path) {
    if (!mkdir(path, 0777)) return 0;
    if (errno == EEXIST) return is_dir(path) ? 0 : -1;
    if (errno != ENOENT) return -1;
    size_t n = strlen(path);
    while (n > 1 && path[n - 1] == '/') n--;   // trailing separators, the last name, then its separators
    while (n > 0 && path[n - 1] != '/') n--;
    while (n > 1 && path[n - 1] == '/') n--;
    if (n == 0 || (n == 1 && path[0] == '/')) return -1;   // nothing above it to create
    char *parent = malloc(n + 1);
    if (!parent) return -1;
    memcpy(parent, path, n);
    parent[n] = 0;
    int r = makedirs(parent);
    free(parent);
    if (r) return -1;
    if (!mkdir(path, 0777)) return 0;
    return errno == EEXIST && is_dir(path) ? 0 : -1;
}

static int make_parent(const char *path) {
    const char *slash = strrchr(path, '/');
    if (!slash || slash == path) return 0;
    size_t n = (size_t)(slash - path);
    char *p = malloc(n + 1);
    if (!p) return -1;
    memcpy(p, path, n);
    p[n] = 0;
    int r = makedirs(p);
    free(p);
    return r;
}

// shutil.copy2 (contents, permission bits, times), after an APFS clone attempt on Apple systems.
static int copy_file(const char *src, const char *dst) {
    if (make_parent(dst)) return -1;
#if defined(__APPLE__)
    if (clonefile(src, dst, 0) == 0) return 0;
#endif
    int in = open(src, O_RDONLY);
    if (in < 0) return -1;
    struct stat st;
    if (fstat(in, &st) || S_ISDIR(st.st_mode)) {
        close(in);
        return -1;
    }
    int out = open(dst, O_WRONLY | O_CREAT | O_TRUNC, 0666);
    if (out < 0) {
        close(in);
        return -1;
    }
    char block[1 << 16];
    int bad = 0;
    for (;;) {
        ssize_t n = read(in, block, sizeof block);
        if (n < 0) {
            if (errno == EINTR) continue;
            bad = 1;
            break;
        }
        if (n == 0) break;
        for (ssize_t done = 0; done < n;) {
            ssize_t w = write(out, block + done, (size_t)(n - done));
            if (w < 0) {
                if (errno == EINTR) continue;
                bad = 1;
                break;
            }
            done += w;
        }
        if (bad) break;
    }
    if (!bad) {
        fchmod(out, st.st_mode & 07777);
#if defined(__APPLE__)
        struct timespec times[2] = {st.st_atimespec, st.st_mtimespec};
#else
        struct timespec times[2] = {st.st_atim, st.st_mtim};
#endif
        futimens(out, times);
    }
    close(in);
    bad |= close(out) != 0;
    if (bad) unlink(dst);
    return bad ? -1 : 0;
}

static int files_equal(const char *a, const char *b, int *equal) {
    FILE *fa = fopen(a, "rb"), *fb = fopen(b, "rb");
    if (!fa || !fb) {
        if (fa) fclose(fa);
        if (fb) fclose(fb);
        return -1;
    }
    static const size_t CHUNK = 1 << 16;
    uint8_t *x = malloc(CHUNK), *y = malloc(CHUNK);
    int r = 0;
    *equal = 0;
    if (!x || !y) r = -1;
    while (!r) {
        size_t na = fread(x, 1, CHUNK, fa), nb = fread(y, 1, CHUNK, fb);
        if (ferror(fa) || ferror(fb)) r = -1;
        else if (na != nb || memcmp(x, y, na)) break;
        else if (!na) {
            *equal = 1;
            break;
        }
    }
    free(x);
    free(y);
    fclose(fa);
    fclose(fb);
    return r;
}

static int rmtree(const char *path, int depth) {   // shutil.rmtree(ignore_errors=True); symlinks removed, not followed
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

// ---------------- directory listings ----------------
typedef struct {
    char **v;
    size_t n, cap;
} list_t;

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
static void list_free(list_t *l) {
    for (size_t i = 0; i < l->n; i++) free(l->v[i]);
    free(l->v);
    l->v = NULL;
    l->n = l->cap = 0;
}
static int cmp_str(const void *a, const void *b) { return strcmp(*(char *const *)a, *(char *const *)b); }

static char *sdup(const char *s) {
    size_t n = strlen(s) + 1;
    char *p = malloc(n);
    if (p) memcpy(p, s, n);
    return p;
}

// os.listdir, sorted; -1 when the directory cannot be listed
static int listdir(const char *path, list_t *out) {
    DIR *d = opendir(path);
    if (!d) return -1;
    struct dirent *e;
    int ok = 1;
    while (ok && (e = readdir(d)))
        if (strcmp(e->d_name, ".") && strcmp(e->d_name, "..")) ok = list_add(out, sdup(e->d_name));
    closedir(d);
    if (!ok) return -2;
    if (out->n) qsort(out->v, out->n, sizeof *out->v, cmp_str);
    return 0;
}

// listdir() with each entry's type from readdir (s2arm_dirent.h) kept in the byte after the name's
// terminating NUL, so that sorting and freeing stay listdir()'s. The walks read it to spare a stat
// on real files and directories.
static unsigned char listed_type(const char *name) { return (unsigned char)name[strlen(name) + 1]; }
static int listdir_typed(const char *path, list_t *out) {
    DIR *d = opendir(path);
    if (!d) return -1;
    struct dirent *e;
    int ok = 1;
    while (ok && (e = readdir(d))) {
        if (!strcmp(e->d_name, ".") || !strcmp(e->d_name, "..")) continue;
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

// What os.walk makes of a listed entry: 1 a directory it enters, 2 a link to a directory (listed,
// not entered), 0 anything else (a file for the walks). Only links and unknown types need a stat.
static int dir_kind(const char *path, const char *listed_name) {
    unsigned char t = listed_type(listed_name);
    if (t == DT_DIR) return 1;
    if (t == DT_LNK) return is_dir(path) ? 2 : 0;
    if (t != DT_UNKNOWN) return 0;
    if (!is_dir(path)) return 0;
    return is_link(path) ? 2 : 1;
}

// walk(): relative path -> absolute path, files only, ".listing" skipped; sorted by relative path.
typedef struct {
    char **rel, **abs;
    size_t n, cap;
} map_t;

static void map_free(map_t *m) {
    for (size_t i = 0; i < m->n; i++) {
        free(m->rel[i]);
        free(m->abs[i]);
    }
    free(m->rel);
    free(m->abs);
    memset(m, 0, sizeof *m);
}
static int map_add(map_t *m, char *rel, char *abs) {
    if (!rel || !abs) {
        free(rel);
        free(abs);
        return 0;
    }
    if (m->n == m->cap) {
        size_t cap = m->cap ? m->cap * 2 : 64;
        char **r = realloc(m->rel, cap * sizeof *r);
        if (!r) goto oom;
        m->rel = r;
        char **a = realloc(m->abs, cap * sizeof *a);
        if (!a) goto oom;
        m->abs = a;
        m->cap = cap;
    }
    m->rel[m->n] = rel;
    m->abs[m->n] = abs;
    m->n++;
    return 1;
oom:
    free(rel);
    free(abs);
    return 0;
}

static int walk_into(map_t *m, const char *dir, const char *rel, int depth) {
    if (depth > MAX_DEPTH) return 0;
    list_t names = {0};
    int r = listdir_typed(dir, &names);
    if (r == -1) return 1;   // os.walk skips what it cannot list
    if (r) return 0;
    int ok = 1;
    for (size_t i = 0; ok && i < names.n; i++) {
        char *abs = pjoin(dir, names.v[i]);
        char *sub = *rel ? pjoin(rel, names.v[i]) : sdup(names.v[i]);
        if (!abs || !sub) {
            free(abs);
            free(sub);
            ok = 0;
            break;
        }
        int kind = dir_kind(abs, names.v[i]);
        if (kind) {
            if (kind == 1) ok = walk_into(m, abs, sub, depth + 1);
            free(abs);
            free(sub);
        } else if (!strcmp(names.v[i], ".listing")) {
            free(abs);
            free(sub);
        } else
            ok = map_add(m, sub, abs);
    }
    list_free(&names);
    return ok;
}

static void map_sort(map_t *m) {   // bottom-up merge sort of the (rel, abs) pairs by rel
    size_t n = m->n;
    if (n < 2) return;
    char **r = malloc(n * sizeof *r), **a = malloc(n * sizeof *a);
    if (!r || !a) {   // fall back to a simple in-place insertion sort
        free(r);
        free(a);
        for (size_t i = 1; i < n; i++)
            for (size_t j = i; j > 0 && strcmp(m->rel[j - 1], m->rel[j]) > 0; j--) {
                char *t = m->rel[j];
                m->rel[j] = m->rel[j - 1];
                m->rel[j - 1] = t;
                t = m->abs[j];
                m->abs[j] = m->abs[j - 1];
                m->abs[j - 1] = t;
            }
        return;
    }
    for (size_t width = 1; width < n; width *= 2) {
        for (size_t lo = 0; lo < n; lo += 2 * width) {
            size_t mid = lo + width < n ? lo + width : n, hi = lo + 2 * width < n ? lo + 2 * width : n, i = lo, j = mid, k = lo;
            while (i < mid && j < hi) {
                if (strcmp(m->rel[i], m->rel[j]) <= 0) r[k] = m->rel[i], a[k++] = m->abs[i++];
                else r[k] = m->rel[j], a[k++] = m->abs[j++];
            }
            while (i < mid) r[k] = m->rel[i], a[k++] = m->abs[i++];
            while (j < hi) r[k] = m->rel[j], a[k++] = m->abs[j++];
        }
        memcpy(m->rel, r, n * sizeof *r);
        memcpy(m->abs, a, n * sizeof *a);
    }
    free(r);
    free(a);
}

static int walk(const char *root, map_t *m) {
    memset(m, 0, sizeof *m);
    if (!walk_into(m, root, "", 0)) {
        map_free(m);
        return -1;
    }
    map_sort(m);
    return 0;
}

static long map_find(const map_t *m, const char *rel) {
    size_t lo = 0, hi = m->n;
    while (lo < hi) {
        size_t mid = (lo + hi) / 2;
        int c = strcmp(m->rel[mid], rel);
        if (!c) return (long)mid;
        if (c < 0) lo = mid + 1;
        else hi = mid;
    }
    return -1;
}

static int file_size(const char *path, uint64_t *size) {
    struct stat st;
    if (stat(path, &st)) return -1;
    *size = (uint64_t)st.st_size;
    return 0;
}

// numdirs(): subfolders whose name is decimal digits, by numeric value (ties by name).
static int numcmp(const void *pa, const void *pb) {
    const char *a = *(char *const *)pa, *b = *(char *const *)pb;
    const char *x = a, *y = b;
    while (*x == '0' && x[1]) x++;
    while (*y == '0' && y[1]) y++;
    size_t lx = strlen(x), ly = strlen(y);
    if (lx != ly) return lx < ly ? -1 : 1;
    int c = strcmp(x, y);
    return c ? c : strcmp(a, b);
}
static int numdirs(const char *dir, list_t *out) {
    memset(out, 0, sizeof *out);
    if (!is_dir(dir)) return 0;
    list_t names = {0};
    int r = listdir(dir, &names);
    if (r == -2) return -1;
    for (size_t i = 0; i < names.n; i++) {
        const char *n = names.v[i];
        int digits = *n != 0;
        for (const char *c = n; *c; c++)
            if (*c < '0' || *c > '9') digits = 0;
        if (!digits) continue;
        char *p = pjoin(dir, n);
        int d = p && is_dir(p);
        free(p);
        if (d && !list_add(out, sdup(n))) {
            list_free(&names);
            list_free(out);
            return -1;
        }
    }
    list_free(&names);
    if (out->n) qsort(out->v, out->n, sizeof *out->v, numcmp);
    return 0;
}

// ---------------- NPDM ----------------
static int read_tid(ctx_t *x, const char *npdm, uint64_t *tid) {
    uint8_t *b = NULL;
    size_t n = 0;
    int r = read_all(npdm, 1u << 26, &b, &n);
    if (r == -1) return fail(x, RB_S2ARM_NS2_INVALID, "cannot read %s", npdm);
    if (r) return fail(x, RB_S2ARM_NS2_INVALID, "%s is too large for an NPDM", npdm);
    int code = RB_S2ARM_NS2_OK;
    if (n < 0x80 || memcmp(b, "META", 4)) code = fail(x, RB_S2ARM_NS2_INVALID, "%s has no META header", npdm);
    else {
        uint64_t aci = le32(b + 0x70);
        if (aci + 4 > n || memcmp(b + aci, "ACI0", 4)) code = fail(x, RB_S2ARM_NS2_INVALID, "%s: ACI0 is not at 0x%llx", npdm, (unsigned long long)aci);
        else if (aci + 0x18 > n) code = fail(x, RB_S2ARM_NS2_INVALID, "%s: ACI0 truncated", npdm);
        else *tid = le64(b + aci + 0x10);
    }
    free(b);
    return code;
}

static char *find_dump(const char *root) {
    char *probe = pjoin3(root, "base", "exefs/main.npdm");
    if (probe && is_file(probe)) {
        free(probe);
        return sdup(root);
    }
    free(probe);
    list_t names = {0};
    if (listdir(root, &names)) return NULL;
    char *found = NULL;
    for (size_t i = 0; !found && i < names.n; i++) {
        char *d = pjoin(root, names.v[i]);
        if (!d) break;
        char *p = is_dir(d) ? pjoin3(d, "base", "exefs/main.npdm") : NULL;
        if (p && is_file(p)) found = d;
        else free(d);
        free(p);
    }
    list_free(&names);
    return found;
}

int rb_s2arm_ns2_detect(const char *root, char *dump, size_t dump_size, uint64_t *program_id, char *error, size_t error_size) {
    ctx_t x = {error, error_size, NULL};
    if (!root || !is_dir(root)) return fail(&x, RB_S2ARM_NS2_INVALID, "not a folder");
    char *d = find_dump(root);
    if (!d) return fail(&x, RB_S2ARM_NS2_INVALID, "%s is not a Switch 2 export folder (needs base/exefs/main.npdm)", root);
    char *npdm = pjoin3(d, "base", "exefs/main.npdm");
    uint64_t tid = 0;
    int r = npdm ? read_tid(&x, npdm, &tid) : fail(&x, RB_S2ARM_NS2_IO, "out of memory");
    free(npdm);
    if (!r) {
        if (dump && dump_size) snprintf(dump, dump_size, "%s", d);
        if (program_id) *program_id = tid;
    }
    free(d);
    return r;
}

// ---------------- save_kinds (synthesised control.nacp) ----------------
static const struct {
    const char *symbol;
    int count;
    struct {
        size_t offset;
        uint64_t value;
    } fields[3];
    const char *note;
} SAVE_KINDS[3] = {
    {"_ZN2nn2fs21MountTemporaryStorageE", 1, {{0x3168, 0x08000000}}, "temporary storage 128 MB"},
    {"_ZN2nn2fs19MountDeviceSaveDataE", 2, {{0x3090, 0x08000000}, {0x3098, 0x04000000}}, "device save data 128 / 64 MB"},
    {"_ZN2nn2fs17MountCacheStorageE", 3, {{0x3170, 0x08000000}, {0x3178, 0x04000000}, {0x3180, 0x0C000000}}, "cache storage 128 / 64 MB"},
};

static int contains(const uint8_t *hay, size_t n, const char *needle) {
    size_t k = strlen(needle);
    if (k > n) return 0;
    for (size_t i = 0; i + k <= n; i++)
        if (hay[i] == (uint8_t)needle[0] && !memcmp(hay + i, needle, k)) return 1;
    return 0;
}

// nso_image(): the three segments decoded and joined (not laid out by address), or the whole file when it is not an NSO.
// Memory: the joined image is bounded (sum of the declared LZ4 sizes and of the stored lengths) and
// checked against the module cap before anything is decoded; segments are decoded into one buffer.
static int nso_image(ctx_t *x, const char *path, uint8_t **image, size_t *image_len) {
    uint8_t *d = NULL;
    size_t n = 0, cap = module_cap(x);
    int r = read_all(path, cap, &d, &n);
    if (r == -1) return fail(x, RB_S2ARM_NS2_IO, "cannot read %s", path);
    if (r) return fail(x, RB_S2ARM_NS2_INVALID, "%s is larger than the module limit 0x%zx", path, cap);
    if (n < 0x100 || memcmp(d, "NSO0", 4)) {
        *image = d;
        *image_len = n;
        return 0;
    }
    uint32_t fl = le32(d + 0x0C);
    size_t start[3], rawlen[3];
    uint64_t bound = 0;
    for (int i = 0; i < 3; i++) {
        uint32_t fo = le32(d + 0x10 + 0x10 * i), size = le32(d + 0x18 + 0x10 * i), csz = le32(d + 0x60 + 4 * i);
        uint64_t want = (fl & (1u << i)) ? csz : size;
        size_t end = (uint64_t)fo + want < n ? (size_t)(fo + want) : n;   // Python slice clamps
        start[i] = fo < n ? fo : n;
        rawlen[i] = end > start[i] ? end - start[i] : 0;
        if ((fl & (1u << i)) && rawlen[i]) {
            if (size > 0x7FFFFFFFu) {   // python-lz4 refuses an uncompressed size above INT_MAX
                free(d);
                return fail(x, RB_S2ARM_NS2_INVALID, "%s: LZ4 segment %d size invalid", path, i);
            }
            bound += size;
        } else
            bound += rawlen[i];
    }
    if (bound > cap) {
        free(d);
        return fail(x, RB_S2ARM_NS2_INVALID, "%s: decoded module would be up to 0x%llx bytes, above the module limit 0x%zx", path,
                    (unsigned long long)bound, cap);
    }
    uint8_t *out = malloc(bound ? (size_t)bound : 1);
    if (!out) {
        free(d);
        return fail(x, RB_S2ARM_NS2_IO, "out of memory");
    }
    size_t at = 0;
    int code = 0;
    for (int i = 0; i < 3 && !code; i++) {
        const uint8_t *raw = d + start[i];
        if ((fl & (1u << i)) && rawlen[i]) {
            uint32_t size = le32(d + 0x18 + 0x10 * i);
            if (rawlen[i] > 0x7FFFFFFFu) {
                code = fail(x, RB_S2ARM_NS2_INVALID, "%s: LZ4 segment %d too large", path, i);
                break;
            }
            int got = LZ4_decompress_safe((const char *)raw, (char *)out + at, (int)rawlen[i], (int)size);
            if (got < 0) code = fail(x, RB_S2ARM_NS2_INVALID, "%s: LZ4 segment %d does not decompress", path, i);
            else at += (size_t)got;
        } else {
            memcpy(out + at, raw, rawlen[i]);
            at += rawlen[i];
        }
    }
    free(d);
    if (code) {
        free(out);
        return code;
    }
    *image = out;
    *image_len = at;
    return 0;
}

static int save_kinds(ctx_t *x, const char *exefs, int found[3]) {
    found[0] = found[1] = found[2] = 0;
    list_t names = {0};
    if (listdir(exefs, &names)) return fail(x, RB_S2ARM_NS2_IO, "cannot list %s", exefs);
    int code = 0;
    for (size_t i = 0; i < names.n && !code; i++) {
        if (strcmp(names.v[i], "main") && strncmp(names.v[i], "subsdk", 6)) continue;
        if (cancelled(x)) {
            code = fail(x, RB_S2ARM_NS2_CANCELLED, "cancelled");
            break;
        }
        char *p = pjoin(exefs, names.v[i]);
        uint8_t *img = NULL;
        size_t len = 0;
        code = p ? nso_image(x, p, &img, &len) : fail(x, RB_S2ARM_NS2_IO, "out of memory");
        free(p);
        if (code) break;
        for (int k = 0; k < 3; k++)
            if (contains(img, len, SAVE_KINDS[k].symbol)) found[k] = 1;
        free(img);
    }
    list_free(&names);
    return code;
}

static void synth_nacp(uint8_t *n, uint64_t tid, const char *name, const int saves[3]) {
    memset(n, 0, NACP_SIZE);
    size_t t = strlen(name);
    if (t > 0x1ff) t = 0x1ff;
    for (int i = 0; i < 16; i++) memcpy(n + i * 0x300, name, t);   // ApplicationTitle[16]: name 0x200 + publisher 0x100
    n[0x3025] = 1;                                                  // StartupUserAccount = Required
    put32(n + 0x302C, 1);                                           // SupportedLanguageFlag: American English only
    n[0x3060] = '?';                                                // DisplayVersion unknown
    put64(n + 0x3078, tid);                                         // SaveDataOwnerId = program id
    put64(n + 0x3080, 0x08000000);                                  // UserAccountSaveDataSize 128 MB
    put64(n + 0x3088, 0x04000000);                                  // UserAccountSaveDataJournalSize 64 MB
    for (int k = 0; k < 3; k++)
        if (saves[k])
            for (int j = 0; j < SAVE_KINDS[k].count; j++) put64(n + SAVE_KINDS[k].fields[j].offset, SAVE_KINDS[k].fields[j].value);
}

// ---------------- control partition ----------------
// find_control(): control.nacp (0x4000 bytes) in a version folder or one level below (not in romfs/exefs).
static int find_control(const char *const *dirs, int ndirs, uint8_t *nacp, char **icon, int *found) {
    *found = 0;
    *icon = NULL;
    for (int i = 0; i < ndirs && !*found; i++) {
        list_t places = {0}, names = {0};
        if (!list_add(&places, sdup(dirs[i]))) return -1;
        if (listdir(dirs[i], &names) == -2) {
            list_free(&places);
            return -1;
        }
        for (size_t k = 0; k < names.n; k++) {
            if (!strcmp(names.v[k], "romfs") || !strcmp(names.v[k], "exefs")) continue;
            char *p = pjoin(dirs[i], names.v[k]);
            if (p && is_dir(p)) {
                if (!list_add(&places, p)) {
                    list_free(&names);
                    list_free(&places);
                    return -1;
                }
            } else
                free(p);
        }
        list_free(&names);
        for (size_t k = 0; k < places.n && !*found; k++) {
            char *c = pjoin(places.v[k], "control.nacp");
            uint64_t size = 0;
            if (c && is_file(c) && !file_size(c, &size) && size == NACP_SIZE) {
                size_t got = 0;
                if (read_head(c, nacp, NACP_SIZE, &got) || got != NACP_SIZE) {
                    free(c);
                    list_free(&places);
                    return -1;
                }
                *found = 1;
                list_t files = {0};
                if (listdir(places.v[k], &files) == 0)
                    for (size_t f = 0; f < files.n && !*icon; f++) {
                        size_t l = strlen(files.v[f]);
                        if (l >= 5 && !strncmp(files.v[f], "icon_", 5) && l >= 4 && !strcmp(files.v[f] + l - 4, ".dat"))
                            *icon = pjoin(places.v[k], files.v[f]);
                    }
                list_free(&files);
            }
            free(c);
        }
        list_free(&places);
    }
    return 0;
}

static int nacp_title(sb_t *out, const uint8_t *n, int lang) {   // ApplicationTitle[lang] name, decoded with replacement
    const uint8_t *t = n + lang * 0x300;
    size_t l = 0;
    while (l < 0x200 && t[l]) l++;
    return utf8_replace(out, t, l);
}

// ---------------- Python int(text, 16) ----------------
// Returns 1 with the value when it parses and fits in 128 bits, 2 when it parses but is
// larger (such a title id never matches the program), 0 when Python raises ValueError.
static int parse_hex(const char *s, unsigned __int128 *value, int *negative) {
    const char *p = s, *end = s + strlen(s);
    while (p < end && (*p == ' ' || (*p >= '\t' && *p <= '\r'))) p++;
    while (end > p && (end[-1] == ' ' || (end[-1] >= '\t' && end[-1] <= '\r'))) end--;
    *negative = 0;
    if (p < end && (*p == '+' || *p == '-')) *negative = *p++ == '-';
    int prefix = 0;
    if (end - p >= 2 && p[0] == '0' && (p[1] == 'x' || p[1] == 'X')) {
        p += 2;
        prefix = 1;
    }
    unsigned __int128 v = 0;
    int digits = 0, big = 0, under = prefix;   // an underscore may follow the prefix
    if (p == end) return 0;
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
        if (v >> 124) big = 1;
        v = v << 4 | (unsigned)d;
        digits++;
        under = 1;
    }
    if (!digits || p[-1] == '_') return 0;
    *value = v;
    return big ? 2 : 1;
}

static void hex128(char *out, unsigned __int128 v) {   // format(v, '016x')
    char tmp[40];
    int k = 0;
    do {
        tmp[k++] = "0123456789abcdef"[(int)(v & 15)];
        v >>= 4;
    } while (v);
    while (k < 16) tmp[k++] = '0';
    for (int i = 0; i < k; i++) out[i] = tmp[k - 1 - i];
    out[k] = 0;
}

// ---------------- source key ----------------
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
    for (int i = 16; i < 64; i++)
        w[i] = w[i - 16] + (ror32(w[i - 15], 7) ^ ror32(w[i - 15], 18) ^ (w[i - 15] >> 3)) + w[i - 7] +
               (ror32(w[i - 2], 17) ^ ror32(w[i - 2], 19) ^ (w[i - 2] >> 10));
    uint32_t a = s->h[0], b = s->h[1], c = s->h[2], d = s->h[3], e = s->h[4], f = s->h[5], g = s->h[6], h = s->h[7];
    for (int i = 0; i < 64; i++) {
        uint32_t t1 = h + (ror32(e, 6) ^ ror32(e, 11) ^ ror32(e, 25)) + ((e & f) ^ (~e & g)) + K256[i] + w[i];
        uint32_t t2 = (ror32(a, 2) ^ ror32(a, 13) ^ ror32(a, 22)) + ((a & b) ^ (a & c) ^ (b & c));
        h = g, g = f, f = e, e = d + t1, d = c, c = b, b = a, a = t1 + t2;
    }
    s->h[0] += a, s->h[1] += b, s->h[2] += c, s->h[3] += d, s->h[4] += e, s->h[5] += f, s->h[6] += g, s->h[7] += h;
}
static void sha_init(sha_t *s) {
    static const uint32_t iv[8] = {0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};
    memcpy(s->h, iv, sizeof iv);
    s->total = 0;
    s->fill = 0;
}
static void sha_update(sha_t *s, const void *data, size_t n) {
    const uint8_t *p = data;
    s->total += n;
    while (n) {
        size_t take = 64 - s->fill < n ? 64 - s->fill : n;
        memcpy(s->buf + s->fill, p, take);
        s->fill += take, p += take, n -= take;
        if (s->fill == 64) sha_block(s, s->buf), s->fill = 0;
    }
}
static void sha_final(sha_t *s, uint8_t out[32]) {
    uint64_t bits = s->total * 8;
    uint8_t pad = 0x80, len[8];
    sha_update(s, &pad, 1);
    pad = 0;
    while (s->fill != 56) sha_update(s, &pad, 1);
    for (int i = 0; i < 8; i++) len[i] = (uint8_t)(bits >> (56 - 8 * i));
    sha_update(s, len, 8);
    for (int i = 0; i < 8; i++)
        for (int k = 0; k < 4; k++) out[4 * i + k] = (uint8_t)(s->h[i] >> (24 - 8 * k));
}

// src_key(): listing (path, size, mtime in ns) of the whole export + this implementation's tag.
static int src_key(ctx_t *x, const char *dump, int reference, char key[17]) {
    map_t all;
    if (walk(dump, &all)) return fail(x, RB_S2ARM_NS2_IO, "out of memory");
    sha_t s;
    sha_init(&s);
    int code = 0;
    for (size_t i = 0; i < all.n; i++) {
        struct stat st;
        if (stat(all.abs[i], &st)) {
            code = fail(x, RB_S2ARM_NS2_IO, "cannot stat %s", all.abs[i]);
            break;
        }
#if defined(__APPLE__)
        long long ns = (long long)st.st_mtimespec.tv_sec * 1000000000LL + st.st_mtimespec.tv_nsec;
#else
        long long ns = (long long)st.st_mtim.tv_sec * 1000000000LL + st.st_mtim.tv_nsec;
#endif
        char line[64];
        sha_update(&s, all.rel[i], strlen(all.rel[i]));
        int n = snprintf(line, sizeof line, "\t%lld\t%lld\n", (long long)st.st_size, ns);
        sha_update(&s, line, (size_t)n);
    }
    map_free(&all);
    if (code) return code;
    sha_update(&s, KEY_TAG, strlen(KEY_TAG));
    sha_update(&s, reference ? "\treference" : "\tcopy", reference ? 10 : 5);
    uint8_t digest[32];
    sha_final(&s, digest);
    for (int i = 0; i < 8; i++) snprintf(key + 2 * i, 3, "%02x", digest[i]);
    return 0;
}

// ---------------- in-place views (reference mode) ----------------
// Relative path from directory `from` to `to` (both absolute and resolved), as os.path.relpath.
static char *relpath(const char *to, const char *from) {
    size_t i = 0, common = 0;
    while (to[i] && from[i] && to[i] == from[i]) {
        if (to[i] == '/') common = i;
        i++;
    }
    if ((!to[i] || to[i] == '/') && (!from[i] || from[i] == '/')) common = i;
    sb_t b = {0};
    const char *rest = from + common;
    while (*rest == '/') rest++;
    int ok = 1;
    while (*rest && ok) {
        ok = sb_str(&b, b.n ? "/.." : "..");
        const char *slash = strchr(rest, '/');
        rest = slash ? slash + 1 : rest + strlen(rest);
        while (*rest == '/') rest++;
    }
    const char *tail = to + common;
    while (*tail == '/') tail++;
    if (ok && *tail) ok = (!b.n || sb_str(&b, "/")) && sb_str(&b, tail);
    if (ok && !b.n) ok = sb_str(&b, ".");
    if (!ok) {
        free(b.p);
        return NULL;
    }
    return b.p;
}

// 1 when a directory holds only real directories (none empty) and regular files other than
// ".listing": the walk then sees exactly its content, and a directory symlink can stand for the copy.
static int tree_clean(const char *dir, int depth) {
    if (depth > MAX_DEPTH) return 0;
    list_t names = {0};
    if (listdir_typed(dir, &names) || !names.n) {
        list_free(&names);
        return 0;
    }
    int ok = 1;
    for (size_t i = 0; i < names.n && ok; i++) {
        char *p = pjoin(dir, names.v[i]);
        unsigned char t = listed_type(names.v[i]);   // lstat's file type, from the listing when it gives one
        mode_t mode = t == DT_DIR ? S_IFDIR : t == DT_REG ? S_IFREG : t == DT_LNK ? S_IFLNK : t == DT_UNKNOWN ? 0 : S_IFIFO;
        struct stat st;
        if (p && !mode && !lstat(p, &st)) mode = st.st_mode & S_IFMT;
        if (!p || !mode) ok = 0;
        else if (S_ISDIR(mode)) ok = tree_clean(p, depth + 1);
        else ok = S_ISREG(mode) && strcmp(names.v[i], ".listing");
        free(p);
    }
    list_free(&names);
    return ok;
}

typedef struct {
    char *final_out;   // the resolved path the output will have once renamed into place
    char *real_dump;   // the resolved export folder
    const char *dump;  // the export folder as given: every source path starts with it
    size_t dump_len;
    char *made_dir;    // the directory the previous link went into, known to exist (links come in path order)
} out_t;

// A relative symlink at <tmp>/<area>/<rel> (rel may be empty: the area itself) to a path under the export folder.
static int link_view(ctx_t *x, out_t *o, const char *src, const char *tmp, const char *area, const char *rel) {
    char *at = *rel ? pjoin3(tmp, area, rel) : pjoin(tmp, area);
    const char *tail = !strncmp(src, o->dump, o->dump_len) ? src + o->dump_len : NULL;
    while (tail && *tail == '/') tail++;
    char *real = tail ? (*tail ? pjoin(o->real_dump, tail) : sdup(o->real_dump)) : NULL;
    char *where = *rel ? pjoin3(o->final_out, area, rel) : pjoin(o->final_out, area);
    char *slash = where ? strrchr(where, '/') : NULL;
    if (slash) *slash = 0;   // the directory the link lives in
    char *target = real && where ? relpath(real, where) : NULL;
    int r = -1;
    if (at && target) {
        const char *cut = strrchr(at, '/');
        size_t dn = cut ? (size_t)(cut - at) : 0;
        int known = o->made_dir && strlen(o->made_dir) == dn && !memcmp(o->made_dir, at, dn);
        if (known || !make_parent(at)) {
            if (!known && cut) {
                free(o->made_dir);
                o->made_dir = malloc(dn + 1);
                if (o->made_dir) memcpy(o->made_dir, at, dn), o->made_dir[dn] = 0;
            }
            r = symlink(target, at);
            if (r && errno == EEXIST) {   // replaced, as before (unlink, then link)
                unlink(at);
                r = symlink(target, at);
            }
        }
    }
    free(at);
    free(real);
    free(where);
    free(target);
    return r ? fail(x, RB_S2ARM_NS2_IO, "cannot link %s", src) : 0;
}

static int place(ctx_t *x, out_t *o, const char *src, const char *tmp, const char *area, const char *rel) {
    if (cancelled(x)) return fail(x, RB_S2ARM_NS2_CANCELLED, "cancelled");
    if (x->request->reference_data) return link_view(x, o, src, tmp, area, rel);
    char *dst = pjoin3(tmp, area, rel);
    int r = dst ? copy_file(src, dst) : -1;
    free(dst);
    return r ? fail(x, RB_S2ARM_NS2_IO, "cannot copy %s", src) : 0;
}

static int ascii_lower_cmp(const void *a, const void *b) {
    const unsigned char *p = *(const unsigned char *const *)a, *q = *(const unsigned char *const *)b;
    for (;; p++, q++) {
        int c = *p >= 'A' && *p <= 'Z' ? *p + 32 : *p, d = *q >= 'A' && *q <= 'Z' ? *q + 32 : *q;
        if (c != d || !c) return c - d;
    }
}

static int convert(ctx_t *x, const char *dump, const char *out, const char *name) {
    const rb_s2arm_ns2_dump_request *rq = x->request;
    int code = 0;
    char *base = pjoin(dump, "base"), *npdm0 = base ? pjoin3(base, "exefs", "main.npdm") : NULL;
    char *updates = pjoin(dump, "updates"), *upd = NULL, *tmp = NULL, *exsrc = NULL, *tmp_exefs = NULL, *keyfile = NULL;
    char *icon = NULL, *dumpname = NULL;
    list_t ups = {0}, dlcs = {0};
    map_t ex = {0}, rb = {0}, ru = {0};
    out_t o = {NULL, NULL, NULL, 0, NULL};
    sb_t builds = {0}, aoc_rows = {0}, aoc_idx = {0}, text = {0}, nm = {0}, nzh = {0}, dver = {0};
    uint8_t *nacp = malloc(NACP_SIZE);
    uint64_t tid = 0, tid2 = 0;
    int made_tmp = 0;
    if (!base || !npdm0 || !updates || !nacp) {
        code = fail(x, RB_S2ARM_NS2_IO, "out of memory");
        goto done;
    }
    if ((code = read_tid(x, npdm0, &tid))) {
        char why[512];
        snprintf(why, sizeof why, "%s", x->error ? x->error : "");
        code = fail(x, RB_S2ARM_NS2_INVALID, "cannot read the program id: %s", why);
        goto done;
    }
    if (numdirs(updates, &ups)) {
        code = fail(x, RB_S2ARM_NS2_IO, "out of memory");
        goto done;
    }
    if (ups.n) {
        upd = pjoin(updates, ups.v[ups.n - 1]);
        if (!upd) {
            code = fail(x, RB_S2ARM_NS2_IO, "out of memory");
            goto done;
        }
    }
    if (ups.n > 1) note(x, "%zu updates, using the newest, %s", ups.n, ups.v[ups.n - 1]);
    char key[17];
    if ((code = src_key(x, dump, rq->reference_data, key))) goto done;
    keyfile = pjoin(out, ".ns2_dump_key");
    tmp = malloc(strlen(out) + 5);
    if (!keyfile || !tmp) {
        code = fail(x, RB_S2ARM_NS2_IO, "out of memory");
        goto done;
    }
    sprintf(tmp, "%s.tmp", out);
    if (rq->reference_data) {   // views are relative to where the output will be, and point into the resolved export
        char *parent = sdup(out), *slash = parent ? strrchr(parent, '/') : NULL;
        const char *base_name = strrchr(out, '/') ? strrchr(out, '/') + 1 : out;
        if (slash == parent && parent) parent[1] = 0;
        else if (slash) *slash = 0;
        char *rp = parent ? realpath(slash ? parent : ".", NULL) : NULL;
        o.final_out = rp ? pjoin(rp, base_name) : NULL;
        o.real_dump = realpath(dump, NULL);
        o.dump = dump;
        o.dump_len = strlen(dump);
        free(rp);
        free(parent);
        if (!o.final_out || !o.real_dump) {
            code = fail(x, RB_S2ARM_NS2_IO, "cannot resolve the output or export folder");
            goto done;
        }
    }
    {
        uint8_t head[64];
        size_t got = 0;
        if (is_file(keyfile) && !read_head(keyfile, head, sizeof head - 1, &got)) {
            head[got] = 0;
            char *s = (char *)head, *e = s + got;   // .strip()
            while (*s == ' ' || (*s >= '\t' && *s <= '\r')) s++;
            while (e > s && (e[-1] == ' ' || (e[-1] >= '\t' && e[-1] <= '\r'))) e--;
            if ((size_t)(e - s) == 16 && !memcmp(s, key, 16)) {
                note(x, "export unchanged (key %s), reusing %s", key, out);
                goto done;
            }
        }
    }
    rmtree(tmp, 0);
    if (makedirs(tmp)) {
        code = fail(x, RB_S2ARM_NS2_IO, "cannot create %s", tmp);
        goto done;
    }
    made_tmp = 1;

    // exefs: the newest update when it has a main, else the base
    {
        char *upd_main = upd ? pjoin3(upd, "exefs", "main") : NULL;
        exsrc = upd_main && is_file(upd_main) ? pjoin(upd, "exefs") : pjoin(base, "exefs");
        free(upd_main);
    }
    tmp_exefs = pjoin(tmp, "exefs");
    if (!exsrc || !tmp_exefs || walk(exsrc, &ex)) {
        code = fail(x, RB_S2ARM_NS2_IO, "out of memory");
        goto done;
    }
    for (size_t i = 0; i < ex.n; i++) {
        if (strchr(ex.rel[i], '/')) continue;
        if (cancelled(x)) {
            code = fail(x, RB_S2ARM_NS2_CANCELLED, "cancelled");
            goto done;
        }
        uint8_t hdr[0x50];
        size_t got = 0;
        if (read_head(ex.abs[i], hdr, sizeof hdr, &got)) {
            code = fail(x, RB_S2ARM_NS2_IO, "cannot read %s", ex.abs[i]);
            goto done;
        }
        char *dst = pjoin(tmp_exefs, ex.rel[i]);
        if (!dst) {
            code = fail(x, RB_S2ARM_NS2_IO, "out of memory");
            goto done;
        }
        if (got >= 4 && !memcmp(hdr, "NSO0", 4)) {
            if (got < 0x10) {
                free(dst);
                code = fail(x, RB_S2ARM_NS2_INVALID, "%s: NSO header truncated", ex.abs[i]);
                goto done;
            }
            uint32_t fl = le32(hdr + 0x0C);
            if (fl & ~0xFFu) {
                free(dst);
                code = fail(x, RB_S2ARM_NS2_INVALID, "%s: NSO flags 0x%x have unknown bits 0x%x, compression unknown", ex.abs[i], fl, fl & ~0xFFu);
                goto done;
            }
            int ok = (builds.n == 0 || sb_str(&builds, " ")) && sb_str(&builds, ex.rel[i]) && sb_str(&builds, ":");
            for (size_t k = 0x40; ok && k < 0x50 && k < got; k++) ok = sb_fmt(&builds, "%02x", hdr[k]);
            if (!ok) {
                free(dst);
                code = fail(x, RB_S2ARM_NS2_IO, "out of memory");
                goto done;
            }
            if (fl & 0x80) {   // ZBIC: normalised to uncompressed segments (SHA-256 checked per segment)
                char why[512] = "";
                if (makedirs(tmp_exefs)) {
                    free(dst);
                    code = fail(x, RB_S2ARM_NS2_IO, "cannot create %s", tmp_exefs);
                    goto done;
                }
                rb_s2arm_zbic_options zopt = {module_cap(x), rq->cancelled, rq->context};
                int r = rb_s2arm_nso_normalize_file_ex(ex.abs[i], dst, &zopt, why, sizeof why);
                free(dst);
                if (r == RB_S2ARM_ZBIC_CANCELLED) {
                    code = fail(x, RB_S2ARM_NS2_CANCELLED, "cancelled");
                    goto done;
                }
                if (r) {
                    code = fail(x, r == RB_S2ARM_ZBIC_IO ? RB_S2ARM_NS2_IO : RB_S2ARM_NS2_INVALID, "%s: ZBIC does not decode: %s", ex.abs[i], why);
                    goto done;
                }
                note(x, "   %s: ZBIC-compressed, normalised to uncompressed segments", ex.rel[i]);
                continue;
            }
        }
        int r = copy_file(ex.abs[i], dst);
        free(dst);
        if (r) {
            code = fail(x, RB_S2ARM_NS2_IO, "cannot copy %s", ex.abs[i]);
            goto done;
        }
    }
    {
        char *m = pjoin(tmp_exefs, "main"), *n2 = pjoin(tmp_exefs, "main.npdm");
        int has_main = m && is_file(m);
        free(m);
        if (!has_main) {
            free(n2);
            code = fail(x, RB_S2ARM_NS2_INVALID, "%s has no main", exsrc);
            goto done;
        }
        code = n2 ? read_tid(x, n2, &tid2) : fail(x, RB_S2ARM_NS2_IO, "out of memory");
        free(n2);
        if (code) goto done;
        if (tid2 != tid) {
            code = fail(x, RB_S2ARM_NS2_INVALID, "the update's main.npdm program id differs from the base");
            goto done;
        }
    }

    // romfs
    {
        char *rbd = pjoin(base, "romfs"), *rud = upd ? pjoin(upd, "romfs") : NULL;
        int bad = !rbd || walk(rbd, &rb) || (upd && (!rud || walk(rud, &ru)));
        free(rbd);
        free(rud);
        if (bad) {
            code = fail(x, RB_S2ARM_NS2_IO, "out of memory");
            goto done;
        }
    }
    const char *same = NULL;
    {   // same_file(): a same-path same-size file of the update identical to the base (first 64 candidates)
        int n = 0;
        for (size_t i = 0, j = 0; i < rb.n && j < ru.n && !same;) {
            int c = strcmp(rb.rel[i], ru.rel[j]);
            if (c < 0) {
                i++;
                continue;
            }
            if (c > 0) {
                j++;
                continue;
            }
            uint64_t sa = 0, sbz = 0;
            if (file_size(rb.abs[i], &sa) || file_size(ru.abs[j], &sbz)) {
                code = fail(x, RB_S2ARM_NS2_IO, "cannot stat %s", rb.rel[i]);
                goto done;
            }
            if (sa == sbz) {
                int eq = 0;
                if (files_equal(rb.abs[i], ru.abs[j], &eq)) {
                    code = fail(x, RB_S2ARM_NS2_IO, "cannot read %s", rb.rel[i]);
                    goto done;
                }
                if (eq) {
                    same = rb.rel[i];
                    break;
                }
                if (++n >= 64) break;
            }
            i++;
            j++;
        }
    }
    // rom = the update alone (no base romfs / full image), base overlaid by the update (delta), or the base
    int use_update_only = ru.n && (!rb.n || same), overlay = ru.n && !use_update_only;
    size_t rom_n = 0;
    {
        const map_t *parts[2] = {use_update_only ? &ru : &rb, overlay ? &ru : NULL};
        list_t all = {0};
        for (int k = 0; k < 2; k++)
            if (parts[k])
                for (size_t i = 0; i < parts[k]->n; i++)
                    if (!list_add(&all, sdup(parts[k]->rel[i]))) {
                        list_free(&all);
                        code = fail(x, RB_S2ARM_NS2_IO, "out of memory");
                        goto done;
                    }
        // unique relative paths, then the case check
        if (all.n) qsort(all.v, all.n, sizeof *all.v, cmp_str);
        size_t u = 0;
        for (size_t i = 0; i < all.n; i++) {
            if (u && !strcmp(all.v[u - 1], all.v[i])) {
                free(all.v[i]);
                continue;
            }
            all.v[u++] = all.v[i];
        }
        all.n = u;
        rom_n = u;
        if (!rom_n) {
            list_free(&all);
            code = fail(x, RB_S2ARM_NS2_INVALID, "%s has no romfs files", dump);
            goto done;
        }
        if (overlay) note(x, "romfs: base %zu + update %zu overlaid (no file of the update is identical to the base: delta update)", rb.n, ru.n);
        qsort(all.v, all.n, sizeof *all.v, ascii_lower_cmp);
        for (size_t i = 1; i < all.n; i++)
            if (!ascii_lower_cmp(&all.v[i - 1], &all.v[i])) {
                code = fail(x, RB_S2ARM_NS2_INVALID, "romfs paths differ only by case: %s / %s (case-insensitive file system)", all.v[i - 1], all.v[i]);
                list_free(&all);
                goto done;
            }
        list_free(&all);
    }
    if (rq->reference_data && !overlay) {   // one export folder holds the whole RomFS: a directory symlink when nothing is left out
        char *dir = pjoin(use_update_only ? upd : base, "romfs");
        int whole = dir && tree_clean(dir, 0);
        if (whole && (code = link_view(x, &o, dir, tmp, "romfs", ""))) {
            free(dir);
            goto done;
        }
        free(dir);
        if (whole) goto romfs_done;
    }
    {
        const map_t *first = use_update_only ? &ru : &rb;
        for (size_t i = 0; i < first->n; i++) {
            if (overlay && map_find(&ru, first->rel[i]) >= 0) continue;   // the update's copy wins
            if ((code = place(x, &o, first->abs[i], tmp, "romfs", first->rel[i]))) goto done;
        }
        if (overlay)
            for (size_t i = 0; i < ru.n; i++)
                if ((code = place(x, &o, ru.abs[i], tmp, "romfs", ru.rel[i]))) goto done;
    }
romfs_done:

    // DLC
    {
        char *dlc = pjoin(dump, "dlc");
        if (!dlc) {
            code = fail(x, RB_S2ARM_NS2_IO, "out of memory");
            goto done;
        }
        if (is_dir(dlc) && listdir(dlc, &dlcs) == -2) {
            free(dlc);
            code = fail(x, RB_S2ARM_NS2_IO, "out of memory");
            goto done;
        }
        for (size_t i = 0; i < dlcs.n; i++) {
            unsigned __int128 atid = 0;
            int negative = 0, parsed = parse_hex(dlcs.v[i], &atid, &negative);
            if (!parsed) continue;
            // idx = atid - tid - 0x1000 must be in (0, 0x1000)
            int in_range = parsed == 1 && !negative && atid > (unsigned __int128)tid + 0x1000 && atid - tid - 0x1000 < 0x1000;
            if (!in_range) {
                note(x, "DLC %s does not belong to program %016llx, skipped", dlcs.v[i], (unsigned long long)tid);
                continue;
            }
            unsigned idx = (unsigned)(atid - tid - 0x1000);
            char atid_hex[40], idx_text[16];
            hex128(atid_hex, atid);
            snprintf(idx_text, sizeof idx_text, "%u", idx);
            char *dd = pjoin(dlc, dlcs.v[i]);
            list_t vs_all = {0}, vs = {0};
            if (!dd || numdirs(dd, &vs_all)) {
                free(dd);
                free(dlc);
                code = fail(x, RB_S2ARM_NS2_IO, "out of memory");
                goto done;
            }
            for (size_t k = 0; k < vs_all.n; k++) {
                char *r = pjoin3(dd, vs_all.v[k], "romfs");
                if (r && is_dir(r)) list_add(&vs, sdup(vs_all.v[k]));
                free(r);
            }
            list_free(&vs_all);
            char *rd = vs.n ? pjoin3(dd, vs.v[vs.n - 1], "romfs") : pjoin(dd, "romfs");
            free(dd);
            int ok = rd != NULL;
            if (ok && !is_dir(rd)) {
                note(x, "DLC %s has no romfs (licence only?), recorded as licence only", dlcs.v[i]);
                ok = sb_fmt(&aoc_rows, "%u\t%s\t0\t-1\t0\n", idx, atid_hex);
            } else if (ok) {
                map_t fs = {0};
                char *area = pjoin("aoc", idx_text);
                uint64_t total = 0;
                if (!area || walk(rd, &fs)) ok = 0;
                for (size_t k = 0; ok && k < fs.n; k++) {
                    uint64_t sz = 0;
                    if ((code = place(x, &o, fs.abs[k], tmp, area, fs.rel[k]))) break;
                    if (file_size(fs.abs[k], &sz)) {
                        code = fail(x, RB_S2ARM_NS2_IO, "cannot stat %s", fs.abs[k]);
                        break;
                    }
                    total += sz;
                }
                if (!code && ok)
                    ok = (aoc_idx.n == 0 || sb_str(&aoc_idx, ",")) && sb_str(&aoc_idx, idx_text) &&
                         sb_fmt(&aoc_rows, "%u\t%s\t%s\t%zu\t%llu\n", idx, atid_hex, vs.n ? vs.v[vs.n - 1] : "0", fs.n, (unsigned long long)total);
                map_free(&fs);
                free(area);
            }
            free(rd);
            list_free(&vs);
            if (code || !ok) {
                free(dlc);
                if (!code) code = fail(x, RB_S2ARM_NS2_IO, "out of memory");
                goto done;
            }
        }
        free(dlc);
    }
    {
        char *p = pjoin(tmp, "aoc.tsv");
        int ok = p && sb_str(&text, "idx\ttitle_id\tversion\tfiles\tbytes\n") && (!aoc_rows.n || sb_add(&text, aoc_rows.p, aoc_rows.n)) &&
                 !write_all(p, text.p, text.n);
        free(p);
        if (!ok) {
            code = fail(x, RB_S2ARM_NS2_IO, "cannot write aoc.tsv");
            goto done;
        }
    }

    // control partition
    {
        char *ctl = pjoin(tmp, "ctl");
        if (!ctl || mkdir(ctl, 0777)) {
            free(ctl);
            code = fail(x, RB_S2ARM_NS2_IO, "cannot create ctl");
            goto done;
        }
        free(ctl);
    }
    {
        const char *dirs[2] = {upd ? upd : base, base};
        int found = 0;
        if (find_control(dirs, upd ? 2 : 1, nacp, &icon, &found)) {
            code = fail(x, RB_S2ARM_NS2_IO, "cannot read control.nacp");
            goto done;
        }
        char *norm = normpath(dump);
        if (!norm) {
            code = fail(x, RB_S2ARM_NS2_IO, "out of memory");
            goto done;
        }
        const char *slash = strrchr(norm, '/');
        dumpname = sdup(slash ? slash + 1 : norm);
        free(norm);
        const char *fallback = name && *name ? name : dumpname;
        char *path = pjoin3(tmp, "ctl", "control.nacp");
        if (!dumpname || !path) {
            free(path);
            code = fail(x, RB_S2ARM_NS2_IO, "out of memory");
            goto done;
        }
        if (found) {   // the exported control partition: title, version and icon are the game's own
            int r = write_all(path, nacp, NACP_SIZE);
            free(path);
            if (r) {
                code = fail(x, RB_S2ARM_NS2_IO, "cannot write control.nacp");
                goto done;
            }
            if (icon) {
                char *ip = pjoin(tmp, "icon.jpg");
                r = ip ? copy_file(icon, ip) : -1;
                free(ip);
                if (r) {
                    code = fail(x, RB_S2ARM_NS2_IO, "cannot copy %s", icon);
                    goto done;
                }
            }
            sb_t t0 = {0};
            int ok = nacp_title(&t0, nacp, 0) && nacp_title(&nzh, nacp, 14);
            if (ok && !nzh.n) ok = nacp_title(&nzh, nacp, 13);
            const uint8_t *v = nacp + 0x3060;
            static const char fffd[] = "\xEF\xBF\xBD";
            for (size_t k = 0; ok && k < 0x10 && v[k]; k++) ok = v[k] < 0x80 ? sb_add(&dver, (const char *)v + k, 1) : sb_add(&dver, fffd, 3);
            if (ok) {
                const char *pick = t0.n ? t0.p : nzh.n ? nzh.p : fallback;
                ok = sb_str(&nm, pick);
                if (ok && !nm.n) ok = sb_str(&nm, "");
            }
            free(t0.p);
            if (!ok) {
                code = fail(x, RB_S2ARM_NS2_IO, "out of memory");
                goto done;
            }
            if (!utf8_valid((const uint8_t *)nm.p, nm.n)) {
                code = fail(x, RB_S2ARM_NS2_INVALID, "the title is not valid UTF-8");
                goto done;
            }
            note(x, "control partition: the exported original");
        } else {   // none exported: synthesised, README.synth says it is not the game's own
            if (!sb_str(&nm, fallback)) {
                free(path);
                code = fail(x, RB_S2ARM_NS2_IO, "out of memory");
                goto done;
            }
            if (!utf8_valid((const uint8_t *)nm.p, nm.n)) {
                free(path);
                code = fail(x, RB_S2ARM_NS2_INVALID, "the title is not valid UTF-8");
                goto done;
            }
            int saves[3];
            if ((code = save_kinds(x, tmp_exefs, saves))) {
                free(path);
                goto done;
            }
            synth_nacp(nacp, tid, nm.p, saves);
            int r = write_all(path, nacp, NACP_SIZE);
            free(path);
            sb_t readme = {0};
            char tidhex[17];
            snprintf(tidhex, sizeof tidhex, "%016llx", (unsigned long long)tid);
            // The original's note, byte for byte (Chinese): "synthesised by pack/ns2_dump.py (the Switch 2 export has no
            // control partition): not the game's original. Program id <id>, title <name> taken from the export folder name".
            int ok = !r && sb_str(&readme, "# pack/ns2_dump.py \xe5\x90\x88\xe6\x88\x90\xef\xbc\x88Switch 2 \xe5\xaf\xbc\xe5\x87\xba\xe7\x9b\xae"
                                           "\xe5\xbd\x95\xe6\xb2\xa1\xe6\x9c\x89\xe6\x8e\xa7\xe5\x88\xb6\xe5\x88\x86\xe5\x8c\xba\xef\xbc\x89"
                                           "\xef\xbc\x9a\xe9\x9d\x9e\xe6\xb8\xb8\xe6\x88\x8f\xe5\x8e\x9f\xe4\xbb\xb6\xe3\x80\x82\xe7\xa8\x8b"
                                           "\xe5\xba\x8f\xe5\x8f\xb7 ") &&
                     sb_str(&readme, tidhex) && sb_str(&readme, "\xef\xbc\x8c\xe6\xa0\x87\xe9\xa2\x98\xe3\x80\x8c") && sb_str(&readme, nm.p) &&
                     sb_str(&readme, "\xe3\x80\x8d\xe5\x8f\x96\xe8\x87\xaa\xe5\xaf\xbc\xe5\x87\xba\xe7\x9b\xae\xe5\xbd\x95\xe5\x90\x8d\xef\xbc\x8c"
                                     "\xe4\xb8\x8d\xe6\x98\xaf\xe6\xb8\xb8\xe6\x88\x8f\xe8\x87\xaa\xe5\xb8\xa6\xe4\xbf\xa1\xe6\x81\xaf\n");
            char *rp = pjoin3(tmp, "ctl", "README.synth");
            ok = ok && rp && !write_all(rp, readme.p, readme.n);
            free(rp);
            free(readme.p);
            if (!ok) {
                code = fail(x, RB_S2ARM_NS2_IO, "cannot write the synthesised control partition");
                goto done;
            }
            note(x, "control.nacp synthesised (the export has no control partition; extra save kinds: %s%s%s%s)", saves[0] ? "temporary " : "",
                 saves[1] ? "device " : "", saves[2] ? "cache " : "", saves[0] || saves[1] || saves[2] ? "" : "none");
        }
    }
    {
        char tidhex[17];
        snprintf(tidhex, sizeof tidhex, "%016llx", (unsigned long long)tid);
        sb_t u = {0};
        int ok = sb_str(&u, "title_id\t") && sb_str(&u, tidhex) && sb_str(&u, "\nname\t") && sb_add(&u, nm.p ? nm.p : "", nm.n) &&
                 sb_str(&u, "\nname_zh\t") && sb_add(&u, nzh.p ? nzh.p : "", nzh.n) && sb_str(&u, "\ndisplay_version\t") &&
                 sb_add(&u, dver.p ? dver.p : "", dver.n) && sb_str(&u, "\nupdate\t") && sb_str(&u, ups.n ? ups.v[ups.n - 1] : "") &&
                 sb_str(&u, "\nbase\t0\nbuilds\t") && sb_add(&u, builds.p ? builds.p : "", builds.n) && sb_str(&u, "\naoc\t") &&
                 sb_add(&u, aoc_idx.p ? aoc_idx.p : "", aoc_idx.n) && sb_str(&u, "\n");
        char *p = pjoin(tmp, "unpack.tsv"), *k = pjoin(tmp, ".ns2_dump_key");
        char keyline[18];
        snprintf(keyline, sizeof keyline, "%s\n", key);
        ok = ok && p && k && !write_all(p, u.p, u.n) && !write_all(k, keyline, 17);
        free(p);
        free(k);
        free(u.p);
        if (!ok) {
            code = fail(x, RB_S2ARM_NS2_IO, "cannot write unpack.tsv");
            goto done;
        }
    }
    rmtree(out, 0);
    if (rename(tmp, out)) {
        code = fail(x, RB_S2ARM_NS2_IO, "cannot rename %s to %s", tmp, out);
        goto done;
    }
    made_tmp = 0;
    note(x, "Switch 2 export -> %s: program %016llx; romfs %zu files (%s); DLC %s; title %s", out, (unsigned long long)tid, rom_n,
         use_update_only ? "update only" : overlay ? "base + update" : "base", aoc_idx.n ? aoc_idx.p : "none", nm.p ? nm.p : "");
done:
    if (code && made_tmp && tmp) rmtree(tmp, 0);
    free(base), free(npdm0), free(updates), free(upd), free(tmp), free(exsrc), free(tmp_exefs), free(keyfile), free(icon), free(dumpname);
    free(nacp);
    list_free(&ups), list_free(&dlcs);
    map_free(&ex), map_free(&rb), map_free(&ru);
    free(o.final_out), free(o.real_dump), free(o.made_dir), free(builds.p), free(aoc_rows.p), free(aoc_idx.p), free(text.p), free(nm.p), free(nzh.p), free(dver.p);
    return code;
}

int rb_s2arm_ns2_dump(const rb_s2arm_ns2_dump_request *request, char *error, size_t error_size) {
    ctx_t x = {error, error_size, request};
    if (error && error_size) error[0] = 0;
    if (!request || !request->export_dir || !request->output_dir || !*request->output_dir)
        return fail(&x, RB_S2ARM_NS2_INVALID, "incomplete request");
    char *dump = is_dir(request->export_dir) ? find_dump(request->export_dir) : NULL;
    if (!dump) return fail(&x, RB_S2ARM_NS2_INVALID, "%s is not a Switch 2 export folder (needs base/exefs/main.npdm)", request->export_dir);
    char *out = normpath(request->output_dir);
    int code = out ? convert(&x, dump, out, request->name) : fail(&x, RB_S2ARM_NS2_IO, "out of memory");
    free(out);
    free(dump);
    return code;
}
