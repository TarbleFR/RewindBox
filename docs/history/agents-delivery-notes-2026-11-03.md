# Earlier delivery notes retained from the project guide

Extracted from AGENTS.md at `d45167df9496afee6c980eb47d17f336202985c9`.
Original prose and evidence identities are preserved; relative Markdown links
are rebased to this folder. These are historical delivery notes, not current
task instructions or fresh build authorization. Read only the relevant build.

626 is delivered, not a pending candidate. Do not reuse its number. MeloNX Core 626 (Hogwarts
Legacy: the read-back into a buffer also runs when the only texture over its destination is the
linear read-back target the first copies created; build 625 never copied into buffers, 286 and
292 copies declined as occupied) has no iPhone result yet
([624 and 625 journals, and the 626 change](../../docs/melonx-624-measurement-2026-11-03.md)); no FPS
claim. The 625 journals at 1x and 0.5x show the GPU busy for the whole frame at 1x, and at 0.5x a
GPU four times lighter with frames still at about 50 ms: the CPU-side read-back wait.
`libretro_internal_bridge` and `rpcs3_internal_bridge` changed from 625 although their effective sources did
not (reported as undeclared image changes, not blocking).
The private 626 recipient key was deleted after the verified delivery.

625 is delivered, not a pending candidate. Do not reuse its number. MeloNX Core 625 (Hogwarts
Legacy: the read-back that build 624 left on the guest path because a buffer holds its
destination, a whole 1x1 R16G16B16A16Float texture about once per frame and a GPU-thread wait
of about 57 ms each, is copied on the GPU into that buffer and marked GPU-modified; every title:
the compute dispatch preparation timed in `RenderStageTimer`) has no iPhone result yet
([624 journals and the 625 changes](../../docs/melonx-624-measurement-2026-11-03.md)); no FPS claim.
The GameCube/Wii controller skins of another session ship for the first time (first iOS SDK
compile of `DOLSkinOverlay.mm`). `rpcs3_internal_bridge` changed from 624 although its effective sources did not (reported as an undeclared image change, not blocking).
The private 625 recipient key was deleted after the verified delivery.

624 is delivered, not a pending candidate. Do not reuse its number. RPCS3 Core 624, from the
Build 622 logs (Assassin's Creed and Black Ops II, with the ZCULL on-demand lever: the RSX
reports block placed so its report array starts on a host page, so GCM label reads no longer
wait for the ZCULL reports and no longer trip the lever; a conditional render whose report
already shows the object visible draws without waiting for the GPU; COREPROF ZCULL624) has no
iPhone result yet ([what the next run reads](../../docs/rpcs3-core624-2026-11-03.md)); no FPS claim.
Only `libRPCS3Core.dylib` and Runner changed from 623 (no undeclared image change). The private
624 recipient key was deleted after the verified delivery.

623 is delivered, not a pending candidate. Do not reuse its number. MeloNX Core 623 (Hogwarts
Legacy: a DMA read-back is copied on the GPU into a linear texture over the destination and
flushed at the first CPU access, instead of a GPU-thread wait for the render thread and a
whole-frame read-back about once per frame; every title: render-thread time per command type,
the Vulkan draw preparation, render passes, submissions, buffer fence waits and presentation
(`RenderStageTimer`), and MoltenVK's own GPU-execution and Metal-encoding statistics in
`MeloNX-stderr.log`) has no iPhone result yet
([621 journals, 623 changes and ceilings](../../docs/melonx-621-measurement-2026-11-03.md)); no FPS
claim. `tools/melonx/frame_report.py --stderr` reads every new journal and gives a ceiling per
resource. `melonx_internal_bridge` changed from 622 although its effective sources did not (reported as an undeclared image change, not blocking).
The private 623 recipient key was deleted after the verified delivery.

622 is delivered, not a pending candidate. Do not reuse its number. RPCS3 Core 621 (every
title: GPU time per RSX command buffer, freeze episodes kept through the pause menu with a deeper
`FREEZE_DUMP`, the mounted ISO kept open, pipeline queue and texture cache counters; Assassin's
Creed and Black Ops II: ZCULL on-demand reads on a guard of one-second buckets, per-frame ZCULL
waits) and its host integration (bounded core_log, last-fatal file, incidents and reports,
GPU timing and ZCULL on-demand levers in 12 languages) have no iPhone result yet
([what the next run reads](../../docs/rpcs3-core621-2026-11-02.md)); no FPS claim.
`Frameworks/armsx2_internal_bridge` changed from 621 although its sources did not (reported as
an undeclared image change, not blocking). The private 622 recipient key was deleted after the
verified delivery.

