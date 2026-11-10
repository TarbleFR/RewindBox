# Standalone MoltenVK source preparation

The recorded producer invocation fetched the exact MoltenVK 1.4.2 commit from a
local Git object mirror into a fresh owned directory, applied the reviewed
source adapter and checked its five postimages and the remaining tracked delta.
The mirror's working-tree edits are not copied. The receipt and eight command
logs describe a **source preparation on Linux**, with no external dependency
build, Apple compilation, RPCS3 Core, IPA or device test.

The producer's ten portable checks pass. They exercise thin-ar/Mach-O archive
validation, including all members, arm64, iOS versus simulator/macOS and minimum
OS, malformed input rejection, dependency SHA checks, unrelated source drift,
preservation of existing directories and the static Release build route. The
Mach-O test objects are synthetic fixtures, not compiled Apple objects.

The complete Apple build route uses the upstream `MoltenVK-iOS-static` target,
then creates a static XCFramework. The packaging aggregate would also link a
dynamic framework, which cannot retain the intentionally unresolved RPCS3
queue hooks. No stubs or dynamic symbol-lookup workaround are introduced.

To build the candidate on macOS/Xcode after review, run the same producer with
new dedicated paths and omit `--prepare-only`. Its archive/platform, dependency,
queue-hook, source, header and license checks run before successful completion.
The delivered Core recipe still selects its historical pinned prebuilt
dependency; this candidate does not silently replace it. A new Core consumer
contract and actual Apple/device validation remain necessary.
