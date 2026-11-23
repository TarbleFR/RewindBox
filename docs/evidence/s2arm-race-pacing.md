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

## Vérification Apple

Les [frameworks iOS arm64 et le contrôle de réouverture des archives Metal](https://github.com/TarbleFR/RewindBox/actions/runs/44889895037) et le [pont UIKit](https://github.com/TarbleFR/RewindBox/actions/runs/44889895029) correspondent au même commit source. Le [banc des 267 patchs](https://github.com/TarbleFR/RewindBox/actions/runs/44888750599/job/136799701221) a vérifié les pixels MRT, les copies GPU, la QoS des pthreads et les 89 contrôles de la suite shaders. La série de patchs est identique octet par octet entre ces deux runs. Le [reçu du moteur](s2arm-fluidity-803/engine267-build.json) associe chaque contrôle à son résultat et identifie les contrôles de file directe indisponibles sur le GPU du banc. Le pin authentifie les 267 patchs et les archives effectivement intégrées. Les temps de trame de course sur A18 Pro restent à mesurer.

## Planchers de TIMESTAMP et cadence 30 demandée par le jeu

Deux sessions Mario Kart World sur iPhone 16 Pro Max : IPA 820 (Nominal, puis Fair à l'image 2501) et une session reçue après la 821 (Fair dès le lancement, puis Serious).

Présentation. Aucune attente parasite : sur 215 et 295 lignes `[longframe]`, aucune n'est dominée par l'attente du display link avec un GPU sous 10 ms. Les images de 33 ms suivent un intervalle 2 écrit par le jeu (1 993 et 3 629 changements d'intervalle dans les deux sessions). L'attente du display link pèse 4,1 % et 2,0 % du temps des images longues ; soumission et présentation 80 % et 84 %.

Part des images de course à l'intervalle 2, selon le plancher que le moteur donne au temps GPU lu par le jeu (IPA 820, images 1200 et suivantes ; p50 GPU réel à l'entrée du segment) :

| État | Plancher | Images | Part à l'intervalle 2 | p50 GPU réel |
|---|---|---|---|---|
| Nominal | 16,6 ms | 1200–2501 | 3,2 % | — |
| Fair, palier 0 | 18,68 ms | 5614–9933 | 32,1 % | 11,4 ms |
| Fair, palier 1 | 20,5 ms | 2915–3249, 4221–4577, 4956–5614 | 30,5 %, 36,0 %, 62,0 % | 11,3 à 29,7 ms |
| Fair, palier 2 | 22,0 ms | 3249–4221 | 51,1 % | 13,8 ms |

Session après la 821 : palier 2 (22,0 ms) de l'image 1200 à la fin, 58,6 % à l'intervalle 2, puis intervalle 2 continu à partir de l'image 5638.

Lecture. Le patch 0087 relève le temps lu au-delà de la bande où le jeu garde sa taille (environ 15 à 17 ms à 60 images par seconde) pour qu'il baisse sa résolution. Un temps au-dessus du budget de 16,67 ms est aussi une image manquée : le jeu demande alors l'intervalle 2. Les scènes diffèrent d'un segment à l'autre ; le lien est une corrélation, pas un essai apparié.

Patch 0305, `rb_drs_report_ticks`.

- À Fair, sans pression GPU mesurée (palier 0), le plancher reste le maintien de 16,6 ms : la chaleur seule ne déclare plus d'image manquée.
- Un palier relevé par le temps GPU mesuré (`rb_drs_observe_gpu`) sort de la bande par le plus petit pas : 18,675 ms au palier 1, 20,5 ms au palier 2. Le pas de 22,0 ms disparaît.
- À partir de Serious, le système a ralenti le GPU lui-même : chaque palier pousse la taille vers le bas, comme le patch 0087.
- `S2A_RB_DRS_THERMAL_STATE` et `S2A_RB_DRS_THERMAL` gardent leur rôle.

Ce qui reste hors de ce patch.

- Une fois l'intervalle 2 tenu une seconde, le maintien passe à 33,2 ms : le jeu ne peut plus constater que le GPU est redevenu rapide. Le temps GPU mesuré s'étire aussi avec l'intervalle (30 à 36 ms à l'intervalle 2, sonde GPU fixe de 0,19–0,31 ms à 0,64–1,23 ms), ce qui ressemble à une baisse de fréquence et non à une charge.
- En course à l'intervalle 1, le thread de soumission consomme 12,8 à 22,5 ms de CPU par image à 1,3–1,7 GHz : c'est lui qui borne la cadence.
- `S2A_WORKGROUP` reste à 0 : le groupe de travail fait refuser la mise en veille de la session, et la seule mesure disponible (un autre jeu) donne 2,47 W contre 1,69 W.
- Profil de cadence : il ne change que l'instant de présentation, pas le coût, et un mode `display` forcé risque d'accélérer la simulation. Aucun n'est ajouté.

Vérification. `t_rb_adaptive_drs.c` couvre les trois cas (maintien à Fair, pas de 18,675 et 20,5 ms, poussée à Serious, plafond de cadence de l'utilisateur) et passe sur l'hôte. À observer sur iPhone, à Fair : la part d'images à l'intervalle 2 dans `the game sets present interval`, les lignes `dynamic resolution hold … raised to`, la taille des cibles du jeu, et le délai avant Serious, qui peut se raccourcir puisque le jeu garde plus souvent 60 images par seconde.

## Poussée de résolution maintenue au plancher du jeu

Depuis le patch 0087, à l'état thermique Serious, chaque rapport TIMESTAMP de fin d'image lit au moins 18,68 ms (20,5 ms au niveau 2). Le jeu baisse alors sa taille de rendu et demande l'intervalle de présentation 2 pour l'image suivante.

Session Mario Kart World après la 821 (moteur 0001–0301), état Serious, fenêtres de 300 images de 3900 à 5700 :

| Mesure | Valeur |
|---|---|
| Taille de scène | 1248×700 sur les 300 images des fenêtres 3900, 4200 et 5400 |
| Images demandées à l'intervalle 2 | 106 à 124 sur 300 (166 à la fenêtre 5700) |
| Images affichées par seconde | 27,6 à 43,8 |
| GPU p50 | 12,3 à 16,9 ms |
| Soumission p50 | 12,0 à 23,6 ms |
| Travail par image p50 | 20,8 à 27,9 ms |

À 1248×700 le jeu est à sa plus petite taille : la poussée ne réduit plus rien et ne produit que des images sautées.

Patch 0307. Une poussée cesse après 24 images poussées sans scène plus petite. Elle reprend au plus tôt 600 images plus tard, et seulement si la scène dépasse de plus d'un dixième la plus petite taille où une poussée s'est arrêtée. La taille de scène est la plus grande cible couleur dessinée avec une profondeur, déjà relevée par les signatures d'images ; inconnue, l'image est poussée comme avant. L'état Critical garde chaque poussée. Journal : `[rb-guest-drs] floor frame= scene_px= floor_px= rests= resumes=`.

Limites. Rien n'est mesuré sur iPhone. Dans ces fenêtres le travail par image dépasse 16,67 ms : le fil de soumission reste la limite, le gain attendu est la fin des intervalles 2 imposés, pas 60 images par seconde. Plus d'images par seconde à Serious dégagent plus de chaleur. La phase où le système ralentit le GPU (images 6000 et suivantes : GPU p50 32 à 34 ms, y compris dans les fenêtres entièrement à 1248×700 ; 26 à 28 images par seconde) n'est pas changée.

Constat sans cause établie. Dans les fenêtres 3900 à 5700, l'horloge moyenne du fil de soumission est de 1,34 à 2,02 GHz pour 12,7 à 22,5 ms de CPU par image, et la sonde GPU fixe lit 0,20 à 0,31 ms. Dans les fenêtres 6000 et suivantes, la sonde lit 0,64 à 1,23 ms et l'horloge monte de 2,19 à 3,58 GHz pour 8,8 à 10,5 ms de CPU. Le calcul temps réel déclaré n'explique pas l'horloge basse : des sessions antérieures à 15 ms déclarés montrent 1,4 à 2,4 GHz dans les fenêtres lourdes.

