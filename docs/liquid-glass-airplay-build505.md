# Liquid glass and sequential AirPlay — combined candidate 505

Base: integrated Rewind Motion startup `d27a06f6ad386a79c55ac4e9304e5475c1c0c9a9` (Build 504).
Isolated first implementation: `252297bf73f089a4d74d7393ce354a7109aba597`.
No tag, release or main change is authorized.

## Appearance and interaction

Console cards and the moving menu lens now use a clear center, thick convex
rim, soft upper glint and inner meniscus over existing artwork. All light is
neutral under imported themes. This lightweight optical illustration does not
claim physically accurate refraction. Dense cards retain their zero-blur path;
the small selected menu lens retains its existing limited backdrop blur.

The focused card alone repaints a small light drift, driven by its existing
animation controller. Artwork/text are not rebuilt each frame. Presses combine
gentle compression with a slight two-axis deformation. The menu lens stretches
in flight and retargets from its current position on fast changes. Reduced
motion, inactive lifecycle and the existing emulation barrier suspend movement.

Playlist opening/closing uses the same glass surface and a small transient
stretch. The true playlist retains its final viewport, element path, scroll
state and input lifetime lock. The source image keeps its aspect ratio and the
existing bounded GPU allocation. No import or playlist-model logic changes.

## AirPlay cause and correction

Previously AirPlay was inserted as a null visual cell outside the `NavTab`
registry. Every swipe/bumper cycle visited only that registry and therefore
skipped the visible AirPlay cell. AirPlay is now an appended identity (index 7),
with existing indices 0–6 unchanged. One order drives drawing and navigation:
Systems, Consoles, Search, AirPlay, Achievements, Scraper, Settings, Library.
Optional hidden tabs are filtered from this same order.

The AirPlay page reuses the existing receiver controls, translated labels and
native bridge without starting discovery or capture on entry. Existing app
input ownership handles its focus/actions, rather than adding another gamepad
subscription on each swipe. A modal help/PIN dialog retains focus and blocks
underlying tab cycling. Leaving AirPlay stops discovery through the existing
widget disposal, without disconnecting an existing stream.

## Controlled assembly

The initial temporary branch did not edit startup files. Its dispatch patch
was tested in a disposable CI checkout. After startup integration completed on
Claude at d27a06f6, that state was merged into the isolated checkout and only
its non-overlapping tab-dispatch changes were applied to AppScreen. Startup,
permission wrapper, logo geometry, launch resources and initialization/scan
implementations remain identical to 504. Engines, imports, catalogue data,
language maps, dependencies and stable identifiers are also unchanged.

The first rehearsal run 39844367586 intentionally remains recorded as failed:
45 tests passed; five fixture failures and five analysis infos were corrected.
Its successful material, transition and receiver checks are not described as a
successful whole run. No physical iPhone/Bluetooth or 60/120 FPS claim follows
from these automated checks.

## Validated combined source

Combined proof: source `01f6e9d44943b5f6bc8df3447ed9ddd465e3971b`, run
`39846213108`, job `120060044288`: full Flutter 3.47.2 analysis clean; 62
individually passed checks from source `534fb842` / run `39845018642` reused
only after exact input comparison, authenticated logs and sole-failure review;
the changed four-test input fixture passed. That earlier run remains failed.
Touch, keyboard, raw host controller translation, existing directional/bumper
pacing, focus/actions, retained modal focus and reverse playlist ownership are
covered. These are automated host fixtures, not physical Bluetooth validation.

Startup 504 delivery `39843964056` succeeded (checks/native/cold), and its exact
startup resources, engine/native inputs and toolchain are the delivery donor.
No unchanged native engine or previously validated unrelated Flutter suite is
rebuilt/replayed. The new IPA recompiles the combined Flutter app and retains
all existing packaging, payload identity and signature gates.

The temporary rehearsal workflow is consolidated into the maintained glass
workflow. The validated-integration marker avoids duplicate UI checks during
505 packaging. After a successful IPA, a separately scoped cleanup job deletes
only the temporary branch at the exact validated SHA, and only if that SHA is
an ancestor of the delivered commit. A moved branch is preserved for review.
Final IPA identity and artifact receipt are appended after delivery.
Delete the temporary branch after controlled integration, leaving Claude/main.
