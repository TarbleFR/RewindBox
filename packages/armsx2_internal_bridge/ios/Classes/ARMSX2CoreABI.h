// SPDX-License-Identifier: GPL-3.0-or-later
// Versioned C boundary. The Flutter host never links the PCSX2 C++ ABI.
#pragma once
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
#define NEO_ARMSX2_ABI_VERSION 8u
#define NEO_ARMSX2_BOOT_DISC 1u
#define NEO_ARMSX2_BOOT_ELF 2u
// No ROM: use the installed BIOS and the same owned VM lifecycle.
#define NEO_ARMSX2_BOOT_BIOS 3u
#define NEO_ARMSX2_RA_ENABLED 1u
#define NEO_ARMSX2_RA_HARDCORE 2u
#define NEO_ARMSX2_RA_NOTIFICATIONS 3u
#define NEO_ARMSX2_RA_LEADERBOARDS 4u
#define NEO_ARMSX2_RA_OVERLAYS 5u
// Blending accuracy scopes (ABI 7): this game's INI, or PCSX2.ini for all PS2 games.
#define NEO_ARMSX2_BLENDING_SCOPE_GAME 0u
#define NEO_ARMSX2_BLENDING_SCOPE_DEFAULT 1u
// Game scope only: removes this game's choice; the default and the GameDB apply again.
#define NEO_ARMSX2_BLENDING_INHERIT (-1)

typedef void (*NeoARMSX2Event)(void* context, uint64_t transaction,
                             const char* event, const char* message);
typedef struct NeoARMSX2Configuration {
  uint32_t size;
  uint64_t transaction;
  const char* data_directory;
  const char* resource_directory;
  const char* bios_directory;
  const char* bios_filename; // Empty selects a valid BIOS, never copies it.
  NeoARMSX2Event event;
  void* context;
} NeoARMSX2Configuration;

