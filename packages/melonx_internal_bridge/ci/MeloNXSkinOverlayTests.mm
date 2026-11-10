#import <XCTest/XCTest.h>
#import "MeloNXSkinOverlay.h"
#import "MeloNXSkinInteraction.h"
#import "SkinFrameCheck.h"

// The production MeloNXSkinOverlay on the REAL shipped Switch Pocket archive
// (unpacked by test_skin_overlay_ui.rb into MELONX_SKIN_FIXTURE), driven by touches
// in the iOS Simulator: press and release of every Switch command with the embedded
// Core's own button index (native/melonx/EmbeddedInput.cs), the D-pad and its
// diagonals, both sticks (exact vectors, cap travel, neutral), L3 and R3, Menu once,
// HOME and Capture said and never sent, several fingers, slide, cancel, release,
// rotation, phone-size letterbox, the drawn shapes and the pressed drawing kept
// inside each outline, and the real overlay renders. The pad is a recorder; no Core
// and no game run here (MeloNXInputRouter's Core path is test/melonx_input_test.py's).
// A simulator is not an iPhone.

@interface MLXFakeTouch : UITouch
@property(nonatomic) CGPoint point;
@end
@implementation MLXFakeTouch
- (CGPoint)locationInView:(UIView*)view { return self.point; }
@end

@interface MeloNXSkinOverlayTests : XCTestCase
- (NSString*)skinId;
- (NSMutableArray<NSString*>*)events;               // "b4+" / "b4-"
- (NSMutableArray<NSArray<NSNumber*>*>*)sticks;     // each change sent: lx ly rx ry
- (NSInteger)menuCount;
- (NSMutableArray<NSString*>*)system;              // "home" / "capture" reported to the session
- (NSDictionary*)layoutForPortrait:(BOOL)portrait;
- (MeloNXSkinOverlay*)overlayPortrait:(BOOL)portrait;
- (NSDictionary*)itemNamed:(NSString*)name portrait:(BOOL)portrait;
- (CGPoint)centerOf:(NSDictionary*)item fx:(CGFloat)fx fy:(CGFloat)fy;
- (MLXFakeTouch*)touchAt:(CGPoint)point;
- (void)begin:(MLXFakeTouch*)touch on:(MeloNXSkinOverlay*)overlay;
- (void)move:(MLXFakeTouch*)touch to:(CGPoint)point on:(MeloNXSkinOverlay*)overlay;
- (void)end:(MLXFakeTouch*)touch on:(MeloNXSkinOverlay*)overlay;
@end

@implementation MeloNXSkinOverlayTests {
  NSMutableArray<NSString*>* _events;      // "b4+" / "b4-"
  NSMutableArray<NSArray<NSNumber*>*>* _sticks;
  NSInteger _menuCount;
  NSMutableArray<NSString*>* _system;
  NSDictionary* _info;
}

/// The installed skin folder under test (the shipped archive's id).
- (NSString*)skinId { return @"switch-pocket"; }
- (NSMutableArray<NSString*>*)events { return _events; }
- (NSMutableArray<NSArray<NSNumber*>*>*)sticks { return _sticks; }
- (NSInteger)menuCount { return _menuCount; }
- (NSMutableArray<NSString*>*)system { return _system; }

- (NSString*)documents {
  return NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES).firstObject;
}

- (void)writeSelection:(NSDictionary*)document {
  NSString* directory = [[self documents] stringByAppendingPathComponent:@"Libretro/Config/Frontend"];
  [NSFileManager.defaultManager createDirectoryAtPath:directory withIntermediateDirectories:YES attributes:nil error:nil];
  NSData* data = [NSJSONSerialization dataWithJSONObject:document options:0 error:nil];
  [data writeToFile:[directory stringByAppendingPathComponent:@"switch.json"] atomically:YES];
}

- (void)setUp {
  NSString* fixture = NSProcessInfo.processInfo.environment[@"MELONX_SKIN_FIXTURE"];
  XCTAssertNotNil(fixture, @"the runner passes the unpacked skin through MELONX_SKIN_FIXTURE");
  NSString* target = [[self documents] stringByAppendingPathComponent:@"Libretro/Skins"];
  [NSFileManager.defaultManager removeItemAtPath:[[self documents] stringByAppendingPathComponent:@"Libretro"] error:nil];
  [NSFileManager.defaultManager createDirectoryAtPath:target withIntermediateDirectories:YES attributes:nil error:nil];
  NSError* error = nil;
  [NSFileManager.defaultManager copyItemAtPath:[fixture stringByAppendingPathComponent:[self skinId]]
                                        toPath:[target stringByAppendingPathComponent:[self skinId]] error:&error];
  XCTAssertNil(error);
  _info = [NSJSONSerialization JSONObjectWithData:[NSData dataWithContentsOfFile:
      [[target stringByAppendingPathComponent:[self skinId]] stringByAppendingPathComponent:@"info.json"]] options:0 error:nil];
  XCTAssertNotNil(_info);
  _events = [NSMutableArray array];
  _sticks = [NSMutableArray array];
  _menuCount = 0;
  _system = [NSMutableArray array];
  [self writeSelection:@{@"console" : @{@"skin.portrait" : [self skinId], @"skin.landscape" : [self skinId]}}];
}

- (NSDictionary*)layoutForPortrait:(BOOL)portrait {
  const CGSize native = UIScreen.mainScreen.nativeBounds.size;
  const CGFloat shortSide = MIN(native.width, native.height);
  const BOOL tall = MAX(native.width, native.height) / shortSide > 2.0;
  // MeloNXSkinOverlay's layout choice: edge-to-edge first on a tall iPhone, standard
  // first otherwise, then the other one (Switch Pocket ships edge-to-edge only).
  NSDictionary* iphone = _info[@"representations"][@"iphone"];
  NSDictionary* display = iphone[tall ? @"edgeToEdge" : @"standard"] ?: iphone[tall ? @"standard" : @"edgeToEdge"];
  return display[portrait ? @"portrait" : @"landscape"];
}

- (MeloNXSkinOverlay*)overlayPortrait:(BOOL)portrait {
  MeloNXSkinOverlay* overlay = [[MeloNXSkinOverlay alloc] initWithGameKey:@"game.iso"];
  XCTAssertTrue(overlay.hasSkin);
  // The recorders are captured directly (the overlay is local to the test, no cycle).
  NSMutableArray<NSString*>* events = _events;
  NSMutableArray<NSArray<NSNumber*>*>* sticks = _sticks;
  __weak MeloNXSkinOverlayTests* weakSelf = self;
  overlay.buttonChanged = ^(uint32_t button, BOOL pressed) {
    [events addObject:[NSString stringWithFormat:@"b%u%@", button, pressed ? @"+" : @"-"]];
  };
  overlay.sticksChanged = ^(float lx, float ly, float rx, float ry) {
    [sticks addObject:@[ @(lx), @(ly), @(rx), @(ry) ]];
  };
  NSMutableArray<NSString*>* system = _system;
  overlay.systemButtonHandler = ^(NSString* name) { [system addObject:name]; };
  overlay.menuHandler = ^{
    MeloNXSkinOverlayTests* strongSelf = weakSelf;
    if (strongSelf != nil) strongSelf->_menuCount++;
  };
  [self layout:overlay portrait:portrait];
  return overlay;
}

- (void)layout:(MeloNXSkinOverlay*)overlay portrait:(BOOL)portrait {
  NSDictionary* mapping = [self layoutForPortrait:portrait][@"mappingSize"];
  overlay.frame = CGRectMake(0, 0, [mapping[@"width"] doubleValue], [mapping[@"height"] doubleValue]);
  [overlay setNeedsLayout];
  [overlay layoutIfNeeded];
}

