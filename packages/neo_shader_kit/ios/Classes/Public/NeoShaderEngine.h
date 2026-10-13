// SPDX-License-Identifier: GPL-3.0-or-later
#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

/// Shader formats. Each engine accepts only its own: a Dolphin shader is
/// never loaded as a RetroArch preset, and the other way round.
typedef NSString *NeoShaderFormat NS_TYPED_ENUM;
/// NeoStation's hand-ported single-pass presets (Metal source in the app).
FOUNDATION_EXPORT NeoShaderFormat const NeoShaderFormatBuiltinMetal;
/// RetroArch slang presets (.slangp + .slang), translated to Metal on the
/// device (glslang + SPIRV-Cross).
FOUNDATION_EXPORT NeoShaderFormat const NeoShaderFormatSlang;
/// Dolphin post-processing shaders (.glsl with Dolphin's helpers), compiled
/// by the Dolphin core itself.
FOUNDATION_EXPORT NeoShaderFormat const NeoShaderFormatDolphinGLSL;

/// What an engine can do with shaders; the common pages adapt to it (no
/// download section when no format is downloadable, "next launch" notes when
/// shaders cannot change during a session...).
@interface NeoShaderEngineCapabilities : NSObject
@property(nonatomic, copy) NSString *engineIdentifier;  // "libretro", "dolphin"
@property(nonatomic, copy) NSArray<NeoShaderFormat> *formats;
/// Metal, the only renderer of the embedded engines.
@property(nonatomic, copy) NSString *renderBackend;
@property(nonatomic, assign) BOOL appliesShaders;
/// YES: a chosen shader is applied to the running game. NO: it is saved
/// and applied when the game is launched again (retained Dolphin core).
@property(nonatomic, assign) BOOL switchesDuringSession;
@property(nonatomic, assign) BOOL configurableParameters;
/// Multi-pass presets with textures and history (slang).
@property(nonatomic, assign) BOOL multiPassPresets;
/// Shaders can be downloaded from an official catalog for this engine.
@property(nonatomic, assign) BOOL downloadableCatalog;
/// Shader files can be imported from the Files app.
@property(nonatomic, assign) BOOL importsFiles;
/// Profile scopes offered, most general first: "global", "core",
/// "console", "game".
@property(nonatomic, copy) NSArray<NSString *> *profileScopes;
/// Hardware and engine limits shown in diagnostics (keys are stable
/// identifiers, values plain numbers or strings).
@property(nonatomic, copy) NSDictionary<NSString *, id> *limits;
@end

/// Result of applying or validating a shader. `code` is a stable reason
/// (translated by the host's catalogs); `detail` is the raw technical
/// diagnostic, kept for the developer page and the session log only.
@interface NeoShaderResult : NSObject
@property(nonatomic, readonly) BOOL success;
@property(nonatomic, copy, readonly, nullable) NSString *code;
@property(nonatomic, copy, readonly, nullable) NSString *detail;
+ (instancetype)success;
+ (instancetype)failureWithCode:(NSString *)code detail:(nullable NSString *)detail;
@end

/// Implemented by each engine (libretro session, Dolphin bridge): the
/// technical pipeline stays the engine's own, the pages are shared.
@protocol NeoShaderBackendAdapter <NSObject>
@property(nonatomic, readonly) NeoShaderEngineCapabilities *shaderCapabilities;
/// Translated label (the host's catalogs), the key itself when missing.
- (NSString *)shaderText:(NSString *)key;
/// Identifier of the shader in effect ("" for none) and its display name.
@property(nonatomic, readonly, copy) NSString *activeShaderIdentifier;
/// Validates then applies (or schedules, see switchesDuringSession) a
/// shader with parameter values; nil identifier = no shader. On failure the
/// previous shader stays in effect. Completion on the main queue.
- (void)applyShader:(nullable NSString *)identifier
         parameters:(nullable NSDictionary<NSString *, NSNumber *> *)parameters
         completion:(void (^)(NeoShaderResult *result))completion;
@end

NS_ASSUME_NONNULL_END
