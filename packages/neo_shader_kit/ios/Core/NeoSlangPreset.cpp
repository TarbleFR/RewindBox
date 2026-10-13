// SPDX-License-Identifier: GPL-3.0-or-later
#include "NeoSlangPreset.hpp"

#include <cmath>
#include <functional>

#include "NeoShaderPaths.hpp"

namespace neoshader {

namespace {

bool fail(ShaderError* error, const char* code, const std::string& detail) {
  if (error != nullptr) {
    error->code = code;
    error->detail = detail;
  }
  return false;
}

bool readConfig(FileProvider& files, const std::string& path, ConfigFile* config, ShaderError* error) {
  std::string text;
  if (!isSafeRelativePath(path)) return fail(error, "PRESET_UNSAFE_PATH", path);
  if (!files.read(path, &text)) return fail(error, "PRESET_UNREADABLE", path);
  *config = ConfigFile::parse(text);
  return true;
}

/// fill_pathname_expanded_and_absolute + video_shader_replace_wildcards: a
/// path relative to the preset that names it. Wildcards ("$GAME$"...) are
/// refused: NeoStation would have to invent their values.
bool resolveIn(const std::string& presetPath, const std::string& reference, std::string* out,
               ShaderError* error) {
  if (reference.find('$') != std::string::npos) {
    return fail(error, "PRESET_UNSAFE_PATH", presetPath + ": wildcard path " + reference);
  }
  if (!resolveRelative(presetPath, reference, out)) {
    return fail(error, "PRESET_UNSAFE_PATH", presetPath + ": " + reference);
  }
  return true;
}

WrapMode wrapFromString(const std::string& text) {
  // video_shader_wrap_str_to_mode: unknown strings fall back to the default.
  if (text == "clamp_to_edge") return WrapMode::ClampToEdge;
  if (text == "repeat") return WrapMode::Repeat;
  if (text == "mirrored_repeat") return WrapMode::MirroredRepeat;
  return WrapMode::ClampToBorder;
}

bool scaleTypeFromString(const std::string& text, bool prefixOnly, ScaleType* type) {
  // RetroArch compares scale_type_x with memcmp on the keyword length
  // (so "source2" is "source") and scale_type_y with strcmp.
  auto matches = [&](const char* keyword) {
    const std::string word(keyword);
    return prefixOnly ? text.compare(0, word.size(), word) == 0 : text == word;
  };
  if (matches("source")) {
    *type = ScaleType::Source;
  } else if (matches("viewport")) {
    *type = ScaleType::Viewport;
  } else if (matches("absolute")) {
    *type = ScaleType::Absolute;
  } else {
    return false;
  }
  return true;
}

std::string indexed(const char* key, unsigned index) { return std::string(key) + std::to_string(index); }

bool parsePass(const ConfigFile& config, const std::string& presetPath, unsigned index, SlangPass* pass,
               ShaderError* error) {
  const std::string* shader = config.find(indexed("shader", index));
  if (shader == nullptr || shader->empty()) {
    return fail(error, "PRESET_PASS_MISSING", presetPath + ": shader" + std::to_string(index));
  }
  if (!resolveIn(presetPath, *shader, &pass->shader, error)) return false;

  bool flag = false;
  if (config.getBool(indexed("filter_linear", index), &flag)) {
    pass->filter = flag ? FilterMode::Linear : FilterMode::Nearest;
  }
  if (const std::string* wrap = config.find(indexed("wrap_mode", index))) {
    if (!wrap->empty()) pass->wrap = wrapFromString(*wrap);
  }
  if (const std::string* modulo = config.find(indexed("frame_count_mod", index))) {
    if (!modulo->empty()) pass->frameCountMod = static_cast<unsigned>(std::strtoul(modulo->c_str(), nullptr, 0));
  }
  if (config.getBool(indexed("srgb_framebuffer", index), &flag)) pass->srgbFramebuffer = flag;
  if (config.getBool(indexed("float_framebuffer", index), &flag)) pass->floatFramebuffer = flag;
  if (config.getBool(indexed("rgb10_framebuffer", index), &flag)) pass->rgb10Framebuffer = flag;
  if (config.getBool(indexed("mipmap_input", index), &flag)) pass->mipmapInput = flag;
  if (const std::string* alias = config.find(indexed("alias", index))) pass->alias = *alias;

  std::string scaleType, scaleTypeX, scaleTypeY;
  if (const std::string* value = config.find(indexed("scale_type", index))) scaleType = *value;
  if (const std::string* value = config.find(indexed("scale_type_x", index))) scaleTypeX = *value;
  if (const std::string* value = config.find(indexed("scale_type_y", index))) scaleTypeY = *value;
  if (!scaleType.empty()) {
    scaleTypeX = scaleType;
    scaleTypeY = scaleType;
  } else if (scaleTypeX.empty() && scaleTypeY.empty()) {
    return true;
  }
  pass->scaleSet = true;
  pass->scaleTypeX = ScaleType::Source;
  pass->scaleTypeY = ScaleType::Source;
  if (!scaleTypeX.empty() && !scaleTypeFromString(scaleTypeX, true, &pass->scaleTypeX)) {
    return fail(error, "PRESET_BAD_SCALE", presetPath + ": scale_type_x" + std::to_string(index) + " = " + scaleTypeX);
  }
  if (!scaleTypeY.empty() && !scaleTypeFromString(scaleTypeY, false, &pass->scaleTypeY)) {
    return fail(error, "PRESET_BAD_SCALE", presetPath + ": scale_type_y" + std::to_string(index) + " = " + scaleTypeY);
  }

  auto readAxis = [&](ScaleType type, const char* axisKey, float* scale, unsigned* absolute) {
    const std::string common = indexed("scale", index);
    const std::string axis = indexed(axisKey, index);
    if (type == ScaleType::Absolute) {
      int integer = 0;
      float number = 0.0f;
      if (config.getInt(common, &integer)) {
        *absolute = static_cast<unsigned>(integer);
      } else if (config.getFloat(common, &number)) {
        *absolute = static_cast<unsigned>(std::lround(number));
      } else if (config.getInt(axis, &integer)) {
        *absolute = static_cast<unsigned>(integer);
      } else if (config.getFloat(axis, &number)) {
        *absolute = static_cast<unsigned>(std::lround(number));
      }
    } else {
      float number = 0.0f;
      if (config.getFloat(common, &number)) {
        *scale = number;
      } else if (config.getFloat(axis, &number)) {
        *scale = number;
      }
    }
  };
  readAxis(pass->scaleTypeX, "scale_x", &pass->scaleX, &pass->absoluteX);
  readAxis(pass->scaleTypeY, "scale_y", &pass->scaleY, &pass->absoluteY);
  if (!std::isfinite(pass->scaleX) || !std::isfinite(pass->scaleY) || pass->scaleX <= 0.0f ||
      pass->scaleY <= 0.0f) {
    return fail(error, "PRESET_BAD_SCALE", presetPath + ": scale of pass " + std::to_string(index));
  }
  return true;
}

bool parseTextures(const ConfigFile& config, const std::string& presetPath, std::vector<SlangTexture>* textures,
                   ShaderError* error) {
  const std::string* list = config.find("textures");
  if (list == nullptr) return true;
  size_t start = 0;
  while (start <= list->size()) {
    size_t end = list->find(';', start);
    if (end == std::string::npos) end = list->size();
    std::string name = list->substr(start, end - start);
    start = end + 1;
    if (name.empty()) continue;
    if (name.size() > 63) name.resize(63);
    if (textures->size() >= kMaxTextures) return fail(error, "PRESET_TOO_MANY_TEXTURES", presetPath);
    const std::string* path = config.find(name);
    if (path == nullptr || path->empty()) return fail(error, "PRESET_TEXTURE_MISSING", presetPath + ": " + name);
    SlangTexture texture;
    texture.name = name;
    if (!resolveIn(presetPath, *path, &texture.path, error)) return false;
    bool flag = false;
    if (config.getBool(name + "_linear", &flag)) texture.filter = flag ? FilterMode::Linear : FilterMode::Nearest;
    if (config.getBool(name + "_mipmap", &flag)) texture.mipmap = flag;
    if (const std::string* wrap = config.find(name + "_wrap_mode")) {
      if (!wrap->empty()) texture.wrap = wrapFromString(*wrap);
    }
    textures->push_back(texture);
  }
  return true;
}

bool loadRootConfig(const ConfigFile& config, const std::string& path, SlangPreset* preset, ShaderError* error) {
  unsigned count = 0;
  if (!config.getUnsigned("shaders", &count) || count == 0) return fail(error, "PRESET_NO_PASSES", path);
  if (count > kMaxPasses) return fail(error, "PRESET_TOO_MANY_PASSES", path + ": " + std::to_string(count));
  int feedback = -1;
  preset->feedbackPass = config.getInt("feedback_pass", &feedback) ? feedback : -1;
  preset->passes.clear();
  for (unsigned index = 0; index < count; index++) {
    SlangPass pass;
    if (!parsePass(config, path, index, &pass, error)) return false;
    preset->passes.push_back(pass);
  }
  preset->textures.clear();
  return parseTextures(config, path, &preset->textures, error);
}

}  // namespace

const char* scaleTypeName(ScaleType type) {
  switch (type) {
    case ScaleType::Source:
      return "source";
    case ScaleType::Viewport:
      return "viewport";
    case ScaleType::Absolute:
      return "absolute";
  }
  return "source";
}

const char* wrapModeName(WrapMode mode) {
  switch (mode) {
    case WrapMode::ClampToBorder:
      return "clamp_to_border";
    case WrapMode::ClampToEdge:
      return "clamp_to_edge";
    case WrapMode::Repeat:
      return "repeat";
    case WrapMode::MirroredRepeat:
      return "mirrored_repeat";
  }
  return "clamp_to_border";
}

bool SlangPreset::parameterValue(const std::string& id, float* value) const {
  bool found = false;
  for (const ConfigFile& config : parameterConfigs) {
    float number = 0.0f;
    if (config.has(id) && config.getFloat(id, &number)) {
      *value = number;
      found = true;
    }
  }
  return found;
}

bool loadSlangPreset(FileProvider& files, const std::string& path, SlangPreset* preset, ShaderError* error) {
  *preset = SlangPreset();
  preset->loadedPath = path;
  std::vector<std::string> read;
  auto remember = [&](const std::string& file) {
    for (const std::string& known : read) {
      if (known == file) return;
    }
    read.push_back(file);
  };

  // video_shader_get_root_preset_config: follow the first reference.
  ConfigFile loaded;
  if (!readConfig(files, path, &loaded, error)) return false;
  remember(path);
  std::string rootPath = path;
  ConfigFile root = loaded;
  for (unsigned depth = 1; !root.references().empty(); depth++) {
    if (depth > kMaxReferenceDepth) return fail(error, "PRESET_REFERENCE_DEPTH", path);
    std::string next;
    if (!resolveIn(rootPath, root.references().front(), &next, error)) return false;
    if (!readConfig(files, next, &root, error)) return false;
    rootPath = next;
    remember(next);
  }
  if (!root.has("shaders")) return fail(error, "PRESET_NO_PASSES", rootPath);
  preset->rootPath = rootPath;

  if (rootPath == path) {
    if (!loadRootConfig(root, rootPath, preset, error)) return false;
    preset->parameterConfigs.push_back(root);
    preset->presetFiles = read;
    return true;
  }

  // Additional references of the loaded preset may only carry overrides.
  for (size_t index = 1; index < loaded.references().size(); index++) {
    std::string other;
    if (!resolveIn(path, loaded.references()[index], &other, error)) return false;
    ConfigFile otherRoot;
    std::string otherRootPath = other;
    if (!readConfig(files, other, &otherRoot, error)) return false;
    for (unsigned depth = 1; !otherRoot.references().empty(); depth++) {
      if (depth > kMaxReferenceDepth) return fail(error, "PRESET_REFERENCE_DEPTH", other);
      std::string next;
      if (!resolveIn(otherRootPath, otherRoot.references().front(), &next, error)) return false;
      if (!readConfig(files, next, &otherRoot, error)) return false;
      otherRootPath = next;
    }
    if (otherRoot.has("shaders")) return fail(error, "PRESET_REFERENCE_CHAIN", path + ": " + other);
  }

  if (!loadRootConfig(root, rootPath, preset, error)) return false;
  preset->parameterConfigs.push_back(root);

  // video_shader_gather_reference_path_list: every preset of every chain,
  // deepest first, the loaded preset last; each applies its overrides.
  std::vector<std::string> order;
  std::function<bool(const std::string&, unsigned)> gather = [&](const std::string& current, unsigned depth) {
    if (depth > kMaxReferenceDepth) return true;  // RetroArch stops silently at the limit
    ConfigFile config;
    if (!readConfig(files, current, &config, error)) return false;
    remember(current);
    for (const std::string& reference : config.references()) {
      std::string next;
      if (!resolveIn(current, reference, &next, error)) return false;
      if (!gather(next, depth + 1)) return false;
    }
    order.push_back(current);
    return true;
  };
  if (!gather(path, 0)) return false;
  for (const std::string& current : order) {
    ConfigFile config;
    if (!readConfig(files, current, &config, error)) return false;
    preset->parameterConfigs.push_back(config);
    for (SlangTexture& texture : preset->textures) {
      const std::string* overridden = config.find(texture.name);
      if (overridden == nullptr || overridden->empty()) continue;
      if (!resolveIn(current, *overridden, &texture.path, error)) return false;
    }
  }
  preset->presetFiles = read;
  return true;
}

}  // namespace neoshader
