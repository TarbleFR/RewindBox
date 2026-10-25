// Uses the same TASK_VM_INFO.phys_footprint measurement as MeloNX's original
// PerformanceOverlay (Stossy11), with a bounded history and explicit failures.
// The title row also shows the engine's game FPS when a live session reports it.
import UIKit

struct MeloNXMemoryPoint {
    let time: TimeInterval
    let bytes: UInt64?
}
struct MeloNXMemoryHistory {
    private(set) var points: [MeloNXMemoryPoint] = []
    private(set) var peak: UInt64?
    mutating func append(time: TimeInterval, bytes: UInt64?) {
        points.append(MeloNXMemoryPoint(time:time,bytes:bytes))
        if points.count > 120 { points.removeFirst(points.count - 120) }
        points.removeAll { time - $0.time > 60 }
        if let bytes { peak = max(peak ?? 0,bytes) }
    }
}

final class MeloNXMemoryGraph: UIView {
    private let title = UILabel()
    private let values = UILabel()
    private let historyLabel = UILabel()
    private let fps = UILabel()
    private(set) var history = MeloNXMemoryHistory()
    private var timer: Timer?
    var now: () -> TimeInterval = { ProcessInfo.processInfo.systemUptime }
    var sample: () -> [String:Any] = { MeloNXMemorySnapshot() as? [String:Any] ?? [:] }
    var isSampling: Bool { timer != nil }
    var fpsText: String { fps.text ?? "" }

    override init(frame: CGRect) {
        super.init(frame:frame)
        isUserInteractionEnabled = false
        backgroundColor = UIColor.black.withAlphaComponent(0.72)
        layer.cornerRadius = 10
        for label in [title,values,historyLabel,fps] {
            label.textColor = .white
            label.font = .monospacedSystemFont(ofSize:11,weight:.medium)
            label.numberOfLines = 0
            label.translatesAutoresizingMaskIntoConstraints = false
            addSubview(label)
        }
        title.text = MeloNXText("RewindBox RAM")
        historyLabel.text = MeloNXText("Last 60 s")
        fps.numberOfLines = 1
        fps.textAlignment = .right
        fps.font = .monospacedSystemFont(ofSize:11,weight:.semibold)
        fps.setContentHuggingPriority(.required,for:.horizontal)
        fps.setContentCompressionResistancePriority(.required,for:.horizontal)
        NSLayoutConstraint.activate([
            title.leadingAnchor.constraint(equalTo:leadingAnchor,constant:9),
            title.trailingAnchor.constraint(lessThanOrEqualTo:fps.leadingAnchor,constant:-6),
            title.topAnchor.constraint(equalTo:topAnchor,constant:7),
            fps.trailingAnchor.constraint(equalTo:trailingAnchor,constant:-9),
            fps.firstBaselineAnchor.constraint(equalTo:title.firstBaselineAnchor),
            values.leadingAnchor.constraint(equalTo:title.leadingAnchor),
            values.trailingAnchor.constraint(equalTo:trailingAnchor,constant:-9),
            values.topAnchor.constraint(equalTo:title.bottomAnchor,constant:3),
            historyLabel.leadingAnchor.constraint(equalTo:title.leadingAnchor),
            historyLabel.bottomAnchor.constraint(equalTo:bottomAnchor,constant:-5)
        ])
        isAccessibilityElement = true
    }
    required init?(coder:NSCoder) { fatalError("init(coder:) is unavailable") }
    func setSampling(_ enabled: Bool) {
        guard enabled != isSampling else { return }
        timer?.invalidate(); timer = nil
        guard enabled else { return }
        observe()
        let timer = Timer(timeInterval:0.5,repeats:true) { [weak self] _ in self?.observe() }
        timer.tolerance = 0.1
        RunLoop.main.add(timer,forMode:.common)
        self.timer = timer
    }
    func observe() {
        let value = sample()
        let footprint = value["footprintBytes"] as? NSNumber
        let headroom = value["availableBytes"] as? NSNumber
        fps.text = (value["gameFps"] as? NSNumber).map { String(format:"%.0f FPS",$0.doubleValue) } ?? ""
        history.append(time:now(),bytes:footprint?.uint64Value)
        func size(_ value: NSNumber?) -> String {
            guard let value else { return MeloNXText("Unavailable") }
            return String(format:"%.0f MiB",Double(value.uint64Value)/1048576)
        }
        values.text = size(footprint) + " · " + MeloNXText("Peak") + " " + size(history.peak.map { NSNumber(value:$0) }) + "\n" + MeloNXText("App headroom") + " " + size(headroom)
        if value["donorState"] != nil {
            let state = value["donorState"] as? String ?? "unavailable"
            values.text = (values.text ?? "") + "\n" + MeloNXText("Donor in use") + " " + size(value["donorUsedBytes"] as? NSNumber) +
                " / " + size(value["donorMappedBytes"] as? NSNumber) + "\n" + MeloNXText("Donor " + state)
        }
        accessibilityLabel = MeloNXText("RewindBox RAM") + ", " + (fpsText.isEmpty ? "" : fpsText + ", ") + (values.text ?? "")
        setNeedsDisplay()
    }
    override func draw(_ rect: CGRect) {
        super.draw(rect)
        guard let context = UIGraphicsGetCurrentContext(),let last = history.points.last else { return }
        let area = CGRect(x:9,y:92,width:max(1,bounds.width-18),height:max(1,bounds.height-114))
        context.setStrokeColor(UIColor.white.withAlphaComponent(0.3).cgColor)
        context.setLineWidth(0.5); context.stroke(area)
        let maximum = max(256 * 1048576,history.points.compactMap(\.bytes).max() ?? 0)
        let path = UIBezierPath(); var connected = false; var previous: TimeInterval?
        for point in history.points {
            guard let bytes = point.bytes else { connected = false; previous = nil; continue }
            let x = area.minX + CGFloat(max(0,1-(last.time-point.time)/60))*area.width
            let y = area.maxY - CGFloat(Double(bytes)/Double(maximum))*area.height
            if connected, let previous, point.time-previous < 1.5 { path.addLine(to:CGPoint(x:x,y:y)) }
            else { path.move(to:CGPoint(x:x,y:y)) }
            connected = true; previous = point.time
        }
        UIColor.systemMint.setStroke(); path.lineWidth = 1.5; path.stroke()
    }
    deinit { timer?.invalidate() }
}
