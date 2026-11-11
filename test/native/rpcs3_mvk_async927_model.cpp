// SPDX-License-Identifier: GPL-2.0-only
// Core 927 host model (REWINDBOX_MVK_ASYNC_DEFINITIVE_927, REWINDBOX_GPU_BACKGROUND_GATE_927).
//
// Compiled against the real headers of a materialized Core source (-I<source>/rpcs3): the encoding-queue registry
// (ios/IOSMoltenVKExecQueue.h), its tickets (ios/IOSMoltenVKExec.h) and the background gate
// (ios/IOSGpuBackgroundGate.h) run unchanged. On macOS the queue is a real libdispatch serial queue, created the way
// MoltenVK creates its encoding queue; elsewhere test/native/dispatch_shim provides the same few calls on a thread.
//
// What stands for MoltenVK and iOS is a model of three rules, each copied from the MoltenVK tree the Core links
// (db660224) or from the device journals, and each exercised with the rule the Core had before 927 as control:
// - MVKSemaphoreMTLEvent (MVKSync.mm:121-135): vkAcquireNextImageKHR reads the semaphore's counter on the calling
//   thread; the queued submit that waits for the semaphore advances it when it is encoded.
// - MVKQueryPool (MVKQueryPool.mm:33-135): a query becomes "written by the device" when vkCmdEndQuery is encoded and
//   available when the GPU completes; vkGetQueryPoolResults(WAIT) blocks only between the two.
// - iOS refuses a command buffer committed once the application is in the background (IPA 650, pid 8767: the device
//   was lost as the application entered the background).
// No iPhone result is inferred.
//
// Sequencing: a scenario never assumes how long the host takes to start, wake or schedule a thread (the macOS runner
// under AddressSanitizer took more than 30 ms to bring a new thread to its first call). A step that must still be in
// progress is held by a latch the scenario releases; a step that must have happened is waited for (eventually) or
// seen through a counter of the Core itself (a wait that outlasts wait_limit counts a timeout). The only durations
// compared are lower bounds of waits that cannot end early.
#include "ios/IOSGpuBackgroundGate.h"
#include "ios/IOSMoltenVKExecQueue.h"

#include <algorithm>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <cstdio>
#include <mutex>
#include <thread>
#include <vector>

namespace exec = rpcs3::ios::moltenvk_exec;
namespace gpu_gate = rpcs3::ios::gpu_gate;
using exec::gcd::registry;
using namespace std::chrono_literals;

static int g_failures = 0;
#define CHECK(condition) do { if (!(condition)) { std::fprintf(stderr, "FAIL %s:%d %s\n", __FILE__, __LINE__, #condition); g_failures++; } } while (0)

static double ms_since(std::chrono::steady_clock::time_point begin)
{
	return std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - begin).count();
}

// Holds a step of a scenario until the scenario lets it go on.
struct latch
{
	std::mutex mutex;
	std::condition_variable cv;
	bool open = false;

	void release()
	{
		// Notified under the lock: the waiter may destroy the latch as soon as it can lock again.
		std::lock_guard lock(mutex);
		open = true;
		cv.notify_all();
	}

	void wait()
	{
		std::unique_lock lock(mutex);
		cv.wait(lock, [this] { return open; });
	}
};

// Waits for something another thread is about to do. The limit only ends a run that is already wrong.
template <typename F>
static bool eventually(F&& condition, std::chrono::milliseconds limit = std::chrono::seconds(60))
{
	const auto end = std::chrono::steady_clock::now() + limit;
	while (!condition())
	{
		if (std::chrono::steady_clock::now() >= end)
		{
			return false;
		}

		std::this_thread::sleep_for(std::chrono::milliseconds(1));
	}

	return true;
}