620 is delivered, not a pending candidate. Do not reuse its number. The Hogwarts
GPU source copy (a DMA copy whose linear source is held by a GPU-modified texture is copied
on the GPU instead of reading the texture back; title `0100f7e00c70e000` only), the
presentation-gap journal (`gaps=`, `long=`) and the attribution of the remaining slow source
reads have no iPhone result yet ([cause, change and what the next run reads](../../docs/melonx-hogwarts-618-measurement-2026-11-02.md));
no FPS claim. `Frameworks/armsx2_internal_bridge` and `dolphin_internal_bridge` changed
from 619 although their sources did not (reported as undeclared image changes, not
blocking). The private 620 recipient key was deleted after the verified delivery.

621 is delivered, not a pending candidate. Do not reuse its number. It is the MeloNX and
game-box build on the delivered 620 (maintainer, 3 November 2026: "deviens le build 621 rpcs3
n'est pas pret de finir"); its draft and recipient key replaced the RPCS3 session's first 621
draft. The MeloNX Core 621 changes have no iPhone result yet
([620 journals and the 621 changes](../../docs/melonx-620-measurement-2026-11-02.md)); no FPS
claim. The Hogwarts GPU region copy only goes into block-linear surfaces; a linear
destination (read-back) stays on the guest path and is counted as `linearDestination`.
`armsx2_internal_bridge`, `dolphin_internal_bridge` and `rpcs3_internal_bridge` changed from
620 although their effective sources did not (reported as undeclared image changes, not
blocking). The private 621 recipient key was deleted after the verified delivery. 622 is the
RPCS3 session's Core 621 build, on the recorded 621.

619 is delivered, not a pending candidate. Do not reuse its number. RPCS3 Core 619
(Assassin's Creed `BLES00158`/`BLUS30089`: ZCULL reports written when the guest reads
them, RSX label accesses off the 16 KiB page shared with reports 0-703; Black Ops II
`BLES01717`: pinned-draw affine clipping and asynchronous MoltenVK submits in Automatic)
has no iPhone result yet ([what the next run reads](../../docs/rpcs3-core619-2026-11-02.md));
no FPS claim. `Frameworks/armsx2_internal_bridge`, `dolphin_internal_bridge` and
`melonx_internal_bridge` changed from 618 although their sources did not (reported as
undeclared image changes, not blocking). The private 619 recipient key was deleted after
the verified delivery.

618 is delivered, not a pending candidate. Do not reuse its number. The Hogwarts
region upload (a partial DMA copy from linear memory into a GPU texture updates that
texture region, guest memory patched untracked; title `0100f7e00c70e000` only) has no
iPhone result yet ([what the next run reads](../../docs/melonx-hogwarts-617-measurement-2026-11-02.md));
no FPS claim. `Frameworks/armsx2_internal_bridge` and `Frameworks/melonx_internal_bridge`
changed from 617 although their sources did not (reported as undeclared image changes, not
blocking). The private 618 recipient key was deleted after the verified delivery. 619 is
reserved by the RPCS3 session (Core 619 on the delivered 618).

617 is delivered, not a pending candidate. Do not reuse its number. The
Hogwarts DMA-copy Core (float DMA copies on the GPU for title
`0100f7e00c70e000` only, logged bindless delta passes) has no iPhone result yet
([what the next run reads](../../docs/melonx-hogwarts-614-measurement-2026-11-02.md));
no FPS claim. `Frameworks/armsx2_internal_bridge` changed from 616 although its
sources did not (reported as an undeclared image change, not blocking). The
private 617 recipient key was deleted after the verified delivery.

616 is delivered, not a pending candidate. Do not reuse its number. Its three
RPCS3 changes (Assassin's Creed ZCULL polls without GPU waits; Black Ops II
pinned-depth order and SPU object read-ahead) have no iPhone result yet
([protocol](../../docs/rpcs3-core616-2026-11-02.md), section 6); no FPS claim.
`Frameworks/dolphin_internal_bridge` changed from 615 although its sources did
not (reported as an undeclared image change, not blocking). The private 616
recipient key was deleted after the verified delivery.

615 is delivered, not a pending candidate. Do not reuse its number. The Glacier
menu and the RetroAchievements Keychain fix have no iPhone result yet; the
Glacier composition was checked by real Flutter rendering against the approved
mock-up ([captures](../../docs/design/rewindbox-glacier/verification/renders/)).
`Frameworks/rpcs3_internal_bridge` changed from 614 although its sources did not
(reported as an undeclared image change, not blocking, as in 614). The private
615 recipient key was deleted after the verified delivery.

614 is delivered, not a pending candidate. Do not reuse its number. Its MeloNX
Core has no iPhone result yet ([protocol](../../docs/melonx-bindless-deltas-2026-11-02.md),
section 6); no FPS claim. `Frameworks/rpcs3_internal_bridge` changed from 613
although its sources did not (reported as an undeclared image change, not
blocking; not reproducible-build checked). The private 614 recipient key was
deleted after the verified delivery.

613 is delivered, not a pending candidate. Do not reuse its number. The Assassin's Creed
ZCULL default comes from the maintainer's iPhone result on BLES00158; the
Black Ops II SPU change and the ZCULL probe have no iPhone result yet
([protocol](../../docs/rpcs3-core613-2026-11-02.md)). The private 613 recipient key
was deleted after the verified delivery. The RPCS3 Core route depends on the
MoltenVK dependency run `41239096061`, whose artifacts expire on 14 November
2026 at 20:30 UTC.

612 is delivered, not a pending candidate. Do not reuse its number. It is the
first build on a standard-recipe base: the recipe now replays from the base's
delivered effective tree and supports an unchanged pinned Core
([recipe note](../../docs/standard-delivery-recipe.md)). Its accuracy test page changes
no default; no iPhone result yet. The private 612 recipient key was deleted
after the verified delivery. The RPCS3 Core route depends on the MoltenVK
dependency run `41239096061`, whose artifacts expire on 14 November 2026 at
20:30 UTC.

611 is delivered, not a pending candidate. Do not reuse its number. Its earlier
attempts (runs `41373565877`, `41374661558`, `41377459800`) failed in the recipe
or in load-sensitive tests and delivered nothing; each retry changed only the
recipe or a reviewed test. The private 611 recipient key was deleted after the
verified delivery.

610 is delivered, not a pending candidate. Do not reuse its number. Its first
delivery run `41341797604` failed in the retained MeloNX packaging check
(concurrent source-only MeloNX inputs); its successful test jobs were reused by
the delivered run. 609 (delivered 608 with the liveness MeloNX Core) remains
recorded in its own report.

**Build 611 delivered** (2 November 2026) on top of delivered 610 with the
standard recipe: its manifest was reviewed by an independent review agent (the
RPCS3 session, moved to 612 by the maintainer, did not review it); the earlier
609-based 611 recipe (`462620d`, `rewind611_*`, run `41340417135` cancelled) is
superseded. 612 (RPCS3 session) is delivered on top of it.

**Delivered 609:** delivered 608 with only the MeloNX Core replaced. The new
Core corrects LightningJit liveness metadata that lost guest NZCV/vector state
(FMOV marked as writing flags, 41 entries missing a destination read, 16-bit
by-element `Vm` width). It also logs the GC memory-load inputs behind gen2
activity. The downloaded IPA, eight bundles and all 90 images passed
verification. 86 images keep their 608 fingerprints; `Runner`
(version string) and two bridges rebuilt from identical sources differ, with
the bridge cause not identified. 608's RetroAchievements session and
translation features, the other engines and the `0279198` test evidence are
retained. These liveness defects are demonstrated by executable
reproductions, but they are **not proven** to cause the Hogwarts guard crash.
**609 does not contain** the RetroAchievements credentials fix (`45d19d7`,
[report](../../docs/ra-credentials-status-2026-11-01.md)) that landed on `Claude`
after the 609 source `3d92f19`. 609 therefore keeps the 608 RA sign-in
regression. The next IPA needs that fix with fresh Flutter/native tests and a
full application build. PS3 RetroAchievements through RPCS3
([report](../../docs/ra-ps3-rpcs3-2026-11-01.md)) is source only: its Core hooks are
staged outside the canonical delta (folding them requires an authorized Core
build); with the current Core, PS3 reports "not available for this core".
Existing unrelated compiler warnings are retained (see the 609 log review).
Device FPS and loading-time gains are still unmeasured; see
[the device analysis](../../docs/hogwarts604-performance-2026-10-30.md).

**Still unproven on iPhone:** whether the 609 liveness fix affects the
Hogwarts crash, what the new GC fields show, removal of the intermittent
minute-long GPU wait, Unreal CVar consumption, black-texture recovery and FPS
gains. The MeloNX presentation animation was removed; its old measured cost
was 0.510–0.513 s, not a measured new-device speedup. The 604 receipt does not
establish resolution of BO2/GOW3 freezes or Assassin's Creed flickering.
Apple model download/consent, real achievement translation and in-game unlock
presentation still require physical-device validation; see the [605 report](../../docs/achievement-translation.md).
