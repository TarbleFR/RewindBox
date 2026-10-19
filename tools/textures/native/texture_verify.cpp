// Catalogue verification driver (CI only, never shipped): runs the
// production installers of the HD textures catalogue on a real downloaded
// pack, exactly as the app does on iOS.
//
//   list <archive>
//       one line per entry: <size>\t<supported 0|1>\t<directory 0|1>\t<name>
//   detect <engine> <current> <archive>
//       NeoTextureInstall::Detect on the archive's names for the game folder
//       <current> (the store's own layout rules): prints problem, rules, IDs.
//   install <engine> <root> <archive> <from=to[!excluded/|...]>... | flat <from[!excluded/|...]>
//       NeoTextureInstall::ExtractArchive (dolphin, ppsspp, azahar), the
//       signature check and the commit into <root>/<to>; "flat": the folder an
//       engine with its own installer (ARMSX2) receives. Prints key=value.
//   armsx2 <dataRoot> <source> <serial> <sourceName> [move]
//       the Build 485 store's own pipeline (ARMSX2TexturePackCore.h:
//       OpenSource, BuildPlan, Judge, StageFiles, CommitStaged) on a ZIP, TAR
//       or folder, for the game <serial>; prints key=value.
#include "NeoTextureInstall.h"
#include "ARMSX2TexturePackCore.h"
#include <cstdio>
#include <iostream>

namespace I = NeoTextureInstall;
namespace A = NeoARMSX2Textures;

static I::Engine Parse(const std::string& s) {
  return s == "dolphin" ? I::Engine::dolphin : s == "armsx2" ? I::Engine::armsx2 : s == "ppsspp" ? I::Engine::ppsspp : s == "mupen64plus" ? I::Engine::mupen64plus : I::Engine::azahar;
}

static int List(const std::string& path) {
  unsigned char magic[6] = {0};
  NeoTextureArchive::File probe;
  if (!probe.open(path) || !probe.read(0, magic, std::min<uint64_t>(6, probe.length()))) { std::printf("error=io\n"); return 2; }
  auto dump = [](const auto& entries) {
    for (const auto& e : entries) std::printf("%llu\t%d\t%d\t%s\n", (unsigned long long)e.size, e.supported ? 1 : 0, e.directory ? 1 : 0, e.name.c_str());
  };
  NeoTextureArchive::Limits limits;
  if (!std::memcmp(magic, "7z\xbc\xaf\x27\x1c", 6)) {
    NeoTextureArchive::SevenZip reader;
    const auto status = reader.open(path, limits);
    if (status != NeoTextureArchive::Status::ok) { std::printf("error=%s\n", NeoTextureArchive::StatusName(status)); return 3; }
    dump(reader.entries());
  } else if (magic[0] == 'P' && magic[1] == 'K') {
    NeoTextureArchive::Zip reader;
    const auto status = reader.open(path, limits);
    if (status != NeoTextureArchive::Status::ok) { std::printf("error=%s\n", NeoTextureArchive::StatusName(status)); return 3; }
    dump(reader.entries());
  } else {
    std::printf("error=%s\n", !std::memcmp(magic, "Rar!", 4) ? "rar" : "format");
    return 4;
  }
  return 0;
}

static std::vector<std::string> Names(const std::string& path, std::string& error) {
  std::vector<std::string> names;
  unsigned char magic[6] = {0};
  NeoTextureArchive::File probe;
  if (!probe.open(path) || !probe.read(0, magic, std::min<uint64_t>(6, probe.length()))) { error = "io"; return names; }
  auto collect = [&](auto& reader) {
    const auto status = reader.open(path, NeoTextureArchive::Limits{});
    if (status != NeoTextureArchive::Status::ok) { error = NeoTextureArchive::StatusName(status); return; }
    for (const auto& entry : reader.entries()) if (!entry.directory) names.push_back(entry.name);
  };
  if (!std::memcmp(magic, "7z\xbc\xaf\x27\x1c", 6)) { NeoTextureArchive::SevenZip reader; collect(reader); }
  else if (magic[0] == 'P' && magic[1] == 'K') { NeoTextureArchive::Zip reader; collect(reader); }
  else error = !std::memcmp(magic, "Rar!", 4) ? "rar" : "format";
  return names;
}

