#pragma once
// RewindBox's in-game menu for the Switch 2 engine (native UIKit, the MeloNX / RPCS3 pattern). See docs/s2arm-engine-bridge.md.
//
// Opened by a ☰ button at the top right of the game view, or by − and + held together on a controller. Rows: resume, show /
// hide the performance overlay (live), settings (written at once, used at the next game start), quit (the engine's clean
// stop: saves written, then session_ended). Strings come from Dart at launch (menuStrings), English when a key is missing.
// The engine's own gear menu (top left, en / zh only) stays available for controls, cheats and saves.
#import <UIKit/UIKit.h>

NS_ASSUME_NONNULL_BEGIN

@interface S2ArmSessionMenu : NSObject

- (instancetype)initWithViewController:(UIViewController *)viewController
                               strings:(NSDictionary<NSString *, NSString *> *)strings
                                  stop:(void (^)(void))stop NS_DESIGNATED_INITIALIZER;
- (instancetype)init NS_UNAVAILABLE;

- (void)attach;   // main thread, once the game view controller is presented
- (void)detach;   // main thread; idempotent
- (void)showMenu;

// The text shown for a key (the Dart string, else English). Exposed for tests of the string table.
- (NSString *)text:(NSString *)key;

@end

NS_ASSUME_NONNULL_END
