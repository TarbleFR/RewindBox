from pathlib import Path
import argparse,json,os,subprocess
parser=argparse.ArgumentParser(description="Check the actual initial transfer-memory quota block and unchanged allocation guard.")
parser.add_argument('--reference',type=Path,required=True,help='thread.c before 0492, including 0480')
parser.add_argument('--candidate',type=Path,required=True,help='thread.c with 0492')
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--cc',default='cc')
a=parser.parse_args()
root=a.output.resolve();root.mkdir(parents=True,exist_ok=True)
src=a.candidate.read_text()
old=a.reference.read_text()
start=src.index('    case 0x15: {  // CreateTransferMemory')
end=src.index('        // 分配失败回 OutOfResource',start)
alloc=src[end:src.index('    case 0x16:',end)]
old_start=old.index('    case 0x15: {  // CreateTransferMemory');oe=old.index('        // 分配失败回 OutOfResource',old_start)
assert alloc==old[oe:old.index('    case 0x16:',oe)],'0480 guard drift'
code=r'''
#define _GNU_SOURCE
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#define MAX_H 8192
#define LIM_TMEM 128
#define S2A_OBJ_TMEM 6
static pthread_mutex_t G=PTHREAD_MUTEX_INITIALIZER;
static struct { uint32_t kind; uint16_t gen; void *obj; uint64_t cookie; } g_h[MAX_H];
static int g_kcnt[16],seen;
static int limits=1;
static int lim_on(void){return limits;}
static void glock(void){pthread_mutex_lock(&G);}
static void review_unlock(pthread_mutex_t*m){pthread_mutex_unlock(m);}
#define pthread_mutex_unlock(m) (seen=count,review_unlock(m))
static int create(uint64_t*regs){switch(0x15){
'''+src[start:end]+r'''
 regs[0]=0;return 1;}}return 0;}
#undef pthread_mutex_unlock
static uint64_t state=0x11c0ffee9283ull;
static uint32_t rnd(void){state^=state<<13;state^=state>>7;state^=state<<17;return (uint32_t)state;}
static uint64_t digest=0xcbf29ce484222325ull;
static void mix(uint64_t v){digest=(digest^v)*0x100000001b3ull;}
int main(void){int tests=0;
 for(int n=0;n<1024;n++){
  memset(g_h,0,sizeof g_h);memset(g_kcnt,0,sizeof g_kcnt);
  for(int i=1;i<MAX_H;i++){g_h[i].kind=(rnd()%11)==0?(rnd()%15)+1:0;if(g_h[i].kind)g_kcnt[g_h[i].kind&15]++;}
  int actual=0;for(int i=1;i<MAX_H;i++)actual+=g_h[i].kind==S2A_OBJ_TMEM;
  uint64_t regs[8]={0};regs[1]=0x10000;regs[2]=0x4000;regs[3]=3;seen=-1;create(regs);
  if(seen!=actual||regs[0]!=(actual>=128?0x10801:0))return 2;
  mix(seen);mix(regs[0]);tests++;
 }
 for(int n=0;n<=130;n++){
  memset(g_h,0,sizeof g_h);memset(g_kcnt,0,sizeof g_kcnt);for(int i=0;i<n;i++)g_h[MAX_H-i-1].kind=S2A_OBJ_TMEM;g_kcnt[S2A_OBJ_TMEM]=n;
  for(int kind=0;kind<7;kind++){
   uint64_t regs[8]={0};regs[1]=0x10000;regs[2]=0x4000;regs[3]=3;
   uint64_t expected=n>=128?0x10801:0;
   if(kind==1){regs[1]++;expected=0xCC01;}if(kind==2){regs[2]++;expected=0xCA01;}if(kind==3){regs[2]=0;expected=0xCA01;}
   if(kind==4){regs[1]=0xfffffffffffff000ull;regs[2]=0x4000;expected=0xD401;}if(kind==5){regs[3]=2;expected=0xD801;}if(kind==6){regs[3]=4;expected=0xD801;}
   seen=-1;create(regs);if(regs[0]!=expected)return 3;mix(regs[0]);mix((uint64_t)seen);tests++;
  }
 }
 printf("{\"tests\":%d,\"digest\":\"%016llx\",\"guard0480Identical\":true}\n",tests,(unsigned long long)digest);return 0;
}
'''
(root/'tmem.c').write_text(code)
subprocess.run([a.cc,'-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer','-pthread',str(root/'tmem.c'),'-o',str(root/'tmem')],check=True)
results=[]
for flag in ['0','1']:
 import os
 env=dict(os.environ,S2A_RB_TMEM_COUNT=flag,ASAN_OPTIONS='detect_leaks=0')
 r=subprocess.run([str(root/'tmem')],env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 assert r.returncode==0,r.stdout
 results.append({'flag':flag,**json.loads(r.stdout)})
assert results[0]['digest']==results[1]['digest']
(root/'tmem.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps(results,indent=2))
