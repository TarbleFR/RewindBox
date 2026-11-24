# DeSmuME : architecture d'un JIT AArch64 pour RewindBox

*23 novembre 2026 — branche `Claude`. **Étapes 0 à 4 réalisées** (sections 13 et 14) : JIT AArch64 de T sur
l'ABI, couche commune, interpréteur en cache, JIT RewindBox à appels puis natif, dans `native/desmume`, vérifiés
hors appareil ; rien mesuré sur iPhone. **Section 15** : cause et correctif du gel de l'IPA 828, rendu plus rapide
en haute résolution interne. **Section 16** : JIT absent sans cause journalisée (IPA 829), ×10 à 20 fps : architecture
retenue ; 16.5 : journaux de la 830, la 3D se dessine pendant la composition 2D. Décisions du mainteneur : « DS : garder DeSmuME, soit inventif et conçois
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
- **Collection et catalogue.** Compilé pour iOS par la route source-cores (run 45237317896) : collection
  `LibretroCores-66e232e0…`, adoptée dans les sources ([passation](libretro-jit-collection-handoff.md)). Sans JIT, la
  surcharge de l'app passe de `interpreter` à `cached` (même résultat, plus rapide). Au lancement d'un jeu, l'app
  affiche le moteur que le cœur rapporte (`engine=`).
- **Reste à faire.**
  - Mesures sur iPhone, puis choix du moteur par défaut d'après elles.
  - Pour que le JIT RewindBox dépasse celui de T : accès mémoire natifs (DTCM, RAM principale, cache de données en
    ligne), recherche en ligne dans le cache d'instructions, vivacité des drapeaux, multiplications, LDM/STM.
  - Livraison de la collection dans une IPA : session des livraisons.

## 15. État : gel de l'IPA 828 corrigé, rendu en haute résolution (23 novembre 2026)

Demande du mainteneur : « le JIT fait planter la console », et une résolution interne jusqu'à ×10 (2560×1920) sans
ralentissement. Retour de l'iPhone sur la 828 : Animal Crossing figé à l'ouverture du menu en jeu
([passation](libretro-jit-collection-handoff.md)). Les journaux fournis ne contenaient que des sessions MeloNX : la
cause a été cherchée hors appareil.

### 15.1 Cause du gel : une écriture hors table dans le JIT de T

- **Défaut.** `OP_LDM_STM_main` (`arm_jit_arm.cpp`), le chemin rapide des STM et PUSH du JIT de T, écrit lui-même
  dans la table des blocs : deux zéros de la taille d'un pointeur à `&JIT_COMPILED_FUNC(adr)`, puis un pas de deux
  pointeurs par mot. C'était juste pour la table d'origine (une entrée de 8 octets par demi-mot). L'étape 1 a
  remplacé cette table par des pages de 8 192 entrées de 32 bits et une page de zéros partagée, « jamais écrite » ;
  ce chemin n'avait pas été repris.
- **Effet.** Chaque écriture multi-registres vers la RAM principale effaçait 16 octets au lieu de 8 et avançait deux
  fois trop vite : en fin de page (ou en début, pour un PUSH), elle sortait des entrées de la page, ou de la page de
  zéros, et mettait à zéro la mémoire voisine. Les boucles de copie et de mise à zéro des jeux passent par là à
  chaque frontière de 16 Kio.
- **Pourquoi le banc de la section 14 ne l'a pas vu.** Sous Linux, ces zéros tombaient sur des en-têtes de blocs
  `malloc` jamais relus ou sur des variables voisines sans effet ; la ROM de test ne faisait pas de STM en fin de
  page. Sur iPhone, ils tombent dans le tas de l'application : le gel à l'ouverture du menu, qui alloue beaucoup,
  est cohérent avec cette cause. Ce lien n'est pas prouvé sur appareil.
