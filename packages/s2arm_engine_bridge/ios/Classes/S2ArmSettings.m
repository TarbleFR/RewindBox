// Switch 2 (S2Arm) user settings: the engine's own NSUserDefaults keys, the game language and the settings profiles by game.
// See S2ArmSettings.h.
#import "S2ArmSettings.h"
#import "S2ArmGameEnvironment.h"
#import "S2ArmLaunchJournal.h"

#include <stdlib.h>

// The engine's keys (S2Arm ios/settings.m:79-108 and ios/Settings.bundle/Root.plist at the pinned commit).
static NSString *const kResolution = @"S2AResolutionScale";
static NSString *const kAntiAliasing = @"S2AAntiAliasing";
static NSString *const kScalingFilter = @"S2AScalingFilter";
static NSString *const kFrameRateLimit = @"S2AFrameRateLimit";
static NSString *const kDocked = @"S2ADockedMode";
static NSString *const kWidescreen = @"S2AWidescreen";
static NSString *const kEngineBriefHud = @"S2APerfHUD";   // S2Arm hud.m: the "FPS · memory" pill, restored when a game starts
// RewindBox's own keys.
static NSString *const kPerformanceOverlay = @"RewindBoxS2ArmPerformanceOverlay";
static NSString *const kGameLanguage = @"RewindBoxS2ArmGameLanguage";
// Frame generation (engine patch 0345): the engine reads S2A_RB_FI, never this key; the bridge sets it from this key at the game's start.
static NSString *const kFrameInterpolation = @"RewindBoxS2ArmFrameInterpolation";
// The settings profiles by game: title id (S2ArmSettingsGameKey) -> the map's keys. RewindBox's own preference, never the
// engine's per-game suite S2AGame.<id> (S2AFps60, S2AWidenForce: ios/settings.m reads it when S2A_LAUNCH_GAME_ID is set, and
// nothing in RewindBox writes it).
static NSString *const kGameProfiles = @"RewindBoxS2ArmGameSettings";
// Their copy in Documents/S2Arm. An update that moves the app to a new container keeps Documents but can start with empty
// preferences (build 586, 28 October 2026: a Switch 1 game started at 1.0 right after the update although it was set to 0.75).
static NSString *const kGameProfilesCopy = @"rewindbox-game-settings.json";

// The SystemLanguage names the engine's services accept in S2A_SYSTEM_LANGUAGE (S2Arm services Host.cs EnvEnum).
static NSArray<NSString *> *GameLanguages(void) {
  return @[
    @"auto", @"AmericanEnglish", @"BritishEnglish", @"French", @"CanadianFrench", @"German", @"Italian", @"Spanish",
    @"LatinAmericanSpanish", @"Dutch", @"Portuguese", @"BrazilianPortuguese", @"Russian", @"Polish", @"Japanese", @"Korean",
    @"SimplifiedChinese", @"TraditionalChinese", @"Thai"
  ];
}

NSArray<NSString *> *S2ArmSettingsValues(NSString *key) {
  if ([key isEqualToString:@"resolutionScale"]) return @[ @"0.5", @"0.75", @"1" ];
  if ([key isEqualToString:@"antiAliasing"]) return @[ @"None", @"SmaaMedium", @"SmaaHigh" ];
  if ([key isEqualToString:@"scalingFilter"]) return @[ @"Bilinear", @"Nearest" ];
  // Engine patch 0319: no 30. Mario Kart World stayed locked at 30 fps in IPA 825 (never from this setting), and 30 is never chosen.
  if ([key isEqualToString:@"frameRateLimit"]) return @[ @"60", @"120", @"0" ];
  if ([key isEqualToString:@"gameLanguage"]) return GameLanguages();
  return @[];
}

static NSString *StoredChoice(NSUserDefaults *defaults, NSString *key, NSString *fallback, NSArray<NSString *> *allowed) {
  id value = [defaults objectForKey:key];
  return [value isKindOfClass:NSString.class] && [allowed containsObject:value] ? value : fallback;
}

