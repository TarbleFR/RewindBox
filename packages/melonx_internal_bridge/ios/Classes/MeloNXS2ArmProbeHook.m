// S2Arm diagnostic hook of the MeloNX JIT transaction (session 04's probe, packages/s2arm_probe; spec of 10 Nov,
// docs/s2arm-prototype-2026-11-10.md "Step 3" on work/s2arm-switch2-prototype-20261110). Off every player path: the
// host calls it only when the IPA's Info.plist sets RewindBoxS2ArmProbe (a test IPA built by the principal session),
// only for the first JIT transaction of the process, and only with the universal helper attached.
//
// Phase 1 (helper attached, after the Core load handoff, before the Core prepares its arena): the probe asks the helper
// for regions through command 1 (brk #0xf00d, x16 = 1, x0 = address or 0, x1 = length), the same trap the Core uses.
// Phase 2 (after the helper detached, before the guest memory lease and any guest thread): the probe runs its module.
// Neither phase changes the launch: whatever they return, the game starts as before (the process may end in the
// "self mapped" variant, RewindBoxS2ArmProbeMapped, which the spec marks as possibly fatal on iOS 26).
//
// The probe is found without a link dependency (NSClassFromString); an absent class is one journal line. Every line
// is appended to MeloNX-launch.log with one write(2) and fsync(2) before the call returns: the next step may end the
// process. The helper script answers a refused allocation with "Exx", which its x0 = 0 path returns as an address
// (melonx-universal.js is pinned, so the check is here): a returned region below 64 KiB, not 16 KiB aligned, above
// 2^48 or other than the address asked for counts as a refusal (0).
#import "MeloNXS2ArmProbeHook.h"
#import <Foundation/Foundation.h>
#import <objc/message.h>

#include <errno.h>
#include <fcntl.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

typedef uint64_t (*MeloNXS2ArmPrepareFn)(uint64_t address, uint64_t length);
typedef void (*MeloNXS2ArmLogFn)(const char *step, const char *status, const char *detail);
typedef int (*MeloNXS2ArmAttachedFn)(MeloNXS2ArmPrepareFn prepare, MeloNXS2ArmLogFn log, uint32_t flags);
typedef int (*MeloNXS2ArmDetachedFn)(MeloNXS2ArmLogFn log);

static char g_journal[1024];
static atomic_int g_phase1Result = -2; // -2: phase 1 not run (phase 2 is then not run either)
static MeloNXS2ArmDetachedFn g_detached;

#if defined(__arm64__)
// Same protocol trampoline as the Core's rewindbox_melonx_jit_map (native/melonx/jit/MeloNXJitSupport.S).
__attribute__((naked, noinline)) static uint64_t MeloNXS2ArmPrepareTrap(uint64_t address, uint64_t length) {
  __asm__("mov x16, #1\n" "brk #0xf00d\n" "ret");
}
#endif

// The region the helper returned, or 0 when it is not a region it prepared.
uint64_t MeloNXS2ArmCheckedRegion(uint64_t requested, uint64_t returned) {
  if (returned < 0x10000 || (returned & 0x3fff) != 0 || returned > 0x0000ffffffffffffULL) return 0;
  if (requested != 0 && returned != requested) return 0;
  return returned;
}

static uint64_t MeloNXS2ArmPrepare(uint64_t address, uint64_t length) {
#if defined(__arm64__)
  if (length == 0) return 0; // (0, 0) is the helper's capability probe, never a region
  return MeloNXS2ArmCheckedRegion(address, MeloNXS2ArmPrepareTrap(address, length));
#else
  (void)address; (void)length;
  return 0;
#endif
}

static size_t MeloNXS2ArmEscape(char *out, size_t room, const char *text) {
  size_t used = 0;
  for (const unsigned char *p = (const unsigned char *)(text ? text : ""); *p && used + 7 < room; p++) {
    if (*p == '"' || *p == '\\') { out[used++] = '\\'; out[used++] = (char)*p; }
    else if (*p < 0x20) { used += (size_t)snprintf(out + used, room - used, "\\u%04x", *p); }
    else out[used++] = (char)*p;
  }
  out[used] = 0;
  return used;
}

