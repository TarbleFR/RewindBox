using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.Vulkan;
using Silk.NET.Vulkan;
using Format = Ryujinx.Graphics.GAL.Format;

bool control = args[0] == "control";
int checks = 0;
void Check(bool condition, string message) { checks++; if (!condition) throw new Exception(message); }
TextureCreateInfo Info(int width, int height, int depth = 1, int levels = 1, int bpp = 4,
    Target target = Target.Texture2D, Format format = Format.R8G8B8A8Unorm, int block = 1) =>
    new(width, height, depth, levels, 1, block, block, bpp, format, DepthStencilMode.Depth, target,
        SwizzleComponent.Red, SwizzleComponent.Green, SwizzleComponent.Blue, SwizzleComponent.Alpha);
byte[] Bytes(int size, int seed) { var bytes = new byte[size]; new Random(seed).NextBytes(bytes); return bytes; }
var digests = new List<string>();
int ordinaryUploadsNativeBuffers, fullRingFallbackBuffers;
int nonzeroOffsetCopyCount;

{
    var gd = new VulkanRenderer();
    var texture = new TextureView(gd, Info(16, 16));
    int before = gd.BufferManager.NativeCreates;
    for (int i = 0; i < 1024; i++) texture.Upload(Bytes(1024, i));
    ordinaryUploadsNativeBuffers = gd.BufferManager.NativeCreates - before;
    Check(gd.Api.Copies.Count == 1024, "An ordinary upload disappeared");
    if (!control) Check(gd.Api.Copies.Any(c => c.Region.BufferOffset != 0), "Uploads never used ring offsets");
    digests.Add(gd.Api.Complete());
    Check(gd.PipelineInternal.EndRenderPassCalls == 0, "Preload uploads ended a render pass");
}

// Unsignaled fences hold the entire 16MiB texture ring. Further uploads fall back rather
// than waiting, flushing, or overwriting any bytes still used by earlier copies.
{
    var gd = new VulkanRenderer();
    var texture = new TextureView(gd, Info(32, 32));
    texture.Storage.Inline = true;
    int before = gd.BufferManager.NativeCreates;
    for (int i = 0; i < 4098; i++) texture.Upload(Bytes(4096, i));
    fullRingFallbackBuffers = gd.BufferManager.NativeCreates - before;
    Check(gd.Api.Copies.Count == 4098, "Ring exhaustion dropped an upload");
    Check(gd.PipelineInternal.EndRenderPassCalls == 4098, "Inline upload ordering changed");
    digests.Add(gd.Api.Complete());
    // Buffer uploads retain their own ring. Filling the texture ring must not
    // make this previously non-blocking upload flush or wait.
    using (var vertex = gd.BufferManager.Create(gd, 4096)) {
        byte[] vertexData = Bytes(4096, 2222);
        gd.BufferManager.StagingBuffer.PushData(gd.CommandBufferPool,
            gd.PipelineInternal.CurrentCommandBuffer, null, vertex, 0, vertexData);
        Check(vertex.Data.SequenceEqual(vertexData), "Mixed buffer upload changed data");
    }
    foreach (var fence in gd.CommandBufferPool.Fences.Values) fence.Signaled = true;
    gd.BufferManager.StagingBuffer.FreeCompleted();
    before = gd.BufferManager.NativeCreates;
    texture.Upload(Bytes(4096, 9999));
    if (!control) Check(gd.BufferManager.NativeCreates == before, "Completed ring was not reused");
    digests.Add(gd.Api.Complete());
    gd.BufferManager.Dispose();
    gd.BufferManager.Dispose();
    Check(gd.BufferManager.AllCreated.All(b => b.DisposeCount == 1), "Both rings did not release exactly once");
    Check(gd.CommandBufferPool.Fences.Values.All(f => f.References == 0), "Staging rings kept fence references after close");
}

// CopyTo(BufferRange) passes a byte count and an independent destination offset.
// The original method mistook the count for an absolute backing-buffer limit.
{
    var gd = new VulkanRenderer();
    var texture = new TextureView(gd, Info(16, 16, levels: 3));
    var holder = gd.BufferManager.Create(gd, 4096);
    texture.CopyFromOrToBuffer(gd.PipelineInternal.CurrentCommandBuffer.CommandBuffer,
        holder.GetBuffer().Get(gd.PipelineInternal.CurrentCommandBuffer).Value,
        texture.GetImage().Get(gd.PipelineInternal.CurrentCommandBuffer).Value,
        1024 + 256, true, 0, 0, 1, 3, false, 512);
    nonzeroOffsetCopyCount = gd.Api.Copies.Count;
    Check(nonzeroOffsetCopyCount == (control ? 0 : 2), "Nonzero-offset byte-count bound changed unexpectedly");
    if (!control) {
        Check(gd.Api.Copies[0].Region.BufferOffset == 512 && gd.Api.Copies[1].Region.BufferOffset == 1536,
            "Nonzero-offset mip chain changed backing-buffer positions");
    }
}

