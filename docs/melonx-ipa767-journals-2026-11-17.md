# MeloNX after IPA 767: what the journals measure, and the lot that follows — 17 November 2026

Private journals of the maintainer's test of IPA 767 (it carries the MeloNX lot of IPA 766: MoltenVK with the seven-part
recipe patch, Core 58319c2c). Two sessions: Hogwarts Legacy (pid 32106, 95 s) and Super Smash Bros. Ultimate (pid 32759,
12 min). Counts and times only; no raw journal is kept in Git. Maintainer's report: Hogwarts sent back to the iPhone's
home screen, RewindBox left in the background, frame rate "slightly more stable"; SSBU "almost no more stutter".

## 1. Hogwarts Legacy: the courtyard still runs the phone out of memory

- Before the game loads (the session's first lifecycle line): footprint 1 454 MiB, 5 201 MiB available to the process,
  device 30 % available. The same 1 452 to 1 454 MiB starts every session of these journals; no journal says what it is.
- Courtyard: the footprint goes from 3.6-3.9 GiB to 4.69 GiB in one second at t=46 (83 250 pages decompressed in that
  second), then 4.3-4.6 GiB; the device's available memory falls from 25 % to 4 %. Memory warnings at t=46 and t=47.
  The per-second sampler stops writing at t=62; the stall watch then sees its own threads return after 0.7 to 1.4 s
  (memory, audio, frame counters). iOS ends the process about 95 s into the session with 1.6 to 2.0 GiB still available
  to it: the device ran out, not the process's limit.
- What the footprint holds at t=30 (3 939 MiB): malloc zone 681 MiB in use (769 held), private anonymous 571 MiB
  resident + 348 MiB compressed, the guest memory lease 907 MiB resident, graphics 557 MiB + 110 compressed. At 4.9 GiB
  (t≈70): managed heap 798 MiB committed (large object heap 444 MiB of which 152 MiB free), Vulkan device memory 667 MiB
  (images 449, buffers 217), texture cache 108 MiB, buffer cache 133 MiB, mirror copies 49 MiB. The native heap window
  (120 s) never closed: Hogwarts' native heap was not reported in this session.
- Frame rate: 30 per second before the courtyard (paced 2 x 16.7 ms), 20 to 23 in it. The render thread is busy 3.0 to
  3.3 s of each 5 s (descriptor updates 0.76 to 0.99 s, draws 1.0 to 1.2 s, submits 0.36 to 0.44 s); the GPU is busy 33 %.
- What the lot of IPA 766 did on the device:
  - texture array barrier passes: 25 000 to 41 000 attachment member passes over 2 000 to 4 000 storages, and 1 700 to
    3 400 full passes over 0.6 to 0.9 million storages per window (IPA 764: 22 413 full passes over 1.05 million); still
    87 to 117 ms per window, the full passes being those whose set was rebuilt;
  - pipeline cache: the worker wrote its snapshot (1.55 MiB at t=20; IPA 764 wrote nothing); 2 176 worker pipelines found
    in the main cache, 14 not; no draw waited for a compile in play;
  - SPIR-V store: SSBU's live native heap went from 1 350 to 1 023 MiB (below).

## 2. Super Smash Bros. Ultimate: stutter almost gone; what remains is memory pressure

- 724 s with frames: 59.3 per second on average, 5th percentile 56.0, 30 s under 55.
- 35 gaps of 100 ms or more, 12 of 200 ms or more, the longest 1.37 s. The 650 ms gap of frame 16 399 is the engine's own
  blocking gen2 collection (675 ms pause, chosen by the GC) running on the GPU thread, with 34 967 pages decompressed
  inside it: the collector marks memory iOS had compressed.
- Managed heap: the large object heap holds 735 MiB, of which about 490 MiB free, for the last eight minutes (filled
  during the first minute, never compacted).
- Native heap after 120 s: 1 023 MiB live (IPA 764: 1 350). First site: MVKShaderModule::setSPIRV, the SPIR-V store of
  22 490 modules, 358 MiB (695 before the sixth part); then Metal libraries 201 MiB (MVKShaderLibraryCompiler), the AGX
  driver's own allocations (70, 51, 42, 37 MiB), the shader library cache merges 29 MiB.

## 3. The lot (next IPA after 767)

| Change | Why (these journals) | Implemented | Tested | Compiled | Delivered | Observed on a device |
| --- | --- | --- | --- | --- | --- | --- |
| MoltenVK, eighth part: a shader module's compressed SPIR-V in an unlinked temporary file of the process, read back (pread) for each use | 358 MiB of SSBU's native heap; Hogwarts ended at 4 % device available | Yes (patch 4e279c68) | Patch regenerates byte for byte; drawable ownership and warmup key parity pass; macOS cache keys measure on this change | iOS rebuild on this change | Next IPA | No |
| Journal: footprint breakdown at the start and at the first memory warning; native heap report at that warning | 1.45 GiB before the game, unexplained; Hogwarts' heap never reported | Yes | 63 source checks; Swift compiled by melonx-host on macOS | With the app | Next IPA | No |
| Core contract frozen again (the patch is one of its inputs), same Core code | The delivery checks every Core input | After the MoltenVK pin | The three gates reading the patch rerun and pass | Core build | Next IPA | No |

The SPIR-V store is about 100 MiB of Hogwarts' footprint by the IPA 759 measure (205 MiB before compression): it does
not by itself give the courtyard the memory it lacks. The two journal records are there to say, at the next test, what
the 1.45 GiB before the game are and what the native heap holds when the courtyard starts.

## 4. Leads read and not taken

- Large object heap free space (SSBU about 490 MiB, Hogwarts 150 to 270 MiB): compacting it with the GC's own blocking
  collections would lengthen those pauses (the 650 ms gap) and is a global GC change; not taken without a measure.
- A stronger codec for the SPIR-V store (LZFSE): about 30 % smaller than LZ4 on the SPIR-V available here (27 engine
  helper shaders: LZ4-style 1.88, zlib 2.53); superseded by the file, which takes the store out of the footprint.
- Render thread in the courtyard: descriptor updates (7.5 million descriptors per 5 s), command buffer release
  (CommandBufferPool.FreeConsumed and Rent: 22 of 178 running samples), submissions (0.45 ms each); unchanged here.
- Bindless texture arrays: 42 MiB of per-element delta state and 48 MiB of element arrays in Hogwarts; unchanged.
