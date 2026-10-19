// SPDX-License-Identifier: GPL-3.0-or-later
// In-game "HD textures" page of the embedded ARMSX2 menu (Build 485).
#import <UIKit/UIKit.h>
#import "ARMSX2TexturePackStore.h"

NS_ASSUME_NONNULL_BEGIN

/// What the page needs from the bridge. Every completion runs on the main thread.
@protocol ARMSX2TextureHost <NSObject>
/// {game, pack, engine (in a game), formats}; nil when the session ended.
- (void)textureReadState:(void (^)(NSDictionary<NSString*, id>* _Nullable state))completion;
- (void)textureInspectURL:(NSURL*)url
                 progress:(ARMSX2TextureProgress)progress
               completion:(void (^)(NSDictionary<NSString*, id>* inspection))completion;
- (void)textureInstall:(NSString*)token
         allowMismatch:(BOOL)allow
              progress:(ARMSX2TextureProgress)progress
            completion:(void (^)(NSDictionary<NSString*, id>* result))completion;
- (void)textureCancel:(NSString*)token;
/// Stops the inspection under way (a .tar.zst expansion can take minutes).
- (void)textureCancelInspection;
- (void)textureDiscard:(NSString*)token;
/// result: success, message (a catalogue key), error (an error key).
- (void)textureSetEnabled:(BOOL)enabled completion:(void (^)(NSDictionary<NSString*, id>* result))completion;
- (void)textureRemove:(void (^)(NSDictionary<NSString*, id>* result))completion;
/// YES in a game: the engine applies changes to the running game.
@property(nonatomic, readonly) BOOL textureLive;
@end

@interface ARMSX2TexturePage : UITableViewController
@property(nonatomic, copy) NSString* localeIdentifier;
@property(nonatomic, strong) id<ARMSX2TextureHost> host;
@end

/// Text for an error result of the store or the engine ("error", "detail", ...).
FOUNDATION_EXPORT NSString* ARMSX2TextureErrorText(NSDictionary<NSString*, id>* result, NSString* _Nullable locale);

NS_ASSUME_NONNULL_END
