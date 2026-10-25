// Build 543 lookup cases, compiled once against the Build 542 body (before)
// and once against the Build 543 body (after). Synthetic requests only.
struct LookupMetrics {
    unsigned concurrent_requests=0, concurrent_builds=0, concurrent_null_returns=0, concurrent_distinct=0;
    unsigned preload_builds=0, preload_null_returns=0;
    unsigned failure_builds=0, failure_exceptions=0, failure_null_returns=0, failure_sticky_null=0;
    unsigned null_result_retry_null=0;
    unsigned async_requests=0, async_jobs=0;
    unsigned miss_flag_mismatches=0;
    unsigned ds_requests[5]{}, ds_builds[5]{};
    unsigned hash_pairs=0, hash_distinct=0;
};

Props ds_props(u64 depth_format) {
    Props p{};
    p.renderpass_key=VK_FORMAT_R8G8B8A8_UNORM | (depth_format<<8) | (1ull<<16) | (2ull<<22) | (3ull<<25);
    p.state.set_attachment_count(1); p.state.att_state[0].colorWriteMask=15;
    p.state.ds.depthBoundsTestEnable=VK_TRUE;
    return p;
}

Pipeline* lookup(Cache& cache, Props props, bool async=false, bool notify=true) {
    return std::get<0>(cache.get_graphics_pipeline(nullptr,RSXVertexProgram{},RSXFragmentProgram{},props,async,notify));
}

// Every thread starts together; the first claims the build, the others race it.
std::vector<Pipeline*> concurrent(Cache& cache, const Props& props, unsigned threads, bool notify,
                                  unsigned& exceptions) {
    std::atomic<unsigned> ready{0}, thrown{0};
    std::atomic<bool> go{false};
    std::vector<Pipeline*> results(threads,nullptr);
    std::vector<std::thread> pool;
    for (unsigned i=0;i<threads;++i) pool.emplace_back([&,i] {
        ++ready; while (!go.load()) std::this_thread::yield();
        // Stagger arrivals so later requests meet the in-flight placeholder.
        if (i) std::this_thread::sleep_for(std::chrono::milliseconds(2));
        try { results[i]=lookup(cache,props,false,notify); } catch (const std::runtime_error&) { ++thrown; }
    });
    while (ready.load()<threads) std::this_thread::yield();
    go=true;
    for (auto& t:pool) t.join();
    exceptions=thrown.load();
    return results;
}

// Literal Vulkan visibility of depth/stencil state for an attachment format.
// Never merges states the spec distinguishes; independent of the normalizer.
std::vector<u32> observable_depth_stencil(const VkPipelineDepthStencilStateCreateInfo& ds, u32 format) {
    std::vector<u32> out;
    if (!format) return out; // No depth/stencil attachment: pDepthStencilState is ignored.
    out.push_back(ds.depthTestEnable);
    if (ds.depthTestEnable) { out.push_back(ds.depthCompareOp); out.push_back(ds.depthWriteEnable); }
    out.push_back(ds.depthBoundsTestEnable);
    const bool stencil_aspect=format==VK_FORMAT_D24_UNORM_S8_UINT||format==VK_FORMAT_D32_SFLOAT_S8_UINT||format==VK_FORMAT_D16_UNORM_S8_UINT;
    out.push_back(stencil_aspect && ds.stencilTestEnable);
    if (stencil_aspect && ds.stencilTestEnable) {
        for (const auto& f:{ds.front,ds.back}) {
            out.insert(out.end(),{u32(f.failOp),u32(f.passOp),u32(f.depthFailOp),u32(f.compareOp),f.compareMask,f.writeMask,f.reference});
        }
    }
    return out;
}

std::vector<VkPipelineDepthStencilStateCreateInfo> realistic_ds_variants(bool depth_variants, bool stencil_variants) {
    // Mirrors decode_rsx_state(): disabled tests leave their fields zero.
    std::vector<VkPipelineDepthStencilStateCreateInfo> depth;
    VkPipelineDepthStencilStateCreateInfo off{}; off.sType=VK_STRUCTURE_TYPE_PIPELINE_DEPTH_STENCIL_STATE_CREATE_INFO; off.depthBoundsTestEnable=VK_TRUE;
    depth.push_back(off);
    if (depth_variants) for (u32 op=0;op<8;++op) for (u32 write=0;write<2;++write) {
        auto d=off; d.depthTestEnable=VK_TRUE; d.depthCompareOp=VkCompareOp(op); d.depthWriteEnable=write; depth.push_back(d);
    }
    std::vector<VkPipelineDepthStencilStateCreateInfo> result;
    for (const auto& d:depth) {
        result.push_back(d);
        if (!stencil_variants) continue;
        for (u32 v=0;v<6;++v) {
            auto s=d; s.stencilTestEnable=VK_TRUE;
            s.front.failOp=VkStencilOp(v%3); s.front.passOp=VkStencilOp((v+1)%8); s.front.depthFailOp=VK_STENCIL_OP_KEEP;
            s.front.compareOp=VkCompareOp(v%8); s.front.compareMask=0xFF; s.front.writeMask=0xFF; s.front.reference=0xFF;
            s.back=s.front; if (v&1) s.back.passOp=VK_STENCIL_OP_INVERT;
            result.push_back(s);
        }
    }
    return result;
}

