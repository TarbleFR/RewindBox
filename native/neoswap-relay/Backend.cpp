// SPDX-License-Identifier: MIT
// Adapted from Guest Page Relay; see LICENSE in this directory.
#include "Backend.h"
#include <algorithm>
#include <array>
#include <atomic>
#include <bitset>
#include <cerrno>
#include <chrono>
#include <limits>
#include <mutex>
#include <new>
#if defined(__APPLE__)
#if __has_include("../Donation/Broker.h")
#include "../Donation/Broker.h"
#else
#include "../neoswap-donation/Broker.h"
#endif
#include <mach/mach.h>
#include <sys/mman.h>
#endif

namespace neostation::relay {
namespace {
constexpr std::uint64_t alignment = NEOSWAP_RELAY_ALIGNMENT;
constexpr std::uint64_t prepared_maximum_bytes = 16ULL * 1024 * 1024;
constexpr std::size_t prepared_bins = prepared_maximum_bytes / alignment, prepared_slots = 128;
constexpr std::uint32_t maximum_bin_demand = 4;
// Build 444: the host maintenance pass is signalled at most this often.
constexpr std::uint64_t wakeup_interval_ns = 50'000'000;
static_assert(std::atomic<std::uint64_t>::is_always_lock_free,
    "Prepared relay requests must not hide an atomic implementation lock");
constexpr std::size_t maximum_entries = 16;
// More retained named-object capacity does not multiply host metadata. Large
// segments still share the original bounded token/alias tables; exhaustion
// takes the client's ordinary allocator fallback before any relay view exists.
constexpr std::size_t maximum_objects = 16384;
constexpr std::size_t maximum_segment_pages = maximum_segment_bytes / alignment;
constexpr std::size_t maximum_aliases = maximum_objects * 4;
constexpr std::uint64_t index_mask = maximum_objects - 1;
constexpr unsigned token_shift = 14;
static_assert((1U << token_shift) == maximum_objects);
static_assert(maximum_entries * maximum_segment_bytes == maximum_capacity);
bool valid_size(std::uint64_t bytes) noexcept {
    return bytes && bytes <= maximum_capacity && bytes % alignment == 0;
}
bool overlaps(std::uintptr_t a, std::uint64_t ab, std::uintptr_t b, std::uint64_t bb) noexcept {
    return a < b + bb && b < a + ab;
}
bool valid_range(std::uintptr_t address, std::uint64_t bytes) noexcept {
    return address && address % alignment == 0 &&
        bytes <= std::numeric_limits<std::uintptr_t>::max() - address;
}
} // namespace

struct Backend::State {
    struct Entry {
        std::uint32_t port = 0;
        std::int32_t pid = 0;
        std::uint64_t generation = 0, bytes = 0;
        std::uintptr_t window = 0;
        bool ready = false;
        // A bitmap naturally coalesces adjacent free intervals; no allocation
        // or fallible metadata growth occurs while returning a guest object.
        std::bitset<maximum_segment_pages> occupied;
        std::size_t occupied_pages = 0;
    };
    struct Object {
        std::uint64_t token = 0, bytes = 0, offset = 0;
        std::uint32_t entry = 0, owner = 0, aliases = 0;
        bool retiring = false;
        int quarantine_error = 0;
        bool published = false, prepared = false, pool_origin = false;
    };
    struct Alias {
        std::uint64_t token = 0, bytes = 0;
        std::uintptr_t address = 0;
        bool fixed = false;
        bool quarantined = false;
    };
    struct Demand {
        std::atomic<std::uint64_t> bytes{0};
        std::atomic<std::uint64_t> count{0};
    };
    struct Prepared { std::uint64_t token = 0, tick = 0; std::size_t bin = 0; };
    std::array<Demand, prepared_bins> demands{};
    std::array<Prepared, prepared_slots> prepared{};
    std::array<std::atomic<std::uint64_t>, maximum_objects> returnable{}, returned{};
    std::atomic<std::uint64_t> returned_count{0};
    std::atomic<std::uint64_t> request_count{0}, requested_bytes{0}, miss_busy{0};
    std::atomic<std::uint64_t> unsupported_count{0}, demand_overflow{0};
    NeoSwapPreparedRelayStats prepared_stats{};
    // Build 444 direct admission. Counters taken before the lock are atomics;
    // the rest of direct_stats and the allowance are written under the mutex.
    std::atomic<std::uint64_t> direct_requests{0}, direct_requested_bytes{0}, direct_busy{0};
    std::atomic<std::uint64_t> direct_refused_invalid{0}, oversize_requests{0};
    std::atomic<std::uint64_t> oversize_requested_bytes{0}, oversize_max_bytes{0}, wakeups{0};
    std::atomic<void (*)(void*)> demand_callback{nullptr};
    std::atomic<void*> demand_context{nullptr};
    std::atomic<std::uint64_t> last_wakeup_ns{0};
    NeoSwapDirectRelayStats direct_stats{};
    std::uint64_t direct_allowance = 0;
    std::uint64_t maintenance_tick = 0;
    std::size_t next_demand = 0;
    PressureDiagnostics pressure_diagnostics;
    const Operations ops;
    void* context;
    std::mutex mutex;
    std::array<Entry, maximum_entries> entries{};
    std::array<Object, maximum_objects> objects{};
    std::array<Alias, maximum_aliases> aliases{};
    NeoSwapRelayStats stats{};
    std::uint64_t capacity_limit = maximum_capacity, next_serial = 1;
    std::size_t next_object = 0, next_alias = 0, next_collect = 0;
    bool closing = false;
    State(const Operations& operations, void* user) noexcept : ops(operations), context(user) {
        stats.struct_size = sizeof(stats);
        stats.abi_version = NEOSWAP_RELAY_ABI;
        prepared_stats.struct_size = sizeof(prepared_stats);
        prepared_stats.abi_version = NEOSWAP_PREPARED_RELAY_ABI;
        direct_stats.struct_size = sizeof(direct_stats);
        direct_stats.abi_version = NEOSWAP_DIRECT_RELAY_ABI;
        for (std::size_t i = 0; i != demands.size(); ++i)
            demands[i].bytes.store(alignment * (i + 1), std::memory_order_relaxed);
    }
    // Every aligned size through 16 MiB has a permanent counter. Direct lookup
    // and one CAS never spin, allocate, or exhaust a size-registration table.
    std::size_t request(std::uint64_t bytes) noexcept {
        const auto index = static_cast<std::size_t>(bytes / alignment - 1);
        auto count = demands[index].count.load(std::memory_order_relaxed);
        if (count >= maximum_bin_demand ||
            !demands[index].count.compare_exchange_strong(count, count + 1, std::memory_order_relaxed))
            demand_overflow.fetch_add(1, std::memory_order_relaxed);
        return index;
    }
    // Never called with the mutex held. The callback must not block: the host
    // merges data into a dispatch source and the utility pass runs later.
    void signal_demand() noexcept {
        const auto callback = demand_callback.load(std::memory_order_acquire);
        if (!callback) return;
        const auto now = static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(
            std::chrono::steady_clock::now().time_since_epoch()).count());
        auto previous = last_wakeup_ns.load(std::memory_order_relaxed);
        if (previous && now - previous < wakeup_interval_ns) return;
        if (!last_wakeup_ns.compare_exchange_strong(previous, now, std::memory_order_relaxed)) return;
        wakeups.fetch_add(1, std::memory_order_relaxed);
        callback(demand_context.load(std::memory_order_acquire));
    }
    void note_oversize(std::uint64_t bytes) noexcept {
        if (bytes <= prepared_maximum_bytes) return;
        oversize_requests.fetch_add(1, std::memory_order_relaxed);
        oversize_requested_bytes.fetch_add(bytes, std::memory_order_relaxed);
        auto maximum = oversize_max_bytes.load(std::memory_order_relaxed);
        while (maximum < bytes && !oversize_max_bytes.compare_exchange_weak(maximum, bytes, std::memory_order_relaxed)) {}
    }
    int create_object(std::uint32_t owner, std::uint64_t bytes, std::uint64_t* token) noexcept;
    bool available() const noexcept {
        return ops.retain && ops.drop && ops.map && ops.unmap && ops.zero && ops.headroom;
    }
    int fail(int result, int error = 0) noexcept {
        stats.last_result = result;
        stats.last_os_error = error;
        ++stats.rejection_count;
        if (error) ++stats.os_error_count;
        return result;
    }
    int success() noexcept {
        stats.last_result = NEOSWAP_RELAY_OK;
        stats.last_os_error = 0;
        return NEOSWAP_RELAY_OK;
    }
    void recount_entries() noexcept {
        stats.capacity_bytes = stats.retained_capacity_bytes = stats.entry_count =
            stats.pending_cleanup_entries = 0;
        for (const auto& entry : entries) if (entry.port) {
            stats.retained_capacity_bytes += entry.bytes;
            if (entry.ready) {
                stats.capacity_bytes += entry.bytes;
                ++stats.entry_count;
            } else ++stats.pending_cleanup_entries;
        }
    }
    Object* object(std::uint64_t token) noexcept {
        auto& candidate = objects[token & index_mask];
        return token && candidate.token == token ? &candidate : nullptr;
    }
    int cleanup(Entry& entry) noexcept {
        entry.ready = false;
        if (entry.window) {
            const int result = ops.unmap(context, entry.window, entry.bytes, false);
            if (result) return fail(NEOSWAP_RELAY_CLEANUP, result);
            entry.window = 0;
        }
        if (entry.port) {
            const int result = ops.drop(context, entry.port);
            if (result) return fail(NEOSWAP_RELAY_CLEANUP, result);
        }
        entry = {};
        return NEOSWAP_RELAY_OK;
    }
    int finish_object(Object& object) noexcept {
        if (object.aliases) return fail(NEOSWAP_RELAY_BUSY);
        auto& entry = entries[object.entry];
        // Prepared tokens have never exposed a caller alias. Fresh backing is
        // zero-filled and reclaimed backing was scrubbed before bitmap release.
        // Do not fault unused prepared pages merely to return their reservation.
        if (!object.pool_origin || object.published) {
            const int result = ops.zero(context, entry.window + object.offset, object.bytes);
            if (result) return fail(NEOSWAP_RELAY_CLEANUP, result);
        }
        if (object.pool_origin && object.retiring) {
            prepared_stats.pending_scrub_bytes -= object.bytes;
            --prepared_stats.pending_scrub_count;
        }
        if (object.pool_origin && !object.published)
            prepared_stats.unpublished_bytes -= object.bytes;
        const auto first = object.offset / alignment;
        for (std::size_t n = 0; n < object.bytes / alignment; ++n) entry.occupied.reset(first + n);
        entry.occupied_pages -= object.bytes / alignment;
        stats.live_bytes -= object.bytes;
        if (object.owner < tracked_owner_count) {
            pressure_diagnostics.owner_live_bytes[object.owner] -= object.bytes;
            if (object.published && !object.retiring)
                pressure_diagnostics.owner_published_live_bytes[object.owner] -= object.bytes;
        }
        --stats.object_count;
        if (object.retiring) --stats.retiring_object_count;
        object = {};
        return success();
    }
    void drain_unused() noexcept {
        if (!returned_count.load(std::memory_order_acquire)) return;
        unsigned remaining = 128;
        for (std::size_t i = 0; i < returned.size() && remaining; ++i) {
            const auto token = returned[i].exchange(0, std::memory_order_acquire);
            if (!token) continue;
            --remaining;
            returned_count.fetch_sub(1, std::memory_order_relaxed);
            auto* value = object(token);
            // CAS admission only accepts a currently borrowed, never-published
            // generation. Lifecycle calls cannot race under the API contract.
            if (!value || !value->pool_origin || value->published || value->aliases || value->prepared)
                continue;
            ++prepared_stats.reclaimed_total;
            finish_object(*value);
        }
    }
    int collect_object(Object& object, unsigned& remaining_unmaps, bool initial_retirement = false) noexcept {
        int failure = NEOSWAP_RELAY_OK;
        if (object.aliases) for (auto& alias : aliases) {
            if (alias.token != object.token) continue;
            if (alias.quarantined) continue;
            // No deferred fixed-address writes: the caller can reuse that
            // address after retire returns. Query-then-replace is not atomic
            // either, so a failed initial replacement must remain quarantined.
            if (alias.fixed && !initial_retirement) continue;
            if (!alias.fixed) {
                if (!remaining_unmaps) continue;
                --remaining_unmaps;
            }
            const int result = ops.unmap(context, alias.address, alias.bytes, alias.fixed);
            if (result) {
                if (alias.fixed) {
                    alias.quarantined = true;
                    object.quarantine_error = result;
                    ++stats.quarantined_fixed_alias_count;
                }
                failure = fail(NEOSWAP_RELAY_CLEANUP, result);
                continue;
            }
            --object.aliases;
            --stats.alias_count;
            stats.mapped_alias_bytes -= alias.bytes;
            alias = {};
        }
        if (failure) return failure;
        if (object.quarantine_error) {
            // Report the original retained failure without counting another OS
            // syscall/error: this pass intentionally did not touch that range.
            stats.last_result = NEOSWAP_RELAY_CLEANUP;
            stats.last_os_error = object.quarantine_error;
            return NEOSWAP_RELAY_CLEANUP;
        }
        if (object.aliases) return fail(NEOSWAP_RELAY_BUSY);
        // A pooled object is scrubbed only by utility collect(), never by its
        // retiring guest thread. FIXED aliases above are still replaced now.
        if (initial_retirement && object.pool_origin) return success();
        return finish_object(object);
    }
};

