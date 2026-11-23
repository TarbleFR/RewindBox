// See LibretroJitArena.h. Plain C in an Objective-C unit: every harness that builds the bridge compiles Classes/*.m.
// Command trampolines, chunked preparation and the read-write alias follow
// packages/s2arm_engine_bridge/ios/Classes/S2ArmCodePages.c; the arena is mapped anywhere by the host itself, before
// the core is opened, so no core code ever runs while the debugger is attached.
#include "LibretroJitArena.h"

#include <errno.h>
#include <pthread.h>
#include <stdio.h>
#include <string.h>
#include <time.h>

#if defined(__APPLE__)
#include <libkern/OSCacheControl.h>
#include <mach/mach.h>
#include <mach/vm_map.h>
#include <sys/mman.h>
#include <sys/sysctl.h>
#include <unistd.h>
#endif

static pthread_mutex_t gLock = PTHREAD_MUTEX_INITIALIZER;
static LibretroJitArenaStats gStats;
static uint8_t *gRX;  // R|X view, executed by the core
static uint8_t *gRW;  // read-write alias of the same pages, written by the core

static uint64_t now_ms(void) {
  struct timespec now;
  clock_gettime(CLOCK_MONOTONIC, &now);
  return (uint64_t)now.tv_sec * 1000ull + (uint64_t)now.tv_nsec / 1000000ull;
}

// Caller holds gLock. Keeps the first reason only.
static void note_failure(const char *reason) {
  if (gStats.failure[0] == 0) snprintf(gStats.failure, sizeof gStats.failure, "%s", reason);
}

#if defined(__APPLE__) && defined(__arm64__)
// The universal script's commands (libretro-universal.js): brk #0xf00d with the command in x16, x0/x1 the arguments,
// x0 the answer. Without a debugger a trap is a SIGTRAP: every caller checks P_TRACED first.
__attribute__((naked, noinline)) static uint64_t libretro_jit_trap_prepare(uint64_t address, uint64_t length) {
  __asm__("mov x16, #1\n"
          "brk #0xf00d\n"
          "ret");
}
__attribute__((naked, noinline)) static uint64_t libretro_jit_trap_probe(uint64_t nonce) {
  __asm__("mov x16, #3\n"
          "brk #0xf00d\n"
          "ret");
}
__attribute__((naked, noinline)) static void libretro_jit_trap_detach(void) {
  __asm__("mov x16, #0\n"
          "brk #0xf00d\n"
          "ret");
}
#define LIBRETRO_JIT_HAVE_TRAPS 1
#else
#define LIBRETRO_JIT_HAVE_TRAPS 0
#endif

#if defined(__APPLE__)
// P_TRACED: a debugger is attached right now (CS_DEBUGGED stays set after a detach and proves nothing).
static int live_debugger(void) {
  int mib[] = {CTL_KERN, KERN_PROC, KERN_PROC_PID, getpid()};
  struct kinfo_proc info;
  memset(&info, 0, sizeof info);
  size_t size = sizeof info;
  return sysctl(mib, 4, &info, &size, NULL, 0) == 0 && size == sizeof info && (info.kp_proc.p_flag & P_TRACED) != 0;
}

// Command 1 over [at, at + length) in chunks; each chunk must come back with its own address (the script answers 0 on
// a refusal). Caller holds gLock.
static int issue_prepare(uint8_t *at, uint64_t length) {
#if LIBRETRO_JIT_HAVE_TRAPS
  for (uint64_t done = 0; done < length;) {
    const uint64_t chunk = length - done < LIBRETRO_JIT_COMMAND_CHUNK ? length - done : LIBRETRO_JIT_COMMAND_CHUNK;
    const uint64_t want = (uint64_t)(uintptr_t)(at + done);
    if (!live_debugger()) {
      note_failure("command1-no-debugger");
      return -1;
    }
    const uint64_t got = libretro_jit_trap_prepare(want, chunk);
    gStats.commands++;
    if (got != want) {
      note_failure("command1-refused");
      return -1;
    }
    done += chunk;
  }
  return 0;
#else
  (void)at;
  (void)length;
  note_failure("no-traps");
  return -1;
#endif
}

