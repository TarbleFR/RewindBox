import UIKit
import GameController

@objc(DOLTouchOverlay) public class DolphinTouchOverlay: UIView {
  private let wii: Bool
  private var pad: TCView?
  private var layoutName = ""
  @objc public var sessionInputActive = false { didSet { refreshPhoneShake() } }
  // Build 484 touch layouts (NeoStation touch-controls editor). The overlay
  // keeps the DolphiniOS controls and inputs; DOLTouchLayout (Objective-C)
  // places each control with one transform from the stored layout. Called on
  // every layout pass: false after the controls' stock layout, true after the
  // Shake control's automatic placement.
  @objc public var layoutPassHandler: ((Bool) -> Void)?
  /// The editor shows every control, including hidden ones, faintly.
  @objc public var touchLayoutEditing = false {
    didSet {
      refreshTouchShake()
      setNeedsLayout()
    }
  }
  /// The stored layout hides the Wii Shake control.
  @objc public var shakeHiddenByLayout = false { didSet { refreshTouchShake() } }
  private var appActive = UIApplication.shared.applicationState == .active
  // Phone and touch shakes press the same first Wii Remote inputs. One owner
  // decides when the shake actually ends.
  private let shakeInput: DolphinShakeInput
  private let touchShake: DolphinTouchShakeHold
  private var shakeButton: DolphinShakeButton?
  private lazy var phoneShake = DolphinPhoneShake(
    prepare: { TCManagerInterface.preparePhoneShakeRouting() },
    unavailable: { TCManagerInterface.reportPhoneShakeSensorUnavailable() }) { [input = self.shakeInput] pressed in
    if pressed { input.press(.phone) } else { input.release(.phone) }
  }

  /// Translated by the session labels (DolphinShakeLocale on the Dart side).
  @objc public var shakeAccessibilityLabel: String? {
    didSet { shakeButton?.accessibilityLabel = shakeAccessibilityLabel }
  }
  @objc public var shakeAccessibilityHint: String? {
    didSet { shakeButton?.accessibilityHint = shakeAccessibilityHint }
  }

  public override var isHidden: Bool { didSet { refreshPhoneShake() } }
  public override var isUserInteractionEnabled: Bool { didSet { refreshPhoneShake() } }

  public override func didMoveToWindow() {
    super.didMoveToWindow()
    refreshPhoneShake()
  }

  @objc private func environmentChanged(_ notification: Notification) {
    guard Thread.isMainThread else {
      DispatchQueue.main.async { [weak self] in self?.environmentChanged(notification) }
      return
    }
    if notification.name == UIApplication.willResignActiveNotification { appActive = false }
    if notification.name == UIApplication.didBecomeActiveNotification { appActive = true }
    if notification.name == Notification.Name(DolphinPhoneShakePolicy.preferenceChanged) {
      // The toggle and the sensitivity share this notification; the detector
      // reads the new level on the sensor queue without restarting the sensor.
      phoneShake.refreshSensitivity()
    }
    if notification.name == NSNotification.Name.GCControllerDidConnect ||
       notification.name == NSNotification.Name.GCControllerDidDisconnect {
      // The default device/profile can change while the sensor stays enabled.
      // Re-qualify phone shake inputs for the new profile before accepting one.
      phoneShake.stop()
      // The game view also clears every touch input on a hot-plug.
      touchShake.cancelled()
    }
    refreshPhoneShake()
  }

  @objc public func refreshPhoneShakeRouting() {
    refreshPhoneShake()
    phoneShake.refreshRouting()
  }

  private func refreshPhoneShake() {
    guard Thread.isMainThread else {
      DispatchQueue.main.async { [weak self] in self?.refreshPhoneShake() }
      return
    }
    let preference = UserDefaults.standard.object(forKey: DolphinPhoneShakePolicy.preferenceKey)
    let enabled = (preference as? Bool) ?? true
    phoneShake.setActive(DolphinPhoneShakePolicy.acceptsInput(wii: wii,
      remoteLayout: layoutName == "wii", sessionRunning: sessionInputActive,
      visible: window != nil && !isHidden, touchEnabled: isUserInteractionEnabled,
      appActive: appActive, physicalController: !GCController.controllers().isEmpty,
      enabled: enabled))
    refreshTouchShake()
  }

  /// Touch Shake accepts a press only on the Wii Remote layout of a running,
  /// visible, interactive session in the foreground.
  private var touchShakeAvailable: Bool {
    return wii && layoutName == "wii" && sessionInputActive && window != nil && !isHidden &&
      isUserInteractionEnabled && appActive
  }

  private func refreshTouchShake() {
    shakeButton?.isHidden = !(wii && layoutName == "wii") || (shakeHiddenByLayout && !touchLayoutEditing)
    if !sessionInputActive || !isUserInteractionEnabled || !appActive || window == nil {
      // Pause (menu), background and game close: nothing may keep shaking.
      // The phone owner was invalidated just before and cannot press again.
      touchShake.cancelled()
      shakeInput.releaseAll()
    } else if !touchShakeAvailable {
      touchShake.cancelled()
    }
  }