LookupMetrics lookup_test() {
    LookupMetrics m;
    // 1. Draw requests for one key while it is being built inline.
    {
        Traits::reset(); Traits::delay_us=30000;
        Cache cache; cache.mark_known(); unsigned thrown=0;
        auto results=concurrent(cache,ds_props(VK_FORMAT_D32_SFLOAT_S8_UINT),16,true,thrown);
        assert(!thrown);
        m.concurrent_requests=16; m.concurrent_builds=Traits::builds;
        std::set<Pipeline*> distinct;
        for (auto* p:results) { m.concurrent_null_returns+=!p; if (p) distinct.insert(p); }
        m.concurrent_distinct=unsigned(distinct.size());
        assert(m.concurrent_builds==1 && distinct.size()==1);
#ifdef CELL543_AFTER
        assert(m.concurrent_null_returns==0 && cache.entries()==1 && !cache.null_entries());
#endif
    }
    // 2. Cached-shader preload duplicates do not need the result: no waiting.
    {
        Traits::reset(); Traits::delay_us=30000;
        Cache cache; cache.mark_known(); unsigned thrown=0;
        auto start=std::chrono::steady_clock::now();
        auto results=concurrent(cache,ds_props(VK_FORMAT_D32_SFLOAT_S8_UINT),8,false,thrown);
        m.preload_builds=Traits::builds;
        for (auto* p:results) m.preload_null_returns+=!p;
        assert(!thrown && m.preload_builds==1 && m.preload_null_returns==7);
        // Losers return immediately; the single build bounds the whole phase.
        assert(std::chrono::steady_clock::now()-start<std::chrono::milliseconds(2000));
        assert(lookup(cache,ds_props(VK_FORMAT_D32_SFLOAT_S8_UINT)));
    }
    // 3. A failing build must not poison the key nor drop the waiting draws.
    {
        Traits::reset(); Traits::delay_us=30000; Traits::throw_on=1;
        Cache cache; cache.mark_known(); unsigned thrown=0;
        auto results=concurrent(cache,ds_props(VK_FORMAT_D32_SFLOAT_S8_UINT),4,true,thrown);
        m.failure_exceptions=thrown;
        for (auto* p:results) m.failure_null_returns+=!p;
        Traits::delay_us=0;
        m.failure_sticky_null=!lookup(cache,ds_props(VK_FORMAT_D32_SFLOAT_S8_UINT));
        m.failure_builds=Traits::builds;
        assert(thrown==1);
#ifdef CELL543_AFTER
        // Thread 0 threw; the three waiters retried once and shared build 2.
        assert(m.failure_null_returns==1 && !m.failure_sticky_null && m.failure_builds==2);
        assert(cache.entries()==1 && !cache.null_entries());
#endif
    }
    // 4. An inline build that returned nothing allows a later retry.
    {
        Traits::reset(); Traits::return_null=true;
        Cache cache;
        assert(!lookup(cache,ds_props(0)));
        Traits::return_null=false;
        m.null_result_retry_null=!lookup(cache,ds_props(0));
#ifdef CELL543_AFTER
        assert(!m.null_result_retry_null && Traits::builds==2);
#endif
    }
    // 5. Deferred requests coalesce into one job and then publish.
    {
        Traits::reset(); Cache cache;
        for (unsigned i=0;i<8;++i) assert(!lookup(cache,ds_props(0),true));
        m.async_requests=8; m.async_jobs=unsigned(Traits::pending.size());
        assert(m.async_jobs==1 && Traits::builds==1);
        Traits::pending.front()(); Traits::pending.clear();
        assert(lookup(cache,ds_props(0),true) && Traits::builds==1 && cache.published.size()==1);
    }
#ifdef CELL543_AFTER
    // 6. The miss flag belongs to the requesting thread.
    {
        Traits::reset(); Cache cache; cache.mark_known();
        auto hit=ds_props(VK_FORMAT_D16_UNORM); assert(lookup(cache,hit));
        std::atomic<unsigned> bad{0};
        std::thread hits([&] { for (int i=0;i<3000;++i) { assert(lookup(cache,hit)); bad+=Cache::cache_missed(); } });
        std::thread misses([&] { for (u64 i=0;i<3000;++i) { auto p=ds_props(VK_FORMAT_D16_UNORM); p.state.rs.lineWidth=float(i+2); assert(lookup(cache,p)); bad+=!Cache::cache_missed(); } });
        hits.join(); misses.join();
        m.miss_flag_mismatches=bad;
        assert(!bad);
    }
#endif
    // 7. Depth/stencil state that the render pass cannot observe.
    {
        struct Family { u64 format; bool depth, stencil; };
        const Family families[5]={{0,true,true},{VK_FORMAT_D16_UNORM,false,true},{VK_FORMAT_D32_SFLOAT,true,true},
                                  {VK_FORMAT_D24_UNORM_S8_UINT,false,true},{VK_FORMAT_D32_SFLOAT_S8_UINT,true,false}};
        for (unsigned f=0;f<5;++f) {
            Traits::reset(); Cache cache; cache.new_fragment(50+f,15);
            const auto variants=realistic_ds_variants(families[f].depth,families[f].stencil);
            std::map<std::vector<u32>,Pipeline*> by_behavior;
            for (const auto& ds:variants) {
                auto p=ds_props(families[f].format); p.state.ds=ds; const auto original=p;
                auto* pipe=lookup(cache,p);
                assert(pipe && p==original); // Guest state stays intact.
                auto [it,inserted]=by_behavior.try_emplace(observable_depth_stencil(ds,u32(families[f].format)),pipe);
                // Equal visible behavior may share; different behavior never shares.
                if (!inserted) { (void)it; }
                for (auto& [behavior,other]:by_behavior) if (behavior!=observable_depth_stencil(ds,u32(families[f].format))) assert(other!=pipe);
            }
            m.ds_requests[f]=unsigned(variants.size()); m.ds_builds[f]=Traits::builds;
#ifdef CELL543_AFTER
            assert(m.ds_builds[f]==by_behavior.size());
#else
            assert(m.ds_builds[f]==variants.size());
#endif
        }
    }
    // 8. Key hash: identical state, 64 x 64 program identifiers.
    {
        std::set<usz> distinct;
        for (u32 v=0;v<64;++v) for (u32 f=0;f<64;++f) {
            Cache::pipeline_key key{v,f,ds_props(0)};
#ifdef CELL543_AFTER
            key.hash=Cache::pipeline_key_hash::compute(key);
#endif
            distinct.insert(Cache::pipeline_key_hash{}(key));
        }
        m.hash_pairs=64*64; m.hash_distinct=unsigned(distinct.size());
#ifdef CELL543_AFTER
        assert(m.hash_distinct==m.hash_pairs);
        Cache::pipeline_key a{1,2,ds_props(0)}, b{1,2,ds_props(VK_FORMAT_D16_UNORM)};
        a.hash=Cache::pipeline_key_hash::compute(a); b.hash=a.hash; // Forced collision.
        assert(!Cache::pipeline_key_compare{}(a,b));
        b=a; assert(Cache::pipeline_key_compare{}(a,b));
#endif
    }
    return m;
}

