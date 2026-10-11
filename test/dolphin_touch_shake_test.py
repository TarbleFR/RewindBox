#!/usr/bin/env python3
"""Execute the production touch Shake arbiter, hold timing and placement policy.

Compiles DolphinShakeInput.swift with DolphinShakeDetector.swift (its policy
constants) and runs behaviour checks: press/hold/release, the 120 ms minimum
on a normal release, immediate cancellation, stale timers, phone and touch
sources sharing the same Wii Remote inputs, and the button placement. Requires
swiftc (macOS CI). Game acceptance on an iPhone remains unvalidated.
"""
from pathlib import Path
import json
import platform
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TOUCH = ROOT / 'packages/dolphin_internal_bridge/ios/Classes/TouchController'

MAIN = r'''
import CoreGraphics
import Foundation

var cases = 0
func expect(_ value: Bool, _ label: String) { precondition(value, label); cases += 1 }
func eventually(_ timeout: Double = 1, _ condition: () -> Bool) -> Bool {
  let until = ProcessInfo.processInfo.systemUptime + timeout
  while !condition() && ProcessInfo.processInfo.systemUptime < until { Thread.sleep(forTimeInterval: 0.001) }
  return condition()
}

final class Events {
  private let lock = NSLock()
  private var values: [(Bool, Double)] = []
  func append(_ value: Bool) {
    lock.lock(); values.append((value, ProcessInfo.processInfo.systemUptime)); lock.unlock()
  }
  var states: [Bool] { lock.lock(); defer { lock.unlock() }; return values.map { $0.0 } }
  var times: [Double] { lock.lock(); defer { lock.unlock() }; return values.map { $0.1 } }
  func clear() { lock.lock(); values = []; lock.unlock() }
}

// The production constants: first Wii Remote touchscreen, Shake X/Y/Z, 120 ms.
expect(DolphinPhoneShakePolicy.touchPort == 4, "first Wii Remote touchscreen port")
expect(DolphinPhoneShakePolicy.shakeButtons == [132, 133, 134], "Wii Remote Shake X/Y/Z inputs")
expect(DolphinPhoneShakePolicy.pulseDuration == 0.12, "minimum shake equals the phone pulse")

// Arbiter: one press per call (re-assert), one release when the last holder lets go.
let events = Events()
let input = DolphinShakeInput { events.append($0) }
input.release(.touch); input.releaseAll()
expect(events.states.isEmpty, "nothing held: no release written")
input.press(.touch)
expect(events.states == [true], "touch press")
input.press(.touch)
expect(events.states == [true, true], "re-assert survives Dolphin's release_touches")
input.press(.phone)
input.release(.phone)
expect(events.states == [true, true, true], "a phone pulse ending never releases a held touch shake")
expect(input.isPressed && input.isHeld(by: .touch) && !input.isHeld(by: .phone), "touch still holds")
input.release(.phone)
expect(events.states.count == 3, "a source that does not hold cannot release")
input.release(.touch)
expect(events.states == [true, true, true, false], "last holder releases")
input.press(.phone); input.press(.touch); input.release(.touch)
expect(events.states.suffix(2) == [true, true], "a lifted finger never cuts a phone pulse")
input.release(.phone)
expect(events.states.last == false && !input.isPressed, "phone pulse end releases")
input.press(.phone); input.press(.touch)
events.clear()
input.releaseAll()
expect(events.states == [false], "pause/background/close releases both sources at once")
input.releaseAll(); input.release(.phone); input.release(.touch)
expect(events.states == [false], "late releases after releaseAll write nothing")

// Hold: tap keeps the shake for the minimum; a long hold ends at finger-up.
events.clear()
let hold = DolphinTouchShakeHold(input: input)
hold.began()
expect(events.states == [true] && hold.isHeld, "touch down presses")
hold.ended()
expect(events.states == [true] && hold.isHeld, "quick tap is not released at once")
expect(eventually { events.states == [true, false] }, "quick tap released after the minimum")
let held = events.times[1] - events.times[0]
expect(held >= 0.115 && held < 0.6, "tap shake lasts at least 120 ms (measured \(held))")
expect(!hold.isHeld && !input.isPressed, "tap fully released")

events.clear()
hold.began()
Thread.sleep(forTimeInterval: 0.2)
expect(events.states == [true], "held finger keeps shaking past the minimum")
hold.ended()
expect(events.states == [true, false], "release after a long hold is immediate")

// Cancellation (touch cancelled, menu, background, close) is immediate.
events.clear()
hold.began(); hold.cancelled()
expect(events.states == [true, false] && !hold.isHeld, "cancel releases at once")
hold.began(); hold.ended(); hold.cancelled()
expect(events.states == [true, false, true, false], "cancel voids a pending minimum release")
Thread.sleep(forTimeInterval: 0.2)
expect(events.states.count == 4, "voided timer writes nothing later")
hold.ended(); hold.cancelled()
expect(events.states.count == 4, "release without a press writes nothing")

// A stale timer cannot release a new press.
events.clear()
hold.began(); hold.ended()
Thread.sleep(forTimeInterval: 0.05)
hold.began()
Thread.sleep(forTimeInterval: 0.2)
expect(events.states == [true, true] && hold.isHeld, "second press survives the first tap's timer")
hold.ended()
expect(eventually { events.states == [true, true, false] }, "second press released normally")

// Phone pulse during a touch hold, and touch tap during a phone pulse.
events.clear()
hold.began()
input.press(.phone)
DispatchQueue.global().asyncAfter(deadline: .now() + 0.12) { input.release(.phone) }
Thread.sleep(forTimeInterval: 0.25)
expect(events.states == [true, true], "phone pulse ending keeps the touch hold")
hold.cancelled()
expect(events.states == [true, true, false], "touch cancel releases when the phone is done")
events.clear()
input.press(.phone)
hold.began(); hold.ended()
Thread.sleep(forTimeInterval: 0.2)
expect(events.states == [true, true], "touch minimum ending keeps the phone pulse")
input.release(.phone)
expect(events.states == [true, true, false], "phone release ends it")

// The minimum release does not depend on the caller's run loop or main.
events.clear()
let custom = DispatchQueue(label: "test.touch-shake.release")
let manual = DolphinTouchShakeHold(input: input, minimumHold: 0.05, queue: custom)
manual.began(); manual.ended()
Thread.sleep(forTimeInterval: 0.15)
expect(events.states == [true, false], "release fires on its own queue while this thread sleeps")

// A clock jump cannot extend or shorten the hold beyond the requested minimum.
events.clear()
var now = 100.0
let stepped = DolphinTouchShakeHold(input: input, clock: { now })
stepped.began(); now += 1; stepped.ended()
expect(events.states == [true, false], "finger held longer than the minimum releases at once")

// Concurrent phone thread and touch thread: never two releases in a row,
// and the final state is released.
events.clear()
let group = DispatchGroup()
DispatchQueue.global().async(group: group) {
  for _ in 0..<300 { input.press(.phone); input.release(.phone) }
}
DispatchQueue.global().async(group: group) {
  for index in 0..<300 { hold.began(); if index % 2 == 0 { hold.cancelled() } else { hold.ended() } }
}
group.wait()
expect(eventually { !hold.isHeld }, "every touch press finished")
expect(!input.isPressed && events.states.last == false, "final state released")
let states = events.states
expect(!zip(states, states.dropFirst()).contains { !$0.0 && !$0.1 }, "never two releases in a row")

// Deinit with a pending release still releases.
events.clear()
var transient: DolphinTouchShakeHold? = DolphinTouchShakeHold(input: input)
transient!.began(); transient!.ended()
weak var weakHold = transient
transient = nil
expect(weakHold == nil, "no retention cycle")
expect(events.states == [true, false], "deinit releases a pending shake")
Thread.sleep(forTimeInterval: 0.2)
expect(events.states == [true, false], "no late write after deinit")

// Placement: landscape iPhone, donor-like right column (Z, B, A) anchored
// bottom-right, centre cluster to its left.
let safe = CGRect(x: 47, y: 0, width: 750, height: 369)
let z = CGRect(x: 713, y: 77, width: 64, height: 64)
let b = CGRect(x: 713, y: 161, width: 64, height: 64)
let a = CGRect(x: 713, y: 265, width: 64, height: 64)
let cluster = [CGRect(x: 634, y: 150, width: 64, height: 64), CGRect(x: 634, y: 234, width: 64, height: 64),
               CGRect(x: 555, y: 265, width: 64, height: 64), CGRect(x: 47, y: 241, width: 128, height: 128),
               CGRect(x: 47, y: 103, width: 128, height: 128)]
let controls = [z, b, a] + cluster
func valid(_ frame: CGRect, _ obstacles: [CGRect], _ area: CGRect) -> Bool {
  return frame.width == DolphinShakeLayout.diameter && frame.height == DolphinShakeLayout.diameter &&
    frame.minY >= area.minY + DolphinShakeLayout.topClearance && frame.maxY <= area.maxY &&
    frame.minX >= area.minX && frame.maxX <= area.maxX && !obstacles.contains { $0.intersects(frame) }
}
let landscape = DolphinShakeLayout.frame(column: [a, b, z], obstacles: controls, safe: safe)
expect(valid(landscape, controls, safe), "short landscape: inside the safe area, below the top strip, over no control \(landscape)")
expect(landscape.maxX <= z.minX && abs(landscape.midY - max(z.midY, safe.minY + 64 + 28)) < 1, "beside the column's top control when it cannot go above")
let tallSafe = CGRect(x: 0, y: 24, width: 1180, height: 796)
let tz = CGRect(x: 1080, y: 520, width: 64, height: 64)
let tb = CGRect(x: 1080, y: 604, width: 64, height: 64)
let ta = CGRect(x: 1080, y: 708, width: 64, height: 64)
let tall = DolphinShakeLayout.frame(column: [ta, tb, tz], obstacles: [ta, tb, tz], safe: tallSafe)
expect(valid(tall, [ta, tb, tz], tallSafe), "tall layout valid \(tall)")
expect(abs(tall.midX - tz.midX) < 0.5 && abs(tall.maxY - (tz.minY - DolphinShakeLayout.spacing)) < 0.5,
       "anchored right above the right column")
let withoutNib = DolphinShakeLayout.frame(column: [], obstacles: [], safe: safe)
expect(valid(withoutNib, [], safe) && abs(withoutNib.maxX - (safe.maxX - DolphinShakeLayout.edgeInset)) < 0.5,
       "without the donor nib: top-right of the safe area")
let blocked = DolphinShakeLayout.frame(column: [z], obstacles: [safe], safe: safe)
expect(blocked.width == 56 && safe.contains(blocked), "a fully covered screen still yields an on-screen control")
let weird = DolphinShakeLayout.frame(column: [CGRect(x: CGFloat.nan, y: 0, width: 10, height: 10), .null, .infinite],
                                     obstacles: [.null, CGRect(x: 0, y: 0, width: CGFloat.infinity, height: 1)], safe: safe)
expect(valid(weird, [], safe), "invalid frames are ignored")
let tiny = DolphinShakeLayout.frame(column: [z], obstacles: controls, safe: CGRect(x: 0, y: 0, width: 40, height: 40))
expect(tiny.width == 56 && tiny.minX.isFinite && tiny.minY.isFinite, "tiny safe area does not crash")

print("PASS: \(cases) touch Shake arbiter, hold/minimum/cancel/stale-timer, phone+touch and placement assertions; no device claim")
'''

if platform.system() != 'Darwin' or shutil.which('swiftc') is None:
    print('SKIP: production Swift execution requires swiftc (macOS CI: dolphin-motion-check)')
    raise SystemExit(0 if platform.system() != 'Darwin' else 1)

with tempfile.TemporaryDirectory() as tmp:
    folder = Path(tmp)
    (folder / 'main.swift').write_text(MAIN)
    binary = folder / 'touch-shake-test'
    subprocess.run(['swiftc', '-swift-version', '5', str(TOUCH / 'DolphinShakeDetector.swift'),
                    str(TOUCH / 'DolphinShakeInput.swift'), str(folder / 'main.swift'),
                    '-o', str(binary)], check=True)
    result = subprocess.run([str(binary)], text=True, capture_output=True, timeout=120)
    if result.returncode != 0:
        # A failed precondition traps (SIGTRAP); show its message instead of only the signal.
        print(result.stdout)
        print(result.stderr)
        raise SystemExit('touch shake harness failed with status ' + str(result.returncode))
    print(result.stdout)
    output = ROOT / 'build/dolphin-motion/touch-shake-tests.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({'productionSwiftExecuted': True, 'realDeviceValidated': False,
                                  'result': result.stdout.strip()}, indent=2) + '\n')
