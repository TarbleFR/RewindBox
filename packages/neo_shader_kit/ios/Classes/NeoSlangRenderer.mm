// SPDX-License-Identifier: GPL-3.0-or-later
#import "NeoSlangRenderer.h"

#import <ImageIO/ImageIO.h>
#import <QuartzCore/QuartzCore.h>

#include <os/lock.h>

#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstddef>
#include <cstring>
#include <string>
#include <utility>
#include <vector>

#include "NeoShaderFiles.hpp"
#include "NeoShaderPaths.hpp"
#include "NeoSlangCompiler.hpp"

NSString *const NeoSlangErrorDomain = @"NeoSlang";
NSString *const NeoSlangErrorCodeKey = @"NeoSlangErrorCode";

namespace {

using neoshader::FilterMode;
using neoshader::ScaleType;
using neoshader::SlangFormat;
using neoshader::SlangSemantic;
using neoshader::SlangTextureSemantic;
using neoshader::SlangUniformSlot;
using neoshader::WrapMode;

/// Vertex buffer of the quad; buffer(0) and buffer(1) are the uniform block
/// and the push constants of every pass.
constexpr NSUInteger kVertexBufferIndex = 4;
/// Largest side of a framebuffer or LUT (Apple GPUs).
constexpr NSUInteger kMaxTextureSide = 16384;
/// GPU memory one chain may hold: framebuffers, feedback, history and the
/// picture. A preset asking for more at the current size is refused for that
/// frame (CHAIN_MEMORY) instead of exhausting the application's memory.
constexpr unsigned long long kChainMemoryBudget = 1ULL << 30;
/// LUT files and pictures.
constexpr size_t kMaxLutFileBytes = 64u << 20;
constexpr unsigned long long kMaxLutPixels = 64ULL << 20;
/// setVertexBytes / setFragmentBytes limit.
constexpr size_t kInlineBytesLimit = 4096;

/// Quad of every pass: Position (x, y, 0, 1) and TexCoord (u, v) in [0,1],
/// RetroArch's vertex data (shader_vulkan.c). After the vertex stage's Y flip
/// (Vulkan clip space -> Metal), (0,0) is the top-left texel of both the
/// framebuffer and the input: pictures are stored with their top row first.
struct QuadVertex {
  float position[4];
  float texCoord[2];
};
const QuadVertex kQuad[4] = {
    {{0.0f, 0.0f, 0.0f, 1.0f}, {0.0f, 0.0f}},
    {{1.0f, 0.0f, 0.0f, 1.0f}, {1.0f, 0.0f}},
    {{0.0f, 1.0f, 0.0f, 1.0f}, {0.0f, 1.0f}},
    {{1.0f, 1.0f, 0.0f, 1.0f}, {1.0f, 1.0f}},
};
static_assert(sizeof(QuadVertex) == 24, "quad vertex layout");

/// RetroArch's default MVP, column-major: [0,1] -> clip space [-1,1].
const float kMVP[16] = {2.0f, 0.0f, 0.0f, 0.0f, 0.0f, 2.0f, 0.0f, 0.0f,
                        0.0f, 0.0f, 1.0f, 0.0f, -1.0f, -1.0f, 0.0f, 1.0f};

NSString *ToNSString(const std::string &text) {
  NSString *string = [[NSString alloc] initWithBytes:text.data() length:text.size() encoding:NSUTF8StringEncoding];
  if (string == nil) {
    string = [[NSString alloc] initWithBytes:text.data() length:text.size() encoding:NSISOLatin1StringEncoding];
  }
  return string ?: @"";
}

/// Stable reason code + raw diagnostic (never shown untranslated: the
/// application translates the code, the detail goes to the session log).
NSError *MakeError(NSString *code, NSString *detail) {
  NSMutableDictionary<NSString *, id> *info = [NSMutableDictionary dictionary];
  info[NeoSlangErrorCodeKey] = code;
  if (detail.length > 0) info[NSDebugDescriptionErrorKey] = detail;
  return [NSError errorWithDomain:NeoSlangErrorDomain code:1 userInfo:info];
}

MTLPixelFormat PixelFormat(SlangFormat format) {
  switch (format) {
    case SlangFormat::R8_UNORM: return MTLPixelFormatR8Unorm;
    case SlangFormat::R8_UINT: return MTLPixelFormatR8Uint;
    case SlangFormat::R8_SINT: return MTLPixelFormatR8Sint;
    case SlangFormat::R8G8_UNORM: return MTLPixelFormatRG8Unorm;
    case SlangFormat::R8G8_UINT: return MTLPixelFormatRG8Uint;
    case SlangFormat::R8G8_SINT: return MTLPixelFormatRG8Sint;
    case SlangFormat::R8G8B8A8_UNORM: return MTLPixelFormatRGBA8Unorm;
    case SlangFormat::R8G8B8A8_UINT: return MTLPixelFormatRGBA8Uint;
    case SlangFormat::R8G8B8A8_SINT: return MTLPixelFormatRGBA8Sint;
    case SlangFormat::R8G8B8A8_SRGB: return MTLPixelFormatRGBA8Unorm_sRGB;
    case SlangFormat::A2B10G10R10_UNORM_PACK32: return MTLPixelFormatRGB10A2Unorm;
    case SlangFormat::A2B10G10R10_UINT_PACK32: return MTLPixelFormatRGB10A2Uint;
    case SlangFormat::R16_UINT: return MTLPixelFormatR16Uint;
    case SlangFormat::R16_SINT: return MTLPixelFormatR16Sint;
    case SlangFormat::R16_SFLOAT: return MTLPixelFormatR16Float;
    case SlangFormat::R16G16_UINT: return MTLPixelFormatRG16Uint;
    case SlangFormat::R16G16_SINT: return MTLPixelFormatRG16Sint;
    case SlangFormat::R16G16_SFLOAT: return MTLPixelFormatRG16Float;
    case SlangFormat::R16G16B16A16_UINT: return MTLPixelFormatRGBA16Uint;
    case SlangFormat::R16G16B16A16_SINT: return MTLPixelFormatRGBA16Sint;
    case SlangFormat::R16G16B16A16_SFLOAT: return MTLPixelFormatRGBA16Float;
    case SlangFormat::R32_UINT: return MTLPixelFormatR32Uint;
    case SlangFormat::R32_SINT: return MTLPixelFormatR32Sint;
    case SlangFormat::R32_SFLOAT: return MTLPixelFormatR32Float;
    case SlangFormat::R32G32_UINT: return MTLPixelFormatRG32Uint;
    case SlangFormat::R32G32_SINT: return MTLPixelFormatRG32Sint;
    case SlangFormat::R32G32_SFLOAT: return MTLPixelFormatRG32Float;
    case SlangFormat::R32G32B32A32_UINT: return MTLPixelFormatRGBA32Uint;
    case SlangFormat::R32G32B32A32_SINT: return MTLPixelFormatRGBA32Sint;
    case SlangFormat::R32G32B32A32_SFLOAT: return MTLPixelFormatRGBA32Float;
    case SlangFormat::Unknown: break;
  }
  return MTLPixelFormatInvalid;
}

NSUInteger BytesPerPixel(MTLPixelFormat format) {
  switch (format) {
    case MTLPixelFormatR8Unorm:
    case MTLPixelFormatR8Uint:
    case MTLPixelFormatR8Sint:
      return 1;
    case MTLPixelFormatRG8Unorm:
    case MTLPixelFormatRG8Uint:
    case MTLPixelFormatRG8Sint:
    case MTLPixelFormatR16Uint:
    case MTLPixelFormatR16Sint:
    case MTLPixelFormatR16Float:
      return 2;
    case MTLPixelFormatRGBA16Uint:
    case MTLPixelFormatRGBA16Sint:
    case MTLPixelFormatRGBA16Float:
    case MTLPixelFormatRG32Uint:
    case MTLPixelFormatRG32Sint:
    case MTLPixelFormatRG32Float:
      return 8;
    case MTLPixelFormatRGBA32Uint:
    case MTLPixelFormatRGBA32Sint:
    case MTLPixelFormatRGBA32Float:
      return 16;
    default:
      return 4;
  }
}

bool IsIntegerFormat(MTLPixelFormat format) {
  switch (format) {
    case MTLPixelFormatR8Uint:
    case MTLPixelFormatR8Sint:
    case MTLPixelFormatRG8Uint:
    case MTLPixelFormatRG8Sint:
    case MTLPixelFormatRGBA8Uint:
    case MTLPixelFormatRGBA8Sint:
    case MTLPixelFormatRGB10A2Uint:
    case MTLPixelFormatR16Uint:
    case MTLPixelFormatR16Sint:
    case MTLPixelFormatRG16Uint:
    case MTLPixelFormatRG16Sint:
    case MTLPixelFormatRGBA16Uint:
    case MTLPixelFormatRGBA16Sint:
    case MTLPixelFormatR32Uint:
    case MTLPixelFormatR32Sint:
    case MTLPixelFormatRG32Uint:
    case MTLPixelFormatRG32Sint:
    case MTLPixelFormatRGBA32Uint:
    case MTLPixelFormatRGBA32Sint:
      return true;
    default:
      return false;
  }
}

bool IsFloat32Format(MTLPixelFormat format) {
  return format == MTLPixelFormatR32Float || format == MTLPixelFormatRG32Float || format == MTLPixelFormatRGBA32Float;
}

unsigned long long TextureBytes(NSUInteger width, NSUInteger height, MTLPixelFormat format, bool mipmapped) {
  const unsigned long long level = (unsigned long long)width * height * BytesPerPixel(format);
  // A full mip chain adds at most a third.
  return mipmapped ? level + level / 3 + 1 : level;
}

unsigned long long TextureBytes(id<MTLTexture> texture) {
  if (texture == nil) return 0;
  return TextureBytes(texture.width, texture.height, texture.pixelFormat, texture.mipmapLevelCount > 1);
}

NSUInteger WrapIndex(WrapMode wrap) {
  switch (wrap) {
    case WrapMode::ClampToBorder: return 0;
    case WrapMode::ClampToEdge: return 1;
    case WrapMode::Repeat: return 2;
    case WrapMode::MirroredRepeat: return 3;
  }
  return 0;
}

MTLSamplerAddressMode AddressMode(NSUInteger wrapIndex) {
  switch (wrapIndex) {
    case 1: return MTLSamplerAddressModeClampToEdge;
    case 2: return MTLSamplerAddressModeRepeat;
    case 3: return MTLSamplerAddressModeMirrorRepeat;
    default:
      // RetroArch's clamp_to_border uses transparent black borders
      // (VK_BORDER_COLOR_FLOAT_TRANSPARENT_BLACK): Metal's clamp-to-zero,
      // available on every Apple GPU.
      return MTLSamplerAddressModeClampToZero;
  }
}

/// 2 filters x 4 wraps x 3 mip modes (not mipmapped, nearest, linear).
constexpr NSUInteger kSamplerCount = 24;

NSUInteger SamplerIndex(bool linear, WrapMode wrap, NSUInteger mipMode) {
  return ((linear ? 1u : 0u) * 4u + WrapIndex(wrap)) * 3u + mipMode;
}

/// How a pass reads its input (Original for pass 0, Source otherwise), and
/// how LUTs are read (RetroArch: Pass::get_source_filter / get_mip_filter /
/// get_address_mode, StaticTexture).
struct Sampling {
  bool linear = false;
  WrapMode wrap = WrapMode::ClampToBorder;
  bool linearMip = false;
};

/// A slang pass ready to draw.
struct RuntimePass {
  id<MTLRenderPipelineState> pipeline;
  MTLPixelFormat format = MTLPixelFormatInvalid;
  neoshader::CompiledSlangPass compiled;
  neoshader::SlangPass description;
  /// Last pass without a scale: RetroArch draws it straight into the back
  /// buffer at the viewport size, in the back buffer's format ("#pragma
  /// format" ignored). NeoStation renders it at the output size in BGRA8.
  bool drawsViewport = false;
};

struct RuntimeLut {
  id<MTLTexture> texture;
  Sampling sampling;
};

struct PassTarget {
  id<MTLTexture> output;
  /// Previous frame's output, for passes read as PassFeedback.
  id<MTLTexture> feedback;
};

NSUInteger SideFromDouble(double value) {
  if (!std::isfinite(value) || value < 0.5 || value > (double)kMaxTextureSide) return 0;
  return (NSUInteger)std::lround(value);
}

/// Pass::get_output_size: unsigned(roundf(...)), at least one pixel.
NSUInteger ScaledSide(ScaleType type, float scale, unsigned absolute, NSUInteger source, NSUInteger viewport) {
  double value = 0.0;
  switch (type) {
    case ScaleType::Source:
      value = (double)source * scale;
      break;
    case ScaleType::Viewport:
      value = (double)viewport * scale;
      break;
    case ScaleType::Absolute:
      value = (double)absolute;
      break;
  }
  if (!std::isfinite(value) || value > (double)kMaxTextureSide) return kMaxTextureSide + 1;
  return (NSUInteger)std::max(1L, std::lround(value));
}

MTLVertexDescriptor *QuadVertexDescriptor() {
  MTLVertexDescriptor *descriptor = [MTLVertexDescriptor vertexDescriptor];
  descriptor.attributes[0].format = MTLVertexFormatFloat4;
  descriptor.attributes[0].offset = offsetof(QuadVertex, position);
  descriptor.attributes[0].bufferIndex = kVertexBufferIndex;
  descriptor.attributes[1].format = MTLVertexFormatFloat2;
  descriptor.attributes[1].offset = offsetof(QuadVertex, texCoord);
  descriptor.attributes[1].bufferIndex = kVertexBufferIndex;
  descriptor.layouts[kVertexBufferIndex].stride = sizeof(QuadVertex);
  descriptor.layouts[kVertexBufferIndex].stepFunction = MTLVertexStepFunctionPerVertex;
  return descriptor;
}

id<MTLFunction> CompileFunction(id<MTLDevice> device, const std::string &source, const std::string &entry,
                                MTLCompileOptions *options, NSString **detail) {
  NSError *compileError = nil;
  id<MTLLibrary> library = [device newLibraryWithSource:ToNSString(source) options:options error:&compileError];
  if (library == nil) {
    *detail = compileError.localizedDescription ?: @"newLibraryWithSource failed";
    return nil;
  }
  id<MTLFunction> function = [library newFunctionWithName:ToNSString(entry)];
  if (function == nil) *detail = [@"missing function " stringByAppendingString:ToNSString(entry)];
  return function;
}

/// LUT pixels as straight (non-premultiplied) RGBA8, top row first. 8-bit
/// RGB / gray pictures are read as stored, without colour conversion (the
/// LUT values are data, as RetroArch's image loader reads them); anything
/// else is drawn into an RGBA context of its own colour space and
/// un-premultiplied.
bool DecodeStraightRGBA(CGImageRef image, std::vector<uint8_t> *pixels) {
  const size_t width = CGImageGetWidth(image);
  const size_t height = CGImageGetHeight(image);
  pixels->assign(width * height * 4, 0);
  const CGBitmapInfo info = CGImageGetBitmapInfo(image);
  const CGImageAlphaInfo alpha = CGImageGetAlphaInfo(image);
  const size_t bitsPerComponent = CGImageGetBitsPerComponent(image);
  const size_t bitsPerPixel = CGImageGetBitsPerPixel(image);
  const size_t bytesPerRow = CGImageGetBytesPerRow(image);
  const CGBitmapInfo order = info & kCGBitmapByteOrderMask;
  CGColorSpaceRef space = CGImageGetColorSpace(image);
  const CGColorSpaceModel model = space != NULL ? CGColorSpaceGetModel(space) : kCGColorSpaceModelUnknown;
  const bool rgb = model == kCGColorSpaceModelRGB;
  const bool gray = model == kCGColorSpaceModelMonochrome;

  bool alphaPresent = false;
  bool alphaFirst = false;
  bool alphaReal = false;
  bool premultiplied = false;
  switch (alpha) {
    case kCGImageAlphaNone:
      break;
    case kCGImageAlphaPremultipliedLast:
      premultiplied = true;
      alphaPresent = alphaReal = true;
      break;
    case kCGImageAlphaPremultipliedFirst:
      premultiplied = true;
      alphaPresent = alphaReal = alphaFirst = true;
      break;
    case kCGImageAlphaLast:
      alphaPresent = alphaReal = true;
      break;
    case kCGImageAlphaFirst:
      alphaPresent = alphaReal = alphaFirst = true;
      break;
    case kCGImageAlphaNoneSkipLast:
      alphaPresent = true;
      break;
    case kCGImageAlphaNoneSkipFirst:
      alphaPresent = alphaFirst = true;
      break;
    default:
      alphaPresent = true;  // alpha only: fallback below
      break;
  }
  const size_t colorComponents = rgb ? 3 : 1;
  const size_t channels = colorComponents + (alphaPresent ? 1 : 0);
  bool reversed = false;
  bool direct = (info & kCGBitmapFloatComponents) == 0 && bitsPerComponent == 8 && (rgb || gray) &&
                alpha != kCGImageAlphaOnly && bitsPerPixel == channels * 8;
  if (direct) {
    if (order == kCGBitmapByteOrder32Little) {
      direct = channels == 4;
      reversed = true;
    } else if (order == kCGBitmapByteOrder16Little) {
      direct = channels == 2;
      reversed = true;
    } else {
      direct = order == kCGBitmapByteOrderDefault || order == kCGBitmapByteOrder32Big ||
               order == kCGBitmapByteOrder16Big;
    }
  }
  if (direct) {
    CFDataRef data = CGDataProviderCopyData(CGImageGetDataProvider(image));
    const size_t needed = height == 0 ? 0 : bytesPerRow * (height - 1) + width * channels;
    if (data != NULL && (size_t)CFDataGetLength(data) >= needed) {
      const uint8_t *bytes = CFDataGetBytePtr(data);
      for (size_t row = 0; row < height; row++) {
        const uint8_t *source = bytes + row * bytesPerRow;
        uint8_t *target = pixels->data() + row * width * 4;
        for (size_t column = 0; column < width; column++) {
          uint8_t logical[4] = {0, 0, 0, 255};
          for (size_t channel = 0; channel < channels; channel++) {
            logical[channel] = source[column * channels + (reversed ? channels - 1 - channel : channel)];
          }
          const size_t colorStart = alphaPresent && alphaFirst ? 1 : 0;
          const size_t alphaIndex = alphaFirst ? 0 : colorComponents;
          uint8_t red, green, blue;
          if (rgb) {
            red = logical[colorStart];
            green = logical[colorStart + 1];
            blue = logical[colorStart + 2];
          } else {
            red = green = blue = logical[colorStart];
          }
          const uint8_t a = alphaReal ? logical[alphaIndex] : 255;
          if (premultiplied && a > 0 && a < 255) {
            red = (uint8_t)std::min(255, (red * 255 + a / 2) / a);
            green = (uint8_t)std::min(255, (green * 255 + a / 2) / a);
            blue = (uint8_t)std::min(255, (blue * 255 + a / 2) / a);
          }
          target[column * 4 + 0] = red;
          target[column * 4 + 1] = green;
          target[column * 4 + 2] = blue;
          target[column * 4 + 3] = a;
        }
      }
      CFRelease(data);
      return true;
    }
    if (data != NULL) CFRelease(data);
  }

  // Indexed (palette) pictures: their base RGB space; 16-bit and other
  // layouts: their own RGB space; gray-alpha with odd layouts: sRGB.
  CGColorSpaceRef target = NULL;
  if (rgb) {
    target = CGColorSpaceRetain(space);
  } else if (model == kCGColorSpaceModelIndexed) {
    CGColorSpaceRef base = CGColorSpaceGetBaseColorSpace(space);
    if (base != NULL && CGColorSpaceGetModel(base) == kCGColorSpaceModelRGB) target = CGColorSpaceRetain(base);
  }
  if (target == NULL) target = CGColorSpaceCreateWithName(kCGColorSpaceSRGB);
  CGContextRef context = CGBitmapContextCreate(pixels->data(), width, height, 8, width * 4, target,
                                               kCGImageAlphaPremultipliedLast | kCGBitmapByteOrder32Big);
  CGColorSpaceRelease(target);
  if (context == NULL) {
    CGColorSpaceRef srgb = CGColorSpaceCreateWithName(kCGColorSpaceSRGB);
    context = CGBitmapContextCreate(pixels->data(), width, height, 8, width * 4, srgb,
                                    kCGImageAlphaPremultipliedLast | kCGBitmapByteOrder32Big);
    CGColorSpaceRelease(srgb);
  }
  if (context == NULL) return false;
  CGContextSetBlendMode(context, kCGBlendModeCopy);
  CGContextSetInterpolationQuality(context, kCGInterpolationNone);
  CGContextDrawImage(context, CGRectMake(0, 0, (CGFloat)width, (CGFloat)height), image);
  CGContextRelease(context);
  uint8_t *bytes = pixels->data();
  for (size_t index = 0; index < width * height; index++) {
    uint8_t *pixel = bytes + index * 4;
    const int a = pixel[3];
    if (a == 0 || a == 255) continue;
    for (int channel = 0; channel < 3; channel++) {
      pixel[channel] = (uint8_t)std::min(255, (pixel[channel] * 255 + a / 2) / a);
    }
  }
  return true;
}

bool TextureMatches(id<MTLTexture> texture, MTLPixelFormat format, MTLSize size, bool mipmapped) {
  return texture != nil && texture.pixelFormat == format && texture.width == size.width &&
         texture.height == size.height && (texture.mipmapLevelCount > 1) == mipmapped;
}

void PutBytes(std::vector<uint8_t> &buffer, int offset, const void *data, size_t size) {
  if (offset < 0 || (size_t)offset + size > buffer.size()) return;
  std::memcpy(buffer.data() + offset, data, size);
}

void SizeVector(NSUInteger width, NSUInteger height, float out[4]) {
  out[0] = (float)width;
  out[1] = (float)height;
  out[2] = width > 0 ? 1.0f / (float)width : 0.0f;
  out[3] = height > 0 ? 1.0f / (float)height : 0.0f;
}

void BindBytes(id<MTLRenderCommandEncoder> encoder, id<MTLDevice> device, const std::vector<uint8_t> &bytes,
                      NSUInteger index) {
  if (bytes.empty()) return;
  if (bytes.size() <= kInlineBytesLimit) {
    [encoder setVertexBytes:bytes.data() length:bytes.size() atIndex:index];
    [encoder setFragmentBytes:bytes.data() length:bytes.size() atIndex:index];
    return;
  }
  id<MTLBuffer> buffer = [device newBufferWithBytes:bytes.data()
                                             length:bytes.size()
                                            options:MTLResourceStorageModeShared];
  [encoder setVertexBuffer:buffer offset:0 atIndex:index];
  [encoder setFragmentBuffer:buffer offset:0 atIndex:index];
}

void ClearTexture(id<MTLCommandBuffer> commandBuffer, id<MTLTexture> texture) {
  MTLRenderPassDescriptor *pass = [MTLRenderPassDescriptor renderPassDescriptor];
  pass.colorAttachments[0].texture = texture;
  pass.colorAttachments[0].loadAction = MTLLoadActionClear;
  pass.colorAttachments[0].clearColor = MTLClearColorMake(0, 0, 0, 0);
  pass.colorAttachments[0].storeAction = MTLStoreActionStore;
  [[commandBuffer renderCommandEncoderWithDescriptor:pass] endEncoding];
  if (texture.mipmapLevelCount > 1) {
    id<MTLBlitCommandEncoder> blit = [commandBuffer blitCommandEncoder];
    [blit generateMipmapsForTexture:texture];
    [blit endEncoding];
  }
}

void GenerateMipmaps(id<MTLCommandBuffer> commandBuffer, id<MTLTexture> texture) {
  if (texture.mipmapLevelCount <= 1) return;
  id<MTLBlitCommandEncoder> blit = [commandBuffer blitCommandEncoder];
  [blit generateMipmapsForTexture:texture];
  [blit endEncoding];
}

}  // namespace

