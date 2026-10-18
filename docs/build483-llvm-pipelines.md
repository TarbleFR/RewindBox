# Build 483 — pipelines LLVM sélectionnables des recompilateurs RPCS3 (God of War III), 18 octobre 2026

Candidate construite par-dessus la Build 482 livrée (`c676b317`, Core RPCS3 481
`5919be61`). Demande du mainteneur : campagne d'optimisation LLVM profonde pour
les scènes lourdes de God of War III (traducteurs PPU/SPU, pipelines IR, backend
ARM64, chemins chauds), au moins trois pistes concrètes, sémantique PS3
préservée, caches cohérents, sélection interne des variantes avec retour à la
référence, nouvelle IPA de test. Contraintes reprises telles quelles : travail
sur `Claude`, aucune release ni poussée sur `main` sans accord ; pas de fichiers
IPS/Jetsam demandés, diagnostics internes de NeoStation seulement ; le chemin
différé de la Build 435 reste désactivé.

Chaque affirmation de ce document porte l'une des étiquettes suivantes :
**observé dans le code**, **mesuré sur hôte** (macOS arm64 du runner, LLVM 22,
noyaux synthétiques), **mesuré sur appareil** (aucun dans ce cycle), **hypothèse
restante**.

## 1. Ce que l'audit établit (observé dans le code)

| Point | Constat | Preuve |
|---|---|---|
| Pipeline SPU de RPCS3 amont (`master` `bd179ffd`, 18 octobre 2026) | `EarlyCSE(memssa)`, `SimplifyCFG`, **`InstCombine`**, `DSE`, `LICM`, `ADCE`, sur x86-64 comme sur ARM64. Le commit `eda7621f` (« Restore SPU InstCombine with matching helper calling conventions ») rétablit InstCombine en donnant aux appels de `spu_test_state` la convention de leur cible. | `rpcs3/Emu/Cell/SPULLVMRecompiler.cpp` amont, `git log` |
| Pipeline SPU d'ARMSX3 (`ab53473f7`, Malcolm, 10 octobre 2026) | Même pipeline avec InstCombine, cherry-pick d'`eda7621f` : la build iOS annoncée tourne **avec** InstCombine sur ARM64. | `ARMSX2/ARMSX3`, `git show ab53473f7` (4 insertions, 2 suppressions dans `SPULLVMRecompiler.cpp`) |
| Pipeline SPU de notre base (XITRIX `22f1152` + patch 481) | `EarlyCSE(memssa)`, `SimplifyCFG`, `DSE`, `LICM`, `ADCE` — **sans InstCombine**, et les deux appels à `m_test_state` sans convention explicite alors que la fonction est déclarée `PreserveMost`/`PreserveAll`. | `SPULLVMRecompiler.cpp:3052-3058` (déclaration), anciens appels nus aux sites `1601` et `11103` |
| Danger de convention | InstCombine **efface** un appel direct vers une fonction **définie** dans le module dont la convention diffère de la sienne (ni l'une ni l'autre compatible C) : il le remplace par `store i1 true, ptr poison`, l'« unreachable non terminal » de LLVM, que DSE/ADCE ou SimplifyCFG réduisent ensuite à rien ou à `unreachable` ; les simples déclarations sont exemptées. Pour `spu_test_state`, le contrôle d'état du thread SPU disparaîtrait donc silencieusement. Vérifié dans `InstCombineCalls.cpp` (identique de LLVM 18 à 22) et prouvé par le mode `cc-hazard` du harnais avec LLVM 22.1.8 (clang 22.1.8 de zig sur ce poste, runner Core). | `llvm/lib/Transforms/InstCombine/InstCombineCalls.cpp` `release/22.x:4681-4706`, `TargetLibraryInfo.cpp:66-95` ; `test/native/rpcs3_llvm_pipeline_harness.cpp` |
| Pipeline PPU amont sur ARM64 | `fpm.addPass(EarlyCSEPass())` est construit mais exécuté sous `#ifdef ARCH_X64 // TODO` : **aucune passe IR PPU sur ARM64** depuis le portage initial de kd-11 (`56cc5d93`, 4 août 2024), sans raison écrite. ARMSX3 n'y touche pas. | `rpcs3/Emu/Cell/PPUThread.cpp` amont `6072`, `6104`, `6122` ; `git show 56cc5d93` |
| Notre PPU depuis la Build 444 | Booléen `ppu_llvm_ir_passes` (défaut off) = EarlyCSE, haché dans le nom d'objet `v9-neostation-…` par le bit `arm64_ir_passes` ; jamais comparé sur l'iPhone. | `PPUThread.cpp:5658`, `5724`, `6227` ; `docs/rpcs3-neoswap-llvm-build444-audit.md` |
| Traducteurs et backend | Les deux traducteurs émettent du code en convention GHC et exécutent `GHC_frame_preservation_pass` comme passe de traducteur **avant** le gestionnaire de passes IR ; le traducteur PPU garde les registres invités en locaux SSA (`RegLoad`/`RegStore`/`FlushRegisters`) et vide vers le thread entre instructions. Le backend cible le CPU hôte (`jit_compiler::cpu`), `dotprod`/`i8mm` activés selon l'hôte, jamais SVE. | `PPUTranslator.cpp:61-65`, `AArch64JIT.h:83`, `CPUTranslator.cpp:202-209` |
| Chemin différé 435 | `deferred_compile_enabled = false` ; inchangé. | `SPUCommonRecompiler.cpp`, garanti par `test/rpcs3_build483_llvm_pipeline_test.py` |

