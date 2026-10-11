#import "LibretroSkinCompatibility.h"

#import "LibretroInputMap.h"
#import "LibretroSkinLayout.h"

#include <math.h>

NSString *const LibretroSkinCompatOtherConsole = @"SKIN_COMPAT_OTHER_CONSOLE";
NSString *const LibretroSkinCompatNoPhoneLayout = @"SKIN_COMPAT_NO_PHONE_LAYOUT";
NSString *const LibretroSkinCompatTabletAdapted = @"SKIN_COMPAT_TABLET_ADAPTED";
NSString *const LibretroSkinCompatTabletTooSmall = @"SKIN_COMPAT_TABLET_TOO_SMALL";
NSString *const LibretroSkinCompatNoTouchControls = @"SKIN_COMPAT_NO_TOUCH_CONTROLS";
NSString *const LibretroSkinCompatMissingControls = @"SKIN_COMPAT_MISSING_CONTROLS";
NSString *const LibretroSkinCompatAdaptedInputs = @"SKIN_COMPAT_ADAPTED_INPUTS";
NSString *const LibretroSkinCompatDeadButtons = @"SKIN_COMPAT_DEAD_BUTTONS";
NSString *const LibretroSkinCompatNoArtwork = @"SKIN_COMPAT_NO_ARTWORK";
NSString *const LibretroSkinCompatSmallControls = @"SKIN_COMPAT_SMALL_CONTROLS";

const double LibretroSkinTabletMinimumControlPoints = 36;
const double LibretroSkinSmallControlPoints = 24;

static NSString *const kDirections = @"directions";

NSString *LibretroSkinCompatibilityStatusName(LibretroSkinCompatibilityStatus status) {
  switch (status) {
    case LibretroSkinCompatibilityCompatible:
      return @"compatible";
    case LibretroSkinCompatibilityAdaptable:
      return @"adaptable";
    case LibretroSkinCompatibilityIncompatible:
      return @"incompatible";
  }
  return @"incompatible";
}

/// Reason codes from the most to the least important.
static NSArray<NSString *> *ReasonOrder(void) {
  return @[
    LibretroSkinCompatOtherConsole, LibretroSkinCompatNoPhoneLayout, LibretroSkinCompatTabletTooSmall,
    LibretroSkinCompatNoArtwork, LibretroSkinCompatNoTouchControls, LibretroSkinCompatMissingControls,
    LibretroSkinCompatTabletAdapted, LibretroSkinCompatAdaptedInputs, LibretroSkinCompatDeadButtons,
    LibretroSkinCompatSmallControls
  ];
}

@interface LibretroSkinCompatibilityReport ()
@property(nonatomic, readwrite) LibretroSkinCompatibilityStatus status;
@property(nonatomic, readwrite, copy) NSString *console;
@property(nonatomic, readwrite, copy) NSDictionary<NSString *, NSString *> *orientations;
@property(nonatomic, readwrite, copy) NSArray<NSString *> *reasons;
@property(nonatomic, readwrite, copy) NSArray<NSString *> *missingControls;
@property(nonatomic, readwrite, copy) NSArray<NSString *> *missingOptionalControls;
@property(nonatomic, readwrite, copy) NSArray<NSString *> *adaptedInputs;
@property(nonatomic, readwrite, copy) NSArray<NSString *> *unsupportedInputs;
@property(nonatomic, readwrite) NSUInteger deadItems;
@property(nonatomic, readwrite) BOOL tabletLayout;
@property(nonatomic, readwrite) double smallestControlPoints;
@end

@implementation LibretroSkinCompatibilityReport

- (LibretroSkinCompatibilityStatus)statusForOrientation:(LibretroSkinOrientation)orientation {
  NSString *name = self.orientations[LibretroSkinOrientationName(orientation)];
  if ([name isEqualToString:@"compatible"]) return LibretroSkinCompatibilityCompatible;
  if ([name isEqualToString:@"adaptable"]) return LibretroSkinCompatibilityAdaptable;
  return LibretroSkinCompatibilityIncompatible;
}

- (NSDictionary<NSString *, id> *)dictionary {
  return @{
    @"status" : LibretroSkinCompatibilityStatusName(self.status),
    @"console" : self.console ?: @"",
    @"orientations" : self.orientations ?: @{},
    @"reasons" : self.reasons ?: @[],
    @"missingControls" : self.missingControls ?: @[],
    @"missingOptionalControls" : self.missingOptionalControls ?: @[],
    @"adaptedInputs" : self.adaptedInputs ?: @[],
    @"unsupportedInputs" : self.unsupportedInputs ?: @[],
    @"deadItems" : @(self.deadItems),
    @"tabletLayout" : @(self.tabletLayout),
    @"smallestControlPoints" : @(round(self.smallestControlPoints * 10) / 10),
  };
}

