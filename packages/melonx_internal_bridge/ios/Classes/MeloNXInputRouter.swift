import Foundation
import SwiftUI
import GameController
import CryptoKit

/// Routes both the original Melo-Controller and iOS controllers into the same
/// generation-bound native Npad ABI. Slots are integers, never object pointers.
final class MeloNXInputRouter: ObservableObject, Controller {
    @Published private(set) var controllerCount = 0
    @Published var hideWithController = UserDefaults.standard.object(forKey: "rewindbox.melonx.hideTouch") as? Bool ?? true {
        didSet {
            UserDefaults.standard.set(hideWithController, forKey: "rewindbox.melonx.hideTouch"); if hideWithController && controllerCount > 0 { releaseTouch() }
            journalState("hideWithController")
        }
    }
    private let legacyGameID: String
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
    // pad -> stick (1 left, 2 right) -> the source ("touch"/"physical") that last took it.
    private var stickOwners: [Int32: [Int32: String]] = [:]
    private(set) var controllers: [GCController] = []
    // Per-second "in=" counters of the performance journal and the "input"
    // "state" launch-journal line (MeloNXInputDiagnostics.swift).
    let counters = MeloNXInputCounters()
    private var journaled: String?

    init(runtime: MeloNXRuntimeAPI, generation: Int64, game: URL, titleID: String? = nil) {
        self.runtime = runtime; self.generation = generation
        legacyGameID = SHA256.hash(data: Data(game.standardizedFileURL.path.utf8)).map { String(format: "%02x", $0) }.joined()
        if let titleID, titleID.range(of:"^[0-9a-fA-F]{16}$",options:.regularExpression) != nil, titleID != "0000000000000000" {
            gameID = titleID.lowercased()
        } else { gameID = legacyGameID }
        // Standalone layouts already use title IDs. Preserve earlier embedded
        // path-based layouts when opening the same game with a stable identity.
        let layouts = FileManager.default.urls(for:.documentDirectory,in:.userDomainMask)[0].appendingPathComponent("MeloNX/controller_layouts")
        let legacyLayout = layouts.appendingPathComponent("\(legacyGameID).json")
        let stableLayout = layouts.appendingPathComponent("\(gameID).json")
        if gameID != legacyGameID, !FileManager.default.fileExists(atPath:stableLayout.path), FileManager.default.fileExists(atPath:legacyLayout.path) {
            try? FileManager.default.copyItem(at:legacyLayout,to:stableLayout)
        }
        gameName = game.deletingPathExtension().lastPathComponent
        _ = runtime.attach(generation, pad: 1, name: "MeloNX touch / player 1", player: 0)
        for name in [Notification.Name.GCControllerDidConnect, .GCControllerDidDisconnect] {
            observers.append(NotificationCenter.default.addObserver(forName: name, object: nil, queue: .main) { [weak self] _ in self?.reconnect() })
        }
        let counters = self.counters
        MeloNXPerfJournal.setInput(owner: self) { counters.take() }
        reconnect()
        journalState("start")
    }

    func buttonPressed(_ button: VirtualControllerButton) {
        if button.id == VirtualControllerButton.guide.id { onMenu?(); return }
        setButton(pad: 1, source: "touch", index: Int32(button.rawValue), pressed: true)
    }
    func buttonReleased(_ button: VirtualControllerButton) {
        setButton(pad: 1, source: "touch", index: Int32(button.rawValue), pressed: false)
    }
    func joystickMoved(position: CGPoint, right: Bool) {
        // Melo-Controller reports UIKit's downward-positive Y. Preserve the
        // original MeloNX BaseController's inversion for both touch sticks.
        setStick(pad: 1, source: "touch", stick: right ? 2 : 1, x: Float(position.x), y: Float(-position.y))
    }