- (NSDictionary*)itemNamed:(NSString*)name portrait:(BOOL)portrait {
  for (NSDictionary* item in [self layoutForPortrait:portrait][@"items"]) {
    id inputs = item[@"inputs"];
    if ([inputs isKindOfClass:NSArray.class] && [inputs containsObject:name]) return item;
    if ([inputs isKindOfClass:NSDictionary.class] && [[inputs allValues] containsObject:name]) return item;
  }
  return nil;
}

- (CGPoint)centerOf:(NSDictionary*)item fx:(CGFloat)fx fy:(CGFloat)fy {
  NSDictionary* f = item[@"frame"];
  return CGPointMake([f[@"x"] doubleValue] + fx * [f[@"width"] doubleValue], [f[@"y"] doubleValue] + fy * [f[@"height"] doubleValue]);
}

- (MLXFakeTouch*)touchAt:(CGPoint)point {
  MLXFakeTouch* touch = [MLXFakeTouch new];
  touch.point = point;
  return touch;
}

- (void)begin:(MLXFakeTouch*)touch on:(MeloNXSkinOverlay*)overlay { [overlay touchesBegan:[NSSet setWithObject:touch] withEvent:nil]; }
- (void)move:(MLXFakeTouch*)touch to:(CGPoint)point on:(MeloNXSkinOverlay*)overlay {
  touch.point = point;
  [overlay touchesMoved:[NSSet setWithObject:touch] withEvent:nil];
}
- (void)end:(MLXFakeTouch*)touch on:(MeloNXSkinOverlay*)overlay { [overlay touchesEnded:[NSSet setWithObject:touch] withEvent:nil]; }

- (void)testChosenOrientationsDecideTheMask {
  MeloNXSkinOverlay* both = [[MeloNXSkinOverlay alloc] initWithGameKey:@"game.iso"];
  XCTAssertTrue(both.hasSkin);
  XCTAssertEqual(both.supportedOrientationMask, UIInterfaceOrientationMaskAllButUpsideDown);
  [self writeSelection:@{@"console" : @{@"skin.portrait" : [self skinId]}}];
  XCTAssertEqual([[MeloNXSkinOverlay alloc] initWithGameKey:nil].supportedOrientationMask, UIInterfaceOrientationMaskPortrait,
                 @"portrait only chosen, although the file also has a landscape layout");
  [self writeSelection:@{@"console" : @{@"skin.landscape" : [self skinId]}}];
  XCTAssertEqual([[MeloNXSkinOverlay alloc] initWithGameKey:nil].supportedOrientationMask, UIInterfaceOrientationMaskLandscape,
                 @"landscape only chosen, although the file also has a portrait layout");
  [self writeSelection:@{@"console" : @{@"skin.portrait" : [self skinId], @"skin.landscape" : [self skinId]},
                         @"games" : @{@"game.iso" : @{@"skin.landscape" : @"default"}}}];
  XCTAssertEqual([[MeloNXSkinOverlay alloc] initWithGameKey:@"game.iso"].supportedOrientationMask, UIInterfaceOrientationMaskPortrait,
                 @"the game's explicit default overrides the console's landscape skin");
  XCTAssertEqual([[MeloNXSkinOverlay alloc] initWithGameKey:@"other.iso"].supportedOrientationMask,
                 UIInterfaceOrientationMaskAllButUpsideDown, @"another game inherits the console");
  [self writeSelection:@{@"console" : @{@"skin.portrait" : @"default"}}];
  XCTAssertFalse([[MeloNXSkinOverlay alloc] initWithGameKey:nil].hasSkin, @"default: no overlay at all");
}

- (void)checkEveryButtonPortrait:(BOOL)portrait {
  MeloNXSkinOverlay* overlay = [self overlayPortrait:portrait];
  XCTAssertTrue(overlay.layoutActive);
  XCTAssertTrue(CGRectGetWidth(overlay.screenFrame) > 0);
  NSDictionary<NSString*, NSNumber*>* pad = MLXTestPad();
  for (NSString* name in pad) {
    NSDictionary* item = [self itemNamed:name portrait:portrait];
    XCTAssertNotNil(item, @"%@ is visible", name);
    [_events removeAllObjects];
    MLXFakeTouch* touch = [self touchAt:[self centerOf:item fx:0.5 fy:0.5]];
    [self begin:touch on:overlay];
    XCTAssertEqualObjects(_events, (@[ [NSString stringWithFormat:@"b%@+", pad[name]] ]), @"%@ press", name);
    [self end:touch on:overlay];
    XCTAssertEqualObjects(_events, (@[ [NSString stringWithFormat:@"b%@+", pad[name]], [NSString stringWithFormat:@"b%@-", pad[name]] ]),
                          @"%@ release", name);
  }
  // D-pad: the four directions and a diagonal, each released.
  NSDictionary* dpad = [self itemNamed:@"up" portrait:portrait];
  // Core indices: Up 11, Down 12, Left 13, Right 14; a diagonal holds two.
  struct { CGFloat x, y; NSArray* expect; } cases[] = {{0.5, 0.1, @[ @11 ]}, {0.5, 0.9, @[ @12 ]}, {0.1, 0.5, @[ @13 ]},
                                                        {0.9, 0.5, @[ @14 ]}, {0.9, 0.9, @[ @14, @12 ]}, {0.1, 0.1, @[ @13, @11 ]}};
  for (auto& c : cases) {
    [_events removeAllObjects];
    MLXFakeTouch* touch = [self touchAt:[self centerOf:dpad fx:c.x fy:c.y]];
    [self begin:touch on:overlay];
    NSMutableSet* pressed = [NSMutableSet set];
    for (NSString* e in _events) if ([e hasSuffix:@"+"]) [pressed addObject:@([[e substringWithRange:NSMakeRange(1, e.length - 2)] integerValue])];
    XCTAssertEqualObjects(pressed, [NSSet setWithArray:c.expect]);
    [self end:touch on:overlay];
    for (NSNumber* b in c.expect) {
      NSString* released = [NSString stringWithFormat:@"b%@-", b];
      XCTAssertTrue([_events containsObject:released], @"%@ released", released);
    }
  }
  // Menu: opens the session menu once, then nothing stays held.
  [_events removeAllObjects];
  NSDictionary* menu = [self itemNamed:@"menu" portrait:portrait];
  XCTAssertNotNil(menu);
  MLXFakeTouch* menuTouch = [self touchAt:[self centerOf:menu fx:0.5 fy:0.5]];
  [self begin:menuTouch on:overlay];
  [self end:menuTouch on:overlay];
  XCTestExpectation* later = [self expectationWithDescription:@"menu after the touch event"];
  dispatch_async(dispatch_get_main_queue(), ^{ [later fulfill]; });
  [self waitForExpectations:@[ later ] timeout:3];
  XCTAssertEqual(_menuCount, 1, @"Menu opens the session menu exactly once");
  XCTAssertEqualObjects(_events, @[], @"Menu sends nothing to the pad");
}

- (void)testEveryControlPressesAndReleasesInPortrait { [self checkEveryButtonPortrait:YES]; }
- (void)testEveryControlPressesAndReleasesInLandscape { [self checkEveryButtonPortrait:NO]; }

