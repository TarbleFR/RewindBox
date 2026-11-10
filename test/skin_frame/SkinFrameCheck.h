// The game's place in a skin overlay, checked on the real overlay in the iOS Simulator.
// Shared by the three harnesses (packages/{dolphin,armsx2,melonx}_internal_bridge/ci):
// DOLSkinOverlay, ARMSX2SkinOverlay and MeloNXSkinOverlay place the game the same way.
//
// A Pocket pack declares the game's place as `screens[0].outputFrame` (the bounding box
// of the opening its body draws) and, when the opening is not a plain rectangle,
// `screens[0].screenCutout` (a PNG the size of the body whose alpha is where the body
// stays). SkinFrameCheck verifies on the overlay UIKit really draws:
//   1. `screenFrame` is the declared frame under the skin's own transform (one scale, the
//      skin centred): the same transform as the drawing;
//   2. the hole in the skin is the cutout under that transform (the declared rectangle
//      for a pack without cutout): transparent where the game shows, the body elsewhere;
//   3. a test pattern put where the session puts the game's surface (the frame grown to
//      whole points) shows a band of its own colour along each of its four edges, and
//      nothing shows through the skin around it.
#pragma once
#import <UIKit/UIKit.h>
#import <XCTest/XCTest.h>

/// One byte per pixel: the image's alpha, first row at the top.
static NSData* SkinFrameAlpha(UIImage* image, long* width, long* height) {
  CGImageRef cg = image.CGImage;
  const size_t w = CGImageGetWidth(cg), h = CGImageGetHeight(cg);
  NSMutableData* data = [NSMutableData dataWithLength:w * h];
  CGContextRef context = CGBitmapContextCreate(data.mutableBytes, w, h, 8, w, NULL, (CGBitmapInfo)kCGImageAlphaOnly);
  CGContextDrawImage(context, CGRectMake(0, 0, w, h), cg);
  CGContextRelease(context);
  *width = (long)w;
  *height = (long)h;
  return data;
}

static NSData* SkinFrameRGBA(UIImage* image, long* width, long* height) {
  CGImageRef cg = image.CGImage;
  const size_t w = CGImageGetWidth(cg), h = CGImageGetHeight(cg);
  NSMutableData* data = [NSMutableData dataWithLength:w * h * 4];
  CGColorSpaceRef space = CGColorSpaceCreateDeviceRGB();
  CGContextRef context = CGBitmapContextCreate(data.mutableBytes, w, h, 8, w * 4, space, (CGBitmapInfo)kCGImageAlphaPremultipliedLast);
  CGContextDrawImage(context, CGRectMake(0, 0, w, h), cg);
  CGContextRelease(context);
  CGColorSpaceRelease(space);
  *width = (long)w;
  *height = (long)h;
  return data;
}

/// `view` as UIKit draws it, 3 pixels per point, over nothing (`opaque` NO) or over black.
static UIImage* SkinFrameRender(UIView* view, BOOL opaque) {
  UIGraphicsImageRendererFormat* format = [UIGraphicsImageRendererFormat preferredFormat];
  format.scale = 3;
  format.opaque = opaque;
  UIGraphicsImageRenderer* renderer = [[UIGraphicsImageRenderer alloc] initWithSize:view.bounds.size format:format];
  return [renderer imageWithActions:^(UIGraphicsImageRendererContext* context) {
    if (opaque) {
      [UIColor.blackColor setFill];
      UIRectFill(view.bounds);
    }
    [view.layer renderInContext:context.CGContext];
  }];
}

static const CGFloat kSkinFrameBand = 6;

/// A test pattern filling `frame`: a 6 pt band along each edge (top red, bottom green,
/// left blue, right yellow), a white cross and a centre square, on mid grey.
static UIView* SkinFrameMire(CGRect frame) {
  UIView* mire = [[UIView alloc] initWithFrame:frame];
  mire.backgroundColor = [UIColor colorWithWhite:0.5 alpha:1];
  const CGFloat w = frame.size.width, h = frame.size.height, t = kSkinFrameBand;
  NSArray<NSArray*>* parts = @[
    @[ [NSValue valueWithCGRect:CGRectMake(w / 2 - 0.5, 0, 1, h)], UIColor.whiteColor ],
    @[ [NSValue valueWithCGRect:CGRectMake(0, h / 2 - 0.5, w, 1)], UIColor.whiteColor ],
    @[ [NSValue valueWithCGRect:CGRectMake(w / 2 - 12, h / 2 - 12, 24, 24)], UIColor.whiteColor ],
    @[ [NSValue valueWithCGRect:CGRectMake(0, t, t, h - 2 * t)], UIColor.blueColor ],
    @[ [NSValue valueWithCGRect:CGRectMake(w - t, t, t, h - 2 * t)], UIColor.yellowColor ],
    @[ [NSValue valueWithCGRect:CGRectMake(0, 0, w, t)], UIColor.redColor ],
    @[ [NSValue valueWithCGRect:CGRectMake(0, h - t, w, t)], UIColor.greenColor ],
  ];
  for (NSArray* part in parts) {
    UIView* view = [[UIView alloc] initWithFrame:[part[0] CGRectValue]];
    view.backgroundColor = part[1];
    [mire addSubview:view];
  }
  return mire;
}

