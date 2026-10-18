// SPDX-License-Identifier: GPL-3.0-or-later
#import <UIKit/UIKit.h>

NS_ASSUME_NONNULL_BEGIN
/// Native, per-session list. Discovery only reads installed catalogue chunks.
/// A catalogue program is imported only when its switch is first enabled.
/// Engine adapters re-read the current identity before every mutation.
@interface NeoUnifiedCheatList : UITableViewController
@property(nonatomic, copy) NSString *locale;
@property(nonatomic, copy) NSString *engine;
/// {identity,items:[{key,name,enabled,...}],available,hardcore,help}
@property(nonatomic, copy) void (^readState)(void (^)(NSDictionary *state));
@property(nonatomic, copy) BOOL (^accepts)(NSDictionary *program);
/// Returns the exact native item created/reused, including its stable key.
@property(nonatomic, copy) void (^install)(NSDictionary *game, NSArray *programs,
                                         void (^)(NSDictionary *_Nullable item, NSError *_Nullable error));
@property(nonatomic, copy) void (^setEnabled)(NSDictionary *item, BOOL enabled,
                                            void (^)(BOOL success));
@property(nonatomic, copy, nullable) void (^importAction)(UIViewController *presenter);
- (void)reloadCheats;
/// Imports a standard RPCS3 patch document encoded as YAML-compatible JSON.
/// The exact current serial/version and native PPU keys remain mandatory.
- (void)openRPCS3Import;
/// Complete ordered closures; missing/cyclic/incompatible dependencies reject
/// the entire program. Kept public for the Foundation and UIKit probes.
+ (NSArray<NSDictionary *> *)selectionsForGame:(NSDictionary *)game programs:(NSArray *)programs
                                      accepts:(BOOL (^)(NSDictionary *))accepts;
@end
NS_ASSUME_NONNULL_END