- (void)checkSticksPortrait:(BOOL)portrait {
  MeloNXSkinOverlay* overlay = [self overlayPortrait:portrait];
  for (NSString* side in @[ @"left", @"right" ]) {
    NSDictionary* item = [self itemNamed:[side stringByAppendingString:@"ThumbstickUp"] portrait:portrait];
    XCTAssertNotNil(item);
    [_sticks removeAllObjects];
    [_events removeAllObjects];
    MLXFakeTouch* touch = [self touchAt:[self centerOf:item fx:0.5 fy:0.5]];
    [self begin:touch on:overlay];
    [self move:touch to:[self centerOf:item fx:1.6 fy:0.5] on:overlay];  // far to the right, even outside the base
    NSArray<NSNumber*>* last = _sticks.lastObject;
    XCTAssertNotNil(last);
    const BOOL left = [side isEqualToString:@"left"];
    XCTAssertEqualWithAccuracy(left ? last[0].floatValue : last[2].floatValue, 1.0, 0.01, @"%@ stick to the right", side);
    XCTAssertEqualWithAccuracy(left ? last[1].floatValue : last[3].floatValue, 0.0, 0.01);
    XCTAssertEqualWithAccuracy(left ? last[2].floatValue : last[0].floatValue, 0.0, 0.01, @"the other stick stays neutral");
    [self move:touch to:[self centerOf:item fx:0.5 fy:1.9] on:overlay];  // down (positive Y)
    XCTAssertGreaterThan((left ? _sticks.lastObject[1] : _sticks.lastObject[3]).floatValue, 0.9f);
    XCTAssertEqualObjects(_events, @[], @"moving a stick presses no button, never L3 or R3");
    [self end:touch on:overlay];
    XCTAssertEqualObjects(_sticks.lastObject, (@[ @0, @0, @0, @0 ]), @"back to neutral");
  }
}

- (void)testSticksMoveAndReturnToNeutralInPortrait { [self checkSticksPortrait:YES]; }
- (void)testSticksMoveAndReturnToNeutralInLandscape { [self checkSticksPortrait:NO]; }

- (void)testSeveralFingersAndEveryWayOfReleasing {
  MeloNXSkinOverlay* overlay = [self overlayPortrait:YES];
  MLXFakeTouch* stick = [self touchAt:[self centerOf:[self itemNamed:@"leftThumbstickUp" portrait:YES] fx:0.5 fy:0.5]];
  MLXFakeTouch* face = [self touchAt:[self centerOf:[self itemNamed:@"a" portrait:YES] fx:0.5 fy:0.5]];
  MLXFakeTouch* r1 = [self touchAt:[self centerOf:[self itemNamed:@"r" portrait:YES] fx:0.5 fy:0.5]];
  [self begin:stick on:overlay];
  [self begin:face on:overlay];
  [self begin:r1 on:overlay];
  [self move:stick to:[self centerOf:[self itemNamed:@"leftThumbstickUp" portrait:YES] fx:1.0 fy:0.5] on:overlay];
  XCTAssertTrue([_events containsObject:@"b0+"] && [_events containsObject:@"b10+"], @"stick + A + R together");
  XCTAssertEqualWithAccuracy(_sticks.lastObject[0].floatValue, 1.0, 0.05);
  // A finger that slides off its button onto another one changes control (no stuck button).
  [_events removeAllObjects];
  [self move:face to:[self centerOf:[self itemNamed:@"b" portrait:YES] fx:0.5 fy:0.5] on:overlay];
  XCTAssertTrue([_events containsObject:@"b0-"] && [_events containsObject:@"b1+"], @"A released, B pressed");
  // Cancel (a system interruption) releases like a lift.
  [_events removeAllObjects];
  [overlay touchesCancelled:[NSSet setWithObject:face] withEvent:nil];
  XCTAssertTrue([_events containsObject:@"b1-"]);
  // The session's release (menu opening, stop, background) lets go of everything at once.
  [_events removeAllObjects];
  [overlay releaseAllInputs];
  XCTAssertTrue([_events containsObject:@"b10-"]);
  XCTAssertEqualObjects(_sticks.lastObject, (@[ @0, @0, @0, @0 ]));
  [_events removeAllObjects];
  [overlay releaseAllInputs];
  XCTAssertEqualObjects(_events, @[], @"releasing twice sends nothing more");
}

- (void)testTheSkinsOwnMenuHidesTheFloatingOne {
  // MeloNXSkinSession hides the session's floating menu button over a skin with a Menu.
  for (NSNumber* portrait in @[ @YES, @NO ]) {
    MeloNXSkinOverlay* overlay = [self overlayPortrait:portrait.boolValue];
    XCTAssertTrue(overlay.hasMenuControl, @"%@ %@ has its own Menu", [self skinId], portrait.boolValue ? @"portrait" : @"landscape");
  }
}

- (void)testHomeAndCaptureAreSaidNeverSentAndDistinctFromMenu {
  for (NSNumber* portrait in @[ @YES, @NO ]) {
    MeloNXSkinOverlay* overlay = [self overlayPortrait:portrait.boolValue];
    for (NSString* name in @[ @"home", @"capture" ]) {
      NSDictionary* item = [self itemNamed:name portrait:portrait.boolValue];
      XCTAssertNotNil(item, @"%@ is drawn", name);
      [_events removeAllObjects];
      [_system removeAllObjects];
      const NSInteger menus = _menuCount;
      MLXFakeTouch* t = [self touchAt:[self centerOf:item fx:0.5 fy:0.5]];
      [self begin:t on:overlay];
      [self end:t on:overlay];
      XCTestExpectation* later = [self expectationWithDescription:@"after the touch event"];
      dispatch_async(dispatch_get_main_queue(), ^{ [later fulfill]; });
      [self waitForExpectations:@[ later ] timeout:3];
      XCTAssertEqualObjects(_system, @[ name ], @"%@ reported once to the session", name);
      XCTAssertEqualObjects(_events, @[], @"%@ sends no button: the Core has none for it", name);
      XCTAssertEqual(_menuCount, menus, @"%@ never opens the RewindBox menu", name);
    }
  }
}

- (void)testRotationReleasesHeldInputs {
  MeloNXSkinOverlay* overlay = [self overlayPortrait:YES];
  MLXFakeTouch* face = [self touchAt:[self centerOf:[self itemNamed:@"a" portrait:YES] fx:0.5 fy:0.5]];
  [self begin:face on:overlay];
  XCTAssertTrue([_events containsObject:@"b0+"]);
  [self layout:overlay portrait:NO];  // the surface turned: the other layout takes over
  XCTAssertTrue([_events containsObject:@"b0-"], @"the held button was released by the turn");
  XCTAssertTrue(CGRectGetWidth(overlay.screenFrame) > CGRectGetHeight(overlay.screenFrame) * 1.2);
}

#pragma mark Menu return (MeloNXMetalSessionViewController.applyPause, MeloNXSkinInteraction)

/// MeloNXSkinSession.sync with the session's rule (skin.interactive): touches only
/// with no presented controller and no pause; a pause releases every input.
- (void)applySessionRuleTo:(MeloNXSkinOverlay*)overlay presenter:(UIViewController*)presenter paused:(BOOL)paused {
  const BOOL interactive = presenter.presentedViewController == nil && !paused;
  if (!interactive) [overlay releaseAllInputs];
  overlay.userInteractionEnabled = interactive;
}

- (UIViewController*)presenter {
  UIWindow* window = nil;
  for (UIScene* scene in UIApplication.sharedApplication.connectedScenes) {
    if (![scene isKindOfClass:UIWindowScene.class]) continue;
    for (UIWindow* candidate in ((UIWindowScene*)scene).windows) {
      if (candidate.isKeyWindow) window = candidate;
    }
  }
  if (window == nil) window = UIApplication.sharedApplication.delegate.window;
  XCTAssertNotNil(window.rootViewController, @"the harness app shows its root controller");
  return window.rootViewController;
}

- (BOOL)spinUntil:(BOOL (^)(void))condition seconds:(NSTimeInterval)seconds {
  NSDate* end = [NSDate dateWithTimeIntervalSinceNow:seconds];
  while (!condition() && end.timeIntervalSinceNow > 0) {
    [NSRunLoop.mainRunLoop runMode:NSDefaultRunLoopMode beforeDate:[NSDate dateWithTimeIntervalSinceNow:0.01]];
  }
  return condition();
}

