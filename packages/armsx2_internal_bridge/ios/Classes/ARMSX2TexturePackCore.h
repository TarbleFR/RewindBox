// SPDX-License-Identifier: GPL-3.0-or-later
// HD texture packs of the embedded ARMSX2 engine (Build 485), host side.
//
// Reads, checks and installs replacement texture packs into
// <ARMSX2 data>/textures/<SERIAL>/replacements, the directory that the pinned
// engine scans (GSTextureReplacements::ReloadReplacementMap: EmuFolders::Textures,
// the disc serial, "replacements", recursively, by file name). Plain C++20 and
// zlib: it runs without ARMSX2Core, so the library can use it outside a JIT
// session, and its tests run on any host.
//
// Archive paths are mapped by the upstream TexturePackPaths::Classify and tar
// archives are read by TexturePackTar::Read (upstream/, byte-identical to ARMSX2
// 9d989ca9, pinned in build-utils/armsx2/upstream-files.json). The name and
// format rules below mirror the engine's loaders (GSTextureReplacements.cpp,
// GSTextureReplacementLoaders.cpp, GSTextureASTC.h, GSTextureKTX.h). They only
// describe files: whether a pack replaces anything in a game is known from the
// engine's indexed/loaded counts (ARMSX2Core ABI 8), never from an import.
#pragma once

#include "upstream/TexturePackPaths.h"
#include "upstream/TexturePackTar.h"

#include <zlib.h>

#include <algorithm>
#include <array>
#include <cctype>
#include <cinttypes>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <functional>
#include <map>
#include <memory>
#include <optional>
#include <regex>
#include <set>
#include <string>
#include <string_view>
#include <system_error>
#include <vector>
#include <sys/stat.h>

