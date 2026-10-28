// CELL581 texture pre-validation. The secret and texture_prehash blocks of
// texture_cache.cpp, and buffered_section::is_locked, protect, sync, discard
// and fast_hash_internal, are copied verbatim from the materialized Core (579
// preimage in namespace before, 581 source in namespace after). The real
// IOSTexturePrehash.h, IOSTextureValidationProfile.h, IOSThreadQoS.h,
// protection policy and XXH3 are used. Guest memory is a real address space
// reservation; RSX local and main memory are mapped in it. The vm range lock
// slots, exclusive bits and page flags follow vm.cpp; an unmapper thread runs
// the vm unmap protocol (exclusive bits, wait for the overlapping range locks,
// clear the page flags, PROT_NONE) on main memory while the worker reads it.
#include <algorithm>
#include <atomic>
#include <bit>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <thread>
#include <utility>
#include <vector>
#include <sys/mman.h>
#if defined(__APPLE__)
#include <pthread.h>
#include <pthread/qos.h>
#endif

using u8 = std::uint8_t;
using u16 = std::uint16_t;
using u32 = std::uint32_t;
using u64 = std::uint64_t;
using s32 = std::int32_t;
using usz = std::size_t;
struct umax_t
{
	template <typename T>
	constexpr operator T() const noexcept { return static_cast<T>(-1); }
};
inline constexpr umax_t umax{};
#define ensure(x) do { if (!(x)) { std::fprintf(stderr, "ensure failed: %s (line %d)\n", #x, __LINE__); std::abort(); } } while (0)
#define AUDIT(x) do { } while (0)
#define CELL581_REQUIRE(x) ensure(x)

template <typename T, usz Align = sizeof(T)>
struct alignas(Align) atomic_t
{
	std::atomic<T> m_data{};
	constexpr atomic_t() noexcept = default;
	T load() const noexcept { return m_data.load(); }
	void store(T value) noexcept { m_data.store(value); }
	void release(T value) noexcept { m_data.store(value, std::memory_order_release); }
	operator T() const noexcept { return load(); }
	T fetch_or(T value) noexcept { return m_data.fetch_or(value); }
	T fetch_and(T value) noexcept { return m_data.fetch_and(value); }
	bool compare_and_swap_test(T expected, T value) noexcept { return m_data.compare_exchange_strong(expected, value); }
};

namespace utils
{
	enum class protection { rw, ro, no };
	inline u64 get_tsc() noexcept
	{
		return static_cast<u64>(std::chrono::steady_clock::now().time_since_epoch().count());
	}
}

namespace rpcs3
{
	constexpr usz fnv_seed = 14695981039346656037ull;
}

// RSX local memory sits at 0xC0000000 in the guest; the copied code only compares
// against this constant, so the model places it lower to keep the reservation small
// for the sanitizers (main memory below it, as in the guest).
namespace rsx::constants
{
	constexpr u32 local_mem_base = 0x04000000;
}

// Guest memory: one reservation, RSX local memory and one main memory block mapped in it.
namespace vm
{
	enum page_info_t : u8 { page_readable = 1 << 0, page_writable = 1 << 1 };
	// vm_locking.h: flags in the top bits of a range lock's size.
	constexpr u64 range_readable = 2ull << 61;
	inline u8* g_sudo_addr = nullptr;
	inline atomic_t<u64, 128> g_range_lock_bits[2]{};
	inline atomic_t<u64, 128> g_range_lock_set[64]{};
	constexpr u32 main_base = 0x01000000;
	constexpr u32 main_size = 8u << 20;
	inline std::atomic<u8> g_main_pages[main_size / 4096]{};

	inline bool check_addr(u64 addr, u8 flags, u32 size)
	{
		if (addr >= rsx::constants::local_mem_base)
		{
			return true;
		}

		if (addr < main_base || addr + size > u64{main_base} + main_size)
		{
			return false;
		}

		for (u64 page = (addr - main_base) / 4096; page <= (addr + size - 1 - main_base) / 4096; page++)
		{
			if ((g_main_pages[page].load() & flags) != flags)
			{
				return false;
			}
		}

		return true;
	}

	inline atomic_t<u64, 128>* alloc_range_lock()
	{
		for (u32 i = 0; i < 63; i++)
		{
			if (!(g_range_lock_bits[0].fetch_or(1ull << i) & (1ull << i)))
			{
				return &g_range_lock_set[i];
			}
		}

		std::abort();
	}

