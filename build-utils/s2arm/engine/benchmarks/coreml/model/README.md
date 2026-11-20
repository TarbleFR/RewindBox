# Core ML reconstruction execution probe

`ReconstructionProbe.mlpackage` is a generated, nonidentity Core ML MLProgram.
Its convolution coefficients are analytical, not trained. It is suitable for
testing buffer transport, scheduling and CPU/Neural Engine eligibility. It does
**not** demonstrate learned detail restoration, game image quality, or an ANE
speedup. No pretrained weights or training dataset are included.

| Feature | Input | Output |
|---|---|---|
| Name | `inputImage` | `outputImage` |
| Default size | 320 × 180 | 640 × 360 |
| Image interface | RGB, 8-bit color | RGB, 8-bit color |
| Pixel buffer | `kCVPixelFormatType_32BGRA` | `kCVPixelFormatType_32BGRA` |
| Graph tensor shape | `[1, 3, 180, 320]` | `[1, 3, 360, 640]` |

Core ML handles the RGB image-feature / BGRA pixel-buffer mapping. Alpha is not
an input to the filter; use opaque buffers in the comparison. Image feature
values use 0–255 units, with no `/255` normalization in this model.

The three channels independently execute this exact operation sequence:

1. 3 × 3 zero-padded convolution with kernel
   `[[0,-0.125,0],[-0.125,1.5,-0.125],[0,-0.125,0]]`.
2. Clamp to `[0,255]` **before** interpolation.
3. Bilinear resize by 2 in each dimension, with `align_corners=False` and
   `half_pixel_centers=True`. Output coordinate `o` samples source coordinate
   `(o + 0.5) / 2 - 0.5`, clamped to the input extent.

Zero padding deliberately brightens outer-edge pixels on a constant image.
This is a documented probe boundary condition, not a production sharpening
recommendation. The Metal comparison must also use zero samples outside the
convolution extent and edge clamp during the later bilinear sampling.

The convolution, clipping and resizing execute in FP16. Image entry/exit uses
conversion to/from bytes, so allow small rounding differences in a pixelwise
comparison. Keep the Metal filter intermediate in float/half, not an 8-bit
texture: otherwise it rounds between clipping and interpolation unlike the graph.

## Regenerate

Use Python 3.12 in a virtual environment:

```sh
python -m pip install -r requirements.txt
python generate_probe.py
python generate_probe.py --width 960 --height 540 --output ReconstructionProbe960x540.mlpackage
```

The larger model has the same weights and processing but produces 1920 × 1080.
Static dimensions avoid measuring flexible-shape specialization or rebuilding a
model during a timed frame. The generated `.manifest.json` contains all feature
shapes, exact coefficients, operation names, checks and file hashes.

Generation works on Linux because `skip_model_load=True` avoids Apple runtime
loading. Missing `libcoremlpython` warnings there are expected. Conversion and
NumPy checks are **not** prediction execution, Xcode compilation, or hardware
placement validation. The manifests record those checks as unexecuted.

## Runtime requirements

Compile `.mlpackage` with Xcode or `MLModel.compileModel(at:)` on Apple hardware,
then load the compiled URL outside the timed region. Minimum deployment target
is iOS 16 / macOS 13. Make a real prediction using `inputImage`; present or inspect
the returned `outputImage` pixel buffer. Do not substitute the source frame when
reporting a successful prediction.

Run matched reduced-resolution inputs through Metal and the Core ML model with
`.cpuOnly`, `.cpuAndGPU`, and `.cpuAndNeuralEngine` configurations. The final
configuration allows CPU and ANE; it does not force ANE. Record plan placement
using `MLComputePlan` (iOS 17.4+), then use Core ML Instruments on the target device
to confirm execution. Include conversion, synchronization and presentation costs
in an end-to-end metric, separately from prediction duration.

Allocate IOSurface-backed Metal-compatible input/output buffers outside the timed
region. `MLPredictionOptions.outputBackings = ["outputImage": outputBuffer]`
supplies the reusable output backing (iOS 16+). Use a buffer ring or otherwise wait
until the GPU has finished reading an output before reusing it for prediction.

## Verification performed here

- Model converted with coremltools 9.0; both features verified as RGB image types.
- `conv`, `clip`, `upsample_bilinear` remain in the generated graph as FP16 ops.
- NumPy checks cover black, constant interior, the zero-padded border and a
  nonidentity impulse. A designated impulse output is 153.5; pure bilinear is 146.
- No Core ML prediction, Apple model compilation, ANE execution, game workload,
  on-device frame-time or thermal test was possible in this Linux generation step.

## Primary references

- [Apple: image input/output conversion](https://apple.github.io/coremltools/docs-guides/source/image-inputs.html)
- [Apple: iOS 16 bilinear half-pixel semantics](https://apple.github.io/coremltools/_modules/coremltools/converters/mil/mil/ops/defs/iOS16/image_resizing.html)
- [Apple: compute-unit configurations](https://developer.apple.com/documentation/coreml/mlcomputeunits)
- [Apple: output backing buffers](https://developer.apple.com/documentation/coreml/mlpredictionoptions/outputbackings)
- [Apple: Core ML compute plans](https://developer.apple.com/documentation/coreml/mlcomputeplan-1w21n)
- [Apple WWDC22: IOSurface and output-buffer management](https://developer.apple.com/videos/play/wwdc2022/10027/)

The generator is original experiment code and does not copy model source from an
external repository. coremltools is a build dependency under Apple's BSD-3-Clause
license. Preserve its license if redistributing the library itself; this bundle
does not include the library. The analytical weight tensor has no external model
license or pretrained provenance claim.