#pragma mark - Parameters

@interface NeoSlangParameterInfo ()
- (instancetype)initWithParameter:(const neoshader::CompiledSlangParameter &)parameter;
@end

@implementation NeoSlangParameterInfo

- (instancetype)initWithParameter:(const neoshader::CompiledSlangParameter &)parameter {
  self = [super init];
  if (self) {
    _identifier = ToNSString(parameter.declaration.id);
    _label = ToNSString(parameter.declaration.description);
    _initial = parameter.declaration.initial;
    _minimum = parameter.declaration.minimum;
    _maximum = parameter.declaration.maximum;
    _step = parameter.declaration.step;
    _presetValue = parameter.value;
    _section = parameter.declaration.minimum == parameter.declaration.maximum;
  }
  return self;
}

@end

#pragma mark - Program

@interface NeoSlangProgram () {
 @public
  std::vector<RuntimePass> _passes;
  std::vector<RuntimeLut> _luts;
  std::vector<float> _presetValues;
  std::vector<float> _minimums;
  std::vector<float> _maximums;
  std::vector<bool> _feedback;
  std::vector<id<MTLSamplerState>> _samplers;
  bool _filtersFloat32;
}
@property(nonatomic, copy, readwrite) NSString *presetPath;
@property(nonatomic, readwrite) id<MTLDevice> device;
@property(nonatomic, copy, readwrite) NSArray<NeoSlangParameterInfo *> *parameters;
@property(nonatomic, readwrite) NSUInteger historyDepth;
@property(nonatomic, copy, readwrite) NSArray<NSString *> *files;
@property(nonatomic, readwrite) double translationSeconds;
@property(nonatomic, readwrite) double metalSeconds;
- (Sampling)inputSamplingOfPass:(size_t)index smooth:(BOOL)smooth;
- (id<MTLSamplerState>)samplerFor:(Sampling)sampling texture:(nullable id<MTLTexture>)texture;
- (bool)passReadsMipmaps:(size_t)index;
@end

