# MeloNX after IPA 764: what the journals measure, and the lot that follows — 17 November 2026

Maintainer request (16 Nov, with the IPA 764 journals): Hogwarts Legacy sent the app back to the home screen in the
castle courtyard, the performance did not change there and it is very unstable; the fog effect seen before appears when
the camera is lowered towards the ground and turned. Super Smash Bros. Ultimate still has a few light stutters. Find the
causes, a real update of the emulator; better RAM management with the system already in the emulator.

Sources: IPA 764 (MeloNX Core `a80b212f`, iPhone 16 Pro Max, 8 GB), two Hogwarts Legacy sessions (pids 28304, 28682)
and one SSBU session (pid 29271). The journals are private; only counts and times are written here. Tools: the 5 s
render-stage records, the per-second lines, the `[MeloNX:hot]` profile with the Core's symbol map, the native heap
record symbolised with the rebuilt MoltenVK, MoltenVK's own statistics, the memory inventory and trim records.

## 1. Super Smash Bros. Ultimate: the change of IPA 764 works, single compiles remain

- 243 s of play in 48 windows, 57.3 frames per second on average.
- `adapt_draw_wait_lanes` acts on the device: 86 draws waited for a first compile, 5 948 ms in all, while the compile
  threads spent 9 146 ms on 93 compiles (98 ms each); 70 programs were created during those waits and 44 compiles were
  started ahead by the demand thread. Before, the waits equalled the compile time (IPA 760: 25.7 s against 24.8 s).
- What remains in the gaps the freeze watch sampled (14 gaps of 100 ms or more): a single first compile (Metal's
  compiler, nothing of the process runs), the game's main thread running translated code for 100 to 190 ms, and one
  background collection. A single first compile keeps its length (about 100 ms: vertex and fragment libraries compiled
  one after the other inside MoltenVK).
- Memory: native heap 1 350 MiB live after 120 s; the first allocation site, 695 MiB, is
  `SPIRVToMSLConverter::setSPIRV` in the `MVKShaderModule` constructor: MoltenVK keeps the SPIR-V words of each of the
  22 490 shader modules for their whole life, while the session converted 177 of them (MoltenVK statistics: 11 797
  pipelines from functions, 11 663 libraries, almost all from the Metal cache). Second site: Metal libraries, 204 MiB.

## 2. Hogwarts Legacy in the courtyard: the phone runs out of memory

- Session 28682: at the courtyard entry (second 50 to 51) the footprint goes from 3 758 to 4 346 MiB in one second, then
  4 511, 4 571, 4 637 MiB; the device's available memory falls from 8 to 4 %; hundreds of thousands of pages are
  decompressed in the intervals the per-second sampler could still write. The process is then ended by iOS (no crash
  record), right after the screen recording started. Session 28304 ends the same way at 4 % device available.
- The render thread is busy 3.3 to 3.6 s of each 5 s (66 to 79 frames, 13 to 16 per second; 1 300 to 1 750 draws per
  frame). Draw preparation takes 1.3 to 1.7 s per window, of which descriptor updates 1.07 to 1.50 s; compute descriptor
  updates 300 to 490 ms (about 58 µs per dispatch); submissions 660 to 720 per window (310 to 630 ms). GPU busy 30 %.
  In the profile of second 70, 19 of the 23 samples under the descriptor set update are inside MoltenVK's template
  write, and 15 % of the render thread's running samples are in the kernel: a thread that touches compressed memory
  faults, so memory pressure makes every CPU cost of the engine larger.
