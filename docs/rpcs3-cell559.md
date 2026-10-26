# RPCS3 iOS 559 — finalisation des optimisations SPU, textures, shaders et copies GPU

26 octobre 2026. Projet `TarbleFR/RewindBox`, branche `Claude`. Base :
`9d0ca40569f8428e29bd4a65f29a330afb25b755`, qui porte le Core 555.
Cible : iPhone 16 Pro Max (8 Go), Dragon Ball Z Budokai HD Collection
(`BLES01658`) et God of War III (`BCES00510`). **Aucun FPS, temps d'image ou
gain sur iPhone n'est revendiqué ici.** Les chiffres ci-dessous sont des
mesures hôtes ou des contrôles de correction.

## 1. Reprise : état réel retrouvé

Le checkout de la session était resté sur `3494edc`, soit 83 commits derrière
`origin/Claude`. Il a été avancé en avance rapide, sans modification locale
perdue. À la reprise, l'historique contient :

- **Core 555** (`f508f1b`, auteur « Tarble FR ») : attribution des readbacks
  GPU de DBZ (`READBACK555`), compteurs de maintenance des textures, correction
  des empreintes de pipelines. Il a été construit (run `40362434134`, dylib
  `ca495ee5…`) mais **n'a jamais été livré** : les IPA 552 à 557 portent
  toujours le Core 551.
- **Bancs de hachage 554** : variantes ARM64 rejetées, faute de gain robuste
  (`docs/rpcs3-cell555.md`). Le hachage de production reste inchangé.
- **Builds 554/557** : import des disques PS3 du dossier bibliothèque. Ils sont
  côté application, sans changement du Core.

Les optimisations décrites comme « engagées » n'existaient dans aucun commit,
aucune branche distante ni aucune PR de `TarbleFR/RewindBox` :
1. contournement LLVM sur un hit du cache SPU ;
2. hachage des textures déjà invalides ;
3. comparaison rapide des vertex programs identiques ;
4. copies évitées en compilation synchrone ;
5. copies GPU dont la destination est intégralement remplacée.

Ce travail interrompu n'a donc jamais atteint le dépôt. Il a été réimplémenté
ici sur la source canonique 555, puis vérifié. Rien de l'état existant n'est
retiré : ISO, NeoSwap, publication JIT, clés de pipelines, attentes hybrides,
profil GoW3, import 554/557 et MeloNX restent inchangés.

## 2. Les optimisations

Toutes sont sous `RPCS3_IOS`, avec les marqueurs `CELL559_*`. Les 268 autres
sources du Core restent identiques octet pour octet au Core 555.

### A. JIT SPU : pas de préparation LLVM sur un hit du cache (`CELL559_SPU_CACHE_HIT_PASSES`)

**Avant.** `compile()` construisait à chaque programme SPU :
- les quatre gestionnaires d'analyse (`Loop`, `Function`, `CGSCC`, `Module`) ;
- le `PassBuilder` avec l'enregistrement de toutes les analyses LLVM ;
- le `FunctionPassManager`.

Cela arrivait même quand un objet compilé était lu dans le cache. Or ces passes
étaient déjà sautées dans ce cas.

**Après.** Ces objets ne sont créés que pour un miss.

**Garanties.**
- Sur un miss, les mêmes passes s'exécutent dans le même ordre sur le même IR.
  Le test compare le bloc avant/après, indentation exceptée.
- Sur un hit, aucun code n'est généré.
- La vérification de l'IR, la persistance et la logique de liaison sont
  inchangées.

**Identité des caches.** `SPULLVMRecompiler.cpp` fait partie de l'identité de
codegen SPU. Sans précaution, ce changement aurait invalidé tous les caches SPU
des utilisateurs : recompilation à froid de GoW3, avec une identité de contrôle
mesurée à `7330ce26f8290f0c`. `JITCacheCompatibility.cmake` reçoit donc un
alias limité à l'empreinte **exacte** de la nouvelle source
(`6b5a1b8d…` → `613a7fa9…`). C'est le mécanisme déjà utilisé en 538, 545 et 547.

