#import "LibretroSkinButtonCrop.h"
#import <Foundation/Foundation.h>
#include <math.h>
#include <stdlib.h>

CGImageRef LibretroSkinCreateButtonCrop(CGImageRef image, CGRect pixels, CGImageRef *background) {
  if (background != NULL) *background = NULL;
  if (image == NULL || background == NULL || !isfinite(pixels.origin.x) || !isfinite(pixels.origin.y) ||
      !isfinite(pixels.size.width) || !isfinite(pixels.size.height)) return NULL;
  pixels = CGRectIntegral(pixels);
  if (pixels.size.width < 8 || pixels.size.height < 8 || pixels.size.width > 2048 || pixels.size.height > 2048 ||
      pixels.origin.x < 0 || pixels.origin.y < 0 || CGRectGetMaxX(pixels) > CGImageGetWidth(image) ||
      CGRectGetMaxY(pixels) > CGImageGetHeight(image)) return NULL;
  size_t width = (size_t)pixels.size.width, height = (size_t)pixels.size.height;
  CGImageRef crop = CGImageCreateWithImageInRect(image, pixels);
  if (crop == NULL) return NULL;
  unsigned char *data = calloc(width * height, 4);
  if (data == NULL) { CGImageRelease(crop); return NULL; }
  CGColorSpaceRef space = CGColorSpaceCreateWithName(kCGColorSpaceSRGB);
  CGContextRef context = CGBitmapContextCreate(data, width, height, 8, width * 4, space,
      kCGImageAlphaPremultipliedLast | kCGBitmapByteOrder32Big);
  CGColorSpaceRelease(space);
  if (context == NULL) { free(data); CGImageRelease(crop); return NULL; }
  CGContextDrawImage(context, CGRectMake(0, 0, width, height), crop);
  // A uniform surface or a gentle bilinear gradient. Every perimeter pixel
  // must agree with the model: textured/overlapping artwork is refused.
  double corners[4][3];
  const size_t offsets[4] = {0, (width-1)*4, (height-1)*width*4, (height*width-1)*4};
  for (int corner = 0; corner < 4; corner++)
    for (int c = 0; c < 3; c++) corners[corner][c] = data[offsets[corner]+c];
  BOOL safe = YES;
  size_t foreground = 0, interior = (width - 4) * (height - 4);
  for (size_t y = 0; y < height && safe; y++) {
    for (size_t x = 0; x < width; x++) {
      unsigned char *p = data + (y * width + x) * 4;
      BOOL edge = x < 2 || y < 2 || x >= width - 2 || y >= height - 2;
      double u = (double)x/(width-1), v = (double)y/(height-1), difference = 0;
      for (int c = 0; c < 3; c++) {
        double model = (1-v)*((1-u)*corners[0][c]+u*corners[1][c]) +
                       v*((1-u)*corners[2][c]+u*corners[3][c]);
        difference = MAX(difference, fabs(p[c] - model));
      }
      if (edge && (p[3] < 250 || difference > 12)) { safe = NO; break; }
      if (!edge && difference > 24) foreground++;
    }
  }
  safe = safe && foreground > interior / 100 && foreground < interior * 9 / 10;
  if (safe) {
    for (size_t y = 0; y < height; y++) {
      for (size_t x = 0; x < width; x++) {
        unsigned char *p = data + (y * width + x) * 4;
        double u = (double)x/(width-1), v = (double)y/(height-1);
        for (int c = 0; c < 3; c++) p[c] = (unsigned char)lrint(
            (1-v)*((1-u)*corners[0][c]+u*corners[1][c]) + v*((1-u)*corners[2][c]+u*corners[3][c]));
        p[3] = 255;
      }
    }
    *background = CGBitmapContextCreateImage(context);
    safe = *background != NULL;
  }
  CGContextRelease(context);
  free(data);
  if (!safe) { CGImageRelease(crop); return NULL; }
  return crop;
}
