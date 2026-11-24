#pragma once
// RewindBox's in-game menu for the Switch 2 engine (native UIKit, the MeloNX / RPCS3 pattern). See docs/s2arm-engine-bridge.md.
//
// Opened by a ☰ button at the top right of the game view, or by − and + held together on a controller. Rows: resume, show /
// hide the performance overlay (live), settings (written at once, used at the next game start; the frame-rate limit at once, patch 0078,
// and frame generation at once in a session started with it, patch 0345), quit (the engine's clean
// stop: saves written, then session_ended). Strings come from Dart at launch (menuStrings), English when a key is missing.
// Settings and the overlay are the running game's profile when it has one (the menu says so), else the global settings; a game
// without a profile can be given one there, made from the values of the moment (S2ArmSettings.h).
// The engine's own gear menu (top left, en / zh only) stays available for controls, cheats and saves.
#import <UIKit/UIKit.h>

NS_ASSUME_NONNULL_BEGIN

@interface S2ArmSessionMenu : NSObject

- (instancetype)initWithViewController:(UIViewController *)viewController
                               strings:(NSDictionary<NSString *, NSString *> *)strings
                                  stop:(void (^)(void))stop NS_DESIGNATED_INITIALIZER;
- (instancetype)init NS_UNAVAILABLE;

// A setting that can change during play (patch 0078: the frame-rate limit; patch 0345: frame generation): YES when it is in effect now.
// Set by the host when the engine has the entry point; nil = every setting waits for the next start.
@property(nonatomic, copy, nullable) BOOL (^applyNow)(NSString *setting, id value);

// The running game's title id (16 hexadecimal digits), set by the host before attach: the key of its settings profile.
@property(nonatomic, copy, nullable) NSString *gameId;

// Patch 0345, set by the host. Live: this session started with frame generation on (S2A_RB_FI=1), so turning it on or off applies at
// once. Unavailable: the engine answered that this device or its graphics backend cannot interpolate; the choice stays stored and the
// menu tells the player.
@property(nonatomic, assign) BOOL frameInterpolationLive;
@property(nonatomic, assign) BOOL frameInterpolationUnavailable;

// Source/game identity and launch preferences. The engine resolves its active
// environment and live cadence when the window starts; the host supplies its overlay.
@property(nonatomic, copy, nullable) NSDictionary<NSString *, id> *benchmarkContext;

- (void)attach;   // main thread, once the game view controller is presented
- (void)detach;   // main thread; idempotent
- (void)applyOverlay;   // also called by the existing game-view watch for late or replaced labels
- (void)showMenu;

// The text shown for a key (the Dart string, else English). Exposed for tests of the string table.
- (NSString *)text:(NSString *)key;

@end

NS_ASSUME_NONNULL_END
