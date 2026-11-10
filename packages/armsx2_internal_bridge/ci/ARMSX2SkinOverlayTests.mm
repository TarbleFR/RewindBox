#import <XCTest/XCTest.h>
#import "ARMSX2SkinOverlay.h"
#import "SkinFrameCheck.h"
#import "SkinHarnessWait.h"
#import "ARMSX2Orientation.h"

// The production ARMSX2SkinOverlay on the REAL shipped PS2 archives (unpacked by
// test_skin_overlay_ui.rb into ARMSX2_SKIN_FIXTURE), driven by touches in the
// iOS Simulator: press and release of every command, the D-pad, both sticks, L3
// and R3, Menu, several fingers, rotation, cancel and release. Every test runs on
// PS2 Pocket (ARMSX2SkinOverlayTests) and again on PS2 Pocket — Original
// (ARMSX2SkinOverlayOriginalTests), which adds its drawn-shape touch, exact stick
// vectors, phone-size letterbox and the pressed drawing kept inside each outline.
// The pad is a recorder; no Core and no game run here. A simulator is not an iPhone.

@interface FakeTouch : UITouch
@property(nonatomic) CGPoint point;
@end
@implementation FakeTouch
- (CGPoint)locationInView:(UIView*)view { return self.point; }
@end

@interface ARMSX2SkinOverlayTests : XCTestCase
- (NSString*)skinId;
- (NSMutableArray<NSString*>*)events;               // "b4+" / "b4-"
- (NSMutableArray<NSArray<NSNumber*>*>*)sticks;     // each change sent: lx ly rx ry
- (NSInteger)menuCount;
- (NSDictionary*)layoutForPortrait:(BOOL)portrait;
- (ARMSX2SkinOverlay*)overlayPortrait:(BOOL)portrait;
- (NSDictionary*)itemNamed:(NSString*)name portrait:(BOOL)portrait;
- (CGPoint)centerOf:(NSDictionary*)item fx:(CGFloat)fx fy:(CGFloat)fy;
- (FakeTouch*)touchAt:(CGPoint)point;
- (void)begin:(FakeTouch*)touch on:(ARMSX2SkinOverlay*)overlay;
- (void)move:(FakeTouch*)touch to:(CGPoint)point on:(ARMSX2SkinOverlay*)overlay;
- (void)end:(FakeTouch*)touch on:(ARMSX2SkinOverlay*)overlay;
@end

@implementation ARMSX2SkinOverlayTests {
  NSMutableArray<NSString*>* _events;      // "b4+" / "b4-"
  NSMutableArray<NSArray<NSNumber*>*>* _sticks;
  NSInteger _menuCount;
  NSDictionary* _info;
}

/// The installed skin folder under test (the shipped archive's id).
- (NSString*)skinId { return @"ps2-pocket"; }
- (NSMutableArray<NSString*>*)events { return _events; }
- (NSMutableArray<NSArray<NSNumber*>*>*)sticks { return _sticks; }
- (NSInteger)menuCount { return _menuCount; }

- (NSString*)documents {
  return NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES).firstObject;
}

- (void)writeSelection:(NSDictionary*)document {
  NSString* directory = [[self documents] stringByAppendingPathComponent:@"Libretro/Config/Frontend"];
  [NSFileManager.defaultManager createDirectoryAtPath:directory withIntermediateDirectories:YES attributes:nil error:nil];
  NSData* data = [NSJSONSerialization dataWithJSONObject:document options:0 error:nil];
  [data writeToFile:[directory stringByAppendingPathComponent:@"ps2.json"] atomically:YES];
}

- (void)setUp {
  NSString* fixture = NSProcessInfo.processInfo.environment[@"ARMSX2_SKIN_FIXTURE"];
  XCTAssertNotNil(fixture, @"the runner passes the unpacked skin through ARMSX2_SKIN_FIXTURE");
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
  [self writeSelection:@{@"console" : @{@"skin.portrait" : [self skinId], @"skin.landscape" : [self skinId]}}];
}

