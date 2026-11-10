# BO2 : corrélation des journaux de la version 593

Analyse issue exclusivement des extractions existantes. Le candidat source `7d1ca65` n’est pas testé par ces journaux. Aucune mesure FPS avant/après n’est disponible.

## Créations graphiques longues

Les 32 opérations inline distinctes totalisent **19,926181 s**, soit **98,957 %** des 20,136100 s de création graphique de la session 2, fenêtres 14–22. Les 140 autres créations totalisent environ 209,919 ms. Aucun chevauchement entre ces 32 opérations ni événement perdu n’est signalé.

| Origine | Nombre | Temps écoulé, ms | VS, ms | FS, ms | Feedback |
|---|---:|---:|---:|---:|---|
| 5 | 2 | 804,355 | 586,230 | 0,028 | [55] |
| 6 | 26 | 15 581,817 | 0,500 | 14 179,115 | [31] |
| 7 | 4 | 3 540,009 | 1 107,175 | 1 571,698 | [23] |

L’origine 5 désigne un nouveau programme VS et un ancien FS ; 6, un ancien VS et un nouveau FS ; 7, deux nouveaux programmes. Le bit 4 indique une création inline. Le feedback 55 indique un échec de cache VS et un succès FS ; 31, un succès VS et un échec FS ; 23, deux échecs de cache. `pipeline_flags=5` correspond à l’énumération interne `INLINE|SEPARATE_SHADER_OBJECTS`, pas à `VkPipelineCreateFlags`.

Les 32 paires VP/FP sont distinctes : 32 modules FP, 26 modules VP et 7 empreintes d’état. Les réutilisations de VP enregistrées gardent un succès de cache VS de quelques dizaines de microsecondes. Cette sélection ne démontre aucune recompilation du même module FP. Dans les fenêtres 19–20, **111 nouveaux programmes FP coexistent avec seulement 8 compilations de bibliothèque FS et 115 succès de cache FS**. Les compteurs sont relevés séparément ; ils ne permettent pas d’affirmer que précisément 103 des 111 nouveaux programmes correspondent à ces succès.

Le thread appelant ne consomme que 217,060 ms de CPU pendant les 19,926181 s d’appels. Les 93,325981 s de CPU du processus incluent les threads invités concurrents, notamment les SPU ; ils ne représentent pas le CPU du compilateur. Les 172 publications ne coûtent que 1,357 ms à l’appelant. Les écritures et les fsync sont différés ; leurs durées sont imbriquées et ne doivent pas être additionnées.

## Frontières temporelles

Le premier appel long commence à 05:02:45.636921 UTC et finit à 05:02:46.603154. Il traverse le rapport FRAME de la fenêtre 13 à 05:02:46.151750 et est rapporté dans la fenêtre 14. Il faut donc conserver la fenêtre 13 hors du groupe entièrement sans compilation graphique longue.

La fenêtre 16 rapporte un appel de 468,183 ms mais un maximum d’intervalle de frame terminé de 62,145 ms. Les histogrammes ne fournissent pas les débuts et fins de chaque frame ; la fenêtre d’un compteur ne suffit pas à attribuer chaque opération à une frame individuelle.

Dans la fenêtre 21, six appels occupent **3 654,210 ms** d’une séquence de 3 696,655 ms. Le maximum de frame est de **3 783,054 ms**. Cette concordance relie la rafale au fort ralentissement de cette période, sans fournir une affectation exacte de chaque appel à une frame.

## Admission LLVM et phase de lecture des objets SPU

Les deux fenêtres ci-dessous montrent une activité d’admission importante pendant les lectures d’objets déjà en cache. Les durées sont des totaux de travaux susceptibles de s’exécuter en parallèle.

