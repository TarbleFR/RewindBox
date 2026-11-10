using System;
using System.Diagnostics;
using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.GAL.Multithreading;
using Ryujinx.Graphics.GAL.Multithreading.Resources;

// Each assembly compiles the whole original or adapted production classes.
// The paired runner references them through assembly aliases without rewriting
// production namespaces or including reflection inside the measured loop.
public static class PairedBridge
{
    public static (Func<int, (long Ticks, long Bytes)> Run, Action Dispose) Create(int kind, int length)
    {
        ThreadedRenderer renderer = new();
        ThreadedTextureArray textures = new(renderer) { Base = new TextureSink() };
        ThreadedImageArray images = new(renderer) { Base = new ImageSink() };
        ITexture[] values = new ITexture[length]; ISampler[] samplers = new ISampler[length];
        Array.Fill(values, new ThreadedTexture { Base = new HostTexture(7) });
        Array.Fill(samplers, new ThreadedSampler { Base = new HostSampler(8) });
        void Step()
        {
            if (kind == 0) textures.SetTextures(0, values);
            else if (kind == 1) textures.SetSamplers(0, samplers);
            else images.SetImages(0, values);
            renderer.DrainOne();
        }
        for (int i = 0; i < 2000; i++) Step();
        (long Ticks, long Bytes) Run(int iterations)
        {
            long before = GC.GetAllocatedBytesForCurrentThread();
            long start = Stopwatch.GetTimestamp();
            for (int i = 0; i < iterations; i++) Step();
            long elapsed = Stopwatch.GetTimestamp() - start;
            long bytes = GC.GetAllocatedBytesForCurrentThread() - before;
            return (elapsed, bytes);
        }
        return (Run, renderer.Dispose);
    }
}
