// See MeloNXCoreLoaded.h. Plain C.
#import "MeloNXCoreLoaded.h"
#import <stdatomic.h>

// Kept and exported from the pod's framework: another package reads it through dlsym.
#define MELONX_CORE_LOADED_EXPORT __attribute__((visibility("default"), used))

static _Atomic int gLoading;

MELONX_CORE_LOADED_EXPORT int rb_melonx_core_loaded(void) { return atomic_load(&gLoading); }

MELONX_CORE_LOADED_EXPORT void rb_melonx_core_mark_loading(void) { atomic_store(&gLoading, 1); }
