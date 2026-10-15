#import "LibretroSkinRenderer.h"
#import "LibretroSkinButtonCrop.h"
#import "LibretroSkinPressure.h"

#import <CommonCrypto/CommonDigest.h>
#import <CoreGraphics/CoreGraphics.h>
#import <ImageIO/ImageIO.h>
#import <QuartzCore/QuartzCore.h>

#include <math.h>
#include <string.h>
#include <sys/stat.h>

/// Memory cache budget of rasterised skin images (bytes).
static const NSUInteger LibretroSkinCacheCostLimit = 96u * 1024u * 1024u;
/// Longest side of a rasterised image, in pixels.
static const double LibretroSkinMaximumPixels = 4096.0;
/// KVC key holding the cache key of the image a layer waits for or shows.
static NSString *const LibretroSkinImageKey = @"neostationSkinImageKey";

typedef NS_ENUM(NSInteger, LibretroSkinImageKind) {
  LibretroSkinImageKindNone = 0,
  LibretroSkinImageKindBitmap,  // PNG or JPEG
  LibretroSkinImageKindPDF,
};

#pragma mark - Shared image pipeline

/// Private serial queue: decoding, rasterising and the disk cache.
static dispatch_queue_t LibretroSkinQueue(void) {
  static dispatch_queue_t queue;
  static dispatch_once_t once;
  dispatch_once(&once, ^{
    dispatch_queue_attr_t attributes =
        dispatch_queue_attr_make_with_qos_class(DISPATCH_QUEUE_SERIAL, QOS_CLASS_USER_INITIATED, 0);
    queue = dispatch_queue_create("neostation.libretro.skin-images", attributes);
  });
  return queue;
}

static NSCache<NSString *, UIImage *> *LibretroSkinMemoryCache(void) {
  static NSCache<NSString *, UIImage *> *cache;
  static dispatch_once_t once;
  dispatch_once(&once, ^{
    cache = [[NSCache alloc] init];
    cache.name = @"neostation.libretro.skin-images";
    cache.totalCostLimit = LibretroSkinCacheCostLimit;
  });
  return cache;
}

static NSString *LibretroSkinCacheFolder(NSString *cacheDirectory) {
  if (cacheDirectory.length == 0) return nil;
  return [cacheDirectory stringByAppendingPathComponent:@"SkinCache"];
}

/// Image type from the first bytes (never from the name).
static LibretroSkinImageKind LibretroSkinImageKindAtPath(NSString *path) {
  if (path.length == 0) return LibretroSkinImageKindNone;
  NSData *data = [NSData dataWithContentsOfFile:path options:NSDataReadingMappedIfSafe error:nil];
  if (data.length < 4) return LibretroSkinImageKindNone;
  const uint8_t *bytes = data.bytes;
  static const uint8_t png[8] = {0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A};
  if (data.length >= 8 && memcmp(bytes, png, 8) == 0) return LibretroSkinImageKindBitmap;
  if (bytes[0] == 0xFF && bytes[1] == 0xD8 && bytes[2] == 0xFF) return LibretroSkinImageKindBitmap;
  // The PDF header may follow a few bytes of junk (PDF 1.7, 7.5.2).
  NSUInteger limit = MIN(data.length, (NSUInteger)1024);
  for (NSUInteger offset = 0; offset + 5 <= limit; offset++) {
    if (memcmp(bytes + offset, "%PDF-", 5) == 0) return LibretroSkinImageKindPDF;
  }
  return LibretroSkinImageKindNone;
}

/// Pixel size for `points` at `scale`, capped to LibretroSkinMaximumPixels.
static BOOL LibretroSkinPixelSize(CGSize points, CGFloat scale, size_t *width, size_t *height) {
  if (!(points.width > 0) || !(points.height > 0) || !isfinite(points.width) || !isfinite(points.height)) return NO;
  double factor = scale > 0 && isfinite(scale) ? scale : 1;
  double w = ceil(points.width * factor), h = ceil(points.height * factor);
  double longest = MAX(w, h);
  if (longest > LibretroSkinMaximumPixels) {
    double shrink = LibretroSkinMaximumPixels / longest;
    w = floor(w * shrink);
    h = floor(h * shrink);
  }
  *width = (size_t)MAX(w, 1.0);
  *height = (size_t)MAX(h, 1.0);
  return YES;
}

/// Cache key: hash of the image path, its modification date and size, and
/// the pixel size it is rasterised at.
static NSString *LibretroSkinCacheKey(NSString *path, size_t width, size_t height) {
  NSString *standardized = path.stringByStandardizingPath;
  long long modified = 0, length = 0;
  if (standardized.length > 0) {
    struct stat info;
    if (stat(standardized.fileSystemRepresentation, &info) == 0) {
      modified = (long long)info.st_mtimespec.tv_sec * 1000LL + (long long)info.st_mtimespec.tv_nsec / 1000000LL;
      length = (long long)info.st_size;
    }
  }
  NSString *source = [NSString stringWithFormat:@"%@|%lld|%lld|%zux%zu", standardized, modified, length, width, height];
  NSData *data = [source dataUsingEncoding:NSUTF8StringEncoding];
  unsigned char digest[CC_SHA256_DIGEST_LENGTH];
  CC_SHA256(data.bytes, (CC_LONG)data.length, digest);
  NSMutableString *hex = [NSMutableString stringWithCapacity:40];
  for (int index = 0; index < 20; index++) [hex appendFormat:@"%02x", digest[index]];
  return hex;
}

/// PNG / JPEG downsampled by ImageIO, or page 1 of a PDF drawn into a
/// bitmap of exactly `width` x `height` pixels. +1 image, NULL on failure.
static CGImageRef LibretroSkinCreateRaster(NSString *path, size_t width, size_t height) CF_RETURNS_RETAINED;
static CGImageRef LibretroSkinCreateRaster(NSString *path, size_t width, size_t height) {
  LibretroSkinImageKind kind = LibretroSkinImageKindAtPath(path);
  if (kind == LibretroSkinImageKindNone || width == 0 || height == 0) return NULL;
  NSURL *url = [NSURL fileURLWithPath:path];
  if (kind == LibretroSkinImageKindBitmap) {
    NSDictionary *sourceOptions = @{(__bridge NSString *)kCGImageSourceShouldCache : @NO};
    CGImageSourceRef source = CGImageSourceCreateWithURL((__bridge CFURLRef)url, (__bridge CFDictionaryRef)sourceOptions);
    if (source == NULL) return NULL;
    NSDictionary *options = @{
      (__bridge NSString *)kCGImageSourceCreateThumbnailFromImageAlways : @YES,
      (__bridge NSString *)kCGImageSourceCreateThumbnailWithTransform : @YES,
      (__bridge NSString *)kCGImageSourceShouldCacheImmediately : @YES,
      (__bridge NSString *)kCGImageSourceThumbnailMaxPixelSize : @(MAX(width, height)),
    };
    CGImageRef image = CGImageSourceCreateThumbnailAtIndex(source, 0, (__bridge CFDictionaryRef)options);
    CFRelease(source);
    return image;
  }

  // PDF: one CGPDFDocument per render (CoreGraphics documents are not
  // shared between threads).
  CGPDFDocumentRef document = CGPDFDocumentCreateWithURL((__bridge CFURLRef)url);
  if (document == NULL) return NULL;
  CGPDFPageRef page = CGPDFDocumentGetPage(document, 1);
  if (page == NULL) {
    CGPDFDocumentRelease(document);
    return NULL;
  }
  CGRect box = CGPDFPageGetBoxRect(page, kCGPDFCropBox);
  int angle = CGPDFPageGetRotationAngle(page);
  CGSize pageSize = (abs(angle) % 180) == 90 ? CGSizeMake(box.size.height, box.size.width) : box.size;
  if (!(pageSize.width > 0) || !(pageSize.height > 0)) {
    CGPDFDocumentRelease(document);
    return NULL;
  }
  CGColorSpaceRef space = CGColorSpaceCreateWithName(kCGColorSpaceSRGB);
  CGContextRef context =
      CGBitmapContextCreate(NULL, width, height, 8, 0, space,
                            (CGBitmapInfo)kCGImageAlphaPremultipliedFirst | (CGBitmapInfo)kCGBitmapByteOrder32Little);
  CGColorSpaceRelease(space);
  if (context == NULL) {
    CGPDFDocumentRelease(document);
    return NULL;
  }
  CGContextClearRect(context, CGRectMake(0, 0, (CGFloat)width, (CGFloat)height));
  CGContextSetInterpolationQuality(context, kCGInterpolationHigh);
  // The drawing transform never scales up: map the page at its own size
  // (rotation and origin), then scale to the requested pixels.
  CGContextScaleCTM(context, (CGFloat)width / pageSize.width, (CGFloat)height / pageSize.height);
  CGAffineTransform transform = CGPDFPageGetDrawingTransform(
      page, kCGPDFCropBox, CGRectMake(0, 0, pageSize.width, pageSize.height), 0, true);
  CGContextConcatCTM(context, transform);
  CGContextDrawPDFPage(context, page);
  CGImageRef image = CGBitmapContextCreateImage(context);
  CGContextRelease(context);
  CGPDFDocumentRelease(document);
  return image;
}

static CGImageRef LibretroSkinCreateFromDisk(NSString *file) CF_RETURNS_RETAINED;
static CGImageRef LibretroSkinCreateFromDisk(NSString *file) {
  if (file == nil || ![[NSFileManager defaultManager] fileExistsAtPath:file]) return NULL;
  CGImageSourceRef source = CGImageSourceCreateWithURL((__bridge CFURLRef)[NSURL fileURLWithPath:file], NULL);
  if (source == NULL) return NULL;
  NSDictionary *options = @{(__bridge NSString *)kCGImageSourceShouldCacheImmediately : @YES};
  CGImageRef image = NULL;
  if (CGImageSourceGetCount(source) > 0) {
    image = CGImageSourceCreateImageAtIndex(source, 0, (__bridge CFDictionaryRef)options);
  }
  CFRelease(source);
  return image;
}

