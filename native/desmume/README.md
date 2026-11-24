# DeSmuME (95b4d798) : JIT AArch64 avec l'interface JIT de RewindBox

Cœur libretro [libretro/desmume@95b4d798](https://github.com/libretro/desmume/tree/95b4d798731caa809125b6c3c11d17cc332ff6ef)
(tête de `master`, la révision des binaires buildbot livrés jusqu'ici), complété par le JIT AArch64 de l'équipe
DeSmuME, que le fork libretro n'a jamais importé, puis corrigé et branché sur
`packages/libretro_internal_bridge/ios/Classes/RewindBoxLibretroJit.h`. S'y ajoutent les étapes 1 à 4 de
[docs/desmume-arm64-jit-architecture.md](../../docs/desmume-arm64-jit-architecture.md) (sections 13 et 14) :
couche commune, interpréteur en cache, JIT RewindBox à appels puis natif ; puis (section 15) le correctif du gel
de l'IPA 828 et un rendu plus rapide en haute résolution interne ; enfin (section 16) le suréchantillonnage 3D,
les mesures `[rb-perf]` et la 3D qui se dessine pendant la composition 2D.

## Ce que la compilation assemble

1. **Fichiers importés** (`importFiles` de `source.json`) : `desmume/src/utils/arm_jit/arm_jit_arm.cpp`,
   `emit_core.cpp` et `arm64_emit.cpp` de
   [TASEmulators/desmume@b549f71b](https://github.com/TASEmulators/desmume/tree/b549f71b83287f265b6d74b9e77ef5d98a617190),
   pris à cette révision et vérifiés par SHA-256. `arm_emit.cpp` (ARM 32 bits) n'est pas pris.
2. **Correctif** `arm64-jit-abi.patch` (30 fichiers, +4 308/−334), un `git diff` contre l'arbre libretro plus ces
   trois fichiers d'origine. Il crée `utils/arm_jit/rb_cached.cpp`, `rb_a64.h`, `rb_jit.cpp`, `utils/rb_perf.h` et
   `utils/rb_sse2neon.h`, et modifie aussi le rendu (`rasterize.cpp`, `rasterize.h`, `render3D.cpp`, `render3D.h`,
   `GPU.cpp`, `GPU.h`, `gfx3d.cpp`, `types.h`, les trois fichiers `colorspacehandler`) et la sortie du frontend.
   `types.h` et `render3D.h` gardent leurs fins de ligne CRLF d'origine (la 831 les convertissait en entier).
3. **En-tête ABI** hors du correctif, copié par la compilation dans
   `desmume/src/frontend/libretro/rewindbox/RewindBoxLibretroJit.h`.

## Modes de CPU

| `desmume_cpu_mode` | Moteur | Résultat |
|---|---|---|
| `interpreter` | Interpréteur de DeSmuME | Référence |
| `cached` | Interpréteur en cache (étape 2), sans mémoire exécutable | Identique à l'interpréteur, au cycle près |
| `jit` | JIT de T (étape 0) sur la couche commune (étape 1) | Le plus rapide ; fetch non compté, entrelacement des CPU par bloc |
| `jit_exact` | JIT RewindBox (étapes 3 et 4), mode exact | Identique à l'interpréteur, au cycle près |
| `jit_fast` (non proposé) | JIT RewindBox, mode rapide | Cycles de chaque instruction exacts, entrelacement par bloc |

- `jit` et `jit_exact` ne tournent que si l'interface est installée et que l'hôte répond oui à
  `RETRO_ENVIRONMENT_GET_JIT_CAPABLE`. Sinon : interpréteur en cache, quoi que dise l'option.
- Journal au démarrage : `[rb-jit] desmume installed=… arena=… page=… wanted=… jit=… cached=… engine=…`. Ensuite,
  toutes les 30 s de jeu et au déchargement, la ligne d'activité du moteur.
- L'option n'est lue qu'au premier démarrage du cœur : un changement s'applique au lancement suivant.

## Ce que change le correctif

| Partie | Changement |
|---|---|
| Mémoire du code (`emit_core.cpp`) | Plus de `mmap` RWX `MAP_JIT`, de `munmap`, de `pthread_jit_write_protect_np`, de `sys_icache_invalidate` ni d'`exit(0)`. Une seule arène, reçue du frontend : chaque bloc est copié par la vue RW, `flush(rx, n)`, puis exécuté à RX. Arène pleine : tables vidées et arène rembobinée (sûr : on ne compile que depuis le distributeur C, aucun bloc n'est alors sur la pile). Les 256 premiers octets portent les stubs d'entrée et de sortie du JIT RewindBox. |
| Couche commune (étape 1) | Table par pages de 16 Kio allouées à la demande, entrées de 32 bits (décalage dans l'arène, étiquette CPU/Thumb vérifiée à chaque lecture). Un bit par 16 octets de code et des listes de blocs par 512 octets : une écriture invalide tous les blocs qu'elle touche et fait sortir le bloc en cours. Crochets WRAMCNT et VRAM. PC hors région : un pas d'interpréteur. Demandes de sortie : DMA, code modifié, `NDS_Reschedule`, bus gelé, `emu_halt`, attente d'IRQ de chaque CPU. `arm_jit_sync` ne touche plus le modèle de temps du fetch. |
| Interpréteur en cache (étape 2, `rb_cached.cpp`) | Blocs décodés {gestionnaire, opcode, condition} en mémoire ordinaire, invalidés comme le code. Chaque instruction s'exécute comme dans `armcpu_exec` : état du prefetch, condition, gestionnaire, temps du fetch suivant. Une course continue tant que la boucle CPU aurait donné l'instruction suivante à ce CPU ; `nds_timer` avance comme elle. |
| JIT RewindBox (étapes 3 et 4, `rb_a64.h`, `rb_jit.cpp`) | Encodeur AArch64 maison. Étape 3 : chaque instruction appelle le gestionnaire de l'interpréteur ; condition testée en natif ; cycles de l'interpréteur, temps du fetch calculé à la compilation sauf aux changements de ligne du cache d'instructions de l'ARM9. Étape 4 : code natif pour les opérations de données ARM (immédiat ou registre décalé par une constante), les opérations Thumb (décalages, additions, ALU, registres hauts, pile) et les branchements B, BL, B<cond> et BL Thumb. Blocs enchaînés par la table, entrée possible à chaque instruction. Mode exact : test de la boucle CPU et `nds_timer` avant chaque instruction ; mode rapide : entre les blocs. |
| Frontend (`libretro.cpp`, `libretro_core_options.h`) | `rewindbox_libretro_jit_install()` exporté : vérifie version, `structBytes`, pointeurs et page, puis prend toute l'arène préparée (au moins 4 Mio), une fois par ouverture. Valeurs `cached` et `jit_exact` de `desmume_cpu_mode`. |
| Makefiles | `make DESMUME_JIT_A64=1` : `-DHAVE_JIT -DREWINDBOX_LIBRETRO_JIT`, `utils/arm_jit/arm_jit_arm.cpp`, `rb_cached.cpp` et `rb_jit.cpp` à la place du JIT x86. `IOSMINVER` (8.0 par défaut, 14.0 pour RewindBox) remplace la version iOS codée en dur. |
| Compatibilité du fork | `DESMUME_FASTCALL` → `FASTCALL` ; `cp15.setSingleRegionAccess` (méthode dans le fork libretro). |
| TASEmulators/desmume#1002 | UMLAL et UMLALS émis en SMADDL (signé) : UMADDL. SMLAWT identique à SMLAWB : demi-mot haut (`SBFX #16, #16`). Retenue d'`ASR #32` (encodé `#0`) : bit 31, en Thumb **et en ARM**. Interpréteur : NEG Thumb de `0x80000000` calculé en non signé. |
| TASEmulators/desmume#998 | Instruction conditionnelle exécutée, de n cycles fixes : n au lieu de 0. Écriture de r15 par une opération de données : +2 cycles comptés une seule fois. |
| TASEmulators/desmume#997 | Une écriture qui arme un DMA fait sortir le bloc, état synchronisé ; la première exécution d'un bloc, interprétée pendant sa compilation, s'arrête aussi là. |
| `MMU_timing.h` | Accès à la dernière adresse de fetch, que le JIT RewindBox écrit là où elle doit être juste. |
| Écritures multi-registres du JIT de T (`OP_LDM_STM_main`), **correctif du gel de la 828** | T mettait à zéro deux entrées de la taille d'un pointeur à `&JIT_COMPILED_FUNC(adr)` et avançait de deux pointeurs par mot. Sur la table par pages de l'étape 1 (entrées de 32 bits), chaque STM/PUSH vers la RAM principale écrivait donc au-delà des entrées de la page, ou de la page de zéros partagée : mémoire voisine écrasée. Ces écritures passent maintenant par le crochet d'invalidation (`JIT_COMPILED_FUNC_KNOWNBANK`), comme dans `MMU.h`. |
| Rastériseur logiciel (`rasterize.cpp`, `rasterize.h`) | Effacement plan par plan (`std::fill_n`, `memset`) au lieu d'un appel par pixel. Avec des fils : l'image est découpée en tranches que les fils prennent à un compteur commun, au lieu d'une bande fixe par fil (des bandes de lignes consécutives depuis la section 16.5, voir plus bas) ; chaque fil efface une tranche juste avant de la dessiner. À la résolution de la console, le fil d'émulation dessine lui-même, comme sans fils. L'image ne change pas. |
| Composition de la couche 3D (`GPU.cpp`) | Chemin sans appel ni branchement pour le cas courant (copie simple, image 15 bits, pas de fenêtre), que le compilateur vectorise. Mêmes pixels que `_PixelCopy`. |
| Sortie du frontend (`libretro.cpp`) | Conversion en RGB565 des deux écrans par huit pixels en NEON sur AArch64 (mêmes opérations de bits que le chemin SSE2), sur le seul fil d'émulation : vectorisée, elle va plus vite seule qu'avec des fils d'aide qui disputent les cœurs aux fils du rastériseur. Sans vectorisation, à partir de 512×384, elle reste partagée avec trois fils d'aide. |
| 3D pendant la composition 2D (`rasterize.cpp`, `rasterize.h`, `render3D.cpp`, `render3D.h`, `GPU.cpp`, `gfx3d.cpp`) | Les tranches deviennent des bandes de lignes consécutives (huit par fil), prises de haut en bas ; une bande ne parcourt que les polygones qui la croisent. Une bande est post-traitée (contours, brouillard) et moyennée dès qu'elle et ses voisines sont dessinées. Le moteur 2D n'attend plus toute la 3D à la première ligne : chaque ligne attend ses propres lignes 3D (`RenderFinishLines`), sauf sortie 24 bits (une capture directe de la 3D aussi, depuis la section 16.6). Avant que le jeu remplace les listes de polygones (`gfx3d_doFlush`), un rendu encore en cours se termine. Mêmes images. |
| `desmume_num_cores` | Nouvelle valeur `auto`, valeur par défaut : un fil de rastériseur par cœur de l'appareil (8 au plus). |
| Suréchantillonnage 3D (`desmume_rb_3d_supersampling`, `rasterize.cpp`) | `2x` : la 3D est dessinée au double de la résolution interne sur chaque axe (tampons de couleur et d'attributs à part), puis chaque bloc de 2×2 échantillons est moyenné dans le tampon 3D que lisent la 2D, la capture et les états. Moyenne simple là où les quatre alphas sont égaux ; ailleurs, couleur pondérée par l'alpha et alpha moyen. Réservé aux résolutions où la 3D dessinée reste dans 2560×1920 (5× au plus) ; appliqué aussitôt. `disabled` (défaut) : rien ne change. |
| Capture directe de la 3D (`GPU.cpp`, `rasterize.cpp`, `render3D.cpp`) | Une ligne capturée avec la 3D seule pour source attend ses bandes et convertit ses lignes en 15 bits (`RenderFlush16Lines`) ; `RenderFlush` convertit le reste. Mêmes images. |
| Composition 2D en NEON (`types.h`, `GPU.h`, `GPU.cpp`, `colorspacehandler*`, `utils/rb_sse2neon.h`) | `RB_GPU_SSE2` choisit les voies SSE2 des moteurs 2D, y compris sur AArch64, où `rb_sse2neon.h` écrit en NEON les 49 instructions SSE2 qu'elles emploient. Le reste du cœur garde ses voies C++. Mêmes images. |
| Fils du rastériseur (`rasterize.cpp`) | Sur les plates-formes Apple, `QOS_CLASS_USER_INITIATED` : une classe sous le fil d'émulation de l'hôte. |
| Mesures `[rb-perf]` (`utils/rb_perf.h`, `GPU.cpp`, `rasterize.cpp`, `libretro.cpp`) | Toutes les 600 images, une ligne du journal du cœur donne le temps moyen par image de chaque étape (voir ci-dessous). |

## Vérification hors appareil

Banc manuel, non livré et non automatisé (AGENTS.md) :
- cœur compilé pour Linux AArch64 (mêmes options qu'iOS, `__IOS__` compris) ;
- frontend libretro minimal sous qemu-aarch64, avec une arène memfd vue deux fois : RW, puis RX ;
- ROM DS de test écrite pour l'occasion (clang `armv5te`, en-tête NDS minimal), et une ROM de mesure.

La ROM de test couvre :
- calculs ARM et Thumb, multiplications longues et DSP, drapeaux des décaleurs, LDM/STM ;
- code automodifiant, y compris dans le bloc en cours et au milieu d'un autre bloc ;
- le scénario DMA du #997, le remappage WRAMCNT, du code en mémoire de palette, un balayage de 2 Mio ;
- 2 500 fonctions distinctes ;
- un compteur de temps émulé par CPU : ses valeurs finales ne sont égales que si les cycles le sont.

| Configuration | Résultat, comparé à l'interpréteur |
|---|---|
| Étape 0 seule | 85 relevés sur 4 488 différents (code modifié, remappage) |
| `jit` (T + étape 1), blocs de 1, 12 et 100, arène de 4 Mio | 4 493 relevés sur 4 493 identiques |
| `cached` | RAM identique octet pour octet, compteurs identiques, états sauvegardés identiques, chargement d'un état identique |
| `jit_exact`, blocs de 1, 12 et 100, arène de 8 Mio rembobinée | RAM identique octet pour octet, compteurs identiques |
| `jit_fast` | 4 493 relevés sur 4 493 identiques, temps émulé à quelques cycles près |
| `jit` demandé sans capacité JIT | Interpréteur en cache, RAM identique |

Vitesse sous qemu, ROM de mesure, 300 images, les deux CPU toujours occupés. Ce ne sont pas des mesures iPhone :
qemu pénalise surtout les appels indirects.

| Mode | Temps | Par rapport à l'interpréteur |
|---|---|---|
| `interpreter` | 67,1 s | 1 |
| `cached` | 54,3 s | 1,24× |
| `jit_exact` | 75,8 s | 0,89× |
| `jit_fast` | 21,9 s | 3,1× |
| `jit` | 8,7 s | 7,7× |

Le binaire iOS n'a pas tourné sur iPhone : à mesurer avec les lignes `[rb-jit]`.

### Gel de la 828 et rendu (section 15 du document d'architecture)

Banc refait pour cette vérification, toujours manuel et non livré :
- cœur Linux AArch64 compilé avec clang, `char` signé et le choix de registres d'Apple (`x23` à la place de `x18`,
  comme `__APPLE__` dans `arm64_emit.cpp`), sous qemu-aarch64, arène memfd vue en RW et en RX ;
- 45 homebrews DS publics qui démarrent (exemples de dsgmLib, dont quatre en 3D, tutoriels libnds, rockwrestler) ;
- variante du cœur avec contrôles de bornes (`-fsanitize=bounds-strict,null`, `_GLIBCXX_ASSERTIONS`) et un contrôle
  des tables du JIT après chaque bloc ;
- cœur x86-64 natif sans SIMD pour les mesures et pour ThreadSanitizer ; horloge figée (`LD_PRELOAD`), car plusieurs
  homebrews tirent leurs nombres aléatoires de l'horloge émulée.

| Vérification | Résultat |
|---|---|
| 828, `jit`, variante contrôlée | Table du JIT écrasée dès le premier homebrew 3D : après le bloc Thumb `STMIA r3!,{r0}` à `0x02020DB0` (boucle de mise à zéro), `jit_page_chunks[0]` vaut zéro ; plantage à la remise à zéro suivante des tables |
| Correctif, `jit`, variante contrôlée, 4 homebrews 3D, état sauvegardé puis rechargé | Aucune écriture hors table, aucun plantage |
| Correctif, `jit` contre `interpreter`, 45 homebrews, 240 images | 44 dernières images identiques, 1 écart de minutage (affichage de texte en cours), aucun plantage |
| Rendu, x86-64 et AArch64, ×1 à ×10, 1 à 4 fils et `auto`, 4 scènes | Images et son identiques à ceux du cœur de la 828 |
| ThreadSanitizer, 4 fils, ×3 | Aucune course nouvelle (reste celle des compteurs d'usage du cache de textures, déjà dans le cœur) |

Temps d'une image de la scène 3D « Galaxy » (dsgmLib), interpréteur, Xeon 2,1 GHz à 4 processeurs virtuels. Ce ne
sont pas des mesures iPhone :

| Résolution interne | Cœur de la 828 (1 fil, réglage livré) | Ce cœur (`auto` : 4 fils) |
|---|---|---|
| ×1 (256×192) | 4,2 ms | 3,8 ms |
| ×3 (768×576) | 8,7 ms | 7,9 ms |
| ×5 (1280×960) | 22,1 ms | 10,9 ms |
| ×10 (2560×1920) | 82,6 ms | 29,5 ms |

Avec 4 fils réglés à la main, le cœur de la 828 mettait 45,4 ms en ×10.

### Suréchantillonnage 3D et mesures (section 16 du document d'architecture)

Ligne du journal du cœur, toutes les 600 images (environ 10 s), temps moyens en millisecondes par image :

```
[rb-perf] desmume frames=600 fps=… res=WxH ss=K threads=N jit=0|1 ms/frame run=… max=… emu=… cpu=… 2d=… 3d=…
          wait=… out=… host=… raster=… resolve=… engA=… engB=… end=… over16=N over33=N
```

- `run` : `retro_run` en entier ; `max` : la plus longue des 600.
- `emu` : `NDS_exec` ; dedans, `2d` (moteurs 2D, attentes de la 3D retirées), `3d` (lancement du rendu 3D sur ce
  fil), `wait` (ce fil attend les fils du rastériseur, moyenne du suréchantillonnage comprise) et `cpu` (le reste :
  CPU émulés et autre matériel).
- `out` : conversion des deux écrans par le frontend ; `host` : appel vidéo de l'hôte (envoi et présentation).
- `raster` : temps de travail cumulé de tous les fils du rastériseur ; `resolve` : moyenne du suréchantillonnage,
  faite bande par bande par ces fils (comptée dans `raster`).
- `engA`, `engB`, `end` : parts de `2d`, les lignes du moteur principal (celui qui compose la 3D), celles du moteur
  secondaire et la fin d'image (agrandissement à la taille interne, post-traitement des écrans).
- `over16`, `over33` : images des 600 dont `retro_run` a dépassé 16,7 ms (une image à 60 Hz manquée) et 33,3 ms.

Banc (x86-64 à 2,1 GHz, 4 processeurs virtuels, interpréteur, scène « Galaxy », `threads=4`) :

| Réglage | fps | run | 2d | wait | out | raster |
|---|---|---|---|---|---|---|
| ×10 | 48,9 | 20,45 | 5,83 | 6,16 | 5,07 | 39,28 |
| ×5 + 3D 2x | 59,5 | 16,80 | 1,86 | 8,93 | 2,73 | 36,46 |
| ×4 + 3D 2x | 78,2 | 12,78 | 1,31 | 6,04 | 2,06 | 25,16 |
| ×5 | 118,1 | 8,46 | 1,71 | 0,95 | 2,44 | 10,95 |

Fidélité, écran du haut à la 400ᵉ image, PSNR par rapport à l'image ×10 réduite par moyenne 2×2 : ×5 + 3D 2x
contre ×5 seul, 42,6 contre 35,6 dB (MarioKart de dsgmLib), 48,0 contre 41,7 dB (MD2), 45,8 contre 45,2 dB (Galaxy).
L'écran 2D est identique au bit près. Avec `disabled`, images et son identiques au cœur de la 829 (cinq réglages,
1 à 4 fils et `auto`, ×1 à ×10) ; en JIT AArch64, mêmes dernières images que l'interpréteur, options basculées en jeu,
état sauvegardé puis rechargé.

### 3D pendant la composition 2D (section 16.5)

DeSmuME lance la 3D à la ligne 262 (fin de la période sans affichage) et le moteur 2D en a besoin à la ligne 0 :
avant ce changement, la 3D ne recouvrait que la sortie du frontend et l'envoi à l'hôte, et le fil d'émulation
attendait le reste. Elle se dessine désormais aussi pendant la composition des lignes 0 à 191.

Banc (mêmes conditions, sans le hachage d'image du banc, `threads=4`, deux séries) :

| Réglage | fps avant | fps après | run avant | run après | wait avant | wait après |
|---|---|---|---|---|---|---|
| ×5 + 3D 2x | 42,0–47,8 | 57,5–65,4 | 20,9–23,8 | 15,3–17,4 | 12,6–13,3 | 7,3–8,9 |
| ×4 + 3D 2x | 58,3–58,4 | 82,5–94,2 | 17,1 | 10,6–12,1 | 9,1–9,3 | 3,6–4,6 |
| ×10 | 31,3–38,7 | 40,5–46,2 | 25,8–32,0 | 21,7–24,7 | 8,2–10,8 | 2,4–2,6 |
| ×5 | 90,6–99,1 | 109,6–124,4 | 10,1–11,0 | 8,0–9,1 | 1,6–2,0 | 0,4 |

Images et son identiques au bit près à ceux du cœur précédent :
- 50 homebrews en ×5 + 3D 2x, sur x86 ;
- 5 homebrews 3D × 4 réglages (×2 à ×10, 3 et 4 fils), plus ×1 ;
- contours et brouillard forcés : 4 homebrews × 3 réglages ;
- état sauvegardé puis rechargé, réglages changés en jeu, remise à zéro, rechargement du jeu ;
- AArch64 sous qemu, JIT et interpréteur, conversion NEON comprise (8 cas).

ThreadSanitizer ne signale que l'écriture concurrente, par plusieurs fils du rastériseur, de compteurs de statistiques
de texture (`TextureStore::ResetCacheAge`, `IncreaseCacheUsageCount`), du code de DeSmuME que ce changement ne
touche pas.

### Capture de la 3D, composition 2D en NEON, mesures (section 16.6)

- **Capture directe de la 3D.** Une ligne capturée avec la 3D seule pour source (`DISPCAPCNT`, source A = 3D)
  attendait toute l'image 3D, puis sa conversion entière en 15 bits : le chemin progressif ne servait pas aux jeux
  qui capturent la 3D (3D sur les deux écrans, effets). Elle attend désormais ses seules bandes et convertit ses
  seules lignes (`RenderFlush16Lines`) ; `RenderFlush` convertit ensuite les lignes restantes.
- **Composition 2D en NEON.** Les voies SSE2 des moteurs 2D de DeSmuME (`GPU.h`, `GPU.cpp` et les quatre aides de
  conversion qu'elles appellent) servent aussi sur AArch64 : `RB_GPU_SSE2`, défini dans `types.h`, les choisit, et
  `utils/rb_sse2neon.h` écrit en NEON les 49 instructions SSE2 qu'elles emploient. Le reste du cœur garde ses voies
  C++ sur AArch64 ; le rastériseur reste celui qui suréchantillonne.
- **Fils du rastériseur** une classe de qualité de service sous le fil d'émulation (`QOS_CLASS_USER_INITIATED`,
  Apple seulement) : quand la 3D se dessine pendant la composition, le fil qui compose garde son cœur.
- **Mesures** ajoutées à la ligne `[rb-perf]` : `r3d` (rendus 3D), `bands` (rendus par bandes), `bwait` (attentes
  bloquantes d'une bande), `cap` et `cap3d` (images avec une capture, et avec une capture directe de la 3D), `ecpu`
  (temps CPU du fil d'émulation par image), `rcpu` (temps CPU des fils du rastériseur par image, à comparer à
  `raster`, leur temps mural), `t3d` (durée murale d'un rendu par bandes, de son départ à sa dernière bande).
- **Pont** : les lignes `[rb-perf]` et `[rb-jit]` du cœur entrent dans `session.log` au fil de l'eau (`core: …`,
  400 au plus par session), même quand l'app est fermée depuis le sélecteur.

Banc x86 (4 processeurs virtuels, deux séries ; les voies SSE2 elles-mêmes, que la couche NEON reproduit) :

| Cas | Avant | Après |
|---|---|---|
| ×5, `engA` (moteur qui compose la 3D), Galaxy | 1,89–1,90 ms | 1,02–1,07 ms |
| ×5, `engA`, MarioKart | 1,54–1,62 ms | 0,98–1,16 ms |
| ×5, i/s, Galaxy | 126,6–128,6 | 143,6–144,2 |
| ×5 + 3D 2x, capture directe de la 3D forcée, i/s, Galaxy | 51,2–56,6 | 59,4–61,0 |
| ×5 + 3D 2x, idem, `wait`, Galaxy | 11,3–12,4 ms | 9,2 ms |

Un écran sans 3D (LargeBackground) ne change pas : les voies vectorielles servent surtout à la composition à la
résolution interne. Trois fils au lieu de quatre sur ce banc de quatre processeurs : 45–47 contre 51–57 i/s (Galaxy),
109–119 contre 126–131 (MarioKart) ; `auto` garde donc un fil par cœur.

Vérifications :
- la couche NEON, instruction par instruction : 281 048 résultats identiques à ceux de la vraie SSE2 (entrées
  aléatoires et limites, tous les décalages de 0 à 255, les 256 valeurs de chaque permutation) ;
- sur x86, composition SSE2 seule contre composition C++ : images et son identiques (4 homebrews, ×1 et ×5) ;
- capture forcée par un code de triche interne (VRAM D en LCDC, `DISPCAPCNT` = 3D seule vers D, puis affichage de
  D) : sur x86, 75 cas identiques au cœur de la 831 (5 homebrews × sans capture, capture, capture affichée × 5
  réglages de ×1 à ×5 + 3D 2x, 1 à 4 fils) ;
- sur AArch64 sous qemu, JIT, composition NEON comprise : 39 cas identiques au cœur de la 831 (10 homebrews 2D en
  ×1 et ×4, 5 homebrews 3D en ×1, ×3 et ×5 + 3D 2x, capture affichée sur 2 homebrews) ;
- le correctif s'applique aux sources épinglées et redonne exactement l'arbre testé.

## Limites connues

- **`jit` (T).** Temps du fetch non compté et entrelacement des deux CPU par bloc : le temps émulé diffère un peu
  de l'interpréteur. QADD, QSUB, QDADD, QDSUB et BKPT passent par l'interpréteur.
- **`jit_exact`.** Quand les deux CPU tournent en même temps, il rend la main à l'autre CPU presque à chaque
  instruction, comme l'interpréteur : c'est un mode de compatibilité, pas de vitesse.
- **JIT RewindBox.** Les accès mémoire, multiplications, décalages par registre et LDM/STM passent encore par le
  gestionnaire de l'interpréteur ; les drapeaux sont réécrits dans CPSR à chaque instruction. C'est ce qui le
  sépare encore du JIT de T.
- **Mémoire.** Table d'environ 32 Kio par page de 16 Kio où du code a tourné ; blocs de l'interpréteur en cache
  plafonnés à 24 Mio, puis oubliés.
- **Haute résolution interne.** Le rendu reste logiciel. En ×10, la 3D, sa composition et la sortie traitent
  4,9 millions de pixels par écran et par image : la fluidité dépend de la scène, et rien n'est mesuré sur iPhone.
  Restent sur le fil d'émulation : la composition de la couche 3D et des couches 2D au-dessus d'elle, et
  l'agrandissement de l'écran sans 3D. Un rendu 3D par le GPU demanderait le moteur OpenGL ES 3 de T
  (`OGLRender_ES3.cpp`), que le fork libretro n'a pas.

## Licences

- Fichiers DeSmuME, JIT AArch64 de T et fichiers `rb_*` de RewindBox : GPLv2 ou ultérieure.
- `arm_jit.h` : GPLv3 ou ultérieure.
- En-tête ABI : MIT.

Le binaire avec `HAVE_JIT` est donc distribué sous GPLv3. `libretro_source_cores.py` réécrit la ligne du cœur
dans `LIBRETRO_CORES.txt` et l'identité porte `GPLv3`.

## Compilation (macOS, Xcode)

```sh
# arbre libretro/desmume à 95b4d798, plus les trois fichiers de TASEmulators/desmume à b549f71b
git apply native/desmume/arm64-jit-abi.patch
mkdir -p desmume/src/frontend/libretro/rewindbox
cp …/RewindBoxLibretroJit.h desmume/src/frontend/libretro/rewindbox/
cd desmume/src/frontend/libretro
SOURCE_DATE_EPOCH=1795306701 make -f Makefile.libretro platform=ios-arm64 DESMUME_JIT_A64=1 IOSMINVER=14.0
strip -x desmume_libretro_ios.dylib
```

`build-utils/libretro_source_cores.py --cores …,desmume` fait la même chose et vérifie chaque empreinte, les
exports et les imports interdits. Il installe le binaire dans la collection avec `jitInterface: 1` et
`jitArenaBytes` (64 Mio depuis la section 16 : Animal Crossing en avait rempli 25,4 Mo sur 32 en 48 s).
