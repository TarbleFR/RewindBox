import Foundation
import UIKit
import AVFoundation
import MediaPlayer

final class NPController {
    let discovery = NPDiscovery()
    let cast = NPGoogleCast()
    let airplay = NPAirPlayMonitor()
    private var fence = NPSessionFence()
    private var capture: NPCapture?
    private var windows: NPWindowsTransport?
    private var http: NPHTTPServer?
    private var store: NPSegmentStore?
    private var overlay: UIWindow?
    private(set) var state = "idle"
    private var failure: String?
    private var selected: String?
    private var isStopping = false
    private var startTimer: Timer?
    private var didLoadCast = false
    private var mediaURL: URL?
    private var adapter = NPLinkAdapter()
    private var adapterTimer: Timer?
    private let localOutput = NPSystemVolumeOutput()
    private lazy var localAudio = NPLocalAudioLease(output: localOutput)
    private var audioWatchdog: Timer?
    // Chromecast: the route of this session, see NPGoogleCast.Route
    private var castRoute = NPGoogleCast.Route.segments
    private var direct: NPDirectStream?
    private var frames: NPFramesStream?          // RewindBox receiver, frames engine
    private var relaunchPending = false          // the capture is stopping before the session starts again on Google's receiver
    private var ladder: NPBitrateLadder?
    private var castLabel = ""
    private var pendingRoute: NPGoogleCast.Route? // the capture is stopping to start again on this route
    private var directFailures: [TimeInterval] = []
    private var statsTimer: Timer?
    private var statsTicks = 0
    var changed: (([String: Any]) -> Void)?
    init() {
        discovery.changed = { [weak self] in self?.publish() }; cast.changed = { [weak self] in self?.publish() }
        airplay.changed = { [weak self] in
            guard let self else { return }
            if NPAirPlayMonitor.facts().externalMirroring && self.fence.active { self.stop(error:.busy) } else { self.publish() }
        }
        airplay.start()
        discovery.failed = { [weak self] in self?.failure = NPError.network.rawValue; self?.publish() }
        NotificationCenter.default.addObserver(forName: UIApplication.didEnterBackgroundNotification, object: nil, queue: .main) { [weak self] _ in if self?.fence.active == true { self?.stop() } }
        NotificationCenter.default.addObserver(forName: AVAudioSession.routeChangeNotification, object: nil, queue: .main) { [weak self] _ in if self?.localAudio.active == true, self?.selected?.hasPrefix("windows:") == true { self?.stop() } }
    }
    var snapshot: [String: Any] { ["state": state, "error": failure as Any? ?? NSNull(), "localAudioSuppressed": localAudio.active, "selected": selected as Any? ?? NSNull(), "receivers": discovery.receivers + cast.receivers, "appleTV": airplay.snapshot, "stream": streamDiagnostics as Any? ?? NSNull(), "castMode": NPCastMode.stored.rawValue, "physicalValidation": ["windows": false, "chromecast": false, "appleTV": false, "controllerBattery": false]] }
    private var streamDiagnostics: [String: Any]? {
        guard var stream = capture?.diagnostics else { return nil }
        if selected?.hasPrefix("cast:") == true {
            stream["cast"] = cast.diagnostics.merging(["route": castRoute.rawValue]) { _, session in session }
            if let direct { stream["direct"] = direct.statistics }
            if let frames { stream["frames"] = frames.statistics }
        }
        return stream
    }
    func setCastMode(_ value: String) { NPCastMode.store(NPCastMode(rawValue: value) ?? .automatic); publish() }
    private func publish() { changed?(snapshot) }
    func discover() { failure = nil; discovery.start(); cast.startDiscovery(); publish() }
    func stopDiscovery() { discovery.stop(); cast.stopDiscovery() }
    func connect(id: String, pin: String, stopLabel: String) throws {
        guard !NPAirPlayMonitor.facts().externalMirroring, !isStopping, !localAudio.active, let token = fence.begin() else { throw NPError.busy }
        NPLog.record("session.connect", ["kind": id.hasPrefix("cast:") ? "cast" : "windows"])
        state = "connecting"; failure = nil; selected = id; didLoadCast = false; publish()
        let fail: (NPError) -> Void = { [weak self] error in DispatchQueue.main.async { guard let self, self.fence.accepts(token) else { return }; self.stop(error: error) } }
        let playing: () -> Void = { [weak self] in DispatchQueue.main.async {
            guard let self, self.fence.accepts(token) else { return }
            if id.hasPrefix("windows:"), !self.localAudio.active {
                self.showOverlay(label: stopLabel)
                guard self.localAudio.begin() else { self.stop(error: .unavailable); return }
                let audioToken = self.localAudio.generation
                var unconfirmed = 0
                self.audioWatchdog?.invalidate()
                self.audioWatchdog = Timer.scheduledTimer(withTimeInterval: 0.25, repeats: true) { [weak self] timer in
                    guard let self, self.fence.accepts(token), self.localAudio.active else { timer.invalidate(); return }
                    if self.localAudio.verify(audioToken) { unconfirmed = 0 }
                    else {
                        unconfirmed += 1
                        if unconfirmed >= 4 || !self.localAudio.enforce(audioToken) { self.stop(error: .unavailable) }
                    }
                }
                NPLog.record("audio.local.suppressed")
            }
            if id.hasPrefix("cast:"), !self.localAudio.active, self.state != "streaming" {
                // The TV plays the sound a moment after the phone: both at once is an echo. Best effort, never a reason to stop;
                // the volume buttons stay the user's.
                NPLog.record(self.localAudio.begin() ? "audio.local.suppressed" : "audio.local.kept", ["route": "cast"])
            }
            if self.state != "streaming" { NPLog.record("receiver.playing") }
            self.state = "streaming"; self.startTimer?.invalidate(); self.startTimer = nil; self.publish()
        } }
        startTimer = Timer.scheduledTimer(withTimeInterval: 40, repeats: false) { _ in fail(.timeout) }
        if id.hasPrefix("windows:"), let service = discovery.services[id], let host = service.hostName {
            let transport = NPWindowsTransport(); windows = transport; transport.onError = fail; transport.onPlayback = playing
            transport.onReady = { [weak self, weak transport] size in DispatchQueue.main.async { self?.startCapture(token: token, size: size, castRoute: false, stopLabel: stopLabel, frames: transport?.framesSupported == true, receiverMax: transport?.receiverMax ?? NPPolicy.legacyCap) } }
            // A shed picture, or a receiver that cannot decode fast enough, asks for a key picture at once; repeated ones lower the tier.
            let congested: (Int) -> Void = { [weak self] count in DispatchQueue.main.async { guard let self, self.fence.accepts(token) else { return }; self.capture?.linkShed(); if let tier = self.adapter.shed(at: Date().timeIntervalSinceReferenceDate, count: count) { NPLog.record("link.tier", ["tier": tier.rawValue, "dropped": count]); self.capture?.setTier(tier) } } }
            transport.onShed = { count, kind in if kind == 4 { congested(count) } }
            transport.onKeyRequest = { NPLog.record("receiver.keyframe"); congested(1) }
            transport.onDisplay = { [weak self] size in DispatchQueue.main.async { guard let self, self.fence.accepts(token) else { return }; self.capture?.updateDisplay(size) } }
            transport.connect(host: host, port: service.port, pin: pin)
        } else if id.hasPrefix("cast:") {
            castLabel = stopLabel; directFailures = []; pendingRoute = nil; relaunchPending = false
            cast.onError = fail; cast.onPlayback = playing
            cast.onDirectTrouble = { [weak self] reason in guard let self, self.fence.accepts(token) else { return }; self.directTrouble(reason, token: token) }
            cast.onReady = { [weak self] in
                guard let self, self.fence.accepts(token) else { return }
                // The RewindBox receiver first tells what it can decode; Google's receiver gets the stream at once.
                if self.cast.receiverApplication == nil { self.startCastMedia(route: self.preferredCastRoute(), token: token) }
            }
            cast.onReceiverEvent = { [weak self] event in guard let self, self.fence.accepts(token) else { return }; self.receiverEvent(event, token: token) }
            // Automatic mode tries the RewindBox receiver first (when configured); the other settings keep Google's receiver.
            cast.connect(id, useReceiver: NPCastMode.stored == .automatic)
        } else { stop(error: .receiverGone); throw NPError.receiverGone }
    }
    private func startCapture(token: Int, size: NPSize, castRoute: Bool, stopLabel: String, frames: Bool = false, receiverMax: NPSize = NPPolicy.legacyCap, sink: ((Data) -> Void)? = nil, stillInterval: TimeInterval = 0) {
        guard fence.accepts(token), capture == nil else { return }
        NPLog.record("session.protocol", ["frames": frames, "maxWidth": receiverMax.width, "maxHeight": receiverMax.height])
        let capture = NPCapture(); self.capture = capture; capture.display = size; capture.cast = castRoute; capture.frames = frames; capture.receiverMax = receiverMax
        capture.stillInterval = stillInterval // see startCastMedia
        adapter = NPLinkAdapter(); adapterTimer?.invalidate()
        adapterTimer = Timer.scheduledTimer(withTimeInterval: 5, repeats: true) { [weak self] _ in
            guard let self, self.fence.accepts(token) else { return }
            if let tier = self.adapter.tick(at: Date().timeIntervalSinceReferenceDate) { NPLog.record("link.tier", ["tier": tier.rawValue]); self.capture?.setTier(tier) }
        }
        capture.onError = { [weak self] error in DispatchQueue.main.async { guard let self, self.fence.accepts(token) else { return }; self.stop(error: error) } }
        capture.onStarted = { [weak self] in guard let self, self.fence.accepts(token) else { return }; self.state = "capturing"; self.showOverlay(label: stopLabel); self.publish() }
        let store = self.store, windows = self.windows
        capture.onPacket = { packet in if let sink { sink(packet) } else { windows?.sendPacket(packet) } }
        capture.onSegment = { [weak self] data, initial, duration in
            do {
                if let store { if initial { try store.initialize(data) } else { try store.append(data, duration: duration) } }
                windows?.send(data, initial: initial)
                if castRoute && store?.isReady == true {
                    DispatchQueue.main.async { guard let self, self.fence.accepts(token), !self.didLoadCast, let url = self.mediaURL else { return }; self.didLoadCast = true; store?.beginLoad(); self.cast.load(url, route: .segments) }
                }
            } catch { DispatchQueue.main.async { if self?.fence.accepts(token) == true { self?.stop(error: .encoder) } } }
        }
        capture.onStopped = { [weak self, weak capture] in
            guard let self, self.capture === capture else { return }
            self.capture = nil; self.isStopping = false; self.publish()
            // The RewindBox receiver cannot be used: now that the capture is stopped, the session starts again on Google's receiver.
            if self.relaunchPending, self.fence.accepts(token) { self.relaunchPending = false; self.cast.relaunchDefault("receiver"); return }
            // The capture was stopped to change the Chromecast route: start it again on the other one, same Cast session.
            if let route = self.pendingRoute, self.fence.accepts(token) { self.pendingRoute = nil; self.startCastMedia(route: route, token: token) }
        }
        capture.start()
    }
    // Automatic: the direct route, unless this receiver model failed to start it before. The setting can force either.
    private func preferredCastRoute() -> NPGoogleCast.Route {
        switch NPCastMode.stored {
        case .direct: return .direct
        case .compatible: return .segments
        case .automatic: return NPCastMode.directFailed(model: cast.deviceModel) ? .segments : .direct
        }
    }
    private func startCastMedia(route: NPGoogleCast.Route, token: Int) {
        guard fence.accepts(token) else { return }
        let fail: (NPError) -> Void = { [weak self] error in DispatchQueue.main.async { guard let self, self.fence.accepts(token) else { return }; self.stop(error: error) } }
        var route = route
        var stream: NPDirectStream?
        if route == .direct || route == .mp4 {
            if let encoder = NPAACEncoder() { stream = NPDirectStream(audioEncoder: encoder) }
            else {
                NPLog.record("cast.direct.unavailable", ["reason": "aac"])
                if route == .mp4 { receiverUnusable(token: token); return }
                route = .segments
            }
        }
        let framesStream = route == .frames ? NPFramesStream() : nil
        castRoute = route; didLoadCast = false; direct = stream; frames = framesStream; ladder = nil; mediaURL = nil
        if route == .frames || route == .mp4 { cast.receiverEngine(route) }
        NPLog.record("cast.route", ["route": route.rawValue, "mode": NPCastMode.stored.rawValue, "model": cast.deviceModel ?? ""])
        let http: NPHTTPServer
        if let stream {
            store = nil
            // The stream calls back from the capture and server queues; the session state lives on the main thread.
            stream.onKeyRequest = { [weak self] in DispatchQueue.main.async { self?.capture?.requestKeyFrame() } }
            stream.onCongestion = { [weak self, weak stream] in DispatchQueue.main.async {
                guard let self, let stream, self.fence.accepts(token), let lower = self.ladder?.congested(at: ProcessInfo.processInfo.systemUptime) else { return }
                NPLog.record("cast.direct.bitrate", ["bitrate": lower, "reason": "congestion"]); self.capture?.setBitrate(lower); stream.setBitrate(lower)
            } }
            stream.onReset = { [weak self] reason in DispatchQueue.main.async {
                guard let self, self.fence.accepts(token), self.castRoute == .direct || self.castRoute == .mp4, self.pendingRoute == nil else { return }
                NPLog.record("cast.direct.reset", ["reason": reason, "route": self.castRoute.rawValue]); self.http?.closeLive()
                if self.castRoute == .direct { self.cast.reload() } // the RewindBox receiver opens a new connection by itself
            } }
            stream.onReady = { [weak self, weak stream] in DispatchQueue.main.async {
                guard let self, let stream, self.fence.accepts(token), !self.didLoadCast, let url = self.mediaURL else { return }
                self.didLoadCast = true
                let size = stream.statistics
                let nominal = NPPolicy.bitrate(for: NPSize(width: size["width"] as? Int ?? 1280, height: size["height"] as? Int ?? 720))
                self.ladder = NPBitrateLadder(nominal: nominal); stream.setBitrate(nominal)
                if self.castRoute == .mp4 {
                    self.cast.link.captureOrigin = { [weak self] in self?.capture?.timelineOrigin }
                    self.cast.link.play(engine: "mp4", url: url); return
                }
                self.cast.newestPicture = { [weak stream] in stream?.newestPictureSeconds ?? 0 }
                self.cast.load(url, route: .direct)
            } }
            http = NPHTTPServer(store: nil, live: stream)
            http.onReceiverAgent = { agent in NPLog.record("cast.receiver.agent", ["agent": agent]) }
        } else if let framesStream {
            store = nil
            framesStream.onKeyRequest = { [weak self] in DispatchQueue.main.async { self?.capture?.requestKeyFrame() } }
            framesStream.onCongestion = { [weak self, weak framesStream] in DispatchQueue.main.async {
                guard let self, let framesStream, self.fence.accepts(token), let lower = self.ladder?.congested(at: ProcessInfo.processInfo.systemUptime) else { return }
                NPLog.record("cast.direct.bitrate", ["bitrate": lower, "reason": "congestion", "route": "frames"]); self.capture?.setBitrate(lower); framesStream.setBitrate(lower)
            } }
            framesStream.onReset = { [weak self] reason in DispatchQueue.main.async {
                guard let self, self.fence.accepts(token), self.castRoute == .frames else { return }
                NPLog.record("cast.frames.reset", ["reason": reason]); self.http?.closeLive() // the receiver reconnects and starts on a key picture
            } }
            framesStream.onReady = { [weak self, weak framesStream] in DispatchQueue.main.async {
                guard let self, let framesStream, self.fence.accepts(token), !self.didLoadCast, let url = self.mediaURL else { return }
                self.didLoadCast = true
                let size = framesStream.statistics
                let nominal = NPPolicy.bitrate(for: NPSize(width: size["width"] as? Int ?? 1280, height: size["height"] as? Int ?? 720))
                self.ladder = NPBitrateLadder(nominal: nominal); framesStream.setBitrate(nominal)
                self.cast.link.captureOrigin = { [weak self] in self?.capture?.timelineOrigin }
                self.cast.link.play(engine: "frames", url: url)
            } }
            http = NPHTTPServer(store: nil, live: framesStream, resource: "frames", contentType: "application/octet-stream")
            http.onReceiverAgent = { agent in NPLog.record("cast.receiver.agent", ["agent": agent]) }
        } else {
            let store = NPSegmentStore(); self.store = store
            http = NPHTTPServer(store: store)
        }
        self.http = http
        statsTimer?.invalidate(); statsTicks = 0
        statsTimer = Timer.scheduledTimer(withTimeInterval: 2, repeats: true) { [weak self] _ in self?.castStats(token: token) }
        http.start { [weak self] result in DispatchQueue.main.async {
            guard let self, self.fence.accepts(token), self.http === http else { http.stop(); return }
            switch result {
            case .success(let url):
                self.mediaURL = url
                // A still screen must not starve a media element: the direct and mp4 routes repeat the last picture thirty times a
                // second (measured on Google's receiver page: 0.7 s to start and 0.9-1.0 s behind, against 7-17 s at five a second);
                // segments only need their length kept. The frames engine draws what it gets; four repeats a second keep its
                // delay measured on a still screen and give a key picture something to ride on.
                let sink: ((Data) -> Void)? = stream.map { stream in { stream.consume($0) } } ?? framesStream.map { frames in { frames.consume($0) } }
                let still: TimeInterval = framesStream != nil ? 0.25 : stream != nil ? 1.0 / 30 : 0.2
                self.startCapture(token: token, size: NPSize(width: 1280, height: 720), castRoute: sink == nil, stopLabel: self.castLabel, frames: sink != nil, receiverMax: NPSize(width: 1280, height: 720), sink: sink, stillInterval: still)
            case .failure(let error): fail(error)
            }
        } }
    }
    // RewindBox receiver. Its capabilities choose the engine; it asks for key pictures, for the MediaSource engine when its
    // WebCodecs cannot keep up, and it reports when it shows the first picture (NPGoogleCast turns that into onPlayback).
    private func receiverEvent(_ event: NPReceiverLink.Event, token: Int) {
        switch event {
        case .caps(let caps):
            guard capture == nil, http == nil else { return }
            switch caps["prefer"] as? String {
            case "frames": startCastMedia(route: .frames, token: token)
            case "mp4": startCastMedia(route: .mp4, token: token)
            default: receiverUnusable(token: token)
            }
        case .playing: break
        case .key: capture?.requestKeyFrame()
        case .switchEngine:
            guard castRoute == .frames, pendingRoute == nil, capture != nil else { return }
            pendingRoute = .mp4; http?.stop(); http = nil; frames = nil; ladder = nil; mediaURL = nil
            capture?.stop() // onStopped starts the mp4 engine, same session
        case .failed: receiverUnusable(token: token)
        }
    }
    // The RewindBox receiver did not answer, cannot decode or does not play: Google's receiver takes over in the same user
    // action. The capture stops first; onStopped then starts the session again (NPGoogleCast.relaunchDefault).
    private func receiverUnusable(token: Int) {
        guard fence.accepts(token) else { return }
        pendingRoute = nil; http?.stop(); http = nil; direct = nil; frames = nil; ladder = nil; mediaURL = nil; didLoadCast = false
        startTimer?.invalidate()
        startTimer = Timer.scheduledTimer(withTimeInterval: 40, repeats: false) { [weak self] _ in guard let self, self.fence.accepts(token) else { return }; self.stop(error: .timeout) }
        if capture != nil { relaunchPending = true; capture?.stop() } else { cast.relaunchDefault("receiver") }
    }
    // Every 2 s of a Chromecast session: the readout for the panel, the way back up of the bit rate, and a log row every 10 s.
    private func castStats(token: Int) {
        guard fence.accepts(token) else { return }
        statsTicks += 1
        // The direct route plays on this receiver model: an earlier failed start no longer keeps automatic mode away from it.
        if castRoute == .direct, cast.everStarted { NPCastMode.clearDirectFailed(model: cast.deviceModel) }
        if let higher = ladder?.tick(at: ProcessInfo.processInfo.systemUptime) {
            NPLog.record("cast.direct.bitrate", ["bitrate": higher, "reason": "quiet", "route": castRoute.rawValue]); capture?.setBitrate(higher); direct?.setBitrate(higher); frames?.setBitrate(higher)
        }
        if statsTicks % 5 == 0, var row = capture?.diagnostics {
            row.removeValue(forKey: "output"); row["route"] = castRoute.rawValue
            if let direct { for (key, value) in direct.statistics { row[key] = value } }
            if let frames { for (key, value) in frames.statistics { row[key] = value } }
            NPLog.record("cast.stats", row)
        }
        publish()
    }
    // The direct route did not start, ended or fell too far behind. It is loaded again; after repeated failures the session
    // continues on the segments route (the capture restarts, the Cast session stays), unless the setting forces the direct one.
    private func directTrouble(_ reason: String, token: Int) {
        guard castRoute == .direct, pendingRoute == nil, capture != nil else { return }
        let now = ProcessInfo.processInfo.systemUptime
        let started = cast.diagnostics["started"] as? Bool == true
        directFailures = directFailures.filter { now - $0 < 60 } + [now]
        let forced = NPCastMode.stored == .direct
        if directFailures.count >= (forced ? 6 : (reason == "load" ? 1 : started ? 3 : 2)) {
            if forced { stop(error: .cast); return }
            NPLog.record("cast.direct.fallback", ["reason": reason, "started": started, "model": cast.deviceModel ?? ""])
            if !cast.everStarted, reason != "reload" { NPCastMode.rememberDirectFailed(model: cast.deviceModel) }
            // The direct route may already have reported playback, which ended the start timer: the segments route gets its own.
            startTimer?.invalidate()
            startTimer = Timer.scheduledTimer(withTimeInterval: 40, repeats: false) { [weak self] _ in guard let self, self.fence.accepts(token) else { return }; self.stop(error: .timeout) }
            pendingRoute = .segments; cast.newestPicture = nil
            http?.stop(); http = nil; direct = nil; ladder = nil; mediaURL = nil
            capture?.stop() // onStopped starts the segments route
            return
        }
        http?.closeLive(); cast.reload()
    }
    func stop(error: NPError? = nil) {
        NPLog.record("session.stop", ["reason": error?.rawValue ?? "user"])
        fence.stop(); startTimer?.invalidate(); startTimer = nil; adapterTimer?.invalidate(); adapterTimer = nil
        statsTimer?.invalidate(); statsTimer = nil; pendingRoute = nil; relaunchPending = false; direct = nil; frames = nil; ladder = nil; directFailures = []
        audioWatchdog?.invalidate(); audioWatchdog = nil
        let restored = localAudio.end()
        NPLog.record("audio.local.restore.requested", ["accepted": restored])
        failure = error?.rawValue; state = error == nil ? "idle" : "failed"; selected = nil
        windows?.stop(); windows = nil; cast.stop(); http?.stop(); http = nil; store = nil; mediaURL = nil
        if restored { overlay?.isHidden = true; overlay = nil }
        else {
            var attempts = 0
            audioWatchdog = Timer.scheduledTimer(withTimeInterval: 0.25, repeats: true) { [weak self] timer in
                guard let self else { timer.invalidate(); return }
                attempts += 1
                if self.localAudio.end() {
                    timer.invalidate(); self.audioWatchdog = nil
                    self.overlay?.isHidden = true; self.overlay = nil
                    self.publish()
                } else if attempts >= 20 {
                    timer.invalidate(); self.audioWatchdog = nil
                    NPLog.record("audio.local.restore.failed")
                    self.publish()
                }
            }
        }
        isStopping = capture != nil; capture?.stop(); publish()
    }
    private func showOverlay(label: String) {
        // Only the iPhone's own scene: the external display scene (external_display plugin) must never host the overlay.
        guard overlay == nil, let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first(where: { $0.activationState == .foregroundActive && $0.session.role == .windowApplication }) else { return }
        let window = NPOverlayWindow(windowScene: scene); window.windowLevel = .alert - 1
        let controller = UIViewController(); controller.view.backgroundColor = .clear; window.rootViewController = controller
        controller.view.addSubview(localOutput.view)
        let button = UIButton(type: .system); button.setTitle("NeoPlay ×", for: .normal); button.accessibilityLabel = label; button.accessibilityIdentifier = "neoplay-stop-stream"
        button.backgroundColor = UIColor.black.withAlphaComponent(0.7); button.tintColor = .white; button.layer.cornerRadius = 12
        button.translatesAutoresizingMaskIntoConstraints = false; controller.view.addSubview(button)
        NSLayoutConstraint.activate([button.centerXAnchor.constraint(equalTo: controller.view.safeAreaLayoutGuide.centerXAnchor), button.topAnchor.constraint(equalTo: controller.view.safeAreaLayoutGuide.topAnchor, constant: 8), button.widthAnchor.constraint(equalToConstant: 110), button.heightAnchor.constraint(equalToConstant: 36)])
        button.addAction(UIAction { [weak self] _ in self?.stop() }, for: .touchUpInside)
        window.button = button; window.isHidden = false; overlay = window // Never make this the key window.
    }
}
private final class NPOverlayWindow: UIWindow {
    weak var button: UIButton?
    override func hitTest(_ point: CGPoint, with event: UIEvent?) -> UIView? {
        guard let button, button.bounds.contains(convert(point, to: button)) else { return nil }
        return super.hitTest(point, with: event)
    }
}


