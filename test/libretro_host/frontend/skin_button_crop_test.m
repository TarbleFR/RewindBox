#import <Foundation/Foundation.h>
#import "LibretroSkinButtonCrop.h"
#include <stdio.h>
#include <math.h>
static int failures;
#define CHECK(v) do { if (!(v)) { printf("FAIL line %d\n", __LINE__); failures++; } } while (0)
int main(void) {
  @autoreleasepool {
    unsigned char pixels[96*96*4];
    for (int y=0;y<96;y++) for (int x=0;x<96;x++) {
      unsigned char *p=pixels+(y*96+x)*4;
      p[0]=100+x/3; p[1]=110+y/3; p[2]=120; p[3]=255;
      if ((x-48)*(x-48)+(y-48)*(y-48)<32*32) {p[0]=220;p[1]=20;p[2]=30;}
    }
    CGColorSpaceRef space=CGColorSpaceCreateDeviceRGB();
    CGContextRef context=CGBitmapContextCreate(pixels,96,96,8,96*4,space,kCGImageAlphaPremultipliedLast|kCGBitmapByteOrder32Big);
    CGImageRef image=CGBitmapContextCreateImage(context), fill=NULL;
    CGImageRef crop=LibretroSkinCreateButtonCrop(image,CGRectMake(6,6,84,84),&fill);
    CHECK(crop!=NULL && fill!=NULL && CGImageGetWidth(crop)==84);
    if(crop)CGImageRelease(crop); if(fill)CGImageRelease(fill); CGImageRelease(image);
    // Artwork crossing the perimeter must remain static, not be patched.
    for(int y=0;y<96;y++) pixels[(y*96+6)*4]=255;
    image=CGBitmapContextCreateImage(context);
    crop=LibretroSkinCreateButtonCrop(image,CGRectMake(6,6,84,84),&fill);
    CHECK(crop==NULL && fill==NULL); CGImageRelease(image);
    CHECK(LibretroSkinCreateButtonCrop(NULL,CGRectZero,&fill)==NULL);
    image=CGBitmapContextCreateImage(context);
    CHECK(LibretroSkinCreateButtonCrop(image,CGRectMake(-1,0,30,30),&fill)==NULL);
    CHECK(LibretroSkinCreateButtonCrop(image,CGRectMake(0,0,INFINITY,30),&fill)==NULL);
    CGImageRelease(image); CGContextRelease(context); CGColorSpaceRelease(space);
  }
  printf("Button extraction: %s\n", failures ? "FAILED" : "passed");
  return failures ? 1 : 0;
}
