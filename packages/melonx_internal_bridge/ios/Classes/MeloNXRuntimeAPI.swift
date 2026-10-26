import Foundation
import Darwin

/// Versioned additions to the existing owned-session ABI. Libraries and all
/// their runtime callbacks remain loaded for the lifetime of this process.
final class MeloNXRuntimeAPI {
    private typealias Version = @convention(c) () -> Int32
    private typealias StringCall = @convention(c) (UnsafePointer<CChar>?) -> Int32
    private typealias MemoryOffer = @convention(c) (UnsafeMutableRawPointer?, UInt64) -> Int32
    private typealias MemorySnapshot = @convention(c) (UnsafeMutablePointer<UInt64>?, Int32) -> Int32
    private typealias PerformanceSnapshot = @convention(c) (Int64, UnsafeMutablePointer<Double>?, Int32) -> Int32
    private typealias PresentTarget = @convention(c) (Int64, Int32) -> Int32
    private typealias AudioPacing = @convention(c) (UnsafeMutablePointer<Int64>?, Int32) -> Int32
    private typealias Mode = @convention(c) (Int32) -> Int32
    private typealias Content = @convention(c) (UnsafePointer<CChar>?, Int32, UnsafeMutablePointer<CChar>?, Int32) -> Int32
    private typealias Attach = @convention(c) (Int64, Int32, UnsafePointer<CChar>?, Int32) -> Int32
    private typealias Pad = @convention(c) (Int64, Int32) -> Int32
    private typealias Button = @convention(c) (Int64, Int32, Int32, Int32) -> Int32
    private typealias Stick = @convention(c) (Int64, Int32, Int32, Float, Float) -> Int32
    private typealias Diagnostic = @convention(c) (UnsafeMutablePointer<CChar>?, Int32) -> Int32
    private static var preparedSDLPaths = Set<String>() // main-thread only
    private static func prepareSDL(frameworks: URL) throws {
        let prepare = {
            let path = frameworks.appendingPathComponent("MeloNXSDL3.framework/MeloNXSDL3").path
            if preparedSDLPaths.contains(path) { return }
            guard let handle = dlopen(path, RTLD_NOW | RTLD_LOCAL),
                  let readyAddress = dlsym(handle,"SDL_SetMainReady"),
                  let initAddress = dlsym(handle,"SDL_Init"),
                  let errorAddress = dlsym(handle,"SDL_GetError") else {
                throw MeloNXHostError.load("The private SDL iOS entry points are unavailable")
            }
            // UIKit owns main(). Prepare SDL's video/events on that same thread
            // before the background NativeAOT bootstrap initializes its drivers.
            // Both handles and SDL remain process-owned, like the managed input manager.
            let ready = unsafeBitCast(readyAddress,to:(@convention(c) () -> Void).self)
            let initialize = unsafeBitCast(initAddress,to:(@convention(c) (UInt32) -> Bool).self)
            let error = unsafeBitCast(errorAddress,to:(@convention(c) () -> UnsafePointer<CChar>?).self)
            ready()
            guard initialize(0x20) else {
                throw MeloNXHostError.load("SDL iOS video initialization failed: " + (error().map { String(cString:$0) } ?? "unknown error"))
            }
            preparedSDLPaths.insert(path)
        }
        if Thread.isMainThread { try prepare() } else { try DispatchQueue.main.sync(execute:prepare) }
    }
    let session: MeloNXNativeSessionAPI
    private let configureNative: StringCall
    private let configureGraphics: StringCall
    private let setAspectFunction: Pad
    private let memoryOffer: MemoryOffer
    private let memoryWithdraw: Version
    private let memorySnapshotFunction: MemorySnapshot
    private let performanceSnapshotFunction: PerformanceSnapshot?
    var providesPerformanceSnapshot: Bool { performanceSnapshotFunction != nil }
    private let presentTargetFunction: PresentTarget?
    private let audioPacingFunction: AudioPacing?
    /// The MoltenVK this process loaded: 0 source-built, 1 the standalone app's.
    let moltenVk: Int32
    private let configureJit: Mode
    private let contentFunction: Content
    private let contentProgressFunction: Version?
    private let cancelContentFunction: Version?
    func cancelContent() { _ = cancelContentFunction?() }
    func contentProgress() -> Int32 { contentProgressFunction?() ?? 0 }
    private let attachFunction: Attach
    private let detachFunction: Pad
    private let resetFunction: Pad
    private let buttonFunction: Button
    private let stickFunction: Stick
    private let diagnosticsFunction: Diagnostic
    private let prepareJitFunction: Version