Conclusion de l'audit : la seule différence de pipeline IR entre la build iOS
d'ARMSX3 et la nôtre est **InstCombine sur les blocs SPU** ; côté PPU, ni l'amont
ni ARMSX3 n'exécutent de passe IR sur ARM64, et aucune source publique n'explique
le `TODO`.

## 2. Les trois pistes et leur état

### Piste A — pipeline SPU : InstCombine comme l'amont et ARMSX3 (adoptée, défaut)

- `SPULLVMRecompiler.cpp:4387-4398` : InstCombine entre SimplifyCFG et DSE quand
  le réglage **SPU LLVM pipeline** vaut `Upstream InstCombine` (défaut) ;
  `Reference 481` garde le pipeline précédent pour comparer sur le même
  binaire.
- `SPULLVMRecompiler.cpp:1601` et `11103` : `->setCallingConv(m_test_state->getCallingConv())`
  sur les deux appels, condition d'InstCombine (§ 1).
- Clé du cache d'objets 481 : `fold(spu_pipeline)` juste après
  `fold(object_cache::format_version)` (`SPUCommonRecompiler.cpp:2008-2012`),
  avant l'identité de codegen (`2042`) : chaque pipeline a son répertoire
  `spuobj-v6-<clé>/`, aucun objet n'est partagé entre variantes. La ligne
  `SPU object cache: … pipeline %s` du journal nomme la variante.
- Mesuré sur hôte : § 4. Mesuré sur appareil : aucun.

### Piste B — pipeline PPU : trois niveaux nommés, défaut inchangé (opt-in)

- Réglage **PPU LLVM pipeline (ARM64)** : `Upstream ARM64` (défaut, aucune
  passe, comportement amont et ARMSX3), `EarlyCSE` (le pipeline x86-64 de
  l'amont, identique au booléen 444 qui reste accepté : `ppu_effective_pipeline()`,
  `PPUThread.cpp:191`), `Extended` (`EarlyCSE(memssa)`, `SimplifyCFG`,
  `InstCombine`, `DSE`, `LICM`, `ADCE`, `PPUThread.cpp:6235-6243`), appliqué aux
  deux sites de passes (`6288`, `6313`).
- Chaque niveau nomme ses objets : bits `arm64_ir_passes` /
  `arm64_ir_passes_extended` dans le nom `v9-neostation-…` (`5658-5659`,
  `5704-5713`, `5724`). `Cell/PPUThread.cpp` rejoint le digest
  `NEOSTATION_PPU_CODEGEN_ID` (`rpcs3/Emu/CMakeLists.txt:44`) : toute
  modification future du pipeline PPU change l'identité des objets.