// RPCS3IOSPlatform.mm's rbx_mvk_exec_q_create, minus the C linkage.
static dispatch_queue_t hook(const char* label)
{
#ifdef __APPLE__
	const dispatch_queue_attr_t attr = dispatch_queue_attr_make_with_qos_class(DISPATCH_QUEUE_SERIAL, QOS_CLASS_USER_INTERACTIVE, 0);
#else
	const dispatch_queue_attr_t attr = DISPATCH_QUEUE_SERIAL;
#endif
	dispatch_queue_t queue = dispatch_queue_create(label, attr);
	registry::instance().record(queue, label);
	return queue;
}

// A submission on MoltenVK's encoding queue: encoding lasts until the scenario releases it.
struct job
{
	std::atomic<bool> done{false};
	latch encoding;
};

static void run_job(void* context)
{
	auto* item = static_cast<job*>(context);
	item->encoding.wait();
	item->done.store(true, std::memory_order_release);
}

static int g_presenting_vk_queue = 0; // its address stands for the VkQueue handle
static int g_transfer_vk_queue = 0;

// ---- 1. Tickets of submissions, and waits that are never abandoned (real registry) ------------------------------
static void tickets(dispatch_queue_t mvk)
{
	auto& queues = registry::instance();
	const auto fence_site = static_cast<std::size_t>(exec::wait_site::fence);
	const auto query_site = static_cast<std::size_t>(exec::wait_site::query);

	// Only the presenting queue is ticketed, once the device told which VkQueue it is.
	CHECK(queues.mark_submit(&g_presenting_vk_queue) == 0);
	queues.set_presenting_queue(&g_presenting_vk_queue);
	CHECK(queues.mark_submit(&g_transfer_vk_queue) == 0 && queues.mark_submit(nullptr) == 0);
	CHECK(exec::submits_marked.load() == 0);

	job first, later;
	dispatch_async_f(mvk, &first, run_job);
	const std::uint64_t t1 = queues.mark_submit(&g_presenting_vk_queue);
	dispatch_async_f(mvk, &later, run_job);
	const std::uint64_t t2 = queues.mark_submit(&g_presenting_vk_queue);
	CHECK(t1 != 0 && t2 == t1 + 1 && exec::submits_marked.load() == 2);

	// The fence wait of the first submission sleeps for as long as MoltenVK encodes it. Here that outlasts wait_limit:
	// one period is counted and the wait goes on (before 927 only the present barrier waited, and it gave up there).
	const std::uint64_t acquire_timeouts_before = exec::acquire_timeouts.load();
	std::atomic<bool> returned{false}, waited{false};
	std::thread waiter([&]
	{
		waited.store(queues.wait_for_encoding(t1, exec::wait_site::fence));
		returned.store(true);
	});
	CHECK(eventually([] { return exec::encode_wait_timeouts.load() >= 1; })); // it has been inside for wait_limit
	CHECK(!returned.load());
	first.encoding.release();
	waiter.join();
	CHECK(waited.load() && first.done.load(std::memory_order_acquire));
	CHECK(!later.done.load(std::memory_order_acquire)); // exactly its own submission: the next one is still being encoded
	CHECK(exec::encode_waits[fence_site].load() == 1 &&
		exec::encode_wait_us[fence_site].load() >= static_cast<std::uint64_t>(exec::wait_limit.count()) * 1000);
	CHECK(exec::acquire_timeouts.load() == acquire_timeouts_before); // counted for the fence, not for the acquisition

	// Already encoded, or no ticket (synchronous submits): no wait, nothing counted.
	CHECK(!queues.wait_for_encoding(t1, exec::wait_site::fence) && !queues.wait_for_encoding(0, exec::wait_site::query));
	CHECK(exec::encode_waits[fence_site].load() == 1 && exec::encode_waits[query_site].load() == 0);

	// The gather's wait, on its own counter. Whether it found the submission still being encoded is the host's
	// scheduling; what holds either way: it is encoded on return, and a wait that happened is counted once.
	std::atomic<bool> about_to_wait{false};
	std::thread encoder([&]
	{
		eventually([&] { return about_to_wait.load(); });
		std::this_thread::sleep_for(50ms);
		later.encoding.release();
	});
	about_to_wait.store(true);
	const bool query_waited = queues.wait_for_encoding(t2, exec::wait_site::query);
	encoder.join();
	CHECK(later.done.load(std::memory_order_acquire));
	CHECK(exec::encode_waits[query_site].load() == (query_waited ? 1u : 0u) && exec::encode_waits[fence_site].load() == 1);

	// A present whose encoding outlasts wait_limit (2 s): the acquisition still waits for it. Before 927 it went on
	// after 2 s with the present still queued. MoltenVK finishes here only once the Core has counted that period.
	job slow;
	dispatch_async_f(mvk, &slow, run_job);
	const std::uint64_t present = queues.mark_present();
	const std::uint64_t waits_before = exec::acquire_waits.load(), timeouts_before = exec::acquire_timeouts.load();
	const std::uint64_t encode_timeouts_before = exec::encode_wait_timeouts.load();
	std::thread slow_encoder([&]
	{
		eventually([&] { return exec::acquire_timeouts.load() > timeouts_before; });
		slow.encoding.release();
	});
	const auto begin = std::chrono::steady_clock::now();
	queues.wait_for_present(present);
	CHECK(slow.done.load(std::memory_order_acquire));
	CHECK(ms_since(begin) >= static_cast<double>(exec::wait_limit.count()));
	slow_encoder.join();
	CHECK(exec::acquire_waits.load() == waits_before + 1 && exec::acquire_timeouts.load() >= timeouts_before + 1);
	CHECK(exec::encode_wait_timeouts.load() == encode_timeouts_before); // counted for the acquisition only
}

