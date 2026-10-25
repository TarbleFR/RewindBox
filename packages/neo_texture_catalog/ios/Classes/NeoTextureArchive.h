// SPDX-License-Identifier: GPL-3.0-or-later
// Streaming readers for HD texture pack archives (ZIP, ZIP64 and 7z).
//
// A pack can hold tens of thousands of textures and several GiB. Nothing here
// keeps an archive, an entry or a solid 7z block in memory: the central
// directory (or the 7z header) is parsed into a list of entries, then each
// entry is decompressed through fixed buffers straight into a new file whose
// CRC-32 and size are checked against the archive. The caller decides which
// entries are wanted and where they go; this layer only rejects archives and
// names it cannot read safely.
#pragma once
#include <algorithm>
#include <array>
#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <functional>
#include <memory>
#include <string>
#include <sys/stat.h>
#include <unistd.h>
#include <vector>
#include <zlib.h>

namespace NeoTextureArchive {

enum class Status { ok, cancelled, invalid, unsupported, io, crc, limits };

inline const char* StatusName(Status status) {
  switch (status) {
    case Status::ok: return "ok";
    case Status::cancelled: return "cancelled";
    case Status::invalid: return "invalid";
    case Status::unsupported: return "unsupported";
    case Status::io: return "io";
    case Status::crc: return "crc";
    case Status::limits: return "limits";
  }
  return "invalid";
}

struct Limits {
  uint64_t maxArchive = 64ULL << 30;  // bytes on disk
  uint64_t maxTotal = 48ULL << 30;    // sum of expanded wanted entries (checked by callers)
  uint64_t maxFile = 1ULL << 30;      // one expanded entry
  uint32_t maxEntries = 400000;
  uint32_t maxName = 1024;
  // 7z only: largest LZMA window allocated for one solid block. A block whose
  // expanded size is smaller than its dictionary only needs that size.
  uint64_t maxDictionary = 256ULL << 20;
};

struct Entry {
  std::string name;  // normalized: '/'-separated, relative, no '.'/'..'/empty parts
  std::string raw;   // exact name bytes as stored (ZIP local header check)
  uint64_t size = 0, compressed = 0, localOffset = 0;
  uint32_t crc = 0;
  bool hasCRC = true, directory = false, link = false, encrypted = false, supported = true;
  uint16_t method = 0, flags = 0;
  // 7z: solid block index and position of the entry inside the block output.
  uint32_t folder = UINT32_MAX;
  uint64_t folderOffset = 0;
};

// A progress callback receives the number of compressed input bytes consumed
// since the previous call and returns false to cancel.
using Progress = std::function<bool(uint64_t)>;

inline uint16_t U16(const unsigned char* p) { return uint16_t(p[0] | (uint16_t(p[1]) << 8)); }
inline uint32_t U32(const unsigned char* p) { return uint32_t(U16(p)) | (uint32_t(U16(p + 2)) << 16); }
inline uint64_t U64(const unsigned char* p) { return uint64_t(U32(p)) | (uint64_t(U32(p + 4)) << 32); }

// CP437 (the ZIP default when bit 11 is clear) to UTF-8 for bytes >= 0x80.
inline const char* CP437High(unsigned char c) {
  static const char* const table[128] = {
    "Ç","ü","é","â","ä","à","å","ç","ê","ë","è","ï","î","ì","Ä","Å","É","æ","Æ","ô","ö","ò","û","ù","ÿ","Ö","Ü","¢","£","¥","₧","ƒ",
    "á","í","ó","ú","ñ","Ñ","ª","º","¿","⌐","¬","½","¼","¡","«","»","░","▒","▓","│","┤","╡","╢","╖","╕","╣","║","╗","╝","╜","╛","┐",
    "└","┴","┬","├","─","┼","╞","╟","╚","╔","╩","╦","╠","═","╬","╧","╨","╤","╥","╙","╘","╒","╓","╫","╪","┘","┌","█","▄","▌","▐","▀",
    "α","ß","Γ","π","Σ","σ","µ","τ","Φ","Θ","Ω","δ","∞","φ","ε","∩","≡","±","≥","≤","⌠","⌡","÷","≈","°","∙","·","√","ⁿ","²","■"," "};
  return table[c - 128];
}

inline bool ValidUTF8(const std::string& s) {
  size_t i = 0;
  while (i < s.size()) {
    const unsigned char c = static_cast<unsigned char>(s[i]);
    size_t extra = c < 0x80 ? 0 : (c >> 5) == 6 ? 1 : (c >> 4) == 14 ? 2 : (c >> 3) == 30 ? 3 : 9;
    if (extra == 9 || i + extra >= s.size() + (extra ? 0 : 1)) return false;
    for (size_t k = 1; k <= extra; ++k)
      if ((static_cast<unsigned char>(s[i + k]) >> 6) != 2) return false;
    i += extra + 1;
  }
  return true;
}

// Normalizes an archive name. Windows tools sometimes store '\' separators;
// they are folded to '/'. Absolute names, drive letters, control characters,
// '.'/'..' and empty components make the whole entry unreadable (empty result).
inline std::string NormalizeName(std::string name, bool* directory) {
  if (directory) *directory = false;
  if (name.empty()) return {};
  for (char& c : name) if (c == '\\') c = '/';
  if (name.front() == '/') return {};
  if (name.size() >= 2 && name[1] == ':') return {};
  bool trailing = name.back() == '/';
  if (trailing) name.pop_back();
  std::string out;
  size_t start = 0;
  while (start <= name.size()) {
    size_t end = name.find('/', start);
    if (end == std::string::npos) end = name.size();
    std::string part = name.substr(start, end - start);
    if (part.empty() || part == "." || part == "..") return {};
    for (unsigned char c : part) if (c < 0x20 || c == 0x7f) return {};
    if (!out.empty()) out += '/';
    out += part;
    start = end + 1;
  }
  if (directory) *directory = trailing;
  return out;
}

class File {
 public:
  File() = default;
  File(const File&) = delete;
  File& operator=(const File&) = delete;
  ~File() { if (fd_ >= 0) ::close(fd_); }
  bool open(const std::string& path) {
    fd_ = ::open(path.c_str(), O_RDONLY | O_CLOEXEC);
    if (fd_ < 0) return false;
    struct stat st {};
    if (fstat(fd_, &st) != 0 || !S_ISREG(st.st_mode)) return false;
    length_ = static_cast<uint64_t>(st.st_size);
    return true;
  }
  bool read(uint64_t at, void* bytes, size_t count) const {
    if (at > length_ || count > length_ - at) return false;
    auto* out = static_cast<unsigned char*>(bytes);
    while (count) {
      const ssize_t n = ::pread(fd_, out, count, static_cast<off_t>(at));
      if (n < 0 && errno == EINTR) continue;
      if (n <= 0) return false;
      out += n; at += static_cast<uint64_t>(n); count -= static_cast<size_t>(n);
    }
    return true;
  }
  uint64_t length() const { return length_; }
 private:
  int fd_ = -1;
  uint64_t length_ = 0;
};

// Writes a new regular file. O_EXCL|O_NOFOLLOW: the staging tree is private
// and freshly created, so an existing name or a link is always an error.
class Output {
 public:
  Output(const Output&) = delete;
  Output& operator=(const Output&) = delete;
  explicit Output(const std::string& path) : path_(path) {
    fd_ = ::open(path.c_str(), O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0644);
  }
  ~Output() {
    if (fd_ >= 0) ::close(fd_);
    if (!committed_) ::unlink(path_.c_str());
  }
  bool good() const { return fd_ >= 0; }
  bool write(const unsigned char* bytes, size_t count) {
    while (count) {
      const ssize_t n = ::write(fd_, bytes, count);
      if (n < 0 && errno == EINTR) continue;
      if (n <= 0) return false;
      bytes += n; count -= static_cast<size_t>(n);
    }
    return true;
  }
  bool commit() {
    if (fd_ < 0) return false;
    const bool ok = ::close(fd_) == 0;
    fd_ = -1;
    committed_ = ok;
    return ok;
  }
 private:
  std::string path_;
  int fd_ = -1;
  bool committed_ = false;
};

// Creates every missing parent of `path` below `root` (both absolute, `path`
// inside `root`). Refuses links and non-directories on the way.
inline bool MakeParents(const std::string& root, const std::string& path) {
  if (path.size() <= root.size() + 1 || path.compare(0, root.size(), root) != 0 || path[root.size()] != '/') return false;
  size_t at = root.size() + 1;
  while (true) {
    const size_t slash = path.find('/', at);
    if (slash == std::string::npos) return true;
    const std::string dir = path.substr(0, slash);
    struct stat st {};
    if (::lstat(dir.c_str(), &st) == 0) {
      if (!S_ISDIR(st.st_mode)) return false;
    } else if (errno != ENOENT || (::mkdir(dir.c_str(), 0755) != 0 && errno != EEXIST)) {
      return false;
    } else if (::lstat(dir.c_str(), &st) != 0 || !S_ISDIR(st.st_mode)) {
      return false;
    }
    at = slash + 1;
  }
}

class Zip {
 public:
  Status open(const std::string& path, const Limits& limits = {}) {
    limits_ = limits;
    entries_.clear();
    if (!file_.open(path)) return Status::io;
    const uint64_t length = file_.length();
    if (length < 22) return Status::invalid;
    if (length > limits.maxArchive) return Status::limits;
    const size_t tailSize = static_cast<size_t>(std::min<uint64_t>(length, 65557));
    std::vector<unsigned char> tail(tailSize);
    if (!file_.read(length - tailSize, tail.data(), tailSize)) return Status::io;
    size_t eocd = tailSize;
    for (size_t i = tailSize - 22;; --i) {
      if (U32(tail.data() + i) == 0x06054b50 && i + 22 + U16(tail.data() + i + 20) == tailSize) { eocd = i; break; }
      if (i == 0) break;
    }
    if (eocd == tailSize) return Status::invalid;
    const unsigned char* e = tail.data() + eocd;
    const uint64_t eocdAt = length - tailSize + eocd;
    uint64_t count = U16(e + 10), dirSize = U32(e + 12), dirAt = U32(e + 16);
    if (U16(e + 4) || U16(e + 6)) return Status::unsupported;  // split archive
    if (U16(e + 8) != U16(e + 10)) return Status::unsupported;
    uint64_t dirEnd = eocdAt;
    if (count == 0xffff || dirSize == 0xffffffff || dirAt == 0xffffffff) {
      if (eocdAt < 20) return Status::invalid;
      unsigned char locator[20];
      if (!file_.read(eocdAt - 20, locator, sizeof(locator)) || U32(locator) != 0x07064b50) return Status::invalid;
      if (U32(locator + 4) != 0 || U32(locator + 16) > 1) return Status::unsupported;
      const uint64_t z64At = U64(locator + 8);
      unsigned char record[56];
      if (z64At + 56 > eocdAt - 20 || !file_.read(z64At, record, sizeof(record)) || U32(record) != 0x06064b50) return Status::invalid;
      if (U32(record + 16) || U32(record + 20) || U64(record + 24) != U64(record + 32)) return Status::unsupported;
      count = U64(record + 32); dirSize = U64(record + 40); dirAt = U64(record + 48);
      dirEnd = z64At;
    }
    if (count > limits.maxEntries) return Status::limits;
    if (dirAt > dirEnd || dirSize > dirEnd - dirAt) return Status::invalid;
    // Some writers pad between the directory and its end record; never accept
    // a directory that would overlap the end records.
    centralStart_ = dirAt;
    uint64_t at = dirAt;
    const uint64_t end = dirAt + dirSize;
    entries_.reserve(static_cast<size_t>(count));
    std::vector<unsigned char> buffer;
    for (uint64_t i = 0; i < count; ++i) {
      unsigned char h[46];
      if (at + 46 > end || !file_.read(at, h, sizeof(h)) || U32(h) != 0x02014b50) return Status::invalid;
      const uint16_t nameSize = U16(h + 28), extraSize = U16(h + 30), commentSize = U16(h + 32);
      if (!nameSize || nameSize > limits.maxName) return Status::limits;
      if (at + 46 + nameSize + extraSize + commentSize > end) return Status::invalid;
      buffer.resize(size_t(nameSize) + extraSize);
      if (!file_.read(at + 46, buffer.data(), buffer.size())) return Status::io;
      Entry entry;
      entry.raw.assign(reinterpret_cast<const char*>(buffer.data()), nameSize);
      entry.flags = U16(h + 8);
      entry.method = U16(h + 10);
      entry.crc = U32(h + 16);
      entry.compressed = U32(h + 20);
      entry.size = U32(h + 24);
      entry.localOffset = U32(h + 42);
      const uint32_t diskStart = U16(h + 34);
      const uint16_t madeBy = U16(h + 4);
      const uint32_t external = U32(h + 38);
      // ZIP64 extended information: only the 32-bit fields saturated at
      // 0xffffffff are present, in this order.
      const unsigned char* extra = buffer.data() + nameSize;
      for (size_t x = 0; x + 4 <= extraSize;) {
        const uint16_t id = U16(extra + x), size = U16(extra + x + 2);
        if (x + 4 + size > extraSize) return Status::invalid;
        if (id == 0x0001) {
          const unsigned char* p = extra + x + 4;
          size_t left = size;
          auto take = [&](uint64_t& value) {
            if (left < 8) return false;
            value = U64(p); p += 8; left -= 8; return true;
          };
          if (entry.size == 0xffffffff && !take(entry.size)) return Status::invalid;
          if (entry.compressed == 0xffffffff && !take(entry.compressed)) return Status::invalid;
          if (entry.localOffset == 0xffffffff && !take(entry.localOffset)) return Status::invalid;
        }
        x += 4 + size;
      }
      if (diskStart != 0 && diskStart != 0xffff) return Status::unsupported;
      std::string name = entry.raw;
      if (!(entry.flags & 0x0800)) {
        bool high = false;
        for (unsigned char c : name) high = high || c >= 0x80;
        if (high) {
          std::string converted;
          for (unsigned char c : name) converted += c < 0x80 ? std::string(1, static_cast<char>(c)) : std::string(CP437High(c));
          name = converted;
        }
      } else if (!ValidUTF8(name)) {
        return Status::invalid;
      }
      bool trailingSlash = false;
      entry.name = NormalizeName(name, &trailingSlash);
      if (entry.name.empty()) return Status::invalid;
      const unsigned host = madeBy >> 8;
      const uint32_t mode = external >> 16;
      entry.link = host == 3 && (mode & 0170000) == 0120000;
      entry.directory = trailingSlash || (host == 3 && (mode & 0170000) == 0040000) || (host == 0 && (external & 0x10));
      entry.encrypted = (entry.flags & 1) != 0;
      entry.supported = !entry.link && !entry.encrypted && (entry.method == 0 || entry.method == 8);
      if (!entry.directory && entry.size > limits.maxFile) entry.supported = false;
      if (entry.localOffset >= centralStart_) return Status::invalid;
      entries_.push_back(std::move(entry));
      at += 46 + nameSize + extraSize + commentSize;
    }
    if (at != end) return Status::invalid;
    return Status::ok;
  }

