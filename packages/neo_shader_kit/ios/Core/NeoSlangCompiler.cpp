// SPDX-License-Identifier: GPL-3.0-or-later
#include "NeoSlangCompiler.hpp"

#include <algorithm>
#include <cstring>
#include <exception>
#include <functional>
#include <map>
#include <mutex>
#include <set>

#include "NeoShaderPaths.hpp"
#include "SPIRV/GlslangToSpv.h"
#include "glslang/Public/ShaderLang.h"
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

struct SemanticName {
  SlangSemantic semantic;
  const char* name;
};

const SemanticName kSemanticNames[] = {
    {SlangSemantic::MVP, "MVP"},
    {SlangSemantic::OutputSize, "OutputSize"},
    {SlangSemantic::FinalViewportSize, "FinalViewportSize"},
    {SlangSemantic::FrameCount, "FrameCount"},
    {SlangSemantic::FrameDirection, "FrameDirection"},
    {SlangSemantic::FrameTimeDelta, "FrameTimeDelta"},
    {SlangSemantic::OriginalFPS, "OriginalFPS"},
    {SlangSemantic::Rotation, "Rotation"},
    {SlangSemantic::OriginalAspect, "OriginalAspect"},
    {SlangSemantic::OriginalAspectRotated, "OriginalAspectRotated"},
    {SlangSemantic::TotalSubFrames, "TotalSubFrames"},
    {SlangSemantic::CurrentSubFrame, "CurrentSubFrame"},
    {SlangSemantic::SwapCount, "SwapCount"},
};

struct TextureName {
  SlangTextureSemantic semantic;
  const char* name;
  const char* sizeName;
  bool array;
};

const TextureName kTextureNames[] = {
    {SlangTextureSemantic::Original, "Original", "OriginalSize", false},
    {SlangTextureSemantic::Source, "Source", "SourceSize", false},
    {SlangTextureSemantic::OriginalHistory, "OriginalHistory", "OriginalHistorySize", true},
    {SlangTextureSemantic::PassOutput, "PassOutput", "PassOutputSize", true},
    {SlangTextureSemantic::PassFeedback, "PassFeedback", "PassFeedbackSize", true},
    {SlangTextureSemantic::User, "User", "UserSize", true},
};

/// RetroArch's resource limits for glslang (gfx/drivers_shader/glslang.cpp).
TBuiltInResource RetroArchResources() {
  TBuiltInResource resources;
  std::memset(&resources, 0, sizeof(resources));
  resources.maxLights = 32;
  resources.maxClipPlanes = 6;
  resources.maxTextureUnits = 32;
  resources.maxTextureCoords = 32;
  resources.maxVertexAttribs = 64;
  resources.maxVertexUniformComponents = 4096;
  resources.maxVaryingFloats = 64;
  resources.maxVertexTextureImageUnits = 32;
  resources.maxCombinedTextureImageUnits = 80;
  resources.maxTextureImageUnits = 32;
  resources.maxFragmentUniformComponents = 4096;
  resources.maxDrawBuffers = 32;
  resources.maxVertexUniformVectors = 128;
  resources.maxVaryingVectors = 8;
  resources.maxFragmentUniformVectors = 16;
  resources.maxVertexOutputVectors = 16;
  resources.maxFragmentInputVectors = 15;
  resources.minProgramTexelOffset = -8;
  resources.maxProgramTexelOffset = 7;
  resources.maxClipDistances = 8;
  resources.maxComputeWorkGroupCountX = 65535;
  resources.maxComputeWorkGroupCountY = 65535;
  resources.maxComputeWorkGroupCountZ = 65535;
  resources.maxComputeWorkGroupSizeX = 1024;
  resources.maxComputeWorkGroupSizeY = 1024;
  resources.maxComputeWorkGroupSizeZ = 64;
  resources.maxComputeUniformComponents = 1024;
  resources.maxComputeTextureImageUnits = 16;
  resources.maxComputeImageUniforms = 8;
  resources.maxComputeAtomicCounters = 8;
  resources.maxComputeAtomicCounterBuffers = 1;
  resources.maxVaryingComponents = 60;
  resources.maxVertexOutputComponents = 64;
  resources.maxGeometryInputComponents = 64;
  resources.maxGeometryOutputComponents = 128;
  resources.maxFragmentInputComponents = 128;
  resources.maxImageUnits = 8;
  resources.maxCombinedImageUnitsAndFragmentOutputs = 8;
  resources.maxCombinedShaderOutputResources = 8;
  resources.maxImageSamples = 0;
  resources.maxVertexImageUniforms = 0;
  resources.maxTessControlImageUniforms = 0;
  resources.maxTessEvaluationImageUniforms = 0;
  resources.maxGeometryImageUniforms = 0;
  resources.maxFragmentImageUniforms = 8;
  resources.maxCombinedImageUniforms = 8;
  resources.maxGeometryTextureImageUnits = 16;
  resources.maxGeometryOutputVertices = 256;
  resources.maxGeometryTotalOutputComponents = 1024;
  resources.maxGeometryUniformComponents = 1024;
  resources.maxGeometryVaryingComponents = 64;
  resources.maxTessControlInputComponents = 128;
  resources.maxTessControlOutputComponents = 128;
  resources.maxTessControlTextureImageUnits = 16;
  resources.maxTessControlUniformComponents = 1024;
  resources.maxTessControlTotalOutputComponents = 4096;
  resources.maxTessEvaluationInputComponents = 128;
  resources.maxTessEvaluationOutputComponents = 128;
  resources.maxTessEvaluationTextureImageUnits = 16;
  resources.maxTessEvaluationUniformComponents = 1024;
  resources.maxTessPatchComponents = 120;
  resources.maxPatchVertices = 32;
  resources.maxTessGenLevel = 64;
  resources.maxViewports = 16;
  resources.maxFragmentAtomicCounters = 8;
  resources.maxCombinedAtomicCounters = 8;
  resources.maxAtomicCounterBindings = 1;
  resources.maxFragmentAtomicCounterBuffers = 1;
  resources.maxCombinedAtomicCounterBuffers = 1;
  resources.maxAtomicCounterBufferSize = 16384;
  resources.maxTransformFeedbackBuffers = 4;
  resources.maxTransformFeedbackInterleavedComponents = 64;
  resources.maxCullDistances = 8;
  resources.maxCombinedClipAndCullDistances = 8;
  resources.maxSamples = 4;
  resources.limits.nonInductiveForLoops = true;
  resources.limits.whileLoops = true;
  resources.limits.doWhileLoops = true;
  resources.limits.generalUniformIndexing = true;
  resources.limits.generalAttributeMatrixVectorIndexing = true;
  resources.limits.generalVaryingIndexing = true;
  resources.limits.generalSamplerIndexing = true;
  resources.limits.generalVariableIndexing = true;
  resources.limits.generalConstantMatrixVectorIndexing = true;
  return resources;
}

