// SPDX-License-Identifier: GPL-3.0-or-later
// Streaming 7z reader for HD texture packs.
//
// The vendored LZMA SDK (public domain, 24.09) parses the archive database.
// Its own folder decoder expands a whole solid block into one memory buffer,
// which for a texture pack can be several GiB. Here a solid block is decoded
// through fixed buffers and split into its files as the bytes arrive; the
// only large allocation is the LZMA window, bounded by the block's expanded
// size and by Limits::maxDictionary. Supported blocks have one coder: Copy,
// LZMA, LZMA2 or Deflate. Filters (BCJ...), PPMd, BZip2 and encrypted blocks
// are reported as unsupported instead of being guessed.
#pragma once
#include "NeoTextureArchive.h"
#include <cstdlib>
#include <map>

extern "C" {
#include "7z.h"
#include "7zCrc.h"
#include "LzmaDec.h"
#include "Lzma2Dec.h"
}

namespace NeoTextureArchive {

namespace SevenZipDetail {
struct CappedAlloc {
  ISzAlloc vt;
  size_t cap;
};
inline void* Allocate(ISzAllocPtr p, size_t size) {
  const auto* self = reinterpret_cast<const CappedAlloc*>(p);
  if (size > self->cap) return nullptr;
  return std::malloc(size ? size : 1);
}
inline void Release(ISzAllocPtr, void* address) { std::free(address); }

struct Stream {
  ISeekInStream vt;
  const File* file;
  uint64_t position;
};
inline SRes Read(ISeekInStreamPtr p, void* buffer, size_t* size) {
  auto* self = reinterpret_cast<Stream*>(const_cast<ISeekInStream*>(p));
  const uint64_t length = self->file->length();
  const uint64_t left = self->position < length ? length - self->position : 0;
  const size_t n = static_cast<size_t>(std::min<uint64_t>(*size, left));
  if (n && !self->file->read(self->position, buffer, n)) { *size = 0; return SZ_ERROR_READ; }
  self->position += n;
  *size = n;
  return SZ_OK;
}
inline SRes Seek(ISeekInStreamPtr p, Int64* position, ESzSeek origin) {
  auto* self = reinterpret_cast<Stream*>(const_cast<ISeekInStream*>(p));
  Int64 base = origin == SZ_SEEK_SET ? 0 : origin == SZ_SEEK_CUR ? Int64(self->position) : Int64(self->file->length());
  const Int64 target = base + *position;
  if (target < 0) return SZ_ERROR_PARAM;
  self->position = uint64_t(target);
  *position = target;
  return SZ_OK;
}

inline std::string UTF8(const std::vector<UInt16>& name) {
  std::string out;
  for (size_t i = 0; i < name.size() && name[i]; ++i) {
    uint32_t c = name[i];
    if (c >= 0xd800 && c <= 0xdbff) {
      if (i + 1 >= name.size() || name[i + 1] < 0xdc00 || name[i + 1] > 0xdfff) return {};
      c = 0x10000 + ((c - 0xd800) << 10) + (name[++i] - 0xdc00);
    } else if (c >= 0xdc00 && c <= 0xdfff) {
      return {};
    }
    if (c < 0x80) out += char(c);
    else if (c < 0x800) { out += char(0xc0 | (c >> 6)); out += char(0x80 | (c & 0x3f)); }
    else if (c < 0x10000) { out += char(0xe0 | (c >> 12)); out += char(0x80 | ((c >> 6) & 0x3f)); out += char(0x80 | (c & 0x3f)); }
    else { out += char(0xf0 | (c >> 18)); out += char(0x80 | ((c >> 12) & 0x3f)); out += char(0x80 | ((c >> 6) & 0x3f)); out += char(0x80 | (c & 0x3f)); }
  }
  return out;
}
}  // namespace SevenZipDetail

class SevenZip {
 public:
  static constexpr uint32_t kCopy = 0, kLZMA = 0x030101, kLZMA2 = 0x21, kDeflate = 0x040108, kAES = 0x06F10701;

  SevenZip() {
    alloc_.vt.Alloc = SevenZipDetail::Allocate;
    alloc_.vt.Free = SevenZipDetail::Release;
    alloc_.cap = 256u << 20;
    SzArEx_Init(&db_);
  }
  SevenZip(const SevenZip&) = delete;
  SevenZip& operator=(const SevenZip&) = delete;
  ~SevenZip() { SzArEx_Free(&db_, &alloc_.vt); }