// ---- 2. MoltenVK's event semaphore: why the acquisition must never overtake -------------------------------------
// MVKSemaphoreMTLEvent. The real counter is a plain field read by the acquiring thread and written by the queue
// thread; it is atomic here so that the control can run under ThreadSanitizer and show the logical failure.
struct event_semaphore
{
	std::atomic<std::uint64_t> value{1};    // _mtlEventValue
	std::atomic<std::uint64_t> signaled{0}; // the MTLEvent's signaledValue

	std::uint64_t defer_signal() const { return value.load(); } // vkAcquireNextImageKHR, calling thread

	void encode_deferred_signal(std::uint64_t token) // committed by the acquisition itself when an image is free
	{
		std::uint64_t seen = signaled.load();
		while (seen < token && !signaled.compare_exchange_weak(seen, token))
		{
		}
	}

	std::uint64_t encode_wait() { return value.fetch_add(1); } // queue thread, when the waiting submit is encoded
};

struct frame_model
{
	event_semaphore semaphores[2]; // one acquisition semaphore per frame context, used in turn
	std::mutex mutex;
	std::vector<std::pair<int, std::uint64_t>> waits; // (context, value the GPU waits for)
};

struct frame_submit
{
	frame_model* model = nullptr;
	int context = 0;
	latch* stalled = nullptr; // earlier commands of the buffer take long to encode
	std::atomic<bool> encoded{false};
};

static void encode_frame_submit(void* raw)
{
	auto* submit = static_cast<frame_submit*>(raw);
	std::this_thread::sleep_for(1ms); // earlier commands of the buffer
	if (submit->stalled)
	{
		submit->stalled->wait();
	}

	const std::uint64_t needed = submit->model->semaphores[submit->context].encode_wait();
	{
		std::lock_guard lock(submit->model->mutex);
		submit->model->waits.emplace_back(submit->context, needed);
	}
	submit->encoded.store(true, std::memory_order_release);
}

// The rule before 927, with its 2 s scaled to old_limit: wait for the last present's marker, then go on regardless.
struct old_marker
{
	std::mutex mutex;
	std::condition_variable cv;
	bool done = false;
};