Backend::Backend(const Operations& operations, void* context) noexcept
    : state_(new (std::nothrow) State(operations, context)) {}
Backend::~Backend() {
    // Application-global instance lives until process exit. shutdown is also
    // explicit so callers can retry kernel failures before destroying a fixture.
    (void)shutdown();
}
int Backend::configure(std::uint32_t mask, std::uint64_t limit) noexcept {
    if (!state_) return NEOSWAP_RELAY_DISABLED;
    auto& s = *state_;
    std::lock_guard<std::mutex> guard(s.mutex);
    if (!s.available()) return s.fail(NEOSWAP_RELAY_DISABLED);
    if ((mask & ~supported_owner_mask) || !valid_size(limit)) return s.fail(NEOSWAP_RELAY_INVALID);
    if (s.stats.object_count || s.closing) return s.fail(NEOSWAP_RELAY_BUSY);
    if (s.stats.retained_capacity_bytes > limit) return s.fail(NEOSWAP_RELAY_QUOTA);
    s.stats.enabled_owner_mask = mask;
    s.capacity_limit = limit;
    return s.success();
}
int Backend::adopt(std::uint32_t port, std::uint64_t bytes, std::int32_t pid,
                   std::uint64_t generation) noexcept {
    if (!state_) return NEOSWAP_RELAY_DISABLED;
    auto& s = *state_;
    std::lock_guard<std::mutex> guard(s.mutex);
    if (!s.available() || !s.stats.enabled_owner_mask || s.closing) return s.fail(NEOSWAP_RELAY_DISABLED);
    if (!port || !valid_size(bytes) || bytes > maximum_segment_bytes || pid <= 0 || !generation)
        return s.fail(NEOSWAP_RELAY_INVALID);
    if (bytes > s.capacity_limit - s.stats.retained_capacity_bytes) return s.fail(NEOSWAP_RELAY_QUOTA);
    State::Entry* slot = nullptr;
    for (auto& entry : s.entries) {
        if (entry.port == port) return s.fail(NEOSWAP_RELAY_INVALID);
        if (!entry.port && !slot) slot = &entry;
    }
    if (!slot) return s.fail(NEOSWAP_RELAY_LIMIT);
    int result = s.ops.retain(s.context, port);
    if (result) return s.fail(NEOSWAP_RELAY_MAPPING, result);
    slot->port = port;
    slot->bytes = bytes;
    slot->pid = pid;
    slot->generation = generation;
    result = s.ops.map(s.context, port, 0, bytes, 0, NEOSWAP_RELAY_READ_WRITE, &slot->window);
    if (result || !valid_range(slot->window, bytes)) {
        // A conforming failed map has no new mapping. Retain failed cleanup
        // rights/windows for shutdown instead of claiming those bytes are free.
        const int map_error = result ? result : -1;
        const int cleanup = s.cleanup(*slot);
        s.recount_entries();
        return cleanup ? cleanup : s.fail(NEOSWAP_RELAY_MAPPING, map_error);
    }
    slot->ready = true;
    s.recount_entries();
    return s.success();
}
void Backend::set_pressure(bool raised) noexcept {
    if (!state_) return;
    std::lock_guard<std::mutex> guard(state_->mutex);
    if (state_->stats.pressure_raised != (raised ? 1U : 0U))
        ++state_->pressure_diagnostics.transitions;
    state_->stats.pressure_raised = raised ? 1U : 0U;
}
int Backend::set_owner_quota(std::uint32_t owner, std::uint64_t bytes) noexcept {
    if (!state_) return NEOSWAP_RELAY_DISABLED;
    auto& s = *state_;
    std::lock_guard<std::mutex> guard(s.mutex);
    if (owner >= tracked_owner_count || !(supported_owner_mask & (1U << owner)))
        return s.fail(NEOSWAP_RELAY_INVALID);
    s.pressure_diagnostics.owner_quota_bytes[owner] = bytes;
    return NEOSWAP_RELAY_OK;
}
int Backend::State::create_object(std::uint32_t owner, std::uint64_t bytes,
                                  std::uint64_t* token) noexcept {
    if (!token || !valid_size(bytes) || owner >= 32) return fail(NEOSWAP_RELAY_INVALID);
    if (bytes > maximum_segment_bytes) return fail(NEOSWAP_RELAY_QUOTA);
    if (!(stats.enabled_owner_mask & (1U << owner)) || !stats.capacity_bytes || closing ||
        stats.quarantined_fixed_alias_count)
        return fail(NEOSWAP_RELAY_DISABLED);
    if (stats.pressure_raised || ops.headroom(context) < bytes) {
        ++pressure_diagnostics.create_refusals;
        return fail(NEOSWAP_RELAY_PRESSURE);
    }
    if (bytes > stats.capacity_bytes - stats.live_bytes) return fail(NEOSWAP_RELAY_QUOTA);
    if (owner < tracked_owner_count) {
        // A per-owner ceiling bounds HOST loans so guest objects retain their
        // reserved share. Zero means the owner is bounded by capacity only.
        const auto quota = pressure_diagnostics.owner_quota_bytes[owner];
        const auto live = pressure_diagnostics.owner_live_bytes[owner];
        if (quota && (live >= quota || bytes > quota - live)) {
            ++pressure_diagnostics.quota_refusals;
            return fail(NEOSWAP_RELAY_QUOTA);
        }
    }
    if (next_serial > (std::numeric_limits<std::uint64_t>::max() >> token_shift))
        return fail(NEOSWAP_RELAY_LIMIT);
    std::size_t object_index = maximum_objects;
    for (std::size_t i = 0; i < maximum_objects; ++i) {
        const auto index = (next_object + i) % maximum_objects;
        if (!objects[index].token) { object_index = index; break; }
    }
    if (object_index == maximum_objects) return fail(NEOSWAP_RELAY_LIMIT);
    const std::size_t pages = bytes / alignment;
    // Adapt DonatedMemory's best-fit policy from MeloNX 2889267834c7581a:
    // preserve large contiguous runs for guest backing instead of splitting
    // the first run for a small host loan. Scan existing bitmap metadata only;
    // no allocation, page access or remapping, and stop at an exact fit.
    std::size_t best_entry = maximum_entries, best_first = 0;
    std::size_t best_pages = maximum_segment_pages + 1;
    for (std::size_t index = 0; index < entries.size(); ++index) {
        const auto& entry = entries[index];
        if (!entry.ready || entry.bytes < bytes) continue;
        const auto end = entry.bytes / alignment;
        if (end - entry.occupied_pages < pages) continue;
        // Untouched retained capacity is common (up to sixteen 512 MiB
        // segments). An empty segment is one known run, so never scan all its
        // bits for every small allocation. Failed scrubs keep pages occupied.
        if (!entry.occupied_pages) {
            if (end < best_pages) {
                best_entry = index;
                best_first = 0;
                best_pages = end;
            }
            if (best_pages == pages) break;
            continue;
        }
        std::size_t contiguous = 0;
        for (std::size_t page = 0; page <= end; ++page) {
            if (page < end && !entry.occupied[page]) {
                ++contiguous;
                continue;
            }
            if (contiguous >= pages && contiguous < best_pages) {
                best_entry = index;
                best_first = page - contiguous;
                best_pages = contiguous;
                if (best_pages == pages) break;
            }
            contiguous = 0;
        }
        if (best_pages == pages) break;
    }
    if (best_entry == maximum_entries)
        return fail(NEOSWAP_RELAY_QUOTA); // Total free capacity can be fragmented.
    auto& entry = entries[best_entry];
    for (auto n = best_first; n < best_first + pages; ++n) entry.occupied.set(n);
    entry.occupied_pages += pages;
    auto& object = objects[object_index];
    object = {(next_serial++ << token_shift) | object_index, bytes,
              best_first * alignment, static_cast<std::uint32_t>(best_entry), owner, 0, false, 0};
    next_object = (object_index + 1) % maximum_objects;
    stats.live_bytes += bytes;
    stats.peak_live_bytes = std::max(stats.peak_live_bytes, stats.live_bytes);
    if (owner < tracked_owner_count) {
        auto& live = pressure_diagnostics.owner_live_bytes[owner];
        live += bytes;
        pressure_diagnostics.owner_peak_bytes[owner] =
            std::max(pressure_diagnostics.owner_peak_bytes[owner], live);
    }
    ++stats.object_count;
    *token = object.token;
    return success();
}
int Backend::create(std::uint32_t owner, std::uint64_t bytes, std::uint64_t* token) noexcept {
    if (token) *token = 0;
    if (!state_) return NEOSWAP_RELAY_DISABLED;
    std::lock_guard<std::mutex> guard(state_->mutex);
    return state_->create_object(owner, bytes, token);
}
int Backend::try_acquire_prepared(std::uint32_t owner, std::uint64_t bytes,
                                  std::uint64_t* token) noexcept {
    if (token) *token = 0;
    if (!state_) return NEOSWAP_RELAY_DISABLED;
    auto& s = *state_;
    s.request_count.fetch_add(1, std::memory_order_relaxed);
    s.requested_bytes.fetch_add(bytes, std::memory_order_relaxed);
    if (!token || owner != 0 || !valid_size(bytes) || bytes > prepared_maximum_bytes) {
        s.unsupported_count.fetch_add(1, std::memory_order_relaxed);
        return NEOSWAP_RELAY_INVALID;
    }
    std::unique_lock<std::mutex> guard(s.mutex, std::try_to_lock);
    if (!guard.owns_lock()) {
        s.miss_busy.fetch_add(1, std::memory_order_relaxed);
        s.request(bytes);
        return NEOSWAP_RELAY_BUSY;
    }
    if (s.closing || !(s.stats.enabled_owner_mask & 1U) || !s.stats.capacity_bytes ||
        s.stats.quarantined_fixed_alias_count) {
        ++s.prepared_stats.refused_disabled;
        return NEOSWAP_RELAY_DISABLED;
    }
    if (s.stats.pressure_raised) {
        ++s.prepared_stats.refused_pressure;
        return NEOSWAP_RELAY_PRESSURE;
    }
    // Record a replacement on success too; utility preparation follows actual
    // consumption. Each exact-size demand is bounded to four waiting objects.
    s.request(bytes);
    for (auto& slot : s.prepared) {
        if (!slot.token) continue;
        auto* object = s.object(slot.token);
        if (!object || object->bytes != bytes) continue;
        object->prepared = false;
        s.returnable[object->token & index_mask].store(object->token, std::memory_order_release);
        *token = object->token;
        s.prepared_stats.prepared_bytes -= bytes;
        --s.prepared_stats.prepared_count;
        ++s.prepared_stats.acquired_count;
        s.prepared_stats.acquired_bytes += bytes;
        slot = {};
        return NEOSWAP_RELAY_OK;
    }
    ++s.prepared_stats.miss_empty;
    guard.unlock();
    s.signal_demand();
    return NEOSWAP_RELAY_QUOTA;
}
// Build 444. The stock serves exact sizes it already holds; this call admits a
// new exact-size object when the stock misses, without waiting for the utility
// pass. It never blocks a guest thread: a held metadata lock is BUSY, and the
// allowance installed by the budget controller bounds what one interval may
// admit beyond the stock. The object is pool-origin: an unpublished token can
// be returned without syscalls, and a published one is scrubbed by collect().
int Backend::try_create_guest(std::uint32_t owner, std::uint64_t bytes, std::uint64_t* token) noexcept {
    if (token) *token = 0;
    if (!state_) return NEOSWAP_RELAY_DISABLED;
    auto& s = *state_;
    s.direct_requests.fetch_add(1, std::memory_order_relaxed);
    s.direct_requested_bytes.fetch_add(bytes, std::memory_order_relaxed);
    if (!token || owner != 0 || !valid_size(bytes) || bytes > maximum_segment_bytes) {
        s.direct_refused_invalid.fetch_add(1, std::memory_order_relaxed);
        return NEOSWAP_RELAY_INVALID;
    }
    s.note_oversize(bytes);
    std::unique_lock<std::mutex> guard(s.mutex, std::try_to_lock);
    if (!guard.owns_lock()) {
        s.direct_busy.fetch_add(1, std::memory_order_relaxed);
        return NEOSWAP_RELAY_BUSY;
    }
    if (s.closing || !(s.stats.enabled_owner_mask & 1U) || !s.stats.capacity_bytes ||
        s.stats.quarantined_fixed_alias_count) {
        ++s.direct_stats.refused_disabled;
        return NEOSWAP_RELAY_DISABLED;
    }
    if (s.stats.pressure_raised) {
        ++s.direct_stats.refused_pressure;
        return NEOSWAP_RELAY_PRESSURE;
    }
    if (bytes > s.direct_allowance) {
        ++s.direct_stats.refused_budget;
        guard.unlock();
        s.signal_demand();
        return NEOSWAP_RELAY_QUOTA;
    }
    const int result = s.create_object(0, bytes, token);
    if (result != NEOSWAP_RELAY_OK) {
        switch (result) {
        case NEOSWAP_RELAY_PRESSURE: ++s.direct_stats.refused_pressure; break;
        case NEOSWAP_RELAY_QUOTA: ++s.direct_stats.refused_capacity; break;
        case NEOSWAP_RELAY_LIMIT: ++s.direct_stats.refused_limit; break;
        case NEOSWAP_RELAY_DISABLED: ++s.direct_stats.refused_disabled; break;
        default: s.direct_refused_invalid.fetch_add(1, std::memory_order_relaxed); break;
        }
        return result;
    }
    auto* object = s.object(*token);
    object->pool_origin = true;
    s.returnable[*token & index_mask].store(*token, std::memory_order_release);
    s.direct_allowance -= bytes;
    s.prepared_stats.unpublished_bytes += bytes;
    ++s.direct_stats.created;
    s.direct_stats.created_bytes += bytes;
    return NEOSWAP_RELAY_OK;
}
int Backend::direct_snapshot(NeoSwapDirectRelayStats* output) noexcept {
    if (!state_) return NEOSWAP_RELAY_DISABLED;
    if (!output || output->struct_size < sizeof(*output)) return NEOSWAP_RELAY_INVALID;
    auto& s = *state_;
    std::lock_guard<std::mutex> guard(s.mutex);
    *output = s.direct_stats;
    output->requests = s.direct_requests.load(std::memory_order_relaxed);
    output->requested_bytes = s.direct_requested_bytes.load(std::memory_order_relaxed);
    output->busy = s.direct_busy.load(std::memory_order_relaxed);
    output->refused_invalid = s.direct_refused_invalid.load(std::memory_order_relaxed);
    output->oversize_requests = s.oversize_requests.load(std::memory_order_relaxed);
    output->oversize_requested_bytes = s.oversize_requested_bytes.load(std::memory_order_relaxed);
    output->oversize_max_bytes = s.oversize_max_bytes.load(std::memory_order_relaxed);
    output->allowance_bytes = s.direct_allowance;
    output->wakeups = s.wakeups.load(std::memory_order_relaxed);
    return NEOSWAP_RELAY_OK;
}
void Backend::set_direct_guest_allowance(std::uint64_t bytes) noexcept {
    if (!state_) return;
    auto& s = *state_;
    std::lock_guard<std::mutex> guard(s.mutex);
    s.direct_allowance = bytes;
    ++s.direct_stats.allowance_grants;
    s.direct_stats.allowance_granted_bytes += bytes;
}
void Backend::set_demand_signal(void (*callback)(void*), void* context) noexcept {
    if (!state_) return;
    // Publish the context before the callback so a concurrent signal never
    // runs a new callback with a stale context.
    state_->demand_context.store(callback ? context : nullptr, std::memory_order_release);
    state_->demand_callback.store(callback, std::memory_order_release);
}
int Backend::return_unused_prepared(std::uint64_t token) noexcept {
    if (!state_) return NEOSWAP_RELAY_DISABLED;
    if (!token) return NEOSWAP_RELAY_UNKNOWN;
    auto& s = *state_;
    const auto index = token & index_mask;
    auto expected = token;
    if (!s.returnable[index].compare_exchange_strong(expected, 0, std::memory_order_acq_rel))
        return NEOSWAP_RELAY_UNKNOWN;
    // Increment before publication: a concurrent worker may defer seeing the
    // queue cell to its next bounded tick, but cannot underflow its count.
    s.returned_count.fetch_add(1, std::memory_order_relaxed);
    s.returned[index].store(token, std::memory_order_release);
    return NEOSWAP_RELAY_OK;
}
int Backend::prepared_snapshot(NeoSwapPreparedRelayStats* output) noexcept {
    if (!state_) return NEOSWAP_RELAY_DISABLED;
    if (!output || output->struct_size < sizeof(*output)) return NEOSWAP_RELAY_INVALID;
    auto& s = *state_;
    std::lock_guard<std::mutex> guard(s.mutex);
    *output = s.prepared_stats;
    output->request_count = s.request_count.load(std::memory_order_relaxed);
    output->requested_bytes = s.requested_bytes.load(std::memory_order_relaxed);
    output->miss_busy = s.miss_busy.load(std::memory_order_relaxed);
    output->unsupported_count = s.unsupported_count.load(std::memory_order_relaxed);
    output->demand_overflow = s.demand_overflow.load(std::memory_order_relaxed);
    for (const auto& demand : s.demands) {
        const auto count = demand.count.load(std::memory_order_relaxed);
        output->demand_count += count;
        output->demand_bytes += count * demand.bytes.load(std::memory_order_relaxed);
    }
    return NEOSWAP_RELAY_OK;
}
int Backend::maintain_guest_pool(std::uint64_t target, std::uint64_t growth) noexcept {
    if (!state_) return NEOSWAP_RELAY_DISABLED;
    auto& s = *state_;
    std::lock_guard<std::mutex> guard(s.mutex);
    ++s.maintenance_tick;
    s.drain_unused();
    target = std::min<std::uint64_t>(target, 64ULL * 1024 * 1024);
    growth = std::min<std::uint64_t>(growth, 32ULL * 1024 * 1024);
    if (s.closing || s.stats.pressure_raised || !(s.stats.enabled_owner_mask & 1U) ||
        s.stats.quarantined_fixed_alias_count) target = growth = 0;
    // Untouched reservations can be returned without scrubbing or syscalls.
    // Eight-second idle expiry at the host's 250 ms maintenance cadence keeps
    // obsolete size classes from monopolizing a small stock.
    for (auto& slot : s.prepared) {
        if (!slot.token) continue;
        if (s.prepared_stats.prepared_bytes <= target && s.maintenance_tick - slot.tick < 32) continue;
        auto* object = s.object(slot.token);
        if (!object) continue;
        s.prepared_stats.prepared_bytes -= object->bytes;
        --s.prepared_stats.prepared_count;
        ++s.prepared_stats.reclaimed_total;
        s.finish_object(*object);
        slot = {};
    }
    unsigned remaining = 8;
    const auto first = s.next_demand;
    for (std::size_t i = 0; i < s.demands.size() && remaining; ++i) {
        const auto bin = (first + i) % s.demands.size();
        auto& demand = s.demands[bin];
        const auto bytes = demand.bytes.load(std::memory_order_relaxed);
        if (!bytes || !demand.count.load(std::memory_order_relaxed)) continue;
        if (s.prepared_stats.prepared_bytes >= target ||
            bytes > target - s.prepared_stats.prepared_bytes || bytes > growth) continue;
        // Build 444: a class that recorded a burst (up to four waiting
        // demands) is restocked for the whole burst in one pass, still within
        // the eight-object, growth and target bounds of this call.
        s.next_demand = (bin + 1) % s.demands.size();
        bool exhausted = false;
        while (remaining && demand.count.load(std::memory_order_relaxed) &&
               s.prepared_stats.prepared_bytes < target &&
               bytes <= target - s.prepared_stats.prepared_bytes && bytes <= growth) {
            State::Prepared* slot = nullptr;
            for (auto& candidate : s.prepared) if (!candidate.token) { slot = &candidate; break; }
            if (!slot) { exhausted = true; break; }
            std::uint64_t token = 0;
            --remaining;
            const int result = s.create_object(0, bytes, &token);
            if (result) { ++s.prepared_stats.prepare_failures; break; }
            auto* object = s.object(token);
            object->prepared = object->pool_origin = true;
            *slot = {token, s.maintenance_tick, bin};
            demand.count.fetch_sub(1, std::memory_order_relaxed);
            s.prepared_stats.prepared_bytes += bytes;
            s.prepared_stats.unpublished_bytes += bytes;
            ++s.prepared_stats.prepared_count;
            ++s.prepared_stats.prepared_total;
            s.prepared_stats.peak_prepared_bytes = std::max(s.prepared_stats.peak_prepared_bytes,
                                                           s.prepared_stats.prepared_bytes);
            growth -= bytes;
        }
        if (exhausted) break;
    }
    return NEOSWAP_RELAY_OK;
}
int Backend::map(std::uint64_t token, void* target, std::uint32_t protection, void** mapped) noexcept {
    if (mapped) *mapped = nullptr;
    if (!state_) return NEOSWAP_RELAY_DISABLED;
    auto& s = *state_;
    std::lock_guard<std::mutex> guard(s.mutex);
    auto* object = s.object(token);
    if (!object) return s.fail(NEOSWAP_RELAY_UNKNOWN);
    if (object->retiring || object->prepared) return s.fail(NEOSWAP_RELAY_BUSY);
    const auto address = reinterpret_cast<std::uintptr_t>(target);
    if (!mapped || (protection != NEOSWAP_RELAY_NONE && protection != NEOSWAP_RELAY_READ &&
                    protection != NEOSWAP_RELAY_READ_WRITE) || (address && !valid_range(address, object->bytes)))
        return s.fail(NEOSWAP_RELAY_INVALID);
    // Admission guards apply to NEW backing / its first published view. Once
    // RPCS3 has seen a view, file fallback would split g_base/g_sudo/map_self
    // into different objects. A later alias reuses the same retained bytes;
    // do not charge the full object against free memory again. This also holds
    // after temporary removal of every alias. Kernel map failure, fixed-range
    // validation, alias limits and retirement guards remain mandatory below.
    if (!object->published && (s.stats.pressure_raised || s.ops.headroom(s.context) < object->bytes)) {
        ++s.pressure_diagnostics.first_map_refusals;
        s.pressure_diagnostics.last_map_result = NEOSWAP_RELAY_PRESSURE;
        s.pressure_diagnostics.last_map_os_error = 0;
        return s.fail(NEOSWAP_RELAY_PRESSURE);
    }
    std::size_t alias_index = maximum_aliases;
    for (std::size_t i = 0; i < maximum_aliases; ++i) {
        const auto index = (s.next_alias + i) % maximum_aliases;
        const auto& alias = s.aliases[index];
        if (!alias.token && alias_index == maximum_aliases) alias_index = index;
        if (address && alias.token && overlaps(address, object->bytes, alias.address, alias.bytes))
            return s.fail(NEOSWAP_RELAY_INVALID);
        // ANYWHERE is chosen by the kernel and cannot overlap live mappings.
        if (!address && alias_index != maximum_aliases) break;
    }
    if (address) for (const auto& entry : s.entries) {
        if (entry.window && overlaps(address, object->bytes, entry.window, entry.bytes))
            return s.fail(NEOSWAP_RELAY_INVALID);
    }
    if (alias_index == maximum_aliases) return s.fail(NEOSWAP_RELAY_LIMIT);
    auto& entry = s.entries[object->entry];
    std::uintptr_t destination = 0;
    const int result = s.ops.map(s.context, entry.port, object->offset, object->bytes,
                                 address, protection, &destination);
    if (result) {
        ++s.pressure_diagnostics.map_failures;
        s.pressure_diagnostics.last_map_result = NEOSWAP_RELAY_MAPPING;
        s.pressure_diagnostics.last_map_os_error = result;
        return s.fail(NEOSWAP_RELAY_MAPPING, result);
    }
    if (object->published && s.stats.pressure_raised)
        ++s.pressure_diagnostics.existing_alias_maps;
    if (!object->published && object->owner < tracked_owner_count)
        s.pressure_diagnostics.owner_published_live_bytes[object->owner] += object->bytes;
    if (!object->published && object->pool_origin)
        s.prepared_stats.unpublished_bytes -= object->bytes;
    if (object->pool_origin)
        s.returnable[token & index_mask].store(0, std::memory_order_release);
    object->published = true;
    // Darwin guarantees aligned ANYWHERE and exact FIXED results. A mock must
    // honor the same contract; bookkeeping uses the returned live address.
    s.aliases[alias_index] = {token, object->bytes, destination, address != 0, false};
    s.next_alias = (alias_index + 1) % maximum_aliases;
    ++object->aliases;
    ++s.stats.alias_count;
    s.stats.mapped_alias_bytes += object->bytes;
    *mapped = reinterpret_cast<void*>(destination);
    return s.success();
}
int Backend::unmap(std::uint64_t token, void* address) noexcept {
    if (!state_) return NEOSWAP_RELAY_DISABLED;
    auto& s = *state_;
    std::lock_guard<std::mutex> guard(s.mutex);
    auto* object = s.object(token);
    if (!object) return s.fail(NEOSWAP_RELAY_UNKNOWN);
    if (object->retiring || object->prepared) return s.fail(NEOSWAP_RELAY_BUSY);
    for (auto& alias : s.aliases) {
        if (alias.token != token || alias.address != reinterpret_cast<std::uintptr_t>(address)) continue;
        const int result = s.ops.unmap(s.context, alias.address, alias.bytes, alias.fixed);
        if (result) return s.fail(NEOSWAP_RELAY_MAPPING, result);
        --object->aliases;
        --s.stats.alias_count;
        s.stats.mapped_alias_bytes -= alias.bytes;
        alias = {};
        return s.success();
    }
    return s.fail(NEOSWAP_RELAY_UNKNOWN);
}
int Backend::release(std::uint64_t token) noexcept {
    if (!state_) return NEOSWAP_RELAY_DISABLED;
    auto& s = *state_;
    std::lock_guard<std::mutex> guard(s.mutex);
    auto* object = s.object(token);
    if (!object) return s.fail(NEOSWAP_RELAY_UNKNOWN);
    if (object->prepared || object->retiring) return s.fail(NEOSWAP_RELAY_BUSY);
    if (object->pool_origin) {
        if (object->aliases) return s.fail(NEOSWAP_RELAY_BUSY);
        s.returnable[token & index_mask].store(0, std::memory_order_release);
        if (object->published)
            s.pressure_diagnostics.owner_published_live_bytes[object->owner] -= object->bytes;
        object->retiring = true;
        ++s.stats.retiring_object_count;
        s.prepared_stats.pending_scrub_bytes += object->bytes;
        ++s.prepared_stats.pending_scrub_count;
        return s.success();
    }
    return s.finish_object(*object);
}
int Backend::retire(std::uint64_t token) noexcept {
    if (!state_) return NEOSWAP_RELAY_DISABLED;
    auto& s = *state_;
    std::lock_guard<std::mutex> guard(s.mutex);
    auto* object = s.object(token);
    if (!object) return s.fail(NEOSWAP_RELAY_UNKNOWN);
    if (object->prepared) return s.fail(NEOSWAP_RELAY_BUSY);
    const bool initial_retirement = !object->retiring;
    if (initial_retirement) {
        if (object->pool_origin)
            s.returnable[token & index_mask].store(0, std::memory_order_release);
        if (object->published && object->owner < tracked_owner_count)
            s.pressure_diagnostics.owner_published_live_bytes[object->owner] -= object->bytes;
        object->retiring = true;
        ++s.stats.retiring_object_count;
        if (object->pool_origin) {
            s.prepared_stats.pending_scrub_bytes += object->bytes;
            ++s.prepared_stats.pending_scrub_count;
        }
    }
    unsigned remaining_unmaps = 64;
    return s.collect_object(*object, remaining_unmaps, initial_retirement);
}
int Backend::collect() noexcept {
    if (!state_) return NEOSWAP_RELAY_DISABLED;
    auto& s = *state_;
    std::lock_guard<std::mutex> guard(s.mutex);
    s.drain_unused();
    unsigned remaining_unmaps = 64, remaining_objects = 4;
    int failure = NEOSWAP_RELAY_OK;
    int failure_os = 0;
    const auto first = s.next_collect;
    for (std::size_t i = 0; i < maximum_objects; ++i) {
        const auto index = (first + i) % maximum_objects;
        auto& object = s.objects[index];
        if (!object.token || !object.retiring) continue;
        if (!remaining_objects) break;
        --remaining_objects;
        s.next_collect = (index + 1) % maximum_objects;
        const int result = s.collect_object(object, remaining_unmaps);
        if (result) { failure = result; failure_os = s.stats.last_os_error; }
    }
    if (failure) {
        s.stats.last_result = failure;
        s.stats.last_os_error = failure_os;
        return failure;
    }
    return s.stats.retiring_object_count ? s.fail(NEOSWAP_RELAY_BUSY) : s.success();
}
int Backend::enabled(std::uint32_t owner) noexcept {
    if (!state_ || owner >= 32) return 0;
    auto& s = *state_;
    std::lock_guard<std::mutex> guard(s.mutex);
    return !s.closing && !s.stats.pressure_raised && !s.stats.quarantined_fixed_alias_count && s.stats.capacity_bytes &&
        (s.stats.enabled_owner_mask & (1U << owner)) ? 1 : 0;
}
int Backend::snapshot(NeoSwapRelayStats* output) noexcept {
    if (!state_) return NEOSWAP_RELAY_DISABLED;
    auto& s = *state_;
    std::lock_guard<std::mutex> guard(s.mutex);
    if (!output || output->struct_size < sizeof(NeoSwapRelayStats)) return s.fail(NEOSWAP_RELAY_INVALID);
    *output = s.stats;
    return NEOSWAP_RELAY_OK;
}
PressureDiagnostics Backend::pressure_diagnostics() noexcept {
    if (!state_) return {};
    std::lock_guard<std::mutex> guard(state_->mutex);
    return state_->pressure_diagnostics;
}
int Backend::shutdown() noexcept {
    if (!state_) return NEOSWAP_RELAY_DISABLED;
    auto& s = *state_;
    std::lock_guard<std::mutex> guard(s.mutex);
    s.drain_unused();
    for (auto& slot : s.prepared) if (slot.token) {
        auto* object = s.object(slot.token);
        s.prepared_stats.prepared_bytes -= object->bytes;
        --s.prepared_stats.prepared_count;
        ++s.prepared_stats.reclaimed_total;
        s.finish_object(*object);
        slot = {};
    }
    if (s.stats.object_count) return s.fail(NEOSWAP_RELAY_BUSY);
    s.closing = true;
    s.stats.enabled_owner_mask = 0;
    int result = NEOSWAP_RELAY_OK;
    for (auto& entry : s.entries) if (entry.port) {
        const int current = s.cleanup(entry);
        if (current) result = current;
    }
    s.recount_entries();
    if (result) return result;
    s.closing = false;
    s.stats.pressure_raised = 0;
    s.direct_allowance = 0;
    for (auto& demand : s.demands) demand.count.store(0, std::memory_order_relaxed);
    return s.success();
}

