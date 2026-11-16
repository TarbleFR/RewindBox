import Foundation

// ---- reviewer stubs: signatures as the real SDKs import into Swift (to the reviewer's knowledge) ----
typealias CFString = String
typealias CFTypeRef = AnyObject

// UIKit / AVFAudio bits used by the kept part of NPController
final class UIWindow { var isHidden = false }
enum UIApplication { static let didEnterBackgroundNotification = Notification.Name("bg") }
final class AVAudioSession { static let routeChangeNotification = Notification.Name("route") }

// Unchanged collaborators, interface only
struct NPAirPlayFacts { let externalMirroring: Bool; let airPlayAudio: Bool }
final class NPAirPlayMonitor {
    var changed: (() -> Void)?
    static func facts() -> NPAirPlayFacts { NPAirPlayFacts(externalMirroring: false, airPlayAudio: false) }
    var snapshot: [String: Any] { [:] }
    func start() {}
}
final class StubService { var hostName: String? { nil }; var port: Int { 0 } }
final class NPDiscovery {
    private(set) var services: [String: StubService] = [:]
    var changed: (() -> Void)?
    var failed: (() -> Void)?
    func start() {}
    func stop() {}
    var receivers: [[String: Any]] { [] }
}
final class NPWindowsTransport {
    var onReady: ((NPSize) -> Void)?
    var onDisplay: ((NPSize) -> Void)?
    var onError: ((NPError) -> Void)?
    var onPlayback: (() -> Void)?
    var onShed: ((Int, UInt8) -> Void)?
    var onKeyRequest: (() -> Void)?
    private(set) var framesSupported = false
    private(set) var receiverMax = NPPolicy.legacyCap
    init() {}
    func connect(host: String, port: Int, pin: String) {}
    func send(_ data: Data, initial: Bool) {}
    func sendPacket(_ packet: Data) {}
    func stop() {}
}

// CoreMedia / CoreVideo / CoreImage / ReplayKit bits used by NPCapture
final class CMSampleBuffer {}
final class CVPixelBuffer {}
struct CIImage { var extent: CGRect { .zero } }
func CMGetAttachment(_ target: CMSampleBuffer, key: CFString, attachmentModeOut: UnsafeMutablePointer<UInt32>?) -> CFTypeRef? { nil }
func CMSampleBufferGetImageBuffer(_ sample: CMSampleBuffer) -> CVPixelBuffer? { nil }
func CVPixelBufferGetPixelFormatType(_ pixel: CVPixelBuffer) -> UInt32 { 0 }
let RPVideoSampleOrientationKey: String = "RPVideoSampleOrientationKey"
enum RPSampleBufferType: Int { case video = 1, audioApp, audioMic }
final class RPPreviewViewController {}
protocol RPScreenRecorderDelegate: AnyObject {
    func screenRecorder(_ screenRecorder: RPScreenRecorder, didStopRecordingWith previewViewController: RPPreviewViewController?, error: Error?)
}
final class RPScreenRecorder {
    private static let instance = RPScreenRecorder()
    static func shared() -> RPScreenRecorder { instance }
    var isAvailable: Bool { true }
    var isRecording: Bool { false }
    var isMicrophoneEnabled = false
    weak var delegate: RPScreenRecorderDelegate?
    func startCapture(handler captureHandler: ((CMSampleBuffer, RPSampleBufferType, Error?) -> Void)?, completionHandler: ((Error?) -> Void)? = nil) {}
    func stopCapture(handler: ((Error?) -> Void)? = nil) {}
}

