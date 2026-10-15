// Scripted UIKit contacts inside the actual embedded game session. No
// synthetic renderer or input sink replaces the production implementations.
#import "LibretroGameViewController.h"
#import "LibretroSkinRenderer.h"
#import "LibretroTouchOverlay.h"
#import "LibretroInputState.h"
#import <GameController/GameController.h>

// Simulator exposes its own idle gamepad, which legitimately hides touch
// controls and occupies a player port. Isolate device enumeration in this
// test app only. Input profiles, values, UIKit, polling, latch and core reads
// stay real; the sole controller below is Apple's GCVirtualController.
static GCController *sSkinProbeController;
static IMP sSkinProbeOriginalControllers;
static NSArray<GCController *> *SkinProbeControllers(id owner, SEL selector) {
  return sSkinProbeController != nil ? @[sSkinProbeController] : @[];
}
static void SkinProbeIsolateControllers(void) {
  if(sSkinProbeOriginalControllers!=NULL)return;
  Method method=class_getClassMethod(GCController.class,@selector(controllers));
  sSkinProbeOriginalControllers=method_setImplementation(method,(IMP)SkinProbeControllers);
}
static void SkinProbeRestoreControllers(void) {
  sSkinProbeController=nil;
  if(sSkinProbeOriginalControllers==NULL)return;
  Method method=class_getClassMethod(GCController.class,@selector(controllers));
  method_setImplementation(method,sSkinProbeOriginalControllers);
  sSkinProbeOriginalControllers=NULL;
}

static void SkinProbeBuildFlatSkin(NSString *folder) {
  [NSFileManager.defaultManager createDirectoryAtPath:folder withIntermediateDirectories:YES attributes:nil error:nil];
  UIGraphicsImageRenderer *draw=[[UIGraphicsImageRenderer alloc] initWithSize:CGSizeMake(360,250)];
  UIImage *image=[draw imageWithActions:^(UIGraphicsImageRendererContext *c) {
    [[UIColor colorWithWhite:0.16 alpha:1] setFill]; UIRectFill(CGRectMake(0,0,360,250));
    for(NSArray *button in @[@[@280,@80,@48,@48,@"A"],@[@220,@145,@48,@48,@"B"],@[@160,@210,@70,@22,@"START"]]) {
      CGRect frame=CGRectMake([button[0] doubleValue],[button[1] doubleValue],[button[2] doubleValue],[button[3] doubleValue]);
      [[UIColor colorWithRed:0.45 green:0.2 blue:0.7 alpha:1] setFill];
      [[UIBezierPath bezierPathWithRoundedRect:frame cornerRadius:frame.size.height/2] fill];
      [button[4] drawInRect:CGRectInset(frame,10,8) withAttributes:@{NSForegroundColorAttributeName:UIColor.whiteColor,NSFontAttributeName:[UIFont boldSystemFontOfSize:14]}];
    }
    [[UIColor colorWithWhite:0.6 alpha:1] setFill];
    UIRectFill(CGRectMake(65,65,40,120)); UIRectFill(CGRectMake(25,105,120,40));
  }];
  [UIImagePNGRepresentation(image) writeToFile:[folder stringByAppendingPathComponent:@"painted.png"] atomically:YES];
  NSArray *items=@[
    @{@"frame":@{@"x":@25,@"y":@65,@"width":@120,@"height":@120},@"inputs":@{@"up":@"up",@"down":@"down",@"left":@"left",@"right":@"right"}},
    @{@"frame":@{@"x":@280,@"y":@80,@"width":@48,@"height":@48},@"inputs":@[@"a"]},
    @{@"frame":@{@"x":@220,@"y":@145,@"width":@48,@"height":@48},@"inputs":@[@"b"]},
    @{@"frame":@{@"x":@160,@"y":@210,@"width":@70,@"height":@22},@"inputs":@[@"start"]}];
  NSDictionary *rep=@{@"mappingSize":@{@"width":@360,@"height":@250},@"assets":@{@"medium":@"painted.png"},@"items":items};
  NSDictionary *info=@{@"name":@"NeoStation painted-button test skin",@"identifier":@"org.neostation.press.flat",@"debug":@NO,
    @"gameTypeIdentifier":@"com.rileytestut.delta.game.nes",@"representations":@{@"iphone":@{@"standard":@{@"portrait":rep},@"edgeToEdge":@{@"portrait":rep}}}};
  [[NSJSONSerialization dataWithJSONObject:info options:0 error:nil] writeToFile:[folder stringByAppendingPathComponent:@"info.json"] atomically:YES];
  [[NSJSONSerialization dataWithJSONObject:@{@"consoles":@[@"nes"]} options:0 error:nil] writeToFile:[folder stringByAppendingPathComponent:@"neostation-skin.json"] atomically:YES];
}

// Original test artwork, with the same geometry as the flat fixture. The
// texture deliberately defeats the older perimeter/background estimator.
static void SkinProbeBuildCompositeSkins(NSString *root) {
  NSString *flat=[root stringByAppendingPathComponent:@"press-flat"];
  UIImage *original=[UIImage imageWithContentsOfFile:[flat stringByAppendingPathComponent:@"painted.png"]];
  NSData *infoData=[NSData dataWithContentsOfFile:[flat stringByAppendingPathComponent:@"info.json"]];
  for(NSString *name in @[@"press-texture",@"press-authored",@"press-alpha"]){
    NSString *folder=[root stringByAppendingPathComponent:name];
    [NSFileManager.defaultManager createDirectoryAtPath:folder withIntermediateDirectories:YES attributes:nil error:nil];
    // PNGs don't retain UIImage.scale when read back from a plain filename.
    // Use the JSON mapping size, not the reloaded image's pixel-size points.
    UIGraphicsImageRenderer *draw=[[UIGraphicsImageRenderer alloc] initWithSize:CGSizeMake(360,250)];
    BOOL alpha=[name isEqual:@"press-alpha"];
    UIImage *normal=[draw imageWithActions:^(UIGraphicsImageRendererContext *ctx){
      [original drawInRect:CGRectMake(0,0,360,250) blendMode:kCGBlendModeNormal alpha:alpha ? 0.6 : 1];
      [[UIColor colorWithWhite:0.9 alpha:alpha ? 0.15 : 0.3] setFill];
      for(int y=0;y<250;y+=3)for(int x=0;x<360;x+=3)
        if((x/3+y/3)%2==0)UIRectFillUsingBlendMode(CGRectMake(x,y,1,1),kCGBlendModeNormal);
    }];
    [UIImagePNGRepresentation(normal) writeToFile:[folder stringByAppendingPathComponent:@"painted.png"] atomically:YES];
    if([name isEqual:@"press-authored"]){
      UIImage *pressed=[draw imageWithActions:^(UIGraphicsImageRendererContext *ctx){
        [normal drawAtPoint:CGPointZero];
        [[UIColor colorWithWhite:0 alpha:0.25] setFill];UIRectFillUsingBlendMode(CGRectMake(0,0,360,250),kCGBlendModeNormal);
      }];
      [UIImagePNGRepresentation(pressed) writeToFile:[folder stringByAppendingPathComponent:@"painted_pressed.png"] atomically:YES];
    }
    NSMutableDictionary *info=[NSJSONSerialization JSONObjectWithData:infoData options:NSJSONReadingMutableContainers error:nil];
    info[@"name"]=name;info[@"identifier"]=[@"org.neostation." stringByAppendingString:name];
    NSMutableDictionary *rep=info[@"representations"][@"iphone"][@"standard"][@"portrait"];
    if(alpha)rep[@"translucent"]=@YES;
    // Same authored geometry offered to both devices and orientations;
    // the production aspect-fit transform must keep masks aligned.
    info[@"representations"]=@{@"iphone":@{@"standard":@{@"portrait":rep,@"landscape":rep}},
      @"ipad":@{@"standard":@{@"portrait":rep,@"landscape":rep}}};
    [[NSJSONSerialization dataWithJSONObject:info options:0 error:nil] writeToFile:[folder stringByAppendingPathComponent:@"info.json"] atomically:YES];
    [[NSJSONSerialization dataWithJSONObject:@{@"consoles":@[@"nes"]} options:0 error:nil] writeToFile:[folder stringByAppendingPathComponent:@"neostation-skin.json"] atomically:YES];
  }
}

