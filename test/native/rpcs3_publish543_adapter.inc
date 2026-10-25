// Portable adapters around the extracted production shader-cache writer of
// Build 543 and its Build 542 baseline (copied verbatim by the harness).
// fs:: is a POSIX implementation with real fsync() and rename(). An optional
// synthetic delay inside commit() models slow flash; it is never presented as
// an iPhone measurement.
namespace fs {
inline std::atomic<int> commit_delay_us{0};
inline std::atomic<unsigned> commits{0}, fsyncs{0};
struct stat_t { u64 size=0; };
inline bool get_stat(const std::string& path, stat_t& s) {
    struct ::stat st{}; if (::stat(path.c_str(),&st)) return false; s.size=u64(st.st_size); return true;
}
struct file {
    int fd=-1;
    explicit operator bool() const { return fd>=0; }
    u64 write(const void* data, u64 size) {
        const char* p=static_cast<const char*>(data); u64 done=0;
        while (done<size) { auto n=::write(fd,p+done,size-done); if (n<=0) return done; done+=u64(n); }
        return done;
    }
};
inline std::atomic<unsigned> temp_counter{0};
struct pending_file {
    fs::file file; std::string m_path, m_dest;
    explicit pending_file(const std::string& path) : m_dest(path) {
        m_path=path+".tmp"+std::to_string(::getpid())+"_"+std::to_string(++temp_counter);
        file.fd=::open(m_path.c_str(),O_CREAT|O_WRONLY|O_TRUNC,0644);
    }
    bool commit() {
        if (file.fd<0) return false;
        if (::fsync(file.fd)) return false;
        ++fsyncs;
        if (const int delay=commit_delay_us.load()) std::this_thread::sleep_for(std::chrono::microseconds(delay));
        ::close(file.fd); file.fd=-1;
        if (::rename(m_path.c_str(),m_dest.c_str())) return false;
        m_path.clear(); ++commits; return true;
    }
    ~pending_file() { if (file.fd>=0) ::close(file.fd); if (!m_path.empty()) ::unlink(m_path.c_str()); }
};
}
namespace fmt {
template<class T> auto printable(const T& v) {
    if constexpr (std::is_integral_v<T>) return static_cast<unsigned long long>(v); else return v;
}
template<class... A> std::string format(const char* f, const A&... a) {
    char buffer[512]; std::snprintf(buffer,sizeof(buffer),f,printable(a)...); return buffer;
}
}
struct StoreLog {
    std::atomic<unsigned> errors{0};
    template<class... A> void error(A&&...) { ++errors; }
    template<class... A> void notice(A&&...) {}
};
inline StoreLog rsx_log;
struct thread_ctrl {
    inline static std::atomic<unsigned> lowered{0};
    inline static std::thread::id lowered_by{};
    static void set_native_priority(int priority) { if (priority<0) { lowered_by=std::this_thread::get_id(); ++lowered; } }
};
constexpr usz max_vertex_program_instructions=544;
template<usz N> void unpack_bitset(const std::bitset<N>& block, u64* values) {
    for (usz i=0;i<N;++i) if (block[i]) values[i/64]|=1ull<<(i%64);
}
struct VertexTextureState { u32 texture_dimensions=0; u16 multisampled_textures=0; };
struct FragmentTextureState { u32 texture_dimensions=0; u16 redirected_textures=0, shadow_textures=0, multisampled_textures=0; };
struct RSXVertexProgram {
    std::vector<u32> data; VertexTextureState texture_state; u32 ctrl=0, output_mask=0, base_address=0, entry=0;
    std::bitset<max_vertex_program_instructions> instruction_mask; std::set<u32> jump_table;
};
struct RSXFragmentProgram {
    std::vector<u8> bytes; u32 ucode_length=0, ctrl=0, texcoord_control_mask=0, mrt_buffers_count=0; bool two_sided_lighting=false;
    FragmentTextureState texture_state;
    const void* get_data() const { return bytes.data(); }
};
struct Storage {
    u64 get_hash(const vk::pipeline_props& p) { return rpcs3::hash_struct<vk::pipeline_props>(p); }
    u64 get_hash(const RSXVertexProgram& p) { return rpcs3::hash_array(p.data.data(),p.data.size()); }
    u64 get_hash(const RSXFragmentProgram& p) { return rpcs3::hash_array(p.bytes.data(),p.bytes.size()); }
};
class ShaderCache {
public:
    using pipeline_storage_type=vk::pipeline_props;
    // PIPELINE_DATA
    // PENDING_RECORD
private:
    std::string version_prefix="v1.95";
    std::string root_path;
    std::string pipeline_class_name="vulkan";
    Storage storage; Storage& m_storage=storage;
    // WRITE_ATOMICALLY
public:
    explicit ShaderCache(std::string root) : root_path(std::move(root)) {
        // CONSTRUCTOR_PUBLISHER
    }
    std::string pipeline_path(const pipeline_data& data) const {
        const u32 state_params[]={data.vp_ctrl0,data.vp_ctrl1,data.fp_ctrl,data.vp_texture_dimensions,data.fp_texture_dimensions,
            data.fp_texcoord_control,data.fp_height,data.fp_pixel_layout,data.fp_lighting_flags,data.fp_shadow_textures,
            data.fp_redirected_textures,data.vp_multisampled_textures,data.fp_multisampled_textures,data.fp_mrt_count};
        return root_path+"/pipelines/"+pipeline_class_name+"/"+version_prefix+"/"+fmt::format("%llX+%llX+%llX+%llX.bin",
            data.vertex_program_hash,data.fragment_program_hash,data.pipeline_storage_hash,rpcs3::hash_array(state_params));
    }
    pipeline_data expected(const pipeline_storage_type& p, const RSXVertexProgram& vp, const RSXFragmentProgram& fp) { return pack(p,vp,fp); }
    // STORE_METHODS
    // PACK
    // PUBLISHER_MEMBER
};