    init(library: URL, frameworks: URL, root: URL, moltenVk requested: Int32 = 0) throws {
        MeloNXLaunchJournal.record("frameworks", "begin", detail:"Loading the private ARM64 MeloNX engine and resolving its ABI.")
        session = try MeloNXNativeSessionAPI(libraryURL: library)
        // session already owns a process-lifetime handle, including on error.
        guard let handle = dlopen(library.path, RTLD_NOW | RTLD_LOCAL) else {
            throw MeloNXHostError.load("Cannot resolve the embedded runtime")
        }
        func symbol<T>(_ name: String, _ type: T.Type) throws -> T {
            guard let value = dlsym(handle, name) else { throw MeloNXHostError.missingSymbol(name) }
            return unsafeBitCast(value, to: type)
        }
        let runtimeVersion = try symbol("neostation_melonx_runtime_abi", Version.self)
        let libraryVersion = try symbol("neostation_melonx_library_abi", Version.self)
        let inputVersion = try symbol("neostation_melonx_input_abi", Version.self)
        configureNative = try symbol("neostation_melonx_configure_native", StringCall.self)
        configureGraphics = try symbol("neostation_melonx_configure_graphics", StringCall.self)
        setAspectFunction = try symbol("neostation_melonx_set_aspect_ratio", Pad.self)
        memoryOffer = try symbol("neostation_melonx_memory_offer", MemoryOffer.self)
        memoryWithdraw = try symbol("neostation_melonx_memory_withdraw", Version.self)
        memorySnapshotFunction = try symbol("neostation_melonx_memory_snapshot", MemorySnapshot.self)
        // Optional: an older engine without it keeps the overlay RAM-only.
        performanceSnapshotFunction = dlsym(handle, "neostation_melonx_performance_snapshot").map { unsafeBitCast($0, to: PerformanceSnapshot.self) }
        presentTargetFunction = dlsym(handle, "neostation_melonx_set_present_target_fps").map { unsafeBitCast($0, to: PresentTarget.self) }
        audioPacingFunction = dlsym(handle, "neostation_melonx_audio_pacing").map { unsafeBitCast($0, to: AudioPacing.self) }
        configureJit = try symbol("neostation_melonx_configure_jit", Mode.self)
        contentFunction = try symbol("neostation_melonx_content", Content.self)
        contentProgressFunction = dlsym(handle, "neostation_melonx_content_progress").map { unsafeBitCast($0, to: Version.self) }
        cancelContentFunction = dlsym(handle, "neostation_melonx_cancel_content").map { unsafeBitCast($0, to: Version.self) }
        attachFunction = try symbol("neostation_melonx_input_attach", Attach.self)
        detachFunction = try symbol("neostation_melonx_input_detach", Pad.self)
        resetFunction = try symbol("neostation_melonx_input_reset", Pad.self)
        buttonFunction = try symbol("neostation_melonx_input_button", Button.self)
        stickFunction = try symbol("neostation_melonx_input_stick", Stick.self)
        diagnosticsFunction = try symbol("neostation_melonx_diagnostics", Diagnostic.self)
        prepareJitFunction = try symbol("neostation_melonx_prepare_jit", Version.self)
        let diagnosticsVersion = try symbol("neostation_melonx_diagnostics_abi", Version.self)
        guard runtimeVersion() == 1, inputVersion() == 1, libraryVersion() == 2, diagnosticsVersion() == 1 else { throw MeloNXHostError.incompatibleABI }
        // Optional, and only before configure_native: an engine without it
        // always loads the source-built MoltenVK.
        var variant: Int32 = 0
        if requested != 0, let address = dlsym(handle, "neostation_melonx_select_moltenvk") {
            let choose = unsafeBitCast(address, to: Mode.self)
            let status = choose(requested)
            if status == 0 { variant = requested }
            else { MeloNXLaunchJournal.record("frameworks", "moltenVk", code:Int64(status), detail:"MoltenVK \(requested) refused; the source-built MoltenVK is used.") }
        }
        moltenVk = variant
        let nativeStatus = frameworks.path.withCString({ configureNative($0) })
        guard nativeStatus == 0 else {
            throw MeloNXHostError.operation("frameworks",Int64(nativeStatus),diagnostics()["diagnostic"] as? String ?? "Private MeloNX native dependencies could not be loaded")
        }
        try Self.prepareSDL(frameworks:frameworks)
        MeloNXLaunchJournal.record("frameworks", "passed", detail:"Private SDL video and dependency closure initialized; MoltenVK \(variant == 1 ? "standalone MeloNX" : "source-built").")
        MeloNXLaunchJournal.record("nativeAot", "begin")
        try session.initialize(root: root)
        MeloNXLaunchJournal.record("nativeAot", "passed")
    }

