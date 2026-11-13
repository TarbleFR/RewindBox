// Harness of test/s2arm_vp_arena_test.py: runs runtime/src/rb_vparena.c (engine patch 0013) as the patch adds it, on the
// build machine (macOS runner or Linux). No engine header, no game: the arena is address space only.
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

void s2a_rb_vp_init(uint64_t base, uint64_t size);
int s2a_rb_vp_has(const void *p);
uint64_t s2a_rb_vp_size(void);
void *s2a_rb_vp_map(uint64_t len);
int s2a_rb_vp_unmap(void *p, uint64_t len);
void s2a_rb_vp_note(char *o, size_t cap);
uint64_t s2a_rb_host_arenas(uint64_t fit, uint64_t host_below, uint64_t need, uint64_t alias, uint64_t slack, uint64_t pool,
                            int alias_first, uint64_t tail_want, uint64_t vp_want, uint64_t *tail, uint64_t *vp);

#define MB (1ull << 20)
#define GB (1ull << 30)
#define PAGE 16384ull
static int bad, checks;
#define CHECK(c, ...) do { checks++; if (!(c)) { bad++; printf("FAIL "); printf(__VA_ARGS__); printf("\n"); } } while (0)

static int g_pipe[2];
// 1 when the byte at p can be read: a pipe write copies it from user memory (EFAULT on an inaccessible page, no signal)
static int readable(const void *p) { char c; if (write(g_pipe[1], p, 1) != 1) return 0; return read(g_pipe[0], &c, 1) == 1; }

