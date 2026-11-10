#include <algorithm>
#include <array>
#include <atomic>
#include <cassert>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <functional>
#include <iostream>
#include <list>
#include <memory>
#include <random>
#include <span>
#include <string>
#include <tuple>
#include <type_traits>
#include <unordered_map>
#include <unordered_set>
#include <vector>
#ifdef NDEBUG
#error "Assertions must remain enabled."
#endif
using u8=std::uint8_t;using u16=std::uint16_t;using u32=std::uint32_t;using u64=std::uint64_t;using usz=std::size_t;
constexpr u32 umax=~u32{0};
// Host allocator observation is active only in a dedicated untimed lookup pass.
inline bool count_allocations=false;inline u64 allocations=0;
[[gnu::noinline]] void* operator new(std::size_t bytes){if(count_allocations)++allocations;if(void* p=std::malloc(bytes?bytes:1))return p;throw std::bad_alloc();}
[[gnu::noinline]] void operator delete(void* p)noexcept{std::free(p);}
[[gnu::noinline]] void operator delete(void* p,std::size_t)noexcept{std::free(p);}
[[gnu::noinline]] void* operator new[](std::size_t bytes){return ::operator new(bytes);}
[[gnu::noinline]] void operator delete[](void* p)noexcept{std::free(p);}
[[gnu::noinline]] void operator delete[](void* p,std::size_t)noexcept{std::free(p);}
template<class T>using atomic_t=std::atomic<T>;
#define ensure(x, ...) assert(x)
#define AUDIT(x) assert(x)
namespace fmt {
template<class...T>std::string format(const char* f,T...v){int n=std::snprintf(nullptr,0,f,v...);std::vector<char>b(n+1);std::snprintf(b.data(),b.size(),f,v...);return std::string(b.data(),n);}
template<class...T>[[noreturn]]void throw_exception(const char*,T...){std::abort();}
}
namespace utils {constexpr u32 get_page_size(){return 4096;}enum class protection{rw,ro,no};inline u64 get_tsc(){return 0;}}
namespace rpcs3::ios::texture_validation {inline std::atomic<u64> trim_calls{0},trim_sections{0},trim_bytes{0},trim_ticks{0},dirty_releases{0},dirty_release_bytes{0};}
namespace rpcs3::ios::texture_residency {inline u64 current_frame(){return 1;}}
// @RANGES@
using utils::address_range32;using utils::address_range_vector32;
struct Log {template<class...T>void warning(const char*,T...){} } rsx_log;
namespace rsx {
enum section_bounds {full_range,locked_range,confirmed_range};
enum class texture_upload_context{shader_read,blit_engine_src,blit_engine_dst,framebuffer_storage,dma};
enum class memory_read_flags{flush_once,flush_always};
enum class component_order{default_};
enum class texture_dimension_extended{texture_dimension_2d};
enum class section_protection_strategy{lock,hash};
inline section_protection_strategy default_texture_protection_strategy(u32){return section_protection_strategy::hash;}
inline u64 visits=0;inline bool tracing=true,count_visits=true;inline std::vector<u32> validations;
struct buffered_section {
 address_range32 cpu_range,locked_range,confirmed_range;
 utils::protection protection=utils::protection::rw;
 section_protection_strategy protection_strat=section_protection_strategy::hash;
 u64 mem_hash=0,validated_epoch=0;bool prehash_bypass=false,locked=false;
 bool memory_valid=true;u32 id=0;
 void init_lockable_range(const address_range32& r){locked_range=r.to_page_range();}
 void reset(const address_range32&);void invalidate_range();void discard();
 const address_range32& get_bounds(section_bounds)const;
 bool valid_range()const{return cpu_range.valid();}
 u32 get_section_base()const{return cpu_range.start;}
 u32 get_section_size()const{return valid_range()?cpu_range.length():0;}
 const address_range32& get_section_range()const{return cpu_range;}
 const address_range32& get_confirmed_range()const{return confirmed_range.valid()?confirmed_range:cpu_range;}
 bool is_locked(bool=false)const{return locked;}
 bool overlaps(const address_range32& range,section_bounds bounds)const{return get_bounds(bounds).overlaps(range);}
 bool matches(const address_range32& range)const{return valid_range()&&cpu_range==range;}
 bool sync()const{if(tracing)validations.push_back(id);return memory_valid;}
};
// @BUFFERED@
}
// @SECTION_BEGIN@
struct Cache;struct Section;struct Traits{using section_storage_type=Section;using texture_cache_base_type=Cache;};
struct Predictor{};
struct Section:rsx::buffered_section {
 using ranged_storage_type=ranged_storage<Traits>;
 using ranged_storage_block_type=ranged_storage_block<ranged_storage_type>;
 ranged_storage_block_type* m_block=nullptr;ranged_storage_type* m_storage=nullptr;Cache* m_tex_cache=nullptr;Predictor* m_predictor=nullptr;
 bool dirty=true,resources=false,triggered_exists_callbacks=false,triggered_unreleased_callbacks=false;
 u16 width=0,height=0,depth=0,mipmaps=0;u32 real_pitch=0,rsx_pitch=0,gcm_format=0;
 bool pack_unpack_swap_bytes=false,swizzled=false,synchronized=false,flushed=false,speculatively_flushed=false,deferred_commit=false;
 u64 sync_timestamp=0,cache_tag=0,last_write_tag=0,last_use_frame=0;void* m_predictor_entry=nullptr;
 memory_read_flags readback_behaviour=memory_read_flags::flush_once;component_order view_flags=component_order::default_;
 texture_upload_context context=texture_upload_context::shader_read;texture_dimension_extended image_type=texture_dimension_extended::texture_dimension_2d;
 std::vector<address_range32> flush_exclusions;
 Section()=default;explicit Section(ranged_storage_block_type* b){initialize(b);}
 Section* derived(){return this;}
 void initialize(ranged_storage_block_type*);void reset(const address_range32&);void notify_range_valid();void invalidate_range();
 void on_section_resources_created();void on_section_resources_destroyed();void set_dirty(bool);void update_unreleased();bool is_unreleased()const;
 bool sync_protection();bool matches(u32,u32,u32,u32,u32)const;bool matches(u32,u32,u32,u32,u32,u32)const;
 bool is_dirty()const{if(rsx::count_visits)++rsx::visits;return dirty;}
 bool exists()const{return resources||(context==texture_upload_context::dma&&locked);}
 bool is_managed()const{return true;}
 texture_upload_context get_context()const{return context;}
 void destroy(){if(resources){resources=false;on_section_resources_destroyed();}}
 void unprotect();
 void discard(bool make_dirty);
 bool sync_protection_untouched(){return sync_protection();}
};
struct Cache {
 using Storage=ranged_storage<Traits>;using ranged_storage_block=typename Storage::block_type;using section_storage_type=Section;
 Storage m_storage{this};Predictor predictor;
 Predictor& get_predictor(){return predictor;}
 void on_memory_read_flags_changed(Section&,memory_read_flags){}
 ~Cache(){m_storage.clear();}
 // @LOOKUP@
};
void Section::unprotect(){if(locked){locked=false;m_block->on_section_unprotected(*this);set_dirty(true);}}
void Section::discard(bool make_dirty){if(locked){rsx::buffered_section::discard();m_block->on_section_unprotected(*this);}if(make_dirty)set_dirty(true);}
// @SECTION_END@
struct Query {u32 address,format=0;u16 width=0,height=0,depth=0,mips=0;bool locked=false;};
template<class Cache>int query(Cache& c,const Query& q){
 auto* r=q.locked?c.template find_texture_from_dimensions<true>(q.address,q.format,q.width,q.height,q.depth,q.mips):c.template find_texture_from_dimensions<false>(q.address,q.format,q.width,q.height,q.depth,q.mips);
 return r?static_cast<int>(r->id):-1;
}
template<class Section>void reset(Section& s,u32 base,u32 length,bool resources){
 s.unprotect();s.reset(address_range32::start_length(base,length));
 s.width=32;s.height=32;s.depth=1;s.mipmaps=4;s.gcm_format=7;s.memory_valid=true;
 if(resources){s.resources=true;s.on_section_resources_created();}
 // Host equivalent of completed GPU upload/protection, without guest mapping.
 s.context=rsx::texture_upload_context::blit_engine_dst;s.set_dirty(!resources);
}
template<class Cache>auto& add(Cache& c,u32 address,u32 length,u32 id,bool resources=true){
 auto& s=c.m_storage.block_for(address).create_section();s.id=id;reset(s,address,length,resources);return s;
}
struct Counters{u64 queries=0,old_visits=0,new_visits=0,mutations=0;};
void compare(before::Cache& a,after::Cache& b,const Query& q,Counters& counts){
 rsx::validations.clear();rsx::visits=0;const int old=query(a,q);const auto old_validation=rsx::validations;const auto old_visits=rsx::visits;counts.old_visits+=old_visits;
 rsx::validations.clear();rsx::visits=0;const int now=query(b,q);counts.new_visits+=rsx::visits;
 assert(old==now&&old_validation==rsx::validations);if(q.locked)assert(old_visits==rsx::visits);++counts.queries;
}
void compare_overlaps(before::Cache& a,after::Cache& b,address_range32 range){
 auto collect=[&](auto& c){std::vector<u32> ids;for(auto it=c.m_storage.range_begin(range,rsx::full_range,false);it!=c.m_storage.range_end();it++)ids.push_back(it->id);std::sort(ids.begin(),ids.end());return ids;};
 assert(collect(a)==collect(b));
}
Counters correctness(){
 auto a=std::make_unique<before::Cache>();auto b=std::make_unique<after::Cache>();Counters c;
 std::vector<before::Section*> old;std::vector<after::Section*> now;
 // Four chunks exercise construction order, duplicate addresses, resource-less
 // slots, mismatched dimensions and dirty/hash-failed earlier versions.
 for(u32 i=0;i<256;++i){const u32 addr=0x100000+(i%128)*4096;old.push_back(&add(*a,addr,128,i,i%7));now.push_back(&add(*b,addr,128,i,i%7));
  if(i==15||i==16)for(u32 j=0;j<=i;++j)compare(*a,*b,{old[j]->get_section_base()},c);
 }
 for(u32 i=0;i<256;++i){old[i]->gcm_format=now[i]->gcm_format=7+i/128;old[i]->width=now[i]->width=32+(i%3);}
 for(u32 i=0;i<128;++i)for(u32 fmt:{0u,7u,8u,9u})for(u16 mip:{u16{0},u16{3},u16{5}})compare(*a,*b,{0x100000+i*4096,fmt,0,0,0,mip},c);
 // Recycling the older duplicate later must not move it behind the newer one.
 reset(*old[16],0x110000,128,true);reset(*now[16],0x110000,128,true);
 old[144]->gcm_format=now[144]->gcm_format=7;
 compare(*a,*b,{0x110000},c);assert(query(*b,{0x110000})==16);
 old[16]->memory_valid=now[16]->memory_valid=false;
 compare(*a,*b,{0x110000},c);assert(query(*b,{0x110000})==144);
 for(u32 i=0;i<64;++i){old[i]->memory_valid=now[i]->memory_valid=false;compare(*a,*b,{old[i]->get_section_base()},c);}
 std::mt19937 rng(20261029);
 for(u32 i=0;i<20000;++i){u32 id=rng()%256;auto& x=*old[id];auto& y=*now[id];
  switch(rng()%7){
   case 0:x.set_dirty(true);y.set_dirty(true);break;
   case 1:x.memory_valid=y.memory_valid=(rng()%2);break;
   case 2:{u32 addr=0x100000+(rng()%192)*4096;reset(x,addr,128,false);reset(y,addr,128,false);++c.mutations;break;}
   case 3:{u32 addr=0x100000+(rng()%192)*4096;reset(x,addr,128,true);reset(y,addr,128,true);++c.mutations;break;}
   case 4:x.unprotect();y.unprotect();x.destroy();y.destroy();x.invalidate_range();y.invalidate_range();x.invalidate_range();y.invalidate_range();++c.mutations;break;
   case 5:x.width=y.width=16+(rng()%3)*16;x.mipmaps=y.mipmaps=rng()%8;break;
   case 6:if(x.valid_range()){x.context=y.context=rsx::texture_upload_context::dma;if(x.exists()){x.set_dirty(false);y.set_dirty(false);}}break;
  }
  Query q{static_cast<u32>(0x100000+(rng()%192)*4096)};if(i%3==0)q.format=7;if(i%5==0)q.width=32;if(i%7==0)q.mips=3;
  compare(*a,*b,q,c);if(i%31==0)compare(*a,*b,{q.address,0,0,0,0,0,true},c);
 }
 // Crossing a block boundary affects overlap iteration but never changes the
 // owning block of an exact-base lookup. Repeated retags remain ordered.
 for(u32 i=0;i<20;++i){u32 addr=0x200000+i*512;add(*a,addr,128,500+i);add(*b,addr,128,500+i);}
 for(u32 i=0;i<3;++i){u32 addr=0x2ff000;add(*a,addr,0x4000,300+i);add(*b,addr,0x4000,300+i);}
 compare(*a,*b,{0x2ff000},c);compare(*a,*b,{0x300000},c);compare_overlaps(*a,*b,address_range32::start_length(0x300000,0x2000));
 // Indexed edge blocks, including address zero and the last byte of 4GiB.
 for(u32 base:{0u,0xfff00000u}){
  for(u32 i=0;i<20;++i){u32 addr=base+i*512;add(*a,addr,128,600+i);add(*b,addr,128,600+i);}
  compare(*a,*b,{base},c);compare(*a,*b,{base+19*512},c);
 }
 add(*a,0xfffff000,4096,700);add(*b,0xfffff000,4096,700);compare(*a,*b,{0xfffff000},c);
 compare_overlaps(*a,*b,address_range32::start_length(0xfffffff0,16));
 // The 17th slot may remain invalid. Existing entries must already be indexed.
 for(u32 i=0;i<16;++i){add(*a,0x400000+i*512,128,800+i);add(*b,0x400000+i*512,128,800+i);}
 a->m_storage.block_for(0x400000).create_section();b->m_storage.block_for(0x400000).create_section();
 for(u32 i=0;i<16;++i)compare(*a,*b,{0x400000+i*512},c);
 // DMA-only valid range without a GPU image remains eligible when protected.
 auto& dx=add(*a,0x400000+30*512,128,900,false);auto& dy=add(*b,0x400000+30*512,128,900,false);
 dx.context=dy.context=rsx::texture_upload_context::dma;dx.locked=dy.locked=true;
 dx.m_block->on_section_protected(dx);dy.m_block->on_section_protected(dy);dx.set_dirty(false);dy.set_dirty(false);
 compare(*a,*b,{dx.get_section_base(),0,0,0,0,0,true},c);assert(query(*b,{dy.get_section_base()})==900);
 // Clear must also remove the resource-less entries left valid by destroy().
 a->m_storage.clear();b->m_storage.clear();for(u32 i=0;i<128;++i)compare(*a,*b,{0x100000+i*4096},c);
 for(u32 i=0;i<160;++i){u32 addr=0x100000+(159-i)*4096;add(*a,addr,256,i,false);add(*b,addr,256,i,false);}
 for(u32 i=0;i<160;++i)compare(*a,*b,{0x100000+i*4096},c);
 // Create resources later without resetting the previously indexed range.
 auto ai=a->m_storage.block_for(0x100000).begin();auto bi=b->m_storage.block_for(0x100000).begin();
 for(u32 i=0;i<160;++i,ai++,bi++){ai->resources=bi->resources=true;ai->on_section_resources_created();bi->on_section_resources_created();ai->set_dirty(false);bi->set_dirty(false);}
 for(u32 i=0;i<160;++i)compare(*a,*b,{0x100000+i*4096},c);
 return c;
}
template<class Fn>double median(Fn fn,u32 count){std::array<double,7> t{};u64 sum=0;for(auto& n:t){auto start=std::chrono::steady_clock::now();for(u32 i=0;i<count;++i){asm volatile("":::"memory");sum+=fn(i)+1;}n=std::chrono::duration<double,std::nano>(std::chrono::steady_clock::now()-start).count()/count;}assert(sum);std::sort(t.begin(),t.end());return t[3];}
template<class Cache>auto measured_index_bytes(Cache& c){usz total=0;for(auto& block:c.m_storage){if constexpr(requires{block.m_address_index;})total+=block.m_address_index.capacity()*sizeof(typename Cache::Storage::block_type::address_entry);}return total;}
void benchmark(){
 rsx::tracing=false;std::cout<<",\"benchmarks\":[";bool first=true;
 for(u32 size:{8,16,17,64,256,1024}){
 auto a=std::make_unique<before::Cache>();auto b=std::make_unique<after::Cache>();std::vector<before::Section*> x;std::vector<after::Section*> y;
 for(u32 i=0;i<size;++i){u32 addr=0x100000+i*512;x.push_back(&add(*a,addr,128,i));y.push_back(&add(*b,addr,128,i));}
 auto run=[&](auto& cache,bool miss){return median([&](u32 i){const int found=query(cache,{0x100000+((i*131)%size)*512+(miss?256u:0u)});return static_cast<u32>(found+1);},30000);};
 // Deterministic work counts are separate from all timed loops.
 rsx::count_visits=true;rsx::visits=0;for(u32 i=0;i<30000;++i)query(*a,{0x100000+((i*131)%size)*512});const u64 old=rsx::visits;
 rsx::visits=0;for(u32 i=0;i<30000;++i)query(*b,{0x100000+((i*131)%size)*512});const u64 now=rsx::visits;
 rsx::count_visits=false;const double hb=run(*a,false),ha=run(*b,false);
 const double mb=run(*a,true),ma=run(*b,true);
 const double first_before=median([&](u32){return static_cast<u32>(query(*a,{0x100000})+1);},30000);
 const double first_after=median([&](u32){return static_cast<u32>(query(*b,{0x100000})+1);},30000);
 allocations=0;count_allocations=true;
 for(u32 i=0;i<30000;++i)query(*b,{0x100000+((i*131)%size)*512});
 count_allocations=false;assert(allocations==0);
 auto change=[&](auto& slots){return median([&](u32 i){auto& s=*slots[(i*131)%size];reset(s,0x100000+((i*131)%size)*512+(i%2)*128,128,true);return s.get_section_base();},10000);};
 const double cb=change(x),ca=change(y);
 if(!first)std::cout<<",";
 first=false;
 std::cout<<"{\"sections\":"<<size<<",\"hitBeforeNs\":"<<hb<<",\"hitAfterNs\":"<<ha<<",\"missBeforeNs\":"<<mb<<",\"missAfterNs\":"<<ma<<",\"firstSlotBeforeNs\":"<<first_before<<",\"firstSlotAfterNs\":"<<first_after<<",\"lookupAllocations\":0,\"recycleBeforeNs\":"<<cb<<",\"recycleAfterNs\":"<<ca<<",\"baselineDirtyPredicateCalls\":"<<old<<",\"indexedDirtyPredicateCalls\":"<<now<<",\"allocatedIndexBytes\":"<<measured_index_bytes(*b)<<"}";
 }std::cout<<"],\"indexHeadersBytes\":"<<(sizeof(after::Cache::Storage)-sizeof(before::Cache::Storage))<<",\"hostAdapterSectionBytes\":"<<sizeof(after::Section);rsx::tracing=rsx::count_visits=true;
}
int main(int argc,char**){const auto c=correctness();std::cout<<"{\"queries\":"<<c.queries<<",\"mutations\":"<<c.mutations<<",\"baselineDirtyPredicateCalls\":"<<c.old_visits<<",\"indexedDirtyPredicateCalls\":"<<c.new_visits<<",\"sameFirstMatch\":true,\"sameValidationOrder\":true,\"sameOverlapMembership\":true,\"clearAndResourceLessRetags\":true,\"sectionLayoutUnchanged\":true,\"presentationWalkUnchanged\":true";if(argc>1)benchmark();std::cout<<"}\n";}