/// glslang's process-wide tables are not thread-safe: every compilation
/// holds this lock (RetroArch does the same).
std::mutex& glslangLock() {
  static std::mutex lock;
  return lock;
}

void initializeGlslang() {
  static std::once_flag once;
  std::call_once(once, [] { glslang::InitializeProcess(); });
}

bool startsWith(const std::string& text, const std::string& prefix) {
  return text.size() >= prefix.size() && text.compare(0, prefix.size(), prefix) == 0;
}

/// slang_name_to_texture_semantic_array: "Original" and "Source" exactly,
/// the arrayed names as a prefix followed by a decimal index.
bool builtinTextureName(const std::string& name, bool sizeName, SlangTextureSemantic* semantic, unsigned* index) {
  for (const TextureName& entry : kTextureNames) {
    const std::string prefix = sizeName ? entry.sizeName : entry.name;
    if (!startsWith(name, prefix)) continue;
    const std::string rest = name.substr(prefix.size());
    if (!entry.array) {
      if (!rest.empty()) continue;
      *semantic = entry.semantic;
      *index = 0;
      return true;
    }
    // strtoul(n, NULL, 10): digits, or 0 when none follow.
    unsigned long value = 0;
    size_t digits = 0;
    while (digits < rest.size() && rest[digits] >= '0' && rest[digits] <= '9') {
      value = value * 10 + static_cast<unsigned long>(rest[digits] - '0');
      if (value > 1000000) return false;
      digits++;
    }
    *semantic = entry.semantic;
    *index = static_cast<unsigned>(value);
    return true;
  }
  return false;
}

struct NameMaps {
  // Aliases and LUT names (exact names) -> texture semantic.
  std::vector<std::pair<std::string, SlangUniformSlot>> textures;
  std::vector<std::pair<std::string, SlangUniformSlot>> sizes;
  std::vector<std::string> parameters;
};

bool lookupTexture(const NameMaps& maps, const std::string& name, bool sizeName, SlangTextureSemantic* semantic,
                   unsigned* index) {
  const auto& list = sizeName ? maps.sizes : maps.textures;
  for (const auto& entry : list) {
    if (entry.first == name) {
      *semantic = entry.second.textureSemantic;
      *index = entry.second.index;
      return true;
    }
  }
  return builtinTextureName(name, sizeName, semantic, index);
}

