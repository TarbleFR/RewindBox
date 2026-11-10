// CELL560 deferred framebuffer-commit write-back. Copied verbatim from the Core
// (namespace before: 559 preimage; namespace after: 560 source):
// cached_texture_section::flush, unprotect, discard and reprotect, the 560
// deferred-commit helpers, the Vulkan create() synchronization reset, the
// flushable branch of invalidate_range_impl_base and its 560 decision, and
// invalidation_cause with its flag table. Adapters model guest memory, one GPU
// image, its pending copy and whether the command buffer holding that copy was
// submitted; flush_set and unprotect_set keep the production order (transfers,
// wait, flush, then OS protection, then discard). No Vulkan, Metal or timing.
//@@PRELUDE
#include <array>
#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <string_view>
#include <utility>
#include <vector>
#include "ios/IOSFullOverwrite.h"
#include "ios/IOSDeferredCommit.h"

using u8 = std::uint8_t;
using u32 = std::uint32_t;
using u64 = std::uint64_t;
using s32 = std::int32_t;
#define ensure(x) do { if (!(x)) { std::fprintf(stderr, "ensure failed: %s (line %d)\n", #x, __LINE__); std::abort(); } } while (0)
#define AUDIT(x) ensure(x)

namespace utils
{
	enum class protection { rw, ro, no };
	inline u64 tsc = 0;
	inline u64 get_tsc() { return ++tsc; }
}

inline struct { struct { bool strict_texture_flushing = false; } video; } g_cfg;

struct world
{
	std::vector<u8> guest, gpu;
	bool copy_submitted = true, gpu_done = true, recorded = false;
	int copies = 0, gpu_waits = 0, unsubmitted_waits = 0, guest_writes = 0, flushes = 0, aborts = 0, owed_at_release = 0;
};
inline world W;

namespace rsx
{
	enum class texture_upload_context : u32 { shader_read = 1, blit_engine_src = 2, blit_engine_dst = 4, framebuffer_storage = 8, dma = 16 };
	struct command_buffer {};
	struct exclusions { bool empty() const { return true; } void clear() {} };
	struct address_range32
	{
		u32 start, end;
		u32 length() const { return end - start + 1; }
		bool inside(const exclusions&) const { return false; }
	};
	struct tiled_region { explicit operator bool() const { return false; } };
	struct renderer { tiled_region get_tiled_memory_region(const address_range32&) const { return {}; } };
	inline renderer* get_current_renderer() { static renderer r; return &r; }

	struct buffered_section
	{
		utils::protection protection = utils::protection::rw;
		void protect(utils::protection p) { protection = p; }
		void unprotect() { protect(utils::protection::rw); }
		void discard() { protect(utils::protection::rw); }
	};

	@CAUSE_CLASS@

	@CAUSE_FLAGS@
}

template <typename S>
bool owed(const S& s)
{
	if constexpr (requires { s.has_deferred_commit(); }) return s.has_deferred_commit();
	else return false;
}

// flush_set: transfers of unsynchronized sections, their submit and wait, then each flush.
template <typename R>
void flush_set_model(rsx::command_buffer& cmd, R& r)
{
	bool transfer = false;
	for (auto* s : r.sections_to_flush)
	{
		if (!s->is_synchronized())
		{
			s->copy_texture(cmd, true);
			transfer = true;
		}
	}
	if (transfer)
	{
		W.copy_submitted = true;
		if (!W.gpu_done) { W.gpu_waits++; W.gpu_done = true; }
	}
	for (auto* s : r.sections_to_flush) s->flush();
}

// unprotect_set: the OS releases the pages first, then the sections are discarded.
template <typename R>
void unprotect_set_model(R& r)
{
	for (auto* s : r.sections_to_unprotect) W.owed_at_release += owed(*s);
	for (auto* s : r.sections_to_flush) W.owed_at_release += owed(*s);
	for (auto* s : r.sections_to_unprotect) { ensure(s->is_flushed() || s->is_dirty()); s->discard(false); }
	for (auto* s : r.sections_to_flush) { ensure(s->is_flushed() || s->is_dirty()); s->discard(false); }
}
//@@VERSION
namespace @NS@
{
	struct section : rsx::buffered_section
	{
		u32 base = 0x40000, len = 0x10000;
		bool synchronized = false, flushed = false, dirty = false, deferred_commit = false;
		u64 sync_timestamp = 0;
		rsx::texture_upload_context context = rsx::texture_upload_context::framebuffer_storage;
		rsx::exclusions flush_exclusions;
		std::vector<u8> dma;

