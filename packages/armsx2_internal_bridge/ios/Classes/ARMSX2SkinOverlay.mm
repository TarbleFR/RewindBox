// SPDX-License-Identifier: GPL-3.0-or-later
// Controller skins for the embedded ARMSX2 (PlayStation 2), docs/dolphin-skins.md.
//
// The same .manicskin / .deltaskin files, folders and selection files as the
// libretro and Dolphin skins: Documents/Libretro/Skins/<id>/info.json and
// Documents/Libretro/Config/Frontend/ps2.json ({"console": {"skin.portrait": id,
// "skin.landscape": id}, "games": {key: {...}}}; the game's choice first, then
// the console's, "default" meaning none). This overlay is the ARMSX2 pod's own
// reader and renderer (it cannot import the Dolphin pod): it draws the skin
// over the session, sends the touches to the same pad inputs as the stock
// controls (ARMSX2PadButton indices through `buttonChanged`, both sticks through
// `sticksChanged`) and tells the session where the game goes. Without a skin
// for the console ("default" or nothing stored) it is never created.
//
// PlayStation names only (see ARMSX2SkinCanonicalInput); L3 and R3 are targets
// of their own, a stick finger only moves the stick.
#import "ARMSX2SkinOverlay.h"
#import "ARMSX2OrientationPolicy.h"
#import "ARMSX2SkinHitTest.h"
#import <CoreGraphics/CoreGraphics.h>
#include <cmath>
#include <vector>

#pragma mark - Input table (DolphinSkins 'ps2', lib/services/dolphin_skins.dart)

