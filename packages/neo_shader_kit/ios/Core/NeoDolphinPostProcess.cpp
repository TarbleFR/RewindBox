// SPDX-License-Identifier: GPL-3.0-or-later
#include "NeoDolphinPostProcess.hpp"

#include <algorithm>
#include <cerrno>
#include <cstdlib>
#include <exception>
#include <locale>
#include <map>
#include <sstream>
#include <strings.h>

#include "NeoSlangCompiler.hpp"
#include "spirv_msl.hpp"

namespace neoshader {

namespace {

bool fail(ShaderError* error, const char* code, const std::string& detail) {
  if (error != nullptr) {
    error->code = code;
    error->detail = detail;
  }
  return false;
}

// MTLUtil.mm SHADER_HEADER (pinned revision).
const char* const kMetalShaderHeader = R"(
// Target GLSL 4.5.
#version 450 core
// Always available on Metal
#extension GL_EXT_shader_8bit_storage : require
#extension GL_EXT_shader_16bit_storage : require
#extension GL_EXT_shader_explicit_arithmetic_types_int8 : require
#extension GL_EXT_shader_explicit_arithmetic_types_int16 : require

#define ATTRIBUTE_LOCATION(x) layout(location = x)
#define FRAGMENT_OUTPUT_LOCATION(x) layout(location = x)
#define FRAGMENT_OUTPUT_LOCATION_INDEXED(x, y) layout(location = x, index = y)
#define UBO_BINDING(packing, x) layout(packing, set = 0, binding = (x - 1))
#define SAMPLER_BINDING(x) layout(set = 1, binding = x)
#define TEXEL_BUFFER_BINDING(x) layout(set = 1, binding = (x + 8))
#define SSBO_BINDING(x) layout(std430, set = 2, binding = x)
#define INPUT_ATTACHMENT_BINDING(x, y, z) layout(set = x, binding = y, input_attachment_index = z)
#define VARYING_LOCATION(x) layout(location = x)
#define FORCE_EARLY_Z layout(early_fragment_tests) in

// Metal framebuffer fetch helpers.
#define FB_FETCH_VALUE subpassLoad(in_ocol0)

// hlsl to glsl function translation
#define API_METAL 1
#define float2 vec2
#define float3 vec3
#define float4 vec4
#define uint2 uvec2
#define uint3 uvec3
#define uint4 uvec4
#define int2 ivec2
#define int3 ivec3
#define int4 ivec4
#define frac fract
#define lerp mix

// These were changed in Vulkan
#define gl_VertexID gl_VertexIndex
#define gl_InstanceID gl_InstanceIndex
)";

// PostProcessing::GetHeader, after the uniform block (Metal: no geometry
// shaders, so v_tex0 is a plain varying).
const char* const kFragmentHelpers = R"(
float4 Sample() { return texture(samp0, v_tex0); }
float4 SampleLocation(float2 location) { return texture(samp0, float3(location, float(v_tex0.z))); }
float4 SampleLayer(int layer) { return texture(samp0, float3(v_tex0.xy, float(layer))); }
#define SampleOffset(offset) textureOffset(samp0, v_tex0, offset)

float2 GetTargetResolution()
{
  return target_resolution.xy;
}

float2 GetInvTargetResolution()
{
  return target_resolution.zw;
}

float2 GetWindowResolution()
{
  return window_resolution.xy;
}

float2 GetInvWindowResolution()
{
  return window_resolution.zw;
}

float2 GetResolution()
{
  return resolution.xy;
}

float2 GetInvResolution()
{
  return resolution.zw;
}

float2 GetCoordinates()
{
  return v_tex0.xy;
}

float GetLayer()
{
  return v_tex0.z;
}

uint GetTime()
{
  return time;
}

void SetOutput(float4 color)
{
  ocol0 = color;
}

#define GetOption(x) (x)
#define OptionEnabled(x) ((x) != 0)
#define OptionDisabled(x) ((x) == 0)

)";

std::string stripWhitespace(const std::string& text) {
  const char* blanks = " \t\r\n";
  const size_t first = text.find_first_not_of(blanks);
  if (first == std::string::npos) return std::string();
  const size_t last = text.find_last_not_of(blanks);
  return text.substr(first, last - first + 1);
}

/// IniFile::ParseLine.
bool parseLine(const std::string& line, std::string* key, std::string* value) {
  if (line.empty() || line.front() == '#') return false;
  const size_t equals = line.find('=');
  if (equals == std::string::npos) return false;
  *key = stripWhitespace(line.substr(0, equals));
  std::string stripped = stripWhitespace(line.substr(equals + 1));
  if (!stripped.empty() && stripped.front() == '"' && stripped.back() == '"') {
    stripped = stripped.size() >= 2 ? stripped.substr(1, stripped.size() - 2) : std::string();
  }
  *value = stripped;
  return true;
}

