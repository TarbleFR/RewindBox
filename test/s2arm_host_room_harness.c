// Runs s2a_rb_host_more (engine patch 0019, runtime/src/rb_hostroom.c as the patch adds it) with the arena sizing of
// patch 0013 (runtime/src/rb_vparena.c as that patch adds it), on the numbers of the device log of 13 Nov.
#include <stdint.h>
#include <stdio.h>

uint64_t s2a_rb_host_arenas(uint64_t fit, uint64_t host_below, uint64_t need, uint64_t alias, uint64_t slack, uint64_t pool, int alias_first,
                            uint64_t tail_want, uint64_t vp_want, uint64_t *tail, uint64_t *vp);
uint64_t s2a_rb_host_more(uint64_t low_free, uint64_t counted, uint64_t most, uint64_t host_below, uint64_t (*arenas)(uint64_t host_below, void *ctx), void *ctx);

#define MB (1ull << 20)
#define GB (1ull << 30)
static int g_failures, g_checks;
#define CHECK(condition, ...) do { g_checks++; if (!(condition)) { g_failures++; printf("FAIL line %d: ", __LINE__); printf(__VA_ARGS__); printf("\n"); } } while (0)

// vawin.c's own call (rb_arenas_at): Mario Kart World, standard layout 75958 MB, alias commitment 63 GiB, slack 256 MB + 1 GiB, pool 9216 MB
typedef struct { uint64_t fit, need, pool, vp_want; int alias_first, calls; uint64_t tail, vp; } game;
static uint64_t arenas(uint64_t host_below, void *ctx) {
    game *g = ctx;
    g->calls++;
    return s2a_rb_host_arenas(g->fit, host_below, g->need, 63 * GB, 256 * MB + GB, g->pool, g->alias_first, 2 * GB, g->vp_want, &g->tail, &g->vp);
}

int main(void) {
    const uint64_t counted = 1843 * MB, host = 3 * GB;
    // The device, 13 Nov 16:15: largest hole below 2^39 63488 MB, 184 MB free in [4 GiB, 6 GiB)
    game kart = {63488 * MB, 75958 * MB, 9216 * MB, 16 * GB, 0, 0, 0, 0};
    uint64_t before = arenas(host, &kart), tail = kart.tail, vp = kart.vp;
    CHECK(before == 18 * GB && tail == 2 * GB && vp == 16 * GB, "the device's arenas are the ones its log shows (18432 MB): %llu MB", (unsigned long long)(before >> 20));
    uint64_t more = s2a_rb_host_more(184 * MB, counted, 2 * GB, host, arenas, &kart);
    CHECK(more == 2 * GB, "184 MB free where 1843 MB are counted on: 1659 MB lack, 2 GiB more for the host (got %llu MB)", (unsigned long long)(more >> 20));
    CHECK(arenas(host + more, &kart) == before && kart.tail == tail && kart.vp == vp, "both arenas keep their size with the larger host share");
    uint64_t window = kart.fit - host - more - before, front = 75958 * MB - 63 * GB + 256 * MB + GB;
    CHECK(window == 39936 * MB && window >= front + 9216 * MB, "the window keeps %llu MB: the regions in front of the alias region (%llu MB) and one pool of it fit", (unsigned long long)(window >> 20),
          (unsigned long long)(front >> 20));
    CHECK(host + more + 923 * MB < 10240 * MB + 1024 * MB, "the host's hole stays below what makes the GC reserve 10 GB (gclimit.c)");

    // What the low region lacks, in whole GiB, never more than `most`
    CHECK(s2a_rb_host_more(1843 * MB, counted, 2 * GB, host, arenas, &kart) == 0, "a low region with what is counted on: nothing more");
    CHECK(s2a_rb_host_more(4000 * MB, counted, 2 * GB, host, arenas, &kart) == 0, "a larger low region: nothing more");
    CHECK(s2a_rb_host_more(1842 * MB, counted, 2 * GB, host, arenas, &kart) == GB, "1 MB lacking: one GiB");
    CHECK(s2a_rb_host_more(819 * MB, counted, 2 * GB, host, arenas, &kart) == GB, "1024 MB lacking: one GiB");
    CHECK(s2a_rb_host_more(818 * MB, counted, 2 * GB, host, arenas, &kart) == 2 * GB, "1025 MB lacking: two GiB");
    CHECK(s2a_rb_host_more(0, counted, 2 * GB, host, arenas, &kart) == 2 * GB, "an empty low region: the most, two GiB");
    CHECK(s2a_rb_host_more(0, counted, GB, host, arenas, &kart) == GB && s2a_rb_host_more(0, counted, 0, host, arenas, &kart) == 0, "S2A_HOST_MORE_MB caps it; 0 turns it off");
    CHECK(s2a_rb_host_more(0, counted, GB + 500 * MB, host, arenas, &kart) == GB, "a cap that is not a whole GiB is rounded down");

    // Only as much as leaves the arenas their size. keep = 12726 + 9216 = 21942 MB.
    game tight = kart;
    tight.fit = 3 * GB + 21942 * MB + 18 * GB + GB + 100 * MB;   // room for both arenas and one GiB more, not two
    before = arenas(host, &tight);
    CHECK(before == 18 * GB, "a hole with 19 GiB of room gives both arenas");
    CHECK(s2a_rb_host_more(184 * MB, counted, 2 * GB, host, arenas, &tight) == GB, "the host gets the one GiB that does not shrink them");
    tight.fit = 3 * GB + 21942 * MB + 18 * GB + 100 * MB;        // exactly the arenas
    CHECK(arenas(host, &tight) == 18 * GB && s2a_rb_host_more(184 * MB, counted, 2 * GB, host, arenas, &tight) == 0, "no room beyond the arenas: nothing more, the arenas stay whole");
    tight.fit = 3 * GB + 21942 * MB + 10 * GB + 100 * MB;        // the arena is already cut to what fits
    before = arenas(host, &tight);
    CHECK(before == 10 * GB && s2a_rb_host_more(184 * MB, counted, 2 * GB, host, arenas, &tight) == 0, "an arena already smaller than asked is not cut further");

    // No arenas: the window is left as S2Arm sizes it
    game hinted = kart;
    hinted.alias_first = 1;
    CHECK(arenas(host, &hinted) == 0 && s2a_rb_host_more(184 * MB, counted, 2 * GB, host, arenas, &hinted) == 0, "a game whose alias region the layout sizes from the window gives nothing up");
    CHECK(s2a_rb_host_more(184 * MB, counted, 2 * GB, host, NULL, &kart) == 0, "no sizing function (S2Arm's tests that link vawin.c alone): nothing");

    printf("%s %d checks, %d failed\n", g_failures ? "FAILED" : "PASSED", g_checks, g_failures);
    return g_failures ? 1 : 0;
}
