#import "LibretroFrontendStore.h"
@interface LibretroSession (SkinFailureProbePrivate)
- (NSString *)gameScopeKey;
- (void)frontendSettingsDidChange;
@end
@interface SkinFailureProbe : NSObject
@property(nonatomic, strong) LibretroSession *session;
@property(nonatomic, strong) NSMutableArray *checks;
@property(nonatomic, copy) dispatch_block_t finish;
@property(nonatomic) NSUInteger stage, attempts;
- (void)next;
@end
@implementation SkinFailureProbe
- (void)select:(NSString *)identifier {
  LibretroFrontendStore *store=[_session valueForKey:@"store"];
  for(NSString *key in @[LibretroSettingSkinPortrait,LibretroSettingSkinLandscape])
    [store setValue:identifier forKey:key console:@"nes" game:[_session gameScopeKey]];
  [_session frontendSettingsDidChange];
}
- (void)check:(BOOL)ok name:(NSString *)name { [_checks addObject:@{@"name":name,@"passed":@(ok)}]; }
- (void)next {
  LibretroSkin *current=[_session valueForKey:@"currentSkin"];
  if(_stage==0){[self select:@"press-complex"];_stage=1;}
  else if(_stage==1 && [current.installedIdentifier isEqual:@"press-complex"]){
    [self check:YES name:@"original Ignited is decoded and active before corruption test"];
    NSString *source=DocumentsPath(@"Libretro/Skins/press-complex"), *broken=DocumentsPath(@"Libretro/Skins/press-broken");
    [NSFileManager.defaultManager removeItemAtPath:broken error:nil];
    NSError *error=nil;[NSFileManager.defaultManager copyItemAtPath:source toPath:broken error:&error];
    for(NSString *file in [NSFileManager.defaultManager subpathsAtPath:broken])
      if([file.pathExtension.lowercaseString isEqual:@"pdf"])
        [@"%PDF-1.7\ntruncated fixture" writeToFile:[broken stringByAppendingPathComponent:file] atomically:YES encoding:NSUTF8StringEncoding error:nil];
    [self check:error==nil name:@"corrupt-PDF fixture created from the original skin"];
    [self select:@"press-broken"];_stage=2;_attempts=0;
  } else if(_stage==2 && [[_session valueForKey:@"failedSkins"] containsObject:@"press-broken"]){
    [self check:[current.installedIdentifier isEqual:@"press-complex"] name:@"failed decoded skin restores previous working Ignited without replacing it by default"];
    [self check:![[_session valueForKey:@"validatedSkins"] containsObject:@"press-broken"] name:@"malformed skin never becomes a validated active skin"];
    [self select:@"default"];self.finish();return;
  }
  if(_attempts++>=200){[self check:NO name:@"skin activation and graceful rejection complete within deadline"];self.finish();return;}
  dispatch_after(dispatch_time(DISPATCH_TIME_NOW,50*NSEC_PER_MSEC),dispatch_get_main_queue(),^{[self next];});
}
@end
static void RunSkinFailureProbe(LibretroSession *session,NSMutableDictionary *result,dispatch_block_t completion){
  SkinFailureProbe *probe=[SkinFailureProbe new];probe.session=session;probe.checks=result[@"skinChecks"];probe.finish=completion;[probe next];
}