/// Lower case, letters and digits only (Dart: toLowerCase, [^a-z0-9] removed).
static NSString* A2SkinKey(NSString* raw) {
  NSString* lower = raw.lowercaseString;
  NSMutableString* key = [NSMutableString stringWithCapacity:lower.length];
  for (NSUInteger i = 0; i < lower.length; i++) {
    const unichar c = [lower characterAtIndex:i];
    if ((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9')) [key appendFormat:@"%C", c];
  }
  return key;
}

static NSArray<NSString*>* A2SkinDirections(void) { return @[ @"Up", @"Down", @"Left", @"Right" ]; }

/// ARMSX2PadButton of each digital logical input (ARMSX2Bridge.h:
/// Up 0, Down 1, Left 2, Right 3, Cross 4, Circle 5, Square 6, Triangle 7,
/// L1 8, R1 9, L2 10, R2 11, Start 12, Select 13, L3 14, R3 15).
static NSDictionary<NSString*, NSNumber*>* A2SkinButtonIds(void) {
  static NSDictionary<NSString*, NSNumber*>* ids;
  static dispatch_once_t once;
  dispatch_once(&once, ^{
    ids = @{
      @"up" : @0, @"down" : @1, @"left" : @2, @"right" : @3, @"cross" : @4, @"circle" : @5, @"square" : @6,
      @"triangle" : @7, @"l1" : @8, @"r1" : @9, @"l2" : @10, @"r2" : @11, @"start" : @12, @"select" : @13,
      @"l3" : @14, @"r3" : @15,
    };
  });
  return ids;
}

/// The logical input of a raw skin input, or nil when the console has
/// nothing for it. Only PlayStation names: nothing Nintendo is guessed.
NSString* ARMSX2SkinCanonicalInput(NSString* raw) {
  if (![raw isKindOfClass:NSString.class]) return nil;
  NSString* key = A2SkinKey(raw);
  for (NSString* prefix in @[ @"leftthumbstick", @"analogstick", @"leftstick", @"leftanalog", @"analog", @"thumbstick" ]) {
    for (NSString* direction in A2SkinDirections()) {
      if ([key isEqualToString:[prefix stringByAppendingString:direction.lowercaseString]])
        return [@"stick" stringByAppendingString:direction];
    }
  }
  for (NSString* prefix in @[ @"rightthumbstick", @"rightstick", @"rightanalog", @"cstick", @"c" ]) {
    for (NSString* direction in A2SkinDirections()) {
      if ([key isEqualToString:[prefix stringByAppendingString:direction.lowercaseString]])
        return [@"rstick" stringByAppendingString:direction];
    }
  }
  for (NSString* direction in A2SkinDirections()) {
    NSString* name = direction.lowercaseString;
    if ([key isEqualToString:name] || [key isEqualToString:[@"dpad" stringByAppendingString:name]]) return name;
  }
  if ([@[ @"menu", @"pause", @"options" ] containsObject:key]) return @"menu";
  return A2SkinButtonIds()[key] != nil && ![@[ @"up", @"down", @"left", @"right" ] containsObject:key] ? key : nil;
}

NSString* ARMSX2SkinConsoleOfGameType(NSString* gameTypeIdentifier) {
  if (![gameTypeIdentifier isKindOfClass:NSString.class]) return nil;
  NSString* trimmed = [gameTypeIdentifier stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
  NSString* key = A2SkinKey([trimmed componentsSeparatedByString:@"."].lastObject ?: @"");
  return [@[ @"ps2", @"playstation2", @"sonyplaystation2", @"armsx2", @"pcsx2" ] containsObject:key] ? @"ps2" : nil;
}

/// "stick" (left) or "rstick" for `stickUp`, `rstickLeft`…; nil else.
static NSString* A2SkinFamily(NSString* canonical, NSString** direction) {
  for (NSString* family in @[ @"rstick", @"stick" ]) {
    for (NSString* d in A2SkinDirections()) {
      if ([canonical isEqualToString:[family stringByAppendingString:d]]) {
        if (direction) *direction = d.lowercaseString;
        return family;
      }
    }
  }
  return nil;
}

#pragma mark - Skin model

typedef NS_ENUM(NSInteger, A2SkinItemKind) {
  A2SkinItemKindButtons = 0,  // every input of the list together
  A2SkinItemKindDPad = 1,     // up / down / left / right, digital
  A2SkinItemKindStick = 2,    // the four directions of one analog family
};

@interface A2SkinItem : NSObject
@property(nonatomic, assign) A2SkinItemKind kind;
@property(nonatomic, assign) CGRect frame;     // mapping points
@property(nonatomic, assign) CGRect hitFrame;  // frame and extendedEdges
@property(nonatomic, copy) NSArray<NSString*>* inputs;
@property(nonatomic, copy) NSDictionary<NSString*, NSString*>* directions;
@property(nonatomic, copy, nullable) NSString* family;
@property(nonatomic, copy, nullable) NSString* assetPath;
@property(nonatomic, copy, nullable) NSString* pressedAssetPath;
@property(nonatomic, copy, nullable) NSString* knobPath;
@property(nonatomic, assign) CGSize knobSize;
// Alpha of the normal sprite (row-major bytes, alphaSize pixels), nil when the
// item has none or it is opaque: the drawn shape answers a touch first
// (ARMSX2SkinHitTest.h).
@property(nonatomic, strong, nullable) NSData* alphaMap;
@property(nonatomic, assign) CGSize alphaSize;
@end
@implementation A2SkinItem
@end

/// The normal sprite's alpha, at most 192 pixels on its long side; nil when
/// it cannot be read or has no transparent pixel (then the frame is the shape).
static NSData* A2SkinAlphaMap(NSString* path, CGSize* size) {
  if (path == nil) return nil;
  UIImage* image = [UIImage imageWithContentsOfFile:path];
  CGImageRef cg = image.CGImage;
  if (cg == NULL) return nil;
  const size_t sourceWidth = CGImageGetWidth(cg), sourceHeight = CGImageGetHeight(cg);
  if (sourceWidth == 0 || sourceHeight == 0) return nil;
  const double scale = MIN(1.0, 192.0 / (double)MAX(sourceWidth, sourceHeight));
  const size_t width = MAX((size_t)1, (size_t)llround((double)sourceWidth * scale));
  const size_t height = MAX((size_t)1, (size_t)llround((double)sourceHeight * scale));
  NSMutableData* data = [NSMutableData dataWithLength:width * height];
  CGContextRef context = CGBitmapContextCreate(data.mutableBytes, width, height, 8, width, NULL,
                                               (CGBitmapInfo)kCGImageAlphaOnly);
  if (context == NULL) return nil;
  CGContextSetInterpolationQuality(context, kCGInterpolationNone);
  CGContextDrawImage(context, CGRectMake(0, 0, width, height), cg);
  CGContextRelease(context);
  // Bitmap rows are top first, as UIKit draws them.
  const uint8_t* bytes = (const uint8_t*)data.bytes;
  BOOL transparent = NO;
  for (size_t i = 0; i < width * height && !transparent; i++) transparent = bytes[i] < 128;
  if (!transparent) return nil;
  *size = CGSizeMake(width, height);
  return data;
}

@interface A2SkinRepresentation : NSObject
@property(nonatomic, assign) BOOL portrait;
@property(nonatomic, assign) CGSize mappingSize;
@property(nonatomic, copy, nullable) NSString* backgroundPath;
@property(nonatomic, copy) NSArray<A2SkinItem*>* items;
@property(nonatomic, assign) BOOL hasScreen;
@property(nonatomic, assign) CGRect screen;
/// The pack's own cutout of its screen (`screens[].screenCutout`), nil without one.
@property(nonatomic, copy, nullable) NSString* cutoutPath;
@property(nonatomic, assign) BOOL translucent;
@end
@implementation A2SkinRepresentation
@end

static BOOL A2SkinNumber(id value, CGFloat* out) {
  if (![value isKindOfClass:NSNumber.class]) return NO;
  const double number = [(NSNumber*)value doubleValue];
  if (!std::isfinite(number)) return NO;
  *out = (CGFloat)number;
  return YES;
}

static BOOL A2SkinSize(id value, CGSize* out) {
  if (![value isKindOfClass:NSDictionary.class]) return NO;
  CGFloat width = 0, height = 0;
  if (!A2SkinNumber(value[@"width"], &width) || !A2SkinNumber(value[@"height"], &height)) return NO;
  if (!(width > 0) || !(height > 0)) return NO;
  *out = CGSizeMake(width, height);
  return YES;
}

static BOOL A2SkinRect(id value, CGRect* out) {
  if (![value isKindOfClass:NSDictionary.class]) return NO;
  CGFloat x = 0, y = 0;
  CGSize size;
  if (!A2SkinNumber(value[@"x"], &x) || !A2SkinNumber(value[@"y"], &y) || !A2SkinSize(value, &size)) return NO;
  *out = CGRectMake(x, y, size.width, size.height);
  return YES;
}

/// extendedEdges, each missing or invalid side taken from `fallback`.
static UIEdgeInsets A2SkinEdges(id value, UIEdgeInsets fallback) {
  if (![value isKindOfClass:NSDictionary.class]) return fallback;
  UIEdgeInsets edges = fallback;
  CGFloat side = 0;
  if (A2SkinNumber(value[@"top"], &side) && side >= 0) edges.top = side;
  if (A2SkinNumber(value[@"left"], &side) && side >= 0) edges.left = side;
  if (A2SkinNumber(value[@"bottom"], &side) && side >= 0) edges.bottom = side;
  if (A2SkinNumber(value[@"right"], &side) && side >= 0) edges.right = side;
  return edges;
}

/// A file of the skin's own folder; nil for anything outside it.
static NSString* A2SkinFile(NSString* root, id name) {
  if (![name isKindOfClass:NSString.class] || [name length] == 0 || [name length] > 255) return nil;
  if ([name hasPrefix:@"/"] || [[name pathComponents] containsObject:@".."]) return nil;
  NSString* base = root.stringByStandardizingPath;
  NSString* path = [base stringByAppendingPathComponent:name].stringByStandardizingPath;
  if (![path hasPrefix:[base stringByAppendingString:@"/"]]) return nil;
  BOOL directory = NO;
  if (![NSFileManager.defaultManager fileExistsAtPath:path isDirectory:&directory] || directory) return nil;
  return path;
}

/// Background of a representation: the resizable PDF first, then the
/// largest bitmap.
static NSString* A2SkinAsset(NSString* root, id assets) {
  if ([assets isKindOfClass:NSString.class]) return A2SkinFile(root, assets);
  if (![assets isKindOfClass:NSDictionary.class]) return nil;
  for (NSString* key in @[ @"resizable", @"large", @"medium", @"small", @"normal" ]) {
    NSString* path = A2SkinFile(root, assets[key]);
    if (path != nil) return path;
  }
  return nil;
}

static NSDictionary* A2SkinReadJSON(NSString* path) {
  NSData* data = [NSData dataWithContentsOfFile:path options:NSDataReadingMappedIfSafe error:nil];
  if (data == nil || data.length > 4 * 1024 * 1024) return nil;
  id object = [NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
  return [object isKindOfClass:NSDictionary.class] ? object : nil;
}

/// LibretroSkinService.isInstalledId: ^[a-z0-9-]+$ and never "default".
static BOOL A2SkinIsInstalledId(NSString* identifier) {
  if (![identifier isKindOfClass:NSString.class] || identifier.length == 0 || identifier.length > 128) return NO;
  if ([identifier isEqualToString:@"default"]) return NO;
  NSCharacterSet* allowed = [NSCharacterSet characterSetWithCharactersInString:@"abcdefghijklmnopqrstuvwxyz0123456789-"];
  return [identifier rangeOfCharacterFromSet:allowed.invertedSet].location == NSNotFound;
}

/// The skin chosen for `orientation`: the game's choice when it has one for
/// that key (even "default"), else the console's.
static NSString* A2SkinSelected(NSDictionary* document, NSString* gameKey, NSString* orientation) {
  NSString* key = [@"skin." stringByAppendingString:orientation];
  id value = nil;
  NSDictionary* games = document[@"games"];
  if (gameKey.length > 0 && [games isKindOfClass:NSDictionary.class]) {
    NSDictionary* scope = games[gameKey];
    if ([scope isKindOfClass:NSDictionary.class]) value = scope[key];
  }
  if (value == nil) {
    NSDictionary* console = document[@"console"];
    if ([console isKindOfClass:NSDictionary.class]) value = console[key];
  }
  return A2SkinIsInstalledId(value) ? value : nil;
}

/// The layout of `orientation` for this device: the iPhone's (edge-to-edge
/// on a tall screen, else standard), an iPad layout when there is none.
static NSDictionary* A2SkinLayoutFor(NSDictionary* info, NSString* orientation) {
  NSDictionary* representations = info[@"representations"];
  if (![representations isKindOfClass:NSDictionary.class]) return nil;
  const BOOL pad = UIDevice.currentDevice.userInterfaceIdiom == UIUserInterfaceIdiomPad;
  const CGSize native = UIScreen.mainScreen.nativeBounds.size;
  const CGFloat shortSide = MIN(native.width, native.height);
  const BOOL tall = shortSide > 0 && MAX(native.width, native.height) / shortSide > 2.0;
  NSArray* devices = pad ? @[ @"ipad", @"iphone" ] : @[ @"iphone", @"ipad" ];
  NSArray* displays = tall || pad ? @[ @"edgeToEdge", @"standard", @"splitView" ]
                                  : @[ @"standard", @"edgeToEdge", @"splitView" ];
  for (NSString* device in devices) {
    NSDictionary* byDisplay = representations[device];
    if (![byDisplay isKindOfClass:NSDictionary.class]) continue;
    for (NSString* display in displays) {
      NSDictionary* byOrientation = byDisplay[display];
      if (![byOrientation isKindOfClass:NSDictionary.class]) continue;
      NSDictionary* layout = byOrientation[orientation];
      if ([layout isKindOfClass:NSDictionary.class]) return layout;
    }
  }
  return nil;
}

static A2SkinRepresentation* A2SkinParse(NSDictionary* layout, NSString* root, BOOL portrait) {
  CGSize mapping;
  if (!A2SkinSize(layout[@"mappingSize"], &mapping)) return nil;
  const UIEdgeInsets defaultEdges = A2SkinEdges(layout[@"extendedEdges"], UIEdgeInsetsZero);
  NSMutableArray<A2SkinItem*>* items = [NSMutableArray array];
  NSArray* objects = [layout[@"items"] isKindOfClass:NSArray.class] ? layout[@"items"] : @[];
  NSUInteger usable = 0;
  for (NSDictionary* object in objects) {
    if (![object isKindOfClass:NSDictionary.class]) continue;
    CGRect frame;
    if (!A2SkinRect(object[@"frame"], &frame)) continue;
    A2SkinItem* item = [A2SkinItem new];
    item.frame = frame;
    const UIEdgeInsets edges = A2SkinEdges(object[@"extendedEdges"], defaultEdges);
    item.hitFrame = CGRectMake(frame.origin.x - edges.left, frame.origin.y - edges.top,
                               frame.size.width + edges.left + edges.right, frame.size.height + edges.top + edges.bottom);
    item.inputs = @[];
    item.directions = @{};
    id inputs = object[@"inputs"];
    if ([inputs isKindOfClass:NSDictionary.class]) {
      NSMutableDictionary<NSString*, NSString*>* directions = [NSMutableDictionary dictionary];
      NSString* family = nil;
      BOOL analog = YES;
      for (NSString* d in A2SkinDirections()) {
        NSString* name = d.lowercaseString;
        NSString* canonical = ARMSX2SkinCanonicalInput([inputs objectForKey:name]);
        if (canonical == nil) continue;
        directions[name] = canonical;
        NSString* direction = nil;
        NSString* own = A2SkinFamily(canonical, &direction);
        if (own == nil || ![direction isEqualToString:name] || (family != nil && ![family isEqualToString:own])) analog = NO;
        family = family ?: own;
      }
      item.directions = directions;
      item.kind = analog && family != nil ? A2SkinItemKindStick : A2SkinItemKindDPad;
      if (item.kind == A2SkinItemKindStick) item.family = family;
      NSDictionary* thumbstick = object[@"thumbstick"];
      CGSize knob;
      if ([thumbstick isKindOfClass:NSDictionary.class] && A2SkinSize(thumbstick, &knob)) {
        item.knobPath = A2SkinFile(root, thumbstick[@"name"]);
        item.knobSize = knob;
      }
      if (directions.count > 0) usable++;
    } else if ([inputs isKindOfClass:NSArray.class]) {
      NSMutableArray<NSString*>* list = [NSMutableArray array];
      for (id raw in (NSArray*)inputs) {
        NSString* canonical = ARMSX2SkinCanonicalInput(raw);
        if (canonical != nil && ![list containsObject:canonical]) [list addObject:canonical];
      }
      item.kind = A2SkinItemKindButtons;
      item.inputs = list;
      if (list.count > 0) usable++;
    }
    id asset = object[@"asset"];
    if ([asset isKindOfClass:NSString.class]) {
      item.assetPath = A2SkinFile(root, asset);
    } else if ([asset isKindOfClass:NSDictionary.class]) {
      item.assetPath = A2SkinFile(root, asset[@"normal"]);
      item.pressedAssetPath = A2SkinFile(root, asset[@"pressed"]);
    }
    CGSize alphaSize = CGSizeZero;
    item.alphaMap = A2SkinAlphaMap(item.assetPath, &alphaSize);
    item.alphaSize = alphaSize;
    if (item.inputs.count == 0 && item.directions.count == 0 && item.assetPath == nil) continue;
    [items addObject:item];
  }
  if (usable == 0) return nil;
  A2SkinRepresentation* representation = [A2SkinRepresentation new];
  representation.portrait = portrait;
  representation.mappingSize = mapping;
  representation.items = items;
  representation.backgroundPath = A2SkinAsset(root, layout[@"assets"]);
  representation.translucent = [layout[@"translucent"] isKindOfClass:NSNumber.class] && [layout[@"translucent"] boolValue];
  CGRect screen;
  if (A2SkinRect(layout[@"gameScreenFrame"], &screen)) {
    // Legacy key: wins over `screens` (Delta).
    representation.hasScreen = YES;
    representation.screen = screen;
  } else if ([layout[@"screens"] isKindOfClass:NSArray.class]) {
    for (NSDictionary* entry in (NSArray*)layout[@"screens"]) {
      if ([entry isKindOfClass:NSDictionary.class] && A2SkinRect(entry[@"outputFrame"], &screen)) {
        representation.hasScreen = YES;
        representation.screen = screen;
        representation.cutoutPath = A2SkinFile(root, entry[@"screenCutout"]);
        break;
      }
    }
  }
  return representation;
}

#pragma mark - Images

/// First page of a PDF drawn at `points` (Delta stretches PDF assets).
static UIImage* A2SkinPDF(NSString* path, CGSize points) {
  CGPDFDocumentRef document = CGPDFDocumentCreateWithURL((__bridge CFURLRef)[NSURL fileURLWithPath:path]);
  if (document == NULL) return nil;
  CGPDFPageRef page = CGPDFDocumentGetPage(document, 1);
  const CGRect box = page != NULL ? CGPDFPageGetBoxRect(page, kCGPDFCropBox) : CGRectZero;
  UIImage* image = nil;
  if (page != NULL && box.size.width > 0 && box.size.height > 0) {
    UIGraphicsImageRendererFormat* format = [UIGraphicsImageRendererFormat preferredFormat];
    format.opaque = NO;
    image = [[[UIGraphicsImageRenderer alloc] initWithSize:points format:format]
        imageWithActions:^(UIGraphicsImageRendererContext* context) {
          CGContextRef cg = context.CGContext;
          CGContextTranslateCTM(cg, 0, points.height);
          CGContextScaleCTM(cg, points.width / box.size.width, -points.height / box.size.height);
          CGContextTranslateCTM(cg, -box.origin.x, -box.origin.y);
          CGContextDrawPDFPage(cg, page);
        }];
  }
  CGPDFDocumentRelease(document);
  return image;
}

static UIImage* A2SkinImage(NSString* path, CGSize points) {
  if (path == nil || !(points.width >= 1) || !(points.height >= 1)) return nil;
  if (points.width > 4096 || points.height > 4096) return nil;
  static NSCache<NSString*, UIImage*>* cache;
  static dispatch_once_t once;
  dispatch_once(&once, ^{
    cache = [NSCache new];
    cache.countLimit = 96;
  });
  const BOOL pdf = [path.pathExtension.lowercaseString isEqualToString:@"pdf"];
  NSString* key = pdf ? [NSString stringWithFormat:@"%@|%.0fx%.0f", path, points.width, points.height] : path;
  UIImage* image = [cache objectForKey:key];
  if (image == nil) {
    image = pdf ? A2SkinPDF(path, points) : [UIImage imageWithContentsOfFile:path];
    if (image != nil) [cache setObject:image forKey:key];
  }
  return image;
}

static CGRect A2SkinScaled(CGRect rect, CGSize mapping, CGRect skin) {
  const CGFloat sx = skin.size.width / mapping.width, sy = skin.size.height / mapping.height;
  return CGRectMake(skin.origin.x + rect.origin.x * sx, skin.origin.y + rect.origin.y * sy, rect.size.width * sx,
                    rect.size.height * sy);
}

static CGRect A2SkinAspectFit(CGRect bounds, CGFloat aspect) {
  if (!(aspect > 0) || !(bounds.size.width > 0) || !(bounds.size.height > 0)) return bounds;
  CGFloat width = bounds.size.width, height = width / aspect;
  if (height > bounds.size.height) {
    height = bounds.size.height;
    width = height * aspect;
  }
  return CGRectMake(bounds.origin.x + (bounds.size.width - width) / 2, bounds.origin.y + (bounds.size.height - height) / 2,
                    width, height);
}

#pragma mark - Overlay

@interface A2SkinTrack : NSObject
@property(nonatomic, assign) NSInteger item;  // index in the representation, -1 none
@property(nonatomic, assign) CGPoint location;
@end
@implementation A2SkinTrack
@end

@implementation ARMSX2SkinOverlay {
  A2SkinRepresentation* _portrait;
  A2SkinRepresentation* _landscape;
  A2SkinRepresentation* _current;
  CGSize _laidOutSize;
  UIEdgeInsets _laidOutInsets;
  CGRect _skinRect;
  UIImageView* _background;
  CAShapeLayer* _backgroundMask;
  CALayer* _cutoutMask;
  NSString* _cutoutPath;
  UIImage* _cutoutImage;
  NSMutableArray<UIImageView*>* _itemViews;
  NSMutableArray<UIImageView*>* _knobViews;
  NSMapTable<UITouch*, A2SkinTrack*>* _tracks;
  NSSet<NSString*>* _pressed;
  NSDictionary<NSString*, NSValue*>* _vectors;
  NSSet<NSNumber*>* _pressedItems;
  // D-pad items held now: item index -> its pressed directions (up, down, left, right).
  NSDictionary<NSNumber*, NSSet<NSString*>*>* _pressedArms;
  NSMutableDictionary<NSNumber*, UIImageView*>* _armViews;
  UIImpactFeedbackGenerator* _haptics;
}

- (instancetype)initWithGameKey:(NSString*)gameKey {
  self = [super initWithFrame:CGRectZero];
  if (!self) return nil;
  _tracks = [NSMapTable strongToStrongObjectsMapTable];
  _pressed = [NSSet set];
  _vectors = @{};
  _pressedItems = [NSSet set];
  _pressedArms = @{};
  _armViews = [NSMutableDictionary dictionary];
  _skinRect = CGRectNull;
  _screenFrame = CGRectNull;
  _laidOutSize = CGSizeZero;
  _haptics = [[UIImpactFeedbackGenerator alloc] initWithStyle:UIImpactFeedbackStyleLight];
  self.backgroundColor = UIColor.clearColor;
  self.multipleTouchEnabled = YES;
  self.accessibilityIdentifier = @"armsx2.skin.overlay";

  NSString* documents = NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES).firstObject;
  NSString* libretro = [documents stringByAppendingPathComponent:@"Libretro"];
  NSString* console = @"ps2";
  NSString* selectionPath = [[libretro stringByAppendingPathComponent:@"Config/Frontend"]
      stringByAppendingPathComponent:[console stringByAppendingString:@".json"]];
  NSDictionary* selection = documents.length > 0 ? A2SkinReadJSON(selectionPath) : nil;
  NSString* skins = [libretro stringByAppendingPathComponent:@"Skins"];
  for (NSString* orientation in @[ @"portrait", @"landscape" ]) {
    NSString* identifier = selection != nil ? A2SkinSelected(selection, gameKey, orientation) : nil;
    if (identifier == nil) continue;
    NSString* root = [skins stringByAppendingPathComponent:identifier];
    NSDictionary* info = A2SkinReadJSON([root stringByAppendingPathComponent:@"info.json"]);
    // Only a skin of this console (the import checked it; a skin may have
    // been replaced by another one since).
    if (info == nil || ![ARMSX2SkinConsoleOfGameType(info[@"gameTypeIdentifier"]) isEqualToString:console]) {
      NSLog(@"armsx2.skin.ignored %@ %@", orientation, identifier);
      continue;
    }
    NSDictionary* layout = A2SkinLayoutFor(info, orientation);
    A2SkinRepresentation* representation =
        layout != nil ? A2SkinParse(layout, root, [orientation isEqualToString:@"portrait"]) : nil;
    if (representation == nil) {
      NSLog(@"armsx2.skin.unusable %@ %@", orientation, identifier);
      continue;
    }
    if ([orientation isEqualToString:@"portrait"]) {
      _portrait = representation;
    } else {
      _landscape = representation;
    }
    NSLog(@"armsx2.skin.selected %@ %@", orientation, identifier);
  }

  _background = [UIImageView new];
  _background.contentMode = UIViewContentModeScaleToFill;
  _backgroundMask = [CAShapeLayer layer];
  _backgroundMask.fillRule = kCAFillRuleEvenOdd;
  _cutoutMask = [CALayer layer];
  _cutoutMask.contentsGravity = kCAGravityResize;
  [self addSubview:_background];
  _itemViews = [NSMutableArray array];
  _knobViews = [NSMutableArray array];
  return self;
}

- (BOOL)hasSkin {
  return _portrait != nil || _landscape != nil;
}

- (BOOL)portraitAvailable {
  return _portrait != nil;
}

- (UIInterfaceOrientationMask)supportedOrientationMask {
  return (UIInterfaceOrientationMask)ARMSX2PolicyMask(_portrait != nil, _landscape != nil);
}

- (BOOL)hasMenuControl {
  for (A2SkinItem* item in _current.items) {
    if ([item.inputs containsObject:@"menu"]) return YES;
  }
  return NO;
}

- (BOOL)layoutActive {
  return _current != nil;
}

#pragma mark Layout

- (void)rebuildViews {
  for (UIView* view in _itemViews) [view removeFromSuperview];
  for (UIView* view in _knobViews) [view removeFromSuperview];
  [_itemViews removeAllObjects];
  [_armViews removeAllObjects];
  [_knobViews removeAllObjects];
  _background.image = nil;
  if (_current == nil) return;
  const CGFloat opacity = _current.translucent ? 0.7 : 1.0;
  _background.alpha = opacity;
  for (A2SkinItem* item in _current.items) {
    UIImageView* view = [UIImageView new];
    view.contentMode = UIViewContentModeScaleToFill;
    view.alpha = opacity;
    view.hidden = item.assetPath == nil;
    [self addSubview:view];
    [_itemViews addObject:view];
    UIImageView* knob = [UIImageView new];
    knob.contentMode = UIViewContentModeScaleToFill;
    knob.alpha = opacity;
    knob.hidden = item.kind != A2SkinItemKindStick || item.knobPath == nil;
    [self addSubview:knob];
    [_knobViews addObject:knob];
  }
}

/// The current skin's own screen cutout, read once per file; nil without one.
- (UIImage*)screenCutout {
  NSString* path = _current.cutoutPath;
  if (path == nil) return nil;
  if (![path isEqualToString:_cutoutPath]) {
    _cutoutPath = [path copy];
    _cutoutImage = [UIImage imageWithContentsOfFile:path];
  }
  return _cutoutImage.CGImage != NULL ? _cutoutImage : nil;
}

- (BOOL)screenCutoutActive {
  return _current.hasScreen && _background.layer.mask == _cutoutMask && _cutoutMask.contents != nil;
}

- (void)layoutSubviews {
  [super layoutSubviews];
  const CGRect bounds = self.bounds;
  const UIEdgeInsets insets = self.safeAreaInsets;
  A2SkinRepresentation* representation = bounds.size.height > bounds.size.width ? _portrait : _landscape;
  if (bounds.size.width < 1 || bounds.size.height < 1) representation = nil;
  const BOOL sameSkin = representation == _current;
  if (sameSkin && CGSizeEqualToSize(bounds.size, _laidOutSize) && UIEdgeInsetsEqualToEdgeInsets(insets, _laidOutInsets)) return;
  if (!sameSkin) {
    // A turn of the surface releases what the other layout held.
    [self releaseAllInputs];
    _current = representation;
    [self rebuildViews];
  }
  _laidOutSize = bounds.size;
  _laidOutInsets = insets;
  if (_current == nil) {
    _skinRect = CGRectNull;
    _screenFrame = CGRectNull;
    _background.hidden = YES;
    if (self.layoutChanged) self.layoutChanged();
    return;
  }
  const CGSize mapping = _current.mappingSize;
  const CGFloat width = bounds.size.width, height = bounds.size.height;
  const CGFloat pinnedHeight = width * mapping.height / mapping.width;
  CGRect gameArea = bounds;
  if (_current.portrait && !_current.hasScreen && pinnedHeight <= height) {
    // Delta portrait: the controller at the bottom at full width, the game
    // above it (below the safe area's top).
    _skinRect = CGRectMake(0, height - pinnedHeight, width, pinnedHeight);
    const CGFloat top = MIN(insets.top, _skinRect.origin.y);
    gameArea = CGRectMake(0, top, width, _skinRect.origin.y - top);
    if (gameArea.size.height < 1) gameArea = CGRectMake(0, 0, width, MAX(_skinRect.origin.y, 1));
  } else {
    // Fitted in the whole bounds, safe areas ignored (Delta).
    _skinRect = A2SkinAspectFit(bounds, mapping.width / mapping.height);
  }
  _screenFrame = _current.hasScreen ? A2SkinScaled(_current.screen, mapping, _skinRect) : gameArea;

  _background.hidden = _current.backgroundPath == nil;
  _background.frame = _skinRect;
  _background.image = A2SkinImage(_current.backgroundPath, _skinRect.size);
  UIImage* cutout = _current.hasScreen ? [self screenCutout] : nil;
  if (cutout != nil) {
    // A RewindBox Pocket pack ships the cutout of its own screen: its alpha is where
    // the body stays. As the body's mask it is scaled with the body, so the game shows
    // through the opening the body draws (rounded corners, any shape) on every device,
    // and never over its frame. `screenFrame` (the emulator's surface) is its bounding box.
    [CATransaction begin];
    [CATransaction setDisableActions:YES];
    _cutoutMask.frame = _background.bounds;
    _cutoutMask.contents = (__bridge id)cutout.CGImage;
    [CATransaction commit];
    _background.layer.mask = _cutoutMask;
  } else if (_current.hasScreen) {
    // The game always shows through the skin's screen, transparent or not.
    UIBezierPath* path = [UIBezierPath bezierPathWithRect:_background.bounds];
    [path appendPath:[UIBezierPath bezierPathWithRect:[self convertRect:_screenFrame toView:_background]]];
    _backgroundMask.frame = _background.bounds;
    _backgroundMask.path = path.CGPath;
    _background.layer.mask = _backgroundMask;
  } else {
    _background.layer.mask = nil;
  }
  [_current.items enumerateObjectsUsingBlock:^(A2SkinItem* item, NSUInteger index, __unused BOOL* stop) {
    UIImageView* view = self->_itemViews[index];
    view.frame = A2SkinScaled(item.frame, mapping, self->_skinRect);
    view.image = A2SkinImage(item.assetPath, view.frame.size);
    view.highlightedImage = A2SkinImage(item.pressedAssetPath, view.frame.size);
  }];
  [self refreshPressedViews];
  if (self.layoutChanged) self.layoutChanged();
}

/// LibretroSkinLayout knobFrameForItem: the knob's size in mapping points,
/// moved by the stick vector within the frame.
- (CGRect)knobFrameForItem:(A2SkinItem*)item frame:(CGRect)frame vector:(CGPoint)vector {
  const CGFloat factor = item.frame.size.width > 0 ? frame.size.width / item.frame.size.width : 1;
  CGFloat width = item.knobSize.width * factor, height = item.knobSize.height * factor;
  if (!(width > 0) || !(height > 0)) {
    width = frame.size.width * 0.5;
    height = frame.size.height * 0.5;
  }
  const CGFloat travelX = frame.size.width - width > 0.001 ? (frame.size.width - width) / 2 : frame.size.width / 4;
  const CGFloat travelY = frame.size.height - height > 0.001 ? (frame.size.height - height) / 2 : frame.size.height / 4;
  const CGFloat x = CGRectGetMidX(frame) + MIN(MAX(vector.x, -1), 1) * travelX;
  const CGFloat y = CGRectGetMidY(frame) + MIN(MAX(vector.y, -1), 1) * travelY;
  return CGRectMake(x - width / 2, y - height / 2, width, height);
}

/// The pressed picture of a D-pad, cut to the quarter(s) of its held directions: each
/// direction is the triangle from the centre to its side (a diagonal shows two).
- (void)showArms:(NSSet<NSString*>*)arms index:(NSUInteger)index on:(UIImageView*)view {
  UIImageView* arm = _armViews[@(index)];
  if (arms.count == 0) {
    arm.hidden = YES;
    return;
  }
  if (arm == nil || arm.superview != view) {
    arm = [[UIImageView alloc] initWithFrame:view.bounds];
    arm.contentMode = view.contentMode;
    arm.layer.mask = [CAShapeLayer layer];
    [view addSubview:arm];
    _armViews[@(index)] = arm;
  }
  arm.frame = view.bounds;
  arm.image = view.highlightedImage;
  arm.hidden = NO;
  const CGFloat w = view.bounds.size.width, h = view.bounds.size.height;
  const CGPoint centre = CGPointMake(w / 2, h / 2);
  UIBezierPath* path = [UIBezierPath bezierPath];
  void (^quarter)(CGPoint, CGPoint) = ^(CGPoint a, CGPoint b) {
    [path moveToPoint:centre];
    [path addLineToPoint:a];
    [path addLineToPoint:b];
    [path closePath];
  };
  if ([arms containsObject:@"up"]) quarter(CGPointMake(0, 0), CGPointMake(w, 0));
  if ([arms containsObject:@"down"]) quarter(CGPointMake(0, h), CGPointMake(w, h));
  if ([arms containsObject:@"left"]) quarter(CGPointMake(0, 0), CGPointMake(0, h));
  if ([arms containsObject:@"right"]) quarter(CGPointMake(w, 0), CGPointMake(w, h));
  CAShapeLayer* mask = (CAShapeLayer*)arm.layer.mask;
  [CATransaction begin];
  [CATransaction setDisableActions:YES];
  mask.frame = arm.bounds;
  mask.path = path.CGPath;
  [CATransaction commit];
}

- (void)refreshPressedViews {
  if (_current == nil) return;
  const CGSize mapping = _current.mappingSize;
  [_current.items enumerateObjectsUsingBlock:^(A2SkinItem* item, NSUInteger index, __unused BOOL* stop) {
    UIImageView* view = self->_itemViews[index];
    const BOOL pressed = [self->_pressedItems containsObject:@(index)];
    view.highlighted = pressed && view.highlightedImage != nil;
    if (item.kind == A2SkinItemKindDPad && view.highlightedImage != nil) {
      // A D-pad shows the arm(s) under the finger pressed, not the whole cross.
      view.highlighted = NO;
      [self showArms:(pressed ? self->_pressedArms[@(index)] : nil) index:index on:view];
    }
    // Without a pressed asset, a held control dims a little.
    const CGFloat opacity = self->_current.translucent ? 0.7 : 1.0;
    view.alpha = pressed && view.highlightedImage == nil ? opacity * 0.6 : opacity;
    UIImageView* knob = self->_knobViews[index];
    if (knob.hidden) return;
    const CGRect frame = A2SkinScaled(item.frame, mapping, self->_skinRect);
    NSValue* vector = item.family != nil ? self->_vectors[item.family] : nil;
    const CGPoint deflection = vector == nil ? CGPointZero : vector.CGPointValue;
    knob.frame = [self knobFrameForItem:item frame:frame vector:deflection];
    if (knob.image == nil || !CGSizeEqualToSize(knob.image.size, knob.frame.size))
      knob.image = A2SkinImage(item.knobPath, knob.frame.size);
  }];
}

#pragma mark Touches

- (UIView*)hitTest:(CGPoint)point withEvent:(UIEvent*)event {
  if (self.hidden || !self.userInteractionEnabled || self.alpha < 0.01 || _current == nil) return nil;
  // Only the skin's own area takes touches; the game's screen stays the game's.
  return CGRectContainsPoint(_skinRect, point) ? self : nil;
}

/// The control under `point` (ARMSX2SkinHitTest.h): the drawn shape first, then
/// the nearest frame, then the nearest extended touch area. Without overlapping
/// frames (the earlier packs) this is the previous answer: frame, then extended
/// edges, the last drawn wins.
- (NSInteger)itemAtPoint:(CGPoint)point {
  if (_current == nil || CGRectIsNull(_skinRect)) return -1;
  const CGSize mapping = _current.mappingSize;
  const CGPoint local = CGPointMake((point.x - _skinRect.origin.x) * mapping.width / _skinRect.size.width,
                                    (point.y - _skinRect.origin.y) * mapping.height / _skinRect.size.height);
  NSArray<A2SkinItem*>* items = _current.items;
  std::vector<A2SkinHitItem> hits(items.count);
  for (NSUInteger index = 0; index < items.count; index++) {
    A2SkinItem* item = items[index];
    const CGRect f = item.frame, h = item.hitFrame;
    hits[index] = A2SkinHitItem{f.origin.x, f.origin.y, f.size.width, f.size.height,
                                h.origin.x, h.origin.y, h.size.width, h.size.height,
                                item.alphaMap != nil ? (const uint8_t*)item.alphaMap.bytes : nullptr,
                                (long)item.alphaSize.width, (long)item.alphaSize.height,
                                (item.inputs.count > 0 || item.directions.count > 0) ? 1 : 0};
  }
  return (NSInteger)A2SkinHitIndex(hits.data(), (long)hits.size(), local.x, local.y);
}

- (void)touchesBegan:(NSSet<UITouch*>*)touches withEvent:(UIEvent*)event {
  for (UITouch* touch in touches) {
    A2SkinTrack* track = [A2SkinTrack new];
    track.location = [touch locationInView:self];
    track.item = [self itemAtPoint:track.location];
    [_tracks setObject:track forKey:touch];
  }
  [_haptics prepare];
  [self updateInputs];
}

- (void)touchesMoved:(NSSet<UITouch*>*)touches withEvent:(UIEvent*)event {
  for (UITouch* touch in touches) {
    A2SkinTrack* track = [_tracks objectForKey:touch];
    if (track == nil) continue;
    track.location = [touch locationInView:self];
    // A finger on a stick keeps it; any other slides from control to control.
    const BOOL stick = track.item >= 0 && _current.items[(NSUInteger)track.item].kind == A2SkinItemKindStick;
    if (!stick) track.item = [self itemAtPoint:track.location];
  }
  [self updateInputs];
}

- (void)touchesEnded:(NSSet<UITouch*>*)touches withEvent:(UIEvent*)event {
  for (UITouch* touch in touches) [_tracks removeObjectForKey:touch];
  [self updateInputs];
}

- (void)touchesCancelled:(NSSet<UITouch*>*)touches withEvent:(UIEvent*)event {
  [self touchesEnded:touches withEvent:event];
}

- (void)releaseAllInputs {
  [_tracks removeAllObjects];
  [self updateInputs];
}

/// D-pad: eight sectors of 45° around the centre, nothing in its middle.
- (NSArray<NSString*>*)dpadDirectionsOf:(A2SkinItem*)item at:(CGPoint)location frame:(CGRect)frame {
  const CGFloat x = (location.x - CGRectGetMidX(frame)) / MAX(frame.size.width / 2, 1);
  const CGFloat y = (location.y - CGRectGetMidY(frame)) / MAX(frame.size.height / 2, 1);
  if (std::hypot(x, y) < 0.2) return @[];
  const double angle = std::atan2((double)y, (double)x) * 180.0 / M_PI;  // 0 right, 90 down
  NSMutableArray<NSString*>* directions = [NSMutableArray array];
  if (angle > -67.5 && angle < 67.5) [directions addObject:@"right"];
  if (angle > 22.5 && angle < 157.5) [directions addObject:@"down"];
  if (angle > 112.5 || angle < -112.5) [directions addObject:@"left"];
  if (angle > -157.5 && angle < -22.5) [directions addObject:@"up"];
  return directions;
}

- (void)updateInputs {
  NSMutableSet<NSString*>* pressed = [NSMutableSet set];
  NSMutableSet<NSNumber*>* pressedItems = [NSMutableSet set];
  NSMutableDictionary<NSNumber*, NSSet<NSString*>*>* pressedArms = [NSMutableDictionary dictionary];
  NSMutableDictionary<NSString*, NSValue*>* vectors = [NSMutableDictionary dictionary];
  const CGSize mapping = _current.mappingSize;
  for (UITouch* touch in _tracks) {
    A2SkinTrack* track = [_tracks objectForKey:touch];
    if (track.item < 0 || _current == nil || track.item >= (NSInteger)_current.items.count) continue;
    A2SkinItem* item = _current.items[(NSUInteger)track.item];
    const CGRect frame = A2SkinScaled(item.frame, mapping, _skinRect);
    switch (item.kind) {
      case A2SkinItemKindButtons:
        [pressed addObjectsFromArray:item.inputs];
        if (item.inputs.count > 0) [pressedItems addObject:@(track.item)];
        break;
      case A2SkinItemKindDPad: {
        NSArray<NSString*>* directions = [self dpadDirectionsOf:item at:track.location frame:frame];
        for (NSString* direction in directions) {
          NSString* canonical = item.directions[direction];
          if (canonical != nil) [pressed addObject:canonical];
        }
        if (directions.count > 0) {
          [pressedItems addObject:@(track.item)];
          NSMutableSet<NSString*>* arms = [NSMutableSet setWithArray:directions];
          if (pressedArms[@(track.item)] != nil) [arms unionSet:pressedArms[@(track.item)]];
          pressedArms[@(track.item)] = arms;
        }
        break;
      }
      case A2SkinItemKindStick: {
        CGFloat x = (track.location.x - CGRectGetMidX(frame)) / MAX(frame.size.width / 2, 1);
        CGFloat y = (track.location.y - CGRectGetMidY(frame)) / MAX(frame.size.height / 2, 1);
        const CGFloat length = std::hypot(x, y);
        if (length > 1) {
          x /= length;
          y /= length;
        }
        vectors[item.family] = [NSValue valueWithCGPoint:CGPointMake(x, y)];
        [pressedItems addObject:@(track.item)];
        break;
      }
    }
  }
  // Stick directions pressed by buttons or a D-pad deflect their stick fully
  // (a finger on the stick itself wins).
  NSMutableDictionary<NSString*, NSValue*>* digital = [NSMutableDictionary dictionary];
  for (NSString* canonical in [pressed copy]) {
    NSString* direction = nil;
    NSString* family = A2SkinFamily(canonical, &direction);
    if (family == nil) continue;
    [pressed removeObject:canonical];
    CGPoint vector = digital[family] != nil ? digital[family].CGPointValue : CGPointZero;
    if ([direction isEqualToString:@"up"]) vector.y = -1;
    if ([direction isEqualToString:@"down"]) vector.y = 1;
    if ([direction isEqualToString:@"left"]) vector.x = -1;
    if ([direction isEqualToString:@"right"]) vector.x = 1;
    digital[family] = [NSValue valueWithCGPoint:vector];
  }
  for (NSString* family in digital) {
    if (vectors[family] == nil) vectors[family] = digital[family];
  }
  [self commitPressed:pressed vectors:vectors];
  _pressedItems = pressedItems;
  _pressedArms = pressedArms;
  [self refreshPressedViews];
}

- (void)commitPressed:(NSSet<NSString*>*)pressed vectors:(NSDictionary<NSString*, NSValue*>*)vectors {
  for (NSString* canonical in _pressed) {
    if (![pressed containsObject:canonical]) [self send:canonical pressed:NO];
  }
  BOOL feedback = NO;
  for (NSString* canonical in pressed) {
    if ([_pressed containsObject:canonical]) continue;
    [self send:canonical pressed:YES];
    feedback = YES;
  }
  if (feedback) [_haptics impactOccurred];
  const CGPoint left = vectors[@"stick"] != nil ? vectors[@"stick"].CGPointValue : CGPointZero;
  const CGPoint right = vectors[@"rstick"] != nil ? vectors[@"rstick"].CGPointValue : CGPointZero;
  const CGPoint wasLeft = _vectors[@"stick"] != nil ? _vectors[@"stick"].CGPointValue : CGPointZero;
  const CGPoint wasRight = _vectors[@"rstick"] != nil ? _vectors[@"rstick"].CGPointValue : CGPointZero;
  if (!CGPointEqualToPoint(left, wasLeft) || !CGPointEqualToPoint(right, wasRight)) {
    // Positive Y is down, like the stock virtual sticks of the session.
    if (self.sticksChanged != nil) self.sticksChanged((float)left.x, (float)left.y, (float)right.x, (float)right.y);
  }
  _pressed = [pressed copy];
  _vectors = [vectors copy];
}

/// Digital inputs go to the pad (`buttonChanged`, ARMSX2PadButton); the menu
/// opens the session menu after the current touch event: the session then
/// hides the skin's input and releases everything.
- (void)send:(NSString*)canonical pressed:(BOOL)pressed {
  NSNumber* button = A2SkinButtonIds()[canonical];
  if (button != nil) {
    if (self.buttonChanged != nil) self.buttonChanged((uint32_t)button.unsignedIntegerValue, pressed);
    return;
  }
  if (pressed && [canonical isEqualToString:@"menu"]) {
    __weak ARMSX2SkinOverlay* weakSelf = self;
    dispatch_async(dispatch_get_main_queue(), ^{
      ARMSX2SkinOverlay* strongSelf = weakSelf;
      if (strongSelf.menuHandler != nil) strongSelf.menuHandler();
    });
  }
}

@end
