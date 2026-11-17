// RewindBox: port of S2Arm pack/ns2_nup.py (see s2arm_nup.h). Structures and checks follow the original's
// Nup._read, scan, write_tree, write_control and convert in that order.
#include "s2arm_nup.h"
#include "s2arm_sha256.h"
#include "../../../packages/libretro_internal_bridge/ios/ThirdParty/libchdr/deps/zstd-1.5.7/zstd.h"

#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
#if defined(__APPLE__)
#include <sys/clonefile.h>
#endif

#define NUP_PORT_TAG "rewindbox-ns2-nup-1"
#define NO_DIR 0xFFFFFFFFu
enum { SUPER_SIZE = 0x80, TOC_HEAD = 0x30, PKG_SIZE = 0x40, DIR_SIZE = 0x18, FILE_SIZE = 0x50, TLV_SIZE = 8 };
enum { K_BASE = 0, K_UPDATE = 1, K_ADDON = 2, K_COUNT = 5 };
enum { STANDALONE = 1, T_NACP = 2, T_ICON = 3, T_LICONS = 10 };
enum { RAW_CHUNK = 8 << 20, Z_CHUNK = 4 << 20, NPDM_MAX = 16 << 20, MAX_DEPTH = 256 };

typedef struct {
    uint64_t title_id, meta_off;
    uint32_t root, exefs, romfs, version, meta_size;
    uint8_t kind, flags;
} nup_pkg;
typedef struct { const uint8_t *name; uint32_t name_len, first, count; } nup_dir;
typedef struct { const uint8_t *name; uint32_t name_len; uint64_t size, eoff, esz; uint8_t sha[32]; uint8_t codec; } nup_file;
typedef struct { const uint8_t *name; uint32_t name_len; int isdir; uint64_t index; } nup_child;

typedef struct {
    const char *path;
    int fd;
    uint64_t fsize, blob;
    uint8_t toc_sha[32];
    uint8_t *toc;
    uint64_t toc_size;
    nup_pkg *pkgs;
    uint32_t npkg;
    nup_dir *dirs;
    uint64_t ndirs;
    nup_file *files;
    uint64_t nfiles;
    const uint8_t *slots;
    uint64_t nslots;
    const rb_s2arm_nup_request *rq;
    uint64_t done, total;
    char *err;
    size_t errn;
    uint8_t *buf, *zbuf;
    ZSTD_DStream *zs;
} nup_t;

static uint16_t rd16(const uint8_t *p) { return (uint16_t)(p[0] | p[1] << 8); }
static uint32_t rd32(const uint8_t *p) { return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24; }
static uint64_t rd64(const uint8_t *p) { return (uint64_t)rd32(p) | (uint64_t)rd32(p + 4) << 32; }

static int fail(nup_t *n, int code, const char *fmt, ...) {
    if (n->err && n->errn && !n->err[0]) {
        va_list ap;
        va_start(ap, fmt);
        vsnprintf(n->err, n->errn, fmt, ap);
        va_end(ap);
    }
    return code;
}

// A path built with a format; refused when it does not fit
static int pathf(nup_t *n, char *out, size_t size, const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    int len = vsnprintf(out, size, fmt, ap);
    va_end(ap);
    return len < 0 || (size_t)len >= size ? fail(n, RB_S2ARM_NUP_IO, "path too long: %.200s", out) : 0;
}

static void say(nup_t *n, const char *fmt, ...) {
    if (!n->rq || !n->rq->note) return;
    char line[1024];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(line, sizeof line, fmt, ap);
    va_end(ap);
    n->rq->note(n->rq->context, line);
}

static int cancelled(nup_t *n) { return n->rq && n->rq->cancelled && n->rq->cancelled(n->rq->context); }

static int read_at(nup_t *n, void *dst, uint64_t len, uint64_t off) {
    uint8_t *p = dst;
    while (len) {
        ssize_t got = pread(n->fd, p, len > (1u << 30) ? (1u << 30) : (size_t)len, (off_t)off);
        if (got < 0 && errno == EINTR) continue;
        if (got <= 0) return fail(n, RB_S2ARM_NUP_IO, "%s: read failed at %llu (%s)", n->path, (unsigned long long)off, got < 0 ? strerror(errno) : "end of file");
        p += got;
        off += (uint64_t)got;
        len -= (uint64_t)got;
    }
    return 0;
}

// ---------- Nup._read ----------
static int name_at(nup_t *n, const uint8_t *pool, uint64_t pool_size, uint32_t off, uint32_t len, const uint8_t **out) {
    if ((uint64_t)off + len > pool_size) return fail(n, RB_S2ARM_NUP_INVALID, "%s: a name is out of bounds", n->path);
    *out = pool + off;
    return 0;
}