/// Common::TryParse for floats: commas become dots, the whole string must be
/// consumed (leading spaces are skipped by >>, trailing ones fail).
bool tryParseFloat(std::string text, float* output) {
  std::replace(text.begin(), text.end(), ',', '.');
  std::istringstream stream(text);
  stream.imbue(std::locale::classic());
  float value = 0;
  if (stream >> value && stream.eof()) {
    *output = value;
    return true;
  }
  return false;
}

/// Common::TryParse for integers: strtoll base 0, whole string consumed.
bool tryParseInteger(const std::string& text, int* output) {
  errno = 0;
  char* end = nullptr;
  const long long value = std::strtoll(text.c_str(), &end, 0);
  if (end == nullptr || *end != '\0' || errno == ERANGE) return false;
  if (value < -2147483648LL || value > 2147483647LL) return false;
  *output = static_cast<int>(value);
  return true;
}

bool tryParseBool(const std::string& text, bool* output) {
  float value = 0;
  const bool isFloat = tryParseFloat(text, &value);
  if ((isFloat && value == 1) || strcasecmp(text.c_str(), "true") == 0) {
    *output = true;
  } else if ((isFloat && value == 0) || strcasecmp(text.c_str(), "false") == 0) {
    *output = false;
  } else {
    return false;
  }
  return true;
}

/// Common::TryParseVector (',' delimiter), at most 4 values kept.
template <typename Parse>
void parseVector(const std::string& text, std::vector<double>* output, Parse parse) {
  output->clear();
  std::istringstream buffer(text);
  std::string item;
  while (std::getline(buffer, item, ',')) {
    double value = 0;
    if (!parse(item, &value)) break;  // TryParseVector stops at the first bad item
    output->push_back(value);
  }
  if (output->size() > 4) output->resize(4);
}

void appendUniformBlock(std::string* source, const std::vector<DolphinOption>& options) {
  // PostProcessing::GetUniformBufferHeader(true).
  *source +=
      "UBO_BINDING(std140, 1) uniform PSBlock {\n"
      "  float4 resolution;\n"
      "  float4 target_resolution;\n"
      "  float4 window_resolution;\n"
      "  int2 stereo_views;\n"
      "  float4 src_rect;\n"
      "  int src_layer;\n"
      "  uint time;\n"
      "  int graphics_api;\n"
      "  int intermediary_buffer;\n"
      "  int resampling_method;\n"
      "  int correct_color_space;\n"
      "  int game_color_space;\n"
      "  int correct_gamma;\n"
      "  float game_gamma;\n"
      "  int sdr_display_gamma_sRGB;\n"
      "  float sdr_display_custom_gamma;\n"
      "  int linear_space_output;\n"
      "  int hdr_output;\n"
      "  float hdr_paper_white_nits;\n"
      "  float hdr_sdr_white_nits;\n";
  *source += "\n";
  unsigned unused = 1;
  for (const DolphinOption& option : options) {
    const size_t count = option.values.size();
    if (option.type == DolphinOptionType::Bool) {
      *source += "  int " + option.name + ";\n";
      for (unsigned index = 0; index < 3; index++) *source += "  int ubo_align_" + std::to_string(unused++) + "_;\n";
    } else if (option.type == DolphinOptionType::Integer) {
      *source += count == 1 ? "  int " + option.name + ";\n"
                            : "  int" + std::to_string(count) + " " + option.name + ";\n";
      for (size_t index = count; index < 4; index++) *source += "  int ubo_align_" + std::to_string(unused++) + "_;\n";
    } else {
      *source += count == 1 ? "  float " + option.name + ";\n"
                            : "  float" + std::to_string(count) + " " + option.name + ";\n";
      for (size_t index = count; index < 4; index++) {
        *source += "  float ubo_align_" + std::to_string(unused++) + "_;\n";
      }
    }
  }
  *source += "};\n\n";
}

