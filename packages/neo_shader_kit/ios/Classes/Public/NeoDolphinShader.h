// SPDX-License-Identifier: GPL-3.0-or-later
// Dolphin post-processing shaders (.glsl with Dolphin's [configuration]
// block and helpers) as the embedded Dolphin core builds them on Metal:
// options, translation through NeoStation's reproduction of the core's
// pipeline (Dolphin's header and uniform block, GLSL -> SPIR-V -> MSL of the
// pinned DolphiniOS revision) and compilation by the device's Metal
// compiler. A Dolphin shader is never treated as a RetroArch preset.
#import <Foundation/Foundation.h>
#import <Metal/Metal.h>

NS_ASSUME_NONNULL_BEGIN

FOUNDATION_EXPORT NSString *const NeoDolphinShaderErrorDomain;
/// userInfo key of the stable reason code (NSString): DOLPHIN_NOT_TEXT,
/// DOLPHIN_TOO_LARGE, DOLPHIN_NO_MAIN, GLSL_FRAGMENT_FAILED,
/// GLSL_VERTEX_FAILED, MSL_FAILED, METAL_LIBRARY_FAILED. The technical
/// detail (compiler log) is under NSDebugDescriptionErrorKey, for the log.
FOUNDATION_EXPORT NSString *const NeoDolphinShaderErrorCodeKey;

typedef NS_ENUM(NSInteger, NeoDolphinOptionType) {
  NeoDolphinOptionTypeBool,
  NeoDolphinOptionTypeFloat,
  NeoDolphinOptionTypeInteger,
};

/// One [OptionBool] / [OptionRangeFloat] / [OptionRangeInteger] entry, as
/// Dolphin's PostProcessingConfiguration::LoadOptions reads it. `guiName`
/// is the shader author's text (shown untranslated).
@interface NeoDolphinShaderOption : NSObject
@property(nonatomic, readonly) NeoDolphinOptionType type;
@property(nonatomic, copy, readonly) NSString *guiName;
/// OptionName: the uniform's name and the key of Dolphin.ini.
@property(nonatomic, copy, readonly) NSString *name;
@property(nonatomic, copy, readonly) NSString *dependentOption;
/// Default values, 1 to 4 components (a bool is 0 or 1).
@property(nonatomic, copy, readonly) NSArray<NSNumber *> *defaultValues;
@property(nonatomic, copy, readonly) NSArray<NSNumber *> *minimums;
@property(nonatomic, copy, readonly) NSArray<NSNumber *> *maximums;
@property(nonatomic, copy, readonly) NSArray<NSNumber *> *steps;
@end

@interface NeoDolphinShader : NSObject
/// The options of `code` (no translation; fast enough for a table).
+ (NSArray<NeoDolphinShaderOption *> *)optionsOfCode:(NSString *)code;
/// Author lines of the leading comment block, quoted as written (at most
/// four), e.g. "by Mattias" / a Shadertoy address.
+ (NSArray<NSString *> *)creditLinesOfCode:(NSString *)code;
/// Translates `code` like the core does on iOS (slow: not on the main
/// thread). Nil with a NeoDolphinShaderErrorDomain error on failure.
+ (nullable instancetype)shaderWithCode:(NSString *)code error:(NSError *_Nullable *_Nullable)error;
@property(nonatomic, copy, readonly) NSArray<NeoDolphinShaderOption *> *options;
@property(nonatomic, copy, readonly) NSString *fragmentMSL;
@property(nonatomic, copy, readonly) NSString *vertexMSL;
@property(nonatomic, readonly) NSUInteger sampleInstructions;
/// Compiles both stages with `device`'s Metal compiler, what the core's
/// Metal backend does when it loads the shader. Slow: not on the main
/// thread.
- (BOOL)compileWithDevice:(id<MTLDevice>)device error:(NSError *_Nullable *_Nullable)error;
@end

NS_ASSUME_NONNULL_END
