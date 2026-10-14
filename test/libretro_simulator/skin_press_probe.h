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
- (BOOL)pressed:(LibretroLaidOutItem *)item {
  id layers=[self layers:item];
  CALayer *face=[layers valueForKey:@"artwork"];
  return face!=nil && face.transform.m11 < 0.99;
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
  SEL close=NSSelectorFromString(@"closeMenu");
  ((void(*)(id,SEL))[self.session methodForSelector:close])(self.session,close);
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
    case 0: [self chooseSkin:self.scenario[@"skinPress"]]; [self next]; break;
    case 1: {
      self.result[@"skinName"]=[[self.session valueForKey:@"currentSkin"] valueForKey:@"name"] ?: @"";
      [self check:a!=nil name:@"skin has a mapped game button"];
      if(a==nil){self.result[@"skinChecks"]=self.checks;SkinProbeRestoreControllers();self.completion();return;}
      id layers=[self layers:a];
      CALayer *image=[layers valueForKey:@"image"];
      BOOL separated=image.contents!=nil || [layers valueForKey:@"shape"]!=nil;
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
      }
      [self capture:@"rest"]; break;
    }
    case 2:
      [self touch:@"one" at:[self center:a] begin:YES];
      [self check:[self pressed:a] name:@"artwork depresses synchronously at contact"];
      [self next];break;
    case 3: [self check:[self pressed:a] && [self deliveredButtons]!=0 name:@"immediate pressed artwork and emulated core input"];
      [self capture:@"pressed"]; break;
    case 4: [self touch:@"two" at:[self center:a] begin:YES]; [self end:@"one" cancel:NO]; [self next]; break;
    case 5: [self check:[self pressed:a] && [self deliveredButtons]!=0 name:@"second finger keeps the same button held"];
      [self end:@"two" cancel:YES]; [self next]; break;
    case 6: [self check:![self pressed:a] && [self deliveredButtons]==0 name:@"cancellation releases visual and core state"];
      [self capture:@"released"]; break;
    case 7:
      [self touch:@"change-skin" at:[self center:a] begin:YES];
      [self chooseSkin:@"default"];
      [self check:[[self.renderer valueForKey:@"pressed"] count]==0 name:@"in-game skin replacement clears a held button"];
      [self.touches removeAllObjects];[self next];break;
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
      SEL close=NSSelectorFromString(@"closeMenu");
      ((void(*)(id,SEL))[self.session methodForSelector:close])(self.session,close);
      [self.touches removeAllObjects];[self next];break;
    }
    case 11: {
      [self check:[self deliveredButtons]==0 name:@"menu clears queued touch inputs"];
      LibretroLaidOutItem *stick=nil;
      for(LibretroLaidOutItem *i in self.layout.items) if(i.item.kind==LibretroSkinItemKindThumbstick){stick=i;break;}
      if(stick){[self touch:@"stick" at:CGPointMake(stick.frame.x+stick.frame.w,stick.frame.y) begin:YES];self.result[@"stickId"]=stick.item.identifier;}
      [self next];break;
    }
    case 12: {
      NSString *id=self.result[@"stickId"];
      if(id){
        NSDictionary *v=[self.renderer valueForKey:@"stickVectors"];
        LibretroLaidOutItem *stick=nil;
        for(LibretroLaidOutItem *i in self.layout.items)if([i.item.identifier isEqual:id]){stick=i;break;}
        id layers=[self layers:stick];CALayer *cap=[layers valueForKey:@"knobImage"] ?: [layers valueForKey:@"knob"];
        LibretroInputSnapshot input=[self.input lastDelivered:NULL];
        [self check:v[id]!=nil && cap.transform.m11<0.99 &&
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
      self.result[@"controllerObservation"]=@{@"connected":self.virtualController.controller!=nil ? @YES : @NO,
        @"extended":self.virtualController.controller.extendedGamepad!=nil ? @YES : @NO,
        @"value":@(self.virtualController.controller.extendedGamepad.buttonA.value),
        @"count":@(GCController.controllers.count),@"physical":self.input.hasPhysicalController ? @YES : @NO};
      [self check:self.input.hasPhysicalController && [self deliveredButtons]!=0 name:@"controller input uses the existing polling and console map"];
      [self check:self.controller.overlay.controlsDisabled name:@"connected controller disables tactile game contacts"];
      [self.virtualController setValue:0 forButtonElement:GCInputButtonA];
      [self.virtualController disconnect];sSkinProbeController=nil;[self next];break;
    case 16:
      if([self.scenario[@"skinPress"] isEqual:@"press-flat"]){[self chooseSkin:@"press-complex"];[self next];break;}
      [self advance];break;
    case 17:
      if([self.scenario[@"skinPress"] isEqual:@"press-flat"]){
        LibretroLaidOutItem *button=[self primaryButton];
        id layers=[self layers:button];
        [self check:![[layers valueForKey:@"extracted"] boolValue]
              name:@"complex catalog background refused without a duplicated animated face"];
        LibretroSkin *skin=[self.session valueForKey:@"currentSkin"];
        [self check:[skin.warnings containsObject:LibretroSkinWarningPaintedControls] name:@"complex skin explains that an adapted variant is needed"];
      }
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
