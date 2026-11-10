#include <algorithm>
#include <array>
#include <atomic>
#include <cassert>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <concepts>
#include <iterator>
#include <utility>
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
template<class T>concept UnsignedInt=std::is_integral_v<T> && std::is_unsigned_v<T>;
inline bool count_allocations=false;inline u64 array_allocations=0,array_bytes=0;
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
inline std::vector<u32> warnings;
struct Log {void warning(const char*,u32 address){warnings.push_back(address);} } rsx_log;
namespace rsx {
enum section_bounds {full_range,locked_range,confirmed_range};
enum texture_upload_context : u32 {shader_read=1,blit_engine_dst=2,blit_engine_src=4,framebuffer_storage=8,dma=16};
enum class memory_read_flags{flush_once,flush_always};
enum class component_order{default_};
enum class texture_dimension_extended{texture_dimension_2d};
enum class section_protection_strategy{lock,hash};
inline section_protection_strategy default_texture_protection_strategy(u32){return section_protection_strategy::hash;}
inline u64 range_visits=0;inline std::vector<u32> unprotects,merges;
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
 bool valid_range()const{if(count_visits)++range_visits;return cpu_range.valid();}
 u32 get_section_base()const{return cpu_range.start;}
 u32 get_section_size()const{return valid_range()?cpu_range.length():0;}
 const address_range32& get_section_range()const{return cpu_range;}
 const address_range32& get_confirmed_range()const{return confirmed_range.valid()?confirmed_range:cpu_range;}
 bool is_locked(bool page=false)const{return locked&&(!page||protection_strat==section_protection_strategy::lock);}
 bool overlaps(const address_range32& range,section_bounds bounds)const{return get_bounds(bounds).overlaps(range);}
 bool matches(const address_range32& range)const{return valid_range()&&cpu_range==range;}
 bool sync()const{if(tracing)validations.push_back(id);return memory_valid;}
};
// @BUFFERED@
}

template<class C>u32 size32(const C& c){return static_cast<u32>(c.size());}
namespace rsx {
template<class T>using reverse_pointer=std::reverse_iterator<T*>;
namespace aligned_allocator {
template<size_t Align>void* malloc(size_t bytes){if(count_allocations){++array_allocations;array_bytes+=bytes;}return std::malloc(bytes);}
template<size_t Align>void* realloc(void* ptr,size_t,size_t bytes){if(count_allocations){++array_allocations;array_bytes+=bytes;}return std::realloc(ptr,bytes);}
inline void free(void* p){std::free(p);}
}
// @PITCH@
}
// @ARRAY@
struct Attributes {u32 address=0,gcm_format=7;u16 width=32,height=32,depth=1,mipmaps=4;u32 pitch=128;bool swizzled=false;};
struct Options {u32 lookup_mask=7;};
struct Result {
 u32 view=0,context=0,format=0,scale=0,image=0,address=0,merge_count=0;
 address_range32 ios_validation_range;
 bool selected=false;
 Result()=default;
 Result(u32 v,u32 c,u32 f,u32 s,u32 i,u32 a):view(v),context(c),format(f),scale(s),image(i),address(a),selected(true){}
 bool operator==(const Result&)const=default;
};
using sampled_image_descriptor=Result;
// @STORAGE@