		section* derived() { return this; }
		void finish_flush() {}
		void release_dma_resources() {}
		utils::protection get_protection() const { return protection; }
		bool is_locked(bool = false) const { return protection != utils::protection::rw; }
		bool is_flushable() const { return is_locked() && context != rsx::texture_upload_context::shader_read; }
		bool is_dirty() const { return dirty; }
		void set_dirty(bool value) { dirty = value; }
		bool is_synchronized() const { return synchronized; }
		bool is_flushed() const { return flushed; }
		rsx::texture_upload_context get_context() const { return context; }
		rsx::address_range32 get_confirmed_range() const { return {base, base + len - 1}; }
		bool exists() const { return true; }
		bool should_flush() const { return true; }
		void on_flush() { W.flushes++; }
		void post_protect(utils::protection, utils::protection) {}
		void protect(utils::protection p) { rsx::buffered_section::protect(p); }
		void dma_abort() { ensure(synchronized && !flushed); W.aborts++; }
		void copy_texture(rsx::command_buffer&, bool miss)
		{
			if (!miss) ensure(!synchronized);
			dma = W.gpu; // GPU order: everything recorded before the copy
			synchronized = true;
			W.copies++;
			W.recorded = true;
			W.copy_submitted = false;
			W.gpu_done = false;
		}
		void imp_flush()
		{
			// The copy's event: never signaled while its command buffer is unsubmitted.
			if (!W.copy_submitted) W.unsubmitted_waits++;
			if (!W.gpu_done) { W.gpu_waits++; W.gpu_done = true; }
			ensure(dma.size() == W.guest.size());
			W.guest = dma;
			W.guest_writes++;
		}
		void reset_unlocked()
		{
			// rsx::cached_texture_section::reset state (the section is unlocked)
			sync_timestamp = 0;
			synchronized = false;
			flushed = false;
			deferred_commit = false;
			dirty = false;
		}
		void vk_create()
		{
			@CREATE_SYNC@
		}

		@HELPERS@

		@FLUSH@

		@UNPROTECT@

		@DISCARD@

		@REPROTECT@
	};

	struct thrashed_set
	{
		std::vector<section*> sections_to_flush, sections_to_unprotect, sections_to_exclude;
		int num_excluded = 0;
	};
	struct intersecting_set { std::vector<section*> sections; };

	template <typename... Args>
	thrashed_set classify([[maybe_unused]] rsx::command_buffer& cmd, intersecting_set& trampled_set, rsx::invalidation_cause cause, [[maybe_unused]] Args&&... extras)
	{
		using namespace rsx;
		thrashed_set result{};
		@DECISION@
		for (auto* obj : trampled_set.sections)
		{
			auto& tex = *obj;
			if (!tex.is_locked())
				continue;
			@FLUSHABLE@
		}
		return result;
	}

	struct machine
	{
		section s, other;
		bool two = false, submit_after_commit = false;
		rsx::command_buffer cmd;
		std::vector<u64> observed;

		static u64 digest(const std::vector<u8>& bytes)
		{
			u64 h = 1469598103934665603ull;
			for (u8 b : bytes) { h ^= b; h *= 1099511628211ull; }
			return h;
		}
		static void fill(std::vector<u8>& bytes, u8 value) { for (std::size_t i = 0; i < bytes.size(); ++i) bytes[i] = static_cast<u8>(value + i * 7); }

