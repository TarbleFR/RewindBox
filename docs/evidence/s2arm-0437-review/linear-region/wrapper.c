#define _DEFAULT_SOURCE
#include <unistd.h>
#include "abi.h"
#define NVN_TEXTURE_FLAGS_LINEAR 0x10
#define NVN_TEXTURE_FLAGS_LINEAR_RENDER_TARGET 0x40
#define NVN_TEXTURE_TARGET_2D 1
#define NVN_TEXTURE_TARGET_3D 2
#define LOG(...) ((void)0)
#define ONCE_LOG(...) ((void)0)
#define die(...) abort()
static int dm_gfx_session_stopping(void){return 0;}
static stats measured;
static void dm_guest_write_prepare(void *p,size_t n){assert(p && n);measured.prepares++;}
static void nvn_be_tex_cpu_written(const tex_t *t){assert(t);measured.notifies++;}
static int force_oom;
static void *count_alloc(size_t n) {
    measured.calls++;measured.bytes+=n;
    if(force_oom){force_oom=0;return NULL;}
    return malloc(n);
}
#define malloc count_alloc
#include SOURCE_FILE
#undef malloc
stats NAME(const tex_t*t,const view_t*v,const NVNcopyRegion*r,const uint8_t*src,size_t row,size_t img){
    measured=(stats){0};
    write_texels(t,v,r,src,row,img);
    return measured;
}
#ifdef IS_SAFE
int eligible(const tex_t*t,const NVNcopyRegion*r,const uint8_t*src,size_t row){
    int bx,by,b=nvn_fmt_bpb(t->d.format,&bx,&by);assert(b);
    return write_region_linear(t,r,src,row,bx,by,b);
}
void fail_next(void){force_oom=1;}
#endif