@end

/// Verdict of one orientation.
@interface LibretroSkinOrientationVerdict : NSObject
@property(nonatomic, assign) LibretroSkinCompatibilityStatus status;
@property(nonatomic, strong) NSMutableOrderedSet<NSString *> *reasons;
@property(nonatomic, strong) NSMutableOrderedSet<NSString *> *missing;
@property(nonatomic, strong) NSMutableOrderedSet<NSString *> *missingOptional;
@property(nonatomic, strong) NSMutableOrderedSet<NSString *> *adapted;
@property(nonatomic, strong) NSMutableOrderedSet<NSString *> *unsupported;
@property(nonatomic, assign) NSUInteger deadItems;
@property(nonatomic, assign) double smallest;
@property(nonatomic, assign) BOOL tablet;
@end

@implementation LibretroSkinOrientationVerdict
- (instancetype)init {
  self = [super init];
  if (self) {
    _reasons = [NSMutableOrderedSet orderedSet];
    _missing = [NSMutableOrderedSet orderedSet];
    _missingOptional = [NSMutableOrderedSet orderedSet];
    _adapted = [NSMutableOrderedSet orderedSet];
    _unsupported = [NSMutableOrderedSet orderedSet];
  }
  return self;
}
@end

@implementation LibretroSkinCompatibility

+ (NSArray<NSString *> *)essentialControlsForConsole:(NSString *)console {
  static NSDictionary<NSString *, NSArray<NSString *> *> *table;
  static dispatch_once_t once;
  dispatch_once(&once, ^{
    NSArray<NSString *> *twoButtons = @[ kDirections, @"a", @"b", @"start" ];
    NSArray<NSString *> *snes = @[ kDirections, @"a", @"b", @"x", @"y", @"l", @"r", @"start" ];
    NSArray<NSString *> *genesis = @[ kDirections, @"a", @"b", @"c", @"start" ];
    table = @{
      @"nes" : twoButtons,
      @"gb" : twoButtons,
      @"gbc" : twoButtons,
      @"sms" : twoButtons,
      @"gg" : twoButtons,
      @"sg1000" : twoButtons,
      @"gba" : @[ kDirections, @"a", @"b", @"l", @"r", @"start" ],
      @"snes" : snes,
      @"md" : genesis,
      @"mcd" : genesis,
      @"32x" : genesis,
      @"arcade" : @[ kDirections, @"a", @"b", @"start", @"select" ],
      @"nds" : [snes arrayByAddingObject:@"touchScreen"],
      @"n64" : @[ kDirections, @"a", @"b", @"z", @"start" ],
      @"psx" : snes,
      @"psp" : snes,
      @"3ds" : [snes arrayByAddingObject:@"touchScreen"],
    };
  });
  return table[console] ?: @[ kDirections ];
}

+ (NSArray<NSString *> *)optionalControlsForConsole:(NSString *)console {
  static NSDictionary<NSString *, NSArray<NSString *> *> *table;
  static dispatch_once_t once;
  dispatch_once(&once, ^{
    NSArray<NSString *> *select = @[ @"select" ];
    NSArray<NSString *> *genesis = @[ @"x", @"y", @"z", @"mode" ];
    table = @{
      @"nes" : select,
      @"gb" : select,
      @"gbc" : select,
      @"gba" : select,
      @"snes" : select,
      @"nds" : select,
      @"md" : genesis,
      @"mcd" : genesis,
      @"32x" : genesis,
      @"n64" : @[ @"l", @"r", @"cUp", @"cDown", @"cLeft", @"cRight" ],
      @"psx" : @[ @"select", @"l2", @"r2" ],
      @"psp" : select,
      @"3ds" : @[ @"select", @"l2", @"r2", @"rightStick" ],
    };
  });
  return table[console] ?: @[];
}

/// Smallest iPhone that shows `representation` (points, portrait first).
+ (NSArray<NSValue *> *)referenceSizesForRepresentation:(LibretroSkinRepresentation *)representation
                                                  tablet:(BOOL)tablet {
  LibretroSize standard = {375, 667}, edgeToEdge = {390, 844};
  NSMutableArray<NSValue *> *sizes = [NSMutableArray array];
  BOOL notched = [representation.displayType isEqualToString:@"edgeToEdge"];
  NSMutableArray<NSValue *> *portraitSizes = [NSMutableArray array];
  if (tablet || !notched) [portraitSizes addObject:[NSValue valueWithBytes:&standard objCType:@encode(LibretroSize)]];
  if (tablet || notched) [portraitSizes addObject:[NSValue valueWithBytes:&edgeToEdge objCType:@encode(LibretroSize)]];
  for (NSValue *value in portraitSizes) {
    LibretroSize size = {0, 0};
    [value getValue:&size];
    if (representation.orientation == LibretroSkinOrientationLandscape) size = (LibretroSize){size.h, size.w};
    [sizes addObject:[NSValue valueWithBytes:&size objCType:@encode(LibretroSize)]];
  }
  return sizes;
}

