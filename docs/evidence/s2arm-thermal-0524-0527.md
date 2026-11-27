# S2Arm · Endurance GPU A18 Pro · 0524–0527

Base `cb6a302a`, moteur `6b6a5715`. Les quatre journaux 830 sont représentés par leurs [agrégats publiés](s2arm-power-wall.md). À charge de sonde fixe, 0,24 → 0,82 ms, GPU de course 12,0 → 34,2 ms p50, image 23,7 → 41,5 ms p50. La chute apparaît aussi en Nominal et précède parfois le passage du jeu à 30 i/s. Cela établit un ralentissement GPU hors de la seule complexité des scènes. Puissance du SoC, contention et fréquence exacte restent à distinguer. Le déficit à froid subsiste avec un GPU à 12 ms et demande de réduire la soumission CPU et les attentes.

| Patch | Fonction | Retour au témoin |
|---|---|---|
| 0524 | Une seule décision d’admission. La montée de la durée d’une sonde fixe, trois mesures de charge jeu sur cinq et une référence relative déclenchent une limitation facultative graduée. Les voies de démarrage au premier plan, les rangées de PSO déjà utilisées/enregistrées et les régimes OS conservent leurs règles. | `S2A_RB_ENERGY_PREDICT=0`. `S2A_RB_ENERGY_PREDICT_DIAG=1` observe indépendamment. |
| 0525 | Sonde à cadence monotone bornée (2/3/5/8 s selon l’état) et mesure séparée du délai avant GPU, de l’exécution GPU et du coût CPU d’encodage. Les options de fréquence explicites gardent priorité. | `S2A_RB_ENERGY_ADAPT_PROBE=0`. |
| 0526 | Le writer d’archives refusé attend un signal ou un secours de 1,5 s. L’époque prise avant le refus protège l’armement. Fermeture, sérialisation, quotas de persistance et mises à jour d’index gardent leurs bornes. | `S2A_RB_ARCHIVE_EVENT_WAKE=0`. `S2A_RB_ARCHIVE_EVENT_DIAG=1` mesure les deux bras. |
| 0527 | Changements OS antérieurs à la décision, baisse de cadence de sonde en présence d’une attente PSO indispensable, minuterie d’archive obsolète et périmètre Metal 3/4 vérifiés. | Interrupteurs des chemins concernés. |

Le candidat apprend une enveloppe basse relative sur trois observations chargées qui concordent à 15 %. Elle se corrige seulement vers le bas, avec trois confirmations. Un démarrage déjà lent peut encore établir une référence relative élevée. Deux montées indépendantes d’au moins 25‰/s, un ratio de 1,20–1,60× et quatre secondes de charge ouvrent la prévention. Deux points à ≥1,60× confirment le régime lent. Le premier palier rend une place supplémentaire après une baisse corroborée ou une prévention expirée. Charge légère répétée, changement OS ou absence de données utiles pendant dix secondes rendent la main. Les seuils servent au banc et restent à valider sur sessions physiques indépendantes.

## Contre-expertise

- Complexité du jeu, saturation, PSO, page-ins, synchronisation et présentation se vérifient chacun avec leurs propres traces. Même charge fixe ralentie et plusieurs passes ralenties constituent un indice de changement de régime. L’état thermique OS, la puissance CPU du processus et les compteurs GPU ne mesurent pas la même grandeur.
- Le coût avant course inclut la compilation de la sonde, les recettes de démarrage et des menus parfois lourds. La cadence expérimentale évite de lancer la sonde pendant une attente PSO du rendu et la suspend hors premier plan. Le polling de `mtl_warm_wait` a des appels dans les fixtures uniquement sur cette tête. La voie de PSO prioritaires et les prélectures proches du premier dessin gardent leur priorité.
- GPU 0481, ombres 0518–0523, compilation de shader, MSAA et RAM doivent rester à version identique entre les bras. L’addition des options de parallélisme a déjà augmenté le p95 synthétique de 7,95 à 22,53 ms. Couvrir les interactions après le premier A/B isolé. [Rejeu Metal 3](s2arm-parallelism/README.md).
- Relecture d’une archive de 87 anciens journaux hôte. 37 contiennent une durée de sonde, 710 points au total. 32 des 35 journaux ayant au moins trois points ont un maximum ≥1,6× leur minimum. Dans 16/35, le premier point dépasse déjà 1,6× le minimum ultérieur. Ces rapports mélangent des charges et des phases différentes. Il manque l’heure de soumission de chaque sonde et les cinq images qui la corroborent. Ces relevés établissent la nécessité du contexte de charge et ne permettent pas de scorer une avance physique.

