#include "LibretroCrashCapture.h"
#include <assert.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>

static void ExistingReporter(int number) { (void)number; }

int main(int argc, char **argv) {
  assert(argc == 2);
  // Existing reporters must keep ownership of their signals.
  struct sigaction existing = {0}, found;
  existing.sa_handler = ExistingReporter;
  sigemptyset(&existing.sa_mask);
  assert(sigaction(SIGILL, &existing, NULL) == 0);
  int descriptor = open(argv[1], O_RDWR | O_CREAT | O_TRUNC | O_APPEND, 0600);
  assert(descriptor >= 0);
  unsigned mask = LibretroInstallCrashCapture(descriptor);
  assert((mask & (1u << 3)) == 0);
  assert(sigaction(SIGILL, NULL, &found) == 0 && found.sa_handler == ExistingReporter);
  const int signals[] = {SIGABRT, SIGBUS, SIGFPE, SIGSEGV};
  for (size_t i = 0; i < sizeof(signals)/sizeof(signals[0]); i++) {
    pid_t child = fork();
    assert(child >= 0);
    if (child == 0) { raise(signals[i]); _exit(99); }
    int status;
    assert(waitpid(child, &status, 0) == child);
    assert(WIFSIGNALED(status) && WTERMSIG(status) == signals[i]);
  }
  assert(lseek(descriptor, 0, SEEK_SET) == 0);
  char bytes[2048] = {0};
  assert(read(descriptor, bytes, sizeof(bytes)-1) > 0);
  unsigned lines = 0;
  for (char *p = bytes; *p; p++) if (*p == '\n') lines++;
  assert(lines == 4 && strstr(bytes, "fatal signal=0x") && strstr(bytes, " code=0x") && strstr(bytes, " pc=0x"));
  LibretroUninstallCrashCapture();
  assert(sigaction(SIGSEGV, NULL, &found) == 0 && found.sa_handler == SIG_DFL);
  assert(sigaction(SIGILL, NULL, &found) == 0 && found.sa_handler == ExistingReporter);
  // An unrelated emulator after the session closes must not acquire the
  // preceding libretro session's identity in this diagnostic file.
  pid_t later = fork();
  assert(later >= 0);
  if (later == 0) { raise(SIGABRT); _exit(99); }
  int status;
  assert(waitpid(later, &status, 0) == later && WIFSIGNALED(status) && WTERMSIG(status) == SIGABRT);
  assert(lseek(descriptor, 0, SEEK_END) == (off_t)strlen(bytes));
  close(descriptor);
  puts("PASS: four fatal signals captured and preserved; reporter untouched; closed-session handler removed");
  return 0;
}