bool addUnique(std::vector<std::pair<std::string, SlangUniformSlot>>* list, const std::string& name,
               SlangTextureSemantic semantic, unsigned index) {
  for (const auto& entry : *list) {
    // slang_texture_semantic_name_map_set_unique: the same name twice is an
    // error unless it maps to the same thing.
    if (entry.first == name) return entry.second.textureSemantic == semantic && entry.second.index == index;
  }
  SlangUniformSlot slot;
  slot.kind = SlangUniformSlot::Kind::TextureSize;
  slot.textureSemantic = semantic;
  slot.index = index;
  list->emplace_back(name, slot);
  return true;
}

/// validate_type_for_semantic.
bool semanticTypeIsValid(const spirv_cross::SPIRType& type, SlangSemantic semantic) {
  using spirv_cross::SPIRType;
  if (!type.array.empty()) return false;
  const bool scalar = type.vecsize == 1 && type.columns == 1;
  switch (semantic) {
    case SlangSemantic::MVP:
      return type.basetype == SPIRType::Float && type.vecsize == 4 && type.columns == 4;
    case SlangSemantic::OutputSize:
    case SlangSemantic::FinalViewportSize:
      return type.basetype == SPIRType::Float && type.vecsize == 4 && type.columns == 1;
    case SlangSemantic::FrameCount:
    case SlangSemantic::TotalSubFrames:
    case SlangSemantic::CurrentSubFrame:
    case SlangSemantic::SwapCount:
    case SlangSemantic::FrameTimeDelta:
    case SlangSemantic::Rotation:
      return type.basetype == SPIRType::UInt && scalar;
    case SlangSemantic::FrameDirection:
      return type.basetype == SPIRType::Int && scalar;
    case SlangSemantic::OriginalFPS:
    case SlangSemantic::OriginalAspect:
    case SlangSemantic::OriginalAspectRotated:
      return type.basetype == SPIRType::Float && scalar;
  }
  return false;
}

struct Reflection {
  std::vector<SlangUniformSlot> uniforms;
  std::vector<SlangTextureSlot> textures;
  size_t uboSize = 0;
  size_t pushSize = 0;
  bool hasUbo = false;
  bool hasPush = false;
  unsigned uboBinding = 0;
};

SlangUniformSlot* findSlot(Reflection* reflection, const SlangUniformSlot& slot) {
  for (SlangUniformSlot& existing : reflection->uniforms) {
    if (existing.kind != slot.kind || existing.index != slot.index) continue;
    if (slot.kind == SlangUniformSlot::Kind::Semantic && existing.semantic != slot.semantic) continue;
    if (slot.kind == SlangUniformSlot::Kind::TextureSize && existing.textureSemantic != slot.textureSemantic) {
      continue;
    }
    return &existing;
  }
  return nullptr;
}

/// add_active_buffer_ranges.
bool addBufferRanges(spirv_cross::Compiler& compiler, const spirv_cross::Resource& resource, bool push,
                     const NameMaps& maps, unsigned passIndex, unsigned passCount, unsigned lutCount,
                     Reflection* reflection, ShaderError* error) {
  const spirv_cross::SPIRType& block = compiler.get_type(resource.base_type_id);
  for (const spirv_cross::BufferRange& range : compiler.get_active_buffer_ranges(resource.id)) {
    const std::string name = compiler.get_member_name(resource.base_type_id, range.index);
    const spirv_cross::SPIRType& type = compiler.get_type(block.member_types[range.index]);
    SlangUniformSlot slot;
    bool known = false;
    for (const SemanticName& entry : kSemanticNames) {
      if (name == entry.name) {
        if (!semanticTypeIsValid(type, entry.semantic)) {
          return fail(error, "REFLECT_SEMANTIC_TYPE", name);
        }
        slot.kind = SlangUniformSlot::Kind::Semantic;
        slot.semantic = entry.semantic;
        slot.components = entry.semantic == SlangSemantic::MVP ? 16 : type.vecsize;
        known = true;
        break;
      }
    }
    if (!known) {
      for (size_t index = 0; index < maps.parameters.size(); index++) {
        if (maps.parameters[index] != name) continue;
        if (!type.array.empty() || type.basetype != spirv_cross::SPIRType::Float || type.vecsize != 1 ||
            type.columns != 1) {
          return fail(error, "REFLECT_SEMANTIC_TYPE", name);
        }
        slot.kind = SlangUniformSlot::Kind::Parameter;
        slot.index = static_cast<unsigned>(index);
        known = true;
        break;
      }
    }
    if (!known) {
      SlangTextureSemantic semantic;
      unsigned index = 0;
      if (lookupTexture(maps, name, true, &semantic, &index)) {
        if (!type.array.empty() || type.basetype != spirv_cross::SPIRType::Float || type.vecsize != 4 ||
            type.columns != 1) {
          return fail(error, "REFLECT_SEMANTIC_TYPE", name);
        }
        if ((semantic == SlangTextureSemantic::PassOutput && index >= passIndex) ||
            (semantic == SlangTextureSemantic::PassFeedback && index >= passCount) ||
            (semantic == SlangTextureSemantic::OriginalHistory && index >= kMaxFrameHistory) ||
            (semantic == SlangTextureSemantic::User && index >= lutCount)) {
          return fail(error, "REFLECT_TEXTURE_SEMANTIC", name);
        }
        slot.kind = SlangUniformSlot::Kind::TextureSize;
        slot.textureSemantic = semantic;
        slot.index = index;
        slot.components = 4;
        known = true;
      }
    }
    if (!known) return fail(error, "REFLECT_UNKNOWN_SEMANTIC", name);
    SlangUniformSlot* existing = findSlot(reflection, slot);
    if (existing == nullptr) {
      reflection->uniforms.push_back(slot);
      existing = &reflection->uniforms.back();
    }
    const int offset = static_cast<int>(range.offset);
    int& target = push ? existing->pushOffset : existing->uboOffset;
    // set_ubo_offset: both stages must agree on the member's place.
    if (target >= 0 && target != offset) return fail(error, "REFLECT_BLOCKS", "offset mismatch for " + name);
    target = offset;
  }
  return true;
}

