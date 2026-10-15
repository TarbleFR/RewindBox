# Build 465 — PocketArch and Provenance catalogues

Baseline: delivered Build 464, branch `Claude`, source `5a5433eb`.
The maintainer confirmed on iPhone that custom skins work again and authorized
the catalogue audit, correction, push, CI and private test IPA without further
intermediate approval. Build 464 must not be reused for another binary.

Final private test IPA: **0.0.7 (465)**, source
`a0f1b291951008a141e0b857800c091660c2b855`, successful delivery run
[`38822682091`](https://github.com/TarbleFR/neostation-ios/actions/runs/38822682091).
PocketArch transport is repaired, its 26 complete originals are retained,
and only the two incomplete PSP originals are hidden. Provenance membership
is restored for PS1 and every other registry console with offered candidates.
No native loading, rendering, pressure or input source changed from Build 464.
Final IPA identity and verification are recorded at the end of this report.

## Confirmed causes and corrections

PocketArch is not a foreign skin format: its files are RetroArch `.cfg` touch
overlays already understood by the production converter. All 28 indexed
configurations at `stunrelay/PocketArch@33dc23be7ea5938956bbe686c1c9494ef5628e30`
were read. Their pages, normalized coordinates, backgrounds, descriptor
artwork, D-pads, buttons and sticks convert into portrait and landscape
layouts without changing the converter or native renderer.

The common failure is transport: `fileUri` percent-encoded each segment and
then passed it to `Uri.https` as an unencoded path. `Touch Overlays` became
`Touch%2520Overlays`. The corrected URI is built from raw path segments once,
for configuration and image downloads alike. The previous mock host decoded
the URL twice and therefore concealed this production failure; it now accepts
only the exact repository path. Catalogue verdict/preview rules advance from
2 to 3 so old failed downloads do not keep entries unusable for six hours.

Two PSP configurations really are incomplete upstream (`po-d0a8dfa31921` and
`po-b3669fc2b2dd`): the converter references five missing images in each,
including `l235.png`, `r235.png`, `l335.png`, `r335.png` and `r35.png`.
Their index entries carry the existing unsupported-overlay refusal. The other
26 originals remain candidates, with 39 console associations. The normal
native compatibility report remains authoritative; no source-wide acceptance
or source-wide rejection was added. Installed files, metadata, favorites and
orientation preferences are never deleted or migrated by this correction.

The current Provenance index, inspected at
`Provenance-Emu/skins@da7784136d7cec8fe614cb65feef36266af6fce9`, lists eight PSX
skins. Every one has `source: deltastyles.com`. NeoStation retained these
entries under DeltaStyles, but built its filter chips solely from that
attribution, making Provenance disappear for PS1. Membership in an index is
now retained independently of the author's host, including deduplication.
The Provenance filter can therefore select those PS1 entries while their
cards keep the correct DeltaStyles credit. Existing keys and download
identities do not change. Sources with no offered candidates are not shown.

Platform candidates now use the central console registry's id, import id,
display names and catalog aliases, with consistent case/separator handling.
This covers PS1/PSX/PlayStation and every integrated console, including
default-hidden platforms and future registry additions. A candidate is not a
compatibility claim: the real `info.json` still goes through the native filter.
The upstream catalogue currently has entries for PCE, Lynx and Virtual Boy,
but none for several newer integrated platforms (for example WASM-4); no
empty Provenance catalogue is forced onto them.

## Validation and boundaries

- Original `.cfg` files, all indexed image hashes, byte sizes and dimensions
  are captured under `test/fixtures/libretro_overlays/pocketarch/`, with MIT
  attribution and licence. Images are CI-only downloads, never app assets.
- The new focused workflow tests exact URI semantics, platform associations,
  source-filter behavior, original conversions, download/import services and
  installed skin preservation, then feeds the actual Dart output and
  hash-verified original images to the iOS Simulator native parser,
  compatibility filter and preview compositor for both orientations.
- Product changes are confined to the catalogue service, unified catalogue,
  catalogue UI and the two incomplete index entries. Native loading, rendering,
  pressure, D-pad input, touch tracking, game sessions and all 34 core binaries
  remain unchanged from Build 464. No new user-facing strings were added.
- CI run identities, actual results and final delivery identity are recorded
  below once complete. A test plan is not a successful run. Physical iPhone,
  real rotation, commercial games and hardware controllers remain manual.

Local setup note: automatic review stopped Flutter bootstrap when it attempted
to contact the cloud-instance metadata endpoint. The allowed offline Dart
conversion audit completed; the full Flutter/native checks run in GitHub CI.

## Candidate and pending runs

Product/audit source: `9c1d63827ae15bcae6a9b73bd4b6bf393987ec6f`.
The following runs were launched and are not yet recorded as successful:

| Check | Run |
| --- | --- |
| PocketArch originals and Provenance filters | 38815903796 |
| Full engine Dart/native checks | 38815903727 |
| Directional/pressure sessions | 38815904483 |
| Existing-install upgrade/loading | 38815907900 |
| Existing Libretro preview/cheat/core regression | 38815903637 |

The accidentally duplicated manual cheat run `38815911848` was cancelled
before execution; the original push-triggered run is retained above.
The delivery guard requires actual success and exact closed input identity
for these runs, including the new catalogue workflow's real-image native
compositions, before an IPA can be packaged. Three targeted Python guard
tests passed locally, including rejection of failed/skipped/wrong-source or
unrelated evidence. This is pipeline validation, not a successful IPA build.

First Dart attempt (`9c1d6382`, job `116700371912`): analysis passed;
577 tests passed and one old search assertion failed. It expected a shared
file to be found only by its winning source, whereas the requested correction
preserves both index memberships. The assertion is updated to require the
shared file under both indexes, with its original attribution and unique
download identity retained. The old failure is not counted as a pass.

Corrected test candidate: `21027385ba349fda77a5966b7eabcbd77a91e48b`.
Product bytes are identical to `9c1d6382`; the source-membership expectation
and delivery-only guards are corrected separately. Current pending runs:

| Check | Run |
| --- | --- |
| PocketArch originals, Provenance filters and native compositions | 38816490259 |
| Engine Dart/native plus full pressure sessions | 38816478454 |
| Existing-install upgrade/loading | 38816483690 |
| Existing Libretro preview/cheat/core regression | 38816486744 |

The separate directional run `38816480254` was cancelled while still queued:
the engine workflow already executes the same complete
`libretro_skin_press_probe.py` command and scenarios, with the same Xcode,
cores and simulator inputs. The delivery gate requires that exact successful
`skin-press` job and its actual execution step from `38816478454`, plus the
independent native/Dart checks; no planned result is treated as a pass. All
older queued `9c1d6382` runs were cancelled following the outdated search
expectation; the original failed Dart phase remains recorded above.

The corrected PS1 widget test passed in the first actual Dart phase, along
with download/import, installed selections and the other skin manager tests.
The complete rerun and native jobs must still pass before packaging.

## Actual first native results and retained failure

- Catalogue run `38816490259`, job `116702356265`: **109 Flutter tests passed**;
  **158 native checks passed** for 39 associations / 78 orientations, using
  279 original image files verified by SHA-256. Native reports: 68 compatible
  orientation reports and 10 adaptable, no incompatible candidate. Catalogue
  artifact `12011054111`, ZIP SHA-256
  `a0cd1f1e3e59a853da8ce1bd9b25ef6a269d9e45666fe58b7abab745d7eca5cd`.
  Original PSX portrait and landscape captures were also visually inspected.
- Engine run `38816478454`: Dart job `116702308526` passed (578 main tests,
  245 storage tests, source/locale/core contracts); native job `116702308801`
  passed (18 frontend executables, 1,133 pressure-pixel and 6,025 tracker
  checks; 74 iPhone sources compiled/linked; real Flutter channel codec).
- Loading run `38816483690`, job `116702331613`: exact 463 rejection reproduced;
  current installed-skin upgrade 53 checks and relaunch 10 checks passed.
- Catalogue/core run `38816486744`, job `116702341072`: 38 parser, 23 offline,
  15 live-source, two original Libretro configuration tests and 160 UIKit/core
  checks passed, including actual Ignited/Nestopia and full Libretro previews.
- The engine's pressure job `116702308728` completed 27 sessions / 2,786
  checks, with one failed final `press-flat-nes` iPhone assertion:
  `controller disconnect leaves no held input`. All other checks, including
  directional pixels, intensities and the preceding post-controller touch,
  passed. Failed artifact `12012176780`, ZIP SHA-256
  `258edf795ced8cd0d6a56b9700790afeb9d92a69492990c17fb7377b6b86fa0d`.
  This whole pressure run is **not a success** and cannot authorize packaging.

The failing final observer checked after a fixed 250 ms. The production latch
deliberately holds a short press for three **emulated frames**; the earlier
cancellation observer already waits for four actual core polls. The final
post-controller cancellation now checks contacts, resolved input and artwork
immediately, then independently observes four fresh core polls within two
seconds before requiring the same zero-button assertion. It never waits for
the expected button value. The original and final cancellation diagnostics
are retained separately. This is a stronger test observation; no runtime
input, rendering, loading or controller source is changed. A focused
reproduction and the relevant suites must pass before delivery proceeds.

Delivery attempt `38818023275` at `f1366b8b` was started with mandatory gates;
it must not package against the failed pressure evidence. Its successful
native phase remains genuine; no IPA success is claimed from this attempt.

That delivery attempt completed with successful `checks` and `native` jobs,
then refused the cold job at its first mandatory evidence gate with
`Directional skin sessions did not all pass`. It produced no IPA. This is
the intended fail-closed result, not a successful delivery.

Observer-only correction: `6f3f017c2ff0ca7bcb24acad2c6253f6b8ce5e99`.
Relevant reruns (pending until actual results below):

| Check | Run |
| --- | --- |
| Exact `press-flat-nes` / iPhone reproduction | 38819107430 |
| Complete engine/pressure suite | 38819105153 |
| Existing-install upgrade/loading | 38819110606 |
| Existing preview/cheat/core regression | 38819105076 |
| PocketArch/Provenance audit | 38819113652 |

The automatic duplicate directional run `38819105079` was superseded by the
focused reproduction. The unrelated broad simulator run `38819105117` was
cancelled; all relevant skin sessions run in the table above. The product
still changes only the same four catalogue paths, with native sources and
the converter/install service identical to delivered Build 464.

## Complete registry census and final regression evidence

The inspected Provenance snapshot contains 1,358 entries, last updated
2026-10-04T05:11:24Z. The central registry contains 42 embedded console
identities. Matching the published systems against that registry produces the
following candidate counts, regardless of the console's default visibility.
These counts precede download/native inspection and deduplication; they do
not certify every listed archive, orientation or current third-party host.

| Registry consoles | Indexed candidates per console |
| --- | ---: |
| NES | 91 |
| SNES | 132 |
| GB, GBC | 210 |
| GBA | 303 |
| Mega Drive, Mega-CD | 37 |
| 32X | 38 |
| Master System | 7 |
| Game Gear | 5 |
| SG-1000 | 3 |
| Arcade | 6 |
| DS | 354 (353 direct archive links) |
| N64 | 57 |
| PS1 / PSX / PlayStation | 8 |
| PSP | 20 |
| 3DS | 92 |
| PC Engine, TurboGrafx-16, PC Engine-CD, TurboGrafx-CD | 5 |
| Atari Lynx | 3 |
| Virtual Boy | 3 (2 direct archive links) |
| WonderSwan, WonderSwan Color, NeoGeo Pocket, NeoGeo Pocket Color, Atari 2600/7800/5200, ColecoVision, Pokémon Mini, Game & Watch, Mega Duck, Watara Supervision, Arduboy, WASM-4, Uzebox, Channel F, Intellivision, Odyssey 2, PC-FX | 0 |

The eight PSX entries are DualShocked, the two HZN PS1 console styles,
M-Gage PlayStation Gamepad, Belmon T Taco PSX Dark, PS1 Controller,
PS1 Dark Controller SCE and PS1 Pocket Taco Minimal. All eight have direct
`.manicskin`/`.deltaskin` URLs and DeltaStyles attribution. Original
DualShocked is also exercised by the real native pressure and existing-install
regressions; the catalogue chip fix does not bypass native inspection of
the seven other archives.

At source `6f3f017c2ff0ca7bcb24acad2c6253f6b8ce5e99`:

- Engine run `38819105153` completed successfully: Dart job `116711020448`
  passed the 578 main and 245 storage tests; native job `116711020713`
  passed the frontend, 6,025 tracker, iPhone compilation and actual channel
  codec checks. Pressure job `116711020588` passed **27 sessions / 2,840
  assertions**, with zero failures. Artifact `12013710327`, ZIP SHA-256
  `eb82a71d374df04dd4d1a2e4c52ed6a171223b423b1e03e9d744eea85c78eb29`.
- Focused iPhone `press-flat-nes` run `38819107430`, job `116711036861`,
  passed **110 assertions**. Its retained report observes zero buttons at
  frame 775 after cancellation at frame 760 (0.259 seconds), independently
  of the expected button value. Artifact `12013116007`, ZIP SHA-256
  `74b8ef224f24e44ed6184a300cb468f4d5c5e792ac38f4a911615b5ba18b544a`.
- Catalogue run `38819113652`, job `116711052906`, passed again: 109 Flutter
  tests and the 39 original PocketArch associations / 78 native orientations.
- Cheat/preview run `38819105076`, job `116711023170`, passed again,
  including 128 actual Ignited/Nestopia, 20 Nestopia cheat, 10 overlay preview
  and four Snes9x checks.
- Loading run `38819110606`, attempt 1, failed before the unchanged 463
  witness application produced any report (`probe.json` absent; launcher
  had no process id at the 120-second diagnostic; system logs show the
  application entering UIKit only at 23:02:57, after that launch deadline).
  It is not an application assertion failure or a
  successful test. Failed artifact `12012564293`, ZIP SHA-256
  `83cc9ea517dc1e276d55774c26b0b66363dbf1d1bdb06b5d199d4710fe547037`.
  Only this failed job was rerun on the same exact source. Attempt 2, job
  `116718443812`, **passed**: the exact 463 rejection was reproduced, then
  all 53 candidate upgrade/selection/orientation/fallback and 10 relaunch
  assertions passed. Artifact `12013283201`, ZIP SHA-256
  `cc02719e879428b12383a4efff787ca1922cf95e2292a434d34e0cc69a419667`.

With all required runs actually successful, private delivery run `38822682091`
was dispatched at source `a0f1b291951008a141e0b857800c091660c2b855`, build
number 465, full validation, benchmark disabled, encrypted to the existing
maintainer recipient `build-utils/delivery-424-recipient.pem`. Packaging and
final IPA verification remain pending until the results below.

## Final private IPA and independent verification

Delivery run `38822682091` at `a0f1b291951008a141e0b857800c091660c2b855`
completed successfully: `checks` job `116722744730`, `native` job
`116722745064` and cold iPhone Release job `116723545669`. The optional warm
benchmark job was intentionally skipped (`benchmark=false`). Successful
unchanged Dart and native phases were reused only after their closed input
identities were verified; the changed pipeline guard checks ran again.
Xcode Release compilation completed in 326 seconds; sealing/export took 55.

- Encrypted IPA/evidence artifact: `12013744858`, 216,816,029 bytes;
  ZIP SHA-256 `a8b7bb96c62deb71c4156d6a3dc687e5450e3ffc008a3e86621c93312aebf735`.
- Final sealed IPA: **215,262,198 bytes**, SHA-256
  `e5b49390d78f2ad9f340c057be694cb0773b8888f1b6a5f44c748ffc980d48ad`.
  Filename: `NeoStation-Build465-a0f1b291.ipa`. Do not reuse build number 465.
- Independent verification of the transferred artifact confirmed the official
  ZIP digest, both final IPA integrity records, ZIP CRCs, exact source commit,
  app and five extension versions, iPhoneOS platform and minimum iOS 18.0.
  All 76 compiled payload fingerprints match the pre/post-signing manifest;
  ABI metadata and compiled code/data sections are unchanged by signing.
  Raw framework hashes change with the delivery signatures; these are not
  falsely claimed to equal the unsigned package hashes.
- All 34 Libretro cores are covered by those payload fingerprints. CI verified
  their unchanged pinned package before sealing. The bundled catalogue index
  exactly matches the corrected repository asset; no CI skin fixtures or
  original PocketArch artwork were added to the application.
- Decryption used the maintainer's existing recipient key on the Windows PC;
  its private key never left that PC. Only the small encrypted password
  envelope was rewrapped for this session, and transient plaintext passwords
  were deleted. No public release or device installation was performed.

The result is a private test IPA requiring Apple re-signing with SideStore.
Actual iPhone upgrade, real rotation, commercial-game use and a physical
controller still need maintainer validation. Simulator contacts and virtual
controllers are not proof of those hardware behaviors. Installed user skins,
ids, favorites, metadata and portrait/landscape selections are preserved.
