#pragma once
#include <stdint.h>
// S2Arm diagnostic hook (MeloNXS2ArmProbeHook.m): test IPAs only (Info.plist RewindBoxS2ArmProbe). Phase 1 while the
// universal helper is attached, before the Core prepares its arena; phase 2 after the detach. Results never change
// the launch. Returns: the probe's result, -1 probe absent, -2 not run.
#ifdef __cplusplus
extern "C" {
#endif
int MeloNXS2ArmProbeAttached(const char* _Nullable journalPath, uint32_t flags);
int MeloNXS2ArmProbeDetached(void);
// The region the helper returned for a request (address 0: any), or 0 when it is not one it prepared.
uint64_t MeloNXS2ArmCheckedRegion(uint64_t requested, uint64_t returned);
#ifdef __cplusplus
}
#endif
