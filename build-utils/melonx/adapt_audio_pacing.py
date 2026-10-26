"""Count audio pacing events for the host's per-second performance journal.

Measurement only; behaviour is unchanged. AudioProcessor.Wait paces the DSP
in 5 ms periods by wall clock: each period records how late it ended (runs
of late periods count as one episode) and how many periods it skipped. The Apple backend records when its queue runs dry
after a completed buffer and how long until the next buffer arrives (heard
as silence). Each session keeps its own interval and a guest stop ends it
uncounted; a completion that races a new buffer or a stop is re-checked.
Horizon.TogglePauseEmulation marks each resume from a host pause: what
waited through the pause is not counted.
Counters: native/melonx/EmbeddedAudioPacing.cs.
"""
from adapt_session import once


def apply(source):
    processor = source / 'src/Ryujinx.Audio/Renderer/Dsp/AudioProcessor.cs'
    once(processor, '''                // Skip a few frames so that we're not too far behind. (the target number of frames)
                _lastTime += increment * (bufferedFrames - TargetBufferedFrames);''', '''                // Skip a few frames so that we're not too far behind. (the target number of frames)
                EmbeddedAudioPacing.DspSkipped(bufferedFrames - TargetBufferedFrames, _lastTime + increment);
                _lastTime += increment * (bufferedFrames - TargetBufferedFrames);''')
    once(processor, '''            while (timeNow < _lastTime + increment)
            {
                _event.WaitOne(1);

                timeNow = PerformanceCounter.ElapsedNanoseconds;
            }

            _lastTime += increment;''', '''            long due = _lastTime + increment;

            while (timeNow < _lastTime + increment)
            {
                _event.WaitOne(1);

                timeNow = PerformanceCounter.ElapsedNanoseconds;
            }

            // How late this period ended (a late wake-up or a busy producer).
            EmbeddedAudioPacing.DspPeriod(due, timeNow);

            _lastTime += increment;''')
    session = source / 'src/Ryujinx.Audio.Backends.Apple/AppleHardwareDeviceSession.cs'
    once(session, '''        private ulong _playedSampleCount;
''', '''        private ulong _playedSampleCount;
        private long _pacingStarvedSince;
''')
    once(session, '''                Interlocked.Add(ref _playedSampleCount, remainingSamples);
''', '''                Interlocked.Add(ref _playedSampleCount, remainingSamples);
                Ryujinx.Common.EmbeddedAudioPacing.HostCompleted(ref _pacingStarvedSince, _queuedBuffers.IsEmpty && _started, Ryujinx.Common.PerformanceCounter.ElapsedNanoseconds);
                // A buffer queued, or a guest stop, while that ran is not a starvation.
                if (!_queuedBuffers.IsEmpty || !_started) Ryujinx.Common.EmbeddedAudioPacing.HostIdle(ref _pacingStarvedSince);
''')
    once(session, '''            _queuedBuffers.Enqueue(driverBuffer);
            AVFoundation.ScheduleBuffer(_playerNode, pcmBuffer, _completionBlock);''', '''            _queuedBuffers.Enqueue(driverBuffer);
            Ryujinx.Common.EmbeddedAudioPacing.HostQueued(ref _pacingStarvedSince, Ryujinx.Common.PerformanceCounter.ElapsedNanoseconds);
            AVFoundation.ScheduleBuffer(_playerNode, pcmBuffer, _completionBlock);''')
    once(session, '''                AVFoundation.Pause(_playerNode);
                _playing = false;
                _started = false;''', '''                AVFoundation.Pause(_playerNode);
                _playing = false;
                _started = false;
                Ryujinx.Common.EmbeddedAudioPacing.HostIdle(ref _pacingStarvedSince);''')
    horizon = source / 'src/Ryujinx.HLE/HOS/Horizon.cs'
    once(horizon, '''                    Device.AudioDeviceDriver.GetPauseEvent().Set();''', '''                    Ryujinx.Common.EmbeddedAudioPacing.Resumed(Ryujinx.Common.PerformanceCounter.ElapsedNanoseconds);
                    Device.AudioDeviceDriver.GetPauseEvent().Set();''')
    return [processor, session, horizon]
