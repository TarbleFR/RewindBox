// SPDX-License-Identifier: GPL-3.0-or-later
#import "DolphinExternalDisplay.h"
#import <MetalKit/MetalKit.h>

NSString* const DOLExternalDisplayModeKey = @"NeoStation.Dolphin.ExternalDisplay.Mode";
NSString* const DOLExternalDisplayChangedNotification = @"NeoStation.Dolphin.ExternalDisplayChanged";

DOLExternalDisplayMode DOLExternalDisplayPreference(void) {
  return DOLExternalDisplayModeFromValue([NSUserDefaults.standardUserDefaults objectForKey:DOLExternalDisplayModeKey]);
}

/// Black, non-rotating host of the render view on the external screen.
@interface DOLExternalDisplayViewController : UIViewController
@end
@implementation DOLExternalDisplayViewController
- (void)loadView {
  UIView* view = [[UIView alloc] initWithFrame:CGRectZero];
  view.backgroundColor = UIColor.blackColor;
  self.view = view;
}
- (BOOL)prefersStatusBarHidden { return YES; }
- (BOOL)prefersHomeIndicatorAutoHidden { return YES; }
@end

@interface DolphinExternalDisplay ()
@property(nonatomic, strong) UIView* render;
@property(nonatomic, weak) UIView* placeholder;
@property(nonatomic, strong, nullable) UIWindow* window;
@property(nonatomic, strong, nullable) UIScreen* screen;
@property(nonatomic, assign) DOLExternalDisplayMode mode;
@property(nonatomic, assign) BOOL observing;
@property(nonatomic, assign) BOOL autoResizeDrawable;
@property(nonatomic, assign) CGFloat contentScale;
@property(nonatomic, assign) UIViewAutoresizing autoresizing;
@end

@implementation DolphinExternalDisplay

- (instancetype)initWithRenderView:(UIView*)render placeholder:(UIView*)placeholder {
  if ((self = [super init])) {
    _render = render;
    _placeholder = placeholder;
    _mode = DOLExternalDisplayModeOff;
    _contentScale = render.contentScaleFactor;
    _autoresizing = render.autoresizingMask;
    _autoResizeDrawable = [render isKindOfClass:MTKView.class] ? ((MTKView*)render).autoResizeDrawable : NO;
  }
  return self;
}

- (BOOL)active { return self.window != nil; }

- (NSArray<UIScreen*>*)candidateScreens {
  if (self.externalScreens) return self.externalScreens() ?: @[];
  NSMutableArray* screens = [NSMutableArray array];
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
  for (UIScreen* screen in UIScreen.screens)
    if (screen != UIScreen.mainScreen) [screens addObject:screen];
#pragma clang diagnostic pop
  return screens;
}

- (void)start {
  NSAssert(NSThread.isMainThread, @"External display belongs to the main thread");
  if (!self.observing) {
    self.observing = YES;
    for (NSNotificationName name in @[UIScreenDidConnectNotification, UIScreenDidDisconnectNotification,
                                      UIScreenModeDidChangeNotification, UIApplicationDidBecomeActiveNotification,
                                      DOLExternalDisplayChangedNotification])
      [NSNotificationCenter.defaultCenter addObserver:self selector:@selector(environmentChanged:) name:name object:nil];
  }
  [self refresh];
}

- (void)environmentChanged:(NSNotification*)notification {
  if (!NSThread.isMainThread) {
    dispatch_async(dispatch_get_main_queue(), ^{ [self environmentChanged:notification]; });
    return;
  }
  if (self.observing) [self refresh];
}

- (void)refresh {
  NSAssert(NSThread.isMainThread, @"External display belongs to the main thread");
  const DOLExternalDisplayMode mode = DOLExternalDisplayPreference();
  UIScreen* screen = mode == DOLExternalDisplayModeOff ? nil : [self candidateScreens].firstObject;
  if (!screen) { [self deactivate]; self.mode = mode; return; }
  if (self.active && self.screen != screen) [self deactivate];
  self.mode = mode;
  if (!self.active) [self activateOnScreen:screen];
  else [self place];
}

- (void)activateOnScreen:(UIScreen*)screen {
  UIView* render = self.render;
  if (!render) return;
  UIWindow* window = self.windowFactory ? self.windowFactory(screen) : nil;
  if (!window) {
    window = [[UIWindow alloc] initWithFrame:screen.bounds];
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
    window.screen = screen;
#pragma clang diagnostic pop
  }
  window.backgroundColor = UIColor.blackColor;
  if (!window.rootViewController) window.rootViewController = [DOLExternalDisplayViewController new];
  self.window = window;
  self.screen = screen;
  // Dolphin sized the drawable for the iPhone and never re-reads it. The view
  // keeps those bounds and that scale; only a transform maps it to the TV.
  self.contentScale = render.contentScaleFactor;
  self.autoresizing = render.autoresizingMask;
  if ([render isKindOfClass:MTKView.class]) {
    self.autoResizeDrawable = ((MTKView*)render).autoResizeDrawable;
    ((MTKView*)render).autoResizeDrawable = NO;
  }
  const CGRect bounds = render.bounds;
  [render removeFromSuperview];
  render.autoresizingMask = UIViewAutoresizingNone;
  [window.rootViewController.view addSubview:render];
  render.bounds = bounds;
  render.contentScaleFactor = self.contentScale;
  window.hidden = NO;
  [self place];
  if (self.stateChanged) self.stateChanged(YES);
}

- (void)place {
  UIView* render = self.render;
  UIWindow* window = self.window;
  if (!render || !window) return;
  UIView* host = window.rootViewController.view;
  host.frame = window.bounds;
  const CGSize screen = host.bounds.size;
  const CGSize source = render.bounds.size;
  const CGFloat scale = DOLExternalDisplayScale(screen, source, self.mode);
  render.transform = CGAffineTransformIdentity;
  render.bounds = CGRectMake(0, 0, source.width, source.height);
  render.center = CGPointMake(screen.width / 2, screen.height / 2);
  render.transform = CGAffineTransformMakeScale(scale, scale);
}

- (void)deactivate {
  UIView* render = self.render;
  UIWindow* window = self.window;
  if (!window) return;
  self.window = nil;
  self.screen = nil;
  if (render) {
    [render removeFromSuperview];
    render.transform = CGAffineTransformIdentity;
    UIView* placeholder = self.placeholder;
    if (placeholder) {
      render.frame = placeholder.bounds;
      [placeholder insertSubview:render atIndex:0];
    }
    render.autoresizingMask = self.autoresizing;
    render.contentScaleFactor = self.contentScale;
    if ([render isKindOfClass:MTKView.class]) ((MTKView*)render).autoResizeDrawable = self.autoResizeDrawable;
  }
  window.hidden = YES;
  window.rootViewController = nil;
  if (self.stateChanged) self.stateChanged(NO);
}

- (void)stop {
  NSAssert(NSThread.isMainThread, @"External display belongs to the main thread");
  if (self.observing) {
    self.observing = NO;
    [NSNotificationCenter.defaultCenter removeObserver:self];
  }
  [self deactivate];
}

- (void)dealloc {
  [NSNotificationCenter.defaultCenter removeObserver:self];
}

@end