    private func setButton(pad: Int32, source: String, index: Int32, pressed: Bool) {
        guard !closed, !suspended else { counters.dropped(); return }
        let before = buttons[pad]?.values.contains(where: { $0.contains(index) }) ?? false
        if pressed { buttons[pad, default: [:]][source, default: []].insert(index) }
        else { buttons[pad]?[source]?.remove(index) }
        let after = buttons[pad]?.values.contains(where: { $0.contains(index) }) ?? false
        if before != after { counters.button(code: runtime.button(generation, pad: pad, button: index, pressed: after)) }
    }
    private func setStick(pad: Int32, source: String, stick: Int32, x: Float, y: Float) {
        guard x.isFinite, y.isFinite else { return }
        guard !closed, !suspended else { counters.dropped(); return }
        let previous = axes[pad]?[source]?[stick]
        axes[pad, default: [:]][source, default: [:]][stick] = (x, y)
        let values = axes[pad] ?? [:]
        let owner = Self.stickOwner(current: stickOwners[pad]?[stick], source: source, previous: previous, values: values, stick: stick)
        stickOwners[pad, default: [:]][stick] = owner
        let value = Self.stickValue(owner: owner, values: values, stick: stick)
        let code = runtime.stick(generation, pad: pad, stick: stick, x: value.0, y: value.1)
        counters.stick(source: source, stick: stick, value: (x, y), sent: value, code: code)
    }

    // Touch and the first controller share pad 1. The source that most recently
    // left rest owns a stick; a source that keeps moving while off rest (a held
    // or drifting physical stick) never takes it back from an active owner.
    // While the owner is at rest, another source off rest is used. Before this,
    // a physical stick off rest (|x|+|y| > 0.01 after its deadzone, e.g. a
    // drifting stick) overrode every touch value of that stick: the touch stick
    // was dead while the touch buttons worked.
    static func isOffRest(_ value: (Float, Float)) -> Bool { abs(value.0) + abs(value.1) > 0.01 }
    static func stickOwner(current: String?, source: String, previous: (Float, Float)?,
                           values: [String: [Int32: (Float, Float)]], stick: Int32) -> String? {
        guard isOffRest(values[source]?[stick] ?? (0, 0)) else { return current }
        if !isOffRest(previous ?? (0, 0)) { return source }
        guard let current, isOffRest(values[current]?[stick] ?? (0, 0)) else { return source }
        return current
    }
    static func stickValue(owner: String?, values: [String: [Int32: (Float, Float)]], stick: Int32) -> (Float, Float) {
        if let owner, let value = values[owner]?[stick], isOffRest(value) { return value }
        for source in ["touch", "physical"] where source != owner {
            if let value = values[source]?[stick], isOffRest(value) { return value }
        }
        return (0, 0)
    }

    func releaseTouch() {
        for index in buttons[1]?["touch"] ?? [] { setButton(pad: 1, source: "touch", index: index, pressed: false) }
        for stick in [Int32(1), Int32(2)] { setStick(pad: 1, source: "touch", stick: stick, x: 0, y: 0) }
    }
    func suspend(_ value: Bool) {
        guard !closed else { return }
        for pad in pads { runtime.reset(generation, pad: pad) }
        buttons.removeAll(); axes.removeAll(); stickOwners.removeAll(); suspended = value
        // Releasing a menu/editor never replays inputs held before it opened.
        // A resume follows every layout edit, mapping save and menu toggle.
        if !value { journalState("resume") }
    }
    func close() {
        guard !closed else { return }
        suspended = false; releaseTouch(); closed = true; epoch += 1
        MeloNXPerfJournal.setInput(owner: self, nil)
        for observer in observers { NotificationCenter.default.removeObserver(observer) }
        observers.removeAll()
        restoreHandlers.reversed().forEach { $0() }; restoreHandlers.removeAll()
        for pad in pads { runtime.reset(generation, pad: pad); runtime.detach(generation, pad: pad) }
        pads.removeAll(); buttons.removeAll(); axes.removeAll(); stickOwners.removeAll(); controllers.removeAll()
    }

    func reconnect() {
        guard !closed else { return }
        epoch += 1
        restoreHandlers.reversed().forEach { $0() }; restoreHandlers.removeAll()
        for pad in pads { runtime.reset(generation, pad: pad); if pad > 1 { runtime.detach(generation, pad: pad) } }
        pads = [1]; buttons.removeAll(); axes.removeAll(); stickOwners.removeAll()
        controllers = Array(GCController.controllers().filter { $0.extendedGamepad != nil }.prefix(8))
        controllerCount = controllers.count
        for (index, controller) in controllers.enumerated() {
            let slot = Int32(index + 1)
            if slot > 1 { guard runtime.attach(generation, pad: slot, name: controller.vendorName ?? "Controller", player: Int32(index)) else { continue }; pads.insert(slot) }
            install(controller, pad: slot, mapping: mapping(for: controller))
        }
        if hideWithController && controllerCount > 0 { releaseTouch() }
        if journaled != nil { journalState("controllers") }
    }