- **Reproduction.** Cœur compilé avec contrôles de bornes et contrôle des tables après chaque bloc, homebrew
  « MarioKart » de dsgmLib, mode `jit` : après le bloc Thumb à `0x02020DB0` (`STMIA r3!,{r0}` ; `SUB r1,#1` ; `BNE`,
  avec r3 = `0x02077FFC`), `jit_page_chunks[0]` est nul, puis `jit_table_clear` plante. Quatre homebrews 3D sur
  quatre.
- **Correctif.** Ces écritures passent par le crochet d'invalidation des autres chemins
  (`JIT_COMPILED_FUNC_KNOWNBANK(adr, MAIN_MEM, …)`) : les blocs touchés sont invalidés, le bloc en cours sort après
  l'instruction. Aucun autre accès direct à la table ne reste dans le cœur.
- **Pistes écartées.** Choix de registres d'Apple (`x23` pour `x18`), reproduit sur le banc : sans effet. Préparation
  de l'arène par l'aide JIT : même script que S2Arm. États sauvegardés, remise à zéro et changement de résolution en
  jeu sous JIT : corrects. Trois plantages SIGSEGV du journal MetricKit fourni : hors sessions MeloNX, sans pile ;
  deux datent d'avant la première IPA avec le JIT de DeSmuME, aucun n'est attribuable à DeSmuME.

### 15.2 Rendu en haute résolution interne

Le profil du cœur de la 828 en ×10 (un seul fil de rastériseur, le réglage livré) :

| Part du fil d'émulation | Cause |
| --- | --- |
| environ 45 % | attente de l'effacement du tampon 3D, fait par un appel par pixel sur sept plans |
| environ 25 % | attente du rastériseur ; avec plusieurs fils, une bande fixe par fil laissait presque tout le travail à la moitié d'entre eux quand la scène est au milieu de l'écran |
| environ 20 % | composition de la couche 3D, pixel par pixel |
| environ 10 % | conversion de l'image en RGB565 |

Changements, tous sans effet sur l'image (vérifié au bit près, [README](../native/desmume/README.md)) :

- effacement plan par plan, fait par chaque fil juste avant de dessiner sa tranche ;
- tranches de lignes entrelacées prises à un compteur commun : charge égale où que soit la scène, et un cœur lent
  prend moins de tranches au lieu de retenir l'image ;
- `desmume_num_cores` vaut `auto` par défaut (un fil par cœur) : RewindBox ne réglait pas cette option, restée à 1 ;
- chemin vectorisable pour la composition de la couche 3D dans son cas courant ;
- conversion de sortie partagée avec trois fils d'aide ;
- à la résolution de la console, le fil d'émulation dessine lui-même (réveiller les fils coûtait plus que le dessin).

Mesures hors appareil (scène « Galaxy », x86-64 à 2,1 GHz, 4 processeurs virtuels) : ×10 de 82,6 à 29,5 ms par
image, ×5 de 22,1 à 10,9 ms, ×1 inchangé. Aucune mesure iPhone.

### 15.3 Limites

- **×10 n'est pas garanti fluide.** Le rendu reste logiciel : en ×10, chaque image traite 4,9 millions de pixels par
  écran. Une scène 3D plein écran avec recouvrement coûte plusieurs fois la scène mesurée.
- **Au-delà de la définition de l'écran.** Deux écrans DS empilés en ×10 font 2560×3840 ; un iPhone 16 Pro
  (2622×1206) affiche chaque écran DS à ×4,7 en portrait et ×6,3 en paysage au plus : au-delà, l'image est réduite à
  l'affichage (lissage), pas plus détaillée.
- **Suite possible.** Composer la couche 3D hors du fil d'émulation, ou rendre la 3D par le GPU (moteur OpenGL ES 3
  de T, absent du fork libretro, et composition côté hôte).
- **Reste sur le fil d'émulation** : composition des couches, agrandissement de l'écran sans 3D.

## 16. État : JIT absent sans cause, ×10 à 20 fps (24 novembre 2026)

