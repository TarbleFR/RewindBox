import Foundation
import Darwin

enum MeloNXHostError: Error, CustomStringConvertible {
    case load(String), missingSymbol(String), incompatibleABI, initialize(Int32)
    case busy, prepare(Int64), run(Int32, String)

    var description: String {
        switch self {
        case .load(let message): return message
        case .missingSymbol(let name): return "Missing MeloNX ABI symbol: \(name)"
        case .incompatibleABI: return "Unsupported MeloNX bootstrap/session ABI"
        case .initialize(let status): return "MeloNX initialization failed: \(status)"
        case .busy: return "A MeloNX session is still active"
        case .prepare(let status): return "MeloNX preparation failed: \(status)"
        case .run(let status, let detail): return "MeloNX session failed (\(status)): \(detail)"
        }
    }
}

// Narrow, versioned C ABI. Resolves every symbol before invoking engine code.
// Loading/ABI compatibility alone never declares the Switch route available.
final class MeloNXNativeSessionAPI {
    private typealias Version = @convention(c) () -> Int32
    private typealias Initialize = @convention(c) (UnsafePointer<CChar>?) -> Int32
    private typealias Prepare = @convention(c) (UnsafePointer<CChar>?, UnsafePointer<CChar>?, Int32, Int32) -> Int64
    private typealias Generation = @convention(c) (Int64) -> Int32
    private typealias Pause = @convention(c) (Int64, Int32) -> Int32
    private typealias Layer = @convention(c) (UnsafeMutableRawPointer?) -> Void
    private typealias Diagnostic = @convention(c) (UnsafeMutablePointer<CChar>?, Int32) -> Int32
    private let initializeFunction: Initialize
    private let prepareFunction: Prepare
    private let runFunction: Generation
    private let stopFunction: Generation
    private let cancelFunction: Generation
    private let pauseFunction: Pause
    private let layerFunction: Layer
    private let stateFunction: Version
    private let errorFunction: Diagnostic
    // Intentionally retained for the entire process, including a rejected ABI.
    // Unloading NativeAOT would leave runtime threads/callbacks in unmapped code.
    private static let handlesLock = NSLock()
    private static var processHandles: [UnsafeMutableRawPointer] = []

    init(libraryURL: URL) throws {
        guard libraryURL.isFileURL,
              let handle = dlopen(libraryURL.path, RTLD_NOW | RTLD_LOCAL) else {
            throw MeloNXHostError.load(dlerror().map { String(cString: $0) } ?? "Cannot load MeloNX library")
        }
        Self.handlesLock.lock()
        Self.processHandles.append(handle)
        Self.handlesLock.unlock()
        func symbol<T>(_ name: String, _ type: T.Type) throws -> T {
            guard let address = dlsym(handle, name) else { throw MeloNXHostError.missingSymbol(name) }
            return unsafeBitCast(address, to: type)
        }
        let bootstrapVersion = try symbol("neostation_melonx_bootstrap_abi", Version.self)
        let sessionVersion = try symbol("neostation_melonx_session_abi", Version.self)
        initializeFunction = try symbol("neostation_melonx_initialize", Initialize.self)
        prepareFunction = try symbol("neostation_melonx_prepare", Prepare.self)
        runFunction = try symbol("neostation_melonx_run", Generation.self)
        stopFunction = try symbol("neostation_melonx_stop", Generation.self)
        cancelFunction = try symbol("neostation_melonx_cancel_prepared", Generation.self)
        pauseFunction = try symbol("neostation_melonx_pause", Pause.self)
        layerFunction = try symbol("set_native_window", Layer.self)
        stateFunction = try symbol("neostation_melonx_session_state", Version.self)
        errorFunction = try symbol("neostation_melonx_session_error", Diagnostic.self)
        guard bootstrapVersion() == 1 && sessionVersion() == 1 else { throw MeloNXHostError.incompatibleABI }
    }

