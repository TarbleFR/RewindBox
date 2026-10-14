// Scripted UIKit contacts inside the actual embedded game session. No
// synthetic renderer or input sink replaces the production implementations.
#import "LibretroGameViewController.h"
#import "LibretroSkinRenderer.h"
#import "LibretroTouchOverlay.h"
#import "LibretroInputState.h"
#import <GameController/GameController.h>

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
      if(a==nil){self.completion();return;}
      id layers=[self layers:a];
      BOOL separated=[layers valueForKey:@"image"]!=nil || [layers valueForKey:@"shape"]!=nil;
      [self check:separated name:@"button artwork separated before contact"];
      self.result[@"extracted"]= [[layers valueForKey:@"extracted"] boolValue] ? @YES : @NO;
      if([self.scenario[@"skinPress"] isEqual:@"press-flat"])
        [self check:[[layers valueForKey:@"extracted"] boolValue] && self.renderer.layer!=nil
              name:@"baked test-skin button cropped with original removed"];
      [self capture:@"rest"]; break;
    }
    case 2: [self touch:@"one" at:[self center:a] begin:YES]; [self next]; break;
    case 3: [self check:[self pressed:a] && [self deliveredButtons]!=0 name:@"immediate pressed artwork and emulated core input"];
      [self capture:@"pressed"]; break;
    case 4: [self touch:@"two" at:[self center:a] begin:YES]; [self end:@"one" cancel:NO]; [self next]; break;
    case 5: [self check:[self pressed:a] && [self deliveredButtons]!=0 name:@"second finger keeps the same button held"];
      [self end:@"two" cancel:YES]; [self next]; break;
    case 6: [self check:![self pressed:a] && [self deliveredButtons]==0 name:@"cancellation releases visual and core state"];
      [self capture:@"released"]; break;
    case 7: [self chooseSkin:@"default"]; [self next]; break;
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
      LibretroLaidOutItem *pad=nil;
      for(LibretroLaidOutItem *i in self.layout.items) if(i.item.kind==LibretroSkinItemKindDPad){pad=i;break;}
      if(pad!=nil){[self touch:@"pad" at:CGPointMake(pad.frame.x+pad.frame.w-3,pad.frame.y+3) begin:YES];}
      [self next];break;
    }
    case 10: {
      NSDictionary *directions=[self.renderer valueForKey:@"dpadDirections"];
      [self check:directions.count>0 && [self deliveredButtons]!=0 name:@"D-pad diagonal plus held button reaches core and artwork"];
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
      if(id){NSDictionary *v=[self.renderer valueForKey:@"stickVectors"]; [self check:v[id]!=nil name:@"analog stick cap follows delivered vector"];}
      [self.controller applicationWillResignActive];
      [self check:[[self.renderer valueForKey:@"pressed"] count]==0 name:@"background transition cancels held controls"];
      [self.touches removeAllObjects];[self next];break;
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
        config.elements=[NSSet setWithArray:@[GCInputButtonA,GCInputDirectionPad]];
        self.virtualController=[[GCVirtualController alloc] initWithConfiguration:config];
        [self.virtualController connectWithReplyHandler:^(NSError *error){
          self.result[@"virtualControllerError"]=error.localizedDescription ?: @"";
          [self check:error==nil name:@"Apple virtual controller connected"];
          [self.virtualController.controller.extendedGamepad.buttonA setValue:1];
          [self next];
        }];
      }
      break;
    case 15: [self.input pollControllers]; [self check:self.input.hasPhysicalController && [self deliveredButtons]!=0 name:@"controller input uses the existing polling and console map"];
      [self.virtualController.controller.extendedGamepad.buttonA setValue:0];
      [self.virtualController disconnect]; [self next];break;
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
      self.completion();break;
  }
}
@end

static void RunSkinPressProbe(LibretroSession *session, NSDictionary *scenario, NSMutableDictionary *result,
                              dispatch_block_t completion) {
  SkinPressRunner *runner=[SkinPressRunner new];
  runner.session=session;runner.scenario=scenario;runner.result=result;runner.completion=completion;
  runner.checks=[NSMutableArray array];runner.touches=[NSMutableDictionary dictionary];
  dispatch_after(dispatch_time(DISPATCH_TIME_NOW,NSEC_PER_SEC),dispatch_get_main_queue(),^{[runner advance];});
}
