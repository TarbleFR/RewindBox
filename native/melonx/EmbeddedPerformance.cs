using System;
using System.Runtime.InteropServices;

namespace Ryujinx.Library;

partial class Library
{
    // Polled by the RAM overlay on UIKit's main thread, twice a second. Reads
    // the engine's own PerformanceStatistics: the game FPS, frame time and FIFO
    // load that standalone MeloNX pushes through its "push_statistics"
    // callback, which this host never registers. The session gate rejects
    // stale or stopped generations, exactly as the live aspect ratio does.
    // values: [0] game FPS, [1] game frame time in ms, [2] FIFO percent.
    [UnmanagedCallersOnly(EntryPoint = "neostation_melonx_performance_snapshot")]
    public static unsafe int EmbeddedPerformanceSnapshot(long generation, double* values, int count)
    {
        if (values == null || count != 3) return 1;
        try
        {
            // Before the first measured frame the frame time is 1000 / 0.
            static double Finite(double value) => double.IsFinite(value) && value > 0 ? value : 0;
            double fps = 0, frameTime = 0, fifo = 0;
            bool available = false;
            bool current = EmbeddedSessions.WithInputs(generation, () =>
            {
                var statistics = _window?.Device?.Statistics;
                if (statistics == null) return;
                fps = Finite(statistics.GetGameFrameRate());
                frameTime = Finite(statistics.GetGameFrameTime());
                fifo = Finite(statistics.GetFifoPercent());
                available = true;
            });
            if (!current || !available) return 2;
            values[0] = fps; values[1] = frameTime; values[2] = fifo;
            return 0;
        }
        catch { return 3; }
    }

    // The standalone app pushes UIScreen.maximumFramesPerSecond through
    // set_unbounded_present_target_fps on layout. It only matters when the
    // guest presents with swap interval 0 (VSync Unbounded, or a game picking
    // 0): the engine default otherwise drops every frame above 60 on a timer.
    // Gated like the live aspect ratio; returns 2 for a stale generation.
    [UnmanagedCallersOnly(EntryPoint = "neostation_melonx_set_present_target_fps")]
    public static int EmbeddedSetPresentTargetFps(long generation, int fps)
    {
        if (fps < 1 || fps > 1000) return 1;
        try
        {
            bool applied = false;
            bool current = EmbeddedSessions.WithInputs(generation, () =>
            {
                var context = _emulationContext;
                if (context == null) return;
                context.SetUnboundedPresentTargetFps(fps);
                applied = true;
            });
            return current && applied ? 0 : 2;
        }
        catch { return 3; }
    }
}
