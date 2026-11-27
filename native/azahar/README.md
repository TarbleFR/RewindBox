# Azahar 2127.0-rc5 avec le JIT de RewindBox

Correctif `rewindbox-jit.patch` (43 fichiers, +1781/−192) appliqué à la source officielle 2127.0-rc5, révision `6f293a24`
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

## Rendu à haute résolution sur un GPU à tuiles

Un GPU d'iPhone dessine par tuiles : au début de chaque passe de rendu, il recharge depuis la mémoire les
attachements (couleur, profondeur-stencil) ; à la fin, il les réécrit. À 10×, l'écran du haut fait 4000 × 2400 :
38,4 Mo de couleur et 48 Mo de profondeur-stencil (D32S8 chez MoltenVK). Chaque passe coupée coûte donc environ
170 Mo de trafic, soit 10 Go/s à 60 images/s. Trois changements de `renderer_vulkan` (Vulkan, tous GPU) :

- **Effacements reportés** (`vk_render_manager`, `vk_texture_runtime`, `vk_scheduler`). Les jeux effacent leurs
  tampons couleur et profondeur à chaque image (remplissages mémoire du GSP). Azahar en faisait un
  `vkCmdClearColorImage`/`vkCmdClearDepthStencilImage` (une passe Metal de plus qui écrit toute l'image), puis la
  passe suivante relisait l'image. Un effacement de toute l'image (niveau 0, couche 0, un échantillon) attend
  maintenant la commande suivante :
  - si c'est la passe d'un framebuffer de même taille qui a cette image en attachement, l'effacement devient son
    opération de chargement (`CLEAR`) : ni écriture séparée, ni relecture ;
  - toute autre commande l'enregistre d'abord comme avant (fonction appelée par `Scheduler::Record` avant la
    commande suivante) : l'ordre du travail GPU ne change pas.
- **Zone de rendu des cibles** (`RenderManager::BeginRendering`, `FramebufferHelper::FramebufferRect`). La zone
  de rendu est le rectangle des cibles du jeu dans leurs surfaces (tout le framebuffer dans le cas courant), et
  non plus celui du dessin, qui reste son ciseau :
  - un dessin avec une autre fenêtre (viewport) sur les mêmes cibles continue la passe au lieu de la couper ;
  - une cible qui n'occupe qu'une partie d'une grande surface ne fait pas charger ni écrire toute la surface ;
  - MoltenVK n'utilise le chargement `CLEAR` que pour une zone entière.

  La passe qui se termine pose aussi ses barrières sur ses propres images ; avant, elles visaient celles de la
  passe suivante.
- **Attachement gardé** (`RasterizerVulkan::Draw`). Un dessin qui n'utilise que la couleur (HUD, effets sans test
  de profondeur) ou que la profondeur prenait un framebuffer sans l'autre attachement, ce qui coupait la passe.
  Tant que la passe des deux cibles est ouverte et que les registres désignent les mêmes cibles, l'autre reste
  attaché. Le dessin ne le touche pas : sans test ni écriture de profondeur, ni test de stencil ; ou masque
  d'écriture couleur nul. La couleur n'est pas gardée quand l'émulation du mélange la relit.

**Mesures.** Toutes les 600 images, le cœur écrit une ligne dans son journal, recopiée dans `session.log` :

```
[rb-perf] azahar frames=600 fps=… res=10 out=4000x4800 per frame: passes=… folded=… flushed=… partial=… kept=…
uploads=… upload_kb=… downloads=… copies=… blits=… transfers=… fills=… submits=… finishes=… finish_ms=…
sync_ms=… present_ms=…
```

Les valeurs sont des moyennes par image :
- `passes` : passes de rendu commencées ;
- `folded` : effacements pris par une passe ;
- `flushed` : effacements enregistrés à part ;
- `partial` : effacements d'une partie d'image ;
- `kept` : dessins qui ont gardé l'autre attachement ;
- `transfers` : transferts vers l'affichage (un par écran et par œil : 3 au lieu de 2 signale un œil droit
  dessiné) ;
- `fills` : remplissages mémoire du jeu ;
- `finish_ms` : attentes du processeur sur le GPU ;
- `sync_ms` : attente dans le `wait_sync_index` du frontend ;
- `present_ms` : remise de l'image au frontend.

`fps` compte le temps du menu en pause.

## Remise des images au frontend

| Azahar | Frontend RewindBox | Copies par image |
| --- | --- | --- |
| Une image de sortie partagée (avant) | relecture puis copie GPU vers Metal | 2 (2 × 76,8 Mo à 10×) |
| Une image par trame (ce correctif) | image du cœur prêtée telle quelle à Metal | 0 |

## Performances à 10× : deuxième série (27 novembre 2026)

