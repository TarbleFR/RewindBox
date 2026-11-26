# S2Arm 0431–0436 — Boucle comparative de performances, fidélité graphique et caches froids/chauds (26 novembre 2026)

Référence moteur : `0430` (avec observations appareil de la référence `845` en `0426`, journaux Zelda `0400486024DEC000` / `04007EF01F8AE000`, journaux Mario Kart World `0400C3F00006E000`, profil `20261126-140625-rec/frames.txt` et vidéo Moo Moo Meadows `ScreenRecording_11-26-2026 14-06-06_1.mov`).

Tous les correctifs `0431–0436` sont **structurels et universels pour l’ensemble du catalogue Switch 2 / NVN2** : aucun branchement spécifique à Mario Kart World ou Zelda, aucune baisse de résolution (`1×` conservé), aucun changement de vitesse invitée, aucun relâchement des tests ou gardes thermiques (`RB_PRESENT_COMP_NS = 2 000 000 ns`, `RB_REGISTRATION_TRICKLE = 16` au démarrage), `S2A.Dsh` inchangé (`xfp = ecd99354f03b846d`) et caches existants préservés.

> **Portée et limites strictes.** Aucune IPA n’a été générée ni livrée à ce stade. Les chiffres ci-dessous proviennent des journaux 845 (état avant changement) et de bancs comparatifs reproductibles sur hôte Linux x86-64 (Clang `-O2 -Wall -Wextra -Werror -fsanitize=address,undefined`) exécutés sur les fonctions C/headers exactes extraites de `0430` vs `0431–0436`. **Les FPS réels, frametimes, chauffe, mémoire et fidélité visuelle sur iPhone A18 Pro restent non mesurés.** La maturité S2Arm reste à **50 %**.

---

## 1. Analyse forensique des glitches graphiques (vidéo Moo Moo Meadows) et des journaux 845

### 1.1 Glitches visuels observés sur Moo Moo Meadows (`20261126-140625-rec` / `ScreenRecording_11-26-2026 14-06-06_1.mov`)

La vidéo montre des **explosions HDR vert/jaune fluo** sur les arbres d’arrière-plan (imposteurs de feuillage) et les nuages, ainsi que des **boîtes à objets cyan/magenta sur-exposées**, qui **persistent plusieurs secondes** même après le retour à `skipped == 0` dans le compteur de pipelines différés. Le croisement image par image avec `20261126-140625-rec/frames.txt` et les sources `0419–0426` isole **quatre défauts architecturaux distincts** :

1. **Saut de cibles persistantes ou précalculées ponctuelles en mode fluide (`0419`/`0422`)** : aux images `F23882` et `F23944..23955`, `pso_pend_take_ex` / `pso_get_vs` permettait de sauter des dessins ciblant des render targets non rafraîchies chaque image (`!rt_fresh_now`) ou non encore stabilisées (`!rt_seen_steady`, cas des cubemaps, sondes IBL, imposteurs de feuillage et LUTs calculés une fois à l’entrée d’un circuit). Sauter ce dessin unique laisse la cible dans un état non initialisé/corrompu pour toute la course.
2. **Réutilisation entière de bloc d’arguments sans exclure Compute ni les états mutables (`0423`/`0424`/`0426`)** :
   - Sur le stade Compute (`nvn_stage == 5`), la réutilisation entière de bloc d’arguments court-circuitait la mise à jour de `g_c0_dim_buf` (laissé `nil`) et réutilisait des dimensions de dispatch `c0+0x200` périmées.
   - Les shaders lisant des handles empaquetés dans un UBO (`TEXU`/`SAMPU`/`IMGU`/`TBUFU`/`SBUFU`), ou utilisant des accès `rw`, géométrie (`geo`), mémoire globale (`gmem`), tableaux non bornés (`unb`), `ab_ub`, `rb_shadow_n` ou `g_nubd` pouvaient réutiliser un bloc obsolète lorsque la mémoire UBO (`g_rb_cont_mem_gen`) changeait sans changement de binding explicite.
