# S2Arm : vague 845 (`0418–0421`, déverrouillage pont et leviers universels NVN2)

26 novembre 2026. Base : [IPA privée 844](rewind844/delivery.json) et [observations iPhone 844](s2arm-844-device.md). À la demande explicite du mainteneur, la vague 845 applique en un seul lot cohérent :
- la correction des régressions de la 844 (`0418`),
- l’élimination des gels de compilation au démarrage et en jeu (`0419`),
- la réduction du trafic mémoire/résidence/clears TBDR (`0420`),
- les leviers universels de performances NVN2 accessibles dans les réglages Switch 2 (`0421`),
- l’activation pour **tous les titres Switch 2** des 17 optimisations CPU/rendu déjà codées et éprouvées dans le pont iOS.

Aucune modification n’est apportée à `S2A.Dsh` : l’empreinte traducteur `S2ArmShaderXfp.txt` reste **`ecd99354f03b846d`** et la chaîne directe `S2ArmDirectChain.txt` reste **`0be3f28548fd`** (aucune retraduction forcée des caches déjà construits sur la 844).

## 1. Patchs moteur (`0418–0421`)

### `0418` — Correction des régressions 844 (replay worker, file de présentation, archives Metal 4)
- **`0404` (`rb_replay_worker.inc`)** : désactivé par défaut (`S2A_RB_REPLAY_WORKER=1` pour réactiver). Ajout d’un chemin rapide atomique sans mutex (`rb_replay_active`) dans `RB_REPLAY_GUARD` / `rb_replay_enter` et soumission synchrone directe dans `nvnQueueSubmitCommands` lorsque le worker est inactif.
- **`0405` (`nvn_mtl.m`)** : file dédiée `g_rb_present_q` désactivée par défaut (`S2A_RB_PRESENT_QUEUE=1` pour réactiver). La présentation et MetalFX Frame Generation repassent sur `g_q4`, supprimant la corruption de fond des réglages, les remises `WindowAcquireTexture` encore à l’écran, le double commit de résidence et le découpage GPU concurrent.
- **`0406`/`0408` (`nvn_mtl.m`, `pso_archive.h`)** : archives Metal 4 désactivées par défaut (`S2A_RB_M4_ARCHIVE=1` pour réactiver) et corrigées pour l’opt-in : compteur `g_rb_m4_live_captures` (décrémenté dans `RBMetal4Capture -dealloc`) empêchant `par_ga_remove_new` de supprimer des dossiers `gpuarchiver-*` vivants (`PersistentState`), et réutilisation d’un `MTL4Compiler` partagé `rb_m4_shared_compiler` hors capture.

### `0419` — Mode de pipelines fluide et plafond de préparation au démarrage
- Relève le plafond de `rb_wait_known_prepare` de `30 s` à `180 s` (`S2A_RB_PREPARE_MAX_MS`, tout en préservant l’échappatoire joueur « Jouer maintenant », l’arrêt à `Critical` et la garde mémoire) pour ne plus couper la préparation connue sur Zelda (`399` pipelines restants sur la 844).
- Ajoute `S2A_RB_FLUID_PSO` (actif par défaut `1` en NVN2 hébergé, basculable à chaud via le nouveau point d’entrée invité `s2a_rb_guest_set_fluid_pso(int on)`) :
  - réduit `rb_pso_frame_ms()` à `8 ms` et `rb_late_budget_ms()` à `0 ms` ;
  - dans `pso_pend_take_ex`, plafonne l’attente des dessins de rendu sans écriture storage (`!may_skip && !storage_writes && !rb_course_exact()`) à `12 ms` (`S2A_RB_FLUID_PSO_MS`, budget `24 ms` par image) avec priorité `USER_INTERACTIVE` au lieu d’un blocage sans borne ;
  - les pipelines compute et les pipelines avec écritures storage restent strictement synchrones (fidélité préservée).