  private func touchShakeBegan() -> Bool {
    guard touchShakeAvailable else { return false }
    touchShake.began()
    return true
  }

  // Runs on the phone input queue and the touch-hold release queue, not only
  // on main: it must not inherit UIView's main-actor isolation.
  nonisolated private static func emitShake(_ pressed: Bool) {
    for button in DolphinPhoneShakePolicy.shakeButtons {
      TCManagerInterface.setButtonStateFor(button,
        controller: DolphinPhoneShakePolicy.touchPort, state: pressed)
    }
  }

  @objc(initWithWii:) public init(wii: Bool) {
    self.wii = wii
    let input = DolphinShakeInput(emit: DolphinTouchOverlay.emitShake)
    shakeInput = input
    touchShake = DolphinTouchShakeHold(input: input)
    super.init(frame: .zero)
    backgroundColor = .clear
    isMultipleTouchEnabled = true
    if wii {
      // GameCube never gets this control and never touches port 4.
      let button = DolphinShakeButton(frame: CGRect(x: 0, y: 0,
        width: DolphinShakeLayout.diameter, height: DolphinShakeLayout.diameter))
      button.onBegan = { [weak self] in self?.touchShakeBegan() ?? false }
      button.onEnded = { [weak self] in self?.touchShake.ended() }
      button.onCancelled = { [weak self] in self?.touchShake.cancelled() }
      addSubview(button)
      shakeButton = button
    }
    updateExtension("Nunchuk")
    for name in [UIApplication.willResignActiveNotification, UIApplication.didBecomeActiveNotification,
                 NSNotification.Name.GCControllerDidConnect, NSNotification.Name.GCControllerDidDisconnect,
                 Notification.Name(DolphinPhoneShakePolicy.preferenceChanged)] {
      NotificationCenter.default.addObserver(self, selector: #selector(environmentChanged(_:)),
                                             name: name, object: nil)
    }
  }

  public required init?(coder: NSCoder) { return nil }

  deinit {
    phoneShake.stop()
    touchShake.cancelled()
    shakeInput.releaseAll()
    NotificationCenter.default.removeObserver(self)
  }

  @objc public func updateExtension(_ name: String) {
    let wanted = !wii ? "gc" : name == "Classic" ? "classic" : "wii"
    guard wanted != layoutName else { return }
    phoneShake.stop()
    touchShake.cancelled()
    layoutName = wanted
    pad?.removeFromSuperview()
    let view: TCView
    if wanted == "gc" { view = TCGameCubePad(frame: bounds) }
    else if wanted == "classic" { view = TCClassicWiiPad(frame: bounds) }
    else { view = TCWiiPad(frame: bounds) }
    view.port = wii ? 4 : 0
    view.autoresizingMask = [.flexibleWidth, .flexibleHeight]
    view.backgroundColor = .clear
    if let remote = view as? TCWiiPad { remote.setTouchIRMode(.follow) }
    // The pad stays first and below the Shake control.
    insertSubview(view, at: 0)
    pad = view
    refreshPhoneShake()
    setNeedsLayout()
  }

  public override func safeAreaInsetsDidChange() {
    super.safeAreaInsetsDidChange()
    setNeedsLayout()
  }

  public override func layoutSubviews() {
    super.layoutSubviews()
    pad?.frame = bounds
    if let remote = pad as? TCWiiPad {
      remote.recalculatePointerValues(new_rect: bounds, game_aspect: 16.0 / 9.0)
    }
    // Stock placement of the nib first (Auto Layout sets centre and bounds,
    // never the layout transforms), then the stored layout.
    pad?.layoutIfNeeded()
    layoutPassHandler?(false)
    shakeButton?.transform = .identity
    layoutShakeButton()
    layoutPassHandler?(true)
  }

  /// Layout key of the current pad: "gc", "wii" (Wii Remote and Nunchuk) or
  /// "wii-classic".
  @objc public var touchLayoutKey: String {
    return !wii ? "gc" : layoutName == "classic" ? "wii-classic" : "wii"
  }

  /// Movable controls of the current pad in drawing order: every button,
  /// stick and D-pad of the original layout (nested ones included).
  @objc public func touchLayoutControls() -> [UIView] {
    var controls: [UIView] = []
    func visit(_ view: UIView) {
      for child in view.subviews {
        if child is TCButton || child is TCJoystick || child is TCDirectionalPad {
          controls.append(child)
        } else {
          visit(child)
        }
      }
    }
    if let pad = pad { visit(pad) }
    return controls
  }

  /// The Wii Shake control while the Wii Remote layout shows it, else nil.
  @objc public var touchLayoutShakeControl: UIView? {
    guard wii && layoutName == "wii" else { return nil }
    return shakeButton
  }

