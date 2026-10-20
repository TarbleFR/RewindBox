// SPDX-License-Identifier: GPL-3.0-or-later
// Streaming, read-only RAR4/RAR5 adapter. ZIP and 7z keep their existing readers.
// libarchive only decodes bytes; filesystem writes stay in NeoStation's guarded
// staging writer. No extra volume or program is opened. Decoder allocations
// share one per-reader capped budget.
#pragma once
#include "NeoTextureArchive.h"
#include "NeoTextureRARMemory.h"
#include "../ThirdParty/libarchive/NeoTextureLibarchivePrefix.h"
extern "C" {
#include "../ThirdParty/libarchive/archive.h"
#include "../ThirdParty/libarchive/archive_entry.h"
#include "../ThirdParty/libarchive/archive_blake2.h"
}
#include <set>

namespace NeoTextureArchive {
class Rar {
 public:
  Rar() = default;
  Rar(const Rar&) = delete;
  Rar& operator=(const Rar&) = delete;
  ~Rar() { closeDecoder(); }

  Status open(const std::string& path, const Limits& limits = {}, const Progress& progress = {}) {
    closeDecoder();
    entries_.clear(); checksums_.clear(); problem_.clear(); limits_ = limits; progress_ = progress; solid_ = false;
    file_ = std::make_unique<File>();
    if (!file_->open(path)) return Status::io;
    if (file_->length() > limits.maxArchive) return Status::limits;
    if (const Status s = preflight(); s != Status::ok) return s;
    if (const Status s = scanChecksums(); s != Status::ok) return s;
    budget_ = {size_t(std::min<uint64_t>(limits.maxDictionary, 256ULL << 20)), 0, 0, 0};
    if (!budget_.limit) return Status::limits;
    if (const Status s = openDecoder(); s != Status::ok) return s;
    BudgetScope scope(&budget_);
    std::set<std::string> names;
    archive_entry* raw = nullptr;
    int code;
    while ((code = archive_read_next_header(decoder_, &raw)) != ARCHIVE_EOF) {
      if (code != ARCHIVE_OK) return stop(status(code));
      if (entries_.size() >= limits.maxEntries) return stop(Status::limits);
      Entry entry;
      if (const Status s = describe(raw, entry); s != Status::ok) return stop(s);
      if (!names.insert(entry.name).second) { problem_ = "duplicate"; return stop(Status::invalid); }
      if (entries_.size() >= checksums_.size()) return stop(Status::invalid);
      if (entry.size != checksums_[entries_.size()].size) return stop(Status::invalid);
      entry.hasCRC = checksums_[entries_.size()].hasCRC;
      entry.crc = checksums_[entries_.size()].crc;
      entries_.push_back(std::move(entry));
      code = entries_.back().directory ? archive_read_data_skip(decoder_) : skipEntry();
      if (code != ARCHIVE_OK) return stop(status(code));
    }
    closeDecoder();
    return entries_.empty() || entries_.size() != checksums_.size() ? Status::invalid : Status::ok;
  }

  const std::vector<Entry>& entries() const { return entries_; }
  const std::string& problem() const { return problem_; }
  uint64_t peakDecoderBytes() const { return budget_.peak; }
  uint64_t decoderBytesOutstanding() const { return budget_.used; }