Retour du mainteneur sur l'IPA 829 (Animal Crossing, A18 Pro) : une session sans JIT
(`jit: engine=cached active=0 capable=0 expected=1`), et le ×10 à environ 20 fps, empreinte à 1,05 Go, `thermal=0`.
Objectif : 60 fps avec une image équivalente au ×10, mémoire maîtrisée.

### 16.1 JIT absent : la préparation s'arrête côté Flutter, sans trace dans la session

- **Pas de régression des binaires.** Sept minutes après la session 17956 (00:08:08 UTC), la session 17989
  (00:15:32 UTC), avec les mêmes images (`App` A1B290F7, `Runner` 97B28B82, `libretro_internal_bridge` 661E9EC7,
  `desmume_libretro` 813C576E), installe l'interface (`load: JIT interface 1 installed; [rb-jit] arena=ready …
  prepare_ms=107`) et DeSmuME tourne en JIT (`[rb-jit] desmume unload jit=1 blocks=32931 used=25354048 … flushes=0`).
  Entre la 828 et la 829, ni `_prepareJit`, ni la sonde LocalDevVPN, ni `LibretroJit.m` n'ont changé ; le pont
  n'ajoute que l'affichage du message JIT.
- **Chemin.** `LibretroInternalService._prepareJit` (Dart) s'exécute avant le lancement : sonde de la route
  LocalDevVPN (2 s au plus), fichier d'appairage enregistré, puis transaction de l'aide StikJIT. Un échec des deux
  premières étapes n'écrit que dans `Diagnostics/app.log` et n'appelle jamais l'aide ; le journal de session, ouvert
  ensuite, ne voyait que la conséquence. Côté natif, une arène absente n'était pas journalisée non plus (seule une
  arène prête mais refusée l'était).
- **Session 17956.** Aucune transaction : pas de ligne `[rb-jit] arena=`, avis « vérifiez LocalDevVPN et le fichier
  d'appairage ». Le fichier d'appairage servant sept minutes plus tard, la route LocalDevVPN est la cause la plus
  probable (coupée ou sans réponse en 2 s). L'étape exacte est dans `app.log` à cette heure
  (`libretro JIT: LocalDevVPN route unavailable (…)` ou `no stored pairing file`), absent des journaux fournis.
- **Correctif.** `_prepareJit` rend `LibretroJitPreparation` (`RB_JIT_VPN <code>: <message>`, `RB_JIT_NO_PAIRING`,
  code et faits de la transaction native, `RB_JIT_EXCEPTION`), transmis par la requête (`jitPreparation`).
  `LibretroJitInstallIntoLibraryWithReason` nomme le refus (`RB_JIT_ARENA_NOT_READY`, `RB_JIT_CORE_SYMBOL`,
  `RB_JIT_CORE_REFUSED install=<n>`). Le journal de session écrit toujours une ligne :
  `load: JIT interface not installed: <raison>; preparation: <détail>; [rb-jit] arena=…`.
- **DeSmuME prend bien son JIT** dès que l'arène est installée (session 17989 ci-dessus). L'arène s'y remplissait
  (25,4 Mo sur 32 en 48 s) : `jitArenaBytes` passe à 64 Mio. Une arène pleine est vidée et le code recompilé : un
  à-coup, pas un plantage.

### 16.2 ×10 : où part le temps (faits des journaux)

- **Cadences.** Session 17989 (JIT) : environ 48 fps en ×6 (images 301 à 812 en 10,55 s), environ 20 fps en ×10
  (242 images en 12 s de jeu, menu et arrière-plan retirés). Session 17956 (interpréteur en cache) : environ 47 fps
  en ×6. Le CPU émulé ne limite donc pas : le temps d'une image croît avec le nombre de pixels, environ
  4,4 ms + 4,6 ms par million de pixels produits (×6 : 3,54 Mpx, 20,8 ms ; ×10 : 9,83 Mpx, 50 ms). Estimation à deux
  points.
- **MetalFX.** `[rb-metalfx] standard picture METALFX_RATIO` : le cadre (2560×3840) est plus grand que sa place à
  l'écran, MetalFX n'est pas appliqué (`LibretroMetalFXPolicy.h`). Il ne coûte rien en ×6 ni en ×10.
- **Travail série par pixel sur le fil d'émulation en ×10** : composition 2D à la résolution interne (4,9 Mpx par
  écran), conversion des deux écrans par le frontend (9,8 Mpx), puis dans l'hôte
  (`LibretroMetalPresenter presentSoftwareFrame`) une conversion RGB565 → BGRA8 pixel par pixel dans un tampon de
  39 Mo et sa copie (`replaceRegion`) de 39 Mo.
- **Mémoire.** Cœur : 80 → 311 Mo de ×1 à ×10 (pic mesuré sur le banc). Hôte en ×10 : tampon de conversion de 39 Mo
  et trois textures BGRA8 de 2560×3840 (118 Mo).

### 16.3 Architecture retenue

1. **Hôte : l'image RGB565 part telle quelle.** Texture `B5G6R5Unorm` (toutes les GPU Apple), le GPU développe les
   canaux : plus de conversion sur le fil d'émulation, copie et textures divisées par deux (3 × 19,7 Mo en ×10 au
   lieu de 3 × 39,3 + 39). Tous les lecteurs de la texture l'échantillonnent par une passe de rendu (cadre standard,
   entrée de MetalFX, chaîne slang) : aucun ne dépend de son format. Repli sur la conversion si le format manque.
2. **Cœur : suréchantillonnage 3D** (`desmume_rb_3d_supersampling`, réglage « Suréchantillonnage 3D » du menu en
   jeu). Composition et image à ×5 (ou ×4), 3D dessinée au double par les fils du rastériseur puis moyennée (2×2).
   Dans DeSmuME, la résolution interne n'agrandit que la 3D : la 2D est faite de pixels natifs agrandis. ×5 + 3D 2x
   est donc l'image ×10 vue sur un écran de ×5, pour un quart des pixels de la 2D, de la sortie et de l'envoi. Un
   iPhone 16 Pro affiche au plus ×4,7 par écran DS en portrait, ×5,1 côte à côte et ×6,3 pour un grand écran en
   paysage : au-delà, le ×10 est réduit à l'affichage. Au-dessus de ×5, le cœur laisse l'option inactive.
3. **Mesures `[rb-perf]`** dans le journal du cœur ([README](../native/desmume/README.md)) : CPU émulé, 2D, attente
   et travail de la 3D, sortie, hôte. Elles diront sur l'iPhone ce que le modèle ci-dessus ne fait qu'estimer.
4. **Rendu GPU : pas maintenant.** Le rendu 3D OpenGL de DeSmuME laisse la composition 2D sur le CPU à pleine
   résolution et relit la 3D à chaque image ; le fork libretro n'a pas de moteur OpenGL ES 3 (celui de T,
   `OGLRender_ES3.cpp`, serait à porter, sur ANGLE ou un contexte GLES de l'hôte) ; une composition entièrement sur
   le GPU (comme celle de melonDS) est un nouveau moteur. La voie retenue retire les pixels du chemin critique sans
   attendre ce chantier.

**Banc** (x86-64, 4 processeurs virtuels, scène 3D « Galaxy ») : ×10 48,9 fps (20,45 ms), ×5 + 3D 2x 59,5 fps
(16,80 ms), ×4 + 3D 2x 78,2 fps (12,78 ms), ×5 seul 118,1 fps (8,46 ms). Pic mémoire du cœur : ×10 311 Mo,
×5 + 3D 2x 192 Mo, ×4 + 3D 2x 151 Mo, ×5 seul 137 Mo. Fidélité (PSNR de l'écran 3D contre le ×10 réduit) : 42,6 dB
contre 35,6 pour le ×5 seul (MarioKart de dsgmLib), 48,0 contre 41,7 (Mario's Dream 2), 45,8 contre 45,2 (Galaxy) ;
écran sans 3D identique. Option désactivée : images identiques au bit près au cœur de la 829 (cinq configurations).

**Attendu sur l'iPhone** (estimation par le modèle de 16.2, gain de l'hôte non compris, non mesurée) : ×5 + 3D 2x
compose 2,46 Mpx, soit environ 15,7 ms par image, vers 60 fps si la 3D au double (six fils, deux cœurs performants
et quatre efficaces) tient dans le temps qu'elle chevauche ; ×4 + 3D 2x (1,57 Mpx, environ 11,7 ms) laisse de la
marge, et MetalFX agrandit alors les ~1,2× restants jusqu'à l'écran. Mémoire : environ −120 Mo dans le cœur et
−140 Mo dans l'hôte par rapport au ×10 actuel, soit vers 0,8 Go au lieu de 1,05. Un vrai ×10 à 60 fps verrouillés
n'est pas à portée du rendu logiciel.

### 16.4 À lire dans le prochain `session.log`

- JIT : `load: JIT interface 1 installed; [rb-jit] arena=ready mode=universal capacity=67108864 …` puis
  `jit: engine=jit active=1 capable=1 expected=1` ; sinon une ligne
  `load: JIT interface not installed: RB_JIT_ARENA_NOT_READY: …; preparation: RB_JIT_VPN <code>: …` (ou
  `RB_JIT_NO_PAIRING`, ou le code de l'aide avec ses faits).
- Journal du cœur : `[rb-jit] desmume installed=1 arena=67108864 … engine=jit`, puis toutes les 600 images
  `[rb-perf] desmume frames=600 fps=… res=1280x960 ss=2 threads=… jit=1 ms/frame run=… emu=… 2d=… wait=… out=…
  host=… raster=…`.
- `run: frame 1280x1920` en ×5 + 3D 2x (au lieu de `2560x3840`), puis `system: … footprint=` après le changement.

### 16.5 Après l'IPA 830 : journaux du mainteneur, la 3D pendant la composition 2D

Journaux fournis : `session.log` (pid 19155, Animal Crossing) et `app.log`. Objectif du mainteneur : 59-60+ i/s
stables.

- **JIT : actif et sain.** `load: JIT interface 1 installed; [rb-jit] arena=ready mode=universal capacity=67108864 …
  commands=4 … prepare_ms=208`, `jit: engine=jit active=1`, `[rb-jit] desmume installed=1 arena=67108864 …
  engine=jit`, puis `unload jit=1 blocks=31555 used=24417264 … flushes=0 failures=0`. La transaction de l'aide dure
  2,16 s dans `app.log` (1,5 à 2,0 s avec 32 Mio). Le CPU émulé coûte 3,1 ms par image (`cpu=`).
- **Cause de la perte de la 829 confirmée** par `app.log` : deux lancements de DeSmuME où « LocalDevVPN did not
  expose RemotePairing at 10.7.0.1:49152 (state=timeout, elapsedMs=1313) », `networkState: preparing`, puis
  « desmume keeps its interpreter ». LocalDevVPN ne répondait pas ; l'appairage n'était pas en cause.
- **Cadence en ×5 + 3D 2x** (en ville, 600 images sans menu) : 42,4 i/s.
  - `run` = 23,08 ms, réparti ainsi : `cpu` 3,15, `2d` 7,52, `wait` 9,16, `out` 2,34, `host` 0,89.
  - `raster` = 57,9 ms de travail des six fils par image.
  - En ×10 au démarrage (titre) : 38 i/s, `host` = 2,88 ms (envoi RGB565 direct).
- **Empreinte de départ de 2,05 Go** : une session MeloNX venait de tourner dans le même processus (MeloNXCore et ses
  bibliothèques sont chargés). Cela ne vient pas de DeSmuME.
- **Cause des 9 ms d'attente.** Sans `rigorous_timing`, DeSmuME lance la 3D à la ligne 262
  (`gfx3d_VBlankEndSignal`), et le moteur 2D attendait toute l'image 3D à la ligne 0, une ligne plus tard. Le
  recouvrement se limitait donc à la sortie du frontend et à l'envoi à l'hôte, environ 3 ms.

**Changements** (détail et vérifications : [README](../native/desmume/README.md), « 3D pendant la composition 2D ») :

- tranches en bandes de lignes consécutives prises de haut en bas ; un polygone qui ne croise pas une bande n'y est
  pas parcouru ;
- chaque bande est post-traitée (contours, brouillard) et moyennée dès qu'elle et ses voisines sont dessinées ;
- le moteur 2D attend, ligne par ligne, les seules lignes 3D qu'il compose (`RenderFinishLines`), sauf capture
  directe de la 3D ou sortie 24 bits ;
- un rendu encore en cours se termine avant que le jeu remplace les listes de polygones (`gfx3d_doFlush`). Ce risque
  existait déjà quand la 2D n'affichait pas la 3D ;
- conversion de sortie en NEON (8 pixels, mêmes opérations de bits), sur le seul fil d'émulation ;
- mesures `engA`, `engB`, `end` (répartition de `2d`), `over16` et `over33` (images au-delà de 16,7 et 33,3 ms).

**Banc** (x86-64, 4 processeurs virtuels, scène Galaxy, deux séries) : ×5 + 3D 2x passe de 42,0–47,8 à
57,5–65,4 i/s, ×4 + 3D 2x de 58 à 82,5–94,2, ×10 de 31,3–38,7 à 40,5–46,2. Images et son identiques au bit près
(x86 et AArch64, JIT compris, contours et brouillard forcés, états, réglages changés en jeu). ThreadSanitizer : rien
de nouveau.

**Attendu sur l'iPhone** (estimation, non mesurée) en ×5 + 3D 2x :
- `out` passe d'environ 2,3 à 0,7 ms ;
- `wait` descend à quelques millisecondes, car la 3D dispose aussi des ~10 ms de composition 2D (`2d` = 7,5 ms
  dans Animal Crossing contre 2 à 3 ms dans la scène du banc) ;
- `run` serait donc vers 14 à 17 ms : autour de 60 i/s, sans garantie de stabilité.

En ×4 + 3D 2x (3D à ×8, composition à ×4, MetalFX pour les ~1,2× restants), l'estimation est de 11 à 12 ms : 60 i/s
avec de la marge. Le vrai ×10 reste hors de portée à 60 i/s.

**À lire** dans le prochain `session.log` : `[rb-perf] … res=1280x960 ss=2 … run=… wait=… over16=… over33=…`. Le
60 est stable quand `over16` reste proche de 0 sur 600 images et `run` sous 15 ms ; sinon, ×4 + 3D 2x. `engA`,
`engB` et `end` diront où passent les 7,5 ms de 2D.

### 16.6 Après l'IPA 831 : 40 i/s au plus, capture de la 3D, composition 2D en NEON

Retour du mainteneur : `session.log` (pid 23400, Animal Crossing en ×5), « 40 FPS maximum ». Objectif inchangé :
59-60+ i/s stables.

- **Ce que dit le journal.**
  - JIT installé (arène de 64 Mio), `jit: engine=jit active=1 capable=1 expected=1`.
  - ×5 (`1280x960`, image `1280x1920`).
  - Images 301 à 989 en 13,9 s : 49 i/s de moyenne, titre et chargement compris.
  - `thermal=1` dès 26 s ; empreinte de 0,81 à 0,85 Go.
- **Ce qu'il ne dit pas.** Aucune ligne `[rb-perf]`. Le journal du cœur n'entrait dans `session.log` qu'à l'arrêt
  par le menu ; l'app a été fermée depuis le sélecteur (`UIApplicationWillTerminateNotification`). Le
  suréchantillonnage, la répartition du temps et le chemin de la 3D restent donc inconnus.
- **Pistes, de la plus probable à la moins probable** (aucune n'est mesurée sur l'iPhone) :
  1. **Capture directe de la 3D.** La 831 ne gagne rien sur la 830 (42,4 i/s), comme si le chemin progressif ne
     servait pas. Le code en donne une raison : une ligne capturée avec la 3D seule pour source (`DISPCAPCNT`)
     attendait toute l'image 3D, puis sa conversion entière en 15 bits. Les jeux qui affichent la 3D sur les deux
     écrans capturent l'image. Un fil du forum DeSmuME (2009) décrit, dans Animal Crossing, le ciel affiché en bas
     par erreur : cela va dans ce sens sans le prouver.
  2. **Sept fils pour six cœurs.** Pendant le recouvrement, le fil d'émulation et les six fils du rastériseur se
     disputent deux cœurs performants et quatre efficaces ; le fil qui compose l'image peut perdre son cœur.
  3. **Piste écartée : la voie SSE2 du rastériseur.** Sur le banc, elle paraissait six fois plus rapide. En fait
     elle ignore le suréchantillonnage (`ss=1`) et son effacement n'est pas compté dans `raster` : rien à porter.

**Changements** (détail et vérifications : [README](../native/desmume/README.md), section « Capture de la 3D,
composition 2D en NEON, mesures ») :

- capture directe de la 3D ligne par ligne : chaque ligne capturée attend ses bandes et convertit ses lignes
  (`RenderFlush16Lines`) ; `RenderFlush` convertit le reste ;
- composition 2D en NEON : les voies SSE2 des moteurs 2D de DeSmuME servent aussi sur AArch64 (`RB_GPU_SSE2`,
  49 instructions écrites en NEON dans `utils/rb_sse2neon.h`) ;
- fils du rastériseur une classe de qualité de service sous le fil d'émulation ;
- pont : les lignes `[rb-perf]` et `[rb-jit]` du cœur entrent dans `session.log` au fil de l'eau (`core: …`) ;
- mesures `r3d`, `bands`, `bwait`, `cap`, `cap3d`, `ecpu`, `rcpu`, `t3d`.

**Banc** (x86, 4 processeurs virtuels, deux séries) :
- composition SSE2 (celle que la couche NEON reproduit) : `engA` passe de 1,89–1,90 à 1,02–1,07 ms (Galaxy, ×5) et
  de 1,54–1,62 à 0,98–1,16 ms (MarioKart), soit 28 à 46 % de moins ; un écran sans 3D ne change pas ;
- capture directe de la 3D forcée, ×5 + 3D 2x : Galaxy passe de 51–57 à 59–61 i/s (`wait` de 11–12 à 9 ms) ;
- trois fils au lieu de quatre : moins bien sur ce banc (Galaxy 45–47 contre 51–57 i/s) ; `auto` reste à un fil par
  cœur.

Images et son identiques au cœur de la 831 : 75 cas sur x86 (capture forcée comprise), 39 cas sur AArch64 avec le
JIT et la composition NEON. Couche NEON : 281 048 résultats identiques à la vraie SSE2.

**Attendu sur l'iPhone** (estimation, non mesurée) : si Animal Crossing capture la 3D, la 3D se dessine enfin
pendant la composition 2D, comme prévu pour la 831 (`run` vers 14 à 17 ms au lieu de 23) ; la composition NEON retire
environ 30 % de `2d` (7,5 ms dans la 830, soit 2 à 2,5 ms). Rien ne garantit 60 i/s stables avant la mesure.

**À lire** dans le prochain `session.log` (lignes `core: [rb-perf] …`, toutes les 600 images, même si l'app est
fermée depuis le sélecteur) :
- `cap3d` proche de 600 : le jeu capture la 3D, et ce correctif s'applique ;
- `r3d` proche de 600 ou de 300 : une image 3D par image, ou une sur deux (jeu à 30 i/s) ;
- `t3d` : durée d'un rendu 3D ; au-dessus de 16 ms, la 3D seule empêche le 60 dans ce réglage (alors ×4 + 3D 2x) ;
- `ecpu` contre `run` − `wait` : temps perdu par le fil d'émulation faute de cœur ;
- `rcpu` contre `raster` : idem pour les fils du rastériseur ;
- `run`, `wait`, `2d`, `engA`, `engB`, `end`, `over16`.
