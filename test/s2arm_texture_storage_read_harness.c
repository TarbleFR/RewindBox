// Runs rb_span_readable and rb_span_copy of engine patch 0016, as written in the patch (the test extracts them into
// rb_span.inc), over real pages of this process. The two Mach calls they use are stood in for by this host's own
// means: vm_region_64 by /proc/self/maps (the mapping that holds an address, or the next one), vm_read_overwrite by a
// pipe (the kernel copies from the address and refuses what the process cannot read: an error, not a fault, which is
// what the engine relies on). What the game does with the result is only known from a device log.
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

typedef uintptr_t vm_address_t;
typedef uintptr_t vm_size_t;
typedef int kern_return_t;
typedef unsigned mach_port_t;
typedef unsigned mach_msg_type_number_t;
typedef struct { int protection, max_protection; } vm_region_basic_info_data_64_t;
typedef int *vm_region_info_t;
#define KERN_SUCCESS 0
#define VM_PROT_READ 1
#define VM_REGION_BASIC_INFO_64 9
#define VM_REGION_BASIC_INFO_COUNT_64 ((mach_msg_type_number_t)(sizeof(vm_region_basic_info_data_64_t) / sizeof(int)))
#define MACH_PORT_NULL 0
#define MIN(a, b) ((a) < (b) ? (a) : (b))
static mach_port_t mach_task_self(void) { return 1; }

static unsigned long g_region_calls, g_read_calls;
static kern_return_t vm_region_64(mach_port_t task, vm_address_t *address, vm_size_t *size, int flavor, vm_region_info_t info, mach_msg_type_number_t *count, mach_port_t *object) {
    (void)task; (void)flavor; (void)count; (void)object;
    g_region_calls++;
    FILE *maps = fopen("/proc/self/maps", "r");
    if (!maps) return 1;
    char line[512];
    kern_return_t result = 1;
    while (fgets(line, sizeof line, maps)) {
        unsigned long lo, hi;
        char perms[8];
        if (sscanf(line, "%lx-%lx %7s", &lo, &hi, perms) != 3 || hi <= *address) continue;
        *address = lo;
        *size = hi - lo;
        ((vm_region_basic_info_data_64_t *)info)->protection = perms[0] == 'r' ? VM_PROT_READ : 0;
        result = KERN_SUCCESS;
        break;
    }
    fclose(maps);
    return result;
}

static int g_pipe[2];
static kern_return_t vm_read_overwrite(mach_port_t task, vm_address_t address, vm_size_t size, vm_address_t data, vm_size_t *got) {
    (void)task;
    g_read_calls++;
    *got = 0;
    for (vm_size_t done = 0; done < size;) {
        size_t chunk = MIN(size - done, (vm_size_t)16384);   // well inside the pipe's capacity
        ssize_t written = write(g_pipe[1], (const void *)(address + done), chunk);
        if (written < 0) return 2;   // EFAULT: the process cannot read there
        if (read(g_pipe[0], (void *)(data + done), (size_t)written) != written) return 3;
        if ((size_t)written != chunk) return 2;   // stopped at a page it cannot read
        done += chunk;
    }
    *got = size;
    return KERN_SUCCESS;
}

static uintptr_t g_far_lo, g_far_hi;
static uint8_t *s2a_far_g2h(uint64_t a) { return a >= g_far_lo && a < g_far_hi ? (uint8_t *)1 : NULL; }

#include "rb_span.inc"

static int g_failures, g_checks;
#define CHECK(condition, ...) do { g_checks++; if (!(condition)) { g_failures++; printf("FAIL line %d: ", __LINE__); printf(__VA_ARGS__); printf("\n"); } } while (0)

// Whether dst is what the engine must give for [a, a + n): the source's bytes where `readable` says so, zeros elsewhere
static int same(const uint8_t *dst, const uint8_t *shadow, uintptr_t base, uintptr_t a, uint64_t n, const int *readable, uintptr_t pg) {
    for (uint64_t o = 0; o < n; o++) {
        uintptr_t at = a + o - base;
        uint8_t want = readable[at / pg] ? shadow[at] : 0;
        if (dst[o] != want) return 0;
    }
    return 1;
}

