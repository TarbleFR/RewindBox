#define _GNU_SOURCE
#define main ordinary_validation_main
#include "verify.c"
#undef main
int main(void) {
    long sz=sysconf(_SC_PAGESIZE);assert(sz>128);size_t pg=(size_t)sz,n=pg*3;
    FILE *fp=tmpfile();assert(fp);int fd=fileno(fp);assert(!ftruncate(fd,n));
    uint8_t *physical=mapfile(fd,n),*view=mapfile(fd,n),*source=mapfile(fd,n),*expected=malloc(n);assert(expected);
    assert(mmap(view+pg,pg,PROT_READ|PROT_WRITE,MAP_SHARED|MAP_FIXED,fd,0)==view+pg);
    assert(mmap(source+pg,pg,PROT_READ|PROT_WRITE,MAP_SHARED|MAP_FIXED,fd,0)==source+pg);
    size_t tests=0;
    for(int off=1;off<120;off+=17)for(int fm=0;fm<3;fm++)for(int horiz=0;horiz<3;horiz++){
        int bw,bh,b,fmt=fm==0?1:fm==1?0x25:0x42;b=nvn_fmt_bpb(fmt,&bw,&bh);
        tex_t t={.d={.target=1,.format=fmt,.width=(64/b)*bw,.height=16*bh,.depth=1,.levels=1,.flags=0x50,.stride=64},.mem=view+pg-off};
        nvn_tex_layout(&t.d,&t.L);assert(t.L.size==1024);
        NVNcopyRegion r={horiz*bw,bh,0,3*bw,8*bh,1};
        fill(physical,n,91);oracle(t,r,source+pg-off,horiz?67:64);memcpy(expected,physical,n);
        fill(physical,n,91);stats a=safe(&t,NULL,&r,source+pg-off,horiz?67:64,0);
        assert(a.calls==0 && a.prepares==2 && a.notifies==1 && !memcmp(physical,expected,n));tests++;
    }
    free(expected);munmap(physical,n);munmap(source,n);munmap(view,n);fclose(fp);
    printf("%zu small linear images crossing two aliases of one page, overlapping source in a distinct mapping: passed\n",tests);
}
