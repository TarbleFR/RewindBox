# Build 481 — cache d'objets SPU ARM64 persistant (RPCS3), 18 octobre 2026

Mission du mainteneur : étudier l'IPA ARMSX3 `ARMSX3-22185-00412bb6.ipa` et
son annonce (« Compiled code is kept between sessions », « Shader interpreter
turned off »), porter dans NeoStation ce qui réduit les saccades et augmente
les FPS réellement calculés de God of War III, puis livrer une IPA privée.
Candidate : **Build 481**, construite par-dessus la 0.0.8 (Build 480,
`7493d9ba`) sur `Claude`. Le produit hors Core RPCS3 est inchangé.

Ce document distingue les faits établis dans les sources et les binaires, les
hypothèses, les tests exécutés sur l'hôte et la validation iPhone (aucune
dans ce cycle : ni iPhone ni jeux sur ce poste).

## 1. Ce que l'analyse d'ARMSX3 établit

| Point | Constat | Preuve |
|---|---|---|
| Sources de la build iOS | Le préfixe `00412bb6` ne correspond à aucun commit public ; `master` de `ARMSX2/ARMSX3` est `58074a7c` (17 octobre 2026, « Release 1.2.1 »), l'IPA date du 18 octobre. La build iOS vient d'un commit postérieur non publié. | `gh api repos/ARMSX2/ARMSX3/commits/00412bb6` → 422 ; horodatages de `Payload/Harness.app` |
| Mécanisme du cache SPU | Le cache d'objets SPU (`spuobj-v%u-%s/`, clé SHA-1 des réglages, bits matériels, fréquence TSC, CPU) est public : porté de `ouroboros420/rpcsx 8430a6558`, activé sur ARM64 le 30 août 2026 (`a84572bcb`), **désactivé le 31 août** (`457a932c7`) parce que les objets figeaient des adresses hôtes absolues (`movz/movk` sans relocation : `&g_timebase_offs`, puis `vm::g_pages` dans leur arbre). `master` : 12 000 fichiers et reconstruction complète au dépassement. | `rpcs3/Emu/Cell/SPUCommonRecompiler.cpp:1776-1930`, messages des commits |
| Différence du binaire iOS | `MOVZ w8, #40000` dans `spu_runtime::spu_runtime()`, chaînes `SPU object cache over %u files: removed the %u oldest.`, `arm64_codegen_v14`, `spuobj-v%u-%s/`. La version iOS a donc réactivé le cache avec une éviction des plus anciens : le correctif de relocalisation n'est pas publié. | désassemblage statique fourni par le mainteneur ; `strings` de `Harness` |
| Cache pipeline Vulkan | `vkutils/device.cpp` : en-tête (longueur, version, vendorID, deviceID, `pipelineCacheUUID`), limite 128 Mio ; `master` **supprime** le fichier au dépassement, le binaire iOS « keeping the one on disk and not saving more ». Écriture par `fs::file(..., fs::rewrite)` non atomique. | source `master`, chaînes du binaire |
| Chemin PUTLLC 16 octets | « a PUTLLC that changes one 16-byte chunk skips the full lock » (`76dd99d95`, port de RPCS3 `083859b94`, PR #19568 de Yahfz). | source `master` |
| Marqueurs `ARMSX3_*` | `ARMSX3_NO_SPU_BUSY_WAIT`, `ARMSX3_MAX_SPURS`, `ARMSX3_NO_SPURS_SHORTCUT`, `ARMSX3_PUTLLC_SITES` sont des **variables d'environnement d'expérimentation**, lues par `getenv`, désactivées par défaut ; `ARMSX3_SPU_TSC_SCALE` n'existe pas dans `master`. | `SPUThread.cpp:4566-4680, 7118-7290` |
| Mode de shaders | L'annonce retire l'interpréteur (passage à `Async Recompiler (multi-threaded)`). | annonce |

Les chiffres de Black Ops II de l'annonce sont mesurés sur Mac ; rien n'est
transposé à l'iPhone ni à God of War III.

## 2. Ce que l'audit de nos sources établit (arbre `XITRIX/rpcs3@22f1152` + patch 444)

- **Une seule adresse hôte figée dans le traducteur SPU** : `SPU_RdDec`
  lisait `g_timebase_offs` par `CreateIntToPtr(getInt64(&g_timebase_offs))`
  (`SPULLVMRecompiler.cpp:5193`). Tous les autres renvois vers l'hôte sont déjà
  des symboles résolus par MCJIT au chargement : `spu_dispatcher` (→ `tr_all`),
  `spu_escape`, `spu_dispatch`, les points de patch `<hash>-pp-<n>`,
  `spu_segment_base`, et les aides `call(...)` de `cpu_translator`
  (`updateGlobalMapping`). La base mémoire invitée est lue dans
  `spu_thread::memory_base_addr`, les tables (`frest`, `frsqest`, table de
  fonctions) sont des données privées du module relocalisées par le chargeur.
  Les en-têtes ARM64 (`SPUARM64Lowering.h`, `SPUARM64CompareLowering.h`,
  `AArch64JIT.cpp`, passerelle, hachage de réservation) n'en figent aucune.
- La politique iOS résolvait `persistent_spu_object_cache` à `false` quel que
  soit le réglage, avec le texte « Unavailable on ARM64 because cached objects
  contain process-specific addresses ». Le code de clé 444 (`cache_version 5`,
  12 000 fichiers, reconstruction au dépassement) n'était jamais exécuté.
- Le chemin **PUTLLC 16 octets** d'ARMSX3 est déjà dans nos sources
  (`SPUThread.cpp:3588, 3627-3630`, `scan16_rdata`, `range_lock<128>`), avec en
  plus la pré-comparaison avant `vm::writer_lock` de la Build 435 et son
  compteur `wl_putllc_avoided`. Rien à porter.
- Notre cache pipeline Vulkan (`vkutils/device.cpp`, `RPCV` v1, 128 Mio) :
  en-tête magique/version/`vendorID`/`deviceID`/UUID, lecture refusée si taille
  ou en-tête invalides (démarrage vide, fichier conservé), écriture atomique
  par `fs::pending_file`, **jamais de suppression** : au-delà de 128 Mio le
  fichier disque reste tel quel et « cache was not saved ». Point de contrôle
  après le chargement du cache de shaders (`VKGSRender.cpp:1311`) et à l'arrêt.
  C'est déjà le comportement annoncé par ARMSX3 iOS, avec une validation plus
  complète. **Aucun changement.**
- Mode de shaders : le profil God of War III impose
  `Async Recompiler (multi-threaded)` (`rpcs3_game_profile_service.dart`),
  publié dans la base de configuration du Core (`config_database`, validée par
  `cfg_root::validate`) et appliqué au démarrage par `m_add_database_config` ;
  les réglages explicites de l'utilisateur sont rejoués après. **Constat
  annexe** : le défaut global iOS de notre Core est `shader_mode::recompiler`,
  soit « Legacy Recompiler (single-threaded) » (`RPCS3IOSGPUDefaults.h`), donc
  compilation synchrone des shaders pour les titres sans profil (BladeStorm).
  Ce défaut n'est pas modifié dans cette build : il est hors du périmètre
  God of War III et un changement global demande une mesure sur l'iPhone.
- Réglages SPU hôtes : `spu_reservation_busy_waiting_enabled = false`
  (défaut amont, identique à ce que `ARMSX3_NO_SPU_BUSY_WAIT` force),
  `max_spurs_threads = 6`. Aucun changement sans mesure.

## 3. Ce que la Build 481 change (Core RPCS3 seulement, patch canonique `bc63c5da…7a33`)

### 3.1 Objets SPU relocalisables (A)

- `SPULLVMRecompiler.cpp` : `init()` enregistre `spu_timebase_offs →
  &g_timebase_offs` sur le moteur ; `SPU_RdDec` lit
  `m_module->getOrInsertGlobal("spu_timebase_offs", i64)`. Le module n'a plus
  aucune constante d'adresse hôte : une référence externe est relocalisée par
  RuntimeDyld (GOT) dans chaque processus, comme les appels aux aides.
- **Garde de relocalisabilité** (`spu_llvm_module_is_relocatable`) : avant de
  persister un module, parcours des instructions et des initialiseurs de
  globales ; tout `inttoptr` d'une constante ≥ 4 Gio
  (`host_address_floor`, au-dessus de `__PAGEZERO` : toute adresse hôte iOS,
  aucune adresse invitée ni décalage de mémoire locale) refuse la persistance.
  Le module est alors compilé sans cache, compté (`obj_nonreloc`) et signalé
  une fois par processus. Un futur changement du traducteur ne peut plus
  empoisonner le cache comme chez ARMSX3.
- Variantes de repli ARM64 (sans TBL2, sans FMA strict) : suffixes
  `-notbl2`/`-nofma` dans le nom de l'objet (ARMSX3 `a84572bcb`).

### 3.2 Chargement, validation, écriture (A)

- Avant la construction de l'IR, `jit_compiler::load_cached_object` lit
  `<dir>/__spu-0x<entrée>-<hash>.obj.gz`, le **parse** (`ObjectFile::createObjectFile`)
  et **exige le symbole d'entrée défini** ; un fichier illisible, tronqué ou
  étranger est supprimé, compté (`obj_invalid`) et le bloc est compilé
  normalement. MCJIT ne reçoit jamais un objet qu'il ne pourrait pas charger
  (erreur fatale chez lui).
- Sur un succès (« hit »), l'IR est toujours construit (noms des symboles,
  points de patch), mais la passe LLVM, les abaissements ARM64 et
  `verifyModule` sont sautés ; `try_add_cached` donne l'objet préchargé à
  `llvm::ObjectCache` et MCJIT lie l'objet au lieu de générer du code.
