// Runs the production blending-accuracy adapter (core/ARMSX2BlendingAccuracy.inc)
// with owned CPU-thread and INI stand-ins, exactly as armsx2_graphics_settings_test.mm
// does for the shader/overlay adapter. The stand-ins mirror the upstream contract
// read in the pinned sources: PCSX2.ini is the default of every PS2 game, a key in a
// game's INI is that game's choice and makes applyGSHardwareFixes skip the GameDB
// blending clamps (PerGameOverrides.cpp), applyGraphicsSettingsNow re-reads both
// layers. No GPU, JIT, VM or rendering result is inferred from this test.
#import <Foundation/Foundation.h>
#include <algorithm>
#include <array>
#include <cassert>
#include <cstring>
#include <string>
#include <string_view>
#include <utility>
#include <vector>
#include "ARMSX2CoreABI.h"

static bool active = true, onCPU = false;
static int applies = 0, flushes = 0;
static NSString* currentGame = @"SLUS-20000_AAAAAAAA";
static NSString* baseIni;
static NSString* gameSettings;
static NSMutableDictionary* baseValues;  // in-memory base layer (deferred save)

enum class AccBlendLevel : unsigned char { Minimum, Basic, Medium, High, Full, Maximum, MaxCount };
struct { struct { AccBlendLevel AccurateBlendingUnit = AccBlendLevel::Basic; } GS; } EmuConfig;

namespace GameDatabaseSchema {
enum class GSHWFixId : unsigned {
  AutoFlush, MinimumBlendingLevel, MaximumBlendingLevel, CopyRoadMaximumBlendingLevel, RecommendedBlendingLevel
};
struct GameEntry { std::vector<std::pair<GSHWFixId, int>> gsHWFixes; };
}
namespace GameDatabase {
static GameDatabaseSchema::GameEntry s_entryB{{
  {GameDatabaseSchema::GSHWFixId::AutoFlush, 1},
  {GameDatabaseSchema::GSHWFixId::MaximumBlendingLevel, 1},
  {GameDatabaseSchema::GSHWFixId::RecommendedBlendingLevel, 4},
}};
const GameDatabaseSchema::GameEntry* findGame(std::string_view serial) {
  return serial == "SLES-50000" ? &s_entryB : nullptr;
}
}
namespace Host {
template <class F> void RunOnCPUThread(F f, bool block) { assert(block); assert(!onCPU); onCPU = true; f(); onCPU = false; }
}
namespace VMManager {
bool HasValidVM() { return active; }
std::string GetDiscSerial() { return std::string([[currentGame componentsSeparatedByString:@"_"][0] UTF8String]); }
}
bool has_running_game() { return active; }
int error_out(const std::string& s, char* out, size_t n) {
  if (out && n) { strncpy(out, s.c_str(), n - 1); out[n - 1] = 0; }
  return 0;
}

static NSString* gameFile(NSString* identity) {
  return [gameSettings stringByAppendingPathComponent:[identity stringByAppendingPathExtension:@"ini"]];
}
static NSMutableDictionary* loadGame(NSString* identity) {
  NSMutableDictionary* values = [NSMutableDictionary dictionaryWithContentsOfFile:gameFile(identity)];
  return values ?: [NSMutableDictionary dictionary];
}
static NSString* k(NSString* section, NSString* key) { return [NSString stringWithFormat:@"%@/%@", section, key]; }

// Reproduces GameDatabaseSchema::GameEntry::applyGSHardwareFixes for the blending
// clamps: a per-game key is a claim and skips them; a global-only value is clamped.
static void applyStandIn() {
  int level = [baseValues[k(@"EmuCore/GS", @"accurate_blending_unit")] intValue];
  if (!baseValues[k(@"EmuCore/GS", @"accurate_blending_unit")]) level = 1;
  NSNumber* game = loadGame(currentGame)[k(@"EmuCore/GS", @"accurate_blending_unit")];
  if (game) level = game.intValue;
  else if (const auto* entry = GameDatabase::findGame(VMManager::GetDiscSerial())) {
    for (const auto& fix : entry->gsHWFixes) {
      if (fix.first == GameDatabaseSchema::GSHWFixId::MinimumBlendingLevel) level = std::max(level, fix.second);
      if (fix.first == GameDatabaseSchema::GSHWFixId::MaximumBlendingLevel) level = std::min(level, fix.second);
    }
  }
  EmuConfig.GS.AccurateBlendingUnit = static_cast<AccBlendLevel>(level);
}

