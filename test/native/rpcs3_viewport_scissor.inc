@REUSED_BOUNDARY@
#include <algorithm>
using s32 = std::int32_t;
using f32 = float;
struct VkViewport { float x, y, width, height, minDepth, maxDepth; };
struct VkOffset2D { s32 x, y; };
struct VkExtent2D { u32 width, height; };
struct VkRect2D { VkOffset2D offset; VkExtent2D extent; };
struct VkCommandBufferInheritanceInfo { int sType{}; };
struct VkCommandBufferBeginInfo { int sType{}; u32 flags{}; const VkCommandBufferInheritanceInfo* pInheritanceInfo{}; };
constexpr int VK_STRUCTURE_TYPE_COMMAND_BUFFER_INHERITANCE_INFO = 1;
constexpr int VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO = 2;
constexpr u32 VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT = 1;
#define CHECK_RESULT(x) assert((x) == 0)
void vkCmdSetViewport(Driver* d, u32 first, u32 count, const VkViewport* v) {
    assert(first == 0 && count == 1);
    store(d,10,{std::bit_cast<u32>(v->x),std::bit_cast<u32>(v->y),std::bit_cast<u32>(v->width),std::bit_cast<u32>(v->height)});
    store(d,11,{std::bit_cast<u32>(v->minDepth),std::bit_cast<u32>(v->maxDepth)});
    ++d->viewport_calls;
}
void vkCmdSetScissor(Driver* d, u32 first, u32 count, const VkRect2D* s) {
    assert(first == 0 && count == 1);
    store(d,12,{std::bit_cast<u32>(s->offset.x),std::bit_cast<u32>(s->offset.y),s->extent.width,s->extent.height});
    ++d->scissor_calls;
}
int vkBeginCommandBuffer(Driver* d, const VkCommandBufferBeginInfo* info) {
    assert(info && info->pInheritanceInfo && info->flags == VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT);
    d->valid=0; d->bound={}; d->lifetime.push_back(1); return 0;
}
int vkResetCommandBuffer(Driver* d, u32 flags) { assert(flags==0); d->lifetime.push_back(2); return 0; }
int vkEndCommandBuffer(Driver* d) { d->lifetime.push_back(3); return 0; }
struct Fence { Driver* driver; void reset() { driver->lifetime.push_back(4); } };
void wait_for_fence(Fence* f) { f->driver->lifetime.push_back(5); }
namespace rpcs3::ios::rsx_sync { constexpr int cb_reuse=0; struct SiteScope { explicit SiteScope(int) {} }; }
struct Logger { void error(const char*) { assert(false); } } rsx_log;
namespace rsx {
namespace pipeline_state { constexpr u32 zclip_config_state_dirty = 1; }
struct Registers { float minimum=0,maximum=1; float clip_min()const{return minimum;} float clip_max()const{return maximum;} } method_registers;
}
struct GraphicsState {
    u32 bits=0;
    u32 operator&(u32 other) const { return bits & other; }
    void clear(u32 value) { bits &= ~value; }
};
struct DeviceBoundary { bool unrestricted=true; bool get_unrestricted_depth_range_support()const{return unrestricted;} };

@PRODUCTION@
@DRAW_EQUAL@

