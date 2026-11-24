#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#import <QuartzCore/QuartzCore.h>

#include "libretro.h"

NS_ASSUME_NONNULL_BEGIN

/// Receives one finished core frame copied to host memory, top-left origin.
/// The bytes are valid only during the call. Called on the emulation thread,
/// outside the queue lock.
typedef void (^LibretroVulkanFrameHandler)(const void *pixels, unsigned width, unsigned height, size_t bytesPerRow,
                                           MTLPixelFormat pixelFormat);

/// Receives one finished core frame as a Metal buffer that aliases the
/// slot's read-back memory (no CPU copy). The receiver copies it on the GPU
/// and calls `released` exactly once, after that GPU work has completed (or
/// at once when it gives up the frame): the slot is not written again
/// before. Called on the emulation thread, outside the queue lock.
typedef void (^LibretroVulkanBufferHandler)(id<MTLBuffer> buffer, unsigned width, unsigned height, size_t bytesPerRow,
                                            MTLPixelFormat pixelFormat, dispatch_block_t released);

/// Vulkan hardware context for libretro cores, through the MoltenVK
/// framework embedded with the cores. Implements the libretro Vulkan render
/// interface (v5) and context negotiation (v1 and v2).
///
/// Frame hand-off (normal mode). No swapchain and no surface on the
/// session's layer: negotiation receives VK_NULL_HANDLE as surface
/// (libretro_vulkan.h makes it optional; Azahar ignores it). A ring of
/// LIBRETRO_VK_HANDOFF_SLOTS (2) slots, each with a fence, a command buffer
/// and a persistently mapped host-visible, host-coherent buffer:
/// - get_sync_index returns the current slot; get_sync_index_mask is
///   (1 << slots) - 1, fixed in `prepare:`; wait_sync_index waits on the
///   current slot's fence;
/// - `endFrameWithWidth:height:valid:` records, in the slot's command
///   buffer: a barrier taking the core image from its layout to
///   TRANSFER_SRC_OPTIMAL (src stage ALL_COMMANDS, acquiring from the
///   core's queue family when different; a GENERAL image stays in GENERAL,
///   as libretro_vulkan.h forbids transitioning it), vkCmdCopyImageToBuffer of
///   (0,0,w,h) with bufferRowLength 0, a barrier back to the original layout
///   (releasing to the source queue family when different) and a buffer
///   barrier TRANSFER_WRITE -> HOST_READ; then submits the core's command
///   buffers and the copy under the queue lock, waiting on the core's
///   semaphores and signalling the core's signal semaphore and the slot's
///   fence. Duplicated frames (`valid` NO) still submit the core's command
///   buffers and signal its semaphore, without copying;
/// - the previous slot is handed to `frameHandler` once its fence has
///   signalled (one frame of latency, no CPU/GPU stall every frame);
/// - GPU hand-off: when the slot's mapped memory is page-aligned, a Metal
///   buffer wraps it (newBufferWithBytesNoCopy) and the slot goes to
///   `bufferHandler` instead, which copies it to a texture on the GPU. A
///   frame of Azahar at 7x (2800x3360, 37.6 MB) is then never copied by the
///   CPU (replaceRegion on the emulation thread). The slot is lent until
///   the handler releases it: recording into it, or freeing its memory,
///   waits for that (2 s at most);
/// Formats: 8-bit R8G8B8A8 / B8G8R8A8 UNORM or SRGB are copied as raw bytes
/// (MTLPixelFormatRGBA8Unorm / BGRA8Unorm); A2B10G10R10 -> RGB10A2Unorm;
/// A2R10G10B10 -> BGR10A2Unorm; any other format is first blitted into an
/// owned B8G8R8A8_UNORM image of the slot. Read-back time is logged.
/// VK_EXT_metal_objects is not used (MoltenVK 1.2.8 crashes with it under
/// ARC).
///
/// Legacy presentation (fallback, decided once in `prepare:` when the
/// hand-off resources cannot be created): the core's image is blitted,
/// aspect-fitted, into a swapchain on `layer` as before; `handsOffFrames`
/// is then NO and the session reports that screens and shaders are
/// unavailable for this renderer.
///
/// Every method runs on the emulation thread.
@interface LibretroVulkanRenderer : NSObject

+ (nullable instancetype)rendererForCallback:(struct retro_hw_render_callback *)callback
                                       layer:(CAMetalLayer *)layer;

+ (unsigned)negotiationVersionForType:(enum retro_hw_render_context_negotiation_interface_type)type;

/// Optimal-tiling features (VkFormatFeatureFlags) MoltenVK reports for
/// `format` (a VkFormat) on the GPU `prepare:` takes, read from a throwaway
/// instance (no core, no device) and kept for the process once known. NO
/// when MoltenVK or the instance is unavailable (`prepare:` would fail too).
+ (BOOL)optimalTilingFeatures:(uint32_t *_Nullable)features ofFormat:(uint32_t)format;
- (BOOL)setNegotiationInterface:(const struct retro_hw_render_context_negotiation_interface *)negotiation;

/// Set before `prepare:`. While nil, handed-off frames are dropped.
@property(nonatomic, copy, nullable) LibretroVulkanFrameHandler frameHandler;
/// Preferred over `frameHandler` for a slot whose memory Metal can wrap.
@property(nonatomic, copy, nullable) LibretroVulkanBufferHandler bufferHandler;

/// Instance, device, then hand-off resources (or the legacy surface and
/// swapchain); call before context_reset.
- (BOOL)prepare:(NSError *_Nullable *_Nullable)error;
- (const struct retro_hw_render_interface *_Nullable)renderInterface;

@property(nonatomic, readonly) BOOL handsOffFrames;

- (void)beginFrame;
- (void)endFrameWithWidth:(unsigned)width height:(unsigned)height valid:(BOOL)valid;
/// Waits for the slot still in flight and hands it to `frameHandler` (game
/// paused or menu opened, so the newest frame is the one kept on screen).
- (void)flushPendingFrame;

/// Legacy presentation only.
@property(nonatomic, assign) BOOL smooth;
@property(nonatomic, assign) float aspectRatio;
@property(nonatomic, readonly) CGRect normalizedVideoRect;

/// Waits for the GPU (every slot fence); the core's context_destroy must
/// run after this and before `teardown`.
- (void)waitIdle;
- (void)teardown;

@end

NS_ASSUME_NONNULL_END
