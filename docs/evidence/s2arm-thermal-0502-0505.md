# S2Arm · Efficacité thermique · 0502–0505

Référence `5a4b9ef24`, moteur épinglé `6b6a5715`. Cible iPhone 16 Pro Max, A18 Pro. Mesures de ce lot sur Linux x86-64. Les comparaisons de charge utilisent le code des décisions du moteur et des entrées synthétiques.

## Diagnostic de départ

- [IPA 830](s2arm-power-wall.md), Mario Kart World, GPU p50 12,0 → 34,2 ms et charge fixe 0,24 → 0,82 ms, parfois en Nominal. Le CPU du processus passe de 1,19 à 1,43 W. Ces chiffres ne donnent pas la puissance totale ni celle du GPU.
- [IPA 810](s2arm-thermal-813.md), 48 403 trames en 22,2 min. Serious à 7,2 min, 68 % des relevés en Serious. [Lot GPU récent](s2arm-gpu-0481/README.md), économies ciblées prouvées sur rejeu, et effet par image sur A18 Pro encore ouvert.
- La politique existante échantillonne pression et thermique à 500 ms. Elle tient les travaux spéculatifs dès Fair en profil strict. Les travaux déjà utilisés et enregistrés gardent 2/2/1/0 voies. Le chargement immédiat sur le dessin passe par ses propres chemins. La voie d’archives avec persistance bornée conserve son budget et ses règles de fermeture.

## Corrections et contre-mesures

| Patch | Changement | Banc hôte apparié |
|---|---|---|
| 0502 | Lire le plan valide sans reprendre le verrou de mesure. La génération invalidée ou la publication incomplète repasse par le verrou. | 16 paires de 640 000 lectures à huit threads. 10 240 000 → 16 passages par le verrou. Même nombre de relevés (16). Temps CPU médian cumulé 219,51 → 17,72 ms par lot dans le banc. |
| 0503 | En RUN borné, les libérations notifient quand un quota plein redevient disponible. | 16 000 libérations, 6 000 passages d’un quota plein à disponible. Appels de notification 32 000 → 12 000. Les deux budgets 2 et 4, ONE et les réveils de fermeture gardent leurs règles. Avec quatre workers sans travail et 100 libérations sous le quota, les sorties d’attente pour signal passent de 400 à 0. Réveils en jeu non mesurés. |
| 0504 | Deux relevés indépendants de la sonde après calibration, avec charge jeu corroborante, peuvent limiter les admissions facultatives à un seul worker. | 3 000 cycles synthétiques et 120 000 observations perturbées, y compris régime déjà lent au départ, trou, pic, données périmées, chaud, reprise et nouvelle session. Exemple de 60 intervalles, 102 → 75 admissions facultatives et 51/51 prioritaires dans les deux bras. |
| 0505 | Les notifications thermiques et Low Power Mode invalident la mesure et réveillent seulement le worker chargé du relevé. | Sept paires avec événement à 20 ms et délai de secours de 500 ms. Attente médiane du worker 500,15 → 20,15 ms dans le banc. Les doublons durant l’invalidation n’ajoutent aucun signal. |

En simulation, 0504 signale l’écart au second relevé lent à t=17, avec l’état OS critique simulé à t=43. Ce décalage imposé au scénario sert à vérifier que les deux sources restent distinctes. Quatre états thermiques, fermeture, seuils de mémoire et PSO liés au dessin restent pilotés comme avant. Le test `t_rb_spec_gate` existant et les cas de fermeture sous ASan/UBSan passent sur hôte. TSan a aussi passé la lecture concurrente du plan et le réveil sur invalidation.

### Rejouer le banc hôte

Compiler le [banc manuel](s2arm-thermal-0502-0505/thermal_bench.c) avec les en-têtes de la source S2Arm après application du lot. Les états OS et la sonde sont simulés. Les mutex, conditions et temps CPU Linux sont réels.

```bash
cc -std=gnu11 -O3 -Wall -Wextra -Werror -pthread \
  -I "$S2ARM_PATCHED_ROOT/graphics/nvn/gfx/nvn" \
  docs/evidence/s2arm-thermal-0502-0505/thermal_bench.c -o /tmp/s2arm-thermal-bench
/tmp/s2arm-thermal-bench bench
```

### Réglages et limites

- `S2A_RB_SPEC_SNAPSHOT=0`, `S2A_RB_SPEC_COALESCE_WAKE=0` et `S2A_RB_SPEC_EVENT_WAKE=0` restaurent séparément le comportement précédent. Les trois optimisations de coordination sont actives par défaut.
- `S2A_RB_ENERGY_SPEC_GUARD=1` est un essai sur iOS physique, chemins NVN2 directs Metal 3/4. `S2A_RB_ENERGY_DIAG=1` journalise chaque mesure consommée et transition `[RB-ENERGY-SPEC]`, avec ou sans garde. La sonde conserve sa cadence existante. Un relevé de durée fixe ne donne ni MHz ni température.
- 0504 exige une référence nominale et deux mesures ≥1,6× avec au moins 3 des 5 images précédentes ayant coûté ≥10 ms côté GPU. Récupération à ≤1,25×, deux relevés et maintien minimal de 5 s. Au-delà de 25 s sans donnée, le garde rend la main aux politiques existantes. Les seuils devront être vérifiés sur A18 Pro.
- Les parcours à faible charge, les régimes déjà ralentis avant la calibration et l’absence de télémétrie peuvent limiter la détection. L’interdiction d’inférer des watts, de la fréquence ou de l’énergie totale à partir de ces compteurs reste valable.

## Réception iPhone

Avec le [Banc d’essai](../s2arm-benchmark-protocol.md), configurer trois paires par titre sur iPhone17,2, en alternant A/B et B/A. Tester Mario Kart World 1.0.0 Coupe Champignon 150 cc, Zelda, Fire Emblem et un autre NVN2. Même réglage 1×, même route et sauvegarde, caches compatibles de départ équivalents, éclairage et luminosité fixes, chauffe et batterie comparables, appareil débranché, Frame Generation désactivée, mêmes versions GPU/CPU/RAM.

Tracer le démarrage, le chargement, l’arrivée en jeu, la pause et le retour au premier plan. Faire 30 min par bras et prendre les fenêtres à 1/5/10/20/30 min. Le [compagnon de cadence du lot parallèle](../../tools/s2arm_a18pro/NEXT_PARALLELISM.md) peut fournir ces jalons si `S2A_RB_PARALLEL_LONG=1` est identique dans les deux bras. Rapporter séparément les FPS natifs, frametimes p50/p95/p99, GPU p50/p95/p99, sonde, latence des travaux indispensables, admissions et files, réveils secondaires, CPU actif, seuil et récupération de la sonde, temps mural dans chaque état OS. Utiliser les mesures CPU en W déjà disponibles en tant que mesure du CPU du processus. Puissance GPU, puissance totale et mJ/image exigent leur propre source de mesure. Comparer les diagnostics désactivés/activés par une paire dédiée avant de les utiliser pour mesurer leur surcoût.

Les résultats de ce lot établissent une réduction du travail d’ordonnancement sur hôte. L’effet réel sur l’énergie et le délai avant plafonnement reste à mesurer sur appareil.

### Compilations Apple

Le [run 46024696863](https://github.com/TarbleFR/RewindBox/actions/runs/46024696863) compile le moteur `584435cb9` pour iPhoneOS sur macOS 15 et 26. Les patches parallèles 0506–0512 s’appliquent après lui et le banc hôte repasse avec les en-têtes combinés de `174731462`.
