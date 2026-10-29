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
#include <memory>
#include <mutex>
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
namespace rsx {
template<class T>using reverse_pointer=std::reverse_iterator<T*>;
namespace aligned_allocator {
template<size_t>void* malloc(size_t n){return std::malloc(n);}
template<size_t>void* realloc(void* p,size_t,size_t n){return std::realloc(p,n);}
inline void free(void* p){std::free(p);}
}
}
@ARRAY@
@ATTRIBUTES@
constexpr u32 CELL_GCM_TEXTURE_REMAP_ZERO=0,CELL_GCM_TEXTURE_REMAP_ONE=1,CELL_GCM_TEXTURE_REMAP_REMAP=2,RSX_TEXTURE_REMAP_IDENTITY=0xAAE4;
namespace rsx {@REMAP@}
using rsx::texture_channel_remap_t;
using VkDevice=int;using VkImage=u64;using VkFormat=u32;using VkComponentSwizzle=u32;using VkImageAspectFlags=u32;using VkImageViewType=u32;
constexpr u32 VK_COMPONENT_SWIZZLE_IDENTITY=0,VK_COMPONENT_SWIZZLE_ZERO=1,VK_COMPONENT_SWIZZLE_ONE=2,VK_COMPONENT_SWIZZLE_R=3,VK_COMPONENT_SWIZZLE_G=4,VK_COMPONENT_SWIZZLE_B=5,VK_COMPONENT_SWIZZLE_A=6;
constexpr u32 VK_IMAGE_ASPECT_COLOR_BIT=1,VK_IMAGE_ASPECT_DEPTH_BIT=2,VK_IMAGE_VIEW_TYPE_MAX_ENUM=~0u;
struct VkComponentMapping{u32 r,g,b,a;bool operator==(const VkComponentMapping&)const=default;};
struct VkImageSubresourceRange{u32 aspectMask,baseMipLevel,levelCount,baseArrayLayer,layerCount;bool operator==(const VkImageSubresourceRange&)const=default;};
inline u64 constructed_views=0,destroyed_views=0;
namespace vk {
constexpr u32 VK_REMAP_IDENTITY=0xCAFEBABE;
struct command_buffer{};
struct image {
 u64 value=1;
 struct {u32 format=37,mipLevels=1,arrayLayers=1;} info;
 VkComponentMapping native_component_map{VK_COMPONENT_SWIZZLE_R,VK_COMPONENT_SWIZZLE_G,VK_COMPONENT_SWIZZLE_B,VK_COMPONENT_SWIZZLE_A};
 u32 aspect_mask=VK_IMAGE_ASPECT_COLOR_BIT;
 u32 aspect()const{return aspect_mask;}
 u32 format()const{return info.format;}
};
struct image_view {
 struct {VkImage image;VkFormat format;VkImageViewType viewType;VkComponentMapping components;VkImageSubresourceRange subresourceRange;} info;
 VkDevice m_device;vk::image* m_resource=nullptr;image_view* m_root_view=nullptr;
 std::unordered_map<VkFormat,std::unique_ptr<image_view>>m_subviews;
 image_view(VkDevice dev,vk::image* resource,VkFormat format,VkImageViewType type,VkComponentMapping mapping,VkImageSubresourceRange range):info{resource->value,format,type,mapping,range},m_device(dev),m_resource(resource){++constructed_views;}
 image_view(VkDevice dev,VkImage image,VkImageViewType type,VkFormat format,VkComponentMapping mapping,VkImageSubresourceRange range):info{image,format,type,mapping,range},m_device(dev){++constructed_views;}
 ~image_view(){++destroyed_views;}
 vk::image* image()const{return m_resource;}
 VkFormat format()const{return info.format;}
 image_view* as(VkFormat format);
};
struct viewable_image:image {
 std::unordered_map<u64,std::unique_ptr<image_view>> views;
 u64 m_last_view_key=0;image_view* m_last_view=nullptr;
 image_view* get_view(const texture_channel_remap_t&,VkImageAspectFlags=VK_IMAGE_ASPECT_COLOR_BIT|VK_IMAGE_ASPECT_DEPTH_BIT);
 void set_native_component_layout(VkComponentMapping);
};
inline int device=1;inline int* g_render_device=&device;
struct GC {template<class T>void dispose(std::unique_ptr<T>& p){p.reset();}};
inline GC* get_resource_manager(){static GC gc;return &gc;}
@APPLY_REMAP@
@GET_VIEW@
@AS@
@SET_LAYOUT@
}
enum class deferred_request_command:u32{nop,copy_image_static,copy_image_dynamic,cubemap_gather,cubemap_unwrap,atlas_gather,_3d_gather,_3d_unwrap,mipmap_gather,blit_image_static};
struct copy_region_descriptor{void*src;u32 xform,base_addr;u8 level;u16 src_x,src_y,dst_x,dst_y,dst_z,src_w,src_h,dst_w,dst_h;};
using image_resource_type=vk::image*;using image_view_type=vk::image_view*;using commandbuffer_type=vk::command_buffer;
@DESCRIPTOR@
struct Boundary {
 std::mutex m_cache_mutex;
 std::vector<image_view_type>m_uncached_subresources;
 std::unordered_map<vk::image*,std::unique_ptr<vk::viewable_image>>owned;
 std::vector<std::unique_ptr<vk::viewable_image>>pool;
 u64 allocations=0,releases=0,updates=0,copies=0;bool fail=false;u32 aspects=VK_IMAGE_ASPECT_COLOR_BIT;
 VkComponentMapping native{VK_COMPONENT_SWIZZLE_R,VK_COMPONENT_SWIZZLE_G,VK_COMPONENT_SWIZZLE_B,VK_COMPONENT_SWIZZLE_A};
 image_view_type create(commandbuffer_type&,const deferred_subresource& desc){
  if(fail)return nullptr;
  auto image=pool.empty()?std::make_unique<vk::viewable_image>():std::move(pool.back());if(!pool.empty())pool.pop_back();
  image->aspect_mask=aspects;image->info.mipLevels=desc.mipmaps;image->info.arrayLayers=desc.depth;image->set_native_component_layout(native);
  auto* result=image->get_view(desc.remap);auto* key=image.get();owned.emplace(key,std::move(image));++allocations;++copies;return result;
 }
 void update_image_contents(commandbuffer_type&,image_view_type view,const deferred_subresource&){assert(owned.contains(view->image()));++updates;++copies;}
 void release_temporary_subresource(image_view_type view){auto it=owned.find(view->image());assert(it!=owned.end());pool.push_back(std::move(it->second));owned.erase(it);++releases;}
 image_view_type generate_cubemap_from_images(commandbuffer_type& c,const deferred_subresource& d){return create(c,d);}
 image_view_type generate_3d_from_2d_images(commandbuffer_type& c,const deferred_subresource& d){return create(c,d);}
 image_view_type generate_atlas_from_images(commandbuffer_type& c,const deferred_subresource& d){return create(c,d);}
 image_view_type create_temporary_subresource_view(commandbuffer_type& c,const deferred_subresource& d){return create(c,d);}
 image_view_type generate_2d_mipmaps_from_images(commandbuffer_type& c,const deferred_subresource& d){return create(c,d);}
 void expand_cube_unwrap_sections(rsx::simple_array<copy_region_descriptor>& out,const deferred_subresource& d){out=d.sections_to_copy;}
 void expand_3d_unwrap_sections(rsx::simple_array<copy_region_descriptor>& out,const deferred_subresource& d,int){out=d.sections_to_copy;}
};
struct CommonCache:Boundary {
 @KEY@
 std::unordered_multimap<u32,std::pair<temporary_subresource_key,image_view_type>>m_temporary_subresource_cache;
 @LOOKUP@
 @INVALIDATE@
 @CLEAR_UNCACHED@
 @CLEAR@
 ~CommonCache(){clear();assert(owned.empty());assert(allocations==releases);}
};
namespace vk {
class texture_cache:public CommonCache {
 using baseclass=CommonCache;
public:
 image_view* create_temporary_subresource(command_buffer&,deferred_subresource&);
};
@WRAPPER@
}
VkComponentMapping expected(const texture_channel_remap_t& r,VkComponentMapping native){
 // Independent scalar oracle in ARGB order; never calls production remap().
 std::array<u32,4>input{native.a,native.r,native.g,native.b},output{};
 for(u32 i=0;i<4;++i)output[i]=r.control_map[i]==0?VK_COMPONENT_SWIZZLE_ZERO:r.control_map[i]==1?VK_COMPONENT_SWIZZLE_ONE:input[r.channel_map[i]];
 return {output[1],output[2],output[3],output[0]};
}
u64 checks=0,baseline_wrong=0,remaps=0;
int main(){
 commandbuffer_type cmd;
 for(u32 aspect:{VK_IMAGE_ASPECT_COLOR_BIT,VK_IMAGE_ASPECT_DEPTH_BIT})for(u32 op=1;op<=9;++op){
  CommonCache old;vk::texture_cache now;old.aspects=now.aspects=aspect;
  deferred_subresource d{};d.address=0x100000;d.cache_range=address_range32::start_length(d.address,4096);d.width=32;d.height=32;d.depth=op==3?6:1;d.mipmaps=3;d.gcm_format=0x85;d.op=static_cast<deferred_request_command>(op);d.remap=rsx::decode_remap_encoding(RSX_TEXTURE_REMAP_IDENTITY);
  auto* a=old.create_temporary_subresource(cmd,d);auto* b=now.create_temporary_subresource(cmd,d);auto* owner=b->image();
  for(u32 controls=0;controls<81;++controls)for(u32 channels=0;channels<256;++channels){
   u32 packed=0,t=controls;for(u32 n=0;n<4;++n){packed|=(t%3)<<(8+n*2);t/=3;}
   d.remap=rsx::decode_remap_encoding(packed|channels);
   a=old.create_temporary_subresource(cmd,d);b=now.create_temporary_subresource(cmd,d);
   auto oracle=expected(d.remap,b->image()->native_component_map);
   baseline_wrong+=a->info.components!=oracle;
   assert(b->info.components==oracle&&b->image()==owner);assert(b->info.subresourceRange.aspectMask==aspect&&b->info.subresourceRange.levelCount==3&&b->info.subresourceRange.layerCount==d.depth);
   auto views=constructed_views;assert(now.create_temporary_subresource(cmd,d)==b&&constructed_views==views);old.create_temporary_subresource(cmd,d);
   assert(old.allocations==1&&now.allocations==1&&old.copies==now.copies);++checks;++remaps;
  }
  assert(now.updates==(op==2?20736u*2:0));
  old.notify_surface_changed(address_range32::start_length(d.address+128,32));now.notify_surface_changed(address_range32::start_length(d.address+128,32));
  assert(old.owned.empty()&&now.owned.empty()&&old.releases==1&&now.releases==1);++checks;
 }
 {
  vk::texture_cache cache;deferred_subresource d{};d.address=0x800000;d.width=4;d.height=4;d.depth=1;d.mipmaps=1;d.gcm_format=0x85;d.op=deferred_request_command::copy_image_dynamic;d.remap=rsx::decode_remap_encoding(RSX_TEXTURE_REMAP_IDENTITY);d.cache_range=address_range32::start_length(d.address,128);
  auto* first=cache.create_temporary_subresource(cmd,d);auto* owner=first->image();
  // An existing format subview must retain that format while its new component
  // view is selected; one owned image and the existing as() subview cache suffice.
  cache.m_temporary_subresource_cache.begin()->second.second=first->as(72);
  for(u32 bits:{0xAAE4u,0xAA1Bu,0u,0x5555u,0xAAE4u}){
   d.remap=rsx::decode_remap_encoding(bits);auto* view=cache.create_temporary_subresource(cmd,d);assert(view->format()==72&&view->image()==owner&&view->info.components==expected(d.remap,owner->native_component_map));
   auto views=constructed_views;assert(cache.create_temporary_subresource(cmd,d)==view&&constructed_views==views);++checks;
  }
  assert(cache.allocations==1&&cache.updates==10&&cache.copies==11);
  cache.clear();assert(cache.releases==1&&cache.owned.empty());
  cache.native={VK_COMPONENT_SWIZZLE_A,VK_COMPONENT_SWIZZLE_B,VK_COMPONENT_SWIZZLE_G,VK_COMPONENT_SWIZZLE_R};
  auto* recycled=cache.create_temporary_subresource(cmd,d);assert(recycled->image()==owner&&recycled->info.components==expected(d.remap,cache.native));++checks;
  cache.clear();assert(cache.releases==2&&cache.owned.empty());
  d.do_not_cache=true;
  for(u32 bits:{0xAAE4u,0xAA1Bu,0u,0x5555u}){d.remap=rsx::decode_remap_encoding(bits);auto* view=cache.create_temporary_subresource(cmd,d);assert(view&&view->info.components==expected(d.remap,view->image()->native_component_map));++checks;}
  assert(cache.m_temporary_subresource_cache.empty()&&cache.m_uncached_subresources.size()==4);
  cache.clear();assert(cache.allocations==cache.releases);
  cache.fail=true;assert(!cache.create_temporary_subresource(cmd,d));++checks;
 }
 assert(constructed_views==destroyed_views&&baseline_wrong>0);
 std::cout<<"{\"checks\":"<<checks<<",\"remapRequests\":"<<remaps<<",\"baselineWrongMappings\":"<<baseline_wrong<<",\"candidateWrongMappings\":0,\"sameImageAllocationsAndPayloadCopies\":true,\"repeatViewAllocations\":0,\"formatAndSubresourcesPreserved\":true,\"poolNativeMappingRefresh\":true,\"viewsConstructed\":"<<constructed_views<<",\"viewsDestroyed\":"<<destroyed_views<<",\"invalidationAndFrameReleaseOnce\":true}";
}
