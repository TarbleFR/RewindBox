// SPDX-License-Identifier: GPL-3.0-or-later
// Blending accuracy of the pinned ARMSX2 2.6 engine (GSdx "Blending Accuracy",
// EmuCore/GS accurate_blending_unit). Every read and write goes through the
// upstream INI layers: PCSX2.ini is the default for all PS2 games, the running
// game's INI is its explicit choice. A key present in the game's INI also makes
// applyGSHardwareFixes skip the GameDB blending clamps for that game
// (PerGameOverrides.cpp), so the order is default -> GameDB profile -> game.
// VMManager::ApplySettings re-reads both layers, applies or skips the GameDB,
// and pushes GSConfig to the GS thread: the level changes for the next draws.
#include "ARMSX2BlendingAccuracy.h"

int blending_default_level() {
  return std::clamp([ARMSX2Bridge getINIInt:@"EmuCore/GS" key:@"accurate_blending_unit"
                                defaultValue:kNeoARMSX2BlendingDefault],0,kNeoARMSX2BlendingMaximum);
}

int get_blending_accuracy_json(char* output,size_t capacity) {
  if(!output || capacity<2 || !has_running_game()) return 0;
  NSData* encoded=nil;
  Host::RunOnCPUThread([&]{
    @autoreleasepool {
      const BOOL available=VMManager::HasValidVM() &&
          [ARMSX2Bridge perGameIdentityKeyForCurrentGame].length>0;
      int game=NEO_ARMSX2_BLENDING_INHERIT;
      if(available && [ARMSX2Bridge hasPerGameINIValue:@"EmuCore/GS" key:@"accurate_blending_unit" forISO:nil])
        game=std::clamp([ARMSX2Bridge getPerGameINIInt:@"EmuCore/GS" key:@"accurate_blending_unit"
                                          defaultValue:kNeoARMSX2BlendingDefault forISO:nil],0,kNeoARMSX2BlendingMaximum);
      int gamedb[3]={-1,-1,-1};
      if(available) {
        if(const GameDatabaseSchema::GameEntry* entry=GameDatabase::findGame(VMManager::GetDiscSerial())) {
          for(const auto& fix:entry->gsHWFixes) {
            if(fix.second<0 || fix.second>kNeoARMSX2BlendingMaximum) continue;
            switch(fix.first) {
              case GameDatabaseSchema::GSHWFixId::MinimumBlendingLevel: gamedb[0]=fix.second; break;
              case GameDatabaseSchema::GSHWFixId::MaximumBlendingLevel: gamedb[1]=fix.second; break;
              case GameDatabaseSchema::GSHWFixId::RecommendedBlendingLevel: gamedb[2]=fix.second; break;
              default: break;
            }
          }
        }
      }
      NSMutableArray* levels=[NSMutableArray array];
      for(int level:kNeoARMSX2BlendingLevels) [levels addObject:@(level)];
      // The core is MRC; retain bytes across the CPU thread's autorelease pool.
      encoded=[[NSJSONSerialization dataWithJSONObject:@{
        @"available":@(available), @"global":@(blending_default_level()), @"game":@(game),
        @"effective":@(static_cast<int>(EmuConfig.GS.AccurateBlendingUnit)),
        @"gamedbMinimum":@(gamedb[0]), @"gamedbMaximum":@(gamedb[1]), @"gamedbRecommended":@(gamedb[2]),
        @"levels":levels
      } options:0 error:nil] retain];
    }
  },true);
  if(!encoded) return 0;
  const BOOL fits=encoded.length+1<=capacity;
  if(fits) { memcpy(output,encoded.bytes,encoded.length); output[encoded.length]=0; }
  [encoded release];
  return fits ? 1 : 0;
}

int set_blending_accuracy(uint32_t scope,int level,char* error,size_t capacity) {
  if(scope!=NEO_ARMSX2_BLENDING_SCOPE_GAME && scope!=NEO_ARMSX2_BLENDING_SCOPE_DEFAULT)
    return error_out("Unsupported ARMSX2 blending accuracy scope.",error,capacity);
  const bool inherit=scope==NEO_ARMSX2_BLENDING_SCOPE_GAME && level==NEO_ARMSX2_BLENDING_INHERIT;
  if(!inherit && !NeoARMSX2BlendingLevelOffered(level))
    return error_out("Unsupported ARMSX2 blending accuracy level for this engine.",error,capacity);
  if(!has_running_game()) return error_out("ARMSX2 blending accuracy requires a running game.",error,capacity);
  BOOL success=NO;
  Host::RunOnCPUThread([&]{
    @autoreleasepool {
      if(!VMManager::HasValidVM()) return;
      if(scope==NEO_ARMSX2_BLENDING_SCOPE_DEFAULT) {
        // Base layer: the in-memory interface is updated at once, the disk copy
        // is normally deferred; flush it so the default survives a termination.
        [ARMSX2Bridge setINIInt:@"EmuCore/GS" key:@"accurate_blending_unit" value:level];
        [ARMSX2Bridge flushINISettings];
        success=[ARMSX2Bridge getINIInt:@"EmuCore/GS" key:@"accurate_blending_unit" defaultValue:-1]==level;
        return;
      }
      if(![ARMSX2Bridge perGameIdentityKeyForCurrentGame].length) return;
      // Per-game writer: this game's INI only, saved immediately. Never the
      // global pin setter: one game's choice must not change the others.
      if(inherit) [ARMSX2Bridge deletePerGameINIValue:@"EmuCore/GS" key:@"accurate_blending_unit" forISO:nil];
      else [ARMSX2Bridge setPerGameINIInt:@"EmuCore/GS" key:@"accurate_blending_unit" value:level forISO:nil];
      const BOOL present=[ARMSX2Bridge hasPerGameINIValue:@"EmuCore/GS" key:@"accurate_blending_unit" forISO:nil];
      success=inherit ? !present : (present &&
          [ARMSX2Bridge getPerGameINIInt:@"EmuCore/GS" key:@"accurate_blending_unit" defaultValue:-1 forISO:nil]==level);
    }
  },true);
  if(!success) return error_out("ARMSX2 could not persist the blending accuracy.",error,capacity);
  [ARMSX2Bridge applyGraphicsSettingsNow];
  return 1;
}
