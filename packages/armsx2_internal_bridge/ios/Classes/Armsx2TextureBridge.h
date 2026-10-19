// SPDX-License-Identifier: GPL-3.0-or-later
// HD texture packs of the embedded ARMSX2 engine (Build 485): the Flutter channel
// methods of a PS2 game's settings (no ARMSX2Core needed) and the in-game host of
// the HD textures page (ARMSX2Core ABI 8).
#import <Flutter/Flutter.h>
#import "ARMSX2CoreABI.h"
#import "ARMSX2TexturePage.h"

NS_ASSUME_NONNULL_BEGIN

@interface Armsx2TextureBridge : NSObject
- (instancetype)initWithChannel:(FlutterMethodChannel*)channel
                  sessionActive:(BOOL (^)(void))sessionActive;
- (instancetype)init NS_UNAVAILABLE;
/// Handles textureStatus, texturePick, textureInstall, textureCancel,
/// textureDiscard, textureSetEnabled and textureRemove. NO for other methods.
- (BOOL)handleMethodCall:(FlutterMethodCall*)call result:(FlutterResult)result;
/// NeoStation's per-game choices, given to ARMSX2Core before a boot.
- (NSString*)bootPreferencesJSONForDataPath:(NSString*)dataPath;
/// After a disc boot: remembers the serial the engine read for this game file,
/// so the library knows it for images it cannot read (CHD, CSO, ...).
- (void)recordBootForAPI:(const NeoARMSX2API*)api gamePath:(NSString*)gamePath dataPath:(NSString*)dataPath;
/// Host of the in-game page for the running disc game. [alive] says whether
/// that session still runs (checked before every engine call).
- (id<ARMSX2TextureHost>)sessionHostForAPI:(const NeoARMSX2API*)api
                                  gamePath:(NSString*)gamePath
                                  dataPath:(NSString*)dataPath
                                     alive:(BOOL (^)(void))alive;
@end

NS_ASSUME_NONNULL_END
