// SPDX-License-Identifier: GPL-3.0-or-later
#include "NeoSlangSource.hpp"

#include <cstdio>
#include <cstring>

#include "NeoShaderPaths.hpp"

namespace neoshader {

const char* const kSlangFeatureDefines[3] = {
    "#define _HAS_ORIGINALASPECT_UNIFORMS",
    "#define _HAS_FRAMETIME_UNIFORMS",
    "#define _HAS_SWAPCOUNT_UNIFORM",
};

namespace {

struct FormatName {
  SlangFormat format;
  const char* name;
};

const FormatName kFormats[] = {
    {SlangFormat::R8_UNORM, "R8_UNORM"},
    {SlangFormat::R8_UINT, "R8_UINT"},
    {SlangFormat::R8_SINT, "R8_SINT"},
    {SlangFormat::R8G8_UNORM, "R8G8_UNORM"},
    {SlangFormat::R8G8_UINT, "R8G8_UINT"},
    {SlangFormat::R8G8_SINT, "R8G8_SINT"},
    {SlangFormat::R8G8B8A8_UNORM, "R8G8B8A8_UNORM"},
    {SlangFormat::R8G8B8A8_UINT, "R8G8B8A8_UINT"},
    {SlangFormat::R8G8B8A8_SINT, "R8G8B8A8_SINT"},
    {SlangFormat::R8G8B8A8_SRGB, "R8G8B8A8_SRGB"},
    {SlangFormat::A2B10G10R10_UNORM_PACK32, "A2B10G10R10_UNORM_PACK32"},
    {SlangFormat::A2B10G10R10_UINT_PACK32, "A2B10G10R10_UINT_PACK32"},
    {SlangFormat::R16_UINT, "R16_UINT"},
    {SlangFormat::R16_SINT, "R16_SINT"},
    {SlangFormat::R16_SFLOAT, "R16_SFLOAT"},
    {SlangFormat::R16G16_UINT, "R16G16_UINT"},
    {SlangFormat::R16G16_SINT, "R16G16_SINT"},
    {SlangFormat::R16G16_SFLOAT, "R16G16_SFLOAT"},
    {SlangFormat::R16G16B16A16_UINT, "R16G16B16A16_UINT"},
    {SlangFormat::R16G16B16A16_SINT, "R16G16B16A16_SINT"},
    {SlangFormat::R16G16B16A16_SFLOAT, "R16G16B16A16_SFLOAT"},
    {SlangFormat::R32_UINT, "R32_UINT"},
    {SlangFormat::R32_SINT, "R32_SINT"},
    {SlangFormat::R32_SFLOAT, "R32_SFLOAT"},
    {SlangFormat::R32G32_UINT, "R32G32_UINT"},
    {SlangFormat::R32G32_SINT, "R32G32_SINT"},
    {SlangFormat::R32G32_SFLOAT, "R32G32_SFLOAT"},
    {SlangFormat::R32G32B32A32_UINT, "R32G32B32A32_UINT"},
    {SlangFormat::R32G32B32A32_SINT, "R32G32B32A32_SINT"},
    {SlangFormat::R32G32B32A32_SFLOAT, "R32G32B32A32_SFLOAT"},
};

bool fail(ShaderError* error, const char* code, const std::string& detail) {
  if (error != nullptr) {
    error->code = code;
    error->detail = detail;
  }
  return false;
}

bool startsWith(const std::string& text, const char* prefix) { return text.compare(0, std::strlen(prefix), prefix) == 0; }

std::vector<std::string> splitLines(const std::string& text) {
  std::vector<std::string> lines;
  size_t start = 0;
  while (start < text.size()) {
    size_t end = text.find('\n', start);
    if (end == std::string::npos) end = text.size();
    std::string line = text.substr(start, end - start);
    // CRLF sources: RetroArch drops every '\r'.
    std::string cleaned;
    cleaned.reserve(line.size());
    for (char character : line) {
      if (character != '\r') cleaned += character;
    }
    lines.push_back(cleaned);
    start = end + 1;
  }
  return lines;
}

/// get_include_file: the text between the first pair of quotes.
bool includeName(const std::string& line, std::string* name) {
  const size_t first = line.find('"');
  if (first == std::string::npos) return false;
  const size_t second = line.find('"', first + 1);
  if (second == std::string::npos || second == first + 1) return false;
  *name = line.substr(first + 1, second - first - 1);
  return true;
}

struct Expander {
  FileProvider& files;
  std::vector<std::string> output;
  std::vector<std::string> visited;
  std::vector<std::string> stack;
  size_t bytes = 0;
  ShaderError* error;

