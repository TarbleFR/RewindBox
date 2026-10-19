// SPDX-License-Identifier: GPL-3.0-or-later
// Reads the identifiers the embedded engines name texture folders after,
// directly from a game file, for the library entry point (outside a game the
// engines cannot be asked). Bounded reads only; no image is loaded whole.
//
//   PS2:   SYSTEM.CNF BOOT2 serial (CDVD.cpp form SLUS-21050) and the boot
//          ELF CRC (ElfObject::GetCRC: XOR of its 32-bit words), from ISO
//          (2048 or raw 2352-byte sectors) or CSO/ZSO.
//   GC/Wii: game ID and revision (disc header bytes 0..5 and 7) from ISO/GCM,
//          WBFS, CISO, GCZ, WIA and RVZ.
//   PSP:   PARAM.SFO DISC_ID / DISC_VERSION (PPSSPP's game ID) from ISO,
//          CSO, ZSO or PBP; UMD_DATA.BIN as a fallback.
//   PS1:   SYSTEM.CNF BOOT serial (SLUS-00067) from a CUE's first file, a
//          CCD's image, an M3U's first disc or a BIN/ISO/IMG (2048 or raw 2352-byte
//          sectors); CHD, PBP and ECM are compressed: no serial, title only.
//   3DS:   program ID (NCCH 0x118, what Azahar names load/textures after)
//          from NCSD (.3ds/.cci) and NCCH (.cxi/.app); title ID from the TMD
//          of a CIA. Encrypted containers keep their headers in clear.
//   N64:   the ROM header name GLideN64 names hires_texture/<name> after
//          (RSP_Init: bytes 0x20..0x33 in big-endian order, cut at the first
//          NUL, trailing spaces removed) from .z64, .v64 or .n64 byte orders;
//          the catalogue matches it in hexadecimal (identity values are
//          [A-Za-z0-9-]); country code 0x3E (region), version 0x3F.
#pragma once
#include <algorithm>
#include <array>
#include <cstdint>
#include <cstring>
#include <fcntl.h>
#include <memory>
#include <string>
#include <sys/stat.h>
#include <unistd.h>
#include <vector>
#include <zlib.h>

