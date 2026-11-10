#include <array>
#include <bit>
#include <cassert>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <random>
#include <vector>

#ifdef NDEBUG
#error The differential checks require assertions.
#endif

using u32 = std::uint32_t;
using u64 = std::uint64_t;
using VkPipeline = u64;
using VkDescriptorSet = u64;
using VkStencilFaceFlags = u32;
enum VkPipelineBindPoint { VK_PIPELINE_BIND_POINT_GRAPHICS, VK_PIPELINE_BIND_POINT_COMPUTE };
enum VkDynamicState {
    VK_DYNAMIC_STATE_VIEWPORT, VK_DYNAMIC_STATE_SCISSOR, VK_DYNAMIC_STATE_LINE_WIDTH,
    VK_DYNAMIC_STATE_DEPTH_BIAS, VK_DYNAMIC_STATE_BLEND_CONSTANTS, VK_DYNAMIC_STATE_DEPTH_BOUNDS,
    VK_DYNAMIC_STATE_STENCIL_COMPARE_MASK, VK_DYNAMIC_STATE_STENCIL_WRITE_MASK, VK_DYNAMIC_STATE_STENCIL_REFERENCE,
    // Match the Vulkan enum's range so unknown extension values remain valid
    // enum representations under Clang's undefined-behavior sanitizer.
    VK_DYNAMIC_STATE_MAX_ENUM = 0x7fffffff
};
constexpr u32 VK_STENCIL_FACE_FRONT_BIT = 1, VK_STENCIL_FACE_BACK_BIT = 2;
constexpr u64 VK_NULL_HANDLE = 0;
struct VkPipelineDynamicStateCreateInfo { u32 dynamicStateCount; const VkDynamicState* pDynamicStates; };
#define ensure(x) assert(x)

using Value = std::array<u32, 4>;
constexpr unsigned slot_count = 10;
constexpr u32 all_states = (1u << slot_count) - 1;
struct Pipeline { u32 mask; std::array<Value, slot_count> static_values{}; };
std::array<Pipeline, 65> pipelines{};
struct Driver {
    std::array<Value, slot_count> values{};
    std::array<u64, 2> bound{};
    u32 valid = 0;
    u64 setters = 0, binds = 0;
};
void vkCmdBindPipeline(Driver* d, VkPipelineBindPoint point, VkPipeline p) {
    assert(p > 0 && p < pipelines.size());
    d->bound[point] = p; ++d->binds;
    if (point == VK_PIPELINE_BIND_POINT_GRAPHICS) d->valid &= pipelines[p].mask;
}
void store(Driver* d, unsigned s, Value value) { d->values[s] = value; d->valid |= 1u << s; }
void vkCmdSetLineWidth(Driver* d, float v) { store(d, 0, {std::bit_cast<u32>(v)}); ++d->setters; }
void vkCmdSetBlendConstants(Driver* d, const float* v) {
    store(d, 1, {std::bit_cast<u32>(v[0]),std::bit_cast<u32>(v[1]),std::bit_cast<u32>(v[2]),std::bit_cast<u32>(v[3])}); ++d->setters;
}
void vkCmdSetDepthBias(Driver* d, float a, float b, float c) {
    store(d, 2, {std::bit_cast<u32>(a),std::bit_cast<u32>(b),std::bit_cast<u32>(c)}); ++d->setters;
}
void vkCmdSetDepthBounds(Driver* d, float a, float b) {
    store(d, 3, {std::bit_cast<u32>(a),std::bit_cast<u32>(b)}); ++d->setters;
}
void stencil(Driver* d, unsigned front, VkStencilFaceFlags faces, u32 value) {
    if (faces & VK_STENCIL_FACE_FRONT_BIT) store(d, front, {value});
    if (faces & VK_STENCIL_FACE_BACK_BIT) store(d, front+1, {value});
    ++d->setters;
}
void vkCmdSetStencilWriteMask(Driver* d, VkStencilFaceFlags f, u32 v) { stencil(d, 4, f, v); }
void vkCmdSetStencilCompareMask(Driver* d, VkStencilFaceFlags f, u32 v) { stencil(d, 6, f, v); }
void vkCmdSetStencilReference(Driver* d, VkStencilFaceFlags f, u32 v) { stencil(d, 8, f, v); }

// @PRODUCTION@

