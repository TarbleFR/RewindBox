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
