# Build 472 — embedded game return label

The maintainer confirmed that the Build 471 Nestopia startup correction works
on their iPhone. The inactive skin report was explained by a connected physical
controller; no skin/input change is part of this delivery.

The new video shows Astérix returning from the embedded PlayStation session:
the native view disappears, revealing `Jeu en cours…` for several seconds before
the launch dialog closes. The same common Flutter route underlies Libretro,
Dolphin, ARMSX2 and RPCS3 (also the two native Ports).

`GameLaunchManager` correctly remains in `playing` until the native end event or
active-session probe confirms teardown. Its dialog had used the external-game
playing label during this interval. The native session fully covers that route
while playing; its first visible frame on return therefore showed the wrong
message. Libretro/Dolphin/RPCS3 status polling makes the mismatch especially
visible, but it is an underlying return-label issue, not evidence of a game
continuing to run or an incomplete shutdown.

The only product change is `lib/widgets/game_launch_dialog.dart`: when the
manager identifies an embedded iOS session, prepare the existing translated
`closingGame` label behind the native view. External sessions retain their
playing label. The real session phase, native teardown, cleanup, media gate and
route-removal timing remain governed by the existing lifecycle. There is no
extra delay and no premature `endGameSession` call. All twelve existing
translations are reused.

Targeted evidence (passed CI): `test/game_close_status_test.py` compiles the
actual manager and dialog listener/cleanup/route-removal methods with Flutter.
It removes a covering native-style route before a terminal event, verifies the
very first revealed label, keeps cleanup blocked until confirmed end, and
checks duplicate notifications, music and route ownership. Six old Build 471
negative controls, six corrected embedded-return cases and one external case
are included. This validates the common UI; no physical engine/gameplay run is
claimed.

The first harness run `39085427665` at `9b6d120e` passed the old Dusklight
negative control, then timed out awaiting the singleton manager's finalization
across separate Flutter FakeAsync test zones. It produced no complete verdict
and is not accepted validation. The harness now runs all thirteen sequential
returns in one app/test clock, retaining every original assertion; its bound is
reduced to two minutes. The product file is byte-identical to `9b6d120e`.

Build 471's corrected Nestopia and all other native inputs must be reused by
identity. Successful unchanged tests must not be repeated. Delivery commit,
actual CI results and final IPA verification are recorded after production.


The corrected harness source `a5e8fe6ee42c53bd20a2ce6f8b96a763f59a262e`
passed run `39086239948`, job `117553304499`. All thirteen cases completed in
one Flutter clock: six exact old-label reproductions, six corrected first-frame
returns, and one external desktop return. Every case also verified deferred
single cleanup, no early music, controller/back protection and owned-route
removal. Twelve locale catalogues contain the three existing session labels.
Two new delivery-composition guard tests passed locally once; previous tests
are reused, not rerun.

The next available delivery number is 472 (the latest completed IPA is 471).
The delivery recipe pins this new UI source and successful run, preserves the
471 Nestopia proof and all unchanged native inputs, and rejects any other
product or core edit. No public GitHub release is requested or created.


## Delivered IPA verification

- IPA source: `02550f923dd2d086227e9f379a896c23ef6670ac` on `Claude`.
- GitHub Actions delivery run `39086364895`: checks `117553679232`, native
  reuse `117553679091`, cold Release `117553781844` succeeded; optional warm
  build skipped. Exactly one Build 472 IPA was produced.
- Final IPA: **0.0.7 (472)**, **218,606,012 bytes**,
  `NeoStation-Build472-02550f92.ipa`.
- Final SHA-256:
  `b47d59188f28b5c6e70de11207b77fe7a81f91f13ebecc5a53d08c5c49455b26`.
- Authorized recipient remains
  `docs/delivery/recipients/neostation-470-skins-recipient.pem`.
  Encrypted artifact `12120918802`, **219,529,117 bytes**, archive SHA-256
  `e7a2291d1df3a0243e46cbc36d733433f90cd5c2a8d0cb0c0af445d66c250f50`.
  The RSA key and transient AES secret are excluded from evidence/deliverables.
- Independent inspection matched the actual IPA against the final CI seal,
  source stamp, all six application/extension versions and ZIP structure.
  All 76 thin Mach-O identities match the seal; CI checked 79 ad hoc bundle
  signatures. Apple codesign was not rerun on this Linux inspection host.
- The fat-wrapped Flutter App executable was inspected separately: its arm64
  AOT fingerprint differs from delivered 471. Final AOT file SHA-256 is
  `4ff1ea8515319a1b16a049e26a22ac69c05b7f3b7dfc287cbc7a41cf47e10179`.
  This delivery includes newly compiled Dart code, not a renamed old IPA.
- Every one of the 34 Libretro cores has the same code/data/ABI fingerprint as
  delivered 471. RPCS3, Dolphin, ARMSX2 and MoltenVK also retain their exact
  code/data/ABI identities. Nestopia is still the tested reset correction,
  UUID `2321DDEC-E187-3AC6-80FD-C94C63C718C0`, iPhoneOS, minimum 18.0.
- SideStore Apple re-signing/provisioning is required as usual. No physical
  iPhone run of 472 or real commercial-game engine test is claimed by the
  Flutter return scenarios. The maintainer's physical confirmation concerns
  the 471 startup fix; 472 preserves that core by identity.

## Changed files

The only product file is `lib/widgets/game_launch_dialog.dart`.
The focused test is `test/game_close_status_test.py`, driven by
`.github/workflows/game-close-status.yml`. Delivery provenance is composed by
`.github/diagnostics/game_close_delivery.py` with two new unit checks in
`.github/diagnostics/game_close_delivery_test.py` and the existing
`.github/workflows/retroarch-delivery.yml`. `AGENTS.md` and this report record
scope, actual results, the retained harness timeout and delivery identity.
No emulator-core, skin, touch, cheat, save, preference or native teardown
implementation was modified.


## Private handoff

Desktop Commander completed the independent Windows copy with the same
218,606,012 bytes and SHA-256:
`C:\Users\Coren\Downloads\NeoStation-Build472-02550f92.ipa`.
The copy used create-only semantics; existing IPAs were preserved.
The transient delivery password was removed after the verified copy.
The downloadable IPA and evidence ZIP are provided privately in the chat;
no public GitHub release was created.