@interface ARMSX2Bridge : NSObject
+ (int)getINIInt:(NSString*)section key:(NSString*)key defaultValue:(int)def;
+ (void)setINIInt:(NSString*)section key:(NSString*)key value:(int)value;
+ (void)flushINISettings;
+ (void)applyGraphicsSettingsNow;
+ (NSString*)perGameIdentityKeyForCurrentGame;
+ (BOOL)hasPerGameINIValue:(NSString*)section key:(NSString*)key forISO:(NSString*)iso;
+ (int)getPerGameINIInt:(NSString*)section key:(NSString*)key defaultValue:(int)def forISO:(NSString*)iso;
+ (void)setPerGameINIInt:(NSString*)section key:(NSString*)key value:(int)value forISO:(NSString*)iso;
+ (void)deletePerGameINIValue:(NSString*)section key:(NSString*)key forISO:(NSString*)iso;
@end
@implementation ARMSX2Bridge
+ (int)getINIInt:(NSString*)section key:(NSString*)key defaultValue:(int)def {
  id v = baseValues[k(section, key)]; return v ? [v intValue] : def;
}
+ (void)setINIInt:(NSString*)section key:(NSString*)key value:(int)value { baseValues[k(section, key)] = @(value); }
+ (void)flushINISettings { ++flushes; assert([baseValues writeToFile:baseIni atomically:YES]); }
+ (void)applyGraphicsSettingsNow { assert(!onCPU); ++applies; applyStandIn(); }
+ (NSString*)perGameIdentityKeyForCurrentGame { return active ? currentGame : @""; }
+ (BOOL)hasPerGameINIValue:(NSString*)section key:(NSString*)key forISO:(NSString*)iso {
  assert(iso == nil); return loadGame(currentGame)[k(section, key)] != nil;
}
+ (int)getPerGameINIInt:(NSString*)section key:(NSString*)key defaultValue:(int)def forISO:(NSString*)iso {
  assert(iso == nil); id v = loadGame(currentGame)[k(section, key)]; return v ? [v intValue] : def;
}
+ (void)setPerGameINIInt:(NSString*)section key:(NSString*)key value:(int)value forISO:(NSString*)iso {
  assert(iso == nil); NSMutableDictionary* values = loadGame(currentGame);
  values[k(section, key)] = @(value); assert([values writeToFile:gameFile(currentGame) atomically:YES]);
}
+ (void)deletePerGameINIValue:(NSString*)section key:(NSString*)key forISO:(NSString*)iso {
  assert(iso == nil); NSMutableDictionary* values = loadGame(currentGame);
  [values removeObjectForKey:k(section, key)]; assert([values writeToFile:gameFile(currentGame) atomically:YES]);
}
@end

#include "ARMSX2BlendingAccuracy.inc"

static NSDictionary* state() {
  char json[2048] = {};
  assert(get_blending_accuracy_json(json, sizeof(json)));
  NSDictionary* decoded = [NSJSONSerialization JSONObjectWithData:[NSData dataWithBytes:json length:strlen(json)]
                                                           options:0 error:nil];
  assert([decoded isKindOfClass:NSDictionary.class]);
  assert([decoded[@"levels"] isEqual:(@[@0, @1, @3, @4, @5])]);  // Medium (2) is never offered
  return decoded;
}
static NSDictionary* disk(NSString* identity) { return [NSDictionary dictionaryWithContentsOfFile:gameFile(identity)]; }
static NSDictionary* baseDisk() { return [NSDictionary dictionaryWithContentsOfFile:baseIni]; }
static void require(bool ok, const char* what) { if (!ok) { fprintf(stderr, "FAIL: %s\n", what); abort(); } }

