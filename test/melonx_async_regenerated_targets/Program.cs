// Fixture of melonx_async_regenerated_targets_test.py: the real VulkanRenderer.IsCriticalOffscreenTarget (and, in the
// candidate, its frame counter), FramebufferParams.HasIncompleteAttachments/HasAttachment (and IsRegeneratedEachFrame,
// NoteAsyncPass, ClearsWhole) and TextureStorage's completeness (and frame) members, extracted from the prepared files of
// each variant and compiled with doubles of the views, the clear rectangle and the render thread's order of calls:
// Present counts a frame; a clear begins the pass (NoteAsyncPass) and then clears (NoteAsyncFullClear when whole); a draw
// asks IsCriticalOffscreenTarget while its program compiles: true makes it wait for its pipeline, false skips it.
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;

struct Offset2D { public int X, Y; public Offset2D(int x, int y) { X = x; Y = y; } }
struct Extent2D { public uint Width, Height; public Extent2D(uint w, uint h) { Width = w; Height = h; } }
struct Rect2D { public Offset2D Offset; public Extent2D Extent; public Rect2D(Offset2D o, Extent2D e) { Offset = o; Extent = e; } }
struct ClearRect { public Rect2D Rect; public uint BaseArrayLayer, LayerCount; public ClearRect(Rect2D r, uint b, uint c) { Rect = r; BaseArrayLayer = b; LayerCount = c; } }

sealed class TextureStorage
{
    public bool Disposed;
    private volatile bool _hasCompleteRenderPass;
    public bool HasCompleteRenderPass => _hasCompleteRenderPass;
    public void MarkRenderPassComplete() { _hasCompleteRenderPass = true; }
//__STORAGE__
}
sealed class TextureView { public TextureStorage Storage = new(); }
sealed class FramebufferParams
{
    private readonly TextureView[] _colors;
    private readonly TextureView _depthStencil;
    public uint Width, Height, Layers = 1;
    public int AttachmentsCount => (_colors?.Length ?? 0) + (_depthStencil != null ? 1 : 0);
    public bool HasDepthStencil => _depthStencil != null;
    public int ColorAttachmentsCount => AttachmentsCount - (HasDepthStencil ? 1 : 0);
    public FramebufferParams(TextureView[] colors, TextureView depth, uint width, uint height) { _colors = colors; _depthStencil = depth; Width = width; Height = height; }
    public TextureView GetColorView(int index) => _colors[index];
    public TextureView GetDepthStencilView() => _depthStencil;
    public void MarkAttachmentsComplete()
    {
        foreach (var c in _colors ?? Array.Empty<TextureView>()) c.Storage?.MarkRenderPassComplete();
        _depthStencil?.Storage?.MarkRenderPassComplete();
    }
//__FRAMEBUFFER__
}
sealed class VulkanRenderer
{
    private readonly HashSet<TextureStorage> _presentationStorages = new();
    public void Present(TextureView view) { _presentationStorages.Add(view.Storage); Frame(); }
    // The candidate's Window.Present counts a frame; the control has no counter.
    private void Frame() { var f = GetType().GetField("AsyncFrame", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance); if (f != null) f.SetValue(this, (ulong)f.GetValue(this) + 1); }
    public ulong CurrentFrame => (ulong)(GetType().GetField("AsyncFrame", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance)?.GetValue(this) ?? 0UL);
//__RENDERER__
}

static class Program
{
    static bool candidate;

