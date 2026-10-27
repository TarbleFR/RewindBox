import Foundation
import GameController

class GamepadsListener {
    var gamepads: [GCExtendedGamepad] = []
    var listener: ((Int, GCExtendedGamepad, GCControllerElement) -> Void)?

    init() {
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(joystickDidConnect),
            name: .GCControllerDidConnect,
            object: nil
        )
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(joystickDidDisconnect),
            name: .GCControllerDidDisconnect,
            object: nil
        )

        // GCControllerDidConnect is not replayed for devices that were already
        // connected before this listener was created. Seed the registry from
        // the controllers iOS currently knows about, then let the plugin run
        // additional delayed/foreground rescans to cover framework startup races.
        rescanConnectedControllers()
    }

    deinit {
        NotificationCenter.default.removeObserver(self)
    }

    /// Synchronizes NeoStation's registry with GameController's current state.
    ///
    /// This is intentionally safe to call repeatedly. It catches controllers
    /// connected before app launch, after Flutter plugin registration, and after
    /// returning from an emulator or the background without duplicating handlers.
    func rescanConnectedControllers() {
        let controllers = GCController.controllers()
        let connectedGamepads = controllers.compactMap { $0.extendedGamepad }

        gamepads.removeAll { known in
            !connectedGamepads.contains(where: { $0 == known })
        }

        for controller in controllers {
            register(controller)
        }
        refreshPlayerIndices()
    }

    /// Puts RewindBox's handler back on every connected pad.
    ///
    /// `valueChangedHandler` holds a single handler. Embedded engines take it
    /// over while a game runs (RPCS3's input bridge, SDL-based or prebuilt
    /// cores) and can leave it nil, or pointing at their finished session, when
    /// the game closes. The pad stays "known" here, so a rescan alone never
    /// reinstalled the handler and the menu stopped receiving the controller
    /// until it was reconnected. Called once the game session has ended; never
    /// while an engine owns the controller.
    func reclaimHandlers() {
        rescanConnectedControllers()
        for gamepad in gamepads {
            // Handlers must run on the main queue: they forward each event to
            // Flutter's channel, which only accepts platform-thread calls.
            gamepad.controller?.handlerQueue = .main
            installHandler(on: gamepad)
        }
    }

    @objc private func joystickDidConnect(notification: NSNotification) {
        guard let controller = notification.object as? GCController else { return }
        register(controller)
    }

    @objc private func joystickDidDisconnect(notification: NSNotification) {
        guard let controller = notification.object as? GCController,
              let disconnected = controller.extendedGamepad else { return }

        gamepads.removeAll(where: { $0 == disconnected })
        refreshPlayerIndices()
    }

    private func register(_ controller: GCController) {
        guard let gamepad = controller.extendedGamepad else { return }
        guard !gamepads.contains(where: { $0 == gamepad }) else { return }

        gamepads.append(gamepad)
        refreshPlayerIndices()
        installHandler(on: gamepad)
    }

    private func installHandler(on gamepad: GCExtendedGamepad) {
        // Resolve the index at event time instead of capturing the connection
        // index forever. If controller 1 disconnects, the remaining controllers
        // are re-indexed and continue reporting the same IDs as listGamepads().
        gamepad.valueChangedHandler = { [weak self] gamepad, element in
            guard let self,
                  let gamepadId = self.gamepads.firstIndex(of: gamepad) else {
                return
            }
            self.listener?(gamepadId, gamepad, element)
        }
    }

    private func refreshPlayerIndices() {
        for (index, gamepad) in gamepads.enumerated() {
            gamepad.controller?.playerIndex = toPlayerIndex(index: index)
        }
    }

    private func toPlayerIndex(index: Int) -> GCControllerPlayerIndex {
        switch index {
        case 0:
            return GCControllerPlayerIndex.index1
        case 1:
            return GCControllerPlayerIndex.index2
        case 2:
            return GCControllerPlayerIndex.index3
        case 3:
            return GCControllerPlayerIndex.index4
        default:
            return GCControllerPlayerIndex.indexUnset
        }
    }
}
