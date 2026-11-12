// See S2ArmEngineLoaded.h. Plain C, same contract as MeloNXCoreLoaded.m (packages/melonx_internal_bridge).
#include "S2ArmEngineLoaded.h"
#include <stdatomic.h>

// Kept and exported from the pod's framework: MeloNX's bridge and the engine look it up through dlsym.
#define S2ARM_ENGINE_LOADED_EXPORT __attribute__((visibility("default"), used))

static _Atomic int gLoading;

S2ARM_ENGINE_LOADED_EXPORT int rb_s2arm_engine_loaded(void) { return atomic_load(&gLoading); }

S2ARM_ENGINE_LOADED_EXPORT void rb_s2arm_engine_mark_loading(void) { atomic_store(&gLoading, 1); }
