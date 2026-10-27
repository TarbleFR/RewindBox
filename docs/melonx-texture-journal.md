# MeloNX: garbage texture descriptors and the engine journal (Hogwarts Legacy)

Source: the Build 562 `app.log` sent on 27 October 2026 (iPhone, Hogwarts Legacy
XCI, MeloNX engine of 558). Facts below come from that log; nothing here was
run on an iPhone.

## What the log shows

| Process | Game | Outcome |
| --- | --- | --- |
| 3337 | Hogwarts Legacy.xci | 18 s after launch, still loading: `Unhandled exception.` on stderr, app gone. The exception text was not captured. |
| 3406 | Hogwarts Legacy.xci | Closed after 23 s, 25.7 FPS. |
| 3506 | Hogwarts Legacy.xci | `The game closed before launch authorization completed.` |
| 3743 | `Hogwarts Legacy [0100F7E00C70E800][USA][v262144].nsp` | `The game could not be read with the current keys.` The title ID ends in `800` and v262144 is version 4: this package is the game's update, not a game. It belongs under the XCI's *Import update* menu. |
| 4041 (1st run) | Hogwarts Legacy.xci | 460 s, closed by the player. 26.0 FPS on average (the game targets 30). |
| 4041 (2nd run) | Hogwarts Legacy.xci | The log stops at 11:49:04 with no close and no stderr line, in a burst of the error below. |

Slow periods of the 460 s run (per-second `[MeloNX:perf]` lines):

1. t=144-158 s: 0 FPS for 15 s. `GPU.MainThread` 99 %, `Logger.MessageThread`
   80 %. The engine journal recorded 13,037 `Gpu GetInfo: Invalid texture format
   0x25A5A (sRGB: True).` errors in the one second before app.log reached its
   5 MiB engine ceiling.
2. t=351-404 s: 0-10 FPS while new pipelines were compiled (render thread
   65-87 %, `Background pipeline compile missed on draw`, syncpoint waits over
   1 s, Vulkan pipeline cache over its 128 MiB budget).
3. t=405-448 s: 1-9 FPS, the same texture error again, .NET GC at 30-60 %.

## Cause of 1 and 3

`0x25A5A` is `0x5A5A5A5A & 0x8007FFFF`: the whole descriptor is the 0x5A fill
pattern (uninitialized pool memory). Its GPU address, `0x5A5A5A5A5A5A`, lies
beyond the 40-bit GPU address space, so `FindOrCreateTexture` returns null and
the pool marks the ID invalid, until the next guest write to the pool clears
that mark. The game rewrites its pool continuously, so each lookup evaluated
the descriptor again and logged again. Every log went synchronously through
`EmbeddedLaunchDiagnostics.Record` (an app.log open/write/close) on the GPU
thread, and through the console target.

## Changes

- `build-utils/melonx/adapt_texture_pool.py`: `TexturePool` rejects a
  descriptor whose address fails `MemoryManager.ValidateAddress` before sizing
  or logging it. The result is unchanged (null, ID marked invalid); mapped and
  in-range unmapped addresses keep the upstream path.
- `native/melonx/EmbeddedLaunchDiagnostics.cs`, `EmbeddedRuntime.cs`: an engine
  warning or error text is journaled for its first 8 occurrences, then at each
  power of two with its count (`... (repeated 512 times)`); counts restart
  with each game and at most 1,024 texts are tracked. An unhandled managed
  exception is written to app.log before the process ends, past the 5 MiB
  ceiling, keys redacted.

## Evidence (no iPhone)

- `test/melonx_texture_pool_test.py` builds the pinned Ryujinx.Graphics.Gpu
  twice (GAL doubled) with the journal wired in as EmbeddedRuntime does. For
  2,560 lookups of 0x5A descriptors rewritten between rounds: the 562 engine
  writes 2,560 app.log lines (17 MB allocated, 60 ms on the looking-up thread,
  Linux); the fixed engine writes none (8 KB, 1.7 ms). In-range unmapped
  lookups: identical results, journaled 13 times instead of 320. A mapped
  256x256 RGBA8 texture is created identically.
- `test/melonx_engine_journal_test.py`: 1,001 repeated texts give 15 lines
  (562: 1,001); 8 threads x 1,000 give 17 exact counts; an unhandled exception
  is written past the ceiling with its type, message and stack under JIT and
  NativeAOT (562: nothing).

Not addressed: pipeline compilation stalls (period 2) and the cause of the
10:35 crash, which the next log will now name.