NSDictionary<NSString *, id> *S2ArmSettingsSnapshot(void) {
  NSUserDefaults *defaults = NSUserDefaults.standardUserDefaults;
  // The engine also accepts 1.5 and 2, written by its own settings page; in direct mode they act as 1.
  NSString *scale = StoredChoice(defaults, kResolution, @"1", @[ @"0.5", @"0.75", @"1", @"1.5", @"2" ]);
  if ([scale isEqualToString:@"1.5"] || [scale isEqualToString:@"2"]) scale = @"1";
  // Widescreen is on unless it was stored as NO (S2Arm settings.m:137).
  id wide = [defaults objectForKey:kWidescreen];
  BOOL widescreen = wide == nil ? YES : [defaults boolForKey:kWidescreen];  // a BOOL, so Dart gets true / false
  return @{
    @"resolutionScale" : scale,
    @"antiAliasing" : StoredChoice(defaults, kAntiAliasing, @"None", S2ArmSettingsValues(@"antiAliasing")),
    @"scalingFilter" : StoredChoice(defaults, kScalingFilter, @"Bilinear", S2ArmSettingsValues(@"scalingFilter")),
    @"frameRateLimit" : StoredChoice(defaults, kFrameRateLimit, @"0", S2ArmSettingsValues(@"frameRateLimit")),
    @"frameInterpolation" : @([defaults boolForKey:kFrameInterpolation]),   // off unless stored as YES
    @"docked" : @([defaults boolForKey:kDocked]),
    @"widescreen" : @(widescreen),
    @"performanceOverlay" : @([defaults boolForKey:kPerformanceOverlay]),
    @"gameLanguage" : StoredChoice(defaults, kGameLanguage, @"auto", GameLanguages()),
  };
}

static void StoreChoice(NSUserDefaults *defaults, NSDictionary *changes, NSString *name, NSString *key) {
  id value = changes[name];
  if ([value isKindOfClass:NSString.class] && [S2ArmSettingsValues(name) containsObject:value]) [defaults setObject:value forKey:key];
}

static void StoreFlag(NSUserDefaults *defaults, NSDictionary *changes, NSString *name, NSString *key) {
  id value = changes[name];
  if ([value isKindOfClass:NSNumber.class]) [defaults setBool:[value boolValue] forKey:key];
}

NSDictionary<NSString *, id> *S2ArmSettingsApply(NSDictionary *changes) {
  if ([changes isKindOfClass:NSDictionary.class]) {
    NSUserDefaults *defaults = NSUserDefaults.standardUserDefaults;
    StoreChoice(defaults, changes, @"resolutionScale", kResolution);
    StoreChoice(defaults, changes, @"antiAliasing", kAntiAliasing);
    StoreChoice(defaults, changes, @"scalingFilter", kScalingFilter);
    StoreChoice(defaults, changes, @"frameRateLimit", kFrameRateLimit);
    StoreChoice(defaults, changes, @"gameLanguage", kGameLanguage);
    StoreFlag(defaults, changes, @"docked", kDocked);
    StoreFlag(defaults, changes, @"widescreen", kWidescreen);
    StoreFlag(defaults, changes, @"performanceOverlay", kPerformanceOverlay);
    StoreFlag(defaults, changes, @"frameInterpolation", kFrameInterpolation);
  }
  return S2ArmSettingsSnapshot();
}

#pragma mark - settings profiles by game

NSString *S2ArmSettingsGameKey(NSString *gid) {
  if (![gid isKindOfClass:NSString.class] || gid.length != 16) return nil;
  NSCharacterSet *other = [NSCharacterSet characterSetWithCharactersInString:@"0123456789ABCDEFabcdef"].invertedSet;
  return [gid rangeOfCharacterFromSet:other].location == NSNotFound ? gid.uppercaseString : nil;
}

// The valid entries of a profile, or of changes to one: each value one the global settings take (S2ArmSettingsValues, so a
// frame-rate limit of 30 is never kept), flags as BOOL. A setting a profile lacks (or holds a value no longer offered for)
// comes from the global settings.
static NSDictionary<NSString *, id> *ValidProfile(id stored) {
  NSMutableDictionary<NSString *, id> *profile = [NSMutableDictionary dictionary];
  if (![stored isKindOfClass:NSDictionary.class]) return profile;
  NSDictionary *map = stored;
  for (NSString *name in @[ @"resolutionScale", @"antiAliasing", @"scalingFilter", @"frameRateLimit", @"gameLanguage" ]) {
    id value = map[name];
    if ([value isKindOfClass:NSString.class] && [S2ArmSettingsValues(name) containsObject:value]) profile[name] = value;
  }
  for (NSString *name in @[ @"frameInterpolation", @"docked", @"widescreen", @"performanceOverlay" ]) {
    id value = map[name];
    if ([value isKindOfClass:NSNumber.class]) profile[name] = [value boolValue] ? @YES : @NO;   // a BOOL, so Dart gets true / false
  }
  return profile;
}