// Encoders: interface copied from NPFrameEncoder.swift / NPMuxer.swift as they stand after the change
final class NPPCMSession {
    init(origin: Int? = nil) {}
    var audioPackets: Int { 0 }
    var reanchors: Int { 0 }
    var beforeOrigin: Int { 0 }
    var beforeConfiguration: Int { 0 }
    var onPacket: ((Data) -> Void)?
    func forwardConfiguration(_ enqueue: () -> Bool) {}
    func append(_ sample: CMSampleBuffer) {}
    func cancel() {}
}
final class NPFrameEncoder {
    let source: NPSize
    let output: NPSize
    var passthrough: Int { 0 }
    var rendered: Int { 0 }
    var onPacket: ((Data) -> Void)?
    var onError: ((NPError) -> Void)?
    init(source: NPSize, display: NPSize, cap: NPSize, origin: Int? = nil, pcm: NPPCMSession? = nil) throws { self.source = source; output = source }
    func requestKeyFrame() {}
    func append(_ sample: CMSampleBuffer, video isVideo: Bool) {}
    func repeatIfStill(now: TimeInterval, interval: TimeInterval) {}
    func setBitrate(_ bitsPerSecond: Int) {}
    func cancel(flushVideo: Bool = true) {}
}
final class NPMuxer: NSObject {
    let source: NPSize
    let output: NPSize
    private(set) var counters = (appended: 0, busy: 0, early: 0, repeated: 0)
    var onSegment: ((Data, Bool, Double) -> Void)?
    var onError: ((NPError) -> Void)?
    init(source: NPSize, display: NPSize, cast: Bool, cap: NPSize) throws { self.source = source; output = source }
    static func image(_ sample: CMSampleBuffer) -> CIImage? { nil }
    func append(_ sample: CMSampleBuffer, video isVideo: Bool) {}
    func repeatIfStill(now: TimeInterval, interval: TimeInterval) {}
    func cancel() {}
}

// AVFAudio bits used by NPAACEncoder
typealias AVAudioFrameCount = UInt32
typealias AVAudioPacketCount = UInt32
typealias AVAudioChannelCount = UInt32
enum AVAudioCommonFormat: UInt { case otherFormat, pcmFormatFloat32, pcmFormatFloat64, pcmFormatInt16, pcmFormatInt32 }
let AVFormatIDKey = "AVFormatIDKey", AVSampleRateKey = "AVSampleRateKey", AVNumberOfChannelsKey = "AVNumberOfChannelsKey"
let kAudioFormatMPEG4AAC: UInt32 = 0x61616320
struct AudioStreamPacketDescription { var mStartOffset: Int64 = 0; var mVariableFramesInPacket: UInt32 = 0; var mDataByteSize: UInt32 = 0 }
class AVAudioFormat: NSObject {
    init?(commonFormat: AVAudioCommonFormat, sampleRate: Double, channels: AVAudioChannelCount, interleaved: Bool) {}
    init?(settings: [String: Any]) {}
}
class AVAudioBuffer: NSObject {}
class AVAudioPCMBuffer: AVAudioBuffer {
    init?(pcmFormat format: AVAudioFormat, frameCapacity: AVAudioFrameCount) {}
    var frameLength: AVAudioFrameCount = 0
    var int16ChannelData: UnsafePointer<UnsafeMutablePointer<Int16>>? { nil }
}
class AVAudioCompressedBuffer: AVAudioBuffer {
    init(format: AVAudioFormat, packetCapacity: AVAudioPacketCount, maximumPacketSize: Int) { data = UnsafeMutableRawPointer.allocate(byteCount: 1, alignment: 1) }
    var packetCount: AVAudioPacketCount = 0
    var byteLength: UInt32 = 0
    let data: UnsafeMutableRawPointer
    var packetDescriptions: UnsafeMutablePointer<AudioStreamPacketDescription>? { nil }
}
enum AVAudioConverterInputStatus: Int { case haveData, noDataNow, endOfStream }
enum AVAudioConverterOutputStatus: Int { case haveData, inputRanDry, endOfStream, error }
typealias AVAudioConverterInputBlock = (AVAudioPacketCount, UnsafeMutablePointer<AVAudioConverterInputStatus>) -> AVAudioBuffer?
class AVAudioConverter: NSObject {
    init?(from fromFormat: AVAudioFormat, to toFormat: AVAudioFormat) {}
    var bitRate: Int = 0
    var maximumOutputPacketSize: Int { 0 }
    func convert(to outputBuffer: AVAudioBuffer, error outError: UnsafeMutablePointer<NSError?>?, withInputFrom inputBlock: @escaping AVAudioConverterInputBlock) -> AVAudioConverterOutputStatus { .haveData }
}