/// `overlay`: the laid-out skin overlay (in no superview); `screen` / `cutoutActive`: its
/// screenFrame and screenCutoutActive; `layout`: the info.json layout it shows;
/// `directory`: the installed skin folder; `minimum`: the part of each edge band (top,
/// bottom, left, right) that must show (a rounded corner, a tab of the body reaching into
/// the opening hide the rest); `evidence`: where to write the test pattern's render (nil:
/// nowhere).
static void SkinFrameCheck(XCTestCase* self, UIView* overlay, CGRect screen, BOOL cutoutActive, NSDictionary* layout,
                           NSString* directory, NSString* tag, const double minimum[4], NSString* evidence) {
  const CGSize size = overlay.bounds.size;
  const CGSize m = CGSizeMake([layout[@"mappingSize"][@"width"] doubleValue], [layout[@"mappingSize"][@"height"] doubleValue]);
  XCTAssertTrue(m.width >= 1 && m.height >= 1 && size.width >= 1 && size.height >= 1, @"%@", tag);
  if (m.width < 1 || m.height < 1 || size.width < 1 || size.height < 1) return;
  const CGFloat scale = MIN(size.width / m.width, size.height / m.height);
  const CGPoint origin = CGPointMake((size.width - m.width * scale) / 2, (size.height - m.height * scale) / 2);
  NSDictionary* declared = [layout[@"screens"] firstObject];
  NSDictionary* f = declared[@"outputFrame"];
  XCTAssertNotNil(f, @"%@ declares its game screen", tag);
  if (f == nil) return;
  const double fx = [f[@"x"] doubleValue], fy = [f[@"y"] doubleValue], fw = [f[@"width"] doubleValue], fh = [f[@"height"] doubleValue];

  // 1. The declared frame under the skin's own transform.
  XCTAssertEqualWithAccuracy(screen.origin.x, origin.x + fx * scale, 0.01, @"%@ screen x", tag);
  XCTAssertEqualWithAccuracy(screen.origin.y, origin.y + fy * scale, 0.01, @"%@ screen y", tag);
  XCTAssertEqualWithAccuracy(screen.size.width, fw * scale, 0.01, @"%@ screen width", tag);
  XCTAssertEqualWithAccuracy(screen.size.height, fh * scale, 0.01, @"%@ screen height", tag);

  // 2. The hole UIKit draws in the skin.
  NSString* cutoutName = declared[@"screenCutout"];
  XCTAssertEqual(cutoutActive, (BOOL)(cutoutName != nil), @"%@ cuts its screen with the pack's cutout when it ships one", tag);
  long cw = 0, ch = 0;
  NSData* cutout = nil;
  if (cutoutName != nil) {
    UIImage* image = [UIImage imageWithContentsOfFile:[directory stringByAppendingPathComponent:cutoutName]];
    XCTAssertNotNil(image, @"%@ cutout %@", tag, cutoutName);
    if (image == nil) return;
    cutout = SkinFrameAlpha(image, &cw, &ch);
  }
  long W = 0, H = 0;
  NSData* drawn = SkinFrameAlpha(SkinFrameRender(overlay, NO), &W, &H);
  const uint8_t* C = (const uint8_t*)cutout.bytes;
  const uint8_t* D = (const uint8_t*)drawn.bytes;
  long holes = 0, bodies = 0, wrong = 0;
  for (long y = 0; y < H; y += 2) {
    for (long x = 0; x < W; x += 2) {
      const double mx = ((x + 0.5) / 3 - origin.x) / scale, my = ((y + 0.5) / 3 - origin.y) / scale;
      if (mx < 1 || my < 1 || mx > m.width - 1 || my > m.height - 1) continue;  // around the skin
      int lo = 255, hi = 0;
      if (cutout != nil) {
        // Where the cutout is flat around the point: its edge is antialiased and resampled.
        const long u = (long)(mx / m.width * cw), v = (long)(my / m.height * ch);
        for (long dv = -3; dv <= 3; dv++) {
          for (long du = -3; du <= 3; du++) {
            const long uu = MIN(MAX(u + du, 0), cw - 1), vv = MIN(MAX(v + dv, 0), ch - 1);
            const int a = C[vv * cw + uu];
            lo = MIN(lo, a);
            hi = MAX(hi, a);
          }
        }
      } else {
        // A rectangular window: the declared frame itself (a point around its edge left out).
        const double inside = MIN(MIN(mx - fx, fx + fw - mx), MIN(my - fy, fy + fh - my));
        if (fabs(inside) < 1) continue;
        lo = hi = inside > 0 ? 0 : 255;
      }
      if (lo != hi) continue;
      const int d = D[y * W + x];
      if (hi == 0) {
        holes++;
        if (d > 8) wrong++;
      } else if (lo == 255) {
        bodies++;
        if (d < 247) wrong++;
      }
    }
  }
  XCTAssertGreaterThan(holes, 1000L, @"%@ the game shows through the skin", tag);
  XCTAssertGreaterThan(bodies, 1000L, @"%@ the body is drawn", tag);
  XCTAssertEqual(wrong, 0L, @"%@ the hole in the skin is the opening its body draws (%ld hole, %ld body points)", tag, holes, bodies);

  // 3. A test pattern where the session puts the game's surface.
  UIView* container = [[UIView alloc] initWithFrame:overlay.bounds];
  container.backgroundColor = UIColor.magentaColor;
  const CGRect place = CGRectIntegral(screen);
  [container addSubview:SkinFrameMire(place)];
  [container addSubview:overlay];
  UIImage* shot = SkinFrameRender(container, YES);
  [overlay removeFromSuperview];
  long SW = 0, SH = 0;
  NSData* rgba = SkinFrameRGBA(shot, &SW, &SH);
  const uint8_t* P = (const uint8_t*)rgba.bytes;
  long through = 0;
  for (long y = 0; y < SH; y++) {
    for (long x = 0; x < SW; x++) {
      const double mx = ((x + 0.5) / 3 - origin.x) / scale, my = ((y + 0.5) / 3 - origin.y) / scale;
      if (mx < 1 || my < 1 || mx > m.width - 1 || my > m.height - 1) continue;
      const uint8_t* p = P + (y * SW + x) * 4;
      if (p[0] > 200 && p[1] < 60 && p[2] > 200) through++;
    }
  }
  XCTAssertEqual(through, 0L, @"%@ nothing shows through the skin around the game", tag);
  // Each band along the middle of its thickness: top, bottom, left, right.
  const int colours[4][3] = {{255, 0, 0}, {0, 255, 0}, {0, 0, 255}, {255, 255, 0}};
  NSArray<NSString*>* names = @[ @"top", @"bottom", @"left", @"right" ];
  const CGFloat t = kSkinFrameBand;
  for (int edge = 0; edge < 4; edge++) {
    long seen = 0, total = 0;
    const BOOL horizontal = edge < 2;
    const CGFloat from = horizontal ? CGRectGetMinX(place) : CGRectGetMinY(place) + t;
    const CGFloat to = horizontal ? CGRectGetMaxX(place) : CGRectGetMaxY(place) - t;
    const CGFloat across = edge == 0 ? CGRectGetMinY(place) + t / 2 : edge == 1 ? CGRectGetMaxY(place) - t / 2
                           : edge == 2 ? CGRectGetMinX(place) + t / 2 : CGRectGetMaxX(place) - t / 2;
    for (CGFloat along = from + 0.5; along < to; along += 1.0 / 3) {
      const long x = (long)((horizontal ? along : across) * 3), y = (long)((horizontal ? across : along) * 3);
      if (x < 0 || y < 0 || x >= SW || y >= SH) continue;
      const uint8_t* p = P + (y * SW + x) * 4;
      total++;
      if (abs(p[0] - colours[edge][0]) < 70 && abs(p[1] - colours[edge][1]) < 70 && abs(p[2] - colours[edge][2]) < 70) seen++;
    }
    XCTAssertGreaterThan(total, 100L, @"%@ %@ edge", tag, names[edge]);
    const double part = total > 0 ? (double)seen / total : 0;
    XCTAssertGreaterThanOrEqual(part, minimum[edge], @"%@ the test pattern's %@ edge shows (%.3f of its length)", tag, names[edge], part);
  }
  if (evidence.length > 0) {
    NSData* png = UIImagePNGRepresentation(shot);
    [NSFileManager.defaultManager createDirectoryAtPath:evidence.stringByDeletingLastPathComponent
                            withIntermediateDirectories:YES attributes:nil error:nil];
    [png writeToFile:evidence atomically:YES];
    XCTAttachment* attachment = [XCTAttachment attachmentWithUniformTypeIdentifier:@"public.png" name:evidence.lastPathComponent
                                                                           payload:png userInfo:nil];
    attachment.lifetime = XCTAttachmentLifetimeKeepAlways;
    [self addAttachment:attachment];
  }
}
