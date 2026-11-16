// The MeloNX performance bar, on RPCS3's minimal bar (RPCS3PerformanceOverlay.mm since IPA 756). One compact bar,
// four columns, the value above its caption:
//   FPS       the engine's game FPS (MeloNXRuntimeAPI.performanceSnapshot), one decimal, locale separator;
//   CPU       the process's CPU time over all the device's cores between two samples, 0-100 % (getrusage);
//   RAM       the app's kernel footprint (TASK_VM_INFO.phys_footprint, the measurement of MeloNX's original
//             PerformanceOverlay by Stossy11), decimal GB;
//   RamDonor  the RamDonor bytes the engine uses (donorUsedBytes), decimal GB; never the mapped capacity.
// "—" when a value is not measured. No graph: eight labels, updated by the sampler only while the bar is shown.
import UIKit

// User plus system CPU time of the whole process (every thread, ended ones included), in seconds.
func MeloNXProcessCPUSeconds() -> Double? {
    var usage = rusage()
    guard getrusage(RUSAGE_SELF,&usage) == 0 else { return nil }
    func seconds(_ time: timeval) -> Double { Double(time.tv_sec) + Double(time.tv_usec) / 1e6 }
    return seconds(usage.ru_utime) + seconds(usage.ru_stime)
}

final class MeloNXMemoryGraph: UIView {
    static let barSize = CGSize(width:256,height:44)
    private static let padding: CGFloat = 8
    // The memory columns carry a unit and are wider.
    private static let weights: [CGFloat] = [0.20,0.20,0.30,0.30]
    private let fpsValue = UILabel(), cpuValue = UILabel(), ramValue = UILabel(), donorValue = UILabel()
    private var values: [UILabel] { [fpsValue,cpuValue,ramValue,donorValue] }
    private var captions: [UILabel] = []
    private let fpsFormat = NumberFormatter(), percentFormat = NumberFormatter(), memoryFormat = NumberFormatter()
    private var lastCPU: (seconds: Double, time: TimeInterval)?
    private var timer: Timer?
    var now: () -> TimeInterval = { ProcessInfo.processInfo.systemUptime }
    var sample: () -> [String:Any] = { MeloNXMemoryGraph.processSample() }
    var processorCount = ProcessInfo.processInfo.activeProcessorCount
    var numberLocale = Locale.current { didSet { for format in [fpsFormat,percentFormat,memoryFormat] { format.locale = numberLocale } } }
    var isSampling: Bool { timer != nil }
    var fpsText: String { fpsValue.text ?? "" }
    var cpuText: String { cpuValue.text ?? "" }
    var ramText: String { ramValue.text ?? "" }
    var donorText: String { donorValue.text ?? "" }
    var captionTexts: [String] { captions.map { $0.text ?? "" } }

    // The footprint sampler of the app and the process's CPU time; the session adds the engine's values.
    static func processSample() -> [String:Any] {
        var values = MeloNXMemorySnapshot() as? [String:Any] ?? [:]
        if let seconds = MeloNXProcessCPUSeconds() { values["processCpuSeconds"] = seconds }
        return values
    }