size_t roundUp16(size_t size) { return (size + 15u) & ~static_cast<size_t>(15u); }

/// slang_reflect.
bool reflectPass(spirv_cross::CompilerMSL& vertex, spirv_cross::CompilerMSL& fragment, const NameMaps& maps,
                 unsigned passIndex, unsigned passCount, unsigned lutCount, Reflection* reflection,
                 ShaderError* error) {
  const spirv_cross::ShaderResources v = vertex.get_shader_resources();
  const spirv_cross::ShaderResources f = fragment.get_shader_resources();
  if (!v.sampled_images.empty() || !v.storage_buffers.empty() || !v.subpass_inputs.empty() ||
      !v.storage_images.empty() || !v.atomic_counters.empty() || !v.separate_images.empty() ||
      !v.separate_samplers.empty() || !f.storage_buffers.empty() || !f.subpass_inputs.empty() ||
      !f.storage_images.empty() || !f.atomic_counters.empty() || !f.separate_images.empty() ||
      !f.separate_samplers.empty()) {
    return fail(error, "REFLECT_RESOURCE_TYPE", "pass " + std::to_string(passIndex));
  }
  if (v.stage_inputs.size() != 2) return fail(error, "REFLECT_VERTEX_INPUTS", "pass " + std::to_string(passIndex));
  unsigned locations = 0;
  for (const spirv_cross::Resource& input : v.stage_inputs) {
    const unsigned location = vertex.get_decoration(input.id, spv::DecorationLocation);
    if (location > 1) return fail(error, "REFLECT_VERTEX_INPUTS", "location " + std::to_string(location));
    locations |= 1u << location;
  }
  if (locations != 0x3) return fail(error, "REFLECT_VERTEX_INPUTS", "pass " + std::to_string(passIndex));
  if (f.stage_outputs.size() != 1 || fragment.get_decoration(f.stage_outputs[0].id, spv::DecorationLocation) != 0) {
    return fail(error, "REFLECT_RENDER_TARGETS", "pass " + std::to_string(passIndex));
  }
  if (v.uniform_buffers.size() > 1 || f.uniform_buffers.size() > 1 || v.push_constant_buffers.size() > 1 ||
      f.push_constant_buffers.size() > 1) {
    return fail(error, "REFLECT_BLOCKS", "pass " + std::to_string(passIndex));
  }

  unsigned bindingMask = 0;
  int uboBinding = -1;
  for (int stage = 0; stage < 2; stage++) {
    spirv_cross::CompilerMSL& compiler = stage == 0 ? vertex : fragment;
    const spirv_cross::ShaderResources& resources = stage == 0 ? v : f;
    if (resources.uniform_buffers.empty()) continue;
    const spirv_cross::Resource& ubo = resources.uniform_buffers[0];
    if (compiler.get_decoration(ubo.id, spv::DecorationDescriptorSet) != 0) {
      return fail(error, "REFLECT_BINDING", "uniform block outside set 0");
    }
    const int binding = static_cast<int>(compiler.get_decoration(ubo.id, spv::DecorationBinding));
    if (uboBinding >= 0 && uboBinding != binding) return fail(error, "REFLECT_BINDING", "uniform block bindings");
    uboBinding = binding;
    const size_t size = compiler.get_declared_struct_size(compiler.get_type(ubo.base_type_id));
    reflection->uboSize = std::max(reflection->uboSize, size);
    reflection->hasUbo = true;
  }
  if (reflection->hasUbo) {
    if (uboBinding < 0 || uboBinding >= static_cast<int>(kMaxBindings)) {
      return fail(error, "REFLECT_BINDING", "uniform block binding " + std::to_string(uboBinding));
    }
    reflection->uboBinding = static_cast<unsigned>(uboBinding);
    bindingMask |= 1u << uboBinding;
  }
  for (int stage = 0; stage < 2; stage++) {
    spirv_cross::CompilerMSL& compiler = stage == 0 ? vertex : fragment;
    const spirv_cross::ShaderResources& resources = stage == 0 ? v : f;
    if (resources.push_constant_buffers.empty()) continue;
    const size_t size =
        compiler.get_declared_struct_size(compiler.get_type(resources.push_constant_buffers[0].base_type_id));
    reflection->pushSize = std::max(reflection->pushSize, size);
    reflection->hasPush = true;
  }
  if (reflection->pushSize > kMaxPushConstantBytes) {
    return fail(error, "REFLECT_PUSH_CONSTANT_SIZE", std::to_string(reflection->pushSize));
  }

  for (int stage = 0; stage < 2; stage++) {
    spirv_cross::CompilerMSL& compiler = stage == 0 ? vertex : fragment;
    const spirv_cross::ShaderResources& resources = stage == 0 ? v : f;
    if (!resources.uniform_buffers.empty() &&
        !addBufferRanges(compiler, resources.uniform_buffers[0], false, maps, passIndex, passCount, lutCount,
                         reflection, error)) {
      return false;
    }
    if (!resources.push_constant_buffers.empty() &&
        !addBufferRanges(compiler, resources.push_constant_buffers[0], true, maps, passIndex, passCount, lutCount,
                         reflection, error)) {
      return false;
    }
  }

  for (const spirv_cross::Resource& image : f.sampled_images) {
    const unsigned set = fragment.get_decoration(image.id, spv::DecorationDescriptorSet);
    const unsigned binding = fragment.get_decoration(image.id, spv::DecorationBinding);
    if (set != 0) return fail(error, "REFLECT_BINDING", image.name + " outside set 0");
    if (binding >= kMaxBindings) return fail(error, "REFLECT_BINDING", image.name + " binding out of range");
    if ((bindingMask & (1u << binding)) != 0) return fail(error, "REFLECT_BINDING", image.name + " binding reused");
    bindingMask |= 1u << binding;
    const spirv_cross::SPIRType& type = fragment.get_type(image.type_id);
    if (!type.array.empty() || type.image.dim != spv::Dim2D || type.image.arrayed || type.image.depth ||
        type.image.ms) {
      return fail(error, "REFLECT_RESOURCE_TYPE", image.name);
    }
    SlangTextureSemantic semantic;
    unsigned index = 0;
    if (!lookupTexture(maps, image.name, false, &semantic, &index)) {
      return fail(error, "REFLECT_TEXTURE_SEMANTIC", image.name);
    }
    if ((semantic == SlangTextureSemantic::PassOutput && index >= passIndex) ||
        (semantic == SlangTextureSemantic::PassFeedback && index >= passCount) ||
        (semantic == SlangTextureSemantic::OriginalHistory && index >= kMaxFrameHistory) ||
        (semantic == SlangTextureSemantic::User && index >= lutCount)) {
      return fail(error, "REFLECT_TEXTURE_SEMANTIC", image.name);
    }
    SlangTextureSlot slot;
    slot.semantic = semantic;
    slot.index = index;
    slot.binding = binding;
    reflection->textures.push_back(slot);
  }
  reflection->uboSize = reflection->hasUbo ? roundUp16(reflection->uboSize) : 0;
  reflection->pushSize = reflection->hasPush ? roundUp16(reflection->pushSize) : 0;
  return true;
}

