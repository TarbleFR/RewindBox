# Melo-Controller b16a8e3 — handoff for the next MeloNX Core freeze

Source only. `wiring.patch` moves the vendored on-screen controller from Melo-Controller `c049ce88` to `b16a8e39`
(public, GPLv3 like the pinned revision, licence file byte-identical: blob `f288702d`). It is the controller code
MeloNX 2.8 ships (comparison: `docs/melonx-2.8-comparison-2026-11-16.md`).

Why it waits for a freeze: `build-utils/melonx/source.json` names the controller revision, the pinned Core's identity
carries that file (`package_runtime.py` asserts `identity['source'] == source.json`) and Core gates list it as an
input. Changing it outside a freeze would stop the delivery of the pinned Core. Owner of the freeze: the MeloNX
session.

## What b16a8e3 changes for players

- A button in toggle mode is released when the overlay disappears (menu, close): no button left held in the game.
- Sticks track one touch each with raw touches instead of a pan gesture: a stick and buttons can be used at the same
  time without the gesture system cancelling one of them; a stick returns to centre when its view leaves the window.
- A stick's own scale is multiplied by the global controller scale (it replaced it before); the drag range follows
  the drawn size.
- The layout editor's "D-Pad Acts Like a Stick" is per game and the buttons now read that switch (before, the editor
  wrote the per-game key and the buttons read a global preference the editor never set).
- Stick positions reach the router directly instead of through `DispatchQueue.main.async` (UIKit touches are already
  on the main thread).
- Sliding between buttons only follows a touch that began on a control.

## Contents of `wiring.patch`

- `build-utils/melonx/source.json`: controller revision.
- `.github/workflows/standard-delivery.yml`, `.github/workflows/melonx-host.yml`: fetch b16a8e3 (the macOS host job
  compiles the vendored Swift against the iPhone SDK).
- `build-utils/melonx/vendor_controller.py`: the per-game and global D-pad keys get the `rewindbox.melonx.` prefix;
  fails closed if the D-pad preference changes shape again.
- `packages/melonx_internal_bridge/ios/Classes/MeloNXInputDiagnostics.swift`: the input journal reports the D-pad
  switch the buttons use (this game's, else the global one).
- `test/melonx_input_stick_test.py`: the existing check of the pinned checkout follows the new preference.
- `assets/legal/melonx/license-sources.json`: revision and licence URL.

## Checked locally (Linux)

- `vendor_controller.py` on c049ce88 (committed script) and b16a8e3 (patched): both pass; the generated sources
  differ only in the eight files b16a8e3 changes and `adaptation.json`.
- `test/melonx_input_stick_test.py --controller <b16a8e3>`: passed (78 checks; Swift execution not run here).
- `test/melonx_text_input_test.py` with `MELO_CONTROLLER_DIR=<b16a8e3>`: passed (42 checks).
- `test/standard_delivery_contract_test.py`: 120 tests OK with the patch applied.
- `test/legal_bundle_preflight_test.py`: OK.
- Not done: the Swift compile (macOS host job), any IPA, anything on an iPhone.