protocol NPVolumeOutput: AnyObject {
    var volume: Float { get }
    func setVolume(_ value: Float) -> Bool
}

final class NPLocalAudioLease {
    private let output: NPVolumeOutput
    private var original: Float?
    private var attenuationRequested = false
    private(set) var generation = 0
    var active: Bool { original != nil }
    init(output: NPVolumeOutput) { self.output = output }
    @discardableResult func begin() -> Bool {
        if active { return true }
        let value = output.volume
        guard value.isFinite, (0...1).contains(value) else { return false }
        original = value; generation += 1
        if value <= 0.001 { return true }
        guard output.setVolume(0) else { _ = end(); return false }
        attenuationRequested = true
        return true
    }
    func verify(_ token: Int) -> Bool { active && token == generation && output.volume <= 0.001 }
    func enforce(_ token: Int) -> Bool {
        guard active, token == generation else { return false }
        return output.volume <= 0.001 || output.setVolume(0)
    }
    @discardableResult func end() -> Bool {
        guard let value = original else { return true }
        generation += 1
        if attenuationRequested || abs(output.volume - value) > 0.02 {
            guard output.setVolume(value) else { return false }
        }
        guard abs(output.volume - value) <= 0.02 else { return false }
        original = nil; attenuationRequested = false
        return true
    }
}

final class NPSystemVolumeOutput: NPVolumeOutput {
    let view = MPVolumeView(frame: CGRect(x: 0, y: 0, width: 120, height: 24))
    var volume: Float { AVAudioSession.sharedInstance().outputVolume }
    init() {
        view.showsRouteButton = false
        view.alpha = 0.01
        view.isUserInteractionEnabled = false
        view.accessibilityElementsHidden = true
    }
    func setVolume(_ value: Float) -> Bool {
        guard view.window != nil, let slider = view.subviews.compactMap({ $0 as? UISlider }).first else { return false }
        slider.setValue(value, animated: false)
        slider.sendActions(for: .valueChanged)
        slider.sendActions(for: .touchUpInside)
        return true
    }
}