void bindResources(spirv_cross::CompilerMSL& compiler, spv::ExecutionModel model, const Reflection& reflection,
                   bool fragment) {
  const spirv_cross::ShaderResources resources = compiler.get_shader_resources();
  for (const spirv_cross::Resource& ubo : resources.uniform_buffers) {
    spirv_cross::MSLResourceBinding binding;
    binding.stage = model;
    binding.desc_set = compiler.get_decoration(ubo.id, spv::DecorationDescriptorSet);
    binding.binding = compiler.get_decoration(ubo.id, spv::DecorationBinding);
    binding.msl_buffer = 0;
    compiler.add_msl_resource_binding(binding);
  }
  if (!resources.push_constant_buffers.empty()) {
    spirv_cross::MSLResourceBinding binding;
    binding.stage = model;
    binding.desc_set = spirv_cross::kPushConstDescSet;
    binding.binding = spirv_cross::kPushConstBinding;
    binding.msl_buffer = 1;
    compiler.add_msl_resource_binding(binding);
  }
  if (fragment) {
    for (const SlangTextureSlot& texture : reflection.textures) {
      spirv_cross::MSLResourceBinding binding;
      binding.stage = model;
      binding.desc_set = 0;
      binding.binding = texture.binding;
      binding.msl_texture = texture.binding;
      binding.msl_sampler = texture.binding;
      compiler.add_msl_resource_binding(binding);
    }
  }
}

