# Hogwarts Legacy on IPA 614 — iPhone measurement and next levers (2 November 2026)

Session: build 614, PID 64582, Core `b181cbe1` (ios-arm64 `7816830c…`), title
`0100f7e00c70e000`, 13:40:02–13:42:35 UTC, first Metal presentation at 13:40:11. Same
settings as the 612 reference (PID 63118): resolution 1×, shader cache on, asynchronous
shaders off, Switch VSync, threading on, HostMappedUnsafe. Thermal state `nominal` until
t=113 s, then `fair` (612: `fair` from t=27 s, `serious` from t=112 s).

## Effect of the bindless array deltas (612 → 614, active play, 5.1 s windows)

| | 612 (PID 63118) | 614 (PID 64582) |
|---|---|---|
| FPS (per-second samples) | about 3 (2.1–3.9) | about 10–11 (9.1–11.8) |
| Managed allocations | 240–330 MiB/s | 7–20 MiB/s |
| GC pauses | 45–155 ms/s | 2–8 ms/s |
| Gen 2 collections per window | 7–9 | 0 (one window: 1) |
| `compute` per window | 3.5–4.1 s | 1.03–1.24 s |
| Compute dispatches per window | 400–1300 | 2500–3700 |

The cost removed by 614 was the one attributed in
[the deltas note](melonx-bindless-deltas-2026-11-02.md). The new counters confirm the path:
`arrFullElems` is 0 in most windows, `arrBufElems` is small (4,600–43,000 elements per window:
the buffer-handle arrays are not the hot ones), and the delta passes carry the work.

## What limits 614 (steady windows, lines 634 and 659 of the performance journal)

- The GPU thread is busy for the whole window (`gpuDispatch` 5.07–5.12 s of 5.10 s), but its
  own CPU use is about 30 % (GPU.MainThread 28–33 %): it mostly waits.
- **`dma` 2.95–3.46 s, almost all `texFlushAction` 2.94–3.45 s**: 50–55 texture flush actions
  per window, one per presented frame, 55–69 ms each. During them the GPU thread waits for the
  render thread (`syncInvoke` 3.42–3.48 s). A flush action is the memory-tracking action of a
  GPU-written texture; inside the DMA engine it fires when a 2D copy reads its source through
  guest memory. `bufferReadback` (fence waits) 1.68–1.69 s, 12,800–14,000 per window.
- **`arrayDelta` 1.03–1.12 s** (the delta pass): about 245 passes of 524,288 elements per
  window (`arrDeltaElems` ≈ 125 M), about 30 changed elements per pass (`arrDeltaChanged`
  6,000–8,000). Every pass had a change, so every pass also ran the verification scan.
- Render thread (`NeoStation.MeloNX.Render`) 49–55 % CPU; `renderDrain` 4.37–4.42 s of the
  window, `renderIdle` 0.70–0.72 s. Draws 50,000–83,000 per window (about 1,100–1,500 per
  frame), barrier requests about 3,600.

## Cause of the per-frame read-back (source)

`DmaClass.DmaCopy` copies a block-linear texture on the GPU (`source.HostTexture.CopyTo`) only
if the copy is complete and identity-remapped, the source texture exists with the copied
height, and its format is not `R32G32B32A32Float` or `R16G16B16A16Float`. That format
exclusion is not in Ryujinx; MeloNX added it in its iOS port (`cf9d3054`, "Full iOS
Implementation", no recorded reason). For those formats every DMA copy reads the texture back
synchronously (flush action), de-swizzles it on the CPU and writes guest memory, which the GPU
uploads again. Unreal Engine 4 keeps its HDR scene colour and temporal history in
`R16G16B16A16Float`. This is the leading hypothesis for the per-frame flush; the next Core
logs the attribution of every 2D copy that still goes through guest memory, so the device run
confirms or refutes it.

## Next Core (in preparation; not measured)

1. `adapt_hogwarts_dma_copies.py`: the GPU-side copy for the two float formats, for Hogwarts
   Legacy only (`GraphicsConfig.HogwartsFloatDmaGpuCopy`, set from the launched title), and
   bounded attribution of the remaining guest-memory copies (24 signatures logged once, counts
   per reason every 1024 copies).
2. The bindless delta pass skips its verification scan when no texture was invalidated during
   the pass (a global epoch moved by every `InvalidatedSequence` increment): about half of the
   1.03–1.12 s per window.

Expected limits afterwards (to be measured): the render thread (about 50 ms of CPU per frame at
the 614 frame rate) and the remaining comparison scan. 30 FPS needs both reduced.
