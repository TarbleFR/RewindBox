// SPDX-License-Identifier: GPL-3.0-or-later
import CoreMotion
import Foundation

/// One per live Wii Remote. Sensor processing and releases must not depend on
/// the UI queue: the emulator can keep polling inputs while UIKit is busy.
///
/// A gesture presses the three shake inputs as soon as the detector confirms
/// it and keeps them pressed while the phone keeps moving (Dolphin shakes the
/// emulated Wii Remote for as long as the inputs are held), then releases them
/// once the motion has settled, after at least the minimum pulse. Each later
/// deliberate shake is a new press after a short re-arm delay.
final class DolphinPhoneShake {
  private let manager = CMMotionManager()
  private let inputQueue = DispatchQueue(label: "NeoStation.Dolphin.PhoneShake", qos: .userInteractive)
  private let inputQueueKey = DispatchSpecificKey<Bool>()
  private let sensorQueue = OperationQueue()
  private let requestLock = NSLock()
  private var requestedActive = false
  private var requestGeneration: UInt64 = 0
  private let emit: (Bool) -> Void
  private let prepare: () -> Bool
  private let unavailable: () -> Void
  private let sensitivity: () -> DolphinShakeSensitivity
  private var detector = DolphinShakeDetector()
  private var active = false
  private var held = false
  private var pressedAt = 0.0
  private var releaseDeadline = 0.0
  private var generation: UInt64 = 0
  private var release: DispatchWorkItem?

  init(prepare: @escaping () -> Bool = { true },
       unavailable: @escaping () -> Void = {},
       sensitivity: @escaping () -> DolphinShakeSensitivity = { DolphinShakeSensitivity.stored() },
       emit: @escaping (Bool) -> Void) {
    self.emit = emit
    self.prepare = prepare
    self.unavailable = unavailable
    self.sensitivity = sensitivity
    inputQueue.setSpecific(key: inputQueueKey, value: true)
    sensorQueue.name = "NeoStation.Dolphin.PhoneShake.Sensor"
    sensorQueue.qualityOfService = .userInteractive
    sensorQueue.maxConcurrentOperationCount = 1
    sensorQueue.underlyingQueue = inputQueue
  }

  private func withInputQueue(_ body: () -> Void) {
    if DispatchQueue.getSpecific(key: inputQueueKey) == true { body() }
    else { inputQueue.sync(execute: body) }
  }

  func setActive(_ value: Bool) {
    precondition(Thread.isMainThread)
    requestLock.lock()
    guard value != requestedActive else { requestLock.unlock(); return }
    requestedActive = value
    requestGeneration &+= 1
    let ticket = requestGeneration
    requestLock.unlock()
    // Native launch can be waiting on main. Route setup must never make main
    // wait in turn for the emulator's serial runtime queue.
    inputQueue.async { [weak self] in
      guard let self = self, self.isCurrentRequest(ticket, active: value) else { return }
      if value { self.updateActive(ticket: ticket) }
      else { self.stopOnInputQueue() }
    }
  }

  private func isCurrentRequest(_ ticket: UInt64, active value: Bool) -> Bool {
    requestLock.lock()
    defer { requestLock.unlock() }
    return requestGeneration == ticket && requestedActive == value
  }

  /// The sensitivity preference changed. Applies to the next samples; a held
  /// shake keeps its current sustain level until released.
  func refreshSensitivity() {
    inputQueue.async { [weak self] in
      guard let self = self else { return }
      self.detector.sensitivity = self.sensitivity()
    }
  }

  func refreshRouting() {
    // Called after Dolphin has refreshed its effective input profile. A GC
    // notification can precede publication of the donor's new MFi device.
    // Re-qualification must not reset the sensor.
    inputQueue.async { [weak self] in
      guard let self = self else { return }
      self.requestLock.lock()
      let requested = self.requestedActive
      let ticket = self.requestGeneration
      self.requestLock.unlock()
      guard requested else { return }
      // A failed initial route may become valid after the donor publishes its
      // physical profile. Retry activation on the actual profile refresh.
      if !self.active { self.updateActive(ticket: ticket); return }
      // Preparation can wait on native configuration work. Never lengthen a
      // held shake while that serial runtime work is pending.
      self.releaseButtons()
      let ready = self.prepare()
      guard self.isCurrentRequest(ticket, active: true) else { return }
      if !ready { self.stopOnInputQueue() }
    }
  }