3. **Incohérence de génération des vues lors des évictions DRS (`0425`)** : le scoping local `rb_serial_local_locked` dans `alias_take_over`, `tex_upgrade` et `rb_swap_storage_locked` ne forçait pas un incrément global `g_ser_gen++` quand un parent jumelé sRGB/linéaire (`g_twin_parent_key`) ou une table d’alias active (`g_bcal_n > 0`) était présent lors des rafales d’éviction de résolution dynamique (`17` à `105` textures par palier), et `rb_clear_combine_run` omettait `rt_seen_mark` sur les groupes fusionnés.
4. **Inversion `may_skip` de `0419` provoquant des gels de 466 à 2 202 ms malgré Fluid Pipelines** : dans `pso_pend_take_ex`, `fluid_cap` exigeait `!may_skip`. Pour un dessin skippable (`may_skip == 1`, `storage_writes == 0`) sous `rb_course_exact()`, `!fluid_cap` basculait à `1` et forçait `required = 1`, court-circuitant tous les plafonds (`6–12 ms`) et bloquant le fil de soumission jusqu’à compilation complète (`466,0`, `535,1`, `1 226,1`, `2 202,5 ms` et `184,3 ms` à l’image filmée `7 954`).

### 1.2 Goulots CPU/GPU, Frame Generation et caches froids/chauds sur Zelda et MKW (845)

- **Frame Generation (`844 → 845`)** : sous charge GPU soutenue (`Serious`), `fi_job` continuait à soumettre MetalFX (`encodeToCommandBuffer`, `11,57–16,20 ms`) uniquement pour amorcer l’historique sur des paires tardives rejetées à l’affichage (`194` primes perdus sur 900 images en rejeu calibré) et faisait osciller l’attachement/détachement DisplayLink, aggravant la saturation GPU.
- **Textures & `pool_gpu()` (`MKW` images `6 090` et `7 746`)** : `175` et `136` premières mises en mémoire (`109,4` et `110,6 ms` CPU, `1 230` et `3 363` pages absentes) sans prélecture groupée par soumission ; la file bind-lane postait des identifiants déjà résolus ou hors package ; `pool_gpu()` verrouillait un mutex et appelait l’horloge deux fois à chaque lookup ; `pool_seen_scan()` rebalayait inutilement en l’absence de mutation réelle.
- **Zelda soumission CPU (`engine__04007EF01F8AE000__host-20261126-130053.log`)** : `741 230` sur `885 530` parcours complets `encode_args_` / 300 images prenaient le mutex `g_rmu` pour des shaders sans texture/image (vertex shaders) ; `g_dsnap` perdait son snapshot dès un changement de passe couleur seule ou alternance de profondeur (`3 300` copies / 300 images = `1 268,1 Mo`).
- **Caches froids vs caches chauds (nouveaux environnements / circuits / effets)** :
  - *Cache chaud bloqué en `Fair`* : `rb_stage_disk.inc` exigeait `thermal == 0` ET `worker == 1` (impossible sous `RB_SPEC_ONE`), laissant **`1 425` stages Zelda** et **`1 593` stages MKW** déjà traduits sur disque non chargés (`0` réchauffé) jusqu’à leur première rencontre bloquante (`3 645,8 ms` à l’image Zelda `3 614`).
  - *Cache froid lors d’une découverte* : `rb_registration.inc` plafonnait l’admission en jeu à `16` stages / `8 Mio` par rafale, différant massivement les nouveaux shaders jusqu’au premier draw bloquant, tandis que `ppq_build` n’enregistrait pas les recettes réellement observées différées en mode fluide dans `pso_user.tsv` (forçant un nouveau miss au lancement suivant).

---

## 2. Correctifs structurels livrés (`0431`–`0436`)

