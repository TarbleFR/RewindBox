// SPDX-License-Identifier: GPL-3.0-or-later
import CoreGraphics
import Foundation

/// The single owner of the first Wii Remote's shake inputs (Touchscreen
/// buttons 132-134 on port 4, already bound to Shake X/Y/Z by the Touch
/// profile and by the phone-shake routing). The phone gesture and the touch
/// Shake button both press them, so neither may end a shake the other one is
/// still holding: a 120 ms phone pulse ending must not release a finger held
/// on the button, and a lifted finger must not cut a phone pulse.
final class DolphinShakeInput {
  enum Source { case phone, touch }

  private let lock = NSLock()
  private var phone = false
  private var touch = false
  private let emit: (Bool) -> Void

  /// `emit` writes the three shake inputs. It runs under this object's lock,
  /// so the emitted sequence always matches the recorded state. It must not
  /// call back into this object.
  init(emit: @escaping (Bool) -> Void) {
    self.emit = emit
  }

  /// Always re-asserts the inputs: Dolphin's release_touches (menu, background,
  /// gamepad hot-plug) can zero them behind this object's back.
  func press(_ source: Source) {
    lock.lock()
    defer { lock.unlock() }
    if source == .phone { phone = true } else { touch = true }
    emit(true)
  }

  /// Releases the inputs only when this source held them and no other source
  /// still does.
  func release(_ source: Source) {
    lock.lock()
    defer { lock.unlock() }
    let held = source == .phone ? phone : touch
    guard held else { return }
    if source == .phone { phone = false } else { touch = false }
    if !phone && !touch { emit(false) }
  }

  /// End of input for the session (pause, background, close): nothing may keep
  /// the Wii Remote shaking.
  func releaseAll() {
    lock.lock()
    defer { lock.unlock() }
    guard phone || touch else { return }
    phone = false
    touch = false
    emit(false)
  }

  var isPressed: Bool {
    lock.lock()
    defer { lock.unlock() }
    return phone || touch
  }

  func isHeld(by source: Source) -> Bool {
    lock.lock()
    defer { lock.unlock() }
    return source == .phone ? phone : touch
  }
}

/// Press, hold and release of the touch Shake button. The shake lasts while the
/// finger stays down. A normal release keeps it for at least `minimumHold`
/// (the phone pulse length) so a quick tap or a VoiceOver activation still
/// produces a shake Dolphin detects. A cancellation (touch cancelled, menu,
/// background, game closed) releases at once and voids any pending release.
final class DolphinTouchShakeHold {
  private let input: DolphinShakeInput
  private let minimumHold: TimeInterval
  private let queue: DispatchQueue
  private let clock: () -> TimeInterval
  private let lock = NSLock()
  private var generation: UInt64 = 0
  private var pressedAt: TimeInterval?
  private var pending: DispatchWorkItem?

  init(input: DolphinShakeInput,
       minimumHold: TimeInterval = DolphinPhoneShakePolicy.pulseDuration,
       queue: DispatchQueue = DispatchQueue(label: "NeoStation.Dolphin.TouchShake", qos: .userInteractive),
       clock: @escaping () -> TimeInterval = { ProcessInfo.processInfo.systemUptime }) {
    self.input = input
    self.minimumHold = minimumHold
    self.queue = queue
    self.clock = clock
  }

  /// True from the press until the (possibly delayed) release.
  var isHeld: Bool {
    lock.lock()
    defer { lock.unlock() }
    return pressedAt != nil || pending != nil
  }

  func began() {
    lock.lock()
    defer { lock.unlock() }
    pending?.cancel()
    pending = nil
    generation &+= 1
    pressedAt = clock()
    input.press(.touch)
  }

  func ended() {
    lock.lock()
    guard let start = pressedAt else { lock.unlock(); return }
    pressedAt = nil
    let remaining = start + minimumHold - clock()
    guard remaining > 0, remaining.isFinite else {
      input.release(.touch)
      lock.unlock()
      return
    }
    generation &+= 1
    let ticket = generation
    let release = DispatchWorkItem { [weak self] in self?.finish(ticket) }
    pending = release
    lock.unlock()
    // Off the UI queue, like the phone pulse: a busy main thread must not
    // lengthen the shake.
    queue.asyncAfter(deadline: .now() + remaining, execute: release)
  }

  func cancelled() {
    lock.lock()
    defer { lock.unlock() }
    pending?.cancel()
    pending = nil
    generation &+= 1
    pressedAt = nil
    input.release(.touch)
  }

  private func finish(_ ticket: UInt64) {
    lock.lock()
    defer { lock.unlock() }
    guard ticket == generation, pending != nil else { return }
    pending = nil
    input.release(.touch)
  }

  deinit {
    pending?.cancel()
    input.release(.touch)
  }
}

/// Placement of the touch Shake control. The donor Wii pad nib anchors its
/// right column (Nunchuk Z, B, A) to the bottom-right corner and has no shake
/// control. The button goes above that column when it fits, otherwise beside
/// its top control, never over another touch control and never in the top
/// strip used by the system edge swipes and the menu buttons.
enum DolphinShakeLayout {
  static let diameter: CGFloat = 56
  static let spacing: CGFloat = 14
  static let topClearance: CGFloat = 64
  static let edgeInset: CGFloat = 16
  /// Nunchuk Z, Wii Remote B and A: the right column of the Wii pad.
  static let rightColumn: Set<Int> = [201, 101, 100]

  /// `column` and `obstacles` are control frames in the overlay's coordinates;
  /// `safe` is the overlay's safe area.
  static func frame(column: [CGRect], obstacles: [CGRect], safe: CGRect) -> CGRect {
    let size = diameter
    let allowed = CGRect(x: safe.minX + edgeInset, y: safe.minY + topClearance,
                         width: max(safe.width - 2 * edgeInset, 0),
                         height: max(safe.height - topClearance, 0))
    func clamped(_ x: CGFloat, _ y: CGFloat) -> CGRect {
      let left = allowed.width >= size ? min(max(x, allowed.minX), allowed.maxX - size) : allowed.minX
      let top = allowed.height >= size ? min(max(y, allowed.minY), allowed.maxY - size) : allowed.minY
      return CGRect(x: left, y: top, width: size, height: size)
    }
    let blockers = obstacles.filter(usable)
    var candidates: [CGRect] = []
    if let top = column.filter(usable).min(by: { $0.minY < $1.minY }) {
      candidates.append(clamped(top.midX - size / 2, top.minY - spacing - size))
      candidates.append(clamped(top.minX - spacing - size, top.midY - size / 2))
      candidates.append(clamped(top.midX - size / 2, allowed.minY))
    }
    candidates.append(clamped(allowed.maxX - size, allowed.minY))
    func overlap(_ rect: CGRect) -> CGFloat {
      let padded = rect.insetBy(dx: -spacing / 2, dy: -spacing / 2)
      return blockers.reduce(0) { total, blocker in
        let shared = padded.intersection(blocker)
        return shared.isNull ? total : total + shared.width * shared.height
      }
    }
    if let free = candidates.first(where: { overlap($0) == 0 }) { return free }
    return candidates.min(by: { overlap($0) < overlap($1) }) ?? clamped(allowed.maxX - size, allowed.minY)
  }

  private static func usable(_ rect: CGRect) -> Bool {
    return !rect.isNull && !rect.isInfinite && rect.minX.isFinite && rect.minY.isFinite &&
      rect.width.isFinite && rect.height.isFinite && rect.width > 0 && rect.height > 0
  }
}
