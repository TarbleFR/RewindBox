// REWINDBOX_FAST_JIT_LOAD_634, REWINDBOX_JIT_OBJECT_RELEASE_634: the real code around the LLVM calls,
// extracted from the Core by test/rpcs3_core634_test.py: the window of validated objects and the
// bytes held until finalizeObject (Utilities/JITLLVM.cpp), the workers and the three parallel
// blocks of ppu_initialize (PPUThread.cpp), on mock engines.
#include "ios/IOSJitLoad.h"

#include <array>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <functional>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>
#include <string_view>
#include <thread>
#include <unordered_map>
#include <utility>
#include <vector>

using u32 = std::uint32_t;
using u64 = std::uint64_t;
using usz = std::size_t;

static int failures = 0;
#define CHECK(x) do { if (!(x)) { std::printf("check failed line %d: %s\n", __LINE__, #x); failures++; } } while (0)

namespace llvm
{
	struct MemoryBuffer
	{
		inline static std::atomic<long> alive{0};
		std::size_t bytes;
		explicit MemoryBuffer(std::size_t size) : bytes(size) { alive++; }
		~MemoryBuffer() { alive--; }
		std::size_t getBufferSize() const { return bytes; }
	};
}

static std::atomic<unsigned> g_checks{0};
static std::string g_missing;

struct jit_compiler
{
	static bool check(const std::string& path)
	{
		g_checks++;
		return path != g_missing;
	}
};

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

// An LLVM fatal error: the thread ends here, the others go on, join() reports it.
struct thread_death {};

template <typename F>
class named_thread_group
{
	std::vector<std::thread> threads;
	std::atomic<bool> died{false};
public:
	named_thread_group(std::string_view, u32 count, F&& function)
	{
		for (u32 i = 0; i < count; i++)
		{
			threads.emplace_back([this, function]() mutable
			{
				try { function(); }
				catch (const thread_death&) { died = true; }
			});
		}
	}
	bool join()
	{
		for (auto& thread : threads)
		{
			if (thread.joinable()) thread.join();
		}
		return !died;
	}
	~named_thread_group() { join(); }
};

namespace fmt
{
template <typename... Args>
[[noreturn]] void throw_exception(const char* format, const Args&...)
{
	throw std::runtime_error(format);
}
}

namespace jit_phase
{
enum phase { ppu_finalize };
struct scope { scope(phase, u64 (*)()) {} };
}

namespace utils { inline u64 get_tsc() { return 0; } }

namespace rpcs3::ios
{
static std::atomic<unsigned> g_recorded{0};
inline void record_ppu_cache_lookup(bool) { g_recorded++; }
namespace boot_diagnostics
{
struct counters_mock
{
	std::atomic<u64> objects_loaded{0};
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

static struct
{
	template <typename... Args> void notice(const char*, const Args&...) {}
	template <typename... Args> void error(const char*, const Args&...) {}
	template <typename... Args> void success(const char*, const Args&...) {}
} ppu_log;

static atomic_t<u32> g_progr_pdone = 0;
static std::string g_fail;
static std::atomic<unsigned> g_stop_after{0};
static std::atomic<unsigned> g_adds{0};

struct mock_engine
{
	std::atomic<int> users{0};
	std::vector<std::string> added;
	std::atomic<int> finished{0};

	bool add(const std::string& path)
	{
		CHECK(users.fetch_add(1) == 0); // one thread per engine at a time
		added.push_back(path);
		users--;
		if (const unsigned stop = g_stop_after.load(); ++g_adds == stop) Emu.stopped = true;
		return path != g_fail;
	}

