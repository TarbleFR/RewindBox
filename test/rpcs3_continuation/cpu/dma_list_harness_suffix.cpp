struct list_item {u8 sb,pad;be_t<u16> ts;be_t<u32> ea;};
static_assert(sizeof(list_item)==8);
static unsigned empty_cases=0,zero_element_cases=0,nonzero_cases=0,stall_cases=0;
static unsigned before_empty_reads=0,before_zero_accesses=0,before_underflows=0;
static void reset_probes(){copy_calls=vm_calls=list_reads=0;deny_list=deny_copy=false;}
template<class T>void initialize(T& s){
 s.local.fill(0x93);guest_memory.fill(0xa5);s.ch_stall_mask=s.events=0;
 s.ch_stall_stat={};s.ch_tag_stat={};s.mfc_size=s.mfc_fence=s.mfc_barrier=0;
 s.ch_tag_mask=0xffffffff;s.ch_tag_upd=MFC_TAG_UPDATE_ALL;reset_probes();
}
template<class T>void put_items(T& s,const std::vector<list_item>& xs){
 std::memcpy(s.ls+0x100,xs.data(),xs.size()*sizeof(list_item));
}
template<class T>void check_empty(bool historical){
 auto holder=std::make_unique<T>();T& s=*holder;
 for(MFC cmd:{MFC_GETL_CMD,MFC_GETLB_CMD,MFC_GETLF_CMD,MFC_PUTL_CMD,MFC_PUTLB_CMD,MFC_PUTLF_CMD})
 for(u32 tag=0;tag<32;++tag)for(u32 addr:{0u,0x100u,0x3fff8u,0xffffffffu})for(bool barrier:{false,true}){
  initialize(s);deny_list=true;
  if(barrier)s.mfc_queue[s.mfc_size++]={MFC_BARRIER_CMD,u8(tag),0,0,0,0};
  s.mfc_queue[s.mfc_size++]={cmd,u8(tag),0,0x10000,addr,0};
  bool threw=false;try{s.do_mfc(false,true);}catch(const std::runtime_error&){threw=true;}
  if(historical){assert(threw&&list_reads==1);++before_empty_reads;}
  else{assert(!threw&&list_reads==0&&vm_calls==0&&copy_calls==0);assert(s.mfc_size==0&&s.mfc_fence==0&&s.mfc_barrier==0);assert(s.ch_tag_stat.ready&&s.ch_tag_stat.value==0xffffffff);++empty_cases;}
 }
}
template<class T>void check_zero_elements(bool historical){
 auto holder=std::make_unique<T>();T& s=*holder;
 for(MFC cmd:{MFC_PUTL_CMD,MFC_PUTLB_CMD,MFC_PUTLF_CMD,MFC_PUTRL_CMD})
 for(u32 tag=0;tag<32;++tag)for(u32 off:{0u,16u,32u,48u}){
  initialize(s);put_items(s,{{0,0,0,0xc0002000u+off}});deny_copy=true;
  spu_mfc_cmd q{cmd,u8(tag),8,0x10000,0x100,0};bool threw=false;
  try{assert(s.do_list_transfer(q));}catch(const std::runtime_error&){threw=true;}
  if(historical){assert(vm_calls!=0);++before_zero_accesses;if(off&16){assert(threw&&copy_calls==1);assert(guest_memory[0x2000+off]==0x93);++before_underflows;}else{assert(!threw&&copy_calls==0);}}
  else{assert(!threw&&vm_calls==0&&copy_calls==0);assert(std::all_of(guest_memory.begin(),guest_memory.end(),[](u8 x){return x==0xa5;}));assert(s.ch_stall_mask==0&&s.events==0);++zero_element_cases;}
 }
}
template<class T>u64 check_nonzero(){
 auto holder=std::make_unique<T>();T& s=*holder;u64 hash=0;unsigned cases=0;
 for(MFC cmd:{MFC_GETL_CMD,MFC_GETLB_CMD,MFC_GETLF_CMD,MFC_PUTL_CMD,MFC_PUTLB_CMD,MFC_PUTLF_CMD,MFC_PUTRL_CMD})
 for(u32 size:{1u,2u,4u,8u,16u,32u,48u,64u,128u,256u,512u,1024u,2048u})
 for(u32 count:{1u,2u,6u,7u})for(u32 off:{0u,16u})for(bool rsxmem:{false,true}){
  if(rsxmem&&(cmd&MFC_GET_CMD)&&count>=6)continue; // guest VM base is a bounded adapter, not a 4 GiB mapping
  initialize(s);std::vector<list_item> items;u32 lsa=0x10000;
  for(u32 i=0;i<count;++i){u32 ea=(rsxmem?0xc0000000u:0u)+0x1000+i*0x4000+off;
   items.push_back({0,0,u16(size),ea});for(u32 j=0;j<size;++j){guest_memory[(ea&0x0fffffff)+j]=u8(i*11+j);s.ls[lsa+j]=u8(i*7+j*3);}lsa+=utils::align<u32>(size,16);}
  put_items(s,items);auto before_ls=s.local;auto before_mem=guest_memory;
  spu_mfc_cmd q{cmd,3,u16(count*8),0x10000,0x100,0};assert(s.do_list_transfer(q));
  auto expected_ls=before_ls;auto expected_mem=before_mem;lsa=0x10000;
  for(const auto& it:items){u32 ea=it.ea;u32 pos=ea&0x0fffffff;if(cmd&MFC_GET_CMD)std::memcpy(expected_ls.data()+lsa,before_mem.data()+pos,size);else std::memcpy(expected_mem.data()+pos,before_ls.data()+lsa,size);lsa+=utils::align<u32>(size,16);}
  assert(expected_ls==s.local&&expected_mem==guest_memory);assert(s.events==0&&s.ch_stall_mask==0);
  hash=hash*1315423911u+guest_memory[0x1000+off]+s.ls[0x10000]+size+count+cmd;++cases;
 }
 nonzero_cases=cases;return hash;
}
void check_stall_ack(){
 auto holder=std::make_unique<spu_new>();auto& s=*holder;
 for(MFC cmd:{MFC_PUTL_CMD,MFC_PUTLB_CMD,MFC_PUTLF_CMD})for(u32 tag=0;tag<32;++tag){
  initialize(s);put_items(s,{{0x80,0,0,0xc0002010},{0,0,16,0xc0002040}});
  s.mfc_queue[s.mfc_size++]={cmd,u8(tag),16,0x10000,0x100,0};s.ch_tag_mask=1u<<tag;
  s.do_mfc(false,true);assert(s.mfc_size==1&&s.mfc_queue[0].tag==(tag|0x80));assert(s.ch_stall_mask==(1u<<tag)&&s.events==SPU_EVENT_SN);assert(vm_calls==0);assert(!s.ch_tag_stat.ready);
  // Explicit channel-ack boundary: only the matching stall bit is cleared.
  s.mfc_queue[0].tag&=0x7f;s.ch_stall_mask=0;s.do_mfc(false,true);
  assert(s.mfc_size==0&&s.ch_tag_stat.value==(1u<<tag));assert(guest_memory[0x2040]==0x93&&guest_memory[0x2010]==0xa5);++stall_cases;
 }
 // A trailing S bit is ignored by the architecture, including size-zero entries.
 initialize(s);put_items(s,{{0x80,0,0,0xc0002010}});spu_mfc_cmd q{MFC_PUTL_CMD,1,8,0x10000,0x100,0};assert(s.do_list_transfer(q));assert(s.events==0&&s.ch_stall_mask==0&&vm_calls==0);++stall_cases;
}
int main(){
 check_empty<spu_old>(true);check_empty<spu_new>(false);
 check_zero_elements<spu_old>(true);check_zero_elements<spu_new>(false);
 auto old_hash=check_nonzero<spu_old>();auto new_hash=check_nonzero<spu_new>();assert(old_hash==new_hash);
 check_stall_ack();
 std::cout<<"{\"empty_queued_cases\":"<<empty_cases<<",\"baseline_empty_ls_reads\":"<<before_empty_reads
 <<",\"zero_element_cases\":"<<zero_element_cases<<",\"baseline_zero_element_accesses\":"<<before_zero_accesses
 <<",\"baseline_copy_underflows\":"<<before_underflows<<",\"nonzero_cases_each\":"<<nonzero_cases
 <<",\"stall_ack_cases\":"<<stall_cases<<",\"nonzero_trace_hash\":"<<new_hash<<",\"fixed_failures\":0}\n";
}
