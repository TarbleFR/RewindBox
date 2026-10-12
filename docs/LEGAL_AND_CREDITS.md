# NeoStation iOS — Legal, Licenses and Credits

This document is the central attribution and redistribution record for the
NeoStation iOS fork. It supplements `LICENSE.md`, `NOTICE.md`, per-file SPDX
headers and the license files shipped by each upstream project.

Attribution does **not** imply endorsement by any upstream project, creator,
console manufacturer or trademark holder.

## Current release and license review

The current published GitHub release is
[NeoStation iOS 0.0.6 / Build 447](https://github.com/TarbleFR/neostation-ios/releases/tag/0.0.6).
See the [Build 447 distribution and license review](RELEASE_0.0.6_LICENSE_REVIEW.md)
for the checked IPA contents, exact release identity, known packaging gaps and
license-compatibility questions. Credits and license-text presence do not alone
certify full compliance or provide exact Corresponding Source for every bundled
binary.

**NeoSwap** is NeoStation's experimental memory-management integration for
the embedded RPCS3 workflow. Its guest-memory relay adapts a MIT-licensed
Guest Page Relay prototype (see [the preserved notice](../assets/legal/Guest-Page-Relay-MIT.txt)). Its relay, donor, file-backed and cold-data
mechanisms are described in the [README](../README.md#neoswap--experimental-memory-management-for-rpcs3).
That description is not a claim to relicense RPCS3, borrowed libraries,
platform APIs or other contributors' code. NeoSwap does not create additional
physical memory or circumvent Apple's resource enforcement.

## NeoStation and the iOS fork

- **NeoStation** — original frontend/project by Miguel Soto / @misobadev, with
  @androosio, @ItsRetroPup and all upstream contributors.
  Source: https://github.com/misobadev/neostation-frontend
- **NeoStation iOS** — iOS/iPadOS fork, native integrations and maintenance by
  @TarbleFR.
  Source: https://github.com/TarbleFR/neostation-ios
- NeoStation's upstream notice is GPL-3.0-or-later. NeoStation iOS preserves
  that attribution and does not claim authorship of upstream work.

## Embedded runtimes and native components

| Component | Authors / upstream | License / redistribution note |
| --- | --- | --- |
| **Embedded RetroArch / Libretro cores** | RetroArch and Libretro contributors, plus the individual emulator authors listed in the README and core notices | The 14 bundled cores run inside NeoStation's native host. Each core and dependency retains its own license; the project-level GPL notice does not replace those terms. |
| **Dolphin / DolphiniOS** | Dolphin Emulator contributors; OatmealDome and DolphiniOS contributors | Most original Dolphin code is GPL-2.0-or-later. The exact fork states the aggregate repository is GPLv3-compatible; per-file SPDX and `LICENSES/` remain authoritative. |
| **RPCS3 / XITRIX iOS fork** | RPCS3 contributors; XITRIX; upstream work credited by XITRIX including ARMSX3 and the iOS JIT community | The pinned XITRIX/rpcs3 source contains the RPCS3 GPL-2.0-only `LICENSE`. No relicensing by NeoStation is claimed. Preserve file-specific notices and third-party licenses. |
| **ARMSX2 / PCSX2** | ARMSX2 team and contributors; PCSX2 contributors | ARMSX2 distributes GPLv3 material and derives from PCSX2. Preserve the exact upstream notices and per-component licenses. |
| **librashader** | Ronny Chan / SnowflakePowered and contributors | Native Metal shader chains used by ARMSX2 2.6. The pinned 0.12.0 C API declares MPL-2.0 OR GPL-3.0-only; preserve upstream notices. |
| **Dusklight** | TwilitRealm/Dusklight contributors; Twilight Princess decompilation community; Aurora and Borealis contributors | Dusklight's root work is CC0-1.0; embedded dependencies retain their own licenses. |
| **KartPad / WiiCompiled** | KartPad by @chrissotraidis; WiiCompiled by @patchzyy | KartPad-owned software and its WiiCompiled modifications are GPL-3.0-only where stated by KartPad. WiiCompiled and dependency notices remain applicable. Game-derived translated logic has separate rights considerations and is not relicensed by the software licenses. |
| **StikJIT** | StikDebug / StikJIT contributors | MPL-2.0. Recipients of executable form must be informed how to obtain the covered source. |
| **Dawn, SDL, Aurora, Borealis and other runtime dependencies** | Their respective projects and contributors | Their individual license files and notices apply. |

### Exact source identities used by the stable 0.0.1 binary

See [RELEASE_0.0.1_SOURCE_MANIFEST.md](RELEASE_0.0.1_SOURCE_MANIFEST.md). That
file records the exact NeoStation packaging commit, workflow artifact identity
and pinned upstream revisions used for the published Build 350 IPA.

## External integrations

The following applications/services are **not claimed as NeoStation-owned
software** merely because NeoStation interoperates with them:

- **MeloNX** — https://github.com/nurtrino/MeloNX
- **ScreenScraper** — https://www.screenscraper.fr/
- **RetroAchievements** — https://retroachievements.org/
- **LocalDevVPN** — separately installed and user-controlled application
  required by the current embedded Dolphin, ARMSX2 and RPCS3 JIT workflows.
  NeoStation does not bundle or activate it.

Their own terms, licenses, privacy policies and service rules apply.

## Remote System Art and creative assets

### NeoStation Assets

NeoStation can fetch optional System Art from:

https://github.com/misobadev/neostation-assets

That repository states that its original artistic works, backgrounds and custom
icons are licensed under **CC BY-NC-SA 4.0**. Attribution to the NeoStation
project is required, commercial use of those original assets is restricted by
that license, and trademarked console logos remain owned by their respective
holders.

These assets are fetched/cached at runtime rather than being treated as
NeoStation iOS-owned artwork.

### RiiSU / iiSU

NeoStation also exposes the **RiiSU** System Art pack as a curated external
on-demand source:

- RiiSU — https://github.com/mult1v4c/RiiSU
- RiiSU repository owner / maintainer — https://github.com/mult1v4c
- iiSU Interpreted for ES-DE — https://github.com/VictorUnlocked/iisu-interpreted-es-de
- iiSU Network — https://iisu.network/

RiiSU's README credits iiSU Interpreted for the system art icons and iiSU
Network for the original inspiration. Its example metadata identifies the author
as **iiSU Network**.

No standalone license file was visible in the RiiSU repository when this
integration was added. NeoStation therefore keeps the RiiSU artwork hosted by
the original project and downloads/cache it only when the user chooses that
pack. Attribution does not invent redistribution rights that upstream has not
published.

## Metadata and datasets

### GameDB / GameDB-PS3

NeoStation thanks **Niema / @niemasd** for GameDB and GameDB-PS3:

- https://github.com/niemasd/GameDB
- https://github.com/niemasd/GameDB-PS3

GameDB-PS3 also identifies **MiSTer Addons** and **Redump** as source datasets.
NeoStation does not claim authorship of those datasets.

## KartPad / translated game-logic boundary

KartPad's own rights document explicitly separates the GPL-covered software
from rights in Nintendo-owned game content and from questions concerning
ahead-of-time translated game logic.

NeoStation therefore does not state or imply that:

- the GPL grants rights in Mario Kart Wii;
- Nintendo-owned code, data, characters, names, audio, textures or other
  commercial assets have been relicensed;
- possession of a NeoStation binary replaces the user's obligation to supply
  legally obtained supported game data where required.

The public NeoStation source manifest also records KartPad's upstream source
limitation concerning generated translation/profile inputs. A release must not
be described as providing complete KartPad Corresponding Source unless the
complete source required for that exact binary is actually available.

## RPCS3 licensing boundary

The exact pinned XITRIX/rpcs3 source used by NeoStation carries RPCS3's
GPL-2.0-only license for most files. NeoStation's host licensing does not change
that license. The RPCS3 core, NeoStation integration changes, file-specific
SPDX notices and third-party components must each retain their applicable
terms.

Because GPL combined-work questions can depend on the technical and legal
relationship between components, this project does not use attribution text to
claim that an otherwise incompatible license has been converted or waived.
Redistributors should review the exact architecture and licenses for the binary
they convey.

## Source availability and rebuild information

For GPL- and MPL-covered components, attribution alone is not a substitute for
source-code obligations.

NeoStation release documentation therefore identifies:

1. the exact NeoStation source commit used for the binary;
2. the exact upstream revisions used by embedded runtimes;
3. NeoStation's integration patches and build scripts;
4. the license and notice documents associated with those components.

See [RELEASE_0.0.1_SOURCE_MANIFEST.md](RELEASE_0.0.1_SOURCE_MANIFEST.md) for the
first public GitHub release.

## Trademarks and commercial game content

Nintendo, PlayStation, Sony, Microsoft, Xbox, SEGA, Dolphin, RPCS3, PCSX2,
ARMSX2, RetroArch, MeloNX, KartPad, StikJIT and all other referenced product
names, logos and trademarks remain the property of their respective owners.

NeoStation iOS is an independent project and is not affiliated with, sponsored
by or endorsed by those rights holders unless explicitly stated.

NeoStation does not bundle commercial games, proprietary console BIOS or
firmware, encryption keys, or paid book/manga content. Users must provide
the legally obtained content required by their games and readers.

## Binary packaging policy and verified limitations

NeoStation iOS builds should include a `Legal/` directory inside the
application bundle containing:

- the NeoStation GPL text and project notice;
- this attribution record;
- the exact release source manifest;
- Dolphin's COPYING notice;
- the exact RPCS3 GPL-2.0 license text;
- KartPad's rights and third-party notices;
- StikJIT's MPL-2.0 text;
- Dusklight's CC0-1.0 text;
- additional dependency notices collected by embedded projects.

The already-published `NeoStation.ipa` asset for release 0.0.1, and the
0.0.6 IPA, are intentionally not modified by this documentation update.
The 0.0.6 IPA includes the main `Legal/` notice collection but does not
currently package all 14 individual Libretro core license texts in the
documented `Legal/Libretro/` location. This is recorded as a follow-up item
rather than described as resolved.

## Optional cheat catalogue source

The RE4 PAL G4BP08 catalogue adapter fetches the author's public WIIRD topic
on demand from gc-forever. Credits: **Ralf / Ralf@gc-forever** and any authors
named beside each code. Source: https://www.gc-forever.com/forums/viewtopic.php?t=2145

The catalogue is not bundled in NeoStation. Imported entries retain the author
and source URL; attribution is not an endorsement or a claim to relicense the
creator's work. The source does not specify a disc revision.

## Embedded Libretro cores — current release 0.0.6 / Build 447

Introduced in release 0.0.3, NeoStation's Embedded RetroArch integration uses
14 bundled Libretro cores: Nestopia, Snes9x, Gambatte, mGBA,
Genesis Plus GX, Genesis Plus GX Wide, PicoDrive, FinalBurn Neo, DeSmuME,
Mupen64Plus-Next, Beetle PSX, Beetle PSX HW, PPSSPP and Azahar.

Full core credits, original license texts, support-library notices, reference
revisions and distribution restrictions are in `assets/legal/libretro/`.
The inspected 0.0.6 IPA contains a subset in `Libretro-Licenses/`, but the
complete core license collection was not present in `Legal/Libretro/`.
See the [Build 447 review](RELEASE_0.0.6_LICENSE_REVIEW.md) before redistributing.
See the [core license record](https://github.com/TarbleFR/neostation-ios/blob/main/assets/legal/libretro/LIBRETRO_CORES.md)
and [0.0.3 provenance](https://github.com/TarbleFR/neostation-ios/blob/main/docs/RELEASE_0.0.3_SOURCE_MANIFEST.md).

Snes9x, Genesis Plus GX/Wide, PicoDrive and FinalBurn Neo have non-commercial
conditions; FBNeo additionally restricts monetary profit and donation solicitation.
The exact source revisions for the prebuilt core binaries were not attested
by their buildbot delivery. License-document snapshots are not a substitute
for complete Corresponding Source and do not establish full license compliance.

The current engine runs these cores inside NeoStation without a separate
RetroArch installation. Older external-app game settings and compatible
exported-library routes can still be retained; they are historical
compatibility paths, not the identity of the embedded engine. The external
RetroArch app has not been offered as a new per-game choice since Build 440.