  private func updateActive(ticket: UInt64) {
    if active { stopOnInputQueue() }
    guard manager.isDeviceMotionAvailable else { unavailable(); return }
    guard prepare() else { return }
    guard isCurrentRequest(ticket, active: true) else { return }
    generation = ticket
    active = true
    detector = DolphinShakeDetector(sensitivity: sensitivity())
    manager.deviceMotionUpdateInterval = 1.0 / 100.0
    manager.startDeviceMotionUpdates(to: sensorQueue) { [weak self] motion, error in
      guard let self = self, self.active, self.generation == ticket,
            self.isCurrentRequest(ticket, active: true) else { return }
      guard error == nil, let motion = motion else { self.unavailable(); self.stop(); return }
      // Drop a backlog on the sensor queue; UI stalls do not delay this queue.
      let now = ProcessInfo.processInfo.systemUptime
      let age = now - motion.timestamp
      guard age >= -0.05, age < DolphinPhoneShakePolicy.freshness else { return }
      let a = motion.userAcceleration
      switch self.detector.sample(x: a.x, y: a.y, z: a.z, timestamp: motion.timestamp) {
      case .none:
        return
      case .press:
        self.requestLock.lock()
        guard self.requestGeneration == ticket && self.requestedActive else {
          self.requestLock.unlock()
          self.detector.released(at: now)
          return
        }
        self.held = true
        self.emit(true)
        self.requestLock.unlock()
        self.pressedAt = now
        self.scheduleRelease(at: now + DolphinPhoneShakePolicy.pulseDuration, ticket: ticket)
      case .sustain:
        guard self.held else { return }
        if now - self.pressedAt >= DolphinPhoneShakePolicy.maximumHold {
          self.releaseButtons()
          return
        }
        let deadline = max(self.pressedAt + DolphinPhoneShakePolicy.pulseDuration,
                           now + DolphinPhoneShakePolicy.settleDuration)
        // Reschedule only for a meaningfully later deadline: 100 Hz samples
        // must not create a timer each.
        if deadline > self.releaseDeadline + 0.02 { self.scheduleRelease(at: deadline, ticket: ticket) }
      }
    }
  }

  /// Runs on the input queue. The release never depends on the UI run loop,
  /// and never on further sensor samples: a stalled sensor still releases.
  private func scheduleRelease(at deadline: Double, ticket: UInt64) {
    release?.cancel()
    let work = DispatchWorkItem { [weak self] in
      guard let self = self, self.generation == ticket else { return }
      self.releaseButtons()
    }
    release = work
    releaseDeadline = deadline
    let delay = max(0, deadline - ProcessInfo.processInfo.systemUptime)
    inputQueue.asyncAfter(deadline: .now() + delay, execute: work)
  }

  private func releaseButtons() {
    release?.cancel()
    release = nil
    releaseDeadline = 0
    if held { held = false; emit(false) }
    detector.released(at: ProcessInfo.processInfo.systemUptime)
  }

  func stop() {
    requestLock.lock()
    requestedActive = false
    requestGeneration &+= 1
    requestLock.unlock()
    if DispatchQueue.getSpecific(key: inputQueueKey) == true { stopOnInputQueue() }
    else { inputQueue.async { [weak self] in self?.stopOnInputQueue() } }
  }

  private func stopOnInputQueue() {
    generation &+= 1
    active = false
    manager.stopDeviceMotionUpdates()
    releaseButtons()
    detector.reset()
  }

  deinit { withInputQueue { stopOnInputQueue() } }
}
