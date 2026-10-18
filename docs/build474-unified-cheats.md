# Build 474 — unified cheat catalogue private IPA

The maintainer authorizes the next IPA after reviewing the complete source
inventory. Candidate builds on the delivered 473 and the final catalogue
integration `2c328dfb6267245220da6162790b52542b9e2e0b` on `Claude`.

The catalogue contains 34 source/provenance attributions on 22 systems,
2,341,355 programs/variants, 43,813 identity groups, 44,955 transport parts and
851 downloadable packs. Initial network transfer is about 281 MB; the IPA
embeds the 6,574,067-byte compressed index, not the full downloadable packs.
Sources, edition limits and adaptations remain in `unified-cheats-sources.md`
and `unified-cheats-integration.md`.

The delivery composition gate requires the exact successful 473 baseline,
the final data CI and full Apple index preflight, plus successful native,
SDK, Foundation, RAM and UIKit component evidence. The earlier failed overall
jobs remain failed: only their documented successful components are reused.
All source packages equal their tested snapshots, with the separately tested
RPCS3 first-import correction and final manifest handled explicitly. No
successful unchanged suite is rerun. Xcode 26.3 / iPhone SDK 26.2 is required.

The delivery reuses the exact 34-core bundle with corrected Nestopia and all
other delivered emulator payloads. No core rebuild is authorized or needed.
The host and its new shared pod are compiled and linked as a device Release.
The actual IPA must contain the exact final resource index and the shared
catalogue/browser linked into all four consumers. All normal version,
signing, source and native payload checks remain required.

Build 474 is reserved for this delivery. The new public RSA recipient is
`build-utils/delivery-474-recipient.pem`; its private key stays outside Git.
No public release or installation on a physical phone is claimed. The final
IPA and CI identities will be recorded after compilation and verification.

## Preparation failure retained

Run `39096704203`, source `22cfddc6cad9d84e3db0ea47806fd3d8d3248973`,
stopped in evidence collection before any IPA compilation. The installed
GitHub CLI rejected historical ANSI-bearing logs without its explicit
`--allow-escape-sequences` flag. The reader now captures those log bytes
privately with that flag. No product, core or prior test assertion changed.