namespace {
#if defined(__APPLE__)
static_assert(sizeof(vm_address_t) == sizeof(std::uintptr_t),
    "NeoSwap relay requires native-width vm_address_t");
static_assert(sizeof(vm_size_t) >= sizeof(std::uint64_t),
    "NeoSwap relay requires vm_size_t to hold 64-bit relay sizes");
static_assert(sizeof(vm_offset_t) >= sizeof(std::uint64_t),
    "NeoSwap relay requires vm_offset_t to hold 64-bit relay offsets");

int retain(void*, std::uint32_t entry) {
    return mach_port_mod_refs(mach_task_self(), entry, MACH_PORT_RIGHT_SEND, 1);
}
int drop(void*, std::uint32_t entry) { return mach_port_deallocate(mach_task_self(), entry); }
int map_pages(void*, std::uint32_t entry, std::uint64_t offset, std::uint64_t bytes,
              std::uintptr_t target, std::uint32_t protection, std::uintptr_t* mapped) {
    vm_address_t address = static_cast<vm_address_t>(target);
    const auto result = vm_map(mach_task_self(), &address, static_cast<vm_size_t>(bytes),
        target ? 0 : static_cast<vm_address_t>(alignment - 1),
        target ? VM_FLAGS_FIXED | VM_FLAGS_OVERWRITE : VM_FLAGS_ANYWHERE, entry,
        static_cast<vm_offset_t>(offset), FALSE, static_cast<vm_prot_t>(protection),
        VM_PROT_READ | VM_PROT_WRITE, VM_INHERIT_NONE);
    if (result == KERN_SUCCESS) *mapped = static_cast<std::uintptr_t>(address);
    return result;
}
int unmap_pages(void*, std::uintptr_t address, std::uint64_t bytes, bool fixed) {
    if (!fixed) return vm_deallocate(mach_task_self(), static_cast<vm_address_t>(address),
        static_cast<vm_size_t>(bytes));
    vm_address_t destination = static_cast<vm_address_t>(address);
    // One atomic replacement preserves ownership of the reserved address even
    // if another thread allocates VM regions concurrently with guest teardown.
    return vm_map(mach_task_self(), &destination, static_cast<vm_size_t>(bytes), 0,
        VM_FLAGS_FIXED | VM_FLAGS_OVERWRITE, MEMORY_OBJECT_NULL, 0, FALSE,
        VM_PROT_NONE, VM_PROT_READ | VM_PROT_WRITE, VM_INHERIT_NONE);
}
int zero_pages(void*, std::uintptr_t address, std::uint64_t bytes) {
    if (madvise(reinterpret_cast<void*>(address), static_cast<std::size_t>(bytes), MADV_ZERO) == 0)
        return 0;
    return errno;
}
std::uint64_t headroom(void*) {
    donation::SystemHeadroom sample;
    if (!donation::system_headroom(sample)) return 0;
    if (sample.pressure == donation::MemoryPressure::warning ||
        sample.pressure == donation::MemoryPressure::critical) return 0;
    return sample.usable_bytes;
}
const Operations system_operations{retain, drop, map_pages, unmap_pages, zero_pages, headroom};
#else
const Operations system_operations{}; // No fabricated portable donation.
#endif
} // namespace
#if defined(NEOSWAP_TESTING)
namespace {
const Operations* test_operations = nullptr;
void* test_context = nullptr;
}
void install_operations_for_test(const Operations& operations, void* context) noexcept {
    static Operations retained;
    retained = operations;
    test_operations = &retained;
    test_context = context;
}
Backend& backend() noexcept {
    static Backend instance(test_operations ? *test_operations : system_operations, test_context);
    return instance;
}
#else
Backend& backend() noexcept { static Backend instance(system_operations); return instance; }
#endif
int configure(std::uint32_t mask, std::uint64_t limit) noexcept { return backend().configure(mask, limit); }
int set_owner_quota(std::uint32_t owner, std::uint64_t bytes) noexcept { return backend().set_owner_quota(owner, bytes); }
int adopt(std::uint32_t entry, std::uint64_t bytes, std::int32_t pid, std::uint64_t generation) noexcept {
    return backend().adopt(entry, bytes, pid, generation);
}
void set_pressure(bool raised) noexcept { backend().set_pressure(raised); }
int shutdown() noexcept { return backend().shutdown(); }
int collect() noexcept { return backend().collect(); }
int maintain_guest_pool(std::uint64_t target, std::uint64_t growth) noexcept {
    return backend().maintain_guest_pool(target, growth);
}
void set_direct_guest_allowance(std::uint64_t bytes) noexcept { backend().set_direct_guest_allowance(bytes); }
void set_demand_signal(void (*callback)(void*), void* context) noexcept {
    backend().set_demand_signal(callback, context);
}
} // namespace neostation::relay

