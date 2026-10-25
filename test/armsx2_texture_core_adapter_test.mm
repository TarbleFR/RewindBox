// Runs the production HD texture adapter of the ARMSX2 Core (core/ARMSX2TextureReplacements.inc,
// Build 485, ABI 8) with owned stand-ins for the engine, as armsx2_blending_accuracy_test.mm does
// for the blending adapter. The stand-ins mirror the upstream contract read in the pinned sources:
// the per-game INI writer and reader of ARMSX2Bridge, VMManager::ReloadGameSettings reading
// LoadTextureReplacements into EmuConfig, MTGS::ApplySettings -> GSUpdateConfig, the GS thread
// owning the replacement map. The tar reader and path rules are the vendored upstream headers;
// the zstd stage is a pass-through stand-in (the Core build compiles the real decoder).
// No GPU, VM or texture replacement in a game is inferred from this test.
#import <Foundation/Foundation.h>
#include <algorithm>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <functional>
#include <map>
#include <memory>
#include <mutex>
#include <string>
#include <string_view>
#include <vector>
#include <sys/stat.h>
#include "ARMSX2CoreABI.h"
#include "upstream/TexturePackPaths.h"
#include "upstream/TexturePackTar.h"

using u32 = uint32_t;
using u64 = uint64_t;

// ---- Engine stand-ins -------------------------------------------------------------------------
static bool running = true, vmValid = true, mtgsOpen = true, onCPU = false, onGS = false, readOnly = false;
static int reloads = 0, applies = 0, mapReloads = 0, purges = 0;
static NSString* currentSerial = @"SLUS-21137";
static NSString* identity = @"SLUS-21137_ABCD1234";
static NSMutableDictionary<NSString*, NSMutableDictionary*>* games;  // identity -> "section/key" -> value
static NSMutableDictionary* globalValues;

struct Runtime { uint32_t kind = NEO_ARMSX2_BOOT_DISC; };
static Runtime& runtime() { static Runtime value; return value; }
static bool has_running_game() { return running; }
static int error_out(const std::string& s, char* out, size_t n) {
  if (out && n) { strncpy(out, s.c_str(), n - 1); out[n - 1] = 0; }
  return 0;
}
static unsigned long long os_proc_available_memory() { return 1500ull * 1024 * 1024; }

struct { struct { bool LoadTextureReplacements = false, LoadTextureReplacementsAsync = true,
                  PrecacheTextureReplacements = false; } GS; } EmuConfig;

static NSString* k(NSString* section, NSString* key) { return [NSString stringWithFormat:@"%@/%@", section, key]; }
static NSMutableDictionary* game() {
  if (!games[identity]) games[identity] = [NSMutableDictionary dictionary];
  return games[identity];
}

namespace Host {
template <class F> void RunOnCPUThread(F f, bool block) { assert(block); assert(!onCPU); onCPU = true; f(); onCPU = false; }
}
namespace VMManager {
bool HasValidVM() { return vmValid; }
std::string GetDiscSerial() { return currentSerial.UTF8String; }
u32 GetDiscCRC() { return 0xABCD1234u; }
std::string GetDiscVersion() { return "1.01"; }
std::string GetTitle(bool) { return "Ratchet & Clank"; }
// Upstream: re-reads the base and per-game layers into EmuConfig.
void ReloadGameSettings() {
  assert(onCPU); ++reloads;
  NSNumber* value = game()[@"EmuCore/GS/LoadTextureReplacements"] ?: globalValues[@"EmuCore/GS/LoadTextureReplacements"];
  EmuConfig.GS.LoadTextureReplacements = value.boolValue;
  NSNumber* async = game()[@"EmuCore/GS/LoadTextureReplacementsAsync"];
  EmuConfig.GS.LoadTextureReplacementsAsync = async ? async.boolValue : true;
  NSNumber* precache = game()[@"EmuCore/GS/PrecacheTextureReplacements"];
  EmuConfig.GS.PrecacheTextureReplacements = precache.boolValue;
}
}
namespace MTGS {
bool IsOpen() { return mtgsOpen; }
void ApplySettings() { assert(onCPU); ++applies; }
template <class F> void RunOnGSThread(F f) { assert(onCPU && !onGS); onGS = true; f(); onGS = false; }
void WaitGS(bool) { assert(onCPU); }
}
struct GSDevice {
  struct FeatureSupport { bool dxt_textures = false, bptc_textures = false, astc_textures = true; };
  FeatureSupport Features() const { assert(onGS); return {}; }
};
static GSDevice deviceStandIn;
static GSDevice* g_gs_device = &deviceStandIn;
struct GSRenderer { void PurgeTextureCache(bool sources, bool targets, bool hash) { assert(onGS && sources && !targets && hash); ++purges; } };
static GSRenderer rendererStandIn;
static GSRenderer* g_gs_renderer = &rendererStandIn;
static bool GSIsHardwareRenderer() { assert(onGS); return true; }
namespace GSTextureReplacements {
u32 GetIndexedReplacementCount() { assert(onGS); return 42; }
u32 GetLoadedTextureCount() { assert(onGS); return 7; }
void GetReplacementCacheUsage(u64* bytes, u64* budget, bool* hit) { assert(onGS); *bytes = 1024; *budget = 4096; *hit = false; }
void ReloadReplacementMap() { assert(onGS); ++mapReloads; }
}
namespace FileSystem {
struct Closer { void operator()(std::FILE* f) const { if (f) std::fclose(f); } };
std::unique_ptr<std::FILE, Closer> OpenManagedCFile(const char* path, const char* mode) {
  return std::unique_ptr<std::FILE, Closer>(std::fopen(path, mode));
}
bool CreateDirectoryPath(const char* path, bool) {
  return [NSFileManager.defaultManager createDirectoryAtPath:@(path) withIntermediateDirectories:YES attributes:nil error:nil];
}
bool FileExists(const char* path) { struct stat st; return stat(path, &st) == 0; }
}
namespace Path {
std::string Combine(std::string_view a, std::string_view b) { return std::string(a) + "/" + std::string(b); }
std::string_view GetDirectory(std::string_view path) {
  const size_t slash = path.rfind('/');
  return slash == std::string_view::npos ? std::string_view() : path.substr(0, slash);
}
}
// Pass-through for the engine's streaming zstd reader: the fixtures are plain tar.
class TexturePackZstd {
 public:
  explicit TexturePackZstd(std::FILE* file) : file_(file) {}
  bool Valid() const { return file_ != nullptr; }
  bool Read(void* buffer, size_t size) { return std::fread(buffer, 1, size, file_) == size; }
 private:
  std::FILE* file_;
};

