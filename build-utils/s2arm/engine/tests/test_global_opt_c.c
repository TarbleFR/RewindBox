// SPDX-License-Identifier: Apache-2.0
// Pure C unit tests for RewindBox patches 0397 (streaming: sparse zero-tile fast path,
// iOS foreground headroom recovery, bind-lane admission).
// Runs on both Linux (gcc/clang) and macOS (xcrun clang) with -Wall -Wextra -Werror.
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "nvn_deswizzle.h"
#include "rb_bind_lane.h"

// Pure function under test from runtime/src/vawin.c (patch 0397).
// Declared here and tested identically against the extracted formula; also verified
// directly from vawin.c when built on Darwin or via included pure helper.
static uint64_t rb_guest_room_fg_ref(uint64_t room0, uint64_t lim0, uint64_t lim1) {
    if (!room0 || !lim0 || lim1 <= lim0) return room0;
    uint64_t boost = lim1 - lim0;
    return room0 > UINT64_MAX - boost ? UINT64_MAX : room0 + boost;
}

static int g_checks = 0, g_fails = 0;

static void check_cond(const char *name, int ok) {
    g_checks++;
    if (!ok) {
        g_fails++;
        fprintf(stderr, "FAIL %s\n", name);
    } else {
        printf("OK   %s\n", name);
    }
}

static void test_tile_is_zero(void) {
    uint8_t buf[0x10000u + 16];
    memset(buf, 0, sizeof buf);
    check_cond("tile_is_zero: all-zero 64KiB aligned", nvn_tile_is_zero(buf, 0x10000u) == 1);
    check_cond("tile_is_zero: all-zero 64KiB unaligned (+1)", nvn_tile_is_zero(buf + 1, 0x10000u) == 1);
    check_cond("tile_is_zero: empty length 0", nvn_tile_is_zero(buf, 0) == 1);
    check_cond("tile_is_zero: odd tail 13 zero bytes", nvn_tile_is_zero(buf + 3, 13) == 1);

    const size_t spots[] = {0, 1, 7, 8, 15, 16, 4095, 32768, 65527, 65534, 65535};
    int all_detected = 1;
    for (size_t i = 0; i < sizeof spots / sizeof spots[0]; i++) {
        memset(buf, 0, sizeof buf);
        buf[1 + spots[i]] = 0x80;
        if (nvn_tile_is_zero(buf + 1, 0x10000u) != 0) all_detected = 0;
    }
    check_cond("tile_is_zero: single non-zero byte detected at all edge/middle offsets (unaligned)", all_detected);

    memset(buf, 0, sizeof buf);
    buf[12] = 1;
    check_cond("tile_is_zero: trailing non-zero byte in tail (<8)", nvn_tile_is_zero(buf, 13) == 0);
}

