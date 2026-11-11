#pragma once
// The engine's prepare_code hook (rb_guest.h, patch 0004) and the JIT helper commands behind it. Game code is copied by the
// engine into a writable alias that this file returns; the pages at the engine's address must be executable first.
//
//   universal (iOS 26+), helper attached: mmap R|X at the requested address (over the engine's read-write pages), command 1
//            (brk #0xf00d, x16 = 1, x0 = address, x1 = length) in chunks of at most 16 MiB, each answered with its own
//            address, then a read-write vm_remap alias of those pages. This is the "process-mapped" placement the device
//            probe ran on 802 (docs/s2arm-prototype-2026-11-10.md), and what RPCS3's Core does for its arena.
//   universal, after the detach: no command can be issued any more. The block comes from the spare pool, R|X pages
//            prepared while attached: they are vm_remap-ed onto the requested address and a read-write alias is returned.
//            Never observed on a device (see docs/s2arm-engine-bridge.md).
//   classic (before iOS 26): the helper attached and detached by itself and left CS_DEBUGGED; the process maps R|X itself.
//
// Every call is serialised (one helper command at a time). Plain C on Apple platforms; elsewhere every call fails.
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

enum { S2ARM_CODE_OFF = 0, S2ARM_CODE_ATTACHED = 1, S2ARM_CODE_DETACHED = 2, S2ARM_CODE_CLASSIC = 3 };
#define S2ARM_CODE_COMMAND_CHUNK (16ull << 20)   // at most 16 MiB per command 1 (RPCS3's choice, agreed with main)
#define S2ARM_CODE_PAGE 0x4000ull

typedef struct {
    int mode;
    unsigned served_blocks;        // successful hook calls
    uint64_t served_bytes;
    unsigned failed_blocks;
    unsigned commands;             // command 1 issued (hook and pool)
    unsigned after_detach_blocks;  // served from the spare pool
    unsigned in_progress;          // hook calls running now
    uint64_t last_activity_ns;     // monotonic time of the last hook call's end (0 = none yet)
    uint64_t pool_bytes, pool_used;
    int detached;                  // command 0 issued
} s2arm_code_stats;

/// Before the engine is opened. universal = 1: helper attached, universal handshake; 0: classic (helper already gone).
void s2arm_code_begin(int universal);
/// Universal only, while attached: prepares the spare pool (R|X pages anywhere, command 1 in chunks). 0 = ok.
int s2arm_code_prepare_pool(uint64_t bytes);
/// Universal only: command 3 (probe) with the session's nonce; returns the value the helper put in x0 (nonce + 1 = ok).
uint64_t s2arm_code_probe(uint64_t nonce);
/// Universal only: command 0 (detach), once. Later hook calls use the spare pool. Returns 1 when this call issued it.
int s2arm_code_detach(void);
/// The engine's hook: s2a_rb_guest_config.prepare_code.
void *s2arm_code_prepare(void *address, size_t length, void *context);
void s2arm_code_stats_get(s2arm_code_stats *out);
uint64_t s2arm_code_now_ns(void);

#ifdef __cplusplus
}
#endif
