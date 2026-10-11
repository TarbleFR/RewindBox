# RPCS3, LLVM et NeoSwap — audit et correctifs Build 444 (11 octobre 2026)

Référence livrée : Build 441, hôte `e1283fe543a8de5d6609359253d10dde46dbff2a`,
Core construit depuis `351b738c8d4d5fbe2c7498d4438776baecdba613`
(run `38163319515`). Les Builds 442 (`e8808dd3`, Dolphin et sauvegardes
RPCS3) et 443 (`79a5920a`, couvertures 3D de la Bibliothèque, autre session)
sont intercalées sur `Claude` ; aucune ne touche NeoSwap ni le Core. Ce cycle
est donc la Build 444 : code `7ec94a8c`, patch canonique
`4c9a2f9e135136481883e684b81429be5db7fa1301f19afde236922953f63fde`.

Les sources du Core sont lues sur l'arbre matérialisé
`XITRIX/rpcs3 @22f1152 + build-utils/rpcs3/embedded-core.patch` de la 441
(`1bd59add…1e6d6`, « PASS: single canonical RPCS3 delta » sur 177 fichiers).

Aucun journal d'iPhone (`NeoSwap-v1.jsonl`, `RPCS3-diagnostic*.log`) n'est
présent sur ce poste pour la Build 441, ni pour God of War III ni pour
BladeStorm. Ce document est donc un audit statique des sources, complété par
les captures exactes à réaliser. Aucune mesure n'est inventée ; les chiffres
cités viennent des constantes des sources ou des documents de mesure
antérieurs, identifiés comme tels.

## 1. Pourquoi God of War III affiche moins de mémoire NeoSwap que BladeStorm

### 1.1 Ce que mesure le chiffre affiché

La courbe « NeoSwap » de l'overlay et le champ `neoswapContribution.donatedBytes`
(schéma 2) du journal sont la même valeur, calculée par
`neostation::donation_metrics::active`
(`packages/neo_swap/ios/Classes/NeoSwapDonationMetrics.h`) :

| Terme | Source | Ce qu'il contient |
|---|---|---|
| `guestPublishedLiveBackingBytes` | relais, `owner_published_live_bytes[0]` | objets invités (owner 0) ayant eu au moins une vue publiée et non retirés |
| `owner_relay_active_bytes[RPCS3]` | broker hôte | prêts hôte actifs sur le relais (buffers CPU RSX, buffers Vulkan hôte, trames vidéo), hors étagères inutilisées |
| `owner_donated_active_bytes[RPCS3]` | broker hôte | prêts donneurs actifs |

Ce total exclut le stock préparé, les objets jamais mappés, les alias, les
fichiers (repli FILE) et les objets en cours de retrait. Il n'est ni de la RAM
résidente, ni une économie de footprint : `phys_footprint` du processus n'en
est jamais diminué, et les deux courbes ne s'additionnent pas.

### 1.2 Mécanismes démontrés dans les sources

Les cinq mécanismes suivants sont établis par lecture des sources 441. Leur
poids respectif pour GoW3 et BladeStorm n'est pas mesuré (voir 1.4).

**M1 — L'admission est bornée par la mémoire libre du système, que le jeu
consomme lui-même.** Chaque nouvelle part (préparation invitée, prêts hôte,
donneurs, petits buffers CPU) exige `system_usable − réserve ≥ 64 Mio`
(`NeoSwapBudget.h`, `growth_admitted`), la réserve opérationnelle valant
`clamp(RAM/16, 256 Mio, 768 Mio)` soit 512 Mio sur 8 Gio, doublée sous
pression ou état thermique sérieux. Le backend relais échantillonne en plus
`host_statistics64` à chaque création (`Backend.cpp`, `create_object` :
`headroom < bytes → PRESSURE`, et 0 sous WARN/CRITICAL). Un jeu dont le
footprint est élevé laisse moins de mémoire système libre ; les documents
antérieurs enregistrent un footprint GoW3 culminant à 3,52 Go et une mémoire
libre d'environ 0,6 Go pendant le jeu (`docs/neoswap-device-analysis-20260930.md`,
`docs/rpcs3-build436-gow3-black-screen.md`). Le chiffre « donné » est donc une
mesure de ce que le système pouvait encore prêter après que le jeu a pris sa
part : il décroît avec l'exigence du jeu. BladeStorm, moins exigeant, laisse
plus de marge et reçoit plus d'admissions.

