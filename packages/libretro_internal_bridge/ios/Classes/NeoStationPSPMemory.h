// Versioned C ABI shared with the narrowly patched PPSSPP Darwin allocator.
// No C++ objects, platform-sized fields or ownership inferred from addresses.
#ifndef NEOSTATION_PSP_MEMORY_H
#define NEOSTATION_PSP_MEMORY_H
#include <stdint.h>
typedef struct NeoStationPSPMemoryCallbacks {
  uint32_t version;
  uint32_t structBytes;
  int (*begin)(uint64_t arenaBytes, uint64_t *arena, uint64_t *base);
  int (*map)(uint64_t source, uint64_t target, uint64_t bytes);
  int (*unmap)(uint64_t target, uint64_t bytes);
  int (*end)(uint64_t arena, uint64_t arenaBytes);
} NeoStationPSPMemoryCallbacks;
#endif