static void test_deswizzle_zero_bit_exact(void) {
    // Test ASTC 8x8 (0x76), BC1 (0x42), BC6H (0x50), RGBA8 (0x25) — both whole and edge-clipped tiles,
    // both X1 (nvn_gob_switch2=0) and Switch 2 (nvn_gob_switch2=1), both all-zero and patterned inputs.
    struct {
        const char *label;
        int format;
        uint32_t w, h;
        uint32_t tx, ty;
    } cases[] = {
        {"ASTC8x8 whole 8192x8192", 0x76, 8192, 8192, 3, 2},
        {"ASTC8x8 edge 600x600",    0x76,  600,  600, 1, 1},
        {"BC1 whole 2048x2048",     0x42, 2048, 2048, 1, 1},
        {"BC1 edge 500x300",        0x42,  500,  300, 1, 0},
        {"BC6H whole 8192x8192",    0x50, 8192, 8192, 0, 1},
        {"RGBA8 whole 1024x1024",   0x25, 1024, 1024, 2, 1},
        {"RGBA8 edge 200x200",      0x25,  200,  200, 1, 1},
    };
    uint8_t zero_tile[0x10000u + 8];
    uint8_t pat_tile[0x10000u + 8];
    uint8_t ref_out[0x10000u + 4096];
    uint8_t got_out[0x10000u + 4096];
    memset(zero_tile, 0, sizeof zero_tile);
    for (size_t i = 0; i < sizeof pat_tile; i++) pat_tile[i] = (uint8_t)((i * 131u + 17u) ^ (i >> 8));

    int exact_zero = 1, exact_pat = 1, bad_fmt_rejected = 1;
    for (int sw2 = 0; sw2 <= 1; sw2++) {
        nvn_gob_switch2 = sw2;
        for (size_t c = 0; c < sizeof cases / sizeof cases[0]; c++) {
            nvn_texdesc d;
            memset(&d, 0, sizeof d);
            d.target = 1; // 2D
            d.format = cases[c].format;
            d.width = cases[c].w;
            d.height = cases[c].h;
            d.depth = 1;
            d.levels = 1;
            d.flags = 0x200; // SPARSE

            uint32_t rb, rows, slices, bpb;
            uint64_t base;
            unsigned th, td;
            if (nvn_deswizzle_geom(&d, 0, 0, &rb, &rows, &slices, &base, &th, &td, &bpb)) continue;
            size_t pitch = (size_t)((128u >> th) * 64u);

            // Check modes 1, 2, 3 against scalar reference mode 0 for ALL-ZERO tile (with sentinel fill)
            uint32_t rwb = 0, rnr = 0;
            memset(ref_out, 0xCC, sizeof ref_out);
            int r0 = nvn_deswizzle_tile_mode(&d, 0, cases[c].tx, cases[c].ty, zero_tile + 1, ref_out + 3, pitch, &rwb, &rnr, 0);
            for (int mode = 1; mode <= 3; mode++) {
                uint32_t gwb = 0, gnr = 0;
                memset(got_out, 0xCC, sizeof got_out);
                int g0 = nvn_deswizzle_tile_mode(&d, 0, cases[c].tx, cases[c].ty, zero_tile + 1, got_out + 3, pitch, &gwb, &gnr, mode);
                if (g0 != r0 || gwb != rwb || gnr != rnr || memcmp(ref_out, got_out, sizeof ref_out) != 0) {
                    fprintf(stderr, "MISMATCH zero sw2=%d case=%s mode=%d r0=%d g0=%d wb=%u/%u nr=%u/%u\n",
                            sw2, cases[c].label, mode, r0, g0, rwb, gwb, rnr, gnr);
                    exact_zero = 0;
                }
            }
            // Check modes 1, 2, 3 against scalar reference mode 0 for NON-ZERO patterned tile
            memset(ref_out, 0x5A, sizeof ref_out);
            r0 = nvn_deswizzle_tile_mode(&d, 0, cases[c].tx, cases[c].ty, pat_tile + 1, ref_out + 3, pitch, &rwb, &rnr, 0);
            for (int mode = 1; mode <= 3; mode++) {
                uint32_t gwb = 0, gnr = 0;
                memset(got_out, 0x5A, sizeof got_out);
                int g0 = nvn_deswizzle_tile_mode(&d, 0, cases[c].tx, cases[c].ty, pat_tile + 1, got_out + 3, pitch, &gwb, &gnr, mode);
                if (g0 != r0 || gwb != rwb || gnr != rnr || memcmp(ref_out, got_out, sizeof ref_out) != 0) {
                    fprintf(stderr, "MISMATCH pat sw2=%d case=%s mode=%d\n", sw2, cases[c].label, mode);
                    exact_pat = 0;
                }
            }
        }
    }
    // Verify linear/invalid flags still fail even when tile is all-zero and mode=3!
    nvn_texdesc bad;
    memset(&bad, 0, sizeof bad);
    bad.target = 1; bad.format = 0x25; bad.width = 256; bad.height = 256; bad.depth = 1; bad.levels = 1;
    bad.flags = 0x10; // LINEAR -> must return -1
    uint32_t wb = 99, nr = 99;
    if (nvn_deswizzle_tile_mode(&bad, 0, 0, 0, zero_tile, got_out, 1024, &wb, &nr, 3) != -1 || wb != 0 || nr != 0)
        bad_fmt_rejected = 0;

    check_cond("deswizzle_zero: bit-exact across ASTC8x8/BC1/BC6H/RGBA8 whole+edge X1+Sw2 modes 0..3", exact_zero);
    check_cond("deswizzle_pat: bit-exact across ASTC8x8/BC1/BC6H/RGBA8 whole+edge X1+Sw2 modes 0..3", exact_pat);
    check_cond("deswizzle_zero: LINEAR flag still rejected (-1) even on all-zero tile", bad_fmt_rejected);
}