Les identités restent **PPU `a987639e9f838d1c`** et **SPU `d070cb361bdef607`**,
comme en 555. Toute modification ultérieure du fichier invalide normalement le
cache.

### B. Textures : plus de hachage des sections déjà invalides (`CELL559_DIRTY_HASH_SKIP`)

Une section « dirty » mais encore verrouillée logiquement était re-hachée par
`sync_protection()`, appelée par `find_cached_texture` et `trim_sections`. C'est
fréquent après un `superseded_by_fbo` partiel. Sous la stratégie de hachage
d'iOS, une telle section est désormais libérée directement, comme le ferait un
hash différent.

Une section dirty n'est jamais échantillonnée avant d'être recréée : son
contenu ne peut plus servir.

**Garanties.**
- Sections propres : toujours hachées. Une texture modifiée reste détectée, et
  le test le vérifie.
- Sections verrouillées par page : inchangées.
- Chaque appelant teste `is_dirty()` avant d'utiliser le résultat, ou l'ignore.
  Le test vérifie l'emplacement exact de ces cinq appels.
- Effet secondaire bénéfique : `create_new_texture` exige
  `ensure(!region.is_locked())` sur une section dirty réutilisable. Avec 559,
  une section dirty à hash inchangé ne peut plus y arriver verrouillée.

### C. Recherche des vertex programs (`CELL559_VP_EXACT_MATCH`)

Chaque recherche réussie comparait la clé instruction par instruction, en
testant le masque bit à bit. Un `memcmp` vectorisé confirme désormais d'un coup
un programme identique.

Si des mots égaux satisfont toute comparaison masquée, l'équivalence est
stricte. Sinon, y compris pour une différence dans un emplacement hors masque,
on retombe sur la comparaison exacte existante. Le hachage et la
`compare_properties` sont inchangés.

### D. Compilation synchrone sans copies superflues (`CELL559_INLINE_CALLBACK`)

**Avant.** Une construction inline de pipeline copiait le vertex program
(ucode et table de sauts) dans le callback. Elle recopiait ensuite deux fois
tout l'état du callback :
- lors du passage par valeur à `build_pipeline` ;
- lors de la conversion vers le `callback_t` du compilateur, inutilisé en mode
  inline.

**Après.**
- Le vertex program est référencé : c'est un état du thread RSX, immuable
  pendant l'appel.
- Le callback est déplacé, sans copie.
- Le compilateur inline reçoit un callback vide.
- Le chemin asynchrone garde ses copies : le callback s'exécute après le retour
  de l'appelant.

**Conservé volontairement.** Le clone du fragment program reste. Son ucode
pointe vers la mémoire invitée, que PPU et SPU peuvent réécrire pendant une
compilation Metal de plusieurs centaines de millisecondes. Le test réécrit
cette mémoire pendant la compilation et vérifie que l'enregistrement disque
garde l'instantané compilé.

### E. Copies GPU vers une destination intégralement remplacée (`CELL559_FULL_OVERWRITE`)

**E1 — destination DMA d'un blit.** Créer une nouvelle section DMA invalide la
plage avec la cause « écriture ». Avant 559, toute section GPU recouverte était
d'abord relue vers le CPU : copie, puis attente de fence sous le verrou des
textures. C'est exactement le type d'attente observé sur DBZ, à 8,3 ms par
image en 553.

Désormais, une section ne l'est plus si tous les octets qu'elle réécrirait
sont écrits par la copie qui suit. Toutes les conditions suivantes sont
requises :
- copie 1:1 avec la même taille de texel ;
- source ni typeless ni réduite ;
- lignes contiguës ou une seule ligne ;
- destination non tuilée ;
- section non framebuffer, non tuilée, entièrement contenue dans la charge
  utile ;
- cause « écriture » à bornes strictes.

