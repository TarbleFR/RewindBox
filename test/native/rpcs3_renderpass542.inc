namespace renderpass542 {
using u64=std::uint64_t;using u32=std::uint32_t;using u8=std::uint8_t;using usz=std::size_t;
namespace fmt {template<class... A> [[noreturn]] void throw_exception(A&&...) {throw 1;} }
namespace rsx {template<class T> using simple_array=std::vector<T>;}
namespace vk {
struct Device {bool get_framebuffer_loops_support() const {return true;}};
inline Device* get_current_renderer() {static Device d;return &d;}
// RENDERPASS_KEY
using shared_mutex=std::shared_mutex;using reader_lock=std::shared_lock<shared_mutex>;
shared_mutex g_renderpass_cache_mutex;
std::unordered_map<u64,VkRenderPass> g_renderpass_cache;
std::vector<std::vector<u64>> compatibility;
std::vector<std::vector<u64>> layouts;
VkResult vkCreateRenderPass(VkDevice,const VkRenderPassCreateInfo* info,const VkAllocationCallbacks*,VkRenderPass* out) {
    std::vector<u64> c{info->flags,info->attachmentCount,info->subpassCount,info->dependencyCount},l;
    for(unsigned i=0;i<info->attachmentCount;++i) {
        const auto& a=info->pAttachments[i];
        c.insert(c.end(),{a.flags,u64(a.format),u64(a.samples),u64(a.loadOp),u64(a.storeOp),u64(a.stencilLoadOp),u64(a.stencilStoreOp)});
        l.insert(l.end(),{u64(a.initialLayout),u64(a.finalLayout)});
    }
    for(unsigned i=0;i<info->subpassCount;++i) {
        const auto& s=info->pSubpasses[i];
        c.insert(c.end(),{s.flags,u64(s.pipelineBindPoint),s.inputAttachmentCount,s.colorAttachmentCount,s.preserveAttachmentCount});
        for(unsigned j=0;j<s.colorAttachmentCount;++j) {c.push_back(s.pColorAttachments[j].attachment);l.push_back(s.pColorAttachments[j].layout);}
        for(unsigned j=0;j<s.inputAttachmentCount;++j) {c.push_back(s.pInputAttachments[j].attachment);l.push_back(s.pInputAttachments[j].layout);}
        c.push_back(s.pDepthStencilAttachment?s.pDepthStencilAttachment->attachment:VK_ATTACHMENT_UNUSED);
        if(s.pDepthStencilAttachment) l.push_back(s.pDepthStencilAttachment->layout);
        assert(!s.pResolveAttachments && !s.preserveAttachmentCount);
    }
    for(unsigned i=0;i<info->dependencyCount;++i) {
        const auto& d=info->pDependencies[i];
        c.insert(c.end(),{d.srcSubpass,d.dstSubpass,d.srcStageMask,d.dstStageMask,d.srcAccessMask,d.dstAccessMask,d.dependencyFlags});
    }
    compatibility.push_back(c);layouts.push_back(l);*out=reinterpret_cast<VkRenderPass>(compatibility.size());return VK_SUCCESS;
}
#define CHECK_RESULT(x) assert((x)==VK_SUCCESS)
// GET_RENDERPASS
#undef CHECK_RESULT
unsigned test() {
    unsigned cases=0;
    for(unsigned count=1;count<=5;++count) for(unsigned inputs=0;inputs<(1u<<count);++inputs)
    for(unsigned variants=0;variants<(1u<<count);++variants) {
        u64 key=VK_FORMAT_R8G8B8A8_UNORM | (u64(VK_FORMAT_D32_SFLOAT_S8_UINT)<<8) | (1ull<<16) | (u64(inputs)<<37);
        for(unsigned i=0;i<count;++i) key|=u64(variants&(1u<<i)?1:(i==count-1?3:2))<<(22+3*i);
        const auto normal=after::vk::compatible_pipeline_renderpass_key(key);
        auto a=reinterpret_cast<usz>(get_renderpass(nullptr,key))-1;
        auto b=reinterpret_cast<usz>(get_renderpass(nullptr,normal))-1;
        assert(compatibility[a]==compatibility[b]);
        if(key!=normal) assert(layouts[a]!=layouts[b]);
        ++cases;
    }
    return cases;
}
}
}