static NSDictionary<NSString *, NSDictionary *> *ValidProfiles(id stored) {
  NSMutableDictionary<NSString *, NSDictionary *> *profiles = [NSMutableDictionary dictionary];
  if (![stored isKindOfClass:NSDictionary.class]) return profiles;
  NSDictionary *map = stored;
  for (id gid in map) {
    NSString *key = [gid isKindOfClass:NSString.class] ? S2ArmSettingsGameKey(gid) : nil;
    if (key && [map[gid] isKindOfClass:NSDictionary.class]) profiles[key] = ValidProfile(map[gid]);
  }
  return profiles;
}

// The profiles are read and written under this lock: the method channel and the in-game menu on the main thread, the launch on
// the bridge's work queue.
static NSObject *ProfilesLock(void) {
  static NSObject *lock;
  static dispatch_once_t once;
  dispatch_once(&once, ^{ lock = [NSObject new]; });
  return lock;
}

static NSString *ProfilesCopyPath(void) {
  NSString *documents = NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES).firstObject;
  return documents.length ? [[documents stringByAppendingPathComponent:@"S2Arm"] stringByAppendingPathComponent:kGameProfilesCopy] : nil;
}

static id ReadProfilesCopy(void) {
  NSString *path = ProfilesCopyPath();
  NSData *data = path ? [NSData dataWithContentsOfFile:path] : nil;
  return data ? [NSJSONSerialization JSONObjectWithData:data options:0 error:NULL] : nil;
}

// Every game's profile (caller holds the lock). The preference is the primary copy. When it is missing (an update that
// started with empty preferences), the Documents copy is read, once a process, and put back.
static NSDictionary<NSString *, NSDictionary *> *StoredProfiles(void) {
  static BOOL restoreTried;
  NSUserDefaults *defaults = NSUserDefaults.standardUserDefaults;
  id stored = [defaults objectForKey:kGameProfiles];
  if (!stored && !restoreTried) {
    restoreTried = YES;
    id copy = ReadProfilesCopy();
    if ([copy isKindOfClass:NSDictionary.class]) {
      stored = ValidProfiles(copy);
      [defaults setObject:stored forKey:kGameProfiles];
      s2arm_journal("gameSettings", "restored", "\"games\":%lu", (unsigned long)[stored count]);
    }
  }
  return ValidProfiles(stored);
}

// Stores every game's profile (caller holds the lock): the preference, then its Documents copy, written whole and atomically.
// No profile left is stored as an empty map, so that a missing preference still means one an update lost.
static void StoreProfiles(NSDictionary<NSString *, NSDictionary *> *profiles) {
  [NSUserDefaults.standardUserDefaults setObject:profiles forKey:kGameProfiles];
  NSString *path = ProfilesCopyPath();
  NSData *data = [NSJSONSerialization dataWithJSONObject:profiles options:NSJSONWritingSortedKeys error:NULL];
  BOOL copied = path && data &&
                [NSFileManager.defaultManager createDirectoryAtPath:path.stringByDeletingLastPathComponent
                                        withIntermediateDirectories:YES attributes:nil error:NULL] &&
                [data writeToFile:path options:NSDataWritingAtomic error:NULL];
  if (!copied) s2arm_journal("gameSettings", "copyFailed", NULL);   // the preference still holds them
}

// At a game's start: the Documents copy is written again when it is missing or differs (deleted in Files, a failed write).
static void KeepProfilesCopy(void) {
  @synchronized(ProfilesLock()) {
    NSDictionary *profiles = StoredProfiles();
    BOOL stored = [NSUserDefaults.standardUserDefaults objectForKey:kGameProfiles] != nil;   // no game ever had a profile otherwise
    if (stored && ![ValidProfiles(ReadProfilesCopy()) isEqual:profiles]) StoreProfiles(profiles);
  }
}

static NSDictionary *_Nullable StoredProfile(NSString *_Nullable gid) {
  NSString *key = S2ArmSettingsGameKey(gid);
  NSDictionary *profile = nil;
  if (key) {
    @synchronized(ProfilesLock()) {
      profile = StoredProfiles()[key];
    }
  }
  return profile;
}

BOOL S2ArmSettingsGameHasProfile(NSString *gid) {
  return StoredProfile(gid) != nil;
}

NSDictionary<NSString *, id> *S2ArmSettingsForGame(NSString *gid) {
  NSDictionary *profile = StoredProfile(gid);
  NSDictionary<NSString *, id> *global = S2ArmSettingsSnapshot();
  if (!profile) return global;
  NSMutableDictionary<NSString *, id> *settings = [global mutableCopy];
  [settings addEntriesFromDictionary:profile];
  return settings;
}