static int nup_read(nup_t *n) {
    struct stat st;
    if (fstat(n->fd, &st)) return fail(n, RB_S2ARM_NUP_IO, "%s: %s", n->path, strerror(errno));
    n->fsize = (uint64_t)st.st_size;
    if (!n->fsize) return fail(n, RB_S2ARM_NUP_INVALID, "%s: empty file", n->path);
    if (n->fsize < SUPER_SIZE) return fail(n, RB_S2ARM_NUP_INVALID, "%s: not a NUP (too short)", n->path);
    uint8_t s[SUPER_SIZE];
    int rc = read_at(n, s, SUPER_SIZE, 0);
    if (rc) return rc;
    if (memcmp(s, "NUP", 3)) return fail(n, RB_S2ARM_NUP_INVALID, "%s: not a NUP", n->path);
    if (s[3] != 1) return fail(n, RB_S2ARM_NUP_INVALID, "%s: NUP format version %u, only version 1 is read", n->path, s[3]);
    uint16_t hsize = rd16(s + 4);
    uint64_t toc_off = rd64(s + 8), toc_size = rd64(s + 16), fsize = rd64(s + 64);
    uint32_t npkg = rd32(s + 72), flags = rd32(s + 76);
    memcpy(n->toc_sha, s + 24, 32);
    n->blob = rd64(s + 56);
    if (hsize < SUPER_SIZE || toc_off != hsize || flags) return fail(n, RB_S2ARM_NUP_INVALID, "%s: unsupported NUP header", n->path);
    if (fsize != n->fsize)
        return fail(n, RB_S2ARM_NUP_INVALID, "%s: the file has %llu bytes, its header says %llu (copied or downloaded only in part?)", n->path,
                    (unsigned long long)n->fsize, (unsigned long long)fsize);
    if (toc_off > fsize || toc_size > fsize - toc_off || n->blob < toc_off + toc_size || n->blob % 16 || n->blob > fsize)
        return fail(n, RB_S2ARM_NUP_INVALID, "%s: the table of contents overlaps the data area", n->path);
    n->toc_size = toc_size;
    n->toc = malloc(toc_size ? (size_t)toc_size : 1);
    if (!n->toc) return fail(n, RB_S2ARM_NUP_IO, "%s: out of memory for a table of contents of %llu bytes", n->path, (unsigned long long)toc_size);
    if ((rc = read_at(n, n->toc, toc_size, toc_off))) return rc;
    uint8_t sha[32];
    s2arm_sha256(n->toc, (size_t)toc_size, sha);
    if (memcmp(sha, n->toc_sha, 32)) return fail(n, RB_S2ARM_NUP_INVALID, "%s: the table of contents does not match its SHA-256 (damaged file)", n->path);
    const uint8_t *t = n->toc;
    if (toc_size < TOC_HEAD) return fail(n, RB_S2ARM_NUP_INVALID, "%s: malformed table of contents", n->path);
    uint32_t tpkg = rd32(t + 4);
    uint64_t ndirs = rd64(t + 8), nfiles = rd64(t + 16), pool_off = rd64(t + 24), pool_size = rd64(t + 32);
    // need = TOC + packages + directories + files, without overflow (each count is bounded by the table's own size first)
    int bad = memcmp(t, "TOC\x01", 4) || tpkg != npkg || !npkg || ndirs > toc_size || nfiles > toc_size;
    uint64_t need = bad ? 0 : TOC_HEAD + (uint64_t)tpkg * PKG_SIZE + ndirs * DIR_SIZE + nfiles * FILE_SIZE;
    if (bad || toc_size < need || pool_off < need || pool_off > toc_size || pool_size > toc_size - pool_off || (pool_off - need) % 4)
        return fail(n, RB_S2ARM_NUP_INVALID, "%s: malformed table of contents", n->path);
    const uint8_t *pool = t + pool_off;
    uint64_t p = TOC_HEAD;
    n->npkg = npkg;
    n->ndirs = ndirs;
    n->nfiles = nfiles;
    n->pkgs = calloc(npkg, sizeof *n->pkgs);
    n->dirs = calloc(ndirs ? ndirs : 1, sizeof *n->dirs);
    n->files = calloc(nfiles ? nfiles : 1, sizeof *n->files);
    if (!n->pkgs || !n->dirs || !n->files) return fail(n, RB_S2ARM_NUP_IO, "%s: out of memory", n->path);
    for (uint32_t i = 0; i < npkg; i++, p += PKG_SIZE) {
        const uint8_t *r = t + p;
        nup_pkg *k = &n->pkgs[i];
        k->title_id = rd64(r);
        k->root = rd32(r + 8);
        k->exefs = rd32(r + 12);
        k->romfs = rd32(r + 16);
        k->version = rd32(r + 20);
        k->kind = r[24];
        k->flags = r[25];
        k->meta_off = rd64(r + 32);
        k->meta_size = rd32(r + 40);
        if (k->kind >= K_COUNT) return fail(n, RB_S2ARM_NUP_INVALID, "%s: package %u has an unknown kind (%u)", n->path, i, k->kind);
        if (rd16(r + 26) || rd32(r + 28) || (k->flags & ~STANDALONE))
            return fail(n, RB_S2ARM_NUP_INVALID, "%s: package %u has reserved fields or flags that are not 0", n->path, i);
    }
    for (uint64_t i = 0; i < ndirs; i++, p += DIR_SIZE) {
        const uint8_t *r = t + p;
        nup_dir *d = &n->dirs[i];
        d->name_len = rd32(r + 4);
        d->first = rd32(r + 8);
        d->count = rd32(r + 12);
        if ((rc = name_at(n, pool, pool_size, rd32(r), d->name_len, &d->name))) return rc;
    }
    for (uint64_t i = 0; i < nfiles; i++, p += FILE_SIZE) {
        const uint8_t *r = t + p;
        nup_file *f = &n->files[i];
        uint32_t o = rd32(r);
        f->name_len = rd32(r + 4);
        f->size = rd64(r + 8);
        f->eoff = rd64(r + 16);
        f->esz = rd64(r + 24);
        memcpy(f->sha, r + 32, 32);
        f->codec = r[64];
        if ((rc = name_at(n, pool, pool_size, o, f->name_len, &f->name))) return rc;
        if (f->codec > 1 || r[65])
            return fail(n, RB_S2ARM_NUP_INVALID, "%s: file %.*s uses codec %u; only stored and zstd files are read", n->path, (int)f->name_len, f->name, f->codec);
        if (f->size && (f->eoff < n->blob || f->eoff > n->fsize || f->esz > n->fsize - f->eoff || f->eoff % 16 || !f->esz || (f->codec == 0 && f->esz != f->size)))
            return fail(n, RB_S2ARM_NUP_INVALID, "%s: file %.*s is out of bounds", n->path, (int)f->name_len, f->name);
        if (!f->size && (f->eoff || f->esz || f->codec))
            return fail(n, RB_S2ARM_NUP_INVALID, "%s: empty file %.*s has data", n->path, (int)f->name_len, f->name);
    }
    n->slots = t + p;
    n->nslots = (pool_off - p) / 4;
    for (uint64_t i = 0; i < ndirs; i++)
        if ((uint64_t)n->dirs[i].first + n->dirs[i].count > n->nslots)
            return fail(n, RB_S2ARM_NUP_INVALID, "%s: directory %.*s is out of bounds", n->path, (int)n->dirs[i].name_len, n->dirs[i].name);
    for (uint64_t i = 0; i < n->nslots; i++)
        if (rd32(n->slots + 4 * i) >= ndirs + nfiles) return fail(n, RB_S2ARM_NUP_INVALID, "%s: child %u is out of bounds", n->path, rd32(n->slots + 4 * i));
    for (uint32_t i = 0; i < npkg; i++) {
        const nup_pkg *k = &n->pkgs[i];
        if (k->root >= ndirs || (k->exefs != NO_DIR && k->exefs >= ndirs) || (k->romfs != NO_DIR && k->romfs >= ndirs) ||
            (k->meta_size && (k->meta_off > n->fsize || k->meta_size > n->fsize - k->meta_off)))
            return fail(n, RB_S2ARM_NUP_INVALID, "%s: package %u is out of bounds", n->path, i);
    }
    return 0;
}

