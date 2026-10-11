// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "NeoSwapHost.h"

#ifdef __cplusplus
namespace neostation::donation_metrics {
// Active backing handed to RPCS3, not pool capacity, resident RAM or a measured
// reduction of TASK_VM_INFO.phys_footprint. Count guest objects only after their
// first successful map and before retirement. Count host loans through the
// broker's active RPCS3 counters, excluding pending releases, unused shelves
// and files. A busy broker leaves donation unavailable; it does not report zero.
struct Donation {
    uint64_t guest_bytes = 0;
    uint64_t host_bytes = 0;
    uint64_t total_bytes = 0;
    bool valid = false;
};

inline Donation active(const NeoSwapHostStats* host, uint64_t guestPublished,
                       bool guestMeasured) noexcept {
    Donation result{};
    if (!host || !host->active_donation_valid || !guestMeasured) return result;
    const auto relay = host->owner_relay_active_bytes[NEOSWAP_RPCS3];
    const auto donor = host->owner_donated_active_bytes[NEOSWAP_RPCS3];
    if (relay > UINT64_MAX - donor) return result;
    const auto loans = relay + donor;
    if (guestPublished > UINT64_MAX - loans) return result;
    result.guest_bytes = guestPublished;
    result.host_bytes = loans;
    result.total_bytes = guestPublished + loans;
    result.valid = true;
    return result;
}
} // namespace neostation::donation_metrics
#endif
