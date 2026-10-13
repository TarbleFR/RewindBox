// SPDX-License-Identifier: GPL-3.0-or-later
// Render tests of the shader kit's Metal runtime (NeoSlangRenderer.mm) on a
// macOS Metal device: every check reads back pixels the GPU produced through
// the same program / chain code the application runs, from the presets and
// shaders written by test/neo_shader_kit_render_test.py.
//
//   neoshader-render-tests FIXTURES_DIRECTORY
//
// Exit status: 0 all checks passed, 1 a check failed, 3 no Metal device.
#import <Foundation/Foundation.h>
#import <Metal/Metal.h>

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

#import "NeoSlangRenderer.h"

static int g_checks = 0;
static int g_failures = 0;

#define CHECK(condition, ...)                                   \
  do {                                                          \
    g_checks++;                                                 \
    if (!(condition)) {                                         \
      g_failures++;                                             \
      std::fprintf(stderr, "FAILED %s:%d: ", __FILE__, __LINE__); \
      std::fprintf(stderr, __VA_ARGS__);                        \
      std::fprintf(stderr, "\n");                               \
    }                                                           \
  } while (0)

namespace {

struct Picture {
  NSUInteger width = 0;
  NSUInteger height = 0;
  std::vector<uint8_t> rgba;  // straight RGBA8, top row first
  const uint8_t *at(NSUInteger x, NSUInteger y) const { return rgba.data() + (y * width + x) * 4; }
};

Picture Gradient(NSUInteger width, NSUInteger height) {
  Picture picture;
  picture.width = width;
  picture.height = height;
  picture.rgba.resize(width * height * 4);
  for (NSUInteger y = 0; y < height; y++) {
    for (NSUInteger x = 0; x < width; x++) {
      uint8_t *pixel = picture.rgba.data() + (y * width + x) * 4;
      pixel[0] = (uint8_t)(x * 30 + 5);
      pixel[1] = (uint8_t)(y * 40 + 7);
      pixel[2] = 100;
      pixel[3] = 255;
    }
  }
  return picture;
}

Picture Solid(NSUInteger width, NSUInteger height, uint8_t r, uint8_t g, uint8_t b) {
  Picture picture;
  picture.width = width;
  picture.height = height;
  picture.rgba.resize(width * height * 4);
  for (NSUInteger index = 0; index < width * height; index++) {
    picture.rgba[index * 4 + 0] = r;
    picture.rgba[index * 4 + 1] = g;
    picture.rgba[index * 4 + 2] = b;
    picture.rgba[index * 4 + 3] = 255;
  }
  return picture;
}

Picture Checkerboard(NSUInteger size) {
  Picture picture;
  picture.width = size;
  picture.height = size;
  picture.rgba.resize(size * size * 4);
  for (NSUInteger y = 0; y < size; y++) {
    for (NSUInteger x = 0; x < size; x++) {
      const uint8_t value = ((x + y) % 2) == 0 ? 0 : 255;
      uint8_t *pixel = picture.rgba.data() + (y * size + x) * 4;
      pixel[0] = pixel[1] = pixel[2] = value;
      pixel[3] = 255;
    }
  }
  return picture;
}

/// Pixels read back from a result texture: RGBA floats (unorm formats
/// normalized to [0,1]).
struct Pixels {
  NSUInteger width = 0;
  NSUInteger height = 0;
  MTLPixelFormat format = MTLPixelFormatInvalid;
  std::vector<float> rgba;
  const float *at(NSUInteger x, NSUInteger y) const { return rgba.data() + (y * width + x) * 4; }
  /// 8-bit value of a channel of a unorm result.
  int byte(NSUInteger x, NSUInteger y, int channel) const { return (int)std::lround(at(x, y)[channel] * 255.0f); }
};

class Harness {
 public:
  explicit Harness(id<MTLDevice> device, NSString *fixtures)
      : device_(device), queue_([device newCommandQueue]), fixtures_(fixtures) {}

