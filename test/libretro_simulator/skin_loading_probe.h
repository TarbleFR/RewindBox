// Exercises the production session, renderer, persisted store and native menu.
// Original skins are CI fixtures only. No commercial ROM or physical device.
static NSString *const LoadingSkinID = @"05878738f250279bfae6e27b9b597f182562b4dcfb71f86ab286d49c0c7f59c4";

static void PrepareSkinLoadingUpgrade(NSDictionary *scenario) {
  if (![scenario[@"skinLoading"] isEqual:@"upgrade"]) return;
  NSString *seed = [NSBundle.mainBundle.bundlePath stringByAppendingPathComponent:@"skin-loading-seed.json"];
  [NSFileManager.defaultManager copyItemAtPath:seed toPath:DocumentsPath(@"Libretro/Config/Frontend/psx.json") error:nil];
}

@interface LibretroSession (LoadingProbePrivate)
- (void)openMenu;
- (void)closeMenu;
- (void)frontendSettingsDidChange;
- (NSString *)gameScopeKey;
- (LibretroSkinOrientation)currentOrientation;
@end

@interface SkinLoadingRunner : NSObject
@property(nonatomic, strong) LibretroSession *session;
@property(nonatomic, strong) NSMutableDictionary *result;
@property(nonatomic, strong) NSMutableArray *checks;
@property(nonatomic, copy) dispatch_block_t finish;
@property(nonatomic, strong) NSData *originalMetadata;
@property(nonatomic, strong) LibretroSkinRenderer *staleRenderer;
- (void)start:(BOOL)relaunch;
@end
@implementation SkinLoadingRunner
- (LibretroGameViewController *)controller { return [_session valueForKey:@"controller"]; }
- (LibretroSkinRenderer *)renderer { return self.controller.skinRenderer; }
- (LibretroFrontendStore *)store { return [_session valueForKey:@"store"]; }
- (void)check:(BOOL)ok name:(NSString *)name {
  [_checks addObject:@{@"name":name,@"passed":@(ok)}];
  Progress(@"skin-loading: %@ %@",ok?@"PASS":@"FAIL",name);
}
- (void)poll:(BOOL (^)(void))condition attempt:(NSUInteger)attempt name:(NSString *)name then:(dispatch_block_t)then {
  if (condition()) { [self check:YES name:name]; then(); return; }
  if (attempt >= 500) { [self check:NO name:name]; self.finish(); return; }
  dispatch_after(dispatch_time(DISPATCH_TIME_NOW,20*NSEC_PER_MSEC),dispatch_get_main_queue(),^{
    [self poll:condition attempt:attempt+1 name:name then:then];
  });
}
- (void)waitSkin:(NSString *)identifier then:(dispatch_block_t)then {
  [self poll:^BOOL{
    LibretroSkin *skin=[self.session valueForKey:@"currentSkin"];
    return [skin.installedIdentifier isEqual:identifier] &&
      [self.renderer valueForKey:@"representation"]==[self.session valueForKey:@"currentRepresentation"] &&
      [[self.renderer valueForKey:@"pendingRequiredImages"] unsignedIntegerValue]==0 &&
      ![[self.renderer valueForKey:@"resourceFailed"] boolValue];
  } attempt:0 name:[@"active, fully decoded layout: " stringByAppendingString:identifier] then:then];
}
- (void)capture:(NSString *)name {
  NSString *folder=DocumentsPath(@"SkinFrames");
  [NSFileManager.defaultManager createDirectoryAtPath:folder withIntermediateDirectories:YES attributes:nil error:nil];
  UIGraphicsImageRenderer *capture=[[UIGraphicsImageRenderer alloc] initWithSize:self.renderer.bounds.size];
  UIImage *image=[capture imageWithActions:^(UIGraphicsImageRendererContext *c){[self.renderer.layer renderInContext:c.CGContext];}];
  [UIImagePNGRepresentation(image) writeToFile:[folder stringByAppendingPathComponent:[name stringByAppendingPathExtension:@"png"]] atomically:YES];
}
- (void)withMenu:(void (^)(LibretroMenuPage *))action then:(dispatch_block_t)then {
  [_session openMenu];
  dispatch_after(dispatch_time(DISPATCH_TIME_NOW,400*NSEC_PER_MSEC),dispatch_get_main_queue(),^{
    LibretroFrontendMenu *menu=[self.session valueForKey:@"frontendMenu"];
    LibretroMenuPage *page=[menu skinsPage];
    [self check:page!=nil && self.controller.presentedViewController!=nil name:@"actual in-game Skins menu is open"];
    if(page)action(page);
    [self.session closeMenu];
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW,400*NSEC_PER_MSEC),dispatch_get_main_queue(),then);
  });
}
- (void)choose:(NSString *)identifier orientation:(NSString *)orientation game:(BOOL)game page:(LibretroMenuPage *)page {
  LibretroMenuRow *scope=MenuRowWithIdentifier(page,game?@"libretro-frontend-scope-game":@"libretro-frontend-scope-console");
  [self check:scope.action!=nil name:@"native scope selector is available"];
  if(scope.action)scope.action(page);
  NSString *rowID=[NSString stringWithFormat:@"libretro-skin-%@-%@",orientation,identifier];
  LibretroMenuRow *row=MenuRowWithIdentifier(page,rowID);
  [self check:row.action!=nil && row.enabled name:[@"native skin action exists: " stringByAppendingString:rowID]];
  if(row.action && row.enabled)row.action(page);
}
- (void)simulateOrientation:(BOOL)portrait then:(dispatch_block_t)then {
  CGSize size=portrait?CGSizeMake(390,844):CGSizeMake(844,390);
  self.controller.view.bounds=(CGRect){CGPointZero,size};
  [self.controller setNeedsSkinLayout];
  [self.controller.view layoutIfNeeded];
  [self poll:^BOOL{return self.session.currentOrientation==(portrait?LibretroSkinOrientationPortrait:LibretroSkinOrientationLandscape);}
    attempt:0 name:portrait?@"portrait game-view layout applied":@"landscape game-view layout applied" then:then];
}
- (void)verifyOneRenderer {
  LibretroSkinRepresentation *representation=[_session valueForKey:@"currentRepresentation"];
  CALayer *panel=[self.renderer valueForKey:@"panelLayer"],*background=[self.renderer valueForKey:@"backgroundLayer"];
  BOOL noVectors=YES;
  for(id layers in [self.renderer valueForKey:@"items"])noVectors=noVectors && [layers valueForKey:@"shape"]==nil;
  [self check:!representation.generated && panel.hidden && noVectors && background.contents!=nil
    name:@"custom artwork replaces every default vector layer and panel"];
  NSUInteger renderers=0;for(UIView *view in self.renderer.superview.subviews)
    if([view isKindOfClass:LibretroSkinRenderer.class])renderers++;
  [self check:renderers==1 name:@"exactly one skin renderer is attached"];
}
- (void)start:(BOOL)relaunch {
  NSString *metadata=DocumentsPath([NSString stringWithFormat:@"Libretro/Skins/%@/neostation-skin.json",LoadingSkinID]);
  self.originalMetadata=[NSData dataWithContentsOfFile:metadata];
  [self waitSkin:LoadingSkinID then:^{
    [self verifyOneRenderer];[self capture:relaunch?@"dualshocked-relaunch":@"dualshocked-upgrade"];
    NSArray *skins=[self.session valueForKey:@"availableSkins"];
    [self check:[[skins valueForKey:@"installedIdentifier"] containsObject:LoadingSkinID]
      name:@"previously installed DualShocked remains in the native catalogue"];
    NSDictionary *saved=ReadJSON(DocumentsPath(@"Libretro/Config/Frontend/psx.json"));
    [self check:[saved[@"console"][@"skin.portrait"] isEqual:LoadingSkinID] &&
      [saved[@"console"][@"skin.landscape"] isEqual:LoadingSkinID] &&
      [saved[@"console"][@"controls.pressureIntensity"] isEqual:@"pronounced"]
      name:@"old portrait/landscape selections and intensity survive loading without migration"];
    [self check:[saved[@"console"][@"future.setting"] isEqual:@"keep-me"] &&
      [self.originalMetadata isEqual:[NSData dataWithContentsOfFile:metadata]]
      name:@"unknown preferences and original installed metadata are untouched"];
    if(relaunch){
      [self check:[[self.store storedValueForKey:LibretroSettingSkinLandscape console:@"psx" game:[self.session gameScopeKey]] isEqual:LoadingSkinID]
        name:@"a new session restores the saved per-game selection"];
      self.finish();return;
    }
    [self withMenu:^(LibretroMenuPage *page){
      for(NSString *orientation in @[@"portrait",@"landscape"]){
        LibretroMenuRow *row=MenuRowWithIdentifier(page,[NSString stringWithFormat:@"libretro-skin-%@-%@",orientation,LoadingSkinID]);
        [self check:row.checked && row.enabled name:[orientation stringByAppendingString:@": installed selection is checked in game"]];
      }
      [self choose:@"default" orientation:@"landscape" game:YES page:page];
    } then:^{[self waitSkin:@"default" then:^{
      [self check:[[self.store storedValueForKey:LibretroSettingSkinLandscape console:@"psx" game:nil] isEqual:LoadingSkinID]
        name:@"game-only selection does not overwrite the console preference"];
      [self simulateOrientation:YES then:^{[self waitSkin:LoadingSkinID then:^{
        [self verifyOneRenderer];[self capture:@"dualshocked-portrait"];
        [self withMenu:^(LibretroMenuPage *page){[self choose:@"press-psx" orientation:@"portrait" game:YES page:page];}
          then:^{[self waitSkin:@"press-psx" then:^{
            [self check:[[self.store valueForKey:LibretroSettingSkinLandscape console:@"psx" game:[self.session gameScopeKey] scope:NULL] isEqual:@"default"]
              name:@"portrait changes preserve the separate landscape override"];
            [self testDamagedOrientation];
          }];}];
      }];}];
    }];}];
  }];
}
- (void)testDamagedOrientation {
  NSString *source=DocumentsPath([@"Libretro/Skins/" stringByAppendingString:LoadingSkinID]);
  NSString *target=DocumentsPath(@"Libretro/Skins/loading-damaged");
  [NSFileManager.defaultManager copyItemAtPath:source toPath:target error:nil];
  NSString *info=[target stringByAppendingPathComponent:@"info.json"];
  NSMutableDictionary *json=[[NSJSONSerialization JSONObjectWithData:[NSData dataWithContentsOfFile:info]
    options:NSJSONReadingMutableContainers error:nil] mutableCopy];
  json[@"representations"][@"iphone"][@"edgeToEdge"][@"portrait"][@"assets"]=@{@"large":@"actually-missing.png"};
  [[NSJSONSerialization dataWithJSONObject:json options:0 error:nil] writeToFile:info atomically:YES];
  for(NSString *key in @[LibretroSettingSkinPortrait,LibretroSettingSkinLandscape])
    [self.store setValue:@"loading-damaged" forKey:key console:@"psx" game:[_session gameScopeKey]];
  [_session frontendSettingsDidChange];
  [self poll:^BOOL{return [[self.session valueForKey:@"failedSkinRepresentations"] count]>0;}
    attempt:0 name:@"a real missing resource is refused on the active portrait only" then:^{
      [self waitSkin:@"press-psx" then:^{
        [self check:[[[self.session valueForKey:@"availableSkins"] valueForKey:@"installedIdentifier"] containsObject:@"loading-damaged"]
          name:@"a failed layout does not hide its installed skin from the selector"];
        [self simulateOrientation:NO then:^{[self waitSkin:@"loading-damaged" then:^{
          [self verifyOneRenderer];[self capture:@"dualshocked-valid-landscape-with-broken-portrait"];
          [self withMenu:^(LibretroMenuPage *page){
            [self choose:LoadingSkinID orientation:@"portrait" game:YES page:page];
            [self choose:LoadingSkinID orientation:@"landscape" game:YES page:page];
          } then:^{[self waitSkin:LoadingSkinID then:^{
            NSString *metadata=DocumentsPath([NSString stringWithFormat:@"Libretro/Skins/%@/neostation-skin.json",LoadingSkinID]);
            [self check:[self.originalMetadata isEqual:[NSData dataWithContentsOfFile:metadata]] name:@"switching and fallback never rewrite the installed archive record"];
            [self verifyOneRenderer];[self capture:@"dualshocked-restored-in-game"];self.finish();
          }];}];
        }];}];
      }];
    }];
}
@end
static void RunSkinLoadingProbe(LibretroSession *session,NSDictionary *scenario,NSMutableDictionary *result,dispatch_block_t completion){
  SkinLoadingRunner *runner=[SkinLoadingRunner new];runner.session=session;runner.result=result;
  runner.checks=[NSMutableArray array];result[@"skinLoadingChecks"]=runner.checks;runner.finish=completion;
  [runner start:[scenario[@"skinLoading"] isEqual:@"relaunch"]];
}