namespace NeoTextureIdentity {

struct Result {
  std::string system, scheme, type, value;   // e.g. ps2 / ps2-disc-serial / serial / SLUS21050
  std::string folder;                        // engine folder form (SLUS-21050, GZ2E01, ULUS10041, 16 hex)
  std::string revision, crc, region, format, title, problem;
  bool ok() const { return !value.empty(); }
};

class Reader {
 public:
  Reader(const Reader&) = delete;
  Reader& operator=(const Reader&) = delete;
  explicit Reader(const std::string& path) {
    fd_ = ::open(path.c_str(), O_RDONLY | O_CLOEXEC);
    struct stat st {};
    if (fd_ >= 0 && fstat(fd_, &st) == 0 && S_ISREG(st.st_mode)) length_ = uint64_t(st.st_size);
    else if (fd_ >= 0) { ::close(fd_); fd_ = -1; }
  }
  ~Reader() { if (fd_ >= 0) ::close(fd_); }
  bool good() const { return fd_ >= 0; }
  uint64_t length() const { return length_; }
  bool read(uint64_t at, void* out, size_t count) const {
    if (fd_ < 0 || at > length_ || count > length_ - at) return false;
    auto* p = static_cast<unsigned char*>(out);
    while (count) {
      const ssize_t n = ::pread(fd_, p, count, off_t(at));
      if (n <= 0) return false;
      p += n; at += uint64_t(n); count -= size_t(n);
    }
    return true;
  }
 private:
  int fd_ = -1;
  uint64_t length_ = 0;
};

inline uint16_t LE16(const unsigned char* p) { return uint16_t(p[0] | (p[1] << 8)); }
inline uint32_t LE32(const unsigned char* p) { return uint32_t(p[0]) | (uint32_t(p[1]) << 8) | (uint32_t(p[2]) << 16) | (uint32_t(p[3]) << 24); }
inline uint64_t LE64(const unsigned char* p) { return uint64_t(LE32(p)) | (uint64_t(LE32(p + 4)) << 32); }
inline uint32_t BE32(const unsigned char* p) { return (uint32_t(p[0]) << 24) | (uint32_t(p[1]) << 16) | (uint32_t(p[2]) << 8) | uint32_t(p[3]); }
inline uint64_t BE64(const unsigned char* p) { return (uint64_t(BE32(p)) << 32) | BE32(p + 4); }

inline std::string Hex16(uint64_t v) {
  static const char* digits = "0123456789ABCDEF";
  std::string s(16, '0');
  for (int i = 15; i >= 0; --i) { s[size_t(i)] = digits[v & 15]; v >>= 4; }
  return s;
}
inline std::string Hex8(uint32_t v) {
  static const char* digits = "0123456789ABCDEF";
  std::string s(8, '0');
  for (int i = 7; i >= 0; --i) { s[size_t(i)] = digits[v & 15]; v >>= 4; }
  return s;
}
inline std::string Upper(std::string s) { for (char& c : s) if (c >= 'a' && c <= 'z') c = char(c - 32); return s; }
inline bool Alnum(unsigned char c) { return (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9'); }

// LZ4 block decompression (ZSO). Returns the produced size or -1.
inline long LZ4Block(const unsigned char* in, size_t inSize, unsigned char* out, size_t outSize) {
  size_t i = 0, o = 0;
  while (i < inSize) {
    const unsigned token = in[i++];
    size_t literal = token >> 4;
    if (literal == 15) { unsigned char b; do { if (i >= inSize) return -1; b = in[i++]; literal += b; } while (b == 255); }
    if (literal > inSize - i || literal > outSize - o) return -1;
    std::memcpy(out + o, in + i, literal); i += literal; o += literal;
    if (i >= inSize) break;
    if (inSize - i < 2) return -1;
    const size_t offset = size_t(in[i]) | (size_t(in[i + 1]) << 8); i += 2;
    if (!offset || offset > o) return -1;
    size_t match = (token & 15) + 4;
    if ((token & 15) == 15) { unsigned char b; do { if (i >= inSize) return -1; b = in[i++]; match += b; } while (b == 255); }
    if (match > outSize - o) return -1;
    for (size_t k = 0; k < match; ++k, ++o) out[o] = out[o - offset];
  }
  return long(o);
}

// 2048-byte logical sectors over a plain ISO, a raw 2352-byte image or a
// CSO/ZSO compressed image (CISO header, block index, deflate or LZ4 blocks).
class Sectors {
 public:
  explicit Sectors(const Reader& reader) : reader_(reader) {
    unsigned char h[24] = {0};
    if (!reader.read(0, h, sizeof(h))) return;
    if ((!std::memcmp(h, "CISO", 4) || !std::memcmp(h, "ZISO", 4)) && LE32(h + 4) == 0x18) {
      compressed_ = true;
      lz4_ = h[0] == 'Z';
      total_ = LE64(h + 8);
      block_ = LE32(h + 16);
      align_ = h[21];
      if (block_ < 2048 || block_ > (1 << 20) || total_ > (64ull << 30)) { compressed_ = false; return; }
      const uint64_t blocks = (total_ + block_ - 1) / block_;
      if (blocks > (1u << 26)) { compressed_ = false; return; }
      index_.resize(size_t(blocks + 1));
      std::vector<unsigned char> raw(index_.size() * 4);
      if (!reader.read(0x18, raw.data(), raw.size())) { compressed_ = false; return; }
      for (size_t i = 0; i < index_.size(); ++i) index_[i] = LE32(raw.data() + i * 4);
      valid_ = true;
      return;
    }
    // Plain 2048-byte ISO, else a raw image (MODE1 data at 16, MODE2 at 24).
    unsigned char pvd[6];
    if (reader.read(16 * 2048, pvd, 6) && pvd[0] == 1 && !std::memcmp(pvd + 1, "CD001", 5)) { valid_ = true; return; }
    for (unsigned offset : {16u, 24u}) {
      if (reader.read(16ull * 2352 + offset, pvd, 6) && pvd[0] == 1 && !std::memcmp(pvd + 1, "CD001", 5)) {
        raw_ = true; rawOffset_ = offset; valid_ = true; return;
      }
    }
  }
  bool valid() const { return valid_; }
  const char* format() const { return compressed_ ? (lz4_ ? "zso" : "cso") : raw_ ? "bin" : "iso"; }
  bool read(uint64_t sector, unsigned char* out, size_t count) {
    for (size_t s = 0; s < count; ++s, ++sector, out += 2048) if (!readOne(sector, out)) return false;
    return true;
  }
 private:
  bool readOne(uint64_t sector, unsigned char* out) {
    if (!compressed_) {
      return raw_ ? reader_.read(sector * 2352 + rawOffset_, out, 2048) : reader_.read(sector * 2048, out, 2048);
    }
    const uint64_t at = sector * 2048, blockIndex = at / block_;
    if (blockIndex + 1 >= index_.size()) return false;
    if (cachedBlock_ != blockIndex) {
      const uint32_t a = index_[blockIndex], b = index_[blockIndex + 1];
      const bool plain = a & 0x80000000u;
      const uint64_t start = uint64_t(a & 0x7fffffffu) << align_, end = uint64_t(b & 0x7fffffffu) << align_;
      if (end < start || end - start > block_ * 2ull + 64) return false;
      std::vector<unsigned char> packed(size_t(end - start));
      if (!reader_.read(start, packed.data(), packed.size())) return false;
      cache_.assign(block_, 0);
      if (plain || packed.size() >= block_) {
        if (packed.size() < block_) return false;
        std::memcpy(cache_.data(), packed.data(), block_);
      } else if (lz4_) {
        if (LZ4Block(packed.data(), packed.size(), cache_.data(), block_) != long(block_)) return false;
      } else {
        z_stream z{};
        if (inflateInit2(&z, -15) != Z_OK) return false;
        z.next_in = packed.data(); z.avail_in = uInt(packed.size());
        z.next_out = cache_.data(); z.avail_out = uInt(block_);
        const int status = inflate(&z, Z_FINISH);
        const bool ok = (status == Z_STREAM_END || status == Z_OK || status == Z_BUF_ERROR) && z.avail_out == 0;
        inflateEnd(&z);
        if (!ok) return false;
      }
      cachedBlock_ = blockIndex;
    }
    std::memcpy(out, cache_.data() + (at % block_), 2048);
    return true;
  }
  const Reader& reader_;
  bool valid_ = false, compressed_ = false, lz4_ = false, raw_ = false;
  unsigned rawOffset_ = 0, align_ = 0;
  uint64_t total_ = 0, block_ = 0, cachedBlock_ = UINT64_MAX;
  std::vector<uint32_t> index_;
  std::vector<unsigned char> cache_;
};

// ISO9660 path lookup (case-insensitive, ";1" ignored), bounded.
struct ISOFile { uint32_t extent = 0, size = 0; bool directory = false; bool found = false; };

inline ISOFile ISOFind(Sectors& sectors, const std::vector<std::string>& path) {
  std::array<unsigned char, 2048> pvd{};
  if (!sectors.read(16, pvd.data(), 1) || pvd[0] != 1) return {};
  ISOFile current{LE32(pvd.data() + 156 + 2), LE32(pvd.data() + 156 + 10), true, true};
  for (auto wanted : path) {
    if (const size_t semicolon = wanted.find(';'); semicolon != std::string::npos) wanted.resize(semicolon);
    if (!current.directory || current.size > (4u << 20)) return {};
    const uint32_t sectorsInDir = (current.size + 2047) / 2048;
    std::vector<unsigned char> dir(size_t(sectorsInDir) * 2048);
    if (!sectors.read(current.extent, dir.data(), sectorsInDir)) return {};
    ISOFile next;
    for (size_t at = 0; at < current.size;) {
      const unsigned length = dir[at];
      if (!length) { at = (at / 2048 + 1) * 2048; continue; }
      if (at + length > dir.size() || length < 34) break;
      const unsigned nameLength = dir[at + 32];
      if (34u + nameLength - 1 > length) break;
      std::string name(reinterpret_cast<const char*>(dir.data() + at + 33), nameLength);
      const size_t semicolon = name.find(';');
      if (semicolon != std::string::npos) name.resize(semicolon);
      if (!name.empty() && name.back() == '.') name.pop_back();
      if (Upper(name) == Upper(wanted)) {
        next = {LE32(dir.data() + at + 2), LE32(dir.data() + at + 10), (dir[at + 25] & 2) != 0, true};
        break;
      }
      at += length;
    }
    if (!next.found) return {};
    current = next;
  }
  return current;
}

inline bool ISORead(Sectors& sectors, const ISOFile& file, std::vector<unsigned char>& out, uint32_t limit) {
  if (!file.found || file.directory || file.size > limit) return false;
  const uint32_t count = (file.size + 2047) / 2048;
  out.resize(size_t(count) * 2048);
  if (count && !sectors.read(file.extent, out.data(), count)) return false;
  out.resize(file.size);
  return true;
}

inline std::string PS2Region(const std::string& serial) {
  const std::string p = serial.substr(0, 4);
  if (p == "SLUS" || p == "SCUS" || p == "SLUD" || p == "SCUD") return "USA";
  if (p == "SLES" || p == "SCES" || p == "SLED" || p == "SCED") return "Europe";
  if (p == "SLPS" || p == "SLPM" || p == "SCPS" || p == "SCPM" || p == "SLAJ" || p == "SCAJ" || p == "PAPX" || p == "PCPX") return "Japan";
  if (p == "SLKA" || p == "SCKA") return "Korea";
  return "";
}

// withCRC false: the serial only (a library scan), without reading the boot ELF.
inline Result PS2(const std::string& path, bool withCRC = true) {
  Result r;
  r.system = "ps2"; r.type = "serial"; r.scheme = "ps2-disc-serial";
  Reader reader(path);
  if (!reader.good()) { r.problem = "unreadable"; return r; }
  Sectors sectors(reader);
  if (!sectors.valid()) { r.problem = "unsupportedFormat"; return r; }
  r.format = sectors.format();
  std::vector<unsigned char> cnf;
  if (!ISORead(sectors, ISOFind(sectors, {"SYSTEM.CNF"}), cnf, 4096)) { r.problem = "noSystemCnf"; return r; }
  const std::string text(cnf.begin(), cnf.end());
  size_t boot = text.find("BOOT2");
  if (boot == std::string::npos) { r.problem = "noBoot2"; return r; }
  size_t colon = text.find(':', boot);
  size_t end = text.find_first_of("\r\n", boot);
  if (colon == std::string::npos || (end != std::string::npos && colon > end)) { r.problem = "noBoot2"; return r; }
  std::string elf = text.substr(colon + 1, (end == std::string::npos ? text.size() : end) - colon - 1);
  while (!elf.empty() && (elf.front() == '\\' || elf.front() == '/' || elf.front() == ' ')) elf.erase(elf.begin());
  while (!elf.empty() && (elf.back() == ' ' || elf.back() == '\t')) elf.pop_back();
  std::vector<std::string> parts;
  std::string part;
  for (char c : elf) { if (c == '\\' || c == '/') { if (!part.empty()) parts.push_back(part); part.clear(); } else part += c; }
  if (!part.empty()) parts.push_back(part);
  if (parts.empty()) { r.problem = "noBoot2"; return r; }
  // Serial from the boot file name: SLUS_210.50;1 -> SLUS21050.
  std::string base = parts.back(), letters, digits;
  if (size_t semicolon = base.find(';'); semicolon != std::string::npos) base.resize(semicolon);
  for (char c : Upper(base)) {
    if (c >= 'A' && c <= 'Z' && digits.empty()) letters += c;
    else if (c >= '0' && c <= '9') digits += c;
  }
  if (letters.size() != 4 || digits.size() != 5) { r.problem = "noSerial"; return r; }
  r.value = letters + digits;
  r.folder = letters + "-" + digits;
  r.region = PS2Region(r.value);
  // Boot ELF CRC as PCSX2 computes it: XOR of all 32-bit little-endian words.
  const ISOFile file = withCRC ? ISOFind(sectors, parts) : ISOFile{};
  if (withCRC && file.found && !file.directory && file.size <= (64u << 20)) {
    uint32_t crc = 0;
    std::vector<unsigned char> chunk(64 * 2048);
    const uint32_t words = file.size / 4;
    uint32_t done = 0;
    bool ok = true;
    for (uint32_t sector = 0; done < words && ok; sector += 64) {
      const uint32_t remainingBytes = file.size - sector * 2048;
      const uint32_t count = std::min<uint32_t>(64, (remainingBytes + 2047) / 2048);
      ok = sectors.read(uint64_t(file.extent) + sector, chunk.data(), count);
      const uint32_t chunkWords = std::min<uint32_t>(words - done, count * 512);
      for (uint32_t w = 0; ok && w < chunkWords; ++w) crc ^= LE32(chunk.data() + w * 4);
      done += chunkWords;
    }
    if (ok) r.crc = Hex8(crc);
  }
  return r;
}

inline std::string LowerExtension(const std::string& path) {
  const size_t slash = path.rfind('/'), dot = path.rfind('.');
  if (dot == std::string::npos || (slash != std::string::npos && dot < slash)) return "";
  std::string e = path.substr(dot + 1);
  for (char& c : e) if (c >= 'A' && c <= 'Z') c = char(c + 32);
  return e;
}

// The disc image a PS1 content file names (Beetle loads the CUE, M3U or CCD
// itself): a CUE's first FILE, a CCD's .img, an M3U's first disc, relative to
// the file; the file itself otherwise. Bounded reads, three levels at most.
inline std::string PS1Image(const std::string& path, int depth = 0) {
  const std::string extension = LowerExtension(path);
  if (depth > 3 || (extension != "cue" && extension != "m3u" && extension != "ccd")) return path;
  const size_t slash = path.rfind('/');
  const std::string folder = slash == std::string::npos ? "" : path.substr(0, slash + 1);
  if (extension == "ccd") {
    const std::string stem = path.substr(0, path.size() - 3);
    struct stat st {};
    return ::stat((stem + "img").c_str(), &st) == 0 ? stem + "img" : stem + "bin";
  }
  Reader reader(path);
  if (!reader.good() || reader.length() > (64u << 10)) return "";
  std::string text(size_t(reader.length()), '\0');
  if (!reader.read(0, text.data(), text.size())) return "";
  size_t at = 0;
  while (at < text.size()) {
    size_t end = text.find_first_of("\r\n", at);
    if (end == std::string::npos) end = text.size();
    std::string line = text.substr(at, end - at);
    at = end + 1;
    while (!line.empty() && (line.front() == ' ' || line.front() == '\t')) line.erase(line.begin());
    while (!line.empty() && (line.back() == ' ' || line.back() == '\t')) line.pop_back();
    if (line.empty() || line[0] == '#') continue;
    std::string name;
    if (extension == "m3u") {
      name = line;
    } else {
      if (line.size() < 5 || Upper(line.substr(0, 5)) != "FILE ") continue;
      std::string rest = line.substr(5);
      if (!rest.empty() && rest[0] == '"') {
        const size_t close = rest.find('"', 1);
        if (close == std::string::npos) return "";
        name = rest.substr(1, close - 1);
      } else {
        name = rest.substr(0, rest.find(' '));
      }
    }
    if (name.empty() || name.find("..") != std::string::npos) return "";
    return PS1Image(name[0] == '/' ? name : folder + name, depth + 1);
  }
  return "";
}

inline Result PS1(const std::string& path) {
  Result r;
  r.system = "ps1"; r.type = "serial"; r.scheme = "ps1-disc-serial";
  const std::string image = PS1Image(path);
  if (image.empty()) { r.problem = "unreadable"; return r; }
  const std::string extension = LowerExtension(image);
  if (extension == "chd" || extension == "pbp" || extension == "ecm" || extension == "7z" || extension == "zip") {
    r.problem = "compressedImage";
    return r;
  }
  Reader reader(image);
  if (!reader.good()) { r.problem = "unreadable"; return r; }
  Sectors sectors(reader);
  if (!sectors.valid()) { r.problem = "unsupportedFormat"; return r; }
  r.format = extension == "cue" ? "bin" : extension;
  std::vector<unsigned char> cnf;
  if (!ISORead(sectors, ISOFind(sectors, {"SYSTEM.CNF"}), cnf, 4096)) { r.problem = "noSystemCnf"; return r; }
  const std::string text(cnf.begin(), cnf.end());
  // BOOT = cdrom:\SLUS_000.67;1 (a PS2 disc names BOOT2 instead).
  size_t boot = std::string::npos;
  for (size_t at = text.find("BOOT"); at != std::string::npos; at = text.find("BOOT", at + 4))
    if (at + 4 < text.size() && text[at + 4] != '2') { boot = at; break; }
  if (boot == std::string::npos) { r.problem = text.find("BOOT2") != std::string::npos ? "ps2Disc" : "noBoot"; return r; }
  const size_t end = text.find_first_of("\r\n", boot);
  const std::string line = text.substr(boot, (end == std::string::npos ? text.size() : end) - boot);
  const size_t sep = line.find_last_of("\\/:");
  std::string base = sep == std::string::npos ? line : line.substr(sep + 1), letters, digits;
  if (size_t semicolon = base.find(';'); semicolon != std::string::npos) base.resize(semicolon);
  for (char c : Upper(base)) {
    if (c >= 'A' && c <= 'Z' && digits.empty()) letters += c;
    else if (c >= '0' && c <= '9') digits += c;
  }
  if (letters.size() != 4 || digits.size() != 5) { r.problem = "noPS1Serial"; return r; }
  r.value = letters + "-" + digits;
  r.folder = r.value;
  r.region = letters == "SIPS" ? "Japan" : PS2Region(letters + digits);
  return r;
}

inline bool GameID(const unsigned char* h) {
  for (int i = 0; i < 6; ++i) if (!Alnum(h[i])) return false;
  return true;
}

inline Result Dolphin(const std::string& path, const std::string& system) {
  Result r;
  r.system = system; r.type = "game_id"; r.scheme = "dolphin-disc-game-id";
  Reader reader(path);
  if (!reader.good()) { r.problem = "unreadable"; return r; }
  unsigned char h[0x60] = {0};
  if (!reader.read(0, h, std::min<uint64_t>(sizeof(h), reader.length()))) { r.problem = "unreadable"; return r; }
  std::array<unsigned char, 0x20> disc{};
  bool found = false;
  auto take = [&](uint64_t at, const char* format) {
    if (reader.read(at, disc.data(), disc.size()) && GameID(disc.data())) { found = true; r.format = format; }
  };
  // WAD (Wii channel, Virtual Console): Dolphin's TMDReader::GetGameID is the
  // title ID's low four bytes and the group ID, its revision the title version.
  const bool wad = BE32(h) == 0x20 && (!std::memcmp(h + 4, "Is", 2) || !std::memcmp(h + 4, "ib", 2));
  if (wad) {
    auto align = [](uint64_t v) { return (v + 0x3F) & ~uint64_t(0x3F); };
    const uint64_t tmd = align(0x20) + align(BE32(h + 8)) + align(BE32(h + 16));
    unsigned char t[0x1DE] = {0};
    if (BE32(h + 20) >= sizeof(t) && reader.read(tmd, t, sizeof(t))) {
      std::memcpy(disc.data(), t + 0x190, 4);
      std::memcpy(disc.data() + 4, t + 0x198, 2);
      if (GameID(disc.data())) {
        found = true;
        r.format = "wad";
        disc[7] = 0;
        r.revision = std::to_string((unsigned(t[0x1DC]) << 8) | t[0x1DD]);
      }
    }
  } else if (!std::memcmp(h, "WBFS", 4)) take(uint64_t(1) << h[8], "wbfs");
  else if ((!std::memcmp(h, "WIA\x01", 4) || !std::memcmp(h, "RVZ\x01", 4))) take(0x58, h[0] == 'R' ? "rvz" : "wia");
  else if (!std::memcmp(h, "CISO", 4) && LE32(h + 4) >= 0x8000) take(0x8000, "ciso");
  else if (LE32(h) == 0xB10BC001u) {
    // GCZ: block pointers after the 32-byte header; block 0 holds the disc header.
    const uint32_t blockSize = LE32(h + 24), blocks = LE32(h + 28);
    unsigned char pointers[16];
    if (blocks && blockSize >= 0x20 && blockSize <= (1u << 24) && reader.read(32, pointers, blocks > 1 ? 16 : 8)) {
      const uint64_t first = LE64(pointers), next = blocks > 1 ? LE64(pointers + 8) : 0;
      const uint64_t dataStart = 32 + uint64_t(blocks) * 12;
      const bool plain = first >> 63;
      const uint64_t offset = first & ~(1ull << 63);
      const uint64_t end = blocks > 1 ? (next & ~(1ull << 63)) : LE64(h + 8);
      const uint64_t size = end > offset ? end - offset : 0;
      std::vector<unsigned char> packed(size_t(std::min<uint64_t>(size, uint64_t(blockSize) + 1024)));
      if (size && reader.read(dataStart + offset, packed.data(), packed.size())) {
        if (plain) {
          if (packed.size() >= disc.size()) { std::memcpy(disc.data(), packed.data(), disc.size()); found = GameID(disc.data()); }
        } else {
          std::vector<unsigned char> block(blockSize);
          uLongf produced = blockSize;
          if (uncompress(block.data(), &produced, packed.data(), uLong(packed.size())) == Z_OK && produced >= disc.size()) {
            std::memcpy(disc.data(), block.data(), disc.size());
            found = GameID(disc.data());
          }
        }
        if (found) r.format = "gcz";
      }
    }
  } else {
    // Raw disc: GameCube magic at 0x1C, Wii magic at 0x18.
    const bool gc = BE32(h + 0x1C) == 0xC2339F3Du, wii = BE32(h + 0x18) == 0x5D1C9EA3u;
    if ((gc || wii) && GameID(h)) { std::memcpy(disc.data(), h, disc.size()); found = true; r.format = "iso"; }
  }
  if (!found) { r.problem = "unsupportedFormat"; return r; }
  r.value = std::string(reinterpret_cast<const char*>(disc.data()), 6);
  r.folder = r.value;
  if (r.format != "wad") r.revision = std::to_string(unsigned(disc[7]));
  switch (disc[3]) {
    case 'E': r.region = "USA"; break;
    case 'P': case 'D': case 'F': case 'S': case 'I': case 'X': case 'Y': case 'U': r.region = "Europe"; break;
    case 'J': r.region = "Japan"; break;
    case 'K': r.region = "Korea"; break;
    default: break;
  }
  return r;
}

inline bool SFOValue(const std::vector<unsigned char>& sfo, const std::string& key, std::string& value) {
  if (sfo.size() < 20 || std::memcmp(sfo.data(), "\0PSF", 4)) return false;
  const uint32_t keys = LE32(sfo.data() + 8), data = LE32(sfo.data() + 12), count = LE32(sfo.data() + 16);
  if (count > 1024 || 20ull + count * 16ull > sfo.size()) return false;
  for (uint32_t i = 0; i < count; ++i) {
    const unsigned char* e = sfo.data() + 20 + i * 16;
    const uint32_t keyAt = keys + LE16(e), length = LE32(e + 4), at = data + LE32(e + 12);
    if (keyAt >= sfo.size()) return false;
    const char* name = reinterpret_cast<const char*>(sfo.data() + keyAt);
    const size_t maxName = sfo.size() - keyAt;
    if (strnlen(name, maxName) == maxName) return false;
    if (key != name) continue;
    if (uint64_t(at) + length > sfo.size()) return false;
    value.assign(reinterpret_cast<const char*>(sfo.data() + at), length);
    value.resize(strnlen(value.c_str(), value.size()));
    return true;
  }
  return false;
}

inline bool DiscID(std::string raw, std::string& out) {
  raw = Upper(raw);
  std::string compact;
  for (char c : raw) if (c != '-' && c != '_') compact += c;
  if (compact.size() != 9) return false;
  for (int i = 0; i < 4; ++i) if (compact[size_t(i)] < 'A' || compact[size_t(i)] > 'Z') return false;
  for (int i = 4; i < 9; ++i) if (compact[size_t(i)] < '0' || compact[size_t(i)] > '9') return false;
  out = compact;
  return true;
}

inline Result PSP(const std::string& path) {
  Result r;
  r.system = "psp"; r.type = "game_id"; r.scheme = "psp-param-sfo-disc-id";
  Reader reader(path);
  if (!reader.good()) { r.problem = "unreadable"; return r; }
  unsigned char h[40] = {0};
  reader.read(0, h, std::min<uint64_t>(sizeof(h), reader.length()));
  std::vector<unsigned char> sfo;
  if (!std::memcmp(h, "\0PBP", 4)) {
    const uint32_t start = LE32(h + 8), end = LE32(h + 12);
    if (end > start && end - start <= 65536) { sfo.resize(end - start); if (!reader.read(start, sfo.data(), sfo.size())) sfo.clear(); }
    r.format = "pbp";
  } else {
    Sectors sectors(reader);
    if (!sectors.valid()) { r.problem = "unsupportedFormat"; return r; }
    r.format = sectors.format();
    if (!ISORead(sectors, ISOFind(sectors, {"PSP_GAME", "PARAM.SFO"}), sfo, 65536)) sfo.clear();
    if (sfo.empty()) {
      std::vector<unsigned char> umd;
      if (ISORead(sectors, ISOFind(sectors, {"UMD_DATA.BIN"}), umd, 4096)) {
        std::string text(umd.begin(), umd.end());
        std::string id;
        if (DiscID(text.substr(0, text.find('|')), id)) { r.value = id; r.folder = id; }
      }
    }
  }
  std::string id, version;
  if (!sfo.empty() && SFOValue(sfo, "DISC_ID", id) && DiscID(id, id)) {
    r.value = id; r.folder = id;
    if (SFOValue(sfo, "DISC_VERSION", version)) r.revision = version;
  }
  if (r.value.empty()) { r.problem = "noDiscID"; return r; }
  const char c = r.value[2];
  r.region = c == 'U' ? "USA" : c == 'E' ? "Europe" : c == 'J' ? "Japan" : c == 'A' ? "Asia" : c == 'K' ? "Korea" : "";
  return r;
}

inline Result N3DS(const std::string& path) {
  Result r;
  r.system = "3ds"; r.type = "title_id"; r.scheme = "3ds-title-id";
  Reader reader(path);
  if (!reader.good()) { r.problem = "unreadable"; return r; }
  unsigned char h[0x200] = {0};
  if (!reader.read(0, h, std::min<uint64_t>(sizeof(h), reader.length()))) { r.problem = "unreadable"; return r; }
  uint64_t program = 0;
  if (!std::memcmp(h + 0x100, "NCSD", 4)) {
    const uint64_t offset = uint64_t(LE32(h + 0x120)) * 0x200;
    unsigned char ncch[0x200];
    if (reader.read(offset, ncch, sizeof(ncch)) && !std::memcmp(ncch + 0x100, "NCCH", 4)) program = LE64(ncch + 0x118);
    r.format = "cci";
  } else if (!std::memcmp(h + 0x100, "NCCH", 4)) {
    program = LE64(h + 0x118);
    r.format = "cxi";
  } else if (LE32(h) == 0x2020) {
    // CIA: header, certificates, ticket, TMD; each section aligned to 64 bytes.
    auto align = [](uint64_t v) { return (v + 63) & ~uint64_t(63); };
    const uint64_t certs = align(0x2020), ticket = certs + align(LE32(h + 8)), tmd = ticket + align(LE32(h + 12));
    unsigned char sig[4];
    if (reader.read(tmd, sig, 4)) {
      const uint32_t type = BE32(sig);
      const uint64_t header = type == 0x10003 ? 0x240 : type == 0x10004 ? 0x140 : type == 0x10005 ? 0x80 : 0;
      unsigned char id[8];
      if (header && reader.read(tmd + header + 0x4C, id, 8)) program = BE64(id);
    }
    r.format = "cia";
  } else {
    r.problem = "unsupportedFormat";
    return r;
  }
  if (!program) { r.problem = "noTitleID"; return r; }
  const uint32_t category = uint32_t(program >> 32);
  // Updates (0004000E) and DLC (0004008C) are not the game's own program.
  if (category == 0x0004000Eu || category == 0x0004008Cu) { r.problem = "notGame"; r.value.clear(); return r; }
  r.value = Hex16(program);
  r.folder = r.value;
  return r;
}

inline Result N64(const std::string& path) {
  Result r;
  r.system = "n64"; r.type = "rom_name"; r.scheme = "n64-rom-name-hex";
  Reader reader(path);
  if (!reader.good()) { r.problem = "unreadable"; return r; }
  unsigned char raw[0x40] = {0}, h[0x40] = {0};
  if (reader.length() < sizeof(raw) || !reader.read(0, raw, sizeof(raw))) { r.problem = "unreadable"; return r; }
  // The first word is 0x80371240 in big-endian (.z64) order.
  const uint32_t magic = BE32(raw);
  for (size_t i = 0; i < sizeof(raw); ++i) {
    if (magic == 0x80371240u) { h[i] = raw[i]; r.format = "z64"; }
    else if (magic == 0x37804012u) { h[i] = raw[i ^ 1]; r.format = "v64"; }
    else if (magic == 0x40123780u) { h[i] = raw[i ^ 3]; r.format = "n64"; }
    else { r.problem = "unsupportedFormat"; return r; }
  }
  std::string name;
  for (size_t i = 0x20; i < 0x34 && h[i]; ++i) name += char(h[i]);
  while (!name.empty() && name.back() == ' ') name.pop_back();
  // mbstowcs turns the name into the folder name: only printable ASCII is the same folder on every system.
  if (name.empty()) { r.problem = "noRomName"; return r; }
  for (unsigned char c : name)
    if (c < 0x20 || c > 0x7E || c == '/' || c == '\\' || c == ':') { r.problem = "unsupportedRomName"; return r; }
  if (name == "." || name == ".." || name.front() == ' ' || name.front() == '.') { r.problem = "unsupportedRomName"; return r; }
  static const char digits[] = "0123456789ABCDEF";
  for (unsigned char c : name) { r.value += digits[c >> 4]; r.value += digits[c & 15]; }
  r.folder = name;
  r.title = name;
  r.revision = std::to_string(unsigned(h[0x3F]));
  switch (h[0x3E]) {
    case 'E': case 'N': r.region = "USA"; break;
    case 'J': r.region = "Japan"; break;
    case 'P': case 'D': case 'F': case 'I': case 'S': case 'U': case 'X': case 'Y': case 'H': case 'W': case 'L': r.region = "Europe"; break;
    case 'K': r.region = "Korea"; break;
    case 'A': case 'C': r.region = "Asia"; break;
    default: break;
  }
  return r;
}

}  // namespace NeoTextureIdentity
