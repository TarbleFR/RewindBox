// SPDX-License-Identifier: GPL-3.0-or-later
// RetroArch .slangp presets (gfx/video_shader_parse.c), read the way
// RetroArch reads them: passes, scales, framebuffer formats, LUT textures,
// "#reference" chains and their parameter / texture overrides.
#pragma once

#include <string>
#include <vector>

#include "NeoShaderConfig.hpp"
#include "NeoShaderFiles.hpp"

namespace neoshader {

/// RetroArch's GFX_MAX_SHADERS / GFX_MAX_TEXTURES and reference depth.
constexpr unsigned kMaxPasses = 64;
constexpr unsigned kMaxTextures = 64;
constexpr unsigned kMaxReferenceDepth = 16;

enum class ScaleType { Source, Viewport, Absolute };
enum class FilterMode { Unspecified, Nearest, Linear };
enum class WrapMode { ClampToBorder, ClampToEdge, Repeat, MirroredRepeat };

const char* scaleTypeName(ScaleType type);
const char* wrapModeName(WrapMode mode);

struct SlangPass {
  /// Repository-relative path of the .slang file.
  std::string shader;
  /// filter_linear#: how this pass samples its input (Source, and Original
  /// for pass 0). Unspecified follows the "smooth picture" setting.
  FilterMode filter = FilterMode::Unspecified;
  /// wrap_mode#: address mode of this pass's input. RetroArch's default is
  /// clamp_to_border (transparent black outside the picture).
  WrapMode wrap = WrapMode::ClampToBorder;
  unsigned frameCountMod = 0;
  bool srgbFramebuffer = false;
  bool floatFramebuffer = false;
  bool rgb10Framebuffer = false;
  /// mipmap_input#: this pass reads its input with mipmaps, so the previous
  /// pass output gets a full mip chain.
  bool mipmapInput = false;
  std::string alias;
  /// A scale_type was given (scale_type#, scale_type_x#, scale_type_y#).
  /// Without one: source x1, or viewport x1 for the last pass.
  bool scaleSet = false;
  ScaleType scaleTypeX = ScaleType::Source;
  ScaleType scaleTypeY = ScaleType::Source;
  float scaleX = 1.0f;
  float scaleY = 1.0f;
  unsigned absoluteX = 0;
  unsigned absoluteY = 0;
};

struct SlangTexture {
  std::string name;
  std::string path;
  FilterMode filter = FilterMode::Unspecified;
  bool mipmap = false;
  WrapMode wrap = WrapMode::ClampToBorder;
};

struct SlangPreset {
  /// The preset that was asked for, and the full preset at the end of its
  /// first "#reference" chain (the same file when there is none).
  std::string loadedPath;
  std::string rootPath;
  std::vector<SlangPass> passes;
  std::vector<SlangTexture> textures;
  int feedbackPass = -1;
  /// Configs whose entries set parameter values, in the order RetroArch
  /// applies them (root first, then every preset of the reference chains in
  /// post-order, the loaded one last): a later config wins.
  std::vector<ConfigFile> parameterConfigs;
  /// Every preset file read (the download closure needs them all).
  std::vector<std::string> presetFiles;

  /// Value the preset chain gives to parameter `id`, if any.
  bool parameterValue(const std::string& id, float* value) const;
};

/// Loads `path` and its reference chain. On failure `error->code` is one of:
/// PRESET_UNREADABLE, PRESET_REFERENCE_DEPTH, PRESET_REFERENCE_CHAIN (a later
/// #reference names a full preset), PRESET_NO_PASSES, PRESET_TOO_MANY_PASSES,
/// PRESET_PASS_MISSING, PRESET_BAD_SCALE, PRESET_TEXTURE_MISSING,
/// PRESET_TOO_MANY_TEXTURES, PRESET_UNSAFE_PATH (absolute path, backslash,
/// path leaving the shader root, or a RetroArch "$WILDCARD$" path).
bool loadSlangPreset(FileProvider& files, const std::string& path, SlangPreset* preset, ShaderError* error);

}  // namespace neoshader
