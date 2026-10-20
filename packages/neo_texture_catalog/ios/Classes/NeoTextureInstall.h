// SPDX-License-Identifier: GPL-3.0-or-later
// File-system core of the HD texture installer: which files an engine reads,
// how an archive maps to the engine's per-game folders, staging, the swap
// that replaces a folder, crash recovery and removal. Portable C++ so the
// exact code shipped in the app is exercised on any test host.
#pragma once
#include "NeoTextureArchive.h"
#include "NeoTextureSevenZip.h"
#include <algorithm>
#include <cerrno>
#include <cstdio>
#include <dirent.h>
#include <filesystem>
#include <map>
#include <fstream>
#include <ftw.h>
#include <random>
#include <regex>
#include <set>
#include <sstream>

namespace NeoTextureInstall {

enum class Engine { dolphin, armsx2, ppsspp, azahar, mupen64plus, beetle, mesen };

inline std::string Lower(std::string s) { for (char& c : s) if (c >= 'A' && c <= 'Z') c = char(c + 32); return s; }
inline std::string UpperCase(std::string s) { for (char& c : s) if (c >= 'a' && c <= 'z') c = char(c - 32); return s; }
inline std::string Extension(const std::string& path) {
  const size_t slash = path.rfind('/'), dot = path.rfind('.');
  return dot == std::string::npos || (slash != std::string::npos && dot < slash) ? "" : Lower(path.substr(dot + 1));
}
inline std::string Basename(const std::string& path) {
  const size_t slash = path.rfind('/');
  return slash == std::string::npos ? path : path.substr(slash + 1);
}
inline std::vector<std::string> Split(const std::string& path) {
  std::vector<std::string> parts;
  size_t start = 0;
  while (start <= path.size()) {
    size_t end = path.find('/', start);
    if (end == std::string::npos) end = path.size();
    if (end > start) parts.push_back(path.substr(start, end - start));
    start = end + 1;
  }
  return parts;
}
inline bool Matches(const std::string& value, const char* pattern) {
  return std::regex_match(value, std::regex(pattern));
}

// Beetle PSX HW (beetle-psx-libretro 10e4b0c, rhi/rhi_tt.c read_texture_directory):
// "<hash>-<palette>.<ext>" in hexadecimal, the extension any of its decoders
// without case (tt_replacement_exts: png, dds, webp, jpg, jpeg, bmp, tga).
inline bool BeetleTextureName(const std::string& name) {
  static const std::regex pattern("^[0-9A-Fa-f]{1,8}-[0-9A-Fa-f]{1,8}\\.(png|dds|webp|jpg|jpeg|bmp|tga)$", std::regex::icase);
  return std::regex_match(name, pattern);
}

// Files the engine reads in a pack folder (anything else is not installed).
inline bool Accepts(Engine engine, const std::string& relative) {
  const std::string name = Basename(relative), extension = Extension(name), lower = Lower(name);
  switch (engine) {
    case Engine::dolphin:
      // HiresTexture::Update: tex1_*.png|dds. GetTextureDirectoriesWithGameId:
      // a <GameID|ID3|all>.txt anywhere selects its top folder for that game
      // (compared exactly with the upper-case Game ID).
      if (extension == "txt") return Matches(name.substr(0, name.size() - 4), "^([A-Z0-9]{3}|[A-Z0-9]{6}|all)$");
      return name.rfind("tex1_", 0) == 0 && (extension == "png" || extension == "dds");
    case Engine::armsx2:
      // GSTextureReplacementLoaders.cpp registers png, dds, astc and ktx.
      return extension == "png" || extension == "dds" || extension == "astc" || extension == "ktx";
    case Engine::ppsspp:
      if (lower == "textures.ini" || lower == "textures.zip") return relative.find('/') == std::string::npos;
      return extension == "png" || extension == "dds" || extension == "zim" || extension == "ktx2";
    case Engine::azahar: {
      // CustomTexManager: pack.json at the root (ReadConfig); a texture is
      // <name>[.<map>].<png|dds|ktx>, its extension compared exactly and a
      // name of more than three dot-separated parts ignored (ParseFilename).
      if (name == "pack.json") return relative.find('/') == std::string::npos;
      const size_t dot = name.rfind('.');
      const std::string raw = dot == std::string::npos ? "" : name.substr(dot + 1);
      if (std::count(name.begin(), name.end(), '.') > 2) return false;
      return raw == "png" || raw == "dds" || raw == "ktx";
    }
    case Engine::mupen64plus: {
      // GLideNHQ (TxHiResLoader::checkFileName, _loadHiResTextures): a Rice
      // texture <ROM name>#<crc>#<fmt>#<siz>..., ".png" or ".bmp" compared
      // exactly; names starting with "." and folders "~!~..." are skipped.
      for (const auto& part : Split(relative))
        if (part.front() == '.' || part.rfind("~!~", 0) == 0) return false;
      const std::string raw = name.size() >= 4 ? name.substr(name.size() - 4) : "";
      return (raw == ".png" || raw == ".bmp") && name.find('#') != std::string::npos && name.front() != '#';
    }
    case Engine::beetle:
      // The core lists the folder's own entries only (no subfolder), and
      // keeps the Lazy modes' prefetch journal next to the textures.
      if (relative.find('/') != std::string::npos) return false;
      return name == "prefetch.journal" || BeetleTextureName(name);
    case Engine::mesen:
      // Mesen (libretro Mesen 0102910, HdPackLoader.cpp): hires.txt and the
      // optional palette.dat at the pack root (opened by these exact names),
      // the PNG images, OGG music and effects and IPS/UPS/BPS ROM patches
      // hires.txt names, by paths relative to the pack folder.
      if (name == "hires.txt" || name == "palette.dat") return relative.find('/') == std::string::npos;
      return extension == "png" || extension == "ogg" || extension == "ips" || extension == "ups" || extension == "bps";
  }
  return false;
}

// N64 (GLideNHQ): the ROM name a Rice texture names, the part before its first "#".
inline std::string RiceName(const std::string& relative) {
  const std::string name = Basename(relative);
  const size_t hash = name.find('#');
  return hash == std::string::npos ? "" : name.substr(0, hash);
}

// An accepted file that is a texture (not a Game ID marker, textures.ini or
// pack.json): a pack without one replaces nothing.
inline bool IsTexture(Engine engine, const std::string& relative) {
  if (!Accepts(engine, relative)) return false;
  const std::string lower = Lower(Basename(relative));
  switch (engine) {
    case Engine::dolphin: return Extension(lower) != "txt";
    case Engine::ppsspp: return lower != "textures.ini";
    case Engine::azahar: return Basename(relative) != "pack.json";
    case Engine::armsx2: return true;
    case Engine::mupen64plus: return true;
    case Engine::beetle: return Basename(relative) != "prefetch.journal";
    case Engine::mesen: return Extension(lower) == "png";
  }
  return false;
}

inline bool HasTextures(Engine engine, const std::string& folder) {
  std::error_code error;
  for (std::filesystem::recursive_directory_iterator walker(folder, error), end; !error && walker != end; walker.increment(error)) {
    if (!walker->is_regular_file(error)) continue;
    const std::string relative = std::filesystem::relative(walker->path(), folder, error).generic_string();
    if (!error && IsTexture(engine, relative)) return true;
  }
  return false;
}

// PNG and DDS files must start with their signature.
inline bool SignatureOK(const std::string& path) {
  const std::string extension = Extension(path);
  if (extension != "png" && extension != "dds") return true;
  NeoTextureArchive::File file;
  unsigned char head[8] = {0};
  if (!file.open(path) || file.length() < 8 || !file.read(0, head, 8)) return false;
  static const unsigned char png[8] = {137, 80, 78, 71, 13, 10, 26, 10};
  return extension == "png" ? !std::memcmp(head, png, 8) : !std::memcmp(head, "DDS ", 4);
}

// Mesen HD pack definition (libretro Mesen 0102910, HdPackLoader::LoadPack):
// what the core would refuse, read from the staged folder. <ver> above 106 is
// refused by the core (HdNesPack::CurrentVersion); an <img> it cannot read
// makes the whole pack fail, while a missing <background>, <patch>, <bgm> or
// <sfx> file is skipped by the core and only reported. Every image and
// background is decoded whole when the game starts: decodedBytes counts
// their width x height x 4 bytes, which the app compares with the memory the
// device can give (the core has no lazy loading).
inline constexpr int kMesenFormatVersion = 106;

struct MesenPack {
  int version = 0, scale = 1;
  uint64_t decodedBytes = 0;
  std::vector<std::string> roms;     // SHA-1 of the ROM files the pack names (<supportedRom>, <patch>), upper case
  std::vector<std::string> missing;  // <img> files hires.txt names that are not in the folder
  std::vector<std::string> skipped;  // other files it names that are absent (the core skips them)
  std::string problem;               // missingHires, formatTooNew, missingFiles, archiveDamaged, noTextures
};

inline bool PNGSize(const std::string& path, uint32_t* width, uint32_t* height) {
  NeoTextureArchive::File file;
  unsigned char head[24] = {0};
  static const unsigned char png[8] = {137, 80, 78, 71, 13, 10, 26, 10};
  if (!file.open(path) || file.length() < 24 || !file.read(0, head, 24) || std::memcmp(head, png, 8) || std::memcmp(head + 12, "IHDR", 4))
    return false;
  *width = uint32_t(head[16]) << 24 | uint32_t(head[17]) << 16 | uint32_t(head[18]) << 8 | head[19];
  *height = uint32_t(head[20]) << 24 | uint32_t(head[21]) << 16 | uint32_t(head[22]) << 8 | head[23];
  return *width && *height && *width <= 32768 && *height <= 32768;
}

inline MesenPack CheckMesenPack(const std::string& folder) {
  MesenPack pack;
  NeoTextureArchive::File file;
  if (!file.open(folder + "/hires.txt") || file.length() > (64ULL << 20)) { pack.problem = "missingHires"; return pack; }
  std::string text(size_t(file.length()), '\0');
  if (!text.empty() && !file.read(0, &text[0], text.size())) { pack.problem = "missingHires"; return pack; }
  std::set<std::string> roms, images, backgrounds, others;
  // Field `index` of a comma-separated tag value, with Mesen's '\' -> '/'.
  auto field = [](const std::string& value, size_t index) {
    size_t start = 0;
    for (size_t i = 0; i < index; ++i) {
      start = value.find(',', start);
      if (start == std::string::npos) return std::string();
      ++start;
    }
    const size_t end = value.find(',', start);
    std::string part = value.substr(start, end == std::string::npos ? std::string::npos : end - start);
    std::replace(part.begin(), part.end(), '\\', '/');
    return part;
  };
  std::istringstream lines(text);
  for (std::string line; std::getline(lines, line);) {
    if (!line.empty() && line.back() == '\r') line.pop_back();
    // A [condition] prefix applies to the tag that follows it.
    if (!line.empty() && line.front() == '[') {
      const size_t close = line.find(']');
      if (close == std::string::npos) continue;
      line = line.substr(close + 1);
    }
    auto value = [&](const char* tag, std::string* out) {
      const size_t n = std::strlen(tag);
      if (line.compare(0, n, tag) != 0) return false;
      *out = line.substr(n);
      return true;
    };
    std::string rest;
    if (value("<ver>", &rest)) pack.version = std::atoi(rest.c_str());
    else if (value("<scale>", &rest)) pack.scale = std::max(1, std::atoi(rest.c_str()));
    else if (value("<img>", &rest)) { std::replace(rest.begin(), rest.end(), '\\', '/'); images.insert(rest); }
    else if (value("<background>", &rest)) backgrounds.insert(field(rest, 0));
    else if (value("<patch>", &rest)) {
      others.insert(field(rest, 0));
      const std::string hash = UpperCase(field(rest, 1));
      if (Matches(hash, "^[0-9A-F]{40}$")) roms.insert(hash);
    } else if (value("<bgm>", &rest) || value("<sfx>", &rest)) others.insert(field(rest, 2));
    else if (value("<supportedRom>", &rest)) {
      const std::string hash = UpperCase(rest.substr(0, std::min<size_t>(40, rest.size())));
      if (Matches(hash, "^[0-9A-F]{40}$")) roms.insert(hash);
    }
  }
  pack.roms.assign(roms.begin(), roms.end());
  if (pack.version > kMesenFormatVersion) { pack.problem = "formatTooNew"; return pack; }
  struct stat st {};
  auto present = [&](const std::string& relative) {
    if (relative.empty() || relative.front() == '/') return false;
    for (const auto& part : Split(relative)) if (part == "..") return false;
    return ::lstat((folder + "/" + relative).c_str(), &st) == 0 && S_ISREG(st.st_mode);
  };
  for (const auto& image : images) {
    if (!present(image)) { pack.missing.push_back(image); continue; }
    uint32_t width = 0, height = 0;
    if (!PNGSize(folder + "/" + image, &width, &height)) { pack.problem = "archiveDamaged"; return pack; }
    pack.decodedBytes += uint64_t(width) * height * 4;
  }
  for (const auto& background : backgrounds) {
    uint32_t width = 0, height = 0;
    if (present(background) && PNGSize(folder + "/" + background, &width, &height)) pack.decodedBytes += uint64_t(width) * height * 4;
    else if (!background.empty()) pack.skipped.push_back(background);
  }
  for (const auto& other : others)
    if (!other.empty() && !present(other)) pack.skipped.push_back(other);
  if (images.empty()) pack.problem = "noTextures";
  else if (!pack.missing.empty()) pack.problem = "missingFiles";
  return pack;
}

// One folder of a pack: the archive subtree `from` (prefix, "" = root)
// installed as `to`, without the subfolders listed in `exclude` (prefixes
// relative to `from`: sources, original dumps, alternative variants).
struct Rule {
  std::string from, to;
  std::vector<std::string> exclude;
};

// Index of the rule whose prefix holds `name` (the longest wins) and the
// path below it; -1 when no rule applies or the path is excluded.
inline int Map(const std::vector<Rule>& rules, const std::string& name, std::string* inside) {
  int best = -1;
  size_t bestLength = 0;
  for (size_t i = 0; i < rules.size(); ++i) {
    const std::string& from = rules[i].from;
    if (name.size() > from.size() && name.compare(0, from.size(), from) == 0 && (best < 0 || from.size() > bestLength)) {
      best = int(i);
      bestLength = from.size();
    }
  }
  if (best < 0) return -1;
  const std::string below = name.substr(bestLength);
  for (const std::string& prefix : rules[size_t(best)].exclude)
    if (!prefix.empty() && below.size() >= prefix.size() && below.compare(0, prefix.size(), prefix) == 0) return -1;
  if (inside) *inside = below;
  return best;
}

inline bool PS2Serial(const std::string& part, std::string* folder) {
  const std::string up = UpperCase(part);
  std::smatch m;
  static const std::regex pattern("^([A-Z]{4})[-_ ]?([0-9]{3})\\.?([0-9]{2})$");
  if (!std::regex_match(up, m, pattern)) return false;
  if (folder) *folder = m[1].str() + "-" + m[2].str() + m[3].str();
  return true;
}

struct Layout {
  std::vector<Rule> rules;
  std::vector<std::string> found;   // identifiers the archive names
  bool otherRegion = false;         // names another region/edition: confirmation needed
  std::string problem;              // noTextures, otherGame, missingIni
};

// Decides where an imported folder or archive goes for the current game.
// `current` is the game's folder ID: GZ2E01, SLUS-21050, ULUS10041 or 16 hex.
inline Layout Detect(Engine engine, const std::vector<std::string>& files, const std::string& current) {
  Layout layout;
  std::set<std::string> found;
  auto finish = [&](const std::string& from, const std::string& to) {
    layout.rules.push_back({from, to, {}});
    size_t usable = 0;
    for (const auto& file : files) {
      std::string inside;
      if (Map(layout.rules, file, &inside) >= 0 && IsTexture(engine, inside)) usable++;
    }
    if (!usable) layout.problem = "noTextures";
    layout.found.assign(found.begin(), found.end());
    return layout;
  };
  if (engine == Engine::dolphin) {
    const std::string family = current.substr(0, std::min<size_t>(3, current.size()));
    std::string root, rootID;
    bool foreign = false;
    for (const auto& file : files) {
      const auto parts = Split(file);
      if (parts.empty() || !Accepts(engine, parts.back()) || parts.back().rfind("tex1_", 0) != 0) continue;
      for (size_t i = 0; i + 1 < parts.size(); ++i) {
        const std::string id = UpperCase(parts[i]);
        const bool sixChar = Matches(id, "^[A-Z0-9]{6}$"), threeChar = Matches(id, "^[A-Z0-9]{3}$");
        if (!sixChar && !threeChar) continue;
        if (id.substr(0, 3) != family) { if (sixChar) { foreign = true; found.insert(id); } continue; }
        found.insert(id);
        std::string prefix;
        for (size_t k = 0; k <= i; ++k) prefix += parts[k] + "/";
        if (root.empty() || prefix.size() < root.size()) { root = prefix; rootID = id; }
        break;
      }
    }
    if (root.empty()) {
      if (foreign) { layout.problem = "otherGame"; layout.found.assign(found.begin(), found.end()); return layout; }
      return finish("", current);
    }
    // Region-free (3 characters) or this game's ID keep their folder; another
    // region of the family is installed as this game after confirmation.
    if (rootID == current || rootID.size() == 3) return finish(root, rootID);
    layout.otherRegion = true;
    return finish(root, current);
  }
  if (engine == Engine::armsx2) {
    const std::string target = current + "/replacements";
    std::string root;
    bool other = false;
    for (const auto& file : files) {
      const auto parts = Split(file);
      for (size_t i = 0; i + 1 < parts.size(); ++i) {
        std::string serial;
        if (!PS2Serial(parts[i], &serial)) continue;
        found.insert(serial);
        if (serial != current) other = true;
        std::string prefix;
        for (size_t k = 0; k <= i; ++k) prefix += parts[k] + "/";
        if (root.empty() || prefix.size() < root.size()) root = prefix;
        break;
      }
    }
    if (!root.empty()) {
      // <SERIAL>/replacements/ when the pack has it (a dumps/ folder is never installed).
      for (const auto& file : files)
        if (file.size() > root.size() && file.compare(0, root.size(), root) == 0) {
          const auto rest = Split(file.substr(root.size()));
          if (rest.size() >= 2 && Lower(rest[0]) == "replacements") { root += rest[0] + "/"; break; }
        }
      layout.otherRegion = other;
      return finish(root, target);
    }
    for (const auto& file : files) {
      const auto parts = Split(file);
      for (size_t i = 0; i + 1 < parts.size(); ++i)
        if (Lower(parts[i]) == "replacements") {
          std::string prefix;
          for (size_t k = 0; k <= i; ++k) prefix += parts[k] + "/";
          if (root.empty() || prefix.size() < root.size()) root = prefix;
          break;
        }
    }
    return finish(root, target);
  }
  if (engine == Engine::mupen64plus) {
    // hires_texture/<ROM name>/, read with its subfolders: the folder named
    // after the ROM name the textures carry, else the folders holding them.
    std::vector<std::string> root;
    bool other = false, have = false;
    for (const auto& file : files) {
      if (!Accepts(engine, file)) continue;
      const std::string rom = RiceName(file);
      found.insert(rom);
      if (rom != current) other = true;
      std::vector<std::string> folders = Split(file);
      folders.pop_back();
      const auto named = std::find(folders.begin(), folders.end(), rom);
      if (named != folders.end()) folders.erase(named + 1, folders.end());
      if (!have) { root = folders; have = true; continue; }
      size_t common = 0;
      while (common < root.size() && common < folders.size() && root[common] == folders[common]) ++common;
      root.resize(common);
    }
    if (!have) { layout.problem = "noTextures"; return layout; }
    // GLideNHQ loads a texture only when its name holds this ROM's name.
    if (other && found.size() == 1) { layout.problem = "otherGame"; layout.found.assign(found.begin(), found.end()); return layout; }
    layout.otherRegion = other;
    std::string prefix;
    for (const auto& part : root) prefix += part + "/";
    return finish(prefix, current);
  }
  if (engine == Engine::ppsspp) {
    std::string root;
    bool have = false;
    for (const auto& file : files) {
      const std::string name = Lower(Basename(file));
      if (name != "textures.ini" && name != "textures.zip") continue;
      const std::string prefix = file.substr(0, file.size() - Basename(file).size());
      if (!have || prefix.size() < root.size()) { root = prefix; have = true; }
    }
    if (!have) { layout.problem = "missingIni"; return layout; }
    const auto parts = Split(root);
    if (!parts.empty()) {
      std::string compact;
      for (char c : UpperCase(parts.back())) if (c != '-' && c != '_') compact += c;
      if (Matches(compact, "^[A-Z]{4}[0-9]{5}$")) {
        found.insert(compact);
        layout.otherRegion = compact != current;
      }
    }
    return finish(root, current);
  }
  if (engine == Engine::mesen) {
    // HdPacks/<content name>/: the folder of the shallowest hires.txt (an
    // alternative hires.txt in a subfolder is a variant the pack's author
    // offers, never read by Mesen).
    std::string root;
    bool have = false;
    for (const auto& file : files) {
      if (Basename(file) != "hires.txt") continue;
      const std::string prefix = file.substr(0, file.size() - 9);
      if (!have || Split(prefix).size() < Split(root).size() || (Split(prefix).size() == Split(root).size() && prefix < root)) {
        root = prefix;
        have = true;
      }
    }
    if (!have) { layout.problem = "missingHires"; return layout; }
    return finish(root, current);
  }
  if (engine == Engine::beetle) {
    // <content name>-texture-replacements: the folder holding the most texture
    // names directly (a dump or page-aligned folder is never installed).
    std::map<std::string, size_t> counts;
    for (const auto& file : files) {
      if (!BeetleTextureName(Basename(file))) continue;
      const std::string prefix = file.substr(0, file.size() - Basename(file).size());
      const auto parts = Split(prefix);
      const std::string last = parts.empty() ? "" : Lower(parts.back());
      auto endsWith = [&](const char* suffix) {
        const std::string s(suffix);
        return last.size() >= s.size() && last.compare(last.size() - s.size(), s.size(), s) == 0;
      };
      if (endsWith("-texture-dump") || endsWith("-texture-dump-pages") || endsWith("-texture-replacements-pages")) continue;
      counts[prefix]++;
    }
    std::string root;
    size_t best = 0;
    for (const auto& [prefix, count] : counts)
      if (count > best || (count == best && prefix.size() < root.size())) { root = prefix; best = count; }
    if (!best) { layout.problem = "noTextures"; return layout; }
    return finish(root, current);
  }
  // Azahar: load/textures/<16 hex program ID>/.
  std::string root;
  bool other = false;
  for (const auto& file : files) {
    const auto parts = Split(file);
    for (size_t i = 0; i + 1 < parts.size(); ++i) {
      const std::string id = UpperCase(parts[i]);
      if (!Matches(id, "^[0-9A-F]{16}$")) continue;
      found.insert(id);
      if (id != current) other = true;
      std::string prefix;
      for (size_t k = 0; k <= i; ++k) prefix += parts[k] + "/";
      if (root.empty() || prefix.size() < root.size()) root = prefix;
      break;
    }
  }
  if (root.empty()) {
    for (const auto& file : files)
      if (Lower(Basename(file)) == "pack.json") {
        const std::string prefix = file.substr(0, file.size() - Basename(file).size());
        if (root.empty() || prefix.size() < root.size()) root = prefix;
      }
  }
  layout.otherRegion = other;
  return finish(root, current);
}

// --- Folders --------------------------------------------------------------

inline bool Exists(const std::string& path) { struct stat st {}; return ::lstat(path.c_str(), &st) == 0; }
inline bool IsDirectory(const std::string& path) { struct stat st {}; return ::lstat(path.c_str(), &st) == 0 && S_ISDIR(st.st_mode); }

// `relative` must stay below root, through real directories only.
inline bool SafeBelow(const std::string& root, const std::string& relative) {
  if (relative.empty() || relative.front() == '/') return false;
  std::string path = root;
  for (const auto& part : Split(relative)) {
    if (part == "." || part == "..") return false;
    path += "/" + part;
    struct stat st {};
    if (::lstat(path.c_str(), &st) == 0 && S_ISLNK(st.st_mode)) return false;
  }
  return true;
}

inline bool MakeDirectories(const std::string& root, const std::string& relative) {
  std::string path = root;
  for (const auto& part : Split(relative)) {
    path += "/" + part;
    struct stat st {};
    if (::lstat(path.c_str(), &st) == 0) { if (!S_ISDIR(st.st_mode)) return false; continue; }
    if (::mkdir(path.c_str(), 0755) != 0 && errno != EEXIST) return false;
  }
  return true;
}

inline int RemoveEntry(const char* path, const struct stat*, int, struct FTW*) { return ::remove(path); }
// Deletes a tree without following links (a link is removed, never its target).
inline bool RemoveTree(const std::string& path) {
  if (!Exists(path)) return true;
  return ::nftw(path.c_str(), RemoveEntry, 32, FTW_DEPTH | FTW_PHYS) == 0 && !Exists(path);
}

inline std::string Token() {
  std::random_device device;
  std::mt19937_64 random(uint64_t(device()) << 32 ^ device());
  char buffer[17];
  std::snprintf(buffer, sizeof(buffer), "%016llx", static_cast<unsigned long long>(random()));
  return buffer;
}

// --- Staging --------------------------------------------------------------

struct Staged {
  std::string staging;              // <root>/.neostation-staging-<token>
  std::vector<std::string> folders; // staging/<i> for rule i (when used)
  std::vector<uint64_t> files, bytes;
  NeoTextureArchive::Status status = NeoTextureArchive::Status::ok;
  std::string problem;
};

struct Limits {
  uint64_t maxFiles = 400000;
  uint64_t maxBytes = 48ULL << 30;
};

// The staging prefix is this store's own; an engine with its own installer
// (ARMSX2) gets a folder under the prefix its leftover sweep removes.
inline constexpr const char* kStagingPrefix = ".neostation-staging-";

// flat: one rule whose files go directly into the staging folder (a folder
// handed to an engine's own installer).
inline Staged Begin(const std::string& root, size_t rules, const char* prefix = kStagingPrefix, bool flat = false) {
  Staged staged;
  if (!IsDirectory(root) || (flat && rules != 1)) return staged;
  staged.staging = root + "/" + prefix + Token();
  if (::mkdir(staged.staging.c_str(), 0755) != 0) { staged.staging.clear(); return staged; }
  for (size_t i = 0; i < rules; ++i) staged.folders.push_back(flat ? staged.staging : staged.staging + "/" + std::to_string(i));
  staged.files.assign(rules, 0);
  staged.bytes.assign(rules, 0);
  return staged;
}

// Destination for one archive entry, or "" when it is not installed.
inline std::string Destination(Engine engine, const std::vector<Rule>& rules, Staged& staged, const std::string& name,
                               uint64_t size, const Limits& limits) {
  std::string inside;
  const int rule = Map(rules, name, &inside);
  if (rule < 0 || inside.empty() || !Accepts(engine, inside)) return {};
  uint64_t files = 0, bytes = 0;
  for (size_t i = 0; i < staged.files.size(); ++i) { files += staged.files[i]; bytes += staged.bytes[i]; }
  if (files + 1 > limits.maxFiles || bytes + size > limits.maxBytes) { staged.problem = "tooLarge"; return {}; }
  const std::string folder = staged.folders[size_t(rule)];
  if (!IsDirectory(folder) && ::mkdir(folder.c_str(), 0755) != 0) return {};
  const std::string path = folder + "/" + inside;
  if (!NeoTextureArchive::MakeParents(folder, path)) return {};
  staged.files[size_t(rule)]++;
  staged.bytes[size_t(rule)] += size;
  return path;
}

inline Staged ExtractArchive(Engine engine, const std::string& root, const std::string& archive, const std::vector<Rule>& rules,
                             const NeoTextureArchive::Progress& progress, const Limits& limits = {},
                             const char* prefix = kStagingPrefix, bool flat = false) {
  Staged staged = Begin(root, rules.size(), prefix, flat);
  if (staged.staging.empty()) { staged.status = NeoTextureArchive::Status::io; return staged; }
  unsigned char magic[6] = {0};
  {
    NeoTextureArchive::File probe;
    if (!probe.open(archive) || !probe.read(0, magic, std::min<uint64_t>(6, probe.length()))) {
      staged.status = NeoTextureArchive::Status::io;
      return staged;
    }
  }
  std::set<std::string> written;  // case-folded destinations: no silent overwrite
  auto destination = [&](const NeoTextureArchive::Entry& entry) -> std::string {
    std::string path = Destination(engine, rules, staged, entry.name, entry.size, limits);
    if (path.empty()) return path;
    if (!written.insert(Lower(path)).second) { staged.problem = "duplicate"; return {}; }
    return path;
  };
  NeoTextureArchive::Limits archiveLimits;
  if (!std::memcmp(magic, "7z\xbc\xaf\x27\x1c", 6)) {
    NeoTextureArchive::SevenZip reader;
    staged.status = reader.open(archive, archiveLimits);
    if (staged.status == NeoTextureArchive::Status::ok) staged.status = reader.extractAll(destination, progress);
  } else if (magic[0] == 'P' && magic[1] == 'K') {
    NeoTextureArchive::Zip reader;
    staged.status = reader.open(archive, archiveLimits);
    if (staged.status == NeoTextureArchive::Status::ok) staged.status = reader.extractAll(destination, progress);
  } else {
    staged.status = NeoTextureArchive::Status::unsupported;
    staged.problem = !std::memcmp(magic, "Rar!", 4) ? "rar" : "format";
  }
  return staged;
}

// Copies a folder the user picked (regular files only; links are refused).
inline Staged CopyFolder(Engine engine, const std::string& root, const std::string& source, const std::vector<Rule>& rules,
                         const std::function<bool(uint64_t)>& progress, const Limits& limits = {}) {
  Staged staged = Begin(root, rules.size());
  if (staged.staging.empty()) { staged.status = NeoTextureArchive::Status::io; return staged; }
  std::error_code error;
  std::filesystem::recursive_directory_iterator walker(source, std::filesystem::directory_options::none, error), end;
  uint64_t visited = 0;
  for (; !error && walker != end; walker.increment(error)) {
    if (++visited > limits.maxFiles * 2) { staged.problem = "tooLarge"; staged.status = NeoTextureArchive::Status::limits; return staged; }
    const auto status = walker->symlink_status(error);
    if (error) break;
    if (std::filesystem::is_symlink(status)) { staged.status = NeoTextureArchive::Status::unsupported; staged.problem = "link"; return staged; }
    if (!std::filesystem::is_regular_file(status)) continue;
    const std::string relative = std::filesystem::relative(walker->path(), source, error).generic_string();
    if (error) break;
    const uint64_t size = walker->file_size(error);
    if (error) break;
    const std::string path = Destination(engine, rules, staged, relative, size, limits);
    if (!staged.problem.empty()) { staged.status = NeoTextureArchive::Status::limits; return staged; }
    if (path.empty()) continue;
    NeoTextureArchive::File in;
    NeoTextureArchive::Output out(path);
    if (!in.open(walker->path().string()) || !out.good()) { staged.status = NeoTextureArchive::Status::io; return staged; }
    std::vector<unsigned char> buffer(256 * 1024);
    for (uint64_t at = 0; at < in.length();) {
      const size_t n = size_t(std::min<uint64_t>(buffer.size(), in.length() - at));
      if (!in.read(at, buffer.data(), n) || !out.write(buffer.data(), n)) { staged.status = NeoTextureArchive::Status::io; return staged; }
      at += n;
      if (progress && !progress(n)) { staged.status = NeoTextureArchive::Status::cancelled; return staged; }
    }
    if (!out.commit()) { staged.status = NeoTextureArchive::Status::io; return staged; }
  }
  if (error) staged.status = NeoTextureArchive::Status::io;
  return staged;
}

// Every staged PNG/DDS starts with its signature.
inline std::string VerifySignatures(const Staged& staged) {
  for (const auto& folder : staged.folders) {
    if (!IsDirectory(folder)) continue;
    std::error_code error;
    for (std::filesystem::recursive_directory_iterator walker(folder, error), end; !error && walker != end; walker.increment(error))
      if (walker->is_regular_file(error) && !SignatureOK(walker->path().string())) return walker->path().filename().string();
  }
  return {};
}

// --- Swap -----------------------------------------------------------------

inline std::string JournalPath(const std::string& root) { return root + "/.neostation-swap.journal"; }

inline void WriteJournal(const std::string& root, const std::vector<std::pair<std::string, std::string>>& entries) {
  std::ofstream out(JournalPath(root) + ".tmp", std::ios::trunc);
  for (const auto& [target, backup] : entries) out << target << '\t' << backup << '\n';
  out.close();
  ::rename((JournalPath(root) + ".tmp").c_str(), JournalPath(root).c_str());
}

// After an interrupted swap: a target that is missing gets its previous
// folder back; otherwise the leftover previous folder is deleted. Leftover
// staging folders are always deleted.
inline void Recover(const std::string& root) {
  std::ifstream in(JournalPath(root));
  std::string line;
  while (std::getline(in, line)) {
    const size_t tab = line.find('\t');
    if (tab == std::string::npos) continue;
    const std::string target = line.substr(0, tab), backup = line.substr(tab + 1);
    if (target.rfind(root + "/", 0) != 0 || backup.rfind(root + "/.neostation-previous-", 0) != 0) continue;
    if (!Exists(target) && Exists(backup)) ::rename(backup.c_str(), target.c_str());
    else RemoveTree(backup);
  }
  in.close();
  ::unlink(JournalPath(root).c_str());
  if (DIR* dir = ::opendir(root.c_str())) {
    std::vector<std::string> stale;
    while (dirent* entry = ::readdir(dir)) {
      const std::string name = entry->d_name;
      if (name.rfind(".neostation-staging-", 0) == 0 || name.rfind(".neostation-previous-", 0) == 0) stale.push_back(root + "/" + name);
    }
    ::closedir(dir);
    for (const auto& path : stale) RemoveTree(path);
  }
}

// Moves staged folder i to root/targets[i]; a previous folder is kept aside
// until every move succeeded, and put back if one fails.
inline bool Commit(const std::string& root, const Staged& staged, const std::vector<std::string>& targets, std::string* problem) {
  std::vector<std::pair<std::string, std::string>> journal;
  std::vector<size_t> used;
  for (size_t i = 0; i < targets.size() && i < staged.folders.size(); ++i) {
    if (!IsDirectory(staged.folders[i])) continue;
    if (!SafeBelow(root, targets[i])) { if (problem) *problem = "unsafeTarget"; return false; }
    used.push_back(i);
    journal.push_back({root + "/" + targets[i], root + "/.neostation-previous-" + Token()});
  }
  if (used.empty()) { if (problem) *problem = "noTextures"; return false; }
  WriteJournal(root, journal);
  std::vector<size_t> moved, backedUp;
  bool ok = true;
  for (size_t k = 0; k < used.size() && ok; ++k) {
    const auto& [target, backup] = journal[k];
    const std::string parent = targets[used[k]].find('/') == std::string::npos ? "" : targets[used[k]].substr(0, targets[used[k]].rfind('/'));
    if (!parent.empty() && !MakeDirectories(root, parent)) { ok = false; break; }
    if (Exists(target)) {
      if (::rename(target.c_str(), backup.c_str()) != 0) { ok = false; break; }
      backedUp.push_back(k);
    }
    if (::rename(staged.folders[used[k]].c_str(), target.c_str()) != 0) { ok = false; break; }
    moved.push_back(k);
  }
  if (!ok) {
    for (auto it = moved.rbegin(); it != moved.rend(); ++it) ::rename(journal[*it].first.c_str(), staged.folders[used[*it]].c_str());
    for (size_t k : backedUp) ::rename(journal[k].second.c_str(), journal[k].first.c_str());
    ::unlink(JournalPath(root).c_str());
    if (problem) *problem = "writeFailed";
    return false;
  }
  for (size_t k : backedUp) RemoveTree(journal[k].second);
  ::unlink(JournalPath(root).c_str());
  RemoveTree(staged.staging);
  return true;
}

// Removes exactly root/relative (a pack folder) and then its parent when it
// became empty (PS2 <SERIAL>/ after <SERIAL>/replacements). Nothing else.
inline bool Remove(const std::string& root, const std::string& relative) {
  if (!SafeBelow(root, relative)) return false;
  const std::string path = root + "/" + relative;
  if (!IsDirectory(path)) return !Exists(path);
  if (!RemoveTree(path)) return false;
  const size_t slash = relative.rfind('/');
  if (slash != std::string::npos) ::rmdir((root + "/" + relative.substr(0, slash)).c_str());  // only when empty
  return true;
}

}  // namespace NeoTextureInstall
