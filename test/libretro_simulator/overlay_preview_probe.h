#import "LibretroSkinRenderer.h"
@interface OverlayPreviewProbe : NSObject
@property(nonatomic, strong) NSMutableArray *checks;
@property(nonatomic, copy) dispatch_block_t finish;
@property(nonatomic) NSUInteger index;
- (void)next;
@end
@implementation OverlayPreviewProbe
- (void)next {
  if (_index >= 4) { self.finish(); return; }
  NSUInteger index = _index++;
  NSString *identifier = index < 2 ? @"flat-psx" : @"rgpad-modern";
  BOOL portrait = index % 2 == 0;
  NSString *directory = [NSBundle.mainBundle.bundlePath stringByAppendingPathComponent:[@"SkinFixtures/" stringByAppendingString:identifier]];
  LibretroSkin *skin = [LibretroSkin skinWithDirectory:directory consoleGeometry:nil errorCode:nil];
  LibretroSkinRepresentation *representation = [skin representationForOrientation:portrait ? LibretroSkinOrientationPortrait : LibretroSkinOrientationLandscape iPad:NO edgeToEdge:YES];
  NSUInteger assets = 0; for (LibretroSkinItem *item in representation.items) if (item.assetPath.length) assets++;
  NSString *name = [NSString stringWithFormat:@"%@-%@",identifier, portrait ? @"portrait" : @"landscape"];
  [_checks addObject:@{@"name":[name stringByAppendingString:@": full composite has more than eight images"],@"passed":@(assets > 8)}];
  if (representation == nil) { [self next]; return; }
  [LibretroSkinRenderer renderPreviewForRepresentation:representation size:portrait ? CGSizeMake(390,844) : CGSizeMake(844,390)
    scale:1 safeInsets:portrait ? UIEdgeInsetsMake(44,0,34,0) : UIEdgeInsetsMake(0,44,21,44)
    cacheDirectory:DocumentsPath(@"PreviewCache") completion:^(UIImage *image) {
      [self.checks addObject:@{@"name":[name stringByAppendingString:@": all native resources compose successfully"],@"passed":@(image != nil)}];
      NSString *folder = DocumentsPath(@"overlay-previews");
      [NSFileManager.defaultManager createDirectoryAtPath:folder withIntermediateDirectories:YES attributes:nil error:nil];
      if (image) [UIImagePNGRepresentation(image) writeToFile:[folder stringByAppendingPathComponent:[name stringByAppendingPathExtension:@"png"]] atomically:YES];
      [self next];
    }];
}
@end
static void RunOverlayPreviewProbe(NSMutableDictionary *result, dispatch_block_t completion) {
  OverlayPreviewProbe *probe = [OverlayPreviewProbe new]; probe.checks = [NSMutableArray array];
  result[@"previewChecks"] = probe.checks; probe.finish = completion; [probe next];
}