- (void)spin:(NSTimeInterval)seconds {
  [self spinUntil:^BOOL { return NO; } seconds:seconds];
}

/// A real action sheet presented from the harness controller, as showMenu does.
- (UIAlertController*)presentSheetFrom:(UIViewController*)presenter {
  UIAlertController* sheet = [UIAlertController alertControllerWithTitle:@"game" message:nil
                                                          preferredStyle:UIAlertControllerStyleActionSheet];
  [sheet addAction:[UIAlertAction actionWithTitle:@"Resume" style:UIAlertActionStyleCancel handler:nil]];
  [presenter presentViewController:sheet animated:YES completion:nil];
  XCTAssertTrue([self spinUntil:^BOOL { return presenter.presentedViewController == sheet && !sheet.isBeingPresented; } seconds:5],
                @"the sheet is presented");
  return sheet;
}

/// The defect (maintainer, IPA 718): after the in-game menu the skin answered no
/// touch until a rotation. The resume ran while the sheet was still being
/// dismissed, so the one sync of the session still read "a controller is
/// presented". Reproduced with a real sheet and a real dismissal: the previous
/// code keeps the skin without touches; MeloNXSkinInteraction gives them back
/// before the first contact, with a stick held when the menu opened.
- (void)testMenuReturnGivesTouchesBackWhenTheResumeRunsDuringTheDismissal {
  UIViewController* presenter = [self presenter];
  MeloNXSkinOverlay* overlay = [self overlayPortrait:NO];
  [presenter.view addSubview:overlay];
  const CGPoint a = [self centerOf:[self itemNamed:@"a" portrait:NO] fx:0.5 fy:0.5];
  NSDictionary* stick = nil;
  for (NSDictionary* item in [self layoutForPortrait:NO][@"items"]) {
    if ([item[@"inputs"] isKindOfClass:NSDictionary.class] && [item[@"inputs"][@"up"] isEqualToString:@"leftThumbstickUp"]) stick = item;
  }
  XCTAssertNotNil(stick, @"the left stick is drawn");
  for (NSNumber* fixed in @[ @NO, @YES ]) {
    for (int round = 0; round < (fixed.boolValue ? 4 : 1); round++) {
      __block BOOL paused = NO;
      [self applySessionRuleTo:overlay presenter:presenter paused:paused];
      XCTAssertTrue(overlay.userInteractionEnabled);
      // A stick held when the skin's Menu opens the session menu.
      MLXFakeTouch* held = [self touchAt:[self centerOf:stick fx:0.5 fy:0.5]];
      [self begin:held on:overlay];
      [self move:held to:[self centerOf:stick fx:0.5 fy:0.05] on:overlay];
      XCTAssertTrue(_sticks.count > 0 && _sticks.lastObject[1].floatValue < -0.5, @"the stick is pushed up");
      paused = YES;  // setPause("menu", true): the skin lets go of everything
      [self applySessionRuleTo:overlay presenter:presenter paused:paused];
      XCTAssertEqualObjects(_sticks.lastObject, (@[ @0, @0, @0, @0 ]), @"the pause centres the held stick");
      [self presentSheetFrom:presenter];
      // "Resume": the action runs while UIKit is still dismissing its sheet.
      [presenter dismissViewControllerAnimated:YES completion:nil];
      XCTAssertNotNil(presenter.presentedViewController, @"the dismissal has not ended when the action runs");
      paused = NO;
      void (^sync)(void) = ^{ [self applySessionRuleTo:overlay presenter:presenter paused:paused]; };
      if (fixed.boolValue) {
        [MLXSkinInteraction syncNowAndWhenUncovered:presenter stillWanted:^BOOL { return !paused; } sync:sync];
      } else {
        sync();  // the previous applyPause: one sync, at the resume
      }
      XCTAssertTrue([self spinUntil:^BOOL { return presenter.presentedViewController == nil; } seconds:5], @"the sheet has gone");
      if (!fixed.boolValue) {
        [self spin:0.3];
        XCTAssertFalse(overlay.userInteractionEnabled, @"previous code: the skin stays without touches after the menu");
        XCTAssertNil([overlay hitTest:a withEvent:nil], @"previous code: the first contact reaches nothing");
        [self end:held on:overlay];
        continue;
      }
      XCTAssertTrue([self spinUntil:^BOOL { return overlay.userInteractionEnabled; } seconds:1],
                    @"round %d: the skin takes touches again once the sheet has gone", round);
      XCTAssertEqual([overlay hitTest:a withEvent:nil], overlay, @"round %d: the first contact reaches the skin", round);
      // The finger held through the menu sends nothing more; the first new contact presses A.
      const NSUInteger stickChanges = _sticks.count;
      [self move:held to:[self centerOf:stick fx:0.95 fy:0.5] on:overlay];
      XCTAssertEqual(_sticks.count, stickChanges, @"round %d: the finger held through the menu is not replayed", round);
      [_events removeAllObjects];
      MLXFakeTouch* first = [self touchAt:a];
      [self begin:first on:overlay];
      [self end:first on:overlay];
      XCTAssertEqualObjects(_events, (@[ @"b0+", @"b0-" ]), @"round %d: the first contact presses and releases A", round);
      [self end:held on:overlay];
      XCTAssertEqual(_sticks.count, stickChanges, @"round %d: lifting the held finger moves no stick", round);
    }
  }
  [overlay removeFromSuperview];
}

/// The usual order (the action after the dismissal) still gives the touches back at
/// once; a pause again during the dismissal (another sheet, a close, another
/// session) keeps them off and stops the follow-up.
- (void)testMenuReturnFollowUpRespectsTheOrderAndStopsWhenNoLongerWanted {
  UIViewController* presenter = [self presenter];
  MeloNXSkinOverlay* overlay = [self overlayPortrait:NO];
  [presenter.view addSubview:overlay];
  __block BOOL paused = YES;
  __block NSInteger syncs = 0;
  void (^sync)(void) = ^{ syncs++; [self applySessionRuleTo:overlay presenter:presenter paused:paused]; };
  [self presentSheetFrom:presenter];
  XCTestExpectation* gone = [self expectationWithDescription:@"dismissed"];
  [presenter dismissViewControllerAnimated:YES completion:^{ [gone fulfill]; }];
  [self waitForExpectations:@[ gone ] timeout:5];
  paused = NO;
  [MLXSkinInteraction syncNowAndWhenUncovered:presenter stillWanted:^BOOL { return !paused; } sync:sync];
  XCTAssertTrue(overlay.userInteractionEnabled, @"after the dismissal: touches at once");
  XCTAssertEqual(syncs, 1, @"nothing presented: no follow-up");

  paused = YES;
  sync();
  [self presentSheetFrom:presenter];
  [presenter dismissViewControllerAnimated:YES completion:nil];
  paused = NO;
  syncs = 0;
  [MLXSkinInteraction syncNowAndWhenUncovered:presenter stillWanted:^BOOL { return !paused; } sync:sync];
  paused = YES;  // paused again before the sheet has gone
  XCTAssertTrue([self spinUntil:^BOOL { return presenter.presentedViewController == nil; } seconds:5]);
  [self spin:0.3];
  XCTAssertEqual(syncs, 1, @"no sync once no longer wanted");
  XCTAssertFalse(overlay.userInteractionEnabled, @"still paused: no touches");
  XCTAssertTrue(MLXSkinInteraction.attemptLimit * 0.05 <= 2.0 + 1e-9, @"the follow-up is bounded to 2 s");
  [overlay removeFromSuperview];
}


- (NSString*)skinFolder {
  return [[NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES).firstObject
      stringByAppendingPathComponent:@"Libretro/Skins"] stringByAppendingPathComponent:[self skinId]];
}

