// SPDX-License-Identifier: GPL-3.0-or-later
// Controller skins for the embedded MeloNX (Nintendo Switch), docs/dolphin-skins.md.
//
// The same .manicskin / .deltaskin files, folders and selection files as the
// libretro, Dolphin and ARMSX2 skins: Documents/Libretro/Skins/<id>/info.json and
// Documents/Libretro/Config/Frontend/switch.json ({"console": {"skin.portrait": id,
// "skin.landscape": id}, "games": {key: {...}}}; the game's choice first, then
// the console's, "default" meaning none). This overlay is the MeloNX pod's own
// reader and renderer (a pod cannot import another): a port of ARMSX2SkinOverlay
// with the Switch input table. It draws the skin over the session, sends its
// touches to the same pad as the Melo-Controller (the embedded Core's button
// indices through `buttonChanged`, both sticks through `sticksChanged`), opens the
// RewindBox session menu from the skin's Menu control and tells the session where
// the game goes. Without a skin for the console ("default" or nothing stored) it is
// never created and the Melo-Controller is unchanged.
//
// Nintendo Switch names only (see MeloNXSkinCanonicalInput); L3 and R3 are
// targets of their own, a stick finger only moves the stick. HOME and Capture have
// no index in the embedded Core: a skin may draw them and the session reports them
// (`systemButtonHandler`), they never pretend to reach the game.
#import "MeloNXSkinOverlay.h"
#import "MeloNXSkinHitTest.h"
#import <CoreGraphics/CoreGraphics.h>
#include <cmath>
#include <vector>

#pragma mark - Input table (DolphinSkins 'switch', lib/services/dolphin_skins.dart)