  Status extractAll(const std::function<std::string(const Entry&)>& destination, const Progress& progress) {
    progress_ = progress;
    if (const Status s = openDecoder(); s != Status::ok) return s;
    BudgetScope scope(&budget_);
    archive_entry* raw = nullptr;
    const size_t chunk = 256 * 1024;
    std::unique_ptr<unsigned char[]> output(new unsigned char[chunk]);
    size_t index = 0;
    int code;
    while ((code = archive_read_next_header(decoder_, &raw)) != ARCHIVE_EOF) {
      if (code != ARCHIVE_OK) return stop(status(code));
      if (index >= entries_.size()) return stop(Status::invalid);
      Entry entry;
      if (const Status s = describe(raw, entry); s != Status::ok) return stop(s);
      const Entry& expected = entries_[index++];
      if (entry.name != expected.name || entry.size != expected.size || entry.directory != expected.directory)
        return stop(Status::invalid);
      const std::string path = entry.directory ? std::string() : destination(expected);
      if (path.empty()) {
        code = entry.directory ? archive_read_data_skip(decoder_) : skipEntry();
        if (code != ARCHIVE_OK) return stop(status(code));
        continue;
      }
      if (entry.size > limits_.maxFile) return stop(Status::limits);
      Output out(path);
      if (!out.good()) return stop(Status::io);
      uint64_t written = 0;
      const Checksum& checksum = checksums_[index - 1];
      uLong crc = crc32(0L, Z_NULL, 0);
      blake2sp_state blake{};
      if (checksum.hasBlake && blake2sp_init(&blake, 32) != 0) return stop(Status::invalid);
      for (;;) {
        const la_ssize_t n = archive_read_data(decoder_, output.get(), chunk);
        if (n < 0) return stop(status(int(n)));
        if (progress_ && !progress_(0)) { cancelled_ = true; return stop(Status::cancelled); }
        if (!n) break;
        if (uint64_t(n) > entry.size - written) return stop(Status::invalid);
        if (!out.write(output.get(), size_t(n))) return stop(Status::io);
        written += uint64_t(n);
        if (checksum.hasCRC) crc = crc32(crc, output.get(), uInt(n));
        if (checksum.hasBlake && blake2sp_update(&blake, output.get(), size_t(n)) != 0) return stop(Status::invalid);
      }
      if (written != entry.size) return stop(Status::invalid);
      // Independently verify every declared checksum, including stored members.
      // Upstream RAR5's stored path can finish without its checksum finalizer.
      if (checksum.hasCRC && uint32_t(crc) != checksum.crc) return stop(Status::crc);
      if (checksum.hasBlake) {
        std::array<unsigned char, 32> digest{};
        if (blake2sp_final(&blake, digest.data(), digest.size()) != 0 || digest != checksum.blake) return stop(Status::crc);
      }
      if (!out.commit()) return stop(Status::io);
    }
    if (index != entries_.size()) return stop(Status::invalid);
    closeDecoder();
    return Status::ok;
  }

 private:
  struct Checksum {
    bool hasCRC = false, hasBlake = false;
    uint32_t crc = 0;
    uint64_t size = 0;
    std::array<unsigned char, 32> blake{};
  };

  struct BudgetScope {
    NeoTexRARBudget* previous;
    explicit BudgetScope(NeoTexRARBudget* budget) : previous(NeoTexRARUseBudget(budget)) {}
    ~BudgetScope() { NeoTexRARUseBudget(previous); }
  };

  static bool vint(const unsigned char* data, size_t size, size_t& at, uint64_t& value) {
    value = 0;
    for (unsigned i = 0; i < 10 && at < size; ++i) {
      const unsigned char b = data[at++];
      if (i == 9 && (b & 0xfe)) return false;
      value |= uint64_t(b & 0x7f) << (i * 7);
      if (!(b & 0x80)) return true;
    }
    return false;
  }