| Session, fenêtre | Attente de budget : appels / total / maximum, ms | Attente de mutex : appels / total / maximum, ms | Lectures d’objets : appels / total, ms | Codegen : appels / total, ms | Maximum de frame, ms | Références |
|---|---|---|---|---|---:|---|
| 1, 4 | 2 884 / 1 438,284 / 7,469 | 8 620 / 1,379 / 0,125 | 8 611 / 3 927,492 | 30 / 228,315 | 1 218,521 | RPCS3-performance.1.log : FRAME 3584, WAIT 3594, JIT 3610 |
| 2, 6 | 1 806 / 927,306 / 6,619 | 6 090 / 0,979 / 0,047 | 6 125 / 2 747,703 | 13 / 125,510 | 24,783 | RPCS3-performance(4).log : FRAME 169, WAIT 179, JIT 195 |

La session 1, fenêtre 4, contient neuf frames de plus de 100 ms. La session 2, fenêtre 6, n’en contient aucune malgré 927,306 ms d’attente cumulée de budget. La grande frame suivante peut terminer dans une autre fenêtre. Ces compteurs justifient l’examen du protocole d’admission, mais ils ne prouvent pas à eux seuls une notification perdue, ni combien de millisecondes d’une frame précise elle expliquerait. Les maxima de budget de ces deux fenêtres restent inférieurs au timeout nominal de 20 ms. Une reproduction déterministe du protocole de verrouillage doit établir le défaut séparément.

Le champ `spu_build` inclut les lectures d’objets et d’autres étapes : il ne faut pas additionner son total au temps de lecture. Les nombres de chargements, de tentatives et de lectures peuvent aussi différer légèrement à cause des relevés indépendants.

## Coût restant hors grosses rafales froides

Les fenêtres 9, 11 et 12 de la session 2 donnent **587 frames / 15,759493 s = 37,247391 FPS**, avec 14 frames de plus de 50 ms et aucune de plus de 100 ms ; maximum : 99,006 ms. Elles ne contiennent aucun codegen SPU et un seul succès de cache graphique de 1,860 ms. Il reste 176 lectures d’objets SPU pour 363,933 ms cumulées : on ne peut ni les soustraire des frames individuelles, ni attribuer les 14 pointes au GPU seul.

| Fenêtre | FPS sur temps écoulé | Maximum, ms | Submit : appels / total / maximum, ms | Texture échantillonnée, ms | Mémoire / headroom, MiB | Lignes dans performance(4).log |
|---|---:|---:|---|---:|---|---|
| 9 | 41,077 | 66,576 | 1 328 / 765,680 / 13,406 | 4,569 | 3661 / 2994 | FRAME 259, SYNC 271, RSX 272, MEM 281, JIT 285, CPU 288 |
| 11 | 36,901 | 51,936 | 1 203 / 854,988 / 7,613 | 5,717 | 3791 / 2864 | FRAME 319, SYNC 331, RSX 332, MEM 341, JIT 345, CPU 348 |
| 12 | 33,721 | 99,006 | 1 059 / 781,752 / 7,827 | 5,532 | 3869 / 2786 | FRAME 349, SYNC 361, RSX 362, MEM 371, JIT 375, CPU 378 |

Sur ces fenêtres, les 3 590 soumissions coûtent 2 402,420 ms cumulées, soit 6,168 soumissions par frame RSX et 4,093 ms par frame présentée. Les attentes explicites de fence, de hard-sync et les readbacks sont nuls. L’acquisition culmine à 0,624 ms et la présentation à 1,169 ms. Les temps texture, vertex, setup et flip sont des moyennes de temps écoulé sur **72 frames échantillonnées parmi 582 frames RSX**, avec des frontières distinctes des **587 frames COREPROF**.

La mémoire comprimée passe de 743,297 MiB dans la fenêtre 9 à 1 081,281 MiB dans la fenêtre 12 ; le résident passe de 3 248,016 à 2 986,344 MiB. Le footprint rapporté monte de 3 661 à 3 869 MiB et le headroom baisse de 2 994 à 2 786 MiB. Les compteurs de pression et de réclamation restent nuls. Cette évolution ne démontre ni OOM ni durée perdue dans la compression. `gpu_time_ms=-1` ne fournit pas de mesure de saturation du GPU.

