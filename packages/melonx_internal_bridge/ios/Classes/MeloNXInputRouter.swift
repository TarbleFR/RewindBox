import Foundation
import SwiftUI
import GameController
import CryptoKit

/// Routes both the original Melo-Controller and iOS controllers into the same
/// generation-bound native Npad ABI. Slots are integers, never object pointers.
final class MeloNXInputRouter: ObservableObject, Controller {
    @Published private(set) var controllerCount = 0
    @Published var hideWithController = UserDefaults.standard.object(forKey: "rewindbox.melonx.hideTouch") as? Bool ?? true {
        didSet { UserDefaults.standard.set(hideWithController, forKey: "rewindbox.melonx.hideTouch"); if hideWithController && controllerCount > 0 { releaseTouch() } }
    }
    let gameID: String
    let gameName: String
    var onMenu: (() -> Void)?
    private let runtime: MeloNXRuntimeAPI
    private let generation: Int64
    private var closed = false
    private var suspended = false
    private var epoch = 0
    private var observers: [NSObjectProtocol] = []
    private var restoreHandlers: [() -> Void] = []
    private var pads: Set<Int32> = [1]
    private var buttons: [Int32: [String: Set<Int32>]] = [:]
    private var axes: [Int32: [String: [Int32: (Float, Float)]]] = [:]
    private(set) var controllers: [GCController] = []

    init(runtime: MeloNXRuntimeAPI, generation: Int64, game: URL) {
        self.runtime = runtime; self.generation = generation
        gameID = SHA256.hash(data: Data(game.standardizedFileURL.path.utf8)).map { String(format: "%02x", $0) }.joined()
        gameName = game.deletingPathExtension().lastPathComponent
        _ = runtime.attach(generation, pad: 1, name: "MeloNX touch / player 1", player: 0)
        for name in [Notification.Name.GCControllerDidConnect, .GCControllerDidDisconnect] {
            observers.append(NotificationCenter.default.addObserver(forName: name, object: nil, queue: .main) { [weak self] _ in self?.reconnect() })
        }
        reconnect()
    }

    func buttonPressed(_ button: VirtualControllerButton) {
        if button.id == VirtualControllerButton.guide.id { onMenu?(); return }
        setButton(pad: 1, source: "touch", index: Int32(button.rawValue), pressed: true)
    }
    func buttonReleased(_ button: VirtualControllerButton) {
        setButton(pad: 1, source: "touch", index: Int32(button.rawValue), pressed: false)
    }
    func joystickMoved(position: CGPoint, right: Bool) {
        setStick(pad: 1, source: "touch", stick: right ? 2 : 1, x: Float(position.x), y: Float(position.y))
    }

    private func setButton(pad: Int32, source: String, index: Int32, pressed: Bool) {
        guard !closed, !suspended else { return }
        let before = buttons[pad]?.values.contains(where: { $0.contains(index) }) ?? false
        if pressed { buttons[pad, default: [:]][source, default: []].insert(index) }
        else { buttons[pad]?[source]?.remove(index) }
        let after = buttons[pad]?.values.contains(where: { $0.contains(index) }) ?? false
        if before != after { runtime.button(generation, pad: pad, button: index, pressed: after) }
    }
    private func setStick(pad: Int32, source: String, stick: Int32, x: Float, y: Float) {
        guard !closed, !suspended, x.isFinite, y.isFinite else { return }
        axes[pad, default: [:]][source, default: [:]][stick] = (x, y)
        let physical = axes[pad]?["physical"]?[stick] ?? (0, 0)
        let value = abs(physical.0) + abs(physical.1) > 0.01 ? physical : (axes[pad]?["touch"]?[stick] ?? (0, 0))
        runtime.stick(generation, pad: pad, stick: stick, x: value.0, y: value.1)
    }

    func releaseTouch() {
        for index in buttons[1]?["touch"] ?? [] { setButton(pad: 1, source: "touch", index: index, pressed: false) }
        for stick: Int32 in [1, 2] { setStick(pad: 1, source: "touch", stick: stick, x: 0, y: 0) }
    }
    func suspend(_ value: Bool) {
        guard !closed else { return }
        for pad in pads { runtime.reset(generation, pad: pad) }
        buttons.removeAll(); axes.removeAll(); suspended = value
        // Releasing a menu/editor never replays inputs held before it opened.
    }
    func close() {
        guard !closed else { return }
        suspended = false; releaseTouch(); closed = true; epoch += 1
        for observer in observers { NotificationCenter.default.removeObserver(observer) }
        observers.removeAll()
        restoreHandlers.reversed().forEach { $0() }; restoreHandlers.removeAll()
        for pad in pads { runtime.reset(generation, pad: pad); runtime.detach(generation, pad: pad) }
        pads.removeAll(); buttons.removeAll(); axes.removeAll(); controllers.removeAll()
    }

