// SPDX-License-Identifier: GPL-3.0-or-later
#include "NeoTextureRAR.h"
#include <cstdio>
int main(int argc, char** argv) {
  if (argc < 3) return 64;
  const std::string input = argv[1], root = argv[2];
  NeoTextureArchive::Limits limits;
  if (argc > 3) limits.maxDictionary = std::stoull(argv[3]);
  if (argc > 4) limits.maxFile = std::stoull(argv[4]);
  if (argc > 5) limits.maxEntries = std::stoul(argv[5]);
  if (argc > 7) limits.maxTotal = std::stoull(argv[7]);
  uint64_t consumed = 0;
  const uint64_t cancel = argc > 6 ? std::stoull(argv[6]) : 0;
  const uint64_t zeroCancel = argc > 8 ? std::stoull(argv[8]) : 0;
  uint64_t zeroPolls = 0;
  auto progress = [&](uint64_t n) {
    consumed += n;
    if (!n && zeroCancel && ++zeroPolls >= zeroCancel) return false;
    return !cancel || consumed < cancel;
  };
  NeoTextureArchive::Rar reader;
  auto status = reader.open(input, limits, progress);
  if (status == NeoTextureArchive::Status::ok) {
    status = reader.extractAll([&](const NeoTextureArchive::Entry& entry) {
      if (entry.name.find("skip-") != std::string::npos) return std::string();
      const std::string path = root + "/" + entry.name;
      if (!NeoTextureArchive::MakeParents(root, path)) return std::string();
      return path;
    }, progress);
  }
  std::printf("status=%s problem=%s entries=%zu peak=%llu consumed=%llu\n", NeoTextureArchive::StatusName(status),
    reader.problem().c_str(), reader.entries().size(), (unsigned long long)reader.peakDecoderBytes(), (unsigned long long)consumed);
  if (reader.decoderBytesOutstanding()) return 2;
  return status == NeoTextureArchive::Status::ok ? 0 : 1;
}
