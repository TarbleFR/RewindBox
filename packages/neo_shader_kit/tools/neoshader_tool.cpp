// SPDX-License-Identifier: GPL-3.0-or-later
// Command-line front end of the shader kit's portable core, for the catalog
// generator and the CI checks (Linux and macOS). Prints JSON.
//
//   neoshader-tool slang ROOT PRESET [--msl DIR] [--macos]
//   neoshader-tool slang-batch ROOT LIST_FILE OUTPUT_JSONL [--macos] [--msl-tree DIR]
//   neoshader-tool dolphin FILE [--msl DIR] [--macos]
//
// --msl-tree writes the MSL of every pass of every compiled preset once per
// distinct source, as DIR/<16 hex digits of its FNV-1a hash>.<stage>.metal,
// for an offline Metal compiler run (the iPhone toolchain in CI).
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>

#include "NeoDolphinPostProcess.hpp"
#include "NeoShaderFiles.hpp"
#include "NeoShaderPaths.hpp"
#include "NeoSlangCompiler.hpp"

using namespace neoshader;

namespace {

std::string quote(const std::string& text) {
  std::string result = "\"";
  for (unsigned char character : text) {
    switch (character) {
      case '"':
        result += "\\\"";
        break;
      case '\\':
        result += "\\\\";
        break;
      case '\n':
        result += "\\n";
        break;
      case '\r':
        result += "\\r";
        break;
      case '\t':
        result += "\\t";
        break;
      default:
        if (character < 0x20) {
          char buffer[8];
          std::snprintf(buffer, sizeof(buffer), "\\u%04x", character);
          result += buffer;
        } else {
          result += static_cast<char>(character);
        }
    }
  }
  return result + "\"";
}

std::string number(double value) {
  std::ostringstream stream;
  stream.imbue(std::locale::classic());
  stream.precision(9);
  stream << value;
  return stream.str();
}

const char* filterName(FilterMode filter) {
  switch (filter) {
    case FilterMode::Linear:
      return "linear";
    case FilterMode::Nearest:
      return "nearest";
    case FilterMode::Unspecified:
      break;
  }
  return "unspecified";
}

std::string errorJson(const ShaderError& error) {
  return "{\"code\":" + quote(error.code) + ",\"detail\":" + quote(error.detail) + "}";
}

std::string slangJson(const std::string& preset, bool ok, const CompiledSlangPreset& compiled,
                      const ShaderError& error) {
  std::string json = "{\"preset\":" + quote(preset) + ",\"ok\":" + (ok ? "true" : "false");
  if (!ok) return json + ",\"error\":" + errorJson(error) + "}";
  json += ",\"root\":" + quote(compiled.preset.rootPath);
  json += ",\"historyDepth\":" + std::to_string(compiled.historyDepth);
  json += ",\"feedbackPass\":" + std::to_string(compiled.preset.feedbackPass);
  json += ",\"passes\":[";
  for (size_t index = 0; index < compiled.passes.size(); index++) {
    const SlangPass& description = compiled.preset.passes[index];
    const CompiledSlangPass& pass = compiled.passes[index];
    if (index > 0) json += ",";
    json += "{\"shader\":" + quote(description.shader);
    json += ",\"alias\":" + quote(compiled.aliases[index]);
    json += ",\"filter\":" + quote(filterName(description.filter));
    json += ",\"wrap\":" + quote(wrapModeName(description.wrap));
    json += ",\"mipmapInput\":" + std::string(description.mipmapInput ? "true" : "false");
    json += ",\"frameCountMod\":" + std::to_string(description.frameCountMod);
    json += ",\"scaleSet\":" + std::string(description.scaleSet ? "true" : "false");
    json += ",\"scaleTypeX\":" + quote(scaleTypeName(description.scaleTypeX));
    json += ",\"scaleTypeY\":" + quote(scaleTypeName(description.scaleTypeY));
    json += ",\"scaleX\":" + number(description.scaleX) + ",\"scaleY\":" + number(description.scaleY);
    json += ",\"absoluteX\":" + std::to_string(description.absoluteX);
    json += ",\"absoluteY\":" + std::to_string(description.absoluteY);
    json += ",\"format\":" + quote(slangFormatName(pass.format));
    json += ",\"feedback\":" + std::string(compiled.feedback[index] ? "true" : "false");
    json += ",\"uboSize\":" + std::to_string(pass.uboSize) + ",\"pushSize\":" + std::to_string(pass.pushSize);
    json += ",\"samples\":" + std::to_string(pass.sampleInstructions);
    json += ",\"samplesInLoop\":" + std::string(pass.samplesInLoop ? "true" : "false");
    json += ",\"spirvInstructions\":" + std::to_string(pass.spirvInstructions);
    json += ",\"textures\":[";
    for (size_t slot = 0; slot < pass.textures.size(); slot++) {
      if (slot > 0) json += ",";
      json += "{\"semantic\":" + quote(slangTextureSemanticName(pass.textures[slot].semantic)) +
              ",\"index\":" + std::to_string(pass.textures[slot].index) +
              ",\"binding\":" + std::to_string(pass.textures[slot].binding) + "}";
    }
    json += "],\"uniforms\":[";
    for (size_t slot = 0; slot < pass.uniforms.size(); slot++) {
      const SlangUniformSlot& uniform = pass.uniforms[slot];
      if (slot > 0) json += ",";
      std::string name;
      if (uniform.kind == SlangUniformSlot::Kind::Semantic) {
        name = slangSemanticName(uniform.semantic);
      } else if (uniform.kind == SlangUniformSlot::Kind::TextureSize) {
        name = std::string(slangTextureSemanticName(uniform.textureSemantic)) + "Size" + std::to_string(uniform.index);
      } else {
        name = compiled.parameters[uniform.index].declaration.id;
      }
      json += "{\"name\":" + quote(name) + ",\"ubo\":" + std::to_string(uniform.uboOffset) +
              ",\"push\":" + std::to_string(uniform.pushOffset) + "}";
    }
    json += "]}";
  }
  json += "],\"textures\":[";
  for (size_t index = 0; index < compiled.preset.textures.size(); index++) {
    const SlangTexture& texture = compiled.preset.textures[index];
    if (index > 0) json += ",";
    json += "{\"name\":" + quote(texture.name) + ",\"path\":" + quote(texture.path) +
            ",\"filter\":" + quote(filterName(texture.filter)) + ",\"mipmap\":" + (texture.mipmap ? "true" : "false") +
            ",\"wrap\":" + quote(wrapModeName(texture.wrap)) + "}";
  }
  json += "],\"parameters\":[";
  for (size_t index = 0; index < compiled.parameters.size(); index++) {
    const CompiledSlangParameter& parameter = compiled.parameters[index];
    if (index > 0) json += ",";
    json += "{\"id\":" + quote(parameter.declaration.id) + ",\"description\":" + quote(parameter.declaration.description) +
            ",\"initial\":" + number(parameter.declaration.initial) + ",\"minimum\":" +
            number(parameter.declaration.minimum) + ",\"maximum\":" + number(parameter.declaration.maximum) +
            ",\"step\":" + number(parameter.declaration.step) + ",\"value\":" + number(parameter.value) + "}";
  }
  json += "],\"files\":[";
  for (size_t index = 0; index < compiled.files.size(); index++) {
    if (index > 0) json += ",";
    json += quote(compiled.files[index]);
  }
  return json + "]}";
}

bool writeFile(const std::string& path, const std::string& contents) {
  std::ofstream stream(path, std::ios::binary);
  stream << contents;
  return static_cast<bool>(stream);
}

int slang(const std::string& root, const std::string& preset, const std::string& mslDirectory, bool macos) {
  DirectoryFileProvider files(root);
  SlangCompileOptions options;
  options.iosPlatform = !macos;
  CompiledSlangPreset compiled;
  ShaderError error;
  const bool ok = compileSlangPreset(files, preset, options, &compiled, &error);
  std::cout << slangJson(preset, ok, compiled, error) << std::endl;
  if (ok && !mslDirectory.empty()) {
    for (size_t index = 0; index < compiled.passes.size(); index++) {
      const std::string base = mslDirectory + "/pass" + std::to_string(index);
      if (!writeFile(base + ".vertex.metal", compiled.passes[index].vertexMSL) ||
          !writeFile(base + ".fragment.metal", compiled.passes[index].fragmentMSL)) {
        std::cerr << "cannot write " << base << std::endl;
        return 2;
      }
    }
  }
  return ok ? 0 : 1;
}

/// FNV-1a 64-bit: names the distinct MSL sources of --msl-tree.
std::string sourceName(const std::string& text) {
  unsigned long long hash = 1469598103934665603ULL;
  for (unsigned char character : text) {
    hash ^= character;
    hash *= 1099511628211ULL;
  }
  char buffer[17];
  std::snprintf(buffer, sizeof(buffer), "%016llx", hash);
  return buffer;
}

int slangBatch(const std::string& root, const std::string& list, const std::string& output, bool macos,
               const std::string& mslTree) {
  std::ifstream input(list);
  std::ofstream out(output, std::ios::binary);
  if (!input || !out) {
    std::cerr << "cannot open " << list << " or " << output << std::endl;
    return 2;
  }
  DirectoryFileProvider files(root);
  SlangCompileOptions options;
  options.iosPlatform = !macos;
  std::string preset;
  unsigned total = 0, passed = 0;
  while (std::getline(input, preset)) {
    if (preset.empty()) continue;
    CompiledSlangPreset compiled;
    ShaderError error;
    const bool ok = compileSlangPreset(files, preset, options, &compiled, &error);
    std::string json = slangJson(preset, ok, compiled, error);
    total++;
    if (ok) passed++;
    if (ok && !mslTree.empty()) {
      // "msl": the --msl-tree names of each pass ([vertex, fragment]).
      std::string names = ",\"msl\":[";
      for (size_t index = 0; index < compiled.passes.size(); index++) {
        const CompiledSlangPass& pass = compiled.passes[index];
        const std::string vertexName = sourceName(pass.vertexMSL);
        const std::string fragmentName = sourceName(pass.fragmentMSL);
        if (!writeFile(mslTree + "/" + vertexName + ".vertex.metal", pass.vertexMSL) ||
            !writeFile(mslTree + "/" + fragmentName + ".fragment.metal", pass.fragmentMSL)) {
          std::cerr << "cannot write into " << mslTree << std::endl;
          return 2;
        }
        names += std::string(index > 0 ? "," : "") + "[" + quote(vertexName) + "," + quote(fragmentName) + "]";
      }
      json.insert(json.size() - 1, names + "]");
    }
    out << json << "\n";
  }
  std::cerr << passed << "/" << total << " presets compiled" << std::endl;
  return 0;
}

int dolphin(const std::string& path, const std::string& mslDirectory, bool macos) {
  std::ifstream input(path, std::ios::binary);
  if (!input) {
    std::cerr << "cannot read " << path << std::endl;
    return 2;
  }
  std::stringstream buffer;
  buffer << input.rdbuf();
  DolphinPostProcessShader shader;
  ShaderError error;
  DolphinTranslateOptions options;
  options.iosPlatform = !macos;
  const bool ok = translateDolphinPostProcess(buffer.str(), options, &shader, &error);
  std::string json = "{\"file\":" + quote(path) + ",\"ok\":" + (ok ? "true" : "false");
  if (!ok) {
    json += ",\"error\":" + errorJson(error);
  } else {
    json += ",\"samples\":" + std::to_string(shader.sampleInstructions) +
            ",\"samplesInLoop\":" + std::string(shader.samplesInLoop ? "true" : "false") +
            ",\"uniformBytes\":" + std::to_string(shader.uniformBytes) + ",\"options\":[";
    for (size_t index = 0; index < shader.options.size(); index++) {
      const DolphinOption& option = shader.options[index];
      if (index > 0) json += ",";
      json += "{\"name\":" + quote(option.name) + ",\"gui\":" + quote(option.guiName) +
              ",\"type\":" + quote(dolphinOptionTypeName(option.type)) + ",\"dependent\":" + quote(option.dependentOption) +
              ",\"offset\":" + std::to_string(option.uniformOffset) + ",\"values\":[";
      for (size_t value = 0; value < option.values.size(); value++) {
        json += (value > 0 ? "," : "") + number(option.values[value]);
      }
      json += "],\"minimum\":[";
      for (size_t value = 0; value < option.minimums.size(); value++) {
        json += (value > 0 ? "," : "") + number(option.minimums[value]);
      }
      json += "],\"maximum\":[";
      for (size_t value = 0; value < option.maximums.size(); value++) {
        json += (value > 0 ? "," : "") + number(option.maximums[value]);
      }
      json += "],\"step\":[";
      for (size_t value = 0; value < option.steps.size(); value++) {
        json += (value > 0 ? "," : "") + number(option.steps[value]);
      }
      json += "]}";
    }
    json += "]";
  }
  std::cout << json << "}" << std::endl;
  if (ok && !mslDirectory.empty()) {
    if (!writeFile(mslDirectory + "/fragment.metal", shader.fragmentMSL) ||
        !writeFile(mslDirectory + "/vertex.metal", shader.vertexMSL)) {
      return 2;
    }
  }
  return ok ? 0 : 1;
}

}  // namespace

int main(int argc, char** argv) {
  if (argc < 3) {
    std::cerr << "usage: neoshader-tool slang ROOT PRESET [--msl DIR] [--macos]\n"
                 "       neoshader-tool slang-batch ROOT LIST OUTPUT [--macos] [--msl-tree DIR]\n"
                 "       neoshader-tool dolphin FILE [--msl DIR] [--macos]"
              << std::endl;
    return 2;
  }
  const std::string command = argv[1];
  std::string msl;
  std::string mslTree;
  bool macos = false;
  for (int index = 2; index < argc; index++) {
    if (std::strcmp(argv[index], "--msl") == 0 && index + 1 < argc) msl = argv[index + 1];
    if (std::strcmp(argv[index], "--msl-tree") == 0 && index + 1 < argc) mslTree = argv[index + 1];
    if (std::strcmp(argv[index], "--macos") == 0) macos = true;
  }
  if (command == "slang" && argc >= 4) return slang(argv[2], argv[3], msl, macos);
  if (command == "slang-batch" && argc >= 5) return slangBatch(argv[2], argv[3], argv[4], macos, mslTree);
  if (command == "dolphin") return dolphin(argv[2], msl, macos);
  std::cerr << "unknown command" << std::endl;
  return 2;
}
