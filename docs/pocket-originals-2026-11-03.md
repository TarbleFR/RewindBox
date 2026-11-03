# RewindBox Pocket originals — 3 November 2026

Only the two approved designs are included: **Wii Pocket** and **GameCube
Pocket – Ivory**. They are original RewindBox artwork, inspired by the
maintainer's approved iPhone boards in [design/pocket](design/pocket/).
The third-party GameCube Pocket archive and artwork are not redistributed.
The wider proposed console lineup is not bundled.

## Reconstruction provenance

Workspace maintenance removed the unpublished local commit `15c82bd` before
its push was authorized. That object is not available on GitHub. This change
reconstructs the same two-pack scope against the current `Claude` branch; it
does not claim the old commit, old binaries or its old 67-check result were
recovered. The approved body images were recovered unchanged. The input
bindings and hit rectangles came from the retained earlier collection; the
control sprites and integration were reconstructed and checked afresh.

## Product behavior

The catalog offers **RewindBox Originals** before external catalog requests
finish, including offline. Existing sources, installed skins, favorites and
console/game choices are retained. Import uses the existing skin service and
replacement checks; installing a pack does not select it automatically.
Choose portrait, landscape or both in the existing skin manager.

Both packs have edge-to-edge and standard iPhone layouts in both
orientations. The game window is 4:3. Each button has separate normal and
pressed images; sticks have independent moving knobs, with a round yellow
C-stick cap for GameCube. Complete manager/catalog previews are composed
from those same resources. The body images have no baked-in buttons.

GameCube includes the main stick, C-stick, D-pad, A/B/X/Y, Z, L/R, Start and
Menu. Wii includes the Nunchuk stick and C/Z, Wii Remote D-pad, A/B, 1/2,
plus/minus/Home and Menu. The game area retains Dolphin's touch pointer.

The existing native `DOLSkinOverlay` sends these inputs through the
DolphiniOS controller path, supports simultaneous fingers, pressed artwork,
moving sticks and haptics, and releases held inputs on rotation, menu and
backgrounding. No native bridge or Core source changes are part of this
commit. L/R are full presses; Wii Classic Controller skins are unsupported.

## Integrity and previews

`assets/skins/pocket/catalog.json` binds each local archive to its byte size
and SHA-256. Both classification and installation authenticate the local
bytes. Classification uses the existing bounded ZIP reader and real Dolphin
compatibility reader, with no HTTP fallback. Verdict cache keys include the
archive digest; favorites keep their stable entry IDs.

Optional `info.json.previewImages` maps portrait/landscape to complete
PNG/JPEG images. The manager validates their confined paths, resolved
symlinks, size (at most 16 MiB) and type signatures. Missing or invalid
optional previews fall back to the existing bitmap background, preserving
older skins. The opaque raw body game window is cut out by the existing
native background mask at runtime.

## Validation

Fresh scoped execution: **126 Flutter tests passed**, zero failed or skipped,
across nine files (Pocket 31, existing Dolphin 11, preview safety 8, bundled
catalog/import 9, offline catalog widgets 2, unified catalogs 25, downloads
10, import service 21, manager widgets 9). Flutter 3.47.2 / Dart 3.13.2 was
used. Targeted analysis of twelve Dart files completed with no diagnostics.
The report binds 21 source files and all seven runtime assets to SHA-256.

Asset checks passed for both archives, all 59 PNG resources and eight
layouts, including CRC, resource presence, input coverage, distinct pressed
states, moving knob resources, game/control separation, reference safe
insets and calculated hit-frame sizes on five iPhone dimensions. The minimum
is 44 pt; each D-pad/stick is measured as one directional cluster, not as
four separate targets. A second generation produced all sixteen review
files byte-for-byte identically, including both archives.

| Pack | Bytes | SHA-256 |
| --- | ---: | --- |
| Wii Pocket | 5760549 | `5a8a4db1d7480269c8011939a3dc6d288bd05687f21f24d8d503972aa9c2b9d5` |
| GameCube Pocket – Ivory | 6053003 | `d37fbd2138c47a271f37e8b352b76b04624abc8b45e8996ea87dd5886316b13b` |

After testing, the shared branch advanced through `792d72c9` to `71459be5`.
Those changes concern the RPCS3 workflow, MeloNX Core preparation and
related documentation. Every tested source hash was checked again and still
matches; the unchanged tests were not needlessly replayed.

Fresh evidence and exact commands are recorded in
[evidence/pocket-originals](evidence/pocket-originals/). Asset generation is reproducible using
`tools/skins/build_pocket_skins.py`; resource, geometry and effective iPhone
fit checks use `tools/skins/verify_pocket_skins.py`. The phone matrix models
the actual native tall-screen versus standard-layout choice, then its aspect
fit. Calculated touch sizes are not physical-device observations.

The scoped Flutter tests execute the actual app parsers, catalog and import
services and widget rendering, rather than a reimplementation of them.
Apple compilation and physical iPhone play of these two original packs
remain pending. Source/host success does not establish on-device gameplay,
latency, haptic feel or comfort. No CI, IPA or release is produced here.
