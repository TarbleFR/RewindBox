# Build 468 — NES skin session lifetime repair

Candidate source: `4411dd2de0278c76010ce122df04d5000f35c4a5`
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
- `38961617527`: same production Nestopia core, original upstream
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
