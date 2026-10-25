# RewindBox UI correction — build 511

The maintainer rejected the delivered 507 carousel and reported the main tabs
colliding with the clock/device/controller status. The correction starts from
`92dd1caa3442769dc6148df33a488d85e7b88500`, preserving the complete delivered 509
Switch retirement/deletion work, 508 RPCS3 audit and all earlier engines.
Concurrent RPCS3 source work at `50714fe0980d0b50ccd93c1c739c480b054a31b9`
is preserved; this UI scope is closed against that integrated head. Build 511
is reserved for this correction so another chantier can deliver 510 independently.

The first implementation had only a shortened, attenuated PnW motion envelope,
a modest transform around the grid cards and three independently aligned header
groups. That did not reproduce the requested complete selection or composition.

## Corrected presentation

All 21 selection segments from Mau Ali's original dotLottie are retained with
original 60 fps timing, full unattenuated X/Y deformation, animated Bezier shape,
capsule impulse, moving rim and fill transparency. The existing real icons,
canonical tab identities and variable visible destination cells replace the
reference's fixed five icons. Rapid reversals start from the current position
and shape. The compiled generated data is derived by
`build-utils/extract_mau_ali_motion.py`; `--check` verifies it against the original
archive. Original archive and full Lottie Simple License/attribution remain.
There is no new dotLottie runtime or package dependency.

The header measures all groups before placement, reserves safe-area insets,
permits only a moderate navigation scale-down, then puts navigation on its own
row where necessary. A shared header/body compositor reserves its measured height in the same
layout pass, so content stays below additional rows without a delayed frame. The console carousel also reserves the
normal header clearance. Device and controller battery readings remain visible.

The console carousel has square branded artwork without the grid logo/footer.
Absent artwork still gets its existing system logo fallback. A bounded Flow
paints cards in far-to-near order, with symmetric perspective and a dominant
central card. The established page controller/snapping and input ownership are
retained; game-box and grid/list presentations keep their existing path.
Artwork widgets are cached within a nine-card window; animation frames repaint
transforms without per-frame image decoding. Reduced Motion and Low Power Mode
use static geometry and immediate controller navigation.

## Validation and delivery

Targeted checks cover all author segments, interruption and reverse selection,
all eight real tabs, complete production header with both batteries, safe areas,
320/393/852/956-point widths and 1.0/1.4 text scaling. Full production Header,
NativeCarousel and SystemCard compositions are rendered in portrait/landscape;
local review uses only cropped reference artwork from the maintainer's captures,
which is not committed or redistributed. CI uses generated neutral artwork.
Real Flutter fonts and icon fonts are loaded for review. Depth tests verify
symmetric projected bounds, paint order, actual hit testing, touch flings,
controller navigation, viewport interruption and route return.

Initial fixture failures (missing theme/font/event-channel setup) and a real
small-width overflow in the leading control were corrected before delivery.
Visual review caught and corrected an asymmetric perspective composition before
IPA assembly. These failed attempts are not represented as successful checks.

Only changed UI tests are run; delivered 509 native/engine and unaffected 507
liquid download/battery validations are reused. Final workflow/source identity,
IPA digest, bundle versions and packaging checks will be recorded after the
actual Release build completes. No release, tag or main update is authorized.
No physical-device installation, gameplay, temperature or frame-rate claim is
made. The user's word "surchauffement" was interpreted in context as the reported
"chevauchement"; no unrelated emulator thermal tuning was undertaken.

Desktop Commander reported a monthly usage limit before file transfer. A direct
IPA download remains deliverable; no claim of a successful Windows Downloads
copy will be made without actual verification.

CI run `39888866329` from `719de6ec3bf967862e95f9a71b2638bba26d9e4e`
passed source closure, analysis and 26 real UI/header/navigation cases. Its
combined test step failed only in the visual fixture setup: two fresh SQLite
initializers raced across Flutter test isolates. The recovery authenticates
that precise run/job and unchanged inputs, retains the failed overall result,
reuses the 26 passing cases, and runs only the visual fixture in its own process.
The five carousel/profile and eight legal cases had not yet run in that CI job.

Recovery proof `fa5c249dbca0f988128021e465b3aa936c7ebea3`, run
`39889391790`, job `120205228418`, completed successfully. It authenticates the
26 passing cases and analysis above, passes the two isolated complete-screen
visual cases, five affected profile/input/rotation/accessibility cases, and eight
legal-packaging checks. Recovery `39889262784` stopped while reading ANSI-bearing
logs; the current capture explicitly permits those bytes into a private Python
buffer, never into a terminal. No product inputs changed during either recovery.
The first proposed Release recipe pinned that successful proof and the exact GoW3 Core
`50714fe0980d0b50ccd93c1c739c480b054a31b9` / `39888215155`, waiting for its success.
Its independent concurrency group preserves the separate 510 assembly run.

A final rapid-input regression reproduced cumulative deformation when interrupted
shape residue was carried through the next full source peak (observed X scale
1.2942 beyond the source bound). The correction fades only that interrupted
residue during the first four source frames; uninterrupted source animation is
unchanged. A 24-selection regression and the existing complete eight-tab
selection test pass locally. The unshipped first assembly was superseded.
The final targeted proof authenticates recovery 39889391790, checks this exact
code delta, reuses its 32 unaffected Flutter and eight legal cases, and reruns
only the affected selection case plus the new regression: 34 Flutter cases in
the resulting proof chain, without replaying native or unchanged visual tests.

Final rapid-selection proof `554c8540570c9eab3c19da0a53123381051977bf`,
run `39894280161`, job `120220965793`, completed successfully: exact delta
authentication, changed-file analysis, complete eight-tab selection and the
24-selection non-accumulation regression. The final recipe pins this proof.
The independent GoW3 Core run `39888215155` also completed successfully.

## Delivered artifact

Final Release source `12589d3fa7c3d5fd28537c456cde1b80a06cca98`, run
`39894506630`, completed successfully (source gate, native evidence closure and
iPhone Release job `120221819782`). The packaged AOT binary contains the complete
21-segment/60 fps author profile, Cover Flow and shared header/body compositor.
The actual final ZIP passed strict nested signature verification; compiled
code, data sections and ABI identities were unchanged by signing.

Delivered `RewindBox-Build511.ipa`: version **0.0.8 (511)**, iPhone **arm64**,
minimum iOS **18.0**, **186,119,672 bytes**, six aligned extensions and **86**
verified ad hoc signatures. Apple re-signing with SideStore/AltStore is required.
SHA-256: `714eecf8c7cc09e9d5b4bc4da375708f1773b8ad4413715c0630aef7c5a54f58`.

Encrypted CI artifact `12476174472` has ZIP SHA-256
`d4042cfa2dd66e9bc791b066baededc7c68fec66473720bee3c2fcf97a640cb7`.
The decrypted IPA digest matches SHA256SUMS, signed-payload identity and final
UI-validation report. It was saved successfully for direct download. The PC
Downloads copy remains blocked by Desktop Commander's reported monthly quota.
No physical-device installation, gameplay or thermal validation is claimed.
The machine-readable receipt is `docs/evidence/ui-correction511-delivery.json`.
No release, tag or main update was made.
