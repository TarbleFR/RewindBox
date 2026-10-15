#import "LibretroSkinPressure.h"
#include <math.h>
#include <stdlib.h>
#include <string.h>

const NSUInteger LibretroSkinPressureFrameCount = 12;

NSArray<NSString *> *LibretroSkinPressureIntensityIdentifiers(void) {
  return @[@"light", @"normal", @"pronounced", @"veryPronounced"];
}
NSUInteger LibretroSkinPressureIntensityFromIdentifier(id value) {
  NSUInteger index = [value isKindOfClass:NSString.class] ?
    [LibretroSkinPressureIntensityIdentifiers() indexOfObject:value] : NSNotFound;
  return index == NSNotFound ? 2 : index;
}
LibretroSkinPressureProfile LibretroSkinPressureProfileForSize(CGSize points, NSUInteger intensity) {
  if (intensity > 3) intensity = 2;
  static const double fractions[] = {0.045,0.07,0.10,0.125};
  static const double caps[] = {1.6,2.8,4.5,6.0};
  static const double compression[] = {0.035,0.05,0.075,0.095};
  static const double occlusion[] = {0.06,0.09,0.14,0.18};
  static const double duration[] = {0.12,0.15,0.18,0.20};
  double side = isfinite(points.width) && isfinite(points.height) ?
    fmax(0,fmin(points.width,points.height)) : 0;
  return (LibretroSkinPressureProfile){fmin(caps[intensity],side*fractions[intensity]),
    compression[intensity],occlusion[intensity],duration[intensity]};
}
double LibretroSkinPressureReleaseTime(double progress) {
  // Invert a critically damped return, normalised to finish exactly at rest.
  // Prepared key times only: no solver or pixel work during a touch callback.
  if (progress <= 0) return 0;
  if (progress >= 1) return 1;
  double lo=0,hi=1,normal=1-7*exp(-6);
  for (NSUInteger i=0;i<24;i++) {
    double t=(lo+hi)*0.5, value=(1-(1+6*t)*exp(-6*t))/normal;
    if (value<progress) lo=t; else hi=t;
  }
  return (lo+hi)*0.5;
}

static NSValue *BoxRect(CGRect rect) { return [NSValue valueWithBytes:&rect objCType:@encode(CGRect)]; }
CGRect LibretroSkinPressureRect(NSValue *value) {
  CGRect rect = CGRectNull;
  if ([value isKindOfClass:NSValue.class] && strcmp(value.objCType, @encode(CGRect)) == 0)
    [value getValue:&rect size:sizeof(rect)];
  return rect;
}
static BOOL ValidRect(CGRect r) {
  return isfinite(r.origin.x) && isfinite(r.origin.y) && isfinite(r.size.width) &&
    isfinite(r.size.height) && r.size.width > 0 && r.size.height > 0;
}

NSArray<NSValue *> *LibretroSkinPressureVisibleRects(CGRect rect, NSArray<NSValue *> *excluded) {
  if (!ValidRect(rect) || excluded.count > 64) return @[];
  NSMutableArray *parts = [NSMutableArray arrayWithObject:BoxRect(rect)];
  for (NSValue *value in excluded) {
    CGRect block = LibretroSkinPressureRect(value);
    if (!ValidRect(block)) return @[];
    NSMutableArray *next = [NSMutableArray array];
    for (NSValue *part in parts) {
      CGRect r = LibretroSkinPressureRect(part), cut = CGRectIntersection(r, block);
      if (CGRectIsNull(cut) || CGRectIsEmpty(cut)) { [next addObject:part]; continue; }
      CGRect pieces[] = {
        CGRectMake(r.origin.x, r.origin.y, r.size.width, cut.origin.y-r.origin.y),
        CGRectMake(r.origin.x, CGRectGetMaxY(cut), r.size.width, CGRectGetMaxY(r)-CGRectGetMaxY(cut)),
        CGRectMake(r.origin.x, cut.origin.y, cut.origin.x-r.origin.x, cut.size.height),
        CGRectMake(CGRectGetMaxX(cut), cut.origin.y, CGRectGetMaxX(r)-CGRectGetMaxX(cut), cut.size.height)};
      for (NSUInteger i=0;i<4;i++) if (!CGRectIsEmpty(pieces[i])) [next addObject:BoxRect(pieces[i])];
      if (next.count > 64) return @[];
    }
    parts = next;
  }
  return parts;
}

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