- (CGRect)rect:(NSDictionary*)f {
  return CGRectMake([f[@"x"] doubleValue], [f[@"y"] doubleValue], [f[@"width"] doubleValue], [f[@"height"] doubleValue]);
}

- (NSData*)alphaOf:(NSDictionary*)item size:(CGSize*)size {
  UIImage* image = [UIImage imageWithContentsOfFile:[[self skinFolder] stringByAppendingPathComponent:item[@"asset"][@"normal"]]];
  CGImageRef cg = image.CGImage;
  const size_t w = CGImageGetWidth(cg), h = CGImageGetHeight(cg);
  NSMutableData* data = [NSMutableData dataWithLength:w * h];
  CGContextRef context = CGBitmapContextCreate(data.mutableBytes, w, h, 8, w, NULL, (CGBitmapInfo)kCGImageAlphaOnly);
  CGContextDrawImage(context, CGRectMake(0, 0, w, h), cg);
  CGContextRelease(context);
  *size = CGSizeMake(w, h);
  return data;
}

/// Points of the drawn shape (alpha >= 80 %): its centroid and, in 16 directions,
/// the last opaque point 1.5 pt inside the outline, in mapping points.
- (NSArray<NSValue*>*)shapePoints:(NSDictionary*)item {
  CGSize size;
  NSData* alpha = [self alphaOf:item size:&size];
  const uint8_t* a = (const uint8_t*)alpha.bytes;
  const long w = (long)size.width, h = (long)size.height;
  double sx = 0, sy = 0, n = 0;
  for (long y = 0; y < h; y++)
    for (long x = 0; x < w; x++)
      if (a[y * w + x] >= 204) { sx += x; sy += y; n++; }
  XCTAssertGreaterThan(n, 0);
  const CGRect f = [self rect:item[@"frame"]];
  CGPoint (^toMap)(double, double) = ^CGPoint(double x, double y) {
    return CGPointMake(f.origin.x + (x + 0.5) / w * f.size.width, f.origin.y + (y + 0.5) / h * f.size.height);
  };
  NSMutableArray<NSValue*>* points = [NSMutableArray array];
  const double cx = sx / n, cy = sy / n;
  if (a[(long)cy * w + (long)cx] >= 204) [points addObject:[NSValue valueWithCGPoint:toMap(cx, cy)]];
  const double inset = 1.5 * w / f.size.width;
  for (int k = 0; k < 16; k++) {
    const double angle = k * M_PI / 8, dx = cos(angle), dy = sin(angle);
    double last = -1;
    for (double t = 0; t < MAX(w, h); t += 0.5) {
      const long x = lround(cx + dx * t), y = lround(cy + dy * t);
      if (x < 0 || y < 0 || x >= w || y >= h) break;
      if (a[y * w + x] >= 204) last = t; else if (last >= 0 && t - last > 2) break;
    }
    if (last > inset) [points addObject:[NSValue valueWithCGPoint:toMap(cx + dx * (last - inset), cy + dy * (last - inset))]];
  }
  return points;
}

static NSDictionary<NSString*, NSNumber*>* MLXTestPad(void) {
  // native/melonx/EmbeddedInput.cs: the Core's button indices (Guide 5 is no skin input).
  return @{@"a" : @0, @"b" : @1, @"x" : @2, @"y" : @3, @"minus" : @4, @"plus" : @6, @"l3" : @7, @"r3" : @8,
           @"l" : @9, @"r" : @10, @"zl" : @15, @"zr" : @16};
}

/// Centre and contour of every drawn button press exactly that button (or open the
/// menu once), and its release leaves nothing held: where frames interlock (face
/// buttons, the L3/R3 labels under the sticks) the drawn shape decides.
- (void)checkShapesPortrait:(BOOL)portrait {
  MeloNXSkinOverlay* overlay = [self overlayPortrait:portrait];
  for (NSDictionary* item in [self layoutForPortrait:portrait][@"items"]) {
    if (![item[@"inputs"] isKindOfClass:NSArray.class]) continue;
    NSString* name = [item[@"inputs"] firstObject];
    NSArray<NSValue*>* points = [self shapePoints:item];
    XCTAssertGreaterThanOrEqual(points.count, 12u, @"%@: contour points", name);
    for (NSValue* value in points) {
      const CGPoint p = value.CGPointValue;
      [[self events] removeAllObjects];
      [[self sticks] removeAllObjects];
      [[self system] removeAllObjects];
      const NSInteger menus = [self menuCount];
      MLXFakeTouch* touch = [self touchAt:p];
      [self begin:touch on:overlay];
      if ([name isEqualToString:@"menu"]) {
        [[NSRunLoop mainRunLoop] runUntilDate:[NSDate dateWithTimeIntervalSinceNow:0.02]];
        XCTAssertEqual([self menuCount], menus + 1, @"Menu once at (%.1f, %.1f)", p.x, p.y);
        XCTAssertEqualObjects([self events], @[]);
      } else if ([@[ @"home", @"capture" ] containsObject:name]) {
        [[NSRunLoop mainRunLoop] runUntilDate:[NSDate dateWithTimeIntervalSinceNow:0.02]];
        XCTAssertEqualObjects([self system], @[ name ], @"%@ reported once at (%.1f, %.1f)", name, p.x, p.y);
        XCTAssertEqualObjects([self events], @[], @"%@ sends nothing to the game", name);
        XCTAssertEqual([self menuCount], menus, @"%@ is not the RewindBox menu", name);
      } else {
        NSString* down = [NSString stringWithFormat:@"b%@+", MLXTestPad()[name]];
        XCTAssertEqualObjects([self events], @[ down ], @"%@ %@ at (%.1f, %.1f)", portrait ? @"portrait" : @"landscape", name, p.x, p.y);
      }
      XCTAssertEqual([self sticks].count, 0u, @"%@ at (%.1f, %.1f) moved a stick", name, p.x, p.y);
      [self end:touch on:overlay];
      if (MLXTestPad()[name] != nil)
        XCTAssertEqualObjects([self events].lastObject, ([NSString stringWithFormat:@"b%@-", MLXTestPad()[name]]));
    }
  }
}

- (void)testDrawnShapesPressTheirOwnButtonInPortrait { [self checkShapesPortrait:YES]; }
- (void)testDrawnShapesPressTheirOwnButtonInLandscape { [self checkShapesPortrait:NO]; }


- (UIImageView*)knobOf:(MeloNXSkinOverlay*)overlay item:(NSDictionary*)item scale:(CGFloat)scale origin:(CGPoint)origin {
  const CGFloat w = [item[@"thumbstick"][@"width"] doubleValue] * scale;
  const CGRect f = [self rect:item[@"frame"]];
  const CGRect frame = CGRectMake(origin.x + f.origin.x * scale, origin.y + f.origin.y * scale, f.size.width * scale, f.size.height * scale);
  for (UIView* view in overlay.subviews) {
    if ([view isKindOfClass:UIImageView.class] && !view.hidden && fabs(view.frame.size.width - w) < 0.01 &&
        CGRectContainsPoint(frame, CGPointMake(CGRectGetMidX(view.frame), CGRectGetMidY(view.frame))))
      return (UIImageView*)view;
  }
  return nil;
}