  Status open(const std::string& path, const Limits& limits = {}) {
    limits_ = limits;
    entries_.clear();
    folders_.clear();
    SzArEx_Free(&db_, &alloc_.vt);
    SzArEx_Init(&db_);
    if (!file_.open(path)) return Status::io;
    if (file_.length() > limits.maxArchive) return Status::limits;
    unsigned char signature[32];
    if (!file_.read(0, signature, sizeof(signature))) return Status::invalid;
    static const unsigned char magic[6] = {'7', 'z', 0xbc, 0xaf, 0x27, 0x1c};
    if (std::memcmp(signature, magic, 6) != 0) return Status::invalid;
    // The header itself must stay small: it only names and sizes the files.
    if (U64(signature + 20) > (64ull << 20)) return Status::limits;
    stream_.vt.Read = SevenZipDetail::Read;
    stream_.vt.Seek = SevenZipDetail::Seek;
    stream_.file = &file_;
    stream_.position = 0;
    lookBuffer_.reset(new Byte[1 << 16]);
    LookToRead2_CreateVTable(&look_, False);
    look_.buf = lookBuffer_.get();
    look_.bufSize = 1 << 16;
    look_.realStream = &stream_.vt;
    LookToRead2_INIT(&look_);
    static const bool crcReady = [] { CrcGenerateTable(); return true; }();
    (void)crcReady;
    const SRes opened = SzArEx_Open(&db_, &look_.vt, &alloc_.vt, &alloc_.vt);
    if (opened == SZ_ERROR_UNSUPPORTED) return Status::unsupported;
    if (opened == SZ_ERROR_MEM) return Status::limits;
    if (opened != SZ_OK) return Status::invalid;
    if (db_.NumFiles > limits.maxEntries) return Status::limits;
    folders_.resize(db_.db.NumFolders);
    for (UInt32 f = 0; f < db_.db.NumFolders; ++f) describeFolder(f);
    std::vector<UInt16> name;
    entries_.reserve(db_.NumFiles);
    for (UInt32 i = 0; i < db_.NumFiles; ++i) {
      const size_t length = SzArEx_GetFileNameUtf16(&db_, i, nullptr);
      if (length == 0 || length > limits.maxName + 1) return Status::limits;
      name.assign(length, 0);
      SzArEx_GetFileNameUtf16(&db_, i, name.data());
      Entry entry;
      entry.raw = SevenZipDetail::UTF8(name);
      bool trailing = false;
      entry.name = NormalizeName(entry.raw, &trailing);
      if (entry.name.empty()) return Status::invalid;
      entry.directory = trailing || SzArEx_IsDir(&db_, i);
      entry.size = SzArEx_GetFileSize(&db_, i);
      entry.hasCRC = SzBitWithVals_Check(&db_.CRCs, i);
      entry.crc = entry.hasCRC ? db_.CRCs.Vals[i] : 0;
      if (SzBitWithVals_Check(&db_.Attribs, i)) {
        const UInt32 attributes = db_.Attribs.Vals[i];
        // FILE_ATTRIBUTE_UNIX_EXTENSION carries st_mode in the high half.
        if ((attributes & 0x8000) && ((attributes >> 16) & 0170000) == 0120000) entry.link = true;
        if (attributes & 0x10) entry.directory = true;
      }
      entry.folder = db_.FileToFolder[i];
      if (entry.folder != UInt32(-1) && entry.folder < folders_.size()) {
        const Folder& folder = folders_[entry.folder];
        entry.folderOffset = db_.UnpackPositions[i] - db_.UnpackPositions[db_.FolderToFile[entry.folder]];
        entry.method = uint16_t(folder.method & 0xffff);
        entry.encrypted = folder.encrypted;
        entry.supported = folder.supported;
        entry.compressed = folder.packSize;
      } else {
        entry.folder = UINT32_MAX;
        entry.supported = entry.size == 0;
      }
      if (entry.link) entry.supported = false;
      if (!entry.directory && entry.size > limits.maxFile) entry.supported = false;
      entries_.push_back(std::move(entry));
    }
    return Status::ok;
  }

  const std::vector<Entry>& entries() const { return entries_; }

  // Largest LZMA window a wanted block would allocate (0 when none).
  uint64_t dictionaryFor(const Entry& entry) const {
    return entry.folder < folders_.size() ? folders_[entry.folder].window : 0;
  }

