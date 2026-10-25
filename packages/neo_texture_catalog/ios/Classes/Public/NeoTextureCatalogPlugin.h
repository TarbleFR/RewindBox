// SPDX-License-Identifier: GPL-3.0-or-later
#import <Flutter/Flutter.h>

NS_ASSUME_NONNULL_BEGIN

/// Flutter channel "neostation/texture_catalog": opens the shared HD
/// textures page (NeoTextureHDPage) over the app for a console or a game of
/// the library, and reads the catalogue state. The page itself does every
/// download, installation and setting change.
@interface NeoTextureCatalogPlugin : NSObject <FlutterPlugin>
@end

NS_ASSUME_NONNULL_END
