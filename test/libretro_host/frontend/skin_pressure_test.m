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
static NSValue *BoxTestRect(CGRect r){return [NSValue valueWithBytes:&r objCType:@encode(CGRect)];}
static void IntensityAndSeparatedArms(void) {
  CHECK(LibretroSkinPressureIntensityFromIdentifier(nil)==2);
  CHECK(LibretroSkinPressureIntensityFromIdentifier(@99)==2);
  CHECK(LibretroSkinPressureIntensityFromIdentifier(@"invalid")==2);
  CGFloat lastDepth=0,lastCompression=0;
  for(NSUInteger level=0;level<4;level++) {
    CHECK(LibretroSkinPressureIntensityFromIdentifier(LibretroSkinPressureIntensityIdentifiers()[level])==level);
    LibretroSkinPressureProfile p=LibretroSkinPressureProfileForSize(CGSizeMake(48,48),level);
    CHECK(p.depth>lastDepth && p.compression>lastCompression && p.depth<=6);
    CHECK(LibretroSkinPressureProfileForSize(CGSizeMake(80,9),level).depth<=9*0.125);
    lastDepth=p.depth;lastCompression=p.compression;
  }
  CHECK(LibretroSkinPressureProfileForSize(CGSizeMake(NAN,50),2).depth==0);
  CHECK(LibretroSkinPressureReleaseTime(0)==0 && LibretroSkinPressureReleaseTime(1)==1);
  for(int i=1;i<=100;i++)CHECK(LibretroSkinPressureReleaseTime(i/100.0)>LibretroSkinPressureReleaseTime((i-1)/100.0));
  size_t w=120,h=110;
  NSMutableData *data=[NSMutableData dataWithLength:w*h*4];uint8_t *p=data.mutableBytes;
  CGRect expected[]={CGRectMake(50,5,20,31),CGRectMake(48,76,25,29),
    CGRectMake(8,45,30,20),CGRectMake(85,43,29,24)};
  for(size_t y=0;y<h;y++)for(size_t x=0;x<w;x++)for(int i=0;i<4;i++)
    if(CGRectContainsPoint(expected[i],CGPointMake(x+0.5,y+0.5))){size_t at=(y*w+x)*4;p[at]=180;p[at+1]=140;p[at+2]=80;p[at+3]=255;}
  CGImageRef arrows=Image(data,w,h);
  NSArray *regions=LibretroSkinPressureRegions(arrows,CGRectMake(0,0,w,h));
  CHECK(regions.count==4);
  for(int i=0;i<4;i++)CHECK(CGRectEqualToRect(LibretroSkinPressureRect(regions[i]),expected[i]));
  CGImageRelease(arrows);
  p[3]=255; // A fifth disconnected symbol is ambiguous, never a guessed arm.
  arrows=Image(data,w,h);regions=LibretroSkinPressureRegions(arrows,CGRectMake(0,0,w,h));
  for(int i=0;i<4;i++)CHECK(CGRectEqualToRect(LibretroSkinPressureRect(regions[i]),LibretroSkinPressureArm(CGSizeMake(w,h),i)));
  CGImageRelease(arrows);
  // Uniform material: the measured darkening is monotonic, not texture noise.
  for(size_t i=0;i<w*h;i++){p[i*4]=180;p[i*4+1]=120;p[i*4+2]=60;p[i*4+3]=255;}
  CGImageRef normal=Image(data,w,h);
  NSArray *blocked=@[BoxTestRect(CGRectMake(60,0,60,30))];
  double previous=0,light=0;
  for(NSUInteger level=0;level<4;level++) {
    NSArray *frames=LibretroSkinPressureFramesWithIntensity(normal,CGRectMake(0,0,w,h),0.5,0,NULL,blocked,12,level);
    CHECK(frames.count==12);
    CFDataRef bytes=CGDataProviderCopyData(CGImageGetDataProvider((__bridge CGImageRef)frames.lastObject));
    const uint8_t *q=CFDataGetBytePtr(bytes);double difference=0;BOOL untouched=YES,valid=YES;
    for(size_t y=0;y<h;y++)for(size_t x=0;x<w;x++) {
      size_t at=((y+1)*(w+2)+x+1)*4;difference+=180-q[at];
      if(x>=60 && y<30 && memcmp(q+at,p+(y*w+x)*4,4))untouched=NO;
      for(int c=0;c<3;c++)if(q[at+c]>q[at+3])valid=NO;
    }
    CHECK(untouched && valid && difference>previous);
    if(level==0)light=difference;
    if(level==2)CHECK(difference>light*1.7);
    previous=difference;CFRelease(bytes);
  }
  CGImageRelease(normal);
}
static void GeometryAndOverlap(void) {
  size_t w=120,h=100;
  NSMutableData *bytes=[NSMutableData dataWithLength:w*h*4];uint8_t *p=bytes.mutableBytes;
  for(size_t y=0;y<h;y++)for(size_t x=0;x<w;x++)
    if((x>=49 && x<75 && y>=10 && y<93)||(x>=9 && x<112 && y>=35 && y<54)){
      size_t i=(y*w+x)*4;p[i]=130;p[i+1]=100;p[i+2]=90;p[i+3]=255;
    }
  CGImageRef cross=Image(bytes,w,h);
  NSArray *regions=LibretroSkinPressureRegions(cross,CGRectMake(0,0,w,h));
  CGRect expected[]={CGRectMake(49,10,26,25),CGRectMake(49,54,26,39),CGRectMake(9,35,40,19),CGRectMake(75,35,37,19)};
  CHECK(regions.count==4);
  for(NSUInteger i=0;i<4;i++)CHECK(CGRectEqualToRect(LibretroSkinPressureRect(regions[i]),expected[i]));
  CGImageRelease(cross);
  // Opaque/textured pictures must not be mistaken for a silhouette.
  for(size_t y=0;y<h;y++)for(size_t x=0;x<w;x++){
    size_t i=(y*w+x)*4;p[i]=(x*11+y*3)%255;p[i+1]=(x+y*7)%255;p[i+2]=80;p[i+3]=255;
  }
  CGImageRef opaque=Image(bytes,w,h);
  regions=LibretroSkinPressureRegions(opaque,CGRectMake(0,0,w,h));
  for(NSUInteger i=0;i<4;i++)CHECK(CGRectEqualToRect(LibretroSkinPressureRect(regions[i]),LibretroSkinPressureArm(CGSizeMake(w,h),i)));
  CGRect whole=CGRectMake(10,10,80,70),block=CGRectMake(50,0,30,45);
  NSArray *excluded=@[BoxTestRect(block),BoxTestRect(CGRectMake(0,55,35,40))];
  NSArray *parts=LibretroSkinPressureVisibleRects(whole,excluded);
  double area=0;
  for(NSUInteger i=0;i<parts.count;i++){
    CGRect r=LibretroSkinPressureRect(parts[i]);area+=r.size.width*r.size.height;
    CHECK(CGRectContainsRect(whole,r));
    for(NSValue *e in excluded)CHECK(CGRectIsEmpty(CGRectIntersection(r,LibretroSkinPressureRect(e))));
    for(NSUInteger j=0;j<i;j++)CHECK(CGRectIsEmpty(CGRectIntersection(r,LibretroSkinPressureRect(parts[j]))));
  }
  CHECK(area==80*70-30*35-25*25);
  CHECK(LibretroSkinPressureVisibleRects(whole,@[BoxTestRect(whole)]).count==0);
  CHECK(LibretroSkinPressureVisibleRects(whole,@[BoxTestRect(CGRectMake(90,10,20,70))]).count==1);
  CHECK(LibretroSkinPressureVisibleRects(whole,@[BoxTestRect(CGRectMake(NAN,10,20,70))]).count==0);
  for(NSNumber *steps in @[@8,@12]){
    NSArray *frames=LibretroSkinPressureFramesExcluding(opaque,whole,0.5,0,NULL,excluded,steps.unsignedIntegerValue);
    CHECK(frames.count==steps.unsignedIntegerValue);
    BOOL unchanged=YES,changed=NO;
    for(id value in frames){
      CGImageRef image=(__bridge CGImageRef)value;
      CFDataRef data=CGDataProviderCopyData(CGImageGetDataProvider(image));const uint8_t *q=CFDataGetBytePtr(data);
      for(size_t y=0;y<70;y++)for(size_t x=0;x<80;x++){
        CGPoint at=CGPointMake(10+x+0.5,10+y+0.5);BOOL blocked=NO;
        for(NSValue *e in excluded)blocked|=CGRectContainsPoint(LibretroSkinPressureRect(e),at);
        BOOL differs=memcmp(q+((y+1)*82+x+1)*4,p+((y+10)*w+x+10)*4,4)!=0;
        if(blocked && differs)unchanged=NO;if(!blocked && differs)changed=YES;
      }
      CFRelease(data);
    }
    CHECK(unchanged);CHECK(changed);
  }
  CHECK(LibretroSkinPressureFramesExcluding(opaque,whole,1,0,NULL,@[],0).count==0);
  CGImageRelease(opaque);
}
int main(void) {
  @autoreleasepool {
    IntensityAndSeparatedArms();
    GeometryAndOverlap();
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
          CHECK(frames.count==LibretroSkinPressureFrameCount); if(frames.count!=LibretroSkinPressureFrameCount)continue;
          size_t aw=area.size.width, ah=area.size.height;
          BOOL restMatches=YES, borderFixed=YES, changed=NO, alphaValid=YES, authoredMatches=YES;
          for(NSUInteger step=0;step<LibretroSkinPressureFrameCount;step++){
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
              if(step==LibretroSkinPressureFrameCount-1 && memcmp(b+i,p+original,4))changed=YES;
              if(!authoredState && (x==0 || y==0 || x==aw-1 || y==ah-1) && memcmp(b+i,p+original,4))borderFixed=NO;
              for(int c=0;c<3;c++)if(b[i+c]>b[i+3])alphaValid=NO;
              if(authoredState && step==LibretroSkinPressureFrameCount-1 && memcmp(b+i,q+original,4))authoredMatches=NO;
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