// ---------- children / child / tree_bytes ----------
static int name_cmp(const uint8_t *a, uint32_t an, const uint8_t *b, uint32_t bn) {
    int c = memcmp(a, b, an < bn ? an : bn);
    return c ? c : an < bn ? -1 : an > bn;
}
static int child_cmp(const void *x, const void *y) {   // Python's sorted() of (name, isdir, index)
    const nup_child *a = x, *b = y;
    int c = name_cmp(a->name, a->name_len, b->name, b->name_len);
    if (c) return c;
    if (a->isdir != b->isdir) return a->isdir - b->isdir;
    return a->index < b->index ? -1 : a->index > b->index;
}
static int is_artifact(const uint8_t *name, uint32_t len) { return len == 8 && !memcmp(name, ".listing", 8); }   // SPEC section 6.3: the exporter's file

// The children of directory d, sorted, without the exporter's .listing; *out is malloc'ed (free it)
static int children(nup_t *n, uint32_t d, nup_child **out, uint32_t *count) {
    const nup_dir *dir = &n->dirs[d];
    nup_child *c = malloc((dir->count ? dir->count : 1) * sizeof *c);
    if (!c) return fail(n, RB_S2ARM_NUP_IO, "out of memory");
    uint32_t k = 0;
    for (uint32_t i = 0; i < dir->count; i++) {
        uint64_t s = rd32(n->slots + 4 * ((uint64_t)dir->first + i));
        if (s < n->ndirs) c[k++] = (nup_child){n->dirs[s].name, n->dirs[s].name_len, 1, s};
        else if (!is_artifact(n->files[s - n->ndirs].name, n->files[s - n->ndirs].name_len))
            c[k++] = (nup_child){n->files[s - n->ndirs].name, n->files[s - n->ndirs].name_len, 0, s - n->ndirs};
    }
    qsort(c, k, sizeof *c, child_cmp);
    *out = c;
    *count = k;
    return 0;
}

static int64_t child_file(nup_t *n, uint32_t d, const char *name) {   // -1: none (or out of memory)
    nup_child *c;
    uint32_t k;
    if (children(n, d, &c, &k)) return -1;
    int64_t hit = -1;
    size_t len = strlen(name);
    for (uint32_t i = 0; i < k && hit < 0; i++)
        if (!c[i].isdir && c[i].name_len == len && !memcmp(c[i].name, name, len)) hit = (int64_t)c[i].index;
    free(c);
    return hit;
}

static int tree_bytes(nup_t *n, uint32_t d, uint64_t *sum, int depth) {
    if (depth > MAX_DEPTH) return fail(n, RB_S2ARM_NUP_INVALID, "%s: directories nest too deep (a cycle?)", n->path);
    nup_child *c;
    uint32_t k;
    int rc = children(n, d, &c, &k);
    for (uint32_t i = 0; !rc && i < k; i++) {
        if (c[i].isdir) rc = tree_bytes(n, (uint32_t)c[i].index, sum, depth + 1);
        else *sum += n->files[c[i].index].size;
    }
    free(c);
    return rc;
}

// ---------- Nup.copy: file i to fd (or into a memory buffer), checking its size and SHA-256 ----------
typedef struct { int fd; uint8_t *mem; uint64_t cap, len; } sink_t;

static int put(nup_t *n, sink_t *o, s2arm_sha256_ctx *h, const uint8_t *b, size_t len, uint64_t *count) {
    s2arm_sha256_update(h, b, len);
    *count += len;
    if (o->mem) {
        if (o->len + len > o->cap) return fail(n, RB_S2ARM_NUP_INVALID, "%s: a file read into memory is larger than %llu bytes", n->path, (unsigned long long)o->cap);
        memcpy(o->mem + o->len, b, len);
        o->len += len;
        return 0;
    }
    while (len) {
        ssize_t w = write(o->fd, b, len);
        if (w < 0 && errno == EINTR) continue;
        if (w <= 0) return fail(n, RB_S2ARM_NUP_IO, "write failed (%s)", w < 0 ? strerror(errno) : "no progress");
        b += w;
        len -= (size_t)w;
        n->done += (uint64_t)w;
    }
    if (n->rq && n->rq->progress) n->rq->progress(n->rq->context, n->done, n->total);
    return 0;
}

