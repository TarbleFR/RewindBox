import Flutter
import Foundation
import UIKit
import AVFoundation

public final class MeloNXInternalBridgePlugin: NSObject, FlutterPlugin {
    private let libraryQueue = DispatchQueue(label:"com.neogamelab.neostation.melonx.library",qos:.userInitiated)
    private let diagnosticsQueue = DispatchQueue(label:"com.neogamelab.neostation.melonx.diagnostics",qos:.utility)
    private var diagnosticsTimer: DispatchSourceTimer?
    private var nativeSequence: Int64 = 0 // diagnosticsQueue only
    private var diagnosticsChannel: FlutterMethodChannel?
    // Registration may precede attachment of the Flutter view controller.
    // Resolve it from the registrar at launch, never freeze its initial nil value.
    private var registrar: FlutterPluginRegistrar?
    private var runtime: MeloNXRuntimeAPI?
    private var host: MeloNXSessionHost?
    private var sessionView: MeloNXMetalSessionViewController?
    private var starting = false
    private var cancelling = false
    private var libraryMutation = false
    private var libraryRestartRequired = false
    private var contentProgress: (() -> Int32)?
    private var contentCancellation: (() -> Void)?
    private var launchReply: FlutterResult?
    private var frameReady = false
    private var jitReady = false
    private var arenaReady = false
    private var lastFailure = ""
    private var previousAudio: (AVAudioSession.Category, AVAudioSession.Mode, AVAudioSession.CategoryOptions, Double, TimeInterval)?
    private var audioObservers: [NSObjectProtocol] = []
    private static let audioOwnership = Notification.Name("RewindBox.MeloNX.AudioOwnership")
    private let tokenLock = NSLock()
    private var launchToken = UUID()

    private func isCurrent(_ token: UUID) -> Bool {
        tokenLock.lock(); defer { tokenLock.unlock() }; return launchToken == token
    }
    private func replaceToken() -> UUID {
        tokenLock.lock(); defer { tokenLock.unlock() }; launchToken = UUID(); return launchToken
    }

    public static func register(with registrar: FlutterPluginRegistrar) {
        let instance = MeloNXInternalBridgePlugin()
        instance.registrar = registrar
        instance.installAudioObservers()
        let channel = FlutterMethodChannel(name:"neostation/melonx_internal",binaryMessenger:registrar.messenger())
        instance.diagnosticsChannel = channel
        MeloNXLaunchJournal.sink = { [weak instance] event in instance?.diagnosticsChannel?.invokeMethod("launchDiagnostic",arguments:event) }
        registrar.addMethodCallDelegate(instance,channel:channel)
        MeloNXJitBridgePlugin.register(with:registrar)
    }

    private func startDiagnostics(_ runtime: MeloNXRuntimeAPI) {
        diagnosticsTimer?.cancel()
        let timer = DispatchSource.makeTimerSource(queue:diagnosticsQueue)
        timer.schedule(deadline:.now(),repeating:.milliseconds(300))
        timer.setEventHandler { [weak self] in
            guard let self else { return }
            self.drainDiagnostics(runtime)
        }
        diagnosticsTimer = timer; timer.resume()
    }

    private func drainDiagnostics(_ runtime: MeloNXRuntimeAPI) {
            let report = runtime.diagnostics()
            for event in report["events"] as? [[String:Any]] ?? [] {
                let sequence = (event["sequence"] as? NSNumber)?.int64Value ?? 0
                guard sequence > self.nativeSequence else { continue }
                self.nativeSequence = sequence
                MeloNXLaunchJournal.record(event["stage"] as? String ?? "native",
                    event["status"] as? String ?? "unknown",
                    code:(event["nativeStatus"] as? NSNumber)?.int64Value ?? 0,
                    detail:event["diagnostic"] as? String ?? "")
            }
    }

