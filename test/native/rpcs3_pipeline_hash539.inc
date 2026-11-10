unsigned test_hash(bool corrected) {
    auto make=[](unsigned a,unsigned b) {
        vk::pipeline_props p{};p.renderpass_key=1u<<16;
        p.state.set_attachment_count(2);
        p.state.att_state[0].colorWriteMask=a;p.state.att_state[1].colorWriteMask=b;
        return p;
    };
    auto hash=[](const auto& p){return rpcs3::hash_struct(p);};
    auto a=make(1,1),b=make(2,2),c=make(1,2),d=make(2,1);
    assert(!(a==b) && !(c==d));
    auto logic=a;logic.state.enable_logic_op(VK_LOGIC_OP_XOR);
    auto count=a;count.state.set_attachment_count(4);
    count.state.att_state[2].colorWriteMask=1;count.state.att_state[3].colorWriteMask=1;
    assert(!(logic==a) && !(count==a));
    unsigned eliminated=0;
    for (auto pair:{std::pair{a,b},std::pair{c,d},std::pair{a,logic},std::pair{a,count}}) {
        assert((hash(pair.first)!=hash(pair.second))==corrected);
        eliminated+=hash(pair.first)!=hash(pair.second);
    }
    // The mask is not passed to Vulkan for a one-sample pipeline. Hashing it
    // previously broke equal=>same-hash and made cache entries unreachable.
    auto mask=a; mask.state.temp_storage.msaa_sample_mask=0;
    assert(mask==a);
    assert((hash(mask)==hash(a))==corrected);
    // Alpha/sample shading are passed even for one sample: do not conflate them.
    auto alpha=a;alpha.state.ms.alphaToCoverageEnable=VK_TRUE;
    assert((alpha==a)==!corrected);
    assert(hash(alpha)!=hash(a));
    auto sample=a;sample.state.ms.sampleShadingEnable=VK_TRUE;sample.state.ms.minSampleShading=1;
    assert((sample==a)==!corrected);
    // Multisample masks continue to distinguish the actual pipeline inputs.
    auto ms=a;ms.renderpass_key=4u<<16;ms.state.ms.rasterizationSamples=VK_SAMPLE_COUNT_4_BIT;
    auto ms2=ms;ms2.state.temp_storage.msaa_sample_mask=0;
    assert(!(ms==ms2) && hash(ms)!=hash(ms2));
    auto copy=a;assert(copy==a && a==copy && hash(copy)==hash(a));
    assert(copy.state.cs.pAttachments==copy.state.att_state);
    // Existing serialized properties are layout-compatible; addresses are rebased
    // by the actual production copy constructor, not included in key hashing.
    static_assert(sizeof(vk::pipeline_props)==sizeof(before_hash::vk::pipeline_props));
    if(corrected) {
        std::unordered_map<vk::pipeline_props,unsigned,decltype(hash)> cache(0,hash);
        cache.emplace(a,1);assert(cache.at(mask)==1);
        cache.emplace(b,2);cache.emplace(c,3);cache.emplace(d,4);cache.emplace(logic,5);
        assert(cache.size()==5);
        for(unsigned value=0;value<4096;++value) {
            auto x=make(value&15,(value>>4)&15);x.state.cs.logicOpEnable=(value>>8)&1;
            x.state.cs.logicOp=static_cast<VkLogicOp>((value>>9)&7);
            auto y=x;y.state.temp_storage.msaa_sample_mask=value;
            assert(x==y && y==x && hash(x)==hash(y));
        }
    }
    return eliminated;
}
