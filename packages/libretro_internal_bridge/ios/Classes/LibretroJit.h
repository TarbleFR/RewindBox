#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

/// True when the kernel reports CS_DEBUGGED for NeoStation's own process.
FOUNDATION_EXPORT BOOL LibretroHostIsDebugged(void);

/// What RETRO_ENVIRONMENT_GET_JIT_CAPABLE reports to a core that allocates
/// executable memory itself (no RewindBox JIT interface): only while the
/// process is debugged and the OS does not require the iOS 26 debugger
/// handshake that NeoStation performs for its other engines. The answer is
/// measured at launch, never inferred from a previous session or an
/// available route.
FOUNDATION_EXPORT BOOL LibretroJitUsableByCores(void);

/// After dlopen, before retro_set_environment and retro_init: hands the code
/// arena prepared for this session (LibretroJitArena.h, prepared by the
/// libretro JIT helper transaction before the launch) to a core that exports
/// rewindbox_libretro_jit_install (RewindBoxLibretroJit.h). YES only when
/// the arena is ready, its probes passed in this process, and the core
/// accepted version 1; the core may then generate code for the session.
FOUNDATION_EXPORT BOOL LibretroJitInstallIntoLibrary(void *library);

/// LibretroJitInstallIntoLibrary that names, on a NO, why the core did not
/// get the arena: RB_JIT_ARENA_NOT_READY (no arena prepared for this launch,
/// or not proven; its state and failure follow), RB_JIT_CORE_SYMBOL (the
/// core does not export the install function) or RB_JIT_CORE_REFUSED (the
/// core's install function answered `install=<value>`).
FOUNDATION_EXPORT BOOL LibretroJitInstallIntoLibraryWithReason(void *library, NSString *_Nullable *_Nullable reason);

/// The arena's facts for the session journal and the diagnostics (state,
/// mode, capacity, used, commands, probes, detach, installed, failure).
FOUNDATION_EXPORT NSString *LibretroJitArenaReport(void);

NS_ASSUME_NONNULL_END
