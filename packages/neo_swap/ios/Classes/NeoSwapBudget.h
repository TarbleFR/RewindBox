// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <cstdint>

// NeoSwap global memory budget: one measured-resource policy that decides how
// much memory outside the host process footprint RPCS3 may hold, which backing
// serves it (guest relay, host relay loans, donors, files, storage), and when
// the storage tier should start archiving cold data.
//
// This header is pure policy. It performs no kernel call, allocation or I/O,
// so the exact decision table is executed by portable sanitized tests. The
// plugin samples the inputs on its serial diagnostics timer and applies the
// decision to the broker, the relay service, the donor manager and storage.
//
// Units: every *_bytes field is a byte count. Capacities are retained
// VM-object capacity, never resident physical RAM. "Mobilized" bytes are live
// backing intervals charged outside the host footprint (relay objects whose
// creator exited, donor-owned purgeable objects), not pages proven resident.
//
// Build434 adds the measured jetsam envelope of the host process: the limit
// estimate (footprint + headroom, session high-water mark), its safety
// reserve, the allocatable share and the remaining host room. The envelope
// slows the shared growth grant and asks the storage tier to archive early;
// a backgrounded application is treated like pressure. It never revokes a
// live loan and never claims a kernel limit the kernel did not publish.
namespace neostation::budget {
constexpr std::uint64_t MiB = 1024ULL * 1024;
constexpr std::uint64_t GiB = 1024ULL * MiB;

enum class Pressure : std::uint32_t { unobserved = 0, normal = 1, warning = 2, critical = 3 };
enum class State : std::uint32_t {
    idle = 0,      // no RPCS3 session: nothing grows, idle reserves retire
    warming = 1,   // session active, relay not ready: donors provide the floor
    growing = 2,   // measured room available: new host loans and donor growth
    holding = 3,   // little room: live loans retained, no new backing
    shrinking = 4, // below the operational reserve: storage tier archives cold data
    pressure = 5,  // kernel/dispatch pressure: fail closed, retain live loans
};

struct Inputs {
    bool session_active = false;
    std::uint64_t compiler_working_set_estimate_bytes = 0;
    std::uint64_t physical_bytes = 0;
    // TASK_VM_INFO.phys_footprint of the host and os_proc_available_memory().
    // Process ledger. phys_footprint is exported for display and ratios only:
    // relay and donor pages live outside it. os_proc_available_memory is the
    // process jetsam headroom; below the operational reserve it requests the
    // storage tier to archive cold data, which does reduce the footprint.
    std::uint64_t host_footprint_bytes = 0;
    bool host_footprint_valid = false;
    std::uint64_t host_available_bytes = 0;
    bool host_available_valid = false;
    // Application state. iOS applies a much lower inactive limit to a
    // backgrounded process: growth closes and cold data archives before the
    // kernel decides. Foreground is the default so older samplers that do not
    // observe UIApplication keep their behavior.
    bool foreground = true;
    // donation::system_headroom(): kernel free/purgeable sample minus margin,
    // or the memorystatus estimate. Not a process limit.
    std::uint64_t system_usable_bytes = 0;
    bool system_valid = false;
    Pressure system_pressure = Pressure::unobserved;
    bool dispatch_warning = false;
    bool thermal_serious = false;
    // Guest page relay: retained named-object capacity and live backing.
    bool relay_ready = false;
    std::uint64_t relay_capacity_bytes = 0;
    std::uint64_t relay_guest_live_bytes = 0;
    std::uint64_t relay_host_live_bytes = 0;
    // Prepared guest tokens already belong to guest_live. Until their first
    // publication they can still fault pages without another budget decision,
    // so their promise also reserves measured system room (not relay capacity
    // a second time). Demand is the unfilled, bounded utility-worker queue.
    std::uint64_t relay_guest_prepared_bytes = 0;
    std::uint64_t relay_guest_unpublished_bytes = 0;
    std::uint64_t relay_guest_demand_bytes = 0;
    // Donor pool: verified prepared bytes and active loans.
    bool donors_available = false;
    std::uint64_t donor_prepared_bytes = 0;
    std::uint64_t donor_live_bytes = 0;
    // Smallest real contiguous request, and helper IPC already committed but
    // not acknowledged. The latter may not yet appear in the kernel sample.
    std::uint64_t donor_demand_bytes = 0;
    std::uint64_t donor_preparing_bytes = 0;
    // File fallback and storage tier (live archived bytes, not cumulative).
    std::uint64_t file_live_bytes = 0;
    std::uint64_t storage_archived_live_bytes = 0;
};

struct Decision {
    State state = State::idle;
    std::uint64_t operational_reserve_bytes = 0;
    std::uint64_t growth_room_bytes = 0;
    std::uint64_t guest_reserve_bytes = 0;
    std::uint64_t guest_unpublished_reserved_bytes = 0;
    std::uint64_t bounded_growth_grant_bytes = 0;
    std::uint64_t pending_reserved_bytes = 0;
    std::uint64_t guest_prepare_grant_bytes = 0;
    // Build 444: direct guest admission allowed between two utility passes.
    // A promise over the same measured room as the other grants (a created
    // object is counted in relay_guest_live_bytes by the next sample), never
    // above the ramped grant or the free relay capacity, zero when growth is
    // not admitted, under pressure, in the background or without a relay.
    std::uint64_t direct_guest_allowance_bytes = 0;
    std::uint64_t relay_growth_grant_bytes = 0;
    // Relay host loans: ceiling of live bytes the broker may hold for RSX CPU
    // data, host-visible Vulkan buffers and video frames. Existing loans are
    // never revoked; a ceiling below the live value only refuses new loans.
    std::uint64_t host_loan_quota_bytes = 0;
    bool host_loans_admitted = false;
    bool small_cpu_admitted = false;
    // Donor manager policy: floor and reserve for adaptive_donation_target().
    std::uint64_t donor_floor_bytes = 0;
    std::uint64_t donor_reserve_bytes = 0;
    // NEW donor room, excluding outstanding IPC. Requested chunks take an
    // exact share before speculative host-loan growth; without a request the
    // previous fallback policy remains. One sample never grants room twice.
    std::uint64_t donor_room_bytes = 0;
    bool donor_growth_admitted = false;
    // Storage tier: prefer archiving cold owned data while this is set.
    bool storage_shrink_requested = false;
    // Measured jetsam envelope of the host process (Build434). The kernel
    // never publishes its per-process limit; footprint plus the headroom that
    // os_proc_available_memory() reports approximates it at every sample.
    // The session high-water mark absorbs the jitter of two readings taken a
    // few microseconds apart and never grows past the physical memory. These
    // bytes are an estimate for policy and display, not a kernel guarantee.
    std::uint64_t host_limit_estimate_bytes = 0;
    bool host_limit_valid = false;
    std::uint64_t host_safety_reserve_bytes = 0;
    // What the host process may still hold before its own reserve: the
    // "allocatable" figure of the maintainer's 7 GB goal, measured, not
    // assumed. Relay and donor pages are outside this envelope.
    std::uint64_t host_allocatable_bytes = 0;
    std::uint64_t host_room_bytes = 0;
    bool host_room_valid = false;
    // Growth ramp: the share of the bounded grant this decision may open.
    // Full while the room is comfortable, a quarter once the envelope is
    // close, nothing in the background or under pressure.
    std::uint32_t growth_ramp_percent = 0;
    std::uint64_t mobilized_bytes = 0;      // relay guest + relay host + donor live
    std::uint64_t neoswap_total_bytes = 0;  // mobilized + file fallback + archived
    const char* reason = "not_sampled";
};

constexpr std::uint64_t reserve_floor_bytes = 256 * MiB;
constexpr std::uint64_t reserve_ceiling_bytes = 768 * MiB;
constexpr std::uint64_t guest_reserve_floor_bytes = 1536 * MiB;
constexpr std::uint64_t growth_quantum_bytes = 64 * MiB;
// A sample may report several GiB free. Exposing all of it as a new quota at
// once permits a burst before the next pressure sample. Admit at most one
// maximum native donor block per decision, shared by relay and donor growth.
constexpr std::uint64_t maximum_growth_grant_bytes = 256 * MiB;
// Matches the prepared guest worker's bounded pass. A larger queued demand
// must not reserve room the worker cannot consume in this decision.
constexpr std::uint64_t maximum_guest_prepare_grant_bytes = 32 * MiB;
constexpr std::uint64_t maximum_guest_prepared_bytes = 64 * MiB;
// Hysteresis of the growing state: admission starts with one growth quantum
// of measured room and ends only below half of it, so sample jitter or the
// bytes a maintenance pass hands back cannot flip the state every tick.
constexpr std::uint64_t growth_hold_quantum_bytes = growth_quantum_bytes / 2;
constexpr std::uint64_t small_cpu_minimum_room_bytes = 128 * MiB;
constexpr std::uint64_t legacy_donor_floor_bytes = 512 * MiB;
constexpr std::uint64_t legacy_donor_reserve_bytes = 128 * MiB;
constexpr std::uint64_t relay_donor_reserve_bytes = 64 * MiB;
// Host jetsam envelope (Build434): the process keeps this much of its
// measured limit unused. A single scene transition of God of War III was
// measured to allocate 3 GiB of VRAM in 15 s, so the reserve is sized to one
// bounded burst: a sixteenth of the limit, never under 384 MiB nor over 1 GiB.
constexpr std::uint64_t host_reserve_floor_bytes = 384 * MiB;
constexpr std::uint64_t host_reserve_ceiling_bytes = 1024 * MiB;
// The ramp halves the bounded grant below two reserves of host room and
// quarters it below one; the host room never admits relay/donor growth by
// itself, it only slows it so the envelope cannot be crossed by the host's
// own ordinary allocations between two samples.
constexpr std::uint32_t growth_ramp_full_percent = 100;
constexpr std::uint32_t growth_ramp_half_percent = 50;
constexpr std::uint32_t growth_ramp_quarter_percent = 25;

constexpr std::uint64_t clamp(std::uint64_t value, std::uint64_t low, std::uint64_t high) noexcept {
    return value < low ? low : value > high ? high : value;
}
constexpr std::uint64_t saturating_add(std::uint64_t a, std::uint64_t b) noexcept {
    return b > UINT64_MAX - a ? UINT64_MAX : a + b;
}
constexpr std::uint64_t operational_reserve(std::uint64_t physical_bytes, bool raised) noexcept {
    const auto base = clamp(physical_bytes / 16, reserve_floor_bytes, reserve_ceiling_bytes);
    return raised ? saturating_add(base, base) : base;
}
constexpr std::uint64_t host_safety_reserve(std::uint64_t limit_bytes) noexcept {
    return clamp(limit_bytes / 16, host_reserve_floor_bytes, host_reserve_ceiling_bytes);
}
// One sample's estimate of the process limit: footprint plus headroom, both
// read by the same tick. Zero when either reading is missing. Bounded by the
// physical memory when that figure is known: a limit cannot exceed the RAM.
constexpr std::uint64_t host_limit_sample(const Inputs& in) noexcept {
    if (!in.host_footprint_valid || !in.host_available_valid) return 0;
    const auto sum = saturating_add(in.host_footprint_bytes, in.host_available_bytes);
    return in.physical_bytes && sum > in.physical_bytes ? in.physical_bytes : sum;
}
constexpr std::uint32_t growth_ramp(std::uint64_t room, std::uint64_t reserve, bool foreground) noexcept {
    if (!foreground) return 0;
    if (room >= saturating_add(reserve, reserve)) return growth_ramp_full_percent;
    if (room >= reserve) return growth_ramp_half_percent;
    return growth_ramp_quarter_percent;
}
constexpr std::uint64_t ramped(std::uint64_t bytes, std::uint32_t percent) noexcept {
    return percent >= 100 ? bytes : bytes / 100 * percent + (bytes % 100) * percent / 100;
}

constexpr Decision decide(const Inputs& in, const Decision& previous) noexcept {
    Decision out{};
    out.mobilized_bytes = saturating_add(saturating_add(in.relay_guest_live_bytes, in.relay_host_live_bytes),
                                         in.donor_live_bytes);
    out.neoswap_total_bytes = saturating_add(saturating_add(out.mobilized_bytes, in.file_live_bytes),
                                             in.storage_archived_live_bytes);
    const bool os_pressure = in.dispatch_warning || in.system_pressure == Pressure::warning ||
                             in.system_pressure == Pressure::critical;
    out.operational_reserve_bytes = saturating_add(operational_reserve(in.physical_bytes, os_pressure || in.thermal_serious), in.compiler_working_set_estimate_bytes);
    // Measured host envelope: the session high-water mark of footprint plus
    // headroom. The previous decision carries the mark; a session start (no
    // previous estimate) takes the first valid sample as is.
    {
        const auto sample = host_limit_sample(in);
        const auto previous_limit = previous.host_limit_valid ? previous.host_limit_estimate_bytes : 0;
        const auto limit = sample > previous_limit ? sample : previous_limit;
        out.host_limit_estimate_bytes = limit;
        out.host_limit_valid = limit != 0;
        if (out.host_limit_valid) {
            out.host_safety_reserve_bytes = host_safety_reserve(limit);
            out.host_allocatable_bytes = limit > out.host_safety_reserve_bytes
                ? limit - out.host_safety_reserve_bytes : 0;
            if (in.host_footprint_valid) {
                out.host_room_bytes = out.host_allocatable_bytes > in.host_footprint_bytes
                    ? out.host_allocatable_bytes - in.host_footprint_bytes : 0;
                out.host_room_valid = true;
            }
        }
    }
    // The envelope slows growth; the system sample still decides admission.
    out.growth_ramp_percent = out.host_room_valid
        ? growth_ramp(out.host_room_bytes, out.host_safety_reserve_bytes, in.foreground)
        : (in.foreground ? growth_ramp_full_percent : 0);
    // Guest objects keep a reserved share of the relay capacity even when host
    // loans are hungry: RPCS3 guest allocations must never fall back to files
    // because host data consumed the whole relay.
    out.guest_reserve_bytes = in.relay_guest_live_bytes > guest_reserve_floor_bytes
        ? in.relay_guest_live_bytes : guest_reserve_floor_bytes;
    if (!in.session_active) {
        out.state = State::idle;
        out.reason = "no_active_rpcs3_session";
        return out;
    }
    out.guest_unpublished_reserved_bytes = in.relay_guest_unpublished_bytes > in.relay_guest_prepared_bytes
        ? in.relay_guest_unpublished_bytes : in.relay_guest_prepared_bytes;
    if (in.system_valid && in.system_usable_bytes > out.operational_reserve_bytes) {
        const auto room = in.system_usable_bytes - out.operational_reserve_bytes;
        out.growth_room_bytes = room > out.guest_unpublished_reserved_bytes
            ? room - out.guest_unpublished_reserved_bytes : 0;
    }
    if (os_pressure || !in.foreground) {
        // Background: iOS applies the inactive limit, far below the active
        // one measured here. Treat it exactly like pressure: fail closed,
        // retain every live loan, archive cold data, grow nothing.
        out.state = State::pressure;
        out.reason = !in.foreground ? "application_background"
            : in.dispatch_warning ? "dispatch_memory_pressure" : "kernel_memory_pressure";
        out.growth_ramp_percent = 0;
        out.host_loan_quota_bytes = in.relay_host_live_bytes; // retain, never grow
        out.storage_shrink_requested = true;
        out.donor_floor_bytes = 0;
        out.donor_reserve_bytes = 0;
        return out;
    }
    const std::uint64_t admission_room = previous.state == State::growing
        ? growth_hold_quantum_bytes : growth_quantum_bytes;
    // The bounded grant of this sample, slowed by the host envelope ramp. A
    // quarter grant below one host reserve still moves: the envelope is a
    // brake on the shared grant, never a second admission gate.
    const auto bounded_grant = ramped(out.growth_room_bytes < maximum_growth_grant_bytes
        ? out.growth_room_bytes : maximum_growth_grant_bytes, out.growth_ramp_percent);
    out.bounded_growth_grant_bytes = bounded_grant;
    out.pending_reserved_bytes = in.donor_preparing_bytes < bounded_grant
        ? in.donor_preparing_bytes : bounded_grant;
    auto remaining = bounded_grant - out.pending_reserved_bytes;
    const bool growth_admitted = in.system_valid && out.growth_room_bytes >= admission_room;
    if (in.relay_ready && growth_admitted) {
        const auto occupied = saturating_add(in.relay_guest_live_bytes, in.relay_host_live_bytes);
        const auto free = in.relay_capacity_bytes > occupied ? in.relay_capacity_bytes - occupied : 0;
        auto guest_grant = in.relay_guest_demand_bytes < maximum_guest_prepare_grant_bytes
            ? in.relay_guest_demand_bytes : maximum_guest_prepare_grant_bytes;
        const auto stock_room = maximum_guest_prepared_bytes > in.relay_guest_prepared_bytes
            ? maximum_guest_prepared_bytes - in.relay_guest_prepared_bytes : 0;
        if (guest_grant > stock_room) guest_grant = stock_room;
        if (guest_grant > remaining) guest_grant = remaining;
        if (guest_grant > free) guest_grant = free;
        out.guest_prepare_grant_bytes = guest_grant;
        remaining -= guest_grant;
        const auto promised_guest = saturating_add(in.relay_guest_live_bytes, guest_grant);
        if (promised_guest > out.guest_reserve_bytes) out.guest_reserve_bytes = promised_guest;
        // Guest data has priority over speculative host loans: the direct
        // allowance is the whole ramped grant, bounded by what the relay can
        // still back. It is not subtracted from `remaining` because it is
        // consumed only by actual guest allocations, which the next sample
        // sees in relay_guest_live_bytes.
        out.direct_guest_allowance_bytes = bounded_grant < free ? bounded_grant : free;
    }
    // Contiguous donor demand cannot use a partial grant. Prioritize a whole
    // queued chunk, including 1-16 MiB requests below the global hysteresis
    // threshold; that threshold applies to measured room, not chunk size.
    const auto requested_donor_grant = growth_admitted && !in.donor_preparing_bytes &&
        in.donor_demand_bytes <= remaining ? in.donor_demand_bytes : 0;
    remaining -= requested_donor_grant;
    const std::uint64_t relay_free_for_host = in.relay_capacity_bytes > out.guest_reserve_bytes
        ? in.relay_capacity_bytes - out.guest_reserve_bytes : 0;
    if (in.relay_ready) {
        // Grow only by measured room; a ceiling never exceeds what the relay
        // can still back after the guest reserve.
        const auto grant = remaining;
        const auto desired = saturating_add(in.relay_host_live_bytes, grant);
        out.host_loan_quota_bytes = desired < relay_free_for_host ? desired : relay_free_for_host;
        if (out.host_loan_quota_bytes < in.relay_host_live_bytes)
            out.host_loan_quota_bytes = in.relay_host_live_bytes;
        out.host_loans_admitted = growth_admitted &&
                                  out.host_loan_quota_bytes > in.relay_host_live_bytes;
    }
    // Donors are the fallback backing. While relay host loans are admitted the
    // pool keeps only a small reserve above its live loans, so no further
    // prepared pages are duplicated on top of relay capacity. Pages already
    // prepared stay with the session in normal operation; pressure/shrinking
    // withdraws completely idle donors, while every live loan stays valid.
    if (in.relay_ready && out.host_loans_admitted) {
        out.donor_floor_bytes = 0;
        out.donor_reserve_bytes = relay_donor_reserve_bytes;
    } else {
        out.donor_floor_bytes = legacy_donor_floor_bytes;
        out.donor_reserve_bytes = legacy_donor_reserve_bytes;
    }
    out.relay_growth_grant_bytes = out.host_loans_admitted && out.host_loan_quota_bytes > in.relay_host_live_bytes
        ? out.host_loan_quota_bytes - in.relay_host_live_bytes : 0;
    out.donor_room_bytes = requested_donor_grant + remaining - out.relay_growth_grant_bytes;
    out.donor_growth_admitted = growth_admitted && !in.donor_preparing_bytes &&
        (requested_donor_grant != 0 || out.donor_room_bytes >= admission_room);
    out.small_cpu_admitted = in.system_valid && in.system_usable_bytes >= small_cpu_minimum_room_bytes &&
        ((in.relay_ready && out.host_loans_admitted) || in.donors_available);
    const bool was_shrinking = previous.state == State::shrinking || previous.state == State::pressure;
    const bool below_reserve = in.system_valid && in.system_usable_bytes < out.operational_reserve_bytes;
    const bool recovered = in.system_valid &&
        in.system_usable_bytes >= saturating_add(out.operational_reserve_bytes, out.operational_reserve_bytes / 2);
    if (!in.system_valid) {
        out.state = State::holding;
        out.reason = "system_headroom_unknown";
        out.host_loans_admitted = false;
        out.donor_growth_admitted = false;
        out.donor_room_bytes = 0;
        out.guest_prepare_grant_bytes = 0;
        out.direct_guest_allowance_bytes = 0;
        out.relay_growth_grant_bytes = 0;
        out.small_cpu_admitted = false;
        out.host_loan_quota_bytes = in.relay_host_live_bytes;
    } else if (below_reserve || (was_shrinking && !recovered)) {
        out.state = State::shrinking;
        out.reason = below_reserve ? "system_room_below_operational_reserve" : "shrink_hysteresis";
        out.storage_shrink_requested = true;
        out.host_loans_admitted = false;
        out.donor_growth_admitted = false;
        out.donor_room_bytes = 0;
        out.guest_prepare_grant_bytes = 0;
        out.direct_guest_allowance_bytes = 0;
        out.relay_growth_grant_bytes = 0;
        out.small_cpu_admitted = false;
        out.host_loan_quota_bytes = in.relay_host_live_bytes;
    } else if (!in.relay_ready) {
        out.state = State::warming;
        out.reason = in.donors_available ? "relay_not_ready_donors_serve" : "relay_not_ready";
    } else if (out.host_loans_admitted || out.guest_prepare_grant_bytes || requested_donor_grant) {
        out.state = State::growing;
        out.reason = "measured_room_available";
    } else {
        out.state = State::holding;
        out.reason = out.growth_room_bytes < admission_room ? "room_below_growth_quantum"
                                                            : "relay_host_capacity_exhausted";
    }
    // The process's own jetsam headroom cannot throttle relay or donor pages,
    // which are not charged to it, but it does ask the storage tier to archive
    // cold data early. A missing process sample is not a reason to fail closed:
    // the system sample above remains the authority.
    if (in.host_available_valid && in.host_available_bytes < out.operational_reserve_bytes)
        out.storage_shrink_requested = true;
    // Build434: the measured envelope is the earlier of the two signals. The
    // process reaches its allocatable share (limit minus the safety reserve)
    // before os_proc_available_memory() falls under the operational reserve.
    if (out.host_room_valid && out.host_room_bytes == 0)
        out.storage_shrink_requested = true;
    return out;
}

// A donor completion can immediately start another request before the next
// sampling tick. Completing/refusing the IPC must not refund this decision's
// allowance: only the next decision may authorize those bytes again.
constexpr std::uint64_t remaining_donor_room(const Decision& decision,
                                            std::uint64_t committed_bytes) noexcept {
    return decision.donor_growth_admitted && decision.donor_room_bytes > committed_bytes
        ? decision.donor_room_bytes - committed_bytes : 0;
}

constexpr const char* state_name(State state) noexcept {
    switch (state) {
    case State::idle: return "idle";
    case State::warming: return "warming";
    case State::growing: return "growing";
    case State::holding: return "holding";
    case State::shrinking: return "shrinking";
    case State::pressure: return "pressure";
    }
    return "unknown";
}
} // namespace neostation::budget
