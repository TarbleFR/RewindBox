#import <Foundation/Foundation.h>
#import "LibretroAddressSpace.h"
#include <mach/mach.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>

static int failures;
#define CHECK(c, label) do { if (!(c)) { printf("FAIL %s line %d\n", label, __LINE__); failures++; } } while (0)
#ifndef PSP497_LEGACY_ONLY
static atomic_bool pressureDone;
static atomic_uint pressureIntrusions;
static uint64_t pressureBase;

static BOOL CanTake(uint64_t at, uint64_t size) {
  vm_address_t p = at;
  if (vm_allocate(mach_task_self(), &p, size, VM_FLAGS_FIXED) != KERN_SUCCESS) return NO;
  vm_deallocate(mach_task_self(), p, size);
  return YES;
}

static void *Pressure(void *unused) {
  (void)unused;
  while (!atomic_load(&pressureDone)) {
    // Representative allocator contention at scratchpad, VRAM, both RAM
    // halves and the former arena slot: there must never be a free hole.
    const uint64_t offsets[] = {0x10000, 0x04000000, 0x08000000, 0x0a000000, 0x00018000};
    for (size_t i = 0; i < 5; i++)
      if (CanTake(pressureBase + offsets[i], 0x4000)) atomic_fetch_add(&pressureIntrusions, 1);
  }
  return NULL;
}
#endif

static int LegacyCollision(void) {
  CHECK(LibretroPPSSPPReserveWindow(), "legacy reservation");
  uint64_t base = LibretroPPSSPPReleaseViewsForBoot();
  // Reproduce the exact observed placement: the backing arena is in the
  // released RAM view, as app(2).log's 0x17c000000 -> 0x17c000000 remap.
  vm_address_t arena = base + 0x08000000;
  CHECK(vm_allocate(mach_task_self(), &arena, 0x2804000, VM_FLAGS_FIXED) == KERN_SUCCESS,
        "legacy backing arena can occupy RAM destination");
  vm_address_t ram = base + 0x08000000;
  vm_prot_t current = 0, maximum = 0;
  int result = vm_remap(mach_task_self(), &ram, 0x1f00000, 0, VM_FLAGS_FIXED,
      mach_task_self(), arena + 0x204000, FALSE, &current, &maximum, VM_INHERIT_DEFAULT);
  CHECK(result == KERN_NO_SPACE, "legacy RAM remap reproduces kernel error 3");
  vm_deallocate(mach_task_self(), arena, 0x2804000);
  LibretroPPSSPPRestoreReservation();
  printf("%s PSP497_ARENA_VIEW_COLLISION_REPRODUCED\n", failures ? "FAIL" : "PASS");
  return failures ? 1 : 0;
}

