// Host double of what the real DualMappedJitAllocator.cs calls on iOS: the JIT helper's trap protocol
// (native/melonx/jit/MeloNXJitSupport.S, packages/melonx_jit_helper/ios/Resources/melonx-universal.js) and the three
// Mach calls of the RW alias. A region is a memfd mapped RX; vm_remap maps the same pages RW, so code written through
// the RW alias is read and executed through the RX one, as on the device. "Preparing" a region costs a set time per
// 16 KiB page, either with every thread of the process stopped (SIGSTOP, what debugserver does while the helper's
// script handles a trap) or with only the calling thread waiting.
#define _GNU_SOURCE
#include <errno.h>
#include <signal.h>
#include <stdint.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#define PROTOCOL 0x5242574a49543031ULL
#define JIT_PAGE 16384ULL
#define MIB (1ULL << 20)

static struct { int fd; uint8_t *rx; uint64_t size; } regions[8];
static int region_count;
static long nanoseconds_per_page;
static int stop_mode, fail_mode, sized_attempted, detached;
static uint64_t counters[8]; // traps, pages, detaches, held microseconds, sized requests, aliases, traps after detach, regions

void helper_double_configure(long per_page_ns, int stop, int fail) { nanoseconds_per_page = per_page_ns; stop_mode = stop; fail_mode = fail; }
uint64_t helper_double_counter(int index) { return index >= 0 && index < 8 ? counters[index] : 0; }

static uint64_t now_us(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); return (uint64_t)t.tv_sec * 1000000ULL + t.tv_nsec / 1000; }
static void sleep_ns(uint64_t ns) { struct timespec t = { (time_t)(ns / 1000000000ULL), (long)(ns % 1000000000ULL) }; while (nanosleep(&t, &t) < 0 && errno == EINTR) { } }

static void hold(uint64_t ns)
{
    if (ns == 0) return;
    uint64_t start = now_us();
    if (stop_mode == 1)
    {
        pid_t parent = getpid(), child = fork();
        if (child == 0) { kill(parent, SIGSTOP); sleep_ns(ns); kill(parent, SIGCONT); _exit(0); }
        if (child > 0) { int status; while (waitpid(child, &status, 0) < 0 && errno == EINTR) { } }
    }
    else sleep_ns(ns);
    counters[3] += now_us() - start;
}

static uint8_t *allocate(uint64_t size)
{
    if (region_count == 8) return 0;
    int fd = memfd_create("jit-arena-double", 0);
    if (fd < 0 || ftruncate(fd, (off_t)size) != 0) return 0;
    uint8_t *rx = mmap(0, size, PROT_READ | PROT_EXEC, MAP_SHARED, fd, 0);
    if (rx == MAP_FAILED) return 0;
#if defined(__x86_64__)
    // The engine's probe writes two ARM64 instructions in the last 16 bytes and calls them. On this host the RX side
    // holds "mov eax, 0x4d4c; ret" there, and the RW alias gets a private last page (vm_remap below).
    if (size >= 4096)
    {
        uint8_t *tail = mmap(0, 4096, PROT_READ | PROT_WRITE, MAP_SHARED, fd, (off_t)(size - 4096));
        if (tail == MAP_FAILED) return 0;
        static const uint8_t probe[] = { 0xb8, 0x4c, 0x4d, 0x00, 0x00, 0xc3 };
        memcpy(tail + 4096 - 16, probe, sizeof probe);
        munmap(tail, 4096);
    }
#endif
    regions[region_count].fd = fd; regions[region_count].rx = rx; regions[region_count].size = size;
    region_count++; counters[7]++;
    return rx;
}

static void prepare(uint64_t size)
{
    uint64_t pages = (size - 1) / JIT_PAGE + 1;
    counters[1] += pages;
    hold(pages * (uint64_t)nanoseconds_per_page);
}

uint8_t *rewindbox_melonx_jit_map(uint8_t *address, size_t bytes)
{
    counters[0]++;
    if (detached) counters[6]++;
    if (address == 0 && bytes == 0) return fail_mode == 1 ? 0 : (uint8_t *)PROTOCOL;
    if (address != 0 && bytes == PROTOCOL)
    {
        uint64_t *fields = (uint64_t *)address;
        counters[4]++;
        if (fields[0] != PROTOCOL || fields[1] < 512 * MIB || fields[1] > 1024 * MIB || fields[1] % (64 * MIB) != 0 ||
            fields[2] != 512 * MIB || fields[3] != 64 * MIB || fields[4] || fields[5] || fields[6] || fields[7]) return 0;
        if (sized_attempted) { fields[6] = 4; return 0; }
        sized_attempted = 1;
        if (fail_mode == 2) { fields[7] = 9; fields[6] = 2; return 0; }
        uint8_t *region = allocate(fields[1]);
        if (region == 0) { fields[6] = 4; return 0; }
        fields[7] = 1; fields[4] = fields[1]; fields[5] = (uint64_t)region; fields[6] = 3;
        prepare(fields[1]);
        fields[6] = 1;
        if (fail_mode == 3) fields[5] ^= 0x4000;
        return region;
    }
    if (address == 0)
    {
        if (fail_mode == 5) return 0;
        uint8_t *region = allocate(bytes);
        if (region != 0) prepare(bytes);
        return region;
    }
    prepare(bytes);
    return address;
}

uint8_t *rewindbox_melonx_jit_mark(size_t bytes) { (void)bytes; counters[0]++; return (uint8_t *)0xE0000069ULL; }
void rewindbox_melonx_jit_detach(void) { counters[0]++; counters[2]++; detached = 1; }

uint64_t mach_task_self(void) { return 0x103; }

int vm_remap(uint64_t target_task, uint64_t *target, uint64_t size, uint64_t mask, int anywhere, uint64_t source_task,
             uint64_t source, int copy, uint32_t *current, uint32_t *maximum, int inheritance)
{
    (void)target_task; (void)mask; (void)anywhere; (void)source_task; (void)copy; (void)inheritance;
    if (fail_mode == 4) return 5;
    for (int i = 0; i < region_count; i++)
    {
        if ((uint64_t)regions[i].rx != source || regions[i].size != size) continue;
        uint8_t *rw = mmap(0, size, PROT_READ | PROT_WRITE, MAP_SHARED, regions[i].fd, 0);
        if (rw == MAP_FAILED) return 3;
#if defined(__x86_64__)
        if (size >= 4096 && mmap(rw + size - 4096, 4096, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0) == MAP_FAILED) return 3;
#endif
        *target = (uint64_t)rw; *current = 5; *maximum = 7;
        counters[5]++;
        return 0;
    }
    return 1;
}

int vm_protect(uint64_t task, uint64_t address, uint64_t size, int set_maximum, int protection)
{
    (void)task; (void)address; (void)size; (void)set_maximum; (void)protection;
    return 0;
}