static void run_old_marker(void* raw)
{
	auto* marker = static_cast<old_marker*>(raw);
	// Notified under the lock: the waiter may destroy the marker as soon as it can lock again.
	std::lock_guard lock(marker->mutex);
	marker->done = true;
	marker->cv.notify_all();
}

// Six frames; the first one's command buffer takes long to encode. Returns the waits no signal will ever satisfy.
// Rule before 927: the renderer gives up after old_limit, so it is through its six frames while that command buffer
// is still being encoded (held until then: the outcome does not depend on the host's speed). Strict rule: the
// renderer waits, so MoltenVK is given stall_ms and the renderer follows however long that takes.
static int semaphore_frames(dispatch_queue_t mvk, bool strict, int stall_ms, std::chrono::milliseconds old_limit)
{
	constexpr int frames = 6;
	frame_model model;
	std::vector<frame_submit> submits(frames);
	std::vector<old_marker> markers(frames);
	std::uint64_t last_ticket = 0;
	old_marker* last_marker = nullptr;
	latch stall;
	std::thread encoder;
	if (strict)
	{
		encoder = std::thread([&]
		{
			std::this_thread::sleep_for(std::chrono::milliseconds(stall_ms));
			stall.release();
		});
	}

	for (int frame = 0; frame < frames; frame++)
	{
		// VKGSRender::flip: the barrier, then the acquisition.
		if (strict)
		{
			registry::instance().wait_for_present(last_ticket);
		}
		else if (last_marker)
		{
			std::unique_lock lock(last_marker->mutex);
			last_marker->cv.wait_for(lock, old_limit, [&] { return last_marker->done; });
		}

		const int context = frame % 2;
		auto& semaphore = model.semaphores[context];
		semaphore.encode_deferred_signal(semaphore.defer_signal());

		// The frame's command buffer (waits for the acquisition semaphore), the present, the marker behind it.
		auto& submit = submits[frame];
		submit.model = &model;
		submit.context = context;
		submit.stalled = frame == 0 ? &stall : nullptr;
		dispatch_async_f(mvk, &submit, encode_frame_submit);
		if (strict)
		{
			last_ticket = registry::instance().mark_present();
		}
		else
		{
			last_marker = &markers[frame];
			dispatch_async_f(mvk, last_marker, run_old_marker);
		}
	}

	if (strict)
	{
		encoder.join();
	}
	else
	{
		stall.release(); // the six frames are submitted: MoltenVK encodes them now
	}

	registry::instance().drain();
	int never_signaled = 0;
	std::lock_guard lock(model.mutex);
	CHECK(model.waits.size() == static_cast<std::size_t>(frames));
	for (const auto& [context, needed] : model.waits)
	{
		if (needed > model.semaphores[context].signaled.load())
		{
			never_signaled++;
		}
	}

	return never_signaled;
}

// ---- 3. MoltenVK's query availability: why a gather sleeps until its command buffer is encoded -------------------
struct query_model
{
	enum class state { initial, device_available, available };
	std::mutex mutex;
	std::condition_variable blocker;
	state value = state::initial;
	std::uint64_t data = 0;

	void end_query() // MVKQueryPool::endQuery, when vkCmdEndQuery is encoded
	{
		std::lock_guard lock(mutex);
		value = state::device_available;
	}

	void finish(std::uint64_t result) // MVKQueryPool::finishQueries, when the GPU completes
	{
		{
			std::lock_guard lock(mutex);
			if (value == state::device_available)
			{
				data = result;
				value = state::available;
			}
		}
		blocker.notify_all();
	}

	// vkGetQueryPoolResults with VK_QUERY_RESULT_WAIT_BIT: false is VK_NOT_READY.
	bool results_wait(std::uint64_t& out)
	{
		std::unique_lock lock(mutex);
		blocker.wait(lock, [this] { return value != state::device_available; });
		if (value != state::available)
		{
			return false;
		}

		out = data;
		return true;
	}
};