static int Detect(int argc, char** argv) {
  if (argc < 5) return 64;
  std::string error;
  const std::vector<std::string> names = Names(argv[4], error);
  if (!error.empty()) { std::printf("error=%s\n", error.c_str()); return 3; }
  const I::Layout layout = I::Detect(Parse(argv[2]), names, argv[3]);
  std::printf("problem=%s\nother=%d\n", layout.problem.c_str(), layout.otherRegion ? 1 : 0);
  for (const auto& rule : layout.rules) std::printf("rule=%s\t%s\n", rule.from.c_str(), rule.to.c_str());
  for (const auto& id : layout.found) std::printf("found=%s\n", id.c_str());
  return layout.problem.empty() ? 0 : 1;
}

static int Install(int argc, char** argv) {
  if (argc < 6) return 64;
  const I::Engine engine = Parse(argv[2]);
  const std::string root = argv[3], archive = argv[4];
  const bool flat = std::string(argv[5]) == "flat";
  std::vector<I::Rule> rules;
  std::vector<std::string> targets;
  // "<rule>!a/|b/": the rule without the subfolders a/ and b/.
  auto split = [](const std::string& spec, std::vector<std::string>& exclude) {
    const size_t bang = spec.find('!');
    if (bang == std::string::npos) return spec;
    std::string rest = spec.substr(bang + 1);
    for (size_t at = 0; at <= rest.size();) {
      const size_t bar = rest.find('|', at);
      const std::string item = rest.substr(at, bar == std::string::npos ? std::string::npos : bar - at);
      if (!item.empty()) exclude.push_back(item);
      if (bar == std::string::npos) break;
      at = bar + 1;
    }
    return spec.substr(0, bang);
  };
  if (flat) {
    if (argc < 7) return 64;
    I::Rule rule;
    rule.from = split(argv[6], rule.exclude);
    rules.push_back(rule);
  } else {
    for (int i = 5; i < argc; ++i) {
      I::Rule rule;
      const std::string spec = split(argv[i], rule.exclude);
      const size_t equals = spec.find('=');
      if (equals == std::string::npos) return 64;
      rule.from = spec.substr(0, equals);
      rule.to = spec.substr(equals + 1);
      rules.push_back(rule);
      targets.push_back(rule.to);
    }
  }
  std::error_code code;
  std::filesystem::create_directories(root, code);
  I::Recover(root);
  const I::Staged staged = I::ExtractArchive(engine, root, archive, rules, nullptr, {},
                                             flat ? ".neostation-expanded-nt" : I::kStagingPrefix, flat);
  uint64_t files = 0, bytes = 0;
  for (size_t i = 0; i < staged.files.size(); ++i) { files += staged.files[i]; bytes += staged.bytes[i]; }
  if (staged.status != NeoTextureArchive::Status::ok || !staged.problem.empty()) {
    std::printf("result=stage status=%s problem=%s\n", NeoTextureArchive::StatusName(staged.status), staged.problem.c_str());
    I::RemoveTree(staged.staging);
    return 3;
  }
  if (!files) { std::printf("result=noTextures\n"); I::RemoveTree(staged.staging); return 5; }
  if (flat) {
    // The expanded folder the ARMSX2 store receives: printed for the next step.
    std::printf("result=expanded files=%llu bytes=%llu folder=%s\n", (unsigned long long)files, (unsigned long long)bytes, staged.staging.c_str());
    return 0;
  }
  if (const std::string bad = I::VerifySignatures(staged); !bad.empty()) {
    std::printf("result=signature file=%s\n", bad.c_str());
    I::RemoveTree(staged.staging);
    return 4;
  }
  // The store refuses a folder that holds no texture (markers, textures.ini or pack.json only).
  for (const auto& folder : staged.folders)
    if (I::IsDirectory(folder) && !I::HasTextures(engine, folder)) {
      std::printf("result=noTextures\n");
      I::RemoveTree(staged.staging);
      return 5;
    }
  std::string problem;
  if (!I::Commit(root, staged, targets, &problem)) {
    std::printf("result=commit problem=%s\n", problem.c_str());
    I::RemoveTree(staged.staging);
    return 6;
  }
  std::printf("result=installed files=%llu bytes=%llu\n", (unsigned long long)files, (unsigned long long)bytes);
  for (size_t i = 0; i < targets.size(); ++i)
    std::printf("folder=%s\t%llu\t%llu\n", targets[i].c_str(), (unsigned long long)staged.files[i], (unsigned long long)staged.bytes[i]);
  return 0;
}