**M2 — Pendant le jeu, seules les tailles exactes déjà en stock étaient
servies.** `gameplay_active` passe à vrai dans `Emulator::Run`
(`RPCS3IOS.cpp:942`, `callbacks.on_run`) et à faux dans `on_stop`. Or `Run`
précède tout le chargement du jeu : les allocations invitées du jeu
(`sys_memory`, `sys_mmapper`, segments PRX, blocs non préalloués de `vm.cpp`
lignes 1471, 1550, 2466) sont toutes « gameplay » pour NeoSwap. Dans ce mode,
le client 441 (`NeoSwapRelayClient.h`, `shared_memory::map`) ne faisait qu'un
`try_acquire` sur le stock préparé et, en cas d'échec, choisissait le repli
FILE définitivement pour cet objet. Le stock (`Backend.cpp`) est limité à :
tailles multiples de 64 Kio jusqu'à 16 Mio (`prepared_maximum_bytes`), au-delà
`INVALID` sans tentative ; 128 emplacements et 64 Mio au plus ; au plus 8
objets et 32 Mio par passage de maintenance, un passage toutes les 250 ms
(`NeoSwapPlugin.mm`, timer `NSEC_PER_SEC/4`) ; un seul objet par classe de
taille et par passage ; demande enregistrée seulement après un échec (la
première demande de chaque taille échouait toujours) ; quatre demandes en
attente par taille au maximum ; stock inutilisé expiré après 32 passages
(8 s) ; stock vidé et acquisitions refusées dès que la pression dispatch est
levée (`refused_pressure`), et `BUSY` si la maintenance tient le verrou. Seuls
les blocs préalloués de `vm::init` (main 0x00010000, video 0xC0000000, stack
0xD0000000) sont créés avant `Run` par le chemin bloquant `create()` ; ils
expliquent le backing invité d'environ 1 Go observé dans les journaux
antérieurs, identique pour tous les titres.

**M3 — Un objet refusé une fois reste FILE toute sa vie.** Les objets de longue
durée alloués pendant le chargement (après `Run`) qui manquaient le stock sont
exclus durablement ; le compteur 441 `ordinary_fallback_bytes` est cumulatif et
ne distingue pas les objets encore vivants. Build 444 ajoute
`fallback_live_bytes` (objets candidats vivants sur FILE).

**M4 — Les prêts hôte dépendent du profil RSX du jeu, pas de son exigence.**
`try_allocate` (≥ 1 Mio, `NeoSwapClient.h`) et `try_allocate_cpu` (64 Kio à
1 Mio, activé par l'hôte pour les six identifiants GoW3 seulement,
`NeoSwapCPUBufferTitle`) ne concernent que les buffers CPU du RSX, les imports
Vulkan hôte (1–256 Mio) et les trames vidéo. Leur volume suit le nombre et la
taille des buffers du jeu, sous le quota `host_loan_quota_bytes` du budget (M1)
et le cache de réemploi (256 Mio, 2 s). Ce mécanisme favorise GoW3 ; il ne peut
pas expliquer un écart en sa défaveur.

**M5 — Le Core réduit son propre footprint sous pression, pas la donation.**
`IOSMemoryPressurePolicy.h` applique des paliers sur la marge processus
(modéré 1536/1792 Mio, sévère 1024/1280 Mio, fatal 512/768 Mio ; palier relatif
« footprint élevé » 2560/2816 Mio), des quotas de cache de textures
(384/256/128 Mio) et des réclamations (délais 1,5 s, 3 s, plafond 24 s). Ces
réclamations détruisent et recréent des ressources (visible dans
`COREPROF_RESILIENCE memory_reclaims` et `vram_allocations/frees`) ; elles
expliquent des saccades, pas la différence de « donné ».

### 1.3 Ce que ces mécanismes impliquent

Un « Donated » plus faible pour GoW3 n'est pas un défaut de comptage ni une
RAM « non donnée » que NeoSwap retiendrait : NeoSwap ne crée pas de mémoire.
C'est la combinaison de M1 (moins de marge système) et de M2/M3 (le chemin de
jeu ne servait que des tailles déjà en stock, jamais au-dessus de 16 Mio, et
jamais au premier passage). La Build 444 corrige M2/M3 (admission directe non
bloquante à la création, réapprovisionnement par rafale, réveil anticipé) et
rend M1 mesurable (allocation budgétée et comptée). M1 reste une règle de
sécurité : lorsque le système n'a plus de marge, aucune version ne prêtera
davantage sans mettre le processus en danger de jetsam.

### 1.4 Ce qui n'est pas démontré

- Le profil d'allocation de BladeStorm (tailles, moments, durée de vie) et
  celui de GoW3 sur la Build 441 : aucune capture sur ce poste.
- La part respective de M1 et de M2/M3 dans l'écart observé.
- Que le chiffre observé par le mainteneur soit bien `donatedBytes` et non un
  autre champ (par exemple `neoswapTotalBytes`, qui inclut les fichiers et les
  étagères, ou `guestRelay.liveBackingBytes`).

### 1.5 Captures nécessaires (même iPhone, même IPA, mêmes réglages)

