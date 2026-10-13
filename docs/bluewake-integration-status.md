# BlueWake integration on Claude

2026-10-13. **Started; not available for gameplay.**

## Delivery requested by the maintainer

The October 13 follow-up explicitly extends the task through a personal test
IPA on `Claude`, including native in-game menus and selection of the game's
language, consistent with the other ports. Passing the standalone host build
is only an intermediate gate, not the requested delivery.

The candidate must support import, launch, controls, saves, return to
NeoStation, relaunch, and switching between ports without terminating the
app. Native menus must use the existing twelve-language UI catalog contract.
Game dialogue languages are a separate capability: only languages backed by
compatible game data may be offered. Re-signing for the maintainer's existing
SideStore installation remains part of the personal delivery workflow.

### Confirmed prerequisites and current blockers

- The pinned engine supports **GZLE01 USA, disc 0, revision 0** only. The
  [upstream European-disc request](https://github.com/chrissotraidis/bluewake/issues/60)
  remains open. The maintainer confirms in
  [the language discussion](https://github.com/chrissotraidis/bluewake/issues/92)
  that the USA disc contains English only. Changing the emulated SRAM language
  does not supply missing game text. European support or a validated personal
  language-data import must be implemented and tested before offering other
  dialogue languages; reports of manually replacing an archive are not a
  validated integration.
- The personal module `gGZLE01_recomp.dylib` must be compiled for iPhoneOS ARM64
  from the player's supported disc and included before signing. Importing an
  ISO in the iPhone app cannot create this native module.
- No supported disc or matching personal iOS module has been supplied. A
  scoped search of the connected Windows PC's Downloads, Desktop and Documents
  did not locate one. This is not a claim that it is absent from every device
  or drive; the maintainer needs to identify its location.
- The available connected device is Windows; no local macOS/Xcode build host
  has been identified. The successful macOS CI compiled only source-owned
  engine code. Personal disc data, translated sources and modules must stay
  out of public CI, logs and artifacts. The player's local Apple build host,
  or an already prepared compatible personal module, is needed for the
  game-bearing package.
- Native embedding is still unfinished: the standalone entry owns SDL/UIKit
  and calls `_exit` after the host returns. The callable adapter must implement
  cooperative stop, complete cleanup and session reset. A settings overlay
  alone does not satisfy this gate.

No playable IPA, native NeoStation menu, language switch or iPhone stability
result is claimed by this checkpoint. No new app build number is allocated.
The concurrent Dart cleanup `e4f6c73597a2063e69f56b60b067a4802f71c2b1` is
preserved. This checkpoint changes documentation only; the previously recorded
compilation and preparation results are reused, not rerun or relabeled.

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
- Added a standalone iOS host build command and a macOS CI workflow, limited
  to changes in the new BlueWake sources on Claude. Portable checks run on
  source changes; the longer iOS shell build is requested explicitly.
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

1. **Completed:** the iOS standalone reference build gate, without game code.
   Exact inputs and executable identity are recorded in the source lock.
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
- Follow-up preparation checks on Linux: **17/17 passed**, including output
  preservation and refusal of a symlink into a source repository. Git attributes
  preserve the four vendored source/notice files byte-for-byte on Windows.
- iOS reference compilation: **passed** at source `5535e304b429e461cc1387650ca70c64694150b4`,
  [run 38465426084](https://github.com/TarbleFR/neostation-ios/actions/runs/38465426084).
  macOS ARM64, Xcode **26.3 (17C529)**, CMake **4.4.3**, iPhoneOS ARM64,
  Release, iOS deployment target 17.0. The vendored importer compiled for iPhone;
  the full standalone host linked successfully. The executable is `MH_EXECUTE`,
  SHA-256 `64409bd3419c80fe120613fbef06c46a152d2b93137399cadab3bce56336c497`.
  The build verified the Dawn archive and produced no translated game module.
- Follow-up CI: **17/17 preparation tests passed** at source
  `f7fd3784e482f7d41edc1f6e416b33a03bfeafd3`,
  [run 38465835435](https://github.com/TarbleFR/neostation-ios/actions/runs/38465835435).
  The unchanged upstream engine was not rebuilt: only output-path protection,
  source byte preservation, test scheduling and documentation changed. Native
  source pins and CMake compilation arguments remain identical.
- No supported personal disc was provided; no valid-disc import, native module
  compilation, signing, launch, save or relaunch in NeoStation was tested.