// Network bits used by NPHTTPServer
struct NWError: Error {}
final class NWParameters { static var tcp: NWParameters { NWParameters() }; var includePeerToPeer = false }
enum NWEndpoint { struct Port: ExpressibleByIntegerLiteral { let rawValue: UInt16; init(integerLiteral value: UInt16) { rawValue = value }; static let any: Port = 0 } }
final class NWListener {
    enum State { case setup, waiting(NWError), ready, failed(NWError), cancelled }
    init(using: NWParameters, on port: NWEndpoint.Port = .any) throws {}
    var stateUpdateHandler: ((State) -> Void)?
    var newConnectionHandler: ((NWConnection) -> Void)?
    var port: NWEndpoint.Port? { nil }
    func start(queue: DispatchQueue) {}
    func cancel() {}
}
final class NWConnection {
    enum State { case setup, waiting(NWError), preparing, ready, failed(NWError), cancelled }
    final class ContentContext { static let defaultMessage = ContentContext() }
    enum SendCompletion { case contentProcessed((NWError?) -> Void), idempotent }
    var stateUpdateHandler: ((State) -> Void)?
    func start(queue: DispatchQueue) {}
    func cancel() {}
    func receive(minimumIncompleteLength: Int, maximumLength: Int, completion: @escaping (Data?, ContentContext?, Bool, NWError?) -> Void) {}
    func send<Content: DataProtocol>(content: Content?, contentContext: ContentContext = .defaultMessage, isComplete: Bool = true, completion: SendCompletion) {}
}