int main(void) {
    if (pipe(g_pipe)) { printf("FAIL pipe errno %d\n", errno); return 1; }
    uint64_t tl, vp, n;

    // ---- how much the window gives up (pure) ----
    // Mario Kart World on iPhone17,2 (host.log of 13 Nov): hole 64512 MB, standard layout 75958 MB, application pool 9216 MB.
    n = s2a_rb_host_arenas(64512 * MB, 3 * GB, 75958 * MB, 63 * GB, 256 * MB + GB, 9216 * MB, 0, 2 * GB, 16 * GB, &tl, &vp);
    CHECK(tl == 2 * GB && vp == 16 * GB && n == 18 * GB, "the device of the report: 2 GiB tail + 16 GiB pools, got %llu + %llu MB", (unsigned long long)(tl >> 20), (unsigned long long)(vp >> 20));
    {   // what the window keeps there: the front regions and one pool of alias region, all with host addresses
        uint64_t window = 64512 * MB - 3 * GB - n, front = 75958 * MB - 63 * GB + 256 * MB + GB;
        CHECK(window == 42 * GB && window >= front + 9216 * MB, "window %llu MB keeps front %llu MB + one pool", (unsigned long long)(window >> 20), (unsigned long long)(front >> 20));
    }
    n = s2a_rb_host_arenas(64512 * MB, 3 * GB, 75958 * MB, 63 * GB, 256 * MB + GB, 9216 * MB, 1, 2 * GB, 16 * GB, &tl, &vp);
    CHECK(!n && !tl && !vp, "a game whose alias region is sized from the window gives nothing up");
    n = s2a_rb_host_arenas(64512 * MB, 3 * GB, 75958 * MB, 63 * GB, 256 * MB + GB, 0, 0, 2 * GB, 16 * GB, &tl, &vp);
    CHECK(!n && !tl && !vp, "an unknown application pool gives nothing up");
    n = s2a_rb_host_arenas(64512 * MB, 3 * GB, 33 * GB, 63 * GB, 256 * MB + GB, 9216 * MB, 0, 2 * GB, 16 * GB, &tl, &vp);
    CHECK(!n, "a layout without the 63 GiB alias commitment (heap mode) gives nothing up");
    // iPadOS 26 class hole (51 GiB): keep = 12726 + 9216 = 21942 MB; 52224 - 3072 - 21942 = 27210 MB -> 26 GiB of room
    n = s2a_rb_host_arenas(51 * GB, 3 * GB, 75958 * MB, 63 * GB, 256 * MB + GB, 9216 * MB, 0, 2 * GB, 16 * GB, &tl, &vp);
    CHECK(tl == 2 * GB && vp == 16 * GB, "51 GiB hole still holds both, got %llu + %llu MB", (unsigned long long)(tl >> 20), (unsigned long long)(vp >> 20));
    // a hole that only leaves 5 GiB of room: the tail first (thread stacks), the pools get the rest, whole GiB
    n = s2a_rb_host_arenas(3 * GB + 21942 * MB + 5 * GB + 300 * MB, 3 * GB, 75958 * MB, 63 * GB, 256 * MB + GB, 9216 * MB, 0, 2 * GB, 16 * GB, &tl, &vp);
    CHECK(tl == 2 * GB && vp == 3 * GB && n == 5 * GB, "5 GiB of room: 2 + 3, got %llu + %llu MB", (unsigned long long)(tl >> 20), (unsigned long long)(vp >> 20));
    n = s2a_rb_host_arenas(3 * GB + 21942 * MB + 900 * MB, 3 * GB, 75958 * MB, 63 * GB, 256 * MB + GB, 9216 * MB, 0, 2 * GB, 16 * GB, &tl, &vp);
    CHECK(!n && !tl && !vp, "less than 1 GiB of room: nothing");
    n = s2a_rb_host_arenas(64512 * MB, 3 * GB, 75958 * MB, 63 * GB, 256 * MB + GB, 9216 * MB, 0, 0, 0, &tl, &vp);
    CHECK(!n, "tail allocator off and no arena asked: nothing");
    n = s2a_rb_host_arenas(64512 * MB, 3 * GB, 75958 * MB, 63 * GB, 256 * MB + GB, 9216 * MB, 0, 2 * GB, 0, &tl, &vp);
    CHECK(tl == 2 * GB && !vp, "S2A_VP_ARENA_MB=0 keeps the tail range only");
    n = s2a_rb_host_arenas(64512 * MB, 3 * GB, 75958 * MB, 63 * GB, 256 * MB + GB, 9216 * MB, 0, 2 * GB, 1500 * MB, &tl, &vp);
    CHECK(vp == GB && !((tl + vp) & (GB - 1)), "an arena size that is not whole GiB is cut to whole GiB (window base alignment)");

    // ---- the arena ----
    char note[400]; s2a_rb_vp_note(note, sizeof note);
    CHECK(!note[0] && !s2a_rb_vp_size() && !s2a_rb_vp_map(MB), "no arena before init: no line, no range");
    const uint64_t SZ = 64 * MB;
    uint8_t *res = mmap(NULL, SZ + PAGE, PROT_NONE, MAP_PRIVATE | MAP_ANON, -1, 0);
    if (res == MAP_FAILED) { printf("FAIL reservation errno %d\n", errno); return 1; }
    uint64_t base = ((uint64_t)(uintptr_t)res + PAGE - 1) & ~(PAGE - 1);
    s2a_rb_vp_init(base, SZ);
    s2a_rb_vp_init(base + MB, MB);   // once only
    CHECK(s2a_rb_vp_size() == SZ, "arena size %llu", (unsigned long long)s2a_rb_vp_size());

    uint8_t *a = s2a_rb_vp_map(0xfa0000), *b = s2a_rb_vp_map(0x457000), *c = s2a_rb_vp_map(3 * MB + 1);
    CHECK(a && b && c, "three pools reserved");
    CHECK((uint64_t)(uintptr_t)a == base && !((uintptr_t)b & (PAGE - 1)) && !((uintptr_t)c & (PAGE - 1)), "ranges start on a host page, the first at the arena's base");
    CHECK(b >= a + 0xfa0000 + PAGE && c >= b + 0x457000 + PAGE, "one inaccessible host page between two pools");
    CHECK(s2a_rb_vp_has(a) && s2a_rb_vp_has(c) && !s2a_rb_vp_has(res + SZ + PAGE) && !s2a_rb_vp_has(&tl), "has() knows the arena's ranges only");
    CHECK(!readable(a) && !readable(b), "a reserved range is inaccessible");
    // MapVirtual puts memory into a pool's range (an alias there; a plain mapping here), Finalize gives the range back
    CHECK(mmap(b, 0x457000, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON | MAP_FIXED, -1, 0) == (void *)b, "mapping inside the pool's range");
    b[0] = 0x5a; b[0x456fff] = 0xa5;
    CHECK(readable(b) && readable(b + 0x456fff) && !readable(b + 0x457000 + PAGE - 1) && !readable(a), "only the pool's own range became accessible");
    CHECK(s2a_rb_vp_unmap(b, 0x457000) == 1, "the pool's range goes back to the arena");
    CHECK(!readable(b) && !readable(b + 0x456fff), "a released range is inaccessible again: nothing that was mapped into it survives");
    uint8_t *b2 = s2a_rb_vp_map(0x457000);
    CHECK(b2 == b && !readable(b2), "the next pool of that size reuses the range (first fit), inaccessible");
    CHECK(!s2a_rb_vp_unmap(&tl, 4096) && !s2a_rb_vp_unmap(NULL, 4096) && !s2a_rb_vp_unmap(a, 0), "a range that is not the arena's is left to the caller");
    // a release is checked against what was handed out, never against the caller's numbers
    CHECK(s2a_rb_vp_unmap(a + PAGE, 0xfa0000) == 1 && !readable(a) && s2a_rb_vp_has(a), "an address inside a held range is not a release: nothing is freed, and the caller must not munmap it");
    {   uint8_t *t1 = s2a_rb_vp_map(MB), *t2 = s2a_rb_vp_map(MB);
        CHECK(t1 && t2 && mmap(t2, MB, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON | MAP_FIXED, -1, 0) == (void *)t2, "two more pools, the second one mapped");
        t2[0] = 7;
        CHECK(s2a_rb_vp_unmap(t1, 8 * MB) == 1 && readable(t2) && t2[0] == 7, "a release with a length that is too long frees its own range only: the next pool is untouched");
        CHECK(s2a_rb_vp_unmap(t2, 4096) == 1 && !readable(t2) && !readable(t2 + MB - 1), "a release with a length that is too short still covers the whole range");
        CHECK(s2a_rb_vp_unmap(t2, MB) == 1, "a second release of the same range frees nothing more");
        s2a_rb_vp_note(note, sizeof note);
        CHECK(strstr(note, "did not match a held range 4"), "the four mismatches are counted: %s", note); }
    CHECK(!s2a_rb_vp_map(SZ) && !s2a_rb_vp_map(SZ + MB), "a request the arena cannot hold is refused, not shortened");
    s2a_rb_vp_note(note, sizeof note);
    CHECK(strstr(note, "3 pools alive") && strstr(note, "refused 2"), "ledger line: %s", note);
    // merging: free the three in an order that needs left, right and both-side merges, then take the whole arena
    CHECK(s2a_rb_vp_unmap(a, 0xfa0000) && s2a_rb_vp_unmap(c, 3 * MB + 1) && s2a_rb_vp_unmap(b2, 0x457000), "all released");
    uint8_t *all = s2a_rb_vp_map(SZ - PAGE);
    CHECK(all == (uint8_t *)(uintptr_t)base, "free ranges merged back into one: the whole arena (less its guard page) fits again");
    CHECK(!s2a_rb_vp_map(PAGE), "and nothing is left beside it");
    CHECK(s2a_rb_vp_unmap(all, SZ - PAGE), "released");

    // random reservations and releases: live ranges never overlap, each keeps its guard page, and everything merges back
    enum { N = 96 }; struct { uint8_t *p; uint64_t n; } live[N]; memset(live, 0, sizeof live);
    uint64_t seed = 0x9e3779b97f4a7c15ull; int overlap = 0, misaligned = 0, outside = 0;
    for (int it = 0; it < 20000; it++) {
        seed = seed * 6364136223846793005ull + 1442695040888963407ull; int i = (int)((seed >> 33) % N);
        if (live[i].p) { if (!s2a_rb_vp_unmap(live[i].p, live[i].n)) outside++; live[i].p = NULL; continue; }
        uint64_t len = (((seed >> 17) % 48) + 1) * 0x10000 + ((seed >> 9) & 0xfff);   // 64 KiB .. 3 MiB, not page multiples
        uint8_t *p = s2a_rb_vp_map(len); if (!p) continue;
        if ((uintptr_t)p & (PAGE - 1)) misaligned++;
        if ((uint64_t)(uintptr_t)p < base || (uint64_t)(uintptr_t)p + len + PAGE > base + SZ) outside++;
        for (int k = 0; k < N; k++) if (live[k].p && p < live[k].p + live[k].n + PAGE && live[k].p < p + len + PAGE) overlap++;
        live[i].p = p; live[i].n = len;
    }
    CHECK(!overlap && !misaligned && !outside, "20000 random steps: overlap %d, misaligned %d, outside %d", overlap, misaligned, outside);
    for (int i = 0; i < N; i++) if (live[i].p) s2a_rb_vp_unmap(live[i].p, live[i].n);
    all = s2a_rb_vp_map(SZ - PAGE);
    s2a_rb_vp_note(note, sizeof note);
    CHECK(all == (uint8_t *)(uintptr_t)base && strstr(note, "address lost 0.0 MB"), "after the random run the arena is whole again: %s", note);

    printf("%s %d checks, %d failed\n", bad ? "FAILED" : "PASSED", checks, bad);
    return bad != 0;
}