@implementation NeoSlangProgram

+ (nullable instancetype)programWithRoot:(NSString *)root
                                  preset:(NSString *)presetPath
                                  device:(id<MTLDevice>)device
                             iosPlatform:(BOOL)iosPlatform
                                   error:(NSError *_Nullable *_Nullable)error {
  if (![root isKindOfClass:NSString.class] || root.length == 0 || ![presetPath isKindOfClass:NSString.class] ||
      presetPath.length == 0 || device == nil) {
    if (error != NULL) *error = MakeError(@"PROGRAM_ARGUMENTS", nil);
    return nil;
  }
  const CFTimeInterval start = CACurrentMediaTime();
  const std::string rootPath(root.fileSystemRepresentation);
  const std::string path(presetPath.UTF8String ?: "");
  neoshader::DirectoryFileProvider files(rootPath);
  neoshader::SlangCompileOptions options;
  options.iosPlatform = iosPlatform;
  neoshader::CompiledSlangPreset compiled;
  neoshader::ShaderError failure;
  if (!neoshader::compileSlangPreset(files, path, options, &compiled, &failure)) {
    if (error != NULL) {
      *error = MakeError(failure.code.empty() ? @"PRESET_UNREADABLE" : ToNSString(failure.code),
                         ToNSString(failure.detail));
    }
    return nil;
  }
  const CFTimeInterval translated = CACurrentMediaTime();

  NeoSlangProgram *program = [[NeoSlangProgram alloc] init];
  program.presetPath = presetPath;
  program.device = device;
  if (![program buildWithCompiled:compiled root:root error:error]) return nil;
  program.translationSeconds = translated - start;
  program.metalSeconds = CACurrentMediaTime() - translated;
  return program;
}

