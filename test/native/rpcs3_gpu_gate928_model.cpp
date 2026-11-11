// SPDX-License-Identifier: GPL-2.0-only
// Core 928 host model (REWINDBOX_GPU_DEACTIVATION_GATE_928): the GPU gate closed when the application is deactivated.
//
// Compiled against the real headers of a materialized Core source (-I<source>/rpcs3): the gate
// (ios/IOSGpuBackgroundGate.h) and the encoding-queue registry (ios/IOSMoltenVKExecQueue.h) run unchanged. On macOS the
// queue is a real libdispatch serial queue; elsewhere test/native/dispatch_shim provides the same few calls on a thread.
//
// What stands for iOS is one rule, read in Apple's Metal documentation ("Preparing your Metal app to run in the
// background") and in the device journal of IPA 650 (pid 8767): some time after the application is deactivated the
// system restricts its use of Metal, and it does not wait for the application to have handled the background
// notification ("Device lost" 30 ms before the host's observer of that notification ran). A command buffer committed
// after the restriction is refused. The rule of Core 927 (the gate closed by the background notification only) is the
// control of the first scenario.
//
// Sequencing: no scenario assumes how long the host takes to start, wake or schedule a thread. A step that must still
// be in progress is held by a latch the scenario releases; a step that must have happened is waited for (eventually).
// The only durations compared are lower bounds of waits that cannot end early. No iPhone result is inferred.
#include "ios/IOSGpuBackgroundGate.h"
#include "ios/IOSMoltenVKExecQueue.h"

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

// iOS: a command buffer committed once the system has restricted the application is refused.
struct metal_model
{
	std::atomic<bool> restricted{false};
	std::atomic<std::uint64_t> committed{0}, refused{0};

	void commit()
	{
		(restricted.load() ? refused : committed).fetch_add(1);
	}
};

struct marker
{
	std::mutex mutex;
	std::condition_variable cv;
	bool done = false;
};

static void run_marker(void* raw)
{
	auto* item = static_cast<marker*>(raw);
	// Notified under the lock: the waiter may destroy the marker as soon as it can lock again.
	std::lock_guard lock(item->mutex);
	item->done = true;
	item->cv.notify_all();
}

// ---- The settle function of the model ---------------------------------------------------------------------------
// What vk::ios_settle_queues does with Vulkan (an empty submission with a fence behind everything queued) is here a
// marker behind everything queued on the encoding queue, waited for within the limit. The text of the real function
// is executed by test/native/rpcs3_gpu_settle928_model.cpp.
static metal_model* g_metal = nullptr;
static dispatch_queue_t g_settle_queue = nullptr;
static latch* g_settle_running = nullptr;      // a settle that is still running until the scenario releases it
static std::atomic<bool> g_settle_started{false}, g_settle_finished{false};
static std::atomic<bool> g_settle_answer{true}; // what a settle without a queue answers
static std::atomic<std::uint64_t> g_settle_calls{0}, g_settle_resumes{0};

