import UIKit
import GameController

@objc(DOLTouchOverlay) public class DolphinTouchOverlay: UIView {
  private let wii: Bool
  private var pad: TCView?
  private var layoutName = ""
  @objc public var sessionInputActive = false { didSet { refreshPhoneShake() } }
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
    shakeButton?.isHidden = !(wii && layoutName == "wii")
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
    layoutShakeButton()
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