		explicit machine(bool second, bool submit) : two(second), submit_after_commit(submit)
		{
			W = {};
			W.guest.assign(s.len, 0x11);
			W.gpu.assign(s.len, 0x22);
			other.base = s.base; // same pages, a second flushable view
		}
		void lock_fbo(section& x)
		{
			// lock_memory_region_impl: reuse a locked framebuffer region (create), else reset it.
			if (!x.is_locked()) x.reset_unlocked();
			else x.vk_create();
			x.reprotect(utils::protection::no);
			x.set_dirty(false);
		}
		void blit(u8 value)
		{
			lock_fbo(s);
			if (two) lock_fbo(other);
			fill(W.gpu, value);
		}
		void invalidate(rsx::invalidation_cause cause, bool rsx_submits)
		{
			intersecting_set set;
			set.sections.push_back(&s);
			if (two) set.sections.push_back(&other);
			auto r = classify(cmd, set, cause);
			if (rsx_submits) W.copy_submitted = true; // flush request: the RSX submits its primary buffer
			flush_set_model(cmd, r);
			unprotect_set_model(r);
		}
		void commit()
		{
			invalidate(rsx::invalidation_cause::committed_as_fbo, false);
			// ios_submit_deferred_commit in VKGSRender::prepare_rtts
			if (submit_after_commit && !W.copy_submitted) W.copy_submitted = true;
		}
		void draw(u8 value)
		{
			if (W.copy_submitted) W.gpu_done = true; // the GPU caught up with submitted work
			fill(W.gpu, value);
		}
		void read()
		{
			if (s.get_protection() == utils::protection::no) invalidate(rsx::invalidation_cause::read, true);
			observed.push_back(digest(W.guest));
		}
		void write(u8 value, std::size_t offset)
		{
			if (s.is_locked()) invalidate(rsx::invalidation_cause::write, true);
			W.guest[offset] = value;
			observed.push_back(digest(W.guest));
		}
		void supersede()
		{
			// discard_framebuffer_memory_region
			if (s.is_locked() && s.get_context() == rsx::texture_upload_context::framebuffer_storage) s.discard(false);
		}
		void savestate()
		{
			// rsx::thread::handle_invalidated_memory_range while stopped: commit host-resident memory.
			if (s.is_locked()) invalidate(rsx::invalidation_cause::read, true);
			observed.push_back(digest(W.guest));
		}
		void dirty_then_fault()
		{
			if (s.is_locked()) { s.set_dirty(true); invalidate(rsx::invalidation_cause::read, true); }
		}
		void reprotect_ro() { s.reprotect(utils::protection::ro); }
		void release()
		{
			// texture_cache block clear(), swizzle-mismatch lookup: pages released by unprotect()
			if (s.is_locked()) s.unprotect();
		}
		void rsx_flush_before_submit()
		{
			// A flush on the RSX thread between a commit and any submit.
			if (s.is_locked()) invalidate(rsx::invalidation_cause::read, false);
		}
	};
}
//@@MAIN
struct outcome { std::vector<u64> observed; int copies, gpu_waits, unsubmitted_waits, owed_at_release; u64 deferrals, dropped, forced; };

template <typename M, typename F>
outcome run(F&& scenario, bool two, bool submit)
{
	namespace dc = rpcs3::ios::deferred_commit;
	const u64 d0 = dc::deferrals.load(), p0 = dc::dropped.load(), f0 = dc::forced_writebacks.load();
	M m(two, submit);
	scenario(m);
	return {m.observed, W.copies, W.gpu_waits, W.unsubmitted_waits, W.owed_at_release,
		dc::deferrals.load() - d0, dc::dropped.load() - p0, dc::forced_writebacks.load() - f0};
}