constexpr u32 viewport_bits=(1u<<10)|(1u<<11), scissor_bits=1u<<12;
std::array<std::vector<VkDynamicState>,65> declarations;
void configure_pipeline(u64 id, u32 mask) {
    pipelines[id].mask=mask;
    pipelines[id].static_values[0]={std::bit_cast<u32>(1.f)};
    pipelines[id].static_values[10]={0,0,std::bit_cast<u32>(1280.f),std::bit_cast<u32>(720.f)};
    pipelines[id].static_values[11]={0,std::bit_cast<u32>(1.f)};
    pipelines[id].static_values[12]={0,0,1280,720};
    if(mask&viewport_bits)declarations[id].push_back(VK_DYNAMIC_STATE_VIEWPORT);
    if(mask&scissor_bits)declarations[id].push_back(VK_DYNAMIC_STATE_SCISSOR);
}
struct Pair {
    Driver a{},b{};
    reference::command_buffer before{&a}; candidate::command_buffer after{&b};
    DeviceBoundary device{};
    reference::VKGSRender old_guest{&before,&device}; candidate::VKGSRender new_guest{&after,&device};
    u64 draws=0;
    Pair() { before.is_open=after.is_open=false; before.begin(); after.begin(); }
    void bind(u64 id, VkPipelineBindPoint point=VK_PIPELINE_BIND_POINT_GRAPHICS, bool unknown=false) {
        auto& states=declarations[id];
        VkPipelineDynamicStateCreateInfo info{u32(states.size()),states.data()};
        before.bind_pipeline(id,point,unknown?0:reference::pipeline_dynamic_state_mask(&info));
        after.bind_pipeline(id,point,unknown?0:candidate::pipeline_dynamic_state_mask(&info));
    }
    void equal() { draw_equal(a,b); assert(a.lifetime==b.lifetime); ++draws; }
    void guest(VkViewport viewport,VkRect2D scissor,bool dirty=false) {
        old_guest.m_viewport=new_guest.m_viewport=viewport;
        old_guest.m_scissor=new_guest.m_scissor=scissor;
        old_guest.m_graphics_state.bits=new_guest.m_graphics_state.bits=dirty?1:0;
        old_guest.bind_viewport();new_guest.bind_viewport();
        assert(old_guest.m_graphics_state.bits==new_guest.m_graphics_state.bits);
        equal();
    }
    void overlay(unsigned which,u32 x,u32 y,u32 w,u32 h,VkRect2D region) {
        if(which==0) {
            reference::overlay_pass old;candidate::overlay_pass now;
            old.set_up_viewport(before,x,y,w,h);now.set_up_viewport(after,x,y,w,h);
        } else if(which==1) {
            reference::attachment_clear_pass old;candidate::attachment_clear_pass now;
            old.region=now.region=region;old.set_up_viewport(before,x,y,w,h);now.set_up_viewport(after,x,y,w,h);
        } else {
            reference::stencil_clear_pass old;candidate::stencil_clear_pass now;
            old.region=now.region=region;old.set_up_viewport(before,x,y,w,h);now.set_up_viewport(after,x,y,w,h);
        }
        equal();
    }
};