  // Read only bounded headers and skip compressed byte ranges. No decoding or
  // archive rewriting. This independently preserves checksum metadata that the
  // generic libarchive entry API does not expose (CRC32 zero is valid too).
  Status scanChecksums() {
    unsigned char magic[8]{};
    if (!file_->read(0, magic, std::min<uint64_t>(8, file_->length()))) return Status::io;
    const bool version5 = magic[6] == 1;
    uint64_t offset = version5 ? 8 : 7;
    uint64_t totalUnpacked = 0, headerCount = 0;
    auto account = [&](uint64_t size) {
      if (size > limits_.maxTotal || totalUnpacked > limits_.maxTotal - size) return false;
      totalUnpacked += size;
      return true;
    };
    while (offset < file_->length()) {
      if (++headerCount > uint64_t(limits_.maxEntries) + 2) return Status::limits;
      if (progress_ && !progress_(0)) { cancelled_ = true; return Status::cancelled; }
      const uint64_t remaining = file_->length() - offset;
      if (remaining < 7) return Status::invalid;
      unsigned char first[14]{};
      const size_t firstSize = size_t(std::min<uint64_t>(sizeof(first), remaining));
      if (!file_->read(offset, first, firstSize)) return Status::io;
      uint64_t headerSize = 0, packed = 0;
      size_t lengthBytes = 0;
      if (version5) {
        size_t at = 4;
        uint64_t bodySize;
        if (!vint(first, firstSize, at, bodySize)) return Status::invalid;
        lengthBytes = at - 4;
        if (bodySize > (1ULL << 20)) return Status::limits;
        headerSize = at + bodySize;
      } else {
        headerSize = U16(first + 5);
      }
      if (headerSize < 7 || headerSize > remaining) return Status::invalid;
      std::vector<unsigned char> header(size_t(headerSize), 0);
      if (!file_->read(offset, header.data(), header.size())) return Status::io;
      if (version5) {
        if (uint32_t(crc32(0L, header.data() + 4, uInt(header.size() - 4))) != U32(header.data())) return Status::crc;
        size_t at = 4 + lengthBytes;
        uint64_t type, flags, extra = 0;
        if (!vint(header.data(),header.size(),at,type) || !vint(header.data(),header.size(),at,flags)) return Status::invalid;
        if ((flags & 1) && !vint(header.data(),header.size(),at,extra)) return Status::invalid;
        if ((flags & 2) && !vint(header.data(),header.size(),at,packed)) return Status::invalid;
        if (flags & (8 | 16)) { problem_ = "multipart"; return Status::unsupported; }
        if (extra > header.size() - at) return Status::invalid;
        if (type == 4) { problem_ = "encrypted"; return Status::unsupported; }
        if (type == 1) {
          uint64_t archiveFlags;
          if (!vint(header.data(),header.size(),at,archiveFlags)) return Status::invalid;
          if (archiveFlags & 1) { problem_ = "multipart"; return Status::unsupported; }
        } else if (type == 2 || type == 3) {
          if (checksums_.size() >= limits_.maxEntries) return Status::limits;
          Checksum checksum;
          uint64_t fileFlags, unpacked, attributes, compression, host, nameSize;
          if (!vint(header.data(),header.size(),at,fileFlags) || !vint(header.data(),header.size(),at,unpacked) ||
              !vint(header.data(),header.size(),at,attributes)) return Status::invalid;
          if (fileFlags & 8) return Status::unsupported;
          if (!account(unpacked)) return Status::limits;
          checksum.size = unpacked;
          if (fileFlags & 2) { if (header.size() - at < 4) return Status::invalid; at += 4; }
          if (fileFlags & 4) {
            if (header.size() - at < 4) return Status::invalid;
            checksum.hasCRC = true; checksum.crc = U32(header.data() + at); at += 4;
          }
          if (!vint(header.data(),header.size(),at,compression) || !vint(header.data(),header.size(),at,host) ||
              !vint(header.data(),header.size(),at,nameSize)) return Status::invalid;
          if (nameSize > limits_.maxName) return Status::limits;
          if (nameSize > header.size() - at || at + nameSize > header.size() - size_t(extra)) return Status::invalid;
          for (size_t i = 0; i < nameSize; ++i) if (header[at + i] == 0) return Status::invalid;
          at = header.size() - size_t(extra);
          while (at < header.size()) {
            uint64_t fieldSize, fieldType;
            if (!vint(header.data(),header.size(),at,fieldSize) || !fieldSize || fieldSize > header.size() - at) return Status::invalid;
            const size_t end = at + size_t(fieldSize);
            if (!vint(header.data(),end,at,fieldType)) return Status::invalid;
            if (fieldType == 1) { problem_ = "encrypted"; return Status::unsupported; }
            if (fieldType == 2) {
              uint64_t hashType;
              if (!vint(header.data(),end,at,hashType) || hashType != 0 || end - at != 32) return Status::unsupported;
              checksum.hasBlake = true;
              std::copy_n(header.data() + at, 32, checksum.blake.begin());
            }
            at = end;
          }
          if (type == 2) checksums_.push_back(checksum);
        } else if (type == 5) {
          uint64_t endFlags;
          if (!vint(header.data(),header.size(),at,endFlags)) return Status::invalid;
          if (endFlags & 1) { problem_ = "multipart"; return Status::unsupported; }
          return Status::ok;
        }
      } else {
        if (uint16_t(crc32(0L, header.data() + 2, uInt(header.size() - 2))) != U16(header.data())) return Status::crc;
        const unsigned char type = header[2];
        const uint16_t flags = U16(header.data() + 3);
        if (flags & 0x8000) {
          if (header.size() < 11) return Status::invalid;
          packed = U32(header.data() + 7);
        }
        if (type == 0x74) {
          if (checksums_.size() >= limits_.maxEntries) return Status::limits;
          if (header.size() < 32) return Status::invalid;
          if (flags & 3) { problem_ = "multipart"; return Status::unsupported; }
          if (flags & 4) { problem_ = "encrypted"; return Status::unsupported; }
          if (flags & 0x100) {
            if (header.size() < 40) return Status::invalid;
            packed |= uint64_t(U32(header.data() + 32)) << 32;
          }
          Checksum checksum;
          checksum.hasCRC = true; checksum.crc = U32(header.data() + 16);
          checksum.size = U32(header.data() + 11);
          if (flags & 0x100) checksum.size |= uint64_t(U32(header.data() + 36)) << 32;
          if (!account(checksum.size)) return Status::limits;
          checksums_.push_back(checksum);
        } else if (type == 0x7b) {
          if (flags & 1) { problem_ = "multipart"; return Status::unsupported; }
          return Status::ok;
        }
      }
      if (packed > remaining - headerSize) return Status::invalid;
      offset += headerSize + packed;
    }
    return Status::invalid; // A missing end-of-archive header is not a complete pack.
  }