	inline void free_range_lock(atomic_t<u64, 128>* range_lock) noexcept
	{
		range_lock->release(0);
		g_range_lock_bits[0].fetch_and(~(1ull << (range_lock - g_range_lock_set)));
	}

	// vm.cpp: the exclusive writer lock, then _page_unmap's main range lock, page flags and protection.
	inline std::atomic<u64> unmaps{0}, remaps{0};

	inline void unmap_and_remap(u32 addr, u32 size, const std::vector<u8>& image)
	{
		while (!g_range_lock_bits[1].compare_and_swap_test(0, ~u64{0}))
		{
			std::this_thread::yield();
		}

		for (bool busy = true; busy;)
		{
			busy = false;
			const u64 allocated = g_range_lock_bits[0].load();

			for (u32 i = 0; i < 63; i++)
			{
				if (!(allocated & (1ull << i)))
				{
					continue;
				}

				// As _lock_main_range_lock: the size half with its flag bits (a readable lock
				// reads as a range of 1 GiB and more, so an unmap waits for it).
				const u64 value = g_range_lock_set[i].load();
				const u32 start = static_cast<u32>(value), length = static_cast<u32>(value >> 32);

				if (length && start < u64{addr} + size && addr < u64{start} + length)
				{
					busy = true;
				}
			}
		}

		for (u32 page = (addr - main_base) / 4096; page < (addr + size - main_base) / 4096; page++)
		{
			g_main_pages[page].store(0);
		}

		ensure(mprotect(g_sudo_addr + addr, size, PROT_NONE) == 0);
		unmaps++;
		std::this_thread::sleep_for(std::chrono::microseconds(200));
		ensure(mprotect(g_sudo_addr + addr, size, PROT_READ | PROT_WRITE) == 0);
		std::memcpy(g_sudo_addr + addr, image.data(), size);

		for (u32 page = (addr - main_base) / 4096; page < (addr + size - main_base) / 4096; page++)
		{
			g_main_pages[page].store(page_readable | page_writable);
		}

		remaps++;
		g_range_lock_bits[1].store(0);
	}
}

#include "ios/IOSTextureValidationProfile.h"
#include "ios/IOSThreadQoS.h"
#include "Emu/RSX/Common/texture_cache_protection_policy.h"
@PREHASH_HEADER_INCLUDE@

namespace rpcs3::ios
{
	struct test_policy { bool texture_hash_hybrid = false; };
	inline const test_policy& get_experimental_policy() noexcept { static const test_policy policy{}; return policy; }
	std::uint64_t texture_hash_hybrid(const void*, std::size_t, const void*, std::size_t, std::uint64_t) noexcept { std::abort(); }
}

#define XXH_INLINE_ALL
#include "Utilities/xxhash3.h"

@SECRET_AND_PREHASH@

namespace tv = rpcs3::ios::texture_validation;
namespace tp = rpcs3::ios::texture_prehash;

namespace rsx
{
	struct address_range32
	{
		u32 start = 1, end = 0;
		static address_range32 start_length(u32 start, u32 length) { return {start, start + length - 1}; }
		u32 length() const { return end - start + 1; }
		bool valid() const { return start <= end; }
		void invalidate() { start = 1; end = 0; }
		bool is_page_range() const { return valid() && (start & 4095) == 0 && ((end + 1) & 4095) == 0; }
		bool inside(const address_range32& other) const { return start >= other.start && end <= other.end; }
		bool operator!=(const address_range32& other) const { return start != other.start || end != other.end; }
	};
	inline void memory_protect(const address_range32&, utils::protection) { std::abort(); }

#define CELL581_SECTION(PREHASH_FIELD, RESET_VALIDATION) \
	struct buffered_section \
	{ \
		address_range32 locked_range, cpu_range, confirmed_range; \
		utils::protection protection = utils::protection::rw; \
		section_protection_strategy protection_strat = section_protection_strategy::hash; \
		u64 mem_hash = 0; \
		mutable u64 validated_epoch = 0; \
		PREHASH_FIELD \
		bool locked = false; \
		explicit buffered_section(u32 start, u32 length) : locked_range(address_range32::start_length(start, length)), cpu_range(locked_range) {} \
		template <typename T = void> \
		T* get_ptr(u32 address) const { return reinterpret_cast<T*>(vm::g_sudo_addr + address); } \
		const address_range32& get_confirmed_range() const { return confirmed_range.valid() ? confirmed_range : cpu_range; } \
		u64 fast_hash_internal() const; \
		bool is_locked(bool actual_page_flags = false) const; \
		void protect(utils::protection new_prot, bool force = false); \
		bool sync() const; \
		void discard(); \
		RESET_VALIDATION \
	};