/// <key>.png plus <key>.source (the standardized image path) so a skin's
/// entries can be found again by purgeCacheForSkinDirectory.
static void LibretroSkinWriteToDisk(CGImageRef image, NSString *file, NSString *sourcePath) {
  NSString *folder = file.stringByDeletingLastPathComponent;
  [[NSFileManager defaultManager] createDirectoryAtPath:folder withIntermediateDirectories:YES attributes:nil error:nil];
  CGImageDestinationRef destination =
      CGImageDestinationCreateWithURL((__bridge CFURLRef)[NSURL fileURLWithPath:file], CFSTR("public.png"), 1, NULL);
  if (destination == NULL) return;
  CGImageDestinationAddImage(destination, image, NULL);
  BOOL written = CGImageDestinationFinalize(destination);
  CFRelease(destination);
  if (!written) {
    [[NSFileManager defaultManager] removeItemAtPath:file error:nil];
    return;
  }
  NSString *sidecar = [file.stringByDeletingPathExtension stringByAppendingPathExtension:@"source"];
  [sourcePath.stringByStandardizingPath writeToFile:sidecar atomically:YES encoding:NSUTF8StringEncoding error:nil];
}

/// Removes cache entries whose source image is gone (deleted skin, or an
/// app container moved by an update). Once per cache folder and launch;
/// runs on the skin queue.
static void LibretroSkinPruneOnce(NSString *folder) {
  static NSMutableSet<NSString *> *pruned;
  if (folder == nil) return;
  if (pruned == nil) pruned = [NSMutableSet set];
  if ([pruned containsObject:folder]) return;
  [pruned addObject:folder];
  NSFileManager *manager = [NSFileManager defaultManager];
  for (NSString *name in [manager contentsOfDirectoryAtPath:folder error:nil]) {
    if (![name.pathExtension isEqualToString:@"source"]) continue;
    NSString *sidecar = [folder stringByAppendingPathComponent:name];
    NSString *source = [NSString stringWithContentsOfFile:sidecar encoding:NSUTF8StringEncoding error:nil];
    if (source.length > 0 && [manager fileExistsAtPath:source]) continue;
    [manager removeItemAtPath:sidecar error:nil];
    NSString *png = [sidecar.stringByDeletingPathExtension stringByAppendingPathExtension:@"png"];
    [manager removeItemAtPath:png error:nil];
  }
}

/// Memory cache, then disk cache, then rasterisation. Skin queue only.
static UIImage *LibretroSkinLoadImage(NSString *path, size_t width, size_t height, NSString *key,
                                      NSString *cacheDirectory) {
  NSCache<NSString *, UIImage *> *memory = LibretroSkinMemoryCache();
  UIImage *cached = [memory objectForKey:key];
  if (cached != nil) return cached;
  UIImage *result = nil;
  @autoreleasepool {
    NSString *folder = LibretroSkinCacheFolder(cacheDirectory);
    LibretroSkinPruneOnce(folder);
    NSString *file = folder != nil ? [folder stringByAppendingPathComponent:[key stringByAppendingPathExtension:@"png"]]
                                   : nil;
    CGImageRef image = LibretroSkinCreateFromDisk(file);
    if (image == NULL) {
      image = LibretroSkinCreateRaster(path, width, height);
      if (image != NULL && file != nil) LibretroSkinWriteToDisk(image, file, path);
    }
    if (image != NULL) {
      result = [UIImage imageWithCGImage:image];
      NSUInteger cost = CGImageGetBytesPerRow(image) * CGImageGetHeight(image);
      CGImageRelease(image);
      [memory setObject:result forKey:key cost:cost];
    }
  }
  return result;
}

#pragma mark - Geometry and style

static CGRect LibretroSkinCGRect(LibretroRect rect) {
  if (!isfinite(rect.x) || !isfinite(rect.y) || !isfinite(rect.w) || !isfinite(rect.h) || rect.w < 0 || rect.h < 0) {
    return CGRectZero;
  }
  return CGRectMake(rect.x, rect.y, rect.w, rect.h);
}

static UIColor *LibretroSkinColor(uint32_t argb) {
  return [UIColor colorWithRed:((argb >> 16) & 0xFF) / 255.0
                         green:((argb >> 8) & 0xFF) / 255.0
                          blue:(argb & 0xFF) / 255.0
                         alpha:((argb >> 24) & 0xFF) / 255.0];
}

/// `argb` mixed with white by `amount` (0-1), alpha kept.
static UIColor *LibretroSkinLighterColor(uint32_t argb, CGFloat amount) {
  CGFloat red = ((argb >> 16) & 0xFF) / 255.0, green = ((argb >> 8) & 0xFF) / 255.0, blue = (argb & 0xFF) / 255.0;
  return [UIColor colorWithRed:red + (1 - red) * amount
                         green:green + (1 - green) * amount
                          blue:blue + (1 - blue) * amount
                         alpha:((argb >> 24) & 0xFF) / 255.0];
}

static void LibretroSkinAddRoundedRect(CGMutablePathRef path, CGRect rect, CGFloat radius) {
  if (!(rect.size.width > 0) || !(rect.size.height > 0)) return;
  // CGPathAddRoundedRect asserts when a radius exceeds half a side.
  CGFloat limit = MIN(rect.size.width, rect.size.height) / 2;
  CGFloat corner = MAX(0, MIN(radius, limit));
  if (corner <= 0) {
    CGPathAddRect(path, NULL, rect);
  } else {
    CGPathAddRoundedRect(path, NULL, rect, corner, corner);
  }
}

/// Outline of a default-skin control in its own coordinates. +1 path.
static CGPathRef LibretroSkinCreateShapePath(LibretroSkinItemShape shape, CGSize size) CF_RETURNS_RETAINED;
static CGPathRef LibretroSkinCreateShapePath(LibretroSkinItemShape shape, CGSize size) {
  CGMutablePathRef path = CGPathCreateMutable();
  CGRect rect = CGRectMake(0, 0, size.width, size.height);
  if (!(size.width > 0) || !(size.height > 0)) return path;
  switch (shape) {
    case LibretroSkinItemShapeCircle:
    case LibretroSkinItemShapeStick:
      CGPathAddEllipseInRect(path, NULL, rect);
      break;
    case LibretroSkinItemShapePill:
      LibretroSkinAddRoundedRect(path, rect, size.height / 2);
      break;
    case LibretroSkinItemShapeRounded:
      LibretroSkinAddRoundedRect(path, rect, MIN(size.width, size.height) * 0.3);
      break;
    case LibretroSkinItemShapeDPad: {
      // Cross: two arms of a third of the size (non-zero winding: union).
      CGFloat armWidth = size.width / 3, armHeight = size.height / 3;
      CGFloat radius = MIN(armWidth, armHeight) * 0.2;
      LibretroSkinAddRoundedRect(path, CGRectMake(0, (size.height - armHeight) / 2, size.width, armHeight), radius);
      LibretroSkinAddRoundedRect(path, CGRectMake((size.width - armWidth) / 2, 0, armWidth, size.height), radius);
      break;
    }
    case LibretroSkinItemShapeNone:
      LibretroSkinAddRoundedRect(path, rect, MIN(size.width, size.height) / 2);
      break;
  }
  return path;
}

/// Four direction arrows of the D-pad cross. +1 path.
static CGPathRef LibretroSkinCreateArrowsPath(CGSize size) CF_RETURNS_RETAINED;
static CGPathRef LibretroSkinCreateArrowsPath(CGSize size) {
  CGMutablePathRef path = CGPathCreateMutable();
  if (!(size.width > 0) || !(size.height > 0)) return path;
  CGFloat arm = MIN(size.width, size.height) / 3;
  CGFloat half = arm * 0.2;
  CGFloat cx = size.width / 2, cy = size.height / 2;
  // Each arrow sits in the middle of its arm end, pointing outward.
  CGPoint tips[4] = {
      {cx, arm * 0.5 - half},
      {cx, size.height - arm * 0.5 + half},
      {arm * 0.5 - half, cy},
      {size.width - arm * 0.5 + half, cy},
  };
  CGFloat directions[4][2] = {{0, -1}, {0, 1}, {-1, 0}, {1, 0}};
  for (int index = 0; index < 4; index++) {
    CGFloat dx = directions[index][0], dy = directions[index][1];
    CGPoint tip = tips[index];
    CGPoint base = CGPointMake(tip.x - dx * half * 1.6, tip.y - dy * half * 1.6);
    CGPathMoveToPoint(path, NULL, tip.x, tip.y);
    CGPathAddLineToPoint(path, NULL, base.x + dy * half, base.y + dx * half);
    CGPathAddLineToPoint(path, NULL, base.x - dy * half, base.y - dx * half);
    CGPathCloseSubpath(path);
  }
  return path;
}

/// Font size of a default-skin glyph so it fits its control.
static CGFloat LibretroSkinLabelFontSize(NSString *label, LibretroSkinItemShape shape, CGSize size) {
  if (label.length == 0 || !(size.width > 0) || !(size.height > 0)) return 0;
  CGFloat base = shape == LibretroSkinItemShapeCircle ? MIN(size.width, size.height) * 0.42 : size.height * 0.46;
  if (shape == LibretroSkinItemShapeCircle && label.length > 1) base *= 0.8;
  UIFont *font = [UIFont systemFontOfSize:base weight:UIFontWeightSemibold];
  CGFloat width = [label sizeWithAttributes:@{NSFontAttributeName : font}].width;
  CGFloat maximum = size.width * 0.82;
  if (width > maximum && width > 0) base *= maximum / width;
  return MAX(base, 5);
}

/// Knob of a thumbstick on the (possibly moved and scaled) frame, moved by
/// the stick `vector` (x, y in -1...1; centred for CGPointZero).
static CGRect LibretroSkinKnobRect(LibretroLaidOutItem *laidOut, CGPoint vector) {
  return LibretroSkinCGRect([LibretroSkinLayout knobFrameForItem:laidOut stickX:vector.x stickY:vector.y]);
}

static BOOL LibretroSkinIsVector(LibretroSkinItem *item) {
  return item.shape != LibretroSkinItemShapeNone && item.kind != LibretroSkinItemKindTouchScreen;
}

static BOOL LibretroSkinHasLabel(LibretroSkinItem *item) {
  return item.label.length > 0 && item.shape != LibretroSkinItemShapeDPad && item.shape != LibretroSkinItemShapeStick &&
         item.kind == LibretroSkinItemKindButton;
}

