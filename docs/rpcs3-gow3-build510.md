# Build 510 — God of War III log follow-up

The maintainer explicitly approved pushing the reviewed corrections to Claude
and preparing a private test IPA. No release, tag or main change is authorized.

Core source: `50714fe0980d0b50ccd93c1c739c480b054a31b9`, dedicated run
`39888215155`. The canonical patch is
`f31bf5f7d66c44dd3a02683a12a3b3ad6ac450d83bd66603e8c2010f7579198d`.
The ISO metadata/real archive path, iOS VMA preferred granularity and effective
game CPU diagnostics are the only production Core changes. ABI 30 and both
PPU/SPU codegen input lists are retained. No device/FPS gain is claimed.

The compilation authenticates the successful Build 508 proof archive and its
exact unchanged input closure, executes the changed boot/CPU/VMA regressions,
then compiles and checks the actual new iPhone Core. The new source-bound reuse
receipt prevents a changed unrelated native input from bypassing its tests.

The IPA keeps all app, native host, catalogue, MeloNX and other-engine product
inputs identical to the delivered Build 509 (`d4e61fa1`, run `39884045828`).
Only RPCS3 is rebuilt. The assembly checks the new Core artifact identity and
compiled payload after signing, the game CPU diagnostic, the existing compiler
broker and all previous distribution/other-engine/Switch deletion gates.
Unchanged Flutter and unrelated native campaigns are reused by source identity.

Build 510 is a new immutable candidate; builds 508 and 509 remain historical.
The final run, hashes, signed payload checks and downloadable IPA must be
recorded after completion. A successful host fixture or Core compilation is
not proof of playable God of War III on an iPhone.
