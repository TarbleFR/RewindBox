// SPDX-License-Identifier: GPL-3.0-or-later
// Metal validation of catalog presets (macOS, CI): each preset goes through
// the application's own program and chain code (NeoSlangRenderer.mm), is
// rendered for three frames of a moving synthetic picture, and its last
// output is read back and compared with a plain nearest upscale of the same
// picture. A preset passes only when it compiled, rendered and visibly
// changed the picture:
//
//   neoshader-metal-validate ROOT LIST_FILE OUTPUT_JSONL
//
// LIST_FILE holds one repository-relative preset path per line. One JSON
// line is written per preset (flushed at once, so a crash loses nothing):
// {"preset", "ok", "stage", "code", "detail", "passes", "compileSeconds",
//  "gpuMilliseconds", "changedFraction", "meanDifference", "litFraction",
//  "colors", "finite"}. Exit status: 0 when every preset passed, 1 when one
// failed, 2 on usage errors, 3 without a Metal device.
#import <Foundation/Foundation.h>
#import <Metal/Metal.h>

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <set>
#include <string>
#include <vector>

#import "NeoSlangRenderer.h"

namespace {

/// Picture of a typical 2D game frame and an output that is not an integer
/// multiple of it (an integer scale would make some upscalers identical to
/// nearest), close to an iPhone game area.
constexpr NSUInteger kPictureWidth = 320;
constexpr NSUInteger kPictureHeight = 240;
constexpr NSUInteger kOutputWidth = 1186;
constexpr NSUInteger kOutputHeight = 890;
constexpr int kFrames = 3;
/// A channel differing by at least this much from the nearest upscale
/// counts as changed; a preset must change this fraction of the pixels.
constexpr int kChangedThreshold = 3;
constexpr double kMinimumChangedFraction = 0.001;
/// Pixels brighter than black, and distinct colours, a real picture keeps.
constexpr double kMinimumLitFraction = 0.02;
constexpr size_t kMinimumColors = 8;

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

/// Synthetic frame `frame` (RGBA8, top row first): colour bars, gradients,
/// a checkerboard, thin lines, "sprites" and text-like glyphs, shifted by
/// one pixel per frame so motion-based shaders see movement. Deterministic.
std::vector<uint8_t> TestPicture(int frame) {
  std::vector<uint8_t> rgba(kPictureWidth * kPictureHeight * 4);
  for (NSUInteger y = 0; y < kPictureHeight; y++) {
    for (NSUInteger x = 0; x < kPictureWidth; x++) {
      const NSUInteger sx = (x + (NSUInteger)frame) % kPictureWidth;
      uint8_t r = 0, g = 0, b = 0;
      if (y < 60) {
        // Eight colour bars.
        const unsigned bar = (unsigned)(sx * 8 / kPictureWidth);
        r = (bar & 1) ? 230 : 20;
        g = (bar & 2) ? 220 : 30;
        b = (bar & 4) ? 210 : 40;
      } else if (y < 120) {
        // Horizontal and vertical gradients.
        r = (uint8_t)(sx * 255 / (kPictureWidth - 1));
        g = (uint8_t)((y - 60) * 255 / 59);
        b = (uint8_t)(255 - r / 2);
      } else if (y < 180) {
        // Checkerboard of 1, 2 and 4 pixel cells with thin lines.
        const NSUInteger cell = sx < 106 ? 1 : (sx < 213 ? 2 : 4);
        const bool on = ((sx / cell) + (y / cell)) % 2 == 0;
        r = g = b = on ? 235 : 25;
        if ((sx + y) % 17 == 0) { r = 250; g = 60; b = 60; }
      } else {
        // Dark background with sprites and glyph-like strokes.
        r = 16; g = 24; b = 48;
        const NSUInteger glyph = sx % 12;
        const NSUInteger row = (y - 180) % 14;
        if (glyph < 8 && row < 10 && ((glyph * 7 + row * 3 + sx / 12) % 5) < 2) { r = 240; g = 240; b = 200; }
        const NSUInteger ox = sx % 64, oy = (y - 180) % 32;
        if (ox > 40 && ox < 56 && oy > 6 && oy < 26) { r = 60; g = 200; b = 90; }
      }
      uint8_t *pixel = rgba.data() + (y * kPictureWidth + x) * 4;
      pixel[0] = r;
      pixel[1] = g;
      pixel[2] = b;
      pixel[3] = 255;
    }
  }
  return rgba;
}

struct Result {
  bool ok = false;
  std::string stage = "compile";
  std::string code;
  std::string detail;
  unsigned long passes = 0;
  double compileSeconds = 0;
  double gpuMilliseconds = 0;
  double changedFraction = 0;
  double meanDifference = 0;
  double litFraction = 0;
  size_t colors = 0;
  bool finite = true;
};

std::string Json(const std::string &preset, const Result &result) {
  char numbers[512];
  std::snprintf(numbers, sizeof(numbers),
                "\"passes\":%lu,\"compileSeconds\":%.4f,\"gpuMilliseconds\":%.4f,\"changedFraction\":%.6f,"
                "\"meanDifference\":%.4f,\"litFraction\":%.6f,\"colors\":%zu,\"finite\":%s",
                result.passes, result.compileSeconds, result.gpuMilliseconds, result.changedFraction,
                result.meanDifference, result.litFraction, result.colors, result.finite ? "true" : "false");
  return "{\"preset\":" + Quote(preset) + ",\"ok\":" + (result.ok ? "true" : "false") +
         ",\"stage\":" + Quote(result.stage) + ",\"code\":" + Quote(result.code) + ",\"detail\":" +
         Quote(result.detail.substr(0, 2000)) + "," + numbers + "}";
}

class Validator {
 public:
  Validator(id<MTLDevice> device, NSString *root) : device_(device), queue_([device newCommandQueue]), root_(root) {
    for (int frame = 0; frame < kFrames; frame++) {
      const std::vector<uint8_t> rgba = TestPicture(frame);
      std::vector<uint8_t> bgra(rgba.size());
      for (size_t index = 0; index < kPictureWidth * kPictureHeight; index++) {
        bgra[index * 4 + 0] = rgba[index * 4 + 2];
        bgra[index * 4 + 1] = rgba[index * 4 + 1];
        bgra[index * 4 + 2] = rgba[index * 4 + 0];
        bgra[index * 4 + 3] = rgba[index * 4 + 3];
      }
      uploads_.push_back([device newBufferWithBytes:bgra.data() length:bgra.size() options:MTLResourceStorageModeShared]);
      if (frame == kFrames - 1) last_ = rgba;
    }
    readback_ = [device newBufferWithLength:kOutputWidth * kOutputHeight * 16 options:MTLResourceStorageModeShared];
  }

