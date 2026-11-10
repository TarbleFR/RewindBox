# MeloNX engine 566: JIT translation units and the GC budget

Source: the Build 564 `app.log` from 27 October 2026 (iPhone, A18 Pro). It
holds three Hogwarts Legacy sessions. Engine settings were unchanged from 564:
resolution 1x, shader cache on, async shaders off, host memory budget on,
texture recompression on, backend threading on, PTC on, HostMappedUnsafe, and
the standalone MeloNX MoltenVK.

## What the log shows

| Session | Content | Length | Result |
| --- | --- | --- | --- |
| 1 (pid 5650) | base game (SDK 16.2.3) | 727 s | closed normally; 11.1 FPS on average |
| 2 (same process) | update NCA loaded (SDK 17.5.4) | 32 s | `System.OutOfMemoryException: JIT Cache exhausted` |
| 3 (new process 5819) | same update | 32 s | same exception |

- **The crash.** The stack is `DualMappedNoWxCache.MemoryCache.Allocate` ←
  `Map` ← `Translator.GetOrTranslatePointer` ← `NativeInterface.GetFunctionAddress`.
  On TXM devices the shared code arena is 512 MB, and LightningJit never frees
  translated code. Session 3 ran in a fresh process and still filled the arena
  in 32 s, at the same point in loading as session 2. The base game ran 727 s
  without filling it. The trigger is therefore the updated executable's code,
  not session reuse.
- **The slowdown.** Session 1 ran at a steady 30 FPS up to about 50 s. From
  then on, the `.NET_BGC` thread (the background GC) used 46–72 % of a core
  for the rest of the session. FPS fell to 6–13, and 4,408 presented frames
  arrived more than 40 ms apart. The device stayed at thermal state "nominal"
  until about 300 s, so heat does not explain the drop.
- **Ruled out:**
  - the engine journal (repeated texts were bounded);
  - the texture pool (no invalid-format flood);
  - host memory pressure (the GPU caches were never trimmed).

## Change 1: LightningJit translation units (`adapt_jit_decoder.py`)

The A64 decoder (`Decoder.DecodeMulti`) keeps decoding after a `BRK` or an
undefined instruction. It also keeps decoding after every `BL`/`BLR`, and stops
only at a return, a far jump or 10,000 instructions. Clang puts a no-return call,
or a trap, at the end of a function, with the next function right after it.
Each entry point therefore translated the functions that follow it, up to the
cap. Each of those functions, when called, then translated its own copy.

The decoder now ends a unit in two cases:

- **After a trap.** The unit resumes after the trap through the dispatcher,
  as a truncated unit does, in case its handler returns.
- **After a call or jump whose next instruction opens a stack frame.** Frame
  openings are `STP`/`STR` pre-indexed on SP and `SUB SP, SP, #imm`, with NOP
  padding skipped. The call keeps its host call and return check. If the call
  does return there, its continuation is translated then.

A branch target already known at that address keeps the unit going, as the
upstream `RET` rule does. If the heuristic is wrong, the only cost is one extra
dispatch; the guest still runs correctly.

**Measured offline.** The test compiled the 93,318 function starts
(`LC_FUNCTION_STARTS`) of the 46 MB `__text` of a real clang ARM64 C++ binary,
`libRPCS3Core.dylib` from IPA 564 (sha256 `e2fef781…`). It used this engine's
production `AarchCompiler` on Linux; the host code was generated but not run.

| | upstream | 566 |
| --- | --- | --- |
| host code for all entries | 293.4 MiB | 123.4 MiB (−58 %) |
| guest code translated | 64.3 MiB | 29.9 MiB |
| largest unit | 898 KiB | 233 KiB |
| 99th percentile unit | 36 KiB | 11 KiB |
| compile time (x64 host) | 9.6 s | 5.5 s |

On iPhone, smaller units also mean shorter compile stalls when the game reaches
new code. That effect has not been measured on the device.

**Tests.** `test/melonx_jit_decoder_test.py` decodes and compiles synthetic A64
code with and without the change, against the pinned source:

- a call followed by the next function: 47 → 3 instructions;
- trap padding: 144 → 3;
- a tail jump: 49 → 4;
- ordinary calls, known targets and loops: unchanged;
- 300 back-to-back functions that end in a no-return call: 542,100 guest
  instructions and 8.4 MiB of host code upstream, against 3,601 instructions
  and 79 KiB.

The engine CI's iOS simulator smoke run (ARM64) now executes a homebrew that
takes both new paths: a call whose return lands on a frame opening, and a tail
jump past one. It must reach its `svc ExitProcess`.

## Change 2: GC gen2 budget (`adapt_gc.py`)

The engine was published with `System.GC.ConserveMemory=9`, which is the
standalone MeloNX setting. In the .NET 10 GC, setting N caps gen2 growth at
`((10 / N) - 1) * 0.5 + 1` of the surviving size
(`gc.cpp`, `desired_new_allocation`). With 9 the cap is 1.056. A background
gen2 GC, which marks the whole heap, therefore starts after about 5.6 % of
heap growth. `generation_to_condemn` also makes every gen2 GC whose gen2 + LOH
fragmentation exceeds `1 - N / 10` (10 %) blocking and compacting.

566 uses 5, the value the GC itself picks when it adapts to the application
size. Gen2 can then grow up to 50 % before the next gen2 GC, and blocking
compaction starts only at 50 % fragmentation.

The managed heap may grow more between collections. The GPU caches still
follow the host memory budget.

## Not measured, not claimed

- No FPS gain has been measured on the iPhone. The expected effects are:
  - Hogwarts Legacy with its update no longer exhausting the JIT arena;
  - much less background GC time after the first minute;
  - shorter stalls on new code.

  The next `app.log` will show whether they happened.
- No Persona 4 log was available for this cycle. Nothing is changed for its
  audio or its black artifacts beyond the two general changes above.
- In sessions 2 and 3, an unnamed host thread (QoS 47) ran at about 100 % from
  the first second. It was quiet in session 1. The log does not identify it.
