# Build 465 candidate — PocketArch and Provenance catalogues

Baseline: delivered Build 464, branch `Claude`, source `5a5433eb`.
The maintainer confirmed on iPhone that custom skins work again and authorized
the catalogue audit, correction, push, CI and private test IPA without further
intermediate approval. Build 464 must not be reused for another binary.

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
