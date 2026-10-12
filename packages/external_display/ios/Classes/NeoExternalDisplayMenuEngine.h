// SPDX-License-Identifier: GPL-3.0-or-later
// The menu shown on the TV: a complete second Flutter engine of a dedicated
// FlutterEngineGroup (docs/external-display-universal.md § 4), created
// lazily once Dart named its entrypoint (`configureMenuEngine`), hidden
// during a game (lifecycle `hidden`: no frame drawn), destroyed while RPCS3
// runs, when the menu or the whole output is turned off, and at
// disconnection. The engine never opens the database: the main engine gives
// it the language and the theme (entrypoint arguments, then the language
// channel).
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
/// `neostation/external_display/menu_locale` (FlutterStringCodec): the app
/// language code, native → a running second engine, when it changes.
FOUNDATION_EXPORT NSString *const kNeoExternalMenuLocaleChannelName;
/// Prefixes of the entrypoint arguments (`language=<code>`, `theme=<name>`),
/// parsed by ExternalDisplayMenuArgs (lib/external_display).
FOUNDATION_EXPORT NSString *const kNeoExternalMenuLanguageArgumentPrefix;
FOUNDATION_EXPORT NSString *const kNeoExternalMenuThemeArgumentPrefix;
/// The frozen plugin registry of the second engine, in registration order.
FOUNDATION_EXPORT NSArray<NSString *> *NeoExternalMenuPluginClassNames(void);

@interface NeoExternalDisplayMenuEngine : NSObject <NeoExternalMenuProvider>

+ (instancetype)shared;

/// Remembers the Dart entrypoint for the lazy creation, with the language
/// and the theme the engine starts with; without it no engine is ever
/// created.
- (void)configureWithEntrypoint:(NSString *)entrypoint
                     libraryURI:(NSString *)libraryURI
                   languageCode:(nullable NSString *)languageCode
                      themeName:(nullable NSString *)themeName;
/// Updates the copy given to the next engine (nil keeps a value); a new
/// language is also sent to the running engine, which applies it at once.
- (void)updateLanguageCode:(nullable NSString *)languageCode themeName:(nullable NSString *)themeName;
@property(nonatomic, readonly) BOOL configured;
@property(nonatomic, readonly, copy, nullable) NSString *languageCode;
@property(nonatomic, readonly, copy, nullable) NSString *themeName;
/// FlutterEngineGroupOptions.entrypointArgs of the next engine.
- (NSArray<NSString *> *)entrypointArguments;
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
