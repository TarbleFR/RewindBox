# BlueWake integration on Claude

2026-10-13. **Started; not available for gameplay.**

The maintainer's latest instruction moves this work to `Claude`. The starting
revision is `43aa985ad01fc6cae00afe35d008e35124ee52b0`, including the latest
legal-bundle and release-documentation corrections. The concurrent follow-up
`e48de7701a482bfecfb7c95396937d30abb4d4d0` (Windows notice hashes) is also
preserved as the commit parent. `Cloud` is left intact.

## Implemented in this phase

- Imported the audited upstream C disc-preparation source and header, GPLv3
  license and rights notice, with original Git blob and SHA-256 verification.
- Added a single machine-readable source/dependency lock and isolated source
  preparation. An existing dirty or differently pinned checkout is refused
  without changing its files or branch.
- Added a read-only personal-disc preflight: ISO/GCM content, game ID, disc
  number, revision, bounded file spans and the expected DOL hash. This does not
  certify every disc byte or produce a native game module.
- Added a standalone iOS host build command and a manual macOS CI workflow.
  SDL is passed by commit, Dawn by archive hash, and no game content is supplied
  or uploaded. A build receipt distinguishes the standalone executable from a
  future NeoStation framework.

The source integration is deliberately outside the app's current build graph.
Existing emulators, the Ports launcher, library database, game data and saves
are unchanged. There are no new user-facing strings in this phase.

## Validation

The portable preparation tests cover source identities, structural rejection,
revision enforcement, the absence of the upstream hash-override bypass,
read-only behavior, dirty-checkout preservation, unsafe SDK archive rejection,
and clear rejection of an iOS build on a non-Mac host. Synthetic positive data
tests the checker only; it is not a successful import of Wind Waker.

See the dated execution result below and the linked CI run when available.
The earlier audit's nine upstream negative tests remain historical evidence;
they are not claimed as new executions in this phase.

## Remaining work

1. Finish the iOS standalone reference build gate and record its exact inputs.
2. Adapt the host to a callable private framework: UIKit/SDL ownership, audio,
   renderer shutdown, global-state reset and repeated sessions.
3. Build the player's game module locally from the supported personal disc;
   assemble and sign a personal NeoStation package. Never publish that module.
4. Add transactional cancellable import, a distinct Ports launch identity,
   metadata enrichment and localized UI after the engine gate is satisfied.
5. Validate import, launch, controls, save, close, relaunch and engine alternation
   on iPhone. None of these gameplay checks has been performed.

## Execution record — first source candidate

- Linux x86_64, Python 3.12: `python3 test/bluewake_preparation_test.py` —
  **16/16 passed**. `verify-vendored` also passed; all four upstream files match
  their original Git blob hashes.
- iOS reference compilation: to be recorded after the manual CI run.
- No supported personal disc was provided; no valid-disc import, native module
  compilation, signing, launch, save or relaunch in NeoStation was tested.
