// CELL561 early command-buffer submission. Copied verbatim from the Core:
// VKGSRender::ios_early_submit, the primary-submission tracking block of
// close_and_submit_command_buffer and the per-frame reset of the flip, with
// rpcs3::ios::early_submit (decide, limits, counters) included unchanged.
// Adapters model the RSX thread recording draws, one in-order GPU queue that
// executes submitted command buffers (each submission also pays a render-pass
// split), and a guest access after each flip that needs every recorded draw
// completed (the per-frame fault readback). Time is simulated: no Vulkan,
// Metal, MoltenVK or iPhone figure is inferred.
//@@PRELUDE
#include <algorithm>
#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <vector>
#include "ios/IOSEarlySubmit.h"

using u32 = std::uint32_t;
using u64 = std::uint64_t;
#define ensure(x) do { if (!(x)) { std::fprintf(stderr, "ensure failed: %s (line %d)\n", #x, __LINE__); std::abort(); } } while (0)

namespace utils
{
	inline u64 tsc = 0;
	inline u64 get_tsc() { return ++tsc; }
}

namespace vk
{
	inline bool uninterruptible = false;
	inline bool is_uninterruptible() { return uninterruptible; }

	// A primary command buffer: the draws it carries and when the GPU completes it.
	struct command_buffer_chunk
	{
		std::vector<u32> draws;
		bool pending = false;
		double done_at = 0;
		const double* now = nullptr;

		// Non-blocking completion test, as the fence check of the Core.
		bool poke()
		{
			if (pending && *now >= done_at)
			{
				pending = false;
			}
			return !pending;
		}
	};
}

enum flush_queue_state : u32
{
	ok = 0,
	flushing = 1,
	deadlock = 2
};

struct queue_status_t
{
	u32 bits = 0;
	bool operator&(flush_queue_state f) const { return (bits & f) != 0; }
};

struct frame_context_t
{
	u64 ios_submit_tsc = 0;
};

struct timing
{
	double rsx_per_draw;  // RSX recording time per draw
	double gpu_per_draw;  // GPU execution time per draw
	double per_submit;    // GPU cost of one submission (render-pass store and reload)
	double guest;         // guest time between the readback and the next frame's first draw
	double copy;          // copy of the read-back surface to guest memory
};

struct renderer
{
	u32 m_ios_draws_since_submit = 0;
	u32 m_ios_early_submits_this_frame = 0;
	vk::command_buffer_chunk* m_ios_last_primary_submit = nullptr;
	queue_status_t m_queue_status;
	frame_context_t frame;
	frame_context_t* m_current_frame = &frame;

	std::vector<vk::command_buffer_chunk> ring = std::vector<vk::command_buffer_chunk>(8);
	std::size_t ring_index = 0;
	vk::command_buffer_chunk* m_current_command_buffer = &ring[0];

	timing t;
	double now = 0;
	double gpu_free_at = 0;
	std::vector<u32> submitted_order;
	std::vector<std::size_t> submission_sizes;

	explicit renderer(timing value) : t(value)
	{
		for (auto& cb : ring)
		{
			cb.now = &now;
		}
	}

	void close_and_submit_command_buffer()
	{
		auto* cb = m_current_command_buffer;
		const double start = std::max(gpu_free_at, now);
		gpu_free_at = start + cb->draws.size() * t.gpu_per_draw + t.per_submit;
		cb->done_at = gpu_free_at;
		cb->pending = true;
		submitted_order.insert(submitted_order.end(), cb->draws.begin(), cb->draws.end());
		submission_sizes.push_back(cb->draws.size());
		cb->draws.clear();
//@TRACK@
	}

	void flush_command_queue()
	{
		close_and_submit_command_buffer();
		ring_index = (ring_index + 1) % ring.size();
		m_current_command_buffer = &ring[ring_index];
		// The Core waits for a still-pending entry before reusing it (cb_reuse).
		if (m_current_command_buffer->pending)
		{
			now = std::max(now, m_current_command_buffer->done_at);
			m_current_command_buffer->poke();
		}
	}

	void flip()
	{
		close_and_submit_command_buffer();
//@RESET@
		ring_index = (ring_index + 1) % ring.size();
		m_current_command_buffer = &ring[ring_index];
		if (m_current_command_buffer->pending)
		{
			now = std::max(now, m_current_command_buffer->done_at);
			m_current_command_buffer->poke();
		}
	}

//@EARLY@
};
//@@MAIN
struct outcome
{
	std::vector<u32> order;
	std::vector<std::size_t> sizes;
	double readback_wait = 0;  // total guest wait for the GPU at the readbacks
	double frame_time = 0;     // simulated time per frame
	u64 early = 0, early_draws = 0, busy = 0, capped = 0;
	u32 max_in_frame = 0;
	u32 last_frame_early = 0;  // early submissions of the final frame: the budget resets every frame
	std::size_t min_early_chunk = SIZE_MAX;
	bool early_while_busy = false;
	bool early_while_guarded = false;
};