// @SECTION_BEGIN@
struct Cache;struct Section;struct Traits{using section_storage_type=Section;using texture_cache_base_type=Cache;};
struct Predictor{};
struct Section:rsx::buffered_section {
 using ranged_storage_type=ranged_storage<Traits>;
 using ranged_storage_block_type=ranged_storage_block<ranged_storage_type>;
 ranged_storage_block_type* m_block=nullptr;ranged_storage_type* m_storage=nullptr;Cache* m_tex_cache=nullptr;Predictor* m_predictor=nullptr;
 bool dirty=true,resources=false,triggered_exists_callbacks=false,triggered_unreleased_callbacks=false;
 u16 width=0,height=0,depth=0,mipmaps=0;u32 real_pitch=0,rsx_pitch=0,gcm_format=0;
 u32 view_id=0;
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
 bool is_swizzled()const{return swizzled;}
 u16 get_height()const{return height;}
 u32 get_rsx_pitch()const{return rsx_pitch;}
 u32 get_view(u32)const{return view_id;}
 u32 get_format_class()const{return gcm_format+17;}
 u32 get_image_type()const{return static_cast<u32>(image_type);}
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
 // @LOOKUPS@
};
void Section::unprotect(){if(rsx::tracing)rsx::unprotects.push_back(id);if(locked){rsx::buffered_section::discard();m_block->on_section_unprotected(*this);if(context==texture_upload_context::shader_read)set_dirty(true);}}
void Section::discard(bool make_dirty){if(locked){rsx::buffered_section::discard();m_block->on_section_unprotected(*this);}if(make_dirty)set_dirty(true);}
// @SECTION_END@
// @METHODS@
struct Query {Attributes attr;address_range32 range;Options options;};
Query make_query(u32 address,u32 length=256){Query q;q.attr.address=address;q.range=address_range32::start_length(address,length);return q;}
void lock_section(Section& s,bool locked){if(s.locked==locked)return;s.locked=locked;if(locked){s.protection=utils::protection::ro;s.m_block->on_section_protected(s);}else{s.protection=utils::protection::rw;s.m_block->on_section_unprotected(s);}s.update_unreleased();}
void reset_section(Section& s,u32 base,u32 length,bool resources=true){
 lock_section(s,false);s.reset(address_range32::start_length(base,length));
 s.width=32;s.height=32;s.depth=1;s.mipmaps=4;s.gcm_format=7;s.rsx_pitch=128;
 s.memory_valid=true;s.swizzled=false;s.view_id=s.id;
 s.context=rsx::texture_upload_context::blit_engine_dst;
 if(resources){s.resources=true;s.on_section_resources_created();lock_section(s,true);s.set_dirty(false);}else{s.set_dirty(true);}
}
struct Rig {
 std::unique_ptr<Cache> cache=std::make_unique<Cache>();std::vector<Section*> slots;
 Section& add(u32 address,u32 length,u32 id,bool resources=true){auto& s=cache->m_storage.block_for(address).create_section();s.id=id;reset_section(s,address,length,resources);slots.push_back(&s);return s;}
 void clear(){cache->m_storage.clear();slots.clear();}
};
struct State {
 bool dirty,locked,resources,unreleased,memory_valid,swizzled;
 utils::protection protection;address_range32 confirmed,cpu;u64 last_use,validated_epoch;
 bool operator==(const State&)const=default;
};
State state(const Section& s){return {s.dirty,s.locked,s.resources,s.triggered_unreleased_callbacks,s.memory_valid,s.swizzled,s.protection,s.confirmed_range,s.cpu_range,s.last_use_frame,s.validated_epoch};}
std::vector<State> states(const Rig& r){std::vector<State> out;for(const auto* s:r.slots)out.push_back(state(*s));return out;}
void restore(Rig& r,const std::vector<State>& snapshots){
 for(usz i=0;i<r.slots.size();++i){auto& s=*r.slots[i];const auto& v=snapshots[i];assert(s.resources==v.resources&&s.cpu_range==v.cpu);lock_section(s,v.locked);s.dirty=v.dirty;s.memory_valid=v.memory_valid;s.swizzled=v.swizzled;s.protection=v.protection;s.confirmed_range=v.confirmed;s.last_use_frame=v.last_use;s.validated_epoch=v.validated_epoch;s.update_unreleased();assert(state(s)==v);}
}
void clear_trace(){rsx::validations.clear();rsx::unprotects.clear();rsx::merges.clear();warnings.clear();rsx::visits=rsx::range_visits=0;array_allocations=array_bytes=0;}
struct Trace {std::vector<u32> validations,unprotects,merges,warnings;bool operator==(const Trace&)const=default;};
Trace trace(){return {rsx::validations,rsx::unprotects,rsx::merges,warnings};}
struct Counts {u64 queries=0,debug_queries=0,mutations=0,range_before=0,range_after=0,predicates_before=0,predicates_after=0,allocations_before=0,allocations_after=0;};
Result compare(Rig& r,const Query& q,Counts& c,bool debug=false){
 const auto initial=states(r);clear_trace();count_allocations=true;
 const auto old=debug?r.cache->query_before_debug(q.attr,q.range,q.options):r.cache->query_before(q.attr,q.range,q.options);
 count_allocations=false;const auto old_trace=trace();const auto old_state=states(r);
 c.range_before+=rsx::range_visits;c.predicates_before+=rsx::visits;c.allocations_before+=array_allocations;
 restore(r,initial);clear_trace();count_allocations=true;
 const auto now=debug?r.cache->query_after_debug(q.attr,q.range,q.options):r.cache->query_after(q.attr,q.range,q.options);
 count_allocations=false;c.range_after+=rsx::range_visits;c.predicates_after+=rsx::visits;c.allocations_after+=array_allocations;
 if(!(old==now&&old_trace==trace()&&old_state==states(r))){std::cerr<<"differential failure query "<<c.queries<<" debug="<<debug<<" base="<<q.attr.address<<" before="<<old.selected<<":"<<old.view<<":"<<old.merge_count<<" after="<<now.selected<<":"<<now.view<<":"<<now.merge_count<<"\n";std::cerr<<" result="<<(old==now)<<" states="<<(old_state==states(r))<<" trace="<<(old_trace==trace())<<"\n";for(auto v:old_trace.validations)std::cerr<<"bV"<<v<<",";for(auto v:rsx::validations)std::cerr<<"aV"<<v<<",";for(auto v:old_trace.merges)std::cerr<<"bM"<<v<<",";for(auto v:rsx::merges)std::cerr<<"aM"<<v<<",";std::cerr<<"\n";std::abort();}
 ++c.queries;c.debug_queries+=debug;return now;
}
void fill(Rig& r,u32 count,u32 base=0x100000){for(u32 i=0;i<count;++i)r.add(base+i*512,256,i+1);}
Counts correctness(){
 Counts counts;
 for(u32 n:{1,8,16,17,64,256}){
  Rig r;fill(r,n);
  for(u32 i=0;i<n;++i){auto q=make_query(0x100000+i*512);auto hit=compare(r,q,counts);assert(hit.selected&&hit.view==i+1);compare(r,q,counts,true);q.attr.gcm_format=99;assert(!compare(r,q,counts).selected);q=make_query(q.attr.address+256);assert(!compare(r,q,counts).selected);}
 }
 {
  Rig r;fill(r,17);const auto base=0x110000;auto& first=r.add(base,256,101);auto& second=r.add(base,256,102);auto& third=r.add(base,256,103);
  first.gcm_format=3;second.rsx_pitch=256;auto q=make_query(base);assert(compare(r,q,counts).view==103);
  first.gcm_format=7;first.memory_valid=false;second.rsx_pitch=128;assert(compare(r,q,counts).view==102);
  assert(rsx::validations==std::vector<u32>({101,102}));assert(first.dirty&&!first.locked);
  reset_section(first,base,256);first.swizzled=true;third.swizzled=false;
  const auto result=compare(r,q,counts);assert(!result.selected&&warnings.size()==1);assert(first.dirty&&!first.locked);assert(rsx::validations.front()==101);
  reset_section(first,base,256);first.view_id=0;const auto null_view=compare(r,q,counts);assert(null_view.selected&&null_view.view==0&&null_view.merge_count==0);
  reset_section(first,base,256);first.confirmed_range=address_range32::start_length(base,128);second.confirmed_range=address_range32::start_length(base,64);third.confirmed_range=address_range32::start_length(base,256);
  assert(compare(r,q,counts,true).view==103);assert(rsx::validations==std::vector<u32>({101,102,103}));
  third.confirmed_range=address_range32::start_length(base,32);assert(!compare(r,q,counts,true).selected);assert(rsx::validations==std::vector<u32>({101,102,103,101,102,103}));
  // Height-one rules use the production pitch_compatible helper. Mip counts
  // deliberately differ: this exact path requests zero and ignores mip count.
  for(auto* s:{&first,&second,&third}){reset_section(*s,base,256);s->height=1;s->rsx_pitch=13;s->mipmaps=0;}
  q.attr.height=1;q.attr.pitch=99;assert(compare(r,q,counts).view==101);
  q.attr.height=0;assert(compare(r,q,counts).view==101);
  q.attr.height=32;for(auto* s:{&first,&second,&third})s->height=32;
  assert(!compare(r,q,counts).selected);
  q.attr.pitch=13;first.context=rsx::framebuffer_storage;second.context=rsx::blit_engine_src;q.options.lookup_mask=rsx::shader_read|rsx::blit_engine_dst;
  assert(compare(r,q,counts).view==103);
  lock_section(third,false);assert(!compare(r,q,counts).selected);
 }
 {
  Rig r;fill(r,17);const u32 base=0x120000;
  r.add(base-64,512,3100);std::vector<Section*> duplicates;
  for(u32 i=0;i<24;++i){auto& slot=r.add(base,256,3200+i);slot.memory_valid=false;duplicates.push_back(&slot);}
  r.add(base-32,512,3300);
  auto q=make_query(base);const auto miss=compare(r,q,counts);assert(!miss.selected&&miss.merge_count==2);
  // More than eight invalidated exacts exercises the retention buffer's real
  // heap growth and swap-with-tail merge order, including a later swizzle stop.
  for(u32 i=0;i<24;++i){reset_section(*duplicates[i],base,256);duplicates[i]->memory_valid=i>=15;}
  duplicates[15]->swizzled=true;const auto swizzle=compare(r,q,counts);assert(!swizzle.selected&&warnings.size()==1);
  for(u32 i=0;i<24;++i){reset_section(*duplicates[i],base,256);duplicates[i]->memory_valid=i>=20;}
  assert(compare(r,q,counts).view==3220);
 }
 {
  Rig r;
  // Earlier blocks contribute unowned overlap pointers. Same storage is used
  // for each version so their unordered_set iteration order is truly equal.
  for(u32 i=0;i<24;++i)r.add(0xff000+i*16,0x6000,1000+i);
  for(u32 i=0;i<64;++i)r.add(0x100000+i*32,0x5000,1100+i);
  auto q=make_query(0x100000+63*32);assert(compare(r,q,counts).view==1163);
  q.attr.gcm_format=99;assert(!compare(r,q,counts).selected);assert(rsx::merges.size()==88);
  // A failed earlier exact candidate remains dirty and absent from the final
  // merge, while validation order of all other blit destinations is retained.
  r.slots.back()->memory_valid=false;q.attr.gcm_format=7;compare(r,q,counts);
  q=make_query(0xff000);q.range=address_range32::start_length(0x100000,256);
  const auto unowned=compare(r,q,counts);assert(unowned.selected&&unowned.view==1000);
  // Multiblock ranges, out-of-order insertion and a same-address duplicate.
  for(u32 i=0;i<24;++i)r.add(0x200000+(23-i)*512,256,1300+i);
  r.add(0x100000,0x120000,1400);q=make_query(0x100000,0x120000);q.attr.width=99;compare(r,q,counts);compare(r,q,counts,true);
 }
 {
  Rig r;fill(r,16);r.slots.push_back(&r.cache->m_storage.block_for(0x100000).create_section());
  for(u32 i=0;i<16;++i)assert(compare(r,make_query(0x100000+i*512),counts).view==i+1);
  auto& no_resource=r.add(0x120000,256,3000,false);
  reset_section(no_resource,0x121000,256,false);compare(r,make_query(0x120000),counts);
  reset_section(no_resource,0x121000,256,true);assert(compare(r,make_query(0x121000),counts).view==3000);
  r.clear();fill(r,64);compare(r,make_query(0x121000),counts);assert(compare(r,make_query(0x100000),counts).view==1);
 }
 {
  Rig r;for(u32 base:{0u,0xfff00000u})for(u32 i=0;i<24;++i)r.add(base+i*512,256,4000+i);
  compare(r,make_query(0),counts);compare(r,make_query(0xfff00000),counts);
  r.add(0xfffff000,4096,5000);assert(compare(r,make_query(0xfffff000,4096),counts).view==5000);
  auto q=make_query(0xfffff000,16);q.range=address_range32::start_length(0xfffffff0,16);compare(r,q,counts);
 }
 {
  Rig r;fill(r,256);std::mt19937 rng(0x59329);
  for(u32 i=0;i<12000;++i){
   auto& s=*r.slots[rng()%r.slots.size()];
   switch(rng()%9){
    case 0:s.memory_valid=rng()%2;break;
    case 1:s.set_dirty(true);break;
    case 2:reset_section(s,0x100000+(rng()%192)*512,256,true);++counts.mutations;break;
    case 3:reset_section(s,0x100000+(rng()%192)*512,256,false);++counts.mutations;break;
    case 4:lock_section(s,false);s.destroy();s.invalidate_range();s.invalidate_range();++counts.mutations;break;
    case 5:s.width=16+(rng()%3)*16;s.height=1+(rng()%2)*31;s.depth=1+(rng()%2);s.mipmaps=rng()%8;break;
    case 6:s.swizzled=rng()%2;s.rsx_pitch=(rng()%3)*128;break;
    case 7:s.context=rsx::texture_upload_context(1u<<(rng()%5));s.update_unreleased();break;
    case 8:if(s.valid_range()&&s.resources){lock_section(s,true);s.set_dirty(false);}break;
   }
   auto q=make_query(0x100000+(rng()%192)*512);q.attr.width=16+(rng()%3)*16;q.attr.height=(rng()%4==0)?1:32;q.attr.depth=1+(rng()%2);q.attr.pitch=(rng()%3)*128;q.attr.swizzled=rng()%2;q.options.lookup_mask=1+(rng()%15);
   if(i%17==0)q.attr.gcm_format=0;
   compare(r,q,counts,i%4==0);
  }
 }
 return counts;
}
template<class Fn>double median(Fn fn,u32 count=20000){std::array<double,7>times{};u64 checksum=0;for(auto& t:times){auto start=std::chrono::steady_clock::now();for(u32 i=0;i<count;++i){asm volatile("":::"memory");auto result=fn(i);checksum+=result.view+result.merge_count+1;}t=std::chrono::duration<double,std::nano>(std::chrono::steady_clock::now()-start).count()/count;}assert(checksum);std::sort(times.begin(),times.end());return times[3];}
void benchmark(){
 rsx::tracing=rsx::count_visits=false;std::cout<<",\"benchmarks\":[";bool first=true;
 for(u32 n:{8,16,17,64,256,1024}){
  Rig r;fill(r,n);
  auto run=[&](bool candidate,bool miss,bool first_slot){return median([&](u32 i){auto q=make_query(0x100000+(first_slot?0:((i*131)%n))*512+(miss?256u:0u));return candidate?r.cache->query_after(q.attr,q.range,q.options):r.cache->query_before(q.attr,q.range,q.options);});};
  const double hit_before=run(false,false,false),hit_after=run(true,false,false),miss_before=run(false,true,false),miss_after=run(true,true,false),first_before=run(false,false,true),first_after=run(true,false,true);
  // Dense overlapping ranges force the baseline's small-vector overflow.
  Rig overlaps;for(u32 i=0;i<n;++i)overlaps.add(0x100000+i*32,0x10000,i+1);
  auto q=make_query(0x100000+(n-1)*32);
  auto bench_overlap=[&](bool candidate){return median([&](u32){return candidate?overlaps.cache->query_after(q.attr,q.range,q.options):overlaps.cache->query_before(q.attr,q.range,q.options);});};
  const double overlap_before=bench_overlap(false),overlap_after=bench_overlap(true);
  array_allocations=array_bytes=0;count_allocations=true;for(u32 i=0;i<1000;++i)overlaps.cache->query_before(q.attr,q.range,q.options);count_allocations=false;
  const auto before_alloc=array_allocations,before_bytes=array_bytes;
  array_allocations=array_bytes=0;count_allocations=true;for(u32 i=0;i<1000;++i)overlaps.cache->query_after(q.attr,q.range,q.options);count_allocations=false;
  const auto after_alloc=array_allocations,after_bytes=array_bytes;if(n>16)assert(after_alloc==0);if(n>8)assert(before_alloc>0);
  if(!first)std::cout<<",";
  first=false;
  std::cout<<"{\"sections\":"<<n<<",\"uniformHitBeforeNs\":"<<hit_before<<",\"uniformHitAfterNs\":"<<hit_after<<",\"missBeforeNs\":"<<miss_before<<",\"missAfterNs\":"<<miss_after<<",\"firstSlotBeforeNs\":"<<first_before<<",\"firstSlotAfterNs\":"<<first_after<<",\"overlapPrefixHitBeforeNs\":"<<overlap_before<<",\"overlapPrefixHitAfterNs\":"<<overlap_after<<",\"allocationsFor1000PrefixHitsBefore\":"<<before_alloc<<",\"allocationsFor1000PrefixHitsAfter\":"<<after_alloc<<",\"allocatedBytesBefore\":"<<before_bytes<<",\"allocatedBytesAfter\":"<<after_bytes<<"}";
 }
 std::cout<<"]";rsx::tracing=rsx::count_visits=true;
}
int main(int argc,char**){const auto c=correctness();std::cout<<"{\"queries\":"<<c.queries<<",\"debugQueries\":"<<c.debug_queries<<",\"mutations\":"<<c.mutations<<",\"rangePredicateCallsBefore\":"<<c.range_before<<",\"rangePredicateCallsAfter\":"<<c.range_after<<",\"dirtyPredicateCallsBefore\":"<<c.predicates_before<<",\"dirtyPredicateCallsAfter\":"<<c.predicates_after<<",\"arrayAllocationsBefore\":"<<c.allocations_before<<",\"arrayAllocationsAfter\":"<<c.allocations_after<<",\"sameFirstMatch\":true,\"sameValidationOrder\":true,\"sameMergeOrder\":true,\"sameMutationState\":true,\"sameInvalidViewSelection\":true,\"confirmedRangeDebugCovered\":true,\"realStorageAndPitch\":true";if(argc>1)benchmark();std::cout<<"}\n";}
