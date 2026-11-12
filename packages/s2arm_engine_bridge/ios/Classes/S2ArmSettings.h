#pragma once
// Switch 2 (S2Arm) user settings, as the engine reads them. See docs/s2arm-engine-bridge.md, Settings and in-game menu.
//
// The engine reads its picture settings from the app's standard NSUserDefaults when a game starts (S2Arm ios/settings.m
// s2a_ios_apply_graphics_settings, called once per process from host_run). In this app that domain is RewindBox's own, so
// the RewindBox settings screen and S2Arm's own in-game settings page write the same keys and always agree. The game
// language is the S2A_SYSTEM_LANGUAGE environment variable, set before the engine starts. No engine change.
#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

// The method-channel map (keys resolutionScale, antiAliasing, scalingFilter, frameRateLimit, docked, widescreen,
// performanceOverlay, gameLanguage), with defaults for anything not stored. A resolution scale above 1 has no effect in
// the engine's direct mode (the only mode it ships), so it is reported as "1".
NSDictionary<NSString *, id> *S2ArmSettingsSnapshot(void);

// Validates and stores any subset of that map (unknown keys and values are ignored), then returns the new snapshot.
NSDictionary<NSString *, id> *S2ArmSettingsApply(NSDictionary *changes);

// Before the engine starts: exports the game language (or clears it for "auto") and turns on the engine's own brief
// performance overlay, which S2ArmSessionMenu then shows or hides live according to performanceOverlay.
void S2ArmSettingsPrepareLaunch(void);

// The values the in-game menu offers, in display order.
NSArray<NSString *> *S2ArmSettingsValues(NSString *key);

// Whether the performance overlay is wanted (the RewindBox preference).
BOOL S2ArmSettingsPerformanceOverlay(void);
void S2ArmSettingsSetPerformanceOverlay(BOOL on);

NS_ASSUME_NONNULL_END
