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
- Inside MoltenVK's descriptor write, each texture descriptor sends several Objective-C messages (the view's base texture
  check, height and bytes per row for the CPU copy, the resource ID for the argument buffer), each buffer descriptor its
  GPU address. Taken in the next lot (§ 5.1).
- The large objects that become live in the courtyard (28304: +232 MiB in 30 s) are not identified; a census by type
  would say which can go. No forced collection during play.
- The fog effect: the journals hold no picture of it, and the recording ended with the process. A few screenshots, or
  a short recording in a lighter place, would allow a diagnosis.

## 5. The lot for the next IPA (17 Nov): every change drawn from these journals

Maintainer request (17 Nov): hold 30 frames per second outside the castle, a stable frame rate and smooth play; look at
the shader cache; "one or two fixes must not be the conclusion"; one IPA only once the fixes the journals support are in.
Five readings of the journals (texture array barriers, submissions, compute dispatches, the shader cache, the GPU
thread) gave the changes below. None is specific to Hogwarts Legacy: each is exact (same draws, same barriers, same
descriptors, same values) and applies to every title. No frame rate gain is claimed before the device's journals.

### 5.1 MoltenVK, recipe patch seventh part: descriptor writes read what does not change once

- `MVKImageViewPlane::getMTLTexture()`: a view whose own base is the image's texture (the first test of
  `matchesMTLTextureViewBase()`; the view retains that base) is remembered with it, under the view's lock, only if it is
  still the current view and nothing was released since its check; it is forgotten in the same write as its release. The
  pair is read without the lock from one even generation that did not change during the reads (a sequence lock). Views
  matched by IOSurface or by root texture (swapchain images) go the checked way each time, as before.
- `MVKBuffer` reads its Metal buffer's GPU address once per binding (cleared on bind and detach; a buffer without a
  Metal buffer reads 0 each time, as before); `MVKSampler` reads its sampler state's resource ID once (cleared on detach).
  The Metal 3 argument buffer encoder uses both; the argument encoder mode is unchanged.
- Why: render thread profile in the courtyard (14.6 FPS), 37 of 221 running samples inside
  `mvkUpdateDescriptorSetWithTemplate`, 16 under `getMTLTexture`, 12 in the base comparison, 17 in the Objective-C runtime.
- Checked: the patch applies to v1.4.2 and regenerates byte for byte; drawable ownership check and the Core gates'
  predicates on the patch pass; iOS rebuild run `43993431320` (binary `5c34831d`, markers 7/7), pinned (`29821b95`);
  cache keys measure on macOS, run `43993431075`: 780 modules, 2 160 pipelines, the same bytes and keys as the sixth part,
  24 draws per run, 0 wrong pixels, pixels equal to the control's. The macos-26 runners now expose a paravirtual GPU
  (family Apple 5) that binds with an argument encoder, not Metal 3 argument buffers as on the iPhone; the descriptor
  cost comparison of the sixth and seventh parts on the same runner records that mode (run `43995838884`).

### 5.2 Core: a texture array's barrier pass calls only the storages that were ever attachments

`adapt_array_attachment_members` (TextureStorage.cs, TextureArray.cs). In a 5 s courtyard window the render thread ran
22 413 texture array barrier passes over 1 053 305 storages (47 per pass, 119.7 ms; 258.8 ms under memory pressure),
while every source together queued 9 916 barriers. The epoch skip of `adapt_array_barrier_epoch` is global, and the
window has 7 346 render passes. A storage never stored or loaded as an attachment has no modification, no covered read
and no reset of its read stages, so once a full pass over an unchanged set gave it the stages asked, its call changes
nothing. A pass over the same set, for covered stages, while no storage of the set became an attachment since (a ring
of the last 64 such storages; more: a full pass), now calls only the storages that were attachments, in the set's order.
Checked with a model of both classes: 6 000 random sequences of 4 000 operations on three driver configurations give the
same barrier log and states, also with a ring of 4; three deliberate mutations are caught. Computed 40 to 100 ms per 5 s
window; the barrier line gains the member passes and the storages ever attachments.

### 5.3 Core: a finished command buffer clears its dependants' bits, then releases them

