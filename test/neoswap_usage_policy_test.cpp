#include "NeoSwapUsagePolicy.h"
#include <cassert>
#include <cstdio>

int main() {
  for (auto title : {"BCES00510", "BCES00799", "BCUS98111", "BCJS37001", "BCAS25003", "BCKS15003"})
    assert(NeoSwapCPUBufferTitle(title));
  assert(!NeoSwapCPUBufferTitle("BLES00113") && !NeoSwapCPUBufferTitle("BCES00510-extra") &&
         !NeoSwapCPUBufferTitle(""));
  assert(NeoSwapFPSValid(60.0, 1));
  assert(NeoSwapFPSValid(0.0, 1));
  assert(NeoSwapFPSValid(120.0, 1));
  assert(!NeoSwapFPSValid(60.0, 0));
  assert(!NeoSwapFPSValid(-1.0, 1));
  assert(!NeoSwapFPSValid(NAN, 1));
  assert(!NeoSwapFPSValid(INFINITY, 1));
  {
    NeoSwapHostStats graphHost{};
    graphHost.active_donation_valid = 1;
    graphHost.owner_donated_active_bytes[NEOSWAP_RPCS3] = 51380224;
    graphHost.owner_relay_active_bytes[NEOSWAP_RPCS3] = 268435456;
    constexpr uint64_t guest = 1020788736, footprint = 2264317952;
    constexpr uint64_t donated = guest + 268435456 + 51380224;
    auto point = NeoSwapMemoryGraph(&graphHost, guest, true, footprint);
    assert(point.footprintValid && point.footprint == footprint);
    assert(point.donatedValid && point.donated == donated);
    // Prepared capacity, unrelated owners and aggregate backend counters must
    // not become donated bytes. The relay aggregate can include idle shelves.
    graphHost.donor_prepared_bytes = UINT64_MAX;
    graphHost.reserved_virtual_bytes = UINT64_MAX;
    graphHost.donor_target_bytes = UINT64_MAX;
    graphHost.donor_footprint_bytes = UINT64_MAX;
    graphHost.relay_loan_live_bytes = UINT64_MAX;
    graphHost.owner_relay_live_bytes[NEOSWAP_RPCS3] = UINT64_MAX;
    graphHost.owner_donated_live_bytes[NEOSWAP_RPCS3] = UINT64_MAX;
    graphHost.owner_donated_active_bytes[NEOSWAP_ARMSX2] = UINT64_MAX;
    graphHost.owner_relay_active_bytes[NEOSWAP_ARMSX2] = UINT64_MAX;
    point = NeoSwapMemoryGraph(&graphHost, guest, true, footprint);
    assert(point.donatedValid && point.donated == donated && point.footprint == footprint);
    // The app's footprint never absorbs or subtracts the shared allocation.
    const auto moreGuest = NeoSwapMemoryGraph(&graphHost, guest + 65536, true, footprint);
    assert(moreGuest.donated == donated + 65536 && moreGuest.footprint == footprint);
    // Missing guest telemetry means unknown donation, not zero or an estimate
    // from the old total relay counter. Footprint validity is independent.
    const auto unmeasured = NeoSwapMemoryGraph(&graphHost, guest, false, footprint);
    assert(!unmeasured.donatedValid && !unmeasured.donated);
    assert(unmeasured.footprintValid && unmeasured.footprint == footprint);
    const auto hostless = NeoSwapMemoryGraph(nullptr, guest, true, footprint);
    assert(!hostless.donatedValid && !hostless.donated);
    assert(hostless.footprintValid && hostless.footprint == footprint);
    const auto noFootprint = NeoSwapMemoryGraph(&graphHost, guest, true, 0);
    assert(noFootprint.donatedValid && noFootprint.donated == donated && !noFootprint.footprintValid);
    // Contention invalidates only donation, without waiting or showing zero.
    graphHost.active_donation_valid = 0;
    const auto busy = NeoSwapMemoryGraph(&graphHost, guest, true, footprint);
    assert(!busy.donatedValid && !busy.donated);
    assert(busy.footprintValid && busy.footprint == footprint);
    graphHost.active_donation_valid = 1;
    // A backend becoming unavailable does not erase donations still owned by
    // RPCS3. Their counters fall only when the corresponding loans are retired.
    graphHost.donation_state = 3;
    assert(NeoSwapMemoryGraph(&graphHost, guest, true, 1).donated == donated);
    // Overflow is an invalid sample, never a saturated successful measurement.
    graphHost.owner_relay_active_bytes[NEOSWAP_RPCS3] = UINT64_MAX;
    const auto hostOverflow = NeoSwapMemoryGraph(&graphHost, 0, true, footprint);
    assert(!hostOverflow.donatedValid && !hostOverflow.donated && hostOverflow.footprint == footprint);
    graphHost.owner_relay_active_bytes[NEOSWAP_RPCS3] = 1;
    graphHost.owner_donated_active_bytes[NEOSWAP_RPCS3] = 0;
    assert(!NeoSwapMemoryGraph(&graphHost, UINT64_MAX, true, footprint).donatedValid);
    graphHost.owner_relay_active_bytes[NEOSWAP_RPCS3] = 0;
    const auto maximum = NeoSwapMemoryGraph(&graphHost, UINT64_MAX, true, UINT64_MAX);
    assert(maximum.donatedValid && maximum.donated == UINT64_MAX);
    assert(maximum.footprintValid && maximum.footprint == UINT64_MAX);
    assert(std::isfinite(NeoSwapDecimalGB(maximum.donated)));
    assert(NeoSwapDecimalGB(1000000000) == 1.0);
    assert(NeoSwapDecimalGB(500000000) == 0.5);
    graphHost = {};
    graphHost.active_donation_valid = 1;
    graphHost.donor_prepared_bytes = 8ULL << 30;
    graphHost.reserved_virtual_bytes = 8ULL << 30;
    point = NeoSwapMemoryGraph(&graphHost, 0, true, 0);
    assert(point.donatedValid && !point.donated && !point.footprintValid);
    assert(!NeoSwapMemoryGraph(&graphHost, 0, false, 0).donatedValid);
  }
  NeoSwapHostStats host = {};
  NeoSwapClientStats client = {};
  assert(!NeoSwapDonorMeasured(nullptr));
  assert(!NeoSwapDonorMeasured(&host));
  assert(NeoSwapUsage(0, &client, nullptr) == NeoSwapUsageStatus::unavailable);
  assert(NeoSwapUsage(0, &client, &host) == NeoSwapUsageStatus::unavailable);
  host.reserved_virtual_bytes = 8ULL << 30;
  host.reservation_result = NEOSWAP_IO;
  assert(NeoSwapUsage(0, &client, &host) == NeoSwapUsageStatus::unavailable);
  host.reservation_result = NEOSWAP_OK;
  // A quota or an address-space count cannot establish allocator readiness.
  assert(NeoSwapUsage(0, &client, &host) == NeoSwapUsageStatus::unavailable);
  host.file_ready_owner_mask = 1u << NEOSWAP_ARMSX2;
  assert(NeoSwapUsage(0, &client, &host) == NeoSwapUsageStatus::unavailable);
  host.file_ready_owner_mask = 1u << NEOSWAP_RPCS3;
  host.reserved_virtual_bytes = 0;
  host.reservation_result = NEOSWAP_MAPPING;
  // Zero VA is normal. The last operation's failure does not disable a
  // configured fallback owner; actual client counters describe that request.
  assert(NeoSwapUsage(0, nullptr, &host) == NeoSwapUsageStatus::clientUnavailable);
  assert(NeoSwapUsage(0, &client, &host) == NeoSwapUsageStatus::waiting);
  client.skipped_small = 123;
  assert(NeoSwapUsage(0, &client, &host) == NeoSwapUsageStatus::small);
  client.missing_api = 1;
  assert(NeoSwapUsage(0, &client, &host) == NeoSwapUsageStatus::clientUnavailable);
  client.disabled = 1;
  assert(NeoSwapUsage(0, &client, &host) == NeoSwapUsageStatus::disabled);
  client.eligible_attempts = 1;
  client.failed_allocations = 1;
  client.last_result = NEOSWAP_IO;
  assert(NeoSwapUsage(0, &client, &host) == NeoSwapUsageStatus::rejected);
  client.successful_allocations = 1;
  assert(NeoSwapUsage(0, &client, &host) == NeoSwapUsageStatus::rejected);
  client.last_result = NEOSWAP_OK;
  assert(NeoSwapUsage(0, &client, &host) == NeoSwapUsageStatus::released);
  assert(NeoSwapUsage(1ULL << 20, &client, &host) == NeoSwapUsageStatus::active);
  assert(NeoSwapUsage(1ULL << 20, nullptr, &host) == NeoSwapUsageStatus::active);
  assert(NeoSwapUsage(1ULL << 20, nullptr, nullptr) == NeoSwapUsageStatus::active);
  host.file_ready_owner_mask = 0;
  host.donation_state = 1;
  host.donor_prepared_bytes = 64ULL << 20;
  host.donor_count = 1;
  assert(NeoSwapUsage(0, &client, &host) == NeoSwapUsageStatus::unavailable);
  host.donation_state = 2;
  assert(NeoSwapDonorMeasured(&host));
  client = {};
  assert(NeoSwapUsage(0, &client, &host) == NeoSwapUsageStatus::waiting);
  assert(NeoSwapUsage(1ULL << 20, &client, &host) == NeoSwapUsageStatus::active);
  host.donor_count = 0;
  assert(NeoSwapUsage(0, &client, &host) == NeoSwapUsageStatus::unavailable);
  host.donor_count = 1;
  host.donor_prepared_bytes = 0;
  assert(NeoSwapUsage(0, &client, &host) == NeoSwapUsageStatus::unavailable);
  host.donor_prepared_bytes = 64ULL << 20;
  host.donation_state = 3;
  assert(!NeoSwapDonorMeasured(&host));
  assert(NeoSwapUsage(0, &client, &host) == NeoSwapUsageStatus::unavailable);
  assert(NeoSwapUsage(1ULL << 20, &client, &host) == NeoSwapUsageStatus::active);
  host.file_ready_owner_mask = 1u << NEOSWAP_RPCS3;
  assert(NeoSwapUsage(0, &client, &host) == NeoSwapUsageStatus::waiting);
  puts("PASS: app footprint and active donated backing stay independent; unknown samples and overflow rejected; idle capacity and other owners excluded; live buffers take precedence; configured RPCS3 file owner or verified donors establish readiness with zero virtual reserve; missing, rejected, small, released and disabled states remain distinct");
}
