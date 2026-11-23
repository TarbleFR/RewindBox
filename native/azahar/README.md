# Azahar 2127.0-alpha1 avec le JIT de RewindBox

Correctif `rewindbox-jit.patch` (17 fichiers, +479/−66) appliqué à la source officielle `5f3306d1`.

- **Source.** Archive « unified source » de la version, avec tous les sous-modules, vérifiée par son SHA-256.
- **Compilation.** Même recette que l'amont (`.github/workflows/libretro.yml`, job `libretro-ios`), par
  `build-utils/libretro_source_cores.py`, appelé par le job `source-cores` de
  `.github/workflows/libretro-cores.yml`.
- **Licence.** GPL-3.0-or-later. dynarmic est sous 0BSD, oaknut sous MIT, l'en-tête ABI sous MIT. Les fichiers
  modifiés sont ceux du correctif (GPLv3 § 5).

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

## Arène demandée

128 Mio, tout résident :

| Console | Répartition | Total |
| --- | --- | --- |
| Old 3DS | 2 × 32 Mio d'application + 2 × 2 Mio inactifs + 16 Mio de shaders | 96 Mio |
| New 3DS | 4 × 24 Mio + 4 × 2 Mio + 16 Mio | 128 Mio |

## Ce qui reste identique à la version officielle

- Révision `5f3306d1`, d'où des états de sauvegarde compatibles : `LoadStateBuffer` exige cette révision exacte.
- Version, iOS 14.0 minimum, dépendances et version du cache de shaders.

Diffèrent : la date de compilation, la chaîne `describe` et le SDK (Xcode 26.3). En plus : un export et deux
options.

## Ce qui n'est pas vérifié

Vérifié jusqu'ici :
- application du correctif sur l'archive ;
- compilation syntaxique des unités modifiées avec `-DIOS` ;
- banc hôte Linux de l'arène et de la séparation écriture/exécution d'oaknut ;
- assemblage du spin-lock pour arm64-apple-ios14.0.

Pas encore vérifié :
- la compilation iOS ;
- le fonctionnement sur iPhone ;
- la fréquence des vidages de cache à 24–32 Mio et le nombre réel de shaders par jeu. Les lignes `[rb-jit]` du
  journal les mesureront.