// Some monobloc textures contain four disconnected arrows, rather than a
// solid cross. Accept exactly four unambiguous cardinal components. Do not
// mistake diagonal decoration, a fifth symbol or a disc for a direction.
// This bounded flood fill runs once on the preparation queue (never touch).
static NSArray<NSValue *> *SeparatedArms(const uint8_t *p, size_t w, size_t h, CGPoint origin) {
  uint8_t *seen = calloc(w*h, 1);
  uint32_t *queue = malloc(w*h*sizeof(uint32_t));
  if (!seen || !queue) { free(seen); free(queue); return nil; }
  CGRect boxes[4]; size_t counts[4]; NSUInteger count = 0;
  BOOL valid = YES;
  for (size_t start=0; start<w*h && valid; start++) {
    if (seen[start] || p[start*4+3]<32) continue;
    if (count==4) { valid=NO; break; }
    size_t head=0, tail=1, left=w, right=0, top=h, bottom=0;
    queue[0]=(uint32_t)start; seen[start]=1;
    while (head<tail) {
      size_t at=queue[head++], x=at%w, y=at/w;
      left=MIN(left,x); right=MAX(right,x+1); top=MIN(top,y); bottom=MAX(bottom,y+1);
      for (size_t ny=y ? y-1 : 0; ny<=MIN(y+1,h-1); ny++)
        for (size_t nx=x ? x-1 : 0; nx<=MIN(x+1,w-1); nx++) {
          size_t next=ny*w+nx;
          if (!seen[next] && p[next*4+3]>=32) { seen[next]=1; queue[tail++]=(uint32_t)next; }
        }
    }
    boxes[count]=CGRectMake(left,top,right-left,bottom-top); counts[count]=tail; count++;
  }
  free(seen); free(queue);
  if (!valid || count!=4) return nil;
  NSUInteger slots[4]={0,0,0,0};
  for (NSUInteger i=1;i<4;i++) {
    if (CGRectGetMidY(boxes[i])<CGRectGetMidY(boxes[slots[0]])) slots[0]=i;
    if (CGRectGetMidY(boxes[i])>CGRectGetMidY(boxes[slots[1]])) slots[1]=i;
    if (CGRectGetMidX(boxes[i])<CGRectGetMidX(boxes[slots[2]])) slots[2]=i;
    if (CGRectGetMidX(boxes[i])>CGRectGetMidX(boxes[slots[3]])) slots[3]=i;
  }
  for (NSUInteger i=0;i<4;i++) {
    CGRect r=boxes[i];
    if (r.size.width<3 || r.size.height<3 || counts[i]<r.size.width*r.size.height*0.25) return nil;
    for (NSUInteger j=0;j<i;j++) if (slots[i]==slots[j]) return nil;
  }
  CGRect up=boxes[slots[0]], down=boxes[slots[1]], left=boxes[slots[2]], right=boxes[slots[3]];
  CGFloat x1=MAX(up.origin.x,down.origin.x), x2=MIN(CGRectGetMaxX(up),CGRectGetMaxX(down));
  CGFloat y1=MAX(left.origin.y,right.origin.y), y2=MIN(CGRectGetMaxY(left),CGRectGetMaxY(right));
  if (x2-x1<3 || y2-y1<3 || CGRectGetMaxY(up)>=y1 || down.origin.y<=y2 ||
      CGRectGetMaxX(left)>=x1 || right.origin.x<=x2) return nil;
  // Entire components, not just their centres, must lie in distinct arms.
  if (CGRectGetMaxY(up)>=MIN(left.origin.y,right.origin.y) ||
      down.origin.y<=MAX(CGRectGetMaxY(left),CGRectGetMaxY(right)) ||
      CGRectGetMaxX(left)>=MIN(up.origin.x,down.origin.x) ||
      right.origin.x<=MAX(CGRectGetMaxX(up),CGRectGetMaxX(down))) return nil;
  NSMutableArray *result=[NSMutableArray array];
  for (NSUInteger i=0;i<4;i++) [result addObject:BoxRect(CGRectOffset(boxes[slots[i]],origin.x,origin.y))];
  return result;
}