bool translateStage(std::vector<uint32_t> words, bool fragment, const DolphinTranslateOptions& options,
                    std::string* msl, std::string* entry, ShaderError* error) {
  try {
    spirv_cross::CompilerMSL compiler(std::move(words));
    spirv_cross::CompilerMSL::Options mslOptions;
    mslOptions.platform = options.iosPlatform ? spirv_cross::CompilerMSL::Options::iOS
                                              : spirv_cross::CompilerMSL::Options::macOS;
    mslOptions.set_msl_version(2, 3);
    mslOptions.use_framebuffer_fetch_subpasses = true;
    compiler.set_msl_options(mslOptions);
    auto bind = [&](spv::ExecutionModel model, uint32_t set, uint32_t binding, uint32_t buffer, uint32_t texture,
                    uint32_t sampler) {
      spirv_cross::MSLResourceBinding resource;
      resource.stage = model;
      resource.desc_set = set;
      resource.binding = binding;
      resource.msl_buffer = buffer;
      resource.msl_texture = texture;
      resource.msl_sampler = sampler;
      compiler.add_msl_resource_binding(resource);
    };
    // MTLUtil.mm resource_bindings.
    bind(spv::ExecutionModelVertex, 0, 0, 1, 0, 0);
    bind(spv::ExecutionModelVertex, 0, 1, 1, 0, 0);
    bind(spv::ExecutionModelVertex, 0, 3, 2, 0, 0);
    bind(spv::ExecutionModelVertex, 2, 1, 0, 0, 0);
    bind(spv::ExecutionModelFragment, 0, 0, 0, 0, 0);
    bind(spv::ExecutionModelFragment, 0, 1, 1, 0, 0);
    bind(spv::ExecutionModelFragment, 2, 0, 2, 0, 0);
    if (fragment) {
      // VideoCommon::MAX_PIXEL_SHADER_SAMPLERS = 8.
      for (uint32_t index = 0; index < 8; index++) bind(spv::ExecutionModelFragment, 1, index, 0, index, index);
    }
    *msl = std::string(
               "#pragma clang diagnostic ignored \"-Wunused-variable\"\n"
               "#pragma clang diagnostic ignored \"-Wreturn-type\"\n") +
           compiler.compile();
    *entry = compiler.get_cleansed_entry_point_name("main", fragment ? spv::ExecutionModelFragment
                                                                     : spv::ExecutionModelVertex);
  } catch (const std::exception& exception) {
    return fail(error, "MSL_FAILED", exception.what());
  }
  return true;
}

}  // namespace

const char* dolphinOptionTypeName(DolphinOptionType type) {
  switch (type) {
    case DolphinOptionType::Bool:
      return "bool";
    case DolphinOptionType::Float:
      return "float";
    case DolphinOptionType::Integer:
      return "integer";
  }
  return "bool";
}

std::vector<DolphinOption> parseDolphinOptions(const std::string& code) {
  const std::string startDelimiter = "[configuration]";
  const std::string endDelimiter = "[/configuration]";
  const size_t start = code.find(startDelimiter);
  const size_t end = code.find(endDelimiter);
  std::map<std::string, DolphinOption> byName;
  if (start == std::string::npos || end == std::string::npos) return {};
  // As Dolphin: the text between the delimiters (empty when misordered).
  const size_t from = start + startDelimiter.size();
  const std::string block = end > from ? code.substr(from, end - from) : std::string();

  struct Section {
    std::string type;
    std::vector<std::pair<std::string, std::string>> entries;
  };
  std::vector<Section> sections;
  std::istringstream lines(block);
  std::string line;
  while (std::getline(lines, line)) {
    if (!line.empty() && line.back() == '\r') line.pop_back();
    if (line.empty()) continue;
    if (line[0] == '[') {
      const size_t close = line.find(']');
      if (close != std::string::npos) sections.push_back({line.substr(1, close - 1), {}});
      continue;
    }
    if (sections.empty()) continue;
    std::string key, value;
    if (!parseLine(line, &key, &value)) continue;
    if (!(key.empty() && value.empty())) sections.back().entries.emplace_back(key, value);
  }

  for (const Section& section : sections) {
    DolphinOption option;
    // Any other section name keeps Dolphin's default type, Bool.
    if (section.type == "OptionRangeFloat") {
      option.type = DolphinOptionType::Float;
    } else if (section.type == "OptionRangeInteger") {
      option.type = DolphinOptionType::Integer;
    }
    bool boolValue = false;
    for (const auto& entry : section.entries) {
      const std::string& key = entry.first;
      const std::string& value = entry.second;
      if (key == "GUIName") {
        option.guiName = value;
      } else if (key == "OptionName") {
        option.name = value;
      } else if (key == "DependentOption") {
        option.dependentOption = value;
      } else if (key == "MinValue" || key == "MaxValue" || key == "DefaultValue" || key == "StepAmount") {
        std::vector<double>* target = key == "MinValue"   ? &option.minimums
                                      : key == "MaxValue" ? &option.maximums
                                      : key == "DefaultValue" ? &option.values
                                                              : &option.steps;
        if (option.type == DolphinOptionType::Bool) {
          // Every one of the four keys feeds the single bool value.
          bool parsed = false;
          if (tryParseBool(value, &parsed)) boolValue = parsed;
        } else if (option.type == DolphinOptionType::Integer) {
          parseVector(value, target, [](const std::string& item, double* out) {
            int number = 0;
            if (!tryParseInteger(item, &number)) return false;
            *out = number;
            return true;
          });
        } else {
          parseVector(value, target, [](const std::string& item, double* out) {
            float number = 0;
            if (!tryParseFloat(item, &number)) return false;
            *out = number;
            return true;
          });
        }
      }
    }
    if (option.type == DolphinOptionType::Bool) option.values = {boolValue ? 1.0 : 0.0};
    byName[option.name] = option;  // later sections with the same name win
  }
  std::vector<DolphinOption> options;
  unsigned offset = kDolphinBuiltinUniformBytes;
  for (auto& entry : byName) {
    entry.second.uniformOffset = offset;
    offset += 16;
    options.push_back(entry.second);
  }
  return options;
}

