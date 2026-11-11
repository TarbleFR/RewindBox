// SPDX-License-Identifier: BSD-3-Clause
// Versioned C boundary between RewindBox and the embedded XeniOS (Xenia)
// Core. The Flutter host never links the Xenia C++ ABI, its statically
// linked third-party code (FFmpeg, fmt, SDL3, imgui, capstone, mbedtls) or
// its globals: XeniaCore.framework exports only NeoXenia_GetAPI
// (core/exports.txt). See docs/xenios-playlist.md § Native boundary.
#pragma once
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

// ABI 2 adds jit_state (the JIT helper decision). ABI 1 was never built.
#define NEO_XENIA_ABI_VERSION 2u

// The Core is built from XeniOS with its upstream iOS 26.0 deployment
// target (XeniOS CMakeLists.txt:4-11). The host app targets iOS 18: the
// bridge dlopens the framework only on iOS 26 or later.
#define NEO_XENIA_MINIMUM_IOS_MAJOR 26u

// Content kinds passed to boot(); the Core resolves them with Xenia's own
// Emulator::LaunchPath, which picks the VFS device from the file.
#define NEO_XENIA_CONTENT_DISC_IMAGE 1u  // .iso (XGD/XISO)
#define NEO_XENIA_CONTENT_ZAR 2u         // .zar (ZArchive)
#define NEO_XENIA_CONTENT_EXECUTABLE 3u  // loose default.xex in its folder
#define NEO_XENIA_CONTENT_PACKAGE 4u     // GOD/SVOD header + .data, or STFS file

// jit_state() bits (XeniOS cpu/backend/jit_memory_ios.h and
// ui/ios/shared/ios_system_utils.h). Callable right after dlopen, before
// prepare: nothing is initialized.
// The next title can only boot while a JIT tool is attached that answers
// the Core's brk #0xf00d prepare (x16=1) and detach (x16=0) requests: TXM
// device on iOS 26+, code region not yet prepared in this process.
#define NEO_XENIA_JIT_NEEDS_TOOL (1u << 0)
// A debugger is attached now (P_TRACED).
#define NEO_XENIA_JIT_TOOL_ATTACHED (1u << 1)
// The process is CS_DEBUGGED (stays set after the tool detaches).
#define NEO_XENIA_JIT_CS_DEBUGGED (1u << 2)
// The Core uses the TXM broker path (dual-mapped, prepared region).
#define NEO_XENIA_JIT_BROKER_PATH (1u << 3)

// Events reported by the Core on any thread. `event` is one of:
// "firstFrame", "paused", "resumed", "stopped", "error". `message` is a
// technical diagnostic, never a user-facing string.
typedef void (*NeoXeniaEvent)(void* context, uint64_t transaction,
                              const char* event, const char* message);

// One cvar override. Only the keys listed in RewindBox's catalogue
// (lib/services/xenia_settings_service.dart) are sent; the Core refuses
// any other key. Values are TOML-like text: "true"/"false", decimal
// integers, or plain strings. Every managed key is sent at every launch
// with its effective value, so nothing from a previous title survives.
typedef struct NeoXeniaSetting {
  const char* key;
  const char* value;
} NeoXeniaSetting;

typedef struct NeoXeniaConfiguration {
  uint32_t size;
  uint64_t transaction;
  // config::SetupConfig storage root (xenia-edge.config.toml, config/,
  // logs). RewindBox's Documents/XeniOS/Engine.
  const char* storage_root;
  // Xenia content root (saves, title updates, DLC): Documents/XeniOS/Content.
  const char* content_root;
  // Shader/pipeline cache root: Library/Caches/XeniOS.
  const char* cache_root;
  // Applied after config::LoadGameConfigForFile, so they win over the
  // engine's own per-game TOML for this session only (never written back).
  const NeoXeniaSetting* settings;
  uint32_t settings_count;
  NeoXeniaEvent event;
  void* context;
} NeoXeniaConfiguration;

typedef struct NeoXeniaAPI {
  uint32_t size;
  uint32_t version;
  const char* source_revision;  // XeniOS commit the Core was built from.
  // UIKit calls only on main. The Core owns the returned view (its layer is
  // a CAMetalLayer used by Xenia's iOSUIViewSurface) until release.
  void* (*create_render_view)(char* error, size_t capacity);
  void (*release_render_view)(void);
  // Blocking calls only off main. One xe::Emulator lives for the process;
  // a stopped title is torn down with Emulator::ResetTitle so a second
  // session reuses it (XeniOS xenia_main_ios.mm:2475).
  int (*prepare)(const NeoXeniaConfiguration*, uint32_t timeout_ms, char*,
                 size_t);
  // JIT: XeniOS dual-maps its code cache through an attached debugger
  // (cpu/backend/jit_memory_ios.cc). Fails, never pretends, without one.
  int (*validate_jit)(char*, size_t);
  int (*boot)(const char* absolute_path, uint32_t kind, uint32_t timeout_ms,
              char*, size_t);
  void (*set_paused)(int paused);
  void (*request_stop)(void);
  // Waits for the title teardown; afterwards no callback for that
  // transaction is delivered.
  int (*shutdown)(uint32_t timeout_ms, char*, size_t);
  // Xbox 360 pad of user 0 (X_INPUT_GAMEPAD_* bit values) and sticks in
  // [-1, 1], triggers in [0, 1].
  void (*set_buttons)(uint32_t buttons);
  void (*set_axes)(float left_x, float left_y, float right_x, float right_y,
                   float left_trigger, float right_trigger);
  // ABI 2: NEO_XENIA_JIT_* bits; any thread.
  uint32_t (*jit_state)(void);
} NeoXeniaAPI;

typedef const NeoXeniaAPI* (*NeoXeniaGetAPI)(uint32_t version);
__attribute__((visibility("default"))) const NeoXeniaAPI* NeoXenia_GetAPI(
    uint32_t version);

#ifdef __cplusplus
}
#endif
