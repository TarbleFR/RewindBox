// SPDX-License-Identifier: GPL-3.0-or-later
// Phone-shake preferences of the first emulated Wii Remote (Build 442).
// Shared by the in-game Controls menu, the Flutter Wii settings panel (method
// channel of the bridge) and DolphinShakeSensitivity.swift, which reads the
// same keys and raw values. Plain NSUserDefaults; no core setting is written.
#pragma once
#import <Foundation/Foundation.h>

static NSString* const DOLPhoneShakeKey = @"NeoStation.Dolphin.PhoneShake.Enabled";
static NSString* const DOLPhoneShakeSensitivityKey = @"NeoStation.Dolphin.PhoneShake.Sensitivity";
static NSString* const DOLPhoneShakeChangedNotification = @"NeoStation.Dolphin.PhoneShakeChanged";

static inline NSArray<NSString*>* DOLPhoneShakeSensitivityLevels(void) {
  return @[@"low", @"medium", @"high"];
}

static inline BOOL DOLPhoneShakeEnabled(void) {
  id value = [NSUserDefaults.standardUserDefaults objectForKey:DOLPhoneShakeKey];
  return value == nil || [value boolValue];
}

/// "low", "medium" (default) or "high"; unknown or missing values read as medium.
static inline NSString* DOLPhoneShakeSensitivity(void) {
  id value = [NSUserDefaults.standardUserDefaults objectForKey:DOLPhoneShakeSensitivityKey];
  NSString* raw = [value isKindOfClass:NSString.class]
      ? [[value stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet] lowercaseString]
      : @"";
  return [DOLPhoneShakeSensitivityLevels() containsObject:raw] ? raw : @"medium";
}

static inline NSString* DOLPhoneShakeNextSensitivity(NSString* current) {
  NSArray* order = DOLPhoneShakeSensitivityLevels();
  NSUInteger index = [order indexOfObject:current];
  return order[index == NSNotFound ? 1 : (index + 1) % order.count];
}

static inline NSString* DOLPhoneShakeSensitivityLabelKey(NSString* level) {
  if ([level isEqual:@"low"]) return @"shakeSensitivityLow";
  if ([level isEqual:@"high"]) return @"shakeSensitivityHigh";
  return @"shakeSensitivityMedium";
}

static inline NSDictionary* DOLPhoneShakeSettingsSnapshot(void) {
  return @{@"enabled": @(DOLPhoneShakeEnabled()), @"sensitivity": DOLPhoneShakeSensitivity()};
}

/// Writes the given values (nil leaves a value unchanged), then notifies the
/// live overlay. Returns NO when a provided value is invalid; nothing is
/// written in that case.
static inline BOOL DOLPhoneShakeApplySettings(id enabled, id sensitivity) {
  NSString* level = nil;
  if (sensitivity != nil) {
    if (![sensitivity isKindOfClass:NSString.class]) return NO;
    level = [[sensitivity stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet] lowercaseString];
    if (![DOLPhoneShakeSensitivityLevels() containsObject:level]) return NO;
  }
  if (enabled != nil && ![enabled isKindOfClass:NSNumber.class]) return NO;
  NSUserDefaults* defaults = NSUserDefaults.standardUserDefaults;
  if (enabled != nil) [defaults setBool:[enabled boolValue] forKey:DOLPhoneShakeKey];
  if (level != nil) [defaults setObject:level forKey:DOLPhoneShakeSensitivityKey];
  [NSNotificationCenter.defaultCenter postNotificationName:DOLPhoneShakeChangedNotification object:nil];
  return YES;
}