La nouvelle section DMA verrouille toutes les pages touchées (`to_page_range`) :
toute lecture CPU relira donc les nouvelles données. La plage est locale au
thread RSX et n'existe que pendant cette invalidation.

**E2 — render target existant.** Un blit qui remplace exactement toute une
cible couleur, simple échantillon et non typeless, ne force plus le rechargement
de l'ancienne mémoire (`force_data_load | erase_bkgnd`). C'était déjà la règle
amont pour une cible de blit nouvellement créée.

**Restent sur le chemin actuel :**
- écriture partielle ou lignes non contiguës ;
- recouvrement ou source réduite ;
- formats différents ou typeless ;
- profondeur/stencil, MSAA ou tuilage ;
- sections framebuffer ;
- cause de lecture.

### F. Validation des textures par lot FIFO (`CELL559_TEXTURE_EPOCH`)

Ajouté pour le coût persistant de GoW3. En 553, ce jeu hachait environ
270 Mio par intervalle, soit 17,4 ms/image de temps textures RSX, alors qu'aucun
shader ne compilait. Ce sont des revalidations de textures **propres**, répétées
draw après draw.

Désormais, une section dont le hash vient d'être confirmé reste validée jusqu'au
prochain point de synchronisation :
- nouvelles commandes rendues visibles par le jeu (nouvelle valeur de `PUT`) ;
- acquisition de sémaphore (`NV406E`) ;
- écriture, démappage ou commit de surface dans le cache de textures ;
- flush de données GPU vers la mémoire invitée ;
- fin d'image.

Sur PS3, une donnée nécessaire à une commande doit être écrite avant que la
commande devienne visible, ou avant que le sémaphore attendu par le RSX ne soit
libéré. Seule une écriture **non synchronisée**, déjà en course avec le RSX réel,
peut apparaître un lot plus tard. Dans le pire cas, elle apparaît une image plus
tard.

**Implémentation.**
- L'époque est lue avant le hachage : une avancée pendant le calcul force une
  nouvelle vérification.
- Un échec n'est jamais mémorisé.
- `protect`, `reset` et `discard` réinitialisent l'état.
- Les sections verrouillées par page sont inchangées.
- Désactivé, l'époque vaut 0 et chaque validation hache comme avant.
- La branche hors iOS de `RSXFIFO::read_put` reste identique à l'amont.

**Réglage.** « Texture Validation Per FIFO Batch »
(`experimental.texture_validation_epoch`). En **Automatique**, il est actif
pour les six identifiants de God of War III seulement (`is_god_of_war_iii_title`)
et inactif pour tous les autres jeux. Activé et Désactivé forcent le choix ; il
prend effet au démarrage suivant. Aucun fichier de l'application n'est modifié.
Le journal de démarrage indique `texture_validation_epoch=0/1`.

**Si une texture semble figée ou en retard dans GoW3**, passer ce réglage à
Désactivé pour revenir exactement au comportement 555.

### Mesure sur appareil (`COREPROF OPT559`)

Une ligne bornée par fenêtre de profilage :
- `dirty_hash_releases` et leurs octets ;
- `dma_flush_skips` et leurs octets ;
- `rt_reload_skips` et leurs octets ;
- `texture_epoch` (actif ou non), `epoch_skips` et leurs octets ;
- `epoch_advances`, le nombre de points de synchronisation.

Ce sont des compteurs atomiques fixes, sans allocation. Ils permettront
d'attribuer sur iPhone le travail évité, à côté de `READBACK555` et du volume
de hachage de `JITMEM`.

## 3. Validation

**Delta canonique.**
- `embedded-core.patch` est régénéré depuis l'amont `22f11527`. La méthode
  reproduit le patch 555 octet pour octet.
- Il s'applique sur une copie vierge, avec les 286 empreintes de post-image
  vérifiées.
- La fixture `test/fixtures/rpcs3_cell559.diff` reconstruit exactement les
  préimages 555.