#ifdef CELL543_AFTER
// Exhaustive grid against the literal reference: one normalized key per
// visible behavior and one visible behavior per normalized key.
unsigned ds_reference_test() {
    unsigned cases=0;
    // RSX keys only encode D16, D32F, D24S8 and D32S8; D16S8 also has both aspects.
    const u32 formats[]={0,VK_FORMAT_D16_UNORM,VK_FORMAT_D32_SFLOAT,VK_FORMAT_D24_UNORM_S8_UINT,VK_FORMAT_D32_SFLOAT_S8_UINT,VK_FORMAT_D16_UNORM_S8_UINT};
    for (u32 format:formats) {
        std::map<std::vector<u8>,std::vector<u32>> key_to_behavior;
        std::map<std::vector<u32>,std::vector<u8>> behavior_to_key;
        for (u32 test=0;test<2;++test) for (u32 op=0;op<8;op+=3) for (u32 write=0;write<2;++write) for (u32 bounds=0;bounds<2;++bounds)
        for (u32 stencil=0;stencil<2;++stencil) for (u32 fail=0;fail<3;++fail) for (u32 pass=0;pass<2;++pass) for (u32 cmp=0;cmp<8;cmp+=7)
        for (u32 back=0;back<2;++back) for (u32 mask=0;mask<2;++mask) {
            graphics_pipeline_state s; auto& ds=s.ds;
            ds.depthTestEnable=test; ds.depthCompareOp=VkCompareOp(op); ds.depthWriteEnable=write; ds.depthBoundsTestEnable=bounds;
            ds.stencilTestEnable=stencil; ds.front.failOp=VkStencilOp(fail); ds.front.passOp=VkStencilOp(pass*2);
            ds.front.compareOp=VkCompareOp(cmp); ds.front.compareMask=mask?0x0F:0xFF; ds.front.writeMask=0xFF; ds.front.reference=mask;
            ds.back=ds.front; if (back) ds.back.depthFailOp=VK_STENCIL_OP_ZERO;
            const auto behavior=observable_depth_stencil(ds,format);
            auto n=s; normalize_pipeline_depth_stencil(n,u64(format)<<8);
            assert(observable_depth_stencil(n.ds,format)==behavior); // Sound: behavior preserved.
            auto again=n; normalize_pipeline_depth_stencil(again,u64(format)<<8);
            assert(!std::memcmp(&again.ds,&n.ds,sizeof(n.ds))); // Idempotent.
            std::vector<u8> bytes(reinterpret_cast<const u8*>(&n.ds),reinterpret_cast<const u8*>(&n.ds)+sizeof(n.ds));
            auto [k,ki]=key_to_behavior.try_emplace(bytes,behavior); assert(k->second==behavior);
            auto [b,bi]=behavior_to_key.try_emplace(behavior,bytes); assert(b->second==bytes);
            ++cases;
        }
    }
    return cases;
}
#endif
