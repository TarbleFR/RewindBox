// The orientations a game allows, from the skins the player CHOSE for it.
// Portable (Foundation only): the session supplies how a skin is loaded and
// whether a layout is usable, the tests supply real store files and skins.
#import <Foundation/Foundation.h>

#import "LibretroFrontendStore.h"
#import "LibretroSkin.h"
#import "LibretroSkinCompatibility.h"

NS_ASSUME_NONNULL_BEGIN

/// The skin the player chose for `orientation`: `skin.portrait` /
/// `skin.landscape` resolved game first, then console (the store's own
/// inheritance; nothing is written or erased). nil for the default controls,
/// an invalid identifier, or a skin `load` cannot give.
FOUNDATION_EXPORT LibretroSkin *_Nullable LibretroChosenSkin(
    LibretroFrontendStore *store, NSString *console, NSString *_Nullable game, LibretroSkinOrientation orientation,
    LibretroSkin *_Nullable (^load)(NSString *identifier));

/// Does `skin` give a layout in `orientation` on this device? The layout must
/// exist for the device class and, on an iPhone, must not be judged
/// incompatible by `report` while touch is the only way to play
/// (`touchNeeded`: touch controls on and no physical controller). The same
/// test as the layout pass (skinPlayable), without its announcement.
FOUNDATION_EXPORT BOOL LibretroSkinGivesLayout(LibretroSkin *skin, LibretroSkinCompatibilityReport *_Nullable report,
                                               LibretroSkinOrientation orientation, BOOL iPad, BOOL touchNeeded);

/// Mask (LibretroPolicyMask values, equal to the UIInterfaceOrientationMask
/// bits) of the game: an orientation counts as chosen when a skin is chosen
/// for it AND `usable` says that skin gives a layout there. Only portrait
/// chosen: portrait; only landscape: landscape; both or none: both.
FOUNDATION_EXPORT NSUInteger LibretroSelectedOrientationMask(
    LibretroFrontendStore *store, NSString *console, NSString *_Nullable game,
    LibretroSkin *_Nullable (^load)(NSString *identifier),
    BOOL (^usable)(LibretroSkin *skin, LibretroSkinOrientation orientation));

NS_ASSUME_NONNULL_END
