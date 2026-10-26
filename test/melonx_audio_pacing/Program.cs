using System;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Threading;
using Ryujinx.Audio.Backends.Apple;
using Ryujinx.Audio.Backends.Apple.Native;
using Ryujinx.Audio.Common;
using Ryujinx.Audio.Integration;
using Ryujinx.Common;
using Ryujinx.Library;

namespace Ryujinx.Common {
    // The session reads this clock; tie it to the double's 48 kHz sample clock.
    static class PerformanceCounter { public static long ElapsedNanoseconds => AVFoundation.Now * 1_000_000_000L / 48000; }
}
namespace Ryujinx.Library { partial class Library {} }

unsafe class Program {
    static int checks;
    static void Check(bool value, string message) { if (!value) throw new Exception(message); checks++; }
    static long Ns(int frame) => frame * 1_000_000_000L / 48000;
    static AudioBuffer Buffer(int frames) {
        float[] data = Enumerable.Range(0, frames * 2).Select(i => (i % 97 + 1) / 100f).ToArray();
        return new AudioBuffer { Data = MemoryMarshal.AsBytes(data.AsSpan()).ToArray(), DataSize = (ulong)(data.Length * 4) };
    }
    static long[] Read() {
        delegate* unmanaged<long*, int, int> export = &Library.EmbeddedAudioPacingSnapshot;
        long[] values = new long[EmbeddedAudioPacing.Count];
        fixed (long* p = values) Check(export(p, values.Length) == 0, "Snapshot export failed");
        return values;
    }
    static void Main() {
        delegate* unmanaged<long*, int, int> export = &Library.EmbeddedAudioPacingSnapshot;
        long* scratch = stackalloc long[EmbeddedAudioPacing.Count + 1];
        Check(export(null, EmbeddedAudioPacing.Count) == 1, "Null buffer accepted");
        Check(export(scratch, EmbeddedAudioPacing.Count - 1) == 1 && export(scratch, EmbeddedAudioPacing.Count + 1) == 1, "Wrong count accepted");
        Check(Read().All(v => v == 0), "Counters did not start at zero");

        // DSP periods: on time and at the threshold are not late. A run of late
        // periods (a stall, then catch-up) is one episode, counted by its first
        // period; the maximum still sees every period.
        EmbeddedAudioPacing.DspPeriod(0);
        EmbeddedAudioPacing.DspPeriod(EmbeddedAudioPacing.LateThresholdNs);
        EmbeddedAudioPacing.DspPeriod(20_000_000);
        EmbeddedAudioPacing.DspPeriod(15_000_000);
        EmbeddedAudioPacing.DspPeriod(10_000_000);
        EmbeddedAudioPacing.DspPeriod(0);
        EmbeddedAudioPacing.DspPeriod(EmbeddedAudioPacing.LateThresholdNs + 1);
        EmbeddedAudioPacing.DspPeriod(0);
        EmbeddedAudioPacing.DspSkipped(0); EmbeddedAudioPacing.DspSkipped(-3); EmbeddedAudioPacing.DspSkipped(2);
        long[] v = Read();
        Check(v[0] == 8 && v[1] == 2 && v[2] == 22_000_001 && v[3] == 20_000_000 && v[4] == 2, "DSP counters wrong: " + string.Join(",", v));
        long[] again = Read();
        Check(again[3] == 0 && again[8] == 0, "Maxima were not reset by the read");
        Check(again[0] == 8 && again[1] == 2 && again[2] == 22_000_001 && again[4] == 2, "Totals changed on read");

        // Concurrent writers (more than the one DSP thread): no lost period, and
        // the maximum is the largest value.
        var threads = Enumerable.Range(0, 8).Select(t => new Thread(() => {
            for (int i = 0; i < 20000; i++) EmbeddedAudioPacing.DspPeriod(t * 1_000_000L + i);
        })).ToArray();
        foreach (var t in threads) t.Start();
        foreach (var t in threads) t.Join();
        v = Read();
        Check(v[0] == 8 + 160000 && v[3] == 7_000_000 + 19999, "Concurrent DSP counters wrong: " + string.Join(",", v));
        EmbeddedAudioPacing.DspPeriod(0);

        // Each session owns its interval: another session's buffer does not end it,
        // a completion with buffers still queued does not open one.
        long first = 0, second = 0;
        EmbeddedAudioPacing.HostCompleted(ref first, true, 1_000);
        EmbeddedAudioPacing.HostCompleted(ref second, false, 1_500);
        EmbeddedAudioPacing.HostQueued(ref second, 2_000);
        v = Read();
        Check(v[5] == 2 && v[6] == 0 && second == 0, "Another session ended the starvation");
        EmbeddedAudioPacing.HostQueued(ref first, 4_000);
        EmbeddedAudioPacing.HostQueued(ref first, 9_000);
        v = Read();
        Check(v[6] == 1 && v[7] == 3_000 && v[8] == 3_000 && first == 0, "Session interval measured wrongly: " + string.Join(",", v));
        long hostBase = v[5], starvedBase = v[7];

        // The real adapted Apple session against the timed AVFoundation double.
        var driver = new AppleHardwareDeviceDriver();
        var a = driver.OpenDeviceSession(IHardwareDeviceDriver.Direction.Output, null, SampleFormat.PcmFloat, 48000, 2);
        a.Start();
        a.QueueBuffer(Buffer(240)); a.QueueBuffer(Buffer(240));
        AVFoundation.AdvanceTo(960 + 480);
        v = Read();
        Check(v[5] == hostBase + 2 && v[6] == 1, "A drained queue was counted before the next buffer");
        AVFoundation.AdvanceTo(1920);
        Check(AVFoundation.EmptyFrames == 480, "Double did not play silence while starved");
        a.QueueBuffer(Buffer(240));
        v = Read();
        long gap = Ns(1920) - Ns(1439);
        Check(v[6] == 2 && v[7] == starvedBase + gap && v[8] == gap, "Starvation not measured from the last completion: " + string.Join(",", v));
        AVFoundation.AdvanceTo(1920 + 240);
        Check(Read()[5] == hostBase + 3, "Completed buffer not counted");
        // A guest stop is not a starvation, before or after it resumes.
        a.Stop();
        AVFoundation.AdvanceTo(3000);
        a.Start(); a.QueueBuffer(Buffer(240));
        v = Read();
        Check(v[6] == 2 && v[7] == starvedBase + gap && v[8] == 0, "A guest stop was counted as starvation");
        AVFoundation.AdvanceTo(3000 + 960 + 240);
        Check(Read()[5] == hostBase + 4, "Resumed buffer not counted");
        driver.Dispose(); AVFoundation.Reset();
        Console.WriteLine(JsonSerializer.Serialize(new { result = "passed", assertions = checks, starvedNs = gap,
            physicalDeviceTested = false, avFoundationDouble = true }));
    }
}
