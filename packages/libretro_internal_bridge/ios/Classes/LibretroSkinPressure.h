#import <Foundation/Foundation.h>
#import <CoreGraphics/CoreGraphics.h>

NS_ASSUME_NONNULL_BEGIN

FOUNDATION_EXPORT const NSUInteger LibretroSkinPressureFrameCount;

/// Shared mechanical profile in display points. Unknown preferences use
/// Pronounced (2). Geometry and resource preparation never change hit areas.
typedef struct {
  CGFloat depth, compression, occlusion, releaseDuration;
} LibretroSkinPressureProfile;
FOUNDATION_EXPORT NSArray<NSString *> *LibretroSkinPressureIntensityIdentifiers(void);
FOUNDATION_EXPORT NSUInteger LibretroSkinPressureIntensityFromIdentifier(id _Nullable value);
FOUNDATION_EXPORT LibretroSkinPressureProfile LibretroSkinPressureProfileForSize(CGSize points, NSUInteger intensity);
FOUNDATION_EXPORT double LibretroSkinPressureReleaseTime(double progress);

/// Detect a well-defined alpha cross, including transparent padding and
/// unequal/off-centre stems, or exactly four separated cardinal arrows in
/// one texture. Otherwise retain the conservative outer thirds.
/// Four integral source-image rectangles, ordered up/down/left/right.
FOUNDATION_EXPORT NSArray<NSValue *> *LibretroSkinPressureRegions(CGImageRef source, CGRect pixels);

/// Subtract ambiguous shared areas without duplicating or inferring pixels.
/// Inputs use one coordinate plane; rectangles remain disjoint. Excessively
/// fragmented or invalid geometry returns no visible regions.
FOUNDATION_EXPORT NSArray<NSValue *> *LibretroSkinPressureVisibleRects(CGRect rect, NSArray<NSValue *> *excluded);
FOUNDATION_EXPORT CGRect LibretroSkinPressureRect(NSValue *value);

/// Pixel-aligned, disjoint outer thirds. Slots are up, down, left, right,
/// matching the touch tracker's direction bits. The central third is fixed.
FOUNDATION_EXPORT CGRect LibretroSkinPressureArm(CGSize size, NSUInteger slot);

/// Prepares twelve premultiplied RGBA images, rest first, fully pressed last.
/// The deformation is zero with zero slope at every boundary. It samples
/// only this region: no guessed background, duplicate face, or changed alpha
/// outside the region. Authored Delta images instead interpolate their local
/// pixels. Call only on the image preparation queue, never from touch events.
/// `pixels` must be integral and inside source. `pointsPerPixel` sets depth
/// independently of the image's resolution; direction is 0 for a button,
/// 1/2/4/8 for a D-pad arm. Invalid/oversized inputs return an empty array.
/// Each image includes one unchanged pixel of sampling apron on every side;
/// display its inner `pixels.size` using contentsRect, not the whole image.
FOUNDATION_EXPORT NSArray *LibretroSkinPressureFrames(CGImageRef source,
    CGRect pixels, CGFloat pointsPerPixel, NSUInteger direction,
    CGImageRef _Nullable authoredPressed);

/// Same preparation, with smooth pinning around excluded source rectangles.
/// The caller must also exclude those rectangles from the layer/background
/// masks. Shared pixels retain the original background, even with two fingers.
FOUNDATION_EXPORT NSArray *LibretroSkinPressureFramesExcluding(CGImageRef source,
    CGRect pixels, CGFloat pointsPerPixel, NSUInteger direction,
    CGImageRef _Nullable authoredPressed, NSArray<NSValue *> *excluded, NSUInteger frameCount);

/// Same bounded preparation with the selected profile. Level zero preserves
/// the original gentle effect, including an author's exact pressed endpoint.
FOUNDATION_EXPORT NSArray *LibretroSkinPressureFramesWithIntensity(CGImageRef source,
    CGRect pixels, CGFloat pointsPerPixel, NSUInteger direction,
    CGImageRef _Nullable authoredPressed, NSArray<NSValue *> *excluded,
    NSUInteger frameCount, NSUInteger intensity);

NS_ASSUME_NONNULL_END
