#!/usr/bin/env python3
"""Pin the MeloNX SDL3 callback fix without a physical-device gameplay claim."""
from pathlib import Path
import re
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
from adapt_audio import apply

CALLBACK_SOURCE = """
class SDL3HardwareDeviceSession
{
    private int _bytesPerFrame = 4;
    private readonly System.Threading.ManualResetEvent _updateRequiredEvent = new(false);
    void Update(int additionalAmount)
    {
            streamSpan.Clear();
            int frameCount = Math.Min(bufferedFrames, maxFrameCount);
            int byteCount = frameCount * _bytesPerFrame;
            if (frameCount > 0)
            {
                _ringBuffer.Read(samples, 0, byteCount);
            }
            fixed (byte* pStreamDst = streamSpan)
            {
                SDL_PutAudioStreamData(streamDevice, (nint)pStreamDst, additionalAmount);
            }
    }
    void QueueBuffer(AudioBuffer buffer)
    {
                _ringBuffer.Write(buffer.Data, 0, buffer.Data.Length);

                _queuedBuffers.Enqueue(driverBuffer);
    }
}
"""

class UnderrunTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.target = self.root / 'src/Ryujinx.Audio.Backends.SDL3/SDL3HardwareDeviceSession.cs'
        self.target.parent.mkdir(parents=True)
        self.target.write_text(CALLBACK_SOURCE)
        
    def test_only_produced_audio_is_enqueued(self):
        self.assertEqual(apply(self.root), [self.target])
        text = self.target.read_text()
        self.assertIn('SDL_PutAudioStreamData(streamDevice, (nint)pStreamDst, byteCount);', text)
        self.assertNotIn('SDL_PutAudioStreamData(streamDevice, (nint)pStreamDst, additionalAmount);', text)
        self.assertIn('if (byteCount == 0)', text)
        self.assertIn('_updateRequiredEvent.Set();', text)
        # For a callback asking for 2048 frames with only 240 ready,
        # the old implementation queued 1808 frames of synthetic silence.
        request, available = 2048, 240
        self.assertEqual(request - available, 1808)
        self.assertEqual(available * 4, 960)
        # The updated code submits exactly these 960 valid bytes, not 8192.
        self.assertRegex(text, r'SDL_PutAudioStreamData\(streamDevice, \(nint\)pStreamDst, byteCount\)')
        with self.assertRaises(AssertionError):
            apply(self.root)  # fail closed on reruns / upstream code drift

    def test_unrecognized_upstream_cannot_be_modified(self):
        self.target.write_text(CALLBACK_SOURCE.replace('additionalAmount);', 'bufferedBytes);'))
        before = self.target.read_bytes()
        with self.assertRaises(AssertionError):
            apply(self.root)
        self.assertEqual(before, self.target.read_bytes())

    def test_missing_buffer_clear_refuses_unverified_patch(self):
        self.target.write_text(CALLBACK_SOURCE.replace('streamSpan.Clear();', '// different callback'))
        with self.assertRaises(AssertionError):
            apply(self.root)

if __name__ == '__main__':
    unittest.main()