`frame_latency` mesure le temps entre la soumission du swap et le constat de fin dans `frame_context_cleanup`. Il inclut une observation CPU retardée, notamment par une compilation. Ce compteur n’est pas une durée GPU indépendante à ajouter aux autres coûts.

## Événements longs : preuves

| Fenêtre | Ligne | Début UTC | Fin UTC | Durée, ms | Origine | Propriétés | VP | FP |
|---|---:|---|---|---:|---:|---|---|---|
| 14 | 414 | 05:02:45.636921 | 05:02:46.603154 | 966,233 | 6 | ae4c3e4c0367d2d2 | 786cc731e0 | 7977117020 |
| 14 | 415 | 05:02:46.606887 | 05:02:46.825763 | 218,876 | 6 | ae4c3e4c0367d2d2 | 78be66b800 | 7977117560 |
| 14 | 416 | 05:02:46.890017 | 05:02:47.796449 | 906,432 | 7 | ae4c3e4c0367d2d2 | 797722c8c0 | 797722d260 |
| 14 | 417 | 05:02:47.935143 | 05:02:48.545747 | 610,604 | 6 | 51ccb581f8bd1e57 | 786cc73640 | 797722ea00 |
| 15 | 448 | 05:02:53.078777 | 05:02:53.851749 | 772,972 | 6 | f93924e189b4a7e1 | 78ef462ca0 | 7980443480 |
| 15 | 449 | 05:02:55.018164 | 05:02:55.875401 | 857,237 | 6 | f93924e189b4a7e1 | 78be668fc0 | 798058c7e0 |
| 16 | 480 | 05:03:01.339869 | 05:03:01.808052 | 468,183 | 5 | c8c182bdbd31e2fb | 79806a0a80 | 78bac66ae0 |
| 17 | 511 | 05:03:02.031792 | 05:03:02.607321 | 575,529 | 6 | ae4c3e4c0367d2d2 | 78bae45ce0 | 79806a32c0 |
| 17 | 512 | 05:03:02.616606 | 05:03:03.400970 | 784,364 | 6 | f93924e189b4a7e1 | 78bae45ce0 | 79806a3560 |
| 17 | 513 | 05:03:03.408021 | 05:03:03.905517 | 497,496 | 6 | 3fd9f9f9c6ac4ca4 | 78bae45ce0 | 79806a3640 |
| 17 | 514 | 05:03:04.045888 | 05:03:04.520107 | 474,219 | 6 | f93924e189b4a7e1 | 7903c23b80 | 79806a3d40 |
| 17 | 515 | 05:03:04.624030 | 05:03:05.033560 | 409,530 | 6 | ae4c3e4c0367d2d2 | 78ef462300 | 7980748b60 |
| 18 | 546 | 05:03:09.415266 | 05:03:10.038915 | 623,649 | 6 | ae4c3e4c0367d2d2 | 78ef463f00 | 79899b1880 |
| 18 | 547 | 05:03:10.507047 | 05:03:11.247873 | 740,826 | 6 | f93924e189b4a7e1 | 786cc73020 | 79899f0c40 |
| 19 | 578 | 05:03:12.337361 | 05:03:13.009689 | 672,328 | 6 | ae4c3e4c0367d2d2 | 78bac67d40 | 79899f39c0 |
| 19 | 579 | 05:03:13.427629 | 05:03:13.969323 | 541,694 | 6 | ae4c3e4c0367d2d2 | 786cc73560 | 7989a6f480 |
| 19 | 580 | 05:03:13.977402 | 05:03:14.436531 | 459,129 | 6 | ae4c3e4c0367d2d2 | 786cc73560 | 7989a6f640 |
| 19 | 581 | 05:03:15.308297 | 05:03:15.815134 | 506,837 | 6 | ae4c3e4c0367d2d2 | 78ef462300 | 798e1a9180 |
| 19 | 582 | 05:03:16.028315 | 05:03:16.422216 | 393,901 | 6 | c8c182bdbd31e2fb | 786cc72a00 | 798e278e00 |
| 19 | 583 | 05:03:16.647998 | 05:03:17.733742 | 1 085,744 | 7 | ae4c3e4c0367d2d2 | 798e27baa0 | 798e27bb80 |
| 20 | 614 | 05:03:18.390840 | 05:03:19.103272 | 712,432 | 7 | ae4c3e4c0367d2d2 | 798e3b3640 | 798e3b3560 |
| 20 | 615 | 05:03:19.182422 | 05:03:19.518594 | 336,172 | 5 | 9f23dbe889b4a7e1 | 798e3b3b80 | 7989b7b100 |
| 20 | 616 | 05:03:21.440313 | 05:03:22.128452 | 688,139 | 6 | ae4c3e4c0367d2d2 | 78ef461180 | 7992cb6300 |
| 21 | 647 | 05:03:23.772291 | 05:03:24.342209 | 569,918 | 6 | ae4c3e4c0367d2d2 | 790d022bc0 | 7992feb720 |
| 21 | 648 | 05:03:24.354226 | 05:03:25.060024 | 705,798 | 6 | ae4c3e4c0367d2d2 | 78ef463f00 | 7992feb020 |
| 21 | 649 | 05:03:25.067891 | 05:03:25.656079 | 588,188 | 6 | ae4c3e4c0367d2d2 | 7903c23100 | 7992fe9f80 |
| 21 | 650 | 05:03:25.668389 | 05:03:26.503790 | 835,401 | 7 | c8c182bdbd31e2fb | 7992fe9ea0 | 7992feaf40 |
| 21 | 651 | 05:03:26.507836 | 05:03:26.925735 | 417,899 | 6 | ae4c3e4c0367d2d2 | 78ef461420 | 7992feb8e0 |
| 21 | 652 | 05:03:26.931940 | 05:03:27.468946 | 537,006 | 6 | f93924e189b4a7e1 | 786cc73020 | 7992feb800 |
| 22 | 683 | 05:03:29.181608 | 05:03:29.807141 | 625,533 | 6 | ae4c3e4c0367d2d2 | 790d022ca0 | 7998a5dc00 |
| 22 | 684 | 05:03:29.833529 | 05:03:30.405256 | 571,727 | 6 | ae4c3e4c0367d2d2 | 786cc70540 | 7998a5e140 |
| 22 | 685 | 05:03:30.453248 | 05:03:31.225433 | 772,185 | 6 | ae33c3940367d2d2 | 78bae47640 | 7998a5e760 |