// The launch journal's line format ([MeloNX:native] + JSON with sorted keys), durable on return.
void MeloNXS2ArmLog(const char *step, const char *status, const char *detail) {
  if (g_journal[0] == 0) return;
  char stage[160], escapedStatus[160], escapedDetail[2048], timestamp[32], line[2560];
  char name[96];
  snprintf(name, sizeof name, "s2armProbe.%s", step ? step : "?");
  MeloNXS2ArmEscape(stage, sizeof stage, name);
  MeloNXS2ArmEscape(escapedStatus, sizeof escapedStatus, status);
  MeloNXS2ArmEscape(escapedDetail, sizeof escapedDetail, detail);
  time_t now = time(NULL);
  struct tm utc;
  gmtime_r(&now, &utc);
  strftime(timestamp, sizeof timestamp, "%Y-%m-%dT%H:%M:%SZ", &utc);
  int length = snprintf(line, sizeof line,
                        "[MeloNX:native] {\"diagnostic\":\"%s\",\"nativeStatus\":0,\"pid\":%d,\"stage\":\"%s\",\"status\":\"%s\","
                        "\"timestamp\":\"%s\"}\n", escapedDetail, (int)getpid(), stage, escapedStatus, timestamp);
  if (length <= 0) return;
  if ((size_t)length >= sizeof line) { length = (int)sizeof line - 1; line[length - 1] = '\n'; }
  int fd = open(g_journal, O_WRONLY | O_APPEND | O_CREAT | O_CLOEXEC, 0600);
  if (fd < 0) return;
  ssize_t offset = 0;
  while (offset < length) {
    ssize_t count = write(fd, line + offset, (size_t)(length - offset));
    if (count < 0 && errno == EINTR) continue;
    if (count <= 0) break;
    offset += count;
  }
  fsync(fd);
  close(fd);
}

static void *MeloNXS2ArmFunction(Class probe, SEL selector) {
  if (probe == Nil || ![probe respondsToSelector:selector]) return NULL;
  return ((void *(*)(id, SEL))objc_msgSend)((id)probe, selector);
}

int MeloNXS2ArmProbeAttached(const char *journalPath, uint32_t flags) {
  if (journalPath == NULL || journalPath[0] != '/' || strlen(journalPath) >= sizeof g_journal) return -2;
  strncpy(g_journal, journalPath, sizeof g_journal - 1);
  int expected = -2;
  if (!atomic_compare_exchange_strong(&g_phase1Result, &expected, -1)) {
    MeloNXS2ArmLog("hook", "skipped", "phase 1 already ran in this process (one JIT transaction per process)");
    return -2;
  }
  Class probe = NSClassFromString(@"S2ArmProbePlugin");
  MeloNXS2ArmAttachedFn attached = (MeloNXS2ArmAttachedFn)MeloNXS2ArmFunction(probe, NSSelectorFromString(@"attachedFunction"));
  g_detached = (MeloNXS2ArmDetachedFn)MeloNXS2ArmFunction(probe, NSSelectorFromString(@"detachedFunction"));
  if (attached == NULL || g_detached == NULL) {
    MeloNXS2ArmLog("hook", "absent", probe == Nil ? "S2ArmProbePlugin is not in this app" : "S2ArmProbePlugin gave no function");
    atomic_store(&g_phase1Result, -1);
    return -1;
  }
  char detail[96];
  snprintf(detail, sizeof detail, "phase 1 begins, flags 0x%x", flags);
  MeloNXS2ArmLog("hook", "phase1", detail);
  int result = attached(MeloNXS2ArmPrepare, MeloNXS2ArmLog, flags);
  snprintf(detail, sizeof detail, "phase 1 returned %d", result);
  MeloNXS2ArmLog("hook", "phase1Done", detail);
  atomic_store(&g_phase1Result, result);
  return result;
}

int MeloNXS2ArmProbeDetached(void) {
  int phase1 = atomic_load(&g_phase1Result);
  if (phase1 < 0 || g_detached == NULL) return -2;
  MeloNXS2ArmLog("hook", "phase2", "phase 2 begins (helper detached)");
  int result = g_detached(MeloNXS2ArmLog);
  char detail[64];
  snprintf(detail, sizeof detail, "phase 2 returned %d", result);
  MeloNXS2ArmLog("hook", "phase2Done", detail);
  g_detached = NULL;
  return result;
}
