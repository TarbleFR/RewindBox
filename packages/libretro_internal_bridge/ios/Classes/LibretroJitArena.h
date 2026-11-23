// The host's code arena for libretro cores (RewindBoxLibretroJit.h), on the model of the S2Arm engine's code pages
// (packages/s2arm_engine_bridge/ios/Classes/S2ArmCodePages.c), prepared before the core is opened:
//
//   universal (iOS 26 and later), the libretro JIT helper attached: R|X pages are mapped, prepared by command 1
//            (brk #0xf00d, x16 = 1, x0 = address, x1 = length) in chunks of at most 16 MiB, each answered with its own
//            address, then aliased read-write with vm_remap (copy = FALSE) and vm_protect. An executable probe runs
//            through the alias. The caller then issues command 3 (nonce) and command 0 (detach): nothing can be
//            prepared after the detach, so the capacity is fixed for the session.
//   classic (before iOS 26): the helper attached and detached by itself and left CS_DEBUGGED; the process maps the
//            R|X pages and their alias itself, then runs the same probe.
//
// One arena per session, released after the core is closed. Every call is serialised. Plain C (LibretroJitArena.m);
// outside Apple arm64 every preparation fails.
#pragma once

#include <stdint.h>

#include "RewindBoxLibretroJit.h"

#ifdef __cplusplus
extern "C" {
#endif

/// 16 KiB pages; at most 16 MiB per command 1 (RPCS3's and S2Arm's choice).
#define LIBRETRO_JIT_PAGE 0x4000ull
#define LIBRETRO_JIT_COMMAND_CHUNK (16ull << 20)
/// Largest arena the host prepares (every prepared page is resident at once).
#define LIBRETRO_JIT_MAX_CAPACITY (512ull << 20)

enum {
  LIBRETRO_JIT_ARENA_OFF = 0,
  LIBRETRO_JIT_ARENA_ATTACHED = 1,  // universal, prepared, debugger still attached
  LIBRETRO_JIT_ARENA_READY = 2,     // prepared, probed (and detached in universal mode)
  LIBRETRO_JIT_ARENA_FAILED = 3,
};

typedef struct {
  int state;
  int universal;              // 1 universal handshake, 0 classic
  uint64_t capacity;          // prepared bytes
  uint64_t used;              // handed out to the core
  unsigned commands;          // command 1 issued
  unsigned blocks;            // allocations served
  unsigned refusedBlocks;     // allocations refused (capacity)
  int executableProbe;        // 1: the probe returned its value through the R|X view
  int nonceProbe;             // 1: command 3 answered nonce + 1
  int detached;               // command 0 issued
  int installed;              // a core accepted the interface
  uint64_t prepareMilliseconds;
  char failure[96];           // first failure, for the journal
} LibretroJitArenaStats;

/// Prepares a fresh arena of `bytes` (rounded up to whole pages, at most LIBRETRO_JIT_MAX_CAPACITY), releasing any
/// previous one. universal = 1 only while the helper keeps the debugger attached. 0 = prepared and probed.
int libretro_jit_arena_prepare(uint64_t bytes, int universal);
/// Universal, attached: command 3 with the session's nonce; returns the helper's answer (nonce + 1 proves it).
uint64_t libretro_jit_arena_probe(uint64_t nonce);
/// Universal, attached: command 0, once, also after a failed preparation (the process must not stay stopped on the
/// next trap). Returns 1 when this call issued it. A prepared arena becomes ready.
int libretro_jit_arena_detach(void);
/// 1 when prepared, probed and (universal) detached, and not released.
int libretro_jit_arena_ready(void);
/// The interface handed to the core; valid while ready.
const RewindBoxLibretroJitV1 *libretro_jit_arena_interface(void);
/// Notes that a core accepted the interface (journal).
void libretro_jit_arena_note_installed(void);
/// After the core is closed: unmaps both views. Safe when nothing is prepared.
void libretro_jit_arena_release(void);
void libretro_jit_arena_stats(LibretroJitArenaStats *out);

#ifdef __cplusplus
}
#endif
