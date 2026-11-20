import Foundation
import Darwin

@main
struct BenchMain {
    static func main() async {
        do {
            let args = CommandLine.arguments
            func value(_ flag: String) -> String? { guard let i = args.firstIndex(of: flag), i + 1 < args.count else { return nil }; return args[i + 1] }
            guard let model = value("--model"), let output = value("--output") else {
                throw BenchError("usage: ReconstructionBench --model MODEL.mlpackage|mlmodelc --output RESULT.json [--iterations 90] [--warmup 10] [--source-bgra RAW] [--no-cpu-control]")
            }
            var options = BenchOptions(modelURL: URL(fileURLWithPath: model), outputURL: URL(fileURLWithPath: output))
            options.iterations = Int(value("--iterations") ?? "90") ?? 90
            options.warmup = Int(value("--warmup") ?? "10") ?? 10
            options.cpuControl = !args.contains("--no-cpu-control")
            if let source = value("--source-bgra") { options.sourceURL = URL(fileURLWithPath: source) }
            try FileManager.default.createDirectory(at: options.outputURL.deletingLastPathComponent(), withIntermediateDirectories: true)
            if #available(macOS 14.4, iOS 17.4, *) {
                let result = try await ReconstructionBench().run(options)
                print("wrote \(output)")
                print(result["ane_verdict"] ?? "unknown")
                print("Scope: standalone reconstruction; no game-render savings or iPhone FPS claim.")
            } else { throw BenchError("Requires macOS 14.4 / iOS 17.4 for per-operation compute-plan evidence") }
        } catch {
            fputs("ReconstructionBench: \(error)\n", stderr)
            // Always leave machine-readable evidence on CI failure.
            let args = CommandLine.arguments
            if let i = args.firstIndex(of: "--output"), i + 1 < args.count {
                let failure: [String: Any] = ["schema": "rewindbox.reconstruction-benchmark.v1", "completed": false,
                    "error": String(describing: error), "ane_gain_claim_permitted": false, "iphone_game_fps_gain_measured": false]
                if let data = try? JSONSerialization.data(withJSONObject: failure, options: [.prettyPrinted, .sortedKeys]) {
                    try? data.write(to: URL(fileURLWithPath: args[i + 1]))
                }
            }
            exit(1)
        }
    }
}