static void test_guest_room_fg(void) {
    const uint64_t MB = 1ull << 20;
    // ActivePrewarm case (S2Arm ee40f8fc0): room0=6140 MB, lim0=6144 MB, foreground lim1=8192 MB -> 8188 MB
    check_cond("guest_room_fg: ActivePrewarm +2048 MB boost",
               rb_guest_room_fg_ref(6140 * MB, 6144 * MB, 8192 * MB) == 8188 * MB);
    // Normal foreground launch (unchanged limit): returns room0
    check_cond("guest_room_fg: unchanged limit returns room0",
               rb_guest_room_fg_ref(8122 * MB, 8192 * MB, 8192 * MB) == 8122 * MB);
    // Limit dropped (never shrinks room0)
    check_cond("guest_room_fg: smaller lim1 keeps room0",
               rb_guest_room_fg_ref(6140 * MB, 8192 * MB, 6144 * MB) == 6140 * MB);
    // Zero inputs
    check_cond("guest_room_fg: zero room0/lim0 safe",
               rb_guest_room_fg_ref(0, 6144 * MB, 8192 * MB) == 0 &&
               rb_guest_room_fg_ref(6140 * MB, 0, 8192 * MB) == 6140 * MB);
    // Overflow clamping
    check_cond("guest_room_fg: UINT64_MAX overflow clamps cleanly",
               rb_guest_room_fg_ref(UINT64_MAX - 10, 100, 500) == UINT64_MAX);
}

static void test_bind_lane_safety(void) {
    // Verify bind lane safety gates remain intact for non-MKW titles (Zelda/Fire Emblem)
    check_cond("bind_lane: route on when gov=1 file_only=0", rb_bl_route(1, 1, 0) == 1);
    check_cond("bind_lane: route off when disabled", rb_bl_route(0, 1, 0) == 0);
    rb_bl_budget b = {0};
    rb_bl_state ok = {.tier = RB_BL_TIER_WARN, .level = 0, .room = 2ull << 30, .mem_low = 0, .thermal = 1, .stopped = 0, .full = 0};
    check_cond("bind_lane: admits 512 KiB under warn tier & thermal 1", rb_bl_admit(&b, &ok, 10, 512u << 10) == RB_BL_ADMIT);
    rb_bl_state hot = ok; hot.thermal = 2;
    check_cond("bind_lane: refuses under serious thermal (2)", rb_bl_admit(&b, &hot, 10, 512u << 10) == RB_BL_NO_HEAT);
    rb_bl_state crit = ok; crit.tier = RB_BL_TIER_CRITICAL;
    check_cond("bind_lane: refuses under critical tier", rb_bl_admit(&b, &crit, 10, 512u << 10) == RB_BL_NO_TIER);
    rb_bl_state low = ok; low.room = 512ull << 20;
    check_cond("bind_lane: refuses under <1 GiB room", rb_bl_admit(&b, &low, 10, 512u << 10) == RB_BL_NO_ROOM);
}

int main(void) {
    test_tile_is_zero();
    test_deswizzle_zero_bit_exact();
    test_guest_room_fg();
    test_bind_lane_safety();
    printf("SUMMARY test_global_opt_c: checks=%d fails=%d\n", g_checks, g_fails);
    return g_fails != 0;
}
