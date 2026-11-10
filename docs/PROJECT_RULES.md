# RewindBox — component rules

Read only the sections relevant to the current task, together with the latest
source and receipts linked from [AGENTS.md](../AGENTS.md). These are retained
engineering constraints, not new build/publication permissions. The complete
pre-cleanup record is preserved in [history](history/README.md).

## Library and lifecycle

- Import into an existing accessible user library; choose among registered
  folders, use the sole folder directly, and use the app's `roms` fallback only
  when none is registered. Do not recopy the same name/size. No arbitrary ROM
  root limit, silent registration success after a persistence failure, new
  scanner migration or database reset. Preserve reviewed relocation behavior.
- Protected library source changes must respect existing reviewed exceptions
  and the applicable baseline contract. An old baseline number alone is not
  a reason to restore older product code. Consult
  [library decisions](library-folders-2026-10-10.md).
- A global embedded-engine preference must not rewrite per-console choices.
  Availability and console visibility are distinct. Preserve existing routing
  policy; do not silently send retired Ports entries to another engine.
- A malformed external catalog entry must not block other entries or sources.
  Native discovery must not turn a background scan into work on UIKit.
- Preserve generation/title/native-session identity through launch, save,
  cancel, stop and resume. Release only resources owned by that session;
  late callbacks must not close the next game. Recover controller menu handlers
  only after the engine releases them, never while it owns the controller.
- TCP reachability, RemotePairing authentication, helper state, expected-PID
  attachment, memory preparation, actual JIT execution and first game frame
  are separate facts. Never infer one from a route or a previous successful run.
- Preserve the integrated helper path and manual LocalDevVPN behavior. Do not
  restore automatic VPN switching or an external JIT fallback that bypasses
  the iOS 26 mapping handshake. Dedicated engine helper identities stay separate.
- Savedata replacement requires validation, confirmation and backup; preserve
  the active-game mutation gate. Do not consume import folders automatically
  at startup. See [RPCS3 savedata exchange](rpcs3-save-exchange-build442.md).
- Library source-file discovery is intentionally not advertised in the app or
  README: do not add its folder path, help text, button or link there. See
  [source-file decision](library-source-files-build440.md).
- Outside a game, release the external scene for iOS mirroring; do not restore
  the second Flutter engine's logo-only external display. App version comes
  from `pubspec.yaml`; app and extension versions must agree.

## MeloNX

- Keep the embedded Switch engine. Runtime readiness, the native report and
  mandatory guest JIT are distinct from .NET NativeAOT compilation. Do not
  restore external MeloNX URLs, Shortcuts or StikDebug fallback launches.
- Retain owned-session teardown: stop input, end the guest while GPU services
  remain live, join rendering, then release host resources. Failed termination
  keeps context/window resources rooted and quarantines the process. Preserve
  driver ownership and generation binding; do not restore double disposal.
- Do not connect a live NeoSwap donation to upstream Offer/Withdraw without
  the broker ownership adapter. Keep memory pressure, admission and lifetime
  guards rather than extending budgets based on advertised physical RAM.
- Preserve per-title caches and the reviewed GPU/JIT fixes. A new title or an
  old cold/warm difference is not evidence that cache deletion improves launch.
- The sized-JIT fallback reacts only to explicit allocation refusal before
  preparation, with its existing bounds. It is not a retry after partial guest
  execution or a way to suppress a fatal memory guard.
- In the 603 Hogwarts journal, guard-relative offset `+3` does not identify a
  table-index overflow; `size=1` is a signal hint, not a proven instruction width.
  The 604 context describes the last known dispatch, not the faulting guest PC.
  Preserve those limits when diagnosing the next device log.
- The 604 presentation optimization removes only UIKit animation. The engine
  still starts after its view attaches, with JIT, generation and audio guards.
  Do not advertise a device timing gain or a fixed minute-long GPU pause yet.
- Experimental Unreal profiles stay OFF by default, consensual and reversible,
  with owned-file restoration and the mutation gate. File installation does not
  prove the game consumed a CVar or recovered black textures.
- Keep source-only experiments separate from compiled and shipped components.
  Do not repeat the rejected pool-binding purge without disposed-pool safety
  and a compute-to-graphics transition proof; single-parent storage also had
  negative hot-path timings. Read the
  [descriptor/cache investigation](melonx-descriptor-cache-2026-10-29.md).