- Sur un manque, le code est généré et l'objet écrit par `fs::pending_file`
  (écriture atomique, comptabilité d'espace disque existante, `commit()`
  vérifié) ; l'écriture ratée est comptée (`obj_write_failures`).
- Le chemin générique PPU valide aussi les objets avant MCJIT (un objet PPU
  corrompu recompile au lieu de planter).

### 3.3 Clé, bornes, éviction (A)

- Répertoire `<cache PPU du titre>/spuobj-v6-<clé>/`. Clé SHA-1 : version de
  format (6), `spu_xfloat_accuracy`, `spu_block_size`, `clocks_scale`, dix
  bits de réglages (DFMA, réservations, DMA, profil, vérifications, boucles,
  MFC debug, RSX, savestate), bits matériels (`i8mm`, `dotprod`, `sha3`),
  fréquence TSC, nom CPU LLVM, **identité de codegen SPU**
  (`jit_compiler::spu_codegen_identity` = version LLVM + digest CMake
  `NEOSTATION_SPU_CODEGEN_ID` des sources du traducteur, de l'analyseur, de
  `SPUThread.h`, des abaissements ARM64, de `CPUTranslator`, de `JIT.h`,
  `JITLLVM.cpp` et du correctif de spill LLVM + attributs cibles), commit et
  révision du Core.
