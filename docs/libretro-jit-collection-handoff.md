# Passation : collection libretro avec DeSmuME (JIT), Beetle PSX (Lightrec) et Azahar 2127.0-rc5

*23 novembre 2026 — branche `Claude`. Note pour la session qui construit les IPA : consigne du mainteneur, « pas
d'ipa c'est une autre session qui la fera ». Cette session n'a lancé aucune livraison après la 826.*

## La collection

- **Source.** Route source-cores de `.github/workflows/libretro-cores.yml`, commit `6cd6a89b`.
  - Run [45213717171](https://github.com/TarbleFR/RewindBox/actions/runs/45213717171).
  - Artefact `LibretroCores-6cd6a89bfdaded3e52400d4640fff4ac17f1c6d9`.
- **Base.** La collection que la 825 retient, république par la Build 801.
- **Cœurs compilés par RewindBox** (`compiled: true`, `jitInterface: 1`) :

  | Cœur | Moteur JIT | Arène | Épingle |
  | --- | --- | --- | --- |
  | `desmume` | JIT AArch64 | 32 Mio | [native/desmume](../native/desmume/README.md) |
  | `mednafen_psx_hw` | Lightrec | 16 Mio | `native/beetle-psx` |
  | `mednafen_psx` | Lightrec | 16 Mio | `native/beetle-psx` |
  | `azahar` 2127.0-rc5 | dynarmic | 128 Mio | `native/azahar` |

  - Azahar a la même source que dans la 826. Son binaire diffère pourtant de celui de la 826 : la date de
    compilation est désormais fixée par `sourceDateEpoch`.
- **Inchangé à l'octet près** : les 31 autres cœurs, MoltenVK et les fichiers système.

## Déjà dans les sources

- **Entrée de la collection** dans `COLLECTIONS` de `.github/diagnostics/libretro_source_collections.py`.
- **Catalogue** (`lib/services/libretro_core_catalog.dart`) :
  - DeSmuME : `desmume_cpu_mode` vaut `jit` par défaut ; sans JIT, il est forcé à `interpreter` et
    `desmume_jit_block_size` à `12`.
  - Beetle PSX et Beetle PSX HW : `…_cpu_dynarec` vaut `execute` par défaut. Sans JIT, il est forcé à `disabled`
    et les cinq options de réglage du dynarec reprennent leurs valeurs par défaut.
  - Le contrat d'options de cette collection passe sur les 35 binaires
    (`test/libretro_core_options_test.py --cores`).
- **Tests** : `test/libretro_core_options_test.py` et `test/libretro_core_catalog_test.dart` attendent ces valeurs.
- **Notices** :
  - `NOTICE.md` et `assets/legal/THIRD_PARTY_NOTICES.md` (sections DeSmuME et Beetle) ;
  - `assets/legal/libretro/LIBRETRO_CORES.md` ;
  - `license-sources.json` : sources compilées attestées, textes Lightrec et GNU Lightning, `LGPL-2.1.txt` ;
  - `embed_legal_bundle.py --validate-only` passe.

## À faire dans le manifeste de la livraison qui l'adopte

1. **Origine.** `components.libretro.origin` pointe vers l'artefact ci-dessus, en mode `retain-archive`.
   `jitHelper: true` est déjà acquis avec la 826.
2. **Images qui changent** (`images.mustChange`) :
   - `Frameworks/desmume_libretro.framework/desmume_libretro` ;
   - `Frameworks/mednafen_psx_hw_libretro.framework/mednafen_psx_hw_libretro` ;
   - `Frameworks/mednafen_psx_libretro.framework/mednafen_psx_libretro` ;
   - `Frameworks/azahar_libretro.framework/azahar_libretro` ;
   - `Frameworks/App.framework/App`, pour le catalogue et les notices.
3. **Images retenues.** `images.retained.libretro` liste les 31 autres cœurs.
4. **Entrées.** `build-utils/libretro_source_cores.py`, `native/desmume`, `native/beetle-psx` et `native/azahar`
   ont changé depuis la 826. Ce sont des entrées de recette, que l'IPA ne compile pas.
5. **Commits concurrents.** Les classer, revus ou « source seulement », comme pour la 826.

## À regarder sur iPhone

- **Journaux `[rb-jit]` de DeSmuME.**
  - Au démarrage : `installed=1 … wanted=1 jit=1`.
  - Toutes les 30 s : `blocks`, `used`, `flushes`, `failures`. Si les rembobinages (`flushes`) reviennent souvent,
    monter `jitArenaBytes`.
- **Jeux DS de référence** : section 7.5 de [desmume-arm64-jit-architecture.md](desmume-arm64-jit-architecture.md).
- **Beetle.** Lightrec actif quand l'aide JIT a préparé l'arène ; sinon l'interpréteur.
- **Sans LocalDevVPN** : interpréteur pour les trois moteurs, avec l'avis « JIT indisponible ».
- **Non vérifié.** Rien n'a encore tourné sur iPhone. La vérification hors appareil est décrite dans
  `native/desmume/README.md` et `native/beetle-psx/README.md`.
