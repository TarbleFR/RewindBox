// Host driver for NeoTextureInstall (the installer's file-system core).
//   detect <engine> <current> <names-file>
//   install <engine> <root> <archive|folder> <from=to[|exclude]...>...   (folder when it is a directory)
//   remove <root> <relative> | recover <root> | accepts <engine> <path>
#include "NeoTextureInstall.h"
#include <cstdio>
#include <fstream>
using namespace NeoTextureInstall;
static Engine Parse(const std::string& s) {
  return s == "dolphin" ? Engine::dolphin : s == "armsx2" ? Engine::armsx2 : s == "ppsspp" ? Engine::ppsspp
       : s == "mupen64plus" ? Engine::mupen64plus : s == "beetle" ? Engine::beetle : Engine::azahar;
}
int main(int argc, char** argv) {
  if (argc < 3) return 64;
  const std::string command = argv[1];
  if (command == "accepts") return Accepts(Parse(argv[2]), argv[3]) ? 0 : 1;
  if (command == "detect") {
    std::ifstream in(argv[4]);
    std::vector<std::string> names;
    for (std::string line; std::getline(in, line);) if (!line.empty()) names.push_back(line);
    const Layout layout = Detect(Parse(argv[2]), names, argv[3]);
    std::printf("problem=%s other=%d", layout.problem.c_str(), layout.otherRegion ? 1 : 0);
    for (const auto& rule : layout.rules) std::printf(" rule=%s>%s", rule.from.c_str(), rule.to.c_str());
    for (const auto& id : layout.found) std::printf(" found=%s", id.c_str());
    std::printf("\n");
    return 0;
  }
  if (command == "recover") { Recover(argv[2]); return 0; }
  if (command == "remove") return Remove(argv[2], argv[3]) ? 0 : 1;
  if (command == "install") {
    const Engine engine = Parse(argv[2]);
    const std::string root = argv[3], source = argv[4];
    std::vector<Rule> rules;
    std::vector<std::string> targets;
    for (int i = 5; i < argc; ++i) {
      // from=to[|excluded prefix]...
      std::string spec = argv[i];
      std::vector<std::string> exclude;
      for (size_t bar; (bar = spec.rfind('|')) != std::string::npos; spec.resize(bar)) exclude.insert(exclude.begin(), spec.substr(bar + 1));
      const size_t equals = spec.find('=');
      rules.push_back({spec.substr(0, equals), spec.substr(equals + 1), exclude});
      targets.push_back(spec.substr(equals + 1));
    }
    Recover(root);
    const Staged staged = IsDirectory(source) ? CopyFolder(engine, root, source, rules, nullptr)
                                              : ExtractArchive(engine, root, source, rules, nullptr);
    if (staged.status != NeoTextureArchive::Status::ok || !staged.problem.empty()) {
      std::printf("stage %s %s\n", NeoTextureArchive::StatusName(staged.status), staged.problem.c_str());
      RemoveTree(staged.staging);
      return 3;
    }
    if (const std::string bad = VerifySignatures(staged); !bad.empty()) { std::printf("signature %s\n", bad.c_str()); RemoveTree(staged.staging); return 4; }
    // The store refuses a staged folder without a texture (problemWithStagedFolder).
    for (const auto& folder : staged.folders)
      if (IsDirectory(folder) && !HasTextures(engine, folder)) { std::printf("commit noTextures\n"); RemoveTree(staged.staging); return 5; }
    std::string problem;
    if (!Commit(root, staged, targets, &problem)) { std::printf("commit %s\n", problem.c_str()); RemoveTree(staged.staging); return 5; }
    uint64_t files = 0;
    for (auto f : staged.files) files += f;
    std::printf("installed files=%llu\n", (unsigned long long)files);
    return 0;
  }
  return 64;
}
