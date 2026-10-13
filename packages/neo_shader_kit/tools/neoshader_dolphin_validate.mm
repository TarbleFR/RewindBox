// SPDX-License-Identifier: GPL-3.0-or-later
// Metal validation of Dolphin post-processing shaders (macOS, CI). Each file
// goes through the translation the embedded Dolphin core performs on Metal
// (NeoDolphinPostProcess.cpp: Dolphin's header, uniform block, GLSL ->
// SPIR-V -> MSL settings of the pinned DolphiniOS revision), then is drawn
// the way VideoCommon/PostProcessing.cpp draws it: one triangle of three
// vertices, the uniform buffer of FillUniformBuffer (140 bytes of builtins,
// then one 16-byte slot per option with its default value), the game picture
// as a one-layer texture array with a linear sampler. Three frames of a
// moving picture are drawn and the last one is compared with the same draw
// through a pass-through shader (SetOutput(Sample()), what Dolphin shows
// without an effect). A file passes only when it compiled, rendered and
// visibly changed the picture:
//
//   neoshader-dolphin-validate LIST_FILE OUTPUT_JSONL
//
// LIST_FILE holds one .glsl path per line. One JSON line is written per
// file: {"file", "ok", "stage", "code", "detail", "options",
// "uniformBytes", "compileSeconds", "gpuMilliseconds", "changedFraction",
// "meanDifference", "litFraction", "colors"}. Exit status: 0 when every file
// passed, 1 when one failed, 2 on usage errors, 3 without a Metal device, 4
// after a GPU error (the caller starts a new process for the files left).
// This reproduces Dolphin's interface; it does not run the Dolphin core.
#import <Foundation/Foundation.h>
#import <Metal/Metal.h>

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <set>
#include <sstream>
#include <string>
#include <vector>

#include "NeoDolphinPostProcess.hpp"