**Compilation de production, LLVM 22.1.8** (`ca7933e47d3a`, le commit LLVM
épinglé par le Core), cible ARM64, `RPCS3_IOS` :
- `ProgramStateCache.cpp`, `VKTextureCache.cpp` (`texture_cache*.h`),
  `texture_cache.cpp`, `RSXFIFO.cpp`, `nv406e.cpp` ;
- `RPCS3IOSExperimentalPolicy.cpp`, `RPCS3IOSSettings.cpp` ;
- `SPULLVMRecompiler.cpp` ;
- `RPCS3IOSPerformance.cpp`, avec des shims d'en-têtes Apple pour la seule
  syntaxe ;
- les trois instanciations de `get_graphics_pipeline` : inline, asynchrone et
  préchargement.

Elles compilent sans erreur. Les diagnostics avec les `-Werror` du projet et
`-Wshadow` sont identiques avant et après.

**Tests de source existants du script de build.** Les 9 tests passent sur la
post-image 559. `neo_swap_core_pin_test.py` échoue déjà sur la base, avec un pin
historique sans `rpcs3_restore_eof_test.py`. Cet échec, documenté en 542/555,
n'est pas présenté comme réussi.

**`test/rpcs3_cell559_test.py`.** Il exécute les corps de production extraits
du source 559 contre leur préimage 555 authentifiée, sous ASan+UBSan puis TSan.
Résultats :

| Cas | Résultat hôte (x86-64, clang 22.1.8) |
|---|---|
| A — bloc de passes | identique hors indentation ; construit seulement sur miss |
| A — identités de cache | PPU/SPU inchangées ; sans alias, SPU deviendrait `7330ce26f8290f0c` |
| B — 16 états de section | 14 identiques ; 2 dirty hachées → libérées sans hash (4 → 2 hachages) ; texture propre modifiée toujours détectée |
| C — 40 000 paires de programmes | résultat identique à 555 dans tous les cas (répétitions, différences masquées/non masquées, propriétés, tailles, tables de sauts) |
| D — construction inline, VP 512 instr. + FP 2 Kio | 35 → 10 allocations ; 53 324 → 13 532 octets ; instantané FP conservé pendant une réécriture invitée ; build asynchrone sûr après destruction de l'appelant (ASan) |
| F — époque de validation | désactivée : identique à 555 (10 validations = 10 hachages) ; activée : 0 hachage dans une époque, modification détectée après un point de synchronisation, échec jamais mémorisé, époque lue avant le hachage, sections verrouillées par page inchangées, seul un nouveau `PUT` ouvre une époque |
| E — 288 combinaisons d'invalidation | 286 identiques ; 2 readbacks évités (DMA et blit_engine_dst entièrement couverts) ; 60 000 copies DMA comparées à un modèle octet par octet ; 60 000 rectangles comparés à un modèle pixel par pixel ; plage locale au thread |

**Benchmarks hôtes** (`--benchmark`, x86-64 Xeon 2,8 GHz, LLVM 22.1.8, `-O2`,
médianes appariées). Ce ne sont pas des mesures iPhone :

| Mesure | 555 | 559 |
|---|---:|---:|
| Comparaison d'un VP identique, 64 instr. | 126,6 ns | 22,8 ns |
| 128 instr. | 238,0 ns | 37,5 ns |
| 256 instr. | 462,4 ns | 69,2 ns |
| 512 instr. | 944,1 ns | 128,6 ns |
| Préparation LLVM par hit du cache SPU (pipeline `upstream`) | 5,61 µs | 0 |

Ordre de grandeur pour A : le log 541 comptait 4 933 hits SPU. Au coût hôte
mesuré, cela représente environ 28 ms de CPU par session. Le gain est réel mais
**modeste** : il ne supprime pas les pauses de plusieurs secondes de GoW3.