/// Centre neutral, linear axes (no dead zone in the overlay), diagonals, saturation at
/// the rim and beyond, positive Y down, the other stick still, release to neutral and
/// the cap moved by the same vector, inside its socket.
- (void)checkVectorsPortrait:(BOOL)portrait {
  MeloNXSkinOverlay* overlay = [self overlayPortrait:portrait];
  for (NSString* side in @[ @"left", @"right" ]) {
    NSDictionary* stick = [self itemNamed:[side stringByAppendingString:@"ThumbstickUp"] portrait:portrait];
    const CGRect f = [self rect:stick[@"frame"]];
    const CGPoint c = CGPointMake(CGRectGetMidX(f), CGRectGetMidY(f));
    const CGFloat radius = f.size.width / 2, travel = (f.size.width - [stick[@"thumbstick"][@"width"] doubleValue]) / 2;
    XCTAssertGreaterThan(travel, 8.0, @"%@: the cap has travel", side);
    UIImageView* knob = [self knobOf:overlay item:stick scale:1 origin:CGPointZero];
    XCTAssertNotNil(knob);
    XCTAssertEqualWithAccuracy(CGRectGetMidX(knob.frame), c.x, 0.01, @"cap at rest on the touch centre");
    XCTAssertEqualWithAccuracy(CGRectGetMidY(knob.frame), c.y, 0.01);
    const BOOL left = [side isEqualToString:@"left"];
    [[self sticks] removeAllObjects];
    [[self events] removeAllObjects];
    MLXFakeTouch* touch = [self touchAt:c];
    [self begin:touch on:overlay];
    XCTAssertEqual([self sticks].count, 0u, @"%@: the centre is neutral (no change sent)", side);
    NSArray<NSNumber*>* v = nil;
    double cases[][4] = {{0.05, 0, 0.05, 0}, {0.5, 0, 0.5, 0}, {1, 0, 1, 0}, {0, -1, 0, -1}, {0, 1, 0, 1}, {-1, 0, -1, 0},
                         {0.7071, -0.7071, 0.7071, -0.7071}, {3, 0, 1, 0}, {-2, 2, -0.7071, 0.7071}};
    for (auto& k : cases) {
      [self move:touch to:CGPointMake(c.x + k[0] * radius, c.y + k[1] * radius) on:overlay];
      v = [self sticks].lastObject;
      XCTAssertEqualWithAccuracy(v[left ? 0 : 2].floatValue, k[2], 0.002, @"%@ x at (%.2f, %.2f)", side, k[0], k[1]);
      XCTAssertEqualWithAccuracy(v[left ? 1 : 3].floatValue, k[3], 0.002, @"%@ y at (%.2f, %.2f)", side, k[0], k[1]);
      XCTAssertEqualWithAccuracy(v[left ? 2 : 0].floatValue, 0, 0.001, @"the other stick stays neutral");
      XCTAssertEqualWithAccuracy(v[left ? 3 : 1].floatValue, 0, 0.001);
      XCTAssertEqualWithAccuracy(CGRectGetMidX(knob.frame) - c.x, k[2] * travel, 0.05, @"%@ cap x", side);
      XCTAssertEqualWithAccuracy(CGRectGetMidY(knob.frame) - c.y, k[3] * travel, 0.05, @"%@ cap y", side);
      XCTAssertTrue(CGRectContainsRect(CGRectInset(f, -0.01, -0.01), knob.frame), @"%@ cap inside its socket", side);
    }
    XCTAssertEqualObjects([self events], @[], @"moving a stick presses no button, never L3 or R3");
    [self end:touch on:overlay];
    XCTAssertEqualObjects([self sticks].lastObject, (@[ @0, @0, @0, @0 ]), @"neutral after release");
    XCTAssertEqualWithAccuracy(CGRectGetMidX(knob.frame), c.x, 0.01, @"cap back to centre");
    XCTAssertEqualWithAccuracy(CGRectGetMidY(knob.frame), c.y, 0.01);
  }
}

- (void)testStickVectorsAndCapInPortrait { [self checkVectorsPortrait:YES]; }
- (void)testStickVectorsAndCapInLandscape { [self checkVectorsPortrait:NO]; }

/// The real phone sizes (the landscape mapping letterboxed): the game screen, the
/// cap and the stick centre follow the same transform as the drawing.
- (void)testLandscapeOnPhoneSizedViews {
  NSDictionary* layout = [self layoutForPortrait:NO];
  const CGSize m = CGSizeMake([layout[@"mappingSize"][@"width"] doubleValue], [layout[@"mappingSize"][@"height"] doubleValue]);
  for (NSValue* sizeValue in @[ [NSValue valueWithCGSize:CGSizeMake(852, 393)], [NSValue valueWithCGSize:CGSizeMake(812, 375)],
                                [NSValue valueWithCGSize:CGSizeMake(932, 430)] ]) {
    const CGSize size = sizeValue.CGSizeValue;
    MeloNXSkinOverlay* overlay = [self overlayPortrait:NO];
    overlay.frame = CGRectMake(0, 0, size.width, size.height);
    [overlay setNeedsLayout];
    [overlay layoutIfNeeded];
    const CGFloat scale = MIN(size.width / m.width, size.height / m.height);
    const CGPoint origin = CGPointMake((size.width - m.width * scale) / 2, (size.height - m.height * scale) / 2);
    const CGRect screen = [self rect:layout[@"screens"][0][@"outputFrame"]];
    XCTAssertEqualWithAccuracy(overlay.screenFrame.origin.x, origin.x + screen.origin.x * scale, 0.01);
    XCTAssertEqualWithAccuracy(overlay.screenFrame.origin.y, origin.y + screen.origin.y * scale, 0.01);
    XCTAssertEqualWithAccuracy(overlay.screenFrame.size.width, screen.size.width * scale, 0.01);
    NSDictionary* stick = [self itemNamed:@"leftThumbstickUp" portrait:NO];
    const CGRect f = [self rect:stick[@"frame"]];
    const CGPoint c = CGPointMake(origin.x + CGRectGetMidX(f) * scale, origin.y + CGRectGetMidY(f) * scale);
    UIImageView* knob = [self knobOf:overlay item:stick scale:scale origin:origin];
    XCTAssertNotNil(knob);
    XCTAssertEqualWithAccuracy(CGRectGetMidX(knob.frame), c.x, 0.01);
    XCTAssertEqualWithAccuracy(CGRectGetMidY(knob.frame), c.y, 0.01);
    [[self sticks] removeAllObjects];
    MLXFakeTouch* touch = [self touchAt:c];
    [self begin:touch on:overlay];
    // The scaled centre is neutral: nothing sent, or (scaled frames are not exact in
    // floating point) a vector of a few millionths at most.
    for (NSNumber* axis in [self sticks].lastObject ?: @[]) {
      XCTAssertEqualWithAccuracy(axis.floatValue, 0, 0.002, @"the scaled centre is neutral, %@", NSStringFromCGSize(size));
    }
    [self move:touch to:CGPointMake(c.x, c.y + f.size.height / 2 * scale) on:overlay];
    XCTAssertEqualWithAccuracy([self sticks].lastObject[1].floatValue, 1, 0.002, @"down at the rim, %@", NSStringFromCGSize(size));
    [self end:touch on:overlay];
    XCTAssertEqualObjects([self sticks].lastObject, (@[ @0, @0, @0, @0 ]));
    // Every drawn button still answers at its scaled centre.
    for (NSString* name in MLXTestPad()) {
      NSDictionary* item = [self itemNamed:name portrait:NO];
      const CGPoint p = [[self shapePoints:item].firstObject CGPointValue];
      [[self events] removeAllObjects];
      MLXFakeTouch* t = [self touchAt:CGPointMake(origin.x + p.x * scale, origin.y + p.y * scale)];
      [self begin:t on:overlay];
      XCTAssertEqualObjects([self events], (@[ [NSString stringWithFormat:@"b%@+", MLXTestPad()[name]] ]), @"%@ on %@", name,
                            NSStringFromCGSize(size));
      [self end:t on:overlay];
    }
  }
}

#pragma mark The drawing: a press changes the control only, inside its outline