/// Logical inputs an item really sends for the console (action names
/// included), in its own order.
+ (NSArray<NSString *> *)effectiveInputsOfItem:(LibretroSkinItem *)item map:(LibretroInputMap *)map {
  NSMutableArray<NSString *> *inputs = [NSMutableArray array];
  if (item.kind == LibretroSkinItemKindTouchScreen) return @[ @"touchScreen" ];
  for (NSString *input in item.inputs) {
    if (input.length == 0) continue;
    LibretroInputTarget target = [map targetForInput:input];
    if (target.kind == LibretroInputTargetNone || target.kind == LibretroInputTargetPointer) continue;
    if (![inputs containsObject:input]) [inputs addObject:input];
  }
  return inputs;
}

/// YES when the item names at least one input (a D-pad or stick with four
/// empty directions names none).
+ (BOOL)declaresInputs:(LibretroSkinItem *)item {
  for (NSString *input in item.inputs) {
    if (input.length > 0) return YES;
  }
  return NO;
}

+ (BOOL)hasArtwork:(LibretroSkinRepresentation *)representation {
  if (representation.generated || representation.backgroundPath.length > 0) return YES;
  for (LibretroSkinItem *item in representation.items) {
    if (item.assetPath.length > 0 || item.thumbstickAssetPath.length > 0) return YES;
  }
  return NO;
}