NSArray<NSValue *> *LibretroSkinPressureRegions(CGImageRef source, CGRect pixels) {
  if (!ValidRect(pixels)) return @[];
  NSMutableArray *fallback = [NSMutableArray array];
  for (NSUInteger slot=0;slot<4;slot++)
    [fallback addObject:BoxRect(CGRectOffset(LibretroSkinPressureArm(pixels.size, slot), pixels.origin.x, pixels.origin.y))];
  if (source == NULL || !ValidRect(pixels) || !CGRectEqualToRect(pixels, CGRectIntegral(pixels)) ||
      pixels.size.width < 12 || pixels.size.height < 12 || pixels.size.width*pixels.size.height > 1024*1024 ||
      !CGRectContainsRect(CGRectMake(0,0,CGImageGetWidth(source),CGImageGetHeight(source)), pixels)) return fallback;
  size_t w=pixels.size.width,h=pixels.size.height;
  NSMutableData *data=[NSMutableData dataWithLength:w*h*4];
  CGColorSpaceRef space=CGColorSpaceCreateWithName(kCGColorSpaceSRGB);
  BOOL read=ReadPixels(source,pixels,data.mutableBytes,w,h,space);CGColorSpaceRelease(space);
  if(!read)return fallback;
  const uint8_t *p=data.bytes;
  size_t left=w,top=h,right=0,bottom=0,count=0;
  for(size_t y=0;y<h;y++)for(size_t x=0;x<w;x++)if(p[(y*w+x)*4+3]>=32){
    left=MIN(left,x);right=MAX(right,x+1);top=MIN(top,y);bottom=MAX(bottom,y+1);count++;
  }
  if(count==0 || right-left<12 || bottom-top<12)return fallback;
  // A solid photograph cannot be four separated arrows. Avoid its flood
  // fill altogether; all recognition remains off the input/render thread.
  NSArray *separated=count<(right-left)*(bottom-top)*0.7 ? SeparatedArms(p,w,h,pixels.origin) : nil;
  if(separated!=nil)return separated;
  size_t bw=right-left,bh=bottom-top,x1=right,x2=left,y1=bottom,y2=top;
  for(size_t y=top;y<bottom;y++){
    size_t n=0;for(size_t x=left;x<right;x++)if(p[(y*w+x)*4+3]>=32)n++;
    if(n>=bw*0.75){y1=MIN(y1,y);y2=MAX(y2,y+1);}
  }
  for(size_t x=left;x<right;x++){
    size_t n=0;for(size_t y=top;y<bottom;y++)if(p[(y*w+x)*4+3]>=32)n++;
    if(n>=bh*0.75){x1=MIN(x1,x);x2=MAX(x2,x+1);}
  }
  // Only accept an actual cross with four separated tips and clear corners;
  // an opaque photograph, a disc or disconnected arrows is not a silhouette.
  if(x2<=x1 || y2<=y1 || x1-left<3 || right-x2<3 || y1-top<3 || bottom-y2<3 ||
     x2-x1<bw*0.12 || x2-x1>bw*0.6 || y2-y1<bh*0.12 || y2-y1>bh*0.6)return fallback;
  size_t outside=0,inside=0;
  for(size_t y=top;y<bottom;y++)for(size_t x=left;x<right;x++)if(p[(y*w+x)*4+3]>=32){
    if((x>=x1 && x<x2)||(y>=y1 && y<y2))inside++;else outside++;
  }
  size_t cross=(x2-x1)*bh+(y2-y1)*bw-(x2-x1)*(y2-y1);
  if(outside>count*0.025 || inside<cross*0.72)return fallback;
  CGRect areas[]={CGRectMake(x1,top,x2-x1,y1-top),CGRectMake(x1,y2,x2-x1,bottom-y2),
    CGRectMake(left,y1,x1-left,y2-y1),CGRectMake(x2,y1,right-x2,y2-y1)};
  NSMutableArray *regions=[NSMutableArray array];
  for(NSUInteger i=0;i<4;i++)[regions addObject:BoxRect(CGRectOffset(areas[i],pixels.origin.x,pixels.origin.y))];
  return regions;
}