  NeoSlangProgram *program(NSString *preset, NSError **error = nullptr) {
    NSError *failure = nil;
    NeoSlangProgram *program = [NeoSlangProgram programWithRoot:fixtures_
                                                         preset:preset
                                                         device:device_
                                                    iosPlatform:NO
                                                          error:&failure];
    if (error != nullptr) *error = failure;
    if (program == nil && error == nullptr) {
      std::fprintf(stderr, "program %s failed: %s %s\n", preset.UTF8String,
                   [failure.userInfo[NeoSlangErrorCodeKey] UTF8String] ?: "?",
                   [failure.userInfo[NSDebugDescriptionErrorKey] UTF8String] ?: "");
    }
    return program;
  }

  /// One frame: uploads `picture` into the chain's Original, encodes, and
  /// reads the result back. `ok` is NO when the encode returned nil.
  Pixels frame(NeoSlangChain *chain, const Picture &picture, CGSize output, CGSize viewport, NeoSlangFrameState state,
               BOOL smooth, BOOL *ok) {
    Pixels pixels;
    *ok = NO;
    id<MTLCommandBuffer> buffer = [queue_ commandBuffer];
    id<MTLTexture> original = [chain originalTextureWithWidth:picture.width height:picture.height];
    if (original == nil) return pixels;
    std::vector<uint8_t> bgra(picture.rgba.size());
    for (size_t index = 0; index < picture.width * picture.height; index++) {
      bgra[index * 4 + 0] = picture.rgba[index * 4 + 2];
      bgra[index * 4 + 1] = picture.rgba[index * 4 + 1];
      bgra[index * 4 + 2] = picture.rgba[index * 4 + 0];
      bgra[index * 4 + 3] = picture.rgba[index * 4 + 3];
    }
    id<MTLBuffer> upload = [device_ newBufferWithBytes:bgra.data()
                                                length:bgra.size()
                                               options:MTLResourceStorageModeShared];
    id<MTLBlitCommandEncoder> blit = [buffer blitCommandEncoder];
    [blit copyFromBuffer:upload
               sourceOffset:0
          sourceBytesPerRow:picture.width * 4
        sourceBytesPerImage:bgra.size()
                 sourceSize:MTLSizeMake(picture.width, picture.height, 1)
                  toTexture:original
           destinationSlice:0
           destinationLevel:0
          destinationOrigin:MTLOriginMake(0, 0, 0)];
    [blit endEncoding];
    id<MTLTexture> result = [chain encodeOnCommandBuffer:buffer
                                              outputSize:output
                                            viewportSize:viewport
                                                   frame:state
                                                  smooth:smooth];
    if (result == nil) {
      [buffer commit];
      [buffer waitUntilCompleted];
      return pixels;
    }
    NSUInteger bytesPerPixel = 4;
    if (result.pixelFormat == MTLPixelFormatRGBA32Float) bytesPerPixel = 16;
    if (result.pixelFormat == MTLPixelFormatRGBA16Float) bytesPerPixel = 8;
    const NSUInteger rowBytes = result.width * bytesPerPixel;
    id<MTLBuffer> readback = [device_ newBufferWithLength:rowBytes * result.height
                                                  options:MTLResourceStorageModeShared];
    blit = [buffer blitCommandEncoder];
    [blit copyFromTexture:result
                     sourceSlice:0
                     sourceLevel:0
                    sourceOrigin:MTLOriginMake(0, 0, 0)
                      sourceSize:MTLSizeMake(result.width, result.height, 1)
                        toBuffer:readback
               destinationOffset:0
          destinationBytesPerRow:rowBytes
        destinationBytesPerImage:rowBytes * result.height];
    [blit endEncoding];
    [buffer commit];
    [buffer waitUntilCompleted];
    if (buffer.status != MTLCommandBufferStatusCompleted) return pixels;
    pixels.width = result.width;
    pixels.height = result.height;
    pixels.format = result.pixelFormat;
    pixels.rgba.resize(result.width * result.height * 4);
    const uint8_t *bytes = (const uint8_t *)readback.contents;
    for (NSUInteger index = 0; index < result.width * result.height; index++) {
      float *target = pixels.rgba.data() + index * 4;
      switch (result.pixelFormat) {
        case MTLPixelFormatBGRA8Unorm:
          target[0] = bytes[index * 4 + 2] / 255.0f;
          target[1] = bytes[index * 4 + 1] / 255.0f;
          target[2] = bytes[index * 4 + 0] / 255.0f;
          target[3] = bytes[index * 4 + 3] / 255.0f;
          break;
        case MTLPixelFormatRGBA8Unorm:
        case MTLPixelFormatRGBA8Unorm_sRGB:
          for (int channel = 0; channel < 4; channel++) target[channel] = bytes[index * 4 + channel] / 255.0f;
          break;
        case MTLPixelFormatRGBA32Float:
          std::memcpy(target, bytes + index * 16, 16);
          break;
        case MTLPixelFormatRGBA16Float:
          for (int channel = 0; channel < 4; channel++) {
            __fp16 half;
            std::memcpy(&half, bytes + index * 8 + channel * 2, 2);
            target[channel] = (float)half;
          }
          break;
        default:
          break;
      }
    }
    *ok = YES;
    return pixels;
  }

