# Private Build 457 — RetroArch compiler isolation

The maintainer's private test IPA/download-folder authorization remains
active. There is no authorization for a public release.

- Output version: **0.0.7 (457)**. Build 456 is the failed device candidate
  and will not be renamed or replaced with different bytes.
- Candidate: `8543b7609d1c793d4c4803b8d95cdecb7561f988` on `Claude`.
- Delivery run: **38608563662**, `retroarch-delivery.yml`, scope `full`,
  benchmark disabled, cold iPhone build. Compilation in progress.
- Earlier 457 attempts **38602619474** (`90f62c5c`) and **38605838506**
  (`8e6e1fe6`) were cancelled before delivery to include the final menu
  correction and scope-restoration regression. No IPA from either run is
  delivered or renamed.
- Public recipient: existing `build-utils/delivery-456-recipient.pem`,
  SHA-256 `49764c811fc0dd73213b5c93835d24766cbeda98e4989885ae9733f60e43af12`.
  Reusing the recipient key does not reuse a build/artifact number. The
  private key stays outside Git; delivery artifacts remain encrypted.
- Product correction: `d457c8ff3b613799317f972b502878b776d8f2a0`, private
  glslang/SPIRV-Cross exports in the shader kit; no Dolphin runtime/core,
  shaders or console-specific core patch.
- Compiler regression source: `90f62c5c9c79c62fdf598e5305f021c0ab0e3833`,
  run **38602335265**, five
  native faults with the original boundary and five successful translations
  with the production boundary; both real compiler source versions loaded.
- Menu correction: `8e6e1fe6` allows retry when a saved preset has no active
  rendered program; `8543b760` preserves resolved game/console scope
  behavior while reflecting actual activation.
- Final native frontend and iPhone build checks: source candidate above,
  run **38607085991**, passed.
- Final session validation: source candidate above, run **38607080426**,
  six synthetic error/recovery scenarios and six official HTTPS/pixel
  scenarios passed. Software/Vulkan test cores and the real DeSmuME core
  with original homebrew content; iPhone SE (3rd generation) iOS 26.2
  Simulator. This is an embedded native session probe, not a physical
  iPhone launch of the complete IPA. Evidence and exact limitations are
  documented in the native diagnostic report.

The final IPA is also checked for the actual dyld export boundary. A sealed
Build 456 IPA is rejected by this gate. The delivery will record the new
sealed IPA's byte count, hash, packaged source/build identity, and download
destination after these checks pass. Neither build success nor source tests
are described as physical iPhone gameplay validation.

Native evidence and limits: `retroarch-shader-compiler-2026-10-14.md`.
