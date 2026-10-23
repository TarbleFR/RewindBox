# Build 509 — embedded-only Switch library and game deletion

The maintainer's recording shows three retired `melonx://game?id=…` entries
failing with `Bad state: localGameRequired` in the multi-delete dialog. Both
the dialog and repository required a local game extension, making these old
alternate-frontend references impossible to remove. The maintainer then
explicitly required removal of all obsolete external MeloNX references.

On iOS, full library reads and Switch playlist reads now purge those retired
rows, the old exported-library preference cache and external iOS Switch
emulator choices. The operation is transactional and repeatable; it runs before
returning games to the UI, without requiring working keys, firmware, JIT or a
native emulator initialization. Real local game rows, favourites, play time and
their shared scraped metadata are preserved. Other platforms and consoles are
unchanged. No game, save, firmware, key or external folder is opened or removed
by this cleanup. Existing embedded-only routing still rejects any stale URL;
it cannot hand off to an external app or synchronize the old library again.

Deletion also accepts a retired reference held by a stale screen and removes
only its exact database row. Local games still require successful physical
file removal before acknowledging deletion or removing their metadata. Shared
confirmation UI supports single, multiple and mixed selections, with the
retired-reference warnings translated in all twelve languages. Cancellation
and file-access failures preserve the appropriate remaining entries.

Targeted executable checks cover the recording's three URLs, automatic cleanup,
repeat cleanup and a later stale import, transaction rollback, legacy cache
removal, local game preservation, old emulator defaults, both retired schemes,
same-name files, unknown schemes, multi-delete and cancellation. Existing local
Switch deletion, denial, large-dialog and translation cases are reused as
targeted scenarios; unaffected firmware/migration campaigns are not repeated.

Build 509 uses the exact native engine, host and catalogue inputs of verified
Build 508 (`e44b0d34`, run `39880551632`). This includes the audited RPCS3 Core
and shared NeoSwap compiler broker, current MeloNX ABI2 engine and existing
Switch fixes. No Core or JIT helper source changes or rebuilds are required.
The final Release device app is rebuilt, packaged and checked for the compiled
cleanup/deletion code and exact source receipt. All existing engine, license,
distribution, signature and final-package gates remain.

No main update, public release or tag is authorized. The IPA requires Apple
re-signing with SideStore; no physical-device gameplay or performance claim is
made. The final decrypted IPA has been independently verified. Delivery source
`d4e61fa1388b9b52e4ea51ea0a0a65cee58bab90`, tree
`bec248cc5597c89e8ac19e67de36a8d9d4611566`, completed all three jobs in
[run 39884045828](https://github.com/TarbleFR/RewindBox/actions/runs/39884045828).
The IPA is version 0.0.8 (509), requires iOS 18.0, and has 186,082,461 bytes.
SHA-256: `b934daa250ab29d50f5a5dfe6ae25d54fa5dbd5e92a3700ece18f155db59b7ef`.

Independent checks verified all 83 compiled Mach-O payloads against the signed
package inventory; CI verified 86 ad hoc signatures. All six MeloNX framework
payloads, including the ABI2 engine, match Build 508. The 38 other emulator
Core/MoltenVK payloads also match Build 508. The RPCS3 audited Core fingerprint,
host compiler broker and binder, final motion assets/notices, and the compiled
Switch retirement/deletion source receipt all passed. The targeted CI suites
passed 34 tests (one existing macOS-only case skipped on Linux) and five existing
Switch deletion/translation scenarios. Receipt:
`evidence/melonx-delete509-delivery.json`.
