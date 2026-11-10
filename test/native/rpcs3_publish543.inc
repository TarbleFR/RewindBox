// Shader-cache publication cases. Compiled in namespace store_before (Build
// 542 inline writer) and store_after (Build 543 deferred writer).
struct StoreMetrics {
    unsigned records=0, files_verified=0, temp_files_left=0, producers=0, errors=0;
    double caller_p50_us=0, caller_max_us=0, caller_total_ms=0;
    unsigned fsyncs=0;
};

std::string scratch(const char* name) {
    char pattern[512]; std::snprintf(pattern,sizeof(pattern),"%s/%sXXXXXX",std::getenv("CELL543_SCRATCH"),name);
    std::string dir=::mkdtemp(pattern);
    for (const char* sub:{"/raw","/pipelines","/pipelines/vulkan","/pipelines/vulkan/v1.95"}) ::mkdir((dir+sub).c_str(),0755);
    return dir;
}

struct Sample {
    vk::pipeline_props props; RSXVertexProgram vp; RSXFragmentProgram fp;
};
Sample make_sample(u32 i) {
    Sample s;
    s.props.renderpass_key=VK_FORMAT_R8G8B8A8_UNORM|(1ull<<16); s.props.state.set_attachment_count(1);
    s.props.state.att_state[0].colorWriteMask=i&15; s.props.state.rs.lineWidth=float(i+1);
    s.vp.data={0x401f9c6cu,i,i*7u,0x0d8086c3u}; s.vp.ctrl=i&3; s.vp.output_mask=0xffff; s.vp.instruction_mask.set(0);
    s.vp.jump_table={1u,2u};
    s.fp.bytes.resize(48+16*(i%4)); for (usz b=0;b<s.fp.bytes.size();++b) s.fp.bytes[b]=u8(i*31+b);
    s.fp.ucode_length=u32(s.fp.bytes.size()); s.fp.ctrl=0x40; s.fp.mrt_buffers_count=1;
    return s;
}

std::vector<char> read_file(const std::string& path) {
    std::ifstream in(path,std::ios::binary); return {std::istreambuf_iterator<char>(in),{}};
}

unsigned verify(ShaderCache& cache, const std::string& root, const std::vector<Sample>& samples, unsigned& temps) {
    unsigned verified=0;
    for (const auto& s:samples) {
        const auto data=cache.expected(s.props,s.vp,s.fp);
        const auto record=read_file(cache.pipeline_path(data));
        assert(record.size()==sizeof(data));
        // The record embeds the process-local cs.pAttachments pointer (pre-existing
        // format; the loader rebases it). Compare every other byte.
        alignas(ShaderCache::pipeline_data) unsigned char stored[sizeof(ShaderCache::pipeline_data)];
        std::memcpy(stored,record.data(),sizeof(stored));
        const auto offset=offsetof(ShaderCache::pipeline_data,pipeline_properties)+offsetof(vk::pipeline_props,state)+
            offsetof(vk::graphics_pipeline_state,cs)+offsetof(VkPipelineColorBlendStateCreateInfo,pAttachments);
        std::memcpy(stored+offset,reinterpret_cast<const unsigned char*>(&data)+offset,sizeof(void*));
        assert(!std::memcmp(stored,&data,sizeof(data)));
        const auto vp=read_file(root+"/raw/"+fmt::format("%llX.vp",data.vertex_program_hash));
        assert(vp.size()==s.vp.data.size()*4 && !std::memcmp(vp.data(),s.vp.data.data(),vp.size()));
        const auto fp=read_file(root+"/raw/"+fmt::format("%llX.fp",data.fragment_program_hash));
        assert(fp.size()==s.fp.bytes.size() && !std::memcmp(fp.data(),s.fp.bytes.data(),fp.size()));
        ++verified;
    }
    temps=0;
    for (auto& entry:std::filesystem::recursive_directory_iterator(root)) temps+=entry.path().string().find(".tmp")!=std::string::npos;
    return verified;
}

StoreMetrics store_test(unsigned records, unsigned producers, int delay_us) {
    StoreMetrics m; m.records=records; m.producers=producers;
    fs::commit_delay_us=delay_us; fs::fsyncs=0; rsx_log.errors=0;
    const auto root=scratch("store");
    std::vector<Sample> samples; for (u32 i=0;i<records;++i) samples.push_back(make_sample(i));
    std::vector<double> caller_us(records);
    {
        ShaderCache cache(root);
        std::vector<std::thread> pool;
        for (unsigned t=0;t<producers;++t) pool.emplace_back([&,t] {
            for (unsigned i=t;i<records;i+=producers) {
                const auto start=std::chrono::steady_clock::now();
                cache.store(samples[i].props,samples[i].vp,samples[i].fp);
                caller_us[i]=std::chrono::duration<double,std::micro>(std::chrono::steady_clock::now()-start).count();
            }
        });
        for (auto& p:pool) p.join();
#ifdef CELL543_AFTER
        cache.flush_pending_writes(); // Durable before the cache is released.
        unsigned temps=0; m.files_verified=verify(cache,root,samples,temps); assert(!temps);
#endif
    } // Destruction drains any queued record.
    {
        ShaderCache reader(root); unsigned temps=0;
        m.files_verified=verify(reader,root,samples,temps); m.temp_files_left=temps;
    }
    auto sorted=caller_us; std::sort(sorted.begin(),sorted.end());
    m.caller_p50_us=sorted[sorted.size()/2]; m.caller_max_us=sorted.back();
    m.caller_total_ms=std::accumulate(sorted.begin(),sorted.end(),0.0)/1000.0;
    m.fsyncs=fs::fsyncs; m.errors=rsx_log.errors;
    assert(m.files_verified==records && !m.temp_files_left && !m.errors);
    std::filesystem::remove_all(root);
    return m;
}