@interface LibretroGameViewController (SkinPressProbePrivate)
- (void)applicationWillResignActive;
- (void)applicationDidBecomeActive;
- (void)menuPressed;
- (void)updateControlsVisibility;
@end

@interface LibretroFrontendMenu (SkinPressProbePrivate)
- (LibretroMenuPage *)skinsPage;
@end

@interface SkinProbeTouch : UITouch
@property(nonatomic) CGPoint probePoint;
@end
@implementation SkinProbeTouch
- (CGPoint)locationInView:(UIView *)view { return self.probePoint; }
- (NSTimeInterval)timestamp { return CACurrentMediaTime(); }
@end

@interface SkinPressRunner : NSObject
@property(nonatomic, strong) LibretroSession *session;
@property(nonatomic, strong) NSMutableDictionary *result;
@property(nonatomic, strong) NSDictionary *scenario;
@property(nonatomic, copy) dispatch_block_t completion;
@property(nonatomic, strong) NSMutableArray *checks;
@property(nonatomic, strong) NSMutableDictionary<NSString *, SkinProbeTouch *> *touches;
@property(nonatomic, strong) GCVirtualController *virtualController;
@property(nonatomic) NSUInteger stage;
@property(nonatomic) NSUInteger preparationAttempts;
@property(nonatomic) NSUInteger menuWaitAttempts;
@property(nonatomic) NSUInteger inputWaitAttempts;
@property(nonatomic, strong) LibretroSkinRenderer *layoutRenderer;
@property(nonatomic, strong) UIImage *buttonRest;
- (void)advance;
@end

@implementation SkinPressRunner
- (LibretroGameViewController *)controller { return [self.session valueForKey:@"controller"]; }
- (LibretroSkinRenderer *)renderer { return [self.controller valueForKey:@"skinRenderer"]; }
- (LibretroInputState *)input { return [self.session valueForKey:@"input"]; }
- (LibretroSkinLayoutResult *)layout { return [self.controller valueForKey:@"layout"]; }
- (void)check:(BOOL)passed name:(NSString *)name {
  [self.checks addObject:@{@"name":name,@"passed":passed ? @YES : @NO}];
  Progress(@"%@: %@ %@", self.result[@"name"], passed ? @"PASS" : @"FAIL", name);
}
- (LibretroLaidOutItem *)button:(NSString *)name {
  for (LibretroLaidOutItem *i in self.layout.items) {
    if (i.item.kind == LibretroSkinItemKindButton && [i.item.inputs containsObject:name]) return i;
  }
  return nil;
}
- (id)layers:(LibretroLaidOutItem *)item {
  for (id l in [self.renderer valueForKey:@"items"]) {
    if ([[l valueForKey:@"identifier"] isEqual:item.item.identifier]) return l;
  }
  return nil;
}
- (LibretroLaidOutItem *)primaryButton { return [self button:@"a"] ?: [self button:@"b"]; }
- (CGPoint)center:(LibretroLaidOutItem *)i { return CGPointMake(i.frame.x+i.frame.w/2,i.frame.y+i.frame.h/2); }
- (void)touch:(NSString *)key at:(CGPoint)point begin:(BOOL)begin {
  SkinProbeTouch *touch = self.touches[key];
  if (touch == nil) { touch=[SkinProbeTouch new]; self.touches[key]=touch; }
  touch.probePoint = point;
  NSSet *set=[NSSet setWithObject:touch];
  if (begin) [self.controller.overlay touchesBegan:set withEvent:nil];
  else [self.controller.overlay touchesMoved:set withEvent:nil];
  LibretroTouchTracker *tracker=[self.controller.overlay valueForKey:@"tracker"];
  LibretroTouchResolution *resolution=[tracker resolve];
  NSMutableArray *observations=self.result[@"touchObservations"];
  if(observations==nil){observations=[NSMutableArray array];self.result[@"touchObservations"]=observations;}
  NSMutableArray *contacts=[NSMutableArray array];
  for(LibretroTouchContact *c in resolution.contacts)
    [contacts addObject:@{@"mode":@(c.mode),@"point":@[@(c.x),@(c.y)],@"items":c.itemIdentifiers,
      @"sent":c.sentInputs,@"inert":c.inertInputs}];
  [observations addObject:@{@"stage":@(self.stage),@"point":@[@(point.x),@(point.y)],
    @"class":NSStringFromClass(touch.class),@"overlay":self.controller.overlay!=nil ? @YES : @NO,
    @"disabled":self.controller.overlay.controlsDisabled ? @YES : @NO,
    @"enabled":self.controller.touchControlsEnabled ? @YES : @NO,
    @"physical":self.input.hasPhysicalController ? @YES : @NO,
    @"contacts":@(tracker.touchCount),@"buttons":@(resolution.coreInput.buttons),
    @"resolvedContacts":contacts,@"rendererHidden":[self.renderer valueForKey:@"controlsHidden"] ?: @NO,
    @"pressed":resolution.pressedItems.allObjects ?: @[],
    @"renderedPressed":[[self.renderer valueForKey:@"pressed"] allObjects] ?: @[]}];
}
- (void)end:(NSString *)key cancel:(BOOL)cancel {
  SkinProbeTouch *touch=self.touches[key];
  if(touch==nil)return;
  if(cancel)[self.controller.overlay touchesCancelled:[NSSet setWithObject:touch] withEvent:nil];
  else [self.controller.overlay touchesEnded:[NSSet setWithObject:touch] withEvent:nil];
  [self.touches removeObjectForKey:key];
}
- (uint16_t)deliveredButtons {
  uint64_t frame=0;
  LibretroInputSnapshot snapshot=[self.input lastDelivered:&frame];
  self.result[@"lastInputFrame"]=@(frame);
  return snapshot.buttons[0];
}
// UIKit's visual transition is synchronous (checked at touch-down). The
// emulation thread is asynchronous: wait for its actual poll, not a fixed
// 250 ms wall-clock slot on a contended Simulator runner. Missing delivery
// still fails after two seconds; no input state or assertion is replaced.
- (BOOL)waitForCoreInputPoll {
  if([self deliveredButtons]!=0){self.inputWaitAttempts=0;return NO;}
  if(self.inputWaitAttempts++>=100){self.inputWaitAttempts=0;return NO;}
  self.result[@"corePollWaitRetries"]=@([self.result[@"corePollWaitRetries"] unsignedIntegerValue]+1);
  self.stage--;
  dispatch_after(dispatch_time(DISPATCH_TIME_NOW,NSEC_PER_SEC/50),dispatch_get_main_queue(),^{[self advance];});
  return YES;
}
- (BOOL)pressed:(LibretroLaidOutItem *)item {
  id layers=[self layers:item];
  NSArray *regions=[layers valueForKey:@"pressureRegions"];
  if(regions.count>0)return [[layers valueForKey:@"pressedState"] boolValue];
  CALayer *face=[layers valueForKey:@"artwork"];
  return face!=nil && face.transform.m11 < 0.99;
}

