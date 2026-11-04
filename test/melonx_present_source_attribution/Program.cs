// Fixture of melonx_present_source_attribution_test.py: the real NotePresentSource and its fields, extracted from the
// adapted Ryujinx.Graphics.Gpu/Window.cs, run with doubles of the presented texture and its group. The group double
// records every call so the test can require that the diagnostic only reads (CheckDirty without consuming).
using Ryujinx.Graphics.GAL;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;

namespace Ryujinx.Common.Logging
{
    enum LogClass { Gpu }
    sealed class Sink { public readonly List<string> Lines = new(); public void Print(LogClass c, string m) => Lines.Add(m); }
    static class Logger { public static Sink Warning; }
}
namespace Ryujinx.Graphics.GAL
{
    enum Format { R8G8B8A8Unorm, B8G8R8A8Unorm }
}
namespace Image
{
    sealed class FormatInfo { public Format Format = Format.R8G8B8A8Unorm; }
    sealed class TextureInfo { public FormatInfo FormatInfo = new(); public int Width = 1920, Height = 1080; }
    readonly struct Span { public readonly ulong Address, Size; public Span(ulong a, ulong s) { Address = a; Size = s; } }
    sealed class Ranges { public List<Span> Spans = new(); public int Count => Spans.Count; public Span GetSubRange(int i) => Spans[i]; }
    sealed class Group
    {
        public bool Modified = true, Dirty; public readonly List<string> Calls = new();
        public bool AnyHandleModified() { Calls.Add("modified"); return Modified; }
        public bool CheckDirty(Texture texture, bool consume) { Calls.Add("dirty " + consume); return Dirty; }
    }
    sealed class Texture
    {
        public TextureInfo Info = new(); public float ScaleFactor = 1f; public Group Group = new(); public Ranges Range = new();
        public Texture(ulong address) { Range.Spans.Add(new Span(address, 0x7e9000)); }
    }
}
sealed class Window
{
//__EXTRACTED__
    public void Present(Image.Texture texture) => NotePresentSource(texture);
}
static class Program
{
    static void Main()
    {
        var sink = new Ryujinx.Common.Logging.Sink();
        Ryujinx.Common.Logging.Logger.Warning = sink;
        var window = new Window();
        var a = new Image.Texture(0x10000000); var b = new Image.Texture(0x20000000); var c = new Image.Texture(0x30000000);
        var all = new List<Image.Texture> { a, b, c };
        // 1-6: rotation A B C A B C, GPU-rendered.
        foreach (var t in new[] { a, b, c, a, b, c }) window.Present(t);
        // 7: a new texture object at A's address (re-created), loaded from guest memory (not modified, dirty).
        var a2 = new Image.Texture(0x10000000); a2.Group.Modified = false; a2.Group.Dirty = true; all.Add(a2);
        window.Present(a2);
        // 8: B again, now dirty and not modified (a guest write since its last load); 9: B repeated.
        b.Group.Modified = false; b.Group.Dirty = true;
        window.Present(b);
        window.Present(b);
        // 10: C not modified and not dirty (flushed earlier, host data still valid): counted as not modified only.
        c.Group.Modified = false;
        window.Present(c);
        // 11-300: rotation of a2 b c, modified; the summary is at 300.
        a2.Group.Modified = b.Group.Modified = true; a2.Group.Dirty = b.Group.Dirty = false; c.Group.Modified = true;
        for (int i = 10; i < 300; i++) window.Present(new[] { a2, b, c }[i % 3]);
        int linesAt300 = sink.Lines.Count;
        // 20 more addresses than the map holds, each from guest memory: 8 detail lines at most; the map is bounded.
        for (int i = 0; i < 20; i++) { var t = new Image.Texture(0x40000000UL + (ulong)i * 0x1000000); t.Group.Modified = false; t.Group.Dirty = true; all.Add(t); window.Present(t); }
        for (int i = 0; i < 64 * 300 + 600; i++) window.Present(a2);
        var map = (Dictionary<ulong, int>)typeof(Window).GetField("_presentedByAddress", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance).GetValue(window);
        var report = new Dictionary<string, object>
        {
            ["details"] = sink.Lines.Where(l => l.StartsWith("Present source #")).ToList(),
            ["summaries"] = sink.Lines.Count(l => l.StartsWith("Present sources: ")),
            ["firstSummary"] = sink.Lines.First(l => l.StartsWith("Present sources: ")),
            ["linesAt300"] = linesAt300,
            ["mapCount"] = map.Count,
            ["calls"] = all.SelectMany(t => t.Group.Calls).Distinct().OrderBy(s => s).ToList(),
        };
        Console.WriteLine(JsonSerializer.Serialize(report));
    }
}