Pour chacun des deux titres, deux sessions (cache froid après suppression du
cache PPU/SPU du titre, puis cache chaud), état thermique nominal au départ,
batterie > 50 %, aucune autre application :

1. Lancement → menu → première zone de jeu → une transition de scène →
   5 minutes de jeu → sortie normale par le menu.
2. Fichiers à fournir sans les ouvrir : toutes les rotations de
   `NeoSwap-v1*.jsonl` et `RPCS3-diagnostic(*).log` de la session, plus le
   manifeste du comparateur (`sourceCommit`, `pid`, `sessionSequence`,
   `bootTimestamp`, `title`, `workloadId`, `deviceId`, `settingsId`).
3. Champs lus par `tools/compare_rpcs3_neoswap_builds.py --mode cross-title`
   (voir §9) : `neoswapContribution` (schéma 2, parties disjointes),
   `budget.inputs.systemUsableBytes`, `budget.state/reason`,
   `budget.hostEnvelope`, `budget.directGuestAllowanceBytes`,
   `guestRelay.guestPreparation`, le nouvel objet
   `guestRelay.guestDirectCreation`, `fileFallbackLiveBytes`,
   `processFootprintBytes`, `processAvailableBytes`, puis côté Core les lignes
   `neoswap_guest_sample` (schéma 1) et `neoswap_guest_sample_ext` (schéma 1,
   nouvelle), `COREPROF`, `COREPROF_RESILIENCE`, `SPUPROF`, `RANGELOCKPROF`
   et la nouvelle ligne `JITPROF`.

## 2. Comparaison mémoire fiable : quel compteur pour quelle question

| Question | Compteur | Source | Règle |
|---|---|---|---|
| Footprint du processus (charge noyau, pages compressées incluses) | `processFootprintBytes` / `hostFootprintBytes` | `TASK_VM_INFO.phys_footprint` | jamais corrigé de « Donated » |
| Résident | `processResidentBytes` | `TASK_VM_INFO.resident_size` | contient déjà les alias des pages prêtées : ne pas additionner au relais |
| Marge jetsam du processus | `processAvailableBytes` | `os_proc_available_memory()` | estimation ; `hostEnvelope.limitEstimateBytes` = footprint + marge, haute valeur de session |
| Mémoire système utilisable | `budget.inputs.systemUsableBytes` | `host_statistics64` (libre + purgeable − marge) | seule autorité d'admission |
| Capacité relais retenue | `guestRelay.capacityBytes` | 16 × 512 Mio nommés | capacité virtuelle, jamais de la RAM |
| Backing invité vivant | `guestRelay.guestLiveBackingBytes` | `owner_live_bytes[0]` | inclut stock préparé et objets non publiés |
| Donation active | `neoswapContribution.donatedBytes` | §1.1 | exclut stock, alias, fichiers |
| Stock préparé / engagé non publié | `guestPreparation.preparedBytes`, `unpublishedCommittedBytes` | backend | engagement, pas des pages touchées |
| Création directe (444) | `guestDirectCreation.*` | backend | demandes, créations, refus par cause, allocation budgétée en vigueur |
| Repli FILE vivant | `fileFallbackLiveBytes` ; `neoswap_guest_sample_ext fallback_live_bytes` | broker hôte ; Core | octets durablement exclus |
| Couverture des demandes invitées | `neoswap_guest_sample prepared_hits/misses`, `ordinary_fallback_bytes`, `_ext gameplay_direct_*` | Core | cumul processus ; comparer par différence début/fin |
| Stockage froid | `storageArchivedLiveBytes` | service de stockage | disque, hors RAM |

Aucune de ces colonnes ne s'additionne pour former une « RAM totale ». Les
journaux de deux titres se comparent uniquement à même IPA, même Core, mêmes
réglages, même parcours et même état de cache.

## 3. Audit des limites NeoSwap 441 et effet sur les rafales

| Limite 441 | Valeur | Effet démontré | Build 444 |
|---|---|---|---|
| Tailles en stock | multiples de 64 Kio ≤ 16 Mio | tout objet > 16 Mio est FILE en jeu | création directe sans limite de taille (≤ 512 Mio, un segment) |
| Stock total / emplacements | 64 Mio / 128 | une rafale de 5 × 16 Mio dépasse le stock | inchangé (un relèvement attend une capture qui le justifie) |
| Par passage | 8 objets, 32 Mio, 1 par classe | une rafale de N objets de même taille obtenait 1 objet par 250 ms | jusqu'à 4 objets de même classe par passage (demande enregistrée), toujours ≤ 8 et ≤ 32 Mio |
| Cadence | 250 ms | première demande d'une taille toujours perdue, puis attente d'un tick | réveil anticipé du passage de maintenance sur manque (au plus un par 50 ms) |
| Demandes en attente | 4 par taille, `demand_overflow` compte le reste | borne conservée | inchangé |
| Expiration | 32 passages (8 s) | stock recyclé pendant les phases calmes | inchangé |
| Pression | stock vidé, `try_acquire` refusé | fail-closed | inchangé ; la création directe est refusée de même |
| Jeu : création | interdite (verrou, échantillon OS, extension) | FILE définitif | `try_create` non bloquant : `try_lock`, admission (pression, `host_statistics64`, capacité, quota, budget), aucune page touchée ; `BUSY` → FILE comme avant |

