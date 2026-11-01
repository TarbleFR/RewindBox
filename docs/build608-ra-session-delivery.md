# Build608 — central RetroAchievements session delivery

This is an authorized delivery recipe, not a successful build receipt. The
integration branch is `Claude`. No device login, award, translation-model
download or gameplay success follows from a successful simulator or IPA build.

## Product and producer selection

The product baseline is the delivered Build607 source
`68552e27770b114ecc9a347600816132794b4fae`, run `41246903346`, application job
`124672229557`. Its previously verified private IPA was 189741645 bytes,
SHA-256 `817a196dd6452c1b6fc876b07f2337d09ade5a148751888c136d0e12dd90d2d4`.
The workflow authenticates that successful run/job and the reviewed source
delta. It does not claim to download the previous encrypted private IPA.

The full application is rebuilt. The resource donor527 is retained only for
its previously authenticated native resource subset; it is not the product
baseline. Every bootstrap Core is replaced before application compilation.

RPCS3 remains the recovered607 `a4ae86d0…` Core, ABI30. Its original producer
`41243687649` failed after linking; `rpcs3runtime607_core.py` retains that failure,
the original diagnostic archive, offline recovery evidence and exact input
bindings. No replacement Core or fabricated successful producer is allowed.
MeloNX remains the exact606/607 engine authenticated by `rewind606_engine.py`,
including its original finalization failure and separate successful validation.

Dolphin is rebuilt from upstream `7cac54161659421ed95c2cd1c0b0746539a4cd38`
with both additive session exports and the original exported ABI. ARMSX2 is
rebuilt from its unchanged pinned iOSv2.6.0 revision with host/Core ABI9. The
original shader resources and its one exported API entry point remain checked.

## One workflow

Push the final reviewed commit on `Claude` with `[rewind608-delivery]` in its
message. The workflow also permits an explicit dispatch on `Claude`.

1. Ubuntu authenticates the reviewed607 baseline and retained native origins.
2. Flutter3.47.2 tests and macOS Xcode16.4 native tests run as prerequisites.
   The latter compile the actual Translation plugin with Swift6, run its
   XCTest, the central session XCTest using real Flutter, the changed Dolphin
   and ARMSX2 menu XCTest, libretro policy behavior and affected host compilation.
3. Dolphin and ARMSX2 build concurrently after both test jobs succeed.
4. A full Flutter3.47.2/Xcode26.3 Release application build consumes their
   artifact IDs and SHA-256 digests through `needs` outputs.

Producer jobs, exact source SHA, run attempt, complete archive digests, member
inventories and compiled source inputs are checked before use. The application
job never waits on another producer workflow while occupying a macOS runner.
Compilation times are recorded, not predicted as measured performance. Two
fresh native cores can exceed the usual delivery-time target on cold runners.

## Freeze after integration

The integrator must run the following after all product, test and recipe files
are final, before the delivery commit:

```sh
python3 -B .github/diagnostics/rewind608_baseline.py freeze
```

Review and commit the resulting `build-utils/rewind608-source-scope.json` and
`docs/evidence/retro-achievements-session-declarations-2026-11-01.json` with the
code they describe. The freeze command is deliberately refused in CI. Later
changes to any scoped source byte or executable mode require review and a new
freeze. Missing scope evidence is a hard failure, not an automatic regeneration.

The new declaration review preserves the old license/source audit and605
translation follow-up verbatim. It covers exactly six changed declarations:
the root pubspec, three native consumers and the central plugin's pubspec and
podspec. The hosted package lock must remain unchanged. Existing unresolved
source/license findings are not relabeled as resolved by this review.

`build-utils/delivery-608-recipient.pem` contains only the new recipient public
key. The private key stays with the integrator and must not be committed.

## Native inventory and signed export

The complete named89-image inventory is preserved; the only addition is
`Frameworks/retro_achievements_session.framework/retro_achievements_session`.
The resulting exact90-image set is checked before signing, after signing and
inside the final ZIP, including single-arm64 fat containers. Every image must
have an actual successful macOS signature verification. Code/data sections,
exports, dependencies, run paths, OS floor and install names must be preserved
by signing. Dropping a baseline image and adding a replacement cannot satisfy
the named inventory even if the total count still equals90.

The actual central C exports and its dependency from all three engine bridges
are inspected in the signed IPA. Both rebuilt cores are compared with their
authenticated producer payloads; exact RPCS3/MeloNX preservation, existing
NeoPlay/shader isolation, source/legal notices, eight bundle versions and the
single application structure retain their own validators.

## Transfer and runtime requirements

The runner needs read access to the retained private Actions artifacts, the
original recovered RPCS3 diagnostics, pinned libretro cores and MeloNX native
dependencies. Expired, missing or mismatched artifacts fail the recipe; an
older engine must not be substituted. Pinned upstream source/submodule fetches,
Flutter/CocoaPods dependencies and Xcode16.4/26.3 availability remain external
build requirements. Existing ScreenScraper build secrets are required as in607.

Read-only GitHub verification on 1 November2026 found the retained libretro
archive `12280822192` available until 3 November16:19UTC and the MeloNX native
dependency archive `12458409441` until 5 November21:09UTC. The original RPCS3
diagnostic archive `13059157171` expires on 14 November21:47UTC. Preflight
authenticates these immutable IDs/digests before either new Core build. Runtime
downloads verify the exact archive size and SHA-256 again before extraction.

Delivery and diagnostic archives are encrypted for608. Four bounded transport
pieces preserve the existing download path. The recipient must download,
decrypt and verify the actual delivered IPA and its embedded receipts before
offering it to the user. Ad hoc preparation does not replace SideStore's Apple
provisioning and signing.

Physical-device checks still include Apple language-model consent/download,
real supported-language availability, authentication/account changes, first
launch/relaunch and genuine game recognition, Hardcore restrictions, unlock
awards and notifications for each engine. Simulator fixtures cannot establish
those outcomes or official RetroAchievements approval of the embedded forks.
