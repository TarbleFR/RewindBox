// Creation-feedback interpretation, VkPipelineCache save skipping and the
// bounded fingerprint table. Production bodies are inserted at the markers;
// Vulkan entry points are fakes that only model the documented contract.
namespace feedback543 {
struct FakeDevice {
    mutable unsigned calls=0, additions=0;
    void note_pipeline_cache_update(bool added) const { ++calls; additions+=added; }
};
inline const FakeDevice* g_render_device=nullptr;
// CREATION_FEEDBACK
}

namespace save543 {
struct SaveLog { std::atomic<unsigned> notices{0}, warnings{0}; template<class... A> void notice(A&&...) { ++notices; } template<class... A> void warning(A&&...) { ++warnings; } };
inline SaveLog rsx_log;
inline unsigned queries=0, extra_on_read=0; inline std::vector<u8> driver_data(1000,0x5a);
inline bool fail_commit=false;
struct FakeGpu { struct { u32 vendorID=0x106b, deviceID=0x1234; u8 pipelineCacheUUID[VK_UUID_SIZE]{1,2,3}; } props; };
// SAVE_CONSTANTS
namespace fs {
inline bool create_path(const std::string&) { return true; }
inline std::string get_parent_dir(const std::string& p) { return p.substr(0,p.rfind('/')); }
inline std::vector<u8> committed;
struct pending_file {
    struct { std::vector<u8> bytes; explicit operator bool() const { return true; } u64 write(const void* d,u64 n) { auto* p=static_cast<const u8*>(d); bytes.insert(bytes.end(),p,p+n); return n; } } file;
    explicit pending_file(const std::string&) {}
    bool commit() { if (fail_commit) return false; committed=file.bytes; return true; }
};
}
class render_device;
VkResult fake_get_data(size_t* size, void* data);
inline VkResult vkGetPipelineCacheData(VkDevice, VkPipelineCache, size_t* size, void* data) { return fake_get_data(size,data); }
class render_device {
public:
    VkDevice dev=reinterpret_cast<VkDevice>(1); VkPipelineCache m_pipeline_cache=reinterpret_cast<VkPipelineCache>(2);
    std::string m_pipeline_cache_path="/cache/shaders_cache/vk_pipeline_cache.bin";
    FakeGpu gpu; FakeGpu* pgpu=&gpu;
    mutable std::atomic<bool> m_pipeline_cache_restored{false};
    mutable std::atomic<u64> m_pipeline_cache_unsaved{0};
    // NOTE_UPDATE
    // SAVE_BODY
};
inline render_device* active=nullptr;
VkResult fake_get_data(size_t* size, void* data) {
    ++queries;
    if (extra_on_read && data) { active->note_pipeline_cache_update(true); --extra_on_read; }
    if (!data) { *size=driver_data.size(); return VK_SUCCESS; }
    std::memcpy(data,driver_data.data(),std::min(*size,driver_data.size())); *size=driver_data.size(); return VK_SUCCESS;
}
}

struct FeedbackMetrics { unsigned bit_cases=0, save_cases=0, fingerprint_cases=0; };

