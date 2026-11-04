// Behaviour of the orientation a game allows, from the skins the player
// CHOSE: real LibretroFrontendStore files (game > console inheritance, an
// explicit "default"), real Delta-format skins parsed by LibretroSkin, the real
// compatibility verdict and the real policy. Portrait only chosen -> portrait
// (2), landscape only chosen -> landscape (24), both or none -> usual
// rotation (26), whatever the skin FILE could also do. Replacement, refusal and
// a missing skin release the lock, and no assignment is erased.
//
// This runs the decision on real inputs; it does not rotate UIKit.
#import <Foundation/Foundation.h>

#import "LibretroFrontendStore.h"
#import "LibretroOrientationSelection.h"
#import "LibretroSkin.h"
#import "LibretroSkinCompatibility.h"

#include <stdio.h>

static int failures = 0;
static NSString *workDirectory = nil;

static void Report(BOOL passed, NSString *message, int line) {
  if (passed) {
    printf("PASS %s\n", message.UTF8String);
  } else {
    printf("FAIL %s (%s:%d)\n", message.UTF8String, __FILE__, line);
    failures++;
  }
}

#define CHECK(condition, ...) Report((condition) ? YES : NO, [NSString stringWithFormat:__VA_ARGS__], __LINE__)

enum { kPortrait = 2, kLandscape = 24, kBoth = 26 };

static NSData *PDFData(void) {
  return [@"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n"
      dataUsingEncoding:NSUTF8StringEncoding];
}

static NSDictionary *Frame(double x, double y, double width, double height) {
  return @{@"x" : @(x), @"y" : @(y), @"width" : @(width), @"height" : @(height)};
}

static NSDictionary *Button(id inputs, double x, double y, double size) {
  return @{@"inputs" : inputs, @"frame" : Frame(x, y, size, size)};
}

static NSDictionary *DPad(double x, double y, double size) {
  return @{
    @"inputs" : @{@"up" : @"up", @"down" : @"down", @"left" : @"left", @"right" : @"right"},
    @"frame" : Frame(x, y, size, size)
  };
}

static NSArray *GBAItems(void) {
  return @[
    DPad(20, 500, 150), Button(@[ @"a" ], 300, 520, 70), Button(@[ @"b" ], 220, 580, 70), Button(@[ @"l" ], 0, 420, 80),
    Button(@[ @"r" ], 300, 420, 80), Button(@[ @"start" ], 200, 760, 50), Button(@[ @"select" ], 130, 760, 50),
    Button(@[ @"menu" ], 170, 800, 40)
  ];
}

static NSDictionary *Representation(NSArray *items) {
  return @{
    @"items" : items,
    @"screens" : @[ @{@"inputFrame" : Frame(0, 0, 240, 160), @"outputFrame" : Frame(0, 60, 390, 260)} ],
    @"mappingSize" : @{@"width" : @390, @"height" : @844},
    @"extendedEdges" : @{@"top" : @6, @"bottom" : @6, @"left" : @6, @"right" : @6},
    @"assets" : @{@"resizable" : @"skin.pdf"},
  };
}

/// Installs the skin as <work>/Skins/<name> (the directory name is its identifier).
static LibretroSkin *InstallSkin(NSString *name, NSDictionary *portrait, NSDictionary *landscape) {
  NSMutableDictionary *orientations = [NSMutableDictionary dictionary];
  if (portrait != nil) orientations[@"portrait"] = portrait;
  if (landscape != nil) orientations[@"landscape"] = landscape;
  NSDictionary *info = @{
    @"name" : name,
    @"identifier" : [@"com.neostation.test." stringByAppendingString:name],
    @"gameTypeIdentifier" : @"com.rileytestut.delta.game.gba",
    @"representations" : @{@"iphone" : @{@"edgeToEdge" : orientations}},
  };
  NSString *directory = [[workDirectory stringByAppendingPathComponent:@"Skins"] stringByAppendingPathComponent:name];
  NSFileManager *manager = [NSFileManager defaultManager];
  [manager createDirectoryAtPath:directory withIntermediateDirectories:YES attributes:nil error:nil];
  [[NSJSONSerialization dataWithJSONObject:info options:0 error:nil]
      writeToFile:[directory stringByAppendingPathComponent:@"info.json"]
       atomically:YES];
  [PDFData() writeToFile:[directory stringByAppendingPathComponent:@"skin.pdf"] atomically:YES];
  NSString *code = nil;
  LibretroSkin *skin = [LibretroSkin skinWithDirectory:directory
                                       consoleGeometry:@{@"gba" : @{@"size" : @[ @240, @160 ]}}
                                             errorCode:&code];
  if (skin == nil) printf("  %s refused: %s\n", name.UTF8String, code.UTF8String);
  return skin;
}

