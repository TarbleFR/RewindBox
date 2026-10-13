// SPDX-License-Identifier: GPL-3.0-or-later
// Behaviour tests of the shader kit's portable core (Linux and macOS):
// paths, RetroArch preset and source rules, reflection, MSL bindings,
// static cost figures and the Dolphin post-processing translation.
#include <cmath>
#include <cstdio>
#include <string>
#include <vector>

#include "NeoDolphinPostProcess.hpp"
#include "NeoShaderConfig.hpp"
#include "NeoShaderFiles.hpp"
#include "NeoShaderPaths.hpp"
#include "NeoSlangCompiler.hpp"
#include "NeoSlangPreset.hpp"
#include "NeoSlangSource.hpp"

using namespace neoshader;

static int g_failures = 0;
static int g_checks = 0;

#define CHECK(condition)                                                            \
  do {                                                                              \
    g_checks++;                                                                     \
    if (!(condition)) {                                                             \
      g_failures++;                                                                 \
      std::fprintf(stderr, "FAILED %s:%d: %s\n", __FILE__, __LINE__, #condition); \
    }                                                                               \
  } while (0)

static bool contains(const std::string& text, const std::string& needle) { return text.find(needle) != std::string::npos; }

static void testPaths() {
  CHECK(isSafeRelativePath("crt/shaders/crt-lottes.slang"));
  CHECK(!isSafeRelativePath(""));
  CHECK(!isSafeRelativePath("/etc/passwd"));
  CHECK(!isSafeRelativePath("crt/../../x"));
  CHECK(!isSafeRelativePath("crt//x.slang"));
  CHECK(!isSafeRelativePath("crt/./x.slang"));
  CHECK(!isSafeRelativePath("crt\\x.slang"));
  CHECK(!isSafeRelativePath("crt/$GAME$.slangp"));
  CHECK(!isSafeRelativePath(std::string("crt/a\0b", 7)));
  CHECK(!isSafeRelativePath(std::string(600, 'a')));

  std::string out;
  CHECK(resolveRelative("crt/crt-royale.slangp", "shaders/crt-royale/pass1.slang", &out) &&
        out == "crt/shaders/crt-royale/pass1.slang");
  CHECK(resolveRelative("crt/shaders/a.slang", "../../include/compat.inc", &out) && out == "include/compat.inc");
  CHECK(resolveRelative("root.slangp", "./x/../y.slang", &out) && out == "y.slang");
  CHECK(!resolveRelative("crt/a.slangp", "../../outside.slang", &out));
  CHECK(!resolveRelative("crt/a.slangp", "/abs.slang", &out));
  CHECK(!resolveRelative("crt/a.slangp", "..\\x.slang", &out));
  CHECK(!resolveRelative("crt/a.slangp", "$PRESET-DIR$/x.slang", &out));
  CHECK(!resolveRelative("crt/a.slangp", "dir/", &out));
  CHECK(fileExtension("a/B.SlangP") == "slangp");
  CHECK(baseName("a/b/c.inc") == "c.inc");
  CHECK(parentDirectory("a/b/c.inc") == "a/b");
  CHECK(parentDirectory("c.inc").empty());
}

static void testConfig() {
  const ConfigFile config = ConfigFile::parse(
      "#reference \"base/a.slangp\"\n"
      " # indented comment is no directive\n"
      "shaders = 2   # trailing comment\n"
      "shader0 = \"shaders/with # hash.slang\"\n"
      "shader1=broken\n"
      "filter_linear0 = true\n"
      "filter_linear0 = false\n"
      "scale0 = 2.5\n"
      "textures = \"LUT;MASK\"\n"
      "escaped = \"say \\\"hi\\\"\"\r\n"
      "hex = 0x10\n"
      "word = notabool\n");
  CHECK(config.references().size() == 1 && config.references()[0] == "base/a.slangp");
  unsigned passes = 0;
  CHECK(config.getUnsigned("shaders", &passes) && passes == 2);
  const std::string* shader = config.find("shader0");
  CHECK(shader != nullptr && *shader == "shaders/with # hash.slang");
  // "key=value" has no '=' after its key run: invalid, as in RetroArch.
  CHECK(!config.has("shader1") && !config.has("shader1=broken"));
  bool flag = false;
  CHECK(config.getBool("filter_linear0", &flag) && flag);  // first value wins
  float scale = 0;
  CHECK(config.getFloat("scale0", &scale) && std::fabs(scale - 2.5f) < 1e-6f);
  CHECK(config.find("textures") != nullptr && *config.find("textures") == "LUT;MASK");
  CHECK(config.find("escaped") != nullptr && *config.find("escaped") == "say \"hi\"");
  int hex = 0;
  CHECK(config.getInt("hex", &hex) && hex == 16);
  CHECK(!config.getBool("word", &flag));
}

static void testPresetBasics() {
  MemoryFileProvider files;
  files.add("crt/test.slangp",
            "shaders = 3\n"
            "shader0 = shaders/a.slang\n"
            "shader1 = ../common/b.slang\n"
            "shader2 = shaders/c.slang\n"
            "filter_linear0 = false\n"
            "wrap_mode1 = repeat\n"
            "mipmap_input2 = true\n"
            "alias0 = FIRST\n"
            "scale_type_x0 = absolute\n"
            "scale_x0 = 320\n"
            "scale_type_y0 = source\n"
            "scale_y0 = 2.0\n"
            "scale_type1 = viewport\n"
            "float_framebuffer1 = true\n"
            "frame_count_mod1 = 4\n"
            "textures = \"MASK;LUT2\"\n"
            "MASK = luts/mask.png\n"
            "MASK_linear = true\n"
            "MASK_wrap_mode = repeat\n"
            "MASK_mipmap = true\n"
            "LUT2 = ../luts/other.png\n");
  SlangPreset preset;
  ShaderError error;
  CHECK(loadSlangPreset(files, "crt/test.slangp", &preset, &error));
  CHECK(preset.passes.size() == 3);
  if (preset.passes.size() == 3) {
    const SlangPass& first = preset.passes[0];
    CHECK(first.shader == "crt/shaders/a.slang");
    CHECK(first.filter == FilterMode::Nearest);
    CHECK(first.wrap == WrapMode::ClampToBorder);  // RetroArch default
    CHECK(first.alias == "FIRST");
    CHECK(first.scaleSet && first.scaleTypeX == ScaleType::Absolute && first.absoluteX == 320);
    CHECK(first.scaleTypeY == ScaleType::Source && std::fabs(first.scaleY - 2.0f) < 1e-6f);
    const SlangPass& second = preset.passes[1];
    CHECK(second.shader == "common/b.slang");
    CHECK(second.filter == FilterMode::Unspecified);
    CHECK(second.wrap == WrapMode::Repeat);
    CHECK(second.scaleSet && second.scaleTypeX == ScaleType::Viewport && second.scaleTypeY == ScaleType::Viewport);
    CHECK(second.floatFramebuffer && second.frameCountMod == 4);
    const SlangPass& third = preset.passes[2];
    CHECK(!third.scaleSet && third.mipmapInput);
  }
  CHECK(preset.textures.size() == 2);
  if (preset.textures.size() == 2) {
    CHECK(preset.textures[0].name == "MASK" && preset.textures[0].path == "crt/luts/mask.png");
    CHECK(preset.textures[0].filter == FilterMode::Linear && preset.textures[0].mipmap &&
          preset.textures[0].wrap == WrapMode::Repeat);
    CHECK(preset.textures[1].path == "luts/other.png" && preset.textures[1].filter == FilterMode::Unspecified);
  }

  MemoryFileProvider bad;
  bad.add("p.slangp", "shaders = 1\nshader0 = ../../escape.slang\n");
  CHECK(!loadSlangPreset(bad, "p.slangp", &preset, &error) && error.code == "PRESET_UNSAFE_PATH");
  bad.add("w.slangp", "shaders = 1\nshader0 = shaders/$CORE$.slang\n");
  CHECK(!loadSlangPreset(bad, "w.slangp", &preset, &error) && error.code == "PRESET_UNSAFE_PATH");
  bad.add("n.slangp", "shaders = 0\n");
  CHECK(!loadSlangPreset(bad, "n.slangp", &preset, &error) && error.code == "PRESET_NO_PASSES");
  bad.add("m.slangp", "shaders = 2\nshader0 = a.slang\n");
  CHECK(!loadSlangPreset(bad, "m.slangp", &preset, &error) && error.code == "PRESET_PASS_MISSING");
  bad.add("t.slangp", "shaders = 1\nshader0 = a.slang\ntextures = LUT\n");
  CHECK(!loadSlangPreset(bad, "t.slangp", &preset, &error) && error.code == "PRESET_TEXTURE_MISSING");
  bad.add("s.slangp", "shaders = 1\nshader0 = a.slang\nscale_type0 = sideways\n");
  CHECK(!loadSlangPreset(bad, "s.slangp", &preset, &error) && error.code == "PRESET_BAD_SCALE");
  CHECK(!loadSlangPreset(bad, "missing.slangp", &preset, &error) && error.code == "PRESET_UNREADABLE");
}

static void testReferences() {
  MemoryFileProvider files;
  files.add("crt/full.slangp",
            "shaders = 1\nshader0 = shaders/a.slang\ntextures = MASK\nMASK = luts/mask.png\nGAMMA = 2.0\n");
  files.add("crt/variants/mid.slangp", "#reference \"../full.slangp\"\nGAMMA = 2.2\nBLUR = 0.5\n");
  files.add("presets/top.slangp",
            "#reference \"../crt/variants/mid.slangp\"\n#reference \"extra.slangp\"\nBLUR = 0.75\n"
            "MASK = mine/mask2.png\n");
  files.add("presets/extra.slangp", "GAMMA = 2.4\n");
  SlangPreset preset;
  ShaderError error;
  CHECK(loadSlangPreset(files, "presets/top.slangp", &preset, &error));
  CHECK(preset.rootPath == "crt/full.slangp" && preset.loadedPath == "presets/top.slangp");
  CHECK(preset.passes.size() == 1 && preset.passes[0].shader == "crt/shaders/a.slang");
  float value = 0;
  // Post-order: full, mid, extra, top; the last config setting a key wins.
  CHECK(preset.parameterValue("GAMMA", &value) && std::fabs(value - 2.4f) < 1e-6f);
  CHECK(preset.parameterValue("BLUR", &value) && std::fabs(value - 0.75f) < 1e-6f);
  CHECK(!preset.parameterValue("UNSET", &value));
  // A texture override is resolved relative to the preset that sets it.
  CHECK(preset.textures.size() == 1 && preset.textures[0].path == "presets/mine/mask2.png");
  CHECK(preset.presetFiles.size() == 4);

  files.add("presets/two-chains.slangp", "#reference \"../crt/full.slangp\"\n#reference \"../crt/full.slangp\"\n");
  CHECK(!loadSlangPreset(files, "presets/two-chains.slangp", &preset, &error) &&
        error.code == "PRESET_REFERENCE_CHAIN");
  files.add("loop/a.slangp", "#reference \"b.slangp\"\n");
  files.add("loop/b.slangp", "#reference \"a.slangp\"\n");
  CHECK(!loadSlangPreset(files, "loop/a.slangp", &preset, &error) && error.code == "PRESET_REFERENCE_DEPTH");
  files.add("presets/wild.slangp", "#reference \"$PRESET$.slangp\"\n");
  CHECK(!loadSlangPreset(files, "presets/wild.slangp", &preset, &error) && error.code == "PRESET_UNSAFE_PATH");
}

static const char* kSimplePass =
    "#version 450\n"
    "#pragma name FirstPass\n"
    "#pragma parameter GAIN \"Gain\" 1.0 0.0 2.0 0.1\n"
    "#pragma parameter MIX \"Mix\" 0.5 0.0 1.0\n"
    "#include \"inc/common.inc\"\n"
    "#pragma include_optional \"inc/missing.inc\"\n"
    "layout(push_constant) uniform Push { vec4 SourceSize; vec4 OutputSize; uint FrameCount; float GAIN; float MIX; } params;\n"
    "layout(std140, set = 0, binding = 0) uniform UBO { mat4 MVP; } global;\n"
    "#pragma stage vertex\n"
    "layout(location = 0) in vec4 Position;\n"
    "layout(location = 1) in vec2 TexCoord;\n"
    "layout(location = 0) out vec2 vTexCoord;\n"
    "void main() { gl_Position = global.MVP * Position; vTexCoord = TexCoord; }\n"
    "#pragma stage fragment\n"
    "layout(location = 0) in vec2 vTexCoord;\n"
    "layout(location = 0) out vec4 FragColor;\n"
    "layout(set = 0, binding = 2) uniform sampler2D Source;\n"
    "vec3 tap(vec2 uv) { return texture(Source, uv).rgb; }\n"
    "void main() {\n"
    "  vec3 c = tap(vTexCoord) + tap(vTexCoord + params.SourceSize.zw) + tap(vTexCoord - params.SourceSize.zw);\n"
    "  FragColor = vec4(c * params.GAIN * helper(params.MIX) + float(params.FrameCount % 2u) * 0.0, 1.0);\n"
    "}\n";

static const char* kSecondPass =
    "#version 450\n"
    "layout(push_constant) uniform Push { vec4 OriginalSize; vec4 FirstPassSize; vec4 OriginalHistorySize1; } params;\n"
    "layout(std140, set = 0, binding = 0) uniform UBO { mat4 MVP; vec4 FinalViewportSize; int FrameDirection; float GAIN; } global;\n"
    "#pragma stage vertex\n"
    "layout(location = 0) in vec4 Position;\n"
    "layout(location = 1) in vec2 TexCoord;\n"
    "layout(location = 0) out vec2 vTexCoord;\n"
    "void main() { gl_Position = global.MVP * Position; vTexCoord = TexCoord; }\n"
    "#pragma stage fragment\n"
    "layout(location = 0) in vec2 vTexCoord;\n"
    "layout(location = 0) out vec4 FragColor;\n"
    "layout(set = 0, binding = 1) uniform sampler2D Original;\n"
    "layout(set = 0, binding = 3) uniform sampler2D FirstPass;\n"
    "layout(set = 0, binding = 4) uniform sampler2D OriginalHistory1;\n"
    "layout(set = 0, binding = 5) uniform sampler2D MASK;\n"
    "layout(set = 0, binding = 6) uniform sampler2D PassFeedback1;\n"
    "void main() {\n"
    "  vec4 a = texture(Original, vTexCoord) + texture(FirstPass, vTexCoord) * global.GAIN;\n"
    "  for (int i = 0; i < 4; i++) a += texture(OriginalHistory1, vTexCoord + float(i) * params.OriginalSize.zw);\n"
    "  FragColor = a + texture(MASK, vTexCoord) * float(global.FrameDirection) + texture(PassFeedback1, vTexCoord)\n"
    "      + params.FirstPassSize + params.OriginalHistorySize1 + global.FinalViewportSize;\n"
    "}\n";

static void addPreset(MemoryFileProvider* files, const std::string& secondPass) {
  files->add("test/two.slangp",
             "shaders = 2\nshader0 = shaders/first.slang\nshader1 = shaders/second.slang\n"
             "textures = MASK\nMASK = mask.png\nGAIN = 1.5\n");
  files->add("test/shaders/inc/common.inc", "float helper(float x) { return x * 2.0; }\n");
  files->add("test/shaders/first.slang", kSimplePass);
  files->add("test/shaders/second.slang", secondPass);
  files->add("test/mask.png", "PNG");
}

static void testSource() {
  MemoryFileProvider files;
  addPreset(&files, kSecondPass);
  SlangSource source;
  ShaderError error;
  CHECK(loadSlangSource(files, "test/shaders/first.slang", &source, &error));
  CHECK(source.name == "FirstPass");
  CHECK(source.parameters.size() == 2);
  if (source.parameters.size() == 2) {
    CHECK(source.parameters[0].id == "GAIN" && source.parameters[0].description == "Gain");
    // Five fields: RetroArch's default step is a tenth of the range.
    CHECK(std::fabs(source.parameters[1].step - 0.1f) < 1e-6f);
  }
  CHECK(source.files.size() == 2 && source.files[1] == "test/shaders/inc/common.inc");
  CHECK(contains(source.vertex, "gl_Position = global.MVP") && !contains(source.vertex, "FragColor"));
  CHECK(contains(source.fragment, "FragColor") && !contains(source.fragment, "gl_Position = global.MVP"));
  CHECK(contains(source.vertex, "float helper"));  // shared include in both stages
  CHECK(contains(source.vertex, "#define _HAS_ORIGINALASPECT_UNIFORMS"));
  CHECK(!contains(source.vertex, "_HAS_SENSOR_UNIFORMS"));
  CHECK(!contains(source.fragment, "#pragma name"));

  MemoryFileProvider bad;
  bad.add("a.slang", "void main() {}\n");
  CHECK(!loadSlangSource(bad, "a.slang", &source, &error) && error.code == "SOURCE_NO_VERSION");
  bad.add("b.slang", "#version 450\n#include \"c.inc\"\n");
  bad.add("c.inc", "#include \"b2.inc\"\n");
  bad.add("b2.inc", "#include \"c.inc\"\n");
  CHECK(!loadSlangSource(bad, "b.slang", &source, &error) && error.code == "SOURCE_INCLUDE_DEPTH");
  bad.add("d.slang", "#version 450\n#include \"missing.inc\"\n");
  CHECK(!loadSlangSource(bad, "d.slang", &source, &error) && error.code == "SOURCE_UNREADABLE");
  bad.add("e.slang", "#version 450\n#include \"../../etc/x\"\n");
  CHECK(!loadSlangSource(bad, "e.slang", &source, &error) && error.code == "SOURCE_UNSAFE_INCLUDE");
  bad.add("f.slang",
          "#version 450\n#pragma parameter A \"One\" 1.0 0.0 2.0 0.1\n#pragma parameter A \"Two\" 1.0 0.0 2.0 0.1\n");
  CHECK(!loadSlangSource(bad, "f.slang", &source, &error) && error.code == "SOURCE_BAD_PARAMETER");
  bad.add("g.slang", "#version 450\n#pragma format R9_NOPE\n");
  CHECK(!loadSlangSource(bad, "g.slang", &source, &error) && error.code == "SOURCE_BAD_FORMAT");
}

static const SlangUniformSlot* findUniform(const CompiledSlangPass& pass, SlangUniformSlot::Kind kind, int semantic,
                                           unsigned index) {
  for (const SlangUniformSlot& slot : pass.uniforms) {
    if (slot.kind != kind || slot.index != index) continue;
    if (kind == SlangUniformSlot::Kind::Semantic && static_cast<int>(slot.semantic) != semantic) continue;
    if (kind == SlangUniformSlot::Kind::TextureSize && static_cast<int>(slot.textureSemantic) != semantic) continue;
    return &slot;
  }
  return nullptr;
}

static void testCompile() {
  MemoryFileProvider files;
  addPreset(&files, kSecondPass);
  CompiledSlangPreset compiled;
  ShaderError error;
  SlangCompileOptions options;
  const bool ok = compileSlangPreset(files, "test/two.slangp", options, &compiled, &error);
  if (!ok) std::fprintf(stderr, "compile error %s: %s\n", error.code.c_str(), error.detail.c_str());
  CHECK(ok);
  if (!ok) return;
  CHECK(compiled.passes.size() == 2);
  CHECK(compiled.aliases[0] == "FirstPass");  // from #pragma name
  CHECK(compiled.parameters.size() == 2);
  CHECK(compiled.parameters[0].declaration.id == "GAIN" && std::fabs(compiled.parameters[0].value - 1.5f) < 1e-6f);
  CHECK(std::fabs(compiled.parameters[1].value - 0.5f) < 1e-6f);
  CHECK(compiled.historyDepth == 1);
  CHECK(compiled.feedback.size() == 2 && !compiled.feedback[0] && compiled.feedback[1]);
  // two.slangp, first.slang, inc/common.inc, second.slang, mask.png (the
  // missing optional include is not part of the closure).
  CHECK(compiled.files.size() == 5);

  const CompiledSlangPass& first = compiled.passes[0];
  const SlangUniformSlot* mvp = findUniform(first, SlangUniformSlot::Kind::Semantic, (int)SlangSemantic::MVP, 0);
  CHECK(mvp != nullptr && mvp->uboOffset == 0 && mvp->pushOffset == -1 && mvp->components == 16);
  const SlangUniformSlot* sourceSize =
      findUniform(first, SlangUniformSlot::Kind::TextureSize, (int)SlangTextureSemantic::Source, 0);
  CHECK(sourceSize != nullptr && sourceSize->pushOffset == 0);
  const SlangUniformSlot* frameCount =
      findUniform(first, SlangUniformSlot::Kind::Semantic, (int)SlangSemantic::FrameCount, 0);
  CHECK(frameCount != nullptr && frameCount->pushOffset == 32);
  const SlangUniformSlot* gain = findUniform(first, SlangUniformSlot::Kind::Parameter, 0, 0);
  CHECK(gain != nullptr && gain->pushOffset == 36);
  CHECK(first.uboSize == 64 && first.pushSize == 48);
  CHECK(first.textures.size() == 1 && first.textures[0].semantic == SlangTextureSemantic::Source &&
        first.textures[0].binding == 2);
  // tap() is called three times: the call graph counts three samples.
  CHECK(first.sampleInstructions == 3 && !first.samplesInLoop);
  CHECK(contains(first.fragmentMSL, "[[texture(2)]]") && contains(first.fragmentMSL, "[[sampler(2)]]"));
  CHECK(contains(first.fragmentMSL, "[[buffer(1)]]"));
  CHECK(contains(first.vertexMSL, "[[buffer(0)]]") && contains(first.vertexMSL, "[[attribute(0)]]") &&
        contains(first.vertexMSL, "[[attribute(1)]]"));
  CHECK(contains(first.vertexMSL, "gl_Position.y = -(out.gl_Position.y)") ||
        contains(first.vertexMSL, "out.gl_Position.y = -(out.gl_Position.y)"));
  CHECK(!first.vertexEntry.empty() && !first.fragmentEntry.empty());

  const CompiledSlangPass& second = compiled.passes[1];
  bool sawPassOutput = false, sawHistory = false, sawUser = false, sawFeedback = false, sawOriginal = false;
  for (const SlangTextureSlot& slot : second.textures) {
    sawOriginal = sawOriginal || (slot.semantic == SlangTextureSemantic::Original && slot.binding == 1);
    sawPassOutput = sawPassOutput || (slot.semantic == SlangTextureSemantic::PassOutput && slot.index == 0);
    sawHistory = sawHistory || (slot.semantic == SlangTextureSemantic::OriginalHistory && slot.index == 1);
    sawUser = sawUser || (slot.semantic == SlangTextureSemantic::User && slot.index == 0 && slot.binding == 5);
    sawFeedback = sawFeedback || (slot.semantic == SlangTextureSemantic::PassFeedback && slot.index == 1);
  }
  CHECK(sawOriginal && sawPassOutput && sawHistory && sawUser && sawFeedback);
  const SlangUniformSlot* aliasSize =
      findUniform(second, SlangUniformSlot::Kind::TextureSize, (int)SlangTextureSemantic::PassOutput, 0);
  CHECK(aliasSize != nullptr && aliasSize->pushOffset == 16);
  const SlangUniformSlot* direction =
      findUniform(second, SlangUniformSlot::Kind::Semantic, (int)SlangSemantic::FrameDirection, 0);
  CHECK(direction != nullptr && direction->uboOffset == 80);
  const SlangUniformSlot* gainUbo = findUniform(second, SlangUniformSlot::Kind::Parameter, 0, 0);
  CHECK(gainUbo != nullptr && gainUbo->uboOffset == 84 && gainUbo->pushOffset == -1);
  CHECK(second.samplesInLoop);

  // The macOS variant only changes the platform of the generated code.
  options.iosPlatform = false;
  CompiledSlangPreset desktop;
  CHECK(compileSlangPreset(files, "test/two.slangp", options, &desktop, &error));
}

static void expectCompileFailure(const std::string& secondPass, const char* code) {
  MemoryFileProvider files;
  addPreset(&files, secondPass);
  CompiledSlangPreset compiled;
  ShaderError error;
  const bool ok = compileSlangPreset(files, "test/two.slangp", SlangCompileOptions(), &compiled, &error);
  CHECK(!ok);
  if (ok || error.code != code) {
    std::fprintf(stderr, "  expected %s, got %s (%s)\n", code, error.code.c_str(), error.detail.c_str());
    g_failures++;
  }
}

static std::string secondPassWith(const std::string& shared, const std::string& fragment, const std::string& body) {
  return "#version 450\n"
         "layout(std140, set = 0, binding = 0) uniform UBO { mat4 MVP; } global;\n" +
         shared +
         "\n#pragma stage vertex\n"
         "layout(location = 0) in vec4 Position;\n"
         "layout(location = 1) in vec2 TexCoord;\n"
         "layout(location = 0) out vec2 vTexCoord;\n"
         "void main() { gl_Position = global.MVP * Position; vTexCoord = TexCoord; }\n"
         "#pragma stage fragment\n"
         "layout(location = 0) in vec2 vTexCoord;\n"
         "layout(location = 0) out vec4 FragColor;\n"
         "layout(set = 0, binding = 2) uniform sampler2D Source;\n" +
         fragment + "\nvoid main() { FragColor = texture(Source, vTexCoord)" + body + "; }\n";
}

static void testRefusals() {
  // HDR and sensor uniforms are not filled by NeoStation.
  expectCompileFailure(secondPassWith("layout(push_constant) uniform Push { uint HDRMode; } params;", "",
                                      " * float(params.HDRMode)"),
                       "REFLECT_UNKNOWN_SEMANTIC");
  // Wrong type for a known semantic.
  expectCompileFailure(secondPassWith("layout(push_constant) uniform Push { float FrameCount; } params;", "",
                                      " * params.FrameCount"),
                       "REFLECT_SEMANTIC_TYPE");
  // A pass output read before it is produced.
  expectCompileFailure(secondPassWith("", "layout(set = 0, binding = 3) uniform sampler2D PassOutput1;",
                                      " + texture(PassOutput1, vTexCoord)"),
                       "REFLECT_TEXTURE_SEMANTIC");
  // A texture name that is neither a semantic, an alias nor a LUT.
  expectCompileFailure(secondPassWith("", "layout(set = 0, binding = 3) uniform sampler2D NotDeclared;",
                                      " + texture(NotDeclared, vTexCoord)"),
                       "REFLECT_TEXTURE_SEMANTIC");
  // A texture declared before "#pragma stage vertex" is a vertex resource
  // too: RetroArch refuses vertex textures.
  expectCompileFailure(secondPassWith("layout(set = 0, binding = 3) uniform sampler2D Original;", "",
                                      " + texture(Original, vTexCoord)"),
                       "REFLECT_RESOURCE_TYPE");
  // Push constants over 128 bytes.
  expectCompileFailure(
      secondPassWith("layout(push_constant) uniform Push { vec4 SourceSize; float GAIN; mat4 MVP; vec4 OutputSize; "
                     "vec4 OriginalSize; vec4 FinalViewportSize; } params;",
                     "",
                     " * params.GAIN + params.SourceSize + params.OutputSize + params.OriginalSize + "
                     "params.FinalViewportSize + params.MVP[0]"),
      "REFLECT_PUSH_CONSTANT_SIZE");
  // A binding used twice.
  expectCompileFailure(secondPassWith("", "layout(set = 0, binding = 2) uniform sampler2D Original;",
                                      " + texture(Original, vTexCoord)"),
                       "REFLECT_BINDING");
  // Syntax errors are reported with glslang's log.
  expectCompileFailure(secondPassWith("", "", " + undefined_function()"), "GLSL_FRAGMENT_FAILED");
}

static void testDolphinOptions() {
  const std::string code =
      "/*\n[configuration]\n"
      "[OptionRangeFloat]\nGUIName = Zeta\nOptionName = Z_OPT\nMinValue = 0.0\nMaxValue = 2.0\n"
      "DefaultValue = 1.5\nStepAmount = 0.5\n"
      "[OptionBool]\nGUIName = Alpha flag\nOptionName = A_FLAG\nDefaultValue = true\n"
      "[OptionRangeInteger]\nGUIName = Count\nOptionName = M_COUNT\nMinValue = 1\nMaxValue = 8\n"
      "DefaultValue = 4\nStepAmount = 1\n"
      "[OptionRangeFloat]\nGUIName = Pair\nOptionName = P_PAIR\nMinValue = 0.0, 0.0\nMaxValue = 1.0, 1.0\n"
      "DefaultValue = 0.25, 0.75\nStepAmount = 0.05, 0.05\n"
      "[Something]\nOptionName = S_ODD\nDefaultValue = 0\n"
      "[/configuration]\n*/\n"
      "void main() { SetOutput(Sample() * GetOption(Z_OPT) * float(GetOption(M_COUNT)) * GetOption(P_PAIR).x "
      "* (OptionEnabled(A_FLAG) ? 1.0 : 0.5) * (OptionEnabled(S_ODD) ? 1.0 : 0.5)); }\n";
  const std::vector<DolphinOption> options = parseDolphinOptions(code);
  CHECK(options.size() == 5);
  if (options.size() == 5) {
    // std::map order: sorted by OptionName; 16-byte slots after 140 bytes.
    CHECK(options[0].name == "A_FLAG" && options[0].type == DolphinOptionType::Bool && options[0].values[0] == 1.0);
    CHECK(options[0].uniformOffset == 140);
    CHECK(options[1].name == "M_COUNT" && options[1].type == DolphinOptionType::Integer &&
          options[1].values[0] == 4.0 && options[1].maximums[0] == 8.0 && options[1].uniformOffset == 156);
    CHECK(options[2].name == "P_PAIR" && options[2].values.size() == 2 && std::fabs(options[2].values[1] - 0.75) < 1e-6);
    CHECK(options[3].name == "S_ODD" && options[3].type == DolphinOptionType::Bool);  // unknown section: Bool
    CHECK(options[4].name == "Z_OPT" && std::fabs(options[4].values[0] - 1.5) < 1e-6 && options[4].guiName == "Zeta");
  }
  DolphinPostProcessShader shader;
  ShaderError error;
  const bool ok = translateDolphinPostProcess(code, DolphinTranslateOptions(), &shader, &error);
  if (!ok) std::fprintf(stderr, "dolphin error %s: %s\n", error.code.c_str(), error.detail.c_str());
  CHECK(ok);
  CHECK(shader.uniformBytes == 140 + 5 * 16);
  CHECK(shader.vectorOptionLayoutMismatch);  // P_PAIR is a float2
  CHECK(contains(shader.fragmentMSL, "texture2d_array<float> samp0 [[texture(0)]]"));
  CHECK(contains(shader.fragmentMSL, "[[buffer(0)]]"));
  CHECK(contains(shader.vertexMSL, "[[buffer(1)]]"));
  CHECK(contains(shader.fragmentGLSL, "uint GetTime()") && contains(shader.fragmentGLSL, "#define API_METAL 1"));

  CHECK(!translateDolphinPostProcess("void main() { SetOutput(NotAFunction()); }", DolphinTranslateOptions(), &shader,
                                     &error) &&
        error.code == "GLSL_FRAGMENT_FAILED");
  CHECK(!translateDolphinPostProcess(std::string(600 * 1024, ' ') + "void main(){}", DolphinTranslateOptions(), &shader,
                                     &error) &&
        error.code == "DOLPHIN_TOO_LARGE");
  CHECK(parseDolphinOptions("void main() {}").empty());
}

int main() {
  testPaths();
  testConfig();
  testPresetBasics();
  testReferences();
  testSource();
  testCompile();
  testRefusals();
  testDolphinOptions();
  std::printf("%d checks, %d failures\n", g_checks, g_failures);
  return g_failures == 0 ? 0 : 1;
}