| Patch | Fichiers moteur modifiés | Rôle structurel universel |
| --- | --- | --- |
| [`0431`](../../../build-utils/s2arm/engine/patches/0431-fluid-pso-unified-cap-and-skippable-inversion-fix.patch) | `rb_fluid_pso_rule.h` *(nouveau)*, `nvn_mtl.m` | Règle unifiée `rb_fluid_pso_decide` / `rb_fluid_pso_skip_sync` : corrige l’inversion `may_skip`, supprime les gels non bornés sur dessins skippables et empêche le repli synchrone hors budget d’image. |
| [`0432`](../../../build-utils/s2arm/engine/patches/0432-fi-bound-overload-priming-link-hysteresis-and-fp16-mv.patch) | `nvn_fi_rule.h`, `nvn_present_fi.inc` | `dm_fi_should_prime` (coupe le priming MetalFX inutile sous surcharge GPU et à 60 Hz adaptatif, réinitialise l’historique à la reprise), `dm_fi_link_hyst` (anti-rebond DisplayLink), noyau MV FP16 + `zsad` SIMDgroup (`−50 %` mémoire threadgroup). |
| [`0433`](../../../build-utils/s2arm/engine/patches/0433-treg-cand-bitset-sub-ahead-and-pool-gpu-fast-path.patch) | `rb_treg_cand.h` *(nouveau)*, `nvn_mtl.m`, `rb_texture_ahead.inc` | Bitset lock-free 128 Kio `g_rb_treg_cand` pour filtrer `rb_bl_record`, pré-scan lecture seule borné par soumission (`rb_sub_ahead_prescan`, `MADV_WILLNEED`, 128 tex / 64 Mio), chemin rapide `pool_gpu()` sans mutex ni horloge, `pool_seen_scan()` indexé par `ser_mut`. |
| [`0434`](../../../build-utils/s2arm/engine/patches/0434-fidelity-args-coherence-lockfree-rmu-and-view-buckets.patch) | `rb_fluid_pso_rule.h`, `rb_args_ubo.h`, `rb_view_epoch.h`, `nvn_mtl.m` | Protège `persistent_rt` (`!rt_fresh_now || !rt_seen_steady`) dans Fluid Mode ; ferme les failles de réutilisation `rb-args` (Compute, `has_rw`/`has_geo`/`has_gmem`/`has_unb`, `ab_mem_gen`, `ab_ub`, `shadow_n`, `had_ubd`, `nubd`) ; évite `g_rmu` + `same_views` sur shaders sans texture ou UBO seul ; force `g_ser_gen++` sur `g_twin_parent_key` / `rb_bcal_active()` ; appelle `rt_seen_mark` dans `rb_clear_combine_run` ; porte `RB_VIEW_BUCKETS` à `4 096`. |
| [`0435`](../../../build-utils/s2arm/engine/patches/0435-cold-warm-shader-disk-fair-burst-xlate-and-pso-persist.patch) | `rb_cache_warm_rule.h` *(nouveau)*, `rb_stage_disk.inc`, `rb_registration.inc`, `nvn_session.inc`, `nvn_mtl.m` | Pré-vérification `rb_disk_stage_cached` et réchauffage disque en `Fair` sur `worker=0` sous gardes strictes (`!busy && !fu_waiting && !warm_running && !mem_low && room >= 1 536 Mio`) ; conservation exacte du trickle de boot (`16`/`8 Mio`), extension live post-préchauffage (`48`/`32`) + file CPU-only `s2a.nvn2.xlate` (`QOS_CLASS_UTILITY`, 128 stages / 16 Mio) sans `MTLCompilerService` ; persistance `pso_user.tsv` dès `par_render` terminé pour toute recette réellement observée (`now != 0`). |
| [`0436`](../../../build-utils/s2arm/engine/patches/0436-dsnap-two-slot-lru-cache-and-non-destructive-set-rt.patch) | `rb_dsnap_rule.h`, `nvn_mtl.m` | Cache LRU à 2 emplacements `g_dsnap` survivant aux passes couleur seules et alternances de cibles profondeur, invalidation croisée d’alias de stockage, `ser_mut` lock-free, flush `after_d`/`after_s` avant `OP_SET_RT`/`OP_CLEAR_DS`/`OP_COPY_*`, invalidation `OP_WAIT_SYNC`/`OP_DISPATCH` (miroir `g_dsnap.use` conservé). |

