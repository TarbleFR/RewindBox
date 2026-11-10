// SPDX-License-Identifier: GPL-3.0-or-later
// Controller skins for the embedded Dolphin (docs/dolphin-skins.md).
//
// Reads the representation of a .deltaskin / .manicskin the way the libretro
// renderer does (LibretroSkin.m, LibretroSkinLayout.m): the iPhone layout of
// the orientation (edge-to-edge or standard, an iPad layout when the skin has
// no iPhone one), its mappingSize, items (frame, extendedEdges, inputs,
// asset, thumbstick), screen (screens[].outputFrame or gameScreenFrame) and
// background. The placement is LayoutBase's: a Delta portrait skin without a
// screen is pinned to the bottom at full width with the game above it; any
// other is fitted in the bounds. Inputs go through TCManagerInterface, the
// way of the DolphiniOS pad, on the pad's port (GameCube 0, Wii 4).
#import "DOLSkinOverlay.h"
#import "DOLOrientationPolicy.h"
#import "DOLSkinHitTest.h"
#import "TouchController/TCManagerInterface.h"
#import <CoreGraphics/CoreGraphics.h>
#include <cmath>
#include <vector>

#pragma mark - Input table (DolphinSkins, lib/services/dolphin_skins.dart)

/// Lower case, letters and digits only (Dart: toLowerCase, [^a-z0-9] removed).
static NSString* DOLSkinKey(NSString* raw) {
  NSString* lower = raw.lowercaseString;
  NSMutableString* key = [NSMutableString stringWithCapacity:lower.length];
  for (NSUInteger i = 0; i < lower.length; i++) {
    const unichar c = [lower characterAtIndex:i];
    if ((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9')) [key appendFormat:@"%C", c];
  }
  return key;
}

static NSArray<NSString*>* DOLSkinDirections(void) { return @[ @"Up", @"Down", @"Left", @"Right" ]; }

// The two tables below are read by test/dolphin_skins_test.dart, which checks
// every entry against DolphinSkins.canonicalInput: keep one entry per line.
static NSDictionary<NSString*, NSString*>* DOLSkinGameCubeNames(void) {
  static NSDictionary<NSString*, NSString*>* names;
  static dispatch_once_t once;
  dispatch_once(&once, ^{
    names = @{
      // dolphin-skins-table: gc
      @"a" : @"a",
      @"b" : @"b",
      @"x" : @"x",
      @"y" : @"y",
      @"z" : @"z",
      @"start" : @"start",
      @"run" : @"start",
      @"plus" : @"start",
      @"l" : @"l",
      @"lefttrigger" : @"l",
      @"ltrigger" : @"l",
      @"r" : @"r",
      @"righttrigger" : @"r",
      @"rtrigger" : @"r",
      @"l2" : @"l",
      @"r2" : @"r",
      @"r1" : @"z",
      @"l1" : @"z",
      @"zr" : @"z",
      @"zl" : @"z",
      // dolphin-skins-table: end
    };
  });
  return names;
}

static NSDictionary<NSString*, NSString*>* DOLSkinWiiNames(void) {
  static NSDictionary<NSString*, NSString*>* names;
  static dispatch_once_t once;
  dispatch_once(&once, ^{
    names = @{
      // dolphin-skins-table: wii
      @"a" : @"a",
      @"b" : @"b",
      @"home" : @"home",
      @"plus" : @"plus",
      @"minus" : @"minus",
      @"1" : @"one",
      @"one" : @"one",
      @"2" : @"two",
      @"two" : @"two",
      @"x" : @"one",
      @"y" : @"two",
      @"start" : @"plus",
      @"select" : @"minus",
      @"c" : @"c",
      @"nunchukc" : @"c",
      @"z" : @"z",
      @"nunchukz" : @"z",
      @"l" : @"c",
      @"l1" : @"c",
      @"l2" : @"c",
      @"zl" : @"c",
      @"r" : @"z",
      @"r1" : @"z",
      @"r2" : @"z",
      @"zr" : @"z",
      // dolphin-skins-table: end
    };
  });
  return names;
}

NSString* DOLSkinCanonicalInput(BOOL wii, NSString* raw) {
  if (![raw isKindOfClass:NSString.class]) return nil;
  NSString* key = DOLSkinKey(raw);
  for (NSString* prefix in @[ @"leftthumbstick", @"analogstick", @"leftstick", @"leftanalog", @"analog", @"thumbstick" ]) {
    for (NSString* direction in DOLSkinDirections()) {
      if ([key isEqualToString:[prefix stringByAppendingString:direction.lowercaseString]])
        return [@"stick" stringByAppendingString:direction];
    }
  }
  for (NSString* prefix in @[ @"rightthumbstick", @"rightstick", @"rightanalog", @"cstick", @"c" ]) {
    for (NSString* direction in DOLSkinDirections()) {
      // The GameCube's C-stick; on a Wii the right stick moves the pointer.
      if ([key isEqualToString:[prefix stringByAppendingString:direction.lowercaseString]])
        return [(wii ? @"pointer" : @"c") stringByAppendingString:direction];
    }
  }
  for (NSString* direction in DOLSkinDirections()) {
    NSString* name = direction.lowercaseString;
    if ([key isEqualToString:name] || [key isEqualToString:[@"dpad" stringByAppendingString:name]]) return name;
  }
  if ([@[ @"menu", @"pause", @"options" ] containsObject:key]) return @"menu";
  if ([key isEqualToString:@"quicksave"]) return @"quickSave";
  if ([key isEqualToString:@"quickload"]) return @"quickLoad";
  return (wii ? DOLSkinWiiNames() : DOLSkinGameCubeNames())[key];
}

NSString* DOLSkinConsoleOfGameType(NSString* gameTypeIdentifier) {
  if (![gameTypeIdentifier isKindOfClass:NSString.class]) return nil;
  NSString* trimmed = [gameTypeIdentifier stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
  NSString* key = DOLSkinKey([trimmed componentsSeparatedByString:@"."].lastObject ?: @"");
  if ([@[ @"ngc", @"gc", @"gamecube", @"dol", @"dolphin" ] containsObject:key]) return @"gc";
  if ([@[ @"wii", @"rvl", @"revolution" ] containsObject:key]) return @"wii";
  return nil;
}

/// TCButtonType of a digital input (TouchController/TCButtonType.swift).
static NSDictionary<NSString*, NSNumber*>* DOLSkinButtonIds(BOOL wii) {
  if (wii) {
    return @{
      @"a" : @100, @"b" : @101, @"minus" : @102, @"plus" : @103, @"home" : @104, @"one" : @105, @"two" : @106,
      @"up" : @107, @"down" : @108, @"left" : @109, @"right" : @110, @"c" : @200, @"z" : @201,
    };
  }
  return @{
    @"a" : @0, @"b" : @1, @"start" : @2, @"x" : @3, @"y" : @4, @"z" : @5,
    @"up" : @6, @"down" : @7, @"left" : @8, @"right" : @9,
  };
}

/// The GameCube L and R triggers are axes, pressed fully (TCButton isAxis).
static NSDictionary<NSString*, NSNumber*>* DOLSkinTriggerIds(BOOL wii) {
  return wii ? @{} : @{@"l" : @20, @"r" : @21};
}

/// First axis (up) minus one of an analog family: GameCube main stick 10,
/// C-stick 15; Nunchuk stick 202, Wii pointer 111.
static NSInteger DOLSkinStickBase(BOOL wii, NSString* family) {
  if ([family isEqualToString:@"stick"]) return wii ? 202 : 10;
  if ([family isEqualToString:@"c"] && !wii) return 15;
  if ([family isEqualToString:@"pointer"] && wii) return 111;
  return -1;
}

/// "stick", "c" or "pointer" for `stickUp`, `cLeft`, `pointerDown`…; nil else.
static NSString* DOLSkinFamily(NSString* canonical, NSString** direction) {
  for (NSString* family in @[ @"stick", @"pointer", @"c" ]) {
    for (NSString* d in DOLSkinDirections()) {
      if ([canonical isEqualToString:[family stringByAppendingString:d]]) {
        if (direction) *direction = d.lowercaseString;
        return family;
      }
    }
  }
  return nil;
}

#pragma mark - Skin model

typedef NS_ENUM(NSInteger, DOLSkinItemKind) {
  DOLSkinItemKindButtons = 0,  // every input of the list together
  DOLSkinItemKindDPad = 1,     // up / down / left / right, digital
  DOLSkinItemKindStick = 2,    // the four directions of one analog family
};

@interface DOLSkinItem : NSObject
@property(nonatomic, assign) DOLSkinItemKind kind;
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
// (DOLSkinHitTest.h).
@property(nonatomic, strong, nullable) NSData* alphaMap;
@property(nonatomic, assign) CGSize alphaSize;
@end
@implementation DOLSkinItem
@end

/// The normal sprite's alpha, at most 192 pixels on its long side; nil when
/// it cannot be read or has no transparent pixel (then the frame is the shape).
static NSData* DOLSkinAlphaMap(NSString* path, CGSize* size) {
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

@interface DOLSkinRepresentation : NSObject
@property(nonatomic, assign) BOOL portrait;
@property(nonatomic, assign) CGSize mappingSize;
@property(nonatomic, copy, nullable) NSString* backgroundPath;
@property(nonatomic, copy) NSArray<DOLSkinItem*>* items;
@property(nonatomic, assign) BOOL hasScreen;
@property(nonatomic, assign) CGRect screen;
/// The pack's own cutout of its screen (`screens[].screenCutout`), nil without one.
@property(nonatomic, copy, nullable) NSString* cutoutPath;
@property(nonatomic, assign) BOOL translucent;
@end
@implementation DOLSkinRepresentation
@end

static BOOL DOLSkinNumber(id value, CGFloat* out) {
  if (![value isKindOfClass:NSNumber.class]) return NO;
  const double number = [(NSNumber*)value doubleValue];
  if (!std::isfinite(number)) return NO;
  *out = (CGFloat)number;
  return YES;
}

static BOOL DOLSkinSize(id value, CGSize* out) {
  if (![value isKindOfClass:NSDictionary.class]) return NO;
  CGFloat width = 0, height = 0;
  if (!DOLSkinNumber(value[@"width"], &width) || !DOLSkinNumber(value[@"height"], &height)) return NO;
  if (!(width > 0) || !(height > 0)) return NO;
  *out = CGSizeMake(width, height);
  return YES;
}

static BOOL DOLSkinRect(id value, CGRect* out) {
  if (![value isKindOfClass:NSDictionary.class]) return NO;
  CGFloat x = 0, y = 0;
  CGSize size;
  if (!DOLSkinNumber(value[@"x"], &x) || !DOLSkinNumber(value[@"y"], &y) || !DOLSkinSize(value, &size)) return NO;
  *out = CGRectMake(x, y, size.width, size.height);
  return YES;
}

/// extendedEdges, each missing or invalid side taken from `fallback`.
static UIEdgeInsets DOLSkinEdges(id value, UIEdgeInsets fallback) {
  if (![value isKindOfClass:NSDictionary.class]) return fallback;
  UIEdgeInsets edges = fallback;
  CGFloat side = 0;
  if (DOLSkinNumber(value[@"top"], &side) && side >= 0) edges.top = side;
  if (DOLSkinNumber(value[@"left"], &side) && side >= 0) edges.left = side;
  if (DOLSkinNumber(value[@"bottom"], &side) && side >= 0) edges.bottom = side;
  if (DOLSkinNumber(value[@"right"], &side) && side >= 0) edges.right = side;
  return edges;
}

/// A file of the skin's own folder; nil for anything outside it.
static NSString* DOLSkinFile(NSString* root, id name) {
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
static NSString* DOLSkinAsset(NSString* root, id assets) {
  if ([assets isKindOfClass:NSString.class]) return DOLSkinFile(root, assets);
  if (![assets isKindOfClass:NSDictionary.class]) return nil;
  for (NSString* key in @[ @"resizable", @"large", @"medium", @"small", @"normal" ]) {
    NSString* path = DOLSkinFile(root, assets[key]);
    if (path != nil) return path;
  }
  return nil;
}

static NSDictionary* DOLSkinReadJSON(NSString* path) {
  NSData* data = [NSData dataWithContentsOfFile:path options:NSDataReadingMappedIfSafe error:nil];
  if (data == nil || data.length > 4 * 1024 * 1024) return nil;
  id object = [NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
  return [object isKindOfClass:NSDictionary.class] ? object : nil;
}

/// LibretroSkinService.isInstalledId: ^[a-z0-9-]+$ and never "default".
static BOOL DOLSkinIsInstalledId(NSString* identifier) {
  if (![identifier isKindOfClass:NSString.class] || identifier.length == 0 || identifier.length > 128) return NO;
  if ([identifier isEqualToString:@"default"]) return NO;
  NSCharacterSet* allowed = [NSCharacterSet characterSetWithCharactersInString:@"abcdefghijklmnopqrstuvwxyz0123456789-"];
  return [identifier rangeOfCharacterFromSet:allowed.invertedSet].location == NSNotFound;
}

/// The skin chosen for `orientation`: the game's choice when it has one for
/// that key (even "default"), else the console's.
static NSString* DOLSkinSelected(NSDictionary* document, NSString* gameKey, NSString* orientation) {
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
  return DOLSkinIsInstalledId(value) ? value : nil;
}

/// The layout of `orientation` for this device: the iPhone's (edge-to-edge
/// on a tall screen, else standard), an iPad layout when there is none.
static NSDictionary* DOLSkinLayoutFor(NSDictionary* info, NSString* orientation) {
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

static DOLSkinRepresentation* DOLSkinParse(NSDictionary* layout, NSString* root, BOOL wii, BOOL portrait) {
  CGSize mapping;
  if (!DOLSkinSize(layout[@"mappingSize"], &mapping)) return nil;
  const UIEdgeInsets defaultEdges = DOLSkinEdges(layout[@"extendedEdges"], UIEdgeInsetsZero);
  NSMutableArray<DOLSkinItem*>* items = [NSMutableArray array];
  NSArray* objects = [layout[@"items"] isKindOfClass:NSArray.class] ? layout[@"items"] : @[];
  NSUInteger usable = 0;
  for (NSDictionary* object in objects) {
    if (![object isKindOfClass:NSDictionary.class]) continue;
    CGRect frame;
    if (!DOLSkinRect(object[@"frame"], &frame)) continue;
    DOLSkinItem* item = [DOLSkinItem new];
    item.frame = frame;
    const UIEdgeInsets edges = DOLSkinEdges(object[@"extendedEdges"], defaultEdges);
    item.hitFrame = CGRectMake(frame.origin.x - edges.left, frame.origin.y - edges.top,
                               frame.size.width + edges.left + edges.right, frame.size.height + edges.top + edges.bottom);
    item.inputs = @[];
    item.directions = @{};
    id inputs = object[@"inputs"];
    if ([inputs isKindOfClass:NSDictionary.class]) {
      NSMutableDictionary<NSString*, NSString*>* directions = [NSMutableDictionary dictionary];
      NSString* family = nil;
      BOOL analog = YES;
      for (NSString* d in DOLSkinDirections()) {
        NSString* name = d.lowercaseString;
        NSString* canonical = DOLSkinCanonicalInput(wii, [inputs objectForKey:name]);
        if (canonical == nil) continue;
        directions[name] = canonical;
        NSString* direction = nil;
        NSString* own = DOLSkinFamily(canonical, &direction);
        if (own == nil || ![direction isEqualToString:name] || (family != nil && ![family isEqualToString:own])) analog = NO;
        family = family ?: own;
      }
      item.directions = directions;
      item.kind = analog && family != nil && DOLSkinStickBase(wii, family) >= 0 ? DOLSkinItemKindStick : DOLSkinItemKindDPad;
      if (item.kind == DOLSkinItemKindStick) item.family = family;
      NSDictionary* thumbstick = object[@"thumbstick"];
      CGSize knob;
      if ([thumbstick isKindOfClass:NSDictionary.class] && DOLSkinSize(thumbstick, &knob)) {
        item.knobPath = DOLSkinFile(root, thumbstick[@"name"]);
        item.knobSize = knob;
      }
      if (directions.count > 0) usable++;
    } else if ([inputs isKindOfClass:NSArray.class]) {
      NSMutableArray<NSString*>* list = [NSMutableArray array];
      for (id raw in (NSArray*)inputs) {
        NSString* canonical = DOLSkinCanonicalInput(wii, raw);
        if (canonical != nil && ![list containsObject:canonical]) [list addObject:canonical];
      }
      item.kind = DOLSkinItemKindButtons;
      item.inputs = list;
      if (list.count > 0) usable++;
    }
    id asset = object[@"asset"];
    if ([asset isKindOfClass:NSString.class]) {
      item.assetPath = DOLSkinFile(root, asset);
    } else if ([asset isKindOfClass:NSDictionary.class]) {
      item.assetPath = DOLSkinFile(root, asset[@"normal"]);
      item.pressedAssetPath = DOLSkinFile(root, asset[@"pressed"]);
    }
    CGSize alphaSize = CGSizeZero;
    item.alphaMap = DOLSkinAlphaMap(item.assetPath, &alphaSize);
    item.alphaSize = alphaSize;
    if (item.inputs.count == 0 && item.directions.count == 0 && item.assetPath == nil) continue;
    [items addObject:item];
  }
  if (usable == 0) return nil;
  DOLSkinRepresentation* representation = [DOLSkinRepresentation new];
  representation.portrait = portrait;
  representation.mappingSize = mapping;
  representation.items = items;
  representation.backgroundPath = DOLSkinAsset(root, layout[@"assets"]);
  representation.translucent = [layout[@"translucent"] isKindOfClass:NSNumber.class] && [layout[@"translucent"] boolValue];
  CGRect screen;
  if (DOLSkinRect(layout[@"gameScreenFrame"], &screen)) {
    // Legacy key: wins over `screens` (Delta).
    representation.hasScreen = YES;
    representation.screen = screen;
  } else if ([layout[@"screens"] isKindOfClass:NSArray.class]) {
    for (NSDictionary* entry in (NSArray*)layout[@"screens"]) {
      if ([entry isKindOfClass:NSDictionary.class] && DOLSkinRect(entry[@"outputFrame"], &screen)) {
        representation.hasScreen = YES;
        representation.screen = screen;
        representation.cutoutPath = DOLSkinFile(root, entry[@"screenCutout"]);
        break;
      }
    }
  }
  return representation;
}

#pragma mark - Images

/// First page of a PDF drawn at `points` (Delta stretches PDF assets).
static UIImage* DOLSkinPDF(NSString* path, CGSize points) {
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

static UIImage* DOLSkinImage(NSString* path, CGSize points) {
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
    image = pdf ? DOLSkinPDF(path, points) : [UIImage imageWithContentsOfFile:path];
    if (image != nil) [cache setObject:image forKey:key];
  }
  return image;
}

static CGRect DOLSkinScaled(CGRect rect, CGSize mapping, CGRect skin) {
  const CGFloat sx = skin.size.width / mapping.width, sy = skin.size.height / mapping.height;
  return CGRectMake(skin.origin.x + rect.origin.x * sx, skin.origin.y + rect.origin.y * sy, rect.size.width * sx,
                    rect.size.height * sy);
}

static CGRect DOLSkinAspectFit(CGRect bounds, CGFloat aspect) {
  if (!(aspect > 0) || !(bounds.size.width > 0) || !(bounds.size.height > 0)) return bounds;
  CGFloat width = bounds.size.width, height = width / aspect;
  if (height > bounds.size.height) {
    height = bounds.size.height;
    width = height * aspect;
  }
  return CGRectMake(bounds.origin.x + (bounds.size.width - width) / 2, bounds.origin.y + (bounds.size.height - height) / 2,
                    width, height);
}

/// Where a skin and the game go in `bounds`: the skin fitted with one scale and centred
/// (or, Delta portrait without a screen, at the bottom at full width), the game in the
/// skin's screen scaled and moved by that same transform. One function for the layout and
/// for the surface the core reads at launch (`screenFrameForBounds:`).
static CGRect DOLSkinPlace(DOLSkinRepresentation* skin, CGRect bounds, UIEdgeInsets insets, CGRect* skinRect) {
  const CGSize mapping = skin.mappingSize;
  const CGFloat width = bounds.size.width, height = bounds.size.height;
  const CGFloat pinnedHeight = width * mapping.height / mapping.width;
  CGRect gameArea = bounds;
  if (skin.portrait && !skin.hasScreen && pinnedHeight <= height) {
    // Delta portrait: the controller at the bottom at full width, the game
    // above it (below the safe area's top).
    *skinRect = CGRectMake(0, height - pinnedHeight, width, pinnedHeight);
    const CGFloat top = MIN(insets.top, skinRect->origin.y);
    gameArea = CGRectMake(0, top, width, skinRect->origin.y - top);
    if (gameArea.size.height < 1) gameArea = CGRectMake(0, 0, width, MAX(skinRect->origin.y, 1));
  } else {
    // Fitted in the whole bounds, safe areas ignored (Delta).
    *skinRect = DOLSkinAspectFit(bounds, mapping.width / mapping.height);
  }
  return skin.hasScreen ? DOLSkinScaled(skin.screen, mapping, *skinRect) : gameArea;
}

#pragma mark - Overlay

@interface DOLSkinTrack : NSObject
@property(nonatomic, assign) NSInteger item;  // index in the representation, -1 none
@property(nonatomic, assign) BOOL pointer;    // the Wii pointer, by the game's screen
@property(nonatomic, assign) CGPoint location;
@end
@implementation DOLSkinTrack
@end

@implementation DOLSkinOverlay {
  BOOL _wii;
  NSInteger _port;
  DOLSkinRepresentation* _portrait;
  DOLSkinRepresentation* _landscape;
  DOLSkinRepresentation* _current;
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
  NSMapTable<UITouch*, DOLSkinTrack*>* _tracks;
  NSSet<NSString*>* _pressed;
  NSDictionary<NSString*, NSValue*>* _vectors;
  NSSet<NSNumber*>* _pressedItems;
  CGPoint _pointer;
  BOOL _pointerSent;
  UIImpactFeedbackGenerator* _haptics;
}

- (instancetype)initWithWii:(BOOL)wii gameKey:(NSString*)gameKey {
  self = [super initWithFrame:CGRectZero];
  if (!self) return nil;
  _wii = wii;
  // The DolphiniOS pad's port: GameCube 0, Wii 4 (DolphinTouchOverlay).
  _port = wii ? 4 : 0;
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
  self.accessibilityIdentifier = @"dolphin.skin.overlay";

  NSString* documents = NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES).firstObject;
  NSString* libretro = [documents stringByAppendingPathComponent:@"Libretro"];
  NSString* console = wii ? @"wii" : @"gc";
  NSString* selectionPath = [[libretro stringByAppendingPathComponent:@"Config/Frontend"]
      stringByAppendingPathComponent:[console stringByAppendingString:@".json"]];
  NSDictionary* selection = documents.length > 0 ? DOLSkinReadJSON(selectionPath) : nil;
  NSString* skins = [libretro stringByAppendingPathComponent:@"Skins"];
  for (NSString* orientation in @[ @"portrait", @"landscape" ]) {
    NSString* identifier = selection != nil ? DOLSkinSelected(selection, gameKey, orientation) : nil;
    if (identifier == nil) continue;
    NSString* root = [skins stringByAppendingPathComponent:identifier];
    NSDictionary* info = DOLSkinReadJSON([root stringByAppendingPathComponent:@"info.json"]);
    // Only a skin of this console (the import checked it; a skin may have
    // been replaced by another one since).
    if (info == nil || ![DOLSkinConsoleOfGameType(info[@"gameTypeIdentifier"]) isEqualToString:console]) {
      NSLog(@"dolphin.skin.ignored %@ %@", orientation, identifier);
      continue;
    }
    NSDictionary* layout = DOLSkinLayoutFor(info, orientation);
    DOLSkinRepresentation* representation =
        layout != nil ? DOLSkinParse(layout, root, wii, [orientation isEqualToString:@"portrait"]) : nil;
    if (representation == nil) {
      NSLog(@"dolphin.skin.unusable %@ %@", orientation, identifier);
      continue;
    }
    if ([orientation isEqualToString:@"portrait"]) {
      _portrait = representation;
    } else {
      _landscape = representation;
    }
    NSLog(@"dolphin.skin.selected %@ %@", orientation, identifier);
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
  return (UIInterfaceOrientationMask)DOLPolicyMask(_portrait != nil, _landscape != nil);
}

- (BOOL)layoutActive {
  return _current != nil;
}

- (BOOL)hasMenuControl {
  for (DOLSkinItem* item in _current.items) {
    if ([item.inputs containsObject:@"menu"]) return YES;
  }
  return NO;
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
  for (DOLSkinItem* item in _current.items) {
    UIImageView* view = [UIImageView new];
    view.contentMode = UIViewContentModeScaleToFill;
    view.alpha = opacity;
    view.hidden = item.assetPath == nil;
    [self addSubview:view];
    [_itemViews addObject:view];
    UIImageView* knob = [UIImageView new];
    knob.contentMode = UIViewContentModeScaleToFill;
    knob.alpha = opacity;
    knob.hidden = item.kind != DOLSkinItemKindStick || item.knobPath == nil;
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

- (CGRect)screenFrameForBounds:(CGRect)bounds {
  if (bounds.size.width < 1 || bounds.size.height < 1) return CGRectNull;
  DOLSkinRepresentation* skin = bounds.size.height > bounds.size.width ? _portrait : _landscape;
  if (skin == nil) return CGRectNull;
  CGRect skinRect;
  return DOLSkinPlace(skin, bounds, self.safeAreaInsets, &skinRect);
}

- (BOOL)screenCutoutActive {
  return _current.hasScreen && _background.layer.mask == _cutoutMask && _cutoutMask.contents != nil;
}

- (void)layoutSubviews {
  [super layoutSubviews];
  const CGRect bounds = self.bounds;
  const UIEdgeInsets insets = self.safeAreaInsets;
  DOLSkinRepresentation* representation = bounds.size.height > bounds.size.width ? _portrait : _landscape;
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
  _screenFrame = DOLSkinPlace(_current, bounds, insets, &_skinRect);

  _background.hidden = _current.backgroundPath == nil;
  _background.frame = _skinRect;
  _background.image = DOLSkinImage(_current.backgroundPath, _skinRect.size);
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
  [_current.items enumerateObjectsUsingBlock:^(DOLSkinItem* item, NSUInteger index, __unused BOOL* stop) {
    UIImageView* view = self->_itemViews[index];
    view.frame = DOLSkinScaled(item.frame, mapping, self->_skinRect);
    view.image = DOLSkinImage(item.assetPath, view.frame.size);
    view.highlightedImage = DOLSkinImage(item.pressedAssetPath, view.frame.size);
  }];
  [self refreshPressedViews];
  if (self.layoutChanged) self.layoutChanged();
}

/// LibretroSkinLayout knobFrameForItem: the knob's size in mapping points,
/// moved by the stick vector within the frame.
- (CGRect)knobFrameForItem:(DOLSkinItem*)item frame:(CGRect)frame vector:(CGPoint)vector {
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
  [_current.items enumerateObjectsUsingBlock:^(DOLSkinItem* item, NSUInteger index, __unused BOOL* stop) {
    UIImageView* view = self->_itemViews[index];
    const BOOL pressed = [self->_pressedItems containsObject:@(index)];
    view.highlighted = pressed && view.highlightedImage != nil;
    // Without a pressed asset, a held control dims a little.
    const CGFloat opacity = self->_current.translucent ? 0.7 : 1.0;
    view.alpha = pressed && view.highlightedImage == nil ? opacity * 0.6 : opacity;
    UIImageView* knob = self->_knobViews[index];
    if (knob.hidden) return;
    const CGRect frame = DOLSkinScaled(item.frame, mapping, self->_skinRect);
    NSValue* vector = item.family != nil ? self->_vectors[item.family] : nil;
    const CGPoint deflection = [item.family isEqualToString:@"pointer"] || vector == nil ? CGPointZero : vector.CGPointValue;
    knob.frame = [self knobFrameForItem:item frame:frame vector:deflection];
    if (knob.image == nil || !CGSizeEqualToSize(knob.image.size, knob.frame.size))
      knob.image = DOLSkinImage(item.knobPath, knob.frame.size);
  }];
}

#pragma mark Touches

- (UIView*)hitTest:(CGPoint)point withEvent:(UIEvent*)event {
  if (self.hidden || !self.userInteractionEnabled || self.alpha < 0.01 || _current == nil) return nil;
  if (CGRectContainsPoint(_skinRect, point)) return self;
  // The Wii pointer follows a finger on the game's screen.
  if (_wii && CGRectContainsPoint(_screenFrame, point)) return self;
  return nil;
}

/// The control under `point` (DOLSkinHitTest.h): the drawn shape first, then
/// the nearest frame, then the nearest extended touch area.
- (NSInteger)itemAtPoint:(CGPoint)point {
  if (_current == nil || CGRectIsNull(_skinRect)) return -1;
  const CGSize mapping = _current.mappingSize;
  const CGPoint local = CGPointMake((point.x - _skinRect.origin.x) * mapping.width / _skinRect.size.width,
                                    (point.y - _skinRect.origin.y) * mapping.height / _skinRect.size.height);
  NSArray<DOLSkinItem*>* items = _current.items;
  std::vector<DOLSkinHitItem> hits(items.count);
  for (NSUInteger index = 0; index < items.count; index++) {
    DOLSkinItem* item = items[index];
    const CGRect f = item.frame, h = item.hitFrame;
    hits[index] = DOLSkinHitItem{f.origin.x, f.origin.y, f.size.width, f.size.height,
                                 h.origin.x, h.origin.y, h.size.width, h.size.height,
                                 item.alphaMap != nil ? (const uint8_t*)item.alphaMap.bytes : nullptr,
                                 (long)item.alphaSize.width, (long)item.alphaSize.height,
                                 (item.inputs.count > 0 || item.directions.count > 0) ? 1 : 0};
  }
  return (NSInteger)DOLSkinHitIndex(hits.data(), (long)hits.size(), local.x, local.y);
}

- (void)touchesBegan:(NSSet<UITouch*>*)touches withEvent:(UIEvent*)event {
  for (UITouch* touch in touches) {
    DOLSkinTrack* track = [DOLSkinTrack new];
    track.location = [touch locationInView:self];
    track.item = [self itemAtPoint:track.location];
    track.pointer = track.item < 0 && _wii && CGRectContainsPoint(_screenFrame, track.location);
    [_tracks setObject:track forKey:touch];
  }
  [_haptics prepare];
  [self updateInputs];
}

- (void)touchesMoved:(NSSet<UITouch*>*)touches withEvent:(UIEvent*)event {
  for (UITouch* touch in touches) {
    DOLSkinTrack* track = [_tracks objectForKey:touch];
    if (track == nil) continue;
    track.location = [touch locationInView:self];
    if (track.pointer) continue;
    // A finger on a stick keeps it; any other slides from control to control.
    const BOOL stick = track.item >= 0 && _current.items[(NSUInteger)track.item].kind == DOLSkinItemKindStick;
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
- (NSArray<NSString*>*)dpadDirectionsOf:(DOLSkinItem*)item at:(CGPoint)location frame:(CGRect)frame {
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
  BOOL pointerTouched = NO;
  CGPoint pointer = _pointer;
  const CGSize mapping = _current.mappingSize;
  for (UITouch* touch in _tracks) {
    DOLSkinTrack* track = [_tracks objectForKey:touch];
    if (track.pointer) {
      // Follow mode of the DolphiniOS Wii pad: the finger is the pointer.
      const CGRect screen = _screenFrame;
      pointer = CGPointMake(MIN(MAX((track.location.x - CGRectGetMidX(screen)) / MAX(screen.size.width / 2, 1), -1), 1),
                            MIN(MAX((track.location.y - CGRectGetMidY(screen)) / MAX(screen.size.height / 2, 1), -1), 1));
      pointerTouched = YES;
      continue;
    }
    if (track.item < 0 || _current == nil || track.item >= (NSInteger)_current.items.count) continue;
    DOLSkinItem* item = _current.items[(NSUInteger)track.item];
    const CGRect frame = DOLSkinScaled(item.frame, mapping, _skinRect);
    switch (item.kind) {
      case DOLSkinItemKindButtons:
        [pressed addObjectsFromArray:item.inputs];
        if (item.inputs.count > 0) [pressedItems addObject:@(track.item)];
        break;
      case DOLSkinItemKindDPad: {
        NSArray<NSString*>* directions = [self dpadDirectionsOf:item at:track.location frame:frame];
        for (NSString* direction in directions) {
          NSString* canonical = item.directions[direction];
          if (canonical != nil) [pressed addObject:canonical];
        }
        if (directions.count > 0) [pressedItems addObject:@(track.item)];
        break;
      }
      case DOLSkinItemKindStick: {
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
    NSString* family = DOLSkinFamily(canonical, &direction);
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
  if (pointerTouched || (_wii && vectors[@"pointer"] != nil)) {
    if (vectors[@"pointer"] != nil && !pointerTouched) pointer = vectors[@"pointer"].CGPointValue;
    [self sendPointer:pointer];
  }
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
  NSMutableSet<NSString*>* families = [NSMutableSet setWithArray:_vectors.allKeys];
  [families addObjectsFromArray:vectors.allKeys];
  for (NSString* family in families) {
    if ([family isEqualToString:@"pointer"]) continue;  // sendPointer
    NSValue* now = vectors[family];
    NSValue* before = _vectors[family];
    const CGPoint vector = now != nil ? now.CGPointValue : CGPointZero;
    if (before != nil && CGPointEqualToPoint(before.CGPointValue, vector)) continue;
    [self sendStick:family vector:vector];
  }
  _pressed = [pressed copy];
  _vectors = [vectors copy];
}

/// TCJoystick: up, down, left, right axes of the family, each one-sided.
- (void)sendStick:(NSString*)family vector:(CGPoint)vector {
  const NSInteger base = DOLSkinStickBase(_wii, family);
  if (base < 0) return;
  const float axes[4] = {(float)MAX(-1, MIN(vector.y, 0)), (float)MAX(0, MIN(vector.y, 1)),
                         (float)MAX(-1, MIN(vector.x, 0)), (float)MAX(0, MIN(vector.x, 1))};
  for (NSInteger i = 0; i < 4; i++) {
    [TCManagerInterface setAxisValueFor:base + i + 1 controller:_port value:axes[i]];
  }
}

/// TCWiiPad: the pointer's y on its up and down axes, x on left and right.
- (void)sendPointer:(CGPoint)pointer {
  if (!_wii) return;
  if (_pointerSent && CGPointEqualToPoint(pointer, _pointer)) return;
  _pointer = pointer;
  _pointerSent = YES;
  const NSInteger base = DOLSkinStickBase(YES, @"pointer");
  const float axes[4] = {(float)pointer.y, (float)pointer.y, (float)pointer.x, (float)pointer.x};
  for (NSInteger i = 0; i < 4; i++) {
    [TCManagerInterface setAxisValueFor:base + i + 1 controller:_port value:axes[i]];
  }
}

- (void)send:(NSString*)canonical pressed:(BOOL)pressed {
  NSNumber* button = DOLSkinButtonIds(_wii)[canonical];
  if (button != nil) {
    [TCManagerInterface setButtonStateFor:button.integerValue controller:_port state:pressed];
    return;
  }
  NSNumber* trigger = DOLSkinTriggerIds(_wii)[canonical];
  if (trigger != nil) {
    [TCManagerInterface setAxisValueFor:trigger.integerValue controller:_port value:pressed ? 1.0f : 0.0f];
    return;
  }
  if (!pressed) return;
  if ([canonical isEqualToString:@"menu"] || [canonical isEqualToString:@"quickSave"] ||
      [canonical isEqualToString:@"quickLoad"]) {
    // The in-game menu (its save states for quick save and load), after the
    // current touch event: the session hides and releases the controls.
    __weak DOLSkinOverlay* weakSelf = self;
    dispatch_async(dispatch_get_main_queue(), ^{
      DOLSkinOverlay* strongSelf = weakSelf;
      if (strongSelf.menuHandler != nil) strongSelf.menuHandler();
    });
  }
}

@end