## Résultats mesurés sur hôte

[Rejeu C et analyseur des sessions](../../tools/s2arm_a18pro/thermal/README.md). Les huit séquences imposent leurs charges et événements. Les chiffres ci-dessous portent sur ces séquences.

| Scénario (60 intervalles) | Historique | Garde corrigé | V2 observation | V2 actif |
|---|---:|---:|---:|---:|
| Montée lente, admissions facultatives | 120 | 103 | 120 | 99 |
| Rupture forte, admissions facultatives | 120 | 103 | 120 | 104 |
| Hausse modérée qui se stabilise, admissions facultatives | 120 | 120 | 120 | 114 |
| Montée lente, admissions au premier plan | 120 | 120 | 120 | 120 |

Sur la montée progressive, la prévention apparaît à 17 s. Le régime lent commence à 21 s et les deux gardes le confirment à 22 s. Sur la rupture brusque, les deux gardes n’alertent qu’après l’apparition du régime lent. La hausse modérée donne une alerte sans épisode lent. À seuils illustratifs, la moyenne mobile déclenche à 19 s sur la montée et sur la hausse modérée. Un compteur de charge seul alerte aussi sur charge stable et changement ordinaire de scène. Un seuil instantané de 1,60× repère la rupture à son apparition. Le candidat reste opt-in compte tenu de ces limites.

Sur Linux x86-64, 15 paires de 240 000 entrées identiques donnent un coût médian de logique de 13,02 ns/relevé pour 0504 et 10,26 ns pour v2. Hors acquisition, Metal, verrous d’intégration et journalisation. Les deux bancs et le test de réservation passent. ASan et UBSan passent avec la recherche de fuites désactivée sur cet hôte. TSan valide la réservation concurrente et la réouverture du quota en présence d’une voie prioritaire. Le rejeu 0513–0517 donne toujours 102→76 admissions facultatives, 51/51 prioritaires et 120 000 observations bruitées.

Le [contrôle Apple du writer](https://github.com/TarbleFR/RewindBox/actions/runs/46041272246/job/140649314281) réussit le réessai périodique, le signal, le secours sans signal, la fermeture et le signal reçu avant l’armement. Les cinq cas persistent et rouvrent strictement le pipeline Metal. Sous un refus injecté d’environ 3,2 s, les réveils de réessai passent de 12 à 3 (deux secours et un signal), soit −75 % dans ce seul essai apparié. Temps CPU writer, écriture comprise, 1,72 → 1,69 ms. La variante sans signal revient au bout de 1,51 s. Effet énergétique sur appareil à mesurer.

Le moteur source `4526a952` compile pour iPhoneOS sur [macOS 15](https://github.com/TarbleFR/RewindBox/actions/runs/46041272246/job/140649314681) et [macOS 26](https://github.com/TarbleFR/RewindBox/actions/runs/46041272246/job/140649314281). [Frameworks de la CI](https://github.com/TarbleFR/RewindBox/actions/runs/46041272246/artifacts/15220024391). Aucune IPA produite. FPS, watts GPU, énergie par image, récupération et avance sur A18 Pro non mesurés.

## Réception sur iPhone17,2

Comparer trois paires A/B puis B/A par titre, 30 min par bras à 1×, Frame Generation coupée et mêmes caches compatibles, sauvegarde, parcours, luminosité, environnement, plage de batterie et identité moteur. Après refroidissement comparable, lancer Mario Kart World 1.0.0 Coupe Champignon 150 cc (quatre circuits), Zelda, Fire Emblem et un quatrième NVN2 à profil distinct. Marquer lancement, menu, chargement, course, pause et reprise. Couvrir 1/5/10/20/30 min et les cinq premières/dernières minutes. [Banc d’essai](../s2arm-benchmark-protocol.md).

Comparer d’abord historique, garde 0504 corrigé, observation v2, puis prédiction v2 active. Garder la même cadence et le même coût diagnostique pour la comparaison observation/action. Confirmer séparément la cadence de sonde et le writer événementiel. Préserver l’intégrité des caches avec réouverture à chaud. Relever durée et couverture des régimes, avance, faux positifs/négatifs, GPU et frametimes p50/p95/p99, cadence native, attente PSO, recouvrement, CPU W, thermique et réveils. Des unités d’énergie par image exigent une mesure indépendante sur la même fenêtre et un dénominateur d’images natives.
