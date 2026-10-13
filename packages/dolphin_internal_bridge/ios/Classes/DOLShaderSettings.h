// SPDX-License-Identifier: GPL-3.0-or-later
// In-game page "Post-processing effect" of the embedded Dolphin core
// (Build 450), opened from Display. Choice for every game or this game,
// Dolphin's official shaders, imported ones, their options; applied at the
// next launch (DOLShaderStore.h). Created by name from the session
// (NSClassFromString) so the launch path does not link the shader kit.
#import <UIKit/UIKit.h>

NS_ASSUME_NONNULL_BEGIN

@interface DOLShaderSettings : UITableViewController
/// Dolphin's user folder (Config/, Shaders/) and the Sys folder shipped.
@property(nonatomic, copy) NSString* userDirectory;
@property(nonatomic, copy) NSString* systemDirectory;
/// Game ID of the running game ("" for the Wii Menu: every game only).
@property(nonatomic, copy) NSString* gameId;
@property(nonatomic, copy) NSString* locale;
@end

NS_ASSUME_NONNULL_END
