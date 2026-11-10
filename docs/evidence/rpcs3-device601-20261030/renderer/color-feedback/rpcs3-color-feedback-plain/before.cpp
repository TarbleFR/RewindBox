
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdint>
#include <iostream>
#include <memory>
#include <utility>
#include <vector>
using u16=std::uint16_t;using u32=std::uint32_t;
constexpr u32 VK_IMAGE_ASPECT_COLOR_BIT=1,VK_IMAGE_ASPECT_DEPTH_BIT=2;
constexpr u32 VK_IMAGE_LAYOUT_GENERAL=1,VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL=2;
struct coord3u {u32 x,y,z,width,height,depth;};
namespace rsx {
enum class surface_access {transfer_read};enum class surface_transform {identity};
struct image_section_attributes_t {u32 address=0,gcm_format=0,width=0,height=0,depth=0;};
struct sampled_image_descriptor_base {virtual ~sampled_image_descriptor_base()=default;};
struct texture {u32 remap=7;u32 decoded_remap()const{return remap;}};
struct {std::array<texture,16>fragment_textures;}method_registers;
}
namespace vk {
enum class driver_vendor {MVK,OTHER};driver_vendor vendor=driver_vendor::MVK;
driver_vendor get_driver_vendor(){return vendor;}
struct command_buffer {};
struct viewable_image;
struct image_view {
    viewable_image* object=nullptr;u32 fmt=10;
    struct {struct {u32 aspectMask=VK_IMAGE_ASPECT_COLOR_BIT;}subresourceRange;}info;
    viewable_image* image(){return object;}
    u32 format()const{return fmt;}
    image_view* as(u32 f){fmt=f;return this;}
};
struct viewable_image {
    std::array<float,4>pixels{1,2,3,4};u32 sample_count=1,spp=1;
    u32 layout=VK_IMAGE_LAYOUT_GENERAL,saved=0;
    u32 barriers=0,pushes=0,pops=0,selected_remap=0;
    image_view view;
    viewable_image(){view.object=this;}
    u32 samples()const{return sample_count;}u32 width()const{return 4;}u32 height()const{return 1;}
    u32 get_memory_range()const{return 128;}
    void memory_barrier(command_buffer&,rsx::surface_access){++barriers;}
    void push_layout(command_buffer&,u32 l){saved=layout;layout=l;++pushes;}
    void pop_layout(command_buffer&){layout=saved;++pops;}
    image_view* get_view(u32 remap){selected_remap=remap;return &view;}
};
struct texture_cache {
    struct sampled_image_descriptor:rsx::sampled_image_descriptor_base {
        u32 ref_address=128;struct {u32 format()const{return 10;}}format_ex;
    };
    struct deferred_subresource {
        viewable_image* source=nullptr;u32 cache_range=0,remap=0;bool cyclic=false;
        rsx::image_section_attributes_t attributes;
        static deferred_subresource create_copy(viewable_image*s,const rsx::image_section_attributes_t&a,
            coord3u rect,rsx::surface_transform,u32 remap,bool cyclic){
            assert(rect.x==0&&rect.y==0&&rect.z==0&&rect.width==4&&rect.height==1&&rect.depth==1);
            return {s,0,remap,cyclic,a};
        }
    };
    viewable_image copy;u32 calls=0,allocations=0;bool fail=false;
    image_view* create_temporary_subresource(command_buffer&,const deferred_subresource&d){
        ++calls;assert(d.cyclic&&d.cache_range==128&&d.attributes.width==4&&d.attributes.height==1);
        assert(d.source->layout==VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL);
        if(fail)return nullptr;
        if(!allocations)++allocations; // explicit reusable-image adapter, not VMA execution
        copy.pixels=d.source->pixels;copy.selected_remap=d.remap;return &copy.view;
    }
};
}
struct VKGSRender {
    struct {u32 multiple_texture_reads_mask=0;}current_fp_metadata;
    struct {std::array<std::pair<u32,vk::viewable_image*>,4>m_bound_render_targets{};}m_rtts;
    std::array<std::unique_ptr<rsx::sampled_image_descriptor_base>,16>fs_sampler_state;
    vk::command_buffer cmd;vk::command_buffer*m_current_command_buffer=&cmd;
    vk::texture_cache m_texture_cache;
    VKGSRender(){fs_sampler_state[0]=std::make_unique<vk::texture_cache::sampled_image_descriptor>();}
    vk::image_view* snapshot_color_feedback(u32,vk::image_view*);
};
vk::image_view* VKGSRender::snapshot_color_feedback(u32 texture_index, vk::image_view* view)
{
	if (vk::get_driver_vendor() != vk::driver_vendor::MVK ||
		!(current_fp_metadata.multiple_texture_reads_mask & (1u << texture_index)) ||
		view->info.subresourceRange.aspectMask != VK_IMAGE_ASPECT_COLOR_BIT ||
		view->image()->samples() != 1)
	{
		return view;
	}

	for (const auto& [address, surface] : m_rtts.m_bound_render_targets)
	{
		if (!surface || surface != view->image() || surface->spp != 1)
		{
			continue;
		}

		// Neighborhood reads from an active color attachment are not ordered against
		// other fragments' writes on MoltenVK. Snapshot multi-tap shaders without
		// enabling all strict-rendering paths. Static instruction count is a conservative
		// filter for these shaders, not a general proof that single-read feedback is safe.
		// Already-separated (including strict-mode) views never match the attachment.
		surface->memory_barrier(*m_current_command_buffer, rsx::surface_access::transfer_read);
		const auto* desc = static_cast<vk::texture_cache::sampled_image_descriptor*>(fs_sampler_state[texture_index].get());
		rsx::image_section_attributes_t attrs{};
		attrs.address = desc->ref_address;
		attrs.gcm_format = desc->format_ex.format();
		attrs.width = surface->width();
		attrs.height = surface->height();
		attrs.depth = 1;

		// Preserve the full host image and the existing shader coordinate transform,
		// including cropped aliases and resolution scaling. Do not scale it again.
		const coord3u rect = { 0, 0, 0, attrs.width, attrs.height, 1 };
		const auto remap = rsx::method_registers.fragment_textures[texture_index].decoded_remap();
		auto copy = vk::texture_cache::deferred_subresource::create_copy(
			surface, attrs, rect, rsx::surface_transform::identity, remap, true);
		copy.cache_range = surface->get_memory_range();

		// Dynamic copies reuse storage but refresh on every draw. Keep the original
		// sampler descriptor so subsequent draws cannot mistake this for a static view.
		// Explicitly order prior attachment writes before the transfer even if the
		// attachment was already in GENERAL for a preceding feedback draw.
		surface->push_layout(*m_current_command_buffer, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL);
		auto snapshot = m_texture_cache.create_temporary_subresource(*m_current_command_buffer, copy);
		surface->pop_layout(*m_current_command_buffer);
		// The temporary-image cache key excludes remapping. Select the current
		// sampler's view explicitly when reusing an earlier draw's allocation.
		return snapshot
			? static_cast<vk::viewable_image*>(snapshot->image())->get_view(remap)->as(view->format())
			: nullptr;
	}

	return view;
}