+ (LibretroSkinOrientationVerdict *)evaluateRepresentation:(LibretroSkinRepresentation *)representation
                                                   console:(NSString *)console
                                                    tablet:(BOOL)tablet {
  LibretroSkinOrientationVerdict *verdict = [LibretroSkinOrientationVerdict new];
  verdict.tablet = tablet;
  LibretroInputMap *map = [LibretroInputMap mapForConsole:console];

  // Every input reachable by touch, and the items that give each one.
  NSMutableDictionary<NSString *, NSMutableArray<LibretroSkinItem *> *> *providers = [NSMutableDictionary dictionary];
  NSUInteger controls = 0;
  for (LibretroSkinItem *item in representation.items) {
    [verdict.adapted addObjectsFromArray:item.adaptedInputs ?: @[]];
    [verdict.unsupported addObjectsFromArray:item.unsupportedInputs ?: @[]];
    NSArray<NSString *> *inputs = [self effectiveInputsOfItem:item map:map];
    if (item.kind != LibretroSkinItemKindTouchScreen) {
      if (inputs.count == 0) {
        // Declared inputs this console cannot use: a dead button. An item
        // that declares none is decoration (drawn, never a control).
        if (item.unsupportedInputs.count > 0 || item.adaptedInputs.count > 0 || [self declaresInputs:item]) {
          verdict.deadItems++;
        }
        continue;
      }
      BOOL drivesCore = NO;
      for (NSString *input in inputs) {
        if ([map targetForInput:input].kind != LibretroInputTargetAction) drivesCore = YES;
      }
      if (drivesCore) controls++;
    }
    for (NSString *input in inputs) {
      NSMutableArray<LibretroSkinItem *> *list = providers[input];
      if (list == nil) providers[input] = list = [NSMutableArray array];
      [list addObject:item];
    }
  }
  for (LibretroSkinScreen *screen in representation.screens) {
    if (screen.touchScreen && providers[@"touchScreen"] == nil) providers[@"touchScreen"] = [NSMutableArray array];
  }

  if (![self hasArtwork:representation]) [verdict.reasons addObject:LibretroSkinCompatNoArtwork];
  if (controls == 0) [verdict.reasons addObject:LibretroSkinCompatNoTouchControls];

  // Essential controls, each as the inputs that satisfy it.
  NSArray<NSString *> *pad = @[ @"up", @"down", @"left", @"right" ];
  NSArray<NSString *> *stick = @[ @"leftStickUp", @"leftStickDown", @"leftStickLeft", @"leftStickRight" ];
  NSMutableArray<NSString *> *measured = [NSMutableArray array];
  for (NSString *control in [self essentialControlsForConsole:console]) {
    if ([control isEqualToString:kDirections]) {
      BOOL hasPad = YES, hasStick = map.hasLeftStick;
      for (NSString *name in pad) hasPad = hasPad && providers[name] != nil;
      for (NSString *name in stick) hasStick = hasStick && providers[name] != nil;
      if (hasPad) {
        [measured addObjectsFromArray:pad];
      } else if (hasStick) {
        [measured addObjectsFromArray:stick];
      } else {
        [verdict.missing addObject:kDirections];
      }
    } else if (providers[control] == nil) {
      [verdict.missing addObject:control];
    } else if (![control isEqualToString:@"touchScreen"]) {
      [measured addObject:control];
    }
  }
  for (NSString *control in [self optionalControlsForConsole:console]) {
    if ([control isEqualToString:@"rightStick"]) {
      if (providers[@"rightStickUp"] == nil && providers[@"rightStickRight"] == nil) [verdict.missingOptional addObject:control];
    } else if (providers[control] == nil) {
      [verdict.missingOptional addObject:control];
    }
  }
  if (verdict.missing.count > 0 && controls > 0) [verdict.reasons addObject:LibretroSkinCompatMissingControls];

  // Touch areas of the essential controls on the smallest iPhone showing
  // this layout: for each control its largest item, then the smallest of
  // those.
  double smallest = INFINITY;
  for (NSValue *value in [self referenceSizesForRepresentation:representation tablet:tablet]) {
    LibretroSize size = {0, 0};
    [value getValue:&size];
    LibretroInsets none = {0, 0, 0, 0};
    LibretroSkinLayoutResult *layout = [LibretroSkinLayout layoutRepresentation:representation
                                                                       viewSize:size
                                                                     safeInsets:none
                                                                      overrides:nil];
    NSMutableDictionary<NSString *, LibretroLaidOutItem *> *laidOutByIdentifier = [NSMutableDictionary dictionary];
    for (LibretroLaidOutItem *laidOut in layout.items) {
      if (laidOut.item.identifier.length > 0) laidOutByIdentifier[laidOut.item.identifier] = laidOut;
    }
    for (NSString *control in measured) {
      double largest = 0;
      for (LibretroSkinItem *item in providers[control]) {
        LibretroLaidOutItem *laidOut = laidOutByIdentifier[item.identifier];
        if (laidOut == nil) continue;
        LibretroRect hit = laidOut.hitFrame;
        largest = MAX(largest, MIN(hit.w, hit.h));
      }
      smallest = MIN(smallest, largest);
    }
  }
  verdict.smallest = isfinite(smallest) ? smallest : 0;

  BOOL blocking = [verdict.reasons containsObject:LibretroSkinCompatNoArtwork] ||
                  [verdict.reasons containsObject:LibretroSkinCompatNoTouchControls] ||
                  [verdict.reasons containsObject:LibretroSkinCompatMissingControls];
  if (!blocking && tablet && verdict.smallest < LibretroSkinTabletMinimumControlPoints) {
    [verdict.reasons addObject:LibretroSkinCompatTabletTooSmall];
    blocking = YES;
  }
  if (blocking) {
    verdict.status = LibretroSkinCompatibilityIncompatible;
    return verdict;
  }
  verdict.status = LibretroSkinCompatibilityCompatible;
  if (tablet) {
    [verdict.reasons addObject:LibretroSkinCompatTabletAdapted];
    verdict.status = LibretroSkinCompatibilityAdaptable;
  }
  if (verdict.adapted.count > 0) {
    [verdict.reasons addObject:LibretroSkinCompatAdaptedInputs];
    verdict.status = LibretroSkinCompatibilityAdaptable;
  }
  if (verdict.deadItems > 0) {
    [verdict.reasons addObject:LibretroSkinCompatDeadButtons];
    verdict.status = LibretroSkinCompatibilityAdaptable;
  }
  if (!tablet && verdict.smallest > 0 && verdict.smallest < LibretroSkinSmallControlPoints) {
    [verdict.reasons addObject:LibretroSkinCompatSmallControls];
  }
  return verdict;
}

/// The iPhone layout of an orientation (edge to edge first), else nil.
+ (LibretroSkinRepresentation *)phoneRepresentationOfSkin:(LibretroSkin *)skin
                                              orientation:(LibretroSkinOrientation)orientation
                                                   device:(NSString *)device {
  LibretroSkinRepresentation *found = nil;
  for (LibretroSkinRepresentation *representation in skin.representations) {
    if (representation.orientation != orientation || ![representation.device isEqualToString:device]) continue;
    if (found == nil || [representation.displayType isEqualToString:@"edgeToEdge"]) found = representation;
  }
  return found;
}