  Status preflight() {
    unsigned char header[128]{};
    const size_t size = size_t(std::min<uint64_t>(sizeof(header), file_->length()));
    if (size < 14 || !file_->read(0, header, size)) return Status::invalid;
    static const unsigned char rar4[] = {'R','a','r','!',0x1a,7,0};
    static const unsigned char rar5[] = {'R','a','r','!',0x1a,7,1,0};
    if (!std::memcmp(header, rar4, sizeof(rar4))) {
      if (header[9] != 0x73) return Status::invalid;
      const uint16_t flags = U16(header + 10);
      if (flags & 1) { problem_ = "multipart"; return Status::unsupported; }
      if (flags & 0x80) { problem_ = "encrypted"; return Status::unsupported; }
      return Status::ok;
    }
    if (!std::memcmp(header, rar5, sizeof(rar5))) {
      size_t at = 12;
      uint64_t bytes, type, flags, unused, archiveFlags;
      if (!vint(header,size,at,bytes) || !vint(header,size,at,type) || !vint(header,size,at,flags)) return Status::invalid;
      if (type == 4) { problem_ = "encrypted"; return Status::unsupported; }
      if (type != 1) return Status::invalid;
      if ((flags & 1) && !vint(header,size,at,unused)) return Status::invalid;
      if ((flags & 2) && !vint(header,size,at,unused)) return Status::invalid;
      if (!vint(header,size,at,archiveFlags)) return Status::invalid;
      if (archiveFlags & 1) { problem_ = "multipart"; return Status::unsupported; }
      solid_ = (archiveFlags & 4) != 0;
      return Status::ok;
    }
    return Status::invalid; // Self-extracting executables are not texture archives.
  }

  Status describe(archive_entry* raw, Entry& entry) {
    const char* name = archive_entry_pathname_utf8(raw);
    if (!name) name = archive_entry_pathname(raw);
    if (!name) return Status::invalid;
    const size_t length = strnlen(name, size_t(limits_.maxName) + 1);
    if (!length || length > limits_.maxName) return Status::limits;
    entry.raw.assign(name, length);
    entry.name = NormalizeName(entry.raw, &entry.directory);
    if (entry.name.empty() || !ValidUTF8(entry.name)) return Status::invalid;
    const mode_t type = archive_entry_filetype(raw);
    entry.directory = entry.directory || type == AE_IFDIR;
    entry.link = archive_entry_symlink(raw) || archive_entry_hardlink(raw) || type == AE_IFLNK;
    entry.encrypted = archive_entry_is_encrypted(raw) > 0;
    entry.hasCRC = false; // CRC32/BLAKE2 is checked by the decoder's data path.
    if (entry.link || (!entry.directory && type != AE_IFREG)) { problem_ = "link"; return Status::unsupported; }
    if (entry.encrypted) { problem_ = "encrypted"; return Status::unsupported; }
    const la_int64_t size = archive_entry_size(raw);
    if (size < 0 || (!entry.directory && !archive_entry_size_is_set(raw))) return Status::invalid;
    entry.size = uint64_t(size);
    entry.supported = entry.size <= limits_.maxFile;
    return entry.supported || entry.directory ? Status::ok : Status::limits;
  }

