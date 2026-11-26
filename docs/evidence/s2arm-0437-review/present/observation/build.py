"""Replay engine functions using RewindBox's existing synthetic presentation fixture."""
import argparse,os,re,subprocess,tempfile
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument('rewindbox',type=Path)
p.add_argument('gpu_tree',type=Path)
p.add_argument('runtime_tree',type=Path)
p.add_argument('out',type=Path)
p.add_argument('--compile-stats',choices=("0","1"),default="0")
p.add_argument('--objects',action='store_true',help='Also emit the optimized ELF object and LLVM IR')
a=p.parse_args()
out=a.out.resolve(); out.mkdir(parents=True,exist_ok=True)
me=Path(__file__).resolve().parent
rt=a.runtime_tree/'runtime/src'
base=a.gpu_tree/'graphics/nvn/gfx/nvn'
src=(base/'nvn_present_fi.inc').read_text()
def function(s, signature):
    i=s.index(signature)
    return s[i:s.index('\n}',i)+2]
support=(a.rewindbox/'docs/evidence/s2arm-0437-review/present/probe.m').read_text().split('static int cases, known_bad;')[0]
def replace(a,b):
    global support
    if support.count(a)!=1: raise ValueError(a)
    support=support.replace(a,b)
replace('#define MLOG(...)','''#include <stdarg.h>
#include <string.h>
static char last_stats_log[1000];
static int validate_log;
static void capture_log(const char *fmt,...) __attribute__((format(printf,1,2)));
static void capture_log(const char *fmt,...) {
    if(!validate_log || strncmp(fmt,"[rb-fi-present-v1]",18)) return;
    va_list args; va_start(args,fmt);
    vsnprintf(last_stats_log,sizeof(last_stats_log),fmt,args);
    va_end(args);
}
#define MLOG capture_log''')
replace('typedef Object NSError;', '''typedef Object NSError;
@interface Object (RbErrorText)
@property(readonly) Object *description;
@property(readonly) const char *UTF8String;
@end''')
replace('@protocol CAMetalDrawable','''@protocol MTLDrawable
@property(readonly) double presentedTime;
@end
@protocol CAMetalDrawable <MTLDrawable>
- (void)addPresentedHandler:(void (^)(id<MTLDrawable>))handler;''')
replace('static BOOL checking_cpu, do_bench;','''static BOOL checking_cpu, do_bench;
static void (^presented[3])(id<MTLDrawable>);
static double shown_time[3];
static int encoding_type, fx_calls;
''')
replace('- (NSUInteger)width { return 16; }','''- (void)addPresentedHandler:(void (^)(id<MTLDrawable>))handler { assert(!presented[slot]); presented[slot]=Block_copy(handler); }
- (double)presentedTime { return shown_time[slot]; }
- (NSUInteger)width { return 16; }''')
if 'static int fi_dup(void)' in src: replace('static int fi_dup(void) {return 0;}',src[src.index('static int fi_dup(void)'):].split('\n')[0])
header=base/'rb_fi_present_stats.h'
aux=''
if header.is_file():
    (out/header.name).write_bytes(header.read_bytes())
    aux = '#if S2A_RB_COMPILE_FI_STATS == 1\n#define atomic_load_explicit __c11_atomic_load\n#define memory_order_relaxed __ATOMIC_RELAXED\n#include "rb_fi_present_stats.h"\n#endif\n'
count=src[src.index('__attribute__((weak)) void s2a_hud_mid_frame'):src.index('// 拆账用',src.index('__attribute__((weak)) void s2a_hud_mid_frame'))]
replace('static void fi_count_on(id dr,_Atomic uint64_t *count) {}', aux+count)
replace('return outcome[1]!=ENCODE_FAIL;', '''if(f==objects[1]) {
  if(a==objects[4]) encoding_type=cut_word ? 3 : 1;
  else if(d==objects[6]) encoding_type=2;
}
return outcome[1]!=ENCODE_FAIL;''')
replace('return outcome[((Fake *)cb)->slot]!=ENCODE_FAIL;', '''if(dst==objects[1]) encoding_type=4;
return outcome[((Fake *)cb)->slot]!=ENCODE_FAIL;''')
replace('static void fi_mv_encode(NvPresentFI *f,id cb,int k,int use,float sign) {}','static void fi_mv_encode(NvPresentFI *f,id cb,int k,int use,float sign) { fx_calls+=use; }')
# This counts the call guarded by use_fx above. Apple MetalFX is deliberately absent.
start=src.index('// Each slot either reads')
end=src.index('} }',src.index('static void fi_job'))+3
(out/'job.inc').write_text(src[start:end].replace('@autoreleasepool {','{'))
(out/'rule.h').write_bytes((base/'nvn_fi_rule.h').read_bytes())
m=(base/'nvn_mtl.m').read_text()
(out/'complete.inc').write_text(function(m,'static void rb_present_complete('))
(out/'hud.inc').write_text(function((rt/'ap_host.c').read_text(),'void s2a_hud_frame(void)')+'\n'+function((rt/'hud.c').read_text(),'int s2a_hud_brief('))
(out/'probe.m').write_text(support+'\n#line 1 "driver.m"\n'+(me/'driver.m').read_text())
include=subprocess.check_output(['gcc','-print-file-name=include'],text=True).strip()
prefix=Path(os.environ['BLOCKS_PREFIX']) if os.getenv('BLOCKS_PREFIX') else None
extra=['-I'+str(prefix/'include'),str(prefix/'lib/x86_64-linux-gnu/libBlocksRuntime.a')] if prefix else ['-lBlocksRuntime']
common=['clang','-std=gnu11','-fblocks','-O2','-isystem',include,'-DHAS_PARTS=1',
        '-DHAS_STATS='+a.compile_stats,*(['-DS2A_RB_COMPILE_FI_STATS=1'] if a.compile_stats=='1' else []),
        *[v for v in extra if v.startswith('-I')]]
libs=[v for v in extra if not v.startswith('-I')]+['-lobjc','-lpthread','-lm']
for name,opts in [('probe',['-fsanitize=undefined,address','-fno-sanitize-recover=all']),('bench',[])]:
    subprocess.run([*common,*opts,'probe.m',*libs,'-o',name],check=True,cwd=out)
if a.objects:
    subprocess.run([*common,'-c','probe.m','-o','callbacks.o'],check=True,cwd=out)
    subprocess.run([*common,'-S','-emit-llvm','probe.m','-o','callbacks.ll'],check=True,cwd=out)
