// SPDX-License-Identifier: GPL-3.0-or-later
#import <UIKit/UIKit.h>
#import "NeoTextureEngine.h"

NS_ASSUME_NONNULL_BEGIN

/// Table page base shared by the HD texture pages (language of the labels).
@interface NeoTextureTablePage : UITableViewController
@property(nonatomic, copy) NSString *locale;
@end

/// The one "HD textures" page shared by Dolphin, ARMSX2 and the libretro
/// PPSSPP/Azahar cores, opened from a game's pause menu, from its options in
/// the library, or (without identity) from a console's library.
///
/// Game mode (identity set): catalogue status and its single refresh action,
/// this game's identifiers and the engine's own switch, the installed pack,
/// the compatible catalogue packs, and import from Files. Console mode:
/// catalogue, every pack installed for the engine, every catalogue pack of
/// the console. Pack pages show author, version, sizes, formats, terms,
/// source and verification date, and download/install/update/remove.
@interface NeoTextureHDPage : NeoTextureTablePage
- (instancetype)initWithEngine:(id<NeoTextureEngine>)engine
                        system:(NSString *)system
                      identity:(nullable NSDictionary *)identity
                     gameTitle:(nullable NSString *)gameTitle
                        locale:(nullable NSString *)locale NS_DESIGNATED_INITIALIZER;
- (instancetype)initWithStyle:(UITableViewStyle)style NS_UNAVAILABLE;
- (instancetype)initWithCoder:(NSCoder *)coder NS_UNAVAILABLE;
- (instancetype)initWithNibName:(nullable NSString *)name bundle:(nullable NSBundle *)bundle NS_UNAVAILABLE;
/// Opened from a running game: changes apply when the game is relaunched.
@property(nonatomic, assign) BOOL inGame;
/// Reason the identity could not be read (unsupported container...), shown
/// instead of the identifiers when `identity` has none.
@property(nonatomic, copy, nullable) NSString *identityProblem;
/// Wraps the page in a navigation controller with a Close button.
- (UINavigationController *)navigationControllerForPresentation;

/// Entry point for the engine bridges and the Flutter plugin, which reach
/// this pod through the Objective-C runtime (NSClassFromString), so no engine
/// pod links it. options:
///   system      ps2, gc, wii, psp (pspminis) or 3ds; engine (optional) derives from it
///   locale, title, inGame (BOOL), presentation ("modal": with a Close button)
///   identity    what the running engine reported (unified form), or gameID
///               (+ revision, crc) in the engine's own terms, or
///   gamePath    the game file (identity read from it; the engine's record first)
///   gameKey     libretro "<system>/<rom file>" of the game (per-game core options)
///   games       console page: [{path, title, gameKey}] of the console's library
///   dolphinUser Dolphin user directory; armsx2Data ARMSX2 data folder and
///   armsx2Host  the running game's ARMSX2TextureHost; libretroSaves and
///   libretroConfig the libretro Saves and Config folders, sessionReader and
///   sessionWriter the running core's option hooks (see NeoTextureEngines).
/// nil when the directories needed by the engine are missing.
+ (nullable UIViewController *)textureViewControllerWithOptions:(NSDictionary *)options;
/// Label text in the page's language (12 NeoStation languages, English fallback).
+ (NSString *)text:(NSString *)key locale:(nullable NSString *)locale;
@end

NS_ASSUME_NONNULL_END
