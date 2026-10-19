// Runs the production host-side HD texture pack core (Build 485) on real files
// written by test/armsx2_texture_packs_test.py: ZIP (Store, Deflate, ZIP64,
// CP437 names, links, encryption, unsupported methods, bad CRC), tar (GNU long
// names, pax refused), folders (links refused), ISO 9660 images (2048 and raw
// 2352 sectors), staging, atomic replacement, removal and leftovers.
// Nothing here runs the engine: it proves file handling, not texture rendering.
#include "ARMSX2TexturePackCore.h"

#include <cassert>
#include <cstdio>
#include <fstream>
#include <iostream>

using namespace NeoARMSX2Textures;
static int checks = 0;
#define CHECK(x) do { if (!(x)) { std::cerr << "FAILED " << __LINE__ << ": " #x << std::endl; std::abort(); } ++checks; } while (0)

static fs::path fixtures;
static std::string read(const fs::path& path) {
  std::ifstream in(path, std::ios::binary);
  return std::string((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
}
static void write(const fs::path& path, const std::string& bytes) {
  fs::create_directories(path.parent_path());
  std::ofstream(path, std::ios::binary) << bytes;
}
static Source open(SourceKind kind, const std::string& name) {
  Source source; source.kind = kind; source.path = fixtures / name;
  OpenSource(source);
  return source;
}

static void serials() {
  CHECK(ExecutablePathToSerial("cdrom0:\\SLUS_211.37;1") == "SLUS-21137");
  CHECK(ExecutablePathToSerial("cdrom0:\\DATA\\sces_500.51;1") == "SCES-50051");
  CHECK(ExecutablePathToSerial("cdrom:SLPM-123.45") == "SLPM-12345");
  CHECK(ExecutablePathToSerial("cdrom0:\\MAIN.ELF;1").empty());
  DiscIdentity cnf = ParseSystemCnf("BOOT2 = cdrom0:\\SLUS_211.37;1\r\nVER = 1.01\r\nVMODE = NTSC\r\n");
  CHECK(cnf.serial == "SLUS-21137" && cnf.version == "1.01");
  CHECK(ParseSystemCnf("BOOT = cdrom:\\SCUS_944.26;1\n").serial == "SCUS-94426");
  CHECK(ParseSystemCnf("VER = 1.00\n").serial.empty());
  CHECK(IsStoreSerial("SLUS-21137") && IsStoreSerial("PBPX-95520") && !IsStoreSerial("SLUS21137") &&
        !IsStoreSerial("../S-12345") && !IsStoreSerial("slus-21137"));
  CHECK(RegionOfSerial("SLUS-21137") == "NTSC-U" && RegionOfSerial("SCES-50051") == "PAL" &&
        RegionOfSerial("SLPM-65000") == "NTSC-J" && RegionOfSerial("ABCD-12345").empty());

  const auto iso = ReadDiscIdentity(fixtures / "game.iso");
  CHECK(iso && iso->serial == "SLUS-21137" && iso->version == "1.01");
  const auto raw = ReadDiscIdentity(fixtures / "game-raw.bin");
  CHECK(raw && raw->serial == "SCES-50051" && raw->version == "1.00");
  CHECK(!ReadDiscIdentity(fixtures / "not-a-disc.chd"));
  CHECK(!ReadDiscIdentity(fixtures / "volume-without-cnf.iso"));
  std::cout << "PASS serials: engine conversion, SYSTEM.CNF, ISO 2048 and raw 2352, refusals\n";
}

static void names_and_formats() {
  for (const char* name : {"a1b2c3d4e5f60708-00004a2d.png", "A1B2-00004A2D.PNG", "ab-cd-0000aaaa.dds",
                           "ab-r128x64-0000aaaa.astc", "ab-cd-r128x64-0000aaaa.ktx", "ab-r1234-0000aaaa.png",
                           "ab-cd-r1234-0000aaaa.png"})
    CHECK(IsReplacementName(name));
  for (const char* name : {"readme.png", "ab-0000aaaa-mip1.png", "ab-0000aaaa.jpg", "ab-0000aaaa.pngx", "ab-0000aaaa"})
    CHECK(!IsReplacementName(name));
  CHECK(IsMipName("ab-0000aaaa-mip1.png") && !IsMipName("ab-0000aaaa.png"));

  unsigned char png[16] = {137, 80, 78, 71, 13, 10, 26, 10};
  CHECK(SniffFormat(png, 16, 100, "x.png") == Format::Png);
  CHECK(SniffFormat(png, 16, 100, "x.dds") == Format::Unsupported);  // content decides, not the extension
  unsigned char dds[kHeadBytes] = {};
  auto put = [](unsigned char* p, uint32_t v) { p[0] = v; p[1] = v >> 8; p[2] = v >> 16; p[3] = v >> 24; };
  auto ddsHead = [&](uint32_t pfFlags, uint32_t fourcc, uint32_t bits, std::array<uint32_t, 4> masks) {
    std::memset(dds, 0, sizeof(dds)); std::memcpy(dds, "DDS ", 4);
    put(dds + 4, 124); put(dds + 8, 0x1007); put(dds + 12, 256); put(dds + 16, 256);
    put(dds + 76, 32); put(dds + 80, pfFlags); put(dds + 84, fourcc); put(dds + 88, bits);
    for (int i = 0; i < 4; ++i) put(dds + 92 + 4 * i, masks[i]);
  };
  auto four = [](const char* s) { return Le32(reinterpret_cast<const unsigned char*>(s)); };
  ddsHead(4, four("DXT1"), 0, {}); CHECK(SniffFormat(dds, kHeadBytes, 1000, "x.dds") == Format::DdsBc1);
  ddsHead(4, four("DXT5"), 0, {}); CHECK(SniffFormat(dds, kHeadBytes, 1000, "x.dds") == Format::DdsBc3);
  ddsHead(4, four("ATI2"), 0, {}); CHECK(SniffFormat(dds, kHeadBytes, 1000, "x.dds") == Format::Unsupported);
  ddsHead(4, four("DX10"), 0, {}); put(dds + 128, 98); put(dds + 132, 3); put(dds + 140, 1);
  CHECK(SniffFormat(dds, kHeadBytes, 1000, "x.dds") == Format::DdsBc7);
  put(dds + 128, 83);  // BC5: the loader leaves it to nothing on iOS
  CHECK(SniffFormat(dds, kHeadBytes, 1000, "x.dds") == Format::Unsupported);
  put(dds + 128, 98); put(dds + 140, 6);  // texture array
  CHECK(SniffFormat(dds, kHeadBytes, 1000, "x.dds") == Format::Unsupported);
  ddsHead(0x41, 0, 32, {0x00ff0000, 0x0000ff00, 0x000000ff, 0xff000000});
  CHECK(SniffFormat(dds, kHeadBytes, 1000, "x.dds") == Format::DdsRgba);
  ddsHead(0x40, 0, 16, {0xf800, 0x07e0, 0x001f, 0});  // R5G6B5
  CHECK(SniffFormat(dds, kHeadBytes, 1000, "x.dds") == Format::Unsupported);
  ddsHead(4, four("DXT1"), 0, {}); put(dds + 8, 0x1007 | 0x00800000);  // volume
  CHECK(SniffFormat(dds, kHeadBytes, 1000, "x.dds") == Format::Unsupported);

  unsigned char astc[16] = {0x13, 0xAB, 0xA1, 0x5C, 4, 4, 1, 16, 0, 0, 16, 0, 0, 1, 0, 0};
  CHECK(SniffFormat(astc, 16, 16 + 16 * 16, "x.astc") == Format::Astc);
  CHECK(SniffFormat(astc, 16, 16 + 16 * 16 + 1, "x.astc") == Format::Unsupported);  // trailing byte
  astc[4] = 7; CHECK(SniffFormat(astc, 16, 16 + 16 * 16, "x.astc") == Format::Unsupported);
  unsigned char ktx[64] = {0xAB, 'K', 'T', 'X', ' ', '1', '1', 0xBB, '\r', '\n', 0x1A, '\n'};
  put(ktx + 12, 0x04030201); put(ktx + 20, 1); put(ktx + 28, 0x93B0); put(ktx + 32, 0x1908);
  put(ktx + 36, 64); put(ktx + 40, 64); put(ktx + 52, 1); put(ktx + 56, 7);
  CHECK(SniffFormat(ktx, 64, 5000, "x.ktx") == Format::Ktx);
  put(ktx + 28, 0x93D0);  // sRGB twin: rejected by the engine's KTX parser
  CHECK(SniffFormat(ktx, 64, 5000, "x.ktx") == Format::Unsupported);
  std::cout << "PASS names and formats: six engine name patterns, PNG/DDS/ASTC/KTX acceptance and refusals\n";
}

static std::vector<Entry> entries(std::initializer_list<std::pair<const char*, uint64_t>> list) {
  std::vector<Entry> out;
  for (const auto& [name, size] : list) out.push_back({name, size, out.size(), {}});
  return out;
}

static void plans() {
  Plan bare = BuildPlan(entries({{"a-00000001.png", 10}, {"sub/b-00000002.dds", 20}, {"readme.txt", 5}}), "pack.zip", "SLUS-21137");
  CHECK(bare.error.empty() && bare.chosenSerial.empty() && bare.files.size() == 2 && bare.bytes == 30 && bare.skipped == 1);
  CHECK(bare.files[1].destination == "sub/b-00000002.dds");
  Verdict v = Judge(bare, "SLUS-21137");
  CHECK(v.match == "noSerial" && !v.regionConflict);

  const std::string hex40(40, 'a');
  Plan nested = BuildPlan(entries({{("pack-" + hex40 + "/textures/SLUS-21137/replacements/ui/a-00000001.png").c_str(), 10},
                                   {("pack-" + hex40 + "/textures/SLUS-21137/dumps/z-00000009.png").c_str(), 10}}),
                          "God of War II (USA) v1.01.zip", "SLUS-21137");
  CHECK(nested.error.empty() && nested.chosenSerial == "SLUS-21137" && nested.files.size() == 2);
  CHECK(nested.files[0].destination == "ui/a-00000001.png");
  CHECK(nested.hints.regions == std::set<std::string>{"NTSC-U"} && nested.hints.versions.count("1.01"));
  CHECK(Judge(nested, "SLUS-21137").match == "same");

  Plan two = BuildPlan(entries({{"SLUS-21137/a-00000001.png", 1}, {"SLES-54164/a-00000001.png", 1}}), "x", "SLES-54164");
  CHECK(two.error.empty() && two.chosenSerial == "SLES-54164" && two.files.size() == 1 && two.excluded == 1);
  Plan ambiguous = BuildPlan(entries({{"SLUS-21137/a-00000001.png", 1}, {"SLES-54164/a-00000001.png", 1}}), "x", "SCUS-97399");
  CHECK(ambiguous.error == "multipleSerials" && ambiguous.detail == "SLES-54164, SLUS-21137");

  Plan other = BuildPlan(entries({{"God of War II (Europe)/SLES-54164/replacements/a-00000001.png", 1}}), "x.zip", "SLUS-21137");
  Verdict o = Judge(other, "SLUS-21137");
  CHECK(o.match == "otherSerial" && o.packSerial == "SLES-54164" && o.regionConflict);
  Plan byName = BuildPlan(entries({{"a-00000001.png", 1}}), "slus_211.37 hd.zip", "SLUS-21137");
  CHECK(Judge(byName, "SLUS-21137").match == "same" && Judge(byName, "").match == "gameUnknown");
  Plan crc = BuildPlan(entries({{"HD [1A2B3C4D] PAL/a-00000001.png", 1}}), "x", "SLUS-21137");
  CHECK(crc.hints.crcs.count("1A2B3C4D") && crc.hints.regions.count("PAL"));

  CHECK(BuildPlan(entries({{"../a-00000001.png", 1}}), "x", "").error == "unsafe");
  CHECK(BuildPlan(entries({{"/abs/a-00000001.png", 1}}), "x", "").error == "unsafe");
  CHECK(BuildPlan(entries({{"C:\\a-00000001.png", 1}}), "x", "").error == "unsafe");
  CHECK(BuildPlan(entries({{"a/x-00000001.png", 1}, {"A/X-00000001.PNG", 1}}), "x", "").error == "duplicate");
  CHECK(BuildPlan(entries({{"a-00000001.png", kMaxFileBytes + 1}}), "x", "").error == "fileTooLarge");
  CHECK(BuildPlan(entries({{"readme.txt", 1}, {"__MACOSX/a-00000001.png", 1}, {".a-00000001.png", 1}}), "x", "").error == "noTextures");
  std::vector<Entry> many(kMaxEntries + 1, Entry{"a.txt", 1, 0, {}});
  CHECK(BuildPlan(many, "x", "").error == "entries");
  std::cout << "PASS plans: upstream mapping, serial groups, ambiguity, region/version/CRC hints, unsafe paths, limits\n";
}

static void stage(const Source& source, const Plan& plan, const fs::path& staging, Inventory& inventory, std::string& error,
                  uint64_t available = UINT64_MAX / 2, std::function<bool(uint64_t, uint64_t)> tick = {}) {
  error.clear();
  StageFiles(source, plan, staging, available, inventory, tick, error);
}

static void archives(const fs::path& work) {
  for (const char* name : {"pack-deflate.zip", "pack-stored.zip", "pack-zip64.zip", "pack.tar"}) {
    const SourceKind kind = std::string(name).ends_with(".tar") ? SourceKind::Tar : SourceKind::Zip;
    Source source = open(kind, name);
    CHECK(source.error.empty());
    Plan plan = BuildPlan(source.entries, name, "SLUS-21137");
    CHECK(plan.error.empty() && plan.chosenSerial == "SLUS-21137");
    Inventory inventory; std::string error;
    const fs::path staging = work / (std::string(kStagingPrefix) + name);
    uint64_t ticks = 0;
    stage(source, plan, staging, inventory, error, UINT64_MAX / 2, [&](uint64_t, uint64_t) { ++ticks; return true; });
    CHECK(error.empty());
    // fixtures: 3 named textures (png, dds bc1, astc), 1 mip, 1 unsupported dds, readme skipped
    CHECK(inventory.files == 4 && inventory.named == 3 && inventory.mips == 1 && inventory.unsupported == 1);
    CHECK(inventory.formats["png"] == 2 && inventory.formats["ddsBc1"] == 1 && inventory.formats["astc"] == 1);
    CHECK(read(staging / "ui/0123456789abcdef-00004a2d.png") == read(fixtures / "payload/ui/0123456789abcdef-00004a2d.png"));
    CHECK(fs::exists(staging / "ui/0123456789abcdef-00004a2d-mip1.png") && !fs::exists(staging / "bad-0000beef.dds"));
    CHECK(ticks > 0);
    if (kind == SourceKind::Tar) {
      bool longName = false;
      for (const Entry& e : source.entries) longName |= e.name.size() > 100;
      CHECK(longName);
    }
    fs::remove_all(staging);
  }
  Source cp = open(SourceKind::Zip, "pack-cp437.zip");
  bool decoded = false;
  for (const Entry& e : cp.entries) decoded |= e.name.find("Caf\xC3\xA9") != std::string::npos;
  CHECK(cp.error.empty() && decoded);

  CHECK(open(SourceKind::Zip, "pack-symlink.zip").error == "unsafe");
  CHECK(BuildPlan(open(SourceKind::Zip, "pack-traversal.zip").entries, "x", "SLUS-21137").error == "unsafe");
  CHECK(open(SourceKind::Zip, "pack-encrypted.zip").error == "encrypted");
  CHECK(open(SourceKind::Zip, "pack-split.zip").error == "split");
  CHECK(open(SourceKind::Zip, "not-a-zip.zip").error == "invalid");
  CHECK(open(SourceKind::Zip, "pack-forged-cd.zip").error == "invalid");  // no allocation from a forged size
  CHECK(open(SourceKind::Tar, "pack-pax.tar").error == "invalid");
  CHECK(open(SourceKind::Tar, "truncated.tar").error == "invalid");

  for (const auto& [name, expected] : {std::pair<const char*, const char*>{"pack-deflate64.zip", "method:9"},
                                       {"pack-badcrc.zip", "invalid"}}) {
    Source source = open(SourceKind::Zip, name);
    CHECK(source.error.empty());
    Plan plan = BuildPlan(source.entries, name, "SLUS-21137");
    Inventory inventory; std::string error;
    stage(source, plan, work / (std::string(kStagingPrefix) + name), inventory, error);
    CHECK(error == expected);
    fs::remove_all(work / (std::string(kStagingPrefix) + name));
  }

  // Free space is checked before writing (and while writing).
  Source source = open(SourceKind::Zip, "pack-deflate.zip");
  Plan plan = BuildPlan(source.entries, "x", "SLUS-21137");
  Inventory inventory; std::string error;
  stage(source, plan, work / ".neostation-import-space", inventory, error, kSpareBytes + plan.bytes - 1);
  CHECK(error == "space");
  // Cancellation stops between chunks.
  stage(source, plan, work / ".neostation-import-cancel", inventory, error, UINT64_MAX / 2, [](uint64_t, uint64_t) { return false; });
  CHECK(error == "cancelled");
  // A pack whose files have no engine name installs nothing.
  Source unnamed = open(SourceKind::Zip, "pack-unnamed.zip");
  Plan unnamedPlan = BuildPlan(unnamed.entries, "x", "SLUS-21137");
  CHECK(unnamedPlan.error.empty());
  stage(unnamed, unnamedPlan, work / ".neostation-import-unnamed", inventory, error);
  CHECK(error == "noNamedTextures");
  std::cout << "PASS archives: ZIP Store/Deflate/ZIP64/CP437, tar long names, refusals (links, traversal, encryption, split, pax, Deflate64, CRC), space, cancel\n";
}

static void folders(const fs::path& work) {
  Source folder = open(SourceKind::Folder, "folder/SLUS-21137");
  CHECK(folder.error.empty());
  Plan plan = BuildPlan(folder.entries, "SLUS-21137", "SLUS-21137");
  CHECK(plan.error.empty() && plan.chosenSerial == "SLUS-21137" && plan.files.size() == 5);
  Inventory inventory; std::string error;
  stage(folder, plan, work / ".neostation-import-folder", inventory, error);
  CHECK(error.empty() && inventory.named == 3 && fs::exists(fixtures / "folder/SLUS-21137/replacements/ui/0123456789abcdef-00004a2d.png"));
  fs::remove_all(work / ".neostation-import-folder");
  CHECK(open(SourceKind::Folder, "folder-link").error == "unsafe");

  // An expanded private folder is moved, not copied.
  const fs::path expanded = work / (std::string(kExpandedPrefix) + "x");
  fs::create_directories(expanded);
  fs::copy(fixtures / "folder/SLUS-21137", expanded / "SLUS-21137", fs::copy_options::recursive);
  fs::copy(fixtures / "payload", expanded / "loose", fs::copy_options::recursive);
  Source moved; moved.kind = SourceKind::Folder; moved.path = expanded; moved.moveFiles = true;
  CHECK(OpenSource(moved));
  for (const Entry& e : moved.entries) CHECK(e.name.find(kExpandedPrefix) == std::string::npos);
  Plan movedPlan = BuildPlan(moved.entries, "x", "SLUS-21137");
  CHECK(movedPlan.chosenSerial == "SLUS-21137" && movedPlan.excluded == 5);
  // Already on this volume: renaming needs no free space for a second copy.
  stage(moved, movedPlan, work / ".neostation-import-moved", inventory, error, /*available=*/0);
  CHECK(error.empty() && !fs::exists(expanded / "SLUS-21137/replacements/ui/0123456789abcdef-00004a2d.png"));
  CHECK(fs::exists(work / ".neostation-import-moved/ui/0123456789abcdef-00004a2d.png"));
  fs::remove_all(expanded); fs::remove_all(work / ".neostation-import-moved");
  std::cout << "PASS folders: serial folder, copies, links refused, private expansion moved\n";
}

static void install(const fs::path& work) {
  const fs::path root = work / "textures";
  fs::create_directories(root / "SLUS-21137/dumps");
  write(root / "SLUS-21137/dumps/keep-00000001.png", "dump");
  write(root / "SLUS-21137/replacements/old-00000001.png", "old");
  write(root / "saves.ps2", "save");

  Source source = open(SourceKind::Zip, "pack-deflate.zip");
  Plan plan = BuildPlan(source.entries, "pack-deflate.zip", "SLUS-21137");
  Verdict verdict = Judge(plan, "SLUS-21137");
  Inventory inventory; std::string error;
  const fs::path staging = root / (std::string(kStagingPrefix) + "a");
  stage(source, plan, staging, inventory, error);
  CHECK(error.empty());
  const std::string manifest = ManifestJSON("SLUS-21137", "pack \"deflate\".zip", "zip", plan, verdict, inventory, "2026-10-18T00:00:00Z");
  CHECK(manifest.find("\"source\":\"pack \\\"deflate\\\".zip\"") != std::string::npos && manifest.find("\"named\":3") != std::string::npos);

  // A failing commit (staged folder missing) keeps the working pack.
  bool hadPrevious = false;
  CHECK(!CommitStaged(root, "SLUS-21137", root / ".neostation-import-missing", manifest, root / ".neostation-previous-x", hadPrevious, error));
  CHECK(read(root / "SLUS-21137/replacements/old-00000001.png") == "old");
  CHECK(!CommitStaged(root, "../escape", staging, manifest, root / ".neostation-previous-x", hadPrevious, error));

  const fs::path previous = root / (std::string(kPreviousPrefix) + "b");
  CHECK(CommitStaged(root, "SLUS-21137", staging, manifest, previous, hadPrevious, error));
  CHECK(hadPrevious && fs::exists(previous / "old-00000001.png") && !fs::exists(staging));
  CHECK(fs::exists(root / "SLUS-21137/replacements/ui/0123456789abcdef-00004a2d.png"));
  CHECK(!fs::exists(root / "SLUS-21137/replacements/old-00000001.png"));
  CHECK(read(root / "SLUS-21137/dumps/keep-00000001.png") == "dump" && read(root / "saves.ps2") == "save");
  CHECK(read(root / "SLUS-21137" / kManifest) == manifest);

  Inventory installed = ScanInstalled(root / "SLUS-21137/replacements");
  CHECK(installed.files == 4 && installed.named == 3 && installed.unsupported == 0);

  // Removal keeps dumps and anything that is not the pack.
  const fs::path removing = root / (std::string(kRemovingPrefix) + "c");
  CHECK(RemovePack(root, "SLUS-21137", removing, error));
  CHECK(!fs::exists(root / "SLUS-21137/replacements") && !fs::exists(root / "SLUS-21137" / kManifest));
  CHECK(fs::exists(removing / "ui") && read(root / "SLUS-21137/dumps/keep-00000001.png") == "dump");
  fs::remove_all(root / "SLUS-21137/dumps");
  write(root / "SLES-54164/replacements/a-00000001.png", "x");
  CHECK(RemovePack(root, "SLES-54164", root / ".neostation-removing-d", error) && !fs::exists(root / "SLES-54164"));
  CHECK(!RemovePack(root, "SCUS-97399", root / ".neostation-removing-e", error) && error == "missing");

  // Leftovers: only this store's prefixes, directly below the textures root.
  fs::create_directories(root / ".neostation-import-z");
  fs::create_directories(root / ".import-upstream");
  CHECK(SweepLeftovers(root) == 4);  // previous-b, removing-c, removing-d, import-z
  CHECK(fs::exists(root / ".import-upstream") && fs::exists(root / "saves.ps2") && fs::exists(root / "SLUS-21137"));
  std::cout << "PASS install: atomic replacement, failure keeps the working pack, dumps and saves untouched, removal, leftovers\n";
}

int main(int argc, char** argv) {
  if (argc != 3) { std::cerr << "usage: test <fixtures> <work>\n"; return 2; }
  fixtures = argv[1];
  const fs::path work = argv[2];
  serials();
  names_and_formats();
  plans();
  archives(work);
  folders(work);
  install(work);
  std::cout << "PASS " << checks << " checks\n";
  return 0;
}
