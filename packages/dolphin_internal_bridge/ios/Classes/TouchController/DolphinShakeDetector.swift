// SPDX-License-Identifier: GPL-3.0-or-later
import Foundation

/// Phone-shake sensitivity. User acceleration is gravity-free, in g.
/// `trigger` starts a shake; `sustain` keeps it held while the motion goes on.
/// Walking, aiming the pointer and taps stay below the medium trigger; a light,
/// deliberate flick reaches it. Low is the Build 440 behaviour (0.90 g).
enum DolphinShakeSensitivity: String, CaseIterable {
  case low, medium, high

  static let preferenceKey = "NeoStation.Dolphin.PhoneShake.Sensitivity"
  static let standard = DolphinShakeSensitivity.medium

  var trigger: Double {
    switch self {
    case .low: return 0.90
    case .medium: return 0.55
    case .high: return 0.35
    }
  }

  var sustain: Double {
    switch self {
    case .low: return 0.45
    case .medium: return 0.30
    case .high: return 0.20
    }
  }

  /// The stored preference, or the default for a missing or unknown value.
  static func named(_ raw: String?) -> DolphinShakeSensitivity {
    guard let raw = raw?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased(),
          let value = DolphinShakeSensitivity(rawValue: raw) else { return standard }
    return value
  }

  static func stored(_ defaults: UserDefaults = .standard) -> DolphinShakeSensitivity {
    return named(defaults.string(forKey: preferenceKey))
  }
}

/// Turns 100 Hz user-acceleration samples into press/sustain events.
/// A press needs `confirmSamples` consecutive samples at or above the trigger
/// (a 10 ms tap spike cannot press) or one sample at `strongFactor` × trigger
/// (a sharp flick presses at once). While held, every sample at or above the
/// sustain level reports `.sustain`; the owner releases when the motion has
/// settled. No title-specific cheats, physics edits, tilt steering or auto-repeat.
struct DolphinShakeDetector {
  enum Event { case none, press, sustain }

  static let confirmSamples = 2
  static let strongFactor = 2.0
  /// After a release, the next press waits this long so Dolphin reads the
  /// released inputs before the next gesture.
  static let rearmDelay = 0.08

  var sensitivity: DolphinShakeSensitivity
  private(set) var held = false
  private var confirmed = 0
  private var lastTimestamp = -Double.infinity
  private var releasedAt = -Double.infinity

  init(sensitivity: DolphinShakeSensitivity = .standard) {
    self.sensitivity = sensitivity
  }

  mutating func reset() { self = DolphinShakeDetector(sensitivity: sensitivity) }

  mutating func sample(x: Double, y: Double, z: Double, timestamp: Double) -> Event {
    guard x.isFinite, y.isFinite, z.isFinite, timestamp.isFinite,
          timestamp >= lastTimestamp else { return .none }
    lastTimestamp = timestamp
    let magnitude = (x*x + y*y + z*z).squareRoot()
    guard magnitude.isFinite else { return .none }
    if held { return magnitude >= sensitivity.sustain ? .sustain : .none }
    guard timestamp >= releasedAt + Self.rearmDelay else { confirmed = 0; return .none }
    if magnitude >= sensitivity.trigger * Self.strongFactor {
      confirmed = 0
      held = true
      return .press
    }
    if magnitude >= sensitivity.trigger {
      confirmed += 1
      guard confirmed >= Self.confirmSamples else { return .none }
      confirmed = 0
      held = true
      return .press
    }
    confirmed = 0
    return .none
  }

  /// The owner released the inputs (motion settled, maximum hold, routing
  /// refresh, stop). `timestamp` is in the sample clock (system uptime).
  mutating func released(at timestamp: Double) {
    held = false
    confirmed = 0
    releasedAt = timestamp.isFinite ? timestamp : lastTimestamp
  }
}

enum DolphinPhoneShakePolicy {
  static let preferenceKey = "NeoStation.Dolphin.PhoneShake.Enabled"
  static let preferenceChanged = "NeoStation.Dolphin.PhoneShakeChanged"
  static let touchPort = 4  // the existing first emulated Wiimote touchscreen
  static let shakeButtons = [132, 133, 134]
  /// Minimum press: a tap on the touch Shake button or a single strong sample.
  static let pulseDuration = 0.12
  /// A held shake is released this long after the last sample above the
  /// sustain level: the zero crossings inside one gesture never cut it.
  static let settleDuration = 0.10
  /// A continuous shake is released and re-armed after this long, so a noisy
  /// sensor can never hold the Wii Remote shaking for ever.
  static let maximumHold = 3.0
  /// Older samples are a backlog (UI stall, batched delivery), not a gesture.
  static let freshness = 0.25

  static func acceptsInput(wii: Bool, remoteLayout: Bool, sessionRunning: Bool,
                           visible: Bool, touchEnabled: Bool, appActive: Bool,
                           physicalController: Bool, enabled: Bool) -> Bool {
    // A gamepad hides the touch buttons, but the phone remains a valid motion
    // source. Menus still disable touchEnabled; background/Classic/GC stop it.
    return wii && remoteLayout && sessionRunning && (visible || physicalController) &&
           touchEnabled && appActive && enabled
  }
}
