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
/// `reason` ∈ {memory, disconnect, menu_off}.
- (void)destroyExternalMenuEngineForReason:(NSString *)reason;
/// none | created | destroyed (the coordinator reports `attached` itself).
- (NSString *)externalMenuEngineStatus;
@end

@interface NeoExternalDisplayCoordinator : NSObject

+ (instancetype)shared;

/// A scene or legacy window on the external screen exists.
@property(nonatomic, readonly) BOOL connected;
@property(nonatomic, readonly) NeoExternalContentKind content;
/// Points of the external window; zero when disconnected.
@property(nonatomic, readonly) CGSize screenPointSize;
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
/// iOS 27 scene accessory: unavailable | registered | failed:<reason>. One
/// registration per presented controller (the application root always, the
/// game controller after attachRenderHost:), released once the controller
/// is dismissed; the system presents the topmost one.
@property(nonatomic, readonly, copy) NSString *accessoryStatus;
/// scene | legacy | none.
@property(nonatomic, readonly, copy) NSString *sceneRole;
/// none | created | attached | destroyed.
@property(nonatomic, readonly, copy) NSString *menuEngineStatus;
@property(nonatomic, readonly, nullable) UIWindow *window;
@property(nonatomic, readonly, nullable) UIViewController *menuViewController;
@property(nonatomic, readonly, nullable) id<NeoExternalRenderHost> renderHost;
/// Set by ExternalDisplayPlugin (NeoExternalDisplayMenuEngine).
@property(nonatomic, weak, nullable) id<NeoExternalMenuProvider> menuProvider;

/// The game takes the screen: its render view moves to the external window
/// (the menu view is hidden, never released here). Before the window exists
/// the host is only remembered. Called once the game controller is
/// presented: the iOS 27 accessory is also registered on the topmost
/// presented controller (calling it again with the same host is harmless).
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
/// Re-reads the preferences and re-applies (settings changed, scene
/// changed). The bridges also call it in the completion of their game
/// controller's dismissal: the dismissed controller's accessory
/// registration is released and the state reported to Dart is current.
- (void)refresh;
/// The state sent to Dart (`getState`, events).
- (NSDictionary<NSString *, id> *)stateDictionary;

@property(nonatomic, copy, nullable) void (^stateChanged)(void);

/// Test seams. `windowFactory` builds the window for a scene (or a legacy
/// screen); `legacyScreens` lists the screens of the legacy fallback.
@property(nonatomic, copy, nullable) UIWindow *_Nullable (^windowFactory)(UIWindowScene *_Nullable scene,
                                                                           UIScreen *_Nullable screen);
@property(nonatomic, copy, nullable) NSArray<UIScreen *> *(^legacyScreens)(void);

/// Called by NeoExternalDisplaySceneDelegate for the external role.
- (void)sceneDidConnect:(UIWindowScene *)scene;
- (void)sceneDidDisconnect:(UIWindowScene *)scene;

@end

NS_ASSUME_NONNULL_END