- (BOOL)buildWithCompiled:(neoshader::CompiledSlangPreset &)compiled
                     root:(NSString *)root
                    error:(NSError *_Nullable *_Nullable)error {
  id<MTLDevice> device = self.device;
  if (@available(iOS 14.0, macOS 11.0, *)) {
    _filtersFloat32 = device.supports32BitFloatFiltering;
  } else {
    _filtersFloat32 = false;
  }

  // Samplers: every filter x wrap x mip combination, built once.
  _samplers.resize(kSamplerCount);
  for (NSUInteger linear = 0; linear < 2; linear++) {
    for (NSUInteger wrap = 0; wrap < 4; wrap++) {
      for (NSUInteger mip = 0; mip < 3; mip++) {
        MTLSamplerDescriptor *descriptor = [MTLSamplerDescriptor new];
        const MTLSamplerMinMagFilter filter = linear ? MTLSamplerMinMagFilterLinear : MTLSamplerMinMagFilterNearest;
        descriptor.minFilter = filter;
        descriptor.magFilter = filter;
        descriptor.mipFilter = mip == 0   ? MTLSamplerMipFilterNotMipmapped
                               : mip == 1 ? MTLSamplerMipFilterNearest
                                          : MTLSamplerMipFilterLinear;
        descriptor.sAddressMode = AddressMode(wrap);
        descriptor.tAddressMode = AddressMode(wrap);
        descriptor.rAddressMode = AddressMode(wrap);
        descriptor.normalizedCoordinates = YES;
        id<MTLSamplerState> sampler = [device newSamplerStateWithDescriptor:descriptor];
        if (sampler == nil) {
          if (error != NULL) *error = MakeError(@"METAL_SAMPLER_FAILED", nil);
          return NO;
        }
        _samplers[(linear * 4 + wrap) * 3 + mip] = sampler;
      }
    }
  }

  // Passes: Metal libraries and pipelines.
  MTLCompileOptions *compileOptions = [MTLCompileOptions new];
  compileOptions.languageVersion = MTLLanguageVersion2_4;
  MTLVertexDescriptor *vertexDescriptor = QuadVertexDescriptor();
  const size_t passCount = compiled.passes.size();
  _passes.resize(passCount);
  for (size_t index = 0; index < passCount; index++) {
    RuntimePass &pass = _passes[index];
    pass.compiled = std::move(compiled.passes[index]);
    pass.description = compiled.preset.passes[index];
    pass.drawsViewport = index + 1 == passCount && !pass.description.scaleSet;
    pass.format = pass.drawsViewport ? MTLPixelFormatBGRA8Unorm : PixelFormat(pass.compiled.format);
    NSString *shader = ToNSString(pass.description.shader);
    if (pass.format == MTLPixelFormatInvalid) {
      if (error != NULL) *error = MakeError(@"PASS_FORMAT_UNSUPPORTED", shader);
      return NO;
    }
    NSString *detail = nil;
    id<MTLFunction> vertex =
        CompileFunction(device, pass.compiled.vertexMSL, pass.compiled.vertexEntry, compileOptions, &detail);
    id<MTLFunction> fragment =
        vertex == nil ? nil
                      : CompileFunction(device, pass.compiled.fragmentMSL, pass.compiled.fragmentEntry,
                                        compileOptions, &detail);
    if (vertex == nil || fragment == nil) {
      if (error != NULL) {
        *error = MakeError(@"METAL_LIBRARY_FAILED", [NSString stringWithFormat:@"%@: %@", shader, detail]);
      }
      return NO;
    }
    MTLRenderPipelineDescriptor *descriptor = [MTLRenderPipelineDescriptor new];
    descriptor.label = [NSString stringWithFormat:@"slang pass %zu", index];
    descriptor.vertexFunction = vertex;
    descriptor.fragmentFunction = fragment;
    descriptor.vertexDescriptor = vertexDescriptor;
    descriptor.colorAttachments[0].pixelFormat = pass.format;
    NSError *pipelineError = nil;
    pass.pipeline = [device newRenderPipelineStateWithDescriptor:descriptor error:&pipelineError];
    if (pass.pipeline == nil) {
      if (error != NULL) {
        *error = MakeError(@"METAL_PIPELINE_FAILED",
                           [NSString stringWithFormat:@"%@: %@", shader,
                                                      pipelineError.localizedDescription ?: @"pipeline"]);
      }
      return NO;
    }
    // The MSL is no longer needed once the pipeline exists.
    pass.compiled.vertexMSL.clear();
    pass.compiled.vertexMSL.shrink_to_fit();
    pass.compiled.fragmentMSL.clear();
    pass.compiled.fragmentMSL.shrink_to_fit();
  }

  // LUT textures.
  id<MTLCommandQueue> queue = nil;
  neoshader::DirectoryFileProvider files(std::string(root.fileSystemRepresentation), kMaxLutFileBytes);
  for (const neoshader::SlangTexture &lut : compiled.preset.textures) {
    NSString *code = nil;
    NSString *detail = ToNSString(lut.path);
    std::string bytes;
    if (!files.read(lut.path, &bytes)) {
      if (error != NULL) *error = MakeError(@"LUT_UNREADABLE", detail);
      return NO;
    }
    NSData *data = [NSData dataWithBytes:bytes.data() length:bytes.size()];
    bytes.clear();
    NSDictionary *noCache = @{(id)kCGImageSourceShouldCache : @NO};
    CGImageSourceRef source = CGImageSourceCreateWithData((__bridge CFDataRef)data, (__bridge CFDictionaryRef)noCache);
    CGImageRef image = NULL;
    if (source != NULL) {
      if (CGImageSourceGetCount(source) > 0) {
        image = CGImageSourceCreateImageAtIndex(source, 0, (__bridge CFDictionaryRef)noCache);
      }
      CFRelease(source);
    }
    std::vector<uint8_t> pixels;
    NSUInteger width = 0;
    NSUInteger height = 0;
    if (image == NULL) {
      code = @"LUT_DECODE_FAILED";
    } else {
      width = CGImageGetWidth(image);
      height = CGImageGetHeight(image);
      if (width == 0 || height == 0 || width > kMaxTextureSide || height > kMaxTextureSide ||
          (unsigned long long)width * height > kMaxLutPixels) {
        code = @"LUT_TOO_LARGE";
      } else if (!DecodeStraightRGBA(image, &pixels)) {
        code = @"LUT_DECODE_FAILED";
      }
      CGImageRelease(image);
    }
    if (code != nil) {
      if (error != NULL) *error = MakeError(code, detail);
      return NO;
    }
    const bool mipmapped = lut.mipmap;
    MTLTextureDescriptor *descriptor = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatRGBA8Unorm
                                                                                          width:width
                                                                                         height:height
                                                                                      mipmapped:mipmapped];
    descriptor.usage = MTLTextureUsageShaderRead | (mipmapped ? MTLTextureUsageRenderTarget : 0);
    id<MTLTexture> texture = [device newTextureWithDescriptor:descriptor];
    if (texture == nil) {
      if (error != NULL) *error = MakeError(@"LUT_ALLOCATION_FAILED", detail);
      return NO;
    }
    [texture replaceRegion:MTLRegionMake2D(0, 0, width, height)
               mipmapLevel:0
                 withBytes:pixels.data()
               bytesPerRow:width * 4];
    if (mipmapped) {
      if (queue == nil) queue = [device newCommandQueue];
      id<MTLCommandBuffer> buffer = [queue commandBuffer];
      id<MTLBlitCommandEncoder> blit = [buffer blitCommandEncoder];
      [blit generateMipmapsForTexture:texture];
      [blit endEncoding];
      [buffer commit];
      [buffer waitUntilCompleted];
    }
    RuntimeLut runtime;
    runtime.texture = texture;
    // StaticTexture: linear unless filter_linear is explicitly false;
    // linear mips when mipmapped and linear.
    runtime.sampling.linear = lut.filter != FilterMode::Nearest;
    runtime.sampling.wrap = lut.wrap;
    runtime.sampling.linearMip = runtime.sampling.linear && mipmapped;
    _luts.push_back(runtime);
  }

  NSMutableArray<NeoSlangParameterInfo *> *parameters = [NSMutableArray array];
  for (const neoshader::CompiledSlangParameter &parameter : compiled.parameters) {
    [parameters addObject:[[NeoSlangParameterInfo alloc] initWithParameter:parameter]];
    _presetValues.push_back(parameter.value);
    _minimums.push_back(parameter.declaration.minimum);
    _maximums.push_back(parameter.declaration.maximum);
  }
  self.parameters = parameters;
  _feedback = compiled.feedback;
  self.historyDepth = compiled.historyDepth;
  NSMutableArray<NSString *> *list = [NSMutableArray arrayWithCapacity:compiled.files.size()];
  for (const std::string &file : compiled.files) [list addObject:ToNSString(file)];
  self.files = list;
  return YES;
}

