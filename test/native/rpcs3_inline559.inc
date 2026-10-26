// CELL559 inline pipeline callback. Inside each namespace, the KEY_TYPES,
// LOOKUP (get_graphics_pipeline and its single-flight helpers, from
// ProgramStateCache.h) and BUILD_PIPELINE (VKTraits::build_pipeline, from
// VKProgramBuffer.h) are copied verbatim from the 555 preimage or the 559
// source. The real RSXVertexProgram/RSXFragmentProgram types are used; the
// compiler, shaders and disk notification are adapters. No Vulkan or Metal.
using VkShaderModule = std::uint64_t;
struct Pipeline { int id = 0; };
struct Shader { VkShaderModule handle = 0; std::vector<int> uniforms; bool use_last_provoking_vertex = false; u32 id = 0; };
struct Log { template <class... A> void notice(A&&...) {} template <class... A> void success(A&&...) {} };
inline Log rsx_log;
using reader_lock = std::shared_lock<std::shared_mutex>;

namespace vk
{
	struct pipeline_props { u32 state = 0, renderpass = 0; bool operator==(const pipeline_props&) const = default; };
	struct pipe_compiler
	{
		enum op_flag_bits { COMPILE_INLINE = 1, COMPILE_DEFERRED = 2, SEPARATE_SHADER_OBJECTS = 4, USE_LAST_PROVOKING_VERTEX = 8 };
		using op_flags = u32;
		using callback_t = std::function<void(std::unique_ptr<Pipeline>&)>;
		std::vector<callback_t> deferred;
		std::function<void()> during_inline_compile;
		int stored_callbacks = 0;
		std::unique_ptr<Pipeline> compile(const pipeline_props&, VkShaderModule, VkShaderModule, op_flags flags,
			callback_t callback, const std::vector<int>&, const std::vector<int>&)
		{
			if (callback) ++stored_callbacks;
			if (flags & COMPILE_INLINE)
			{
				// A long driver compile: PPU/SPU keep running and may rewrite guest memory.
				if (during_inline_compile) during_inline_compile();
				return std::make_unique<Pipeline>(Pipeline{1});
			}
			deferred.push_back(std::move(callback));
			return {};
		}
	};
	inline pipe_compiler g_compiler;
	inline pipe_compiler* get_pipe_compiler() { return &g_compiler; }
}
using Props = vk::pipeline_props;
using pipeline_properties = Props;
struct Published { Props props; std::vector<u32> vertex_words; std::vector<u8> fragment_bytes; };

// PER_NAMESPACE: everything below is instantiated once for 555 and once for 559.
struct Traits
{
	using vertex_program_type = Shader;
	using fragment_program_type = Shader;
	using pipeline_type = Pipeline;
	using pipeline_storage_type = std::unique_ptr<Pipeline>;
	static void validate_pipeline_properties(const Shader&, const Shader&, Props&) {}
	static
	@BUILD_PIPELINE@
};

class Cache
{
	using backend_traits = Traits;
	using pipeline_type = Pipeline;
	using pipeline_storage_type = std::unique_ptr<Pipeline>;
	using vertex_program_type = Shader;
	using fragment_program_type = Shader;
	using pipeline_data_type = std::tuple<Pipeline*, const Shader*, const Shader*>;
public:
	@KEY_TYPES@
private:
	std::shared_mutex m_pipeline_mutex;
	std::unordered_map<pipeline_key, pipeline_storage_type, pipeline_key_hash, pipeline_key_compare> m_storage;
	pipeline_storage_type __null_pipeline_handle;
	inline static thread_local bool m_cache_miss_flag = false;
	std::unordered_set<pipeline_key, pipeline_key_hash, pipeline_key_compare> m_inline_builds;
	std::mutex m_build_mutex;
	std::condition_variable m_build_cv;
	u64 m_build_generation = 0;
	Shader vertex{11, {}, false, 1}, fragment{22, {}, false, 2};
	bool known = false;
	auto search_vertex_program(rsx::program_cache_hint_t*, const RSXVertexProgram&) { return std::tuple<const Shader&, bool>(vertex, known); }
	auto search_fragment_program(rsx::program_cache_hint_t*, const RSXFragmentProgram&) { return std::tuple<const Shader&, bool>(fragment, known); }
	void notify_pipeline_compiled(const Props& props, const RSXVertexProgram& vp, const RSXFragmentProgram& fp)
	{
		// The disk writer copies what it keeps before returning (rsx_cache.h store()).
		const auto* bytes = static_cast<const u8*>(fp.get_data());
		published.push_back({props, vp.data, std::vector<u8>(bytes, bytes + fp.ucode_length)});
	}
public:
	std::vector<Published> published;
	@LOOKUP@
};
