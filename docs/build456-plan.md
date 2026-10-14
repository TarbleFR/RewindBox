# Private Build 456 — shader fixes

The maintainer authorized a private IPA on 14 October 2026, after the shader
changes through `5d90ea223d0dc1894b0763f3ea77a70be844b2ba` were tested.
No public GitHub release is requested.

## Candidate and delivery

- Branch: `Claude`; unchanged shader runtime from the completed investigation.
- Application output: **0.0.7 (456)**, through the workflow's build-number
  override and app/extension version stamping. Do not reuse Build 455.
- Workflow: `retroarch-delivery.yml`, scope `full`, benchmark disabled.
- Recipient: `build-utils/delivery-456-recipient.pem`, SHA-256
  `49764c811fc0dd73213b5c93835d24766cbeda98e4989885ae9733f60e43af12`.
  The private key stays outside Git. Only encrypted delivery artifacts are
  uploaded by the workflow; the decrypted IPA will be supplied privately.

## Preflight

The delivery inventory omitted 39 historical files already accepted in
`29b24945`, and six shader additions tested in `5d90ea22`. The updated gate
requires exact bytes and modes from those references; it refuses later
mutations, deletion and symlinks. The recipient is pinned by hash and PEM type.
The original closed-tree check and unrelated-runtime rejection remain intact.

- Delivery pipeline regression: **15 tests passed**.
- Full offline preflight and unchanged source contracts: passed.
- Shader runtime evidence: see `shader-recovery-2026-10-14.md`.

## Final artifact checks

Compilation and export are pending. Before delivery, verify the sealed IPA
hash against its manifests, output version in the app and extensions, retained
core/dependency identities, new shader recovery and activation selectors,
bundled catalogs, and all 43 offered Dolphin shader files by size and SHA-256.
Mattias files must remain absent from the app bundle.

This build is intended for the maintainer's physical iPhone tests. Earlier
results do not establish the cause of the initial device crash or prove an
effect in the integrated Dolphin engine. No device validation is claimed.
