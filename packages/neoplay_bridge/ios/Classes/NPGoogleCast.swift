import Foundation
import GoogleCast

// Google Cast is a separate receiver protocol; never call a Chromecast an AirPlay receiver.
final class NPGoogleCast: NSObject, GCKDiscoveryManagerListener, GCKSessionManagerListener, GCKRemoteMediaClientListener, GCKRequestDelegate, GCKGenericChannelDelegate {
    private var initialized = false
    private var selected: String?
    private var ownsSession = false
    private var cancelling = false
    private var liveTimer: Timer?        // main thread, see NPLiveLagTracker
    private var lag = NPLiveLagTracker()
    private var lagChecks = 0
    var changed: (() -> Void)?
    var onReady: (() -> Void)?
    var onPlayback: (() -> Void)?
    var onError: ((NPError) -> Void)?
    // RewindBox receiver (NPReceiverApp): the application this session launched, its channel and its protocol.
    let link = NPReceiverLink()
    var onReceiverEvent: ((NPReceiverLink.Event) -> Void)?
    private(set) var receiverApplication: String?
    private var channel: GCKGenericChannel?
    private var selectedDevice: GCKDevice?
    private var relaunching = false               // the session ends to start again on Google's receiver
    private var context: GCKCastContext { GCKCastContext.sharedInstance() }
    func startDiscovery() {
        if !initialized {
            let options = GCKCastOptions(discoveryCriteria: GCKDiscoveryCriteria(applicationID: kGCKDefaultMediaReceiverApplicationID))
            options.disableDiscoveryAutostart = true
            options.disableAnalyticsLogging = true
            options.physicalVolumeButtonsWillControlDeviceVolume = false
            GCKCastContext.setSharedInstanceWith(options)
            context.discoveryManager.add(self); context.sessionManager.add(self); initialized = true
        }
        // A new user request must also recover a scan previously suspended by
        // a Settings/network round trip, without ending an owned Cast session.
        context.discoveryManager.stopDiscovery()
        context.discoveryManager.startDiscovery()
        recordDiscovery("cast.discovery.requested"); changed?()
    }
    func stopDiscovery() { if initialized { context.discoveryManager.stopDiscovery() } }
    func didUpdateDeviceList() { recordDiscovery("cast.discovery.updated"); changed?() }
    private func recordDiscovery(_ event: String) {
        NPLog.record(event, ["active": context.discoveryManager.discoveryActive,
                             "deviceCount": context.discoveryManager.deviceCount,
                             "eligibleCount": devices.count])
    }
    private var devices: [GCKDevice] {
        guard initialized else { return [] }
        return (0..<context.discoveryManager.deviceCount).map { context.discoveryManager.device(at: $0) }.filter { $0.isOnLocalNetwork && $0.hasCapabilities(.videoOut) }
    }
    // Model name of the receiver of this session, as the device announces it ("Chromecast", "Chromecast Ultra", "Google TV Streamer" ...).
    var deviceModel: String? { ownsSession ? context.sessionManager.currentCastSession?.device.modelName : nil }
    var receivers: [[String: Any]] { devices.map { ["id": "cast:\($0.uniqueID)", "name": $0.friendlyName ?? "Chromecast", "kind": "cast"] } }
    // useReceiver: launch the RewindBox receiver when it is configured and has not just failed on this model.
    func connect(_ id: String, useReceiver: Bool = false) {
        guard let device = devices.first(where: { "cast:\($0.uniqueID)" == id }) else { onError?(.receiverGone); return }
        // Do not take over a session started by another integration.
        guard context.sessionManager.currentCastSession == nil, selected == nil else { onError?(.busy); return }
        selected = device.uniqueID; selectedDevice = device
        let application = useReceiver && NPReceiverApp.enabled && !NPCastMode.receiverFailed(model: device.modelName) ? NPReceiverApp.applicationID : nil
        if !launch(device, application: application) { selected = nil; selectedDevice = nil; receiverApplication = nil; onError?(.cast) }
    }
    private func launch(_ device: GCKDevice, application: String?) -> Bool {
        receiverApplication = application
        NPLog.record("cast.launch", ["application": application ?? kGCKDefaultMediaReceiverApplicationID, "model": device.modelName ?? ""])
        guard let application else { return context.sessionManager.startSession(with: device) }
        return context.sessionManager.startSession(with: device, sessionOptions: [NPReceiverApp.sessionOptionKey: application as NSString])
    }
    // The RewindBox receiver did not answer or cannot play here: end its session and start one on Google's receiver, same
    // device; onReady follows as for a first start.
    func relaunchDefault(_ reason: String) {
        guard receiverApplication != nil, ownsSession else { return }
        NPLog.record("cast.receiver.relaunch", ["reason": reason, "model": selectedDevice?.modelName ?? ""])
        NPCastMode.rememberReceiverFailed(model: selectedDevice?.modelName)
        closeReceiver(); relaunching = true
        context.sessionManager.endSessionAndStopCasting(true)
    }
    func sessionManager(_ sessionManager: GCKSessionManager, didStart session: GCKCastSession) {
        guard selected == session.device.uniqueID else { return }
        ownsSession = true
        if cancelling { sessionManager.endSessionAndStopCasting(true); return }
        if receiverApplication != nil { openReceiver(session) } else { session.remoteMediaClient?.add(self) }
        onReady?() // kept: a session started again on Google's receiver is ready again
    }
    private func openReceiver(_ session: GCKCastSession) {
        let channel = GCKGenericChannel(namespace: NPReceiverLink.namespace)
        channel.delegate = self; session.add(channel); self.channel = channel
        route = .frames
        link.send = { [weak self] message in self?.sendReceiver(message) }
        link.log = { event, row in NPLog.record(event, row) }
        link.onEvent = { [weak self] event in
            guard let self else { return }
            // A picture on the TV: the session is streaming, and this model can use the receiver again.
            if case .playing = event { NPCastMode.clearReceiverFailed(model: self.selectedDevice?.modelName); self.onPlayback?() }
            self.onReceiverEvent?(event)
        }
        link.start(); startLiveWatch()
    }
    private func closeReceiver() {
        if let channel { _ = context.sessionManager.currentCastSession?.remove(channel); channel.delegate = nil }
        channel = nil; link.reset(); link.send = nil; link.onEvent = nil; stopLiveWatch()
    }
    func sendReceiver(_ message: [String: Any]) {
        guard let channel, channel.isConnected, let data = try? JSONSerialization.data(withJSONObject: message), let text = String(data: data, encoding: .utf8) else { return }
        _ = channel.sendTextMessage(text, error: nil)
    }
    func castChannel(_ channel: GCKGenericChannel, didReceiveTextMessage message: String, withNamespace protocolNamespace: String) {
        guard channel === self.channel, let data = message.data(using: .utf8), let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return }
        link.receive(object)
    }
    // The receiver plays the stream itself: the route is the engine it plays with.
    func receiverEngine(_ engine: Route) { route = engine }
    // Two ways to give the default receiver a live picture. `direct`: one endless fragmented MP4 that its media
    // element plays as it arrives. `segments`: HLS, played by the receiver's HLS player with its own buffer.
    // RewindBox receiver: `frames` (WebCodecs) or `mp4` (its MediaSource player on the direct route's stream).
    enum Route: String { case direct, segments, frames, mp4 }
    static let startTimeout: TimeInterval = 8 // direct route: no moving picture this long after a load is a failed start
    private(set) var route = Route.segments
    private var loadedURL: URL?
    private var loadedAt: TimeInterval = 0
    private var loads = 0
    private var orderedSession = Int.min   // media session the play order went to
    private var replacedSession = Int.min  // media session that the current load replaced: its late statuses are not ours
    private var started = false
    private(set) var everStarted = false   // the direct route has played at least once in this session
    private var reports = 0                // positions reported by the receiver that moved, see checkDirect
    private var lastReported = -1.0
    private var playbackReported = false   // once per load: the direct route sends many statuses a second
    private var moving = 0
    private var lastPosition = -1.0
    private var lastAdvance: TimeInterval = 0
    private var lastTrouble: TimeInterval = -.infinity
    private var control = NPLagController()
    private var lastLag = 0.0
    private var heldLag = -1.0   // what the receiver says it holds ahead, in seconds; -1 when it does not say
    private var window = (count: 0, sum: 0.0, low: Double.infinity, high: 0.0) // lag since the last log row
    private var ticks = 0
    var newestPicture: (() -> Double)?          // direct route: time stamp, in seconds, of the newest picture produced
    var onDirectTrouble: ((String) -> Void)?    // direct route: "start", "load", "error", "ended" or "reload"
    private var uptime: TimeInterval { ProcessInfo.processInfo.systemUptime }
    var diagnostics: [String: Any] {
        if receiverApplication != nil {
            // Capture-to-screen delay measured by the receiver, decoding included (Google's receiver can only give the player's).
            return ["route": route.rawValue, "receiver": "rewindbox", "started": link.playing, "lagMs": link.latencyMs ?? -1, "rttMs": link.bestRoundTripMs ?? -1]
        }
        return ["route": route.rawValue, "started": started, "lagMs": Int(lastLag * 1000), "targetMs": Int(control.target * 1000), "rate": Double(control.rate),
                "stalls": control.stalls, "loads": loads]
    }
    func load(_ url: URL, route: Route) {
        guard route == .direct || route == .segments, receiverApplication == nil, ownsSession, let session = context.sessionManager.currentCastSession, selected == session.device.uniqueID else { onError?(.cast); return }
        let media = GCKMediaInformationBuilder(contentURL: url)
        media.streamType = .live
        switch route {
        case .direct: media.contentType = "video/mp4"
        case .segments:
            // hlsVideoSegmentFormat only. With hlsSegmentFormat (the audio format) also set to fMP4, Google's older HLS player,
            // still used on receivers opted out of Shaka, refuses this muxed stream at once (error 104 on the receiver page).
            media.contentType = "application/vnd.apple.mpegurl"; media.hlsVideoSegmentFormat = .FMP4
        case .frames, .mp4: return // the RewindBox receiver is never sent a load, see the guard
        }
        let metadata = GCKMediaMetadata(metadataType: .generic); metadata.setString("NeoPlay", forKey: kGCKMetadataKeyTitle); media.metadata = metadata
        let request = GCKMediaLoadRequestDataBuilder(); request.mediaInformation = media.build(); request.autoplay = true
        replacedSession = session.remoteMediaClient?.mediaStatus?.mediaSessionID ?? Int.min
        self.route = route; loadedURL = url; loadedAt = uptime; loads += 1
        started = false; playbackReported = false; moving = 0; reports = 0; lastReported = -1; lastPosition = -1; lastAdvance = loadedAt; control.restarted(at: loadedAt)
        NPLog.record("cast.load", ["route": route.rawValue, "count": loads, "model": session.device.modelName ?? "", "version": session.device.deviceVersion ?? "", "type": session.device.type.rawValue])
        session.remoteMediaClient?.loadMedia(with: request.build()).delegate = self
        if route == .direct { startLiveWatch() }
    }
    // The same stream again: the receiver opens a new connection, which starts on the live picture.
    func reload() { if let loadedURL { load(loadedURL, route: route) } }
    func remoteMediaClient(_ client: GCKRemoteMediaClient, didUpdate mediaStatus: GCKMediaStatus?) {
        guard ownsSession, let status = mediaStatus else { return }
        let state = status.playerState
        if route == .direct, state != .idle, state != .unknown, status.mediaSessionID != orderedSession {
            // The receiver starts its media element in "autoplay", which waits until the element believes it can play through:
            // three seconds for an endless stream, kept as delay for the whole session. An explicit play order starts it on the
            // first data (measured on Google's receiver page in Chromium: 0.65 s behind instead of 3.0 s).
            orderedSession = status.mediaSessionID
            NPLog.record("cast.play.ordered", ["afterMs": Int((uptime - loadedAt) * 1000)])
            _ = client.play()
        }
        if state == .playing { startLiveWatch(); if !playbackReported { playbackReported = true; onPlayback?() } }
        guard state == .idle, status.mediaSessionID != replacedSession else { return }
        switch route {
        case .frames, .mp4: break
        case .segments: if status.idleReason == .error { onError?(.cast) }
        case .direct:
            // An idle status that follows a new load belongs to the stream it replaced.
            guard uptime - loadedAt > 2 else { return }
            if status.idleReason == .error { trouble("error") } else if status.idleReason == .finished, started { trouble("ended") }
        }
    }
    private func trouble(_ reason: String) {
        let now = uptime
        guard now - lastTrouble >= 1 else { return }
        lastTrouble = now; NPLog.record("cast.direct.trouble", ["reason": reason, "started": started, "sinceLoadMs": Int((now - loadedAt) * 1000)])
        onDirectTrouble?(reason)
    }
    private func startLiveWatch() {
        guard liveTimer == nil else { return }
        lag = NPLiveLagTracker(); lagChecks = 0; ticks = 0
        liveTimer = Timer.scheduledTimer(withTimeInterval: 0.25, repeats: true) { [weak self] _ in self?.tick() }
    }
    private func stopLiveWatch() { liveTimer?.invalidate(); liveTimer = nil }
    private func tick() {
        if receiverApplication != nil { link.tick(); return }
        guard ownsSession, let session = context.sessionManager.currentCastSession, selected == session.device.uniqueID, let client = session.remoteMediaClient else { return }
        ticks += 1
        switch route {
        case .segments: if ticks % 4 == 0 { checkLive(client) }
        case .direct: checkDirect(client)
        case .frames, .mp4: break
        }
    }
    // Direct route, four times a second: is the picture moving, how far behind the newest picture is it, and what to ask for.
    private func checkDirect(_ client: GCKRemoteMediaClient) {
        let now = uptime
        // A fresh position even from a receiver that reports little: twice a second until the stream has started, then every 2 s.
        if ticks % (started ? 8 : 2) == 0 { _ = client.requestStatus() }
        guard let status = client.mediaStatus, status.mediaSessionID != replacedSession, status.playerState == .playing || status.playerState == .buffering, let newest = newestPicture?() else {
            if !started, now - loadedAt > Self.startTimeout { trouble("start") }
            return
        }
        let position = client.approximateStreamPosition()
        let step = position - lastPosition
        if step > 0.01 { lastAdvance = now; moving = lastPosition >= 0 && step < 1 ? moving + 1 : 0; lastPosition = position }
        // Started = the receiver itself reported a position that moved, twice. The SDK's approximate position advances with the
        // wall clock from the first PLAYING status, which the receiver sends before its element really plays.
        let reported = status.streamPosition
        if reported > lastReported + 0.05 { if lastReported >= 0 { reports += 1 }; lastReported = reported }
        if !started {
            if reports >= 2 { started = true; everStarted = true; NPLog.record("cast.direct.started", ["afterMs": Int((now - loadedAt) * 1000), "lagMs": Int(max(0, newest - position) * 1000)]) }
            else if now - loadedAt > Self.startTimeout { trouble("start") }
            return
        }
        let stalled = status.playerState == .buffering || status.playbackRate == 0 || now - lastAdvance > 1
        // Two measures. By the clock: newest picture produced minus the receiver's position, which holds when the receiver's
        // time line is the stream's (it was on Google's receiver page). By the receiver: the duration it reports for an endless
        // stream is what it has received, so duration minus position is what it holds ahead. If they disagree by more than
        // 1.5 s the time lines differ on this receiver and its own measure is used.
        let byClock = max(0, newest - position)
        let duration = status.mediaInformation?.streamDuration ?? .infinity
        let held = duration.isFinite && duration > 0 ? max(0, duration - status.streamPosition) : nil
        // The receiver's measure stops near 3.4 s (seen on its page): beyond 3 s only the clock is believed.
        let behind = held.map { $0 < 3 && abs(byClock - $0) > 1.5 ? $0 : byClock } ?? byClock
        heldLag = held ?? -1
        lastLag = behind
        if !stalled { window.count += 1; window.sum += behind; window.low = min(window.low, behind); window.high = max(window.high, behind) }
        switch control.sample(lag: behind, stalled: stalled, at: now) {
        case .rate(let rate):
            NPLog.record("cast.direct.rate", ["rate": Double(rate), "lagMs": Int(behind * 1000), "targetMs": Int(control.target * 1000)])
            _ = client.setPlaybackRate(rate)
        case .reload: trouble("reload")
        case .none: break
        }
        if ticks % 40 == 0 {
            let mean = window.count > 0 ? window.sum / Double(window.count) : behind
            NPLog.record("cast.direct.lag", ["meanMs": Int(mean * 1000), "minMs": Int((window.count > 0 ? window.low : behind) * 1000), "maxMs": Int(max(window.high, behind) * 1000),
                                             "heldMs": Int(heldLag * 1000), "targetMs": Int(control.target * 1000), "rate": Double(control.rate), "stalls": control.stalls, "loads": loads])
            window = (0, 0, .infinity, 0)
        }
    }
    // Segments route, once a second: a failed seek is not a session error, the next lag lines show its effect.
    private func checkLive(_ client: GCKRemoteMediaClient) {
        guard client.mediaStatus?.playerState == .playing else { return }
        let end = client.approximateLiveSeekableRangeEnd(), position = client.approximateStreamPosition()
        guard end != kGCKInvalidTimeInterval, end.isFinite, end > 0, position.isFinite else { return }
        let behind = end - position, ms = { (value: TimeInterval) in (value * 1000).rounded() / 1000 }
        lagChecks += 1; lastLag = max(0, behind)
        if lagChecks % 10 == 1 { NPLog.record("cast.live.lag", ["behind": ms(behind), "best": ms(lag.best ?? behind)]) }
        guard lag.sample(behind: behind, at: Date().timeIntervalSinceReferenceDate) else { return }
        NPLog.record("cast.live.resync", ["behind": ms(behind), "count": lag.resyncs])
        let options = GCKMediaSeekOptions(); options.seekToInfinite = true; options.resumeState = .play
        _ = client.seek(with: options)
    }
    // Only the load request has this delegate. A direct stream that the receiver refuses is a route to change, not a dead session.
    func request(_ request: GCKRequest, didFailWithError error: GCKError) {
        guard ownsSession else { return }
        NPLog.error("cast.request", error)
        // A load that a newer load replaced or cancelled did not fail.
        if error.code == GCKErrorCode.replaced.rawValue || error.code == GCKErrorCode.cancelled.rawValue { return }
        if route == .direct { trouble("load") } else { onError?(.cast) }
    }
    func sessionManager(_ sessionManager: GCKSessionManager, didFailToStart session: GCKCastSession, withError error: Error) {
        guard selected == session.device.uniqueID else { return }; NPLog.error("cast.session.start.failed", error); stopLiveWatch()
        // The RewindBox receiver could not be launched (not published, not registered for this device, no network): the
        // same device, at once, with Google's receiver.
        if receiverApplication != nil, !cancelling, let device = selectedDevice {
            NPLog.record("cast.receiver.unavailable", ["model": device.modelName ?? ""])
            NPCastMode.rememberReceiverFailed(model: device.modelName)
            closeReceiver()
            if launch(device, application: nil) { return }
        }
        selected = nil; selectedDevice = nil; receiverApplication = nil; ownsSession = false; cancelling = false; onError?(.cast)
    }
    func sessionManager(_ sessionManager: GCKSessionManager, didEnd session: GCKCastSession, withError error: Error?) {
        guard selected == session.device.uniqueID else { return }; NPLog.error("cast.session.ended", error); stopLiveWatch()
        // Ended to start again on Google's receiver, or the RewindBox receiver closed before it ever answered (its page could
        // not be loaded): Google's receiver, same device.
        let neverAnswered = receiverApplication != nil && link.caps == nil
        if relaunching || neverAnswered, !cancelling, let device = selectedDevice {
            if !relaunching { NPLog.record("cast.receiver.unavailable", ["reason": "ended", "model": device.modelName ?? ""]); NPCastMode.rememberReceiverFailed(model: device.modelName) }
            closeReceiver(); relaunching = false; ownsSession = false
            if launch(device, application: nil) { return }
        }
        closeReceiver(); relaunching = false
        selected = nil; selectedDevice = nil; receiverApplication = nil; ownsSession = false; cancelling = false; onError?(.network)
    }
    func stop() {
        onReady = nil; onPlayback = nil; onError = nil; onDirectTrouble = nil; newestPicture = nil; onReceiverEvent = nil
        if receiverApplication != nil, channel != nil { sendReceiver(["type": "stop"]) }
        closeReceiver(); relaunching = false
        stopLiveWatch()
        control = NPLagController(); window = (0, 0, .infinity, 0); lastTrouble = -.infinity; replacedSession = Int.min; everStarted = false; route = .segments
        loadedURL = nil; loads = 0; orderedSession = Int.min; started = false; lastLag = 0
        guard initialized else { return }
        let matches = context.sessionManager.currentCastSession?.device.uniqueID == selected
        context.sessionManager.currentCastSession?.remoteMediaClient?.remove(self)
        if matches && ownsSession { context.sessionManager.endSessionAndStopCasting(true) }
        if ownsSession { selected = nil; selectedDevice = nil; receiverApplication = nil; ownsSession = false; cancelling = false }
        else if selected != nil { cancelling = true }
    }
}
