// SPDX-License-Identifier: GPL-3.0-or-later
// The actual NeoStation presenter, not an imitation of its shader chain.
// A drawable is replaced by a readable offscreen target so pixels can be
// asserted deterministically; input copy, passes and final copy are unchanged.
#import <Foundation/Foundation.h>
#import <Metal/Metal.h>

#import "LibretroMetalPresenter.h"
#import "LibretroShaderLibrary.h"
#import "NeoSlangRenderer.h"

#include <cstdio>
#include <cstring>
#include <vector>

@interface LibretroMetalPresenter (TestAccess)
- (NSArray<LibretroPresenterScreen *> *)screensForWidth:(NSUInteger)width height:(NSUInteger)height
                                             generation:(uint64_t *)generation;
- (NSArray<NSValue *> *)encodeFrameOnBuffer:(id<MTLCommandBuffer>)buffer target:(id<MTLTexture>)target
                                    screens:(NSArray<LibretroPresenterScreen *> *)screens
                                    texture:(id<MTLTexture>)texture width:(unsigned)width height:(unsigned)height
                                    flipped:(BOOL)flipped;
- (void)observeSlangActivationOnBuffer:(id<MTLCommandBuffer>)buffer generation:(uint64_t)generation;
@end

static int checks, failures;
#define CHECK(condition, detail) do { checks++; if (!(condition)) { failures++; std::fprintf(stderr, "FAIL: %s\n", detail); } } while (0)

static void DrainMainQueue(BOOL (^done)(void)) {
  NSDate *deadline = [NSDate dateWithTimeIntervalSinceNow:5.0];
  while (!done() && deadline.timeIntervalSinceNow > 0) {
    [[NSRunLoop mainRunLoop] runUntilDate:[NSDate dateWithTimeIntervalSinceNow:0.001]];
  }
}

static id<MTLTexture> Input(id<MTLDevice> device, MTLPixelFormat format) {
  MTLTextureDescriptor *desc = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:format width:8 height:6 mipmapped:NO];
  desc.usage = MTLTextureUsageShaderRead;
  id<MTLTexture> texture = [device newTextureWithDescriptor:desc];
  std::vector<uint32_t> pixels(48);
  for (NSUInteger y = 0; y < 6; y++) {
    for (NSUInteger x = 0; x < 8; x++) {
      const uint32_t red = (uint32_t)(x * 30 + 5), green = (uint32_t)(y * 40 + 7), blue = 100;
      uint32_t value = (255u << 24) | (blue << 16) | (green << 8) | red;
      if (format == MTLPixelFormatBGRA8Unorm) value = (255u << 24) | (red << 16) | (green << 8) | blue;
      if (format == MTLPixelFormatRGB10A2Unorm || format == MTLPixelFormatBGR10A2Unorm) {
        const uint32_t first = format == MTLPixelFormatRGB10A2Unorm ? red : blue;
        const uint32_t last = format == MTLPixelFormatRGB10A2Unorm ? blue : red;
        value = (3u << 30) | ((last * 1023 / 255) << 20) | ((green * 1023 / 255) << 10) | (first * 1023 / 255);
      }
      pixels[y * 8 + x] = value;
    }
  }
  [texture replaceRegion:MTLRegionMake2D(0, 0, 8, 6) mipmapLevel:0 withBytes:pixels.data() bytesPerRow:32];
  return texture;
}

static NSData *Draw(LibretroMetalPresenter *presenter, id<MTLTexture> source, BOOL flipped = NO) {
  MTLTextureDescriptor *desc = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatBGRA8Unorm width:16 height:12 mipmapped:NO];
  desc.storageMode = MTLStorageModePrivate;
  desc.usage = MTLTextureUsageRenderTarget;
  id<MTLTexture> target = [presenter.device newTextureWithDescriptor:desc];
  id<MTLCommandQueue> queue = [presenter.device newCommandQueue];
  id<MTLCommandBuffer> buffer = [queue commandBuffer];
  uint64_t generation = 0;
  NSArray *screens = [presenter screensForWidth:16 height:12 generation:&generation];
  [presenter encodeFrameOnBuffer:buffer target:target screens:screens texture:source width:8 height:6 flipped:flipped];
  [presenter observeSlangActivationOnBuffer:buffer generation:generation];
  id<MTLBuffer> readback = [presenter.device newBufferWithLength:16 * 12 * 4 options:MTLResourceStorageModeShared];
  id<MTLBlitCommandEncoder> blit = [buffer blitCommandEncoder];
  [blit copyFromTexture:target sourceSlice:0 sourceLevel:0 sourceOrigin:MTLOriginMake(0, 0, 0)
             sourceSize:MTLSizeMake(16, 12, 1) toBuffer:readback destinationOffset:0
   destinationBytesPerRow:64 destinationBytesPerImage:16 * 12 * 4];
  [blit endEncoding];
  [buffer commit];
  [buffer waitUntilCompleted];
  CHECK(buffer.status == MTLCommandBufferStatusCompleted, "actual presenter GPU buffer completed");
  return [NSData dataWithBytes:readback.contents length:readback.length];
}

