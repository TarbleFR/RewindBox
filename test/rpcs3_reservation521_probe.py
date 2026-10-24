"""Measure candidates before changing the production reservation comparison."""
import hashlib,json,platform,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
source=Path(sys.argv[1]).resolve()
assert platform.system()=='Darwin' and platform.machine()=='arm64'
text=(source/'rpcs3/Emu/Cell/SPUThread.cpp').read_text()
def function(start):
 a=text.index(start);brace=text.index('{',a);depth=1;b=brace+1
 while depth:
  depth+=int(text[b]=='{')-int(text[b]=='}');b+=1
 return text[a:b]
helper=function('static FORCE_INLINE int16x8_t cmp16_pair_accum_arm64(')
baseline=function('extern bool cmp_rdata(')
prefix='#include <arm_neon.h>\n#include <cstdint>\n#define ARCH_ARM64 1\n#define FORCE_INLINE __attribute__((always_inline)) inline\nusing v128=uint16x8_t;using spu_rdata_t=uint8_t[128];\n'
baseline=baseline.replace('extern bool cmp_rdata(', '__attribute__((always_inline)) inline bool baseline_impl(')
tail='''
#include "rpcs3_reservation521_candidates.h"
extern "C" __attribute__((noinline)) bool baseline_compare(const uint8_t* a,const uint8_t* b) {
 return baseline_impl(*reinterpret_cast<const spu_rdata_t*>(a),*reinterpret_cast<const spu_rdata_t*>(b));
}
extern "C" __attribute__((noinline)) bool xor_compare(const uint8_t* a,const uint8_t* b) {return rpcs3_reservation521::xor_tree(a,b);}
extern "C" __attribute__((noinline)) bool equality_compare(const uint8_t* a,const uint8_t* b) {return rpcs3_reservation521::equality_tree(a,b);}
'''
out=ROOT/'build/rpcs3-cell521-probe';out.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory() as directory:
 work=Path(directory);cpp=work/'functions.cpp';cpp.write_text(prefix+helper+'\n'+baseline+tail)
 common=['xcrun','clang++','-std=c++20','-O3','-march=armv8.4-a','-fno-lto','-Wall','-Wextra','-Werror','-I',str(ROOT/'test/native')]
 subprocess.run([*common,'-c',str(cpp),'-o',str(out/'functions.o')],check=True)
 subprocess.run([*common,str(ROOT/'test/native/rpcs3_reservation521_bench.cpp'),str(out/'functions.o'),'-o',str(work/'probe')],check=True)
 subprocess.run([str(work/'probe'),str(out/'measurements.json')],check=True)
 with (out/'disassembly.txt').open('w') as f:subprocess.run(['xcrun','otool','-tvV',str(out/'functions.o')],stdout=f,check=True)
record=json.loads((out/'measurements.json').read_text())
record.update(source=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
 baselineProductionSHA256=hashlib.sha256((helper+'\n'+function('extern bool cmp_rdata(')).encode()).hexdigest(),
 hardware=subprocess.check_output(['sysctl','-n','machdep.cpu.brand_string'],text=True).strip(),
 compiler=subprocess.check_output(['xcrun','clang++','--version'],text=True).splitlines()[0],
 method='14 rotated-order rounds; discard first 2; median/min/max of 12 samples, 2M calls each; hot and 1MiB paired working sets',
 functionCallOverheadIncluded=True,productionChanged=False,
 inputs={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in [
 'test/rpcs3_reservation521_probe.py','test/native/rpcs3_reservation521_bench.cpp',
 'test/native/rpcs3_reservation521_candidates.h','build-utils/rpcs3/canonical-source.json']})
(out/'measurements.json').write_text(json.dumps(record,indent=2)+'\n')
for r in record['results']:print(r)
