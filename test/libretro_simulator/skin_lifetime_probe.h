#import "LibretroSkinRenderer.h"
#import "LibretroGameViewController.h"

static void LifetimeCheck(NSMutableDictionary *result, BOOL passed, NSString *name) {
  if (!result[@"lifetimeChecks"]) result[@"lifetimeChecks"] = [NSMutableArray array];
  [result[@"lifetimeChecks"] addObject:@{@"name":name, @"passed":@(passed)}];
}

static void ProbeTerminalRenderer(NSMutableDictionary *result, BOOL baseline) {
  LibretroSkinRenderer *renderer = [[LibretroSkinRenderer alloc] initWithCacheDirectory:NSTemporaryDirectory()];
  LibretroSkinRepresentation *rep = [LibretroSkinRepresentation new];
  rep.generated = YES; rep.mappingSize = (LibretroSize){800,400};
  rep.items = @[]; rep.screens = @[];
  LibretroSkinLayoutResult *layout = [LibretroSkinLayout layoutRepresentation:rep
    viewSize:(LibretroSize){800,400} safeInsets:(LibretroInsets){0,0,0,0} overrides:nil];
  [renderer showRepresentation:rep layout:layout opacity:1 controlsHidden:NO];
  [renderer invalidateSession];
  NSUInteger generation = [[renderer valueForKey:@"imageGeneration"] unsignedIntegerValue];
  [renderer showRepresentation:rep layout:layout opacity:1 controlsHidden:NO];
  BOOL terminal = [renderer valueForKey:@"representation"] == nil &&
    [[renderer valueForKey:@"imageGeneration"] unsignedIntegerValue] == generation;
  result[@"reactivatedAfterInvalidation"] = @(!terminal);
  LifetimeCheck(result, terminal != baseline,
    baseline ? @"469 renderer body reproduces reactivation after invalidation" : @"invalidated renderer rejects late layout");
  [renderer invalidateSession];
}

@interface SkinStabilityActions : NSObject
@property(nonatomic, strong) LibretroSession *session;
@property(nonatomic, strong) NSMutableDictionary *result;
@property(nonatomic, copy) dispatch_block_t finished;
@property(nonatomic, strong) NSMutableData *pressure;
@property(nonatomic) NSUInteger index, attempts;
- (void)next;
@end
@implementation SkinStabilityActions
- (void)next {
  NSArray *choices = @[@"press-complex", @"2cb17f0364a285dd", @"default", @"2cb17f0364a285dd"];
  if (_index >= choices.count) { self.pressure = nil; self.finished(); return; }
  NSString *choice = choices[_index];
  LibretroGameViewController *controller = [_session valueForKey:@"controller"];
  BOOL portrait = _index % 2 == 0;
  if (_attempts == 0) {
    if (_index == 0) {
      self.pressure = [NSMutableData dataWithLength:32u*1024u*1024u];
      memset(self.pressure.mutableBytes, 0x5a, self.pressure.length);
      // Controlled cache eviction, explicitly a synthetic memory warning.
      [NSNotificationCenter.defaultCenter postNotificationName:UIApplicationDidReceiveMemoryWarningNotification object:nil];
    }
    LibretroFrontendStore *store = [_session valueForKey:@"store"];
    for (NSString *key in @[LibretroSettingSkinPortrait,LibretroSettingSkinLandscape])
      [store setValue:choice forKey:key console:@"nes" game:nil];
    [_session frontendSettingsDidChange];
    ProbeRootController *root = (id)controller.view.window.rootViewController;
    root.probeMask = UIInterfaceOrientationMaskAllButUpsideDown;
    [root setNeedsUpdateOfSupportedInterfaceOrientations];
    UIWindowSceneGeometryPreferencesIOS *preferences = [[UIWindowSceneGeometryPreferencesIOS alloc]
      initWithInterfaceOrientations:portrait ? UIInterfaceOrientationMaskPortrait : UIInterfaceOrientationMaskLandscape];
    [controller.view.window.windowScene requestGeometryUpdateWithPreferences:preferences errorHandler:^(NSError *error) {
      LifetimeCheck(self.result, NO, [@"rotation request failed: " stringByAppendingString:error.localizedDescription]);
    }];
  }
  LibretroSkin *current = [_session valueForKey:@"currentSkin"];
  LibretroSkinRenderer *renderer = controller.skinRenderer;
  BOOL selected = [current.installedIdentifier isEqual:choice];
  BOOL ready = [[renderer valueForKey:@"pendingRequiredImages"] unsignedIntegerValue] == 0 &&
    [renderer valueForKey:@"representation"] == [_session valueForKey:@"currentRepresentation"];
  BOOL rotated = (controller.view.bounds.size.height > controller.view.bounds.size.width) == portrait;
  if (selected && ready && rotated) {
    LifetimeCheck(_result, YES, [NSString stringWithFormat:@"live switch %@ %@ under 32 MiB load", choice, portrait ? @"portrait" : @"landscape"]);
    _index++; _attempts = 0;
  } else if (++_attempts > 160) {
    LifetimeCheck(_result, NO, [NSString stringWithFormat:@"live switch/rotation deadline: %@ selected=%d ready=%d rotated=%d", choice, selected, ready, rotated]);
    self.pressure = nil; self.finished(); return;
  }
  dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 50*NSEC_PER_MSEC), dispatch_get_main_queue(), ^{ [self next]; });
}
@end

static void RunSkinStabilityActions(LibretroSession *session, NSMutableDictionary *result, dispatch_block_t finished) {
  SkinStabilityActions *actions = [SkinStabilityActions new];
  actions.session = session; actions.result = result; actions.finished = finished;
  [actions next];
}