  Status openDecoder() {
    closeDecoder();
    BudgetScope scope(&budget_);
    budget_.failed = 0; cancelled_ = false; offset_ = 0;
    decoder_ = archive_read_new();
    if (!decoder_) return budget_.failed ? Status::limits : Status::io;
    if (archive_read_support_filter_none(decoder_) != ARCHIVE_OK ||
        archive_read_support_format_rar(decoder_) != ARCHIVE_OK ||
        archive_read_support_format_rar5(decoder_) != ARCHIVE_OK)
      return stop(budget_.failed ? Status::limits : Status::unsupported);
    const int code = archive_read_open2(decoder_, this, nullptr, readBlock, skipBlock, nullptr);
    if (code != ARCHIVE_OK) return stop(status(code));
    return Status::ok;
  }

  int skipEntry() {
    if (!solid_) return archive_read_data_skip(decoder_);
    // RAR5 solid skipping must decode prior members. Pull bounded output
    // chunks ourselves so a tiny compressed stream cannot starve cancellation.
    std::array<unsigned char, 64 * 1024> discarded{};
    for (;;) {
      const la_ssize_t count = archive_read_data(decoder_, discarded.data(), discarded.size());
      if (count < 0) return int(count);
      if (progress_ && !progress_(0)) { cancelled_ = true; return ARCHIVE_FATAL; }
      if (!count) return ARCHIVE_OK;
    }
  }

  void closeDecoder() {
    if (decoder_) {
      BudgetScope scope(&budget_);
      archive_read_free(decoder_);
      decoder_ = nullptr;
    }
  }
  Status stop(Status result) { closeDecoder(); return result; }
  Status status(int) {
    if (cancelled_) return Status::cancelled;
    if (budget_.failed) { problem_ = "memory"; return Status::limits; }
    const std::string error = decoder_ && archive_error_string(decoder_) ? archive_error_string(decoder_) : "";
    if (error.find("CRC") != std::string::npos || error.find("checksum") != std::string::npos || error.find("Checksum") != std::string::npos)
      return Status::crc;
    if (error.find("encrypt") != std::string::npos || error.find("passphrase") != std::string::npos) {
      problem_ = "encrypted"; return Status::unsupported;
    }
    if (error.find("solid archive support unavailable") != std::string::npos) {
      problem_ = "rar4Solid"; return Status::unsupported;
    }
    if (error.find("Unsupported") != std::string::npos || error.find("unsupported") != std::string::npos) return Status::unsupported;
    return Status::invalid;
  }

  bool advance(uint64_t amount) {
    if (progress_ && !progress_(amount)) { cancelled_ = true; return false; }
    offset_ += amount;
    return true;
  }
  static la_ssize_t readBlock(archive* decoder, void* context, const void** block) {
    Rar* self = static_cast<Rar*>(context);
    const size_t count = size_t(std::min<uint64_t>(self->input_.size(), self->file_->length() - self->offset_));
    if (!count) return 0;
    if (!self->file_->read(self->offset_, self->input_.data(), count)) { archive_set_error(decoder, EIO, "read failed"); return -1; }
    if (!self->advance(count)) { archive_set_error(decoder, ECANCELED, "cancelled"); return -1; }
    *block = self->input_.data();
    return la_ssize_t(count);
  }
  static la_int64_t skipBlock(archive* decoder, void* context, la_int64_t request) {
    Rar* self = static_cast<Rar*>(context);
    if (request <= 0) return 0;
    const uint64_t count = std::min<uint64_t>(uint64_t(request), self->file_->length() - self->offset_);
    if (!self->advance(count)) { archive_set_error(decoder, ECANCELED, "cancelled"); return -1; }
    return la_int64_t(count);
  }

  std::unique_ptr<File> file_ = std::make_unique<File>();
  archive* decoder_ = nullptr;
  NeoTexRARBudget budget_{};
  std::vector<Entry> entries_;
  std::vector<Checksum> checksums_;
  Limits limits_;
  Progress progress_;
  uint64_t offset_ = 0;
  std::array<unsigned char, 64 * 1024> input_{};
  std::string problem_;
  bool cancelled_ = false, solid_ = false;
};
}  // namespace NeoTextureArchive
