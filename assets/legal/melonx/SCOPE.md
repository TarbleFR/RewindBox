# MeloNX license reference scope

These files preserve notices from the exact source revisions recorded in
`build-utils/melonx/source.json`. They are reference material for ongoing
integration. The current NeoStation Legal packaging step must not copy this
folder into an IPA as evidence that a MeloNX runtime is already included or
approved. No runtime or native dependency is staged by this notice collection.

## Conflicting upstream declarations

At MeloNX revision `13700519f3abc4e6d7ed8a065b118b2cc59bcd67`, the root
`LICENSE.txt` contains the MIT License and credits the Ryujinx Team and
Contributors. The same revision's README calls the software GPLv3 at lines
13 and 218, linking to that MIT file. The exact root license is retained;
this discrepancy remains unresolved. No unambiguous license classification,
permission to relicense, or distribution clearance is inferred here.

`distribution/legal/THIRDPARTY.md` is copied as upstream published it.
It lists component-specific terms including FFmpeg LGPLv3 and libvpx BSD.
Its presence does not identify the exact source and build configuration of
the prebuilt native libraries supplied by MeloNX. Those frameworks require
a separate version, source, build and license inventory before distribution.
The retained SDL3 header is a notice accompanying one staged framework; it
is not proof of source correspondence for that framework.

## Other pinned sources

LibHac's complete license file includes the upstream MIT notice, the hactool
ISC notice and the XTSSharp BSD notice. Melo-Controller and Spv.Generator
keep their complete original license files. None of the copyright wording
or permissions in these copies has been rewritten or attributed to NeoStation.

The manifest records source URLs, exact revisions, Git blob identifiers and
SHA-256 digests. This source-notice collection does not satisfy all future
corresponding-source or binary distribution obligations. See the current
native dependency evidence and release preparation review before enabling
runtime packaging.
