// RewindBox: port of S2Arm pack/gen_caps.sh --both with tools/caps_policy.py decide (target
// apple), including the engine detection it calls (graphics/nvn/games/profile_guess.py
// facts_of / guess / engine, with nso_syms.dynsyms and the romfs_list walk rules). Apache-2.0,
// pinned commit in tools/s2arm_prototype/pin.json. CI compares the files with gen_caps.sh on
// synthetic product roots (tools/s2arm_prototype/run_pack_test.py).
//
// Writes s2a_caps.tsv (release: fps60 on by default, widen off unless widen_verified.tsv) and
// s2a_caps.all.tsv (--all-caps: on whenever a source exists). Inputs read from the product root:
// unpack.tsv, exefs/ (every NSO: segments decoded, dynamic symbols parsed, markers in main),
// romfs/ (file extensions), and the optional tables S2Arm reads (widen_enable.*.tsv,
// widen_verified.tsv, widen_full.*.tsv, cpatch.tsv, <m>.widen.tsv, fps.tsv). Not available on the
// phone and taken as absent: S2Arm's per-game registries (strong signals, 60 fps coverage, A/B
// ledger, verification ledger) - the result is S2Arm's for a game none of them lists.
#pragma once
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

enum {
    RB_S2ARM_CAPS_OK = 0,
    RB_S2ARM_CAPS_INVALID = 1,  // the original's decision fails (no root, an unreadable table)
    RB_S2ARM_CAPS_IO = 2,       // a file could not be written, or out of memory
};

// release_path receives s2a_caps.tsv, all_caps_path (may be NULL) s2a_caps.all.tsv. *engine_l1
// (may be NULL) receives 1 when the engine rule (Unity, or Unreal with .pak/.utoc data) found the
// game, which makes fps60 come from the engine rather than from the general rule.
int rb_s2arm_caps(const char *root, const char *release_path, const char *all_caps_path, int *engine_l1, char *error, size_t error_size);

#ifdef __cplusplus
}
#endif