static int copy_file(nup_t *n, uint64_t i, sink_t *o) {
    const nup_file *f = &n->files[i];
    s2arm_sha256_ctx h;
    s2arm_sha256_init(&h);
    uint64_t count = 0;
    int rc = 0, frame_done = 0;
    if (f->codec == 0) {
        for (uint64_t p = f->eoff; !rc && p < f->eoff + f->esz; p += RAW_CHUNK) {
            if (cancelled(n)) return RB_S2ARM_NUP_CANCELLED;
            uint64_t len = f->eoff + f->esz - p < RAW_CHUNK ? f->eoff + f->esz - p : RAW_CHUNK;
            if (!(rc = read_at(n, n->buf, len, p))) rc = put(n, o, &h, n->buf, (size_t)len, &count);
        }
    } else if (f->size) {
        if (!n->zs && !(n->zs = ZSTD_createDStream())) return fail(n, RB_S2ARM_NUP_IO, "out of memory for the zstd decoder");
        size_t init = ZSTD_initDStream(n->zs);
        if (ZSTD_isError(init)) return fail(n, RB_S2ARM_NUP_IO, "zstd: %s", ZSTD_getErrorName(init));
        for (uint64_t p = f->eoff; !rc && !frame_done && p < f->eoff + f->esz; p += Z_CHUNK) {
            if (cancelled(n)) return RB_S2ARM_NUP_CANCELLED;
            uint64_t len = f->eoff + f->esz - p < Z_CHUNK ? f->eoff + f->esz - p : Z_CHUNK;
            if ((rc = read_at(n, n->buf, len, p))) break;
            ZSTD_inBuffer in = {n->buf, (size_t)len, 0};
            while (!rc && in.pos < in.size) {
                ZSTD_outBuffer out = {n->zbuf, ZSTD_DStreamOutSize(), 0};
                size_t r = ZSTD_decompressStream(n->zs, &out, &in);
                if (ZSTD_isError(r)) return fail(n, RB_S2ARM_NUP_INVALID, "%s: %.*s: %s", n->path, (int)f->name_len, f->name, ZSTD_getErrorName(r));
                if (out.pos) rc = put(n, o, &h, n->zbuf, out.pos, &count);
                if (!rc && count > f->size) break;
                if (!r) { frame_done = 1; break; }
            }
            if (!rc && frame_done && (in.pos < in.size || p + len < f->eoff + f->esz))   // deliberate difference: data after the frame is refused
                return fail(n, RB_S2ARM_NUP_INVALID, "%s: %.*s: data after its zstd frame", n->path, (int)f->name_len, f->name);
            if (!rc && count > f->size) break;
        }
        for (int guard = 0; !rc && !frame_done && count <= f->size && guard < 1 << 20; guard++) {   // what the decoder still holds
            ZSTD_inBuffer in = {NULL, 0, 0};
            ZSTD_outBuffer out = {n->zbuf, ZSTD_DStreamOutSize(), 0};
            size_t r = ZSTD_decompressStream(n->zs, &out, &in);
            if (ZSTD_isError(r)) return fail(n, RB_S2ARM_NUP_INVALID, "%s: %.*s: %s", n->path, (int)f->name_len, f->name, ZSTD_getErrorName(r));
            if (out.pos) rc = put(n, o, &h, n->zbuf, out.pos, &count);
            if (!r) frame_done = 1;
            else if (!out.pos) break;
        }
        if (!rc && count <= f->size && !frame_done) count = UINT64_MAX;   // the frame does not end (the original: n = -1)
    }
    if (rc) return rc;
    uint8_t sha[32];
    s2arm_sha256_final(&h, sha);
    if (count != f->size || memcmp(sha, f->sha, 32))
        return fail(n, RB_S2ARM_NUP_INVALID, "%s: %.*s does not match its size or SHA-256 (damaged file)", n->path, (int)f->name_len, f->name);
    return 0;
}

// ---------- program id (NPDM ACI0), scan ----------
static int program_id(nup_t *n, uint64_t i, const char *where, uint64_t *pid) {
    const nup_file *f = &n->files[i];
    if (f->size > NPDM_MAX) return fail(n, RB_S2ARM_NUP_INVALID, "%s: %s is larger than %u bytes", n->path, where, NPDM_MAX);
    sink_t o = {-1, malloc(f->size ? (size_t)f->size : 1), f->size, 0};
    if (!o.mem) return fail(n, RB_S2ARM_NUP_IO, "out of memory");
    int rc = copy_file(n, i, &o);
    const uint8_t *b = o.mem;
    uint64_t len = o.len;
    if (!rc && (len < 4 || memcmp(b, "META", 4))) rc = fail(n, RB_S2ARM_NUP_INVALID, "%s: %s: not an NPDM", n->path, where);
    if (!rc && len < 0x78) rc = fail(n, RB_S2ARM_NUP_INVALID, "%s: %s: no ACI0 section", n->path, where);
    uint32_t off = rc ? 0 : rd32(b + 0x70), size = rc ? 0 : rd32(b + 0x74);
    if (!rc && ((uint64_t)off + 0x18 > len || memcmp(b + off, "ACI0", 4) || size < 0x18)) rc = fail(n, RB_S2ARM_NUP_INVALID, "%s: %s: no ACI0 section", n->path, where);
    if (!rc) *pid = rd64(b + off + 0x10);
    free(o.mem);
    return rc;
}

typedef struct { uint64_t app; const nup_pkg *base, *update; const nup_pkg **dlc; uint32_t ndlc; } nup_scan;

static int dlc_cmp(const void *x, const void *y) {
    const nup_pkg *a = *(const nup_pkg *const *)x, *b = *(const nup_pkg *const *)y;
    return a->title_id < b->title_id ? -1 : a->title_id > b->title_id;
}

static int scan(nup_t *n, nup_scan *sc) {
    memset(sc, 0, sizeof *sc);
    const nup_pkg *base0 = NULL;
    uint32_t bases = 0, updates = 0, standalone = 0;
    for (uint32_t i = 0; i < n->npkg; i++) {
        const nup_pkg *k = &n->pkgs[i];
        if (k->kind == K_BASE && !bases++) base0 = k;
        if (k->kind == K_UPDATE) { updates++; standalone += (k->flags & STANDALONE) != 0; }
    }
    if (bases > 1) return fail(n, RB_S2ARM_NUP_INVALID, "%s: %u base packages", n->path, bases);
    if (!bases && (!updates || standalone != updates))
        return fail(n, RB_S2ARM_NUP_INVALID, "%s: no base: pack the base and the update into the same NUP, or mark the update standalone_update with whole exefs/ and romfs/", n->path);
    if (base0) {
        uint64_t sum = 0;
        int rc = tree_bytes(n, base0->root, &sum, 0);
        if (rc) return rc;
        if (sum) sc->base = base0;
    }
    uint64_t app = 0;
    int have = 0;
    for (uint32_t i = 0; i < n->npkg; i++) {
        const nup_pkg *k = &n->pkgs[i];
        if ((k->kind != K_BASE && k->kind != K_UPDATE) || k->exefs == NO_DIR) continue;
        int64_t m = child_file(n, k->exefs, "main.npdm");
        if (m < 0) continue;
        char where[96];
        snprintf(where, sizeof where, "%s %u exefs/main.npdm", k->kind == K_BASE ? "base" : "update", k->version);
        uint64_t pid = 0;
        int rc = program_id(n, (uint64_t)m, where, &pid);
        if (rc) return rc;
        if (have && pid != app)
            return fail(n, RB_S2ARM_NUP_INVALID, "%s: the base and the updates have different program ids: %016llX, %016llX", n->path,
                        (unsigned long long)(app < pid ? app : pid), (unsigned long long)(app < pid ? pid : app));
        app = pid;
        have = 1;
    }
    if (!have) return fail(n, RB_S2ARM_NUP_INVALID, "%s: no exefs/main.npdm in the base or the updates", n->path);
    if (app & 0xFFF) return fail(n, RB_S2ARM_NUP_INVALID, "%s: program id %016llX is not a base title id", n->path, (unsigned long long)app);
    sc->app = app;
    sc->dlc = calloc(n->npkg, sizeof *sc->dlc);
    if (!sc->dlc) return fail(n, RB_S2ARM_NUP_IO, "out of memory");
    for (uint32_t i = 0; i < n->npkg; i++) {
        const nup_pkg *k = &n->pkgs[i];
        if (k->kind == K_UPDATE) {
            for (uint32_t j = 0; j < i; j++)
                if (n->pkgs[j].kind == K_UPDATE && n->pkgs[j].version == k->version)
                    return fail(n, RB_S2ARM_NUP_INVALID, "%s: two updates of version %u", n->path, k->version);
            if (!k->version) return fail(n, RB_S2ARM_NUP_INVALID, "%s: an update of version 0", n->path);
            if (!sc->update || k->version > sc->update->version) sc->update = k;
        } else if (k->kind == K_ADDON) {
            if (k->title_id <= app + 0x1000 || k->title_id > app + 0x1000 + 2000)
                return fail(n, RB_S2ARM_NUP_INVALID, "%s: %016llX is not a DLC of %016llX", n->path, (unsigned long long)k->title_id, (unsigned long long)app);
            if (k->romfs == NO_DIR) return fail(n, RB_S2ARM_NUP_INVALID, "%s: DLC %016llX has no romfs/", n->path, (unsigned long long)k->title_id);
            for (uint32_t j = 0; j < sc->ndlc; j++)
                if (sc->dlc[j]->title_id == k->title_id)
                    return fail(n, RB_S2ARM_NUP_INVALID, "%s: DLC %016llX appears more than once", n->path, (unsigned long long)k->title_id);
            sc->dlc[sc->ndlc++] = k;
        }
    }
    qsort(sc->dlc, sc->ndlc, sizeof *sc->dlc, dlc_cmp);
    return 0;
}

