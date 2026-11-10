# Console-organized diagnostics — pending Build 606

These host changes extend delivered 605. They do not establish an FPS gain,
guest crash recovery or a successful new IPA. Core and device performance
evidence is recorded separately in the Hogwarts investigation.

New diagnostic files use `Documents/Diagnostics`. Player data and the historical
engine directories remain in place. `Diagnostics/index.json` records relative
canonical paths and retained legacy locations; its startup operation neither
moves nor deletes old diagnostics and does not scan game directories.

| Producer | Canonical location below Diagnostics | Retention |
| --- | --- | --- |
| iOS application summary | `System/Application/app.log` | Existing logger rotation at initialization; this is not a runtime hard cap |
| MeloNX native Core | `Switch/MeloNX-core.log` | Core writer; bounded current/previous generation |
| MeloNX host launch | `Switch/MeloNX-launch.log` | 5 MiB current plus `.previous` |
| MeloNX host and native performance | `Switch/MeloNX-performance.log` | 8 MiB current plus `.previous`; host samples also limited per session |
| MeloNX direct stderr / MoltenVK | `Switch/MeloNX-stderr.log` | 5 MiB current plus `.previous`, separate direct/NSLog line budgets and repeat summaries |
| Libretro sessions | `<actual console>/Libretro/` | 2 MiB per current/overflow file, paired previous/unfinished/failed diagnostic generations |
| Process-wide Libretro fatal breadcrumb | `System/Libretro/` | One retained process-wide descriptor, previous termination preserved |
| RPCS3 host | `PS3/` | Existing per-file limits and rotations; Core a4d0 unchanged |
| ARMSX2 host JIT | `PS2/` | Existing writer policy; Core-owned `ARMSX2/logs` retained |
| Dolphin sessions | `GameCube/Dolphin/` or `Wii/Dolphin/` | Existing newest-ten policy at launch |
| Dolphin shared host journal | `Dolphin/` | Existing persistent journal rotation at launch |
| 3DS system-data diagnostics | `Nintendo3DS/` | Existing writer policy |
| NeoSwap, NeoPlay, external storage, controllers, scraper, RetroArch | `System/<service>/` | Existing producer policy; no invented console attribution |

Libretro uses the console identifier from the actual launch request, including
PS1, PSP, NintendoDS and Nintendo3DS aliases. An unknown safe console identifier
gets its own folder; invalid identifiers use System. Unknown process-wide
events stay under System. This classification changes log destinations, not
engine data roots, games, saves, firmware, keys, caches or helpers.

MeloNX's engine chatter is persisted by the native writer once. The Swift bridge
does not copy its entire event stream through NSLog and Dart. Failure, fatal and
memory-retained events still reach the application state machine. Native
performance is outside the 64-event diagnostic ring: the bridge drains the
preceding sample and final event in sequence, or the latest sample during play,
and deduplicates sequence numbers on its utility queue. It drains once more
after native run returns. Native collection and host persistence are distinct;
the latter is the only writer of native performance records.

Performance rows retain PID, UTC time, generation, session token, title ID,
application build/version and packaged Core source/SHA-256, with explicit
`unavailable` values when the producer lacks identity. Packaged identity is read
once during preflight. Generation context is bound by the prepared callback
before native run and copied into the host sampler. An older generation cannot
borrow a later title's identity. The stderr pump owns an immutable capture token
and preflight context even if the next session is being prepared. Each rotated
performance row remains independently attributable.

The stderr writer uses a route lock separate from the capture lock. `end()` may
hold the capture lock while `fflush(stderr)` waits for a full pipe; the pump's
append never acquires that lock. Identical MoltenVK warning/error messages are
counted with bounded repeat state and periodic summaries, preserving a later
distinct technical error. This reduces diagnostic amplification; it does not
claim to repair the underlying driver fault.

Storage cleanup retains its native live-session and import gates. The active
application log is never offered for deletion, including through its parent
directory. A current canonical Libretro session that is empty, unfinished,
linked or unreadable blocks cleanup. A historical unfinished `Libretro/Logs`
session stops blocking only when a readable regular canonical session has an
END marker. An unreadable or linked legacy source still blocks. Cleanup plans
and the final deletion recheck protect canonical Libretro/Dolphin directories
while their corresponding session is active.

Validation commands for the merged source:

```sh
flutter test test/diagnostics_directory_test.dart test/storage_roots_test.dart test/storage_cleanup_planner_test.dart test/logger_append_test.dart test/user_data_migration_log_test.dart test/retroarch_launch_diagnostics_test.dart
python3 test/diagnostics_routing_native_test.py --require-native --receipt dist/melonx-host/diagnostics-routing.json
python3 test/melonx_perf_journal_test.py
python3 test/melonx_standalone_parity_test.py
python3 test/melonx_presentation_test.py --current-only
python3 test/storage_contract_test.py
python3 test/libretro_route_contract_test.py
python3 test/check_neo_swap_simulator.py
```

The Foundation fixture compiles production Swift and Objective-C writers,
including full-pipe/concurrent-end, UTF-8 rotation, immutable provenance,
unfinished/failed retention and shared fatal descriptor scenarios. UIKit uses
the actual registered plugin and explicit engine/JIT/frame boundary doubles;
it covers routing, sequence deduplication and the post-run final drain. These
checks require their stated Apple/Flutter toolchains and must be reported as
executed only after successful runs. Source assertions alone are not a device,
native engine or gameplay test. The session-host SDK check retains byte-exact
comparison of all FFI/lifecycle code below `MeloNXHostError` to its validated
baseline; the changed launch writer is exercised independently.