// Regions, arrays, 3D and compressed mip chains retain the exact copy payloads.
foreach (var tuple in new[] {
    (Info(16, 16, levels: 3), 1, 3, false),
    (Info(8, 8, depth: 3, target: Target.Texture2DArray), 3, 1, false),
    (Info(8, 8, depth: 4, levels: 2, target: Target.Texture3D), 1, 2, false),
    (Info(16, 16, levels: 3, bpp: 8, format: Format.Bc1RgbaUnorm, block: 4), 1, 3, false),
}) {
    var gd = new VulkanRenderer();
    var texture = new TextureView(gd, tuple.Item1);
    // Move the ring offset away from zero before the tested upload.
    var first = new TextureView(gd, Info(1, 1)); first.Upload(Bytes(4, 1));
    int size = Enumerable.Range(0, tuple.Item3).Sum(tuple.Item1.GetMipSize);
    texture.Upload(Bytes(size, 50), layers: tuple.Item2, levels: tuple.Item3, singleSlice: tuple.Item4);
    Check(gd.Api.Copies.Count == 1 + tuple.Item3, "Mip chain lost a copy at a nonzero buffer offset");
    digests.Add(gd.Api.Complete());
}

// The optional 16MiB allocation can fail while a 1KiB temporary still fits.
// Both null return and allocation-exhaustion exceptions preserve that path;
// the large allocation is attempted only once for the session.
foreach (int failure in new[] { 0, 1, 2 }) {
    var gd = new VulkanRenderer();
    gd.BufferManager.ReturnNullForNextLarge = failure == 0;
    gd.BufferManager.ThrowForNextLarge = failure == 1 ? Result.ErrorOutOfHostMemory :
        failure == 2 ? Result.ErrorOutOfDeviceMemory : null;
    var texture = new TextureView(gd, Info(16, 16));
    texture.Upload(Bytes(1024, 600));
    texture.Upload(Bytes(1024, 601));
    Check(gd.BufferManager.LargeAllocationAttempts == (control ? 1 : 2), "Optional ring allocation retried after exhaustion");
    Check(gd.Api.Copies.Count == 2, "Allocation exhaustion lost a small upload");
    digests.Add(gd.Api.Complete());
    gd.BufferManager.Dispose();
    Check(gd.BufferManager.AllCreated.All(b => b.DisposeCount == 1), "Failed optional ring leaked or double-disposed a buffer");
}

if (!control) {
    foreach (Result failure in new[] { Result.ErrorDeviceLost, Result.ErrorUnknown }) {
        var gd = new VulkanRenderer();
        gd.BufferManager.ThrowForNextLarge = failure;
        var texture = new TextureView(gd, Info(16, 16));
        bool propagated = false;
        try { texture.Upload(Bytes(1024, 700)); }
        catch (VulkanException e) { propagated = e.ResultCode == failure; }
        Check(propagated, "Optional ring hid device loss or an unexpected Vulkan error");
        gd.BufferManager.Dispose();
    }
}
{
    var gd = new VulkanRenderer();
    var texture = new TextureView(gd, Info(16, 16));
    texture.Upload(Bytes(1024, 1));
    texture.Upload(Bytes(4 * 4 * 4, 2), region: new Rectangle<int>(4, 8, 4, 4));
    Check(gd.Api.Copies.Last().Region.ImageOffset.X == 4 && gd.Api.Copies.Last().Region.ImageOffset.Y == 8,
        "Subrectangle destination changed");
    digests.Add(gd.Api.Complete());
}

// D24 expansion writes converted bytes to an 8-aligned ring slice; NPOT
// texel-block sizes and uploads larger than the ring keep the original buffer.
{
    var gd = new VulkanRenderer();
    var small = new TextureView(gd, Info(1, 1)); small.Upload(Bytes(4, 2));
    var depth = new TextureView(gd, Info(8, 8, format: Format.D24UnormS8Uint), expanded: true);
    depth.Upload(Bytes(256, 3));
    if (!control) Check(gd.Api.Copies.Last().Region.BufferOffset % 8 == 0, "Converted depth upload misaligned");
    digests.Add(gd.Api.Complete());

    var rgb = new TextureView(gd, Info(4, 4, bpp: 3, format: Format.R8G8B8Unorm));
    int before = gd.BufferManager.NativeCreates;
    rgb.Upload(Bytes(48, 4));
    Check(gd.BufferManager.NativeCreates == before + 1, "NPOT block should use original path");
    digests.Add(gd.Api.Complete());

    var large = new TextureView(gd, Info(2048, 2049));
    before = gd.BufferManager.NativeCreates;
    large.Upload(Bytes(2048 * 2049 * 4, 5));
    Check(gd.BufferManager.NativeCreates == before + 1, "Oversize upload should use original path");
    digests.Add(gd.Api.Complete());
}

// A title that only needs oversize or NPOT uploads does not create the new
// 16MiB ring at all. Those paths preserve their single original temporary.
foreach (var tuple in new[] {
    (Info(4, 4, bpp: 3, format: Format.R8G8B8Unorm), 48),
    (Info(2048, 2049), 2048 * 2049 * 4),
}) {
    var gd = new VulkanRenderer();
    var texture = new TextureView(gd, tuple.Item1);
    int before = gd.BufferManager.NativeCreates;
    texture.Upload(Bytes(tuple.Item2, 333));
    Check(gd.BufferManager.NativeCreates == before + 1, "Fallback-only title allocated the texture ring");
    digests.Add(gd.Api.Complete());
}

Console.WriteLine(JsonSerializer.Serialize(new { mode = control ? "control" : "fixed", checks,
    ordinaryUploadsNativeBuffers, fullRingFallbackBuffers, payloadDigests = digests,
    nonzeroOffsetCopyCount,
    nativeTransferDouble = true, physicalDeviceTested = false }));
