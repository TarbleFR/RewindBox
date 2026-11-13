#!/usr/bin/env python3
"""Patch 0016: a texture's storage is read where the game holds readable memory, and only there (plain python3 + cc).

Mario Kart World on IPA 734 (engine log of iPhone17,2, 13 Nov 16:15, the first run that drew: 308 frames, 60 per
second up to frame 300). At frame 308, the first submission of the 3D scene, the process stopped with SIGBUS:

    CRASH 信号 10 地址 0x78e7afc000 pc span_hash+0x3c lr pkg_upload+0x2f8
    #0 tex_mtl #1 tex_by_id #2 encode_args_ ... #10 h_nvnQueueSubmitCommands

The registers, read against the disassembly of the engine that was in that IPA (pkg_upload+0x2b4..0x2f8): the page
hash of a texture's first upload was at host page 87 of 89 (x24 = 0x57, x21 = 0x59), reading a whole page (x1 = 0x4000)
at its first byte. Pages 0-86 were readable, that one was not. The address is in the game's alias region
(0x78c01fc000 + 633 MiB), where the game maps and unmaps physical memory (svc 0x2c x410, 0x2d x430 by then: 458 MB
mapped in a span of 647 MB); S2Arm makes an unmapped host page PROT_NONE.

The host read a texture's storage as the layout's whole size from the texture's address, without asking whether the
game holds memory there: a texture whose pool was finalized and unmapped while its ID stays registered, or whose
computed size runs past its pool, is read into memory that is not there. S2Arm has the same stop open as its #819
(an iPad after 20-40 minutes, the same function), and guards only the pool-table walk (tex_storage_live, its #934),
not a texture a draw binds (tex_by_id).

Patch 0016: before the host reads a texture's storage it asks Mach whether every page is readable (no memory is
touched). All readable, the usual case: nothing changes. Otherwise it reads a private copy in which what cannot be read
is zeros (as a sparse pool's unmapped pages already are), says so in red with the texture and where its storage lies
among the live pools, and uploads from the copy on the CPU. The layout and its size are not changed. Such a texture is
then compared by its bytes at each use instead of being uploaded again each time; the GPU-write ledger marks none of
its blocks and takes it for GPU content; the partial re-upload and ReadTexels read the same copy; a write-tracked
texture's written pages are hashed in place only when its storage can all be read (it is uploaded whole otherwise).
Not covered: the development diagnostics that read a storage whole (DM_NVN_DIRTYCHECK, DM_NVN_TEXINFO, DM_NVN_ZBLOCK),
and a page the game unmaps between the question and the read of storage that was all readable.

The two functions that ask and copy are compiled from the patch and run here over real pages (protected, unmapped,
unaligned ranges, storage ending inside an unreadable page). On macOS they call Mach itself; elsewhere their two Mach
calls are stood in for by the host's own means (see the harness). The engine itself is compiled by s2arm-engine.yml;
whether the game goes on past frame 308, and which case the red line names, is only known from a device log.

    python3 -B test/s2arm_texture_storage_read_test.py
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATCHES = ROOT / 'build-utils/s2arm/engine/patches'
PATCH = PATCHES / '0016-guest-texture-storage-read-where-the-game-holds-memory.patch'
HARNESS = ROOT / 'test/s2arm_texture_storage_read_harness.c'
failures, checks = [], 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        failures.append(message)


def ordered(text, *parts):
    at = -1
    for part in parts:
        at = text.find(part, at + 1)
        if at < 0:
            return False
    return True


def function(text, head):
    """The definition that starts with `head`, up to its closing brace in column 0."""
    start = text.find(head)
    if start < 0:
        return ''
    end = text.find('\n}\n', start)
    return text[start:end + 3] if end >= 0 else ''


patch = PATCH.read_text(encoding='utf-8') if PATCH.is_file() else ''
check(bool(patch), 'patch 0016 exists')
check(re.findall(r'^diff --git a/(\S+) b/', patch, re.M) == ['graphics/nvn/gfx/nvn/nvn_mtl.m'], 'patch 0016 touches nvn_mtl.m only')
added = '\n'.join(line[1:] for line in patch.splitlines() if line.startswith('+') and not line.startswith('+++')) + '\n'
removed = '\n'.join(line[1:] for line in patch.splitlines() if line.startswith('-') and not line.startswith('---')) + '\n'

# ---- the two functions, as the patch has them ----
readable, copy = function(added, 'static int rb_span_readable(uintptr_t a, uint64_t n) {'), function(added, 'static uint64_t rb_span_copy(uint8_t *dst, uintptr_t a, uint64_t n, uint64_t *first) {')
check(bool(readable) and bool(copy), 'rb_span_readable and rb_span_copy are whole functions of the patch')
check(ordered(readable, 'if (!n) return 1;', 's2a_far_g2h((uint64_t)a) || s2a_far_g2h((uint64_t)a + n - 1)', 'vm_region_64(mach_task_self()', 'return 0;',
              'if (ra > r || !rs || !(vi.protection & VM_PROT_READ)) return 0;', 'r = ra + rs;', 'return 1;'),
      'readable: far alias storage first (no host pages of its own), then every Mach region over the range must exist, follow the last one and allow reads')
check('memcpy' not in readable and '*(const' not in readable and '[' not in readable.split('{', 1)[1].replace('s2a_far_g2h', ''),
      'asking whether storage is readable dereferences nothing')
check(ordered(copy, 'pg - ((a + o) & (pg - 1))', 'vm_read_overwrite(mach_task_self(), (vm_address_t)(a + o), (vm_size_t)k, (vm_address_t)(dst + o), &got) != KERN_SUCCESS || got != k',
              'memset(dst + o, 0, k);', 'bad += k;'),
      'copy: through Mach (an error, not a fault), host page by host page; a page that cannot be read is zeros and counted')
check(copy.count('vm_read_overwrite(') == 1 and '(vm_size_t)n,' not in copy,
      'the copy is not tried in one piece first: its callers have found that the range cannot all be read, and that try copied the readable part twice')

# ---- where the storage is read ----
upload = added[added.find('    uint8_t *rb = NULL;'):]
check(ordered(patch, ' static id<MTLTexture> pkg_upload_(const tex_t *t, uint64_t *stamp', '+    uint8_t *rb = NULL;', 'nvn_dirty_protect(t->mem, t->L.size);', '*stamp = nvn_dirty_now();',
              '+    if (!sparse) rb = rb_pkg_bytes(t, 1);', '+    if (stamp && ph && !sparse) {', 'h[k] = span_hash(rd + (lo - t->mem), m);'),
      'upload: protection, stamp, then the readable bytes, then the page hashes from them (the order the write tracking needs is kept)')
check('-            if (h) { for (uint32_t k = 0; k < n; k++) { const uint8_t *lo; size_t m; page_span(t, k, &lo, &m); h[k] = span_hash(lo, m); }' in patch,
      'the page hash no longer reads the storage address unasked (the line that stopped the process)')
check(all(piece in added for piece in ('if ((!unp || gdec) && !sparse && !rb && g_nvn_deswz_gpu) { up_begin(); upsrc = up_tex_src(',
                                       'int use_gpu = (!unp || gdec) && !sparse && !rb && g_nvn_deswz_gpu && !lin &&')),
      'storage that cannot all be read never goes to the GPU deswizzle (it would read the pool pages themselves)')
check(ordered(added, 'if (rb) src = rb;', 'free(part); free(rb);'), 'the CPU upload reads the copy, which is freed with the upload')
check(ordered(function(added, 'static uint8_t *rb_pkg_bytes(const tex_t *t, int note) {'), 'rb_span_readable((uintptr_t)t->mem, t->L.size)) return NULL;', 'malloc(t->L.size)',
              'rb_span_copy(c, (uintptr_t)t->mem, t->L.size, &first)', 'rb_pkg_note(t, bad, first)'),
      'readable storage is not copied (NULL: the usual case is as before); otherwise a copy of the whole layout size, and the red line')
check('t->L.size =' not in added and 'L.size -=' not in added and 'nvn_tex_layout' not in added, "the texture's layout and its size are not changed")
note = function(added, 'static void rb_pkg_note(const tex_t *t, uint64_t bad, uint64_t first) {')
check(ordered(note, 'int c = rb_pool_text(t, where, sizeof where);', 'if (g_rb_case_n[c]++ >= 8) return;', 'MLOG("【红】 RewindBox: texture storage that cannot all be read, %s: texture ser=%llu',
              'are read as 0 (the first at +%#llx)', '%llu such uploads and %llu KB so far'),
      "the red line says where the storage lies, then names the texture and how much of it could not be read and from where; the first 8 of each case")
logcap = 'the log layer keeps'
check(logcap in note and note.find('RewindBox: texture storage that cannot all be read, %s:') < note.find('texture ser=%llu'),
      "the case's words come before any figure of the texture: the log layer keeps 8 red lines per text with its digits erased, so each case keeps its own 8")
case = function(added, 'static int rb_pool_case(const tex_t *t, uint64_t *plo, uint64_t *psz, uint64_t *over) {')
check(ordered(case, 'pthread_mutex_lock(&g_mu);', 'pool_find((uint64_t)(uintptr_t)t->mem, t->L.size ? t->L.size : 1)', 'pool_find((uint64_t)(uintptr_t)t->mem, 1)',
              '(uintptr_t)t->mem + t->L.size - g_pools[i].hi', 'pthread_mutex_unlock(&g_mu);') and 't->pool' not in case,
      "the three cases come from the host's own pool table (whole in a pool / past the end of its pool / no live pool), never from the game's pool object")
check(all(text in added for text in ('"inside the live memory pool %#llx+%#llx"', '"running %llu bytes past the end of the memory pool %#llx+%#llx that holds its first byte"',
                                     '"with no live memory pool at its first byte (the pool it was made in was finalized)"')),
      'the line says which case it is: the next device log tells a finalized pool from a size that runs past the pool')

# ---- the other reads of a texture's storage ----
check(ordered(patch, ' static int mem_any_touched(const uint8_t *p, uint64_t n) {', '+    if (n && !rb_span_readable((uintptr_t)p, n)) {', 'rb_span_copy(c, (uintptr_t)p, n, NULL); int any = mem_any(c, n); free(c); return any; }'),
      'the zero check of a new texture (tex_cpu_content, tex_init_fill) judges storage it cannot wholly read on a copy')
check(ordered(patch, '-        memcpy(masked, t->mem, t->L.size);', '+        if (rb_span_readable((uintptr_t)t->mem, t->L.size)) memcpy(masked, t->mem, t->L.size); else rb_span_copy(masked, (uintptr_t)t->mem, t->L.size, NULL);',
              '+    if (!masked && (masked = rb_pkg_bytes(t, 0))) src = masked;'),
      "the initial fill's own copy and checks read the storage the same way")
same = function(added, 'static int rb_pkg_same(const tex_t *t, const uint64_t *ph, uint32_t nph) {')
check(ordered(same, 'if (!ph || n != nph) return 0;', 'uint8_t *c = rb_pkg_bytes(t, 0); int same = c != NULL;', 'g_rb_cmp_n++; g_rb_cmp_bytes += t->L.size;',
              'span_hash(c + (lo - t->mem), m) == ph[k]', 'free(c);', 'return same;') and 't->mem, m)' not in same,
      'only storage that cannot all be read is compared (readable storage: 0, it keeps what it had before); page for page with the hashes of its last upload, on the copy')
check(ordered(patch, '+            if (!clean && !pk->sparse && pk->ph && !nvn_dirty_tracked(t->mem, t->L.size) && rb_pkg_same(t, pk->ph, pk->nph)) {', '+                clean = 1;',
              '+                uint64_t k = ++g_rb_same_n;', '+                if (!(k & (k - 1))) {', '%llu comparisons, %llu MB copied for them',
              ' if (clean && atomic_load_explicit(&g_up_lost_n, memory_order_relaxed) && up_lost_take(pk->tex)) { clean = 0;'),
      'such a texture is uploaded again only when its bytes changed, and what the comparisons cost is in the log at 1, 2, 4, 8...; an upload that was lost is still made again')
# a write-tracked texture: its written pages are hashed in place at each use, after a protection that gives read access only to the pages it takes
check(ordered(patch, ' int changed = 0, gpu = pk->pgpu != NULL;',
              '-                    for (long k = 0; k < np && ncap >= pk->nph; k++) if (bits[k >> 6] >> (k & 63) & 1) {',
              '+                    int rb_ok = rb_span_readable((uintptr_t)t->mem, t->L.size);',
              '+                    for (long k = 0; rb_ok && k < np && ncap >= pk->nph; k++) if (bits[k >> 6] >> (k & 63) & 1) {',
              ' page_span(t, (size_t)k, &lo, &m); nh[k] = span_hash(lo, m);',
              '-                    if (!changed) { pk->stamp = st; pk->seen = nvn_dirty_now(); clean = 1; g_pkg_same++; }',
              '+                    if (rb_ok && !changed) { pk->stamp = st; pk->seen = nvn_dirty_now(); clean = 1; g_pkg_same++; }',
              '+                    else if (rb_ok && gpu && pk->tex.width >= t->d.width'),
      "a tracked texture's written pages are hashed in place only when its storage can all be read; otherwise it stays not clean and is uploaded whole, from a copy")
check(ordered(patch, ' static void gpw_mark(const tex_t *t', '+    int rb_ok = -1;', '+        if (rb_ok < 0) rb_ok = rb_span_readable((uintptr_t)t->mem, t->L.size);',
              '+        if (!rb_ok) { gpw_own_note(t, 0); break; }', '         tex_rect_gobs(t, level, k, x, y, w, h, gpw_add, (void *)t->mem);'),
      "the GPU-write ledger hashes the guest bytes it marks: in storage that cannot all be read no block is marked and the texture counts as GPU content for good, as a virtual pool's")
check(ordered(patch, ' static int gpw_stale(const uint8_t *mem, uint64_t size', 'rb_ok = -1;',
              '-        if (span_hash((const uint8_t *)(uintptr_t)(g << 9), 512) != b->h[i]) { gpw_unmark(g); continue; }',
              '+        if (rb_ok < 0) rb_ok = rb_span_readable((uintptr_t)mem, size);',
              '+        if (rb_ok && span_hash((const uint8_t *)(uintptr_t)(g << 9), 512) != b->h[i]) { gpw_unmark(g); continue; }')
      and '+        if (!rb_ok) break;' not in patch,
      'a marked block of a range that cannot all be read stays stale, unread (its readers take "no stale run" for "guest memory is current"); the question is asked once, at the first marked block')
rects = patch[patch.find(' static int pkg_upload_rects(const tex_t *t, id<MTLTexture> mt, const rect_list *L) {'):]
check(ordered(rects, '+    uint8_t *rb = rb_pkg_bytes(t, 1);', '+        if (!stg) { free(rb); return 1; }',
              '+        if (nvn_deswizzle(&t->d, q->level, q->layer, rb ? rb : t->mem, stg.contents, pitch)) { RED_ONCE(98, "partial re-upload: deswizzle failed format %#x target %d", t->d.format, t->d.target); free(rb); return 1; }',
              '+    free(rb);', ' static id<MTLTexture> tex_mtl_(const tex_t *ct) {'),
      'the partial re-upload reads a level from the copy when the storage cannot all be read, and frees it on every way out')
texels = patch[patch.find(' void nvn_be_read_texels(const tex_t *t'):]
check(ordered(texels, '+        uint8_t *rb = rb_pkg_bytes(t, 0);',
              '+            if ((is3d && z == 0) || !is3d) if (nvn_deswizzle(&t->d, level, layer, rb ? rb : t->mem, lin, lp)) { RED_ONCE(32, "ReadTexels deswizzle failed"); free(lin); free(rb); return; }',
              '+        free(lin); free(rb);'),
      "ReadTexels of a texture the CPU filled reads the same way, on the caller's thread and without touching the submit thread's counters (note 0)")
reports = re.findall(r'^-.*?((?:RED_ONCE|MDIE)\((?:\d+, )?"[^"]*")', patch, re.M)
check(len(reports) == 3 and all(report in added for report in reports) and not re.search(r'^-.*【红】', patch, re.M),
      f'no report or stop of the engine is removed: each of the {len(reports)} on a changed line is on the line that replaces it')
check(added.count('RewindBox (patch 0016)') >= 11, 'every change is marked RewindBox (patch 0016)')

# ---- the two functions, run over real pages ----
check(HARNESS.is_file(), 'test/s2arm_texture_storage_read_harness.c exists')
compiler = shutil.which('cc') or shutil.which('clang') or shutil.which('gcc')
check(bool(compiler), 'a C compiler is available (cc, clang or gcc)')
ran = ''
if compiler and readable and copy and HARNESS.is_file():
    with tempfile.TemporaryDirectory() as work:
        (Path(work) / 'rb_span.inc').write_text(readable + copy, encoding='utf-8')
        binary = Path(work) / 'span'
        build = subprocess.run([compiler, '-std=c11', '-D_GNU_SOURCE', '-D_DARWIN_C_SOURCE', '-Wall', '-Wextra', '-Werror', '-O1', '-I', work, '-o', str(binary), str(HARNESS)],
                               capture_output=True, text=True)
        check(build.returncode == 0, 'the two functions and the harness compile without a warning: ' + build.stderr[-900:])
        if build.returncode == 0:
            run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=120)
            ran = run.stdout.strip().splitlines()[-1] if run.stdout.strip() else ''
            check(run.returncode == 0 and ran.startswith('PASSED'), 'the harness passes: ' + run.stdout[-1200:] + run.stderr[-300:])

series = sorted(p.name for p in PATCHES.glob('*.patch'))
check(len(series) >= 16 and series[15] == PATCH.name, f'0016 is the 16th engine patch: {series[14:17]}')
notices = (ROOT / 'docs/s2arm-legal-notices.md').read_text(encoding='utf-8')
check(PATCH.name in notices, 'the legal notices list patch 0016')
readme = (ROOT / 'build-utils/s2arm/engine/README.md').read_text(encoding='utf-8')
check(PATCH.name in readme, 'the engine README explains patch 0016')

for failure in failures:
    print('FAIL ' + failure)
print(json.dumps({'result': 'failed' if failures else 'passed', 'checks': checks, 'harness': ran}))
sys.exit(1 if failures else 0)
