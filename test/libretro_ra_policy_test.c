// Executes the exact pinned rcheevos option rules and memory mapping.
// This portable test does not claim to emulate a game or authenticate RA.
#include "rc_client.h"
#include "rc_libretro.h"
#include "rc_consoles.h"
#include <stdio.h>
#include <string.h>

_Static_assert(_Generic(&rc_client_set_hardcore_enabled,
    void (*)(rc_client_t *, int): 1, default: 0), "hardcore API signature");
_Static_assert(_Generic(&rc_client_can_pause,
    int (*)(rc_client_t *, uint32_t *): 1, default: 0), "pause API signature");
_Static_assert(_Generic(&rc_client_set_allow_background_memory_reads,
    void (*)(rc_client_t *, int): 1, default: 0), "background-memory API signature");

static unsigned checks, failures;
static void expect(int condition, const char *message) {
  ++checks;
  if (!condition) { ++failures; fprintf(stderr, "FAIL %s\n", message); }
}

static int allowed(const char *library, uint32_t system, const char *key, const char *value) {
  const rc_disallowed_setting_t *all = rc_libretro_get_disallowed_settings(library);
  const rc_disallowed_setting_t *specific = rc_libretro_get_disallowed_settings_for_system(library, system);
  return (!all || rc_libretro_is_setting_allowed(all, key, value)) &&
         (!specific || rc_libretro_is_setting_allowed(specific, key, value));
}

static uint8_t ram[8192];
static int expose_ram;
static void memory_info(uint32_t id, rc_libretro_core_memory_info_t *info) {
  info->data = expose_ram && id == RETRO_MEMORY_SYSTEM_RAM ? ram : NULL;
  info->size = info->data ? sizeof(ram) : 0;
}

int main(void) {
  const struct { const char *library, *key, *value; int expected; } cases[] = {
    {"Beetle PSX", "beetle_psx_cpu_freq_scale", "99", 0},
    {"Beetle PSX", "beetle_psx_cpu_freq_scale", "100", 1},
    {"Beetle PSX HW", "beetle_psx_hw_cpu_freq_scale", "50", 0},
    {"Beetle PSX HW", "beetle_psx_hw_cpu_freq_scale", "100", 1},
    {"FinalBurn Neo", "fbneo-allow-patched-romsets", "enabled", 0},
    {"FinalBurn Neo", "fbneo-allow-patched-romsets", "disabled", 1},
    {"FinalBurn Neo", "fbneo-cheat-1-test-infinite", "1 - Enabled", 0},
    {"FinalBurn Neo", "fbneo-cheat-1-test-infinite", "0 - Disabled", 1},
    {"FinalBurn Neo", "fbneo-cheat-1-test-infinite", "Disabled", 1},
    {"FinalBurn Neo", "fbneo-cpu-speed-adjust", "50%", 0},
    {"FinalBurn Neo", "fbneo-cpu-speed-adjust", "100%", 1},
    {"FinalBurn Neo", "fbneo-neogeo-mode", "UNIBIOS", 0},
    {"FinalBurn Neo", "fbneo-dipswitch-test-bios", "Universe BIOS v4", 0},
    {"Genesis Plus GX", "genesis_plus_gx_lock_on", "game genie", 0},
    {"Genesis Plus GX", "genesis_plus_gx_lock_on", "disabled", 1},
    {"Genesis Plus GX", "genesis_plus_gx_region_detect", "pal", 0},
    {"Genesis Plus GX", "genesis_plus_gx_region_detect", "auto", 1},
    {"Genesis Plus GX Wide", "genesis_plus_gx_wide_lock_on", "action replay (pro)", 0},
    {"Genesis Plus GX Wide", "genesis_plus_gx_wide_region_detect", "pal", 0},
    {"Mesen", "mesen_region", "Dendy", 0},
    {"Mesen", "mesen_region", "PAL", 0},
    {"Mesen", "mesen_region", "Auto", 1},
    {"PicoDrive", "picodrive_region", "Europe", 0},
    {"PicoDrive", "picodrive_region", "Japan PAL", 0},
    {"PicoDrive", "picodrive_region", "Auto", 1},
    {"PPSSPP", "ppsspp_cheats", "enabled", 0},
    {"PPSSPP", "ppsspp_cheats", "disabled", 1},
    {"Snes9x", "snes9x_gfx_clip", "disabled", 0},
    {"Snes9x", "snes9x_gfx_transp", "disabled", 0},
    {"Snes9x", "snes9x_layer_1", "disabled", 0},
    {"Snes9x", "snes9x_region", "pal", 0},
    {"Snes9x", "snes9x_region", "auto", 1},
    {"Snes9x", "unrelated_display_option", "disabled", 1},
  };
  for (unsigned i = 0; i < sizeof(cases) / sizeof(cases[0]); ++i) {
    int result = allowed(cases[i].library, 0, cases[i].key, cases[i].value);
    if (result != cases[i].expected)
      fprintf(stderr, "%s: %s=%s\n", cases[i].library, cases[i].key, cases[i].value);
    expect(result == cases[i].expected, "pinned core-option policy");
  }
  expect(!allowed("melonDS", RC_CONSOLE_NINTENDO_DS, "melonds_console_mode", "dsi"),
         "system-specific restrictions are included");
  expect(!rc_libretro_is_system_allowed("Mesen-S", RC_CONSOLE_GAMEBOY),
         "pinned incompatible library/system pair is rejected");
  expect(rc_libretro_is_system_allowed("Mesen", RC_CONSOLE_NINTENDO),
         "the Mesen NES alternative is not confused with Mesen-S");
  rc_libretro_memory_regions_t regions = {0};
  expect(!rc_libretro_memory_init(&regions, NULL, memory_info, RC_CONSOLE_NINTENDO),
         "no actual memory pointer cannot produce a valid region map");
  rc_libretro_memory_destroy(&regions);
  expose_ram = 1;
  ram[0] = 0x42;
  expect(rc_libretro_memory_init(&regions, NULL, memory_info, RC_CONSOLE_NINTENDO),
         "actual emulated RAM is accepted");
  uint8_t byte = 0;
  expect(rc_libretro_memory_read(&regions, 0, &byte, 1) == 1 && byte == 0x42,
         "achievement reads use the mapped core memory");
  expect(rc_libretro_memory_read(&regions, UINT32_MAX, &byte, 1) == 0,
         "an invalid achievement address is not fabricated as valid memory");
  rc_libretro_memory_destroy(&regions);
  expect(regions.count == 0 && regions.total_size == 0, "memory-map teardown clears the previous session");
  printf("%u pinned RA policy/memory checks, %u failures\n", checks, failures);
  return failures ? 1 : 0;
}
