// Runs s2a_rb_host_more (engine patch 0019, runtime/src/rb_hostroom.c as the patch adds it) with the arena sizing of
// patch 0013 (runtime/src/rb_vparena.c as that patch adds it), on the numbers of the device log of 13 Nov.
// With -DRB_GCLIMIT it is linked with S2Arm's gclimit.c as the patch leaves it (the test makes that file when it has
// S2Arm's source) and also runs s2a_gc_limit_apply: the limit picked with and without the room given to the host.
#include <stdint.h>
#include <stdio.h>
#ifdef RB_GCLIMIT
#include <stdarg.h>
#include <stdlib.h>
#include <string.h>
#endif

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

// gclimit.c's tiers at the pinned S2Arm commit: what the GC reserves at its start, by the largest hole it is given (with
// -DRB_GCLIMIT the thresholds are checked against the file's own s2a_gc_limit_pick below)
static uint64_t gc_reserve(uint64_t largest) { return largest >= 11264 * MB ? 10240 * MB : largest >= 3712 * MB ? 2688 * MB : largest >= 1894 * MB ? 870 * MB : 0; }

#ifdef RB_GCLIMIT
int s2a_gc_limit_pick(uint64_t largest);
void s2a_gc_limit_apply(void);
static uint64_t g_holes[2], g_less[3];   // total, largest (, the room given)
void s2a_low_holes(uint64_t *total, uint64_t *largest) { *total = g_holes[0]; *largest = g_holes[1]; }
void s2a_rb_low_holes_less(uint64_t *total, uint64_t *largest, uint64_t *more) { *total = g_less[0]; *largest = g_less[1]; *more = g_less[2]; }
static char g_log[8192];
void rb_test_log(const char *format, ...) {
    va_list ap; va_start(ap, format); size_t n = strlen(g_log);
    vsnprintf(g_log + n, sizeof g_log - n, format, ap); va_end(ap);
    n = strlen(g_log); snprintf(g_log + n, sizeof g_log - n, "\n");
}
static const char *const k_vars[] = {"DOTNET_GCHeapHardLimit", "DOTNET_GCHeapHardLimitPercent", "DOTNET_GCHeapHardLimitSOH", "DOTNET_GCHeapHardLimitLOH", "DOTNET_GCHeapHardLimitPOH"};
// The limit s2a_gc_limit_apply sets when the host's largest hole is `real` MB, of which `room` MB were given by patch 0019, and the largest hole without them is `less` MB
static const char *limit_for(uint64_t real, uint64_t room, uint64_t less) {
    for (unsigned i = 0; i < 5; i++) unsetenv(k_vars[i]);
    g_log[0] = 0;
    g_holes[0] = (real + 100) * MB; g_holes[1] = real * MB; g_less[0] = (less + 100) * MB; g_less[1] = less * MB; g_less[2] = room * MB;
    s2a_gc_limit_apply();
    const char *total = getenv(k_vars[0]), *soh = getenv(k_vars[2]), *loh = getenv(k_vars[3]), *poh = getenv(k_vars[4]);
    if (total) return !strcmp(total, "80000000") && !soh ? "total" : "?";
    if (!soh) return !loh && !poh ? "none" : "?";
    if (!loh || !poh) return "?";
    if (!strcmp(soh, "60000000") && !strcmp(loh, "20000000") && !strcmp(poh, "8000000")) return "heaps";
    if (!strcmp(soh, "18000000") && !strcmp(loh, "10000000") && !strcmp(poh, "4000000")) return "need";
    return "?";
}
#endif