- (NSUInteger)passCount {
  return _passes.size();
}

- (NSUInteger)indexOfParameter:(NSString *)identifier {
  if (![identifier isKindOfClass:NSString.class]) return NSNotFound;
  NSArray<NeoSlangParameterInfo *> *parameters = self.parameters;
  for (NSUInteger index = 0; index < parameters.count; index++) {
    if ([parameters[index].identifier isEqualToString:identifier]) return index;
  }
  return NSNotFound;
}

/// Input sampling of pass `index` (RetroArch: filter_linear#, wrap_mode#,
/// mipmap_input#); `smooth` replaces an unspecified filter.
- (Sampling)inputSamplingOfPass:(size_t)index smooth:(BOOL)smooth {
  Sampling sampling;
  if (index >= _passes.size()) {
    sampling.linear = smooth;
    return sampling;
  }
  const neoshader::SlangPass &pass = _passes[index].description;
  sampling.linear = pass.filter == FilterMode::Linear || (pass.filter == FilterMode::Unspecified && smooth);
  sampling.wrap = pass.wrap;
  sampling.linearMip = pass.filter != FilterMode::Nearest && pass.mipmapInput;
  return sampling;
}

/// Sampler for `texture` read with `sampling`: integer formats and, on GPUs
/// without 32-bit float filtering, float32 formats are read nearest.
- (id<MTLSamplerState>)samplerFor:(Sampling)sampling texture:(nullable id<MTLTexture>)texture {
  bool linear = sampling.linear;
  const MTLPixelFormat format = texture.pixelFormat;
  if (IsIntegerFormat(format) || (IsFloat32Format(format) && !_filtersFloat32)) linear = false;
  NSUInteger mip = 0;
  if (texture != nil && texture.mipmapLevelCount > 1) mip = sampling.linearMip && linear ? 2 : 1;
  return _samplers[SamplerIndex(linear, sampling.wrap, mip)];
}