/// Identity of an item's drawing, to keep its layers (and images) across
/// layouts of an equivalent representation. nil: nothing is drawn.
static NSString *LibretroSkinItemSignature(LibretroSkinItem *item) {
  if (item.kind == LibretroSkinItemKindTouchScreen) return nil;
  if (LibretroSkinIsVector(item)) {
    return [NSString stringWithFormat:@"vector-%ld-%ld", (long)item.shape, (long)item.kind];
  }
  return [NSString stringWithFormat:@"image-%ld|%@|%@", (long)item.kind, item.assetPath ?: @"",
                                    item.thumbstickAssetPath ?: @""];
}

#pragma mark - Item layers

@interface LibretroSkinPressureLayer : CALayer
@property(nonatomic, strong) CALayer *texture;
@property(nonatomic, copy) NSArray *frames;
@property(nonatomic, assign) NSUInteger direction;
@property(nonatomic, assign) BOOL down;
@end
@implementation LibretroSkinPressureLayer
@end

/// Layers of one item, all positioned in renderer coordinates inside
/// `container` (bounds and position preserve layout coordinates).
@interface LibretroSkinItemLayers : NSObject
@property(nonatomic, copy) NSString *identifier;
@property(nonatomic, copy) NSString *signature;
@property(nonatomic, strong) LibretroLaidOutItem *laidOut;
@property(nonatomic, strong) CALayer *container;
@property(nonatomic, strong) CALayer *artwork;
@property(nonatomic, strong, nullable) CALayer *backplate;
@property(nonatomic, assign) BOOL pressedState;
@property(nonatomic, assign) BOOL extracted;
@property(nonatomic, assign) BOOL pressurePreparing;
@property(nonatomic, assign) BOOL cropPreparing;
@property(nonatomic, assign) BOOL cropAttempted;
@property(nonatomic, assign) BOOL compositePressure;
@property(nonatomic, copy) NSArray<LibretroSkinPressureLayer *> *pressureRegions;
@property(nonatomic, strong, nullable) CAShapeLayer *shape;
@property(nonatomic, strong, nullable) CAShapeLayer *arrows;
@property(nonatomic, strong, nullable) CAShapeLayer *knob;
@property(nonatomic, strong, nullable) CATextLayer *text;
@property(nonatomic, strong, nullable) CALayer *image;
@property(nonatomic, strong, nullable) CALayer *knobImage;
/// Pressed overlay: a shape (vector and painted items) or a white layer
/// masked by the item's image.
@property(nonatomic, strong, nullable) CAShapeLayer *highlightShape;
@property(nonatomic, strong, nullable) CALayer *highlightImage;
@property(nonatomic, strong, nullable) CALayer *highlightMask;
@property(nonatomic, strong) CAShapeLayer *outline;
@end

@implementation LibretroSkinItemLayers
@end

static CALayer *LibretroSkinPlainLayer(CGFloat scale) {
  CALayer *layer = [CALayer layer];
  layer.contentsScale = scale;
  layer.contentsGravity = kCAGravityResize;
  return layer;
}

static CAShapeLayer *LibretroSkinShapeLayer(CGFloat scale) {
  CAShapeLayer *layer = [CAShapeLayer layer];
  layer.contentsScale = scale;
  return layer;
}

#pragma mark - Renderer

@implementation LibretroSkinRenderer {
  NSString *_cacheDirectory;
  CALayer *_panelLayer;
  CALayer *_backgroundLayer;
  CALayer *_pressedBackgroundLayer; // Preload target only, never displayed whole.
  NSMutableArray<LibretroSkinItemLayers *> *_items;
  LibretroSkinRepresentation *_representation;
  LibretroSkinLayoutResult *_layout;
  CGFloat _opacity;
  CGFloat _scale;
  BOOL _controlsHidden;
  NSSet<NSString *> *_pressed;
  NSDictionary<NSString *, NSValue *> *_stickVectors;
  BOOL _editing;
  NSString *_selectedItem;
  NSDictionary<NSString *, NSNumber *> *_dpadDirections;
  NSUInteger _imageGeneration;
  NSUInteger _pressureBytes;
  NSProgress *_pressurePreparation;
}

- (instancetype)initWithCacheDirectory:(NSString *)cacheDirectory {
  self = [super initWithFrame:CGRectZero];
  if (self) {
    _cacheDirectory = [cacheDirectory isKindOfClass:[NSString class]] ? [cacheDirectory copy] : @"";
    _items = [NSMutableArray array];
    _pressed = [NSSet set];
    _stickVectors = @{};
    _opacity = 1;
    _scale = 2;
    self.userInteractionEnabled = NO;
    self.opaque = NO;
    self.backgroundColor = UIColor.clearColor;
    self.isAccessibilityElement = NO;
    self.accessibilityElementsHidden = YES;
    _panelLayer = [CALayer layer];
    _panelLayer.hidden = YES;
    _backgroundLayer = LibretroSkinPlainLayer(_scale);
    _pressedBackgroundLayer = LibretroSkinPlainLayer(_scale);
    _backgroundLayer.hidden = YES;
    [self.layer addSublayer:_panelLayer];
    [self.layer addSublayer:_backgroundLayer];
  }
  return self;
}

- (CGFloat)currentDisplayScale {
  CGFloat scale = self.traitCollection.displayScale;
  if (!(scale > 0)) scale = UIScreen.mainScreen.scale;
  return scale > 0 ? scale : 2;
}

- (void)showRepresentation:(LibretroSkinRepresentation *)representation
                    layout:(LibretroSkinLayoutResult *)layout
                   opacity:(CGFloat)opacity
            controlsHidden:(BOOL)controlsHidden {
  [CATransaction begin];
  [CATransaction setDisableActions:YES];
  CGFloat scale = [self currentDisplayScale];
  BOOL sameContent = representation != nil && representation == _representation && layout == _layout &&
                     fabs(scale - _scale) < 0.01;
  if (!sameContent) {
    _imageGeneration++;
    _pressureBytes = 0;
    [_pressurePreparation cancel];
    _pressurePreparation = [NSProgress progressWithTotalUnitCount:1];
    _backgroundLayer.mask = nil;
    if (_representation != representation) {
      _pressed = [NSSet set];
      _stickVectors = @{};
      _dpadDirections = @{};
    }
    if (![_representation.backgroundPath isEqualToString:representation.backgroundPath]) _backgroundLayer.contents = nil;
  }
  _scale = scale;
  _representation = representation;
  _layout = layout;
  _opacity = isfinite(opacity) ? MIN(MAX(opacity, 0), 1) : 1;
  _controlsHidden = controlsHidden;
  if (representation == nil || layout == nil) {
    [self clearAll];
  } else if (sameContent) {
    // Same layout: only opacity and visibility change (controller
    // connected, opacity slider).
    if (!_backgroundLayer.hidden) {
      _backgroundLayer.opacity = representation.translucent ? (float)_opacity : 1.0f;
    }
    for (LibretroSkinItemLayers *layers in _items) [self applyStateToLayers:layers];
  } else {
    [self applyPanelAndBackground];
    [self applyItems];
    [self preparePaintedItems];
    [self preparePressureItems];
  }
  [CATransaction commit];
}

- (void)clearAll {
  _panelLayer.hidden = YES;
  _backgroundLayer.hidden = YES;
  _backgroundLayer.contents = nil;
  _pressedBackgroundLayer.contents = nil;
  [_backgroundLayer setValue:nil forKey:LibretroSkinImageKey];
  [_pressedBackgroundLayer setValue:nil forKey:LibretroSkinImageKey];
  for (LibretroSkinItemLayers *layers in _items) [layers.container removeFromSuperlayer];
  [_items removeAllObjects];
  _backgroundLayer.mask = nil;
  _imageGeneration++;
  [_pressurePreparation cancel];
}

- (void)applyPanelAndBackground {
  LibretroSkinRepresentation *representation = _representation;
  LibretroSkinLayoutResult *layout = _layout;
  // Portrait default skins: opaque controller panel below the items.
  CGRect panel = LibretroSkinCGRect(layout.panelFrame);
  if (representation.panelColor != 0 && !CGRectIsEmpty(panel)) {
    _panelLayer.hidden = NO;
    _panelLayer.frame = panel;
    UIColor *color = LibretroSkinColor(representation.panelColor);
    _panelLayer.backgroundColor = color.CGColor;
  } else {
    _panelLayer.hidden = YES;
  }

  CGRect skinRect = LibretroSkinCGRect(layout.skinRect);
  NSString *background = representation.generated ? nil : representation.backgroundPath;
  if (background.length > 0 && !CGRectIsEmpty(skinRect)) {
    _backgroundLayer.hidden = NO;
    _backgroundLayer.frame = skinRect;
    _backgroundLayer.contentsScale = _scale;
    // Opaque skins keep their image fully opaque; translucent ones follow
    // the user's opacity (Delta).
    _backgroundLayer.opacity = representation.translucent ? (float)_opacity : 1.0f;
    [self loadImageAtPath:background points:skinRect.size layer:_backgroundLayer mask:nil force:YES];
    if (![_pressedBackgroundLayer.name isEqualToString:representation.pressedBackgroundPath]) {
      _pressedBackgroundLayer.contents = nil;
      _pressedBackgroundLayer.name = representation.pressedBackgroundPath;
    }
    [self loadImageAtPath:representation.pressedBackgroundPath points:skinRect.size
                   layer:_pressedBackgroundLayer mask:nil force:YES];
  } else {
    _backgroundLayer.hidden = YES;
    _backgroundLayer.contents = nil;
    [_backgroundLayer setValue:nil forKey:LibretroSkinImageKey];
    _pressedBackgroundLayer.contents = nil;
    [_pressedBackgroundLayer setValue:nil forKey:LibretroSkinImageKey];
  }
}

- (float)itemsOpacity {
  LibretroSkinRepresentation *representation = _representation;
  return (representation.translucent || representation.generated) ? (float)_opacity : 1.0f;
}

