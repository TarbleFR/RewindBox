# Metal binary archives in MoltenVK: prototype (lot 7)

Status: **prototype, not integrated**. MeloNX's MoltenVK (`../moltenvk-rebuild.json`, `patch: null`), its pin and every
Core are unchanged. Nothing here is packaged in an IPA. The decision and the measures are in
`docs/AI_TASK_BOARD.md` (MeloNX lot 7) and `docs/evidence/melonx-lot7-metal-archive/`.

## What it is

`moltenvk-v1.4.2-binary-archives.patch` applies to Khronos MoltenVK v1.4.2 (`db660224`, the revision MeloNX embeds). It
adds `MVKMetalBinaryArchives` (MVKPipeline.h/.mm) and its owner (MVKDevice). Without the environment variable below the
library behaves as upstream.

- **Where**: `MVKRenderPipelineCompiler::newMTLRenderPipelineState` and
  `MVKComputePipelineCompiler::newMTLComputePipelineState`, the two places where every Metal pipeline state is created,
  with the very descriptor MoltenVK compiles (functions, specialization, formats, vertex layout, options).
- **Lookup**: inside the compiler's own block (same device lock, same compile timeout), the loaded archives are set on
  the descriptor and the pipeline is requested with `MTLPipelineOptionFailOnBinaryArchiveMiss`. A hit returns the
  pipeline; a miss lets the unchanged compilation run.
- **Collection**: after a compilation, a copy of the descriptor is queued on one utility serial queue and its functions
  are added to this session's archive (Metal reuses the binary it just compiled). The creating thread never waits.
- **Files**: `<dir>/id-<identity>/seg-<n>-<session token>-<bytes>-<sha256 prefix>.mtlarchive`. One segment per session,
  written to a temporary file then renamed; earlier segments are never rewritten. Identity: the Vulkan
  `pipelineCacheUUID` (MoltenVK revision, OS version, GPU family, argument buffers), the OS build and the GPU name.
- **What it cannot do**: a binary archive holds pipeline functions. It does not avoid creating the `MTLLibrary` from MSL
  (`newLibraryWithSource`), which is most of the native shader time measured on the iPhone.

## Environment (read when the VkDevice is created)

| Variable | Default | Meaning |
| --- | --- | --- |
| `RBX_MVK_BINARY_ARCHIVE_DIR` | unset = off | directory of one title's archives |
| `RBX_MVK_BINARY_ARCHIVE_STRICT` | 0 | tests only: a pipeline no archive holds fails instead of being compiled |
| `RBX_MVK_BINARY_ARCHIVE_SYNC_LOAD` | 0 | tests only: load the segments before the device is returned |
| `RBX_MVK_BINARY_ARCHIVE_COLLECT` | 1 | 0: lookups only |
| `RBX_MVK_BINARY_ARCHIVE_VERIFY` | 1 | check each segment's SHA-256 against its name before Metal opens it |
| `RBX_MVK_BINARY_ARCHIVE_REOPEN` | 1 | reopen the session's archive from its file after each save (memory) |
| `RBX_MVK_BINARY_ARCHIVE_MAX_SEGMENTS` | 8 | segments kept, this session's included |
| `RBX_MVK_BINARY_ARCHIVE_MAX_MB` | 192 | bytes of earlier segments kept |
| `RBX_MVK_BINARY_ARCHIVE_SESSION_MAX_ADDS` | 4096 | pipelines one session may collect |
| `RBX_MVK_BINARY_ARCHIVE_SESSION_MAX_MB` | 64 | size at which this session stops collecting |
| `RBX_MVK_BINARY_ARCHIVE_SAVE_EVERY` | 64 | additions between two saves |
| `RBX_MVK_BINARY_ARCHIVE_MIN_FREE_MB` | 384 (0 on macOS) | no collection below this available memory |
| `RBX_MVK_BINARY_ARCHIVE_REPORT` | unset | path of a JSON summary rewritten at each save and at device destruction |

One aggregate line is logged when the segments are loaded and when the device is destroyed
("RewindBox Metal binary archives ..."); nothing per draw.

## Run it

`.github/workflows/melonx-metal-archive.yml` (pushes that touch this directory or `test/melonx_metal_binary_archive/`):

- `probe`: `test/melonx_metal_binary_archive/run_probe.py`, the stand-alone Metal probe (`metal_probe.mm`);
- `moltenvk`: `test/melonx_metal_binary_archive/run_mvk.py`, which builds MoltenVK for macOS with the patch and runs
  `mvk_archive_test.cpp` through Vulkan in isolated directories.

Both run on the macOS runner's real Metal device ("Apple Paravirtual device"). They are not iPhone measures, and nothing
runs in the simulator. `mvk_archive_test.cpp` also builds against any Vulkan driver (`-lvulkan -lz`) to check the
program itself; `generate_shaders.py` regenerates `shaders.spvz` (needs glslangValidator).

## If it is ever tried on the iPhone

Not requested. It needs the integration owner: build the patched MoltenVK for iOS with
`melonx-moltenvk-rebuild.yml` (`patch` and `patchSha256` in `moltenvk-rebuild.json`), pin it, set
`RBX_MVK_BINARY_ARCHIVE_DIR` per title before the Vulkan device is created, and follow the protocol of the board entry.
