// SPDX-License-Identifier: GPL-3.0-or-later
#import "Public/NeoTouchControllerMonitor.h"
#import "Public/NeoTouchLayoutStore.h"
#import <UIKit/UIKit.h>
#import <stdatomic.h>

static _Atomic(NSInteger) gNeoTouchTestingCount = -1;

void NeoTouchControllerMonitorSetTestingCount(NSInteger count) {
  atomic_store(&gNeoTouchTestingCount, count < 0 ? -1 : count);
}

BOOL NeoTouchControlsShouldHide(NSString* console, BOOL controllerConnected, BOOL touchEnabled, BOOL covered,
                                BOOL editing) {
  if (editing) return NO;
  if (!touchEnabled || covered) return YES;
  return controllerConnected && NeoTouchHidesControlsWithController(console);
}

@implementation NeoTouchControllerMonitor {
  void (^_handler)(BOOL);
  BOOL _connected;
  BOOL _invalidated;
  // Controllers announced as disconnected, ignored while GameController may
  // still list them; weak, so a released controller leaves the table.
  NSHashTable<GCController*>* _departed;
}

+ (BOOL)isCompatibleController:(GCController*)controller {
  if (![controller isKindOfClass:GCController.class]) return NO;
  if (controller.isSnapshot) return NO;
  return controller.extendedGamepad != nil;
}

+ (BOOL)compatibleControllerConnectedIgnoring:(GCController*)leaving {
  const NSInteger testing = atomic_load(&gNeoTouchTestingCount);
  if (testing >= 0) return testing > 0;
  for (GCController* controller in GCController.controllers) {
    if (controller == leaving) continue;
    if ([self isCompatibleController:controller]) return YES;
  }
  return NO;
}

+ (BOOL)compatibleControllerConnected {
  return [self compatibleControllerConnectedIgnoring:nil];
}

- (instancetype)initWithChangeHandler:(void (^)(BOOL))handler {
  self = [super init];
  if (self) {
    _handler = [handler copy];
    _departed = [NSHashTable weakObjectsHashTable];
    _connected = [NeoTouchControllerMonitor compatibleControllerConnected];
    NSNotificationCenter* center = NSNotificationCenter.defaultCenter;
    [center addObserver:self selector:@selector(controllerConnected:) name:GCControllerDidConnectNotification object:nil];
    [center addObserver:self selector:@selector(controllerDisconnected:)
                   name:GCControllerDidDisconnectNotification object:nil];
    [center addObserver:self selector:@selector(applicationBecameActive:)
                   name:UIApplicationDidBecomeActiveNotification object:nil];
  }
  return self;
}

- (void)dealloc {
  [NSNotificationCenter.defaultCenter removeObserver:self];
}

- (BOOL)connected {
  return _connected;
}

- (void)invalidate {
  _invalidated = YES;
  _handler = nil;
  [NSNotificationCenter.defaultCenter removeObserver:self];
}

- (BOOL)presence {
  const NSInteger testing = atomic_load(&gNeoTouchTestingCount);
  if (testing >= 0) return testing > 0;
  NSArray<GCController*>* controllers = GCController.controllers;
  for (GCController* departed in _departed.allObjects)
    if (![controllers containsObject:departed]) [_departed removeObject:departed];
  for (GCController* controller in controllers) {
    if ([_departed containsObject:controller]) continue;
    if ([NeoTouchControllerMonitor isCompatibleController:controller]) return YES;
  }
  return NO;
}

- (void)update {
  if (!NSThread.isMainThread) {
    dispatch_async(dispatch_get_main_queue(), ^{ [self update]; });
    return;
  }
  if (_invalidated) return;
  const BOOL connected = [self presence];
  if (connected == _connected) return;
  _connected = connected;
  void (^handler)(BOOL) = _handler;
  if (handler) handler(connected);
}

- (void)refresh {
  [self update];
}

- (void)controllerConnected:(NSNotification*)notification {
  GCController* arriving = [notification.object isKindOfClass:GCController.class] ? notification.object : nil;
  dispatch_block_t apply = ^{
    if (arriving) [self->_departed removeObject:arriving];
    [self update];
  };
  if (NSThread.isMainThread) apply();
  else dispatch_async(dispatch_get_main_queue(), apply);
}

- (void)controllerDisconnected:(NSNotification*)notification {
  GCController* leaving = [notification.object isKindOfClass:GCController.class] ? notification.object : nil;
  dispatch_block_t apply = ^{
    if (leaving) [self->_departed addObject:leaving];
    [self update];
  };
  if (NSThread.isMainThread) apply();
  else dispatch_async(dispatch_get_main_queue(), apply);
}

- (void)applicationBecameActive:(NSNotification*)notification {
  [self update];
}

@end
