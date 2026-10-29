#include <algorithm>
#include <array>
#include <cassert>
#include <chrono>
#include <concepts>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <iostream>
#include <iterator>
#include <list>
#include <memory>
#include <new>
#include <string>
#include <type_traits>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>
using u8=std::uint8_t;using u16=std::uint16_t;using u32=std::uint32_t;using u64=std::uint64_t;using usz=std::size_t;
#define ensure(x,...) assert(x)
#define AUDIT(x) assert(x)
template<class C>u32 size32(const C& c){return static_cast<u32>(c.size());}
template<class T>concept UnsignedInt=std::is_unsigned_v<T>;
namespace fmt {template<class...T>[[noreturn]]void throw_exception(const char*,T...){std::abort();}}
inline bool count_allocations=false;inline u64 allocation_calls=0;
[[gnu::noinline]] void* operator new(std::size_t n){if(count_allocations)++allocation_calls;if(void* p=std::malloc(n?n:1))return p;throw std::bad_alloc();}
[[gnu::noinline]] void operator delete(void* p) noexcept {std::free(p);}
[[gnu::noinline]] void operator delete(void* p,std::size_t) noexcept {std::free(p);}
constexpr u32 CELL_GCM_TEXTURE_REMAP_ZERO=0,CELL_GCM_TEXTURE_REMAP_ONE=1,CELL_GCM_TEXTURE_REMAP_REMAP=2,RSX_TEXTURE_REMAP_IDENTITY=0xAAE4;
@GCM_ENUM@
@DEPTH_CONSTANTS@
namespace rsx {
template<class T>using reverse_pointer=std::reverse_iterator<T*>;
namespace aligned_allocator {
template<size_t>void* malloc(size_t n){if(count_allocations)++allocation_calls;return std::malloc(n);}
template<size_t>void* realloc(void* p,size_t,size_t n){if(count_allocations)++allocation_calls;return std::realloc(p,n);}
inline void free(void* p){std::free(p);}
}
}
@ARRAY@
namespace rsx {
@DEPTH_ENUM@
@CLASS_ENUM@
@ORDER_ENUM@
@REMAP@
inline auto default_remap_vector=decode_remap_encoding(RSX_TEXTURE_REMAP_IDENTITY);
@CLASSIFY@
@DEPTH_COMPATIBLE@
}
using namespace rsx;
using VkDevice=int;using VkImage=u64;using VkFormat=u32;using VkComponentSwizzle=u32;using VkImageAspectFlags=u32;using VkImageViewType=u32;using VkImageType=u32;using VkImageCreateFlags=u32;using VkImageUsageFlags=u32;using VkSharingMode=u32;using VkFlags=u32;
constexpr u32 VK_COMPONENT_SWIZZLE_IDENTITY=0,VK_COMPONENT_SWIZZLE_ZERO=1,VK_COMPONENT_SWIZZLE_ONE=2,VK_COMPONENT_SWIZZLE_R=3,VK_COMPONENT_SWIZZLE_G=4,VK_COMPONENT_SWIZZLE_B=5,VK_COMPONENT_SWIZZLE_A=6;
constexpr u32 VK_IMAGE_ASPECT_COLOR_BIT=1,VK_IMAGE_ASPECT_DEPTH_BIT=2,VK_IMAGE_VIEW_TYPE_MAX_ENUM=~0u,VK_IMAGE_LAYOUT_GENERAL=1,VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL=2,VK_IMAGE_TYPE_2D=1,VK_IMAGE_TYPE_3D=2;
constexpr u32 VK_IMAGE_USAGE_TRANSFER_SRC_BIT=1,VK_IMAGE_USAGE_TRANSFER_DST_BIT=2,VK_IMAGE_USAGE_SAMPLED_BIT=4,VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT=1,VK_SAMPLE_COUNT_1_BIT=1,VK_IMAGE_LAYOUT_UNDEFINED=0,VK_IMAGE_TILING_OPTIMAL=0,VMM_ALLOCATION_POOL_TEXTURE_CACHE=0,VK_IMAGE_CREATE_ALLOW_NULL_RPCS3=0x80000000,VK_SHARING_MODE_EXCLUSIVE=0;
struct VkComponentMapping{u32 r,g,b,a;bool operator==(const VkComponentMapping&)const=default;};
struct VkImageSubresourceRange{u32 aspectMask,baseMipLevel,levelCount,baseArrayLayer,layerCount;bool operator==(const VkImageSubresourceRange&)const=default;};
inline u64 constructed_views=0,destroyed_views=0;
namespace vk {
constexpr u32 VK_REMAP_IDENTITY=0xCAFEBABE;
struct command_buffer{u64 pushes=0,pops=0,copies=0,push_digest=0,copy_digest=0;};
struct memory_block {u64 size()const{return 4096;}};
struct image {
 u64 value=1;
 struct {u32 format=37,mipLevels=1,arrayLayers=1,width=512,height=512,depth=1,imageType=2,flags=0,sharingMode=0,usage=3;} info;
 VkComponentMapping native_component_map{VK_COMPONENT_SWIZZLE_R,VK_COMPONENT_SWIZZLE_G,VK_COMPONENT_SWIZZLE_B,VK_COMPONENT_SWIZZLE_A};
 u32 aspect_mask=VK_IMAGE_ASPECT_COLOR_BIT;
 u32 aspect()const{return aspect_mask;}u32 format()const{return info.format;}
 u32 width()const{return info.width;}u32 height()const{return info.height;}
 u32 depth()const{return info.depth;}u32 mipmaps()const{return info.mipLevels;}
 u32 type()const{return info.imageType;}u32 layers()const{return info.arrayLayers;}
 rsx::format_class image_class=RSX_FORMAT_CLASS_COLOR;
 rsx::format_class format_class()const{return image_class;}
 std::unique_ptr<memory_block>memory=std::make_unique<memory_block>();
 u32 identity=0,current_layout=3,saved_layout=0,push_count=0,pop_count=0,copy_count=0;
 void push_layout(command_buffer& cmd,u32 layout){assert(!saved_layout);saved_layout=current_layout;current_layout=layout;++push_count;++cmd.pushes;cmd.push_digest=cmd.push_digest*31+identity;}
 void pop_layout(command_buffer& cmd){assert(saved_layout);current_layout=saved_layout;saved_layout=0;++pop_count;++cmd.pops;}
 void copy(command_buffer& cmd){assert(saved_layout&&current_layout==(saved_layout==VK_IMAGE_LAYOUT_GENERAL?VK_IMAGE_LAYOUT_GENERAL:VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL));++copy_count;++cmd.copies;cmd.copy_digest=cmd.copy_digest*31+identity;}
};
struct image_view {
 struct {VkImage image;VkFormat format;VkImageViewType viewType;VkComponentMapping components;VkImageSubresourceRange subresourceRange;} info;
 VkDevice m_device;vk::image* m_resource=nullptr;image_view* m_root_view=nullptr;
 std::unordered_map<VkFormat,std::unique_ptr<image_view>>m_subviews;
 image_view(VkDevice dev,vk::image* resource,VkFormat format,VkImageViewType type,VkComponentMapping mapping,VkImageSubresourceRange range):info{resource->value,format,type,mapping,range},m_device(dev),m_resource(resource){++constructed_views;}
 image_view(VkDevice dev,VkImage image,VkImageViewType type,VkFormat format,VkComponentMapping mapping,VkImageSubresourceRange range):info{image,format,type,mapping,range},m_device(dev){++constructed_views;}
 ~image_view(){++destroyed_views;}
 vk::image* image()const{return m_resource;}VkFormat format()const{return info.format;}
 image_view* as(VkFormat format);
};
struct viewable_image:image {
 viewable_image()=default;
 viewable_image(int,int,u32,u32 type,u32 format,u32 w,u32 h,u32 d,u32 m,u32 layers,u32,u32,u32,u32 usage,u32 flags,u32,rsx::format_class c){info.imageType=type;info.format=format;info.width=w;info.height=h;info.depth=d;info.mipLevels=m;info.arrayLayers=layers;info.usage=usage;info.flags=flags&~VK_IMAGE_CREATE_ALLOW_NULL_RPCS3;image_class=c;}
 std::unordered_map<u64,std::unique_ptr<image_view>> views;
 u64 m_last_view_key=0;image_view* m_last_view=nullptr;
 image_view* get_view(const texture_channel_remap_t&,VkImageAspectFlags=VK_IMAGE_ASPECT_COLOR_BIT|VK_IMAGE_ASPECT_DEPTH_BIT);
 void set_native_component_layout(VkComponentMapping);
};
inline int device=1;inline int* g_render_device=&device;
inline int* get_current_renderer(){return g_render_device;}
struct GC {std::vector<std::unique_ptr<image_view>>retired;void dispose(std::unique_ptr<image_view>& p){retired.push_back(std::move(p));}};
inline GC* get_resource_manager(){static GC gc;return &gc;}
@COMPONENTS@
@APPLY_REMAP@
@APPLY_FLAGS@
@GET_VIEW@
@AS@
@SET_LAYOUT@
@HASH@
void initialize_before(viewable_image* image,u32 gcm_format,rsx::component_order swizzle_flags){@BEFORE_NATIVE@}
void initialize_after(viewable_image* image,u32 gcm_format,rsx::component_order swizzle_flags){@AFTER_NATIVE@}
struct render_target {
 bool depth_surface;rsx::surface_depth_format2 format;
 bool is_depth_surface()const{return depth_surface;}
 rsx::surface_depth_format2 get_surface_depth_format()const{return format;}
 u32 get_surface_color_format()const{return CELL_GCM_TEXTURE_A8R8G8B8;}
};
std::pair<u32,bool>get_compatible_gcm_format(u32 format){return{format,false};}
struct section_boundary {
 u32 captured_format=0;bool captured_swap=false;image*captured_image=nullptr;std::array<u32,6> dimensions{};
 void create(u16 w,u16 h,u16 d,u16 m,image* im,u32 pitch,bool managed,u32 format,bool swap){captured_format=format;captured_swap=swap;captured_image=im;dimensions={w,h,d,m,pitch,managed};}
};
struct before_section:section_boundary {using section_boundary::create;@BEFORE_DEPTH@};
struct after_section:section_boundary {using section_boundary::create;@AFTER_DEPTH@};
// The pool's synchronization boundary checks one upgrade, balanced destruction
// and no removal under a reader lock. Actual driver retirement is unchanged.
struct reader_lock {int& state;explicit reader_lock(int& s):state(s){assert(!s);s=1;}void upgrade(){assert(state==1);state=2;}~reader_lock(){state=0;}};
struct entry {u64 key;std::unique_ptr<viewable_image>data;};
struct pool_boundary {
 int m_cached_pool_lock=0;std::list<entry>m_cached_images;u64 m_cached_memory_size=0;
 void put(u32 d,u32 m,rsx::format_class c){auto im=std::make_unique<viewable_image>();im->info.depth=d;im->info.mipLevels=m;im->image_class=c;const u64 key=hash_image_properties(im->format(),im->width(),im->height(),im->depth(),im->mipmaps(),im->info.imageType,im->info.flags,im->info.sharingMode);m_cached_images.push_back({key,std::move(im)});m_cached_memory_size+=4096;}
};
struct before_pool:pool_boundary {@BEFORE_POOL_DECL@};
struct after_pool:pool_boundary {@AFTER_POOL_DECL@};
@BEFORE_POOL@
@AFTER_POOL@
struct before_storage:before_pool {struct{int device_local=0;}m_memory_types;@BEFORE_STORAGE@};
struct after_storage:after_pool {struct{int device_local=0;}m_memory_types;@AFTER_STORAGE@};
struct copy_region_descriptor{image* src;u32 level=0,src_w=1,src_h=1,dst_x=0,dst_y=0,dst_z=0,dst_w=1,dst_h=1;};
@BEFORE_COPY@
@AFTER_COPY@
@FULL_COVERAGE@
}
VkComponentMapping oracle(const texture_channel_remap_t& r,VkComponentMapping native){
 std::array<u32,4>input{native.a,native.r,native.g,native.b},output{};
 for(u32 i=0;i<4;++i)output[i]=r.control_map[i]==0?VK_COMPONENT_SWIZZLE_ZERO:r.control_map[i]==1?VK_COMPONENT_SWIZZLE_ONE:input[r.channel_map[i]];
 return {output[1],output[2],output[3],output[0]};
}
u64 native_checks=0,native_wrong=0,pool_checks=0,pool_wrong=0,depth_checks=0,depth_wrong=0,copy_checks=0,coverage_checks=0,clear_eliminated=0,storage_checks=0,storage_wrong=0;
void test_views(){
 for(u32 controls=0;controls<81;++controls)for(u32 channels=0;channels<256;++channels){
  u32 packed=0,t=controls;for(u32 n=0;n<4;++n){packed|=(t%3)<<(8+n*2);t/=3;}
  auto remap=rsx::decode_remap_encoding(packed|channels);
  vk::viewable_image old,now;old.info.mipLevels=now.info.mipLevels=5;old.info.arrayLayers=now.info.arrayLayers=6;
  vk::initialize_before(&old,CELL_GCM_TEXTURE_A8R8G8B8,component_order::default_);vk::initialize_after(&now,CELL_GCM_TEXTURE_A8R8G8B8,component_order::default_);
  auto* original=now.get_view(remap);auto* original_sub=original->as(72);old.get_view(remap);
  auto original_mapping=original->info.components;
  vk::initialize_before(&old,CELL_GCM_TEXTURE_D8R8G8B8,component_order::default_);vk::initialize_after(&now,CELL_GCM_TEXTURE_D8R8G8B8,component_order::default_);
  auto* view=now.get_view(remap);auto expected=oracle(remap,{VK_COMPONENT_SWIZZLE_R,VK_COMPONENT_SWIZZLE_G,VK_COMPONENT_SWIZZLE_B,VK_COMPONENT_SWIZZLE_ONE});
  native_wrong+=old.get_view(remap)->info.components!=expected;
  assert(view->info.components==expected&&view->image()==&now&&view->info.subresourceRange.levelCount==5&&view->info.subresourceRange.layerCount==6);
  assert(view->as(72)->info.components==expected);
  // Old descriptors stay alive until the resource manager retires their scope.
  assert(original->info.components==original_mapping&&original_sub->format()==72);
  auto total=constructed_views;vk::initialize_after(&now,CELL_GCM_TEXTURE_D8R8G8B8,component_order::default_);
  assert(now.get_view(remap)==view&&constructed_views==total);
  vk::initialize_after(&now,CELL_GCM_TEXTURE_A8R8G8B8,component_order::default_);
  assert(now.get_view(remap)->info.components==original_mapping);
  vk::get_resource_manager()->retired.clear();++native_checks;
 }
 // Explicit order changes and depth native mapping use the same production path.
 vk::viewable_image now;
 for(auto order:{component_order::native,component_order::swapped_native,component_order::default_}){
  vk::initialize_after(&now,CELL_GCM_TEXTURE_A8R8G8B8,order);auto* v=now.get_view(rsx::default_remap_vector);
  auto expected=order==component_order::swapped_native?VkComponentMapping{6,3,4,5}:VkComponentMapping{3,4,5,6};
  assert(v->info.components==expected);++native_checks;
 }
 vk::get_resource_manager()->retired.clear();
}
void test_pool(){
 const std::array<rsx::format_class,5> classes{RSX_FORMAT_CLASS_COLOR,RSX_FORMAT_CLASS_DEPTH16_UNORM,RSX_FORMAT_CLASS_DEPTH16_FLOAT,RSX_FORMAT_CLASS_DEPTH24_UNORM_X8_PACK32,RSX_FORMAT_CLASS_DEPTH24_FLOAT_X8_PACK32};
 for(u32 depth:{1,2,16,128,256,512})for(u32 wanted_d:{1,2,16,128,256,512})for(u32 stored_m=1;stored_m<=10;++stored_m)for(u32 wanted_m=1;wanted_m<=10;++wanted_m)for(auto stored:classes)for(auto wanted:classes){
  vk::before_pool old;vk::after_pool now;old.put(depth,stored_m,stored);now.put(depth,stored_m,stored);
  auto a=old.find_cached_image(37,512,512,wanted_d,wanted_m,2,0,3,0);
  auto b=now.find_cached_image(37,512,512,wanted_d,wanted_m,2,0,3,0,wanted);
  const bool expected=depth==wanted_d&&stored_m==wanted_m&&stored==wanted;
  pool_wrong+=bool(a)!=expected;assert(bool(b)==expected);
  assert(now.m_cached_memory_size==(expected?0:4096)&&now.m_cached_images.size()==(expected?0:1));assert(!now.m_cached_pool_lock);
  if(b)assert(b->depth()==depth&&b->mipmaps()==wanted_m&&b->format_class()==wanted);
  ++pool_checks;
 }
 // Missing entries and unsupported usages cannot change pool accounting.
 vk::after_pool pool;assert(!pool.find_cached_image(37,512,512,1,1,2,0,1,0,RSX_FORMAT_CLASS_COLOR));
 pool.put(1,1,RSX_FORMAT_CLASS_COLOR);
 assert(!pool.find_cached_image(37,512,512,1,1,2,0,4,0,RSX_FORMAT_CLASS_COLOR)&&pool.m_cached_memory_size==4096);
 assert(!pool.find_cached_image(37,512,512,1,1,2,0,1,1,RSX_FORMAT_CLASS_COLOR)&&pool.m_cached_memory_size==4096);
 // Two images with the same VkFormat but different PS3 depth interpretation.
 assert(rsx::classify_format(CELL_GCM_TEXTURE_DEPTH24_D8)!=rsx::classify_format(CELL_GCM_TEXTURE_DEPTH24_D8_FLOAT));
 vk::after_pool mixed;mixed.put(1,1,RSX_FORMAT_CLASS_DEPTH24_UNORM_X8_PACK32);mixed.put(1,1,RSX_FORMAT_CLASS_DEPTH24_FLOAT_X8_PACK32);
 auto f=mixed.find_cached_image(37,512,512,1,1,2,0,1,0,RSX_FORMAT_CLASS_DEPTH24_FLOAT_X8_PACK32);assert(f&&f->format_class()==RSX_FORMAT_CLASS_DEPTH24_FLOAT_X8_PACK32&&mixed.m_cached_memory_size==4096);
 auto n=mixed.find_cached_image(37,512,512,1,1,2,0,1,0,RSX_FORMAT_CLASS_DEPTH24_UNORM_X8_PACK32);assert(n&&n->format_class()==RSX_FORMAT_CLASS_DEPTH24_UNORM_X8_PACK32&&!mixed.m_cached_memory_size);
 pool_checks+=5;
}
// Independent payload model: paint individual destination texels over stale
// pooled bytes. A skipped clear must give the same bytes as clearing first.
void check_coverage(vk::image& dst,const rsx::simple_array<vk::copy_region_descriptor>& sections){
 const bool skip=vk::copy_transfer_regions_fully_cover_image(&dst,sections);
 if(skip){
  for(u32 level=0;level<dst.mipmaps();++level){
   const u32 w=std::max(1u,dst.width()>>level),h=std::max(1u,dst.height()>>level);
   const u32 slices=dst.type()==VK_IMAGE_TYPE_3D?std::max(1u,dst.depth()>>level):dst.layers();
   std::vector<u32>old(w*h*slices,0),now(w*h*slices,0xfeed);
   u32 value=0;
   for(const auto& s:sections){++value;if(!s.src||s.level!=level)continue;
    for(u32 y=s.dst_y;y<s.dst_y+s.dst_h;++y)for(u32 x=s.dst_x;x<s.dst_x+s.dst_w;++x){assert(x<w&&y<h&&s.dst_z<slices);old[(s.dst_z*h+y)*w+x]=now[(s.dst_z*h+y)*w+x]=value;}
   }
   assert(old==now);
  }
  ++clear_eliminated;
 }
 ++coverage_checks;
}
void test_coverage(){
 vk::image src,depth_src;depth_src.aspect_mask=VK_IMAGE_ASPECT_DEPTH_BIT;
 for(u32 type:{VK_IMAGE_TYPE_2D,VK_IMAGE_TYPE_3D})for(u32 width:{1,3,8,17})for(u32 height:{1,4,9})for(u32 depth:{1,2,7})for(u32 mips:{1,2,4}){
  vk::image dst;dst.info.width=width;dst.info.height=height;dst.info.depth=depth;dst.info.imageType=type;dst.info.arrayLayers=type==VK_IMAGE_TYPE_2D?6:1;dst.info.mipLevels=mips;
  rsx::simple_array<vk::copy_region_descriptor>full;
  for(u32 level=0;level<mips;++level)for(u32 z=0;z<(type==VK_IMAGE_TYPE_3D?std::max(1u,depth>>level):6);++z){
   vk::copy_region_descriptor s{&src};s.level=level;s.dst_z=z;s.src_w=s.dst_w=std::max(1u,width>>level);s.src_h=s.dst_h=std::max(1u,height>>level);full.push_back(s);
  }
  assert(vk::copy_transfer_regions_fully_cover_image(&dst,full));check_coverage(dst,full);
  auto reversed=full;std::reverse(reversed.begin(),reversed.end());check_coverage(dst,reversed);
  for(u32 mutation=0;mutation<13;++mutation){
   auto partial=full;
   switch(mutation){
   case 0:partial.resize(partial.size()-1);break;
   case 1:if(partial.size()>1)partial.back()=partial.front();else partial.clear();break;
   case 2:partial.front().src=nullptr;break;
   case 3:partial.front().src=&depth_src;break;
   case 4:partial.front().src_w=0;break;
   case 5:partial.front().src_h=0;break;
   case 6:partial.front().level=mips;break;
   case 7:partial.front().dst_x=1;break;
   case 8:partial.front().dst_y=1;break;
   case 9:++partial.front().dst_w;break;
   case 10:++partial.front().dst_h;break;
   case 11:partial.front().dst_z=2048;break;
   case 12:partial.front().dst_w=0;break;
   }
   assert(!vk::copy_transfer_regions_fully_cover_image(&dst,partial));check_coverage(dst,partial);
  }
  full.push_back(full.front());assert(vk::copy_transfer_regions_fully_cover_image(&dst,full));check_coverage(dst,full);
  dst.aspect_mask=VK_IMAGE_ASPECT_DEPTH_BIT;assert(!vk::copy_transfer_regions_fully_cover_image(&dst,full));++coverage_checks;
 }
 // The coverage bitmap's bound is conservative, including 512-deep images
 // with long mipchains and boundaries at 64, 1024 and 2048 slices.
 for(u32 depth:{64,512,1024,2048,2049})for(u32 mips:{1,10,16,17}){
  vk::image dst;dst.info.width=dst.info.height=1;dst.info.depth=depth;dst.info.mipLevels=mips;dst.info.imageType=VK_IMAGE_TYPE_3D;
  rsx::simple_array<vk::copy_region_descriptor>sections;u32 total=0;
  for(u32 level=0;level<mips;++level)for(u32 z=0;z<std::max(1u,depth>>level);++z){vk::copy_region_descriptor s{&src};s.level=level;s.dst_z=z;sections.push_back(s);++total;}
  assert(vk::copy_transfer_regions_fully_cover_image(&dst,sections)==(mips<=16&&total<=2048));check_coverage(dst,sections);
 }
}
void test_depth(){
 vk::image image;
 for(bool is_depth:{false,true})for(auto format:{surface_depth_format2::z16_uint,surface_depth_format2::z24s8_uint,surface_depth_format2::z16_float,surface_depth_format2::z24s8_float}){
  vk::render_target surface{is_depth,format};vk::before_section old;vk::after_section now;
  old.create(17,23,1,3,&image,256,true,&surface);now.create(17,23,1,3,&image,256,true,&surface);
  const std::array<u32,4>expected_formats{CELL_GCM_TEXTURE_DEPTH16,CELL_GCM_TEXTURE_DEPTH24_D8,CELL_GCM_TEXTURE_DEPTH16_FLOAT,CELL_GCM_TEXTURE_DEPTH24_D8_FLOAT};
  auto expected=is_depth?expected_formats[static_cast<u32>(format)-1]:CELL_GCM_TEXTURE_A8R8G8B8;
  depth_wrong+=old.captured_format!=expected;assert(now.captured_format==expected&&now.captured_swap==is_depth&&now.captured_image==&image&&now.dimensions==old.dimensions);++depth_checks;
 }
}
void test_storage(){
 for(u32 usage=0;usage<8;++usage){
  vk::before_storage old;vk::after_storage now;
  auto a=old.create_temporary_subresource_storage(RSX_FORMAT_CLASS_COLOR,37,512,512,1,1,1,VK_IMAGE_TYPE_2D,0,usage);
  auto b=now.create_temporary_subresource_storage(RSX_FORMAT_CLASS_COLOR,37,512,512,1,1,1,VK_IMAGE_TYPE_2D,0,usage);
  auto expected=usage|VK_IMAGE_USAGE_TRANSFER_DST_BIT|VK_IMAGE_USAGE_SAMPLED_BIT;
  storage_wrong+=a->info.usage!=expected;assert(b->info.usage==expected&&b->info.flags==0&&b->mipmaps()==1&&b->layers()==1);++storage_checks;
 }
 // A pool entry satisfying caller usage but missing intrinsic DST must stay in
 // the pool; a complete superset is accepted without another image allocation.
 vk::after_storage cache;cache.put(1,1,RSX_FORMAT_CLASS_COLOR);cache.m_cached_images.back().data->info.imageType=VK_IMAGE_TYPE_2D;cache.m_cached_images.back().key=vk::hash_image_properties(37,512,512,1,1,VK_IMAGE_TYPE_2D,0,0);cache.m_cached_images.back().data->info.usage=VK_IMAGE_USAGE_TRANSFER_SRC_BIT|VK_IMAGE_USAGE_SAMPLED_BIT;
 auto rejected=cache.create_temporary_subresource_storage(RSX_FORMAT_CLASS_COLOR,37,512,512,1,1,1,VK_IMAGE_TYPE_2D,0,VK_IMAGE_USAGE_TRANSFER_SRC_BIT|VK_IMAGE_USAGE_SAMPLED_BIT);
 assert(cache.m_cached_memory_size==4096&&rejected->info.usage==7);++storage_checks;
 auto* identity=cache.m_cached_images.back().data.get();identity->info.usage=7;
 auto reused=cache.create_temporary_subresource_storage(RSX_FORMAT_CLASS_COLOR,37,512,512,1,1,1,VK_IMAGE_TYPE_2D,0,VK_IMAGE_USAGE_SAMPLED_BIT);
 assert(reused.get()==identity&&!cache.m_cached_memory_size);++storage_checks;
}
using Copy=void(*)(vk::command_buffer&,const std::vector<vk::copy_region_descriptor>&);
void reset_images(std::array<vk::image,16>& images){for(u32 i=0;i<images.size();++i){auto& image=images[i];image.identity=i+1;image.current_layout=i%2?VK_IMAGE_LAYOUT_GENERAL:3;image.saved_layout=image.push_count=image.pop_count=image.copy_count=0;}}
void test_copies(){
 std::array<vk::image,16>old,now;u32 random=1;
 for(u32 count=0;count<=64;++count)for(u32 pattern=0;pattern<200;++pattern){
  reset_images(old);reset_images(now);std::vector<vk::copy_region_descriptor>a,b;
  for(u32 n=0;n<count;++n){random=random*1664525+1013904223;u32 id=(random>>24)%18;a.push_back({id<16?&old[id]:nullptr});b.push_back({id<16?&now[id]:nullptr});}
  vk::command_buffer ca,cb;vk::before_copy(ca,a);vk::after_copy(cb,b);
  assert(ca.pushes==cb.pushes&&ca.pops==cb.pops&&ca.copies==cb.copies&&ca.push_digest==cb.push_digest&&ca.copy_digest==cb.copy_digest);
  for(u32 n=0;n<16;++n){assert(old[n].push_count==now[n].push_count&&old[n].pop_count==now[n].pop_count&&old[n].copy_count==now[n].copy_count&&old[n].current_layout==now[n].current_layout);assert(now[n].push_count<=1&&now[n].push_count==now[n].pop_count&&!now[n].saved_layout);}
  ++copy_checks;
 }
}
struct timing{double ns;u64 allocations,digest;};
timing measure(Copy fn,const std::vector<vk::copy_region_descriptor>& sections,u32 iterations){
 vk::command_buffer cmd;allocation_calls=0;count_allocations=true;
 auto start=std::chrono::steady_clock::now();for(u32 i=0;i<iterations;++i)fn(cmd,sections);auto end=std::chrono::steady_clock::now();
 count_allocations=false;return{std::chrono::duration<double,std::nano>(end-start).count()/iterations,allocation_calls,cmd.copy_digest};
}
void benchmark(){
 std::array<vk::image,16>images;reset_images(images);bool first=true;
 std::cout<<"[";
 for(u32 count:{1,2,4,8,9,32,256})for(bool repeated:{false,true}){
  std::vector<vk::copy_region_descriptor>sections;for(u32 n=0;n<count;++n)sections.push_back({&images[repeated?0:n%16]});
  const u32 iterations=30000/(1+count/16);
  std::array<double,7>old_trials{},new_trials{};timing old{},now{};
  for(u32 trial=0;trial<7;++trial){
   if(trial%2){now=measure(vk::after_copy,sections,iterations);old=measure(vk::before_copy,sections,iterations);}
   else{old=measure(vk::before_copy,sections,iterations);now=measure(vk::after_copy,sections,iterations);}
   old_trials[trial]=old.ns;new_trials[trial]=now.ns;
  }
  auto old_sorted=old_trials,new_sorted=new_trials;std::sort(old_sorted.begin(),old_sorted.end());std::sort(new_sorted.begin(),new_sorted.end());old.ns=old_sorted[3];now.ns=new_sorted[3];
  assert(old.digest==now.digest);if(count<=8)assert(now.allocations==0&&old.allocations>0);else assert(now.allocations==old.allocations);
  if(!first)std::cout<<",";
  first=false;
  std::cout<<"{\"sections\":"<<count<<",\"repeated\":"<<(repeated?"true":"false")<<",\"iterationsPerTrial\":"<<iterations<<",\"beforeMedianNs\":"<<old.ns<<",\"afterMedianNs\":"<<now.ns<<",\"beforeAllocationsPerTrial\":"<<old.allocations<<",\"afterAllocationsPerTrial\":"<<now.allocations<<",\"beforeTrialsNs\":[";
  for(u32 i=0;i<7;++i){if(i)std::cout<<",";std::cout<<old_trials[i];}std::cout<<"],\"afterTrialsNs\":[";
  for(u32 i=0;i<7;++i){if(i)std::cout<<",";std::cout<<new_trials[i];}std::cout<<"]}";
 }
 std::cout<<"]";
}
int main(){
 test_views();test_pool();test_depth();test_copies();test_coverage();test_storage();
 assert(native_wrong>0&&pool_wrong>0&&depth_wrong==4&&storage_wrong==4&&constructed_views==destroyed_views);
 std::cout<<"{\"nativeChecks\":"<<native_checks<<",\"baselineWrongNativeMappings\":"<<native_wrong<<",\"candidateWrongNativeMappings\":0,\"poolChecks\":"<<pool_checks<<",\"baselineWrongPoolSelections\":"<<pool_wrong<<",\"candidateWrongPoolSelections\":0,\"depthChecks\":"<<depth_checks<<",\"baselineWrongDepthFormats\":"<<depth_wrong<<",\"candidateWrongDepthFormats\":0,\"copyChecks\":"<<copy_checks<<",\"sameCopiesAndPerImageBarriers\":true,\"coverageChecks\":"<<coverage_checks<<",\"colorClearEliminationsInCases\":"<<clear_eliminated<<",\"sameModeledDestinationTexels\":true,\"viewsConstructed\":"<<constructed_views<<",\"viewsDestroyed\":"<<destroyed_views<<",\"copyBenchmarks\":";
 benchmark();std::cout<<",\"storageChecks\":"<<storage_checks<<",\"baselineWrongUsageFlags\":"<<storage_wrong<<",\"candidateWrongUsageFlags\":0}";
}
