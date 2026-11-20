// Standalone optional iOS runner. Bundle ReconstructionProbe.mlmodelc with this
// target; never add this @main file to the regular RewindBox application.
import UIKit
import Metal
import QuartzCore

final class BenchmarkView: UIView {
    override class var layerClass: AnyClass { CAMetalLayer.self }
}

@main
final class BenchmarkApp: UIResponder, UIApplicationDelegate {
    var window: UIWindow?
    func application(_ application: UIApplication, didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
        let window = UIWindow(frame: UIScreen.main.bounds)
        let controller = UIViewController()
        let view = BenchmarkView(frame: window.bounds)
        controller.view = view; window.rootViewController = controller; self.window = window
        let layer = view.layer as! CAMetalLayer
        layer.device = MTLCreateSystemDefaultDevice(); layer.pixelFormat = .bgra8Unorm
        layer.framebufferOnly = false; layer.drawableSize = CGSize(width: 640, height: 360)
        layer.maximumDrawableCount = 3
        window.makeKeyAndVisible()
        UIApplication.shared.isIdleTimerDisabled = true
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
            guard let model = Bundle.main.url(forResource: "ReconstructionProbe", withExtension: "mlmodelc") else {
                self.show("Model missing: bundle ReconstructionProbe.mlmodelc", in: controller); return
            }
            let output = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("reconstruction-benchmark.json")
            Task.detached {
                do {
                    if #available(iOS 17.4, *) {
                        let options = BenchOptions(modelURL: model, outputURL: output)
                        let result = try await ReconstructionBench(layer: layer).run(options)
                        await MainActor.run { self.show("Benchmark complete.\n\(result["ane_verdict"] ?? "")\n\nExport reconstruction-benchmark.json and A/B/C.bgra from Documents.\nThis is a fixed-filter feasibility probe, not a game FPS result.", in: controller) }
                    } else { throw BenchError("Requires iOS 17.4 or later") }
                } catch { await MainActor.run { self.show("Benchmark failed: \(error)", in: controller) } }
            }
        }
        return true
    }
    private func show(_ text: String, in controller: UIViewController) {
        let alert = UIAlertController(title: "Reconstruction benchmark", message: text, preferredStyle: .alert)
        alert.addAction(UIAlertAction(title: "OK", style: .default))
        controller.present(alert, animated: true)
        UIApplication.shared.isIdleTimerDisabled = false
    }
}