/// The pass reads its input with mipmaps: the texture feeding it gets them.
- (bool)passReadsMipmaps:(size_t)index {
  return index < _passes.size() && _passes[index].description.mipmapInput;
}

@end

#pragma mark - Chain

@interface NeoSlangChain ()
@property(nonatomic, copy, readwrite, nullable) NSString *lastFailureCode;
@property(nonatomic, copy, readwrite, nullable) NSString *lastFailureDetail;
@end

@implementation NeoSlangChain {
  os_unfair_lock _lock;
  std::vector<float> _values;  // under _lock
  // Encoding thread.
  std::vector<PassTarget> _targets;
  std::vector<MTLSize> _sizes;
  NSMutableArray<id<MTLTexture>> *_history;  // previous pictures, newest first
  id<MTLTexture> _pendingOriginal;
  id<MTLTexture> _spareOriginal;
  BOOL _lastPassMatchesOutput;
  std::atomic<NSUInteger> _textureBytes;
}

- (instancetype)initWithProgram:(NeoSlangProgram *)program {
  self = [super init];
  if (self) {
    _program = program;
    _lock = OS_UNFAIR_LOCK_INIT;
    _values = program->_presetValues;
    _targets.resize(program->_passes.size());
    _sizes.resize(program->_passes.size(), MTLSizeMake(0, 0, 0));
    _history = [NSMutableArray array];
    _textureBytes = 0;
  }
  return self;
}

#pragma mark Parameters

- (float)clampedValue:(float)value atIndex:(size_t)index {
  NeoSlangProgram *program = _program;
  if (index >= program->_minimums.size()) return value;
  const float minimum = program->_minimums[index];
  const float maximum = program->_maximums[index];
  if (!(minimum < maximum)) return value;
  return std::min(std::max(value, minimum), maximum);
}

- (void)setParameterValues:(NSArray<NSNumber *> *)values {
  NeoSlangProgram *program = _program;
  std::vector<float> resolved = program->_presetValues;
  if ([values isKindOfClass:NSArray.class]) {
    const NSUInteger count = MIN(values.count, (NSUInteger)resolved.size());
    for (NSUInteger index = 0; index < count; index++) {
      id value = values[index];
      if (![value isKindOfClass:NSNumber.class]) continue;
      const float number = [value floatValue];
      if (!std::isfinite(number)) continue;
      resolved[index] = [self clampedValue:number atIndex:index];
    }
  }
  os_unfair_lock_lock(&_lock);
  _values = std::move(resolved);
  os_unfair_lock_unlock(&_lock);
}

- (void)setParameter:(NSString *)identifier value:(float)value {
  if (!std::isfinite(value)) return;
  const NSUInteger index = [_program indexOfParameter:identifier];
  if (index == NSNotFound) return;
  const float clamped = [self clampedValue:value atIndex:index];
  os_unfair_lock_lock(&_lock);
  if (index < _values.size()) _values[index] = clamped;
  os_unfair_lock_unlock(&_lock);
}

- (NSArray<NSNumber *> *)parameterValues {
  os_unfair_lock_lock(&_lock);
  const std::vector<float> values = _values;
  os_unfair_lock_unlock(&_lock);
  NSMutableArray<NSNumber *> *numbers = [NSMutableArray arrayWithCapacity:values.size()];
  for (float value : values) [numbers addObject:@(value)];
  return numbers;
}

#pragma mark Textures

- (nullable id<MTLTexture>)newTargetWithFormat:(MTLPixelFormat)format
                                          size:(MTLSize)size
                                     mipmapped:(bool)mipmapped {
  MTLTextureDescriptor *descriptor = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:format
                                                                                        width:size.width
                                                                                       height:size.height
                                                                                    mipmapped:mipmapped];
  descriptor.usage = MTLTextureUsageRenderTarget | MTLTextureUsageShaderRead;
  descriptor.storageMode = MTLStorageModePrivate;
  return [_program.device newTextureWithDescriptor:descriptor];
}

- (nullable id<MTLTexture>)originalTextureWithWidth:(NSUInteger)width height:(NSUInteger)height {
  if (width == 0 || height == 0 || width > kMaxTextureSide || height > kMaxTextureSide) return nil;
  const bool mipmapped = [_program passReadsMipmaps:0];
  const MTLSize size = MTLSizeMake(width, height, 1);
  if (TextureMatches(_pendingOriginal, MTLPixelFormatBGRA8Unorm, size, mipmapped)) return _pendingOriginal;
  if (TextureMatches(_spareOriginal, MTLPixelFormatBGRA8Unorm, size, mipmapped)) {
    _pendingOriginal = _spareOriginal;
    _spareOriginal = nil;
    return _pendingOriginal;
  }
  _pendingOriginal = [self newTargetWithFormat:MTLPixelFormatBGRA8Unorm size:size mipmapped:mipmapped];
  return _pendingOriginal;
}

- (void)reset {
  for (PassTarget &target : _targets) {
    target.output = nil;
    target.feedback = nil;
  }
  [_history removeAllObjects];
  _spareOriginal = nil;
  _textureBytes = TextureBytes(_pendingOriginal);
}

- (NSUInteger)textureBytes {
  return _textureBytes.load();
}

- (BOOL)lastPassMatchesOutput {
  return _lastPassMatchesOutput;
}

