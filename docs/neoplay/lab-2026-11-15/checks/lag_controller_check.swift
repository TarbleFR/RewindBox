import Foundation
func expect(_ c: Bool, _ m: String) { if !c { print("FAIL: \(m)"); exit(1) } }
// A receiver model: lag falls by (rate - 1) per second; below `floor` it stalls for 0.4 s and comes back 0.3 s later.
func simulate(start: Double, floor: Double, seconds: Double, outageAt: Double? = nil, outage: Double = 0) -> (c: NPLagController, lag: Double, log: [String], stalls: Int) {
    var c = NPLagController(); var lag = start; var rate: Float = 1; var t = 0.0; var log: [String] = []; var stallUntil = -1.0; var stalls = 0
    while t < seconds {
        if let o = outageAt, t >= o, t < o + outage { lag += 0.25; if c.sample(lag: lag, stalled: true, at: t) == .reload { lag = 0.6; rate = 1; log.append(String(format: "%.2fs reload", t)) }; t += 0.25; continue }
        let stalled = t < stallUntil
        if stalled { lag += 0.25 } else { lag -= Double(rate - 1) * 0.25; if lag < floor { stallUntil = t + 0.4; stalls += 1; lag += 0.3 } }
        switch c.sample(lag: lag, stalled: stalled, at: t) {
        case .rate(let r): rate = r; log.append(String(format: "%.2fs rate %.2f lag %.2f", t, r, lag))
        case .reload: lag = 0.6; rate = 1; log.append(String(format: "%.2fs reload", t))
        case .none: break
        }
        t += 0.25
    }
    return (c, lag, log, stalls)
}
// 1. starts 1.2 s behind (a receiver that buffers 1 s first), can hold 0.35: comes down near the target, no stall
var r = simulate(start: 1.2, floor: 0.35, seconds: 30)
print("A", r.log, String(format: "final lag %.2f target %.2f stalls %d", r.lag, r.c.target, r.stalls))
expect(r.stalls == 0 && r.lag < 0.75 && r.lag > 0.4 && r.c.rate == 1, "A converges without stall")
// 2. a receiver that cannot hold less than 0.8: the target rises after the first stall and stays above
r = simulate(start: 1.6, floor: 0.8, seconds: 60)
print("B", r.log.prefix(8), String(format: "final lag %.2f target %.2f stalls %d", r.lag, r.c.target, r.stalls))
expect(r.stalls <= 3 && r.c.target >= 0.7 && r.c.rate == 1, "B adapts: \(r.stalls) stalls, target \(r.c.target)")
// 3. a 2 s outage: recovered by rate, no reload
r = simulate(start: 0.55, floor: 0.35, seconds: 40, outageAt: 10, outage: 2)
print("C", r.log, String(format: "final lag %.2f reloads %d", r.lag, r.c.reloads))
expect(r.c.reloads == 0 && r.lag < 0.8, "C recovers by rate")
// 4. a 6 s outage: reload (stall longer than 5 s)
r = simulate(start: 0.55, floor: 0.35, seconds: 30, outageAt: 10, outage: 6)
print("D", r.log, String(format: "final lag %.2f reloads %d", r.lag, r.c.reloads))
expect(r.c.reloads == 1, "D reloads once")
// 5. steady: no command at all
r = simulate(start: 0.55, floor: 0.35, seconds: 120)
expect(r.log.isEmpty, "E steady: no command"); print("E target after 120 s:", r.c.target)
// 6. ladder
var l = NPBitrateLadder(nominal: 9_000_000)
expect(l.congested(at: 10) == 6_300_000 && l.congested(at: 10.5) == nil && l.congested(at: 13) == 4_410_000, "ladder down")
expect(l.tick(at: 20) == nil && l.tick(at: 44) == 5_071_500, "ladder up"); for t in stride(from: 80.0, to: 400, by: 31) { _ = l.tick(at: t) }; expect(l.current == 9_000_000, "ladder back to nominal")
print("OK")