extern "C" const NeoSwapRelayAPI* NeoSwap_GetRelayAPI(std::uint32_t abi) {
    static const NeoSwapRelayAPI api{sizeof(NeoSwapRelayAPI), NEOSWAP_RELAY_ABI,
        [](std::uint32_t owner, std::uint64_t bytes, std::uint64_t* token) {
            return neostation::relay::backend().create(owner, bytes, token);
        },
        [](std::uint64_t token, void* target, std::uint32_t protection, void** mapped) {
            return neostation::relay::backend().map(token, target, protection, mapped);
        },
        [](std::uint64_t token, void* address) { return neostation::relay::backend().unmap(token, address); },
        [](std::uint64_t token) { return neostation::relay::backend().release(token); },
        [](std::uint32_t owner) { return neostation::relay::backend().enabled(owner); },
        [](NeoSwapRelayStats* stats) { return neostation::relay::backend().snapshot(stats); },
        [](std::uint64_t token) { return neostation::relay::backend().retire(token); }};
    return abi == NEOSWAP_RELAY_ABI ? &api : nullptr;
}

extern "C" const NeoSwapPreparedRelayAPI* NeoSwap_GetPreparedRelayAPI(std::uint32_t abi) {
    static const NeoSwapPreparedRelayAPI api{sizeof(NeoSwapPreparedRelayAPI), NEOSWAP_PREPARED_RELAY_ABI,
        [](std::uint32_t owner, std::uint64_t bytes, std::uint64_t* token) {
            return neostation::relay::backend().try_acquire_prepared(owner, bytes, token);
        },
        [](std::uint64_t token) {
            return neostation::relay::backend().return_unused_prepared(token);
        },
        [](NeoSwapPreparedRelayStats* stats) {
            return neostation::relay::backend().prepared_snapshot(stats);
        }};
    return abi == NEOSWAP_PREPARED_RELAY_ABI ? &api : nullptr;
}

extern "C" const NeoSwapDirectRelayAPI* NeoSwap_GetDirectRelayAPI(std::uint32_t abi) {
    static const NeoSwapDirectRelayAPI api{sizeof(NeoSwapDirectRelayAPI), NEOSWAP_DIRECT_RELAY_ABI,
        [](std::uint32_t owner, std::uint64_t bytes, std::uint64_t* token) {
            return neostation::relay::backend().try_create_guest(owner, bytes, token);
        },
        [](NeoSwapDirectRelayStats* stats) {
            return neostation::relay::backend().direct_snapshot(stats);
        }};
    return abi == NEOSWAP_DIRECT_RELAY_ABI ? &api : nullptr;
}
