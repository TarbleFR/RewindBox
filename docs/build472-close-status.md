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

Targeted evidence (pending CI): `test/game_close_status_test.py` compiles the
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