struct query_submit
{
	query_model* query = nullptr;
	dispatch_queue_t gpu = nullptr;
	int encode_ms = 0;
	latch* start = nullptr; // encoding starts when the scenario says so
};

static void gpu_completes(void* raw)
{
	std::this_thread::sleep_for(30ms);
	static_cast<query_model*>(raw)->finish(7);
}

static void encode_query_submit(void* raw)
{
	auto* submit = static_cast<query_submit*>(raw);
	if (submit->start)
	{
		submit->start->wait();
	}

	std::this_thread::sleep_for(std::chrono::milliseconds(submit->encode_ms));
	submit->query->end_query();
	dispatch_async_f(submit->gpu, submit->query, gpu_completes); // committed: the GPU runs it
}

// Returns how many times the gather got VK_NOT_READY back at once (the spin of vk::query_pool_manager::get_query_result).
static std::uint64_t gather(dispatch_queue_t mvk, dispatch_queue_t gpu, bool encode_wait, std::uint64_t& result)
{
	// Control: MoltenVK starts encoding (60 ms) once the gather is seen spinning, so the spin does not depend on which
	// thread the host runs first. With the wait there is nothing to hold: the gather sleeps until the encoding is done.
	constexpr std::uint64_t seen_spinning = 1000;
	query_model query;
	latch start;
	query_submit submit{&query, gpu, 60, encode_wait ? nullptr : &start};
	dispatch_async_f(mvk, &submit, encode_query_submit);
	const std::uint64_t ticket = registry::instance().mark_submit(&g_presenting_vk_queue);
	CHECK(ticket != 0);

	if (encode_wait)
	{
		registry::instance().wait_for_encoding(ticket, exec::wait_site::query); // occlusion_data::sync()
	}

	std::uint64_t not_ready = 0;
	while (!query.results_wait(result))
	{
		if (++not_ready == seen_spinning)
		{
			start.release();
		}

		std::this_thread::yield(); // utils::pause()
	}

	CHECK(encode_wait || not_ready >= seen_spinning);

	registry::instance().drain();
	dispatch_sync_f(gpu, nullptr, [](void*) {});
	return not_ready;
}

// ---- 4. The background gate (real class) ------------------------------------------------------------------------
// iOS: a command buffer committed while the application is in the background is refused.
// From Core 928 the gate closes at the deactivation and its settle function takes a second argument: its scenarios,
// these ones included, are in test/native/rpcs3_gpu_gate928_model.cpp, and this part is compiled for Core 927 only.
#ifndef REWINDBOX_GPU_DEACTIVATION_GATE_928
struct metal_model
{
	std::atomic<bool> background{false};
	std::atomic<std::uint64_t> committed{0}, refused{0};

	void commit()
	{
		(background.load() ? refused : committed).fetch_add(1);
	}
};

static metal_model* g_metal = nullptr;
static dispatch_queue_t g_settle_queue = nullptr;
static latch* g_settle_running = nullptr; // a settle that is still running until the scenario releases it
static std::atomic<bool> g_settle_started{false}, g_settle_finished{false};

// What vk::ios_settle_queues does with Vulkan (an empty submission with a fence behind everything queued): here a
// marker behind everything queued on the encoding queue, waited for within the limit.
static bool model_settle(std::chrono::milliseconds limit)
{
	g_settle_started.store(true);
	if (g_settle_running)
	{
		g_settle_running->wait();
	}

	bool settled = true;
	if (g_settle_queue)
	{
		old_marker marker;
		dispatch_async_f(g_settle_queue, &marker, run_old_marker);
		std::unique_lock lock(marker.mutex);
		settled = marker.cv.wait_for(lock, limit, [&] { return marker.done; });
		if (!settled)
		{
			// The marker must not outlive this frame: wait for it now (the test only reaches this on a failure).
			marker.cv.wait(lock, [&] { return marker.done; });
		}
	}

	g_settle_finished.store(true);
	return settled;
}

