# DeSmuME : architecture d'un JIT AArch64 pour RewindBox

*23 novembre 2026 — branche `Claude`. **Étapes 0 à 4 réalisées** (sections 13 et 14) : JIT AArch64 de T sur
l'ABI, couche commune, interpréteur en cache, JIT RewindBox à appels puis natif, dans `native/desmume`, vérifiés
hors appareil ; rien mesuré sur iPhone. Décisions du mainteneur : « DS : garder DeSmuME, soit inventif et conçois
l'architecture », « fini de concevoir l'architecture JIT pour la DS », « vas jusqu'au bout », puis « fini toute les
étapes de l'architecture pour le JIT ». Sources relues : libretro/desmume `95b4d798` (**L**), TASEmulators/desmume
`b549f71b` (**T**), melonDS `ff972523`, oaknut `94c726ce`. Les chiffres de gain sont des estimations ou des
affirmations d'auteurs, jamais des mesures RewindBox.*

*Les sections 1 à 6 posent l'architecture. Les sections 7 à 12 la rendent directement réalisable avec ce qui existe
désormais dans RewindBox, livré ou prêt à l'être :*
- *l'ABI `RewindBoxLibretroJit.h` v1 et l'arène préparée par StikJIT ;*
- *l'aide `LibretroJITHelper.appex`, déclenchée par l'identité de la collection ;*
- *la route `build-utils/libretro_source_cores.py` ;*
- *la table des collections revues `.github/diagnostics/libretro_source_collections.py`.*

*Elles reprennent aussi les leçons d'Azahar 2127.0-rc5 et de Beetle/Lightrec.*

## En bref

- **Le cœur libretro n'a pas de JIT AArch64.** L'émetteur x86 dépend d'AsmJit (x86 seul). `utils/arm_arm` produit
  du code ARM 32 bits, qu'aucun iPhone récent n'exécute ; il est incomplet et alloue de la mémoire RWX.
- **Un JIT AArch64 existe pourtant en amont.**
  - Il est dans **T** (`utils/arm_jit/`, environ 7 900 lignes, GPL-2.0-or-later), publié en 2022 et mis à jour
    en août 2026. C'est le choix par défaut des builds ARM Linux et Apple Silicon de DeSmuME.
  - Le fork libretro ne l'a jamais importé.
  - Son code est relocalisable : adresses absolues en `movz/movk` + `blr`, étiquettes relatives. Il est écrit dans
    un tampon ordinaire puis copié dans la zone exécutable : il se branche donc sur notre ABI en copiant dans
    l'alias RW et en renvoyant l'adresse RX.
  - Il hérite des défauts de l'émetteur x86 : tickets amont #997, #998 et #1002 de novembre 2026, avec un banc
    différentiel de 81 920 cas.
- **Architecture proposée : un front-end de blocs commun, trois exécutions, l'interpréteur comme référence.**
  - **A. Interpréteur en cache**, sans mémoire exécutable : pour tous les joueurs, même sans StikJIT.
  - **B. Code AArch64 « à appels »** : chaque instruction appelle le gestionnaire de l'interpréteur.
    Sémantique et cycles identiques par construction.
  - **C. Code natif** pour les classes d'instructions chaudes.
  - Le code est écrit avec oaknut (MIT, déjà dans Azahar via dynarmic) dans l'alias RW de l'arène RewindBox.
- **Gains attendus sur la part CPU** (estimations) : A 1,15–1,6× ; B 1,3–2× ; C 3–6×. La reprise de T (étape 0) :
  1,1–1,5× selon son auteur.
- **Effet sur l'upscaling.** La 3D logicielle et la composition 2D de DeSmuME croissent avec le carré du facteur ;
  le coût CPU de l'émulation, lui, n'en dépend pas.
  - Le JIT apporte environ un cran de résolution interne (par exemple ×2 → ×3), pas ×4 et au-delà.
  - Deux leviers voisins, indépendants du JIT :
    - `desmume_num_cores`, threads du rastériseur, à 1 par défaut et non réglé par RewindBox ;
    - le portage des chemins NEON de T (composition 2D, conversion des couleurs), annoncés jusqu'à +50 % sur
      Apple Silicon.

## 1. Ce qui existe

