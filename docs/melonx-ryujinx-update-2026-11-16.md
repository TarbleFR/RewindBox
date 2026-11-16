# MeloNX engine: the latest Ryujinx, the IPA 759 journals, and the lever taken — 16 November 2026

Maintainer request: improve the MeloNX engine; an update to the latest Ryujinx engine may be a way to performance;
find the levers and apply the fixes judged good.

Journals read: IPA 759 (Core `127b72b9`, iPhone 16 Pro Max), one Hogwarts Legacy session and two Super Smash Bros.
Ultimate sessions. They are private and stay out of the repository; the figures below are aggregates.

## 1. Would the latest Ryujinx make the iPhone faster? No.

- MeloNX 2.7 (`13700519`, the public source RewindBox builds from) branched from Ryubing at `69c22a74`
  (17 April 2026). Ryubing's head is `6af327bd` (14 November 2026): 159 commits later. MeloNX itself added 20.
  MeloNX 2.8 is a rebase on a newer Ryubing tree whose source is not published
  ([comparison of 16 November](melonx-2.8-comparison-2026-11-16.md): nothing taken).
- Most of the 159 commits are interface, translations, CI, input and service stubs. The ones that touch speed or
  memory do not reach the iPhone path:

| Ryubing commit | What it does | Why it is not taken |
| --- | --- | --- |
| `47c0180b` larger base JIT cache | 1 GiB of JIT cache on desktop | RewindBox has its own JIT arena; regions already grow when one is full |
| `4631e0a9` garbage collector settings | Concurrent, RetainVM, latency mode | Settings of the JIT runtime that NativeAOT does not read, or that raise the footprint (RetainVM); the collector's behaviour here is already driven by measured adapters |
| `a82350bb` mono-jit-v2 | One-level address table | Needs the sparse table (a 2^37-entry reservation and signal handling), which MeloNX disables on iOS |
| `6fb71b08` instanced JIT cache | ARMeilleure cache per instance | iOS runs LightningJit, not ARMeilleure |
| `8d53b02f` larger texture cache | More textures kept | More memory, and memory is the open limit here |