- Pourquoi le défaut ne change pas : aucune production ARM64 (amont, ARMSX3)
  n'exécute de passe IR PPU ; le traducteur PPU produit des locaux SSA déjà
  simples ; la Build 444 avait posé la même condition (comparer JITPROF
  `ppu_opt`/`ppu_codegen` et COREPROF sur l'iPhone avant tout défaut). Les
  noyaux PPU du harnais montrent ce que chaque niveau retire (§ 4), pas ce que
  cela vaut en jeu.

### Piste C — backend ARM64 et chemins chauds : audités, mesurés, non modifiés

- Le harnais compile chaque variante avec la machine cible du Core
  (`aarch64`, CPU `apple-m4`, nom que LLVM résout pour l'A18 Pro,
  `+sha3,+dotprod,+i8mm,-sve,-sve2`) et compte les instructions AArch64 : les
  gains d'InstCombine survivent-ils à l'ISel ? (§ 4, mesuré sur hôte.)
- Aucun changement de CPU cible, de modèle de code, d'attributs (`noalias`,
  `nsw`, `inbounds`, `readonly`), ni de `fast-math`/XFloat : interdits par la
  mission sans justification, et le CPU fait partie de la clé du cache SPU
  (un changement invaliderait tous les objets).
- Chemins chauds hors LLVM déjà alignés sur ARMSX3 par la Build 481 (PUTLLC
  16 octets, cache d'objets SPU, cache de pipeline Vulkan) : rien à reprendre
  (voir `docs/build481-plan.md` § 6).

### Diagnostics

`RPCS3IOSPerformance.cpp` ajoute à la ligne `JITPROF` :
`ppu_pipeline=<0|1|2> ppu_ir_passes=<0|1> spu_pipeline=<0|1>` (ordinaux des
énumérations : PPU 0 = Upstream ARM64, 1 = EarlyCSE, 2 = Extended ; SPU 0 =
Reference 481, 1 = Upstream InstCombine). Une trace d'iPhone nomme donc la
variante qui a produit ses nombres ; `tools/compare_rpcs3_neoswap_builds.py`
reste l'outil de comparaison.

## 3. Cohérence des caches (observé dans le code)

- **PPU** : l'ajout de `PPUThread.cpp` au digest change l'identité
  `v9-neostation-…-<identité>` : **une recompilation PPU complète au premier
  démarrage de chaque titre** après l'installation de la 483, quel que soit le
  niveau choisi. Ensuite, chaque niveau a ses propres objets.
- **SPU** : l'identité de codegen SPU change aussi (sources du traducteur
  modifiées) et la clé plie le pipeline : nouveau répertoire
  `spuobj-v6-<clé>/`, **compilation SPU complète avec écriture au premier
  démarrage**, puis chargement d'objets à partir du deuxième processus comme
  en 481. Le répertoire de la 481 (`spuobj-v6-<ancienne clé>/`) n'est plus lu
  ni purgé par le Core : il peut être supprimé à la main dans
  `RPCS3/Cache/<titre>/` (au plus 512 Mio par titre), sans autre conséquence.
