#pragma once
// The engine's guest interface as this host calls it. S2ArmEngine.framework is opened with dlopen and never linked, so its
// public header (runtime/src/rb_guest.h of patch 0003, copied into S2ArmEngine.framework/Headers) is not on this pod's
// search path: the declarations below copy it field for field. test/s2arm_engine_bridge_test.py compares this struct with
// the one in build-utils/s2arm/engine/patches/0003-guest-configure-launch-context-and-window.patch and fails on any change.
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct s2a_rb_guest_config {
    uint32_t size;
    const char *game_id;
    const char *images;
    const char *module_dir;
    const char *caps_dir;
    const char *game_data;
    const char *ryu_data;
    const char *docs;
    void *(*prepare_code)(void *address, size_t length, void *context);
    void *prepare_context;
    void (*session_ended)(int code, const char *reason, void *context);
    void *ended_context;
} s2a_rb_guest_config;

// Looked up with dlsym after the dlopen (names of rb_guest.h).
typedef int (*s2a_rb_guest_configure_fn)(const s2a_rb_guest_config *config, char *error, size_t error_size);
typedef void *(*s2a_rb_guest_make_view_controller_fn)(void);   // UIViewController *, autoreleased (main thread)
typedef int (*s2a_rb_guest_start_fn)(char *error, size_t error_size);
typedef void (*s2a_rb_guest_stop_fn)(const char *reason);

#define S2A_RB_GUEST_CONFIGURE "s2a_rb_guest_configure"
#define S2A_RB_GUEST_MAKE_VIEW_CONTROLLER "s2a_rb_guest_make_view_controller"
#define S2A_RB_GUEST_START "s2a_rb_guest_start"
#define S2A_RB_GUEST_STOP "s2a_rb_guest_stop"

// session_ended codes (rb_guest.h): 0 normal end, 1 the session could not start, 86 watchdog or GPU stop,
// 134 fatal engine error (the process aborts after the call).
enum { S2A_RB_ENDED_NORMAL = 0, S2A_RB_ENDED_START_FAILED = 1, S2A_RB_ENDED_WATCHDOG = 86, S2A_RB_ENDED_FATAL = 134 };

#ifdef __cplusplus
}
#endif
