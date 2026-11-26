#pragma once
// Switch 2 (S2Arm) user settings, as the engine reads them. See docs/s2arm-engine-bridge.md, Settings and in-game menu.
//
// The engine reads its picture settings from the app's standard NSUserDefaults when a game starts (S2Arm ios/settings.m
// s2a_ios_apply_graphics_settings, called once per process from host_run). In this app that domain is RewindBox's own, so
// the RewindBox settings screen and S2Arm's own in-game settings page write the same keys and always agree. The game
// language is the S2A_SYSTEM_LANGUAGE environment variable, set before the engine starts. No engine change. Frame
// generation (engine patch 0345) is RewindBox's own key, given to the engine as S2A_RB_FI by the bridge before it starts.
//
// Settings profiles by game (not the title profile of engine switches, journal gameProfile): a game without one uses the
// global settings above. A profile is made from the global values of the moment, then each value changes for that game
// alone; a global change leaves it as it is; removing it brings the game back to the global settings. The key is the title
// id the launch gives the engine (16 hexadecimal digits). The global keys are never rewritten for a profile: the launch
// gives it to the engine as the environment variables the engine reads before those keys (S2A_RES_SCALE,
// S2A_ANTI_ALIASING, S2A_SCALING_FILTER, S2A_FPS, S2A_DOCKED, S2A_WIDESCREEN), and a value already in the environment (the
// launch environment, Documents/env.txt) still wins (S2ArmGameEnvironment.h). Profiles are stored in RewindBox's own
// preferences, with a copy in Documents/S2Arm/rewindbox-game-settings.json, never in the engine's per-game suite S2AGame.<id>.
#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

// The method-channel map (keys resolutionScale, antiAliasing, scalingFilter, frameRateLimit, frameInterpolation, docked,
// widescreen, performanceOverlay, gameLanguage), with defaults for anything not stored. A resolution scale above 1 has no
// effect in the engine's direct mode (the only mode it ships), so it is reported as "1". frameInterpolation is off by default.
NSDictionary<NSString *, id> *S2ArmSettingsSnapshot(void);

// Validates and stores any subset of that map (unknown keys and values are ignored), then returns the new snapshot.
NSDictionary<NSString *, id> *S2ArmSettingsApply(NSDictionary *changes);

// Before the engine starts game `gid` (its first start, or the resume of a parked game): removes a frame-rate limit no
// longer offered (a stored 30 reads as no limit), exports the game language (or clears it for "auto"), turns on the
// engine's own brief performance overlay, which S2ArmSessionMenu then shows or hides live according to performanceOverlay,
// and gives the engine the game's profile when it has one.
void S2ArmSettingsPrepareLaunch(NSString *_Nullable gid);

// The values the in-game menu offers, in display order.
NSArray<NSString *> *S2ArmSettingsValues(NSString *key);

// The key of a game's profile: `gid` in upper case when it is a title id (16 hexadecimal digits), else nil.
NSString *_Nullable S2ArmSettingsGameKey(NSString *_Nullable gid);

// Whether the game has a settings profile.
BOOL S2ArmSettingsGameHasProfile(NSString *_Nullable gid);

// The settings the game starts with, as the method-channel map: its profile when it has one, else the global snapshot.
NSDictionary<NSString *, id> *S2ArmSettingsForGame(NSString *_Nullable gid);

// Gives the game a profile made from the global values of the moment (an existing one is kept as it is). Returns the game's
// settings, nil for a gid that is not a title id.
NSDictionary<NSString *, id> *_Nullable S2ArmSettingsGameCreateProfile(NSString *_Nullable gid);

// Validates and stores any subset of the map in the game's profile. Never the global settings: nil when the game has none.
NSDictionary<NSString *, id> *_Nullable S2ArmSettingsGameApply(NSString *_Nullable gid, NSDictionary *changes);

// Removes the game's profile: it follows the global settings again, which are returned.
NSDictionary<NSString *, id> *S2ArmSettingsGameRemoveProfile(NSString *_Nullable gid);

// Where the in-game menu writes: the game's profile when it has one, else the global settings. Returns the game's settings.
NSDictionary<NSString *, id> *S2ArmSettingsApplyForGame(NSString *_Nullable gid, NSDictionary *changes);

// Whether the performance overlay is wanted for the game (its profile, else the RewindBox preference).
BOOL S2ArmSettingsPerformanceOverlay(NSString *_Nullable gid);
void S2ArmSettingsSetPerformanceOverlay(NSString *_Nullable gid, BOOL on);

// Whether frame generation is wanted for the game (engine patch 0345, off by default): S2A_RB_FI at the next game start.
BOOL S2ArmSettingsFrameInterpolation(NSString *_Nullable gid);

// Whether adaptive frame generation for all games (engine patch 0421, off by default) is wanted: S2A_RB_FI_ALL.
BOOL S2ArmSettingsFrameInterpolationAll(NSString *_Nullable gid);

// Shadow map resolution scale for the game (engine patch 0421, "1" / "0.75" / "0.5"): S2A_RB_SHADOW_SCALE.
NSString *S2ArmSettingsShadowQuality(NSString *_Nullable gid);

// Render pipeline compilation mode (engine patch 0419, "fluid" / "strict"): S2A_RB_FLUID_PSO.
NSString *S2ArmSettingsPipelineMode(NSString *_Nullable gid);

// Performance / thermal profile (engine patch 0421, "balanced" / "performance" / "thermalDrs").
NSString *S2ArmSettingsPerformanceProfile(NSString *_Nullable gid);

NS_ASSUME_NONNULL_END
