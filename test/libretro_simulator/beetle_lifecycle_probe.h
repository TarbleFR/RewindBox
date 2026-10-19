// Build 489: Beetle PSX HW in Vulkan through a game's life, once its
// replacement texture is recognised: pause and resume (the menu's call),
// background and foreground (the game view's call), a state saved on the
// emulation thread (loading it is left to the device: see step 8), a rotation and back, and the audio output; then
// the replacement must still be recognised and Beetle still in Vulkan.
// Main thread. Private session calls, made as the menu and the app make them.

#import "LibretroCoreHost.h"
#import "LibretroGameViewController.h"

@interface BeetleLifecycle : NSObject
@property(nonatomic, strong) LibretroSession *session;
@property(nonatomic, strong) NSMutableDictionary *result;
@property(nonatomic, copy) dispatch_block_t finished;
@property(nonatomic) NSUInteger step;
@property(nonatomic) uint64_t mark;
- (void)next;
@end

static void BeetleCheck(NSMutableDictionary *result, BOOL passed, NSString *name) {
  NSMutableArray *checks = result[@"beetleLifecycle"] ?: [NSMutableArray array];
  [checks addObject:@{@"name" : name, @"passed" : @(passed)}];
  result[@"beetleLifecycle"] = checks;
  Progress(@"beetle lifecycle %@ %@", passed ? @"ok" : @"FAILED", name);
}

static uint64_t BeetleFrames(LibretroSession *session) {
  LibretroCoreHost *host = [session valueForKey:@"host"];
  return host.frameSerial;
}

static void BeetleSendBool(LibretroSession *session, NSString *name, BOOL value) {
  SEL selector = NSSelectorFromString(name);
  if (![session respondsToSelector:selector]) return;
  ((void (*)(id, SEL, BOOL))[session methodForSelector:selector])(session, selector, value);
}

/// Runs `work` on the emulation thread (the session's own queue), then
/// `done` on the main thread.
static void BeetleOnEmulation(LibretroSession *session, BOOL (^work)(LibretroCoreHost *host), void (^done)(BOOL ok)) {
  SEL selector = NSSelectorFromString(@"enqueue:");
  LibretroCoreHost *host = [session valueForKey:@"host"];
  if (![session respondsToSelector:selector] || host == nil) {
    done(NO);
    return;
  }
  ((void (*)(id, SEL, dispatch_block_t))[session methodForSelector:selector])(session, selector, ^{
    BOOL ok = work(host);
    dispatch_async(dispatch_get_main_queue(), ^{ done(ok); });
  });
}

static void BeetleRotate(LibretroSession *session, BOOL portrait) {
  LibretroGameViewController *controller = [session valueForKey:@"controller"];
  ProbeRootController *root = (id)controller.view.window.rootViewController;
  root.probeMask = UIInterfaceOrientationMaskAllButUpsideDown;
  [root setNeedsUpdateOfSupportedInterfaceOrientations];
  UIWindowSceneGeometryPreferencesIOS *preferences = [[UIWindowSceneGeometryPreferencesIOS alloc]
      initWithInterfaceOrientations:portrait ? UIInterfaceOrientationMaskPortrait : UIInterfaceOrientationMaskLandscape];
  [controller.view.window.windowScene requestGeometryUpdateWithPreferences:preferences errorHandler:^(NSError *error) {
    Progress(@"beetle rotation request failed: %@", error.localizedDescription);
  }];
}

static BOOL BeetlePortrait(LibretroSession *session) {
  LibretroGameViewController *controller = [session valueForKey:@"controller"];
  return controller.view.bounds.size.height > controller.view.bounds.size.width;
}

static const NSInteger kBeetleProbeSlot = 7;

@implementation BeetleLifecycle

- (void)after:(double)seconds {
  dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(seconds * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{
    [self next];
  });
}