| Élément | État | Réutilisable |
| --- | --- | --- |
| Interpréteur L (`armcpu_exec`, tables `arm_instructions_set[2][4096]` et `thumb_instructions_set[2][1024]`, gestionnaire `u32 OpFunc(u32)`) | Référence de comportement et de cycles (`max(exécution, fetch)` avec `advanced_timing`) | Oui : appelé tel quel par B et par les replis de C |
| Cadre JIT commun L (`JIT_COMPILED_FUNC`, table de correspondance par demi-mot, crochets d'écriture MMU, `arm_jit_sync`, appels de remise à zéro) | Fonctionnel, mais la table coûte environ 72 Mio de mémoire sale ; l'invalidation par entrée laisse du code périmé dans un bloc commencé plus tôt ; les remappages VRAM et WRAMCNT ne sont pas suivis | API et points d'appel oui ; table et invalidation à refaire |
| JIT x86 L (`arm_jit.cpp`, 4 472 lignes) | Modèle de structure le plus complet ; défauts de cycles (#998) et de DMA (#997) | Structure seulement |
| JIT ARM32 L (`utils/arm_arm`) | 52 % des entrées ARM et 87 % des entrées Thumb ; cycles marqués « TODO » ; ne s'exécute pas en AArch64 | Non |
| JIT AArch64 T (`utils/arm_jit/`) | Fonctionnel en amont, défauts connus (#1002 : UMLAL émis comme SMADDL, SMLAWT, carry d'`ASR #0` en Thumb) ; utilise `MAP_JIT` et `pthread_jit_write_protect_np` | Oui, pour une reprise rapide (étape 0) |
| melonDS `ARMJIT_A64` | Excellente référence (ALU et drapeaux, cache de registres, invalidation par plages), mais modèles mémoire, cycles et ordonnanceur différents | Comme référence et code à porter par morceaux, pas en bloc |

## 2. Architecture

```text
retro_run → NDS_exec → matériel, IRQ → armInnerLoop (inchangé)
               jit_exec<P> : table compacte[P][instruct_adr] ── trouvé ──► entrée RX ─► bloc ─┐
                  │ absent : front-end (décodage, attributs, sorties, coûts de fetch)         │
                  ├─► A : interpréteur en cache (tableau de gestionnaires, mémoire ordinaire) │
                  ├─► B : code « à appels » ─┐ oaknut écrit par l'alias RW, flush(RX),        │
                  └─► C : code natif ────────┘ allocation dans l'arène RewindBox              │
               ◄── cycles, instruct_adr = PC suivant ────────────────────────────────────────┘
crochets d'écriture MMU → invalidation par plage (bitmap de code, listes par 512 octets)
NDS_Reschedule, armement DMA, freezeBus, Wait4IRQ, emu_halt → drapeau d'arrêt vérifié
après les instructions à effet de bord
```

### 2.1 Couche commune

- **Table de correspondance compacte.**
  - Décalages 32 bits dans l'arène au lieu de pointeurs 64 bits, en pages à deux niveaux allouées à la demande :
    environ 10,7 Mio au pire en mode DS, au lieu de 72 Mio.
  - Une table par CPU, avec une étiquette Thumb/CPU vérifiée à la lecture.
  - Effacée par la liste des pages utilisées, jamais par un `memset` global.
- **Invalidation précise.**
  - Bitmap de code à 16 octets et listes de blocs par 512 octets.
  - Les douze points de crochet existants appellent `jit_invalidate(addr, size)`.
  - Nouveaux crochets dans `MMU_VRAMmapControl` et WRAMCNT.
  - Chaque entrée de code commence par une instruction de garde, remplacée via l'alias RW par un saut vers
    l'invalidation. Un code périmé ne s'exécute donc jamais, même plus loin dans le bloc en cours.
- **PC non mappé** : un pas d'interpréteur, au lieu de `execute=false`.
- **`arm_jit_sync` sans effet de bord.**

### 2.2 A. Interpréteur en cache (sans StikJIT)

- **Principe.** Chaque bloc est un tableau `{fonction, opcode, pc, condition, drapeaux, coût de fetch}`. Une boucle
  C++ l'exécute avec les mêmes règles de sortie, d'arrêt et de budget que B, et on peut y entrer à n'importe
  quelle instruction.
- **Pour qui.** Aucune mémoire exécutable : c'est l'apport pour tous les joueurs sans LocalDevVPN.
- **Ce qu'il économise.** Le décodage de DeSmuME est déjà une seule lecture de table ; le gain vient du fetch, du
  calcul de cycles et du travail de l'ordonnanceur évités à chaque instruction.
- **Taille** (estimation) : 500 à 900 lignes.

### 2.3 B. Code « à appels » (étape 1)

Pour chaque instruction, le bloc appelle directement le même gestionnaire que l'interpréteur
(`arm_instructions_set[P][INSTRUCTION_INDEX(op)](op)` ou `thumb_instructions_set[P][op>>6](op)`). Il n'appelle
jamais `armcpu_exec` ni `OP_DECODE`, qui refont le fetch.

- **Condition ARM.** Testée en natif : les bits NZCV de CPSR[31:28] et d'A64 ont les mêmes positions, la même
  convention de retenue et les mêmes codes de condition. La condition 0xF se décide à la compilation.
- **Cycles.** La valeur de retour du gestionnaire, plus `max(exécution, MMU_codeFetchCycles)` avec
  `advanced_timing`, dans le même ordre que l'interpréteur.
  - D'abord un appel d'aide par instruction.
  - Ensuite, les fetchs séquentiels sont repliés à la compilation : seuls les franchissements de ligne de cache
    de l'ARM9 et le fetch de sortie passent encore par l'aide.
- **Sorties.**
  - Toujours après SWI, MSR, MCR/MRC, UND/BKPT/coprocesseur, LDM^/STM^.
  - Vérification du drapeau d'arrêt après chaque accès mémoire : cela corrige la classe de bugs du #997.
- **Mode exact.** Une instruction par passage : la suite d'appels de gestionnaires est alors identique à celle de
  l'interpréteur. C'est le mode de vérification pas à pas.
- **Mode rapide.** Un passage par bloc, puis chaînage des blocs sous un budget de cycles.
- **Taille** (estimation) : 900 à 1 600 lignes.

### 2.4 C. Code natif (étape 2)

- **Registres.**
  - x19 = `&armcpu_t` ; x28 = contexte du CPU (bases mémoire, région DTCM, budget, drapeau d'arrêt, cycles).
  - R0 à R15 par paires dans x20 à x27, dans l'ordre de `armcpu_t::R`. Sauvegarde en quatre `STP`, rechargement en
    quatre `LDP`.
  - Un registre impair coûte une instruction de plus en lecture, chaque écriture une de plus.
  - Apple réserve x18 et x29 reste le pointeur de cadre : seize registres séparés sont impossibles.
- **Drapeaux.**
  - NZCV de l'invité dans NZCV de l'hôte, recopiés à la demande dans CPSR ; ADDS, SUBS, ADCS et SBCS
    correspondent un pour un.
  - Les opérations logiques S prennent C du décaleur et gardent V : `RMIF` si FEAT_FlagM est présent (détecté par
    `sysctl`, absent des A12), sinon `MRS`/`BFI`/`MSR`.
  - Une analyse de vivacité des drapeaux supprime l'essentiel du travail sur C et V.
- **Mémoire.**
  - Chemins rapides en ligne, sans toucher aux drapeaux. ARM9 : DTCM, puis RAM principale, puis ITCM.
    ARM7 : RAM principale, puis WRAM exclusive. C'est l'ordre de `MMU.h`.
  - Les écritures vérifient le bitmap de code.
  - La temporisation exacte (`m_lastAddress`, cache de données) est calculée en ligne.
  - Le chemin lent passe par des aides qui appellent `_MMU_read32<P>` et `MMU_aluMemAccessCycles`.
- **Autres classes.**
  - MUL et MLA avec cycles calculés en ligne.
  - B/BL/BLX chaînés ; BX et `LDR PC` par recherche dynamique.
  - MRS natif, MSR en repli suivi d'une sortie.
  - Tout le reste : repli vers le code « à appels » de B.
- **Taille** (estimation) : 5 000 à 7 500 lignes.

### 2.5 Arène, état et options

- **Installation.** `rewindbox_libretro_jit_install` copie l'ABI, puis fait aussitôt un seul `allocate` de toute
  la capacité préparée (32 Mio par défaut, section 7.2). Ce bloc dure jusqu'à la fermeture du cœur. L'hôte appelle
  cette fonction juste après `dlopen`, avant `retro_set_environment` et `retro_init`, donc avant toute option.
- **Remises à zéro.** `NDS_Reset` et le chargement d'un état ne font que rembobiner les pointeurs.
- **Arène pleine.** Un drapeau est levé ; le vidage n'a lieu qu'à un point sûr du distributeur (aucun bloc JIT sur
  la pile). Jamais de `munmap` ni de `mprotect`.
- **États.** L'état du JIT n'est jamais sérialisé : `arm_jit_sync` avant la sauvegarde, et les fichiers sont
  identiques entre les modes.
- **Codes de triche** (`retro_cheat_set`, moteur Action Replay via `_MMU_write*`). L'invalidation précise rend
  inutile la remise à zéro globale de `cheatSystem.cpp:1041-1049`, qui viderait tout le JIT à chaque image tant
  qu'une valeur de triche change.
- **Options.**
  - Règle : `use_jit = mode jit && GET_JIT_CAPABLE && ABI installée && arène allouée`.
  - L'interpréteur en cache devient une valeur à part de `desmume_cpu_mode`, pour que la surcharge sans JIT de
    l'app (`interpreter`) puisse choisir le chemin le plus rapide.
  - Bascule permise entre deux images, avec synchronisation.

## 3. Plan

| Étape | Contenu | Taille (estimation) | Gain CPU (estimation) |
| --- | --- | --- | --- |
| 0. Reprise de T | `utils/arm_jit` de T branché sur l'ABI : copie dans l'alias RW, retour de l'adresse RX, ni `MAP_JIT`, ni `munmap`, ni bascule W^X ; table compacte ; correctifs #997, #998 et #1002. Cœur compilé depuis la source (règle aussi la provenance de DeSmuME, encore « non résolue ») | 300 à 800 lignes changées, environ 7 900 importées | 1,1–1,5× |
| 1. Couche commune | Table compacte, invalidation précise, crochets VRAM et WRAMCNT, arrêts | 1 800 à 2 800 | — |
| 2. A. Interpréteur en cache | Sans StikJIT | 500 à 900 | 1,15–1,6× |
| 3. B. Code « à appels » | Mode exact et mode rapide | 900 à 1 600 | 1,3–2× (rapide) |
| 4. C. Code natif | Registres, drapeaux, mémoire, multiplications, LDM/STM, branchements, vivacité | 5 000 à 7 500 | 3–6× |
| Outils de développement | Banc différentiel instruction par instruction (comme #998) et empreintes d'images rejouées | 800 à 1 500 | — |

- **Ordre conseillé.** L'étape 0 vient d'abord : elle prouve la chaîne de l'ABI et donne les premières mesures
  sur iPhone pour un faible coût. Le chantier complet suit, dans l'ordre 1 → 2 → 3 → 4.
- **Durée** (estimation) : environ 2 à 3 mois jusqu'à une étape 3 utilisable, 6 à 9 mois jusqu'à l'étape 4.
- **Gain réel par image** : `1/((1−f)+f/S)`, où f est la part de l'émulation CPU dans le temps d'une image, non
  mesurée. Exemple : f = 0,6 donne 1,43× pour S = 2 et 1,92× pour S = 5.
- **Le banc différentiel reste un outil manuel.** AGENTS.md exclut les nouvelles suites de tests automatiques
  pour les cœurs, sauf décision contraire du mainteneur.

## 4. Avant de coder : mesurer

- **Intervalles à relever** (`os_signpost`) : `armInnerLoop`, `GPU->RenderLine`, `RenderGeometry`, l'attente
  `RenderFinish` et la copie de sortie.
- **Conditions** : résolution interne ×1, ×2, ×3 et ×4, avec `desmume_num_cores` à 1 puis à 3.
- **Ce qu'on en tire** : la part f de l'émulation CPU, qui décide de l'ordre des chantiers.
- **Levier simple à essayer en parallèle** : `desmume_num_cores` à 2 ou 3. Le découpage en bandes est statique ;
  quatre threads peuvent être plus lents sur deux cœurs performants et quatre cœurs efficaces. Un changement de
  valeur par défaut demande une validation sur iPhone.

## 5. Risques

1. **Entrelacement ARM9/ARM7 plus grossier.** Des jeux peuvent casser, comme avec la taille de bloc actuelle.
   Parades : mode exact, quantum d'entrelacement, arrêts après les instructions à effet de bord.
2. **L'interpréteur de référence a ses propres défauts**, par exemple `OP_NEG` indéfini à INT_MIN (#1002).
3. **Mémoire.** La table actuelle coûte environ 72 Mio. Le code automodifiant et les overlays peuvent provoquer
   des vidages en rafale : garder le repli après huit recompilations.
4. **Code périmé après un remappage VRAM ou WRAM**, tant que les nouveaux crochets manquent.
5. **Contraintes d'ABI.**
   - x18 est réservé par Apple et x29 reste le pointeur de cadre.
   - Cœurs arm64 sans PAC (pas arm64e).
   - Aucune exception C++ ne doit traverser un bloc JIT ; aucune n'a été trouvée dans les chemins CPU et MMU.
6. **Licences.** Les fichiers JIT de L sont GPL-3.0-or-later, ceux de T GPL-2.0-or-later. Tout binaire avec
   `HAVE_JIT` est en pratique GPLv3+, ce qui est compatible avec RewindBox.
7. **Rien n'est mesuré.** Une compilation réussie ne prouve pas qu'un jeu fonctionne sur iPhone.

## 6. Points d'intégration dans L

- **Compilation.** `Makefile.libretro:214-245` (iOS) : `DESMUME_JIT_A64` définit `-DHAVE_JIT` sans AsmJit.
  `Makefile.common:123-165` : nouvelles sources et chemin d'en-têtes d'oaknut.
- **Frontend libretro.** `frontend/libretro/libretro.cpp` : symbole d'installation, options (722-751) et leur
  visibilité (2349-2354).
- **CPU.**
  - `arm_jit.h` : nouvelle table derrière la même API ;
  - `armcpu.cpp:719-745` : distributeur et `arm_jit_sync`.
- **Système et ordonnancement.** `NDSSystem.cpp` : 1617-1621, 1882-1953, 2370-2375, 2609-2611, et `emu_halt`.
- **Mémoire.** `MMU.h` et `MMU.cpp` : crochets d'écriture, `MMU_VRAMmapControl` (791), WRAMCNT (3658), freezeBus
  (2353, 4380).
- **Triche et états.** `cheatSystem.cpp` (98-124, 1041-1049) ; `saves.cpp` (985-987).
- **Nouveaux fichiers.** `utils/arm64_jit/*` : arène, table, front-end, invalidation, distributeur, interpréteur
  en cache, émetteurs, aides.
- **Côté RewindBox.** Voir la section 10 :
  - taille de l'arène dans l'épingle, donc dans l'identité de la collection, et non dans le catalogue ;
  - surcharges sans JIT ;
  - réglage visible par jeu ;
  - route de compilation depuis la source, comme Azahar et Beetle.

## 7. Étape 0 en détail : le JIT de T sur l'ABI RewindBox

### 7.1 Ce qui est importé, et ce qui ne l'est pas

- **Fichiers repris de T `b549f71b` (GPL-2.0-or-later).**
  - `utils/arm_jit/arm_jit_arm.cpp`, 4 374 lignes. Il inclut lui-même `emit_core.cpp` (231 lignes) et, en
    AArch64, `arm64_emit.cpp` (1 949 lignes).
  - `arm_emit.cpp`, l'émetteur ARM 32 bits (1 316 lignes), n'est pas compilé.
  - T compile `arm_jit_arm.cpp` à la place de `arm_jit.cpp` et d'AsmJit dès que la cible est ARM
    (`frontend/posix/meson.build:202-205`).
- **Ce qui ne change pas dans L.**
  - L'API `arm_jit.h` (`arm_jit_reset`, `arm_jit_sync`, `arm_jit_compile<P>`, `ArmOpCompiled`). Elle ne diffère
    de T que par la macro `FASTCALL`/`DESMUME_FASTCALL` : un `#define` de compatibilité suffit.
  - Les points d'appel du distributeur (`armcpu.cpp`).
- **Fonctionnement de T à garder en tête.**
  - La première exécution d'un bloc se fait dans l'interpréteur, pendant sa compilation
    (`arm_jit_arm.cpp:4105`).
  - **Chaque bloc est une fonction `u32 f()` qui rend ses cycles au distributeur C.** Il n'y a pas de chaînage :
    aucun code JIT n'est sur la pile pendant une compilation.
  - Si la copie échoue, `compile_basicblock` retombe sur `op_decode` (l'interpréteur) pour ce bloc
    (`arm_jit_arm.cpp:4127-4134`).
- **Déjà correct pour Apple dans T.**
  - x18, réservé par Apple, est remplacé par x23 (`arm64_emit.cpp:63-67`). Le prologue de chaque bloc sauvegarde
    x23 avec x19 à x24 (`save()`/`restore()`, `arm64_emit.cpp:1785-1800`).
  - Les adresses absolues passent par `movz/movk` + `blr`. Les sauts vers les étiquettes sont résolus dans le
    tampon avant la copie (`createFunc`, `emit_core.cpp:194-200`) : un bloc peut donc être copié n'importe où.
- **Ce qui est retiré.** `jit_write()`/`jit_exec()` (`pthread_jit_write_protect_np`, `arm_jit_arm.cpp:51-79`)
  deviennent vides : l'écriture passe par l'alias RW, l'exécution par la vue RX, sans bascule W^X.

### 7.2 Mémoire du code : une seule arène, jamais de `mmap` exécutable

Dans T (`emit_core.cpp`) :
- chaque bloc est d'abord assemblé dans des morceaux `malloc` de 24 192 octets ;
- `createFunc` le copie ensuite dans une zone de 40 000 000 octets projetée en RWX avec `MAP_JIT` ;
- au débordement, `armjitarm_alloc_func` appelle `arm_jit_reset(1)` en pleine compilation. Les tables sont
  vidées, `freeFuncs()` libère toutes les zones (`munmap`), puis une nouvelle zone est projetée
  (`emit_core.cpp:86-104`).

Ce vidage immédiat est sûr parce qu'aucun bloc n'est sur la pile pendant une compilation (section 7.1). Sur
l'ABI :

| T | Étape 0 |
| --- | --- |
| `alloc_executable_memory` : `mmap` RWX `MAP_JIT` (`emit_core.cpp:61-80`) | Supprimé. Un seul `allocate` de toute la capacité, à l'installation ; le bloc reste valide jusqu'à la fermeture du cœur |
| `armjitarm_alloc_func` : bump ; au débordement, `arm_jit_reset(1)` et nouvelle zone | Bump aligné sur 16 octets dans l'arène. Arène pleine : `arm_jit_reset(true)`, rembobinage (`used = 0`) et nouvel essai, comme T mais sans `munmap`. Un compteur de vidages est tenu. Un bloc plus grand que l'arène : `NULL`, donc l'interpréteur |
| `createFunc` : `memcpy` dans la zone, puis `sys_icache_invalidate` | `memcpy` dans `rw + used`, `abi->flush(rx + used, n)`, retour de `rx + used`. Aucun `sys_icache_invalidate`, `__clear_cache` ni `FlushInstructionCache` ne subsiste |
| `freeFuncs` : `munmap` de chaque zone | Rembobinage seulement |
| `allocBytes` et `allocNewBlock` : `exit(0)` si `malloc` échoue (`emit_core.cpp:119-132` et `164-171`) | Échec propagé, puis interpréteur pour ce bloc |

- **Vidage différé.** Le vidage à un point sûr du distributeur (section 2.5) ne devient obligatoire qu'avec le
  chaînage des blocs (B en mode rapide, C). À l'étape 0, le vidage immédiat de T suffit.
- **Taille.** 32 Mio par défaut, au champ `jitArenaBytes` de l'épingle.
  - T projette 40 Mo par zone, et une nouvelle zone à chaque vidage. Nous vidons une arène fixe et mesurons.
  - Les lignes `[rb-jit]` (section 9) diront s'il faut monter à 48 ou 64 Mio. Le plafond de l'hôte est 512 Mio
    (`LIBRETRO_JIT_MAX_CAPACITY`, `LibretroJitArena.h:28`).
- **Installation.** L'hôte appelle `rewindbox_libretro_jit_install(abi)`, exporté par
  `frontend/libretro/libretro.cpp`, juste après `dlopen`, avant `retro_set_environment` et `retro_init`. La
  fonction :
  - vérifie la version 1, `structBytes`, une page qui est une puissance de deux et une capacité suffisante ;
  - puis fait l'unique `allocate`.

  Sans installation, `CommonSettings.use_jit` reste faux quoi que demande l'option.
- **Règle d'activation**, reprise de la section 2.5 :
  `use_jit = (desmume_cpu_mode == "jit") && GET_JIT_CAPABLE && ABI installée && arène allouée`.
  - L'hôte ne répond `GET_JIT_CAPABLE = true` que si l'installation a réussi (`LibretroSession.m:917`,
    `LibretroCoreHost.m:731`).
  - L ne lit `desmume_cpu_mode` et `desmume_jit_block_size` qu'au premier démarrage
    (`check_variables(first_boot)`, `libretro.cpp:718-751`). Un changement s'applique donc au lancement suivant.

### 7.3 Correctifs fonctionnels inclus dans l'étape 0

- **#1002.**
  - UMLAL est émis comme SMADDL : corriger le signe.
  - SMLAWT : prendre la moitié haute.
  - Retenue d'`ASR #0` en Thumb : `ASR #32`, comme l'interpréteur.
  - `OP_NEG` à INT_MIN : aligner le JIT sur le résultat du matériel, et non sur l'indéfini du C.
- **#998.** Cycles : appliquer la règle `max(exécution, fetch)` de l'interpréteur avec `advanced_timing`, dans le
  même ordre.
- **#997.** Après chaque instruction d'accès mémoire, vérifier le drapeau d'arrêt (armement DMA, `NDS_Reschedule`,
  freezeBus) et sortir du bloc avec un état synchronisé.
- **Cache d'instructions de l'ARM9.** Les MCR p15, c7 (maintenance de cache) terminent le bloc et vident les blocs
  marqués (section 8).
- **Méthode.** Chaque correctif est vérifié au banc différentiel instruction par instruction (outil manuel, comme
  #998) avant d'être intégré.

### 7.4 Compilation par la route RewindBox

Épingle `native/desmume/source.json`, sur le modèle de `native/beetle-psx/source.json` :

| Champ | Valeur |
| --- | --- |
| `core`, `framework` | `desmume`, `desmume_libretro` |
| `upstream`, `sourceGit`, `revision` | `https://github.com/libretro/desmume`, révision `95b4d798`, à revalider sur `master` au moment du code |
| `patch`, `patchSHA256` | `native/desmume/arm64-jit-abi.patch` : import de T, adaptations des sections 7.1 à 7.3, frontend libretro, Makefile |
| `originalFilesSHA256` | Empreintes des fichiers de L que le correctif modifie |
| `abiHeaderInTree`, `abiHeaderCopied` | `desmume/src/frontend/libretro/rewindbox/RewindBoxLibretroJit.h`, `true` |
| `build` | `kind: make`, `directory: desmume/src/frontend/libretro` (le Makefile suppose `CORE_DIR := ../..`), `makefile: Makefile.libretro`, `make: [platform=ios-arm64, DESMUME_JIT_A64=1]`, `output: desmume/src/frontend/libretro/desmume_libretro_ios.dylib`, `strip: [-x]` |
| iOS minimum | 14.0, comme Azahar et Beetle. Pour `ios9` et `ios-arm64`, `Makefile.libretro:233-237` code 8.0 en dur dans `CC`, `CXX`, `CFLAGS` et `CXXFLAGS` : le correctif le remplace par `IOSMINVER ?= 14.0`. Beetle passe le sien en variable de make (`IPHONEMINVER`) |
| `expectedExports` | `_rewindbox_libretro_jit_install` et les `_retro_*` |
| `expectedStrings` | `desmume_cpu_mode`, `desmume_jit_block_size` |
| `forbiddenImports` | `_pthread_jit_write_protect_np`, `_vm_protect`, `_mach_vm_protect`, `_task_set_exception_ports`, `_mach_msg`, `___clear_cache` (le SDK iOS ne l'a pas : c'est l'échec de lien de Beetle, run 45191228672) |
| `jitArenaBytes` | 33 554 432 |
| `noticeLicense`, `identityLicense` | « GPLv3 (DeSmuME GPLv2+, JIT AArch64 de TASEmulators GPLv2+, cadre JIT libretro GPLv3+) », `GPLv3` |
| `licenseFiles` | `license.txt` (texte GPLv2 fourni par L) |

- **Extension du constructeur.** `build_make` accepte un champ `directory` (`make -C <source>/<directory>`) ;
  `output` reste relatif à la racine. Ces quelques lignes viennent avec l'épingle.
- **Ce que le constructeur vérifie déjà** :
  - empreintes de l'archive, du correctif, de l'en-tête et des fichiers d'origine ;
  - Mach-O iOS, dépendances et exports ;
  - imports interdits ;
  - réécriture de la notice et de l'identité.
- **Contrôle à ajouter dans le correctif.** Aucune occurrence de `MAP_JIT` ni de `PROT_EXEC` dans les fichiers
  compilés (`grep` dans la revue du correctif).

### 7.5 Critères d'acceptation de l'étape 0

1. **Compilation.**
   - Le job `source-cores` est vert, et l'identité porte `compiled`, `jitInterface: 1` et `jitArenaBytes`.
   - Les exports sont présents et aucun import interdit n'apparaît.
   - `test/libretro_core_options_test.py --cores` passe avec les surcharges de la section 10.
2. **Sur iPhone, JIT prêt.**
   - Les lignes `[rb-jit] desmume installed=1 …` puis `[rb-jit] desmume jit=1 …` apparaissent (section 9).
   - Le nombre de vidages et de replis reste bas sur dix jeux de référence :
     - 2D : New Super Mario Bros., Castlevania ;
     - 3D : Mario Kart DS, Zelda Phantom Hourglass ;
     - overlays et ARM7 chargé : Pokémon Platine, Animal Crossing Wild World, Advance Wars Dual Strike ;
     - trois autres choisis par le mainteneur.
   - Chacun est joué dix minutes sans défaut nouveau.
3. **États.** Une sauvegarde d'état faite en JIT se recharge en interpréteur, et inversement : l'état du JIT n'est
   jamais sérialisé.
4. **Sans JIT.** Le comportement est identique à aujourd'hui : interpréteur, avec l'avis `jitInterpreterNotice`.
5. **Mesure.** Part CPU par image avant et après (`os_signpost`, section 4). Aucun gain n'est annoncé sans elle.

## 8. Code automodifiant, overlays et cache d'instructions

Leçon de Lightrec (Beetle, `485411bb`). Sortir d'un bloc au milieu d'une écriture et reprendre dans un nouveau
bloc n'est juste que si tous les registres de l'invité sont à jour en mémoire. Un optimiseur qui retarde ou
supprime des écritures de registres casse cette hypothèse.

- **Étapes 0, A et B.** L'état est en mémoire (`armcpu_t`) à chaque frontière d'instruction : toute sortie est sûre.
- **Étape C.** Les registres restent dans x20-x27 : chaque sortie anticipée passe par l'épilogue qui écrit les
  paires (`STP`) avant de rendre la main.
- **Règle d'écriture dans le code.**
  - Une écriture qui touche le bitmap de code marque la plage.
  - Si la plage recoupe le bloc en cours au-delà du PC courant, le bloc se termine juste après l'écriture :
    PC = instruction suivante, état synchronisé, sortie vers le distributeur.
  - Sinon, l'exécution continue.
  - Le distributeur retire les blocs marqués avant toute nouvelle recherche.
- **ARM9 (ARM946E-S).** Il a un cache d'instructions. Après avoir chargé un overlay, les jeux nettoient le
  cache de données (MCR p15, c7, c10 ou c14), puis invalident le cache d'instructions (MCR p15, c7, c5). Toute
  MCR p15, c7 est un point de sortie ; l'invalidation c7, c5 est aussi un point de validation.
- **ARM7.** Il n'a pas de cache : la règle d'écriture suffit.
- **Remappages.** Les remappages VRAM et WRAMCNT invalident les plages concernées (nouveaux crochets,
  section 2.1).
- **Triche.** Mêmes chemins : l'invalidation précise remplace la remise à zéro globale de
  `cheatSystem.cpp:1041-1049`.
- **Recompilations répétées.** Garder le repli de T : après huit recompilations d'une même adresse, ce bloc reste
  interprété (`recompile_counts`, `arm_jit_arm.cpp:4147-4162`).

## 9. Fils d'exécution et diagnostic

- **Un seul fil.** Le JIT tourne sur le fil d'émulation de la session libretro. Pas de compilation en arrière-plan
  aux étapes 0 à 3, donc aucune course entre écriture RW et exécution RX. L'entrelacement ARM9/ARM7 est celui
  d'aujourd'hui.
- **Journal**, au format des lignes `[rb-jit]` d'Azahar :
  - à l'installation : `[rb-jit] desmume installed=1 arena=33554432 page=16384` ;
  - toutes les 30 secondes de jeu et à la fermeture :
    `[rb-jit] desmume jit=1 blocks=… used=… flushes=… recompiles=… fallbacks=… interp_blocks=…` ;
  - sans interface : `[rb-jit] desmume installed=0 jit=0`.
- **Usage.** Régler la taille de l'arène, repérer les jeux qui vident en rafale et documenter chaque essai sur
  iPhone.

## 10. Côté RewindBox

- **Catalogue (`lib/services/libretro_core_catalog.dart`).**
  - `noJitOverrides` : `desmume_cpu_mode: interpreter` (existant) et `desmume_jit_block_size: 12`, sa valeur par
    défaut. Le contrat d'options l'exige, car la clé contient « jit ».
  - `optionDefaults` : `desmume_cpu_mode: jit`. La valeur par défaut de L est `interpreter`.
  - Pas de `jitOverrides` : avec le JIT, le choix de l'utilisateur prime ; sans, la surcharge impose
    l'interpréteur pour la session.
- **Réglage visible par jeu.** Réponse à la question du mainteneur : « aucune option visible ».
  - `LibretroCuratedSetting` gagne un attribut `requiresJit`. La session native n'affiche le réglage que si le cœur
    a accepté l'interface (`_host.jitCapable`).
  - Le choix est enregistré dans la couche par jeu de `LibretroCoreOptions.m` (`Config/Games/<cœur>.json`). Les
    surcharges sans JIT passent avant cette couche : sans JIT, l'interpréteur s'impose quel que soit le choix
    enregistré.
  - Il s'applique au redémarrage du jeu, comme le dit déjà le pied du menu en jeu (L ne relit pas l'option,
    section 7.2).
  - Pour DeSmuME : « Processeur : JIT / Interpréteur », en douze langues.
  - Le même mécanisme sert à Azahar (`citra_use_cpu_jit`) et à Beetle (`beetle_psx(_hw)_cpu_dynarec` :
    `execute`, `disabled`).
- **Arène.** Aucune taille dans le catalogue. Elle vient de l'identité embarquée (`jitInterface`,
  `jitArenaBytes`), comme pour Azahar ; l'aide n'est lancée que pour un cœur qui la porte.
- **Collection.** `PINS` de `libretro_source_cores.py` gagne `desmume`, et le job `source-cores` construit
  `azahar,mednafen_psx_hw,mednafen_psx,desmume`.
- **Livraison.**
  - L'artefact retenu est ajouté à `COLLECTIONS` dans `.github/diagnostics/libretro_source_collections.py`, avec
    `cores` complété de `desmume`.
  - Jamais dans `retained_components.py`, entrée figée du Core MeloNX : la 826 a échoué sur ce point
    (run 45195605335).
  - Le manifeste suit la liste de la section 11.

## 11. Liste de contrôle de livraison

Tirée de la 826.

1. Télécharger l'artefact du job `source-cores` et contrôler :
   - les identités ;
   - la notice (lignes réécrites) ;
   - les textes de licence ;
   - `test/libretro_core_options_test.py --cores` sur la collection réelle.
2. Commit produit :
   - surcharges et réglages du catalogue ;
   - tests Dart et Python qui les attendent ;
   - notices de l'application (`NOTICE.md`, `assets/legal/THIRD_PARTY_NOTICES.md`,
     `assets/legal/libretro/LIBRETRO_CORES.md`, `license-sources.json`) ;
   - `embed_legal_bundle.py --validate-only`.
3. Manifeste :
   - `components.libretro.origin` vers le run `source-cores`, `jitHelper: true` ;
   - `images.retained.libretro` qui nomme les cœurs non reconstruits ;
   - chaque framework reconstruit sous `images.mustChange` ;
   - travaux concurrents classés (revus ou « source seulement »).
4. Contrat hors ligne, gel, `trigger-paths`, file de livraison vide, puis commit `[ipa-delivery:N]`.

## 12. Décisions restantes pour le mainteneur

1. **Réglage visible par jeu** (`requiresJit`, section 10) pour DeSmuME, Azahar et Beetle. Recommandé.
2. **Taille de l'arène** : 32 Mio au départ, ajustée d'après les lignes `[rb-jit]`.
3. **Calendrier.** Étapes 0 à 4 faites (sections 13 et 14) ; leur livraison revient à la session qui fait les
   IPA. La suite dépend des mesures sur iPhone (section 14, « Reste à faire »).

## 13. État : étape 0 réalisée (23 novembre 2026)

- **Code.** `native/desmume/` contient l'épingle `source.json`, le correctif `arm64-jit-abi.patch` (11 fichiers,
  +310/−142) et un [README](../native/desmume/README.md).
  - Les trois fichiers du JIT de T sont importés à `b549f71b` par `importFiles`, nouveau dans
    `build-utils/libretro_source_cores.py`, avec leurs SHA-256 vérifiés. Le correctif ne porte que nos changements.
  - Le constructeur gagne aussi `build.directory` (make dans `desmume/src/frontend/libretro`) et `sourceDateEpoch`.
    Celui-ci donne une date de compilation fixe : une recompilation de la même épingle redonne le même binaire,
    ce qui vaut aussi pour Azahar et Beetle.
- **Écarts avec les sections 7 à 10.**
  - Vidage de l'arène immédiat, comme T, sans `munmap` (section 7.2).
  - `IOSMINVER` vaut toujours 8.0 par défaut dans le Makefile ; l'épingle passe `IOSMINVER=14.0`.
  - Défauts corrigés en plus de #997, #998 et #1002 :
    - retenue d'`ASR #32` aussi en ARM (opérations de données avec S) ;
    - +2 cycles comptés deux fois pour les écritures de r15 par une opération de données ;
    - la première exécution d'un bloc, interprétée pendant sa compilation, s'arrête aussi après une écriture qui
      arme un DMA (sinon le premier transfert se perdait).
  - Le défaut 1 du #998 (cycles lus sans initialisation) n'existe pas dans la version AArch64 : le repli sur
    l'interpréteur écrit `bb_cycles`.
  - Journal : `[rb-jit] desmume installed=… arena=… page=… wanted=… jit=…` au démarrage, puis
    `blocks used capacity flushes interpreted failures` toutes les 30 s de jeu et au déchargement.
  - Section 8 non faite : ni sortie sur écriture dans le bloc en cours, ni MCR p15 c7 comme point de sortie. Le
    comportement du JIT amont est conservé.
  - Section 10 faite pour le catalogue (JIT par défaut ; interpréteur et taille de bloc 12 sans JIT). Le réglage
    visible par jeu n'est pas fait (décision 1).
- **Vérification hors appareil**, banc manuel non livré :
  - le cœur compilé pour Linux AArch64, sous qemu, dans un frontend libretro avec une arène memfd vue en RW et en
    RX ;
  - une ROM DS de test écrite pour l'occasion.

  | Configuration | Résultat |
  | --- | --- |
  | Avant correctifs | 249 relevés sur 4 380 différaient de l'interpréteur |
  | Après correctifs, blocs de 1, 12 et 100 | 4 396 sur 4 396 identiques |
  | Arène de 4 Mio | Rembobinages corrects |
  | Sans interface ou hôte sans capacité JIT | Interpréteur |

  Le même arbre, reconstruit par le constructeur à partir de l'épingle, donne les mêmes résultats.
- **Compilation iOS** : route source-cores, run [45213717171](https://github.com/TarbleFR/RewindBox/actions/runs/45213717171),
  artefact `LibretroCores-6cd6a89b…` (id 14839590544).
  - DeSmuME pèse 4 515 640 octets, vise iOS 14.0 et a les mêmes dépendances que le binaire buildbot.
  - Exports et imports sont conformes ; le contrat d'options passe sur les 35 binaires.
  - Passation pour la livraison : [libretro-jit-collection-handoff.md](libretro-jit-collection-handoff.md).
- **Reste à faire.**
  - Mesures sur iPhone : critères 2 à 5 de la section 7.5.
  - Livraison par la session IPA.
  - Étapes 1 à 4 de la section 3 : faites, section 14.

## 14. État : étapes 1 à 4 réalisées (23 novembre 2026)

- **Code.** Le correctif `native/desmume/arm64-jit-abi.patch` passe à 17 fichiers (+2 702/−208), dont trois
  nouveaux : `utils/arm_jit/rb_cached.cpp` (étape 2), `rb_a64.h` et `rb_jit.cpp` (étapes 3 et 4). L'épingle
  vérifie aussi `armcpu.cpp`, `MMU_timing.h` et `libretro_core_options.h`. Détail dans le
  [README](../native/desmume/README.md).
- **Modes de CPU** (`desmume_cpu_mode`) :

  | Valeur | Moteur | Résultat |
  | --- | --- | --- |
  | `interpreter` | Interpréteur de DeSmuME | Référence |
  | `cached` | Interpréteur en cache (étape 2), sans mémoire exécutable | Identique à l'interpréteur, au cycle près |
  | `jit` | JIT de T (étape 0) sur la couche commune (étape 1) | Le plus rapide ; fetch non compté, entrelacement par bloc |
  | `jit_exact` | JIT RewindBox (étapes 3 et 4), mode exact | Identique à l'interpréteur, au cycle près |
  | `jit_fast` (non proposé) | JIT RewindBox, mode rapide | Cycles exacts, entrelacement par bloc |

  - `jit` ou `jit_exact` sans JIT disponible : interpréteur en cache.
  - Journal de démarrage : `[rb-jit] desmume … cached=… engine=…`.
- **Étape 1, couche commune.**
  - Table par pages de 16 Kio allouées à la demande, entrées de 32 bits : décalage dans l'arène, étiquette
    CPU/Thumb vérifiée à chaque lecture.
  - Invalidation précise : bit de code par 16 octets, listes de blocs par 512 octets ; une écriture tue tous les
    blocs qu'elle touche et fait sortir le bloc en cours (section 8).
  - Crochets WRAMCNT et VRAM ; PC hors région : un pas d'interpréteur.
  - Demandes de sortie : DMA, code modifié, `NDS_Reschedule`, bus gelé, `emu_halt`, attente d'IRQ par CPU.
  - `arm_jit_sync` sans effet de bord.
- **Étape 2, interpréteur en cache.** Blocs décodés {gestionnaire, opcode, condition} en mémoire ordinaire. Chaque
  instruction s'exécute comme dans `armcpu_exec`. Une course continue tant que la boucle CPU aurait donné
  l'instruction suivante à ce CPU (temps inférieur à celui de l'autre CPU et au prochain événement), et
  `nds_timer` avance comme elle : le résultat est celui de l'interpréteur, au cycle près.
- **Étapes 3 et 4, JIT RewindBox.**
  - Encodeur AArch64 maison (`rb_a64.h`) au lieu d'oaknut : une centaine d'encodages suffisent.
  - Stubs d'entrée et de sortie dans les 256 premiers octets de l'arène ; x19 à x28 portent l'état d'une course
    (CPU, temps, limite, table, arène, `nds_timer`).
  - Étape 3 : appel du gestionnaire de chaque instruction, condition testée en natif, cycles de l'interpréteur. Le
    temps du fetch est calculé à la compilation, sauf aux changements de ligne du cache d'instructions de l'ARM9,
    qui passent par une aide.
  - Étape 4 : code natif pour les opérations de données ARM (immédiat ou registre décalé par une constante, avec
    ou sans drapeaux, conditionnelles), les opérations Thumb (décalages, additions, ALU, registres hauts, pile) et
    les branchements B, BL, B<cond> et BL Thumb, enchaînés directement vers leur cible. Le gestionnaire doit être
    celui de la classe, sinon l'instruction reste à l'étape 3.
  - Blocs enchaînés par la table ; entrée possible à chaque instruction.
  - Mode exact : test de la boucle CPU et `nds_timer` avant chaque instruction. Mode rapide : entre les blocs.
- **Écarts avec les sections 2 et 7.**
  - Pas de registres invités fixes dans x20 à x27 : chaque instruction relit et réécrit `armcpu_t`, ce qui permet
    d'entrer n'importe où dans un bloc.
  - Drapeaux réécrits dans CPSR à chaque instruction ; pas encore d'analyse de vivacité.
  - Accès mémoire, multiplications, décalages par registre, LDM/STM : encore par le gestionnaire.
  - Le moteur `jit` reste celui de T, le plus rapide mesuré.
- **Vérification hors appareil** (banc de la section 13, ROM complétée : code modifié dans le bloc en cours et au
  milieu d'un autre bloc, remappage WRAMCNT, code en mémoire de palette, balayage de 2 Mio, compteur de temps émulé
  par CPU) :

  | Configuration | Résultat, comparé à l'interpréteur |
  | --- | --- |
  | Étape 0 seule | 85 relevés sur 4 488 différents (code modifié, remappage) |
  | `jit`, blocs de 1, 12 et 100, arène de 4 Mio | 4 493 sur 4 493 identiques |
  | `cached` | RAM identique octet pour octet, compteurs identiques ; états sauvegardés et chargement d'un état identiques |
  | `jit_exact`, blocs de 1, 12 et 100, arène de 8 Mio rembobinée | RAM et compteurs identiques |
  | `jit_fast` | 4 493 sur 4 493 identiques ; temps émulé à quelques cycles près |
  | `jit` demandé, hôte sans JIT | Interpréteur en cache, RAM identique |

  Le même arbre, reconstruit par le constructeur à partir de l'épingle, est identique fichier par fichier.
- **Vitesse sous qemu** (ROM de mesure, 300 images, deux CPU toujours occupés). Ce ne sont pas des mesures
  iPhone : qemu pénalise surtout les appels indirects.

  | Mode | Temps | Par rapport à l'interpréteur |
  | --- | --- | --- |
  | `interpreter` | 67,1 s | 1 |
  | `cached` | 54,3 s | 1,24× |
  | `jit_exact` | 75,8 s | 0,89× |
  | `jit_fast` | 21,9 s | 3,1× |
  | `jit` | 8,7 s | 7,7× |

  - Sans le temps du fetch (`desmume_advanced_timing` désactivé), `jit_fast` passe à 18,9 s.
  - `jit_exact` rend la main à l'autre CPU presque à chaque instruction quand les deux tournent : c'est un mode
    de compatibilité.
- **Catalogue.** Sans JIT, la surcharge de l'app passera de `interpreter` à `cached` avec la collection qui porte
  ce binaire (même résultat, plus rapide).
- **Reste à faire.**
  - Mesures sur iPhone, puis choix du moteur par défaut d'après elles.
  - Pour que le JIT RewindBox dépasse celui de T : accès mémoire natifs (DTCM, RAM principale, cache de données en
    ligne), recherche en ligne dans le cache d'instructions, vivacité des drapeaux, multiplications, LDM/STM.
  - Compilation iOS par la route source-cores et nouvelle collection.
