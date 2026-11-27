static int cases;
static uint64_t get(int num,uint64_t id,uint64_t handle,int64_t sub,uint64_t *error){
    uint64_t regs[4]={0,id,handle,(uint64_t)sub};assert(read_api(num,regs)==1);*error=regs[0];return regs[1];
}
static void expect(int num,uint64_t id,uint64_t handle,int64_t sub,uint64_t error,uint64_t value){
    uint64_t e,v=get(num,id,handle,sub,&e);assert(e==error);assert(v==value);cases++;
}
static void basic(void){
    const uint64_t total[4]={3285ull<<20,507ull<<20,251ull<<20,(0x2238ull+0x710+0x80)<<12};
    const uint64_t states[]={0,1,4096,2ull<<20,APP_POOL-65536,APP_POOL,APP_POOL+65536};
    for(unsigned st=0;st<sizeof states/sizeof *states;st++){
        g_heap_cur=0;g_phys=states[st];code=g_mstack=0;L.sys_resource_size=65536;limit_on=1;
        for(int id=0;id<4;id++)for(int h=0;h<2;h++)for(int sub=-1;sub<6;sub++){
            uint64_t e=0,v=0,used=states[st]+L.sys_resource_size;
            if(id>2)e=0xF001;
            else if(h)e=0xE401;
            else if((uint64_t)sub>(id==2?1u:3u))e=0xE801;
            else if(id==2)v=sub==0?1:8;
            else if(id==1&&sub==0)v=APP_POOL>used?APP_POOL-used:0;
            else v=total[sub];
            expect(0x6f,id,h,sub,e,v);
        }
        const int ids[]={I_TotalMem,I_TotalNonSys,I_UsedMem,I_UsedNonSys,I_SysResTotal,I_SysResUsed};
        for(unsigned n=0;n<sizeof ids/sizeof *ids;n++)for(int h=0;h<2;h++)for(int sub=-1;sub<2;sub++){
            uint64_t e=sub?0xE801:h?0:0xE401,v=0;
            if(!e){
                switch(ids[n]){
                case I_TotalMem:v=APP_POOL;break;
                case I_TotalNonSys:v=APP_POOL-L.sys_resource_size;break;
                case I_UsedMem:v=states[st]+L.sys_resource_size;break;
                case I_UsedNonSys:v=states[st];break;
                case I_SysResTotal:v=L.sys_resource_size;break;
                case I_SysResUsed:v=((states[st]+(2ull<<20)-1)>>21)<<12;if(v>L.sys_resource_size)v=L.sys_resource_size;break;
                }
            }
            expect(0x29,ids[n],h?0xffff8001u:0,sub,e,v);
        }
    }
    for(int disabled=0;disabled<2;disabled++)for(int im=0;im<3;im++){
        limit_on=!disabled;g_heap_cur=12288;g_phys=8192;g_mstack=4096;code=16384;
        L.sys_resource_size=65536;image=im==0?0:im==1?64ull<<20:128ull<<20;
        uint64_t used=limit_on?g_heap_cur+g_phys+g_mstack+code+L.sys_resource_size:g_heap_cur+(image>(64ull<<20)?image:(64ull<<20));
        expect(0x29,I_UsedMem,0xffff8001u,0,0,used);
        expect(0x29,I_UsedNonSys,0xffff8001u,0,0,used-(limit_on?L.sys_resource_size:0));
    }
    limit_on=1;L.sys_resource_size=0;
    expect(0x29,I_SysResUsed,0xffff8001u,0,0,0);
}
static pthread_mutex_t sync_mu=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t sync_cv=PTHREAD_COND_INITIALIZER;
static int mid,release_writer,reader_done,which;
static uint64_t observed;
static void *writer(void *unused){
    (void)unused;GMU_LOCK();
    g_phys=2ull<<20;
    pthread_mutex_lock(&sync_mu);mid=1;pthread_cond_broadcast(&sync_cv);
    while(!release_writer)pthread_cond_wait(&sync_cv,&sync_mu);
    pthread_mutex_unlock(&sync_mu);g_phys=4ull<<20;GMU_UNLOCK();return NULL;
}
static void *reader(void *unused){
    (void)unused;uint64_t e;
    const int ids[]={0,I_UsedMem,I_UsedNonSys,I_SysResUsed};
    observed=get(which?0x29:0x6f,which?ids[which]:1,which?0xffff8001u:0,0,&e);assert(!e);
    pthread_mutex_lock(&sync_mu);reader_done=1;pthread_cond_broadcast(&sync_cv);pthread_mutex_unlock(&sync_mu);return NULL;
}
int main(void){
    basic();int during=0,final=0,intermediate=0;
    for(which=0;which<4;which++)for(int trial=0;trial<5;trial++){
        mid=release_writer=reader_done=0;g_heap_cur=g_phys=g_mstack=code=image=0;limit_on=1;L.sys_resource_size=65536;
        pthread_t wt,rt;assert(!pthread_create(&wt,NULL,writer,NULL));
        pthread_mutex_lock(&sync_mu);while(!mid)pthread_cond_wait(&sync_cv,&sync_mu);pthread_mutex_unlock(&sync_mu);
        assert(!pthread_create(&rt,NULL,reader,NULL));struct timespec deadline;clock_gettime(CLOCK_REALTIME,&deadline);deadline.tv_nsec+=30000000;
        if(deadline.tv_nsec>=1000000000){deadline.tv_nsec-=1000000000;deadline.tv_sec++;}
        pthread_mutex_lock(&sync_mu);int rc=0;while(!reader_done&&!rc)rc=pthread_cond_timedwait(&sync_cv,&sync_mu,&deadline);assert(rc==0||rc==ETIMEDOUT);
        during+=reader_done;release_writer=1;pthread_cond_broadcast(&sync_cv);pthread_mutex_unlock(&sync_mu);
        assert(!pthread_join(wt,NULL));assert(!pthread_join(rt,NULL));
        uint64_t expected_final=which==0?APP_POOL-(4ull<<20)-65536:which==1?(4ull<<20)+65536:which==2?(4ull<<20):8192;
        uint64_t expected_mid=which==0?APP_POOL-(2ull<<20)-65536:which==1?(2ull<<20)+65536:which==2?(2ull<<20):4096;
        final+=observed==expected_final;intermediate+=observed==expected_mid;
        assert(observed==expected_final||observed==expected_mid);
    }
    printf("{\"api_cases\":%d,\"concurrent_cases\":20,\"completed_while_writer_locked\":%d,\"intermediate_values\":%d,\"final_values\":%d}\n",cases,during,intermediate,final);
}