- (nullable id<MTLTexture>)failWithCode:(NSString *)code detail:(nullable NSString *)detail {
  self.lastFailureCode = code;
  self.lastFailureDetail = detail;
  return nil;
}

/// Texture bound to a semantic in pass `passIndex`.
- (nullable id<MTLTexture>)textureFor:(SlangTextureSemantic)semantic
                                index:(unsigned)index
                                 pass:(size_t)passIndex
                             original:(id<MTLTexture>)original
                               source:(id<MTLTexture>)source {
  NeoSlangProgram *program = _program;
  switch (semantic) {
    case SlangTextureSemantic::Original:
      return original;
    case SlangTextureSemantic::Source:
      return source;
    case SlangTextureSemantic::OriginalHistory:
      if (index == 0) return original;
      return index - 1 < _history.count ? _history[index - 1] : nil;
    case SlangTextureSemantic::PassOutput:
      return index < passIndex && index < _targets.size() ? _targets[index].output : nil;
    case SlangTextureSemantic::PassFeedback:
      return index < _targets.size() ? _targets[index].feedback : nil;
    case SlangTextureSemantic::User:
      return index < program->_luts.size() ? program->_luts[index].texture : nil;
  }
  return nil;
}

/// Sampling of a texture semantic in pass `passIndex` (RetroArch: Original
/// and history follow pass 0's input settings, Source this pass's,
/// PassOutput# and PassFeedback# those of pass # + 1, LUTs their own).
- (Sampling)samplingFor:(SlangTextureSemantic)semantic
                  index:(unsigned)index
                   pass:(size_t)passIndex
                 smooth:(BOOL)smooth {
  NeoSlangProgram *program = _program;
  switch (semantic) {
    case SlangTextureSemantic::Original:
    case SlangTextureSemantic::OriginalHistory:
      return [program inputSamplingOfPass:0 smooth:smooth];
    case SlangTextureSemantic::Source:
      return [program inputSamplingOfPass:passIndex smooth:smooth];
    case SlangTextureSemantic::PassOutput:
    case SlangTextureSemantic::PassFeedback:
      return [program inputSamplingOfPass:(size_t)index + 1 smooth:smooth];
    case SlangTextureSemantic::User:
      if (index < program->_luts.size()) return program->_luts[index].sampling;
      break;
  }
  return Sampling();
}

#pragma mark Encoding