using pixels_t=std::array<float,4>;
struct draw_result {pixels_t pixels;u32 copies,allocations;};
draw_result run_draw(u32 static_reads,bool linear,bool reverse,bool alias=true){
    vk::vendor=vk::driver_vendor::MVK;
    vk::viewable_image target,separate;
    VKGSRender r;r.m_rtts.m_bound_render_targets[0]={128,&target};
    r.current_fp_metadata.multiple_texture_reads_mask=static_reads>1?1:0;
    auto* source=r.snapshot_color_feedback(0,alias?&target.view:&separate.view);
    assert(source);
    for(u32 n=0;n<4;++n){
        const u32 x=reverse?3-n:n,prev=(x+3)%4;
        const auto& p=source->image()->pixels;
        // One filtered TEX can read two neighbors; two TEX instructions in the
        // other variant implement exactly the same immutable-pixel operation.
        target.pixels[x]=linear?(p[x]+p[prev])*0.5f:p[prev];
    }
    assert(target.layout==VK_IMAGE_LAYOUT_GENERAL&&target.pushes==target.pops);
    return {target.pixels,r.m_texture_cache.calls,r.m_texture_cache.allocations};
}
int main(){
    u32 checks=0,order_dependent=0;
    for(u32 reads:{1u,2u})for(bool linear:{false,true}){
        const auto a=run_draw(reads,linear,false),b=run_draw(reads,linear,true);
        const pixels_t expected=linear?pixels_t{2.5f,1.5f,2.5f,3.5f}:pixels_t{4,1,2,3};
        order_dependent+=a.pixels!=b.pixels;
#ifdef CANDIDATE
        assert(a.pixels==expected&&b.pixels==expected&&a.copies==1&&b.copies==1);checks+=3;
#else
        if(reads==2){assert(a.pixels==expected&&b.pixels==expected&&a.copies==1);checks+=3;}
        else{assert(a.pixels!=b.pixels&&a.copies==0);checks+=2;}
#endif
    }
#ifdef CANDIDATE
    assert(order_dependent==0);
#else
    assert(order_dependent==2);
#endif
    // All guards keep returning the original view with no copy/allocation.
    for(u32 scenario=0;scenario<6;++scenario){
        VKGSRender r;vk::viewable_image target,separate;
        r.current_fp_metadata.multiple_texture_reads_mask=1;
        r.m_rtts.m_bound_render_targets[0]={128,&target};
        auto* input=&target.view;
        vk::vendor=vk::driver_vendor::MVK;
        if(scenario==0)vk::vendor=vk::driver_vendor::OTHER;
        if(scenario==1)target.view.info.subresourceRange.aspectMask=VK_IMAGE_ASPECT_DEPTH_BIT;
        if(scenario==2)target.sample_count=4;
        if(scenario==3)target.spp=4;
        if(scenario==4)input=&separate.view; // strict mode already supplied a distinct copy
        if(scenario==5)r.m_rtts.m_bound_render_targets[0].second=nullptr;
        assert(r.snapshot_color_feedback(0,input)==input&&r.m_texture_cache.calls==0&&r.m_texture_cache.allocations==0);
        ++checks;
    }
    // Repeated dynamic snapshots must use the fresh pixels, preserve view
    // format/remapping and restore attachment layout, including an OOM return.
    vk::vendor=vk::driver_vendor::MVK;
    VKGSRender r;vk::viewable_image target;
    r.current_fp_metadata.multiple_texture_reads_mask=1;
    r.m_rtts.m_bound_render_targets[0]={128,&target};
    target.view.fmt=99;
    for(u32 frame=0;frame<16;++frame){
        target.pixels[0]=float(frame+41);rsx::method_registers.fragment_textures[0].remap=frame;
        const auto* state=r.fs_sampler_state[0].get();
        auto* copy=r.snapshot_color_feedback(0,&target.view);
        assert(copy&&copy->image()!=&target&&copy->image()->pixels==target.pixels&&copy->format()==99);
        assert(copy->image()->selected_remap==frame&&r.fs_sampler_state[0].get()==state);
        assert(target.layout==VK_IMAGE_LAYOUT_GENERAL&&target.pushes==target.pops);checks+=3;
    }
    assert(r.m_texture_cache.calls==16&&r.m_texture_cache.allocations==1);++checks;
    r.m_texture_cache.fail=true;
    assert(!r.snapshot_color_feedback(0,&target.view));++checks;
    assert(target.layout==VK_IMAGE_LAYOUT_GENERAL&&target.pushes==target.pops);++checks;
    // Zero referenced samplers never call this helper: the production callers
    // iterate the referenced mask. Keep that caller contract explicit here.
    const auto before=r.m_texture_cache.calls;
    for(u32 referenced=0;referenced;referenced&=referenced-1)r.snapshot_color_feedback(0,&target.view);
    assert(r.m_texture_cache.calls==before);++checks;
    std::cout<<"{\"checks\":"<<checks<<",\"order_dependent_cases\":"<<order_dependent
      <<",\"repeated_copy_requests\":16,\"reusable_image_allocations_modeled\":1,\"gpu_executed\":false}"<<std::endl;
}
