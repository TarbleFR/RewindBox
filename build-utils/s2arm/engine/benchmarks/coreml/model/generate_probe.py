#!/usr/bin/env python3
"""Generate a real Core ML fixed-filter probe; no downloaded/trained weights.

This measures Core ML execution/transport, NOT learned super-resolution quality.
RGB input NCHW (1,3,H,W), output (1,3,2H,2W), both exposed as image features.
Requires coremltools==9.0 and numpy==2.2.6. Conversion also works on Linux;
prediction and ANE/device placement measurements require Apple hardware.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import coremltools as ct
from coremltools.converters.mil import Builder as mb
from coremltools.proto import FeatureTypes_pb2, MIL_pb2


INPUT_NAME = "inputImage"
OUTPUT_NAME = "outputImage"
KERNEL = np.array([[0, -0.125, 0], [-0.125, 1.5, -0.125], [0, -0.125, 0]], dtype=np.float32)


def reference(rgb: np.ndarray) -> np.ndarray:
    """Float32 mathematical reference; rgb is HWC with values in [0,255].

    Zero-pad convolution, clip BEFORE resizing, then half-pixel bilinear with
    coordinates (o+0.5)/2-0.5 and edge-clamped sampling. Byte output conversion
    may differ by a rounding unit between hardware paths; compare tolerantly.
    """
    image = np.asarray(rgb, dtype=np.float32)
    if image.ndim != 3 or image.shape[-1] != 3:
        raise ValueError("Expected HWC RGB image")
    height, width, _ = image.shape
    padded = np.pad(image, ((1, 1), (1, 1), (0, 0)), mode="constant")
    filtered = np.zeros_like(image)
    for ky in range(3):
        for kx in range(3):
            filtered += KERNEL[ky, kx] * padded[ky:ky + height, kx:kx + width]
    filtered = np.clip(filtered, 0.0, 255.0)
    y = np.clip((np.arange(2 * height, dtype=np.float32) + 0.5) * 0.5 - 0.5, 0, height - 1)
    x = np.clip((np.arange(2 * width, dtype=np.float32) + 0.5) * 0.5 - 0.5, 0, width - 1)
    y0, x0 = np.floor(y).astype(np.int32), np.floor(x).astype(np.int32)
    y1, x1 = np.minimum(y0 + 1, height - 1), np.minimum(x0 + 1, width - 1)
    wy, wx = (y - y0)[:, None, None], (x - x0)[None, :, None]
    top = filtered[y0[:, None], x0[None, :]] * (1 - wx) + filtered[y0[:, None], x1[None, :]] * wx
    bottom = filtered[y1[:, None], x0[None, :]] * (1 - wx) + filtered[y1[:, None], x1[None, :]] * wx
    return (top * (1 - wy) + bottom * wy).astype(np.float32)


def reference_checks() -> dict:
    zero = reference(np.zeros((8, 8, 3), dtype=np.float32))
    assert zero.shape == (16, 16, 3) and np.count_nonzero(zero) == 0
    image = np.full((8, 8, 3), 128.0, dtype=np.float32)
    constant = reference(image)
    assert np.all(constant[4:12, 4:12] == 128)
    # The zero boundary is deliberate and must match the Metal implementation.
    assert constant[0, 0, 0] == 160
    image[4, 4] = 160
    impulse = reference(image)
    # Filtered center=176, cross neighbors=124, diagonals=128. At (8,8),
    # the source coordinate is (3.75,3.75): 176*.5625+124*.375+128*.0625.
    assert np.all(impulse[8, 8] == 153.5)
    assert np.all(impulse[8, 8] != 146.0)  # pure bilinear would produce 146
    assert impulse.min() >= 0 and impulse.max() <= 255
    return {"passed": True, "scope": "NumPy reference math only; not Core ML inference", "nonidentity_probe_pixel": float(impulse[8, 8, 0])}


def generate(width: int, height: int, output: Path) -> dict:
    if min(width, height) < 2 or max(width, height) > 8192:
        raise ValueError("Width/height must each be between 2 and 8192")
    weights = np.repeat(KERNEL[None, None, :, :], 3, axis=0)

    @mb.program(input_specs=[mb.TensorSpec(shape=(1, 3, height, width))], opset_version=ct.target.iOS16)
    def program(inputImage):
        filtered = mb.conv(x=inputImage, weight=weights, groups=3, strides=[1, 1],
                           pad_type="same", name="unsharp_zero_padded")
        clipped = mb.clip(x=filtered, alpha=0.0, beta=255.0, name="clip_before_resize")
        return mb.upsample_bilinear(x=clipped, scale_factor_height=2.0,
                                   scale_factor_width=2.0, align_corners=False,
                                   half_pixel_centers=True, name=OUTPUT_NAME)

    # The MIL frontend in coremltools 9 reads input types from convert(), but
    # output types must also be attached to the MIL function explicitly.
    program.functions["main"].set_output_types([
        ct.ImageType(name=OUTPUT_NAME, color_layout=ct.colorlayout.RGB)
    ])
    model = ct.convert(
        program,
        convert_to="mlprogram",
        inputs=[ct.ImageType(name=INPUT_NAME, shape=(1, 3, height, width),
                             color_layout=ct.colorlayout.RGB, scale=1.0)],
        outputs=[ct.ImageType(name=OUTPUT_NAME, color_layout=ct.colorlayout.RGB)],
        minimum_deployment_target=ct.target.iOS16,
        compute_precision=ct.precision.FLOAT16,
        skip_model_load=True,
    )
    model.author = "RewindBox experiment"
    model.short_description = "Fixed unsharp + 2x bilinear Core ML execution probe; not learned super-resolution"
    model.input_description[INPUT_NAME] = "RGB bytes, zero-padded 3x3 convolution; BGRA CVPixelBuffer"
    model.output_description[OUTPUT_NAME] = "2x RGB image; clip before half-pixel bilinear interpolation"
    model.user_defined_metadata["rewindbox.probe_kind"] = "deterministic-unsharp-bilinear-not-learned"
    model.user_defined_metadata["rewindbox.kernel"] = json.dumps(KERNEL.tolist())
    model.user_defined_metadata["rewindbox.boundary"] = "convolution=zeros; resize=clamp_to_edge"
    model.user_defined_metadata["rewindbox.order"] = "convolution,clip(0..255),bilinear(2x,half_pixel_centers)"
    model.user_defined_metadata["rewindbox.ane_status"] = "unmeasured; cpuAndNeuralEngine is permission, not proof of ANE execution"
    model.user_defined_metadata["rewindbox.weights_provenance"] = "analytical coefficients written in generate_probe.py; no pretrained weights or dataset"
    output.parent.mkdir(parents=True, exist_ok=True)
    model.save(str(output))

    spec = model.get_spec()
    assert spec.WhichOneof("Type") == "mlProgram"
    assert spec.description.input[0].name == INPUT_NAME
    assert spec.description.output[0].name == OUTPUT_NAME
    assert spec.description.input[0].type.WhichOneof("Type") == "imageType"
    assert spec.description.output[0].type.WhichOneof("Type") == "imageType"
    assert spec.description.input[0].type.imageType.colorSpace == FeatureTypes_pb2.ImageFeatureType.RGB
    assert spec.description.output[0].type.imageType.colorSpace == FeatureTypes_pb2.ImageFeatureType.RGB
    assert spec.description.input[0].type.imageType.width == width
    assert spec.description.input[0].type.imageType.height == height
    assert spec.description.output[0].type.imageType.width == 2 * width
    assert spec.description.output[0].type.imageType.height == 2 * height
    graph_ops = [op for function in spec.mlProgram.functions.values()
                 for block in function.block_specializations.values() for op in block.operations]
    operations = [op.type for op in graph_ops]
    for expected in ["conv", "clip", "upsample_bilinear"]:
        assert expected in operations, (expected, operations)
        for op in graph_ops:
            if op.type == expected:
                assert op.outputs[0].type.tensorType.dataType == MIL_pb2.FLOAT16
    files = {str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sorted(output.rglob("*")) if p.is_file()}
    report = {
        "model": output.name,
        "coremltools": ct.__version__,
        "input": {"name": INPUT_NAME, "shape_nchw": [1, 3, height, width], "image_type": "RGB", "pixel_buffer": "32BGRA"},
        "output": {"name": OUTPUT_NAME, "shape_nchw": [1, 3, 2 * height, 2 * width], "image_type": "RGB", "pixel_buffer": "32BGRA"},
        "kernel": KERNEL.tolist(), "convolution_boundary": "zero", "clip": [0, 255],
        "order": ["depthwise_conv", "clip", "2x_bilinear"],
        "resize": {"align_corners": False, "half_pixel_centers": True, "boundary": "clamp_to_edge"},
        "execution_precision": "fp16", "minimum_deployment_target": "iOS16/macOS13",
        "operations": operations, "learned": False,
        "coreml_prediction_executed": False, "ane_execution_verified": False,
        "verification": reference_checks(), "sha256": files,
    }
    output.with_suffix(".manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--width", type=int, default=320)
    parser.add_argument("--height", type=int, default=180)
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "ReconstructionProbe.mlpackage")
    args = parser.parse_args()
    print(json.dumps(generate(args.width, args.height, args.output), indent=2))