NSDictionary<NSString *, id> *S2ArmSettingsGameCreateProfile(NSString *gid) {
  NSString *key = S2ArmSettingsGameKey(gid);
  if (!key) return nil;
  @synchronized(ProfilesLock()) {
    NSMutableDictionary<NSString *, NSDictionary *> *profiles = [StoredProfiles() mutableCopy];
    if (!profiles[key]) {
      profiles[key] = ValidProfile(S2ArmSettingsSnapshot());   // every setting, at its global value of the moment
      StoreProfiles(profiles);
      s2arm_journal("gameSettings", "created", "\"gid\":\"%s\"", key.UTF8String);
    }
  }
  return S2ArmSettingsForGame(key);
}

NSDictionary<NSString *, id> *S2ArmSettingsGameApply(NSString *gid, NSDictionary *changes) {
  NSString *key = S2ArmSettingsGameKey(gid);
  BOOL found = NO;
  if (key) {
    @synchronized(ProfilesLock()) {
      NSMutableDictionary<NSString *, NSDictionary *> *profiles = [StoredProfiles() mutableCopy];
      NSDictionary *profile = profiles[key];
      found = profile != nil;
      NSMutableDictionary *next = [profile mutableCopy];
      [next addEntriesFromDictionary:ValidProfile(changes)];
      if (found && ![next isEqual:profile]) {
        profiles[key] = next;
        StoreProfiles(profiles);
      }
    }
  }
  return found ? S2ArmSettingsForGame(key) : nil;
}

NSDictionary<NSString *, id> *S2ArmSettingsGameRemoveProfile(NSString *gid) {
  NSString *key = S2ArmSettingsGameKey(gid);
  if (key) {
    @synchronized(ProfilesLock()) {
      NSMutableDictionary<NSString *, NSDictionary *> *profiles = [StoredProfiles() mutableCopy];
      if (profiles[key]) {
        [profiles removeObjectForKey:key];
        StoreProfiles(profiles);
        s2arm_journal("gameSettings", "removed", "\"gid\":\"%s\"", key.UTF8String);
      }
    }
  }
  return S2ArmSettingsSnapshot();
}

NSDictionary<NSString *, id> *S2ArmSettingsApplyForGame(NSString *gid, NSDictionary *changes) {
  return S2ArmSettingsGameApply(gid, changes) ?: S2ArmSettingsApply(changes);
}

BOOL S2ArmSettingsPerformanceOverlay(NSString *gid) {
  return [S2ArmSettingsForGame(gid)[@"performanceOverlay"] boolValue];
}

void S2ArmSettingsSetPerformanceOverlay(NSString *gid, BOOL on) {
  (void)S2ArmSettingsApplyForGame(gid, @{@"performanceOverlay" : on ? @YES : @NO});
}

BOOL S2ArmSettingsFrameInterpolation(NSString *gid) {
  return [S2ArmSettingsForGame(gid)[@"frameInterpolation"] boolValue];
}

#pragma mark - launch

// The engine's variables of the picture settings, read at a game's start before their NSUserDefaults keys (S2Arm ios/settings.m
// s2a_ios_apply_graphics_settings, from host_run at the first start of a process, again from s2a_host_rebuild when a parked
// game resumes; a variable already set is used as it is, its key stays as stored), with the values the engine takes: any
// other value stops the game (services GraphicsSettings.cs throws, graphics nvn_present_aa.inc and nvn_fps.c abort), so only
// S2ArmSettingsValues values. S2A_RES_SCALE 0.5 / 0.75 / 1; S2A_ANTI_ALIASING None / SmaaMedium / SmaaHigh; S2A_SCALING_FILTER
// Bilinear / Nearest; S2A_FPS 60 / 120 / 0 (no limit); S2A_DOCKED 1 docked, 0 handheld (services Host.cs, widen.c, the quality
// ladder's upper bound in qladder_host.c); S2A_WIDESCREEN 0 is 16:9 with black bars, 1 widescreen as when unset (widen.c). The
// direct graphics read the scale, the filters and the limit once a process (a resumed game keeps them; the limit then changes
// live, applyStoredFrameRateLimit:); the services and widen.c read the console mode and the image format at each session.
static NSArray<NSString *> *GameVariables(void) {
  return @[ @"S2A_RES_SCALE", @"S2A_ANTI_ALIASING", @"S2A_SCALING_FILTER", @"S2A_FPS", @"S2A_DOCKED", @"S2A_WIDESCREEN" ];
}