@interface ARMSX2Bridge : NSObject
+ (NSString*)perGameIdentityKeyForCurrentGame;
+ (void)setPerGameINIBool:(NSString*)section key:(NSString*)key value:(BOOL)value forISO:(NSString*)iso;
+ (NSNumber*)perGameINIBoolIfPresent:(NSString*)section key:(NSString*)key forISO:(NSString*)iso;
+ (BOOL)getINIBool:(NSString*)section key:(NSString*)key defaultValue:(BOOL)def;
@end
@implementation ARMSX2Bridge
+ (NSString*)perGameIdentityKeyForCurrentGame { return vmValid ? identity : @""; }
+ (void)setPerGameINIBool:(NSString*)section key:(NSString*)key value:(BOOL)value forISO:(NSString*)iso {
  assert(iso == nil && onCPU);
  if (!readOnly) game()[k(section, key)] = @(value);
}
+ (NSNumber*)perGameINIBoolIfPresent:(NSString*)section key:(NSString*)key forISO:(NSString*)iso {
  assert(iso == nil && onCPU); return game()[k(section, key)];
}
+ (BOOL)getINIBool:(NSString*)section key:(NSString*)key defaultValue:(BOOL)def {
  id value = globalValues[k(section, key)]; return value ? [value boolValue] : def;
}
@end

#include "ARMSX2TextureReplacements.inc"

// ---- Test ----------------------------------------------------------------------------------------
// vm_worker calls the boot hook on the CPU thread after VMManager::Initialize.
static void boot() { Host::RunOnCPUThread([] { apply_texture_boot_preference(); }, true); }
static void require(bool ok, const char* what) { if (!ok) { fprintf(stderr, "FAIL: %s\n", what); abort(); } }
static int checks = 0;
#define REQUIRE(x, what) do { require((x), what); ++checks; } while (0)

static NSDictionary* state(size_t capacity = 4096) {
  std::vector<char> json(capacity);
  if (!get_texture_replacements_json(json.data(), json.size())) return nil;
  return [NSJSONSerialization JSONObjectWithData:[NSData dataWithBytes:json.data() length:strlen(json.data())] options:0 error:nil];
}
static NSArray<NSString*>* files(NSString* root) {
  NSMutableArray* found = [NSMutableArray array];
  for (NSString* relative in [NSFileManager.defaultManager enumeratorAtPath:root]) {
    BOOL directory = NO;
    [NSFileManager.defaultManager fileExistsAtPath:[root stringByAppendingPathComponent:relative] isDirectory:&directory];
    if (!directory) [found addObject:relative];
  }
  return [found sortedArrayUsingSelector:@selector(compare:)];
}

