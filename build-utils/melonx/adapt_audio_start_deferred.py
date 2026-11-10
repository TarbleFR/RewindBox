"""An audio output whose AVAudioEngine iOS refuses to start no longer aborts the application.

IPA 674, private journals, not in the repository: Hogwarts Legacy (pid 23682) at about 3 min of play, during a run of
iOS memory warnings (5.3 GB footprint, 4-8 % of the device available). The game opened a new audio output;
AppleHardwareDeviceSession.SetupAudioEngine threw "AVAudioEngine failed to start" from OpenDeviceSession on a guest
service thread, and that unhandled exception terminated the application.

Change (AppleHardwareDeviceSession.cs, every title): when the engine does not start at creation, the session keeps its
prepared engine (player node attached and connected), records audio/startDeferred and marks the restart pending. The
existing deferred restart (StartBufferedPlayback, retried from GetPlayedSampleCount and from each queued buffer, as
after an audio interruption) starts it as soon as iOS allows it; the queued PCM is kept. A failure to create the
AVFoundation objects still throws, as before. Nothing changes when the engine starts.
Fail closed on drift: the file must be the Core 677 preparation's.
"""
import hashlib
from adapt_session import once

BASELINE = {
    'src/Ryujinx.Audio.Backends.Apple/AppleHardwareDeviceSession.cs':
        'b4f6a9c1f7c55dd7fc0a909cbf81d843409f28bd2b006cc7a6ae53c3434b084e',
}

START_OLD = '''                if (!AVFoundation.Start(_engine, out nint error))
                {
                    string errorMessage = error != nint.Zero ? $" Error object: 0x{error:x}." : string.Empty;

                    throw new InvalidOperationException($"AVAudioEngine failed to start.{errorMessage}");
                }
'''
START_NEW = '''                if (!AVFoundation.Start(_engine, out nint error))
                {
                    // RewindBox (adapt_audio_start_deferred): iOS can refuse to start an engine (memory pressure, an
                    // interruption). The prepared engine is kept and the deferred restart starts it from playback,
                    // instead of an unhandled exception that terminates the application.
                    string errorMessage = error != nint.Zero ? $" Error object: 0x{error:x}." : string.Empty;

                    _restartPending = true;
                    UpdateEffectiveVolume();
                    Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("audio", "startDeferred",
                        detail: $"AVAudioEngine did not start at session creation; retried from playback.{errorMessage}");

                    return;
                }
'''


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name

    once(paths['src/Ryujinx.Audio.Backends.Apple/AppleHardwareDeviceSession.cs'], START_OLD, START_NEW)
    return list(paths.values())
