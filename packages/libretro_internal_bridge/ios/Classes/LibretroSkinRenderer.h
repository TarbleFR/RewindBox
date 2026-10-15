#import <UIKit/UIKit.h>

#import "LibretroSkin.h"
#import "LibretroSkinLayout.h"

NS_ASSUME_NONNULL_BEGIN

/// Draws a skin representation above the game picture: the background image
/// and the items, either their own images (imported skins) or NeoStation's
/// vector style (default skins). One CALayer per item (CAShapeLayer /
/// CATextLayer for vector items); immediate press changes run inside
/// [CATransaction setDisableActions:YES]. Never receives touches
/// (userInteractionEnabled = NO); LibretroTouchOverlay sits above it.
///
/// Images (PNG / JPEG decoded with ImageIO downsampling, PDF page 1
/// rasterised with CoreGraphics, one CGPDFDocument per render) are produced
/// on a private serial background queue at the on-screen pixel size, kept in
/// an NSCache with a cost limit and on disk under
/// <cacheDirectory>/SkinCache (key: skin directory, file, pixel size,
/// scale); the previous image stays visible until the new one is ready.
/// Public methods: main thread only.
@interface LibretroSkinRenderer : UIView

- (instancetype)initWithCacheDirectory:(NSString *)cacheDirectory;

/// Decode/geometry validation off the main thread before activation/import.
/// Missing, damaged or unreasonably large resources are refused as a whole.
+ (void)validateResourcesForSkin:(LibretroSkin *)skin completion:(void (^)(BOOL valid))completion;
/// Main-thread notification if an on-screen resource still fails after validation.
@property(nonatomic, copy, nullable) void (^resourceLoadFailed)(void);

/// Light / Normal / Pronounced (default) / Very pronounced, 0...3.
/// Changing the setting rebuilds only prepared visual resources.
@property(nonatomic, assign) NSUInteger pressureIntensity;

/// Replaces the drawn representation. `opacity` applies to the controls of
/// translucent and default skins (background images of opaque skins stay
/// fully opaque). `controlsHidden` hides items but keeps the background and
/// the touch-screen area (physical controller connected).
- (void)showRepresentation:(nullable LibretroSkinRepresentation *)representation
                    layout:(nullable LibretroSkinLayoutResult *)layout
                   opacity:(CGFloat)opacity
            controlsHidden:(BOOL)controlsHidden;

/// Immediately depresses the artwork of delivered controls, then animates
/// its return on release. No image decoding occurs on this path.
- (void)setPressedItems:(NSSet<NSString *> *)itemIdentifiers;
/// Effective D-pad directions, supplied by the same touch/input resolution.
- (void)setDPadDirections:(NSDictionary<NSString *, NSNumber *> *)directions;

/// Moves each thumbstick knob with its finger: {itemId: NSValue of a
/// CGPoint, x and y in -1...1, y positive downward}, as reported by
/// LibretroTouchOverlay.stickVectorsChanged; absent items are centred.
/// The knob travels by the vector times half the room left between it and
/// the stick (+[LibretroSkinLayout knobFrameForItem:stickX:stickY:]),
/// without animation. Ignored while editing.
- (void)setStickVectors:(NSDictionary<NSString *, NSValue *> *)vectors;

/// Editing mode of "Commandes › Déplacer et redimensionner": dashed
/// outlines around movable items and a highlight on `selectedItem`. During
/// a pinch the item layer is only scaled; it is re-rasterised at the end.
- (void)setEditing:(BOOL)editing selectedItem:(nullable NSString *)itemIdentifier;

/// Removes cached images of one skin directory (deleted or replaced skin).
+ (void)purgeCacheForSkinDirectory:(NSString *)directory cacheDirectory:(NSString *)cacheDirectory;

/// Preview for the skin pickers (in-game menu and Flutter): background,
/// items and grey placeholders for the screens, rendered off the main
/// thread into an image of `size` points at `scale`. `completion` runs on
/// the main queue (nil image on failure).
+ (void)renderPreviewForRepresentation:(LibretroSkinRepresentation *)representation
                                  size:(CGSize)size
                                 scale:(CGFloat)scale
                            safeInsets:(UIEdgeInsets)safeInsets
                        cacheDirectory:(NSString *)cacheDirectory
                            completion:(void (^)(UIImage *_Nullable image))completion;

@end

NS_ASSUME_NONNULL_END
