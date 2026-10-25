using System;
using System.Linq;
using System.IO;
using System.Runtime.InteropServices;
using System.Text.Json;
using Ryujinx.Audio.Backends.Apple;
using Ryujinx.Audio.Backends.Apple.Native;
using Ryujinx.Audio.Common;
using Ryujinx.Audio.Integration;
using Ryujinx.Library;

class Program {
    static int checks;
    static void Check(bool value, string message) { if (!value) throw new Exception(message); checks++; }
    static AudioBuffer Buffer(int first, int frames, int channels = 2) {
        float[] data = Enumerable.Range(first * channels, frames * channels).Select(i => (i % 97 + 1) / 100f).ToArray();
        return new AudioBuffer { Data = MemoryMarshal.AsBytes(data.AsSpan()).ToArray(), DataSize = (ulong)(data.Length * 4) };
    }
    static void Main(string[] args) {
        bool old = args.Single() == "control";
        var driver = new AppleHardwareDeviceDriver();
        var session = driver.OpenDeviceSession(IHardwareDeviceDriver.Direction.Output, null, SampleFormat.PcmFloat, 48000, 2);
        session.Start();
        if (!old) Check(AVFoundation.Plays == 0, "An empty player was started");
        // Six 5 ms buffers; one 15 ms scheduling delay. The real session is
        // responsible for scheduling/deinterleaving and completion accounting.
        int[] arrivals = {0, 240, 480, 1440, 1680, 1920};
        for (int i = 0; i < arrivals.Length; i++) {
            AVFoundation.AdvanceTo(arrivals[i]); session.QueueBuffer(Buffer(i * 240, 240));
        }
        AVFoundation.AdvanceTo((old ? 0 : 960) + 1440);
        int missing = AVFoundation.EmptyFrames;
        if (old) Check(missing > 0, "Old Apple backend did not reproduce underflow");
        else {
            Check(missing == 0, "Scheduled producer jitter caused underflow");
            Check(session.GetPlayedSampleCount() == 1440, "Incorrect completed sample count");
            var expected = MemoryMarshal.Cast<byte, float>(Buffer(0, 1440).Data).ToArray();
            Check(AVFoundation.Rendered.SequenceEqual(expected), "PCM was lost, duplicated or reordered");
            Check(AVFoundation.Plays == 1, "Playback repeatedly restarted");
        }
        driver.Dispose(); AVFoundation.Reset();
        if (!old) {
            driver = new AppleHardwareDeviceDriver();
            session = driver.OpenDeviceSession(IHardwareDeviceDriver.Direction.Output, null, SampleFormat.PcmFloat, 48000, 1);
            session.Start(); session.QueueBuffer(Buffer(0, 100, 1));
            Check(AVFoundation.StartAt == 960, "Startup lead differs from 20 ms");
            AVFoundation.AdvanceTo(1060);
            Check(session.GetPlayedSampleCount() == 100, "Single short buffer was left waiting for more data");
            session.Stop(); session.QueueBuffer(Buffer(100, 100, 1));
            Check(!AVFoundation.Playing, "Paused stream restarted while scheduling");
            session.Start(); AVFoundation.AdvanceTo(2120);
            Check(session.GetPlayedSampleCount() == 200, "Pause/resume lost PCM");
            AVFoundation.Running = false;
            session.QueueBuffer(Buffer(200, 100, 1));
            Check(AVFoundation.Running && AVFoundation.Starts == 2, "Stopped audio engine was never restarted");
            AVFoundation.AdvanceTo(3180);
            Check(session.GetPlayedSampleCount() == 300, "Restarted engine did not complete audio");
            driver.Volume = 0.5f; session.SetVolume(0.25f);
            Check(AVFoundation.Volume == 0.125f, "Personal volume was changed");
            driver.Dispose(); session.QueueBuffer(Buffer(0, 240)); session.Start();
            Check(!AVFoundation.Playing, "Closed session restarted");
            AVFoundation.Reset();
            ulong target = 0x0100123456780000;
            Check(EmbeddedAddonSelection.RequestedTitle(null, false) == null, "Global import requires a selected game");
            Check(EmbeddedAddonSelection.SelectUpdate(new[] {target + 0x800}, null) == target, "Patch did not select its base");
            Check(EmbeddedAddonSelection.SelectUpdate(new[] {target + 0x800, target + 0x801}, null) == target, "Same-base program variants are ambiguous");
            Check(EmbeddedAddonSelection.SelectUpdate(new[] {target + 0x800, target + 0x2800}, target) == target, "Selected game was ignored");
            foreach (var test in new (ulong[] Titles, ulong? Requested, string Code)[] {
                (Array.Empty<ulong>(), null, "invalidUpdate"),
                (new[] {target + 0x2800}, target, "addonWrongGame"),
                (new[] {target + 0x800, target + 0x2800}, null, "ambiguousUpdate")}) {
                try { EmbeddedAddonSelection.SelectUpdate(test.Titles, test.Requested); throw new Exception("Invalid package accepted"); }
                catch (InvalidDataException e) { Check(EmbeddedAddonSelection.ErrorCode(e) == test.Code, "Incorrect package refusal"); }
            }
        }
        Console.WriteLine(JsonSerializer.Serialize(new { result = "passed", control = old, assertions = checks, underflowFrames = missing,
            physicalDeviceTested = false, avFoundationDouble = true }));
    }
}