/// Lower case, letters and digits only (Dart: toLowerCase, [^a-z0-9] removed).
static NSString* MLXSkinKey(NSString* raw) {
  NSString* lower = raw.lowercaseString;
  NSMutableString* key = [NSMutableString stringWithCapacity:lower.length];
  for (NSUInteger i = 0; i < lower.length; i++) {
    const unichar c = [lower characterAtIndex:i];
    if ((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9')) [key appendFormat:@"%C", c];
  }
  return key;
}

static NSArray<NSString*>* MLXSkinDirections(void) { return @[ @"Up", @"Down", @"Left", @"Right" ]; }

/// The embedded Core's 17 button indices (native/melonx/EmbeddedInput.cs
/// neostation_melonx_input_button, order proven on the real NativeGamepadDriver by
/// test/melonx_input_test.py): A 0, B 1, X 2, Y 3, Minus (Back) 4, [Guide 5], Plus
/// (Start) 6, L3 7, R3 8, L 9, R 10, Up 11, Down 12, Left 13, Right 14, ZL 15, ZR 16.
/// Guide (5) is not a skin input: nothing shows the guest acting on it (HOME), and
/// the session keeps it for its own menu, as the standalone Melo-Controller does.
static NSDictionary<NSString*, NSNumber*>* MLXSkinButtonIds(void) {
  static NSDictionary<NSString*, NSNumber*>* ids;
  static dispatch_once_t once;
  dispatch_once(&once, ^{
    ids = @{
      @"a" : @0, @"b" : @1, @"x" : @2, @"y" : @3, @"minus" : @4, @"plus" : @6, @"l3" : @7, @"r3" : @8,
      @"l" : @9, @"r" : @10, @"up" : @11, @"down" : @12, @"left" : @13, @"right" : @14, @"zl" : @15,
      @"zr" : @16,
    };
  });
  return ids;
}

/// Console buttons the embedded Core cannot receive (no index; docs/dolphin-skins.md):
/// a skin may draw them, the session says so when one is pressed.
static NSArray<NSString*>* MLXSkinSystemButtons(void) { return @[ @"home", @"capture" ]; }

/// The logical input of a raw skin input, or nil when the console has nothing
/// for it. Only Nintendo Switch names (Same table as DolphinSkins 'switch').
NSString* MeloNXSkinCanonicalInput(NSString* raw) {
  if (![raw isKindOfClass:NSString.class]) return nil;
  NSString* key = MLXSkinKey(raw);
  for (NSString* prefix in @[ @"leftthumbstick", @"analogstick", @"leftstick", @"leftanalog", @"analog", @"thumbstick" ]) {
    for (NSString* direction in MLXSkinDirections()) {
      if ([key isEqualToString:[prefix stringByAppendingString:direction.lowercaseString]])
        return [@"stick" stringByAppendingString:direction];
    }
  }
  for (NSString* prefix in @[ @"rightthumbstick", @"rightstick", @"rightanalog", @"cstick", @"c" ]) {
    for (NSString* direction in MLXSkinDirections()) {
      if ([key isEqualToString:[prefix stringByAppendingString:direction.lowercaseString]])
        return [@"rstick" stringByAppendingString:direction];
    }
  }
  for (NSString* direction in MLXSkinDirections()) {
    NSString* name = direction.lowercaseString;
    if ([key isEqualToString:name] || [key isEqualToString:[@"dpad" stringByAppendingString:name]]) return name;
  }
  if ([@[ @"menu", @"pause", @"options" ] containsObject:key]) return @"menu";
  if ([@[ @"leftstickclick", @"lsclick", @"ls" ] containsObject:key]) return @"l3";
  if ([@[ @"rightstickclick", @"rsclick", @"rs" ] containsObject:key]) return @"r3";
  if ([@[ @"select", @"back" ] containsObject:key]) return @"minus";
  if ([key isEqualToString:@"start"]) return @"plus";
  if ([@[ @"home", @"capture" ] containsObject:key]) return key;
  if ([key isEqualToString:@"screenshot"]) return @"capture";
  return MLXSkinButtonIds()[key] != nil && ![@[ @"up", @"down", @"left", @"right" ] containsObject:key] ? key : nil;
}

NSString* MeloNXSkinConsoleOfGameType(NSString* gameTypeIdentifier) {
  if (![gameTypeIdentifier isKindOfClass:NSString.class]) return nil;
  NSString* trimmed = [gameTypeIdentifier stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
  NSString* key = MLXSkinKey([trimmed componentsSeparatedByString:@"."].lastObject ?: @"");
  return [@[ @"switch", @"nintendoswitch", @"nx", @"melonx" ] containsObject:key] ? @"switch" : nil;
}

/// "stick" (left) or "rstick" for `stickUp`, `rstickLeft`…; nil else.
static NSString* MLXSkinFamily(NSString* canonical, NSString** direction) {
  for (NSString* family in @[ @"rstick", @"stick" ]) {
    for (NSString* d in MLXSkinDirections()) {
      if ([canonical isEqualToString:[family stringByAppendingString:d]]) {
        if (direction) *direction = d.lowercaseString;
        return family;
      }
    }
  }
  return nil;
}

/// Orientations a session allows from the skins the player CHOSE (the rule of
/// ARMSX2OrientationPolicy.h / DOLOrientationPolicy.h). Mask values mirror
/// UIInterfaceOrientationMask.
static inline unsigned MLXSkinPolicyMask(bool portrait, bool landscape) {
  if (portrait && !landscape) return 1u << 1;
  if (landscape && !portrait) return (1u << 3) | (1u << 4);
  return (1u << 1) | (1u << 3) | (1u << 4);
}

#pragma mark - Skin model

typedef NS_ENUM(NSInteger, MLXSkinItemKind) {
  MLXSkinItemKindButtons = 0,  // every input of the list together
  MLXSkinItemKindDPad = 1,     // up / down / left / right, digital
  MLXSkinItemKindStick = 2,    // the four directions of one analog family
};

@interface MLXSkinItem : NSObject
@property(nonatomic, assign) MLXSkinItemKind kind;
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
// (MeloNXSkinHitTest.h).
@property(nonatomic, strong, nullable) NSData* alphaMap;
@property(nonatomic, assign) CGSize alphaSize;
@end
@implementation MLXSkinItem
@end

/// The normal sprite's alpha, at most 192 pixels on its long side; nil when
/// it cannot be read or has no transparent pixel (then the frame is the shape).
static NSData* MLXSkinAlphaMap(NSString* path, CGSize* size) {
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

@interface MLXSkinRepresentation : NSObject
@property(nonatomic, assign) BOOL portrait;
@property(nonatomic, assign) CGSize mappingSize;
@property(nonatomic, copy, nullable) NSString* backgroundPath;
@property(nonatomic, copy) NSArray<MLXSkinItem*>* items;
@property(nonatomic, assign) BOOL hasScreen;
@property(nonatomic, assign) CGRect screen;
@property(nonatomic, assign) BOOL translucent;
@end
@implementation MLXSkinRepresentation
@end

static BOOL MLXSkinNumber(id value, CGFloat* out) {
  if (![value isKindOfClass:NSNumber.class]) return NO;
  const double number = [(NSNumber*)value doubleValue];
  if (!std::isfinite(number)) return NO;
  *out = (CGFloat)number;
  return YES;
}

static BOOL MLXSkinSize(id value, CGSize* out) {
  if (![value isKindOfClass:NSDictionary.class]) return NO;
  CGFloat width = 0, height = 0;
  if (!MLXSkinNumber(value[@"width"], &width) || !MLXSkinNumber(value[@"height"], &height)) return NO;
  if (!(width > 0) || !(height > 0)) return NO;
  *out = CGSizeMake(width, height);
  return YES;
}

static BOOL MLXSkinRect(id value, CGRect* out) {
  if (![value isKindOfClass:NSDictionary.class]) return NO;
  CGFloat x = 0, y = 0;
  CGSize size;
  if (!MLXSkinNumber(value[@"x"], &x) || !MLXSkinNumber(value[@"y"], &y) || !MLXSkinSize(value, &size)) return NO;
  *out = CGRectMake(x, y, size.width, size.height);
  return YES;
}

/// extendedEdges, each missing or invalid side taken from `fallback`.
static UIEdgeInsets MLXSkinEdges(id value, UIEdgeInsets fallback) {
  if (![value isKindOfClass:NSDictionary.class]) return fallback;
  UIEdgeInsets edges = fallback;
  CGFloat side = 0;
  if (MLXSkinNumber(value[@"top"], &side) && side >= 0) edges.top = side;
  if (MLXSkinNumber(value[@"left"], &side) && side >= 0) edges.left = side;
  if (MLXSkinNumber(value[@"bottom"], &side) && side >= 0) edges.bottom = side;
  if (MLXSkinNumber(value[@"right"], &side) && side >= 0) edges.right = side;
  return edges;
}

/// A file of the skin's own folder; nil for anything outside it.
static NSString* MLXSkinFile(NSString* root, id name) {
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
static NSString* MLXSkinAsset(NSString* root, id assets) {
  if ([assets isKindOfClass:NSString.class]) return MLXSkinFile(root, assets);
  if (![assets isKindOfClass:NSDictionary.class]) return nil;
  for (NSString* key in @[ @"resizable", @"large", @"medium", @"small", @"normal" ]) {
    NSString* path = MLXSkinFile(root, assets[key]);
    if (path != nil) return path;
  }
  return nil;
}

static NSDictionary* MLXSkinReadJSON(NSString* path) {
  NSData* data = [NSData dataWithContentsOfFile:path options:NSDataReadingMappedIfSafe error:nil];
  if (data == nil || data.length > 4 * 1024 * 1024) return nil;
  id object = [NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
  return [object isKindOfClass:NSDictionary.class] ? object : nil;
}

/// LibretroSkinService.isInstalledId: ^[a-z0-9-]+$ and never "default".
static BOOL MLXSkinIsInstalledId(NSString* identifier) {
  if (![identifier isKindOfClass:NSString.class] || identifier.length == 0 || identifier.length > 128) return NO;
  if ([identifier isEqualToString:@"default"]) return NO;
  NSCharacterSet* allowed = [NSCharacterSet characterSetWithCharactersInString:@"abcdefghijklmnopqrstuvwxyz0123456789-"];
  return [identifier rangeOfCharacterFromSet:allowed.invertedSet].location == NSNotFound;
}

/// The skin chosen for `orientation`: the game's choice when it has one for
/// that key (even "default"), else the console's.
static NSString* MLXSkinSelected(NSDictionary* document, NSString* gameKey, NSString* orientation) {
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
  return MLXSkinIsInstalledId(value) ? value : nil;
}

/// The layout of `orientation` for this device: the iPhone's (edge-to-edge
/// on a tall screen, else standard), an iPad layout when there is none.
static NSDictionary* MLXSkinLayoutFor(NSDictionary* info, NSString* orientation) {
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

static MLXSkinRepresentation* MLXSkinParse(NSDictionary* layout, NSString* root, BOOL portrait) {
  CGSize mapping;
  if (!MLXSkinSize(layout[@"mappingSize"], &mapping)) return nil;
  const UIEdgeInsets defaultEdges = MLXSkinEdges(layout[@"extendedEdges"], UIEdgeInsetsZero);
  NSMutableArray<MLXSkinItem*>* items = [NSMutableArray array];
  NSArray* objects = [layout[@"items"] isKindOfClass:NSArray.class] ? layout[@"items"] : @[];
  NSUInteger usable = 0;
  for (NSDictionary* object in objects) {
    if (![object isKindOfClass:NSDictionary.class]) continue;
    CGRect frame;
    if (!MLXSkinRect(object[@"frame"], &frame)) continue;
    MLXSkinItem* item = [MLXSkinItem new];
    item.frame = frame;
    const UIEdgeInsets edges = MLXSkinEdges(object[@"extendedEdges"], defaultEdges);
    item.hitFrame = CGRectMake(frame.origin.x - edges.left, frame.origin.y - edges.top,
                               frame.size.width + edges.left + edges.right, frame.size.height + edges.top + edges.bottom);
    item.inputs = @[];
    item.directions = @{};
    id inputs = object[@"inputs"];
    if ([inputs isKindOfClass:NSDictionary.class]) {
      NSMutableDictionary<NSString*, NSString*>* directions = [NSMutableDictionary dictionary];
      NSString* family = nil;
      BOOL analog = YES;
      for (NSString* d in MLXSkinDirections()) {
        NSString* name = d.lowercaseString;
        NSString* canonical = MeloNXSkinCanonicalInput([inputs objectForKey:name]);
        if (canonical == nil) continue;
        directions[name] = canonical;
        NSString* direction = nil;
        NSString* own = MLXSkinFamily(canonical, &direction);
        if (own == nil || ![direction isEqualToString:name] || (family != nil && ![family isEqualToString:own])) analog = NO;
        family = family ?: own;
      }
      item.directions = directions;
      item.kind = analog && family != nil ? MLXSkinItemKindStick : MLXSkinItemKindDPad;
      if (item.kind == MLXSkinItemKindStick) item.family = family;
      NSDictionary* thumbstick = object[@"thumbstick"];
      CGSize knob;
      if ([thumbstick isKindOfClass:NSDictionary.class] && MLXSkinSize(thumbstick, &knob)) {
        item.knobPath = MLXSkinFile(root, thumbstick[@"name"]);
        item.knobSize = knob;
      }
      if (directions.count > 0) usable++;
    } else if ([inputs isKindOfClass:NSArray.class]) {
      NSMutableArray<NSString*>* list = [NSMutableArray array];
      for (id raw in (NSArray*)inputs) {
        NSString* canonical = MeloNXSkinCanonicalInput(raw);
        if (canonical != nil && ![list containsObject:canonical]) [list addObject:canonical];
      }
      item.kind = MLXSkinItemKindButtons;
      item.inputs = list;
      if (list.count > 0) usable++;
    }
    id asset = object[@"asset"];
    if ([asset isKindOfClass:NSString.class]) {
      item.assetPath = MLXSkinFile(root, asset);
    } else if ([asset isKindOfClass:NSDictionary.class]) {
      item.assetPath = MLXSkinFile(root, asset[@"normal"]);
      item.pressedAssetPath = MLXSkinFile(root, asset[@"pressed"]);
    }
    CGSize alphaSize = CGSizeZero;
    item.alphaMap = MLXSkinAlphaMap(item.assetPath, &alphaSize);
    item.alphaSize = alphaSize;
    if (item.inputs.count == 0 && item.directions.count == 0 && item.assetPath == nil) continue;
    [items addObject:item];
  }
  if (usable == 0) return nil;
  MLXSkinRepresentation* representation = [MLXSkinRepresentation new];
  representation.portrait = portrait;
  representation.mappingSize = mapping;
  representation.items = items;
  representation.backgroundPath = MLXSkinAsset(root, layout[@"assets"]);
  representation.translucent = [layout[@"translucent"] isKindOfClass:NSNumber.class] && [layout[@"translucent"] boolValue];
  CGRect screen;
  if (MLXSkinRect(layout[@"gameScreenFrame"], &screen)) {
    // Legacy key: wins over `screens` (Delta).
    representation.hasScreen = YES;
    representation.screen = screen;
  } else if ([layout[@"screens"] isKindOfClass:NSArray.class]) {
    for (NSDictionary* entry in (NSArray*)layout[@"screens"]) {
      if ([entry isKindOfClass:NSDictionary.class] && MLXSkinRect(entry[@"outputFrame"], &screen)) {
        representation.hasScreen = YES;
        representation.screen = screen;
        break;
      }
    }
  }
  return representation;
}

#pragma mark - Images

/// First page of a PDF drawn at `points` (Delta stretches PDF assets).
static UIImage* MLXSkinPDF(NSString* path, CGSize points) {
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

static UIImage* MLXSkinImage(NSString* path, CGSize points) {
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
    image = pdf ? MLXSkinPDF(path, points) : [UIImage imageWithContentsOfFile:path];
    if (image != nil) [cache setObject:image forKey:key];
  }
  return image;
}

static CGRect MLXSkinScaled(CGRect rect, CGSize mapping, CGRect skin) {
  const CGFloat sx = skin.size.width / mapping.width, sy = skin.size.height / mapping.height;
  return CGRectMake(skin.origin.x + rect.origin.x * sx, skin.origin.y + rect.origin.y * sy, rect.size.width * sx,
                    rect.size.height * sy);
}

static CGRect MLXSkinAspectFit(CGRect bounds, CGFloat aspect) {
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

@interface MLXSkinTrack : NSObject
@property(nonatomic, assign) NSInteger item;  // index in the representation, -1 none
@property(nonatomic, assign) CGPoint location;
@end
@implementation MLXSkinTrack
@end

@implementation MeloNXSkinOverlay {
  MLXSkinRepresentation* _portrait;
  MLXSkinRepresentation* _landscape;
  MLXSkinRepresentation* _current;
  CGSize _laidOutSize;
  UIEdgeInsets _laidOutInsets;
  CGRect _skinRect;
  UIImageView* _background;
  CAShapeLayer* _backgroundMask;
  NSMutableArray<UIImageView*>* _itemViews;
  NSMutableArray<UIImageView*>* _knobViews;
  NSMapTable<UITouch*, MLXSkinTrack*>* _tracks;
  NSSet<NSString*>* _pressed;
  NSDictionary<NSString*, NSValue*>* _vectors;
  NSSet<NSNumber*>* _pressedItems;
  UIImpactFeedbackGenerator* _haptics;
}

- (instancetype)initWithGameKey:(NSString*)gameKey {
  self = [super initWithFrame:CGRectZero];
  if (!self) return nil;
  _tracks = [NSMapTable strongToStrongObjectsMapTable];
  _pressed = [NSSet set];
  _vectors = @{};
  _pressedItems = [NSSet set];
  _skinRect = CGRectNull;
  _screenFrame = CGRectNull;
  _laidOutSize = CGSizeZero;
  _haptics = [[UIImpactFeedbackGenerator alloc] initWithStyle:UIImpactFeedbackStyleLight];
  self.backgroundColor = UIColor.clearColor;
  self.multipleTouchEnabled = YES;
  self.accessibilityIdentifier = @"melonx.skin.overlay";

  NSString* documents = NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES).firstObject;
  NSString* libretro = [documents stringByAppendingPathComponent:@"Libretro"];
  NSString* console = @"switch";
  NSString* selectionPath = [[libretro stringByAppendingPathComponent:@"Config/Frontend"]
      stringByAppendingPathComponent:[console stringByAppendingString:@".json"]];
  NSDictionary* selection = documents.length > 0 ? MLXSkinReadJSON(selectionPath) : nil;
  NSString* skins = [libretro stringByAppendingPathComponent:@"Skins"];
  for (NSString* orientation in @[ @"portrait", @"landscape" ]) {
    NSString* identifier = selection != nil ? MLXSkinSelected(selection, gameKey, orientation) : nil;
    if (identifier == nil) continue;
    NSString* root = [skins stringByAppendingPathComponent:identifier];
    NSDictionary* info = MLXSkinReadJSON([root stringByAppendingPathComponent:@"info.json"]);
    // Only a skin of this console (the import checked it; a skin may have
    // been replaced by another one since).
    if (info == nil || ![MeloNXSkinConsoleOfGameType(info[@"gameTypeIdentifier"]) isEqualToString:console]) {
      NSLog(@"melonx.skin.ignored %@ %@", orientation, identifier);
      continue;
    }
    NSDictionary* layout = MLXSkinLayoutFor(info, orientation);
    MLXSkinRepresentation* representation =
        layout != nil ? MLXSkinParse(layout, root, [orientation isEqualToString:@"portrait"]) : nil;
    if (representation == nil) {
      NSLog(@"melonx.skin.unusable %@ %@", orientation, identifier);
      continue;
    }
    if ([orientation isEqualToString:@"portrait"]) {
      _portrait = representation;
    } else {
      _landscape = representation;
    }
    NSLog(@"melonx.skin.selected %@ %@", orientation, identifier);
  }

  _background = [UIImageView new];
  _background.contentMode = UIViewContentModeScaleToFill;
  _backgroundMask = [CAShapeLayer layer];
  _backgroundMask.fillRule = kCAFillRuleEvenOdd;
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
  return (UIInterfaceOrientationMask)MLXSkinPolicyMask(_portrait != nil, _landscape != nil);
}

- (BOOL)hasMenuControl {
  for (MLXSkinItem* item in _current.items) {
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
  [_knobViews removeAllObjects];
  _background.image = nil;
  if (_current == nil) return;
  const CGFloat opacity = _current.translucent ? 0.7 : 1.0;
  _background.alpha = opacity;
  for (MLXSkinItem* item in _current.items) {
    UIImageView* view = [UIImageView new];
    view.contentMode = UIViewContentModeScaleToFill;
    view.alpha = opacity;
    view.hidden = item.assetPath == nil;
    [self addSubview:view];
    [_itemViews addObject:view];
    UIImageView* knob = [UIImageView new];
    knob.contentMode = UIViewContentModeScaleToFill;
    knob.alpha = opacity;
    knob.hidden = item.kind != MLXSkinItemKindStick || item.knobPath == nil;
    [self addSubview:knob];
    [_knobViews addObject:knob];
  }
}

- (void)layoutSubviews {
  [super layoutSubviews];
  const CGRect bounds = self.bounds;
  const UIEdgeInsets insets = self.safeAreaInsets;
  MLXSkinRepresentation* representation = bounds.size.height > bounds.size.width ? _portrait : _landscape;
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
    _skinRect = MLXSkinAspectFit(bounds, mapping.width / mapping.height);
  }
  _screenFrame = _current.hasScreen ? MLXSkinScaled(_current.screen, mapping, _skinRect) : gameArea;

  _background.hidden = _current.backgroundPath == nil;
  _background.frame = _skinRect;
  _background.image = MLXSkinImage(_current.backgroundPath, _skinRect.size);
  if (_current.hasScreen) {
    // The game always shows through the skin's screen, transparent or not.
    UIBezierPath* path = [UIBezierPath bezierPathWithRect:_background.bounds];
    [path appendPath:[UIBezierPath bezierPathWithRect:[self convertRect:_screenFrame toView:_background]]];
    _backgroundMask.frame = _background.bounds;
    _backgroundMask.path = path.CGPath;
    _background.layer.mask = _backgroundMask;
  } else {
    _background.layer.mask = nil;
  }
  [_current.items enumerateObjectsUsingBlock:^(MLXSkinItem* item, NSUInteger index, __unused BOOL* stop) {
    UIImageView* view = self->_itemViews[index];
    view.frame = MLXSkinScaled(item.frame, mapping, self->_skinRect);
    view.image = MLXSkinImage(item.assetPath, view.frame.size);
    view.highlightedImage = MLXSkinImage(item.pressedAssetPath, view.frame.size);
  }];
  [self refreshPressedViews];
  if (self.layoutChanged) self.layoutChanged();
}

/// LibretroSkinLayout knobFrameForItem: the knob's size in mapping points,
/// moved by the stick vector within the frame.
- (CGRect)knobFrameForItem:(MLXSkinItem*)item frame:(CGRect)frame vector:(CGPoint)vector {
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

- (void)refreshPressedViews {
  if (_current == nil) return;
  const CGSize mapping = _current.mappingSize;
  [_current.items enumerateObjectsUsingBlock:^(MLXSkinItem* item, NSUInteger index, __unused BOOL* stop) {
    UIImageView* view = self->_itemViews[index];
    const BOOL pressed = [self->_pressedItems containsObject:@(index)];
    view.highlighted = pressed && view.highlightedImage != nil;
    // Without a pressed asset, a held control dims a little.
    const CGFloat opacity = self->_current.translucent ? 0.7 : 1.0;
    view.alpha = pressed && view.highlightedImage == nil ? opacity * 0.6 : opacity;
    UIImageView* knob = self->_knobViews[index];
    if (knob.hidden) return;
    const CGRect frame = MLXSkinScaled(item.frame, mapping, self->_skinRect);
    NSValue* vector = item.family != nil ? self->_vectors[item.family] : nil;
    const CGPoint deflection = vector == nil ? CGPointZero : vector.CGPointValue;
    knob.frame = [self knobFrameForItem:item frame:frame vector:deflection];
    if (knob.image == nil || !CGSizeEqualToSize(knob.image.size, knob.frame.size))
      knob.image = MLXSkinImage(item.knobPath, knob.frame.size);
  }];
}

#pragma mark Touches

- (UIView*)hitTest:(CGPoint)point withEvent:(UIEvent*)event {
  if (self.hidden || !self.userInteractionEnabled || self.alpha < 0.01 || _current == nil) return nil;
  // Only the skin's own area takes touches; the game's screen stays the game's.
  return CGRectContainsPoint(_skinRect, point) ? self : nil;
}

/// The control under `point` (MeloNXSkinHitTest.h): the drawn shape first, then
/// the nearest frame, then the nearest extended touch area. Without overlapping
/// frames (the earlier packs) this is the previous answer: frame, then extended
/// edges, the last drawn wins.
- (NSInteger)itemAtPoint:(CGPoint)point {
  if (_current == nil || CGRectIsNull(_skinRect)) return -1;
  const CGSize mapping = _current.mappingSize;
  const CGPoint local = CGPointMake((point.x - _skinRect.origin.x) * mapping.width / _skinRect.size.width,
                                    (point.y - _skinRect.origin.y) * mapping.height / _skinRect.size.height);
  NSArray<MLXSkinItem*>* items = _current.items;
  std::vector<MLXSkinHitItem> hits(items.count);
  for (NSUInteger index = 0; index < items.count; index++) {
    MLXSkinItem* item = items[index];
    const CGRect f = item.frame, h = item.hitFrame;
    hits[index] = MLXSkinHitItem{f.origin.x, f.origin.y, f.size.width, f.size.height,
                                h.origin.x, h.origin.y, h.size.width, h.size.height,
                                item.alphaMap != nil ? (const uint8_t*)item.alphaMap.bytes : nullptr,
                                (long)item.alphaSize.width, (long)item.alphaSize.height,
                                (item.inputs.count > 0 || item.directions.count > 0) ? 1 : 0};
  }
  return (NSInteger)MLXSkinHitIndex(hits.data(), (long)hits.size(), local.x, local.y);
}

- (void)touchesBegan:(NSSet<UITouch*>*)touches withEvent:(UIEvent*)event {
  for (UITouch* touch in touches) {
    MLXSkinTrack* track = [MLXSkinTrack new];
    track.location = [touch locationInView:self];
    track.item = [self itemAtPoint:track.location];
    [_tracks setObject:track forKey:touch];
  }
  [_haptics prepare];
  [self updateInputs];
}

- (void)touchesMoved:(NSSet<UITouch*>*)touches withEvent:(UIEvent*)event {
  for (UITouch* touch in touches) {
    MLXSkinTrack* track = [_tracks objectForKey:touch];
    if (track == nil) continue;
    track.location = [touch locationInView:self];
    // A finger on a stick keeps it; any other slides from control to control.
    const BOOL stick = track.item >= 0 && _current.items[(NSUInteger)track.item].kind == MLXSkinItemKindStick;
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
- (NSArray<NSString*>*)dpadDirectionsOf:(MLXSkinItem*)item at:(CGPoint)location frame:(CGRect)frame {
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
  NSMutableDictionary<NSString*, NSValue*>* vectors = [NSMutableDictionary dictionary];
  const CGSize mapping = _current.mappingSize;
  for (UITouch* touch in _tracks) {
    MLXSkinTrack* track = [_tracks objectForKey:touch];
    if (track.item < 0 || _current == nil || track.item >= (NSInteger)_current.items.count) continue;
    MLXSkinItem* item = _current.items[(NSUInteger)track.item];
    const CGRect frame = MLXSkinScaled(item.frame, mapping, _skinRect);
    switch (item.kind) {
      case MLXSkinItemKindButtons:
        [pressed addObjectsFromArray:item.inputs];
        if (item.inputs.count > 0) [pressedItems addObject:@(track.item)];
        break;
      case MLXSkinItemKindDPad: {
        NSArray<NSString*>* directions = [self dpadDirectionsOf:item at:track.location frame:frame];
        for (NSString* direction in directions) {
          NSString* canonical = item.directions[direction];
          if (canonical != nil) [pressed addObject:canonical];
        }
        if (directions.count > 0) [pressedItems addObject:@(track.item)];
        break;
      }
      case MLXSkinItemKindStick: {
        CGFloat x = (track.location.x - CGRectGetMidX(frame)) / MAX(frame.size.width / 2, 1);
        CGFloat y = (track.location.y - CGRectGetMidY(frame)) / MAX(frame.size.height / 2, 1);
        // The skin rectangle is fitted in floating point (a scale of 0.9999999999999999):
        // the exact centre of a stick far from the origin gave a 1e-15 vector and sent a
        // change. Rounding noise only, not a dead zone (1e-9 of the travel).
        if (std::fabs(x) < 1e-9) x = 0;
        if (std::fabs(y) < 1e-9) y = 0;
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
    NSString* family = MLXSkinFamily(canonical, &direction);
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

/// Digital inputs go to the pad (`buttonChanged`, the Core's button index); the
/// menu opens the session menu after the current touch event (the session then
/// hides the skin's input and releases everything); HOME and Capture, which the
/// embedded Core cannot receive, are reported to the session (`systemButtonHandler`)
/// instead of being sent nowhere.
- (void)send:(NSString*)canonical pressed:(BOOL)pressed {
  NSNumber* button = MLXSkinButtonIds()[canonical];
  if (button != nil) {
    if (self.buttonChanged != nil) self.buttonChanged((uint32_t)button.unsignedIntegerValue, pressed);
    return;
  }
  if (!pressed) return;
  __weak MeloNXSkinOverlay* weakSelf = self;
  if ([canonical isEqualToString:@"menu"]) {
    dispatch_async(dispatch_get_main_queue(), ^{
      MeloNXSkinOverlay* strongSelf = weakSelf;
      if (strongSelf.menuHandler != nil) strongSelf.menuHandler();
    });
  } else if ([MLXSkinSystemButtons() containsObject:canonical]) {
    dispatch_async(dispatch_get_main_queue(), ^{
      MeloNXSkinOverlay* strongSelf = weakSelf;
      if (strongSelf.systemButtonHandler != nil) strongSelf.systemButtonHandler(canonical);
    });
  }
}

@end