    // Accessed only on libraryQueue. Success includes actual dependency loading
    // and native initialization; it never asserts guest execution or JIT.
    private func ensureRuntime() throws -> MeloNXRuntimeAPI {
        if let runtime { return runtime }
        let documents = FileManager.default.urls(for:.documentDirectory,in:.userDomainMask)[0]
        guard !FileManager.default.fileExists(atPath: documents.appendingPathComponent("MeloNX/.rewindbox-transfer.json").path) else { throw MeloNXHostError.load("Library recovery required") }
        guard let frameworks = Bundle.main.privateFrameworksURL else { throw MeloNXHostError.load("Frameworks directory missing") }
        let root = FileManager.default.urls(for:.documentDirectory,in:.userDomainMask)[0].appendingPathComponent("MeloNX")
        let runtime = try MeloNXRuntimeAPI(library:frameworks.appendingPathComponent("MeloNXCore.framework/MeloNXCore"),frameworks:frameworks,root:root)
        self.runtime = runtime
        DispatchQueue.main.async { [weak self] in self?.contentProgress = { runtime.contentProgress() }; self?.contentCancellation = { runtime.cancelContent() } }
        return runtime
    }

    public func handle(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
        let arguments = call.arguments as? [String:Any] ?? [:]
        switch call.method {
        case "memoryEntitlements": result(MeloNXMemoryEntitlements())
        case "storageCapacity":
            do {
                let documents = FileManager.default.urls(for:.documentDirectory,in:.userDomainMask)[0]
                let attributes = try FileManager.default.attributesOfFileSystem(forPath:documents.path)
                result((attributes[.systemFreeSize] as? NSNumber)?.int64Value)
            } catch { result(FlutterError(code:"storageUnavailable",message:"Storage capacity unavailable",details:nil)) }
        case "contentProgress": result(contentProgress?() ?? 0)
        case "cancelContent": contentCancellation?(); result(nil)
        case "configureLaunchJournal":
            guard let path = arguments["path"] as? String, path.hasPrefix("/"),
                  URL(fileURLWithPath:path).lastPathComponent == "app.log" else {
                result(FlutterError(code:"invalidJournal",message:"Invalid application journal path.",details:nil)); return
            }
            MeloNXLaunchJournal.configure(path:path)
            libraryQueue.async { [self] in
                do {
                    let response = try ensureRuntime().content(path:path,operation:9)
                    DispatchQueue.main.async { result(response) }
                } catch { DispatchQueue.main.async { result(FlutterError(code:"journalUnavailable",message:String(describing:error),details:nil)) } }
            }
        case "beginLibraryMutation":
            guard !libraryMutation, !starting, host?.isSessionActive != true else { result(false); return }
            libraryMutation = true; result(true)
        case "endLibraryMutation": libraryMutation = false; result(nil)
        case "markLibraryRestartRequired": libraryRestartRequired = true; result(nil)
        case "cancelJit":
            guard host?.isSessionActive != true else { result(false); return }
            MeloNXJitAbortTransaction(); result(true)
        case "isSessionActive": result(starting || host?.isSessionActive == true)
        case "stop":
            if starting, sessionView == nil {
                if !cancelling {
                    cancelling = true; _ = replaceToken()
                    // Do not detach a debugger under a NativeAOT mapping call.
                    // The serial worker acknowledges cancellation after the
                    // current content/JIT step has returned safely.
                    libraryQueue.async { [self] in DispatchQueue.main.async { [self] in
                        cancelling = false; failLaunch("launchCancelled",stage:"close")
                    } }
                }
            } else { sessionView?.requestClose() }
            result(["success":true,"active":host?.isSessionActive == true])
        case "diagnostics":
            libraryQueue.async { [self] in
                do {
                    _ = try ensureRuntime()
                    DispatchQueue.main.async { [self] in result(["available":true,"initialized":true,"sessionActive":starting || host?.isSessionActive == true,"jitArenaReady":arenaReady,"gameplayVerified":false,"lastFailure":lastFailure]) }
                } catch { DispatchQueue.main.async { result(["available":false,"initialized":false,"diagnostic":String(describing:error)]) } }
            }
        case "metadata", "installFirmware", "reloadKeys", "firmwareInfo", "inspectUpdate", "inspectDlc", "storageInfo", "saveTarget", "launchPreflight":
            guard !starting, host?.isSessionActive != true else { result(FlutterError(code:"busy",message:"Close the current game first.",details:nil)); return }
            let operation: Int32 = ["metadata":0,"installFirmware":1,"reloadKeys":2,"firmwareInfo":3,"inspectUpdate":4,"inspectDlc":5,"storageInfo":6,"saveTarget":7,"launchPreflight":8][call.method]!
            var path = arguments["path"] as? String ?? ""
            if operation == 7 {
                guard let data = try? JSONSerialization.data(withJSONObject:arguments),
                      let request = String(data:data,encoding:.utf8) else { result(FlutterError(code:"invalidSave",message:"Invalid save association.",details:nil)); return }
                path = request
            } else if operation == 4 || operation == 5 {
                var addon: [String:Any] = ["path":path]
                if let title = arguments["titleId"] as? String { addon["titleId"] = title }
                guard (operation == 4 || addon["titleId"] != nil),
                      let data = try? JSONSerialization.data(withJSONObject:addon),
                      let request = String(data:data,encoding:.utf8) else { result(FlutterError(code:"invalidTitle",message:"A base-game title is required.",details:nil)); return }
                path = request
            }
            let requestPath = path
            libraryQueue.async { [self] in
                do { let response = try ensureRuntime().content(path:requestPath,operation:operation); DispatchQueue.main.async { result(response) } }
                catch { DispatchQueue.main.async { result(FlutterError(code:"contentFailed",message:String(describing:error),details:nil)) } }
            }
        case "launch": launch(arguments,result:result)
        default: result(FlutterMethodNotImplemented)
        }
    }

