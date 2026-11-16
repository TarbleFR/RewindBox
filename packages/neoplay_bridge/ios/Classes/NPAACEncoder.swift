import AVFoundation

// AAC-LC encoder of the direct Chromecast route (AudioToolbox through
// AVAudioConverter): one block of 1024 stereo 16-bit samples at 48 kHz in, the
// packets the encoder has finished out. Used from NPDirectStream under its lock.
final class NPAACEncoder: NPAudioPacketEncoder {
    private let converter: AVAudioConverter
    private let source: AVAudioPCMBuffer
    private let output: AVAudioCompressedBuffer
    private(set) var failures = 0
    init?(bitrate: Int = 128_000) {
        guard let input = AVAudioFormat(commonFormat: .pcmFormatInt16, sampleRate: 48_000, channels: 2, interleaved: true),
              let compressed = AVAudioFormat(settings: [AVFormatIDKey: kAudioFormatMPEG4AAC, AVSampleRateKey: 48_000, AVNumberOfChannelsKey: 2]),
              let converter = AVAudioConverter(from: input, to: compressed),
              let source = AVAudioPCMBuffer(pcmFormat: input, frameCapacity: AVAudioFrameCount(NPDirectStream.blockFrames)) else { return nil }
        converter.bitRate = bitrate
        self.converter = converter; self.source = source
        output = AVAudioCompressedBuffer(format: compressed, packetCapacity: 8, maximumPacketSize: converter.maximumOutputPacketSize)
    }
    func encode(block: Data) -> [Data] {
        let bytes = NPDirectStream.blockFrames * 4
        guard block.count == bytes, let samples = source.int16ChannelData?.pointee else { return [] }
        block.withUnsafeBytes { raw in if let base = raw.baseAddress { memcpy(samples, base, bytes) } }
        source.frameLength = AVAudioFrameCount(NPDirectStream.blockFrames)
        output.packetCount = 0; output.byteLength = 0
        var consumed = false
        var error: NSError?
        let input = source
        let status = converter.convert(to: output, error: &error) { _, outStatus in
            if consumed { outStatus.pointee = .noDataNow; return nil }
            consumed = true; outStatus.pointee = .haveData; return input
        }
        guard status != .error else { failures += 1; return [] }
        let count = Int(output.packetCount)
        guard count > 0 else { return [] } // the encoder keeps its first samples: nothing is ready yet
        guard let descriptions = output.packetDescriptions else { return [Data(bytes: output.data, count: Int(output.byteLength))] }
        return (0..<count).map { Data(bytes: output.data.advanced(by: Int(descriptions[$0].mStartOffset)), count: Int(descriptions[$0].mDataByteSize)) }
    }
}
