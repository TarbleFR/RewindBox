# RPCS3 CELL521 — diagnostic et candidat privé

Branche `Claude`. Base application `a4b2f27775b4038b7bd143d6cf723a6fc56f5a13` (Build 520 préservé). Cœur modifié `93f82e6f98d9fbdf59e848e357bf85f7487af93f`, compilation native Actions [40093526893](https://github.com/TarbleFR/RewindBox/actions/runs/40093526893). Ce document distingue les mesures fournies, les essais natifs et les vérifications sur appareil encore nécessaires.

## Sources et périmètre

Le cœur reste XITRIX/rpcs3 `22f1152783cef1f7e04af7b1c895173e28fd5b03` avec le delta canonique RewindBox, ABI 30, clients NeoSwap et archive ABI 1. Les apports v0.12 et leurs limites de provenance sont conservés dans [le rapport précédent](rpcs3-xitrix-v012.md). LLVM 22.1.8 conserve son correctif AArch64 GHC, FFmpeg 8.1.1 et MoltenVK 1.4.2 restent les dépendances sélectionnées. Pas de remplacement par un moteur extrait d'une IPA externe.

Quatre postimages du cœur changent : `cellVdec.cpp`, `System.cpp`, `FrameClient.h`, `SourceClient.cpp`. Le broker hôte `packages/neo_swap/ios/Classes/NeoSwap.cpp` change pour les tailles vidéo. Les headers C, exports, formats de sauvegarde, recompilateurs PPU/SPU, réservations/atomiques CELL, synchronisation RSX et réglages sont préservés. Code nouveau du client sous MIT ; modifications des fichiers RPCS3 sous leur licence existante. Les tests utilisent le code de production et des adaptateurs explicitement délimités.

Les autres émulateurs, NeoSwap donation/relais invités, les sauvegardes originales, StikJIT/LocalDevVPN, la vérification CPU avant JIT/dlopen et les fonctionnalités Flutter restent dans leur état de Build 520. Le cœur fourni exige ARMv8.4-A ; le garde ne prétend pas qu'ARMv8-A suffit. Aucune télémétrie automatique, release, modification de `main` ou tag.

## Observations fournies : ne pas mélanger les sessions

[Extraction reproductible](evidence/rpcs3-cell521-log-baseline.json), générée hors ligne par `build-utils/analyze_rpcs3_cell_sessions.py`. Les empreintes des quatre fichiers sont conservées ; les journaux bruts et chemins personnels ne sont pas publiés. 147 groupes build/PID sont séparés. Le journal applicatif contient aussi d'anciennes sessions et d'autres émulateurs ; il n'est pas ajouté aux compteurs des journaux RPCS3 pour éviter les doublons.

| Build / PID / jeu | Observation | Ce qu'elle établit |
|---|---|---|
| 520 / 22138 / BCES00510 | PPU : 136 modules compilés, 400797,363 ms ; codegen agrégé 698706,982 ms sur plusieurs threads | Coût de compilation froide ; le temps agrégé n'est pas une durée murale |
| 520 / 22183 / BCES00510 | Deux boots PPU 709,330 et 665,494 ms ; 40 modules en cache, aucune compilation | Démarrage PPU chaud, pas temps total de lancement de l'application |
| 520 / 22226 / BCES00510 | Boot PPU 664,654 ms ; 25 fenêtres COREPROF, environ 122,6 s | Session chaude distincte des précédentes |
| 520 / 22226 / BCES00510 | FPS des fenêtres : 4,579–57,470 ; médiane 14,069. Médiane p95 92,612 ms ; p99 maximum 6983,918 ms | Irrégularité réelle ; les logs seuls ne séparent pas gameplay, menus et cinématiques |
| 520 / 22226 / BCES00510 | Footprint COREPROF 3029–4750 MiB ; headroom minimum 1905 MiB ; température ultérieure niveau 2 | Pression croissante ; ni jetsam ni cause d'arrêt confirmés |
| 520 / 22226 / BCES00510 | Restauration vidéo 720p : lectures 17–196 ms, maximum 195563 µs | I/O synchrone sur le consommateur PPU, chemin identifié ci-dessous |
| 520 / 22138 / BCES00510 | TAR 1614785536 octets terminé ; VM terminée à la position 1969125883 ; aucun jalon suivant | Le problème restant n'est pas démontré dans TAR/VM ; la phase ultérieure manque |

Les gelés RSX observés ont `fifo_state=2` (boucle de saut du FIFO). Cela ne prouve pas une attente de fence GPU. `gpu_time_ms=-1` signifie mesure indisponible ; les fences à zéro ne permettent pas de conclure que le GPU est rapide. Les SPURS/event/lwcond en attente ne suffisent pas à identifier un deadlock. Aucun délai ni barrière n'est relâché.

Les 667 échantillons NeoSwap concernent seulement les PID 22183 et 22226 et se terminent avant les derniers pics COREPROF. Pour 22226, le footprint échantillonné atteint environ 3,219 Go, le résident 2,647 Go et le ledger compressé 1,088 Go. Ce sont des vues distinctes : ne pas les additionner. Les 8 Gio configurés sont une capacité, les alias mappés ne sont pas de la RAM additionnelle. `padding_bytes` est cumulatif et ne démontre pas une fuite courante de 1,3 Go. Le contrôleur de budget global et ses refus sous réserve système faible sont conservés.

## Interventions et preuves

| Symptôme → cause | Correctif | Validation et résultat |
|---|---|---|
| Le consommateur `cellVdecGetPictureExt` relit les pixels archivés ; l'ancienne politique archive même la tête du FIFO | Garder les huit prochaines images et les huit références récentes ; prélecture des images archivées proches sur le producteur VDEC existant, hors mutex de file et de conversion | Tests du vrai client, méthode producteur extraite, pixels exacts, contrôle négatif de l'ancienne politique, courses arrêt/epoch, échec/relecture, lecture unique en cours, limites octets/objets. Essai à délai injecté : consommateur froid ~17,18 ms, prêt ~0,24 ms, zéro lecture stockage sur le consommateur prêt. Le producteur assume ~17,15 ms ; ce coût n'a pas disparu |
| Blocs de classe 2 MiB pour des pixels de 1382400 octets | Refill vidéo à la taille alignée 64 Kio ; prêts génériques gardent la classe complète ; refus des entrées trop petites ; remplacement borné des anciens blocs inactifs | Broker + backend réels sur mappings de fichiers : huit prêts passent de 16777216 à 11534336 octets, soit 5242880 octets / 31,25 % de backing en moins pour cette charge. Identité des données, alignement, demande générique 2 MiB, quotas, contention, retraits et fautes vérifiés. Ce résultat n'est pas une baisse mesurée du footprint iPhone |
| Journaux de restauration arrêtés après VM | Jalons `ppu_exec_begin/end` et `finalize_run_begin/end` avec position du flux | Chargement, branchement et reset inchangés ; compilation réelle de `System.cpp` requise. Cela localise le prochain diagnostic et ne revendique pas une restauration GoW3 corrigée |
| PUTLLC et range locks coûteux dans les journaux | Deux candidats NEON évalués sans changer la production | [Actions 40092024229](https://github.com/TarbleFR/RewindBox/actions/runs/40092024229), Apple M1 virtualisé, ARMv8.4-A : 295014 comparaisons de correction, pages de garde, 12 tours mesurés après chauffe, données chaudes puis ensemble 1 MiB. Résultats proches et régressions selon le cas : remplacement rejeté. Atomiques et ordre mémoire intacts |

La prélecture possède un plafond global de **8 MiB de payload / huit objets**, pas une promesse de footprint total de 8 MiB. L'image remise au consommateur sort de ce budget ; métadonnées et allocations de décodage restent comptées séparément. La prélecture refuse une session arrêtée, ancienne ou fermée par la pression. Le fallback de restauration reste disponible ; les originaux archivés sont conservés jusqu'au dernier propriétaire. Aucun nouveau thread, API hôte ou couche de traduction.

Les lectures de fichiers, copies FFmpeg et prêts sont testés avec ASan/UBSan. Le test FFmpeg décode 60 images H264 720p, vérifie pixels/plans/strides négatifs/PTS, références partagées, refus transactionnels et vrais `munmap`. Sur l'hôte Linux, il retire 62537728 octets de mappings logiciels possédés dans sa fixture, tout en conservant les pixels restitués. Cela ne prouve ni rendu RSX, ni précision d'un jeu, ni résidence Darwin. La campagne Apple reconstruit le test contre **FFmpeg 8.1.1**, la même version que le cœur.

## Livraison et validation restante

La compilation native iPhone puis la reconstruction de l'application sont obligatoires avant de qualifier l'IPA de testable. Leur statut, les empreintes binaires et le commit d'application seront ajoutés après succès. Les preuves natives 520 non affectées sont réutilisées seulement après vérification du run réussi, du ZIP de diagnostics et des empreintes d'entrée ; la campagne 521 exécute les chemins modifiés.

Aucun iPhone ni contenu de jeu n'est accessible dans cet environnement. Aucun gain FPS, temps GPU, température, footprint ou stabilité GoW3 après modification n'est donc mesuré. Restent à vérifier : lancement réel, ISO, manette, JIT, pause/reprise, sauvegarde/restauration, arrêt et deuxième lancement. L'essai hôte et la compilation iPhone ne remplacent pas ces vérifications.

Pour comparer 520/521 : même iPhone, même dump légal BCES00510, même sauvegarde copiée et même scène, réglages identiques, température initiale comparable. Faire séparément un lancement avec caches froids puis deux chauds, et deux minutes identifiées de gameplay, menu et cinématique. Relever les journaux internes COREPROF/RANGELOCKPROF/SPUPROF/NEOSWAP_VDEC, les nouveaux jalons de restauration et NeoSwap aux mêmes intervalles. Ne pas supprimer les sauvegardes originales ; conserver une copie. Comparer p95/p99, nombre de longues saccades, coût du lancement complet, footprint maximal, résident/compressé distincts, payload prélu, hits/lectures à la demande et température. La référence GPU restera inconnue tant que son compteur n'est pas disponible.
