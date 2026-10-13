// SPDX-License-Identifier: GPL-3.0-or-later
#import <Foundation/Foundation.h>

#import "NeoShaderEngine.h"

NS_ASSUME_NONNULL_BEGIN

/// Static cost class computed by the catalog generator from known figures
/// of each preset (passes, resolution of each pass relative to the screen,
/// texture reads per pixel of every pass), never from a guess; the menu
/// shows it as an estimate next to the GPU time measured on the device.
typedef NS_ENUM(NSInteger, NeoShaderCostTier) {
  NeoShaderCostTierUnknown = 0,
  NeoShaderCostTierPerformance,
  NeoShaderCostTierBalanced,
  NeoShaderCostTierQuality,
};

/// One file of the official repository, pinned by size and SHA-256.
@interface NeoShaderCatalogFile : NSObject
@property(nonatomic, copy, readonly) NSString *path;
@property(nonatomic, readonly) unsigned long long size;
@property(nonatomic, copy, readonly) NSString *sha256;
@end

@interface NeoShaderCatalogEntry : NSObject
/// Stable identifier: the preset's path in the repository
/// ("crt/crt-royale.slangp"), or "sys/<name>" for a shader bundled with
/// the engine.
@property(nonatomic, copy, readonly) NSString *identifier;
/// The upstream file name without extension (never translated).
@property(nonatomic, copy, readonly) NSString *name;
/// crt, scanlines, lcd, pixel-art, upscaling, sharpen, anti-aliasing,
/// ntsc-pal, color, retro, vhs, other.
@property(nonatomic, copy, readonly) NSString *category;
/// Upstream folder (shown raw).
@property(nonatomic, copy, readonly) NSString *family;
@property(nonatomic, copy, readonly) NeoShaderFormat format;
/// Every file the shader needs (presets, sources, includes, textures).
@property(nonatomic, copy, readonly) NSArray<NeoShaderCatalogFile *> *files;
@property(nonatomic, readonly) unsigned long long downloadBytes;
/// Part of the application (Dolphin's official shaders): nothing to download.
@property(nonatomic, readonly) BOOL bundled;
@property(nonatomic, readonly) NSUInteger passCount;
@property(nonatomic, readonly) NSUInteger textureCount;
@property(nonatomic, readonly) NSUInteger parameterCount;
@property(nonatomic, readonly) NSUInteger historyDepth;
@property(nonatomic, readonly) NSUInteger feedbackCount;
@property(nonatomic, readonly) NSUInteger floatFramebufferCount;
/// Texture reads per screen pixel along the call graph, weighted by the
/// size of each pass (reference: 320x240 picture on a 1572x1179 screen);
/// a lower bound when `samplesInLoop`.
@property(nonatomic, readonly) double samplesPerPixel;
@property(nonatomic, readonly) BOOL samplesInLoop;
@property(nonatomic, readonly) NeoShaderCostTier costTier;
@property(nonatomic, strong, readonly, nullable) NeoShaderCatalogFile *preview;
/// Author / copyright lines found in the sources' header comments, quoted
/// as written (empty when the files name nobody).
@property(nonatomic, copy, readonly) NSArray<NSString *> *authorMentions;
/// Licence named in those comments ("" when none).
@property(nonatomic, copy, readonly) NSString *licenseMention;
/// How far it was verified before being listed: "rendered" (compiled to
/// Metal and rendered on a macOS Apple GPU in CI), "compiled" (Metal
/// compilation only), "translated" (SPIR-V -> MSL only).
@property(nonatomic, copy, readonly) NSString *validation;
/// Dolphin options ([{name, gui, type, values, minimum, maximum, step}]).
@property(nonatomic, copy, readonly) NSArray<NSDictionary<NSString *, id> *> *options;
/// Stable remarks ("hdr-output", "touch-geometry", ...).
@property(nonatomic, copy, readonly) NSArray<NSString *> *notes;
@end

/// A catalog bundled with the application, generated from a pinned commit
/// of an official repository (tools/shaders/build_*_catalog.py). Files are
/// fetched from that exact commit and checked against its SHA-256.
@interface NeoShaderCatalog : NSObject
@property(nonatomic, copy, readonly) NSString *engine;
@property(nonatomic, copy, readonly) NeoShaderFormat format;
@property(nonatomic, copy, readonly) NSString *sourceName;
@property(nonatomic, copy, readonly) NSString *sourceRepository;
@property(nonatomic, copy, readonly) NSString *sourceRevision;
/// https base URL of raw files at sourceRevision ("" for bundled shaders).
@property(nonatomic, copy, readonly) NSString *rawBaseURL;
@property(nonatomic, copy, readonly) NSString *previewSourceName;
@property(nonatomic, copy, readonly) NSString *previewRevision;
@property(nonatomic, copy, readonly) NSString *previewRawBaseURL;
/// The picture previews were made from (upscale-test.png), shown as the
/// "before" image when a preview is exactly `previewScale` times its size.
@property(nonatomic, strong, readonly, nullable) NeoShaderCatalogFile *previewReference;
@property(nonatomic, readonly) NSUInteger previewScale;
@property(nonatomic, copy, readonly) NSString *compilerDescription;
@property(nonatomic, copy, readonly) NSArray<NSString *> *categories;
@property(nonatomic, copy, readonly) NSArray<NeoShaderCatalogEntry *> *entries;

+ (nullable instancetype)catalogWithData:(NSData *)data error:(NSError *_Nullable *_Nullable)error;
- (nullable NeoShaderCatalogEntry *)entryWithIdentifier:(NSString *)identifier;
- (NSArray<NeoShaderCatalogEntry *> *)entriesInCategory:(NSString *)category;
/// Case-insensitive search in names, folders and identifiers.
- (NSArray<NeoShaderCatalogEntry *> *)entriesMatching:(NSString *)query;
- (nullable NSURL *)downloadURLForFile:(NeoShaderCatalogFile *)file;
- (nullable NSURL *)previewURLForFile:(NeoShaderCatalogFile *)file;
@end

/// The catalogs bundled with the application, loaded once. "Catalog
/// manager" of the shared shader kit.
@interface NeoShaderCatalogManager : NSObject
+ (instancetype)sharedManager;
/// "libretro" (slang-catalog.json) or "dolphin" (dolphin-catalog.json).
- (nullable NeoShaderCatalog *)catalogForEngine:(NSString *)engine;
/// Presets NOT offered and why ([{identifier, code, detail}]), for the
/// developer diagnostics page; loaded on demand.
- (NSArray<NSDictionary<NSString *, NSString *> *> *)diagnosticsForEngine:(NSString *)engine;
/// Tests and tools: catalogs read from a directory instead of the bundle.
- (void)setCatalogDirectory:(nullable NSString *)directory;
@end

NS_ASSUME_NONNULL_END