- Les répertoires `spuobj-*` d'une autre clé sont supprimés au démarrage.
- Bornes : 40 000 fichiers **et** 512 Mio ; au dépassement, les plus anciens
  (mtime) sont retirés jusqu'à 90 % des deux bornes, une fois par démarrage,
  avant tout worker. **Jamais de purge d'un cache valide.**
- `g_cfg.core.spu_cache` (« SPU Cache ») désactivé = rien de persisté ;
  `spu_debug` conserve le chemin textuel amont sans réutilisation d'objets.
- Réglage « Persistent SPU object cache » : `Automatic` → activé sur ARM64 tant
  que `arm64_objects_relocatable` (compile-time) est vrai ; `Disabled` désactive.
  Texte du catalogue mis à jour (catalogue du Core en anglais, comme ses autres
  entrées : aucune chaîne Flutter ajoutée).

### 3.4 Diagnostics (D)

- `JITPROF` : phases `spu_cache_read` (lecture + décompression, octets),
  `spu_object_load` (liaison d'un hit, remplace `spu_passes`/`spu_codegen`),
  `spu_cache_write` (compression + écriture). Les douze phases 444 gardent
  leur ordre.
- `SPUPROF` : `obj_hits`, `obj_hit_kib`, `obj_misses`, `obj_written`,
  `obj_written_kib`, `obj_write_failures`, `obj_invalid`, `obj_nonreloc`,
  `obj_evicted`, `obj_stale_dirs` (par fenêtre de 5 s). Compteurs atomiques,
  sans allocation ni écriture par événement.
- Journal : `SPU object cache: <dir> (<n> files, <KiB>)`, évictions, répertoires
  retirés, refus de persistance (une ligne par processus).

### 3.5 Non modifié

Compilation SPU différée (`deferred_compile_enabled = false`, test 444
reconduit), module interpréteur SPU (construit par processus, non persisté),
StikJIT et preuves PID/nonce, ABI du Core (30) et ABI NeoSwap, chemins
PUTLLC/PUTLLUC et pré-comparaison 435, cache pipeline Vulkan, mode de shaders,
profils de jeux, autres moteurs, skins, triches, bibliothèque, fermeture
0.0.8. Aucune purge de cache n'est demandée : les anciens fichiers
`v8-…`/`v9-…` PPU et les métadonnées SPU restent utilisés comme avant.

### 3.6 Effet attendu, séparément

- **Démarrage** : au premier lancement d'un titre après cette build, tout est
  compilé une fois et persisté (coût d'écriture en plus, mesuré par
  `spu_cache_write`). La recompilation PPU complète a lieu aussi une fois
  (`JIT.h`/`JITLLVM.cpp` sont dans le digest PPU : identité v9 différente).
  Aux lancements suivants, le préchauffage de chargement (`SPUWARMUP`) lie
  les objets au lieu de les générer : `spu_object_load` remplace
  `spu_passes + spu_codegen` ; `spu_build` (construction de l'IR) subsiste.
- **Saccades de compilation en jeu** : un bloc déjà rencontré dans une session
  précédente est lié, pas généré ; `gameplay_attempts` et `spu_compile_ms`
  doivent baisser à parcours égal à partir de la deuxième session.
- **FPS en régime chaud** : aucune prétention. Quand tout est compilé, le
  cache n'ajoute rien ; les goulots mesurés en Build 411 (verrou exclusif
  `vm::writer_lock` des PUTLLC) ont leur chemin 16 octets déjà en place.
  Les candidats restants d'ARMSX3 (plafond SPURS, attente active, raccourci
  SPURS) sont des réglages désactivés par défaut chez eux aussi ; ils ne sont
  pas copiés sans mesure (§ 6).