- (void)applyItems {
  NSMutableDictionary<NSString *, LibretroSkinItemLayers *> *previous = [NSMutableDictionary dictionary];
  for (LibretroSkinItemLayers *layers in _items) previous[layers.identifier] = layers;
  NSMutableArray<LibretroSkinItemLayers *> *items = [NSMutableArray array];
  for (LibretroLaidOutItem *laidOut in _layout.items) {
    LibretroSkinItem *item = laidOut.item;
    NSString *signature = LibretroSkinItemSignature(item);
    if (signature == nil || item.identifier.length == 0) continue;
    LibretroSkinItemLayers *layers = previous[item.identifier];
    if (layers != nil && !layers.extracted && !layers.cropPreparing && !layers.pressurePreparing && layers.pressureRegions.count == 0 &&
        [layers.signature isEqualToString:signature]) {
      [previous removeObjectForKey:item.identifier];
    } else {
      layers = [self createLayersForItem:item signature:signature];
    }
    layers.laidOut = laidOut;
    [self updateLayers:layers];
    [items addObject:layers];
  }
  for (LibretroSkinItemLayers *layers in previous.allValues) [layers.container removeFromSuperlayer];
  // Drawing order: panel, background, then the items in skin order.
  for (LibretroSkinItemLayers *layers in items) [self.layer addSublayer:layers.container];
  [_items setArray:items];
}

- (LibretroSkinItemLayers *)createLayersForItem:(LibretroSkinItem *)item signature:(NSString *)signature {
  CGFloat scale = _scale;
  LibretroSkinItemLayers *layers = [LibretroSkinItemLayers new];
  layers.identifier = item.identifier;
  layers.signature = signature;
  layers.container = [CALayer layer];
  layers.container.anchorPoint = CGPointZero;
  layers.container.frame = CGRectZero;
  layers.container.name = [@"skin-item-" stringByAppendingString:item.identifier];
  layers.artwork = [CALayer layer];
  layers.artwork.anchorPoint = CGPointZero;
  layers.artwork.frame = CGRectZero;
  layers.artwork.name = [@"skin-face-" stringByAppendingString:item.identifier];
  [layers.container addSublayer:layers.artwork];
  if (LibretroSkinIsVector(item)) {
    layers.shape = LibretroSkinShapeLayer(scale);
    [layers.artwork addSublayer:layers.shape];
    if (item.shape == LibretroSkinItemShapeDPad) {
      layers.arrows = LibretroSkinShapeLayer(scale);
      [layers.artwork addSublayer:layers.arrows];
    }
    if (item.kind == LibretroSkinItemKindThumbstick) {
      layers.knob = LibretroSkinShapeLayer(scale);
      [layers.artwork addSublayer:layers.knob];
    }
    if (LibretroSkinHasLabel(item)) {
      CATextLayer *text = [CATextLayer layer];
      text.contentsScale = scale;
      text.alignmentMode = kCAAlignmentCenter;
      text.wrapped = NO;
      text.truncationMode = kCATruncationNone;
      layers.text = text;
      [layers.artwork addSublayer:text];
    }
    layers.highlightShape = LibretroSkinShapeLayer(scale);
    [layers.artwork addSublayer:layers.highlightShape];
  } else {
    if (item.assetPath.length > 0) {
      layers.image = LibretroSkinPlainLayer(scale);
      [layers.artwork addSublayer:layers.image];
      layers.highlightImage = [CALayer layer];
      layers.highlightMask = LibretroSkinPlainLayer(scale);
      layers.highlightImage.mask = layers.highlightMask;
      [layers.artwork addSublayer:layers.highlightImage];
    } else {
      // Control painted in the background image: a soft overlay only.
      layers.highlightShape = LibretroSkinShapeLayer(scale);
      [layers.artwork addSublayer:layers.highlightShape];
    }
    if (item.kind == LibretroSkinItemKindThumbstick && item.thumbstickAssetPath.length > 0) {
      layers.knobImage = LibretroSkinPlainLayer(scale);
      [layers.artwork addSublayer:layers.knobImage];
    }
  }
  layers.outline = LibretroSkinShapeLayer(scale);
  layers.outline.hidden = YES;
  [layers.container addSublayer:layers.outline];
  return layers;
}

- (void)updateLayers:(LibretroSkinItemLayers *)layers {
  LibretroLaidOutItem *laidOut = layers.laidOut;
  LibretroSkinItem *item = laidOut.item;
  CGRect frame = LibretroSkinCGRect(laidOut.frame);
  CGRect assetFrame = LibretroSkinCGRect(laidOut.assetFrame);
  if (CGRectIsEmpty(assetFrame)) assetFrame = frame;
  CGFloat scale = _scale;
  // Groups keep the same layout coordinate system, with bounds limited to
  // the control and its shadow rather than a full-screen offscreen surface.
  CGRect scope = CGRectUnion(frame, assetFrame);
  if (item.kind == LibretroSkinItemKindThumbstick) {
    scope = CGRectUnion(scope, LibretroSkinKnobRect(laidOut, CGPointMake(-1, -1)));
    scope = CGRectUnion(scope, LibretroSkinKnobRect(laidOut, CGPointMake(1, 1)));
  }
  scope = CGRectInset(scope, -8, -8);
  layers.container.bounds = scope;
  layers.container.position = scope.origin;
  layers.artwork.bounds = scope;
  layers.artwork.position = scope.origin;

  if (layers.shape != nil) {
    layers.shape.contentsScale = scale;
    layers.shape.frame = frame;
    CGPathRef path = LibretroSkinCreateShapePath(item.shape, frame.size);
    layers.shape.path = path;
    CGPathRelease(path);
    UIColor *fill = LibretroSkinColor(item.fillColor);
    layers.shape.fillColor = fill.CGColor;
  }
  if (layers.arrows != nil) {
    layers.arrows.contentsScale = scale;
    layers.arrows.frame = frame;
    CGPathRef path = LibretroSkinCreateArrowsPath(frame.size);
    layers.arrows.path = path;
    CGPathRelease(path);
    UIColor *color = item.labelColor != 0 ? LibretroSkinColor(item.labelColor) : [UIColor colorWithWhite:1 alpha:0.6];
    layers.arrows.fillColor = color.CGColor;
  }
  if (layers.knob != nil) {
    CGRect knob = LibretroSkinKnobRect(laidOut, [self stickVectorForIdentifier:layers.identifier]);
    layers.knob.contentsScale = scale;
    layers.knob.frame = knob;
    CGPathRef path = LibretroSkinCreateShapePath(LibretroSkinItemShapeCircle, knob.size);
    layers.knob.path = path;
    CGPathRelease(path);
    UIColor *fill = LibretroSkinLighterColor(item.fillColor, 0.3);
    layers.knob.fillColor = fill.CGColor;
  }
  if (layers.text != nil) {
    CGFloat size = LibretroSkinLabelFontSize(item.label, item.shape, frame.size);
    UIFont *font = [UIFont systemFontOfSize:MAX(size, 1) weight:UIFontWeightSemibold];
    CGFloat lineHeight = ceil(font.lineHeight);
    layers.text.contentsScale = scale;
    layers.text.string = item.label;
    layers.text.font = (__bridge CFTypeRef)font;
    layers.text.fontSize = font.pointSize;
    UIColor *color = item.labelColor != 0 ? LibretroSkinColor(item.labelColor) : UIColor.whiteColor;
    layers.text.foregroundColor = color.CGColor;
    layers.text.frame = CGRectMake(frame.origin.x, frame.origin.y + (frame.size.height - lineHeight) / 2,
                                   frame.size.width, lineHeight);
    layers.text.hidden = size <= 0;
  }
  if (layers.image != nil && !layers.extracted && layers.pressureRegions.count == 0) {
    layers.image.frame = assetFrame;
    [self loadImageAtPath:item.assetPath
                   points:assetFrame.size
                    layer:layers.image
                     mask:layers.highlightMask
                    force:!_editing];
  }
  if (layers.knobImage != nil) {
    CGRect knob = LibretroSkinKnobRect(laidOut, [self stickVectorForIdentifier:layers.identifier]);
    layers.knobImage.frame = knob;
    [self loadImageAtPath:item.thumbstickAssetPath points:knob.size layer:layers.knobImage mask:nil force:!_editing];
  }
  if (layers.highlightShape != nil) {
    layers.highlightShape.contentsScale = scale;
    layers.highlightShape.frame = frame;
    CGPathRef path = LibretroSkinCreateShapePath(LibretroSkinIsVector(item) ? item.shape : LibretroSkinItemShapeNone,
                                                 frame.size);
    layers.highlightShape.path = path;
    CGPathRelease(path);
    UIColor *overlay = [UIColor colorWithWhite:1 alpha:LibretroSkinIsVector(item) ? 0.35 : 0.25];
    layers.highlightShape.fillColor = overlay.CGColor;
  }
  if (layers.highlightImage != nil) {
    layers.highlightImage.frame = assetFrame;
    UIColor *overlay = [UIColor colorWithWhite:1 alpha:0.4];
    layers.highlightImage.backgroundColor = overlay.CGColor;
    layers.highlightMask.frame = CGRectMake(0, 0, assetFrame.size.width, assetFrame.size.height);
  }
  CGRect outline = CGRectInset(frame, -6, -6);
  layers.outline.contentsScale = scale;
  layers.outline.frame = outline;
  CGMutablePathRef outlinePath = CGPathCreateMutable();
  LibretroSkinAddRoundedRect(outlinePath, CGRectMake(0, 0, outline.size.width, outline.size.height),
                             MIN(MIN(outline.size.width, outline.size.height) / 2, 14));
  layers.outline.path = outlinePath;
  CGPathRelease(outlinePath);
  [self applyStateToLayers:layers];
}

/// Visibility, opacity, pressed highlight and editing outline.
- (void)applyStateToLayers:(LibretroSkinItemLayers *)layers {
  LibretroSkinItem *item = layers.laidOut.item;
  // Editing shows every control, even with a physical controller.
  layers.container.hidden = _controlsHidden && !_editing && !layers.extracted && !layers.compositePressure;
  layers.artwork.hidden = _controlsHidden && !_editing && !layers.compositePressure;
  layers.container.opacity = [self itemsOpacity];
  BOOL pressed = !_editing && [_pressed containsObject:layers.identifier];
  [self applyPressToLayers:layers down:pressed];
  BOOL movable = _editing && item.movable;
  layers.outline.hidden = !movable;
  if (movable) {
    BOOL selected = _selectedItem != nil && [_selectedItem isEqualToString:layers.identifier];
    UIColor *stroke = selected ? UIColor.systemYellowColor : [UIColor colorWithWhite:1 alpha:0.9];
    UIColor *fill = selected ? [UIColor colorWithWhite:1 alpha:0.14] : UIColor.clearColor;
    layers.outline.strokeColor = stroke.CGColor;
    layers.outline.fillColor = fill.CGColor;
    layers.outline.lineWidth = selected ? 2.5 : 1.5;
    layers.outline.lineDashPattern = selected ? nil : @[ @6, @4 ];
  }
}