int main(int argc, char **argv) {
    (void)argc; (void)argv;
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

    // The GC limit is picked by the hole without the room (vawin.c s2a_rb_low_holes_less; gclimit.c below with -DRB_GCLIMIT), so what the GC reserves
    // at its start is what it reserved before and every GiB given is the host's. The hole is the 3 GiB and the 0-1023 MB that the window's 1 GiB
    // alignment leaves in front of them: 68 MB on 13 Nov 04:41 (3140 MB, the on-demand limit), 1022 MB on 13 Nov 16:15 (4094 MB, the per-heap limit,
    // the run that stopped). Left to the host = its hole less that reservation
    {   // What counting the room did (the first version of this patch): every start over 3712 MB, the per-heap reservation
        uint64_t hole = 3140 * MB, before = hole - gc_reserve(hole);
        CHECK(before == 2270 * MB, "a 3140 MB hole left the host 2270 MB after the on-demand reservation");
        CHECK(hole + 2 * GB - gc_reserve(hole + 2 * GB) == before + 230 * MB, "counted, 2 GiB gained that start 230 MB");
        CHECK(before - (hole + GB - gc_reserve(hole + GB)) == 794 * MB, "counted, one GiB cost that start 794 MB");
        CHECK(hole + 2 * GB - gc_reserve(hole) == before + 2 * GB && 4094 * MB + 2 * GB - gc_reserve(4094 * MB) == 3454 * MB,
              "not counted: 2270 -> 4318 MB there, and 1406 -> 3454 MB on the start that stopped");
    }
#ifdef RB_GCLIMIT
    {   // S2Arm's gclimit.c as the patch leaves it. argv[1] = "absent": this binary does not export s2a_rb_low_holes_less, so the file finds no such function
        int absent = argc > 1 && !strcmp(argv[1], "absent");
        CHECK(s2a_gc_limit_pick(11264 * MB) == 1 && s2a_gc_limit_pick(11263 * MB) == 2 && s2a_gc_limit_pick(3712 * MB) == 2 && s2a_gc_limit_pick(3711 * MB) == 3
              && s2a_gc_limit_pick(1894 * MB) == 3 && s2a_gc_limit_pick(1893 * MB) == 0, "the tiers' thresholds are those gc_reserve assumes");
        const char *got = limit_for(3140, 0, 3140);
        CHECK(!strcmp(got, "need") && !strstr(g_log, "RewindBox"), "no room given, a 3140 MB hole: the on-demand limit, as S2Arm picks it, and no line of ours (%s)", got);
        got = limit_for(4094, 0, 4094);
        CHECK(!strcmp(got, "heaps") && !strstr(g_log, "RewindBox"), "no room given, a 4094 MB hole: the per-heap limit, as S2Arm picks it (%s)", got);
        got = limit_for(3140 + 2048, 2048, 3140);
        if (absent) CHECK(!strcmp(got, "heaps") && !strstr(g_log, "RewindBox"), "without the function the room is counted, as S2Arm's own test links the file (%s)", got);
        else {
            CHECK(!strcmp(got, "need"), "2 GiB given on a 3140 MB hole: still the on-demand limit (%s)", got);
            CHECK(strstr(g_log, "RewindBox: the GC limit is picked without the 2048 MB the host got below the window for its low region: by a largest hole of 3140 MB (of 3240 MB in all), "
                                "where the host's largest hole is 5188 MB (of 5288 MB)") != NULL, "the log says by which hole the limit is picked: %s", g_log);
            const char *second = strchr(g_log, '\n'); second = second ? second + 1 : "";
            CHECK(strstr(second, "3140 MB") && !strstr(second, "5188"), "S2Arm's own line gives the hole the limit was picked by: %s", g_log);
            got = limit_for(3140 + 1024, 1024, 3140);
            CHECK(!strcmp(got, "need"), "1 GiB given on a 3140 MB hole: the on-demand limit (%s)", got);
            got = limit_for(3711 + 2048, 2048, 3711);
            CHECK(!strcmp(got, "need"), "2 GiB given on a 3711 MB hole: the on-demand limit (%s)", got);
            got = limit_for(3712 + 2048, 2048, 3712);
            CHECK(!strcmp(got, "heaps"), "2 GiB given on a 3712 MB hole: the per-heap limit, as without the room (%s)", got);
            got = limit_for(4094 + 2048, 2048, 4094);
            CHECK(!strcmp(got, "heaps"), "2 GiB given on a 4094 MB hole: the per-heap limit, as without the room (%s)", got);
            got = limit_for(9000, 2048, 9000);
            CHECK(!strcmp(got, "heaps"), "another hole is the largest, with or without the room: it decides (%s)", got);
            got = limit_for(1893 + 2048, 2048, 1893);
            CHECK(!strcmp(got, "none") && strstr(g_log, "1893 MB"), "a hole that held no limit without the room holds none with it (%s)", got);
        }
        for (unsigned i = 0; i < 5; i++) unsetenv(k_vars[i]);
        setenv("DOTNET_GCHeapHardLimitSOH", "123", 1); g_log[0] = 0;
        g_holes[0] = g_holes[1] = 5188 * MB; g_less[0] = g_less[1] = 3140 * MB; g_less[2] = 2 * GB;
        s2a_gc_limit_apply();
        CHECK(!strcmp(getenv("DOTNET_GCHeapHardLimitSOH"), "123") && !getenv("DOTNET_GCHeapHardLimitLOH") && !strstr(g_log, "RewindBox"), "a limit set from outside is kept, as before: %s", g_log);
    }
#endif

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