  Result validate(NSString *preset) {
    Result result;
    NSError *error = nil;
    const CFAbsoluteTime start = CFAbsoluteTimeGetCurrent();
    NeoSlangProgram *program = nil;
    @try {
      program = [NeoSlangProgram programWithRoot:root_ preset:preset device:device_ iosPlatform:NO error:&error];
    } @catch (NSException *exception) {
      result.code = "EXCEPTION";
      result.detail = exception.reason.UTF8String ?: "";
      return result;
    }
    result.compileSeconds = CFAbsoluteTimeGetCurrent() - start;
    if (program == nil) {
      result.code = [error.userInfo[NeoSlangErrorCodeKey] UTF8String] ?: "UNKNOWN";
      result.detail = [error.userInfo[NSDebugDescriptionErrorKey] UTF8String] ?: "";
      return result;
    }
    result.passes = program.passCount;
    result.stage = "render";
    NeoSlangChain *chain = [[NeoSlangChain alloc] initWithProgram:program];
    id<MTLTexture> output = nil;
    std::vector<double> gpu;
    for (int frame = 0; frame < kFrames + 4; frame++) {
      // Frames 0-2 move the picture; the next ones repeat the last picture
      // and give the GPU time (median).
      const int picture = std::min(frame, kFrames - 1);
      id<MTLCommandBuffer> buffer = [queue_ commandBuffer];
      id<MTLTexture> original = [chain originalTextureWithWidth:kPictureWidth height:kPictureHeight];
      if (original == nil) {
        result.code = "CHAIN_ALLOCATION";
        return result;
      }
      id<MTLBlitCommandEncoder> blit = [buffer blitCommandEncoder];
      [blit copyFromBuffer:uploads_[picture]
                 sourceOffset:0
            sourceBytesPerRow:kPictureWidth * 4
          sourceBytesPerImage:kPictureWidth * kPictureHeight * 4
                   sourceSize:MTLSizeMake(kPictureWidth, kPictureHeight, 1)
                    toTexture:original
             destinationSlice:0
             destinationLevel:0
            destinationOrigin:MTLOriginMake(0, 0, 0)];
      [blit endEncoding];
      NeoSlangFrameState state;
      std::memset(&state, 0, sizeof(state));
      state.frameCount = (uint32_t)frame;
      state.frameDirection = 1;
      state.coreAspect = 4.0f / 3.0f;
      state.coreFPS = 60.0f;
      state.frameTimeDelta = 16667;
      state.swapCount = 1;
      output = [chain encodeOnCommandBuffer:buffer
                                 outputSize:CGSizeMake(kOutputWidth, kOutputHeight)
                               viewportSize:CGSizeMake(kOutputWidth, kOutputHeight)
                                      frame:state
                                     smooth:NO];
      if (output == nil) {
        [buffer commit];
        result.code = chain.lastFailureCode.UTF8String ?: "CHAIN_FAILED";
        result.detail = chain.lastFailureDetail.UTF8String ?: "";
        return result;
      }
      if (frame == kFrames - 1) copyToReadback(buffer, output);
      [buffer commit];
      [buffer waitUntilCompleted];
      if (buffer.status != MTLCommandBufferStatusCompleted) {
        result.code = "GPU_ERROR";
        result.detail = buffer.error.localizedDescription.UTF8String ?: "";
        return result;
      }
      if (frame == kFrames - 1) {
        if (!measure(output, &result)) return result;
      } else if (frame >= kFrames) {
        gpu.push_back((buffer.GPUEndTime - buffer.GPUStartTime) * 1000.0);
      }
    }
    std::sort(gpu.begin(), gpu.end());
    result.gpuMilliseconds = gpu.empty() ? 0 : gpu[gpu.size() / 2];
    result.stage = "visible";
    if (!result.finite) {
      result.code = "NOT_FINITE";
    } else if (result.litFraction < kMinimumLitFraction) {
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
  void copyToReadback(id<MTLCommandBuffer> buffer, id<MTLTexture> output) {
    const NSUInteger bytesPerPixel = BytesPerPixel(output.pixelFormat);
    id<MTLBlitCommandEncoder> blit = [buffer blitCommandEncoder];
    [blit copyFromTexture:output
                     sourceSlice:0
                     sourceLevel:0
                    sourceOrigin:MTLOriginMake(0, 0, 0)
                      sourceSize:MTLSizeMake(output.width, output.height, 1)
                        toBuffer:readback_
               destinationOffset:0
          destinationBytesPerRow:output.width * bytesPerPixel
        destinationBytesPerImage:output.width * output.height * bytesPerPixel];
    [blit endEncoding];
  }

  static NSUInteger BytesPerPixel(MTLPixelFormat format) {
    switch (format) {
      case MTLPixelFormatRGBA16Float: return 8;
      case MTLPixelFormatRGBA32Float: return 16;
      case MTLPixelFormatR8Unorm: return 1;
      case MTLPixelFormatRG8Unorm:
      case MTLPixelFormatR16Float: return 2;
      case MTLPixelFormatRG16Float:
      case MTLPixelFormatR32Float: return 4;
      case MTLPixelFormatRG32Float: return 8;
      default: return 4;
    }
  }

  /// Reads the output as RGB in [0,255] (whatever its format), scales it to
  /// the output size if the last pass has another size (as the presenter's
  /// final draw does), and compares it with the nearest upscale.
  bool measure(id<MTLTexture> output, Result *result) {
    const NSUInteger width = output.width;
    const NSUInteger height = output.height;
    const MTLPixelFormat format = output.pixelFormat;
    const uint8_t *bytes = (const uint8_t *)readback_.contents;
    std::vector<float> rgb(width * height * 3, 0.0f);
    for (NSUInteger index = 0; index < width * height; index++) {
      float value[4] = {0, 0, 0, 1};
      switch (format) {
        case MTLPixelFormatBGRA8Unorm:
          value[0] = bytes[index * 4 + 2];
          value[1] = bytes[index * 4 + 1];
          value[2] = bytes[index * 4 + 0];
          break;
        case MTLPixelFormatRGBA8Unorm:
        case MTLPixelFormatRGBA8Unorm_sRGB:
          for (int channel = 0; channel < 3; channel++) value[channel] = bytes[index * 4 + channel];
          break;
        case MTLPixelFormatRGB10A2Unorm: {
          uint32_t packed;
          std::memcpy(&packed, bytes + index * 4, 4);
          value[0] = (float)(packed & 0x3FF) * 255.0f / 1023.0f;
          value[1] = (float)((packed >> 10) & 0x3FF) * 255.0f / 1023.0f;
          value[2] = (float)((packed >> 20) & 0x3FF) * 255.0f / 1023.0f;
          break;
        }
        case MTLPixelFormatRGBA16Float:
          for (int channel = 0; channel < 3; channel++) {
            __fp16 half;
            std::memcpy(&half, bytes + index * 8 + channel * 2, 2);
            value[channel] = (float)half * 255.0f;
          }
          break;
        case MTLPixelFormatRGBA32Float:
          for (int channel = 0; channel < 3; channel++) {
            float number;
            std::memcpy(&number, bytes + index * 16 + channel * 4, 4);
            value[channel] = number * 255.0f;
          }
          break;
        default:
          result->code = "OUTPUT_FORMAT";
          result->detail = std::to_string((unsigned long)format);
          return false;
      }
      for (int channel = 0; channel < 3; channel++) {
        if (!std::isfinite(value[channel])) result->finite = false;
        rgb[index * 3 + channel] = std::isfinite(value[channel]) ? std::min(std::max(value[channel], 0.0f), 255.0f) : 0.0f;
      }
    }
    unsigned long long changed = 0, lit = 0;
    double difference = 0;
    std::set<uint32_t> colors;
    for (NSUInteger y = 0; y < kOutputHeight; y++) {
      for (NSUInteger x = 0; x < kOutputWidth; x++) {
        // Output pixel as drawn at the output size (nearest from the last
        // pass when it has another size).
        const NSUInteger ox = std::min(width - 1, x * width / kOutputWidth);
        const NSUInteger oy = std::min(height - 1, y * height / kOutputHeight);
        const float *pixel = rgb.data() + (oy * width + ox) * 3;
        const NSUInteger px = std::min(kPictureWidth - 1, (NSUInteger)((x + 0.5) * kPictureWidth / kOutputWidth));
        const NSUInteger py = std::min(kPictureHeight - 1, (NSUInteger)((y + 0.5) * kPictureHeight / kOutputHeight));
        const uint8_t *reference = last_.data() + (py * kPictureWidth + px) * 4;
        bool pixelChanged = false;
        for (int channel = 0; channel < 3; channel++) {
          const double delta = std::fabs((double)pixel[channel] - (double)reference[channel]);
          difference += delta;
          if (delta >= kChangedThreshold) pixelChanged = true;
        }
        if (pixelChanged) changed++;
        if (pixel[0] + pixel[1] + pixel[2] > 6.0f) lit++;
        if (colors.size() < 4096) {
          colors.insert(((uint32_t)pixel[0] << 16) | ((uint32_t)pixel[1] << 8) | (uint32_t)pixel[2]);
        }
      }
    }
    const double count = (double)kOutputWidth * kOutputHeight;
    result->changedFraction = changed / count;
    result->meanDifference = difference / (count * 3.0);
    result->litFraction = lit / count;
    result->colors = colors.size();
    return true;
  }

  id<MTLDevice> device_;
  id<MTLCommandQueue> queue_;
  NSString *root_;
  std::vector<id<MTLBuffer>> uploads_;
  std::vector<uint8_t> last_;
  id<MTLBuffer> readback_;
};

}  // namespace

int main(int argc, const char *argv[]) {
  @autoreleasepool {
    if (argc != 4) {
      std::fprintf(stderr, "usage: neoshader-metal-validate ROOT LIST_FILE OUTPUT_JSONL\n");
      return 2;
    }
    id<MTLDevice> device = MTLCreateSystemDefaultDevice();
    if (device == nil) {
      std::fprintf(stderr, "NO METAL DEVICE\n");
      return 3;
    }
    std::ifstream list(argv[2]);
    std::ofstream output(argv[3], std::ios::app);
    if (!list || !output) {
      std::fprintf(stderr, "cannot open the list or the output\n");
      return 2;
    }
    Validator validator(device, [NSString stringWithUTF8String:argv[1]]);
    std::string line;
    int failures = 0, total = 0;
    while (std::getline(list, line)) {
      if (line.empty()) continue;
      @autoreleasepool {
        total++;
        const Result result = validator.validate([NSString stringWithUTF8String:line.c_str()]);
        if (!result.ok) failures++;
        output << Json(line, result) << "\n";
        output.flush();
        std::printf("%s %s %s\n", result.ok ? "ok  " : "FAIL", line.c_str(), result.ok ? "" : result.code.c_str());
        std::fflush(stdout);
      }
    }
    std::printf("%d presets, %d failed (Metal device: %s)\n", total, failures, device.name.UTF8String);
    return failures == 0 ? 0 : 1;
  }
}