static NSMutableDictionary<NSString *, LibretroSkin *> *gSkins;
static NSMutableDictionary<NSString *, LibretroSkinCompatibilityReport *> *gReports;
static NSMutableSet<NSString *> *gRefused;

static NSUInteger Mask(LibretroFrontendStore *store, NSString *game, BOOL touchNeeded) {
  return LibretroSelectedOrientationMask(
      store, @"gba", game,
      ^LibretroSkin *(NSString *identifier) {
        return [gRefused containsObject:identifier] ? nil : gSkins[identifier];
      },
      ^BOOL(LibretroSkin *skin, LibretroSkinOrientation orientation) {
        return LibretroSkinGivesLayout(skin, gReports[skin.installedIdentifier], orientation, NO, touchNeeded);
      });
}

static void Assign(LibretroFrontendStore *store, NSString *portrait, NSString *landscape, NSString *game) {
  [store setValue:portrait forKey:LibretroSettingSkinPortrait console:@"gba" game:game];
  [store setValue:landscape forKey:LibretroSettingSkinLandscape console:@"gba" game:game];
}

static void Learn(NSString *name, LibretroSkin *skin) {
  CHECK(skin != nil, @"skin %@ parses", name);
  if (skin == nil) return;
  gSkins[name] = skin;
  gReports[name] = [LibretroSkinCompatibility prepareSkin:skin console:@"gba"];
}

