#!/usr/bin/env python3
"""The on-device preparation's speed fixes stay in place (source contract).

Mario Kart World on IPA 731 (S2Arm journal and app.log): 427 s in all. Unpack 119 s, code 60 s (two RomFS
walks of 29 s each), caps 29 s (a third walk), pack 204 s (SHA-256 of the whole 22 GB RomFS, one thread,
portable C), plus about 14 s deleting the previous root before the unpack. The RomFS view has about
205 000 entries. The fixes keep every output byte for byte; CI compares them with S2Arm's tools
(tools/s2arm_prototype/run_*_test.py in s2arm-prepare.yml, on Linux and macOS). This test guards the
fixes themselves:
  - SHA-256 from CommonCrypto on Apple systems (the CPU's SHA-256 instructions);
  - the resource pack hashes the linked files with up to four threads, one buffer per thread, progress
    from the calling thread only, and the earliest file's failure reported, as with one thread;
  - os.makedirs tries the path itself first: no mkdir for every component from / before each link;
  - the in-place view remembers the directory of the previous link;
  - the walks read the entry type from readdir and stat only links and unknown types;
  - the caps engine rule does not walk the RomFS when main names neither Unity nor Unreal.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREPARE = ROOT / 'native/s2arm/prepare'
failures = []
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        failures.append(message)


def read(name):
    return (PREPARE / name).read_text(encoding='utf-8')


def body(text, start):
    """The function that starts at `start`, up to its closing brace in column 0; '' when it is not there."""
    i = text.find(start)
    j = text.find('\n}\n', i) if i >= 0 else -1
    return text[i:j + 2] if j >= 0 else ''


def ordered(text, *parts):
    """Every part is in text, each after the previous one."""
    at = -1
    for part in parts:
        at = text.find(part, at + 1)
        if at < 0:
            return False
    return True


sha_h, sha_c = read('s2arm_sha256.h'), read('s2arm_sha256.c')
check('#include <CommonCrypto/CommonDigest.h>' in sha_h and 'CC_SHA256_CTX cc;' in sha_h,
      'on Apple systems the SHA-256 context is CommonCrypto\'s')
apple = sha_c[sha_c.find('#if defined(__APPLE__)'):sha_c.find('#else')] if '#if defined(__APPLE__)' in sha_c else ''
check('CC_SHA256_Init(&s->cc)' in apple and 'CC_SHA256_Update(&s->cc, p, (CC_LONG)take)' in apple
      and 'CC_SHA256_Final(out, &s->cc)' in apple and '((size_t)1 << 30)' in apple,
      'SHA-256 runs on CommonCrypto on Apple systems, in slices CC_LONG can hold')
check(ordered(sha_c, '#else', 'static void block(s2arm_sha256_ctx *s, const uint8_t *p)'),
      'the portable SHA-256 stays for the other systems (the Linux CI leg)')

dirent = read('s2arm_dirent.h')
values = dict(re.findall(r'#define (DT_[A-Z]+) (\d+)', dirent))
check(values == {'DT_UNKNOWN': '0', 'DT_FIFO': '1', 'DT_CHR': '2', 'DT_DIR': '4', 'DT_BLK': '6', 'DT_REG': '8', 'DT_LNK': '10',
                 'DT_SOCK': '12'} and '#ifndef DT_UNKNOWN' in dirent,
      'the readdir types carry their Linux and Darwin values when the feature macros hide the names')
check('return e->d_type;' in dirent and 'return DT_UNKNOWN;' in dirent, 'an unknown type makes the walks stat, as before')

ns2 = read('s2arm_ns2_dump.c')
makedirs = body(ns2, 'static int makedirs(const char *path) {')
check(ordered(makedirs, 'if (!mkdir(path, 0777)) return 0;', 'int r = makedirs(parent);')
      and 'for (size_t i = 1; i <= n; i++)' not in makedirs and 'if (errno != ENOENT) return -1;' in makedirs,
      'makedirs tries the path itself first and creates a parent only when it is missing')
link = body(ns2, 'static int link_view(ctx_t *x, out_t *o, const char *src, const char *tmp, const char *area, const char *rel) {')
check('int known = o->made_dir && strlen(o->made_dir) == dn && !memcmp(o->made_dir, at, dn);' in link
      and 'if (known || !make_parent(at)) {' in link and ordered(link, 'r = symlink(target, at);', 'unlink(at);'),
      'a link into the same directory as the previous one makes no directory, and links before any unlink')
check('free(o.made_dir)' in ns2, 'the remembered directory is freed with the rest of the view')
walk = body(ns2, 'static int walk_into(map_t *m, const char *dir, const char *rel, int depth) {')
check('listdir_typed(dir, &names)' in walk and 'int kind = dir_kind(abs, names.v[i]);' in walk and 'is_dir(abs)' not in walk,
      'the export walk takes the entry types from the listing')
kind = body(ns2, 'static int dir_kind(const char *path, const char *listed_name) {')
check(ordered(kind, 'if (t == DT_DIR) return 1;', 'if (t == DT_LNK) return is_dir(path) ? 2 : 0;', 'if (t != DT_UNKNOWN) return 0;',
              'return is_link(path) ? 2 : 1;'),
      'only links and unknown types are stat()ed by the export walk')
clean = body(ns2, 'static int tree_clean(const char *dir, int depth) {')
check('listdir_typed(dir, &names)' in clean and 'if (p && !mode && !lstat(p, &st)) mode = st.st_mode & S_IFMT;' in clean,
      'the whole-folder test lstat()s only entries of unknown type')

nro = read('s2arm_nro.c')
walk_nro = body(nro, 'static int walk_nro(ctx_t *x, const char *root, const char *rel, int depth, strvec_t *found) {')
check('if (type == DT_DIR) {' in walk_nro and 'if (ends_nro_ci(name, ".nro") && stat(full, &fs) == 0)' in walk_nro
      and walk_nro.count('lstat(full, &ls)') == 1 and ordered(walk_nro, '} else if (type == DT_UNKNOWN) {', 'lstat(full, &ls)'),
      'the NRO walk stats only links named *.nro, and lstat()s only entries of unknown type')

caps = read('s2arm_caps.c')
rule = body(caps, 'static int engine_l1(const char *root) {')
check(ordered(rule, 'ok = npdm && npdm_ok(npdm);', 'if (!unity && !unreal) goto done;', 'romfs_scan(rf, 0, &pak)'),
      'the engine rule walks the RomFS only when main names Unity or Unreal')
scan = body(caps, 'static int romfs_scan(const char *dir, int depth, int *pak) {')
check('if (type == DT_UNKNOWN || (type == DT_LNK && !litter)) {' in scan and 'int lok = type == DT_UNKNOWN && lstat(p, &ls) == 0' in scan,
      'the caps walk stats only links and unknown types')

pack = read('s2arm_pack.c')
check('#define HASH_THREADS 4' in pack and '#define HASH_CHUNK ((size_t)4 << 20)' in pack, 'up to four hashing threads, 4 MiB reads')
worker = body(pack, 'static void *hash_worker(void *arg) {')
one = body(pack, 'static int hash_one(hash_pool_t *p, size_t at, uint8_t *b) {')
check('uint8_t *b = malloc(HASH_CHUNK);' in worker and 'malloc' not in one, 'one read buffer per thread, not one per file')
check(ordered(one, 'p->r->cancelled(p->r->context)', 'read(fd, b, HASH_CHUNK)'),
      'every thread polls the cancel callback between chunks')
check('if (p->inline_progress && p->r->progress)' in one, 'the threads report no progress themselves')
linked = body(pack, 'static int hash_linked(ctx_t *x, const rb_s2arm_resource_request *r, pfile_t *files, const size_t *todo, size_t count,')
check('pthread_cond_timedwait(&p.idle, &p.lock, &deadline);' in linked and 'r->progress(r->context, atomic_load(&p.done), total);' in linked
      and 'pthread_join(threads[i], NULL);' in linked and 'hash_worker(&p);' in linked,
      'the calling thread reports progress while the threads hash, joins them, and hashes alone when none starts')
fail = body(pack, 'static int pool_fail(hash_pool_t *p, size_t at, int code, const char *fmt, ...) {')
check(ordered(fail, 'pthread_mutex_lock(&p->lock);', 'if (at < atomic_load(&p->failed_at)) {', 'vsnprintf(',
              'atomic_store(&p->failed_at, at);', 'pthread_mutex_unlock(&p->lock);'),
      'the earliest file\'s failure writes the error, under the lock (as the one-thread loop reported it)')
check('if (k >= p->count || k > atomic_load(&p->failed_at) || hash_one(p, k, b)) break;' in worker
      and 'if (atomic_load(&p->failed_at) < at) {' in one,
      'a failure stops the files after it; the files before it run to their end, so the earliest failure is found')
resource = body(pack, 'int rb_s2arm_resource_pack(const rb_s2arm_resource_request *r, char *error, size_t error_size) {')
check('linked_files[nlinked++] = i;' in resource and 'code = hash_linked(&x, r, files.v, linked_files, nlinked, &done, total);' in resource
      and ordered(resource, 'code = hash_linked(', 's2arm_sha256_hex(files.v[i].sha, hex);'),
      'the linked files are hashed before index.tsv is written from their slots')
source = body(pack, 'static int walk_source(ctx_t *x, pfiles_t *out, const char *name, const char *dir, const char *rel, int depth) {')
check('if (type == DT_DIR) {' in source and 'fstatat(dfd, names.v[i], &st, 0)' in source and 'if (dfd >= 0) close(dfd);' in source
      and 'type == DT_UNKNOWN && !is_link(p)' in source,
      'the pack walk takes real directories from the listing and stats files relative to their directory')

# The library is built with these units (CI and the xcframework compile every s2arm_*.c; the CI build lists them).
prepare_yml = (ROOT / '.github/workflows/s2arm-prepare.yml').read_text(encoding='utf-8')
check('python3 -B test/s2arm_prepare_speed_test.py' in prepare_yml and 'test/s2arm_prepare_speed_test.py' in prepare_yml.split('jobs:')[0],
      's2arm-prepare.yml runs this test and is triggered by it')

for failure in failures:
    print('FAIL ' + failure)
print(json.dumps({'result': 'failed' if failures else 'passed', 'checks': checks}))
sys.exit(1 if failures else 0)
