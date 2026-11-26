#define _GNU_SOURCE
#include "abi.h"
#include <sys/mman.h>
#include <unistd.h>
static void fill(uint8_t*p,size_t n,unsigned seed){while(n--){seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;*p++=(uint8_t)seed;}}
static writer modes[]={base,fixed,naive,staged,safe,suffix};
static size_t mat[6], mismatches[6], total, alias_count;
static void oracle(tex_t t,NVNcopyRegion r,const uint8_t*src,size_t row){
    int bw,bh;size_t b=(size_t)nvn_fmt_bpb(t.d.format,&bw,&bh);
    size_t w=((t.d.width+bw-1)/bw)*b,h=(t.d.height+bh-1)/bh,pitch=t.L.size/h;
    size_t ww=((r.width+bw-1)/bw)*b,hh=(r.height+bh-1)/bh;
    size_t x=(r.xoffset/bw)*b,y=r.yoffset/bh;if(!row)row=ww;
    uint8_t *pixels=malloc(w*h);assert(pixels);
    for(size_t j=0;j<h;j++)for(size_t i=0;i<w;i++)pixels[j*w+i]=t.mem[j*pitch+i];
    for(size_t j=0;j<hh;j++)for(size_t i=0;i<ww;i++)pixels[(y+j)*w+x+i]=src[j*row+i];
    for(size_t j=0;j<h;j++)for(size_t i=0;i<w;i++)t.mem[j*pitch+i]=pixels[j*w+i];
    free(pixels);
}
static void independent(void){
    size_t page=(size_t)sysconf(_SC_PAGESIZE);assert(page>256 && !(page&(page-1)));
    int formats[]={1,0x25,0x42,0x8b},flags[]={0x10,0x40,0x50};
    for(int f=0;f<4;f++)for(int g=0;g<3;g++)for(int large=0;large<2;large++)for(int pad=0;pad<3;pad++)
    for(int off=0;off<2;off++)for(int mode=0;mode<7;mode++)for(int sl=0;sl<3;sl++){
        int bw,bh,b=nvn_fmt_bpb(formats[f],&bw,&bh),w=(large?160:32)*bw-(bw>1),h=(large?96:12)*bh-(bh>1);
        int tight=(w+bw-1)/bw*b;
        tex_t t={.d={.target=1,.format=formats[f],.width=w,.height=h,.depth=1,.levels=1,.flags=flags[g],.stride=pad==0?0:pad==1?tight:tight+32}};
        nvn_tex_layout(&t.d,&t.L);
        NVNcopyRegion regs[]={{0,0,0,w,h,0},{0,0,0,bw,bh,1},{2*bw,3*bh,0,4*bw,3*bh,1},{0,h-3*bh+(bh>1),0,w,3*bh-(bh>1),1},
            {(w-1)/bw*bw,(h-1)/bh*bh,0,w-(w-1)/bw*bw,h-(h-1)/bh*bh,1},{bw,0,0,w-bw,h-bh,1},
            {bw+(bw>1),bh+(bh>1),0,2*bw,2*bh,1}};
        NVNcopyRegion r=regs[mode];
        size_t wb=(r.width+bw-1)/bw*b,rows=(r.height+bh-1)/bh,row=sl==0?0:sl==1?wb+11:wb>1?wb-1:wb;
        size_t offset=off?page-205:29,n=offset+t.L.size+65536,ins=(row?row:wb)*(rows-1)+wb;
        uint8_t *pool=aligned_alloc(page,(n+page-1)&~(page-1)),*expected=malloc(n),*src=malloc(ins);assert(pool&&expected&&src);
        fill(expected,n,41);fill(src,ins,921);t.mem=expected+offset;oracle(t,r,src,row);
        for(int m=0;m<6;m++){
            fill(pool,n,41);t.mem=pool+offset;
            stats got=modes[m](&t,NULL,&r,src,row,6511);
            if(memcmp(expected,pool,n))mismatches[m]++;
            if(m!=0)assert(!memcmp(expected,pool,n)&&got.notifies==1 && got.prepares==2);
            if(got.prepares==2)mat[m]++;
        }
        total++;free(pool);free(src);free(expected);
    }
}
static uint8_t *mapfile(int fd,size_t n) {
    uint8_t *p=mmap(NULL,n,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0);assert(p!=MAP_FAILED);return p;
}
static void aliases(void){
    long system_page=sysconf(_SC_PAGESIZE);assert(system_page>=128 && system_page%64==0);
    size_t page=(size_t)system_page,n=3*page;int height=(int)(n/64);
    for(int folded=0;folded<2;folded++)for(int reg=0;reg<4;reg++)for(int self=0;self<2;self++){
        FILE*fp=tmpfile();assert(fp);int fd=fileno(fp);assert(ftruncate(fd,n)==0);
        uint8_t *raw=mapfile(fd,n),*view=mapfile(fd,n),*src_view=mapfile(fd,n);
        if(folded){assert(mmap(view+page,page,PROT_READ|PROT_WRITE,MAP_SHARED|MAP_FIXED,fd,0)==view+page);}
        NVNcopyRegion rs[]={{0,1,0,64,32,1},{5,1,0,12,16,1},{0,height-12,0,64,12,1},{0,0,0,64,height,1}};
        NVNcopyRegion r=rs[reg];tex_t t={.d={.target=1,.format=1,.width=64,.height=(unsigned)height,.levels=1,.depth=1,.stride=64,.flags=0x10},.mem=view};
        nvn_tex_layout(&t.d,&t.L);assert(t.L.size==n);
        size_t row=64;
        uint8_t*src=self?view:src_view;
        // One source aliases the start of the pool. Keep its entire source span readable.
        uint8_t*expected=malloc(n);fill(raw,n,14);oracle(t,r,src,row);memcpy(expected,raw,n);
        for(int m=1;m<6;m++){
            if(self&&m==2)continue; // memcpy inside a row has no overlap contract.
            fill(raw,n,14);stats g=modes[m](&t,NULL,&r,src,row,0);assert(g.notifies==1);int bad=memcmp(expected,raw,n)!=0;
            if(m==1||m>=4)assert(!bad);
            if(bad){mismatches[m]++;printf("divergence variant=%d dest-folded=%d region=%d source-same-va=%d\n",m,folded,reg,self);}
        }
        alias_count++;free(expected);munmap(raw,n);munmap(view,n);munmap(src_view,n);fclose(fp);
    }
}
static void folded_wide_rows(void) {
    size_t page=(size_t)sysconf(_SC_PAGESIZE),n=8*page;
    FILE *fp=tmpfile();assert(fp);int fd=fileno(fp);assert(!ftruncate(fd,n));
    uint8_t *physical=mapfile(fd,n),*view=mapfile(fd,n);
    for(size_t off=page;off<n;off+=page)
        assert(mmap(view+off,page,PROT_READ|PROT_WRITE,MAP_SHARED|MAP_FIXED,fd,0)==view+off);
    uint8_t*input=malloc(n),*expected=malloc(n);assert(input&&expected);fill(input,n,78);
    for(int fmt=0;fmt<3;fmt++){
        int format=fmt==0?1:fmt==1?0x25:0x42,bw,bh,b=nvn_fmt_bpb(format,&bw,&bh);
        int width=(int)(2*page)/b*bw;
        tex_t t={.d={.target=1,.format=format,.width=width,.height=(unsigned)(4*bh),.depth=1,.levels=1,.flags=0x50},.mem=view};
        nvn_tex_layout(&t.d,&t.L);assert(t.L.size==n);
        NVNcopyRegion regs[]={{0,2*bh,0,width,2*bh,1},{width-bw,3*bh,0,bw,bh,1}};
        for(int i=0;i<2;i++) {
            fill(physical,n,27);stats a=fixed(&t,NULL,&regs[i],input,0,0);memcpy(expected,physical,n);
            for(int m=4;m<6;m++){fill(physical,n,27);stats z=modes[m](&t,NULL,&regs[i],input,0,0);
                assert(!memcmp(physical,expected,n)&&a.calls==z.calls&&a.bytes==z.bytes&&a.prepares==z.prepares&&a.notifies==z.notifies);}
        }
    }
    free(input);free(expected);munmap(physical,n);munmap(view,n);fclose(fp);
}
static void rejects(void) {
    uint8_t *p=calloc(1,16384),*src=calloc(1,16384);assert(p&&src);
    tex_t t={.d={.target=1,.width=64,.height=128,.levels=1,.flags=0x10,.format=1,.depth=1,.stride=64},.mem=p};
    nvn_tex_layout(&t.d,&t.L);NVNcopyRegion r={0,64,0,64,64,1},v;
    for(int i=0;i<8;i++){
        v=r;
        switch(i){case 0:v.width=0;break;case 1:v.height=0;break;case 2:v.xoffset=-1;break;case 3:v.yoffset=127;break;case 4:v.zoffset=1;break;case 5:v.depth=2;break;case 6:v.width=INT32_MAX;break;case 7:v.height=INT32_MAX;break;}
        assert(!eligible(&t,&v,src,0));
    }
    assert(!eligible(&t,&r,src,SIZE_MAX));assert(!eligible(&t,&r,NULL,0));
    assert(!eligible(&t,&r,(const uint8_t*)(uintptr_t)(UINTPTR_MAX-5),64));
    uint8_t *old=t.mem;t.mem=(uint8_t*)(uintptr_t)(UINTPTR_MAX-5);assert(!eligible(&t,&r,src,64));t.mem=old;
    assert(!eligible(&t,&r,src,31));
    uint64_t oldsize=t.L.size;t.L.size=8;assert(!eligible(&t,&r,src,64));t.L.size=oldsize;
    fill(src,t.L.size,31);fail_next();stats got=safe(&t,NULL,&r,src,64,0);assert(got.calls==2 && got.notifies==1&&!memcmp(p+4096,src,4096));
    const view_t view={.set_levels=1,.base_level=1};NVNcopyRegion small={0,0,0,1,1,1};
    for (int i=0;i<4;i++){
        tex_t bad=t;bad.d.target=i==0?4:1;bad.d.samples=i==1?4:0;
        const view_t layer={.set_layers=1,.min_layer=1},*vv=i==2?&view:i==3?&layer:NULL;
        uint8_t *cp=malloc(t.L.size);memcpy(cp,p,t.L.size);stats a=fixed(&bad,vv,&small,src,0,0);uint8_t *expected=malloc(t.L.size);memcpy(expected,p,t.L.size);memcpy(p,cp,t.L.size);
        stats b=safe(&bad,vv,&small,src,0,0);assert(a.notifies==b.notifies&&a.prepares==b.prepares&&a.calls==b.calls&&!memcmp(expected,p,t.L.size));free(cp);free(expected);
    }
    free(src);free(p);
}
int main(void){independent();printf("independent source cases %zu, complete backing mismatches before alias tests (base, fixed, direct, regional, safe, suffix): %zu %zu %zu %zu %zu %zu\n",total,mismatches[0],mismatches[1],mismatches[2],mismatches[3],mismatches[4],mismatches[5]);
    printf("two pool preparations before alias tests: %zu %zu %zu %zu %zu %zu\n",mat[0],mat[1],mat[2],mat[3],mat[4],mat[5]);
    aliases();folded_wide_rows();rejects();printf("alias cases %zu, cumulative mismatches: %zu %zu %zu %zu %zu %zu\n",alias_count,mismatches[0],mismatches[1],mismatches[2],mismatches[3],mismatches[4],mismatches[5]);assert(mismatches[0]&&mismatches[2]&&mismatches[3]&&!mismatches[4]&&!mismatches[5]);puts("six wide repeated-page cases, range and pointer refusals, allocation fallback and four public dispatch refusals: passed");return 0;}
