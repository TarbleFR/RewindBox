// SPDX-License-Identifier: GPL-3.0-or-later
#import <UIKit/UIKit.h>
NS_ASSUME_NONNULL_BEGIN
typedef NS_ENUM(NSInteger, RBLiquidProgressStatus) {
    RBLiquidProgressRunning, RBLiquidProgressPaused,
    RBLiquidProgressSuccess, RBLiquidProgressError
};
/// Shared presentation for measured native downloads. Unknown duration is
/// represented by separated droplets, never by a fabricated filled amount.
@interface RBLiquidProgressView : UIView
@property(nonatomic) double progress;
@property(nonatomic) BOOL indeterminate;
@property(nonatomic) RBLiquidProgressStatus status;
- (void)liquidTick:(CFTimeInterval)time;
- (BOOL)wantsLiquidMotion;
@end
NS_ASSUME_NONNULL_END
