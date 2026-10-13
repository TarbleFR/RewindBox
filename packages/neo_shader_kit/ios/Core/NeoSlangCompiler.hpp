// SPDX-License-Identifier: GPL-3.0-or-later
// Compiles RetroArch slang presets for Metal: glslang turns each stage into
// SPIR-V (Vulkan rules, as RetroArch), SPIRV-Cross reflects it with
// RetroArch's semantic rules (gfx/drivers_shader/slang_process.c) and emits
// Metal Shading Language with fixed bindings:
//   uniform block      -> buffer(0), vertex and fragment
//   push constants     -> buffer(1), vertex and fragment
//   texture binding N  -> texture(N) and sampler(N), fragment
//   vertex attributes  -> attribute(0) Position (float4), attribute(1) TexCoord (float2)
// The vertex stage flips gl_Position.y (Vulkan clip space -> Metal).
#pragma once

#include <cstdint>
#include <string>
#include <vector>

#include "NeoShaderFiles.hpp"
#include "NeoSlangPreset.hpp"
#include "NeoSlangSource.hpp"

namespace spirv_cross {
class Compiler;
}

namespace neoshader {

/// Renames every SPIR-V name that is a C++ alternative token ("and",
/// "or", "not", "xor"...): valid GLSL identifiers (xbr-hybrid defines
/// functions "and" and "or"), rejected by the Metal compiler as MSL is C++.
/// Called before every MSL translation.
void renameReservedMSLNames(spirv_cross::Compiler& compiler);

/// Uniforms NeoStation fills (RetroArch semantic names).
enum class SlangSemantic {
  MVP,
  OutputSize,
  FinalViewportSize,
  FrameCount,
  FrameDirection,
  FrameTimeDelta,
  OriginalFPS,
  Rotation,
  OriginalAspect,
  OriginalAspectRotated,
  TotalSubFrames,
  CurrentSubFrame,
  SwapCount,
};
const char* slangSemanticName(SlangSemantic semantic);

enum class SlangTextureSemantic { Original, Source, OriginalHistory, PassOutput, PassFeedback, User };
const char* slangTextureSemanticName(SlangTextureSemantic semantic);

/// RetroArch's limits (SLANG_NUM_BINDINGS, push constant size, history).
constexpr unsigned kMaxBindings = 16;
constexpr unsigned kMaxPushConstantBytes = 128;
constexpr unsigned kMaxFrameHistory = 128;

/// One active member of the uniform block and/or push constant block.
struct SlangUniformSlot {
  enum class Kind { Semantic, TextureSize, Parameter };
  Kind kind = Kind::Semantic;
  SlangSemantic semantic = SlangSemantic::MVP;            // Kind::Semantic
  SlangTextureSemantic textureSemantic = SlangTextureSemantic::Original;  // Kind::TextureSize
  /// Array index (OriginalHistory#, PassOutput#, PassFeedback#, User#) or
  /// the parameter's index in CompiledSlangPreset::parameters.
  unsigned index = 0;
  /// Byte offsets, -1 when the member is not active in that block.
  int uboOffset = -1;
  int pushOffset = -1;
  /// Float/int/uint components (16 for MVP).
  unsigned components = 1;
};

struct SlangTextureSlot {
  SlangTextureSemantic semantic = SlangTextureSemantic::Original;
  unsigned index = 0;
  unsigned binding = 0;
};

struct CompiledSlangPass {
  std::string vertexMSL;
  std::string fragmentMSL;
  std::string vertexEntry;
  std::string fragmentEntry;
  /// Bytes to bind at buffer(0) / buffer(1) (0 when the block is absent),
  /// rounded up to 16.
  size_t uboSize = 0;
  size_t pushSize = 0;
  std::vector<SlangUniformSlot> uniforms;
  std::vector<SlangTextureSlot> textures;
  /// "#pragma format", or the preset's framebuffer flags.
  SlangFormat format = SlangFormat::R8G8B8A8_UNORM;
  bool explicitFormat = false;
  /// Static figures of the fragment SPIR-V: texture sampling / fetch /
  /// gather instructions and whether any of them can repeat in a loop.
  unsigned sampleInstructions = 0;
  bool samplesInLoop = false;
  unsigned spirvInstructions = 0;
};

/// A preset parameter (first declaration across the passes) with the value
/// the preset chain gives it.
struct CompiledSlangParameter {
  SlangParameter declaration;
  float value = 0.0f;
};

struct CompiledSlangPreset {
  SlangPreset preset;
  std::vector<CompiledSlangPass> passes;
  std::vector<CompiledSlangParameter> parameters;
  /// Pass names after "#pragma name" (preset aliases win).
  std::vector<std::string> aliases;
  /// Frames of history needed (highest OriginalHistory index read).
  unsigned historyDepth = 0;
  /// Passes whose previous output is read (PassFeedback).
  std::vector<bool> feedback;
  /// Every file the preset needs, repository-relative, sorted, unique:
  /// presets, .slang sources and their includes, LUT images.
  std::vector<std::string> files;
};

struct SlangCompileOptions {
  /// SPIRV-Cross platform: iOS for the application, macOS for desktop tests.
  bool iosPlatform = true;
  unsigned mslMajor = 2;
  unsigned mslMinor = 4;
};

/// Loads, preprocesses, compiles and reflects a whole preset. Error codes:
/// the PRESET_* and SOURCE_* codes of the loaders, then
///   GLSL_VERTEX_FAILED / GLSL_FRAGMENT_FAILED (glslang, log in detail),
///   REFLECT_RESOURCE_TYPE (storage buffers/images, vertex textures...),
///   REFLECT_VERTEX_INPUTS, REFLECT_RENDER_TARGETS, REFLECT_BLOCKS,
///   REFLECT_PUSH_CONSTANT_SIZE, REFLECT_BINDING,
///   REFLECT_UNKNOWN_SEMANTIC (a uniform NeoStation does not fill, e.g.
///   RetroArch's HDR or motion sensor uniforms), REFLECT_SEMANTIC_TYPE,
///   REFLECT_TEXTURE_SEMANTIC (unknown texture name, a pass output read
///   before it exists, a missing LUT),
///   MSL_FAILED (SPIRV-Cross).
bool compileSlangPreset(FileProvider& files, const std::string& presetPath, const SlangCompileOptions& options,
                        CompiledSlangPreset* compiled, ShaderError* error);

/// glslang -> SPIR-V for one stage (shared with the Dolphin translator).
/// `vulkanRules` adds EShMsgVulkanRules; `spirvTarget` is 0x10000 (1.0) for
/// slang, 0x10500 (1.5) for Dolphin; `defaultVersion` is the #version
/// assumed when the source has none.
bool compileGLSLToSPIRV(const std::string& source, bool fragment, int defaultVersion, bool coreProfile,
                        unsigned spirvTarget, std::vector<uint32_t>* words, std::string* log);

/// Static figures of a SPIR-V module (see CompiledSlangPass).
void countSampleInstructions(const std::vector<uint32_t>& words, unsigned* samples, bool* inLoop,
                             unsigned* instructions);

}  // namespace neoshader
