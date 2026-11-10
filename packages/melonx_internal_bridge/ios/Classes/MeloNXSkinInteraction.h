// SPDX-License-Identifier: GPL-3.0-or-later
#import <UIKit/UIKit.h>

NS_ASSUME_NONNULL_BEGIN

/// The skin's touches after a session menu: the session's rule (no presented
/// controller, no pause, not closing) is applied when the game resumes, but a
/// menu action can run while its sheet is still being dismissed, so the rule
/// then still reads "a controller is presented" and the skin would stay without
/// touches until the next rotation. This applies the rule now and again once the
/// presentation has gone: at the end of its transition when UIKit gives one,
/// else every 50 ms, for at most 2 s. It stops as soon as `stillWanted` answers
/// NO (paused again, another sheet, closing, another session) and never retains
/// the presenting controller.
@interface MLXSkinInteraction : NSObject
+ (void)syncNowAndWhenUncovered:(UIViewController*)presenter
                    stillWanted:(BOOL (^)(void))stillWanted
                           sync:(void (^)(void))sync;
/// The bound of the fallback polling (attempts of 50 ms).
@property(class, nonatomic, readonly) NSInteger attemptLimit;
@end

NS_ASSUME_NONNULL_END