- Correctness fixes exist upstream and stay available, none taken in this lot: the maintainer's line for the engine
  is performance only, and a rendering change for every title needs a check on several titles. `9e896b8f` (shadow
  state of blend enable, three lines, fixes loading transitions in one title), `d2fb1404` (texture descriptors with
  unmapped addresses, one title's crash; touches files RewindBox's adapters rewrite), `e3940abe` (threaded renderer
  stop: RewindBox's teardown already waits for the render loop; the reference index fix is partial upstream),
  `e2a612b1` (NaN texture coordinates on Apple GPUs; changes generated shaders, so every shader cache is rebuilt),
  `68432d21` (VP9), `58bd19a2`/`b7772462` (Vulkan validation), `c0078088`/`48888bd0` (non-uniform indexing; bumps
  the disk cache version), `6af327bd` (SoftFloat32, not used by LightningJit).

## 2. IPA 759 on the iPhone

Super Smash Bros. Ultimate (two sessions, 185 s and 790 s): median 60.0 FPS, mean 58.0 and 58.9, p99 frame gap
17 ms; one gap over 1 s in the first session (2.2 s), none in the second; footprint 4.3 to 5.0 GiB, thermal state
nominal.

Hogwarts Legacy (one session, 94 s in the world): 30 FPS in the menu and at the start of play, then 17 to 24 FPS;
median 28.2, mean 24.6, p95 67 ms, p99 167 ms, two gaps over 1 s. The fall starts when the footprint passes about
4.5 GiB (free memory of the device 4 to 5 %), with 7 000 to 17 000 pages decompressed per second and threads ready
but waiting for a core 46 to 238 % of the time. The GPU is not the limit (busy 16 to 17 ms per frame).

What the earlier lots changed, measured here: about 12 Metal command buffers per frame (24 to 31 in IPA 729); the
texture-array barrier passes 126 to 146 ms per 5 s window (240 to 290 ms before).

## 3. The lever: the runtime's locks yield with a priority drop

`[MeloNX:hot]` profiles of the Hogwarts session, decoded with `tools/melonx/hot_spots.py` and the symbol map of Core
`127b72b9` (six busiest threads, 300 samples 10 ms apart):

| Profile | Frame rate | Running samples | In `swtch_pri` (libsystem_kernel) | Share |
| --- | --- | --- | --- | --- |
| 1 (base) | 30.2 | 197 | 1 | 0.5 % |
| 2 (base) | 29.8 | 194 | 1 | 0.5 % |
| 3 (slow) | 23.0 | 640 | 97 | 15.2 % |
| 4 (slow) | 14.6 | 753 | 109 | 14.5 % |

- Every thread is touched in the slow profiles: the guest main thread 23 of 161 and 20 of 120, the guest render
  thread 21 of 85 and 35 of 112, the guest RHI thread 15 of 72 and 23 of 79, the engine's GPU thread 15 of 112 and
  21 of 159, the engine's render thread 16 of 172 and 10 of 216.
- The stacks give the callers. All these samples are under `System.Threading.Thread.Yield` (RhYield,
  PalSwitchToThread, `sched_yield`); the call sites name the contended paths of two locks of the .NET runtime for 94
  of the 97 and for all 109:
  - `Lock.TryEnterSlow` (the lock behind `Monitor.Enter`): 42 samples in profile 3, 71 in profile 4. The monitors are
    the emulated kernel's critical section (`KCriticalSection.Enter`), the memory tracking lock
    (`MemoryTracking.VirtualMemoryEvent` on the guest threads, `RegionHandle.Reprotect` on the GPU thread), the timer
    manager and `KThread.HandlePostSyscall`;
  - `LowLevelLock.WaitAndAcquire`, the single process-wide lock of the runtime's wait subsystem, taken by every event
    `Set` and every `Monitor.Wait`: 52 samples in profile 3, 38 in profile 4.
- Mechanism. On Apple platforms `sched_yield` is `swtch_pri(0)`: when another thread is runnable, the caller falls
  to priority 0 until it runs again. [The RPCS3 measurement](rpcs3-cell579.md) on macOS under five busy threads: up
  to 22.4 ms for one `sched_yield`, 18 µs for `thread_switch(MACH_PORT_NULL, SWITCH_OPTION_NONE, 0)`, which yields to
  threads of the caller's priority and keeps that priority. In .NET 10.0.0 `Lock.TryEnterSlow` spins up to 22
  iterations and yields at every other one from the tenth; `LowLevelLock.WaitAndAcquire` spins 8 and yields at the
  fifth and seventh; both then block. While the phone is short of cores (memory pressure, compressor), each of those
  yields can park a priority-47 thread for milliseconds while the lock it wanted was released microseconds later.
- Already done for the engine's own spin: `adapt_darwin_spin_yield` (AdaptiveSpinEvent). Its yields are now the
  `thread_switch` samples of the table's sessions: 9 and 6 per slow profile. What is left is inside the runtime.

### The fix: `adapt_runtime_yield`

The Core defines `sched_yield` itself: one C file (`src/Ryujinx.Library/RewindBoxRuntimeYield.c`, no include) compiled
by the link's own driver for the link's target and added to the link's inputs, by a target of `Ryujinx.Library.csproj`
that runs before the NativeAOT link. A symbol defined in an image's own objects is the one its references bind to, so
every `sched_yield` of the Core (the runtime's `PalSwitchToThread`, the collector's spin locks) is this one. The
symbol is hidden; no other image of the app changes. Spin counts, the order of spin, yield and block, and every wait
condition stay the runtime's.

- It calls `thread_switch` with no thread, no option and no time, except in two states of the runtime, where it
  calls `swtch_pri(0)`, which is what the system library's `sched_yield` does: while the runtime stops its threads or
  holds them stopped (`RhpTrapThreads`, not zero from the start of `SuspendAllThreads` to the resume), and while a
  background collection runs (`gc_background_running` of the collector).
- Why the two exceptions: both have loops that move on only when a thread of possibly lower priority runs. The
  suspension loop yields once per millisecond of waiting so that a thread it must stop, and that needs the
  suspending thread's core, can run (thread pool, background pipeline compilation), while guest threads in
  translated code keep their cores. During a background collection's concurrent mark, an allocating thread of
  priority 47 can wait for the background collector's thread in a loop that only yields (`exclusive_sync`); the
  runtime creates that thread without a priority class. Only a yield that depresses hands the core over. A first
  version without the first exception was withdrawn before any build; the second came from an independent review.
- Two other routes were weighed. The setting `System.Threading.Lock.SpinCount` (10 would stop the managed lock before
  its first yield) leaves `LowLevelLock` as it is and sends more waiters to it. Rebuilding the runtime library with a
  patched `PalSwitchToThread` (the route of `nativeaot-gc-rebuild`, not in the current Core) is a second build chain
  for a few lines.
- What differs in behaviour, outside those two states: a yielding thread no longer lets lower-priority threads run
  before it. The yields left there: the two locks (bounded spin, then a block), the collector's spin locks (a 5 ms
  sleep at every thirty-second iteration), and one short yield-only loop around the collector's own lock.
