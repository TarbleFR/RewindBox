// Test dylib only. Fill fresh Nestopia C++ allocations BEFORE construction.
// dyld's buildInterposingTables deliberately skips non-dylib images.
// No core instructions, fields, callbacks or reset behavior are patched.
#include <atomic>
#include <cstdio>
#include <cstring>
#include <dlfcn.h>
#include <new>

static std::atomic<unsigned> poisoned{0};
static void *fill(void *allocation, std::size_t size, const void *caller) {
  Dl_info image{};
  if (dladdr(caller, &image) && image.dli_fname &&
      std::strstr(image.dli_fname, "nestopia_libretro.framework/")) {
    std::memset(allocation, 0xaa, size);
    unsigned count = ++poisoned;
    if (count <= 8) std::fprintf(stderr, "NESTOPIA_CPP_POISON allocation=%u bytes=%zu\n", count, size);
  }
  return allocation;
}
static void *scalar(std::size_t size) {
  return fill(::operator new(size), size, __builtin_return_address(0));
}
static void *array(std::size_t size) {
  return fill(::operator new[](size), size, __builtin_return_address(0));
}
using Allocate = void *(*)(std::size_t);
__attribute__((used, section("__DATA,__interpose")))
static const struct { Allocate replacement; Allocate original; } interpositions[] = {
  {scalar, static_cast<Allocate>(&::operator new)},
  {array, static_cast<Allocate>(&::operator new[])}
};
extern "C" unsigned nestopia_poisoned_allocations() { return poisoned.load(); }