- (UIImage *)padImage:(LibretroLaidOutItem *)pad {
  @autoreleasepool {
    UIGraphicsImageRendererFormat *format=[UIGraphicsImageRendererFormat defaultFormat];
    format.scale=self.renderer.traitCollection.displayScale;
    if(format.scale<=0)format.scale=UIScreen.mainScreen.scale;
    format.preferredRange=UIGraphicsImageRendererFormatRangeStandard;
    // Capture at the display's pixel grid, then crop integer pixels. A 1x
    // translated capture resamples masked layers twice but the unmasked
    // reference only once, producing differences absent on the display.
    UIGraphicsImageRenderer *render=[[UIGraphicsImageRenderer alloc] initWithSize:self.renderer.bounds.size format:format];
    UIImage *whole=[render imageWithActions:^(UIGraphicsImageRendererContext *ctx){
      [self.renderer.layer renderInContext:ctx.CGContext];
    }];
    CGFloat scale=format.scale;
    CGRect pixels=CGRectIntegral(CGRectMake(pad.frame.x*scale,pad.frame.y*scale,pad.frame.w*scale,pad.frame.h*scale));
    CGRect crop=CGRectMake(pixels.origin.x/scale,pixels.origin.y/scale,pixels.size.width/scale,pixels.size.height/scale);
    UIGraphicsImageRenderer *extract=[[UIGraphicsImageRenderer alloc] initWithSize:crop.size format:format];
    return [extract imageWithActions:^(UIGraphicsImageRendererContext *ctx){
      [whole drawAtPoint:CGPointMake(-crop.origin.x,-crop.origin.y) blendMode:kCGBlendModeCopy alpha:1];
    }];
  }
}
- (void)verifyDirectionalArtwork {
  LibretroLaidOutItem *pad=nil;
  for(LibretroLaidOutItem *item in self.layout.items)if(item.item.kind==LibretroSkinItemKindDPad){pad=item;break;}
  if(pad==nil)return;
  id layers=[self layers:pad];NSArray *regions=[layers valueForKey:@"pressureRegions"];
  [self check:regions.count==4 name:@"four prepared directional regions including monobloc skins"];
  if(regions.count!=4)return;
  CALayer *face=[layers valueForKey:@"artwork"];
  UIImage *rest=[self padImage:pad];
  self.result[@"dpadFrame"]=@[@(pad.frame.x),@(pad.frame.y),@(pad.frame.w),@(pad.frame.h)];
  NSString *padFolder=DocumentsPath(@"SkinFrames");
  [UIImagePNGRepresentation(rest) writeToFile:[padFolder stringByAppendingPathComponent:
    [self.result[@"name"] stringByAppendingString:@"-dpad-rest.png"]] atomically:YES];
  // Compare prepared rest with the original single texture, including
  // alpha. This catches a duplicated face or a mask seam before any press.
  BOOL composite=[[layers valueForKey:@"compositePressure"] boolValue];
  CALayer *source=composite ? [self.renderer valueForKey:@"backgroundLayer"] : [layers valueForKey:@"image"];
  CALayer *savedMask=source.mask;
  [CATransaction begin];[CATransaction setDisableActions:YES];
  source.mask=nil; for(CALayer *region in regions)region.hidden=YES;
  UIImage *unsplit=[self padImage:pad];
  CAShapeLayer *fullMask=[CAShapeLayer layer];fullMask.frame=source.bounds;
  fullMask.contentsScale=source.contentsScale;fullMask.edgeAntialiasingMask=0;
  fullMask.path=[UIBezierPath bezierPathWithRect:source.bounds].CGPath;
  source.mask=fullMask;
  UIImage *maskedOriginal=[self padImage:pad];
  source.mask=savedMask;for(CALayer *region in regions)region.hidden=NO;
  [CATransaction commit];
  [UIImagePNGRepresentation(unsplit) writeToFile:[padFolder stringByAppendingPathComponent:
    [self.result[@"name"] stringByAppendingString:@"-dpad-original.png"]] atomically:YES];
  [UIImagePNGRepresentation(maskedOriginal) writeToFile:[padFolder stringByAppendingPathComponent:
    [self.result[@"name"] stringByAppendingString:@"-dpad-original-full-mask.png"]] atomically:YES];
  CFDataRef reference=CGDataProviderCopyData(CGImageGetDataProvider(rest.CGImage));
  size_t width=CGImageGetWidth(rest.CGImage),height=CGImageGetHeight(rest.CGImage),stride=CGImageGetBytesPerRow(rest.CGImage);
  const uint8_t *before=CFDataGetBytePtr(reference);
  CFDataRef unsplitData=CGDataProviderCopyData(CGImageGetDataProvider(unsplit.CGImage));
  const uint8_t *original=CFDataGetBytePtr(unsplitData);
  CFDataRef maskedData=CGDataProviderCopyData(CGImageGetDataProvider(maskedOriginal.CGImage));
  const uint8_t *masked=CFDataGetBytePtr(maskedData);
  NSUInteger seamPixels=0,maximum=0,maskDifference=0,splitVsFullMask=0;
  for(size_t y=0;y<height;y++)for(size_t x=0;x<width;x++){
    NSUInteger difference=0;
    for(int c=0;c<4;c++)difference=MAX(difference,(NSUInteger)abs(before[y*stride+x*4+c]-original[y*stride+x*4+c]));
    if(difference>2)seamPixels++; maximum=MAX(maximum,difference);
    NSUInteger md=0,sd=0;
    for(int c=0;c<4;c++){
      md=MAX(md,(NSUInteger)abs(masked[y*stride+x*4+c]-original[y*stride+x*4+c]));
      sd=MAX(sd,(NSUInteger)abs(masked[y*stride+x*4+c]-before[y*stride+x*4+c]));
    }
    if(md>2)maskDifference++;if(sd>2)splitVsFullMask++;
  }
  self.result[@"restSplitDifference"]=@{@"pixelsAboveTwoLevels":@(seamPixels),@"maximum":@(maximum),
    @"fullMaskVsOriginal":@(maskDifference),@"splitVsFullMask":@(splitVsFullMask),@"captureScale":@(rest.scale)};
  [self check:seamPixels==0 name:@"rest preserves original texture and alpha without seams (2/255 rounding tolerance)"];
  CFRelease(unsplitData);
  CFRelease(maskedData);
  NSArray *cases=@[@[@0.5,@0.1,@1],@[@0.5,@0.9,@2],@[@0.1,@0.5,@4],@[@0.9,@0.5,@8],
    @[@0.9,@0.1,@9],@[@0.1,@0.9,@6],@[@0.1,@0.1,@5],@[@0.9,@0.9,@10]];
  NSTimeInterval start=CACurrentMediaTime();
  NSUInteger index=0;
  for(NSArray *entry in cases){
    NSUInteger expected=[entry[2] unsignedIntegerValue];
    CGPoint point=CGPointMake(pad.frame.x+pad.frame.w*[entry[0] doubleValue],pad.frame.y+pad.frame.h*[entry[1] doubleValue]);
    [self touch:@"direction-sweep" at:point begin:index==0];
    BOOL correct=CATransform3DIsIdentity(face.transform);
    for(id region in regions){
      BOOL active=([region valueForKey:@"direction"] && ([[region valueForKey:@"direction"] unsignedIntegerValue]&expected)!=0);
      NSArray *frames=[region valueForKey:@"frames"];
      correct=correct && [[region valueForKey:@"down"] boolValue]==active &&
        ((CALayer *)[region valueForKey:@"texture"]).contents==(active ? frames.lastObject : frames.firstObject);
    }
    [self check:correct name:[NSString stringWithFormat:@"direction mask %lu affects only its own regions",(unsigned long)expected]];
    UIImage *image=[self padImage:pad];
    CFDataRef pixels=CGDataProviderCopyData(CGImageGetDataProvider(image.CGImage));
    const uint8_t *after=CFDataGetBytePtr(pixels); NSUInteger outside=0,inside=0;
    for(size_t y=0;y<height;y++)for(size_t x=0;x<width;x++){
      BOOL affected=NO;
      CGPoint point=CGPointMake((floor(pad.frame.x*rest.scale)+x+0.5)/rest.scale,
                               (floor(pad.frame.y*rest.scale)+y+0.5)/rest.scale);
      for(id region in regions)if(([[region valueForKey:@"direction"] unsignedIntegerValue]&expected)!=0 &&
        CGRectContainsPoint(CGRectInset(((CALayer *)region).frame,-1/rest.scale,-1/rest.scale),point))affected=YES;
      if(memcmp(before+y*stride+x*4,after+y*stride+x*4,4)) { if(affected)inside++;else outside++; }
    }
    [self check:outside==0 && inside>0 name:[NSString stringWithFormat:@"pixels mask %lu: active changes, centre and other arms identical",(unsigned long)expected]];
    {
      NSString *folder=DocumentsPath(@"SkinFrames");
      NSString *file=[NSString stringWithFormat:@"%@-dpad-%lu.png",self.result[@"name"],(unsigned long)expected];
      [UIImagePNGRepresentation(image) writeToFile:[folder stringByAppendingPathComponent:file] atomically:YES];
    }
    NSMutableArray *metrics=self.result[@"directionPixelMetrics"];
    if(metrics==nil){metrics=[NSMutableArray array];self.result[@"directionPixelMetrics"]=metrics;}
    [metrics addObject:@{@"directions":@(expected),@"insideChanged":@(inside),@"outsideChanged":@(outside)}];
    CFRelease(pixels);index++;
  }
  self.result[@"directionSweepWithPixelChecksSeconds"]=@(CACurrentMediaTime()-start);
  self.result[@"pressurePreparedBytes"]=[self.renderer valueForKey:@"pressureBytes"];
  [self check:[[self.renderer valueForKey:@"pressureBytes"] unsignedIntegerValue]<=32u*1024u*1024u name:@"pressure resources stay within 32 MiB per layout"];
  [self touch:@"direction-sweep" at:CGPointMake(pad.frame.x+pad.frame.w*0.5,pad.frame.y+pad.frame.h*0.1) begin:NO];
  [self touch:@"second-direction" at:CGPointMake(pad.frame.x+pad.frame.w*0.9,pad.frame.y+pad.frame.h*0.5) begin:YES];
  NSUInteger multi=0;for(id region in regions)if([[region valueForKey:@"down"] boolValue])multi|=[[region valueForKey:@"direction"] unsignedIntegerValue];
  [self check:multi==9 name:@"two fingers on separate arms animate their union"];
  [self end:@"direction-sweep" cancel:YES];
  multi=0;for(id region in regions)if([[region valueForKey:@"down"] boolValue])multi|=[[region valueForKey:@"direction"] unsignedIntegerValue];
  [self check:multi==8 name:@"lifting one D-pad finger preserves the other arm"];
  [self end:@"second-direction" cancel:YES];
  BOOL clear=YES;for(id region in regions)clear=clear && ![[region valueForKey:@"down"] boolValue];
  [self check:clear name:@"direction cancellation resets all four regions"];
  // Measure submission cost only; separate from screenshots and image
  // preparation, and explicitly not a physical-device GPU/FPS claim.
  [self.renderer setPressedItems:[NSSet setWithObject:pad.item.identifier]];
  NSTimeInterval updates=CACurrentMediaTime();
  for(NSUInteger iteration=0;iteration<500;iteration++)
    [self.renderer setDPadDirections:@{pad.item.identifier:@(iteration%2 ? 1 : 8)}];
  self.result[@"directionUpdateAverageMicroseconds"]=@((CACurrentMediaTime()-updates)*1000000/500);
  [self.renderer setPressedItems:[NSSet set]];[self.renderer setDPadDirections:@{}];
  [self.renderer setEditing:YES selectedItem:nil];[self.renderer setEditing:NO selectedItem:nil];
  [self check:((CALayer *)[layers valueForKey:@"image"]).contents!=nil || composite
    name:@"layout editor preserves prepared D-pad artwork"];
  UIImage *released=[self padImage:pad];
  [self check:[UIImagePNGRepresentation(rest) isEqualToData:UIImagePNGRepresentation(released)]
    name:@"released D-pad pixels exactly match rest after editor and rapid presses"];
  [UIImagePNGRepresentation(released) writeToFile:[padFolder stringByAppendingPathComponent:
    [self.result[@"name"] stringByAppendingString:@"-dpad-released.png"]] atomically:YES];
  CFRelease(reference);
}

