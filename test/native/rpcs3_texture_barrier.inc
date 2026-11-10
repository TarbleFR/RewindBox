#include <array>
#include <cassert>
#include <cstdint>
#include <cstdlib>
#include <iostream>
using u32=std::uint32_t;using u64=std::uint64_t;
using VkImage=u64;using VkImageLayout=u32;using VkPipelineStageFlags=u32;using VkAccessFlags=u32;
// Vulkan 1.0 numeric stage/access values; these do not model driver execution.
constexpr u32 VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT=1,VK_PIPELINE_STAGE_VERTEX_SHADER_BIT=8,VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT=0x80,VK_PIPELINE_STAGE_EARLY_FRAGMENT_TESTS_BIT=0x100,VK_PIPELINE_STAGE_LATE_FRAGMENT_TESTS_BIT=0x200,VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT=0x400,VK_PIPELINE_STAGE_TRANSFER_BIT=0x1000;
constexpr u32 VK_ACCESS_INPUT_ATTACHMENT_READ_BIT=0x10,VK_ACCESS_SHADER_READ_BIT=0x20,VK_ACCESS_COLOR_ATTACHMENT_READ_BIT=0x80,VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT=0x100,VK_ACCESS_DEPTH_STENCIL_ATTACHMENT_READ_BIT=0x200,VK_ACCESS_DEPTH_STENCIL_ATTACHMENT_WRITE_BIT=0x400,VK_ACCESS_TRANSFER_READ_BIT=0x800,VK_ACCESS_TRANSFER_WRITE_BIT=0x1000;
constexpr u32 VK_IMAGE_LAYOUT_UNDEFINED=0,VK_IMAGE_LAYOUT_GENERAL=1,VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL=2,VK_IMAGE_LAYOUT_DEPTH_STENCIL_ATTACHMENT_OPTIMAL=3,VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL=5,VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL=6,VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL=7,VK_IMAGE_LAYOUT_PREINITIALIZED=8,VK_IMAGE_LAYOUT_PRESENT_SRC_KHR=1000001002,VK_IMAGE_LAYOUT_ATTACHMENT_FEEDBACK_LOOP_OPTIMAL_EXT=1000339000;
constexpr u32 VK_IMAGE_ASPECT_COLOR_BIT=1,VK_IMAGE_ASPECT_DEPTH_BIT=2,VK_IMAGE_ASPECT_STENCIL_BIT=4,VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER=45;
struct VkImageSubresourceRange{u32 aspectMask,baseMipLevel,levelCount,baseArrayLayer,layerCount;bool operator==(const VkImageSubresourceRange&)const=default;};
struct VkImageMemoryBarrier{u32 sType=0,newLayout=0,oldLayout=0;VkImage image=0;u32 srcAccessMask=0,dstAccessMask=0,srcQueueFamilyIndex=0,dstQueueFamilyIndex=0;VkImageSubresourceRange subresourceRange{};bool operator==(const VkImageMemoryBarrier&)const=default;};
namespace fmt {template<class...T>[[noreturn]]void throw_exception(const char*,T...){std::abort();}}
namespace vk {
struct command_buffer{mutable bool renderpass=true;mutable u32 calls=0,src=0,dst=0;mutable VkImageMemoryBarrier barrier{};};
bool is_renderpass_open(const command_buffer& cmd){return cmd.renderpass;}
void end_renderpass(const command_buffer& cmd){cmd.renderpass=false;}
void vkCmdPipelineBarrier(const command_buffer& cmd,u32 src,u32 dst,u32 flags,u32 memory_count,const void*,u32 buffer_count,const void*,u32 image_count,const VkImageMemoryBarrier* barrier){assert(!cmd.renderpass&&!flags&&!memory_count&&!buffer_count&&image_count==1);++cmd.calls;cmd.src=src;cmd.dst=dst;cmd.barrier=*barrier;}
@BEFORE@
@AFTER@
}
int main(){
 u64 checks=0,missing_before=0;
 constexpr std::array<u32,10> old_layouts{VK_IMAGE_LAYOUT_UNDEFINED,VK_IMAGE_LAYOUT_PREINITIALIZED,VK_IMAGE_LAYOUT_GENERAL,VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL,VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL,VK_IMAGE_LAYOUT_DEPTH_STENCIL_ATTACHMENT_OPTIMAL,VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL,VK_IMAGE_LAYOUT_ATTACHMENT_FEEDBACK_LOOP_OPTIMAL_EXT,VK_IMAGE_LAYOUT_PRESENT_SRC_KHR};
 constexpr std::array<u32,8> new_layouts{VK_IMAGE_LAYOUT_GENERAL,VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL,VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL,VK_IMAGE_LAYOUT_DEPTH_STENCIL_ATTACHMENT_OPTIMAL,VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL,VK_IMAGE_LAYOUT_ATTACHMENT_FEEDBACK_LOOP_OPTIMAL_EXT,VK_IMAGE_LAYOUT_PRESENT_SRC_KHR};
 for(u32 old:old_layouts)for(u32 next:new_layouts)for(u32 aspect:{1u,2u,6u})for(u32 src_mask:{0u,~0u,VK_ACCESS_SHADER_READ_BIT,VK_ACCESS_TRANSFER_WRITE_BIT})for(u32 dst_mask:{0u,~0u,VK_ACCESS_SHADER_READ_BIT,VK_ACCESS_TRANSFER_WRITE_BIT})for(bool open:{false,true}){
  vk::command_buffer a,b;a.renderpass=b.renderpass=open;VkImageSubresourceRange range{aspect,2,4,3,6};
  vk::before(a,0x1234,old,next,range,7,11,src_mask,dst_mask);vk::after(b,0x1234,old,next,range,7,11,src_mask,dst_mask);
  assert(a.calls==1&&b.calls==1&&!a.renderpass&&!b.renderpass&&a.barrier==b.barrier);
  assert((a.src&~VK_PIPELINE_STAGE_VERTEX_SHADER_BIT)==(b.src&~VK_PIPELINE_STAGE_VERTEX_SHADER_BIT));
  assert((a.dst&~VK_PIPELINE_STAGE_VERTEX_SHADER_BIT)==(b.dst&~VK_PIPELINE_STAGE_VERTEX_SHADER_BIT));
  if(b.barrier.srcAccessMask&VK_ACCESS_SHADER_READ_BIT){missing_before+=!(a.src&VK_PIPELINE_STAGE_VERTEX_SHADER_BIT);assert(b.src&VK_PIPELINE_STAGE_VERTEX_SHADER_BIT);}
  if(b.barrier.dstAccessMask&VK_ACCESS_SHADER_READ_BIT){missing_before+=!(a.dst&VK_PIPELINE_STAGE_VERTEX_SHADER_BIT);assert(b.dst&VK_PIPELINE_STAGE_VERTEX_SHADER_BIT);}
  if(!b.barrier.srcAccessMask)assert(b.src==VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT);
  if(!b.barrier.dstAccessMask)assert(b.dst==VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT);
  assert(b.barrier.image==0x1234&&b.barrier.subresourceRange==range&&b.barrier.srcQueueFamilyIndex==7&&b.barrier.dstQueueFamilyIndex==11);
  ++checks;
 }
 assert(missing_before>0);
 std::cout<<"{\"checks\":"<<checks<<",\"baselineShaderReadScopesWithoutVertex\":"<<missing_before<<",\"candidateShaderReadScopesWithoutVertex\":0,\"sameImageAccessRangesQueueFamiliesAndBarrierCounts\":true,\"computeScopeChanged\":false}";
}
