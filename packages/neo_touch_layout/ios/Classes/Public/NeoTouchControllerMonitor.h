// SPDX-License-Identifier: GPL-3.0-or-later
#import <Foundation/Foundation.h>
#import <GameController/GameController.h>

NS_ASSUME_NONNULL_BEGIN

/// Decides whether a real game controller is connected, for the "hide the
/// touch controls when a controller is connected" policy.
///
/// A compatible controller is a GCController with a full gamepad profile
/// (extendedGamepad: the profile the PlayStation, GameCube and Wii touch
/// layouts stand for), wired, Bluetooth or attached to the phone, that is not
/// a snapshot. Keyboards and mice are GCKeyboard/GCMouse on iOS 14 and later,
/// and audio or other Bluetooth accessories are not GCControllers: none of
/// them hides the touch controls. The engines' own controller input is not
/// changed by this policy.
@interface NeoTouchControllerMonitor : NSObject
+ (BOOL)isCompatibleController:(nullable GCController*)controller;
+ (BOOL)compatibleControllerConnected;
/// As above, ignoring a controller that is disconnecting.
+ (BOOL)compatibleControllerConnectedIgnoring:(nullable GCController*)leaving;

/// Calls `handler` on the main thread whenever the presence of a compatible
/// controller changes (connection, disconnection, return to the foreground).
- (instancetype)initWithChangeHandler:(void (^)(BOOL connected))handler NS_DESIGNATED_INITIALIZER;
- (instancetype)init NS_UNAVAILABLE;
@property(nonatomic, readonly) BOOL connected;
/// Re-reads the controllers now; calls the handler if the presence changed.
- (void)refresh;
- (void)invalidate;
@end

/// Test seam: a count >= 0 replaces the GameController list (number of
/// compatible controllers); a negative count restores the real list.
FOUNDATION_EXPORT void NeoTouchControllerMonitorSetTestingCount(NSInteger count);

NS_ASSUME_NONNULL_END