  Status extractAll(const std::function<std::string(const Entry&)>& destination, const Progress& progress) {
    std::vector<std::string> paths(entries_.size());
    std::vector<bool> wanted(folders_.size(), false);
    for (size_t i = 0; i < entries_.size(); ++i) {
      const Entry& entry = entries_[i];
      if (entry.directory) continue;
      paths[i] = destination(entry);
      if (paths[i].empty()) continue;
      if (!entry.supported) {
        if (entry.size > limits_.maxFile) return Status::limits;
        if (entry.folder < folders_.size() && folders_[entry.folder].window > limits_.maxDictionary) return Status::limits;
        return Status::unsupported;
      }
      if (entry.folder == UINT32_MAX) {
        Output out(paths[i]);
        if (!out.good() || !out.commit()) return Status::io;
        continue;
      }
      wanted[entry.folder] = true;
    }
    for (UInt32 f = 0; f < folders_.size(); ++f) {
      if (!wanted[f]) continue;
      if (folders_[f].window > limits_.maxDictionary) return Status::limits;
      const Status status = decodeFolder(f, paths, progress);
      if (status != Status::ok) return status;
    }
    return Status::ok;
  }

 private:
  struct Folder {
    uint32_t method = 0;
    uint64_t packAt = 0, packSize = 0, unpackSize = 0, window = 0;
    std::vector<Byte> props;
    bool supported = false, encrypted = false;
  };

  void describeFolder(UInt32 f) {
    Folder& folder = folders_[f];
    CSzFolder parsed;
    CSzData data;
    data.Data = db_.db.CodersData + db_.db.FoCodersOffsets[f];
    data.Size = db_.db.FoCodersOffsets[f + 1] - db_.db.FoCodersOffsets[f];
    const Byte* base = data.Data;
    if (SzGetNextFolderItem(&parsed, &data) != SZ_OK || data.Size != 0) return;
    for (UInt32 c = 0; c < parsed.NumCoders; ++c)
      if (parsed.Coders[c].MethodID == kAES) folder.encrypted = true;
    if (parsed.NumCoders != 1 || parsed.NumPackStreams != 1 || parsed.NumBonds != 0 || parsed.Coders[0].NumStreams != 1) return;
    const CSzCoderInfo& coder = parsed.Coders[0];
    folder.method = coder.MethodID;
    folder.props.assign(base + coder.PropsOffset, base + coder.PropsOffset + coder.PropsSize);
    const UInt32 start = db_.db.FoStartPackStreamIndex[f];
    folder.packAt = db_.dataPos + db_.db.PackPositions[start];
    folder.packSize = db_.db.PackPositions[start + 1] - db_.db.PackPositions[start];
    folder.unpackSize = SzAr_GetFolderUnpackSize(&db_.db, f);
    if (folder.packAt > file_.length() || folder.packSize > file_.length() - folder.packAt) return;
    const uint64_t floor = std::max<uint64_t>(folder.unpackSize, 4096);
    switch (folder.method) {
      case kCopy:
        folder.supported = folder.packSize == folder.unpackSize;
        break;
      case kDeflate:
        folder.supported = true;
        break;
      case kLZMA: {
        if (folder.props.size() != LZMA_PROPS_SIZE) return;
        const uint64_t dictionary = std::max<uint64_t>(U32(folder.props.data() + 1), 4096);
        folder.window = std::min(dictionary, floor);
        folder.supported = true;
        break;
      }
      case kLZMA2: {
        if (folder.props.size() != 1 || folder.props[0] > 40) return;
        const Byte prop = folder.props[0];
        const uint64_t dictionary = prop == 40 ? 0xffffffffull : (uint64_t(2 | (prop & 1)) << (prop / 2 + 11));
        folder.window = std::min(dictionary, floor);
        folder.supported = true;
        break;
      }
      default:
        break;
    }
  }

