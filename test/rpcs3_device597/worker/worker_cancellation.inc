// New worker integration cases only. The generator prefixes the existing VM
// adapter and includes exact source bodies. No old prehash test is executed.
#ifdef NDEBUG
#error Assertions must remain enabled
#endif
#include <string>
#include "ios/IOSTextureHash.h"
#include "ios/IOSTextureValidationProfile.h"
#include "ios/IOSTexturePrehash.h"
#include "ios/IOSThreadQoS.h"

namespace rpcs3::ios
{
struct test_policy { bool texture_hash_hybrid = true; };
inline test_policy test_policy_value{};
inline const test_policy& get_experimental_policy() noexcept { return test_policy_value; }
}

namespace worker_test
{
constexpr usz prefix_bytes = 64u << 10;
struct observation_gate
{
	std::mutex mutex;
	std::condition_variable wakeup;
	bool armed = false, paused = false, released = false;
	usz processed = 0;

	void arm()
	{
		std::lock_guard lock(mutex);
		armed = true; paused = false; released = false; processed = 0;
	}
	void await_pause()
	{
		std::unique_lock lock(mutex);
		ensure(wakeup.wait_for(lock, std::chrono::seconds(5), [&] { return paused; }));
		ensure(processed == prefix_bytes);
	}
	void release()
	{
		std::lock_guard lock(mutex);
		armed = false; released = true;
		wakeup.notify_all();
	}
};
inline observation_gate gate;

bool observe_current(const rpcs3::ios::texture_hash_cancellation& cancellation, usz processed) noexcept
{
	{
		std::unique_lock lock(gate.mutex);
		if (gate.armed && !gate.paused && processed == prefix_bytes)
		{
			gate.paused = true;
			gate.processed = processed;
			gate.wakeup.notify_all();
			gate.wakeup.wait(lock, [&] { return gate.released; });
		}
	}
	return cancellation.current();
}
}

#include "ios/IOSTextureHash.observed.cpp"
#include "worker_body.inc"

namespace tv = rpcs3::ios::texture_validation;
namespace tp = rpcs3::ios::texture_prehash;
namespace wt = worker_test;

