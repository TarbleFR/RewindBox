static unsigned normal_cases=0,mmio_cases=0,overlap_cases=0,invalid_cases=0;
struct trace{bool fault;unsigned faults,waits;u64 lock;friend bool operator==(const trace&,const trace&)=default;};
template<bool new_version>trace attempt(u32 addr,u32 size,bool readable,bool overlapping){
 namespace V=vm_old;
 if constexpr(new_version)vm_new::reset();else vm_old::reset();
 auto& pages=new_version?vm_new::g_pages:vm_old::g_pages;
 auto& locks=new_version?vm_new::g_range_lock_set:vm_old::g_range_lock_set;
 auto& bits=new_version?vm_new::g_range_lock_bits:vm_old::g_range_lock_bits;
 if(readable)for(u64 p=addr/4096;p<=(u64(addr)+size-1)/4096&&p<pages.size();++p)pages[p]=1;
 if(overlapping){bits[1].store(1);locks[0].store(u64(addr)|(u64(size)<<32));}
 reset_probes([&]{bits[1].store(0);});atomic_t<u64,128> own;bool threw=false;
 try{if constexpr(new_version)vm_new::range_lock(&own,addr,size);else vm_old::range_lock(&own,addr,size);}catch(const std::runtime_error&){threw=true;}
 return {threw,faults,waits,own.load()};
}
int main(){
 // Ordinary RAM protection and conflicting range exclusion are unchanged.
 for(u32 addr:{0u,0x1000u,0x10000u,0x7ffff000u,0xdffff000u})for(u32 size:{1u,4u,16u,128u,4096u})for(bool readable:{false,true})for(bool conflict:{false,true}){
  const auto a=attempt<false>(addr,size,readable,conflict),b=attempt<true>(addr,size,readable,conflict);assert(a==b);assert(b.fault==!readable);++normal_cases;
 }
 // Raw and group SPU addresses use validated host LS pointers, not g_pages.
 for(u32 addr:{0xe0000000u,0xe0040000u,0xf0000000u,0xf0100000u,0xf0200000u})for(u32 size:{1u,4u,16u,128u,4096u})for(bool conflict:{false,true}){
  const auto a=attempt<false>(addr,size,false,conflict),b=attempt<true>(addr,size,false,conflict);assert(a.fault&&a.faults==1);assert(!b.fault&&b.faults==0);assert(b.lock==(u64(addr)|(u64(size)<<32)));if(conflict){assert(b.waits==1);++overlap_cases;}++mmio_cases;
 }
 // Cross-page ordinary ranges must still fault at the first unreadable page.
 for(u32 addr:{0x1ff0u,0x3ff0u,0xdfffffe0u})for(u32 size:{16u,32u,64u}){
  const auto a=attempt<false>(addr,size,false,false),b=attempt<true>(addr,size,false,false);assert(a==b&&b.fault);++invalid_cases;
 }
 std::cout<<"{\"normal_permission_cases\":"<<normal_cases<<",\"mmio_cases\":"<<mmio_cases<<",\"mmio_conflicting_lock_cases\":"<<overlap_cases<<",\"unreadable_cross_page_cases\":"<<invalid_cases<<",\"fixed_failures\":0}\n";
}