- (void)verifyLayouts:(NSUInteger)index {
  if(index==4){self.layoutRenderer=nil;[self advance];return;}
  const LibretroSize sizes[]={{390,844},{844,390},{768,1024},{1024,768}};
  LibretroSkin *skin=[self.session valueForKey:@"currentSkin"];
  // This helper is invoked after the main scenario changed back to default;
  // reload only the original test fixture, using the real decoder/layout.
  skin=[LibretroSkin skinWithDirectory:DocumentsPath(@"Libretro/Skins/press-texture") consoleGeometry:nil errorCode:nil];
  LibretroSkinRepresentation *rep=[skin representationForOrientation:index%2 ? LibretroSkinOrientationLandscape : LibretroSkinOrientationPortrait
    iPad:index>=2 edgeToEdge:NO];
  LibretroInsets insets={0,0,0,0};
  LibretroSkinLayoutResult *layout=[LibretroSkinLayout layoutRepresentation:rep viewSize:sizes[index] safeInsets:insets overrides:nil];
  self.layoutRenderer=[[LibretroSkinRenderer alloc] initWithCacheDirectory:DocumentsPath(@"SkinLayoutProbeCache")];
  self.layoutRenderer.frame=CGRectMake(0,0,sizes[index].w,sizes[index].h);
  // Queue a different layout first; its completion must not enter this one.
  LibretroSkinLayoutResult *old=[LibretroSkinLayout layoutRepresentation:rep viewSize:sizes[(index+1)%4] safeInsets:insets overrides:nil];
  [self.layoutRenderer showRepresentation:rep layout:old opacity:1 controlsHidden:NO];
  [self.layoutRenderer showRepresentation:rep layout:layout opacity:0.65 controlsHidden:NO];
  [self waitForLayout:layout representation:rep index:index attempt:0];
}
- (void)waitForLayout:(LibretroSkinLayoutResult *)layout representation:(LibretroSkinRepresentation *)rep index:(NSUInteger)index attempt:(NSUInteger)attempt {
  LibretroLaidOutItem *pad=layout.items.firstObject;
  id layers=nil;for(id candidate in [self.layoutRenderer valueForKey:@"items"])
    if([[candidate valueForKey:@"identifier"] isEqual:pad.item.identifier])layers=candidate;
  NSArray *regions=[layers valueForKey:@"pressureRegions"];
  if(regions.count!=4 && attempt<100){
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW,NSEC_PER_SEC/20),dispatch_get_main_queue(),^{
      [self waitForLayout:layout representation:rep index:index attempt:attempt+1];});return;
  }
  [self check:regions.count==4 && [layers valueForKey:@"laidOut"]==pad
    name:[NSString stringWithFormat:@"layout %lu: final geometry wins over stale preparation",(unsigned long)index]];
  LibretroTouchTracker *tracker=[LibretroTouchTracker new];
  [tracker applyLayout:layout inputMap:[LibretroInputMap mapForConsole:@"nes"] touchRemap:nil];
  [tracker beginTouch:@1 x:pad.frame.x+pad.frame.w*0.9 y:pad.frame.y+pad.frame.h*0.1];
  LibretroTouchResolution *resolution=[tracker resolve];
  [self.layoutRenderer setPressedItems:resolution.pressedItems];[self.layoutRenderer setDPadDirections:resolution.dpadDirections];
  NSUInteger active=0;BOOL inside=YES,pixelAligned=YES;
  NSMutableArray *geometry=[NSMutableArray array];
  for(id region in regions){
    if([[region valueForKey:@"down"] boolValue])active|=[[region valueForKey:@"direction"] unsignedIntegerValue];
    // CALayer reconstructs frame from position/anchor/bounds; allow only
    // floating-point arithmetic noise, far below any fraction of a pixel.
    inside=inside && CGRectContainsRect(CGRectInset(CGRectMake(pad.frame.x,pad.frame.y,pad.frame.w,pad.frame.h),-1e-7,-1e-7),((CALayer *)region).frame);
    [geometry addObject:NSStringFromCGRect(((CALayer *)region).frame)];
    CGFloat scale=self.layoutRenderer.traitCollection.displayScale;
    if(scale<=0)scale=UIScreen.mainScreen.scale;
    CGRect rf=((CALayer *)region).frame;
    for(NSNumber *edge in @[@(rf.origin.x),@(rf.origin.y),@(CGRectGetMaxX(rf)),@(CGRectGetMaxY(rf))])
      pixelAligned=pixelAligned && fabs(edge.doubleValue*scale-round(edge.doubleValue*scale))<1e-6;
  }
  NSMutableArray *layouts=self.result[@"layoutMetrics"];
  if(layouts==nil){layouts=[NSMutableArray array];self.result[@"layoutMetrics"]=layouts;}
  [layouts addObject:@{@"index":@(index),@"active":@(active),@"inside":@(inside),
    @"buttons":@(resolution.coreInput.buttons),@"pad":NSStringFromCGRect(CGRectMake(pad.frame.x,pad.frame.y,pad.frame.w,pad.frame.h)),@"regions":geometry}];
  [self check:active==9 && inside && resolution.coreInput.buttons!=0
    name:[NSString stringWithFormat:@"layout %lu: aligned diagonal and mapped inputs",(unsigned long)index]];
  [self check:pixelAligned name:[NSString stringWithFormat:@"layout %lu: cut edges use whole display pixels",(unsigned long)index]];
  [self.layoutRenderer showRepresentation:rep layout:layout opacity:0.65 controlsHidden:YES];
  BOOL reset=YES;for(id region in regions)reset=reset && ![[region valueForKey:@"down"] boolValue];
  [self check:reset && !((CALayer *)[layers valueForKey:@"artwork"]).hidden
    name:[NSString stringWithFormat:@"layout %lu: controller hides pressure without background holes",(unsigned long)index]];
  [self.layoutRenderer showRepresentation:nil layout:nil opacity:1 controlsHidden:NO];
  [self check:[[self.layoutRenderer valueForKey:@"items"] count]==0 name:@"cleared layout owns no prepared regions"];
  [self verifyLayouts:index+1];
}
- (void)chooseSkin:(NSString *)skin {
  [self.controller menuPressed];
  LibretroFrontendMenu *frontend=[self.session valueForKey:@"frontendMenu"];
  LibretroMenuPage *page=[frontend skinsPage];
  BOOL found=NO;
  for (NSString *orientation in @[@"portrait",@"landscape"]) {
    NSString *identifier=[NSString stringWithFormat:@"libretro-skin-%@-%@",orientation,skin];
    LibretroMenuRow *row=MenuRowWithIdentifier(page,identifier);
    if(row.action!=nil && row.enabled){row.action(page);found=YES;}
  }
  [self check:found name:[@"in-game skin action: " stringByAppendingString:skin]];
  self.menuWaitAttempts=0;
  [self resumeAfterMenuPresentation];
}
- (void)verifyAuthoredReload {
  LibretroSkin *skin=[LibretroSkin skinWithDirectory:DocumentsPath(@"Libretro/Skins/press-authored") consoleGeometry:nil errorCode:nil];
  LibretroSkinRepresentation *rep=[skin representationForOrientation:LibretroSkinOrientationPortrait iPad:NO edgeToEdge:NO];
  LibretroSkinLayoutResult *layout=[LibretroSkinLayout layoutRepresentation:rep viewSize:(LibretroSize){390,844}
    safeInsets:(LibretroInsets){0,0,0,0} overrides:nil];
  self.layoutRenderer=[[LibretroSkinRenderer alloc] initWithCacheDirectory:DocumentsPath(@"SkinReloadProbeCache")];
  self.layoutRenderer.frame=CGRectMake(0,0,390,844);
  [self.layoutRenderer showRepresentation:rep layout:layout opacity:1 controlsHidden:NO];
  [self waitForAuthoredReload:rep layout:layout expected:nil attempt:0];
}
- (void)waitForAuthoredReload:(LibretroSkinRepresentation *)rep layout:(LibretroSkinLayoutResult *)layout
                    expected:(NSArray *)expected attempt:(NSUInteger)attempt {
  id item=[[self.layoutRenderer valueForKey:@"items"] firstObject];
  NSArray *regions=[item valueForKey:@"pressureRegions"];
  if(regions.count!=4 && attempt<100){
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW,NSEC_PER_SEC/20),dispatch_get_main_queue(),^{
      [self waitForAuthoredReload:rep layout:layout expected:expected attempt:attempt+1];});return;
  }
  NSMutableArray *pixels=[NSMutableArray array];
  for(id region in regions){
    CGImageRef image=(__bridge CGImageRef)[[region valueForKey:@"frames"] lastObject];
    [pixels addObject:CFBridgingRelease(CGDataProviderCopyData(CGImageGetDataProvider(image)))];
  }
  if(expected==nil && pixels.count==4){
    [self.layoutRenderer showRepresentation:nil layout:nil opacity:1 controlsHidden:NO];
    [LibretroSkinRenderer purgeCacheForSkinDirectory:@"" cacheDirectory:@""];
    [self.layoutRenderer showRepresentation:rep layout:layout opacity:1 controlsHidden:NO];
    CALayer *pressed=[self.layoutRenderer valueForKey:@"pressedBackgroundLayer"];
    [self check:[pressed valueForKey:@"neostationSkinReadyKey"]==nil
      name:@"reselecting an uncached authored skin waits for its pressed image"];
    [self waitForAuthoredReload:rep layout:layout expected:pixels attempt:0];return;
  }
  [self check:expected!=nil && pixels.count==4 && [pixels isEqualToArray:expected]
    name:@"authored directional pixels survive clear, cache eviction and reload"];
  self.layoutRenderer=nil;[self advance];
}
- (void)resumeAfterMenuPresentation {
  UINavigationController *menu=[self.session valueForKey:@"menu"];
  if(menu.isBeingPresented && self.menuWaitAttempts++<200){
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW,NSEC_PER_SEC/20),dispatch_get_main_queue(),^{[self resumeAfterMenuPresentation];});
    return;
  }
  [self check:!menu.isBeingPresented name:@"native menu presentation finished before resume"];
  SEL close=NSSelectorFromString(@"closeMenu");
  ((void(*)(id,SEL))[self.session methodForSelector:close])(self.session,close);
  self.menuWaitAttempts=0;
  [self waitForMenuDismissal];
}
- (void)waitForMenuDismissal {
  BOOL closed=[self.session valueForKey:@"menu"]==nil && self.controller.presentedViewController==nil;
  if(!closed && self.menuWaitAttempts++<200){
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW,NSEC_PER_SEC/20),dispatch_get_main_queue(),^{[self waitForMenuDismissal];});
    return;
  }
  [self check:closed name:@"native resume completion precedes gameplay contacts"];
  [self next];
}
- (void)capture:(NSString *)suffix {
  NSString *name=[NSString stringWithFormat:@"%@-%@",self.result[@"name"],suffix];
  CaptureNextGameFrame(self.session,name,^(NSDictionary *frame) {
    NSString *png=frame[@"png"];
    UIImage *game=png!=nil ? [UIImage imageWithContentsOfFile:DocumentsPath([@"ShaderFrames/" stringByAppendingString:png])] : nil;
    [self check:game!=nil name:[@"real presented game frame: " stringByAppendingString:suffix]];
    UIGraphicsImageRendererFormat *format=[UIGraphicsImageRendererFormat defaultFormat];
    format.scale=2;
    CGSize size=self.controller.view.bounds.size;
    UIGraphicsImageRenderer *render=[[UIGraphicsImageRenderer alloc] initWithSize:size format:format];
    UIImage *image=[render imageWithActions:^(UIGraphicsImageRendererContext *context) {
      [game drawInRect:CGRectMake(0,0,size.width,size.height)];
      [self.renderer.layer renderInContext:context.CGContext];
    }];
    NSString *folder=DocumentsPath(@"SkinFrames");
    [NSFileManager.defaultManager createDirectoryAtPath:folder withIntermediateDirectories:YES attributes:nil error:nil];
    [UIImagePNGRepresentation(image) writeToFile:[folder stringByAppendingPathComponent:[name stringByAppendingString:@".png"]] atomically:YES];
    LibretroLaidOutItem *item=[self primaryButton];
    self.result[@"buttonFrame"]=@[@(item.frame.x),@(item.frame.y),@(item.frame.w),@(item.frame.h)];
    self.result[@"captureScale"]=@2;
    [self next];
  });
}
- (void)next {
  dispatch_after(dispatch_time(DISPATCH_TIME_NOW,(int64_t)(0.25*NSEC_PER_SEC)),dispatch_get_main_queue(),^{[self advance];});
}
- (void)advance {
  NSUInteger stage=self.stage++;
  LibretroLaidOutItem *a=[self primaryButton];
  switch(stage) {
    case 0: [self chooseSkin:self.scenario[@"skinPress"]]; break;
    case 1: {
      self.result[@"skinName"]=[[self.session valueForKey:@"currentSkin"] valueForKey:@"name"] ?: @"";
      [self check:a!=nil name:@"skin has a mapped game button"];
      if(a==nil){self.result[@"skinChecks"]=self.checks;SkinProbeRestoreControllers();self.completion();return;}
      id layers=[self layers:a];
      CALayer *image=[layers valueForKey:@"image"];
      BOOL separated=image.contents!=nil || [layers valueForKey:@"shape"]!=nil || [[layers valueForKey:@"pressureRegions"] count]>0;
      if(!separated && self.preparationAttempts++<20){self.stage--;[self next];break;}
      [self check:separated name:@"button artwork separated before contact"];
      self.result[@"extracted"]= [[layers valueForKey:@"extracted"] boolValue] ? @YES : @NO;
      if([self.scenario[@"skinPress"] isEqual:@"press-flat"]) {
        CALayer *background=[self.renderer valueForKey:@"backgroundLayer"];
        CAShapeLayer *mask=(CAShapeLayer *)background.mask;
        CGPoint center=[self center:a];
        center.x-=background.frame.origin.x;center.y-=background.frame.origin.y;
        BOOL hole=mask.path!=NULL && !CGPathContainsPoint(mask.path,NULL,center,YES);
        CALayer *backplate=[layers valueForKey:@"backplate"];
        [self check:[[layers valueForKey:@"extracted"] boolValue] && hole && backplate.contents!=nil
              name:@"baked test-skin button cropped with original removed"];
        id original=image.contents;
        [self.renderer setEditing:YES selectedItem:nil];
        [self.renderer setEditing:NO selectedItem:nil];
        [self check:image.contents!=nil && image.contents==original
          name:@"leaving the layout editor preserves extracted artwork"];
      }
      self.buttonRest=[self padImage:a];
      [self capture:@"rest"]; break;
    }
    case 2:
      [self touch:@"one" at:[self center:a] begin:YES];
      [self check:[self pressed:a] name:@"artwork depresses synchronously at contact"];
      [self next];break;
    case 3:
      if([self waitForCoreInputPoll])break;
      [self check:[self pressed:a] && [self deliveredButtons]!=0 name:@"held artwork and input received at the actual core poll"];
      [self check:![UIImagePNGRepresentation(self.buttonRest) isEqualToData:UIImagePNGRepresentation([self padImage:a])]
        name:@"pressed button pixels differ from rest (skin only, no moving game pixels)"];
      [self capture:@"pressed"]; break;
    case 4: [self touch:@"two" at:[self center:a] begin:YES]; [self end:@"one" cancel:NO]; [self next]; break;
    case 5: [self check:[self pressed:a] && [self deliveredButtons]!=0 name:@"second finger keeps the same button held"];
      [self end:@"two" cancel:YES]; [self next]; break;
    case 6: [self check:![self pressed:a] && [self deliveredButtons]==0 name:@"cancellation releases visual and core state"];
      [self check:[UIImagePNGRepresentation(self.buttonRest) isEqualToData:UIImagePNGRepresentation([self padImage:a])]
        name:@"released button pixels exactly match rest"];
      [self capture:@"released"]; break;
    case 7:
      [self verifyDirectionalArtwork];
      [self touch:@"change-skin" at:[self center:a] begin:YES];
      [self chooseSkin:@"default"];
      [self check:[[self.renderer valueForKey:@"pressed"] count]==0 name:@"in-game skin replacement clears a held button"];
      [self.touches removeAllObjects];break;
    case 8: {
      a=[self primaryButton];
      [self touch:@"one" at:[self center:a] begin:YES];
      LibretroLaidOutItem *b=[self button:@"b"];
      if(b!=nil && b!=a){[self touch:@"one" at:[self center:b] begin:NO]; self.result[@"slideChecked"]=@YES;}
      [self next];break;
    }
    case 9: {
      LibretroLaidOutItem *b=[self button:@"b"];
      if([self.result[@"slideChecked"] boolValue]) [self check:![self pressed:a] && [self pressed:b] name:@"slide changes the actual pressed button"];
      LibretroLaidOutItem *pad=nil,*stick=nil;
      for(LibretroLaidOutItem *i in self.layout.items) {
        if(i.item.kind==LibretroSkinItemKindDPad && pad==nil)pad=i;
        if(i.item.kind==LibretroSkinItemKindThumbstick && stick==nil)stick=i;
      }
      LibretroLaidOutItem *direction=pad ?: stick;
      self.result[@"combinedDirectionIsAnalog"]=(pad==nil && stick!=nil) ? @YES : @NO;
      if(direction!=nil){[self touch:@"pad" at:CGPointMake(direction.frame.x+direction.frame.w-3,direction.frame.y+3) begin:YES];}
      [self next];break;
    }
    case 10: {
      NSDictionary *directions=[self.renderer valueForKey:@"dpadDirections"];
      LibretroInputSnapshot input=[self.input lastDelivered:NULL];
      BOOL directional=[self.result[@"combinedDirectionIsAnalog"] boolValue]
        ? [[self.renderer valueForKey:@"stickVectors"] count]>0 && input.analog[0][0][0]!=0 && input.analog[0][0][1]!=0
        : directions.count>0;
      [self check:directional && [self deliveredButtons]!=0 name:@"direction diagonal plus held button reaches core and artwork"];
      [self.controller menuPressed];
      [self check:[[self.renderer valueForKey:@"pressed"] count]==0 name:@"opening menu releases every visual button"];
      [self.touches removeAllObjects];self.menuWaitAttempts=0;
      [self resumeAfterMenuPresentation];break;
    }
    case 11: {
      [self check:[self deliveredButtons]==0 name:@"menu clears queued touch inputs"];
      LibretroLaidOutItem *stick=nil;
      for(LibretroLaidOutItem *i in self.layout.items) if(i.item.kind==LibretroSkinItemKindThumbstick){stick=i;break;}
      if(stick){[self touch:@"stick" at:CGPointMake(stick.frame.x+stick.frame.w,stick.frame.y) begin:YES];self.result[@"stickId"]=stick.item.identifier;}
      [self next];break;
    }
    case 12: {
      NSString *stickIdentifier=self.result[@"stickId"];
      if(stickIdentifier){
        NSDictionary *v=[self.renderer valueForKey:@"stickVectors"];
        LibretroLaidOutItem *stick=nil;
        for(LibretroLaidOutItem *i in self.layout.items)if([i.item.identifier isEqual:stickIdentifier]){stick=i;break;}
        id layers=[self layers:stick];CALayer *cap=[layers valueForKey:@"knobImage"] ?: [layers valueForKey:@"knob"];
        LibretroInputSnapshot input=[self.input lastDelivered:NULL];
        [self check:v[stickIdentifier]!=nil && cap.transform.m11<0.99 &&
          (input.analog[0][0][0]!=0 || input.analog[0][0][1]!=0)
          name:@"analog stick cap depression and vector reach the actual core input"];
      }
      [self.controller applicationWillResignActive];
      [self check:[[self.renderer valueForKey:@"pressed"] count]==0 name:@"background transition cancels held controls"];
      [self.touches removeAllObjects];
      [self.controller applicationDidBecomeActive];[self next];break;
    }
    case 13: [self check:[self deliveredButtons]==0 name:@"background transition clears the input latch"];
      [self touch:@"rotation" at:[self center:[self primaryButton]] begin:YES];
      [self.controller viewWillTransitionToSize:CGSizeMake(self.controller.view.bounds.size.height,self.controller.view.bounds.size.width) withTransitionCoordinator:nil];
      [self next];break;
    case 14: [self check:[self deliveredButtons]==0 && [[self.renderer valueForKey:@"pressed"] count]==0 name:@"rotation cancels inputs and pressed artwork"];
      [self.touches removeAllObjects];
      // No physical hardware is claimed: use Apple's virtual controller to
      // exercise the production GCController polling and remap path.
      {
        GCVirtualControllerConfiguration *config=[GCVirtualControllerConfiguration new];
        config.elements=[NSSet setWithArray:@[GCInputButtonA,GCInputButtonB,GCInputButtonX,GCInputButtonY,
          GCInputLeftThumbstick,GCInputRightThumbstick]];
        config.hidden=YES;
        self.virtualController=[[GCVirtualController alloc] initWithConfiguration:config];
        __block BOOL answered=NO;
        [self.virtualController connectWithReplyHandler:^(NSError *error){
          if(answered)return;answered=YES;
          self.result[@"virtualControllerError"]=error.localizedDescription ?: @"";
          [self check:error==nil name:@"Apple virtual controller connected"];
          sSkinProbeController=self.virtualController.controller;
          [self.virtualController setValue:1 forButtonElement:GCInputButtonA];
          [self next];
        }];
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW,5*NSEC_PER_SEC),dispatch_get_main_queue(),^{
          if(answered)return;answered=YES;
          [self check:NO name:@"Apple virtual controller connection timeout"];
          [self next];
        });
      }
      break;
    case 15: [self.input pollControllers];
      if([self waitForCoreInputPoll])break;
      self.result[@"controllerObservation"]=@{@"connected":self.virtualController.controller!=nil ? @YES : @NO,
        @"extended":self.virtualController.controller.extendedGamepad!=nil ? @YES : @NO,
        @"value":@(self.virtualController.controller.extendedGamepad.buttonA.value),
        @"count":@(GCController.controllers.count),@"physical":self.input.hasPhysicalController ? @YES : @NO};
      [self check:self.input.hasPhysicalController && [self deliveredButtons]!=0 name:@"controller input uses the existing polling and console map"];
      [self check:self.controller.overlay.controlsDisabled name:@"connected controller disables tactile game contacts"];
      [self.virtualController setValue:0 forButtonElement:GCInputButtonA];
      [self.virtualController disconnect];sSkinProbeController=nil;[self next];break;
    case 16:
      if([self.scenario[@"skinPress"] isEqual:@"press-flat"]){[self chooseSkin:@"press-complex"];break;}
      [self advance];break;
    case 17:
      if([self.scenario[@"skinPress"] isEqual:@"press-flat"]){
        LibretroLaidOutItem *button=[self primaryButton];
        id layers=[self layers:button];
        if([[layers valueForKey:@"pressureRegions"] count]==0 && self.preparationAttempts++<40){self.stage--;[self next];break;}
        [self check:![[layers valueForKey:@"extracted"] boolValue] && [[layers valueForKey:@"pressureRegions"] count]>0
              name:@"complex catalog background animates locally without inferred backplate"];
      }
      [self advance];break;
    case 18:
      if([self.scenario[@"skinPress"] isEqual:@"press-texture"]){[self verifyLayouts:0];break;}
      if([self.scenario[@"skinPress"] isEqual:@"press-authored"]){[self verifyAuthoredReload];break;}
      [self advance];break;
    default:
      [self check:[self deliveredButtons]==0 name:@"controller disconnect leaves no held input"];
      self.result[@"skinChecks"]=self.checks;
      self.result[@"realDeviceTested"]=@NO;
      SkinProbeRestoreControllers();
      self.completion();break;
  }
}
@end

static void RunSkinPressProbe(LibretroSession *session, NSDictionary *scenario, NSMutableDictionary *result,
                              dispatch_block_t completion) {
  SkinPressRunner *runner=[SkinPressRunner new];
  runner.session=session;runner.scenario=scenario;runner.result=result;runner.completion=completion;
  runner.checks=[NSMutableArray array];runner.touches=[NSMutableDictionary dictionary];
  runner.result[@"simulatorControllersExcluded"]=@(GCController.controllers.count);
  SkinProbeIsolateControllers();
  [runner.input pollControllers];[runner.controller updateControlsVisibility];
  runner.controller.overlay.recordsContacts=YES;
  dispatch_after(dispatch_time(DISPATCH_TIME_NOW,NSEC_PER_SEC),dispatch_get_main_queue(),^{[runner advance];});
}