bool translate(spirv_cross::CompilerMSL& compiler, spv::ExecutionModel model, const SlangCompileOptions& options,
               std::string* msl, std::string* entry, ShaderError* error) {
  try {
    spirv_cross::CompilerMSL::Options mslOptions;
    mslOptions.platform = options.iosPlatform ? spirv_cross::CompilerMSL::Options::iOS
                                              : spirv_cross::CompilerMSL::Options::macOS;
    mslOptions.set_msl_version(options.mslMajor, options.mslMinor);
    mslOptions.pad_fragment_output_components = true;
    compiler.set_msl_options(mslOptions);
    spirv_cross::CompilerGLSL::Options common = compiler.get_common_options();
    common.vertex.flip_vert_y = model == spv::ExecutionModelVertex;
    compiler.set_common_options(common);
    *msl = compiler.compile();
    *entry = compiler.get_cleansed_entry_point_name("main", model);
  } catch (const std::exception& exception) {
    return fail(error, "MSL_FAILED", exception.what());
  }
  return true;
}

}  // namespace

const char* slangSemanticName(SlangSemantic semantic) {
  for (const SemanticName& entry : kSemanticNames) {
    if (entry.semantic == semantic) return entry.name;
  }
  return "?";
}

const char* slangTextureSemanticName(SlangTextureSemantic semantic) {
  for (const TextureName& entry : kTextureNames) {
    if (entry.semantic == semantic) return entry.name;
  }
  return "?";
}

bool compileGLSLToSPIRV(const std::string& source, bool fragment, int defaultVersion, bool coreProfile,
                        unsigned spirvTarget, std::vector<uint32_t>* words, std::string* log) {
  std::lock_guard<std::mutex> lock(glslangLock());
  initializeGlslang();
  static const TBuiltInResource resources = RetroArchResources();
  const EShLanguage language = fragment ? EShLangFragment : EShLangVertex;
  glslang::TShader shader(language);
  const char* text = source.c_str();
  const int length = static_cast<int>(source.size());
  shader.setStringsWithLengths(&text, &length, 1);
  if (spirvTarget != 0) shader.setEnvTarget(glslang::EShTargetSpv, static_cast<glslang::EShTargetLanguageVersion>(spirvTarget));
  const EShMessages messages = static_cast<EShMessages>(EShMsgDefault | EShMsgVulkanRules | EShMsgSpvRules);
  glslang::TShader::ForbidIncluder includer;
  // Slang (RetroArch): parse(resources, 100, false, messages) = no profile,
  // not forward compatible. Dolphin: 450 core, forward compatible.
  const bool parsed = shader.parse(&resources, defaultVersion, coreProfile ? ECoreProfile : ENoProfile, false,
                                   coreProfile, messages, includer);
  if (!parsed) {
    if (log != nullptr) *log = std::string(shader.getInfoLog()) + shader.getInfoDebugLog();
    return false;
  }
  glslang::TProgram program;
  program.addShader(&shader);
  if (!program.link(messages)) {
    if (log != nullptr) *log = std::string(program.getInfoLog()) + program.getInfoDebugLog();
    return false;
  }
  const glslang::TIntermediate* intermediate = program.getIntermediate(language);
  if (intermediate == nullptr) {
    if (log != nullptr) *log = "no intermediate";
    return false;
  }
  std::vector<unsigned int> spirv;
  spv::SpvBuildLogger logger;
  glslang::SpvOptions spvOptions;
  glslang::GlslangToSpv(*intermediate, spirv, &logger, &spvOptions);
  words->assign(spirv.begin(), spirv.end());
  if (log != nullptr) *log = logger.getAllMessages();
  return !words->empty();
}

