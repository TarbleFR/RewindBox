// Portable adapters around the extracted production lookup and Vulkan validation.
// No Vulkan/Metal compilation or device performance is simulated here.
using u32 = unsigned; using usz = std::size_t;
struct Attachment { u32 colorWriteMask{}; bool operator==(const Attachment&) const = default; };
struct Props {
    struct { Attachment att_state[4]{}; } state;
    u32 renderpass_key{};
    bool operator==(const Props& b) const {
        return renderpass_key == b.renderpass_key &&
            std::equal(std::begin(state.att_state), std::end(state.att_state), std::begin(b.state.att_state));
    }
};
namespace vk { using pipeline_props = Props; }
namespace rpcs3 {
template<class T> usz hash_base(T v) { return v; }
template<class T> usz hash_struct(const T& p) {
    usz h=p.renderpass_key;
    for (auto a:p.state.att_state) h=h*31+a.colorWriteMask;
    return h;
}
}
struct Shader { unsigned id=1; unsigned output_color_masks[4]{1,0,0,0}; };
using VKVertexProgram=Shader; using VKFragmentProgram=Shader;
struct RSXVertexProgram {};
struct RSXFragmentProgram { static RSXFragmentProgram clone(const RSXFragmentProgram& p) { return p; } };
namespace rsx { struct program_cache_hint_t {}; }
struct Pipeline { Props props; };
struct Log { template<class... A> void notice(A&&...) {} template<class... A> void success(A&&...) {} };
inline Log rsx_log;
using reader_lock=std::shared_lock<std::shared_mutex>;
struct Traits {
    using pipeline_storage_type=std::unique_ptr<Pipeline>;
    using pipeline_type=Pipeline;
    inline static unsigned builds=0;
    inline static std::vector<std::function<void()>> pending;
    static // VALIDATION
    static Pipeline* build_pipeline(const Shader&,const Shader&,const Props& props,bool async,
                                    std::function<Pipeline*(pipeline_storage_type&)> callback) {
        ++builds;
        if (async) {
            pending.emplace_back([props,callback] { auto p=std::make_unique<Pipeline>(Pipeline{props}); callback(p); });
            return nullptr;
        }
        auto p=std::make_unique<Pipeline>(Pipeline{props}); return callback(p);
    }
};
class Cache {
    using backend_traits=Traits;
    using pipeline_properties=Props; using pipeline_type=Pipeline;
    using pipeline_storage_type=std::unique_ptr<Pipeline>;
    using vertex_program_type=Shader; using fragment_program_type=Shader;
    using pipeline_data_type=std::tuple<Pipeline*,const Shader*,const Shader*>;
    // KEY_TYPES
    std::shared_mutex m_pipeline_mutex;
    std::unordered_map<pipeline_key,pipeline_storage_type,pipeline_key_hash,pipeline_key_compare> m_storage;
    pipeline_storage_type __null_pipeline_handle;
    bool m_cache_miss_flag{};
    Shader vertex{1},fragment{2};
    bool seen_vertex=false,seen_fragment=false;
    auto search_vertex_program(rsx::program_cache_hint_t*,const RSXVertexProgram&) {
        bool seen=std::exchange(seen_vertex,true); return std::tuple<const Shader&,bool>(vertex,seen);
    }
    auto search_fragment_program(rsx::program_cache_hint_t*,const RSXFragmentProgram&) {
        bool seen=std::exchange(seen_fragment,true); return std::tuple<const Shader&,bool>(fragment,seen);
    }
    void notify_pipeline_compiled(const Props& props,const RSXVertexProgram&,const RSXFragmentProgram&) {
        published.push_back(props);
    }
public:
    std::vector<Props> published;
    void new_fragment(unsigned id, unsigned mask) { fragment.id=id; fragment.output_color_masks[0]=mask; seen_fragment=false; }
    std::size_t entries() const { return m_storage.size(); }
    // LOOKUP
};
unsigned test(bool corrected) {
    Traits::builds=0; Cache cache; Pipeline* first=nullptr;
    for (unsigned i=0;i<1000;++i) {
        Props props{}; props.state.att_state[0].colorWriteMask=15-2*(i%8);
        auto [pipeline,vs,fs]=cache.get_graphics_pipeline(nullptr,RSXVertexProgram{},RSXFragmentProgram{},props,false,true);
        assert(pipeline && vs && fs);
        if (!first) first=pipeline;
        if (corrected) { assert(props.state.att_state[0].colorWriteMask==15-2*(i%8)); assert(pipeline==first); assert(pipeline->props.state.att_state[0].colorWriteMask==1); }
    }
    const auto builds=Traits::builds;
    assert(builds==(corrected?1u:8u));
    assert(cache.entries()==builds && cache.published.size()==builds);
    if (corrected) assert(cache.published.front().state.att_state[0].colorWriteMask==1);
    // A meaningful guest change must still create a distinct pipeline.
    Props no_write{};
    auto [disabled,vs,fs]=cache.get_graphics_pipeline(nullptr,RSXVertexProgram{},RSXFragmentProgram{},no_write,false,true);
    assert(disabled!=first && disabled->props.state.att_state[0].colorWriteMask==0);
    Props different_pass{}; different_pass.renderpass_key=2; different_pass.state.att_state[0].colorWriteMask=1;
    auto [pass,vs2,fs2]=cache.get_graphics_pipeline(nullptr,RSXVertexProgram{},RSXFragmentProgram{},different_pass,false,true);
    assert(pass!=first && pass!=disabled);
    cache.new_fragment(3,2); Props changed{}; changed.state.att_state[0].colorWriteMask=3;
    auto [shader,vs3,fs3]=cache.get_graphics_pipeline(nullptr,RSXVertexProgram{},RSXFragmentProgram{},changed,false,true);
    assert(shader!=first && shader!=disabled);
    if (corrected) assert(shader->props.state.att_state[0].colorWriteMask==2);
    // Shader changes must not progressively intersect the caller's guest mask.
    if (corrected) {
        Cache channels; Props guest{}; guest.state.att_state[0].colorWriteMask=15;
        auto first=std::get<0>(channels.get_graphics_pipeline(nullptr,RSXVertexProgram{},RSXFragmentProgram{},guest,false,true));
        assert(first->props.state.att_state[0].colorWriteMask==1 && guest.state.att_state[0].colorWriteMask==15);
        channels.new_fragment(4,2);
        auto next=std::get<0>(channels.get_graphics_pipeline(nullptr,RSXVertexProgram{},RSXFragmentProgram{},guest,false,true));
        assert(next->props.state.att_state[0].colorWriteMask==2 && guest.state.att_state[0].colorWriteMask==15);
        channels.new_fragment(5,15);
        auto all=std::get<0>(channels.get_graphics_pipeline(nullptr,RSXVertexProgram{},RSXFragmentProgram{},guest,false,true));
        assert(all->props.state.att_state[0].colorWriteMask==15 && guest.state.att_state[0].colorWriteMask==15);
    }
    // Placeholder, callback and publication must have the same canonical key.
    if (corrected) {
        Cache async; const auto start=Traits::builds;
        for(unsigned mask:{15u,7u,1u}) {
            Props p{};p.state.att_state[0].colorWriteMask=mask;
            assert(!std::get<0>(async.get_graphics_pipeline(nullptr,RSXVertexProgram{},RSXFragmentProgram{},p,true,true)));
        }
        assert(Traits::pending.size()==1 && Traits::builds==start+1 && async.entries()==1);
        Traits::pending.front()(); Traits::pending.clear();
        Props p{};p.state.att_state[0].colorWriteMask=5;
        assert(std::get<0>(async.get_graphics_pipeline(nullptr,RSXVertexProgram{},RSXFragmentProgram{},p,true,true)));
        assert(Traits::builds==start+1 && async.published.size()==1);
    }
    return builds;
}
