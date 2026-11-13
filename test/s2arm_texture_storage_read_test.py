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
among the live pools, and uploads from the copy on the CPU. The layout and its size are not changed; a texture no
tracked pool holds whole is compared by its bytes instead of being uploaded again at every use.

The two functions that ask and copy are compiled from the patch and run here over real pages (protected, unmapped,
unaligned ranges, storage ending inside an unreadable page). Their two Mach calls are stood in for by this host's own
means (see the harness). The engine itself is compiled by s2arm-engine.yml; whether the game goes on past frame 308,
and which of the two cases the red line names, is only known from a device log.

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
check(ordered(copy, 'vm_read_overwrite(mach_task_self(), (vm_address_t)a, (vm_size_t)n, (vm_address_t)dst, &got) == KERN_SUCCESS && got == n) return 0;',
              'pg - ((a + o) & (pg - 1))', 'vm_read_overwrite(mach_task_self(), (vm_address_t)(a + o), (vm_size_t)k, (vm_address_t)(dst + o), &got) != KERN_SUCCESS || got != k',
              'memset(dst + o, 0, k);', 'bad += k;'),
      'copy: through Mach (an error, not a fault), host page by host page; a page that cannot be read is zeros and counted')

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
check(ordered(note, 'if (k > 8 && (k & (k - 1))) return;', 'rb_pool_text(t, where, sizeof where);', 'MLOG("【红】 RewindBox: texture ser=%llu', 'cannot be read (the first at +%#llx)', 'they are read as 0; %s'),
      'the red line names the texture, how much of its storage could not be read and from where, and where the storage lies (first 8, then at powers of two)')
case = function(added, 'static int rb_pool_case(const tex_t *t, uint64_t *plo, uint64_t *psz, uint64_t *over) {')
check(ordered(case, 'pthread_mutex_lock(&g_mu);', 'pool_find((uint64_t)(uintptr_t)t->mem, t->L.size ? t->L.size : 1)', 'pool_find((uint64_t)(uintptr_t)t->mem, 1)',
              '(uintptr_t)t->mem + t->L.size - g_pools[i].hi', 'pthread_mutex_unlock(&g_mu);') and 't->pool' not in case,
      "the three cases come from the host's own pool table (whole in a pool / past the end of its pool / no live pool), never from the game's pool object")
check(all(text in added for text in ('its storage is inside the live memory pool', 'bytes past the end of the memory pool', 'no live memory pool holds its first byte')),
      'the line says which case it is: the next device log tells a finalized pool from a size that runs past the pool')

# ---- the other reads of a texture's storage ----
check(ordered(patch, ' static int mem_any_touched(const uint8_t *p, uint64_t n) {', '+    if (n && !rb_span_readable((uintptr_t)p, n)) {', 'rb_span_copy(c, (uintptr_t)p, n, NULL); int any = mem_any(c, n); free(c); return any; }'),
      'the zero check of a new texture (tex_cpu_content, tex_init_fill) judges storage it cannot wholly read on a copy')
check(ordered(patch, '-        memcpy(masked, t->mem, t->L.size);', '+        if (rb_span_readable((uintptr_t)t->mem, t->L.size)) memcpy(masked, t->mem, t->L.size); else rb_span_copy(masked, (uintptr_t)t->mem, t->L.size, NULL);',
              '+    if (!masked && (masked = rb_pkg_bytes(t, 0))) src = masked;'),
      "the initial fill's own copy and checks read the storage the same way")
same = function(added, 'static int rb_pkg_same(const tex_t *t, const uint64_t *ph, uint32_t nph) {')
check(ordered(same, 'if (!ph || n != nph) return 0;', 'rb_pkg_bytes(t, 0)', 'span_hash(rd + (lo - t->mem), m) == ph[k]', 'free(c);'),
      'the bytes of a texture are compared page for page with the hashes of its last upload, read the safe way')
check(ordered(patch, '+            if (!clean && !pk->sparse && pk->ph && !nvn_dirty_tracked(t->mem, t->L.size) && rb_pkg_same(t, pk->ph, pk->nph)) {', '+                clean = 1;',
              ' if (clean && atomic_load_explicit(&g_up_lost_n, memory_order_relaxed) && up_lost_take(pk->tex)) { clean = 0;'),
      'a texture no tracked pool holds whole is uploaded again only when its bytes changed; an upload that was lost is still made again')
check(ordered(patch, ' static void gpw_mark(const tex_t *t', '+    int rb_ok = -1;', '+        if (rb_ok < 0) rb_ok = rb_span_readable((uintptr_t)t->mem, t->L.size);', '+        if (!rb_ok) break;',
              '         tex_rect_gobs(t, level, k, x, y, w, h, gpw_add, (void *)t->mem);'),
      'the GPU-write ledger hashes the guest bytes it marks: nothing is marked in storage that cannot all be read (as for a virtual pool)')
check(ordered(patch, ' static int gpw_stale(const uint8_t *mem, uint64_t size', 'rb_ok = -1;', '+        if (rb_ok < 0) rb_ok = rb_span_readable((uintptr_t)mem, size);', '+        if (!rb_ok) break;',
              '         if (span_hash((const uint8_t *)(uintptr_t)(g << 9), 512) != b->h[i])'),
      'and it compares a marked GOB only in storage that can all be read; the question is asked once, at the first marked GOB')
check(not re.search(r'^-.*(RED_ONCE\(|MDIE\(|【红】)', patch.replace('RED_ONCE(40, "swizzled texture storage is not in a memory pool; falling back to the CPU");', ''), re.M),
      'no report or stop of the engine is removed (the one changed line still reports a texture outside every pool)')
check(added.count('RewindBox (patch 0016)') >= 9, 'every change is marked RewindBox (patch 0016)')

# ---- the two functions, run over real pages ----
check(HARNESS.is_file(), 'test/s2arm_texture_storage_read_harness.c exists')
compiler = shutil.which('cc') or shutil.which('clang') or shutil.which('gcc')
check(bool(compiler), 'a C compiler is available (cc, clang or gcc)')
ran = ''
if compiler and readable and copy and HARNESS.is_file():
    with tempfile.TemporaryDirectory() as work:
        (Path(work) / 'rb_span.inc').write_text(readable + copy, encoding='utf-8')
        binary = Path(work) / 'span'
        build = subprocess.run([compiler, '-std=c11', '-D_GNU_SOURCE', '-Wall', '-Wextra', '-Werror', '-O1', '-I', work, '-o', str(binary), str(HARNESS)], capture_output=True, text=True)
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
