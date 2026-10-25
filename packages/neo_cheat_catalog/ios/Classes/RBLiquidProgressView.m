// SPDX-License-Identifier: GPL-3.0-or-later
#import "Public/RBLiquidProgressView.h"
#import <QuartzCore/QuartzCore.h>
#include <math.h>

@interface RBLiquidClock : NSObject
@property(nonatomic, strong) NSHashTable<RBLiquidProgressView *> *views;
@property(nonatomic, strong) CADisplayLink *link;
+ (instancetype)shared;
- (void)sync;
@end
@implementation RBLiquidClock
+ (instancetype)shared {
    static RBLiquidClock *clock; static dispatch_once_t once;
    dispatch_once(&once, ^{
        clock = [self new]; clock.views = [NSHashTable weakObjectsHashTable];
        for (NSString *name in @[UIApplicationDidBecomeActiveNotification, UIApplicationWillResignActiveNotification,
             UIAccessibilityReduceMotionStatusDidChangeNotification, NSProcessInfoPowerStateDidChangeNotification]) {
            [NSNotificationCenter.defaultCenter addObserver:clock selector:@selector(changed:) name:name object:nil];
        }
    }); return clock;
}
- (void)changed:(NSNotification *)note { [self sync]; for (RBLiquidProgressView *v in self.views) [v setNeedsDisplay]; }
- (void)sync {
    BOOL enabled = UIApplication.sharedApplication.applicationState == UIApplicationStateActive &&
        !UIAccessibilityIsReduceMotionEnabled() && !NSProcessInfo.processInfo.lowPowerModeEnabled;
    BOOL wanted = NO;
    if (enabled) for (RBLiquidProgressView *view in self.views) if ([view wantsLiquidMotion]) { wanted = YES; break; }
    if (wanted && !self.link) {
        self.link = [CADisplayLink displayLinkWithTarget:self selector:@selector(tick:)];
        self.link.preferredFrameRateRange = CAFrameRateRangeMake(15, 30, 30);
        [self.link addToRunLoop:NSRunLoop.mainRunLoop forMode:NSRunLoopCommonModes];
    } else if (!wanted) { [self.link invalidate]; self.link = nil; }
}
- (void)tick:(CADisplayLink *)link {
    for (RBLiquidProgressView *view in self.views) if ([view wantsLiquidMotion]) [view liquidTick:link.timestamp];
    [self sync];
}
@end