// A read-write alias anywhere of [source, source + length): the same physical pages (copy = FALSE).
static uint8_t *writable_alias(uint8_t *source, uint64_t length) {
  vm_address_t alias = 0;
  vm_prot_t current = VM_PROT_NONE, maximum = VM_PROT_NONE;
  kern_return_t kr = vm_remap(mach_task_self(), &alias, (vm_size_t)length, 0, VM_FLAGS_ANYWHERE, mach_task_self(),
                              (vm_address_t)source, FALSE, &current, &maximum, VM_INHERIT_NONE);
  if (kr != KERN_SUCCESS) {
    note_failure("alias-remap");
    return NULL;
  }
  kr = vm_protect(mach_task_self(), alias, (vm_size_t)length, FALSE, VM_PROT_READ | VM_PROT_WRITE);
  if (kr != KERN_SUCCESS) {
    note_failure("alias-protect");
    vm_deallocate(mach_task_self(), alias, (vm_size_t)length);
    return NULL;
  }
  return (uint8_t *)alias;
}

// Caller holds gLock.
static void release_views(void) {
  if (gRW != NULL) munmap(gRW, (size_t)gStats.capacity);
  if (gRX != NULL) munmap(gRX, (size_t)gStats.capacity);
  gRW = NULL;
  gRX = NULL;
}
#endif

int libretro_jit_arena_prepare(uint64_t bytes, int universal) {
#if defined(__APPLE__) && defined(__arm64__)
  bytes = (bytes + LIBRETRO_JIT_PAGE - 1) & ~(LIBRETRO_JIT_PAGE - 1);
  pthread_mutex_lock(&gLock);
  if (gStats.state == LIBRETRO_JIT_ARENA_ATTACHED) {  // a transaction is still running
    pthread_mutex_unlock(&gLock);
    return -1;
  }
  release_views();
  memset(&gStats, 0, sizeof gStats);
  gStats.universal = universal ? 1 : 0;
  gStats.state = LIBRETRO_JIT_ARENA_FAILED;
  if (bytes == 0 || bytes > LIBRETRO_JIT_MAX_CAPACITY) {
    note_failure("capacity");
    pthread_mutex_unlock(&gLock);
    return -1;
  }
  const uint64_t started = now_ms();
  void *mapped = mmap(NULL, (size_t)bytes, PROT_READ | PROT_EXEC, MAP_PRIVATE | MAP_ANON, -1, 0);
  if (mapped == MAP_FAILED) {
    note_failure("map-rx");
    pthread_mutex_unlock(&gLock);
    return -1;
  }
  uint8_t *rx = mapped;
  if (universal && issue_prepare(rx, bytes) != 0) {
    munmap(rx, (size_t)bytes);
    pthread_mutex_unlock(&gLock);
    return -1;
  }
  uint8_t *rw = writable_alias(rx, bytes);
  if (rw == NULL) {
    munmap(rx, (size_t)bytes);
    pthread_mutex_unlock(&gLock);
    return -1;
  }
  // Executable probe through both views: mov w0, #0x5242 ; ret, written through the alias, run at the R|X address.
  const uint32_t probe[2] = {0x52800000u | (0x5242u << 5), 0xD65F03C0u};
  memcpy(rw, probe, sizeof probe);
  sys_icache_invalidate(rx, sizeof probe);
  uint32_t (*function)(void) = (uint32_t (*)(void))(void *)rx;
  const uint32_t answer = function();
  if (answer != 0x5242u) {
    note_failure("executable-probe");
    munmap(rw, (size_t)bytes);
    munmap(rx, (size_t)bytes);
    pthread_mutex_unlock(&gLock);
    return -1;
  }
  memset(rw, 0, sizeof probe);
  sys_icache_invalidate(rx, sizeof probe);
  gRX = rx;
  gRW = rw;
  gStats.capacity = bytes;
  gStats.executableProbe = 1;
  gStats.prepareMilliseconds = now_ms() - started;
  gStats.state = universal ? LIBRETRO_JIT_ARENA_ATTACHED : LIBRETRO_JIT_ARENA_READY;
  pthread_mutex_unlock(&gLock);
  return 0;
#else
  (void)bytes;
  pthread_mutex_lock(&gLock);
  memset(&gStats, 0, sizeof gStats);
  gStats.universal = universal ? 1 : 0;
  gStats.state = LIBRETRO_JIT_ARENA_FAILED;
  note_failure("unsupported-platform");
  pthread_mutex_unlock(&gLock);
  return -1;
#endif
}

