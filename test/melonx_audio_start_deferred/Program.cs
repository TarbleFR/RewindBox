// Scenarios for melonx_audio_start_deferred_test.py: the variant's real final AppleHardwareDeviceSession.cs (control:
// Core 677 postimage; candidate: with adapt_audio_start_deferred) against the timed AVFoundation double of
// test/melonx_apple_audio. A session is created while iOS refuses to start the engine, then iOS allows it again.
using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text.Json;
using Ryujinx.Audio.Backends.Apple;
using Ryujinx.Audio.Backends.Apple.Native;
using Ryujinx.Audio.Common;
using Ryujinx.Audio.Integration;

namespace Ryujinx.Common {
    static class PerformanceCounter { public static long ElapsedNanoseconds => AVFoundation.Now * 1_000_000_000L / 48000; }
}

class Program {
    static AudioBuffer Buffer(int first, int frames) {
        float[] data = Enumerable.Range(first * 2, frames * 2).Select(i => (i % 97 + 1) / 100f).ToArray();
        return new AudioBuffer { Data = MemoryMarshal.AsBytes(data.AsSpan()).ToArray(), DataSize = (ulong)(data.Length * 4) };
    }

    static int Clear() {
        int left = 0;
        foreach (string name in new[] { "pcm", "blocks", "queue" }) {
            object value = typeof(AVFoundation).GetField(name, System.Reflection.BindingFlags.Static | System.Reflection.BindingFlags.NonPublic).GetValue(null);
            left += (int)value.GetType().GetProperty("Count").GetValue(value);
            value.GetType().GetMethod("Clear").Invoke(value, null);
        }
        return left;
    }

    static Dictionary<string, object> Run(bool refusedAtCreation) {
        var report = new Dictionary<string, object>();
        AVFoundation.CanStart = !refusedAtCreation;
        var driver = new AppleHardwareDeviceDriver();
        IHardwareDeviceSession session;
        try {
            session = driver.OpenDeviceSession(IHardwareDeviceDriver.Direction.Output, null, SampleFormat.PcmFloat, 48000, 2);
        } catch (Exception exception) {
            report["created"] = false;
            report["exception"] = exception.GetType().Name + ": " + exception.Message;
            driver.Dispose();
            // The throwing constructor never released its completion block: recorded, then cleared for the next case.
            report["nativeObjectsLeftByThrow"] = Clear();
            AVFoundation.Reset();
            return report;
        }
        report["created"] = true;
        session.Start();
        session.QueueBuffer(Buffer(0, 480));
        AVFoundation.AdvanceTo(2000);
        report["playedWhileRefused"] = (long)session.GetPlayedSampleCount();
        report["runningWhileRefused"] = AVFoundation.Running;
        // iOS allows the engine again: consumer polling alone must start it (no further producer buffer needed).
        AVFoundation.CanStart = true;
        session.GetPlayedSampleCount();
        report["runningAfterPoll"] = AVFoundation.Running;
        session.QueueBuffer(Buffer(480, 480));
        AVFoundation.AdvanceTo(AVFoundation.Now + 3000);
        report["played"] = (long)session.GetPlayedSampleCount();
        var expected = MemoryMarshal.Cast<byte, float>(Buffer(0, 960).Data).ToArray();
        report["pcmIntact"] = AVFoundation.Rendered.SequenceEqual(expected);
        report["starts"] = AVFoundation.Starts;
        driver.Dispose(); AVFoundation.Reset();
        return report;
    }

    static void Main(string[] args) {
        var report = new Dictionary<string, object> { ["variant"] = args[0], ["refusedAtCreation"] = Run(true), ["startedAtCreation"] = Run(false) };
        Console.WriteLine(JsonSerializer.Serialize(report));
    }
}
