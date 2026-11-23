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

## Verrou à 30 images par seconde et GPU ralenti à cette cadence

Mécanisme. Quand le jeu demande l'intervalle 2 pendant une seconde, `nvn_game_fps` passe à 30 et le maintien du temps GPU lu par le jeu passe à 33,2 ms. Tout rapport TIMESTAMP de 16,6 à 33,2 ms lit alors 33,2 ms. Le jeu choisit l'intervalle de chaque image d'après ce temps : il ne peut plus lire un temps sous son budget de 16,67 ms.

Mesure. Les sondes GPU intégrées (`RewindBox GPU-only probe`, une image, sans suspension de thread) donnent le temps de chaque encodeur.

| Session | Image | Régime | Passes de rendu | Rendu | 1248×700 | 2048×2048 | 16×16 | 8×8 |
|---|---|---|---|---|---|---|---|---|
| IPA 820, Fair | 1322 | intervalle 1 | 127 | 9,86 ms | 4,01 ms (10 passes) | 0,58 ms (3) | 0,38 ms (3) | 0,31 ms (4) |
| IPA 820, Fair | 3842 | verrou à 30 | 133 | 24,47 ms | 8,75 ms (8) | 1,54 ms (3) | 1,06 ms (3) | 0,89 ms (4) |
| Après 821, Serious | 5642 | entrée dans le verrou | 124 | 24,56 ms | 10,41 ms (7) | 1,44 ms (3) | 0,86 ms (3) | 0,70 ms (4) |

Lecture. Les mêmes passes sont 2,2 à 2,9 fois plus lentes dans le verrou, y compris des passes de 8×8 pixels : c'est la fréquence du GPU qui baisse à cette cadence, pas la charge qui monte. Le temps lu par le jeu reste donc au-dessus de 16,67 ms et le verrou se maintient. Dans la session après la 821, il dure de l'image 5638 à la fin (3 793 images).

Patch 0309 (`rb_drs_trial_step`). Un essai rend au jeu le maintien de 16,6 ms pendant 30 images, quel que soit le temps réel. Le jeu repasse à l'intervalle 1 ; si le GPU suit à cette cadence, il y reste. Sinon ses propres lectures le renvoient à l'intervalle 2 et l'essai suivant attend deux fois plus (60 images, puis jusqu'à 960). Après 300 images à 60, l'essai est compté comme tenu et l'attente repart de 60. Seul un jeu qui alterne ses intervalles (8 changements en 1 200 images au plus) est essayé : un titre à 30 par choix n'en change que quelques fois. Pas d'essai sous un plafond utilisateur de 30, pendant une vidéo ni à l'état Critical. Journal : `[rb-guest-drs] trial frame= frames= waited= trials= kept=`.

Limites. Rien n'est mesuré sur iPhone. Si le système bride réellement le GPU, l'essai échoue : environ une seconde à l'intervalle 1 sans gain, puis retour au verrou. Chaque essai fait changer deux fois le mode du display link. Le gain attendu est la sortie du verrou quand seul le ralentissement de cadence le maintenait.

Répartition du temps GPU à l'intervalle 1 (image 1322). Les passes de scène à 1248×700 pèsent 4,0 ms sur 9,9 ms ; une centaine de passes plus petites se partagent le reste, une passe de 8×8 coûtant près de 80 microsecondes. Baisser la résolution de la scène agit donc sur 40 % du temps GPU au plus. Le coût fixe par passe est la piste suivante ; il n'est pas traité ici. L'élision des stores reste hors service pour les titres hébergés (lecteurs d'attachements par handles : durée de vie non prouvable), et ce verrou n'a pas de forçage.

Fil de soumission, audit. Il tourne à 100 % sur les cœurs performance, sous une politique temps réel de priorité 97. Le calcul déclaré n'explique pas son horloge : des sessions à 15 ms déclarés montrent 1,4 à 2,4 GHz dans les fenêtres lourdes, comme les sessions à 2 ms. L'horloge suit l'état du GPU (voir plus haut) : basse quand le GPU travaille à pleine fréquence, haute quand il est ralenti. Aucun réglage de QoS ou de placement ne ressort comme cause. Le groupe de travail (`S2A_WORKGROUP`), qui annonce une échéance par image au système, reste hors service parce qu'il fait refuser la mise en veille de la session ; aucune mesure de course n'existe avec lui actif depuis l'IPA 783. Essai proposé alors : `S2A_WORKGROUP=1` dans `Documents/env.txt`. Correction : jusqu'à l'IPA 823, le pont posait cette variable avant le chargement du moteur, et le moteur ne lit env.txt que pour compléter ; l'essai n'avait donc aucun effet. Il devient possible avec l'IPA 824 (voir « Session IPA 823 sur iPhone : course, fil de soumission et verrou »).