uint64_t libretro_jit_arena_probe(uint64_t nonce) {
#if LIBRETRO_JIT_HAVE_TRAPS
  pthread_mutex_lock(&gLock);
  uint64_t answer = 0;
  if (gStats.universal && !gStats.detached && live_debugger()) {
    answer = libretro_jit_trap_probe(nonce);
    gStats.nonceProbe = answer == nonce + 1;
    if (!gStats.nonceProbe) note_failure("nonce-probe");
  }
  pthread_mutex_unlock(&gLock);
  return answer;
#else
  (void)nonce;
  return 0;
#endif
}

int libretro_jit_arena_detach(void) {
  int issued = 0;
#if LIBRETRO_JIT_HAVE_TRAPS
  pthread_mutex_lock(&gLock);
  if (gStats.universal && !gStats.detached && live_debugger()) {
    libretro_jit_trap_detach();
    gStats.detached = 1;
    issued = 1;
    // Ready only with a proven helper round trip.
    if (gStats.state == LIBRETRO_JIT_ARENA_ATTACHED) {
      gStats.state = gStats.nonceProbe ? LIBRETRO_JIT_ARENA_READY : LIBRETRO_JIT_ARENA_FAILED;
    }
  }
  pthread_mutex_unlock(&gLock);
#endif
  return issued;
}

int libretro_jit_arena_ready(void) {
  pthread_mutex_lock(&gLock);
  const int ready = gStats.state == LIBRETRO_JIT_ARENA_READY && gRX != NULL;
  pthread_mutex_unlock(&gLock);
  return ready;
}

static int arena_allocate(uint64_t bytes, uint64_t *rx, uint64_t *rw) {
  if (rx == NULL || rw == NULL || bytes == 0) return -1;
  const uint64_t rounded = (bytes + LIBRETRO_JIT_PAGE - 1) & ~(LIBRETRO_JIT_PAGE - 1);
  int result = -1;
  pthread_mutex_lock(&gLock);
  if (gStats.state == LIBRETRO_JIT_ARENA_READY && gRX != NULL && rounded >= bytes &&
      rounded <= gStats.capacity - gStats.used) {
    *rx = (uint64_t)(uintptr_t)(gRX + gStats.used);
    *rw = (uint64_t)(uintptr_t)(gRW + gStats.used);
    gStats.used += rounded;
    gStats.blocks++;
    result = 0;
  } else {
    gStats.refusedBlocks++;
  }
  pthread_mutex_unlock(&gLock);
  return result;
}

static void arena_flush(uint64_t rx, uint64_t bytes) {
#if defined(__APPLE__)
  if (rx != 0 && bytes != 0) sys_icache_invalidate((void *)(uintptr_t)rx, (size_t)bytes);
#else
  (void)rx;
  (void)bytes;
#endif
}

static uint64_t arena_available(void) {
  pthread_mutex_lock(&gLock);
  const uint64_t available = gStats.state == LIBRETRO_JIT_ARENA_READY ? gStats.capacity - gStats.used : 0;
  pthread_mutex_unlock(&gLock);
  return available;
}

static RewindBoxLibretroJitV1 gInterface = {
    REWINDBOX_LIBRETRO_JIT_VERSION, (uint32_t)sizeof(RewindBoxLibretroJitV1), LIBRETRO_JIT_PAGE, 0, arena_allocate,
    arena_flush, arena_available,
};

const RewindBoxLibretroJitV1 *libretro_jit_arena_interface(void) {
  pthread_mutex_lock(&gLock);
  gInterface.capacity = gStats.state == LIBRETRO_JIT_ARENA_READY ? gStats.capacity : 0;
  pthread_mutex_unlock(&gLock);
  return &gInterface;
}

void libretro_jit_arena_note_installed(void) {
  pthread_mutex_lock(&gLock);
  gStats.installed = 1;
  pthread_mutex_unlock(&gLock);
}

void libretro_jit_arena_release(void) {
  pthread_mutex_lock(&gLock);
  if (gStats.state != LIBRETRO_JIT_ARENA_ATTACHED) {
#if defined(__APPLE__)
    release_views();
#endif
    gStats.state = LIBRETRO_JIT_ARENA_OFF;
    gStats.used = 0;
    gStats.installed = 0;
  }
  pthread_mutex_unlock(&gLock);
}

void libretro_jit_arena_stats(LibretroJitArenaStats *out) {
  if (out == NULL) return;
  pthread_mutex_lock(&gLock);
  *out = gStats;
  pthread_mutex_unlock(&gLock);
}