struct submitters
{
	metal_model metal;
	std::atomic<bool> stop{false};
	std::atomic<std::uint64_t> calls{0};
	std::vector<std::thread> threads;

	// Synchronous submits: the calling thread commits inside vkQueueSubmit.
	void start(int count, bool gated)
	{
		for (int i = 0; i < count; i++)
		{
			threads.emplace_back([this, gated]
			{
				while (!stop.load())
				{
					if (gated)
					{
						const gpu_gate::pass pass; // vk::queue_submit_impl
						metal.commit();
						std::this_thread::sleep_for(200us);
					}
					else
					{
						metal.commit();
						std::this_thread::sleep_for(200us);
					}

					calls.fetch_add(1);
					std::this_thread::sleep_for(100us);
				}
			});
		}
	}

	void join()
	{
		stop.store(true);
		for (auto& thread : threads)
		{
			thread.join();
		}
	}
};

struct gate_results
{
	std::uint64_t refused_without_gate = 0, refused_with_gate = 0;
	std::uint64_t refused_async_without_settle = 0, refused_async_with_settle = 0;
};

static void queued_commit(void*)
{
	std::this_thread::sleep_for(2ms); // encoding
	g_metal->commit();
}

static gate_results gate_model(dispatch_queue_t mvk)
{
	gate_results results;
	auto& gate = gpu_gate::gate::instance();

	// Without the gate: the threads keep committing after the application is in the background.
	{
		submitters control;
		control.start(3, false);
		CHECK(eventually([&] { return control.metal.committed.load() > 0; }));
		control.metal.background.store(true);
		CHECK(eventually([&] { return control.metal.refused.load() > 0; }));
		std::this_thread::sleep_for(30ms);
		control.join();
		results.refused_without_gate = control.metal.refused.load();
	}

	// With the gate: closed and idle before the transition finishes, open again once the application is active.
	{
		submitters gated;
		gated.start(3, true);
		CHECK(eventually([&] { return gated.metal.committed.load() > 0; }));
		const std::uint64_t closes_before = gpu_gate::closes.load(), parks_before = gpu_gate::parks.load();
		gate.app_entered_background();           // UIApplicationDidEnterBackgroundNotification, posting thread
		const std::uint64_t committed_at_close = gated.metal.committed.load();
		gated.metal.background.store(true);      // the transition is over: iOS refuses from here on
		CHECK(eventually([&] { return gpu_gate::parks.load() >= parks_before + 3; })); // the calls are waiting, not dropped
		std::this_thread::sleep_for(50ms);
		CHECK(gate.closed() && gpu_gate::closes.load() == closes_before + 1);
		CHECK(gated.metal.committed.load() == committed_at_close); // nothing was committed in the background
		gated.metal.background.store(false);
		gate.app_became_active();                // UIApplicationDidBecomeActiveNotification
		CHECK(eventually([&] { return gated.metal.committed.load() > committed_at_close; })); // and they run afterwards
		CHECK(!gate.closed());
		gated.join();
		results.refused_with_gate = gated.metal.refused.load();
		CHECK(gated.metal.committed.load() == gated.calls.load()); // every call committed once
	}

	// Asynchronous submits: 30 submissions are queued (2 ms of encoding each) when the application leaves. Without a
	// settle nothing waits for the queue: it is held until the transition is over, so that what was queued is still
	// there whatever the host's speed. With the settle the transition itself waits for the queue.
	for (const bool settle : {false, true})
	{
		metal_model metal;
		g_metal = &metal;
		g_settle_queue = settle ? mvk : nullptr;
		gate.set_settle(&model_settle);
		job still_queued;
		if (!settle)
		{
			dispatch_async_f(mvk, &still_queued, run_job);
		}

		for (int i = 0; i < 30; i++)
		{
			const gpu_gate::pass pass;
			dispatch_async_f(mvk, nullptr, queued_commit);
		}

		const std::uint64_t settles_before = gpu_gate::settles.load(), timeouts_before = gpu_gate::settle_timeouts.load();
		gate.app_entered_background();
		metal.background.store(true);
		still_queued.encoding.release();
		registry::instance().drain(); // whatever is still queued is encoded and committed now, in the background
		(settle ? results.refused_async_with_settle : results.refused_async_without_settle) = metal.refused.load();
		CHECK(metal.committed.load() + metal.refused.load() == 30);
		CHECK(metal.refused.load() == (settle ? 0u : 30u));
		CHECK(gpu_gate::settles.load() == settles_before + 1 && gpu_gate::settle_timeouts.load() == timeouts_before);
		gate.set_settle(nullptr);
		gate.app_became_active();
		g_metal = nullptr;
	}

	// A call already inside when the gate closes is waited for, up to the limit, and counted beyond it.
	{
		latch call;
		std::atomic<bool> inside{false};
		std::thread caller([&]
		{
			const gpu_gate::pass pass;
			inside.store(true);
			call.wait();
			// The same thread, one level down, while the gate is closed: part of the same call, it does not park.
			const gpu_gate::pass nested;
			inside.store(false);
		});
		CHECK(eventually([&] { return inside.load(); }));

		const std::uint64_t timeouts_before = gpu_gate::in_flight_timeouts.load();
		const auto begin = std::chrono::steady_clock::now();
		CHECK(!gate.close(20ms));
		CHECK(ms_since(begin) >= 15 && gpu_gate::in_flight_timeouts.load() == timeouts_before + 1);
		call.release();
		CHECK(gate.close(60s)); // it leaves; the gate is idle
		CHECK(!inside.load() && gpu_gate::in_flight_timeouts.load() == timeouts_before + 1);
		caller.join();
		gate.open();
	}

	// A call still inside after the limit of the transition: no settle, the queues are not the posting thread's then.
	{
		latch call;
		std::atomic<bool> inside{false};
		std::thread caller([&]
		{
			const gpu_gate::pass pass;
			inside.store(true);
			call.wait();
		});
		CHECK(eventually([&] { return inside.load(); }));

		g_settle_queue = nullptr;
		gate.set_settle(&model_settle);
		const std::uint64_t settles_before = gpu_gate::settles.load(), timeouts_before = gpu_gate::in_flight_timeouts.load();
		const auto begin = std::chrono::steady_clock::now();
		gate.app_entered_background();
		CHECK(ms_since(begin) >= static_cast<double>(gpu_gate::in_flight_limit.count()) - 5);
		CHECK(gpu_gate::settles.load() == settles_before && gpu_gate::in_flight_timeouts.load() == timeouts_before + 1);
		CHECK(gate.closed());
		call.release();
		caller.join();
		gate.set_settle(nullptr);
		gate.app_became_active();
	}

	// An emulator that is being stopped while the application is in the background: its threads do not park.
	{
		static std::atomic<bool> stopping{false};
		gate.set_bypass([]() -> bool { return stopping.load(); });
		gate.app_entered_background();
		std::atomic<bool> through{false};
		const std::uint64_t bypasses_before = gpu_gate::park_bypasses.load(), parks_before = gpu_gate::parks.load();
		std::thread caller([&]
		{
			const gpu_gate::pass pass; // the device wait of VKGSRender::~VKGSRender
			through.store(true);
		});
		CHECK(eventually([&] { return gpu_gate::parks.load() == parks_before + 1; })); // parked: the emulator is running
		std::this_thread::sleep_for(250ms);
		CHECK(!through.load() && gate.closed());
		stopping.store(true);
		caller.join();
		CHECK(through.load() && gate.closed() && gpu_gate::park_bypasses.load() == bypasses_before + 1);
		// Its next calls do not wait at all (a stopping renderer makes many): none of them is counted as parked.
		for (int i = 0; i < 20; i++)
		{
			const gpu_gate::pass pass;
		}
		CHECK(gpu_gate::parks.load() == parks_before + 1 && gpu_gate::park_bypasses.load() == bypasses_before + 21);
		stopping.store(false);
		gate.set_bypass(nullptr);
		gate.app_became_active();
	}

	// The renderer takes its settle function back while a settle runs: it waits for the settle to finish.
	{
		latch running;
		g_settle_queue = nullptr;
		g_settle_running = &running;
		g_settle_started.store(false);
		g_settle_finished.store(false);
		gate.set_settle(&model_settle);
		std::thread transition([&] { gate.app_entered_background(); });
		CHECK(eventually([] { return g_settle_started.load(); })); // the settle is running
		std::atomic<bool> taken{false}, finished_when_taken{false};
		std::thread renderer([&]
		{
			gate.set_settle(nullptr); // VKGSRender::~VKGSRender
			finished_when_taken.store(g_settle_finished.load());
			taken.store(true);
		});
		std::this_thread::sleep_for(100ms);
		CHECK(!taken.load()); // still waiting for it
		running.release();
		renderer.join();
		transition.join();
		CHECK(taken.load() && finished_when_taken.load()); // it came back only once the settle had finished
		g_settle_running = nullptr;
		gate.app_became_active();
	}

	return results;
}
#endif // REWINDBOX_GPU_DEACTIVATION_GATE_928