template<class C> void set_states(C& c, u32 mask, const std::array<Value, slot_count>& v) {
    if (mask & 1) c.set_line_width(std::bit_cast<float>(v[0][0]));
    if (mask & 2) {
        const std::array<float,4> colors{std::bit_cast<float>(v[1][0]),std::bit_cast<float>(v[1][1]),std::bit_cast<float>(v[1][2]),std::bit_cast<float>(v[1][3])};
        c.set_blend_constants(colors.data());
    }
    if (mask & 4) c.set_depth_bias(std::bit_cast<float>(v[2][0]),std::bit_cast<float>(v[2][1]),std::bit_cast<float>(v[2][2]));
    if (mask & 8) c.set_depth_bounds(std::bit_cast<float>(v[3][0]),std::bit_cast<float>(v[3][1]));
    for (unsigned s=4;s<10;s+=2) {
        if (!(mask & (1u << s))) continue;
        auto apply=[&](u32 faces, u32 value) {
            if(s==4)c.set_stencil_write_mask(faces,value);
            if(s==6)c.set_stencil_compare_mask(faces,value);
            if(s==8)c.set_stencil_reference(faces,value);
        };
        if(v[s]==v[s+1]) apply(3,v[s][0]);
        else {apply(1,v[s][0]);apply(2,v[s+1][0]);}
    }
}
void draw_equal(const Driver& a, const Driver& b) {
    assert(a.bound == b.bound);
    const auto& p = pipelines[a.bound[0]];
    assert((a.valid & p.mask) == p.mask && (b.valid & p.mask) == p.mask);
    for(unsigned s=0;s<slot_count;++s) {
        const Value av=(p.mask&(1u<<s))?a.values[s]:p.static_values[s];
        const Value bv=(p.mask&(1u<<s))?b.values[s]:p.static_values[s];
        assert(av==bv);
    }
}
int main() {
    const std::array<u32,9> bits{0,0,1,4,2,8,192,48,768};
    unsigned mask_cases=0;
    for(u32 selection=0;selection<512;++selection) {
        std::vector<VkDynamicState> states; u32 expected=0;
        for(unsigned i=0;i<9;++i)if(selection&(1u<<i)){states.push_back(VkDynamicState(i));expected|=bits[i];}
        states.push_back(VkDynamicState(987654)); // an untracked extension state
        if(!states.empty())states.push_back(states.front());
        VkPipelineDynamicStateCreateInfo info{u32(states.size()),states.data()};
        assert(candidate::pipeline_dynamic_state_mask(&info)==expected); ++mask_cases;
    }
    assert(candidate::pipeline_dynamic_state_mask(nullptr)==0);
    VkPipelineDynamicStateCreateInfo empty{0,nullptr};
    assert(candidate::pipeline_dynamic_state_mask(&empty)==0);
    mask_cases+=2;

    std::mt19937 rng(0x588592);
    for(unsigned p=1;p<pipelines.size();++p) {
        auto& pipeline=pipelines[p];
        pipeline.mask=rng()&15;
        for(unsigned s=4;s<10;s+=2)if(rng()&1)pipeline.mask|=3u<<s;
        for(auto& v:pipeline.static_values)for(auto& u:v)u=rng();
    }
    pipelines[1].mask=pipelines[2].mask=all_states;
    pipelines[3].mask=0;
    Driver a{},b{}; reference::command_buffer before(&a); candidate::command_buffer after(&b);
    std::array<Value,slot_count> values{};
    // Identical guest state, alternating actual graphics pipelines.
    for(unsigned i=0;i<10000;++i) {
        const u64 p=1+i%2;
        before.bind_pipeline(p,VK_PIPELINE_BIND_POINT_GRAPHICS);
        after.bind_pipeline(p,VK_PIPELINE_BIND_POINT_GRAPHICS,pipelines[p].mask);
        set_states(before,all_states,values);set_states(after,all_states,values);draw_equal(a,b);
    }
    const u64 favorable_before=a.setters,favorable_after=b.setters;
    assert(favorable_before==70000 && favorable_after==7);

    const std::array<u32,8> edge{0,0x80000000u,0x3f800000u,0x7fc00001u,0x7fc00002u,0x7f800000u,0xff800000u,0xffffffffu};
    unsigned draws=0, resets=0, unknown_binds=0, compute_binds=0;
    for(unsigned i=0;i<100000;++i) {
        if(i%127==0) {
            before.clear_state_cache();after.clear_state_cache();a.valid=b.valid=0;a.bound={};b.bound={};++resets;
        }
        if(i%13==0) {
            const u64 p=1+rng()%64;
            before.bind_pipeline(p,VK_PIPELINE_BIND_POINT_COMPUTE);
            after.bind_pipeline(p,VK_PIPELINE_BIND_POINT_COMPUTE,all_states);++compute_binds;
        }
        const u64 p=1+rng()%64;
        before.bind_pipeline(p,VK_PIPELINE_BIND_POINT_GRAPHICS);
        if(i%11==0) {after.bind_pipeline(p,VK_PIPELINE_BIND_POINT_GRAPHICS);++unknown_binds;}
        else after.bind_pipeline(p,VK_PIPELINE_BIND_POINT_GRAPHICS,pipelines[p].mask);
        if(i%7==0)for(unsigned s=0;s<slot_count;++s){
            for(auto& word:values[s])word=(rng()%3)?rng():edge[rng()%edge.size()];
            if(s==0 || s>=4)values[s][1]=values[s][2]=values[s][3]=0;
            if(s==2)values[s][3]=0;
            if(s==3)values[s][2]=values[s][3]=0;
        }
        set_states(before,pipelines[p].mask,values);set_states(after,pipelines[p].mask,values);
        draw_equal(a,b);++draws;
    }
    assert(a.binds==b.binds);
    std::cout << "{\"mask_cases\":" << mask_cases << ",\"random_draws\":" << draws
        << ",\"resets\":" << resets << ",\"unknown_binds\":" << unknown_binds << ",\"compute_binds\":" << compute_binds
        << ",\"identical_state_switches\":10000,\"baseline_dynamic_commands\":" << favorable_before
        << ",\"candidate_dynamic_commands\":" << favorable_after
        << ",\"random_baseline_commands\":" << a.setters-favorable_before
        << ",\"random_candidate_commands\":" << b.setters-favorable_after << "}\n";
}
