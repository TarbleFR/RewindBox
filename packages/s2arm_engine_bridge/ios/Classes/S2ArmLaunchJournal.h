#pragma once
// Synchronous step journal of the Switch 2 engine bridge: one JSON object per line, appended with write(2) and made durable
// with fsync(2) before the call returns, because the next step (dlopen, a JIT command, the engine's start) may end the
// process. Sizes, addresses, durations and result codes only: never a path, a title or anything read from a game.
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/// Absolute path of the journal file (Documents/Diagnostics/Switch2/S2Arm-launch.log for a launch). Missing parent
/// directories are created. Returns 0, or -1 when the path is not absolute or too long (the journal then stays off).
int s2arm_journal_open(const char *path);

/// One line: {"t":"<UTC ISO-8601 with ms>","pid":N,"seq":N,"step":"<step>","status":"<status>"[,<fields>]}.
/// step and status are fixed tokens (escaped anyway). fields is a printf format producing JSON members without braces,
/// e.g. "\"bytes\":%llu,\"at\":\"%#llx\"", or NULL. Thread-safe. Silently does nothing while the journal is off.
void s2arm_journal(const char *step, const char *status, const char *fields, ...) __attribute__((format(printf, 3, 4)));

/// Number of lines written since the journal was opened (tests and the plugin's status).
unsigned long s2arm_journal_lines(void);

#ifdef __cplusplus
}
#endif
