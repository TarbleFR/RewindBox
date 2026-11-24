#import "LibretroJit.h"

#import "LibretroJitArena.h"
#import "RewindBoxLibretroJit.h"

#include <dlfcn.h>
#include <unistd.h>

int csops(pid_t pid, unsigned int ops, void *useraddr, size_t usersize);

#ifndef CS_OPS_STATUS
#define CS_OPS_STATUS 0
#endif
#ifndef CS_DEBUGGED
#define CS_DEBUGGED 0x10000000
#endif

BOOL LibretroHostIsDebugged(void) {
  uint32_t flags = 0;
  if (csops(getpid(), CS_OPS_STATUS, &flags, sizeof(flags)) != 0) return NO;
  return (flags & CS_DEBUGGED) != 0;
}

BOOL LibretroJitUsableByCores(void) {
  if (@available(iOS 26.0, *)) return NO;
  return LibretroHostIsDebugged();
}

BOOL LibretroJitInstallIntoLibrary(void *library) {
  return LibretroJitInstallIntoLibraryWithReason(library, NULL);
}

BOOL LibretroJitInstallIntoLibraryWithReason(void *library, NSString **reason) {
  if (reason != NULL) *reason = nil;
  if (library == NULL) {
    if (reason != NULL) *reason = @"RB_JIT_CORE_SYMBOL: no core library";
    return NO;
  }
  if (!libretro_jit_arena_ready()) {
    if (reason != NULL) *reason = @"RB_JIT_ARENA_NOT_READY: no proven code arena for this launch";
    return NO;
  }
  RewindBoxLibretroJitInstall install =
      (RewindBoxLibretroJitInstall)dlsym(library, REWINDBOX_LIBRETRO_JIT_INSTALL_SYMBOL);
  if (install == NULL) {
    if (reason != NULL) *reason = @"RB_JIT_CORE_SYMBOL: the core does not export " REWINDBOX_LIBRETRO_JIT_INSTALL_SYMBOL;
    return NO;
  }
  const int answer = install(libretro_jit_arena_interface());
  if (answer != 0) {
    if (reason != NULL) *reason = [NSString stringWithFormat:@"RB_JIT_CORE_REFUSED: install=%d", answer];
    return NO;
  }
  libretro_jit_arena_note_installed();
  return YES;
}

NSString *LibretroJitArenaReport(void) {
  LibretroJitArenaStats stats;
  libretro_jit_arena_stats(&stats);
  static NSString *const states[] = {@"off", @"attached", @"ready", @"failed"};
  NSString *state = stats.state >= 0 && stats.state <= 3 ? states[stats.state] : @"unknown";
  return [NSString stringWithFormat:@"[rb-jit] arena=%@ mode=%@ capacity=%llu used=%llu blocks=%u refused=%u "
                                    @"commands=%u probe=%d nonce=%d detached=%d installed=%d prepare_ms=%llu%@%@",
                                    state, stats.universal ? @"universal" : @"classic",
                                    (unsigned long long)stats.capacity, (unsigned long long)stats.used, stats.blocks,
                                    stats.refusedBlocks, stats.commands, stats.executableProbe, stats.nonceProbe,
                                    stats.detached, stats.installed, (unsigned long long)stats.prepareMilliseconds,
                                    stats.failure[0] != 0 ? @" failure=" : @"",
                                    stats.failure[0] != 0 ? @(stats.failure) : @""];
}
