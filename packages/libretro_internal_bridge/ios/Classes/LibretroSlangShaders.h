#import <Foundation/Foundation.h>
#import <Metal/Metal.h>

@class NeoShaderCatalog;
@class NeoShaderStorage;
@class NeoSlangProgram;

NS_ASSUME_NONNULL_BEGIN

/// RetroArch slang presets in the embedded libretro engine (Build 450):
/// identifiers stored in the frontend settings, the shared storage of
/// installed presets and their compilation. The catalog, downloads and
/// Metal runtime belong to the shader kit (neo_shader_kit).

/// Prefix of a slang preset in `shader.preset`: "slang:" + catalog
/// identifier ("slang:crt/crt-royale.slangp"); built-in presets keep their
/// bare identifiers.
FOUNDATION_EXPORT NSString *const LibretroSlangPrefix;

/// Failure codes of LibretroCompileSlangShader besides the shader kit's
/// (NeoSlangErrorCodeKey): the preset is not installed, or a file of its
/// installation is missing.
FOUNDATION_EXPORT NSString *const LibretroSlangNotInstalled;  // SHADER_NOT_INSTALLED

FOUNDATION_EXPORT BOOL LibretroIsSlangShader(NSString *_Nullable identifier);
/// Catalog identifier of a stored slang identifier (nil when not one).
FOUNDATION_EXPORT NSString *_Nullable LibretroSlangCatalogIdentifier(NSString *_Nullable identifier);
FOUNDATION_EXPORT NSString *LibretroSlangShaderIdentifier(NSString *catalogIdentifier);

/// Library/Application Support/NeoStation/Shaders/libretro.
FOUNDATION_EXPORT NSString *LibretroSlangStorageRoot(void);
FOUNDATION_EXPORT NeoShaderStorage *LibretroSlangStorage(void);
/// The libretro/slang-shaders catalog bundled with the shader kit (nil
/// when it cannot be read).
FOUNDATION_EXPORT NeoShaderCatalog *_Nullable LibretroSlangCatalog(void);

/// Compiles an installed preset for `device` (glslang, SPIRV-Cross, Metal):
/// slow, never on the main or emulation thread. On failure `code` gets a
/// stable reason (SHADER_NOT_INSTALLED or the shader kit's code) and
/// `detail` the technical diagnostic (log only).
FOUNDATION_EXPORT NeoSlangProgram *_Nullable LibretroCompileSlangShader(NSString *identifier, id<MTLDevice> device,
                                                                        NSString *_Nullable *_Nullable code,
                                                                        NSString *_Nullable *_Nullable detail);

NS_ASSUME_NONNULL_END