 private:
  id<MTLDevice> device_;
  id<MTLCommandQueue> queue_;
  NSString *fixtures_;
};

NeoSlangFrameState DefaultState() {
  NeoSlangFrameState state;
  std::memset(&state, 0, sizeof(state));
  state.frameCount = 1;
  state.frameDirection = 1;
  state.coreAspect = 4.0f / 3.0f;
  state.coreFPS = 60.0f;
  state.frameTimeDelta = 16667;
  state.swapCount = 1;
  return state;
}

bool Near(float value, float expected, float tolerance) { return std::fabs(value - expected) <= tolerance; }

NSString *ErrorCode(NSError *error) { return error.userInfo[NeoSlangErrorCodeKey]; }

void TestPassthrough(Harness &harness) {
  NeoSlangProgram *program = harness.program(@"stock.slangp");
  CHECK(program != nil, "stock.slangp compiles");
  if (program == nil) return;
  CHECK(program.passCount == 1 && program.historyDepth == 0 && program.parameters.count == 0,
        "stock: one pass, no history, no parameter");
  CHECK([program.files containsObject:@"stock.slangp"] && [program.files containsObject:@"stock.slang"],
        "stock: files list the preset and its source");
  NeoSlangChain *chain = [[NeoSlangChain alloc] initWithProgram:program];
  const Picture input = Gradient(8, 6);
  BOOL ok = NO;
  Pixels out = harness.frame(chain, input, CGSizeMake(16, 12), CGSizeMake(16, 12), DefaultState(), YES, &ok);
  CHECK(ok, "stock: encode succeeded (%s)", chain.lastFailureCode.UTF8String ?: "");
  if (!ok) return;
  CHECK(out.width == 16 && out.height == 12 && out.format == MTLPixelFormatBGRA8Unorm,
        "stock: last pass without scale renders the output size in BGRA8 (%lux%lu, format %lu)",
        (unsigned long)out.width, (unsigned long)out.height, (unsigned long)out.format);
  CHECK(chain.lastPassMatchesOutput, "stock: last pass matches the output");
  int mismatches = 0;
  for (NSUInteger y = 0; y < 12; y++) {
    for (NSUInteger x = 0; x < 16; x++) {
      const uint8_t *expected = input.at(x / 2, y / 2);
      for (int channel = 0; channel < 4; channel++) {
        if (out.byte(x, y, channel) != expected[channel]) mismatches++;
      }
    }
  }
  CHECK(mismatches == 0, "stock: nearest 2x copy, top row first (%d channel mismatches)", mismatches);
  CHECK(chain.textureBytes > 0, "stock: texture memory is reported");

  // Without filter_linear0, the "smooth" setting chooses: linear blends the
  // first two columns at x = 1 (texel 0.75: 5 * 0.75 + 35 * 0.25 = 12.5).
  // Row 5 is inside the picture: at the edges RetroArch's default
  // clamp_to_border also blends in its transparent black border.
  NeoSlangProgram *smoothProgram = harness.program(@"stock-smooth.slangp");
  CHECK(smoothProgram != nil, "stock-smooth.slangp compiles");
  if (smoothProgram == nil) return;
  NeoSlangChain *smoothChain = [[NeoSlangChain alloc] initWithProgram:smoothProgram];
  out = harness.frame(smoothChain, input, CGSizeMake(16, 12), CGSizeMake(16, 12), DefaultState(), YES, &ok);
  CHECK(ok && std::abs(out.byte(1, 5, 0) - 12.5) <= 1.0 && std::abs(out.byte(3, 5, 0) - 42.5) <= 1.0,
        "smooth: unspecified filter follows the smooth setting (red %d at x=1, %d at x=3)",
        ok ? out.byte(1, 5, 0) : -1, ok ? out.byte(3, 5, 0) : -1);
  CHECK(ok && out.byte(0, 0, 0) < 5, "smooth: clamp_to_border blends transparent black at the corner (red %d)",
        ok ? out.byte(0, 0, 0) : -1);
  out = harness.frame(smoothChain, input, CGSizeMake(16, 12), CGSizeMake(16, 12), DefaultState(), NO, &ok);
  CHECK(ok && out.byte(1, 5, 0) == 5 && out.byte(0, 0, 0) == 5, "smooth off: nearest (red %d at x=1)",
        ok ? out.byte(1, 5, 0) : -1);
}

void TestSemantics(Harness &harness) {
  NeoSlangProgram *program = harness.program(@"semantics.slangp");
  CHECK(program != nil, "semantics.slangp compiles");
  if (program == nil) return;
  CHECK(program.parameters.count == 2, "semantics: two parameters");
  const NSUInteger a = [program indexOfParameter:@"PARAM_A"];
  CHECK(a != NSNotFound, "semantics: PARAM_A found");
  if (a == NSNotFound || program.parameters.count < 2) return;
  NeoSlangParameterInfo *info = program.parameters[a];
  CHECK([info.label isEqualToString:@"Parameter A"] && info.initial == 0.5f && info.minimum == 0.0f &&
            info.maximum == 2.0f && Near(info.step, 0.1f, 1e-6f) && info.presetValue == 0.75f && !info.section,
        "semantics: PARAM_A declaration and preset value 0.75");
  NeoSlangChain *chain = [[NeoSlangChain alloc] initWithProgram:program];
  NeoSlangFrameState state = DefaultState();
  state.frameCount = 23;
  state.frameDirection = -1;
  state.rotation = 3;
  state.coreAspect = 1.25f;
  state.coreFPS = 59.94f;
  state.frameTimeDelta = 16667;
  BOOL ok = NO;
  Pixels out = harness.frame(chain, Gradient(8, 6), CGSizeMake(20, 10), CGSizeMake(30, 15), state, NO, &ok);
  CHECK(ok, "semantics: encode succeeded (%s)", chain.lastFailureCode.UTF8String ?: "");
  if (!ok) return;
  CHECK(out.width == 4 && out.height == 4 && out.format == MTLPixelFormatRGBA32Float,
        "semantics: absolute 4x4 pass in its #pragma format R32G32B32A32_SFLOAT");
  CHECK(!chain.lastPassMatchesOutput, "semantics: a scaled last pass does not match the output");
  struct Expected {
    int index;
    float values[4];
    const char *what;
  };
  const Expected expected[] = {
      {0, {4.0f, 4.0f, 0.25f, 0.25f}, "OutputSize"},
      {1, {8.0f, 6.0f, 0.125f, 1.0f / 6.0f}, "SourceSize"},
      {2, {8.0f, 6.0f, 0.125f, 1.0f / 6.0f}, "OriginalSize"},
      {3, {30.0f, 15.0f, 1.0f / 30.0f, 1.0f / 15.0f}, "FinalViewportSize"},
      {4, {2.0f, -1.0f, 3.0f, 1.25f}, "FrameCount % frame_count_mod, FrameDirection, Rotation, OriginalAspect"},
      {5, {0.8f, 59.94f, 16667.0f, 1.0f}, "OriginalAspectRotated, OriginalFPS, FrameTimeDelta, TotalSubFrames"},
      {6, {1.0f, 0.75f, 1.0f, 1.0f}, "CurrentSubFrame, PARAM_A (preset), PARAM_B (initial), Source alpha"},
      {7, {2.0f, 0.0f, 0.0f, 0.0f}, "MVP column 0"},
      {8, {0.0f, 2.0f, 0.0f, 0.0f}, "MVP column 1"},
      {9, {0.0f, 0.0f, 1.0f, 0.0f}, "MVP column 2"},
      {10, {-1.0f, -1.0f, 0.0f, 1.0f}, "MVP column 3"},
      {12, {0.125f, 0.875f, 0.0f, 1.0f}, "vTexCoord at the bottom-left pixel (top-left origin)"},
      {15, {0.875f, 0.875f, 0.0f, 1.0f}, "vTexCoord at the bottom-right pixel"},
  };
  for (const Expected &entry : expected) {
    const float *value = out.at(entry.index % 4, entry.index / 4);
    bool match = true;
    for (int channel = 0; channel < 4; channel++) {
      match = match && Near(value[channel], entry.values[channel], 1e-4f * std::max(1.0f, std::fabs(entry.values[channel])));
    }
    CHECK(match, "semantics: %s = (%g, %g, %g, %g), expected (%g, %g, %g, %g)", entry.what, value[0], value[1],
          value[2], value[3], entry.values[0], entry.values[1], entry.values[2], entry.values[3]);
  }
  // User values are clamped to the declared range.
  [chain setParameter:@"PARAM_A" value:9.0f];
  [chain setParameter:@"PARAM_B" value:0.25f];
  [chain setParameter:@"UNKNOWN" value:1.0f];
  NSArray<NSNumber *> *values = [chain parameterValues];
  CHECK(values.count == 2 && values[a].floatValue == 2.0f, "semantics: PARAM_A clamped to 2");
  out = harness.frame(chain, Gradient(8, 6), CGSizeMake(20, 10), CGSizeMake(30, 15), state, NO, &ok);
  CHECK(ok && Near(out.at(2, 1)[1], 2.0f, 1e-6f) && Near(out.at(2, 1)[2], 0.25f, 1e-6f),
        "semantics: new parameter values reach the shader (%g, %g)", ok ? out.at(2, 1)[1] : -1.0f,
        ok ? out.at(2, 1)[2] : -1.0f);
  [chain setParameterValues:@[]];
  out = harness.frame(chain, Gradient(8, 6), CGSizeMake(20, 10), CGSizeMake(30, 15), state, NO, &ok);
  CHECK(ok && Near(out.at(2, 1)[1], 0.75f, 1e-6f) && Near(out.at(2, 1)[2], 1.0f, 1e-6f),
        "semantics: missing values return to the preset's");
}

void TestMultiPass(Harness &harness) {
  NeoSlangProgram *program = harness.program(@"multipass.slangp");
  CHECK(program != nil, "multipass.slangp compiles");
  if (program == nil) return;
  NeoSlangChain *chain = [[NeoSlangChain alloc] initWithProgram:program];
  const Picture input = Gradient(8, 6);
  BOOL ok = NO;
  Pixels out = harness.frame(chain, input, CGSizeMake(16, 12), CGSizeMake(16, 12), DefaultState(), NO, &ok);
  CHECK(ok, "multipass: encode succeeded (%s)", chain.lastFailureCode.UTF8String ?: "");
  if (!ok) return;
  CHECK(out.width == 16 && out.height == 12, "multipass: final pass at the output size");
  CHECK(out.byte(0, 0, 0) == 16 && out.byte(0, 0, 1) == 12 && out.byte(0, 0, 2) == 8 && out.byte(0, 0, 3) == 5,
        "multipass: FirstSize 16x12 (source x2), SourceSize 8x5 (viewport x0.5, absolute 5): got %d %d %d %d",
        out.byte(0, 0, 0), out.byte(0, 0, 1), out.byte(0, 0, 2), out.byte(0, 0, 3));
  CHECK(out.byte(1, 0, 0) == 16 && out.byte(1, 0, 1) == 12 && out.byte(1, 0, 2) == 16 && out.byte(1, 0, 3) == 12,
        "multipass: OutputSize 16x12, PassOutputSize0 16x12");
  CHECK(out.byte(2, 0, 0) == 8 && out.byte(2, 0, 1) == 5, "multipass: PassOutputSize1 8x5");
  int mismatches = 0;
  for (NSUInteger y = 1; y < 12; y++) {
    for (NSUInteger x = 0; x < 16; x++) {
      const uint8_t *expected = input.at(x / 2, y / 2);
      for (int channel = 0; channel < 3; channel++) {
        if (out.byte(x, y, channel) != expected[channel]) mismatches++;
      }
    }
  }
  CHECK(mismatches == 0, "multipass: the alias First reads pass 0's output (%d mismatches)", mismatches);
}

void TestHistory(Harness &harness) {
  NeoSlangProgram *program = harness.program(@"history.slangp");
  CHECK(program != nil, "history.slangp compiles");
  if (program == nil) return;
  CHECK(program.historyDepth == 2, "history: depth 2 (got %lu)", (unsigned long)program.historyDepth);
  NeoSlangChain *chain = [[NeoSlangChain alloc] initWithProgram:program];
  const int expected[5][3] = {{0, 0, 30}, {10, 0, 70}, {50, 20, 110}, {90, 60, 150}, {0, 0, 190}};
  for (int frame = 0; frame < 5; frame++) {
    if (frame == 4) [chain reset];
    const Picture input = Solid(8, 6, (uint8_t)(40 * frame + 10), (uint8_t)(40 * frame + 20), (uint8_t)(40 * frame + 30));
    BOOL ok = NO;
    Pixels out = harness.frame(chain, input, CGSizeMake(8, 6), CGSizeMake(8, 6), DefaultState(), NO, &ok);
    CHECK(ok, "history frame %d: encode succeeded", frame);
    if (!ok) return;
    CHECK(out.byte(3, 3, 0) == expected[frame][0] && out.byte(3, 3, 1) == expected[frame][1] &&
              out.byte(3, 3, 2) == expected[frame][2],
          "history frame %d: OriginalHistory1.r, OriginalHistory2.g, Original.b = %d %d %d, expected %d %d %d%s",
          frame, out.byte(3, 3, 0), out.byte(3, 3, 1), out.byte(3, 3, 2), expected[frame][0], expected[frame][1],
          expected[frame][2], frame == 4 ? " (after reset: black history)" : "");
  }
}

void TestFeedback(Harness &harness) {
  NeoSlangProgram *program = harness.program(@"feedback.slangp");
  CHECK(program != nil, "feedback.slangp compiles");
  if (program == nil) return;
  NeoSlangChain *chain = [[NeoSlangChain alloc] initWithProgram:program];
  for (int frame = 1; frame <= 3; frame++) {
    BOOL ok = NO;
    Pixels out = harness.frame(chain, Gradient(8, 6), CGSizeMake(8, 6), CGSizeMake(8, 6), DefaultState(), NO, &ok);
    CHECK(ok, "feedback frame %d: encode succeeded", frame);
    if (!ok) return;
    CHECK(out.byte(2, 2, 0) == frame && out.byte(2, 2, 1) == 2 * frame,
          "feedback frame %d: PassFeedback0 + 1 = %d, AccFeedback + 2 = %d", frame, out.byte(2, 2, 0),
          out.byte(2, 2, 1));
  }
}

void TestLut(Harness &harness) {
  NeoSlangProgram *program = harness.program(@"lut.slangp");
  CHECK(program != nil, "lut.slangp compiles");
  if (program == nil) return;
  CHECK([program.files containsObject:@"textures/palette.png"], "lut: the LUT is part of the files");
  NeoSlangChain *chain = [[NeoSlangChain alloc] initWithProgram:program];
  BOOL ok = NO;
  Pixels out = harness.frame(chain, Gradient(8, 6), CGSizeMake(4, 2), CGSizeMake(4, 2), DefaultState(), NO, &ok);
  CHECK(ok, "lut: encode succeeded");
  if (!ok) return;
  const int expected[7][4] = {{255, 0, 0, 255},  {0, 255, 0, 255}, {0, 0, 255, 255},    {200, 100, 50, 128},
                              {10, 20, 30, 255}, {0, 0, 0, 0},     {255, 255, 255, 255}};
  for (int index = 0; index < 7; index++) {
    const NSUInteger x = index % 4;
    const NSUInteger y = index / 4;
    CHECK(out.byte(x, y, 0) == expected[index][0] && out.byte(x, y, 1) == expected[index][1] &&
              out.byte(x, y, 2) == expected[index][2] && out.byte(x, y, 3) == expected[index][3],
          "lut texel %d: %d %d %d %d, expected %d %d %d %d (straight alpha, no colour conversion)", index,
          out.byte(x, y, 0), out.byte(x, y, 1), out.byte(x, y, 2), out.byte(x, y, 3), expected[index][0],
          expected[index][1], expected[index][2], expected[index][3]);
  }
  CHECK(out.byte(3, 1, 0) == 4 && out.byte(3, 1, 1) == 2, "lut: PaletteSize 4x2");
}

void TestMipmaps(Harness &harness) {
  NeoSlangProgram *program = harness.program(@"mipmap.slangp");
  CHECK(program != nil, "mipmap.slangp compiles");
  if (program == nil) return;
  NeoSlangChain *chain = [[NeoSlangChain alloc] initWithProgram:program];
  BOOL ok = NO;
  Pixels out = harness.frame(chain, Checkerboard(8), CGSizeMake(4, 4), CGSizeMake(4, 4), DefaultState(), NO, &ok);
  CHECK(ok, "mipmap: encode succeeded");
  if (!ok) return;
  CHECK(std::abs(out.byte(1, 1, 0) - 128) <= 3,
        "mipmap_input1: the 1x1 level of pass 0's output averages the checkerboard (%d)", out.byte(1, 1, 0));
  // Same chain with the default clamp_to_border: the 1x1 level is blended
  // with the transparent black border at (0.0625, 0.0625): 0.5625^2 * 0.5.
  NeoSlangProgram *bordered = harness.program(@"mipmap-border.slangp");
  CHECK(bordered != nil, "mipmap-border.slangp compiles");
  if (bordered == nil) return;
  NeoSlangChain *borderChain = [[NeoSlangChain alloc] initWithProgram:bordered];
  out = harness.frame(borderChain, Checkerboard(8), CGSizeMake(4, 4), CGSizeMake(4, 4), DefaultState(), NO, &ok);
  CHECK(ok && std::abs(out.byte(1, 1, 0) - 40) <= 3,
        "mipmap_input1 + clamp_to_border: border blended into the last level (%d)", ok ? out.byte(1, 1, 0) : -1);
}

void TestWrap(Harness &harness) {
  const Picture input = Gradient(8, 6);
  NeoSlangProgram *border = harness.program(@"wrap-border.slangp");
  NeoSlangProgram *repeat = harness.program(@"wrap-repeat.slangp");
  CHECK(border != nil && repeat != nil, "wrap presets compile");
  if (border == nil || repeat == nil) return;
  BOOL ok = NO;
  NeoSlangChain *chain = [[NeoSlangChain alloc] initWithProgram:border];
  Pixels out = harness.frame(chain, input, CGSizeMake(8, 6), CGSizeMake(8, 6), DefaultState(), NO, &ok);
  CHECK(ok && out.byte(0, 0, 0) == 0 && out.byte(0, 0, 1) == 0 && out.byte(0, 0, 2) == 0 && out.byte(0, 0, 3) == 0,
        "clamp_to_border: transparent black outside the picture");
  // Inside: texel (2x - 3, 2y - 2).
  CHECK(ok && out.byte(4, 3, 0) == input.at(5, 4)[0] && out.byte(4, 3, 1) == input.at(5, 4)[1],
        "clamp_to_border: inside the picture unchanged");
  chain = [[NeoSlangChain alloc] initWithProgram:repeat];
  out = harness.frame(chain, input, CGSizeMake(8, 6), CGSizeMake(8, 6), DefaultState(), NO, &ok);
  CHECK(ok && out.byte(0, 0, 0) == input.at(5, 4)[0] && out.byte(0, 0, 1) == input.at(5, 4)[1],
        "repeat: texel (-3, -2) wraps to (5, 4): %d %d", ok ? out.byte(0, 0, 0) : -1, ok ? out.byte(0, 0, 1) : -1);
}

void TestSrgb(Harness &harness) {
  NeoSlangProgram *program = harness.program(@"srgb.slangp");
  CHECK(program != nil, "srgb.slangp compiles");
  if (program == nil) return;
  NeoSlangChain *chain = [[NeoSlangChain alloc] initWithProgram:program];
  BOOL ok = NO;
  Pixels out = harness.frame(chain, Gradient(8, 6), CGSizeMake(8, 6), CGSizeMake(8, 6), DefaultState(), NO, &ok);
  CHECK(ok, "srgb: encode succeeded");
  if (!ok) return;
  // 0.01 stored as sRGB (25/255) reads back ~0.0097: x20 -> ~50; a plain
  // UNORM framebuffer would give 60.
  CHECK(out.byte(2, 2, 0) >= 44 && out.byte(2, 2, 0) <= 56,
        "srgb_framebuffer0: values stored as sRGB and read back linear (%d, 60 without sRGB)", out.byte(2, 2, 0));
}

void TestSections(Harness &harness) {
  NeoSlangProgram *program = harness.program(@"sections.slangp");
  CHECK(program != nil, "sections.slangp compiles");
  if (program == nil) return;
  const NSUInteger header = [program indexOfParameter:@"HEADER"];
  const NSUInteger value = [program indexOfParameter:@"STRENGTH"];
  CHECK(header != NSNotFound && value != NSNotFound, "sections: both parameters listed");
  if (header == NSNotFound || value == NSNotFound) return;
  CHECK(program.parameters[header].section && !program.parameters[value].section,
        "sections: a heading line (minimum == maximum) is a section, not a value");
  CHECK([program.parameters[header].label isEqualToString:@"== Section =="], "sections: author's label kept as written");
}

void TestFailures(Harness &harness) {
  NSError *error = nil;
  CHECK(harness.program(@"unknown-semantic.slangp", &error) == nil &&
            [ErrorCode(error) isEqualToString:@"REFLECT_UNKNOWN_SEMANTIC"],
        "an unknown uniform is refused with REFLECT_UNKNOWN_SEMANTIC (%s)", ErrorCode(error).UTF8String ?: "nil");
  error = nil;
  CHECK(harness.program(@"missing-lut.slangp", &error) == nil && [ErrorCode(error) isEqualToString:@"LUT_UNREADABLE"],
        "a missing LUT is refused with LUT_UNREADABLE (%s)", ErrorCode(error).UTF8String ?: "nil");
  error = nil;
  CHECK(harness.program(@"symlink-lut.slangp", &error) == nil && [ErrorCode(error) isEqualToString:@"LUT_UNREADABLE"],
        "a LUT reached through a symbolic link is refused (%s)", ErrorCode(error).UTF8String ?: "nil");
  error = nil;
  CHECK(harness.program(@"corrupt-lut.slangp", &error) == nil &&
            [ErrorCode(error) isEqualToString:@"LUT_DECODE_FAILED"],
        "an undecodable LUT is refused with LUT_DECODE_FAILED (%s)", ErrorCode(error).UTF8String ?: "nil");
  error = nil;
  CHECK(harness.program(@"../outside.slangp", &error) == nil, "a preset path leaving the root is refused (%s)",
        ErrorCode(error).UTF8String ?: "nil");

  NeoSlangProgram *huge = harness.program(@"huge.slangp");
  CHECK(huge != nil, "huge.slangp compiles");
  if (huge == nil) return;
  NeoSlangChain *chain = [[NeoSlangChain alloc] initWithProgram:huge];
  BOOL ok = YES;
  harness.frame(chain, Gradient(8, 6), CGSizeMake(8, 6), CGSizeMake(8, 6), DefaultState(), NO, &ok);
  CHECK(!ok && [chain.lastFailureCode isEqualToString:@"CHAIN_MEMORY"],
        "a 16384x16384 float pass is refused before allocation with CHAIN_MEMORY (%s)",
        chain.lastFailureCode.UTF8String ?: "nil");
}

}  // namespace

int main(int argc, const char *argv[]) {
  @autoreleasepool {
    if (argc != 2) {
      std::fprintf(stderr, "usage: neoshader-render-tests FIXTURES_DIRECTORY\n");
      return 2;
    }
    id<MTLDevice> device = MTLCreateSystemDefaultDevice();
    if (device == nil) {
      std::fprintf(stderr, "NO METAL DEVICE\n");
      return 3;
    }
    std::printf("Metal device: %s\n", device.name.UTF8String);
    Harness harness(device, [NSString stringWithUTF8String:argv[1]]);
    TestPassthrough(harness);
    TestSemantics(harness);
    TestMultiPass(harness);
    TestHistory(harness);
    TestFeedback(harness);
    TestLut(harness);
    TestMipmaps(harness);
    TestWrap(harness);
    TestSrgb(harness);
    TestSections(harness);
    TestFailures(harness);
    std::printf("%d checks, %d failures\n", g_checks, g_failures);
    return g_failures == 0 ? 0 : 1;
  }
}