	void fin()
	{
		CHECK(users.fetch_add(1) == 0);
		finished++;
		users--;
	}
};

using engines = std::vector<std::shared_ptr<mock_engine>>;
using workload = std::vector<std::pair<std::string, bool>>;

namespace
{
#include "jit_window.inc"
#include "jit_held.inc"
#include "ppu_link_jobs.inc"

constexpr u32 c_modules_per_jit = 25;

bool run_link(engines& jits, const workload& link_workload, usz increment_link_count_at, ppu_mock* cpu)
{
	const std::string cache_path = "c/";
	bool failed_to_load = false;
#include "ppu_link_block.inc"
	return failed_to_load;
}

void run_reloc(engines& jits)
{
#include "ppu_reloc_block.inc"
}

bool run_check(const std::vector<std::string>& ios_deferred_checks)
{
#include "ppu_check_block.inc"
}

engines make_engines(usz modules)
{
	engines jits((modules + c_modules_per_jit - 1) / c_modules_per_jit);
	for (auto& jit : jits) jit = std::make_shared<mock_engine>();
	return jits;
}

workload make_workload(usz modules)
{
	workload out;
	for (usz i = 0; i < modules; i++) out.emplace_back("m" + std::to_string(i), i % 3 == 0);
	return out;
}

void reset_link()
{
	g_progr_pdone = 0;
	g_fail.clear();
	g_stop_after = 0;
	g_adds = 0;
	Emu.stopped = false;
	rpcs3::ios::boot_diagnostics::g_counters.objects_loaded = 0;
}
}

namespace jl = rpcs3::ios::jit_load;

static std::unique_ptr<llvm::MemoryBuffer> buffer(std::size_t size)
{
	return std::make_unique<llvm::MemoryBuffer>(size);
}

static object_file_identity identity(unsigned index)
{
	object_file_identity result;
	result.path = "object" + std::to_string(index);
	result.inode = index + 1;
	result.valid = true;
	return result;
}

int main()
{
	// The window follows the memory headroom, within its bounds.
	CHECK(jl::window_bytes(0) == 32ull << 20);
	CHECK(jl::window_bytes(256ull << 20) == 32ull << 20);
	CHECK(jl::window_bytes(800ull << 20) == 100ull << 20);
	CHECK(jl::window_bytes(4096ull << 20) == 256ull << 20);

	{ // what fits stays for the link, what does not stays known as checked, without its bytes
		validated_object_window window;
		const std::size_t object = 8 << 20;
		jl::window_limit = 32 << 20;
		for (unsigned i = 0; i < 8; i++) window.remember(std::to_string(i), identity(i), buffer(object));
		unsigned kept = 0, known = 0;
		for (unsigned i = 0; i < 8; i++)
		{
			known += window.checked(std::to_string(i), identity(i));
			kept += window.take(std::to_string(i), identity(i)) != nullptr;
		}
		CHECK(known == 8 && kept == 4 && window.bytes == 0);

		jl::window_limit = 256 << 20;
		for (unsigned i = 0; i < 8; i++) window.remember(std::to_string(i), identity(i), buffer(object));
		kept = 0;
		for (unsigned i = 0; i < 8; i++) kept += window.take(std::to_string(i), identity(i)) != nullptr;
		CHECK(kept == 8 && window.bytes == 0);

		// The limit drops below what is held (the next boot, less headroom): nothing underflows.
		for (unsigned i = 0; i < 8; i++) window.remember(std::to_string(i), identity(i), buffer(object));
		jl::window_limit = 16 << 20;
		window.remember("late", identity(99), buffer(1));
		CHECK(window.take("late", identity(99)) == nullptr);
		CHECK(window.take("0", identity(1)) == nullptr); // another file under the same path
		jl::window_limit = jl::minimum_window_bytes;
	}
	CHECK(llvm::MemoryBuffer::alive == 0);

	{ // bytes live until their engine is finalized or destroyed, one engine does not free another's
		held_object_bytes held;
		jit_compiler first, second;
		held.hold(&first, buffer(10));
		held.hold(&first, buffer(20));
		held.hold(&second, buffer(30));
		CHECK(llvm::MemoryBuffer::alive == 3);
		held.release(&first);
		CHECK(llvm::MemoryBuffer::alive == 1);
		held.release(&first);
		CHECK(llvm::MemoryBuffer::alive == 1);
		held.release(&second);
		CHECK(llvm::MemoryBuffer::alive == 0 && held.owners.empty());
	}
	{ // the engines of the link workers, at the same time
		held_object_bytes held;
		std::vector<jit_compiler> engines(8);
		std::vector<std::thread> workers;
		for (auto& engine : engines)
		{
			workers.emplace_back([&held, &engine]()
			{
				for (unsigned round = 0; round < 200; round++)
				{
					for (unsigned i = 0; i < 5; i++) held.hold(&engine, buffer(i));
					held.release(&engine);
				}
			});
		}
		for (auto& worker : workers) worker.join();
		CHECK(llvm::MemoryBuffer::alive == 0 && held.owners.empty());
	}

	// Every job once; no thread for one job; no underflow for none; at most four threads at a time.
	CHECK(jl::link_workers == 4);
	for (const usz count : {usz{0}, usz{1}, usz{2}, usz{3}, usz{4}, usz{5}, usz{25}, usz{175}})
	{
		std::vector<std::atomic<unsigned>> runs(count);
		std::atomic<unsigned> running{0}, peak{0};
		std::vector<std::thread::id> ids(count);
		ios_run_link_jobs("test ", count, [&](usz index)
		{
			const unsigned now = ++running;
			unsigned seen = peak.load();
			while (now > seen && !peak.compare_exchange_weak(seen, now)) {}
			ids[index] = std::this_thread::get_id();
			runs[index]++;
			std::this_thread::sleep_for(std::chrono::microseconds(200));
			running--;
		});
		unsigned once = 0, here = 0;
		for (auto& run : runs) once += run.load() == 1;
		for (const auto& id : ids) here += id == std::this_thread::get_id();
		CHECK(once == count && peak.load() <= jl::link_workers);
		// One job stays here. With several, this thread only waits: the workers use its stack.
		CHECK(here == (count == 1 ? 1u : 0u));
	}

	{ // a worker ended by a fatal error: the others finish, then this thread ends too
		std::atomic<unsigned> ran{0};
		bool ended = false;
		try
		{
			ios_run_link_jobs("test ", 16, [&](usz index)
			{
				if (index == 3) throw thread_death{};
				ran++;
			});
		}
		catch (const std::runtime_error&)
		{
			ended = true;
		}
		CHECK(ended && ran.load() <= 15);
	}

	// The link block of ppu_initialize: engines, order, the count the progress dialog waits for.
	for (const usz modules : {usz{26}, usz{60}, usz{61}, usz{175}})
	{
		for (const usz every : {usz{1}, usz{20}})
		{
			usz expected = 0;
			for (usz i = 0; i < modules; i++) expected += i % every == (modules - 1) % every;
			CHECK(expected == (modules + every - 1) / every);

			reset_link();
			auto jits = make_engines(modules);
			CHECK(!run_link(jits, make_workload(modules), every, nullptr));
			CHECK(g_progr_pdone == expected && rpcs3::ios::boot_diagnostics::g_counters.objects_loaded == modules && g_adds == modules);
			for (usz engine = 0; engine < jits.size(); engine++)
			{
				const usz first = engine * c_modules_per_jit;
				CHECK(jits[engine]->added.size() == std::min<usz>(c_modules_per_jit, modules - first));
				for (usz i = 0; i < jits[engine]->added.size(); i++) CHECK(jits[engine]->added[i] == "c/m" + std::to_string(first + i));
			}

			run_reloc(jits);
			for (const auto& jit : jits) CHECK(jit->finished == 1);

			// A failed object: the boot goes on as it did on one thread, so the count still ends.
			reset_link();
			g_fail = "c/m" + std::to_string(modules / 2);
			auto failing = make_engines(modules);
			CHECK(run_link(failing, make_workload(modules), every, nullptr));
			CHECK(g_progr_pdone == expected);
			CHECK(rpcs3::ios::boot_diagnostics::g_counters.objects_loaded < modules);
			CHECK(failing[(modules / 2) / c_modules_per_jit]->added.back() == g_fail); // nothing after it
		}
	}

	{ // a stop during the link: no new object per engine, nothing waits for the rest
		reset_link();
		g_stop_after = 5;
		auto jits = make_engines(100);
		CHECK(!run_link(jits, make_workload(100), 1, nullptr));
		CHECK(g_adds.load() <= 5 + jl::link_workers - 1);

		reset_link();
		ppu_mock thread;
		thread.state.exiting = true;
		auto others = make_engines(100);
		CHECK(!run_link(others, make_workload(100), 1, &thread) && g_adds == 0);
		reset_link();
	}

	{ // the check pass: every object, one answer, each lookup recorded once
		std::vector<std::string> paths;
		for (unsigned i = 0; i < 100; i++) paths.push_back("o" + std::to_string(i));
		CHECK(!run_check(paths) && g_checks == 100 && rpcs3::ios::g_recorded == 100 && rpcs3::ios::boot_diagnostics::g_counters.lookups == 100);
		g_missing = "o57";
		CHECK(run_check(paths) && g_checks == 200);
		CHECK(!run_check({}));
	}

	std::printf("{\"failures\": %d}\n", failures);
	return failures != 0;
}
