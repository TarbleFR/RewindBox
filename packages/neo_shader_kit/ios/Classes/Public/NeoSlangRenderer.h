// SPDX-License-Identifier: GPL-3.0-or-later
// Metal runtime of RetroArch slang presets, engine-independent. A program
// holds the compiled passes, pipelines and textures of one preset for one
// device; a chain holds the per-picture state (framebuffers, history,
// feedback) and encodes the passes, following RetroArch's filter chain
// (gfx/drivers_shader/shader_vulkan.c): Original is the picture, Source the
// previous pass output, PassOutput# / PassFeedback# / OriginalHistory# /
// LUTs by name; filter_linear#, wrap_mode# and mipmap_input# describe how
// pass # samples its input; a pass without scale is source x1, the last one
// viewport x1. Every pass renders into a texture; the caller draws the
// returned texture on screen (rotation and placement stay the engine's).
#import <CoreGraphics/CoreGraphics.h>
#import <Foundation/Foundation.h>
#import <Metal/Metal.h>

NS_ASSUME_NONNULL_BEGIN

FOUNDATION_EXPORT NSString *const NeoSlangErrorDomain;
/// userInfo key of the stable reason code (NSString) of a failure: the
/// PRESET_*, SOURCE_*, GLSL_*, REFLECT_* and MSL_FAILED codes of the
/// portable core (NeoSlangCompiler.hpp), then PROGRAM_ARGUMENTS,
/// PASS_FORMAT_UNSUPPORTED, METAL_SAMPLER_FAILED, METAL_LIBRARY_FAILED,
/// METAL_PIPELINE_FAILED, LUT_UNREADABLE, LUT_DECODE_FAILED, LUT_TOO_LARGE,
/// LUT_ALLOCATION_FAILED. The raw technical detail (file, compiler message)
/// is under NSDebugDescriptionErrorKey, for diagnostics only.
FOUNDATION_EXPORT NSString *const NeoSlangErrorCodeKey;

/// One "#pragma parameter". `label` is the shader author's text (shown
/// untranslated); `section` is YES for RetroArch's heading lines
/// (minimum == maximum), which have no value to set.
@interface NeoSlangParameterInfo : NSObject
@property(nonatomic, copy, readonly) NSString *identifier;
@property(nonatomic, copy, readonly) NSString *label;
@property(nonatomic, readonly) float initial;
@property(nonatomic, readonly) float minimum;
@property(nonatomic, readonly) float maximum;
@property(nonatomic, readonly) float step;
/// Value given by the preset chain (initial when it gives none).
@property(nonatomic, readonly) float presetValue;
@property(nonatomic, readonly) BOOL section;
@end

/// Per-frame values of the semantic uniforms.
typedef struct {
  uint32_t frameCount;
  int32_t frameDirection;
  /// Quarter turns counter-clockwise (0-3), RetroArch's Rotation.
  uint32_t rotation;
  /// Display aspect of the core picture.
  float coreAspect;
  float coreFPS;
  /// Microseconds since the previous frame.
  uint32_t frameTimeDelta;
  uint32_t swapCount;
} NeoSlangFrameState;

@interface NeoSlangProgram : NSObject
/// Compiles `presetPath` (relative to `root`, the repository mirror) for
/// `device`: preset rules, glslang, reflection, MSL, Metal libraries and
/// pipelines, LUT textures. Slow: never on the main thread. `iosPlatform`
/// selects SPIRV-Cross's platform (NO only for desktop tests).
+ (nullable instancetype)programWithRoot:(NSString *)root
                                  preset:(NSString *)presetPath
                                  device:(id<MTLDevice>)device
                             iosPlatform:(BOOL)iosPlatform
                                   error:(NSError *_Nullable *_Nullable)error;
@property(nonatomic, copy, readonly) NSString *presetPath;
@property(nonatomic, readonly) id<MTLDevice> device;
@property(nonatomic, copy, readonly) NSArray<NeoSlangParameterInfo *> *parameters;
@property(nonatomic, readonly) NSUInteger passCount;
@property(nonatomic, readonly) NSUInteger historyDepth;
/// Every repository file the preset read.
@property(nonatomic, copy, readonly) NSArray<NSString *> *files;
/// Seconds spent compiling (translation, then Metal).
@property(nonatomic, readonly) double translationSeconds;
@property(nonatomic, readonly) double metalSeconds;
/// Index of a parameter by identifier, NSNotFound when absent.
- (NSUInteger)indexOfParameter:(NSString *)identifier;
@end

@interface NeoSlangChain : NSObject
- (instancetype)initWithProgram:(NeoSlangProgram *)program;
@property(nonatomic, readonly) NeoSlangProgram *program;
/// Parameter values in the program's order (thread-safe; missing values
/// keep the preset's).
- (void)setParameterValues:(NSArray<NSNumber *> *)values;
- (void)setParameter:(NSString *)identifier value:(float)value;
/// Current values, in the program's order.
- (NSArray<NSNumber *> *)parameterValues;
/// Texture of `width` x `height` (BGRA8Unorm, render target, private) to
/// receive the next picture, top row first; it becomes Original and enters
/// the history ring at the next encode. Nil on allocation failure. This
/// method, encode and reset run on one thread (the emulation thread).
- (nullable id<MTLTexture>)originalTextureWithWidth:(NSUInteger)width height:(NSUInteger)height;
/// Encodes every pass on `commandBuffer` reading the texture last returned
/// by originalTextureWithWidth:height:, and returns the texture holding the
/// last pass output. `outputSize`: the screen rectangle in pixels along the
/// picture's own axes (swapped for odd rotations); `viewportSize`: the same
/// rectangle as drawn (RetroArch's FinalViewportSize). `smooth` is the
/// filter of passes that do not set filter_linear. Nil on failure.
- (nullable id<MTLTexture>)encodeOnCommandBuffer:(id<MTLCommandBuffer>)commandBuffer
                                      outputSize:(CGSize)outputSize
                                    viewportSize:(CGSize)viewportSize
                                           frame:(NeoSlangFrameState)frame
                                          smooth:(BOOL)smooth;
/// YES when the last pass's output already has the size asked for (draw it
/// 1:1, nearest); NO when the preset scales its last pass itself
/// (RetroArch then adds a plain copy filtered by the smooth setting).
@property(nonatomic, readonly) BOOL lastPassMatchesOutput;
/// Forgets history and feedback (black), e.g. after a size change.
- (void)reset;
/// Bytes of GPU memory of the chain's textures (framebuffers, history,
/// feedback), for the diagnostics page.
@property(nonatomic, readonly) NSUInteger textureBytes;
/// Why the last encode returned nil: CHAIN_NO_PICTURE, CHAIN_OUTPUT_SIZE,
/// CHAIN_PASS_SIZE, CHAIN_MEMORY (more than 1 GiB of textures at this
/// size), CHAIN_ALLOCATION, CHAIN_ENCODER; nil after a success. The detail
/// is technical (log only).
@property(nonatomic, copy, readonly, nullable) NSString *lastFailureCode;
@property(nonatomic, copy, readonly, nullable) NSString *lastFailureDetail;
@end

NS_ASSUME_NONNULL_END
