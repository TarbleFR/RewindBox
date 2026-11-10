# MeloNX: in-play blocking gen2 GCs are failed background GC starts (.NET 10.0.0 runtime defect)

5 November 2026, IPA 658 (MeloNX Core 658, coreSource 2cfc28e5), Hogwarts Legacy, two players' private journals
(not in the repository). Branch `gc/bgc-fallback`. Status: **cause confirmed in source, on the host runtime and in
the device journals; correction implemented locally (rebuild route + Core hook), not yet built on CI, not
device-tested.**

## Symptom

In-play `gcEvent` lines of kind `fullBlocking` (concurrent 0): 102 ms (swept) and 332 ms (compacting) for player 1
(pid 11152), 952 ms (compacting) for player 2 (pid 79931). Each is paired with a `background` line of the **same
index**, whose payload is the background collection two before it:

| pid | fallback index | pause | paired "background" payload | equals background GC |
| --- | --- | --- | --- | --- |
| 11152 | 231 | 102.1 ms, swept | pauses 0.001 / 3.095 ms, heap 664 MiB | index 160 (two before) |
| 11152 | 349 | 331.8 ms, compacted | pauses 4.761 / 45.07 ms, heap 824 MiB | index 255 (two before) |
| 79931 | 186 | 952.4 ms, compacted | pauses 1.714 / 3.28 ms, heap 759 MiB | index 118 (two before) |

## Mechanism (dotnet/runtime v10.0.0, commit 60629d14)

The iOS NativeAOT runtime packs 10.0.0 were built from dotnet/dotnet b0f34d51 (nuspec), whose `gc.cpp`
(sha256 4d92ead4…) and NativeAOT `gcenv.ee.cpp` (34a41063…) are byte-identical to the v10.0.0 tag.

1. `gc.cpp:24574-24584` (garbage_collect): a gen2 with no blocking reason in interactive mode is decided
   background: `keep_bgc_threads_p = TRUE; settings.concurrent = TRUE`.
2. `gc.cpp:24602` `do_pre_gc()` → `gc.cpp:50975-50979`: with `settings.concurrent`, it flips
   `last_bgc_info_index` and stamps `last_bgc_info[idx].index = settings.gc_index` **before** the start check.
3. `gc.cpp:24719` `prepare_bgc_thread(0)` → `gc.cpp:39985-40044`; when no thread runs, `create_bgc_thread`
   (`gc.cpp:40052`) sets `bgc_thread_running = GCToEEInterface::CreateThread(bgc_thread_stub, …)`.