    func reconnect() {
        guard !closed else { return }
        epoch += 1
        restoreHandlers.reversed().forEach { $0() }; restoreHandlers.removeAll()
        for pad in pads { runtime.reset(generation, pad: pad); if pad > 1 { runtime.detach(generation, pad: pad) } }
        pads = [1]; buttons.removeAll(); axes.removeAll()
        controllers = Array(GCController.controllers().filter { $0.extendedGamepad != nil }.prefix(8))
        controllerCount = controllers.count
        for (index, controller) in controllers.enumerated() {
            let slot = Int32(index + 1)
            if slot > 1 { guard runtime.attach(generation, pad: slot, name: controller.vendorName ?? "Controller", player: Int32(index)) else { continue }; pads.insert(slot) }
            install(controller, pad: slot, mapping: mapping(for: controller))
        }
        if hideWithController && controllerCount > 0 { releaseTouch() }
    }

    private func install(_ controller: GCController, pad: Int32, mapping: ControllerMapping) {
        guard let profile = controller.extendedGamepad else { return }
        let token = epoch
        let oldQueue = controller.handlerQueue
        controller.handlerQueue = .main
        restoreHandlers.append { controller.handlerQueue = oldQueue }
        let physical: [(PhysicalInput, GCControllerButtonInput?)] = [
            (.a,profile.buttonA),(.b,profile.buttonB),(.x,profile.buttonX),(.y,profile.buttonY),
            (.dpadUp,profile.dpad.up),(.dpadDown,profile.dpad.down),(.dpadLeft,profile.dpad.left),(.dpadRight,profile.dpad.right),
            (.leftShoulder,profile.leftShoulder),(.rightShoulder,profile.rightShoulder),(.leftTrigger,profile.leftTrigger),(.rightTrigger,profile.rightTrigger),
            (.leftStickButton,profile.leftThumbstickButton),(.rightStickButton,profile.rightThumbstickButton),
            (.menu,profile.buttonMenu),(.options,profile.buttonOptions),(.home,profile.buttonHome)]
        for (input, element) in physical {
            guard let element else { continue }
            let previous = element.valueChangedHandler
            restoreHandlers.append { element.valueChangedHandler = previous }
            element.valueChangedHandler = { [weak self] _, value, pressed in
                guard let self, !self.closed, self.epoch == token else { return }
                let down = input.isTrigger ? value >= mapping.triggerThreshold : pressed
                for target in mapping.emulatedButtons(for: input) {
                    if target.id == VirtualControllerButton.guide.id { if down { self.onMenu?() }; continue }
                    self.setButton(pad: pad, source: "physical", index: Int32(target.rawValue), pressed: down)
                }
            }
        }
        for (source, element) in [(PhysicalStick.left,profile.leftThumbstick),(.right,profile.rightThumbstick)] {
            let previous = element.valueChangedHandler
            restoreHandlers.append { element.valueChangedHandler = previous }
            element.valueChangedHandler = { [weak self] _, x, y in
                guard let self, !self.closed, self.epoch == token else { return }
                for (axis, configuration) in [(Int32(1),mapping.leftStick),(Int32(2),mapping.rightStick)] where configuration.source == source {
                    let value = configuration.apply(x:x,y:y)
                    self.setStick(pad:pad,source:"physical",stick:axis,x:value.x,y:value.y)
                }
            }
        }
    }

    private func mappingURL(_ controller: GCController) -> URL {
        let name = controller.productCategory + ":" + (controller.vendorName ?? "")
        let key = SHA256.hash(data: Data(name.utf8)).map { String(format:"%02x",$0) }.joined()
        return FileManager.default.urls(for:.documentDirectory,in:.userDomainMask)[0]
            .appendingPathComponent("MeloNX/controller_mappings/\(gameID)/\(key).json")
    }
    func mapping(for controller: GCController) -> ControllerMapping {
        let url = mappingURL(controller)
        guard let data = try? Data(contentsOf:url), data.count < 65536,
              let mapping = try? JSONDecoder().decode(ControllerMapping.self,from:data), Self.valid(mapping) else { return .standard() }
        return mapping
    }
    func save(_ mapping: ControllerMapping, for controller: GCController) throws {
        guard Self.valid(mapping) else { throw MeloNXHostError.load("Invalid controller mapping") }
        let url = mappingURL(controller)
        try FileManager.default.createDirectory(at:url.deletingLastPathComponent(),withIntermediateDirectories:true)
        try JSONEncoder().encode(mapping).write(to:url,options:.atomic)
        reconnect()
    }
    private static func valid(_ mapping: ControllerMapping) -> Bool {
        guard mapping.triggerThreshold.isFinite, (0...1).contains(mapping.triggerThreshold) else { return false }
        return [mapping.leftStick,mapping.rightStick].allSatisfy { $0.deadzone.isFinite && (0...0.9).contains($0.deadzone) && $0.range.isFinite && (0.1...2).contains($0.range) }
    }
    deinit { close() }
}
