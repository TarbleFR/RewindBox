from pathlib import Path
import argparse
import shutil
import difflib

p=argparse.ArgumentParser()
p.add_argument('engine',type=Path)
p.add_argument('evidence',type=Path)
p.add_argument('destination',type=Path)
a=p.parse_args()
root=a.destination
src=Path("graphics/nvn/gfx/nvn/nvn_mtl.m")
dst=root/'candidate'/src
dst.parent.mkdir(parents=True,exist_ok=True)
s=(a.engine/src).read_text()
shutil.copy2(a.engine/src.with_name('nvn_refl.h'),dst.parent)
oldblock=s[s.index('    // The arena generation changes at both',s.index('static uint64_t len_fill(')):s.index('        id<MTLBuffer> buffer;',s.index('static uint64_t len_fill('))]
start=s.index('    uint32_t q[NVN_REFL_MAXARG]; int n = 0;',s.index('static uint64_t len_fill('))
finish=s.index('        id<MTLBuffer> buffer;',start)
prefix='''    uint32_t q[NVN_REFL_MAXARG]; int n = 0;
    if (rb_bounds_reuse && kind == NVN_RB_UBOLEN && (unsigned)nvn_stage < 6) {
        static struct { uint64_t generation, gpu; const uint32_t *bounds; } last[6];
        const size_t length = sizeof(uint32_t) * NVN_UBOLEN_N;
        if (last[nvn_stage].generation == g_arena_gen) {
            const uint32_t *previous = last[nvn_stage].bounds;
            for (; n < NVN_UBOLEN_N; ++n) {
                uint32_t value = ubolen_vec4_cap(&S.ubo[nvn_stage][n], ubcap ? ubcap[n] : UINT64_MAX);
                if (value != previous[n]) {
                    memcpy(q, previous, (size_t)n * sizeof *q);
                    q[n++] = value;
                    goto changed_bounds;
                }
            }
            ++rb_bounds_hits;
            return last[nvn_stage].gpu;
        }
changed_bounds:
        for (; n < NVN_UBOLEN_N; ++n)
            q[n] = ubolen_vec4_cap(&S.ubo[nvn_stage][n], ubcap ? ubcap[n] : UINT64_MAX);
'''
z=s[:start]+prefix+s[finish:]
tail=z.index('    // arena_new snapshots',start)
og=s[s.index('    if (kind == NVN_RB_UBOLEN)',start):s.index('    // The arena generation changes at both',start)]
z=z[:tail]+og+z[tail:]
dst.write_text(z)
(root/'compare_ubolen.py').write_text((a.evidence/'compare_ubolen.py').read_text())
(root/'candidate.diff').write_text(''.join(difflib.unified_diff(s.splitlines(True),z.splitlines(True),fromfile='a/'+str(src),tofile='b/'+str(src))))
h=(a.evidence/'bench.m').read_text()
h=h.replace('static uint64_t reference_addr[verification_calls];','static uint64_t reference_addr[verification_calls], reference_hits[verification_calls], reference_misses[verification_calls];')
h=h.replace('uint64_t caps[NVN_UBOLEN_N];','uint64_t caps[NVN_UBOLEN_N], second[NVN_UBOLEN_N];')
h=h.replace('    shader.rf.nb = 16;','''    if (mode >= 4) {
        for (int st = 0; st < 6; ++st) for (int slot = 0; slot < NVN_UBOLEN_N; ++slot) {
            S.ubo[st][slot].addr = UINT64_C(0x108000) + slot*4096;
            S.ubo[st][slot].size = 4096;
        }
    }
    shader.rf.nb = 16;''')
h=h.replace('        if (mode != 2) {','        if (mode < 4 && mode != 2) {')
h=h.replace('} else if (i % 1023 == 0)', '} else if (mode == 2 && i % 1023 == 0)')
h=h.replace('        uint64_t addr = candidate_on', '''        if (mode == 4) {
            // Keep every binding fixed. Vary backing caps alone including crossings of a vec4.
            unsigned reg=(i/48)%14;
            uint64_t a=(uint64_t[]){64,65,63,0,15,16,65536,UINT64_MAX}[(i/6)%8];
            caps[reg]=a;
            bounds=caps;
        } else if (mode == 5) {
            // Replace size/availability as on a full state restore. Cap and address stay stable on size edits.
            unsigned reg=(i/48)%14;
            S.ubo[stage][reg].size=(uint64_t[]){4096,17,31,32,33,UINT64_MAX,UINT64_MAX-15,16}[(i/6)%8];
            S.ubo[stage][reg].addr=(i/6)%11?UINT64_C(0x108000)+reg*4096:0;
            bounds=caps;
        } else if (mode == 6) {
            // Recycle and poison an old arena, keeping the same guest and host addresses and logical length.
            if (!(i%37)) {
                g_cur_arena = g_cur_arena==&arenas[0] ? &arenas[1] : &arenas[0];
                g_cur_arena->used = 0;
                memset(g_cur_arena->cpu, 0xb9, arena_bytes);
                ++g_arena_gen;
            }
            bounds=caps;
        } else if (mode == 7) {
            // The actual UBOLEN caller always passes a nonnull array. Differently located copies are equal.
            bounds=caps;
            if ((i/6)&1) {
                memcpy(second, caps, sizeof second);
                bounds=second;
            }
            if (!(i%1023)) ++g_arena_gen;
        }
        uint64_t addr = candidate_on''')
h=h.replace('                reference_addr[i] = addr;', '                reference_hits[i] = rb_bounds_hits; reference_misses[i] = rb_bounds_misses;\n                reference_addr[i] = addr;').replace('                assert(reference_addr[i] == addr);','                assert(reference_addr[i] == addr && reference_hits[i] == rb_bounds_hits && reference_misses[i] == rb_bounds_misses);')
h=h.replace('            for (unsigned j = 0; j < 256; j++) sum', '''            if (kind == NVN_RB_UBOLEN) {
                for (unsigned slot=0; slot<NVN_UBOLEN_N; ++slot) {
                    uint64_t want = (S.ubo[stage][slot].size+15) / 16;
                    uint64_t limit=(bounds?bounds[slot]:UINT64_MAX) / 16;
                    if (!S.ubo[stage][slot].addr) want=0;
                    if (want>4096) want=4096;
                    if (want>limit) want=limit;
                    uint32_t got; memcpy(&got, bytes + 4*slot, 4);
                    assert(want == got);
                }
            }
            for (unsigned j = 0; j < 256; j++) sum''')
h=h.replace('mode < 4; mode++','mode < 8; mode++')
(root/'bench.m').write_text(h)
r=(a.evidence/'report.py').read_text().replace('"UBOLEN cache modifié")','"UBOLEN cache modifié", "cap seule", "restauration", "recyclage", "stable non nul")')
(root/'report.py').write_text(r)