Current evidence: [guard crash and completed source work](melonx-build603-guard-crash-2026-10-30.md),
[launch investigation](melonx-hogwarts-launch-2026-10-30.md),
[steady-state work](melonx-steady-state-2026-10-29.md),
[owned-session design](melonx-native-session-2026-10-20.md).
The older design's “not packaged yet” status is historical, not current readiness.

## RPCS3

- Preserve the latest successfully compiled Core's exact source and identities.
  A later source checkout is not proof those changes are inside an older binary.
  Canonical patch changes require the matching source/patch hash contract.
- Preserve ABI 30, code-generation/cache identities and their explicit reviewed
  compatibility mapping. Do not extend the SPU host-only mapping to unknown
  hashes or earlier reservation implementations.
- Preserve save-completion handoff, generation/title/native-ID checks, worker
  boot dispatch, accurate event/fence ownership and error handling. Do not drop
  an internal boot request during a save, force a guest label or skip a wait to
  claim a freeze fix. Failed saves after old-PPU teardown remain stopped with
  an explicit error instead of touching absent FXO objects.
- The related LR full-queue issue remains open: direct reservation stores do
  not always notify. A simple notifier wait has not resolved it.
- Deferred SPU compilation and the shader interpreter stay disabled unless new
  evidence and an applicable maintainer decision authorize a change. Do not
  restore the God of War III 30-FPS cap; its profile uses `Auto`, with explicit
  per-game user choices applied last. A VBlank change is not an established fix.
- Use existing `RPCS3-diagnostic.log` and `RPCS3-performance.log` counters for
  title-lever decisions; do not add diagnostics for that tuning exercise.
  Keep player settings minimal: optimizations belong in the Core/title profile,
  not in instructions asking the player to toggle removed settings.
- Keep Automatic title-independent improvements global: RSX priority, retained
  iOS QoS, passive-lock fairness, persistent SPU cache, NEON paths and RSX idle
  park under its FIFO-empty condition (Yield mode). Do not silently narrow them.
- Keep scoped optimizations scoped. Texture prehash Automatic remains GOW3-only;
  its hit counters may include synchronous producers, not only the worker.
  Preserve rejected sampler-mask/inflater-reuse experiments and negative timing
  cases; they are not established speedups.
- Preserve texture-validation order, real guest writes, invalidations, drains,
  fences and submissions. The `check_unlocked=true` presentation walk stays
  linear; its local locking does not authorize concurrent index-vector reads.
  Lazy shader analysis retains malformed/flow/indirect fallbacks and real
  operands; do not restore rejected eager analysis without new cost evidence.

### Title-lever policy

These thresholds retain the maintainer's 27–28 October rules. Check the current
`IOSTitleLevers.h`, serials and device evidence before changing coverage.

| Lever | Scope and required evidence |
| --- | --- |
| FIFO-batch texture validation and scoped revalidation | Add a title when `RSXFRAME551 texture_ms >= 5 ms/frame`; global promotion requires the recorded no-stale/wrong-texture device evidence |
| Texture residency cap | Scoped until promotion is justified; acts above `JITMEM gpu_textures_requested = 768 MB` |
| No-op PUTLLC | Per title only, accurate reservations on and `SPUWAIT551 putllc_fail >= 1 M/5 s`; never global because reservation-loss semantics differ |
| Deferred FBO write-back and early submission | Per-title log signature of GPU waits on framebuffer commits or render-target readback; preserve later reviewed title decisions |
| Promotion to all titles | Title-independent conditional mechanism, device logs on at least two titles without regression, and unchanged Disabled path |

Record added serials and justifying counters in `rpcs3/ios/IOSTitleLevers.h` and
its matching Core record. Enabled/Disabled remain unchanged. First-use SPU/PPU
compilation and Metal pipeline bursts are not automatically lever failures:
compare a second launch of the same mode using cache-hit and stall counters.

Read [latest Core verification](rpcs3-device601-core-2026-10-30.md),
[open issues](rpcs3-open-issues-2026-10-30.md),
[device601 source follow-up](rpcs3-device601-followup-2026-10-30.md),
[prior runtime log analysis](rpcs3-runtime-log-followup-2026-10-29.md) and
[title-lever background](rpcs3-cell575.md). BO2/GOW3/AC physical recovery must
be established from device evidence, not the source or compilation alone.

## Dolphin, NeoSwap and retired ports

