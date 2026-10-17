#ifndef LIBRETRO_CRASH_CAPTURE_H
#define LIBRETRO_CRASH_CAPTURE_H

// Fatal-signal breadcrumbs only. No allocation, Objective-C, locks, stack
// unwinding or filesystem path resolution in the handler. Never catches
// SIGKILL (jetsam/watchdog), and never replaces an installed crash reporter.
#include <signal.h>
#include <stdint.h>
#include <time.h>
#include <unistd.h>
#if defined(__APPLE__)
#include <sys/ucontext.h>
#endif

static volatile sig_atomic_t LibretroCrashDescriptor = -1;

static inline size_t LibretroCrashHex(char *text, size_t at, uintptr_t value) {
  static const char digits[] = "0123456789abcdef";
  text[at++] = '0'; text[at++] = 'x';
  for (int shift = (int)(sizeof(value) * 8) - 4; shift >= 0; shift -= 4)
    text[at++] = digits[(value >> shift) & 15u];
  return at;
}

static void LibretroCaptureSignal(int number, siginfo_t *info, void *context) {
  char line[160] = "fatal signal=";
  size_t at = sizeof("fatal signal=") - 1;
  at = LibretroCrashHex(line, at, (uintptr_t)number);
  const char code[] = " code=";
  for (size_t i = 0; i < sizeof(code)-1; i++) line[at++] = code[i];
  at = LibretroCrashHex(line, at, info ? (uintptr_t)info->si_code : 0);
  const char address[] = " address=";
  for (size_t i = 0; i < sizeof(address)-1; i++) line[at++] = address[i];
  at = LibretroCrashHex(line, at, info && (number == SIGSEGV || number == SIGBUS || number == SIGILL || number == SIGFPE)
      ? (uintptr_t)info->si_addr : 0);
  uintptr_t pc = 0;
#if defined(__APPLE__) && defined(__aarch64__)
  if (context) pc = (uintptr_t)((ucontext_t *)context)->uc_mcontext->__ss.__pc;
#elif defined(__APPLE__) && defined(__x86_64__)
  if (context) pc = (uintptr_t)((ucontext_t *)context)->uc_mcontext->__ss.__rip;
#else
  (void)context;
#endif
  const char program[] = " pc=";
  for (size_t i = 0; i < sizeof(program)-1; i++) line[at++] = program[i];
  at = LibretroCrashHex(line, at, pc);
  line[at++] = '\n';
  int descriptor = LibretroCrashDescriptor;
  if (descriptor >= 0) {
    // One bounded append. A disk error must never turn a fault into a loop.
    ssize_t result = write(descriptor, line, at);
    (void)result;
  }
  // SA_RESETHAND has restored SIG_DFL. Preserve native fatal termination;
  // do not swallow the fault or resume the emulation session.
  // Thread-directed redelivery preserves the faulting thread. Process-wide
  // kill() could terminate an unrelated UIKit/audio thread instead.
  raise(number);
}

// Call once in normal process context. Descriptor stays open until exit;
// the handler cannot race descriptor closure/reuse in another session.
static inline unsigned LibretroInstallCrashCapture(int descriptor) {
  if (descriptor < 0) return 0;
  LibretroCrashDescriptor = descriptor;
  const int signals[] = {SIGABRT, SIGBUS, SIGFPE, SIGILL, SIGSEGV};
  unsigned installed = 0;
  for (size_t i = 0; i < sizeof(signals)/sizeof(signals[0]); i++) {
    struct sigaction previous;
    if (sigaction(signals[i], NULL, &previous) != 0 || previous.sa_handler != SIG_DFL) continue;
    struct sigaction action = {0};
    sigemptyset(&action.sa_mask);
    action.sa_sigaction = LibretroCaptureSignal;
    action.sa_flags = SA_SIGINFO | SA_RESETHAND;
    if (sigaction(signals[i], &action, NULL) == 0) installed |= 1u << i;
  }
  return installed;
}
#endif
