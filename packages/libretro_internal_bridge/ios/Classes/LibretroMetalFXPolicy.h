// Sizes the presenter gives MetalFX spatial upscaling (LibretroMetalPresenter).
// Plain C on Foundation types, no Metal: the rule can run in the portable
// frontend tests like LibretroRenderSurface.h.
//
// Each game screen (one, or two for DS / 3DS) has its own scaler: the screen's
// part of the core frame (content, in texels) is enlarged towards its place on
// the drawable, along the picture's own axes. MetalFX only enlarges: a place
// smaller than the content on an axis keeps the standard picture.
#pragma once
#import <Foundation/Foundation.h>

#include <math.h>

/// Largest enlargement asked of the spatial scaler on each axis. Apple
/// documents no limit; beyond it the final composition finishes with linear
/// filtering. To be tuned on an iPhone.
#define LIBRETRO_METALFX_MAX_FACTOR 3.0
/// Below this enlargement on both axes the scaler adds nothing worth its cost:
/// the screen keeps the standard picture (an internal resolution already at or
/// above the screen's size, DeSmuME at ×10).
#define LIBRETRO_METALFX_MIN_FACTOR 1.05
/// Input textures grow in steps of this many pixels, so a core changing its
/// frame size within a step (a PlayStation game going from 320 to 368 pixels
/// wide) keeps its scaler.
#define LIBRETRO_METALFX_INPUT_STEP 64
/// Largest 2D texture side of the Apple GPUs RewindBox runs on.
#define LIBRETRO_METALFX_MAX_SIDE 16384

typedef struct {
  NSUInteger width;
  NSUInteger height;
} LibretroMetalFXSize;

static inline LibretroMetalFXSize LibretroMetalFXSizeMake(NSUInteger width, NSUInteger height) {
  LibretroMetalFXSize size;
  size.width = width;
  size.height = height;
  return size;
}

static inline BOOL LibretroMetalFXSizeEqual(LibretroMetalFXSize left, LibretroMetalFXSize right) {
  return left.width == right.width && left.height == right.height;
}

static inline BOOL LibretroMetalFXSizeIsEmpty(LibretroMetalFXSize size) {
  return size.width == 0 || size.height == 0;
}

/// Output of the scaler for a screen whose content is `content` texels and whose
/// place on the drawable is `placeWidth` x `placeHeight` pixels along the
/// picture's axes: the place, capped at LIBRETRO_METALFX_MAX_FACTOR x the content
/// on each axis. {0, 0} when MetalFX does not apply: no content, a place that is
/// not finite, under one pixel, smaller than the content on an axis, enlarged
/// less than LIBRETRO_METALFX_MIN_FACTOR on both axes, or wider or taller than
/// LIBRETRO_METALFX_MAX_SIDE once capped.
static inline LibretroMetalFXSize LibretroMetalFXOutputSize(LibretroMetalFXSize content, double placeWidth,
                                                            double placeHeight) {
  const LibretroMetalFXSize none = LibretroMetalFXSizeMake(0, 0);
  if (LibretroMetalFXSizeIsEmpty(content) || !isfinite(placeWidth) || !isfinite(placeHeight)) return none;
  const double width = round(placeWidth);
  const double height = round(placeHeight);
  if (width < 1.0 || height < 1.0) return none;
  if (width < (double)content.width || height < (double)content.height) return none;
  if (width < (double)content.width * LIBRETRO_METALFX_MIN_FACTOR &&
      height < (double)content.height * LIBRETRO_METALFX_MIN_FACTOR) {
    return none;
  }
  const double cappedWidth = fmin(width, floor((double)content.width * LIBRETRO_METALFX_MAX_FACTOR));
  const double cappedHeight = fmin(height, floor((double)content.height * LIBRETRO_METALFX_MAX_FACTOR));
  if (cappedWidth > LIBRETRO_METALFX_MAX_SIDE || cappedHeight > LIBRETRO_METALFX_MAX_SIDE) return none;
  return LibretroMetalFXSizeMake((NSUInteger)cappedWidth, (NSUInteger)cappedHeight);
}

static inline NSUInteger LibretroMetalFXRoundUp(NSUInteger value, NSUInteger limit) {
  const NSUInteger step = LIBRETRO_METALFX_INPUT_STEP;
  NSUInteger rounded = value % step == 0 ? value : value + (step - value % step);
  if (rounded > limit) rounded = limit;
  return rounded < value ? value : rounded;
}

/// Size of the input texture (and of the scaler's input) for `content`, given the
/// allocation in use (`current`, {0, 0} for none) and the scaler's `output`:
/// - the current allocation while it holds the content, is at most twice the
///   content on each axis and fits within the output (no new scaler);
/// - else the content rounded up to LIBRETRO_METALFX_INPUT_STEP, never beyond
///   the output (the scaler only enlarges) nor under the content.
/// {0, 0} when the content or the output is empty or the output is smaller
/// than the content.
static inline LibretroMetalFXSize LibretroMetalFXInputAllocation(LibretroMetalFXSize content,
                                                                 LibretroMetalFXSize current,
                                                                 LibretroMetalFXSize output) {
  const LibretroMetalFXSize none = LibretroMetalFXSizeMake(0, 0);
  if (LibretroMetalFXSizeIsEmpty(content) || LibretroMetalFXSizeIsEmpty(output)) return none;
  if (output.width < content.width || output.height < content.height) return none;
  if (current.width >= content.width && current.height >= content.height &&
      current.width <= content.width * 2 && current.height <= content.height * 2 &&
      current.width <= output.width && current.height <= output.height) {
    return current;
  }
  return LibretroMetalFXSizeMake(LibretroMetalFXRoundUp(content.width, output.width),
                                 LibretroMetalFXRoundUp(content.height, output.height));
}