bool translateDolphinPostProcess(const std::string& code, const DolphinTranslateOptions& options,
                                 DolphinPostProcessShader* shader, ShaderError* error) {
  *shader = DolphinPostProcessShader();
  if (code.size() > kMaxDolphinShaderBytes) return fail(error, "DOLPHIN_TOO_LARGE", std::to_string(code.size()));
  if (code.find("main") == std::string::npos) return fail(error, "DOLPHIN_NO_MAIN", "");
  shader->options = parseDolphinOptions(code);
  shader->uniformBytes =
      kDolphinBuiltinUniformBytes + 16u * static_cast<unsigned>(shader->options.size());
  for (const DolphinOption& option : shader->options) {
    if (option.type != DolphinOptionType::Bool && option.values.size() > 1) shader->vectorOptionLayoutMismatch = true;
  }

  // CompilePixelShader: GetHeader(true) + code + GetFooter() (empty), then
  // TranslateShaderToMSL prepends the Metal header.
  std::string fragment = kMetalShaderHeader;
  appendUniformBlock(&fragment, shader->options);
  fragment +=
      "SAMPLER_BINDING(0) uniform sampler2DArray samp0;\n"
      "SAMPLER_BINDING(1) uniform sampler2DArray samp1;\n"
      "VARYING_LOCATION(0) in float3 v_tex0;\n"
      "FRAGMENT_OUTPUT_LOCATION(0) out float4 ocol0;\n";
  fragment += kFragmentHelpers;
  fragment += code;
  shader->fragmentGLSL = fragment;

  // CompileVertexShader: GetUniformBufferHeader(true) + GetVertexShaderBody()
  // (Metal: no Y inversion).
  std::string vertex = kMetalShaderHeader;
  appendUniformBlock(&vertex, shader->options);
  vertex +=
      "VARYING_LOCATION(0) out float3 v_tex0;\n"
      "#define id gl_VertexID\n"
      "#define opos gl_Position\n"
      "void main() {\n"
      "  v_tex0 = float3(float((id << 1) & 2), float(id & 2), 0.0f);\n"
      "  opos = float4(v_tex0.xy * float2(2.0f, -2.0f) + float2(-1.0f, 1.0f), 0.0f, 1.0f);\n"
      "  v_tex0 = float3(src_rect.xy + (src_rect.zw * v_tex0.xy), float(src_layer));\n"
      "}\n";
  shader->vertexGLSL = vertex;

  // VideoCommon/Spirv.cpp: 450 core, forward compatible, SPIR-V 1.5.
  std::vector<uint32_t> fragmentWords, vertexWords;
  std::string log;
  if (!compileGLSLToSPIRV(fragment, true, 450, true, 0x10500, &fragmentWords, &log)) {
    return fail(error, "GLSL_FRAGMENT_FAILED", log);
  }
  if (!compileGLSLToSPIRV(vertex, false, 450, true, 0x10500, &vertexWords, &log)) {
    return fail(error, "GLSL_VERTEX_FAILED", log);
  }
  unsigned instructions = 0;
  countSampleInstructions(fragmentWords, &shader->sampleInstructions, &shader->samplesInLoop, &instructions);
  if (!translateStage(std::move(fragmentWords), true, options, &shader->fragmentMSL, &shader->fragmentEntry, error)) {
    return false;
  }
  return translateStage(std::move(vertexWords), false, options, &shader->vertexMSL, &shader->vertexEntry, error);
}

}  // namespace neoshader