// ---------- files and folders ----------
static int mkdirs(nup_t *n, const char *path) {
    char p[4096];
    size_t len = strlen(path);
    if (len >= sizeof p) return fail(n, RB_S2ARM_NUP_IO, "path too long: %s", path);
    memcpy(p, path, len + 1);
    for (size_t i = 1; i <= len; i++) {
        if (p[i] != '/' && p[i]) continue;
        char c = p[i];
        p[i] = 0;
        if (mkdir(p, 0755) && errno != EEXIST) return fail(n, RB_S2ARM_NUP_IO, "cannot make %s (%s)", p, strerror(errno));
        p[i] = c;
    }
    return 0;
}

static int rm_tree(const char *path) {   // 0 also when nothing is there
    struct stat st;
    if (lstat(path, &st)) return errno == ENOENT ? 0 : -1;
    if (!S_ISDIR(st.st_mode)) return unlink(path);
    DIR *d = opendir(path);
    if (!d) return -1;
    struct dirent *e;
    int rc = 0;
    while ((e = readdir(d))) {
        if (!strcmp(e->d_name, ".") || !strcmp(e->d_name, "..")) continue;
        char sub[4096];
        if (snprintf(sub, sizeof sub, "%s/%s", path, e->d_name) >= (int)sizeof sub) { rc = -1; continue; }
        if (rm_tree(sub)) rc = -1;
    }
    closedir(d);
    return rmdir(path) ? -1 : rc;
}

static int join(nup_t *n, char *out, size_t size, const char *dir, const uint8_t *name, uint32_t len) {   // safe_name: no '', '.', '..', NUL, '/' or '\'
    if (!len || (len == 1 && name[0] == '.') || (len == 2 && name[0] == '.' && name[1] == '.') || memchr(name, 0, len) || memchr(name, '/', len) ||
        memchr(name, '\\', len))
        return fail(n, RB_S2ARM_NUP_INVALID, "%s: invalid file name %.*s", n->path, (int)len, name);
    if (snprintf(out, size, "%s/%.*s", dir, (int)len, name) >= (int)size) return fail(n, RB_S2ARM_NUP_IO, "path too long in %s", dir);
    return 0;
}

static int write_tree(nup_t *n, uint32_t d, const char *dst, uint64_t *files, int depth) {
    if (depth > MAX_DEPTH) return fail(n, RB_S2ARM_NUP_INVALID, "%s: directories nest too deep (a cycle?)", n->path);
    int rc = mkdirs(n, dst);
    if (rc) return rc;
    nup_child *c;
    uint32_t k;
    if ((rc = children(n, d, &c, &k))) return rc;
    for (uint32_t i = 0; !rc && i < k; i++) {
        char p[4096];
        if ((rc = join(n, p, sizeof p, dst, c[i].name, c[i].name_len))) break;
        if (c[i].isdir) {
            rc = write_tree(n, (uint32_t)c[i].index, p, files, depth + 1);
            continue;
        }
        sink_t o = {open(p, O_WRONLY | O_CREAT | O_TRUNC, 0644), NULL, 0, 0};
        if (o.fd < 0) {
            rc = fail(n, RB_S2ARM_NUP_IO, "cannot write %s (%s)", p, strerror(errno));
            break;
        }
        rc = copy_file(n, c[i].index, &o);
        if (close(o.fd) && !rc) rc = fail(n, RB_S2ARM_NUP_IO, "cannot write %s (%s)", p, strerror(errno));
        ++*files;
    }
    free(c);
    return rc;
}

