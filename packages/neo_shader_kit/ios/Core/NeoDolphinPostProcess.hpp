// SPDX-License-Identifier: GPL-3.0-or-later
// Dolphin post-processing shaders (Data/Sys/Shaders/*.glsl, User/Shaders)
// as the Dolphin core NeoStation embeds compiles them on Metal: the pinned
// DolphiniOS revision 7cac54161659421ed95c2cd1c0b0746539a4cd38
// (Source/Core/VideoCommon/PostProcessing.cpp, VideoCommon/Spirv.cpp,
// VideoBackends/Metal/MTLUtil.mm). The options block, the uniform layout,
// the GLSL header and the GLSL -> SPIR-V -> MSL settings are reproduced, so
// a shader that translates here is expected to translate in the core.
// Dolphin shaders are never treated as RetroArch presets.
#pragma once

#include <cstdint>
#include <string>
#include <vector>

#include "NeoShaderFiles.hpp"

namespace neoshader {

enum class DolphinOptionType { Bool, Float, Integer };
const char* dolphinOptionTypeName(DolphinOptionType type);

/// One [OptionBool] / [OptionRangeFloat] / [OptionRangeInteger] entry.
struct DolphinOption {
  DolphinOptionType type = DolphinOptionType::Bool;
  std::string guiName;
  std::string name;  // OptionName: the uniform's name, key of Dolphin.ini
  std::string dependentOption;
  /// Default values (1 to 4 components; a bool is 0 or 1).
  std::vector<double> values;
  std::vector<double> minimums;
  std::vector<double> maximums;
  std::vector<double> steps;
  /// Byte offset of its 16-byte slot in the uniform buffer, as Dolphin's
  /// FillUniformBuffer writes it (sizeof(BuiltinUniforms) = 140, then one
  /// slot per option in name order).
  unsigned uniformOffset = 0;
};

/// sizeof(VideoCommon::BuiltinUniforms) in the pinned revision.
constexpr unsigned kDolphinBuiltinUniformBytes = 140;

struct DolphinPostProcessShader {
  /// Options in Dolphin's order (std::map: sorted by OptionName).
  std::vector<DolphinOption> options;
  /// The complete GLSL Dolphin compiles for Metal (header included).
  std::string fragmentGLSL;
  std::string vertexGLSL;
  std::string fragmentMSL;
  std::string vertexMSL;
  std::string fragmentEntry;
  std::string vertexEntry;
  /// Bytes of the uniform buffer (builtins + 16 per option).
  unsigned uniformBytes = 0;
  unsigned sampleInstructions = 0;
  bool samplesInLoop = false;
  /// Vector options do not get their 16-byte slot in Dolphin's std140
  /// block (a Dolphin layout limitation): set when one is present.
  bool vectorOptionLayoutMismatch = false;
};

struct DolphinTranslateOptions {
  bool iosPlatform = true;
};

/// PostProcessingConfiguration::LoadOptions on `code`.
std::vector<DolphinOption> parseDolphinOptions(const std::string& code);

/// Builds Dolphin's sources for `code` and translates them to MSL with the
/// core's settings. Error codes: DOLPHIN_TOO_LARGE, DOLPHIN_NO_MAIN,
/// GLSL_FRAGMENT_FAILED / GLSL_VERTEX_FAILED (glslang log in detail),
/// MSL_FAILED.
bool translateDolphinPostProcess(const std::string& code, const DolphinTranslateOptions& options,
                                 DolphinPostProcessShader* shader, ShaderError* error);

/// Largest post-processing source accepted (bytes).
constexpr size_t kMaxDolphinShaderBytes = 512u * 1024u;

}  // namespace neoshader