`adapt_release_passes` (Auto.cs, CommandBufferPool.cs). The 660 to 720 submissions of a window cost 310 to 630 ms: in
the profile, `Rent` holds 17 samples, 10 of them freeing the finished command buffer, 6 on the one indirect call per
dependant, 7 in MoltenVK's reset; no lock wait. A main command buffer holds about 1 000 to 2 600 dependants, and each
release was an interlocked decrement (a full barrier on ARMv8.0) before the next dependant's loads could start. The
ownership bits of every dependant are now cleared first, then the releases follow, in the same order: same clears, same
releases, no dependant released before its bits are cleared. Computed 40 to 60 ms per window; it depends on the caches.

### 5.4 Core: the pipeline cache keeps what a session compiles

`adapt_empty_worker_snapshot` (PipelineCacheManager.cs). Both Hogwarts launches loaded the same 97.08 MiB main file with
"1/1 worker snapshots (0,04 KiB) joined", made the same 85 SPIR-V to MSL conversions and missed the same 47 worker
creations, and the file never grew: the empty worker file (a cache's header alone) joined main and held every worker's
file until main was written, which the sessions never reached (one was ended by iOS at 87 s, the pause refused +1.17 MiB
under its 8 MiB rule). Beside a main snapshot, a worker file of 64 bytes or less is now read as no file: the workers
write their caches during play, as in the Super Smash Bros. Ultimate sessions (file 121.6 to 128.9 MiB). The pause and
play rules are unchanged (a gate pins the pause rule; a change there is a separate decision). Expected: the launch line
reads "0/0 worker snapshots", and later launches make fewer conversions; courtyard states (14 conversions, 9 then 2 draws
skipped while they compiled) are written by the workers before a session ends.

### 5.5 Core: a bindless array entry walks its own textures when the change ring to read is longer

`adapt_array_walk_size` (TextureBindingsArrayCache.cs). The GPU thread runs 157 of 300 samples of the courtyard profile
(about 36 ms per frame; the render thread waits for its commands in 75 samples): the bindless arrays hold 23, under them
`CacheEntry.SynchronizeMemory` at least 11 and `MayContain` 4 of its own, called only by the walks of the global change
rings. An array of handles in a constant buffer covers the whole buffer but holds few textures, and there are many such
entries, each used rarely: at each use they read the ring from their last complete state (up to 1 024 entries, up to
three rounds). The ring is now read only while its entries to read are not more than the set's textures; otherwise the
complete walk runs, the code the entry already runs whenever the ring is not read (a texture with nothing to synchronise
costs one store and two tests). Same textures, samplers, arrays and uploads; never more visits than before. Computed 5 to
7 of the GPU thread's 157 samples (about 1.1 to 1.6 ms per frame); no gain for the pool arrays.

### 5.6 What the readings found and left

- Compute dispatches (about 58 us each): about 13 us of main sets, 35 us of reference passes of the bindless arrays
  (once per command buffer, about 2 000 views and samplers; the ownership model requires it) and 11 us of slot writes.
  No exact descriptor change removes it; each command buffer costs about 0.3 to 0.4 ms there and about 0.45 ms in `Rent`.
  The number of command buffers (686 per window: 328 strict syncs, 216 automatic flushes) is the lever; it must be
  measured by cause before any change to the flush policy.
- Shader cache: outdoors it already serves everything (2 110 programs from the disk cache, no module created after the
  launch, no draw waiting for a compile). The pipeline lookup of each draw costs 32 to 103 ms per window (small). Metal
  libraries compiled on demand were measured on macOS before and refuted (no memory given back).
- GPU thread, larger leads not taken without a proof of exactness or gain: the pool arrays' delta passes in compute
  dispatches (218 to 673 ms per window; their fallbacks to a complete walk must first be counted by cause), the buffer
  lookups (`OverlapsWith` 8 samples on a hit table miss), the address translations (`HasAnyPrivateAllocation` 10), the
  buffer textures resolved again at each draw (about 3.5 per draw).
- Memory: the large object heap holds 216 to 444 MiB live and up to 306 MiB of free space after collections; the
  engine's own array pool is bounded (64 MiB of spares, released after 3 s) and the bindless arrays hold a stable 90 MiB;
  mirror copies hold 16 to 33 MiB. What becomes live in the courtyard (+232 MiB in 30 s) is still not identified.

| Change | Implemented | Tested | Compiled | Delivered | Observed on a device |
| --- | --- | --- | --- | --- | --- |
| 5.1 MoltenVK seventh part | Yes | macOS pixels and keys, patch checks | iOS, pinned | Next IPA | No |
| 5.2 to 5.5 Core adapters | Yes | Vulkan and GPU assemblies built; 111 gates on the final preparation (in progress) | Core build pending | Next IPA | No |
