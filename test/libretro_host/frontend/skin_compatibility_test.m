// Behaviour of LibretroSkinCompatibility, the central iPhone filter of
// skins: real Delta-format skins are written, parsed by LibretroSkin and
// judged compatible, adaptable or incompatible with their reasons
// (essential controls, adapted names, dead buttons, iPad layouts large
// enough or not on an iPhone, screen-only skins, missing artwork).
#import <Foundation/Foundation.h>

#import "LibretroDefaultSkins.h"
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

/// A complete GBA layout on a 390 x 844 iPhone mapping, `scale` times the
/// usual size (items shrink around the origin).
static NSArray *GBAItems(double scale) {
  return @[
    DPad(20 * scale, 500 * scale, 150 * scale), Button(@[ @"a" ], 300 * scale, 520 * scale, 70 * scale),
    Button(@[ @"b" ], 220 * scale, 580 * scale, 70 * scale), Button(@[ @"l" ], 0, 420 * scale, 80 * scale),
    Button(@[ @"r" ], 300 * scale, 420 * scale, 80 * scale), Button(@[ @"start" ], 200 * scale, 760 * scale, 50 * scale),
    Button(@[ @"select" ], 130 * scale, 760 * scale, 50 * scale), Button(@[ @"menu" ], 170 * scale, 800 * scale, 40 * scale)
  ];
}

static NSDictionary *Representation(NSArray *items, double width, double height, BOOL artwork) {
  NSMutableDictionary *representation = [@{
    @"items" : items,
    @"screens" : @[ @{@"inputFrame" : Frame(0, 0, 240, 160), @"outputFrame" : Frame(0, 60, width, width * 2 / 3)} ],
    @"mappingSize" : @{@"width" : @(width), @"height" : @(height)},
    @"extendedEdges" : @{@"top" : @6, @"bottom" : @6, @"left" : @6, @"right" : @6},
  } mutableCopy];
  if (artwork) representation[@"assets"] = @{@"resizable" : @"skin.pdf"};
  return representation;
}

static LibretroSkin *Skin(NSString *name, NSString *gameType, NSDictionary *representations) {
  NSDictionary *info = @{
    @"name" : name,
    @"identifier" : [@"com.neostation.test." stringByAppendingString:name],
    @"gameTypeIdentifier" : gameType,
    @"representations" : representations,
  };
  NSString *directory = [workDirectory stringByAppendingPathComponent:name];
  NSFileManager *manager = [NSFileManager defaultManager];
  [manager removeItemAtPath:directory error:nil];
  [manager createDirectoryAtPath:directory withIntermediateDirectories:YES attributes:nil error:nil];
  [[NSJSONSerialization dataWithJSONObject:info options:0 error:nil]
      writeToFile:[directory stringByAppendingPathComponent:@"info.json"]
       atomically:YES];
  [PDFData() writeToFile:[directory stringByAppendingPathComponent:@"skin.pdf"] atomically:YES];
  NSDictionary *geometry = @{
    @"gba" : @{@"size" : @[ @240, @160 ]},
    @"nds" : @{@"size" : @[ @256, @384 ], @"regions" : @{@"top" : @[ @0, @0, @1, @0.5 ], @"bottom" : @[ @0, @0.5, @1, @0.5 ]}},
    @"n64" : @{@"size" : @[ @320, @240 ]},
  };
  NSString *code = nil;
  LibretroSkin *skin = [LibretroSkin skinWithDirectory:directory consoleGeometry:geometry errorCode:&code];
  if (skin == nil) printf("  %s refused: %s\n", name.UTF8String, code.UTF8String);
  return skin;
}

static NSDictionary *Phone(NSDictionary *portrait, NSDictionary *landscape) {
  NSMutableDictionary *orientations = [NSMutableDictionary dictionary];
  if (portrait != nil) orientations[@"portrait"] = portrait;
  if (landscape != nil) orientations[@"landscape"] = landscape;
  return @{@"iphone" : @{@"edgeToEdge" : orientations}};
}

static NSString *const kGBA = @"com.rileytestut.delta.game.gba";

