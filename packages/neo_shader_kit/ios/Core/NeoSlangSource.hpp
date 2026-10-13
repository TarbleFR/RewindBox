// SPDX-License-Identifier: GPL-3.0-or-later
// RetroArch .slang sources (gfx/drivers_shader/glslang_util.c): #include
// expansion, "#pragma name / format / parameter" metadata and the split into
// a vertex and a fragment stage.
#pragma once

#include <string>
#include <vector>

#include "NeoShaderFiles.hpp"

namespace neoshader {

/// "#pragma format": render target format of the pass (slang names).
enum class SlangFormat {
  Unknown,
  R8_UNORM, R8_UINT, R8_SINT,
  R8G8_UNORM, R8G8_UINT, R8G8_SINT,
  R8G8B8A8_UNORM, R8G8B8A8_UINT, R8G8B8A8_SINT, R8G8B8A8_SRGB,
  A2B10G10R10_UNORM_PACK32, A2B10G10R10_UINT_PACK32,
  R16_UINT, R16_SINT, R16_SFLOAT,
  R16G16_UINT, R16G16_SINT, R16G16_SFLOAT,
  R16G16B16A16_UINT, R16G16B16A16_SINT, R16G16B16A16_SFLOAT,
  R32_UINT, R32_SINT, R32_SFLOAT,
  R32G32_UINT, R32G32_SINT, R32G32_SFLOAT,
  R32G32B32A32_UINT, R32G32B32A32_SINT, R32G32B32A32_SFLOAT,
};

SlangFormat slangFormatFromName(const std::string& name);
const char* slangFormatName(SlangFormat format);

/// "#pragma parameter ID "Description" initial minimum maximum [step]".
struct SlangParameter {
  std::string id;
  std::string description;
  float initial = 0.0f;
  float minimum = 0.0f;
  float maximum = 0.0f;
  float step = 0.0f;
};

struct SlangSource {
  std::string path;
  std::string name;  // "#pragma name" (pass alias declared by the shader)
  SlangFormat format = SlangFormat::Unknown;
  std::vector<SlangParameter> parameters;
  /// GLSL of each stage, ready for glslang: #version, line directive
  /// extension, RetroArch's feature defines, then the shared lines and the
  /// stage's own lines (other stage blanked, "#pragma name/format" removed).
  std::string vertex;
  std::string fragment;
  /// The .slang file and every file it includes (download closure).
  std::vector<std::string> files;
};

/// Limits of one pass source after include expansion.
constexpr unsigned kMaxIncludeDepth = 32;
constexpr size_t kMaxExpandedSourceBytes = 8u * 1024u * 1024u;

/// Feature defines NeoStation emits after #version, as RetroArch does for the
/// uniforms it fills. NeoStation fills OriginalAspect(Rotated),
/// FrameTimeDelta, OriginalFPS and SwapCount; it has no motion sensors, so
/// _HAS_SENSOR_UNIFORMS is not defined and shaders take their fallback path.
extern const char* const kSlangFeatureDefines[3];

/// Loads and expands `path`. Error codes: SOURCE_UNREADABLE (file or include
/// missing), SOURCE_NO_VERSION (first line is not "#version"),
/// SOURCE_UNSAFE_INCLUDE, SOURCE_INCLUDE_DEPTH, SOURCE_TOO_LARGE,
/// SOURCE_BAD_PARAMETER (malformed or conflicting "#pragma parameter"),
/// SOURCE_DUPLICATE_NAME, SOURCE_BAD_FORMAT.
bool loadSlangSource(FileProvider& files, const std::string& path, SlangSource* source, ShaderError* error);

}  // namespace neoshader