    private func launch(_ arguments: [String:Any], result: @escaping FlutterResult) {
        let access = MeloNXMemoryEntitlements()
        MeloNXLaunchJournal.record("entitlements", "begin")
        guard access["allowed"] as? Bool == true else { MeloNXLaunchJournal.record("entitlements","failed",detail:"Required entitlements are absent from this signed process."); result(["success":false,"error":"memoryEntitlements","stage":"entitlements","access":access]); return }
        MeloNXLaunchJournal.record("entitlements", "passed")
        guard !libraryRestartRequired else { result(["success":false,"error":"libraryRestartRequired"]); return }
        guard !libraryMutation, !starting, host?.isSessionActive != true else { result(["success":false,"error":"busy"]); return }
        guard let path = arguments["gamePath"] as? String, path.hasPrefix("/"),
              FileManager.default.isReadableFile(atPath:path),
              ["nro","nso","nsp","xci"].contains(URL(fileURLWithPath:path).pathExtension.lowercased()),
              let backend = arguments["jitBackend"] as? String, ["builtin","external"].contains(backend) else {
            result(["success":false,"error":"invalidLaunch"]); return
        }
        let locale = arguments["locale"] as? String ?? "en"
        let settings = arguments["graphics"] as? [String:Any] ?? [:]
        let reuseArena = arenaReady
        let token = replaceToken()
        let universal = backend == "builtin" && ProcessInfo.processInfo.operatingSystemVersion.majorVersion >= 26
        starting = true; cancelling = false; launchReply = result; frameReady = false; jitReady = reuseArena
        MeloNXStrings.locale = locale
        libraryQueue.async { [self] in
            var stage = "frameworks"
            do {
                guard isCurrent(token) else { return }
                let runtime = try ensureRuntime()
                DispatchQueue.main.async { [weak self] in self?.startDiagnostics(runtime) }
                stage = "contentPreflight"
                let preflight = try runtime.content(path:path,operation:8)
                guard preflight["success"] as? Bool == true else {
                    DispatchQueue.main.async { [self] in
                        guard isCurrent(token) else { return }
                        failLaunch(preflight["errorCode"] as? String ?? "invalidContent",
                            diagnostic:preflight["diagnostic"] as? String ?? "Native content preflight rejected the game.",
                            stage:preflight["stage"] as? String ?? "contentPreflight", nativeStatus:(preflight["nativeStatus"] as? NSNumber)?.int64Value ?? 1)
                    }
                    return
                }
                let titleID = preflight["titleId"] as? String
                guard isCurrent(token) else { return }
                try runtime.prepareGraphics(settings,universalJit:universal)
                stage = "jit"
                MeloNXLaunchJournal.record("jit", "begin")
                if !reuseArena {
                    MeloNXLaunchJournal.record("jitProbe", "begin", detail:universal ? "Checking the selected helper's core-mapping handshake." : "Checking executable RX/RW aliases for the RewindBox PID.")
                    let authorized = universal
                        ? (MeloNXJitHasActiveCoreHandshake() && MeloNXJitConfirmCoreLoadHandoff())
                        : ((MeloNXJitExecutableMappingProbe()["success"] as? Bool) == true)
                    guard authorized else { throw MeloNXHostError.prepare(-1,"The selected method did not authorize executable mappings for the RewindBox PID.") }
                    MeloNXLaunchJournal.record("jitProbe", "passed")
                }
                // Prepare both the shared cache and native signal mapping before
                // creating guest threads. This is the standalone MeloNX order.
                try runtime.prepareJit()
                if backend == "builtin", !reuseArena {
                    var message: NSString?
                    guard MeloNXJitWaitForDetach(120,&message) else {
                        throw MeloNXHostError.prepare(-1,message as String? ?? "The JIT helper did not confirm detach.")
                    }
                }
                MeloNXLaunchJournal.record("jit", "passed", detail:"Actual engine mapping verified; selected helper transaction completed.")
                // Cache actual one-time JIT success even if donor setup or UIKit fails.
                DispatchQueue.main.async { [self] in arenaReady = true }
                stage = "memory"
                try MeloNXMemoryLease.shared.prepare(runtime:runtime,enabled:settings["donateMemory"] as? Bool ?? true,
                    isCurrent:{ [weak self] in self?.isCurrent(token) == true })
                DispatchQueue.main.async { [self] in
                    // The arena and helper detach have succeeded independently
                    // of UIKit. A presentation failure must not reattach a helper
                    // waiting for the already-completed one-time arena handshake.
                    arenaReady = true
                    guard isCurrent(token) else { return }
                    jitReady = true
                    MeloNXLaunchJournal.record("presentation", "begin")
                    MeloNXPresentation.whenReady(
                        preferred: { [weak self] in self?.registrar?.viewController },
                        isCurrent: { [weak self] in self?.isCurrent(token) == true }
                    ) { [self] presenter in
                        guard isCurrent(token) else { return }
                        guard let presenter else {
                            failLaunch("presentationUnavailable", diagnostic:"No attached foreground application controller became available.", stage:"presentation")
                            return
                        }
                        do { try acquireAudio() }
                        catch { failLaunch("audioUnavailable",diagnostic:String(describing:error)); return }
                        let host = MeloNXSessionHost(api:runtime.session); self.host = host
                        let view = MeloNXMetalSessionViewController(host:host,game:URL(fileURLWithPath:path),locale:locale,runtime:runtime,titleID:titleID,settings:settings,
                            saveSettings:{ [weak self] updated, completion in
                                guard let self, self.isCurrent(token), let channel = self.diagnosticsChannel else { completion(false); return }
                                channel.invokeMethod("saveGameGraphics",arguments:["gamePath":path,"settings":updated]) { reply in
                                    completion((reply as? Bool) == true)
                                }
                            },
                            beforeRun:{ [weak self] in
                                guard let self else { return false }
                                // The frontend audio device may close during UIKit
                                // presentation. Reassert ownership after that handoff,
                                // immediately before the Apple backend is created.
                                let authorize = { () -> Bool in
                                    guard self.isCurrent(token), self.jitReady else { return false }
                                    do { try self.activateAudio(reason:"beforeRun"); return true }
                                    catch { MeloNXLaunchJournal.record("audio","failed",detail:String(describing:error)); return false }
                                }
                                return Thread.isMainThread ? authorize() : DispatchQueue.main.sync(execute:authorize)
                            },firstFrame:{ [weak self] in guard let self, self.isCurrent(token) else { return }; MeloNXLaunchJournal.record("firstFrame","passed",detail:"CAMetalDrawable presentedTime confirmed."); self.frameReady = true; self.completeLaunchIfReady() }) { [weak self] outcome in
                                guard let self else { return }
                                self.libraryQueue.async { _ = MeloNXMemoryLease.shared.retire(runtime:runtime) }
                                guard self.isCurrent(token) else { return }
                                if self.launchReply != nil {
                                    let detail: String
                                    switch outcome { case .success: detail = "The game closed before launch authorization completed."; case .failure(let error): detail = error.description }
                                    var status: Int64 = 0
                                    if case .failure(let error) = outcome {
                                        switch error { case .prepare(let code,_): status = code; case .run(let code,_): status = Int64(code); default: break }
                                    }
                                    let native = runtime.diagnostics()
                                    self.failLaunch(native["errorCode"] as? String ?? "launchFailed",diagnostic:detail,
                                        stage:native["stage"] as? String ?? "session",nativeStatus:status)
                                }
                                self.starting = false; self.sessionView = nil
                                if self.host?.isSessionActive != true { self.host = nil; self.restoreAudio() }
                                if case .failure(let error) = outcome { self.lastFailure = error.description }
                                self.diagnosticsTimer?.cancel(); self.diagnosticsTimer = nil
                                MeloNXLaunchJournal.record("close",self.host?.isSessionActive == true ? "quarantined" : "passed")
                                _ = self.replaceToken()
                            }
                        sessionView = view
                        presenter.present(view,animated:true) {
                            guard self.isCurrent(token), view.viewIfLoaded?.window != nil else { return }
                            MeloNXLaunchJournal.record("presentation", "passed", detail:"Embedded MeloNX view attached to the foreground application window.")
                        }
                    }
                }
            } catch {
                let native = self.runtime?.diagnostics() ?? [:]
                let nativeCode = native["errorCode"] as? String ?? ""
                var status: Int64 = 1
                if let failure = error as? MeloNXHostError {
                    switch failure {
                    case .prepare(let code,_): status = code
                    case .operation(let failedStage,let code,_): stage = failedStage; status = code
                    default: break
                    }
                }
                DispatchQueue.main.async { [self] in
                    guard isCurrent(token) else { return }
                    failLaunch(nativeCode.isEmpty ? (stage.hasPrefix("jit") ? "jitUnavailable" : "runtimeUnavailable") : nativeCode,diagnostic:String(describing:error),
                        stage:nativeCode.isEmpty ? stage : (native["stage"] as? String ?? stage),nativeStatus:status)
                }
            }
        }
    }