static NSDictionary<NSString *, NSString *> *GameEnvironment(NSDictionary *settings) {
  NSString *docked = [settings[@"docked"] boolValue] ? @"1" : @"0";
  NSString *widescreen = [settings[@"widescreen"] boolValue] ? @"1" : @"0";
  return @{
    @"S2A_RES_SCALE" : settings[@"resolutionScale"] ?: @"1",
    @"S2A_ANTI_ALIASING" : settings[@"antiAliasing"] ?: @"None",
    @"S2A_SCALING_FILTER" : settings[@"scalingFilter"] ?: @"Bilinear",
    @"S2A_FPS" : settings[@"frameRateLimit"] ?: @"0",
    @"S2A_DOCKED" : docked,
    @"S2A_WIDESCREEN" : widescreen,
  };
}

// The values this bridge put in the environment for a game's profile, by variable (the launch runs on the bridge's serial work queue).
static NSMutableDictionary<NSString *, NSString *> *gGameEnvironment;

// The game's profile as the engine's variables. A value from elsewhere (the launch environment, env.txt, the engine's own
// reading of the global keys at an earlier start) is kept: setenv without overwrite. Only this bridge's own value of an
// earlier start of this process (a parked game that resumes) is replaced, or removed when the game has no profile any more:
// the engine's rebuild then reads the global keys again. The journal names the variables, never their values.
static void ExportGameProfile(NSString *_Nullable gid) {
  BOOL profile = S2ArmSettingsGameHasProfile(gid);
  NSDictionary<NSString *, NSString *> *wanted = profile ? GameEnvironment(S2ArmSettingsForGame(gid)) : @{};
  if (!gGameEnvironment) gGameEnvironment = [NSMutableDictionary dictionary];
  NSMutableArray<NSString *> *given = [NSMutableArray array], *kept = [NSMutableArray array];
  for (NSString *name in GameVariables()) {
    NSString *value = wanted[name];
    const char *variable = name.UTF8String;
    s2arm_game_env_action action = s2arm_game_env_decide(getenv(variable), gGameEnvironment[name].UTF8String, value.UTF8String);
    if (action == S2ARM_GAME_ENV_SET || action == S2ARM_GAME_ENV_REPLACE) {
      if (setenv(variable, value.UTF8String, action == S2ARM_GAME_ENV_REPLACE) == 0) {
        gGameEnvironment[name] = value;
        [given addObject:name];
        continue;
      }
    } else if (action == S2ARM_GAME_ENV_UNSET) {
      unsetenv(variable);
    } else if (value) {
      [kept addObject:name];
    }
    [gGameEnvironment removeObjectForKey:name];
  }
  s2arm_journal("gameSettings", profile ? "profile" : "global", "\"gid\":\"%s\",\"given\":\"%s\",\"kept\":\"%s\"",
                (S2ArmSettingsGameKey(gid) ?: @"").UTF8String, [given componentsJoinedByString:@","].UTF8String,
                [kept componentsJoinedByString:@","].UTF8String);
}

// A frame-rate limit no longer offered (30, stored by IPA 826 and earlier) reads as no limit and is removed before the engine reads it.
static void S2ArmSettingsForgetRetiredLimit(void) {
  NSUserDefaults *defaults = NSUserDefaults.standardUserDefaults;
  id stored = [defaults objectForKey:kFrameRateLimit];
  if (stored && !([stored isKindOfClass:NSString.class] && [S2ArmSettingsValues(@"frameRateLimit") containsObject:stored]))
    [defaults removeObjectForKey:kFrameRateLimit];
}

void S2ArmSettingsPrepareLaunch(NSString *gid) {
  S2ArmSettingsForgetRetiredLimit();
  KeepProfilesCopy();
  NSString *language = S2ArmSettingsForGame(gid)[@"gameLanguage"];   // the game's profile when it has one, else the global choice
  if ([language isEqualToString:@"auto"]) {
    unsetenv("S2A_SYSTEM_LANGUAGE");   // the engine then follows the iPhone's preferred languages (SystemLocale.cs)
  } else {
    setenv("S2A_SYSTEM_LANGUAGE", language.UTF8String, 1);
  }
  // The engine creates its brief overlay only when this key is on at the start; the in-game menu then hides or shows it.
  [NSUserDefaults.standardUserDefaults setBool:YES forKey:kEngineBriefHud];
  ExportGameProfile(gid);
}
