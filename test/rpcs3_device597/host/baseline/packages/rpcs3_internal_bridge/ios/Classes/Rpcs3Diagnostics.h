#pragma once

#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

#ifdef __cplusplus
extern "C" {
#endif

// Ordinary diagnostics are serialized by one process-wide writer implemented
// in Rpcs3Diagnostics.mm. Keeping the implementation out of this header is
// essential: both the JIT bridge and the Core bridge write the same files.
FOUNDATION_EXPORT void RPCS3Diagnostic(
    NSString* _Nullable stage,
    NSString* _Nullable message);

// Crash-boundary milestones are synchronously persisted by that same writer.
FOUNDATION_EXPORT void RPCS3Milestone(
    NSString* _Nullable stage,
    NSString* _Nullable message);

// CELL546: detailed savestate restore steps (constructor and file stages, up
// to ~770 lines per restore) go to their own bounded file, written in order on
// the calling thread without fsync, so they never evict milestones or the
// ordinary journal and still reach the kernel before the next restore step.
FOUNDATION_EXPORT void RPCS3RestoreTrace(NSString* _Nullable message);

#if defined(RPCS3_DIAGNOSTICS_TESTING)
// Native regression tests redirect Documents and explicitly drain the
// asynchronous diagnostic queue. These symbols are absent from production.
FOUNDATION_EXPORT void RPCS3DiagnosticsSetDirectoryForTesting(
    NSString* directory);
FOUNDATION_EXPORT void RPCS3DiagnosticsFlushForTesting(void);
#endif

#ifdef __cplusplus
}  // extern "C"
#endif

NS_ASSUME_NONNULL_END