- (UIImage*)render:(MeloNXSkinOverlay*)overlay {
  UIGraphicsImageRendererFormat* format = [UIGraphicsImageRendererFormat preferredFormat];
  format.scale = 3;
  format.opaque = YES;
  UIGraphicsImageRenderer* renderer = [[UIGraphicsImageRenderer alloc] initWithSize:overlay.bounds.size format:format];
  return [renderer imageWithActions:^(UIGraphicsImageRendererContext* context) {
    [UIColor.blackColor setFill];
    UIRectFill(overlay.bounds);
    [overlay.layer renderInContext:context.CGContext];
  }];
}

- (NSData*)rgba:(UIImage*)image {
  CGImageRef cg = image.CGImage;
  const size_t w = CGImageGetWidth(cg), h = CGImageGetHeight(cg);
  NSMutableData* data = [NSMutableData dataWithLength:w * h * 4];
  CGColorSpaceRef space = CGColorSpaceCreateDeviceRGB();
  CGContextRef context = CGBitmapContextCreate(data.mutableBytes, w, h, 8, w * 4, space, (CGBitmapInfo)kCGImageAlphaPremultipliedLast);
  CGContextDrawImage(context, CGRectMake(0, 0, w, h), cg);
  CGContextRelease(context);
  CGColorSpaceRelease(space);
  return data;
}

- (void)checkPressedDrawingPortrait:(BOOL)portrait {
  MeloNXSkinOverlay* overlay = [self overlayPortrait:portrait];
  NSData* rest = [self rgba:[self render:overlay]];
  const long W = lround(overlay.bounds.size.width * 3);
  for (NSDictionary* item in [self layoutForPortrait:portrait][@"items"]) {
    if (![item[@"inputs"] isKindOfClass:NSArray.class] || [[item[@"inputs"] firstObject] isEqualToString:@"menu"]) continue;
    const CGRect f = [self rect:item[@"frame"]];
    MLXFakeTouch* t = [self touchAt:[[self shapePoints:item].firstObject CGPointValue]];
    [self begin:t on:overlay];
    NSData* pressed = [self rgba:[self render:overlay]];
    [self end:t on:overlay];
    NSData* released = [self rgba:[self render:overlay]];
    XCTAssertEqualObjects(released, rest, @"%@: released is the rest drawing again", item[@"inputs"]);
    CGSize asize;
    NSData* alpha = [self alphaOf:item size:&asize];
    const uint8_t* A = (const uint8_t*)alpha.bytes;
    const uint8_t* R = (const uint8_t*)rest.bytes;
    const uint8_t* P = (const uint8_t*)pressed.bytes;
    // Outside the sprite's outline (alpha 0) nothing changes; inside it darkens visibly.
    double outsideChange = 0, insideRest = 0, insidePressed = 0;
    long outside = 0, inside = 0;
    const long x0 = lround(f.origin.x * 3) - 6, y0 = lround(f.origin.y * 3) - 6;
    const long x1 = lround(CGRectGetMaxX(f) * 3) + 6, y1 = lround(CGRectGetMaxY(f) * 3) + 6;
    const long H = (long)(pressed.length / 4 / W);
    for (long y = MAX(0, y0); y < MIN(H, y1); y++) {
      for (long x = MAX(0, x0); x < MIN(W, x1); x++) {
        const double mx = (x + 0.5) / 3, my = (y + 0.5) / 3;
        long u = (long)floor((mx - f.origin.x) / f.size.width * asize.width), v = (long)floor((my - f.origin.y) / f.size.height * asize.height);
        int a = 0;  // largest alpha around the point (UIKit resamples the sprite)
        for (long dv = -2; dv <= 2; dv++)
          for (long du = -2; du <= 2; du++) {
            const long uu = u + du, vv = v + dv;
            if (uu >= 0 && vv >= 0 && uu < asize.width && vv < asize.height) a = MAX(a, (int)A[vv * (long)asize.width + uu]);
          }
        const BOOL inFrame = u >= 0 && v >= 0 && u < asize.width && v < asize.height;
        const int centre = inFrame ? A[v * (long)asize.width + u] : 0;
        const long i = (y * W + x) * 4;
        const double dr = fabs((double)P[i] - R[i]) + fabs((double)P[i + 1] - R[i + 1]) + fabs((double)P[i + 2] - R[i + 2]);
        if (a == 0) {
          outsideChange = MAX(outsideChange, dr);
          outside++;
        } else if (centre >= 250) {
          insideRest += R[i] + R[i + 1] + R[i + 2];
          insidePressed += P[i] + P[i + 1] + P[i + 2];
          inside++;
        }
      }
    }
    XCTAssertGreaterThan(outside, 0);
    XCTAssertGreaterThan(inside, 0);
    XCTAssertLessThanOrEqual(outsideChange, 6.0, @"%@: the press changed pixels outside the control", item[@"inputs"]);
    if ([@[ @"home", @"capture" ] containsObject:[item[@"inputs"] firstObject]]) {
      // No input in the embedded Core: never drawn as pressed (the session says so).
      XCTAssertEqualWithAccuracy(insidePressed, insideRest, insideRest * 0.002, @"%@: an inert control looks pressed",
                                 item[@"inputs"]);
    } else {
      XCTAssertLessThan(insidePressed, insideRest * 0.9, @"%@: a press is clearly visible", item[@"inputs"]);
    }
  }
}

/// Evidence: the real overlay's drawing (UIKit render of MeloNXSkinOverlay, 3x) at rest,
/// with every button held at once, with both sticks pushed, and released again, in both
/// orientations; written to MELONX_RENDER_DIR (uploaded by the workflow) and attached.
- (void)testRenderEvidenceOfTheRealOverlay {
  NSString* directory = NSProcessInfo.processInfo.environment[@"MELONX_RENDER_DIR"];
  for (NSNumber* portraitValue in @[ @YES, @NO ]) {
    const BOOL portrait = portraitValue.boolValue;
    NSString* tag = portrait ? @"portrait" : @"landscape";
    MeloNXSkinOverlay* overlay = [self overlayPortrait:portrait];
    NSMutableDictionary<NSString*, UIImage*>* shots = [NSMutableDictionary dictionary];
    shots[@"rest"] = [self render:overlay];
    NSMutableArray<MLXFakeTouch*>* fingers = [NSMutableArray array];
    for (NSDictionary* item in [self layoutForPortrait:portrait][@"items"]) {
      if (![item[@"inputs"] isKindOfClass:NSArray.class] || [[item[@"inputs"] firstObject] isEqualToString:@"menu"]) continue;
      MLXFakeTouch* t = [self touchAt:[[self shapePoints:item].firstObject CGPointValue]];
      [self begin:t on:overlay];
      [fingers addObject:t];
    }
    shots[@"buttons-pressed"] = [self render:overlay];
    for (MLXFakeTouch* t in fingers) [self end:t on:overlay];
    NSMutableArray<MLXFakeTouch*>* sticks = [NSMutableArray array];
    for (NSArray* k in @[ @[ @"leftThumbstickUp", @0.7071, @0.7071 ], @[ @"rightThumbstickUp", @-1, @0 ] ]) {
      NSDictionary* stick = [self itemNamed:k[0] portrait:portrait];
      const CGRect f = [self rect:stick[@"frame"]];
      MLXFakeTouch* t = [self touchAt:CGPointMake(CGRectGetMidX(f), CGRectGetMidY(f))];
      [self begin:t on:overlay];
      [self move:t to:CGPointMake(CGRectGetMidX(f) + [k[1] doubleValue] * f.size.width / 2,
                                  CGRectGetMidY(f) + [k[2] doubleValue] * f.size.height / 2) on:overlay];
      [sticks addObject:t];
    }
    shots[@"sticks-pushed"] = [self render:overlay];
    for (MLXFakeTouch* t in sticks) [self end:t on:overlay];
    shots[@"released"] = [self render:overlay];
    XCTAssertEqualObjects([self rgba:shots[@"released"]], [self rgba:shots[@"rest"]], @"%@: released is the rest drawing", tag);
    for (NSString* state in shots) {
      NSData* png = UIImagePNGRepresentation(shots[state]);
      XCTAttachment* attachment = [XCTAttachment attachmentWithUniformTypeIdentifier:@"public.png"
                                                                                name:[NSString stringWithFormat:@"%@-%@.png", tag, state]
                                                                             payload:png
                                                                            userInfo:nil];
      attachment.lifetime = XCTAttachmentLifetimeKeepAlways;
      [self addAttachment:attachment];
      if (directory.length > 0) {
        [NSFileManager.defaultManager createDirectoryAtPath:directory withIntermediateDirectories:YES attributes:nil error:nil];
        [png writeToFile:[directory stringByAppendingPathComponent:
                                        [NSString stringWithFormat:@"switch-pocket-%@-%@.png", tag, state]]
              atomically:YES];
      }
    }
  }
}