int main()
{
	auto& queues = registry::instance();
	queues.begin_device(0, 0);
	dispatch_queue_t mvk = hook("MoltenVKQueue-0-0-1.0-Dispatch");
	dispatch_queue_t gpu = dispatch_queue_create("gpu-model", DISPATCH_QUEUE_SERIAL); // not MoltenVK's: not recorded
	CHECK(queues.queue_count() == 1 && queues.has_present_queue());

	tickets(mvk);

	const int hazards_old = semaphore_frames(mvk, false, 400, 20ms);
	const int hazards_strict = semaphore_frames(mvk, true, 400, 20ms);
	CHECK(hazards_old > 0 && hazards_strict == 0);

	std::uint64_t result_old = 0, result_new = 0;
	const std::uint64_t spins_old = gather(mvk, gpu, false, result_old);
	const std::uint64_t spins_new = gather(mvk, gpu, true, result_new);
	CHECK(result_old == 7 && result_new == 7); // the same answer
	CHECK(spins_old > 100 && spins_new == 0);  // without a spin

#ifndef REWINDBOX_GPU_DEACTIVATION_GATE_928
	const gate_results gate = gate_model(mvk);
	CHECK(gate.refused_without_gate > 0 && gate.refused_with_gate == 0);
	CHECK(gate.refused_async_without_settle > 0 && gate.refused_async_with_settle == 0);
#endif

	queues.begin_device(0, 0);
	dispatch_release(mvk);
	dispatch_release(gpu);

	std::printf("{\"failures\": %d, \"semaphore\": {\"neverSignaledOldRule\": %d, \"neverSignaledStrict\": %d}, "
		"\"query\": {\"notReadySpinsOldRule\": %llu, \"notReadySpinsEncodeWait\": %llu}, ",
		g_failures, hazards_old, hazards_strict, static_cast<unsigned long long>(spins_old),
		static_cast<unsigned long long>(spins_new));
#ifndef REWINDBOX_GPU_DEACTIVATION_GATE_928
	std::printf("\"gate\": {\"refusedWithoutGate\": %llu, \"refusedWithGate\": %llu, \"refusedQueuedWithoutSettle\": %llu, "
		"\"refusedQueuedWithSettle\": %llu}}\n",
		static_cast<unsigned long long>(gate.refused_without_gate),
		static_cast<unsigned long long>(gate.refused_with_gate), static_cast<unsigned long long>(gate.refused_async_without_settle),
		static_cast<unsigned long long>(gate.refused_async_with_settle));
#else
	std::printf("\"gate\": null}\n");
#endif
	return g_failures ? 1 : 0;
}
