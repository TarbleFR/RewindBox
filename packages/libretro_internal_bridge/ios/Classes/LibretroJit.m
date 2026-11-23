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
  if (library == NULL || !libretro_jit_arena_ready()) return NO;
  RewindBoxLibretroJitInstall install =
      (RewindBoxLibretroJitInstall)dlsym(library, REWINDBOX_LIBRETRO_JIT_INSTALL_SYMBOL);
  if (install == NULL) return NO;
  if (install(libretro_jit_arena_interface()) != 0) return NO;
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
