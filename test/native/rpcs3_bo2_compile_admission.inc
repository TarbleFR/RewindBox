// SPDX-License-Identifier: GPL-2.0-or-later
// Real admission bodies and host budget; controllable mutex/CV boundaries.
#include <algorithm>
#include <array>
#include <atomic>
#include <cassert>
#include <chrono>
#include <condition_variable>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <functional>
#include <memory>
#include <mutex>
#include <thread>
#include <vector>
#include "packages/neo_swap/ios/Classes/NeoSwapCompilerAPI.h"
#include "packages/neo_swap/ios/Classes/NeoSwapCompilerBudget.h"

#ifdef NDEBUG
#error "The admission regression requires active assertions"
#endif

using u64 = std::uint64_t;

namespace utils
{
u64 get_tsc()
{
	return static_cast<u64>(std::chrono::steady_clock::now().time_since_epoch().count());
}
}

// Memory sampling and profiling are boundaries, not subjects of this test.
// Fixed samples keep both versions' real admission-estimate arithmetic equal.
namespace jit_memory
{
std::atomic<void(*)()> sample_hook{nullptr};
std::atomic<u64> latest_footprint{0}, batch_peak{0}, active{0}, peak_active{0};
void maximum(std::atomic<u64>& destination, u64 value)
{
	auto old = destination.load();
	while (old < value && !destination.compare_exchange_weak(old, value)) {}
}
}

struct performance_boundary
{
	std::atomic<unsigned> waits{0};
	void record_compile_admission_mutex(u64) {}
	void record_compile_admission_wait(u64) { ++waits; }
} g_performance_registry;

std::atomic<unsigned> host_budget_signals{0};
extern "C" void NeoSwapCompilerBudgetChanged()
{
	// The production callback only merges data into a dispatch source. It
	// never enters the Core or waits for that asynchronous host task.
	++host_budget_signals;
}

namespace host
{
@HOST_CALLBACKS@
}

namespace boundary
{
struct interleaving
{
	std::mutex event_mutex;
	std::condition_variable event_cv;
	bool force_release_gap = false;
	bool wait_entered = false;
	bool release_attempted_lock = false;
	bool release_completed = false;
	bool wait_registered = false;
	unsigned lost_notifications = 0;
	unsigned wait_calls = 0;
};

std::atomic<interleaving*> current{nullptr};
thread_local bool releasing_owner = false;

// Both versions use a real mutex. The hook observes the release thread's
// attempt before it blocks; it cannot grant that thread the waiter's lock.
class mutex
{
	std::mutex value;
public:
	void lock()
	{
		if (auto* test = current.load(); test && releasing_owner)
		{
			std::lock_guard event_lock(test->event_mutex);
			test->release_attempted_lock = true;
			test->event_cv.notify_all();
		}
		value.lock();
	}
	void unlock() { value.unlock(); }
};

class condition_variable
{
	std::condition_variable_any value;
public:
	template <typename Rep, typename Period>
	void wait_for(std::unique_lock<mutex>& lock, std::chrono::duration<Rep, Period> duration)
	{
		assert(lock.owns_lock());
		assert(duration == std::chrono::milliseconds(20));
		auto* test = current.load();
		if (test)
		{
			std::unique_lock event_lock(test->event_mutex);
			const bool first = !test->wait_entered;
			test->wait_entered = true;
			++test->wait_calls;
			test->event_cv.notify_all();
			if (first && test->force_release_gap)
			{
				// The constructor has rejected the ticket and still owns the
				// admission mutex. Let the other thread run its real destructor.
				// Old API release finishes here; fixed release must block on it.
				test->event_cv.wait(event_lock, [&]
				{
					return test->release_attempted_lock || test->release_completed;
				});
			}
			test->wait_registered = true;
		}
		// The actual bounded wait remains unchanged. Assertions use ordering
		// and notification counts, never a host-time threshold or sleep guess.
		value.wait_for(lock, duration);
		if (test)
		{
			std::lock_guard event_lock(test->event_mutex);
			test->wait_registered = false;
		}
	}

	void notify_all()
	{
		if (auto* test = current.load(); test && releasing_owner)
		{
			std::lock_guard event_lock(test->event_mutex);
			if (test->wait_entered && !test->wait_registered)
				++test->lost_notifications;
		}
		value.notify_all();
	}
};
}

@BASELINE_PRODUCTION@
@CANDIDATE_PRODUCTION@

struct suite_result
{
	unsigned forced_gap_cases = 0;
	unsigned api_gap_notifications = 0;
	unsigned fallback_gap_notifications = 0;
	unsigned cancellation_cases = 0;
	unsigned concurrent_admissions = 0;
	unsigned max_concurrent_work = 0;
};

template <typename Access>
void setup(bool api, bool constrained = true)
{
	assert(host::controller().reserved() == 0);
	assert(jit_memory::active.load() == 0);
	host::controller().update(true, constrained, 0);
	Access::set_api(api ? &host::api : nullptr);
}