	namespace before
	{
		CELL581_SECTION(, @BEFORE_RESET_VALIDATION@)
		@BEFORE_FAST_HASH@
		@BEFORE_IS_LOCKED@
		@BEFORE_PROTECT@
		@BEFORE_SYNC@
		@BEFORE_DISCARD@
	}

	namespace after
	{
		CELL581_SECTION(mutable bool prehash_bypass = false;, @AFTER_RESET_VALIDATION@)
		@AFTER_FAST_HASH@
		@AFTER_IS_LOCKED@
		@AFTER_PROTECT@
		@AFTER_SYNC@
		@AFTER_DISCARD@
	}
}

namespace
{
	using section = rsx::after::buffered_section;

	struct texture
	{
		u32 start, length;
		section s;
		texture(u32 start_, u32 length_) : start(start_), length(length_), s(start_, length_) {}
	};

	void fill(u32 start, u32 length, u32 seed)
	{
		for (u32 i = 0; i < length; i += 4)
		{
			const u32 value = (i * 2654435761u) ^ seed;
			std::memcpy(vm::g_sudo_addr + start + i, &value, 4);
		}
	}

	void spin_for(std::chrono::microseconds duration)
	{
		const auto stop = std::chrono::steady_clock::now() + duration;
		while (std::chrono::steady_clock::now() < stop) {}
	}

	struct frame_report
	{
		u64 validations = 0, unchanged_ok = 0, changes_seen = 0, stale_accepted = 0, spurious_changes = 0;
		u64 hits = 0, misses = 0, hit_bytes = 0, worker_hashes = 0, worker_skips = 0;
	};

	// Frames of `epochs` epochs; each validates its own textures in a fixed order with
	// `work` of draw work after each. Between epochs, as the guest does before a PUT,
	// one texture is rewritten; every validation is checked against the memory itself.
	frame_report run_frames(std::vector<texture>& textures, int frames, int epochs, std::chrono::microseconds work, bool scoped_write)
	{
		frame_report report{};
		const u64 hits0 = tp::hits, misses0 = tp::misses, bytes0 = tp::hit_bytes, worker0 = tp::worker_hashes, skips0 = tp::worker_skips;
		u32 generation = 1;

		for (int frame = 0; frame < frames; frame++)
		{
			for (int epoch = 0; epoch < epochs; epoch++)
			{
				// The guest's write is complete before the commands that read it become visible.
				texture& changed = textures[(frame * epochs + epoch) % textures.size()];
				const bool rewrite = frame % 3 == 2;
				if (rewrite)
				{
					fill(changed.start, changed.length, ++generation * 7919u);
				}
				tv::advance_epoch();

				for (usz i = epoch; i < textures.size(); i += epochs)
				{
					texture& t = textures[i];

					if (scoped_write && frame > 1 && i == static_cast<usz>(epoch))
					{
						// CELL573_SCOPED_RSX_WRITES: the RSX writes a range inside the epoch,
						// after the worker may have hashed it, and revalidates its sections.
						spin_for(std::chrono::microseconds(300));
						fill(t.start, t.length, ++generation * 104729u);
						t.s.reset_validation();
					}

					// What the section holds against what memory holds now.
					const bool memory_unchanged = rpcs3::ios::texture_prehash::range_hash(vm::g_sudo_addr + t.start, t.length) == t.s.mem_hash;
					const bool valid = t.s.sync();
					report.validations++;

					if (memory_unchanged != valid)
					{
						(valid ? report.stale_accepted : report.spurious_changes)++;
					}
					else if (valid)
					{
						report.unchanged_ok++;
					}
					else
					{
						report.changes_seen++;
					}

					if (!valid)
					{
						// Upload again: a new section confirmed in this epoch.
						t.s.discard();
						t.s.protect(utils::protection::ro);
					}

					spin_for(work);
				}
			}

			tv::advance_epoch();
			tp::end_frame();
		}

		report.hits = tp::hits - hits0;
		report.misses = tp::misses - misses0;
		report.hit_bytes = tp::hit_bytes - bytes0;
		report.worker_hashes = tp::worker_hashes - worker0;
		report.worker_skips = tp::worker_skips - skips0;
		return report;
	}
}

