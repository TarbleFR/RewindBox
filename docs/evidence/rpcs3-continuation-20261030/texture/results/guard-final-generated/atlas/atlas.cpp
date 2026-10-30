#include <algorithm>
#include <array>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <memory>
#include <new>
#include <random>
#include <stdexcept>
#include <string>
#include <vector>
using u8=uint8_t; using u16=uint16_t; using u32=uint32_t;
static bool count_allocations=false;
static unsigned allocations=0,checks=0;
[[gnu::noinline]] void* operator new(std::size_t n) { if(count_allocations)++allocations; if(auto p=std::malloc(n?n:1))return p;throw std::bad_alloc(); }
[[gnu::noinline]] void operator delete(void* p) noexcept {std::free(p);}
[[gnu::noinline]] void operator delete(void* p,std::size_t) noexcept {std::free(p);}
static void ensure(bool x){++checks;if(!x)throw std::runtime_error("atlas contract");}
using VkImageAspectFlags=u32;
constexpr u32 VK_IMAGE_ASPECT_COLOR_BIT=1,VK_IMAGE_ASPECT_DEPTH_BIT=2,VK_IMAGE_TYPE_2D=2,VK_IMAGE_TYPE_3D=3,VK_IMAGE_VIEW_TYPE_2D=2;
constexpr u32 VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL=4,VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL=5;
constexpr u32 VK_PIPELINE_STAGE_TRANSFER_BIT=8,VK_ACCESS_TRANSFER_WRITE_BIT=16;
struct VkImageSubresourceRange{u32 aspectMask,baseMipLevel,levelCount,baseArrayLayer,layerCount;};
struct VkClearColorValue{u32 value[4];};
struct VkClearDepthStencilValue{float depth;u32 stencil;};
namespace rsx {template<class T>using simple_array=std::vector<T>;enum class texture_dimension_extended{texture_dimension_2d};}
namespace vk {
struct image {
    u32 w=8,h=8,aspect_value=1,type_value=2,mip_count=1,layer_count=1,current_layout=0;
    image* value=this;
    std::vector<u32> pixels;
    u32 width()const{return w;}u32 height()const{return h;}u32 aspect()const{return aspect_value;}
    u32 type()const{return type_value;}u32 mipmaps()const{return mip_count;}u32 layers()const{return layer_count;}
    image* handle(){return this;}
};
struct image_view {
    struct {u32 format;}info{1};
    vk::image* target=nullptr;
    vk::image* image(){return target;}
};
struct copy_region_descriptor{
    image* src=nullptr;u16 src_w=1,src_h=1,dst_w=1,dst_h=1,dst_x=0,dst_y=0,dst_z=0;u8 level=0;
};
struct deferred_subresource{rsx::simple_array<copy_region_descriptor>sections_to_copy;u16 width=8,height=8;u32 gcm_format=1,remap=0;bool force_bg_load=false;};
struct command_buffer{std::string events;unsigned color_clears=0,depth_clears=0,copies=0,barriers=0,loads=0;};
u32 get_aspect_flags(u32 format){return format;}
void change_image_layout(command_buffer& cmd,image* target,u32 layout,VkImageSubresourceRange){cmd.events+='L';target->current_layout=layout;}
void vkCmdClearColorImage(command_buffer& cmd,image* target,u32,const VkClearColorValue*,u32,const VkImageSubresourceRange*){cmd.events+='C';++cmd.color_clears;std::fill(target->pixels.begin(),target->pixels.end(),0);}
void vkCmdClearDepthStencilImage(command_buffer& cmd,image* target,u32,const VkClearDepthStencilValue*,u32,const VkImageSubresourceRange*){cmd.events+='D';++cmd.depth_clears;std::fill(target->pixels.begin(),target->pixels.end(),~0u);}
void insert_image_memory_barrier(command_buffer& cmd,image*,u32,u32,u32,u32,u32,u32,VkImageSubresourceRange){cmd.events+='B';++cmd.barriers;}
struct texture_cache{
    image destination;
    image_view view;
    bool oom=false;
    image* get_template_from_collection_impl(const rsx::simple_array<copy_region_descriptor>& s){return s.empty()?nullptr:s[0].src;}
    image_view* create_temporary_subresource_view_impl(command_buffer&,image*,u32,u32,u32 format,u16 w,u16 h,u16,u8,u32){
        if(oom)return nullptr;
        destination.w=w;destination.h=h;destination.aspect_value=format;destination.pixels.assign(w*h,0xdeadbeefu);
        view.target=&destination;view.info.format=format;return &view;
    }
    void initialize_subresource_from_memory(command_buffer& cmd,image* dst,const deferred_subresource&,rsx::texture_dimension_extended){
        ++cmd.loads;cmd.events+='H';for(unsigned i=0;i<dst->pixels.size();++i)dst->pixels[i]=1000+i;
    }
    void copy_transfer_regions_impl(command_buffer& cmd,image* dst,const rsx::simple_array<copy_region_descriptor>& sections)const{
        for(unsigned index=0;index<sections.size();++index){
            const auto& s=sections[index];if(!s.src)continue;
            ++cmd.copies;cmd.events+='X';
            for(unsigned y=s.dst_y;y<u32{s.dst_y}+s.dst_h&&y<dst->h;++y)
            for(unsigned x=s.dst_x;x<u32{s.dst_x}+s.dst_w&&x<dst->w;++x)
                dst->pixels[y*dst->w+x]=0x1000000+index*4096+y*dst->w+x;
        }
    }
    bool copy_transfer_regions_fully_cover_2d_image(image*,const rsx::simple_array<copy_region_descriptor>&)const;
    image_view* generate_atlas_from_images(command_buffer&,const deferred_subresource&);
};
struct baseline_cache:texture_cache{image_view*generate_atlas_from_images(command_buffer&,const deferred_subresource&);};
bool texture_cache::copy_transfer_regions_fully_cover_2d_image(vk::image* dst, const rsx::simple_array<copy_region_descriptor>& sections) const
	{
		// A small atlas often consists of strips/tiles that collectively replace
		// every texel. Prove their union without a pixel-sized scratch allocation.
		// Larger or non-color/2D requests keep the existing clear path.
		if (dst->aspect() != VK_IMAGE_ASPECT_COLOR_BIT || dst->type() != VK_IMAGE_TYPE_2D ||
			dst->mipmaps() != 1 || dst->layers() != 1 || !dst->width() || !dst->height() ||
			sections.empty() || sections.size() > 8)
		{
			return false;
		}

		std::array<u32, 18> row_edges{};
		u32 edge_count = 2;
		row_edges[1] = dst->height();
		for (const auto& section : sections)
		{
			if (!section.src || section.src == dst || section.src->aspect() != VK_IMAGE_ASPECT_COLOR_BIT ||
				!section.src_w || !section.src_h || !section.dst_w || !section.dst_h ||
				section.level || section.dst_z ||
				u32{section.dst_x} + section.dst_w > dst->width() ||
				u32{section.dst_y} + section.dst_h > dst->height())
			{
				return false;
			}
			row_edges[edge_count++] = section.dst_y;
			row_edges[edge_count++] = u32{section.dst_y} + section.dst_h;
		}
		std::sort(row_edges.begin(), row_edges.begin() + edge_count);

		for (u32 row = 1; row < edge_count; ++row)
		{
			const u32 y0 = row_edges[row - 1], y1 = row_edges[row];
			if (y0 == y1)
				continue;

			// Each extension reaches an edge of one of the at most eight
			// rectangles. Gaps stop immediately; overlaps never count twice.
			u32 covered_x = 0;
			while (covered_x < dst->width())
			{
				u32 next_x = covered_x;
				for (const auto& section : sections)
				{
					if (section.dst_y <= y0 && u32{section.dst_y} + section.dst_h >= y1 &&
						section.dst_x <= covered_x)
					{
						next_x = std::max(next_x, u32{section.dst_x} + section.dst_w);
					}
				}
				if (next_x == covered_x)
					return false;
				covered_x = next_x;
			}
		}
		return true;
	}
vk::image_view* texture_cache::generate_atlas_from_images(vk::command_buffer& cmd, const deferred_subresource& desc)
	{
		const auto& sections_to_copy = desc.sections_to_copy;
		auto _template = get_template_from_collection_impl(sections_to_copy);
		auto result = create_temporary_subresource_view_impl(cmd, _template, VK_IMAGE_TYPE_2D,
			VK_IMAGE_VIEW_TYPE_2D, desc.gcm_format, desc.width, desc.height, 1, 1, desc.remap);

		if (!result)
		{
			// Failed to create temporary object, bail
			return nullptr;
		}

		const auto image = result->image();
		VkImageAspectFlags dst_aspect = vk::get_aspect_flags(result->info.format);
		VkImageSubresourceRange dst_range = { dst_aspect, 0, 1, 0, 1 };
		vk::change_image_layout(cmd, image, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, dst_range);

		if (desc.force_bg_load)
		{
			// The memory load covers the whole image, no need to clear it first
			initialize_subresource_from_memory(cmd, image, desc, rsx::texture_dimension_extended::texture_dimension_2d);
		}
		else if ((sections_to_copy[0].dst_w != desc.width || sections_to_copy[0].dst_h != desc.height) &&
			!copy_transfer_regions_fully_cover_2d_image(image, sections_to_copy))
		{
			if (!(dst_aspect & VK_IMAGE_ASPECT_DEPTH_BIT))
			{
				VkClearColorValue clear = {};
				vkCmdClearColorImage(cmd, image->value, image->current_layout, &clear, 1, &dst_range);
			}
			else
			{
				VkClearDepthStencilValue clear = { 1.f, 0 };
				vkCmdClearDepthStencilImage(cmd, image->value, image->current_layout, &clear, 1, &dst_range);
			}
		}

		vk::insert_image_memory_barrier(
			cmd,
			image->handle(),
			image->current_layout, image->current_layout,
			VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT,
			VK_ACCESS_TRANSFER_WRITE_BIT, VK_ACCESS_TRANSFER_WRITE_BIT,
			dst_range);

		copy_transfer_regions_impl(cmd, image, sections_to_copy);

		vk::change_image_layout(cmd, image, VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL, dst_range);
		return result;
	}
vk::image_view* baseline_cache::generate_atlas_from_images(vk::command_buffer& cmd, const deferred_subresource& desc)
	{
		const auto& sections_to_copy = desc.sections_to_copy;
		auto _template = get_template_from_collection_impl(sections_to_copy);
		auto result = create_temporary_subresource_view_impl(cmd, _template, VK_IMAGE_TYPE_2D,
			VK_IMAGE_VIEW_TYPE_2D, desc.gcm_format, desc.width, desc.height, 1, 1, desc.remap);

		if (!result)
		{
			// Failed to create temporary object, bail
			return nullptr;
		}

		const auto image = result->image();
		VkImageAspectFlags dst_aspect = vk::get_aspect_flags(result->info.format);
		VkImageSubresourceRange dst_range = { dst_aspect, 0, 1, 0, 1 };
		vk::change_image_layout(cmd, image, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, dst_range);

		if (desc.force_bg_load)
		{
			// The memory load covers the whole image, no need to clear it first
			initialize_subresource_from_memory(cmd, image, desc, rsx::texture_dimension_extended::texture_dimension_2d);
		}
		else if (sections_to_copy[0].dst_w != desc.width || sections_to_copy[0].dst_h != desc.height)
		{
			if (!(dst_aspect & VK_IMAGE_ASPECT_DEPTH_BIT))
			{
				VkClearColorValue clear = {};
				vkCmdClearColorImage(cmd, image->value, image->current_layout, &clear, 1, &dst_range);
			}
			else
			{
				VkClearDepthStencilValue clear = { 1.f, 0 };
				vkCmdClearDepthStencilImage(cmd, image->value, image->current_layout, &clear, 1, &dst_range);
			}
		}

		vk::insert_image_memory_barrier(
			cmd,
			image->handle(),
			image->current_layout, image->current_layout,
			VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT,
			VK_ACCESS_TRANSFER_WRITE_BIT, VK_ACCESS_TRANSFER_WRITE_BIT,
			dst_range);

		copy_transfer_regions_impl(cmd, image, sections_to_copy);

		vk::change_image_layout(cmd, image, VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL, dst_range);
		return result;
	}
}
int main(){
    using namespace vk;
    unsigned cases=0,omitted=0,clear_preserved=0,fallbacks=0;
    texture_cache candidate;baseline_cache baseline;image source;
    auto independent_coverage=[&](const image& dst,const auto& sections){
        if(dst.aspect()!=1||dst.type()!=2||dst.mipmaps()!=1||dst.layers()!=1||!dst.w||!dst.h||sections.empty()||sections.size()>8)return false;
        std::vector<bool> painted(dst.w*dst.h,false);
        for(const auto& s:sections){
            if(!s.src||s.src==&dst||s.src->aspect()!=1||!s.src_w||!s.src_h||!s.dst_w||!s.dst_h||s.level||s.dst_z||u32{s.dst_x}+s.dst_w>dst.w||u32{s.dst_y}+s.dst_h>dst.h)return false;
            for(unsigned y=s.dst_y;y<u32{s.dst_y}+s.dst_h;++y)for(unsigned x=s.dst_x;x<u32{s.dst_x}+s.dst_w;++x)painted[y*dst.w+x]=true;
        }
        return std::all_of(painted.begin(),painted.end(),[](bool x){return x;});
    };
    auto check=[&](deferred_subresource desc){
        image dst;dst.w=desc.width;dst.h=desc.height;dst.aspect_value=desc.gcm_format;
        const bool expected=independent_coverage(dst,desc.sections_to_copy);
        count_allocations=true;const auto before=allocations;
        const bool covered=candidate.copy_transfer_regions_fully_cover_2d_image(&dst,desc.sections_to_copy);
        count_allocations=false;
        ensure(allocations==before);ensure(covered==expected);
        command_buffer oldcmd,newcmd;
        ensure(baseline.generate_atlas_from_images(oldcmd,desc)!=nullptr);
        ensure(candidate.generate_atlas_from_images(newcmd,desc)!=nullptr);
        ensure(baseline.destination.pixels==candidate.destination.pixels);
        ensure(oldcmd.copies==newcmd.copies&&oldcmd.barriers==newcmd.barriers&&oldcmd.loads==newcmd.loads&&oldcmd.depth_clears==newcmd.depth_clears);
        ensure(newcmd.color_clears<=oldcmd.color_clears);
        if(newcmd.color_clears!=oldcmd.color_clears){
            ensure(covered&&!desc.force_bg_load&&desc.gcm_format==1);
            auto events=oldcmd.events;events.erase(events.find('C'),1);ensure(events==newcmd.events);++omitted;
        }else{ensure(oldcmd.events==newcmd.events);++clear_preserved;}
        ++cases;
    };
    std::mt19937 rng(0x596a71a5);
    for(unsigned trial=0;trial<12000;++trial){
        deferred_subresource desc;
        desc.width=2+rng()%31;desc.height=2+rng()%31;
        desc.sections_to_copy.push_back({&source,desc.width,desc.height,desc.width,desc.height,0,0,0,0});
        const unsigned target=2+rng()%7;
        for(unsigned attempt=0;attempt<30&&desc.sections_to_copy.size()<target;++attempt){
            const unsigned i=rng()%desc.sections_to_copy.size();auto a=desc.sections_to_copy[i],b=a;
            if((rng()&1)&&a.dst_w>1){unsigned w=1+rng()%(a.dst_w-1);a.dst_w=w;b.dst_x+=w;b.dst_w-=w;}
            else if(a.dst_h>1){unsigned h=1+rng()%(a.dst_h-1);a.dst_h=h;b.dst_y+=h;b.dst_h-=h;}
            else continue;
            desc.sections_to_copy[i]=a;desc.sections_to_copy.push_back(b);
        }
        std::shuffle(desc.sections_to_copy.begin(),desc.sections_to_copy.end(),rng);
        check(desc);
        desc.force_bg_load=true;check(desc);desc.force_bg_load=false;
        // A missing tile, one-pixel gap, duplicate and exact overlap must obey the painted oracle.
        if(desc.sections_to_copy.size()>1){
            auto hole=desc;hole.sections_to_copy.pop_back();check(hole);
            auto duplicate=desc;duplicate.sections_to_copy.back()=duplicate.sections_to_copy.front();check(duplicate);
        }
        auto overlap=desc;overlap.sections_to_copy.push_back(overlap.sections_to_copy.front());check(overlap);
        desc.gcm_format=2;check(desc);
    }
    for(unsigned trial=0;trial<12000;++trial){
        deferred_subresource desc;desc.width=2+rng()%31;desc.height=2+rng()%31;
        unsigned count=1+rng()%12;
        for(unsigned i=0;i<count;++i){u16 x=rng()%desc.width,y=rng()%desc.height;desc.sections_to_copy.push_back({&source,1,1,u16(1+rng()%(desc.width-x)),u16(1+rng()%(desc.height-y)),x,y,0,0});}
        check(desc);
    }
    // Unsafe and unsupported geometry always falls back; the generator still owns the actual copies.
    for(unsigned variant=0;variant<14;++variant){
        image dst;dst.w=dst.h=8;image input;
        rsx::simple_array<copy_region_descriptor> s{{&input,8,8,8,8,0,0,0,0}};
        switch(variant){case 0:s.clear();break;case 1:s.resize(9,s[0]);break;case 2:s[0].src=nullptr;break;case 3:input.aspect_value=2;break;case 4:s[0].src_w=0;break;case 5:s[0].src_h=0;break;case 6:s[0].dst_z=1;break;case 7:s[0].level=1;break;case 8:s[0].dst_x=1;break;case 9:s[0].dst_y=1;break;case 10:dst.type_value=3;break;case 11:dst.mip_count=2;break;case 12:dst.layer_count=6;break;case 13:s[0].src=&dst;break;}
        ensure(!candidate.copy_transfer_regions_fully_cover_2d_image(&dst,s));++fallbacks;
    }
    candidate.oom=true;deferred_subresource d;d.sections_to_copy.push_back({&source});command_buffer cmd;
    ensure(candidate.generate_atlas_from_images(cmd,d)==nullptr);ensure(cmd.events.empty());
    std::cout<<"{\"case\":\"atlas_coverage\",\"cases\":"<<cases<<",\"checks\":"<<checks<<",\"newly_omitted_color_clears\":"<<omitted<<",\"unchanged_clear_cases\":"<<clear_preserved<<",\"unsafe_fallbacks\":"<<fallbacks<<",\"helper_allocations\":"<<allocations<<"}\n";
}
