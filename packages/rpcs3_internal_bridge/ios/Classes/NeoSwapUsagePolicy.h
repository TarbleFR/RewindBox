#pragma once
#include <string_view>
#include <cmath>
#include <neo_swap/NeoSwapClientStats.h>
#include <neo_swap/NeoSwapHost.h>
#include <neo_swap/NeoSwapDonationMetrics.h>

// Live buffers take precedence over a lost backend. Readiness comes from a
// configured file owner or verified donor pages, never a virtual reservation.
enum class NeoSwapUsageStatus {
    unavailable, clientUnavailable, disabled, waiting, small,
    rejected, released, active
};
inline bool NeoSwapDonorMeasured(const NeoSwapHostStats* host) noexcept {
    return host && host->donation_state == 2 && host->donor_count && host->donor_prepared_bytes;
}
inline NeoSwapUsageStatus NeoSwapUsage(uint64_t live, const NeoSwapClientStats* client,
                                     const NeoSwapHostStats* host) noexcept {
    if (live) return NeoSwapUsageStatus::active;
    if (!host) return NeoSwapUsageStatus::unavailable;
    const bool fileReady = host->file_ready_owner_mask & (1u << NEOSWAP_RPCS3);
    const bool donorReady = NeoSwapDonorMeasured(host);
    if (!fileReady && !donorReady) return NeoSwapUsageStatus::unavailable;
    if (!client) return NeoSwapUsageStatus::clientUnavailable;
    if (client->eligible_attempts && client->last_result != NEOSWAP_OK)
        return NeoSwapUsageStatus::rejected;
    if (client->successful_allocations) return NeoSwapUsageStatus::released;
    if (client->disabled) return NeoSwapUsageStatus::disabled;
    if (client->missing_api) return NeoSwapUsageStatus::clientUnavailable;
    if (!client->eligible_attempts && client->skipped_small) return NeoSwapUsageStatus::small;
    return NeoSwapUsageStatus::waiting;
}

// Two independent measures: the app's kernel footprint and backing currently
// donated to RPCS3. Prepared capacity, idle shelves, files and aliases never
// enter donated bytes. Active backing is not a physical-residency measurement.
struct NeoSwapMemoryGraphPoint {
    uint64_t footprint = 0;
    uint64_t donated = 0;
    bool footprintValid = false;
    bool donatedValid = false;
};
inline NeoSwapMemoryGraphPoint NeoSwapMemoryGraph(const NeoSwapHostStats* host,
    uint64_t relayGuestPublished, bool relayGuestMeasured, uint64_t processFootprint) noexcept {
    NeoSwapMemoryGraphPoint point{};
    // phys_footprint is already the app's kernel charge. Never add or subtract
    // shared backing here, even when the independent donation sample is absent.
    point.footprint = processFootprint;
    point.footprintValid = processFootprint != 0;
    const auto donation = neostation::donation_metrics::active(host, relayGuestPublished, relayGuestMeasured);
    point.donatedValid = donation.valid;
    point.donated = donation.valid ? donation.total_bytes : 0;
    return point;
}
constexpr double NeoSwapDecimalGB(uint64_t bytes) noexcept {
    return static_cast<double>(bytes) / 1000000000.0;
}

// Zero FPS is a valid stalled-frame sample, not an unavailable measurement.
inline bool NeoSwapFPSValid(double fps, uint32_t validFields) noexcept {
    return (validFields & 1U) && std::isfinite(fps) && fps >= 0.0;
}

inline bool NeoSwapCPUBufferTitle(std::string_view title) noexcept {
    return title == "BCES00510" || title == "BCES00799" || title == "BCUS98111" ||
        title == "BCJS37001" || title == "BCAS25003" || title == "BCKS15003";
}
