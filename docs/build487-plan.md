# Build 487 — correctifs de l'audit des goulots RPCS3 (diagnostics et leviers sélectionnables), 19 octobre 2026

Candidate construite par-dessus la Build 486 livrée (`b18c30cd`, Core RPCS3 483
`1b4f65e2`). Demande du mainteneur, après l'audit
`docs/rpcs3-bottleneck-audit-2026-10-18.md` : « établis tes correctifs suite à
l'audit ». Contraintes reprises telles quelles : travail sur `Claude` seulement,
rien sur `main`, aucune release ; aucun rapport `.ips`, Jetsam ou watchdog
demandé ; la compilation SPU différée de la Build 435 reste désactivée ; aucun
gain n'est annoncé sans mesure sur l'iPhone.

Chaque affirmation porte l'une des étiquettes **observé dans le code**,
**exécuté sur hôte** (Linux du conteneur ou macOS du runner Core), **mesuré sur
appareil** (aucun dans ce cycle), **hypothèse restante**.

## 1. Ce que la Build 487 corrige, et ce qu'elle ne prétend pas corriger

L'audit a établi que les journaux fournis ne contenaient aucune seconde de jeu
de God of War III ni de GTA V, que les causes décisives (profil GoW III jamais
appliqué, recompilation PPU après un état, gel de Fallout 3) restaient des
hypothèses faute d'observabilité, et que les leviers LLVM n'étaient pas
mesurables. La Build 487 fait donc deux choses :