Les causes d'échec sont désormais toutes comptées séparément : stock vide
(`emptyMisses`), taille absente (demande enregistrée), contention
(`busyMisses`, `direct.busy`), alignement (`unsupportedCount` : taille non
multiple de 64 Kio ou owner ≠ 0), budget (`direct.refusedBudget`), pression
(`pressureRefusals`, `direct.refusedPressure`), fragmentation/capacité
(`direct.refusedCapacity`), emplacements (`direct.refusedLimit`), échec de
mapping (`mapFailureCount`, Core `map_failures`).

## 4. Consommateurs réels de mémoire et routes

| Consommateur | Taille typique | Route 441 | Route 444 | Compteurs |
|---|---|---|---|---|
| Blocs `vm::init` (main, video, stack) | 3 × 256 Mio | relais `create()` au boot | inchangé | `guestLiveBackingBytes` |
| Allocations invitées du jeu (`sys_memory`, `sys_mmapper`, PRX) | 64 Kio à plusieurs centaines de Mio | stock préparé ≤ 16 Mio sinon FILE | stock, puis création directe budgétée, puis FILE | `neoswap_guest_sample(_ext)` |
| Buffers CPU RSX ≥ 1 Mio | 1–64 Mio | prêt hôte relais (quota budget), sinon tas | inchangé | `relayHostLoans.kindLiveBytes.cpuData` |
| Buffers CPU RSX 64 Kio–1 Mio (GoW3 seulement) | | prêt hôte `CPU_CACHE`, sinon tas | inchangé | `cpuBufferExperiment`, `kindLiveBytes.cpuCache` |
| Buffers Vulkan hôte visibles | 1–256 Mio | import relais (budget), sinon allocateur Vulkan | inchangé | `kindLiveBytes.gpuHostVisible` |
| Textures / surfaces (VRAM MoltenVK) | centaines de Mio | privé GPU, quota par palier de pression | inchangé | `COREPROF_RESILIENCE vram_*`, `memory_reclaims` |
| JIT PPU/SPU (arène `JITIOS.cpp`, pas 64 Mio) | | privé, jamais NeoSwap | inchangé | nouvelle ligne `JITPROF` (temps, octets, marge minimale) |
| Cache d'objets PPU, cache SPU brut | disque | fichiers du cache | clé PPU durcie | `ppu_cache_hits/misses`, `JITPROF ppu_cache_read/write` |
| Sources GLSL froides | disque | archive hôte | inchangé | `storageArchivedLiveBytes` |

Les tailles, octets demandés/éligibles/servis/refusés et durées de vie par
consommateur ne sont pas connus sans capture ; les compteurs de la colonne de
droite sont ceux qui les établissent.

## 5. LLVM et Core : état audité

