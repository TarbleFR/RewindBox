// Switch 2 (S2Arm) user settings: the engine's own NSUserDefaults keys and the game language. See S2ArmSettings.h.
#import "S2ArmSettings.h"

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
  if ([key isEqualToString:@"frameRateLimit"]) return @[ @"30", @"60", @"120", @"0" ];
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
  }
  return S2ArmSettingsSnapshot();
}

BOOL S2ArmSettingsPerformanceOverlay(void) {
  return [NSUserDefaults.standardUserDefaults boolForKey:kPerformanceOverlay];
}

void S2ArmSettingsSetPerformanceOverlay(BOOL on) {
  [NSUserDefaults.standardUserDefaults setBool:on forKey:kPerformanceOverlay];
}

void S2ArmSettingsPrepareLaunch(void) {
  NSString *language = S2ArmSettingsSnapshot()[@"gameLanguage"];
  if ([language isEqualToString:@"auto"]) {
    unsetenv("S2A_SYSTEM_LANGUAGE");   // the engine then follows the iPhone's preferred languages (SystemLocale.cs)
  } else {
    setenv("S2A_SYSTEM_LANGUAGE", language.UTF8String, 1);
  }
  // The engine creates its brief overlay only when this key is on at the start; the in-game menu then hides or shows it.
  [NSUserDefaults.standardUserDefaults setBool:YES forKey:kEngineBriefHud];
}
