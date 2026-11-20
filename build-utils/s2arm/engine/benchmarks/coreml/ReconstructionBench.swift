// Experimental, standalone feasibility benchmark. Never linked into normal game playback.
// Core ML and Metal implement the SAME fixed spatial filter; this is not a trained model.
import Foundation
import Metal
import CoreVideo
import CoreML
import QuartzCore
import Darwin

struct BenchError: Error, CustomStringConvertible {
    let description: String
    init(_ text: String) { description = text }
}

struct BenchOptions {
    var modelURL: URL
    var outputURL: URL
    var iterations = 90
    var warmup = 10
    var cpuControl = true
    var sourceURL: URL? = nil // Optional raw BGRA reference, exactly outputWidth * outputHeight * 4.
}

private let metalSource = #"""
#include <metal_stdlib>
using namespace metal;
kernel void pattern(texture2d<float, access::write> dst [[texture(0)]],
                    constant uint &frame [[buffer(0)]], uint2 p [[thread_position_in_grid]]) {
    if (p.x >= dst.get_width() || p.y >= dst.get_height()) return;
    uint x = p.x + frame * 3, y = p.y;
    float a = ((x / 3 + y / 3) & 1) ? 0.82 : 0.16;
    float3 c = float3(a, float(x % 251) / 250.0, float(y % 239) / 238.0);
    // Thin diagonals, one-pixel lines, and a moving high-contrast label-like grid.
    if ((x + y) % 31 == 0 || (x + 2 * y) % 47 == 0) c = float3(1);
    if (p.y < 28 && p.x < dst.get_width() / 2) {
        bool ink = ((p.x / 2) % 7 < 2) || ((p.y / 2) % 9 == 0);
        c = ink ? float3(1, 0.9, 0.1) : float3(0.02);
    }
    dst.write(float4(c, 1), p);
}
kernel void resize(texture2d<float, access::sample> src [[texture(0)]],
                   texture2d<float, access::write> dst [[texture(1)]],
                   uint2 p [[thread_position_in_grid]]) {
    if (p.x >= dst.get_width() || p.y >= dst.get_height()) return;
    constexpr sampler s(coord::normalized, address::clamp_to_edge, filter::linear);
    float2 uv = (float2(p) + 0.5) / float2(dst.get_width(), dst.get_height());
    dst.write(float4(src.sample(s, uv).rgb, 1), p);
}
kernel void sharpen(texture2d<float, access::read> src [[texture(0)]],
                    texture2d<half, access::write> dst [[texture(1)]],
                    uint2 p [[thread_position_in_grid]]) {
    if (p.x >= dst.get_width() || p.y >= dst.get_height()) return;
    // Work in the model's 0..255 domain, with half precision and zero padding.
    half3 c = half3(src.read(p).rgb * 255.0) * half(1.5);
    if (p.x > 0) c -= half3(src.read(p - uint2(1, 0)).rgb * 255.0) * half(0.125);
    if (p.x + 1 < src.get_width()) c -= half3(src.read(p + uint2(1, 0)).rgb * 255.0) * half(0.125);
    if (p.y > 0) c -= half3(src.read(p - uint2(0, 1)).rgb * 255.0) * half(0.125);
    if (p.y + 1 < src.get_height()) c -= half3(src.read(p + uint2(0, 1)).rgb * 255.0) * half(0.125);
    dst.write(half4(clamp(c, half3(0), half3(255)), half(255)), p);
}
kernel void upscale(texture2d<half, access::sample> src [[texture(0)]],
                    texture2d<float, access::write> dst [[texture(1)]],
                    uint2 p [[thread_position_in_grid]]) {
    if (p.x >= dst.get_width() || p.y >= dst.get_height()) return;
    constexpr sampler s(coord::normalized, address::clamp_to_edge, filter::linear);
    float2 uv = (float2(p) + 0.5) / float2(dst.get_width(), dst.get_height());
    dst.write(float4(float3(src.sample(s, uv).rgb) / 255.0, 1), p);
}
"""#

private final class PixelSurface {
    let pixelBuffer: CVPixelBuffer
    let cvTexture: CVMetalTexture
    let texture: MTLTexture
    init(width: Int, height: Int, cache: CVMetalTextureCache) throws {
        var pb: CVPixelBuffer?
        let attrs: [CFString: Any] = [kCVPixelBufferMetalCompatibilityKey: true,
                                    kCVPixelBufferIOSurfacePropertiesKey: [:]]
        guard CVPixelBufferCreate(kCFAllocatorDefault, width, height, kCVPixelFormatType_32BGRA,
                                  attrs as CFDictionary, &pb) == kCVReturnSuccess, let buffer = pb else {
            throw BenchError("CVPixelBuffer allocation failed")
        }
        var cv: CVMetalTexture?
        let textureAttrs = [kCVMetalTextureUsage: MTLTextureUsage.shaderRead.rawValue | MTLTextureUsage.shaderWrite.rawValue] as CFDictionary
        guard CVMetalTextureCacheCreateTextureFromImage(kCFAllocatorDefault, cache, buffer, textureAttrs,
                  .bgra8Unorm, width, height, 0, &cv) == kCVReturnSuccess,
              let view = cv, let texture = CVMetalTextureGetTexture(view) else {
            throw BenchError("CVMetalTexture mapping failed")
        }
        self.pixelBuffer = buffer; self.cvTexture = view; self.texture = texture
    }
    func bytes() throws -> Data {
        guard CVPixelBufferLockBaseAddress(pixelBuffer, .readOnly) == kCVReturnSuccess else {
            throw BenchError("Could not lock output pixels")
        }
        defer { CVPixelBufferUnlockBaseAddress(pixelBuffer, .readOnly) }
        guard let base = CVPixelBufferGetBaseAddress(pixelBuffer) else { throw BenchError("No pixel address") }
        let width = CVPixelBufferGetWidth(pixelBuffer), height = CVPixelBufferGetHeight(pixelBuffer)
        let stride = CVPixelBufferGetBytesPerRow(pixelBuffer)
        var result = Data(count: width * height * 4)
        result.withUnsafeMutableBytes { output in
            for y in 0..<height { memcpy(output.baseAddress!.advanced(by: y * width * 4), base.advanced(by: y * stride), width * 4) }
        }
        return result
    }
}

private final class PresentationStamp {
    private let lock = NSLock()
    private var value: Double = 0
    let semaphore = DispatchSemaphore(value: 0)
    func set(_ time: Double) { lock.lock(); value = time; lock.unlock(); semaphore.signal() }
    func get() -> Double { lock.lock(); defer { lock.unlock() }; return value }
}

private func percentiles(_ values: [Double]) -> [String: Any] {
    let a = values.filter { $0.isFinite && $0 >= 0 }.sorted()
    guard !a.isEmpty else { return ["count": 0] }
    func p(_ fraction: Double) -> Double {
        let pos = Double(a.count - 1) * fraction, low = Int(pos), high = min(low + 1, a.count - 1)
        return a[low] + (a[high] - a[low]) * (pos - Double(low))
    }
    return ["count": a.count, "p50": p(0.5), "p95": p(0.95), "p99": p(0.99), "min": a[0], "max": a.last!]
}

@available(macOS 14.4, iOS 17.4, *)
private func deviceName(_ device: MLComputeDevice) -> String {
    switch device { case .cpu: return "cpu"; case .gpu: return "gpu"; case .neuralEngine: return "neuralEngine"; @unknown default: return "unknown" }
}

@available(macOS 14.4, iOS 17.4, *)
private func computePlan(_ url: URL, _ configuration: MLModelConfiguration) async throws -> [String: Any] {
    let plan = try await MLComputePlan.load(contentsOf: url, configuration: configuration)
    var rows = [[String: Any]]()
    func visit(_ block: MLModelStructure.Program.Block, _ path: String) {
        for (index, operation) in block.operations.enumerated() {
            var row: [String: Any] = ["path": "\(path)/\(index)", "operator": operation.operatorName]
            if let usage = plan.deviceUsage(for: operation) {
                row["preferred"] = deviceName(usage.preferred)
                row["supported"] = usage.supported.map(deviceName)
            } else { row["preferred"] = "unavailable" }
            if let cost = plan.estimatedCost(of: operation) { row["relative_cost"] = cost.weight }
            rows.append(row)
            for (i, child) in operation.blocks.enumerated() { visit(child, "\(path)/\(index)/block\(i)") }
        }
    }
    if case let .program(program) = plan.modelStructure {
        for name in program.functions.keys.sorted() { visit(program.functions[name]!.block, name) }
    }
    return ["evidence": "anticipated_compute_plan_not_runtime_hardware_trace", "operations": rows,
            "preferred_neural_engine_operations": rows.filter { ($0["preferred"] as? String) == "neuralEngine" }.count]
}

@available(macOS 14.4, iOS 17.4, *)
final class ReconstructionBench {
    private let device: MTLDevice
    private let queue: MTLCommandQueue
    private var cache: CVMetalTextureCache
    private var pipelines: [String: MTLComputePipelineState] = [:]
    // A layer is optional. CI is honestly headless; an iOS view can supply one.
    private let layer: CAMetalLayer?
    init(layer: CAMetalLayer? = nil) throws {
        guard let device = MTLCreateSystemDefaultDevice(), let queue = device.makeCommandQueue() else {
            throw BenchError("No Metal device/queue; benchmark cannot compare B and C")
        }
        self.device = device; self.queue = queue; self.layer = layer
        var cache: CVMetalTextureCache?
        guard CVMetalTextureCacheCreate(kCFAllocatorDefault, nil, device, nil, &cache) == kCVReturnSuccess,
              let cache else { throw BenchError("CVMetalTextureCache creation failed") }
        self.cache = cache
        let library = try device.makeLibrary(source: metalSource, options: nil)
        for name in ["pattern", "resize", "sharpen", "upscale"] {
            guard let f = library.makeFunction(name: name) else { throw BenchError("Missing Metal function \(name)") }
            pipelines[name] = try device.makeComputePipelineState(function: f)
        }
    }
    private func texture(_ format: MTLPixelFormat, _ w: Int, _ h: Int) throws -> MTLTexture {
        let d = MTLTextureDescriptor.texture2DDescriptor(pixelFormat: format, width: w, height: h, mipmapped: false)
        d.storageMode = .private; d.usage = [.shaderRead, .shaderWrite]
        guard let t = device.makeTexture(descriptor: d) else { throw BenchError("Metal texture allocation failed") }
        return t
    }
    private func command() throws -> MTLCommandBuffer {
        guard let cb = queue.makeCommandBuffer() else { throw BenchError("No command buffer") }; return cb
    }
    private func encode(_ name: String, _ cb: MTLCommandBuffer, _ source: MTLTexture?, _ output: MTLTexture, frame: UInt32 = 0) throws {
        guard let e = cb.makeComputeCommandEncoder(), let pipeline = pipelines[name] else { throw BenchError("No compute encoder") }
        e.label = "reconstruction.\(name)"; e.setComputePipelineState(pipeline)
        if name == "pattern" {
            var f = frame; e.setTexture(output, index: 0); e.setBytes(&f, length: MemoryLayout<UInt32>.size, index: 0)
        } else { e.setTexture(source, index: 0); e.setTexture(output, index: 1) }
        let tw = min(16, pipeline.threadExecutionWidth)
        let th = min(16, max(1, pipeline.maxTotalThreadsPerThreadgroup / tw))
        e.dispatchThreads(MTLSize(width: output.width, height: output.height, depth: 1),
                          threadsPerThreadgroup: MTLSize(width: tw, height: th, depth: 1))
        e.endEncoding()
    }
    private func finish(_ cb: MTLCommandBuffer) throws -> Double {
        cb.commit(); cb.waitUntilCompleted()
        if let error = cb.error { throw error }
        return cb.gpuStartTime > 0 && cb.gpuEndTime >= cb.gpuStartTime ? (cb.gpuEndTime - cb.gpuStartTime) * 1000 : -1
    }
    private func display(_ cb: MTLCommandBuffer, _ source: MTLTexture) throws -> PresentationStamp? {
        guard let layer, let drawable = layer.nextDrawable() else { return nil }
        try encode("resize", cb, source, drawable.texture)
        let stamp = PresentationStamp()
#if !targetEnvironment(simulator)
        drawable.addPresentedHandler { stamp.set($0.presentedTime) }
#endif
        cb.present(drawable)
        return stamp
    }
    func run(_ options: BenchOptions) async throws -> [String: Any] {
        guard options.iterations > 0 && options.iterations <= 10000 && options.warmup >= 0 else { throw BenchError("Invalid iteration count") }
        let compiled: URL
        let compileStart = CACurrentMediaTime()
        if options.modelURL.pathExtension == "mlmodelc" { compiled = options.modelURL }
        else { compiled = try await MLModel.compileModel(at: options.modelURL) }
        let compileMS = (CACurrentMediaTime() - compileStart) * 1000
        let config = MLModelConfiguration(); config.computeUnits = .cpuAndNeuralEngine
        let loadStart = CACurrentMediaTime()
        let model = try MLModel(contentsOf: compiled, configuration: config)
        let loadMS = (CACurrentMediaTime() - loadStart) * 1000
        let plan: [String: Any]
        do { plan = try await computePlan(compiled, config) } catch { plan = ["error": String(describing: error)] }
        var cpu: MLModel? = nil
        if options.cpuControl { let c = MLModelConfiguration(); c.computeUnits = .cpuOnly; cpu = try MLModel(contentsOf: compiled, configuration: c) }
        guard let inputShape = model.modelDescription.inputDescriptionsByName["inputImage"]?.imageConstraint,
              let outputShape = model.modelDescription.outputDescriptionsByName["outputImage"]?.imageConstraint else {
            throw BenchError("Model must expose inputImage/outputImage image features")
        }
        let w = inputShape.pixelsWide, h = inputShape.pixelsHigh, ow = outputShape.pixelsWide, oh = outputShape.pixelsHigh
        guard ow == w * 2 && oh == h * 2 else { throw BenchError("This benchmark requires the supplied 2x model") }
        let source = try PixelSurface(width: ow, height: oh, cache: cache)
        let input = try PixelSurface(width: w, height: h, cache: cache)
        let metalOut = try PixelSurface(width: ow, height: oh, cache: cache)
        let mlOut = try PixelSurface(width: ow, height: oh, cache: cache)
        let final = try PixelSurface(width: ow, height: oh, cache: cache)
        let filtered = try texture(.rgba16Float, w, h)
        let feature = try MLDictionaryFeatureProvider(dictionary: ["inputImage": MLFeatureValue(pixelBuffer: input.pixelBuffer)])
        let predictionOptions = MLPredictionOptions()
        predictionOptions.outputBackings = ["outputImage": mlOut.pixelBuffer]
        if let sourceURL = options.sourceURL {
            let data = try Data(contentsOf: sourceURL)
            guard data.count == ow * oh * 4 else { throw BenchError("Raw BGRA reference has wrong dimensions") }
            CVPixelBufferLockBaseAddress(source.pixelBuffer, [])
            guard let dst = CVPixelBufferGetBaseAddress(source.pixelBuffer) else { throw BenchError("Reference pixels unavailable") }
            let stride = CVPixelBufferGetBytesPerRow(source.pixelBuffer)
            data.withUnsafeBytes { raw in for y in 0..<oh { memcpy(dst.advanced(by: y * stride), raw.baseAddress!.advanced(by: y * ow * 4), ow * 4) } }
            CVPixelBufferUnlockBaseAddress(source.pixelBuffer, [])
        }
        var samples = [[String: Any]](), cold = [[String: Any]](), comparisons = [[String: Any]]()
        let thermalStart = ProcessInfo.processInfo.thermalState.rawValue
        var errors = [String](), cFailures = 0
        let variants = cpu == nil ? ["A_full", "B_metal", "C_cpuAndNeuralEngine"] : ["A_full", "B_metal", "C_cpuAndNeuralEngine", "D_cpuOnly"]
        for iteration in 0..<(options.warmup + options.iterations) {
            if options.sourceURL == nil {
                let cb = try command(); try encode("pattern", cb, nil, source.texture, frame: UInt32(iteration)); _ = try finish(cb)
            }
            var currentMetal: Data?, currentML: Data?
            // Rotate variant order; identical source pixels for every paired iteration.
            let order = Array(variants[(iteration % variants.count)...]) + Array(variants[..<(iteration % variants.count)])
            for variant in order {
                try autoreleasepool {
                    let start = CACurrentMediaTime()
                    var gpuMS = 0.0, gpuKnown = true, inputWaitMS = 0.0, predictionMS = 0.0
                    var actual = variant, failure: String? = nil, outputBacking = true
                    var outputTexture = source.texture
                    var retainedCV: CVMetalTexture? = nil // Keep a replacement model output mapping alive until final GPU completion.
                    var retainedPB: CVPixelBuffer? = nil
                    let cb: MTLCommandBuffer
                    if variant == "A_full" { cb = try command() }
                    else if variant == "B_metal" {
                        cb = try command()
                        try encode("resize", cb, source.texture, input.texture)
                        try encode("sharpen", cb, input.texture, filtered)
                        try encode("upscale", cb, filtered, metalOut.texture)
                        outputTexture = metalOut.texture
                    } else {
                        let pre = try command(); try encode("resize", pre, source.texture, input.texture)
                        let preStart = CACurrentMediaTime(), preGPU = try finish(pre)
                        inputWaitMS = (CACurrentMediaTime() - preStart) * 1000
                        if preGPU >= 0 { gpuMS += preGPU } else { gpuKnown = false }
                        let predictionStart = CACurrentMediaTime()
                        do {
                            let selected = variant == "D_cpuOnly" ? cpu! : model
                            let result = try selected.prediction(from: feature, options: predictionOptions)
                            guard let buffer = result.featureValue(for: "outputImage")?.imageBufferValue else { throw BenchError("No prediction image") }
                            predictionMS = (CACurrentMediaTime() - predictionStart) * 1000
                            outputBacking = CFEqual(buffer, mlOut.pixelBuffer)
                            if outputBacking { outputTexture = mlOut.texture }
                            else {
                                var mapped: CVMetalTexture?
                                guard CVMetalTextureCacheCreateTextureFromImage(kCFAllocatorDefault, cache, buffer, nil, .bgra8Unorm, ow, oh, 0, &mapped) == kCVReturnSuccess,
                                      let view = mapped, let texture = CVMetalTextureGetTexture(view) else { throw BenchError("Prediction output mapping failed") }
                                retainedPB = buffer; retainedCV = view; outputTexture = texture
                            }
                        } catch {
                            predictionMS = (CACurrentMediaTime() - predictionStart) * 1000
                            failure = String(describing: error); errors.append(failure!); actual = "B_metal_fallback"
                            if variant == "C_cpuAndNeuralEngine" { cFailures += 1 }
                        }
                        cb = try command()
                        if failure != nil {
                            try encode("sharpen", cb, input.texture, filtered)
                            try encode("upscale", cb, filtered, metalOut.texture); outputTexture = metalOut.texture
                        }
                    }
                    try encode("resize", cb, outputTexture, final.texture)
                    let beforeDrawable = CACurrentMediaTime()
                    let presented = try display(cb, final.texture)
                    let drawableMS = (CACurrentMediaTime() - beforeDrawable) * 1000
                    let endGPU = try finish(cb), complete = CACurrentMediaTime()
                    if endGPU >= 0 { gpuMS += endGPU } else { gpuKnown = false }
                    var shown = 0.0
                    if let presented {
#if !targetEnvironment(simulator)
                        _ = presented.semaphore.wait(timeout: .now() + 2)
                        shown = presented.get()
#endif
                    }
                    withExtendedLifetime(retainedCV) {}; withExtendedLifetime(retainedPB) {}
                    var row: [String: Any] = ["iteration": iteration, "variant": variant, "effective_variant": actual,
                        "end_to_end_gpu_complete_ms": (complete - start) * 1000,
                        "metal_gpu_ms": gpuKnown ? gpuMS : -1, "input_gpu_completion_wait_ms": inputWaitMS,
                        "prediction_wall_ms": predictionMS, "drawable_and_display_encode_ms": drawableMS,
                        "presented_time": shown, "end_to_end_display_ms": shown > 0 ? (shown - start) * 1000 : -1,
                        "output_backing_reused": outputBacking, "valid_comparison": failure == nil,
                        "thermal_state": ProcessInfo.processInfo.thermalState.rawValue]
                    if let failure { row["fallback_reason"] = failure }
                    if iteration == 0 { cold.append(row) }
                    if iteration >= options.warmup { samples.append(row) }
                    // Correctness/readback is intentionally outside measured intervals.
                    if iteration == 0 || iteration == options.warmup + options.iterations - 1 {
                        if variant == "B_metal" { currentMetal = try final.bytes() }
                        if variant == "C_cpuAndNeuralEngine" && failure == nil { currentML = try final.bytes() }
                    }
                }
            }
            if let b = currentMetal, let c = currentML {
                var sum = 0.0, square = 0.0, maxDiff = 0, count = 0
                b.withUnsafeBytes { rb in c.withUnsafeBytes { rc in
                    let x = rb.bindMemory(to: UInt8.self), y = rc.bindMemory(to: UInt8.self)
                    for i in 0..<b.count where i % 4 != 3 {
                        let diff = abs(Int(x[i]) - Int(y[i])); sum += Double(diff); square += Double(diff * diff); maxDiff = max(maxDiff, diff); count += 1
                    }
                } }
                let mse = square / Double(count)
                comparisons.append(["iteration": iteration, "rgb_mae_byte": sum / Double(count), "rgb_max_error_byte": maxDiff,
                                    "rgb_psnr_db": mse > 0 ? 10 * log10(255 * 255 / mse) : 999,
                                    "scope": "same_input_same_fixed_filter_B_vs_C_not_quality_against_native_game"])
                try b.write(to: options.outputURL.deletingPathExtension().appendingPathExtension("B.bgra"))
                try c.write(to: options.outputURL.deletingPathExtension().appendingPathExtension("C.bgra"))
                try source.bytes().write(to: options.outputURL.deletingPathExtension().appendingPathExtension("A.bgra"))
            }
        }
        var summaries = [String: Any]()
        for variant in variants {
            let rows = samples.filter { ($0["variant"] as? String) == variant && ($0["valid_comparison"] as? Bool) == true }
            var summary = [String: Any]()
            for key in ["end_to_end_gpu_complete_ms", "metal_gpu_ms", "input_gpu_completion_wait_ms", "prediction_wall_ms", "end_to_end_display_ms"] {
                summary[key] = percentiles(rows.compactMap { $0[key] as? Double })
            }
            summaries[variant] = summary
        }
        let devices = MLComputeDevice.allComputeDevices.map(deviceName)
        let availableANE = devices.contains("neuralEngine")
        let preferredANE = (plan["preferred_neural_engine_operations"] as? Int ?? 0) > 0
        let equivalent = !comparisons.isEmpty && comparisons.allSatisfy {
            ($0["rgb_max_error_byte"] as? Int ?? 256) <= 3 && ($0["rgb_mae_byte"] as? Double ?? 256) <= 0.75
        }
        let result: [String: Any] = [
            "schema": "rewindbox.reconstruction-benchmark.v1", "model": options.modelURL.lastPathComponent,
            "model_kind": "fixed_3x3_filter_plus_2x_bilinear_not_trained_neural_reconstruction",
            "input_width": w, "input_height": h, "output_width": ow, "output_height": oh,
            "source": options.sourceURL == nil ? "generated_moving_lines_and_checkerboard" : "provided_raw_BGRA_frame",
            "metal_device": device.name, "os": ProcessInfo.processInfo.operatingSystemVersionString,
            "compute_devices_available": devices, "neural_engine_available": availableANE,
            "neural_engine_preferred_in_plan": preferredANE, "ane_runtime_execution_proven": false,
            "ane_gain_claim_permitted": false,
            "ane_verdict": !availableANE ? "Neural Engine unavailable: C is CPU fallback; no ANE performance conclusion" : !preferredANE ? "No operation prefers ANE in this plan; no ANE benefit proven" : "ANE preferred in plan; runtime Instruments and A18 device evidence still required",
            "compute_plan": plan, "compile_ms": compileMS, "load_cpu_and_neural_engine_ms": loadMS,
            "cold_first_iteration": cold, "warmup_iterations": options.warmup, "measured_iterations": options.iterations,
            "summary": summaries, "samples": samples, "B_C_numeric_comparison": comparisons,
            "B_C_numerical_equivalence_passed": equivalent,
            "B_C_equivalence_threshold": "RGB max<=3/255 and MAE<=0.75/255 at first and last tested frame; FP16 and image quantization tolerated",
            "thermal_start": thermalStart, "thermal_end": ProcessInfo.processInfo.thermalState.rawValue,
            "explicit_pixel_storage_bytes": (ow * oh * 4 * 4) + w * h * 4 + w * h * 8,
            "memory_coverage": "explicit pixel surfaces only; CoreML internal allocations and resident footprint require Instruments",
            "copy_scope": "B and C include full-resolution source to reduced input and reconstructed output to final surface; C additionally includes required GPU completion and CoreML prediction/conversions",
            "presented_timestamp_coverage": samples.filter { ($0["presented_time"] as? Double ?? 0) > 0 }.count,
            "game_render_work_saved_measured": false, "iphone_game_fps_gain_measured": false,
            "coreml_prediction_failures": cFailures, "errors": errors
        ]
        let data = try JSONSerialization.data(withJSONObject: result, options: [.prettyPrinted, .sortedKeys])
        try data.write(to: options.outputURL, options: .atomic)
        return result
    }
}
