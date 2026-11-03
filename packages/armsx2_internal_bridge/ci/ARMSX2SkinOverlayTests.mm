#import <XCTest/XCTest.h>
#import "ARMSX2SkinOverlay.h"
#import "ARMSX2Orientation.h"

// The production ARMSX2SkinOverlay on the REAL PS2 Pocket archive (unpacked by
// test_skin_overlay_ui.rb into ARMSX2_SKIN_FIXTURE), driven by touches in the
// iOS Simulator: press and release of every command, the D-pad, both sticks, L3
// and R3, Menu, several fingers, rotation, cancel and release. The pad is a
// recorder; no Core and no game run here. A simulator is not an iPhone.

@interface FakeTouch : UITouch
@property(nonatomic) CGPoint point;
@end
@implementation FakeTouch
- (CGPoint)locationInView:(UIView*)view { return self.point; }
@end

static NSString* const kSkinId = @"ps2-pocket";

@interface ARMSX2SkinOverlayTests : XCTestCase
@end

@implementation ARMSX2SkinOverlayTests {
  NSMutableArray<NSString*>* _events;      // "b4+" / "b4-"
  NSMutableArray<NSArray<NSNumber*>*>* _sticks;
  NSInteger _menuCount;
  NSDictionary* _info;
}

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
  [NSFileManager.defaultManager copyItemAtPath:[fixture stringByAppendingPathComponent:kSkinId]
                                        toPath:[target stringByAppendingPathComponent:kSkinId] error:&error];
  XCTAssertNil(error);
  _info = [NSJSONSerialization JSONObjectWithData:[NSData dataWithContentsOfFile:
      [[target stringByAppendingPathComponent:kSkinId] stringByAppendingPathComponent:@"info.json"]] options:0 error:nil];
  XCTAssertNotNil(_info);
  _events = [NSMutableArray array];
  _sticks = [NSMutableArray array];
  _menuCount = 0;
  [self writeSelection:@{@"console" : @{@"skin.portrait" : kSkinId, @"skin.landscape" : kSkinId}}];
}

- (NSDictionary*)layoutForPortrait:(BOOL)portrait {
  const CGSize native = UIScreen.mainScreen.nativeBounds.size;
  const CGFloat shortSide = MIN(native.width, native.height);
  const BOOL tall = MAX(native.width, native.height) / shortSide > 2.0;
  return _info[@"representations"][@"iphone"][tall ? @"edgeToEdge" : @"standard"][portrait ? @"portrait" : @"landscape"];
}

- (ARMSX2SkinOverlay*)overlayPortrait:(BOOL)portrait {
  ARMSX2SkinOverlay* overlay = [[ARMSX2SkinOverlay alloc] initWithGameKey:@"game.iso"];
  XCTAssertTrue(overlay.hasSkin);
  __weak ARMSX2SkinOverlayTests* weakSelf = self;
  overlay.buttonChanged = ^(uint32_t button, BOOL pressed) {
    [weakSelf->_events addObject:[NSString stringWithFormat:@"b%u%@", button, pressed ? @"+" : @"-"]];
  };
  overlay.sticksChanged = ^(float lx, float ly, float rx, float ry) {
    [weakSelf->_sticks addObject:@[ @(lx), @(ly), @(rx), @(ry) ]];
  };
  overlay.menuHandler = ^{ weakSelf->_menuCount++; };
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
  [self writeSelection:@{@"console" : @{@"skin.portrait" : kSkinId}}];
  XCTAssertEqual([[ARMSX2SkinOverlay alloc] initWithGameKey:nil].supportedOrientationMask, UIInterfaceOrientationMaskPortrait,
                 @"portrait only chosen, although the file also has a landscape layout");
  [self writeSelection:@{@"console" : @{@"skin.landscape" : kSkinId}}];
  XCTAssertEqual([[ARMSX2SkinOverlay alloc] initWithGameKey:nil].supportedOrientationMask, UIInterfaceOrientationMaskLandscape,
                 @"landscape only chosen, although the file also has a portrait layout");
  [self writeSelection:@{@"console" : @{@"skin.portrait" : kSkinId, @"skin.landscape" : kSkinId},
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
  XCTAssertEqualWithAccuracy(CGRectGetWidth(overlay.screenFrame) / CGRectGetHeight(overlay.screenFrame), 4.0 / 3.0, 0.01);
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

@end