4. NativeAOT `gcenv.ee.cpp:604-655` CreateThread: the new thread calls `m_ThreadStartedEvent.Set()` (line 638)
   **before** `realStartRoutine` (line 642, i.e. `bgc_thread_stub`), and CreateThread returns after that event
   (line 650 wait). `bgc_thread` is only set inside `bgc_thread_stub` (`gc.cpp:38142`).
   (CoreCLR's own CreateSuspendableThread, `vm/gcenv.ee.cpp:1520/1526`, has the same order.)
5. `gc.cpp:24755` (workstation): `do_concurrent_p = (!!bgc_thread && commit_mark_array_bgc_init());` — if the new
   thread has not reached `bgc_thread_stub`, this is false and `gc.cpp:24855-24858` runs the collection blocking
   with `settings.compaction = TRUE`. `do_post_gc` (`gc.cpp:51451-51463`) records it as full blocking; the
   background slot stamped in step 2 keeps the payload of two background GCs earlier (GetMemoryInfo
   `gc_kind_background` → `get_completed_bgc_info`, `gc.cpp:50940`). Hence the equal-index pair and the stale payload.
6. Why a thread must be created in play: `gc.cpp:40213-40276` bgc_thread_function waits **20000 ms** (release,
   workstation) and exits on timeout unless a BGC is pending (`bgc_thread_running = FALSE; bgc_thread = 0`).

Upstream fix: [dotnet/runtime#119383](https://github.com/dotnet/runtime/pull/119383) (commit f1f0a476, merged
5 Sep 2025, issue #13238) changes line 5 to `bgc_thread_running`. Present from `v11.0.0-preview.1` (and rc.3);
**absent from every 10.0.x tag, v10.0.0 to v10.0.14** (each tag's gc.cpp read on 5 Nov 2026). `gcconfig.h` has no
setting for the BGC thread lifetime or the 20 s wait; `keep_bgc_threads_p` is internal.

Ruled out as the cause: induced GCs (the only `GC.Collect` in the Core is the session teardown, Library.cs:966/970,
seen as unpaired final-sample blocking GCs), `GCSettings.LargeObjectHeapCompactionMode = CompactOnce` (Ptc.cs
459/841: only affects a blocking GC's LOH compaction; the fallbacks kept LOH fragmentation), memory load and
fragmentation (those set `should_do_blocking_collection`, which never stamps the background slot, so no pairing),
GC configuration (ConserveMemory 5, HighMemoryPercent 99, `DOTNET_GCgen0size` 0x4000000: none touches BGC thread
lifetime; a larger gen0 budget only makes >20 s gaps between gen2s more common).

## Timing in the journals (aggregated)

Gap = time between the performance samples (5 s) that saw the previous real background GC and this request.

| player / builds | requests with gap < 15 s | 15–25 s | > 25 s: background | > 25 s: **fell back** |
| --- | --- | --- | --- | --- |
| player 1, builds 609–658 | 113 / 0 fallback | 13 / 0 | 37 | **5** |
| player 2, builds 621–658 | 10 / 0 | 7 / 0 | 31 | **14** |
| total | 123 / 0 | 20 / 0 | 68 | **19 (22 %)** |

Build 658, player 1 pid 11152: background GCs at 03:10:13–03:10:33 (5–10 s apart), 03:11:55 (gap 82 s, ok),
**03:13:06 fallback** (gap 71 s, 102 ms), 03:14:02 (gap 128 s, ok), 03:17:01 (gap 179 s, ok), **03:20:15 fallback**
(gap 194 s, 332 ms), 03:21:03 teardown GC.Collect. Player 2 pid 79931: 03:55:07–03:55:27, **03:56:24 fallback**
(gap 57 s, 952 ms); pids 79315, 79477, 80176 had gaps of 20–71 s without fallback. Every fallback follows a gap
> 20 s and many such gaps do not fall back: a race at thread creation, not a policy.

## Host reproduction (docs/evidence/melonx-bgc-fallback/host-probe)

Probe: requests a background gen2 (`GC.Collect(2, Default, blocking: false)`) at process start, every 2 s, and after
21 s idle, reading `/proc/self/task/*/comm` for the `.NET BGC` thread. 56 + 56 processes, 8 in parallel, 4 cores.

| runtime | requests that had to create the BGC thread | fell back | requests with the thread alive | fell back |
| --- | --- | --- | --- | --- |
| .NET 10.0.0 (CoreCLR host) | 277 (221 after the 20 s idle exit) | **27 (9.7 %)**, 16 after idle exit | 115 | 0 |
| .NET 11.0 rc.3 (contains #119383) | 280 (224 after idle exit) | **0** | 112 | 0 |

The idle exit is confirmed (`.NET BGC` thread absent after 21 s), the equal-index signature appears only on thread
creation, and the runtime with the upstream fix never falls back (one-sided Fisher p ≈ 3e-9).

## Decision and correction

**Confirmed runtime defect.** Order of preference: (a) no 10.0.x servicing package contains the fix (.NET 11 is a
major retarget, rc only); (b) no configuration keeps the thread (server GC would avoid the idle exit but changes the
heap model and still checks `bgc_thread` at creation; a keep-alive BGC every < 20 s costs a full mark each time and
stays racy; disabling concurrent GC makes every gen2 blocking); (c) **implemented**: rebuild only `gcwks.cpp.o` from
v10.0.0 + the upstream one-line fix and splice it into the official `libRuntime.WorkstationGC.a`.

- `build-utils/melonx/nativeaot-gc/wks-bgc-thread-running.patch` (sha256 018214fb…): the upstream line and a marker
  string (`used`, so `[no dead strip]` in Mach-O, checked by clang for arm64-apple-ios).
- `build-utils/melonx/nativeaot-gc-rebuild.json`: tag/revision, source digests, patch digest, both runtime packs
  (nupkg, library, member digests, 81 members, platform).
- `build-utils/melonx/build_nativeaot_gc_rebuild.py` + `.github/workflows/melonx-nativeaot-gc-rebuild.yml` (macOS):
  official `./build.sh -subset clr.nativeaotruntime -os ios|iossimulator -arch arm64 -c Release`, official pack from
  nuget.org by digest, `ar r` + `ranlib` of gcwks.cpp.o only, then checks: same member list as the pack, every
  other member byte-identical, same symbol table for them, same strong definitions in gcwks.cpp.o, marker present
  and no-dead-strip, platform/minos equal; identity.json and annotations.
- `build-utils/melonx/nativeaot-gc-rebuild-pin.template.json`: copy to `nativeaot-gc-rebuild-pin.json` after the run.
- `build-utils/melonx/fetch_nativeaot_gc.py` (from build_core.sh): artifact by API digest, libraries by pinned
  digest and structure, placed in the prepared tree; `build_core.sh` passes the digest to MSBuild and requires the
  marker in the linked `Ryujinx.Library.dylib`; the Core identity gains `nativeAotGc`.
- `build-utils/melonx/adapt_nativeaot_gc_runtime.py` (last adapter, Ryujinx.Library.csproj of Core 658):
  `RewindBoxPatchedNativeAotGc` after `SetupOSSpecificProps` replaces the pack library **in place** among
  `LinkerArg`/`NativeLibrary`, failing closed on: unknown RID, server GC, other pack bytes, unset/other patched digest,
  missing library, duplicated input. Checked with the real ILCompiler 10.0.0 on a linux-x64 NativeAOT publish: the
  link command is byte-identical except that path, same position, the binary runs.
- Journal: not changed here. The equal-index pair is a stale background slot, not a second collection; its
  one-line attribution (`fellBackFromBackground`) is lot/diagnostics commit 35dd0ca6
  (EmbeddedPerformanceDiagnostics.cs, test/melonx_gc_fallback_test.py).
- `test/melonx_nativeaot_gc_test.py`: 69 checks passed (source mechanism, patch, marker, packs, splice acceptance
  and refusal, fetch acceptance and 6 refusals, adapter and 8 MSBuild refusals); `melonx_adapter_control_order_test`
  passes. The frozen Core contract tests now report the changed inputs (melonx-core.yml, build_core.sh,
  prepare_embedded.py): a Core 659 freeze is required.

## Next

1. Push (main): the rebuild workflow runs on macos-26; read its `NativeAOT GC rebuild` annotation (both libraries,
   `otherMembersAndSymbolTable` identical, marker, Xcode). 2. Fill `nativeaot-gc-rebuild-pin.json` from the run and
   artifact API. 3. Refreeze the Core plan/contract, add this test to the gates, build Core 659 (log line
   `RewindBox NativeAOT GC: linking …`, marker grep, simulator smoke). 4. iPhone: no `fullBlocking` paired with or
   flagged as a background fallback, background GCs after > 20 s idle all concurrent, max in-play GC pause from
   `gcEvent` / `gcPauseMs` well under 100 ms; any remaining unpaired in-play blocking gen2 is a separate GC-policy lever.
