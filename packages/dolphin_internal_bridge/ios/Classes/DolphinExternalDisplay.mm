// SPDX-License-Identifier: GPL-3.0-or-later
#import "DolphinExternalDisplay.h"
#if __has_include(<external_display/NeoExternalDisplayCoordinator.h>)
#import <external_display/NeoExternalDisplayCoordinator.h>
#import <external_display/NeoExternalDisplayPreferences.h>
#else
#import "NeoExternalDisplayCoordinator.h"
#import "NeoExternalDisplayPreferences.h"
#endif

DOLExternalDisplayMode DOLExternalDisplayPreference(void) {
  if (!NeoExternalDisplayPreferences.enabled) return DOLExternalDisplayModeOff;
  return DOLExternalDisplayModeFromGlobal(NeoExternalDisplayPreferences.mode);
}

@interface DolphinExternalDisplay ()
@property(nonatomic, strong) UIView* renderView;
@property(nonatomic, strong) UIView* placeholderView;
@property(nonatomic, assign) BOOL started;
@property(nonatomic, assign) BOOL active;
@end

@implementation DolphinExternalDisplay

- (instancetype)initWithRenderView:(UIView*)render placeholder:(UIView*)placeholder {
  if ((self = [super init])) {
    _renderView = render;
    _placeholderView = placeholder;
  }
  return self;
}

// Dolphin sized the drawable for the iPhone and never re-reads it: the
// coordinator keeps the view's bounds and scale, cuts autoResizeDrawable
// while the view is away and maps it to the TV with a transform only.
- (BOOL)fixedDrawable { return YES; }

- (void)start {
  NSAssert(NSThread.isMainThread, @"External display belongs to the main thread");
  if (self.started) return;
  self.started = YES;
  [NeoExternalDisplayCoordinator.shared attachRenderHost:self];
}

- (void)refresh {
  NSAssert(NSThread.isMainThread, @"External display belongs to the main thread");
  [NeoExternalDisplayCoordinator.shared refresh];
}

- (void)stop {
  NSAssert(NSThread.isMainThread, @"External display belongs to the main thread");
  if (!self.started) return;
  self.started = NO;
  // The coordinator returns the view to index 0 of the placeholder before
  // letting go of the host; the window itself outlives the session.
  [NeoExternalDisplayCoordinator.shared detachRenderHost:self];
}

#pragma mark NeoExternalRenderHost

- (void)externalDisplayDidChange:(BOOL)active {
  self.active = active;
  if (self.stateChanged) self.stateChanged(active);
}

@end