int main(void) {
    uintptr_t pg = (uintptr_t)getpagesize();
    enum { PAGES = 12 };
    if (pipe(g_pipe)) { perror("pipe"); return 2; }
    // A reservation with a guard page on each side, so that neighbours of this process never make the block's ends readable
    uint8_t *reservation = mmap(NULL, (PAGES + 2) * pg, PROT_NONE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (reservation == MAP_FAILED) { perror("mmap"); return 2; }
    uint8_t *block = reservation + pg;
    if (mprotect(block, PAGES * pg, PROT_READ | PROT_WRITE)) { perror("mprotect"); return 2; }
    uint8_t *shadow = malloc(PAGES * pg), *dst = malloc(PAGES * pg);
    for (uintptr_t i = 0; i < PAGES * pg; i++) block[i] = shadow[i] = (uint8_t)(1 + (i * 131 + (i >> 9)) % 251);   // never 0
    int readable[PAGES];
    for (int i = 0; i < PAGES; i++) readable[i] = 1;
    uintptr_t base = (uintptr_t)block;
    uint64_t first = 99;

    // 1. everything readable: nothing to copy, and the copy is the memory
    CHECK(rb_span_readable(base, PAGES * pg), "a readable block");
    CHECK(rb_span_readable(base + 100, 3 * pg + 77), "an unaligned readable range");
    CHECK(rb_span_readable(base, 0) && rb_span_readable(0, 0), "an empty range reads");
    CHECK(rb_span_copy(dst, base, PAGES * pg, &first) == 0 && first == 0 && !memcmp(dst, shadow, PAGES * pg), "copy of a readable block");
    CHECK(rb_span_copy(dst, base, 0, &first) == 0, "copy of nothing");

    // 2. one page the process cannot read (page 5): the crash of 13 Nov was the first byte of such a page
    mprotect(block + 5 * pg, pg, PROT_NONE); readable[5] = 0;
    CHECK(!rb_span_readable(base, PAGES * pg), "a block with an unreadable page");
    CHECK(rb_span_readable(base, 5 * pg), "the pages before it, up to its first byte");
    CHECK(!rb_span_readable(base, 5 * pg + 1), "one byte into it");
    CHECK(!rb_span_readable(base + 5 * pg, 1) && !rb_span_readable(base + 6 * pg - 1, 1), "its first and last byte");
    CHECK(rb_span_readable(base + 6 * pg, (PAGES - 6) * pg), "the pages after it");
    memset(dst, 0xee, PAGES * pg);
    CHECK(rb_span_copy(dst, base, PAGES * pg, &first) == pg && first == 5 * pg, "copy: one page not read, first at its offset (got first %llu)", (unsigned long long)first);
    CHECK(same(dst, shadow, base, base, PAGES * pg, readable, pg), "copy: the unreadable page is zeros, every other byte is the memory's");
    // unaligned start and end
    memset(dst, 0xee, PAGES * pg);
    uint64_t n = 6 * pg + 77;
    CHECK(rb_span_copy(dst, base + 100, n, &first) == pg && first == 5 * pg - 100, "unaligned copy: the whole page 5, first at 5 pages - 100 (got %llu)", (unsigned long long)first);
    CHECK(same(dst, shadow, base, base + 100, n, readable, pg), "unaligned copy: bytes");
    // a range that ends inside the unreadable page: only the part of it in the range counts
    memset(dst, 0xee, PAGES * pg);
    n = 5 * pg + 300 - 100;
    CHECK(rb_span_copy(dst, base + 100, n, &first) == 300 && first == 5 * pg - 100, "a range ending 300 bytes into the unreadable page counts 300 (first %llu)", (unsigned long long)first);
    CHECK(same(dst, shadow, base, base + 100, n, readable, pg), "bytes of that range");
    // a range that starts inside it
    memset(dst, 0xee, PAGES * pg);
    CHECK(rb_span_copy(dst, base + 5 * pg + 10, pg, &first) == pg - 10 && first == 0, "a range starting inside it: its rest is not read, first at 0");
    CHECK(same(dst, shadow, base, base + 5 * pg + 10, pg, readable, pg), "bytes of that range");

    // 3. a second one, not adjacent (page 2), and one the game unmapped altogether (page 9: a hole, not a protection)
    mprotect(block + 2 * pg, pg, PROT_NONE); readable[2] = 0;
    munmap(block + 9 * pg, pg); readable[9] = 0;
    CHECK(!rb_span_readable(base + 8 * pg, 2 * pg) && rb_span_readable(base + 8 * pg, pg), "a hole is not readable, the page before it is");
    CHECK(!rb_span_readable(base + 9 * pg, 3 * pg), "a range that starts in a hole");
    memset(dst, 0xee, PAGES * pg);
    CHECK(rb_span_copy(dst, base, PAGES * pg, &first) == 3 * pg && first == 2 * pg, "three pages not read, the first at page 2 (got %llu)", (unsigned long long)first);
    CHECK(same(dst, shadow, base, base, PAGES * pg, readable, pg), "bytes with two unreadable pages and a hole");

    // 4. the last page of the storage unreadable, the storage ending inside it (a texture whose size runs past its memory)
    mprotect(block + 11 * pg, pg, PROT_NONE); readable[11] = 0;
    memset(dst, 0xee, PAGES * pg);
    n = pg + 123;
    CHECK(!rb_span_readable(base + 10 * pg, n), "storage that runs past readable memory");
    CHECK(rb_span_copy(dst, base + 10 * pg, n, &first) == 123 && first == pg, "its tail of 123 bytes is not read, first at one page");
    CHECK(same(dst, shadow, base, base + 10 * pg, n, readable, pg), "bytes of that storage");
    // past the end of everything this block holds: the guard page, then whatever follows
    CHECK(!rb_span_readable(base + 10 * pg, 3 * pg), "a range that runs into the guard page");

    // 5. two mappings of different protections side by side are one readable range
    mprotect(block, pg, PROT_READ);
    CHECK(rb_span_readable(base, 2 * pg), "a read-only page followed by a read-write one");

    // 6. far alias storage has no host pages: left to the engine's far reads, nothing is asked or copied
    g_far_lo = base + 5 * pg; g_far_hi = base + 6 * pg;
    unsigned long regions = g_region_calls;
    CHECK(rb_span_readable(base + 5 * pg, 16) && g_region_calls == regions, "a far address reads as before, without a region query");
    CHECK(rb_span_readable(base + 4 * pg, pg + 16) && g_region_calls == regions, "storage whose last byte is far, the same");
    g_far_lo = g_far_hi = 0;

    // 7. the usual case costs region queries only: no copy
    unsigned long reads = g_read_calls;
    CHECK(rb_span_readable(base + 6 * pg, 2 * pg) && g_read_calls == reads, "asking does not read");

    printf("%s %d checks, %d failed (page %lu bytes)\n", g_failures ? "FAILED" : "PASSED", g_checks, g_failures, (unsigned long)pg);
    return g_failures ? 1 : 0;
}