---

## 3. Mesures comparatives sur hôte (`0430` vs `0431–0436`, conditions identiques, ASan + UBSan)

Chaque banc compile et exécute directement les headers/règles C du moteur (`-std=gnu11 -O2 -Wall -Wextra -Werror -fsanitize=address,undefined`) sur le même hôte Linux x86-64, avec les mêmes séquences d’entrée et des contrôles de mutation négatifs prouvant que chaque invariant détecte réellement une régression.

### 3.1 Cache froid (premier passage, découverte de nouveaux environnements / shaders / textures)

| Domaine / Banc | Référence `0430` | Candidat `0431–0436` | Écart mesuré | Contrôles / Mutations |
| --- | ---: | ---: | ---: | --- |
| `0431` — Attente PSO cumulée (rejeu MKW+Zelda 845) | `4 711,3 ms` | `82,3 ms` | **`−98,3 %`** | 512/512 états, 4/4 mutations, `sw_deferred = 0` |
| `0431` — Pic d’attente PSO par image (`storage_writes=0` vs `=1`) | `2 202,5 ms` | `35,0 ms` (`6,0 ms` skippable) | **`−98,4 %`** | `stalls > 16,6 ms : 7 → 1` |
| `0435 [B1]` — Rafale froide 96 nouveaux stages en `Fair` : différés | `80` différés (`16` admis, `0` bg xlate) | **`0`** différé (`32` admis, `64` bg CPU xlate) | **`−100,0 %`** | `boot trickle = 16` préservé, 6/6 mutations |
| `0435 [B1]` — Stall traduction sur fil de soumission (rafale 96 stages) | `520,0 ms` | **`0,0 ms`** | **`−100,0 %`** | `+288,0 ms` `MTLLibrary` asynchrones économisés |
| `0433 [B2]` — Pré-scan textures par soumission (rafale 175 textures) | `0` préchargée en lot | `128` uniques (`MADV_WILLNEED`, cap 64 Mio) | Lot borné | Coût établi = `1` lecture atomique |
| `0434 [B1]` — Cibles persistantes / one-shot sautées à tort | `20` corrompues | **`0`** corrompue | **`−100,0 %`** | Passes `over_prepass` fraîches toujours `≤ 6 ms` |

### 3.2 Cache chaud et régime soutenu (passages suivants, CPU soumission, GPU, Frame Gen, fidélité)