    private func completeLaunchIfReady() {
        guard frameReady, jitReady, let reply = launchReply else { return }
        // Launch success still requires a real frame, separately from the
        // process-local arena/detach proof cached before presentation.
        starting = false; launchReply = nil
        MeloNXLaunchJournal.record("launchResult", "passed", detail:"First Metal presentation and actual engine JIT authorization confirmed.")
        reply(["success":true,"firstMetalFramePresented":true,"jitMappingConfirmed":true,"pid":ProcessInfo.processInfo.processIdentifier])
    }
    private func failLaunch(_ code: String, diagnostic: String = "", stage: String = "launch", nativeStatus: Int64 = 1) {
        lastFailure = diagnostic
        if let runtime { libraryQueue.async { _ = MeloNXMemoryLease.shared.retire(runtime:runtime) } }
        if let runtime { diagnosticsQueue.sync { drainDiagnostics(runtime) } }
        let errorCode = code.isEmpty ? "launchFailed" : code
        MeloNXLaunchJournal.record(stage,"failed",code:nativeStatus,detail:errorCode + ": " + diagnostic)
        let reply = launchReply; launchReply = nil; starting = false
        if host?.isSessionActive != true { restoreAudio(); MeloNXJitAbortTransaction() }
        if host?.isSessionActive != true { diagnosticsTimer?.cancel(); diagnosticsTimer = nil }
        reply?(["success":false,"error":errorCode,"errorCode":errorCode,"stage":stage,"nativeStatus":nativeStatus,
            "diagnostic":diagnostic,"sessionActive":host?.isSessionActive == true,"requiresRestart":host?.isSessionActive == true || errorCode == "jitRestartRequired" || (MeloNXMemoryLease.shared.snapshot()["donorState"] as? String) == "retained"])
    }
    private func acquireAudio() throws {
        let audio = AVAudioSession.sharedInstance()
        if previousAudio == nil {
            previousAudio = (audio.category,audio.mode,audio.categoryOptions,
                             audio.preferredSampleRate,audio.preferredIOBufferDuration)
            NotificationCenter.default.post(name:Self.audioOwnership,object:nil,userInfo:["active":true])
        }
        try audio.setCategory(.playback,mode:.default,options:[])
        // Preferences are requests, not assumed hardware formats. Log the
        // actual route/rate/quantum after activation for internal diagnostics.
        do { try audio.setPreferredSampleRate(48000); try audio.setPreferredIOBufferDuration(256.0 / 48000.0) }
        catch { MeloNXLaunchJournal.record("audio","preferenceUnavailable",detail:String(describing:error)) }
        try activateAudio(reason:"acquired")
    }

