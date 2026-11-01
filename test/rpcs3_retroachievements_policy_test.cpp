// Host test of the pure rules of the PS3 RetroAchievements client
// (packages/rpcs3_internal_bridge/ios/Classes/Rpcs3AchievementsPolicy.h) and of
// the host copy of the optional Core ABI (Rpcs3AchievementsABI.h).
// Compiled and run by test/rpcs3_retroachievements_test.py.
#include <cstddef>
#include <cstdio>
#include <set>
#include <string>

#include "Rpcs3AchievementsABI.h"
#include "Rpcs3AchievementsPolicy.h"

static int failures = 0;
#define CHECK(condition) do { if (!(condition)) { std::fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #condition); ++failures; } } while (0)

static_assert(offsetof(rpcs3_ios_ra_session_info, boot_generation) == 24, "boot_generation offset");
static_assert(offsetof(rpcs3_ios_ra_session_info, title_id) == 32, "title_id offset");
static_assert(offsetof(rpcs3_ios_ra_session_info, content_path) == 96, "content_path offset");

int main() {
  std::set<std::string> files;
  auto exists = [&files](const std::string& path) { return files.count(path) != 0; };
  using rpcs3_ra::hash_source;

  // Disc image imported by the Core library: hashed through the ISO reader.
  files = {"/Data/games/BLUS30001/disc.iso"};
  CHECK(hash_source("/Data/games/BLUS30001/disc.iso", exists) == "/Data/games/BLUS30001/disc.iso");
  files = {"/Data/games/X/GAME.ISO"};
  CHECK(hash_source("/Data/games/X/GAME.ISO", exists) == "/Data/games/X/GAME.ISO");
  files = {};
  CHECK(hash_source("/Data/games/BLUS30001/disc.iso", exists).empty());

  // Extracted disc folder: PS3_GAME/USRDIR/EBOOT.BIN (PARAM.SFO in PS3_GAME).
  files = {"/Data/games/ExtractedGames/BLES00001/PS3_GAME/USRDIR/EBOOT.BIN"};
  CHECK(hash_source("/Data/games/ExtractedGames/BLES00001/", exists) ==
        "/Data/games/ExtractedGames/BLES00001/PS3_GAME/USRDIR/EBOOT.BIN");

  // Installed PSN/HDD title: TITLE/USRDIR/EBOOT.BIN (PARAM.SFO in TITLE).
  files = {"/Data/dev_hdd0/game/NPUB30002/USRDIR/EBOOT.BIN"};
  CHECK(hash_source("/Data/dev_hdd0/game/NPUB30002", exists) == "/Data/dev_hdd0/game/NPUB30002/USRDIR/EBOOT.BIN");

  // The disc layout wins when both exist; nothing else is guessed.
  files = {"/G/PS3_GAME/USRDIR/EBOOT.BIN", "/G/USRDIR/EBOOT.BIN"};
  CHECK(hash_source("/G", exists) == "/G/PS3_GAME/USRDIR/EBOOT.BIN");
  files = {"/G/EBOOT.BIN"};
  CHECK(hash_source("/G", exists).empty());
  CHECK(hash_source("", exists).empty());
  CHECK(hash_source("relative/path", exists).empty());
  CHECK(hash_source(std::string_view("/G\0/x", 5), exists).empty());

  using rpcs3_ra::decide_hardcore;
  auto none = decide_hardcore(false, true, true, false);
  CHECK(!none.requested && !none.applied && none.blocks == rpcs3_ra::hardcore_block_none);
  auto clean = decide_hardcore(true, false, false, true);
  CHECK(clean.requested && clean.applied && clean.blocks == rpcs3_ra::hardcore_block_none);
  auto state = decide_hardcore(true, true, false, true);
  CHECK(!state.applied && state.blocks == rpcs3_ra::hardcore_block_savestate);
  auto cheats = decide_hardcore(true, false, true, true);
  CHECK(!cheats.applied && cheats.blocks == rpcs3_ra::hardcore_block_cheats);
  auto speed = decide_hardcore(true, false, false, false);
  CHECK(!speed.applied && speed.blocks == rpcs3_ra::hardcore_block_speed);
  auto all = decide_hardcore(true, true, true, false);
  CHECK(!all.applied && rpcs3_ra::block_text(all.blocks) == "savestate,cheats,speed");
  CHECK(rpcs3_ra::block_text(rpcs3_ra::hardcore_block_none) == "none");

  // Only an argument outside the guest space is a short read for rcheevos.
  CHECK(rpcs3_ra::reported_bytes(RPCS3_IOS_RA_STATUS_OK, 4) == 4);
  CHECK(rpcs3_ra::reported_bytes(RPCS3_IOS_RA_STATUS_INVALID_STATE, 4) == 4);
  CHECK(rpcs3_ra::reported_bytes(7, 2) == 2);
  CHECK(rpcs3_ra::reported_bytes(RPCS3_IOS_RA_STATUS_INVALID_ARGUMENT, 4) == 0);

  CHECK(RPCS3_IOS_RA_API_VERSION == 1u);
  CHECK(RPCS3_IOS_RA_EMULATION_RUNNING == 5u && RPCS3_IOS_RA_EMULATION_PAUSED == 6u);
  if (failures) {
    std::fprintf(stderr, "%d check(s) failed\n", failures);
    return 1;
  }
  std::puts("PASS: PS3 RetroAchievements host rules (hash source, Hardcore decision, read results, ABI layout)");
  return 0;
}
