// SPDX-License-Identifier: GPL-3.0-or-later
#import <Foundation/Foundation.h>
#import "NeoTouchLayoutModel.h"

NS_ASSUME_NONNULL_BEGIN

/// Posted on the main thread after a layout file changed. userInfo: "key".
FOUNDATION_EXPORT NSNotificationName const NeoTouchLayoutStoreDidChangeNotification;
/// Posted on the main thread after the "hide with a controller" preference of
/// a console changed. userInfo: "console", "hide".
FOUNDATION_EXPORT NSNotificationName const NeoTouchControllerPreferenceDidChangeNotification;

/// "Hide the touch controls when a controller is connected" for a console
/// ("gc", "wii", "ps2", "ps3"). On unless the user turned it off.
FOUNDATION_EXPORT BOOL NeoTouchHidesControlsWithController(NSString* console);
FOUNDATION_EXPORT void NeoTouchSetHidesControlsWithController(NSString* console, BOOL hide);
/// NSUserDefaults key of the preference (diagnostics and tests).
FOUNDATION_EXPORT NSString* NeoTouchHideWithControllerDefaultsKey(NSString* console);

/// Touch layouts, one JSON file per layout key in
/// Library/Application Support/NeoStation/TouchControls:
///   {"format": 1,
///    "general": {"landscape": {"elements": {...}}, "portrait": {...}},
///    "games": {"<game key>": {"landscape": {...}, "portrait": {...}}}}
/// A game entry replaces the general layout of that orientation for that
/// game only. Keys this version does not know are kept when a file is
/// rewritten. Main thread only.
@interface NeoTouchLayoutStore : NSObject
@property(class, nonatomic, readonly) NeoTouchLayoutStore* sharedStore;
@property(class, nonatomic, readonly) NSString* defaultDirectory;
- (instancetype)initWithDirectory:(NSString*)directory NS_DESIGNATED_INITIALIZER;
- (instancetype)init NS_UNAVAILABLE;
@property(nonatomic, copy, readonly) NSString* directory;

/// The stored layout of exactly this scope (game nil: the general layout).
- (nullable NeoTouchLayout*)layoutForKey:(NSString*)key
                             orientation:(NSString*)orientation
                                    game:(nullable NSString*)game;
/// The game's layout when it has one for this orientation, else the general
/// layout, else an empty (stock) layout.
- (NeoTouchLayout*)effectiveLayoutForKey:(NSString*)key
                             orientation:(NSString*)orientation
                                    game:(nullable NSString*)game
                            gameSpecific:(BOOL* _Nullable)gameSpecific;
/// Stores a layout. For the general scope an empty layout removes the entry
/// (stock controls); for a game it records that the game uses the stock
/// controls. Use -removeLayoutForKey:... to make a game follow the general
/// layout again.
- (BOOL)saveLayout:(NeoTouchLayout*)layout
            forKey:(NSString*)key
       orientation:(NSString*)orientation
              game:(nullable NSString*)game
             error:(NSError* _Nullable* _Nullable)error;
- (BOOL)removeLayoutForKey:(NSString*)key
               orientation:(NSString*)orientation
                      game:(nullable NSString*)game
                     error:(NSError* _Nullable* _Nullable)error;
- (BOOL)hasGameLayoutForKey:(NSString*)key game:(NSString*)game;
/// YES when the general layout or any game layout of the key is customised.
- (BOOL)hasCustomLayoutForKey:(NSString*)key;
- (NSString*)pathForKey:(NSString*)key;
@end

NS_ASSUME_NONNULL_END