static int write_bytes(nup_t *n, const char *path, const uint8_t *b, size_t len) {
    int fd = open(path, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (fd < 0) return fail(n, RB_S2ARM_NUP_IO, "cannot write %s (%s)", path, strerror(errno));
    while (len) {
        ssize_t w = write(fd, b, len);
        if (w < 0 && errno == EINTR) continue;
        if (w <= 0) {
            close(fd);
            return fail(n, RB_S2ARM_NUP_IO, "cannot write %s (%s)", path, w < 0 ? strerror(errno) : "no progress");
        }
        b += w;
        len -= (size_t)w;
    }
    return close(fd) ? fail(n, RB_S2ARM_NUP_IO, "cannot write %s (%s)", path, strerror(errno)) : 0;
}

// ---------- Package.meta, localized_icon, write_control ----------
typedef struct { const uint8_t *nacp, *icon, *licons; uint64_t nacp_len, icon_len, licons_len; int has_nacp, has_icon, has_licons; } nup_meta;

static int read_meta(nup_t *n, const nup_pkg *k, uint8_t **owned, nup_meta *m) {   // the first TLV of each type, as setdefault keeps it
    *owned = NULL;
    if (!k->meta_size) return 0;
    uint8_t *b = malloc(k->meta_size);
    if (!b) return fail(n, RB_S2ARM_NUP_IO, "out of memory");
    int rc = read_at(n, b, k->meta_size, k->meta_off);
    if (rc) {
        free(b);
        return rc;
    }
    *owned = b;
    for (uint64_t p = 0; p + TLV_SIZE <= k->meta_size;) {
        uint16_t t = rd16(b + p);
        uint32_t len = rd32(b + p + 4);
        p += TLV_SIZE;
        if (p + len > k->meta_size) return fail(n, RB_S2ARM_NUP_INVALID, "%s: the metadata %#x of package %ld runs past its block", n->path, t, (long)(k - n->pkgs));
        if (t == T_NACP && !m->has_nacp) { m->nacp = b + p; m->nacp_len = len; m->has_nacp = 1; }
        if (t == T_ICON && !m->has_icon) { m->icon = b + p; m->icon_len = len; m->has_icon = 1; }
        if (t == T_LICONS && !m->has_licons) { m->licons = b + p; m->licons_len = len; m->has_licons = 1; }
        p += len;
    }
    return 0;
}

static void merge_meta(nup_meta *into, const nup_meta *from) {   // dict.update: from's entries replace
    if (from->has_nacp) { into->nacp = from->nacp; into->nacp_len = from->nacp_len; into->has_nacp = 1; }
    if (from->has_icon) { into->icon = from->icon; into->icon_len = from->icon_len; into->has_icon = 1; }
    if (from->has_licons) { into->licons = from->licons; into->licons_len = from->licons_len; into->has_licons = 1; }
}

// The English icon of a localized icon record (TLV 0x000A), else the first: [tag length][tag][u32 size][data]...
static void localized_icon(const uint8_t *b, uint64_t len, const uint8_t **icon, uint64_t *icon_len) {
    const uint8_t *first = NULL, *en = NULL, *enus = NULL;
    uint64_t first_n = 0, en_n = 0, enus_n = 0;
    int have_first = 0, have_en = 0, have_enus = 0;
    uint64_t p = 0;
    while (p < len) {
        uint64_t ln = b[p];
        const uint8_t *tag = b + p + 1;
        uint64_t tag_n = p + 1 + ln <= len ? ln : (p + 1 < len ? len - p - 1 : 0);
        p += 1 + ln;
        if (p + 4 > len) break;
        uint64_t dn = rd32(b + p);
        p += 4;
        const uint8_t *data = b + p;
        uint64_t data_n = p + dn <= len ? dn : len - p;
        p += dn;
        char low[256];
        for (uint64_t i = 0; i < tag_n; i++) low[i] = (char)(tag[i] >= 'A' && tag[i] <= 'Z' ? tag[i] + 32 : tag[i]);
        if (tag_n == 5 && !memcmp(low, "en-us", 5) && !have_enus) { enus = data; enus_n = data_n; have_enus = 1; }
        if (tag_n == 2 && !memcmp(low, "en", 2) && !have_en) { en = data; en_n = data_n; have_en = 1; }
        if (!have_first) { first = data; first_n = data_n; have_first = 1; }
    }
    // out.get('en-us') or out.get('en') or next(iter(out.values()), None): an empty entry counts as missing
    if (have_enus && enus_n) { *icon = enus; *icon_len = enus_n; }
    else if (have_en && en_n) { *icon = en; *icon_len = en_n; }
    else if (have_first) { *icon = first; *icon_len = first_n; }
    else { *icon = NULL; *icon_len = 0; }
}

static int write_control(nup_t *n, const nup_pkg *k, const nup_pkg *base, const char *dst, int *wrote) {
    *wrote = 0;
    nup_meta m = {0}, mk = {0};
    uint8_t *own1 = NULL, *own2 = NULL;
    int rc = 0;
    if (k->kind != K_BASE && !base) {
        const nup_pkg *holder = NULL;
        for (uint32_t i = 0; i < n->npkg && !holder; i++) if (n->pkgs[i].kind == K_BASE) holder = &n->pkgs[i];
        if (holder) rc = read_meta(n, holder, &own1, &m);
    }
    if (!rc) rc = read_meta(n, k, &own2, &mk);
    if (!rc) {
        merge_meta(&m, &mk);
        const uint8_t *icon = m.has_icon && m.icon_len ? m.icon : NULL;
        uint64_t icon_len = icon ? m.icon_len : 0;
        if (!icon && m.has_licons) localized_icon(m.licons, m.licons_len, &icon, &icon_len);
        else if (!icon) icon_len = 0;
        if (m.has_nacp && m.nacp_len == 0x4000) {
            char p[4096];
            if (!(rc = pathf(n, p, sizeof p, "%s/control.nacp", dst))) rc = write_bytes(n, p, m.nacp, 0x4000);
            if (!rc && icon && icon_len && !(rc = pathf(n, p, sizeof p, "%s/icon_AmericanEnglish.dat", dst))) rc = write_bytes(n, p, icon, (size_t)icon_len);
            if (!rc) *wrote = 1;
        }
    }
    free(own1);
    free(own2);
    return rc;
}

// copytree(updates/<v>/<part>, base/<part>): a clone on APFS, else a byte copy
static int copy_tree(nup_t *n, const char *src, const char *dst) {
    struct stat st;
    if (lstat(src, &st)) return errno == ENOENT ? 0 : fail(n, RB_S2ARM_NUP_IO, "cannot read %s (%s)", src, strerror(errno));
#if defined(__APPLE__)
    if (S_ISDIR(st.st_mode) && !clonefile(src, dst, CLONE_NOFOLLOW)) return 0;
#endif
    if (S_ISDIR(st.st_mode)) {
        int rc = mkdirs(n, dst);
        if (rc) return rc;
        DIR *d = opendir(src);
        if (!d) return fail(n, RB_S2ARM_NUP_IO, "cannot read %s (%s)", src, strerror(errno));
        struct dirent *e;
        while (!rc && (e = readdir(d))) {
            if (!strcmp(e->d_name, ".") || !strcmp(e->d_name, "..")) continue;
            char a[4096], b[4096];
            if (!(rc = pathf(n, a, sizeof a, "%s/%s", src, e->d_name)) && !(rc = pathf(n, b, sizeof b, "%s/%s", dst, e->d_name))) rc = copy_tree(n, a, b);
        }
        closedir(d);
        return rc;
    }
    int in = open(src, O_RDONLY), out = in < 0 ? -1 : open(dst, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    int rc = in < 0 || out < 0 ? fail(n, RB_S2ARM_NUP_IO, "cannot copy %s (%s)", src, strerror(errno)) : 0;
    while (!rc) {
        ssize_t got = read(in, n->buf, RAW_CHUNK);
        if (got < 0 && errno == EINTR) continue;
        if (got < 0) rc = fail(n, RB_S2ARM_NUP_IO, "cannot read %s (%s)", src, strerror(errno));
        if (got <= 0) break;
        for (ssize_t off = 0; !rc && off < got;) {
            ssize_t w = write(out, n->buf + off, (size_t)(got - off));
            if (w < 0 && errno == EINTR) continue;
            if (w <= 0) rc = fail(n, RB_S2ARM_NUP_IO, "cannot write %s (%s)", dst, w < 0 ? strerror(errno) : "no progress");
            else off += w;
        }
    }
    if (in >= 0) close(in);
    if (out >= 0 && close(out) && !rc) rc = fail(n, RB_S2ARM_NUP_IO, "cannot write %s (%s)", dst, strerror(errno));
    return rc;
}

// ---------- the API ----------
static int is_nup(const char *path) {
    int fd = open(path, O_RDONLY);
    if (fd < 0) return 0;
    char m[3];
    ssize_t got = read(fd, m, 3);
    close(fd);
    return got == 3 && !memcmp(m, "NUP", 3);
}

static int str_cmp(const void *a, const void *b) { return strcmp(*(char *const *)a, *(char *const *)b); }

int rb_s2arm_nup_detect(const char *path, char *nup, size_t nup_size) {
    struct stat st;
    if (!path || stat(path, &st)) return 1;
    if (S_ISREG(st.st_mode)) {
        if (!is_nup(path) || snprintf(nup, nup_size, "%s", path) >= (int)nup_size) return 1;
        return 0;
    }
    if (!S_ISDIR(st.st_mode)) return 1;
    DIR *d = opendir(path);
    if (!d) return 1;
    char **names = NULL;
    size_t count = 0, cap = 0;
    struct dirent *e;
    while ((e = readdir(d))) {
        size_t len = strlen(e->d_name);
        if (len < 4) continue;
        const char *x = e->d_name + len - 4;
        if (x[0] != '.' || (x[1] | 32) != 'n' || (x[2] | 32) != 'u' || (x[3] | 32) != 'p') continue;
        if (count == cap) {
            char **grown = realloc(names, (cap = cap ? cap * 2 : 8) * sizeof *names);
            if (!grown) break;
            names = grown;
        }
        if (!(names[count] = strdup(e->d_name))) break;
        count++;
    }
    closedir(d);
    if (names) qsort(names, count, sizeof *names, str_cmp);
    int hits = 0;
    for (size_t i = 0; i < count; i++) {
        char p[4096];
        struct stat fs;
        if (snprintf(p, sizeof p, "%s/%s", path, names[i]) < (int)sizeof p && !stat(p, &fs) && S_ISREG(fs.st_mode) && is_nup(p)) {
            if (!hits++ && snprintf(nup, nup_size, "%s", p) >= (int)nup_size) hits = 2;
        }
        free(names[i]);
    }
    free(names);
    return hits == 1 ? 0 : 1;
}

static void nup_close(nup_t *n) {
    if (n->fd >= 0) close(n->fd);
    free(n->toc);
    free(n->pkgs);
    free(n->dirs);
    free(n->files);
    free(n->buf);
    free(n->zbuf);
    if (n->zs) ZSTD_freeDStream(n->zs);
}

static int nup_open(nup_t *n, const char *path, char *error, size_t error_size) {
    memset(n, 0, sizeof *n);
    n->fd = -1;
    n->path = path;
    n->err = error;
    n->errn = error_size;
    if (error && error_size) error[0] = 0;
    if ((n->fd = open(path, O_RDONLY)) < 0) return fail(n, RB_S2ARM_NUP_IO, "%s: %s", path, strerror(errno));
    n->buf = malloc(RAW_CHUNK);
    n->zbuf = malloc(ZSTD_DStreamOutSize());
    if (!n->buf || !n->zbuf) return fail(n, RB_S2ARM_NUP_IO, "out of memory");
    return nup_read(n);
}

static int tree_add(nup_t *n, uint32_t d, uint64_t *sum) { return d == NO_DIR ? 0 : tree_bytes(n, d, sum, 0); }

// The bytes the expansion writes: the base's and the newest update's exefs and romfs, each DLC's romfs (the copy as
//   base/ of a container without a base is a clone on APFS and not counted)
static int fill_info(nup_t *n, const nup_scan *sc, rb_s2arm_nup_info *info) {
    rb_s2arm_nup_info v = {sc->app, 0, sc->update ? sc->update->version : 0, sc->ndlc, sc->base != NULL};
    const nup_pkg *parts[2] = {sc->base, sc->update};
    int rc = 0;
    for (int i = 0; !rc && i < 2; i++)
        if (parts[i] && !(rc = tree_add(n, parts[i]->exefs, &v.bytes))) rc = tree_add(n, parts[i]->romfs, &v.bytes);
    for (uint32_t i = 0; !rc && i < sc->ndlc; i++) rc = tree_add(n, sc->dlc[i]->romfs, &v.bytes);
    if (!rc && info) *info = v;
    n->total = v.bytes;
    return rc;
}

int rb_s2arm_nup_inspect(const char *nup_path, rb_s2arm_nup_info *info, char *error, size_t error_size) {
    nup_t n;
    nup_scan sc = {0};
    int rc = nup_open(&n, nup_path, error, error_size);
    if (!rc) rc = scan(&n, &sc);
    if (!rc) rc = fill_info(&n, &sc, info);
    free(sc.dlc);
    nup_close(&n);
    return rc;
}

static void key_of(const nup_t *n, char out[65]) {
    s2arm_sha256_ctx h;
    uint8_t d[32];
    s2arm_sha256_init(&h);
    s2arm_sha256_update(&h, n->toc_sha, 32);
    s2arm_sha256_update(&h, NUP_PORT_TAG, strlen(NUP_PORT_TAG));
    s2arm_sha256_final(&h, d);
    s2arm_sha256_hex(d, out);
}

int rb_s2arm_nup_expand(const rb_s2arm_nup_request *request, rb_s2arm_nup_info *info, char *error, size_t error_size) {
    if (error && error_size) error[0] = 0;
    if (!request || !request->nup_path || !request->output_dir || !request->output_dir[0]) {
        if (error && error_size) snprintf(error, error_size, "no NUP or no output folder");
        return RB_S2ARM_NUP_INVALID;
    }
    char src[4096];
    if (rb_s2arm_nup_detect(request->nup_path, src, sizeof src)) {
        if (error && error_size) snprintf(error, error_size, "%s is not a NUP, or the folder holds none or more than one .nup", request->nup_path);
        return RB_S2ARM_NUP_INVALID;
    }
    nup_t n;
    nup_scan sc = {0};
    int rc = nup_open(&n, src, error, error_size);
    n.rq = request;
    if (!rc) rc = scan(&n, &sc);
    if (!rc) rc = fill_info(&n, &sc, info);
    char key[65] = "", kf[4096] = "", tmp[4096] = "", line[80];
    const char *out = request->output_dir;
    if (!rc && !(rc = pathf(&n, kf, sizeof kf, "%s/.ns2_nup_key", out))) rc = pathf(&n, tmp, sizeof tmp, "%s.tmp", out);
    if (rc) tmp[0] = 0;
    if (!rc) {
        key_of(&n, key);
        FILE *f = fopen(kf, "r");
        if (f) {
            int same = fgets(line, sizeof line, f) && !strncmp(line, key, 64) && (line[64] == '\n' || !line[64]);
            fclose(f);
            if (same) {
                say(&n, "NUP unchanged (key %.16s): %s reused", key, out);
                free(sc.dlc);
                nup_close(&n);
                return RB_S2ARM_NUP_OK;
            }
        }
        say(&n, "NUP %s: program id %016llX, base %s, newest update %u, %u DLC", src, (unsigned long long)sc.app, sc.base ? "yes" : "no",
            sc.update ? sc.update->version : 0, sc.ndlc);
        if (!sc.base) say(&n, "no base in the container: the newest update is written as base/ (the container cannot prove the update is whole)");
        if (rm_tree(tmp)) rc = fail(&n, RB_S2ARM_NUP_IO, "cannot clear %s", tmp);
    }
    uint64_t files = 0;
    const nup_pkg *parts[2] = {sc.base, sc.update};
    for (int i = 0; !rc && i < 2; i++) {
        const nup_pkg *k = parts[i];
        if (!k) continue;
        char rel[4096], p[4096];
        if ((rc = i == 0 ? pathf(&n, rel, sizeof rel, "%s/base", tmp) : pathf(&n, rel, sizeof rel, "%s/updates/%u", tmp, k->version))) break;
        if (k->exefs == NO_DIR || child_file(&n, k->exefs, "main") < 0 || child_file(&n, k->exefs, "main.npdm") < 0) {
            rc = fail(&n, RB_S2ARM_NUP_INVALID, "%s v%u: no exefs/main and exefs/main.npdm", k->kind == K_BASE ? "base" : "update", k->version);
            break;
        }
        if (!(rc = pathf(&n, p, sizeof p, "%s/exefs", rel))) rc = write_tree(&n, k->exefs, p, &files, 0);
        if (!rc && k->romfs != NO_DIR && !(rc = pathf(&n, p, sizeof p, "%s/romfs", rel))) rc = write_tree(&n, k->romfs, p, &files, 0);
        int wrote = 0;
        if (!rc) rc = write_control(&n, k, sc.base, rel, &wrote);
        if (!rc && wrote) say(&n, "   %s: carries its control data (control.nacp and icon), kept", i == 0 ? "base" : "update");
    }
    if (!rc && !sc.base && sc.update) {   // no base: the newest update as the whole game, written as base/ too
        static const char *const part[2] = {"exefs", "romfs"};
        for (int i = 0; !rc && i < 2; i++) {
            char a[4096], b[4096], parent[4096];
            if ((rc = pathf(&n, a, sizeof a, "%s/updates/%u/%s", tmp, sc.update->version, part[i])) || (rc = pathf(&n, b, sizeof b, "%s/base/%s", tmp, part[i])) ||
                (rc = pathf(&n, parent, sizeof parent, "%s/base", tmp)))
                break;
            struct stat st;
            if (stat(a, &st) || !S_ISDIR(st.st_mode)) continue;
            if (!(rc = mkdirs(&n, parent))) rc = copy_tree(&n, a, b);
        }
    }
    for (uint32_t i = 0; !rc && i < sc.ndlc; i++) {
        char p[4096];
        if (!(rc = pathf(&n, p, sizeof p, "%s/dlc/%016llX/0/romfs", tmp, (unsigned long long)sc.dlc[i]->title_id))) rc = write_tree(&n, sc.dlc[i]->romfs, p, &files, 0);
    }
    if (!rc) {
        char p[4096], body[66];
        memcpy(body, key, 64);
        body[64] = '\n';
        body[65] = 0;
        if (!(rc = pathf(&n, p, sizeof p, "%s/.ns2_nup_key", tmp)) && !(rc = mkdirs(&n, tmp))) rc = write_bytes(&n, p, (const uint8_t *)body, 65);
    }
    if (!rc && rm_tree(out)) rc = fail(&n, RB_S2ARM_NUP_IO, "cannot replace %s", out);
    if (!rc && rename(tmp, out)) rc = fail(&n, RB_S2ARM_NUP_IO, "cannot rename %s (%s)", tmp, strerror(errno));
    if (!rc) say(&n, "expanded: %llu files, %.2f GB -> %s", (unsigned long long)files, n.done / 1073741824.0, out);
    else if (tmp[0]) rm_tree(tmp);   // deliberate difference: the original leaves <out>.tmp behind on failure
    free(sc.dlc);
    nup_close(&n);
    return rc;
}