- (void)setPressedItems:(NSSet<NSString *> *)itemIdentifiers {
  NSSet<NSString *> *pressed = [itemIdentifiers isKindOfClass:[NSSet class]] ? [itemIdentifiers copy] : [NSSet set];
  if ([pressed isEqualToSet:_pressed]) return;
  _pressed = pressed;
  [CATransaction begin];
  [CATransaction setDisableActions:YES];
  for (LibretroSkinItemLayers *layers in _items) {
    BOOL down = !_editing && [pressed containsObject:layers.identifier];
    [self applyPressToLayers:layers down:down];
  }
  [CATransaction commit];
}

/// Press the face, not its hit area. Artwork stays in layout coordinates,
/// so scaling is explicitly centred on the visible control. A stick moves
/// only its cap; the base stays fixed. Touch-down has no animation delay.
- (void)applyPressToLayers:(LibretroSkinItemLayers *)layers down:(BOOL)down {
  LibretroSkinItem *item = layers.laidOut.item;
  if (layers.pressureRegions.count > 0 || item.kind == LibretroSkinItemKindDPad) {
    layers.artwork.transform = CATransform3DIdentity;
    [layers.artwork removeAnimationForKey:@"skin-release"];
    layers.highlightShape.hidden = YES;
    layers.highlightImage.hidden = YES;
    NSUInteger directions = _dpadDirections[layers.identifier].unsignedIntegerValue;
    BOOL enabled = down && !_controlsHidden && !_editing;
    for (LibretroSkinPressureLayer *region in layers.pressureRegions) {
      BOOL active = enabled && (region.direction == 0 || (directions & region.direction) != 0);
      if (active == region.down && !_controlsHidden && !_editing) continue;
      BOOL released = region.down && !active;
      [region.texture removeAnimationForKey:@"skin-release"];
      region.texture.contents = active ? region.frames.lastObject : region.frames.firstObject;
      if (released && !_controlsHidden && !_editing && !UIAccessibilityIsReduceMotionEnabled()) {
        CAKeyframeAnimation *animation = [CAKeyframeAnimation animationWithKeyPath:@"contents"];
        animation.values = region.frames.reverseObjectEnumerator.allObjects;
        animation.duration = 0.12;
        animation.calculationMode = kCAAnimationDiscrete;
        animation.keyTimes = @[@0, @0.075, @0.155, @0.244, @0.345, @0.465, @0.622, @1];
        [region.texture addAnimation:animation forKey:@"skin-release"];
      }
      region.down = active;
    }
    layers.pressedState = enabled;
    return;
  }
  BOOL stick = item.kind == LibretroSkinItemKindThumbstick;
  CALayer *cap = layers.knobImage ?: layers.knob;
  BOOL movable = stick ? cap != nil : (layers.image != nil || layers.shape != nil);
  BOOL active = down && !_controlsHidden && !_editing && movable;
  // An ambiguous painted control stays intact. Neither an artificial glow
  // nor a duplicate face substitutes for safely identified artwork.
  layers.highlightShape.hidden = YES;
  layers.highlightImage.hidden = YES;
  CALayer *face = stick ? cap : layers.artwork;
  if (face == nil) return;
  CATransform3D target = CATransform3DIdentity;
  if (active) {
    CGFloat shrink = stick ? 0.96 : 0.965;
    CGFloat depth = MIN(2.0, MAX(0.7, layers.laidOut.frame.h * 0.025));
    target = CATransform3DMakeScale(shrink, shrink, 1);
    if (stick) {
      target.m42 = depth;
    } else {
      CGRect frame = LibretroSkinCGRect(layers.laidOut.assetFrame);
      if (CGRectIsEmpty(frame)) frame = LibretroSkinCGRect(layers.laidOut.frame);
      target.m41 = (CGRectGetMidX(frame) - face.bounds.origin.x) * (1 - shrink);
      target.m42 = (CGRectGetMidY(frame) - face.bounds.origin.y) * (1 - shrink) + depth;
    }
  }
  CATransform3D previous = face.presentationLayer != nil ? face.presentationLayer.transform : face.transform;
  BOOL released = layers.pressedState && !active;
  if (active || released || _editing || _controlsHidden) [face removeAnimationForKey:@"skin-release"];
  face.transform = target;
  // Editing/hidden controls return immediately. Touch release or cancellation
  // interpolates from the visible position, so rapid re-presses never queue.
  if (released && !_editing && !_controlsHidden && !UIAccessibilityIsReduceMotionEnabled()) {
    CABasicAnimation *animation = [CABasicAnimation animationWithKeyPath:@"transform"];
    animation.fromValue = [NSValue valueWithCATransform3D:previous];
    animation.toValue = [NSValue valueWithCATransform3D:target];
    animation.duration = 0.12;
    animation.timingFunction = [CAMediaTimingFunction functionWithName:kCAMediaTimingFunctionEaseOut];
    [face addAnimation:animation forKey:@"skin-release"];
  }
  layers.pressedState = active;
  // Imported artwork may already contain a shadow. Keep added shadows subtle;
  // flat extracted rectangles keep their original perimeter, without a halo.
  CALayer *shadow = stick ? cap : (layers.image ?: layers.shape);
  shadow.shadowColor = UIColor.blackColor.CGColor;
  shadow.shadowOpacity = layers.extracted || !movable ? 0 : (active ? 0.08f : 0.18f);
  shadow.shadowRadius = active ? 0.5 : 1.5;
  shadow.shadowOffset = CGSizeMake(0, active ? 0.4 : 1.5);
}

- (void)setDPadDirections:(NSDictionary<NSString *, NSNumber *> *)directions {
  if ([_dpadDirections isEqualToDictionary:directions ?: @{}]) return;
  _dpadDirections = [directions copy] ?: @{};
  [CATransaction begin];
  [CATransaction setDisableActions:YES];
  for (LibretroSkinItemLayers *layers in _items) {
    if (layers.laidOut.item.kind == LibretroSkinItemKindDPad)
      [self applyPressToLayers:layers down:[_pressed containsObject:layers.identifier]];
  }
  [CATransaction commit];
}

/// The source is replaced, including its alpha, never drawn twice. Integer
/// pixel boundaries and non-antialiased masks avoid a fringe around a patch.
- (void)updateBackgroundMask {
  CGRect skin = _backgroundLayer.frame;
  CGMutablePathRef holes = CGPathCreateMutable();
  CGPathAddRect(holes, NULL, CGRectMake(0, 0, skin.size.width, skin.size.height));
  for (LibretroSkinItemLayers *layers in _items) {
    if (layers.extracted)
      CGPathAddRect(holes, NULL, CGRectOffset(layers.image.frame, -skin.origin.x, -skin.origin.y));
    if (layers.compositePressure) for (CALayer *region in layers.pressureRegions)
      CGPathAddRect(holes, NULL, CGRectOffset(region.frame, -skin.origin.x, -skin.origin.y));
  }
  CAShapeLayer *mask = [CAShapeLayer layer];
  mask.frame = CGRectMake(0, 0, skin.size.width, skin.size.height);
  mask.contentsScale = _scale;
  mask.edgeAntialiasingMask = 0;
  mask.path = holes;
  mask.fillRule = kCAFillRuleEvenOdd;
  _backgroundLayer.mask = mask;
  CGPathRelease(holes);
}

/// Normalized visual geometry deliberately excludes extended hit edges.
/// Regions crossing another item or a game screen are not inferred from a
/// touch rectangle. Such layouts keep their original artwork intact.
- (BOOL)canAdaptCompositeFrame:(CGRect)frame item:(LibretroLaidOutItem *)item {
  if (!CGRectContainsRect(_backgroundLayer.frame, frame) || CGRectIsEmpty(frame)) return NO;
  for (NSUInteger index = 0; index < _layout.screens.count; index++) {
    LibretroLaidOutScreen *screen = _layout.screens[index];
    BOOL explicitWindow = index < _representation.screens.count && _representation.screens[index].hasOutputFrame;
    // Landscape overlays intentionally sit above a full-view game. We only
    // sample the skin texture, never game pixels. A declared opaque window
    // or a stylus surface, however, must not be inferred as button artwork.
    if ((screen.touchScreen || (explicitWindow && !_representation.translucent)) &&
        CGRectIntersectsRect(frame, LibretroSkinCGRect(screen.container))) return NO;
  }
  for (LibretroLaidOutItem *other in _layout.items)
    if (other != item && CGRectIntersectsRect(frame, LibretroSkinCGRect(other.frame))) return NO;
  return YES;
}