static void TestVerdicts(void) {
  NSDictionary *landscapeItems = Representation(GBAItems(1), 390, 844, YES);
  LibretroSkin *complete = Skin(@"complete", kGBA, Phone(Representation(GBAItems(1), 390, 844, YES), landscapeItems));
  LibretroSkinCompatibilityReport *report = [LibretroSkinCompatibility evaluateSkin:complete console:@"gba"];
  CHECK(report.status == LibretroSkinCompatibilityCompatible && report.reasons.count == 0 &&
            [report.orientations[@"portrait"] isEqualToString:@"compatible"] && report.missingControls.count == 0,
        @"a full Delta GBA skin is compatible (%@)", report.dictionary);
  NSDictionary *dictionary = report.dictionary;
  CHECK([dictionary[@"status"] isEqualToString:@"compatible"] && [dictionary[@"console"] isEqualToString:@"gba"] &&
            dictionary[@"orientations"] != nil && dictionary[@"smallestControlPoints"] != nil,
        @"the report reaches Dart as a dictionary");

  LibretroSkin *portraitOnly = Skin(@"portrait-only", kGBA, Phone(Representation(GBAItems(1), 390, 844, YES), nil));
  report = [LibretroSkinCompatibility evaluateSkin:portraitOnly console:@"gba"];
  CHECK(report.status == LibretroSkinCompatibilityCompatible &&
            [report.orientations[@"landscape"] isEqualToString:@"missing"],
        @"a portrait-only skin is compatible, landscape uses the default skin");

  NSMutableArray *adapted = [GBAItems(1) mutableCopy];
  adapted[5] = Button(@[ @"run" ], 200, 760, 50);
  [adapted addObject:Button(@[ @"upLeft" ], 0, 680, 40)];
  report = [LibretroSkinCompatibility evaluateSkin:Skin(@"adapted", kGBA, Phone(Representation(adapted, 390, 844, YES), nil))
                                           console:@"gba"];
  CHECK(report.status == LibretroSkinCompatibilityAdaptable &&
            [report.reasons isEqualToArray:@[ LibretroSkinCompatAdaptedInputs ]] &&
            [report.adaptedInputs isEqualToArray:(@[ @"run", @"upLeft" ])],
        @"other emulators' names make the skin adaptable (%@)", report.dictionary);

  NSMutableArray *dead = [GBAItems(1) mutableCopy];
  [dead addObject:Button(@[ @"x" ], 330, 300, 40)];
  report = [LibretroSkinCompatibility evaluateSkin:Skin(@"dead", kGBA, Phone(Representation(dead, 390, 844, YES), nil))
                                           console:@"gba"];
  CHECK(report.status == LibretroSkinCompatibilityAdaptable && report.deadItems == 1 &&
            [report.reasons containsObject:LibretroSkinCompatDeadButtons] &&
            [report.unsupportedInputs isEqualToArray:@[ @"x" ]],
        @"a drawn button the console lacks is reported dead, the skin stays playable");

  NSMutableArray *decorated = [GBAItems(1) mutableCopy];
  [decorated addObject:Button(@[], 330, 300, 40)];
  report = [LibretroSkinCompatibility evaluateSkin:Skin(@"decorated", kGBA, Phone(Representation(decorated, 390, 844, YES), nil))
                                           console:@"gba"];
  CHECK(report.status == LibretroSkinCompatibilityCompatible && report.deadItems == 0,
        @"an item naming no input is decoration, not a dead button");

  NSArray *noShoulders = [GBAItems(1) subarrayWithRange:NSMakeRange(0, 3)];
  report = [LibretroSkinCompatibility evaluateSkin:Skin(@"no-shoulders", kGBA, Phone(Representation(noShoulders, 390, 844, YES), nil))
                                           console:@"gba"];
  CHECK(report.status == LibretroSkinCompatibilityIncompatible &&
            [report.reasons containsObject:LibretroSkinCompatMissingControls] &&
            [report.missingControls isEqualToArray:(@[ @"l", @"r", @"start" ])],
        @"essential controls missing: incompatible, the missing ones are named (%@)", report.missingControls);

  report = [LibretroSkinCompatibility evaluateSkin:Skin(@"screen-only", kGBA, Phone(Representation(@[], 390, 844, YES), nil))
                                           console:@"gba"];
  CHECK(report.status == LibretroSkinCompatibilityIncompatible &&
            [report.reasons isEqualToArray:@[ LibretroSkinCompatNoTouchControls ]],
        @"a screen-only skin (for controllers) is not offered as a touch skin");

  report = [LibretroSkinCompatibility evaluateSkin:Skin(@"no-art", kGBA, Phone(Representation(GBAItems(1), 390, 844, NO), nil))
                                           console:@"gba"];
  CHECK(report.status == LibretroSkinCompatibilityIncompatible &&
            [report.reasons containsObject:LibretroSkinCompatNoArtwork],
        @"a skin without any image is not offered");

  report = [LibretroSkinCompatibility evaluateSkin:complete console:@"snes"];
  CHECK(report.status == LibretroSkinCompatibilityIncompatible &&
            [report.reasons.firstObject isEqualToString:LibretroSkinCompatOtherConsole],
        @"a GBA skin is not a SNES skin");

  NSArray *tiny = GBAItems(0.2);
  report = [LibretroSkinCompatibility evaluateSkin:Skin(@"tiny", kGBA, Phone(Representation(tiny, 390, 844, YES), nil))
                                           console:@"gba"];
  CHECK(report.status == LibretroSkinCompatibilityCompatible &&
            [report.reasons isEqualToArray:@[ LibretroSkinCompatSmallControls ]] && report.smallestControlPoints < 24,
        @"tiny iPhone controls are reported, the creator's layout is kept (%.1f pt)", report.smallestControlPoints);

  LibretroSkin *builtIn = [LibretroDefaultSkins skinForConsole:@"nds"];
  report = [LibretroSkinCompatibility evaluateSkin:builtIn console:@"nds"];
  CHECK(report.status == LibretroSkinCompatibilityCompatible, @"NeoStation's default skin is compatible");
}

