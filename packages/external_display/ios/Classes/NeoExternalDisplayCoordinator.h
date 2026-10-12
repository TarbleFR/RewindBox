// SPDX-License-Identifier: GPL-3.0-or-later
// Owner of NeoStation's window on the external screen (AirPlay to an Apple
// TV, Lightning/USB-C adapter): docs/external-display-universal.md § 3.3.
// One infrastructure places either the menu's second Flutter engine or the
// render view of the running emulator in that window; system mirroring stays
// the fallback (disabled, unsupported engines, no content). Main thread only.
#pragma once
#import <UIKit/UIKit.h>
#import "NeoExternalDisplayLayout.h"
#import "NeoExternalRenderHost.h"

NS_ASSUME_NONNULL_BEGIN

/// Posted on the main thread at every state change; `userInfo` is the
/// state dictionary of `-stateDictionary` (the plugin's event channel relays
/// it to Dart).
FOUNDATION_EXPORT NSString *const NeoExternalDisplayStateChangedNotification;

/// Source of the menu shown on the TV (NeoExternalDisplayMenuEngine wraps the
/// second Flutter engine). The coordinator never imports Flutter itself, so
/// the simulator tests run it with a plain UIViewController provider.
@protocol NeoExternalMenuProvider <NSObject>
/// Creates the engine lazily; nil until `configureMenuEngine` named the
/// Dart entrypoint.
- (nullable UIViewController *)externalMenuViewControllerCreatingIfNeeded;
/// `reason` ∈ {memory, disconnect, menu_off, disabled}.
- (void)destroyExternalMenuEngineForReason:(NSString *)reason;
/// none | created | destroyed (the coordinator reports `attached` itself).
- (NSString *)externalMenuEngineStatus;
@optional
/// Told at every pass: YES while the TV shows the menu, NO while the menu is
/// hidden (a game holds the TV, iOS mirrors the iPhone). A hidden engine
/// goes to the `hidden` lifecycle state so it draws no frame (animated
/// backgrounds run up to the TV's refresh rate otherwise) and comes back to
/// `resumed` when the menu shows again.
- (void)externalMenuSetVisible:(BOOL)visible;
@end

@interface NeoExternalDisplayCoordinator : NSObject

+ (instancetype)shared;

/// A scene or legacy window on the external screen exists.
@property(nonatomic, readonly) BOOL connected;
@property(nonatomic, readonly) NeoExternalContentKind content;
/// Points of the external window; zero when disconnected.
@property(nonatomic, readonly) CGSize screenPointSize;
/// Scale of the external screen, re-read at every pass (a mode change of
/// the TV can change it alone); zero when disconnected.
@property(nonatomic, readonly) CGFloat screenScale;
/// Stored preferences (NeoExternalDisplayPreferences), re-read on refresh.
@property(nonatomic, readonly) NeoExternalDisplayMode mode;
@property(nonatomic, readonly) BOOL enabled;
@property(nonatomic, readonly) BOOL menuOnTV;
/// Dusklight/KartPad run: the window is hidden and iOS mirrors the iPhone.
@property(nonatomic, readonly) BOOL suspended;
/// iOS shows the mirrored iPhone (connected, but NeoStation shows nothing of
/// its own there).
@property(nonatomic, readonly) BOOL mirroringActive;
/// iOS 27 scene accessory: unavailable (no UISceneAccessory class: iOS ≤
/// 26) | inactive:sdk (the app was built with an SDK before 27, whose
/// external scene iOS 27 still connects by itself) | inactive:automatic_scene
/// (a scene the system offered by itself is connected) | registered (an
/// enabled registration exists) | disabled (registrations exist, all turned
/// off: output off, suspended, nothing to show) | failed:<reason>. When
/// active: one registration on the application root (the menu) and one on
/// the presented controller that owns the attached render host, never on a
/// menu presented over the game; the system presents the topmost one.
@property(nonatomic, readonly, copy) NSString *accessoryStatus;
/// scene | legacy | none.
@property(nonatomic, readonly, copy) NSString *sceneRole;
/// none | created | attached | destroyed.
@property(nonatomic, readonly, copy) NSString *menuEngineStatus;
@property(nonatomic, readonly, nullable) UIWindow *window;
/// The external scenes UIKit connected and has not disconnected, in
/// connection order; the window is in one of them (the others stand by and
/// one is adopted when the shown one disconnects).
@property(nonatomic, readonly, copy) NSArray<UIWindowScene *> *externalScenes;
@property(nonatomic, readonly, nullable) UIViewController *menuViewController;
@property(nonatomic, readonly, nullable) id<NeoExternalRenderHost> renderHost;
/// Set by ExternalDisplayPlugin (NeoExternalDisplayMenuEngine).
@property(nonatomic, weak, nullable) id<NeoExternalMenuProvider> menuProvider;

/// The game takes the screen: its render view moves to the external window
/// (the menu view is hidden, never released here). Before the window exists
/// the host is only remembered. Called once the game controller is
/// presented; in the iOS 27 accessory regime the presented controller that
/// owns the host's placeholder view holds a registration while the host is
/// attached (calling it again with the same host is harmless).
- (void)attachRenderHost:(id<NeoExternalRenderHost>)host;
/// Returns the render view to index 0 of the placeholder. Bridges call it
/// BEFORE stopping their core.
- (void)detachRenderHost:(id<NeoExternalRenderHost>)host;
/// Dusklight/KartPad: hide the window so iOS resumes mirroring.
- (void)suspendForUnsupportedEngine;
- (void)resumeAfterUnsupportedEngine;
/// The Flutter controller of the second engine (or any controller in tests).
- (void)attachMenuViewController:(UIViewController *)controller;
- (void)detachMenuViewController;
/// RPCS3: the menu engine is destroyed and not recreated until the game's
/// host detaches.
- (void)destroyMenuEngineForMemory;
/// Re-reads the preferences, rescans UIApplication.connectedScenes for the
/// external role and re-applies (settings changed, scene changed, a host's
/// iPhone layout changed). The bridges also call it in the completion of
/// their game controller's dismissal: the dismissed controller's accessory
/// registration is released and the state reported to Dart is current.
/// Called during a pass, it runs once that pass ends.
- (void)refresh;
/// The state sent to Dart (`getState`, events).
- (NSDictionary<NSString *, id> *)stateDictionary;

@property(nonatomic, copy, nullable) void (^stateChanged)(void);

/// Test seams. `windowFactory` builds the window for a scene (or a legacy
/// screen); `legacyScreens` lists the screens of the legacy fallback;
/// `buildSDKMajorVersion` replaces the SDK major read from the main bundle
/// (DTPlatformVersion / DTSDKName, NeoExternalDisplaySDKMajorVersion);
/// `screenScaleReader` replaces the external screen's scale.
@property(nonatomic, copy, nullable) UIWindow *_Nullable (^windowFactory)(UIWindowScene *_Nullable scene,
                                                                           UIScreen *_Nullable screen);
@property(nonatomic, copy, nullable) NSArray<UIScreen *> *(^legacyScreens)(void);
@property(nonatomic, copy, nullable) NSInteger (^buildSDKMajorVersion)(void);
@property(nonatomic, copy, nullable) CGFloat (^screenScaleReader)(void);

/// Called by NeoExternalDisplaySceneDelegate for the external role.
- (void)sceneDidConnect:(UIWindowScene *)scene;
- (void)sceneDidDisconnect:(UIWindowScene *)scene;

@end

NS_ASSUME_NONNULL_END
