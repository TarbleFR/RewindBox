# Cadence de course sur iPhone 16 Pro Max

Mario Kart World, programme `0400C3F00006E000`. Le relevé communiqué pour le moteur 0247 couvre 31 517 trames avec 15,34 ms au p50 GPU, 18,50 ms au p95 GPU et 9,81 ms au p50 soumission + présentation. Les compteurs agrégés ne donnent pas le motif de rejet de chacun des 1 500 couples de clears. La validation après modification doit porter sur les intervalles de deux images réellement affichées, les temps GPU et les évictions en course.

## Passes et événements

Dans `nvn_mtl.m`, la simple présence de `DM_NVN_TBDR` neutralisait les règles prudentes de store adjacent ou en fin de liste. Une valeur explicite de `0` désactivait simultanément l’autre chemin. Les drapeaux de 0241 pouvaient donc être actifs sans atteindre ces décisions. Le prédicat du clear couleur exigeait aussi une cible unique. Le plan de fusion refusait deux groupes pourtant compatibles si l'un gardait d'autres cibles attachées sans les effacer. Les 1 500 couples comptés avaient déjà atteint la même matérialisation. Une coupure au 64e draw peut empêcher la formation d’un autre couple. L’ancien compteur de barrière exigeait à la fois un tas de placement actif et un producteur complet dans le même command buffer. Les nouveaux contrôles distinguent la coupure réelle, l’absence de clear suivant prouvable, la cible exposée, le backing ou le format incompatible. Une coupure réelle de command buffer, un transfert, une vue ou un alias incertains restent des frontières pour ces preuves.

Dans `nvn_xqueue.inc`, la lecture d’un événement tient déjà compte des signaux SET et ADD encodés avant son WAIT. Lorsqu’une autre file doit encore relever une valeur remise à zéro par le CPU, le consommateur se parque pour laisser le producteur soumettre ses commandes. Les 305,8 s incluent le rejeu des commandes utiles des pièces supplémentaires. Le nouveau chemin construit l’index des signaux du suffixe au premier besoin de détection de cycle et relit sous verrou la valeur et le type d’écrivain. Si une attente de premier niveau est déjà satisfaite à la relecture, sa continuation peut rester dans le même command buffer. Un rapport CPU, une fence, une attente GPU, une lecture de compteur indirect ou un CALL imbriqué conservent la coupure. `park_to_resume_wall_ms` mesure un délai de dépendance qui peut inclure le travail utile de l'autre file.

## Affichage et adaptation thermique

Le filtre 0238–0247 stabilisait la fréquence de la dalle et les appels Mach. Le callback CAMetalDisplayLink utilisait encore la période brute de la dernière image soumise pour fixer sa retenue. Le moteur mémorise maintenant un intervalle d’affichage distinct par image. Après une demande à 60 Hz, les sept premières demandes consécutives à 30 Hz restent affichables au prochain tick et la huitième rétablit la retenue de 33,3 ms. Un titre qui commence directement à 30 Hz garde sa cadence dès la première image. Les plafonds utilisateur, vidéos et modes à pas de jeu explicites conservent leur période. Le thread d’acquisition et l’horloge du jeu utilisent toujours la demande de l’invité. Une image prête est nécessaire pour récupérer un tick.

Le contrôleur DRS utilise en Fair des fenêtres disjointes de 32 images et demande au moins 24 mesures de travail GPU terminées. Il relève le plancher du TIMESTAMP invité après deux fenêtres au-dessus de la cible p50 ou de 15,5 ms au p95. À 60 Hz, les trois planchers sont 18,675 ms, 20,5 ms et 22,0 ms. Huit fenêtres sous la cible p50 moins 1 ms et sous 14,5 ms au p95 autorisent un recul d’un palier. Les timestamps de début gardent leur valeur et un intervalle réel supérieur au plancher garde sa durée. Le jeu décide de sa résolution jusqu’à son minimum interne.

## QoS des threads invités

0240 prélevait les compteurs à la publication thermique, avant l’application par chaque pthread. Un secondaire pouvait aussi entrer en attente à Nominal, en ressortir en Fair et reprendre son travail avec l’ancienne QoS jusqu’au prochain SVC. Une file série échantillonne maintenant la température. Les threads secondaires éligibles appliquent la demande à la sortie de l’attente ou en repassant par les chemins d’exécution et d’horloge. Le premier succès confirmé publie une ligne `phase=applied`. Le thread principal, nx-83 et les threads chargés de l’encodage, de la soumission ou de la présentation conservent leurs priorités. La QoS demandée et relue ne mesure pas le placement sur P-core ni les watts.

## Comparaison sur iPhone

Dans `env.txt`, changer un réglage à la fois puis relancer le processus. Les drapeaux booléens ci-dessous utilisent `0` pour le témoin et `1` pour l’essai. Les compteurs de différentes sessions ne s’additionnent pas.

| Réglage | Activé dans cet essai | Mesures du host.log |
| --- | --- | --- |
| `S2A_RB_NVN2_MRT_CLEARS` | `1` dans la politique NVN2 de suivi des attachements | `sealed_stores`, `private_clear_entry_saved`, `projected_clear_pairs`, `segment_cut`, `no_adjacent_landing`, rejets par motif et encodeurs évités |
| `S2A_RB_XQ_RESUME` | `1` sur NVN2 | `suffix_scans_avoided`, `late_ready_checks`, `pieces_avoided`, `extra_replay_ms`, `extra_commit_ms`, `tracked_cpu_wait_ms`, `park_to_resume_wall_ms` |
| `S2A_RB_PRESENT_INTERVAL_DEBOUNCE` | `1` sur le chemin NVN2 Metal 4 hébergé | `[rb-present-hold]` avec `filtered_frames` et `sustained_runs`, ticks réellement retenus, images fusionnées, p95/p99 des intervalles affichés |
| `S2A_RB_DRS_TARGET_MS` | `13.5` par défaut, `0` pour le palier fixe, cible acceptée de 10 à 15,5 ms | `[rb-guest-drs]` avec `level`, `gpu_p50_ms`, `gpu_p95_ms`, `windows`, `incomplete`, `up_steps`, `down_steps`, ainsi que les tailles des cibles du jeu |
| `S2A_RB_GUEST_QOS_TRANSITIONS` | `1` pour les secondaires du profil thermique actif | `[RB-GUEST-QOS]` avec `phase=applied`, `reduced_requests`, `restore_requests`. Avec `S2A_RB_GUEST_QOS_STATS=1`, contrôler `down_verified`, `down_failed` et `restore_verified` |

Comparer Airship Fortress et Moo Moo Farm avec un premier passage à caches équivalents, puis après relance avec les mêmes caches chauds. Suivre séparément Nominal et Fair. Les critères de course sont 16,67 ms entre images affichées à 60 Hz, p50 soumission + présentation sous 5–6 ms, p50 GPU au plus 13,5 ms et p95 GPU au plus 15,8 ms. Relever le maximum de trame, les compilations ou dépendances bloquant la soumission, les évictions PSO et le budget Mach effectif aux deux périodes. Une diminution de charge se vérifie en conservant la même scène et en notant aussi la résolution de rendu.
