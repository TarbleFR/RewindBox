import Foundation
import Darwin

/// Versioned additions to the existing owned-session ABI. Libraries and all
/// their runtime callbacks remain loaded for the lifetime of this process.
final class MeloNXRuntimeAPI {
    private typealias Version = @convention(c) () -> Int32
    private typealias StringCall = @convention(c) (UnsafePointer<CChar>?) -> Int32
    private typealias Mode = @convention(c) (Int32) -> Int32
    private typealias Content = @convention(c) (UnsafePointer<CChar>?, Int32, UnsafeMutablePointer<CChar>?, Int32) -> Int32
    private typealias Attach = @convention(c) (Int64, Int32, UnsafePointer<CChar>?, Int32) -> Int32
    private typealias Pad = @convention(c) (Int64, Int32) -> Int32
    private typealias Button = @convention(c) (Int64, Int32, Int32, Int32) -> Int32
    private typealias Stick = @convention(c) (Int64, Int32, Int32, Float, Float) -> Int32
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

    init(library: URL, frameworks: URL, root: URL) throws {
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
        configureJit = try symbol("neostation_melonx_configure_jit", Mode.self)
        contentFunction = try symbol("neostation_melonx_content", Content.self)
        contentProgressFunction = dlsym(handle, "neostation_melonx_content_progress").map { unsafeBitCast($0, to: Version.self) }
        cancelContentFunction = dlsym(handle, "neostation_melonx_cancel_content").map { unsafeBitCast($0, to: Version.self) }
        attachFunction = try symbol("neostation_melonx_input_attach", Attach.self)
        detachFunction = try symbol("neostation_melonx_input_detach", Pad.self)
        resetFunction = try symbol("neostation_melonx_input_reset", Pad.self)
        buttonFunction = try symbol("neostation_melonx_input_button", Button.self)
        stickFunction = try symbol("neostation_melonx_input_stick", Stick.self)
        guard runtimeVersion() == 1, inputVersion() == 1, libraryVersion() == 2 else { throw MeloNXHostError.incompatibleABI }
        guard frameworks.path.withCString({ configureNative($0) }) == 0 else {
            throw MeloNXHostError.load("Private MeloNX native dependencies could not be loaded")
        }
        try Self.prepareSDL(frameworks:frameworks)
        try session.initialize(root: root)
    }

    func prepareGraphics(_ settings: [String: Any], universalJit: Bool) throws {
        let data = try JSONSerialization.data(withJSONObject: settings, options: [.sortedKeys])
        guard let text = String(data: data, encoding: .utf8), text.utf8.count < 8192,
              configureJit(universalJit ? 1 : 0) == 0,
              text.withCString({ configureGraphics($0) }) == 0 else {
            throw MeloNXHostError.load("MeloNX rejected its JIT mode or graphics configuration")
        }
    }

    /// Call on the serial library worker, never the main thread.
    func content(path: String = "", operation: Int32) throws -> [String: Any] {
        var output = [CChar](repeating: 0, count: 65536)
        let status = path.withCString { contentFunction($0, operation, &output, Int32(output.count)) }
        guard status == 0 else { throw MeloNXHostError.load("MeloNX content ABI failed: \(status)") }
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