namespace
{
constexpr u32 length = 1u << 20;
constexpr u64 untouched = 0x72d20e44a5f91893ull;
constexpr usz reservation_size = rsx::constants::local_mem_base + (16u << 20);
struct result
{
	const char* name;
	u64 prefix, completed, skips;
	bool range_released, unmap_completed, output_untouched;
};
std::vector<result> results;

template <typename Predicate>
void await(Predicate&& predicate)
{
	const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(5);
	while (!predicate())
	{
		ensure(std::chrono::steady_clock::now() < deadline);
		std::this_thread::yield();
	}
}

bool no_active_ranges()
{
	for (auto& slot : vm::g_range_lock_set)
		if (slot.load()) return false;
	return true;
}

void reset(bool hybrid = true)
{
	tp::stop();
	ensure(vm::g_range_lock_bits[0].load() == 0);
	ensure(vm::g_range_lock_bits[1].load() == 0);
	ensure(no_active_ranges());
	for (auto& slot : tp::table)
	{
		slot.seq.store(0); slot.key.store(0); slot.epoch.store(0); slot.hash.store(0);
	}
	tp::worker_bytes.store(0); tp::worker_ticks.store(0);
	tp::worker_hashes.store(0); tp::worker_skips.store(0);
	jit_memory::texture_hash_bytes.store(0); jit_memory::texture_hash_ticks.store(0);
	vm::unmaps.store(0); vm::remaps.store(0);
	rpcs3::ios::test_policy_value.texture_hash_hybrid = hybrid;
	tv::epoch_enabled.store(true);
	tv::advance_epoch();
	tp::enabled.store(true);
}

void predict_one(u32 start)
{
	// The first recorded frame establishes the real worker's frame epoch.
	// The next frame records the sole eligible prediction at ordinal zero.
	tp::record(start, length, false);
	tp::end_frame();
	tp::record(start, length, true);
	tp::end_frame();
}

void require_no_publication(u32 start)
{
	const auto& slot = tp::table[tp::slot_of(tp::make_key(start, length))];
	ensure(slot.seq.load() == 0);
	ensure(slot.key.load() == 0);
}

void helper_entry_guards()
{
	reset();
	auto* slot = vm::alloc_range_lock();
	const auto epoch = tv::current_epoch();
	u64 hash = untouched;
	usz processed = 123;
	const rpcs3::ios::texture_hash_cancellation guard{
		tv::validation_epoch, tp::g_position, tp::enabled, epoch, 0};
	tp::enabled.store(false);
	ensure(!tp::hash_guest_range(slot, vm::main_base, length, guard, hash, processed));
	ensure(hash == untouched && processed == 0 && slot->load() == 0);
	tp::enabled.store(true);
	tp::g_position.store(1);
	ensure(!tp::hash_guest_range(slot, vm::main_base, length, guard, hash, processed));
	ensure(hash == untouched && processed == 0 && slot->load() == 0);
	tp::g_position.store(0);
	vm::g_range_lock_bits[1].store(~u64{0});
	ensure(!tp::hash_guest_range(slot, vm::main_base, length, guard, hash, processed));
	ensure(hash == untouched && processed == 0 && slot->load() == 0);
	vm::g_range_lock_bits[1].store(0);
	ensure(!tp::hash_guest_range(nullptr, vm::main_base, length, guard, hash, processed));
	ensure(hash == untouched && processed == 0);
	tv::advance_epoch();
	ensure(!tp::hash_guest_range(slot, vm::main_base, length, guard, hash, processed));
	ensure(hash == untouched && processed == 0 && slot->load() == 0);
	ensure(jit_memory::texture_hash_bytes.load() == 0);
	vm::free_range_lock(slot);
	results.push_back({"helper_entry_guards_5", 0, 0, 0, true, false, true});
}

void helper_cancel()
{
	reset();
	auto* slot = vm::alloc_range_lock();
	u64 hash = untouched;
	usz processed = 0;
	bool complete = true;
	const auto epoch = tv::current_epoch();
	const rpcs3::ios::texture_hash_cancellation guard{
		tv::validation_epoch, tp::g_position, tp::enabled, epoch, 0};
	wt::gate.arm();
	std::thread reader([&] {
		complete = tp::hash_guest_range(slot, vm::main_base, length, guard, hash, processed);
	});
	wt::gate.await_pause();
	ensure(slot->load() != 0);
	tv::advance_epoch();
	wt::gate.release();
	reader.join();
	ensure(!complete);
	ensure(hash == untouched && processed == wt::prefix_bytes);
	ensure(slot->load() == 0);
	ensure(jit_memory::texture_hash_bytes.load() == wt::prefix_bytes);
	vm::free_range_lock(slot);
	results.push_back({"helper_cancel", processed, 0, 1, true, false, true});
}

void helper_complete(bool local, bool hybrid)
{
	reset(hybrid);
	auto* slot = vm::alloc_range_lock();
	const u32 start = local ? rsx::constants::local_mem_base : vm::main_base;
	constexpr u32 test_length = length + 33;
	const auto epoch = tv::current_epoch();
	const rpcs3::ios::texture_hash_cancellation guard{
		tv::validation_epoch, tp::g_position, tp::enabled, epoch, 0};
	u64 hash = untouched;
	usz processed = 0;
	ensure(tp::hash_guest_range(slot, start, test_length, guard, hash, processed));
	ensure(hash == XXH3_64bits_withSeed(vm::g_sudo_addr + start, test_length, rpcs3::fnv_seed));
	ensure(processed == test_length && slot->load() == 0);
	vm::free_range_lock(slot);
	results.push_back({local ? (hybrid ? "helper_complete_local" : "helper_fallback_local")
		: (hybrid ? "helper_complete_main" : "helper_fallback_main"), processed, 1, 0, true, false, false});
}

enum class event { epoch, position, disabled, stop };

void worker_cancel(const char* name, event cause, bool local, bool unmap)
{
	reset();
	const u32 start = local ? rsx::constants::local_mem_base : vm::main_base;
	wt::gate.arm();
	predict_one(start);
	wt::gate.await_pause();
	ensure(vm::g_range_lock_bits[0].load() != 0);
	ensure(local ? no_active_ranges() : !no_active_ranges());
	require_no_publication(start);
	std::thread unmapper;
	std::vector<u8> replacement;
	if (unmap)
	{
		ensure(!local);
		replacement.assign(length, 0x73);
		unmapper = std::thread([&] { vm::unmap_and_remap(start, length, replacement); });
		await([&] { return vm::g_range_lock_bits[1].load() != 0; });
		ensure(vm::unmaps.load() == 0 && !no_active_ranges());
	}
	std::thread stopper;
	switch (cause)
	{
	case event::epoch:
		tv::advance_epoch();
		// Actual empty frame transition prevents a second, current-epoch batch.
		// It keeps position zero and leaves the captured batch unchanged.
		tp::end_frame();
		break;
	case event::position:
		tp::record(start, length, true);
		ensure(tp::g_position.load() == 1);
		break;
	case event::disabled:
		tp::enabled.store(false);
		break;
	case event::stop:
		stopper = std::thread([] { tp::stop(); });
		await([] { return !tp::enabled.load(); });
		break;
	}
	wt::gate.release();
	await([] { return tp::worker_skips.load() + tp::worker_hashes.load() >= 1; });
	if (stopper.joinable()) stopper.join();
	else tp::stop();
	if (unmapper.joinable()) unmapper.join();
	ensure(tp::worker_hashes.load() == 0);
	ensure(tp::worker_skips.load() == 1);
	ensure(tp::worker_bytes.load() == wt::prefix_bytes);
	ensure(jit_memory::texture_hash_bytes.load() == wt::prefix_bytes);
	ensure(tp::worker_ticks.load() > 0 && jit_memory::texture_hash_ticks.load() > 0);
	require_no_publication(start);
	ensure(no_active_ranges() && vm::g_range_lock_bits[0].load() == 0);
	ensure(vm::g_range_lock_bits[1].load() == 0);
	ensure(!tp::g_started && tp::g_worker == nullptr);
	if (unmap)
	{
		ensure(vm::unmaps.load() == 1 && vm::remaps.load() == 1);
		ensure(std::memcmp(vm::g_sudo_addr + start, replacement.data(), length) == 0);
	}
	results.push_back({name, tp::worker_bytes.load(), tp::worker_hashes.load(),
		tp::worker_skips.load(), true, unmap, true});
}

void worker_complete(bool local, bool hybrid)
{
	reset(hybrid);
	const u32 start = local ? rsx::constants::local_mem_base : vm::main_base;
	const auto epoch = tv::current_epoch();
	const auto reference = XXH3_64bits_withSeed(vm::g_sudo_addr + start, length, rpcs3::fnv_seed);
	predict_one(start);
	await([] { return tp::worker_hashes.load() == 1; });
	tp::stop();
	u64 actual = untouched;
	ensure(tp::lookup(start, length, epoch, actual));
	ensure(actual == reference);
	ensure(tp::worker_skips.load() == 0 && tp::worker_bytes.load() == length);
	ensure(no_active_ranges() && vm::g_range_lock_bits[0].load() == 0);
	results.push_back({local ? "worker_complete_local" : (hybrid ? "worker_complete_main" : "worker_fallback_main"),
		tp::worker_bytes.load(), 1, 0, true, false, false});
}
}

