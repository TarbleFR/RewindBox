// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <algorithm>
#include <array>
#include <cstdint>
#include <mutex>

// One host coordinator for all PPU/SPU workers. Estimates reserve room for
// future work; they are never reported as physical RAM consumed or saved.
namespace neostation::compiler {
class budget {
    std::mutex mutex;
    struct lease { std::uint64_t id = 0, bytes = 0; };
    std::array<lease, 64> leases{};
    std::uint64_t next_id = 1, promised = 0;
    unsigned active = 0;
    bool foreground = true, constrained = true;
    std::uint64_t reserve = 256ull * 1024 * 1024;
public:
    void update(bool front, bool pressure_or_thermal, std::uint64_t reserve_bytes) {
        std::lock_guard lock(mutex);
        foreground = front; constrained = pressure_or_thermal; reserve = reserve_bytes;
    }
    std::uint64_t acquire(std::uint64_t estimate, std::uint64_t headroom) {
        std::lock_guard lock(mutex);
        if (!foreground || active >= 3 || (active && constrained)) return 0;
        const auto room = headroom > reserve ? headroom - reserve : 0;
        // One oversized job must advance exclusively. Never cancel LLVM in flight.
        if (estimate > UINT64_MAX - promised || (active && (promised >= room || estimate > room - promised))) return 0;
        for (auto& lease : leases) if (!lease.id) {
            if (!next_id) ++next_id;
            lease = {next_id++, estimate};
            promised += estimate;
            ++active; return lease.id;
        }
        return 0;
    }
    void release(std::uint64_t ticket) {
        std::lock_guard lock(mutex);
        for (auto& lease : leases) if (lease.id == ticket && ticket) {
            promised -= lease.bytes; lease = {}; --active; return;
        }
    }
    std::uint64_t reserved() { std::lock_guard lock(mutex); return promised; }
};
}
