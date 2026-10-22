import Flutter
import Foundation
import UIKit
import AVFoundation

public final class MeloNXInternalBridgePlugin: NSObject, FlutterPlugin {
    private let libraryQueue = DispatchQueue(label:"com.neogamelab.neostation.melonx.library",qos:.userInitiated)
    private weak var presenter: UIViewController?
    private var runtime: MeloNXRuntimeAPI?
    private var host: MeloNXSessionHost?
    private var sessionView: MeloNXMetalSessionViewController?
    private var starting = false
    private var launchReply: FlutterResult?
    private var frameReady = false
    private var jitReady = false
    private var arenaReady = false
    private var lastFailure = ""
    private var previousAudio: (AVAudioSession.Category, AVAudioSession.Mode, AVAudioSession.CategoryOptions)?
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
        instance.presenter = registrar.viewController()
        registrar.addMethodCallDelegate(instance,channel:FlutterMethodChannel(name:"neostation/melonx_internal",binaryMessenger:registrar.messenger()))
        MeloNXJitBridgePlugin.register(with:registrar)
    }

    // Accessed only on libraryQueue. Success includes actual dependency loading
    // and native initialization; it never asserts guest execution or JIT.
    private func ensureRuntime() throws -> MeloNXRuntimeAPI {
        if let runtime { return runtime }
        guard let frameworks = Bundle.main.privateFrameworksURL else { throw MeloNXHostError.load("Frameworks directory missing") }
        let root = FileManager.default.urls(for:.documentDirectory,in:.userDomainMask)[0].appendingPathComponent("MeloNX")
        let runtime = try MeloNXRuntimeAPI(library:frameworks.appendingPathComponent("MeloNXCore.framework/MeloNXCore"),frameworks:frameworks,root:root)
        self.runtime = runtime
        return runtime
    }

    public func handle(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
        let arguments = call.arguments as? [String:Any] ?? [:]
        switch call.method {
        case "cancelJit":
            guard host?.isSessionActive != true else { result(false); return }
            MeloNXJitAbortTransaction(); result(true)
        case "isSessionActive": result(starting || host?.isSessionActive == true)
        case "stop": sessionView?.requestClose(); result(["success":true,"active":host?.isSessionActive == true])
        case "diagnostics":
            libraryQueue.async { [self] in
                do {
                    _ = try ensureRuntime()
                    DispatchQueue.main.async { [self] in result(["available":true,"initialized":true,"sessionActive":starting || host?.isSessionActive == true,"jitArenaReady":arenaReady,"gameplayVerified":false,"lastFailure":lastFailure]) }
                } catch { DispatchQueue.main.async { result(["available":false,"initialized":false,"diagnostic":String(describing:error)]) } }
            }
        case "metadata", "installFirmware", "reloadKeys", "firmwareInfo":
            guard !starting, host?.isSessionActive != true else { result(FlutterError(code:"busy",message:"Close the current game first.",details:nil)); return }
            let operation: Int32 = ["metadata":0,"installFirmware":1,"reloadKeys":2,"firmwareInfo":3][call.method]!
            let path = arguments["path"] as? String ?? ""
            libraryQueue.async { [self] in
                do { let response = try ensureRuntime().content(path:path,operation:operation); DispatchQueue.main.async { result(response) } }
                catch { DispatchQueue.main.async { result(FlutterError(code:"contentFailed",message:String(describing:error),details:nil)) } }
            }
        case "launch": launch(arguments,result:result)
        default: result(FlutterMethodNotImplemented)
        }
    }

    private func launch(_ arguments: [String:Any], result: @escaping FlutterResult) {
        guard !starting, host?.isSessionActive != true else { result(["success":false,"error":"busy"]); return }
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
        starting = true; launchReply = result; frameReady = false; jitReady = reuseArena
        MeloNXStrings.locale = locale
        libraryQueue.async { [self] in
            do {
                let runtime = try ensureRuntime()
                try runtime.prepareGraphics(settings,universalJit:universal)
                DispatchQueue.main.async { [self] in
                    guard isCurrent(token) else { return }
                    guard let presenter = topPresenter(), presenter.viewIfLoaded?.window != nil else { failLaunch("presentationUnavailable"); return }
                    let audio = AVAudioSession.sharedInstance()
                    previousAudio = (audio.category,audio.mode,audio.categoryOptions)
                    do { try audio.setCategory(.playback,mode:.default,options:[]); try audio.setActive(true) }
                    catch { failLaunch("audioUnavailable",diagnostic:String(describing:error)); return }
                    let host = MeloNXSessionHost(api:runtime.session); self.host = host
                    let view = MeloNXMetalSessionViewController(host:host,game:URL(fileURLWithPath:path),locale:locale,runtime:runtime,
                        beforeRun:{ [weak self] in
                            guard let self, self.isCurrent(token) else { return false }
                            if reuseArena { return true }
                            let authorized: Bool
                            if universal { authorized = MeloNXJitHasActiveCoreHandshake() && MeloNXJitConfirmCoreLoadHandoff() }
                            else { authorized = (MeloNXJitExecutableMappingProbe()["success"] as? Bool) == true }
                            guard authorized else { return false }
                            if backend == "builtin" {
                                DispatchQueue.global(qos:.userInitiated).async { [weak self] in
                                    var message: NSString?
                                    let detached = MeloNXJitWaitForDetach(120,&message)
                                    DispatchQueue.main.async { [weak self] in
                                        guard let self, self.isCurrent(token) else { return }
                                        if detached { self.jitReady = true; self.completeLaunchIfReady() }
                                        else { self.failLaunch("jitDetachFailed",diagnostic:message as String? ?? "Helper did not confirm detach"); self.sessionView?.requestClose() }
                                    }
                                }
                            } else { DispatchQueue.main.async { [weak self] in guard let self, self.isCurrent(token) else { return }; self.jitReady = true; self.completeLaunchIfReady() } }
                            return true
                        },firstFrame:{ [weak self] in guard let self, self.isCurrent(token) else { return }; self.frameReady = true; self.completeLaunchIfReady() }) { [weak self] outcome in
                            guard let self, self.isCurrent(token) else { return }
                            if self.launchReply != nil {
                                let detail: String
                                switch outcome { case .success: detail = "The game closed before launch authorization completed."; case .failure(let error): detail = error.description }
                                self.failLaunch("launchFailed",diagnostic:detail)
                            }
                            self.starting = false; self.sessionView = nil
                            if self.host?.isSessionActive != true { self.host = nil; self.restoreAudio() }
                            if case .failure(let error) = outcome { self.lastFailure = error.description }
                            _ = self.replaceToken()
                        }
                    sessionView = view; presenter.present(view,animated:true)
                }
            } catch { DispatchQueue.main.async { [self] in guard isCurrent(token) else { return }; failLaunch("runtimeUnavailable",diagnostic:String(describing:error)) } }
        }
    }

    private func completeLaunchIfReady() {
        guard frameReady, jitReady, let reply = launchReply else { return }
        // Cached authorization is process-local and backed by actual rendering
        // plus the helper's completed mapping transaction, never a preference.
        arenaReady = true; starting = false; launchReply = nil
        reply(["success":true,"firstMetalFramePresented":true,"jitMappingConfirmed":true,"pid":ProcessInfo.processInfo.processIdentifier])
    }
    private func failLaunch(_ code: String, diagnostic: String = "") {
        lastFailure = diagnostic
        let reply = launchReply; launchReply = nil; starting = false
        if host?.isSessionActive != true { restoreAudio(); MeloNXJitAbortTransaction() }
        reply?(["success":false,"error":code,"diagnostic":diagnostic])
    }
    private func topPresenter() -> UIViewController? {
        var top = presenter
        while let presented = top?.presentedViewController { top = presented }
        return top
    }
    private func restoreAudio() {
        guard let previousAudio else { return }; self.previousAudio = nil
        let audio = AVAudioSession.sharedInstance()
        do { try audio.setCategory(previousAudio.0,mode:previousAudio.1,options:previousAudio.2) }
        catch { NSLog("[MeloNX] Audio restoration failed: %@",String(describing:error)) }
    }
}
