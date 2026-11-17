# MeloNX after IPA 773: Hogwarts Legacy courtyard frame rate — 17 November 2026

Private journals and screen recording of the maintainer's test of IPA 773 (Core 9546deb7, MoltenVK eight parts, the
journal's start/warning breakdowns, the session exit record). Hogwarts Legacy, pid 37647, 16:59:25-17:02:22 UTC. No
crash: the session closed normally. Counts and times only; no raw journal in Git.

## 1. What limits the courtyard

- Courtyard (20 windows of 5 s, t = 52-171 s): 18.9 frames per second on average, about 55 ms per frame (771: 22.2).
  The recording (17:00:57-17:01:07) shows about 12 frames per second after a resume, with a 1.1 s freeze.
- The host render thread's work sets the frame time: frame ms ~ 1.12 x render busy + 17 (r = 0.95). Per frame:
  descriptor updates 12.9 ms (draws about 9, compute 4.4; a compute dispatch's update about 76 us against 6.2 us per
  draw), submits 5.4 ms (8.3 command buffers per frame, about half from strict syncs), CreateSync about 4 ms, command
  buffer pool about 3 ms, texture array passes about 4 ms, BufferSetData 3.1 ms; the guest waits on host syncs about
  13 ms per frame. GPU busy 33-41 % (about 18 ms per frame): headroom. No pipeline compile in play. No guest thread
  near 100 %.
- Memory makes it worse and causes the freezes: footprint +1 GiB at the courtyard entry (t = 46-47 s: graphics +652
  MiB, Metal's allocated size 718 -> 1 425 MB while Vulkan device memory is 679-766 MiB), device at 4-6 % available
  from then on, up to 151 000 pages decompressed in one second, stalls of 0.4-2.4 s, 18 collections of 36-250 ms in
  the courtyard (gen0 pauses of 215-250 ms for under 13 MiB promoted).

## 2. Memory owners (the new breakdowns)

- Before the game: 1 461 MiB, of which about 880 MiB is anonymous shared memory in small regions matching the JIT
  arena's two views (inferred: the walk does not read residency of shared regions under 1 MiB).
- At the warning: graphics 1 317 MiB; native heap 476 MiB live in sampled stacks: Metal libraries 129 MiB
  (MVKShaderLibraryCompiler), MoltenVK descriptor pools 61 MiB, LightningJit address tables 51 MiB, AGX 41 MiB,
  pipeline states 42 MiB; no SPIR-V site (the eighth part works). Malloc churn about 237 MiB/s, not attributed.
- The shader load change of Core 9546deb7 shows no effect at load for Hogwarts (large object heap 531 MiB, 195 free,
  as in 771): its cause is still open.

## 3. Next lot, by expected gain

| Change | Evidence | Expected | Status |
| --- | --- | --- | --- |
| Compute dispatches: keep descriptor sets bound when nothing changed | 4.4 ms per frame, 76 us per dispatch | -2 to -4 ms per frame | Investigation and prototype |
| Graphics: reuse a set whose template payload is identical | about 9 ms per frame | -3 to -5 ms per frame if about 40 % repeat | Measure the repeat rate first |
| Strict syncs ride the next flush | submits + CreateSync + pool about 12 ms per frame | -3 to -6 ms per frame | Semantics to check |
| Cached Metal libraries compiled at first use (MoltenVK ninth part) | 129 MiB live site | -60 to -200 MiB | Next MoltenVK part |
| Sub-allocate small Vulkan buffers | 13.5-15.8k dedicated blocks, Metal 0.6 GiB above Vulkan | -50 to -250 MiB | Measure the difference first |
| Journal: the per-second sampler stopped at t = 98 (its memory call starved for 3.3 s) | diagnostics | complete journals | Bridge fix |
