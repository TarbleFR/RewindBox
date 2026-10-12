// SPDX-License-Identifier: GPL-3.0-or-later
// The menu shown on the TV: a complete second Flutter engine of a dedicated
// FlutterEngineGroup (docs/external-display-universal.md § 4), created
// lazily once Dart named its entrypoint (`configureMenuEngine`), hidden
// during a game, destroyed while RPCS3 runs and at disconnection.
#pragma once
#import <Flutter/Flutter.h>
#import <UIKit/UIKit.h>

#import "NeoExternalDisplayCoordinator.h"

NS_ASSUME_NONNULL_BEGIN

/// `neostation-external`.
FOUNDATION_EXPORT NSString *const kNeoExternalMenuEngineGroupName;
/// `neostation/external_display/menu` (FlutterStringCodec): the JSON of
/// SecondaryDisplayStateData, native → second engine.
FOUNDATION_EXPORT NSString *const kNeoExternalMenuChannelName;
/// The frozen plugin registry of the second engine, in registration order.
FOUNDATION_EXPORT NSArray<NSString *> *NeoExternalMenuPluginClassNames(void);

@interface NeoExternalDisplayMenuEngine : NSObject <NeoExternalMenuProvider>

+ (instancetype)shared;

/// Remembers the Dart entrypoint for the lazy creation; without it no
/// engine is ever created.
- (void)configureWithEntrypoint:(NSString *)entrypoint libraryURI:(NSString *)libraryURI;
@property(nonatomic, readonly) BOOL configured;
/// none | created | destroyed.
@property(nonatomic, readonly, copy) NSString *status;
@property(nonatomic, readonly, nullable) FlutterEngine *engine;
@property(nonatomic, readonly, nullable) FlutterViewController *viewController;

/// Caches the latest state and relays it to the running engine (a freshly
/// created engine receives it at once).
- (void)pushMenuState:(NSString *)json;
/// Main thread. The engine and its controller are released; the coordinator
/// recreates them when it needs the menu again.
- (void)destroyMenuEngineForMemory;

@end

NS_ASSUME_NONNULL_END
