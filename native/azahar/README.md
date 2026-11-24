# Azahar 2127.0-rc5 avec le JIT de RewindBox

Correctif `rewindbox-jit.patch` (19 fichiers, +524/−114) appliqué à la source officielle 2127.0-rc5, révision `6f293a24`
(tête de `master` au 21 novembre 2026).

- **Source.** Archive « unified source » de la release, avec tous les sous-modules, vérifiée par son SHA-256 :
  `09a441d9…79cb7`, 43 174 580 octets, identique au fichier `.sha256sum` publié.
- **Compilation.** Même recette que l'amont (`.github/workflows/libretro.yml`, job `libretro-ios`), par
  `build-utils/libretro_source_cores.py`, appelé par le job `source-cores` de
  `.github/workflows/libretro-cores.yml`.
- **Licence.** GPL-3.0-or-later. dynarmic est sous 0BSD, oaknut sous MIT, l'en-tête ABI sous MIT. Les fichiers
  modifiés sont ceux du correctif (GPLv3 § 5).

## Version choisie

Décision du mainteneur, 23 novembre 2026 : « la dernière version d'Azahar sans attendre ». Le correctif, écrit
d'abord pour 2127.0-alpha1 (`5f3306d1`), a été régénéré sur la rc5 :
- il s'appliquait déjà sans conflit (seulement des décalages de lignes) ;
- son contenu est identique, hors positions des blocs et lignes d'index ;
- sur les 17 fichiers, seuls `citra_libretro.cpp`, `settings.h` et `shader_jit_a64_compiler.cpp` avaient changé en
  amont, sans recouvrement avec le correctif ;
- dynarmic et oaknut n'ont pas bougé.

