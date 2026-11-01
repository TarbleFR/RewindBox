#pragma once

// NEOSTATION_RPCS3_RETROACHIEVEMENTS_V1: host copy of the optional
// RetroAchievements exports of the RPCS3 Core (rpcs3/ios/RPCS3IOS.h, staged in
// build-utils/rpcs3/retroachievements-core.patch). They are resolved with
// dlsym only: a Core without them keeps working and PS3 RetroAchievements is
// reported as unavailable for this core. Kept out of Rpcs3CoreABI.h on
// purpose: that header belongs to the pinned Core identity, these optional
// symbols do not, and RPCS3_IOS_ABI_VERSION (30) is unchanged.

#include <stddef.h>
#include <stdint.h>

#include "Rpcs3CoreABI.h"

#ifdef __cplusplus
extern "C" {
#endif

#define RPCS3_IOS_RA_API_VERSION 1u

// rpcs3_ios_status values used by the RetroAchievements exports.
#define RPCS3_IOS_RA_STATUS_OK 0
#define RPCS3_IOS_RA_STATUS_INVALID_ARGUMENT 1
#define RPCS3_IOS_RA_STATUS_INVALID_STATE 2

// rpcs3_ios_emulation_state values reported in rpcs3_ios_ra_session_info.
#define RPCS3_IOS_RA_EMULATION_RUNNING 5u
#define RPCS3_IOS_RA_EMULATION_PAUSED 6u

typedef void (*rpcs3_ios_ra_frame_callback)(void* context, uint64_t frame);

typedef struct rpcs3_ios_ra_session_info {
  uint32_t struct_size;
  uint32_t emulation_state;
  uint32_t hardcore_compatible;
  uint32_t vblank_rate;
  uint32_t clocks_scale;
  uint32_t frame_limit_unbounded;
  uint64_t boot_generation;
  char title_id[64];
  char content_path[1024];
} rpcs3_ios_ra_session_info;

typedef uint32_t (*rpcs3_ios_ra_api_version_function)(void);
typedef rpcs3_ios_status (*rpcs3_ios_ra_set_frame_callback_function)(
    rpcs3_ios_ra_frame_callback callback, void* context);
typedef rpcs3_ios_status (*rpcs3_ios_ra_read_memory_function)(
    uint32_t address, void* buffer, uint32_t size, uint32_t* mapped_bytes);
typedef rpcs3_ios_status (*rpcs3_ios_ra_get_session_info_function)(
    rpcs3_ios_ra_session_info* info);

// Resolved together or not at all.
typedef struct rpcs3_ios_ra_api {
  rpcs3_ios_ra_set_frame_callback_function set_frame_callback;
  rpcs3_ios_ra_read_memory_function read_memory;
  rpcs3_ios_ra_get_session_info_function get_session_info;
} rpcs3_ios_ra_api;

#ifdef __cplusplus
}
static_assert(sizeof(rpcs3_ios_ra_session_info) == 1120,
              "rpcs3_ios_ra_session_info must match the Core layout");
#endif
