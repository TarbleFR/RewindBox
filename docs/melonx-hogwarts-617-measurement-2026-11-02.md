# Hogwarts Legacy on IPA 617 — iPhone measurement and the next lever (2 November 2026)

Session: build 617, PID 65478, Core `88c4cb85` (ios-arm64 `6d9bf835…`), title
`0100f7e00c70e000`, 17:10:00–17:11:56 UTC, first Metal presentation at 17:10:09. Same
settings as the 614 reference (PID 64582). Thermal state `nominal` for the whole session.

## Effect of the 617 Core (614 → 617, steady play, 5.1 s windows)

| | 614 (PID 64582) | 617 (PID 65478) |
|---|---|---|
| FPS in play (per-second samples) | about 10–11 | about 12–15 (11.9–17.1) |
| `arrayDelta` per window | 1.03–1.12 s | 0.15–0.22 s |
| `arrDeltaElems` per window | about 125 M | 7,000–7.4 M (logged passes) |
| `compute` per window | 1.03–1.24 s | 0.20–0.30 s |
| `dma` / `texFlushAction` per window | 2.95–3.46 s / 50–55 flushes | 2.5–4.2 s / 63–85 flushes (one per frame) |
| `syncInvoke` per window | 3.42–3.48 s | 2.7–4.3 s |
| Draws per window | 50,000–83,000 | 59,000–124,000 |
| Render thread CPU | 49–55 % | 55–70 % |

The logged delta passes removed the scan (six times less `arrayDelta`). The float DMA
policy never applied: `DMA float GPU copy (Hogwarts policy)` was never logged and the
attribution counts `floatFormat 0` for the whole session. That hypothesis is refuted.

## What still costs a frame

One texture flush per frame remains (37–65 ms each), inside the DMA engine, and the GPU
thread waits for the render thread during it (`syncInvoke`): with the delta scan gone it is now
the largest cost of the GPU thread (up to 80 % of a window). In steady play about 21
copies per second still go through guest memory: about 17 partial copies (`incomplete`)
and 4 complete copies from linear memory, all with a linear source and a block-linear
destination (the logged signatures, bpp 1: partial copies of 4×1 to 296×74 bytes, complete
ones of 32×8 to 5120×720 bytes).

Source (`DmaClass.DmaCopy`, guest-memory path): a partial copy reads the destination range
untracked, patches it and writes it back with a tracked `MemoryManager.Write`. The memory
tracking runs a texture's flush action before any CPU read **or write** of memory the GPU
modified (`RegionHandle`: "Action to perform before a read or write"; `TextureGroup`: "A
write from CPU will do a flush before writing its data"). A partial update of a GPU-written
texture therefore reads the whole texture back, waits for the render thread and the GPU,
and uploads the texture again afterwards. About one such copy per frame matches one flush
per frame.

## Next Core (in preparation; not measured)

`adapt_hogwarts_dma_copies.py`, Hogwarts Legacy only (`GraphicsConfig.HogwartsDmaRegionUpload`):
such a copy, when its destination surface is a single-level 2D uncompressed colour texture
of the cache (the lookup of the upstream direct upload of complete copies) without overlaps
of an incompatible layout, is uploaded into that region of the host texture
(`Texture.SetData(data, 0, 0, region)`) after the texture's memory synchronisation, and
guest memory is then patched as before but written untracked: the texture and guest memory
hold the same region, no flush action runs, nothing is uploaded again, and the texture's
modified state is left as it was. Any other copy keeps the tracked guest-memory path. The
summary line now also counts region uploads, declined ones (no texture, layout, format,
incompatible overlap) and guest-memory reads and writes over 2 ms. An independent review of
the first version (texture marked modified, guest memory left unwritten) found four
memory-semantics risks; this form removes them.

What the next run reads: `DMA region upload (Hogwarts policy): …` once; in the
`DMA guest-memory copies:` lines, `regionUploads` against `declined …` and `slowWrites`
against `slowReads` (which access still runs the flush); `texFlushAction`, `syncInvoke`,
`dma` and FPS against the windows above.

Expected limits afterwards (to be measured): the render thread (55–70 % CPU, about 45 ms
per frame at 617 rates) and the buffer read-backs (`bufferReadback` 1.5–1.8 s per window).