static void TestTabletLayouts(void) {
  // iPad-only layout, 768 x 1024 points, buttons sized for an iPad.
  NSArray *large = @[
    DPad(40, 650, 260), Button(@[ @"a" ], 600, 680, 130), Button(@[ @"b" ], 450, 760, 130), Button(@[ @"l" ], 0, 560, 160),
    Button(@[ @"r" ], 600, 560, 160), Button(@[ @"start" ], 400, 920, 90), Button(@[ @"select" ], 280, 920, 90)
  ];
  NSDictionary *ipad = @{@"ipad" : @{@"standard" : @{@"portrait" : Representation(large, 768, 1024, YES)}}};
  LibretroSkin *skin = Skin(@"ipad-large", kGBA, ipad);
  CHECK([skin representationForOrientation:LibretroSkinOrientationPortrait iPad:NO edgeToEdge:YES] == nil,
        @"before evaluation an iPhone never uses the iPad layout");
  LibretroSkinCompatibilityReport *report = [LibretroSkinCompatibility prepareSkin:skin console:@"gba"];
  CHECK(report.status == LibretroSkinCompatibilityAdaptable && report.tabletLayout &&
            [report.reasons containsObject:LibretroSkinCompatTabletAdapted] &&
            report.smallestControlPoints >= LibretroSkinTabletMinimumControlPoints,
        @"an iPad layout whose controls stay large on an iPhone is adapted (%.1f pt)", report.smallestControlPoints);
  CHECK(skin.phoneUsesTabletLayouts &&
            [[skin representationForOrientation:LibretroSkinOrientationPortrait iPad:NO edgeToEdge:YES].device
                isEqualToString:@"ipad"] &&
            [[skin orientationsForIPad:NO] isEqualToArray:@[ @"portrait" ]],
        @"after preparation the iPhone uses that iPad layout");

  NSArray *small = @[
    DPad(40, 650, 90), Button(@[ @"a" ], 600, 680, 50), Button(@[ @"b" ], 450, 760, 50), Button(@[ @"l" ], 0, 560, 50),
    Button(@[ @"r" ], 600, 560, 50), Button(@[ @"start" ], 400, 920, 40), Button(@[ @"select" ], 280, 920, 40)
  ];
  LibretroSkin *smallSkin =
      Skin(@"ipad-small", kGBA, @{@"ipad" : @{@"standard" : @{@"portrait" : Representation(small, 768, 1024, YES)}}});
  report = [LibretroSkinCompatibility prepareSkin:smallSkin console:@"gba"];
  CHECK(report.status == LibretroSkinCompatibilityIncompatible &&
            [report.reasons containsObject:LibretroSkinCompatTabletTooSmall] && !smallSkin.phoneUsesTabletLayouts &&
            [smallSkin representationForOrientation:LibretroSkinOrientationPortrait iPad:NO edgeToEdge:YES] == nil,
        @"an iPad layout too small on an iPhone is refused (%.1f pt)", report.smallestControlPoints);
}