    // The render thread's calls, as PipelineBase makes them in each variant.
    static void Pass(VulkanRenderer gd, FramebufferParams fb)
    {
        if (candidate) typeof(FramebufferParams).GetMethod("NoteAsyncPass").Invoke(fb, new object[] { gd.CurrentFrame });
    }
    static void ClearDepth(VulkanRenderer gd, FramebufferParams fb, int x = 0, uint width = 0, uint layers = 1)
    {
        Pass(gd, fb);
        if (!candidate) return;
        var rect = new ClearRect(new Rect2D(new Offset2D(x, 0), new Extent2D(width == 0 ? fb.Width : width, fb.Height)), 0, layers);
        if ((bool)typeof(FramebufferParams).GetMethod("ClearsWhole").Invoke(fb, new object[] { rect }))
            typeof(TextureStorage).GetMethod("NoteAsyncFullClear").Invoke(fb.GetDepthStencilView().Storage, new object[] { gd.CurrentFrame });
    }
    static void ClearColor(VulkanRenderer gd, FramebufferParams fb, int index)
    {
        Pass(gd, fb);
        if (!candidate) return;
        var rect = new ClearRect(new Rect2D(new Offset2D(0, 0), new Extent2D(0xffff, 0xffff)), 0, 1);
        if ((bool)typeof(FramebufferParams).GetMethod("ClearsWhole").Invoke(fb, new object[] { rect }))
            typeof(TextureStorage).GetMethod("NoteAsyncFullClear").Invoke(fb.GetColorView(index).Storage, new object[] { gd.CurrentFrame });
    }
    // A draw of a compiling program: skipped unless the target is critical; a pass with no skipped draw marks it complete.
    static bool Draw(VulkanRenderer gd, FramebufferParams fb, bool compiling = true)
    {
        bool critical = gd.IsCriticalOffscreenTarget(fb);
        bool skipped = compiling && !critical;
        Pass(gd, fb);
        if (!skipped) fb.MarkAttachmentsComplete();
        return skipped;
    }

    static TextureView[] Views(int n) => Enumerable.Range(0, n).Select(_ => new TextureView()).ToArray();

    static void Main(string[] args)
    {
        candidate = args[0] == "candidate";
        var report = new Dictionary<string, object> { ["variant"] = args[0] };
        var gd = new VulkanRenderer();
        var swap = new TextureView();
        var onScreen = new FramebufferParams(new[] { swap }, null, 1280, 720);
        // A G-buffer: four colour targets and the scene depth cleared whole each frame.
        var gbuffer = new FramebufferParams(Views(4), new TextureView(), 1280, 720);
        // A target drawn once (a capture) with its own depth cleared whole once.
        var capture = new FramebufferParams(Views(1), new TextureView(), 256, 256);
        // An atlas drawn every frame, its tiles cleared by scissor only (never whole).
        var atlas = new FramebufferParams(Views(1), new TextureView(), 2048, 2048);
        // A post-process target fully drawn every frame without a clear.
        var post = new FramebufferParams(Views(1), null, 1280, 720);
        // A colour target cleared whole each frame (no depth).
        var cleared = new FramebufferParams(Views(1), null, 640, 360);
        // A layered depth target cleared on layer 0 only.
        var layered = new FramebufferParams(Views(1), new TextureView(), 512, 512) { Layers = 4 };

        var skips = new Dictionary<string, List<bool>> { ["onScreen"] = new(), ["gbuffer"] = new(), ["capture"] = new(), ["atlas"] = new(),
                                                         ["post"] = new(), ["cleared"] = new(), ["layered"] = new(), ["gbufferAfterGap"] = new() };
        for (int frame = 1; frame <= 8; frame++)
        {
            // Frame 1 completes the targets the game draws each frame; later frames draw with a compiling program.
            bool compiling = frame > 1;
            ClearDepth(gd, gbuffer);
            skips["gbuffer"].Add(Draw(gd, gbuffer, compiling));
            if (frame == 1 || frame == 5) { ClearDepth(gd, capture); skips["capture"].Add(Draw(gd, capture, frame == 5)); }
            ClearDepth(gd, atlas, x: 256, width: 256);
            skips["atlas"].Add(Draw(gd, atlas, compiling));
            skips["post"].Add(Draw(gd, post, compiling));
            ClearColor(gd, cleared, 0);
            skips["cleared"].Add(Draw(gd, cleared, compiling));
            ClearDepth(gd, layered, layers: 1);
            skips["layered"].Add(Draw(gd, layered, compiling));
            skips["onScreen"].Add(Draw(gd, onScreen, compiling));
            gd.Present(swap);
        }
        // A frame without the G-buffer, then it comes back: its first frame back waits, the next ones skip again.
        gd.Present(swap);
        for (int frame = 0; frame < 3; frame++)
        {
            ClearDepth(gd, gbuffer);
            skips["gbufferAfterGap"].Add(Draw(gd, gbuffer, true));
            gd.Present(swap);
        }
        report["skips"] = skips;
        // Before any presentation every target is non-critical (the existing rule), in both.
        var fresh = new VulkanRenderer();
        report["beforePresentation"] = fresh.IsCriticalOffscreenTarget(new FramebufferParams(Views(1), null, 64, 64));
        Console.WriteLine(JsonSerializer.Serialize(report));
    }
}