    // One "input" "state" launch-journal line at session start, then only when
    // the state changed: the touch layout in effect for both sticks, the touch
    // overlay, each controller with its mapping origin and stick sources. The
    // detail starts with the reason word, never with a key=value entry (the
    // journal scrubber replaces a detail line that starts with one).
    func journalState(_ reason: String) {
        guard !closed else { return }
        let overlay = !hideWithController || controllerCount == 0
        var state = MeloNXInputDiagnostics.layout(gameID: gameID)
        state += "; overlay \(overlay ? "shown" : "hidden") hideWithController=\(hideWithController ? 1 : 0); controllers \(controllers.count)"
        for (index, controller) in controllers.enumerated() {
            let resolved = resolvedMapping(for: controller)
            let name = MeloNXInputDiagnostics.name(controller.vendorName ?? "?") + "|" + MeloNXInputDiagnostics.name(controller.productCategory)
            let sources = "L=\(resolved.mapping.leftStick.source.rawValue) R=\(resolved.mapping.rightStick.source.rawValue)"
            let deadzones = String(format: "%.2f/%.2f", resolved.mapping.leftStick.deadzone, resolved.mapping.rightStick.deadzone)
            state += "; pad\(index + 1) \(name) mapping=\(resolved.origin) \(sources) dz=\(deadzones)"
        }
        guard reason == "start" || state != journaled else { return }
        journaled = state
        MeloNXLaunchJournal.record("input", "state", detail: reason + "; " + state)
    }

    private func install(_ controller: GCController, pad: Int32, mapping: ControllerMapping) {
        guard let profile = controller.extendedGamepad else { return }
        let token = epoch
        let oldQueue = controller.handlerQueue
        controller.handlerQueue = .main
        restoreHandlers.append { controller.handlerQueue = oldQueue }
        // The game owns the pad: the menu's profile-wide handler would relay
        // every stick and trigger change to Flutter on the main thread for the
        // whole game. Restored at close; the menu also reclaims it afterwards.
        let menuHandler = profile.valueChangedHandler
        profile.valueChangedHandler = nil
        restoreHandlers.append { profile.valueChangedHandler = menuHandler }
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

    private func mappingURL(_ controller: GCController, identity: String? = nil) -> URL {
        let name = controller.productCategory + ":" + (controller.vendorName ?? "")
        let key = SHA256.hash(data: Data(name.utf8)).map { String(format:"%02x",$0) }.joined()
        return FileManager.default.urls(for:.documentDirectory,in:.userDomainMask)[0]
            .appendingPathComponent("MeloNX/controller_mappings/\(identity ?? gameID)/\(key).json")
    }
    func mapping(for controller: GCController) -> ControllerMapping { resolvedMapping(for: controller).mapping }
    // origin: "game" (this title), "legacy" (path-keyed), "global" (standalone export) or "standard".
    private func resolvedMapping(for controller: GCController) -> (mapping: ControllerMapping, origin: String) {
        for (url, origin) in [(mappingURL(controller), "game"), (mappingURL(controller, identity:legacyGameID), "legacy")] {
            guard let size = try? url.resourceValues(forKeys:[.fileSizeKey]).fileSize, size < 65536,
                  let data = try? Data(contentsOf:url),
                  let mapping = try? JSONDecoder().decode(ControllerMapping.self,from:data), Self.valid(mapping) else { continue }
            return (mapping, origin)
        }
        // The standalone app exports a global dictionary keyed by vendor name.
        // Keep a per-game override first, then use only a validated exact match.
        let global = FileManager.default.urls(for:.documentDirectory,in:.userDomainMask)[0].appendingPathComponent("MeloNX/controllerMappings.json")
        if let size = try? global.resourceValues(forKeys:[.fileSizeKey]).fileSize, size < 4 * 1024 * 1024,
           let data = try? Data(contentsOf:global),
           let mappings = try? JSONDecoder().decode([String:ControllerMapping].self,from:data),
           let name = controller.vendorName, let mapping = mappings[name], Self.valid(mapping) { return (mapping, "global") }
        return (ControllerMapping.standard(), "standard")
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
