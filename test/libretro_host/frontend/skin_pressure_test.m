// Pixel tests of the production pressure preparation, independent of UIKit.
#import "LibretroSkinPressure.h"
#include <math.h>
#include <stdio.h>
#include <string.h>
static int failures, checks;
#define CHECK(v) do { checks++; if (!(v)) { printf("FAIL line %d\n",__LINE__); failures++; } } while (0)
static CGImageRef Image(NSData *data, size_t w, size_t h) {
  CGColorSpaceRef space=CGColorSpaceCreateDeviceRGB();
  CGDataProviderRef provider=CGDataProviderCreateWithCFData((__bridge CFDataRef)data);
  CGImageRef image=CGImageCreate(w,h,8,32,w*4,space,kCGImageAlphaPremultipliedLast|kCGBitmapByteOrder32Big,provider,NULL,false,kCGRenderingIntentDefault);
  CGDataProviderRelease(provider);CGColorSpaceRelease(space);return image;
}
int main(void) {
  @autoreleasepool {
    for (NSNumber *scale in @[@1,@2,@3]) {
      size_t w=93*scale.unsignedIntegerValue, h=117*scale.unsignedIntegerValue;
      NSMutableData *source=[NSMutableData dataWithLength:w*h*4]; uint8_t *p=source.mutableBytes;
      for(size_t y=0;y<h;y++)for(size_t x=0;x<w;x++){
        size_t i=(y*w+x)*4; uint8_t a=(x+y)%2 ? 160 : 255;
        p[i]=(x*13+y*7)%a;p[i+1]=(x*3+y*17)%a;p[i+2]=(x+y*3)%a;p[i+3]=a;
      }
      CGImageRef normal=Image(source,w,h);
      NSMutableData *pressed=[source mutableCopy]; uint8_t *q=pressed.mutableBytes;
      for(size_t i=0;i<w*h*4;i+=4){q[i]/=2;q[i+1]/=2;q[i+2]/=2;q[i+3]/=2;}
      CGImageRef authored=Image(pressed,w,h);
      for(NSUInteger slot=0;slot<5;slot++) {
        CGRect area=slot<4 ? LibretroSkinPressureArm(CGSizeMake(w,h),slot) : CGRectMake(7,9,w-14,h-18);
        if(slot<4){
          CHECK(!CGRectContainsPoint(area,CGPointMake(w/2,h/2)));
          for(NSUInteger other=0;other<4;other++)if(other!=slot)
            CHECK(!CGRectIntersectsRect(area,LibretroSkinPressureArm(CGSizeMake(w,h),other)));
        }
        for(NSUInteger authoredState=0;authoredState<2;authoredState++){
          NSArray *frames=LibretroSkinPressureFrames(normal,area,1.0/scale.doubleValue,slot<4 ? 1u<<slot : 0,authoredState ? authored : NULL);
          CHECK(frames.count==8); if(frames.count!=8)continue;
          size_t aw=area.size.width, ah=area.size.height;
          BOOL restMatches=YES, borderFixed=YES, changed=NO, alphaValid=YES, authoredMatches=YES;
          for(NSUInteger step=0;step<8;step++){
            CGImageRef frame=(__bridge CGImageRef)frames[step];
            CHECK(CGImageGetWidth(frame)==aw+2 && CGImageGetHeight(frame)==ah+2);
            CFDataRef bytes=CGDataProviderCopyData(CGImageGetDataProvider(frame));
            const uint8_t *b=CFDataGetBytePtr(bytes);
            BOOL apronMatches=YES;
            for(size_t y=0;y<ah+2;y++)for(size_t x=0;x<aw+2;x++)if(x==0 || y==0 || x==aw+1 || y==ah+1){
              size_t sx=(size_t)fmax(0,fmin(w-1,area.origin.x+(double)x-1));
              size_t sy=(size_t)fmax(0,fmin(h-1,area.origin.y+(double)y-1));
              if(memcmp(b+(y*(aw+2)+x)*4,p+(sy*w+sx)*4,4))apronMatches=NO;
            }
            CHECK(apronMatches);
            for(size_t y=0;y<ah;y++)for(size_t x=0;x<aw;x++){
              size_t original=(((size_t)area.origin.y+y)*w+(size_t)area.origin.x+x)*4;
              size_t i=((y+1)*(aw+2)+x+1)*4;
              if(step==0 && memcmp(b+i,p+original,4))restMatches=NO;
              if(step==7 && memcmp(b+i,p+original,4))changed=YES;
              if(!authoredState && (x==0 || y==0 || x==aw-1 || y==ah-1) && memcmp(b+i,p+original,4))borderFixed=NO;
              for(int c=0;c<3;c++)if(b[i+c]>b[i+3])alphaValid=NO;
              if(authoredState && step==7 && memcmp(b+i,q+original,4))authoredMatches=NO;
            }
            CFRelease(bytes);
          }
          CHECK(restMatches); CHECK(borderFixed); CHECK(changed); CHECK(alphaValid); CHECK(authoredMatches);
        }
      }
      CHECK(LibretroSkinPressureFrames(normal,CGRectMake(-1,0,20,20),1,0,NULL).count==0);
      CHECK(LibretroSkinPressureFrames(normal,CGRectMake(0,0,INFINITY,20),1,0,NULL).count==0);
      CHECK(LibretroSkinPressureFrames(normal,CGRectMake(0.5,0,20,20),1,0,NULL).count==0);
      CHECK(LibretroSkinPressureFrames(normal,CGRectMake(0,0,20,20),NAN,0,NULL).count==0);
      CGImageRelease(normal);CGImageRelease(authored);
    }
  }
  printf("Pressure pixels: %d checks, %d failures\n",checks,failures);return failures ? 1 : 0;
}