- The memory budget system (host memory budget, cache trims, cold texture release, compactions) runs and is right, but
  has little to give back there:
  - GPU caches 155 of 768 MiB (textures) and 120 of 554 MiB (buffers); trims released 8 to 124 MiB.
  - Cold texture release: 8 782 textures only a pool holds (192 to 206 MiB), none unused for 60 s, in all 105 passes of
    every journal available. Hogwarts samples through bindless texture arrays: each array update stamps every element as
    used, and the engine cannot know which elements a shader reads, so those textures must stay. A shorter age would
    release nothing safely (an element on a destroyed view samples black); not changed.
  - Compactions: first frame 2 969 to 2 729 MiB, a 933 ms loading gap 3 797 to 3 522 MiB. Then, in the next 30 s, the
    managed heap commits 434 to 766 MiB (28304: live large objects 212 to 444 MiB), Vulkan buffers 107 to 216 MiB.
- So the lever in the courtyard is memory the engine itself holds without using it. The largest such item measured is
  MoltenVK's copy of the SPIR-V: 205 MiB in Hogwarts (IPA 759), 695 MiB in SSBU.

## 3. The change: MoltenVK keeps the SPIR-V compressed (recipe patch, sixth part)

- `MVKShaderModule` keeps its SPIR-V compressed with LZ4 (`mvkCompress`, the codec MoltenVK already uses for the MSL it
  retains; MeloNX sets `MVK_CONFIG_SHADER_COMPRESSION_ALGORITHM=3` for that); words LZ4 does not make smaller are kept
  as given. A conversion to MSL decompresses a copy into a converter of its own; `getSPIRV()` returns a copy.
- `getShaderInterfaceVariables()`: the interface of a stage (vertex outputs, tessellation inputs and outputs) is
  reflected once per module, storage class, stage and entry point, then copied out; every graphics pipeline used to
  parse and reflect its vertex shader's SPIR-V again. Same reflection code, same container type as before.
- Not changed: what is converted and how, the conversion configurations, the libraries, the pipeline cache keys and
  data, the pipelines; no draw, effect, resolution or setting. `MVK_CONFIG_REWINDBOX_RAW_SPIRV` keeps the words as given
  (the control; nothing sets it in the app). Every title running on MeloNX goes through it.
- Expected on the device, to be read in the native heap record: the `setSPIRV` site disappears and a smaller
  compression site takes its place (about a third of 695 MiB for SSBU if Ryujinx's SPIR-V compresses as SPIR-V usually
  does with LZ4); the footprint falls by the difference. Refuted if the heap record shows no such fall. No frame rate
  gain is claimed.

| Step | State |
| --- | --- |
| Implemented | Yes: `build-utils/melonx/moltenvk/rewindbox-moltenvk.patch` (`fa274300`), sixth marker in `moltenvk-rebuild.json` |
| Tested | The patch applies to v1.4.2 (`db660224`) and regenerates byte for byte; drawable ownership check passes; the Core gates' predicates on the patch hold. On a real Metal device: the cache keys measure (macOS runner, pipelines built from SPIR-V, pixels checked) runs on this change |
| Compiled | MoltenVK rebuild for iOS (`melonx-moltenvk-rebuild.yml`) on this change |
| Delivered | Next private IPA after 765 |
| Observed on a device | No |

## 4. Leads not taken

- The vertex and fragment libraries of one pipeline compiled at the same time inside MoltenVK (a single first compile
  would lose 25 to 35 ms in SSBU). Needs a restructuring of `MVKGraphicsPipeline`'s creation; to be proven on macOS.
- Descriptor updates in Hogwarts: the cost is inside MoltenVK's write and grows with memory pressure. A breakdown
  (set allocation, buffer mirrors, MoltenVK write, extra sets) is the measure that would show what to change.
- Push descriptors are capped at 8 on MoltenVK (MeloNX's own limit), so Hogwarts' programs rewrite whole uniform sets;
  raising the cap changes how every title binds uniforms and needs its own proof.
- The large objects that become live in the courtyard (28304: +232 MiB in 30 s) are not identified; a census by type
  would say which can go. No forced collection during play.
- The fog effect: the journals hold no picture of it, and the recording ended with the process. A few screenshots, or
  a short recording in a lighter place, would allow a diagnosis.
