#ifndef NEOSTATION_MELONX_SESSION_ABI_H
#define NEOSTATION_MELONX_SESSION_ABI_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* Session ABI 1. UTF-8 buffers are borrowed for the duration of each call.
 * The host owns/retains the CAMetalLayer until run returns. Never dlclose the
 * NativeAOT library. Initialization and run must execute off UIKit's thread.
 * No function here proves that guest JIT, dependencies or inputs are ready. */
int32_t neostation_melonx_bootstrap_abi(void);
int32_t neostation_melonx_initialize(const char *root_utf8);
int32_t neostation_melonx_session_abi(void);
/* 0 idle, 1 prepared, 2 running, 3 stopping, 4 quarantined. */
int32_t neostation_melonx_session_state(void);
/* Required UTF-8 length excluding NUL; bounded copy if capacity > 0. */
int32_t neostation_melonx_session_error(char *output, int32_t capacity);
/* Positive generation, -1 busy, -2 invalid arguments, -3 uninitialized. */
int64_t neostation_melonx_prepare(const char *game_utf8, const char *locale_utf8,
                                int32_t width, int32_t height);
/* Synchronous owner. 0 completion, 2 stale/busy, 3 quarantined failure. */
int32_t neostation_melonx_run(int64_t generation);
/* Signal only; does not wait or release objects. */
int32_t neostation_melonx_stop(int64_t generation);
int32_t neostation_melonx_pause(int64_t generation, int32_t paused);
int32_t neostation_melonx_cancel_prepared(int64_t generation);
void set_native_window(void *metal_layer);
/* Runtime ABI 1. Calls configure_native before initialize; absolute private
 * Frameworks root. Content runs on a serial worker with a 64 KiB output. */
int32_t neostation_melonx_runtime_abi(void);
int32_t neostation_melonx_configure_native(const char *frameworks_utf8);
int32_t neostation_melonx_configure_jit(int32_t universal);
int32_t neostation_melonx_configure_graphics(const char *json_utf8);
int32_t neostation_melonx_content(const char *path_utf8, int32_t operation, char *output, int32_t capacity);
int32_t neostation_melonx_input_abi(void);
int32_t neostation_melonx_input_attach(int64_t generation, int32_t pad, const char *name_utf8, int32_t player);
int32_t neostation_melonx_input_detach(int64_t generation, int32_t pad);
int32_t neostation_melonx_input_reset(int64_t generation, int32_t pad);
int32_t neostation_melonx_input_button(int64_t generation, int32_t pad, int32_t button, int32_t pressed);
int32_t neostation_melonx_input_stick(int64_t generation, int32_t pad, int32_t stick, float x, float y);
/* Live renderer ratio and checked, process-owned borrowed memory. */
int32_t neostation_melonx_set_aspect_ratio(int64_t generation, int32_t aspect);
int32_t neostation_melonx_memory_offer(void *address, uint64_t bytes);
int32_t neostation_melonx_memory_withdraw(void);
int32_t neostation_melonx_memory_snapshot(uint64_t *values, int32_t count);
#ifdef __cplusplus
}
#endif
#endif