static void TestConsoleRules(void) {
  // DS without a touch screen.
  NSArray *ds = @[
    DPad(20, 600, 120), Button(@[ @"a" ], 320, 620, 50), Button(@[ @"b" ], 270, 670, 50), Button(@[ @"x" ], 270, 570, 50),
    Button(@[ @"y" ], 220, 620, 50), Button(@[ @"l" ], 0, 540, 60), Button(@[ @"r" ], 320, 540, 60),
    Button(@[ @"start" ], 200, 780, 40), Button(@[ @"select" ], 140, 780, 40)
  ];
  NSDictionary *dsRepresentation = @{
    @"items" : ds,
    @"screens" : @[ @{@"inputFrame" : Frame(0, 0, 256, 192), @"outputFrame" : Frame(0, 40, 390, 292)} ],
    @"mappingSize" : @{@"width" : @390, @"height" : @844},
    @"assets" : @{@"resizable" : @"skin.pdf"},
  };
  LibretroSkin *dsSkin = Skin(@"ds-no-touch", @"com.rileytestut.delta.game.ds", Phone(dsRepresentation, nil));
  LibretroSkinCompatibilityReport *report = [LibretroSkinCompatibility evaluateSkin:dsSkin console:@"nds"];
  CHECK(report.status == LibretroSkinCompatibilityIncompatible &&
            [report.missingControls isEqualToArray:@[ @"touchScreen" ]],
        @"a DS skin without touch screen is not playable (%@)", report.missingControls);
  NSMutableArray *withTouch = [ds mutableCopy];
  [withTouch addObject:@{@"inputs" : @{@"x" : @"touchScreenX", @"y" : @"touchScreenY"}, @"frame" : Frame(0, 340, 390, 200)}];
  NSMutableDictionary *touchRepresentation = [dsRepresentation mutableCopy];
  touchRepresentation[@"items"] = withTouch;
  report = [LibretroSkinCompatibility evaluateSkin:Skin(@"ds-touch", @"com.rileytestut.delta.game.ds", Phone(touchRepresentation, nil))
                                           console:@"nds"];
  CHECK(report.status == LibretroSkinCompatibilityCompatible, @"with a touch screen item it is (%@)", report.dictionary);

  // N64: the analog stick satisfies the directions.
  NSArray *n64 = @[
    @{@"inputs" : @{@"up" : @"analogStickUp", @"down" : @"analogStickDown", @"left" : @"analogStickLeft",
                    @"right" : @"analogStickRight"},
      @"thumbstick" : @{@"name" : @"skin.pdf", @"width" : @50, @"height" : @50},
      @"frame" : Frame(20, 600, 140, 140)},
    Button(@[ @"a" ], 300, 650, 60), Button(@[ @"b" ], 240, 700, 60), Button(@[ @"z" ], 0, 520, 60),
    Button(@[ @"start" ], 180, 780, 40)
  ];
  report = [LibretroSkinCompatibility evaluateSkin:Skin(@"n64-stick", @"com.rileytestut.delta.game.n64",
                                                        Phone(Representation(n64, 390, 844, YES), nil))
                                           console:@"n64"];
  CHECK(report.status == LibretroSkinCompatibilityCompatible &&
            [report.missingOptionalControls containsObject:@"cUp"],
        @"an N64 skin with a stick and no D-pad is playable; missing C buttons are a remark (%@)", report.dictionary);
  CHECK([[LibretroSkinCompatibility essentialControlsForConsole:@"arcade"] containsObject:@"select"] &&
            [[LibretroSkinCompatibility essentialControlsForConsole:@"3ds"] containsObject:@"touchScreen"],
        @"arcade needs its coin button, 3DS its touch screen");
}

int main(int argc, const char *argv[]) {
  @autoreleasepool {
    workDirectory = argc > 1 ? @(argv[1]) : NSTemporaryDirectory();
    TestVerdicts();
    TestTabletLayouts();
    TestConsoleRules();
  }
  if (failures > 0) {
    printf("%d skin compatibility check(s) failed\n", failures);
    return 1;
  }
  printf("All skin compatibility checks passed\n");
  return 0;
}