## 4. Matrice hypothèse → modification → test → résultat → limite

| Hypothèse | Modification | Test | Résultat | Limite |
|---|---|---|---|---|
| Les objets SPU ARM64 ne sont pas relocalisables à cause d'une adresse figée | symbole `spu_timebase_offs` ; audit regex de tous les `reinterpret_cast`/`IntToPtr` du traducteur et des en-têtes ARM64 | `rpcs3_build481_spu_object_cache_test.py` § câblage (aucune constante d'adresse hôte vers l'IR) | PASS sur l'arbre matérialisé | audit statique des sources, pas désassemblage de chaque objet généré |
| Un objet lié par un autre processus, à d'autres adresses, exécute correctement les symboles externes (données via GOT, appels, table de pointeurs, rodata) | — (mécanisme MCJIT utilisé par le Core) | `rpcs3_spu_object_relocation_test.cpp` : `save` puis `load` dans **deux processus**, triple `aarch64-unknown-linux-android`, PIC, génération de code interdite au chargement, adresses de données et de code différentes vérifiées | exécuté par le run Core `39142102313` (étape de préflight, LLVM 22 du runner) — résultat consigné en § 7 | mémoire gérée par `SectionMemoryManager`, pas `MemoryManager2`/arène iOS ; macOS arm64, pas l'iPhone |
| Un fichier tronqué ou étranger ne doit jamais atteindre MCJIT | validation parse + symbole d'entrée, suppression | même test, mode `corrupt` (tronqué, puis module étranger sous le même nom) | idem | — |
| Un module qui figerait une adresse hôte ne doit pas être persisté | garde `spu_llvm_module_is_relocatable`, seuil 4 Gio | test de politique (`is_host_address_constant`) + câblage ; le garde réel s'exécute sur l'iPhone à chaque manque | PASS (politique), câblage PASS | pas de cas réel déclenché (il n'y a plus d'adresse figée) |
| Les bornes ne doivent jamais purger un cache valide | `plan_eviction` (plus anciens d'abord, 90 %) | test de politique : bornes fichiers, octets, égalité de mtime, vide | PASS (zig localement, clang CI) | l'ordre par mtime dépend de l'horloge du système de fichiers |
| Une variante de repli ne doit pas être servie sous le nom par défaut | suffixes `-notbl2`/`-nofma` | test de politique + câblage (suffixe avant la recherche) | PASS | — |
| La clé doit distinguer Core, LLVM, réglages, CPU | identité SPU + digest CMake, format 6 | câblage (composition de la clé, digest CMake couvrant 20 sources) | PASS | la valeur du digest n'est connue qu'à la configuration CMake du run Core |
| Compteurs sans coût notable | atomiques relaxés, échange par fenêtre | câblage + exécution du registre de phases 444 (15 phases) | PASS | coût non mesuré sur l'iPhone |

## 5. Tests exécutés

Sur ce poste (Windows, zig 0.17.0 `c++` C++20 `-UNDEBUG -Wall -Wextra -Werror`, Python 3.12) :

- `test/native/rpcs3_build481_spu_object_cache_test.cpp` contre
  `rpcs3/Emu/Cell/SPUObjectCachePolicy.h` matérialisé : PASS.
- `test/rpcs3_build481_spu_object_cache_test.py <tree481>` : politique PASS,
  preuve de relocalisation **ignorée** (pas de LLVM sur ce poste), câblage PASS.
- `test/rpcs3_build444_core_delta_test.py <tree481>` (liste de phases étendue à 15) : PASS.
- `build-utils/materialize_rpcs3_core.py` sur un worktree vierge de
  `XITRIX/rpcs3@22f1152` : PASS (212 sections, 212 empreintes), arbre
  **identique** à l'arbre de travail (`diff -r`), un seul avertissement
  d'espace comme avant.
- `test/neo_swap_core_pin_test.py --source-only` et `--source-root <tree481>` : PASS.
- `git diff --check`, `py_compile` : propres.

Confiés à la CI (macOS, LLVM 22, iOS SDK) : porte de syntaxe iOS des unités
modifiées (`JITLLVM.cpp`, `SPUCommonRecompiler.cpp`, `SPULLVMRecompiler.cpp`,
`RPCS3IOSPerformance.cpp`), preuve de relocalisation en deux processus,
construction du Core, validation des exports. Résultats en § 7.

## 6. Pistes ARMSX3 non reprises et pourquoi

| Piste | État chez ARMSX3 | État chez nous | Décision |
|---|---|---|---|
| `ARMSX3_MAX_SPURS` | variable d'environnement ; réglage `max_spurs_threads` (6) | même réglage amont, 6 | pas de copie d'un nombre de threads sans mesure ; candidat de mesure par profil God of War III (`cpu.max_spurs_threads` n'est pas encore un réglage géré par NeoStation) |
| `ARMSX3_NO_SPU_BUSY_WAIT` | force l'attente passive ; leur appareil avait l'attente active à 100 % | attente active désactivée par défaut | sans objet |
| `ARMSX3_NO_SPURS_SHORTCUT` | diagnostic du raccourci SPURS (`relaxed_spurs`) | même raccourci amont | sans objet |
| `ARMSX3_SPU_TSC_SCALE` | absent des sources publiques | — | non transposable sans source |
| Éviction « removed the oldest » à 40 000 | binaire iOS seulement | implémentée avec borne d'octets et marge | reprise |
| Interpréteur de shaders désactivé pour tous | défaut global | profil God of War III déjà asynchrone ; défaut global iOS = Legacy single-threaded (§ 2) | hors périmètre ; à mesurer séparément |
| Cache pipeline : conserver le fichier saturé | binaire iOS | déjà le cas, écriture atomique en plus | aucun changement |

## 7. Identités et résultats CI

- Code : commit `2fffa08bb02b3453e0487f3ed87e97551b5d8ff0` sur `Claude`
  (patch canonique `bc63c5da2dc97dca0f205b132dfb078d53da3d87c6fcf546810468512dd37a33`,
  manifeste 212 fichiers, `PATCH_SHA256` épinglé).
- Runs Core `rpcs3-core.yml` :
  - `39142102313` sur `2fffa08b` : arrêt au préflight, `rpcs3_spu_warmup_test.py`
    ancré sur le commentaire du module interpréteur reformulé (ancrage déplacé
    par `e731ed95`, contrat conservé).
  - `39142620900` sur `e731ed95` : la porte de syntaxe iOS et la **preuve de
    relocalisation en deux processus ont réussi** (LLVM 22.1.8 : objet de
    2 000 octets lié sans génération de code ; données `0x1023a4028 →
    0x1045a8188`, aide `0x102399320 → 0x10459d320`, code `0x1023f8010 →
    0x1045fc010`) ; arrêt sur le scénario `corrupt` du test lui-même (le module
    « étranger » était validé contre le symbole du module d'origine au lieu du
    sien) ; corrigé par `aae1c147`.
  - `39143262614` sur `aae1c147` : préflight complet réussi (preuve en deux
    processus avec scénarios tronqué/étranger, porte de syntaxe iOS) ; arrêt
    dans le script de construction sur `rpcs3_xitrix_v0101_native_test.py`,
    qui lisait l'ancienne constante `cache_version` (contrat déplacé vers
    `format_version` de l'en-tête de politique par `5919be61`).
  - `39144244183` sur `5919be61` : **réussi** (préflight avec preuve en deux
    processus, construction 54 min, exports validés). Core
    `libRPCS3Core.dylib` SHA-256
    `b249523453b3c3188b2f849b1bd87187d259511612170c9167b9420678aef01d`, ABI 30,
    67 entrées de Core épinglées, identité de codegen SPU `72b3b9b3c7883b23`
    (PPU `a58328ba0a0e9be6`), artefact `RPCS3Core-5919be61…` (28 324 684 octets,
    conservé jusqu'au 17 novembre 2026), diagnostics conservés jusqu'au
    1er novembre 2026. Épinglé dans `retroarch-delivery.yml` et `neoswap-ipa.yml`.
- Livraison : *à compléter* (source, run, artefact, IPA, SHA-256, taille).

## 8. Protocole d'essai sur l'iPhone 16 Pro Max

Même titre, même édition et mise à jour, même sauvegarde, mêmes réglages
(limite 30 FPS, 75 %, patches), état thermique comparable, journaux
`RPCS3-diagnostic.log` et `NeoSwap-v1.jsonl` à transmettre sans les ouvrir.

1. **Premier lancement (froid)** de God of War III : recompilation PPU
   complète attendue (identité v9 différente) et compilation SPU complète avec
   écriture (`SPUPROF obj_misses`, `obj_written`, `JITPROF spu_cache_write`).
   Ne pas mesurer cette session, seulement l'enregistrer, et noter la ligne
   `SPU object cache: … (<n> files, <KiB>)` du journal.
2. **Deuxième processus** (quitter NeoStation complètement, relancer le jeu) :
   `obj_hits` doit dominer, `JITPROF spu_object_load` remplacer
   `spu_passes`/`spu_codegen`, `SPUWARMUP elapsed_ms` et
   `COREPROF_RESILIENCE spu_compile_ms` baisser ; `obj_invalid` et
   `obj_nonreloc` doivent rester à 0. Un plantage, un gel ou un `interp_*`
   anormal dans les premières secondes invaliderait la relocalisation : passer
   « Persistent SPU object cache » sur `Disabled` et transmettre le journal.
3. **Troisième processus** après un parcours de 10 minutes dans une zone
   lourde : nombre de `gameplay_attempts` et `spu_compile_ms` en baisse par
   rapport au deuxième ; image, son, cinématiques, commandes, fermeture et
   relancement normaux.
4. **Contrôle** : BladeStorm (ou un autre titre déjà joué) sur le même schéma ;
   comparer avec `tools/compare_rpcs3_neoswap_builds.py` (même IPA, même
   Core, mêmes réglages).
5. Ne jamais prendre une présentation à 60 Hz pour 60 images calculées :
   `COREPROF frames/avg_fps` et `ppu_ms/spu_ms/rsx_ms` font foi.

## 9. Risques et retour arrière sans perte

- Un objet lié dans un mauvais contexte se manifesterait par une faute dès les
  premières secondes de la deuxième session (comme chez ARMSX3). Les trois
  barrières (aucune adresse figée, garde de relocalisabilité, validation avant
  MCJIT) sont vérifiées sur l'hôte, pas sur l'iPhone.
- Retour arrière : réglage `Disabled` (le répertoire reste, inutilisé), ou
  réinstallation de la 0.0.8 : son Core n'exécute jamais le bloc de cache
  (politique `false`), ignore `spuobj-v6-*` et ne touche à rien d'autre.
  Sauvegardes, états, licences RAP, BIOS, bibliothèques et réglages ne sont ni
  lus ni écrits par ce changement. Le répertoire `spuobj-v6-*` peut être
  supprimé à la main dans `RPCS3/Cache/<titre>/` sans conséquence (une
  recompilation).
- Espace disque : au plus 512 Mio par titre, comptés dans la comptabilité
  d'espace existante du JIT (`add_sub_disk_space`), sous le quota de 25 % de
  l'espace libre.

## 10. Crédits

- Mécanisme et clé du cache : ouroboros420/rpcsx `8430a6558`, porté par
  jpolo1224 dans ARMSX3 (`a84572bcb`, analyse de la faute `457a932c7`,
  nommage des variantes). Sources GPL-2.0, conservées avec leurs auteurs.
- Chemin PUTLLC 16 octets : Yahfz, RPCS3 PR #19568 (déjà présent dans notre base).
- Relocalisation par symboles, garde, validation, bornes, identité de codegen,
  compteurs et tests : NeoStation Build 481.