  // Sends the bytes of one solid block, in order, to the files it contains.
  // Unwanted files are decoded and discarded; once the last wanted file of
  // the block is complete the caller may stop decoding.
  class Splitter {
   public:
    Splitter(SevenZip& owner, UInt32 folder, const std::vector<std::string>& paths) : owner_(owner), paths_(paths) {
      for (UInt32 i = owner.db_.FolderToFile[folder]; i < owner.db_.NumFiles; ++i) {
        const UInt32 owned = owner.db_.FileToFolder[i];
        if (owned == folder) files_.push_back(i);
        else if (owned != UInt32(-1)) break;
      }
      for (size_t k = 0; k < files_.size(); ++k)
        if (!paths_[files_[k]].empty()) lastWanted_ = k;
      folderCRC_ = crc32(0L, Z_NULL, 0);
    }
    Status write(const unsigned char* bytes, size_t count) {
      folderCRC_ = crc32(folderCRC_, bytes, static_cast<uInt>(count));
      while (count) {
        if (const Status s = advance(); s != Status::ok) return s;
        if (index_ >= files_.size()) return Status::invalid;  // more bytes than files
        const size_t n = static_cast<size_t>(std::min<uint64_t>(remaining_, count));
        if (out_) {
          if (!out_->write(bytes, n)) return Status::io;
          crc_ = crc32(crc_, bytes, static_cast<uInt>(n));
        }
        bytes += n; count -= n; remaining_ -= n;
      }
      return Status::ok;
    }
    // Every file of the block received exactly its bytes.
    Status finish(UInt32 folder) {
      if (const Status s = advance(); s != Status::ok) return s;
      if (index_ < files_.size()) return Status::invalid;
      const auto& crcs = owner_.db_.db.FolderCRCs;
      if (SzBitWithVals_Check(&crcs, folder) && crcs.Vals[folder] != folderCRC_) return Status::crc;
      return Status::ok;
    }
    // The wanted files are all complete (the rest of the block may be skipped).
    bool satisfied() {
      if (lastWanted_ == SIZE_MAX) return true;
      if (advance() != Status::ok) return false;
      return index_ > lastWanted_;
    }

   private:
    // Opens the current file when needed and closes completed ones until the
    // current file still expects bytes, or no file remains.
    Status advance() {
      while (index_ < files_.size()) {
        if (!open_) {
          const UInt32 file = files_[index_];
          remaining_ = SzArEx_GetFileSize(&owner_.db_, file);
          crc_ = crc32(0L, Z_NULL, 0);
          const std::string& path = paths_[file];
          out_.reset(path.empty() ? nullptr : new Output(path));
          if (out_ && !out_->good()) return Status::io;
          open_ = true;
        }
        if (remaining_ > 0) return Status::ok;
        if (out_) {
          const Entry& entry = owner_.entries_[files_[index_]];
          if (entry.hasCRC && crc_ != entry.crc) return Status::crc;
          if (!out_->commit()) return Status::io;
          out_.reset();
        }
        ++index_;
        open_ = false;
      }
      return Status::ok;
    }
    SevenZip& owner_;
    const std::vector<std::string>& paths_;
    std::vector<UInt32> files_;
    size_t index_ = 0, lastWanted_ = SIZE_MAX;
    uint64_t remaining_ = 0;
    uLong crc_ = 0, folderCRC_ = 0;
    std::unique_ptr<Output> out_;
    bool open_ = false;
  };

