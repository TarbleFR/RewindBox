/*
 * Versioned C ABI between RewindBox's libretro host and the libretro cores RewindBox builds with their JIT
 * (Azahar's dynarmic, Beetle PSX's Lightrec, DeSmuME). The host prepares the session's executable memory
 * itself, before it opens the core, under the app's JIT contract (packages/libretro_internal_bridge,
 * LibretroJitArena.c); a patched core takes its code buffers from it instead of mapping executable memory.
 *
 * Contract for the core:
 * - Code is written only through `rw` and executed only at `rx`: the same physical pages at two addresses.
 *   Never make those pages writable and executable at once, never change their protections, never map
 *   executable memory itself (iOS 26 forbids it once the debugger has detached).
 * - After writing code through `rw`, call `flush(rx, bytes)` before executing it.
 * - `allocate` hands out page-aligned blocks out of a fixed `capacity` that never grows: a full code cache is
 *   cleared and reused by the core. Blocks stay valid until the core is closed (after retro_deinit).
 * - The host calls REWINDBOX_LIBRETRO_JIT_INSTALL_SYMBOL right after dlopen, before retro_set_environment and
 *   retro_init, at most once per open, only when the arena is ready. A return of 0 means the core will use the
 *   interface; the host then answers RETRO_ENVIRONMENT_GET_JIT_CAPABLE with true. Any other value, or no
 *   such symbol, keeps the core's interpreter.
 *
 * Plain C with fixed-width fields and no ownership inferred from addresses, like NeoStationPSPMemory.h.
 * License: MIT (this header only), so that it can be copied into the cores' sources.
 */
#ifndef REWINDBOX_LIBRETRO_JIT_H
#define REWINDBOX_LIBRETRO_JIT_H

#include <stdint.h>

#define REWINDBOX_LIBRETRO_JIT_VERSION 1u
#define REWINDBOX_LIBRETRO_JIT_INSTALL_SYMBOL "rewindbox_libretro_jit_install"

typedef struct RewindBoxLibretroJitV1 {
  uint32_t version;     /* REWINDBOX_LIBRETRO_JIT_VERSION */
  uint32_t structBytes; /* sizeof(RewindBoxLibretroJitV1) */
  uint64_t pageBytes;   /* allocation granule (16 KiB) */
  uint64_t capacity;    /* bytes prepared for this session */
  /* A page-aligned block of at least `bytes`: *rx executes, *rw writes the same pages.
   * 0 on success; -1 (outputs untouched) when the capacity left is too small. Thread-safe. */
  int (*allocate)(uint64_t bytes, uint64_t *rx, uint64_t *rw);
  /* Instruction-cache invalidation of [rx, rx + bytes) after writing it through its rw alias. */
  void (*flush)(uint64_t rx, uint64_t bytes);
  /* Bytes still available to allocate. */
  uint64_t (*available)(void);
} RewindBoxLibretroJitV1;

typedef int (*RewindBoxLibretroJitInstall)(const RewindBoxLibretroJitV1 *jit);

#endif /* REWINDBOX_LIBRETRO_JIT_H */