NSArray *LibretroSkinPressureFrames(CGImageRef source, CGRect pixels,
    CGFloat pointsPerPixel, NSUInteger direction, CGImageRef authoredPressed) {
  return LibretroSkinPressureFramesExcluding(source,pixels,pointsPerPixel,direction,authoredPressed,@[],LibretroSkinPressureFrameCount);
}

NSArray *LibretroSkinPressureFramesExcluding(CGImageRef source, CGRect pixels,
    CGFloat pointsPerPixel, NSUInteger direction, CGImageRef authoredPressed, NSArray<NSValue *> *excluded, NSUInteger frameCount) {
  return LibretroSkinPressureFramesWithIntensity(source,pixels,pointsPerPixel,direction,authoredPressed,excluded,frameCount,0);
}

NSArray *LibretroSkinPressureFramesWithIntensity(CGImageRef source, CGRect pixels,
    CGFloat pointsPerPixel, NSUInteger direction, CGImageRef authoredPressed,
    NSArray<NSValue *> *excluded, NSUInteger frameCount, NSUInteger intensity) {
  if (intensity > 3) intensity = 2;
  if (source == NULL || !isfinite(pointsPerPixel) || pointsPerPixel <= 0 ||
      !isfinite(pixels.origin.x) || !isfinite(pixels.origin.y) ||
      !isfinite(pixels.size.width) || !isfinite(pixels.size.height) ||
      !CGRectEqualToRect(pixels, CGRectIntegral(pixels)) ||
      pixels.size.width < 3 || pixels.size.height < 3 ||
      pixels.size.width > 2048 || pixels.size.height > 2048 ||
      !CGRectContainsRect(CGRectMake(0, 0, CGImageGetWidth(source), CGImageGetHeight(source)), pixels)) return @[];
  if (excluded.count>64 || frameCount<2 || frameCount>LibretroSkinPressureFrameCount) return @[];
  for(NSValue *value in excluded)if(!ValidRect(LibretroSkinPressureRect(value)))return @[];
  size_t w = (size_t)pixels.size.width, h = (size_t)pixels.size.height, length = w*h*4;
  // Caller also enforces a per-renderer budget across controls.
  if (length > 4u*1024u*1024u) return @[];
  if (authoredPressed != NULL && (CGImageGetWidth(authoredPressed) != CGImageGetWidth(source) ||
      CGImageGetHeight(authoredPressed) != CGImageGetHeight(source))) return @[];
  // Keep a one-pixel sampling apron. Core Animation can then filter a
  // scaled patch against the same neighbouring pixels as the unsplit skin,
  // instead of clamping the crop's edge into a visible seam.
  size_t outputWidth = w+2, outputHeight = h+2, outputLength = outputWidth*outputHeight*4;
  CGRect apronRect = CGRectIntersection(CGRectInset(pixels, -1, -1),
      CGRectMake(0, 0, CGImageGetWidth(source), CGImageGetHeight(source)));
  size_t apronWidth = apronRect.size.width, apronHeight = apronRect.size.height;
  NSMutableData *apronData = [NSMutableData dataWithLength:apronWidth*apronHeight*4];
  uint8_t *normal = calloc(1, length), *pressed = authoredPressed ? calloc(1, length) : NULL;
  if (normal == NULL || (authoredPressed && pressed == NULL)) { free(normal); free(pressed); return @[]; }
  CGColorSpaceRef originalSpace = CGImageGetColorSpace(source);
  CGColorSpaceRef space = originalSpace != NULL && CGColorSpaceGetModel(originalSpace) == kCGColorSpaceModelRGB ?
      CGColorSpaceRetain(originalSpace) : CGColorSpaceCreateWithName(kCGColorSpaceSRGB);
  if (!ReadPixels(source, apronRect, apronData.mutableBytes, apronWidth, apronHeight, space) ||
      !ReadPixels(source, pixels, normal, w, h, space) ||
      (authoredPressed && !ReadPixels(authoredPressed, pixels, pressed, w, h, space))) {
    CGColorSpaceRelease(space); free(normal); free(pressed); return @[];
  }
  NSMutableArray *frames = [NSMutableArray arrayWithCapacity:frameCount];
  // Limit displacement relative to the smaller side too: the mapping stays
  // monotonic even for thin Start/Select keys. No fold or edge extrapolation.
  LibretroSkinPressureProfile profile = LibretroSkinPressureProfileForSize(
      CGSizeMake(w*pointsPerPixel,h*pointsPerPixel),intensity);
  double depth = profile.depth/pointsPerPixel;
  // An authored endpoint already includes its own relief: retain its colour
  // and texture, adding only a smaller local depression at stronger settings.
  double authoredDepth = intensity == 0 ? 0 : 0.35;
  // Compute shared-area falloff once, not once per release frame. Taper far
  // enough that inverse sampling cannot borrow pixels across a blocked edge.
  NSMutableData *supports=excluded.count ? [NSMutableData dataWithLength:w*h*sizeof(float)] : nil;
  float *support=supports.mutableBytes;
  CGRect blocks[64];for(NSUInteger i=0;i<excluded.count;i++)blocks[i]=LibretroSkinPressureRect(excluded[i]);
  double feather=MAX(4/pointsPerPixel,3*(profile.compression*MAX(w,h)+depth));
  if(support!=NULL)for(size_t y=0;y<h;y++)for(size_t x=0;x<w;x++){
    double factor=1,px=pixels.origin.x+x+0.5,py=pixels.origin.y+y+0.5;
    for(NSUInteger i=0;i<excluded.count;i++){
      CGRect r=blocks[i];
      double dx=fmax(0,fmax(r.origin.x-px,px-CGRectGetMaxX(r)));
      double dy=fmax(0,fmax(r.origin.y-py,py-CGRectGetMaxY(r)));
      double t=fmin(1,hypot(dx,dy)/feather);factor=fmin(factor,t*t*(3-2*t));
    }
    support[y*w+x]=factor;
  }
  // Column/row factors are shared by all twelve frames.
  double *horizontal=calloc(w,sizeof(double)),*vertical=calloc(h,sizeof(double));
  if(!horizontal || !vertical){free(horizontal);free(vertical);free(normal);free(pressed);CGColorSpaceRelease(space);return @[];}
  for(size_t x=0;x<w;x++)horizontal[x]=Weight((2.0*x/(w-1)-1)*((direction==1 || direction==2)?1.5:1));
  for(size_t y=0;y<h;y++)vertical[y]=Weight(2.0*y/(h-1)-1);
  for (NSUInteger step = 0; step < frameCount; step++) {
    double amount = (double)step / (frameCount-1);
    NSMutableData *data = [NSMutableData dataWithLength:length];
    uint8_t *out = data.mutableBytes;
    if (step == 0) {
      memcpy(out, normal, length);
    } else for (size_t y = 0; y < h; y++) for (size_t x = 0; x < w; x++) {
      size_t offset = (y*w+x)*4;
      // For the broad upper/lower regions, don't bend the housing in the
      // corners alongside a cross. Other arms never share this support.
      double permitted = support != NULL ? support[y*w+x] : 1;
      double weight = horizontal[x] * vertical[y] * permitted;
      if (pressed != NULL && intensity == 0) {
        // Authored states have their own edges/shadows: preserve those
        // pixels, including alpha, instead of adding a lighting effect.
        double local=amount*permitted;
        for (size_t c = 0; c < 4; c++)
          out[offset+c] = (uint8_t)lround(normal[offset+c]*(1-local) + pressed[offset+c]*local);
        continue;
      }
      if (weight == 0 && pressed == NULL) { memcpy(out+offset, normal+offset, 4); continue; }
      // Inverse sampling: a slight contraction and downward depression,
      // smoothly anchored to the untouched image at the region boundary.
      double dx = (x-(w-1)*0.5)*profile.compression;
      double dy = (y-(h-1)*0.5)*profile.compression - depth;
      if (pressed != NULL) { dx*=authoredDepth; dy*=authoredDepth; }
      double sx = fmax(0, fmin(w-1, x + dx*weight*amount));
      double sy = fmax(0, fmin(h-1, y + dy*weight*amount));
      size_t x0 = (size_t)sx, y0 = (size_t)sy, x1 = MIN(x0+1,w-1), y1 = MIN(y0+1,h-1);
      double fx = sx-x0, fy = sy-y0;
      for (size_t c = 0; c < 4; c++) {
        const uint8_t *texture = pressed ?: normal;
        double top = texture[(y0*w+x0)*4+c]*(1-fx)+texture[(y0*w+x1)*4+c]*fx;
        double bottom = texture[(y1*w+x0)*4+c]*(1-fx)+texture[(y1*w+x1)*4+c]*fx;
        // Subtle occlusion also makes a featureless solid-colour arm read
        // as depressed. Preserve its hue and alpha; never add a glow.
        double shade = c == 3 || pressed != NULL ? 1 : 1 - profile.occlusion*weight*amount;
        double sample = (top*(1-fy)+bottom*fy)*shade;
        if (pressed != NULL) sample=normal[offset+c]*(1-amount*permitted)+sample*amount*permitted;
        out[offset+c] = (uint8_t)lround(sample);
      }
    }
    NSMutableData *padded = [NSMutableData dataWithLength:outputLength];
    uint8_t *destination = padded.mutableBytes;
    const uint8_t *apron = apronData.bytes;
    for (size_t y=0; y<outputHeight; y++) for (size_t x=0; x<outputWidth; x++) {
      if (x>0 && x<=w && y>0 && y<=h) {
        memcpy(destination+(y*outputWidth+x)*4, out+((y-1)*w+x-1)*4, 4);
      } else {
        size_t ax = (size_t)fmax(0, fmin(apronWidth-1, pixels.origin.x-apronRect.origin.x+(double)x-1));
        size_t ay = (size_t)fmax(0, fmin(apronHeight-1, pixels.origin.y-apronRect.origin.y+(double)y-1));
        memcpy(destination+(y*outputWidth+x)*4, apron+(ay*apronWidth+ax)*4, 4);
      }
    }
    CGDataProviderRef provider = CGDataProviderCreateWithCFData((__bridge CFDataRef)padded);
    CGImageRef image = CGImageCreate(outputWidth, outputHeight, 8, 32, outputWidth*4, space,
        kCGImageAlphaPremultipliedLast | kCGBitmapByteOrder32Big, provider, NULL, true, kCGRenderingIntentDefault);
    CGDataProviderRelease(provider);
    if (image != NULL) { [frames addObject:(__bridge id)image]; CGImageRelease(image); }
  }
  CGColorSpaceRelease(space);
  free(normal); free(pressed);
  free(horizontal);free(vertical);
  return frames.count == frameCount ? frames : @[];
}