int main()
{
	namespace dc = rpcs3::ios::deferred_commit;
	struct scenario { const char* name; void (*b)(before::machine&); void (*a)(after::machine&); bool two; };
#define BOTH(name, two, body) scenario{ name, [](before::machine& m) { body; }, [](after::machine& m) { body; }, two }
	const scenario scenarios[] = {
		BOTH("commit_draw_read", false, m.blit(1); m.commit(); m.draw(2); m.read()),
		BOTH("reblit_before_read", false, m.blit(1); m.commit(); m.draw(2); m.blit(3); m.commit(); m.draw(4); m.read()),
		BOTH("five_frames_then_read", false, for (u8 i = 1; i <= 5; ++i) { m.blit(i); m.commit(); m.draw(static_cast<u8>(i + 10)); } m.read()),
		BOTH("partial_write", false, m.blit(1); m.commit(); m.draw(2); m.write(7, 100); m.read()),
		BOTH("superseded_surface", false, m.blit(1); m.commit(); m.draw(2); m.supersede(); m.read()),
		BOTH("savestate", false, m.blit(1); m.commit(); m.draw(2); m.savestate(); m.read()),
		BOTH("clobbered_then_fault", false, m.blit(1); m.commit(); m.draw(2); m.dirty_then_fault(); m.read()),
		BOTH("reprotected_read_only", false, m.blit(1); m.commit(); m.draw(2); m.reprotect_ro(); m.read()),
		BOTH("released_by_unprotect", false, m.blit(1); m.commit(); m.draw(2); m.release(); m.read()),
		BOTH("read_before_commit", false, m.blit(1); m.read(); m.commit(); m.draw(2); m.read()),
		BOTH("commit_then_read_at_once", false, m.blit(1); m.commit(); m.read()),
		BOTH("two_flushables_not_deferred", true, m.blit(1); m.commit(); m.draw(2); m.read()),
	};
#undef BOTH

	int identical = 0, waits_before = 0, waits_after = 0, deferred_total = 0, dropped_total = 0, forced_total = 0;
	for (const auto& sc : scenarios)
	{
		dc::enabled = false;
		const auto b = run<before::machine>(sc.b, sc.two, false);
		const auto d = run<after::machine>(sc.a, sc.two, true);
		dc::enabled = true;
		const auto a = run<after::machine>(sc.a, sc.two, true);
		dc::enabled = false;

		// Disabled 560 is the 559 behaviour exactly.
		ensure(d.observed == b.observed && d.copies == b.copies && d.gpu_waits == b.gpu_waits && d.deferrals == 0);
		// Enabled: the guest reads the same bytes at every access, never waits on an
		// unsubmitted copy and never releases pages that still owe bytes.
		if (a.observed != b.observed) { std::fprintf(stderr, "observable difference in %s\n", sc.name); return 1; }
		ensure(a.unsubmitted_waits == 0 && a.owed_at_release == 0 && b.owed_at_release == 0);
		ensure(a.gpu_waits <= b.gpu_waits);
		if (sc.two) ensure(a.deferrals == 0 && a.gpu_waits == b.gpu_waits);
		++identical;
		waits_before += b.gpu_waits;
		waits_after += a.gpu_waits;
		deferred_total += static_cast<int>(a.deferrals);
		dropped_total += static_cast<int>(a.dropped);
		forced_total += static_cast<int>(a.forced);
	}
	// Five frames, no access until the end: one wait per commit before, none after.
	{
		const auto& sc = scenarios[2];
		const auto b = run<before::machine>(sc.b, false, false);
		dc::enabled = true;
		const auto a = run<after::machine>(sc.a, false, true);
		dc::enabled = false;
		ensure(b.gpu_waits == 5 && a.gpu_waits == 0 && a.deferrals == 5 && a.dropped == 4);
	}
	// Negative control: without the submit after a deferred commit, an RSX-thread
	// flush would wait on a copy whose command buffer was never submitted.
	int unsubmitted = 0;
	{
		dc::enabled = true;
		const auto a = run<after::machine>([](after::machine& m) { m.blit(1); m.commit(); m.rsx_flush_before_submit(); }, false, false);
		const auto ok = run<after::machine>([](after::machine& m) { m.blit(1); m.commit(); m.rsx_flush_before_submit(); }, false, true);
		dc::enabled = false;
		unsubmitted = a.unsubmitted_waits;
		ensure(unsubmitted == 1 && ok.unsubmitted_waits == 0);
	}

	std::printf("{\"passed\":true,\"scenarios\":%d,\"observedIdentical\":%d,\"disabledIdenticalTo559\":true,"
		"\"gpuWaitsBefore\":%d,\"gpuWaitsAfter\":%d,\"deferrals\":%d,\"dropped\":%d,\"forcedWritebacks\":%d,"
		"\"unsubmittedWaitsWithoutSubmit\":%d,\"unsubmittedWaits\":0,\"pagesReleasedOwingBytes\":0}\n",
		static_cast<int>(std::size(scenarios)), identical, waits_before, waits_after, deferred_total, dropped_total,
		forced_total, unsubmitted);
	return 0;
}
