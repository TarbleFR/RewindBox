# Build 468 — NES skin session lifetime repair

Validated product source: `4411dd2de0278c76010ce122df04d5000f35c4a5`
Final fixture source: `9ee313d96b79550406c62c5b862c0f859b01ad00`
Delivery recipient: `docs/delivery/recipients/neostation-468-chatgpt-recipient.pem`
This delivery does not change existing emulator cores, game libraries, skin catalogues or user preferences.

The two field logs stop without a normal END event, one after NESThumbstick
became active and another before that event. Neither provides a crash report,
so the termination mechanism (exception, watchdog or jetsam) is **unproven**.

Source audit identified work that may outlive its game view: queued image/PDF
decodes and layout preflight while a new representation/session is selected.
The candidate cancels stale decoded-image work, snapshots preflight paths before
the image worker, and revokes renderer callbacks/assets when input polling
is stopped. It also validates libretro software-frame pitch without assuming
that the observed filtered 602 x 224 frame is invalid. Valid skins remain
supported; incompatible artwork retains the existing native fallback.

Targeted CI:
- `38963540654`: same production Nestopia core, original upstream
  NESThumbstick image, 31 original-skin sessions, 4 unskinned sessions and
  2 other-catalogue sessions, synthetic ROMs only.
- `38961617939`: libretro native/host/language/skin and iPhone checks.
- `38961617429`: installed skin preservation and per-orientation fallback.
- `38961617498`: directional pressure/skin regressions.
- `38961617420`: other integrated-core simulator tests.

These run IDs are targets, **not reported as passed here**. The delivery
requires exact successful 37-session evidence and the pre-existing
licence/cheat/skin gates. No physical iPhone or commercial NES game test
is implied. If the simulator does not reproduce the intermittent crash,
a device crash .ips / jetsam report is still needed to prove the root cause.

The original 37-session baseline run `38961318281` exercised all 37 real Nestopia sessions
without unexpected termination; the six negative checks concerned a test-only
selection writer bypassing the production in-memory frontend store. The corrected
fixture uses the native `LibretroFrontendStore` and requests notched-iPhone landscape.
This historical result is not substituted for the corrected fixture's final proof.

CI is deliberately gated: no private Build 468 release IPA is accepted unless
the final exact-source stability suite succeeds and the delivery IPA validator passes.