### `0420` — Réduction du churn de résidence, des passes de clear et du trafic TBDR
- Regroupe les `res_commit_` de simple retrait jusqu’à 4 images tant que le volume retiré reste `< 32 Mio` et `!rb_mem_low()` (vérifié : `rb_mem_low()` ne verrouille pas `g_res_mu`).
- Supprime les doubles acquisitions de verrou `res_add(mt)` dans `tex_mtl_` et saute `res_add` sur les hits `txr_take` déjà résidents dans `g_res`.
- Relève le seuil souple d’allocateur par image `0401` (`rb_alloc_frame`) de `16 Mio` à `32 Mio` (`S2A_RB_ALLOC_FRAME_MB`).
- Ajoute un chemin rapide sur `rb_clear_batch_on()` et étend `lc_land` via `rb_clear_combine_run` pour fusionner 3 groupes de clear compatibles consécutifs ou plus (ex. G-buffer) en une seule passe.
- Étend la fenêtre d’anticipation de `rb_raster_then_clear` (`rb_raster_clear.h`) de `8` à `16` opérations et admet les opérations raster sans effet sur le scissor (`OP_DEPTH_CLAMP`, `OP_POLY_OFFSET`, `OP_STENCIL`, `OP_VP_SWIZZLE`, `OP_PRIM_RESTART`).

### `0421` — Leviers universels de performances NVN2 (Frame Generation adaptatif, ombres, rétention d’échelle)
- **Frame Generation adaptatif (`nvn_fi_rule.h`, `nvn_present_fi.inc`)** : machine à états pure C `dm_fi_adaptive` (EMA `0,85 / 0,15`, hystérésis d’entrée `≥ 24 ms` sur 8 images et sortie `≤ 20 ms` sur 20 images, période effective bornée `[1/36, 1/16] s`, tolérance `1,50×` rejetant les gels), activable par `S2A_RB_FI_ALL=1` ou à chaud via `s2a_rb_guest_set_frame_interp(2)` (rétrocompatible avec `0` = off et `1` = 30 Hz classique), sans altérer la vitesse de simulation invité.
- **Échelle d’ombres universelle (`nvn_mtl.m`, `nvn_rscale.inc`, `nvn_session.inc`)** : lève les limites dédiées Fire Emblem / A18 Pro / `1536×1536` vers tout GPU Metal 4 et toute shadow map carrée `D32F` de `512` à `4096` (dont Zelda `1000×1000` et MKW `2048×2048`), avec facteur `S2A_RB_SHADOW_SCALE` (`1` / `0.75` / `0.5`), quatre tableaux statiques parallèles compatibles ARC libérés en fin de session, preuve des shadow maps bindless par usage profondeur pure (`≥ 2` passes sans cible couleur) et admission des shaders alpha-test en lecture seule (`!shader_writes && !rf.pool`).
- **Rétention d’échelle de résolution universelle (`nvn_rscale.inc`)** : généralise `rs_retain_on()` à tous les titres Switch 2 sur Metal 4 dès que `S2A_RES_SCALE < 1.0` (sauf `S2A_RB_SCALE_RETAIN=0`), afin de préserver la netteté des interfaces `1920×1080` tout en réduisant le coût des cibles 3D.

### `0422` — Pipelines fluides actifs sur Mario Kart World et élimination du gel de 60–95,34 ms (`alias_orphan_pass`)
- **Pipelines fluides sur MKW (`nvn_mtl.m`)** : `0419` excluait `!rb_course_exact()`, mais MKW active `g_course_exact = 1` dès le chargement de `pso_reference.tsv`. `0422` limite l’exclusion au seul mode strict hors jeu (`rb_ref_profile_on()`, `S2A_RB_PREPARE_PROFILE`), activant le mode fluide (`S2A_RB_FLUID_PSO=1`, bascule live `s2a_rb_guest_set_fluid_pso`) pour Mario Kart World dans `pso_pend_take_ex`, `pso_get_vs`, `vp_kick` et `se_want` (hors textures `fold` qui restent synchrones).
- **Élimination du gel de 60 à 95,34 ms toutes les 300 images (`nvn_mtl.m`)** : sur les journaux MKW 844 (`[rb-report]` + `patch 0350`), la passe des textures orphelines verrouillait `g_rmu` + `g_smu` pendant `59,79 ms` pour `0` texture vérifiée/libérée (passe 12) et `56,48 + 38,61 = 95,34 ms` pour `2` textures (passe 13), parce que `rb_alias_held_ids()` parcourait toute la table `g_treg` en envoyant `.parentTexture` en Objective-C deux fois par passe même sans candidat. `0422` met en cache les pointeurs immuables `view_parent`/`view_root`/`alt_root`/`ar_root`/`im_root` lors de l’affectation dans `treg_t`, vérifie d’abord sous `g_smu` seul s’il existe un candidat orphelin (sortie immédiate sans toucher `g_rmu` ni `g_treg` quand 0 candidat), et filtre `rb_alias_held_ids_for(cands)` en C pur (zéro envoi Objective-C) sur le seul petit ensemble de candidats réels.