typedef struct NeoARMSX2API {
  uint32_t size;
  uint32_t version;
  const char* source_revision;
  // UIKit calls only on main. The core retains the returned UIView.
  void* (*create_render_view)(char* error, size_t capacity);
  void (*release_render_view)(void);
  // Blocking calls only off main. All VM operations run on one owned thread.
  int (*prepare)(const NeoARMSX2Configuration*, uint32_t timeout_ms, char*, size_t);
  // Must be called while the authenticated helper still owns debugserver.
  // The breakpoint requests a real GDB D detach; failure never becomes ready.
  int (*request_jit_detach)(char*, size_t);
  int (*validate_jit)(char*, size_t);
  int (*boot)(const char* absolute_path, uint32_t kind, uint32_t timeout_ms, char*, size_t);
  void (*request_stop)(void);
  int (*shutdown)(uint32_t timeout_ms, char*, size_t);
  void (*set_paused)(int paused);
  void (*set_button)(uint32_t button, int pressed);
  void (*set_sticks)(float left_x, float left_y, float right_x, float right_y);

  // In-game ARMSX2 controls/settings. Settings target the running game's
  // per-game INI and are live-applied by the upstream ARMSX2 bridge.
  float (*get_upscale_multiplier)(void);
  uint32_t (*get_aspect_ratio)(void);
  int (*get_cheats_enabled)(void);
  int (*set_upscale_multiplier)(float value, char* error, size_t capacity);
  int (*set_aspect_ratio)(uint32_t value, char* error, size_t capacity);
  int (*set_cheats_enabled)(int enabled, char* error, size_t capacity);
  int (*reload_cheats)(char* error, size_t capacity);

  // Native catalogue from patches.zip, patches/ and cheats/. JSON includes
  // typed item IDs, unlabelled command counts and actual active counts.
  int (*get_available_patches_json)(char* output, size_t capacity);
  // Accepts a catalogue item ID (neo-patch-v1: + JSON [isCheat,name]) or a
  // legacy patch name. -1 automatic (presentation patches only), 0 off, 1 on.
  int (*set_patch_state)(const char* name, int state, char* error, size_t capacity);

  int (*has_save_state)(uint32_t slot);
  int (*save_state)(uint32_t slot, uint32_t timeout_ms, char* error, size_t capacity);
  int (*load_state)(uint32_t slot, uint32_t timeout_ms, char* error, size_t capacity);

  // RetroAchievements is implemented by upstream ARMSX2/PCSX2. The host only
  // exposes that native state and its persisted settings through this stable C ABI.
  int (*get_retroachievements_state_json)(char* output, size_t capacity);
  int (*set_retroachievements_option)(uint32_t option, int enabled,
                                      uint32_t timeout_ms, char* error, size_t capacity);
  int (*login_retroachievements)(const char* username, const char* password,
                                 uint32_t timeout_ms, char* error, size_t capacity);
  int (*logout_retroachievements)(uint32_t timeout_ms, char* error, size_t capacity);

  // Whitelisted per-game GS hacks. -1 removes this game's explicit override;
  // 0/1 select off/on. Effective state comes from the upstream GS/GameDB path.
  int (*get_graphics_hacks_json)(char* output, size_t capacity);
  int (*set_graphics_hack)(const char* key, int value, char* error, size_t capacity);
  // iOS 2.6 graphics. File I/O is off main; shader compilation stays on GS.
  int (*get_graphics_assets_json)(char* output, size_t capacity);
  int (*set_shader_preset)(const char* stable_token, char* error, size_t capacity);
  int (*set_performance_overlay)(uint32_t preset, char* error, size_t capacity);
  int (*install_shader_pack)(const char* archive_path, char* error, size_t capacity);

  // ABI 7: GSdx "Blending Accuracy" (EmuCore/GS accurate_blending_unit, 0..5).
  // JSON: available, global (default for all PS2 games), game (-1 inherits),
  // effective (EmuConfig after the GameDB), gamedbMinimum/gamedbMaximum/
  // gamedbRecommended (-1 when the database has none) and levels: the only
  // values this engine distinguishes on iPhone (core/ARMSX2BlendingAccuracy.h).
  int (*get_blending_accuracy_json)(char* output, size_t capacity);
  // Writes the INI layer of the scope, then applies live through VMManager.
  // A level outside `levels` (Medium included) is refused: no option without effect.
  int (*set_blending_accuracy)(uint32_t scope, int level, char* error, size_t capacity);

  // ABI 8: HD replacement textures of the engine (GSTextureReplacements).
  // JSON: available, serial, crc, version, title, game (-1 inherits, 0/1 this
  // game's INI), global, effective/async/precache (EmuConfig), hardware, and from
  // the GS thread indexed (file names the engine indexed), loaded (decoded and
  // cached), cacheBytes, budgetBytes (0 until set), budgetReached, bcTextures,
  // astcTextures; availableMemory (os_proc_available_memory). Errors are keys.
  int (*get_texture_replacements_json)(char* output, size_t capacity);
  // This game's INI: LoadTextureReplacements, and when on asynchronous loading
  // without preloading the whole pack. Applied to the running game at once.
  int (*set_texture_replacements)(int enabled, char* error, size_t capacity);
  // Re-indexes the running game's replacements after their files changed.
  int (*reload_texture_replacements)(char* error, size_t capacity);
  // Before boot: {"games":{"<serial>":true|false}}, NeoStation's per-game choices.
  // Once the disc is identified, the running game's choice is written to its INI
  // before the first frame. Games absent from the map keep their INI.
  int (*set_texture_boot_preferences)(const char* json, char* error, size_t capacity);
  // Decodes a .tar.zst pack with the engine's own reader into [destination]
  // (texture entries only, checked paths). Any thread; *cancel stops it,
  // *consumed reports the compressed bytes read.
  int (*expand_texture_archive)(const char* archive_path, const char* destination,
                                uint64_t available_bytes, const volatile int* cancel,
                                volatile uint64_t* consumed, char* error, size_t capacity);
} NeoARMSX2API;

typedef const NeoARMSX2API* (*NeoARMSX2GetAPI)(uint32_t version);
__attribute__((visibility("default"))) const NeoARMSX2API* NeoARMSX2_GetAPI(uint32_t version);
#ifdef __cplusplus
}
#endif