- (void)next {
  LibretroSession *session = _session;
  NSMutableDictionary *result = _result;
  switch (_step++) {
    case 0: {
      id audio = [session valueForKey:@"audio"];
      BeetleCheck(result, audio != nil, @"audio output started");
      _mark = BeetleFrames(session);
      [self after:0.5];
      return;
    }
    case 1: {
      BeetleCheck(result, BeetleFrames(session) > _mark, @"frames advance before pausing");
      BeetleSendBool(session, @"setMenuPaused:", YES);
      [self after:0.4];
      return;
    }
    case 2: {
      _mark = BeetleFrames(session);
      [self after:0.6];
      return;
    }
    case 3: {
      BeetleCheck(result, BeetleFrames(session) <= _mark + 1, @"no frame while paused");
      BeetleSendBool(session, @"setMenuPaused:", NO);
      _mark = BeetleFrames(session);
      [self after:0.6];
      return;
    }
    case 4: {
      BeetleCheck(result, BeetleFrames(session) > _mark + 5, @"frames resume after the pause");
      BeetleSendBool(session, @"applicationActive:", NO);
      [self after:0.4];
      return;
    }
    case 5: {
      _mark = BeetleFrames(session);
      [self after:0.6];
      return;
    }
    case 6: {
      BeetleCheck(result, BeetleFrames(session) <= _mark + 1, @"no frame in the background");
      BeetleSendBool(session, @"applicationActive:", YES);
      _mark = BeetleFrames(session);
      [self after:0.6];
      return;
    }
    case 7: {
      BeetleCheck(result, BeetleFrames(session) > _mark + 5, @"frames resume in the foreground");
      LibretroCoreHost *host = [session valueForKey:@"host"];
      NSString *path = [host statePathForSlot:kBeetleProbeSlot];
      if (path.length > 0) [NSFileManager.defaultManager removeItemAtPath:path error:nil];
      BeetleOnEmulation(session, ^BOOL(LibretroCoreHost *core) {
        NSError *error = nil;
        BOOL ok = [core saveStateToSlot:kBeetleProbeSlot error:&error];
        if (!ok) Progress(@"beetle state save failed: %@", error);
        return ok;
      }, ^(BOOL ok) {
        BOOL written = path.length > 0 && [NSFileManager.defaultManager fileExistsAtPath:path];
        BeetleCheck(result, ok && written, @"state saved in Vulkan");
        [self after:0.5];
      });
      return;
    }
    case 8: {
      // Loading a state makes Beetle's Vulkan renderer create linear textures on
      // host-visible buffers, which the Simulator's Metal refuses ("Linear texture
      // can only be created on buffers with MTLStorageModePrivate in the
      // simulator", run 39291452900); an iPhone's Metal allows them. The load is
      // left to the device; the probe records that it did not run it.
      result[@"beetleStateLoad"] = @"not run in the Simulator";
      _mark = BeetleFrames(session);
      [self after:0.6];
      return;
    }
    case 9: {
      BeetleCheck(result, BeetleFrames(session) > _mark + 5, @"frames advance after saving the state");
      BeetleRotate(session, NO);
      [self after:1.5];
      return;
    }
    case 10: {
      BeetleCheck(result, !BeetlePortrait(session), @"rotated to landscape");
      _mark = BeetleFrames(session);
      BeetleRotate(session, YES);
      [self after:1.5];
      return;
    }
    case 11: {
      BeetleCheck(result, BeetlePortrait(session), @"rotated back to portrait");
      BeetleCheck(result, BeetleFrames(session) > _mark + 5, @"frames advance through the rotations");
      NSDictionary *status = BeetleStatus(session);
      result[@"beetleStatusAfterLifecycle"] = status;
      BeetleCheck(result, [status[@"renderer"] isEqual:@"vulkan"], @"still Vulkan after the lifecycle");
      BeetleCheck(result, [status[@"replace"] boolValue] && [status[@"recognized"] integerValue] > 0,
                  @"replacement still recognised after the lifecycle");
      [self after:0.5];
      return;
    }
    default: {
      dispatch_block_t finished = self.finished;
      self.finished = nil;
      if (finished) finished();
      return;
    }
  }
}

@end

static void RunBeetleLifecycle(LibretroSession *session, NSMutableDictionary *result, dispatch_block_t finished) {
  BeetleLifecycle *lifecycle = [BeetleLifecycle new];
  lifecycle.session = session;
  lifecycle.result = result;
  lifecycle.finished = finished;
  [lifecycle next];
}