int main(int argc, char** argv)
{
	const std::string selected = argc > 1 ? argv[1] : "all";
	vm::g_sudo_addr = static_cast<u8*>(mmap(nullptr, reservation_size, PROT_NONE,
		MAP_PRIVATE | MAP_ANONYMOUS, -1, 0));
	ensure(vm::g_sudo_addr != MAP_FAILED);
	ensure(mprotect(vm::g_sudo_addr + vm::main_base, vm::main_size, PROT_READ | PROT_WRITE) == 0);
	ensure(mprotect(vm::g_sudo_addr + rsx::constants::local_mem_base, 16u << 20, PROT_READ | PROT_WRITE) == 0);
	for (u32 i = 0; i < vm::main_size; ++i)
		vm::g_sudo_addr[vm::main_base + i] = static_cast<u8>((i * 73u) ^ (i >> 11));
	for (u32 i = 0; i < (16u << 20); ++i)
		vm::g_sudo_addr[rsx::constants::local_mem_base + i] = static_cast<u8>((i * 31u) ^ (i >> 8));
	for (auto& page : vm::g_main_pages) page.store(vm::page_readable | vm::page_writable);
	if (selected == "all")
	{
		helper_entry_guards();
		helper_cancel();
		helper_complete(false, true); helper_complete(true, true);
		helper_complete(false, false); helper_complete(true, false);
		worker_cancel("epoch_main", event::epoch, false, false);
		worker_cancel("epoch_local", event::epoch, true, false);
		worker_cancel("position_main", event::position, false, false);
		worker_cancel("position_local", event::position, true, false);
		worker_cancel("disabled_main", event::disabled, false, false);
		worker_cancel("disabled_local", event::disabled, true, false);
		worker_cancel("stop_main", event::stop, false, false);
		worker_cancel("stop_local", event::stop, true, false);
		worker_cancel("epoch_unmap", event::epoch, false, true);
		worker_cancel("stop_unmap", event::stop, false, true);
		worker_complete(false, true); worker_complete(true, true);
		worker_complete(false, false);
	}
	else if (selected == "helper_cancel") helper_cancel();
	else if (selected == "epoch_main") worker_cancel("epoch_main", event::epoch, false, false);
	else ensure(false);
	tp::stop();
	ensure(munmap(vm::g_sudo_addr, reservation_size) == 0);
	vm::g_sudo_addr = nullptr;
	std::printf("{\"passed\":true,\"caseCount\":%zu,\"cases\":[", results.size());
	for (usz i = 0; i < results.size(); ++i)
	{
		const auto& r = results[i];
		std::printf("%s{\"name\":\"%s\",\"processedBytes\":%llu,\"completed\":%llu,\"skips\":%llu,"
			"\"rangeReleased\":%s,\"unmapCompleted\":%s,\"outputOrTableUnchanged\":%s}", i ? "," : "",
			r.name, static_cast<unsigned long long>(r.prefix), static_cast<unsigned long long>(r.completed),
			static_cast<unsigned long long>(r.skips), r.range_released ? "true" : "false",
			r.unmap_completed ? "true" : "false", r.output_untouched ? "true" : "false");
	}
	std::printf("]}\n");
	return 0;
}