int main(int argc, char** argv) { @autoreleasepool {
  if (argc != 3) return 2;
  NSString* fixtures = @(argv[1]);
  NSString* work = @(argv[2]);
  games = [NSMutableDictionary dictionary];
  globalValues = [NSMutableDictionary dictionary];
  char error[256] = {};

  // 1. Boot choices from NeoStation's library: validated, then applied once per game.
  REQUIRE(!set_texture_boot_preferences("not json", error, sizeof(error)) && !strcmp(error, "invalid"), "bad JSON refused");
  REQUIRE(!set_texture_boot_preferences("{\"games\":{\"SLUS-21137\":\"yes\"}}", error, sizeof(error)), "non-boolean refused");
  REQUIRE(!set_texture_boot_preferences("{\"games\":[]}", error, sizeof(error)), "non-object refused");
  REQUIRE(set_texture_boot_preferences("{\"games\":{\"SLUS-21137\":true,\"SLES-50000\":false}}", error, sizeof(error)), "valid choices");

  runtime().kind = NEO_ARMSX2_BOOT_ELF;
  boot();
  REQUIRE(reloads == 0 && game().count == 0, "an ELF boot is not a game disc: nothing written");
  runtime().kind = NEO_ARMSX2_BOOT_DISC;
  boot();
  REQUIRE([game()[@"EmuCore/GS/LoadTextureReplacements"] isEqual:@YES], "choice written to the game's INI");
  REQUIRE([game()[@"EmuCore/GS/LoadTextureReplacementsAsync"] isEqual:@YES], "background decoding");
  REQUIRE([game()[@"EmuCore/GS/PrecacheTextureReplacements"] isEqual:@NO], "never preload the whole pack");
  REQUIRE(reloads == 1 && applies == 1 && EmuConfig.GS.LoadTextureReplacements, "settings reloaded and applied before the first frame");
  boot();
  REQUIRE(reloads == 1 && applies == 1, "second start with the same choice: no rewrite");
  game()[@"EmuCore/GS/PrecacheTextureReplacements"] = @YES;  // set by another frontend
  boot();
  REQUIRE(reloads == 2 && [game()[@"EmuCore/GS/PrecacheTextureReplacements"] isEqual:@NO], "a whole-pack preload is turned back off");

  currentSerial = @"SLES-50000"; identity = @"SLES-50000_00C0FFEE";
  boot();
  REQUIRE([game()[@"EmuCore/GS/LoadTextureReplacements"] isEqual:@NO] && !game()[@"EmuCore/GS/PrecacheTextureReplacements"], "off: only the switch is written");
  REQUIRE([games[@"SLUS-21137_ABCD1234"][@"EmuCore/GS/LoadTextureReplacements"] isEqual:@YES], "the other game's INI untouched");
  currentSerial = @"SCUS-97399"; identity = @"SCUS-97399_11111111";
  const int before = reloads;
  boot();
  REQUIRE(reloads == before && game().count == 0, "no NeoStation choice for this game: its INI is left alone");

  // 2. State read on the CPU thread, engine counts on the GS thread.
  currentSerial = @"SLUS-21137"; identity = @"SLUS-21137_ABCD1234";
  Host::RunOnCPUThread([] { VMManager::ReloadGameSettings(); }, true);  // this game's boot
  NSDictionary* s = state();
  REQUIRE([s[@"available"] boolValue] && [s[@"serial"] isEqual:@"SLUS-21137"] && [s[@"crc"] isEqual:@"ABCD1234"], "identity");
  REQUIRE([s[@"game"] intValue] == 1 && [s[@"global"] isEqual:@NO] && [s[@"effective"] isEqual:@YES], "choice, global default, effective");
  REQUIRE([s[@"async"] isEqual:@YES] && [s[@"precache"] isEqual:@NO], "async without preload");
  REQUIRE([s[@"hardware"] isEqual:@YES] && [s[@"indexed"] intValue] == 42 && [s[@"loaded"] intValue] == 7, "engine counts");
  REQUIRE([s[@"cacheBytes"] intValue] == 1024 && [s[@"budgetBytes"] intValue] == 4096 && [s[@"budgetReached"] isEqual:@NO], "cache budget");
  REQUIRE([s[@"bcTextures"] isEqual:@NO] && [s[@"astcTextures"] isEqual:@YES], "device formats");
  REQUIRE(state(16) == nil, "an answer that does not fit is refused, not truncated");
  mtgsOpen = false;
  s = state();
  REQUIRE(s && !s[@"indexed"] && [s[@"effective"] isEqual:@YES], "GS closed: no engine counts invented");
  mtgsOpen = true;
  running = false;
  REQUIRE(state() == nil, "no session: no state");
  running = true;

  // 3. Live switch: the game's INI, then the engine's settings.
  REQUIRE(!set_texture_replacements(2, error, sizeof(error)) && !strcmp(error, "invalid"), "out of range");
  running = false;
  REQUIRE(!set_texture_replacements(0, error, sizeof(error)) && !strcmp(error, "noSession"), "no session");
  running = true;
  const int applied = applies;
  REQUIRE(set_texture_replacements(0, error, sizeof(error)), "off in game");
  REQUIRE([game()[@"EmuCore/GS/LoadTextureReplacements"] isEqual:@NO] && !EmuConfig.GS.LoadTextureReplacements && applies == applied + 1, "applied live");
  REQUIRE(set_texture_replacements(1, error, sizeof(error)) && EmuConfig.GS.LoadTextureReplacements, "on in game");
  readOnly = true;
  REQUIRE(!set_texture_replacements(0, error, sizeof(error)) && !strcmp(error, "write"), "a write the engine did not keep is reported");
  readOnly = false;
  runtime().kind = NEO_ARMSX2_BOOT_BIOS;
  REQUIRE(!set_texture_replacements(0, error, sizeof(error)), "BIOS session: no game to configure");
  runtime().kind = NEO_ARMSX2_BOOT_DISC;

  // 4. Reload after NeoStation changed the files of the running game's pack.
  REQUIRE(reload_texture_replacements(error, sizeof(error)) && mapReloads == 1 && purges == 1, "map re-indexed, cache purged");
  mtgsOpen = false;
  REQUIRE(!reload_texture_replacements(error, sizeof(error)) && mapReloads == 1, "GS closed: nothing to reload");
  mtgsOpen = true;

  // 5. The engine's .tar.zst stage (pass-through decoder here): texture entries only.
  NSString* out = [work stringByAppendingPathComponent:@"expanded"];
  [NSFileManager.defaultManager createDirectoryAtPath:out withIntermediateDirectories:YES attributes:nil error:nil];
  NSString* tar = [fixtures stringByAppendingPathComponent:@"pack.tar"];
  volatile int cancel = 0; volatile uint64_t consumed = 0;
  REQUIRE(expand_texture_archive(tar.UTF8String, out.UTF8String, 1ull << 40, &cancel, &consumed, error, sizeof(error)), "expanded");
  NSArray* written = files(out);
  REQUIRE(written.count == 5, "five texture entries (readme skipped)");
  NSString* prefix = [NSString stringWithFormat:@"pack-%@/textures/SLUS-21137/replacements/", [@"" stringByPaddingToLength:40 withString:@"a" startingAtIndex:0]];
  REQUIRE([written containsObject:[prefix stringByAppendingString:@"ui/0123456789abcdef-00004a2d.png"]], "archive path and sub-folders kept");
  REQUIRE(consumed > 0, "progress reported");
  REQUIRE(!expand_texture_archive(tar.UTF8String, out.UTF8String, 1ull << 40, &cancel, &consumed, error, sizeof(error)) && !strcmp(error, "write"),
          "an existing file is never overwritten");
  NSString* fresh = [work stringByAppendingPathComponent:@"fresh"];
  REQUIRE(!expand_texture_archive(tar.UTF8String, fresh.UTF8String, 512ull * 1024 * 1024 + 16, &cancel, &consumed, error, sizeof(error)) && !strcmp(error, "space"),
          "free space below the 512 MiB margin");
  cancel = 1;
  REQUIRE(!expand_texture_archive(tar.UTF8String, [work stringByAppendingPathComponent:@"cancel"].UTF8String, 1ull << 40, &cancel, &consumed, error, sizeof(error)) &&
          !strcmp(error, "cancelled"), "cancelled");
  cancel = 0;
  REQUIRE(!expand_texture_archive([fixtures stringByAppendingPathComponent:@"truncated.tar"].UTF8String,
                                  [work stringByAppendingPathComponent:@"truncated"].UTF8String, 1ull << 40, &cancel, &consumed, error, sizeof(error)) &&
          !strcmp(error, "invalid"), "damaged archive: a key, not the reader's English sentence");
  REQUIRE(!expand_texture_archive([fixtures stringByAppendingPathComponent:@"pack-traversal.tar"].UTF8String,
                                  [work stringByAppendingPathComponent:@"traversal"].UTF8String, 1ull << 40, &cancel, &consumed, error, sizeof(error)) &&
          !strcmp(error, "unsafe"), "path traversal refused");
  REQUIRE(![NSFileManager.defaultManager fileExistsAtPath:[work stringByAppendingPathComponent:@"evil-00000001.png"]], "nothing written outside");
  REQUIRE(!expand_texture_archive("relative.tar", out.UTF8String, 1, &cancel, &consumed, error, sizeof(error)) && !strcmp(error, "invalid"), "absolute paths only");
  REQUIRE(!expand_texture_archive([fixtures stringByAppendingPathComponent:@"missing.tar.zst"].UTF8String, out.UTF8String, 1ull << 40, &cancel, &consumed,
                                  error, sizeof(error)) && !strcmp(error, "unreadable"), "missing archive");
  printf("PASS core adapter: %d checks (boot choices, state, live switch, reload, archive expansion)\n", checks);
  return 0;
} }