void countSampleInstructions(const std::vector<uint32_t>& words, unsigned* samples, bool* inLoop,
                             unsigned* instructions) {
  *samples = 0;
  *inLoop = false;
  *instructions = 0;
  if (words.size() < 5) return;
  // Per function: sampling instructions and calls, each marked when it
  // follows a loop header (OpLoopMerge) in the function, so it may run
  // more than once. The entry point's total multiplies every call by its
  // callee's total (GLSL has no recursion): the samples one invocation can
  // take along all of its branches, a lower bound when a loop is involved.
  struct Function {
    unsigned direct = 0;
    bool loopSamples = false;
    std::vector<std::pair<uint32_t, bool>> calls;  // callee, inside a loop
  };
  std::map<uint32_t, Function> functions;
  uint32_t entry = 0;
  uint32_t current = 0;
  bool loopSeen = false;
  size_t position = 5;
  while (position < words.size()) {
    const uint32_t word = words[position];
    const uint32_t count = word >> 16;
    const uint32_t opcode = word & 0xFFFFu;
    if (count == 0 || position + count > words.size()) break;
    (*instructions)++;
    switch (opcode) {
      case 15:  // OpEntryPoint: execution model, function id
        if (entry == 0 && count >= 3) entry = words[position + 2];
        break;
      case 54:  // OpFunction: result type, result id
        if (count >= 3) {
          current = words[position + 2];
          functions[current];
        }
        loopSeen = false;
        break;
      case 56:  // OpFunctionEnd
        current = 0;
        loopSeen = false;
        break;
      case 57:  // OpFunctionCall: result type, result id, function id
        if (current != 0 && count >= 4) functions[current].calls.emplace_back(words[position + 3], loopSeen);
        break;
      case 246:  // OpLoopMerge
        loopSeen = true;
        break;
      case 87: case 88: case 89: case 90: case 91: case 92: case 93: case 94:  // OpImageSample*
      case 95:                                                               // OpImageFetch
      case 96: case 97:                                                      // OpImage(Dref)Gather
        if (current != 0) {
          functions[current].direct++;
          if (loopSeen) functions[current].loopSamples = true;
        }
        break;
      default:
        break;
    }
    position += count;
  }
  std::map<uint32_t, std::pair<unsigned long long, bool>> totals;
  std::function<std::pair<unsigned long long, bool>(uint32_t, unsigned)> total = [&](uint32_t id, unsigned depth) {
    auto known = totals.find(id);
    if (known != totals.end()) return known->second;
    std::pair<unsigned long long, bool> result{0, false};
    auto found = functions.find(id);
    if (found == functions.end() || depth > 64) return result;
    result.first = found->second.direct;
    result.second = found->second.loopSamples;
    for (const auto& call : found->second.calls) {
      const std::pair<unsigned long long, bool> callee = total(call.first, depth + 1);
      result.first += callee.first;
      result.second = result.second || callee.second || (call.second && callee.first > 0);
    }
    if (result.first > 1000000ULL) result.first = 1000000ULL;
    totals[id] = result;
    return result;
  };
  const std::pair<unsigned long long, bool> result = total(entry, 0);
  *samples = static_cast<unsigned>(result.first);
  *inLoop = result.second;
}