| Domaine / Banc | Référence `0430` | Candidat `0431–0436` | Écart mesuré | Contrôles / Mutations |
| --- | ---: | ---: | ---: | --- |
| `0435 [B2]` — Stages disque hors liste réchauffés en `Fair` (Zelda / MKW) | `120/1 425` / `0/1 593` | **`1 425/1 425`** / **`1 593/1 593`** | **`100,0 %`** | `0` fuite en `Serious`, `mem_low` ou `fu_waiting` |
| `0434 [B2]` — Réutilisations `rb-args` corrompues (100k tirages) | `57 837` | **`0`** | **`−100,0 %`** | `42 163` réutilisations valides conservées, 5/5 mutations |
| `0434 [B3]` — Verrous `g_rmu` sur profil Zelda 300 images | `923 929` (`4,86 ms`) | `144 300` (`0,76 ms`) | **`−84,4 %`** (**`6,37×`**) | `t_rb_args_ubo` vert |
| `0434 [B4]` — Fausses collisions de seaux de vues (`1 024 → 4 096`, 120k) | `11 702` | `2 926` | **`−75,0 %`** | `t_rb_view_scope` vert |
| `0433 [B1]` — Envois bind-lane inutiles (300 images) | `12 258` (`12 900` total) | **`0`** (`642` utiles conservés) | **`−100,0 %`** | 5/5 mutations `rb_treg_cand` |
| `0433 [B3]` — `pool_gpu()` sur 1 M d’appels (temps / verrous / horloges) | `61,79 ms` / `1 000 000` / `2 000 000` | `6,09 ms` / **`0`** / `122` | **`10,14×`** (`−90,1 %`) | Zéro mutex sur chemin rapide |
| `0433 [B4]` — Mises à jour `pool_seen_scan` (300 soumissions) | `96 000` | `8 400` | **`−91,2 %`** | Recontrôle complet sur mutation `ser_mut` |
| `0436 [B1]` — Blits snapshot profondeur Zelda 300 images (2-slot LRU) | `1 500` (`4 838,4 Mo`) | `600` (`1 728,0 Mo`) | **`−60,0 %`** (`−64,3 %` Mo) | `t_rb_dsnap_rule` + 4/4 mutations |
| `0432` — MetalFX Frame Gen : primes perdus en surcharge (900f MKW) | `194` (`585` mid) | `26` (`585` mid identiques) | **`−86,6 %`** | `14/14` retards isolés préservés (`t_fi_link`) |
| `0432` — Bascules DisplayLink / primes 60 Hz adaptatif / mémoire TG MV | `180` / `100` / `6 656 o` | `1` / **`0`** / `3 328 o` | **`−99,4 %`** / **`−100 %`** / **`−50 %`** | Parité MV FP16 vs FP32 : `128/128` exacte |

---

## 4. Tests de non-régression et compilation

- **Application propre de la série complète `0001..0436`** sur le pin S2Arm `6b6a5715` : `git apply` sans conflit, arbre résultant identique octet par octet à la branche de travail.
- **Suite C NVN portable (ASan + UBSan, `-Wall -Wextra`)** : **24/24** tests unitaires portables verts (`t_rb_args_ubo`, `t_rb_view_scope`, `t_rb_dsnap_rule`, `t_rb_registration_plan`, `t_rb_bind_lane`, `t_rb_bind_facts`, `t_rb_clear_batch`, `t_rb_attachment_liveness`, `t_rb_alias_key`, `t_rb_archive_index`, `t_rb_audit_sample`, `t_rb_course_history`, `t_rb_display_hold`, `t_rb_drs_control`, `t_rb_drs_fx_extent`, `t_rb_fb_dirty`, `t_rb_file_hint`, `t_rb_fx_prefix`, `t_rb_gov_stress`, `t_rb_look_budget`, `t_rb_pool_index`, `t_rb_promotion`, `t_rb_pso_trace`, `t_rb_thermal_pacing`).
- **Contrats du dépôt Python** : `s2arm_upstream_switch2_fixes_test.py`, `s2arm_legal_bundle_test.py`, `s2arm_pinned_engine_test.py`, `s2arm_never_30_lock_test.py`.
- **Compilation iOS arm64 (`s2arm-engine.yml`, `macos-15` + `macos-26`)** : déclenchée par le commit `[s2arm-engine]` (sans génération d’IPA ; lien du run ajouté dès validation).

## 5. Validation requise sur iPhone A18 Pro (non exécutée)

Les mesures suivantes restent à effectuer sur appareil avant toute révision de la note de maturité (50 %) :
1. **Cache froid (premier passage)** : nouveau circuit MKW (dont Moo Moo Meadows) et nouvelle zone Zelda avec cache shaders vidé, en relevant séparément cadence moteur réelle (interpolation coupée), p95/p99, pauses `>100 / >500 ms`, absences de glitches HDR/sur-exposition et persistance effective dans `pso_user.tsv`.
2. **Cache chaud (passages suivants)** : 3 × 180 s à `1×` appariés (même état thermique initial), d’abord **sans Frame Generation** (mesure du vrai FPS moteur), puis **avec Frame Generation** (mesure séparée des images réelles vs générées et du temps GPU MetalFX).
