#pragma once
// The rb_s2arm_* entry points of S2ArmPrepare.xcframework (native/s2arm/prepare) this host calls. The xcframework is linked
// but its headers are not on this pod's search path (it exposes only rb_s2arm_* symbols); these declarations copy the ones
// used, field for field. test/s2arm_engine_bridge_test.py checks them against native/s2arm/prepare/*.h.
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

// s2arm_ns2_dump.h
enum { RB_S2ARM_NS2_OK = 0, RB_S2ARM_NS2_INVALID = 1, RB_S2ARM_NS2_IO = 2, RB_S2ARM_NS2_CANCELLED = 5 };
typedef struct {
    const char *export_dir;
    const char *output_dir;
    const char *name;
    int reference_data;
    void (*note)(void *context, const char *line);
    int (*cancelled)(void *context);
    void *context;
    size_t max_module_bytes;
} rb_s2arm_ns2_dump_request;
int rb_s2arm_ns2_detect(const char *root, char *dump, size_t dump_size, uint64_t *program_id, char *error, size_t error_size);
int rb_s2arm_ns2_dump(const rb_s2arm_ns2_dump_request *request, char *error, size_t error_size);

// s2arm_prepare.h
enum {
    RB_S2ARM_PREPARE_OK = 0,
    RB_S2ARM_PREPARE_INVALID = 1,
    RB_S2ARM_PREPARE_IO = 2,
    RB_S2ARM_PREPARE_GAPS = 3,
    RB_S2ARM_PREPARE_REWRITER = 4,
    RB_S2ARM_PREPARE_CANCELLED = 5,
    RB_S2ARM_PREPARE_UNSUPPORTED = 6,
};
typedef struct {
    const char *exefs_dir;
    const char *romfs_dir;
    const char *output_dir;
    void (*progress)(void *context, const char *step, int index, int count);
    int (*cancelled)(void *context);
    void *context;
} rb_s2arm_code_request;
int rb_s2arm_prepare_code(const rb_s2arm_code_request *request, char *error, size_t error_size);

// s2arm_caps.h
enum { RB_S2ARM_CAPS_OK = 0, RB_S2ARM_CAPS_INVALID = 1, RB_S2ARM_CAPS_IO = 2 };
int rb_s2arm_caps(const char *root, const char *release_path, const char *all_caps_path, int *engine_l1, char *error, size_t error_size);

// s2arm_pack.h
enum { RB_S2ARM_PACK_OK = 0, RB_S2ARM_PACK_INVALID = 1, RB_S2ARM_PACK_IO = 2, RB_S2ARM_PACK_CANCELLED = 5 };
typedef struct {
    const char *id;
    const char *name;
    long long version;
    const char *content_identity;
} rb_s2arm_save_identity;
typedef struct {
    const char *root;
    const char *module_dir;
    const char *images_path;
    const rb_s2arm_save_identity *save_identity;
    int write_launch_ctx;
    const char *ctx_images, *ctx_module_dir, *ctx_game_data, *ctx_docs;
} rb_s2arm_module_request;
typedef struct {
    const char *root;
    const char *pack_dir;
    const char *systemdata_dir;
    int systemdata_link;
    int write_applied;
    void (*progress)(void *context, uint64_t done_bytes, uint64_t total_bytes);
    int (*cancelled)(void *context);
    void *context;
} rb_s2arm_resource_request;
int rb_s2arm_module_dir(const rb_s2arm_module_request *request, char *error, size_t error_size);
int rb_s2arm_direct_skeleton(const char *root, const char *chain, const char *tag, const char *reason, char *error, size_t error_size);
int rb_s2arm_resource_pack(const rb_s2arm_resource_request *request, char *error, size_t error_size);

#ifdef __cplusplus
}
#endif