enum class guard { none, uninterruptible, flushing, deadlock };

static outcome run(timing t, u32 draws_per_frame, u32 frames, bool hook, bool enabled, guard g = guard::none, bool readback = true)
{
	namespace early = rpcs3::ios::early_submit;
	early::enabled.store(enabled);
	early::submits.store(0);
	early::submitted_draws.store(0);
	early::gpu_busy.store(0);
	early::frame_capped.store(0);
	vk::uninterruptible = g == guard::uninterruptible;

	renderer r(t);
	if (g == guard::flushing) r.m_queue_status.bits = flushing;
	if (g == guard::deadlock) r.m_queue_status.bits = deadlock;
	outcome o;
	u32 id = 0;
	const double start = r.now;
	for (u32 f = 0; f < frames; f++)
	{
		u32 in_frame = 0;
		for (u32 d = 0; d < draws_per_frame; d++)
		{
			r.now += t.rsx_per_draw;
			r.m_current_command_buffer->draws.push_back(id++);
			if (hook)
			{
				// Expected GPU state as the Core's end-of-draw check sees it (without mutating it).
				const auto* last = r.m_ios_last_primary_submit;
				const bool idle = !last || !last->pending || r.now >= last->done_at;
				const u64 before = early::submits.load();
				r.ios_early_submit();
				if (early::submits.load() != before)
				{
					in_frame++;
					o.min_early_chunk = std::min(o.min_early_chunk, r.submission_sizes.back());
					o.early_while_busy |= !idle;
					o.early_while_guarded |= g != guard::none;
				}
			}
		}
		o.max_in_frame = std::max(o.max_in_frame, in_frame);
		o.last_frame_early = in_frame;
		r.flip();
		if (readback)
		{
			// The guest reads the frame back: every recorded draw must have executed.
			const double wait = std::max(0.0, r.gpu_free_at - r.now);
			o.readback_wait += wait;
			r.now += wait + t.copy;
		}
		r.now += t.guest;
	}
	o.order = r.submitted_order;
	o.sizes = r.submission_sizes;
	o.frame_time = (r.now - start) / frames;
	o.early = early::submits.load();
	o.early_draws = early::submitted_draws.load();
	o.busy = early::gpu_busy.load();
	o.capped = early::frame_capped.load();
	return o;
}

static bool expect(bool condition, const char* what)
{
	if (!condition) std::fprintf(stderr, "FAILED: %s\n", what);
	return condition;
}

