// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "NeoSwap.h"
#include "NeoSwapHost.h"
#include <cstdint>

namespace neostation::donation {
// Called on the serial donor-maintenance queue. Reconsider a blocked demand
// after every idle tick so a newly queued smaller buffer can use the available
// budget. Once a helper is preparing a chunk, keep its sequence until the
// authenticated result is acknowledged or refused; a late result must never
// acknowledge a different demand.
inline int refresh_idle_demand(NeoSwapDonationDemand& current,
                              std::uint64_t pending_chunks) noexcept {
    if (pending_chunks) return NEOSWAP_OK;
    NeoSwapDonationDemand next{};
    const int result = NeoSwap_ClaimDonationDemand(&next);
    if (result == NEOSWAP_OK) current = next;
    return result;
}
} // namespace neostation::donation
