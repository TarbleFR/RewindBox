# DeSmuME (95b4d798) : JIT AArch64 avec l'interface JIT de RewindBox

Cœur libretro [libretro/desmume@95b4d798](https://github.com/libretro/desmume/tree/95b4d798731caa809125b6c3c11d17cc332ff6ef)
(tête de `master`, la révision des binaires buildbot livrés jusqu'ici), complété par le JIT AArch64 de l'équipe
DeSmuME, que le fork libretro n'a jamais importé, puis corrigé et branché sur
`packages/libretro_internal_bridge/ios/Classes/RewindBoxLibretroJit.h`. S'y ajoutent les étapes 1 à 4 de
[docs/desmume-arm64-jit-architecture.md](../../docs/desmume-arm64-jit-architecture.md) (sections 13 et 14) :
couche commune, interpréteur en cache, JIT RewindBox à appels puis natif ; puis (section 15) le correctif du gel
de l'IPA 828 et un rendu plus rapide en haute résolution interne.

## Ce que la compilation assemble

1. **Fichiers importés** (`importFiles` de `source.json`) : `desmume/src/utils/arm_jit/arm_jit_arm.cpp`,
   `emit_core.cpp` et `arm64_emit.cpp` de
   [TASEmulators/desmume@b549f71b](https://github.com/TASEmulators/desmume/tree/b549f71b83287f265b6d74b9e77ef5d98a617190),
   pris à cette révision et vérifiés par SHA-256. `arm_emit.cpp` (ARM 32 bits) n'est pas pris.
2. **Correctif** `arm64-jit-abi.patch` (20 fichiers, +3 048/−241), un `git diff` contre l'arbre libretro plus ces
   trois fichiers d'origine. Il crée `utils/arm_jit/rb_cached.cpp`, `rb_a64.h` et `rb_jit.cpp`, et modifie aussi le
   rendu (`rasterize.cpp`, `rasterize.h`, `GPU.cpp`) et la sortie du frontend.
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
| Rastériseur logiciel (`rasterize.cpp`, `rasterize.h`) | Effacement plan par plan (`std::fill_n`, `memset`) au lieu d'un appel par pixel. Avec des fils : l'image est découpée en tranches de groupes de lignes entrelacés (quatre tranches par fil) que les fils prennent à un compteur commun, au lieu d'une bande fixe par fil ; chaque fil efface une tranche juste avant de la dessiner. À la résolution de la console, le fil d'émulation dessine lui-même, comme sans fils. L'image ne change pas. |
| Composition de la couche 3D (`GPU.cpp`) | Chemin sans appel ni branchement pour le cas courant (copie simple, image 15 bits, pas de fenêtre), que le compilateur vectorise. Mêmes pixels que `_PixelCopy`. |
| Sortie du frontend (`libretro.cpp`) | À partir de 512×384, la conversion en RGB565 des deux écrans est partagée avec trois fils d'aide. |
| `desmume_num_cores` | Nouvelle valeur `auto`, valeur par défaut : un fil de rastériseur par cœur de l'appareil (8 au plus). |

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
`jitArenaBytes` (32 Mio).
