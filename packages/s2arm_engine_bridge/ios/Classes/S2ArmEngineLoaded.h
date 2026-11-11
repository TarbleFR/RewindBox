#pragma once

// One NativeAOT engine per process (docs/s2arm-engine-bridge.md). S2ArmEngine.framework is opened with dlopen when a Switch 2
// game starts and never closed. MeloNX's bridge asks this flag through dlsym(RTLD_DEFAULT, "rb_s2arm_engine_loaded") and
// refuses to load MeloNXCore once it answers 1. The engine's constructor (patch 0003, vawin.c rb_guest_load) only checks that
// the symbol exists in the process, which tells it that RewindBox loaded it; the engine never defines it.
#ifdef __cplusplus
extern "C" {
#endif

/// 1 once this process has BEGUN loading S2ArmEngine (set before the dlopen, so a load that failed or crashed half-way
/// counts as well), 0 otherwise. Any thread.
int rb_s2arm_engine_loaded(void);

/// Called by the plugin right before it opens S2ArmEngine for the first time. Idempotent; the flag is never cleared.
void rb_s2arm_engine_mark_loading(void);

#ifdef __cplusplus
}
#endif
