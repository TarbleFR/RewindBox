// SPDX-License-Identifier: GPL-3.0-or-later
import UIKit

/// On-screen "Shake" control of the Wii touch layout. The donor nibs have no
/// shake control, so the overlay adds this one by code above the Wii pad.
/// Press, hold and release follow the other touch buttons; the overlay owns
/// what a press does (see DolphinTouchShakeHold).
final class DolphinShakeButton: UIButton {
  static let accessibilityIdentifierValue = "dolphinTouchShake"

  /// Returns false when the overlay refuses the press (no live Wii session).
  var onBegan: (() -> Bool)?
  var onEnded: (() -> Void)?
  var onCancelled: (() -> Void)?
  private let haptic = UIImpactFeedbackGenerator(style: .medium)

  override init(frame: CGRect) {
    super.init(frame: frame)
    let configuration = UIImage.SymbolConfiguration(pointSize: 22, weight: .semibold)
    let image = UIImage(systemName: "hand.wave.fill", withConfiguration: configuration) ??
      UIImage(systemName: "arrow.left.and.right", withConfiguration: configuration)
    setImage(image?.withRenderingMode(.alwaysTemplate), for: .normal)
    tintColor = .white
    layer.cornerRadius = DolphinShakeLayout.diameter / 2
    layer.borderWidth = 1.5
    layer.borderColor = UIColor(white: 1, alpha: 0.55).cgColor
    applyAppearance()
    isExclusiveTouch = false
    isAccessibilityElement = true
    accessibilityTraits = .button
    accessibilityIdentifier = Self.accessibilityIdentifierValue
    addTarget(self, action: #selector(pressed), for: [.touchDown, .touchDragEnter])
    addTarget(self, action: #selector(released), for: [.touchUpInside, .touchUpOutside, .touchDragExit])
    addTarget(self, action: #selector(cancelled), for: .touchCancel)
  }

  required init?(coder: NSCoder) { return nil }

  override var intrinsicContentSize: CGSize {
    // A fixed size: pressing never reflows the pad or this control.
    return CGSize(width: DolphinShakeLayout.diameter, height: DolphinShakeLayout.diameter)
  }

  override var isHighlighted: Bool {
    didSet { applyAppearance() }
  }

  private func applyAppearance() {
    backgroundColor = isHighlighted ? UIColor(white: 1, alpha: 0.38) : UIColor(white: 0, alpha: 0.45)
  }

  @objc private func pressed() {
    if onBegan?() == true { haptic.impactOccurred() }
  }

  @objc private func released() { onEnded?() }

  @objc private func cancelled() { onCancelled?() }

  /// VoiceOver activation is one shake: press, then a normal release, which
  /// keeps the inputs held for the minimum shake duration.
  override func accessibilityActivate() -> Bool {
    guard onBegan?() == true else { return false }
    onEnded?()
    return true
  }
}