static int Armsx2(int argc, char** argv) {
  if (argc < 6) return 64;
  const A::fs::path data = argv[2], source = argv[3];
  const std::string serial = argv[4], name = argv[5];
  const bool move = argc > 6 && std::string(argv[6]) == "move";
  const A::fs::path root = data / "textures";
  std::error_code code;
  A::fs::create_directories(root, code);
  A::Source input;
  const std::string lower = TexturePackPaths::Lower(source.string());
  if (A::IsRealDirectory(source)) { input.kind = A::SourceKind::Folder; input.moveFiles = move; }
  else if (lower.size() > 4 && lower.substr(lower.size() - 4) == ".tar") input.kind = A::SourceKind::Tar;
  else input.kind = A::SourceKind::Zip;
  input.path = source;
  if (!A::OpenSource(input)) { std::printf("result=open error=%s\n", input.error.c_str()); return 3; }
  A::Plan plan = A::BuildPlan(input.entries, name, serial);
  const A::Verdict verdict = A::Judge(plan, serial);
  std::printf("plan files=%zu bytes=%llu skipped=%llu excluded=%llu error=%s detail=%s match=%s pack=%s regionConflict=%d serials=",
              plan.files.size(), (unsigned long long)plan.bytes, (unsigned long long)plan.skipped, (unsigned long long)plan.excluded,
              plan.error.c_str(), plan.detail.c_str(), verdict.match.c_str(), verdict.packSerial.c_str(), verdict.regionConflict ? 1 : 0);
  for (const auto& s : plan.packSerials) std::printf("%s,", s.c_str());
  std::printf("\n");
  if (!plan.error.empty()) return 4;
  const A::fs::path staging = root / (std::string(A::kStagingPrefix) + "verify");
  A::Inventory inventory;
  std::string error;
  if (!A::StageFiles(input, plan, staging, UINT64_MAX / 4, inventory, nullptr, error)) {
    std::printf("result=stage error=%s\n", error.c_str());
    A::fs::remove_all(staging, code);
    return 5;
  }
  const std::string manifest = A::ManifestJSON(serial, name, move ? "catalogue" : "zip", plan, verdict, inventory, "verify");
  bool hadPrevious = false;
  if (!A::CommitStaged(root, serial, staging, manifest, root / (std::string(A::kPreviousPrefix) + "verify"), hadPrevious, error)) {
    std::printf("result=commit error=%s\n", error.c_str());
    A::fs::remove_all(staging, code);
    return 6;
  }
  std::printf("result=installed files=%llu bytes=%llu named=%llu mips=%llu unsupported=%llu formats=", (unsigned long long)inventory.files,
              (unsigned long long)inventory.bytes, (unsigned long long)inventory.named, (unsigned long long)inventory.mips,
              (unsigned long long)inventory.unsupported);
  for (const auto& [format, count] : inventory.formats) std::printf("%s:%llu,", format.c_str(), (unsigned long long)count);
  std::printf("\n");
  return 0;
}

int main(int argc, char** argv) {
  if (argc < 3) return 64;
  const std::string command = argv[1];
  if (command == "list") return List(argv[2]);
  if (command == "detect") return Detect(argc, argv);
  if (command == "install") return Install(argc, argv);
  if (command == "armsx2") return Armsx2(argc, argv);
  return 64;
}