| Point | Constat (sources) |
|---|---|
| Version LLVM | sous-module `3rdparty/llvm/llvm` à `ca7933e47d3a3451d81e72ac174dcb5aa28b59d1` (branche 22.x), construite in-tree pour iOS, cible AArch64 seule ; correctif `llvm-aarch64-ghc-emergency-spill.patch` sur `AArch64FrameLowering.cpp` |
| Moteur JIT | MCJIT (`EngineBuilder`, `RTDyldMemoryManager`), `CodeGenOptLevel::Aggressive`, `Reloc::PIC_`, modèle de code Small (Large pour les JIT PPU drapeau 0x2), `disable-interleaved-load-combine` forcé (ARMSX3 85d074b) |
| Ciblage CPU du JIT | `getHostCPUName()` (A18 Pro → `apple-m4` dans `Host.cpp` de ce LLVM ; `cortex-a78` si « generic ») + attributs explicites `±sha3 ±dotprod ±i8mm ±sve ±sve2` lus par `sysctl` : seules les capacités réellement présentes sont annoncées |
| Pipeline PPU | aucune passe IR sur ARM64 : `fpm.run(EarlyCSE)` est sous `#ifdef ARCH_X64 // TODO` (`PPUThread.cpp:6207, 6225` en 441), identique dans RPCS3 master (lignes 6104/6122 au 11 octobre 2026). Le code ARM64 PPU va directement de la traduction au backend |
| Pipeline SPU | `EarlyCSE(true)`, `SimplifyCFG`, `DSE`, `LICM`, `ADCE` puis replis ARM64 (`lower_spu_variable_insertions`, `fold_byte_reversals`, `fold_single_source_tables`, `fold_wide_comparison_reversals`), sur toutes les architectures |
| Cache PPU | objets relocalisables `.obj.gz` (zip) nommés en 441 `v8-neostation-embedded1-<hash module>-<réglages>-<cpu>` : identité du code invité ✓, options de codegen ✓ (liste manuelle), nom CPU ✓ ; version LLVM ✗, révision du Core ✗ (bits `arm64_codegen_vN` manuels), attributs CPU ✗ |
| Cache SPU | programmes bruts (`spu_cache`), recompilés à chaque démarrage ; aucun objet persistant sur ARM64 (adresses hôte incorporées, réglage `persistent_spu_object_cache` « unavailable on ARM64 ») |
| Parallélisme | PPU : `min(modules, get_max_threads())` → limite iOS automatique 3 (`automatic_llvm_compile_threads`) ; SPU : revendication par `llvm_compile_state` CAS (aucune compilation en double), préchauffage de chargement ≤ 2 workers (`warmup_worker_count(…, true)`) ; compilation différée 435 désactivée (`deferred_compile_enabled = false`) et laissée telle quelle |
| Core natif | `-march=armv8.4-a` sans `-mcpu`/`-mtune` (`ConfigureCompiler.cmake`, branche Apple), ordonnancement générique ; cible `arm64-apple-ios16.3` ; ThinLTO sélectif actif sur `RPCS3Core` et `rpcs3_emu` (`RPCS3_IOS_SELECTIVE_THINLTO=ON`) ; `-fstack-protector`. Compatibilité : armv8.4-a suppose un A13 ou plus récent ; clang seul aurait choisi `apple-a7` pour iOS 16.3 |
| PGO | non applicable sans profils collectés sur l'appareil ; nécessiterait un Core instrumenté exportant `.profraw` via Fichiers, puis un second Core. Non entrepris |

### 5.1 Problèmes identifiés et suite donnée

1. **Aucune mesure par phase de compilation.** Les journaux ne donnaient que le
   total des compilations SPU (`SPUPROF`) et les hits/misses du cache PPU.
   Build 444 ajoute `JITPROF` : traduction IR PPU, passes optionnelles,
   vérification, génération de code, lecture/écriture du cache, chargement
   d'objet, finalisation, symboles ; construction IR SPU, passes, génération ;
   octets d'objets ; marge mémoire processus minimale observée après chaque
   module PPU compilé.
2. **Passes IR PPU absentes sur ARM64.** Lever le `// TODO` n'est pas prouvé
   sans appareil ; la Build 444 ajoute l'option `emulator.ppu_llvm_ir_passes`
   (désactivée par défaut, hachée dans la clé du cache) qui exécute `EarlyCSE`
   comme sur x86-64. Elle sert à mesurer, avec `JITPROF` et `COREPROF
   ppu_ms`, avant toute activation par défaut.
3. **Clé de cache PPU incomplète.** Build 444 ajoute une identité de codegen :
   chaîne de version LLVM, attributs CPU effectifs, empreinte SHA-256 des
   sources du traducteur et du moteur (calculée par CMake, voir §8). Toute
   divergence recompile une fois ; aucun objet n'est réutilisé avec une
   identité différente.
4. **Objets SPU non persistants sur ARM64.** Un démarrage recompile le cache
   SPU entier (à ≤ 2 workers). Rendre ces objets relocalisables exige de
   remplacer les adresses incorporées par des symboles dans le traducteur SPU :
   travail séparé, non entrepris ici, à chiffrer avec `JITPROF spu_*`.
5. **Core natif en ordonnancement générique.** Un `-mtune=apple-a13` ou plus
   précis est possible mais non mesuré ; non modifié dans cette build.

### 5.2 Préchauffage des modules connus pendant le chargement

Le mécanisme existe déjà et n'est pas modifié : `spu_cache` relit les
programmes SPU connus au démarrage et les compile avec au plus deux workers sur
iOS (`rpcs3::spu::warmup_worker_count(…, true)`, `SPUWarmupPolicy.h`), ciblé
pour God of War III (`targeted_warmup`), journalisé par `SPUWARMUP begin/end`
(`metadata`, `discovered`, `programs`, `failed`, `stopped`, `elapsed_ms`) et
par `SPUPROF loading_*`. Son budget n'était mesuré qu'en temps total ; la Build
444 ajoute, par `JITPROF spu_build/spu_passes/spu_codegen`, le coût unitaire
moyen et maximal d'un bloc (ms et octets de code invité) et la marge mémoire
minimale pendant les compilations PPU. C'est avec ces deux mesures sur
l'iPhone qu'un budget de préchauffage (nombre de blocs, temps, mémoire) peut
être fixé ; aucun budget n'est changé sans elles.

### 5.3 Analyse du code ARM64 chaud

