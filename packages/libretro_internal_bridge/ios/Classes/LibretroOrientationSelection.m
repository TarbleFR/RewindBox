#import "LibretroOrientationSelection.h"

#import "LibretroOrientationPolicy.h"

LibretroSkin *LibretroChosenSkin(LibretroFrontendStore *store, NSString *console, NSString *game,
                                 LibretroSkinOrientation orientation,
                                 LibretroSkin *(^load)(NSString *identifier)) {
  NSString *key =
      orientation == LibretroSkinOrientationPortrait ? LibretroSettingSkinPortrait : LibretroSettingSkinLandscape;
  id value = [store valueForKey:key console:console game:game.length > 0 ? game : nil scope:NULL];
  if (![value isKindOfClass:NSString.class] || [(NSString *)value length] == 0) return nil;
  if ([value isEqualToString:LibretroDefaultSkinIdentifier] || !LibretroSkinIdentifierIsValid(value)) return nil;
  return load(value);
}

NSUInteger LibretroSelectedOrientationMask(LibretroFrontendStore *store, NSString *console, NSString *game,
                                           LibretroSkin *(^load)(NSString *identifier),
                                           BOOL (^usable)(LibretroSkin *skin, LibretroSkinOrientation orientation)) {
  LibretroSkin *portrait = LibretroChosenSkin(store, console, game, LibretroSkinOrientationPortrait, load);
  LibretroSkin *landscape = LibretroChosenSkin(store, console, game, LibretroSkinOrientationLandscape, load);
  BOOL portraitChosen = portrait != nil && usable(portrait, LibretroSkinOrientationPortrait);
  BOOL landscapeChosen = landscape != nil && usable(landscape, LibretroSkinOrientationLandscape);
  return LibretroPolicyMask(portraitChosen, landscapeChosen);
}

BOOL LibretroSkinGivesLayout(LibretroSkin *skin, LibretroSkinCompatibilityReport *report,
                             LibretroSkinOrientation orientation, BOOL iPad, BOOL touchNeeded) {
  if (skin == nil) return NO;
  NSString *name = LibretroSkinOrientationName(orientation);
  if (![[skin orientationsForIPad:iPad] containsObject:name]) return NO;
  if (iPad) return YES;
  return !([report.orientations[name] isEqualToString:@"incompatible"] && touchNeeded);
}