Toutes ces lignes viennent de `RPCS3-performance(4).log`, session 2. Le JSON contient les références UTC, fichier et ligne de chaque compteur, les sources d’entrée et leurs SHA256, les 29 fenêtres BO2 et les détails des 32 opérations. Les événements du journal rotatif sont joints par build, PID, session et fenêtre ; les répétitions des diagnostics et des milestones ne sont pas sommées.

## Pistes concrètes et réfutations

La première piste est de réduire le travail de source ou d’IR dont l’inutilité est démontrée sur le chemin fragment, en conservant les clés sémantiques, puis de vérifier le SPIR-V et le MSL produits. L’admission LLVM et les lectures d’objets concernent la phase SPU. Les chemins textures et soumissions restent les principaux coûts RSX récurrents mesurés, à optimiser en conservant l’invalidation des écritures CPU et l’ordre des commandes. Aucun gain de FPS n’est prouvé par cette analyse.

Les journaux ne justifient pas une suppression du cache, un assouplissement de ses clés, une désactivation de validation, une activation globale du mode async ou un retour du SPU différé. Le prehash est désactivé ; les attentes GPU, les readbacks et les contentions VM n’expliquent pas les saccades observées ici. Le cache de bibliothèques fonctionne déjà au démarrage : les 393 puis 1 061 pipelines ont des succès de cache pour les deux stages. Le contraste entre 111 nouveaux programmes FP et seulement 8 bibliothèques FS compilées dans les fenêtres 19–20 confirme aussi une réutilisation importante, sans autoriser une correspondance individuelle entre ces deux compteurs.
