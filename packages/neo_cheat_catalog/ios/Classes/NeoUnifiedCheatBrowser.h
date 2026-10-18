#import <UIKit/UIKit.h>

NS_ASSUME_NONNULL_BEGIN

/// One catalogue browser for Libretro, Dolphin, ARMSX2 and RPCS3.
/// Import handlers persist complete disabled programs; only the engine's own
/// menu can subsequently enable them. Callbacks may arrive after dismissal.
@interface NeoUnifiedCheatBrowser : UITableViewController
/// Shared catalogue labels for entry points in the four engine menus.
+ (NSString *)localizedText:(NSString *)key locale:(NSString *)locale;
+ (void)presentFrom:(UIViewController *)presenter
           identity:(NSDictionary *)identity
             engine:(NSString *)engine
             locale:(NSString *)locale
            accepts:(BOOL (^)(NSDictionary *program))accepts
      importHandler:(void (^)(NSDictionary *game, NSArray *programs,
                              void (^completion)(NSError * _Nullable error)))importHandler;
@end

NS_ASSUME_NONNULL_END