int main()
{
	namespace early = rpcs3::ios::early_submit;
	using early::verdict;
	bool ok = true;

	// decide(): every branch over a small exhaustive range.
	u32 decisions = 0;
	for (int on = 0; on < 2; on++)
		for (u32 draws = 0; draws < early::min_draws * 2; draws++)
			for (u32 this_frame = 0; this_frame <= early::max_per_frame + 1; this_frame++)
				for (int idle = 0; idle < 2; idle++)
				{
					const verdict v = early::decide(on, draws, this_frame, idle);
					verdict want = verdict::keep;
					if (on && draws >= early::min_draws)
						want = this_frame >= early::max_per_frame ? verdict::capped : idle ? verdict::submit : verdict::gpu_busy;
					ok &= expect(v == want, "decide verdict");
					decisions++;
				}

	// Dragon Ball Z combat in build 560: about 177 draws recorded over ~10 ms per frame,
	// the read-back surface needed right after the flip.
	const timing combat{10.0 / 177, 7.0 / 177, 0.2, 6.0, 0.8};
	const auto combat_before = run(combat, 177, 120, false, false);
	const auto combat_after = run(combat, 177, 120, true, true);
	// Light scenes: fewer draws per frame than one early chunk.
	const timing light{0.4, 0.2, 0.2, 9.0, 0.8};
	const auto light_before = run(light, 26, 120, false, false);
	const auto light_after = run(light, 26, 120, true, true);
	// GPU-bound frames without a readback: submitted frames queue up, so after the
	// first frame the GPU never drains while the RSX thread records.
	const timing gpu_bound{10.0 / 177, 30.0 / 177, 0.2, 2.0, 0.8};
	const auto bound_before = run(gpu_bound, 177, 120, false, false, guard::none, false);
	const auto bound_after = run(gpu_bound, 177, 120, true, true, guard::none, false);
	// Many draws and a fast GPU: the per-frame budget is the limit.
	const timing many{0.02, 0.002, 0.05, 2.0, 0.5};
	const auto many_after = run(many, 1000, 40, true, true);
	// Disabled and guarded: the 560 boundaries exactly.
	const auto disabled = run(combat, 177, 120, true, false);
	const auto guarded_u = run(combat, 177, 120, true, true, guard::uninterruptible);
	const auto guarded_f = run(combat, 177, 120, true, true, guard::flushing);
	const auto guarded_d = run(combat, 177, 120, true, true, guard::deadlock);

	const outcome* all[] = {&combat_after, &light_after, &bound_after, &many_after, &disabled, &guarded_u, &guarded_f, &guarded_d};
	for (const auto* o : all)
	{
		ok &= expect(!o->early_while_busy, "no early submission while the GPU has work");
		ok &= expect(o->max_in_frame <= early::max_per_frame, "per-frame budget");
		ok &= expect(o->early == 0 || o->min_early_chunk >= early::min_draws, "minimum chunk");
	}

	// The submitted draw sequence is the recorded one: only boundaries move.
	ok &= expect(combat_after.order == combat_before.order, "combat order");
	ok &= expect(light_after.order == light_before.order, "light order");
	ok &= expect(bound_after.order == bound_before.order, "gpu-bound order");

	// Below one chunk, disabled, or guarded: exactly the 560 boundaries.
	ok &= expect(light_after.sizes == light_before.sizes && light_after.early == 0, "light unchanged");
	ok &= expect(disabled.sizes == combat_before.sizes && disabled.early == 0, "disabled unchanged");
	for (const auto* o : {&guarded_u, &guarded_f, &guarded_d})
		ok &= expect(o->sizes == combat_before.sizes && o->early == 0 && !o->early_while_guarded, "guard keeps boundaries");

	// A GPU that never drains never sees an early submission: only the first frame,
	// before anything is queued, can use one, and the throughput-limited frame time
	// does not get worse.
	ok &= expect(bound_after.early <= early::max_per_frame, "gpu-bound: early submissions only before the queue fills");
	ok &= expect(bound_after.busy > 0, "gpu-bound checks counted as busy");
	ok &= expect(bound_after.frame_time <= bound_before.frame_time * 1.01, "gpu-bound frame time not worse");

	// The cap binds when the GPU keeps draining.
	ok &= expect(many_after.max_in_frame == early::max_per_frame && many_after.capped > 0, "cap reached");

	// Combat: the GPU starts during recording, so the guest waits less at the readback.
	ok &= expect(combat_after.early > 0, "combat uses early submissions");
	ok &= expect(combat_after.last_frame_early > 0 && many_after.last_frame_early == early::max_per_frame, "the budget resets every frame");
	ok &= expect(combat_after.readback_wait < combat_before.readback_wait, "combat readback wait decreases");
	ok &= expect(combat_after.frame_time < combat_before.frame_time, "combat frame time decreases");

	if (!ok) return 1;
	std::printf("{\"passed\":true,\"decisions\":%u,\"scenarios\":8,"
		"\"combat\":{\"readbackWaitBeforeMsPerFrame\":%.3f,\"readbackWaitAfterMsPerFrame\":%.3f,"
		"\"frameBeforeMs\":%.3f,\"frameAfterMs\":%.3f,\"earlyPerFrame\":%.2f,\"earlyDrawsPerSubmit\":%.1f,"
		"\"submissionsBeforePerFrame\":%.2f,\"submissionsAfterPerFrame\":%.2f},"
		"\"lightUnchanged\":true,\"gpuBound\":{\"earlyTotal\":%llu,\"frameBeforeMs\":%.3f,\"frameAfterMs\":%.3f},\"disabledIdenticalTo560\":true,\"guardsKeepBoundaries\":3,"
		"\"capReachedWithFastGpu\":%u,\"orderPreserved\":true,\"minDraws\":%u,\"maxPerFrame\":%u}\n",
		decisions,
		combat_before.readback_wait / 120, combat_after.readback_wait / 120,
		combat_before.frame_time, combat_after.frame_time,
		combat_after.early / 120.0, combat_after.early ? double(combat_after.early_draws) / combat_after.early : 0.0,
		combat_before.sizes.size() / 120.0, combat_after.sizes.size() / 120.0,
		static_cast<unsigned long long>(bound_after.early), bound_before.frame_time, bound_after.frame_time,
		many_after.max_in_frame, early::min_draws, early::max_per_frame);
	return 0;
}