// GoogleCast 4.8.6 bits used by NPGoogleCast (names as the headers import)
let kGCKDefaultMediaReceiverApplicationID = "CC1AD845"
let kGCKMetadataKeyTitle = "title"
let kGCKInvalidTimeInterval: TimeInterval = .nan
class GCKDiscoveryCriteria: NSObject { init(applicationID: String) {} }
class GCKCastOptions: NSObject {
    init(discoveryCriteria: GCKDiscoveryCriteria) {}
    var disableDiscoveryAutostart = false, disableAnalyticsLogging = false, physicalVolumeButtonsWillControlDeviceVolume = false
}
struct GCKDeviceCapabilities: OptionSet { let rawValue: Int; static let videoOut = GCKDeviceCapabilities(rawValue: 1) }
enum GCKDeviceType: Int { case generic, TV, speaker, speakerGroup, nearbyUnpaired }
class GCKDevice: NSObject {
    var uniqueID: String { "" }
    var friendlyName: String?
    var modelName: String?
    var deviceVersion: String?
    var isOnLocalNetwork: Bool { true }
    var type: GCKDeviceType { .generic }
    func hasCapabilities(_ capabilities: GCKDeviceCapabilities) -> Bool { true }
}
protocol GCKDiscoveryManagerListener: AnyObject {}
class GCKDiscoveryManager: NSObject {
    func add(_ listener: GCKDiscoveryManagerListener) {}
    func startDiscovery() {}
    func stopDiscovery() {}
    var discoveryActive: Bool { false }
    var deviceCount: UInt { 0 }
    func device(at index: UInt) -> GCKDevice { GCKDevice() }
}
protocol GCKSessionManagerListener: AnyObject {}
class GCKSession: NSObject { var device: GCKDevice { GCKDevice() }; var remoteMediaClient: GCKRemoteMediaClient? { nil } }
class GCKCastSession: GCKSession {}
class GCKSessionManager: NSObject {
    func add(_ listener: GCKSessionManagerListener) {}
    var currentCastSession: GCKCastSession? { nil }
    func startSession(with device: GCKDevice) -> Bool { true }
    @discardableResult func endSessionAndStopCasting(_ stopCasting: Bool) -> Bool { true }
}
class GCKCastContext: NSObject {
    private static let instance = GCKCastContext()
    static func sharedInstance() -> GCKCastContext { instance }
    static func setSharedInstanceWith(_ options: GCKCastOptions) {}
    let discoveryManager = GCKDiscoveryManager()
    let sessionManager = GCKSessionManager()
}
protocol GCKRemoteMediaClientListener: AnyObject {}
protocol GCKRequestDelegate: AnyObject {}
class GCKRequest: NSObject { weak var delegate: GCKRequestDelegate? }
class GCKError: NSError {}
enum GCKMediaPlayerState: Int { case unknown, idle, playing, paused, buffering, loading }
enum GCKMediaPlayerIdleReason: Int { case none, finished, cancelled, interrupted, error }
enum GCKMediaStreamType: Int { case none, buffered, live, unknown = 99 }
enum GCKHLSSegmentFormat: Int { case undefined, AAC, AC3, MP3, TS, TS_AAC, E_AC3, FMP4 }
enum GCKHLSVideoSegmentFormat: Int { case undefined, MPEG2_TS, FMP4 }
enum GCKMediaMetadataType: Int { case generic, movie, tvShow, musicTrack, photo, audioBookChapter, user = 100 }
enum GCKMediaResumeState: Int { case unchanged, play, pause }
class GCKMediaStatus: NSObject {
    var mediaSessionID: Int { 0 }
    var playerState: GCKMediaPlayerState { .unknown }
    var idleReason: GCKMediaPlayerIdleReason { .none }
    var playbackRate: Float { 1 }
    var streamPosition: TimeInterval { 0 }
}
class GCKMediaMetadata: NSObject { init(metadataType: GCKMediaMetadataType) {}; func setString(_ value: String, forKey key: String) {} }
class GCKMediaInformation: NSObject {}
class GCKMediaInformationBuilder: NSObject {
    init(contentURL: URL) {}
    var streamType: GCKMediaStreamType = .none
    var contentType: String?
    var metadata: GCKMediaMetadata?
    var hlsSegmentFormat: GCKHLSSegmentFormat = .undefined
    var hlsVideoSegmentFormat: GCKHLSVideoSegmentFormat = .undefined
    func build() -> GCKMediaInformation { GCKMediaInformation() }
}
class GCKMediaLoadRequestData: NSObject {}
class GCKMediaLoadRequestDataBuilder: NSObject {
    var mediaInformation: GCKMediaInformation?
    var autoplay: NSNumber?
    func build() -> GCKMediaLoadRequestData { GCKMediaLoadRequestData() }
}
class GCKMediaSeekOptions: NSObject { var seekToInfinite = false; var resumeState: GCKMediaResumeState = .unchanged }
class GCKRemoteMediaClient: NSObject {
    func add(_ listener: GCKRemoteMediaClientListener) {}
    func remove(_ listener: GCKRemoteMediaClientListener) {}
    var mediaStatus: GCKMediaStatus? { nil }
    func loadMedia(with requestData: GCKMediaLoadRequestData) -> GCKRequest { GCKRequest() }
    func play() -> GCKRequest { GCKRequest() }
    func setPlaybackRate(_ playbackRate: Float) -> GCKRequest { GCKRequest() }
    func requestStatus() -> GCKRequest { GCKRequest() }
    func seek(with options: GCKMediaSeekOptions) -> GCKRequest { GCKRequest() }
    func approximateStreamPosition() -> TimeInterval { 0 }
    func approximateLiveSeekableRangeEnd() -> TimeInterval { 0 }
}
// Network.framework: NWParameters(tls:tcp:) and NWProtocolTCP.Options.noDelay, as Apple documents them.
enum NWProtocolTLS { final class Options {} }
enum NWProtocolTCP { final class Options { var noDelay = false; init() {} } }
extension NWParameters { convenience init(tls: NWProtocolTLS.Options?, tcp: NWProtocolTCP.Options = .init()) { self.init() } }