- (void)testPressedDrawingStaysInsideTheOutlineInPortrait { [self checkPressedDrawingPortrait:YES]; }
- (void)testPressedDrawingStaysInsideTheOutlineInLandscape { [self checkPressedDrawingPortrait:NO]; }

#pragma mark The game's place: the opening the skin's body draws (test/skin_frame/SkinFrameCheck.h)

/// The part of each band of the test pattern that must show: a rounded corner hides a
/// few points at each end. Upright, the body's HOME / Capture tab reaches 16 to 18 points
/// into the top of the opening over its middle (the board's drawing): the top band shows
/// on both sides of it only, and the opening's sides lean a little.
- (const double*)frameMinimum:(NSString*)skin portrait:(BOOL)portrait {
  static const double upright[4] = {0.35, 0.85, 0.88, 0.82};
  static const double sideways[4] = {0.9, 0.9, 0.9, 0.9};
  return portrait ? upright : sideways;
}

- (NSDictionary*)infoOf:(NSString*)skin {
  return [NSJSONSerialization JSONObjectWithData:[NSData dataWithContentsOfFile:
      [[[[self documents] stringByAppendingPathComponent:@"Libretro/Skins"] stringByAppendingPathComponent:skin]
          stringByAppendingPathComponent:@"info.json"]] options:0 error:nil];
}

/// `skin` is the one `_info` describes (the class's own, or the one a test just chose).
- (void)checkFrameOf:(MeloNXSkinOverlay*)overlay skin:(NSString*)skin portrait:(BOOL)portrait tag:(NSString*)tag evidence:(BOOL)evidence {
  NSString* directory = [[[self documents] stringByAppendingPathComponent:@"Libretro/Skins"] stringByAppendingPathComponent:skin];
  NSString* renders = NSProcessInfo.processInfo.environment[@"MELONX_RENDER_DIR"];
  NSString* file = evidence && renders.length > 0
      ? [renders stringByAppendingPathComponent:[NSString stringWithFormat:@"%@-%@-test-pattern.png", skin, tag]] : nil;
  SkinFrameCheck(self, overlay, overlay.screenFrame, overlay.screenCutoutActive, [self layoutForPortrait:portrait], directory,
                 [NSString stringWithFormat:@"%@ %@", skin, tag], [self frameMinimum:skin portrait:portrait], file);
}

- (void)checkGameScreenPortrait:(BOOL)portrait {
  NSString* name = portrait ? @"portrait" : @"landscape";
  // The mapping size, then real phone sizes (the skin fitted with one scale).
  for (NSValue* value in @[ [NSValue valueWithCGSize:CGSizeZero], [NSValue valueWithCGSize:CGSizeMake(393, 852)],
                           [NSValue valueWithCGSize:CGSizeMake(375, 812)], [NSValue valueWithCGSize:CGSizeMake(430, 932)] ]) {
    CGSize size = value.CGSizeValue;
    if (!portrait) size = CGSizeMake(size.height, size.width);
    MeloNXSkinOverlay* overlay = [self overlayPortrait:portrait];
    if (size.width >= 1) {
      overlay.frame = CGRectMake(0, 0, size.width, size.height);
      [overlay setNeedsLayout];
      [overlay layoutIfNeeded];
    }
    [self checkFrameOf:overlay skin:[self skinId] portrait:portrait
                   tag:size.width >= 1 ? [NSString stringWithFormat:@"%@-%.0fx%.0f", name, size.width, size.height] : name
              evidence:size.width < 1];
  }
}

- (void)testTheGameFillsTheDrawnOpeningInPortrait { [self checkGameScreenPortrait:YES]; }
- (void)testTheGameFillsTheDrawnOpeningInLandscape { [self checkGameScreenPortrait:NO]; }

- (void)pressOn:(MeloNXSkinOverlay*)overlay portrait:(BOOL)portrait what:(NSString*)what {
  [_events removeAllObjects];
  MLXFakeTouch* finger = [self touchAt:[self centerOf:[self itemNamed:@"a" portrait:portrait] fx:0.5 fy:0.5]];
  [self begin:finger on:overlay];
  [self end:finger on:overlay];
  XCTAssertEqualObjects(_events, (@[ @"b0+", @"b0-" ]), @"the controls answer %@", what);
}

/// One overlay through what a session does to it: a turn, the session menu over it (inputs
/// released, touches off then on again, hidden then shown), a turn back. The game's place
/// is right each time and the controls answer again.
- (void)testTheGameScreenAndControlsAfterRotationAndMenu {
  MeloNXSkinOverlay* overlay = [self overlayPortrait:YES];
  [self checkFrameOf:overlay skin:[self skinId] portrait:YES tag:@"portrait" evidence:NO];
  [self layout:overlay portrait:NO];
  [self checkFrameOf:overlay skin:[self skinId] portrait:NO tag:@"landscape after a turn" evidence:NO];
  [self pressOn:overlay portrait:NO what:@"after a turn"];
  [overlay releaseAllInputs];
  overlay.userInteractionEnabled = NO;
  overlay.hidden = YES;
  overlay.hidden = NO;
  overlay.userInteractionEnabled = YES;
  [overlay setNeedsLayout];
  [overlay layoutIfNeeded];
  [self checkFrameOf:overlay skin:[self skinId] portrait:NO tag:@"landscape after the menu" evidence:NO];
  [self pressOn:overlay portrait:NO what:@"after the menu closed"];
  [self layout:overlay portrait:YES];
  [self checkFrameOf:overlay skin:[self skinId] portrait:YES tag:@"portrait after turning back" evidence:NO];
  [self pressOn:overlay portrait:YES what:@"after turning back"];
}

/// The skin turned off, then chosen again, then the session launched again (a new overlay
/// reads the files): no overlay without a skin, the same game place with it.
- (void)testTheGameScreenFollowsASkinChangeAndARelaunch {
  [self writeSelection:@{@"console" : @{@"skin.portrait" : @"default", @"skin.landscape" : @"default"}}];
  XCTAssertFalse([[MeloNXSkinOverlay alloc] initWithGameKey:@"game.iso"].hasSkin, @"skin off: no overlay, the game keeps the whole view");
  for (int launch = 0; launch < 2; launch++) {
    [self writeSelection:@{@"console" : @{@"skin.portrait" : [self skinId], @"skin.landscape" : [self skinId]}}];
    for (NSNumber* portrait in @[ @YES, @NO ]) {
      MeloNXSkinOverlay* overlay = [self overlayPortrait:portrait.boolValue];
      [self checkFrameOf:overlay skin:[self skinId] portrait:portrait.boolValue
                     tag:[NSString stringWithFormat:@"%@ after choosing the skin again", portrait.boolValue ? @"portrait" : @"landscape"] evidence:NO];
      [self pressOn:overlay portrait:portrait.boolValue what:@"after choosing the skin again"];
    }
  }
}

@end
