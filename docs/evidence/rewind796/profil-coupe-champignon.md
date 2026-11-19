# Coupe Champignon en 150 cc, Mario Kart World 1.0.0

Le profil s’applique au programme `0400C3F00006E000` et au build principal `9e244438c3d8ef1c703a6a85ef99c4f0`. La révision graphique 2 ouvre une génération distincte. À partir d’une installation 795, l’application conserve le jeu importé, les réglages et la sauvegarde. Elle peut reprendre les données compatibles d’une génération 795 inachevée. À l’ouverture de RewindBox, un jeu déjà préparé sur la 795 déclenche la copie des caches compatibles. L’écran affiche « Préparation du cache graphique » et le nombre de fichiers examinés. Si le joueur lance une course pendant la copie, la préparation du jeu reprend la même transaction. La compilation et le contrôle Metal démarrent au lancement du jeu, sous « Reconstruction des shaders et des pipelines graphiques ».

| Source | Révision | Lignes de rendu observées | Portée documentée |
| --- | --- | ---: | --- |
| [Kartnative](https://github.com/pahorema/kartnative/tree/47f2d1d5c8298a562190dd0493da8a4eb18e4626/dm/games/0400C3F00006E000) | `47f2d1d5` | 3 429 | Quatre circuits de la coupe |
| [Plumber Racer 2](https://github.com/cheemu21/plumber-racer-2/tree/843170ac3e7068d0a096acc9694aea478cc8873b/dm/games/0400C3F00006E000) | `843170ac` | 4 238 | Titre, menus, cinématique et Mario Bros. Circuit |

Le convertisseur de 0141 accepte 7 659 descriptions de 440 octets. Il écarte quatre descriptions de chaque source dont la fonction du test alpha reste indéterminée. Les états conservés représentent 1 226 combinaisons distinctes avant l’association aux shaders. Le test et l’écriture de profondeur sont dynamiques dans le rendu NVN. Le convertisseur conserve les formats de profondeur et de stencil, les masques des cibles, les facteurs et équations de mélange, et la couverture alpha.

La correspondance des identifiants dépend du contrôle NVN2 et du code du jeu importé. Les compteurs de l’export `external-profile-counts.plist` donnent le total natif dédupliqué, les sources manquantes, les ambiguïtés, les refus et les réflexions manquantes. La préparation ajoute aux références de l’iPhone jusqu’à 32 recettes attestées dans les deux sources, 32 propres à Kartnative et 16 propres à Plumber Racer 2. Les lignes suivantes utilisent les travailleurs existants. Les manifestes source agrègent les parcours sans fournir de marqueur de circuit pour chaque ligne.

### Capture 795 sur iPhone 16 Pro Max

Le journal et l’archive de préparation décrivent la même session. Les 32 descripteurs de l’archive et les 53 observations supplémentaires du journal donnent 85 recettes natives complètes. Le contenu de chaque description de 432 octets reproduit son identifiant d’archive. En plus des 58 identités prioritaires, 21 autres identités étaient déjà dans l’inventaire général et 75 en étaient absentes. Le journal atteste le chargement en jeu de la traduction de ces 75 shaders, dont 74 traduits par anticipation pendant la session. Leur récupération avant le premier dessin reste à mesurer dans le prochain export. [Empreintes et observations](profile-observations-795.json)

La 795 a construit les 58 fonctions visées et vérifié 30 des 32 pipelines par relecture stricte de l’archive. Le journal confirme neuf liaisons de ces objets à l’encodeur. Pour la recette `07dfda7b60367136e9ccc12ddd8a97911537a2cb`, le vertex `9678fe6942364b79` devait fournir la valeur de l’interpolant 5 du fragment `a47117e84f2c4c0d`. La 795 a demandé cette variante au dessin et enregistré une attente de 10,2 ms à l’image 1 109. Le journal et son export incomplet ne désignent pas avec certitude le second refus. Le candidat consigne chaque descripteur absent au contrôle, sa normalisation éventuelle et les erreurs Metal.

| Image | Durée | Nouveaux PSO / bibliothèques | Temps cumulé PSO et bibliothèques | Premiers transferts de textures |
| ---: | ---: | ---: | ---: | ---: |
| 3 132 | 3 156,8 ms | 1 / 0 | 2 371,3 ms | 140 en 295,7 ms |
| 5 536 | 2 993,0 ms | 8 / 1 | 2 591,0 ms | 1 en 6,0 ms |

Les fenêtres complètes de la 795 couvrent 9 145 intervalles, à 26,886 images/s de moyenne. 213 dépassent 100 ms, 87 dépassent 200 ms et 36 dépassent 500 ms. Dans les compteurs d’usage publiés jusqu’à l’image 9 000, huit dessins graphiques et quinze dessins de maillage ou de tâche ont été sautés pendant la construction du pipeline. Ces compteurs décrivent la session entière. La 795 ne permet pas de les rattacher aux quatre circuits individuellement.

### Export du premier passage

Installer la mise à jour en place et laisser se terminer la préparation. Sélectionner la Coupe Champignon en 150 cc et effectuer les quatre courses dans la même session. Exporter le journal hôte et l’archive de préparation associés au même lancement. La commande `python3 tools/s2arm_prototype/shader_session_metrics.py host.log` regroupe les fenêtres complètes par ressource de circuit et garde les fenêtres non attribuables dans une catégorie distincte. Les identifiants de ressources proviennent des lectures du jeu. Seule la correspondance du premier circuit avec `FirstCircuit_A_00[Game03]` a été attestée dans la source. Une capture vidéo synchronisée permet de vérifier les effets, la transparence, les textures et l’ordre des circuits sur l’appareil.

Le journal dissocie attente du pipeline, attente d’une bibliothèque partagée, traduction, création de bibliothèque depuis le MSL, et transferts de textures. L’archive de préparation fournit les états de récupération et les reçus stricts disponibles. Pour chaque intervalle supérieur à 100 ms, le journal donne aussi le numéro d’image, la durée et les coûts mesurés. Le rapport les regroupe dans `slowFramesByAsset` et indique ceux qui dépassent strictement 500 ms. Les gains de fluidité du candidat demandent la mesure de ce premier passage sur iPhone.