## Session IPA 822 sur iPhone : patchs 0302 à 0307 observés

Journal `549fdcf9`, Mario Kart World, 7 800 images, Fair au lancement, Serious de l'image 1000 environ à la fin.

| Point | Observé |
|---|---|
| Gouverneur mémoire (0303) | `tier=0`, `resident_MiB=232`, quotas non bridés |
| Index des pools (0304) | 4 083 modifications isolées appliquées, 13 tris complets |
| Pipelines des programmes annoncés (0302) | `front_moved=289 front_taken=289` ; 197 pipelines construits au dessin (5,27 s), dont 99 dans les 900 premières images (4,72 s) |
| Poussée arrêtée au plancher (0307), course hors verrou à Serious | 6 à 44 images sur 300 à l'intervalle 2 (106 à 124 avant), 41,4 à 52,1 images par seconde (27,6 à 43,8 avant) |
| Verrou à 30 images par seconde | fenêtres 3900 à 5100 et 7200 à 7800 : 26,4 à 27,8 images par seconde, GPU p50 33,1 à 34,6 ms, sonde GPU 0,80 à 1,37 ms |
| Sortie du verrou sans changement d'état thermique | fenêtre 5400 : 56,2 images par seconde, GPU p50 10,1 ms, sonde 0,19 ms, toujours à Serious |
| Fil de soumission, même charge (71 à 73 M d'instructions par image) | 9,4 ms à 2,94 GHz et 1,97 W dans la fenêtre 5400 ; 18,7 ms à 1,36 GHz et 0,82 W dans la fenêtre 5700 |

Lecture.

- Le verrou occupe 2 360 images sur 7 800 (fenêtres 3900 à 5100 et 7200 à 7800) alors que le même état thermique donne 56 images par seconde juste après : c'est le cas visé par le patch 0309.
- Hors verrou, la cadence suit l'horloge du fil de soumission. Elle retombe à 1,33–1,41 GHz en quelques secondes dès que le GPU travaille à pleine fréquence, ce qui borne la course à 41–49 images par seconde. Aucun réglage du moteur n'explique cette horloge.
- Le plancher du patch 0307 a été appris dans un menu : `floor frame=1022 scene_px=2073600 floor_px=2073600 rests=1 resumes=0`. La scène d'un menu ne rétrécit pas ; 1920×1080 a été pris pour la plus petite taille du jeu et plus aucune course n'a été poussée.

Patch 0310. Seule une poussée qui a fait rétrécir la scène apprend le plancher. Une poussée sans effet est retentée après une attente doublée (600 images, jusqu'à 4 800) ; l'attente repart de 600 quand la scène dépasse de plus d'un dixième la taille où la dernière poussée s'est arrêtée. Journal : `[rb-guest-drs] floor … wait=`.

Sonde GPU de cette session (demandée à l'image 2160, 81 ms d'image moyenne pendant un chargement) : non exploitée.

## Session IPA 823 sur iPhone : course, fil de soumission et verrou

Journal `f909c983`, Mario Kart World, moteur 0001–0310, 22 200 images, Fair de l'image 1 374 à 17 400, puis Serious. Fenêtres de 300 images.

| Fenêtres | État | Images par seconde | Soumission + présentation, p50 | GPU, p50 | Horloge du fil de soumission |
|---|---|---|---|---|---|
| 3 600–4 500 et 11 400–13 500 | Fair | 55,0 à 60,0 | — | — | 1,62 à 2,00 GHz |
| Course, 6 000–6 900 | Fair | 33,4 à 39,3 | 17,7 à 21,5 ms | 14,2 à 16,2 ms | 1,26 à 1,31 GHz |
| Courses, 7 200–11 100 et 14 400–17 100 | Fair | 23,8 à 50,0 | — | — | 1,26 à 1,52 GHz |
| Verrou à 30, 18 300–19 800 | Serious | 25,7 à 28,6 | 11,7 à 17,8 ms | 31,6 à 35,1 ms | 1,68 à 1,93 GHz |
| 20 100–21 300 | Serious | 38,1 à 50,7 | 15,7 à 20,9 ms | 11,4 à 15,4 ms | 1,27 à 1,38 GHz |

Lecture.

- En course, le fil de soumission est le premier verrou : soumission et présentation prennent 17,7 à 21,5 ms par image quand le GPU en prend 14,2 à 16,2, et le fil travaille 13,5 à 19,6 ms de CPU par image dans les fenêtres à 1,26–1,32 GHz. Son travail est celui de l'IPA 822 : au p50 des fenêtres de course, 45 500 instructions par dessin, 1 418 dessins et 66 M d'instructions par image (822 : 44 500, 1 492 et 65 M). Le coût par dessin est stable depuis le 14 novembre (41 000 à 56 000 au p50 selon les sessions). Ce qui change, c'est l'horloge que le système lui donne : 1,26 à 1,52 GHz dans les courses lentes, 1,6 à 2,0 GHz dans les fenêtres qui tiennent 55 à 60 images par seconde.
- Les compilations de fond du patch 0308 (20 à 90 toutes les 10 secondes) couvrent aussi bien les fenêtres à 60 que les fenêtres lentes : elles n'expliquent pas l'horloge. Le patch 0311 les retire.
- Verrou à 30 (patch 0309) : 7 essais, 2 tenus (images 18 208 et 21 708), attente doublée de 60 à 480 images entre deux échecs, comme prévu. Les fenêtres 18 300–19 800 restent au verrou parce que le GPU y est ralenti : de l'image 18 600 à 19 800, la sonde fixe prend 0,82 à 1,18 ms, contre 0,27 à 0,36 ms dans les fenêtres hors verrou.
- Plancher de résolution (patch 0310) : aucun appris (`floor_px=0`) ; les poussées sans effet ont été retentées avec une attente doublée, de 600 à 4 800 images.

Leviers restants, non intégrés faute de mesure sur iPhone.

- Le groupe de travail : `S2A_WORKGROUP=1` dans `Documents/env.txt`, possible à partir de l'IPA 824 (le pont applique désormais env.txt avant ses propres valeurs). Il annonce au système une échéance par image. Sur Silksong, il a porté les cœurs performance de 1,9 à 3,5 GHz, et la puissance de 1,69 à 2,47 W à 60 images par seconde dans les deux cas. Il ne prend pas d'intervalle à Serious (patch 0088) et se met au repos à Fair après 120 images à l'heure (patch 0093, profil Mario Kart World). Avec lui, Quitter ne met pas la session en veille : fermer l'app après l'essai. Un essai à la fois, à comparer sur `mean clock`, la puissance CPU et les images par seconde des fenêtres de course.
- Le coût par dessin : pour 60 images par seconde à 1,26 GHz, le fil de soumission devrait passer sous 21 M de cycles par image (17 à 26 M dans ces courses), et le GPU rester sous 16,7 ms (14 à 16 ms). Un profil CPU de course dit où partent les instructions : une capture d'écran pendant une course suffit (patch 0045) ; 10 secondes après, 6 secondes de profil sont écrites dans `Documents/Diagnostics/S2Arm/captures/<capture>/cpuprof.txt`.

## Sessions IPA 825 sur iPhone : verrou à 30 et récupération GPU

Journaux `de0a5911` (première session, 7 300 images, enregistrement d'écran à partir de l'image 6 543) et `b7d5aa42` (relance, 11 100 images), Mario Kart World, moteur 0001–0318, Fair pendant les courses. Comparés à la session 824 (`c758810c`). Fenêtres de course de 300 images ; « au verrou » : 98 images ou plus à l'intervalle 2.

| Session | Fenêtres surtout à l'intervalle 1 | Fenêtres au verrou | GPU p50 des images longues, période 16,7 / 33,3 ms |
|---|---|---|---|
| 824 | 39 à 58 images par seconde | 27 à 40 (15 dans la fenêtre du blocage GPU) | 14,3 / 30,4 ms |
| 825, première | 27 à 42 | 22 à 27 (14 pendant l'enregistrement et le blocage GPU) | 13,7 / 25,1 ms |
| 825, relance | 39 à 60, dont 52 à 60 après l'image 3 900 | 27 à 41 | 13,0 / 34,0 ms |

Lecture.

- Dans la relance, les fenêtres lentes sont celles où le jeu reste à l'intervalle 2 (111 à 266 images sur 300). Le GPU y est occupé 820 à 935 ms par seconde.
- À la période de 33,3 ms, le temps GPU par image est 2 à 2,6 fois plus long dans les trois sessions, 824 comprise. Les mêmes passes de 32×32 à un dessin prennent 0,25 ms à l'image 3 242 et 0,58 ms à l'image 5 642 de la relance. C'est le mécanisme décrit plus haut (GPU ralenti à cette cadence), pas une régression des patchs 0312–0318.
- La première session est lente aussi hors verrou : 27 à 42 images par seconde quand le jeu reste surtout à l'intervalle 1, contre 52 à 60 dans la relance après l'image 3 900. Ses images longues sont des attentes du jeu (`guest_sync`, attente p50 51 ms, 14 ms dans la relance) : le fil principal attend ses fils de travail (`rb-mkw-wait-path`, réveil par les fils 179 à 183).
- Ces attentes suivent la relecture de la mémoire invité depuis ses fichiers de secours (`[写盘]`, par 10 secondes) :
  - première session, toute la course jusqu'à l'image 6 400 : 133 à 688 Mo ;
  - relance : 490 à 885 Mo jusqu'à l'image 4 000, à 39–42 images par seconde, puis 0 à 414 Mo, à 52–60 hors verrou ;
  - 824 : 361 à 813 Mo de l'image 3 400 à 4 900 (42 à 54 images par seconde), puis 89 à 203 Mo jusqu'à l'image 8 800.
  Une relance repart d'une mémoire libre, ce qui peut expliquer qu'elle soit plus rapide. La corrélation ne prouve pas la cause : à mesurer en isolant la pagination.
- Essais de sortie (patch 0309) : un tenu au quatrième essai de la relance, deux au sixième de la première session.
- Le groupe de travail est resté éteint dans les deux sessions (`帧间隔工作组：关（S2A_WORKGROUP=0）`) : il n'a toujours pas été mesuré en course.
- Barrières : 22 400 à 30 600 barrières complètes à l'entrée des passes de dessin par fenêtre de 300 images après le chargement, soit 75 à 100 par image (profil sans `game.tsv`, `draw_barriers` à `full`).
- Pendant l'enregistrement d'écran (images 6 544 à 6 566), les images durent 55 à 108 ms.
- Patch 0316 : les fins de segment survenues pendant qu'un fil du jeu dort passent de 11 402 (824, 9 000 images) à 205 et 622. Il y a moins de segments soumis quand le GPU est occupé. Les attentes de clôture du jeu ne se libèrent qu'à la fin de la soumission entière, avec ou sans 0316 : aucun lien avec la baisse n'est établi.
- Préchauffage : il plafonne à 1 925 pipelines préparés dès l'image 2 100 (première session) et n'avance plus pendant les courses.

Récupération GPU de la première session : l'image 6 568 dure 10,09 s, puis 5 tampons de commandes sont rendus en erreur « Discarded (victim of GPU error/recovery) » (`kIOGPUCommandBufferCallbackErrorInnocentVictim`). Voir [Clippings noirs fugaces](s2arm-mkw-black-flicker.md#ipa-825--flash-noir-et-récupération-gpu).

Essais possibles sans nouvelle IPA (`Documents/env.txt`, une ligne `CLÉ=VALEUR`, un essai à la fois, à comparer sur les fenêtres de course) :

- `S2A_WORKGROUP=1` : annonce une échéance par image au système. Avec lui, quitter ne met pas la session en veille : fermer l'app après l'essai.
- `DM_NVN_BARRIER=game` : les passes de dessin sont ordonnées par les barrières du jeu, le travail des sommets d'une passe peut chevaucher les fragments de la précédente. Risque : un défaut d'image si le jeu lit au stade des sommets un résultat de la passe précédente sans barrière.
