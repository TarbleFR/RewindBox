# RPCS3 CELL538 — caches SPU et attribution des pauses

Base fonctionnelle : Claude `961c37f158fc387b2fec418b794cb6e456fadf04` (MeloNX537 final), avec son reçu ajouté par `fe9e23a1`. Cœur538 : `066a3fe6c015a3c25807a9feac07b392d2fc2cb4`. Le correctif canonique534, les corrections536 et les modifications MeloNX537 sont conservés. Aucune modification de `main`, de sauvegarde originale ou de cache existant ; aucune release publique.

Les nouvelles pièces confirment des saccades importantes. Elles ne constituent pas une comparaison contrôlée 534/536 et aucune exécution iPhone538 n'est encore mesurée. Le 538 corrige une recherche redondante et évite une nouvelle invalidation générale des caches536 compatibles ; il ne prétend pas résoudre tous les ralentissements observés.

## Observations sur appareil avant538

Source reproductible : `build-utils/analyze_rpcs3_cell538_logs.py`, résultats et empreintes des cinq pièces dans `docs/evidence/rpcs3-cell538-observed.json`. Les chemins privés et les fichiers du jeu ne sont pas recopiés.

| Build / PID | Période RPCS3 UTC, 25 octobre 2026 | Portée |
|---|---|---|
| 534 / 28732 | 10:23:37–10:24:11 | Fin de session3, déjà analysée précédemment |
| 534 / 28939 | 10:31:30–10:33:48 | Démarrage session1, restauration session2 |
| 536 / 29509 | 11:35:09–11:37:27 | Démarrage session1, restauration session2 et jeu non classé |

`NeoSwap-v1.jsonl(2).previous` contient uniquement des instantanés534 : PID28732,28916,28935,28939. Ce n'est pas le journal des opérations gérées : aucun `batch.events`, aucun PID29509. Les deux avertissements mémoire du PID28732 ne sont pas des événements536. L'absence de lots ne permet pas de compter les opérations perdues, les restaurations actuelles ou leurs latences. Le journal applicatif contient 537 occurrences historiques du message GameDB indisponible ; ce n'est pas un décompte du processus536.

La vidéo dure 152,720 s, avec cinématique et gameplay visibles. Aucun horodatage de création ni ancrage monotone partagé : son nom ne suffit pas à l'aligner sur le PID29509. Sa cadence d'encodage variable n'est pas la cadence du jeu.

Les compteurs périodiques sont rapprochés uniquement dans un même PID, session, thread de journalisation et lot de mesures, à moins de100 ms sur l'horloge native. Les copies d'un événement dans les deux fichiers sont identifiées comme captures rapprochées, pas comme nouvelles restaurations. Les percentiles ci-dessous sont les bornes issues des histogrammes fusionnés, pas une moyenne des percentiles de fenêtres.

| 536 / session2 | Intervalles | p50 ms | p95 ms | p99 ms | Maximum ms | >50 / >100 / >500 ms |
|---|---:|---:|---:|---:|---:|---:|
| Toutes fenêtres retenues |1124|58–58,999|119–119,999|208–215,999|11401,663|753 /144 /5|
| Fenêtres8–23, après première reprise |1102|58–58,999|117–117,999|192–199,999|5405,488|745 /142 /3|
| Fin, fenêtres16–23 |437|86–86,999|136–143,999|208–215,999|882,160|437 /122 /2|

Aucun intervalle déclaré indisponible dans ces fenêtres. La première ligne inclut la transition de restauration : le maximum11,4 s n'est pas attribué à du gameplay continu. Un intervalle peut traverser plusieurs fenêtres ; sa durée entière appartient à sa publication ultérieure. Les 97,349 s d'intervalles retenus ne sont donc pas une durée complète de session. L'instantané `FREEZE_DUMP` à11:35:53,112 indique4,676 s sans image ; ce n'est ni une durée supplémentaire à additionner ni une preuve d'interblocage.

Pic d'empreinte échantillonné par `MEMPROF527` : **5447473528 octets,5195,12 Mio** ; pic compressé1832,42 Mio. Ces pics ne s'additionnent pas. L'échantillonneur applicatif plus lent voit un maximum5418228088 octets ; les deux séries n'ont pas les mêmes instants. État thermique0 puis1 à11:35:40 (108 des129 échantillons à1), sans mesure de fréquence effective ni preuve de throttling. `donor_lost` passe à2 dès11:35:16, avant la restauration ; `relay_ready` passe à0 à11:36:58. La cause de ces transitions n'est pas établie par ce fichier et elles ne prouvent pas une terminaison mémoire.

## Causes distinguées et chemins de code

