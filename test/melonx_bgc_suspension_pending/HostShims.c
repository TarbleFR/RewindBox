/* Host stand-ins for the gate of adapt_bgc_suspension_pending (Linux, NativeAOT 10.0.0 linux-x64).
 *
 * The Core's RewindBoxRuntimeYield.c is compiled as it is in the tree under test (only the Mach-O label of
 * gc_background_running is given its ELF spelling) and linked into a NativeAOT executable with the official runtime
 * pack. It calls the two Mach traps; here both are the kernel's sched_yield, and each call notes what the collector's
 * g_fSuspensionPending read. A plain thread of this file (unknown to the runtime, so never stopped by it) samples
 * RhpTrapThreads every 250 microseconds while a background collection runs: the suspensions that begin inside one,
 * and the longest time the engine's threads were being stopped or held stopped there. One line on stderr at exit.
 */
#define _GNU_SOURCE
#include <pthread.h>
#include <stdio.h>
#include <time.h>
#include <unistd.h>
#include <sys/syscall.h>

extern volatile unsigned int RhpTrapThreads;
extern volatile int g_fSuspensionPending;
extern volatile int background_running __asm__("_ZN3WKS7gc_heap21gc_background_runningE");

static volatile long depressed, depressed_flag, plain, plain_flag;
static volatile long inside, longest_us, flag_seen, samples_background, samples_background_flag;
static volatile int stop;
static pthread_t monitor;

int thread_switch(unsigned int thread_name, int option, unsigned int option_time)
{
    __sync_fetch_and_add(&plain, 1);
    if (g_fSuspensionPending != 0) __sync_fetch_and_add(&plain_flag, 1);
    return (int)syscall(SYS_sched_yield);
}

int swtch_pri(int pri)
{
    __sync_fetch_and_add(&depressed, 1);
    if (g_fSuspensionPending != 0) __sync_fetch_and_add(&depressed_flag, 1);
    return (int)syscall(SYS_sched_yield);
}

static long now_us(void)
{
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec * 1000000L + t.tv_nsec / 1000;
}

static void* watch(void* unused)
{
    struct timespec nap = {0, 250000};
    int held = 0, counted = 0, was_background = 0;
    long since = 0;
    while (!stop) {
        nanosleep(&nap, 0);
        int background = background_running != 0, trap = RhpTrapThreads != 0u;
        if (g_fSuspensionPending != 0) flag_seen = 1;
        if (background) {
            samples_background++;
            if (g_fSuspensionPending != 0) samples_background_flag++;
        }
        /* A suspension that begins while the background collection already runs (not the one that starts it). */
        if (trap && !held && background && was_background) { counted = 1; since = now_us(); inside++; }
        if (trap && counted) { long us = now_us() - since; if (us > longest_us) longest_us = us; }
        if (!trap) counted = 0;
        held = trap;
        was_background = background;
    }
    return 0;
}

__attribute__((constructor)) static void start(void) { pthread_create(&monitor, 0, watch, 0); }

__attribute__((destructor)) static void report(void)
{
    stop = 1;
    fprintf(stderr, "SHIM swtchPri=%ld swtchPriWithFlag=%ld threadSwitch=%ld threadSwitchWithFlag=%ld flagSeen=%ld "
            "suspensionsInsideBackground=%ld longestInsideMs=%.1f backgroundSamples=%ld backgroundSamplesWithFlag=%ld\n",
            depressed, depressed_flag, plain, plain_flag, flag_seen, inside, longest_us / 1000.0,
            samples_background, samples_background_flag);
}
