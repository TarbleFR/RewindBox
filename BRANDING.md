# RewindBox name, logo and official builds

RewindBox is free software. Its code is licensed under the GNU General Public License, version 3 or (at
your option) any later version (see [LICENSE.md](LICENSE.md) and [NOTICE.md](NOTICE.md)). Nothing on this
page restricts the rights the GPL gives you to study, change, build, run and share the code; building and
running any version for yourself is unrestricted. This page covers only how official builds are identified
and the use of the RewindBox name and logo.

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

The CI recipes in this repository build test IPAs only when they run in TarbleFR/RewindBox:

- The standard delivery recipe stops a run in any other repository before restoring or compiling anything,
  unless that run rebuilds a published release exactly: the commit the release tag points to, its frozen
  manifest unchanged except its recipient, and the builder's own recipient key (`build-utils/delivery-<N>-recipient.pem`)
  as the only other change. See [the recipe notes](docs/standard-delivery-recipe.md).
- The older per-build workflows that produce IPAs skip their jobs outside TarbleFR/RewindBox
  (`if: ${{ github.repository == 'TarbleFR/RewindBox' ... }}`).

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

For the material TarbleFR has added to RewindBox, section 7(c) of the GPL applies: modified versions must
be marked in reasonable ways as different from the original. If you distribute a modified build, it must:

1. use its own name and app icon, not the RewindBox name or logo;
2. use its own bundle identifier, so that it cannot replace the official app or its data;
3. say clearly, where users see it (for example in its description and About screen), that it is
   unofficial and not made or supported by the RewindBox project;
4. keep the copyright, licence and attribution notices, including the credits to NeoStation and to the
   third-party projects, and provide its Corresponding Source, as the GPL requires.

## Scope

This page covers only the RewindBox name and logo and the material added by TarbleFR. NeoStation (by Miguel
Soto and contributors), the emulator engines and every other third-party name, logo and piece of code keep
their own owners and licences; nothing here adds conditions to them. Questions:
[issues](https://github.com/TarbleFR/RewindBox/issues).

**Résumé (FR).** Seuls les IPA joints aux releases publiées de TarbleFR/RewindBox sont des builds
officiels ; les IPA de test sont privés, chiffrés pour le mainteneur et jamais publiés, et les recettes du
dépôt ne les compilent que dans TarbleFR/RewindBox (un fork ne peut reconstruire qu'une release publiée).
Le code reste sous GPL v3 ou ultérieure, sans restriction ; le nom et le logo RewindBox ne sont pas
concédés aux builds non officiels, et un build modifié diffusé doit porter un autre nom, une autre icône et
un autre identifiant de bundle, et se déclarer non officiel.
