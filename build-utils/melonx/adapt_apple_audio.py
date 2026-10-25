"""Correct the AVAudioEngine backend actually selected by MeloNX on iOS."""
from adapt_session import once


def apply(source):
    session = source / 'src/Ryujinx.Audio.Backends.Apple/AppleHardwareDeviceSession.cs'
    native = session.parent / 'Native/AVFoundation.cs'
    library = source / 'src/Ryujinx.Library/Library.cs'
    assert 'new AppleHardwareDeviceDriver(),' in library.read_text(encoding='utf-8-sig')
    once(session, '        private bool _started;', '        private bool _started;\n        private bool _playing;')
    once(session, '        public override void QueueBuffer(AudioBuffer buffer)\n        {',
         '''        // Keep scheduling and teardown mutually exclusive. Completion
        // callbacks remain lock-free: stopping a node may invoke them.
        public override void QueueBuffer(AudioBuffer buffer)
        {
            lock (_lock) QueueBufferLocked(buffer);
        }

        private void QueueBufferLocked(AudioBuffer buffer)
        {''')
    once(session, '            AVFoundation.ScheduleBuffer(_playerNode, pcmBuffer, _completionBlock);',
         '''            AVFoundation.ScheduleBuffer(_playerNode, pcmBuffer, _completionBlock);
            StartBufferedPlayback();''')
    once(session, '''                AVFoundation.Play(_playerNode);
                _started = true;''', '''                _started = true;
                StartBufferedPlayback();''')
    once(session, '''                AVFoundation.Pause(_playerNode);
                _started = false;''', '''                AVFoundation.Pause(_playerNode);
                _playing = false;
                _started = false;''')
    once(session, '        public override ulong GetPlayedSampleCount()', '''        private void StartBufferedPlayback()
        {
            if (!_started || _disposed || _queuedBuffers.IsEmpty) return;
            // A route/session reconfiguration can stop AVAudioEngine without
            // changing the guest's started flag. Resume the actual engine.
            if (!AVFoundation.IsRunning(_engine))
            {
                if (!AVFoundation.Start(_engine, out _))
                    throw new InvalidOperationException("Apple audio engine restart failed.");
                _playing = false;
            }
            if (_playing) return;
            // The DSP supplies 5 ms blocks. Starting an empty player, then
            // submitting each block just in time, leaves no scheduling margin.
            // Schedule from the first real PCM block with 20 ms of lead. This
            // also plays a single short buffer; no minimum buffer count, PCM
            // duplication, silence padding or rate change is required.
            AVFoundation.PlayBuffered(_playerNode, 0.020);
            _playing = true;
        }

        public override ulong GetPlayedSampleCount()''')
    once(session, '                UpdateEffectiveVolume();', '''                UpdateEffectiveVolume();
                Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("audio", "backendReady",
                    detail: $"Apple AVAudioEngine; rate: {RequestedSampleRate}; channels: {RequestedChannelCount}; startup lead ms: 20");''')
    once(native, '        internal static void Play(nint playerNode)', '''        [LibraryImport(LibSystem)]
        private static partial ulong mach_absolute_time();

        [LibraryImport(ObjCRuntime, EntryPoint = "objc_msgSend")]
        private static partial ulong ulong_objc_msgSend_double(nint receiver, nint selector, double seconds);

        [LibraryImport(ObjCRuntime, EntryPoint = "objc_msgSend")]
        private static partial nint nint_objc_msgSend_ulong(nint receiver, nint selector, ulong value);

        [LibraryImport(ObjCRuntime, EntryPoint = "objc_msgSend")]
        [return: MarshalAs(UnmanagedType.I1)]
        private static partial bool bool_objc_msgSend(nint receiver, nint selector);

        internal static bool IsRunning(nint engine) => bool_objc_msgSend(engine, GetSelector("isRunning"));

        internal static void PlayBuffered(nint playerNode, double leadSeconds)
        {
            nint timeClass = GetClass("AVAudioTime");
            ulong lead = ulong_objc_msgSend_double(timeClass, GetSelector("hostTimeForSeconds:"), leadSeconds);
            nint time = nint_objc_msgSend_ulong(timeClass, GetSelector("timeWithHostTime:"), checked(mach_absolute_time() + lead));
            void_objc_msgSend_nint(playerNode, GetSelector("playAtTime:"), time);
        }

        internal static void Play(nint playerNode)''')
    return [session, native]