    private func activateAudio(reason: String) throws {
        guard previousAudio != nil else { return }
        let audio = AVAudioSession.sharedInstance()
        if audio.category != .playback || audio.mode != .default || !audio.categoryOptions.isEmpty {
            try audio.setCategory(.playback,mode:.default,options:[])
        }
        try audio.setActive(true)
        let routes = audio.currentRoute.outputs.map { $0.portType.rawValue }.joined(separator:",")
        MeloNXLaunchJournal.record("audio",reason,detail:"Apple backend; rate: \(audio.sampleRate); I/O ms: \(audio.ioBufferDuration * 1000); category: \(audio.category.rawValue); route: \(routes)")
    }

    private func installAudioObservers() {
        let center = NotificationCenter.default
        audioObservers.append(center.addObserver(forName:UIApplication.didBecomeActiveNotification,object:nil,queue:.main) { [weak self] _ in
            guard let self, self.previousAudio != nil else { return }
            do { try self.activateAudio(reason:"foreground") }
            catch { MeloNXLaunchJournal.record("audio","failed",detail:String(describing:error)) }
        })
        audioObservers.append(center.addObserver(forName:AVAudioSession.routeChangeNotification,object:AVAudioSession.sharedInstance(),queue:.main) { [weak self] _ in
            guard let self, self.previousAudio != nil else { return }
            let audio = AVAudioSession.sharedInstance()
            guard audio.category != .playback || audio.mode != .default || !audio.categoryOptions.isEmpty else { return }
            do { try self.activateAudio(reason:"ownershipRestored") }
            catch { MeloNXLaunchJournal.record("audio","failed",detail:String(describing:error)) }
        })
        audioObservers.append(center.addObserver(forName:AVAudioSession.interruptionNotification,object:AVAudioSession.sharedInstance(),queue:.main) { [weak self] event in
            guard let self, self.previousAudio != nil,
                  (event.userInfo?[AVAudioSessionInterruptionTypeKey] as? NSNumber)?.uintValue == AVAudioSession.InterruptionType.ended.rawValue,
                  let raw = (event.userInfo?[AVAudioSessionInterruptionOptionKey] as? NSNumber)?.uintValue,
                  AVAudioSession.InterruptionOptions(rawValue:raw).contains(.shouldResume) else { return }
            do { try self.activateAudio(reason:"interruptionEnded") }
            catch { MeloNXLaunchJournal.record("audio","failed",detail:String(describing:error)) }
        })
    }

    deinit {
        for observer in audioObservers { NotificationCenter.default.removeObserver(observer) }
    }

    private func restoreAudio() {
        guard let previousAudio else { return }; self.previousAudio = nil
        let audio = AVAudioSession.sharedInstance()
        defer { NotificationCenter.default.post(name:Self.audioOwnership,object:nil,userInfo:["active":false]) }
        do {
            try audio.setCategory(previousAudio.0,mode:previousAudio.1,options:previousAudio.2)
            try audio.setPreferredSampleRate(previousAudio.3)
            try audio.setPreferredIOBufferDuration(previousAudio.4)
        }
        catch { NSLog("[MeloNX] Audio restoration failed: %@",String(describing:error)) }
    }
}
