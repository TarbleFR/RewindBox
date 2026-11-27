from pathlib import Path
import argparse
p=argparse.ArgumentParser()
p.add_argument('--reference',required=True);p.add_argument('--candidate',required=True);p.add_argument('--output',required=True)
a=p.parse_args()
base=Path(a.reference).read_text();new=Path(a.candidate).read_text()
out=Path(a.output);out.mkdir(parents=True,exist_ok=True)
pre='''#include <stdint.h>
#include <stddef.h>
#include <pthread.h>
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <time.h>
#define APP_POOL (1ull<<30)
static pthread_mutex_t g_mu=PTHREAD_MUTEX_INITIALIZER;
#define GMU_LOCK() pthread_mutex_lock(&g_mu)
#define GMU_UNLOCK() pthread_mutex_unlock(&g_mu)
static uint64_t g_heap_cur,g_phys,g_mstack,code,image;
static int limit_on=1;
static struct { uint64_t sys_resource_size; } L;
static int phys_limit_on(void){return limit_on;}
static uint64_t code_bytes(void){return code;}
static size_t image_bytes(void){return image;}
static uint64_t pool_fixed(void){return limit_on?code+g_mstack+L.sys_resource_size+g_phys:image;}
static uint64_t mem_used(void){return g_heap_cur+pool_fixed();}
'''
a=base.index('enum { I_CoreMask');b=base.index('};',a)+2
pre+=base[a:b]+'\n'
for label,s in [('reference',base),('candidate',new)]:
    a=s.index('    case 0x6f: {');b=s.index('    case 0x2A:',a)
    sys=s[a:b]
    a=s.index('    case 0x29: {');b=s.index('        switch (id) {',a)
    b=s.index('        switch (id) {',b+1)
    info=s[a:b]+'        switch (id) {\n'
    a=s.index('        case I_TotalMem: v = APP_POOL;',b)
    b=s.index('        case I_DebuggerAttached:',a)
    info+=s[a:b]+'''        default: regs[0]=0xF001;regs[1]=0;return 1;
        }
        regs[0]=0;regs[1]=v;return 1; }
'''
    wrapper='static int read_api(int num,uint64_t *regs){switch(num){\n'+sys+info+'default:return 0;}}\n'
    (out/(label+'.c')).write_text(pre+wrapper+Path(__file__).with_name('memory_info_main.inc').read_text())