@interface RBLiquidProgressView ()
@property(nonatomic) CFTimeInterval phase;
@end
@implementation RBLiquidProgressView
- (instancetype)initWithFrame:(CGRect)frame {
    if ((self = [super initWithFrame:frame])) {
        self.opaque = NO; self.backgroundColor = UIColor.clearColor;
        self.isAccessibilityElement = YES;
        self.accessibilityTraits = UIAccessibilityTraitUpdatesFrequently;
        self.contentMode = UIViewContentModeRedraw;
    } return self;
}
- (CGSize)intrinsicContentSize { return CGSizeMake(UIViewNoIntrinsicMetric, 12); }
- (BOOL)wantsLiquidMotion {
    if (!self.window || self.hidden || self.alpha < .01 || self.status != RBLiquidProgressRunning ||
        (!self.indeterminate && self.progress >= 1)) return NO;
    for (UIView *v = self.superview; v; v = v.superview) if (v.hidden || v.alpha < .01) return NO;
    return CGRectIntersectsRect([self convertRect:self.bounds toView:self.window], self.window.bounds);
}
- (void)didMoveToWindow {
    [super didMoveToWindow];
    if (self.window) [RBLiquidClock.shared.views addObject:self];
    else [RBLiquidClock.shared.views removeObject:self];
    [RBLiquidClock.shared sync];
}
- (void)setHidden:(BOOL)hidden { [super setHidden:hidden]; [RBLiquidClock.shared sync]; }
- (void)setProgress:(double)progress {
    _progress = isfinite(progress) ? fmax(0, fmin(1, progress)) : 0;
    [self setNeedsDisplay]; [RBLiquidClock.shared sync];
}
- (void)setIndeterminate:(BOOL)value { _indeterminate = value; [self setNeedsDisplay]; [RBLiquidClock.shared sync]; }
- (void)setStatus:(RBLiquidProgressStatus)status {
    BOOL completed = _status != RBLiquidProgressSuccess && status == RBLiquidProgressSuccess;
    _status = status; [self setNeedsDisplay]; [RBLiquidClock.shared sync];
    if (completed && self.window && !UIAccessibilityIsReduceMotionEnabled() && !NSProcessInfo.processInfo.lowPowerModeEnabled) {
        CAKeyframeAnimation *pulse = [CAKeyframeAnimation animationWithKeyPath:@"transform.scale"];
        pulse.values = @[@1, @1.018, @1]; pulse.duration = .24;
        [self.layer addAnimation:pulse forKey:@"liquidCompletion"];
    }
}
- (void)liquidTick:(CFTimeInterval)time { self.phase = fmod(time / 2.4, 1) * M_PI * 2; [self setNeedsDisplay]; }
- (void)drawRect:(CGRect)dirty {
    CGContextRef c = UIGraphicsGetCurrentContext(); if (!c || CGRectIsEmpty(self.bounds)) return;
    CGRect rect = CGRectInset(self.bounds, .7, .7);
    UIBezierPath *glass = [UIBezierPath bezierPathWithRoundedRect:rect cornerRadius:rect.size.height / 2];
    [[UIColor.secondaryLabelColor colorWithAlphaComponent:.1] setFill]; [glass fill];
    UIColor *water = self.status == RBLiquidProgressError ? UIColor.systemRedColor :
        self.status == RBLiquidProgressPaused ? [UIColor colorWithRed:.56 green:.68 blue:.72 alpha:1] :
        [UIColor colorWithRed:.35 green:.82 blue:.9 alpha:1];
    CGContextSaveGState(c); [glass addClip];
    if (self.indeterminate) {
        for (NSInteger i = 0; i < 3; i++) {
            CGFloat x = rect.origin.x + rect.size.width * fmod(self.phase / (M_PI * 2) + i / 3.0, 1);
            [[water colorWithAlphaComponent:.45 + i * .15] setFill];
            [[UIBezierPath bezierPathWithOvalInRect:CGRectMake(x - 1.5, CGRectGetMidY(rect) - 1.5, 3, 3)] fill];
        }
    } else if (self.progress > 0) {
        CGContextClipToRect(c, CGRectMake(rect.origin.x, rect.origin.y, rect.size.width * self.progress, rect.size.height));
        UIBezierPath *liquid = [UIBezierPath bezierPath];
        [liquid moveToPoint:CGPointMake(rect.origin.x, CGRectGetMaxY(rect))];
        BOOL moving = [self wantsLiquidMotion] && !UIAccessibilityIsReduceMotionEnabled() && !NSProcessInfo.processInfo.lowPowerModeEnabled;
        for (NSInteger i = 0; i <= 28; i++) {
            CGFloat x = rect.origin.x + rect.size.width * i / 28.0;
            CGFloat y = rect.origin.y + 1 + (moving ? .65 * sin(i / 28.0 * M_PI * 4 + self.phase) : 0);
            [liquid addLineToPoint:CGPointMake(x, y)];
        }
        [liquid addLineToPoint:CGPointMake(CGRectGetMaxX(rect), CGRectGetMaxY(rect))]; [liquid closePath];
        [liquid addClip];
        CGColorSpaceRef space = CGColorSpaceCreateDeviceRGB();
        NSArray *colors = @[(id)[water colorWithAlphaComponent:.72].CGColor, (id)water.CGColor];
        CGGradientRef gradient = CGGradientCreateWithColors(space, (__bridge CFArrayRef)colors, NULL);
        CGContextDrawLinearGradient(c, gradient, rect.origin, CGPointMake(rect.origin.x, CGRectGetMaxY(rect)), 0);
        CGGradientRelease(gradient); CGColorSpaceRelease(space);
        if (moving) for (NSInteger i = 0; i < 3; i++) {
            CGFloat x = rect.origin.x + rect.size.width * self.progress * (.18 + i * .29);
            CGFloat y = CGRectGetMaxY(rect) - rect.size.height * (.2 + .6 * fmod(self.phase / (M_PI * 2) + i * .31, 1));
            [[UIColor.whiteColor colorWithAlphaComponent:.35] setFill];
            [[UIBezierPath bezierPathWithOvalInRect:CGRectMake(x, y, 1.2, 1.2)] fill];
        }
    }
    CGContextRestoreGState(c);
    [[UIColor.labelColor colorWithAlphaComponent:UIAccessibilityDarkerSystemColorsEnabled() ? .7 : .28] setStroke];
    glass.lineWidth = 1; [glass stroke];
    UIBezierPath *glint = [UIBezierPath bezierPath];
    [glint moveToPoint:CGPointMake(rect.origin.x + rect.size.height / 2, rect.origin.y + .8)];
    [glint addLineToPoint:CGPointMake(CGRectGetMaxX(rect) - rect.size.height / 2, rect.origin.y + .8)];
    [[UIColor.whiteColor colorWithAlphaComponent:.6] setStroke]; glint.lineWidth = .7; [glint stroke];
}
@end