- (nullable id<MTLTexture>)encodeOnCommandBuffer:(id<MTLCommandBuffer>)commandBuffer
                                      outputSize:(CGSize)outputSize
                                    viewportSize:(CGSize)viewportSize
                                           frame:(NeoSlangFrameState)frame
                                          smooth:(BOOL)smooth {
  self.lastFailureCode = nil;
  self.lastFailureDetail = nil;
  NeoSlangProgram *program = _program;
  const size_t passCount = program->_passes.size();
  id<MTLTexture> original = _pendingOriginal;
  if (commandBuffer == nil || original == nil || passCount == 0) {
    return [self failWithCode:@"CHAIN_NO_PICTURE" detail:nil];
  }
  const NSUInteger outputWidth = SideFromDouble(outputSize.width);
  const NSUInteger outputHeight = SideFromDouble(outputSize.height);
  if (outputWidth == 0 || outputHeight == 0) {
    return [self failWithCode:@"CHAIN_OUTPUT_SIZE"
                         detail:[NSString stringWithFormat:@"%gx%g", (double)outputSize.width,
                                                           (double)outputSize.height]];
  }

  // Sizes of every pass (Pass::get_output_size), then the memory they need.
  NSUInteger sourceWidth = original.width;
  NSUInteger sourceHeight = original.height;
  for (size_t index = 0; index < passCount; index++) {
    const RuntimePass &pass = program->_passes[index];
    NSUInteger width = sourceWidth;
    NSUInteger height = sourceHeight;
    if (pass.drawsViewport) {
      width = outputWidth;
      height = outputHeight;
    } else if (pass.description.scaleSet) {
      width = ScaledSide(pass.description.scaleTypeX, pass.description.scaleX, pass.description.absoluteX,
                         sourceWidth, outputWidth);
      height = ScaledSide(pass.description.scaleTypeY, pass.description.scaleY, pass.description.absoluteY,
                          sourceHeight, outputHeight);
    }
    if (width == 0 || height == 0 || width > kMaxTextureSide || height > kMaxTextureSide) {
      return [self failWithCode:@"CHAIN_PASS_SIZE"
                         detail:[NSString stringWithFormat:@"pass %zu: %lux%lu", index, (unsigned long)width,
                                                           (unsigned long)height]];
    }
    _sizes[index] = MTLSizeMake(width, height, 1);
    sourceWidth = width;
    sourceHeight = height;
  }
  const NSUInteger depth = program.historyDepth;
  unsigned long long bytes = TextureBytes(original);
  for (NSUInteger index = 0; index < depth; index++) {
    bytes += index < _history.count ? TextureBytes(_history[index]) : TextureBytes(original);
  }
  for (size_t index = 0; index < passCount; index++) {
    const RuntimePass &pass = program->_passes[index];
    const bool mipmapped = [program passReadsMipmaps:index + 1] && !IsIntegerFormat(pass.format);
    const unsigned long long one = TextureBytes(_sizes[index].width, _sizes[index].height, pass.format, mipmapped);
    bytes += program->_feedback[index] ? one * 2 : one;
  }
  if (bytes > kChainMemoryBudget) {
    return [self failWithCode:@"CHAIN_MEMORY"
                       detail:[NSString stringWithFormat:@"%llu bytes for %lux%lu", bytes,
                                                         (unsigned long)outputWidth, (unsigned long)outputHeight]];
  }

  // Framebuffers of the right size; history and feedback start black.
  std::vector<id<MTLTexture>> cleared;
  for (size_t index = 0; index < passCount; index++) {
    const RuntimePass &pass = program->_passes[index];
    const bool mipmapped = [program passReadsMipmaps:index + 1] && !IsIntegerFormat(pass.format) &&
                           !(IsFloat32Format(pass.format) && !program->_filtersFloat32);
    PassTarget &target = _targets[index];
    if (!TextureMatches(target.output, pass.format, _sizes[index], mipmapped)) {
      target.output = [self newTargetWithFormat:pass.format size:_sizes[index] mipmapped:mipmapped];
      target.feedback = nil;
      if (target.output == nil) return [self failWithCode:@"CHAIN_ALLOCATION" detail:nil];
    }
    if (program->_feedback[index] && target.feedback == nil) {
      target.feedback = [self newTargetWithFormat:pass.format size:_sizes[index] mipmapped:mipmapped];
      if (target.feedback == nil) return [self failWithCode:@"CHAIN_ALLOCATION" detail:nil];
      cleared.push_back(target.feedback);
    }
  }
  while (_history.count < depth) {
    id<MTLTexture> black = [self newTargetWithFormat:MTLPixelFormatBGRA8Unorm
                                                size:MTLSizeMake(original.width, original.height, 1)
                                           mipmapped:original.mipmapLevelCount > 1];
    if (black == nil) return [self failWithCode:@"CHAIN_ALLOCATION" detail:nil];
    [_history addObject:black];
    cleared.push_back(black);
  }
  for (id<MTLTexture> texture : cleared) ClearTexture(commandBuffer, texture);
  GenerateMipmaps(commandBuffer, original);

  std::vector<float> values;
  os_unfair_lock_lock(&_lock);
  values = _values;
  os_unfair_lock_unlock(&_lock);

  const float coreAspect = frame.coreAspect > 0.0f && std::isfinite(frame.coreAspect)
                               ? frame.coreAspect
                               : (float)original.width / (float)MAX(original.height, (NSUInteger)1);
  const float rotatedAspect = (frame.rotation % 2) == 1 ? 1.0f / coreAspect : coreAspect;
  float viewport[4];
  SizeVector(SideFromDouble(viewportSize.width), SideFromDouble(viewportSize.height), viewport);

  id<MTLDevice> device = program.device;
  id<MTLTexture> source = original;
  for (size_t index = 0; index < passCount; index++) {
    const RuntimePass &pass = program->_passes[index];
    id<MTLTexture> target = _targets[index].output;
    MTLRenderPassDescriptor *descriptor = [MTLRenderPassDescriptor renderPassDescriptor];
    descriptor.colorAttachments[0].texture = target;
    descriptor.colorAttachments[0].loadAction = MTLLoadActionClear;
    descriptor.colorAttachments[0].clearColor = MTLClearColorMake(0, 0, 0, 0);
    descriptor.colorAttachments[0].storeAction = MTLStoreActionStore;
    id<MTLRenderCommandEncoder> encoder = [commandBuffer renderCommandEncoderWithDescriptor:descriptor];
    if (encoder == nil) return [self failWithCode:@"CHAIN_ENCODER" detail:nil];
    [encoder setRenderPipelineState:pass.pipeline];
    [encoder setVertexBytes:kQuad length:sizeof(kQuad) atIndex:kVertexBufferIndex];

    std::vector<uint8_t> ubo(pass.compiled.uboSize, 0);
    std::vector<uint8_t> push(pass.compiled.pushSize, 0);
    for (const SlangUniformSlot &slot : pass.compiled.uniforms) {
      uint8_t value[64];
      size_t size = 0;
      switch (slot.kind) {
        case SlangUniformSlot::Kind::Semantic: {
          uint32_t unsignedValue = 0;
          int32_t signedValue = 0;
          float floatValue = 0.0f;
          float vector[4];
          switch (slot.semantic) {
            case SlangSemantic::MVP:
              std::memcpy(value, kMVP, sizeof(kMVP));
              size = sizeof(kMVP);
              break;
            case SlangSemantic::OutputSize:
              SizeVector(_sizes[index].width, _sizes[index].height, vector);
              std::memcpy(value, vector, sizeof(vector));
              size = sizeof(vector);
              break;
            case SlangSemantic::FinalViewportSize:
              std::memcpy(value, viewport, sizeof(viewport));
              size = sizeof(viewport);
              break;
            case SlangSemantic::FrameCount:
              unsignedValue = pass.description.frameCountMod > 0 ? frame.frameCount % pass.description.frameCountMod
                                                                  : frame.frameCount;
              break;
            case SlangSemantic::FrameDirection:
              signedValue = frame.frameDirection;
              break;
            case SlangSemantic::FrameTimeDelta:
              unsignedValue = frame.frameTimeDelta;
              break;
            case SlangSemantic::OriginalFPS:
              floatValue = frame.coreFPS;
              break;
            case SlangSemantic::Rotation:
              unsignedValue = frame.rotation % 4;
              break;
            case SlangSemantic::OriginalAspect:
              floatValue = coreAspect;
              break;
            case SlangSemantic::OriginalAspectRotated:
              floatValue = rotatedAspect;
              break;
            case SlangSemantic::TotalSubFrames:
            case SlangSemantic::CurrentSubFrame:
              unsignedValue = 1;
              break;
            case SlangSemantic::SwapCount:
              unsignedValue = frame.swapCount;
              break;
          }
          if (size == 0) {
            if (slot.semantic == SlangSemantic::FrameDirection) {
              std::memcpy(value, &signedValue, sizeof(signedValue));
            } else if (slot.semantic == SlangSemantic::OriginalFPS || slot.semantic == SlangSemantic::OriginalAspect ||
                       slot.semantic == SlangSemantic::OriginalAspectRotated) {
              std::memcpy(value, &floatValue, sizeof(floatValue));
            } else {
              std::memcpy(value, &unsignedValue, sizeof(unsignedValue));
            }
            size = 4;
          }
          break;
        }
        case SlangUniformSlot::Kind::TextureSize: {
          NSUInteger width = 0;
          NSUInteger height = 0;
          switch (slot.textureSemantic) {
            case SlangTextureSemantic::Source:
              width = index == 0 ? original.width : _sizes[index - 1].width;
              height = index == 0 ? original.height : _sizes[index - 1].height;
              break;
            case SlangTextureSemantic::PassOutput:
            case SlangTextureSemantic::PassFeedback:
              if (slot.index < passCount) {
                width = _sizes[slot.index].width;
                height = _sizes[slot.index].height;
              }
              break;
            default: {
              id<MTLTexture> texture = [self textureFor:slot.textureSemantic
                                                  index:slot.index
                                                   pass:index
                                               original:original
                                                 source:source];
              width = texture.width;
              height = texture.height;
              break;
            }
          }
          float vector[4];
          SizeVector(width, height, vector);
          std::memcpy(value, vector, sizeof(vector));
          size = sizeof(vector);
          break;
        }
        case SlangUniformSlot::Kind::Parameter: {
          const float parameter = slot.index < values.size() ? values[slot.index] : 0.0f;
          std::memcpy(value, &parameter, sizeof(parameter));
          size = sizeof(parameter);
          break;
        }
      }
      PutBytes(ubo, slot.uboOffset, value, size);
      PutBytes(push, slot.pushOffset, value, size);
    }
    BindBytes(encoder, device, ubo, 0);
    BindBytes(encoder, device, push, 1);

    for (const neoshader::SlangTextureSlot &slot : pass.compiled.textures) {
      id<MTLTexture> texture = [self textureFor:slot.semantic
                                          index:slot.index
                                           pass:index
                                       original:original
                                         source:source];
      const Sampling sampling = [self samplingFor:slot.semantic index:slot.index pass:index smooth:smooth];
      [encoder setFragmentTexture:texture atIndex:slot.binding];
      [encoder setFragmentSamplerState:[program samplerFor:sampling texture:texture] atIndex:slot.binding];
    }
    [encoder drawPrimitives:MTLPrimitiveTypeTriangleStrip vertexStart:0 vertexCount:4];
    [encoder endEncoding];
    GenerateMipmaps(commandBuffer, target);
    source = target;
  }

  id<MTLTexture> result = _targets[passCount - 1].output;
  _lastPassMatchesOutput =
      _sizes[passCount - 1].width == outputWidth && _sizes[passCount - 1].height == outputHeight;

  // End of frame: outputs become feedback (Pass::end_frame), the picture
  // enters the history ring and the oldest picture is reused.
  for (size_t index = 0; index < passCount; index++) {
    if (program->_feedback[index]) std::swap(_targets[index].output, _targets[index].feedback);
  }
  if (depth > 0) {
    [_history insertObject:original atIndex:0];
    while (_history.count > depth) {
      _spareOriginal = _history.lastObject;
      [_history removeLastObject];
    }
  } else {
    _spareOriginal = original;
  }
  _pendingOriginal = nil;
  _textureBytes = (NSUInteger)MIN(bytes, (unsigned long long)NSUIntegerMax);
  return result;
}

@end