## 2. Pont iOS, réglages Switch 2 et 12 langues

- **Déverrouillage des 17 optimisations agnostiques dans `S2ArmEngineBridgePlugin.m`** : `S2A_RB_UP_PRESSURE_TRIM`, `S2A_RB_WG_CADENCE_IDLE`, `S2A_RB_PSO_ARCHIVE_COALESCE`, `S2A_RB_YIELD_WORKER_IDLE`, `S2A_RB_POOL_QUEUE_BUDGET`, `S2A_RB_SHADER_URGENT_UNIQUE`, `S2A_RB_TEX_FIT_FAST`, `S2A_RB_DEMAND_PROBE_BATCH`, `S2A_RB_AUDIO_REPRIME`, `S2A_RB_FB_DIRECT_SNAPSHOT`, `S2A_RB_PSO_HOT_FIRST`, `S2A_RB_SHADER_AHEAD_JOIN`, `S2A_RB_PSO_LOOK_META`, `S2A_RB_UNIFORM_BOUNDS_REUSE`, `S2A_RB_IDLE_WAIT_PROBE`, `S2A_RB_FRAME_SHADER_KEY`, `S2A_RB_RES_TOP_PER_FRAME` et `S2A_RB_BOUND_SHADER_VARIANT` passent à `"1"` pour **tous** les titres Switch 2 (et `S2A_RB_AUTO_PROBE="0"` par défaut pour supprimer le profileur à suspension de thread 500 Hz sur Zelda tout en conservant les résumés 300 images de `host.log` et la priorité de `env.txt`). La garde `S2A_RB_DRS_NO_LOCK` et le contrat anti-verrou 30 de MKW restent intacts.
- **4 nouveaux réglages Switch 2** (`S2ArmSettings`, `S2ArmSessionMenu`, `lib/services/s2arm_settings.dart`, `lib/widgets/switch2_engine_settings_panel.dart`, 12 langues dans `lib/l10n/switch2_settings_locale.dart`) :
  - `frameInterpolationAll` (Frame Generation adaptatif tous jeux — bascule à chaud),
  - `shadowQuality` (`1` / `0.75` / `0.5` — prochain lancement),
  - `pipelineMode` (`fluid` par défaut / `strict` — bascule à chaud via `s2a_rb_guest_set_fluid_pso`),
  - `performanceProfile` (`balanced` / `performance` [`S2A_RB_FLUID_PSO_MS=6`, `S2A_RB_ALLOC_FRAME_MB=32`] / `thermalDrs` [`S2A_RB_DRS_THERMAL=1`, `S2A_RB_FAIR_SCALE=0.85`]).
- **Exports invité (`export_list.py` + `S2ArmGuestABI.h`)** : ajout de `s2a_rb_guest_set_fluid_pso`.

## 3. Vérifications exécutées et limites

- **Série de patchs** : `git apply --check` + application complète `0001..0421` (417 patchs) sur la révision amont `6b6a571` réussie.
- **Vérification C pure (`gcc` et `clang -Wall -Wextra -Werror`)** : machine à états adaptative `dm_fi_adaptive` (`0421`, entrée/sortie hystérésis + rejet de gel), anticipation 16 ops + ops raster sûres + refus `OP_SCISSOR` dans `rb_raster_then_clear` (`0420`), et intégrité de l’anneau UBO `0415` (`RB_UB_FRAMES=64`, `RB_UB_SPANS=512`) — **`PURE_C_TESTS_OK`** sous `gcc` et `clang`.
- **Contrats Python pont & moteur** : 14/14 suites vertes (`s2arm_engine_bridge_test.py` 276 contrôles, `s2arm_session_menu_test.py` avec `S2ARM_UPSTREAM`, `s2arm_never_30_lock_test.py`, `s2arm_park_resume_test.py` 47 contrôles, `s2arm_engine_exports_test.py`, `s2arm_prepare_identity_test.py` 20 contrôles, `s2arm_pinned_engine_test.py`, et 7 harnais bas niveau).
- **Cohérence 12 langues Flutter** : 12 langues × 76 clés identiques vérifiées (suite `flutter test` non exécutée localement faute de SDK Flutter dans le conteneur).
- **Non mesuré sur iPhone A18 Pro** : la compilation et la livraison ne prouvent ni les FPS, ni la chauffe, ni l’absence de régression visuelle en jeu (Zelda, MKW, Fire Emblem) ; tous les gains réels restent à mesurer sur appareil.
