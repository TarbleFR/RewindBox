// Portable adapters around the extracted production lookup of Build 543 and
// its Build 542 baseline. The bodies between the markers are copied verbatim
// from the Core source by test/rpcs3_cell543_test.py. No Vulkan/Metal
// compilation, GPU work or device timing is simulated here.
struct Shader { unsigned id=1; unsigned output_color_masks[4]{1,0,0,0}; };
using VKVertexProgram=Shader; using VKFragmentProgram=Shader;
struct RSXVertexProgram {};
struct RSXFragmentProgram { static RSXFragmentProgram clone(const RSXFragmentProgram& p) { return p; } };
namespace rsx { struct program_cache_hint_t {}; }
struct Pipeline { Props props; };
struct Log { template<class... A> void notice(A&&...) {} template<class... A> void success(A&&...) {} template<class... A> void error(A&&...) {} };
inline Log rsx_log;
using reader_lock=std::shared_lock<std::shared_mutex>;
struct Traits {
    using pipeline_storage_type=std::unique_ptr<Pipeline>;
    using pipeline_type=Pipeline;
    inline static BuildCounter builds{};
    inline static std::atomic<int> delay_us{0}, throw_on{-1};
    inline static std::atomic<bool> return_null{false};
    inline static std::mutex pending_mutex;
    inline static std::vector<std::function<void()>> pending;
    static // VALIDATION
    static Pipeline* build_pipeline(const Shader&,const Shader&,const Props& props,bool async,
                                    std::function<Pipeline*(pipeline_storage_type&)> callback) {
        const int n=static_cast<int>(++builds);
        if (const int delay=delay_us.load()) std::this_thread::sleep_for(std::chrono::microseconds(delay));
        if (n==throw_on.load()) throw std::runtime_error("simulated driver failure");
        if (async) {
            std::lock_guard lock(pending_mutex);
            pending.emplace_back([props,callback] { auto p=std::make_unique<Pipeline>(Pipeline{props}); callback(p); });
            return nullptr;
        }
        if (return_null.load()) { pipeline_storage_type none; return callback(none); }
        auto p=std::make_unique<Pipeline>(Pipeline{props}); return callback(p);
    }
    static void reset() {
        builds=0; delay_us=0; throw_on=-1; return_null=false;
        std::lock_guard lock(pending_mutex); pending.clear();
    }
};
class Cache {
    using backend_traits=Traits;
    using pipeline_properties=Props; using pipeline_type=Pipeline;
    using pipeline_storage_type=std::unique_ptr<Pipeline>;
    using vertex_program_type=Shader; using fragment_program_type=Shader;
    using pipeline_data_type=std::tuple<Pipeline*,const Shader*,const Shader*>;
public:
    // KEY_TYPES
private:
    std::shared_mutex m_pipeline_mutex;
    std::unordered_map<pipeline_key,pipeline_storage_type,pipeline_key_hash,pipeline_key_compare> m_storage;
    pipeline_storage_type __null_pipeline_handle;
    inline static thread_local bool m_cache_miss_flag=false;
    std::unordered_set<pipeline_key,pipeline_key_hash,pipeline_key_compare> m_inline_builds;
    std::mutex m_build_mutex;
    std::condition_variable m_build_cv;
    [[maybe_unused]] u64 m_build_generation=0; // Unused by the 542 baseline body.
    Shader vertex{1},fragment{2};
    std::atomic<bool> seen_vertex{false},seen_fragment{false};
    std::mutex published_mutex;
    auto search_vertex_program(rsx::program_cache_hint_t*,const RSXVertexProgram&) {
        bool seen=seen_vertex.exchange(true); return std::tuple<const Shader&,bool>(vertex,seen);
    }
    auto search_fragment_program(rsx::program_cache_hint_t*,const RSXFragmentProgram&) {
        bool seen=seen_fragment.exchange(true); return std::tuple<const Shader&,bool>(fragment,seen);
    }
    void notify_pipeline_compiled(const Props& props,const RSXVertexProgram&,const RSXFragmentProgram&) {
        std::lock_guard lock(published_mutex); published.push_back(props);
    }
public:
    std::vector<Props> published;
    void new_fragment(unsigned id, unsigned mask) { fragment.id=id; fragment.output_color_masks[0]=mask; seen_fragment=false; }
    void set_programs(unsigned vertex_id, unsigned fragment_id) { vertex.id=vertex_id; fragment.id=fragment_id; }
    void mark_known() { seen_vertex=true; seen_fragment=true; }
    std::size_t entries() { std::shared_lock lock(m_pipeline_mutex); return m_storage.size(); }
    std::size_t null_entries() {
        std::shared_lock lock(m_pipeline_mutex); std::size_t n=0;
        for (auto& [key,value]:m_storage) n+=!value;
        return n;
    }
    static bool cache_missed() { return m_cache_miss_flag; }
    // LOOKUP
};