+ (LibretroSkinCompatibilityReport *)evaluateSkin:(LibretroSkin *)skin console:(NSString *)console {
  LibretroSkinCompatibilityReport *report = [LibretroSkinCompatibilityReport new];
  report.console = console ?: @"";
  NSMutableOrderedSet<NSString *> *reasons = [NSMutableOrderedSet orderedSet];
  NSMutableOrderedSet<NSString *> *missing = [NSMutableOrderedSet orderedSet];
  NSMutableOrderedSet<NSString *> *missingOptional = [NSMutableOrderedSet orderedSet];
  NSMutableOrderedSet<NSString *> *adapted = [NSMutableOrderedSet orderedSet];
  NSMutableOrderedSet<NSString *> *unsupported = [NSMutableOrderedSet orderedSet];
  NSMutableDictionary<NSString *, NSString *> *orientations = [NSMutableDictionary dictionary];
  NSUInteger deadItems = 0;
  double smallest = INFINITY;
  BOOL tabletLayout = NO;
  LibretroSkinCompatibilityStatus best = LibretroSkinCompatibilityIncompatible;
  BOOL anyLayout = NO;

  BOOL builtIn = [skin.installedIdentifier isEqualToString:LibretroDefaultSkinIdentifier] &&
                 skin.representations.count == 0;
  if (builtIn) {
    // NeoStation's own skin, generated for any view (default_skins_test).
    report.status = LibretroSkinCompatibilityCompatible;
    report.orientations = @{@"portrait" : @"compatible", @"landscape" : @"compatible"};
    report.reasons = @[];
    report.missingControls = @[];
    report.missingOptionalControls = @[];
    report.adaptedInputs = @[];
    report.unsupportedInputs = @[];
    return report;
  }
  if (![skin.consoles containsObject:console]) [reasons addObject:LibretroSkinCompatOtherConsole];

  for (NSNumber *value in @[ @(LibretroSkinOrientationPortrait), @(LibretroSkinOrientationLandscape) ]) {
    LibretroSkinOrientation orientation = (LibretroSkinOrientation)value.integerValue;
    NSString *name = LibretroSkinOrientationName(orientation);
    LibretroSkinRepresentation *representation = [self phoneRepresentationOfSkin:skin
                                                                      orientation:orientation
                                                                           device:@"iphone"];
    BOOL tablet = NO;
    if (representation == nil) {
      representation = [self phoneRepresentationOfSkin:skin orientation:orientation device:@"ipad"];
      tablet = representation != nil;
    }
    if (representation == nil) {
      orientations[name] = @"missing";
      continue;
    }
    anyLayout = YES;
    LibretroSkinOrientationVerdict *verdict = [self evaluateRepresentation:representation console:console tablet:tablet];
    if (reasons.count > 0 && [reasons containsObject:LibretroSkinCompatOtherConsole]) {
      verdict.status = LibretroSkinCompatibilityIncompatible;
    }
    orientations[name] = LibretroSkinCompatibilityStatusName(verdict.status);
    [reasons unionOrderedSet:verdict.reasons];
    [missing unionOrderedSet:verdict.missing];
    [missingOptional unionOrderedSet:verdict.missingOptional];
    [adapted unionOrderedSet:verdict.adapted];
    [unsupported unionOrderedSet:verdict.unsupported];
    deadItems = MAX(deadItems, verdict.deadItems);
    if (verdict.smallest > 0) smallest = MIN(smallest, verdict.smallest);
    if (tablet && verdict.status != LibretroSkinCompatibilityIncompatible) tabletLayout = YES;
    if (verdict.status < best) best = verdict.status;
  }
  if (!anyLayout) [reasons addObject:LibretroSkinCompatNoPhoneLayout];

  NSMutableArray<NSString *> *ordered = [NSMutableArray array];
  for (NSString *code in ReasonOrder()) {
    if ([reasons containsObject:code]) [ordered addObject:code];
  }
  report.status = best;
  report.orientations = orientations;
  report.reasons = ordered;
  report.missingControls = missing.array;
  report.missingOptionalControls = missingOptional.array;
  report.adaptedInputs = adapted.array;
  report.unsupportedInputs = unsupported.array;
  report.deadItems = deadItems;
  report.tabletLayout = tabletLayout;
  report.smallestControlPoints = isfinite(smallest) ? smallest : 0;
  return report;
}

+ (LibretroSkinCompatibilityReport *)prepareSkin:(LibretroSkin *)skin console:(NSString *)console {
  LibretroSkinCompatibilityReport *report = [self evaluateSkin:skin console:console];
  skin.phoneUsesTabletLayouts = report.tabletLayout;
  return report;
}

@end