static bool model_settle(std::chrono::milliseconds limit, bool resume)
{
	g_settle_calls.fetch_add(1);
	if (resume)
	{
		g_settle_resumes.fetch_add(1);
	}

	g_settle_started.store(true);
	if (g_settle_running)
	{
		g_settle_running->wait();
	}

	bool settled = g_settle_answer.load();
	if (g_settle_queue)
	{
		marker behind;
		dispatch_async_f(g_settle_queue, &behind, run_marker);
		std::unique_lock lock(behind.mutex);
		settled = behind.cv.wait_for(lock, limit, [&] { return behind.done; });
		if (!settled)
		{
			// The marker must not outlive this frame: wait for it now (the test only reaches this on a failure).
			behind.cv.wait(lock, [&] { return behind.done; });
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

	// Synchronous submits: the calling thread commits inside vkQueueSubmit, behind the gate.
	void start(int count)
	{
		for (int i = 0; i < count; i++)
		{
			threads.emplace_back([this]
			{
				while (!stop.load())
				{
					{
						const gpu_gate::pass pass; // vk::queue_submit_impl
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

// ---- 1. Deactivation, restriction, then the background notification ---------------------------------------------
// Three threads submit frames. The application is deactivated; the system restricts Metal; the application then
// handles the background notification. close_at_deactivation false is Core 927: the gate closes at the last step only.
// Returns the commits the system refused.
static std::uint64_t leave_the_application(bool close_at_deactivation)
{
	auto& gate = gpu_gate::gate::instance();
	submitters frames;
	frames.start(3);
	CHECK(eventually([&] { return frames.metal.committed.load() > 0; }));

	const std::uint64_t closes_before = gpu_gate::closes.load(), parks_before = gpu_gate::parks.load();
	if (close_at_deactivation)
	{
		gate.app_will_resign_active(); // UIApplicationWillResignActiveNotification, posting thread
		CHECK(gate.closed() && gpu_gate::closes.load() == closes_before + 1);
	}

	const std::uint64_t committed_at_deactivation = frames.metal.committed.load();
	frames.metal.restricted.store(true); // the system restricts Metal: it does not wait for the application
	if (close_at_deactivation)
	{
		CHECK(eventually([&] { return gpu_gate::parks.load() >= parks_before + 3; })); // the calls are waiting, not dropped
		std::this_thread::sleep_for(50ms);
		CHECK(frames.metal.committed.load() == committed_at_deactivation && frames.metal.refused.load() == 0);
	}
	else
	{
		CHECK(eventually([&] { return frames.metal.refused.load() > 0; })); // frames still reach the GPU: refused
		std::this_thread::sleep_for(30ms);
	}

	gate.app_entered_background(); // UIApplicationDidEnterBackgroundNotification, handled after the restriction
	CHECK(gate.closed());
	const std::uint64_t refused = frames.metal.refused.load();
	CHECK(eventually([&] { return gpu_gate::parks.load() >= parks_before + 3; }));
	std::this_thread::sleep_for(20ms);
	CHECK(frames.metal.refused.load() == refused); // closed now in both rules

	frames.metal.restricted.store(false);
	const std::uint64_t committed_in_background = frames.metal.committed.load();
	gate.app_became_active(); // UIApplicationDidBecomeActiveNotification
	CHECK(eventually([&] { return frames.metal.committed.load() > committed_in_background; })); // and they run afterwards
	CHECK(!gate.closed());
	frames.join();
	CHECK(frames.metal.committed.load() + frames.metal.refused.load() == frames.calls.load()); // every call happened once
	return frames.metal.refused.load();
}

static void queued_commit(void*)
{
	std::this_thread::sleep_for(2ms); // encoding
	g_metal->commit();
}

struct held_job
{
	latch encoding;
};

static void run_held_job(void* raw)
{
	static_cast<held_job*>(raw)->encoding.wait();
}

// ---- 2. Asynchronous submits: what is queued when the application is deactivated --------------------------------
// 30 submissions are queued (2 ms of encoding each). Without a settle nothing waits for the queue: it is held until
// the restriction, so that what was queued is still there whatever the host's speed. With the settle the deactivation
// itself waits for the queue. Returns the commits refused.
static std::uint64_t queued_at_the_deactivation(dispatch_queue_t mvk, bool settle)
{
	auto& gate = gpu_gate::gate::instance();
	metal_model metal;
	g_metal = &metal;
	g_settle_queue = settle ? mvk : nullptr;
	gate.set_settle(settle ? &model_settle : nullptr);
	held_job still_queued;
	if (!settle)
	{
		dispatch_async_f(mvk, &still_queued, run_held_job);
	}

	for (int i = 0; i < 30; i++)
	{
		const gpu_gate::pass pass;
		dispatch_async_f(mvk, nullptr, queued_commit);
	}

	const std::uint64_t settles_before = gpu_gate::settles.load(), timeouts_before = gpu_gate::settle_timeouts.load();
	gate.app_will_resign_active();
	metal.restricted.store(true);
	still_queued.encoding.release();
	registry::instance().drain(); // whatever is still queued is encoded and committed now, after the restriction
	CHECK(metal.committed.load() + metal.refused.load() == 30);
	CHECK(metal.refused.load() == (settle ? 0u : 30u));
	CHECK(gpu_gate::settles.load() == settles_before + (settle ? 1u : 0u) && gpu_gate::settle_timeouts.load() == timeouts_before);
	gate.app_entered_background();
	CHECK(gpu_gate::settles.load() == settles_before + (settle ? 1u : 0u)); // nothing left for the background notification
	gate.set_settle(nullptr);
	gate.app_became_active();
	g_settle_queue = nullptr;
	g_metal = nullptr;
	return metal.refused.load();
}

// ---- 3. The gate itself -----------------------------------------------------------------------------------------
static void gate_rules()
{
	auto& gate = gpu_gate::gate::instance();
	const auto calls = [] { return g_settle_calls.load(); };
	const auto resumes = [] { return g_settle_resumes.load(); };

	// The deactivation settles; the background notification has nothing left to do; reactivation opens.
	{
		gate.set_settle(&model_settle);
		const std::uint64_t calls_before = calls(), resumes_before = resumes();
		const std::uint64_t deactivations_before = gpu_gate::deactivations.load(), backgrounds_before = gpu_gate::backgrounds.load();
		const std::uint64_t settles_before = gpu_gate::settles.load(), waits_before = gpu_gate::settle_waits.load();
		const std::uint64_t closes_before = gpu_gate::closes.load(), opens_before = gpu_gate::opens.load();
		gate.app_will_resign_active();
		CHECK(gate.closed() && calls() == calls_before + 1 && resumes() == resumes_before);
		gate.app_entered_background();
		CHECK(gate.closed() && calls() == calls_before + 1); // settled already: no second submission
		CHECK(gpu_gate::deactivations.load() == deactivations_before + 1 && gpu_gate::backgrounds.load() == backgrounds_before + 1);
		CHECK(gpu_gate::settles.load() == settles_before + 1 && gpu_gate::settle_waits.load() == waits_before);
		CHECK(gpu_gate::closes.load() == closes_before + 1); // closed once, by the deactivation
		gate.app_became_active();
		CHECK(!gate.closed() && gpu_gate::opens.load() == opens_before + 1);

		// Deactivated and reactivated without the background (Control Centre): the next deactivation settles anew.
		gate.app_will_resign_active();
		gate.app_became_active();
		gate.app_will_resign_active();
		CHECK(calls() == calls_before + 3 && resumes() == resumes_before);
		gate.app_became_active();
		gate.set_settle(nullptr);
	}

	// The settle of the deactivation times out: the background notification resumes it, and only until it is settled.
	{
		gate.set_settle(&model_settle);
		const std::uint64_t calls_before = calls(), resumes_before = resumes();
		const std::uint64_t timeouts_before = gpu_gate::settle_timeouts.load(), waits_before = gpu_gate::settle_waits.load();
		const std::uint64_t wait_timeouts_before = gpu_gate::settle_wait_timeouts.load();
		g_settle_answer.store(false);
		gate.app_will_resign_active();
		CHECK(calls() == calls_before + 1 && resumes() == resumes_before && gpu_gate::settle_timeouts.load() == timeouts_before + 1);
		gate.app_entered_background(); // still not settled
		CHECK(calls() == calls_before + 2 && resumes() == resumes_before + 1);
		CHECK(gpu_gate::settle_waits.load() == waits_before + 1 && gpu_gate::settle_wait_timeouts.load() == wait_timeouts_before + 1);
		g_settle_answer.store(true);
		gate.app_entered_background(); // a later notification of the same closing: resumed again, settled this time
		CHECK(calls() == calls_before + 3 && resumes() == resumes_before + 2);
		CHECK(gpu_gate::settle_waits.load() == waits_before + 2 && gpu_gate::settle_wait_timeouts.load() == wait_timeouts_before + 1);
		gate.app_entered_background(); // settled: nothing more
		CHECK(calls() == calls_before + 3 && gpu_gate::settle_timeouts.load() == timeouts_before + 1);
		gate.app_became_active();
		gate.set_settle(nullptr);
	}

	// Another renderer takes over while the gate is closed: what the previous one settled says nothing about it.
	{
		gate.set_settle(&model_settle);
		const std::uint64_t calls_before = calls(), resumes_before = resumes();
		gate.app_will_resign_active();
		gate.set_settle(nullptr);       // VKGSRender::~VKGSRender
		gate.set_settle(&model_settle); // VKGSRender::VKGSRender of the next game
		gate.app_entered_background();
		CHECK(calls() == calls_before + 2 && resumes() == resumes_before); // a whole settle, not a resumed one
		gate.app_became_active();
		gate.set_settle(nullptr);
	}

	// The observers are installed while the application is not active: closed and settled at once, counted apart.
	{
		gate.set_settle(&model_settle);
		const std::uint64_t calls_before = calls();
		const std::uint64_t found_before = gpu_gate::found_not_active.load(), deactivations_before = gpu_gate::deactivations.load();
		gate.app_found_not_active();
		CHECK(gate.closed() && calls() == calls_before + 1);
		CHECK(gpu_gate::found_not_active.load() == found_before + 1 && gpu_gate::deactivations.load() == deactivations_before);
		gate.app_became_active();
		gate.set_settle(nullptr);
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

	// A call still inside after the limit of the deactivation: no settle then, the queues are not the posting thread's.
	// It has left when the application enters the background: the whole settle runs there.
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

		gate.set_settle(&model_settle);
		const std::uint64_t calls_before = calls(), resumes_before = resumes();
		const std::uint64_t settles_before = gpu_gate::settles.load(), timeouts_before = gpu_gate::in_flight_timeouts.load();
		const auto begin = std::chrono::steady_clock::now();
		gate.app_will_resign_active();
		CHECK(ms_since(begin) >= static_cast<double>(gpu_gate::in_flight_limit.count()) - 5);
		CHECK(calls() == calls_before && gpu_gate::settles.load() == settles_before && gpu_gate::in_flight_timeouts.load() == timeouts_before + 1);
		CHECK(gate.closed());
		call.release();
		caller.join();
		gate.app_entered_background();
		CHECK(calls() == calls_before + 1 && resumes() == resumes_before && gpu_gate::settles.load() == settles_before + 1);
		gate.set_settle(nullptr);
		gate.app_became_active();
	}

	// An emulator that is being stopped while the application is inactive: its threads do not park.
	{
		static std::atomic<bool> stopping{false};
		gate.set_bypass([]() -> bool { return stopping.load(); });
		gate.app_will_resign_active();
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
		g_settle_running = &running;
		g_settle_started.store(false);
		g_settle_finished.store(false);
		gate.set_settle(&model_settle);
		std::thread transition([&] { gate.app_will_resign_active(); });
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
}

int main()
{
	auto& queues = registry::instance();
	queues.begin_device(0, 0);
	dispatch_queue_t mvk = hook("MoltenVKQueue-0-0-1.0-Dispatch");
	CHECK(queues.queue_count() == 1 && queues.has_present_queue());

	const std::uint64_t refused_927 = leave_the_application(false);
	const std::uint64_t refused_928 = leave_the_application(true);
	CHECK(refused_927 > 0 && refused_928 == 0);

	const std::uint64_t queued_without = queued_at_the_deactivation(mvk, false);
	const std::uint64_t queued_with = queued_at_the_deactivation(mvk, true);
	CHECK(queued_without == 30 && queued_with == 0);

	gate_rules();

	queues.begin_device(0, 0);
	dispatch_release(mvk);

	std::printf("{\"failures\": %d, \"refusedGateAtBackground\": %llu, \"refusedGateAtDeactivation\": %llu, "
		"\"refusedQueuedWithoutSettle\": %llu, \"refusedQueuedWithSettle\": %llu, \"settleCalls\": %llu, \"settleResumes\": %llu}\n",
		g_failures, static_cast<unsigned long long>(refused_927), static_cast<unsigned long long>(refused_928),
		static_cast<unsigned long long>(queued_without), static_cast<unsigned long long>(queued_with),
		static_cast<unsigned long long>(g_settle_calls.load()), static_cast<unsigned long long>(g_settle_resumes.load()));
	return g_failures ? 1 : 0;
}