Apports de l'amont entre alpha1 et rc5 qui atteignent le cœur libretro (94 commits, la plupart pour Android et Qt) :
- **performances :**
  - JIT de shaders AArch64 plus efficace (écritures masquées, #2597) ;
  - travail GPU limité aux images du jeu (#2755) ;
  - sources de latence (#2700) ;
  - réglage de l'avance sur le GPU (#2793, désactivé par défaut) ;
- **précision :**
  - GSP (#2678), son CSND (#2680) ;
  - interpréteur Thumb (#2710) ;
  - états de sauvegarde avec modules LLE (#2730) ;
  - limite de temps CPU, services boss et nwm, cache de textures, proctex Vulkan ;
- **nouveautés :**
  - MSAA (#2053), sans option libretro ;
  - ROM groupées `.bcci`/`.bcxi` dans les extensions du cœur ;
  - plugins v3, signature des contenus chiffrés.

**États de sauvegarde.** `System::LoadStateBuffer` refuse un état créé par une autre révision. Les états faits avec
Azahar 2127.0-alpha1 ne se chargent donc plus. Les sauvegardes internes des jeux ne sont pas concernées.

## Ce que change le correctif

- **oaknut** (`code_block.hpp`). Allocateur externe facultatif : `ptr()` est la vue R|X de l'arène RewindBox,
  `wptr()` son alias RW. `protect`/`unprotect` ne font plus rien et `invalidate` passe par le `flush` de l'ABI.
  Sans l'allocateur, le comportement est inchangé.
- **dynarmic.**
  - Les générateurs sont construits avec `(mem.wptr(), mem.ptr())`, dans `address_space.cpp` et les deux
    générateurs de liens.
  - Le spin-lock, auparavant compilé à la volée au chargement dans un bloc mappé par `mmap`, devient de
    l'assembleur précompilé.
  - Sur iOS, gestionnaire d'exceptions générique : l'arrière-plan Mach prenait le port d'exceptions de tout le
    processus.
- **`rewindbox_jit.{h,cpp}`** (nouveaux, compilés seulement sous `IOS`).
  - `rewindbox_libretro_jit_install` vérifie version, taille, page et capacité, puis fait un seul `allocate`.
  - Un allocateur interne de premier ajustement découpe l'arène :
    - jusqu'à 32 Mio par cache d'application ;
    - 2 Mio par cache inactif ;
    - 16 Mio pour le JIT de shaders PICA.
  - Libération à `retro_deinit`.
- **`core_settings.cpp`.**
  - Les options `citra_use_cpu_jit` et `citra_use_shader_jit` sont déclarées sur iOS.
  - `ApplyJitPlan()` active le JIT seulement si l'option le demande, si l'ABI est installée, si
    `CanUseJIT()` répond oui et si l'arène suffit. Sinon : FastInterp et l'interpréteur de shaders.
- **`settings.h`, `arm_dynarmic.cpp`.**
  - Caches de code bornés, avec un nouvel essai à 8 puis 2 Mio au lieu d'un échec.
  - Les instances dynarmic des tables de pages abandonnées sont libérées.
- **JIT de shaders.** Copie dans `wptr()`. Région pleine : l'interpréteur prend les shaders suivants, jamais
  d'éviction au milieu d'un dessin.
- **`libretro.osx.def`.** Exporte `_rewindbox_libretro_jit_install`.
- **`libretro_vk.{cpp,h}` : une image de sortie par image du pool.** En amont, les deux `Frame` du pool partagent une
  seule image de sortie (« All frames use the same output texture ») : le frontend devait copier chaque image avant
  que la suivante soit dessinée dans la même. Chaque `Frame` a maintenant la sienne (`CreateFrameImage`, détruite
  avec le pool ; `view_info` donne sa description à `retro_vulkan_image`), choisie par l'index de synchronisation
  du frontend comme avant. Le frontend de RewindBox montre ainsi l'image N pendant que N+1 est dessinée, sans copie
  (`LibretroVulkanRenderer`, remise directe). Mémoire : une image de plus (76,8 Mio à 10×).

## Remise des images au frontend

| Azahar | Frontend RewindBox | Copies par image |
| --- | --- | --- |
| Une image de sortie partagée (avant) | relecture puis copie GPU vers Metal | 2 (2 × 76,8 Mo à 10×) |
| Une image par trame (ce correctif) | image du cœur prêtée telle quelle à Metal | 0 |

## Arène demandée

128 Mio, tout résident :

| Console | Répartition | Total |
| --- | --- | --- |
| Old 3DS | 2 × 32 Mio d'application + 2 × 2 Mio inactifs + 16 Mio de shaders | 96 Mio |
| New 3DS | 4 × 24 Mio + 4 × 2 Mio + 16 Mio | 128 Mio |

## Identité et notice

`libretro_source_cores.py` remplace dans la collection le binaire, son enregistrement d'identité (`version`
2127.0-rc5, `sourceCommit`, source, correctif, `jitInterface: 1`, `jitArenaBytes`) et, dans
`Libretro-Licenses/LIBRETRO_CORES.txt`, les lignes qui décrivaient la release officielle (`noticeLines` de
`source.json`) ; il y ajoute la provenance du binaire. Les notices de l'application (`NOTICE.md`,
`assets/legal/THIRD_PARTY_NOTICES.md`, `assets/legal/libretro/`) changent avec la livraison qui adopte ce binaire.

## Ce qui n'est pas vérifié

Vérifié :
- application du correctif sur l'archive rc5 et empreinte de l'en-tête ABI dans l'arbre ;
- compilation iOS de la même version du correctif sur alpha1 (run 45182286491) ;
- banc hôte Linux de l'arène et de la séparation écriture/exécution d'oaknut (sur alpha1) ;
- assemblage du spin-lock pour arm64-apple-ios14.0.

Vérifié pour les images par trame : vérification syntaxique de `libretro_vk.cpp` (clang 18, C++20, mêmes définitions
qu'avant le changement, qui passent aussi sur l'original).

Pas encore vérifié :
- la compilation iOS sur rc5 (demandée au job `source-cores`) ;
- le fonctionnement sur iPhone ;
- la fréquence des vidages de cache à 24–32 Mio et le nombre réel de shaders par jeu. Les lignes `[rb-jit]` du
  journal les mesureront.
- la remise directe des images par trame : le journal de session doit écrire `vulkan: frames reach Metal directly,
  no copy` (sinon `by a GPU copy`, voie d'avant), et la surcouche de performances donner les FPS et le temps GPU
  à 10×.
