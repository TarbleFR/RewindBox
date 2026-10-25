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
}
