#import <XCTest/XCTest.h>
#import "DOLSkinOverlay.h"
#import "SkinOverlayRecorder.h"
#import "SkinFrameCheck.h"
#import "SkinHarnessWait.h"

// The production DOLSkinOverlay on the REAL GameCube / Wii Pocket Original
// archives (unpacked by test_skin_overlay_ui.rb into DOLPHIN_SKIN_FIXTURE),
// driven by touches in the iOS Simulator. Every command is read back from the
// TCManagerInterface calls (SkinOverlayRecorder stands in for the Core): the
// centre and the contour of every drawn control press that control only, its
// invisible extension too, the sticks follow the finger from the cap's centre
// in both orientations, and a press changes the drawing inside the control's
// outline only. A simulator is not an iPhone; no game runs here.

@interface SkinFakeTouch : UITouch
@property(nonatomic) CGPoint point;
@end
@implementation SkinFakeTouch
- (CGPoint)locationInView:(UIView*)view { return self.point; }
@end

static NSString* const kGC = @"gamecube-pocket-original";
static NSString* const kWii = @"wii-pocket-original";
// The packs whose body bears the RewindBox wordmark (one body for both consoles).
static NSString* const kGCPocket = @"gamecube-pocket";
static NSString* const kWiiPocket = @"wii-pocket";

@interface DolphinSkinOverlayTests : XCTestCase
@end

@implementation DolphinSkinOverlayTests {
  NSString* _skins;
  NSInteger _menuCount;
}

- (NSString*)documents {
  return NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES).firstObject;
}

- (void)setUp {
  NSString* fixture = NSProcessInfo.processInfo.environment[@"DOLPHIN_SKIN_FIXTURE"];
  XCTAssertNotNil(fixture, @"the runner passes the unpacked skins through DOLPHIN_SKIN_FIXTURE");
  NSString* libretro = [[self documents] stringByAppendingPathComponent:@"Libretro"];
  [NSFileManager.defaultManager removeItemAtPath:libretro error:nil];
  _skins = [libretro stringByAppendingPathComponent:@"Skins"];
  [NSFileManager.defaultManager createDirectoryAtPath:_skins withIntermediateDirectories:YES attributes:nil error:nil];
  for (NSString* identifier in @[ kGC, kWii, kGCPocket, kWiiPocket ]) {
    NSError* error = nil;
    [NSFileManager.defaultManager copyItemAtPath:[fixture stringByAppendingPathComponent:identifier]
                                          toPath:[_skins stringByAppendingPathComponent:identifier] error:&error];
    XCTAssertNil(error);
  }
  NSString* frontend = [libretro stringByAppendingPathComponent:@"Config/Frontend"];
  [NSFileManager.defaultManager createDirectoryAtPath:frontend withIntermediateDirectories:YES attributes:nil error:nil];
  for (NSArray* pair in @[ @[ @"gc", kGC ], @[ @"wii", kWii ] ]) {
    NSData* data = [NSJSONSerialization dataWithJSONObject:@{@"console" : @{@"skin.portrait" : pair[1], @"skin.landscape" : pair[1]}}
                                                   options:0 error:nil];
    [data writeToFile:[frontend stringByAppendingPathComponent:[pair[0] stringByAppendingString:@".json"]] atomically:YES];
  }
  _menuCount = 0;
  SkinRecorderReset();
}

#pragma mark Helpers

- (NSDictionary*)layout:(NSString*)skin portrait:(BOOL)portrait {
  NSDictionary* info = [NSJSONSerialization JSONObjectWithData:[NSData dataWithContentsOfFile:
      [[_skins stringByAppendingPathComponent:skin] stringByAppendingPathComponent:@"info.json"]] options:0 error:nil];
  // DOLSkinLayoutFor: edge-to-edge first on a tall iPhone, standard first otherwise, then
  // the other one (the Originals ship edge-to-edge only).
  const CGSize native = UIScreen.mainScreen.nativeBounds.size;
  const BOOL tall = MAX(native.width, native.height) / MIN(native.width, native.height) > 2.0;
  NSDictionary* iphone = info[@"representations"][@"iphone"];
  NSDictionary* display = iphone[tall ? @"edgeToEdge" : @"standard"] ?: iphone[tall ? @"standard" : @"edgeToEdge"];
  return display[portrait ? @"portrait" : @"landscape"];
}

/// The overlay laid out at `size` (the mapping size unless given).
- (DOLSkinOverlay*)overlay:(NSString*)skin portrait:(BOOL)portrait size:(CGSize)size {
  DOLSkinOverlay* overlay = [[DOLSkinOverlay alloc] initWithWii:[skin hasPrefix:@"wii"] gameKey:nil];
  XCTAssertTrue(overlay.hasSkin);
  __weak DolphinSkinOverlayTests* weakSelf = self;
  overlay.menuHandler = ^{
    DolphinSkinOverlayTests* strongSelf = weakSelf;
    if (strongSelf != nil) strongSelf->_menuCount++;
  };
  if (size.width < 1) {
    NSDictionary* mapping = [self layout:skin portrait:portrait][@"mappingSize"];
    size = CGSizeMake([mapping[@"width"] doubleValue], [mapping[@"height"] doubleValue]);
  }
  overlay.frame = CGRectMake(0, 0, size.width, size.height);
  [overlay setNeedsLayout];
  [overlay layoutIfNeeded];
  XCTAssertTrue(overlay.layoutActive);
  return overlay;
}