- (NSDictionary*)layoutForPortrait:(BOOL)portrait {
  const CGSize native = UIScreen.mainScreen.nativeBounds.size;
  const CGFloat shortSide = MIN(native.width, native.height);
  const BOOL tall = MAX(native.width, native.height) / shortSide > 2.0;
  // ARMSX2SkinLayoutFor: edge-to-edge first on a tall iPhone, standard first otherwise,
  // then the other one (the Original ships edge-to-edge only).
  NSDictionary* iphone = _info[@"representations"][@"iphone"];
  NSDictionary* display = iphone[tall ? @"edgeToEdge" : @"standard"] ?: iphone[tall ? @"standard" : @"edgeToEdge"];
  return display[portrait ? @"portrait" : @"landscape"];
}

- (ARMSX2SkinOverlay*)overlayPortrait:(BOOL)portrait {
  ARMSX2SkinOverlay* overlay = [[ARMSX2SkinOverlay alloc] initWithGameKey:@"game.iso"];
  XCTAssertTrue(overlay.hasSkin);
  // The recorders are captured directly (the overlay is local to the test, no cycle).
  NSMutableArray<NSString*>* events = _events;
  NSMutableArray<NSArray<NSNumber*>*>* sticks = _sticks;
  __weak ARMSX2SkinOverlayTests* weakSelf = self;
  overlay.buttonChanged = ^(uint32_t button, BOOL pressed) {
    [events addObject:[NSString stringWithFormat:@"b%u%@", button, pressed ? @"+" : @"-"]];
  };
  overlay.sticksChanged = ^(float lx, float ly, float rx, float ry) {
    [sticks addObject:@[ @(lx), @(ly), @(rx), @(ry) ]];
  };
  overlay.menuHandler = ^{
    ARMSX2SkinOverlayTests* strongSelf = weakSelf;
    if (strongSelf != nil) strongSelf->_menuCount++;
  };
  [self layout:overlay portrait:portrait];
  return overlay;
}

