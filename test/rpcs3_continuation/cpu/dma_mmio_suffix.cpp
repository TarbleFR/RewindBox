static u32 failures=0,group_put_cases=0,group_get_cases=0,ram_cases=0,raw_cases=0,invalid_offset_cases=0,snr_cases=0;
static u32 old_group_faults=0,new_group_faults=0,old_atomic_misroutes=0,new_atomic_misroutes=0;
static void check(bool ok,const char*msg){if(!ok){++failures;std::cerr<<msg<<'\n';}}
struct result{bool fault=false,invalid=false;u32 atomics=0,ranges=0;};
static result invoke(bool newer,spu_thread&sender,const spu_mfc_cmd&args){
 new_mode=newer;current_cpu=&sender;range_calls=atomic_calls=fault_calls=0;
 for(auto&r:vm::reservations)r.v=0;
 vm::reservation_storage.fill(0);sender.slot.v=0;
 result r;
 try{(newer?new_dma_transfer:old_dma_transfer)(&sender,args,sender.ls);}
 catch(const access_fault&){r.fault=true;}
 catch(const std::invalid_argument&){r.invalid=true;}
 r.atomics=atomic_calls;r.ranges=range_calls;return r;
}
static void seed(spu_thread&sender,spu_thread&target){
 for(u32 i=0;i<SPU_LS_SIZE;++i){sender.ls[i]=u8(i*17+31);target.ls[i]=u8(i*13+59);}
 for(u32 i=0;i<ordinary_ram.size();++i)ordinary_ram[i]=u8(i*19+11);
 sender.snr[0]=sender.snr[1]=target.snr[0]=target.snr[1]=0;
 sender.snr_calls=target.snr_calls=0;
}
int main(){
 auto sender=std::make_unique<spu_thread>();auto target=std::make_unique<spu_thread>();spu_group group;
 sender->group=&group;group.threads[0]=target.get();for(auto&i:group.threads_map)i=0;
 raw_threads[0]=target.get();raw_threads[255]=target.get();
 for(u32 size:{1u,2u,4u,8u,16u,32u,64u,128u,256u,512u,1024u,2048u})
 for(u32 off:{0u,0x80u,0x100u,0xff80u,0xfff0u,0x10010u,0x3f800u})
 for(bool accurate:{false,true})for(bool atomic:{false,true}){
  if(off+size>SPU_LS_SIZE)continue;
  g_cfg.core.spu_accurate_dma=accurate;g_cfg.core.accurate_cache_line_stores=atomic;
  for(bool is_get:{false,true})for(u8 modifiers:{u8(0),u8(MFC_BARRIER_MASK),u8(MFC_FENCE_MASK)}){
   spu_mfc_cmd args;args.cmd=(is_get?MFC_GET_CMD:MFC_PUT_CMD)|modifiers;args.size=u16(size);args.lsa=0x800;args.eal=SYS_SPU_THREAD_BASE_LOW+off;
   std::array<u8,SPU_LS_SIZE>expected{};
   for(bool newer:{false,true}){
    seed(*sender,*target);std::memcpy(expected.data(),is_get?sender->ls:target->ls,SPU_LS_SIZE);
    std::memcpy(expected.data()+(is_get?args.lsa:off),is_get?target->ls+off:sender->ls+args.lsa,size);
    const auto r=invoke(newer,*sender,args);check(!r.invalid,"valid group LS rejected");
    if(!is_get&&!newer){++old_group_faults;old_atomic_misroutes+=r.atomics!=0;check(r.fault,"original group PUT failed to reproduce address fault");}
    else{check(!r.fault,"valid group transfer fault after fix / unchanged GET");check(std::memcmp(expected.data(),is_get?sender->ls:target->ls,SPU_LS_SIZE)==0,"group copy differs from bounded memcpy oracle");}
    if(newer&&!is_get){new_group_faults+=r.fault;new_atomic_misroutes+=r.atomics!=0;check(r.atomics==0,"group PUT still entered atomic address re-resolution");check(r.ranges!=0,"group PUT omitted normal range exclusion");}
   }
   if(is_get)++group_get_cases;else ++group_put_cases;
  }
  for(bool is_get:{false,true}){
   spu_mfc_cmd args;args.cmd=is_get?MFC_GET_CMD:MFC_PUT_CMD;args.size=u16(size);args.lsa=0x800;args.eal=0x10000+off;
   std::array<u8,SPU_LS_SIZE>expected_ls{};std::array<u8,2048>expected_ram{};result before;
   for(bool newer:{false,true}){
    seed(*sender,*target);std::memcpy(expected_ls.data(),sender->ls,SPU_LS_SIZE);
    if(is_get)std::memcpy(expected_ls.data()+args.lsa,ordinary_ram.data()+args.eal,size);else std::memcpy(expected_ram.data(),sender->ls+args.lsa,size);
    const auto r=invoke(newer,*sender,args);check(!r.fault&&!r.invalid,"ordinary RAM routing changed");
    check(is_get?std::memcmp(expected_ls.data(),sender->ls,SPU_LS_SIZE)==0:std::memcmp(expected_ram.data(),ordinary_ram.data()+args.eal,size)==0,"ordinary RAM copy differs");
    if(newer){check(r.atomics==before.atomics&&r.ranges==before.ranges,"ordinary RAM lock/atomic route differs");}else before=r;
   }
   ++ram_cases;
  }
  for(bool is_get:{false,true}){
   spu_mfc_cmd args;args.cmd=is_get?MFC_GET_CMD:MFC_PUT_CMD;args.size=u16(size);args.lsa=0x800;args.eal=RAW_SPU_BASE_ADDR+off;
   std::array<u8,SPU_LS_SIZE>expected{};
   for(bool newer:{false,true}){
    seed(*sender,*target);std::memcpy(expected.data(),is_get?sender->ls:target->ls,SPU_LS_SIZE);
    std::memcpy(expected.data()+(is_get?args.lsa:off),is_get?target->ls+off:sender->ls+args.lsa,size);
    const auto r=invoke(newer,*sender,args);check(!r.invalid,"valid raw LS rejected");
    if(newer||is_get||!r.fault){check(!r.fault,"valid raw transfer fault after fix / unchanged GET");check(std::memcmp(expected.data(),is_get?sender->ls:target->ls,SPU_LS_SIZE)==0,"raw LS copy differs");}
    if(newer&&!is_get)check(r.atomics==0&&r.ranges>0,"raw PUT route omitted normal range exclusion");
   }
   ++raw_cases;
  }
 }
 // All effective addresses above SYS_SPU_THREAD_BASE_LOW produce index<=255;
 // offset<=0xfffff and size<=0xffff, so offset+size cannot wrap u32.
 for(u32 index:{0u,1u,255u})for(u32 offset:{SPU_LS_SIZE-1,SPU_LS_SIZE,SPU_LS_SIZE+16,0xfffffu})
 for(u16 size:{u16(2),u16(16),u16(128),u16(0xffff)})for(bool newer:{false,true})for(bool is_get:{false,true}){
  spu_mfc_cmd args;args.cmd=is_get?MFC_GET_CMD:MFC_PUT_CMD;args.size=size;args.lsa=0x800;args.eal=SYS_SPU_THREAD_BASE_LOW+index*SYS_SPU_THREAD_OFFSET+offset;
  const auto r=invoke(newer,*sender,args);check(r.invalid&&!r.fault&&r.atomics==0&&r.ranges==0,"invalid group offset was not rejected before memory use");++invalid_offset_cases;
 }
 for(u32 offset:{SPU_LS_SIZE-1,SPU_LS_SIZE,0xfffffu})for(u16 size:{u16(2),u16(16),u16(128),u16(0xffff)})for(bool newer:{false,true})for(bool is_get:{false,true}){
  spu_mfc_cmd args;args.cmd=is_get?MFC_GET_CMD:MFC_PUT_CMD;args.size=size;args.lsa=0x800;args.eal=RAW_SPU_BASE_ADDR+offset;
  const auto r=invoke(newer,*sender,args);check(r.invalid&&!r.fault&&r.atomics==0&&r.ranges==0,"invalid raw offset was not rejected before memory use");++invalid_offset_cases;
 }
 for(bool newer:{false,true})for(u32 offset:{SYS_SPU_THREAD_SNR1,SYS_SPU_THREAD_SNR2})for(u8 cmd:{MFC_PUT_CMD,u8(MFC_PUT_CMD|MFC_FENCE_MASK),MFC_SDCRZ_CMD}){
  seed(*sender,*target);sender->_ref<u32>(0x800)=0x12345678;
  spu_mfc_cmd args;args.cmd=cmd;args.size=4;args.lsa=0x800;args.eal=SYS_SPU_THREAD_BASE_LOW+offset;
  const auto r=invoke(newer,*sender,args);check(!r.invalid&&!r.fault&&r.atomics==0&&r.ranges==0,"SNR route changed");
  check(target->snr_calls==1&&target->snr[offset==SYS_SPU_THREAD_SNR2]==(cmd==MFC_SDCRZ_CMD?0:0x12345678),"SNR payload changed");++snr_cases;
 }
 std::cout<<"{\"group_put_cases\":"<<group_put_cases<<",\"group_get_cases\":"<<group_get_cases<<",\"ordinary_ram_cases\":"<<ram_cases<<",\"raw_spu_cases\":"<<raw_cases<<",\"invalid_offset_cases\":"<<invalid_offset_cases<<",\"snr_cases\":"<<snr_cases<<",\"original_group_address_faults\":"<<old_group_faults<<",\"fixed_group_address_faults\":"<<new_group_faults<<",\"original_atomic_group_misroutes\":"<<old_atomic_misroutes<<",\"fixed_atomic_group_misroutes\":"<<new_atomic_misroutes<<",\"failures\":"<<failures<<"}\n";
 return failures?1:0;
}