- Keep the pinned Dolphin Core unless a relevant change is explicitly
  authorized. Do not call its C++ exports directly from the host to bypass
  JIT, Metal or launch ownership. Riivolution exports alone do not establish
  support through the actual app bridge or a working online race.
- Retro Rewind assets are not bundled or rehosted. Official-CDN download needs
  the recorded written permission; otherwise preserve player import. Wiimmfi
  uses a player-patched image. See the
  [Dolphin online audit](dolphin-retro-rewind-online-audit-2026-10-20.md).
- NeoSwap remains bounded by actual free system memory and its admission policy;
  it is not extra physical RAM. Prepared, assigned, donated and footprint
  counters are distinct. Do not migrate already-published FILE objects or
  bypass pressure rejection to increase a displayed donation total.
- KartPad/Dusklight runtime code and the Ports playlist stay removed. Use the
  native-donor subset and game-content gates; do not download the full historical
  Build 350 donor with retired game code. Keep both final IPA removal validators.
- Preserve `Ports/KartPad` and `Ports/Dusklight` player files, historical receipts
  and compatibility ABI values. Database retirement requires its verified backup;
  failure must not delete data or route a retired game elsewhere. See
  [KartPad removal](kartpad-removal-2026-10-19.md) and
  [Ports removal](ports-removal-2026-10-20.md).

## Catalogs, shaders and content

- Preserve source credits, exact licenses and legal notices. No firmware, keys,
  games or translated/decompiled game code is bundled as an emulator resource.
  A missing license is not permission to redistribute third-party bytes.
- Respect the reviewed origin-download model: unhosted sources carry names and
  pinned recipes/pointers, and the app authenticates original files before
  installing them. Do not rehost their bodies, relax restricted-title exclusions or
  rewrite history as part of an unrelated cleanup. See
  [origin publication](CHEAT_ORIGIN_PUBLICATION.md),
  [source-rights follow-up](SOURCE_RIGHTS_FOLLOWUP_2026-10-28.md),
  [enhancements](ENHANCEMENTS.md) and [credits](LEGAL_AND_CREDITS.md).
- Compatibility requires the actual adapter, exact game identity/region/revision
  and engine-readable format. Recognition of a filename, generic title match or
  successful download does not establish installation or rendering support.
- Install only owned files and preserve user cheats/mods, previous settings,
  backups, restoration and active-game mutation guards. Codes start disabled.
- Count distinct HD projects/families, not resolution, region or format variants,
  research leads, non-HD recolors or unverified imports. Preserve positive and
  negative original observations, author permissions and edition limitations.
  Do not promote a pack from `status: ok` alone or loosen extraction bounds.
- Switch HD research remains research-only until its actual adapter and exact
  target/version are proven. DuckStation packs do not become Beetle packs by
  renaming. Software rendering is not “HD active”. Preserve lazy loading and
  the reviewed texture-memory budgets.
- Mesen NES packs require the exact loaded-file SHA-1, engine-supported format
  and bounded decoded images. Enabling a pack for a Nestopia game must use the
  app's per-game engine selection, not a silent engine switch.
- A shader is “Verified” only with the matching iPhone compilation, actual
  application Metal execution and visible-effect proof. Downloads are on
  demand, pinned and digest-checked. Do not bundle/rehost Mattias CRT assets
  without the required redistribution permission. See [shader rules](shaders-system.md).
- Retained Dolphin shaders apply at the next launch. Do not write `GFX.ini`
  during gameplay; live changes require an explicitly reviewed Core ABI.
- The known `ppsspp-crowded` / `ppsspp-crowded-prx` address assertion is a
  simulator-probe limitation, not a demonstrated launch regression when content
  starts/stops correctly. Keep its tests and honest failure status. Reopen only
  for new evidence; do not repeat it in release summaries or weaken it for green CI.
- A 3DS NCCH encrypted in an unsupported format stays refused. Do not advertise
  keys as a remedy; preserve the reviewed console-data/OTP import rules, bounds
  and no-secret-logging behavior. iCloud placeholders are `notDownloaded`, not
  files to read. See [3DS import rules](libretro-3ds-system-settings.md).

Historical counts, one-off authorizations and earlier implementation statuses
remain in the [archived record](history/README.md). Read the relevant detailed
feature document before changing its behavior; this guide does not erase its
contract or authorize restoring a withdrawn feature.