namespace NeoARMSX2Textures {
namespace fs = std::filesystem;

// ARMSX2/Android limits: more entries, or one larger file, is a malformed pack.
inline constexpr uint64_t kMaxEntries = 100000;
inline constexpr uint64_t kMaxFileBytes = 512ull * 1024 * 1024;
// Free space left on the device once the pack is written.
inline constexpr uint64_t kSpareBytes = 512ull * 1024 * 1024;
inline constexpr size_t kChunk = 256 * 1024;
inline constexpr const char* kReplacements = "replacements";
inline constexpr const char* kManifest = "NeoStation-texture-pack.json";
inline constexpr const char* kStagingPrefix = ".neostation-import-";
inline constexpr const char* kPreviousPrefix = ".neostation-previous-";
inline constexpr const char* kRemovingPrefix = ".neostation-removing-";
inline constexpr const char* kExpandedPrefix = ".neostation-expanded-";

inline std::string Upper(std::string_view text) {
  std::string out(text);
  for (char& c : out) c = static_cast<char>(std::toupper(static_cast<unsigned char>(c)));
  return out;
}

// ---------------------------------------------------------------------------
// Serials

// pcsx2/CDVD/CDVD.cpp ExecutablePathToSerial: "cdrom0:\SLUS_211.37;1" -> "SLUS-21137".
inline std::string ExecutablePathToSerial(const std::string& path) {
  std::string serial;
  auto pos = path.rfind('\\');
  if (pos != std::string::npos) serial = path.substr(pos + 1);
  else {
    pos = path.rfind(':');
    serial = pos != std::string::npos ? path.substr(pos + 1) : path;
  }
  pos = serial.rfind(';');
  if (pos != std::string::npos) serial.erase(pos);
  // WildcardMatch "????_???.??*" or "????-???.??*" (case-insensitive literals).
  if (!(serial.size() >= 11 && (serial[4] == '_' || serial[4] == '-') && serial[8] == '.')) serial.clear();
  for (std::string::size_type at = 0; at < serial.size();) {
    if (serial[at] == '.') { serial.erase(at, 1); continue; }
    serial[at] = serial[at] == '_' ? '-' : static_cast<char>(std::toupper(static_cast<unsigned char>(serial[at])));
    ++at;
  }
  return serial;
}

inline std::string_view Strip(std::string_view text) {
  while (!text.empty() && std::isspace(static_cast<unsigned char>(text.front()))) text.remove_prefix(1);
  while (!text.empty() && std::isspace(static_cast<unsigned char>(text.back()))) text.remove_suffix(1);
  return text;
}

struct DiscIdentity {
  std::string serial;   // as VMManager::GetDiscSerial() reports it
  std::string version;  // SYSTEM.CNF VER, the disc's software version
};

// GetPS2ElfName of the pinned engine: the last BOOT2 (PS2) or BOOT (PS1) wins.
inline DiscIdentity ParseSystemCnf(std::string_view text) {
  DiscIdentity identity;
  std::string elf;
  size_t start = 0;
  while (start <= text.size()) {
    const size_t end = text.find('\n', start);
    const std::string_view line = Strip(text.substr(start, end == std::string_view::npos ? std::string_view::npos : end - start));
    const size_t equals = line.find('=');
    if (equals != std::string_view::npos) {
      const std::string_view key = Strip(line.substr(0, equals)), value = Strip(line.substr(equals + 1));
      if (!value.empty()) {
        if (key == "BOOT2" || key == "BOOT") elf = std::string(value);
        else if (key == "VER") identity.version = std::string(value);
      }
    }
    if (end == std::string_view::npos) break;
    start = end + 1;
  }
  identity.serial = elf.empty() ? std::string() : ExecutablePathToSerial(elf);
  return identity;
}

// The only serials this store writes as a folder name: four letters or digits,
// a dash, five letters or digits. Anything else is never a path component.
inline bool IsStoreSerial(std::string_view serial) {
  if (serial.size() != 10 || serial[4] != '-') return false;
  for (size_t i = 0; i < serial.size(); ++i) {
    if (i == 4) continue;
    const unsigned char c = static_cast<unsigned char>(serial[i]);
    if (!(std::isdigit(c) || (c >= 'A' && c <= 'Z'))) return false;
  }
  return true;
}

// Region a PS2 serial prefix denotes. Unknown prefixes have no region: nothing
// is inferred from them.
inline std::string RegionOfSerial(std::string_view serial) {
  if (serial.size() < 4) return {};
  const std::string prefix = Upper(serial.substr(0, 4));
  static const std::map<std::string, std::string> table = {
      {"SLUS", "NTSC-U"}, {"SCUS", "NTSC-U"}, {"PBPX", "NTSC-J"},
      {"SLES", "PAL"},    {"SCES", "PAL"},    {"SCED", "PAL"},    {"SLED", "PAL"},
      {"SLPS", "NTSC-J"}, {"SLPM", "NTSC-J"}, {"SCPS", "NTSC-J"}, {"SCPM", "NTSC-J"},
      {"SLAJ", "NTSC-J"}, {"SCAJ", "NTSC-J"}, {"SLKA", "NTSC-K"}, {"SCKA", "NTSC-K"},
      {"SCCS", "NTSC-C"}};
  const auto it = table.find(prefix);
  return it == table.end() ? std::string() : it->second;
}

// ---------------------------------------------------------------------------
// ISO 9660 identity (plain 2048-byte images and raw 2352-byte CD images).
// Compressed containers (CHD, CSO, GZ, ...) are never decoded here.

inline std::optional<DiscIdentity> ReadDiscIdentity(const fs::path& path) {
  std::unique_ptr<std::FILE, int (*)(std::FILE*)> file(std::fopen(path.c_str(), "rb"), std::fclose);
  if (!file) return std::nullopt;
  struct Layout { uint64_t sector, offset; };
  for (const Layout layout : {Layout{2048, 0}, Layout{2352, 16}, Layout{2352, 24}}) {
    const auto readSectors = [&](uint64_t lba, uint64_t bytes, std::vector<unsigned char>& out) {
      out.clear();
      while (out.size() < bytes) {
        unsigned char sector[2048];
        if (fseeko(file.get(), static_cast<off_t>(lba * layout.sector + layout.offset), SEEK_SET) != 0 ||
            std::fread(sector, 1, sizeof(sector), file.get()) != sizeof(sector))
          return false;
        out.insert(out.end(), sector, sector + std::min<uint64_t>(2048, bytes - out.size()));
        ++lba;
      }
      return true;
    };
    std::vector<unsigned char> pvd;
    if (!readSectors(16, 2048, pvd) || pvd[0] != 1 || std::memcmp(pvd.data() + 1, "CD001", 5) != 0 || pvd[6] != 1)
      continue;
    const auto le32 = [](const unsigned char* p) {
      return static_cast<uint32_t>(p[0]) | (static_cast<uint32_t>(p[1]) << 8) |
             (static_cast<uint32_t>(p[2]) << 16) | (static_cast<uint32_t>(p[3]) << 24);
    };
    const uint32_t rootLba = le32(pvd.data() + 156 + 2), rootSize = le32(pvd.data() + 156 + 10);
    if (rootSize == 0) continue;
    std::vector<unsigned char> directory;
    if (!readSectors(rootLba, std::min<uint64_t>(rootSize, 64 * 2048), directory)) continue;
    for (size_t at = 0; at < directory.size();) {
      const unsigned length = directory[at];
      if (length == 0) { at = (at / 2048 + 1) * 2048; continue; }  // records never cross a sector
      if (length < 34 || at + length > directory.size()) break;
      const unsigned nameLength = directory[at + 32];
      if (33 + nameLength <= length) {
        const std::string name = Upper(std::string_view(reinterpret_cast<const char*>(directory.data() + at + 33), nameLength));
        if (name == "SYSTEM.CNF;1" || name == "SYSTEM.CNF") {
          std::vector<unsigned char> cnf;
          if (!readSectors(le32(directory.data() + at + 2), std::min<uint32_t>(le32(directory.data() + at + 10), 4096), cnf))
            return std::nullopt;
          DiscIdentity identity = ParseSystemCnf(std::string_view(reinterpret_cast<const char*>(cnf.data()), cnf.size()));
          if (identity.serial.empty()) return std::nullopt;
          return identity;
        }
      }
      at += length;
    }
    return std::nullopt;  // a valid volume without SYSTEM.CNF is not a game disc
  }
  return std::nullopt;
}

// ---------------------------------------------------------------------------
// Hints a pack's own names give. They are reported, never trusted: a name
// cannot prove compatibility.

struct NameHints {
  std::set<std::string> regions;   // NTSC-U, PAL, NTSC-J, NTSC-K
  std::set<std::string> versions;  // "1.01", "Rev 1", "Greatest Hits", ...
  std::set<std::string> crcs;      // explicit "CRC XXXXXXXX" or "[XXXXXXXX]" mentions
};

inline void CollectHints(std::string_view text, NameHints& hints) {
  const std::string lower = [&] {
    std::string out(text);
    for (char& c : out) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    return out;
  }();
  static const std::regex word("[a-z0-9]+");
  static const std::map<std::string, std::string> regions = {
      {"usa", "NTSC-U"}, {"us", "NTSC-U"}, {"ntscu", "NTSC-U"},
      {"europe", "PAL"}, {"eur", "PAL"}, {"pal", "PAL"},
      {"japan", "NTSC-J"}, {"jpn", "NTSC-J"}, {"jp", "NTSC-J"}, {"ntscj", "NTSC-J"},
      {"korea", "NTSC-K"}, {"kor", "NTSC-K"}, {"ntsck", "NTSC-K"}};
  for (auto it = std::sregex_iterator(lower.begin(), lower.end(), word); it != std::sregex_iterator(); ++it) {
    const auto region = regions.find(it->str());
    if (region != regions.end()) hints.regions.insert(region->second);
  }
  static const std::regex ntsc("ntsc[ _-]([ujk])(?![a-z0-9])");
  for (auto it = std::sregex_iterator(lower.begin(), lower.end(), ntsc); it != std::sregex_iterator(); ++it)
    hints.regions.insert(std::string("NTSC-") + static_cast<char>(std::toupper(static_cast<unsigned char>((*it)[1].str()[0]))));
  static const std::regex version("(?:^|[^a-z0-9])v(?:er(?:sion)?)?[ ._-]?([0-9]{1,2}\\.[0-9]{1,2})(?![0-9])");
  static const std::regex revision("(?:^|[^a-z0-9])rev(?:ision)?[ ._-]?([0-9a-z])(?![a-z0-9])");
  for (auto it = std::sregex_iterator(lower.begin(), lower.end(), version); it != std::sregex_iterator(); ++it)
    hints.versions.insert((*it)[1].str());
  for (auto it = std::sregex_iterator(lower.begin(), lower.end(), revision); it != std::sregex_iterator(); ++it)
    hints.versions.insert("Rev " + Upper((*it)[1].str()));
  for (const char* edition : {"greatest hits", "platinum", "the best"})
    if (lower.find(edition) != std::string::npos) hints.versions.insert(edition);
  static const std::regex crc("crc[ ._:-]?([0-9a-f]{8})(?![0-9a-f])|[\\[(]([0-9a-f]{8})[\\])]");
  for (auto it = std::sregex_iterator(lower.begin(), lower.end(), crc); it != std::sregex_iterator(); ++it)
    hints.crcs.insert(Upper((*it)[1].matched ? (*it)[1].str() : (*it)[2].str()));
}

// ---------------------------------------------------------------------------
// Replacement file names and formats of the pinned loaders.

// GetLoader: exact, case-insensitive extension.
inline bool HasLoaderExtension(std::string_view name) {
  const size_t dot = name.rfind('.');
  if (dot == std::string_view::npos) return false;
  std::string ext(name.substr(dot + 1));
  for (char& c : ext) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
  return ext == "png" || ext == "dds" || ext == "astc" || ext == "ktx";
}

// ParseReplacementName: the six sscanf patterns, in the engine's order.
inline bool IsReplacementName(const std::string& filename) {
  if (!HasLoaderExtension(filename)) return false;
  uint64_t tex = 0, clut = 0, region = 0;
  unsigned width = 0, height = 0, bits = 0;
  char dot = 0;
  const char* name = filename.c_str();
  if (std::sscanf(name, "%" SCNx64 "-%" SCNx64 "-r%ux%u-%08x%c", &tex, &clut, &width, &height, &bits, &dot) == 6 && dot == '.') return true;
  if (std::sscanf(name, "%" SCNx64 "-r%ux%u-%08x%c", &tex, &width, &height, &bits, &dot) == 5 && dot == '.') return true;
  if (std::sscanf(name, "%" SCNx64 "-%" SCNx64 "-r%" SCNx64 "-%08x%c", &tex, &clut, &region, &bits, &dot) == 5 && dot == '.') return true;
  if (std::sscanf(name, "%" SCNx64 "-r%" SCNx64 "-%08x%c", &tex, &region, &bits, &dot) == 4 && dot == '.') return true;
  if (std::sscanf(name, "%" SCNx64 "-%" SCNx64 "-%08x%c", &tex, &clut, &bits, &dot) == 4 && dot == '.') return true;
  if (std::sscanf(name, "%" SCNx64 "-%08x%c", &tex, &bits, &dot) == 3 && dot == '.') return true;
  return false;
}

// "<name>-mip<N>.<ext>": an explicit mip level the loader reads next to its base.
inline bool IsMipName(const std::string& filename) {
  static const std::regex mip(".+-mip[0-9]+\\.(png|dds|astc|ktx)", std::regex::icase);
  return std::regex_match(filename, mip);
}

enum class Format { Png, DdsRgba, DdsBc1, DdsBc2, DdsBc3, DdsBc7, Astc, Ktx, Unsupported };
inline constexpr size_t kHeadBytes = 148;  // DDS magic + header + DX10 header

inline const char* FormatKey(Format format) {
  switch (format) {
    case Format::Png: return "png";
    case Format::DdsRgba: return "ddsRgba";
    case Format::DdsBc1: return "ddsBc1";
    case Format::DdsBc2: return "ddsBc2";
    case Format::DdsBc3: return "ddsBc3";
    case Format::DdsBc7: return "ddsBc7";
    case Format::Astc: return "astc";
    case Format::Ktx: return "ktx";
    case Format::Unsupported: return "unsupported";
  }
  return "unsupported";
}

inline bool IsBlockCompressed(Format format) {
  return format == Format::DdsBc1 || format == Format::DdsBc2 || format == Format::DdsBc3 || format == Format::DdsBc7;
}

inline uint32_t Le32(const unsigned char* p) {
  return static_cast<uint32_t>(p[0]) | (static_cast<uint32_t>(p[1]) << 8) |
         (static_cast<uint32_t>(p[2]) << 16) | (static_cast<uint32_t>(p[3]) << 24);
}
inline uint16_t Le16(const unsigned char* p) {
  return static_cast<uint16_t>(p[0] | (p[1] << 8));
}
inline uint64_t Le64(const unsigned char* p) {
  return static_cast<uint64_t>(Le32(p)) | (static_cast<uint64_t>(Le32(p + 4)) << 32);
}

// What the pinned loaders accept, from the file head. PNG decoding, DDS mip
// chains and the KTX key/value data are checked by the engine when it loads.
inline Format SniffFormat(const unsigned char* head, size_t length, uint64_t fileSize, std::string_view filename) {
  const size_t dot = filename.rfind('.');
  std::string ext = dot == std::string_view::npos ? std::string() : std::string(filename.substr(dot + 1));
  for (char& c : ext) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
  if (ext == "png") {
    static const unsigned char signature[8] = {137, 80, 78, 71, 13, 10, 26, 10};
    return length >= 8 && std::memcmp(head, signature, 8) == 0 ? Format::Png : Format::Unsupported;
  }
  if (ext == "dds") {
    if (length < 128 || std::memcmp(head, "DDS ", 4) != 0) return Format::Unsupported;
    const unsigned char* h = head + 4;
    const uint32_t size = Le32(h), flags = Le32(h + 4), height = Le32(h + 8), width = Le32(h + 12);
    if (size < 124 || width == 0 || width >= 32768 || height == 0 || height >= 32768 || (flags & 0x00800000))
      return Format::Unsupported;
    const unsigned char* pf = h + 72;
    const uint32_t pfSize = Le32(pf), pfFlags = Le32(pf + 4), fourcc = Le32(pf + 8), bits = Le32(pf + 12);
    const uint32_t r = Le32(pf + 16), g = Le32(pf + 20), b = Le32(pf + 24), a = Le32(pf + 28);
    const auto four = [](const char* s) { return Le32(reinterpret_cast<const unsigned char*>(s)); };
    if (pfFlags & 0x4) {
      uint32_t dxgi = 0;
      if (fourcc == four("DX10")) {
        if (length < kHeadBytes) return Format::Unsupported;
        dxgi = Le32(head + 128);
        if (Le32(head + 132) != 3 || Le32(head + 140) != 1) return Format::Unsupported;
      }
      if (fourcc == four("DXT1") || dxgi == 71) return Format::DdsBc1;
      if (fourcc == four("DXT2") || fourcc == four("DXT3") || dxgi == 74) return Format::DdsBc2;
      if (fourcc == four("DXT4") || fourcc == four("DXT5") || dxgi == 77) return Format::DdsBc3;
      if (dxgi == 98) return Format::DdsBc7;
      return Format::Unsupported;
    }
    struct Pixel { uint32_t flags, bits, r, g, b, a; };
    static constexpr Pixel accepted[] = {
        {0x41, 32, 0x00ff0000, 0x0000ff00, 0x000000ff, 0xff000000},  // A8R8G8B8
        {0x40, 32, 0x00ff0000, 0x0000ff00, 0x000000ff, 0x00000000},  // X8R8G8B8
        {0x40, 32, 0x000000ff, 0x0000ff00, 0x00ff0000, 0x00000000},  // X8B8G8R8
        {0x40, 24, 0x00ff0000, 0x0000ff00, 0x000000ff, 0x00000000},  // R8G8B8
        {0x41, 32, 0x000000ff, 0x0000ff00, 0x00ff0000, 0xff000000}}; // A8B8G8R8
    for (const Pixel& p : accepted)
      if (pfSize == 32 && pfFlags == p.flags && fourcc == 0 && bits == p.bits && r == p.r && g == p.g && b == p.b && a == p.a)
        return Format::DdsRgba;
    return Format::Unsupported;
  }
  if (ext == "astc") {
    static const unsigned char magic[4] = {0x13, 0xAB, 0xA1, 0x5C};
    if (length < 16 || std::memcmp(head, magic, 4) != 0) return Format::Unsupported;
    const uint32_t bw = head[4], bh = head[5], bd = head[6];
    const uint32_t width = head[7] | (head[8] << 8) | (head[9] << 16);
    const uint32_t height = head[10] | (head[11] << 8) | (head[12] << 16);
    const uint32_t depth = head[13] | (head[14] << 8) | (head[15] << 16);
    static const std::set<uint32_t> footprints = {0x404, 0x504, 0x505, 0x605, 0x606, 0x805, 0x806, 0x808,
                                                  0xA05, 0xA06, 0xA08, 0xA0A, 0xC0A, 0xC0C};
    if (bd != 1 || depth != 1 || !footprints.count((bw << 8) | bh) || width == 0 || height == 0) return Format::Unsupported;
    const uint64_t payload = static_cast<uint64_t>((width + bw - 1) / bw) * ((height + bh - 1) / bh) * 16ull;
    return fileSize == 16 + payload ? Format::Astc : Format::Unsupported;
  }
  if (ext == "ktx") {
    static const unsigned char identifier[12] = {0xAB, 'K', 'T', 'X', ' ', '1', '1', 0xBB, '\r', '\n', 0x1A, '\n'};
    if (length < 64 || std::memcmp(head, identifier, 12) != 0 || Le32(head + 12) != 0x04030201) return Format::Unsupported;
    const uint32_t internal = Le32(head + 28);
    const uint32_t width = Le32(head + 36), height = Le32(head + 40), mips = Le32(head + 56);
    uint32_t chain = 1;
    for (uint32_t w = width, h = height; w > 1 || h > 1; ++chain) { w = std::max(1u, w >> 1); h = std::max(1u, h >> 1); }
    if (Le32(head + 16) != 0 || Le32(head + 20) != 1 || Le32(head + 24) != 0 || Le32(head + 32) != 0x1908 ||
        internal < 0x93B0 || internal > 0x93BD || Le32(head + 44) != 0 || Le32(head + 48) != 0 || Le32(head + 52) != 1 ||
        width == 0 || height == 0 || mips == 0 || mips > chain || mips > 7 || Le32(head + 60) > 1024 * 1024)
      return Format::Unsupported;
    return Format::Ktx;
  }
  return Format::Unsupported;
}

// ---------------------------------------------------------------------------
// Pack plans

struct Entry {
  std::string name;      // path inside the source, '/' separated (a chosen folder's own name first)
  uint64_t size = 0;
  uint64_t index = 0;    // reader-specific locator
  std::string location;  // folders: path relative to the folder, to read the file
};

struct Selected {
  size_t entry = 0;
  std::string destination;  // relative to <SERIAL>/replacements, from TexturePackPaths::Classify
};

struct Plan {
  std::vector<Selected> files;
  uint64_t bytes = 0;
  std::set<std::string> packSerials;  // serial folders found in the pack
  std::string chosenSerial;           // serial folder whose files were selected ("" = bare files)
  std::string nameSerial;             // serial written in the archive or folder name
  uint64_t skipped = 0;               // entries that are not textures (readme, thumbnails, ...)
  uint64_t excluded = 0;              // textures of another serial folder, not installed
  NameHints hints;
  std::string error;                  // "", "entries", "unsafe", "multipleSerials", "fileTooLarge", "duplicate", "noTextures"
  std::string detail;
};

inline std::string Normalized(std::optional<std::string> serial) { return serial ? *serial : std::string(); }

inline Plan BuildPlan(const std::vector<Entry>& entries, std::string_view sourceName, std::string_view gameSerial) {
  Plan plan;
  if (entries.size() > kMaxEntries) { plan.error = "entries"; return plan; }
  std::map<std::string, std::vector<std::pair<size_t, std::string>>> groups;
  std::set<std::string> directories;
  for (size_t i = 0; i < entries.size(); ++i) {
    const std::string& name = entries[i].name;
    const TexturePackPaths::Entry mapped = TexturePackPaths::Classify(name);
    if (mapped.kind == TexturePackPaths::Kind::Unsafe) { plan.error = "unsafe"; plan.detail = name; return plan; }
    const size_t slash = name.find_last_of("/\\");
    if (slash != std::string::npos) directories.insert(name.substr(0, slash));
    if (mapped.kind != TexturePackPaths::Kind::Texture) { ++plan.skipped; continue; }
    const std::string serial = Normalized(TexturePackPaths::SerialFolderIn(name));
    if (!serial.empty()) plan.packSerials.insert(serial);
    groups[serial].emplace_back(i, mapped.path);
  }
  plan.nameSerial = Normalized(TexturePackPaths::FindSerial(std::string(sourceName)));
  CollectHints(sourceName, plan.hints);
  for (const std::string& directory : directories) CollectHints(directory, plan.hints);

  const std::string game(gameSerial);
  if (!game.empty() && groups.count(game)) plan.chosenSerial = game;
  else if (plan.packSerials.size() == 1) plan.chosenSerial = *plan.packSerials.begin();
  else if (plan.packSerials.size() > 1) {
    plan.error = "multipleSerials";
    for (const std::string& serial : plan.packSerials) plan.detail += (plan.detail.empty() ? "" : ", ") + serial;
    return plan;
  }
  std::set<std::string> destinations;
  for (const auto& [serial, files] : groups) {
    if (serial != plan.chosenSerial) { plan.excluded += files.size(); continue; }
    for (const auto& [index, destination] : files) {
      if (entries[index].size > kMaxFileBytes) { plan.error = "fileTooLarge"; plan.detail = entries[index].name; return plan; }
      if (!destinations.insert(TexturePackPaths::Lower(destination)).second) {
        plan.error = "duplicate"; plan.detail = destination; return plan;
      }
      plan.files.push_back({index, destination});
      plan.bytes += entries[index].size;
    }
  }
  if (plan.files.empty()) plan.error = "noTextures";
  return plan;
}

// How the pack relates to the game it is imported for. Only "same" installs
// without a question; every other verdict is explained and confirmed first,
// and an unknown game serial is refused (nothing to associate the pack with).
struct Verdict {
  std::string match;          // "same", "otherSerial", "noSerial", "gameUnknown"
  std::string packSerial;     // serial the pack names, when one does
  bool regionConflict = false;  // the pack's names cite a region other than the game's
};

inline Verdict Judge(const Plan& plan, std::string_view gameSerial) {
  Verdict verdict;
  verdict.packSerial = !plan.chosenSerial.empty() ? plan.chosenSerial : plan.nameSerial;
  if (gameSerial.empty()) { verdict.match = "gameUnknown"; return verdict; }
  if (verdict.packSerial.empty()) verdict.match = "noSerial";
  else verdict.match = verdict.packSerial == gameSerial ? "same" : "otherSerial";
  const std::string region = RegionOfSerial(gameSerial);
  if (!region.empty())
    for (const std::string& hinted : plan.hints.regions)
      if (hinted != region) verdict.regionConflict = true;
  return verdict;
}

// ---------------------------------------------------------------------------
// Folder sources

// Lists regular files below [root]. With [prefixRoot] the entry names start with
// the folder's own name, so a chosen folder named after a serial counts as a
// serial folder. A symbolic link anywhere is an unsafe pack (nothing outside the
// chosen folder is read).
inline bool ListFolder(const fs::path& root, std::vector<Entry>& entries, std::string& error, bool prefixRoot = true) {
  entries.clear();
  std::error_code code;
  if (fs::is_symlink(fs::symlink_status(root, code)) || !fs::is_directory(root, code)) { error = "unreadable"; return false; }
  const std::string base = root.filename().string();
  fs::recursive_directory_iterator it(root, fs::directory_options::none, code), end;
  if (code) { error = "unreadable"; return false; }
  for (; it != end; it.increment(code)) {
    if (code) { error = "unreadable"; return false; }
    const fs::file_status status = it->symlink_status(code);
    if (code) { error = "unreadable"; return false; }
    if (fs::is_symlink(status)) { error = "unsafe"; return false; }
    if (!fs::is_regular_file(status)) continue;
    if (entries.size() >= kMaxEntries) { error = "entries"; return false; }
    const std::string relative = fs::relative(it->path(), root, code).generic_string();
    if (code) { error = "unreadable"; return false; }
    entries.push_back({prefixRoot ? base + "/" + relative : relative, it->file_size(code), entries.size(), relative});
    if (code) { error = "unreadable"; return false; }
  }
  return true;
}

// ---------------------------------------------------------------------------
// ZIP sources: Store and Deflate, ZIP64, no encryption, no links.

struct ZipEntry {
  std::string name;
  uint64_t compressed = 0, size = 0, local = 0;
  uint32_t crc = 0;
  uint16_t method = 0, flags = 0;
};

inline std::string Cp437ToUtf8(std::string_view raw) {
  static const char16_t high[128] = {
      0x00C7, 0x00FC, 0x00E9, 0x00E2, 0x00E4, 0x00E0, 0x00E5, 0x00E7, 0x00EA, 0x00EB, 0x00E8, 0x00EF, 0x00EE, 0x00EC, 0x00C4, 0x00C5,
      0x00C9, 0x00E6, 0x00C6, 0x00F4, 0x00F6, 0x00F2, 0x00FB, 0x00F9, 0x00FF, 0x00D6, 0x00DC, 0x00A2, 0x00A3, 0x00A5, 0x20A7, 0x0192,
      0x00E1, 0x00ED, 0x00F3, 0x00FA, 0x00F1, 0x00D1, 0x00AA, 0x00BA, 0x00BF, 0x2310, 0x00AC, 0x00BD, 0x00BC, 0x00A1, 0x00AB, 0x00BB,
      0x2591, 0x2592, 0x2593, 0x2502, 0x2524, 0x2561, 0x2562, 0x2556, 0x2555, 0x2563, 0x2551, 0x2557, 0x255D, 0x255C, 0x255B, 0x2510,
      0x2514, 0x2534, 0x252C, 0x251C, 0x2500, 0x253C, 0x255E, 0x255F, 0x255A, 0x2554, 0x2569, 0x2566, 0x2560, 0x2550, 0x256C, 0x2567,
      0x2568, 0x2564, 0x2565, 0x2559, 0x2558, 0x2552, 0x2553, 0x256B, 0x256A, 0x2518, 0x250C, 0x2588, 0x2584, 0x258C, 0x2590, 0x2580,
      0x03B1, 0x00DF, 0x0393, 0x03C0, 0x03A3, 0x03C3, 0x00B5, 0x03C4, 0x03A6, 0x0398, 0x03A9, 0x03B4, 0x221E, 0x03C6, 0x03B5, 0x2229,
      0x2261, 0x00B1, 0x2265, 0x2264, 0x2320, 0x2321, 0x00F7, 0x2248, 0x00B0, 0x2219, 0x00B7, 0x221A, 0x207F, 0x00B2, 0x25A0, 0x00A0};
  std::string out;
  for (const unsigned char c : raw) {
    if (c < 0x80) { out += static_cast<char>(c); continue; }
    const char16_t u = high[c - 0x80];
    if (u < 0x800) { out += static_cast<char>(0xC0 | (u >> 6)); out += static_cast<char>(0x80 | (u & 0x3F)); }
    else { out += static_cast<char>(0xE0 | (u >> 12)); out += static_cast<char>(0x80 | ((u >> 6) & 0x3F)); out += static_cast<char>(0x80 | (u & 0x3F)); }
  }
  return out;
}

inline bool ValidUtf8(std::string_view text) {
  for (size_t i = 0; i < text.size();) {
    const unsigned char c = static_cast<unsigned char>(text[i]);
    const size_t n = c < 0x80 ? 1 : (c >> 5) == 0x6 ? 2 : (c >> 4) == 0xE ? 3 : (c >> 3) == 0x1E ? 4 : 0;
    if (!n || i + n > text.size()) return false;
    for (size_t k = 1; k < n; ++k) if ((static_cast<unsigned char>(text[i + k]) & 0xC0) != 0x80) return false;
    i += n;
  }
  return true;
}

inline bool ReadAt(std::FILE* file, uint64_t offset, void* bytes, size_t count) {
  return fseeko(file, static_cast<off_t>(offset), SEEK_SET) == 0 && std::fread(bytes, 1, count, file) == count;
}

// error: "invalid", "split", "encrypted", "method:<n>", "entries".
inline bool ListZip(std::FILE* file, std::vector<ZipEntry>& entries, std::string& error) {
  entries.clear();
  if (fseeko(file, 0, SEEK_END) != 0) { error = "invalid"; return false; }
  const uint64_t length = static_cast<uint64_t>(ftello(file));
  if (length < 22) { error = "invalid"; return false; }
  const size_t tailSize = static_cast<size_t>(std::min<uint64_t>(length, 65557));
  std::vector<unsigned char> tail(tailSize);
  if (!ReadAt(file, length - tailSize, tail.data(), tailSize)) { error = "invalid"; return false; }
  size_t eocd = tailSize;
  for (size_t i = tailSize - 22;; --i) {
    if (Le32(tail.data() + i) == 0x06054b50 && i + 22 + Le16(tail.data() + i + 20) <= tailSize) { eocd = i; break; }
    if (i == 0) break;
  }
  if (eocd == tailSize) { error = "invalid"; return false; }
  const unsigned char* e = tail.data() + eocd;
  uint64_t disk = Le16(e + 4), cdDisk = Le16(e + 6), count = Le16(e + 10), total = Le16(e + 8);
  uint64_t cdSize = Le32(e + 12), cdOffset = Le32(e + 16);
  const uint64_t eocdOffset = length - tailSize + eocd;
  if (count == 0xFFFF || total == 0xFFFF || cdSize == 0xFFFFFFFF || cdOffset == 0xFFFFFFFF) {
    unsigned char locator[20], record[56];
    if (eocdOffset < 20 || !ReadAt(file, eocdOffset - 20, locator, 20) || Le32(locator) != 0x07064b50) { error = "invalid"; return false; }
    const uint64_t at = Le64(locator + 8);
    if (Le32(locator + 4) != 0 || Le32(locator + 16) > 1 || !ReadAt(file, at, record, 56) || Le32(record) != 0x06064b50) {
      error = Le32(locator + 16) > 1 ? "split" : "invalid"; return false;
    }
    disk = Le32(record + 16); cdDisk = Le32(record + 20);
    total = Le64(record + 24); count = Le64(record + 32); cdSize = Le64(record + 40); cdOffset = Le64(record + 48);
  }
  if (disk != 0 || cdDisk != 0 || total != count) { error = "split"; return false; }
  if (count > kMaxEntries) { error = "entries"; return false; }
  // The directory precedes its end record; 100000 entries never need 128 MiB of
  // it, so a forged size cannot become a huge allocation.
  if (cdOffset > eocdOffset || cdSize > eocdOffset - cdOffset || cdSize > (128ull << 20)) { error = "invalid"; return false; }
  std::vector<unsigned char> directory(static_cast<size_t>(cdSize));
  if (cdSize && !ReadAt(file, cdOffset, directory.data(), directory.size())) { error = "invalid"; return false; }
  size_t at = 0;
  for (uint64_t i = 0; i < count; ++i) {
    if (at + 46 > directory.size() || Le32(directory.data() + at) != 0x02014b50) { error = "invalid"; return false; }
    const unsigned char* h = directory.data() + at;
    const uint16_t nameSize = Le16(h + 28), extraSize = Le16(h + 30), commentSize = Le16(h + 32);
    if (at + 46 + nameSize + extraSize + commentSize > directory.size()) { error = "invalid"; return false; }
    ZipEntry entry;
    const std::string_view raw(reinterpret_cast<const char*>(h + 46), nameSize);
    entry.name = (Le16(h + 8) & 0x800) || ValidUtf8(raw) ? std::string(raw) : Cp437ToUtf8(raw);
    entry.flags = Le16(h + 8); entry.method = Le16(h + 10); entry.crc = Le32(h + 16);
    entry.compressed = Le32(h + 20); entry.size = Le32(h + 24); entry.local = Le32(h + 42);
    uint32_t entryDisk = Le16(h + 34);
    for (size_t x = 0; x + 4 <= extraSize;) {
      const unsigned char* field = h + 46 + nameSize + x;
      const uint16_t id = Le16(field), size = Le16(field + 2);
      if (x + 4 + size > extraSize) { error = "invalid"; return false; }
      if (id == 0x0001) {
        size_t f = 4;
        const auto take64 = [&](uint64_t& value) {
          if (f + 8 > 4u + size) return false;
          value = Le64(field + f); f += 8; return true;
        };
        if ((entry.size == 0xFFFFFFFF && !take64(entry.size)) ||
            (entry.compressed == 0xFFFFFFFF && !take64(entry.compressed)) ||
            (entry.local == 0xFFFFFFFF && !take64(entry.local))) { error = "invalid"; return false; }
        if (entryDisk == 0xFFFF) { if (f + 4 > 4u + size) { error = "invalid"; return false; } entryDisk = Le32(field + f); }
      }
      x += 4 + size;
    }
    if (entryDisk != 0) { error = "split"; return false; }
    const uint32_t external = Le32(h + 38);
    if ((Le16(h + 4) >> 8) == 3 && ((external >> 16) & S_IFMT) == S_IFLNK) {
      error = "unsafe"; entries.clear(); entries.push_back(entry); return false;
    }
    at += 46 + nameSize + extraSize + commentSize;
    const bool directoryEntry = !entry.name.empty() && (entry.name.back() == '/' || entry.name.back() == '\\');
    if (!directoryEntry && (entry.flags & 0x1)) { error = "encrypted"; return false; }
    entries.push_back(std::move(entry));
  }
  return true;
}

inline std::string MethodError(uint16_t method) { return "method:" + std::to_string(method); }

// Streams one entry into [output], checking its size and CRC-32. [tick] receives
// the produced byte count and returns false to cancel.
inline bool ExtractZipEntry(std::FILE* file, const ZipEntry& entry, std::FILE* output,
                            const std::function<bool(uint64_t)>& tick, std::string& error) {
  if (entry.method != 0 && entry.method != 8) { error = MethodError(entry.method); return false; }
  unsigned char local[30];
  if (!ReadAt(file, entry.local, local, 30) || Le32(local) != 0x04034b50) { error = "invalid"; return false; }
  uint64_t at = entry.local + 30 + Le16(local + 26) + Le16(local + 28);
  std::vector<unsigned char> input(kChunk), decoded(kChunk);
  uLong crc = crc32(0, nullptr, 0);
  uint64_t produced = 0, remaining = entry.compressed;
  z_stream stream{};
  const bool deflated = entry.method == 8;
  if (deflated && inflateInit2(&stream, -MAX_WBITS) != Z_OK) { error = "invalid"; return false; }
  bool ok = true, ended = !deflated;
  const auto emit = [&](const unsigned char* bytes, size_t count) {
    produced += count;
    // More bytes than the directory announced: a damaged archive; a short write: the disk.
    if (produced > entry.size) { error = "invalid"; return false; }
    if (std::fwrite(bytes, 1, count, output) != count) { error = "write"; return false; }
    crc = crc32(crc, bytes, static_cast<uInt>(count));
    return true;
  };
  while (ok && remaining) {
    const size_t n = static_cast<size_t>(std::min<uint64_t>(remaining, input.size()));
    if (!ReadAt(file, at, input.data(), n)) { error = "invalid"; ok = false; break; }
    at += n; remaining -= n;
    if (!deflated) { if (!emit(input.data(), n)) ok = false; }
    else {
      if (ended) { error = "invalid"; ok = false; break; }  // bytes after the deflate stream
      stream.next_in = input.data(); stream.avail_in = static_cast<uInt>(n);
      do {
        stream.next_out = decoded.data(); stream.avail_out = static_cast<uInt>(decoded.size());
        const int status = inflate(&stream, Z_NO_FLUSH);
        // No input left and nothing produced: the next chunk is needed.
        if (status == Z_BUF_ERROR && !stream.avail_in && stream.avail_out == decoded.size()) break;
        if (status != Z_OK && status != Z_STREAM_END) { error = "invalid"; ok = false; break; }
        if (!emit(decoded.data(), decoded.size() - stream.avail_out)) { ok = false; break; }
        if (status == Z_STREAM_END) {
          ended = true;
          if (stream.avail_in) { error = "invalid"; ok = false; }
          break;
        }
      } while (stream.avail_in || stream.avail_out == 0);
    }
    if (ok && tick && !tick(produced)) { error = "cancelled"; ok = false; }
  }
  if (deflated) inflateEnd(&stream);
  if (ok && (!ended || produced != entry.size || crc != entry.crc)) { error = "invalid"; ok = false; }
  return ok;
}

// ---------------------------------------------------------------------------
// TAR sources (the upstream reader: regular files, folders, GNU long names).

inline bool ListTar(std::FILE* file, std::vector<Entry>& entries, std::string& error) {
  entries.clear();
  std::rewind(file);
  const auto read = [file](void* buffer, size_t n) { return std::fread(buffer, 1, n, file) == n; };
  std::string reason;
  const bool ok = TexturePackTar::Read(read, [&](const std::string& name, uint64_t size) {
    if (entries.size() >= kMaxEntries) { reason = "entries"; return false; }
    entries.push_back({name, size, static_cast<uint64_t>(ftello(file)), {}});  // index = data offset
    return fseeko(file, static_cast<off_t>(size), SEEK_CUR) == 0;
  }, reason);
  if (!ok) error = reason == "entries" ? "entries" : "invalid";
  return ok;
}

inline bool ExtractTarEntry(std::FILE* file, const Entry& entry, std::FILE* output,
                            const std::function<bool(uint64_t)>& tick, std::string& error) {
  std::vector<unsigned char> buffer(kChunk);
  uint64_t done = 0;
  if (fseeko(file, static_cast<off_t>(entry.index), SEEK_SET) != 0) { error = "invalid"; return false; }
  while (done < entry.size) {
    const size_t n = static_cast<size_t>(std::min<uint64_t>(entry.size - done, buffer.size()));
    if (std::fread(buffer.data(), 1, n, file) != n) { error = "invalid"; return false; }
    if (std::fwrite(buffer.data(), 1, n, output) != n) { error = "write"; return false; }
    done += n;
    if (tick && !tick(done)) { error = "cancelled"; return false; }
  }
  return true;
}

// ---------------------------------------------------------------------------
// Staged packs

struct Inventory {
  uint64_t files = 0, bytes = 0, named = 0, mips = 0, unsupported = 0;
  std::map<std::string, uint64_t> formats;  // FormatKey -> files
  std::vector<std::string> unsupportedSamples;
};

inline Format SniffFile(const fs::path& path, uint64_t size) {
  unsigned char head[kHeadBytes] = {};
  std::unique_ptr<std::FILE, int (*)(std::FILE*)> file(std::fopen(path.c_str(), "rb"), std::fclose);
  if (!file) return Format::Unsupported;
  const size_t length = std::fread(head, 1, sizeof(head), file.get());
  return SniffFormat(head, length, size, path.filename().string());
}

// Accounts for one staged file. A file the loaders cannot read is removed from
// the staged pack and counted: its extension alone never makes it compatible.
inline void Account(const fs::path& path, uint64_t size, Inventory& inventory, bool removeUnsupported) {
  const Format format = SniffFile(path, size);
  const std::string name = path.filename().string();
  if (format == Format::Unsupported) {
    ++inventory.unsupported;
    if (inventory.unsupportedSamples.size() < 5) inventory.unsupportedSamples.push_back(name);
    if (removeUnsupported) { std::error_code ignored; fs::remove(path, ignored); }
    return;
  }
  ++inventory.files;
  inventory.bytes += size;
  ++inventory.formats[FormatKey(format)];
  if (IsReplacementName(name)) ++inventory.named;
  else if (IsMipName(name)) ++inventory.mips;
}

// Scans an installed replacements folder (a pack copied without NeoStation, or
// a check of one it installed). Symbolic links are neither followed nor counted.
inline Inventory ScanInstalled(const fs::path& directory, const std::function<bool()>& cancelled = {}) {
  Inventory inventory;
  std::error_code code;
  fs::recursive_directory_iterator it(directory, fs::directory_options::none, code), end;
  uint64_t visited = 0;
  for (; !code && it != end; it.increment(code)) {
    if (++visited > kMaxEntries || (cancelled && cancelled())) break;
    const fs::file_status status = it->symlink_status(code);
    if (code || !fs::is_regular_file(status)) continue;
    const std::string name = it->path().filename().string();
    if (!HasLoaderExtension(name)) continue;
    const uint64_t size = it->file_size(code);
    if (!code) Account(it->path(), size, inventory, false);
  }
  return inventory;
}

inline bool IsRealDirectory(const fs::path& path) {
  std::error_code code;
  const fs::file_status status = fs::symlink_status(path, code);
  return !code && fs::is_directory(status) && !fs::is_symlink(status);
}

// Replaces <root>/<serial>/replacements with [staged] in two renames on one
// volume. The previous pack is moved to [previous] and kept until the caller
// deletes it (after the engine reloaded its map); any failure puts it back.
// Only the replacements folder changes: dumps and other files stay.
inline bool CommitStaged(const fs::path& root, const std::string& serial, const fs::path& staged,
                         const std::string& manifest, const fs::path& previous, bool& hadPrevious, std::string& error) {
  hadPrevious = false;
  std::error_code code;
  if (!IsStoreSerial(serial) || !IsRealDirectory(root) || !IsRealDirectory(staged)) { error = "invalid"; return false; }
  const fs::path folder = root / serial, target = folder / kReplacements;
  if (fs::exists(fs::symlink_status(folder, code)) && !IsRealDirectory(folder)) { error = "invalid"; return false; }
  fs::create_directories(folder, code);
  if (code || !IsRealDirectory(folder)) { error = "write"; return false; }
  const fs::file_status existing = fs::symlink_status(target, code);
  if (fs::exists(existing)) {
    if (!IsRealDirectory(target)) { error = "invalid"; return false; }
    fs::rename(target, previous, code);
    if (code) { error = "write"; return false; }
    hadPrevious = true;
  }
  const auto restore = [&] {
    std::error_code ignored;
    if (hadPrevious) { fs::remove_all(target, ignored); fs::rename(previous, target, ignored); hadPrevious = false; }
  };
  fs::rename(staged, target, code);
  if (code) { restore(); error = "write"; return false; }
  const fs::path temporary = folder / (std::string(kManifest) + ".tmp");
  {
    std::unique_ptr<std::FILE, int (*)(std::FILE*)> file(std::fopen(temporary.c_str(), "wb"), std::fclose);
    if (!file || std::fwrite(manifest.data(), 1, manifest.size(), file.get()) != manifest.size() || std::fflush(file.get()) != 0) {
      file.reset(); fs::remove(temporary, code);
      std::error_code ignored; fs::rename(target, staged, ignored);
      restore(); error = "write"; return false;
    }
  }
  fs::rename(temporary, folder / kManifest, code);
  if (code) {
    std::error_code ignored; fs::remove(temporary, ignored); fs::rename(target, staged, ignored);
    restore(); error = "write"; return false;
  }
  return true;
}

// Moves <root>/<serial>/replacements aside to [removing] (deleted by the caller
// after the engine reloaded its map), drops the manifest and the serial folder
// when nothing else (dumps, other files) is left in it.
inline bool RemovePack(const fs::path& root, const std::string& serial, const fs::path& removing, std::string& error) {
  std::error_code code;
  if (!IsStoreSerial(serial) || !IsRealDirectory(root)) { error = "invalid"; return false; }
  const fs::path folder = root / serial, target = folder / kReplacements;
  if (!fs::exists(fs::symlink_status(folder, code))) { error = "missing"; return false; }
  if (!IsRealDirectory(folder)) { error = "invalid"; return false; }
  if (fs::exists(fs::symlink_status(target, code))) {
    if (!IsRealDirectory(target)) { error = "invalid"; return false; }
    fs::rename(target, removing, code);
    if (code) { error = "write"; return false; }
  }
  fs::remove(folder / kManifest, code);
  if (fs::is_empty(folder, code) && !code) fs::remove(folder, code);
  return true;
}

// Leftovers of an interrupted import or removal, directly below [root] and only
// with this store's prefixes. Never called while an import or a game runs.
inline uint64_t SweepLeftovers(const fs::path& root) {
  uint64_t removed = 0;
  std::error_code code;
  if (!IsRealDirectory(root)) return 0;
  for (fs::directory_iterator it(root, code), end; !code && it != end; it.increment(code)) {
    const std::string name = it->path().filename().string();
    for (const char* prefix : {kStagingPrefix, kPreviousPrefix, kRemovingPrefix, kExpandedPrefix}) {
      if (name.rfind(prefix, 0) == 0) {
        std::error_code ignored;
        if (fs::remove_all(it->path(), ignored) != static_cast<std::uintmax_t>(-1)) ++removed;
        break;
      }
    }
  }
  return removed;
}

// ---------------------------------------------------------------------------
// Sources and staging

enum class SourceKind { Folder, Zip, Tar };

struct Source {
  SourceKind kind = SourceKind::Folder;
  fs::path path;
  bool moveFiles = false;            // folder already private to this store (expanded .tar.zst):
                                     // its files are moved and its own name is not part of the pack
  std::vector<Entry> entries;
  std::vector<ZipEntry> zip;         // parallel to entries for ZIP sources
  std::string error;
};

inline bool OpenSource(Source& source) {
  source.entries.clear(); source.zip.clear(); source.error.clear();
  if (source.kind == SourceKind::Folder) return ListFolder(source.path, source.entries, source.error, !source.moveFiles);
  std::unique_ptr<std::FILE, int (*)(std::FILE*)> file(std::fopen(source.path.c_str(), "rb"), std::fclose);
  if (!file) { source.error = "unreadable"; return false; }
  if (source.kind == SourceKind::Tar) return ListTar(file.get(), source.entries, source.error);
  if (!ListZip(file.get(), source.zip, source.error)) {
    if (source.error == "unsafe" && !source.zip.empty()) source.entries.push_back({source.zip.back().name, 0, 0, {}});
    return false;
  }
  for (size_t i = 0; i < source.zip.size(); ++i) source.entries.push_back({source.zip[i].name, source.zip[i].size, i, {}});
  return true;
}

// Writes the planned files below [staging] (a new private folder on the same
// volume as the textures), checking the free space before and while writing.
// [tick] gets the bytes written so far and returns false to cancel. Files the
// loaders cannot read are left out and counted in [inventory].
// error: "space", "cancelled", "write", "invalid", "method:<n>", "noNamedTextures".
inline bool StageFiles(const Source& source, const Plan& plan, const fs::path& staging, uint64_t available,
                       Inventory& inventory, const std::function<bool(uint64_t, uint64_t)>& tick, std::string& error) {
  inventory = {};
  // Files moved from a private expansion already occupy their space on this volume.
  const bool copying = !source.moveFiles;
  if (copying && (available < plan.bytes || available - plan.bytes < kSpareBytes)) { error = "space"; return false; }
  std::error_code code;
  fs::create_directories(staging, code);
  if (code || !IsRealDirectory(staging)) { error = "write"; return false; }
  std::unique_ptr<std::FILE, int (*)(std::FILE*)> archive(nullptr, std::fclose);
  if (source.kind != SourceKind::Folder) {
    archive.reset(std::fopen(source.path.c_str(), "rb"));
    if (!archive) { error = "unreadable"; return false; }
  }
  uint64_t written = 0;
  for (const Selected& selected : plan.files) {
    const Entry& entry = source.entries[selected.entry];
    const fs::path destination = staging / fs::path(selected.destination);
    fs::create_directories(destination.parent_path(), code);
    if (code) { error = "write"; return false; }
    const uint64_t before = written;
    const auto progress = [&](uint64_t done) {
      if (copying && (before + done > available || available - (before + done) < kSpareBytes)) { error = "space"; return false; }
      return !tick || tick(before + done, plan.bytes);
    };
    if (source.kind == SourceKind::Folder && source.moveFiles) {
      fs::rename(source.path / fs::path(entry.location), destination, code);
      if (code) { error = "write"; return false; }
      if (!progress(entry.size)) return false;
    } else {
      std::unique_ptr<std::FILE, int (*)(std::FILE*)> output(std::fopen(destination.c_str(), "wb"), std::fclose);
      if (!output) { error = "write"; return false; }
      bool ok = false;
      std::string reason;
      if (source.kind == SourceKind::Zip) ok = ExtractZipEntry(archive.get(), source.zip[entry.index], output.get(), progress, reason);
      else if (source.kind == SourceKind::Tar) ok = ExtractTarEntry(archive.get(), entry, output.get(), progress, reason);
      else {
        std::unique_ptr<std::FILE, int (*)(std::FILE*)> input(std::fopen((source.path / fs::path(entry.location)).c_str(), "rb"), std::fclose);
        ok = input != nullptr;
        if (!ok) reason = "unreadable";
        std::vector<unsigned char> buffer(kChunk);
        uint64_t done = 0;
        while (ok) {
          const size_t n = std::fread(buffer.data(), 1, buffer.size(), input.get());
          if (n == 0) { ok = !std::ferror(input.get()) && done == entry.size; if (!ok) reason = "unreadable"; break; }
          if (std::fwrite(buffer.data(), 1, n, output.get()) != n) { ok = false; reason = "write"; break; }
          done += n;
          if (done > entry.size) { ok = false; reason = "unreadable"; break; }
          if (!progress(done)) { ok = false; break; }
        }
      }
      if (std::fflush(output.get()) != 0) { ok = false; if (reason.empty()) reason = "write"; }
      output.reset();
      if (!ok) { if (error.empty()) error = reason.empty() ? "write" : reason; return false; }
    }
    written += entry.size;
    Account(destination, entry.size, inventory, true);
  }
  if (inventory.named == 0) { error = "noNamedTextures"; return false; }
  return true;
}

inline std::string JsonString(std::string_view text) {
  std::string out = "\"";
  for (const unsigned char c : text) {
    switch (c) {
      case '"': out += "\\\""; break;
      case '\\': out += "\\\\"; break;
      case '\n': out += "\\n"; break;
      case '\r': out += "\\r"; break;
      case '\t': out += "\\t"; break;
      default:
        if (c < 0x20) { char escaped[8]; std::snprintf(escaped, sizeof(escaped), "\\u%04x", c); out += escaped; }
        else out += static_cast<char>(c);
    }
  }
  return out + "\"";
}

inline std::string JsonStrings(const std::set<std::string>& values) {
  std::string out = "[";
  for (const std::string& value : values) out += (out.size() > 1 ? "," : "") + JsonString(value);
  return out + "]";
}

// NeoStation-texture-pack.json next to the replacements folder (the engine
// never reads it): what was installed, from what, and what the import saw.
inline std::string ManifestJSON(const std::string& serial, const std::string& sourceName, const char* sourceKind,
                                const Plan& plan, const Verdict& verdict, const Inventory& inventory,
                                const std::string& installedAt) {
  std::string formats = "{";
  for (const auto& [key, count] : inventory.formats) formats += (formats.size() > 1 ? "," : "") + JsonString(key) + ":" + std::to_string(count);
  formats += "}";
  return std::string("{\"schema\":1,\"serial\":") + JsonString(serial) +
         ",\"source\":" + JsonString(sourceName) + ",\"sourceKind\":" + JsonString(sourceKind) +
         ",\"installedAt\":" + JsonString(installedAt) +
         ",\"files\":" + std::to_string(inventory.files) + ",\"bytes\":" + std::to_string(inventory.bytes) +
         ",\"named\":" + std::to_string(inventory.named) + ",\"mips\":" + std::to_string(inventory.mips) +
         ",\"unsupported\":" + std::to_string(inventory.unsupported) + ",\"formats\":" + formats +
         ",\"packSerial\":" + JsonString(verdict.packSerial) + ",\"match\":" + JsonString(verdict.match) +
         ",\"packSerials\":" + JsonStrings(plan.packSerials) + ",\"regions\":" + JsonStrings(plan.hints.regions) +
         ",\"versions\":" + JsonStrings(plan.hints.versions) + ",\"crcs\":" + JsonStrings(plan.hints.crcs) + "}\n";
}

}  // namespace NeoARMSX2Textures