  Status decodeFolder(UInt32 f, const std::vector<std::string>& paths, const Progress& progress) {
    const Folder& folder = folders_[f];
    if (!folder.supported) return Status::unsupported;
    Splitter splitter(*this, f, paths);
    std::unique_ptr<unsigned char[]> input(new unsigned char[kChunk]), output(new unsigned char[kChunk]);
    uint64_t packLeft = folder.packSize, unpackLeft = folder.unpackSize, at = folder.packAt;
    auto readInput = [&](size_t& length) -> Status {
      length = static_cast<size_t>(std::min<uint64_t>(packLeft, kChunk));
      if (length && !file_.read(at, input.get(), length)) return Status::io;
      at += length; packLeft -= length;
      if (length && progress && !progress(length)) return Status::cancelled;
      return Status::ok;
    };
    if (folder.method == kCopy) {
      while (unpackLeft) {
        size_t length = 0;
        if (const Status s = readInput(length); s != Status::ok) return s;
        if (!length) return Status::invalid;
        if (length > unpackLeft) return Status::invalid;
        if (const Status s = splitter.write(input.get(), length); s != Status::ok) return s;
        unpackLeft -= length;
        if (splitter.satisfied()) return Status::ok;
      }
      return splitter.finish(f);
    }
    if (folder.method == kDeflate) {
      z_stream stream{};
      if (inflateInit2(&stream, -MAX_WBITS) != Z_OK) return Status::io;
      struct Ender { z_stream* s; ~Ender() { inflateEnd(s); } } ender{&stream};
      bool ended = false;
      while (!ended) {
        size_t length = 0;
        if (const Status s = readInput(length); s != Status::ok) return s;
        if (!length) return Status::invalid;
        stream.next_in = input.get();
        stream.avail_in = static_cast<uInt>(length);
        do {
          stream.next_out = output.get();
          stream.avail_out = static_cast<uInt>(kChunk);
          const int status = inflate(&stream, Z_NO_FLUSH);
          if (status == Z_STREAM_END) ended = true;
          else if (status != Z_OK && status != Z_BUF_ERROR) return Status::invalid;
          const size_t written = kChunk - stream.avail_out;
          if (written > unpackLeft) return Status::invalid;
          unpackLeft -= written;
          if (written) if (const Status s = splitter.write(output.get(), written); s != Status::ok) return s;
          if (splitter.satisfied()) return Status::ok;
          if (ended) break;
          if (status == Z_BUF_ERROR && !written) { if (stream.avail_in) return Status::invalid; break; }
        } while (stream.avail_in || stream.avail_out == 0);
      }
      if (unpackLeft) return Status::invalid;
      return splitter.finish(f);
    }
    // LZMA / LZMA2 with a window no larger than the block itself.
    const bool lzma2 = folder.method == kLZMA2;
    CLzmaDec lzma;
    CLzma2Dec lzma2Decoder;
    LzmaDec_CONSTRUCT(&lzma);
    Lzma2Dec_CONSTRUCT(&lzma2Decoder);
    SRes allocated;
    if (lzma2) {
      Byte prop = folder.props[0];
      while (prop > 0) {
        const Byte smaller = Byte(prop - 1);
        const uint64_t size = uint64_t(2 | (smaller & 1)) << (smaller / 2 + 11);
        if (size < folder.window) break;
        prop = smaller;
      }
      allocated = Lzma2Dec_Allocate(&lzma2Decoder, prop, &alloc_.vt);
      if (allocated == SZ_OK) Lzma2Dec_Init(&lzma2Decoder);
    } else {
      Byte props[LZMA_PROPS_SIZE];
      std::memcpy(props, folder.props.data(), LZMA_PROPS_SIZE);
      const uint32_t window = static_cast<uint32_t>(folder.window);
      props[1] = Byte(window); props[2] = Byte(window >> 8); props[3] = Byte(window >> 16); props[4] = Byte(window >> 24);
      allocated = LzmaDec_Allocate(&lzma, props, LZMA_PROPS_SIZE, &alloc_.vt);
      if (allocated == SZ_OK) LzmaDec_Init(&lzma);
    }
    struct Freer {
      CLzmaDec* a; CLzma2Dec* b; ISzAllocPtr alloc;
      ~Freer() { LzmaDec_Free(a, alloc); Lzma2Dec_Free(b, alloc); }
    } freer{&lzma, &lzma2Decoder, &alloc_.vt};
    if (allocated == SZ_ERROR_MEM) return Status::limits;
    if (allocated != SZ_OK) return Status::unsupported;
    size_t length = 0, used = 0;
    while (unpackLeft) {
      if (used == length) {
        if (const Status s = readInput(length); s != Status::ok) return s;
        used = 0;
      }
      SizeT inSize = length - used;
      SizeT outSize = static_cast<SizeT>(std::min<uint64_t>(unpackLeft, kChunk));
      ELzmaStatus status;
      const ELzmaFinishMode finish = outSize == unpackLeft ? LZMA_FINISH_END : LZMA_FINISH_ANY;
      const SRes result = lzma2
        ? Lzma2Dec_DecodeToBuf(&lzma2Decoder, output.get(), &outSize, input.get() + used, &inSize, finish, &status)
        : LzmaDec_DecodeToBuf(&lzma, output.get(), &outSize, input.get() + used, &inSize, finish, &status);
      if (result != SZ_OK) return Status::invalid;
      used += inSize;
      if (outSize) {
        unpackLeft -= outSize;
        if (const Status s = splitter.write(output.get(), outSize); s != Status::ok) return s;
        if (splitter.satisfied()) return Status::ok;
      }
      if (!inSize && !outSize) {
        if (used == length && packLeft == 0) return Status::invalid;  // truncated block
        if (used < length) return Status::invalid;                     // no progress
      }
      if (status == LZMA_STATUS_FINISHED_WITH_MARK && unpackLeft) return Status::invalid;
    }
    return splitter.finish(f);
  }

  static constexpr size_t kChunk = 256 * 1024;
  File file_;
  SevenZipDetail::CappedAlloc alloc_{};
  SevenZipDetail::Stream stream_{};
  CLookToRead2 look_{};
  std::unique_ptr<Byte[]> lookBuffer_;
  CSzArEx db_{};
  std::vector<Entry> entries_;
  std::vector<Folder> folders_;
  Limits limits_;
};

}  // namespace NeoTextureArchive
