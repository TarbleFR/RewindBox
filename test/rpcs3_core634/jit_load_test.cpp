// REWINDBOX_FAST_JIT_LOAD_634, REWINDBOX_JIT_OBJECT_RELEASE_634: the real code around the LLVM calls,
// extracted from the Core by test/rpcs3_core634_test.py: the window of validated objects and the
// bytes held until finalizeObject (Utilities/JITLLVM.cpp), the link workers (PPUThread.cpp).
#include "ios/IOSJitLoad.h"

#include <array>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <functional>
#include <memory>
#include <mutex>
#include <string>
#include <string_view>
#include <thread>
#include <unordered_map>
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

struct jit_compiler {};

template <typename T>
struct atomic_t
{
	std::atomic<T> value;
	atomic_t(T initial) : value(initial) {}
	T operator++(int) { return value.fetch_add(1); }
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
	~named_thread_group() { for (auto& thread : threads) thread.join(); }
};

namespace
{
#include "jit_window.inc"
#include "jit_held.inc"
#include "ppu_link_jobs.inc"
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
		unsigned once = 0;
		for (auto& run : runs) once += run.load() == 1;
		CHECK(once == count && peak.load() <= jl::link_workers);
		if (count == 1) CHECK(ids[0] == std::this_thread::get_id());
	}

	std::printf("{\"failures\": %d}\n", failures);
	return failures != 0;
}
