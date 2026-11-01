#pragma once

// NEOSTATION_RPCS3_RETROACHIEVEMENTS_V1: pure rules of the PS3
// RetroAchievements client (Rpcs3Achievements.mm). Standard C++ only, so the
// same code is compiled into the bridge and by the Linux contract tests.

#include <cstdint>
#include <string>
#include <string_view>

namespace rpcs3_ra {

// rcheevos identifies a PS3 title from PARAM.SFO + EBOOT.BIN (rc_hash_ps3):
// from an .iso/.chd image, or from an EBOOT.BIN whose folder layout tells
// where PARAM.SFO is (…/PS3_GAME/USRDIR/EBOOT.BIN or …/TITLE/USRDIR/EBOOT.BIN).
// The Core reports the base library entry of the booted title (disc image or
// game directory, never an installed update or a savestate); this returns the
// path to hash, or an empty string when no supported layout exists.
template <typename FileExists>
std::string hash_source(std::string_view content_path, FileExists&& exists) {
  if (content_path.empty() || content_path.front() != '/' ||
      content_path.find('\0') != std::string_view::npos)
    return {};
  std::string path(content_path);
  while (path.size() > 1 && path.back() == '/') path.pop_back();
  auto ends_with_ci = [&path](std::string_view suffix) {
    if (path.size() < suffix.size()) return false;
    for (size_t i = 0; i < suffix.size(); ++i) {
      char c = path[path.size() - suffix.size() + i];
      if (c >= 'A' && c <= 'Z') c = static_cast<char>(c - 'A' + 'a');
      if (c != suffix[i]) return false;
    }
    return true;
  };
  if (ends_with_ci(".iso") || ends_with_ci(".chd")) return exists(path) ? path : std::string{};
  for (std::string_view suffix : {std::string_view{"/PS3_GAME/USRDIR/EBOOT.BIN"},
                                  std::string_view{"/USRDIR/EBOOT.BIN"}}) {
    std::string candidate = path + std::string(suffix);
    if (exists(candidate)) return candidate;
  }
  return {};
}

enum hardcore_block : unsigned {
  hardcore_block_none = 0,
  hardcore_block_savestate = 1u << 0,  // the session started from a savestate
  hardcore_block_cheats = 1u << 1,     // patches/cheats are enabled for the title
  hardcore_block_speed = 1u << 2,      // VBlank, clock or frame limit changes game speed
};

struct hardcore_decision {
  bool requested = false;
  bool applied = false;
  unsigned blocks = hardcore_block_none;
};

// Hardcore is applied only when the player asked for it and nothing gives an
// advantage the console would not. Otherwise the session runs in Softcore and
// the in-game status says "Hardcore not applied"; achievements still count.
constexpr hardcore_decision decide_hardcore(bool requested, bool savestate_boot, bool cheats_enabled,
                                            bool speed_compatible) {
  unsigned blocks = hardcore_block_none;
  if (requested) {
    if (savestate_boot) blocks |= hardcore_block_savestate;
    if (cheats_enabled) blocks |= hardcore_block_cheats;
    if (!speed_compatible) blocks |= hardcore_block_speed;
  }
  return hardcore_decision{requested, requested && blocks == hardcore_block_none, blocks};
}

inline std::string block_text(unsigned blocks) {
  std::string text;
  auto add = [&text](const char* item) {
    if (!text.empty()) text += ',';
    text += item;
  };
  if (blocks & hardcore_block_savestate) add("savestate");
  if (blocks & hardcore_block_cheats) add("cheats");
  if (blocks & hardcore_block_speed) add("speed");
  return text.empty() ? std::string("none") : text;
}

// Bytes reported to rcheevos for one Core read. PS3 titles allocate memory at
// run time and the Core zero-fills pages that do not exist (yet), also while a
// game restarts: reporting a short read would make rcheevos disable every
// achievement using that address for the whole session. Only a request outside
// the 32-bit guest space (Core status 1, invalid argument) is a short read.
constexpr uint32_t reported_bytes(int32_t core_status, uint32_t requested) {
  return core_status == 1 ? 0u : requested;
}

}  // namespace rpcs3_ra
