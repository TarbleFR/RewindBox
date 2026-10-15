#import <Foundation/Foundation.h>
#import <CoreGraphics/CoreGraphics.h>

NS_ASSUME_NONNULL_BEGIN

/// Pixel-aligned, disjoint outer thirds. Slots are up, down, left, right,
/// matching the touch tracker's direction bits. The central third is fixed.
FOUNDATION_EXPORT CGRect LibretroSkinPressureArm(CGSize size, NSUInteger slot);

/// Prepares eight premultiplied RGBA images, rest first, fully pressed last.
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

NS_ASSUME_NONNULL_END
