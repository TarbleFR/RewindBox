# Mario Kart World · IPA 799 · budget de 16,67 ms à 1×

## Identité et méthode

Session B64C3D08-49EE-4349-9245-675B47FA610B, titre 0400C3F00006E000, exécutable 9e244438c3d8ef1c703a6a85ef99c4f0. [Reçu de livraison](rewind799/delivery.json) : IPA 799, source 27316165, moteur [44661903275](https://github.com/TarbleFR/RewindBox/actions/runs/44661903275) de 447c8e06. Les 154 SHA-256 des patches du pin correspondent aux fichiers de la branche, les six empreintes de l’export de préparation correspondent à identity.json. Le moteur inclut donc 0154 et les corrections antérieures de résidence, de prélecture bornée et de préchauffage. La piste 0155 ci-dessous est postérieure à cette capture.

Recalcul avec tools/s2arm_prototype/shader_session_metrics.py sur le seul host.log de ce titre, filtre de session explicite, recoupement avec le journal PID 9483. Les anciens profils CPU de profiles.zip ne couvrent pas la session. Percentiles au rang supérieur. Les indices d’assets désignent l’asset observé le plus récemment. Aucune annotation synchronisée ne permet de nommer les courses. Le réglage visé est 1× ; les signatures de la fenêtre 3600 mesurent des surfaces de scène de 1248×700 à 1256×704. L’export ne fournit pas une attestation continue du réglage utilisateur.

| Série moteur | Intervalles | FPS | p95 / p99 ms | >100 / >200 / >500 ms |
|---|---:|---:|---:|---:|
| Ensemble, 237,788 s | 7232 | 30,414 | 69,364 / 136,830 | 153 / 41 / 10 |
| race_sequence_asset | 5259 | 27,282 | 74,890 / 137,797 | 123 / 28 / 6 |
| selection_asset | 1636 | 43,146 | 31,488 / 131,316 | 24 / 10 / 4 |

Aucun trou ni abandon déclaré dans la série moteur. À l’affichage, fenêtre 3600 : 292 présentations renseignées, 253 tardives ou écartées dont 9 écartées, p99 200,02 ms. Fenêtre 7200 : 299, 164 dont 143 écartées, p99 75,01 ms, proche du passage en arrière-plan. La 799 fournit ici des quantiles et des comptes de présentation. Les horodatages successifs nécessaires à une moyenne FPS écran exacte ne figurent pas dans l’export. Une fenêtre incomplète ou proche du passage en arrière-plan ne représente pas une course entière.

## Les dix plus longs intervalles

Durées en ms. SVC = temps dans les quatre appels invités suivis du thread qui présente. RomFS = durée cumulée des appels de lecture qui se terminent dans l’intervalle, tous threads confondus. Upload = coût CPU enregistré par le moteur. Ces durées peuvent se chevaucher et chevaucher les bornes d’une image.

| Image | Intervalle | SVC | CPU upload | RomFS cumulé |
|---:|---:|---:|---:|---:|
|304|2226,2|1055,3|556,5|2174,6|
|3518|2182,5|1963,5|6,9|15,0|
|3303|1887,0|1859,7|1,5|65,3|
|2441|1881,2|778,5|573,1|5,8|
|300|1755,4|4,1|0,0|1673,2|
|3756|1540,2|1423,7|10,4|69,8|
|2368|1088,5|157,2|585,5|318,3|
|121|910,9|2,7|63,4|3,3|
|1516|566,1|84,1|336,1|552,3|
|3576|503,2|454,0|0,0|37,3|

## Registre et décisions

Les chemins moteur sont relatifs au pin amont après application ordonnée des patches. Les changements décrits sont dans 0155. La vérification sur cible physique et l’absence de régression restent ouvertes pour l’ensemble du lot.

| Priorité et défaut | Preuve, coût et fréquence 799 | Cause, correction ou dépendance | Risque et vérification |
|---|---|---|---|
| P0 · Thread de présentation bloqué | 74 des 153 intervalles lents dépassent 100 ms de SVC suivis. À 3518 : 1963,450 ms, plus long trou hors NVN 1962,168 ms, CPU du thread 37,964 ms, GPU 27,1 ms, zéro nouveau pipeline. | runtime/src/thread.c, svc_thread / svc_thread_impl / wake ; hle_nvn.c, nvnQueuePresentTexture ; rb_course_tracking.inc. Le temps dans SVC est confirmé ; l’objet et le producteur précis restent inconnus en 799. 0155 conserve par thread le plus long appel, SVC, clé ou liste, PC, résultat, handle signalé disponible et dernier thread invité ayant réveillé. Sortie différée pour image >100 ms et appel ≥50 ms. | Le réveil d’un groupe peut être transitoire. Un identifiant nul inclut les événements hôtes et les absences de réveil. Aucun accès supplémentaire à la mémoire d’une liste invitée. Vérifier retour, timeout et clé dans la prochaine capture avant de modifier l’ordonnancement. |
| P0 · RomFS, fichiers adossés, décompression et activité disque | À 300 : 593 lectures, 134 Mio, 1673 ms cumulées ; à 3518 : 2 lectures, 256 Kio, 15 ms pour 166,2 Mio lus par le processus et 5157 défauts avec lecture. Pic 2156 Mo / 10 s, 209882 page-ins ; 55014 décompressions de pages machine sur l’intervalle 3518. | services/S2A.Services/RomFsIndex.cs, IndexedStorage.ReadIndexed / File : le chemin dossier reconstruisait le préfixe racine au premier accès à chaque fichier. Calcul unique et vérification de plage sans débordement dans 0155. Durée de décompression invitée, thread producteur RomFS et latence individuelle des fautes non enregistrés. | Préfixe et comparaison de chemins identiques, lectures courtes encore refusées. Croiser handle/réveil avec traces de fautes et E/S horodatées sur appareil. Les compteurs machine couvrent aussi les autres processus. |
| P0 · Premier transfert de textures | 7 images dépassent 100 ms d’upload CPU. À 2441 : 980 premiers transferts, 0 retransfert, 128 Mio, 573,1 ms CPU, 27,6 ms de lots GPU achevés, 5258 pages de stockage absentes. Attente PSO de la file 13,4 ms, 17,7 ms PSO/bibliothèques dans le diagnostic longframe. Sur la session : 4 831 153 229 octets, 8335,162 ms CPU. | graphics/nvn/gfx/nvn/nvn_mtl.m, pkg_upload_, up_flush. Suppression de la création de vue source GPU inutilisée en mode linéaire ; réutilisation du tampon BC entre niveaux ; références successives identiques regroupées dans le suivi de lots ; si la liste de décodage GPU ne peut grandir, annulation des commandes partielles et repli CPU. | Ni cache agrandi ni prélecture générale. Vérifier formats BC/linéaire, mipmaps, couches, remplacement après perte de lot, fidélité couleur et pression mémoire. La part exacte des 573 ms dans chacun de ces chemins et les besoins réels de chaque texture restent inconnus. |
| P0/P2 · Attente pour un diagnostic de staging | pkg_upload_ imposait rec_drain et up_wait_zero après les premiers uploads fractionnés puis aux puissances de deux. Aucune ligne de transfert fractionné dans le host.log de la 799 ; effet sur 2441 non démontré. | Le relevé mémoire après retrait devient opportuniste lorsque les lots sont déjà terminés. Les barrières de consommation, le recyclage des slots et le plafond de staging par morceaux restent actifs. | Le journal peut contenir moins de relevés après retrait. Vérifier l’absence de pic de staging supplémentaire et les clôtures de ressources lors des grosses textures. |
| P1 · Coût CPU/NVN régulier | Fenêtre 3600, 2216 dessins et 127,8 passes/image, 17,311 ms CPU de soumission ; 1682,7 résolutions de vues répétées/image. 2332 soumissions fractionnées et 38344 barrières d’entrée en 300 images ; coût individuel non isolé. | nvn_mtl.m, tex_by_id : en cas de remplacement d’une vue, réemploi de la base déjà obtenue par tex_mtl sous g_rmu. La recherche est répétée si la première ne rend aucune base. Le nombre de doubles recherches effectivement évitées est un sous-ensemble inconnu des résolutions. | Inspecter fidélité des vues aliasées, profondeur/couleur et écritures invitées. Rejeu Metal avec dépendances lecture/écriture nécessaire pour supprimer des barrières ou fusionner d’autres passes. Le compteur annonce zéro passe cassée par copies/mises à jour dans cette fenêtre. |
| P1 · Budget GPU et cadence visible | Fenêtres 3600 et 6600 : GPU p50/p95 17,23/26,30 puis 13,46/20,14 ms. Soumission + présentation p50/p95 18,35/50,07 puis 12,77/21,07 ms. Le jeu alterne son intervalle de présentation 1/2 ; plafond utilisateur S2A_FPS absent. | hle_nvn.c, nvnQueuePresentTexture / synthèse par fenêtre : ajout FPS visibles par timestamps du compositeur et compteur d’horodatages manquants. Pas d’addition CPU + GPU. Le mode de présentation demandé par le jeu reste respecté. | Une fenêtre avec timestamps manquants sous-compte les présentations ; comparer uniquement celles à couverture complète. Capture GPU avec compteurs par passe nécessaire pour attribuer le coût des cibles, copies et dépendances. |
| P1 · Reconstruction graphique | 288,140 s entre starting et stageInputs. CPU prepare réutilisé, génération graphique en construction ; 6252 cibles, 2 traductions, 0 manquante ; 893 décompressions vers fichiers temporaires, aucun échec déclaré. | graphics/nvn/host/rb_external_stages.inc, rb_alias_candidate : exclure avant hachage les combinaisons source/stage absentes du manifeste. rb_prepare_stages.inc, rb_row_digest : encodage hexadécimal direct, mêmes SHA et format. Trois durées monotones exportées par S2ArmGraphicsGeneration.m pour recherche de cibles, scan et récupération. Le pont iOS journalise aussi prepareMs autour de l’appel moteur et exportMs autour de la copie des preuves, y compris quand la génération est réutilisée. | Comparer empreintes et couvertures de procédures à froid, reprise incomplète puis lancement de la même génération vérifiée. Les durées de sous-phases ne peuvent être reconstituées en 799. Les contrôles d’identité et la persistance atomique restent actifs. |
| P1 · Archives et concurrence préchauffage | 298/298 fonctions, 200/200 PSO requis validés. Attente initiale 3,231 s ; 2 workers différés. Au terme du préchauffage, 3967 constructions depuis archive, 429 compilées, zéro fichier périmé écarté ; durée d’arrière-plan 246,45 s. Sur 7232 intervalles : 102,662 ms d’attente PSO, 21,233 ms bibliothèque, 104 compilations MSL pour 89,345 ms. | rb_reference.inc, préchauffage dans nvn_mtl.m, préparation du bridge. La compilation PSO est réfutée comme cause du gel 3518. Des archives sont exploitées durant la session. L’export ne contient pas un second lancement équivalent de la génération vérifiée. | Suspendre arbitrairement les workers peut déplacer les compilations au premier dessin. Mesurer charge des workers, premier dessin et temps de reprise sur le même passage avant d’ajuster leur budget. |
| P1/P2 · Résidence, chauffe et réveils | Empreinte maximale échantillonnée 5006 Mio ; fenêtre 3600, zéro pool libéré encore vivant dans cet instantané. État thermique 1 puis 2 ; fenêtre 6600, 4202 réveils/s, CPU 0,80 W et 232 %, GPU occupé 433 ms/s. GC .NET : 148 ms de pauses cumulées sur 240 s. | nvn_mtl.m, up_flush / pkg_upload_ ; thread.c, wake / peer_yield ; nvn_session.inc. Réduction des temporaires et attentes diagnostiques ci-dessus. Les octets Metal, empreinte physique et stockage adossé se recouvrent. Ni fuite prolongée ni origine thermique unique démontrée. | Série de 20 min sur le même appareil, pression système comparable, passage à chaud et repos après sortie. Purger toutes les textures rendrait les retransferts probables. |
| P2 · Audio, arrière-plan, reprise et sauvegardes | Notification de réinitialisation audio suivie d’une reconstruction réussie. En fin de capture, deux watchdogs sans callback (1043 et 2026 ms) tentent stop/start après refus d’activation, code 2003329396. Passage en arrière-plan avec 3 images en attente abandonnées. | compat/tree/src/Ryujinx.Audio.Backends.Apple/AppleHardwareDeviceSession.cs, S2ARecover : le watchdog ordinaire diffère le redémarrage lorsque iOS refuse l’activation, conserve les buffers, réessaie selon le délai existant ; les notifications de reset conservent leur reconstruction. | Vérifier interruption réelle, reprise audio avec activation réussie, arrêt/reprise du moteur, chargement d’une sauvegarde après relance. Aucun aller-retour complet équivalent dans le journal, aucune preuve de causalité audio pour 3518. |
| P2 · Collecte et analyse | Profils CPU joints antérieurs ; 2689 mesures de lots GPU disponibles, 1865 indisponibles. | shader_session_metrics.py ajoute p99 et regroupement par indice d’asset. Télémétrie SVC en mémoire bornée, sortie dans le lot différé ; durée de préparation en trois entiers, lisibles avec les anciens exports. | Cinq tests existants de l’analyseur et quatre contrôles existants des exports exécutés. Mesurer sur appareil le surcoût résiduel et les FPS visibles ; écarter les fenêtres avec couverture lacunaire. |

## Réveils et écritures après la 799

La 799 atteint l’état thermique sérieux. Aux images 6 600 et 6 900, iOS relève respectivement 4 202 et 4 487 réveils/s pour le processus. Le tableau compare ensuite des essais locaux. Ces deux fenêtres iPhone servent de référence pour le prochain passage en course à 1×.

| Opération et conditions | Avant | Après | Travail vérifié |
| --- | ---: | ---: | --- |
| Événements invités, 8 threads POSIX, 5 000 signaux à tour de rôle, 7 passages par version | 40 000 réveils | 5 000 réveils | 5 000 événements reçus à chaque passage. Temps CPU médian du processus Linux de 1 354,8 à 138,5 ms. |
| Présentateur classique pendant 5 000 images DisplayLink, avec notifications d’ajout, de prise et de fin séparées sur le banc pthread | 15 000 revérifications inutiles | 0 | 100 bascules d’ordonnanceur d’affichage, 1 001 images classiques traitées et 200 images écartées lors des suspensions simulées dans chaque version. |
| Journal de course, rejeu des 7 232 images et 153 lignes de pause | 7 385 écritures | 226 écritures | 2 089 095 octets identiques et résultats identiques avec `shader_session_metrics.py`. |
| Premiers dessins de pipelines, rejeu de 1 341 lignes en 94 groupes | 1 341 écritures | 116 écritures | 400 406 octets identiques. Les groupes s’arrêtent aux interruptions observées du journal et aux bornes de lot du moteur. |

Les essais utilisent les fonctions de sélection des réveils, d’attente et de regroupement extraites des versions comparées. Le test de présentation contrôle l’ordre des notifications pour rendre le comptage reproductible. Les quatre niveaux thermiques simulés terminent chacun 34 768 copies avant et après 0157. Une fois l’état sérieux ou critique échantillonné, les boucles de scrutation du travailleur de copie et de son appelant ont chacune un budget nul. La file continue à signaler les transferts prêts.

Les sommes SHA-256 des sorties rejouées sont `331b9b85be553fd464941cafc3ed5793ae164ad95efdfedaab8d3970224988a5` pour les mesures par image et `226224e9a3a899abbb8f1679913bdc3d314e6933d11bede5f9589d6c8d6c52ba` pour les premiers dessins. Les écritures comptées sont les appels de l’application pour ces lignes, à contenu conservé. Les réveils du processus, l’énergie par image, l’état thermique et les FPS restent à mesurer sur un iPhone utilisant le moteur 0159.

## Chargement de la carte de Mario Kart World

Vidéo du 20 novembre, durée 10,59 s. Sur la carte de lancement, le compteur affiche successivement 60 FPS et 23 ms maximum, 14 FPS et 767 ms, puis 3 FPS et 942 ms à 3,5 s. La mémoire affichée monte de 3,3 à 4,2 Go. Le numéro du moteur et l’identité de la session ne sont pas visibles.

La 799 fournit un point de comparaison indépendant. L’image 121 dure 910,9 ms, dont 2,6 ms de création de pipeline et bibliothèque et 63,4 ms pour 42 premiers uploads de textures totalisant 131,25 Mio. Le thread de présentation consomme 625,1 ms de CPU, et le processus lit 138,2 Mio depuis le stockage sur l’intervalle. Ces compteurs se chevauchent. À l’image 304, 556,5 ms de transferts CPU et environ 1 055 ms d’attente invitée sont relevés. L’attribution précise du pic de la vidéo nécessite le journal de son lancement.

Le moteur 0160 consulte en mémoire l’identité exacte du shader avant la vérification des fichiers de traduction. Il retire de la liste de promotion les paires déjà examinées et transfère les lots prêts sans recopier leurs objets sous verrou. Une bibliothèque déjà publiée par le travailleur de prélecture ne crée plus un élément vide à traiter sur le thread de soumission. Le premier upload traite quatre pages de texture indépendantes en parallèle dans la même boucle, avec les empreintes et protections existantes.

| Essai local | Avant | Après | Résultat conservé |
| --- | ---: | ---: | --- |
| Préparation séquentielle des 298 étapes et 200 pipelines du manifeste 799, cache initialement vide, même mode de profondeur | 698 appels au contrôle de disponibilité | 298 appels | 298 variantes chargées. Les absences restent réessayées. Les variantes de profondeur et les étapes distinctes gardent leurs identités. |
| Hachage en mémoire de 137 626 752 octets, longueur correspondant au volume téléchargé sur l’image 121. Médiane de sept exécutions alternées sur Linux | 43,71 ms CPU | 14,84 ms CPU | 312 comparaisons identiques avec plages vides, bords partiels, sources décalées et pages de 4, 16 ou 64 Kio. |

Les instants du HUD sont des mesures de la vidéo. Les durées du banc isolent le calcul sur des données synthétiques déjà résidentes. Le coût du stockage, le FPS et le maximum du HUD après 0160 restent à mesurer sur iPhone.

## Réveil des workers et chauffe après 0160

En 799, le moteur a relevé 1 705 mises en attente du travail facultatif pour 242 s cumulées. Au niveau thermique sérieux, iOS attribue au processus 4 202 puis 4 487 réveils/s dans deux fenêtres de course. Le compteur couvre tout le processus.

Le préchauffage facultatif respecte désormais le même plafond après une promotion en tête de file. Une alerte sérieuse ou critique bloque les nouvelles tâches facultatives. Les tâches déjà engagées se terminent. Le retour à l’état nominal garde au plus un worker pendant cinq secondes à compter du dernier échantillon chaud. En préparation de référence, une demande exacte pour le premier rendu peut passer en priorité dans le préfixe obligatoire. Le chemin utilisé par un vrai draw garde son accès au pipeline.

| Vérification ciblée sur Linux | Avant | Après |
| --- | ---: | ---: |
| Délais expirés à quatre workers arrêtés par le gouverneur pendant 4,25 s | 64 | 14 |
| Appels de scrutation à quatre workers pendant un premier usage simulé de 350 ms | 2 377 | 0 |
| Appels d’écriture du tampon stdio sur les 498 lignes de référence 799, une ligne par image simulée | 498 | 6 |

Le rejeu stdio produit les mêmes 180 254 octets. Le manifeste personnel est vidé sur des points de contrôle espacés de 120 images ainsi qu’à la suspension et à l’arrêt ordonné. Une interruption brutale peut perdre les dernières entrées du cache en attente. Le test de sélection de files vérifie la priorité d’un pipeline exact obligatoire en niveau sérieux, l’attente du pipeline facultatif promu et la consommation unique de chaque entrée à la reprise. Ces mesures isolent les chemins corrigés. La température, le débit d’écriture et le nombre total de réveils en jeu restent à vérifier sur iPhone.

## Vérification physique restante

Sur le même appareil, même version du jeu, mode 1× et départ comparable : annoter circuit et phase à partir d’une capture synchronisée ; premier passage puis même passage avec génération et archives réutilisées. Conserver images moteur et timestamps écran, p95/p99, seuils 100/200/500 ms, CPU de soumission, GPU, attente SVC/objet/réveil, uploads, empreinte, E/S, état thermique et réveils. Associer le lancement au SHA moteur et à la génération. Relever l’intégrité visuelle, l’audio et la sauvegarde après reprise. Un avant/après reste indisponible pour 0155.

### Débit en course après 0162

Le patch 0163 traite les invalidations du cache de vues Metal dans `tex_by_id`. Les changements de programmes et certaines écritures d’une texture non virtuelle sont suivis par numéro de série. Une recherche peut réutiliser sa vue si tous les changements depuis son dernier passage sont connus et concernent d’autres numéros de série. Le chemin complet reste actif lors d’une collision de suivi, d’une modification du même objet, d’une invalidation globale, d’un remappage sparse, d’un alias compressé ou d’un changement pertinent des données invitées. Les compteurs distinguent les vues réutilisées sans nouvelle recherche, les recherches qui retrouvent la même base et celles qui la remplacent.

Banc local Linux x86-64, temps CPU du thread, 300 images synthétiques de 1 683 vérifications, neuf essais par variante et médiane. Le scénario alterne changements de programme, remplacements du même objet, changements des données invitées et invalidations globales à deux fréquences. Le banc appelle la logique de génération du patch avec un modèle de résolution de texture et compare les valeurs et remplacements. Les sommes de contrôle concordent à chaque essai.

| Invalidation globale simulée | Recherches avant → après | CPU par image avant → après | Économie CPU du banc |
| --- | ---: | ---: | ---: |
| Toutes les 2 images | 504 900 → 322 506 | 0,0418 → 0,0342 ms | 0,0076 ms |
| Toutes les 10 images | 504 900 → 96 745 | 0,0385 → 0,0271 ms | 0,0114 ms |

Le banc mesure les parcours du cache sur hôte. Les 17,311 ms par image de la fenêtre 3600 sont le temps CPU de l’ensemble de la soumission sur iPhone. La part gagnée par 0163 sur cette charge réelle reste à mesurer. L’analyseur a aussi rejoué la 799 et une trace synthétique couvrant horodatages valides ou absents, deux budgets d’affichage, attente invitée et motifs de vidage.

Un profil court antérieur du même titre du 18 novembre à 13 h 01 a classé 1 318 mesures d’encodeurs. Les trois plus coûteuses sont des passes 1248×700 avec chargement couleur et profondeur, 388, 401 et 693 dessins et des durées de 3,786, 3,690 et 3,387 ms. Les durées mesurées sont regroupées par type dans l’analyseur. Les chemins Metal existants emploient déjà l’action Clear lorsqu’un effacement peut être intégré à l’ouverture d’une passe. Le profil ne contient pas les dépendances et pixels nécessaires pour déclarer les autres chargements et stockages redondants. Les actions de rendu Metal de ces passes conservent leur comportement.

| Portion de référence 799 | Échantillons | FPS moteur | p95 / p99 moteur | >100 / >200 / >500 ms |
| --- | ---: | ---: | ---: | ---: |
| Indice `race_sequence_asset`, tous les intervalles | 5 259 | 27,282 | 74,890 / 137,797 ms | 123 / 28 / 6 |
| Images 3301 à 3600, même indice | 300 | 14,297 | 133,886 / 437,877 ms | 32 / 9 / 3 |

Pour 3518, le journal confirme 1 963,45 ms en synchronisation et zéro nouveau pipeline. Objet et thread de réveil sont inconnus dans cet export. Pour 2441, 980 premiers transferts totalisent 128 Mio et 573,081 ms CPU, sans motif de vidage observé. Le patch groupe des premiers transferts non sparse jusqu’à 128 Kio quand ils tiennent dans un tampon de staging déjà alloué et que le plafond thermique le permet. Les limites de lot et les dépendances d’exécution sont conservées. La sortie d’une image lente compte les vidages aux frontières, à saturation, lors d’un transfert isolé, par limite de lot ou par découpage.

À relever sur iPhone 16 Pro Max, Mario Kart World 1.0.0, Coupe Champignon 150 cc à 1×. Identifier chacun des quatre circuits et un segment reproductible par circuit. Relever séparément le premier passage, le retour avec caches compatibles et un passage après 20 min. Comparer FPS moteur et affichés, percentiles, seuils, horodatages manquants, échéances à 16,67 et 33,33 ms et durée de soumission. Vérifier jeu à vitesse normale, rendu couleur/profondeur, progression après relance et apprentissage des shaders en course. Les anciennes lignes `on-screen` de la 799 ne suffisent pas pour reconstruire ses FPS affichés et ses échéances par intervalle demandé.
