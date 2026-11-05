#pragma once

#ifdef __cplusplus
extern "C" {
#endif

/// Journal of fatal signals and exit() for the in-process MeloNX engine.
///
/// Its handlers are installed when this framework loads (before any engine), so it is the last handler of each fatal
/// signal: the NativeAOT runtime and Ryujinx's memory-tracking handler, installed later, handle their own faults first
/// and pass on only those they cannot handle. On a fatal signal it writes, with write(2), the signal, fault address,
/// thread, registers and a frame-pointer backtrace (image + offset) to the journal file, then the bytes still waiting
/// in the engine's stderr pipe (where the runtime's fatal message would otherwise be lost), restores the previous
/// action and returns, so the signal takes its usual course. exit() is journaled the same way. Nothing is written
/// before the file is opened.
///
/// Swift resolves these functions with dlsym (MeloNXCrashJournalLink in MeloNXStandaloneParity.swift).

/// Opens the journal file, once per process (when the diagnostics directory is configured). A NULL path or a second
/// call does nothing.
void MeloNXCrashJournalInstall(const char *_Nullable path);

/// The read end of the engine's stderr pipe (MeloNXStdioCapture), drained on a fatal signal; -1 when none.
void MeloNXCrashJournalSetStderrSource(int fd);

/// One line of context in the journal (a session's title, build and core), so a fatal record can be attributed.
void MeloNXCrashJournalNote(const char *_Nullable text);

#ifdef __cplusplus
}
#endif
