"""iOS-only MeloNX SDL3 audio callback fix.

The pinned SDL3HardwareDeviceSession cleared the entire requested callback
buffer, mixed only bytes present in its producer ring, but enqueued the
entire request, including synthetic zeros. With a busy guest thread this
produces a periodic chopper effect. SDL3 allows a shorter put callback.
"""
from adapt_session import once


def apply(source):
    target = source / "src/Ryujinx.Audio.Backends.SDL3/SDL3HardwareDeviceSession.cs"
    original = target.read_text(encoding="utf-8-sig")
    guard = "            int byteCount = frameCount * _bytesPerFrame;"
    push = "                SDL_PutAudioStreamData(streamDevice, (nint)pStreamDst, additionalAmount);"
    if original.count(guard) != 1 or original.count(push) != 1:
        raise AssertionError("Pinned MeloNX SDL3 audio callback differs; refuse unverified patch")
    if original.count("            streamSpan.Clear();") != 1:
        raise AssertionError("Audio underrun path differs; refuse unverified patch")
    queue = """                _ringBuffer.Write(buffer.Data, 0, buffer.Data.Length);

                _queuedBuffers.Enqueue(driverBuffer);"""
    if original.count(queue) != 1:
        raise AssertionError("Audio producer publication differs; refuse unverified patch")
    once(target, guard,
         """            int byteCount = frameCount * _bytesPerFrame;

            // Never enqueue fabricated silence for frames the emulated
            // Switch has not produced yet. SDL3 permits a short callback.
            // The next callback can consume actual producer data on arrival.
            if (byteCount == 0)
            {
                _updateRequiredEvent.Set();
                return;
            }""")
    once(target, push,
         """                // Only send the audio samples we actually consumed from
                // the producer ring; never pad the SDL queue to additionalAmount.
                SDL_PutAudioStreamData(streamDevice, (nint)pStreamDst, byteCount);""")
    once(target, queue, """                // Publish accounting before PCM becomes visible to the SDL
                // callback. Otherwise it can consume those samples without
                // retiring their buffer, starving the guest audio producer.
                _queuedBuffers.Enqueue(driverBuffer);
                _ringBuffer.Write(buffer.Data, 0, buffer.Data.Length);""")
    return [target]
