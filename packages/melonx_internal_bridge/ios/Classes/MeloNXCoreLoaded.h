#pragma once

// One NativeAOT engine per process. MeloNXCore is loaded with dlopen(RTLD_LOCAL) and never unloaded, so another engine
// of the same kind (the Switch 2 engine of packages/s2arm_*) cannot find it by name: it asks this instead.
#ifdef __cplusplus
extern "C" {
#endif

/// 1 once this process has BEGUN loading MeloNXCore (set before the first dlopen, so a load that failed or crashed
/// half-way counts as well), 0 otherwise. Any thread; visible to dlsym(RTLD_DEFAULT, "rb_melonx_core_loaded").
int rb_melonx_core_loaded(void);

/// Called by the plugin right before it loads MeloNXCore for the first time. Idempotent.
void rb_melonx_core_mark_loading(void);

#ifdef __cplusplus
}
#endif
