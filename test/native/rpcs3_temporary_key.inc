#include <algorithm>
#include <array>
#include <cassert>
#include <concepts>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <iostream>
#include <iterator>
#include <mutex>
#include <span>
#include <string>
#include <type_traits>
#include <unordered_map>
#include <utility>
#include <vector>
using u8=std::uint8_t;using u16=std::uint16_t;using u32=std::uint32_t;using u64=std::uint64_t;using usz=std::size_t;
constexpr u32 umax=~u32{0};
template<class C>u32 size32(const C& c){return static_cast<u32>(c.size());}
template<class T>concept UnsignedInt=std::is_unsigned_v<T>;
#define ensure(x,...) assert(x)
#define AUDIT(x) assert(x)
namespace fmt {
template<class...T>std::string format(const char* f,T...v){int n=std::snprintf(nullptr,0,f,v...);std::vector<char>b(n+1);std::snprintf(b.data(),b.size(),f,v...);return std::string(b.data(),n);}
template<class...T>[[noreturn]]void throw_exception(const char*,T...){std::abort();}
}
namespace utils{constexpr u32 get_page_size(){return 4096;}}
@RANGE@
using utils::address_range32;
inline bool observe_arrays=false;
inline u64 array_allocations=0,array_bytes=0;
namespace rsx {
template<class T>using reverse_pointer=std::reverse_iterator<T*>;
namespace aligned_allocator {
template<size_t>void* malloc(size_t n){if(observe_arrays){++array_allocations;array_bytes+=n;}return std::malloc(n);}
template<size_t>void* realloc(void* p,size_t,size_t n){if(observe_arrays){++array_allocations;array_bytes+=n;}return std::realloc(p,n);}
inline void free(void* p){std::free(p);}
}
}
@ARRAY@
@ATTRIBUTES@
enum class deferred_request_command:u32{nop,copy_image_static,copy_image_dynamic,cubemap_gather,cubemap_unwrap,atlas_gather,_3d_gather,_3d_unwrap,mipmap_gather,blit_image_static};
struct copy_region_descriptor{void* src;u32 xform,base_addr;u8 level;u16 src_x,src_y,dst_x,dst_y,dst_z,src_w,src_h,dst_w,dst_h;};
struct texture_channel_remap_t{u32 encoded=0xDEAD;std::array<u8,4> control_map{},channel_map{};};
using image_resource_type=void*;using image_view_type=u64;using commandbuffer_type=int;
@DESCRIPTOR@
struct Boundary {
 std::mutex m_cache_mutex;
 std::vector<image_view_type> m_uncached_subresources;
 std::vector<std::pair<u32,u64>> events;
 u64 next=1;bool fail=false;
 u64 checksum(const deferred_subresource& desc){
  u64 sum=desc.encoded_properties()+desc.external_ref_addr+desc.force_bg_load;
  for(auto& region:desc.sections_to_copy)sum=sum*33+region.base_addr+region.level;
  return sum;
 }
 image_view_type create(int&,deferred_subresource& desc){events.emplace_back(1,checksum(desc));return fail?0:next++;}
 void update_image_contents(int&,image_view_type view,deferred_subresource& desc){events.emplace_back(2,view);events.emplace_back(3,checksum(desc));}
 void release_temporary_subresource(image_view_type view){events.emplace_back(4,view);}
 image_view_type generate_cubemap_from_images(int& cmd,deferred_subresource& d){return create(cmd,d);}
 image_view_type generate_3d_from_2d_images(int& cmd,deferred_subresource& d){return create(cmd,d);}
 image_view_type generate_atlas_from_images(int& cmd,deferred_subresource& d){return create(cmd,d);}
 image_view_type create_temporary_subresource_view(int& cmd,deferred_subresource& d){return create(cmd,d);}
 image_view_type generate_2d_mipmaps_from_images(int& cmd,deferred_subresource& d){return create(cmd,d);}
 void expand_cube_unwrap_sections(rsx::simple_array<copy_region_descriptor>& sections,deferred_subresource& desc){sections=desc.sections_to_copy;}
 void expand_3d_unwrap_sections(rsx::simple_array<copy_region_descriptor>& sections,deferred_subresource& desc,int){sections=desc.sections_to_copy;}
};
@VERSIONS@
int main(){
 before::Cache old;after::Cache now;int cmd=0;u64 checks=0;
 auto same=[&]{assert(old.events==now.events);assert(old.m_temporary_subresource_cache.size()==now.m_temporary_subresource_cache.size());assert(old.m_uncached_subresources==now.m_uncached_subresources);++checks;};
 for(u32 i=0;i<6000;++i){
  deferred_subresource desc{};desc.address=0x100000+(i%47)*4096;desc.width=32+(i%3);desc.height=64;desc.depth=1;desc.mipmaps=1;desc.gcm_format=0x85;
  desc.op=static_cast<deferred_request_command>(1+i%9);desc.cache_range=address_range32::start_length(desc.address,4096);
  desc.do_not_cache=i%19==0;desc.force_bg_load=i%2;desc.external_ref_addr=i;
  for(u32 j=0;j<i%33;++j)desc.sections_to_copy.push_back({nullptr,0,i+j,static_cast<u8>(j%16),0,0,0,0,0,32,64,32,64});
  old.fail=now.fail=i%23==0;
  assert(old.create_temporary_subresource(cmd,desc)==now.create_temporary_subresource(cmd,desc));same();
  ++desc.external_ref_addr;
  assert(old.create_temporary_subresource(cmd,desc)==now.create_temporary_subresource(cmd,desc));same();
  if(i%17==0){auto r=address_range32::start_length(0x100000+(i%47)*4096+128,5000);old.notify_surface_changed(r);now.notify_surface_changed(r);same();}
  if(i%97==0){old.clear();now.clear();same();old.events.clear();now.events.clear();}
 }
 old.clear();now.clear();same();
 // Observe copies made exclusively by successful static cache insertion. The
 // source recipes themselves are prepared before allocation observation.
 u64 old_alloc=0,new_alloc=0,old_bytes=0,new_bytes=0;
 for(u32 count: {0u,1u,2u,8u,64u,256u}){
  deferred_subresource desc{};desc.address=0x200000+count*4096;desc.width=32;desc.height=32;desc.depth=1;desc.mipmaps=1;desc.gcm_format=0x85;desc.op=deferred_request_command::atlas_gather;
  desc.cache_range=address_range32::start_length(desc.address,4096);desc.sections_to_copy.resize(count);
  old.fail=now.fail=false;
  observe_arrays=true;array_allocations=array_bytes=0;old.create_temporary_subresource(cmd,desc);old_alloc+=array_allocations;old_bytes+=array_bytes;
  array_allocations=array_bytes=0;now.create_temporary_subresource(cmd,desc);new_alloc+=array_allocations;new_bytes+=array_bytes;observe_arrays=false;
  same();
 }
 assert(old_alloc>0&&new_alloc==0);
 std::cout<<"{\"checks\":"<<checks<<",\"sameHitsCopiesUpdatesReleases\":true,\"baselineRecipeCopyAllocations\":"<<old_alloc<<",\"candidateRecipeCopyAllocations\":"<<new_alloc<<",\"baselineRecipeCopyBytes\":"<<old_bytes<<",\"candidateRecipeCopyBytes\":"<<new_bytes<<",\"baselineValueBytes\":"<<sizeof(decltype(old.m_temporary_subresource_cache)::value_type)<<",\"candidateValueBytes\":"<<sizeof(decltype(now.m_temporary_subresource_cache)::value_type)<<"}";
}