**Point de départ mesuré sur iPhone.** Journal du mainteneur (Mario Kart 7, A18 Pro, iOS 27, 10× demandé mais
mesure à 9× sur 600 images) : `fps=57.8 out=3600x4320 passes=1.1 folded=0.00 flushed=1.48 partial=0.12 copies=0.8
blits=2.5 transfers=2.46 fills=3.19 submits=1.0 sync_ms=0.97`. Le JIT est actif (`cpu=dynarmic`, `shader=jit`). Le
`used=134217728` de la ligne `[rb-jit] arena=` du frontend est la réservation de l'arène (Azahar en prend toute la
capacité en un seul `allocate`, d'où `blocks=1`, `LibretroJitArena.m`), pas le remplissage des caches de code.
Aucune mesure à 10× soutenue dans ce journal.

**Goulets retenus (lecture du code, pas de mesure sur appareil) :**

1. **Aucun effacement pris par la passe** (`folded=0`) : le report d'effacement de la première série ne servait à
   rien sur ce jeu. Toute commande enregistrée entre l'effacement reporté et la passe (envoi de texture, copie de
   validation d'une texture rendue, barrière d'une image neuve) l'écrivait à part, puis la passe relisait l'image.
2. **Cibles de rendu réallouées à chaque image (hypothèse forte).** Un remplissage mémoire qui couvre toute une cible
   la rendait entièrement invalide ; le cache la désinscrivait (condamnée jusqu'à ce que le GPU ait fini) et la
   première passe suivante en allouait une neuve : couleur et profondeur des deux écrans, environ 150 Mio par image
   à 10× quand le GPU a une image de retard. Mesuré désormais par `created` et `created_mb`.
3. **Pas de compression sans perte des cibles RGBA8.** Toute surface RGBA8 recevait l'usage stockage et un format
   modifiable (vue R32Uint), au cas où elle servirait plus tard d'ombre. MoltenVK en fait
   `MTLTextureUsageShaderWrite | MTLTextureUsagePixelFormatView` (`MVKPixelFormats::getMTLTextureUsage`) ; la
   documentation d'Apple (« Optimizing texture data ») exclut de la compression sans perte toute texture qui a l'un de
   ces usages. Les cibles couleur, les écrans de destination des transferts et leur lecture par la composition
   circulaient donc à plein débit (38,4 Mo par écran du haut à 10×, plusieurs fois par image).
4. **Branchements indirects du CPU invité.** Le dorsal arm64 de dynarmic n'implémente pas `FastDispatchHint`
   (« TODO », aussi dans la tête d'`azahar-emu/dynarmic`) : chaque branchement indirect qui n'est pas un retour
   (BX/BLX registre, MOV/LDR vers PC, tables de sauts) repassait par le répartiteur C++ (appel, calcul du descripteur,
   recherche dans la table de hachage).

**Changements :**

| Chantier | Fichiers | Effet attendu |
| --- | --- | --- |
| Effacements gardés jusqu'à leur passe | `vk_scheduler.h` (`RecordIndependent`), `vk_render_manager`, `vk_texture_runtime` | Les envois, copies, blits, effacements partiels, copies de rétroaction et barrières d'images neuves n'écrivent que les effacements de **leurs** images ; les autres attendent la passe qui les prend en chargement `CLEAR`. Ordre GPU inchangé pour chaque image. |
| Cibles gardées à travers un remplissage | `rasterizer_cache.h` (`InvalidateRegion`) | Une cible de rendu (couleur ou profondeur, pas une texture) entièrement couverte par un remplissage reste inscrite, invalide : la passe suivante la revalide depuis le remplissage (effacement, plié) sur les mêmes images et le même framebuffer. |
| Stockage seulement pour les ombres | `vk_texture_runtime` (`EnsureShaderStorage`, `ImageUsage`, `ImageFlags`), `surface_base.h`, `framebuffer_base.h`, `rasterizer_cache.h`, `vk_rasterizer.cpp` | Les surfaces RGBA8 naissent sans usage stockage ni format modifiable, donc compressibles. Celles créées pour un rendu d'ombre (ou une texture d'ombre) les ont dès la création ; une surface qui en a besoin plus tard (vue R32, conversion D24S8 → RGBA8) reçoit de nouvelles images avec une copie de son contenu, les anciennes sont gardées jusqu'à la fin du GPU (`Retire`), et `view_generation`, dans la clé des framebuffers, empêche de réutiliser leurs vues. |
| Répartition rapide arm64 | dynarmic `address_space`, `a32_address_space`, `emit_arm64_a32.cpp`, `emit_arm64.h` | Table directe de 65 536 entrées (1 Mio par instance de JIT, hors arène) remplie par le répartiteur ; le code d'un branchement indirect vérifie le budget de cycles, lit la case (EOR, UBFX, ADD, LDP), compare l'emplacement et saute. Vidée avec le cache et à chaque invalidation. |
| Mesures | `vk_rewindbox_perf.h`, `renderer_vulkan.cpp`, `arm_dynarmic.cpp`, dynarmic `a32.h` (`GetCacheStats`) | Ligne `[rb-perf]` complétée ; nouvelle ligne `[rb-jit] azahar cpu` par cœur et par minute. |

Divers : `ScaleUp` ne détruit plus immédiatement une image encore utilisée par des commandes enregistrées (retraite) ;
les images de copie de rétroaction et MSAA ne prennent plus l'usage stockage.

**Nouveaux champs de `[rb-perf]`** (moyennes par image, ajoutés en fin de ligne) :
- `deferred`, `replaced` : effacements reportés, remplacés par un effacement suivant ;
- `touched` : effacements écrits avant un transfert de leur propre image ;
- `held` : transferts enregistrés pendant que des effacements d'autres images attendaient (gain du chantier 1) ;
- `missed` : effacements d'une pièce jointe que sa passe n'a pas pu prendre (zone ou taille différente) ;
- `retained` : cibles gardées à travers un remplissage ; `created`, `created_mb` : surfaces allouées ;
- `migrated` : surfaces passées au stockage après coup ; `fb_copies` : copies d'une cible entière (rétroaction,
  mélange émulé) ;