int main() {
    static_assert(candidate::dynamic_state_cache::count==13);
    static_assert(all_states==0x1fff);
    const std::array<u32,9> bits{viewport_bits,scissor_bits,1,4,2,8,192,48,768};
    unsigned mask_cases=0;
    for(u32 selected=0;selected<512;++selected) {
        std::vector<VkDynamicState> states;u32 expected=0;
        for(unsigned i=0;i<bits.size();++i)if(selected&(1u<<i)){states.push_back(VkDynamicState(i));expected|=bits[i];}
        states.push_back(VkDynamicState(987654));states.push_back(states.front());
        VkPipelineDynamicStateCreateInfo info{u32(states.size()),states.data()};
        assert(candidate::pipeline_dynamic_state_mask(&info)==expected);++mask_cases;
    }
    VkPipelineDynamicStateCreateInfo empty{0,nullptr};
    assert(candidate::pipeline_dynamic_state_mask(nullptr)==0 && candidate::pipeline_dynamic_state_mask(&empty)==0);
    mask_cases+=2;
    configure_pipeline(1,viewport_bits|scissor_bits);configure_pipeline(2,viewport_bits|scissor_bits);
    configure_pipeline(3,0);configure_pipeline(4,viewport_bits);configure_pipeline(5,scissor_bits);
    const VkViewport initial{0,0,1280,720,0,1};const VkRect2D area{{0,0},{1280,720}};
    Pair repeats;
    for(unsigned i=0;i<10000;++i){repeats.bind(1+i%2);repeats.guest(initial,area);}
    assert(repeats.a.viewport_calls==10000 && repeats.a.scissor_calls==10000);
    assert(repeats.b.viewport_calls==1 && repeats.b.scissor_calls==1);
    assert(repeats.a.binds==repeats.b.binds);

    Pair component;component.bind(1);component.guest(initial,area);
    VkViewport viewport=initial;VkRect2D rect=area;
    viewport.width=640;component.guest(viewport,rect);component.guest(viewport,rect);
    assert(component.b.viewport_calls==2 && component.b.scissor_calls==1);
    viewport.minDepth=0.25f;component.guest(viewport,rect);component.guest(viewport,rect);
    assert(component.b.viewport_calls==3 && component.b.scissor_calls==1);
    rect.offset.x=-7;component.guest(viewport,rect);component.guest(viewport,rect);
    assert(component.b.viewport_calls==3 && component.b.scissor_calls==2);
    rect.extent.height=23;component.guest(viewport,rect);component.guest(viewport,rect);
    assert(component.b.viewport_calls==3 && component.b.scissor_calls==3);
    rsx::method_registers.minimum=-0.5f;rsx::method_registers.maximum=1.5f;
    component.guest(viewport,rect,true);assert(component.b.viewport_calls==4);
    component.device.unrestricted=false;component.guest(viewport,rect,true);
    assert(component.b.viewport_calls==5 && component.new_guest.m_graphics_state.bits==0);

    unsigned bit_cases=0;
    const std::array<u32,8> edge{0,0x80000000u,0x3f800000u,0x3f000000u,0x7fc00001u,0x7fc00002u,0x7f800000u,0xffffffffu};
    for(unsigned field=0;field<6;++field)for(u32 pattern:edge) {
        VkViewport value=initial;
        switch(field){case 0:value.x=std::bit_cast<float>(pattern);break;case 1:value.y=std::bit_cast<float>(pattern);break;
          case 2:value.width=std::bit_cast<float>(pattern);break;case 3:value.height=std::bit_cast<float>(pattern);break;
          case 4:value.minDepth=std::bit_cast<float>(pattern);break;case 5:value.maxDepth=std::bit_cast<float>(pattern);break;}
        component.guest(value,area);const auto calls=component.b.viewport_calls;
        component.guest(value,area);assert(component.b.viewport_calls==calls);++bit_cases;
    }
    for(u32 pattern:edge) {
        VkRect2D value{{std::bit_cast<s32>(pattern),std::bit_cast<s32>(~pattern)},{pattern,~pattern}};
        component.guest(initial,value);const auto calls=component.b.scissor_calls;
        component.guest(initial,value);assert(component.b.scissor_calls==calls);++bit_cases;
    }

    Pair transitions;transitions.bind(1);transitions.guest(initial,area);
    unsigned static_cases=0;
    for(u64 pipeline:{3ull,4ull,5ull}) {
        transitions.bind(pipeline);transitions.equal();transitions.bind(1);
        const auto vc=transitions.b.viewport_calls,sc=transitions.b.scissor_calls;
        transitions.guest(initial,area);
        assert(transitions.b.viewport_calls-vc==((pipelines[pipeline].mask&viewport_bits)?0:1));
        assert(transitions.b.scissor_calls-sc==((pipelines[pipeline].mask&scissor_bits)?0:1));++static_cases;
    }
    const auto vc=transitions.b.viewport_calls,sc=transitions.b.scissor_calls;
    transitions.bind(3,VK_PIPELINE_BIND_POINT_COMPUTE);transitions.guest(initial,area);
    assert(transitions.b.viewport_calls==vc && transitions.b.scissor_calls==sc);
    transitions.bind(2,VK_PIPELINE_BIND_POINT_GRAPHICS,true);transitions.guest(initial,area);
    assert(transitions.b.viewport_calls==vc+1 && transitions.b.scissor_calls==sc+1);
    unsigned overlay_cases=0;
    for(unsigned type=0;type<3;++type) {
        transitions.bind(2);transitions.overlay(type,10,20,300,200,{{3,4},{30,40}});
        const auto ov=transitions.b.viewport_calls,os=transitions.b.scissor_calls;
        transitions.overlay(type,10,20,300,200,{{3,4},{30,40}});
        assert(transitions.b.viewport_calls==ov && transitions.b.scissor_calls==os);
        transitions.bind(1);transitions.guest(initial,area);
        assert(transitions.b.viewport_calls==ov+1 && transitions.b.scissor_calls==os+1);++overlay_cases;
    }

    Pair lifetime;lifetime.bind(1);lifetime.guest(initial,area);
    Fence old_fence{&lifetime.a},new_fence{&lifetime.b};
    for(unsigned iteration=0;iteration<3;++iteration) {
        lifetime.before.end();lifetime.after.end();
        if(iteration==1){lifetime.before.reset();lifetime.after.reset();}
        if(iteration==2){lifetime.before.m_submit_fence=&old_fence;lifetime.after.m_submit_fence=&new_fence;lifetime.before.is_pending=lifetime.after.is_pending=true;}
        lifetime.before.begin();lifetime.after.begin();lifetime.bind(1);lifetime.guest(initial,area);
        assert(lifetime.b.viewport_calls==iteration+2 && lifetime.b.scissor_calls==iteration+2);
        assert(lifetime.before.is_pending==lifetime.after.is_pending);
    }
    Pair independent;independent.bind(1);independent.guest(initial,area);
    assert(independent.b.viewport_calls==1 && independent.b.scissor_calls==1);

    Pair randomized;std::mt19937 rng(0x593066);
    unsigned random_draws=0;
    for(unsigned iteration=0;iteration<20000;++iteration) {
        if(iteration%191==0){randomized.before.end();randomized.after.end();randomized.before.begin();randomized.after.begin();}
        randomized.bind(1+rng()%5);
        // Static binds above test invalidation. Every following dynamic setter
        // and draw uses a fully dynamic viewport/scissor pipeline (VUID08608).
        randomized.bind(1+iteration%2);
        if(iteration%7==0){
            viewport.x=float(rng()%50);viewport.y=float(rng()%70);
            viewport.width=float(1+rng()%1280);viewport.height=float(1+rng()%720);
            viewport.minDepth=0;viewport.maxDepth=1;
            rect={{s32(rng()%20),s32(rng()%20)},{u32(1+rng()%640),u32(1+rng()%360)}};
        }
        randomized.guest(viewport,rect);++random_draws;
    }
    assert(randomized.a.binds==randomized.b.binds && randomized.a.lifetime==randomized.b.lifetime);
    assert(randomized.b.viewport_calls<=randomized.a.viewport_calls && randomized.b.scissor_calls<=randomized.a.scissor_calls);
    std::cout<<"{\"passed\":true,\"assertionsActive\":true,\"maskCases\":"<<mask_cases
      <<",\"identicalDraws\":10000,\"baselineViewportCommands\":10000,\"candidateViewportCommands\":1,"
      "\"baselineScissorCommands\":10000,\"candidateScissorCommands\":1,\"bitPatternCases\":"<<bit_cases
      <<",\"staticTransitionCases\":"<<static_cases<<",\"overlayReturnCases\":"<<overlay_cases
      <<",\"recordingReuseCases\":3,\"randomDraws\":"<<random_draws
      <<",\"randomBaselineViewportCommands\":"<<randomized.a.viewport_calls<<",\"randomCandidateViewportCommands\":"<<randomized.b.viewport_calls
      <<",\"randomBaselineScissorCommands\":"<<randomized.a.scissor_calls<<",\"randomCandidateScissorCommands\":"<<randomized.b.scissor_calls
      <<",\"boundsAndDepthIndependent\":true,\"independentBuffers\":true,\"computeRetainsGraphics\":true,\"unknownMaskInvalidates\":true,\"lifetimeTraceEqual\":true}\n";
}