  const std::vector<Entry>& entries() const { return entries_; }

  // Extracts one regular entry into a new file at `output` (whose parent
  // must exist). Data must lie before the central directory and the bytes
  // produced must match the recorded size and CRC-32 exactly.
  Status extract(const Entry& entry, const std::string& output, const Progress& progress) const {
    if (entry.directory || !entry.supported) return Status::unsupported;
    unsigned char h[30];
    if (!file_.read(entry.localOffset, h, sizeof(h)) || U32(h) != 0x04034b50) return Status::invalid;
    if (U16(h + 8) != entry.method) return Status::invalid;
    const uint16_t nameSize = U16(h + 26), extraSize = U16(h + 28);
    if (nameSize != entry.raw.size()) return Status::invalid;
    std::string local(nameSize, '\0');
    if (!file_.read(entry.localOffset + 30, local.data(), nameSize) || local != entry.raw) return Status::invalid;
    const uint64_t dataAt = entry.localOffset + 30 + nameSize + extraSize;
    if (dataAt > centralStart_ || entry.compressed > centralStart_ - dataAt) return Status::invalid;
    if (entry.method == 0 && entry.compressed != entry.size) return Status::invalid;
    Output out(output);
    if (!out.good()) return Status::io;
    std::unique_ptr<unsigned char[]> input(new unsigned char[kChunk]), decoded(new unsigned char[kChunk]);
    uint64_t remaining = entry.compressed, produced = 0, at = dataAt;
    uLong crc = crc32(0L, Z_NULL, 0);
    z_stream stream{};
    const bool deflated = entry.method == 8;
    if (deflated && inflateInit2(&stream, -MAX_WBITS) != Z_OK) return Status::io;
    struct Ender { z_stream* s; bool on; ~Ender() { if (on) inflateEnd(s); } } ender{&stream, deflated};
    bool ended = !deflated;
    while (remaining) {
      const size_t n = static_cast<size_t>(std::min<uint64_t>(remaining, kChunk));
      if (!file_.read(at, input.get(), n)) return Status::io;
      at += n; remaining -= n;
      if (!deflated) {
        produced += n;
        if (produced > entry.size || !out.write(input.get(), n)) return produced > entry.size ? Status::invalid : Status::io;
        crc = crc32(crc, input.get(), static_cast<uInt>(n));
      } else {
        if (ended) return Status::invalid;  // data after the end of the stream
        stream.next_in = input.get();
        stream.avail_in = static_cast<uInt>(n);
        do {
          stream.next_out = decoded.get();
          stream.avail_out = static_cast<uInt>(kChunk);
          const int status = inflate(&stream, Z_NO_FLUSH);
          if (status == Z_STREAM_END) ended = true;
          else if (status != Z_OK && status != Z_BUF_ERROR) return Status::invalid;
          const size_t written = kChunk - stream.avail_out;
          produced += written;
          if (produced > entry.size) return Status::invalid;
          if (written && !out.write(decoded.get(), written)) return Status::io;
          crc = crc32(crc, decoded.get(), static_cast<uInt>(written));
          if (ended) { if (stream.avail_in || remaining) return Status::invalid; break; }
          if (status == Z_BUF_ERROR && !written) { if (stream.avail_in) return Status::invalid; break; }
        } while (stream.avail_in || stream.avail_out == 0);
      }
      if (progress && !progress(n)) return Status::cancelled;
    }
    if (!ended || produced != entry.size) return Status::invalid;
    if (crc != entry.crc) return Status::crc;
    if (!out.commit()) return Status::io;
    return Status::ok;
  }

