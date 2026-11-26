"""Check the sensitivity of the old and extended counter oracles and report workload coverage."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

p=argparse.ArgumentParser()
p.add_argument('engine',type=Path)
p.add_argument('evidence',type=Path)
p.add_argument('prepared',type=Path)
a=p.parse_args()
sys.path.insert(0,str(a.evidence.resolve()))
from compare_ubolen import extract
opts=['clang','-O2','-fsanitize=address,undefined','-fno-sanitize-recover=all']
libs=['-lobjc']
if sys.platform=='darwin':
    libs+=['-framework','Foundation']
else:
    opts+=['-I'+subprocess.check_output(['gcc','-print-file-name=include'],text=True).strip()]
with TemporaryDirectory() as t:
    t=Path(t)
    (t/'nvn_refl.h').write_text(extract(a.engine,t,'baseline'))
    extract(a.engine,t,'candidate')
    original=(t/'candidate.inc').read_text()
    for name,bench in [('extended',a.prepared/'bench.m'),('original',a.evidence/'bench.m')]:
        code=bench.read_text().replace('    return sum + rb_bounds_hits + rb_bounds_misses;','''    if(verify && !candidate_on) printf("coverage mode %d hits %llu misses %llu\\n",mode, (unsigned long long)rb_bounds_hits,(unsigned long long)rb_bounds_misses);
    return sum + rb_bounds_hits + rb_bounds_misses;''')
        (t/'bench.m').write_text(code)
        for swap in [False,True]:
            (t/'candidate.inc').write_text(original.replace('rb_bounds_hits','rb_bounds_TMP').replace('rb_bounds_misses','rb_bounds_hits').replace('rb_bounds_TMP','rb_bounds_misses') if swap else original)
            subprocess.run([*opts,'bench.m',*libs,'-o','guard'],cwd=t,check=True)
            result=subprocess.run(['./guard','verify'],cwd=t,capture_output=True,text=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})
            expected_failure=bool(name=='extended' and swap)
            assert (result.returncode!=0)==expected_failure, result
            if expected_failure:
                assert 'reference_hits[i] == rb_bounds_hits' in result.stderr,result
            print(f"{name}, swap={swap}, status={result.returncode}, expected={'failure' if expected_failure else 'success'}")
            if name=='extended' and not swap: print('\n'.join(line for line in result.stdout.splitlines() if line.startswith('coverage')))