/// Prepare four independent D-pad regions, or one composite button region.
/// All pixels and intermediate release frames are ready before touch-down.
/// Across this layout at most 32 MiB is reserved for these frames; no cache
/// or layer from a previous layout can publish into the new generation.
- (void)preparePressureItems {
  const NSUInteger budget = 32u * 1024u * 1024u;
  NSArray *ordered = [_items sortedArrayUsingComparator:^NSComparisonResult(LibretroSkinItemLayers *a, LibretroSkinItemLayers *b) {
    BOOL ap = a.laidOut.item.kind == LibretroSkinItemKindDPad, bp = b.laidOut.item.kind == LibretroSkinItemKindDPad;
    return ap == bp ? NSOrderedSame : (ap ? NSOrderedAscending : NSOrderedDescending);
  }];
  for (LibretroSkinItemLayers *layers in ordered) {
    LibretroSkinItem *item = layers.laidOut.item;
    BOOL pad = item.kind == LibretroSkinItemKindDPad;
    BOOL composite = item.assetPath == nil && layers.shape == nil;
    if ((!pad && (!composite || item.kind != LibretroSkinItemKindButton)) ||
        item.inputs.count == 0 || layers.extracted || layers.cropPreparing ||
        layers.pressurePreparing || layers.pressureRegions.count > 0) continue;
    CALayer *sourceLayer = composite ? _backgroundLayer : layers.image;
    CGRect frame = LibretroSkinCGRect(composite || layers.shape != nil ? layers.laidOut.frame : layers.laidOut.assetFrame);
    if (CGRectIsEmpty(frame)) frame = LibretroSkinCGRect(layers.laidOut.frame);
    if (composite && ![self canAdaptCompositeFrame:frame item:layers.laidOut]) continue;
    if (layers.shape == nil && (sourceLayer.contents == nil ||
        ![[sourceLayer valueForKey:@"neostationSkinReadyKey"] isEqual:[sourceLayer valueForKey:LibretroSkinImageKey]])) continue;
    if (composite && _representation.pressedBackgroundPath != nil &&
        ![[_pressedBackgroundLayer valueForKey:@"neostationSkinReadyKey"]
          isEqual:[_pressedBackgroundLayer valueForKey:LibretroSkinImageKey]]) continue;
    UIImage *source = sourceLayer.contents ? [UIImage imageWithCGImage:(__bridge CGImageRef)sourceLayer.contents] : nil;
    UIImage *authored = composite && _pressedBackgroundLayer.contents ?
        [UIImage imageWithCGImage:(__bridge CGImageRef)_pressedBackgroundLayer.contents] : nil;
    CGRect sourceFrame = composite ? _backgroundLayer.frame : frame;
    size_t width = 0, height = 0;
    if (source != nil) { width = CGImageGetWidth(source.CGImage); height = CGImageGetHeight(source.CGImage); }
    else if (!LibretroSkinPixelSize(frame.size, _scale, &width, &height)) continue;
    CGFloat sx = width / sourceFrame.size.width, sy = height / sourceFrame.size.height;
    // Round inward: never borrow pixels from a neighbouring control/screen.
    CGFloat x = ceil((frame.origin.x-sourceFrame.origin.x)*sx);
    CGFloat y = ceil((frame.origin.y-sourceFrame.origin.y)*sy);
    CGRect pixels = CGRectMake(x, y, floor((CGRectGetMaxX(frame)-sourceFrame.origin.x)*sx)-x,
                                   floor((CGRectGetMaxY(frame)-sourceFrame.origin.y)*sy)-y);
    if (pixels.size.width < 9 || pixels.size.height < 9) continue;
    // Conservative bound for up to four two-sided sampling aprons.
    NSUInteger cost = (NSUInteger)((pixels.size.width+8)*(pixels.size.height+8))*4*8;
    if (cost > budget - _pressureBytes) continue;
    _pressureBytes += cost;
    layers.pressurePreparing = YES;
    NSUInteger generation = _imageGeneration;
    NSProgress *preparation = _pressurePreparation;
    uint32_t fillColor = item.fillColor, labelColor = item.labelColor;
    __weak LibretroSkinRenderer *weakSelf = self;
    dispatch_async(LibretroSkinQueue(), ^{
      @autoreleasepool {
        if (preparation.cancelled) return;
        UIImage *normal = source;
        if (normal == nil) {
          // Rasterize the built-in vector once, in the same UIKit geometry.
          CGColorSpaceRef space = CGColorSpaceCreateWithName(kCGColorSpaceSRGB);
          CGContextRef context = CGBitmapContextCreate(NULL, width, height, 8, width*4, space,
              kCGImageAlphaPremultipliedLast | kCGBitmapByteOrder32Big);
          CGColorSpaceRelease(space);
          if (context != NULL) {
            CGContextTranslateCTM(context, 0, height);
            CGContextScaleCTM(context, sx, -sy);
            CGPathRef cross = LibretroSkinCreateShapePath(LibretroSkinItemShapeDPad, frame.size);
            CGContextAddPath(context, cross);
            CGContextSetFillColorWithColor(context, LibretroSkinColor(fillColor).CGColor);
            CGContextFillPath(context);
            CGPathRelease(cross);
            CGPathRef arrows = LibretroSkinCreateArrowsPath(frame.size);
            CGContextAddPath(context, arrows);
            CGContextSetFillColorWithColor(context, (labelColor ? LibretroSkinColor(labelColor) :
                [UIColor colorWithWhite:1 alpha:0.6]).CGColor);
            CGContextFillPath(context);
            CGPathRelease(arrows);
            CGImageRef image = CGBitmapContextCreateImage(context);
            if (image != NULL) { normal = [UIImage imageWithCGImage:image]; CGImageRelease(image); }
            CGContextRelease(context);
          }
        }
        // Delta permits differently sized pressed rasters. Map the whole
        // representation to the normal raster before taking local regions.
        UIImage *pressed = authored;
        if (pressed != nil && (CGImageGetWidth(pressed.CGImage) != width || CGImageGetHeight(pressed.CGImage) != height)) {
          CGColorSpaceRef space = CGColorSpaceCreateWithName(kCGColorSpaceSRGB);
          CGContextRef context = CGBitmapContextCreate(NULL, width, height, 8, width*4, space,
              kCGImageAlphaPremultipliedLast | kCGBitmapByteOrder32Big);
          CGColorSpaceRelease(space);
          pressed = nil;
          if (context != NULL) {
            CGContextDrawImage(context, CGRectMake(0,0,width,height), authored.CGImage);
            CGImageRef image = CGBitmapContextCreateImage(context);
            if (image != NULL) { pressed = [UIImage imageWithCGImage:image]; CGImageRelease(image); }
            CGContextRelease(context);
          }
        }
        NSMutableArray *prepared = [NSMutableArray array];
        for (NSUInteger slot = 0; slot < (pad ? 4u : 1u); slot++) {
          if (preparation.cancelled) return;
          CGRect area = pad ? CGRectOffset(LibretroSkinPressureArm(pixels.size, slot), pixels.origin.x, pixels.origin.y) : pixels;
          NSArray *frames = normal ? LibretroSkinPressureFrames(normal.CGImage, area, 1/sy, pad ? 1u<<slot : 0, pressed.CGImage) : @[];
          if (frames.count == 0) break;
          CGRect exact = CGRectMake(sourceFrame.origin.x+area.origin.x/sx, sourceFrame.origin.y+area.origin.y/sy,
                                   area.size.width/sx, area.size.height/sy);
          exact = CGRectIntersection(exact, frame);
          [prepared addObject:@{@"frame":[NSValue valueWithCGRect:exact], @"pixels":[NSValue valueWithCGRect:area],
            @"images":frames, @"direction":@(pad ? 1u<<slot : 0)}];
        }
        dispatch_async(dispatch_get_main_queue(), ^{
          LibretroSkinRenderer *renderer = weakSelf;
          if (renderer == nil || renderer->_imageGeneration != generation || ![renderer->_items containsObject:layers]) return;
          // One attempt per layout, including failures; never retry on touch.
          if (prepared.count != (pad ? 4u : 1u)) return;
          [CATransaction begin]; [CATransaction setDisableActions:YES];
          NSMutableArray *regions = [NSMutableArray array];
          CGMutablePathRef holes = CGPathCreateMutable();
          CGPathAddRect(holes, NULL, CGRectMake(0,0,frame.size.width,frame.size.height));
          for (NSDictionary *part in prepared) {
            LibretroSkinPressureLayer *region = [LibretroSkinPressureLayer layer];
            region.frame = [part[@"frame"] CGRectValue];
            region.contentsScale = renderer->_scale;
            region.edgeAntialiasingMask = 0;
            region.masksToBounds = YES;
            region.frames = part[@"images"];
            region.texture = LibretroSkinPlainLayer(renderer->_scale);
            region.texture.edgeAntialiasingMask = 0;
            region.texture.contents = region.frames.firstObject;
            CGImageRef texture = (__bridge CGImageRef)region.texture.contents;
            CGFloat tw = CGImageGetWidth(texture), th = CGImageGetHeight(texture);
            CGRect area = [part[@"pixels"] CGRectValue];
            // Keep the same image plane/transform as the unsplit source.
            // A separately resized crop can acquire a different sampling
            // phase at fractional layout coordinates. The parent clips the
            // full-plane mapping to this arm; only small patch pixels are
            // stored, with their one-pixel apron available for filtering.
            region.texture.frame = CGRectOffset(sourceFrame, -region.frame.origin.x, -region.frame.origin.y);
            region.texture.contentsRect = CGRectMake((1-area.origin.x)/tw, (1-area.origin.y)/th, width/tw, height/th);
            [region addSublayer:region.texture];
            region.direction = [part[@"direction"] unsignedIntegerValue];
            [regions addObject:region];
            CGPathAddRect(holes, NULL, CGRectOffset(region.frame,-frame.origin.x,-frame.origin.y));
          }
          layers.pressureRegions = regions;
          layers.compositePressure = composite;
          if (!composite) {
            layers.shape.hidden = YES;
            layers.arrows.hidden = YES;
            if (layers.image == nil) { layers.image = LibretroSkinPlainLayer(renderer->_scale); [layers.artwork addSublayer:layers.image]; }
            layers.image.frame = frame;
            layers.image.contents = (__bridge id)normal.CGImage;
            layers.image.shadowOpacity = 0;
            CAShapeLayer *mask = [CAShapeLayer layer];
            mask.frame = CGRectMake(0,0,frame.size.width,frame.size.height);
            mask.path = holes; mask.fillRule = kCAFillRuleEvenOdd;
            mask.contentsScale = renderer->_scale; mask.edgeAntialiasingMask = 0;
            layers.image.mask = mask;
          }
          CGPathRelease(holes);
          for (CALayer *region in regions) [layers.artwork addSublayer:region];
          [renderer updateBackgroundMask];
          [renderer applyStateToLayers:layers];
          [CATransaction commit];
        });
      }
    });
  }
}