    func initialize(root: URL) throws {
        let status = root.path.withCString { initializeFunction($0) }
        guard status == 0 else { throw MeloNXHostError.initialize(status) }
    }
    func prepare(game: URL, locale: String, width: Int32, height: Int32) -> Int64 {
        game.path.withCString { path in locale.withCString { prepareFunction(path, $0, width, height) } }
    }
    func run(_ generation: Int64) -> Int32 { runFunction(generation) }
    func stop(_ generation: Int64) -> Int32 { stopFunction(generation) }
    func cancel(_ generation: Int64) -> Int32 { cancelFunction(generation) }
    func pause(_ generation: Int64, _ paused: Bool) -> Int32 { pauseFunction(generation, paused ? 1 : 0) }
    func setLayer(_ layer: UnsafeMutableRawPointer?) { layerFunction(layer) }
    var state: Int32 { stateFunction() }
    var diagnostic: String {
        var buffer = [CChar](repeating: 0, count: 8192)
        _ = errorFunction(&buffer, Int32(buffer.count))
        return String(cString: buffer)
    }
}

// Owns only a session; JIT authorization, dependency verification, original
// controls and imports belong to the integration above this boundary.
final class MeloNXSessionHost {
    private static let quarantineLock = NSLock()
    private static var quarantinedHosts: [MeloNXSessionHost] = []
    private let api: MeloNXNativeSessionAPI
    private let queue = DispatchQueue(label: "com.neogamelab.neostation.melonx.session", qos: .userInitiated)
    private let lock = NSLock()
    private var generation: Int64?
    private var retainedSurface: AnyObject?

    init(api: MeloNXNativeSessionAPI) { self.api = api }
    var isSessionActive: Bool {
        lock.lock(); defer { lock.unlock() }
        return generation != nil
    }

    // The caller must have completed JIT/dependency/input preflight before this
    // method. Keep the surface alive through teardown, even after a UI close.
    func start(game: URL, locale: String, width: Int32, height: Int32,
               surface: AnyObject, pointer: UnsafeMutableRawPointer,
               prepared: ((Int64) -> Void)? = nil,
               beforeRun: (() -> Bool)? = nil,
               completion: @escaping (Result<Void, MeloNXHostError>) -> Void) throws {
        lock.lock()
        guard generation == nil else { lock.unlock(); throw MeloNXHostError.busy }
        let id = api.prepare(game: game, locale: locale, width: width, height: height)
        guard id > 0 else { lock.unlock(); throw MeloNXHostError.prepare(id) }
        generation = id
        retainedSurface = surface
        api.setLayer(pointer)
        lock.unlock()
        prepared?(id)
        queue.async { [self] in
            let authorized = beforeRun?() ?? true
            let status: Int32
            if authorized { status = api.run(id) }
            else {
                let cancelled = api.cancel(id) == 0
                // Stop may have arrived during JIT preflight. The owned
                // coordinator drains that prepared/stopping generation
                // without entering the guest; cancel alone cannot do so.
                let drained = cancelled || (api.state == 3 && api.run(id) == 0)
                if drained { api.setLayer(nil) }
                status = drained ? 1 : 3
            }
            let detail = authorized ? (status == 0 ? "" : api.diagnostic) : "JIT authorization or executable mapping failed"
            // Report inactive only after run has joined and released resources.
            // Retain self and the surface until this main-thread completion.
            DispatchQueue.main.async { [self] in
                lock.lock()
                guard generation == id else { lock.unlock(); return }
                let quarantined = api.state != 0
                if !quarantined {
                    generation = nil
                    retainedSurface = nil
                }
                lock.unlock()
                if quarantined {
                    // Native failure may leave guest users alive. Preserve
                    // activity and the layer even if the UI releases this host.
                    Self.quarantineLock.lock()
                    Self.quarantinedHosts.append(self)
                    Self.quarantineLock.unlock()
                }
                completion(status == 0 ? .success(()) : .failure(.run(status, detail)))
            }
        }
    }

    @discardableResult func requestStop() -> Bool {
        lock.lock(); defer { lock.unlock() }
        guard let id = generation else { return false }
        return api.stop(id) == 0
    }
    @discardableResult func setPaused(_ paused: Bool) -> Bool {
        lock.lock(); defer { lock.unlock() }
        guard let id = generation else { return false }
        return api.pause(id, paused) == 0
    }
}
