# Rights and licenses

## BlueWake's code

BlueWake is licensed under the GNU General Public License, version 3 or (at your option) any later
version. The full text is in [LICENSE](LICENSE).

GPLv3 is the license the parts BlueWake is built from allow together:

- the compatibility runtime, [RecompCore](https://github.com/chrissotraidis/RecompCore), is derived from
  [Dolphin](https://dolphin-emu.org/) (GPLv2 or later), and RecompCore's `COPYING` states that the fork
  as a whole is compatible with GPLv3
- the touch control overlay is adapted from SunPad (GPL-3.0)
- the translator, [DolRecomp](https://github.com/chrissotraidis/DolRecomp), and the Aurora renderer
  vendored in RecompCore keep their own licenses, recorded in those repositories

Rendering interpolation, desktop camera controls, jump and sprint, quicker transitions, runtime
game options and associated optimizations were contributed through
[elliotttate's Wind-Waker-Recomp source fork](https://github.com/elliotttate/Wind-Waker-Recomp).
Imported commits retain their original authorship. Its RecompCore and DolRecomp changes build on
BlueWake's pinned forks; the exact revisions are recorded in the dependency lock.

The recovered J3D rotation/translation formulas in `cmake/composite/native_j3d.c`
were adapted by Elliott from zeldaret/tww's
[J3DTransform.cpp](https://github.com/zeldaret/tww/blob/09de0609ecdb6d30dd012e2258f755afdac1cb56/src/JSystem/J3DGraphBase/J3DTransform.cpp).
That fixed revision carries [CC0-1.0](https://github.com/zeldaret/tww/blob/09de0609ecdb6d30dd012e2258f755afdac1cb56/LICENSE).
The import retains its attribution. Certification scripts record hashes and
modify only a player's locally generated source; translated bodies stay private.

BlueWake's source is published here. Mac, iPhone and iPad apps are built by each player from their own
disc ([docs/BUILD_YOUR_OWN.md](docs/BUILD_YOUR_OWN.md)). One exception: the maintainers publish a
ready-made Windows build on the Releases page, as Wind Waker Recomp did. It contains code translated
from the game but no disc image, game assets, saves or console keys, and it needs the player's own
disc. It will be taken down if the rights holder asks.

## Game content

BlueWake is an independent, unofficial project, not affiliated with or endorsed by Nintendo. *The
Legend of Zelda: The Wind Waker*, its code, data, characters, names and imagery, and the GameCube
trademark remain the property of their owners. BlueWake cannot grant rights it does not hold.

This repository contains no disc image, playable game assets, saves or code translated from the game.
The Windows release build described above is the only published file that contains translated code.
Documentation screenshots depict the game and are not covered by BlueWake's software license. You
supply your own legally obtained USA `GZLE01` revision 0 disc, and the app or IPA you build from it
contains code translated from that disc (`Frameworks/gGZLE01_recomp.dylib`). That build is for your
own use: do not share, upload or sell it. The software license does not grant any rights in
game-derived code, and running a GPL-covered translator does not by itself place its output under
the GPL.

## Mods

Better Wind Waker, the widescreen code from Dolphin's game settings and HD texture packs are the work
of their authors and keep their own terms. The repository carries only the widescreen code's text
(`mods/widescreen/GZLE01.gecko` and its 16:10 variant) and the option-site descriptions derived from
Better Wind Waker. Personal builds translate both behaviors at those sites from the player's disc;
the settings select which behavior runs. You add texture packs yourself.

The optional Wind Waker HD texture importer (`scripts/import_wwhd_textures.py`)
extracts artwork only from the user's local disc. Its output, discs, tickets and
keys are personal data and must never be included in a public release. The
vendored Wii U surface address library is AboodXD's BFRES-Tool addrlib under
GPL-3.0-or-later; its license, copyright and pinned source are recorded in
`scripts/wwhd/vendor/`. Format reader attribution is in `docs/WWHD_TEXTURES.md`.

## Stage select names

`config/stage_select/` holds English names for the developers' stage select that is still on the disc
([docs/STAGE_SELECT.md](docs/STAGE_SELECT.md)). The menu's own Japanese labels stay on the player's disc;
none of these files copies them.

- `names.tsv` is BlueWake's own: short descriptive names for each menu line, plus the place each
  line goes to (stage, room, spawn point and layer) and the spawn points that room has.
- `names-randomizer.tsv` names dungeon rooms after their item locations in the
  [Wind Waker Randomizer](https://github.com/LagoLunatic/wwrando) (LagoLunatic, MIT). Its license and
  copyright are in `config/stage_select/NOTICE-randomizer`.
- `names-decomp.tsv` names other rooms after the actors in them, as described in zeldaret/tww's actor
  sources at revision
  [342d447](https://github.com/zeldaret/tww/blob/342d447b6b6b3bafe7a0dc42d6b1e36b2de172e0/LICENSE)
  (CC0-1.0).

## Runtime metadata

`apple/ios/resources/initial_pipeline_cache.db` contains Aurora rendering-pipeline descriptions
recorded during testing: structural GPU state, configuration versions and usage order. It does not
contain textures, models, game executables or compiled shaders. Aurora builds shaders from these
descriptions using its own renderer. The cache reduces missing draws while first-use pipelines compile.

The bundled `composite-rt.profdata` and `host.profdata` contain LLVM profiling metadata for the
compatibility runtime and host. They contain function identifiers and execution counts, not machine
code. The translated-game optimization profile used by the developer is not distributed; player
builds must generate their own from their disc. See [Builder status](docs/BUILDER.md#optimization-profiles).
