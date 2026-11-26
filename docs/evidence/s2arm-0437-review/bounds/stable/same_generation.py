"""Exercise the ordinary arena block rollover, which leaves the segment generation unchanged."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile

parser=argparse.ArgumentParser()
for name in ['engine','evidence','out']:parser.add_argument(name,type=Path)
a=parser.parse_args()
sys.path.insert(0,str(a.evidence.resolve()))
from compare_ubolen import extract
with tempfile.TemporaryDirectory() as raw:
    work=Path(raw)
    (work/'nvn_refl.h').write_text(extract(a.engine,work,'baseline'))
    extract(a.out/'candidate',work,'candidate')
    local=(a.out/'bench.m').read_text().replace('    uint64_t sum = 0;', '    uint64_t sum = 0, previous_block_hits = 0;').replace('        uint64_t addr = candidate_on','''        size_t step = i%64;
        if (!step) {
            ++g_arena_gen;
            g_cur_arena=&arenas[0];
            for(int j=0;j<2;++j){
                arenas[j].used=0;
                memset(arenas[j].cpu,0xeb,arena_bytes);
            }
        }
        if (step==8) g_cur_arena=&arenas[1]; // New current block; the old one is retained in the segment.
        caps[0]=step>=20 && stage==0 ? 31 : 4096;
        bounds=caps;
        uint64_t before=rb_bounds_hits;
        uint64_t addr = candidate_on''').replace('        sum += addr;', '''        sum += addr;
        const Arena *from=&arenas[addr>=arenas[1].gpu];
        if(before!=rb_bounds_hits && from!=g_cur_arena)++previous_block_hits;''').replace('    return sum + rb_bounds_hits + rb_bounds_misses;', '''    assert(previous_block_hits>0);
    printf("which=%d hits=%llu misses=%llu hits_in_previous_arena=%llu\\n",candidate_on,(unsigned long long)rb_bounds_hits,(unsigned long long)rb_bounds_misses,(unsigned long long)previous_block_hits);
    return sum + rb_bounds_hits + rb_bounds_misses;''').replace('for (int mode = 0; mode < 8; mode++)', 'for (int mode = 8; mode == 8; mode++)')
    (work/'check.m').write_text(local)
    opts=['clang','-O2','-fsanitize=address,undefined','-fno-sanitize-recover=all']
    libs=['-lobjc']
    if sys.platform=='darwin': libs+=['-framework','Foundation']
    else:opts+=['-I'+subprocess.check_output(['gcc','-print-file-name=include'],text=True).strip()]
    subprocess.run([*opts,'check.m',*libs,'-o','check'],cwd=work,check=True)
    subprocess.run(['./check','verify'],cwd=work,check=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})