static NeoSlangProgram *Program(LibretroMetalPresenter *presenter, NSString *root, NSString *path) {
  NSError *error = nil;
  NeoSlangProgram *program = [NeoSlangProgram programWithRoot:root preset:path device:presenter.device iosPlatform:NO error:&error];
  if (program == nil) std::fprintf(stderr, "%s: %s %s\n", path.UTF8String,
                                   [error.userInfo[NeoSlangErrorCodeKey] UTF8String],
                                   [error.userInfo[NSDebugDescriptionErrorKey] UTF8String]);
  CHECK(program != nil, "fixture compiles");
  return program;
}

int main(int argc, char **argv) {
  @autoreleasepool {
    if (argc != 2) return 2;
    if (MTLCreateSystemDefaultDevice() == nil) return 3;
    LibretroMetalPresenter *presenter = [[LibretroMetalPresenter alloc] initWithLayer:[CAMetalLayer layer]];
    CHECK(presenter != nil, "actual NeoStation presenter initializes");
    if (presenter == nil) return 1;
    [presenter setDrawableSize:CGSizeMake(16, 12)];
    NSString *root = [NSString stringWithUTF8String:argv[1]];
    NeoSlangProgram *stock = Program(presenter, root, @"stock.slangp");
    NeoSlangProgram *multi = Program(presenter, root, @"multipass.slangp");
    NeoSlangProgram *huge = Program(presenter, root, @"huge.slangp");
    NeoSlangProgram *parameter = Program(presenter, root, @"sections.slangp");
    if (!stock || !multi || !huge || !parameter) return 1;
    id<MTLTexture> input = Input(presenter.device, MTLPixelFormatBGRA8Unorm);
    NSData *plain = Draw(presenter, input);
    __block int callbacks = 0;
    __block BOOL success = NO;
    __block NSString *code = nil;
    void (^completed)(BOOL, NSString *) = ^(BOOL ok, NSString *failure) { callbacks++; success = ok; code = failure; };

    [presenter setSlangProgram:stock identifier:@"slang:stock" parameters:@{} completion:completed];
    CHECK(callbacks == 0, "compilation/selection alone is not activation success");
    NSData *filtered = Draw(presenter, input);
    DrainMainQueue(^{ return callbacks == 1; });
    CHECK(callbacks == 1 && success && code == nil, "first complete GPU frame accepts candidate once");
    CHECK([filtered isEqualToData:plain], "core copy + stock chain + final copy preserve all pixels/orientation");

    LibretroShaderPreset *invalidBuiltin = [LibretroShaderPreset new];
    [invalidBuiltin setValue:@"invalid-builtin-test" forKey:@"identifier"];
    [invalidBuiltin setValue:@"this is invalid Metal source" forKey:@"fragmentSource"];
    NSError *builtinError = nil;
    CHECK(![presenter setShaderPreset:invalidBuiltin parameters:nil error:&builtinError] && builtinError != nil,
          "built-in compiler failure is reported");
    CHECK([presenter.activePresetIdentifier isEqualToString:@"slang:stock"] &&
          [Draw(presenter, input) isEqualToData:plain], "built-in compiler failure preserves previous shader");

    // Reproduces the pre-fix false success: huge.slangp compiles, but fails
    // CHAIN_MEMORY during the first actual presenter draw. It must not be
    // persisted as successfully rendered, and the preceding choice survives.
    callbacks = 0;
    [presenter setSlangProgram:huge identifier:@"slang:huge" parameters:@{} completion:completed];
    filtered = Draw(presenter, input);
    DrainMainQueue(^{ return callbacks == 1; });
    CHECK(callbacks == 1 && !success && [code isEqualToString:@"CHAIN_MEMORY"], "compiled but unrunnable preset reports failure");
    CHECK([filtered isEqualToData:plain], "recoverable chain failure draws standard picture");
    [presenter rollbackLastSlangActivation];
    CHECK([presenter.activePresetIdentifier isEqualToString:@"slang:stock"], "failed candidate restores preceding accepted shader");
    CHECK([Draw(presenter, input) isEqualToData:plain], "preceding chains remain usable after rollback");

    // All formats reaching the shared presenter: software/GL BGRA, Vulkan
    // RGBA and both packed 10-bit variants. Every one feeds slang in BGRA.
    for (NSNumber *format in @[@(MTLPixelFormatBGRA8Unorm), @(MTLPixelFormatRGBA8Unorm), @(MTLPixelFormatRGB10A2Unorm), @(MTLPixelFormatBGR10A2Unorm)]) {
      id<MTLTexture> frame = Input(presenter.device, (MTLPixelFormat)format.unsignedIntegerValue);
      [presenter setSlangProgram:nil identifier:nil parameters:nil];
      NSData *reference = Draw(presenter, frame);
      [presenter setSlangProgram:stock identifier:@"slang:stock" parameters:@{}];
      CHECK([Draw(presenter, frame) isEqualToData:reference], "shared renderer format survives shader activation");
      [presenter setSlangProgram:nil identifier:nil parameters:nil];
      reference = Draw(presenter, frame, YES);
      [presenter setSlangProgram:stock identifier:@"slang:stock" parameters:@{}];
      CHECK([Draw(presenter, frame, YES) isEqualToData:reference], "GL bottom-left input preserves orientation through chain");
    }

    for (int change = 0; change < 12; change++) {
      callbacks = 0;
      [presenter setSlangProgram:(change % 2 == 0 ? multi : stock) identifier:(change % 2 == 0 ? @"slang:multi" : @"slang:stock") parameters:@{} completion:completed];
      Draw(presenter, input);
      DrainMainQueue(^{ return callbacks == 1; });
      CHECK(success && callbacks == 1, "repeated single/multiple-pass switch completes");
    }
    // Session receives a newer request while the old GPU frame has already
    // completed but its main callback has not run. The newer request fails
    // compilation: no subsequent setSlangProgram call occurs. Invalidation
    // must therefore preserve the preceding accepted stock selection for the
    // emulation-thread rollback, rather than implicitly accepting `multi`.
    callbacks = 0;
    [presenter setSlangProgram:multi identifier:@"slang:provisional" parameters:@{} completion:completed];
    Draw(presenter, input);
    [presenter invalidatePendingSlangActivation];
    DrainMainQueue(^{ return callbacks == 1; });
    CHECK(callbacks == 1 && !success && [code isEqualToString:@"SHADER_SUPERSEDED"], "new request invalidates late GPU success before its compilation finishes");
    [presenter rollbackLastSlangActivation];
    CHECK([presenter.activePresetIdentifier isEqualToString:@"slang:stock"], "failed newer compilation restores prior accepted shader");
    CHECK([Draw(presenter, input) isEqualToData:plain], "failed newer compilation preserves prior accepted pixels");
    callbacks = 0;
    [presenter setSlangProgram:multi identifier:@"slang:provisional" parameters:@{} completion:completed];
    [presenter invalidatePendingSlangActivation];
    [presenter rollbackLastSlangActivation];
    DrainMainQueue(^{ return callbacks == 1; });
    CHECK(callbacks == 1 && !success && [code isEqualToString:@"SHADER_SUPERSEDED"], "new request before any frame cancels provisional callback exactly once");
    CHECK([presenter.activePresetIdentifier isEqualToString:@"slang:stock"], "invalidation before first frame retains accepted selection");
    callbacks = 0;
    [presenter setSlangProgram:stock identifier:@"slang:old" parameters:@{} completion:completed];
    [presenter setSlangProgram:nil identifier:nil parameters:nil];
    DrainMainQueue(^{ return callbacks == 1; });
    CHECK(callbacks == 1 && !success && [code isEqualToString:@"SHADER_SUPERSEDED"], "disable before first frame supersedes candidate once");
    CHECK([Draw(presenter, input) isEqualToData:plain], "disable restores unfiltered pixels");
    callbacks = 0;
    [presenter setSlangProgram:stock identifier:@"slang:old" parameters:@{} completion:completed];
    Draw(presenter, input); // GPU complete, main-queue callback still queued.
    [presenter setSlangProgram:nil identifier:nil parameters:nil];
    DrainMainQueue(^{ return callbacks == 1; });
    CHECK(callbacks == 1 && !success && [code isEqualToString:@"SHADER_SUPERSEDED"], "late GPU callback cannot accept a superseded choice");
    callbacks = 0;
    [presenter setSlangProgram:parameter identifier:@"slang:parameter" parameters:@{@"STRENGTH": @0.0} completion:completed];
    NSData *black = Draw(presenter, input);
    DrainMainQueue(^{ return callbacks == 1; });
    CHECK(success && ![black isEqualToData:plain], "parameter change reaches actual displayed shader output");
    [presenter setShaderParameter:@"STRENGTH" value:1.0];
    CHECK([Draw(presenter, input) isEqualToData:plain], "live parameter restores expected picture");
    std::printf("libretro presenter: %d checks, %d failures (macOS Metal, synthetic core images)\n", checks, failures);
    return failures ? 1 : 0;
  }
}