Non réalisée dans ce cycle faute de modules capturés. Méthode prévue : activer
`Save LLVM logs` (`core.llvm_logs`, écrit l'IR de chaque module PPU dans le
cache du titre) ou `SPU Debug` (`spu-ir.log`) sur l'appareil, rapatrier les
journaux par Fichiers, puis recompiler hors ligne les modules les plus chauds
(d'après `COREPROF ppu_ms/spu_ms` et les profils PPU) avec le même LLVM 22 et
`-Rpass-missed`/`-Rpass-analysis` pour l'inlining, la vectorisation NEON, le
déroulage, les accès mémoire, les appels d'aides et la pression de registres.
Le remplacement de pipelines ne précède pas cette mesure.

## 6. Modifications de la Build 444

Chaque changement est isolable : les compteurs nouveaux ne modifient aucune
décision ; la création directe est une ABI optionnelle séparée
(`NEOSWAP_DIRECT_RELAY_ABI = 1`) que le Core utilise seulement si l'hôte
l'expose, et qui laisse le comportement 441 à un hôte qui ne l'expose pas ;
l'option PPU est désactivée par défaut ; la clé de cache ne change que le nom
des objets. Les ABI 441 (`NEOSWAP_PREPARED_RELAY_ABI = 1`,
`NEOSWAP_RELAY_CLIENT_STATS_ABI = 1`) sont intactes.

## 7. Hôte NeoSwap (packages/neo_swap, native/neoswap-relay)

- `NeoSwapRelay.h` (copie identique dans le Core) : `NeoSwapDirectRelayAPI`
  (`try_create`, `snapshot`) avec `NeoSwapDirectRelayStats` (demandes, octets,
  créations, refus par cause, tailles > 16 Mio, allocation en vigueur et
  cumul, réveils) ; `NeoSwapRelayClientStatsExt` (issues de l'admission
  directe, replis de jeu, exclusion FILE vivante, tailles > 16 Mio, créations
  au boot, publications directes).
- `Backend.cpp/.h` : `try_create_guest` (owner 0 ; `try_lock` ; refus
  disabled/pression avant tout échantillon ; budget `direct_allowance` ;
  admission de `create_object` ; l'objet est `pool_origin` : retour non publié
  sans syscall, scrub différé par `collect()`, cycle `map/unmap/retire`
  inchangé ; `unpublished_bytes` compte l'engagement jusqu'à la première vue) ;
  `set_direct_guest_allowance` (remplacée à chaque passage, jamais cumulée,
  remise à zéro par `shutdown`) ; `set_demand_signal` et `signal_demand`
  (appel hors verrou, au plus un par 50 ms, sur `miss_empty` et refus budget
  seulement : ni `BUSY`, ni pression, ni succès) ; `maintain_guest_pool`
  prépare jusqu'à la demande enregistrée d'une classe (quatre) dans les bornes
  8 objets / 32 Mio / cible.
- `NeoSwapBudget.h` : `Decision.direct_guest_allowance_bytes` = grant borné et
  rampé, limité par la capacité relais libre ; non soustrait de `remaining`
  (promesse consommée seulement par de vraies allocations invitées, vues au
  passage suivant dans `relay_guest_live_bytes`) ; zéro si croissance non
  admise, relais absent, pression, arrière-plan, rétrécissement, marge
  inconnue, session inactive.
- `NeoSwapPlugin.mm` : source dispatch `DATA_ADD` sur la file utilitaire
  (`NeoSwapDemandSignal` → `applyBudget` si session RPCS3 active) ; application
  de l'allocation après `maintain_guest_pool` ; `budget.directGuestAllowanceBytes`
  et `budget.demandWakeups` dans le journal.
- `NeoSwapRelayService.mm` : objet `guestDirectCreation` (schéma 1) dans les
  diagnostics relais.
- `Rpcs3CoreABI.h`, `Rpcs3InternalBridgePlugin.mm` : liaison optionnelle
  `rpcs3_ios_set_neoswap_direct_relay_api`, diagnostic
  `neoswap_direct_guest_client`, ligne `neoswap_guest_sample_ext` aux quatre
  phases (`before_boot`, `boot_return`, `sample`, `session_end`).

## 8. Core RPCS3 et LLVM (build-utils/rpcs3/embedded-core.patch)

Quatorze sections régénérées (une nouvelle : `Utilities/JITPhaseProfile.h`),
le reste du patch 441 octet pour octet identique ; postimages et
`patch_sha256` vérifiés par `materialize_rpcs3_core.py` sur un arbre vierge.

- `rpcs3/ios/NeoSwapRelayClient.h` : `install_direct`, compteurs d'extension,
  `snapshot_ext` ; en jeu, après un manque du stock `QUOTA` (vide) ou
  `INVALID` (taille > 16 Mio) et seulement si la table directe est installée,
  `try_create` ; `BUSY`, `PRESSURE`, `QUOTA` (budget) et autres refus sont
  comptés puis le repli FILE reste définitif ; jamais `api->create`, jamais
  `api->enabled`, jamais d'attente dans ce chemin ; `fallback_live_*`
  décrémentés à la destruction ; publications directes comptées à part.
- `rpcs3/ios/RPCS3IOS.cpp/.h/.exports` : exports
  `rpcs3_ios_set_neoswap_direct_relay_api` et
  `rpcs3_ios_get_neoswap_relay_client_stats_ext` (aucune E/S à l'installation).
- `Utilities/JITPhaseProfile.h` : registre constant-initialisé (aucun
  constructeur au `dlopen`), `scope` RAII à temps exclusif (les phases
  imbriquées sur le même thread sont soustraites), `exchange()` pour le
  rapporteur. `JITLLVM.cpp` : `ppu_cache_write` (zip + écriture),
  `ppu_cache_read` (lecture + unzip), `ppu_codegen` (génération d'un manque),
  `ppu_object_load` (parsing + `addObjectFile`). `PPUThread.cpp` :
  `ppu_translate` (par fonction, octets = code invité), `ppu_opt`,
  `ppu_verify`, `ppu_finalize` (par JIT), `ppu_symbols`, échantillon de marge
  après chaque module compilé. `SPULLVMRecompiler.cpp` : `spu_build`,
  `spu_passes`, `spu_codegen` dans `compile()`. `RPCS3IOSPerformance.cpp` :
  ligne `JITPROF session=<n> <phase>=<événements>:<total_ms>:<max_ms>:<octets>
  … headroom_samples=<n> headroom_min_mib=<f>` dans la même fenêtre de 5 s que
  `SPUPROF`/`RANGELOCKPROF`/`COREPROF_RESILIENCE`.
- Clé de cache PPU : `jit_compiler::target_attributes()` (liste unique partagée
  par le moteur et l'identité), `jit_compiler::codegen_identity()` = base57 du
  SHA-1 de `LLVM_VERSION_STRING | NEOSTATION_PPU_CODEGEN_ID | attributs |
  options fixes du backend` ; `rpcs3/Emu/CMakeLists.txt` calcule
  `NEOSTATION_PPU_CODEGEN_ID` (SHA-256 des empreintes de `PPUTranslator.cpp/.h`,
  `PPUThread.h`, `PPUFunction.h`, `PPUOpcodes.h`, `CPUTranslator.cpp/.h`,
  `JIT.h`, `JITLLVM.cpp`, `JITPhaseProfile.h`, `AArch64FrameLowering.cpp`) ;
  nom d'objet `v9-neostation-<module>-<réglages>-<cpu>-<identité>.obj`. Effet
  attendu sur l'iPhone : une recompilation PPU complète au premier lancement de
  chaque titre après ce Core (les anciens fichiers `v8-…` restent sur disque et
  ne sont jamais relus), puis cache chaud.
- Option `emulator.ppu_llvm_ir_passes` (`system_config.h` « PPU LLVM IR
  Passes », `RPCS3IOSSettings.cpp` catégorie Emulator › Compilation, booléen,
  défaut off) ; bit `arm64_ir_passes` dans les réglages hachés ; `fpm.run`
  exécuté aux deux sites sous `#elif defined(RPCS3_IOS)` seulement si l'option
  est active. Le catalogue de réglages du Core est en anglais, comme ses autres
  entrées ; aucune chaîne Flutter n'a été ajoutée.
- `SPUDeferredCompilePolicy.h` : `deferred_compile_enabled = false` inchangé
  (vérifié par le test 444).

## 9. Outils, tests et résultats

Exécutés sur ce poste (Windows, zig 0.17.0 `c++` en C++20, `-UNDEBUG`,
`-Wall -Wextra -Werror`) :

| Vérification | Résultat |
|---|---|
| `test/relay_backend_test.cpp` + `Backend.cpp` (`-DNEOSWAP_TESTING`) : quatre tests 444 (admission directe budgétée, non-blocage, rafale, signal borné) + suites 441 | PASS |
| `test/neoswap_budget_test.cpp` : allocation directe (croissance, relais serré, relais absent, sous le quantum, pression, arrière-plan, rétrécissement, marge inconnue, session inactive) | PASS |
| `test/rpcs3_build444_core_delta_test.py` + `.cpp` sur l'arbre matérialisé : registre de phases (temps exclusif, maxima, octets, marge, remise à zéro) et câblage (clé v9, identité, option, JITPROF, admission directe, SPU différé off) | PASS |
| `rpcs3/ios/NeoSwapRelayClient.h` compilé seul (TU minimale, ABI de l'extension) | PASS |
| `build-utils/materialize_rpcs3_core.py` sur un arbre XITRIX vierge, hashes des 211 sections | PASS |
| `test/neoswap_relay_extension_test.py` (contrats sources du service relais) | 9 réussis, 3 erreurs d'import de module voisin propres à ce poste, 1 ignoré |

Non exécutables ici (fork/mmap, ObjC++, LLVM) et confiés à la CI sur
`7ec94a8c` : `test/rpcs3_neoswap_relay_test.py` (client matérialisé, chemin
direct, contrats de verrou), compilation ObjC++ du plugin et du pont, run
`rpcs3-core.yml` `38177331182` (Core complet avec ses tests préalables, dont
le test 444), run `neoswap-relay-check.yml` `38177333574` (backend ASan/UBSan,
extension, simulateur). Le run `neoswap-check.yml` `38177335871` s'arrête à
`check_neo_swap_scope.py` sur un contrôle antérieur à ce cycle (reconstruction
de `neoswap-ipa.yml` figée avant les épingles 441) ; ce contrôle n'est pas dans
la livraison. Les résultats de ces runs sont consignés dans §11 à leur
conclusion.

Outil de comparaison : `tools/compare_rpcs3_neoswap_builds.py` lit désormais
`neoswap_guest_sample_ext`, `JITPROF`, `guestDirectCreation`,
`directGuestAllowanceBytes`, `demandWakeups`, `fileFallbackLiveBytes`, et
accepte `--mode cross-title` (deux titres, un seul commit, même appareil et
réglages) ; tests unitaires dans `test/rpcs3_neoswap_build_comparison_test.py`.

## 10. Protocole de validation sur iPhone

1. Installer la Build 444 (SideStore). Premier lancement de chaque titre : la
   recompilation PPU complète est attendue (clé v9) ; ne pas mesurer cette
   session, seulement l'enregistrer (`JITPROF ppu_translate/ppu_codegen`,
   `headroom_min_mib`).
2. Parcours de §1.5 pour GoW3 puis BladeStorm, cache chaud, option
   `ppu_llvm_ir_passes` désactivée. Comparer entre titres avec
   `--mode cross-title` : `donatedBytes` et ses parties, `guestDirectCreation`
   (créations/refus par cause, `allowanceBytes`), `fallback_live_bytes`,
   `gameplay_direct_*`, `systemUsableBytes`, `budget.state`.
3. Même parcours GoW3 avec la Build 441 encore installée si possible (ou ses
   journaux antérieurs) : `--mode same-title` ; gains recherchés sur les temps
   d'image (`COREPROF frametime/p95/p99`), les compilations en jeu (`SPUPROF
   gameplay_*`), la couverture invitée (`ordinary_fallback_bytes` en baisse,
   `prepared_hits + gameplay_direct_creates` en hausse) et l'absence de
   nouveaux `refusedPressure`/jetsam. Un « Donated » plus élevé seul n'est pas
   un gain.
4. Ensuite seulement : activer `PPU LLVM IR passes (ARM64)`, relancer (une
   recompilation PPU, nouveau bit de réglages), même parcours : comparer
   `JITPROF ppu_opt/ppu_codegen` (coût), `COREPROF ppu_ms`, temps d'image. Toute
   anomalie de jeu avec l'option invalide l'hypothèse : la laisser désactivée.
5. Stabilité : trois lancements à froid/chaud, pause/reprise, retour menu,
   relancement sans redémarrer l'application ; vérifier l'absence de
   `fixed_alias_quarantined`, de `map_failures` et de fin de session anormale.

## 11. Limites restantes

- Aucune mesure d'appareil dans ce cycle : l'écart GoW3/BladeStorm est expliqué
  par les sources, pas quantifié ; les captures de §1.5 restent à faire.
- L'allocation directe est une promesse par intervalle de 250 ms ; une rafale
  supérieure au grant rampé (≤ 256 Mio) retombe sur FILE comme avant, et les
  objets > 512 Mio ne tiennent pas dans un segment nommé.
- Le stock reste borné à 64 Mio / 128 objets ; un relèvement attend
  `guestDirectCreation.oversizeMaxBytes` et `demandOverflow` mesurés.
- `JITPROF` n'inclut pas la mémoire de pic des compilations LLVM ; la marge
  minimale après chaque module est une approximation.
- Les objets SPU ne sont toujours pas persistants sur ARM64 ; le Core natif
  garde son ordonnancement générique armv8.4-a ; PGO non entrepris.
- `check_neo_swap_scope.py` et `import_memory_candidate_scope_test.py`
  échouaient déjà sur `Claude` avant ce cycle (reconstructions figées avant
  les épingles 441) et n'ont pas été étendus ; ils ne font pas partie de la
  livraison.
- Le catalogue de réglages du Core (dont la nouvelle option) n'est pas traduit
  dans les douze langues de l'application, comme ses autres entrées.