    // This snapshot has its own native lock and may be polled while the library
    // worker is opening content or waiting for the JIT helper.
    func diagnostics() -> [String: Any] {
        var output = [CChar](repeating:0,count:524288)
        guard diagnosticsFunction(&output,Int32(output.count)) == 0 else { return [:] }
        let data = Data(bytes:output,count:output.prefix { $0 != 0 }.count)
        return (try? JSONSerialization.jsonObject(with:data)) as? [String:Any] ?? [:]
    }

    func offerMemory(_ address: UnsafeMutableRawPointer, bytes: UInt64) -> Bool { memoryOffer(address,bytes) == 0 }
    func withdrawMemory() -> Bool { memoryWithdraw() == 0 }
    func memorySnapshot() -> [String:Any] {
        var values = [UInt64](repeating:0,count:3)
        guard memorySnapshotFunction(&values,3) == 0 else { return [:] }
        return ["donorOfferedBytes":values[0],"donorUsedBytes":values[1],"donorAllocations":values[2]]
    }
    // The engine's own game FPS statistics; empty for a stale or stopped generation.
    func performanceSnapshot(generation: Int64) -> [String:Any] {
        guard let performanceSnapshotFunction else { return [:] }
        var values = [Double](repeating:0,count:3)
        guard performanceSnapshotFunction(generation,&values,3) == 0 else { return [:] }
        return ["gameFps":values[0],"gameFrameTimeMs":values[1],"fifoPercent":values[2]]
    }

    // The engine's cumulative audio pacing counters (EmbeddedAudioPacing order:
    // DSP periods, late, late ns, max late ns, skipped, buffers played,
    // starvations, starved ns, max starved ns); nil without the export.
    func audioPacing() -> [Int64]? {
        guard let audioPacingFunction else { return nil }
        var values = [Int64](repeating:0,count:9)
        guard audioPacingFunction(&values,9) == 0 else { return nil }
        return values
    }

    func setAspectRatio(_ value: Int32, generation: Int64) -> Bool {
        setAspectFunction(generation,value) == 0
    }
    // The standalone app's unbounded-present cap (its screen's maximum rate).
    func setPresentTargetFps(_ fps: Int32, generation: Int64) -> Bool {
        presentTargetFunction?(generation,fps) == 0
    }

    func prepareJit() throws {
        let status = prepareJitFunction()
        guard status == 0 else {
            let report = diagnostics()
            throw MeloNXHostError.prepare(Int64(status),report["diagnostic"] as? String ?? session.diagnostic)
        }
    }

    func prepareGraphics(_ settings: [String: Any], universalJit: Bool) throws {
        var engine = settings
        engine.removeValue(forKey:"showRamGraph") // presentation only, never a Core option
        engine.removeValue(forKey:"donateMemory") // acquired by the owned host lease
        let data = try JSONSerialization.data(withJSONObject: engine, options: [.sortedKeys])
        guard let text = String(data: data, encoding: .utf8), text.utf8.count < 8192 else {
            throw MeloNXHostError.operation("graphics",-1,"Invalid or oversized graphics configuration.")
        }
        let jitStatus = configureJit(universalJit ? 1 : 0)
        guard jitStatus == 0 else {
            throw MeloNXHostError.operation("jitMode",Int64(jitStatus),diagnostics()["diagnostic"] as? String ?? "JIT mode rejected")
        }
        let graphicsStatus = text.withCString({ configureGraphics($0) })
        guard graphicsStatus == 0 else {
            throw MeloNXHostError.operation("graphics",Int64(graphicsStatus),diagnostics()["diagnostic"] as? String ?? "Graphics configuration rejected")
        }
    }

    /// Call on the serial library worker, never the main thread.
    func content(path: String = "", operation: Int32) throws -> [String: Any] {
        var output = [CChar](repeating: 0, count: 65536)
        let status = path.withCString { contentFunction($0, operation, &output, Int32(output.count)) }
        guard status == 0 else { throw MeloNXHostError.operation("contentTransport",Int64(status),"Native content response failed.") }
        let data = Data(bytes: output, count: output.prefix { $0 != 0 }.count)
        guard let response = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw MeloNXHostError.load("Invalid MeloNX content response")
        }
        return response
    }
    func attach(_ id: Int64, pad: Int32, name: String, player: Int32) -> Bool {
        name.withCString { attachFunction(id, pad, $0, player) == 0 }
    }
    func detach(_ id: Int64, pad: Int32) { _ = detachFunction(id, pad) }
    func reset(_ id: Int64, pad: Int32) { _ = resetFunction(id, pad) }
    func button(_ id: Int64, pad: Int32, button: Int32, pressed: Bool) {
        _ = buttonFunction(id, pad, button, pressed ? 1 : 0)
    }
    func stick(_ id: Int64, pad: Int32, stick: Int32, x: Float, y: Float) {
        _ = stickFunction(id, pad, stick, max(-1, min(1, x)), max(-1, min(1, y)))
    }
}