- `worker_ms` : attente du fil Vulkan à chaque fin d'image (`TickFrame`) ;
- `frame_ms_p50`, `p95`, `p99`, `max` : temps entre deux images du jeu.

**Ligne `[rb-jit] azahar cpu`** (une par cœur et par minute, quand l'arène RewindBox est installée) :
`cache_kb=utilisé/capacité` (prélude compris), `live_blocks`, `compiled=+N`, `avg_bytes`, `compile_ms=+…`,
`clears=+N` (vidages entiers), `full=+N` (dont cache plein), `invalidated=+N` (blocs invalidés par une écriture de
code), `dispatch_per_s` (retours au répartiteur).

**Dimensionnement de l'arène.** Inchangé : 2 × 32 Mio d'application, 2 × 2 Mio inactifs, 16 Mio de shaders, 8 Mio de
marge (Old 3DS : 92 Mio sur 128). Rien ne montre encore que 32 Mio soit un goulet ; `full=+N` non nul sur une
longue course le montrerait, et 36 Mio restent libres dans l'arène pour l'agrandir alors. La réserve universelle
partagée n'est pas touchée.

**MetalFX.** Sans effet à 9× et 10× : `LibretroMetalFXOutputSize` refuse une image du cœur plus grande que sa place
à l'écran (`[rb-metalfx] standard picture METALFX_RATIO` dans le journal), la composition finale est un
échantillonnage linéaire. Le réglage n'a donc ni coût ni bénéfice à ces résolutions ; rien n'est changé.

**Écartés ou laissés :**
- *Ne plus écrire la profondeur en fin de passe* : il faudrait savoir que le prochain usage est un effacement ; une
  erreur corromprait la profondeur d'une image. Écarté.
- *Composer à la taille de l'écran au lieu de 4000 × 4800* : économiserait environ 150 Mo par image, mais le cœur ne
  connaît pas la taille d'affichage ; demande une interface avec le frontend partagé. Laissé.
- *Supprimer le `WaitWorker` de chaque `TickFrame`* : protège le ramasse-miettes du cache ; d'abord mesurer
  `worker_ms`.
- *Table de pages à décalage absolu (une instruction de moins par accès mémoire)* : 8 Mio de table en plus par
  processus pour un gain faible ; *fastmem* : demande un miroir de 4 Gio de la mémoire invitée et un gestionnaire
  d'exceptions que l'intégration iOS a remplacé. Écartés.
- *Agrandir les caches de code* : sans preuve de saturation. Écarté pour l'instant.

## Protocole de vérification sur iPhone (60 images/s à 10×)

1. Collection compilée par le job `source-cores` de ce commit, adoptée par une IPA privée (autre session).
2. Mario Kart 7, même circuit et même départ (contre-la-montre 150 cc, Circuit Mario par exemple), MetalFX laissé
   tel quel, appareil froid (`thermal=0` en début de journal), luminosité et Mode économie identiques.
3. Pour chaque facteur 1×, 6×, 8×, 9×, 10× : changer la résolution au menu, reprendre, attendre une ligne
   `[rb-perf]` complète (600 images, environ 10 s), puis courir 3 tours ; cinq répétitions par facteur.
4. Relever dans `session.log` : `fps`, `frame_ms_p50/p95/p99/max`, `sync_ms`, `worker_ms`, `folded` contre
   `deferred`, `flushed`, `missed`, `created`/`created_mb`, `retained`, `fb_copies`, `transfers`, et les lignes
   `[rb-jit] azahar cpu` (`full`, `compile_ms`, `dispatch_per_s`) ; `thermal=` et `footprint=` des lignes `system:`.
5. 60 images/s à 10× : `fps` ≥ 59,5 et `frame_ms_p99` ≤ 20 sur toutes les lignes d'une course, sans montée de
   `thermal` au-delà de 1 sur 3 tours. Le journal doit garder `vulkan: frames reach Metal directly` après chaque
   changement de résolution et chaque retour du menu.
6. Lecture : `sync_ms` haut avec `fps` bas = GPU ou présentation ; `worker_ms` haut = encodage Vulkan/MoltenVK sur le
   fil du cœur ; `compile_ms` ou `full` non nuls en course = cache de code ; `fps` à 10× proche de 8× = limite CPU.
7. Contrôle d'image : HUD, carte de l'écran du bas, ombres, rétroviseur, menus ; un ou deux autres jeux 3DS (un jeu
   à ombres PICA, un jeu qui relit la profondeur) pour les surfaces passées au stockage (`migrated`).

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

Vérifié pour le rendu par tuiles :
- vérification syntaxique (clang 18, C++20) des fichiers changés et de ceux qui incluent leurs en-têtes
  (`vk_blit_helper`, `vk_pipeline_cache`, `vk_graphics_pipeline`, `libretro_vk`), sans nouvel avertissement ;
- application du correctif sur l'archive rc5, arbre obtenu identique à l'arbre vérifié.

Vérifié pour la deuxième série (27 novembre 2026, hôte Linux x86-64, 2 cœurs) :
- application du correctif sur l'archive rc5 téléchargée (SHA-256 contrôlé), arbre identique à l'arbre de travail ;
  le correctif d'avant se régénère octet pour octet par la même commande (`git diff`, abréviation 7) ;
- compilation hôte (clang 18, `-Werror` du projet) de `video_core` entière (Vulkan, OpenGL, cache), de dynarmic
  (dorsal x64) et d'`arm_dynarmic.cpp` ;
- vérification syntaxique pour AArch64 des fichiers du dorsal arm64 touchés et de leurs voisins ;
- séquence de recherche émise par oaknut, désassemblée par `llvm-mc` : 13 instructions attendues, case identique à
  `FastDispatchIndex` ;
- dynarmic arm64 compilé pour Linux AArch64 (GCC 13) et exécuté sous `qemu-aarch64` : 23 cas A32 de dynarmic
  passés, dont 4 cas écrits pour cette vérification et laissés hors du dépôt (pas de nouveau test pour les cœurs) :
  résultat identique avec et sans la table, **5 retours au répartiteur au lieu de 20 004** pour 20 000 appels
  indirects, passage ARM → Thumb, aucune entrée périmée après `InvalidateCacheRange` ou `ClearCache`, arrêt en fin de
  tranche de temps sur une boucle de sauts indirects. Le cas « ASIMD Decoder » (ordre des tables), très long sous
  qemu, n'a pas été relancé. Ni le temps sous qemu ni ce décompte ne mesurent le gain sur l'A18 Pro.

Pas encore vérifié :
- la compilation iOS de la deuxième série (job `source-cores`) ;
- sur iPhone : `folded` proche de `deferred`, `created` proche de 0 en course, `retained` non nul, image identique
  (effacements, HUD, ombres de jeux qui en ont, effets lisant la profondeur), FPS et `frame_ms_p95` à 9× et 10×,
  `dispatch_per_s` et `full` dans `[rb-jit] azahar cpu` ; la compression sans perte elle-même n'est pas observable
  dans le journal (seulement par le débit mémoire dans Instruments ou par les FPS) ;
- la compilation iOS sur rc5 (demandée au job `source-cores`) ;
- le fonctionnement sur iPhone ;
- la fréquence des vidages de cache à 24–32 Mio et le nombre réel de shaders par jeu. Les lignes `[rb-jit]` du
  journal les mesureront.
- la remise directe des images par trame : le journal de session doit écrire `vulkan: frames reach Metal directly,
  no copy` (sinon `by a GPU copy`, voie d'avant), et la surcouche de performances donner les FPS et le temps GPU
  à 10×.
- le rendu par tuiles sur iPhone : image identique (effacements, HUD, ombres) et lignes `[rb-perf]` avec
  `folded` proche de `fills` et `passes` en baisse. Le gain dépend du jeu : un jeu qui efface autrement ou dessine
  dans beaucoup de cibles en gagne moins. 60 images/s constantes à 10× restent limitées par le GPU et la chauffe
  de l'iPhone.