- Changer de pipeline dans les réglages ne mélange jamais d'objets : chaque
  valeur a son répertoire SPU et son nom d'objet PPU. Revenir à `Reference
  481` recompile sous une nouvelle clé (l'identité de codegen 483 diffère de
  la 481) : ce n'est pas une relecture du cache 481.

## 4. Avant / après mesuré sur hôte (noyaux synthétiques, LLVM 22)

Source : `llvm-pipeline-kernels.json` publié par le préflight du run Core
(copie : `docs/evidence/llvm-pipeline-kernels-483.json`). Les noyaux sont
écrits comme les traducteurs émettent (masques SELB, chaînes de comparaison
signées, idiomes de permutation d'octets, bits CR puis branchement, vidages
redondants de registres, rotations-masques, masques de signe flottants) ; ce ne
sont **pas** des sorties des vrais traducteurs et rien ici n'est une mesure
d'iPhone. Toutes les variantes doivent produire des résultats **identiques au
bit près** à la version non optimisée sur des entrées fixes (`all_variants_bit_exact`).

Hôte : `generic` ; cible : `apple-m4` ; résultats identiques au bit près pour toutes les variantes : **oui**.

**Noyaux SPU — Reference 481 → Upstream InstCombine**

| Noyau | Ce qu'il modèle | IR 481 | IR 483 | Δ IR | AArch64 481 | AArch64 483 | Δ AArch64 | Passes 481 (ms) | Passes 483 (ms) |
|---|---|---|---|---|---|---|---|---|---|
| `spu_selb_mask` | SELB as (a & ~m) | (b & m) with redundant mask and xor, as the translator emits before folding | 17 | 17 | +0 % | 9 | 9 | +0 % | 0.08 | 0.17 |
| `spu_cmp_sext_chain` | CGT/CEQ masks combined, inverted and re-tested: compare, sign-extend, or, xor, compare again | 22 | 21 | -5 % | 11 | 12 | +9 % | 0.23 | 0.21 |
| `bswap_idiom` | big-endian loads: manual byte-swap by shifts and masks, and bswap(bswap(x)) round trips | 22 | 14 | -36 % | 13 | 7 | -46 % | 0.08 | 0.23 |
| `float_sign_masks` | fabs/fneg by integer masks on <4 x float>, then fma, as XFloat Approximate lowers them | 21 | 19 | -10 % | 11 | 10 | -9 % | 0.17 | 0.15 |

**Noyaux PPU — Upstream ARM64 (aucune passe) → EarlyCSE → Extended**

| Noyau | Ce qu'il modèle | IR aucune | IR EarlyCSE | IR Extended | AArch64 aucune | AArch64 EarlyCSE | AArch64 Extended | Passes EarlyCSE (ms) | Passes Extended (ms) |
|---|---|---|---|---|---|---|---|---|---|
| `ppu_cr_bits` | cmpd then bc: lt/gt/eq bits stored to the thread, reloaded and combined for the branch | 33 | 30 | 29 | 14 | 14 | 14 | 0.08 | 0.48 |
| `ppu_register_flush` | successive flushes of the same guest registers to the thread between instructions (dead stores) | 19 | 17 | 13 | 8 | 8 | 8 | 0.05 | 0.22 |
| `ppu_rlwinm_rotate` | rlwinm/rlwimi sequences: rotate by shifts and or, then mask and merge | 19 | 18 | 14 | 7 | 7 | 7 | 0.06 | 0.20 |

Les noyaux SPU passent aussi par les niveaux PPU et inversement dans le rapport JSON (cinq variantes par noyau) ; seules les colonnes qui correspondent au traducteur du noyau sont reprises ici. Les temps de passes sont ceux d'un Mac du runner sur un module d'une fonction : ils situent l'ordre de grandeur, pas le coût sur l'iPhone.

## 5. Matrice hypothèse → modification → test → résultat → limite

| Hypothèse | Modification | Test | Résultat | Limite |
|---|---|---|---|---|
| InstCombine réduit le code SPU généré sans changer les résultats | Piste A | `kernels` : IR et AArch64 par noyau SPU, exécution bit-exacte | **Partiellement falsifiée** (hôte) : résultats bit-exacts sur les 4 noyaux ; AArch64 13 → 7 (`bswap_idiom`), 11 → 10 (`float_sign_masks`), 9 → 9 (`spu_selb_mask`), mais **11 → 12** sur `spu_cmp_sext_chain` (une instruction IR de moins, une constante tout-à-un matérialisée par `movi` pour un `cmeq`/`mvn`) ; total 44 → 38 | noyaux synthétiques ; pas de FPS ; la garde directionnelle du test (« jamais plus d'instructions ») a été remplacée par un enregistrement après cette mesure (run `39162763005`) |
| InstCombine seul casserait les appels `m_test_state` | convention posée aux deux sites | `cc-hazard` : après InstCombine seul, l'appel non apparié est effacé (store vers poison) et l'appel apparié conservé ; après le pipeline SPU complet, plus aucun appel non apparié, l'apparié toujours là | voir § 7 (hôte) | — |
| Les objets des variantes ne doivent jamais se mélanger | clé SPU, bits PPU, digest | câblage : ordre des `fold`, bits par niveau, `PPUThread.cpp` dans le digest | PASS (câblage) | identités connues seulement à la configuration CMake du run Core |
| Le booléen 444 garde son sens | `ppu_effective_pipeline()` | câblage : `upstream` + booléen → `early_cse` | PASS | — |
| Un niveau PPU supérieur retire des instructions IR | Piste B | `kernels` : `none ≥ EarlyCSE ≥ Extended` sur les noyaux PPU, puis AArch64 | **Confirmée pour l'IR, sans effet sur le code** (hôte) : IR 33/30/29 (`ppu_cr_bits`), 19/17/13 (`ppu_register_flush`), 19/18/14 (`ppu_rlwinm_rotate`) ; AArch64 **identique aux trois niveaux** (14, 8, 7) : sur ces formes le backend produit déjà le même code sans passe IR | aucune production ARM64 de comparaison ; un gain n'est envisageable que sur de grandes fonctions PPU réelles (hypothèse restante), au prix du temps de compilation au premier démarrage |
| Les garanties 436 et 481 tiennent | aucune | câblage : `deferred_compile_enabled = false`, garde de relocalisabilité, validation avant MCJIT | PASS | — |

## 6. Tests exécutés

Sur ce poste (Windows, Python 3.12, zig 0.17.0 `c++` pour le C++ pur) :

- `test/rpcs3_build483_llvm_pipeline_test.py <tree483> --skip-native` :
  câblage PASS (harnais ignoré : pas de LLVM ici).
- `test/rpcs3_build444_core_delta_test.py <tree483>` (littéraux déplacés vers
  le sélecteur 483) : PASS, y compris le profil de phases compilé par zig.
- `test/neo_swap_core_pin_test.py --source-only --source-root <tree483>` : PASS
  (ABI 30, 69 entrées de Core).
- `build-utils/materialize_rpcs3_core.py` sur un worktree vierge de
  `XITRIX/rpcs3@22f1152` : 214 sections, arbre identique à l'arbre de travail.
- Balayage des ancrages : aucun test hôte ne cite une ligne retirée ou
  modifiée par le delta 483 (11 lignes candidates, 0 occurrence).
- Les huit modules IR du harnais (sept noyaux, `cc-hazard`) analysés et
  vérifiés par le clang de zig (`-target aarch64-macos`, `-O0` et `-O2`) après
  la correction de la ligne `define` du module `cc-hazard` (run Core
  `39161571672`, § 7) : syntaxe seulement, les passes du Core et l'exécution
  restent la preuve CI.
- Tests de contrat du dépôt (`preprocessor_balance`, `embedded_core_validator`,
  `build301_passive_dlopen`, `jit_handshake`, `build258_*`, `build264`,
  `build351`, `build352`, `build353`, `armsx3_performance_patch`,
  `serial_profile_patch`) : PASS. `atomic_startup`, `spu_warmup`, `build435`,
  `shader_storage`, `source_archive`, `xitrix_v0101`, `neoswap_relay`,
  `build481` et la sonde ffmpeg de `core_syntax_gate` demandent clang/LLVM
  macOS : confiés à la CI.
- `git diff --check`, `py_compile` : propres.
- `test/import_memory_candidate_scope_test.py` échoue avant ce cycle et hors
  de lui (18 fichiers ARMSX2 révisés depuis la révision figée, constat déjà
  consigné dans `docs/build445-plan.md`) ; il n'est exécuté par aucun workflow
  de livraison. Son bloc `IPA_WORKFLOW_BUILD483_LINES` est ajouté pour mémoire.

Confiés à la CI (macOS, LLVM 22, iOS SDK) : porte de syntaxe iOS des unités
modifiées (`PPUThread.cpp`, `SPUCommonRecompiler.cpp`, `SPULLVMRecompiler.cpp`,
`RPCS3IOSSettings.cpp`, `RPCS3IOSPerformance.cpp`), preuve 481 en deux
processus, **harnais 483** (`cc-hazard`, `kernels`), construction du Core,
validation des exports. Résultats en § 7.

## 7. Identités et résultats CI

- Code : commit `b5d61a75e1176638de87d3e776294009b0041350` sur `Claude`
  (delta Core + tests + manifeste, patch canonique
  `0fd83bccbdcfbe079236b47e1e3ebd674c70ecb06a2092f426cc88d0b769d843`, 214
  sections, `PATCH_SHA256` épinglé, 69 entrées de Core), puis `349f45f1` et
  `cb097f56` (harnais seulement).
- Runs Core `rpcs3-core.yml` :
  - `39161571672` sur `b5d61a75` : tous les contrats de démarrage, la preuve
    481 en deux processus (LLVM 22.1.8) et la **compilation du harnais 483**
    ont réussi ; arrêt sur la ligne `define` du module IR `cc-hazard` du
    harnais (convention écrite après les paramètres). Corrigé par `349f45f1`
    après analyse des huit modules par le clang 22.1.8 de zig.
  - `39162137490` sur `349f45f1` : le harnais s'exécute ; verdict « call kept »
    pour les deux appelants parce que le détecteur cherchait une instruction
    `unreachable` alors qu'InstCombine efface l'appel et laisse un
    `store i1 true, ptr poison` que DSE/ADCE retirent (reproduit sur ce poste
    avec le même clang 22.1.8 : InstCombine seul → store vers poison ;
    pipeline complet → `unreachable` ou corps vide). Détecteur réécrit par
    `cb097f56` (deux étapes, formes réelles, appel apparié exigé avec sa
    convention) ; aucun test de Core modifié.
  - `39162763005` sur `cb097f56` : **preuve `cc-hazard` réussie** (après
    InstCombine seul : appel non apparié effacé, store vers poison ; appel
    apparié conservé avec sa convention ; idem après le pipeline SPU complet)
    et **35 variantes vérifiées, assemblées pour `apple-m4` et exécutées
    bit-exactement** ; arrêt sur la garde directionnelle du test lui-même
    (`spu_cmp_sext_chain` : 11 → 12 instructions AArch64, § 5). Garde
    remplacée par un enregistrement par `1b4f65e2` : les gardes de
    correction (vérification, sept noyaux, bit-exact, preuve de convention)
    restent bloquantes ; les comptes sont publiés (`summary`) et étiquetés
    « mesuré sur hôte ».
  - `39163125594` sur `1b4f65e2` : **réussi**. Préflight 3 min 15 s (contrats
    de démarrage, preuve 481 en deux processus, porte de syntaxe iOS, harnais
    483 : `cc-hazard` et `kernels` passés, mesures du § 4), construction du
    Core 72 min (20:27–21:40 UTC, LLVM 22.1.8), exports validés. Core
    `libRPCS3Core.dylib` SHA-256
    `8db85fa174c8639b35be581fe3b8dca03ee996502f5e5ace3f169867f44a5b8e`
    (76 844 416 octets, ABI 30, source XITRIX `22f1152`, patch
    `0fd83bcc…9d843`, 69 entrées de Core épinglées, aucune validation
    appareil), identité de codegen PPU `8288754769446e6d` (481 :
    `a58328ba0a0e9be6`), identité de codegen SPU `36eabce56a6bbd8e` (481 :
    `72b3b9b3c7883b23`) : les deux changent, d'où la recompilation complète
    au premier démarrage (§ 3). Artefact `RPCS3Core-1b4f65e2…`
    (28 919 309 octets, conservé jusqu'au 17 novembre 2026), diagnostics
    conservés jusqu'au 1er novembre 2026 (`llvm-pipeline-proof.txt`,
    `llvm-pipeline-kernels.json`, copie dans
    `docs/evidence/llvm-pipeline-kernels-483.json`). Épinglé dans
    `retroarch-delivery.yml`, `neoswap-ipa.yml` et
    `.github/diagnostics/llvmpipe483_delivery.py` ; fermeture vérifiée sur ce
    poste en mode source et en mode évidence (preuves 481 et 483 relues
    depuis l'artefact, identité du Core égale au pin).
- Séquencement avec l'autre session : pendant la construction du Core, la
  branche `Claude` a reçu les commits de la Build 484 (éditeur de commandes
  tactiles, autre session : 69 fichiers sous `packages/`, `lib/`, `test/`,
  aucun n'étant une entrée du Core). Le commit d'épinglage est donc sur
  `Claude` **rebasé** par-dessus eux (`3eae482c`, même diff), et la livraison
  483 est produite depuis le **tag `build-483`** = commit
  `2c0e022f8cf0f95f732cc749d7a47444eb28d3f9` (`1b4f65e2` + cet épinglage),
  pour que la 483 reste « application 482 + Core 483 » sans les changements
  484 non validés, comme l'exige sa fermeture. Aucune branche de travail
  créée, aucune force-push ; la 484 hérite du pin par la branche.
- Livraison `retroarch-delivery.yml` run `39169474336` sur `2c0e022f` (tag
  `build-483`, périmètre `full`, recette `build-utils/delivery-424-recipient.pem`) :
  `checks` (21:48–21:49 UTC) et `native` (21:53–21:54) réutilisent l'évidence
  482 inchangée par `.github/diagnostics/llvmpipe483_delivery.py` (fermeture :
  produit = 482, entrées changées = entrées du Core identiques à `1b4f65e2`,
  preuves 481 et 483 relues depuis l'artefact du run Core ; reçu
  `docs/evidence/llvmpipe483-delivery.json`), `cold` Release iPhone réussi en
  17 min (21:54–22:12 UTC ; `xcode_build` 386 s, signature et export 58 s) ;
  `warm` ignoré. Garde des entrées du Core : 69 entrées authentiques du pin.
- Artefact chiffré `12152521608` (227 411 869 octets, conservé jusqu'au
  1er novembre 2026), déchiffré sur ce poste avec la clé privée 424.
- **IPA `NeoStation-Build483-2c0e022f…-cold.ipa` : 227 199 943 octets,
  SHA-256 `bb8c0f8efeaaf7d719670757624fb23fc595a754dba6680b8b02d9cd95e6e86c`**
  (identique dans `SHA256SUMS`, `signed-payload-identity.json` et la copie
  `C:\Users\Coren\Downloads\NeoStation-Build483-2c0e022f.ipa`). Version
  **0.0.8 (483)** pour l'hôte et les cinq extensions, iOS 18.0 minimum ; 80
  signatures ad hoc vérifiées par la CI ; re-signature Apple par SideStore
  requise (`directAppleInstallationReady: false`,
  `deviceInstallationTested: false`). Ne pas réutiliser le numéro 483.
- Inspection indépendante de l'IPA sur ce poste (Python, sans Xcode), contre
  l'IPA 482 déchiffrée (SHA-256 `1a220c8a…2f6b` revérifié) : ZIP intègre ;
  80 images Mach-O ; hôte et cinq extensions **0.0.8 (483)**, les 74 autres
  bundles gardent leur version 482 (seul `CFBundleVersion` de `DolphinCore`
  suit le numéro de build) ; le Core `libRPCS3Core.dylib` de l'IPA
  (77 463 040 octets, SHA-256
  `d66fdec9177678c36fd2ee1987b1c9ef99e9dbc814153b8764b501adac6d4a09`) a ses
  **31 sections de code et de données identiques** à celles du Core de
  l'artefact `RPCS3Core-1b4f65e2…` (`8db85fa1…5b8e`), les seules différences
  étant la signature ad hoc (`LC_CODE_SIGNATURE` ajouté, `__LINKEDIT`
  agrandi) et une commande de chargement ajustée par l'empaquetage ; il
  contient les chaînes des réglages 483 (`PPU LLVM Pipeline`, `SPU LLVM
  Pipeline`, `Upstream InstCombine`, `Reference 481`, `Upstream ARM64`,
  `ppu_pipeline=%u`, `pipeline %s`) et celles du cache 481. **72 images
  identiques octet pour octet à la 482** (34 cœurs libretro, `App.framework`
  — code Dart AOT —, Flutter, pods, Core ARMSX2 ABI 7, MoltenVK) ;
  `DolphinCore` et les cinq extensions : toutes leurs sections identiques,
  seule la signature change avec le numéro de build ; `Runner` : 47 sections
  sur 48 identiques, seule `__TEXT,__const` diffère (même taille, 233 504
  octets : constantes liées au numéro de build). Aucune validation iPhone.

## 8. Protocole d'essai sur l'iPhone 16 Pro Max

Même titre, même édition, même sauvegarde, mêmes réglages (limite 30 FPS, 75 %,
patches), état thermique comparable ; journaux `RPCS3-diagnostic.log` et
`NeoSwap-v1.jsonl` à transmettre sans les ouvrir. Comparer avec
`tools/compare_rpcs3_neoswap_builds.py` (même appareil, même sauvegarde).

1. **Référence** : dernière session jouée sur la Build 482 (Core 481) dans la
   même zone lourde, si elle existe ; sinon une session 482 avant
   l'installation.
2. **Premier démarrage 483** (défauts : `Upstream ARM64` / `Upstream
   InstCombine`) : recompilation PPU complète et compilation SPU complète avec
   écriture attendues (§ 3). Ne pas mesurer, seulement enregistrer ; vérifier
   la ligne `JITPROF … ppu_pipeline=0 ppu_ir_passes=0 spu_pipeline=1` et la
   ligne `SPU object cache: … pipeline Upstream InstCombine`.
3. **Deuxième processus** (quitter NeoStation complètement) : `SPUPROF
   obj_hits` doit dominer comme en 481 ; `obj_invalid` et `obj_nonreloc` à 0.
   Parcours de 10 minutes dans la zone lourde : relever `COREPROF
   frames/avg_fps`, `ppu_ms/spu_ms/rsx_ms`, `gameplay_attempts`,
   `JITPROF spu_passes/spu_codegen` (compilations en jeu), thermique.
4. **A/B sur le même binaire** : régler **SPU LLVM pipeline** sur `Reference
   481`, relancer deux fois (la première recompile sous sa clé), refaire le
   parcours ; revenir à `Upstream InstCombine`. La différence entre les deux
   deuxièmes processus est l'effet d'InstCombine ; un écart de `avg_fps`
   inférieur au bruit entre deux sessions identiques n'est pas un gain.
5. **PPU, séparément et seulement ensuite** : `EarlyCSE`, puis `Extended`,
   chacun avec son premier démarrage (recompilation PPU) ignoré et un deuxième
   processus mesuré ; relever aussi `JITPROF ppu_opt/ppu_codegen` du premier
   démarrage (coût de compilation). Revenir à `Upstream ARM64`.
6. Un gel, un plantage, une image fausse ou un son anormal dans une variante :
   revenir à la valeur de référence (§ 9) et transmettre le journal ; ne pas
   additionner les variantes.
7. Ne jamais prendre une présentation à 60 Hz pour 60 images calculées :
   `COREPROF frames/avg_fps` et `ppu_ms/spu_ms/rsx_ms` font foi.

## 9. Risques et retour arrière sans perte

- **Risque A** (hypothèse restante) : un bloc SPU réel que InstCombine
  transformerait différemment du pipeline 481 avec un résultat visible. Le
  harnais exige l'égalité bit à bit sur des noyaux, pas sur le jeu ; l'amont
  et ARMSX3 livrent ce pipeline. Retour : `SPU LLVM pipeline` = `Reference
  481` (effet au prochain démarrage, cache séparé), sans rien perdre.
- **Risque B** : un niveau PPU opt-in qui allonge le premier démarrage ou
  change un résultat. Il n'est jamais actif par défaut ; retour : `Upstream
  ARM64`.
- **Coût certain** : un premier démarrage long par titre après l'installation
  (recompilation PPU et SPU complètes, § 3) ; espace disque : un nouveau
  répertoire d'objets SPU par titre, l'ancien restant sur place jusqu'à
  suppression manuelle.
- Réinstaller la Build 482 rétablit le Core 481 : il ignore les réglages
  inconnus, lit son propre répertoire `spuobj-v6-<clé 481>/` s'il existe
  encore et ses objets PPU v9 de l'identité 481. Sauvegardes, états, licences
  RAP, BIOS, bibliothèques et réglages ne sont ni lus ni écrits par ce
  changement.

## 10. Expériences non retenues et pourquoi

| Piste | Décision | Raison | Étiquette |
|---|---|---|---|
| Réactiver la compilation SPU différée (Build 435) | non | interdit par le mainteneur ; `deferred_compile_enabled = false` vérifié | observé dans le code |
| EarlyCSE ou Extended PPU par défaut | non (opt-in hachés) | aucune production ARM64 ne le fait ; condition 444 (comparaison iPhone) non remplie | observé dans le code, mesure appareil absente |
| Pipeline standard LLVM O2/O3 (`PassBuilder`) sur SPU ou PPU | non | hors de toute production RPCS3 ; coût de compilation par bloc en jeu non mesuré sur l'iPhone ; aucune donnée hôte produite pour cette variante | hypothèse restante |
| `fast-math`, changement de XFloat, attributs `noalias`/`nsw`/`inbounds`/`readonly` | non | interdits par la mission sans justification par chemin ; sémantique flottante PS3 | — |
| Changer le CPU cible, le modèle de code ou les attributs du backend | non | le CPU fait partie de la clé du cache SPU et du nom d'objet PPU ; aucun écart avec ARMSX3 constaté | observé dans le code |
| Variables `ARMSX3_*` (busy wait, SPURS, PUTLLC sites) | non | expérimentations désactivées par défaut chez ARMSX3 (`docs/build481-plan.md` § 6) | observé dans le code |
| Correctif `a5c5ed56` et autres commits XITRIX v0.11 non importés | hors cycle | périmètre LLVM ; inchangé depuis la 436 | — |

## 11. Crédits

- RPCS3 (`eda7621f`, rétablissement d'InstCombine avec conventions appariées ;
  kd-11 `56cc5d93`, portage PPU aarch64).
- ARMSX3 (`ab53473f7`, Malcolm, 10 octobre 2026) pour la confirmation qu'InstCombine
  tourne en production sur ARM64 avec la même correction.
- LLVM 22 (InstCombine, EarlyCSE, SimplifyCFG, DSE, LICM, ADCE, MCJIT).
