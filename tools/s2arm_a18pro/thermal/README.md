# Endurance S2Arm · Banc hôte et comparaison iPhone

Compiler le banc manuel contre l’arbre S2Arm avec les patches appliqués.

```sh
cc -std=gnu11 -O2 -Wall -Wextra -Werror -pthread \
  -I "$S2ARM_PATCHED_ROOT/graphics/nvn/gfx/nvn" \
  tools/s2arm_a18pro/thermal/energy_bench.c -o /tmp/s2arm-energy-bench
/tmp/s2arm-energy-bench
```

Sur iPhone17,2, appliquer les réglages au lancement. Le moteur journalise le backend sélectionné. Refaire la matrice sur chaque backend à comparer. Conserver `S2A_RB_SPEC_GOVERN`, le JIT, les réglages graphiques, la mémoire et la concurrence GPU à l’identique. Les options de cadence de sonde et d’archives changent dans des paires séparées.

| Configuration | `ENERGY_SPEC_GUARD` | `ENERGY_DIAG` | `ENERGY_PREDICT_DIAG` | `ENERGY_PREDICT` |
|---|---:|---:|---:|---:|
| Historique, politique OS | 0 | 0 | 0 | 0 |
| Garde 0504 corrigé | 1 | 1 | 0 | 0 |
| V2 observation | 0 | 0 | 1 | 0 |
| V2 actif | 0 | 0 | 1 | 1 |

Ajouter `S2A_RB_` devant chaque variable du tableau. Refaire observation/action avec la même sonde, par exemple `S2A_RB_ENERGY_ADAPT_PROBE=1` dans les deux bras, puis mesurer le coût du diagnostic par une paire dédiée. Une cadence explicite `S2A_RB_PROBE_EVERY` a priorité. `S2A_RB_ARCHIVE_EVENT_DIAG=1` relève le writer avec ou sans `S2A_RB_ARCHIVE_EVENT_WAKE=1`.

## Durées, mesures et rejeu

- Avec `S2A_RB_PARALLEL_LONG=1` dans les deux bras, déclencher le Banc d’essai au repère convenu. Récupérer la cadence native et ses jalons 1, 5, 10, 20, 30 min. Extraire aussi les fenêtres 0–5 et 25–30 min d’une trace native à horodatages individuels. Un export qui donne seulement un cumul à 20 et 30 min ne suffit pas pour la dernière fenêtre de cinq minutes.
- Récupérer `host.log`, la cadence et les mesures indépendantes. Le [compagnon CPU/GPU](../parallelism/timeline.py) calcule les unions et le recouvrement sur sa fenêtre instrumentée. Capturer les fenêtres d’horodatage GPU, énergie et PSO indépendamment des passages de score si leurs diagnostics modifient les timings.
- Annoter le démarrage, le menu, le chargement, les quatre circuits, la pause et la reprise. Étiqueter les épisodes du bras observation sur des fenêtres de géométrie et de soumission comparables, avec plusieurs passes GPU ralenties. Conserver l’heure du premier indice indépendant. Un épisode déjà présent au début et un épisode traversant une interruption sont censurés.
- Comparer trois paires alternées par titre. Relever GPU et frametimes p50/p95/p99, fenêtres natives, CPU/GPU actifs et recouvrement, attente des PSO, transferts, réveils facultatifs et températures OS. Déclarer les watts CPU du processus avec leur source. Un appareil ou un outil externe doit fournir les joules et les images natives sur la même fenêtre pour obtenir `1000 × joules / images natives` en mJ/image.

Pour un relevé d’impact relatif, enregistrer Power Profiler appareil débranché, via une trace sur l’iPhone ou Instruments sans fil. Le GPU s’y compare sur le même appareil. Le taux global est exprimé en fraction d’énergie de batterie par heure. [Documentation Apple](https://developer.apple.com/documentation/xcode/measuring-your-app-s-power-use-with-power-profiler).

Créer localement un manifeste `sessions` avec des entrées `id`, `configuration` (`historical`, `reactive`, `observe_v2`, `active_v2`), `source` (`device` ou `synthetic`), `split` (`calibrate`, `holdout`, `ab`), `host_log` et `start_ns`/`end_ns` dans l’horloge monotone du journal thermique. Les chemins sont relatifs au manifeste. Indiquer `identity` (jeu, build, appareil, backend, OS, parcours, caches), `cadence` (JSON natif), `phase_marks`, `measurements` et `power_measurement` si disponibles. Le JSON de cadence utilise sa propre horloge.

En option, `native_frames_csv` accepte un export normalisé avec une ligne par image native et les colonnes `t_ns,gpu_exec_ns,required_wait_ns`. Les deux durées peuvent rester vides. Fournir une fenêtre intégralement couverte sur la même horloge. L’outil calcule les FPS, les quantiles et les intervalles longs sur les jalons et les cinq premières/dernières minutes. Les durées bordant les fenêtres et la couverture des compteurs restent visibles.

Pour scorer, ajouter `truth_source` et `truth` (liste ordonnée des couples `start_ns`/`end_ns`, vide si aucun épisode indépendant) à une session `observe_v2` de `holdout`. Recueillir au moins deux relevés valides avant l’épisode pour évaluer sa prédiction. Fixer l’horizon à partir du jeu de calibration avant d’ouvrir la validation.

```sh
python3 -B tools/s2arm_a18pro/thermal/analyze.py capture-privee.json --horizon-s 8
```

Ajouter `pairs: [{"a": "<id-A>", "b": "<id-B>"}]` au manifeste pour calculer les écarts B−A par fenêtre native. Renseigner la même identité de l’appareil, du moteur et du parcours dans les deux bras.

L’outil donne l’avance et les alarmes, les épisodes manqués ou non évaluables, les quantiles de la sonde et l’attente séparée, la couverture temporelle et les admissions observées. Garder les journaux privés selon le [protocole](../../../docs/evidence/s2arm-thermal-0524-0527.md).