/// Prepare reliable crops once on the serial image queue, before any press.
/// The original painted area is removed with a background mask and filled
/// with its verified background model, so it cannot remain underneath.
- (void)preparePaintedItems {
  if (_backgroundLayer.contents == nil || _representation.generated || _representation.translucent ||
      _representation.pressedBackgroundPath != nil ||
      ![[_backgroundLayer valueForKey:@"neostationSkinReadyKey"] isEqual:[_backgroundLayer valueForKey:LibretroSkinImageKey]]) return;
  UIImage *background = [UIImage imageWithCGImage:(__bridge CGImageRef)_backgroundLayer.contents];
  CGRect skin = _backgroundLayer.frame;
  if (CGRectIsEmpty(skin)) return;
  NSMutableArray<LibretroSkinItemLayers *> *candidates = [NSMutableArray array];
  for (LibretroSkinItemLayers *layers in _items) {
    LibretroSkinItem *item = layers.laidOut.item;
    if (item.kind != LibretroSkinItemKindButton) continue;
    if (layers.image != nil || layers.shape != nil || item.assetPath != nil || item.inputs.count == 0 ||
        layers.pressurePreparing || layers.cropPreparing || layers.cropAttempted) continue;
    CGRect frame = CGRectInset(LibretroSkinCGRect(layers.laidOut.frame), -6, -6);
    if (!CGRectContainsRect(skin, frame)) continue;
    BOOL isolated = YES;
    for (LibretroLaidOutScreen *screen in _layout.screens) {
      if (CGRectIntersectsRect(frame, LibretroSkinCGRect(screen.container))) isolated = NO;
    }
    for (LibretroLaidOutItem *other in _layout.items) {
      if (other != layers.laidOut && CGRectIntersectsRect(frame, LibretroSkinCGRect(other.frame))) isolated = NO;
    }
    if (isolated) { layers.cropPreparing = YES; [candidates addObject:layers]; }
  }
  if (candidates.count == 0) return;
  NSUInteger generation = _imageGeneration;
  // Copy geometry now; a resize must not mutate what the worker reads.
  NSMutableArray<NSValue *> *frames = [NSMutableArray array];
  for (LibretroSkinItemLayers *layers in candidates) [frames addObject:[NSValue valueWithCGRect:CGRectInset(LibretroSkinCGRect(layers.laidOut.frame), -6, -6)]];
  __weak LibretroSkinRenderer *weakSelf = self;
  dispatch_async(LibretroSkinQueue(), ^{
    NSMutableArray<NSDictionary *> *crops = [NSMutableArray array];
    CGFloat sx = CGImageGetWidth(background.CGImage) / skin.size.width;
    CGFloat sy = CGImageGetHeight(background.CGImage) / skin.size.height;
    for (NSUInteger index = 0; index < candidates.count; index++) {
      CGRect frame = frames[index].CGRectValue;
      CGRect pixels = CGRectMake((frame.origin.x-skin.origin.x)*sx, (frame.origin.y-skin.origin.y)*sy,
                                frame.size.width*sx, frame.size.height*sy);
      CGImageRef underlay = NULL;
      CGImageRef image = LibretroSkinCreateButtonCrop(background.CGImage, pixels, &underlay);
      if (image == NULL) continue;
      // Integral crop geometry is used for both the mask and its replacement,
      // avoiding fractional-pixel remnants of the original painted control.
      CGRect integral = CGRectIntegral(pixels);
      CGRect exact = CGRectMake(skin.origin.x+integral.origin.x/sx, skin.origin.y+integral.origin.y/sy,
                               integral.size.width/sx, integral.size.height/sy);
      [crops addObject:@{@"index":@(index), @"frame":[NSValue valueWithCGRect:exact],
                        @"image":[UIImage imageWithCGImage:image],
                        @"underlay":[UIImage imageWithCGImage:underlay]}];
      CGImageRelease(image);
      CGImageRelease(underlay);
    }
    dispatch_async(dispatch_get_main_queue(), ^{
      LibretroSkinRenderer *renderer = weakSelf;
      if (renderer == nil || renderer->_imageGeneration != generation) return;
      [CATransaction begin];
      [CATransaction setDisableActions:YES];
      for (LibretroSkinItemLayers *layers in candidates) { layers.cropPreparing = NO; layers.cropAttempted = YES; }
      for (NSDictionary *crop in crops) {
        LibretroSkinItemLayers *layers = candidates[[crop[@"index"] unsignedIntegerValue]];
        if (![renderer->_items containsObject:layers] || layers.extracted) continue;
        CGRect exact = [crop[@"frame"] CGRectValue];
        layers.extracted = YES;
        layers.backplate = [CALayer layer];
        // Cover the mask's antialiased edge with one physical pixel of the
        // same opaque background. Two complementary translucent edges alone
        // leave a dark seam. Translucent skins keep their original backdrop.
        CGFloat overlap = 1.0 / renderer->_scale;
        layers.backplate.frame = CGRectIntersection(CGRectInset(exact, -overlap, -overlap), skin);
        layers.backplate.contents = (__bridge id)[crop[@"underlay"] CGImage];
        layers.backplate.contentsGravity = kCAGravityResize;
        // Backplate stays fixed below the animated face.
        [layers.container insertSublayer:layers.backplate below:layers.artwork];
        layers.image = LibretroSkinPlainLayer(renderer->_scale);
        layers.image.frame = exact;
        layers.image.contents = (__bridge id)[crop[@"image"] CGImage];
        [layers.artwork addSublayer:layers.image];
        [renderer applyStateToLayers:layers];
      }
      [renderer updateBackgroundMask];
      [renderer preparePressureItems];
      [CATransaction commit];
    });
  });
}

- (void)setStickVectors:(NSDictionary<NSString *, NSValue *> *)vectors {
  NSDictionary<NSString *, NSValue *> *next = [vectors isKindOfClass:[NSDictionary class]] ? [vectors copy] : @{};
  if ([next isEqualToDictionary:_stickVectors]) return;
  NSDictionary<NSString *, NSValue *> *previous = _stickVectors;
  _stickVectors = next;
  [CATransaction begin];
  [CATransaction setDisableActions:YES];
  for (LibretroSkinItemLayers *layers in _items) {
    if (layers.knob == nil && layers.knobImage == nil) continue;
    if (next[layers.identifier] == nil && previous[layers.identifier] == nil) continue;
    [self positionKnobOfLayers:layers];
  }
  [CATransaction commit];
}

/// Deflection of a thumbstick item (CGPointZero when released or editing).
- (CGPoint)stickVectorForIdentifier:(NSString *)identifier {
  if (_editing || identifier.length == 0) return CGPointZero;
  id value = _stickVectors[identifier];
  if (![value isKindOfClass:[NSValue class]] || strcmp([(NSValue *)value objCType], @encode(CGPoint)) != 0) {
    return CGPointZero;
  }
  CGPoint vector = [(NSValue *)value CGPointValue];
  if (!isfinite(vector.x) || !isfinite(vector.y)) return CGPointZero;
  return vector;
}

/// Moves the knob layers with the stick: same size, only the position
/// changes (no new path or image).
- (void)positionKnobOfLayers:(LibretroSkinItemLayers *)layers {
  CGRect knob = LibretroSkinKnobRect(layers.laidOut, [self stickVectorForIdentifier:layers.identifier]);
  if (CGRectIsEmpty(knob)) return;
  CGPoint center = CGPointMake(CGRectGetMidX(knob), CGRectGetMidY(knob));
  layers.knob.position = center;
  layers.knobImage.position = center;
}

- (void)setEditing:(BOOL)editing selectedItem:(NSString *)itemIdentifier {
  BOOL finished = _editing && !editing;
  _editing = editing;
  _selectedItem = [itemIdentifier isKindOfClass:[NSString class]] ? [itemIdentifier copy] : nil;
  [CATransaction begin];
  [CATransaction setDisableActions:YES];
  for (LibretroSkinItemLayers *layers in _items) {
    if (finished) {
      // Images were only stretched while editing: rasterise them now at
      // their final size.
      [self updateLayers:layers];
    } else {
      [self applyStateToLayers:layers];
    }
  }
  [CATransaction commit];
}

#pragma mark - Images

/// Shows the image of `path` rasterised for `points` in `layer` (and in
/// `mask`). The previous contents stay until the new image is ready. With
/// `force` NO (editing), a layer that already shows an image keeps it,
/// stretched to its new frame.
- (void)loadImageAtPath:(NSString *)path
                 points:(CGSize)points
                  layer:(CALayer *)layer
                   mask:(CALayer *)mask
                  force:(BOOL)force {
  if (path.length == 0) {
    layer.contents = nil;
    mask.contents = nil;
    [layer setValue:nil forKey:LibretroSkinImageKey];
    return;
  }
  if (!force && layer.contents != nil) return;
  size_t width = 0, height = 0;
  if (!LibretroSkinPixelSize(points, _scale, &width, &height)) return;
  NSString *key = LibretroSkinCacheKey(path, width, height);
  NSString *current = [layer valueForKey:LibretroSkinImageKey];
  if ([current isKindOfClass:[NSString class]] && [current isEqualToString:key]) return;
  [layer setValue:key forKey:LibretroSkinImageKey];
  UIImage *cached = [LibretroSkinMemoryCache() objectForKey:key];
  if (cached != nil) {
    layer.contents = (__bridge id)cached.CGImage;
    mask.contents = (__bridge id)cached.CGImage;
    [layer setValue:key forKey:@"neostationSkinReadyKey"];
    return;
  }
  NSString *cacheDirectory = _cacheDirectory;
  __weak LibretroSkinRenderer *weakRenderer = self;
  __weak CALayer *weakLayer = layer;
  __weak CALayer *weakMask = mask;
  dispatch_async(LibretroSkinQueue(), ^{
    UIImage *image = LibretroSkinLoadImage(path, width, height, key, cacheDirectory);
    dispatch_async(dispatch_get_main_queue(), ^{
      CALayer *target = weakLayer;
      if (target == nil) return;
      NSString *expected = [target valueForKey:LibretroSkinImageKey];
      if (![expected isKindOfClass:[NSString class]] || ![expected isEqualToString:key]) return;
      [CATransaction begin];
      [CATransaction setDisableActions:YES];
      target.contents = (__bridge id)image.CGImage;
      [target setValue:key forKey:@"neostationSkinReadyKey"];
      weakMask.contents = (__bridge id)image.CGImage;
      [CATransaction commit];
      LibretroSkinRenderer *renderer = weakRenderer;
      if (renderer != nil) {
        if (target == renderer->_backgroundLayer) [renderer preparePaintedItems];
        [renderer preparePressureItems];
      }

    });
  });
}

+ (void)purgeCacheForSkinDirectory:(NSString *)directory cacheDirectory:(NSString *)cacheDirectory {
  // Keys are hashes: drop the whole memory cache, it refills on demand.
  [LibretroSkinMemoryCache() removeAllObjects];
  if (![directory isKindOfClass:[NSString class]] || directory.length == 0) return;
  NSString *folder = [cacheDirectory isKindOfClass:[NSString class]] ? LibretroSkinCacheFolder(cacheDirectory) : nil;
  if (folder == nil) return;
  NSString *root = directory.stringByStandardizingPath;
  NSString *prefix = [root hasSuffix:@"/"] ? root : [root stringByAppendingString:@"/"];
  dispatch_async(LibretroSkinQueue(), ^{
    NSFileManager *manager = [NSFileManager defaultManager];
    for (NSString *name in [manager contentsOfDirectoryAtPath:folder error:nil]) {
      if (![name.pathExtension isEqualToString:@"source"]) continue;
      NSString *sidecar = [folder stringByAppendingPathComponent:name];
      NSString *source = [NSString stringWithContentsOfFile:sidecar encoding:NSUTF8StringEncoding error:nil];
      if (source != nil && ![source hasPrefix:prefix] && ![source isEqualToString:root]) continue;
      [manager removeItemAtPath:sidecar error:nil];
      NSString *png = [sidecar.stringByDeletingPathExtension stringByAppendingPathExtension:@"png"];
      [manager removeItemAtPath:png error:nil];
    }
  });
}

