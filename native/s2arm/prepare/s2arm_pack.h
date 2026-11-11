// RewindBox: the per-game files S2Arm's iOS runtime reads at boot, written on the phone from a
// prepared product root (the unpack directory of s2arm_ns2_dump.h with the outputs of
// rb_s2arm_prepare_code and rb_s2arm_caps written into it). Ports of S2Arm (Apache-2.0, pinned
// commit in tools/s2arm_prototype/pin.json):
//   image pack       ios/embed.py + ios/macho_dylib.py: S2AImages[-<gid>].dylib, a Mach-O wrapper
//                    with __TEXT,__swidx ("S2AEMB01", 88-byte entries x0/W/x1/x2), __TEXT,__swcode
//                    and __SWDATA,__img, 16 KiB blocks, the reserved signature area and the
//                    linker-style ad-hoc signature exactly as written there (unsigned on the phone).
//   module directory pack/ship_ext.py container (place_game + per-game files): the companion
//                    tables, main.npdm, the shell's table list (s2a_caps.tsv, addr_need.tsv ...),
//                    icon.jpg / banner.jpg, save-identity.json, optionally launch.ctx.
//   resource pack    pack/pkg_srcs.py srcs + pack/pack.py (manifest.json, index.tsv, the files),
//                    as the device holds it after pack_apply (.applied, index.applied.tsv); RomFS
//                    and DLC data are relative symlinks into the product root (read in place).
// CI compares every output with S2Arm's tools on synthetic input
// (tools/s2arm_prototype/run_pack_test.py). Deliberate differences are listed in
// docs/s2arm-study-2026-11-11.md section 8.
#pragma once
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

enum {
    RB_S2ARM_PACK_OK = 0,
    RB_S2ARM_PACK_INVALID = 1,    // missing or malformed input (where S2Arm stops with a red line, an assertion or an exception)
    RB_S2ARM_PACK_IO = 2,         // a file could not be read, written or linked, or out of memory
    RB_S2ARM_PACK_CANCELLED = 5,
};

// ios/embed.py <root> <output> <modules...>. modules = NULL or count 0: every <m>.fixups.tsv of
// root in the Horizon load order (main, subsdk0..N, others by name, sdk), as ship_ext.py does.
// A name may be "<name in the pack>=<file prefix in root>". The file is written to
// <output>.tmp and renamed over output at the end: on failure the previous file stays. The
// install name and the signature identifier are those of embed.py ("@rpath/S2AImages.dylib",
// "S2AImages") whatever the output file name.
int rb_s2arm_image_pack(const char *root, const char *const *modules, size_t count, const char *output, char *error, size_t error_size);

typedef struct {
    const char *id;                // 16 hex digits (the program id)
    const char *name;
    long long version;             // >= 0
    const char *content_identity;  // 64 lowercase hex digits
} rb_s2arm_save_identity;

typedef struct {
    const char *root;         // product root
    const char *module_dir;   // the game's module directory (Games/<gid>/ of a container); built in <module_dir>.tmp, then replaces it whole
    const char *images_path;  // where the image pack is written (Frameworks/S2AImages-<gid>.dylib in a container); NULL = not written
    // save-identity.json from the values given here, validated as pack/save_identity.py does
    // (the host reads them from the export's control data and its own content hash). NULL: no
    // save-identity.json (the file is optional for the runtime).
    const rb_s2arm_save_identity *save_identity;
    // launch.ctx (runtime/include/s2a_launch_ctx.h v1). 0: not written (the guest host fills the
    // context itself). 1: written; NULL values take ship_ext.py's container values
    // (@bundle/Frameworks/S2AImages-<gid>.dylib, @bundle/Games/<gid>, @home/Documents/games/<gid>/资源包,
    // @home/Documents/games/<gid>); a value is an absolute path or starts with @bundle/ or @home/.
    int write_launch_ctx;
    const char *ctx_images, *ctx_module_dir, *ctx_game_data, *ctx_docs;
} rb_s2arm_module_request;

// The module directory of one game, as pack/ship_ext.py container writes Games/<gid>/ (and the
// image pack when images_path is given, written last). The game id is the program id of
// <root>/main.npdm. Multi-program collections (programs/<n>/) are refused.
int rb_s2arm_module_dir(const rb_s2arm_module_request *request, char *error, size_t error_size);

typedef struct {
    const char *root;       // product root (exefs/main.npdm, romfs/, ctl/, aoc.tsv, aoc/ ...)
    const char *pack_dir;   // the resource pack (Documents/games/<gid>/资源包 on the device); replaced
    // The game-independent system data tree (fonts/, 010000000000080E/, 0100000000000802/ ...,
    // shipped with the app); NULL = <root>/systemdata. systemdata_link = 1: a relative symlink to
    // it instead of a copy (index.tsv is the same either way).
    const char *systemdata_dir;
    int systemdata_link;
    // 1: also .applied and index.applied.tsv, as runtime/src/pack_apply.c leaves them after a
    // successful import, so that the game library sees the pack ready at once.
    int write_applied;
    void (*progress)(void *context, uint64_t done_bytes, uint64_t total_bytes);  // while hashing (may be NULL)
    int (*cancelled)(void *context);                                             // polled between files and 4 MiB chunks (may be NULL)
    void *context;
} rb_s2arm_resource_request;

// graphics/tools/direct/runtime_only_lib.sh as pack/stage_direct.sh calls it: the empty direct
// shader library (shaders compiled at first use) in <root>/shaders/direct, replacing what is there.
// chain = the engine's direct library chain version (1 to 12 characters; translator/dmsh_chain.py
// version()); tag = the inputs tag; reason = the reason text (runtime_only.txt). The program id is
// the title_id of <root>/unpack.tsv, upper case.
int rb_s2arm_direct_skeleton(const char *root, const char *chain, const char *tag, const char *reason, char *error, size_t error_size);

// pack/pkg_srcs.py srcs + pack/pack.py: the resource pack of one game. Built in <pack_dir>.tmp
// and renamed at the end. exefs/main.npdm, ctl/control.nacp, aoc.tsv, the shader library are
// copies; romfs and aoc are relative symlinks to the product root's (resolved) directories;
// index.tsv lists every file with its size and SHA-256 in pack.py's order.
int rb_s2arm_resource_pack(const rb_s2arm_resource_request *request, char *error, size_t error_size);

#ifdef __cplusplus
}
#endif