namespace {

/// Source: a GameCube frame at 1x internal resolution (640x480); target:
/// an iPhone game area, not an integer multiple of it.
constexpr NSUInteger kSourceWidth = 640;
constexpr NSUInteger kSourceHeight = 480;
constexpr NSUInteger kTargetWidth = 1186;
constexpr NSUInteger kTargetHeight = 890;
constexpr int kFrames = 3;
constexpr int kChangedThreshold = 3;
constexpr double kMinimumChangedFraction = 0.001;
constexpr double kMinimumLitFraction = 0.02;
constexpr size_t kMinimumColors = 2;
constexpr int kGPUErrorExit = 4;
/// APIType::Metal in VideoCommon/VideoConfig.h of the pinned revision.
constexpr int32_t kAPIMetal = 3;
const char *const kPassThrough = "void main()\n{\n  SetOutput(Sample());\n}\n";

std::string Quote(const std::string &text) {
  std::string result = "\"";
  for (unsigned char character : text) {
    switch (character) {
      case '"': result += "\\\""; break;
      case '\\': result += "\\\\"; break;
      case '\n': result += "\\n"; break;
      case '\r': result += "\\r"; break;
      case '\t': result += "\\t"; break;
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

/// Synthetic game frame (RGBA8, top row first): colour bars, gradients,
/// fine checkerboards and lines, sprites on a dark background, shifted by
/// two pixels per frame. Deterministic.
std::vector<uint8_t> TestPicture(int frame) {
  std::vector<uint8_t> rgba(kSourceWidth * kSourceHeight * 4);
  for (NSUInteger y = 0; y < kSourceHeight; y++) {
    for (NSUInteger x = 0; x < kSourceWidth; x++) {
      const NSUInteger sx = (x + (NSUInteger)frame * 2) % kSourceWidth;
      uint8_t r = 0, g = 0, b = 0;
      if (y < 120) {
        const unsigned bar = (unsigned)(sx * 8 / kSourceWidth);
        r = (bar & 1) ? 230 : 20;
        g = (bar & 2) ? 220 : 30;
        b = (bar & 4) ? 210 : 40;
      } else if (y < 240) {
        r = (uint8_t)(sx * 255 / (kSourceWidth - 1));
        g = (uint8_t)((y - 120) * 255 / 119);
        b = (uint8_t)(255 - r / 2);
      } else if (y < 360) {
        const NSUInteger cell = sx < 213 ? 1 : (sx < 426 ? 2 : 4);
        const bool on = ((sx / cell) + (y / cell)) % 2 == 0;
        r = g = b = on ? 235 : 25;
        if ((sx + y) % 23 == 0) { r = 250; g = 60; b = 60; }
      } else {
        r = 16; g = 24; b = 48;
        const NSUInteger ox = sx % 96, oy = (y - 360) % 60;
        if (ox > 50 && ox < 80 && oy > 10 && oy < 50) { r = 60; g = 200; b = 90; }
        if ((sx % 16) < 10 && ((y - 360) % 20) < 12 && ((sx / 16 + y / 20) % 3) == 0) { r = 240; g = 240; b = 200; }
      }
      uint8_t *pixel = rgba.data() + (y * kSourceWidth + x) * 4;
      pixel[0] = r;
      pixel[1] = g;
      pixel[2] = b;
      pixel[3] = 255;
    }
  }
  return rgba;
}

struct Result {
  bool gpuError = false;
  bool ok = false;
  std::string stage = "translate";
  std::string code;
  std::string detail;
  std::string options = "[]";
  unsigned uniformBytes = 0;
  double compileSeconds = 0;
  double gpuMilliseconds = 0;
  double changedFraction = 0;
  double meanDifference = 0;
  double litFraction = 0;
  size_t colors = 0;
};

std::string Number(double value) {
  char buffer[64];
  std::snprintf(buffer, sizeof(buffer), "%.6g", value);
  return buffer;
}

std::string OptionsJson(const std::vector<neoshader::DolphinOption> &options) {
  std::string json = "[";
  for (size_t index = 0; index < options.size(); index++) {
    const neoshader::DolphinOption &option = options[index];
    if (index > 0) json += ",";
    json += "{\"name\":" + Quote(option.name) + ",\"gui\":" + Quote(option.guiName) +
            ",\"type\":" + Quote(neoshader::dolphinOptionTypeName(option.type)) +
            ",\"dependent\":" + Quote(option.dependentOption) + ",\"values\":[";
    for (size_t value = 0; value < option.values.size(); value++) json += (value ? "," : "") + Number(option.values[value]);
    json += "],\"minimum\":[";
    for (size_t value = 0; value < option.minimums.size(); value++) json += (value ? "," : "") + Number(option.minimums[value]);
    json += "],\"maximum\":[";
    for (size_t value = 0; value < option.maximums.size(); value++) json += (value ? "," : "") + Number(option.maximums[value]);
    json += "],\"step\":[";
    for (size_t value = 0; value < option.steps.size(); value++) json += (value ? "," : "") + Number(option.steps[value]);
    json += "]}";
  }
  return json + "]";
}

std::string Json(const std::string &file, const Result &result) {
  char numbers[512];
  std::snprintf(numbers, sizeof(numbers),
                "\"uniformBytes\":%u,\"compileSeconds\":%.4f,\"gpuMilliseconds\":%.4f,\"changedFraction\":%.6f,"
                "\"meanDifference\":%.4f,\"litFraction\":%.6f,\"colors\":%zu",
                result.uniformBytes, result.compileSeconds, result.gpuMilliseconds, result.changedFraction,
                result.meanDifference, result.litFraction, result.colors);
  return "{\"file\":" + Quote(file) + ",\"ok\":" + (result.ok ? "true" : "false") + ",\"stage\":" +
         Quote(result.stage) + ",\"code\":" + Quote(result.code) + ",\"detail\":" + Quote(result.detail.substr(0, 2000)) +
         ",\"options\":" + result.options + "," + numbers + "}";
}

/// FillUniformBuffer of the pinned revision (BuiltinUniforms, then options).
std::vector<uint8_t> Uniforms(const neoshader::DolphinPostProcessShader &shader, uint32_t milliseconds) {
  std::vector<uint8_t> bytes((shader.uniformBytes + 255) / 256 * 256, 0);
  auto putFloats = [&](size_t offset, std::initializer_list<float> values) {
    size_t index = 0;
    for (float value : values) std::memcpy(bytes.data() + offset + 4 * index++, &value, 4);
  };
  auto putInt = [&](size_t offset, int32_t value) { std::memcpy(bytes.data() + offset, &value, 4); };
  auto putFloat = [&](size_t offset, float value) { std::memcpy(bytes.data() + offset, &value, 4); };
  putFloats(0, {(float)kSourceWidth, (float)kSourceHeight, 1.0f / kSourceWidth, 1.0f / kSourceHeight});
  putFloats(16, {(float)kTargetWidth, (float)kTargetHeight, 1.0f / kTargetWidth, 1.0f / kTargetHeight});
  putFloats(32, {(float)kTargetWidth, (float)kTargetHeight, 1.0f / kTargetWidth, 1.0f / kTargetHeight});
  // stereo_views (48) is left zero: the revision does not fill it.
  putFloats(64, {0.0f, 0.0f, 1.0f, 1.0f});  // src_rect: the whole picture
  putInt(80, 0);                            // src_layer
  std::memcpy(bytes.data() + 84, &milliseconds, 4);
  putInt(88, kAPIMetal);
  putInt(92, 0);      // intermediary_buffer
  putInt(96, 0);      // resampling_method: default
  putInt(100, 0);     // correct_color_space
  putInt(104, 0);     // game_color_space
  putInt(108, 0);     // correct_gamma
  putFloat(112, 2.35f);
  putInt(116, 1);     // sdr_display_gamma_sRGB
  putFloat(120, 2.2f);
  putInt(124, 0);     // linear_space_output
  putInt(128, 0);     // hdr_output
  putFloat(132, 200.0f);
  putFloat(136, 80.0f);
  for (const neoshader::DolphinOption &option : shader.options) {
    const size_t offset = option.uniformOffset;
    if (offset + 16 > bytes.size()) continue;
    for (size_t component = 0; component < option.values.size() && component < 4; component++) {
      const double value = option.values[component];
      if (option.type == neoshader::DolphinOptionType::Float) {
        putFloat(offset + 4 * component, (float)value);
      } else {
        putInt(offset + 4 * component, (int32_t)std::lround(value));
      }
    }
  }
  return bytes;
}

class Validator {
 public:
  explicit Validator(id<MTLDevice> device) : device_(device), queue_([device newCommandQueue]) {
    MTLSamplerDescriptor *sampler = [MTLSamplerDescriptor new];
    sampler.minFilter = MTLSamplerMinMagFilterLinear;
    sampler.magFilter = MTLSamplerMinMagFilterLinear;
    sampler.sAddressMode = MTLSamplerAddressModeClampToEdge;
    sampler.tAddressMode = MTLSamplerAddressModeClampToEdge;
    sampler.rAddressMode = MTLSamplerAddressModeClampToEdge;
    sampler_ = [device newSamplerStateWithDescriptor:sampler];
    MTLTextureDescriptor *source = [MTLTextureDescriptor new];
    source.textureType = MTLTextureType2DArray;
    source.pixelFormat = MTLPixelFormatRGBA8Unorm;
    source.width = kSourceWidth;
    source.height = kSourceHeight;
    source.arrayLength = 1;
    source.usage = MTLTextureUsageShaderRead;
    for (int frame = 0; frame < kFrames; frame++) {
      id<MTLTexture> texture = [device newTextureWithDescriptor:source];
      const std::vector<uint8_t> rgba = TestPicture(frame);
      [texture replaceRegion:MTLRegionMake2D(0, 0, kSourceWidth, kSourceHeight)
                 mipmapLevel:0
                       slice:0
                   withBytes:rgba.data()
                 bytesPerRow:kSourceWidth * 4
               bytesPerImage:kSourceWidth * kSourceHeight * 4];
      pictures_.push_back(texture);
    }
    MTLTextureDescriptor *target = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatBGRA8Unorm
                                                                                      width:kTargetWidth
                                                                                     height:kTargetHeight
                                                                                  mipmapped:NO];
    target.usage = MTLTextureUsageRenderTarget | MTLTextureUsageShaderRead;
    target.storageMode = MTLStorageModePrivate;
    target_ = [device newTextureWithDescriptor:target];
    readback_ = [device newBufferWithLength:kTargetWidth * kTargetHeight * 4 options:MTLResourceStorageModeShared];
  }

  /// The pass-through draw every result is compared with.
  bool prepareReference(std::string *problem) {
    Result result;
    if (!render(kPassThrough, &result, nullptr)) {
      *problem = result.code + " " + result.detail;
      return false;
    }
    const uint8_t *bytes = (const uint8_t *)readback_.contents;
    reference_.assign(bytes, bytes + kTargetWidth * kTargetHeight * 4);
    return true;
  }

  Result validate(const std::string &code) {
    Result result;
    std::vector<double> gpu;
    if (!render(code, &result, &gpu)) return result;
    std::sort(gpu.begin(), gpu.end());
    result.gpuMilliseconds = gpu.empty() ? 0 : gpu[gpu.size() / 2];
    measure(&result);
    result.stage = "visible";
    if (result.litFraction < kMinimumLitFraction) {
      result.code = "BLACK_OUTPUT";
    } else if (result.colors < kMinimumColors) {
      result.code = "UNIFORM_OUTPUT";
    } else if (result.changedFraction < kMinimumChangedFraction) {
      result.code = "NO_VISIBLE_EFFECT";
    } else {
      result.ok = true;
      result.stage = "done";
    }
    return result;
  }

 private:
  /// Translates, compiles and draws `code` for three moving frames (then
  /// four more for the GPU time); the last moving frame is in readback_.
  bool render(const std::string &code, Result *result, std::vector<double> *gpu) {
    const CFAbsoluteTime start = CFAbsoluteTimeGetCurrent();
    neoshader::DolphinPostProcessShader shader;
    neoshader::ShaderError error;
    neoshader::DolphinTranslateOptions options;
    options.iosPlatform = false;  // the macOS device; iPhone MSL is compiled by xcrun in the test
    if (!neoshader::translateDolphinPostProcess(code, options, &shader, &error)) {
      result->code = error.code;
      result->detail = error.detail;
      return false;
    }
    result->options = OptionsJson(shader.options);
    result->uniformBytes = shader.uniformBytes;
    result->stage = "compile";
    NSError *metalError = nil;
    id<MTLLibrary> fragmentLibrary =
        [device_ newLibraryWithSource:[NSString stringWithUTF8String:shader.fragmentMSL.c_str()] options:nil error:&metalError];
    id<MTLLibrary> vertexLibrary =
        fragmentLibrary != nil
            ? [device_ newLibraryWithSource:[NSString stringWithUTF8String:shader.vertexMSL.c_str()] options:nil error:&metalError]
            : nil;
    id<MTLFunction> fragment =
        [fragmentLibrary newFunctionWithName:[NSString stringWithUTF8String:shader.fragmentEntry.c_str()]];
    id<MTLFunction> vertex = [vertexLibrary newFunctionWithName:[NSString stringWithUTF8String:shader.vertexEntry.c_str()]];
    if (fragment == nil || vertex == nil) {
      result->code = "METAL_LIBRARY_FAILED";
      result->detail = metalError.localizedDescription.UTF8String ?: "entry point missing";
      return false;
    }
    MTLRenderPipelineDescriptor *descriptor = [MTLRenderPipelineDescriptor new];
    descriptor.vertexFunction = vertex;
    descriptor.fragmentFunction = fragment;
    descriptor.colorAttachments[0].pixelFormat = MTLPixelFormatBGRA8Unorm;
    id<MTLRenderPipelineState> pipeline = [device_ newRenderPipelineStateWithDescriptor:descriptor error:&metalError];
    if (pipeline == nil) {
      result->code = "METAL_PIPELINE_FAILED";
      result->detail = metalError.localizedDescription.UTF8String ?: "";
      return false;
    }
    result->compileSeconds = CFAbsoluteTimeGetCurrent() - start;
    result->stage = "render";
    for (int frame = 0; frame < kFrames + (gpu != nullptr ? 4 : 0); frame++) {
      const int picture = std::min(frame, kFrames - 1);
      const std::vector<uint8_t> uniforms = Uniforms(shader, (uint32_t)(frame * 16));
      id<MTLCommandBuffer> buffer = [queue_ commandBuffer];
      MTLRenderPassDescriptor *pass = [MTLRenderPassDescriptor renderPassDescriptor];
      pass.colorAttachments[0].texture = target_;
      pass.colorAttachments[0].loadAction = MTLLoadActionClear;
      pass.colorAttachments[0].clearColor = MTLClearColorMake(0, 0, 0, 1);
      pass.colorAttachments[0].storeAction = MTLStoreActionStore;
      id<MTLRenderCommandEncoder> encoder = [buffer renderCommandEncoderWithDescriptor:pass];
      [encoder setRenderPipelineState:pipeline];
      // MTLUtil.mm bindings: the uniform block is buffer 1 of the vertex
      // stage and buffer 0 of the fragment stage; samp0 / samp1 are
      // texture and sampler 0 / 1.
      [encoder setVertexBytes:uniforms.data() length:uniforms.size() atIndex:1];
      [encoder setFragmentBytes:uniforms.data() length:uniforms.size() atIndex:0];
      [encoder setFragmentTexture:pictures_[picture] atIndex:0];
      [encoder setFragmentTexture:pictures_[picture] atIndex:1];
      [encoder setFragmentSamplerState:sampler_ atIndex:0];
      [encoder setFragmentSamplerState:sampler_ atIndex:1];
      [encoder drawPrimitives:MTLPrimitiveTypeTriangle vertexStart:0 vertexCount:3];
      [encoder endEncoding];
      if (frame == kFrames - 1) {
        id<MTLBlitCommandEncoder> blit = [buffer blitCommandEncoder];
        [blit copyFromTexture:target_
                         sourceSlice:0
                         sourceLevel:0
                        sourceOrigin:MTLOriginMake(0, 0, 0)
                          sourceSize:MTLSizeMake(kTargetWidth, kTargetHeight, 1)
                            toBuffer:readback_
                   destinationOffset:0
              destinationBytesPerRow:kTargetWidth * 4
            destinationBytesPerImage:kTargetWidth * kTargetHeight * 4];
        [blit endEncoding];
      }
      [buffer commit];
      [buffer waitUntilCompleted];
      if (buffer.status != MTLCommandBufferStatusCompleted) {
        result->code = "GPU_ERROR";
        result->detail = buffer.error.localizedDescription.UTF8String ?: "";
        result->gpuError = true;
        return false;
      }
      if (gpu != nullptr && frame >= kFrames) gpu->push_back((buffer.GPUEndTime - buffer.GPUStartTime) * 1000.0);
    }
    return true;
  }

  void measure(Result *result) {
    const uint8_t *bytes = (const uint8_t *)readback_.contents;
    unsigned long long changed = 0, lit = 0;
    double difference = 0;
    std::set<uint32_t> colors;
    for (NSUInteger index = 0; index < kTargetWidth * kTargetHeight; index++) {
      const uint8_t *pixel = bytes + index * 4;
      const uint8_t *reference = reference_.data() + index * 4;
      bool pixelChanged = false;
      for (int channel = 0; channel < 3; channel++) {
        const double delta = std::fabs((double)pixel[channel] - (double)reference[channel]);
        difference += delta;
        if (delta >= kChangedThreshold) pixelChanged = true;
      }
      if (pixelChanged) changed++;
      if (pixel[0] + pixel[1] + pixel[2] > 6) lit++;
      if (colors.size() < 4096) colors.insert(((uint32_t)pixel[2] << 16) | ((uint32_t)pixel[1] << 8) | pixel[0]);
    }
    const double count = (double)kTargetWidth * kTargetHeight;
    result->changedFraction = changed / count;
    result->meanDifference = difference / (count * 3.0);
    result->litFraction = lit / count;
    result->colors = colors.size();
  }

  id<MTLDevice> device_;
  id<MTLCommandQueue> queue_;
  id<MTLSamplerState> sampler_;
  std::vector<id<MTLTexture>> pictures_;
  id<MTLTexture> target_;
  id<MTLBuffer> readback_;
  std::vector<uint8_t> reference_;
};

}  // namespace

int main(int argc, const char *argv[]) {
  @autoreleasepool {
    if (argc != 3) {
      std::fprintf(stderr, "usage: neoshader-dolphin-validate LIST_FILE OUTPUT_JSONL\n");
      return 2;
    }
    id<MTLDevice> device = MTLCreateSystemDefaultDevice();
    if (device == nil) {
      std::fprintf(stderr, "NO METAL DEVICE\n");
      return 3;
    }
    std::ifstream list(argv[1]);
    std::ofstream output(argv[2], std::ios::app);
    if (!list || !output) {
      std::fprintf(stderr, "cannot open the list or the output\n");
      return 2;
    }
    Validator validator(device);
    std::string problem;
    if (!validator.prepareReference(&problem)) {
      std::fprintf(stderr, "the pass-through shader does not render: %s\n", problem.c_str());
      return 2;
    }
    std::string line;
    int failures = 0, total = 0;
    while (std::getline(list, line)) {
      if (line.empty()) continue;
      @autoreleasepool {
        total++;
        std::ifstream input(line, std::ios::binary);
        std::stringstream code;
        code << input.rdbuf();
        Result result;
        if (!input) {
          result.code = "UNREADABLE";
        } else {
          result = validator.validate(code.str());
        }
        if (!result.ok) failures++;
        output << Json(line, result) << "\n";
        output.flush();
        std::printf("%s %s %s\n", result.ok ? "ok  " : "FAIL", line.c_str(), result.ok ? "" : result.code.c_str());
        std::fflush(stdout);
        if (result.gpuError) {
          std::printf("GPU error: stopping so that a new process validates the rest\n");
          return kGPUErrorExit;
        }
      }
    }
    std::printf("%d Dolphin shaders, %d failed (Metal device: %s)\n", total, failures, device.name.UTF8String);
    return failures == 0 ? 0 : 1;
  }
}