int main() { @autoreleasepool {
  NSString* temp = [NSTemporaryDirectory() stringByAppendingPathComponent:NSUUID.UUID.UUIDString];
  gameSettings = [temp stringByAppendingPathComponent:@"gamesettings"];
  baseIni = [temp stringByAppendingPathComponent:@"inis/PCSX2.ini"];
  assert([NSFileManager.defaultManager createDirectoryAtPath:gameSettings withIntermediateDirectories:YES attributes:nil error:nil]);
  assert([NSFileManager.defaultManager createDirectoryAtPath:baseIni.stringByDeletingLastPathComponent withIntermediateDirectories:YES attributes:nil error:nil]);
  baseValues = [NSMutableDictionary dictionary];
  baseValues[@"EmuCore/Unrelated"] = @"keep";
  assert([baseValues writeToFile:baseIni atomically:YES]);
  NSMutableDictionary* seedA = [NSMutableDictionary dictionary];
  seedA[@"EmuCore/GS/upscale_multiplier"] = @2;
  assert([seedA writeToFile:gameFile(@"SLUS-20000_AAAAAAAA") atomically:YES]);
  applyStandIn();  // boot of game A
  char error[512] = {};

  // 1. Defaults: no choice anywhere, Basic effective, GameDB silent for game A.
  NSDictionary* s = state();
  require([s[@"available"] boolValue], "available with a running identified game");
  require([s[@"global"] intValue] == 1 && [s[@"game"] intValue] == -1 && [s[@"effective"] intValue] == 1, "defaults");
  require([s[@"gamedbMinimum"] intValue] == -1 && [s[@"gamedbMaximum"] intValue] == -1 && [s[@"gamedbRecommended"] intValue] == -1, "no GameDB entry for A");

  // 2. Rejections write nothing and apply nothing.
  require(!set_blending_accuracy(NEO_ARMSX2_BLENDING_SCOPE_GAME, 2, error, sizeof(error)) && strstr(error, "level"), "Medium refused");
  require(!set_blending_accuracy(NEO_ARMSX2_BLENDING_SCOPE_GAME, 6, error, sizeof(error)), "out of range refused");
  require(!set_blending_accuracy(NEO_ARMSX2_BLENDING_SCOPE_DEFAULT, -1, error, sizeof(error)), "inherit has no meaning for the default");
  require(!set_blending_accuracy(2, 1, error, sizeof(error)) && strstr(error, "scope"), "unknown scope refused");
  require(applies == 0 && flushes == 0 && !disk(@"SLUS-20000_AAAAAAAA")[@"EmuCore/GS/accurate_blending_unit"], "no side effect on refusal");

  // 3. Game A chooses High: its INI only, one live apply, effective follows.
  require(set_blending_accuracy(NEO_ARMSX2_BLENDING_SCOPE_GAME, 3, error, sizeof(error)), "High for game A");
  require(applies == 1, "one live apply");
  require([disk(@"SLUS-20000_AAAAAAAA")[@"EmuCore/GS/accurate_blending_unit"] intValue] == 3, "A persisted on disk");
  require([disk(@"SLUS-20000_AAAAAAAA")[@"EmuCore/GS/upscale_multiplier"] intValue] == 2, "A's other keys kept");
  require(!baseValues[@"EmuCore/GS/accurate_blending_unit"], "base layer untouched by a game choice");
  s = state();
  require([s[@"game"] intValue] == 3 && [s[@"effective"] intValue] == 3 && [s[@"global"] intValue] == 1, "A reads its own choice");

  // 4. Game B (GameDB caps it at Basic, recommends Full) inherits the default.
  currentGame = @"SLES-50000_BBBBBBBB"; applyStandIn();
  s = state();
  require([s[@"game"] intValue] == -1 && [s[@"effective"] intValue] == 1, "B inherits");
  require([s[@"gamedbMaximum"] intValue] == 1 && [s[@"gamedbRecommended"] intValue] == 4 && [s[@"gamedbMinimum"] intValue] == -1, "B's GameDB clamps reported");

  // 5. Default for all games -> Full: flushed to disk, A keeps High, B stays clamped.
  require(set_blending_accuracy(NEO_ARMSX2_BLENDING_SCOPE_DEFAULT, 4, error, sizeof(error)), "default Full");
  require(applies == 2 && flushes == 1, "default applied live and flushed");
  require([baseDisk()[@"EmuCore/GS/accurate_blending_unit"] intValue] == 4 && [baseDisk()[@"EmuCore/Unrelated"] isEqual:@"keep"], "PCSX2.ini stand-in persisted, other keys kept");
  s = state();
  require([s[@"global"] intValue] == 4 && [s[@"game"] intValue] == -1 && [s[@"effective"] intValue] == 1, "B: GameDB maximum still caps the inherited default");
  currentGame = @"SLUS-20000_AAAAAAAA"; applyStandIn();
  s = state();
  require([s[@"global"] intValue] == 4 && [s[@"game"] intValue] == 3 && [s[@"effective"] intValue] == 3, "A: its own choice outranks the new default");

  // 6. B's explicit choice outranks the GameDB cap; inheriting restores it.
  currentGame = @"SLES-50000_BBBBBBBB"; applyStandIn();
  require(set_blending_accuracy(NEO_ARMSX2_BLENDING_SCOPE_GAME, 4, error, sizeof(error)), "Full for game B");
  s = state();
  require([s[@"game"] intValue] == 4 && [s[@"effective"] intValue] == 4, "B: explicit choice skips the GameDB clamp");
  require([disk(@"SLUS-20000_AAAAAAAA")[@"EmuCore/GS/accurate_blending_unit"] intValue] == 3, "A untouched by B");
  require(set_blending_accuracy(NEO_ARMSX2_BLENDING_SCOPE_GAME, NEO_ARMSX2_BLENDING_INHERIT, error, sizeof(error)), "B inherits again");
  require(!disk(@"SLES-50000_BBBBBBBB")[@"EmuCore/GS/accurate_blending_unit"], "B's key removed");
  s = state();
  require([s[@"game"] intValue] == -1 && [s[@"effective"] intValue] == 1, "B: default 4 capped to 1 again");
  require(applies == 4, "every accepted write applied once");

  // 7. Relaunch: fresh readers see only what is on disk.
  baseValues = [NSMutableDictionary dictionaryWithContentsOfFile:baseIni];
  currentGame = @"SLUS-20000_AAAAAAAA"; applyStandIn();
  s = state();
  require([s[@"global"] intValue] == 4 && [s[@"game"] intValue] == 3 && [s[@"effective"] intValue] == 3, "A after relaunch");
  currentGame = @"SLES-50000_BBBBBBBB"; applyStandIn();
  s = state();
  require([s[@"global"] intValue] == 4 && [s[@"game"] intValue] == -1 && [s[@"effective"] intValue] == 1, "B after relaunch");

  // 8. Capacity and inactive session.
  char tiny[16] = {};
  require(!get_blending_accuracy_json(tiny, sizeof(tiny)), "too small a buffer is refused, not truncated");
  active = false;
  require(!get_blending_accuracy_json(error, sizeof(error)), "no JSON without a game");
  require(!set_blending_accuracy(NEO_ARMSX2_BLENDING_SCOPE_GAME, 3, error, sizeof(error)) && strstr(error, "running game"), "no write without a game");
  require(applies == 4, "no apply without a game");
  [NSFileManager.defaultManager removeItemAtPath:temp error:nil];
  puts("PASS: production blending adapter; only the five iPhone levels; default/GameDB/game precedence; two games independent; disk persistence across relaunch; refusals without side effects");
} }
