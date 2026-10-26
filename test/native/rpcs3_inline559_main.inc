// CELL559 inline callback scenarios, run against the 555 and 559 bodies.
// ThreadSanitizer owns operator new/delete: allocations are counted otherwise.
#if defined(__has_feature)
#if __has_feature(thread_sanitizer)
#define CELL559_THREAD_SANITIZER 1
#endif
#endif
namespace alloc_count
{
	inline std::atomic<bool> enabled{false};
	inline std::atomic<u64> calls{0}, bytes{0};
#ifdef CELL559_THREAD_SANITIZER
	constexpr bool counted = false;
#else
	constexpr bool counted = true;
#endif
}
#ifndef CELL559_THREAD_SANITIZER
void* operator new(std::size_t size)
{
	if (alloc_count::enabled.load(std::memory_order_relaxed))
	{
		alloc_count::calls.fetch_add(1, std::memory_order_relaxed);
		alloc_count::bytes.fetch_add(size, std::memory_order_relaxed);
	}
	if (void* p = std::malloc(size ? size : 1)) return p;
	std::abort();
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }
#endif

#define CELL559_REQUIRE(x) do { if (!(x)) { std::fprintf(stderr, "requirement failed: %s (line %d)\n", #x, __LINE__); std::abort(); } } while (0)

struct Programs
{
	RSXVertexProgram vp;
	std::vector<u8> guest;   // fragment ucode lives in guest memory
	RSXFragmentProgram fp;
	explicit Programs(u32 seed)
	{
		vp.data.resize(512 * 4);
		for (usz i = 0; i < vp.data.size(); ++i) vp.data[i] = static_cast<u32>(i * 2654435761u + seed);
		for (u32 j = 0; j < 4; ++j) vp.jump_table.insert(j * 16 + seed % 7);
		guest.resize(2048);
		for (usz i = 0; i < guest.size(); ++i) guest[i] = static_cast<u8>(i * 31 + seed);
		fp.data = RSXFragmentProgram::data_storage_helper(guest.data());
		fp.ucode_length = static_cast<u32>(guest.size());
		fp.total_length = fp.ucode_length;
		fp.valid = true;
	}
};

struct InlineResult { u64 calls, bytes; int stored_callbacks; bool snapshot_kept, vertex_matches; };

template <typename CacheT>
static InlineResult inline_build(u32 seed)
{
	CacheT cache;
	Programs p(seed);
	const std::vector<u32> vertex_words = p.vp.data;
	const std::vector<u8> original = p.guest;
	vk::g_compiler = {};
	// The guest rewrites the fragment program while the driver compiles inline.
	vk::g_compiler.during_inline_compile = [&] { for (auto& b : p.guest) b ^= 0xff; };
	Props props{seed, 3};
	alloc_count::calls = 0;
	alloc_count::bytes = 0;
	alloc_count::enabled = true;
	const auto result = cache.get_graphics_pipeline(nullptr, p.vp, p.fp, props, false, true);
	alloc_count::enabled = false;
	CELL559_REQUIRE(std::get<0>(result) != nullptr);
	CELL559_REQUIRE(cache.published.size() == 1);
	return {alloc_count::calls.load(), alloc_count::bytes.load(), vk::g_compiler.stored_callbacks,
		cache.published[0].fragment_bytes == original, cache.published[0].vertex_words == vertex_words};
}

template <typename CacheT>
static bool async_build_outlives_caller(u32 seed)
{
	CacheT cache;
	vk::g_compiler = {};
	std::vector<u32> vertex_words;
	std::vector<u8> original;
	{
		auto p = std::make_unique<Programs>(seed);
		vertex_words = p->vp.data;
		original = p->guest;
		Props props{seed, 4};
		const auto result = cache.get_graphics_pipeline(nullptr, p->vp, p->fp, props, true, true);
		CELL559_REQUIRE(std::get<0>(result) == nullptr);
		// The caller's programs and the guest bytes disappear before the build completes.
	}
	CELL559_REQUIRE(vk::g_compiler.deferred.size() == 1 && vk::g_compiler.stored_callbacks == 1);
	auto pipeline = std::make_unique<Pipeline>(Pipeline{2});
	vk::g_compiler.deferred[0](pipeline);
	return cache.published.size() == 1 && cache.published[0].fragment_bytes == original &&
		cache.published[0].vertex_words == vertex_words;
}

template <typename CacheT>
static int preload_without_notification(u32 seed)
{
	CacheT cache;
	vk::g_compiler = {};
	Programs p(seed);
	Props props{seed, 5};
	const auto result = cache.get_graphics_pipeline(nullptr, p.vp, p.fp, props, false, false);
	CELL559_REQUIRE(std::get<0>(result) != nullptr);
	CELL559_REQUIRE(cache.published.empty());
	return vk::g_compiler.stored_callbacks;
}

int main()
{
	const InlineResult b = inline_build<before::Cache>(7);
	const InlineResult a = inline_build<after::Cache>(7);
	// Both keep the fragment snapshot taken before the compile, and the vertex words.
	CELL559_REQUIRE(b.snapshot_kept && a.snapshot_kept && b.vertex_matches && a.vertex_matches);
	// Before: the inline compiler received (and copied) the callback; after: it does not.
	CELL559_REQUIRE(b.stored_callbacks == 1 && a.stored_callbacks == 0);
	if (alloc_count::counted)
	{
		CELL559_REQUIRE(a.calls < b.calls && a.bytes < b.bytes);
		// Removed: two copies of the whole callback state, and the vertex program copy.
		const u64 vertex_bytes = 512 * 4 * sizeof(u32);
		CELL559_REQUIRE(b.bytes - a.bytes >= 3 * vertex_bytes + 2 * 2048);
	}

	CELL559_REQUIRE(async_build_outlives_caller<before::Cache>(9));
	CELL559_REQUIRE(async_build_outlives_caller<after::Cache>(9));
	// Cached-shader preloading builds inline without notification: it publishes the
	// same pipeline and, after 559, no longer hands the inline compiler a copy either.
	CELL559_REQUIRE(preload_without_notification<before::Cache>(11) == 1);
	CELL559_REQUIRE(preload_without_notification<after::Cache>(11) == 0);

	std::printf("{\"passed\":true,\"allocationsCounted\":%s,\"inlineAllocationsBefore\":%llu,\"inlineAllocationsAfter\":%llu,"
		"\"inlineAllocatedBytesBefore\":%llu,\"inlineAllocatedBytesAfter\":%llu,"
		"\"callbackStoredByInlineCompilerBefore\":%d,\"callbackStoredByInlineCompilerAfter\":%d,"
		"\"fragmentSnapshotKeptDuringGuestRewrite\":true,\"asyncBuildOutlivesCaller\":true,"
		"\"preloadPublishesWithoutCallbackCopy\":true,\"vertexInstructions\":512,\"fragmentUcodeBytes\":2048}\n",
		alloc_count::counted ? "true" : "false",
		static_cast<unsigned long long>(b.calls), static_cast<unsigned long long>(a.calls),
		static_cast<unsigned long long>(b.bytes), static_cast<unsigned long long>(a.bytes),
		b.stored_callbacks, a.stored_callbacks);
	return 0;
}
