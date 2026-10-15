#import "LibretroSkinPressure.h"
#include <math.h>
#include <stdlib.h>
#include <string.h>

CGRect LibretroSkinPressureArm(CGSize size, NSUInteger slot) {
  CGFloat x = floor(size.width / 3), y = floor(size.height / 3);
  CGFloat right = ceil(size.width * 2 / 3), bottom = ceil(size.height * 2 / 3);
  switch (slot) {
    case 0: return CGRectMake(0, 0, size.width, y);
    case 1: return CGRectMake(0, bottom, size.width, size.height - bottom);
    case 2: return CGRectMake(0, y, x, bottom - y);
    case 3: return CGRectMake(right, y, size.width - right, bottom - y);
    default: return CGRectZero;
  }
}

// A compact smooth support, flat at its peak and pinned at the perimeter.
// A steep falloff would visibly stretch the housing around a painted key.
static double Weight(double t) {
  double v = fmax(0, 1 - t*t);
  return v*v;
}

static BOOL ReadPixels(CGImageRef source, CGRect rect, uint8_t *bytes, size_t w, size_t h, CGColorSpaceRef space) {
  CGImageRef crop = CGImageCreateWithImageInRect(source, rect);
  if (crop == NULL) return NO;
  CGContextRef context = CGBitmapContextCreate(bytes, w, h, 8, w*4, space,
      kCGImageAlphaPremultipliedLast | kCGBitmapByteOrder32Big);
  if (context != NULL) {
    // Copy CGImage rows without a UIKit coordinate-system flip.
    CGContextDrawImage(context, CGRectMake(0, 0, w, h), crop);
    CGContextRelease(context);
  }
  CGImageRelease(crop);
  return context != NULL;
}

NSArray *LibretroSkinPressureFrames(CGImageRef source, CGRect pixels,
    CGFloat pointsPerPixel, NSUInteger direction, CGImageRef authoredPressed) {
  if (source == NULL || !isfinite(pointsPerPixel) || pointsPerPixel <= 0 ||
      !isfinite(pixels.origin.x) || !isfinite(pixels.origin.y) ||
      !isfinite(pixels.size.width) || !isfinite(pixels.size.height) ||
      !CGRectEqualToRect(pixels, CGRectIntegral(pixels)) ||
      pixels.size.width < 3 || pixels.size.height < 3 ||
      pixels.size.width > 2048 || pixels.size.height > 2048 ||
      !CGRectContainsRect(CGRectMake(0, 0, CGImageGetWidth(source), CGImageGetHeight(source)), pixels)) return @[];
  size_t w = (size_t)pixels.size.width, h = (size_t)pixels.size.height, length = w*h*4;
  // Caller also enforces a per-renderer budget across controls.
  if (length > 4u*1024u*1024u) return @[];
  if (authoredPressed != NULL && (CGImageGetWidth(authoredPressed) != CGImageGetWidth(source) ||
      CGImageGetHeight(authoredPressed) != CGImageGetHeight(source))) return @[];
  uint8_t *normal = calloc(1, length), *pressed = authoredPressed ? calloc(1, length) : NULL;
  if (normal == NULL || (authoredPressed && pressed == NULL)) { free(normal); free(pressed); return @[]; }
  CGColorSpaceRef originalSpace = CGImageGetColorSpace(source);
  CGColorSpaceRef space = originalSpace != NULL && CGColorSpaceGetModel(originalSpace) == kCGColorSpaceModelRGB ?
      CGColorSpaceRetain(originalSpace) : CGColorSpaceCreateWithName(kCGColorSpaceSRGB);
  if (!ReadPixels(source, pixels, normal, w, h, space) ||
      (authoredPressed && !ReadPixels(authoredPressed, pixels, pressed, w, h, space))) {
    CGColorSpaceRelease(space); free(normal); free(pressed); return @[];
  }
  NSMutableArray *frames = [NSMutableArray arrayWithCapacity:8];
  // Limit displacement relative to the smaller side too: the mapping stays
  // monotonic even for thin Start/Select keys. No fold or edge extrapolation.
  double depth = fmin(1.6 / pointsPerPixel, fmin(w, h) * 0.045);
  for (NSUInteger step = 0; step < 8; step++) {
    double amount = (double)step / 7;
    NSMutableData *data = [NSMutableData dataWithLength:length];
    uint8_t *out = data.mutableBytes;
    if (step == 0) {
      memcpy(out, normal, length);
    } else for (size_t y = 0; y < h; y++) for (size_t x = 0; x < w; x++) {
      size_t offset = (y*w+x)*4;
      double nx = 2.0*x/(w-1)-1, ny = 2.0*y/(h-1)-1;
      // For the broad upper/lower regions, don't bend the housing in the
      // corners alongside a cross. Other arms never share this support.
      double wx = Weight(nx * ((direction == 1 || direction == 2) ? 1.5 : 1));
      double weight = wx * Weight(ny);
      if (pressed != NULL) {
        // Authored states have their own edges/shadows: preserve those
        // pixels, including alpha, instead of adding a lighting effect.
        for (size_t c = 0; c < 4; c++)
          out[offset+c] = (uint8_t)lround(normal[offset+c]*(1-amount) + pressed[offset+c]*amount);
        continue;
      }
      if (weight == 0) { memcpy(out+offset, normal+offset, 4); continue; }
      // Inverse sampling: a slight contraction and downward depression,
      // smoothly anchored to the untouched image at the region boundary.
      double dx = (x-(w-1)*0.5)*0.035;
      double dy = (y-(h-1)*0.5)*0.035 - depth;
      double sx = fmax(0, fmin(w-1, x + dx*weight*amount));
      double sy = fmax(0, fmin(h-1, y + dy*weight*amount));
      size_t x0 = (size_t)sx, y0 = (size_t)sy, x1 = MIN(x0+1,w-1), y1 = MIN(y0+1,h-1);
      double fx = sx-x0, fy = sy-y0;
      for (size_t c = 0; c < 4; c++) {
        double top = normal[(y0*w+x0)*4+c]*(1-fx)+normal[(y0*w+x1)*4+c]*fx;
        double bottom = normal[(y1*w+x0)*4+c]*(1-fx)+normal[(y1*w+x1)*4+c]*fx;
        // Subtle occlusion also makes a featureless solid-colour arm read
        // as depressed. Preserve its hue and alpha; never add a glow.
        double shade = c == 3 ? 1 : 1 - 0.06*weight*amount;
        out[offset+c] = (uint8_t)lround((top*(1-fy)+bottom*fy)*shade);
      }
    }
    CGDataProviderRef provider = CGDataProviderCreateWithCFData((__bridge CFDataRef)data);
    CGImageRef image = CGImageCreate(w, h, 8, 32, w*4, space,
        kCGImageAlphaPremultipliedLast | kCGBitmapByteOrder32Big, provider, NULL, false, kCGRenderingIntentDefault);
    CGDataProviderRelease(provider);
    if (image != NULL) { [frames addObject:(__bridge id)image]; CGImageRelease(image); }
  }
  CGColorSpaceRelease(space);
  free(normal); free(pressed);
  return frames.count == 8 ? frames : @[];
}