template <typename Access>
unsigned release_in_gap(bool use_api)
{
	using admission = typename Access::admission;
	setup<Access>(use_api);
	auto owner = std::make_unique<admission>(128, [] { return false; });
	assert(bool(*owner));
	boundary::interleaving schedule;
	schedule.force_release_gap = true;
	boundary::current.store(&schedule);
	std::thread releaser([&]
	{
		{
			std::unique_lock event_lock(schedule.event_mutex);
			schedule.event_cv.wait(event_lock, [&] { return schedule.wait_entered; });
		}
		boundary::releasing_owner = true;
		owner.reset();
		boundary::releasing_owner = false;
		{
			std::lock_guard event_lock(schedule.event_mutex);
			schedule.release_completed = true;
			schedule.event_cv.notify_all();
		}
	});
	{
		admission waiter(128, [] { return false; });
		assert(bool(waiter));
	}
	releaser.join();
	boundary::current.store(nullptr);
	assert(schedule.wait_calls > 0);
	assert(host::controller().reserved() == 0);
	assert(jit_memory::active.load() == 0);
	return schedule.lost_notifications;
}

template <typename Access>
void cancellation(bool use_api)
{
	using admission = typename Access::admission;
	setup<Access>(use_api);
	{
		admission already_stopped(128, [] { return true; });
		assert(!already_stopped);
		assert(host::controller().reserved() == 0);
	}
	auto owner = std::make_unique<admission>(128, [] { return false; });
	assert(bool(*owner));
	const u64 reserved = host::controller().reserved();
	boundary::interleaving schedule;
	boundary::current.store(&schedule);
	std::atomic<bool> stopped{false};
	std::atomic<bool> acquired{true};
	std::thread waiter([&]
	{
		admission request(128, [&] { return stopped.load(); });
		acquired.store(bool(request));
	});
	{
		std::unique_lock event_lock(schedule.event_mutex);
		schedule.event_cv.wait(event_lock, [&] { return schedule.wait_entered; });
	}
	{
		// Register the wait before testing the unchanged explicit stop wake.
		std::lock_guard lock(Access::wait_mutex());
		stopped.store(true);
	}
	Access::wake();
	waiter.join();
	boundary::current.store(nullptr);
	assert(!acquired.load());
	assert(host::controller().reserved() == reserved);
	assert(jit_memory::active.load() == 1);
	owner.reset();
	assert(host::controller().reserved() == 0);
	assert(jit_memory::active.load() == 0);
}

template <typename Access>
void concurrency(suite_result& result)
{
	using admission = typename Access::admission;
	setup<Access>(true, false);
	std::atomic<unsigned> live{0}, completed{0}, maximum{0};
	std::vector<std::thread> workers;
	for (unsigned worker = 0; worker < 12; ++worker)
	{
		workers.emplace_back([&]
		{
			for (unsigned iteration = 0; iteration < 64; ++iteration)
			{
				admission request(128, [] { return false; });
				assert(bool(request));
				const unsigned now = ++live;
				assert(now <= 3);
				auto previous = maximum.load();
				while (previous < now && !maximum.compare_exchange_weak(previous, now)) {}
				std::this_thread::yield();
				--live;
				++completed;
			}
		});
	}
	for (auto& worker : workers) worker.join();
	assert(completed.load() == 12 * 64);
	assert(live.load() == 0);
	assert(host::controller().reserved() == 0);
	assert(jit_memory::active.load() == 0);
	result.concurrent_admissions = completed.load();
	result.max_concurrent_work = maximum.load();
}

template <typename Access>
suite_result run_suite(unsigned expected_api_gaps)
{
	suite_result result;
	for (unsigned iteration = 0; iteration < 16; ++iteration)
	{
		result.api_gap_notifications += release_in_gap<Access>(true);
		result.fallback_gap_notifications += release_in_gap<Access>(false);
		result.forced_gap_cases += 2;
	}
	assert(result.api_gap_notifications == expected_api_gaps);
	assert(result.fallback_gap_notifications == 0);
	cancellation<Access>(true);
	cancellation<Access>(false);
	result.cancellation_cases = 4;
	concurrency<Access>(result);
	return result;
}

int main()
{
	const auto before = run_suite<baseline::access>(16);
	const auto after = run_suite<candidate::access>(0);
	assert(host_budget_signals.load() > 0);
	std::printf("{\"passed\":true,\"assertionsActive\":true,"
		"\"forcedGapCasesPerVersion\":%u,\"baselineLostNotifications\":%u,\"candidateLostNotifications\":%u,"
		"\"fallbackLostNotifications\":[%u,%u],\"cancellationCasesPerVersion\":%u,"
		"\"concurrentAdmissionsPerVersion\":%u,\"maximumConcurrentWork\":[%u,%u],"
		"\"admissionLimit\":3,\"productionTimeoutMilliseconds\":20,\"timingThresholdAssertions\":false}\n",
		before.forced_gap_cases, before.api_gap_notifications, after.api_gap_notifications,
		before.fallback_gap_notifications, after.fallback_gap_notifications, before.cancellation_cases,
		before.concurrent_admissions, before.max_concurrent_work, after.max_concurrent_work);
}