  /// Stable identifier of a control in stored layouts.
  @objc public func touchLayoutIdentifier(_ control: UIView) -> String {
    if control === shakeButton { return "shake" }
    if let button = control as? TCButton { return "button.\(button.controllerButton)" }
    if let stick = control as? TCJoystick { return "stick.\(stick.joystickType)" }
    if let dpad = control as? TCDirectionalPad { return "dpad.\(dpad.directionalPadType)" }
    return "view.\(ObjectIdentifier(control).hashValue)"
  }

  /// 0 button, 1 D-pad, 2 stick, 3 trigger, 4 system (Shake).
  @objc public func touchLayoutKind(_ control: UIView) -> Int {
    if control === shakeButton { return 4 }
    if let button = control as? TCButton { return button.isAxis ? 3 : 0 }
    if control is TCDirectionalPad { return 1 }
    if control is TCJoystick { return 2 }
    return 0
  }

  /// Display name: the label printed on the controller, or "@key" for a
  /// translated name of the NeoStation touch-layout catalogue.
  @objc public func touchLayoutName(_ control: UIView) -> String {
    if control === shakeButton { return "@shake" }
    if control is TCDirectionalPad { return "@dpad" }
    if let stick = control as? TCJoystick {
      switch stick.joystickType {
      case TCButtonType.gcStickC.rawValue: return "@cStick"
      case TCButtonType.nunchukStick.rawValue: return "@nunchukStick"
      case TCButtonType.classicStickLeft.rawValue: return "@leftStick"
      case TCButtonType.classicStickRight.rawValue: return "@rightStick"
      default: return "@controlStick"
      }
    }
    guard let button = control as? TCButton else { return "?" }
    let names: [Int: String] = [
      0: "A", 1: "B", 2: "START", 3: "X", 4: "Y", 5: "Z", 20: "L", 21: "R",
      100: "A", 101: "B", 102: "\u{2212}", 103: "+", 104: "HOME", 105: "1", 106: "2",
      200: "C", 201: "Z",
      300: "a", 301: "b", 302: "x", 303: "y", 304: "\u{2212}", 305: "+", 306: "HOME",
      307: "ZL", 308: "ZR", 323: "L", 324: "R",
    ]
    return names[button.controllerButton] ?? "\(button.controllerButton)"
  }

  /// Releases every held touch control as if its finger had left: buttons
  /// send their release, sticks return to the centre, D-pads release all
  /// directions, the Shake hold ends. Used before hiding the controls, when
  /// the surface turns, before editing and at the end of a session.
  @objc public func cancelTouchInteractions() {
    for control in touchLayoutControls() {
      if let button = control as? TCButton {
        if button.isTracking || button.isHighlighted {
          button.cancelTracking(with: nil)
          button.isHighlighted = false
          button.buttonReleased()
        }
      } else if let stick = control as? TCJoystick {
        stick.resetToCenter()
      } else if let dpad = control as? TCDirectionalPad {
        dpad.releaseAllDirections()
      }
    }
    touchShake.cancelled()
  }

  /// Hit testing through each control's layout transform, so the touch area
  /// is the drawn control wherever it was moved or resized, including the
  /// Classic buttons nested in a container of the original nib.
  public override func hitTest(_ point: CGPoint, with event: UIEvent?) -> UIView? {
    guard isUserInteractionEnabled, !isHidden, alpha > 0.01, self.point(inside: point, with: event) else {
      return nil
    }
    if let shake = shakeButton, !shake.isHidden, shake.isUserInteractionEnabled, shake.alpha > 0.01,
       let hit = shake.hitTest(convert(point, to: shake), with: event) {
      return hit
    }
    for control in touchLayoutControls().reversed() {
      guard control.isUserInteractionEnabled, control.alpha > 0.01, !control.isHidden,
            control.superview?.isHidden == false else { continue }
      if let hit = control.hitTest(convert(point, to: control), with: event) { return hit }
    }
    return super.hitTest(point, with: event)
  }

  private func layoutShakeButton() {
    guard let button = shakeButton, !button.isHidden, let pad = pad else { return }
    pad.layoutIfNeeded()
    var column: [CGRect] = []
    var controls: [CGRect] = []
    func visit(_ view: UIView) {
      for child in view.subviews where !child.isHidden {
        if let control = child as? TCButton {
          let frame = control.convert(control.bounds, to: self)
          controls.append(frame)
          if DolphinShakeLayout.rightColumn.contains(control.controllerButton) { column.append(frame) }
        } else if child is TCJoystick || child is TCDirectionalPad {
          controls.append(child.convert(child.bounds, to: self))
        } else {
          visit(child)
        }
      }
    }
    visit(pad)
    button.frame = DolphinShakeLayout.frame(column: column, obstacles: controls,
                                            safe: bounds.inset(by: safeAreaInsets))
  }
}