#ifndef PSP497_LEGACY_ONLY
static void Cycle(uint64_t ramBytes, BOOL abortPartial) {
  const NeoStationPSPMemoryCallbacks *api = LibretroPPSSPPMemoryCallbacks();
  const uint64_t bytes = ramBytes + 0x804000;
  uint64_t arena = 0, base = 0;
  CHECK(api->begin(bytes, &arena, &base) == KERN_SUCCESS, "managed arena acquired");
  if (!arena || !base) return;
  CHECK(arena + bytes <= base || arena >= base + 0x08000000 + MAX(ramBytes, 0x04000000ull),
        "backing arena never overlaps its views");
  CHECK(!CanTake(base + 0x08000000, 0x4000), "RAM stays owned before the first view");
  ((volatile uint8_t *)arena)[0x100] = 0xa5;
  ((volatile uint8_t *)arena)[0x204100] = 0x5a;
  CHECK(api->map(arena, base + 0x10000, 0x4000) == KERN_SUCCESS, "scratchpad atomically mapped");
  CHECK(((volatile uint8_t *)(base + 0x10000))[0x100] == 0xa5, "scratchpad aliases backing");
  // Invalid source and destination must leave a foreign mapping intact.
  vm_address_t foreign = 0;
  CHECK(vm_allocate(mach_task_self(), &foreign, 0x4000, VM_FLAGS_ANYWHERE) == KERN_SUCCESS, "foreign mapping");
  ((volatile uint8_t *)foreign)[0] = 0x71;
  CHECK(api->map(arena, foreign, 0x4000) != KERN_SUCCESS, "foreign target refused");
  CHECK(api->map(arena - 0x4000, base + 0x04000000, 0x4000) != KERN_SUCCESS, "foreign source refused");
  CHECK(api->unmap(foreign, 0x4000) != KERN_SUCCESS, "foreign unmap refused");
  CHECK(((volatile uint8_t *)foreign)[0] == 0x71, "foreign bytes preserved");
  vm_deallocate(mach_task_self(), foreign, 0x4000);
  if (abortPartial) {
    CHECK(api->end(arena, bytes) == KERN_SUCCESS, "partial failed startup cleans views and backing");
    CHECK(!CanTake(base + 0x10000, 0x4000), "aborted scratchpad remains reserved");
    return;
  }
  for (uint64_t i = 0; i < 4; i++)
    CHECK(api->map(arena + 0x4000, base + 0x04000000 + i * 0x200000, 0x200000) == KERN_SUCCESS,
          "VRAM mirror mapped");
  uint64_t remaining = ramBytes, source = arena + 0x204000, destination = base + 0x08000000;
  while (remaining) {
    uint64_t part = MIN(remaining, 31ull * 1024 * 1024);
    CHECK(api->map(source, destination, part) == KERN_SUCCESS, "RAM part mapped");
    source += part; destination += part; remaining -= part;
  }
  CHECK(((volatile uint8_t *)(base + 0x08000000))[0x100] == 0x5a, "RAM aliases backing");
  ((volatile uint8_t *)(base + 0x08000000))[0x100] = 0x82;
  CHECK(((volatile uint8_t *)arena)[0x204100] == 0x82, "RAM writes reach backing");
  CHECK(api->map(arena, base + 0x10000, 0x4000) != KERN_SUCCESS, "live view never overwritten");
  LibretroPPSSPPMemorySettled(base);
  CHECK(((volatile uint8_t *)arena)[0x100] == 0xa5, "settling preserves live bytes");
  CHECK(api->unmap(base + 0x10000, 0x4000) == KERN_SUCCESS, "scratchpad restored atomically");
  CHECK(api->unmap(base + 0x10000, 0x4000) == KERN_SUCCESS, "duplicate masked alias is harmless");
  CHECK(api->end(arena, bytes) == KERN_SUCCESS, "remaining views and backing released");
  CHECK(!CanTake(base + 0x08000000, ramBytes), "RAM reserved again after shutdown");
  CHECK([LibretroPPSSPPReservationReport() containsString:@"continuously reserved"], "continuous ownership recorded");
}
#endif

int main(int argc, const char **argv) {
  @autoreleasepool {
    if (argc > 1 && strcmp(argv[1], "legacy") == 0) return LegacyCollision();
#ifndef PSP497_LEGACY_ONLY
    CHECK(LibretroPPSSPPReserveWindow(), "initial reservation");
    pressureBase = LibretroPPSSPPReservedBase();
    pthread_t pressure;
    CHECK(pthread_create(&pressure, NULL, Pressure, NULL) == 0, "allocator pressure started");
    for (unsigned i = 0; i < 16; i++) Cycle((i % 2 ? 64ull : 32ull) * 1024 * 1024, i % 5 == 4);
    atomic_store(&pressureDone, true);
    pthread_join(pressure, NULL);
    CHECK(atomic_load(&pressureIntrusions) == 0, "no transient hole during 16 pressured cycles");
    Cycle(76ull * 1024 * 1024, NO);
    Cycle(32ull * 1024 * 1024, NO);
    printf("%s PSP497_MANAGED_MEMORY cycles=18 allocatorIntrusions=%u\n",
           failures ? "FAIL" : "PASS", atomic_load(&pressureIntrusions));
#endif
    return failures ? 1 : 0;
  }
}