- (CGRect)rect:(NSDictionary*)frame {
  return CGRectMake([frame[@"x"] doubleValue], [frame[@"y"] doubleValue], [frame[@"width"] doubleValue], [frame[@"height"] doubleValue]);
}

- (CGRect)hitRect:(NSDictionary*)item {
  CGRect f = [self rect:item[@"frame"]];
  NSDictionary* e = item[@"extendedEdges"];
  const CGFloat l = [e[@"left"] doubleValue], t = [e[@"top"] doubleValue], r = [e[@"right"] doubleValue], b = [e[@"bottom"] doubleValue];
  return CGRectMake(f.origin.x - l, f.origin.y - t, f.size.width + l + r, f.size.height + t + b);
}

/// The normal sprite's alpha (as DOLSkinOverlay reads it) at full resolution.
- (NSData*)alphaOf:(NSString*)skin item:(NSDictionary*)item size:(CGSize*)size {
  UIImage* image = [UIImage imageWithContentsOfFile:[[_skins stringByAppendingPathComponent:skin]
      stringByAppendingPathComponent:item[@"asset"][@"normal"]]];
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
/// the last opaque point before the outline (the contour), in mapping points.
- (NSArray<NSValue*>*)shapePoints:(NSString*)skin item:(NSDictionary*)item {
  CGSize size;
  NSData* alpha = [self alphaOf:skin item:item size:&size];
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
  const double inset = 1.5 * w / f.size.width;  // 1.5 pt inside the outline
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

- (SkinFakeTouch*)touch:(CGPoint)point {
  SkinFakeTouch* touch = [SkinFakeTouch new];
  touch.point = point;
  return touch;
}
- (void)begin:(SkinFakeTouch*)t on:(DOLSkinOverlay*)o { [o touchesBegan:[NSSet setWithObject:t] withEvent:nil]; }
- (void)move:(SkinFakeTouch*)t to:(CGPoint)p on:(DOLSkinOverlay*)o {
  t.point = p;
  [o touchesMoved:[NSSet setWithObject:t] withEvent:nil];
}
- (void)end:(SkinFakeTouch*)t on:(DOLSkinOverlay*)o { [o touchesEnded:[NSSet setWithObject:t] withEvent:nil]; }

/// What the pad holds now: "b<id>" buttons and "a<axis>" axes away from 0.
- (NSSet<NSString*>*)held {
  NSMutableSet<NSString*>* held = [NSMutableSet set];
  for (NSNumber* button in SkinRecorderHeldButtons()) [held addObject:[NSString stringWithFormat:@"b%@", button]];
  [SkinRecorderAxes() enumerateKeysAndObjectsUsingBlock:^(NSNumber* axis, NSNumber* value, BOOL* stop) {
    if (fabsf(value.floatValue) > 0.001f) [held addObject:[NSString stringWithFormat:@"a%@", axis]];
  }];
  return held;
}

/// The pad commands of a button item (DOLSkinButtonIds / DOLSkinTriggerIds).
- (NSSet<NSString*>*)commandsOf:(NSDictionary*)item wii:(BOOL)wii {
  NSDictionary* gc = @{@"a" : @"b0", @"b" : @"b1", @"start" : @"b2", @"x" : @"b3", @"y" : @"b4", @"z" : @"b5",
                       @"l" : @"a20", @"r" : @"a21"};
  NSDictionary* w = @{@"a" : @"b100", @"b" : @"b101", @"minus" : @"b102", @"plus" : @"b103", @"home" : @"b104",
                      @"one" : @"b105", @"two" : @"b106", @"c" : @"b200", @"z" : @"b201"};
  NSMutableSet* out = [NSMutableSet set];
  for (NSString* raw in item[@"inputs"]) {
    NSString* c = (wii ? w : gc)[raw];
    if (c != nil) [out addObject:c];
  }
  return out;
}

- (NSDictionary*)item:(NSString*)input of:(NSDictionary*)layout {
  for (NSDictionary* item in layout[@"items"]) {
    id inputs = item[@"inputs"];
    if ([inputs isKindOfClass:NSArray.class] && [inputs containsObject:input]) return item;
    if ([inputs isKindOfClass:NSDictionary.class] && [[inputs allValues] containsObject:input]) return item;
  }
  return nil;
}

#pragma mark Buttons: centre, contour and extension press only their control

- (void)checkButtons:(NSString*)skin portrait:(BOOL)portrait {
  const BOOL wii = [skin isEqualToString:kWii];
  NSDictionary* layout = [self layout:skin portrait:portrait];
  DOLSkinOverlay* overlay = [self overlay:skin portrait:portrait size:CGSizeZero];
  NSArray* items = layout[@"items"];
  for (NSDictionary* item in items) {
    if (![item[@"inputs"] isKindOfClass:NSArray.class]) continue;
    NSString* name = [item[@"inputs"] firstObject];
    NSSet* expected = [self commandsOf:item wii:wii];
    NSMutableArray<NSValue*>* points = [[self shapePoints:skin item:item] mutableCopy];
    XCTAssertGreaterThanOrEqual(points.count, 12u, @"%@ %@: contour points", skin, name);
    // The invisible extension, outside every drawn frame.
    const CGRect hit = [self hitRect:item], f = [self rect:item[@"frame"]];
    for (NSValue* candidate in @[ [NSValue valueWithCGPoint:CGPointMake(CGRectGetMidX(hit), CGRectGetMinY(hit) + 0.2)],
                                  [NSValue valueWithCGPoint:CGPointMake(CGRectGetMidX(hit), CGRectGetMaxY(hit) - 0.2)],
                                  [NSValue valueWithCGPoint:CGPointMake(CGRectGetMinX(hit) + 0.2, CGRectGetMidY(hit))],
                                  [NSValue valueWithCGPoint:CGPointMake(CGRectGetMaxX(hit) - 0.2, CGRectGetMidY(hit))] ]) {
      const CGPoint p = candidate.CGPointValue;
      if (CGRectContainsPoint(f, p)) continue;
      BOOL inOtherFrame = NO;
      for (NSDictionary* other in items) inOtherFrame = inOtherFrame || (other != item && CGRectContainsPoint([self rect:other[@"frame"]], p));
      if (!inOtherFrame) [points addObject:candidate];
    }
    for (NSValue* value in points) {
      const CGPoint p = value.CGPointValue;
      if ([name isEqualToString:@"menu"]) {
        const NSInteger before = _menuCount;
        SkinFakeTouch* t = [self touch:p];
        [self begin:t on:overlay];
        SkinHarnessWait(^BOOL { return self->_menuCount != before; }, 2);
        XCTAssertEqual(_menuCount, before + 1, @"%@ Menu once at (%.1f, %.1f)", skin, p.x, p.y);
        XCTAssertEqualObjects([self held], [NSSet set], @"Menu sends nothing to the pad");
        [self end:t on:overlay];
        continue;
      }
      SkinFakeTouch* t = [self touch:p];
      [self begin:t on:overlay];
      XCTAssertEqualObjects([self held], expected, @"%@ %@ %@ at (%.1f, %.1f)", skin, portrait ? @"portrait" : @"landscape", name, p.x, p.y);
      [self end:t on:overlay];
      XCTAssertEqualObjects([self held], [NSSet set], @"%@ %@ released", skin, name);
    }
  }
}

- (void)testGameCubeButtonsPortrait { [self checkButtons:kGC portrait:YES]; }
- (void)testGameCubeButtonsLandscape { [self checkButtons:kGC portrait:NO]; }
- (void)testWiiButtonsPortrait { [self checkButtons:kWii portrait:YES]; }
- (void)testWiiButtonsLandscape { [self checkButtons:kWii portrait:NO]; }

#pragma mark D-pad

- (void)checkDPad:(NSString*)skin portrait:(BOOL)portrait {
  const BOOL wii = [skin isEqualToString:kWii];
  NSDictionary* layout = [self layout:skin portrait:portrait];
  DOLSkinOverlay* overlay = [self overlay:skin portrait:portrait size:CGSizeZero];
  NSDictionary* dpad = [self item:@"up" of:layout];
  const CGRect f = [self rect:dpad[@"frame"]];
  const NSInteger base = wii ? 107 : 6;  // up, down, left, right
  NSArray* cases = @[ @[ @0.5, @0.12, @[ @0 ] ], @[ @0.5, @0.88, @[ @1 ] ], @[ @0.12, @0.5, @[ @2 ] ], @[ @0.88, @0.5, @[ @3 ] ],
                      @[ @0.86, @0.14, @[ @0, @3 ] ], @[ @0.14, @0.86, @[ @1, @2 ] ], @[ @0.5, @0.5, @[] ] ];
  for (NSArray* c in cases) {
    SkinFakeTouch* t = [self touch:CGPointMake(f.origin.x + [c[0] doubleValue] * f.size.width, f.origin.y + [c[1] doubleValue] * f.size.height)];
    [self begin:t on:overlay];
    NSMutableSet* expected = [NSMutableSet set];
    for (NSNumber* d in c[2]) [expected addObject:[NSString stringWithFormat:@"b%ld", (long)(base + d.integerValue)]];
    XCTAssertEqualObjects([self held], expected, @"%@ D-pad at %@,%@", skin, c[0], c[1]);
    [self end:t on:overlay];
    XCTAssertEqualObjects([self held], [NSSet set]);
  }
}

- (void)testDPadDirectionsAndDiagonals {
  for (NSString* skin in @[ kGC, kWii ]) {
    [self checkDPad:skin portrait:YES];
    [self checkDPad:skin portrait:NO];
  }
}

#pragma mark Sticks: centre, radius, axes, diagonals, saturation, exit, neutral, cap

- (UIImageView*)knobOf:(DOLSkinOverlay*)overlay item:(NSDictionary*)item {
  const CGFloat w = [item[@"thumbstick"][@"width"] doubleValue];
  for (UIView* view in overlay.subviews) {
    if ([view isKindOfClass:UIImageView.class] && !view.hidden && fabs(view.frame.size.width - w) < 0.01 &&
        CGRectContainsPoint([self rect:item[@"frame"]], CGPointMake(CGRectGetMidX(view.frame), CGRectGetMidY(view.frame))))
      return (UIImageView*)view;
  }
  return nil;
}

- (void)checkStick:(NSString*)skin input:(NSString*)input base:(NSInteger)base portrait:(BOOL)portrait {
  NSDictionary* layout = [self layout:skin portrait:portrait];
  DOLSkinOverlay* overlay = [self overlay:skin portrait:portrait size:CGSizeZero];
  NSDictionary* stick = [self item:input of:layout];
  XCTAssertNotNil(stick[@"thumbstick"]);
  const CGRect f = [self rect:stick[@"frame"]];
  const CGPoint c = CGPointMake(CGRectGetMidX(f), CGRectGetMidY(f));
  const CGFloat radius = f.size.width / 2, travel = (f.size.width - [stick[@"thumbstick"][@"width"] doubleValue]) / 2;
  UIImageView* knob = [self knobOf:overlay item:stick];
  XCTAssertNotNil(knob);
  XCTAssertEqualWithAccuracy(CGRectGetMidX(knob.frame), c.x, 0.01, @"cap at rest on the touch centre");
  XCTAssertEqualWithAccuracy(CGRectGetMidY(knob.frame), c.y, 0.01);
  NSString* tag = [NSString stringWithFormat:@"%@ %@ %@", skin, portrait ? @"portrait" : @"landscape", input];
  float (^axis)(NSInteger) = ^float(NSInteger i) { return SkinRecorderAxes()[@(base + i)].floatValue; };

  SkinFakeTouch* t = [self touch:c];
  [self begin:t on:overlay];
  for (NSInteger i = 1; i <= 4; i++) XCTAssertEqualWithAccuracy(axis(i), 0, 0.001, @"%@: centre is neutral", tag);
  // (dx, dy) in radii -> up, down, left, right axis values (TCJoystick: up and left negative).
  NSArray* cases = @[ @[ @0.5, @0, @0, @0, @0, @0.5 ], @[ @1, @0, @0, @0, @0, @1 ], @[ @0, @-1, @-1, @0, @0, @0 ],
                      @[ @0, @1, @0, @1, @0, @0 ], @[ @-1, @0, @0, @0, @-1, @0 ],
                      @[ @0.7071, @-0.7071, @-0.7071, @0, @0, @0.7071 ], @[ @3, @0, @0, @0, @0, @1 ],
                      @[ @-2, @2, @0, @0.7071, @-0.7071, @0 ] ];
  for (NSArray* k in cases) {
    const double dx = [k[0] doubleValue], dy = [k[1] doubleValue];
    [self move:t to:CGPointMake(c.x + dx * radius, c.y + dy * radius) on:overlay];
    for (NSInteger i = 1; i <= 4; i++)
      XCTAssertEqualWithAccuracy(axis(i), [k[i + 1] floatValue], 0.002, @"%@ at (%.2f, %.2f) axis %ld", tag, dx, dy, (long)i);
    // The cap moves by the same vector the axes carry, inside the socket.
    const double len = MAX(1.0, hypot(dx, dy));
    XCTAssertEqualWithAccuracy(CGRectGetMidX(knob.frame) - c.x, dx / len * travel, 0.05, @"%@ cap x", tag);
    XCTAssertEqualWithAccuracy(CGRectGetMidY(knob.frame) - c.y, dy / len * travel, 0.05, @"%@ cap y", tag);
    XCTAssertTrue(CGRectContainsRect(CGRectInset(f, -0.01, -0.01), knob.frame), @"%@ cap inside its socket", tag);
  }
  [self end:t on:overlay];
  for (NSInteger i = 1; i <= 4; i++) XCTAssertEqualWithAccuracy(axis(i), 0, 0.001, @"%@: neutral after release", tag);
  XCTAssertEqualWithAccuracy(CGRectGetMidX(knob.frame), c.x, 0.01, @"%@ cap back to centre", tag);
  XCTAssertEqualWithAccuracy(CGRectGetMidY(knob.frame), c.y, 0.01);
}

- (void)testSticksInBothOrientations {
  for (NSNumber* portrait in @[ @NO, @YES ]) {
    [self checkStick:kGC input:@"leftThumbstickUp" base:10 portrait:portrait.boolValue];
    [self checkStick:kGC input:@"rightThumbstickUp" base:15 portrait:portrait.boolValue];
    [self checkStick:kWii input:@"leftThumbstickUp" base:202 portrait:portrait.boolValue];
  }
}

/// The real phone size (letterboxed landscape mapping): the screen and the stick
/// centre follow the same transform as the drawing.
- (void)testLandscapeStickOnAPhoneSizedView {
  for (NSValue* sizeValue in @[ [NSValue valueWithCGSize:CGSizeMake(852, 393)], [NSValue valueWithCGSize:CGSizeMake(812, 375)] ]) {
    const CGSize size = sizeValue.CGSizeValue;
    NSDictionary* layout = [self layout:kGC portrait:NO];
    DOLSkinOverlay* overlay = [self overlay:kGC portrait:NO size:size];
    const CGSize m = CGSizeMake([layout[@"mappingSize"][@"width"] doubleValue], [layout[@"mappingSize"][@"height"] doubleValue]);
    const CGFloat scale = MIN(size.width / m.width, size.height / m.height);
    const CGPoint origin = CGPointMake((size.width - m.width * scale) / 2, (size.height - m.height * scale) / 2);
    const CGRect screen = [self rect:layout[@"screens"][0][@"outputFrame"]];
    XCTAssertEqualWithAccuracy(overlay.screenFrame.origin.x, origin.x + screen.origin.x * scale, 0.01);
    XCTAssertEqualWithAccuracy(overlay.screenFrame.origin.y, origin.y + screen.origin.y * scale, 0.01);
    NSDictionary* stick = [self item:@"leftThumbstickUp" of:layout];
    const CGRect f = [self rect:stick[@"frame"]];
    const CGPoint c = CGPointMake(origin.x + CGRectGetMidX(f) * scale, origin.y + CGRectGetMidY(f) * scale);
    UIImageView* knob = nil;
    for (UIView* view in overlay.subviews)
      if ([view isKindOfClass:UIImageView.class] && !view.hidden && fabs(view.frame.size.width - [stick[@"thumbstick"][@"width"] doubleValue] * scale) < 0.01) knob = (UIImageView*)view;
    XCTAssertNotNil(knob);
    XCTAssertEqualWithAccuracy(CGRectGetMidX(knob.frame), c.x, 0.01);
    XCTAssertEqualWithAccuracy(CGRectGetMidY(knob.frame), c.y, 0.01);
    SkinFakeTouch* t = [self touch:c];
    [self begin:t on:overlay];
    for (NSInteger i = 11; i <= 14; i++) XCTAssertEqualWithAccuracy(SkinRecorderAxes()[@(i)].floatValue, 0, 0.001);
    [self move:t to:CGPointMake(c.x, c.y + f.size.height / 2 * scale) on:overlay];
    XCTAssertEqualWithAccuracy(SkinRecorderAxes()[@12].floatValue, 1, 0.002, @"down at the rim, %@", NSStringFromCGSize(size));
    [self end:t on:overlay];
    XCTAssertEqualObjects([self held], [NSSet set]);
  }
}

#pragma mark Several fingers, slide, long press, cancel, rotation, menu

- (void)testStickPlusAAndShouldersTogetherThenSlideCancelAndRotation {
  NSDictionary* layout = [self layout:kGC portrait:NO];
  DOLSkinOverlay* overlay = [self overlay:kGC portrait:NO size:CGSizeZero];
  CGPoint (^centre)(NSString*) = ^CGPoint(NSString* input) {
    CGRect f = [self rect:[self item:input of:layout][@"frame"]];
    return CGPointMake(CGRectGetMidX(f), CGRectGetMidY(f));
  };
  NSDictionary* stick = [self item:@"leftThumbstickUp" of:layout];
  const CGRect sf = [self rect:stick[@"frame"]];
  SkinFakeTouch* s = [self touch:centre(@"leftThumbstickUp")];
  SkinFakeTouch* a = [self touch:centre(@"a")];
  SkinFakeTouch* l = [self touch:centre(@"l")];
  SkinFakeTouch* r = [self touch:centre(@"r")];
  [self begin:s on:overlay];
  [self move:s to:CGPointMake(CGRectGetMidX(sf) + sf.size.width / 2, CGRectGetMidY(sf)) on:overlay];
  [self begin:a on:overlay];
  [self begin:l on:overlay];
  [self begin:r on:overlay];
  NSSet* all = [NSSet setWithArray:@[ @"a14", @"b0", @"a20", @"a21" ]];
  XCTAssertEqualObjects([self held], all, @"stick right + A + L + R at once");
  // Long press: nothing releases by itself.
  [[NSRunLoop mainRunLoop] runUntilDate:[NSDate dateWithTimeIntervalSinceNow:0.6]];
  XCTAssertEqualObjects([self held], all);
  // A finger on the stick keeps it even outside its socket.
  [self move:s to:CGPointMake(CGRectGetMidX(sf), CGRectGetMinY(sf) - 80) on:overlay];
  XCTAssertEqualWithAccuracy(SkinRecorderAxes()[@11].floatValue, -1, 0.002, @"still the stick, up");
  // A finger slides from A to B: A releases, B presses.
  [self move:a to:centre(@"b") on:overlay];
  XCTAssertTrue([[self held] containsObject:@"b1"]);
  XCTAssertFalse([[self held] containsObject:@"b0"]);
  // Cancel of one finger releases it only.
  [overlay touchesCancelled:[NSSet setWithObject:l] withEvent:nil];
  XCTAssertFalse([[self held] containsObject:@"a20"]);
  XCTAssertTrue([[self held] containsObject:@"a21"]);
  // Rotation (the other layout) releases everything, then the portrait layout works.
  NSDictionary* pm = [self layout:kGC portrait:YES][@"mappingSize"];
  overlay.frame = CGRectMake(0, 0, [pm[@"width"] doubleValue], [pm[@"height"] doubleValue]);
  [overlay setNeedsLayout];
  [overlay layoutIfNeeded];
  XCTAssertEqualObjects([self held], [NSSet set], @"rotation releases every held command");
  NSDictionary* portraitA = [self item:@"a" of:[self layout:kGC portrait:YES]];
  CGRect pf = [self rect:portraitA[@"frame"]];
  SkinFakeTouch* p = [self touch:CGPointMake(CGRectGetMidX(pf), CGRectGetMidY(pf))];
  [self begin:p on:overlay];
  XCTAssertEqualObjects([self held], [NSSet setWithObject:@"b0"]);
  // Menu / background / stop go through releaseAllInputs.
  [overlay releaseAllInputs];
  XCTAssertEqualObjects([self held], [NSSet set], @"menu, background and stop release everything");
}

#pragma mark The drawing: a press changes the control only, inside its outline

- (UIImage*)render:(DOLSkinOverlay*)overlay {
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

- (void)checkPressedDrawing:(NSString*)skin portrait:(BOOL)portrait {
  NSDictionary* layout = [self layout:skin portrait:portrait];
  DOLSkinOverlay* overlay = [self overlay:skin portrait:portrait size:CGSizeZero];
  NSData* rest = [self rgba:[self render:overlay]];
  const long W = lround(overlay.bounds.size.width * 3);
  for (NSDictionary* item in layout[@"items"]) {
    if (![item[@"inputs"] isKindOfClass:NSArray.class] || [[item[@"inputs"] firstObject] isEqualToString:@"menu"]) continue;
    const CGRect f = [self rect:item[@"frame"]];
    SkinFakeTouch* t = [self touch:[[self shapePoints:skin item:item].firstObject CGPointValue]];
    [self begin:t on:overlay];
    NSData* pressed = [self rgba:[self render:overlay]];
    [self end:t on:overlay];
    NSData* released = [self rgba:[self render:overlay]];
    XCTAssertEqualObjects(released, rest, @"%@ %@: released is the rest drawing again", skin, item[@"inputs"]);
    CGSize asize;
    NSData* alpha = [self alphaOf:skin item:item size:&asize];
    const uint8_t* A = (const uint8_t*)alpha.bytes;
    const uint8_t* R = (const uint8_t*)rest.bytes;
    const uint8_t* P = (const uint8_t*)pressed.bytes;
    // Outside the sprite's outline (alpha 0) nothing changes; inside it darkens visibly.
    double outsideChange = 0, insideRest = 0, insidePressed = 0;
    long outside = 0, inside = 0;
    const long x0 = lround(f.origin.x * 3) - 6, y0 = lround(f.origin.y * 3) - 6;
    const long x1 = lround(CGRectGetMaxX(f) * 3) + 6, y1 = lround(CGRectGetMaxY(f) * 3) + 6;
    for (long y = MAX(0, y0); y < y1; y++) {
      for (long x = MAX(0, x0); x < MIN(W, x1); x++) {
        const double mx = (x + 0.5) / 3, my = (y + 0.5) / 3;
        long u = (long)((mx - f.origin.x) / f.size.width * asize.width), v = (long)((my - f.origin.y) / f.size.height * asize.height);
        // Largest alpha around the point (2 sprite pixels): UIKit resamples the sprite.
        int a = 0;
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
    XCTAssertLessThanOrEqual(outsideChange, 6.0, @"%@ %@: the press changed pixels outside the control", skin, item[@"inputs"]);
    XCTAssertLessThan(insidePressed, insideRest * 0.88, @"%@ %@: a press is clearly visible", skin, item[@"inputs"]);
  }
}

- (void)testPressedDrawingStaysInsideTheOutline {
  for (NSString* skin in @[ kGC, kWii ]) {
    [self checkPressedDrawing:skin portrait:YES];
    [self checkPressedDrawing:skin portrait:NO];
  }
}

#pragma mark The game's place: the opening the skin's body draws (test/skin_frame/SkinFrameCheck.h)

/// `skin` chosen for both orientations of its console (the Originals are chosen by setUp).
- (void)choose:(NSString*)skin {
  NSString* frontend = [[[self documents] stringByAppendingPathComponent:@"Libretro"] stringByAppendingPathComponent:@"Config/Frontend"];
  NSData* data = [NSJSONSerialization dataWithJSONObject:@{@"console" : @{@"skin.portrait" : skin, @"skin.landscape" : skin}}
                                                 options:0 error:nil];
  [data writeToFile:[frontend stringByAppendingPathComponent:[skin hasPrefix:@"wii"] ? @"wii.json" : @"gc.json"] atomically:YES];
}

- (void)checkFrameOf:(DOLSkinOverlay*)overlay skin:(NSString*)skin portrait:(BOOL)portrait tag:(NSString*)tag evidence:(BOOL)evidence {
  // A rounded corner hides a few points at each end of the test pattern's bands.
  static const double minimum[4] = {0.9, 0.9, 0.9, 0.9};
  NSString* renders = NSProcessInfo.processInfo.environment[@"DOLPHIN_RENDER_DIR"];
  NSString* file = evidence && renders.length > 0
      ? [renders stringByAppendingPathComponent:[NSString stringWithFormat:@"%@-%@-test-pattern.png", skin, tag]] : nil;
  SkinFrameCheck(self, overlay, overlay.screenFrame, overlay.screenCutoutActive, [self layout:skin portrait:portrait],
                 [_skins stringByAppendingPathComponent:skin], [NSString stringWithFormat:@"%@ %@", skin, tag], minimum, file);
}

/// A (GameCube) or A (Wii Remote) pressed and released at its drawn centre.
- (void)pressAOn:(DOLSkinOverlay*)overlay skin:(NSString*)skin portrait:(BOOL)portrait what:(NSString*)what {
  NSDictionary* item = [self item:@"a" of:[self layout:skin portrait:portrait]];
  const CGSize size = overlay.bounds.size;
  NSDictionary* mapping = [self layout:skin portrait:portrait][@"mappingSize"];
  const CGSize m = CGSizeMake([mapping[@"width"] doubleValue], [mapping[@"height"] doubleValue]);
  const CGFloat scale = MIN(size.width / m.width, size.height / m.height);
  const CGRect f = [self rect:item[@"frame"]];
  SkinFakeTouch* finger = [self touch:CGPointMake((size.width - m.width * scale) / 2 + CGRectGetMidX(f) * scale,
                                                  (size.height - m.height * scale) / 2 + CGRectGetMidY(f) * scale)];
  [self begin:finger on:overlay];
  XCTAssertEqualObjects([self held], [self commandsOf:item wii:[skin hasPrefix:@"wii"]], @"%@: A answers %@", skin, what);
  [self end:finger on:overlay];
  XCTAssertEqualObjects([self held], [NSSet set], @"%@: A released %@", skin, what);
}

/// Every Dolphin Pocket pack, both orientations, at the mapping size and at real phone
/// sizes (the skin fitted with one scale).
- (void)testTheGameFillsTheDrawnOpening {
  for (NSString* skin in @[ kWiiPocket, kGCPocket, kWii, kGC ]) {
    [self choose:skin];
    for (NSNumber* portraitValue in @[ @YES, @NO ]) {
      const BOOL portrait = portraitValue.boolValue;
      NSString* name = portrait ? @"portrait" : @"landscape";
      for (NSValue* value in @[ [NSValue valueWithCGSize:CGSizeZero], [NSValue valueWithCGSize:CGSizeMake(393, 852)],
                                [NSValue valueWithCGSize:CGSizeMake(375, 812)], [NSValue valueWithCGSize:CGSizeMake(430, 932)] ]) {
        CGSize size = value.CGSizeValue;
        if (!portrait) size = CGSizeMake(size.height, size.width);
        DOLSkinOverlay* overlay = [self overlay:skin portrait:portrait size:size];
        [self checkFrameOf:overlay skin:skin portrait:portrait
                       tag:size.width >= 1 ? [NSString stringWithFormat:@"%@-%.0fx%.0f", name, size.width, size.height] : name
                  evidence:size.width < 1];
        [self pressAOn:overlay skin:skin portrait:portrait what:@"in its place"];
      }
    }
  }
}

/// One overlay through what a session does to it: a turn, the session menu over it (inputs
/// released, touches off then on again, hidden then shown), a turn back.
- (void)testTheGameScreenAndControlsAfterRotationAndMenu {
  for (NSString* skin in @[ kWiiPocket, kGCPocket, kWii, kGC ]) {
    [self choose:skin];
    DOLSkinOverlay* overlay = [self overlay:skin portrait:YES size:CGSizeMake(393, 852)];
    [self checkFrameOf:overlay skin:skin portrait:YES tag:@"portrait" evidence:NO];
    void (^turn)(CGSize) = ^(CGSize size) {
      overlay.frame = CGRectMake(0, 0, size.width, size.height);
      [overlay setNeedsLayout];
      [overlay layoutIfNeeded];
    };
    turn(CGSizeMake(852, 393));
    [self checkFrameOf:overlay skin:skin portrait:NO tag:@"landscape after a turn" evidence:NO];
    [self pressAOn:overlay skin:skin portrait:NO what:@"after a turn"];
    [overlay releaseAllInputs];
    overlay.userInteractionEnabled = NO;
    overlay.hidden = YES;
    overlay.hidden = NO;
    overlay.userInteractionEnabled = YES;
    [overlay setNeedsLayout];
    [overlay layoutIfNeeded];
    [self checkFrameOf:overlay skin:skin portrait:NO tag:@"landscape after the menu" evidence:NO];
    [self pressAOn:overlay skin:skin portrait:NO what:@"after the menu closed"];
    turn(CGSizeMake(393, 852));
    [self checkFrameOf:overlay skin:skin portrait:YES tag:@"portrait after turning back" evidence:NO];
    [self pressAOn:overlay skin:skin portrait:YES what:@"after turning back"];
  }
}

/// A D-pad shows the arm under the finger pressed, not the whole cross (maintainer's
/// recording of Wii Pocket - Original upright).
- (void)testTheDPadShowsThePressedArmOnly {
  for (NSString* skin in @[ kWii, kGC, kWiiPocket, kGCPocket ]) {
    [self choose:skin];
    for (NSNumber* portraitValue in @[ @YES, @NO ]) {
      const BOOL portrait = portraitValue.boolValue;
      DOLSkinOverlay* overlay = [self overlay:skin portrait:portrait size:CGSizeZero];
      const CGRect frame = [self rect:[self item:@"up" of:[self layout:skin portrait:portrait]][@"frame"]];
      __block SkinFakeTouch* finger = nil;
      SkinDPadArmCheck(self, overlay, frame, ^(CGPoint point) {
        finger = [self touch:point];
        [self begin:finger on:overlay];
      }, ^{
        [self end:finger on:overlay];
      }, [NSString stringWithFormat:@"%@ %@", skin, portrait ? @"portrait" : @"landscape"]);
    }
  }
}

/// Another skin chosen, then the session launched again (a new overlay reads the files):
/// each skin gets its own game place and its controls; "default" leaves no overlay.
- (void)testTheGameScreenFollowsASkinChangeAndARelaunch {
  for (NSString* skin in @[ kWiiPocket, kWii, kWiiPocket, kGCPocket, kGC, kGCPocket ]) {
    [self choose:skin];
    for (NSNumber* portrait in @[ @YES, @NO ]) {
      DOLSkinOverlay* overlay = [self overlay:skin portrait:portrait.boolValue size:CGSizeZero];
      [self checkFrameOf:overlay skin:skin portrait:portrait.boolValue
                     tag:[NSString stringWithFormat:@"%@ after a skin change", portrait.boolValue ? @"portrait" : @"landscape"] evidence:NO];
      [self pressAOn:overlay skin:skin portrait:portrait.boolValue what:@"after a skin change"];
    }
  }
  [self choose:@"default"];
  XCTAssertFalse([[DOLSkinOverlay alloc] initWithWii:NO gameKey:nil].hasSkin, @"skin off: no overlay, the game keeps the whole view");
}

/// The surface the core reads once at launch: the session asks for the game's place in
/// the bounds it settles in (DOLPolicyBoundsWillTurn), whatever the overlay is laid out
/// in at that moment. It is the same rectangle as the layout gives once turned.
- (void)testTheScreenForTheSettledBoundsIsTheOneOfTheLayout {
  for (NSString* skin in @[ kWiiPocket, kGCPocket, kWii, kGC ]) {
    [self choose:skin];
    const CGSize upright = CGSizeMake(393, 852), sideways = CGSizeMake(852, 393);
    // Laid out sideways (the screen that opened the session), asked for the upright bounds.
    DOLSkinOverlay* overlay = [self overlay:skin portrait:NO size:sideways];
    const CGRect asked = [overlay screenFrameForBounds:CGRectMake(0, 0, upright.width, upright.height)];
    XCTAssertTrue(CGRectEqualToRect([overlay screenFrameForBounds:overlay.bounds], overlay.screenFrame), @"%@: the current bounds", skin);
    overlay.frame = CGRectMake(0, 0, upright.width, upright.height);
    [overlay setNeedsLayout];
    [overlay layoutIfNeeded];
    XCTAssertTrue(CGRectEqualToRect(asked, overlay.screenFrame), @"%@: asked %@, laid out %@", skin, NSStringFromCGRect(asked),
                  NSStringFromCGRect(overlay.screenFrame));
    XCTAssertTrue(asked.size.width > asked.size.height, @"%@: the upright skin's screen is wider than tall, not the sideways view", skin);
    XCTAssertTrue(CGRectIsNull([overlay screenFrameForBounds:CGRectZero]));
  }
}

@end
