Props make_props(unsigned layouts=0) {
    Props p{};p.renderpass_key=VK_FORMAT_R8G8B8A8_UNORM | (u64(VK_FORMAT_D32_SFLOAT_S8_UINT)<<8) | (1ull<<16);
    for(unsigned i=0;i<5;++i) p.renderpass_key|=u64(layouts&(1u<<i)?1:(i==4?3:2))<<(22+3*i);
    p.state.set_attachment_count(4);p.state.att_state[0].colorWriteMask=15;
    return p;
}
std::array<unsigned,4> test(bool corrected) {
    std::array<unsigned,4> builds{};
    for(unsigned family=0;family<4;++family) {
        Cache cache;cache.new_fragment(20,15);auto initial=Traits::builds;
        Pipeline* first=nullptr;
        unsigned requests=family==0?32:16;
        for(unsigned i=0;i<requests;++i) {
            auto p=make_props(family==0?i:0);
            auto& a=p.state.att_state[0];
            if(family) {
                a.blendEnable=VK_TRUE;a.srcColorBlendFactor=VK_BLEND_FACTOR_SRC_ALPHA;
                a.dstColorBlendFactor=VK_BLEND_FACTOR_ONE_MINUS_SRC_ALPHA;
                a.srcAlphaBlendFactor=static_cast<VkBlendFactor>(i);a.dstAlphaBlendFactor=VK_BLEND_FACTOR_ONE;
                if(family==1) a.colorWriteMask=0;
                if(family==2) a.colorWriteMask=7;
                if(family==3) {a.alphaBlendOp=VK_BLEND_OP_MIN;a.colorBlendOp=VK_BLEND_OP_MAX;a.srcColorBlendFactor=static_cast<VkBlendFactor>(i);}
            }
            auto original=p;
            auto pipe=std::get<0>(cache.get_graphics_pipeline(nullptr,RSXVertexProgram{},RSXFragmentProgram{},p,false,true));
            assert(p==original); // Never modify caller's guest state.
            if(!first) first=pipe;
            if(corrected) assert(pipe==first);
        }
        builds[family]=Traits::builds-initial;
        assert(builds[family]==(corrected?1:requests));
    }
    // Material state differences, including feedback-loop and input references,
    // must not become the same pipeline. Preserve the complete ordered hash.
    Cache distinct;distinct.new_fragment(30,15);
    auto base=make_props();auto add=[&](Props p) {return std::get<0>(distinct.get_graphics_pipeline(nullptr,RSXVertexProgram{},RSXFragmentProgram{},p,false,true));};
    auto first=add(base);
    std::vector<Props> variants;
    auto v=base;v.renderpass_key^=1;variants.push_back(v);
    v=base;v.renderpass_key^=1ull<<37;variants.push_back(v);
    v=base;v.renderpass_key&=~(7ull<<34);variants.push_back(v);
    v=base;v.renderpass_key=(v.renderpass_key&~(7ull<<22))|(4ull<<22);variants.push_back(v);
    v=base;v.state.att_state[0].colorWriteMask=0;variants.push_back(v);
    v=base;v.state.att_state[0].blendEnable=VK_TRUE;v.state.att_state[0].srcColorBlendFactor=VK_BLEND_FACTOR_SRC_ALPHA;variants.push_back(v);
    v=base;v.state.ds.depthTestEnable=VK_TRUE;variants.push_back(v);
    v=base;v.state.ms.alphaToCoverageEnable=VK_TRUE;variants.push_back(v);
    for(auto p:variants) assert(add(p)!=first);
    // Pending work coalesces too; the callback retains the same normalized key.
    Cache async;async.new_fragment(40,15);auto start=Traits::builds;
    for(unsigned i=0;i<32;++i) {auto p=make_props(i);assert(!std::get<0>(async.get_graphics_pipeline(nullptr,RSXVertexProgram{},RSXFragmentProgram{},p,true,true)));}
    assert(Traits::builds-start==(corrected?1u:32u));
    for(auto& done:Traits::pending) done();
    Traits::pending.clear();
    auto p=make_props(31);assert(std::get<0>(async.get_graphics_pipeline(nullptr,RSXVertexProgram{},RSXFragmentProgram{},p,true,true)));
    assert(async.published.size()==(corrected?1u:32u));
    return builds;
}
// Independent Vulkan basic blending reference. Factors are read from the
// original shader outputs even when the corresponding write channel is masked.
using Color=std::array<double,4>;
double factor(VkBlendFactor f,unsigned c,const Color& s,const Color& d) {
    const Color constant{0.2,0.4,0.6,0.8},second{0.8,0.6,0.4,0.2};
    switch(f) {
    case VK_BLEND_FACTOR_ZERO:return 0;case VK_BLEND_FACTOR_ONE:return 1;
    case VK_BLEND_FACTOR_SRC_COLOR:return s[c];case VK_BLEND_FACTOR_ONE_MINUS_SRC_COLOR:return 1-s[c];
    case VK_BLEND_FACTOR_DST_COLOR:return d[c];case VK_BLEND_FACTOR_ONE_MINUS_DST_COLOR:return 1-d[c];
    case VK_BLEND_FACTOR_SRC_ALPHA:return s[3];case VK_BLEND_FACTOR_ONE_MINUS_SRC_ALPHA:return 1-s[3];
    case VK_BLEND_FACTOR_DST_ALPHA:return d[3];case VK_BLEND_FACTOR_ONE_MINUS_DST_ALPHA:return 1-d[3];
    case VK_BLEND_FACTOR_CONSTANT_COLOR:return constant[c];case VK_BLEND_FACTOR_ONE_MINUS_CONSTANT_COLOR:return 1-constant[c];
    case VK_BLEND_FACTOR_CONSTANT_ALPHA:return constant[3];case VK_BLEND_FACTOR_ONE_MINUS_CONSTANT_ALPHA:return 1-constant[3];
    case VK_BLEND_FACTOR_SRC_ALPHA_SATURATE:return c==3?1:std::min(s[3],1-d[3]);
    case VK_BLEND_FACTOR_SRC1_COLOR:return second[c];case VK_BLEND_FACTOR_ONE_MINUS_SRC1_COLOR:return 1-second[c];
    case VK_BLEND_FACTOR_SRC1_ALPHA:return second[3];case VK_BLEND_FACTOR_ONE_MINUS_SRC1_ALPHA:return 1-second[3];
    default:assert(false);return 0;
    }
}
Color reference(const VkPipelineColorBlendAttachmentState& a,const Color& s,const Color& d) {
    auto result=d;
    for(unsigned c=0;c<4;++c) {
        if(!(a.colorWriteMask&(1u<<c))) continue;
        if(!a.blendEnable) {result[c]=s[c];continue;}
        auto op=c==3?a.alphaBlendOp:a.colorBlendOp;
        if(op==VK_BLEND_OP_MIN) {result[c]=std::min(s[c],d[c]);continue;}
        if(op==VK_BLEND_OP_MAX) {result[c]=std::max(s[c],d[c]);continue;}
        auto left=s[c]*factor(c==3?a.srcAlphaBlendFactor:a.srcColorBlendFactor,c,s,d);
        auto right=d[c]*factor(c==3?a.dstAlphaBlendFactor:a.dstColorBlendFactor,c,s,d);
        result[c]=op==VK_BLEND_OP_ADD?left+right:op==VK_BLEND_OP_SUBTRACT?left-right:right-left;
    }
    return result;
}
unsigned semantic_test() {
    unsigned cases=0;
#ifdef CELL542_AFTER
    for(unsigned mask=0;mask<16;++mask) for(unsigned enabled=0;enabled<2;++enabled)
    for(unsigned op=0;op<5;++op) for(unsigned src=0;src<19;++src) for(unsigned dst=0;dst<19;++dst) {
        auto p=make_props();auto& a=p.state.att_state[0];a.colorWriteMask=mask;a.blendEnable=enabled;
        a.colorBlendOp=VkBlendOp(op);a.alphaBlendOp=VkBlendOp((op+2)%5);
        a.srcColorBlendFactor=VkBlendFactor(src);a.dstColorBlendFactor=VkBlendFactor(dst);
        a.srcAlphaBlendFactor=VkBlendFactor(dst);a.dstAlphaBlendFactor=VkBlendFactor(src);
        auto old=a;normalize_pipeline_blending(p.state);
        for(auto colors:{std::pair{Color{0,0.5,1,0},Color{1,0.25,0,1}},std::pair{Color{0.1,0.8,0.4,0.75},Color{0.7,0.3,0.6,0.2}}})
            {assert(reference(old,colors.first,colors.second)==reference(a,colors.first,colors.second));++cases;}
        auto repeat=p;normalize_pipeline_blending(repeat.state);assert(p==repeat && rpcs3::hash_struct(p)==rpcs3::hash_struct(repeat));
    }
    for(u64 slots=0;slots<32768;++slots) {
        auto key=(slots<<22)|0xf000002000010025ull;
        auto norm=compatible_pipeline_renderpass_key(key);
        assert(compatible_pipeline_renderpass_key(norm)==norm);
        assert((key&~(32767ull<<22))==(norm&~(32767ull<<22)));
        for(unsigned sh=22;sh<37;sh+=3) {u64 a=(key>>sh)&7,b=(norm>>sh)&7;assert(b==((a==2||a==3)?1:a));}
    }
#endif
    return cases;
}
