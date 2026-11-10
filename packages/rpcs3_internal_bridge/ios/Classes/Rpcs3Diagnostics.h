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

// REWINDBOX_CORE_LOG_BOUNDED_621: an admitted Core line, written
// asynchronously; reservedBytes are released from the admission backlog
// (Rpcs3CoreLogAdmission.h) once it is written.
FOUNDATION_EXPORT void RPCS3CoreLogLine(NSString* message, uint64_t reservedBytes);

// REWINDBOX_INCIDENT_REPORT_621 (Rpcs3IncidentReport.h).
// A fatal-level Core line: written at once to RPCS3-last-fatal.log (one
// write(2), kept through abort()), then to the incident model; gameStopped
// when the game cannot continue (thread terminated, guest fault).
FOUNDATION_EXPORT void RPCS3RecordFatalLine(const char* message, BOOL gameStopped);
// After a fatal line: waits at most timeoutMs for the journal queue to write
// what was queued before it (the Core may abort right after).
FOUNDATION_EXPORT void RPCS3DiagnosticsDrain(uint32_t timeoutMs);
// The host context of the running session: the RewindBox menu (which does not
// pause the PS3 emulation) and the app in the background.
FOUNDATION_EXPORT void RPCS3HostState(BOOL menuOpen, BOOL background);
// The session stopped cleanly: its record is marked stopped.
FOUNDATION_EXPORT void RPCS3SessionStopped(void);
// At launch: the incident file of a previous process that ended during a
// session, or nil.
FOUNDATION_EXPORT NSString* _Nullable RPCS3TakePreviousSessionIncident(void);
// Builds the shareable report (summary + bounded journal tails, streamed) in
// the temporary directory; completion on the main queue, nil on failure.
FOUNDATION_EXPORT void RPCS3BuildIncidentReport(void (^completion)(NSString* _Nullable path));

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

#ifdef __cplusplus
#include "Rpcs3CoreLogAdmission.h"
// REWINDBOX_CORE_LOG_BOUNDED_621: the process-wide admission of Core log lines.
rpcs3_host::core_log_admission& RPCS3CoreLogAdmissionShared();
#endif