- (void)layout:(ARMSX2SkinOverlay*)overlay portrait:(BOOL)portrait {
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

- (FakeTouch*)touchAt:(CGPoint)point {
  FakeTouch* touch = [FakeTouch new];
  touch.point = point;
  return touch;
}

- (void)begin:(FakeTouch*)touch on:(ARMSX2SkinOverlay*)overlay { [overlay touchesBegan:[NSSet setWithObject:touch] withEvent:nil]; }
- (void)move:(FakeTouch*)touch to:(CGPoint)point on:(ARMSX2SkinOverlay*)overlay {
  touch.point = point;
  [overlay touchesMoved:[NSSet setWithObject:touch] withEvent:nil];
}
- (void)end:(FakeTouch*)touch on:(ARMSX2SkinOverlay*)overlay { [overlay touchesEnded:[NSSet setWithObject:touch] withEvent:nil]; }

- (void)testChosenOrientationsDecideTheMask {
  ARMSX2SkinOverlay* both = [[ARMSX2SkinOverlay alloc] initWithGameKey:@"game.iso"];
  XCTAssertTrue(both.hasSkin);
  XCTAssertEqual(both.supportedOrientationMask, UIInterfaceOrientationMaskAllButUpsideDown);
  [self writeSelection:@{@"console" : @{@"skin.portrait" : [self skinId]}}];
  XCTAssertEqual([[ARMSX2SkinOverlay alloc] initWithGameKey:nil].supportedOrientationMask, UIInterfaceOrientationMaskPortrait,
                 @"portrait only chosen, although the file also has a landscape layout");
  [self writeSelection:@{@"console" : @{@"skin.landscape" : [self skinId]}}];
  XCTAssertEqual([[ARMSX2SkinOverlay alloc] initWithGameKey:nil].supportedOrientationMask, UIInterfaceOrientationMaskLandscape,
                 @"landscape only chosen, although the file also has a portrait layout");
  [self writeSelection:@{@"console" : @{@"skin.portrait" : [self skinId], @"skin.landscape" : [self skinId]},
                         @"games" : @{@"game.iso" : @{@"skin.landscape" : @"default"}}}];
  XCTAssertEqual([[ARMSX2SkinOverlay alloc] initWithGameKey:@"game.iso"].supportedOrientationMask, UIInterfaceOrientationMaskPortrait,
                 @"the game's explicit default overrides the console's landscape skin");
  XCTAssertEqual([[ARMSX2SkinOverlay alloc] initWithGameKey:@"other.iso"].supportedOrientationMask,
                 UIInterfaceOrientationMaskAllButUpsideDown, @"another game inherits the console");
  [self writeSelection:@{@"console" : @{@"skin.portrait" : @"default"}}];
  XCTAssertFalse([[ARMSX2SkinOverlay alloc] initWithGameKey:nil].hasSkin, @"default: no overlay at all");
}

- (void)checkEveryButtonPortrait:(BOOL)portrait {
  ARMSX2SkinOverlay* overlay = [self overlayPortrait:portrait];
  XCTAssertTrue(overlay.layoutActive);
  XCTAssertTrue(CGRectGetWidth(overlay.screenFrame) > 0);
  NSDictionary<NSString*, NSNumber*>* pad = @{@"up" : @0, @"down" : @1, @"left" : @2, @"right" : @3, @"cross" : @4,
                                               @"circle" : @5, @"square" : @6, @"triangle" : @7, @"l1" : @8, @"r1" : @9,
                                               @"l2" : @10, @"r2" : @11, @"start" : @12, @"select" : @13, @"l3" : @14,
                                               @"r3" : @15};
  for (NSString* name in pad) {
    if ([@[ @"up", @"down", @"left", @"right" ] containsObject:name]) continue;  // D-pad: tested separately
    NSDictionary* item = [self itemNamed:name portrait:portrait];
    XCTAssertNotNil(item, @"%@ is visible", name);
    [_events removeAllObjects];
    FakeTouch* touch = [self touchAt:[self centerOf:item fx:0.5 fy:0.5]];
    [self begin:touch on:overlay];
    XCTAssertEqualObjects(_events, (@[ [NSString stringWithFormat:@"b%@+", pad[name]] ]), @"%@ press", name);
    [self end:touch on:overlay];
    XCTAssertEqualObjects(_events, (@[ [NSString stringWithFormat:@"b%@+", pad[name]], [NSString stringWithFormat:@"b%@-", pad[name]] ]),
                          @"%@ release", name);
  }
  // D-pad: the four directions and a diagonal, each released.
  NSDictionary* dpad = [self itemNamed:@"up" portrait:portrait];
  struct { CGFloat x, y; NSArray* expect; } cases[] = {{0.5, 0.1, @[ @0 ]}, {0.5, 0.9, @[ @1 ]}, {0.1, 0.5, @[ @2 ]},
                                                        {0.9, 0.5, @[ @3 ]}, {0.9, 0.9, @[ @3, @1 ]}};
  for (auto& c : cases) {
    [_events removeAllObjects];
    FakeTouch* touch = [self touchAt:[self centerOf:dpad fx:c.x fy:c.y]];
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
  FakeTouch* menuTouch = [self touchAt:[self centerOf:menu fx:0.5 fy:0.5]];
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
  ARMSX2SkinOverlay* overlay = [self overlayPortrait:portrait];
  for (NSString* side in @[ @"left", @"right" ]) {
    NSDictionary* item = [self itemNamed:[side stringByAppendingString:@"ThumbstickUp"] portrait:portrait];
    XCTAssertNotNil(item);
    [_sticks removeAllObjects];
    [_events removeAllObjects];
    FakeTouch* touch = [self touchAt:[self centerOf:item fx:0.5 fy:0.5]];
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
  ARMSX2SkinOverlay* overlay = [self overlayPortrait:YES];
  FakeTouch* stick = [self touchAt:[self centerOf:[self itemNamed:@"leftThumbstickUp" portrait:YES] fx:0.5 fy:0.5]];
  FakeTouch* cross = [self touchAt:[self centerOf:[self itemNamed:@"cross" portrait:YES] fx:0.5 fy:0.5]];
  FakeTouch* r1 = [self touchAt:[self centerOf:[self itemNamed:@"r1" portrait:YES] fx:0.5 fy:0.5]];
  [self begin:stick on:overlay];
  [self begin:cross on:overlay];
  [self begin:r1 on:overlay];
  [self move:stick to:[self centerOf:[self itemNamed:@"leftThumbstickUp" portrait:YES] fx:1.0 fy:0.5] on:overlay];
  XCTAssertTrue([_events containsObject:@"b4+"] && [_events containsObject:@"b9+"], @"stick + face button + shoulder together");
  XCTAssertEqualWithAccuracy(_sticks.lastObject[0].floatValue, 1.0, 0.05);
  // A finger that slides off its button onto another one changes control (no stuck button).
  [_events removeAllObjects];
  [self move:cross to:[self centerOf:[self itemNamed:@"circle" portrait:YES] fx:0.5 fy:0.5] on:overlay];
  XCTAssertTrue([_events containsObject:@"b4-"] && [_events containsObject:@"b5+"]);
  // Cancel (a system interruption) releases like a lift.
  [_events removeAllObjects];
  [overlay touchesCancelled:[NSSet setWithObject:cross] withEvent:nil];
  XCTAssertTrue([_events containsObject:@"b5-"]);
  // The session's release (menu opening, stop, background) lets go of everything at once.
  [_events removeAllObjects];
  [overlay releaseAllInputs];
  XCTAssertTrue([_events containsObject:@"b9-"]);
  XCTAssertEqualObjects(_sticks.lastObject, (@[ @0, @0, @0, @0 ]));
  [_events removeAllObjects];
  [overlay releaseAllInputs];
  XCTAssertEqualObjects(_events, @[], @"releasing twice sends nothing more");
}

- (void)testTheSkinsOwnMenuHidesTheFloatingOne {
  // Armsx2InternalBridgePlugin hides its floating hamburger over a skin with a Menu.
  for (NSNumber* portrait in @[ @YES, @NO ]) {
    ARMSX2SkinOverlay* overlay = [self overlayPortrait:portrait.boolValue];
    XCTAssertTrue(overlay.hasMenuControl, @"%@ %@ has its own Menu", [self skinId], portrait.boolValue ? @"portrait" : @"landscape");
  }
}

- (void)testRotationReleasesHeldInputs {
  ARMSX2SkinOverlay* overlay = [self overlayPortrait:YES];
  FakeTouch* cross = [self touchAt:[self centerOf:[self itemNamed:@"cross" portrait:YES] fx:0.5 fy:0.5]];
  [self begin:cross on:overlay];
  XCTAssertTrue([_events containsObject:@"b4+"]);
  [self layout:overlay portrait:NO];  // the surface turned: the other layout takes over
  XCTAssertTrue([_events containsObject:@"b4-"], @"the held button was released by the turn");
  XCTAssertTrue(CGRectGetWidth(overlay.screenFrame) > CGRectGetHeight(overlay.screenFrame) * 1.2);
}

- (void)testApplicationMaskAndRestore {
  ARMSX2OrientationInstall();
  id<UIApplicationDelegate> delegate = UIApplication.sharedApplication.delegate;
  UIWindow* window = [(id)delegate window];
  UIInterfaceOrientationMask (^mask)(void) = ^{
    return [delegate application:UIApplication.sharedApplication supportedInterfaceOrientationsForWindow:window];
  };
  XCTAssertEqual(mask(), UIInterfaceOrientationMaskLandscape, @"the host is landscape only");
  ARMSX2OrientationSetGameMask(UIInterfaceOrientationMaskPortrait);
  XCTAssertEqual(mask(), UIInterfaceOrientationMaskPortrait);
  ARMSX2OrientationSetGameMask(0);
  XCTAssertEqual(mask(), UIInterfaceOrientationMaskLandscape, @"released: the app's own again");
}

#pragma mark The game's place: the opening the skin's body draws (test/skin_frame/SkinFrameCheck.h)

/// The part of each band of the test pattern that must show: a rounded corner hides a
/// few points at each end.
- (const double*)frameMinimum:(NSString*)skin portrait:(BOOL)portrait {
  static const double minimum[4] = {0.9, 0.9, 0.9, 0.9};
  return minimum;
}

- (NSDictionary*)infoOf:(NSString*)skin {
  return [NSJSONSerialization JSONObjectWithData:[NSData dataWithContentsOfFile:
      [[[[self documents] stringByAppendingPathComponent:@"Libretro/Skins"] stringByAppendingPathComponent:skin]
          stringByAppendingPathComponent:@"info.json"]] options:0 error:nil];
}

/// `skin` is the one `_info` describes (the class's own, or the one a test just chose).
- (void)checkFrameOf:(ARMSX2SkinOverlay*)overlay skin:(NSString*)skin portrait:(BOOL)portrait tag:(NSString*)tag evidence:(BOOL)evidence {
  NSString* directory = [[[self documents] stringByAppendingPathComponent:@"Libretro/Skins"] stringByAppendingPathComponent:skin];
  NSString* renders = NSProcessInfo.processInfo.environment[@"ARMSX2_RENDER_DIR"];
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
    ARMSX2SkinOverlay* overlay = [self overlayPortrait:portrait];
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

- (void)pressOn:(ARMSX2SkinOverlay*)overlay portrait:(BOOL)portrait what:(NSString*)what {
  [_events removeAllObjects];
  FakeTouch* finger = [self touchAt:[self centerOf:[self itemNamed:@"cross" portrait:portrait] fx:0.5 fy:0.5]];
  [self begin:finger on:overlay];
  [self end:finger on:overlay];
  XCTAssertEqualObjects(_events, (@[ @"b4+", @"b4-" ]), @"the controls answer %@", what);
}

/// One overlay through what a session does to it: a turn, the session menu over it (inputs
/// released, touches off then on again, hidden then shown), a turn back. The game's place
/// is right each time and the controls answer again.
- (void)testTheGameScreenAndControlsAfterRotationAndMenu {
  ARMSX2SkinOverlay* overlay = [self overlayPortrait:YES];
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

/// Another skin chosen, then the session launched again (a new overlay reads the files):
/// each skin gets its own game place and its controls; "default" leaves no overlay.
- (void)testTheGameScreenFollowsASkinChangeAndARelaunch {
  NSString* other = [[self skinId] isEqualToString:@"ps2-pocket"] ? @"ps2-pocket-original" : @"ps2-pocket";
  NSString* skins = [[self documents] stringByAppendingPathComponent:@"Libretro/Skins"];
  NSError* error = nil;
  [NSFileManager.defaultManager copyItemAtPath:[NSProcessInfo.processInfo.environment[@"ARMSX2_SKIN_FIXTURE"] stringByAppendingPathComponent:other]
                                        toPath:[skins stringByAppendingPathComponent:other] error:&error];
  XCTAssertNil(error);
  NSDictionary* own = _info;
  for (NSString* skin in @[ other, [self skinId], other, [self skinId] ]) {
    [self writeSelection:@{@"console" : @{@"skin.portrait" : skin, @"skin.landscape" : skin}}];
    _info = [self infoOf:skin];
    for (NSNumber* portrait in @[ @YES, @NO ]) {
      ARMSX2SkinOverlay* overlay = [self overlayPortrait:portrait.boolValue];
      [self checkFrameOf:overlay skin:skin portrait:portrait.boolValue
                     tag:[NSString stringWithFormat:@"%@ after a skin change", portrait.boolValue ? @"portrait" : @"landscape"] evidence:NO];
      [self pressOn:overlay portrait:portrait.boolValue what:[NSString stringWithFormat:@"with %@ after a skin change", skin]];
    }
  }
  _info = own;
  [self writeSelection:@{@"console" : @{@"skin.portrait" : @"default", @"skin.landscape" : @"default"}}];
  XCTAssertFalse([[ARMSX2SkinOverlay alloc] initWithGameKey:@"game.iso"].hasSkin, @"skin off: no overlay, the game keeps the whole view");
}

@end

#pragma mark PS2 Pocket — Original

// The same tests on the Original, and what only its board layout has: interlocking
// frames resolved by the drawn shape (ARMSX2SkinHitTest.h on the sprite alpha), the
// L3/R3 labels just under the caps, the exact stick vectors and cap travel.
@interface ARMSX2SkinOverlayOriginalTests : ARMSX2SkinOverlayTests
@end

@implementation ARMSX2SkinOverlayOriginalTests

- (NSString*)skinId { return @"ps2-pocket-original"; }

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

static NSDictionary<NSString*, NSNumber*>* A2TestPad(void) {
  return @{@"cross" : @4, @"circle" : @5, @"square" : @6, @"triangle" : @7, @"l1" : @8, @"r1" : @9, @"l2" : @10,
           @"r2" : @11, @"start" : @12, @"select" : @13, @"l3" : @14, @"r3" : @15};
}

/// Centre and contour of every drawn button press exactly that button (or open the
/// menu once), and its release leaves nothing held: where frames interlock (face
/// buttons, the L3/R3 labels under the sticks) the drawn shape decides.
- (void)checkShapesPortrait:(BOOL)portrait {
  ARMSX2SkinOverlay* overlay = [self overlayPortrait:portrait];
  for (NSDictionary* item in [self layoutForPortrait:portrait][@"items"]) {
    if (![item[@"inputs"] isKindOfClass:NSArray.class]) continue;
    NSString* name = [item[@"inputs"] firstObject];
    NSArray<NSValue*>* points = [self shapePoints:item];
    XCTAssertGreaterThanOrEqual(points.count, 12u, @"%@: contour points", name);
    for (NSValue* value in points) {
      const CGPoint p = value.CGPointValue;
      [[self events] removeAllObjects];
      [[self sticks] removeAllObjects];
      const NSInteger menus = [self menuCount];
      FakeTouch* touch = [self touchAt:p];
      [self begin:touch on:overlay];
      if ([name isEqualToString:@"menu"]) {
        SkinHarnessWait(^BOOL { return [self menuCount] != menus; }, 2);
        XCTAssertEqual([self menuCount], menus + 1, @"Menu once at (%.1f, %.1f)", p.x, p.y);
        XCTAssertEqualObjects([self events], @[]);
      } else {
        NSString* down = [NSString stringWithFormat:@"b%@+", A2TestPad()[name]];
        XCTAssertEqualObjects([self events], @[ down ], @"%@ %@ at (%.1f, %.1f)", portrait ? @"portrait" : @"landscape", name, p.x, p.y);
      }
      XCTAssertEqual([self sticks].count, 0u, @"%@ at (%.1f, %.1f) moved a stick", name, p.x, p.y);
      [self end:touch on:overlay];
      if (![name isEqualToString:@"menu"])
        XCTAssertEqualObjects([self events].lastObject, ([NSString stringWithFormat:@"b%@-", A2TestPad()[name]]));
    }
  }
}

- (void)testDrawnShapesPressTheirOwnButtonInPortrait { [self checkShapesPortrait:YES]; }
- (void)testDrawnShapesPressTheirOwnButtonInLandscape { [self checkShapesPortrait:NO]; }

/// The labels sit just under the caps, inside the stick's square frame: the label's
/// band presses L3/R3 only; the cap and its socket above it move the stick only.
- (void)checkLabelsPortrait:(BOOL)portrait {
  ARMSX2SkinOverlay* overlay = [self overlayPortrait:portrait];
  for (NSArray* pair in @[ @[ @"l3", @"leftThumbstickUp", @14 ], @[ @"r3", @"rightThumbstickUp", @15 ] ]) {
    NSDictionary* label = [self itemNamed:pair[0] portrait:portrait];
    NSDictionary* stick = [self itemNamed:pair[1] portrait:portrait];
    const CGRect l = [self rect:label[@"frame"]], s = [self rect:stick[@"frame"]];
    XCTAssertTrue(CGRectIntersectsRect(l, s), @"%@: the label frame meets the stick frame", pair[0]);
    const CGFloat capBottom = CGRectGetMidY(s) + [stick[@"thumbstick"][@"height"] doubleValue] / 2;
    XCTAssertGreaterThanOrEqual(CGRectGetMinY(l), capBottom - 0.01, @"%@ starts under the cap at rest", pair[0]);
    // In both frames, inside the label: L3/R3, no stick.
    const CGPoint inLabel = CGPointMake(CGRectGetMidX(l), CGRectGetMinY(l) + 2);
    XCTAssertTrue(CGRectContainsPoint(s, inLabel));
    [[self events] removeAllObjects];
    [[self sticks] removeAllObjects];
    FakeTouch* touch = [self touchAt:inLabel];
    [self begin:touch on:overlay];
    XCTAssertEqualObjects([self events], (@[ [NSString stringWithFormat:@"b%@+", pair[2]] ]), @"%@ under the cap", pair[0]);
    XCTAssertEqual([self sticks].count, 0u);
    [self end:touch on:overlay];
    // Just above the label (the cap's lower edge): the stick, never L3/R3.
    [[self events] removeAllObjects];
    FakeTouch* cap = [self touchAt:CGPointMake(CGRectGetMidX(s), capBottom - 2)];
    [self begin:cap on:overlay];
    XCTAssertEqualObjects([self events], @[], @"the cap edge presses no button");
    XCTAssertGreaterThan([self sticks].lastObject[[pair[0] isEqualToString:@"l3"] ? 1 : 3].floatValue, 0.0f, @"pushed down");
    [self end:cap on:overlay];
    XCTAssertEqualObjects([self sticks].lastObject, (@[ @0, @0, @0, @0 ]));
  }
}

- (void)testL3AndR3LabelsUnderTheCapsInPortrait { [self checkLabelsPortrait:YES]; }
- (void)testL3AndR3LabelsUnderTheCapsInLandscape { [self checkLabelsPortrait:NO]; }

- (UIImageView*)knobOf:(ARMSX2SkinOverlay*)overlay item:(NSDictionary*)item scale:(CGFloat)scale origin:(CGPoint)origin {
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
  ARMSX2SkinOverlay* overlay = [self overlayPortrait:portrait];
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
    FakeTouch* touch = [self touchAt:c];
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
    ARMSX2SkinOverlay* overlay = [self overlayPortrait:NO];
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
    FakeTouch* touch = [self touchAt:c];
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
    for (NSString* name in A2TestPad()) {
      NSDictionary* item = [self itemNamed:name portrait:NO];
      const CGPoint p = [[self shapePoints:item].firstObject CGPointValue];
      [[self events] removeAllObjects];
      FakeTouch* t = [self touchAt:CGPointMake(origin.x + p.x * scale, origin.y + p.y * scale)];
      [self begin:t on:overlay];
      XCTAssertEqualObjects([self events], (@[ [NSString stringWithFormat:@"b%@+", A2TestPad()[name]] ]), @"%@ on %@", name,
                            NSStringFromCGSize(size));
      [self end:t on:overlay];
    }
  }
}

#pragma mark The drawing: a press changes the control only, inside its outline

- (UIImage*)render:(ARMSX2SkinOverlay*)overlay {
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
  ARMSX2SkinOverlay* overlay = [self overlayPortrait:portrait];
  NSData* rest = [self rgba:[self render:overlay]];
  const long W = lround(overlay.bounds.size.width * 3);
  for (NSDictionary* item in [self layoutForPortrait:portrait][@"items"]) {
    if (![item[@"inputs"] isKindOfClass:NSArray.class] || [[item[@"inputs"] firstObject] isEqualToString:@"menu"]) continue;
    const CGRect f = [self rect:item[@"frame"]];
    FakeTouch* t = [self touchAt:[[self shapePoints:item].firstObject CGPointValue]];
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
    XCTAssertLessThan(insidePressed, insideRest * 0.9, @"%@: a press is clearly visible", item[@"inputs"]);
  }
}

/// Evidence: the real overlay's drawing (UIKit render of ARMSX2SkinOverlay, 3x) at rest,
/// with every button held at once, with both sticks pushed, and released again, in both
/// orientations; written to ARMSX2_RENDER_DIR (uploaded by the workflow) and attached.
- (void)testRenderEvidenceOfTheRealOverlay {
  NSString* directory = NSProcessInfo.processInfo.environment[@"ARMSX2_RENDER_DIR"];
  for (NSNumber* portraitValue in @[ @YES, @NO ]) {
    const BOOL portrait = portraitValue.boolValue;
    NSString* tag = portrait ? @"portrait" : @"landscape";
    ARMSX2SkinOverlay* overlay = [self overlayPortrait:portrait];
    NSMutableDictionary<NSString*, UIImage*>* shots = [NSMutableDictionary dictionary];
    shots[@"rest"] = [self render:overlay];
    NSMutableArray<FakeTouch*>* fingers = [NSMutableArray array];
    for (NSDictionary* item in [self layoutForPortrait:portrait][@"items"]) {
      if (![item[@"inputs"] isKindOfClass:NSArray.class] || [[item[@"inputs"] firstObject] isEqualToString:@"menu"]) continue;
      FakeTouch* t = [self touchAt:[[self shapePoints:item].firstObject CGPointValue]];
      [self begin:t on:overlay];
      [fingers addObject:t];
    }
    shots[@"buttons-pressed"] = [self render:overlay];
    for (FakeTouch* t in fingers) [self end:t on:overlay];
    NSMutableArray<FakeTouch*>* sticks = [NSMutableArray array];
    for (NSArray* k in @[ @[ @"leftThumbstickUp", @0.7071, @0.7071 ], @[ @"rightThumbstickUp", @-1, @0 ] ]) {
      NSDictionary* stick = [self itemNamed:k[0] portrait:portrait];
      const CGRect f = [self rect:stick[@"frame"]];
      FakeTouch* t = [self touchAt:CGPointMake(CGRectGetMidX(f), CGRectGetMidY(f))];
      [self begin:t on:overlay];
      [self move:t to:CGPointMake(CGRectGetMidX(f) + [k[1] doubleValue] * f.size.width / 2,
                                  CGRectGetMidY(f) + [k[2] doubleValue] * f.size.height / 2) on:overlay];
      [sticks addObject:t];
    }
    shots[@"sticks-pushed"] = [self render:overlay];
    for (FakeTouch* t in sticks) [self end:t on:overlay];
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
                                        [NSString stringWithFormat:@"ps2-pocket-original-%@-%@.png", tag, state]]
              atomically:YES];
      }
    }
  }
}

- (void)testPressedDrawingStaysInsideTheOutlineInPortrait { [self checkPressedDrawingPortrait:YES]; }
- (void)testPressedDrawingStaysInsideTheOutlineInLandscape { [self checkPressedDrawingPortrait:NO]; }

@end
