#include <stdio.h>
#include <stdint.h>
#include "nvn_hmap.h"
#include "nvn_tex.h"
typedef struct {uint64_t pool; int64_t off; nvn_texdesc d;} key;
int main(void) {
    nvn_hmap m; nvn_hm_init(&m,sizeof(key));
    for (unsigned i=1; i<=17; i++) {
        key k={0}; k.pool=7; k.off=(i-1)*256; k.d=(nvn_texdesc){.target=1,.format=0x25,.width=128,.height=64,.depth=1,.levels=1};
        nvn_hm_put(&m,&k,(void *)(uintptr_t)i);
    }
    unsigned count=0;
    for (unsigned slot=0;slot<m.cap;slot++) if(m.vals[slot])printf("%s%lu ",++count==17?"survives=":"",(unsigned long)(uintptr_t)m.vals[slot]);
    printf("\n"); return 0;
}
