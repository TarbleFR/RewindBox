// SPDX-License-Identifier: GPL-2.0-only
#pragma once

#include <array>
#include <atomic>
#include <cstddef>
#include <cstdint>

namespace rpcs3::ios::texture_validation
{
// Fixed 32-byte observations, outside all PPU/SPU code-generation inputs.
// Frame-end maintenance covers all validation sizes; its time overlaps the
// existing hash measurements, not an extra cost. No new per-hash observation.
inline std::atomic<std::uint64_t> trim_calls{0}, trim_sections{0};
inline std::atomic<std::uint64_t> trim_bytes{0}, trim_ticks{0};
// CELL559_DIRTY_HASH_SKIP: dirty hashed sections released without hashing.
inline std::atomic<std::uint64_t> dirty_releases{0}, dirty_release_bytes{0};

// CELL559_TEXTURE_EPOCH: "Texture Validation Per FIFO Batch". A clean section
// whose hash matched stays validated until the next synchronization point:
// new commands made visible by the guest (PUT), a semaphore acquire, an RSX
// write, flush or invalidation of guest memory, or the end of a frame. Guest
// data a command needs is written before that command becomes visible, or
// before the semaphore the RSX waits for is released; only an unsynchronized
// write racing the RSX can be seen one batch later. Disabled: epoch 0, every
// validation hashes as before.
inline std::atomic<bool> epoch_enabled{false};
inline std::atomic<std::uint64_t> validation_epoch{1};
inline std::atomic<std::uint64_t> epoch_skips{0}, epoch_skip_bytes{0}, epoch_bumps{0};

// A bound sampler must revisit the texture cache after a synchronization point,
// including when per-epoch hashing is disabled. This revision never validates
// bytes itself: buffered_section::sync() still performs the content check.
inline std::atomic<std::uint64_t> sampler_revision{1};

struct sampler_stamp
{
	std::uint64_t memory = 0;
	std::uint64_t range = 0;
};

// Owned by the texture cache, one slot per fragment/vertex sampler. Store guest
// ranges, never pointers to recyclable sections or Vulkan resources. Scoped
// writes only invalidate overlapping bindings; unknown layouts are conservative.
template <std::size_t Count>
class sampler_bindings
{
	struct binding
	{
		std::atomic<std::uint64_t> range{0};
		std::atomic<std::uint64_t> revision{1};
	};
	std::array<binding, Count> m_bindings{};
	static constexpr std::uint64_t unknown_range = ~std::uint64_t{0};

public:
	bool matches(std::size_t index, sampler_stamp stamp) const noexcept
	{
		return stamp.memory && stamp.memory == sampler_revision.load(std::memory_order_acquire) &&
			stamp.range == m_bindings[index].revision.load(std::memory_order_acquire);
	}

	// Called under the cache reader lock, before the lookup. A scoped writer
	// either finishes before this snapshot or sees the new range under its
	// exclusive lock. The lookup also takes that lock, so it cannot sample an
	// in-progress write whose notification has already been observed.
	void set_range(std::size_t index, std::uint32_t start, std::uint64_t length) noexcept
	{
		const std::uint64_t range = !length || length > 0xffffffffull || start + length > (1ull << 32)
			? unknown_range : start | (length << 32);
		m_bindings[index].range.store(range, std::memory_order_release);
	}

	sampler_stamp prepare(std::size_t index) noexcept
	{
		// Until the lookup has produced its actual source range, every scoped
		// write must be able to invalidate this in-flight binding.
		set_range(index, 0, 0);
		return {sampler_revision.load(std::memory_order_acquire), m_bindings[index].revision.load(std::memory_order_acquire)};
	}

	void forget(std::size_t index) noexcept
	{
		m_bindings[index].range.store(0, std::memory_order_release);
	}

	// Called under the cache exclusive lock, alongside reset_validation().
	void invalidate(std::uint32_t start, std::uint64_t length) noexcept
	{
		if (!length)
		{
			return;
		}
		const bool unknown_write = length > 0xffffffffull || start + length > (1ull << 32);
		for (auto& binding : m_bindings)
		{
			const std::uint64_t range = binding.range.load(std::memory_order_acquire);
			const std::uint64_t bound_start = static_cast<std::uint32_t>(range);
			const std::uint64_t bound_length = range >> 32;
			if (range && (unknown_write || range == unknown_range ||
				(start < bound_start + bound_length && bound_start < start + length)))
			{
				binding.revision.fetch_add(1, std::memory_order_acq_rel);
			}
		}
	}
};

inline std::uint64_t current_epoch() noexcept
{
	return epoch_enabled.load(std::memory_order_relaxed) ? validation_epoch.load(std::memory_order_acquire) : 0;
}

// CELL581_TEXTURE_PREHASH: wakes the texture pre-validation worker while it runs
// (ios/IOSTexturePrehash.h); called after the epoch has advanced.
inline std::atomic<void (*)() noexcept> epoch_listener{nullptr};

inline void advance_epoch() noexcept
{
	const bool enabled = epoch_enabled.load(std::memory_order_relaxed);
	if (enabled)
	{
		validation_epoch.fetch_add(1, std::memory_order_acq_rel);
		epoch_bumps.fetch_add(1, std::memory_order_relaxed);
	}
	// Observing this revision also observes the preceding hash epoch and writes.
	sampler_revision.fetch_add(1, std::memory_order_acq_rel);

	if (enabled)
	{
		if (const auto listener = epoch_listener.load(std::memory_order_relaxed))
		{
			listener();
		}
	}
}
}
