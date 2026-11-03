// REWINDBOX_PPU_CHECK_STOP_636: the real check pass of ppu_initialize (PPUThread.cpp: ios_run_link_jobs and the
// check_only block, extracted by test/rpcs3_core636_test.py) on mock object checks. The serial walk returns at its
// first missing object and stops with the emulator; the parallel pass of Core 634 kept issuing every remaining check
// after a miss or a stop. Cases: a fully warm cache (every object checked once, nothing missing), an early miss (no
// check starts after it), the emulator stopping, the PPU thread exiting, and a warm pass again afterwards.
#include "ios/IOSJitLoad.h"

#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <stdexcept>
#include <string>
#include <string_view>
#include <thread>
#include <utility>
#include <vector>

using u32 = std::uint32_t;
using u64 = std::uint64_t;
using usz = std::size_t;

static int failures = 0;
#define CHECK(x) do { if (!(x)) { std::printf("check failed line %d: %s\n", __LINE__, #x); failures++; } } while (0)

template <typename T>
struct atomic_t
{
	std::atomic<T> value;
	atomic_t(T initial) : value(initial) {}
	T operator++(int) { return value.fetch_add(1); }
	T operator=(T other) { value = other; return other; }
	T operator+=(T other) { return value.fetch_add(other) + other; }
	operator T() const { return value.load(); }
};

template <typename F>
class named_thread_group
{
	std::vector<std::thread> threads;
public:
	named_thread_group(std::string_view, u32 count, F&& function)
	{
		for (u32 i = 0; i < count; i++) threads.emplace_back(function);
	}
	bool join()
	{
		for (auto& thread : threads)
			if (thread.joinable()) thread.join();
		return true;
	}
	~named_thread_group() { join(); }
};

namespace fmt
{
template <typename... Args>
[[noreturn]] void throw_exception(const char* format, const Args&...) { throw std::runtime_error(format); }
}

namespace rpcs3::ios
{
static std::atomic<unsigned> g_recorded{0};
inline void record_ppu_cache_lookup(bool) { g_recorded++; }
namespace boot_diagnostics
{
struct counters_mock
{
	std::atomic<unsigned> lookups{0};
	void note_cache_lookup(bool) { lookups++; }
};
static counters_mock g_counters;
}
}

enum class cpu_flag { exit };

struct ppu_mock
{
	struct state_mock
	{
		std::atomic<bool> exiting{false};
		bool all_of(cpu_flag) const { return exiting; }
	} state;
};

static struct { std::atomic<bool> stopped{false}; bool IsStopped() const { return stopped; } } Emu;

static std::atomic<unsigned> g_checks{0};
static std::string g_missing;
static std::atomic<unsigned> g_stop_after{0};
static ppu_mock* g_exit_thread = nullptr;

// One LLVM object check: a hit costs about a millisecond, a miss is found at once.
struct jit_compiler
{
	static bool check(const std::string& path)
	{
		const unsigned count = ++g_checks;
		if (const unsigned stop = g_stop_after.load(); stop && count == stop)
		{
			if (g_exit_thread) g_exit_thread->state.exiting = true;
			else Emu.stopped = true;
		}
		if (path == g_missing) return false;
		std::this_thread::sleep_for(std::chrono::milliseconds(1));
		return true;
	}
};

namespace
{
#include "ppu_link_jobs.inc"

bool run_check(const std::vector<std::string>& ios_deferred_checks, ppu_mock* cpu)
{
	(void)cpu;
#include "ppu_check_block.inc"
}
}

static void reset()
{
	g_checks = 0;
	g_missing.clear();
	g_stop_after = 0;
	g_exit_thread = nullptr;
	Emu.stopped = false;
	rpcs3::ios::g_recorded = 0;
	rpcs3::ios::boot_diagnostics::g_counters.lookups = 0;
}

int main()
{
	std::vector<std::string> paths;
	for (unsigned i = 0; i < 100; i++) paths.push_back("o" + std::to_string(i));
	const unsigned workers = rpcs3::ios::jit_load::link_workers;
	unsigned warm = 0, miss = 0, stopped = 0, exited = 0;

	{ // a fully warm cache: every object once, nothing missing, every lookup recorded
		reset();
		CHECK(!run_check(paths, nullptr));
		CHECK(g_checks == 100 && rpcs3::ios::g_recorded == 100 && rpcs3::ios::boot_diagnostics::g_counters.lookups == 100);
		warm = g_checks;
	}

	{ // an early miss answers the pass: only the checks already running when it was found end
		reset();
		g_missing = "o1";
		CHECK(run_check(paths, nullptr));
		miss = g_checks;
		CHECK(miss <= 2 + 2 * workers);
		CHECK(rpcs3::ios::g_recorded == miss);
	}

	{ // the emulator stops during the pass
		reset();
		g_stop_after = 3;
		CHECK(!run_check(paths, nullptr));
		stopped = g_checks;
		CHECK(stopped <= 3 + workers);
	}

	{ // the PPU thread that runs the pass exits
		reset();
		ppu_mock thread;
		g_exit_thread = &thread;
		g_stop_after = 3;
		CHECK(!run_check(paths, &thread));
		exited = g_checks;
		CHECK(exited <= 3 + workers);
	}

	{ // the warm cache again, after the stops: still every object, nothing missing
		reset();
		CHECK(!run_check(paths, nullptr) && g_checks == 100);
		CHECK(!run_check({}, nullptr) && g_checks == 100);
	}

	std::printf("{\"failures\": %d, \"warm\": %u, \"miss\": %u, \"stopped\": %u, \"exited\": %u, \"workers\": %u}\n",
	            failures, warm, miss, stopped, exited, workers);
	return failures != 0;
}