    override init(frame: CGRect) {
        super.init(frame:frame)
        isOpaque = false
        backgroundColor = UIColor(white:0,alpha:0.55)
        layer.cornerRadius = 10
        clipsToBounds = true
        isUserInteractionEnabled = false
        isAccessibilityElement = true
        accessibilityTraits = .staticText
        accessibilityIdentifier = "melonx.performance.overlay"
        for label in values {
            label.font = .monospacedDigitSystemFont(ofSize:15,weight:.semibold)
            label.textColor = .white
            label.textAlignment = .center
            label.adjustsFontSizeToFitWidth = true
            label.minimumScaleFactor = 0.7
            label.isAccessibilityElement = false
            label.text = "—"
            addSubview(label)
        }
        // Captions are names, the same in every language; orange and green as RPCS3's RAM and NeoSwap.
        let muted = UIColor(white:1,alpha:0.6)
        for (text,color) in [("FPS",muted),("CPU",muted),("RAM",UIColor.systemOrange),("RamDonor",UIColor.systemGreen)] {
            let label = UILabel()
            label.font = .systemFont(ofSize:9,weight:.medium)
            label.textColor = color
            label.textAlignment = .center
            label.adjustsFontSizeToFitWidth = true
            label.minimumScaleFactor = 0.8
            label.isAccessibilityElement = false
            label.text = text
            addSubview(label); captions.append(label)
        }
        fpsFormat.numberStyle = .decimal; fpsFormat.usesGroupingSeparator = false
        fpsFormat.minimumFractionDigits = 1; fpsFormat.maximumFractionDigits = 1
        percentFormat.numberStyle = .percent; percentFormat.maximumFractionDigits = 0
        memoryFormat.numberStyle = .decimal; memoryFormat.usesGroupingSeparator = false
        memoryFormat.minimumFractionDigits = 2; memoryFormat.maximumFractionDigits = 2
        for format in [fpsFormat,percentFormat,memoryFormat] { format.locale = numberLocale }
        accessibilityLabel = MeloNXText("RSwitch Performance")
        updateAccessibility()
    }
    required init?(coder:NSCoder) { fatalError("init(coder:) is unavailable") }
    override var intrinsicContentSize: CGSize { Self.barSize }
    override func layoutSubviews() {
        super.layoutSubviews()
        let width = max(0,bounds.width - 2 * Self.padding)
        // The two rows sit in the middle of whatever height the layout gives the bar.
        let top = max(0,(bounds.height - 34) / 2)
        var x = Self.padding
        for (column,value) in values.enumerated() {
            let columnWidth = width * Self.weights[column]
            value.frame = CGRect(x:x,y:top,width:columnWidth,height:20)
            captions[column].frame = CGRect(x:x,y:top + 21,width:columnWidth,height:12)
            x += columnWidth
        }
    }
    func setSampling(_ enabled: Bool) {
        guard enabled != isSampling else { return }
        timer?.invalidate(); timer = nil
        guard enabled else { return }
        lastCPU = nil // a CPU share covers one sampling interval, never a pause
        observe()
        let timer = Timer(timeInterval:0.5,repeats:true) { [weak self] _ in self?.observe() }
        timer.tolerance = 0.1
        RunLoop.main.add(timer,forMode:.common)
        self.timer = timer
    }
    func observe() {
        let value = sample()
        let time = now()
        // Zero is a stalled-frame sample, not a missing one (NeoSwapFPSValid).
        let fps = (value["gameFps"] as? NSNumber)?.doubleValue
        fpsValue.text = fps.flatMap { $0.isFinite && $0 >= 0 ? fpsFormat.string(from:NSNumber(value:$0)) : nil } ?? "—"
        var cpu: Double?
        if let seconds = (value["processCpuSeconds"] as? NSNumber)?.doubleValue, seconds.isFinite {
            if let last = lastCPU, time > last.time, seconds >= last.seconds, processorCount > 0 {
                cpu = (seconds - last.seconds) / ((time - last.time) * Double(processorCount)) * 100
            }
            lastCPU = (seconds,time)
        } else {
            lastCPU = nil
        }
        cpuValue.text = cpu.flatMap { $0.isFinite && $0 >= 0 ? percentFormat.string(from:NSNumber(value:min($0,100) / 100)) : nil } ?? "—"
        ramValue.text = memory(value["footprintBytes"])
        donorValue.text = memory(value["donorUsedBytes"])
        updateAccessibility()
    }
    // Decimal gigabytes with two decimals, as RPCS3 (NeoSwapDecimalGB).
    private func memory(_ value: Any?) -> String {
        guard let bytes = (value as? NSNumber)?.uint64Value,
              let text = memoryFormat.string(from:NSNumber(value:Double(bytes) / 1e9)) else { return "—" }
        return text + " " + MeloNXText("GB")
    }
    private func updateAccessibility() {
        // Spoken with the full names of the two memory values (12 languages).
        let ram = MeloNXText("App RAM"), donor = MeloNXText("RamDonor lent")
        accessibilityValue = "FPS \(fpsText). CPU \(cpuText). \(ram): \(ramText). \(donor): \(donorText)"
    }
    deinit { timer?.invalidate() }
}