- Fail closed. The build stops for a runtime identifier other than the two iOS ones, without a target triple, or
  without the object. `build_core.sh` then reads the linked library: `sched_yield` no longer imported,
  `thread_switch` and `swtch_pri` imported, the marker string present. The link itself fails if the runtime no
  longer defines one of the two flags.

### Status

| Step | State |
| --- | --- |
| Implemented | Yes: adapter, wiring, build check |
| Tested | On Linux: the C file run with stand-ins (each call under each value of the two flags), the project's target run by MSBuild for both iOS runtime identifiers, the objects' symbols, and a Mach-O link (lld) of a stand-in caller, where the image's own definition replaces the system import (gate `runtime-yield`, 28 checks) |
| Compiled | Not yet: the NativeAOT link on macOS is the Core build |
| Delivered | No |
| Observed on a device | No |

Expected on the iPhone, read from the next IPA's `[MeloNX:hot]` lines: no running sample in `swtch_pri` under
`Lock.TryEnterSlow` or `LowLevelSpinWaiter.Wait`. Refuted, and the adapter removed, if those samples remain, or if
the slow profiles show more blocked samples in the two locks with fewer presented frames. No frame rate gain is
claimed: the root of the slow phases is still physical memory.

## 4. Leads examined and not taken

- Descriptor pools sized for 8 sets (about 98 MiB of `MVKDescriptorPool::Create` in the native heap): MoltenVK does
  not touch those buffers when it creates the pool; most of it is virtual.
- Compressing MoltenVK's SPIR-V copies (205 MiB): cold data that the system's compressor already holds; a real gain
  of tens of MiB at most, for a shared MoltenVK rebuild.
- `EnableSuballocationPooling` in the Vulkan allocator (MeloNX's own switch, off): unproven here, and it changes
  every buffer's lifetime.
- Making the DMA read-back sync strict: the wait is most likely the GPU's backlog, not the submit.
- Upstream's collector and JIT settings: see section 1.

## 5. Still to measure

- Who allocates the managed memory the GPU scopes do not explain (about 70 % of 70 to 200 MiB per 5 s window in
  play): one ephemeral collection every 1.6 to 2 s, pauses of 22 to 341 ms.
- Which waits make up the "sync waits" of 7 to 11.5 ms per frame in play (`adapt_paced_strict_syncs` sets its own
  limit at 4 ms; the frame rate held 30 with 3.8 to 8.7 ms, so it is not shown to be the limiter).
- The memory tracking lock: guest threads fault on tracked pages while the GPU thread reprotects under the same
  lock (30 of the 71 monitor samples of profile 4). Not changed here.
