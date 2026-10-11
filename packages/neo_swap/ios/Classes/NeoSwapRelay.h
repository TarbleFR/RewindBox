// SPDX-License-Identifier: MIT
#ifndef NEOSTATION_NEOSWAP_RELAY_H
#define NEOSTATION_NEOSWAP_RELAY_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

/* Separate ABI: does not change NeoSwapAPI v1 or its allocation ownership.
 * A token owns one backing interval. Every map of that token aliases the SAME
 * bytes. Capacity is retained VM-object capacity, never resident physical RAM.
 * All calls require a normal thread. Quiesce every guest/CPU/GPU user before
 * unmap/release; these operations do not wait for emulator work to complete.
 */
enum { NEOSWAP_RELAY_ABI = 1, NEOSWAP_RELAY_ALIGNMENT = 65536 };
enum NeoSwapRelayProtection {
    NEOSWAP_RELAY_NONE = 0, NEOSWAP_RELAY_READ = 1, NEOSWAP_RELAY_READ_WRITE = 3
};
enum NeoSwapRelayResult {
    NEOSWAP_RELAY_OK = 0, NEOSWAP_RELAY_DISABLED = -1,
    NEOSWAP_RELAY_INVALID = -2, NEOSWAP_RELAY_QUOTA = -3,
    NEOSWAP_RELAY_MAPPING = -4, NEOSWAP_RELAY_BUSY = -5,
    NEOSWAP_RELAY_UNKNOWN = -6, NEOSWAP_RELAY_PRESSURE = -7,
    NEOSWAP_RELAY_LIMIT = -8, NEOSWAP_RELAY_CLEANUP = -9
};
typedef struct NeoSwapRelayStats {
    uint32_t struct_size, abi_version;
    uint64_t capacity_bytes, retained_capacity_bytes, live_bytes, peak_live_bytes;
    uint64_t object_count, alias_count, mapped_alias_bytes, entry_count;
    uint64_t rejection_count, os_error_count, pending_cleanup_entries, retiring_object_count;
    uint64_t quarantined_fixed_alias_count;
    uint32_t enabled_owner_mask, pressure_raised;
    int32_t last_result, last_os_error;
} NeoSwapRelayStats;
typedef struct NeoSwapRelayAPI {
    uint32_t struct_size, abi_version;
    int (*create)(uint32_t owner, uint64_t bytes, uint64_t* token);
    /* A non-null target MUST be a caller-owned reserved guest range. Existing
     * guest users must be quiesced. Failed maps leave that reservation intact.
     * Null requests a new, 64-KiB-aligned alias. No executable mapping exists.
     */
    int (*map)(uint64_t token, void* target, uint32_t protection, void** mapped);
    /* A fixed alias is atomically replaced with a PROT_NONE reservation;
     * an anywhere alias is deallocated. Failure retains ownership and mapping.
     */
    int (*unmap)(uint64_t token, void* address);
    /* BUSY while any aliases remain. Scrub failure retains the token for retry;
     * no error permits reuse of the backing interval or an ordinary free().
     */
    int (*release)(uint64_t token);
    int (*enabled)(uint32_t owner);
    int (*snapshot)(NeoSwapRelayStats* stats);
    /* Destructor path: caller has quiesced ALL users and relinquishes the
     * token. The backend blocks new maps immediately and owns retirement of
     * every remaining alias. ANYWHERE cleanup errors are retried by collect().
     * FIXED aliases are attempted synchronously once: a failed fixed replacement
     * is permanently quarantined because its caller may subsequently reuse the
     * virtual address. That object is never scrubbed/reissued during this process.
     * Unlike release(), caller may forget the token after calling retire().
     */
    int (*retire)(uint64_t token);
} NeoSwapRelayAPI;
#if defined(__GNUC__)
__attribute__((visibility("default")))
#endif
const NeoSwapRelayAPI* NeoSwap_GetRelayAPI(uint32_t abi_version);

/* Optional, separate ABI. Prepared objects have no caller alias and are not
 * donated until RelayAPI.map first publishes them. Acquisition only tries a
 * metadata lock: it never allocates, samples the OS, maps or touches pages.
 * A successful token uses the unchanged RelayAPI lifecycle. Misses record
 * bounded demand for a utility worker; callers may use ordinary backing.
 */
enum { NEOSWAP_PREPARED_RELAY_ABI = 1 };
typedef struct NeoSwapPreparedRelayStats {
    uint32_t struct_size, abi_version;
    uint64_t prepared_bytes, prepared_count, demand_bytes, demand_count;
    uint64_t request_count, requested_bytes, acquired_count, acquired_bytes;
    uint64_t miss_busy, miss_empty, refused_pressure, refused_disabled;
    uint64_t unsupported_count, demand_overflow;
    uint64_t prepared_total, reclaimed_total, prepare_failures, peak_prepared_bytes;
    uint64_t pending_scrub_bytes, pending_scrub_count;
    /* Includes prepared + borrowed-but-unpublished + their pending cleanup.
     * These commitments have not necessarily consumed physical pages yet. */
    uint64_t unpublished_bytes;
} NeoSwapPreparedRelayStats;
typedef struct NeoSwapPreparedRelayAPI {
    uint32_t struct_size, abi_version;
    int (*try_acquire)(uint32_t owner, uint64_t bytes, uint64_t* token);
    /* Only before any successful map, with no concurrent user of the token.
     * OK transfers ownership to utility cleanup without locks or OS calls;
     * failure retains ownership. Does not accept legacy create() tokens. */
    int (*return_unused)(uint64_t token);
    int (*snapshot)(NeoSwapPreparedRelayStats* stats);
} NeoSwapPreparedRelayAPI;
#if defined(__GNUC__)
__attribute__((visibility("default")))
#endif
const NeoSwapPreparedRelayAPI* NeoSwap_GetPreparedRelayAPI(uint32_t abi_version);

/* Optional Core diagnostics; independent from both relay function tables. */
enum { NEOSWAP_RELAY_CLIENT_STATS_ABI = 1 };
typedef struct NeoSwapRelayClientStats {
    uint32_t struct_size, abi_version, gameplay_active, reserved;
    uint64_t candidate_first_maps, requested_bytes, gameplay_first_maps, gameplay_requested_bytes;
    uint64_t prepared_hits, prepared_hit_bytes, prepared_misses, prepared_miss_bytes;
    uint64_t ordinary_fallbacks, ordinary_fallback_bytes, map_failures, alias_maps;
    uint64_t prepared_published_objects, prepared_published_bytes;
    uint64_t first_map_total_ns, first_map_max_ns;
    int32_t last_result;
    uint32_t reserved_result;
} NeoSwapRelayClientStats;
#ifdef __cplusplus
}
#endif
#endif
