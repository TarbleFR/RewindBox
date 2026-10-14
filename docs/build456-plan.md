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

Compilation, export and final checks passed in run
`38591125638`, candidate `6346df7dcbe9f2a40caea058bc67321f6f72e85f`.
`checks`, `native` and the cold iPhone build passed; warm was intentionally
skipped because benchmarking was disabled.

Encrypted artifact: `11909445866`, 211,401,117 bytes, archive SHA-256
`4549b873f27c3ccadc4e3352f269666993eefd586afcd2f1bd7d521dfdf1a99b`,
expires 28 October 2026. This hash identifies the encrypted ZIP.

The **sealed, decrypted IPA** is 211,140,422 bytes, SHA-256
`5dc0cf7e798a95eb001f093533dbb590a0d3b08738a412e8a03313a8e0a86b35`.
It matches both `SHA256SUMS` and `signed-payload-identity.json`.
Independent ZIP inspection confirmed:

- App and five helper extensions: **0.0.7 (456)**.
- Packaged source identity: exact candidate SHA above.
- Signing preserves code/data and ABI metadata in all 56 executable images.
- Sixteen native shader class/selector markers are present in their actual
  compiled owner images, including recovery and GPU-confirmed activation.
- Both catalogs match the source bytes; all 43 offered Dolphin shader files
  match their pinned size and SHA-256.
- No Mattias shader file is bundled; the existing local import remains.

This build is intended for the maintainer's physical iPhone tests. Earlier
results do not establish the cause of the initial device crash or prove an
effect in the integrated Dolphin engine. No device validation is claimed.