int main(int argc, char** argv)
{
	// Sanitizers slow hashing far more than the modelled draw work: they pass a lower bound.
	const double min_hit_rate = argc > 1 ? std::atof(argv[1]) : 0.6;
	constexpr u64 reservation = u64{rsx::constants::local_mem_base} + (16u << 20);
	void* base = mmap(nullptr, reservation, PROT_NONE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_NORESERVE, -1, 0);
	ensure(base != MAP_FAILED);
	vm::g_sudo_addr = static_cast<u8*>(base);
	ensure(mprotect(vm::g_sudo_addr + rsx::constants::local_mem_base, 16u << 20, PROT_READ | PROT_WRITE) == 0);
	ensure(mprotect(vm::g_sudo_addr + vm::main_base, vm::main_size, PROT_READ | PROT_WRITE) == 0);
	for (auto& page : vm::g_main_pages) page.store(vm::page_readable | vm::page_writable);
	// Slots the emulator's SPU threads hold.
	for (int i = 0; i < 6; i++) vm::alloc_range_lock();

	// Textures: local memory (most) and main memory, 64 KiB to 1 MiB; one below min_bytes.
	std::vector<texture> textures;
	u32 local = rsx::constants::local_mem_base, main = vm::main_base;
	const u32 sizes[] = {1u << 20, 256u << 10, 512u << 10, 64u << 10, 768u << 10, 128u << 10, 16u << 10, 384u << 10};
	for (int i = 0; i < 24; i++)
	{
		const u32 size = sizes[i % 8];
		u32& cursor = (i % 4 == 3) ? main : local;
		textures.emplace_back(cursor, size);
		fill(cursor, size, 1000u + i);
		cursor += size + 4096;
	}
	ensure(main <= vm::main_base + vm::main_size);

	tv::epoch_enabled = true;

	// 1. Disabled: 581 validates exactly as 579, no worker, every validation hashed on the caller.
	tp::enabled = false;
	{
		std::vector<u8> scratch(64u << 10);
		rsx::before::buffered_section b(textures[0].start, textures[0].length);
		rsx::after::buffered_section a(textures[0].start, textures[0].length);
		b.protect(utils::protection::ro);
		a.protect(utils::protection::ro);
		CELL581_REQUIRE(a.mem_hash == b.mem_hash && a.validated_epoch == b.validated_epoch);
		for (int i = 0; i < 4; i++)
		{
			tv::advance_epoch();
			if (i == 2) vm::g_sudo_addr[textures[0].start + 17] ^= 0x5a;
			CELL581_REQUIRE(a.sync() == b.sync());
			CELL581_REQUIRE(a.validated_epoch == b.validated_epoch);
		}
		vm::g_sudo_addr[textures[0].start + 17] ^= 0x5a;
		CELL581_REQUIRE(tp::hits == 0 && tp::misses == 0 && tp::worker_hashes == 0);
	}

	for (auto& t : textures)
	{
		t.s.protect(utils::protection::ro);
	}

	// 2. Enabled: the worker's results serve the RSX validations; every change is seen.
	tp::enabled = true;
	std::atomic<bool> stop_unmapper{false};
	std::vector<u8> main_image(vm::main_size);
	std::memcpy(main_image.data(), vm::g_sudo_addr + vm::main_base, vm::main_size);
	const frame_report warm = run_frames(textures, 3, 4, std::chrono::microseconds(150), false);
	const frame_report steady = run_frames(textures, 12, 4, std::chrono::microseconds(150), false);
	const frame_report tight = run_frames(textures, 6, 4, std::chrono::microseconds(0), false);
	const frame_report scoped = run_frames(textures, 6, 4, std::chrono::microseconds(100), true);

	// 3. Main memory unmapped and mapped again while the worker reads it.
	std::memcpy(main_image.data(), vm::g_sudo_addr + vm::main_base, vm::main_size);
	std::thread unmapper([&]
	{
		while (!stop_unmapper.load())
		{
			vm::unmap_and_remap(vm::main_base, vm::main_size, main_image);
			std::this_thread::sleep_for(std::chrono::microseconds(300));
		}
	});
	// Only the ranges: the texture cache drops sections of memory before it is unmapped,
	// so here the worker alone reads main memory.
	std::vector<std::pair<u32, u32>> main_only;
	for (const auto& t : textures) if (t.start < rsx::constants::local_mem_base) main_only.emplace_back(t.start, t.length);
	frame_report unmapped{};
	const u64 race_hashes0 = tp::worker_hashes, race_skips0 = tp::worker_skips;
	{
		// The RSX thread validates main memory only while it is mapped (the texture cache
		// drops sections of unmapped memory first); the worker races the unmapper.
		// Until the worker has both read main memory between unmaps and skipped it while unmapped.
		for (int frame = 0; frame < 4000 && (vm::unmaps.load() < 8 || tp::worker_skips == race_skips0 || tp::worker_hashes == race_hashes0); frame++)
		{
			for (int epoch = 0; epoch < 2; epoch++)
			{
				tv::advance_epoch();
				// This frame's validations of main memory, which predict the next frame's.
				if (epoch == 0) for (const auto& [start, length] : main_only) tp::record(start, length);
				std::this_thread::sleep_for(std::chrono::microseconds(250));
			}
			tv::advance_epoch();
			tp::end_frame();
		}
		unmapped.worker_skips = tp::worker_skips - race_skips0;
		unmapped.worker_hashes = tp::worker_hashes - race_hashes0;
	}
	stop_unmapper = true;
	unmapper.join();

	tp::stop();
	CELL581_REQUIRE(vm::g_range_lock_bits[0].load() == 0x3f);
	// After the RSX thread: no validation starts a worker until the next boot resolves the lever.
	{
		const u64 hashes = tp::worker_hashes;
		CELL581_REQUIRE(!tp::enabled.load());
		tp::record(textures[0].start, textures[0].length);
		tv::advance_epoch();
		std::this_thread::sleep_for(std::chrono::milliseconds(10));
		CELL581_REQUIRE(tp::worker_hashes == hashes && vm::g_range_lock_bits[0].load() == 0x3f);
		tp::stop();
	}

	for (const frame_report* r : {&warm, &steady, &tight, &scoped})
	{
		CELL581_REQUIRE(r->stale_accepted == 0 && r->spurious_changes == 0);
	}
	CELL581_REQUIRE(steady.changes_seen > 0 && scoped.changes_seen > 0);
	const double steady_hit_rate = static_cast<double>(steady.hits) / static_cast<double>(steady.hits + steady.misses);
	CELL581_REQUIRE(steady_hit_rate >= min_hit_rate);
	// Main memory both read between unmaps and skipped while unmapped, never faulting.
	CELL581_REQUIRE(vm::unmaps.load() >= 8 && unmapped.worker_skips > 0 && unmapped.worker_hashes > 0);

	std::printf("{\"passed\":true,\"disabledIdenticalTo579\":true,\"textures\":%zu,\"steady\":{\"validations\":%llu,\"hits\":%llu,"
		"\"misses\":%llu,\"hitRate\":%.3f,\"changesSeen\":%llu,\"staleAccepted\":%llu,\"workerHashes\":%llu},"
		"\"tightLoop\":{\"hits\":%llu,\"misses\":%llu,\"staleAccepted\":%llu},"
		"\"scopedRsxWrites\":{\"hits\":%llu,\"misses\":%llu,\"changesSeen\":%llu,\"staleAccepted\":%llu},"
		"\"unmapRace\":{\"unmaps\":%llu,\"workerSkips\":%llu,\"workerHashes\":%llu},\"rangeLockReleased\":true,\"noRestartAfterStop\":true}\n",
		textures.size(),
		static_cast<unsigned long long>(steady.validations), static_cast<unsigned long long>(steady.hits),
		static_cast<unsigned long long>(steady.misses), steady_hit_rate,
		static_cast<unsigned long long>(steady.changes_seen), static_cast<unsigned long long>(steady.stale_accepted),
		static_cast<unsigned long long>(steady.worker_hashes),
		static_cast<unsigned long long>(tight.hits), static_cast<unsigned long long>(tight.misses),
		static_cast<unsigned long long>(tight.stale_accepted),
		static_cast<unsigned long long>(scoped.hits), static_cast<unsigned long long>(scoped.misses),
		static_cast<unsigned long long>(scoped.changes_seen), static_cast<unsigned long long>(scoped.stale_accepted),
		static_cast<unsigned long long>(vm::unmaps.load()), static_cast<unsigned long long>(unmapped.worker_skips),
		static_cast<unsigned long long>(unmapped.worker_hashes));
	munmap(base, reservation);
	return 0;
}