1. **Rendre la prochaine capture décisive** (diagnostics D1–D10 de l'audit) sans
   rien changer au jeu.
2. **Exposer les leviers de l'audit comme réglages** (L2, L3, L5, L9) avec un
   retour à la référence ; leurs défauts gardent le comportement de jeu de la
   Build 483, sauf la rétention des répertoires d'objets SPU, qui est une
   politique de cache.

Elle ne prétend corriger ni le gel de Fallout 3, ni l'absence du profil GoW III,
ni la recompilation après un état : elle permet de les trancher sur l'iPhone.

## 2. Diagnostics (Core `NEOSTATION_BUILD487_DIAGNOSTICS_V1`, hôte `NEOSTATION_BUILD487_HOST_DIAGNOSTICS_V1`)

| # | Ajout | Où | Ce que la capture montrera |
|---|---|---|---|
| D1 | `rpcs3_ios_performance_metrics` grandit de 48 à 72 octets après `memory_total_bytes` : `guest_frames_presented`, `native_ui_visible`, `emulation_state`, `boot_progress_completed/total`, bits de validité 4–7, écrits seulement si `struct_size` couvre la nouvelle taille ; `performance_sample` gagne `emu_state= boot_progress= guest_frames= native_ui=` (`-` sans le bit) | `rpcs3/ios/RPCS3IOS.h`, `RPCS3IOSPerformance.cpp`, `RPCS3IOS.cpp` ; hôte `Rpcs3CoreABI.h`, `Rpcs3InternalBridgePlugin.mm` | distinguer « jeu à 30 fps » de « boîte de progression à 30 fps » (cas GTA V) |
| D2 | `COREPROF` ajoute `other_ms window_ms ppu/spu/rsx/jit/other_cores compile_threads compile_cores other_threads rsx_fifo_busy rsx_thread_cpu top=<cinq threads>` et s'émet aussi dans une fenêtre sans image (sauf émulateur arrêté) | `RPCS3IOSPerformance.cpp`, `RPCS3IOSProfilerHelpers.h` | nommer le consommateur de CPU, voir un gel |
| D3 | `CONFIG_LAYERS title= name= database= legacy_custom= legacy_path= sparse_overrides= shader_mode= frame_limit= wcb= wdb= rsx_res= spu_block= spu_decoder= ppu_decoder= async_tex= max_spurs= getllar_pct=`, une fois par démarrage, d'après le chemin réellement suivi | `System.cpp`, `RPCS3IOSBootDiagnostics.h` | prouver quelle couche de configuration était active (profil GoW III) |
| D4 | `NEOSTATION_RESTART reason=<savestate_create|savestate_load|game_setting:<clé>|home_menu|sys_game|other> title= detail=`, une ligne par redémarrage interne | `System.cpp`, `RPCS3IOS.cpp`, menus Home, `sys_game.cpp` | relier une recompilation à sa cause |
| D5 | `MUTEX_DESTROY_BUSY mutex_id= owner_id= owner_name= caller_id= caller_name=` au site `CELL_EBUSY` | `sys_mutex.cpp` | relier l'erreur de Fallout 3 au thread propriétaire |
| D6 | `FREEZE_DUMP` (64 lignes au plus, une fois par 30 s) des threads PPU/SPU/RSX quand aucune image n'a été présentée depuis plus de 3 s alors qu'un groupe dépasse 0,5 cœur et que l'émulateur tourne | `RPCS3IOSFreezeDump.{h,cpp}` | établir ce que font les threads pendant un gel |
| D7 | `RANGELOCKPROF` ajoute le maintien maximal par source | `RPCS3IOSPerformance.cpp` | distinguer beaucoup de verrous courts d'un long |
| D8 | deux lignes `JITPROF_BOOT` par démarrage : `session= boot_kind= modules_total= modules_compiled= modules_cached= modules_existing= ppu_cache_hits= ppu_cache_misses= wall_ms=` + les neuf phases PPU de `JITPROF` + `headroom_samples= headroom_min_mib= ppu_pipeline= ppu_ir_passes= spu_pipeline=`, puis `session= boot_kind= part=spu` + les six phases SPU (toutes les phases sont toujours écrites ; la coupure garde chaque ligne sous la limite de 1 Kio des jalons, préfixe de thread compris) | `PPUThread.cpp`, `Utilities/JITPhaseProfile.h` (totaux monotones additifs), `RPCS3IOSBootDiagnostics.h` | coût réel d'une recompilation PPU sur l'iPhone |
| D9 | `RPCS3-diagnostic.log` tourne vers `RPCS3-diagnostic.1.log` au lieu d'être tronqué ; `neoswap_guest_sample_ext` (phase `sample`) n'est écrit que si ses compteurs changent, plus une ligne par 60 s | `Rpcs3Diagnostics.mm`, `Rpcs3InternalBridgePlugin.mm` | couvrir le démarrage d'une session de 30 min |
| D10 | `SAVESTATE_BOOT` (deux lignes) sur un démarrage depuis un état : `applied_patches seg0_code_end funcs fragments`, puis `ppu_cache_hits ppu_cache_misses objects_loaded link_ms fragments_total` | `PPUThread.cpp` | savoir si un chargement d'état recompile et pourquoi |
| L1 | l'hôte laisse passer `JITPROF`, `JITPROF_BOOT`, `CONFIG_LAYERS`, `NEOSTATION_RESTART`, `SAVESTATE_BOOT`, `FREEZE_DUMP`, `MUTEX_DESTROY_BUSY` ; jalons `jitprof_boot`, `config_layers`, `internal_restart`, `savestate_boot`, `freeze_dump` (première ligne, 512 octets), `mutex_destroy_busy` (64 par processus) | `Rpcs3InternalBridgePlugin.mm` | les lignes survivent à la rotation de 2 Mio |

Le compteur `rsx` (audit § 6.1) est corrigé dans le même lot : horodatage
initialisé au démarrage du thread RSX, recalcul aussi sur base de temps,
comptage de l'attente FIFO vide et de la pause, champs `rsx_fifo_busy` et
`rsx_thread_cpu`. Conséquence observée dans le code : la première valeur de
`gpu_usage_percent` vaut 0 sur une fenêtre vide au lieu d'environ 100 %.

## 3. Leviers (réglages du nœud « iOS Experimental » du Core, catalogue en anglais)

| Levier | Réglage | Défaut | Autre valeur | Établi dans le code | Hypothèse à mesurer |
|---|---|---|---|---|---|
| L2 | `SPU Spin Timing` (`experimental.spu_spin_timing`) | Reference : constantes en ticks de la 483 (1 000 / 5 000 / 400 000 ticks = 41,7 µs / 208 µs / 16,7 ms à 24 MHz) | Calibrated : seuils GETLLAR en temps via `cntfrq_el0`, durées voulues par l'amont sur un TSC à 3 GHz (333 ns / 1,67 µs / 133 µs = 8 / 40 / 3 200 ticks) ; appelle `utils::init_arm_timer_scale()` | `init_arm_timer_scale()` calcule `cntfrq / 30 000 000`, nul sous 30 MHz : à 24 MHz l'échelle reste 1 et `busy_wait(n)` est identique dans les deux modes ; seules les trois bornes GETLLAR changent réellement | moins de CPU brûlé en attente de réservation, latence de réveil possible |
| L3 | `RSX FIFO Idle Wait` (`experimental.fifo_idle_mode`) | Yield (483) | Bounded sleep : `sleep_for(100 µs)` après les huit spins | la boucle FIFO vide de Fallout 3 brûlait ≈ 0,85 cœur à 0–1 % d'occupation | suppression de ce spin en scène légère ; latence de reprise de quelques centaines de µs |
| L5 | `SPU Object Cache Retained Keys` (`experimental.spu_object_cache_retained_keys`, 1–4) | 2 | 1 = comportement 481/483 | répertoire de la clé courante toujours gardé ; jusqu'à N−1 autres `spuobj-v6-*` du même Core et du même CPU (fichier `neostation-build.id`) dans les bornes communes 40 000 fichiers / 512 Mio ; autres formats, Cores et CPU toujours supprimés | un A/B de réglage SPU ne recompile plus à chaque bascule |
| L9 | `SPU Warmup Scope` (`experimental.spu_warmup_scope`) | God of War III | All titles with metadata | le préchauffage n'était lancé que pour GoW III | moins de compilations SPU en jeu, écran de chargement plus long |

La ligne `Resolved boot policy` garde ses champs 483 et ajoute
`spin_timing= fifo_idle= spuobj_keys= warmup_scope= cntfrq= timer_scale= getllar_ticks=`.
Aucun de ces réglages n'entre dans une clé de cache ni ne change le code généré.

Non repris dans cette build, et pourquoi : L4 (pipelines 483, déjà livrés) ; L6
`SPU Block Size` et L7 `Max SPURS Threads` (réglages amont existants, à
comparer par titre avec le protocole) ; L8 QoS des threads auxiliaires et L10
`max_llvm_threads` (risques audio et mémoire, à décider après une capture) ;
L11 identité d'objet PPU stable après un état (à décider après D10).

## 4. Ce qui ne change pas (observé dans le code, vérifié par test)

- Les fichiers de génération de code (traducteurs PPU/SPU, `CPUTranslator.h`,
  `JIT.h`, `JITLLVM.cpp`, passerelles AArch64, `PPUAnalyser.cpp`) sont
  identiques octet pour octet à la Build 483 ; les lignes qui composent la clé
  du cache d'objets SPU et le nom d'objet PPU sont identiques à la 483
  (`test/rpcs3_build487_core_diagnostics_test.py`).
- Compilation SPU différée toujours désactivée ; ABI principale 30 inchangée ;
  aucune exportation retirée ; Core ARMSX2, Dolphin, cœurs libretro, catalogues
  et skins inchangés.

**Conséquence certaine** : `PPUThread.cpp`, `Utilities/JITPhaseProfile.h` et
`SPUCommonRecompiler.cpp` font partie des empreintes de codegen calculées par
CMake (`rpcs3/Emu/CMakeLists.txt`). Nouvelle identité de codegen PPU (et SPU
par `SPUCommonRecompiler.cpp`) : recompilation complète au premier démarrage
de chaque titre après l'installation, comme après la 483. Les objets PPU de la
483 sont conservés sur le disque (aucune purge : l'espace occupé par le cache
PPU double jusqu'à suppression manuelle) ; le répertoire SPU de la 483 (sans
fichier marqueur) est supprimé à ce démarrage. Le premier démarrage après
installation doit être écarté de toute comparaison. Le run Core imprime les
deux identités (`NeoStation PPU codegen identity:`,
`NeoStation SPU codegen identity:`), à consigner au § 7.

## 5. Vérifications exécutées

Exécuté dans le conteneur Linux (aucune compilation iOS possible ici) :

| Vérification | Résultat |
|---|---|
| Relecture contradictoire des trois lots Core (un relecteur par lot, puis correction) | 16 constats, tous confirmés ou documentés ; corrigés : indicateur `native_ui_visible` qui restait à 1 (liste d'overlays jamais vidée), test de contrat `RPCS3IOSContractTests.cpp` resté à 48 octets, pause comptée deux fois comme inactivité RSX, inactivité non comptée pendant les spins NOP/saut-sur-soi, verrous bloquants du vidage de gel (remplacés par des essais), lecture concurrente de l'état du cycle de vie, `MUTEX_DESTROY_BUSY` non borné dans le Core (64 puis 1/1024), marqueur de rétention incapable de distinguer deux builds du Core (identité de codegen SPU ajoutée), date du répertoire non rafraîchie, coût quadratique de `entries_left_in`, portée du réglage de rétention, `JITPROF_BOOT` au-delà de 1 Kio (coupé en deux lignes), `memcpy` avec pointeur nul (UB), redémarrage exitspawn non signalé |
| Vérification syntaxique différentielle de chaque fichier Core modifié (clang 18, C++23, `-DRPCS3_IOS`, en-têtes amont réels : yaml-cpp, asmjit, stb, Fusion, zstd, pugixml, zlib, wolfSSL, LLVM 20), en x86-64 et en aarch64, contre l'arbre 483 | 17 fichiers : **aucune erreur nouvelle** ; les erreurs restantes sont identiques à la 483 (frameworks Apple absents, écarts LLVM 20/22). Les blocs `__APPLE__` (échantillonnage `task_threads`) ne sont pas couverts par cette vérification |
| `test/rpcs3_build487_core_diagnostics_test.py` sur le delta matérialisé | 4 exécutables (115 + 54 + 55 + 25 vérifications, aussi sous ASan/UBSan avec g++), 10 sources de génération de code identiques à la 483, lignes de clé SPU et de nom d'objet PPU identiques, câblage et défauts |
| `test/rpcs3_build487_host_diagnostics_test.py --core` | bloc d'admission réel exécuté, jalons et plafond, contrats, disposition de l'ABI (72 octets), miroir égal à l'en-tête du Core |
| 33 tests Core existants prenant l'arbre en argument, sur la 483 et sur la 487 | résultats identiques ; les 7 échecs sont les mêmes sur les deux arbres (environnement : sous-module zstd absent, ancres audio, historique Git superficiel) |
| Delta canonique régénéré (`build-utils/rpcs3/regenerate_canonical_delta.py`) | 226 sections, SHA-256 `61e41b7d…975e`, appliqué sur un clone amont vierge, toutes les post-images vérifiées ; l'outil reproduit le delta 483 à l'octet près hors lignes `index` |

Non vérifié ici : compilation iOS (porte de syntaxe puis construction du Core en CI macOS), comportement sur l'iPhone.

## 6. Protocole de capture sur l'iPhone

1. Installer la Build 487 (re-signature SideStore), lancer chaque titre une
   première fois et l'écarter (recompilation certaine, § 4).
2. Ne comparer que des captures au même état thermique ; écarter toute
   fenêtre où `emu_state` n'est pas `running` ou où `guest_frames` vaut 0.
3. God of War III : relever le jalon `config_layers` du démarrage. Si
   `legacy_custom=1`, le fichier nommé par `legacy_path` explique l'absence du
   profil (hypothèse a de l'audit) ; si `database=1` et `fifo=4096 getllar=1`
   dans `boot_policy`, le profil est actif.
4. Après une création ou un chargement d'état : jalons `internal_restart`,
   `savestate_boot` et `jitprof_boot` (`modules_compiled`, `ppu_cache_misses`,
   `wall_ms`).
5. En cas de gel : jalon `freeze_dump`, puis les lignes `FREEZE_DUMP` complètes
   dans `RPCS3-diagnostic.log` ou `RPCS3-diagnostic.1.log` ; `mutex_destroy_busy`.
6. Leviers, un à la fois, deux processus par variante (le premier écarté) :
   `RSX FIFO Idle Wait` Yield puis Bounded sleep ; `SPU Spin Timing` Reference
   puis Calibrated ; `SPU Warmup Scope`. Champs : `COREPROF frametime/p95/p99`,
   `rsx_thread_cpu`, `spu_cores`, `guest_frames`, `JITPROF`, `SPUPROF`.

## 7. Identités et résultats CI

### Core RPCS3 487

- `rpcs3-core.yml` run `39251938919` sur `1cf0219773d4c64922367151de3508f5dbcb9c8e`,
  job « RPCS3 Core arm64 with NeoSwap client » (`118063361933`) réussi à la
  **tentative 2**. La tentative 1 s'est arrêtée sur l'expiration de la fixture
  existante `run-minecraft-fence-tests.py --native-atomic`, dont les entrées
  ne changent pas dans cette build (seul un commentaire de `util/asm.hpp`) ;
  les tâches échouées ont été relancées une seule fois, comme le prévoient
  les consignes. L'échec de la tentative 1 n'est pas compté comme un succès.
- Préflight exécuté : preuve 481 en deux processus, harnais 483 (LLVM 22),
  test Core 487 (`PASS: Build 487 Core diagnostics and levers`), test 258,
  tests hôtes 487 sur macOS ; porte de syntaxe iOS ; construction du Core.
- Core `libRPCS3Core.dylib` SHA-256
  `6b64fe7aeca17325592f478a8eb97d08187721127a586bd6f007f71cbdd11c73`, ABI 30,
  patch canonique `61e41b7df09d77b016cddbceebff14a14502632ea714af70ea5ace1b76ea975e`.
- Artefact Core `12191176025` (28 958 094 octets, archive SHA-256
  `10d6c7416a83a8c8e5fefb0847b13cbedbf96ce0bc275d403c9ac124abd6f473`) ;
  diagnostics `12191576064` (archive SHA-256
  `76eb7088986d5dbd45bf4e2e8a3bc452c821114da56dc2619316400db4536866`).
  Les deux tentatives ont publié un artefact de diagnostics sous le même nom :
  la porte de livraison lit celui de la tentative 2 par son identifiant,
  jamais par son nom, et vérifie son nom et son run.
- Épinglé dans `retroarch-delivery.yml` (deux tâches) et `neoswap-ipa.yml` ;
  `test/neo_swap_core_pin_test.py` et `--rpc-core-inputs` de la porte
  (76 entrées) réussis dans le conteneur.

### Livraison

- Source livrée `fad5eac6f793672240d2cb5f3559da73a40226f8`, tête de `Claude` au
  lancement. Le tag `build-487` n'a pas pu être poussé : le proxy Git de la
  session n'autorise que la branche `Claude` (HTTP 403), et cette restriction
  n'a pas été contournée. Le `head_sha` du run est la source fixe de la 487.
- `retroarch-delivery.yml` run `39262042654` : `checks` et `native` réutilisés
  par la porte `rpcs3diag487_delivery.py`, `cold` réussi, `warm` ignoré.
  Compilation Xcode 311 s, signature et export 59 s ; Xcode 26.3, SDK iPhone
  26.2, Flutter 3.47.2, macOS 15.7.9. Aucun moteur reconstruit pendant la
  livraison : seul le Core RPCS3 487 vient d'un nouveau run.
- Contrôles CI sur l'IPA avant scellement (`63a89663…b42f`) :
  `validate_rpcs3_diag487_ipa.py` (9 marqueurs Core, 14 marqueurs du pont,
  Core SHA-256 `6b64fe7a…1c73` égal à l'artefact du run Core), catalogue de
  textures HD et catalogue de cheats inchangés, aucun pack embarqué. Le
  scellement ne modifie aucune section de code ou de données ni les
  métadonnées d'ABI (`signed-payload-identity.json`).
- Artefact chiffré `12192460455` (228 261 789 octets, archive SHA-256
  `3e1808c21442d4d69aa5614f5a5c2c034e5654a11c2d81ce0788a00c747dcc05`, conservé
  jusqu'au 2 novembre 2026) pour `build-utils/delivery-424-recipient.pem`,
  déchiffré sur le PC du mainteneur avec la clé 424 (mot de passe de session et
  archive en clair supprimés aussitôt, archive chiffrée et doublon de l'IPA
  supprimés après vérification).
- IPA **0.0.8 (487)** `NeoStation-Build487-fad5eac6f793672240d2cb5f3559da73a40226f8-cold.ipa`,
  **228 039 548 octets**, SHA-256
  **`bd59a616d8f6f02a969ea9de71e9803b9f7156df250eb36d56559462b1551759`**, égal à
  `SHA256SUMS`, à `signed-payload-identity.json` et à la copie
  `C:\Users\Coren\Downloads\NeoStation-Build487-fad5eac6.ipa` (relue après copie).
  iOS 18.0 minimum ; re-signature Apple par SideStore requise.
- Inspection indépendante contre l'IPA 486 livrée (`eef1553e…c607`, relue),
  par empreinte des sections Mach-O hors signature : hôte et cinq extensions en
  0.0.8 (487) ; 78 des 82 images identiques (34 cœurs libretro, ARMSX2, Dolphin,
  Dusklight, MoltenVK, helpers, extensions, code Dart, catalogues). Changent :
  - `libRPCS3Core.dylib` et `rpcs3_internal_bridge` : attendus, marqueurs 487
    présents (9/9 et 14/14, aucun dans la 486) ;
  - `Runner` : `__TEXT,__const` seulement (numéro de build, comme aux builds
    précédentes) ;
  - `armsx2_internal_bridge` : `__TEXT,__stubs` et `__TEXT,__objc_stubs`
    seulement, sans changement de source. Les emplacements GOT 141 et 142
    référencent tous deux `_objc_msgSend` (même import, tables d'imports et GOT
    identiques dans les deux builds) ; l'éditeur de liens a seulement inversé
    l'emplacement lu par les 814 stubs Objective-C et par le stub 159. Le code
    (`__text`), la GOT et les références de sélecteurs sont identiques à
    l'octet : aucun effet sur le comportement.
- Reçu : `docs/evidence/rpcs3diag487-delivery.json`. Aucune validation sur
  iPhone : premier démarrage de chaque titre à écarter (recompilation complète),
  puis protocole du § 6. Ne pas réutiliser le numéro 487.

## 8. Risques et retour arrière

- Retour arrière sans perte : remettre les réglages à Reference / Yield / 1 /
  God of War III, ou réinstaller la Build 486 (son Core ignore le fichier
  marqueur et les répertoires `spuobj-v6-*` d'une autre clé).
- Volume de diagnostic : `COREPROF` toutes les 5 s même sans image (≈ 0,9 Kio),
  `FREEZE_DUMP` borné par le Core, `MUTEX_DESTROY_BUSY` borné par l'hôte ; deux
  fichiers de 2 Mio au plus.
- Le vidage de gel lit des champs d'autres threads sans verrou (comme le
  débogueur de RPCS3) : valeurs possiblement incohérentes entre elles, sans
  effet sur l'émulation.