  // Extracts the entries for which `destination` returns a non-empty path,
  // in archive order. Local headers must not overlap: a byte range of the
  // archive can never be decompressed twice (overlapping-entry ZIP bombs).
  Status extractAll(const std::function<std::string(const Entry&)>& destination, const Progress& progress) const {
    std::vector<const Entry*> order;
    order.reserve(entries_.size());
    for (const auto& entry : entries_) if (!entry.directory) order.push_back(&entry);
    std::sort(order.begin(), order.end(), [](const Entry* a, const Entry* b) { return a->localOffset < b->localOffset; });
    uint64_t previousEnd = 0;
    for (const Entry* entry : order) {
      if (entry->localOffset < previousEnd) return Status::invalid;
      previousEnd = entry->localOffset + 30 + entry->raw.size() + entry->compressed;
      const std::string path = destination(*entry);
      if (path.empty()) continue;
      if (!entry->supported) return entry->size > limits_.maxFile ? Status::limits : Status::unsupported;
      const Status status = extract(*entry, path, progress);
      if (status != Status::ok) return status;
    }
    return Status::ok;
  }

 private:
  static constexpr size_t kChunk = 256 * 1024;
  File file_;
  std::vector<Entry> entries_;
  uint64_t centralStart_ = 0;
  Limits limits_;
};

}  // namespace NeoTextureArchive
