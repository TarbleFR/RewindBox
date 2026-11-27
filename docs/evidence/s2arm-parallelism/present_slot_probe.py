import argparse
import os
import subprocess
import tempfile
from pathlib import Path

parser = argparse.ArgumentParser(description='Exercise the presentation slot scheduler and its host-side ownership updates.')
parser.add_argument('engine', type=Path, help='Patched S2Arm source directory')
options = parser.parse_args()
temporary = tempfile.TemporaryDirectory()
r = Path(temporary.name)
src = (options.engine / 'graphics/nvn/gfx/nvn/nvn_mtl.m').read_text()
def through(start,end,at=0):
    a=src.index(start,at); b=src.index(end,a)+len(end); return src[a:b]
selector=through('static int rb_pick_present_slot(', '\n}')
reserve_start=src.index('    // Publish the owner before submission')
reserve=through('    pthread_mutex_lock(&g_pq_mu);','pthread_mutex_unlock(&g_pq_mu);', reserve_start)
rollback_at=src.index('        if (!accepted)')
rollback=through('            pthread_mutex_lock(&g_pq_mu);','pthread_mutex_unlock(&g_pq_mu);',rollback_at)
release_at=src.index('g_present_slot_done[alloc_i] = ticket;')
release=src[release_at:src.index(' RB_WAKE_CALL(',release_at)].replace('rb_present_complete(ticket);','(void)ticket;')
(r/'check.c').write_text('''
#include <assert.h>
#include <inttypes.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
typedef struct { int busy; } Stage;
enum {NO,YES};
static pthread_mutex_t g_pq_mu = PTHREAD_MUTEX_INITIALIZER;
static uint64_t g_present_alloc_fence[3], g_present_slot_done[3];
static Stage aa_slots[3],fx_slots[3];
static unsigned g_pq_inflight;
'''+selector+'''
static void reserve(int alloc_i, uint64_t ticket) {
    Stage *aa = aa_slots+alloc_i, *fxs = fx_slots+alloc_i;
    assert(!aa->busy && !fxs->busy);
'''+reserve+'''
}
static void refuse(int alloc_i) {
    Stage *aa = aa_slots+alloc_i, *fxs = fx_slots+alloc_i;
    assert(aa->busy && fxs->busy);
'''+rollback+'''
}
static void release(int alloc_i, uint64_t ticket) {
    Stage *aa = aa_slots+alloc_i, *fxs = fx_slots+alloc_i;
    assert(aa->busy && fxs->busy && ticket == g_present_alloc_fence[alloc_i]);
'''+release+'''
}
static uint32_t state=42;
static uint32_t next(void) {state=1664525u*state+1013904223u; return state;}
int main(void) {
  unsigned cases=0, opportunities=0, saturated=0;
  for(int pref=0;pref<3;pref++) for(int mask=0;mask<8;mask++) {
    uint64_t owner[3],done[3];
    for(int i=0;i<3;i++) { owner[i]=(UINT64_C(1)<<43)+i; done[i]=owner[i]-(unsigned)!!(mask&(1<<i)); }
    int pick=rb_pick_present_slot(pref,owner,done);
    assert((pick==-1)==(mask==7));
    if(pick!=-1) { assert(!(mask&(1<<pick))); if(!(mask&(1<<pref))) assert(pick==pref); }
    if(pick!=-1 && pref!=pick) opportunities++;
    saturated+=(pick==-1); cases++;
  }
  /* Four guest textures. With ticket 3 running, enqueue 4,5,6. FIFO chooses 5 and drops 4.
     At the following tick ticket 6 collides with ticket 3 while slot 1 is idle. */
  reserve(0,3); reserve(2,5);
  assert(rb_pick_present_slot(6%3,g_present_alloc_fence,g_present_slot_done)==1);
  /* Exercise callback order independently of the order in which resources were acquired. */
  reserve(1,6); assert(g_pq_inflight==3); release(1,6); assert(g_present_slot_done[0]==0);
  release(2,5); release(0,3); assert(!g_pq_inflight);
  /* Refusal after acquisition returns the slot to its previous genuine GPU feedback. */
  reserve(0,9); refuse(0); assert(g_present_slot_done[0]==3 && g_present_alloc_fence[0]==3 && !g_pq_inflight);
  unsigned refused=1, completed=0, choices=0, all_busy=0;
  uint64_t ticket=9;
  for(unsigned k=0;k<1000000;k++) {
    uint32_t r=next();
    if ((r>>16)%5 < 2) {
       int s=(r>>24)%3;
       if (aa_slots[s].busy) {release(s,g_present_alloc_fence[s]); completed++;}
    } else {
       ticket+=1+(r>>20)%4; int pref=ticket%3;
       int pick=rb_pick_present_slot(pref,g_present_alloc_fence,g_present_slot_done);
       if(pick<0) { assert(g_pq_inflight==3); all_busy++; continue; }
       choices+=pref!=pick;
       assert(g_pq_inflight<3); reserve(pick,ticket);
       if((r>>16)%11==0) {refuse(pick); refused++;}
    }
    unsigned count=0;
    for(int i=0;i<3;i++){
        int busy=g_present_slot_done[i]!=g_present_alloc_fence[i];
        assert(aa_slots[i].busy==busy && fx_slots[i].busy==busy);
        count+=(unsigned)busy;
    }
    assert(count==g_pq_inflight);
  }
  for(int i=0;i<3;i++) if(aa_slots[i].busy) release(i,g_present_alloc_fence[i]);
  assert(!g_pq_inflight);
  printf("selector cases %u; alternative cases %u; saturated cases %u; fixture iterations 1000000; alternates %u; all-busy %u; simulated callbacks %u; refused %u; final inflight %u\\n",cases,opportunities,saturated,choices,all_busy,completed,refused,g_pq_inflight);
}
''')

cc = os.environ.get('CC', 'cc')
subprocess.run([cc, '-std=c11', '-O1', '-g', '-fsanitize=undefined', '-fno-sanitize-recover=all',
                '-Wall', '-Wextra', '-Werror', '-pthread', str(r / 'check.c'), '-o', str(r / 'check')], check=True)
subprocess.run([str(r / 'check')], check=True)
