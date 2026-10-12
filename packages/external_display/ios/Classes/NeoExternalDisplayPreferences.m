// SPDX-License-Identifier: GPL-3.0-or-later
#import "NeoExternalDisplayPreferences.h"

NSString *const NeoExternalDisplayEnabledKey = @"NeoStation.ExternalDisplay.Enabled";
NSString *const NeoExternalDisplayModeKey = @"NeoStation.ExternalDisplay.Mode";
NSString *const NeoExternalDisplayMenuOnTVKey = @"NeoStation.ExternalDisplay.MenuOnTV";
NSString *const NeoExternalDisplayLegacyDolphinModeKey = @"NeoStation.Dolphin.ExternalDisplay.Mode";
NSString *const NeoExternalDisplayChangedNotification = @"NeoStation.ExternalDisplayChanged";

@implementation NeoExternalDisplayPreferences

/// The Build 442 Dolphin value, or NSNotFound when it was never stored.
+ (NSInteger)legacyDolphinMode {
  id legacy = [NSUserDefaults.standardUserDefaults objectForKey:NeoExternalDisplayLegacyDolphinModeKey];
  return [legacy isKindOfClass:NSNumber.class] ? [(NSNumber *)legacy integerValue] : NSNotFound;
}

+ (BOOL)enabled {
  NSUserDefaults *defaults = NSUserDefaults.standardUserDefaults;
  id stored = [defaults objectForKey:NeoExternalDisplayEnabledKey];
  if ([stored isKindOfClass:NSNumber.class]) return [(NSNumber *)stored boolValue];
  // Never chosen globally: a Dolphin user who turned the 442 output off keeps
  // system mirroring until the global switch is used.
  if ([defaults objectForKey:NeoExternalDisplayModeKey] == nil && [self legacyDolphinMode] == 0) return NO;
  return YES;
}

+ (NeoExternalDisplayMode)mode {
  id stored = [NSUserDefaults.standardUserDefaults objectForKey:NeoExternalDisplayModeKey];
  if (stored != nil) return NeoExternalDisplayModeFromValue(stored);
  switch ([self legacyDolphinMode]) {
    case 1: return NeoExternalDisplayModeFit;
    case 2: return NeoExternalDisplayModeFill;
    default: return NeoExternalDisplayModeAutomatic;
  }
}

+ (BOOL)menuOnTV {
  id stored = [NSUserDefaults.standardUserDefaults objectForKey:NeoExternalDisplayMenuOnTVKey];
  return [stored isKindOfClass:NSNumber.class] ? [(NSNumber *)stored boolValue] : YES;
}

/// Writes and reads back; NO when NSUserDefaults did not keep the value.
+ (BOOL)writeNumber:(NSNumber *)value forKey:(NSString *)key {
  NSUserDefaults *defaults = NSUserDefaults.standardUserDefaults;
  [defaults setObject:value forKey:key];
  id stored = [defaults objectForKey:key];
  return [stored isKindOfClass:NSNumber.class] && [(NSNumber *)stored isEqualToNumber:value];
}

/// Writes, reads back, and only then tells the live session.
+ (BOOL)storeNumber:(NSNumber *)value forKey:(NSString *)key {
  if (![self writeNumber:value forKey:key]) return NO;
  [NSNotificationCenter.defaultCenter postNotificationName:NeoExternalDisplayChangedNotification object:nil];
  return YES;
}

+ (BOOL)storeEnabled:(BOOL)enabled {
  return [self storeNumber:@(enabled) forKey:NeoExternalDisplayEnabledKey];
}

+ (BOOL)storeMode:(NeoExternalDisplayMode)mode {
  if (mode < NeoExternalDisplayModeAutomatic || mode > NeoExternalDisplayModeOriginal) return NO;
  NSUserDefaults *defaults = NSUserDefaults.standardUserDefaults;
  // The Enabled value of a user who never used the global switch is derived
  // from the absence of the Mode key (442 Dolphin Off → disabled). Storing
  // the mode ends that fallback, so the derived value is persisted first
  // (no notification: it does not change): choosing a format never turns
  // the external display on by itself.
  if ([defaults objectForKey:NeoExternalDisplayEnabledKey] == nil && [defaults objectForKey:NeoExternalDisplayModeKey] == nil &&
      ![self writeNumber:@([self enabled]) forKey:NeoExternalDisplayEnabledKey]) {
    return NO;
  }
  return [self storeNumber:@((NSInteger)mode) forKey:NeoExternalDisplayModeKey];
}

+ (BOOL)storeMenuOnTV:(BOOL)enabled {
  return [self storeNumber:@(enabled) forKey:NeoExternalDisplayMenuOnTVKey];
}

@end