- **Recompilation SPU à cache froid :** PID29509,5153 objets absents puis écrits,852 réutilisés ; PID28939,7 absents et6424 réutilisés. Le changement de clé SPU du536 avait été annoncé et peut expliquer cette préparation supplémentaire. Des scènes, réglages et états thermiques différents empêchent toute comparaison de FPS. En fenêtre10,428 tentatives SPU représentent4947,668 ms cumulées, tandis qu'un intervalle invité atteint5405,488 ms. Cela désigne la compilation comme contributeur plausible, sans égaler une somme multithread à une pause murale.
- **PPU déjà réutilisé :**40 modules au démarrage en705,683 ms,45 à la restauration en735,983 ms, aucune compilation. Les ensembles diffèrent ; aucune comparaison avec les136 modules froids historiques. `JITPROF_BOOT` est émis avant la préparation SPU ; ses zéros SPU ne prouvent pas l'absence de travail SPU. `ppu_pipeline=0` conserve la signification du sélecteur existant, pas «aucune optimisation».
- **Recherche disque en double confirmée :** `SPULLVMRecompiler.cpp` appelle `jit_compiler::load_cached_object`, qui valide l'objet et son symbole attendu. `try_add_cached` transmet ce résultat à `ObjectCache`. Après une absence, `ObjectCache::getObject` cherchait de nouveau les variantes compressée et brute, sous un compteur de lecture PPU, une fois l'IR construit. Un fichier apparu entre-temps pouvait même être repris sans vérification du symbole initial. La mutualisation des compilations identiques déjà présente reste inchangée.
- **Shaders :** profil legacy explicite, `database=0`, mode configuré/appliqué0, aucun repli dans `SHADERCFG536`. Le flush GameDB après initialisation existe déjà ; une configuration legacy a priorité par conception. Pas de remplacement silencieux du choix utilisateur par Async. Fenêtre18 : un pipeline graphique768,627 ms, aucune compilation source ni création de module ; maximum invité882,160 ms dans le même lot. Association de fenêtre, pas chevauchement exact démontré. Le mode asynchrone disponible utilise le chemin interprété de secours, avec coût/rendu à vérifier sur appareil avant recommandation.
- **Ralentissement après compilation :** fenêtre23, deux tentatives SPU seulement,24,200 ms cumulées, aucun shader ; médiane95,273 ms, SPU3,695 cœurs moyens et RSX0,667. Les attentes de réservation cumulées se recouvrent entre threads. Le mutex d'admission LLVM est négligeable dans ces mesures ; aucune preuve de réveil perdu ou d'interblocage persistant. Les SPU, le producteur des sémaphores invités, la consommation RSX et les réservations doivent rester ordonnés. Les garanties invitées ne sont pas supprimées pour faire baisser un compteur.
- **NeoSwap :** `VDECIO528` n'enregistre aucune lecture de frame archivée dans les fenêtres536 retenues. Impossible d'attribuer ces pauses à la restauration vidéo coûteuse historique527. Sans opérations29509 ni pages sales, aucune nouvelle réserve, éviction ou politique `fsync` n'est justifiée ici. Les protections/préchargements/checkpoints existants et le retrait534 des synchronisations disque sont conservés.
- **Save state :** finalisation de restauration vers11:35:46,696 puis frames invitées ; aucune erreur `missing_resource` dans cette capture. La correction de montage534 est conservée, pas présentée comme nouvelle.

## Modifications538

1. `Utilities/JITLLVM.cpp` : après le buffer prévalidé, un cache SPU absent reste absent pour cette compilation. Aucun second accès disque ; le chemin PPU, l'écriture, la validation initiale, la durée de vie du buffer et les bornes du cache restent identiques.
2. `rpcs3/Emu/CPU/JITCacheCompatibility.cmake` et son appel dans les deux listes CMake : correspondance **du seul chemin et du seul SHA-256538 revus** vers l'empreinte536. La preuve reconstitue exactement le fichier536 en retirant cette insertion ; ni IR, émetteur, ABI, relocation ni structure invité ne change. Les clés restent PPU`a987639e9f838d1c`,SPU`d070cb361bdef607`. Un autre fichier ou un octet futur différent retrouve son hash réel et invalide normalement. Aucune réutilisation forcée des objets534.
3. `IOSShaderTiming.h` / `RPCS3IOSPerformance.cpp` : `SHADERSTALL538` pour les opérations≥50 ms,32 entrées fixes, verrou tenté sans attente, pertes explicitement comptées, bornes début/fin et ancrage `report_steady_us`. Portée processus à la fin de l'opération ; le numéro de session du rapport n'est pas une attribution de phase. Au maximum33 lignes par fenêtre5 s, stockées par le filtre `COREPROF` déjà conservé dans l'historique borné après erreur. Aucune allocation sur le chemin de mesure.

Les modifications sont dans le patch canonique unique et le manifeste de264 fichiers, avec fixture réversible538. Aucun changement NEON spéculatif : le précédent microbenchmark536 n'avait pas montré de gain suffisamment stable pour déployer un autre comparateur.

## Vérifications et limites

`docs/evidence/rpcs3-cell538-local.json` : corps complet réel de `getObject` extrait avant/après, adaptateurs LLVM et accès réels au système de fichiers ; absences, buffer prévalidé, fichier tardif, objet invalide, chemin PPU.5153 absences simulées :10306 tentatives d'ouverture supplémentaires avant,0 après ;40,6912 contre0,433311 ms sur cet hôte sous sanitizers. **Ce n'est pas un gain iPhone, ni la suppression des coûts LLVM des5153 compilations.**

ASan/UBSan :40 000 producteurs concurrents, comptabilité des pertes/drain, débordement32+8, seuils et scope réel ;824 octets fixes sur l'hôte. Les tests de configuration536 et des compteurs534 sont réexécutés parce que leur en-tête a changé. CMake vérifie l'alias exact et son refus pour un autre chemin ou un changement d'un octet. Le patch se rematérialise sur un checkout amont intact avec toutes les empreintes et exports vérifiés.

La CI538 exécute également la relocation LLVM22 réelle entre processus et construit le véritable cœur iPhone. Les résultats historiques sont conservés uniquement pour leurs entrées inchangées ; les preuves et le contrôle de l'IPA seront ajoutés au terme de la livraison privée.

À mesurer sur iPhone538 : même copie de save state et mêmes scènes, conserver les caches536 pour une première comparaison chaude, puis cache froid isolé sans effacer les originaux ; répéter le parcours en distinguant cinématique/combat/traversée, mêmes réglages et état thermique ; comparer p95/p99 et pauses≥500 ms, empreinte/compression, restauration et session30 min. Les nouvelles bornes shader doivent être alignées par leurs ancrages, jamais par l'heure d'export. Aucun FPS538 ni gain de fluidité n'est encore affirmé.
