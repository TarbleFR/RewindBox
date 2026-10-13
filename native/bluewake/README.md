# BlueWake integration — source preparation

Status: **in progress, not playable in NeoStation**. Work branch: `Claude`.

This directory starts the native-port integration with the upstream C disc
preparation component, preserved byte-for-byte at BlueWake
`6248171f3ef6094d179d45385b522d6bc8f49248`. Chris Sotraidis, Elliott Tate and
the BlueWake contributors retain their authorship. The full GPLv3 license and
the upstream rights notice are in `upstream/`. No Nintendo game content is included.

The canonical [source lock](../../build-utils/bluewake/source.json) records
upstream Git blobs, SHA-256 hashes, the runtime/translator/SDL/Dawn pins and
the game compatibility contract. The rest of BlueWake is fetched into an
independent checkout for a reference build; it is not silently copied into
NeoStation's existing Dolphin, Dusklight or KartPad trees.

## Reproduce the first build gate

From the NeoStation root, with Python 3.9+ and Git:

```sh
python3 test/bluewake_preparation_test.py
python3 build-utils/bluewake/prepare.py verify-vendored
python3 build-utils/bluewake/prepare.py prepare-source /tmp/bluewake-source
```

On a Mac with Xcode, the iPhoneOS SDK, CMake 3.25+ and Ninja:

```sh
python3 build-utils/bluewake/prepare.py check-tools
python3 build-utils/bluewake/prepare.py build-shell \
  --source /tmp/bluewake-source --output /tmp/bluewake-reference --jobs 3
```

Use a new output path for each attempt. Existing source checkouts are checked
for the exact revision and local edits; they are never reset or cleaned. The
builder verifies Dawn's archive digest and passes SDL's full commit to CMake.
It builds the standalone upstream `BlueWake.app`, with no disc, game module,
signing credentials, IPA distribution or automatic installation. A successful
build writes `build-receipt.json` next to the app and explicitly records that
neither a NeoStation core nor gameplay has been tested. The GitHub workflow
**BlueWake source preparation** runs on changes to these BlueWake sources on
`Claude`, or by manual dispatch once GitHub registers it. It runs the same gate
without uploading the application or other build artifacts.

For a personal disc kept on the build machine:

```sh
python3 build-utils/bluewake/prepare.py probe-disc /path/to/personal-disc.iso
```

This read-only check accepts ISO/GCM, GZLE01 USA disc 0 revision 0, bounded
DOL/file-table spans and the pinned executable SHA-1. It does not extract,
copy or upload the disc and does not claim full-disc integrity. The complete
415-module set and translated source digest still require the personal builder.
The production command does not accept the upstream mod hash override.

## Not connected to the app yet

The upstream `disc_import.c` is a reference component, not an enabled Files
importer. Its replacement, cancellation, module-set validation and path safety
still need the changes listed in the [integration audit](../../docs/bluewake-integration-audit.md).
Do not call `bluewake_disc_prepare` on an existing installation or on arbitrary
user-selected input from NeoStation yet.

The reference host is an `MH_EXECUTE` standalone application, not a framework.
It owns SDL/UIKit and can terminate the process. Before enabling Ports, provide
a callable host without that entry point, private symbols and Objective-C
classes, restartable shutdown, a signed personal game module, persistent save
paths, then the importer/library/session bridge and twelve-language UI.
An imported ISO cannot supply the missing native module.