**ARM64.** Les mêmes harnais sont compilés par LLVM 22.1.8 pour
`aarch64-linux-gnu -mcpu=apple-a7 -march=armv8.4-a`, les options du Core. Ils
sont exécutés sous `qemu-aarch64-static` avec UBSan en mode trap. B, C, D et E
passent avec des résultats identiques à x86-64. Les empreintes des harnais sont
identiques à celles du run hôte final. Il s'agit de correction seulement :
aucun chiffre de performance sous émulation.

Le reçu complet est dans `evidence/rpcs3-cell559-host-linux.json` : pré-vol du
pilote CI, authentification du Core 555, rapports, ARM64, syntaxe et tests
existants. Le pilote `rpcs3cell559_core.py` a été exécuté de bout en bout sur
une source fraîchement matérialisée. Il authentifie l'artefact du Core 555
(`12668749038`, SHA-256 `1fea0ba7…`) et le chemin `--verify-reuse` passe.
Le workflow `rpcs3-cell559-core.yml` réexécute toute la suite et les benchmarks
nativement sur le runner macOS ARM64 (Apple Silicon), puis construit le vrai
Core iPhone.

## 4. Ce qui reste à mesurer sur iPhone

Les effets en jeu ne sont **pas confirmés** :
- FPS moyen ;
- 1 % low, p95/p99 ;
- pauses supérieures à 50/100/500 ms ;
- compilation SPU et shaders ;
- attentes GPU ;
- mémoire.

Attendu, sans preuve :
- DBZ : moins d'attentes de fence si ses readbacks viennent de destinations DMA
  entièrement réécrites. À vérifier avec `READBACK555 blit_destination_dma`
  et `OPT559 dma_flush_skips`.
- GoW3 : moins de hachage par image avec F. Le gain dépend du nombre de points
  de synchronisation par image (`epoch_advances`) : il vaut au plus les
  ~17 ms/image de temps textures mesurés en 553.
- Les deux jeux : moins de CPU RSX sur les recherches de shaders et les
  compilations inline. Moins de hachage de sections invalides
  (`dirty_hash_releases`).

Protocole : celui de `docs/rpcs3-cell555.md`, avec les mêmes scènes, réglages
et état thermique, des caches froids puis chauds, et une session de 30 minutes.
Il faut comparer 551/555/559 avec `OPT559`, `READBACK555`, `SHADERCOST534` et
`JITPROF`.

## 5. Problèmes restants

- **GoW3, coût du hachage** : traité par F, en automatique pour GoW3 seulement.
  Il reste à le valider sur iPhone (rendu, `epoch_skips`, temps d'image) ; il
  peut être désactivé dans les réglages.
- **Pauses de pipelines Metal** : non traitées dans le Core. En 553, le
  pilote MoltenVK/Metal représentait l'essentiel des 29 s de compilation de
  GoW3. Le mode « Async » éviterait ces pauses en sautant des draws, ce que le
  mainteneur a exclu (décision 551). 559 réduit seulement le travail CPU autour :
  C, D et la publication différée 543.
- **Reprise SPU de GoW3** : non traitée au-delà de A. Après un hit, le coût
  restant est la reconstruction de l'IR, nécessaire à la liaison de l'objet en
  cache. L'éditeur de liens « objet minimal » qui l'éviterait
  (`try_add_minimal_object`) reste un prototype désactivé, en attente d'une
  preuve sur un vrai jeu (`AGENTS.md`, audit mémoire du 23 octobre). L'activer
  sans essai sur iPhone risquerait un plantage du JIT.
- **`neo_swap_core_pin_test.py`** : ce n'est pas un défaut du moteur. Ce test
  vérifie que le workflow **public** `neoswap-ipa.yml` épingle un Core
  contenant toutes les entrées actuelles. Il est resté sur `cfe92344`. Le
  rééplinger ferait construire l'IPA publique avec un Core non validé sur
  appareil ; c'est donc laissé au mainteneur. Le contrat de source
  (`--source-only`, utilisé par la CI 559) passe.
- **Livraison** : le Core 559 est construit par `rpcs3-cell559-core.yml`.
  L'IPA privée 559 se prépare sur l'arbre livré 558. Aucune release.
