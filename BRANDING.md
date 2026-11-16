# RewindBox name, logo and official builds

RewindBox's own code is licensed under the GNU General Public License, version 3 or (at your option) any
later version, where the original licensing permits; the other components keep their own licences (see
[LICENSE.md](LICENSE.md) and [NOTICE.md](NOTICE.md)). Apart from the section 7 terms below, which apply only
to TarbleFR's own GPLv3-or-later material, nothing on this page restricts the rights the GPL gives you to
study, change, build, run and share the code; building and running any version for yourself is
unrestricted. This page covers how official builds are identified and the use of the RewindBox name and
logo.

## Official builds

- Official RewindBox builds are only the IPA files attached to a published release of
  [TarbleFR/RewindBox](https://github.com/TarbleFR/RewindBox/releases), identified by the SHA-256
  checksums published with that release. The SideStore/AltStore source linked from the README lists
  only those files.
- The maintainer's test IPAs are private: they are built for the maintainer's own testing, encrypted
  for the maintainer and never published. A RewindBox "test", "beta" or "nightly" IPA found anywhere
  else is not an official build.
- Every other build is unofficial, including a build compiled by anyone else from a branch, a commit or a
  release tag, with or without the project's build recipe.
- You may share an official release IPA unchanged, under its own name, as long as you comply with the GPL,
  including access to its Corresponding Source.

## The project's build recipes

By default, the CI recipes in this repository do not build test IPAs outside TarbleFR/RewindBox:

- The standard delivery recipe stops a run in any other repository before restoring or compiling anything.
  It accepts only the exact rebuild of a published release whose tag points to its `[ipa-delivery:N]`
  trigger commit: the frozen manifest unchanged except its recipient, and the builder's own recipient key
  (`build-utils/delivery-<N>-recipient.pem`) as the only other change, checked against the official
  repository's API (if the API cannot be read, the run is refused). The recipe also authenticates its own
  run through this repository's API, so rebuilding a release elsewhere means adapting those calls, which
  the GPL allows. The releases published before 16 November 2026 predate this gate.
- The older per-build workflows that produce IPAs skip their jobs outside TarbleFR/RewindBox, except the
  legacy routes kept byte-identical for the reasons listed in `EXEMPT` of
  `.github/ipa-protection/check_official_guard.py`.

These are defaults of the project's own scripts, not licence conditions: the GPL lets you change them, and
they are not technical protection measures (GPLv3 section 3). Release sources stay public: each release
tag and its recipe remain in this repository.

## The RewindBox name and logo

- TarbleFR uses the name "RewindBox" and the RewindBox logo (the app icon `assets/images/rewindbox-logo.png`
  and the emblems derived from it) to identify the project and its official builds. This page does not
  claim that they are registered trademarks.
- As section 7(e) of the GPL allows, no right to use the name or the logo under trademark law is granted.
  They are not licensed for unofficial builds: do not distribute an unofficial build under the RewindBox
  name or with the RewindBox logo, and do not present it as official.
- You may refer to RewindBox truthfully, for example "based on RewindBox" or "a fork of RewindBox", as
  long as it is clear that your build is not official.

## Modified builds

For the material TarbleFR has added to RewindBox under GPLv3-or-later, section 7(c) of the GPL applies:
modified versions must be marked in reasonable ways as different from the original. If you distribute a
modified build, it must:

1. use its own name and app icon, not the RewindBox name or logo;
2. say clearly, where users see it (for example in its description and About screen), that it is
   unofficial and not made or supported by the RewindBox project;
3. keep the copyright, licence and attribution notices, including the credits to NeoStation and to the
   third-party projects, and provide its Corresponding Source, as the GPL requires.

We also ask, as a request and not a licence term, that a modified build use its own bundle identifier so
that users do not confuse it with the official app. The official app keeps the identifier it inherited
from NeoStation (`com.neogamelab.neostation`), which this page does not claim.

## Scope

This page covers only the RewindBox name and logo and TarbleFR's own GPLv3-or-later material. It adds no
term to NeoStation's code (Miguel Soto and contributors), to the emulator engines or to any other
third-party name, logo or code. In particular, TarbleFR's modifications of the GPL-2.0-only RPCS3 (the
`build-utils/rpcs3*` deltas) carry only the GPLv2 and its change notices, with no additional term.
NOTICE.md does not point to this page yet: it will once a delivery freeze allows that file to change.
Questions: [issues](https://github.com/TarbleFR/RewindBox/issues).

**Résumé (FR).** Seuls les IPA joints aux releases publiées de TarbleFR/RewindBox sont des builds
officiels ; les IPA de test sont privés, chiffrés pour le mainteneur et jamais publiés. Par défaut, les
recettes du dépôt ne compilent pas d'IPA de test hors de TarbleFR/RewindBox : la recette standard
n'accepte que la reconstruction exacte d'une release publiée, et les anciens workflows IPA (sauf les
routes héritées exemptées) sautent leurs jobs ; ce sont des réglages par défaut des scripts, pas une
condition de licence, et la GPL permet de les modifier. Le code propre à RewindBox reste sous GPL v3 ou
ultérieure ; le nom et le logo RewindBox ne sont pas concédés aux builds non officiels, et un build
modifié diffusé doit porter un autre nom et une autre icône, et se déclarer non officiel (règle limitée au
code de TarbleFR sous GPLv3 ou ultérieure, jamais aux modifications de RPCS3 en GPLv2).