int main(int argc, const char *argv[]) {
  @autoreleasepool {
    NSString *base = argc > 1 ? @(argv[1]) : NSTemporaryDirectory();
    workDirectory = [base stringByAppendingPathComponent:[NSString stringWithFormat:@"orientation-%@", [NSUUID UUID].UUIDString]];
    [[NSFileManager defaultManager] createDirectoryAtPath:workDirectory withIntermediateDirectories:YES attributes:nil error:nil];
    gSkins = [NSMutableDictionary dictionary];
    gReports = [NSMutableDictionary dictionary];
    gRefused = [NSMutableSet set];

    Learn(@"only-portrait", InstallSkin(@"only-portrait", Representation(GBAItems()), nil));
    Learn(@"only-landscape", InstallSkin(@"only-landscape", nil, Representation(GBAItems())));
    Learn(@"dual-skin", InstallSkin(@"dual-skin", Representation(GBAItems()), Representation(GBAItems())));
    // Portrait layout without the essential controls: judged incompatible by touch.
    Learn(@"no-shoulders", InstallSkin(@"no-shoulders", Representation([GBAItems() subarrayWithRange:NSMakeRange(0, 3)]), nil));
    CHECK([[gSkins[@"only-portrait"] orientationsForIPad:NO] containsObject:@"landscape"] == NO &&
              [[gSkins[@"dual-skin"] orientationsForIPad:NO] containsObject:@"landscape"],
          @"fixtures: one file offers portrait only, another offers both");
    CHECK([gReports[@"no-shoulders"].orientations[@"portrait"] isEqualToString:@"incompatible"],
          @"fixtures: the layout without essential controls is incompatible (%@)", gReports[@"no-shoulders"].dictionary);

    LibretroFrontendStore *store = [LibretroFrontendStore storeWithDirectory:[workDirectory stringByAppendingPathComponent:@"Frontend"]];

    CHECK(Mask(store, nil, YES) == kBoth, @"nothing chosen: the usual rotation");

    Assign(store, @"only-portrait", nil, nil);
    CHECK(Mask(store, nil, YES) == kPortrait, @"portrait-only skin chosen for portrait: portrait lock");
    Assign(store, @"only-portrait", @"only-portrait", nil);
    CHECK(Mask(store, nil, YES) == kPortrait, @"the same portrait-only skin written to both keys: still portrait (no landscape layout)");
    Assign(store, nil, @"only-landscape", nil);
    CHECK(Mask(store, nil, YES) == kLandscape, @"landscape-only skin chosen for landscape: landscape lock");

    // The choice wins over the file's capabilities.
    Assign(store, nil, @"dual-skin", nil);
    CHECK(Mask(store, nil, YES) == kLandscape, @"dual-layout skin chosen for landscape only: landscape lock");
    Assign(store, @"dual-skin", nil, nil);
    CHECK(Mask(store, nil, YES) == kPortrait, @"dual-layout skin chosen for portrait only: portrait lock");
    Assign(store, @"dual-skin", @"dual-skin", nil);
    CHECK(Mask(store, nil, YES) == kBoth, @"dual-layout skin chosen for both: the player turns the phone");
    Assign(store, @"only-portrait", @"only-landscape", nil);
    CHECK(Mask(store, nil, YES) == kBoth, @"portrait-only and landscape-only skins chosen on purpose: both orientations");
    Assign(store, @"only-portrait", @"dual-skin", nil);
    CHECK(Mask(store, nil, YES) == kBoth, @"two distinct skins chosen: both orientations");

    // The default is never a second choice, explicit or not.
    Assign(store, @"dual-skin", LibretroDefaultSkinIdentifier, nil);
    CHECK(Mask(store, nil, YES) == kPortrait, @"landscape explicitly on default does not count as a choice");
    Assign(store, LibretroDefaultSkinIdentifier, @"dual-skin", nil);
    CHECK(Mask(store, nil, YES) == kLandscape, @"portrait explicitly on default does not count as a choice");

    // Game over console, per key; the assignments stay where they are.
    Assign(store, nil, nil, nil);
    Assign(store, @"dual-skin", @"dual-skin", nil);               // console: both
    Assign(store, nil, LibretroDefaultSkinIdentifier, @"game-a"); // game A: landscape back to default
    Assign(store, @"only-portrait", nil, @"game-b");              // game B: another portrait skin
    NSString *consoleFile = [[workDirectory stringByAppendingPathComponent:@"Frontend"] stringByAppendingPathComponent:@"gba.json"];
    NSData *before = [NSData dataWithContentsOfFile:consoleFile];
    CHECK(Mask(store, @"game-other", YES) == kBoth, @"a game without its own choice inherits the console (both)");
    CHECK(Mask(store, @"game-a", YES) == kPortrait, @"the game's explicit default overrides the console's landscape: portrait");
    CHECK(Mask(store, @"game-b", YES) == kBoth, @"the game's portrait choice, the console's landscape: both (per key inheritance)");
    CHECK([[NSData dataWithContentsOfFile:consoleFile] isEqualToData:before] &&
              [[store valueForKey:LibretroSettingSkinLandscape console:@"gba" game:@"game-a" scope:NULL] isEqual:LibretroDefaultSkinIdentifier] &&
              [[store valueForKey:LibretroSettingSkinLandscape console:@"gba" game:nil scope:NULL] isEqual:@"dual-skin"],
          @"computing the mask erased and changed no assignment");

    // Replacement: portrait-only -> dual / default releases the lock.
    Assign(store, nil, nil, nil);
    Assign(store, @"only-portrait", nil, nil);
    CHECK(Mask(store, nil, YES) == kPortrait, @"replacement start: portrait lock");
    Assign(store, @"dual-skin", @"dual-skin", nil);
    CHECK(Mask(store, nil, YES) == kBoth, @"portrait-only replaced by a dual skin: released");
    Assign(store, @"only-portrait", nil, nil);
    Assign(store, LibretroDefaultSkinIdentifier, LibretroDefaultSkinIdentifier, nil);
    CHECK(Mask(store, nil, YES) == kBoth, @"portrait-only replaced by the default: released");
    Assign(store, nil, @"only-landscape", nil);
    CHECK(Mask(store, nil, YES) == kLandscape, @"landscape lock");
    Assign(store, nil, @"dual-skin", nil);
    Assign(store, @"dual-skin", @"dual-skin", nil);
    CHECK(Mask(store, nil, YES) == kBoth, @"landscape-only replaced by a dual skin chosen for both: released");

    // A chosen skin that cannot be played in its orientation is not a choice.
    Assign(store, @"no-shoulders", nil, nil);
    CHECK(Mask(store, nil, YES) == kBoth, @"incompatible portrait skin, touch needed: default controls, no lock");
    CHECK(Mask(store, nil, NO) == kPortrait, @"the same skin with a physical controller or no touch: its layout is used, portrait lock");
    Assign(store, @"missing-skin", nil, nil);
    CHECK(Mask(store, nil, YES) == kBoth, @"a chosen skin that is not installed: no lock");
    Assign(store, @"only-portrait", nil, nil);
    [gRefused addObject:@"only-portrait"];
    CHECK(Mask(store, nil, YES) == kBoth, @"a refused skin: the lock is released, the assignment stays");
    CHECK([[store valueForKey:LibretroSettingSkinPortrait console:@"gba" game:nil scope:NULL] isEqual:@"only-portrait"],
          @"the refused skin is still assigned");
    [gRefused removeAllObjects];
    CHECK(Mask(store, nil, YES) == kPortrait, @"repaired: the lock returns with the same assignment");
  }
  if (failures > 0) {
    printf("%d orientation selection check(s) failed\n", failures);
    return 1;
  }
  printf("All orientation selection checks passed\n");
  return 0;
}