#pragma mark - Previews

/// Draws one default-skin control (vector) into `context` (UIKit
/// coordinates). Skin queue.
static void LibretroSkinDrawVectorItem(CGContextRef context, LibretroLaidOutItem *laidOut) {
  LibretroSkinItem *item = laidOut.item;
  CGRect frame = LibretroSkinCGRect(laidOut.frame);
  if (CGRectIsEmpty(frame)) return;
  CGContextSaveGState(context);
  CGContextTranslateCTM(context, frame.origin.x, frame.origin.y);
  CGPathRef shape = LibretroSkinCreateShapePath(item.shape, frame.size);
  UIColor *fill = LibretroSkinColor(item.fillColor);
  CGContextSetFillColorWithColor(context, fill.CGColor);
  CGContextAddPath(context, shape);
  CGContextFillPath(context);
  CGPathRelease(shape);
  if (item.shape == LibretroSkinItemShapeDPad) {
    CGPathRef arrows = LibretroSkinCreateArrowsPath(frame.size);
    UIColor *color = item.labelColor != 0 ? LibretroSkinColor(item.labelColor) : [UIColor colorWithWhite:1 alpha:0.6];
    CGContextSetFillColorWithColor(context, color.CGColor);
    CGContextAddPath(context, arrows);
    CGContextFillPath(context);
    CGPathRelease(arrows);
  }
  CGContextRestoreGState(context);
  if (item.kind == LibretroSkinItemKindThumbstick) {
    CGRect knob = LibretroSkinKnobRect(laidOut, CGPointZero);
    UIColor *color = LibretroSkinLighterColor(item.fillColor, 0.3);
    CGContextSetFillColorWithColor(context, color.CGColor);
    CGContextFillEllipseInRect(context, knob);
  }
  if (LibretroSkinHasLabel(item)) {
    CGFloat size = LibretroSkinLabelFontSize(item.label, item.shape, frame.size);
    if (size > 0) {
      UIFont *font = [UIFont systemFontOfSize:size weight:UIFontWeightSemibold];
      NSMutableParagraphStyle *paragraph = [[NSMutableParagraphStyle alloc] init];
      paragraph.alignment = NSTextAlignmentCenter;
      UIColor *color = item.labelColor != 0 ? LibretroSkinColor(item.labelColor) : UIColor.whiteColor;
      NSDictionary *attributes = @{
        NSFontAttributeName : font,
        NSForegroundColorAttributeName : color,
        NSParagraphStyleAttributeName : paragraph,
      };
      CGFloat lineHeight = ceil(font.lineHeight);
      CGRect textRect = CGRectMake(frame.origin.x, frame.origin.y + (frame.size.height - lineHeight) / 2,
                                   frame.size.width, lineHeight);
      [item.label drawInRect:textRect withAttributes:attributes];
    }
  }
}

+ (void)renderPreviewForRepresentation:(LibretroSkinRepresentation *)representation
                                  size:(CGSize)size
                                 scale:(CGFloat)scale
                            safeInsets:(UIEdgeInsets)safeInsets
                        cacheDirectory:(NSString *)cacheDirectory
                            completion:(void (^)(UIImage *_Nullable image))completion {
  void (^finish)(UIImage *) = [completion copy];
  if (finish == nil) return;
  if (representation == nil || !(size.width >= 1) || !(size.height >= 1) || !isfinite(size.width) ||
      !isfinite(size.height)) {
    dispatch_async(dispatch_get_main_queue(), ^{
      finish(nil);
    });
    return;
  }
  CGFloat pixelScale = scale > 0 && isfinite(scale) ? MIN(scale, 4) : 2;
  CGFloat longest = MAX(size.width, size.height);
  if (longest * pixelScale > LibretroSkinMaximumPixels) pixelScale = (CGFloat)LibretroSkinMaximumPixels / longest;
  NSString *cache = [cacheDirectory isKindOfClass:[NSString class]] ? [cacheDirectory copy] : @"";
  LibretroInsets insets = {safeInsets.top, safeInsets.left, safeInsets.bottom, safeInsets.right};
  dispatch_async(LibretroSkinQueue(), ^{
    UIImage *preview = nil;
    @autoreleasepool {
      LibretroSkinLayoutResult *layout = [LibretroSkinLayout layoutRepresentation:representation
                                                                         viewSize:(LibretroSize){size.width, size.height}
                                                                       safeInsets:insets
                                                                        overrides:nil];
      // Images first (cached), then one drawing pass.
      UIImage *background = nil;
      CGRect skinRect = LibretroSkinCGRect(layout.skinRect);
      size_t width = 0, height = 0;
      if (!representation.generated && representation.backgroundPath.length > 0 &&
          LibretroSkinPixelSize(skinRect.size, pixelScale, &width, &height)) {
        NSString *key = LibretroSkinCacheKey(representation.backgroundPath, width, height);
        background = LibretroSkinLoadImage(representation.backgroundPath, width, height, key, cache);
      }
      NSMutableDictionary<NSString *, UIImage *> *images = [NSMutableDictionary dictionary];
      NSMutableDictionary<NSString *, UIImage *> *knobs = [NSMutableDictionary dictionary];
      for (LibretroLaidOutItem *laidOut in layout.items) {
        LibretroSkinItem *item = laidOut.item;
        if (item.kind == LibretroSkinItemKindTouchScreen || LibretroSkinIsVector(item) || item.identifier.length == 0) {
          continue;
        }
        CGRect assetFrame = LibretroSkinCGRect(laidOut.assetFrame);
        if (CGRectIsEmpty(assetFrame)) assetFrame = LibretroSkinCGRect(laidOut.frame);
        if (item.assetPath.length > 0 && LibretroSkinPixelSize(assetFrame.size, pixelScale, &width, &height)) {
          NSString *key = LibretroSkinCacheKey(item.assetPath, width, height);
          UIImage *image = LibretroSkinLoadImage(item.assetPath, width, height, key, cache);
          if (image != nil) images[item.identifier] = image;
        }
        CGRect knob = LibretroSkinKnobRect(laidOut, CGPointZero);
        if (item.kind == LibretroSkinItemKindThumbstick && item.thumbstickAssetPath.length > 0 &&
            LibretroSkinPixelSize(knob.size, pixelScale, &width, &height)) {
          NSString *key = LibretroSkinCacheKey(item.thumbstickAssetPath, width, height);
          UIImage *image = LibretroSkinLoadImage(item.thumbstickAssetPath, width, height, key, cache);
          if (image != nil) knobs[item.identifier] = image;
        }
      }

      // A plain bitmap context made the current UIKit context (thread-safe,
      // unlike renderer formats that consult the main screen), flipped to
      // UIKit coordinates in points.
      size_t pixelWidth = (size_t)ceil(size.width * pixelScale);
      size_t pixelHeight = (size_t)ceil(size.height * pixelScale);
      CGColorSpaceRef space = CGColorSpaceCreateWithName(kCGColorSpaceSRGB);
      CGContextRef context =
          CGBitmapContextCreate(NULL, pixelWidth, pixelHeight, 8, 0, space,
                                (CGBitmapInfo)kCGImageAlphaNoneSkipFirst | (CGBitmapInfo)kCGBitmapByteOrder32Little);
      CGColorSpaceRelease(space);
      if (context != NULL) {
        CGContextTranslateCTM(context, 0, (CGFloat)pixelHeight);
        CGContextScaleCTM(context, pixelScale, -pixelScale);
        UIGraphicsPushContext(context);
        CGContextSetRGBFillColor(context, 0, 0, 0, 1);
        CGContextFillRect(context, CGRectMake(0, 0, size.width, size.height));
        // Grey placeholders where the game picture goes (below the skin,
        // whose screen areas are transparent).
        CGContextSetRGBFillColor(context, 0.30, 0.30, 0.32, 1);
        for (LibretroLaidOutScreen *screen in layout.screens) {
          CGRect container = LibretroSkinCGRect(screen.container);
          if (!CGRectIsEmpty(container)) CGContextFillRect(context, container);
        }
        CGRect panel = LibretroSkinCGRect(layout.panelFrame);
        if (representation.panelColor != 0 && !CGRectIsEmpty(panel)) {
          UIColor *color = LibretroSkinColor(representation.panelColor);
          CGContextSetFillColorWithColor(context, color.CGColor);
          CGContextFillRect(context, panel);
        }
        if (background != nil && !CGRectIsEmpty(skinRect)) [background drawInRect:skinRect];
        for (LibretroLaidOutItem *laidOut in layout.items) {
          LibretroSkinItem *item = laidOut.item;
          if (item.kind == LibretroSkinItemKindTouchScreen) continue;
          if (LibretroSkinIsVector(item)) {
            LibretroSkinDrawVectorItem(context, laidOut);
            continue;
          }
          UIImage *image = item.identifier.length > 0 ? images[item.identifier] : nil;
          if (image != nil) {
            CGRect assetFrame = LibretroSkinCGRect(laidOut.assetFrame);
            if (CGRectIsEmpty(assetFrame)) assetFrame = LibretroSkinCGRect(laidOut.frame);
            [image drawInRect:assetFrame];
          }
          UIImage *knob = item.identifier.length > 0 ? knobs[item.identifier] : nil;
          if (knob != nil) [knob drawInRect:LibretroSkinKnobRect(laidOut, CGPointZero)];
        }
        UIGraphicsPopContext();
        CGImageRef rendered = CGBitmapContextCreateImage(context);
        CGContextRelease(context);
        if (rendered != NULL) {
          preview = [UIImage imageWithCGImage:rendered scale:pixelScale orientation:UIImageOrientationUp];
          CGImageRelease(rendered);
        }
      }
    }
    dispatch_async(dispatch_get_main_queue(), ^{
      finish(preview);
    });
  });
}

@end
