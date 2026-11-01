#pragma once
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
// Host-owned preparation. No constructors are added to any emulator Core.
// Start is asynchronous. WaitReady never blocks the UI thread and never
// changes the normal allocation fallback when preparation is unavailable.
__attribute__((visibility("default"))) void NeoSwapRelay_Start(void);
// Schedules bounded cleanup and preparation retries on the host worker.
__attribute__((visibility("default"))) void NeoSwapRelay_Maintain(void);
__attribute__((visibility("default"))) int NeoSwapRelay_WaitReady(uint32_t timeout_ms);
// Build 610: WaitReady for an imminent RPCS3 boot. A relay still ready from the
// previous session is kept until the next session is observed (never stopped by
// idle maintenance in between); everything else is WaitReady.
__attribute__((visibility("default"))) int NeoSwapRelay_PrepareForBoot(uint32_t timeout_ms);
// Budget controller output: live-byte ceiling of relay HOST loans (owner 1).
// Zero means capacity-bound only. Lowering it never revokes live loans.
__attribute__((visibility("default"))) int NeoSwapRelay_SetHostLoanQuota(uint64_t bytes);
#ifdef __cplusplus
}
#endif
#ifdef __OBJC__
@class NSDictionary;
NSDictionary* NeoSwapRelay_Diagnostics(void);
#endif