  bool append(const std::string& line) {
    bytes += line.size() + 1;
    if (bytes > kMaxExpandedSourceBytes) return fail(error, "SOURCE_TOO_LARGE", stack.empty() ? "" : stack.front());
    output.push_back(line);
    return true;
  }

  std::string lineDirective(unsigned line, const std::string& path) {
    return "#line " + std::to_string(line) + " \"" + baseName(path) + "\"";
  }

  /// glslang_read_shader_file. Returns false on error; *missing is set when
  /// the file itself could not be read (optional includes are skipped).
  bool expand(const std::string& path, bool root, bool* missing) {
    *missing = false;
    if (stack.size() >= kMaxIncludeDepth) return fail(error, "SOURCE_INCLUDE_DEPTH", path);
    for (const std::string& open : stack) {
      if (open == path) return fail(error, "SOURCE_INCLUDE_DEPTH", "include cycle: " + path);
    }
    std::string text;
    if (!files.read(path, &text)) {
      *missing = true;
      return fail(error, "SOURCE_UNREADABLE", path);
    }
    bool known = false;
    for (const std::string& file : visited) known = known || file == path;
    if (!known) visited.push_back(path);
    stack.push_back(path);
    const std::vector<std::string> lines = splitLines(text);
    size_t first = 0;
    if (root) {
      if (lines.empty() || !startsWith(lines[0], "#version ")) return fail(error, "SOURCE_NO_VERSION", path);
      if (!append(lines[0])) return false;
      if (!append("#extension GL_GOOGLE_cpp_style_line_directive : require")) return false;
      for (const char* define : kSlangFeatureDefines) {
        if (!append(define)) return false;
      }
      if (!append(lineDirective(2, path))) return false;
      first = 1;
    } else {
      if (!append(lineDirective(1, path))) return false;
    }
    for (size_t index = first; index < lines.size(); index++) {
      const std::string& line = lines[index];
      const bool optional = startsWith(line, "#pragma include_optional ");
      unsigned pushLine = 0;
      if (startsWith(line, "#include ") || optional) {
        std::string name;
        if (!includeName(line, &name)) return fail(error, "SOURCE_UNSAFE_INCLUDE", path + ": " + line);
        std::string included;
        if (!resolveRelative(path, name, &included)) {
          return fail(error, "SOURCE_UNSAFE_INCLUDE", path + ": " + name);
        }
        bool includeMissing = false;
        if (!expand(included, false, &includeMissing)) {
          if (!(optional && includeMissing)) return false;
          if (error != nullptr) *error = ShaderError();
        }
        pushLine = 1;
      } else if (startsWith(line, "#endif") || startsWith(line, "#pragma")) {
        // RetroArch re-states #line after these (glslang may drop a #line
        // inside a failed #if); the offset is for the following line.
        if (!append(line)) return false;
        pushLine = 2;
      } else {
        if (!append(line)) return false;
      }
      if (pushLine != 0) {
        if (!append(lineDirective(static_cast<unsigned>(index + pushLine), path))) return false;
      }
    }
    stack.pop_back();
    return true;
  }
};

/// sscanf("#pragma parameter %63s \"%63[^\"]\" %f %f %f %f") as RetroArch
/// does, including its 63-character limits and the default step
/// (0.1 * (maximum - minimum)) when only five fields are present.
bool parseParameter(const std::string& line, SlangParameter* parameter) {
  char id[64] = {0};
  char description[64] = {0};
  float initial = 0, minimum = 0, maximum = 0, step = 0;
  int fields = std::sscanf(line.c_str(), "#pragma parameter %63s \"%63[^\"]\" %f %f %f %f", id, description, &initial,
                           &minimum, &maximum, &step);
  if (fields == 5) {
    step = 0.1f * (maximum - minimum);
    fields = 6;
  }
  if (fields != 6) return false;
  parameter->id = id;
  parameter->description = description;
  parameter->initial = initial;
  parameter->minimum = minimum;
  parameter->maximum = maximum;
  parameter->step = step;
  return true;
}

/// build_stage_source: the version line, then every line with the inactive
/// stage's lines and "#pragma name/format/stage" lines blanked (line numbers
/// keep their place).
std::string buildStage(const std::vector<std::string>& lines, const std::string& stage) {
  std::string result;
  if (lines.empty()) return result;
  result += lines[0];
  result += '\n';
  bool active = true;
  const std::string expected = "#pragma stage " + stage;
  for (size_t index = 1; index < lines.size(); index++) {
    const std::string& line = lines[index];
    if (startsWith(line, "#pragma stage ")) {
      active = line == expected;
    } else if (startsWith(line, "#pragma name ") || startsWith(line, "#pragma format ")) {
      // ignored
    } else if (active) {
      result += line;
    }
    result += '\n';
  }
  return result;
}

}  // namespace

SlangFormat slangFormatFromName(const std::string& name) {
  for (const FormatName& entry : kFormats) {
    if (name == entry.name) return entry.format;
  }
  return SlangFormat::Unknown;
}

const char* slangFormatName(SlangFormat format) {
  for (const FormatName& entry : kFormats) {
    if (entry.format == format) return entry.name;
  }
  return "UNKNOWN";
}

bool loadSlangSource(FileProvider& files, const std::string& path, SlangSource* source, ShaderError* error) {
  *source = SlangSource();
  source->path = path;
  if (!isSafeRelativePath(path)) return fail(error, "SOURCE_UNSAFE_INCLUDE", path);
  Expander expander{files, {}, {}, {}, 0, error};
  bool missing = false;
  if (!expander.expand(path, true, &missing)) return false;
  source->files = expander.visited;

  // glslang_parse_meta.
  for (const std::string& line : expander.output) {
    if (startsWith(line, "#pragma name ")) {
      if (!source->name.empty()) return fail(error, "SOURCE_DUPLICATE_NAME", path);
      size_t start = std::strlen("#pragma name ");
      while (start < line.size() && line[start] == ' ') start++;
      source->name = line.substr(start);
    } else if (startsWith(line, "#pragma parameter ")) {
      SlangParameter parameter;
      if (!parseParameter(line, &parameter)) return fail(error, "SOURCE_BAD_PARAMETER", path + ": " + line);
      bool duplicate = false;
      for (const SlangParameter& known : source->parameters) {
        if (known.id != parameter.id) continue;
        duplicate = true;
        // Allowed only when every argument matches.
        if (known.description != parameter.description || known.initial != parameter.initial ||
            known.minimum != parameter.minimum || known.maximum != parameter.maximum ||
            known.step != parameter.step) {
          return fail(error, "SOURCE_BAD_PARAMETER", path + ": conflicting declarations of " + parameter.id);
        }
      }
      if (!duplicate) source->parameters.push_back(parameter);
    } else if (startsWith(line, "#pragma format ")) {
      if (source->format != SlangFormat::Unknown) return fail(error, "SOURCE_BAD_FORMAT", path + ": twice");
      size_t start = std::strlen("#pragma format ");
      while (start < line.size() && line[start] == ' ') start++;
      // Trailing spaces would make RetroArch's lookup fail as well.
      source->format = slangFormatFromName(line.substr(start));
      if (source->format == SlangFormat::Unknown) return fail(error, "SOURCE_BAD_FORMAT", path + ": " + line);
    }
  }
  source->vertex = buildStage(expander.output, "vertex");
  source->fragment = buildStage(expander.output, "fragment");
  return true;
}

}  // namespace neoshader
