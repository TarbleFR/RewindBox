// Runs the device probe (packages/s2arm_probe) on macOS arm64 with a stand-in for
// the JIT helper, to check the probe's own logic before it reaches an iPhone.
// A pass here says nothing about what iOS allows.
#include "S2ArmProbe.h"
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>

static uint64_t fake_prepare(uint64_t address, uint64_t length) {
    if (address) return address;
    void *region = mmap(NULL, length, PROT_READ | PROT_EXEC, MAP_PRIVATE | MAP_ANON, -1, 0);
    return region == MAP_FAILED ? 0 : (uint64_t)region;
}

static void journal(const char *step, const char *status, const char *detail) {
    printf("[s2armProbe] %s %s %s\n", step, status, detail);
    fflush(stdout);
}

int main(int argc, char **argv) {
    int modes = rb_s2arm_probe_attached(fake_prepare, journal, argc > 1 ? (uint32_t)strtoul(argv[1], NULL, 0) : 0);
    int result = rb_s2arm_probe_detached(journal);
    printf("modes=%d result=%d\n", modes, result);
    return modes > 0 && result == 0 ? 0 : 1;
}
