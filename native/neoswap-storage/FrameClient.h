// SPDX-License-Identifier: MIT
#pragma once
#include "SourceClient.h"
#include <array>
#include <cstddef>
#include <cstdint>
#include <condition_variable>
#include <mutex>

namespace neostation::source_client {
// Immutable packed SOFTWARE pixels only, after the decoder has relinquished
// its references. Neither guest buffers nor GPU images belong to this client.
inline constexpr uint32_t frame_domain = 3;
inline constexpr uint64_t frame_max_bytes = 4ULL << 20;
inline constexpr uint32_t frame_max_chunks = 4;
inline constexpr uint64_t frame_cold_age_us = 250'000;
inline constexpr uint32_t frame_warm_count = 8, frame_min_queue = 24;
// Protect the next pictures as well as FFmpeg's newest references. Archiving
// the FIFO head creates an avoidable disk restore on cellVdecGetPicture.
inline constexpr uint32_t frame_warm_head_count = 8;
inline constexpr uint64_t frame_prefetch_payload_limit = 8ULL << 20;
inline constexpr uint32_t frame_prefetch_count_limit = 8;
enum class FrameWarmState : uint8_t { cold, loading, ready, consumed, failed };
inline constinit std::atomic<uint64_t> frame_prefetch_payload_bytes{0},frame_prefetch_peak_bytes{0};
inline constinit std::atomic<uint32_t> frame_prefetch_count{0};
inline constinit std::atomic<uint64_t> frame_prefetch_hits{0},frame_prefetch_requests{0};
inline constinit std::atomic<uint64_t> frame_prefetch_failures{0},frame_prefetch_refusals{0};
inline constinit std::atomic<uint64_t> frame_demand_reads{0},frame_prefetch_wait_max_us{0};
inline constinit std::atomic<uint64_t> frame_prefetch_read_us{0},frame_prefetch_read_max_us{0};
inline constinit std::atomic<uint64_t> frame_demand_read_us{0},frame_demand_read_max_us{0};
inline constexpr bool frame_requires_restore_slot(bool archived, bool has_output) noexcept {
    // Normal/warm/default-off consumption keeps the original producer wakeup.
    return archived && has_output;
}
inline bool frame_queue_has_room(uint64_t queued, uint64_t consuming, uint64_t maximum) noexcept {
    return queued < maximum && consuming < maximum - queued;
}
inline bool frame_can_cool(uint32_t queue, uint32_t position, uint64_t age_us,
                           uint64_t bytes, bool exclusively_owned) noexcept {
    return exclusively_owned && queue >= frame_min_queue && position >= frame_warm_head_count && position < queue &&
        queue - position > frame_warm_count && age_us >= frame_cold_age_us &&
        bytes >= 4096 && bytes <= frame_max_bytes;
}
struct FrameReference final {
    std::array<Reference, frame_max_chunks> chunks;
    uint64_t bytes = 0;
    uint32_t count = 0;
    std::atomic<FrameWarmState> warm_state{FrameWarmState::cold};
    std::mutex warm_mutex;
    std::condition_variable warm_changed;
    std::string warm_pixels;
    bool warm_charge = false; // guarded by warm_mutex; last shared owner retires it
    ~FrameReference();
};
class ColdFrame final {
public:
    bool archived() const noexcept { return bool(reference_); }
    void reset() noexcept { reference_.reset(); }
    // Transactional admission: every chunk shares ONE session; partial
    // acceptance is retired and the caller must keep its original AVFrame.
    // This only copies bounded bytes, never performs storage I/O.
    bool offload(const char* packed_pixels, size_t bytes) noexcept;
    // Allocation/copy lives in the dedicated exception-enabled source unit,
    // keeping decoder consumers valid with their real -fno-exceptions flags.
    using PixelCopy = int (*)(char*, size_t, void*);
    bool offload_copy(size_t bytes, PixelCopy copy, void* context) noexcept;
    // VDEC's CPU consumer only, outside the queue/conversion mutexes. Failed
    // restore clears output; no caller may consume partially restored pixels.
    int restore(std::string& output, int& os_error, bool* prefetched = nullptr) const noexcept;
    bool can_prefetch() const noexcept {
        return reference_ && reference_->warm_state.load(std::memory_order_relaxed)==FrameWarmState::cold;
    }
    // Existing VDEC producer only, OUTSIDE its queue/conversion locks. There
    // is no new worker thread, Core ABI or host storage API. A consumed frame
    // never starts a second speculative read. Payload/count limits are global.
    bool prefetch() const noexcept;
private:
    std::shared_ptr<FrameReference> reference_;
};
}
