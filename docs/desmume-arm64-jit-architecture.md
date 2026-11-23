# DeSmuME : architecture d'un JIT AArch64 pour RewindBox

*23 novembre 2026 — branche `Claude`. Conception seulement : aucun code du cœur modifié ni compilé, rien mesuré.
Décision du mainteneur : « DS : garder DeSmuME, soit inventif et conçois l'architecture ». Sources relues :
libretro/desmume `95b4d798` (**L**), TASEmulators/desmume `b549f71b` (**T**), melonDS `ff972523`, oaknut
`94c726ce`. Les chiffres de gain sont des estimations ou des affirmations d'auteurs, jamais des mesures RewindBox.*

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

- **Installation.** `rewindbox_libretro_jit_install` copie l'ABI. Au premier `retro_init` en mode JIT, un seul
  `allocate` de 32 à 64 Mio est fait ; il dure jusqu'à la fermeture du cœur.
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
- **Côté RewindBox.**
  - Catalogue : `jitArenaBytes` (32 à 64 Mio) et `jitOverrides` (`desmume_cpu_mode: jit`).
  - La surcharge sans JIT existante (`interpreter`) est conservée.
  - Nouvelle route de compilation depuis la source, comme Beetle et Azahar.