FeedbackMetrics feedback_test() {
    FeedbackMetrics m;
    using feedback543::creation_feedback;
    // Every VALID/HIT combination for a vertex+fragment pipeline.
    VkPipelineShaderStageCreateInfo stages[2]{};
    stages[0].stage=VK_SHADER_STAGE_VERTEX_BIT; stages[1].stage=VK_SHADER_STAGE_FRAGMENT_BIT;
    for (u32 combo=0;combo<32;++combo) {
        creation_feedback fb; VkGraphicsPipelineCreateInfo info{VK_STRUCTURE_TYPE_GRAPHICS_PIPELINE_CREATE_INFO};
        int previous=7; info.pNext=&previous; info.stageCount=2;
        fb.chain(info,2);
        assert(info.pNext==&fb.info && fb.info.pNext==&previous && fb.info.pipelineStageCreationFeedbackCount==2);
        if (combo&1) fb.pipeline.flags|=VK_PIPELINE_CREATION_FEEDBACK_VALID_BIT;
        for (u32 s=0;s<2;++s) {
            if (combo&(2u<<(2*s))) fb.stages[s].flags|=VK_PIPELINE_CREATION_FEEDBACK_VALID_BIT;
            if (combo&(4u<<(2*s))) fb.stages[s].flags|=VK_PIPELINE_CREATION_FEEDBACK_APPLICATION_PIPELINE_CACHE_HIT_BIT;
        }
        u32 added=0; const u32 bits=fb.bits(stages,2,added);
        u32 expected=1|((combo&1)?2u:0u), expected_added=0;
        for (u32 s=0;s<2;++s) {
            const bool valid=combo&(2u<<(2*s)), hit=combo&(4u<<(2*s));
            if (!valid) continue; // A HIT bit without VALID is never interpreted.
            const u32 shift=s?4:2; expected|=(1u<<shift)|(hit?(2u<<shift):0u); expected_added+=!hit;
        }
        assert(bits==expected && added==expected_added);
        ++m.bit_cases;
    }
    {
        creation_feedback fb; VkGraphicsPipelineCreateInfo info{VK_STRUCTURE_TYPE_GRAPHICS_PIPELINE_CREATE_INFO};
        fb.chain(info,3); // More stages than storage: not chained.
        u32 added=9; assert(!fb.chained && info.pNext==nullptr && fb.bits(stages,2,added)==0 && added==0);
        ++m.bit_cases;
    }
    {
        using namespace feedback543;
        FakeDevice device; g_render_device=&device;
        creation_feedback chained; VkComputePipelineCreateInfo info{VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO};
        chained.chain(info,1);
        const VkPipelineCache cache=reinterpret_cast<VkPipelineCache>(1);
        note_cache_effect(cache,chained,0); note_cache_effect(cache,chained,2);
        note_cache_effect(cache,creation_feedback{},0); note_cache_effect(VK_NULL_HANDLE,creation_feedback{},0);
        assert(device.calls==3 && device.additions==2);
        g_render_device=nullptr; ++m.bit_cases;
    }
    // Save skipping: only a restored, unchanged cache is skipped.
    using namespace save543;
    auto run=[&](bool restored,u64 unsaved,bool failing,unsigned extra) {
        render_device device; active=&device; device.m_pipeline_cache_restored=restored; device.m_pipeline_cache_unsaved=unsaved;
        queries=0; fail_commit=failing; extra_on_read=extra; fs::committed.clear();
        device.save_pipeline_cache();
        return std::tuple{queries,fs::committed.size(),device.m_pipeline_cache_unsaved.load(),device.m_pipeline_cache_restored.load()};
    };
    {   auto [q,bytes,left,restored]=run(true,0,false,0); assert(q==0 && bytes==0 && left==0 && restored); ++m.save_cases; }
    {   auto [q,bytes,left,restored]=run(false,0,false,0); assert(q==2 && bytes==40+1000 && left==0 && restored); ++m.save_cases; }
    {   auto [q,bytes,left,restored]=run(true,3,false,0); assert(q==2 && bytes==1040 && left==0 && restored); ++m.save_cases; }
    {   auto [q,bytes,left,restored]=run(true,2,false,1); assert(q==2 && bytes==1040 && left==1 && restored); ++m.save_cases; }
    {   auto [q,bytes,left,restored]=run(false,4,true,0); assert(q==2 && bytes==0 && left==4 && !restored); ++m.save_cases; }
    {
        render_device device; active=&device; fail_commit=false; extra_on_read=0;
        device.m_pipeline_cache_restored=true; device.note_pipeline_cache_update(false);
        queries=0; fs::committed.clear(); device.save_pipeline_cache();
        assert(fs::committed.empty() && queries==0);
        device.note_pipeline_cache_update(true); queries=0; device.save_pipeline_cache();
        assert(queries==2 && device.m_pipeline_cache_unsaved==0);
        pipeline_cache_file_header header{}; std::memcpy(&header,fs::committed.data(),sizeof(header));
        assert(header.magic==pipeline_cache_file_magic && header.version==pipeline_cache_file_version);
        assert(header.header_size==sizeof(header) && header.data_size==1000 && header.vendor_id==0x106b && header.device_id==0x1234);
        assert(!std::memcmp(fs::committed.data()+sizeof(header),driver_data.data(),1000));
        ++m.save_cases;
    }
    // Bounded fingerprint aggregation.
    {
        using namespace rpcs3::ios::shader_timing;
        FingerprintTable table;
        for (int i=0;i<3;++i) table.record(42,100+i);
        for (u64 k=1;k<=70;++k) if (k!=42) table.record(1000+k,k*10);
        auto s=table.snapshot();
        assert(s.captured && s.distinct==64 && s.repeated_builds==2 && s.dropped==6);
        assert(s.repeated[0].fingerprint==42 && s.repeated[0].builds==3 && s.repeated[0].max_us==102 && s.repeated[0].total_us==303);
        assert(s.costliest[0].max_us>=s.costliest[1].max_us && s.costliest[1].max_us>=s.costliest[2].max_us);
        table.reset(); assert(table.snapshot().distinct==0 && table.snapshot().dropped==0);
        std::vector<std::thread> pool; std::atomic<unsigned> sent{0};
        for (u64 t=0;t<8;++t) pool.emplace_back([&,t] { for (u64 i=0;i<200;++i) { table.record(1+(t*200+i)%40,i); ++sent; } });
        for (auto& p:pool) p.join();
        s=table.snapshot();
        u64 recorded=s.distinct+s.repeated_builds; assert(recorded+s.dropped==sent && s.distinct<=40);
        PipelineContext c{1,2,3,4,5}; assert(FingerprintTable::fingerprint(c)==FingerprintTable::fingerprint(c));
        PipelineContext d=c; d.fragment_module=5; assert(FingerprintTable::fingerprint(c)!=FingerprintTable::fingerprint(d));
        PipelineProfile profile; profile.record_origin(1); profile.record_origin(2); profile.record_origin(3); profile.record_origin(4);
        profile.record_feedback(1|4|8|16); profile.record_feedback(0);
        auto sample=profile.take();
        assert(sample.new_vertex==2 && sample.new_fragment==2 && sample.state_only==1);
        assert(sample.feedback==1 && sample.vertex_cached==1 && sample.fragment_compiled==1 && sample.fragment_cached==0);
        m.fingerprint_cases=5;
    }
    return m;
}
