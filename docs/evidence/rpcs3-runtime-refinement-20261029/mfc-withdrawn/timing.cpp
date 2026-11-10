#include <algorithm>
#include <array>
#include <chrono>
#include <cstdint>
#include <iostream>
#if defined(__aarch64__) || defined(__arm64__)
#define ARCH_ARM64 1
#elif defined(__x86_64__)
#define ARCH_X64 1
#else
#error Unsupported host timestamp architecture
#endif
using u16 = std::uint16_t;
using u32 = std::uint32_t;
using u64 = std::uint64_t;
struct { struct { u32 mfc_transfers_shuffling{}; } core; } g_cfg;
namespace utils {
inline u64 get_tsc()
	{
#if defined(ARCH_ARM64)
		u64 r = 0;
		__asm__ volatile("mrs %0, cntvct_el0" : "=r" (r));
		return r;
#elif defined(_M_X64)
		return __rdtsc();
#elif defined(ARCH_X64)
		return __builtin_ia32_rdtsc();
#else
#error "Missing utils::get_tsc() implementation"
#endif
	}
}
[[gnu::noinline]] u16 before_mask(u32 mfc_size) {
auto get_exec_mask = [&size = mfc_size]
	{
		// Get commands' execution mask
		const u32 shuffle_count = std::min<u32>(g_cfg.core.mfc_transfers_shuffling, size);
		if (!shuffle_count)
		{
			// All commands are enabled. Reading the host clock cannot affect
			// this mask, including an empty queue with shuffling enabled.
			return u16{0xffff};
		}

		return static_cast<u16>((0 - (1u << shuffle_count)) | utils::get_tsc());
	};
return get_exec_mask();
}
[[gnu::noinline]] u16 after_mask(u32 mfc_size) {
auto get_exec_mask = [&size = mfc_size]
	{
		// Get commands' execution mask
		const u32 shuffle_limit = g_cfg.core.mfc_transfers_shuffling;
		if (!shuffle_limit || !size)
		{
			// All commands are enabled. Reading the host clock cannot affect
			// this mask, including an empty queue with shuffling enabled.
			return u16{0xffff};
		}

		return static_cast<u16>((0 - (1u << std::min(shuffle_limit, size))) | utils::get_tsc());
	};
return get_exec_mask();
}

using Mask = u16(*)(u32);
u64 sink{};
double measure(Mask f, u32 size) {
    constexpr u32 iterations = 1000000;
    u64 sum = 0;
    const auto start = std::chrono::steady_clock::now();
    for (u32 i = 0; i != iterations; ++i) {
        // Equal compiler barriers prevent constant-hoisting of either helper.
        asm volatile("" : "+r"(size) : : "memory");
        sum += f(size);
    }
    const auto end = std::chrono::steady_clock::now();
    sink += sum;
    return std::chrono::duration<double, std::nano>(end - start).count() / iterations;
}
int main() {
    std::cout << "{\"iterationsPerSample\":1000000,\"samples\":7,\"cases\":[";
    bool first = true;
    for (const auto& [limit, size] : std::array<std::pair<u32,u32>,4>{{{0,16},{0,0},{1,16},{16,16}}}) {
        g_cfg.core.mfc_transfers_shuffling = limit;
        std::array<double,7> old{}, fresh{};
        for (u32 i = 0; i != 7; ++i) {
            if (i % 2) { fresh[i] = measure(after_mask, size); old[i] = measure(before_mask, size); }
            else { old[i] = measure(before_mask, size); fresh[i] = measure(after_mask, size); }
        }
        if (!first) std::cout << ',';
        first = false;
        std::cout << "{\"shuffle\":" << limit << ",\"queueSize\":" << size << ",\"baselineNs\":[";
        for (u32 i = 0; i != 7; ++i) { if (i) std::cout << ','; std::cout << old[i]; }
        std::cout << "],\"candidateNs\":[";
        for (u32 i = 0; i != 7; ++i) { if (i) std::cout << ','; std::cout << fresh[i]; }
        std::sort(old.begin(),old.end()); std::sort(fresh.begin(),fresh.end());
        std::cout << "],\"baselineMedianNs\":" << old[3] << ",\"candidateMedianNs\":" << fresh[3] << '}';
    }
    std::cout << "],\"sink\":" << sink << "}\n";
}