bool compileSlangPreset(FileProvider& files, const std::string& presetPath, const SlangCompileOptions& options,
                        CompiledSlangPreset* compiled, ShaderError* error) {
  *compiled = CompiledSlangPreset();
  if (!loadSlangPreset(files, presetPath, &compiled->preset, error)) return false;
  const SlangPreset& preset = compiled->preset;
  const unsigned passCount = static_cast<unsigned>(preset.passes.size());

  std::vector<SlangSource> sources(passCount);
  for (unsigned index = 0; index < passCount; index++) {
    if (!loadSlangSource(files, preset.passes[index].shader, &sources[index], error)) return false;
  }

  // video_shader_resolve_parameters: first declaration across passes.
  for (const SlangSource& source : sources) {
    for (const SlangParameter& parameter : source.parameters) {
      bool known = false;
      for (const CompiledSlangParameter& existing : compiled->parameters) {
        known = known || existing.declaration.id == parameter.id;
      }
      if (known) continue;
      CompiledSlangParameter entry;
      entry.declaration = parameter;
      entry.value = parameter.initial;
      float value = 0.0f;
      if (preset.parameterValue(parameter.id, &value)) entry.value = value;
      compiled->parameters.push_back(entry);
    }
  }

  compiled->aliases.resize(passCount);
  for (unsigned index = 0; index < passCount; index++) compiled->aliases[index] = preset.passes[index].alias;
  compiled->feedback.assign(passCount, false);

  NameMaps maps;
  for (const CompiledSlangParameter& parameter : compiled->parameters) maps.parameters.push_back(parameter.declaration.id);

  for (unsigned index = 0; index < passCount; index++) {
    const SlangSource& source = sources[index];
    // slang_process: an unnamed pass takes the shader's "#pragma name".
    if (compiled->aliases[index].empty() && !source.name.empty()) compiled->aliases[index] = source.name;

    maps.textures.clear();
    maps.sizes.clear();
    for (unsigned pass = 0; pass < passCount; pass++) {
      const std::string& alias = compiled->aliases[pass];
      if (alias.empty()) continue;
      if (!addUnique(&maps.textures, alias, SlangTextureSemantic::PassOutput, pass) ||
          !addUnique(&maps.sizes, alias + "Size", SlangTextureSemantic::PassOutput, pass) ||
          !addUnique(&maps.textures, alias + "Feedback", SlangTextureSemantic::PassFeedback, pass) ||
          !addUnique(&maps.sizes, alias + "FeedbackSize", SlangTextureSemantic::PassFeedback, pass)) {
        return fail(error, "REFLECT_TEXTURE_SEMANTIC", "duplicate pass name " + alias);
      }
    }
    for (unsigned lut = 0; lut < preset.textures.size(); lut++) {
      const std::string& name = preset.textures[lut].name;
      if (!addUnique(&maps.textures, name, SlangTextureSemantic::User, lut) ||
          !addUnique(&maps.sizes, name + "Size", SlangTextureSemantic::User, lut)) {
        return fail(error, "REFLECT_TEXTURE_SEMANTIC", "duplicate texture name " + name);
      }
    }

    std::vector<uint32_t> vertexWords, fragmentWords;
    std::string log;
    if (!compileGLSLToSPIRV(source.vertex, false, 100, false, 0, &vertexWords, &log)) {
      return fail(error, "GLSL_VERTEX_FAILED", source.path + "\n" + log);
    }
    if (!compileGLSLToSPIRV(source.fragment, true, 100, false, 0, &fragmentWords, &log)) {
      return fail(error, "GLSL_FRAGMENT_FAILED", source.path + "\n" + log);
    }

    CompiledSlangPass pass;
    countSampleInstructions(fragmentWords, &pass.sampleInstructions, &pass.samplesInLoop, &pass.spirvInstructions);
    try {
      spirv_cross::CompilerMSL vertex(std::move(vertexWords));
      spirv_cross::CompilerMSL fragment(std::move(fragmentWords));
      Reflection reflection;
      if (!reflectPass(vertex, fragment, maps, index, passCount, static_cast<unsigned>(preset.textures.size()),
                       &reflection, error)) {
        if (error != nullptr) error->detail = source.path + ": " + error->detail;
        return false;
      }
      bindResources(vertex, spv::ExecutionModelVertex, reflection, false);
      bindResources(fragment, spv::ExecutionModelFragment, reflection, true);
      if (!translate(vertex, spv::ExecutionModelVertex, options, &pass.vertexMSL, &pass.vertexEntry, error) ||
          !translate(fragment, spv::ExecutionModelFragment, options, &pass.fragmentMSL, &pass.fragmentEntry, error)) {
        if (error != nullptr) error->detail = source.path + ": " + error->detail;
        return false;
      }
      pass.uboSize = reflection.uboSize;
      pass.pushSize = reflection.pushSize;
      pass.uniforms = reflection.uniforms;
      pass.textures = reflection.textures;
    } catch (const std::exception& exception) {
      return fail(error, "MSL_FAILED", source.path + ": " + exception.what());
    }

    // Render target format: "#pragma format", overridden by the preset's
    // framebuffer flags when the pass has an explicit scale (RetroArch).
    const SlangPass& description = preset.passes[index];
    pass.explicitFormat = source.format != SlangFormat::Unknown;
    pass.format = pass.explicitFormat ? source.format : SlangFormat::R8G8B8A8_UNORM;
    if (description.scaleSet) {
      if (description.srgbFramebuffer) {
        pass.format = SlangFormat::R8G8B8A8_SRGB;
      } else if (description.floatFramebuffer) {
        pass.format = SlangFormat::R16G16B16A16_SFLOAT;
      } else if (description.rgb10Framebuffer) {
        pass.format = SlangFormat::A2B10G10R10_UNORM_PACK32;
      }
    }
    for (const SlangTextureSlot& texture : pass.textures) {
      if (texture.semantic == SlangTextureSemantic::OriginalHistory) {
        compiled->historyDepth = std::max(compiled->historyDepth, texture.index);
      }
      if (texture.semantic == SlangTextureSemantic::PassFeedback) compiled->feedback[texture.index] = true;
    }
    for (const SlangUniformSlot& uniform : pass.uniforms) {
      if (uniform.kind != SlangUniformSlot::Kind::TextureSize) continue;
      if (uniform.textureSemantic == SlangTextureSemantic::OriginalHistory) {
        compiled->historyDepth = std::max(compiled->historyDepth, uniform.index);
      }
    }
    compiled->passes.push_back(std::move(pass));
  }

  std::set<std::string> closure(preset.presetFiles.begin(), preset.presetFiles.end());
  for (const SlangSource& source : sources) closure.insert(source.files.begin(), source.files.end());
  for (const SlangTexture& texture : preset.textures) closure.insert(texture.path);
  compiled->files.assign(closure.begin(), closure.end());
  return true;
}

}  // namespace neoshader
