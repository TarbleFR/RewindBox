// SPDX-License-Identifier: GPL-3.0-or-later
#import <UIKit/UIKit.h>
#import <QuartzCore/QuartzCore.h>
NS_ASSUME_NONNULL_BEGIN
FOUNDATION_EXPORT NSString* DOLPacingText(NSString* key,NSString* locale);
FOUNDATION_EXPORT NSInteger DOLFrameProfile(void);
FOUNDATION_EXPORT NSInteger DOLRequestedRefresh(NSInteger requested,NSInteger maximum,BOOL lowPower,NSInteger thermal);
@interface DolphinFramePacing : NSObject
@property(nonatomic,copy) NSString* locale;
@property(nonatomic,assign) NSInteger activeProfile;
@property(nonatomic,copy) NSString* gameId;
@property(nonatomic,readonly) BOOL traceEnabled;
@property(nonatomic,readonly) NSDictionary* summary;
@property(nonatomic,readonly) NSArray<NSDictionary*>* samples;
/// Build 442: set by the session when the game is drawn on an external screen.
@property(atomic,assign) BOOL externalDisplayActive;
/// Build 450: the post-processing effect page and the effect chosen for the
/// running game, given by the session; the Display page shows a second
/// section with its row only when both are set.
@property(nonatomic,copy,nullable) UIViewController* _Nullable (^shaderPage)(void);
@property(nonatomic,copy,nullable) NSString* _Nullable (^shaderSummary)(void);
- (void)startWithView:(UIView*)view;
- (void)stop;
- (void)refreshPreference;
- (void)appendPerformance:(NSDictionary*)sample inputMs:(double)inputMs refreshed:(BOOL)refreshed;
/// Build 442: a 10 Hz sub-sample of the core's last frame time (any thread).
/// Folded into the next trace row (max/min/slow counts) and the summary.
- (void)recordFrameTimeMs:(double)lastFrameMs;
- (NSDictionary*)frameTimeSummary;
- (UIViewController*)settingsController;
@end
NS_ASSUME_NONNULL_END
