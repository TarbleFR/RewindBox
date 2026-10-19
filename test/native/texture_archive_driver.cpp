// Host driver for NeoTextureArchive: lists an archive and extracts every
// supported regular entry below an output directory. Exit codes: 0 ok,
// 2 open failed, 3 extraction failed, 4 cancelled. Prints one line per entry
// so the Python test can compare the listing.
#include "NeoTextureArchive.h"
#include "NeoTextureSevenZip.h"
#include <cstdio>
#include <string>
int main(int argc, char** argv) {
  if (argc < 4) return 64;
  const std::string kind = argv[1], archive = argv[2], output = argv[3];
  const uint64_t cancelAfter = argc > 4 ? std::stoull(argv[4]) : 0;
  NeoTextureArchive::Limits limits;
  if (argc > 5) limits.maxDictionary = std::stoull(argv[5]);
  if (argc > 6) limits.maxFile = std::stoull(argv[6]);
  uint64_t consumed = 0;
  auto progress = [&](uint64_t n) { consumed += n; return !(cancelAfter && consumed >= cancelAfter); };
  auto run = [&](auto& reader) {
    const auto status = reader.open(archive, limits);
    if (status != NeoTextureArchive::Status::ok) { std::printf("open %s\n", NeoTextureArchive::StatusName(status)); return 2; }
    for (const auto& e : reader.entries())
      std::printf("entry %s size=%llu dir=%d link=%d enc=%d supported=%d\n", e.name.c_str(), (unsigned long long)e.size,
                  e.directory, e.link, e.encrypted, e.supported);
    bool parentsFailed = false;
    const auto result = reader.extractAll([&](const NeoTextureArchive::Entry& e) -> std::string {
      if (e.name.find("skip-") != std::string::npos) return {};
      const std::string path = output + "/" + e.name;
      if (!NeoTextureArchive::MakeParents(output, path)) { parentsFailed = true; return {}; }
      return path;
    }, progress);
    if (parentsFailed) { std::printf("parents failed\n"); return 3; }
    if (result == NeoTextureArchive::Status::cancelled) { std::printf("cancelled\n"); return 4; }
    if (result != NeoTextureArchive::Status::ok) { std::printf("extract %s\n", NeoTextureArchive::StatusName(result)); return 3; }
    std::printf("consumed %llu\n", (unsigned long long)consumed);
    return 0;
  };
  if (kind == "zip") { NeoTextureArchive::Zip zip; return run(zip); }
  if (kind == "7z") { NeoTextureArchive::SevenZip archive7z; return run(archive7z); }
  return 64;
}
