// SPDX-License-Identifier: GPL-3.0-or-later
#import "MeloNXSkinInteraction.h"

static const NSInteger MLXSkinInteractionAttempts = 40;  // 40 x 50 ms = 2 s

@implementation MLXSkinInteraction

+ (NSInteger)attemptLimit { return MLXSkinInteractionAttempts; }

+ (void)syncNowAndWhenUncovered:(UIViewController*)presenter
                    stillWanted:(BOOL (^)(void))stillWanted
                           sync:(void (^)(void))sync {
  [self step:presenter wanted:stillWanted sync:sync left:MLXSkinInteractionAttempts];
}

+ (void)step:(UIViewController*)presenter
      wanted:(BOOL (^)(void))wanted
        sync:(void (^)(void))sync
        left:(NSInteger)left {
  if (!wanted()) return;
  sync();
  UIViewController* presented = presenter.presentedViewController;
  if (presented == nil || left <= 0) return;
  __weak UIViewController* weakPresenter = presenter;
  void (^again)(void) = ^{
    UIViewController* strongPresenter = weakPresenter;
    if (strongPresenter != nil) [MLXSkinInteraction step:strongPresenter wanted:wanted sync:sync left:left - 1];
  };
  // The dismissal's own end first (no wait after the sheet has gone), the bounded polling otherwise.
  id<UIViewControllerTransitionCoordinator> coordinator = presented.transitionCoordinator;
  if (coordinator != nil &&
      [coordinator animateAlongsideTransition:nil
                                   completion:^(id<UIViewControllerTransitionCoordinatorContext> context) {
                                     dispatch_async(dispatch_get_main_queue(), again);
                                   }]) {
    return;
  }
  dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(50 * NSEC_PER_MSEC)), dispatch_get_main_queue(), again);
}

@end
